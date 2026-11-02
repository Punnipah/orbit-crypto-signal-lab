"""Venue-native, closed-bar, non-executable institutional-style playbooks."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from institutional_radar import evaluate_institutional_radar
from test_spot_range_v594 import CFG, NOW, snapshot


class InstitutionalRadarV596Tests(unittest.TestCase):
    def test_closed_bar_low_sweep_is_watch_not_a_buy(self):
        result = evaluate_institutional_radar(snapshot(), CFG)
        self.assertEqual(result.playbooks[0].state, "SETUP_WATCH")
        self.assertEqual(result.playbooks[0].side, "LONG")
        self.assertLess(result.playbooks[0].stop, result.playbooks[0].entry)
        self.assertGreater(result.playbooks[0].target, result.playbooks[0].entry)
        self.assertNotIn("READY", result.playbooks[0].state)

    def test_sweep_watches_flow_gates(self):
        snap = snapshot()
        one = snap.frames["1m"].copy()
        one.loc[one.index[-3:], "taker_buy"] = 20
        result = evaluate_institutional_radar(replace(
            snap, frames={**snap.frames, "1m": one}), CFG)
        self.assertEqual(result.playbooks[0].state, "FLOW_BLOCK")

    def test_bitget_unknown_flow_must_not_be_invented(self):
        snap = replace(snapshot(), venue="BITGET_USDT_FUTURES", flow_reconciled=False)
        result = evaluate_institutional_radar(snap, CFG)
        self.assertIsNone(result.evidence.recent_taker_buy_share)
        self.assertEqual(result.playbooks[0].state, "FLOW_BLOCK")

    def test_stale_snapshot_blocks_all_playbooks(self):
        result = evaluate_institutional_radar(snapshot(), CFG, now=NOW+timedelta(minutes=2))
        self.assertTrue(all(x.state == "DATA_BLOCK" for x in result.playbooks))

    def test_future_bar_cannot_trigger(self):
        snap = snapshot()
        five = snap.frames["5m"].copy()
        five.loc[five.index[-1], "open_ms"] += 300_000
        result = evaluate_institutional_radar(replace(
            snap, frames={**snap.frames, "5m": five}), CFG)
        self.assertTrue(all(x.state == "DATA_BLOCK" for x in result.playbooks))

    def test_single_depth_snapshot_is_only_a_proxy(self):
        result = evaluate_institutional_radar(snapshot(), CFG)
        self.assertIn("ไม่ใช่ L2 OFI", result.evidence.explanation)
        self.assertAlmostEqual(result.evidence.bid_depth_share, .5)

    def test_spot_high_sweep_is_exit_watch_never_short(self):
        snap = snapshot()
        five = snap.frames["5m"].copy()
        resistance = five.high.iloc[-21:-1].max()
        five.loc[five.index[-1], ["open", "high", "low", "close", "volume"]] = [
            resistance + .15, resistance + .4, resistance - .25, resistance - .15, 230]
        one = snap.frames["1m"].copy()
        one.loc[one.index[-1], ["open", "high", "low", "close"]] = [
            resistance - .12, resistance - .09, resistance - .2, resistance - .15]
        changed = replace(snap, bid=resistance-.16, ask=resistance-.14,
                          frames={**snap.frames, "5m": five, "1m": one})
        result = evaluate_institutional_radar(changed, CFG)
        self.assertEqual(result.playbooks[0].state, "EXIT_WATCH")
        self.assertEqual(result.playbooks[0].side, "SELL")

    def test_breakout_retest_is_distinct_playbook(self):
        snap = snapshot()
        five = snap.frames["5m"].copy()
        roof = float(five.high.iloc[-22:-2].max())
        five.loc[five.index[-2], ["open", "high", "low", "close", "volume"]] = [
            roof-.10, roof+.5, roof-.2, roof+.35, 220]
        five.loc[five.index[-1], ["open", "high", "low", "close", "volume"]] = [
            roof+.03, roof+.27, roof-.08, roof+.20, 180]
        one = snap.frames["1m"].copy()
        one.loc[one.index[-1], ["open", "high", "low", "close"]] = [
            roof+.15, roof+.25, roof+.12, roof+.20]
        changed = replace(snap, bid=roof+.19, ask=roof+.21,
                          frames={**snap.frames, "5m": five, "1m": one})
        result = evaluate_institutional_radar(changed, CFG)
        self.assertEqual(result.playbooks[1].side, "LONG")
        self.assertIn(result.playbooks[1].state, ("SETUP_WATCH", "COST_BLOCK"))

    def test_vwap_reclaim_is_separate_playbook(self):
        snap = snapshot()
        five = snap.frames["5m"].copy()
        five.loc[five.index[-2], ["open", "high", "low", "close", "volume"]] = [
            100.8, 101.0, 100.5, 100.6, 100]
        five.loc[five.index[-1], ["open", "high", "low", "close", "volume"]] = [
            100.7, 101.7, 100.6, 101.6, 200]
        one = snap.frames["1m"].copy()
        one.loc[one.index[-1], ["open", "high", "low", "close"]] = [
            101.4, 101.7, 101.3, 101.6]
        changed = replace(snap, bid=101.59, ask=101.61,
                          frames={**snap.frames, "5m": five, "1m": one})
        result = evaluate_institutional_radar(changed, CFG)
        self.assertEqual(result.playbooks[2].side, "LONG")
        self.assertNotEqual(result.playbooks[2].state, "NO_SETUP")

    def test_risk_config_never_mutated(self):
        before = repr(CFG)
        evaluate_institutional_radar(snapshot(), CFG)
        self.assertEqual(repr(CFG), before)


if __name__ == "__main__":
    unittest.main()
