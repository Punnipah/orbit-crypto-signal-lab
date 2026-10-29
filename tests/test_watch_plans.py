"""Frozen watch plan: causal 15m replay and safety gates."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

import pandas as pd

from watch_plans import decode_watch, encode_watch, evaluate_watch, new_watch_plan


UTC = timezone.utc
START = datetime(2026, 10, 29, 2, 0, tzinfo=UTC)
LOW, HIGH, STOP, TP1, TP2 = (0.00000480, 0.00000485, 0.00000475,
                              0.00000500, 0.00000520)


def make_plan(hours=12):
    entry = SimpleNamespace(entry_low=LOW, entry_high=HIGH, stop_loss=STOP,
                            take_profit_1=TP1, take_profit_2=TP2)
    return new_watch_plan("PEPEUSDT", entry, now=START, hours=hours)


def candles(event_rows=()):
    """Start with 25 legitimate *prior* candles so prior volume is known."""
    records = []
    ix = []
    for i in range(-25, 0):
        ix.append(START + timedelta(minutes=15 * i))
        records.append(dict(open=0.00000494, high=0.00000496, low=0.00000493,
                            close=0.00000495, volume=100.))
    for i, row in enumerate(event_rows):
        ix.append(START + timedelta(minutes=15 * i))
        records.append(dict(open=row[0], high=row[1], low=row[2],
                            close=row[3], volume=row[4]))
    return pd.DataFrame(records, index=pd.DatetimeIndex(ix))


TOUCH = (0.00000491, 0.00000492, 0.00000482, 0.00000484, 120)
RECLAIM = (0.00000484, 0.00000488, 0.00000482, 0.00000486, 125)
BREAK = (0.00000486, 0.00000492, 0.00000484, 0.00000489, 135)


def check(rows, quote=0.00000489, mtf=True, now=None):
    data = candles(rows)
    if now is None:
        now = START + timedelta(minutes=15 * len(rows))
    return evaluate_watch(make_plan(), data, now=now,
                          current_price=quote, mtf_buy=mtf)


class TestFrozenPlan(unittest.TestCase):
    def test_roundtrip_preserves_frozen_prices_and_times(self):
        plan = make_plan()
        self.assertEqual(decode_watch(encode_watch(plan)), plan)

    def test_decode_rejects_corrupted_and_oversize_tokens(self):
        token = encode_watch(make_plan())
        with self.assertRaises(ValueError):
            decode_watch(token[:-1] + ("0" if token[-1] != "0" else "1"))
        with self.assertRaises(ValueError):
            decode_watch("a" * 3000)

    def test_rejects_bad_price_order_and_symbol(self):
        with self.assertRaises(ValueError):
            encode_watch(replace(make_plan(), stop_loss=HIGH))
        with self.assertRaises(ValueError):
            encode_watch(replace(make_plan(), symbol="PEPE/USDT"))

    def test_rejects_non_numeric_and_nonfinite(self):
        with self.assertRaises(ValueError):
            encode_watch(replace(make_plan(), stop_loss=float("nan")))

    def test_rejects_bad_expiry(self):
        with self.assertRaises(ValueError):
            make_plan(hours=73)

    def test_touch_is_not_buy(self):
        result = check([TOUCH], quote=0.00000483)
        self.assertEqual(result.status, "WAIT_RECLAIM")
        self.assertIsNotNone(result.touched_at)
        self.assertIsNone(result.triggered_at)

    def test_reclaim_alone_is_not_buy(self):
        result = check([TOUCH, RECLAIM], quote=0.00000486)
        self.assertEqual(result.status, "WAIT_BREAK")
        self.assertIsNotNone(result.reclaimed_at)
        self.assertIsNone(result.triggered_at)

    def test_break_confirmation_still_requires_mtf(self):
        result = check([TOUCH, RECLAIM, BREAK], mtf=False)
        self.assertEqual(result.status, "WAIT_MTF")
        self.assertEqual(result.trigger_price, BREAK[3])

    def test_full_confirmation_has_live_rr(self):
        result = check([TOUCH, RECLAIM, BREAK])
        self.assertEqual(result.status, "READY_NOW")
        self.assertIsNotNone(result.net_rr_tp2)
        self.assertGreaterEqual(result.net_rr_tp2, 1.5)

    def test_dont_chase_price_far_above_zone(self):
        result = check([TOUCH, RECLAIM, BREAK], quote=0.00000499)
        self.assertEqual(result.status, "PASSED")

    def test_historical_trigger_is_not_ready_today(self):
        rows = [TOUCH, RECLAIM, BREAK] + [
            (0.00000490, 0.00000492, 0.00000488, 0.00000490, 110)] * 3
        result = check(rows)
        self.assertEqual(result.status, "PASSED")

    def test_stop_wick_invalidates_setup(self):
        dropped = (0.00000481, 0.00000485, 0.00000474, 0.00000482, 140)
        result = check([TOUCH, dropped], quote=0.00000482)
        self.assertEqual(result.status, "INVALIDATED")

    def test_two_closes_below_zone_invalidate(self):
        red = (0.00000483, 0.00000483, 0.00000477, 0.00000478, 140)
        result = check([TOUCH, red, red], quote=0.00000478)
        self.assertEqual(result.status, "INVALIDATED")

    def test_live_quote_at_stop_invalidates(self):
        result = check([TOUCH], quote=STOP)
        self.assertEqual(result.status, "INVALIDATED")

    def test_quote_missing_is_not_ready(self):
        result = check([TOUCH, RECLAIM, BREAK], quote=None)
        self.assertEqual(result.status, "DATA_MISSING")

    def test_missing_15m_data_does_not_buy(self):
        result = evaluate_watch(make_plan(), pd.DataFrame(), now=START,
                                current_price=HIGH, mtf_buy=True)
        self.assertEqual(result.status, "DATA_MISSING")

    def test_candle_time_gap_blocks_trade(self):
        frame = candles([TOUCH, RECLAIM, BREAK]).drop(START + timedelta(minutes=15))
        result = evaluate_watch(make_plan(), frame, now=START + timedelta(minutes=45),
                                current_price=0.00000489, mtf_buy=True)
        self.assertEqual(result.status, "DATA_GAP")

    def test_expiry_blocks_even_when_market_data_old(self):
        result = check([TOUCH, RECLAIM, BREAK], now=START + timedelta(hours=13))
        self.assertEqual(result.status, "EXPIRED")

    def test_old_market_data_blocks_ready(self):
        result = check([TOUCH, RECLAIM, BREAK], now=START + timedelta(hours=1, minutes=30))
        self.assertEqual(result.status, "DATA_STALE")

    def test_candle_already_open_at_creation_is_not_historical_touch(self):
        plan = replace(make_plan(), created_at=START + timedelta(minutes=5))
        frame = candles([TOUCH, (0.00000488, 0.00000491, 0.00000487, 0.00000489, 120)])
        result = evaluate_watch(plan, frame, now=START + timedelta(minutes=30),
                                current_price=0.00000489, mtf_buy=True)
        self.assertEqual(result.status, "WAIT_ZONE")
        self.assertIsNone(result.touched_at)

    def test_unconfirmed_candle_is_not_used(self):
        result = check([TOUCH, RECLAIM, BREAK], now=START + timedelta(minutes=35))
        self.assertNotEqual(result.status, "READY_NOW")

    def test_fee_slippage_can_veto_weak_rr(self):
        plan = replace(make_plan(), min_net_rr=3)
        frame = candles([TOUCH, RECLAIM, BREAK])
        result = evaluate_watch(plan, frame, now=START + timedelta(minutes=45),
                                current_price=BREAK[3], mtf_buy=True)
        self.assertEqual(result.status, "WAIT_RISK")


if __name__ == "__main__":
    unittest.main()
