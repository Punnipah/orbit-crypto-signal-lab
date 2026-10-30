"""Offline regression checks: two directions, timing, risk, events and config."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from futures_daytrade import (FuturesDataError, FuturesObservation, FuturesSettings, evaluate_futures,
                              parse_futures_klines, read_futures_settings)
from futures_daytrade_runner import empty_state, transition, validate_state


NOW = datetime(2026, 10, 30, 2, 7, tzinfo=timezone.utc)
SETTINGS = FuturesSettings(("PEPEUSDT", "BTCUSDT", "DOGEUSDT"))


def chart(tf: str, *, rising: bool, count=155) -> pd.DataFrame:
    minutes = {"15m": 15, "1h": 60, "4h": 240}[tf]
    latest_open = NOW - timedelta(minutes=minutes + 7)
    index = pd.date_range(end=latest_open, periods=count, freq=f"{minutes}min", tz="UTC")
    trend = 0.09 if rising else -0.09
    rows = []
    for i in range(count):
        price = 100 + i * trend
        rows.append({"open": price - trend * 0.5, "high": price + 0.2,
                     "low": price - 0.2, "close": price,
                     "volume": 100.0, "taker_buy": 53.0 if rising else 47.0})
    return pd.DataFrame(rows, index=index)


def base_frames(*, rising: bool):
    return {tf: chart(tf, rising=rising) for tf in ("15m", "1h", "4h")}


def breakout(frames, direction: str, *, last_index=-1):
    f = frames["15m"]
    i = len(f) + last_index
    prior = f.iloc[i - SETTINGS.breakout_lookback:i]
    if direction == "LONG":
        level = float(prior["high"].max())
        f.iloc[i, f.columns.get_loc("open")] = level - 0.02
        f.iloc[i, f.columns.get_loc("close")] = level + 0.20
        f.iloc[i, f.columns.get_loc("high")] = level + 0.25
        f.iloc[i, f.columns.get_loc("low")] = level - 0.06
        f.iloc[i, f.columns.get_loc("taker_buy")] = 150
    else:
        level = float(prior["low"].min())
        f.iloc[i, f.columns.get_loc("open")] = level + 0.02
        f.iloc[i, f.columns.get_loc("close")] = level - 0.20
        f.iloc[i, f.columns.get_loc("high")] = level + 0.06
        f.iloc[i, f.columns.get_loc("low")] = level - 0.25
        f.iloc[i, f.columns.get_loc("taker_buy")] = 50
    f.iloc[i, f.columns.get_loc("volume")] = 200
    return level


class FuturesCoreTests(unittest.TestCase):
    def evaluate(self, frames, *, last=110.0, mark=None, funding=0.01):
        return evaluate_futures("PEPEUSDT", frames, last=last,
                                mark=last if mark is None else mark,
                                funding_pct=funding, now=NOW, settings=SETTINGS)

    def test_rejects_no_volume_breakout(self):
        frames = base_frames(rising=True)
        result = self.evaluate(frames)
        self.assertEqual(result.state, "NO_SETUP")

    def test_long_watch_not_ready_on_first_breakout(self):
        frames = base_frames(rising=True)
        breakout(frames, "LONG")
        result = self.evaluate(frames, last=frames["15m"]["close"].iloc[-1])
        self.assertEqual(result.state, "WATCH_LONG")
        self.assertEqual(result.direction, "LONG")
        self.assertLess(result.stop, result.entry_low)
        self.assertLess(result.entry_high, result.tp1)
        self.assertLess(result.tp1, result.tp2)

    def test_short_watch_not_ready_on_first_breakout(self):
        frames = base_frames(rising=False)
        breakout(frames, "SHORT")
        result = self.evaluate(frames, last=frames["15m"]["close"].iloc[-1])
        self.assertEqual(result.state, "WATCH_SHORT")
        self.assertGreater(result.stop, result.entry_high)
        self.assertGreater(result.entry_low, result.tp1)
        self.assertGreater(result.tp1, result.tp2)

    def test_mark_dislocation_blocks(self):
        frames = base_frames(rising=True)
        breakout(frames, "LONG")
        self.assertEqual(self.evaluate(frames, last=100, mark=99).state, "RISK_BLOCK")

    def test_funding_risk_blocks(self):
        frames = base_frames(rising=False)
        breakout(frames, "SHORT")
        self.assertEqual(self.evaluate(frames, last=100, funding=0.4).state, "RISK_BLOCK")

    def test_conflicting_higher_timeframe_is_wait(self):
        frames = base_frames(rising=True)
        frames["4h"] = chart("4h", rising=False)
        breakout(frames, "LONG")
        self.assertEqual(self.evaluate(frames).state, "NO_TREND")

    def test_ready_requires_retest_and_live_price_in_zone(self):
        frames = base_frames(rising=True)
        level = breakout(frames, "LONG", last_index=-2)
        f = frames["15m"]
        i = -1
        for name, value in {"open": level + 0.02, "low": level - 0.01,
                            "high": level + 0.2, "close": level + 0.15,
                            "volume": 120, "taker_buy": 65}.items():
            f.iloc[i, f.columns.get_loc(name)] = value
        result = self.evaluate(frames, last=level + 0.10)
        self.assertEqual(result.state, "READY_LONG")
        self.assertLessEqual(result.risk_usdt, SETTINGS.capital_usdt * 0.005 + 1e-8)
        self.assertLessEqual(result.notional_usdt, SETTINGS.capital_usdt)
        self.assertGreaterEqual(result.net_rr_tp2, 2.0)
        escaped = self.evaluate(frames, last=level + 1.0)
        self.assertEqual(escaped.state, "WATCH_LONG")

    def test_short_ready_and_no_chasing_on_futures_price(self):
        frames = base_frames(rising=False)
        level = breakout(frames, "SHORT", last_index=-2)
        f = frames["15m"]
        for name, value in {"open": level - 0.02, "low": level - 0.20,
                            "high": level + 0.01, "close": level - 0.15,
                            "volume": 120, "taker_buy": 55}.items():
            f.iloc[-1, f.columns.get_loc(name)] = value
        ready = self.evaluate(frames, last=level - 0.10)
        self.assertEqual(ready.state, "READY_SHORT")
        self.assertLess(ready.tp2, ready.tp1)
        self.assertLess(ready.tp1, ready.entry_low)
        escaped = self.evaluate(frames, last=level - 1.0)
        self.assertEqual(escaped.state, "WATCH_SHORT")

    def test_invalidated_retest_blocks(self):
        frames = base_frames(rising=True)
        level = breakout(frames, "LONG", last_index=-2)
        f = frames["15m"]
        for key, value in {"open": level - 0.5, "low": level - 1.0,
                           "high": level - 0.1, "close": level - 0.8}.items():
            f.iloc[-1, f.columns.get_loc(key)] = value
        self.assertEqual(self.evaluate(frames, last=level - 0.8).state, "INVALIDATED")

    def test_config_loads_and_rejects_overrisk(self):
        actual = read_futures_settings(Path(__file__).resolve().parents[1] / "futures_daytrade_config.json")
        self.assertEqual(actual.symbols, ("PEPEUSDT", "BTCUSDT", "DOGEUSDT"))
        import json
        with tempfile.TemporaryDirectory() as folder:
            name = Path(folder) / "config.json"
            name.write_text(json.dumps({"symbols": ["BTCUSDT"], "risk_per_signal_pct": 20}))
            with self.assertRaises(ValueError):
                read_futures_settings(name)

    def test_closed_bars_and_staleness(self):
        rows = []
        opening = NOW - timedelta(minutes=15 * 150 + 7)
        for i in range(151):
            stamp = int((opening + timedelta(minutes=15 * i)).timestamp() * 1000)
            rows.append([stamp, "100", "101", "99", "100", "100", stamp + 899999,
                         "0", 0, "50", "0", "0"])
        frame = parse_futures_klines(rows, now=NOW, timeframe="15m")
        self.assertEqual(len(frame), 150)
        with self.assertRaises(FuturesDataError):
            parse_futures_klines(rows, now=NOW + timedelta(hours=2), timeframe="15m")

    def test_state_dedup_and_invalidated_notice(self):
        frames = base_frames(rising=True)
        breakout(frames, "LONG")
        watch = self.evaluate(frames, last=frames["15m"]["close"].iloc[-1])
        state = empty_state()
        transition(state, [watch])
        self.assertEqual(len(state["pending"]), 1)
        transition(state, [watch])
        self.assertEqual(len(state["pending"]), 1)
        invalid = FuturesObservation(watch.symbol, "INVALIDATED", "test", NOW,
                                     direction="LONG", setup_id=watch.setup_id)
        transition(state, [invalid])
        self.assertEqual(len(state["pending"]), 2)
        validate_state(state)

    def test_no_telegram_on_no_setup(self):
        state = empty_state()
        transition(state, [FuturesObservation("PEPEUSDT", "NO_SETUP", "no", NOW)])
        self.assertEqual(state["pending"], [])


if __name__ == "__main__":
    unittest.main()
