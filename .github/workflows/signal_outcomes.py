"""Conservative retrospective *hypothetical* signal paths, never trade fills.

Observations are time-stamped manually by the user. For a READY signal this
module assumes the next fully observable 1h candle OPEN is a possible fill
ONLY if that open lies within the previously recorded Entry Zone. Neither
the actual trade nor queue position/order type is known. Stop wins ties.
"""

from __future__ import annotations

import math

import pandas as pd


def _value(row: dict, key: str) -> float | None:
    try:
        value = float(row.get(key, ""))
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) else None


def evaluate_recorded_signals(records: list[dict], candles: pd.DataFrame,
                              symbol: str, *, horizon_bars: int = 48) -> pd.DataFrame:
    if horizon_bars < 1 or horizon_bars > 720:
        raise ValueError("ช่วงประเมินต้องอยู่ระหว่าง 1–720 แท่ง")
    if candles.empty or not isinstance(candles.index, pd.DatetimeIndex) or candles.index.tz is None:
        raise ValueError("ข้อมูลแท่ง 1h ต้องมี timezone")
    if not {"open", "high", "low", "close"}.issubset(candles.columns):
        raise ValueError("ไม่มีราคา OHLC ที่ใช้ตรวจผล")
    data = candles.sort_index()
    results = []
    for row in records:
        if row.get("symbol") != symbol or row.get("entry_status") != "READY":
            continue
        entry_low = _value(row, "entry_low")
        entry_high = _value(row, "entry_high")
        stop = _value(row, "stop_loss")
        target = _value(row, "tp2")
        base = {"observed_at_th": row.get("observed_at_th"), "symbol": symbol,
                "status": "UNVERIFIABLE", "assumed_entry": None,
                "exit_price": None, "net_r_model": None}
        try:
            when = pd.Timestamp(row["observed_at_th"])
            when = when.tz_localize("Asia/Bangkok") if when.tz is None else when
            when = when.tz_convert("UTC")
        except (ValueError, TypeError, KeyError):
            base["status"] = "INVALID_OBSERVED_TIME"
            results.append(base)
            continue
        if any(x is None for x in (entry_low, entry_high, stop, target)) or not (
                0 < stop < entry_low <= entry_high < target):
            base["status"] = "INVALID_PLAN"
            results.append(base)
            continue
        # A signal observed at 10:30 UTC can only be replayed on the 11:00
        # opening candle, never the candle that had already begun at 10:00.
        candidates = data.index.searchsorted(when, side="left")
        if candidates >= len(data):
            base["status"] = "PENDING_NEXT_1H_CANDLE"
            results.append(base)
            continue
        if when < data.index[0]:
            base["status"] = "OUTSIDE_AVAILABLE_HISTORY"
            results.append(base)
            continue
        first = data.iloc[candidates]
        raw_open = float(first["open"])
        if not entry_low <= raw_open <= entry_high:
            base["status"] = "NOT_FILLED_NEXT_OPEN"
            results.append(base)
            continue
        base["assumed_entry"] = raw_open
        path = data.iloc[candidates:candidates + horizon_bars]
        previous_time = None
        for at, candle in path.iterrows():
            if previous_time is not None and (at - previous_time).total_seconds() != 3600:
                base["status"] = "DATA_GAP"
                break
            previous_time = at
            if float(candle["low"]) <= stop:
                base["status"] = "HYPOTHETICAL_STOP"
                base["exit_price"] = min(float(candle["open"]), stop)
                break
            if float(candle["high"]) >= target:
                base["status"] = "HYPOTHETICAL_TP2"
                base["exit_price"] = target
                break
        if base["exit_price"] is None and base["status"] != "DATA_GAP":
            # If there are fewer completed bars than the horizon, a surviving
            # position is still unknown. Do not mark it as a winner or loser.
            base["status"] = "PENDING" if len(path) < horizon_bars else "NO_EXIT_WITHIN_HORIZON"
        fee = _value(row, "fee_pct_per_side")
        slip = _value(row, "slippage_pct_per_side")
        if base["exit_price"] is not None and fee is not None and slip is not None and (
                0 <= fee <= 5 and 0 <= slip <= 5):
            entry_cost = raw_open * (1 + slip / 100) * (1 + fee / 100)
            stop_proceeds = stop * (1 - slip / 100) * (1 - fee / 100)
            exit_proceeds = base["exit_price"] * (1 - slip / 100) * (1 - fee / 100)
            risk = entry_cost - stop_proceeds
            if risk > 0:
                base["net_r_model"] = (exit_proceeds - entry_cost) / risk
        results.append(base)
    return pd.DataFrame(results)
