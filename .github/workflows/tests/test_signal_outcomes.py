"""Temporal safety of hypothetical paper signal replay."""

from datetime import datetime, timedelta, timezone
import unittest

import pandas as pd

from signal_outcomes import evaluate_recorded_signals


class PaperOutcomeTests(unittest.TestCase):
    def setUp(self):
        idx = pd.date_range("2026-10-27 00:00:00", periods=72, freq="h", tz="UTC")
        self.frame = pd.DataFrame({"open": [100.] * 72,
                                   "high": [101.] * 72, "low": [99.] * 72,
                                   "close": [100.] * 72}, index=idx)
        self.record = {"observed_at_th": "2026-10-28 10:20:00", "symbol": "BTCUSDT",
                       "mtf_signal": "BUY", "entry_status": "READY",
                       "entry_low": 99., "entry_high": 101.,
                       "stop_loss": 95., "tp2": 110.,
                       "fee_pct_per_side": .1, "slippage_pct_per_side": .05}

    def test_next_bar_open_only_and_stop_first_when_both_touch(self):
        # Thai 10:20 = UTC 03:20, next 1h bar opens at UTC 04:00.
        target_idx = pd.Timestamp("2026-10-28 04:00:00", tz="UTC")
        self.frame.loc[target_idx, "high"] = 111
        self.frame.loc[target_idx, "low"] = 94
        results = evaluate_recorded_signals([self.record], self.frame, "BTCUSDT")
        self.assertEqual(results.iloc[0]["status"], "HYPOTHETICAL_STOP")
        self.assertAlmostEqual(results.iloc[0]["assumed_entry"], 100)
        self.assertLess(results.iloc[0]["net_r_model"], 0)

    def test_next_bar_open_outside_zone_does_not_fill(self):
        self.frame.loc[pd.Timestamp("2026-10-28 04:00:00", tz="UTC"), "open"] = 103
        result = evaluate_recorded_signals([self.record], self.frame, "BTCUSDT")
        self.assertEqual(result.iloc[0]["status"], "NOT_FILLED_NEXT_OPEN")

    def test_signal_recorded_after_history_remains_pending(self):
        row = dict(self.record, observed_at_th="2026-11-05 15:00:00")
        result = evaluate_recorded_signals([row], self.frame, "BTCUSDT")
        self.assertEqual(result.iloc[0]["status"], "PENDING_NEXT_1H_CANDLE")

    def test_future_candles_never_change_past_fill_decision(self):
        selected = self.frame.copy()
        base = evaluate_recorded_signals([self.record], selected, "BTCUSDT")
        selected.loc[pd.Timestamp("2026-10-29 23:00:00", tz="UTC"), "open"] = 500
        after = evaluate_recorded_signals([self.record], selected, "BTCUSDT")
        self.assertEqual(base.iloc[0]["assumed_entry"], after.iloc[0]["assumed_entry"])

    def test_wait_signal_never_labeled_trade(self):
        record = dict(self.record, entry_status="WAIT_SIGNAL")
        result = evaluate_recorded_signals([record], self.frame, "BTCUSDT")
        self.assertTrue(result.empty)


if __name__ == "__main__":
    unittest.main()
