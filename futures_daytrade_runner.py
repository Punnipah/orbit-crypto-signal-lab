"""Separate, read-only Futures LONG/SHORT monitor for GitHub Actions.

No shared Spot configuration/state and no trade execution. Separate GitHub
state branch keeps Futures notifications independent of the Spot bot.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from futures_daytrade import (FuturesDataError, FuturesObservation, evaluate_futures,
                              fetch_futures_catalog, fetch_futures_klines,
                              fetch_futures_ticker, read_futures_settings)
from futures_paper import empty_paper, update_paper
from futures_backup import fetch_backup_pair, fetch_backup_klines, fetch_backup_ticker
from futures_symbols import resolve_futures_pair
from monitor_delivery import send_telegram


ROOT = Path(__file__).resolve().parent
STATE_BRANCH = "orbit-futures-state"
STATE_FILE = ".orbit-futures/daytrade-alerts.json"


def empty_state() -> dict:
    return {"schema": 2, "signals": {}, "sent": [], "pending": [],
            "paper": empty_paper(), "health": {}}


def validate_state(value: dict) -> None:
    if not isinstance(value, dict) or value.get("schema") not in (1, 2):
        raise ValueError("Futures state invalid")
    fields = ({"schema", "signals", "sent", "pending"} if value["schema"] == 1 else
              {"schema", "signals", "sent", "pending", "paper", "health"})
    if (set(value) != fields or not isinstance(value["signals"], dict)
            or not isinstance(value["sent"], list) or not isinstance(value["pending"], list)
            or len(value["signals"]) > 20 or len(value["sent"]) > 300
            or len(value["pending"]) > 100):
        raise ValueError("Futures state invalid")
    if (any(not isinstance(x, str) or not re.fullmatch("[0-9a-f]{24}", x) for x in value["sent"])
            or any(not isinstance(v, dict) or set(v) != {"setup", "state"}
                   or not isinstance(v["setup"], str) or not isinstance(v["state"], str)
                   for v in value["signals"].values())
            or any(not isinstance(x, dict) or set(x) != {"id", "text"}
                   or not isinstance(x["id"], str) or not isinstance(x["text"], str)
                   or len(x["text"]) > 4000 for x in value["pending"])):
        raise ValueError("Futures alert state malformed")
    if value["schema"] == 2:
        paper = value["paper"]
        if (not isinstance(paper, dict) or set(paper) != {"active", "history", "seen"}
                or not isinstance(paper["active"], dict) or len(paper["active"]) > 10
                or not isinstance(paper["history"], list) or len(paper["history"]) > 400
                or not isinstance(paper["seen"], list) or len(paper["seen"]) > 800
                or any(not isinstance(item, dict) for item in paper["history"])
                or any(not isinstance(item, str) for item in paper["seen"])
                or any(not isinstance(item, dict) for item in paper["active"].values())
                or not isinstance(value["health"], dict)):
            raise ValueError("Futures paper state malformed")


class FuturesStateStore:
    def __init__(self, repository: str, token: str, default_sha: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("GITHUB_REPOSITORY missing")
        if not token or not re.fullmatch(r"[0-9a-fA-F]{40}", default_sha):
            raise ValueError("GITHUB_TOKEN/GITHUB_SHA missing")
        self.root = f"https://api.github.com/repos/{repository}"
        self.token = token
        self.default_sha = default_sha
        self.exists = False
        self.sha = None
        self.blob = None

    def request(self, method: str, path: str, payload: dict | None = None,
                *, missing_ok: bool = False):
        req = Request(self.root + path, method=method,
                      data=json.dumps(payload).encode("utf-8") if payload is not None else None,
                      headers={"Authorization": f"Bearer {self.token}",
                               "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28",
                               "Content-Type": "application/json",
                               "User-Agent": "OrbitFuturesAlerts/1.0"})
        try:
            with urlopen(req, timeout=25) as response:
                result = json.load(response)
        except HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            raise RuntimeError(f"GitHub state HTTP {exc.code}; check contents:write") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise RuntimeError("GitHub Futures state API unavailable") from None
        if not isinstance(result, dict):
            raise RuntimeError("GitHub response malformed")
        return result

    def load(self) -> dict:
        self.exists = self.request("GET", f"/git/ref/heads/{STATE_BRANCH}", missing_ok=True) is not None
        if not self.exists:
            return empty_state()
        payload = self.request("GET", f"/contents/{quote(STATE_FILE, safe='/')}?ref={STATE_BRANCH}",
                               missing_ok=True)
        if payload is None:
            return empty_state()
        try:
            if payload["encoding"] != "base64":
                raise ValueError("not base64")
            blob = base64.b64decode(payload["content"])
            state = json.loads(blob)
            validate_state(state)
            if state["schema"] == 1:
                state = {**state, "schema": 2, "paper": empty_paper(), "health": {}}
            self.sha = payload["sha"]
            self.blob = blob
            return state
        except (KeyError, ValueError, TypeError, UnicodeError):
            raise RuntimeError("Futures state corrupt: stop to prevent repeat alerts") from None

    def save(self, state: dict) -> None:
        validate_state(state)
        blob = json.dumps(state, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
        if blob == self.blob:
            return
        if not self.exists:
            self.request("POST", "/git/refs", {"ref": f"refs/heads/{STATE_BRANCH}",
                                                   "sha": self.default_sha})
            self.exists = True
        body = {"message": "chore(orbit): futures alert state [skip ci]",
                "content": base64.b64encode(blob).decode("ascii"), "branch": STATE_BRANCH}
        if self.sha:
            body["sha"] = self.sha
        saved = self.request("PUT", f"/contents/{quote(STATE_FILE, safe='/')}", body)
        if not isinstance(saved.get("content"), dict) or not saved["content"].get("sha"):
            raise RuntimeError("GitHub did not confirm Futures state write")
        self.sha = saved["content"]["sha"]
        self.blob = blob


def _format_price(value: float) -> str:
    if value >= 100:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:.4f}"
    if value >= 0.01:
        return f"{value:.6f}"
    return f"{value:.9f}".rstrip("0").rstrip(".")


def telegram_message(ob: FuturesObservation) -> str:
    is_ready = ob.state.startswith("READY_")
    side_th = "เปิด Long (ขาขึ้น)" if ob.direction == "LONG" else "เปิด Short (ขาลง)"
    when = ob.checked_at.astimezone(ZoneInfo("Asia/Bangkok"))
    label = ("🟢 พร้อมพิจารณาเข้า" if is_ready else "🟡 รอราคา Retest")
    caution = ("ตรวจราคาและสภาพคล่องซ้ำก่อนตัดสินใจ ไม่ใช่ออร์เดอร์"
               if is_ready else "ยังไม่ใช่สัญญาณเข้า ห้ามไล่ราคา")
    if ob.state == "INVALIDATED":
        return (f"🪐 Orbit FUTURES v5.0\n🔴 ยกเลิก Setup {ob.direction}\n"
                f"คู่: {ob.symbol}\nเวลา: {when:%d/%m/%Y %H:%M} (ไทย)\n"
                f"เหตุผล: {ob.reason}\nไม่มีการส่งคำสั่งซื้อขาย")
    venue = ("BYBIT USDT Perpetual · WATCH ONLY (ไม่มี Taker Flow)" if ob.source != "BINANCE"
             else "BINANCE USDⓈ-M Perpetual")
    return (f"🪐 Orbit FUTURES v5.2\n{label}: {side_th}\n"
            f"คู่: {ob.symbol} | {venue}\n"
            f"เวลา: {when:%d/%m/%Y %H:%M} (ไทย)\n"
            f"ราคา Futures ล่าสุด: {_format_price(ob.last_price)} USDT\n"
            f"Entry Zone: {_format_price(ob.entry_low)} – {_format_price(ob.entry_high)}\n"
            f"Stop Loss: {_format_price(ob.stop)}\n"
            f"TP1: {_format_price(ob.tp1)} | TP2: {_format_price(ob.tp2)}\n"
            f"เป้า Net R:R TP2 (ประมาณ): {ob.net_rr_tp2:.1f}:1 หลังสมมติค่าธรรมเนียม/Slippage\n"
            f"ความเสี่ยงตามทุนสมมติใน Config: ≈{ob.risk_usdt:.2f} USDT | "
            f"Notional ≈{ob.notional_usdt:.2f} USDT\n"
            f"สถานะ: {ob.state}\n{ob.reason}\n"
            f"⚠️ {caution}; ฟิวเจอร์สเสี่ยงถูกล้างพอร์ต หากใช้ Leverage สูง")


def transition(state: dict, observations: list[FuturesObservation]) -> None:
    """Per-setup event ids, no duplicate notification on every 15-minute scan."""
    validate_state(state)
    already = set(state["sent"]) | {p["id"] for p in state["pending"]}
    for ob in observations:
        state_key = ("BYBIT:" if ob.source != "BINANCE" else "") + ob.symbol
        old = state["signals"].get(state_key, {})
        next_info = {"setup": ob.setup_id, "state": ob.state}
        if ob.state in {"WATCH_LONG", "WATCH_SHORT", "READY_LONG", "READY_SHORT"}:
            event = "WATCH" if ob.state.startswith("WATCH") else "READY"
        elif ob.state == "INVALIDATED" and old.get("setup") == ob.setup_id and old.get("state", "").startswith(("WATCH", "READY")):
            event = "INVALIDATED"
        else:
            event = None
        if event and ob.setup_id:
            event_id = hashlib.sha256(f"{state_key}|{ob.setup_id}|{event}".encode()).hexdigest()[:24]
            if event_id not in already:
                state["pending"].append({"id": event_id, "text": telegram_message(ob)})
                already.add(event_id)
        state["signals"][state_key] = next_info
    validate_state(state)


def scan(settings, *, now: datetime, frames_by_symbol: dict | None = None,
         requested_by_contract: dict | None = None) -> list[FuturesObservation]:
    frames_by_symbol = frames_by_symbol if frames_by_symbol is not None else {}
    requested_by_contract = requested_by_contract if requested_by_contract is not None else {}
    try:
        active = fetch_futures_catalog()
    except FuturesDataError as exc:
        print(f"Binance Futures catalog unavailable: {str(exc)[:80]}; trying Bybit watch-only", flush=True)
        active = set()
    results = []
    for requested in settings.symbols:
        try:
            pair = resolve_futures_pair(requested, active)
            symbol = pair.contract
            frames = {tf: fetch_futures_klines(symbol, tf, now=now) for tf in ("15m", "1h", "4h")}
            last, mark, funding = fetch_futures_ticker(symbol, now=now)
            source = "BINANCE"
        except (FuturesDataError, ValueError, TypeError, KeyError, OverflowError, OSError) as exc:
            binance_error = f"{type(exc).__name__}: {str(exc).replace(chr(10), ' ')[:120]}"
            print(f"{requested} | Binance unavailable ({binance_error}); trying Bybit WATCH fallback", flush=True)
            try:
                symbol = fetch_backup_pair(requested)
                frames = {tf: fetch_backup_klines(symbol, tf, now=now) for tf in ("15m", "1h", "4h")}
                last, mark, funding = fetch_backup_ticker(symbol, now=now)
                source = "BYBIT_WATCH_ONLY"
            except (FuturesDataError, ValueError, TypeError, KeyError, OSError) as backup_exc:
                bybit_error = f"{type(backup_exc).__name__}: {str(backup_exc).replace(chr(10), ' ')[:120]}"
                print(f"{requested} | Bybit unavailable ({bybit_error}); status=DATA_UNAVAILABLE", flush=True)
                results.append(FuturesObservation(requested, "DATA_UNAVAILABLE",
                                    f"Binance/Bybit ไม่พร้อม ({type(backup_exc).__name__})", now))
                continue
        try:
            ob = evaluate_futures(symbol, frames, last=last, mark=mark, funding_pct=funding,
                                  now=now, settings=replace(settings, symbols=(symbol,)),
                                  require_taker_flow=(source == "BINANCE"))
            ob = replace(ob, source=source)
            if source == "BINANCE":
                frames_by_symbol[symbol] = frames["15m"]
                requested_by_contract[symbol] = requested
        except (FuturesDataError, ValueError, TypeError, KeyError, OverflowError, OSError) as exc:
            ob = FuturesObservation(symbol, "DATA_UNAVAILABLE",
                                    f"ตลาด/ข้อมูลไม่พร้อม ({type(exc).__name__})", now)
        results.append(ob)
        print(f"{symbol} {ob.source} Futures | status={ob.state} | direction={ob.direction} | "
              f"setup={ob.setup_id or '-'}", flush=True)
    return results


def run(*, dry_run=False) -> int:
    settings = read_futures_settings(ROOT / "futures_daytrade_config.json")
    print(f"Orbit FUTURES Day Trade scanning {', '.join(settings.symbols)}; read-only; no orders", flush=True)
    if dry_run:
        state, store = empty_state(), None
    else:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            raise ValueError("Telegram secrets missing")
        store = FuturesStateStore(os.getenv("GITHUB_REPOSITORY", ""),
                                  os.getenv("GITHUB_TOKEN", ""), os.getenv("GITHUB_SHA", ""))
        state = store.load()
    now = datetime.now(timezone.utc)
    frames_by_symbol, requested_by_contract = {}, {}
    observations = scan(settings, now=now, frames_by_symbol=frames_by_symbol,
                        requested_by_contract=requested_by_contract)
    transition(state, observations)
    events = update_paper(state["paper"], observations, frames_by_symbol, now,
                          round_trip_cost_pct=settings.round_trip_cost_pct,
                          requested_by_contract=requested_by_contract)
    already = set(state["sent"]) | {item["id"] for item in state["pending"]}
    for event in events:
        if event["id"] not in already:
            state["pending"].append(event)
            already.add(event["id"])
    coverage = sum(ob.state != "DATA_UNAVAILABLE" for ob in observations)
    state_health = "DOWN" if coverage == 0 else "OK" if coverage == len(observations) else "DEGRADED"
    print(f"Futures market data: {coverage}/{len(observations)} | health={state_health}", flush=True)
    prior_health = state.get("health", {}).get("status")
    if state_health != "OK" and prior_health != state_health:
        event_id = hashlib.sha256(f"HEALTH|{state_health}|{now:%Y-%m-%d}".encode()).hexdigest()[:24]
        if event_id not in already:
            state["pending"].append({"id": event_id, "text":
                f"🪐 Orbit Futures v5.0 · ⚠️ {state_health}\n"
                f"ตรวจข้อมูล Futures ได้ {coverage}/{len(observations)} คู่\n"
                "ระบบงดสัญญาณในคู่ที่ข้อมูลไม่พร้อม · โปรดตรวจ GitHub Actions"})
            already.add(event_id)
    elif state_health == "OK" and prior_health in {"DOWN", "DEGRADED"}:
        event_id = hashlib.sha256(f"HEALTH|RECOVERED|{now:%Y-%m-%d}".encode()).hexdigest()[:24]
        if event_id not in already:
            state["pending"].append({"id": event_id, "text":
                f"✅ Orbit Futures v5.0 · ข้อมูลกลับมาพร้อม {coverage}/{len(observations)} คู่"})
            already.add(event_id)
    state["health"] = {"last_scan_at": now.isoformat(),
                       "monitored": len(observations), "status": state_health,
                       "market_data_ok": coverage,
                       "paper_active": len(state["paper"]["active"]),
                       "paper_closed": len(state["paper"]["history"]),
                       "monitor": "futures", "version": "5.0"}
    validate_state(state)
    print(f"Pending FUTURES alert events: {len(state['pending'])}", flush=True)
    if dry_run:
        return 0
    store.save(state)  # Outbox before Telegram send.
    count = 0
    while state["pending"]:
        pending = state["pending"][0]
        send_telegram(token, chat_id, pending["text"])
        state["sent"].append(pending["id"])
        state["sent"] = state["sent"][-300:]
        state["pending"].pop(0)
        store.save(state)
        count += 1
    print(f"FUTURES run complete; Telegram sent={count}; exchange orders=0", flush=True)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Independent Orbit Futures Day Trade Alerts")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-config", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--test-telegram", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.validate_config:
            cfg = read_futures_settings(ROOT / "futures_daytrade_config.json")
            print(f"Futures config OK: {', '.join(cfg.symbols)}")
            return 0
        if args.test_telegram:
            send_telegram(os.getenv("TELEGRAM_BOT_TOKEN", ""),
                          os.getenv("TELEGRAM_CHAT_ID", ""),
                          "✅ Orbit FUTURES DAY TRADE TEST: ช่องทางพร้อม (ไม่มีคำสั่งซื้อขาย)")
            return 0
        return run(dry_run=args.dry_run)
    except Exception as exc:
        print(f"Futures monitor failed: {type(exc).__name__}: {str(exc)[:120]}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
