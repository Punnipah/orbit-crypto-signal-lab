"""GitHub Actions v5.8 AUTO REGIME 5m cadence. Public data, no orders.

Usage:
  python -m scalp_runner --validate-config
  python -m scalp_runner --probe
  python -m scalp_runner --dry-run
  python -m scalp_runner --test-telegram
  python -m scalp_runner
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from monitor_delivery import DeliveryError, send_telegram
from scalp_alerts import ScalpStateStore, empty_state, send_pending, transition
from scalp_engine import ScalpObservation, ScalpSettings, evaluate_scalp, read_scalp_settings, unavailable
from scalp_marketdata import MarketDataError, fetch_snapshot, get_exchange_catalog


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "scalp_config.json"
VENUES = (("BINANCE_TH_SPOT", "spot_symbols"),
          ("BINANCE_GLOBAL_USDM", "futures_symbols"),
          ("BITGET_USDT_FUTURES", "bitget_futures_symbols"))


def scan(settings: ScalpSettings, *, now: datetime | None = None) -> list[ScalpObservation]:
    now = now or datetime.now(timezone.utc)
    observations = []
    for venue, field in VENUES:
        symbols: tuple[str, ...] = getattr(settings, field)
        try:
            catalog = get_exchange_catalog(venue)
        except MarketDataError as exc:
            # Blocked venues stay unavailable. We never invent Futures READY
            # by reusing Binance TH Spot or Kraken prices.
            print(f"{venue} unavailable: {str(exc)[:90]}", flush=True)
            observations.extend(unavailable(venue, sym, str(exc), now) for sym in symbols)
            continue
        for sym in symbols:
            try:
                snapshot = fetch_snapshot(venue, sym, catalog=catalog, now=datetime.now(timezone.utc))
                ob = evaluate_scalp(snapshot, settings, now=datetime.now(timezone.utc))
            except (MarketDataError, ValueError, TypeError, KeyError, OverflowError) as exc:
                ob = unavailable(venue, sym, f"{type(exc).__name__}: {str(exc)[:130]}", now)
            observations.append(ob)
            print(f"{venue} {sym}: {ob.state} {ob.side} | {ob.reason[:110]}", flush=True)
    return observations


def run(*, dry_run: bool = False) -> int:
    settings = read_scalp_settings(CONFIG)
    print("Orbit Scalp v5.8: AUTO REGIME Trend/Range; public read-only PAPER ONLY; no exchange orders", flush=True)
    if dry_run:
        state, store = empty_state(), None
    else:
        token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID secrets missing")
        store = ScalpStateStore(os.getenv("GITHUB_REPOSITORY", ""),
                                os.getenv("GITHUB_TOKEN", ""), os.getenv("GITHUB_SHA", ""))
        state = store.load()
    now = datetime.now(timezone.utc)
    obs = scan(settings, now=now)
    changes = transition(state, obs, settings, now=datetime.now(timezone.utc))
    print(f"Scalp events: {changes or 'no state change'} | queued={len(state['pending'])}", flush=True)
    print(f"Data coverage: {sum(v.state != 'DATA_UNAVAILABLE' for v in obs)}/{len(obs)}", flush=True)
    if dry_run:
        for event in state["pending"]:
            print(f"DRY RUN: {event['text'][:160].replace(chr(10),' | ')}", flush=True)
        return 0
    assert store is not None
    sent, dropped = send_pending(state, store, token, chat_id)
    print(f"Telegram sent={sent}; stale alerts discarded={dropped}; zero exchange orders", flush=True)
    return 0


def probe() -> int:
    """Public API source + symbol filter diagnostics; no secrets, no Telegram."""
    settings = read_scalp_settings(CONFIG)
    obs = scan(settings)
    n_spot = sum(v.venue == "BINANCE_TH_SPOT" and v.state != "DATA_UNAVAILABLE" for v in obs)
    n_futures = sum(v.venue == "BINANCE_GLOBAL_USDM" and v.state != "DATA_UNAVAILABLE" for v in obs)
    n_bitget = sum(v.venue == "BITGET_USDT_FUTURES" and v.state != "DATA_UNAVAILABLE" for v in obs)
    print(f"PROBE coverage Spot Binance TH={n_spot}/{len(settings.spot_symbols)}; "
          f"Futures Binance Global={n_futures}/{len(settings.futures_symbols)}; "
          f"Futures Bitget={n_bitget}/{len(settings.bitget_futures_symbols)}", flush=True)
    if n_spot == 0:
        print("No Binance TH Spot coverage: STOP, check region/network/endpoint", flush=True)
        return 2
    if n_futures == 0:
        print("Futures Global unavailable (e.g. HTTP 451): Futures READY disabled; no fallback", flush=True)
    if settings.bitget_futures_symbols and n_bitget == 0:
        print("Bitget Futures unavailable: independent Futures signals disabled", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Orbit Scalp v5.8 · read-only")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--validate-config", action="store_true")
    mode.add_argument("--probe", action="store_true")
    mode.add_argument("--research", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--test-telegram", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.validate_config:
            settings = read_scalp_settings(CONFIG)
            print(f"Valid Scalp v5.8 PAPER ONLY: Spot={settings.spot_symbols} "
                  f"Futures={settings.futures_symbols} Bitget={settings.bitget_futures_symbols} "
                  f"capital={settings.capital_usdt} USDT")
            return 0
        if args.probe:
            return probe()
        if args.research:
            from scalp_research import research_spot
            settings = read_scalp_settings(CONFIG)
            print("Historical descriptive ATR study only; NOT a backtest or win-rate")
            for sym, result in research_spot(settings.spot_symbols).items():
                print(f"{sym}: {result}", flush=True)
            return 0
        if args.test_telegram:
            send_telegram(os.getenv("TELEGRAM_BOT_TOKEN", ""),
                          os.getenv("TELEGRAM_CHAT_ID", ""),
                          "🧪 Orbit Scalp Signal v5.8 · Telegram TEST ONLY\n"
                          "Spot Binance TH / Futures Binance Global / Bitget Futures\n"
                          "PAPER ONLY · ไม่ใช่ BUY/LONG/SHORT และไม่ส่งคำสั่งซื้อขาย")
            print("Safe Telegram test sent")
            return 0
        return run(dry_run=args.dry_run)
    except (ValueError, MarketDataError, DeliveryError, RuntimeError) as exc:
        print(f"Scalp runner stopped safely: {type(exc).__name__}: {str(exc)[:180]}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
