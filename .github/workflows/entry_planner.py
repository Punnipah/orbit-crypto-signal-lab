"""Causal, read-only long-side entry plans from completed Spot candles.

This prospective heuristic is NOT included in backtesting or walk-forward.
It never places orders or implies a profitable or guaranteed entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Mapping

from binance_data import TIMEFRAMES


@dataclass(frozen=True)
class EntryPlan:
    status: str
    reason: str
    anchor_name: str | None = None
    anchor_price: float | None = None
    entry_low: float | None = None
    entry_high: float | None = None
    stop_loss: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    position_qty: float | None = None
    estimated_risk: float | None = None
    notional: float | None = None
    risk_budget: float | None = None
    last_closed_at: datetime | None = None
    next_check_at: datetime | None = None
    expires_at: datetime | None = None


def _valid_positive(row: Mapping, name: str) -> float | None:
    try:
        value = float(row.get(name, math.nan))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def plan_entry(
    row: Mapping,
    timeframe: str,
    final_signal: str,
    last_closed_at: datetime,
    *,
    capital: float,
    risk_pct: float,
    max_allocation_pct: float,
    fee_pct: float,
    slippage_pct: float,
    data_ok: bool = True,
    current_price: float | None = None,
) -> EntryPlan:
    """Return a conditional buy zone, or explain why none is valid.

    Support candidates must be already known at the *last completed* candle.
    The planner uses no future bars and never changes a BUY/WAIT/SELL signal.
    TP1/TP2 are illustrative gross 1.5R/2.5R from the zone's high edge.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError("Timeframe ไม่ถูกต้อง")
    if last_closed_at.tzinfo is None:
        raise ValueError("เวลาปิดแท่งต้องมีเขตเวลา")
    params = (capital, risk_pct, max_allocation_pct, fee_pct, slippage_pct)
    if not all(math.isfinite(v) for v in params):
        raise ValueError("ค่าการจัดการความเสี่ยงต้องเป็นตัวเลขที่ใช้ได้")
    if capital <= 0 or not 0 < risk_pct <= 100 or not 0 < max_allocation_pct <= 100:
        raise ValueError("ทุนหรือสัดส่วนความเสี่ยงไม่ถูกต้อง")
    if fee_pct < 0 or slippage_pct < 0:
        raise ValueError("ต้นทุนการเทรดต้องไม่ติดลบ")
    if not data_ok:
        return EntryPlan("INVALID", "ข้อมูลแท่งเทียนขาดหายหรือเก่า: ยังไม่คำนวณราคาเข้าซื้อ")

    close = _valid_positive(row, "close")
    open_price = _valid_positive(row, "open")
    atr = _valid_positive(row, "atr")
    if close is None or atr is None:
        return EntryPlan("NO_SETUP", "ราคา/ATR ยังไม่ครบหรือใช้ไม่ได้")

    # Trade only in a supportive trend/structure; a liquidity sweep over
    # confirmed resistance is treated as a potential bull trap.
    if row.get("trend") != 1:
        return EntryPlan("INVALID", "แนวโน้ม Spot ยังไม่เป็นขาขึ้น: ไม่เสนอจุดซื้อฝืนเทรนด์")
    if timeframe != "1d" and row.get("higher_trend") != 1:
        return EntryPlan("INVALID", "Timeframe ใหญ่ยังไม่เป็นขาขึ้น: รอการยืนยันก่อน")
    if row.get("structure_bias", 0) < 0:
        return EntryPlan("INVALID", "Market Structure ยังเป็นขาลง: ไม่เสนอแผนซื้อ")
    if bool(row.get("sweep_high", False)):
        return EntryPlan("INVALID", "พบ Liquidity Sweep เหนือ Pivot High: ระวัง Bull Trap")

    # Retest of broken confirmed pivot-high is one candidate. Otherwise use
    # confirmed pivot-low, rolling support, and moving-average supports.
    candidates: list[tuple[float, int, str, float]] = []
    high_pivot = _valid_positive(row, "pivot_high")
    if high_pivot is not None and high_pivot < close and close - high_pivot <= 1.5 * atr:
        candidates.append(((close - high_pivot) / atr - 0.15, 0, "Pivot High ที่ทะลุแล้ว (รอ Retest)", high_pivot))
    for rank, (name, label) in enumerate((
        ("pivot_low", "Pivot Low ที่ยืนยันแล้ว"),
        ("support50", "แนวรับ 50 แท่ง"),
        ("ema20", "EMA20 (แนวรับเคลื่อนที่)"),
        ("ema50", "EMA50 (แนวรับเคลื่อนที่)"),
    ), start=1):
        support = _valid_positive(row, name)
        if support is None or support > close or close - support > 3 * atr:
            continue
        # A nearby confirmed structure level gets a small preference; never
        # choose a remote support just because of its type.
        candidates.append(((close - support) / atr + 0.03 * rank, rank, label, support))
    if not candidates:
        return EntryPlan("NO_SETUP", "ไม่มีแนวรับหรือจุด Retest ใกล้ราคาพอ: ไม่สร้างโซนซื้อจากการคาดเดา")

    _, _, anchor_name, anchor = min(candidates)
    low = max(anchor - 0.30 * atr, close * 1e-12)
    high = anchor + 0.30 * atr
    if not (0 < low < high):
        return EntryPlan("NO_SETUP", "ช่วงราคาไม่สมเหตุสมผล")

    # Put stops under the entire zone. Use a nearby confirmed pivot-low if it
    # gives a stricter structural invalidation; never move a stop above zone.
    stop = low - 0.75 * atr
    pivot_low = _valid_positive(row, "pivot_low")
    if pivot_low is not None and pivot_low <= low and low - pivot_low <= 1.5 * atr:
        stop = min(stop, pivot_low - 0.35 * atr)
    if stop <= 0 or high - stop > 0.25 * high:
        return EntryPlan("NO_SETUP", "Stop Loss จากความผันผวนอยู่ไกล/ต่ำเกินไป: ไม่มีแผนซื้อที่ควบคุมความเสี่ยงได้")

    distance = high - stop
    tp1 = high + 1.5 * distance
    tp2 = high + 2.5 * distance
    # Conservative sizing: calculate loss from the *highest* zone entry and
    # include both-side fee+slippage; execution gaps remain a real risk.
    friction = (fee_pct + slippage_pct) / 100
    risk_per_unit = distance + friction * (high + stop)
    risk_budget = capital * risk_pct / 100
    qty_by_risk = risk_budget / risk_per_unit
    qty_by_allocation = capital * max_allocation_pct / 100 / (high * (1 + friction))
    qty = min(qty_by_risk, qty_by_allocation)
    if not math.isfinite(qty) or qty <= 0:
        return EntryPlan("NO_SETUP", "ขนาดสถานะคำนวณไม่ได้")

    next_check = last_closed_at + timedelta(minutes=TIMEFRAMES[timeframe])
    expiry = last_closed_at + timedelta(minutes=3 * TIMEFRAMES[timeframe])
    if current_price is None or not math.isfinite(current_price) or current_price <= 0:
        status, reason = "WAIT_LIVE_QUOTE", "ไม่มีราคา Spot ล่าสุดที่ตรวจสอบได้: โซนมีไว้เฝ้ารอเท่านั้น"
    elif current_price > high:
        status, reason = "WAIT_RETEST", "ราคา Spot ล่าสุดสูงกว่า Entry Zone: รอย่อ ห้ามซื้อไล่ราคา"
    elif current_price < low:
        status, reason = "WAIT_RECLAIM", "ราคา Spot ล่าสุดต่ำกว่าโซน: รอแท่งปิดกลับเข้าโซน"
    elif close > high or close < low:
        status, reason = "WAIT_CONFIRMATION", "ราคา Spot ล่าสุดเข้าโซนแล้ว แต่แท่งที่ปิดล่าสุดยังอยู่นอกโซน: รอแท่งยืนยัน"
    elif final_signal != "BUY":
        status, reason = "WAIT_CONFIRMATION", "ราคาอยู่ในโซน แต่ Final Signal ยังไม่ใช่ BUY: ยังไม่ยืนยันการซื้อ"
    elif open_price is None or close < anchor or close <= open_price:
        status, reason = "WAIT_CONFIRMATION", "รอแท่งเขียวปิดเหนือแนวรับอ้างอิงภายในโซน"
    elif (_valid_positive(row, "volume_ratio") or 0) < 0.75:
        status, reason = "WAIT_CONFIRMATION", "Volume ยังไม่ถึง 0.75 เท่าของค่าเฉลี่ย: รอแท่งยืนยัน"
    else:
        status, reason = "READY", "แท่งปิดล่าสุดอยู่ใน Entry Zone + แท่งเขียว + Final BUY; เช็กราคาจริงอีกครั้งก่อนทำรายการ"

    return EntryPlan(
        status=status, reason=reason, anchor_name=anchor_name, anchor_price=anchor,
        entry_low=low, entry_high=high, stop_loss=stop,
        take_profit_1=tp1, take_profit_2=tp2,
        position_qty=qty, estimated_risk=qty * risk_per_unit,
        notional=qty * high, risk_budget=risk_budget,
        last_closed_at=last_closed_at, next_check_at=next_check,
        expires_at=expiry,
    )
