"""Automatic Spot scanning must not depend on manually saved watch links."""

from datetime import datetime, timezone
from unittest import TestCase, mock

from alert_monitor import _load_inputs, scan_all
from monitor_alerts import empty_state, remove_sent, transition
from monitor_engine import MonitorSettings, Observation


NOW = datetime(2026, 10, 31, 1, 15, tzinfo=timezone.utc)


def sample(mode: str, status: str, symbol: str = "PEPEUSDT") -> Observation:
    return Observation(symbol, mode, status, NOW, 0.000005, 81.0,
                       "Kraken Public Futures", "NOT_ENTERED", "offline fixture",
                       watch_token="existing-saved-link" if mode == "FROZEN" else None,
                       entry_low=0.0000049, entry_high=0.0000051,
                       stop_loss=0.0000047, tp1=0.0000057, tp2=0.0000061,
                       trigger_at=NOW)


class AutomaticSpotScanTests(TestCase):
    def test_saved_symbol_gets_live_and_frozen_with_one_analysis(self):
        settings = MonitorSettings(("PEPEUSDT",), 500)
        live = sample("LIVE_MTF", "MTF_READY")
        frozen = sample("FROZEN", "WAIT_ZONE")
        watches = {"PEPEUSDT": ("existing-saved-link", "https://example.test/?watch=token")}
        with mock.patch("alert_monitor.fetch_catalog", return_value=[
                {"symbol": "PEPEUSDT", "quote": "USDT"}]), \
                mock.patch("alert_monitor.fetch_klines"), \
                mock.patch("alert_monitor.analyze_symbol", return_value=(live, frozen)) as analyze:
            result = scan_all(settings, watches, {}, now=NOW)
        self.assertEqual([(ob.mode, ob.status) for ob in result],
                         [("LIVE_MTF", "MTF_READY"), ("FROZEN", "WAIT_ZONE")])
        analyze.assert_called_once()
        self.assertTrue(analyze.call_args.kwargs["return_live_also"])

    def test_bad_catalog_does_not_hide_live_status_with_saved_link(self):
        settings = MonitorSettings(("PEPEUSDT",), 500)
        with mock.patch("alert_monitor.fetch_catalog", side_effect=RuntimeError("offline")):
            result = scan_all(settings, {"PEPEUSDT": ("watch", "https://example.test")},
                              {}, now=NOW)
        self.assertEqual([(ob.mode, ob.status) for ob in result],
                         [("LIVE_MTF", "DATA_UNAVAILABLE"),
                          ("FROZEN", "DATA_UNAVAILABLE")])

    def test_malformed_saved_secret_is_optional(self):
        settings = MonitorSettings(("PEPEUSDT",), 500)
        with mock.patch("alert_monitor.read_settings", return_value=settings), \
                mock.patch("alert_monitor.parse_watch_links", side_effect=ValueError("invalid")), \
                mock.patch("alert_monitor.read_manual_coinglass", return_value={}):
            _, watches, _ = _load_inputs()
        self.assertEqual(watches, {})


class IndependentTelegramStreamsTests(TestCase):
    def test_frozen_invalidated_cannot_suppress_live_buy(self):
        state = empty_state()
        transition(state, [sample("LIVE_MTF", "MTF_READY"), sample("FROZEN", "INVALIDATED")])
        self.assertEqual({row["kind"] for row in state["pending"]},
                         {"MTF_READY", "INVALIDATED"})
        self.assertEqual(len({row["symbol"] for row in state["pending"]}), 2)
        self.assertEqual(state["symbols"]["PEPEUSDT"]["status"], "INVALIDATED")
        self.assertEqual(state["symbols"]["PEPEUSDT|LIVE_MTF"]["status"], "MTF_READY")

    def test_wait_removes_only_outdated_live_ready(self):
        state = empty_state()
        transition(state, [sample("LIVE_MTF", "MTF_READY"), sample("FROZEN", "INVALIDATED")])
        transition(state, [sample("LIVE_MTF", "MTF_WAIT"), sample("FROZEN", "INVALIDATED")])
        self.assertNotIn("MTF_READY", {row["kind"] for row in state["pending"]})
        self.assertIn("INVALIDATED", {row["kind"] for row in state["pending"]})

    def test_repeat_live_ready_does_not_spam_telegram(self):
        state = empty_state()
        live = sample("LIVE_MTF", "MTF_READY")
        transition(state, [live])
        self.assertEqual(len(state["pending"]), 1)
        remove_sent(state, state["pending"][0]["id"])
        transition(state, [live])
        self.assertEqual(state["pending"], [])

    def test_legacy_live_state_migrates_without_resending(self):
        state = empty_state()
        live = sample("LIVE_MTF", "MTF_READY", "BTCUSDT")
        transition(state, [live])
        state["symbols"]["BTCUSDT"] = state["symbols"].pop("BTCUSDT|LIVE_MTF")
        state["pending"][0]["symbol"] = "BTCUSDT"
        original_id = state["pending"][0]["id"]
        transition(state, [live])
        self.assertNotIn("BTCUSDT", state["symbols"])
        self.assertEqual(state["pending"][0]["symbol"], "BTCUSDT|LIVE_MTF")
        self.assertEqual([row["id"] for row in state["pending"]], [original_id])

    def test_removing_saved_watch_discards_old_queued_ready(self):
        state = empty_state()
        transition(state, [sample("FROZEN", "READY_NOW")])
        transition(state, [sample("LIVE_MTF", "MTF_WAIT")])
        self.assertNotIn("PEPEUSDT", state["symbols"])
        self.assertEqual(state["pending"], [])

