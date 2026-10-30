"""Offline tests for GitHub Actions monitor, frozen plans and Telegram dedupe."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock
from tempfile import TemporaryDirectory
import json

import numpy as np
import pandas as pd

from binance_data import PublicDataError, TIMEFRAMES
from monitor_alerts import empty_state, remove_sent, serialize_state, transition, validate_state
from monitor_delivery import DeliveryError, GitHubStateStore, send_telegram
from monitor_engine import (MonitorSettings, Observation, analyze_symbol, parse_watch_links,
                            read_manual_coinglass, read_settings, unavailable)
from public_derivatives import DerivativesDataError
from watch_plans import encode_watch, new_watch_plan


UTC = timezone.utc
NOW = datetime(2026, 10, 29, 9, 15, tzinfo=UTC)


def obs(status="WAIT_ZONE", symbol="PEPEUSDT", token="frozen-v41", **kw):
    return Observation(symbol, "FROZEN" if token else "LIVE_MTF", status, NOW,
                       0.00000483, 80., "Kraken Public Futures", "NOT_ENTERED",
                       "fixture", watch_token=token, entry_low=.00000480,
                       entry_high=.00000485, stop_loss=.00000475,
                       tp1=.000005, tp2=.0000052, **kw)


def make_token(symbol="PEPEUSDT"):
    p = SimpleNamespace(entry_low=.00000480, entry_high=.00000485,
                        stop_loss=.00000475, take_profit_1=.000005,
                        take_profit_2=.0000052)
    return encode_watch(new_watch_plan(symbol, p, now=NOW, hours=48))


class MonitorConfigTests(TestCase):
    def test_default_three_symbols(self):
        config = read_settings(Path(__file__).parents[1] / "monitor_config.json")
        self.assertEqual(config.symbols, ("PEPEUSDT", "BTCUSDT", "DOGEUSDT"))

    def test_rejects_invalid_symbols_and_settings(self):
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / "settings.json"
            file.write_text(json.dumps({"symbols": ["PEPE/USDT"]}))
            with self.assertRaises(ValueError):
                read_settings(file)
            file.write_text(json.dumps({"symbols": ["PEPEUSDT"], "capital": -1}))
            with self.assertRaises(ValueError):
                read_settings(file)

    def test_watch_link_decodes_and_matches_coin(self):
        token = make_token()
        links = parse_watch_links(f"PEPEUSDT=https://app.streamlit.app/?watch={token}\n",
                                  ("PEPEUSDT",))
        self.assertEqual(links["PEPEUSDT"],
                         (token, f"https://app.streamlit.app/?watch={token}"))

    def test_watch_link_rejects_wrong_symbol_and_missing_query(self):
        token = make_token()
        with self.assertRaises(ValueError):
            parse_watch_links(f"BTCUSDT={token}", ("BTCUSDT",))
        with self.assertRaises(ValueError):
            parse_watch_links("PEPEUSDT=https://app.streamlit.app/", ("PEPEUSDT",))

    def test_watch_link_rejects_duplicate_and_unknown(self):
        token = make_token()
        with self.assertRaises(ValueError):
            parse_watch_links(f"PEPEUSDT={token}\nPEPEUSDT={token}", ("PEPEUSDT",))
        with self.assertRaises(ValueError):
            parse_watch_links(f"ETHUSDT={token}", ("PEPEUSDT",))

    def test_manual_coinglass_empty_is_optional(self):
        snapshots = read_manual_coinglass(Path(__file__).parents[1] / "monitor_coinglass_manual.json")
        self.assertEqual(snapshots, {})

    def test_manual_coinglass_requires_timezone(self):
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / "cg.json"
            file.write_text(json.dumps({"snapshots": {"PEPE": {
                "observed_at": "2026-10-29T15:00:00", "funding_rate_pct": .01,
                "oi_change_24h_pct": 2, "long_short_account_ratio": 1.3,
                "long_liquidations_usd_24h": 1000, "short_liquidations_usd_24h": 2000}}}))
            with self.assertRaises(ValueError):
                read_manual_coinglass(file)


class AlertTransitionTests(TestCase):
    def test_wait_does_not_spam_or_queue(self):
        state = empty_state()
        transition(state, [obs("WAIT_ZONE")])
        transition(state, [obs("WAIT_ZONE")])
        self.assertEqual(state["pending"], [])

    def test_ready_is_only_queued_once_across_runs(self):
        state = empty_state()
        result = obs("READY_NOW", trigger_at=NOW)
        transition(state, [result])
        self.assertEqual(len(state["pending"]), 1)
        remove_sent(state, state["pending"][0]["id"])
        transition(state, [result])
        self.assertEqual(len(state["pending"]), 0)
        self.assertEqual(state["symbols"][result.symbol]["status"], "READY_NOW")

    def test_pending_ready_is_dropped_after_invalidated(self):
        state = empty_state()
        transition(state, [obs("READY_NOW", trigger_at=NOW)])
        transition(state, [obs("INVALIDATED")])
        self.assertEqual([e["kind"] for e in state["pending"]], ["INVALIDATED"])

    def test_pending_ready_is_dropped_when_data_unavailable(self):
        state = empty_state()
        transition(state, [obs("READY_NOW", trigger_at=NOW)])
        transition(state, [unavailable("PEPEUSDT", NOW, "offline", watch_token="frozen-v41")])
        self.assertEqual([e["kind"] for e in state["pending"]], [])

    def test_lost_ready_warning_when_wait_returns(self):
        state = empty_state()
        transition(state, [obs("READY_NOW", trigger_at=NOW)])
        remove_sent(state, state["pending"][0]["id"])
        transition(state, [obs("WAIT_RECLAIM")])
        self.assertEqual(state["pending"][0]["kind"], "NO_LONGER_READY")

    def test_invalidated_and_expired_are_once_per_plan(self):
        state = empty_state()
        transition(state, [obs("INVALIDATED")])
        self.assertEqual(len(state["pending"]), 1)
        remove_sent(state, state["pending"][0]["id"])
        transition(state, [obs("EXPIRED")])
        transition(state, [obs("INVALIDATED")])
        self.assertEqual([e["kind"] for e in state["pending"]], ["EXPIRED"])

    def test_changing_plan_replaces_pending_old_plan(self):
        state = empty_state()
        transition(state, [obs("READY_NOW", trigger_at=NOW)])
        transition(state, [obs("WAIT_ZONE", token="another-watch-plan")])
        self.assertEqual(state["pending"], [])

    def test_two_consecutive_data_outages_alert_once(self):
        state = empty_state()
        row = unavailable("PEPEUSDT", NOW, "offline", watch_token="frozen-v41")
        transition(state, [row])
        self.assertEqual(state["pending"], [])
        transition(state, [row])
        transition(state, [row])
        self.assertEqual([e["kind"] for e in state["pending"]], ["DATA_UNAVAILABLE"])

    def test_futures_missing_twice_warns_without_buy(self):
        state = empty_state()
        row = Observation(**{**obs("WAIT_MTF").__dict__, "futures_source": "MISSING"})
        transition(state, [row])
        self.assertEqual(state["pending"], [])
        transition(state, [row])
        self.assertEqual([e["kind"] for e in state["pending"]], ["DATA_UNAVAILABLE"])

    def test_pending_buy_removed_if_price_signal_passed(self):
        state = empty_state()
        transition(state, [obs("READY_NOW", trigger_at=NOW)])
        transition(state, [obs("PASSED")])
        self.assertEqual([e["kind"] for e in state["pending"]], ["PASSED"])

    def test_manually_entered_coinglass_invalid_warns_once(self):
        state = empty_state()
        row = obs("WAIT_MTF")
        bad = Observation(**{**row.__dict__, "coinglass_status": "INVALID"})
        transition(state, [bad])
        transition(state, [bad])
        self.assertEqual([e["kind"] for e in state["pending"]], ["COINGLASS_STALE"])

    def test_persisted_state_has_no_watch_token_or_url(self):
        state = empty_state()
        transition(state, [obs("READY_NOW", trigger_at=NOW)])
        payload = serialize_state(state)
        self.assertNotIn(b"frozen-v41", payload)
        self.assertNotIn(b"TELEGRAM_BOT_TOKEN", payload)
        self.assertEqual(validate_state(json.loads(payload)), json.loads(payload))

    def test_live_mtf_ready_is_explicitly_labeled_non_frozen(self):
        state = empty_state()
        transition(state, [obs("MTF_READY", token=None)])
        self.assertIn("ยังไม่ได้ล็อกโซน", state["pending"][0]["text"])


class DeliveryTests(TestCase):
    def test_telegram_rejects_missing_credentials_before_network(self):
        with self.assertRaises(DeliveryError):
            send_telegram("", "123456789", "hello")
        with self.assertRaises(DeliveryError):
            send_telegram("123456789:012345678901234567890", "not-chat-id", "hello")

    def test_telegram_sends_only_through_official_post(self):
        payload = SimpleNamespace(__enter__=lambda self: self)
        class Reply:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def read(self):
                return b'{"ok":true}'
        with mock.patch("monitor_delivery.urlopen", return_value=Reply()) as patched:
            send_telegram("123456789:012345678901234567890", "123456789", "test")
        req = patched.call_args.args[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(json.loads(req.data)["chat_id"], "123456789")

    def test_state_store_stays_off_default_branch(self):
        store = GitHubStateStore("example/repo", "test_github_token", "a" * 40)
        with mock.patch.object(store, "_request", side_effect=[
            None, {}, {"content": {"sha": "blobsha1"}},
        ]) as req:
            state = store.load()
            self.assertEqual(state, empty_state())
            self.assertTrue(store.save(state))
            self.assertFalse(store.save(state))
        self.assertEqual(req.call_args_list[1].args[1], "/git/refs")
        put_payload = req.call_args_list[2].args[2]
        self.assertEqual(put_payload["branch"], "orbit-alert-state")


class HeadlessAnalysisTests(TestCase):
    @staticmethod
    def _candles(symbol, timeframe, count):
        minutes = TIMEFRAMES[timeframe]
        instant = pd.Timestamp.now(tz="UTC")
        start = instant.floor(f"{minutes}min") - pd.Timedelta(minutes=minutes)
        index = pd.date_range(end=start, periods=count, freq=f"{minutes}min", tz="UTC")
        prices = 100 + np.arange(count) * 0.002
        vol = np.full(count, 100.)
        return pd.DataFrame({"open": prices - .04, "high": prices + .3,
                             "low": prices - .3, "close": prices, "volume": vol,
                             "taker_buy_base": vol * .56}, index=index)

    def test_missing_futures_and_microstructure_cannot_trigger_mtf_buy(self):
        settings = MonitorSettings(("BTCUSDT",), 500)
        now = datetime.now(UTC)
        with mock.patch("monitor_engine.fetch_klines", side_effect=self._candles), \
             mock.patch("monitor_engine.fetch_spot_last_price", return_value=(101., now)), \
             mock.patch("monitor_engine.fetch_with_fallback", side_effect=DerivativesDataError("offline")), \
             mock.patch("monitor_engine.fetch_microstructure", side_effect=PublicDataError("offline")), \
             mock.patch("monitor_engine.fetch_bybit_evidence", side_effect=ValueError("offline")):
            result = analyze_symbol("BTCUSDT", settings, now=now, watch=None, manual_cg=None)
        self.assertEqual(result.status, "MTF_WAIT")
        self.assertEqual(result.futures_source, "MISSING")
        self.assertIn("สภาพคล่อง Spot", result.failed_checks)

    def test_scanner_failure_for_one_coin_keeps_others_but_never_fakes_buy(self):
        from alert_monitor import scan_all
        settings = MonitorSettings(("PEPEUSDT", "BTCUSDT", "DOGEUSDT"), 500)
        catalog = [{"symbol": s, "quote": "USDT"} for s in settings.symbols]
        with mock.patch("alert_monitor.fetch_catalog", return_value=catalog), \
             mock.patch("alert_monitor.fetch_klines", side_effect=self._candles), \
             mock.patch("alert_monitor.analyze_symbol", side_effect=[
                 ValueError("offline PEPE"),
                 obs("WAIT_ZONE", symbol="BTCUSDT", token=None),
                 obs("WAIT_ZONE", symbol="DOGEUSDT", token=None),
             ]):
            result = scan_all(settings, {}, {}, now=datetime.now(UTC))
        self.assertEqual([r.symbol for r in result], list(settings.symbols))
        self.assertEqual(result[0].status, "DATA_UNAVAILABLE")
        self.assertEqual([r.status for r in result[1:]], ["WAIT_ZONE", "WAIT_ZONE"])


if __name__ == "__main__":
    import unittest
    unittest.main()
