"""Orbit v5.9 independent public signal journal, no orders, no Telegram.

Records real 1m CLOSED candles and scanner outputs for later conservative
paper replay; it does not record real fills or create actual orders.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from monitor_delivery import DeliveryError
from scalp_engine import ScalpObservation, read_scalp_settings, evaluate_scalp
from scalp_fixed_tp import pepe_daily_ten_preview
from scalp_marketdata import MarketDataError, fetch_snapshot, get_exchange_catalog
from scalp_runner import VENUES
from validation_history import GitHubValidationStore, merge_history
from near_ready_tracker import near_candidates
from near_ready_history import GitHubNearReadyStore, merge as merge_near


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "scalp_config.json"


def observation_row(ob: ScalpObservation, snapshot=None, settings=None) -> dict:
    now = ob.checked_at
    if now.tzinfo is None:
        raise ValueError("scan time must be UTC-aware")
    stamp = int(now.timestamp() * 1000)
    bars = []
    price = None
    spread = None
    fee = None
    slip = None
    daily_tp = None
    daily_state = "NOT_APPLICABLE"
    if snapshot is not None:
        price = (snapshot.bid + snapshot.ask) / 2
        spread = float(snapshot.spread_bps)
        for _, candle in snapshot.frames["1m"].tail(7).iterrows():
            bars.append([int(candle.open_ms), float(candle.open), float(candle.high),
                         float(candle.low), float(candle.close)])
        if settings is not None:
            fee = (settings.spot_fee_each_side_pct if snapshot.venue == "BINANCE_TH_SPOT"
                   else max(settings.futures_fee_each_side_pct,
                            snapshot.instrument.taker_fee_pct or 0.0))
            slip = settings.slippage_each_side_pct
        if ob.state == "READY" and ob.symbol == "PEPEUSDT" and ob.side in ("LONG", "SHORT"):
            try:
                preview = pepe_daily_ten_preview(snapshot, settings, ob.side,
                                                 entry=ob.entry, stop=ob.stop,
                                                 qty=ob.qty, signal_ready=True)
                daily_state = preview.state
                if preview.state == "ALTERNATIVE_READY":
                    daily_tp = preview.target
            except (ValueError, TypeError, OverflowError):
                # Optional ten-point preview cannot erase a verified v5.8.4
                # primary signal from its independent research journal.
                daily_state = "PREVIEW_UNAVAILABLE"
    return {
        "t": stamp, "v": ob.venue, "s": ob.symbol, "st": ob.state,
        "sd": ob.side, "id": ob.setup_id[:64], "why": ob.reason[:180],
        "p": price, "e": ob.entry, "sl": ob.stop, "tp1": ob.tp1,
        "tp2": ob.tp2, "tp10": daily_tp, "tp10_state": daily_state,
        "qty": ob.qty, "risk": ob.risk_usdt, "fee": fee, "slip": slip,
        "spread": spread, "regime": ob.market_regime[:50],
        "strategy": ob.strategy[:50], "bars": bars,
    }


def scan(*, near_sink: list[dict] | None = None) -> list[dict]:
    settings = read_scalp_settings(CONFIG)
    rows = []
    for venue, key in VENUES:
        symbols = getattr(settings, key)
        try:
            catalog = get_exchange_catalog(venue)
        except MarketDataError as exc:
            print(f"{venue}: API unavailable · {str(exc)[:85]}", flush=True)
            for sym in symbols:
                ob = ScalpObservation(venue, sym, "DATA_UNAVAILABLE", str(exc)[:180],
                                      datetime.now(timezone.utc))
                rows.append(observation_row(ob))
            continue
        for sym in symbols:
            try:
                snapshot = fetch_snapshot(venue, sym, catalog=catalog,
                                          now=datetime.now(timezone.utc))
                ob = evaluate_scalp(snapshot, settings, now=datetime.now(timezone.utc))
                row = observation_row(ob, snapshot, settings)
                if near_sink is not None:
                    try:
                        near_sink.extend(near_candidates(snapshot, settings, ob))
                    except (ValueError, TypeError, KeyError, OverflowError, IndexError):
                        # New optional diagnostics cannot suppress original
                        # READY/WAIT observations or bypass any risk gate.
                        print(f"{venue}/{sym}: optional near-ready evidence unavailable", flush=True)
            except (MarketDataError, ValueError, TypeError, KeyError, OverflowError) as exc:
                ob = ScalpObservation(venue, sym, "DATA_UNAVAILABLE",
                                      f"{type(exc).__name__}: {str(exc)[:120]}",
                                      datetime.now(timezone.utc))
                row = observation_row(ob)
            rows.append(row)
            print(f"{venue}/{sym}: {row['st']} · {row['sd']} · {row['why'][:70]}", flush=True)
    return rows


def run(*, record: bool) -> int:
    print("Orbit v5.9.1 Professional Validation + Near Ready · PAPER ONLY", flush=True)
    near: list[dict] = []
    rows = scan(near_sink=near)
    available = sum(r["st"] != "DATA_UNAVAILABLE" for r in rows)
    print(f"Verified coverage: {available}/{len(rows)} · READY: "
          f"{sum(r['st'] == 'READY' for r in rows)} · NEAR READY (research): {len(near)}", flush=True)
    if not record:
        print("DRY RUN · no write, no alerts, no exchange orders", flush=True)
        return 0 if available else 2
    if not rows:
        return 2
    now = datetime.now(timezone.utc)
    day = now.date()
    # Midnight-safe: actual observation time remains unchanged and older-day
    # scans never get assigned to today's file.
    rows = [r for r in rows if datetime.fromtimestamp(r["t"] / 1000,
             timezone.utc).date() == day]
    if not rows:
        print("All observations crossed UTC midnight; retry next scan")
        return 0
    store = GitHubValidationStore(os.getenv("GITHUB_REPOSITORY", ""),
                                  os.getenv("GITHUB_TOKEN", ""),
                                  os.getenv("GITHUB_SHA", ""))
    before = store.load(day)
    updated, count = merge_history(before, rows, now)
    if count:
        store.save(updated)
    print(f"Recorded {count} unique observations / UTC day; "
          f"missing data stays missing; PAPER ONLY", flush=True)
    # Independent secondary file on the same validation-history branch.
    # Failure does not alter existing original validation records/READY.
    daily_near = [r for r in near if datetime.fromtimestamp(r["t"] / 1000,
                  timezone.utc).date() == day]
    if daily_near:
        try:
            near_store = GitHubNearReadyStore(os.getenv("GITHUB_REPOSITORY", ""),
                                              os.getenv("GITHUB_TOKEN", ""),
                                              os.getenv("GITHUB_SHA", ""))
            previous = near_store.load(day)
            near_state, near_count = merge_near(previous, daily_near, now)
            if near_count:
                near_store.save(near_state)
            print(f"Recorded {near_count} NEAR READY observations; watch only", flush=True)
        except (DeliveryError, ValueError, RuntimeError) as exc:
            print(f"Optional NEAR READY journal failed: {type(exc).__name__}: "
                  f"{str(exc)[:130]}", file=sys.stderr, flush=True)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Orbit v5.9 real signal evidence journal")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--dry-run", action="store_true")
    choice.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)
    try:
        return run(record=args.record)
    except (MarketDataError, ValueError, DeliveryError, RuntimeError) as exc:
        print(f"Validation stopped safely: {type(exc).__name__}: {str(exc)[:160]}",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
