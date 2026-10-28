from datetime import datetime, timezone
import unittest

import numpy as np
import pandas as pd

from backtest_engine import BacktestConfig, simulate, walk_forward
from binance_data import count_time_gaps, parse_klines, search_catalog
from market_structure import structure_features
from research_engine import prepare_features, with_signal


def candles(n=1500, period="h", direction=1):
    times = pd.date_range("2025-01-01", periods=n, freq=period, tz="UTC")
    x = np.arange(n)
    close = 1000 + direction * x * 0.12 + np.sin(x / 7) * 8
    return pd.DataFrame({"open": close - 0.3, "high": close + 3,
                         "low": close - 3, "close": close,
                         "volume": 100 + (x % 8)}, index=times)


class TestDataAndStructure(unittest.TestCase):
    def test_search_any_supported_coin(self):
        catalog = [{"symbol": "BTCUSDT", "base": "BTC", "quote": "USDT"},
                   {"symbol": "DOGEUSDT", "base": "DOGE", "quote": "USDT"},
                   {"symbol": "BTCUSDC", "base": "BTC", "quote": "USDC"}]
        self.assertEqual([x["symbol"] for x in search_catalog(catalog, "bitcoin", "USDT")], ["BTCUSDT"])
        self.assertEqual([x["symbol"] for x in search_catalog(catalog, "DOGE", "USDT")], ["DOGEUSDT"])

    def test_parse_binance_klines(self):
        rows = [[1700000000000 + 60000 * i, "100", "105", "99", "103", "14",
                 1700000059999 + 60000 * i] for i in range(300)]
        df = parse_klines(rows)
        self.assertEqual(len(df), 300)
        self.assertEqual(float(df["close"].iloc[-1]), 103)
        self.assertEqual(count_time_gaps(df, "15m"), 299)

    def test_structure_never_rewrites_past_when_future_added(self):
        f = candles(500)
        earlier = structure_features(f.iloc[:300])
        later = structure_features(f).iloc[:300]
        pd.testing.assert_frame_equal(earlier, later)

    def test_higher_timeframe_never_uses_future_closed_candle(self):
        f = candles(1000, "h")
        h = candles(500, "4h")
        first = prepare_features(f.iloc[:700], h.iloc[:300], "1h")
        second = prepare_features(f, h, "1h").iloc[:700]
        pd.testing.assert_series_equal(first["higher_trend"], second["higher_trend"])


class TestBacktest(unittest.TestCase):
    def fake_features(self, n=350):
        f = candles(n)
        f["atr"] = 1.0
        f["support50"] = f["close"] - 5.0
        f["buy_gate"] = False
        f["sell_gate"] = False
        f["score"] = 0
        f["threshold"] = 6
        f.loc[f.index[249], "buy_gate"] = True
        f.loc[f.index[249], "score"] = 8
        return f

    def test_next_bar_entry_and_no_short(self):
        f = self.fake_features()
        result = simulate(f, BacktestConfig(), start=250, end=280)
        self.assertEqual(result["stats"]["trades"], 1)
        self.assertEqual(result["trades"].iloc[0]["entry_time"], f.index[250])
        self.assertEqual(result["trades"].iloc[0]["side"], "LONG")

    def test_wait_never_opens_position(self):
        f = self.fake_features()
        f["buy_gate"] = False
        result = simulate(f, BacktestConfig(), start=250, end=280)
        self.assertEqual(result["stats"]["trades"], 0)
        self.assertEqual(result["stats"]["return_pct"], 0)

    def test_walkforward_reports_separate_test_windows(self):
        f = self.fake_features(1700)
        result = walk_forward(f, BacktestConfig())
        self.assertEqual(result["status"], "OK")
        self.assertGreater(len(result["folds"]), 0)
        for fold in result["folds"]:
            self.assertLess(fold["train_end"], fold["test_start"])


if __name__ == "__main__":
    unittest.main()
