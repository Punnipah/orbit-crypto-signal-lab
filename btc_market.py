"""Causal BTC market-regime context for altcoin Spot buy setups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from analysis_engine import indicators
from binance_data import TIMEFRAMES, count_time_gaps
from multi_timeframe import RuleCheck


@dataclass(frozen=True)
class BtcRegime:
    trend_4h: int
    trend_1d: int
    close_4h: datetime
    close_1d: datetime
    clean: bool
    source: str = "Binance Spot BTCUSDT completed candles"


def _classify(frame: pd.DataFrame) -> int:
    row = indicators(frame).iloc[-1]
    if row["close"] > row["ema200"] and row["ema50"] > row["ema200"]:
        return 1
    if row["close"] < row["ema200"] and row["ema50"] < row["ema200"]:
        return -1
    return 0


def btc_regime(four_hour: pd.DataFrame, daily: pd.DataFrame, *, now: datetime) -> BtcRegime:
    if now.tzinfo is None:
        raise ValueError("ต้องระบุเวลาแบบมี timezone")
    last_4h = (four_hour.index[-1] + timedelta(minutes=TIMEFRAMES["4h"])).to_pydatetime()
    last_day = (daily.index[-1] + timedelta(minutes=TIMEFRAMES["1d"])).to_pydatetime()
    fresh = (last_4h >= now - timedelta(hours=8)
             and last_day >= now - timedelta(days=2)
             and count_time_gaps(four_hour, "4h") == 0
             and count_time_gaps(daily, "1d") == 0)
    return BtcRegime(_classify(four_hour), _classify(daily), last_4h, last_day, fresh)


def btc_context_checks(regime: BtcRegime | None) -> tuple[RuleCheck, ...]:
    if regime is None:
        return (RuleCheck("ภาวะตลาด BTC", False, "ข้อมูล BTC 4h/1d ไม่พร้อม"),)
    return (
        RuleCheck("BTC Market Regime ยังสดและต่อเนื่อง", regime.clean,
                  "Binance BTCUSDT 4h/1d"),
        RuleCheck("BTC ไม่เป็นขาลงใน 4h และ 1d", regime.trend_4h >= 0 and regime.trend_1d >= 0,
                  f"BTC 4h={regime.trend_4h:+d}, 1d={regime.trend_1d:+d} (0 = ไม่ชัด)"),
    )
