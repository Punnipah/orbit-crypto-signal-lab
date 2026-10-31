"""Read-only historical 5m volatility/technical opportunity diagnostics.

NOT a full scalp strategy backtest: historical bid/ask, order-book, execution
slippage, complete 1m aggressor data and order fill prices are NOT known.
Do not derive a win rate, profit expectancy or parameter optimum from these
descriptive counts. Use 3-day historical Binance TH Spot data only.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math

import pandas as pd

from scalp_marketdata import (MarketDataError, PERIOD, SPOT_URL, _get_json,
                              parse_closed_klines)


def summarise_volatility(frame: pd.DataFrame) -> dict:
    if len(frame) < 100:
        raise ValueError("Need at least 100 historical 5m bars")
    frame = frame.copy()
    prior = frame.close.shift(1)
    true_range = pd.concat([frame.high - frame.low, (frame.high - prior).abs(),
                            (frame.low - prior).abs()], axis=1).max(axis=1)
    frame["atr_pct"] = true_range.rolling(14).mean() / frame.close * 100
    frame["breakout"] = ((frame.close > frame.high.shift(1).rolling(10).max()) &
                         (frame.close > frame.open) &
                         (frame.volume > frame.volume.shift(1).rolling(20).mean() * 1.10))
    sample = frame.iloc[40:-4].copy()
    if len(sample) < 50 or sample.atr_pct.isna().any():
        raise ValueError("Volatility sample incomplete")
    results = {"bars": len(sample),
               "median_atr_pct": round(float(sample.atr_pct.median()), 4),
               "p25_atr_pct": round(float(sample.atr_pct.quantile(.25)), 4),
               "p75_atr_pct": round(float(sample.atr_pct.quantile(.75)), 4)}
    # Not a success/win measure. The future high is only a gross excursion
    # after the signal candle and has no stop ordering or executable prices.
    for gate in (0.07, 0.10):
        valid = sample[(sample.atr_pct >= gate) & sample.breakout]
        results[f"breakouts_atr_ge_{gate:.2f}"] = len(valid)
    return results


def research_spot(symbols: tuple[str, ...], *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Research timezone missing")
    results = {}
    for symbol in symbols:
        rows = _get_json(SPOT_URL, "/api/v1/klines",
                         {"symbol": symbol, "interval": "5m", "limit": 950})
        frame = parse_closed_klines(rows, "5m", now)
        if (frame.open_ms.diff().dropna() != PERIOD["5m"]).any():
            raise MarketDataError(f"{symbol}: historical 5m candle gap")
        results[symbol] = summarise_volatility(frame)
    return results
