"""Regression checks for the isolated paper-only Model Lab, no internet needed."""

from __future__ import annotations

from datetime import datetime, timezone
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orbit_model_lab_engine import (DataUnavailable, MODELS, ResearchSettings,
                                    fetch_candles, indicators, model_signals,
                                    research_report, simulate, validate_candles)


def fixture(n=1600):
    opened = 1_780_000_000_000 // 300_000 * 300_000 + np.arange(n) * 300_000
    cycle = np.sin(np.arange(n) / 17) * .003
    close = 100 * np.exp(np.cumsum(cycle))
    opening = np.r_[100, close[:-1]]
    return pd.DataFrame({"open_ms": opened, "open": opening,
                         "high": np.maximum(opening, close) * 1.001,
                         "low": np.minimum(opening, close) * .999,
                         "close": close, "volume": 5000 + np.arange(n) % 100})


class ModelLabTests(unittest.TestCase):
    def test_contiguous_bars_and_gap_block(self):
        good = validate_candles(fixture())
        self.assertEqual(len(good), 1600)
        broken = fixture().drop(index=501)
        with self.assertRaisesRegex(DataUnavailable, "ช่วงเวลาขาด"):
            validate_candles(broken)

    def test_reject_impossible_ohlc_and_stale(self):
        bad = fixture()
        bad.loc[20, "high"] = 0
        with self.assertRaises(DataUnavailable):
            validate_candles(bad)
        with self.assertRaises(DataUnavailable):
            validate_candles(fixture(), now=datetime(2027, 1, 1, tzinfo=timezone.utc))

    def test_future_candle_cannot_repaint_previous_signal(self):
        base = fixture()
        orig = indicators(base)
        altered = base.copy()
        tail = altered.index[-1]
        altered.loc[tail, ["open", "high", "low", "close"]] = [1000, 1001, 999, 1000]
        updated = indicators(altered)
        for model in MODELS:
            a = model_signals(orig, model, True)
            b = model_signals(updated, model, True)
            pd.testing.assert_series_equal(a.iloc[:-1], b.iloc[:-1])

    def test_spot_cannot_have_short(self):
        f = indicators(fixture())
        for model in MODELS:
            self.assertFalse((model_signals(f, model, False) < 0).any())

    def test_next_candle_entry_and_fee_penalty(self):
        f = indicators(fixture())
        signal = pd.Series(0, index=f.index)
        signal.iloc[299] = 1
        free = simulate(f, signal, ResearchSettings(0, 0), 300, 400)
        charged = simulate(f, signal, ResearchSettings(10, 5), 300, 400)
        self.assertEqual(len(free), 1)
        self.assertAlmostEqual(free.entry.iloc[0], f.open.iloc[300])
        self.assertAlmostEqual(free.net_pct.iloc[0] - charged.net_pct.iloc[0], .30)

    def test_report_separates_train_and_holdout(self):
        report, raw, _ = research_report(fixture(), ResearchSettings(), allow_short=True)
        self.assertEqual(len(report), len(MODELS) * 2)
        self.assertEqual(set(raw), set(MODELS))
        self.assertTrue((report[report.Window == "Holdout 30%"]["Verdict"] !=
                         "TRAIN · NOT DECISION").all())

    def test_negative_holdout_not_painted_as_just_missing_data(self):
        report, _, _ = research_report(fixture(), ResearchSettings(), allow_short=False)
        negative = report[(report.Window == "Holdout 30%") &
                          (report["Mean net/trade %"] < 0)]
        self.assertTrue((negative.Verdict == "NEGATIVE HOLDOUT · NO EDGE SHOWN").all())

    def test_public_binance_candles_pagination_without_replacing_venue(self):
        now_ms = 1_780_000_000_000 // 300_000 * 300_000
        now = datetime.fromtimestamp((now_ms + 10_000) / 1000, timezone.utc)

        def read(url, params):
            self.assertIn("api.binance.th", url)
            self.assertEqual(params["symbol"], "PEPEUSDT")
            start, end = int(params["startTime"]), int(params["endTime"])
            times = range(start, end + 1, 300_000)
            return [[t, "100", "101", "99", "100", "5000", t + 299999,
                     "0", 100, "2500", "0", "0"] for t in times]

        with patch("orbit_model_lab_engine._read_json", side_effect=read):
            frame = fetch_candles("BINANCE_TH_SPOT", "PEPEUSDT", 7, now=now)
        self.assertGreater(len(frame), 2000)
        self.assertLess(frame.open_ms.iloc[-1] + 300_000, int(now.timestamp() * 1000) + 1)


if __name__ == "__main__":
    unittest.main()
