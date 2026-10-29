"""GitHub Actions entry point: read-only 15-minute Orbit Telegram monitor.

Usage:
    python -m alert_monitor --validate-config
    python -m alert_monitor --dry-run       # reads live public market APIs, no writes
    python -m alert_monitor --test-telegram # sends exactly one test message
    python -m alert_monitor               # GitHub schedule, persists dedupe state

Credentials must be injected through GitHub Actions secrets. Never require a
Binance account key, Binance order permission, or CoinGlass subscription.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from binance_data import fetch_catalog, fetch_klines
from monitor_alerts import remove_sent, transition
from monitor_delivery import GitHubStateStore, send_telegram
from monitor_engine import (analyze_symbol, parse_watch_links, read_manual_coinglass,
                            read_settings, unavailable)


ROOT = Path(__file__).resolve().parent


def _log(message: str) -> None:
    print(message, flush=True)


def _load_inputs():
    settings = read_settings(ROOT / "monitor_config.json")
    watches = parse_watch_links(os.environ.get("ORBIT_WATCH_LINKS", ""), settings.symbols)
    coinglass = read_manual_coinglass(ROOT / "monitor_coinglass_manual.json")
    return settings, watches, coinglass


def scan_all(settings, watches, coinglass, *, now: datetime) -> list:
    """A failure in one coin must not suppress other coins or fabricate READY."""
    try:
        active = {item["symbol"] for item in fetch_catalog()
                  if item["quote"] == "USDT"}
    except (Exception,) as exc:
        _log(f"Spot catalog unavailable: {type(exc).__name__}")
        return [unavailable(symbol, now, "รายการคู่ Spot USDT ไม่พร้อม",
                            watch_token=watches[symbol][0] if symbol in watches else None)
                for symbol in settings.symbols]

    try:
        btc_bars = (fetch_klines("BTCUSDT", "4h", settings.history_candles),
                    fetch_klines("BTCUSDT", "1d", settings.history_candles))
    except (Exception,) as exc:
        _log(f"BTC regime source unavailable: {type(exc).__name__}")
        btc_bars = None

    observations = []
    for symbol in settings.symbols:
        watch = watches.get(symbol)
        if symbol not in active:
            observations.append(unavailable(symbol, now, "คู่ Spot/USDT นี้ไม่ได้อยู่ใน Catalog ที่ซื้อขายได้",
                                            watch_token=watch[0] if watch else None))
            continue
        try:
            observation = analyze_symbol(symbol, settings, now=now, watch=watch,
                                         manual_cg=coinglass.get(symbol[:-4]),
                                         btc_bars=btc_bars)
        except Exception as exc:
            # Fail closed: app/market input bugs must never turn into READY.
            _log(f"{symbol} analyze failed: {type(exc).__name__}")
            observation = unavailable(symbol, now, f"ข้อมูลสำคัญหรือการคำนวณไม่พร้อม ({type(exc).__name__})",
                                      watch_token=watch[0] if watch else None)
        observations.append(observation)
        _log(f"{symbol} | mode={observation.mode} | status={observation.status} "
             f"| futures={'OK' if observation.futures_source != 'MISSING' else 'MISSING'} "
             f"| CoinGlass={observation.coinglass_status}")
    return observations


def run_monitor(*, dry_run: bool = False) -> int:
    settings, watches, coinglass = _load_inputs()
    _log(f"Orbit v4.1 scanning {', '.join(settings.symbols)} | "
         f"Frozen links {len(watches)}/{len(settings.symbols)} | CoinGlass manual {len(coinglass)}")
    if not dry_run:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            raise ValueError("ต้องตั้ง TELEGRAM_BOT_TOKEN และ TELEGRAM_CHAT_ID เป็น GitHub Secrets")
        store = GitHubStateStore(os.environ.get("GITHUB_REPOSITORY", ""),
                                 os.environ.get("GITHUB_TOKEN", ""),
                                 os.environ.get("GITHUB_SHA", ""))
        state = store.load()
    else:
        from monitor_alerts import empty_state
        state = empty_state()
    observations = scan_all(settings, watches, coinglass, now=datetime.now(timezone.utc))
    transition(state, observations)
    if dry_run:
        _log(f"DRY RUN: {len(state['pending'])} important changes (no Telegram/GitHub writes)")
        for row in state["pending"]:
            _log(f"Would notify: {row['text'].splitlines()[1]}")
        return 0
    store.save(state)  # Outbox persisted BEFORE send; avoids lost unsent alerts.
    for pending in list(state["pending"]):
        send_telegram(token, chat_id, pending["text"])
        remove_sent(state, pending["id"])
        store.save(state)  # One ack per successful send; retries after failure.
    _log("Completed. Telegram delivered/queued, no exchange orders sent.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Orbit v4.1 read-only Telegram monitor")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--test-telegram", action="store_true")
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--validate-config", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.test_telegram:
            send_telegram(os.environ.get("TELEGRAM_BOT_TOKEN", ""),
                          os.environ.get("TELEGRAM_CHAT_ID", ""),
                          "✅ Orbit v4.1 Telegram Test สำเร็จ\n"
                          "ข้อความนี้ใช้ตรวจช่องทางแจ้งเตือนเท่านั้น ไม่ใช่สัญญาณซื้อ")
            _log("Telegram test delivered.")
            return 0
        if args.validate_config:
            settings, watches, cg = _load_inputs()
            _log(f"Configuration OK: {len(settings.symbols)} symbols, "
                 f"{len(watches)} frozen links, {len(cg)} manual CoinGlass rows")
            return 0
        return run_monitor(dry_run=args.dry_run)
    except Exception as exc:
        # Never print credentials or a full watch URL into public workflow logs.
        _log(f"MONITOR ERROR: {type(exc).__name__}: {str(exc)[:220]}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
