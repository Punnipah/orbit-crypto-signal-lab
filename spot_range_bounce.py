"""Independent, read-only Spot Range Bounce engine. Never modifies MTF BUY."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
import hashlib
import math
import pandas as pd

from scalp_engine import ScalpSettings, _adx, _atr, _floor_step, _tick_price
from scalp_marketdata import MarketSnapshot


@dataclass(frozen=True)
class RangeBounce:
    state: str
    reason: str
    venue: str
    symbol: str
    checked_at: datetime
    support: float | None = None
    support_zone_high: float | None = None
    resistance: float | None = None
    adx_1h: float | None = None
    entry: float | None = None
    stop: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    net_rr: float | None = None
    quantity: float | None = None
    risk_usdt: float | None = None
    setup_id: str = ""
    expires_at: datetime | None = None


def _closed_rejection(five: pd.DataFrame, support: float, edge: float,
                      now: datetime, cfg: ScalpSettings) -> tuple[int, float] | None:
    for i in range(len(five)-1, max(25, len(five)-3), -1):
        bar = five.iloc[i]
        closed = int(bar.open_ms) + 300_000
        age = (now.timestamp()*1000 - closed)/60_000
        baseline = float(five.volume.iloc[i-20:i].mean())
        if (0 <= age <= cfg.setup_expiry_minutes and baseline > 0 and
                float(bar.volume) >= baseline*1.10 and
                float(bar.low) <= edge and float(bar.close) >= support and
                float(bar.close) > max(float(bar.open), float(five.close.iloc[i-1]))):
            return int(bar.open_ms), float(bar.close)
    return None


def _closed_buy_flow(one: pd.DataFrame, setup_ms: int, now: datetime,
                     cfg: ScalpSettings) -> datetime | None:
    for i in range(len(one)-1, max(25, len(one)-4), -1):
        bar = one.iloc[i]
        closed = int(bar.open_ms) + 60_000
        age = now.timestamp()*1000 - closed
        baseline = float(one.volume.iloc[i-20:i].mean())
        ratio = float(bar.taker_buy/bar.volume) if bar.volume > 0 else float("nan")
        if (closed > setup_ms + 300_000 and
                0 <= age <= cfg.ready_expiry_seconds*1000 and
                baseline > 0 and bar.volume >= baseline*cfg.volume_multiplier and
                math.isfinite(ratio) and ratio >= cfg.min_taker_buy_share_long and
                bar.close > bar.open):
            return datetime.fromtimestamp(closed/1000, timezone.utc)
    return None


def evaluate_spot_range(snap: MarketSnapshot, cfg: ScalpSettings,
                        *, now: datetime | None = None) -> RangeBounce:
    if snap.venue != "BINANCE_TH_SPOT":
        raise ValueError("Range Bounce requires Binance TH Spot, never Futures")
    now = now or snap.checked_at
    if now.tzinfo is None or snap.checked_at.tzinfo is None:
        raise ValueError("timezone-aware snapshot required")
    identity = dict(venue=snap.venue, symbol=snap.symbol, checked_at=now)
    def decision(state: str, reason: str, **details) -> RangeBounce:
        return RangeBounce(state=state, reason=reason, **identity, **details)

    if not 0 <= (now - snap.checked_at).total_seconds() <= 60:
        return decision("DATA_UNAVAILABLE", "Quote เก่าหรือเวลาไม่ถูกต้อง")
    hour, fifteen, five, one = (snap.frames.get(k) for k in ("1h", "15m", "5m", "1m"))
    if any(f is None or len(f) < 55 for f in (hour, fifteen, five, one)):
        return decision("DATA_UNAVAILABLE", "แท่งปิด 1H/15M/5M/1M ไม่ครบ · ไม่เดาสัญญาณ")
    adx = _adx(hour)
    reference = hour.iloc[-13:-1]  # Exclude the latest closed hour: no shifting range.
    support, resistance = float(reference.low.min()), float(reference.high.max())
    width = (resistance-support)/((support+resistance)/2)*100 if support > 0 else float("nan")
    if not (math.isfinite(adx) and math.isfinite(width) and
            adx <= cfg.range_max_adx and
            cfg.range_min_width_pct <= width <= cfg.range_max_width_pct):
        return decision("NO_RANGE", "1H ยังไม่ผ่าน ADX/ความกว้างกรอบ Sideways",
                        adx_1h=adx if math.isfinite(adx) else None)
    edge = support + (resistance-support)*.22
    info = dict(support=support, support_zone_high=edge,
                resistance=resistance, adx_1h=adx)
    midpoint = (snap.bid+snap.ask)/2
    atr = _atr(five)
    if not math.isfinite(atr) or atr <= 0 or midpoint <= 0:
        return decision("DATA_UNAVAILABLE", "ATR/ราคาไม่ถูกต้อง", **info)
    if (float(hour.close.iloc[-1]) < support or
            (float(fifteen.close.iloc[-1]) < support and float(fifteen.close.iloc[-2]) < support) or
            (float(five.close.iloc[-1]) < support and float(five.close.iloc[-2]) < support) or
            midpoint < support - .20*atr):
        return decision("RANGE_BROKEN", "แท่งปิดหลุดแนวรับ · ไม่ใช้กรอบเก่าเข้าซื้อ", **info)
    if midpoint > resistance or midpoint > edge + min(.4*atr, .1*(resistance-support)):
        return decision("RANGE_DETECTED", "Sideways 1H แต่ราคายังไม่ใกล้แนวรับ", **info)
    if midpoint < support - .05*atr:
        return decision("REBOUND_WATCH", "ราคาอยู่ใต้แนวรับ · ต้องรอแท่งปิด reclaim", **info)
    setup = _closed_rejection(five, support, edge, now, cfg)
    if not setup:
        return decision("NEAR_SUPPORT", "ใกล้แนวรับ แต่แท่ง 5m ยังไม่ปิดกลับตัวพร้อม Volume", **info)
    opened, closed_price = setup
    setup_id = hashlib.sha256(f"{snap.venue}:{snap.symbol}:RANGE_BOUNCE:{opened}".encode()).hexdigest()[:24]
    confirmed = _closed_buy_flow(one, opened, now, cfg)
    if not confirmed:
        return decision("REBOUND_WATCH", "5m ทดสอบแนวรับแล้ว · รอแท่ง 1m Buy Flow ยืนยัน",
                        setup_id=setup_id, **info)
    entry = snap.ask
    if abs(entry/closed_price-1) > min(.006, max(.002, .65*atr/midpoint)):
        return decision("RISK_BLOCK", "ราคาวิ่งห่างจากแท่งยืนยัน · ไม่ไล่ซื้อ",
                        setup_id=setup_id, **info)
    atr_pct = atr/midpoint*100
    tick_bps = float(snap.instrument.tick_price)/midpoint*10_000
    spread_cap = max(cfg.max_spread_bps, min(25., atr_pct*25))
    if 0 < tick_bps <= 25:
        spread_cap = max(spread_cap, min(25., tick_bps*1.05))
    if snap.spread_bps > spread_cap or not .06 <= atr_pct <= 3.0:
        return decision("RISK_BLOCK", "Spread/ATR เกินเกณฑ์เดิม", setup_id=setup_id, **info)
    stop = _tick_price(support-.20*atr, snap.instrument.tick_price, ROUND_DOWN)
    if stop <= 0 or stop >= entry or not .003 <= (entry-stop)/entry <= .025:
        return decision("RISK_BLOCK", "Stop ไม่ผ่านกรอบความเสี่ยง 0.3–2.5%",
                        setup_id=setup_id, **info)
    tp1 = _tick_price((support+resistance)/2, snap.instrument.tick_price, ROUND_DOWN)
    tp2 = _tick_price(resistance-.15*atr, snap.instrument.tick_price, ROUND_DOWN)
    fees = max(cfg.spot_fee_each_side_pct, snap.instrument.taker_fee_pct or 0)
    cost = 2*(fees+cfg.slippage_each_side_pct)/100 + snap.spread_bps/10_000
    if not entry < tp1 < tp2:
        return decision("RISK_BLOCK", "TP1/TP2 ไม่มีระยะกำไรพอ", setup_id=setup_id, **info)
    risk_fraction = (entry-stop)/entry
    net_rr = ((tp1-entry)/entry-cost)/(risk_fraction+cost)
    if net_rr < cfg.min_net_rr:
        return decision("RISK_BLOCK", f"TP1 หลังต้นทุน Net R:R {net_rr:.2f} ต่ำกว่าเกณฑ์",
                        net_rr=net_rr, setup_id=setup_id, **info)
    qty = _floor_step(min(cfg.capital_usdt*cfg.risk_per_trade_pct/100 /
                          (entry*(risk_fraction+cost)),
                          cfg.capital_usdt*cfg.max_notional_multiple/entry),
                      snap.instrument.step_qty)
    notional = float(qty)*entry
    if (qty < snap.instrument.min_qty or
            Decimal(str(notional)) < snap.instrument.min_notional or
            min(snap.bid_depth_usdt, snap.ask_depth_usdt) <
            notional*cfg.min_depth_to_notional_ratio):
        return decision("RISK_BLOCK", "จำนวนขั้นต่ำ/Order Book Depth ไม่ผ่าน",
                        setup_id=setup_id, **info)
    expiry = confirmed + timedelta(seconds=cfg.ready_expiry_seconds)
    if expiry <= now:
        return decision("REBOUND_WATCH", "การยืนยัน 1m หมดอายุแล้ว",
                        setup_id=setup_id, **info)
    return decision("RANGE_READY", "5m Rejection + 1m Flow + Net R:R ผ่าน · PAPER ONLY",
                    entry=entry, stop=stop, tp1=tp1, tp2=tp2, net_rr=net_rr,
                    quantity=float(qty), risk_usdt=notional*(risk_fraction+cost),
                    setup_id=setup_id, expires_at=expiry, **info)
