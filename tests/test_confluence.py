"""Single-result MTF consensus must never create a BUY from incomplete context."""

from dataclasses import replace
from datetime import timedelta
import unittest

from confluence import combine_timeframes
from test_multi_timeframe import NOW, cg, evaluate, future


def reports(*, price=100.):
    return {tf: evaluate(tf, derivatives=future(), price=price)
            for tf in ("15m", "1h", "4h", "1d")}


class TestConfluence(unittest.TestCase):
    def test_one_verdict_with_one_price_zone_when_all_frames_confirm(self):
        data = reports()
        data["4h"] = evaluate("4h", derivatives=future(), ema20=96., atr=3.)
        verdict = combine_timeframes(data)
        self.assertEqual(verdict.signal, "BUY")
        self.assertEqual(verdict.status, "READY")
        self.assertGreaterEqual(verdict.alignment_index, 70.)
        self.assertIs(verdict.entry, data["1h"].entry)
        self.assertNotEqual(verdict.entry.entry_low, data["4h"].entry.entry_low)
        self.assertEqual(verdict.next_15m_close,
                         data["15m"].last_close + timedelta(minutes=15))

    def test_buy_direction_waits_when_price_above_one_hour_zone(self):
        verdict = combine_timeframes(reports(price=104.))
        self.assertEqual(verdict.signal, "BUY")
        self.assertEqual(verdict.status, "WAIT_ENTRY")
        self.assertEqual(verdict.entry.status, "WAIT_RETEST")

    def test_bearish_4h_context_blocks_mtf_buy(self):
        data = reports()
        data["4h"] = evaluate("4h", derivatives=future(), trend=-1)
        verdict = combine_timeframes(data)
        self.assertEqual(verdict.signal, "WAIT")
        self.assertEqual(verdict.status, "WAIT_SIGNAL")

    def test_missing_frame_and_stale_data_always_block(self):
        data = reports()
        del data["1d"]
        verdict = combine_timeframes(data)
        self.assertEqual(verdict.signal, "WAIT")
        self.assertIsNone(verdict.alignment_index)
        self.assertIn("1d", verdict.reasons[0])
        data = reports()
        data["15m"] = evaluate("15m", derivatives=future(), late=60)
        self.assertEqual(combine_timeframes(data).signal, "WAIT")

    def test_15m_must_confirm_with_buy_and_green_candle(self):
        data = reports()
        data["15m"] = evaluate("15m", derivatives=future(), open=100.4)
        self.assertEqual(combine_timeframes(data).signal, "WAIT")
        data = reports()
        data["15m"] = evaluate("15m", derivatives=None)
        self.assertEqual(combine_timeframes(data).signal, "WAIT")

    def test_coin_glass_veto_in_a_required_frame_blocks(self):
        data = reports()
        stale = cg(at=NOW - timedelta(hours=3))
        data["15m"] = evaluate("15m", derivatives=future(), coinglass=stale)
        data["1h"] = evaluate("1h", derivatives=future(), coinglass=stale)
        self.assertEqual(combine_timeframes(data).signal, "WAIT")

    def test_alignment_index_is_not_sufficient_by_itself(self):
        data = reports()
        data["4h"] = replace(data["4h"], trend=-1)
        verdict = combine_timeframes(data)
        self.assertGreater(verdict.alignment_index, 70.)
        self.assertEqual(verdict.signal, "WAIT")

    def test_low_weighted_score_blocks_even_with_nominal_buys(self):
        data = {tf: replace(r, score=1) for tf, r in reports().items()}
        verdict = combine_timeframes(data)
        self.assertLess(verdict.alignment_index, 70.)
        self.assertEqual(verdict.signal, "WAIT")


if __name__ == "__main__":
    unittest.main()
