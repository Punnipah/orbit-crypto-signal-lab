"""Regression tests: observational-only near-ready, never future fabricated fills."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from near_ready_history import (GitHubNearReadyStore, decode, empty_history,
                                encode, merge, valid_event)
from near_ready_tracker import CHECKS, assess_zone, forward_excursions, near_candidates
from validation_runner import observation_row, run
from scalp_engine import ScalpObservation


STAMP = 1_760_000_000_000
MINUTE = 60_000
VENUE = "BINANCE_TH_SPOT"
SYMBOL = "PEPEUSDT"


def zone():
    return {"name": "โซน 1", "state": "IN_ZONE", "low": .0000049, "high": .0000050}


def decision(fail_index=3, state="WAIT_CONFIRM", side="LONG"):
    return SimpleNamespace(state=state, side=side,
                           checks=tuple((name, n != fail_index, "evidence")
                                        for n, name in enumerate(CHECKS)))


def near(t=STAMP):
    return assess_zone(zone(), decision(), observed_state="WAIT",
                       venue=VENUE, symbol=SYMBOL, timestamp_ms=t, quote=.00000495)


class NearCandidateTests(unittest.TestCase):
    def test_exactly_four_checks_is_watch_not_trade(self):
        event = near()
        self.assertEqual(event["st"], "NEAR_READY")
        self.assertEqual(event["fail"], "1m Volume")
        self.assertEqual(sum(event["checks"]), 4)
        self.assertTrue(valid_event(event))
        self.assertEqual(decode(encode({"schema": 1, "rows": [event]}))["rows"], [event])

    def test_risk_block_invalidated_ready_or_missing_two_rejected(self):
        self.assertIsNone(assess_zone(zone(), decision(), observed_state="RISK_BLOCK",
                                      venue=VENUE, symbol=SYMBOL, timestamp_ms=STAMP,
                                      quote=.00000495))
        for state in ("ZONE_READY", "RISK_BLOCK", "MISSED", "WAIT_PRICE", "DATA_UNAVAILABLE"):
            self.assertIsNone(assess_zone(zone(), decision(state=state), observed_state="WAIT",
                                          venue=VENUE, symbol=SYMBOL, timestamp_ms=STAMP,
                                          quote=.00000495))
        bad = SimpleNamespace(state="WAIT_CONFIRM", side="LONG",
                              checks=tuple((name, i not in (2, 3), "")
                                           for i, name in enumerate(CHECKS)))
        self.assertIsNone(assess_zone(zone(), bad, observed_state="WAIT",
                                      venue=VENUE, symbol=SYMBOL, timestamp_ms=STAMP,
                                      quote=.00000495))

    def test_spot_short_never_near_ready(self):
        self.assertIsNone(assess_zone(zone(), decision(side="SHORT"), observed_state="WAIT",
                                      venue=VENUE, symbol=SYMBOL, timestamp_ms=STAMP,
                                      quote=.00000495))

    def test_bitget_watch_only_never_near_ready(self):
        self.assertIsNone(assess_zone(zone(), decision(), observed_state="WAIT",
                                      venue="BITGET_USDT_FUTURES", symbol=SYMBOL,
                                      timestamp_ms=STAMP, quote=.00000495))

    def test_live_candidates_do_not_mutate_signal(self):
        stamp = datetime.fromtimestamp(STAMP / 1000, timezone.utc)
        ob = ScalpObservation(VENUE, SYMBOL, "WAIT", "wait", stamp)
        snap = SimpleNamespace(venue=VENUE, symbol=SYMBOL, ask=.00000495,
                               bid=.00000494)
        with patch("scalp_engine.scalp_watch_zones", return_value=[zone()]), \
             patch("zone_signal.evaluate_zone", return_value=decision()):
            events = near_candidates(snap, object(), ob)
        self.assertEqual(len(events), 1)
        self.assertEqual(ob.state, "WAIT")


class ArchiveTests(unittest.TestCase):
    def test_dedup_buckets_and_no_mutation_of_existing(self):
        now = datetime.fromtimestamp(STAMP / 1000, timezone.utc) + timedelta(minutes=3)
        state, n = merge(empty_history(), [near()], now)
        self.assertEqual(n, 1)
        state2, n2 = merge(state, [near(STAMP + 90_000)], now)
        self.assertEqual(n2, 0)
        self.assertEqual(state2, state)
        with self.assertRaises(ValueError):
            merge(state, [near(STAMP + 86_400_000)], now)

    def test_invalid_event_cannot_hide_failed_gate(self):
        event = near()
        event["checks"] = [True] * 5
        self.assertFalse(valid_event(event))

    def test_only_validation_history_branch_used(self):
        store = GitHubNearReadyStore("Sample/orbit", "fake-token", "a" * 40)
        calls = []

        def fake(method, path, body=None, *, missing_ok=False):
            calls.append((method, path, body))
            if method == "GET":
                return None
            if method == "POST":
                return {"ref": "refs/heads/orbit-validation-history"}
            return {"content": {"sha": "stored"}}

        day = datetime.fromtimestamp(STAMP / 1000, timezone.utc).date()
        with patch.object(store, "_request", side_effect=fake):
            state = store.load(day)
            state, _ = merge(state, [near()], datetime.fromtimestamp(STAMP / 1000,
                                                                      timezone.utc))
            self.assertTrue(store.save(state))
        put = next(c for c in calls if c[0] == "PUT")
        self.assertEqual(put[2]["branch"], "orbit-validation-history")
        self.assertIn("near-ready", put[1])


def candle_rows(t=STAMP, minutes=30, high=1.01, low=.995):
    """Construct a future-only, complete validation journal for deterministic tests."""
    start = (t // MINUTE + 1) * MINUTE
    rows = []
    for block in range(0, minutes, 5):
        bars = [[start + i * MINUTE, 1., high, low, 1.]
                for i in range(block, min(block + 5, minutes))]
        rows.append({"t": t + block * MINUTE, "v": VENUE, "s": SYMBOL,
                     "bars": bars})
    return rows


class ForwardTests(unittest.TestCase):
    def test_complete_30m_window_reports_gross_excursion_not_profit(self):
        event = near()
        event["p"] = 1.
        outcome = forward_excursions([event], candle_rows(), VENUE, SYMBOL)
        self.assertEqual(outcome[0]["state"], "OBSERVED_30M")
        self.assertEqual(outcome[0]["favorable_pct"], 1.)
        self.assertEqual(outcome[0]["adverse_pct"], .5)
        self.assertNotIn("net_usdt", outcome[0])

    def test_missing_future_bars_stays_pending(self):
        event = near()
        event["p"] = 1.
        outcome = forward_excursions([event], candle_rows(minutes=25), VENUE, SYMBOL)
        self.assertEqual(outcome[0]["state"], "PENDING_DATA")
        self.assertIsNone(outcome[0]["favorable_pct"])

    def test_non_contiguous_candles_do_not_claim_missed(self):
        event = near()
        event["p"] = 1.
        bars = candle_rows()
        bars[0]["bars"].pop()
        outcome = forward_excursions([event], bars, VENUE, SYMBOL)
        self.assertEqual(outcome[0]["state"], "PENDING_DATA")

    def test_duplicate_observations_count_once_per_half_hour(self):
        a = near()
        b = near(STAMP + MINUTE)
        for x in (a, b):
            x["p"] = 1.
        outcome = forward_excursions([a, b], candle_rows(), VENUE, SYMBOL)
        self.assertEqual(len(outcome), 1)

    def test_not_yet_observed_future_remains_pending(self):
        event = near()
        event["p"] = 1.
        outcome = forward_excursions([event], candle_rows(), VENUE, SYMBOL,
                                     observed_until_ms=STAMP + 10 * MINUTE)
        self.assertEqual(outcome[0]["state"], "PENDING_DATA")


if __name__ == "__main__":
    unittest.main()
