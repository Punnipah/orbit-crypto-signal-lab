"""Read-only structural watch prices when a trading engine has no approved plan.

These are *conditional scenarios* from closed OHLC candles, not forecasts of
where price must go and never permission to trade. No exchange orders.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd


@dataclass(frozen=True)
class IndicativeZone:
    low: float
    high: float
    invalidation: float
    target_1: float
    target_2: float
    side: str
    basis: str


def support_resistance(candles: pd.DataFrame) -> tuple[IndicativeZone, IndicativeZone] | None:
    """Expose both sides even when the trading signal has no direction."""
    support = indicative_zone(candles, side="LONG")
    resistance = indicative_zone(candles, side="SHORT")
    return (support, resistance) if support is not None and resistance is not None else None


def indicative_zone(candles: pd.DataFrame, *, side: str = "LONG") -> IndicativeZone | None:
    """Project a watch scenario using only previous closed price candles.

    Avoid a point estimate without meaningful ranges; unavailable/bad inputs
    return None. Targets are illustrative scenarios and not backtested TP.
    """
    if side not in ("LONG", "SHORT") or len(candles) < 35:
        return None
    required = {"open", "high", "low", "close"}
    if not required.issubset(candles.columns):
        return None
    c = candles.tail(60)
    if c[list(required)].isna().any().any():
        return None
    if not (c[list(required)] > 0).all().all():
        return None
    prev = c.close.shift(1)
    tr = pd.concat((c.high-c.low, (c.high-prev).abs(), (c.low-prev).abs()), axis=1).max(axis=1)
    atr = float(tr.tail(14).mean())
    price = float(c.close.iloc[-1])
    if not math.isfinite(atr) or atr <= 0 or atr / price > .15:
        return None
    # Recent structural extremes, with the newest closed candle excluded so
    # the reference zone does not jump to the exact price being evaluated.
    reference = c.iloc[-25:-1]
    anchor = float(reference.low.min() if side == "LONG" else reference.high.max())
    if side == "LONG":
        low, high = max(0.0, anchor - .15 * atr), anchor + .20 * atr
        invalidation = anchor - .85 * atr
        target_1 = high + 1.5 * (high - invalidation)
        target_2 = high + 2.5 * (high - invalidation)
    else:
        low, high = anchor - .20 * atr, anchor + .15 * atr
        invalidation = anchor + .85 * atr
        target_1 = low - 1.5 * (invalidation - low)
        target_2 = low - 2.5 * (invalidation - low)
    if min(low, high, invalidation, target_1, target_2) <= 0:
        return None
    return IndicativeZone(low, high, invalidation, target_1, target_2,
                          side, "24 แท่งก่อนหน้าที่ปิดแล้ว + ATR14")
