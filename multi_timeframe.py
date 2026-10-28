"""Independent, auditable 15m/1h/4h/1d watch plans.

This is a presentation of the existing causal signal and entry rules, not a
new multi-timeframe trading strategy or a backtested confluence signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math

import pandas as pd

from binance_data import TIMEFRAMES, count_time_gaps
from coinglass_overlay import CoinGlassSnapshot, confirm_signal
from entry_planner import EntryPlan, plan_entry
from public_derivatives import DerivativesSnapshot, evaluate_derivatives


@dataclass(frozen=True)
class RuleCheck:
    label: str
    passed: bool | None  # None means optional or not applicable.
    detail: str


@dataclass(frozen=True)
class TimeframeReport:
    timeframe: str
    technical: str
    auto: str
    final: str
    futures_status: str
    coinglass_status: str
    coinglass_blockers: tuple[str, ...]
    futures_reasons: tuple[str, ...]
    entry: EntryPlan
    checks: tuple[RuleCheck, ...]
    last_close: datetime
    price_change_24h_pct: float
    score: int
    rsi: float
    adx: float
    volume_ratio: float
    taker_buy_share20: float
    trend: int
    higher_trend: int
    structure_bias: int
    green_candle: bool
    source_bars: int
    gaps: int
    stale: bool


def build_timeframe_report(
    base: pd.DataFrame,
    analyzed: pd.DataFrame,
    timeframe: str,
    *,
    base_asset: str,
    derivatives: DerivativesSnapshot | None,
    coinglass: CoinGlassSnapshot | None,
    now: datetime,
    current_price: float | None,
    capital: float,
    risk_pct: float,
    max_allocation_pct: float,
    fee_pct: float,
    slippage_pct: float,
) -> TimeframeReport:
    """Evaluate one closed-candle timeframe using exactly the detailed view's rules.

    Missing/stale Spot data forces WAIT even if derivative heuristics suggest BUY.
    A CoinGlass snapshot is optional but can veto a BUY when supplied.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError("Timeframe ไม่ถูกต้อง")
    if now.tzinfo is None:
        raise ValueError("เวลาตรวจต้องมีเขตเวลา")
    if len(base) != len(analyzed) or base.empty:
        raise ValueError("ข้อมูลแท่งเทียนและผลวิเคราะห์ไม่ตรงกัน")
    bars_per_day = max(1, 1440 // TIMEFRAMES[timeframe])
    if len(base) <= bars_per_day:
        raise ValueError("ข้อมูลไม่เพียงพอสำหรับเทียบราคา 24 ชม.")

    row = analyzed.iloc[-1]
    technical = str(row["signal"])
    price_change = (float(base["close"].iloc[-1]) / float(base["close"].iloc[-1-bars_per_day]) - 1) * 100
    if not math.isfinite(price_change):
        raise ValueError("ราคาเปลี่ยน 24 ชม. ใช้ไม่ได้")
    auto = evaluate_derivatives(technical, derivatives, price_change)
    max_age = {"15m": 1, "1h": 2, "4h": 4, "1d": 24}[timeframe]
    cg = confirm_signal(technical, coinglass, base_asset, price_change,
                        now=now, max_age_hours=max_age)

    last_close = (base.index[-1] + timedelta(minutes=TIMEFRAMES[timeframe])).to_pydatetime()
    gaps = count_time_gaps(base, timeframe)
    stale = last_close < now - timedelta(minutes=TIMEFRAMES[timeframe] * 2)
    data_ok = not bool(gaps) and not stale

    final = auto["signal"]
    if coinglass is not None and cg["signal"] != technical:
        final = "WAIT"
    if not data_ok:
        final = "WAIT"

    entry = plan_entry(
        row, timeframe, final, last_close,
        capital=capital, risk_pct=risk_pct,
        max_allocation_pct=max_allocation_pct,
        fee_pct=fee_pct, slippage_pct=slippage_pct,
        data_ok=data_ok, current_price=current_price,
    )

    def check(name: str, passed: bool, detail: str) -> RuleCheck:
        return RuleCheck(name, bool(passed), detail)

    score_threshold = 5 if timeframe == "1d" else 6
    indicator_cols = ("ema200", "rsi", "macd_hist", "atr", "adx", "volume_ma20")
    indicators_valid = all(pd.notna(row.get(name)) for name in indicator_cols)
    checks = [
        check("แท่งเทียนครบและยังสด", data_ok,
              f"ขาด {gaps} ช่วง" if gaps else "เก่าเกินเกณฑ์" if stale else "ผ่าน"),
        check("ตัวชี้วัดคำนวณครบ", indicators_valid, "EMA200, RSI, MACD, ATR, ADX, Volume"),
        check("แนวโน้ม Spot เป็นขาขึ้น", row.get("trend") == 1, "Trend = +1"),
    ]
    if timeframe == "1d":
        checks.append(RuleCheck("แนวโน้มกรอบใหญ่", None, "1d เป็นกรอบสูงสุดของระบบ"))
    else:
        checks.append(check("แนวโน้มกรอบใหญ่เป็นขาขึ้น", row.get("higher_trend") == 1,
                            {"15m": "1h", "1h": "4h", "4h": "1d"}[timeframe]))
    checks.extend([
        check("โครงสร้างราคาไม่เป็นขาลง", float(row.get("structure_bias", -1)) >= 0,
              "Market Structure"),
        check("ไม่มีการ Sweep เหนือแนวต้าน", not bool(row.get("sweep_high", True)),
              "หลีกเลี่ยง Bull Trap"),
        check("ADX อย่างน้อย 18", float(row.get("adx", float("nan"))) >= 18,
              f"ADX {float(row.get('adx', float('nan'))):.1f}"),
        check("RSI ต่ำกว่า 75", float(row.get("rsi", float("nan"))) < 75,
              f"RSI {float(row.get('rsi', float('nan'))):.1f}"),
        check("Volume อย่างน้อย 0.75×", float(row.get("volume_ratio", float("nan"))) >= 0.75,
              f"Volume {float(row.get('volume_ratio', float('nan'))):.2f}×"),
        check(f"คะแนนถึง +{score_threshold}", int(row["score"]) >= score_threshold,
              f"คะแนน {int(row['score']):+d}"),
        check("Technical Signal = BUY", technical == "BUY", technical),
        check("Futures สนับสนุน BUY", auto["signal"] == "BUY",
              str(auto["status"])),
    ])
    if coinglass is None:
        checks.append(RuleCheck("CoinGlass", None, "ไม่กรอก — ตัวกรองเสริมไม่ได้ยืนยัน"))
    else:
        checks.append(check("CoinGlass ไม่คัดค้าน BUY", cg["signal"] == "BUY",
                            str(cg["status"])))
    checks.append(check("Final Signal = BUY", final == "BUY", final))

    if entry.entry_low is None:
        checks.append(check("มี Entry Zone ที่ใช้เฝ้ารอได้", False, entry.reason))
    else:
        inside = current_price is not None and entry.entry_low <= current_price <= entry.entry_high
        checks.append(check("ราคา Spot ล่าสุดอยู่ในโซน", inside,
                            "ราคาในโซน" if inside else "รอราคาเข้าโซนหรือราคา Spot ไม่พร้อม"))
        candle_confirmed = (entry.entry_low <= float(row["close"]) <= entry.entry_high
                            and float(row["close"]) >= float(entry.anchor_price)
                            and float(row["close"]) > float(row["open"]))
        checks.append(check("แท่งล่าสุดปิดเขียวในโซนเหนือแนวรับ", candle_confirmed,
                            "ใช้แท่งที่ปิดแล้ว ไม่ใช่แท่งที่ยังวิ่ง"))
    checks.append(check("Entry พร้อมตามกฎปัจจุบัน", entry.status == "READY", entry.reason))

    return TimeframeReport(
        timeframe=timeframe, technical=technical, auto=auto["signal"], final=final,
        futures_status=auto["status"], coinglass_status=cg["status"],
        coinglass_blockers=tuple(cg["blocking_reasons"]),
        futures_reasons=tuple(auto["reasons"]), entry=entry,
        checks=tuple(checks), last_close=last_close,
        price_change_24h_pct=price_change, score=int(row["score"]),
        rsi=float(row["rsi"]), adx=float(row["adx"]),
        volume_ratio=float(row["volume_ratio"]),
        taker_buy_share20=float(row.get("taker_buy_share20", float("nan"))),
        trend=int(row["trend"]),
        higher_trend=int(row["higher_trend"]),
        structure_bias=int(row["structure_bias"]),
        green_candle=float(row["close"]) > float(row["open"]),
        source_bars=len(base),
        gaps=gaps, stale=stale,
    )
