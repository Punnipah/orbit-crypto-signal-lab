"""One causal signal engine shared by the dashboard and historical simulation."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from analysis_engine import indicators
from binance_data import HIGHER_TIMEFRAME, TIMEFRAMES
from market_structure import structure_features


def prepare_features(base: pd.DataFrame, higher: pd.DataFrame, timeframe: str,
                     *, pivot_bars: int = 3) -> pd.DataFrame:
    """Compute all features using current/past completed candles only.

    A higher-timeframe candle is available only at its *close* timestamp.
    Confirmed pivots appear only after pivot_bars right-hand candles close.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError("Timeframe ไม่ถูกต้อง")
    f = indicators(base)
    f = f.join(structure_features(base, pivot_bars=pivot_bars))
    htf = HIGHER_TIMEFRAME[timeframe]
    same_tf = htf == timeframe
    f["trend"] = np.select(
        [(f["close"] > f["ema200"]) & (f["ema50"] > f["ema200"]),
         (f["close"] < f["ema200"]) & (f["ema50"] < f["ema200"])], [1, -1], default=0,
    ).astype(int)
    if same_tf:
        f["higher_trend"] = 0
    else:
        h = indicators(higher)
        htrend = np.select(
            [(h["close"] > h["ema200"]) & (h["ema50"] > h["ema200"]),
             (h["close"] < h["ema200"]) & (h["ema50"] < h["ema200"])], [1, -1], default=0,
        ).astype(int)
        left = pd.DataFrame({"available_at": f.index + timedelta(minutes=TIMEFRAMES[timeframe])})
        right = pd.DataFrame({"known_at": h.index + timedelta(minutes=TIMEFRAMES[htf]),
                              "higher_trend": htrend})
        matched = pd.merge_asof(left.sort_values("available_at"), right.sort_values("known_at"),
                                left_on="available_at", right_on="known_at", direction="backward")
        f["higher_trend"] = pd.Series(matched["higher_trend"].fillna(0).to_numpy(dtype=int), index=f.index)

    f["volume_ratio"] = f["volume"] / f["volume_ma20"].replace(0, np.nan)
    if "taker_buy_base" in f:
        taker = f["taker_buy_base"]
        # Share of aggressively executed BUY volume over the last 20 *closed*
        # candles. This is an anonymous market-flow proxy, not a whale ID.
        f["taker_buy_share20"] = (taker.rolling(20, min_periods=20).sum()
                                   / f["volume"].rolling(20, min_periods=20).sum().replace(0, np.nan))
        f["taker_net_flow20"] = (2 * taker - f["volume"]).rolling(20, min_periods=20).sum()
    else:
        f["taker_buy_share20"] = np.nan
        f["taker_net_flow20"] = np.nan
    ema_vote = np.select([f["ema20"] > f["ema50"], f["ema20"] < f["ema50"]], [1, -1], default=0)
    macd_vote = np.select([f["macd_hist"] > 0, f["macd_hist"] < 0], [1, -1], default=0)
    rsi_vote = np.select([f["rsi"].between(52, 70), f["rsi"].between(30, 48)], [1, -1], default=0)
    adx_vote = np.select([(f["adx"] >= 22) & (f["plus_di"] > f["minus_di"]),
                          (f["adx"] >= 22) & (f["plus_di"] < f["minus_di"])], [1, -1], default=0)
    breakout_vote = np.select(
        [(f["volume_ratio"] >= 1.2) & (f["close"] > f["breakout_high20"]),
         (f["volume_ratio"] >= 1.2) & (f["close"] < f["breakout_low20"])], [1, -1], default=0,
    )
    f["score"] = (2 * f["trend"] + ema_vote + macd_vote + rsi_vote + adx_vote + breakout_vote
                  + 2 * f["higher_trend"])
    valid = f[["ema200", "rsi", "macd_hist", "atr", "adx", "volume_ma20"]].notna().all(axis=1)
    f["buy_gate"] = (valid & (f["trend"] == 1) & (f["adx"] >= 18) & (f["volume_ratio"] >= 0.75)
                     & (f["rsi"] < 75) & (f["structure_bias"] >= 0) & ~f["sweep_high"])
    f["sell_gate"] = (valid & (f["trend"] == -1) & (f["adx"] >= 18) & (f["volume_ratio"] >= 0.75)
                      & (f["rsi"] > 25) & (f["structure_bias"] <= 0) & ~f["sweep_low"])
    if not same_tf:
        f["buy_gate"] = f["buy_gate"] & (f["higher_trend"] == 1)
        f["sell_gate"] = f["sell_gate"] & (f["higher_trend"] == -1)
    f["threshold"] = 5 if same_tf else 6
    return f


def with_signal(features: pd.DataFrame, threshold: int | None = None) -> pd.DataFrame:
    f = features.copy()
    effective = f["threshold"] if threshold is None else threshold
    f["signal"] = np.select([
        f["buy_gate"] & (f["score"] >= effective),
        f["sell_gate"] & (f["score"] <= -effective),
    ], ["BUY", "SELL"], default="WAIT")
    return f


def latest_reasons(row: pd.Series, timeframe: str) -> list[str]:
    lines = [
        f"คะแนนเทคนิค {int(row['score']):+d}/{7 if timeframe == '1d' else 9} · ADX {row['adx']:.1f} · RSI {row['rsi']:.1f}",
        f"แนวโน้มหลัก: {'ขึ้น' if row['trend'] > 0 else 'ลง' if row['trend'] < 0 else 'ยังไม่ชัด'}",
        f"โครงสร้างราคา: {'ขาขึ้น' if row['structure_bias'] > 0 else 'ขาลง' if row['structure_bias'] < 0 else 'ยังไม่ยืนยัน'}",
        f"Volume เทียบค่าเฉลี่ย 20 แท่ง: {row['volume_ratio']:.2f}×",
    ]
    if timeframe != "1d":
        lines.append(f"Timeframe ใหญ่: {'ขึ้น' if row['higher_trend'] > 0 else 'ลง' if row['higher_trend'] < 0 else 'ยังไม่ชัด'}")
    if row["sweep_high"]:
        lines.append("พบการกวาดสภาพคล่องเหนือ Pivot High: ระวังการซื้อไล่ราคา")
    if row["sweep_low"]:
        lines.append("พบการกวาดสภาพคล่องใต้ Pivot Low: ระวังการขายไล่ราคา")
    if row["bos_up"] or row["bos_down"]:
        lines.append("เกิด Break of Structure บนแท่งปิดล่าสุด")
    if row["choch_up"] or row["choch_down"]:
        lines.append("เกิด Change of Character หลังโครงสร้างราคาสลับทิศ")
    if row["structure_bias"] != 0 and row["structure_bias"] != row["trend"]:
        lines.append("โครงสร้างราคาและแนวโน้ม EMA ยังขัดแย้งกัน")
    return lines
