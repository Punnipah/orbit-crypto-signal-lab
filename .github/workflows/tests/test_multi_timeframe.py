"""Regression checks for the read-only four-timeframe comparison view."""

from datetime import datetime, timedelta, timezone
import unittest

import numpy as np
import pandas as pd

from coinglass_overlay import CoinGlassSnapshot
from multi_timeframe import build_timeframe_report
from public_derivatives import DerivativesSnapshot


NOW = datetime(2026, 10, 29, 0, 1, tzinfo=timezone.utc)


def frame(tf="1h", *, late=0):
    freq = {"15m": "15min", "1h": "h", "4h": "4h", "1d": "D"}[tf]
    minutes = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}[tf]
    latest_closed = datetime(2026, 10, 29, 0, 0, tzinfo=timezone.utc) - timedelta(minutes=late)
    latest_open = latest_closed - timedelta(minutes=minutes)
    idx = pd.date_range(end=latest_open, periods=300, freq=freq)
    price = np.linspace(90, 100, 300)
    base = pd.DataFrame({"open": price - 0.4, "high": price + 1,
                         "low": price - 1, "close": price,
                         "volume": np.full(300, 100.)}, index=idx)
    features = pd.DataFrame(index=idx)
    defaults = {
        "signal": "BUY", "open": 99.6, "close": 100., "atr": 2.,
        "pivot_high": 96., "pivot_low": 97., "support50": 96.5,
        "ema20": 99.5, "ema50": 98., "ema200": 90., "macd_hist": 0.3,
        "volume_ma20": 100., "trend": 1, "higher_trend": 1,
        "structure_bias": 1, "sweep_high": False, "score": 8,
        "adx": 30., "rsi": 60., "volume_ratio": 1.2,
    }
    for key, value in defaults.items():
        features[key] = value
    return base, features


def future():
    return DerivativesSnapshot(
        symbol="BTCUSDT", observed_at=NOW, funding_rate_pct=.01,
        oi_change_24h_pct=5., long_short_account_ratio=1.1,
        oi_notional_usdt=2e8, funding_at=NOW, oi_at=NOW, ratio_at=NOW,
    )


def cg(*, at=NOW, ratio=1.1):
    return CoinGlassSnapshot(
        symbol="BTC", observed_at=at, funding_rate_pct=.01,
        oi_change_24h_pct=5., long_short_account_ratio=ratio,
        long_liquidations_usd_24h=1000, short_liquidations_usd_24h=2000,
    )


def evaluate(tf="1h", *, derivatives=None, coinglass=None, price=100., late=0, **changes):
    base, analyzed = frame(tf, late=late)
    for key, value in changes.items():
        analyzed.loc[analyzed.index[-1], key] = value
    return build_timeframe_report(
        base, analyzed, tf, base_asset="BTC", derivatives=derivatives,
        coinglass=coinglass, now=NOW, current_price=price,
        capital=10000, risk_pct=1, max_allocation_pct=30,
        fee_pct=.1, slippage_pct=.05,
    )


class TestMultiTimeframe(unittest.TestCase):
    def test_all_four_timeframes_can_evaluate_without_future_bars(self):
        for tf in ("15m", "1h", "4h", "1d"):
            with self.subTest(tf=tf):
                report = evaluate(tf, derivatives=future())
                self.assertEqual(report.final, "BUY")
                self.assertEqual(report.entry.status, "READY")
                self.assertLess(report.last_close, NOW)
                self.assertFalse(report.gaps)
                self.assertFalse(report.stale)
                self.assertEqual(report.coinglass_status, "MISSING")
                self.assertTrue(any(c.label == "CoinGlass" and c.passed is None
                                    for c in report.checks))

    def test_missing_futures_blocks_final_and_ready(self):
        report = evaluate()
        self.assertEqual(report.technical, "BUY")
        self.assertEqual(report.final, "WAIT")
        self.assertEqual(report.futures_status, "MISSING")
        self.assertNotEqual(report.entry.status, "READY")
        self.assertFalse(next(c.passed for c in report.checks
                              if c.label == "Futures สนับสนุน BUY"))

    def test_stale_bars_cannot_be_ready_even_with_futures(self):
        report = evaluate(derivatives=future(), late=180)
        self.assertEqual(report.final, "WAIT")
        self.assertTrue(report.stale)
        self.assertEqual(report.entry.status, "INVALID")
        self.assertIsNone(report.entry.entry_low)

    def test_stale_coin_glass_vetoes_15m_but_not_daily(self):
        snapshot = cg(at=NOW - timedelta(hours=3))
        fast = evaluate("15m", derivatives=future(), coinglass=snapshot)
        slow = evaluate("1d", derivatives=future(), coinglass=snapshot)
        self.assertEqual(fast.coinglass_status, "INVALID")
        self.assertEqual(fast.final, "WAIT")
        self.assertEqual(slow.coinglass_status, "CONFIRMED")
        self.assertEqual(slow.final, "BUY")

    def test_coinglass_crowding_blocks_even_if_auto_supported(self):
        report = evaluate(derivatives=future(), coinglass=cg(ratio=1.8))
        self.assertEqual(report.auto, "BUY")
        self.assertEqual(report.coinglass_status, "CAUTION")
        self.assertEqual(report.final, "WAIT")
        self.assertNotEqual(report.entry.status, "READY")
        self.assertTrue(report.coinglass_blockers)

    def test_buy_direction_does_not_mean_entry_now(self):
        report = evaluate(derivatives=future(), price=104)
        self.assertEqual(report.final, "BUY")
        self.assertEqual(report.entry.status, "WAIT_RETEST")
        self.assertFalse(next(c.passed for c in report.checks
                              if c.label == "ราคา Spot ล่าสุดอยู่ในโซน"))

    def test_timeframes_preserve_their_own_support_and_atr(self):
        fast = evaluate("1h", derivatives=future())
        slow = evaluate("4h", derivatives=future(), ema20=96., atr=3.)
        self.assertNotEqual(fast.entry.entry_low, slow.entry.entry_low)
        self.assertNotEqual(fast.entry.entry_high, slow.entry.entry_high)

    def test_wrong_snapshot_coin_rejected(self):
        other = CoinGlassSnapshot(
            symbol="ETH", observed_at=NOW, funding_rate_pct=.01,
            oi_change_24h_pct=5., long_short_account_ratio=1.1,
            long_liquidations_usd_24h=100, short_liquidations_usd_24h=100,
        )
        report = evaluate(derivatives=future(), coinglass=other)
        self.assertEqual(report.final, "WAIT")
        self.assertEqual(report.coinglass_status, "INVALID")


if __name__ == "__main__":
    unittest.main()
