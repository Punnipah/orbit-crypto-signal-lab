"""Deterministic offline checks: a pump must never fabricate a buy signal."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase

import pandas as pd

from monitor_alerts import empty_state, remove_sent, serialize_state, transition
from monitor_engine import MonitorSettings, Observation
from rally_watch import RallySettings, evaluate_rally
from watch_plans import new_watch_plan


NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)


def make_plan():
    return new_watch_plan("PEPEUSDT",
                          SimpleNamespace(entry_low=100, entry_high=101,
                                          stop_loss=97, take_profit_1=110,
                                          take_profit_2=120),
                          now=NOW - timedelta(hours=2), hours=48)


def make_bars(close=105, *, last_volume=150):
    # 20 history candles before the lock + 8 after the lock.
    index = pd.date_range(end=NOW - timedelta(minutes=15), periods=28,
                          freq="15min", tz="UTC")
    bars = pd.DataFrame({"open": [100.] * 28, "high": [101.] * 28,
                         "low": [99.] * 28, "close": [100.] * 28,
                         "volume": [100.] * 28}, index=index)
    for i in (-2, -1):
        bars.iloc[i, bars.columns.get_loc("open")] = close - 1
        bars.iloc[i, bars.columns.get_loc("high")] = close + 1
        bars.iloc[i, bars.columns.get_loc("low")] = close - 2
        bars.iloc[i, bars.columns.get_loc("close")] = close
        bars.iloc[i, bars.columns.get_loc("volume")] = last_volume
    return bars


def evaluate(bars=None, price=105, **kwargs):
    defaults = {"now": NOW, "current_price": price, "frozen_status": "WAIT_ZONE",
                "context_ready": True}
    defaults.update(kwargs)
    return evaluate_rally(make_plan(), make_bars() if bars is None else bars, **defaults)


def obs(base_status="WAIT_ZONE", opportunity="NONE", **kwargs):
    row = Observation("PEPEUSDT", "FROZEN", base_status, NOW, 110., 85.,
                      "Public Futures", "NOT_ENTERED", "frozen wait",
                      watch_token="secret-plan-token", entry_low=100, entry_high=101,
                      stop_loss=97, tp1=110, tp2=120,
                      opportunity_status=opportunity,
                      opportunity_reason="two 15m candle closes", **kwargs)
    return row


class RallyPriceEvidenceTests(TestCase):
    def test_two_closed_candles_make_breakout_observation(self):
        result = evaluate()
        self.assertEqual(result.status, "BREAKOUT_WATCH")
        self.assertAlmostEqual(result.distance_pct, (105 / 101 - 1) * 100)
        self.assertGreaterEqual(result.volume_ratio, .8)

    def test_higher_price_is_missed_entry_not_new_buy(self):
        result = evaluate(make_bars(111), 111)
        self.assertEqual(result.status, "MISSED_ENTRY")
        self.assertIn("ไม่ไล่ซื้อ", result.reason)

    def test_one_spot_tick_above_zone_without_closed_candles_not_alerted(self):
        result = evaluate(make_bars(100), 120)
        self.assertEqual(result.status, "NONE")

    def test_low_volume_not_alerted(self):
        result = evaluate(make_bars(105, last_volume=10), 105)
        self.assertEqual(result.status, "NONE")

    def test_stale_candles_not_alerted(self):
        old = make_bars().copy()
        old.index = old.index - timedelta(hours=2)
        self.assertEqual(evaluate(old).status, "NONE")

    def test_incomplete_candle_cannot_complete_confirmation(self):
        bars = make_bars(100)
        last = bars.index[-1]
        bars.loc[last, ["open", "high", "low", "close", "volume"]] = [104, 106, 103, 105, 200]
        # Only one close over the threshold: spot does not rescue it.
        self.assertEqual(evaluate(bars, 105).status, "NONE")

    def test_rejects_bad_context_or_plan_no_longer_waiting(self):
        self.assertEqual(evaluate(context_ready=False).status, "NONE")
        self.assertEqual(evaluate(frozen_status="READY_NOW").status, "NONE")
        self.assertEqual(evaluate(frozen_status="EXPIRED").status, "NONE")
        self.assertEqual(evaluate(now=NOW + timedelta(days=3)).status, "NONE")

    def test_gap_in_last_two_candles_disables_alert(self):
        bars = make_bars()
        bars = bars.drop(index=bars.index[-2])
        self.assertEqual(evaluate(bars).status, "NONE")

    def test_candidate_requires_ready_and_non_chased_higher_zone(self):
        fresh = SimpleNamespace(entry_low=107, entry_high=109,
                                stop_loss=103, take_profit_1=114, take_profit_2=125)
        result = evaluate(make_bars(110), 110, live_mtf_ready=True, new_entry=fresh)
        self.assertEqual(result.status, "NEW_SETUP_CANDIDATE")
        self.assertEqual((result.new_entry_low, result.new_entry_high), (107, 109))
        self.assertEqual(evaluate(make_bars(110), 110, new_entry=fresh).status, "MISSED_ENTRY")
        self.assertEqual(evaluate(make_bars(111), 111, live_mtf_ready=True,
                                  new_entry=fresh).status, "MISSED_ENTRY")

    def test_invalid_new_plan_not_a_candidate(self):
        bogus = SimpleNamespace(entry_low=107, entry_high=109,
                                stop_loss=110, take_profit_1=114, take_profit_2=125)
        self.assertEqual(evaluate(make_bars(110), 110, live_mtf_ready=True,
                                  new_entry=bogus).status, "MISSED_ENTRY")

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            RallySettings(watch_above_zone_pct=9, missed_above_zone_pct=8).validate()
        with self.assertRaises(ValueError):
            MonitorSettings(("PEPEUSDT",), rally_confirmation_bars=1).rally_settings()


class RallyTelegramTransitionTests(TestCase):
    def test_two_stages_alert_once_each_no_wait_spam(self):
        state = empty_state()
        transition(state, [obs(opportunity="BREAKOUT_WATCH", opportunity_distance_pct=4.)])
        self.assertEqual([r["kind"] for r in state["pending"]], ["BREAKOUT_WATCH"])
        notice = state["pending"][0]["text"]
        self.assertIn("ไม่ไล่ซื้อ", notice)
        self.assertIn("100", notice)
        self.assertNotIn("secret-plan-token", serialize_state(state).decode())
        remove_sent(state, state["pending"][0]["id"])
        transition(state, [obs(opportunity="BREAKOUT_WATCH")])
        self.assertEqual(state["pending"], [])
        transition(state, [obs(opportunity="MISSED_ENTRY")])
        self.assertEqual([r["kind"] for r in state["pending"]], ["MISSED_ENTRY"])

    def test_pending_stale_rally_removed_if_price_returns_or_plan_expires(self):
        state = empty_state()
        transition(state, [obs(opportunity="BREAKOUT_WATCH")])
        transition(state, [obs(opportunity="NONE")])
        self.assertEqual(state["pending"], [])
        transition(state, [obs(opportunity="MISSED_ENTRY")])
        transition(state, [obs(base_status="EXPIRED")])
        self.assertEqual([r["kind"] for r in state["pending"]], ["EXPIRED"])

    def test_stale_stage_is_replaced_by_new_stage(self):
        state = empty_state()
        transition(state, [obs(opportunity="BREAKOUT_WATCH")])
        transition(state, [obs(opportunity="NEW_SETUP_CANDIDATE",
                               candidate_low=107, candidate_high=109)])
        self.assertEqual([r["kind"] for r in state["pending"]], ["NEW_SETUP_CANDIDATE"])

    def test_plan_change_restarts_only_new_plan_alerts(self):
        state = empty_state()
        transition(state, [obs(opportunity="BREAKOUT_WATCH")])
        modified = Observation(**{**obs(opportunity="BREAKOUT_WATCH").__dict__,
                                  "watch_token": "new-plan-token"})
        transition(state, [modified])
        self.assertEqual(len(state["pending"]), 1)
        self.assertEqual(state["pending"][0]["kind"], "BREAKOUT_WATCH")
        self.assertNotIn("new-plan-token", serialize_state(state).decode())


if __name__ == "__main__":
    import unittest
    unittest.main()
