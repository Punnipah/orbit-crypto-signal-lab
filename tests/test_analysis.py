import unittest

import numpy as np
import pandas as pd

from analysis_engine import evaluate, indicators


def synthetic_prices(direction=1, n=400):
    timestamp = pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC")
    slope = direction * np.arange(n) * 0.8
    wave = np.sin(np.arange(n) / 6) * 3
    close = 1000 + slope + wave
    open_ = close - direction * 0.4
    return pd.DataFrame({"open": open_, "high": close + 2, "low": close - 2,
                         "close": close, "volume": np.full(n, 100.0)}, index=timestamp)


class TestIndicators(unittest.TestCase):
    def test_rising_data_has_positive_trend(self):
        frame = indicators(synthetic_prices(1))
        self.assertGreater(frame["ema50"].iloc[-1], frame["ema200"].iloc[-1])
        self.assertTrue(np.isfinite(frame["adx"].iloc[-1]))

    def test_falling_data_has_negative_trend(self):
        frame = indicators(synthetic_prices(-1))
        self.assertLess(frame["ema50"].iloc[-1], frame["ema200"].iloc[-1])

    def test_score_bounded_and_wait_is_possible(self):
        f = synthetic_prices(1)
        result = evaluate(f, f)
        self.assertLessEqual(abs(result["score"]), 9)
        self.assertIn(result["signal"], ("BUY", "SELL", "WAIT"))

    def test_higher_timeframe_disagreement_blocks_buy_and_sell(self):
        result = evaluate(synthetic_prices(1), synthetic_prices(-1))
        self.assertEqual(result["signal"], "WAIT")

    def test_same_timeframe_does_not_double_count(self):
        f = synthetic_prices(1)
        result = evaluate(f, f, same_timeframe=True)
        self.assertEqual(result["max_score"], 7)
        self.assertEqual(result["factors"][-1]["points"], 0)


if __name__ == "__main__":
    unittest.main()
