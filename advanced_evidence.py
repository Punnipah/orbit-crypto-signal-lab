"""Causal, exchange-labeled quantitative Spot evidence.

Everything here is derived from *completed Binance Spot candles*.
No candle-derived volume profile is claimed to be tick-accurate order flow.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SpotEvidence:
    timeframe: str
    cvd_20_base: float | None
    delta_share20: float | None
    delta_share5: float | None
    candle_vwap: float | None
    price_to_vwap_pct: float | None
    candle_volume_poc: float | None
    atr_pct: float | None
    atr_regime_percentile: float | None
    sweep_reclaim: bool
    source: str = "Binance Spot completed klines (taker buy + OHLCV; approximations labeled)"


def _finite(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def analyze_spot_evidence(features: pd.DataFrame, timeframe: str) -> SpotEvidence:
    """Read-only momentum, rolling CVD, candle-approximated VWAP/POC.

    Note that exchange kline *taker buy base volume* is actual aggregate trade
    side for that candle, but POC and VWAP use candle typical price rather
    than the original sequence of individual executions.
    """
    if timeframe not in ("15m", "1h", "4h", "1d") or features.empty:
        raise ValueError("กรอบเวลา/ข้อมูล Spot ไม่พร้อม")
    required = ("high", "low", "close", "volume", "atr")
    if any(k not in features for k in required) or len(features) < 30:
        raise ValueError("ต้องมีแท่ง OHLCV อย่างน้อย 30 แท่ง")
    f = features.copy()
    f["typical"] = (f["high"] + f["low"] + f["close"]) / 3
    f["quote_weight"] = f["volume"] * f["typical"]

    n = {"15m": 96, "1h": 24, "4h": 6, "1d": 7}[timeframe]
    window = f.tail(n)
    base_sum = float(window["volume"].sum())
    vwap = (float((window["typical"] * window["volume"]).sum()) / base_sum
            if base_sum > 0 else None)
    close = _finite(f["close"].iloc[-1])
    distance = ((close / vwap - 1) * 100 if vwap and close else None)

    tail = f.tail(120)
    # Histogram of bar typical prices weighted by approx quote volume; not a
    # transaction-price histogram, true Volume Profile or Level 2 heatmap.
    typical = tail["typical"].to_numpy(dtype=float)
    volumes = tail["quote_weight"].to_numpy(dtype=float)
    valid = np.isfinite(typical) & np.isfinite(volumes) & (volumes >= 0)
    poc = None
    if valid.sum() >= 24 and volumes[valid].sum() > 0:
        prices, weights = typical[valid], volumes[valid]
        if prices.max() == prices.min():
            poc = float(prices[0])
        else:
            hist, edges = np.histogram(prices, bins=24, weights=weights)
            j = int(np.argmax(hist))
            poc = float((edges[j] + edges[j+1]) / 2)

    atr = _finite(f["atr"].iloc[-1])
    atr_pct = (100 * atr / close if close and atr is not None and atr >= 0 else None)
    pct_series = 100 * f["atr"].tail(120) / f["close"].tail(120).replace(0, np.nan)
    past = pct_series.dropna().to_numpy(dtype=float)
    atr_rank = (100 * float((past <= atr_pct).sum()) / len(past)
                if atr_pct is not None and len(past) >= 50 else None)

    cvd = buy20 = buy5 = None
    if "taker_buy_base" in f and len(f) >= 20:
        twenty = f.tail(20)
        taker = pd.to_numeric(twenty["taker_buy_base"], errors="coerce")
        vol = pd.to_numeric(twenty["volume"], errors="coerce")
        if (taker.notna().all() and vol.notna().all()
                and (taker >= 0).all() and (taker <= vol * (1 + 1e-8)).all()
                and vol.sum() > 0):
            cvd = float((2 * taker - vol).sum())
            buy20 = float(taker.sum() / vol.sum())
            if vol.tail(5).sum() > 0:
                buy5 = float(taker.tail(5).sum() / vol.tail(5).sum())

    return SpotEvidence(
        timeframe=timeframe, cvd_20_base=cvd,
        delta_share20=buy20, delta_share5=buy5,
        candle_vwap=vwap, price_to_vwap_pct=distance,
        candle_volume_poc=poc, atr_pct=atr_pct,
        atr_regime_percentile=atr_rank,
        sweep_reclaim=bool(f.iloc[-1].get("sweep_low", False)),
    )


def interpret_spot_evidence(item: SpotEvidence) -> tuple[str, ...]:
    """Descriptive, not an optimized/validated trading rule."""
    messages = []
    if item.delta_share20 is None:
        messages.append("CVD/Taker Buy ไม่พร้อม — ไม่สร้างค่าแทน")
    else:
        messages.append(f"20-bar CVD (base): {item.cvd_20_base:+,.4f} · "
                        f"Taker buy {item.delta_share20*100:.1f}% · "
                        f"5-bar {item.delta_share5*100:.1f}%" if item.delta_share5 is not None
                        else f"20-bar Taker buy {item.delta_share20*100:.1f}%")
    if item.candle_vwap is not None:
        messages.append(f"VWAP จากราคาแท่งโดยประมาณ: ห่างราคาปิด {item.price_to_vwap_pct:+.2f}% "
                        "(ไม่ใช่ Tick VWAP)")
    if item.atr_regime_percentile is not None:
        messages.append(f"ATR volatility percentile (120 แท่ง): {item.atr_regime_percentile:.0f}%")
    if item.sweep_reclaim:
        messages.append("พบการ Sweep Low ตามกฎ Pivot/แท่งปิด; ต้องตรวจการยืนราคาเพิ่ม")
    if item.candle_volume_poc is not None:
        messages.append("มี POC จากราคาเฉลี่ยของแท่งที่ถ่วงน้ำหนัก Volume: "
                        "เป็นการประมาณ ไม่ใช่ Volume Profile จากทุกดีล")
    return tuple(messages)
