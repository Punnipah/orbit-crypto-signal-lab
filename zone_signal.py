"""Per-zone scalp confirmation, independent of the global trend/breakout signal.

No private exchange calls, no orders. Every approved candidate requires closed
1m/5m candles, a recent reaction, venue-native liquidity and net risk checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_UP
import math

from scalp_engine import ScalpSettings, _adx, _atr, _ema, _floor_step, _tick_price
from scalp_marketdata import MarketSnapshot


@dataclass(frozen=True)
class ZoneDecision:
    state: str
    reason: str
    side: str
    entry: float | None = None
    stop: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    qty: float | None = None
    net_rr: float | None = None
    expires_at: datetime | None = None
    checks: tuple[tuple[str, bool, str], ...] = ()


def evaluate_zone(snapshot: MarketSnapshot, settings: ScalpSettings, zone: dict,
                  side: str, *, now: datetime | None = None) -> ZoneDecision:
    now = now or snapshot.checked_at
    if side not in ("LONG", "SHORT") or not settings.paper_only:
        raise ValueError("Invalid side or non-paper config")

    def result(state: str, reason: str, **kwargs) -> ZoneDecision:
        return ZoneDecision(state, reason, side, **kwargs)

    if now.tzinfo is None or snapshot.checked_at.tzinfo is None or not 0 <= (
            now - snapshot.checked_at).total_seconds() <= 60:
        return result("DATA_UNAVAILABLE", "Quote เก่าหรือเวลาข้อมูลไม่ถูกต้อง")
    if zone["state"] == "INVALIDATED":
        return result("INVALIDATED", "โครงสร้างแนวรับ/แนวต้านหลุดแล้ว ต้องคำนวณโซนใหม่")
    one, five, fifteen = (snapshot.frames[k] for k in ("1m", "5m", "15m"))
    if min(len(one), len(five), len(fifteen)) < 50:
        return result("DATA_UNAVAILABLE", "แท่งที่ปิดแล้วไม่เพียงพอ")
    quote = float(snapshot.ask if side == "LONG" else snapshot.bid)
    atr = _atr(five)
    follow_through = min(atr * .40, (zone["high"] - zone["low"]) * 1.20)
    # After a *real* recent touch, a confirmation candle may close just past
    # the zone boundary. It is still a small rebound, not chasing a breakout.
    rebound = (zone["state"] == "WATCH" and
               ((side == "LONG" and zone["high"] < quote <= zone["high"] + follow_through) or
                (side == "SHORT" and zone["low"] - follow_through <= quote < zone["low"])))
    if zone["state"] != "IN_ZONE" and not rebound:
        recent_touch = any(float(r.low) <= zone["high"] and
                           float(r.high) >= zone["low"]
                           for _, r in one.tail(3).iterrows())
        far_rebound = ((side == "LONG" and quote > zone["high"] + follow_through) or
                       (side == "SHORT" and quote < zone["low"] - follow_through))
        if recent_touch and far_rebound:
            return result("MISSED", "เด้งจากโซนไปไกลเกินระยะเข้าแล้ว · ไม่ไล่ราคา")
        return result("WAIT_PRICE", "ราคายังไม่แตะโซน · แสดงโซนไว้เฝ้าดู")

    latest = one.iloc[-1]
    last_ms = int(latest.open_ms) + 60_000
    age = (now.timestamp() * 1000 - last_ms) / 1000
    touched_1m = False
    for _, r in one.tail(3).iterrows():
        if float(r.low) <= zone["high"] and float(r.high) >= zone["low"]:
            touched_1m = True
    touched_5m = any(float(r.low) <= zone["high"] and float(r.high) >= zone["low"]
                      for _, r in five.tail(2).iterrows())
    # Each confirmation candidate must independently pass the volume, taker
    # share, recency and reaction checks; never combine passes from different
    # candles. Allow up to three consecutive CLOSED 1m bars after zone touch.
    verified = None
    for pos in range(len(one) - 1, len(one) - 4, -1):
        row = one.iloc[pos]
        row_ms = int(row.open_ms) + 60_000
        row_age = (now.timestamp() * 1000 - row_ms) / 1000
        touch_window = one.iloc[max(len(one) - 3, pos - 2):pos + 1]
        visited = any(float(r.low) <= zone["high"] and float(r.high) >= zone["low"]
                      for _, r in touch_window.iterrows())
        reversal = (float(row.close) > float(row.open) if side == "LONG" else
                    float(row.close) < float(row.open))
        base = float(one.volume.iloc[pos - 20:pos].mean())
        volume = bool(math.isfinite(base) and base > 0 and
                      float(row.volume) >= base * settings.volume_multiplier)
        share = float(row.taker_buy / row.volume) if row.volume > 0 else float("nan")
        flow = math.isfinite(share) and (share >= settings.min_taker_buy_share_long if
                                         side == "LONG" else share <= settings.max_taker_buy_share_short)
        if visited and reversal and volume and flow and 0 <= row_age <= settings.ready_expiry_seconds:
            verified = (row, row_ms, row_age, share)
            break
    if verified is not None:
        last_ms, age, taker = verified[1], verified[2], verified[3]
        reaction = True
        volume_ok = True
        flow_ok = True
    else:
        reaction = (float(latest.close) > float(latest.open) if side == "LONG" else
                    float(latest.close) < float(latest.open))
        base_volume = float(one.volume.iloc[-21:-1].mean())
        volume_ok = bool(base_volume > 0 and math.isfinite(base_volume) and
                         float(latest.volume) >= base_volume * settings.volume_multiplier)
        taker = float(latest.taker_buy / latest.volume) if latest.volume > 0 else float("nan")
        flow_ok = math.isfinite(taker) and (taker >= settings.min_taker_buy_share_long if
                                            side == "LONG" else taker <= settings.max_taker_buy_share_short)
    ema9, ema21 = _ema(fifteen.close, 9), _ema(fifteen.close, 21)
    bearish = (ema9.iloc[-1] < ema21.iloc[-1] and
               float(fifteen.close.iloc[-1]) < ema21.iloc[-1] and
               ema21.iloc[-1] < ema21.iloc[-4])
    bullish = (ema9.iloc[-1] > ema21.iloc[-1] and
               float(fifteen.close.iloc[-1]) > ema21.iloc[-1] and
               ema21.iloc[-1] > ema21.iloc[-4])
    adx = _adx(five)
    trend_ok = not ((side == "LONG" and bearish) or (side == "SHORT" and bullish)) or (
        math.isfinite(adx) and adx <= settings.range_max_adx)
    checks = (("15m บริบทแนวโน้ม", bool(trend_ok), "ไม่สวนแนวโน้มแรง หรือ 5m เป็นตลาด Range"),
              ("5m แตะโซน", bool(touched_5m), "มีแท่ง 5m ปิดแล้วสัมผัสโซนล่าสุด"),
              ("1m ปิดแท่งกลับตัว", bool(touched_1m and reaction and 0 <= age <= settings.ready_expiry_seconds),
               f"ยืนยันภายใน 3 แท่ง 1m · อายุแท่งยืนยัน {age:.0f} วินาที"),
              ("1m Volume", bool(volume_ok), f"ต้องผ่าน {settings.volume_multiplier:.2f}x"),
              ("1m Taker Flow", bool(flow_ok), f"Taker Buy {taker:.0%}" if math.isfinite(taker) else "ข้อมูล Flow ไม่ครบ"))
    if not trend_ok:
        return result("RISK_BLOCK", "สวนแนวโน้ม 15m ที่แรงเกินเกณฑ์ Range", checks=checks)
    if not all(ok for _, ok, _ in checks):
        return result("WAIT_CONFIRM", "ราคาเข้า/เด้งใกล้โซนแล้ว แต่ยังขาดเงื่อนไข 5m/1m หรือ Volume/Flow",
                      checks=checks)

    price = snapshot.ask if side == "LONG" else snapshot.bid
    atr_pct = atr / price * 100
    tick_bps = float(snapshot.instrument.tick_price) / price * 10_000
    spread_limit = max(settings.max_spread_bps, min(25.0, atr_pct * 25.0))
    if 0 < tick_bps <= 25:
        spread_limit = max(spread_limit, min(25.0, tick_bps * 1.05))
    if snapshot.spread_bps > spread_limit or not .06 <= atr_pct <= 3.0:
        return result("RISK_BLOCK", "Spread หรือ ATR สูง/ต่ำเกินเกณฑ์", checks=checks)
    if snapshot.venue == "BINANCE_TH_SPOT" and side == "SHORT":
        return result("RISK_BLOCK", "Spot ไม่เปิด Short", checks=checks)
    if snapshot.venue == "BITGET_USDT_FUTURES":
        # Public aggregated fills are not the same as exchange-certified
        # directional taker-volume candles; keep this as watch-only.
        return result("WAIT_CONFIRM", "Bitget ยังไม่มี Taker Flow ที่ยืนยันได้ครบสำหรับ Zone READY",
                      checks=checks)

    stop_raw = (zone["low"] - .25 * atr if side == "LONG" else zone["high"] + .25 * atr)
    stop = _tick_price(stop_raw, snapshot.instrument.tick_price,
                       ROUND_DOWN if side == "LONG" else ROUND_UP)
    risk = (price - stop) / price if side == "LONG" else (stop - price) / price
    if stop <= 0 or not .003 <= risk <= .025:
        return result("RISK_BLOCK", "Stop จากโครงสร้างโซนไม่อยู่ในกรอบ 0.3–2.5%", checks=checks)
    fee = (settings.spot_fee_each_side_pct if snapshot.venue == "BINANCE_TH_SPOT"
           else max(settings.futures_fee_each_side_pct, snapshot.instrument.taker_fee_pct or 0))
    cost = 2 * (fee + settings.slippage_each_side_pct) / 100 + snapshot.spread_bps / 10_000
    # Opposite structural boundary is the plausible target; never invent
    # a far-away TP to force a favorable ratio.
    history = five.iloc[-49:-1]
    opposite = (float(history.high.max()) - .15 * atr if side == "LONG" else
                float(history.low.min()) + .15 * atr)
    target = _tick_price(opposite, snapshot.instrument.tick_price,
                         ROUND_DOWN if side == "LONG" else ROUND_UP)
    gross_gain = (target - price) / price if side == "LONG" else (price - target) / price
    net_rr = (gross_gain - cost) / (risk + cost)
    if gross_gain <= 0 or net_rr < settings.min_net_rr or gross_gain > .055:
        return result("RISK_BLOCK", f"เป้าหมายถึงแนวฝั่งตรงข้ามไม่คุ้มต้นทุน (Net R:R {net_rr:.2f})",
                      checks=checks)
    tp1 = _tick_price(price + (target - price) * .55, snapshot.instrument.tick_price,
                      ROUND_DOWN if side == "LONG" else ROUND_UP)
    qty = _floor_step(min(settings.capital_usdt * settings.risk_per_trade_pct / 100 /
                          (price * (risk + cost)),
                          settings.capital_usdt * settings.max_notional_multiple / price),
                      snapshot.instrument.step_qty)
    notional = float(qty) * price
    if (qty < snapshot.instrument.min_qty or
            Decimal(str(notional)) < snapshot.instrument.min_notional or
            min(snapshot.bid_depth_usdt, snapshot.ask_depth_usdt) <
            notional * settings.min_depth_to_notional_ratio):
        return result("RISK_BLOCK", "ทุนขั้นต่ำหรือ Depth ไม่เพียงพอ", checks=checks)
    expiry = datetime.fromtimestamp(last_ms / 1000, now.tzinfo) + timedelta(
        seconds=settings.ready_expiry_seconds)
    if expiry <= now:
        return result("WAIT_CONFIRM", "แท่งยืนยันหมดอายุแล้ว", checks=checks)
    return result("ZONE_READY", "แท่งปิด 5m/1m ยืนยัน และต้นทุน/ความเสี่ยงผ่าน · Paper only",
                  entry=price, stop=stop, tp1=tp1, tp2=target,
                  qty=float(qty), net_rr=net_rr, expires_at=expiry, checks=checks)
