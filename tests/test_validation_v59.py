"""Deterministic temporal tests; do NOT imply a live trading backtest."""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import gzip
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scalp_engine import ScalpObservation, ScalpSettings, evaluate_scalp
from test_scalp_range_v58 import sideways
from validation_history import (GitHubValidationStore, day_path, decode_history,
                                empty_history, encode_history, merge_history, valid_row)
from validation_logic import (collect_bars, missed_opportunities, performance,
                              replay_all, replay_ready, unique_ready, walk_forward_report)
from validation_runner import observation_row, run


MINUTE = 60_000
STAMP = 1_760_000_000_000


def sample(state="READY", *, t=STAMP, side="LONG", id="setup-a", price=100.0):
    return {"t": t, "v": "BINANCE_TH_SPOT", "s": "BTCUSDT", "st": state,
            "sd": side, "id": id, "why": "sample", "p": price, "e": 100.0,
            "sl": 99.0, "tp1": 101.0, "tp2": 102.0, "tp10": None,
            "tp10_state": "NOT_APPLICABLE", "qty": 1.0, "risk": 1.0,
            "fee": .1, "slip": .05, "spread": 10.0,
            "regime": "SIDEWAYS", "strategy": "RANGE_SCALP", "bars": []}


def next_bar(t=STAMP, *, high=100.5, low=99.5, opened=100.0, close=100.0):
    start = (t // MINUTE + 1) * MINUTE
    return [start, opened, high, low, close]


class ArchiveTests(unittest.TestCase):
    def test_valid_observation_from_unchanged_engine_and_roundtrip(self):
        snap = sideways()
        cfg = ScalpSettings(("BTCUSDT",), ("BTCUSDT",))
        ob = evaluate_scalp(snap, cfg)
        before = ob
        row = observation_row(ob, snap, cfg)
        self.assertTrue(valid_row(row))
        self.assertEqual(evaluate_scalp(snap, cfg), before)
        state = {"schema": 1, "rows": [row]}
        self.assertEqual(decode_history(encode_history(state)), state)

    def test_missing_venue_never_fabricates_ohlc_or_trade(self):
        ob = ScalpObservation("BINANCE_GLOBAL_USDM", "PEPEUSDT",
                              "DATA_UNAVAILABLE", "HTTP 451", datetime.now(timezone.utc))
        row = observation_row(ob)
        self.assertTrue(valid_row(row))
        self.assertEqual(row["bars"], [])
        self.assertIsNone(row["p"])

    def test_same_bucket_dedup_and_recovers_verified_data(self):
        now = datetime.fromtimestamp(STAMP / 1000, timezone.utc) + timedelta(minutes=4)
        original = sample("DATA_UNAVAILABLE")
        original["p"] = None
        original["bars"] = []
        updated, changes = merge_history(empty_history(), [original], now)
        self.assertEqual(changes, 1)
        updated, changes = merge_history(updated, [sample()], now)
        self.assertEqual(changes, 1)
        self.assertEqual(updated["rows"][0]["st"], "READY")
        updated, changes = merge_history(updated, [original], now)
        self.assertEqual(changes, 0)
        with self.assertRaises(ValueError):
            merge_history(updated, [sample(t=STAMP + 86_400_000)], now)

    def test_corrupt_archive_rejected_and_day_path_is_date_scoped(self):
        with self.assertRaises(ValueError):
            decode_history(gzip.compress(b'{"schema":2,"rows":[]}'))
        self.assertIn("2026-11-01.json.gz", day_path(date(2026, 11, 1)))

    def test_separate_branch_never_writes_main(self):
        store = GitHubValidationStore("Example/orbit", "token", "a" * 40)
        calls = []

        def fake_request(method, path, body=None, *, missing_ok=False):
            calls.append((method, path, body))
            if method == "GET":
                return None
            if method == "POST":
                return {"ref": "refs/heads/orbit-validation-history"}
            return {"content": {"sha": "newsha"}}

        row = sample()
        day = datetime.fromtimestamp(row["t"] / 1000, timezone.utc).date()
        with patch.object(store, "_request", side_effect=fake_request):
            self.assertEqual(store.load(day), empty_history())
            self.assertTrue(store.save({"schema": 1, "rows": [row]}))
            self.assertFalse(store.save({"schema": 1, "rows": [row]}))
        self.assertEqual(len([x for x in calls if x[0] == "PUT"]), 1)
        self.assertEqual([x for x in calls if x[0] == "PUT"][0][2]["branch"],
                         "orbit-validation-history")


class PaperReplayTests(unittest.TestCase):
    def test_stop_first_when_same_future_minute_hits_tp_and_sl(self):
        result = replay_ready(sample(), [next_bar(high=102.0, low=98.0)])
        self.assertEqual(result["state"], "PAPER_STOP")
        self.assertTrue(result["ambiguous_stop_first"])
        self.assertLess(result["net_usdt"], -1.0)

    def test_past_bar_cannot_trigger_post_signal_tp(self):
        past = [STAMP // MINUTE * MINUTE, 100., 120., 80., 100.]
        future = next_bar(high=100.5, low=99.5)
        result = replay_ready(sample(), [past, future])
        self.assertEqual(result["state"], "PENDING_OUTCOME")

    def test_next_open_gap_refuses_hypothetical_fill(self):
        result = replay_ready(sample(), [next_bar(opened=103, high=104, low=102)])
        self.assertEqual(result["state"], "NOT_FILLED_PRICE_GAP")
        self.assertIsNone(result["net_usdt"])

    def test_missing_bar_refuses_profit_or_loss(self):
        first = next_bar()
        gap = [first[0] + 2 * MINUTE, 100., 103., 99.8, 102.]
        result = replay_ready(sample(), [first, gap])
        self.assertEqual(result["state"], "INCOMPLETE_1M_DATA")
        self.assertIsNone(result["net_usdt"])

    def test_complete_sixty_minutes_can_time_exit_after_costs(self):
        first = next_bar()
        candles = [[first[0] + i * MINUTE, 100., 100.5, 99.5, 100.]
                   for i in range(60)]
        result = replay_ready(sample(), candles)
        self.assertEqual(result["state"], "PAPER_TIME_EXIT")
        self.assertLess(result["net_usdt"], 0)

    def test_tp_first_on_separate_minute_is_modeled_as_profit(self):
        bar = next_bar(high=101.1, low=99.9)
        result = replay_ready(sample(), [bar])
        self.assertEqual(result["state"], "PAPER_TP")
        self.assertGreater(result["net_usdt"], 0)
        self.assertFalse(result["ambiguous_stop_first"])

    def test_approved_pepe_ten_points_is_separate_target(self):
        r = sample()
        r["s"] = "PEPEUSDT"
        r["tp10"] = 101.
        r["tp10_state"] = "ALTERNATIVE_READY"
        outcome = replay_ready(r, [next_bar(high=101.1, low=99.9)], target="tp10")
        self.assertEqual(outcome["state"], "PAPER_TP")

    def test_non_approved_pepe_ten_points_not_counted(self):
        r = sample()
        r["s"] = "PEPEUSDT"
        self.assertEqual(replay_ready(r, [next_bar()], target="tp10")["state"],
                         "ALTERNATIVE_TP_BLOCK")

    def test_repeated_ready_same_setup_counts_as_one_candidate(self):
        rows = [sample(t=STAMP), sample(t=STAMP + 300_000)]
        self.assertEqual(len(unique_ready(rows)), 1)

    def test_no_venue_substitution_and_conflicts_block_replay(self):
        r = sample("WAIT")
        b = next_bar()
        r["bars"] = [b]
        s = dict(r, t=r["t"] + 300_000, bars=[[b[0], 101, 102, 100, 101]])
        with self.assertRaises(ValueError):
            collect_bars([r, s], "BINANCE_TH_SPOT", "BTCUSDT")
        self.assertEqual(collect_bars([r], "BITGET_USDT_FUTURES", "BTCUSDT"), [])

    def test_missed_watch_requires_direction_and_thirty_real_bars(self):
        r = sample("WATCH")
        start = next_bar()[0]
        other = dict(r, t=r["t"] + 5 * MINUTE, st="WAIT", id="other")
        other["bars"] = []
        # History is captured as closing blocks of <=7 1m bars.
        rows = [r, other]
        for offset in range(0, 30, 5):
            z = dict(r, t=r["t"] + offset * MINUTE, id=f"bar{offset}",
                     bars=[[start + j * MINUTE, 100., 102., 99., 100.]
                           for j in range(offset, min(offset + 5, 30))])
            rows.append(z)
        opportunities = missed_opportunities(rows, "BINANCE_TH_SPOT", "BTCUSDT")
        self.assertTrue(any(r["favorable_pct"] >= 1.9 for r in opportunities))

    def test_performance_not_fabricated_and_walkforward_is_chronological(self):
        self.assertEqual(performance([])["n"], 0)
        self.assertEqual(walk_forward_report([]), [])
        results = []
        for i in range(23):
            results.append({"t": STAMP + i * 86_400_000, "net_usdt": 1 if i < 7 else -1,
                            "net_r": 1 if i < 7 else -1})
        report = walk_forward_report(results)
        self.assertTrue(report)
        self.assertLess(report[0]["test_avg_r"], report[0]["train_avg_r"])


class CollectorTests(unittest.TestCase):
    def test_dry_run_cannot_write_github(self):
        with patch("validation_runner.scan", return_value=[]), \
             patch("validation_runner.GitHubValidationStore") as store:
            self.assertEqual(run(record=False), 2)
            store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
