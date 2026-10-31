"""Provisional levels are evidence-based, read-only and never READY signals."""
import unittest

import pandas as pd

from indicative_zones import indicative_zone


class WatchPriceTests(unittest.TestCase):
    def frame(self):
        data = []
        for i in range(60):
            c = 100 + (i % 8) * .18
            data.append({"open": c-.04, "high": c+.20, "low": c-.22, "close": c})
        return pd.DataFrame(data)

    def test_spot_wait_has_conditional_levels(self):
        p = indicative_zone(self.frame())
        self.assertIsNotNone(p)
        self.assertLess(p.low, p.high)
        self.assertLess(p.invalidation, p.low)
        self.assertLess(p.high, p.target_1)
        self.assertLess(p.target_1, p.target_2)

    def test_futures_short_has_opposite_levels(self):
        p = indicative_zone(self.frame(), side="SHORT")
        self.assertLess(p.target_2, p.target_1)
        self.assertLess(p.target_1, p.low)
        self.assertLess(p.high, p.invalidation)

    def test_invalid_or_missing_data_returns_no_price(self):
        self.assertIsNone(indicative_zone(self.frame().head(10)))
        frame = self.frame()
        frame.loc[0, "close"] = float("nan")
        self.assertIsNone(indicative_zone(frame))


if __name__ == "__main__":
    unittest.main()
