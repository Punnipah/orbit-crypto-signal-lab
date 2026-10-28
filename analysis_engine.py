"""Deterministic indicators and transparent, non-predictive signal rules."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def indicators(source: pd.DataFrame) -> pd.DataFrame:
    if len(source) < 250:
        raise ValueError("ต้องมีแท่งเทียนอย่างน้อย 250 แท่ง")
    f = source.copy()
    high, low, close, volume = f["high"], f["low"], f["close"], f["volume"]

    for period in (20, 50, 200):
        f[f"ema{period}"] = close.ewm(span=period, adjust=False, min_periods=period).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    ratio = gain / loss.replace(0, np.nan)
    f["rsi"] = 100 - 100 / (1 + ratio)
    f.loc[(loss == 0) & (gain > 0), "rsi"] = 100.0
    f.loc[(loss == 0) & (gain == 0), "rsi"] = 50.0

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    f["macd"] = ema12 - ema26
    f["macd_signal"] = f["macd"].ewm(span=9, adjust=False, min_periods=9).mean()
    f["macd_hist"] = f["macd"] - f["macd_signal"]

    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    f["atr"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=f.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=f.index)
    plus_smoothed = plus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    minus_smoothed = minus_dm.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    f["plus_di"] = 100 * plus_smoothed / f["atr"].replace(0, np.nan)
    f["minus_di"] = 100 * minus_smoothed / f["atr"].replace(0, np.nan)
    di_total = f["plus_di"] + f["minus_di"]
    dx = 100 * (f["plus_di"] - f["minus_di"]).abs() / di_total.replace(0, np.nan)
    f["adx"] = dx.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    f["volume_ma20"] = volume.rolling(20).mean()
    f["breakout_high20"] = high.shift(1).rolling(20).max()
    f["breakout_low20"] = low.shift(1).rolling(20).min()
    f["support50"] = low.shift(1).rolling(50).min()
    f["resistance50"] = high.shift(1).rolling(50).max()
    return f


def _trend(row: pd.Series) -> int:
    if row["close"] > row["ema200"] and row["ema50"] > row["ema200"]:
        return 1
    if row["close"] < row["ema200"] and row["ema50"] < row["ema200"]:
        return -1
    return 0


def evaluate(base: pd.DataFrame, higher: pd.DataFrame, *, same_timeframe: bool = False) -> dict:
    f, h = indicators(base), indicators(higher)
    row, hrow = f.iloc[-1], h.iloc[-1]
    mandatory = ["ema200", "rsi", "macd_hist", "atr", "adx", "volume_ma20", "plus_di", "minus_di"]
    if not all(math.isfinite(float(row[name])) for name in mandatory):
        raise ValueError("ข้อมูลไม่เพียงพอต่อการคำนวณตัวชี้วัด")

    trend = _trend(row)
    higher_trend = 0 if same_timeframe else _trend(hrow)
    volume_ratio = float(row["volume"] / row["volume_ma20"]) if row["volume_ma20"] else 0.0

    factors: list[dict] = []

    def add(label: str, points: int, detail: str) -> None:
        factors.append({"label": label, "points": points, "detail": detail})

    add("แนวโน้มหลัก EMA50/200", 2 * trend, "ขาขึ้น" if trend > 0 else "ขาลง" if trend < 0 else "ยังไม่ชัด")
    ema_vote = 1 if row["ema20"] > row["ema50"] else -1 if row["ema20"] < row["ema50"] else 0
    add("โมเมนตัม EMA20/50", ema_vote, "EMA20 สูงกว่า EMA50" if ema_vote > 0 else "EMA20 ต่ำกว่า EMA50")
    macd_vote = 1 if row["macd_hist"] > 0 else -1 if row["macd_hist"] < 0 else 0
    add("MACD Histogram", macd_vote, "ฝั่งบวก" if macd_vote > 0 else "ฝั่งลบ" if macd_vote < 0 else "กลาง")
    rsi = float(row["rsi"])
    rsi_vote = 1 if 52 <= rsi <= 70 else -1 if 30 <= rsi <= 48 else 0
    add("RSI 14", rsi_vote, f"RSI = {rsi:.1f}")
    adx = float(row["adx"])
    adx_vote = 0
    if adx >= 22:
        adx_vote = 1 if row["plus_di"] > row["minus_di"] else -1 if row["plus_di"] < row["minus_di"] else 0
    add("ADX + Directional Movement", adx_vote, f"ADX = {adx:.1f}")
    breakout_vote = 0
    if volume_ratio >= 1.2:
        if row["close"] > row["breakout_high20"]:
            breakout_vote = 1
        elif row["close"] < row["breakout_low20"]:
            breakout_vote = -1
    add("Breakout พร้อม Volume", breakout_vote, f"Volume = {volume_ratio:.2f} เท่าของค่าเฉลี่ย")
    higher_detail = ("ไม่ได้เพิ่มคะแนน เพราะเป็น Timeframe เดียวกัน" if same_timeframe else
                     "ขาขึ้น" if higher_trend > 0 else "ขาลง" if higher_trend < 0 else "ยังไม่ชัด")
    add("แนวโน้ม Timeframe ใหญ่", 2 * higher_trend, higher_detail)

    score = sum(item["points"] for item in factors)
    threshold = 5 if same_timeframe else 6
    higher_ok_buy = same_timeframe or higher_trend == 1
    higher_ok_sell = same_timeframe or higher_trend == -1
    if score >= threshold and trend == 1 and higher_ok_buy and adx >= 18 and volume_ratio >= 0.75 and rsi < 75:
        signal = "BUY"
    elif score <= -threshold and trend == -1 and higher_ok_sell and adx >= 18 and volume_ratio >= 0.75 and rsi > 25:
        signal = "SELL"
    else:
        signal = "WAIT"

    price, atr = float(row["close"]), float(row["atr"])
    plan = None
    if signal == "BUY":
        stop = min(price - 1.5 * atr, float(row["support50"]) - 0.2 * atr)
        risk = price - stop
        plan = {"entry_reference": price, "invalidation": stop, "target1": price + risk * 1.5,
                "target2": price + risk * 2, "risk_percent": risk / price * 100}
    elif signal == "SELL":
        # SELL refers to reducing/selling existing spot holdings, not opening a short.
        invalidation = max(price + 1.5 * atr, float(row["resistance50"]) + 0.2 * atr)
        plan = {"entry_reference": price, "invalidation": invalidation,
                "target1": max(0, price - (invalidation - price) * 1.5),
                "target2": max(0, price - (invalidation - price) * 2),
                "risk_percent": (invalidation - price) / price * 100}

    return {"frame": f, "higher_frame": h, "signal": signal, "score": score, "max_score": 7 if same_timeframe else 9,
            "factors": factors,
            "price": price, "rsi": rsi, "adx": adx, "atr": atr,
            "support": float(row["support50"]), "resistance": float(row["resistance50"]),
            "volume_ratio": volume_ratio, "higher_trend": higher_trend,
            "last_candle_start": f.index[-1], "plan": plan}
