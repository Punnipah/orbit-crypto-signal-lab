"""Historical proxy for the Futures technical setup, never a live edge claim.

Uses the same evaluate_futures rules, with each historical timeframe cut at its
own bar close. Historical mark/funding/order-book are not replayed and those
filters are explicitly excluded from interpretation of the results.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import math

import pandas as pd

from futures_daytrade import (_read_public, FuturesDataError, FuturesSettings,
                              evaluate_futures, parse_futures_klines,
                              TIMEFRAME_MINUTES)
from futures_paper import empty_paper, paper_stats, update_paper


@dataclass
class ProxyReport:
    symbol: str
    evaluated_bars: int
    all_stats: dict
    early_stats: dict
    later_stats: dict
    first_at: datetime
    last_at: datetime
    history: list[dict]
    limitations: str = ("TECHNICAL PROXY ONLY: Mark=Close, Funding=0 (not historical), "
                        "no historical order book or liquidation prices, simplified costs, "
                        "no proof of real execution or predictive performance")


def fetch_history(symbol: str, timeframe: str, *, days: int = 45,
                  now: datetime | None = None) -> pd.DataFrame:
    if not isinstance(days, int) or not 25 <= days <= 60:
        raise ValueError("Historical window must be 25–60 days")
    if timeframe not in TIMEFRAME_MINUTES or not isinstance(symbol, str) or not symbol.endswith("USDT"):
        raise ValueError("Futures pair/timeframe invalid")
    now = now or datetime.now(timezone.utc)
    start_ms = int((now - timedelta(days=days)).timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)
    rows = []
    cursor = start_ms
    period_ms = TIMEFRAME_MINUTES[timeframe] * 60000
    # At most 7 pages for 60 days of 15m bars; never unbounded API loops.
    for _ in range(8):
        batch = _read_public("/fapi/v1/klines", {"symbol": symbol, "interval": timeframe,
                                                 "startTime": cursor, "endTime": end_ms,
                                                 "limit": 1000})
        if not isinstance(batch, list):
            raise FuturesDataError("Historical klines malformed")
        if not batch:
            break
        if any(not isinstance(item, list) or not isinstance(item[0], int) for item in batch):
            raise FuturesDataError("Historical timestamp malformed")
        rows.extend(batch)
        next_cursor = batch[-1][0] + period_ms
        if next_cursor <= cursor:
            raise FuturesDataError("Historical pagination stalled")
        cursor = next_cursor
        if cursor >= end_ms or len(batch) < 1000:
            break
    if not rows or cursor < end_ms - period_ms * 2:
        raise FuturesDataError("Historical data incomplete or too many pages")
    frame = parse_futures_klines(rows, now=now, timeframe=timeframe)
    if (frame.index.to_series().diff().dropna() != pd.Timedelta(minutes=TIMEFRAME_MINUTES[timeframe])).any():
        raise FuturesDataError("Historical klines have gaps")
    return frame


def evaluate_historical_proxy(symbol: str, frames: dict[str, pd.DataFrame],
                              settings: FuturesSettings, *,
                              start: datetime | None = None) -> ProxyReport:
    if any(tf not in frames or len(frames[tf]) < 101 for tf in ("15m", "1h", "4h")):
        raise ValueError("Historical data missing")
    for tf, frame in frames.items():
        if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None or frame.index.has_duplicates:
            raise ValueError(f"{tf} time index invalid")
        if (frame.index.to_series().diff().dropna() != pd.Timedelta(minutes=TIMEFRAME_MINUTES[tf])).any():
            raise ValueError(f"{tf} contains gap")
    # The first usable 15m bar needs 100 already-closed 1h AND 4h bars.
    warmup = frames["4h"].index[99] + pd.Timedelta(hours=4)
    if start is not None:
        warmup = max(warmup, pd.Timestamp(start))
    stamps = frames["15m"].index
    end = stamps[-1] + pd.Timedelta(minutes=15)
    active_times = stamps[(stamps + pd.Timedelta(minutes=15)) >= warmup]
    if len(active_times) < 20:
        raise ValueError("Not enough aligned historical candles")
    paper = empty_paper()
    checked = 0
    settings = replace(settings, symbols=(symbol,))
    for opened in active_times:
        timestamp = (opened + pd.Timedelta(minutes=15)).to_pydatetime()
        f15 = frames["15m"].loc[frames["15m"].index <= opened].tail(250)
        f1h = frames["1h"].loc[frames["1h"].index + pd.Timedelta(hours=1) <= timestamp].tail(150)
        f4h = frames["4h"].loc[frames["4h"].index + pd.Timedelta(hours=4) <= timestamp].tail(150)
        if min(len(f15), len(f1h), len(f4h)) < 100:
            continue
        # Historical mark/funding unavailable in this research proxy; never
        # report this as a faithful full Futures replay.
        last = float(f15["close"].iloc[-1])
        ob = evaluate_futures(symbol, {"15m": f15, "1h": f1h, "4h": f4h},
                              last=last, mark=last, funding_pct=0.0,
                              now=timestamp, settings=settings)
        update_paper(paper, [ob], {symbol: f15}, timestamp,
                     round_trip_cost_pct=settings.round_trip_cost_pct)
        checked += 1
    cut = active_times[len(active_times) // 2] + pd.Timedelta(minutes=15)
    history = paper["history"]
    # Split on the entry-alert time; chronology is preserved, no fitting to
    # the later portion is performed. This is a holdout, not walk-forward optimization.
    early = [item for item in history if pd.Timestamp(item["created_at"]) < cut]
    later = [item for item in history if pd.Timestamp(item["created_at"]) >= cut]
    return ProxyReport(symbol, checked, paper_stats(history), paper_stats(early),
                       paper_stats(later), active_times[0].to_pydatetime(),
                       end.to_pydatetime(), history)
