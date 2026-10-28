from datetime import datetime, timedelta, timezone
import unittest

from coinglass_overlay import CoinGlassSnapshot, confirm_signal


NOW = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)


def snapshot(**changes):
    values = dict(
        symbol="BTC", observed_at=NOW - timedelta(minutes=20),
        funding_rate_pct=0.005, oi_change_24h_pct=2.4,
        long_short_account_ratio=1.05,
        long_liquidations_usd_24h=2_000_000.0,
        short_liquidations_usd_24h=1_000_000.0,
    )
    values.update(changes)
    return CoinGlassSnapshot(**values)


class TestCoinGlassOverlay(unittest.TestCase):
    def test_missing_snapshot_blocks_trade_signal(self):
        result = confirm_signal("BUY", None, "BTC", 3, now=NOW)
        self.assertEqual(result["signal"], "WAIT")
        self.assertEqual(result["status"], "MISSING")

    def test_fresh_confluence_confirms_buy(self):
        result = confirm_signal("BUY", snapshot(), "BTC", 2.0, now=NOW)
        self.assertEqual(result["signal"], "BUY")
        self.assertTrue(result["confirmed"])

    def test_fresh_confluence_confirms_sell(self):
        result = confirm_signal("SELL", snapshot(funding_rate_pct=-0.003), "BTC", -2.0, now=NOW)
        self.assertEqual(result["signal"], "SELL")

    def test_crowded_longs_block_buy(self):
        result = confirm_signal("BUY", snapshot(long_short_account_ratio=1.66), "BTC", 2, now=NOW)
        self.assertEqual(result["signal"], "WAIT")
        self.assertEqual(result["status"], "CAUTION")
        self.assertIn("1.660 > 1.600", result["blocking_reasons"][0])

    def test_account_ratio_boundary_is_not_automatically_rejected(self):
        result = confirm_signal("BUY", snapshot(long_short_account_ratio=1.6), "BTC", 2, now=NOW)
        self.assertEqual(result["status"], "CONFIRMED")
        self.assertEqual(result["blocking_reasons"], [])

    def test_funding_and_crowding_both_show_as_specific_blockers(self):
        result = confirm_signal("BUY", snapshot(funding_rate_pct=0.06,
                                                 long_short_account_ratio=1.7), "BTC", 2, now=NOW)
        self.assertEqual(len(result["blocking_reasons"]), 2)
        self.assertTrue(any("+0.0600%" in reason for reason in result["blocking_reasons"]))
        self.assertTrue(any("1.700 > 1.600" in reason for reason in result["blocking_reasons"]))

    def test_falling_oi_blocks_buy(self):
        result = confirm_signal("BUY", snapshot(oi_change_24h_pct=-3), "BTC", 2, now=NOW)
        self.assertEqual(result["signal"], "WAIT")

    def test_stale_snapshot_blocks_trade_signal(self):
        result = confirm_signal("BUY", snapshot(observed_at=NOW-timedelta(hours=5)), "BTC", 2,
                                now=NOW, max_age_hours=2)
        self.assertEqual(result["status"], "INVALID")
        self.assertTrue(any("เก่าเกิน" in why for why in result["blocking_reasons"]))

    def test_wrong_coin_blocks_trade_signal(self):
        result = confirm_signal("BUY", snapshot(symbol="ETH"), "BTC", 2, now=NOW)
        self.assertEqual(result["status"], "INVALID")

    def test_liquidations_are_context_not_decisive(self):
        result = confirm_signal("BUY", snapshot(long_liquidations_usd_24h=0,
                                                short_liquidations_usd_24h=100_000_000), "BTC", 2, now=NOW)
        self.assertEqual(result["signal"], "BUY")
        self.assertTrue(any("Liquidation" in reason for reason in result["reasons"]))


if __name__ == "__main__":
    unittest.main()
