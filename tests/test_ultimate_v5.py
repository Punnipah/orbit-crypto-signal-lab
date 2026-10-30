"""v5: multiplier safety, no retroactive paper fills, risk-first outcomes, state migration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from futures_daytrade import FuturesObservation
from futures_daytrade_runner import empty_state, validate_state
from futures_paper import empty_paper, paper_stats, update_paper
from futures_symbols import resolve_futures_pair
from futures_research import evaluate_historical_proxy
from futures_daytrade import FuturesSettings


NOW = datetime(2026, 10, 30, 10, 1, tzinfo=timezone.utc)


def ready(symbol="1000PEPEUSDT", side="LONG"):
    return FuturesObservation(symbol, "READY_" + side, "retest", NOW, direction=side,
                              setup_id="LONG:2026-10-30T10:00:00+00:00" if side == "LONG" else "SHORT:t0",
                              entry_low=99 if side == "LONG" else 101,
                              entry_high=100 if side == "LONG" else 102,
                              stop=95 if side == "LONG" else 106,
                              tp1=105 if side == "LONG" else 96,
                              tp2=110 if side == "LONG" else 91)


def candle(opened: datetime, *, low: float, high: float, close: float):
    return pd.DataFrame([{"open": 100, "high": high, "low": low, "close": close}],
                        index=pd.DatetimeIndex([opened]))


class SymbolSafetyTests(unittest.TestCase):
    def test_pepe_is_not_assumed_same_exchange_price(self):
        pair = resolve_futures_pair("PEPEUSDT", {"1000PEPEUSDT", "BTCUSDT"})
        self.assertEqual(pair.contract, "1000PEPEUSDT")
        self.assertEqual(pair.multiplier, 1000)
        self.assertAlmostEqual(pair.unit_price(0.004), 0.000004)

    def test_exact_and_unavailable_symbols(self):
        self.assertEqual(resolve_futures_pair("BTCUSDT", {"BTCUSDT"}).multiplier, 1)
        with self.assertRaises(ValueError):
            resolve_futures_pair("PEPEUSDT", {"DOGEUSDT"})
        with self.assertRaises(ValueError):
            resolve_futures_pair("PEPEUSDT", {"1000PEPEUSDT", "10000PEPEUSDT"})


class PaperTrackingTests(unittest.TestCase):
    def test_ready_is_not_assumed_entry_and_old_wick_ignored(self):
        ledger = empty_paper()
        ob = ready()
        self.assertEqual(update_paper(ledger, [ob], {}, NOW), [])
        self.assertIsNone(ledger["active"][ob.symbol]["entry_at"])
        older = candle(datetime(2026, 10, 30, 10, tzinfo=timezone.utc),
                       low=90, high=115, close=100)
        self.assertEqual(update_paper(ledger, [], {ob.symbol: older}, NOW + timedelta(minutes=17)), [])
        self.assertIsNone(ledger["active"][ob.symbol]["entry_at"])

    def test_next_bar_fill_then_stop_first_with_both_target_and_stop(self):
        ledger, ob = empty_paper(), ready()
        update_paper(ledger, [ob], {}, NOW, requested_by_contract={ob.symbol: "PEPEUSDT"})
        after = NOW.replace(minute=15)
        e1 = update_paper(ledger, [], {ob.symbol: candle(after, low=99.5, high=101, close=100)},
                          NOW + timedelta(minutes=31))
        self.assertEqual([x["text"].split("\n")[0] for x in e1], ["🪐 Orbit FUTURES PAPER · PAPER_ENTRY"])
        self.assertIsNotNone(ledger["active"][ob.symbol]["entry_at"])
        e2 = update_paper(ledger, [], {ob.symbol: pd.concat([
            candle(after, low=99.5, high=101, close=100),
            candle(after + timedelta(minutes=15), low=94, high=111, close=100)]).sort_index()},
            NOW + timedelta(minutes=46))
        self.assertEqual(len(e2), 1)
        self.assertEqual(ledger["history"][0]["status"], "STOP")
        self.assertLess(ledger["history"][0]["net_r_estimate"], 0)
        self.assertEqual(ledger["history"][0]["requested"], "PEPEUSDT")
        self.assertEqual(paper_stats(ledger["history"])["trades"], 1)
        update_paper(ledger, [ob], {}, NOW + timedelta(hours=2))
        self.assertEqual(ledger["active"], {})  # Same setup never resurrects.

    def test_short_and_later_target(self):
        ledger, ob = empty_paper(), ready("BTCUSDT", "SHORT")
        update_paper(ledger, [ob], {}, NOW)
        start = NOW.replace(minute=15)
        c1 = candle(start, low=100, high=101.5, close=101)
        update_paper(ledger, [], {ob.symbol: c1}, NOW + timedelta(minutes=31))
        c2 = candle(start + timedelta(minutes=15), low=90, high=101, close=93)
        update_paper(ledger, [], {ob.symbol: pd.concat([c1, c2]).sort_index()},
                     NOW + timedelta(minutes=46))
        self.assertEqual(ledger["history"][0]["status"], "TP2")
        self.assertGreater(ledger["history"][0]["net_r_estimate"], 0)

    def test_gap_makes_no_unsupported_result(self):
        ledger, ob = empty_paper(), ready()
        update_paper(ledger, [ob], {}, NOW)
        late = candle(NOW.replace(minute=30), low=90, high=115, close=100)
        self.assertEqual(update_paper(ledger, [], {ob.symbol: late}, NOW + timedelta(hours=2)), [])
        self.assertEqual(ledger["history"], [])

    def test_schema2_and_legacy_migration_shape(self):
        s = empty_state()
        validate_state(s)
        self.assertEqual(s["schema"], 2)
        validate_state({"schema": 1, "signals": {}, "sent": [], "pending": []})


class FuturesResearchTests(unittest.TestCase):
    def test_historical_proxy_never_reads_unclosed_higher_timeframe(self):
        beginning = datetime(2026, 9, 1, tzinfo=timezone.utc)
        frames = {}
        for tf, freq, count in (("15m", "15min", 1920), ("1h", "1h", 480), ("4h", "4h", 120)):
            idx = pd.date_range(beginning, periods=count, freq=freq, tz="UTC")
            frames[tf] = pd.DataFrame({"open": 100., "high": 101., "low": 99.,
                                       "close": 100., "volume": 50., "taker_buy": 25.}, index=idx)
        seen = []

        def no_future(symbol, data, *, last, mark, funding_pct, now, settings):
            for tf, mins in (("15m", 15), ("1h", 60), ("4h", 240)):
                self.assertLessEqual(data[tf].index[-1].to_pydatetime() + timedelta(minutes=mins), now)
            seen.append(now)
            return FuturesObservation(symbol, "NO_SETUP", "test", now)

        with patch("futures_research.evaluate_futures", side_effect=no_future):
            report = evaluate_historical_proxy("BTCUSDT", frames, FuturesSettings(("BTCUSDT",)))
        self.assertGreater(len(seen), 20)
        self.assertEqual(report.all_stats["trades"], 0)
        self.assertIn("PROXY", report.limitations)


if __name__ == "__main__":
    unittest.main()
