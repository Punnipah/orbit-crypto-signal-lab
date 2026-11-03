"""Closed-candle multi-timeframe live decision support.

This module reports conditional reference plans, not executable quotes, trade
instructions, a validated profit edge, or orders. It never touches production.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

import numpy as np
import pandas as pd

from orbit_model_lab_engine import DataUnavailable, validate_candles


@dataclass(frozen=True)
class LivePlan:
    status: str
    direction: str
    regime: str
    strength: str
    reference_close: float
    closed_at: datetime
    entry_reference: float | None
    entry_zones: tuple[tuple[str, float, float, str], ...]
    stop: float | None
    take_profit_1: float | None
    take_profit_2: float | None
    reward_to_risk: float | None
    risk_usdt: float | None
    max_notional_usdt: float | None
    checks: tuple[tuple[str, bool], ...]
    explanations: tuple[str, ...]
    volume_ratio: float
    rsi: float
    atr_pct: float
    exchange_futures: bool


def _completed_bars(frame: pd.DataFrame, minutes: int) -> pd.DataFrame:
    expected = minutes // 5
    ohlcv = frame[["open", "high", "low", "close", "volume"]].resample(
        f"{minutes}min", label="left", closed="left"
    ).agg({"open": "first", "high": "max", "low": "min",
           "close": "last", "volume": "sum"})
    count = frame["close"].resample(
        f"{minutes}min", label="left", closed="left"
    ).count()
    return ohlcv.loc[count == expected].dropna()


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    change = close.diff()
    average_gain = change.clip(lower=0).ewm(
        alpha=1 / length, adjust=False, min_periods=length
    ).mean()
    average_loss = (-change.clip(upper=0)).ewm(
        alpha=1 / length, adjust=False, min_periods=length
    ).mean()
    rs = average_gain / average_loss.replace(0, np.nan)
    result = 100 - 100 / (1 + rs)
    return result.fillna(50)


def _ema(close: pd.Series, length: int) -> pd.Series:
    return close.ewm(span=length, adjust=False, min_periods=length).mean()


def _zone(label: str, low: float, high: float, condition: str) -> tuple[str, float, float, str]:
    return (label, max(0.0, min(low, high)), max(low, high), condition)


def build_live_plan(data: pd.DataFrame, venue: str, *,
                    capital_usdt: float = 75.0,
                    fee_each_side_bps: float = 10.0,
                    slippage_each_side_bps: float = 5.0,
                    risk_pct: float = 0.5) -> LivePlan:
    """Generate a conditional plan from one exchange's *closed* 5m candles.

    15m/1h/4h candles are built only from complete 5m groups. The last completed
    5m candle is the sole trigger; no lookahead or synthetic future prices.
    """
    futures = venue in {"BINANCE_GLOBAL_USDM", "BITGET_USDT_FUTURES"}
    if venue not in {"BINANCE_TH_SPOT", "BINANCE_GLOBAL_USDM", "BITGET_USDT_FUTURES"}:
        raise DataUnavailable("ตลาดนี้ไม่อยู่ในรายการที่รองรับ")
    if not (math.isfinite(capital_usdt) and 10 <= capital_usdt <= 1_000_000
            and math.isfinite(risk_pct) and 0.1 <= risk_pct <= 2
            and math.isfinite(fee_each_side_bps) and 0 <= fee_each_side_bps <= 100
            and math.isfinite(slippage_each_side_bps) and 0 <= slippage_each_side_bps <= 100):
        raise DataUnavailable("ค่าทุนหรือความเสี่ยงไม่ถูกต้อง")

    frame = validate_candles(data, require_fresh=False)
    if len(frame) < 1600:
        raise DataUnavailable("ข้อมูลไม่พอสำหรับวิเคราะห์หลายกรอบเวลา")
    h4 = _completed_bars(frame, 240)
    h1 = _completed_bars(frame, 60)
    m15 = _completed_bars(frame, 15)
    if len(h4) < 24 or len(h1) < 120 or len(m15) < 65:
        raise DataUnavailable("แท่งเวลาสูงที่ปิดครบมีไม่พอ")

    c = frame.close
    ema9, ema21 = _ema(c, 9), _ema(c, 21)
    atr_series = pd.concat([
        frame.high - frame.low,
        (frame.high - c.shift()).abs(),
        (frame.low - c.shift()).abs()
    ], axis=1).max(axis=1).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    current = frame.iloc[-1]
    prev = frame.iloc[-2]
    close = float(current.close)
    atr = float(atr_series.iloc[-1])
    if not (math.isfinite(atr) and atr > 0 and math.isfinite(close) and close > 0):
        raise DataUnavailable("คำนวณความผันผวนไม่ได้")
    volume_base = float(frame.volume.iloc[-21:-1].mean())
    volume_ratio = float(current.volume / max(volume_base, 1e-12))
    rsi = float(_rsi(c).iloc[-1])

    h4_close, h4_ema20 = float(h4.close.iloc[-1]), float(_ema(h4.close, 20).iloc[-1])
    h1_close = float(h1.close.iloc[-1])
    h1_ema50, h1_ema100 = float(_ema(h1.close, 50).iloc[-1]), float(_ema(h1.close, 100).iloc[-1])
    m15_close = float(m15.close.iloc[-1])
    m15_ema21, m15_ema55 = float(_ema(m15.close, 21).iloc[-1]), float(_ema(m15.close, 55).iloc[-1])
    if not all(math.isfinite(x) for x in (
        h4_ema20, h1_ema50, h1_ema100, m15_ema21, m15_ema55
    )):
        raise DataUnavailable("EMA กรอบเวลาสูงไม่พร้อม")

    votes = (
        1 if h4_close > h4_ema20 else -1,
        1 if h1_close > h1_ema100 and h1_ema50 > h1_ema100 else
        (-1 if h1_close < h1_ema100 and h1_ema50 < h1_ema100 else 0),
        1 if m15_close > m15_ema55 and m15_ema21 > m15_ema55 else
        (-1 if m15_close < m15_ema55 and m15_ema21 < m15_ema55 else 0),
    )
    vote_sum = sum(votes)
    regime = "UPTREND" if vote_sum >= 2 else ("DOWNTREND" if vote_sum <= -2 else "SIDEWAYS / MIXED")
    strength = f"{sum(v == (1 if vote_sum > 0 else -1) for v in votes)}/3 TF ยืนทิศเดียวกัน"
    # The observed support/resistance is from completed 5m bars, excluding the
    # signal candle, so a trigger cannot rewrite its own reference levels.
    support = float(frame.low.iloc[-21:-1].min())
    resistance = float(frame.high.iloc[-21:-1].max())
    avg9, avg21 = float(ema9.iloc[-1]), float(ema21.iloc[-1])
    buy_trigger = bool(
        current.close > current.open and current.close > avg9 and
        current.low <= avg9 and current.close > avg21 and
        volume_ratio >= 0.8 and 45 <= rsi <= 72 and close <= avg9 + 1.0 * atr
    )
    sell_trigger = bool(
        current.close < current.open and current.close < avg9 and
        current.high >= avg9 and current.close < avg21 and
        volume_ratio >= 0.8 and 28 <= rsi <= 55 and close >= avg9 - 1.0 * atr
    )

    explanations: list[str] = []
    if regime == "UPTREND":
        direction = "LONG" if futures else "BUY"
        zones = (
            _zone("ZONE 1 · Pullback", avg21 - .22 * atr, avg9 + .12 * atr,
                  "รอราคาแตะ EMA9/21 แล้วแท่ง 5m ปิดกลับขึ้น"),
            _zone("ZONE 2 · Support", support - .12 * atr, support + .20 * atr,
                  "รอดีดจากแนวรับและปริมาณซื้อยืนยัน"),
            _zone("ZONE 3 · Breakout", resistance + .05 * atr, resistance + .22 * atr,
                  "รอแท่ง 5m ปิดเหนือแนวต้านพร้อม Volume"),
        )
        valid_trigger = buy_trigger
        ref = close if valid_trigger else (zones[0][1] + zones[0][2]) / 2
        stop = min(support - .5 * atr, zones[0][1] - .7 * atr)
        explanations.append("แนวโน้มกรอบเวลาสูงสนับสนุนฝั่งขึ้น")
    elif regime == "DOWNTREND" and futures:
        direction = "SHORT"
        zones = (
            _zone("ZONE 1 · Pullback", avg9 - .12 * atr, avg21 + .22 * atr,
                  "รอราคาแตะ EMA9/21 แล้วแท่ง 5m ปิดกลับลง"),
            _zone("ZONE 2 · Resistance", resistance - .20 * atr, resistance + .12 * atr,
                  "รอถูกปฏิเสธที่แนวต้านพร้อม Volume"),
            _zone("ZONE 3 · Breakdown", support - .22 * atr, support - .05 * atr,
                  "รอแท่ง 5m ปิดใต้แนวรับพร้อม Volume"),
        )
        valid_trigger = sell_trigger
        ref = close if valid_trigger else (zones[0][1] + zones[0][2]) / 2
        stop = max(resistance + .5 * atr, zones[0][2] + .7 * atr)
        explanations.append("แนวโน้มกรอบเวลาสูงสนับสนุนฝั่งลง")
    else:
        direction = "NONE"
        zones = (
            _zone("SUPPORT WATCH", support - .15 * atr, support + .22 * atr,
                  "เฝ้าดูแรงซื้อเท่านั้น จนกว่า TF สูงจะยืนยัน"),
            _zone("RESISTANCE WATCH", resistance - .22 * atr, resistance + .15 * atr,
                  "เฝ้าดูแรงขายเท่านั้น จนกว่า TF สูงจะยืนยัน"),
            _zone("BREAKOUT WATCH", resistance + .05 * atr, resistance + .22 * atr,
                  "ดูแท่ง 15m ปิดเหนือกรอบก่อนพิจารณาแผนใหม่"),
        )
        if regime == "DOWNTREND" and not futures:
            explanations.append("Spot ห้าม SHORT · ขาลงจึงไม่มีแผนเปิดซื้อสวนเทรนด์")
        else:
            explanations.append("TF สูงยังขัดกัน ตลาด Sideways/Mixed · ไม่เดาฝั่ง")
        valid_trigger = False
        ref = None
        stop = None

    cost_bps = 2 * (fee_each_side_bps + slippage_each_side_bps)
    costs_ok = atr / close * 10_000 >= cost_bps * 1.2
    volume_ok = volume_ratio >= 0.8
    chasing = bool(direction in ("BUY", "LONG") and close > zones[0][2] + .8 * atr) if ref else False
    chasing = chasing or (
        bool(direction == "SHORT" and close < zones[0][1] - .8 * atr) if ref else False
    )
    # A plan can be labelled SIGNAL only after the current closed 5m bar
    # actually confirmed it; a projection or an opposing TF stays WATCH.
    if direction == "NONE":
        status = "NO TRADE"
    elif not costs_ok:
        status = "NO TRADE"
        explanations.append("ATR เล็กเมื่อเทียบกับ Fee/Slippage · ความคุ้มค่าต่ำ")
    elif chasing:
        status = f"WATCH {direction}"
        explanations.append("ราคาไกลโซนแล้ว ห้ามไล่ซื้อ/ไล่ Short")
    elif valid_trigger:
        status = f"SIGNAL {direction}"
        explanations.append("แท่ง 5m ปิดยืนยันตามทิศทาง · ตรวจราคา Bid/Ask จริงก่อนตัดสินใจ")
    else:
        status = f"WATCH {direction}"
        explanations.append("เฝ้ารอแท่ง 5m ปิดกลับตามทิศทางและ Volume ≥0.8x")

    tp1 = tp2 = rr = risk_usdt = notional = None
    if ref is not None and stop is not None and ref > 0:
        distance = abs(ref - stop)
        if distance <= 0 or distance / ref > .06 or distance / ref < .002:
            status = "NO TRADE"
            explanations.append("ระยะ Stop ไม่สมเหตุสมผลกับราคาและ ATR")
        else:
            signed = 1 if direction in ("BUY", "LONG") else -1
            tp1 = ref + signed * 1.5 * distance
            tp2 = ref + signed * 2.5 * distance
            rr = 2.5
            risk_usdt = capital_usdt * risk_pct / 100
            notional = min(capital_usdt, risk_usdt / (distance / ref))

    checks = (
        ("4H สนับสนุนฝั่งที่เลือก", direction != "NONE" and votes[0] == (1 if direction != "SHORT" else -1)),
        ("1H สนับสนุนฝั่งที่เลือก", direction != "NONE" and votes[1] == (1 if direction != "SHORT" else -1)),
        ("15M สนับสนุนฝั่งที่เลือก", direction != "NONE" and votes[2] == (1 if direction != "SHORT" else -1)),
        ("5M มีแท่งยืนยัน", valid_trigger),
        ("ATR สูงพอเมื่อเทียบต้นทุน", costs_ok),
    )
    return LivePlan(
        status=status, direction=direction, regime=regime, strength=strength,
        reference_close=close,
        closed_at=frame.index[-1].to_pydatetime() + pd.Timedelta(minutes=5),
        entry_reference=ref, entry_zones=zones, stop=stop,
        take_profit_1=tp1, take_profit_2=tp2, reward_to_risk=rr,
        risk_usdt=risk_usdt, max_notional_usdt=notional,
        checks=checks, explanations=tuple(explanations),
        volume_ratio=volume_ratio, rsi=rsi, atr_pct=atr / close * 100,
        exchange_futures=futures,
    )
