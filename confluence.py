"""One cautious multi-timeframe verdict for a single selected Spot pair.

The strength index is a weighted *technical alignment score*, NOT a win-rate,
probability, or backtested prediction. Entry prices only come from the 1h plan;
raw Entry Zones from different timeframes are never numerically averaged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping

from multi_timeframe import RuleCheck, TimeframeReport
from entry_planner import EntryPlan


FRAME_WEIGHTS = {"1d": 0.30, "4h": 0.30, "1h": 0.25, "15m": 0.15}
FRAME_SCORE_MAX = {"1d": 7, "4h": 9, "1h": 9, "15m": 9}
MIN_ALIGNMENT_INDEX = 70.0  # Heuristic threshold; has no statistical calibration.


@dataclass(frozen=True)
class ConfluenceVerdict:
    signal: str  # BUY or WAIT; no synthetic SELL/short trade is generated.
    status: str  # READY / WAIT_ENTRY / WAIT_SIGNAL
    alignment_index: float | None
    checks: tuple[RuleCheck, ...]
    reasons: tuple[str, ...]
    entry: EntryPlan | None
    next_15m_close: datetime | None
    next_1h_close: datetime | None


def combine_timeframes(reports: Mapping[str, TimeframeReport]) -> ConfluenceVerdict:
    """Require independent timeframe context before proposing one 1h entry plan.

    Roles: 1d + 4h bullish context, 1h final BUY and entry zone, 15m final
    BUY + green closed candle for execution timing. All four must be fresh,
    with no missing/gapped data. CoinGlass is optional, but if supplied its
    per-frame veto has already been applied by TimeframeReport.
    """
    missing = [tf for tf in FRAME_WEIGHTS if tf not in reports]
    checks: list[RuleCheck] = [RuleCheck(
        "ข้อมูลครบ 4 กรอบ", not missing,
        "ครบ 15m / 1h / 4h / 1d" if not missing else "ขาด " + ", ".join(missing),
    )]

    all_fresh = not missing and all(not r.stale and r.gaps == 0 for r in reports.values())
    checks.append(RuleCheck("ข้อมูลทุกกรอบสดและไม่มีช่องว่าง", all_fresh,
                            "ผ่าน" if all_fresh else "บางกรอบข้อมูลไม่พร้อม/เก่า/ขาดช่วง"))

    alignment: float | None = None
    if not missing:
        weighted = sum(
            FRAME_WEIGHTS[tf] * max(-1., min(1., reports[tf].score / FRAME_SCORE_MAX[tf]))
            for tf in FRAME_WEIGHTS
        )
        alignment = 50. + 50. * weighted
    checks.append(RuleCheck("คะแนนสอดคล้อง ≥ 70/100", alignment is not None and alignment >= MIN_ALIGNMENT_INDEX,
                            f"{alignment:.1f}/100" if alignment is not None else "ยังคำนวณไม่ได้"))

    daily = reports.get("1d")
    four = reports.get("4h")
    hour = reports.get("1h")
    fast = reports.get("15m")
    checks.extend([
        RuleCheck("แนวโน้มรายวันสนับสนุนฝั่งซื้อ",
                  daily is not None and daily.trend == 1 and daily.structure_bias >= 0,
                  "1d trend + structure"),
        RuleCheck("แนวโน้มหลักระยะกลางสนับสนุน",
                  four is not None and four.trend == 1 and four.higher_trend == 1
                  and four.structure_bias >= 0,
                  "4h trend + 1d confirmation"),
        RuleCheck("1h Final BUY ผ่าน Spot + Futures และ CoinGlass (ถ้ามี)",
                  hour is not None and hour.final == "BUY", "ยึด 1h เป็นแผน Entry"),
        RuleCheck("15m Final BUY ยืนยันจังหวะ",
                  fast is not None and fast.final == "BUY", "เช็ก Momentum ระยะสั้น"),
        RuleCheck("15m แท่งปิดเขียวและ Volume ≥ 0.75×",
                  fast is not None and fast.green_candle and fast.volume_ratio >= 0.75,
                  "ไม่ใช้แท่งเทียนที่ยังไม่ปิด"),
    ])

    bias = all(c.passed for c in checks)
    entry = hour.entry if hour is not None else None
    ready = bias and entry is not None and entry.status == "READY"
    checks.append(RuleCheck("ราคาและแท่ง 1h อยู่ในโซนที่ผ่านเกณฑ์",
                            entry is not None and entry.status == "READY",
                            entry.reason if entry is not None else "ไม่มีแผน Entry 1h"))

    signal = "BUY" if bias else "WAIT"
    status = "READY" if ready else "WAIT_ENTRY" if bias else "WAIT_SIGNAL"
    reasons = [c.detail if c.label.startswith("ข้อมูลครบ") else c.label + ": " + c.detail
               for c in checks if not c.passed]
    if ready:
        reasons = ["ทุกเงื่อนไขของกฎทดลองผ่านบนแท่งที่ปิดแล้ว; ยังต้องตรวจราคาเสนอขายและความเสี่ยงจริง"]
    elif bias and entry is not None:
        reasons = ["MTF สนับสนุนขาขึ้น แต่ยังเข้าเงื่อนไขซื้อไม่ครบ: " + entry.reason]

    return ConfluenceVerdict(
        signal=signal, status=status, alignment_index=alignment,
        checks=tuple(checks), reasons=tuple(reasons), entry=entry,
        next_15m_close=fast.last_close + timedelta(minutes=15) if fast else None,
        next_1h_close=hour.last_close + timedelta(hours=1) if hour else None,
    )
