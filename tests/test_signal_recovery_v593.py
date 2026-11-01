"""v5.9.3 fail-closed directional-flow recovery and pullback regression."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from futures_data_health import classify
from scalp_bitget import HISTORY_ROUTE, _history_fills, reconcile_recent_fills
from scalp_engine import (_pullback_rejection_5m, _setup_5m, evaluate_scalp)
from test_scalp_v56 import NOW, SETTINGS, frame, snapshot


class PublicFlowRecoveryTests(unittest.TestCase):
    def _trade(self, timestamp, size, side, identity):
        return {"ts": str(timestamp), "size": str(size), "side": side,
                "tradeId": str(identity), "symbol": "BTCUSDT"}

    def test_history_uses_published_read_only_route(self):
        stamp = int(NOW.timestamp() * 1000)
        trades = [self._trade(stamp - 140_000, 1, "Buy", 1),
                  self._trade(stamp - 20_000, 1, "Sell", 2)]
        with patch("scalp_bitget._api", return_value=trades) as api:
            result = _history_fills("BTCUSDT", NOW)
        self.assertEqual(result, trades)
        args, _ = api.call_args
        self.assertEqual(args[0], HISTORY_ROUTE)
        self.assertEqual(args[1]["productType"], "USDT-FUTURES")
        self.assertEqual(args[1]["limit"], 1000)
        self.assertNotIn("apiKey", args[1])

    def test_history_requires_correct_symbol_and_cursor(self):
        with patch("scalp_bitget._api", return_value=[{**self._trade(1, 1, "buy", 1),
                                                       "symbol": "ETHUSDT"}]):
            with self.assertRaisesRegex(Exception, "symbol"):
                _history_fills("BTCUSDT", NOW)

    def test_history_bounded_pagination_uses_public_cursor(self):
        stamp = int(NOW.timestamp() * 1000)
        first_page = [self._trade(stamp - i * 20, 1, "Sell", 2000-i)
                      for i in range(1000)]
        older_page = [self._trade(stamp - 150_000, 1, "Buy", 500)]
        with patch("scalp_bitget._api", side_effect=[first_page, older_page]) as api:
            result = _history_fills("BTCUSDT", NOW)
        self.assertEqual(len(result), 1001)
        self.assertEqual(api.call_count, 2)
        self.assertEqual(api.call_args_list[1].args[1]["idLessThan"], "1001")

    def test_v2_case_and_duplicate_ids_do_not_inflate_volume(self):
        f = frame("1m")
        f["taker_buy"] = float("nan")
        opened = int(f.open_ms.iloc[-2])
        trades = [self._trade(opened - 1, 1, "Sell", "before"),
                  self._trade(opened + 500, 60, "Buy", "buy"),
                  self._trade(opened + 2500, 40, "Sell", "sell"),
                  self._trade(opened + 2500, 40, "Sell", "sell"),
                  self._trade(opened + 60_001, 1, "Buy", "after")]
        self.assertEqual(reconcile_recent_fills(f, trades, NOW), 1)
        self.assertEqual(float(f.taker_buy.iloc[-2]), 60)

    def test_partial_or_wrong_volume_never_creates_flow(self):
        f = frame("1m")
        f["taker_buy"] = float("nan")
        opened = int(f.open_ms.iloc[-2])
        partial = [self._trade(opened + 400, 50, "Sell", 1),
                   self._trade(opened + 60_001, 1, "Buy", 2)]
        self.assertEqual(reconcile_recent_fills(f, partial, NOW), 0)
        self.assertTrue(f.taker_buy.isna().all())

    def test_health_only_certifies_verified_source(self):
        snap = snapshot(venue="BITGET_USDT_FUTURES")
        unverified = classify("BITGET_USDT_FUTURES", "BTCUSDT", snapshot=snap, now=NOW)
        self.assertEqual(unverified.state, "FLOW_UNAVAILABLE")
        verified = classify("BITGET_USDT_FUTURES", "BTCUSDT",
                            snapshot=replace(snap, flow_reconciled=True), now=NOW)
        self.assertEqual(verified.state, "FUTURES_FLOW_VERIFIED")
        self.assertTrue(verified.can_approve_short)


class PullbackSafetyTests(unittest.TestCase):
    def _pullback_snapshot(self, *, trigger=True):
        snap = snapshot(venue="BINANCE_GLOBAL_USDM", rising=False,
                        breakout=False, trigger=trigger, quote=103.04)
        frames = {key: val.copy(deep=True) for key, val in snap.frames.items()}
        five = frames["5m"]
        i = len(five) - 1
        five.iloc[i, five.columns.get_loc("open")] = 103.19
        five.iloc[i, five.columns.get_loc("close")] = 103.10
        five.iloc[i, five.columns.get_loc("high")] = 103.22
        five.iloc[i, five.columns.get_loc("low")] = 103.07
        five.iloc[i, five.columns.get_loc("volume")] = 200
        return replace(snap, frames=frames)

    def test_closed_rejection_is_not_a_breakout(self):
        snap = self._pullback_snapshot()
        five = snap.frames["5m"]
        self.assertIsNone(_setup_5m(five, "SHORT", SETTINGS, NOW))
        self.assertIsNotNone(_pullback_rejection_5m(five, "SHORT", SETTINGS, NOW))

    def test_verified_rejection_can_become_short_with_original_risk(self):
        ob = evaluate_scalp(self._pullback_snapshot(), SETTINGS)
        self.assertEqual(ob.strategy, "PULLBACK_REJECTION", ob.reason)
        self.assertEqual(ob.state, "READY", ob.reason)
        self.assertEqual(ob.side, "SHORT")
        self.assertGreater(ob.stop, ob.entry)
        self.assertLess(ob.tp2, ob.entry)
        self.assertGreaterEqual(ob.net_rr, SETTINGS.min_net_rr)
        self.assertLessEqual(ob.risk_usdt, SETTINGS.capital_usdt *
                             SETTINGS.risk_per_trade_pct / 100 + .00001)

    def test_without_closed_1m_volume_confirmation_cannot_be_ready(self):
        ob = evaluate_scalp(self._pullback_snapshot(trigger=False), SETTINGS)
        self.assertEqual(ob.strategy, "PULLBACK_REJECTION", ob.reason)
        self.assertNotEqual(ob.state, "READY")

    def test_price_chasing_is_still_blocked(self):
        snap = self._pullback_snapshot()
        farther = replace(snap, bid=snap.bid * .985, ask=snap.ask * .985)
        ob = evaluate_scalp(farther, SETTINGS)
        self.assertEqual(ob.state, "RISK_BLOCK")


if __name__ == "__main__":
    unittest.main()
