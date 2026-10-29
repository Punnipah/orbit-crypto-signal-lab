"""Independent regression tests for Orbit Professional Final's free-data layers."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

import numpy as np
import pandas as pd

from advanced_evidence import analyze_spot_evidence, interpret_spot_evidence
from bybit_intelligence import parse_bybit_evidence
from journal_utils import combine_journal, export_signal_journal, import_signal_journal
from macro_liquidity import parse_market_liquidity
from risk_audit import audit_entry


class ProfessionalEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)

    def _candles(self, buy: float = .6):
        index = pd.date_range("2026-10-01", periods=120, freq="h", tz="UTC")
        price = 100 + np.arange(120) * .03
        volume = np.full(120, 10.)
        return pd.DataFrame({"high": price + .4, "low": price - .4,
                             "open": price - .1, "close": price,
                             "volume": volume, "atr": np.full(120, 1.2),
                             "taker_buy_base": volume * buy,
                             "sweep_low": [False] * 119 + [True]}, index=index)

    def test_cvd_vwap_and_profile_are_derived_from_closed_bars(self):
        frame = self._candles()
        result = analyze_spot_evidence(frame, "1h")
        self.assertAlmostEqual(result.delta_share20, .6)
        self.assertAlmostEqual(result.cvd_20_base, 40)
        self.assertTrue(result.sweep_reclaim)
        self.assertGreater(result.candle_vwap, frame.iloc[-24]["close"])
        self.assertLess(result.candle_vwap, frame.iloc[-1]["close"])
        self.assertIsNotNone(result.candle_volume_poc)
        self.assertIn("ประมาณ", " ".join(interpret_spot_evidence(result)))

    def test_missing_aggressor_volumes_not_invented(self):
        frame = self._candles().drop(columns=["taker_buy_base"])
        item = analyze_spot_evidence(frame, "15m")
        self.assertIsNone(item.cvd_20_base)
        self.assertIsNone(item.delta_share20)

    def test_spot_evidence_does_not_rely_on_future_bars(self):
        frame = self._candles()
        before = analyze_spot_evidence(frame.iloc[:-1], "1h")
        changed = frame.copy()
        changed.iloc[-1, changed.columns.get_loc("close")] *= 2
        still = analyze_spot_evidence(changed.iloc[:-1], "1h")
        self.assertEqual(before, still)

    def test_bybit_separates_spot_orderflow_and_perpetual_oi(self):
        ms = lambda hours=0: int((self.now - timedelta(hours=hours)).timestamp() * 1000)
        spot = {"retCode": 0, "result": {"s": "BTCUSDT", "ts": ms(),
                "b": [["100", "12"]], "a": [["101", "6"]]}}
        trades = {"retCode": 0, "result": {"list": [
            {"symbol": "BTCUSDT", "side": "Buy", "price": "101", "size": "2", "time": ms()},
            {"symbol": "BTCUSDT", "side": "Sell", "price": "100", "size": "1", "time": ms()}]}}
        oi = {"retCode": 0, "result": {"symbol": "BTCUSDT", "category": "linear",
              "list": [{"timestamp": str(ms(24)), "openInterest": "100"},
                       {"timestamp": str(ms()), "openInterest": "110"}]}}
        ticker = {"retCode": 0, "result": {"list": [
            {"symbol": "BTCUSDT", "fundingRate": "0.0001"}]}}
        result = parse_bybit_evidence("BTCUSDT", spot, trades, oi, ticker, now=self.now)
        self.assertAlmostEqual(result.futures_oi_change_24h_pct, 10)
        self.assertAlmostEqual(result.futures_funding_rate_pct, .01)
        self.assertAlmostEqual(result.spot_aggressor_buy_share, 202 / 302)
        self.assertTrue(all("OK" in line for line in result.source_status))

    def test_bybit_stale_and_wrong_source_fail_closed(self):
        ms = int((self.now - timedelta(hours=4)).timestamp() * 1000)
        spot = {"retCode": 0, "result": {"s": "OTHER", "ts": ms,
                "b": [["100", "1"]], "a": [["101", "1"]]}}
        missing = {"retCode": -1, "retMsg": "region restriction"}
        result = parse_bybit_evidence("BTCUSDT", spot, missing, missing, missing,
                                      now=self.now)
        self.assertIsNone(result.spot_mid)
        self.assertIsNone(result.spot_aggressor_buy_share)
        self.assertIsNone(result.futures_oi_change_24h_pct)
        self.assertTrue(all("MISSING" in line for line in result.source_status))

    def test_defillama_market_context_is_not_whale_data(self):
        time_at = lambda days: int((self.now - timedelta(days=days)).timestamp())
        stable = [{"date": time_at(7), "totalCirculatingUSD": {"peggedUSD": 100}},
                  {"date": time_at(0), "totalCirculatingUSD": {"peggedUSD": 110}}]
        tvl = [{"date": time_at(7), "tvl": 200}, {"date": time_at(0), "tvl": 180}]
        result = parse_market_liquidity(stable, tvl, now=self.now)
        self.assertAlmostEqual(result.stablecoin_change_7d_pct, 10)
        self.assertAlmostEqual(result.defi_tvl_change_7d_pct, -10)
        self.assertIn("DefiLlama", result.source)

    def test_stale_defillama_is_not_called_current(self):
        stale = [{"date": int((self.now - timedelta(days=10)).timestamp()),
                  "totalCirculatingUSD": {"peggedUSD": 12}}]
        result = parse_market_liquidity(stale, [], now=self.now)
        self.assertIsNone(result.stablecoin_supply_usd)

    def test_net_rr_includes_modeled_costs_and_missing_plan_veto(self):
        plan = SimpleNamespace(entry_high=100, stop_loss=95, take_profit_1=107.5,
                               take_profit_2=112.5)
        result = audit_entry(plan, fee_pct=.1, slippage_pct=.1)
        self.assertTrue(result.checks[0].passed)
        self.assertLess(result.rr_tp2, 2.5)
        self.assertGreater(result.rr_tp2, 2)
        self.assertFalse(audit_entry(None, fee_pct=.1, slippage_pct=.1).checks[0].passed)

    def test_journal_roundtrip_and_deduplication(self):
        row = {"observed_at_th": "2026-10-28 17:00:00", "symbol": "PEPEUSDT",
               "mtf_signal": "BUY", "entry_status": "READY", "note": "no trade"}
        saved = export_signal_journal([row])
        loaded = import_signal_journal(saved)
        self.assertEqual(loaded[0], row)
        self.assertEqual(len(combine_journal([row], loaded)), 1)

    def test_journal_rejects_bad_pair(self):
        raw = b"observed_at_th,symbol,mtf_signal,entry_status\n2026-01-01,=BAD,BUY,READY\n"
        with self.assertRaises(ValueError):
            import_signal_journal(raw)


if __name__ == "__main__":
    unittest.main()
