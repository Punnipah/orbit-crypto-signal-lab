"""Read-only Spot liquidity and anonymous aggressive-trade footprints.

No order submissions, no exchange account, no API keys. Book levels are
cancellable and a single snapshot cannot identify market makers or whales.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math

from binance_data import PublicDataError, _get_json
from multi_timeframe import RuleCheck


@dataclass(frozen=True)
class MicrostructureSnapshot:
    symbol: str
    requested_at: datetime
    last_trade_at: datetime
    bid: float
    ask: float
    spread_bps: float
    depth_bid_quote: float
    depth_ask_quote: float
    near_bid_share: float
    aggressor_buy_share: float
    aggregate_trades: int
    trade_quote_volume: float
    ask_impact_bps: float | None
    requested_notional: float
    source: str = "Binance Spot public bookTicker + depth + aggTrades (single exchange)"


def _positive(value: object, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise PublicDataError(f"{name} ไม่ใช่ตัวเลข") from exc
    if not math.isfinite(number) or number <= 0:
        raise PublicDataError(f"{name} ไม่ใช่ค่าบวกที่ใช้ได้")
    return number


def _levels(entries: object, name: str, *, is_bid: bool) -> list[tuple[float, float]]:
    if not isinstance(entries, list) or not entries:
        raise PublicDataError(f"Order Book {name} ไม่มีข้อมูล")
    result = []
    for item in entries:
        if not isinstance(item, (tuple, list)) or len(item) < 2:
            raise PublicDataError(f"Order Book {name} ผิดรูปแบบ")
        result.append((_positive(item[0], "ราคาในสมุด"), _positive(item[1], "ปริมาณในสมุด")))
    return sorted(result, key=lambda x: x[0], reverse=is_bid)


def parse_microstructure(
    symbol: str, book_ticker: dict, book: dict, trades: list,
    *, requested_notional: float, now: datetime,
) -> MicrostructureSnapshot:
    if now.tzinfo is None or not math.isfinite(requested_notional) or requested_notional <= 0:
        raise PublicDataError("เวลา/มูลค่าซื้อจำลองไม่ถูกต้อง")
    if not isinstance(book_ticker, dict) or book_ticker.get("symbol") != symbol:
        raise PublicDataError("Bid/Ask ไม่ตรงกับคู่เหรียญ")
    if not isinstance(book, dict) or not book.get("lastUpdateId"):
        raise PublicDataError("Order Book ไม่พร้อม")
    bids = _levels(book.get("bids"), "Bid", is_bid=True)
    asks = _levels(book.get("asks"), "Ask", is_bid=False)
    bid = _positive(book_ticker.get("bidPrice"), "Best Bid")
    ask = _positive(book_ticker.get("askPrice"), "Best Ask")
    if ask <= bid or asks[0][0] <= bids[0][0]:
        raise PublicDataError("Bid/Ask ผิดลำดับ")
    # These are separate REST requests, not an atomic exchange snapshot.
    if abs(asks[0][0] - ask) / ask > 0.005 or abs(bids[0][0] - bid) / bid > 0.005:
        raise PublicDataError("Order Book และ Bid/Ask ต่างกันเกิน 0.5% ระหว่างเรียกข้อมูล")
    mid = (ask + bid) / 2
    spread_bps = (ask - bid) / mid * 10_000
    near_bid = sum(p * q for p, q in bids if p >= mid * 0.995)
    near_ask = sum(p * q for p, q in asks if p <= mid * 1.005)
    total_near = near_bid + near_ask
    if total_near <= 0:
        raise PublicDataError("Order Book ไม่มีปริมาณในช่วง ±0.5%")

    remaining = requested_notional
    units = total_paid = 0.0
    for p, q in asks:
        spend = min(remaining, p * q)
        units += spend / p
        total_paid += spend
        remaining -= spend
        if remaining <= requested_notional * 1e-10:
            break
    impact = (total_paid / units / ask - 1) * 10_000 if remaining <= requested_notional * 1e-10 and units > 0 else None

    if not isinstance(trades, list) or not trades:
        raise PublicDataError("Aggregate Trades ไม่พร้อม")
    buy_quote = sell_quote = 0.0
    latest_ms = 0
    for trade in trades:
        if not isinstance(trade, dict) or not isinstance(trade.get("m"), bool):
            raise PublicDataError("Aggressor Side ไม่ถูกต้อง")
        price = _positive(trade.get("p"), "ราคาซื้อขาย")
        qty = _positive(trade.get("q"), "ปริมาณซื้อขาย")
        try:
            trade_ms = int(trade["T"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PublicDataError("เวลา Aggregate Trade ไม่ถูกต้อง") from exc
        latest_ms = max(latest_ms, trade_ms)
        # m=true: buyer was maker => seller took liquidity.
        if trade["m"]:
            sell_quote += price * qty
        else:
            buy_quote += price * qty
    total_flow = buy_quote + sell_quote
    last_trade = datetime.fromtimestamp(latest_ms / 1000, timezone.utc)
    if last_trade > now + timedelta(minutes=5):
        raise PublicDataError("ข้อมูลเทรดแสดงเวลาอนาคต")
    return MicrostructureSnapshot(
        symbol=symbol, requested_at=now, last_trade_at=last_trade,
        bid=bid, ask=ask, spread_bps=spread_bps,
        depth_bid_quote=near_bid, depth_ask_quote=near_ask,
        near_bid_share=near_bid / total_near,
        aggressor_buy_share=buy_quote / total_flow,
        aggregate_trades=len(trades), trade_quote_volume=total_flow,
        ask_impact_bps=impact, requested_notional=requested_notional,
    )


def fetch_microstructure(symbol: str, notional: float) -> MicrostructureSnapshot:
    """Fetch three Binance public sources, all for the same Spot symbol."""
    ticker = _get_json("/ticker/bookTicker", {"symbol": symbol})
    depth = _get_json("/depth", {"symbol": symbol, "limit": 100})
    trades = _get_json("/aggTrades", {"symbol": symbol, "limit": 500})
    return parse_microstructure(symbol, ticker, depth, trades,
                                requested_notional=notional,
                                now=datetime.now(timezone.utc))


def microstructure_checks(snapshot: MicrostructureSnapshot | None, *, now: datetime,
                          requested_notional: float) -> tuple[RuleCheck, ...]:
    """Conservative gating; parameters are explicit heuristics, not calibrated."""
    if snapshot is None:
        return (RuleCheck("สภาพคล่อง Spot", False, "Book / Trades ไม่พร้อม: ห้ามยืนยัน READY"),)
    if now.tzinfo is None:
        raise ValueError("เวลาต้องมี timezone")
    age = now - snapshot.requested_at
    trade_age = now - snapshot.last_trade_at
    return (
        RuleCheck("ข้อมูล Order Book ใหม่ไม่เกิน 90 วินาที",
                  timedelta(0) <= age <= timedelta(seconds=90), f"อายุข้อมูล {age.total_seconds():.0f} วินาที (เวลาเมื่อร้องขอ)"),
        RuleCheck("รายการเทรดล่าสุดไม่เกิน 15 นาที",
                  timedelta(0) <= trade_age <= timedelta(minutes=15), f"เทรดล่าสุด {trade_age.total_seconds()/60:.1f} นาที"),
        RuleCheck("Bid/Ask Spread ไม่เกิน 30 bps (0.30%)",
                  snapshot.spread_bps <= 30, f"Spread {snapshot.spread_bps:.1f} bps"),
        RuleCheck("Book Depth สองฝั่งเพียงพอ (แต่ละด้าน ≥5× มูลค่าดีล)",
                  min(snapshot.depth_bid_quote, snapshot.depth_ask_quote) >= 5 * requested_notional,
                  f"Bid {snapshot.depth_bid_quote:,.0f}; Ask {snapshot.depth_ask_quote:,.0f} หน่วยสกุลราคา"),
        RuleCheck("ต้นทุนกวาด Ask Book สำหรับดีลจำลองไม่เกิน 25 bps",
                  snapshot.ask_impact_bps is not None and snapshot.ask_impact_bps <= 25,
                  f"Impact {snapshot.ask_impact_bps:.1f} bps" if snapshot.ask_impact_bps is not None else "Ask Book ไม่พอ"),
        RuleCheck("Bid Depth ไม่อ่อนกว่าฝั่ง Ask มากเกินไป",
                  snapshot.near_bid_share >= .35, f"Bid share {snapshot.near_bid_share*100:.1f}% (Book อาจมี Spoofing)"),
        RuleCheck("Aggressive BUY ≥52% ของ 500 Aggregate Trades ล่าสุด",
                  snapshot.aggregate_trades >= 30 and snapshot.aggressor_buy_share >= .52,
                  f"Buy {snapshot.aggressor_buy_share*100:.1f}% · {snapshot.aggregate_trades} aggTrades"),
    )
