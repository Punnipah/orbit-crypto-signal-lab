"""Deterministic, restart-safe alert transitions and pending outbox.

The outbox is persisted to a private-ish state branch *before* Telegram calls.
Delivery is at-least-once on certain failures, not exactly-once: a Telegram
success followed by a GitHub write failure can still produce a duplicate.
No watch token, bot token or chat ID is ever included in persisted state.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from zoneinfo import ZoneInfo

from display_format import format_price
from monitor_engine import Observation


IMPORTANT = {"READY_NOW", "MTF_READY", "INVALIDATED", "PASSED", "EXPIRED"}
READY = {"READY_NOW", "MTF_READY"}
MAX_QUEUE = 100
BKK = ZoneInfo("Asia/Bangkok")


def empty_state() -> dict:
    return {"version": 1, "symbols": {}, "pending": []}


def validate_state(data: object) -> dict:
    if (not isinstance(data, dict) or set(data) != {"version", "symbols", "pending"}
            or data["version"] != 1 or not isinstance(data["symbols"], dict)
            or not isinstance(data["pending"], list) or len(data["pending"]) > MAX_QUEUE):
        raise ValueError("รูปแบบ monitor state ไม่รองรับ")
    for name, value in data["symbols"].items():
        if not isinstance(name, str) or not isinstance(value, dict):
            raise ValueError("monitor state มี symbol status ผิดรูปแบบ")
    for row in data["pending"]:
        if not isinstance(row, dict) or set(row) != {"id", "text", "symbol", "kind"} or not all(
                isinstance(row[key], str) for key in ("id", "text", "symbol", "kind")):
            raise ValueError("monitor pending event ผิดรูปแบบ")
    return data


def _fingerprint(plan_token: str | None) -> str:
    return sha256((plan_token or "LIVE_MTF").encode("utf-8")).hexdigest()[:20]


def _event_id(symbol: str, fp: str, kind: str, marker: str = "") -> str:
    return sha256(f"{symbol}/{fp}/{kind}/{marker}".encode()).hexdigest()[:24]


def _fmt(value: float | None) -> str:
    return format_price(value) if value is not None else "ไม่พร้อม"


def build_message(observation: Observation, kind: str) -> str:
    titles = {
        "READY_NOW": "🟢 Frozen Entry Trigger ผ่าน (ตรวจเองก่อนซื้อ)",
        "MTF_READY": "🟡 MTF สด READY (ยังไม่ได้ล็อกโซน)",
        "INVALIDATED": "🔴 แผนที่ล็อกถูกยกเลิก",
        "PASSED": "⚪ จังหวะแผนเดิมผ่านไปแล้ว",
        "EXPIRED": "⚪ แผนล็อกหมดอายุ",
        "NO_LONGER_READY": "🟠 สัญญาณ READY เดิมไม่ผ่านแล้ว",
        "COINGLASS_STALE": "⚠️ CoinGlass ที่กรอกเก่า/ใช้ไม่ได้",
        "DATA_UNAVAILABLE": "⚠️ ดึงข้อมูลสำคัญไม่ได้สองรอบติด",
        "RECOVERED": "✅ ระบบดึงข้อมูลกลับมาทำงานได้",
    }
    if kind not in titles:
        raise ValueError("เหตุแจ้งเตือนไม่รองรับ")
    at = observation.observed_at.astimezone(BKK).strftime("%d/%m/%Y %H:%M น. (ไทย)")
    parts = ["🪐 Orbit Crypto Signal Lab v4.1", titles[kind],
             f"คู่: {observation.symbol}", f"ตรวจเมื่อ: {at}",
             f"Spot ล่าสุด (ไม่ใช่ราคาเสนอขาย): {_fmt(observation.last_price)} USDT"]
    if observation.entry_low is not None and observation.entry_high is not None:
        parts.append(f"Entry Zone: {_fmt(observation.entry_low)}–{_fmt(observation.entry_high)}")
    if observation.stop_loss is not None:
        parts.append(f"Stop: {_fmt(observation.stop_loss)} · TP1: {_fmt(observation.tp1)} · TP2: {_fmt(observation.tp2)}")
    if observation.alignment is not None:
        parts.append(f"MTF Alignment: {observation.alignment:.1f}/100 (ไม่ใช่ Win Rate)")
    parts.append(f"Futures: {observation.futures_source[:140]}")
    parts.append(f"CoinGlass Manual: {observation.coinglass_status}")
    parts.append(f"สถานะปัจจุบัน: {observation.status}")
    if observation.trigger_at is not None:
        label = "แท่ง Trigger ปิด" if observation.mode == "FROZEN" else "แท่ง 15m ที่อ้างอิงปิด"
        parts.append(f"{label}: {observation.trigger_at.astimezone(BKK):%d/%m %H:%M} น. (ไทย)")
    parts.append("เหตุผล: " + observation.reason[:340])
    if observation.failed_checks and kind in {"NO_LONGER_READY", "DATA_UNAVAILABLE"}:
        parts.append("ยังไม่ผ่าน: " + ", ".join(observation.failed_checks[:4])[:200])
    if observation.mode == "FROZEN":
        parts.append("เปิด Bookmark แผนล็อกเดิมที่มี ?watch= ก่อนตัดสินใจ")
    else:
        parts.append("ยังไม่มี Frozen Watch ของคู่นี้; สัญญาณ MTF สดอาจเปลี่ยนทุกครั้ง")
    parts.append("⚠️ เป็นสัญญาณทดลอง ไม่รับประกันผล และไม่มีการส่งออเดอร์")
    return "\n".join(parts)[:3800]


def transition(state: dict, observations: list[Observation]) -> dict:
    """Mutates a validated state with important changes only; no WAIT spam."""
    validate_state(state)
    ids = {notice["id"] for notice in state["pending"]}
    for ob in observations:
        fp = _fingerprint(ob.watch_token)
        old = state["symbols"].get(ob.symbol, {})
        if old.get("plan_fingerprint") != fp:
            # Never deliver a pending alert for an older frozen plan/link.
            state["pending"] = [row for row in state["pending"] if row["symbol"] != ob.symbol]
            old = {}
        if ob.status not in READY:
            # A delayed Telegram outage must never turn an old READY into a
            # fresh-looking buy notification after the signal disappeared.
            state["pending"] = [row for row in state["pending"] if not (
                row["symbol"] == ob.symbol and row["kind"] in READY)]
        ids = {notice["id"] for notice in state["pending"]}
        prev_status = old.get("status")
        prev_cg = old.get("coinglass")
        source_problem = (ob.status == "DATA_UNAVAILABLE" or ob.futures_source == "MISSING"
                          or ob.last_price is None
                          or "สภาพคล่อง Spot" in ob.failed_checks
                          or "ภาวะตลาด BTC" in ob.failed_checks)
        err_count = (int(old.get("errors", 0)) + 1 if source_problem else 0)
        err_count = min(2, err_count)
        seen = list(old.get("seen", []))[-100:]
        last_ready_id = old.get("last_ready_id")
        queued: list[tuple[str, str]] = []
        if ob.status in IMPORTANT and ob.status != prev_status:
            marker = (ob.trigger_at.isoformat() if ob.status in READY and ob.trigger_at
                      else ob.observed_at.strftime("%Y%m%d%H") if ob.status == "MTF_READY"
                      else "")
            event_id = _event_id(ob.symbol, fp, ob.status, marker)
            queued.append((event_id, ob.status))
            if ob.status in READY:
                last_ready_id = event_id
        if prev_status in READY and ob.status not in IMPORTANT and ob.status != "DATA_UNAVAILABLE":
            queued.append((_event_id(ob.symbol, fp, "NO_LONGER_READY", last_ready_id or ""),
                           "NO_LONGER_READY"))
        if ob.coinglass_status == "INVALID" and prev_cg != "INVALID":
            queued.append((_event_id(ob.symbol, fp, "COINGLASS_STALE", ob.observed_at.strftime("%Y%m%d%H")),
                           "COINGLASS_STALE"))
        if source_problem and err_count == 2 and int(old.get("errors", 0)) < 2:
            queued.append((_event_id(ob.symbol, fp, "DATA_UNAVAILABLE"), "DATA_UNAVAILABLE"))
        if not source_problem and int(old.get("errors", 0)) == 2:
            queued.append((_event_id(ob.symbol, fp, "RECOVERED", ob.observed_at.strftime("%Y%m%d")),
                           "RECOVERED"))
        for notice_id, kind in queued:
            if notice_id in seen or notice_id in ids:
                continue
            if len(state["pending"]) >= MAX_QUEUE:
                raise RuntimeError("Telegram pending เต็ม: หยุดเพิ่มแจ้งเตือนจนกว่าจะส่งสำเร็จ")
            state["pending"].append({"id": notice_id, "text": build_message(ob, kind),
                                     "symbol": ob.symbol, "kind": kind})
            ids.add(notice_id)
            seen.append(notice_id)
        state["symbols"][ob.symbol] = {
            "plan_fingerprint": fp,
            "status": ob.status,
            "coinglass": ob.coinglass_status,
            "errors": err_count,
            "last_ready_id": last_ready_id,
            "seen": seen[-100:],
        }
    return state


def remove_sent(state: dict, sent_id: str) -> dict:
    validate_state(state)
    state["pending"] = [row for row in state["pending"] if row["id"] != sent_id]
    return state


def serialize_state(state: dict) -> bytes:
    validate_state(state)
    return (json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
