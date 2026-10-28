"""CoinGlass manual snapshot verification and conservative signal confirmation.

No CoinGlass API calls are made: official API access requires an API key and a
subscription. All values must be entered by the user from a legitimately
accessible CoinGlass page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re


@dataclass(frozen=True)
class CoinGlassSnapshot:
    symbol: str
    observed_at: datetime
    funding_rate_pct: float
    oi_change_24h_pct: float
    long_short_account_ratio: float
    long_liquidations_usd_24h: float
    short_liquidations_usd_24h: float


def parse_quick_paste(text: str) -> tuple[float, float, float, float, float]:
    """Parse five manually copied figures; never infer or scrape missing fields."""
    fields = [part.strip() for part in re.split(r"[,;\t\n]+", text.strip()) if part.strip()]
    if len(fields) != 5:
        raise ValueError("ต้องใส่ตัวเลข 5 ค่า คั่นด้วยคอมมา")
    try:
        nums = tuple(float(field) for field in fields)
    except ValueError as exc:
        raise ValueError("มีข้อมูลที่ไม่ใช่ตัวเลข") from exc
    funding, oi, ratio, long_liq, short_liq = nums
    if not all(math.isfinite(v) for v in nums):
        raise ValueError("ต้องเป็นตัวเลขที่ใช้ได้")
    if not (-5 <= funding <= 5 and -100 <= oi <= 1000 and 0 < ratio <= 50
            and 0 <= long_liq <= 1e15 and 0 <= short_liq <= 1e15):
        raise ValueError("มีค่าผิดหน่วยหรืออยู่นอกช่วงที่กำหนด")
    return nums


def validate_snapshot(
    snapshot: CoinGlassSnapshot,
    expected_symbol: str,
    now: datetime,
    max_age: timedelta,
) -> list[str]:
    problems: list[str] = []
    if snapshot.symbol != expected_symbol:
        problems.append("ข้อมูล CoinGlass เป็นคนละเหรียญกับกราฟที่เลือก")
    if snapshot.observed_at.tzinfo is None or now.tzinfo is None:
        problems.append("เวลา CoinGlass ต้องระบุเขตเวลา")
    else:
        age = now - snapshot.observed_at
        if age > max_age:
            problems.append("ข้อมูล CoinGlass เก่าเกินกำหนด ต้องอัปเดตก่อน")
        if age < -timedelta(minutes=5):
            problems.append("เวลาบันทึก CoinGlass อยู่ในอนาคต")
    numeric = (
        snapshot.funding_rate_pct,
        snapshot.oi_change_24h_pct,
        snapshot.long_short_account_ratio,
        snapshot.long_liquidations_usd_24h,
        snapshot.short_liquidations_usd_24h,
    )
    if not all(math.isfinite(value) for value in numeric):
        problems.append("ข้อมูล CoinGlass ต้องเป็นตัวเลขที่ถูกต้อง")
    if not 0 < snapshot.long_short_account_ratio <= 50:
        problems.append("Long/Short Ratio ต้องมากกว่า 0")
    if snapshot.long_liquidations_usd_24h < 0 or snapshot.short_liquidations_usd_24h < 0:
        problems.append("Liquidation ต้องไม่ติดลบ")
    if abs(snapshot.funding_rate_pct) > 5:
        problems.append("Funding Rate ดูผิดหน่วย: ต้องกรอกเป็นเปอร์เซ็นต์ เช่น 0.01 = 0.01%")
    if not -100 <= snapshot.oi_change_24h_pct <= 1000:
        problems.append("OI Change 24h อยู่นอกช่วงที่สมเหตุสมผล")
    return problems


def confirm_signal(
    technical_signal: str,
    snapshot: CoinGlassSnapshot | None,
    expected_symbol: str,
    price_change_24h_pct: float,
    *,
    now: datetime | None = None,
    max_age_hours: float = 4.0,
) -> dict:
    """Require current CoinGlass context before allowing BUY or SELL.

    OI supports trend continuation only if it grows with price direction. The
    funding/crowding/liquidation checks are protective heuristics, *not*
    empirically calibrated probabilities or an independently backtested model.
    """
    now = now or datetime.now(timezone.utc)
    if snapshot is None:
        return {"signal": "WAIT", "status": "MISSING", "reasons": [
            "ยังไม่มีข้อมูล CoinGlass ที่ผู้ใช้ยืนยัน (ตัวกรองเสริม)"],
            "blocking_reasons": [], "confirmed": False}
    problems = validate_snapshot(snapshot, expected_symbol, now, timedelta(hours=max_age_hours))
    if problems:
        return {"signal": "WAIT", "status": "INVALID", "reasons": problems,
                "blocking_reasons": problems, "confirmed": False}
    if technical_signal == "WAIT":
        return {"signal": "WAIT", "status": "TECHNICAL_WAIT", "reasons": [
            "ข้อมูล CoinGlass ผ่านการตรวจสอบ แต่ฝั่งเทคนิคยังเป็น WAIT"],
            "blocking_reasons": [], "confirmed": False}

    reasons: list[str] = []
    blocking_reasons: list[str] = []
    oi = snapshot.oi_change_24h_pct
    funding = snapshot.funding_rate_pct
    ratio = snapshot.long_short_account_ratio

    if technical_signal == "BUY":
        if price_change_24h_pct <= 0 or oi < 1:
            blocking_reasons.append(
                f"ราคา Spot 24h {price_change_24h_pct:+.2f}% ต้องเป็นบวก และ OI 24h {oi:+.2f}% ต้อง ≥ +1.00%")
            reasons.append(blocking_reasons[-1])
        else:
            reasons.append("ราคาเพิ่มขึ้นพร้อม OI เพิ่มอย่างน้อย 1%: สนับสนุนแนวโน้มขาขึ้น")
        if funding > 0.05:
            blocking_reasons.append(f"Funding {funding:+.4f}% > +0.0500%: เสี่ยงซื้อไล่ราคา")
            reasons.append(blocking_reasons[-1])
        if funding < -0.05:
            blocking_reasons.append(f"Funding {funding:+.4f}% < -0.0500%: ภาวะตลาดผิดปกติ")
            reasons.append(blocking_reasons[-1])
        if ratio > 1.6:
            blocking_reasons.append(f"Long/Short Accounts {ratio:.3f} > 1.600: Long แออัด เสี่ยงซื้อไล่ราคา")
            reasons.append(blocking_reasons[-1])
        if not any((funding > 0.05, funding < -0.05, ratio > 1.6)):
            reasons.append("Funding และสัดส่วน Long/Short ยังไม่อยู่ในโซนแออัดเกินเกณฑ์")
    elif technical_signal == "SELL":
        if price_change_24h_pct >= 0 or oi < 1:
            blocking_reasons.append(
                f"ราคา Spot 24h {price_change_24h_pct:+.2f}% ต้องเป็นลบ และ OI 24h {oi:+.2f}% ต้อง ≥ +1.00%")
            reasons.append(blocking_reasons[-1])
        else:
            reasons.append("ราคาลดลงพร้อม OI เพิ่มอย่างน้อย 1%: สนับสนุนแรงขาย")
        if funding < -0.05:
            blocking_reasons.append(f"Funding {funding:+.4f}% < -0.0500%: Short แออัด")
            reasons.append(blocking_reasons[-1])
        if ratio < 0.625:
            blocking_reasons.append(f"Long/Short Accounts {ratio:.3f} < 0.625: Short แออัด")
            reasons.append(blocking_reasons[-1])
        if funding > 0.05:
            blocking_reasons.append(f"Funding {funding:+.4f}% > +0.0500%: โครงสร้างตลาดไม่สมดุล")
            reasons.append(blocking_reasons[-1])
        if not any((funding < -0.05, ratio < 0.625, funding > 0.05)):
            reasons.append("Funding และสัดส่วน Long/Short ยังไม่อยู่ในโซนแออัดเกินเกณฑ์")
    else:
        return {"signal": "WAIT", "status": "INVALID", "reasons": ["สัญญาณเทคนิคไม่ถูกต้อง"],
                "blocking_reasons": ["สัญญาณเทคนิคไม่ถูกต้อง"], "confirmed": False}

    long_liq = snapshot.long_liquidations_usd_24h
    short_liq = snapshot.short_liquidations_usd_24h
    total_liq = long_liq + short_liq
    if total_liq == 0:
        reasons.append("ไม่พบ Liquidation ในชุดข้อมูลที่กรอก; ตรวจสอบว่าเป็นค่า 0 จริง")
    else:
        long_share = long_liq / total_liq
        if long_share > 0.75:
            reasons.append("Liquidation 24h หนักไปทาง Long: มีแรงล้างสถานะ Long")
        elif long_share < 0.25:
            reasons.append("Liquidation 24h หนักไปทาง Short: มีแรงล้างสถานะ Short")
        else:
            reasons.append("Liquidation 24h กระจายสองฝั่ง ไม่เห็นฝั่งครอบงำชัด")

    # Liquidation shares alone cannot prove continuation or reversal without
    # a denominator/market-size baseline. Hence they inform but never veto.
    if blocking_reasons:
        reasons.append("CoinGlass ยังไม่ยืนยันสัญญาณเทคนิค จึงปรับผลสุดท้ายเป็น WAIT")
        return {"signal": "WAIT", "status": "CAUTION", "reasons": reasons,
                "blocking_reasons": blocking_reasons, "confirmed": False}
    return {"signal": technical_signal, "status": "CONFIRMED", "reasons": reasons,
            "blocking_reasons": [], "confirmed": True}
