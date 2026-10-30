"""Conservative closed-candle PAPER outcome tracking for Futures alerts.

This journal does not connect to the user's exchange account or claim fills.
Only candles opened AFTER the alert can count as potential paper entries.
When SL and TP touch during one candle, the worse STOP outcome wins.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import math

import pandas as pd

from futures_daytrade import FuturesObservation


MAX_HISTORY = 400
MAX_SEEN = 800
ENTRY_WINDOW = timedelta(hours=3)
MAX_HOLD = timedelta(hours=24)
MAX_UNVERIFIABLE = timedelta(hours=72)


def empty_paper() -> dict:
    return {"active": {}, "history": [], "seen": []}


def _utc(value: str | datetime) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Paper timestamp must have timezone")
    return value.astimezone(timezone.utc)


def _ceil_next_15m(when: datetime) -> datetime:
    utc = _utc(when)
    period = 15 * 60
    seconds = utc.timestamp()
    return datetime.fromtimestamp(math.ceil(seconds / period) * period, timezone.utc)


def _event(plan: dict, event: str, when: datetime, note: str) -> dict:
    event_id = hashlib.sha256(f"PAPER|{plan['symbol']}|{plan['setup']}|{event}".encode()).hexdigest()[:24]
    side = "🟢 LONG" if plan["side"] == "LONG" else "🔴 SHORT"
    label = plan.get("requested", plan["symbol"])
    return {"id": event_id,
            "text": (f"🪐 Orbit FUTURES PAPER · {event}\n{label} → {plan['symbol']} | {side}\n"
                     f"เวลา: {when.astimezone(timezone(timedelta(hours=7))):%d/%m/%Y %H:%M} ไทย\n"
                     f"{note}\n⚠️ ผลจำลองจากแท่งปิด ไม่ยืนยันว่าซื้อขายจริงได้")}


def _r_multiple(plan: dict, exit_price: float) -> float:
    entry = float(plan["entry_price"])
    stop = float(plan["stop"])
    direction = 1 if plan["side"] == "LONG" else -1
    costs = entry * float(plan["cost_pct"]) / 100
    risk = abs(entry - stop) + costs
    result = (direction * (exit_price - entry) - costs) / risk
    if plan.get("tp1_at"):
        first = (direction * (float(plan["tp1"]) - entry) - costs) / risk
        return round((first + result) / 2, 4)
    return round(result, 4)


def _closed(paper: dict, plan: dict, status: str, when: datetime,
            exit_price: float | None, events: list[dict]) -> None:
    record = {k: v for k, v in plan.items() if k != "processed_until"}
    record.update({"status": status, "closed_at": when.isoformat(),
                   "exit_price": exit_price,
                   "net_r_estimate": _r_multiple(plan, exit_price) if exit_price is not None and plan.get("entry_price") else None})
    paper["history"].append(record)
    paper["history"] = paper["history"][-MAX_HISTORY:]
    paper["active"].pop(plan["symbol"], None)
    detail = (f"ผลจำลอง {record['net_r_estimate']:+.2f}R · ไม่รวม Funding จริง" if record["net_r_estimate"] is not None
              else "ไม่มีการเข้าออร์เดอร์จำลอง")
    events.append(_event(plan, status, when, detail))


def _advance(paper: dict, plan: dict, frame: pd.DataFrame,
             now: datetime, events: list[dict]) -> None:
    if not isinstance(frame, pd.DataFrame) or frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        return  # Missing data: fail closed; do not manufacture outcomes.
    created = _utc(plan["created_at"])
    next_open = _ceil_next_15m(created)
    prev = _utc(plan["processed_until"]) if plan.get("processed_until") else None
    bars = frame.loc[frame.index >= next_open]
    if prev is not None:
        bars = bars.loc[bars.index > prev]
    if bars.empty:
        return
    gap = ((prev is not None and bars.index[0] - prev != pd.Timedelta(minutes=15))
           or (prev is None and bars.index[0] > next_open)
           or (bars.index.to_series().diff().dropna() != pd.Timedelta(minutes=15)).any())
    if gap:
        if now - created > MAX_UNVERIFIABLE:
            _closed(paper, plan, "DATA_GAP_UNKNOWN", now, None, events)
        # An unseen candle could have hit STOP; don't claim a paper win.
        return

    for stamp, candle in bars.iterrows():
        opened = stamp.to_pydatetime().astimezone(timezone.utc)
        closed = opened + timedelta(minutes=15)
        if closed > now:
            break
        high, low, close = (float(candle[key]) for key in ("high", "low", "close"))
        if not (math.isfinite(high) and math.isfinite(low) and math.isfinite(close)
                and low > 0 and high >= low and low <= close <= high):
            return
        plan["processed_until"] = opened.isoformat()
        if not plan.get("entry_at"):
            if closed > created + ENTRY_WINDOW:
                _closed(paper, plan, "NO_FILL_EXPIRED", closed, None, events)
                return
            touches = low <= float(plan["entry_high"]) and high >= float(plan["entry_low"])
            if not touches:
                continue
            # Deliberately pessimistic LIMIT-style fill assumption at zone edge.
            plan["entry_price"] = (float(plan["entry_high"]) if plan["side"] == "LONG"
                                   else float(plan["entry_low"]))
            plan["entry_at"] = closed.isoformat()
            events.append(_event(plan, "PAPER_ENTRY", closed, "ราคาแท่งปิดแตะโซน · จำลอง Fill ที่ขอบโซนฝั่งเสียเปรียบ"))

        if plan["side"] == "LONG":
            stop_hit, target_hit = low <= float(plan["stop"]), high >= float(plan["tp2"])
            first_hit = high >= float(plan["tp1"])
        else:
            stop_hit, target_hit = high >= float(plan["stop"]), low <= float(plan["tp2"])
            first_hit = low <= float(plan["tp1"])

        if stop_hit:  # Ambiguous intrabar order: worst case always wins.
            _closed(paper, plan, "STOP", closed, float(plan["stop"]), events)
            return
        if target_hit:
            if not plan.get("tp1_at"):
                plan["tp1_at"] = closed.isoformat()
            _closed(paper, plan, "TP2", closed, float(plan["tp2"]), events)
            return
        if first_hit and not plan.get("tp1_at"):
            plan["tp1_at"] = closed.isoformat()
            events.append(_event(plan, "TP1", closed, "แตะ TP1 ตามข้อมูลแท่งปิด · จำลองปิดครึ่งสถานะ"))
        if closed > _utc(plan["entry_at"]) + MAX_HOLD:
            _closed(paper, plan, "TIME_EXIT", closed, close, events)
            return


def update_paper(paper: dict, observations: list[FuturesObservation],
                 frames: dict[str, pd.DataFrame], now: datetime, *,
                 round_trip_cost_pct: float = 0.16,
                 requested_by_contract: dict[str, str] | None = None) -> list[dict]:
    """Advance existing frozen setups first; only then register fresh READY plans."""
    if not isinstance(paper, dict) or not all(key in paper for key in ("active", "history", "seen")):
        raise ValueError("Paper state invalid")
    if now.tzinfo is None or not math.isfinite(round_trip_cost_pct) or not 0 < round_trip_cost_pct <= 1:
        raise ValueError("Paper clock/cost invalid")
    requested_by_contract = requested_by_contract or {}
    events = []
    for symbol, plan in list(paper["active"].items()):
        if symbol in frames:
            _advance(paper, plan, frames[symbol], now, events)
    for ob in observations:
        if ob.state not in {"READY_LONG", "READY_SHORT"} or not ob.setup_id:
            continue
        if ob.symbol in paper["active"]:
            continue
        marker = f"{ob.symbol}|{ob.setup_id}"
        if marker in paper["seen"]:
            continue
        prices = (ob.entry_low, ob.entry_high, ob.stop, ob.tp1, ob.tp2)
        if any(x is None or not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0 for x in prices):
            continue
        paper["seen"].append(marker)
        paper["seen"] = paper["seen"][-MAX_SEEN:]
        paper["active"][ob.symbol] = {
            "symbol": ob.symbol, "requested": requested_by_contract.get(ob.symbol, ob.symbol),
            "setup": ob.setup_id, "side": ob.direction, "created_at": now.isoformat(),
            "entry_low": ob.entry_low, "entry_high": ob.entry_high, "stop": ob.stop,
            "tp1": ob.tp1, "tp2": ob.tp2, "cost_pct": round_trip_cost_pct,
            "entry_price": None, "entry_at": None, "tp1_at": None, "processed_until": None,
        }
    return events


def paper_stats(history: list[dict]) -> dict:
    """Descriptive statistics only; never label these live realized trades."""
    trades = sorted((x for x in history if isinstance(x.get("net_r_estimate"), (int, float))
                     and math.isfinite(x["net_r_estimate"])), key=lambda x: x["closed_at"])
    results = [float(x["net_r_estimate"]) for x in trades]
    equity = peak = max_drawdown = 0.0
    for r in results:
        equity += r
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    gains = sum(max(0.0, r) for r in results)
    losses = -sum(min(0.0, r) for r in results)
    return {"trades": len(results), "wins": sum(r > 0 for r in results),
            "win_rate_pct": 100 * sum(r > 0 for r in results) / len(results) if results else None,
            "expectancy_r": sum(results) / len(results) if results else None,
            "profit_factor": gains / losses if losses > 0 else None,
            "max_drawdown_r": max_drawdown, "equity_r": equity,
            "no_fill": sum(x.get("status") == "NO_FILL_EXPIRED" for x in history)}
