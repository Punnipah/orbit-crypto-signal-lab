"""v5.9.2 SHORT Opportunity Watch (public, same-venue research only).

This module NEVER creates a trade entry, stop, target, qty, READY, alert or
Futures proxy. An optional Spot observation is explicitly tagged SPOT-ONLY.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

from scalp_engine import _ema
from scalp_marketdata import MarketSnapshot


@dataclass(frozen=True)
class ShortWatch:
    state: str
    reason: str
    source_venue: str
    symbol: str
    checked_at: datetime
    checks: tuple[tuple[str, bool, str], ...] = ()
    frame_high: float | None = None
    frame_low: float | None = None
    price: float | None = None


def evaluate_short_watch(snapshot: MarketSnapshot) -> ShortWatch:
    """Detect early weakness from *closed* candles, not executable shorts.

    The watch requires either proximity to a prior 1H resistance or a fresh,
    unextended 5m breakdown; old support/extended selloffs are never entries.
    """
    venue, symbol, now = snapshot.venue, snapshot.symbol, snapshot.checked_at

    def observation(state: str, reason: str, **extra) -> ShortWatch:
        return ShortWatch(state, reason, venue, symbol, now, **extra)

    one, five, fifteen, hour = (snapshot.frames.get(k) for k in ("1m", "5m", "15m", "1h"))
    if (hour is None or one is None or five is None or fifteen is None or
            min(len(one), len(five), len(fifteen), len(hour)) < 35 or
            now.tzinfo is None):
        return observation("INSUFFICIENT_DATA", "1H/15m/5m/1m ที่ปิดแล้วไม่ครบ · ห้ามอนุมาน SHORT")
    price = (snapshot.bid + snapshot.ask) / 2
    if not math.isfinite(price) or price <= 0 or snapshot.ask <= snapshot.bid:
        return observation("INSUFFICIENT_DATA", "ราคา Bid/Ask ไม่ถูกต้อง")
    # Exclude the current last 1H bar from defining the historical boundary;
    # all bars supplied by MarketSnapshot have closed.
    prior_h = hour.iloc[-13:-1]
    high_h, low_h = float(prior_h.high.max()), float(prior_h.low.min())
    width = high_h - low_h
    if not (math.isfinite(width) and width > 0 and low_h > 0):
        return observation("INSUFFICIENT_DATA", "กรอบ 1H ไม่สมบูรณ์")

    # An upper-edge failure is watchable before or immediately after a turn.
    # A fresh 5m support break is watchable only within 0.4% of its level.
    near_upper = high_h - width * .28 <= price <= high_h + width * .08
    previous_five = five.iloc[-13:-1]
    base_low = float(previous_five.low.min())
    breakdown = (price < base_low and (base_low - price) / base_low <= .004)
    at_structure = bool(near_upper or breakdown)
    ema9_15, ema21_15 = _ema(fifteen.close, 9), _ema(fifteen.close, 21)
    trend = bool(float(fifteen.close.iloc[-1]) < float(ema9_15.iloc[-1]) and
                 float(ema9_15.iloc[-1]) <= float(ema21_15.iloc[-1]))
    ema9_5 = _ema(five.close, 9)
    five_down = bool(float(five.close.iloc[-1]) < float(ema9_5.iloc[-1]) and
                     float(five.close.iloc[-1]) < float(five.close.iloc[-2]))
    last_one = one.iloc[-1]
    one_down = bool(float(last_one.close) < float(last_one.open) and
                    float(last_one.close) <= float(one.close.iloc[-2]))
    flow_ratio = (float(last_one.taker_buy / last_one.volume)
                  if last_one.volume > 0 else float("nan"))
    sell_flow = bool(math.isfinite(flow_ratio) and flow_ratio <= .47)
    checks = (
        ("1H/5m โครงสร้างขาลงที่ยังไม่ไล่ราคา", at_structure,
         "ใกล้แนวต้าน 1H หรือเพิ่งหลุดกรอบ 5m ไม่เกิน 0.4%"),
        ("15m เริ่มเอนลง", trend, "Close ต่ำกว่า EMA9 และ EMA9 ไม่สูงกว่า EMA21"),
        ("5m แรงลง", five_down, "Close ต่ำกว่า EMA9 และต่ำกว่าแท่งก่อน"),
        ("1m แท่งแดงปิดแล้ว", one_down, "Close ต่ำกว่า Open และไม่สูงกว่า Close ก่อนหน้า"),
        ("1m Sell Flow", sell_flow,
         f"Taker Sell {1-flow_ratio:.0%}" if math.isfinite(flow_ratio) else "Flow ไม่ครบ"),
    )
    count = sum(ok for _, ok, _ in checks)
    if at_structure and (five_down or one_down) and count >= 3:
        state = "SHORT_WATCH"
        reason = ("แรงขายใกล้แนวต้าน 1H" if near_upper else
                  "เพิ่งหลุดแนวรับ 5m โดยยังไม่ไล่ราคาลง")
    elif at_structure and count >= 2:
        state, reason = "EARLY_WATCH", "เริ่มเห็นแรงขาย แต่ยังขาดการยืนยันระยะสั้น"
    else:
        state, reason = "NO_SETUP", "ยังไม่เห็น SHORT Watch ใกล้จุดโครงสร้างที่เหมาะสม"
    return observation(state, reason + f" · ผ่าน {count}/5 ข้อเฝ้าดู (ไม่ใช่ READY)",
                       checks=checks, frame_high=high_h, frame_low=low_h, price=price)
