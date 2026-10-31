"""No exchange mixing, no synthetic taker flow, no fallback READY."""

import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from unittest import mock

import numpy as np
import pandas as pd

from futures_backup import fetch_backup_klines, fetch_backup_ticker
from futures_kraken_backup import fetch_kraken_pair, fetch_kraken_klines, fetch_kraken_ticker
from futures_daytrade import FuturesDataError, FuturesSettings, evaluate_futures
from futures_daytrade_runner import empty_state, scan, transition, telegram_message


class BybitSafetyTests(unittest.TestCase):
    def test_kraken_contract_mapping_uses_usd_and_btc_xbt_symbol(self):
        row = {"symbol": "PF_XBTUSD", "tag": "perpetual"}
        with mock.patch("futures_kraken_backup._read", return_value={"tickers": [row]}):
            self.assertEqual(fetch_kraken_pair("BTCUSDT"), "PF_XBTUSD")

    def test_kraken_candles_drop_open_bar_and_keep_missing_taker_flow(self):
        now = datetime(2026, 10, 30, 11, 40, tzinfo=timezone.utc)
        start = int(now.timestamp() * 1000) - 125 * 900_000
        candles = [{"time": start + i * 900_000, "open": "1", "high": "1.1",
                    "low": "0.9", "close": "1", "volume": "10"} for i in range(126)]
        with mock.patch("futures_kraken_backup._read", return_value={"candles": candles}):
            frame = fetch_kraken_klines("PF_PEPEUSD", "15m", now=now)
        self.assertGreaterEqual(len(frame), 100)
        self.assertTrue(frame["taker_buy"].isna().all())
        self.assertLessEqual(int(frame["closed"].iloc[-1]), int(now.timestamp() * 1000))

    def test_kraken_ticker_rejects_stale_and_marks_usd_watch_only(self):
        now = datetime(2026, 10, 30, 11, 40, tzinfo=timezone.utc)
        row = {"symbol": "PF_PEPEUSD", "tag": "perpetual", "last": 0.01,
               "markPrice": 0.01, "fundingRate": 999.0, "relativeFundingRate": 0.0001,
               "lastTime": "2026-10-30T11:30:00Z"}
        with mock.patch("futures_kraken_backup._read", return_value={"tickers": [row]}):
            with self.assertRaises(FuturesDataError):
                fetch_kraken_ticker("PF_PEPEUSD", now=now)
            row["lastTime"] = "2026-10-30T11:39:00Z"
            self.assertEqual(fetch_kraken_ticker("PF_PEPEUSD", now=now), (.01, .01, .01))
        from futures_daytrade import FuturesObservation
        ob = FuturesObservation("PF_PEPEUSD", "WATCH_LONG", "research", now,
                                direction="LONG", source="KRAKEN_WATCH_ONLY",
                                setup_id="LONG:abc", last_price=0.01, entry_low=0.009,
                                entry_high=0.011, stop=0.008, tp1=0.012, tp2=0.013,
                                risk_usdt=5, notional_usdt=100, net_rr_tp2=2)
        self.assertIn("KRAKEN USD", telegram_message(ob))
        state = empty_state()
        transition(state, [ob])
        self.assertIn("KRAKEN:PF_PEPEUSD", state["signals"])

    def test_scan_exposes_both_venue_failures_without_crashing(self):
        now = datetime(2026, 10, 30, 11, 40, tzinfo=timezone.utc)
        output = StringIO()
        with mock.patch("futures_daytrade_runner.fetch_futures_catalog",
                        side_effect=FuturesDataError("Binance HTTP 451")), \
             mock.patch("futures_daytrade_runner.fetch_backup_pair",
                        side_effect=FuturesDataError("Bybit HTTP 403")), \
             mock.patch("futures_daytrade_runner.fetch_kraken_pair",
                        side_effect=FuturesDataError("Kraken HTTP 503")), \
             redirect_stdout(output):
            results = scan(FuturesSettings(("PEPEUSDT", "BTCUSDT")), now=now)
        self.assertEqual([ob.state for ob in results], ["DATA_UNAVAILABLE"] * 2)
        self.assertIn("Binance HTTP 451", output.getvalue())
        self.assertIn("Bybit HTTP 403", output.getvalue())
        self.assertIn("PEPEUSDT | Bybit unavailable", output.getvalue())
        self.assertIn("Kraken HTTP 503", output.getvalue())

    def test_bybit_klines_keep_taker_evidence_missing_and_drop_open_bar(self):
        now = datetime(2026, 10, 30, 11, 40, tzinfo=timezone.utc)
        start = int(now.timestamp() * 1000) - 125 * 900_000
        rows = [[str(start + i * 900_000), "1.00", "1.02", ".98", "1.01", "100", "101"]
                for i in range(126)]
        with mock.patch("futures_backup._read", return_value={"list": list(reversed(rows))}):
            data = fetch_backup_klines("PEPEUSDT", "15m", now=now)
        self.assertGreaterEqual(len(data), 100)
        self.assertTrue(data["taker_buy"].isna().all())
        self.assertLessEqual(int(data["closed"].iloc[-1]), int(now.timestamp() * 1000))

    def test_bybit_ticker_rejects_old_server_time(self):
        now = datetime(2026, 10, 30, 11, 40, tzinfo=timezone.utc)
        stale = int(now.timestamp() * 1000) - 500_000
        with mock.patch("futures_backup._read", return_value={"list": [
            {"symbol": "PEPEUSDT", "lastPrice": "1", "markPrice": "1", "fundingRate": "0.0001"}],
            "_orbit_server_time": stale}):
            with self.assertRaises(FuturesDataError):
                fetch_backup_ticker("PEPEUSDT", now=now)

    def test_backup_cannot_produce_ready_even_when_breakout_passes(self):
        now = datetime(2026, 10, 30, 11, 40, tzinfo=timezone.utc)
        idx = pd.date_range(end=pd.Timestamp(now).floor("15min") - pd.Timedelta(minutes=15),
                            periods=150, freq="15min", tz="UTC")
        prices = np.linspace(1.0, 1.3, len(idx))
        frame = pd.DataFrame({"open": prices-.001, "high": prices+.008,
                              "low": prices-.008, "close": prices,
                              "volume": np.full(len(idx), 100.),
                              "taker_buy": np.full(len(idx), np.nan)}, index=idx)
        data = {"15m": frame, "1h": frame.copy(), "4h": frame.copy()}
        ob = evaluate_futures("PEPEUSDT", data, last=1.3, mark=1.3, funding_pct=0.01,
                              now=now, settings=FuturesSettings(("PEPEUSDT",)),
                              require_taker_flow=False)
        self.assertFalse(ob.state.startswith("READY"))

    def test_backup_events_are_distinct_from_binance(self):
        from futures_daytrade import FuturesObservation
        now = datetime(2026, 10, 30, 11, 40, tzinfo=timezone.utc)
        state = empty_state()
        transition(state, [FuturesObservation("PEPEUSDT", "WATCH_LONG", "volume only", now,
                         direction="LONG", setup_id="LONG:abc", source="BYBIT_WATCH_ONLY",
                         last_price=1.0, entry_low=.99, entry_high=1.01, stop=.95,
                         tp1=1.08, tp2=1.12, risk_usdt=5.0, notional_usdt=100.,
                         net_rr_tp2=2.0)])
        self.assertIn("BYBIT:PEPEUSDT", state["signals"])
        self.assertNotIn("PEPEUSDT", state["signals"])
        self.assertIn("BYBIT", state["pending"][0]["text"])


if __name__ == "__main__":
    unittest.main()
