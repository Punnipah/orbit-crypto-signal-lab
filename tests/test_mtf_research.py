"""Historical multi-timeframe alignment must not use future closing bars."""

from datetime import datetime, timezone
import unittest

import numpy as np
import pandas as pd

from backtest_engine import BacktestConfig
from mtf_research import _known_at, historical_mtf_features, mtf_walk_forward, run_mtf_backtest


def fake(tf, n=400):
    freq = {"15m": "15min", "1h": "h", "4h": "4h", "1d": "D"}[tf]
    end = datetime(2026, 10, 28, tzinfo=timezone.utc)
    idx = pd.date_range(end=end, freq=freq, periods=n)
    f = pd.DataFrame(index=idx)
    row = {
        "open": 99.6, "high": 101., "low": 98.8, "close": 100., "volume": 100.,
        "signal": "BUY", "score": 7 if tf == "1d" else 8,
        "trend": 1, "higher_trend": 1, "structure_bias": 1,
        "atr": 2., "pivot_high": 96., "pivot_low": 97.,
        "support50": 98., "ema20": 99.5, "ema50": 98.,
        "volume_ratio": 1., "taker_buy_share20": .65,
        "sweep_high": False,
    }
    for col, val in row.items():
        f[col] = val
    return f


class TestMtfResearch(unittest.TestCase):
    def test_four_hour_bar_not_seen_before_its_close(self):
        base_close = pd.DatetimeIndex([
            datetime(2026, 10, 28, 2, tzinfo=timezone.utc),
            datetime(2026, 10, 28, 4, tzinfo=timezone.utc),
        ])
        f = pd.DataFrame({"score": [8.]}, index=pd.DatetimeIndex([
            datetime(2026, 10, 28, tzinfo=timezone.utc)]))
        merged = _known_at(base_close, f, "4h", ("score",))
        self.assertTrue(pd.isna(merged.iloc[0]["score"]))
        self.assertEqual(merged.iloc[1]["score"], 8.)

    def test_signal_uses_one_hour_closed_bar_and_single_1h_plan(self):
        f = {tf: fake(tf) for tf in ("15m", "1h", "4h", "1d")}
        out = historical_mtf_features(f, BacktestConfig())
        self.assertEqual(len(out), 400)
        self.assertIn("mtf_strength", out.columns)
        self.assertIn("mtf_entry_low", out.columns)
        self.assertTrue((out["mtf_strength"].dropna() <= 100).all())
        self.assertTrue((out["mtf_entry_low"].dropna() < out["mtf_entry_high"].dropna()).all())
        run = run_mtf_backtest(out, BacktestConfig(), 70)
        self.assertTrue(all(t["side"] == "LONG" for t in run["trades"].to_dict("records")))

    def test_weak_taker_flow_blocks_historical_entries(self):
        f = {tf: fake(tf) for tf in ("15m", "1h", "4h", "1d")}
        f["15m"]["taker_buy_share20"] = .2
        out = historical_mtf_features(f, BacktestConfig())
        self.assertFalse(out["mtf_base_gate"].any())
        self.assertEqual(run_mtf_backtest(out, BacktestConfig(), 70)["stats"]["trades"], 0)

    def test_walkforward_requires_sufficient_history(self):
        f = {tf: fake(tf) for tf in ("15m", "1h", "4h", "1d")}
        out = historical_mtf_features(f, BacktestConfig())
        self.assertEqual(mtf_walk_forward(out, BacktestConfig())["status"], "INSUFFICIENT")

    def test_walkforward_windows_disjoint_even_with_no_trades(self):
        f = fake("1h", 2000)
        f["mtf_base_gate"] = False
        f["mtf_strength"] = 95.
        f["mtf_entry_low"] = np.nan
        f["mtf_entry_high"] = np.nan
        f["mtf_stop"] = np.nan
        f["mtf_tp2"] = np.nan
        result = mtf_walk_forward(f, BacktestConfig())
        self.assertEqual(result["status"], "OK")
        self.assertTrue(all(fold["train_end"] < fold["test_start"]
                            for fold in result["folds"]))
        self.assertTrue(all(fold["trades"] == 0 for fold in result["folds"]))

    def test_precomputed_plan_must_wait_for_next_open_inside_zone(self):
        f = fake("1h", 350)
        f["signal"] = "WAIT"
        f.iloc[300, f.columns.get_loc("signal")] = "BUY"
        f["mtf_entry_low"] = 99.
        f["mtf_entry_high"] = 100.
        f["mtf_stop"] = 96.
        f["mtf_tp2"] = 110.
        f.iloc[301, f.columns.get_loc("open")] = 105.
        from backtest_engine import simulate
        out = simulate(f, BacktestConfig(), precomputed_signals=True, planned_levels=True)
        self.assertEqual(out["stats"]["trades"], 0)


if __name__ == "__main__":
    unittest.main()
