"""Read-only, evidence-gated price-escape alerts for *unchanged* Frozen plans.

These are observational advisories, NOT entries, orders, or automatic re-anchoring.
Only complete 15-minute candles *after* the freeze are eligible. Never use a
single live-tick spike, a stale candle, or an unavailable market-data context.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math

import pandas as pd

from watch_plans import FrozenWatchPlan


BAR = timedelta(minutes=15)
IMPORTANT_RALLIES = {"BREAKOUT_WATCH", "MISSED_ENTRY", "NEW_SETUP_CANDIDATE"}


@dataclass(frozen=True)
class RallySettings:
    watch_above_zone_pct: float = 3.0
    missed_above_zone_pct: float = 8.0
    confirmation_bars: int = 2
    min_volume_ratio: float = 0.8
    candidate_max_above_new_zone_pct: float = 1.0

    def validate(self) -> None:
        values = (self.watch_above_zone_pct, self.missed_above_zone_pct,
                  self.min_volume_ratio, self.candidate_max_above_new_zone_pct)
        if (not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                    and math.isfinite(v) for v in values)
                or not 0.5 <= self.watch_above_zone_pct <= 15
                or not self.watch_above_zone_pct + 0.5 <= self.missed_above_zone_pct <= 50
                or not isinstance(self.confirmation_bars, int)
                or not 2 <= self.confirmation_bars <= 4
                or not 0.5 <= self.min_volume_ratio <= 3.0
                or not 0 <= self.candidate_max_above_new_zone_pct <= 2):
            raise ValueError("เกณฑ์ Rally Watch ไม่ถูกต้อง")


@dataclass(frozen=True)
class RallyResult:
    status: str = "NONE"
    reason: str = ""
    distance_pct: float | None = None
    volume_ratio: float | None = None
    frozen_atr_pct: float | None = None
    latest_confirmed_at: datetime | None = None
    new_entry_low: float | None = None
    new_entry_high: float | None = None


def evaluate_rally(plan: FrozenWatchPlan, bars: pd.DataFrame, *,
                   now: datetime, current_price: float | None,
                   frozen_status: str, context_ready: bool,
                   live_mtf_ready: bool = False, new_entry=None,
                   settings: RallySettings | None = None) -> RallyResult:
    """Evaluate a *secondary* market opportunity without changing watch state.

    A candidate requires live MTF READY and a genuinely higher, non-chased new
    zone; it is still only a prompt for a human to review and lock a new plan.
    """
    rules = settings or RallySettings()
    rules.validate()
    nothing = RallyResult()
    if (now.tzinfo is None or not context_ready or frozen_status != "WAIT_ZONE"
            or now.astimezone(timezone.utc) > plan.expires_at
            or current_price is None or not isinstance(current_price, (int, float))
            or not math.isfinite(current_price) or current_price <= plan.entry_high):
        return nothing
    if (not isinstance(bars, pd.DataFrame) or bars.empty
            or not isinstance(bars.index, pd.DatetimeIndex)
            or bars.index.tz is None or bars.index.has_duplicates
            or not {"open", "high", "low", "close", "volume"}.issubset(bars)):
        return nothing

    ordered = bars.sort_index()
    utc_now = now.astimezone(timezone.utc)
    # Freeze a volatility reference using candles completed *before* the plan;
    # a fresh pump must not inflate the threshold after the fact.
    before_lock = ordered.loc[ordered.index + pd.Timedelta(BAR) <= pd.Timestamp(plan.created_at)].tail(20)
    if len(before_lock) < 15 or any(before_lock.index.to_series().diff().dropna() != pd.Timedelta(BAR)):
        return nothing
    previous_closes = before_lock["close"].shift(1)
    ranges = pd.concat([before_lock["high"] - before_lock["low"],
                        (before_lock["high"] - previous_closes).abs(),
                        (before_lock["low"] - previous_closes).abs()], axis=1).max(axis=1)
    atr = float(ranges.tail(14).mean())
    reference_close = float(before_lock["close"].iloc[-1])
    if not math.isfinite(atr) or not math.isfinite(reference_close) or reference_close <= 0 or atr <= 0:
        return nothing
    frozen_atr_pct = 100 * atr / reference_close
    watch_threshold_pct = max(rules.watch_above_zone_pct, 1.5 * frozen_atr_pct)
    missed_threshold_pct = max(rules.missed_above_zone_pct, 3 * frozen_atr_pct,
                               watch_threshold_pct + 1)
    # As in evaluate_watch, a candle that began before the lock is ineligible.
    closed = ordered.loc[(ordered.index >= pd.Timestamp(plan.created_at)) &
                         (ordered.index + pd.Timedelta(BAR) <= pd.Timestamp(utc_now))]
    if len(closed) < rules.confirmation_bars:
        return nothing
    recent = closed.tail(rules.confirmation_bars)
    times = recent.index.to_series().diff().dropna()
    if not all(times == pd.Timedelta(BAR)):
        return nothing
    last_at = recent.index[-1].to_pydatetime() + BAR
    if utc_now - last_at > BAR * 2:
        return nothing
    for _, bar in recent.iterrows():
        try:
            op, hi, low, close, vol = (float(bar[x]) for x in
                                        ("open", "high", "low", "close", "volume"))
        except (TypeError, ValueError):
            return nothing
        if (not all(math.isfinite(x) for x in (op, hi, low, close, vol))
                or not 0 < low <= min(op, close) <= max(op, close) <= hi
                or vol < 0):
            return nothing

    above = float(current_price / plan.entry_high - 1) * 100
    if above < watch_threshold_pct:
        return nothing
    threshold = plan.entry_high * (1 + watch_threshold_pct / 100)
    if not all(float(c) > threshold for c in recent["close"]):
        return nothing

    # Compare only with earlier volume; no leakage from current/incomplete bars.
    previous_avg = ordered["volume"].rolling(20, min_periods=10).mean().shift(1)
    ratios: list[float] = []
    for stamp, row in recent.iterrows():
        avg = previous_avg.loc[stamp]
        if pd.isna(avg) or not math.isfinite(float(avg)) or float(avg) <= 0:
            return nothing
        ratios.append(float(row["volume"]) / float(avg))
    evidence_volume = max(ratios)
    if evidence_volume < rules.min_volume_ratio:
        return nothing

    if above >= missed_threshold_pct:
        status = "MISSED_ENTRY"
        reason = (f"Spot อยู่เหนือ Frozen Entry Zone {above:.2f}% (เกณฑ์ {missed_threshold_pct:.2f}% "
                  f"ปรับตาม ATR ณ เวลาล็อก) และมีแท่ง 15m ปิดยืนยัน "
                  f"{rules.confirmation_bars} แท่ง; ไม่เลื่อนโซน ไม่ไล่ซื้อ")
    else:
        status = "BREAKOUT_WATCH"
        reason = (f"ราคาวิ่งเหนือ Frozen Entry Zone {above:.2f}% (เกณฑ์ {watch_threshold_pct:.2f}% "
                  "ปรับตาม ATR ณ เวลาล็อก) "
                  f"ยืนยันด้วย {rules.confirmation_bars} แท่งปิดและ Volume; "
                  "นี่ไม่ใช่คำสั่งซื้อหรือการยืนยันเบรกแนวต้าน")

    candidate_low = candidate_high = None
    if live_mtf_ready and new_entry is not None:
        try:
            low = float(new_entry.entry_low)
            high = float(new_entry.entry_high)
            stop = float(new_entry.stop_loss)
            tp1 = float(new_entry.take_profit_1)
            tp2 = float(new_entry.take_profit_2)
        except (AttributeError, ValueError, TypeError):
            pass
        else:
            if (all(math.isfinite(v) for v in (low, high, stop, tp1, tp2))
                    and 0 < stop < low < high < tp1 < tp2
                    and low > plan.entry_high * (1 + watch_threshold_pct / 100)
                    and low <= current_price <= high * (1 + rules.candidate_max_above_new_zone_pct / 100)):
                status = "NEW_SETUP_CANDIDATE"
                reason = ("MTF สดผ่านเกณฑ์ READY และพบ Entry Zone ใหม่สูงกว่าแผนเดิม "
                          "แต่ยังไม่ล็อกแผนใหม่และไม่ส่งคำสั่งซื้อ; ให้ตรวจด้วยตนเอง")
                candidate_low, candidate_high = low, high

    return RallyResult(status, reason, above, evidence_volume, frozen_atr_pct, last_at,
                       candidate_low, candidate_high)
