"""Frozen, URL-bookmarkable *observational* entry plans.

This module never submits orders. It reconstructs an observation history only
from completed 15-minute Binance Spot candles. A price touching a zone is not
an entry signal; a fresh, multi-stage trigger and current MTF checks are needed.

The encoded URL holds no credentials or account data. It has a corruption
checksum, *not* a cryptographic signature or server-side persistence.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re

import pandas as pd


MAX_WATCH_HOURS = 72
BAR_DURATION = timedelta(minutes=15)


@dataclass(frozen=True)
class FrozenWatchPlan:
    symbol: str
    created_at: datetime
    expires_at: datetime
    entry_low: float
    entry_high: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    fee_pct: float
    slippage_pct: float
    min_net_rr: float


@dataclass(frozen=True)
class WatchResult:
    status: str
    reason: str
    touched_at: datetime | None = None
    reclaimed_at: datetime | None = None
    triggered_at: datetime | None = None
    trigger_price: float | None = None
    net_rr_tp2: float | None = None
    next_candle_close: datetime | None = None


def _check_plan(plan: FrozenWatchPlan) -> None:
    if not re.fullmatch(r"[A-Z0-9]{2,20}USDT", plan.symbol):
        raise ValueError("คู่เหรียญของแผนไม่ถูกต้อง (ต้องเป็น Spot / USDT)")
    if (plan.created_at.tzinfo is None or plan.expires_at.tzinfo is None
            or plan.expires_at <= plan.created_at
            or plan.expires_at - plan.created_at > timedelta(hours=MAX_WATCH_HOURS)):
        raise ValueError("เวลาของแผนต้องอยู่ภายใน 72 ชั่วโมงและมี timezone")
    nums = (plan.entry_low, plan.entry_high, plan.stop_loss, plan.take_profit_1,
            plan.take_profit_2, plan.fee_pct, plan.slippage_pct, plan.min_net_rr)
    if not all(isinstance(n, (int, float)) and not isinstance(n, bool)
               and math.isfinite(n) for n in nums):
        raise ValueError("แผนมีข้อมูลตัวเลขที่ใช้ไม่ได้")
    if not (0 < plan.stop_loss < plan.entry_low < plan.entry_high
            < plan.take_profit_1 < plan.take_profit_2):
        raise ValueError("ลำดับ Entry/Stop/TP ผิดปกติ")
    if not (0 <= plan.fee_pct <= 2 and 0 <= plan.slippage_pct <= 2
            and 1 <= plan.min_net_rr <= 10):
        raise ValueError("ค่าความเสี่ยงของแผนผิดปกติ")


def new_watch_plan(symbol: str, entry, *, now: datetime,
                   hours: int = 48, fee_pct: float = 0.1,
                   slippage_pct: float = 0.05, min_net_rr: float = 1.5) -> FrozenWatchPlan:
    """Freeze prices from the existing 1h EntryPlan; never recalculate them."""
    if now.tzinfo is None:
        raise ValueError("now ต้องมี timezone")
    if not isinstance(hours, int) or not 1 <= hours <= MAX_WATCH_HOURS:
        raise ValueError("ระยะเวลาเฝ้าดูต้องอยู่ใน 1–72 ชั่วโมง")
    fields = (entry.entry_low, entry.entry_high, entry.stop_loss,
              entry.take_profit_1, entry.take_profit_2)
    if any(value is None for value in fields):
        raise ValueError("ยังไม่มีแผน 1h ที่ระบุ Entry/SL/TP ครบ")
    observed = now.astimezone(timezone.utc).replace(microsecond=0)
    plan = FrozenWatchPlan(symbol=symbol, created_at=observed,
                           expires_at=observed + timedelta(hours=hours),
                           entry_low=float(fields[0]), entry_high=float(fields[1]),
                           stop_loss=float(fields[2]), take_profit_1=float(fields[3]),
                           take_profit_2=float(fields[4]), fee_pct=float(fee_pct),
                           slippage_pct=float(slippage_pct), min_net_rr=float(min_net_rr))
    _check_plan(plan)
    return plan


def encode_watch(plan: FrozenWatchPlan) -> str:
    """Checksum detects broken links; it is NOT an authentication feature."""
    _check_plan(plan)
    data = {name: getattr(plan, name) for name in plan.__dataclass_fields__}
    data["created_at"] = plan.created_at.astimezone(timezone.utc).isoformat()
    data["expires_at"] = plan.expires_at.astimezone(timezone.utc).isoformat()
    data["version"] = 1
    payload = json.dumps(data, separators=(",", ":"), sort_keys=True,
                         allow_nan=False).encode("utf-8")
    b64 = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{b64}.{hashlib.sha256(payload).hexdigest()[:12]}"


def decode_watch(token: str) -> FrozenWatchPlan:
    """Reject malformed/oversized URL data without executing or trusting it."""
    if not isinstance(token, str) or not 50 <= len(token) <= 2500 or token.count(".") != 1:
        raise ValueError("ลิงก์แผนไม่ถูกต้อง")
    body, checksum = token.split(".")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", body) or not re.fullmatch(r"[0-9a-f]{12}", checksum):
        raise ValueError("ลิงก์แผนมีอักขระที่ใช้ไม่ได้")
    try:
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        if hashlib.sha256(raw).hexdigest()[:12] != checksum:
            raise ValueError("ลิงก์แผนเสียหาย/ถูกแก้ไข")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.pop("version", None) != 1:
            raise ValueError("เวอร์ชันแผนไม่รองรับ")
        if set(data) != set(FrozenWatchPlan.__dataclass_fields__):
            raise ValueError("ช่องข้อมูลของแผนไม่ถูกต้อง")
        for key in ("created_at", "expires_at"):
            data[key] = datetime.fromisoformat(data[key])
        plan = FrozenWatchPlan(**data)
        _check_plan(plan)
    except (ValueError, KeyError, TypeError, UnicodeError, OverflowError) as exc:
        raise ValueError(f"อ่านแผนเฝ้าดูไม่ได้: {exc}") from exc
    return plan


def _net_rr(entry: float, stop: float, tp: float,
            fee_pct: float, slippage_pct: float) -> float:
    friction = (fee_pct + slippage_pct) / 100.0
    risk = (entry - stop) + friction * (entry + stop)
    reward = (tp - entry) - friction * (entry + tp)
    return reward / risk if risk > 0 else float("-inf")


def evaluate_watch(plan: FrozenWatchPlan, bars: pd.DataFrame, *,
                   now: datetime, current_price: float | None,
                   mtf_buy: bool) -> WatchResult:
    """Replay complete 15m bars since plan creation, then check *current* gates.

    Candle timestamp is its UTC opening time. A candle that was already open
    when the plan was created is excluded to avoid claiming unseen intrabar
    lows occurred after the watch began. Two successive 15m closes below the
    zone cancel the plan. Any touch of the planned SL cancels it immediately.
    No historical trigger is ever represented as currently executable.
    """
    _check_plan(plan)
    if now.tzinfo is None:
        raise ValueError("เวลาตรวจสอบต้องระบุ timezone")
    now_utc = now.astimezone(timezone.utc)
    if now_utc > plan.expires_at:
        return WatchResult("EXPIRED", "หมดอายุแผนที่ล็อกไว้แล้ว ต้องสร้างแผนใหม่")
    if now_utc + timedelta(minutes=5) < plan.created_at:
        return WatchResult("DATA_MISSING", "เวลาของแผนอยู่ในอนาคต ตรวจเวลาเครื่อง")
    if not isinstance(bars, pd.DataFrame) or bars.empty or not isinstance(bars.index, pd.DatetimeIndex):
        return WatchResult("DATA_MISSING", "ไม่พบแท่งปิด 15 นาที: ยังไม่ยืนยันการเข้าซื้อ")
    if bars.index.tz is None:
        return WatchResult("DATA_MISSING", "แท่ง 15 นาทีไม่มี timezone")
    if not {"open", "high", "low", "close", "volume"}.issubset(bars):
        return WatchResult("DATA_MISSING", "แท่งราคา/Volume ไม่ครบ")
    ordered = bars.sort_index()
    if ordered.index.has_duplicates:
        return WatchResult("DATA_MISSING", "พบแท่งเวลาซ้ำ")
    last_open = ordered.index[-1].to_pydatetime()
    last_close = last_open + BAR_DURATION
    next_check = last_close + BAR_DURATION
    if last_close > now_utc + timedelta(seconds=1) or now_utc - last_close > BAR_DURATION * 2:
        return WatchResult("DATA_STALE", "แท่ง 15 นาทีเก่าหรือมีแท่งยังไม่ปิด", next_candle_close=next_check)
    eligible = ordered.loc[(ordered.index >= pd.Timestamp(plan.created_at)) &
                           (ordered.index + pd.Timedelta(BAR_DURATION) <= pd.Timestamp(now_utc))]
    if len(eligible) >= 2 and any(eligible.index.to_series().diff().dropna() != pd.Timedelta(BAR_DURATION)):
        return WatchResult("DATA_GAP", "แท่งราคาขาดช่วง: ไม่สร้างสัญญาณจากประวัติที่ไม่ครบ",
                           next_candle_close=next_check)
    if current_price is None or not math.isfinite(current_price) or current_price <= 0:
        return WatchResult("DATA_MISSING", "ไม่มีราคา Spot ล่าสุดสำหรับตรวจสถานะเข้า",
                           next_candle_close=next_check)
    if current_price <= plan.stop_loss:
        return WatchResult("INVALIDATED", "ราคา Spot ล่าสุดแตะ/หลุด Stop Loss: ยกเลิกแผนทันที",
                           next_candle_close=next_check)

    touched_at = None
    reclaimed_at = None
    trigger_at = None
    trigger_close = None
    reclaim_high = None
    below_streak = 0

    # A rolling *prior*-20-bar average to avoid using future volume.
    prior_vol = ordered["volume"].rolling(20, min_periods=10).mean().shift(1)
    for candle_start, r in eligible.iterrows():
        candle_end = candle_start.to_pydatetime() + BAR_DURATION
        vals = (float(r["open"]), float(r["high"]), float(r["low"]),
                float(r["close"]), float(r["volume"]))
        op, high, low, close, volume = vals
        if not all(math.isfinite(x) for x in vals) or not (0 < low <= min(op, close) <= high
                                                          and max(op, close) <= high and volume >= 0):
            return WatchResult("DATA_MISSING", "ข้อมูลราคา/Volume ผิดปกติ",
                               next_candle_close=next_check)
        if low <= plan.stop_loss:
            return WatchResult("INVALIDATED", "ราคาลงแตะ/หลุด Stop Loss ของแผนก่อนเข้าซื้อ: ยกเลิกแผน",
                               touched_at=touched_at, reclaimed_at=reclaimed_at,
                               triggered_at=trigger_at, next_candle_close=next_check)
        below_streak = below_streak + 1 if close < plan.entry_low else 0
        if below_streak >= 2:
            return WatchResult("INVALIDATED", "แท่ง 15m ปิดต่ำกว่าขอบล่างโซน 2 แท่งติด: ไม่รับมีดตก",
                               touched_at=touched_at, reclaimed_at=reclaimed_at,
                               triggered_at=trigger_at, next_candle_close=next_check)
        if touched_at is None and low <= plan.entry_high and high >= plan.entry_low:
            touched_at = candle_end
        if touched_at is None:
            continue
        if trigger_at is not None:
            if high >= plan.take_profit_1:
                return WatchResult("PASSED", "หลังสัญญาณเดิม ราคาเคยถึง TP1 แล้ว: ไม่ใช่จุดเข้าซื้อใหม่",
                                   touched_at=touched_at, reclaimed_at=reclaimed_at,
                                   triggered_at=trigger_at, trigger_price=trigger_close,
                                   next_candle_close=next_check)
            continue
        avg = prior_vol.get(candle_start)
        enough_volume = pd.notna(avg) and float(avg) > 0 and volume >= float(avg) * 0.8
        if reclaimed_at is None:
            if (close > plan.entry_high and close > op and enough_volume):
                reclaimed_at = candle_end
                reclaim_high = high
        elif (close > op and close >= plan.entry_high and enough_volume
              and (close > reclaim_high or (low <= plan.entry_high and close > plan.entry_high))):
            trigger_at = candle_end
            trigger_close = close

    if touched_at is None:
        if current_price < plan.entry_low:
            return WatchResult("WAIT_RECLAIM", "ราคาต่ำกว่าโซน แต่ยังไม่มีแท่งปิดยืนยัน: อย่าซื้อทันที",
                               next_candle_close=next_check)
        if current_price <= plan.entry_high:
            return WatchResult("WAIT_TOUCH", "ราคาแตะโซนระหว่างแท่ง: รอแท่ง 15m ปิดก่อน",
                               next_candle_close=next_check)
        return WatchResult("WAIT_ZONE", "ยังไม่แตะโซนที่ล็อกไว้; รอราคา ไม่ใช้โซนใหม่แทน",
                           next_candle_close=next_check)
    if trigger_at is None:
        if reclaimed_at is None:
            return WatchResult("WAIT_RECLAIM", "ราคาเคยแตะโซนแล้ว รอ 15m ปิดเขียวเหนือขอบบนพร้อม Volume",
                               touched_at=touched_at, next_candle_close=next_check)
        return WatchResult("WAIT_BREAK", "แท่ง 15m กลับเหนือโซนแล้ว รอเบรกยอดย่อยหรือ Retest ยืนได้",
                           touched_at=touched_at, reclaimed_at=reclaimed_at,
                           next_candle_close=next_check)

    kwargs = {"touched_at": touched_at, "reclaimed_at": reclaimed_at,
              "triggered_at": trigger_at, "trigger_price": trigger_close,
              "next_candle_close": next_check}
    if now_utc - trigger_at > BAR_DURATION * 2:
        return WatchResult("PASSED", "เคยมี Trigger แต่เป็นสัญญาณเก่า ไม่ไล่ราคาจากสัญญาณย้อนหลัง", **kwargs)
    if current_price < plan.entry_high:
        return WatchResult("WAIT_RECLAIM", "ราคา Spot ล่าสุดหลุดกลับใต้ขอบบน: รอยืนยันใหม่", **kwargs)
    max_execution = min(plan.take_profit_1, plan.entry_high + (plan.entry_high - plan.stop_loss) * 0.75)
    if current_price > max_execution:
        return WatchResult("PASSED", "ราคาออกห่างจุดเข้ามากแล้ว: ไม่ไล่ซื้อ", **kwargs)
    # Conservative: prospective execution cost/return are based on the *live*
    # quote, never the old theoretical zone or an assumed historical fill.
    rr = _net_rr(current_price, plan.stop_loss, plan.take_profit_2,
                 plan.fee_pct, plan.slippage_pct)
    kwargs["net_rr_tp2"] = rr
    if rr < plan.min_net_rr:
        return WatchResult("WAIT_RISK", "R:R สุทธิ ณ ราคาล่าสุดต่ำกว่าเกณฑ์: ไม่ซื้อ", **kwargs)
    if not mtf_buy:
        return WatchResult("WAIT_MTF", "Trigger เกิดแล้ว แต่ตัวกรอง MTF/Futures ล่าสุดไม่ผ่าน: ยังไม่ซื้อ", **kwargs)
    return WatchResult("READY_NOW", "แท่งปิดยืนยันหลังแตะโซน + MTF ผ่าน + ราคาไม่ไล่ + R:R ผ่าน; ตรวจ Bid/Ask ก่อนตัดสินใจ",
                       **kwargs)
