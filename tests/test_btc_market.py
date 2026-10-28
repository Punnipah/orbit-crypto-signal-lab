"""BTC risk-regime checks use only closed Spot candles."""

from datetime import datetime, timedelta, timezone
import unittest

import numpy as np
import pandas as pd

from btc_market import btc_context_checks, btc_regime


NOW = datetime(2026, 10, 28, 12, 1, tzinfo=timezone.utc)


def market(tf="4h", *, rising=True, old=False, gap=False):
    freq = "4h" if tf == "4h" else "D"
    final_open = (datetime(2026, 10, 28, 8, tzinfo=timezone.utc)
                  if tf == "4h" else datetime(2026, 10, 27, tzinfo=timezone.utc))
    if old:
        final_open -= timedelta(days=5)
    idx = pd.date_range(end=final_open, periods=300, freq=freq)
    if gap:
        idx = idx.to_list()
        idx[-10] += timedelta(minutes=1)
    close = np.linspace(90, 120, 300) if rising else np.linspace(120, 90, 300)
    return pd.DataFrame({"open": close, "high": close+2, "low": close-2,
                         "close": close, "volume": 100.}, index=idx)


class TestBtcMarket(unittest.TestCase):
    def test_uptrend_both_frames_is_clean(self):
        regime = btc_regime(market(), market("1d"), now=NOW)
        self.assertEqual(regime.trend_4h, 1)
        self.assertEqual(regime.trend_1d, 1)
        self.assertTrue(regime.clean)
        self.assertTrue(all(c.passed for c in btc_context_checks(regime)))

    def test_bearish_four_hour_blocks_buy_context(self):
        regime = btc_regime(market(rising=False), market("1d"), now=NOW)
        self.assertFalse(btc_context_checks(regime)[1].passed)

    def test_stale_or_gapped_market_does_not_pass(self):
        self.assertFalse(btc_regime(market(old=True), market("1d"), now=NOW).clean)
        self.assertFalse(btc_regime(market(gap=True), market("1d"), now=NOW).clean)

    def test_missing_regime_blocks(self):
        self.assertFalse(btc_context_checks(None)[0].passed)


if __name__ == "__main__":
    unittest.main()
