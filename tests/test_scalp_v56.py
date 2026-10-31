"""v5.6 offline regression: venue separation, candle integrity, risk, alerts."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scalp_alerts import empty_state, send_pending, serialise_state, transition, validate_state
from scalp_engine import ScalpObservation, _short_term_direction, evaluate_scalp, read_scalp_settings
from scalp_marketdata import (Instrument, MarketDataError, MarketSnapshot, fetch_snapshot,
                              get_exchange_catalog, parse_closed_klines, parse_depth, parse_quote)
from scalp_runner import scan
from scalp_bitget import get_bitget_catalog, parse_bitget_candles, reconcile_recent_fills
from scalp_research import summarise_volatility


NOW = datetime(2026, 10, 31, 0, 17, 20, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]
SETTINGS = read_scalp_settings(ROOT / "scalp_config.json")
INSTRUMENT = Instrument("BTCUSDT", Decimal("0.00001"), Decimal("0.00001"),
                        Decimal("5"), Decimal("0.01"))


def frame(tf: str, *, rising=True, breakout=False, trigger=False) -> pd.DataFrame:
    period = {"15m": 15, "5m": 5, "1m": 1}[tf]
    last_open = {"15m": NOW.replace(minute=0, second=0),
                 "5m": NOW.replace(minute=10, second=0),
                 "1m": NOW.replace(minute=16, second=0)}[tf]
    index = pd.date_range(end=last_open, periods=110, freq=f"{period}min", tz="UTC")
    direction = 1 if rising else -1
    trend = 0.04 if tf == "15m" else 0.008 if tf == "5m" else 0.002
    start = 100 if tf == "15m" else 104 if tf == "5m" else (105 if rising else 103.2)
    rows = []
    for i, opened in enumerate(index):
        mid = start + direction * i * trend
        o, c = mid - 0.02, mid
        h, l = max(o, c) + 0.06, min(o, c) - 0.06
        rows.append({"open_ms": int(opened.timestamp() * 1000), "open": o, "high": h,
                     "low": l, "close": c, "volume": 100.0, "taker_buy": 60.0 if rising else 40.0})
    f = pd.DataFrame(rows, index=index)
    if tf == "5m" and breakout:
        i = len(f) - 1
        previous = f.iloc[i - SETTINGS.setup_lookback_5m:i]
        level = float(previous.high.max()) if rising else float(previous.low.min())
        c = level + direction * 0.16
        o = level - direction * 0.03
        f.iloc[i, f.columns.get_loc("open")] = o
        f.iloc[i, f.columns.get_loc("close")] = c
        f.iloc[i, f.columns.get_loc("high")] = max(o, c) + 0.04
        f.iloc[i, f.columns.get_loc("low")] = min(o, c) - 0.04
        f.iloc[i, f.columns.get_loc("volume")] = 200
    if tf == "1m" and trigger:
        i = len(f) - 1
        f.iloc[i, f.columns.get_loc("volume")] = 200
        f.iloc[i, f.columns.get_loc("taker_buy")] = 120 if rising else 70
        f.iloc[i, f.columns.get_loc("open")] = 105.21 if rising else 102.99
        f.iloc[i, f.columns.get_loc("close")] = 105.26 if rising else 102.94
        f.iloc[i, f.columns.get_loc("high")] = 105.29 if rising else 103.02
        f.iloc[i, f.columns.get_loc("low")] = 105.19 if rising else 102.91
    return f


def snapshot(*, venue="BINANCE_TH_SPOT", rising=True, breakout=True,
             trigger=True, quote=105.15, spread_bps=2.0) -> MarketSnapshot:
    frames = {tf: frame(tf, rising=rising, breakout=breakout, trigger=trigger)
              for tf in ("15m", "5m", "1m")}
    return MarketSnapshot(venue, "BTCUSDT", frames, quote * (1 - spread_bps / 20_000),
                          quote * (1 + spread_bps / 20_000), 100_000, 100_000,
                          INSTRUMENT, NOW)


def raw_candles(period_min=1, count=70):
    last_open = NOW - timedelta(minutes=1, seconds=20)
    index = pd.date_range(end=last_open, periods=count, freq=f"{period_min}min", tz="UTC")
    return [[int(x.timestamp()*1000), "100", "102", "99", "101", "1000",
             int(x.timestamp()*1000 + period_min*60_000-1), "0", 20, "520", "0", "0"]
            for x in index]


class ScalpMarketTests(unittest.TestCase):
    def test_closed_candles_exclude_forming_bar(self):
        rows = raw_candles()
        future_open = NOW.replace(second=0)
        rows.append([int(future_open.timestamp()*1000), "101", "102", "100", "101", "10",
                     int(future_open.timestamp()*1000+59_999), "0", 1, "2", "0", "0"])
        result = parse_closed_klines(rows, "1m", NOW)
        self.assertNotEqual(result.open_ms.iloc[-1], rows[-1][0])

    def test_rejects_gapped_candles(self):
        rows = raw_candles()
        rows.pop(-6)
        with self.assertRaises(MarketDataError):
            parse_closed_klines(rows, "1m", NOW)

    def test_rejects_stale_candles(self):
        rows = raw_candles()
        for row in rows:
            row[0] -= 60 * 60_000
            row[6] -= 60 * 60_000
        with self.assertRaises(MarketDataError):
            parse_closed_klines(rows, "1m", NOW)

    def test_rejects_invalid_taker_volume(self):
        rows = raw_candles()
        rows[-1][9] = "2000"
        with self.assertRaises(MarketDataError):
            parse_closed_klines(rows, "1m", NOW)

    def test_quote_must_match_venue_symbol(self):
        with self.assertRaises(MarketDataError):
            parse_quote({"symbol": "ETHUSDT", "bidPrice": "10", "askPrice": "11",
                         "bidQty": "1", "askQty": "1"}, "BTCUSDT")

    def test_depth_must_be_two_sides(self):
        with self.assertRaises(MarketDataError):
            parse_depth({"bids": [["10", "5"]], "asks": []})

    @patch("scalp_marketdata._get_json")
    def test_exchange_catalog_uses_min_notional_and_step(self, mock):
        mock.return_value = {"symbols": [{"symbol": "BTCUSDT", "status": "TRADING",
                                         "filters": [{"filterType": "LOT_SIZE", "minQty": "0.00001", "stepSize": "0.00001"},
                                                     {"filterType": "MIN_NOTIONAL", "minNotional": "5"},
                                                     {"filterType": "PRICE_FILTER", "tickSize": "0.01"}]}]}
        found = get_exchange_catalog("BINANCE_TH_SPOT")
        self.assertEqual(found["BTCUSDT"].min_notional, Decimal("5"))
        self.assertEqual(found["BTCUSDT"].step_qty, Decimal("0.00001"))

    @patch("scalp_marketdata._get_json", side_effect=MarketDataError("HTTP 451"))
    def test_http_451_is_blocked_without_cross_exchange_fallback(self, _mock):
        with self.assertRaisesRegex(MarketDataError, "451"):
            fetch_snapshot("BINANCE_GLOBAL_USDM", "BTCUSDT")

    @patch("scalp_runner.get_exchange_catalog", side_effect=MarketDataError("HTTP 451"))
    def test_runner_marks_all_venues_unavailable_not_ready(self, _mock):
        results = scan(SETTINGS, now=NOW)
        self.assertEqual(len(results), len(SETTINGS.spot_symbols) + len(SETTINGS.futures_symbols)
                         + len(SETTINGS.bitget_futures_symbols))
        self.assertTrue(all(ob.state == "DATA_UNAVAILABLE" for ob in results))


class ScalpEngineTests(unittest.TestCase):
    def test_microtrend_can_classify_neutral_15m_with_5m_momentum(self):
        snap = snapshot()
        frames = {k: v.copy() for k, v in snap.frames.items()}
        fifteen = frames["15m"]
        fifteen["close"] = 104.0  # 15m EMA is flat: original trend gate is neutral.
        direction = _short_term_direction(fifteen, frames["5m"])
        self.assertEqual(direction, "LONG")
        ob = evaluate_scalp(replace(snap, frames=frames), SETTINGS)
        self.assertEqual(ob.strategy, "MICRO_TREND", ob.reason)
        self.assertIn(ob.state, ("READY", "WATCH", "RISK_BLOCK", "WAIT"))

    def test_microtrend_does_not_override_clear_opposing_15m(self):
        snap = snapshot()
        frames = {k: v.copy() for k, v in snap.frames.items()}
        fifteen = frames["15m"]
        fifteen["close"] = [110.0 - i * .04 for i in range(len(fifteen))]
        self.assertEqual(_short_term_direction(fifteen, frames["5m"]), "")
        ob = evaluate_scalp(replace(snap, frames=frames), SETTINGS)
        self.assertNotEqual(ob.strategy, "MICRO_TREND")
        self.assertNotEqual(ob.state, "READY")

    def test_no_5m_breakout_is_wait(self):
        ob = evaluate_scalp(snapshot(breakout=False), SETTINGS)
        self.assertEqual(ob.state, "WAIT")

    def test_spot_short_never_opened(self):
        ob = evaluate_scalp(snapshot(rising=False, quote=104.85), SETTINGS)
        self.assertEqual(ob.state, "EXIT_WATCH")
        self.assertEqual(ob.side, "SELL")

    def test_spread_guard(self):
        ob = evaluate_scalp(snapshot(spread_bps=30), SETTINGS)
        self.assertEqual(ob.state, "RISK_BLOCK")

    def test_adaptive_spread_cap_still_has_absolute_limit(self):
        snap = snapshot(spread_bps=20)
        f = snap.frames["5m"]
        # High-volatility 5m: enough to permit ~20bps, with absolute 25bps cap.
        f["high"] = f[["open", "close"]].max(axis=1) + 0.60
        f["low"] = f[["open", "close"]].min(axis=1) - 0.60
        self.assertNotIn("Spread", evaluate_scalp(snap, SETTINGS).reason)
        snap = replace(snap, bid=snap.ask * (1 - 32 / 10_000))
        self.assertIn("Spread", evaluate_scalp(snap, SETTINGS).reason)

    def test_small_balance_requires_min_notional(self):
        bad = replace(snapshot(), instrument=replace(INSTRUMENT, min_notional=Decimal("100")))
        ob = evaluate_scalp(bad, SETTINGS)
        self.assertIn(ob.state, ("RISK_BLOCK", "WAIT", "WATCH"))
        self.assertNotEqual(ob.state, "READY")

    def test_no_closed_1m_trigger_is_not_ready(self):
        ob = evaluate_scalp(snapshot(trigger=False), SETTINGS)
        self.assertNotEqual(ob.state, "READY")

    def test_spot_buy_ready_has_costs_and_small_capital(self):
        ob = evaluate_scalp(snapshot(), SETTINGS)
        self.assertEqual(ob.state, "READY", ob.reason)
        self.assertEqual(ob.side, "LONG")
        self.assertLess(ob.stop, ob.entry)
        self.assertLess(ob.entry, ob.tp1)
        self.assertLess(ob.tp1, ob.tp2)
        self.assertGreaterEqual(ob.net_rr, SETTINGS.min_net_rr)
        self.assertLessEqual(ob.notional_usdt, SETTINGS.capital_usdt)
        self.assertLessEqual(ob.risk_usdt, SETTINGS.capital_usdt * SETTINGS.risk_per_trade_pct / 100)
        self.assertGreater(ob.expires_at, NOW)

    def test_futures_short_not_based_on_spot(self):
        ob = evaluate_scalp(snapshot(venue="BINANCE_GLOBAL_USDM", rising=False, quote=102.94), SETTINGS)
        self.assertNotEqual(ob.venue, "BINANCE_TH_SPOT")
        self.assertEqual(ob.state, "READY", ob.reason)
        self.assertEqual(ob.side, "SHORT")
        self.assertGreater(ob.stop, ob.entry)
        self.assertLess(ob.tp2, ob.tp1)

    def test_bitget_missing_taker_flow_never_ready(self):
        snap = snapshot(venue="BITGET_USDT_FUTURES")
        snap.frames["1m"]["taker_buy"] = float("nan")
        ob = evaluate_scalp(snap, SETTINGS)
        self.assertEqual(ob.state, "WATCH")

    def test_bitget_complete_flow_can_be_ready_independently(self):
        snap = snapshot(venue="BITGET_USDT_FUTURES")
        snap = replace(snap, instrument=replace(INSTRUMENT, taker_fee_pct=0.06))
        ob = evaluate_scalp(snap, SETTINGS)
        self.assertEqual(ob.state, "READY")
        self.assertEqual(ob.venue, "BITGET_USDT_FUTURES")
        self.assertGreaterEqual(ob.net_rr, 1.5)

    def test_expired_quote_never_ready(self):
        old = replace(snapshot(), checked_at=NOW - timedelta(minutes=3))
        ob = evaluate_scalp(old, SETTINGS, now=NOW)
        self.assertEqual(ob.state, "DATA_UNAVAILABLE")

    def test_config_disallows_automation_and_large_capital(self):
        data = json.loads((ROOT / "scalp_config.json").read_text())
        for k, value in (("paper_only", False), ("capital_usdt", 1000),
                         ("risk_per_trade_pct", 5)):
            variant = dict(data)
            variant[k] = value
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "config.json"
                path.write_text(json.dumps(variant))
                with self.assertRaises(ValueError):
                    read_scalp_settings(path)


class ScalpAlertTests(unittest.TestCase):
    def watch(self):
        return ScalpObservation("BINANCE_TH_SPOT", "BTCUSDT", "WATCH", "test", NOW,
                                side="LONG", setup_id="abcd"*6, entry=100, stop=99,
                                tp1=101, tp2=102, qty=.5, notional_usdt=50,
                                risk_usdt=.2, net_rr=1.8, spread_bps=2,
                                setup_expires_at=NOW+timedelta(minutes=7))

    def test_watch_only_once_then_ready_only_once(self):
        state = empty_state()
        w = self.watch()
        self.assertEqual(len(transition(state, [w], SETTINGS, now=NOW)), 1)
        self.assertEqual(len(transition(state, [w], SETTINGS, now=NOW)), 0)
        ready = replace(w, state="READY", expires_at=NOW+timedelta(minutes=2))
        self.assertEqual(len(transition(state, [ready], SETTINGS, now=NOW)), 1)
        self.assertEqual(len(transition(state, [ready], SETTINGS, now=NOW)), 0)
        self.assertEqual(len(state["pending"]), 2)
        self.assertIn("PAPER ONLY", state["pending"][1]["text"])
        validate_state(json.loads(serialise_state(state)))

    def test_ready_daily_budget_caps_alerts(self):
        state = empty_state()
        for i in range(7):
            w = replace(self.watch(), setup_id=f"{i:024x}", symbol=f"X{i}USDT",
                        state="READY", expires_at=NOW+timedelta(minutes=2))
            transition(state, [w], SETTINGS, now=NOW)
        self.assertLessEqual(sum("READY" in x["text"] or "พร้อม" in x["text"]
                                 for x in state["pending"]), SETTINGS.max_ready_alerts_per_day)
        self.assertEqual(len(state["ready_day"]), SETTINGS.max_ready_alerts_per_day)

    def test_old_ready_is_not_queued(self):
        state = empty_state()
        w = replace(self.watch(), state="READY", expires_at=NOW-timedelta(seconds=2))
        transition(state, [w], SETTINGS, now=NOW)
        self.assertEqual(len(state["pending"]), 0)

    def test_data_unavailable_does_not_cancel_previous_plan(self):
        state = empty_state()
        w = self.watch()
        transition(state, [w], SETTINGS, now=NOW)
        transition(state, [replace(w, state="DATA_UNAVAILABLE")], SETTINGS, now=NOW)
        self.assertEqual(state["signals"]["BINANCE_TH_SPOT:BTCUSDT"]["phase"], "WATCH")

    def test_cancel_and_expire_follow_previous_setup(self):
        w = self.watch()
        state = empty_state()
        transition(state, [w], SETTINGS, now=NOW)
        transition(state, [replace(w, state="RISK_BLOCK")], SETTINGS, now=NOW)
        self.assertEqual(state["signals"]["BINANCE_TH_SPOT:BTCUSDT"]["phase"], "CANCELLED")
        self.assertEqual(len(state["pending"]), 2)
        state = empty_state()
        transition(state, [w], SETTINGS, now=NOW)
        then = NOW + timedelta(minutes=8)
        transition(state, [replace(w, state="WAIT", checked_at=then)], SETTINGS, now=then)
        self.assertEqual(state["signals"]["BINANCE_TH_SPOT:BTCUSDT"]["phase"], "EXPIRED")

    @patch("monitor_delivery.send_telegram")
    def test_expired_pending_not_sent_but_fresh_pending_is_sent(self, send):
        class FakeStore:
            def __init__(self):
                self.saves = 0

            def save(self, _state):
                self.saves += 1

        state = empty_state()
        w = self.watch()
        transition(state, [w], SETTINGS, now=NOW)
        state["pending"].append({"id": "f"*24, "text": "expired entry",
                                 "expires_at": (NOW-timedelta(seconds=1)).isoformat()})
        store = FakeStore()
        sent, dropped = send_pending(state, store, "fake", "fake", now=NOW)
        self.assertEqual((sent, dropped), (1, 1))
        self.assertEqual(send.call_count, 1)
        self.assertEqual(len(state["pending"]), 0)
        self.assertEqual(store.saves, 3)


class BitgetAdapterTests(unittest.TestCase):
    @patch("scalp_bitget._api")
    def test_online_perpetual_catalog_and_exchange_fee(self, api):
        api.return_value = [{"symbol": "BTCUSDT", "status": "online", "type": "perpetual",
                             "quoteCoin": "USDT", "minOrderQty": "0.0001",
                             "minOrderAmount": "5", "quantityMultiplier": "0.0001",
                             "priceMultiplier": "0.1", "takerFeeRate": "0.0006"},
                            {"symbol": "ETHUSDT", "status": "offline", "type": "perpetual",
                             "quoteCoin": "USDT"}]
        found = get_bitget_catalog()
        self.assertEqual(list(found), ["BTCUSDT"])
        self.assertEqual(found["BTCUSDT"].taker_fee_pct, 0.06)
        self.assertEqual(found["BTCUSDT"].step_qty, Decimal("0.0001"))

    def test_kline_without_trade_fills_stays_unknown(self):
        raw = raw_candles()
        bitget = [[str(r[0]), *map(str, r[1:6]), "999"] for r in raw]
        result = parse_bitget_candles(bitget, "1m", NOW)
        self.assertTrue(result.taker_buy.isna().all())

    def test_reconcile_closed_bar_full_coverage_only(self):
        f = frame("1m")
        open_ms = int(f.open_ms.iloc[-2])
        # Four fills; one before bar start and one after bar closes.
        complete = [{"ts": str(open_ms - 1), "size": "1", "side": "sell"},
                    {"ts": str(open_ms + 1000), "size": "60", "side": "buy"},
                    {"ts": str(open_ms + 30000), "size": "40", "side": "sell"},
                    {"ts": str(open_ms + 60001), "size": "1", "side": "sell"}]
        f["taker_buy"] = float("nan")
        result = reconcile_recent_fills(f, complete, NOW)
        self.assertEqual(result, 1)
        self.assertEqual(float(f.taker_buy.iloc[-2]), 60)
        self.assertTrue(pd.isna(f.taker_buy.iloc[-1]))
        partial = complete[1:]
        f["taker_buy"] = float("nan")
        result = reconcile_recent_fills(f, partial, NOW)
        self.assertEqual(result, 0)

    def test_rejects_mismatched_trade_volume(self):
        f = frame("1m")
        opened = int(f.open_ms.iloc[-2])
        f["taker_buy"] = float("nan")
        fills = [{"ts": str(opened - 1), "size": "1", "side": "sell"},
                 {"ts": str(opened + 1000), "size": "15", "side": "buy"},
                 {"ts": str(opened + 60001), "size": "1", "side": "sell"}]
        self.assertEqual(reconcile_recent_fills(f, fills, NOW), 0)
        self.assertTrue(f.taker_buy.isna().all())

    def test_research_is_descriptive_and_uses_closed_bars(self):
        f = frame("5m")
        result = summarise_volatility(f)
        self.assertIn("median_atr_pct", result)
        self.assertIn("breakouts_atr_ge_0.10", result)


if __name__ == "__main__":
    unittest.main()
