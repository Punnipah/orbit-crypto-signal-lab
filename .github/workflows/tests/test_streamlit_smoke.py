"""Optional real Streamlit render smoke test; skips without UI dependencies.

Network is replaced by deterministic completed candles and unavailable-source
signals to verify the final dashboard's fail-closed rendering behavior.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase, mock
import importlib.util

import numpy as np
import pandas as pd

from binance_data import PublicDataError, TIMEFRAMES
from public_derivatives import DerivativesDataError


class StreamlitSmokeTests(TestCase):
    @staticmethod
    def _candles(symbol, timeframe, n):
        minutes = TIMEFRAMES[timeframe]
        now = pd.Timestamp.now(tz="UTC")
        last_open = now.floor(f"{minutes}min") - pd.Timedelta(minutes=minutes)
        index = pd.date_range(end=last_open, periods=n, freq=f"{minutes}min", tz="UTC")
        prices = 100 + np.arange(n) * .002
        vol = np.full(n, 100.)
        return pd.DataFrame({"open": prices - .04, "high": prices + .3,
                             "low": prices - .3, "close": prices,
                             "volume": vol, "taker_buy_base": vol * .56}, index=index)

    def test_final_app_renders_without_network_when_sources_missing(self):
        if importlib.util.find_spec("streamlit") is None or importlib.util.find_spec("plotly") is None:
            self.skipTest("Optional Streamlit/Plotly UI packages are not installed locally")
        from streamlit.testing.v1 import AppTest

        def no_derivatives(*args):
            raise DerivativesDataError("offline smoke fixture")

        def no_book(*args):
            raise PublicDataError("offline smoke fixture")

        def no_bybit(*args):
            raise ValueError("offline smoke fixture")

        from macro_liquidity import MarketLiquidity
        with mock.patch("binance_data.fetch_catalog", return_value=[
                {"symbol": "BTCUSDT", "base": "BTC", "quote": "USDT"}]), \
             mock.patch("binance_data.fetch_klines", side_effect=self._candles), \
             mock.patch("binance_data.fetch_spot_last_price",
                        return_value=(101., datetime.now(timezone.utc))), \
             mock.patch("public_derivatives.fetch_with_fallback", side_effect=no_derivatives), \
             mock.patch("market_microstructure.fetch_microstructure", side_effect=no_book), \
             mock.patch("bybit_intelligence.fetch_bybit_evidence", side_effect=no_bybit), \
             mock.patch("macro_liquidity.fetch_market_liquidity",
                        return_value=MarketLiquidity(None, None, None, None, None, None)):
            app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30)
            app.run(timeout=30)
            self.assertEqual([str(e.message) for e in app.exception], [])
            self.assertTrue(any("Orbit" in str(item.value) for item in app.title))

    def test_bookmarked_watch_link_reopens_original_symbol_and_zone(self):
        if importlib.util.find_spec("streamlit") is None or importlib.util.find_spec("plotly") is None:
            self.skipTest("Optional Streamlit/Plotly UI packages are not installed locally")
        from streamlit.testing.v1 import AppTest
        import streamlit as st
        from types import SimpleNamespace
        from watch_plans import new_watch_plan, encode_watch

        entry = SimpleNamespace(entry_low=98.0, entry_high=99.0,
                                stop_loss=95.0, take_profit_1=105.0,
                                take_profit_2=112.0)
        locked = new_watch_plan("PEPEUSDT", entry, now=datetime.now(timezone.utc), hours=48)

        st.cache_data.clear()
        with mock.patch("binance_data.fetch_catalog", return_value=[
                {"symbol": "BTCUSDT", "base": "BTC", "quote": "USDT"},
                {"symbol": "PEPEUSDT", "base": "PEPE", "quote": "USDT"}]), \
             mock.patch("binance_data.fetch_klines", side_effect=self._candles), \
             mock.patch("binance_data.fetch_spot_last_price",
                        return_value=(101., datetime.now(timezone.utc))), \
             mock.patch("public_derivatives.fetch_with_fallback",
                        side_effect=DerivativesDataError("offline fixture")), \
             mock.patch("market_microstructure.fetch_microstructure",
                        side_effect=PublicDataError("offline fixture")), \
             mock.patch("bybit_intelligence.fetch_bybit_evidence",
                        side_effect=ValueError("offline fixture")):
            app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30)
            app.query_params["watch"] = encode_watch(locked)
            app.run(timeout=30)
            self.assertEqual([str(e.message) for e in app.exception], [])
            self.assertTrue(any("PEPEUSDT" in str(item.value) for item in app.success))
            self.assertTrue(any(widget.value == "PEPEUSDT" for widget in app.selectbox))

    def test_final_app_renders_with_positive_optional_sources(self):
        if importlib.util.find_spec("streamlit") is None or importlib.util.find_spec("plotly") is None:
            self.skipTest("Optional Streamlit/Plotly UI packages are not installed locally")
        from streamlit.testing.v1 import AppTest
        import streamlit as st
        from market_microstructure import MicrostructureSnapshot
        from bybit_intelligence import BybitEvidence
        from macro_liquidity import MarketLiquidity

        stamp = datetime.now(timezone.utc)
        book = MicrostructureSnapshot(
            symbol="BTCUSDT", requested_at=stamp, last_trade_at=stamp,
            bid=100.9, ask=101.0, spread_bps=9.9,
            depth_bid_quote=1e8, depth_ask_quote=1e8,
            near_bid_share=.55, aggressor_buy_share=.60,
            aggregate_trades=500, trade_quote_volume=1e7,
            ask_impact_bps=2.0, requested_notional=3000)
        bybit = BybitEvidence("BTCUSDT", 100.95, .51, .59, stamp,
                              3.4, .01, ("Bybit Spot Book: OK", "Bybit Linear: OK"))
        macro = MarketLiquidity(3.0e11, .4, stamp, 1.2e11, 1.1, stamp)

        def no_derivatives(*args):
            raise DerivativesDataError("offline fixture")

        st.cache_data.clear()
        with mock.patch("binance_data.fetch_catalog", return_value=[
                {"symbol": "BTCUSDT", "base": "BTC", "quote": "USDT"}]), \
             mock.patch("binance_data.fetch_klines", side_effect=self._candles), \
             mock.patch("binance_data.fetch_spot_last_price", return_value=(101., stamp)), \
             mock.patch("public_derivatives.fetch_with_fallback", side_effect=no_derivatives), \
             mock.patch("market_microstructure.fetch_microstructure", return_value=book), \
             mock.patch("bybit_intelligence.fetch_bybit_evidence", return_value=bybit), \
             mock.patch("macro_liquidity.fetch_market_liquidity", return_value=macro):
            app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30)
            app.run(timeout=30)
            self.assertEqual([str(e.message) for e in app.exception], [])
