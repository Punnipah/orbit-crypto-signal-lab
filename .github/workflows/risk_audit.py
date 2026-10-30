"""Model-based post-fee reward/risk audit for a read-only Spot entry plan."""

from __future__ import annotations

from dataclasses import dataclass
import math

from entry_planner import EntryPlan
from multi_timeframe import RuleCheck


@dataclass(frozen=True)
class RiskAudit:
    rr_tp1: float | None
    rr_tp2: float | None
    modeled_loss_per_unit: float | None
    modeled_gain_per_unit_tp2: float | None
    checks: tuple[RuleCheck, ...]
    source: str = "1h EntryPlan + simulated fees/slippage (not executable exchange fills)"


def audit_entry(plan: EntryPlan | None, *, fee_pct: float,
                slippage_pct: float, min_net_rr: float = 1.5) -> RiskAudit:
    """Worst-side modeled entry at zone HIGH, exit at stop/TP net of costs.

    Does not assume a fill will occur; does not model gaps, maker/taker tier,
    market impact or exchange tick sizes. This calculation is deliberately
    separate from the backtest's simulated realized fills.
    """
    if not (0 <= fee_pct <= 5 and 0 <= slippage_pct <= 5 and 1 <= min_net_rr <= 5):
        raise ValueError("ค่าต้นทุน/เกณฑ์ R:R ไม่ถูกต้อง")
    if plan is None or any(getattr(plan, k) is None for k in
                           ("entry_high", "stop_loss", "take_profit_1", "take_profit_2")):
        return RiskAudit(None, None, None, None,
                         (RuleCheck("R:R หลังค่าธรรมเนียม", False,
                                    "ยังไม่มีแผน Entry/SL/TP ที่คำนวณได้"),))
    entry, stop, tp1, tp2 = (float(getattr(plan, key)) for key in
                              ("entry_high", "stop_loss", "take_profit_1", "take_profit_2"))
    if not all(map(math.isfinite, (entry, stop, tp1, tp2))) or not 0 < stop < entry < tp1 < tp2:
        return RiskAudit(None, None, None, None,
                         (RuleCheck("R:R หลังค่าธรรมเนียม", False, "โครงสร้างราคาหรือระดับ TP ไม่ถูกต้อง"),))
    fee, slip = fee_pct / 100, slippage_pct / 100
    entry_cost = entry * (1 + slip) * (1 + fee)
    stop_proceeds = stop * (1 - slip) * (1 - fee)
    tp1_proceeds = tp1 * (1 - slip) * (1 - fee)
    tp2_proceeds = tp2 * (1 - slip) * (1 - fee)
    risk = entry_cost - stop_proceeds
    gain1, gain2 = tp1_proceeds - entry_cost, tp2_proceeds - entry_cost
    rr1 = gain1 / risk if risk > 0 else None
    rr2 = gain2 / risk if risk > 0 else None
    return RiskAudit(rr1, rr2, risk, gain2,
                     (RuleCheck(f"R:R สุทธิจำลอง TP2 ≥{min_net_rr:g}:1",
                                rr2 is not None and rr2 >= min_net_rr,
                                f"TP1 {rr1:.2f}R · TP2 {rr2:.2f}R หลังต้นทุนจำลอง"
                                if rr1 is not None and rr2 is not None else "ไม่พร้อม"),))
