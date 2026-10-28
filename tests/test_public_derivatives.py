import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from public_derivatives import (DerivativesDataError, DerivativesSnapshot,
                                evaluate_derivatives, fetch_derivatives, fetch_with_fallback,
                                fetch_kraken, parse_bybit, parse_kraken, parse_snapshot)
from coinglass_overlay import parse_quick_paste


NOW = datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)


def ms(dt):
    return int(dt.timestamp() * 1000)


def fixture():
    mark = {"symbol": "BTCUSDT", "time": ms(NOW - timedelta(minutes=1)), "lastFundingRate": "0.0001"}
    oi = [{"timestamp": ms(NOW - timedelta(hours=25-i)),
           "sumOpenInterestValue": str(1000000 + i * 1000)} for i in range(26)]
    ratio = [{"symbol": "BTCUSDT", "timestamp": ms(NOW - timedelta(minutes=45)), "longShortRatio": "1.1"}]
    return mark, oi, ratio


class PublicDerivativesTests(unittest.TestCase):
    def test_parse_24h_change_and_source(self):
        value = parse_snapshot("BTCUSDT", *fixture(), now=NOW)
        self.assertAlmostEqual(value.funding_rate_pct, 0.01)
        self.assertAlmostEqual(value.oi_change_24h_pct, 24000 / 1001000 * 100)
        self.assertEqual(value.symbol, "BTCUSDT")
        self.assertEqual(value.provider, "Binance")
        self.assertIn("single exchange", value.source)

    def test_missing_24h_history_fails(self):
        mark, oi, ratio = fixture()
        with self.assertRaises(DerivativesDataError):
            parse_snapshot("BTCUSDT", mark, oi[-10:], ratio, now=NOW)

    def test_stale_ratio_fails(self):
        mark, oi, ratio = fixture()
        ratio[0]["timestamp"] = ms(NOW - timedelta(hours=4))
        with self.assertRaises(DerivativesDataError):
            parse_snapshot("BTCUSDT", mark, oi, ratio, now=NOW)

    def test_symbol_mismatch_fails(self):
        mark, oi, ratio = fixture()
        with self.assertRaises(DerivativesDataError):
            parse_snapshot("ETHUSDT", mark, oi, ratio, now=NOW)

    def test_no_spot_only_futures_substitution(self):
        with self.assertRaises(DerivativesDataError):
            fetch_derivatives("PEPEBRL")

    def test_public_endpoints_only(self):
        with patch("public_derivatives._request", side_effect=list(fixture())) as request:
            with patch("public_derivatives.parse_snapshot"):
                fetch_derivatives("BTCUSDT")
        self.assertEqual([c.args[0] for c in request.call_args_list], [
            "/fapi/v1/premiumIndex", "/futures/data/openInterestHist",
            "/futures/data/globalLongShortAccountRatio"])

    def test_signal_with_supported_data(self):
        snapshot = DerivativesSnapshot(
            "BTCUSDT", NOW, 0.01, 2.5, 1.1, 123456.0, NOW, NOW, NOW)
        self.assertEqual(evaluate_derivatives("BUY", snapshot, 3)["signal"], "BUY")
        self.assertEqual(evaluate_derivatives("BUY", snapshot, -1)["signal"], "WAIT")
        self.assertEqual(evaluate_derivatives("SELL", snapshot, -1)["signal"], "SELL")
        self.assertEqual(evaluate_derivatives("BUY", None, 2)["signal"], "WAIT")

    def test_bybit_parser_does_not_mix_contract_quantity_with_usd(self):
        ticker = {"time": ms(NOW - timedelta(minutes=2)), "result": {"list": [{
            "symbol": "BTCUSDT", "fundingRate": "0.0002", "openInterestValue": "2500000"}]}}
        oi = {"result": {"list": [{"timestamp": ms(NOW - timedelta(hours=25-i)),
                                    "openInterest": str(100 + i)} for i in range(26)]}}
        ratio = {"result": {"list": [{"symbol": "BTCUSDT", "timestamp": ms(NOW - timedelta(minutes=40)),
                                      "buyRatio": "0.55", "sellRatio": "0.45"}]}}
        got = parse_bybit("BTCUSDT", ticker, oi, ratio, now=NOW)
        self.assertAlmostEqual(got.oi_change_24h_pct, (125 / 101 - 1) * 100)
        self.assertEqual(got.oi_notional_usdt, 2500000)
        self.assertEqual(got.provider, "Bybit")
        self.assertIn("quantity", got.source)

    def test_fallback_returns_only_one_exchange(self):
        snapshot = DerivativesSnapshot("BTCUSDT", NOW, .01, 2, 1, 100, NOW, NOW, NOW, "Bybit")
        with patch("public_derivatives.fetch_kraken", side_effect=DerivativesDataError("no Kraken")):
            with patch("public_derivatives.fetch_derivatives", side_effect=DerivativesDataError("451")):
                with patch("public_derivatives.fetch_bybit", return_value=snapshot) as fallback:
                    self.assertEqual(fetch_with_fallback("BTCUSDT"), snapshot)
                    fallback.assert_called_once_with("BTCUSDT")

    @staticmethod
    def kraken_fixture():
        ticker = {"tickers": [{"symbol": "PF_XBTUSD", "tag": "perpetual", "suspended": False,
                               "lastTime": (NOW - timedelta(minutes=2)).isoformat(), "fundingRate": 0.87}]}
        oi = {"result": {"timestamp": [int((NOW - timedelta(hours=25-i)).timestamp()) for i in range(26)],
                         "data": [[100+i, 102+i, 99+i, 100+i] for i in range(26)]}}
        ratio = {"result": {"timestamp": [int((NOW - timedelta(hours=1)).timestamp())], "data": [1.1]}}
        return ticker, oi, ratio

    def test_kraken_24h_fresh_and_never_normalizes_funding(self):
        value = parse_kraken("BTCUSDT", "PF_XBTUSD", *self.kraken_fixture(), now=NOW)
        self.assertAlmostEqual(value.oi_change_24h_pct, (125 / 101 - 1) * 100)
        self.assertEqual(value.oi_unit, "contracts")
        self.assertEqual(value.provider, "Kraken")
        self.assertEqual(value.funding_unit, "Kraken raw (not normalized)")
        # 0.87 is Kraken-native raw, not a Binance-compatible percent value.
        self.assertEqual(evaluate_derivatives("BUY", value, 3)["signal"], "BUY")

    def test_kraken_stale_rejected(self):
        ticker, oi, ratio = self.kraken_fixture()
        ratio["result"]["timestamp"] = [int((NOW - timedelta(hours=4)).timestamp())]
        with self.assertRaises(DerivativesDataError):
            parse_kraken("BTCUSDT", "PF_XBTUSD", ticker, oi, ratio, now=NOW)

    def test_kraken_uses_public_read_only_paths(self):
        ticker, oi, ratio = self.kraken_fixture()
        with patch("public_derivatives._kraken_request", side_effect=[ticker, oi, ratio]) as request:
            with patch("public_derivatives.parse_kraken"):
                fetch_kraken("BTCUSDT")
        self.assertEqual([c.args[0] for c in request.call_args_list], [
            "/derivatives/api/v3/tickers", "/api/charts/v1/analytics/PF_XBTUSD/open-interest",
            "/api/charts/v1/analytics/PF_XBTUSD/long-short-ratio"])

    def test_quick_paste_must_be_five_real_eligible_numbers(self):
        self.assertEqual(parse_quick_paste("0.01, 2.5, 1.1, 120000, 90000"),
                         (0.01, 2.5, 1.1, 120000.0, 90000.0))
        for invalid in ("0.01,2.5,1.1,12", "nan,2.5,1.1,0,0", "2.5,2.5,0,0,0", "0,0,1,-5,0"):
            with self.assertRaises(ValueError):
                parse_quick_paste(invalid)


if __name__ == "__main__":
    unittest.main()
