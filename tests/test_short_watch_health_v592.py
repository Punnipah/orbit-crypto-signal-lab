"""v5.9.2 independent Short Watch / Data Health, no private order capability."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from futures_data_health import classify, probe_catalog
from scalp_engine import ScalpSettings, evaluate_scalp
from scalp_marketdata import Instrument, MarketDataError, MarketSnapshot
from short_opportunity import evaluate_short_watch


NOW = datetime(2026, 11, 1, 12, 15, 20, tzinfo=timezone.utc)
INS = Instrument("PEPEUSDT", Decimal("1"), Decimal("1"), Decimal("1"), Decimal("0.00000001"))


def bearish(venue="BINANCE_TH_SPOT", with_hour=True):
    frames = {}
    for tf, step in (("1m", 1), ("5m", 5), ("15m", 15), ("1h", 60)):
        count = 65
        last_close = NOW.replace(second=0, microsecond=0)
        if tf == "5m":
            last_close = last_close.replace(minute=15)
        if tf == "15m":
            last_close = last_close.replace(minute=15)
        if tf == "1h":
            last_close = last_close.replace(minute=0)
        rows = []
        for i in range(count):
            t = last_close - timedelta(minutes=step * (count-i))
            c = 104.5 - i * (0.8 / count)
            # The independent, historical 1H band is 99-105; price is near top.
            rows.append({"open_ms": int(t.timestamp()*1000),
                         "open": c + .02, "high": 105 if tf == "1h" else c + .08,
                         "low": 99 if tf == "1h" else c - .08,
                         "close": c, "volume":100.0, "taker_buy":34.0})
        frames[tf] = pd.DataFrame(rows)
    if not with_hour:
        frames.pop("1h")
    return MarketSnapshot(venue, "PEPEUSDT", frames, 103.70, 103.72,
                          100_000., 100_000., INS, NOW)


class WatchTests(unittest.TestCase):
    def test_bearish_near_resistance_is_watch_only(self):
        snap = bearish()
        before = {key: frame.copy(deep=True) for key, frame in snap.frames.items()}
        result = evaluate_short_watch(snap)
        self.assertEqual(result.state, "SHORT_WATCH")
        self.assertGreaterEqual(sum(passed for _, passed, _ in result.checks), 3)
        self.assertFalse(hasattr(result, "entry"))
        self.assertFalse(hasattr(result, "stop"))
        self.assertFalse(hasattr(result, "tp1"))
        self.assertEqual(result.source_venue, "BINANCE_TH_SPOT")
        for key, frame in snap.frames.items():
            pd.testing.assert_frame_equal(frame, before[key])

    def test_short_watch_is_not_futures_signal_or_allowed_spot_short(self):
        result = evaluate_short_watch(bearish())
        self.assertNotEqual(result.state, "READY")
        self.assertNotEqual(result.state, "ZONE_READY")
        self.assertNotEqual(result.state, "SHORT")

    def test_missing_hour_cannot_reconstruct_structure_from_spot(self):
        result = evaluate_short_watch(bearish(with_hour=False))
        self.assertEqual(result.state, "INSUFFICIENT_DATA")

    def test_distant_price_never_short_watch(self):
        result = evaluate_short_watch(replace(bearish(), bid=94.98, ask=95.00))
        self.assertEqual(result.state, "NO_SETUP")

    def test_no_effect_on_existing_scalp_evaluator(self):
        snap = bearish()
        settings = ScalpSettings(("PEPEUSDT",), ("PEPEUSDT",))
        base = evaluate_scalp(snap, settings)
        evaluate_short_watch(snap)
        self.assertEqual(evaluate_scalp(snap, settings), base)


class HealthTests(unittest.TestCase):
    def test_futures_451_is_access_block_not_wait(self):
        state = classify("BINANCE_GLOBAL_USDM", "PEPEUSDT",
                         error="https://fapi.binance.com HTTP 451 (venue unavailable)", now=NOW)
        self.assertEqual(state.state, "ACCESS_BLOCKED")
        self.assertFalse(state.can_approve_short)
        self.assertIn("ไม่ใช้ราคา Spot แทน Futures", state.detail)

    def test_rate_limit_and_timeout_are_distinct(self):
        self.assertEqual(classify("BINANCE_GLOBAL_USDM", "PEPEUSDT",
                                  error="HTTP 429", now=NOW).state, "RATE_LIMITED")
        self.assertEqual(classify("BINANCE_GLOBAL_USDM", "PEPEUSDT",
                                  error="network/timeout", now=NOW).state, "NETWORK_ERROR")

    def test_catalog_only_is_not_trade_approved(self):
        with patch("futures_data_health.get_exchange_catalog", return_value={"PEPEUSDT": INS}):
            status = probe_catalog("BINANCE_GLOBAL_USDM", "PEPEUSDT")
        self.assertEqual(status.state, "API_REACHABLE")
        self.assertFalse(status.can_approve_short)

    def test_blocked_catalog_does_not_fallback(self):
        with patch("futures_data_health.get_exchange_catalog", side_effect=MarketDataError("HTTP 451")):
            status = probe_catalog("BINANCE_GLOBAL_USDM", "PEPEUSDT")
        self.assertEqual(status.state, "ACCESS_BLOCKED")

    def test_full_snapshot_venue_distinctions(self):
        spot = classify("BINANCE_TH_SPOT", "PEPEUSDT", snapshot=bearish(), now=NOW)
        bitget = classify("BITGET_USDT_FUTURES", "PEPEUSDT",
                          snapshot=bearish("BITGET_USDT_FUTURES"), now=NOW)
        futures = classify("BINANCE_GLOBAL_USDM", "PEPEUSDT",
                           snapshot=bearish("BINANCE_GLOBAL_USDM"), now=NOW)
        self.assertEqual(spot.state, "SPOT_ONLY")
        self.assertEqual(bitget.state, "FLOW_UNAVAILABLE")
        self.assertEqual(futures.state, "FUTURES_DATA_READY")
        self.assertFalse(spot.can_approve_short)
        self.assertFalse(bitget.can_approve_short)
        self.assertTrue(futures.can_approve_short)

    def test_stale_or_wrong_market_refused(self):
        self.assertEqual(classify("BINANCE_GLOBAL_USDM", "PEPEUSDT", snapshot=bearish(),
                                  now=NOW).state, "DATA_UNAVAILABLE")
        stale = replace(bearish("BINANCE_GLOBAL_USDM"), checked_at=NOW-timedelta(minutes=5))
        self.assertEqual(classify("BINANCE_GLOBAL_USDM", "PEPEUSDT", snapshot=stale,
                                  now=NOW).state, "STALE_DATA")


if __name__ == "__main__":
    unittest.main()
