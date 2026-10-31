"""Research-only PEPE/USDT Binance TH replay. Not a trading signal or live order.

Historic order book, spread, latency and maker/taker fees are unavailable;
the replay uses a stated synthetic one-tick spread and conservative cost model.
Never optimize thresholds on the same sample used to claim accuracy.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scalp_engine import _adx, _ema, _setup_5m, _atr, read_scalp_settings


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tests" / "pepe_binanceth_30d_data"
END = int(datetime(2026, 10, 31, 9, 0, tzinfo=timezone.utc).timestamp() * 1000)
START = END - 30 * 24 * 60 * 60 * 1000
INTERVAL = {"1m": 60_000, "5m": 300_000, "15m": 900_000}
TICK = 0.00000001


def fetch(interval: str) -> pd.DataFrame:
    cache = DATA / f"PEPEUSDT_{interval}.csv"
    if cache.exists():
        return pd.read_csv(cache)
    rows: list[list] = []
    cursor = START - 36 * 60 * 60 * 1000
    while cursor < END:
        params = urlencode({"symbol": "PEPEUSDT", "interval": interval,
                            "startTime": cursor,
                            "endTime": min(END - 1, cursor + 999 * INTERVAL[interval],
                                           cursor + 5 * 24 * 60 * 60 * 1000),
                            "limit": 1000})
        url = "https://api.binance.th/api/v1/klines?" + params
        with urlopen(Request(url, headers={"User-Agent": "OrbitResearch/1.0"}), timeout=25) as response:
            batch = json.load(response)
        if not isinstance(batch, list) or not batch:
            raise RuntimeError(f"Missing candle history at {cursor} for {interval}")
        rows.extend(batch)
        newest = int(batch[-1][0])
        if newest < cursor:
            raise RuntimeError("Non-monotonic Binance TH history")
        cursor = newest + INTERVAL[interval]
    frame = pd.DataFrame(rows, columns=["open_ms", "open", "high", "low", "close", "volume",
                                         "close_ms", "quote_volume", "trades", "taker_buy", "taker_quote", "unused"])
    frame = frame[["open_ms", "open", "high", "low", "close", "volume", "taker_buy"]]
    for col in frame.columns:
        frame[col] = pd.to_numeric(frame[col])
    frame = frame.drop_duplicates("open_ms").sort_values("open_ms")
    if (frame.open_ms.diff().dropna() != INTERVAL[interval]).any():
        raise RuntimeError(f"Missing/corrupt candles in {interval}")
    DATA.mkdir(parents=True, exist_ok=True)
    frame.to_csv(cache, index=False)
    return frame


@dataclass
class Event:
    timestamp: int
    kind: str
    price: float
    stop: float
    target: float
    outcome: str = ""
    pnl_pct: float = math.nan


def evaluate():
    one, five, fifteen = (fetch(tf) for tf in ("1m", "5m", "15m"))
    settings = read_scalp_settings(ROOT / "scalp_config.json")
    one = one.set_index("open_ms", drop=False)
    five = five.set_index("open_ms", drop=False)
    fifteen = fifteen.set_index("open_ms", drop=False)
    five_open = five.open_ms.to_numpy()
    one_open = one.open_ms.to_numpy()
    fifteen_open = fifteen.open_ms.to_numpy()
    events: list[Event] = []
    observations = {"EARLY_WATCH": 0, "EARLY_CONFIRMED": 0, "BREAKOUT_5M_LONG": 0}
    # Evaluate at 5m boundaries, using only 1m/5m/15m bars closed as of that instant.
    next_allowed = {"EARLY_WATCH": 0, "EARLY_CONFIRMED": 0, "BREAKOUT_5M_LONG": 0}
    for close_ms in five_open[(five_open >= START) & (five_open < END)] + 300_000:
        idx5 = int(np.searchsorted(five_open, close_ms - 300_000, side="right"))
        idx1 = int(np.searchsorted(one_open, close_ms - 60_000, side="right"))
        idx15 = int(np.searchsorted(fifteen_open, close_ms - 900_000, side="right"))
        if min(idx5, idx1, idx15) < 70:
            continue
        # Slices end precisely on completed candle; present/future candles excluded.
        f = five.iloc[idx5 - 100:idx5]
        o = one.iloc[idx1 - 100:idx1]
        h = fifteen.iloc[idx15 - 100:idx15]
        if len(f) < 70 or len(o) < 70 or len(h) < 70:
            continue
        now = datetime.fromtimestamp(close_ms / 1000, timezone.utc)
        ema9, ema21 = _ema(h.close, 9), _ema(h.close, 21)
        down = (h.close.iloc[-1] < ema21.iloc[-1] and ema9.iloc[-1] < ema21.iloc[-1])
        up = (h.close.iloc[-1] > ema21.iloc[-1] and ema9.iloc[-1] > ema21.iloc[-1]
              and ema21.iloc[-1] > ema21.iloc[-4])
        bottom, top = float(f.low.iloc[-31:-1].min()), float(f.high.iloc[-31:-1].max())
        width = top - bottom
        latest = o.iloc[-1]
        close = float(latest.close)
        share = float(latest.taker_buy / latest.volume) if latest.volume > 0 else 0
        early = bool(down and width > 0 and _adx(f) <= 27 and
                     bottom - width * .10 <= close <= bottom + width * .30 and
                     share >= .53 and close >= float(o.close.iloc[-2]))
        prior_volume = float(o.volume.iloc[-21:-1].mean())
        confirmed = bool(early and close > float(latest.open) and
                         prior_volume > 0 and float(latest.volume) >= prior_volume * 1.20)
        breakout = bool(up and float(f.close.iloc[-1]) >= float(_ema(f.close, 21).iloc[-1])
                        and _setup_5m(f, "LONG", settings, now) is not None)
        if early:
            observations["EARLY_WATCH"] += 1
        if confirmed:
            observations["EARLY_CONFIRMED"] += 1
        if breakout:
            observations["BREAKOUT_5M_LONG"] += 1
        for kind, matches in (("EARLY_WATCH", early), ("EARLY_CONFIRMED", confirmed),
                              ("BREAKOUT_5M_LONG", breakout)):
            if not matches or close_ms < next_allowed[kind]:
                continue
            # Next minute open approximates an actionable entry, with one-tick ask.
            next_idx = int(np.searchsorted(one_open, close_ms, side="left"))
            if next_idx >= len(one):
                continue
            entry = float(one.iloc[next_idx].open) + TICK
            # Uniform stop/target for fair comparison of signal timing; NOT live Orbit SL/TP.
            stop, target = entry * .99, entry * 1.02
            events.append(Event(int(close_ms), kind, entry, stop, target))
            next_allowed[kind] = close_ms + 60 * 60_000  # No overlapping 60m paper positions.
    # Forward evaluation: 60m, conservative stop-first if both hit in one candle.
    for event in events:
        future = one.loc[(one.open_ms >= event.timestamp) &
                         (one.open_ms < event.timestamp + 60 * 60_000)]
        if len(future) < 60:
            event.outcome = "INCOMPLETE"
            continue
        exit_price = float(future.close.iloc[-1]) - TICK
        event.outcome = "TIME"
        for r in future.itertuples():
            if r.low <= event.stop:
                event.outcome = "STOP"
                exit_price = event.stop - TICK
                break
            if r.high >= event.target:
                event.outcome = "TARGET"
                exit_price = event.target - TICK
                break
        event.pnl_pct = (exit_price / event.price - 1) * 100 - 0.30  # 0.1% fee x2 + slippage 0.05% x2.
    print("PEPE Binance TH; 30-day retrospective; 5m scan, completed candles only")
    print("Method: next-minute-open +1 tick; exit -1 tick; 0.30% fee/slippage; stop 1%; TP 2%; hold <=60m")
    print("NO historical order book; not comparable to actual fills, not a production backtest")
    print("Raw observations:", observations)
    midpoint = START + (END - START) // 2
    for kind in ("EARLY_WATCH", "EARLY_CONFIRMED", "BREAKOUT_5M_LONG"):
        scored = [e for e in events if e.kind == kind and math.isfinite(e.pnl_pct)]
        if not scored:
            print(kind, "no resolved opportunities")
            continue
        wins = sum(e.pnl_pct > 0 for e in scored)
        gains = sum(max(0, e.pnl_pct) for e in scored)
        losses = -sum(min(0, e.pnl_pct) for e in scored)
        print(kind, "n", len(scored), "win_rate", round(wins / len(scored) * 100, 1),
              "mean_net_pct", round(float(np.mean([e.pnl_pct for e in scored])), 3),
              "profit_factor", round(gains / losses, 3) if losses else "undefined",
              "TARGET", sum(e.outcome == "TARGET" for e in scored),
              "STOP", sum(e.outcome == "STOP" for e in scored),
              "TIME", sum(e.outcome == "TIME" for e in scored))
        for label, group in (("first_half", [e for e in scored if e.timestamp < midpoint]),
                             ("second_half", [e for e in scored if e.timestamp >= midpoint])):
            if group:
                print(" ",label,"n",len(group),"win_rate",round(100*sum(e.pnl_pct>0 for e in group)/len(group),1),
                      "mean_net_pct",round(float(np.mean([e.pnl_pct for e in group])),3))
    reference_ms = int(datetime(2026, 10, 31, 4, 40, tzinfo=timezone.utc).timestamp() * 1000)
    near = [e for e in events if abs(e.timestamp - reference_ms) <= 30 * 60_000]
    print("Events near reference trade (11:40 Thailand):",
          [(e.kind, datetime.fromtimestamp(e.timestamp/1000,timezone.utc).isoformat(),e.outcome) for e in near])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluate", action="store_true")
    args = parser.parse_args()
    if args.evaluate:
        evaluate()
    else:
        for tf in INTERVAL:
            print(tf, len(fetch(tf)))
