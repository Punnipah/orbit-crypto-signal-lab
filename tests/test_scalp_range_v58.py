"""Offline range-regime regression; fabricated fixtures, no claims of win rate."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import math
from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scalp_engine import ScalpSettings, _adx, evaluate_scalp, scalp_evidence, scalp_watch_zones
from scalp_marketdata import Instrument, MarketSnapshot


NOW = datetime(2026, 10, 31, 12, 17, 20, tzinfo=timezone.utc)
INST = Instrument("BTCUSDT", Decimal("0.001"), Decimal("0.001"), Decimal("5"), Decimal("0.01"))


def sideways(venue: str = "BINANCE_TH_SPOT", confirm: bool = True) -> MarketSnapshot:
    frames = {}
    for minutes, count in ((5, 100), (1, 100), (15, 100)):
        end = {5: "12:10", 1: "12:16", 15: "12:00"}[minutes]
        index = pd.date_range(end=f"2026-10-31 {end}:00+00:00", periods=count,
                              freq=f"{minutes}min")
        rows = []
        for j, t in enumerate(index):
            c = 100.0 + math.sin(j * .45) * 1.0
            rows.append(dict(open_ms=int(t.timestamp() * 1000), open=c - .015,
                             high=c + .13, low=c - .13, close=c,
                             volume=100., taker_buy=55.))
        frames[f"{minutes}m"] = pd.DataFrame(rows, index=index)
    # Last closed 5m candle tests bottom of prior oscillating range.
    f = frames["5m"]
    f.loc[f.index[-1], ["open", "high", "low", "close"]] = [99.15, 99.30, 98.88, 99.12]
    one = frames["1m"]
    one.loc[one.index[-1], ["open", "high", "low", "close", "volume", "taker_buy"]] = [
        99.05, 99.30, 99.01, 99.25, 200., 140. if confirm else float("nan")]
    return MarketSnapshot(venue, "BTCUSDT", frames, 99.24, 99.26, 100000., 100000., INST, NOW)


class RangeTests(unittest.TestCase):
    def test_three_watch_zones_exist_even_when_signal_waits(self):
        snap = sideways()
        zones = scalp_watch_zones(snap)
        self.assertEqual(len(zones), 3)
        self.assertTrue(all(z["low"] < z["high"] and z["low"] > 0 for z in zones))
        self.assertTrue(all(z["state"] in ("WATCH", "IN_ZONE", "INVALIDATED") for z in zones))
        # Rendering watch zones does not mutate or upgrade the signal state.
        self.assertEqual(scalp_watch_zones(snap), zones)

    def test_broken_support_is_not_a_buy_signal(self):
        snap = sideways()
        moved = replace(snap, ask=90.0, bid=89.99)
        zones = scalp_watch_zones(moved)
        self.assertTrue(any(z["state"] == "INVALIDATED" for z in zones))

    def settings(self) -> ScalpSettings:
        return ScalpSettings(("BTCUSDT",), ("BTCUSDT",), min_net_rr=1.5)

    def test_range_candidate_detected_not_breakout_wait(self):
        snap = sideways()
        self.assertLess(_adx(snap.frames["5m"]), 23)
        ob = evaluate_scalp(snap, self.settings())
        self.assertEqual(ob.strategy, "RANGE_REVERSAL", ob.reason)
        self.assertEqual(ob.market_regime, "SIDEWAYS")
        self.assertEqual(ob.state, "READY", ob.reason)
        self.assertLess(ob.stop, ob.entry)
        self.assertLess(ob.entry, ob.tp1)
        self.assertLess(ob.tp1, ob.tp2)
        self.assertGreaterEqual(ob.net_rr, self.settings().min_net_rr)
        self.assertLessEqual(ob.risk_usdt, .2 + 1e-8)

    def test_spot_no_range_short(self):
        snap = sideways()
        frame = snap.frames["1m"]
        frame.loc[frame.index[-1], ["open", "high", "low", "close"]] = [
            100.97, 101.10, 100.90, 100.99]
        five = snap.frames["5m"]
        five.loc[five.index[-1], ["open", "high", "low", "close"]] = [
            101.02, 101.15, 100.91, 100.99]
        ob = evaluate_scalp(replace(snap, bid=100.98, ask=101.00), self.settings())
        self.assertEqual(ob.state, "EXIT_WATCH", ob.reason)
        self.assertEqual(ob.side, "SELL")

    def test_missing_confirmed_fills_must_not_be_ready(self):
        ob = evaluate_scalp(sideways("BITGET_USDT_FUTURES", confirm=False), self.settings())
        self.assertNotEqual(ob.state, "READY")

    def test_disabling_range_keeps_original_breakout_engine(self):
        ob = evaluate_scalp(sideways(), replace(self.settings(), enable_range_scalp=False))
        self.assertEqual(ob.strategy, "TREND_BREAKOUT")

    def test_early_reversal_watch_is_advisory_not_buy(self):
        snap = sideways()
        frames = {tf: frame.copy() for tf, frame in snap.frames.items()}
        # 15m still bearish even though a 1m taker-buy recovery appears at support.
        fifteen = frames["15m"]
        for idx in range(len(fifteen)):
            price = 102.0 - idx * .025
            fifteen.iloc[idx, fifteen.columns.get_loc("close")] = price
        one = frames["1m"]
        one.iloc[-2, one.columns.get_loc("close")] = 99.0
        snap = replace(snap, frames=frames, bid=99.21, ask=99.28)
        ob = evaluate_scalp(snap, self.settings())
        self.assertIn("EARLY BUY WATCH", ob.early_reversal_note)
        self.assertIn("ยังไม่ใช่สัญญาณซื้อ", ob.early_reversal_note)
        self.assertNotEqual(ob.state, "EARLY_BUY")

    def test_one_tick_spread_for_low_price_pair_is_not_automatically_rejected(self):
        snap = sideways()
        scale = 5e-8
        frames = {tf: frame.copy() for tf, frame in snap.frames.items()}
        for frame in frames.values():
            for name in ("open", "high", "low", "close"):
                frame[name] *= scale
        bid = 99.24 * scale
        tick = Decimal("0.00000001")
        inst = Instrument("PEPEUSDT", Decimal("1"), Decimal("1"), Decimal("1"), tick)
        snap = replace(snap, symbol="PEPEUSDT", instrument=inst, frames=frames,
                       bid=bid, ask=bid + float(tick))
        self.assertGreater(snap.spread_bps, self.settings().max_spread_bps)
        ob = evaluate_scalp(snap, self.settings())
        self.assertNotIn("Spread หรือ ATR", ob.reason)
        self.assertTrue(any(name == "Spread" and passed
                            for name, passed, _ in scalp_evidence(snap, self.settings())))


if __name__ == "__main__":
    unittest.main()
