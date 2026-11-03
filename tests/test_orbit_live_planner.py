"""No-network contract checks for the live conditional planner."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orbit_live_planner import build_live_plan, _completed_bars
from orbit_model_lab_engine import DataUnavailable, validate_candles


def candles(n: int = 2300, trend: float = .00011) -> pd.DataFrame:
    start = 1_780_000_000_000 // 300_000 * 300_000
    t = np.arange(n, dtype=float)
    c = 100 * np.exp(t * trend + .006 * np.sin(t / 16))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open_ms": start + np.arange(n) * 300_000,
                         "open": o, "high": np.maximum(o, c) * 1.001,
                         "low": np.minimum(o, c) * .999,
                         "close": c, "volume": 4000 + 800 * (1 + np.cos(t / 11))})


class LivePlannerTests(unittest.TestCase):
    def test_live_plan_returns_same_venue_and_zones(self):
        frame = validate_candles(candles())
        plan = build_live_plan(frame, "BINANCE_GLOBAL_USDM")
        self.assertEqual(len(plan.entry_zones), 3)
        self.assertGreater(plan.reference_close, 0)
        self.assertEqual(len(plan.checks), 5)
        self.assertIn(plan.direction, {"LONG", "SHORT", "NONE"})
        self.assertTrue(plan.status.startswith(("SIGNAL", "WATCH", "NO TRADE")))
        self.assertTrue(all(lo <= hi for _, lo, hi, _ in plan.entry_zones))
        if plan.entry_reference is not None and plan.take_profit_2 is not None:
            self.assertGreater(plan.max_notional_usdt, 0)
            self.assertLessEqual(plan.max_notional_usdt, 75)
            if plan.direction == "LONG":
                self.assertLess(plan.stop, plan.entry_reference)
                self.assertGreater(plan.take_profit_2, plan.entry_reference)
            else:
                self.assertGreater(plan.stop, plan.entry_reference)
                self.assertLess(plan.take_profit_2, plan.entry_reference)

    def test_spot_does_not_return_short_or_long(self):
        frame = validate_candles(candles(trend=-.0002))
        plan = build_live_plan(frame, "BINANCE_TH_SPOT")
        self.assertNotEqual(plan.direction, "SHORT")
        self.assertNotEqual(plan.direction, "LONG")
        self.assertNotIn("SHORT", plan.status)

    def test_completed_higher_timeframe_omits_partial_periods(self):
        frame = validate_candles(candles(2301))
        h1 = _completed_bars(frame, 60)
        counts = frame.close.resample("60min", label="left", closed="left").count()
        self.assertTrue((counts.loc[h1.index] == 12).all())
        self.assertLessEqual(len(h1), 2301 // 12)

    def test_venues_and_risk_bounds(self):
        frame = validate_candles(candles())
        with self.assertRaises(DataUnavailable):
            build_live_plan(frame, "UNSUPPORTED")
        with self.assertRaises(DataUnavailable):
            build_live_plan(frame, "BINANCE_TH_SPOT", risk_pct=5)


if __name__ == "__main__":
    unittest.main()
