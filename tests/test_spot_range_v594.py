"""Synthetic, offline checks for v5.9.4 independent Binance TH Spot range."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import math
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scalp_engine import ScalpSettings
from scalp_marketdata import Instrument, MarketSnapshot
from spot_range_bounce import evaluate_spot_range


NOW = datetime(2026, 11, 1, 12, 17, 20, tzinfo=timezone.utc)
CFG = ScalpSettings(("PEPEUSDT",), ("PEPEUSDT",))
INST = Instrument("PEPEUSDT", Decimal("0.001"), Decimal("0.001"),
                  Decimal("5"), Decimal("0.01"))


def snapshot(*, flow=True, five_green=True) -> MarketSnapshot:
    frames = {}
    for minutes, count, end in ((60, 100, "11:00"), (15, 100, "12:00"),
                                (5, 100, "12:10"), (1, 100, "12:16")):
        ts = pd.date_range(end=f"2026-11-01 {end}:00+00:00", periods=count,
                           freq=f"{minutes}min")
        rows = []
        for j, t in enumerate(ts):
            c = 101 + math.sin(j * .48) * 1.7
            rows.append(dict(open_ms=int(t.timestamp() * 1000), open=c-.03,
                             high=c+.16, low=c-.16, close=c,
                             volume=100., taker_buy=55.))
        frames[f"{minutes}m" if minutes != 60 else "1h"] = pd.DataFrame(rows, index=ts)
    hour = frames["1h"]
    # Previous twelve 1h candles establish ~99.0–103.0.
    for j in range(len(hour)-13, len(hour)-1):
        c = 101 + math.sin(j * 1.3) * 1.7
        hour.loc[hour.index[j], ["open", "high", "low", "close"]] = [c-.03, c+.22, c-.22, c]
    hour.loc[hour.index[-1], ["open", "high", "low", "close"]] = [99.5, 99.8, 99.3, 99.5]
    fifteen = frames["15m"]
    fifteen.loc[fifteen.index[-2:], ["open", "high", "low", "close"]] = [
        [99.6, 99.8, 99.2, 99.5], [99.5, 99.7, 99.1, 99.4]]
    five = frames["5m"]
    five.loc[five.index[-2], ["open", "high", "low", "close"]] = [99.5, 99.6, 99.2, 99.3]
    five.loc[five.index[-1], ["open", "high", "low", "close", "volume", "taker_buy"]] = [
        99.22, 99.6, 98.95, 99.52 if five_green else 99.20, 200, 130]
    one = frames["1m"]
    one.loc[one.index[-1], ["open", "high", "low", "close", "volume", "taker_buy"]] = [
        99.45, 99.60, 99.42, 99.55, 200, 140 if flow else 80]
    return MarketSnapshot("BINANCE_TH_SPOT", "PEPEUSDT", frames, 99.54, 99.56,
                          100000, 100000, INST, NOW)


class SpotRangeV594Tests(unittest.TestCase):
    def test_confirmed_bounce_is_ready_with_stop_and_net_rr(self):
        result = evaluate_spot_range(snapshot(), CFG)
        self.assertEqual(result.state, "RANGE_READY", result.reason)
        self.assertLess(result.stop, result.entry)
        self.assertLess(result.entry, result.tp1)
        self.assertLess(result.tp1, result.tp2)
        self.assertGreaterEqual(result.net_rr, CFG.min_net_rr)
        self.assertLessEqual(result.risk_usdt, CFG.capital_usdt*CFG.risk_per_trade_pct/100)

    def test_separate_spot_venue_only(self):
        with self.assertRaises(ValueError):
            evaluate_spot_range(replace(snapshot(), venue="BINANCE_GLOBAL_USDM"), CFG)

    def test_not_ready_without_one_minute_buy_flow(self):
        result = evaluate_spot_range(snapshot(flow=False), CFG)
        self.assertNotEqual(result.state, "RANGE_READY", result.reason)

    def test_not_ready_without_rejection(self):
        result = evaluate_spot_range(snapshot(five_green=False), CFG)
        self.assertNotEqual(result.state, "RANGE_READY", result.reason)

    def test_broken_support_never_ready(self):
        result = evaluate_spot_range(replace(snapshot(), bid=95, ask=95.01), CFG)
        self.assertEqual(result.state, "RANGE_BROKEN", result.reason)

    def test_stale_snapshot_unavailable(self):
        result = evaluate_spot_range(snapshot(), CFG, now=NOW+timedelta(minutes=2))
        self.assertEqual(result.state, "DATA_UNAVAILABLE")

    def test_missing_hour_unavailable(self):
        snap = snapshot()
        snap = replace(snap, frames={k: v for k, v in snap.frames.items() if k != "1h"})
        self.assertEqual(evaluate_spot_range(snap, CFG).state, "DATA_UNAVAILABLE")

    def test_settings_not_mutated(self):
        before = repr(CFG)
        evaluate_spot_range(snapshot(), CFG)
        self.assertEqual(repr(CFG), before)


if __name__ == "__main__":
    unittest.main()
