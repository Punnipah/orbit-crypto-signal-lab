"""Regression tests for v2.5 prospective zones, timing, and risk bounds."""

from datetime import datetime, timedelta, timezone
import math
import unittest

from entry_planner import plan_entry


CLOSED = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def row(**changes):
    values = {
        "open": 99.6, "high": 101, "low": 98, "close": 100,
        "atr": 2, "pivot_high": 96, "pivot_low": 97,
        "support50": 96.5, "ema20": 99.5, "ema50": 98,
        "trend": 1, "higher_trend": 1, "structure_bias": 1,
        "sweep_high": False, "sweep_low": False, "volume_ratio": 0.9,
    }
    values.update(changes)
    return values


def calculate(values=None, signal="BUY", timeframe="1h", **changes):
    values = values or row()
    quote = changes.pop("current_price", values["close"])
    return plan_entry(
        values, timeframe, signal, CLOSED,
        capital=10000, risk_pct=1, max_allocation_pct=30,
        fee_pct=.1, slippage_pct=.05, current_price=quote, **changes,
    )


class TestEntryPlanner(unittest.TestCase):
    def test_ready_only_after_closed_green_candle_and_final_buy(self):
        plan = calculate()
        self.assertEqual(plan.status, "READY")
        self.assertLess(plan.entry_low, 100)
        self.assertGreater(plan.entry_high, 100)
        self.assertLess(plan.stop_loss, plan.entry_low)
        self.assertGreater(plan.take_profit_1, plan.entry_high)
        self.assertGreater(plan.take_profit_2, plan.take_profit_1)
        self.assertEqual(plan.next_check_at, CLOSED + timedelta(hours=1))
        self.assertEqual(plan.expires_at, CLOSED + timedelta(hours=3))

    def test_wait_if_final_wait_even_inside_zone(self):
        plan = calculate(signal="WAIT")
        self.assertEqual(plan.status, "WAIT_CONFIRMATION")
        self.assertIsNotNone(plan.entry_low)
        self.assertNotIn("ซื้อแล้ว", plan.reason)

    def test_missing_live_quote_blocks_ready_but_preserves_watch_zone(self):
        plan = plan_entry(row(), "1h", "BUY", CLOSED, capital=10000, risk_pct=1,
                          max_allocation_pct=30, fee_pct=.1, slippage_pct=.05)
        self.assertEqual(plan.status, "WAIT_LIVE_QUOTE")
        self.assertIsNotNone(plan.entry_low)

    def test_current_price_outside_zone_blocks_ready(self):
        high = calculate(current_price=105)
        low = calculate(current_price=98)
        self.assertEqual(high.status, "WAIT_RETEST")
        self.assertEqual(low.status, "WAIT_RECLAIM")

    def test_live_price_in_zone_but_last_closed_outside_must_wait(self):
        plan = calculate(values=row(open=102.5, close=103, pivot_high=101, ema20=100),
                         current_price=101)
        self.assertEqual(plan.status, "WAIT_CONFIRMATION")

    def test_wait_retest_does_not_chase_price(self):
        plan = calculate(values=row(open=102.5, close=103, pivot_high=101, ema20=100))
        self.assertEqual(plan.status, "WAIT_RETEST")
        self.assertGreater(103, plan.entry_high)

    def test_bearish_candle_cannot_be_ready(self):
        plan = calculate(values=row(open=100.2, close=100))
        self.assertEqual(plan.status, "WAIT_CONFIRMATION")

    def test_bearish_structure_and_sweep_invalidate(self):
        for change in ({"trend": -1}, {"higher_trend": -1},
                       {"structure_bias": -1}, {"sweep_high": True}):
            with self.subTest(change=change):
                plan = calculate(values=row(**change))
                self.assertEqual(plan.status, "INVALID")
                self.assertIsNone(plan.entry_low)

    def test_stale_or_gapped_data_never_returns_levels(self):
        plan = plan_entry(row(), "1h", "BUY", CLOSED, capital=10000, risk_pct=1,
                          max_allocation_pct=30, fee_pct=.1, slippage_pct=.05,
                          data_ok=False)
        self.assertEqual(plan.status, "INVALID")
        self.assertIsNone(plan.stop_loss)

    def test_no_close_support_is_not_fabricated(self):
        plan = calculate(values=row(ema20=40, ema50=35, pivot_high=70,
                                    pivot_low=50, support50=30))
        self.assertEqual(plan.status, "NO_SETUP")
        self.assertIsNone(plan.entry_low)

    def test_very_volatile_stop_is_rejected(self):
        plan = calculate(values=row(atr=30, ema20=95, pivot_high=40, pivot_low=30,
                                    support50=40))
        self.assertEqual(plan.status, "NO_SETUP")

    def test_pepe_micro_price_has_nonzero_levels(self):
        tiny = {k: v * 1e-8 if k in (
            "open", "high", "low", "close", "atr", "pivot_high", "pivot_low",
            "support50", "ema20", "ema50") else v for k, v in row().items()}
        plan = calculate(values=tiny)
        self.assertEqual(plan.status, "READY")
        self.assertTrue(all(math.isfinite(x) and x > 0 for x in (
            plan.entry_low, plan.entry_high, plan.stop_loss,
            plan.take_profit_1, plan.take_profit_2, plan.position_qty)))

    def test_risk_sizing_includes_fees_and_slippage_and_allocation_cap(self):
        plan = calculate()
        self.assertLessEqual(plan.estimated_risk, 100.0000001)
        self.assertLessEqual(plan.notional * 1.0015, 3000.0000001)
        self.assertAlmostEqual(plan.take_profit_1 - plan.entry_high,
                               1.5 * (plan.entry_high - plan.stop_loss))
        self.assertAlmostEqual(plan.take_profit_2 - plan.entry_high,
                               2.5 * (plan.entry_high - plan.stop_loss))

    def test_nearby_broken_resistance_used_as_retest(self):
        plan = calculate(values=row(pivot_high=99.6, ema20=98))
        self.assertIn("Retest", plan.anchor_name)

    def test_daily_does_not_require_separate_higher_timeframe(self):
        plan = calculate(values=row(higher_trend=0), timeframe="1d")
        self.assertEqual(plan.status, "READY")
        self.assertEqual(plan.next_check_at, CLOSED + timedelta(days=1))

    def test_invalid_time_and_parameters_rejected(self):
        with self.assertRaises(ValueError):
            calculate(timeframe="2h")
        with self.assertRaises(ValueError):
            plan_entry(row(), "1h", "BUY", CLOSED.replace(tzinfo=None),
                       capital=10000, risk_pct=1, max_allocation_pct=30,
                       fee_pct=.1, slippage_pct=.05)


if __name__ == "__main__":
    unittest.main()
