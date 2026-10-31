"""Restart-safe, time-limited v5.6 Telegram notifications.

PENDING is persisted on an independent GitHub branch before sending. Delivery
is at-least-once on ambiguous failures (a Telegram success then a GitHub
save failure may duplicate once). All events expire before they can become a
late scalp entry alert; completed/expired events are not retried forever.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from urllib.parse import quote
from zoneinfo import ZoneInfo

from monitor_delivery import GitHubStateStore, DeliveryError
from scalp_engine import ScalpObservation, ScalpSettings


STATE_BRANCH = "orbit-scalp-state"
STATE_FILE = ".orbit-scalp/scalp-alerts.json"
BKK = ZoneInfo("Asia/Bangkok")
PHASES = {"WATCH", "READY", "CANCELLED", "EXPIRED"}


def empty_state() -> dict:
    return {"schema": 1, "signals": {}, "pending": [], "sent": [], "ready_day": []}


def validate_state(state: object) -> dict:
    if (not isinstance(state, dict) or set(state) != {"schema", "signals", "pending", "sent", "ready_day"}
            or state["schema"] != 1 or not isinstance(state["signals"], dict)
            or not isinstance(state["pending"], list) or not isinstance(state["sent"], list)
            or not isinstance(state["ready_day"], list) or len(state["signals"]) > 30
            or len(state["pending"]) > 100 or len(state["sent"]) > 500
            or len(state["ready_day"]) > 200):
        raise ValueError("Scalp state invalid; stop to avoid duplicate alerts")
    for key, item in state["signals"].items():
        if (not isinstance(key, str) or not isinstance(item, dict)
                or set(item) != {"setup", "phase", "expires_at"}
                or not isinstance(item["setup"], str) or item["phase"] not in PHASES
                or not isinstance(item["expires_at"], str)):
            raise ValueError("Scalp state setup malformed")
    for item in state["pending"]:
        if (not isinstance(item, dict) or set(item) != {"id", "text", "expires_at"}
                or not isinstance(item["id"], str) or not re.fullmatch(r"[a-f0-9]{24}", item["id"])
                or not isinstance(item["text"], str) or len(item["text"]) > 4000
                or not isinstance(item["expires_at"], str)):
            raise ValueError("Scalp state pending malformed")
    if (any(not isinstance(x, str) or not re.fullmatch(r"[a-f0-9]{24}", x)
            for x in state["sent"]) or
            any(not isinstance(x, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}:[a-f0-9]{24}", x)
                for x in state["ready_day"])):
        raise ValueError("Scalp state history malformed")
    return state


def serialise_state(state: dict) -> bytes:
    validate_state(state)
    return json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _price(val: float | None) -> str:
    if val is None:
        return "—"
    if val >= 100:
        return f"{val:,.2f}"
    if val >= 1:
        return f"{val:.4f}"
    return f"{val:.10f}".rstrip("0").rstrip(".")


def message(ob: ScalpObservation, kind: str) -> str:
    direction = ("แผนเดิม" if kind in ("CANCELLED", "EXPIRED") else
                 "SPOT BUY" if ob.venue == "BINANCE_TH_SPOT" else
                 "FUTURES LONG" if ob.side == "LONG" else "FUTURES SHORT")
    venue = ("Binance TH · Spot" if ob.venue == "BINANCE_TH_SPOT" else
             "Bitget · USDT Perpetual" if ob.venue == "BITGET_USDT_FUTURES" else
             "Binance Global · USDⓈ-M")
    title = {"WATCH": "🟡 เฝ้าดู (ยังไม่เข้าซื้อ)",
             "READY": "🟢 สัญญาณ Scalp ยืนยัน (มีเวลาจำกัด)",
             "CANCELLED": "🔴 ยกเลิก Setup (ห้ามใช้แผนเดิม)",
             "EXPIRED": "⚪ หมดเวลา Setup (ห้ามใช้แผนเดิม)"}[kind]
    parts = [f"🪐 Orbit Scalp Signal v5.7 · {title}",
             f"{direction} | {ob.symbol}", f"ตลาด: {venue}",
             f"สแกน: {ob.checked_at.astimezone(BKK):%d/%m/%Y %H:%M:%S} (ไทย)",
             f"เหตุผล: {ob.reason[:170]}"]
    if kind in ("WATCH", "READY") and ob.entry is not None:
        parts += [f"ราคาอ้างอิง Bid/Ask: {_price(ob.entry)} USDT (ไม่ใช่ราคา Fill)",
                  f"Stop: {_price(ob.stop)} | TP1: {_price(ob.tp1)} | TP2: {_price(ob.tp2)}",
                  f"ประมาณ {ob.notional_usdt:.2f} USDT · Qty {ob.qty:g} · Risk {ob.risk_usdt:.3f} USDT",
                  f"Net TP2 R:R ~{ob.net_rr:.2f}:1 รวมค่าธรรมเนียมและ Slippage สมมติ",
                  f"Spread {ob.spread_bps:.1f} bps"]
    if kind == "READY" and ob.expires_at:
        parts.append(f"หมดอายุ READY: {ob.expires_at.astimezone(BKK):%H:%M:%S} น. (ไทย)")
    parts += ["โหมด PAPER ONLY · ไม่มีการส่งคำสั่งซื้อขาย · ไม่รับประกันกำไร",
              "ตรวจ Spread, ราคา, ค่าธรรมเนียม และจำนวนขั้นต่ำในบัญชีจริงก่อนตัดสินใจ"]
    if ob.venue == "BINANCE_GLOBAL_USDM":
        parts.append("⚠️ Futures เสี่ยงถูกบังคับปิดสถานะ; ไม่แนะนำ Leverage สำหรับทุนเล็ก")
    if ob.venue == "BITGET_USDT_FUTURES":
        parts.append("⚠️ ราคาจาก Bitget Futures เท่านั้น ไม่ใช่จุดเข้า Binance Global; "
                     "ต้องเช็กตลาดและสัญญาจริงก่อนใช้")
    return "\n".join(parts)[:3900]


def _event_id(key: str, setup: str, kind: str) -> str:
    return hashlib.sha256(f"{key}|{setup}|{kind}".encode()).hexdigest()[:24]


def _date(now: datetime) -> str:
    return now.astimezone(BKK).strftime("%Y-%m-%d")


def transition(state: dict, observations: list[ScalpObservation], settings: ScalpSettings,
               *, now: datetime) -> list[str]:
    """Persist only phase changes; one WATCH and one READY max per setup."""
    validate_state(state)
    date = _date(now)
    state["ready_day"] = [x for x in state["ready_day"] if x.startswith(date + ":")][-100:]
    state["sent"] = state["sent"][-400:]
    messages = []
    known = set(state["sent"]) | {v["id"] for v in state["pending"]}

    def queue(key: str, ob: ScalpObservation, kind: str, setup_id: str, until: datetime):
        event_id = _event_id(key, setup_id, kind)
        if event_id in known:
            return
        if until <= now:
            return
        txt = message(ob, kind)
        state["pending"].append({"id": event_id, "text": txt, "expires_at": until.isoformat()})
        known.add(event_id)
        messages.append(f"{key} {kind}")

    for ob in observations:
        key = f"{ob.venue}:{ob.symbol}"
        old = state["signals"].get(key)
        if ob.state == "DATA_UNAVAILABLE":
            # Never cancel a live setup because the venue is unavailable.
            continue
        if ob.state in ("WATCH", "READY") and ob.setup_id and ob.setup_expires_at:
            if old and old["setup"] != ob.setup_id and old["phase"] in ("WATCH", "READY"):
                # Historic setup is no longer executable; no old price is reused.
                old["phase"] = "CANCELLED"
            marker = ob.setup_id
            if ob.state == "READY":
                rid = _event_id(key, marker, "READY")
                already_counted = date + ":" + rid in state["ready_day"]
                budget = min(settings.max_ready_alerts_per_day,
                             int(settings.daily_risk_budget_pct / settings.risk_per_trade_pct + 1e-9))
                if not already_counted and len(state["ready_day"]) >= budget:
                    # Daily *alert* risk budget (not a claim about real positions).
                    state["signals"][key] = {"setup": marker, "phase": "WATCH",
                                              "expires_at": ob.setup_expires_at.isoformat()}
                    messages.append(f"{key}: daily risk alert budget reached")
                    continue
                if not already_counted:
                    state["ready_day"].append(date + ":" + rid)
                if ob.expires_at:
                    queue(key, ob, "READY", marker, ob.expires_at)
                phase = "READY"
            else:
                # If READY already fired, don't revert to WATCH during 1m pause.
                phase = "READY" if old and old["setup"] == marker and old["phase"] == "READY" else "WATCH"
                if phase == "WATCH":
                    queue(key, ob, "WATCH", marker, ob.setup_expires_at)
            state["signals"][key] = {"setup": marker, "phase": phase,
                                      "expires_at": ob.setup_expires_at.isoformat()}
        elif old and old["phase"] in ("WATCH", "READY") and old["setup"]:
            try:
                deadline = datetime.fromisoformat(old["expires_at"])
            except ValueError:
                raise ValueError("Scalp state expiry malformed") from None
            if deadline.tzinfo is None:
                raise ValueError("Scalp state expiry missing timezone")
            kind = "EXPIRED" if now >= deadline else "CANCELLED"
            # These informational events are also short-lived; late notices
            # are dropped rather than advertised as current signals.
            queue(key, ob, kind, old["setup"], now.replace(microsecond=0) + timedelta(minutes=30))
            old["phase"] = kind
    if len(state["pending"]) > 100:
        raise ValueError("Scalp pending queue full; stop to avoid data loss")
    validate_state(state)
    return messages


class ScalpStateStore(GitHubStateStore):
    """Uses existing official GitHub client but an entirely separate branch."""

    def load(self) -> dict:
        self.exists = self._request("GET", "/git/ref/heads/" + STATE_BRANCH, missing_ok=True) is not None
        if not self.exists:
            self.current_blob = None
            self.file_sha = None
            return empty_state()
        item = self._request("GET", "/contents/" + quote(STATE_FILE, safe="/") + "?ref=" + STATE_BRANCH,
                             missing_ok=True)
        if item is None:
            self.current_blob = None
            self.file_sha = None
            return empty_state()
        try:
            if item["encoding"] != "base64":
                raise ValueError("encoding invalid")
            blob = base64.b64decode(item["content"], validate=False)
            state = validate_state(json.loads(blob))
            self.file_sha = item["sha"]
            self.current_blob = blob
            return state
        except (TypeError, KeyError, ValueError, UnicodeError):
            raise DeliveryError("Scalp state ผิดรูปแบบ; หยุดส่งป้องกันข้อความซ้ำ") from None

    def save(self, state: dict) -> bool:
        blob = serialise_state(state)
        if blob == self.current_blob:
            return False
        if not self.exists:
            self._request("POST", "/git/refs", {"ref": "refs/heads/" + STATE_BRANCH,
                                                   "sha": self.default_sha})
            self.exists = True
        body = {"message": "chore(orbit): scalp signal state [skip ci]",
                "content": base64.b64encode(blob).decode("ascii"), "branch": STATE_BRANCH}
        if self.file_sha:
            body["sha"] = self.file_sha
        data = self._request("PUT", "/contents/" + quote(STATE_FILE, safe="/"), body)
        if not isinstance(data.get("content"), dict) or not data["content"].get("sha"):
            raise DeliveryError("GitHub ยังไม่ยืนยันการบันทึก Scalp state")
        self.file_sha = data["content"]["sha"]
        self.current_blob = blob
        return True


def send_pending(state: dict, store: ScalpStateStore, token: str, chat_id: str,
                 *, now: datetime | None = None) -> tuple[int, int]:
    """Save intent first; suppress any outdated entry notice before delivery."""
    from monitor_delivery import send_telegram

    validate_state(state)
    store.save(state)
    sent, dropped = 0, 0
    for item in list(state["pending"]):
        instant = now or datetime.now(timezone.utc)
        try:
            expires = datetime.fromisoformat(item["expires_at"])
        except ValueError:
            raise DeliveryError("Pending Scalp expiry invalid") from None
        if expires.tzinfo is None:
            raise DeliveryError("Pending Scalp expiry missing timezone")
        if instant >= expires:
            dropped += 1
        else:
            send_telegram(token, chat_id, item["text"])
            sent += 1
        state["sent"].append(item["id"])
        state["sent"] = state["sent"][-400:]
        state["pending"].remove(item)
        store.save(state)
    return sent, dropped
