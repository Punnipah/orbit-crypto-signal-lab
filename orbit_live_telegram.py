"""Isolated Orbit Live Signal Telegram notifier (no brokerage orders).

Intended for the dedicated default-branch GitHub Actions scheduler, which
checks out experiment/orbit-model-lab. Existing production monitors untouched.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from monitor_delivery import DeliveryError, send_telegram
from orbit_live_planner import LivePlan, build_live_plan
from orbit_model_lab_engine import DataUnavailable, VENUES, fetch_candles


STATE_BRANCH = "orbit-live-telegram-state"
STATE_PATH = ".orbit-live/signal-notifications.json"
MARKET_URL = "https://orbit-crypto-signal-lab-yutfuwuihmsjovxpfize6v.streamlit.app/"
SYMBOLS = ("PEPEUSDT", "BTCUSDT", "DOGEUSDT")
VENUE_IDS = ("BINANCE_TH_SPOT", "BINANCE_GLOBAL_USDM", "BITGET_USDT_FUTURES")
MAX_SIGNAL_AGE_MINUTES = 22
LOOKBACK_CANDLES = 4


def display_price(value: float | None) -> str:
    if value is None:
        return "—"
    if value < .00001:
        return f"{value:.10f}".rstrip("0").rstrip(".")
    if value < .001:
        return f"{value:.9f}".rstrip("0").rstrip(".")
    if value < .1:
        return f"{value:.7f}".rstrip("0").rstrip(".")
    if value < 10:
        return f"{value:.5f}".rstrip("0").rstrip(".")
    return f"{value:,.2f}"


def signal_key(venue: str, symbol: str, plan: LivePlan) -> str:
    stamp = plan.closed_at.astimezone(timezone.utc).strftime("%Y%m%d%H%M")
    return f"{venue}/{symbol}/{stamp}/{plan.direction}"


def signal_text(venue: str, symbol: str, plan: LivePlan) -> str:
    """Reference levels must be labelled non-executable and time-bound."""
    th_time = plan.closed_at.astimezone(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M")
    zones = "\n".join(
        f"• {label}: {display_price(low)} – {display_price(high)} USDT"
        for label, low, high, _ in plan.entry_zones
    )
    return (
        f"🪐 ORBIT LIVE · {plan.status}\n"
        f"📊 {symbol} · {VENUES[venue][0]}\n"
        f"🕘 แท่ง 5m ปิด {th_time} น. (ไทย)\n"
        f"📈 MTF: {plan.regime} · {plan.strength}\n"
        f"💹 ราคาปิดอ้างอิง: {display_price(plan.reference_close)} USDT\n"
        f"🎯 โซนเฝ้ารอ:\n{zones}\n"
        f"📍 ราคาเข้าอ้างอิง: {display_price(plan.entry_reference)} USDT\n"
        f"🛑 Stop Loss: {display_price(plan.stop)} USDT\n"
        f"✅ Take Profit 1: {display_price(plan.take_profit_1)} USDT\n"
        f"✅ Take Profit 2: {display_price(plan.take_profit_2)} USDT\n"
        f"💰 เพดานสถานะ (ไม่ใช้ Leverage): "
        f"{plan.max_notional_usdt:.2f} USDT\n"
        "⚠️ สัญญาณจากแท่งปิด ไม่ใช่คำสั่งซื้อขาย; "
        "ตรวจราคา Bid/Ask และต้นทุนจริงก่อนตัดสินใจ "
        "ไม่รับประกันกำไร\n"
        f"📱 {MARKET_URL}"
    )


class GitHubAlertState:
    """Persist dedup IDs on a dedicated state branch, never on main."""

    def __init__(self, repository: str, token: str, sha: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise DeliveryError("GITHUB_REPOSITORY ไม่ถูกต้อง")
        if not token or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
            raise DeliveryError("GITHUB_TOKEN / GITHUB_SHA ไม่พร้อม")
        self.api = f"https://api.github.com/repos/{repository}"
        self.token = token
        self.sha = sha
        self.branch_exists = False
        self.file_sha: str | None = None

    def _api(self, method: str, path: str, payload: dict | None = None,
             *, missing_ok: bool = False) -> dict | None:
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.api + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "OrbitLiveTelegram/1.0",
        })
        try:
            with urlopen(request, timeout=25) as response:
                result = json.load(response)
        except HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            raise DeliveryError(f"GitHub state HTTP {exc.code}; ตรวจสิทธิ์ Actions contents:write") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise DeliveryError("GitHub state ติดต่อไม่ได้") from None
        if not isinstance(result, dict):
            raise DeliveryError("GitHub state รูปแบบ JSON ผิด")
        return result

    def load(self) -> dict:
        ref = self._api("GET", f"/git/ref/heads/{STATE_BRANCH}", missing_ok=True)
        if ref is None:
            self.branch_exists = False
            return {"version": 1, "sent": {}}
        self.branch_exists = True
        blob = self._api("GET", "/contents/" + quote(STATE_PATH, safe="/") +
                         "?ref=" + STATE_BRANCH, missing_ok=True)
        if blob is None:
            return {"version": 1, "sent": {}}
        self.file_sha = blob.get("sha")
        try:
            value = json.loads(base64.b64decode(blob["content"]))
        except (KeyError, TypeError, ValueError):
            raise DeliveryError("State เสียหาย · หยุดเพื่อกันข้อความซ้ำ") from None
        if (not isinstance(value, dict) or value.get("version") != 1 or
                not isinstance(value.get("sent"), dict)):
            raise DeliveryError("State schema ไม่รองรับ · หยุดส่ง")
        return value

    def save(self, value: dict) -> None:
        if not self.branch_exists:
            self._api("POST", "/git/refs", {"ref": f"refs/heads/{STATE_BRANCH}",
                                             "sha": self.sha})
            self.branch_exists = True
        # Retain approximately 30 days of dedup IDs, bounded even in a busy market.
        recent = sorted(value["sent"].items(), key=lambda pair: pair[1])[-1500:]
        value["sent"] = dict(recent)
        payload = {"message": "chore: record isolated Orbit Live Telegram alert [skip ci]",
                   "branch": STATE_BRANCH,
                   "content": base64.b64encode(json.dumps(value, ensure_ascii=False,
                                                          sort_keys=True).encode()).decode()}
        if self.file_sha:
            payload["sha"] = self.file_sha
        result = self._api("PUT", "/contents/" + quote(STATE_PATH, safe="/"), payload)
        if not isinstance(result.get("content"), dict) or not result["content"].get("sha"):
            raise DeliveryError("GitHub ไม่ยืนยัน state SHA")
        self.file_sha = result["content"]["sha"]


def collect_recent_signals(venue: str, symbol: str, *, now: datetime) -> list[LivePlan]:
    candles = fetch_candles(venue, symbol, 7, now=now)
    found: list[LivePlan] = []
    # Slice after the respective closed candle. Never peek into future candles.
    # One extra predecessor identifies a new transition into SIGNAL, rather
    # than alerting on every consecutive 5m bar that remains SIGNAL.
    previous_signal = ""
    for tail in range(LOOKBACK_CANDLES, -1, -1):
        portion = candles.iloc[:-tail] if tail else candles
        plan = build_live_plan(portion, venue)
        age = (now - plan.closed_at).total_seconds()
        current_signal = plan.status if plan.status.startswith("SIGNAL ") else ""
        if (tail < LOOKBACK_CANDLES and current_signal and
                current_signal != previous_signal and
                -60 <= age <= MAX_SIGNAL_AGE_MINUTES * 60 and
                plan.stop is not None and plan.take_profit_2 is not None and
                plan.max_notional_usdt is not None):
            found.append(plan)
        previous_signal = current_signal
    return found


def scan_and_send(*, now: datetime | None = None, venues: tuple[str, ...] = VENUE_IDS,
                  symbols: tuple[str, ...] = SYMBOLS) -> dict:
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise DeliveryError("เวลา scan ต้องมี timezone")
    bot, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    token, sha = os.getenv("GITHUB_TOKEN", ""), os.getenv("GITHUB_SHA", "")
    if not bot or not chat:
        raise DeliveryError("Telegram secrets ไม่พร้อม · ไม่มีการส่งข้อความ")
    store = GitHubAlertState(repo, token, sha)
    state = store.load()
    succeeded, errors, sent, duplicates = 0, [], 0, 0
    for venue in venues:
        for symbol in symbols:
            try:
                signals = collect_recent_signals(venue, symbol, now=stamp)
            except (DataUnavailable, ValueError, KeyError) as exc:
                errors.append(f"{venue}/{symbol}: {str(exc)[:140]}")
                continue
            succeeded += 1
            for plan in signals:
                key = signal_key(venue, symbol, plan)
                if key in state["sent"]:
                    duplicates += 1
                    continue
                send_telegram(bot, chat, signal_text(venue, symbol, plan))
                state["sent"][key] = plan.closed_at.astimezone(timezone.utc).isoformat()
                store.save(state)  # Commit after every successfully sent message.
                sent += 1
    for err in errors:
        print("MARKET UNAVAILABLE:", err)
    print(f"Orbit Live Telegram: markets_ok={succeeded} failed={len(errors)} "
          f"sent={sent} already_sent={duplicates}")
    if succeeded == 0:
        raise DeliveryError("ทุกตลาดไม่พร้อม · ห้ามส่งสัญญาณโดยใช้ข้อมูลสำรอง")
    return {"markets_ok": succeeded, "failed": len(errors), "sent": sent,
            "already_sent": duplicates}


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--test-telegram", action="store_true",
                     help="Send a single connection test; no simulated trading signal")
    args = cli.parse_args()
    try:
        if args.test_telegram:
            send_telegram(os.getenv("TELEGRAM_BOT_TOKEN", ""),
                          os.getenv("TELEGRAM_CHAT_ID", ""),
                          "✅ Orbit Live Signal · Telegram เชื่อมต่อสำเร็จ\n"
                          "⏰ ตั้งสแกนทุก 15 นาที · ส่งเฉพาะ SIGNAL ใหม่จากแท่งปิด\n"
                          "⚠️ ไม่ใช่คำสั่งซื้อขาย และไม่รับประกันกำไร")
            print("Telegram connection test accepted by Bot API")
        else:
            scan_and_send()
        return 0
    except DeliveryError as exc:
        print(f"Orbit Live Telegram BLOCKED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
