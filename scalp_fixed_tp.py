"""Read-only fixed 10-USDT *price movement* TP, never an automatic order.

This is intentionally separate from the approved strategy target. A candidate
may be READY under its original plan yet have an unprofitable fixed 10-USDT TP.
The overlay must reject that combination instead of silently replacing TP2.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_UP
import math

from scalp_engine import ScalpSettings, _floor_step, _tick_price
from scalp_marketdata import MarketSnapshot


FIXED_PRICE_MOVE_USDT = Decimal("10")
MAX_PRICE_MOVE_PCT = 5.5  # Same gross target sanity ceiling as the scalp engine.


@dataclass(frozen=True)
class FixedTPPreview:
    state: str
    reason: str
    side: str
    entry: float
    target: float | None
    move_pct: float | None
    notional_usdt: float
    gross_profit_usdt: float | None
    estimated_cost_usdt: float | None
    estimated_net_usdt: float | None
    net_rr: float | None


def fixed_tp_preview(snapshot: MarketSnapshot, settings: ScalpSettings, side: str,
                     *, entry: float | None = None, stop: float | None = None,
                     qty: float | None = None, signal_ready: bool = False,
                     price_move_usdt: Decimal = FIXED_PRICE_MOVE_USDT,
                     plan_label: str = "TP 10 USDT") -> FixedTPPreview:
    """Evaluate an optional quote-price TP; default is a fixed 10 USDT move.

    `signal_ready=False` is a *hypothetical quote preview*, never permission
    to trade even if after-cost reward looks favorable. Spot short is forbidden.
    Existing zone/trend READY gates remain the sole source of entry approval.
    """
    if side not in ("LONG", "SHORT"):
        raise ValueError("side must be LONG or SHORT")
    if not settings.paper_only:
        raise ValueError("fixed TP is PAPER ONLY")
    if not price_move_usdt.is_finite() or price_move_usdt <= 0:
        raise ValueError("price move must be positive")
    price = float(entry if entry is not None else
                  snapshot.ask if side == "LONG" else snapshot.bid)
    if not math.isfinite(price) or price <= 0:
        raise ValueError("invalid entry quote")
    if snapshot.instrument.tick_price <= 0 or snapshot.instrument.step_qty <= 0:
        raise ValueError("invalid exchange price/quantity step")

    def preview(state: str, reason: str, target: float | None,
                move: float | None = None, *, notional: float = 0,
                gross: float | None = None, costs: float | None = None,
                net: float | None = None, rr: float | None = None) -> FixedTPPreview:
        return FixedTPPreview(state, reason, side, price, target, move,
                              notional, gross, costs, net, rr)

    if side == "SHORT" and snapshot.venue == "BINANCE_TH_SPOT":
        return preview("MARKET_BLOCK", "Spot ไม่สามารถเปิด Short ได้", None)

    raw = Decimal(str(price)) + (price_move_usdt if side == "LONG" else
                                 -price_move_usdt)
    if raw <= 0:
        return preview("DISTANCE_BLOCK", f"{plan_label} ทำให้ราคาฝั่ง SHORT ต่ำกว่าศูนย์", None)
    target = _tick_price(float(raw), snapshot.instrument.tick_price,
                         ROUND_UP if side == "LONG" else ROUND_DOWN)
    if not math.isfinite(target) or target <= 0:
        return preview("DISTANCE_BLOCK", "ไม่สามารถปัดราคา TP ตาม Tick ของตลาดนี้ได้", None)
    move = ((target - price) if side == "LONG" else (price - target)) / price
    if not math.isfinite(move) or move <= 0:
        return preview("DISTANCE_BLOCK", "TP ไม่ได้ขยับไปในทิศทางทำกำไร", target)
    move_pct = move * 100
    if move_pct > MAX_PRICE_MOVE_PCT:
        return preview("DISTANCE_BLOCK",
                       f"{plan_label} คิดเป็น {move_pct:,.1f}% ของราคาเหรียญ "
                       f"สูงกว่าเพดานจำลอง {MAX_PRICE_MOVE_PCT:.1f}% · "
                       "ไม่เหมาะกับเหรียญราคาต่ำอย่าง PEPE", target, move_pct)

    if qty is None:
        quote_capital = settings.capital_usdt * settings.max_notional_multiple
        quantity = _floor_step(quote_capital / price, snapshot.instrument.step_qty)
    else:
        if not math.isfinite(qty) or qty <= 0:
            raise ValueError("invalid approved quantity")
        quantity = _floor_step(qty, snapshot.instrument.step_qty)
    notional = float(quantity) * price
    if (quantity < snapshot.instrument.min_qty or
            Decimal(str(notional)) < snapshot.instrument.min_notional):
        return preview("SIZE_BLOCK", "ขนาดไม้จำลองต่ำกว่า Min Qty / Min Notional ของตลาด",
                       target, move_pct, notional=notional)

    fee_pct = (settings.spot_fee_each_side_pct if snapshot.venue == "BINANCE_TH_SPOT"
               else max(settings.futures_fee_each_side_pct,
                        snapshot.instrument.taker_fee_pct or 0.0))
    # Same conservative cost convention as the existing scalp engine:
    # both-side fees, both-side slippage and current spread. Does not include
    # future funding, actual market movement or liquidation.
    cost_fraction = (2 * (fee_pct + settings.slippage_each_side_pct) / 100
                     + snapshot.spread_bps / 10_000)
    gross = notional * move
    cost = notional * cost_fraction
    net = gross - cost
    if net <= 0:
        return preview("COST_BLOCK", f"{plan_label} ไม่เหลือกำไรหลัง Fee / Spread / Slippage ประเมิน",
                       target, move_pct, notional=notional, gross=gross,
                       costs=cost, net=net)

    net_rr = None
    if signal_ready:
        if stop is None or not math.isfinite(stop) or stop <= 0:
            return preview("RISK_BLOCK", "สัญญาณยังไม่มี Stop Loss ที่ตรวจสอบได้",
                           target, move_pct, notional=notional, gross=gross,
                           costs=cost, net=net)
        stop_fraction = ((price - stop) if side == "LONG" else (stop - price)) / price
        if stop_fraction <= 0:
            return preview("RISK_BLOCK", "Stop Loss อยู่ผิดฝั่งราคาเข้า",
                           target, move_pct, notional=notional, gross=gross,
                           costs=cost, net=net)
        net_rr = (move - cost_fraction) / (stop_fraction + cost_fraction)
        if net_rr < settings.min_net_rr:
            return preview("RR_BLOCK",
                           f"Net R:R {net_rr:.2f}:1 ต่ำกว่าเกณฑ์ {settings.min_net_rr:.2f}:1",
                           target, move_pct, notional=notional, gross=gross,
                           costs=cost, net=net, rr=net_rr)
        return preview("ALTERNATIVE_READY", f"{plan_label} ผ่านต้นทุนและ R:R จำลอง",
                       target, move_pct, notional=notional, gross=gross,
                       costs=cost, net=net, rr=net_rr)
    return preview("WATCH_ONLY", "เป็นตัวอย่างจาก Bid/Ask ยังไม่มีสัญญาณเข้า",
                   target, move_pct, notional=notional, gross=gross,
                   costs=cost, net=net, rr=net_rr)


def pepe_point_unit(entry: float) -> Decimal:
    """Human 'point' at the third significant decimal of PEPE quote price.

    This is deliberately *not* an exchange tick. For example:
      0.0000488 -> 1 point = 0.0000001
      0.00000488 -> 1 point = 0.00000001
    Both give +10 points ~2% gross. The UI must display the unit explicitly.
    """
    if not math.isfinite(entry) or entry <= 0:
        raise ValueError("invalid PEPE reference price")
    return Decimal(1).scaleb(Decimal(str(entry)).adjusted() - 2)


def pepe_daily_ten_preview(snapshot: MarketSnapshot, settings: ScalpSettings, side: str,
                           *, entry: float | None = None, stop: float | None = None,
                           qty: float | None = None,
                           signal_ready: bool = False) -> FixedTPPreview:
    """One-trade daily target, +10 human points; never implies guaranteed fill."""
    if snapshot.symbol != "PEPEUSDT":
        raise ValueError("daily 10-point mode is currently PEPEUSDT only")
    reference = float(entry if entry is not None else
                      snapshot.ask if side == "LONG" else snapshot.bid)
    point = pepe_point_unit(reference)
    return fixed_tp_preview(snapshot, settings, side, entry=entry, stop=stop,
                            qty=qty, signal_ready=signal_ready,
                            price_move_usdt=point * 10, plan_label="TP 10 จุดของ PEPE")
