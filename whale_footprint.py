"""Orbit v5.8.5: read-only, venue-native *anonymous* trade-flow evidence.

This is an explanatory overlay, NOT a whale-identity detector or an input to
evaluate_scalp/evaluate_zone. No API credentials, orders, SL/TP or risk changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import statistics

from scalp_marketdata import (MarketDataError, MarketSnapshot, SYMBOL,
                              _get_json, venue_base)


@dataclass(frozen=True)
class LargePrints:
    source: str
    sample_size: int
    latest_at: datetime
    window_seconds: float
    threshold_usdt: float
    buy_count: int
    sell_count: int
    buy_usdt: float
    sell_usdt: float


@dataclass(frozen=True)
class WhaleFootprint:
    venue: str
    symbol: str
    checked_at: datetime
    candle_ms: int
    price: float
    delta_5m_usdt: float | None
    taker_buy_share_5m: float | None
    volume_ratio_5m: float
    price_change_5m_pct: float
    bid_depth_share: float
    spread_bps: float
    classification: str
    explanation: str
    prints: LargePrints | None = None
    print_note: str = ""


def _number(value: object, field: str) -> float:
    try:
        v = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{field}: invalid number") from None
    if not math.isfinite(v) or v <= 0:
        raise ValueError(f"{field}: must be positive and finite")
    return v


def parse_large_prints(raw: object, venue: str, now: datetime) -> LargePrints:
    """Use relative print size, not an invented notion of a whale account.

    Binance aggregates fills from one taker order; Bitget public fills are
    labelled buy/sell by that venue and must not be called certified taker CVD.
    A short 100/500-fill sample is *not* a complete one/five-minute history.
    """
    if now.tzinfo is None or not isinstance(raw, list) or not 20 <= len(raw) <= 1000:
        raise ValueError("recent trades insufficient")
    values: list[tuple[int, float, bool]] = []
    for row in raw:
        if not isinstance(row, dict):
            raise ValueError("trade malformed")
        if venue in ("BINANCE_TH_SPOT", "BINANCE_GLOBAL_USDM"):
            if not isinstance(row.get("m"), bool):
                raise ValueError("missing Binance maker flag")
            buy = not row["m"]
            stamp, price, qty = row.get("T"), row.get("p"), row.get("q")
        elif venue == "BITGET_USDT_FUTURES":
            if row.get("side") not in ("buy", "sell"):
                raise ValueError("missing Bitget side")
            buy = row["side"] == "buy"
            stamp, price, qty = row.get("ts"), row.get("price"), row.get("size")
        else:
            raise ValueError("unknown trading venue")
        try:
            timestamp = int(stamp)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("bad trade timestamp") from None
        usd = _number(price, "price") * _number(qty, "quantity")
        if timestamp < 0 or timestamp > int(now.timestamp() * 1000) + 5_000:
            raise ValueError("trade timestamp in future")
        values.append((timestamp, usd, buy))
    latest_ms = max(x[0] for x in values)
    oldest_ms = min(x[0] for x in values)
    if (int(now.timestamp() * 1000) - latest_ms > 90_000 or
            latest_ms - oldest_ms > 86_400_000):
        raise ValueError("public trade sample stale or spans too long")
    # At least 5x the sample median and $500; only relative *large prints*,
    # never a declaration that a single named whale placed an order.
    threshold = max(500.0, statistics.median(v for _, v, _ in values) * 5)
    large = [(usd, buy) for _, usd, buy in values if usd >= threshold]
    source = ("Binance aggregate taker fills" if venue.startswith("BINANCE_")
              else "Bitget public fills: side proxy")
    return LargePrints(source, len(values),
                       datetime.fromtimestamp(latest_ms / 1000, timezone.utc),
                       (latest_ms - oldest_ms) / 1000, threshold,
                       sum(1 for _, buy in large if buy),
                       sum(1 for _, buy in large if not buy),
                       sum(usd for usd, buy in large if buy),
                       sum(usd for usd, buy in large if not buy))


def fetch_large_prints(snapshot: MarketSnapshot) -> LargePrints:
    """Optional same-venue public data. Never substitute another market."""
    if not SYMBOL.fullmatch(snapshot.symbol):
        raise MarketDataError("invalid symbol")
    if snapshot.venue == "BITGET_USDT_FUTURES":
        from scalp_bitget import _api, CATEGORY
        raw = _api("fills", {"category": CATEGORY, "symbol": snapshot.symbol, "limit": 100})
    else:
        base, prefix = venue_base(snapshot.venue)
        raw = _get_json(base, prefix + "/aggTrades", {"symbol": snapshot.symbol, "limit": 500})
    try:
        # Public fills are requested AFTER the candle/book snapshot. Validate
        # their freshness at response time, not against that older snapshot.
        return parse_large_prints(raw, snapshot.venue, datetime.now(timezone.utc))
    except ValueError as exc:
        raise MarketDataError(f"public prints unusable: {exc}") from None


def analyze_footprint(snapshot: MarketSnapshot, *, prints: LargePrints | None = None,
                      print_note: str = "") -> WhaleFootprint:
    """Calculate auditable indicators on CLOSED 1m candles from the chosen venue.

    `prints` is supplementary. This function cannot approve a trade.
    Missing taker volume (e.g. Bitget) is kept unknown; never imputed from
    candle colour, price, another exchange or synthetic data.
    """
    one = snapshot.frames["1m"]
    if len(one) < 55:
        raise ValueError("insufficient closed 1m history")
    now_ms = int(snapshot.checked_at.timestamp() * 1000)
    candle_ms = int(one.open_ms.iloc[-1])
    if not 0 <= now_ms - candle_ms - 60_000 <= 105_000:
        raise ValueError("last closed 1m candle stale or in future")
    last = one.tail(5)
    historic = one.iloc[-45:-5]
    baseline = float(historic.volume.mean()) * 5
    volume = float(last.volume.sum())
    if not math.isfinite(baseline) or baseline <= 0 or volume <= 0:
        raise ValueError("insufficient baseline trading volume")
    ratio = volume / baseline
    price = float(last.close.iloc[-1])
    initial = float(last.open.iloc[0])
    change_pct = (price / initial - 1) * 100
    if not math.isfinite(change_pct):
        raise ValueError("invalid price movement")
    bid_depth = snapshot.bid_depth_usdt
    ask_depth = snapshot.ask_depth_usdt
    if (not all(math.isfinite(v) and v > 0 for v in (bid_depth, ask_depth))
            or not math.isfinite(snapshot.spread_bps)):
        raise ValueError("orderbook snapshot unavailable")
    bid_share = bid_depth / (bid_depth + ask_depth)

    buys = last.taker_buy.astype(float)
    # Require all five closed bars to have verified aggressor volume.
    covered = (buys.notna().all() and all(math.isfinite(float(b)) and
               0 <= float(b) <= float(v) for b, v in zip(buys, last.volume)))
    delta = None
    buy_share = None
    if covered:
        buy_share = float(buys.sum()) / volume
        delta = float(((2 * buys - last.volume) * last.close).sum())

    # Descriptive, uncalibrated hypotheses only. Avoid "whale buying" labels.
    if delta is None:
        classification = "FLOW_UNAVAILABLE"
        explanation = "ปริมาณซื้อ/ขายเชิงรุกของตลาดนี้ไม่ครบ · ประเมินฝ่ายรุกไม่ได้"
    elif ratio >= 1.3 and abs(change_pct) <= 0.15 and buy_share <= 0.42:
        classification = "POSSIBLE_BID_ABSORPTION"
        explanation = "ขายเชิงรุกมากแต่ราคาขยับน้อย · อาจมีแรงรับซ่อนอยู่ (ยังไม่ยืนยันผู้ซื้อ)"
    elif ratio >= 1.3 and abs(change_pct) <= 0.15 and buy_share >= 0.58:
        classification = "POSSIBLE_ASK_ABSORPTION"
        explanation = "ซื้อเชิงรุกมากแต่ราคาขยับน้อย · อาจมีแรงขายดักอยู่ (ยังไม่ยืนยันผู้ขาย)"
    elif ratio >= 1.2 and buy_share >= 0.60 and change_pct > 0:
        classification = "BUY_PRESSURE"
        explanation = "ซื้อเชิงรุกและราคาขยับขึ้นพร้อมปริมาณเพิ่ม · ไม่ใช่หลักฐานว่าวาฬซื้อ"
    elif ratio >= 1.2 and buy_share <= 0.40 and change_pct < 0:
        classification = "SELL_PRESSURE"
        explanation = "ขายเชิงรุกและราคาลดพร้อมปริมาณเพิ่ม · ไม่ใช่หลักฐานว่าวาฬขาย"
    else:
        classification = "MIXED"
        explanation = "แรงซื้อขายผสมกันหรือยังไม่เด่นพอ · ตลาดอาจแกว่งในกรอบ"

    return WhaleFootprint(snapshot.venue, snapshot.symbol, snapshot.checked_at,
                          candle_ms, price, delta, buy_share, ratio,
                          change_pct, bid_share, snapshot.spread_bps,
                          classification, explanation, prints, print_note[:140])
