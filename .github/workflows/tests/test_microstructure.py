"""Public liquidity/anonymous aggressor data never invents whale identities."""

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from binance_data import PublicDataError, parse_klines
from market_microstructure import (fetch_microstructure, microstructure_checks,
                                   parse_microstructure)


NOW = datetime(2026, 10, 28, 13, 0, tzinfo=timezone.utc)


def market(*, buy_ratio=.7, spread=.1, time_age=5):
    ticker = {"symbol": "BTCUSDT", "bidPrice": "100", "askPrice": str(100 + spread)}
    book = {"lastUpdateId": 123,
            "bids": [["100", "300"], ["99.9", "300"]],
            "asks": [[str(100+spread), "300"], ["100.2", "300"]]}
    trades = [{"p": "100", "q": "1", "m": i >= int(100 * buy_ratio),
               "T": int((NOW - timedelta(minutes=time_age)).timestamp() * 1000)}
              for i in range(100)]
    return ticker, book, trades


class TestMicrostructure(unittest.TestCase):
    def test_orderbook_and_aggressor_buy_share_are_consistent(self):
        snapshot = parse_microstructure("BTCUSDT", *market(), requested_notional=1000, now=NOW)
        self.assertAlmostEqual(snapshot.aggressor_buy_share, .7)
        self.assertAlmostEqual(snapshot.spread_bps, 9.995, places=1)
        self.assertGreater(snapshot.depth_bid_quote, 5 * 1000)
        self.assertGreater(snapshot.depth_ask_quote, 5 * 1000)
        self.assertIsNotNone(snapshot.ask_impact_bps)
        self.assertTrue(all(c.passed for c in microstructure_checks(snapshot, now=NOW,
                                                                      requested_notional=1000)))

    def test_sell_pressure_blocks_even_when_depth_is_large(self):
        snapshot = parse_microstructure("BTCUSDT", *market(buy_ratio=.1),
                                        requested_notional=1000, now=NOW)
        checks = microstructure_checks(snapshot, now=NOW, requested_notional=1000)
        self.assertTrue(any(not c.passed and "Aggressive" in c.label for c in checks))

    def test_stale_trade_and_unknown_book_are_rejected(self):
        snapshot = parse_microstructure("BTCUSDT", *market(time_age=80),
                                        requested_notional=1000, now=NOW)
        self.assertFalse(microstructure_checks(snapshot, now=NOW, requested_notional=1000)[1].passed)
        with self.assertRaises(PublicDataError):
            parse_microstructure("BTCUSDT", {"symbol": "ETHUSDT"}, market()[1], market()[2],
                                 requested_notional=1000, now=NOW)

    def test_missing_asks_returns_no_impact_and_blocks(self):
        ticker, book, trades = market()
        book["asks"] = [["100.1", "1"]]
        snapshot = parse_microstructure("BTCUSDT", ticker, book, trades,
                                        requested_notional=1000, now=NOW)
        self.assertIsNone(snapshot.ask_impact_bps)
        self.assertFalse(microstructure_checks(snapshot, now=NOW, requested_notional=1000)[4].passed)

    def test_public_endpoints_only_and_no_api_key(self):
        ticker, book, trades = market()
        with patch("market_microstructure._get_json", side_effect=[ticker, book, trades]) as getter:
            snapshot = fetch_microstructure("BTCUSDT", 1000)
        self.assertEqual(snapshot.symbol, "BTCUSDT")
        self.assertEqual([c.args[0] for c in getter.call_args_list],
                         ["/ticker/bookTicker", "/depth", "/aggTrades"])

    def test_real_taker_volume_parsed_and_missing_not_fabricated(self):
        ms = 1700000000000
        normal = [[ms, "100", "101", "99", "100.5", "10", ms+59999,
                   "1000", 15, "7", "700", "0"]]
        parsed = parse_klines(normal)
        self.assertEqual(float(parsed["taker_buy_base"].iloc[0]), 7.0)
        synthetic = [[ms, "100", "101", "99", "100.5", "10", ms+59999]]
        self.assertTrue(parse_klines(synthetic)["taker_buy_base"].isna().all())
        bad = [r.copy() for r in normal]
        bad[0][9] = "12"
        with self.assertRaises(PublicDataError):
            parse_klines(bad)


if __name__ == "__main__":
    unittest.main()
