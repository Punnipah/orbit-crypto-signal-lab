"""Independent historical collector; safe to run in GitHub Actions every 5m.

No Telegram, account/order APIs, trading signals or modification of SL/TP.
`--dry-run` works without GitHub credentials and never writes history.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import sys

from monitor_delivery import DeliveryError
from scalp_marketdata import MarketDataError, fetch_snapshot, get_exchange_catalog
from whale_footprint import analyze_footprint, fetch_large_prints
from whale_history import GitHubWhaleHistoryStore, make_row, merge_history


# Start with PEPE on each venue, plus BTC/DOGE Spot. Venue failures are logged
# and excluded, NEVER replaced with a price from another exchange.
TRACKED = {
    "BINANCE_TH_SPOT": ("PEPEUSDT", "BTCUSDT", "DOGEUSDT"),
    "BINANCE_GLOBAL_USDM": ("PEPEUSDT",),
    "BITGET_USDT_FUTURES": ("PEPEUSDT",),
}


def collect() -> list[dict]:
    rows = []
    for venue, symbols in TRACKED.items():
        try:
            catalog = get_exchange_catalog(venue)
        except MarketDataError as exc:
            print(f"{venue}: market unavailable ({str(exc)[:90]})", flush=True)
            continue
        for symbol in symbols:
            if symbol not in catalog:
                print(f"{venue}/{symbol}: not listed; no substitute", flush=True)
                continue
            try:
                snap = fetch_snapshot(venue, symbol, catalog=catalog,
                                      now=datetime.now(timezone.utc))
                try:
                    prints = fetch_large_prints(snap)
                    note = ""
                except (MarketDataError, ValueError, TypeError) as exc:
                    prints, note = None, f"recent public trades unavailable: {str(exc)[:70]}"
                evidence = analyze_footprint(snap, prints=prints, print_note=note)
                rows.append(make_row(evidence))
                print(f"{venue}/{symbol}: {evidence.classification} "
                      f"taker={evidence.taker_buy_share_5m} "
                      f"prints={'ok' if prints else 'unavailable'}", flush=True)
            except (MarketDataError, ValueError, TypeError, OverflowError, KeyError) as exc:
                print(f"{venue}/{symbol}: unavailable ({str(exc)[:100]})", flush=True)
    return rows


def run(record: bool) -> int:
    print("Orbit 5.8.5 Whale Footprint · public, anonymous, research only", flush=True)
    rows = collect()
    print(f"Coverage: {len(rows)}/{sum(map(len, TRACKED.values()))}", flush=True)
    if not record:
        print(f"DRY RUN · no GitHub write · {len(rows)} observations", flush=True)
        # A green dry-run with zero verified markets would be misleading.
        return 0 if rows else 2
    if not rows:
        print("No verified data: keeping history unchanged", file=sys.stderr)
        return 2
    store = GitHubWhaleHistoryStore(os.getenv("GITHUB_REPOSITORY", ""),
                                    os.getenv("GITHUB_TOKEN", ""),
                                    os.getenv("GITHUB_SHA", ""))
    now = datetime.now(timezone.utc)
    today = now.date()
    existing = store.load(today)
    # A delayed GitHub schedule can cross UTC midnight while gathering data.
    # Those previous-day observations are deliberately skipped, not mixed into
    # today's file or assigned a fabricated timestamp.
    rows = [r for r in rows if datetime.fromtimestamp(r["t"] / 1000,
             timezone.utc).date() == today]
    if not rows:
        print("Observation belongs to previous UTC day; retry next schedule", flush=True)
        return 0
    merged, count = merge_history(existing, rows, now)
    if count == 0:
        print("All 5m buckets already captured; no rewrite", flush=True)
        return 0
    changed = store.save(merged)
    print(f"Added {count} observations; retained {len(merged['rows'])}; persisted={changed}",
          flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v5.8.5 public whale footprint collector")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--record", action="store_true")
    args = parser.parse_args(argv)
    try:
        return run(args.record)
    except (MarketDataError, ValueError, DeliveryError) as exc:
        print(f"Whale collection stopped safely: {type(exc).__name__}: {str(exc)[:140]}",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
