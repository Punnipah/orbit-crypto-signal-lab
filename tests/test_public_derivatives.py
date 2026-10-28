import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from public_derivatives import (DerivativesDataError, DerivativesSnapshot,
                                evaluate_derivatives, fetch_derivatives, fetch_with_fallback,
                                parse_bybit, parse_snapshot)


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
        self.assertIn("quantity", got.source)

    def test_fallback_returns_only_one_exchange(self):
        snapshot = DerivativesSnapshot("BTCUSDT", NOW, .01, 2, 1, 100, NOW, NOW, NOW, "Bybit")
        with patch("public_derivatives.fetch_derivatives", side_effect=DerivativesDataError("451")):
            with patch("public_derivatives.fetch_bybit", return_value=snapshot) as fallback:
                self.assertEqual(fetch_with_fallback("BTCUSDT"), snapshot)
                fallback.assert_called_once_with("BTCUSDT")


if __name__ == "__main__":
    unittest.main()
