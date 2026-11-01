"""Orbit v5.9.1: independent near-ready research and forward-only excursions.

Never converts WAIT to READY; does not change execution, TP, SL, or risk gates.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math

from validation_logic import MINUTE, MISSED_WINDOW_MS, _next_minute, _continuous, collect_bars


CHECKS = ("15m บริบทแนวโน้ม", "5m แตะโซน", "1m ปิดแท่งกลับตัว",
          "1m Volume", "1m Taker Flow")
NEAR_STATE = "NEAR_READY"


def assess_zone(zone: dict, decision, *, observed_state: str, venue: str,
                symbol: str, timestamp_ms: int, quote: float) -> dict | None:
    """A qualifying *watch*, not a risk-approved trade.

Require one and only one failing technical gate on one current zone.
Hard risk blocks, stale data and completed entries cannot be near-ready.
"""
    if observed_state not in ("WAIT", "WATCH") or decision.state != "WAIT_CONFIRM":
        return None
    if (zone.get("state") not in ("WATCH", "IN_ZONE") or
            decision.side not in ("LONG", "SHORT") or
            (venue == "BINANCE_TH_SPOT" and decision.side == "SHORT") or
            venue == "BITGET_USDT_FUTURES" or  # no verified directional 1m flow
            type(timestamp_ms) is not int or timestamp_ms <= 0 or
            not isinstance(quote, (int, float)) or not math.isfinite(quote) or quote <= 0):
        return None
    checks = decision.checks
    if len(checks) != len(CHECKS) or tuple(n for n, _, _ in checks) != CHECKS:
        return None
    passed = [bool(ok) for _, ok, _ in checks]
    if sum(passed) != 4:
        return None
    failed = passed.index(False)
    return {"t": timestamp_ms, "v": venue, "s": symbol, "sd": decision.side,
            "z": str(zone.get("name", ""))[:35],
            "lo": float(zone["low"]), "hi": float(zone["high"]),
            "p": float(quote), "fail": CHECKS[failed], "checks": passed,
            "st": NEAR_STATE}


def near_candidates(snapshot, settings, observation) -> list[dict]:
    """One independently confirmed, nearest candidate per side per scan."""
    from scalp_engine import scalp_watch_zones
    from zone_signal import evaluate_zone

    if observation.state not in ("WAIT", "WATCH"):
        return []
    venue, symbol = snapshot.venue, snapshot.symbol
    sides = ("LONG",) if venue == "BINANCE_TH_SPOT" else ("LONG", "SHORT")
    stamp = int(observation.checked_at.timestamp() * 1000)
    results = []
    for side in sides:
        quote = float(snapshot.ask if side == "LONG" else snapshot.bid)
        candidates = []
        for zone in scalp_watch_zones(snapshot, side):
            decision = evaluate_zone(snapshot, settings, zone, side, now=observation.checked_at)
            near = assess_zone(zone, decision, observed_state=observation.state,
                               venue=venue, symbol=symbol, timestamp_ms=stamp, quote=quote)
            if near is not None:
                gap = abs((near["lo"] + near["hi"]) / 2 - quote)
                candidates.append((gap, near))
        if candidates:
            results.append(min(candidates, key=lambda item: item[0])[1])
    return results


def forward_excursions(events: list[dict], validation_rows: list[dict],
                       venue: str, symbol: str, *, observed_until_ms: int | None = None,
                       minutes: int = 30) -> list[dict]:
    """Post-observation 1m OHLC only; no inferred fills or missed profit.

    One event per side per 30m window prevents duplicate scans from
    masquerading as independent opportunities. Incomplete windows are PENDING.
    """
    if minutes != 30:
        raise ValueError("v5.9.1 requires a fixed prospective 30m window")
    bars = collect_bars(validation_rows, venue, symbol)
    latest = observed_until_ms if observed_until_ms is not None else (bars[-1][0] + MINUTE if bars else 0)
    seen: set[tuple[str, int]] = set()
    output = []
    for event in sorted(events, key=lambda e: e["t"]):
        if event["v"] != venue or event["s"] != symbol or event["st"] != NEAR_STATE:
            continue
        key = (event["sd"], event["t"] // MISSED_WINDOW_MS)
        if key in seen:
            continue
        seen.add(key)
        start = _next_minute(event["t"])
        future = [b for b in bars if start <= b[0] < start + MISSED_WINDOW_MS]
        result = {"t": event["t"], "side": event["sd"],
                  "failed_gate": event["fail"], "price": event["p"],
                  "state": "PENDING_DATA", "favorable_pct": None,
                  "adverse_pct": None, "reached_0_5pct": None,
                  "reached_10_points": None}
        if (latest < start + MISSED_WINDOW_MS or len(future) != minutes or
                future[0][0] != start or not _continuous(future)):
            output.append(result)
            continue
        sign = 1 if event["sd"] == "LONG" else -1
        price = event["p"]
        favorable_price = max(b[2] for b in future) if sign == 1 else min(b[3] for b in future)
        adverse_price = min(b[3] for b in future) if sign == 1 else max(b[2] for b in future)
        favorable_pct = sign * (favorable_price - price) / price * 100
        adverse_pct = -sign * (adverse_price - price) / price * 100
        result.update(state="OBSERVED_30M",
                      favorable_pct=round(max(0.0, favorable_pct), 3),
                      adverse_pct=round(max(0.0, adverse_pct), 3),
                      reached_0_5pct=favorable_pct >= 0.5)
        if symbol == "PEPEUSDT":
            from scalp_fixed_tp import pepe_point_unit
            result["reached_10_points"] = sign * (favorable_price - price) >= float(pepe_point_unit(price) * 10)
        output.append(result)
    return output
