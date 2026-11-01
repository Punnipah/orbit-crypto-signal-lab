"""Conservative forward-only paper replay over *observed* closed 1m bars.

No retroactive READY, no invented candles, no account fills. The TP/SL order
inside a single minute is unknowable; pessimistically resolve it as STOP.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math


MINUTE = 60_000
ENTRY_VALID_FOR_MS = 180_000
MAX_HOLD_MS = 60 * MINUTE
MISSED_WINDOW_MS = 30 * MINUTE
MAX_ENTRY_DEVIATION_PCT = 0.3


def collect_bars(rows: list[dict], venue: str, symbol: str) -> list[list]:
    """Never interpolate missing bars or combine venues. Conflict => refuse."""
    values: dict[int, list] = {}
    for row in rows:
        if row["v"] != venue or row["s"] != symbol:
            continue
        for candle in row["bars"]:
            old = values.get(candle[0])
            if old is not None and old != candle:
                raise ValueError("conflicting closed-candle snapshots; replay blocked")
            values[candle[0]] = candle
    return [values[k] for k in sorted(values)]


def _next_minute(t: int) -> int:
    # Strictly later than scan, including an observation exactly at :00.
    return (t // MINUTE + 1) * MINUTE


def _continuous(window: list[list]) -> bool:
    return all(b[0] - a[0] == MINUTE for a, b in zip(window, window[1:]))


def _result(row: dict, state: str, **kwargs) -> dict:
    result = {"t": row["t"], "v": row["v"], "s": row["s"], "id": row["id"],
              "side": row["sd"], "strategy": row["strategy"],
              "regime": row["regime"], "state": state,
              "entry": None, "exit": None, "net_usdt": None, "net_r": None,
              "mfe_pct": None, "mae_pct": None, "exit_at": None,
              "ambiguous_stop_first": False}
    result.update(kwargs)
    return result


def unique_ready(rows: list[dict]) -> list[dict]:
    """One paper candidate per setup; repeated READY scans aren't new trades."""
    known = set()
    signals = []
    for row in sorted(rows, key=lambda r: r["t"]):
        if row["st"] != "READY":
            continue
        key = (row["v"], row["s"], row["sd"],
               row["id"] or str(row["t"] // 300_000))
        if key not in known:
            known.add(key)
            signals.append(row)
    return signals


def replay_ready(signal: dict, candles: list[list], target: str = "tp1") -> dict:
    """Next CLOSED 1m bar *after* the observation supplies paper fill.

    Marketable-paper entry at next bar open (not the strategy's older quote),
    subject to a tight maximum price gap. Includes fee, slippage and spread.
    Time exit after 60 minutes if complete consecutive observations exist.
    """
    if target not in ("tp1", "tp2", "tp10"):
        raise ValueError("unknown paper target")
    if signal["st"] != "READY" or signal["sd"] not in ("LONG", "SHORT"):
        return _result(signal, "NOT_APPROVED_SIGNAL")
    if target == "tp10" and signal["tp10_state"] != "ALTERNATIVE_READY":
        return _result(signal, "ALTERNATIVE_TP_BLOCK")
    tp = signal[target]
    stop, planned, qty = signal["sl"], signal["e"], signal["qty"]
    if any(v is None or v <= 0 for v in (tp, stop, planned, qty, signal["risk"])):
        return _result(signal, "UNUSABLE_PLAN")
    sign = 1 if signal["sd"] == "LONG" else -1
    if sign * (tp - planned) <= 0 or sign * (planned - stop) <= 0:
        return _result(signal, "UNUSABLE_PLAN")
    start = _next_minute(signal["t"])
    eligible = [b for b in candles if b[0] >= start]
    if not eligible:
        return _result(signal, "PENDING_NEXT_BAR")
    first = eligible[0]
    if first[0] > signal["t"] + ENTRY_VALID_FOR_MS:
        return _result(signal, "NO_ENTRY_DATA")
    if abs(first[1] / planned - 1) * 100 > MAX_ENTRY_DEVIATION_PCT:
        return _result(signal, "NOT_FILLED_PRICE_GAP")
    # A 5m scheduled fetch cannot promise exact order execution; this model
    # applies conservative costs to the next observable 1m OPEN.
    fee = signal["fee"]
    slip = signal["slip"]
    spread = signal["spread"]
    if any(v is None for v in (fee, slip, spread)):
        return _result(signal, "COST_DATA_UNAVAILABLE")
    side_cost = slip / 100 + spread / 20_000
    entry_fill = first[1] * (1 + sign * side_cost)
    if sign * (entry_fill - stop) <= 0 or sign * (tp - entry_fill) <= 0:
        return _result(signal, "NO_SAFE_ENTRY_AFTER_COST")
    end = first[0] + MAX_HOLD_MS
    bars = [b for b in eligible if b[0] < end]
    if not bars or bars[0][0] != first[0]:
        return _result(signal, "PENDING_NEXT_BAR")
    mfe = mae = 0.0
    for index, b in enumerate(bars):
        # If data skips a minute, we cannot know which barrier hit first.
        if index > 0 and b[0] != bars[index - 1][0] + MINUTE:
            return _result(signal, "INCOMPLETE_1M_DATA", entry=entry_fill)
        high, low = b[2], b[3]
        mfe = max(mfe, ((high - entry_fill) if sign == 1 else (entry_fill - low)) /
                  entry_fill * 100)
        mae = max(mae, ((entry_fill - low) if sign == 1 else (high - entry_fill)) /
                  entry_fill * 100)
        hit_stop = low <= stop if sign == 1 else high >= stop
        hit_tp = high >= tp if sign == 1 else low <= tp
        if hit_stop or hit_tp:
            status = "PAPER_STOP" if hit_stop else "PAPER_TP"
            raw_exit = stop if hit_stop else tp
            ambiguous = hit_stop and hit_tp
            break
    else:
        if bars[-1][0] + MINUTE < end:
            return _result(signal, "PENDING_OUTCOME", entry=entry_fill,
                           mfe_pct=round(mfe, 3), mae_pct=round(mae, 3))
        status = "PAPER_TIME_EXIT"
        raw_exit = bars[-1][4]
        ambiguous = False
    exit_fill = raw_exit * (1 - sign * side_cost)
    fees_usdt = qty * (entry_fill + exit_fill) * fee / 100
    net = sign * (exit_fill - entry_fill) * qty - fees_usdt
    if not math.isfinite(net) or not math.isfinite(signal["risk"]):
        return _result(signal, "UNUSABLE_PLAN")
    return _result(signal, status, entry=entry_fill, exit=exit_fill,
                   net_usdt=round(net, 6), net_r=round(net / signal["risk"], 4),
                   mfe_pct=round(mfe, 3), mae_pct=round(mae, 3),
                   exit_at=b[0] + MINUTE, ambiguous_stop_first=ambiguous)


def replay_all(rows: list[dict], venue: str, symbol: str, target: str = "tp1") -> list[dict]:
    candles = collect_bars(rows, venue, symbol)
    return [replay_ready(r, candles, target) for r in unique_ready(rows)
            if r["v"] == venue and r["s"] == symbol]


def missed_opportunities(rows: list[dict], venue: str, symbol: str) -> list[dict]:
    """Observation of directional favorable moves, NEVER a 'missed profit'."""
    from scalp_fixed_tp import pepe_point_unit
    candles = collect_bars(rows, venue, symbol)
    output = []
    seen_windows = set()
    for r in rows:
        if (r["v"] != venue or r["s"] != symbol or
                r["st"] not in ("WAIT", "WATCH", "RISK_BLOCK", "EXIT_WATCH") or
                r["sd"] not in ("LONG", "SHORT") or r["p"] is None):
            continue
        # Five-minute repeated WAITs during the *same* 30m market move are
        # one observation window, not six separate "missed opportunities".
        key = (r["sd"], r["t"] // MISSED_WINDOW_MS)
        if key in seen_windows:
            continue
        start = _next_minute(r["t"])
        future = [b for b in candles if start <= b[0] < start + MISSED_WINDOW_MS]
        if (len(future) != MISSED_WINDOW_MS // MINUTE or
                future[0][0] != start or not _continuous(future)):
            continue  # no claim if all 30 future 1m bars aren't observed
        seen_windows.add(key)
        sign = 1 if r["sd"] == "LONG" else -1
        favorable_price = (max(x[2] for x in future) if sign == 1
                           else min(x[3] for x in future))
        favorable = sign * (favorable_price - r["p"]) / r["p"] * 100
        ten_points = None
        if r["s"] == "PEPEUSDT":
            goal = float(pepe_point_unit(r["p"]) * 10)
            ten_points = sign * (favorable_price - r["p"]) >= goal
        output.append({"t": r["t"], "status": r["st"], "reason": r["why"],
                       "side": r["sd"], "favorable_pct": round(favorable, 3),
                       "reached_10_points": ten_points})
    return output


def performance(results: list[dict]) -> dict:
    finished = [r for r in results if r["net_usdt"] is not None]
    if not finished:
        return {"n": 0, "win_rate": None, "expectancy_r": None,
                "net_usdt": 0.0, "profit_factor": None, "max_drawdown_usdt": None}
    values = [r["net_usdt"] for r in finished]
    rs = [r["net_r"] for r in finished]
    positive = sum(x for x in values if x > 0)
    negative = -sum(x for x in values if x < 0)
    equity = peak = drawdown = 0.0
    for v in values:
        equity += v
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {"n": len(values), "win_rate": sum(v > 0 for v in values) / len(values),
            "expectancy_r": sum(rs) / len(rs), "net_usdt": sum(values),
            "profit_factor": positive / negative if negative else None,
            "max_drawdown_usdt": drawdown}


def walk_forward_report(results: list[dict], *, train_days: int = 7,
                        test_days: int = 7) -> list[dict]:
    """Rolling chronological report; no retraining and NO optimized parameters.

    Designed to compare the UNCHANGED strategy across time. A valid report
    requires enough calendar history; no synthetic early windows.
    """
    if train_days < 1 or test_days < 1:
        raise ValueError("positive chronological windows required")
    complete = sorted((r for r in results if r["net_usdt"] is not None),
                      key=lambda r: r["t"])
    if not complete:
        return []
    oldest = datetime.fromtimestamp(complete[0]["t"] / 1000, timezone.utc)
    newest = datetime.fromtimestamp(complete[-1]["t"] / 1000, timezone.utc)
    anchor = oldest.replace(hour=0, minute=0, second=0, microsecond=0)
    output = []
    while anchor + timedelta(days=train_days + test_days) <= newest:
        cut = anchor + timedelta(days=train_days)
        end = cut + timedelta(days=test_days)
        train = [r for r in complete if anchor.timestamp() * 1000 <= r["t"] < cut.timestamp() * 1000]
        test = [r for r in complete if cut.timestamp() * 1000 <= r["t"] < end.timestamp() * 1000]
        before = performance(train)
        after = performance(test)
        output.append({"period": f"{cut:%d/%m}–{end:%d/%m}",
                       "train_n": before["n"], "test_n": after["n"],
                       "train_avg_r": before["expectancy_r"],
                       "test_avg_r": after["expectancy_r"],
                       "test_net_usdt": after["net_usdt"]})
        anchor += timedelta(days=test_days)
    return output
