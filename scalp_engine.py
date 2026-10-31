"""Orbit v5.6 conservative scalp candidate engine; no private APIs or orders.

15m trend + closed 5m breakout + closed 1m confirmation. READY means a
time-limited research candidate, not a guaranteed fill or profitable trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from scalp_marketdata import MarketSnapshot


@dataclass(frozen=True)
class ScalpSettings:
    spot_symbols: tuple[str, ...]
    futures_symbols: tuple[str, ...]
    bitget_futures_symbols: tuple[str, ...] = ()
    capital_usdt: float = 80.0
    risk_per_trade_pct: float = 0.25
    daily_risk_budget_pct: float = 1.0
    max_notional_multiple: float = 1.0
    min_net_rr: float = 1.5
    spot_fee_each_side_pct: float = 0.10
    futures_fee_each_side_pct: float = 0.05
    slippage_each_side_pct: float = 0.05
    max_spread_bps: float = 12.0
    min_depth_to_notional_ratio: float = 5.0
    volume_multiplier: float = 1.20
    min_taker_buy_share_long: float = 0.53
    max_taker_buy_share_short: float = 0.47
    setup_lookback_5m: int = 10
    setup_expiry_minutes: int = 10
    ready_expiry_seconds: int = 180
    max_ready_alerts_per_day: int = 4
    paper_only: bool = True
    enable_range_scalp: bool = True
    range_max_adx: float = 23.0
    range_min_width_pct: float = 0.6
    range_max_width_pct: float = 5.0


@dataclass(frozen=True)
class ScalpObservation:
    venue: str
    symbol: str
    state: str
    reason: str
    checked_at: datetime
    side: str = "NONE"
    setup_id: str = ""
    entry: float | None = None
    stop: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    qty: float | None = None
    notional_usdt: float | None = None
    risk_usdt: float | None = None
    net_rr: float | None = None
    spread_bps: float | None = None
    last_closed_1m: datetime | None = None
    expires_at: datetime | None = None
    setup_expires_at: datetime | None = None
    strategy: str = "TREND_BREAKOUT"
    market_regime: str = "UNCONFIRMED"


def read_scalp_settings(path: Path | str) -> ScalpSettings:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    optional = {"bitget_futures_symbols", "enable_range_scalp", "range_max_adx",
                "range_min_width_pct", "range_max_width_pct"}
    fields = set(ScalpSettings.__dataclass_fields__)
    if (not isinstance(payload, dict) or set(payload) - fields
            or not fields - optional <= set(payload)):
        raise ValueError("Scalp config ต้องมีฟิลด์ตรงตาม v5.6 ครบทุกตัว")
    for k in ("spot_symbols", "futures_symbols", "bitget_futures_symbols"):
        if k not in payload:
            continue
        vals = payload[k]
        min_len = 0 if k == "bitget_futures_symbols" else 1
        if (not isinstance(vals, list) or not min_len <= len(vals) <= 12 or len(set(vals)) != len(vals)
                or any(not isinstance(v, str) or not v.isupper() or not v.endswith("USDT")
                       or len(v) > 22 for v in vals)):
            raise ValueError(f"{k} ต้องเป็นคู่ USDT ไม่ซ้ำ")
        payload[k] = tuple(vals)
    obj = ScalpSettings(**payload)
    checks = {
        "capital_usdt": (5, 99.99), "risk_per_trade_pct": (0.1, 0.5),
        "daily_risk_budget_pct": (0.25, 2.0), "max_notional_multiple": (0.1, 1.0),
        "min_net_rr": (1.5, 3.0), "spot_fee_each_side_pct": (0.08, 0.5),
        "futures_fee_each_side_pct": (0.03, 0.5), "slippage_each_side_pct": (0.01, 0.5),
        "max_spread_bps": (1.0, 30.0), "min_depth_to_notional_ratio": (1.0, 50.0),
        "volume_multiplier": (1.0, 3.0), "min_taker_buy_share_long": (0.5, 0.75),
        "max_taker_buy_share_short": (0.25, 0.5),
        "range_max_adx": (15.0, 27.0), "range_min_width_pct": (0.3, 2.0),
        "range_max_width_pct": (2.0, 8.0),
    }
    for field, (lo, hi) in checks.items():
        val = getattr(obj, field)
        if type(val) not in (float, int) or not math.isfinite(val) or not lo <= val <= hi:
            raise ValueError(f"Scalp config {field} ต้องอยู่ในช่วง {lo}–{hi}")
    integers = {"setup_lookback_5m": (8, 20), "setup_expiry_minutes": (5, 15),
                "ready_expiry_seconds": (60, 240), "max_ready_alerts_per_day": (1, 8)}
    for field, (lo, hi) in integers.items():
        val = getattr(obj, field)
        if type(val) is not int or not lo <= val <= hi:
            raise ValueError(f"Scalp config {field} ต้องเป็นจำนวนเต็ม {lo}–{hi}")
    if (type(obj.enable_range_scalp) is not bool or
            obj.range_min_width_pct >= obj.range_max_width_pct or
            obj.paper_only is not True or obj.daily_risk_budget_pct < obj.risk_per_trade_pct
            or obj.max_ready_alerts_per_day * obj.risk_per_trade_pct > obj.daily_risk_budget_pct):
        raise ValueError("ระบบต้องเป็น PAPER ONLY และผลรวมความเสี่ยงแจ้งเตือนต้องไม่เกินรายวัน")
    return obj


def unavailable(venue: str, symbol: str, reason: str, now: datetime) -> ScalpObservation:
    return ScalpObservation(venue, symbol, "DATA_UNAVAILABLE", reason[:180], now)


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _atr(frame: pd.DataFrame) -> float:
    prior = frame.close.shift(1)
    true_range = pd.concat([frame.high - frame.low, (frame.high - prior).abs(),
                            (frame.low - prior).abs()], axis=1).max(axis=1)
    return float(true_range.tail(14).mean())


def _setup_5m(frame: pd.DataFrame, side: str, settings: ScalpSettings,
              now: datetime) -> tuple[int, float, float] | None:
    n = settings.setup_lookback_5m
    # Previous closed candles (not current), and the most recent 5m candle
    # within the configured setup lifetime. Latest wins.
    for pos in range(len(frame) - 1, max(n + 20, len(frame) - 4), -1):
        row = frame.iloc[pos]
        close_at = int(row.open_ms) + 300_000
        age_min = (now.timestamp() * 1000 - close_at) / 60_000
        if age_min < 0 or age_min > settings.setup_expiry_minutes:
            continue
        prev = frame.iloc[pos - n:pos]
        prior_vol = frame.volume.iloc[pos - 20:pos].mean()
        if not math.isfinite(prior_vol) or prior_vol <= 0 or row.volume < prior_vol * 1.10:
            continue
        if side == "LONG" and row.close > max(prev.high) and row.close > row.open:
            return int(row.open_ms), float(row.close), float(row.low)
        if side == "SHORT" and row.close < min(prev.low) and row.close < row.open:
            return int(row.open_ms), float(row.close), float(row.high)
    return None


def _one_minute_confirmation(frame: pd.DataFrame, side: str, settings: ScalpSettings,
                             now: datetime, setup_open_ms: int) -> datetime | None:
    ema = _ema(frame.close, 9)
    # Closed 1m trigger after the 5m breakout closed; never look at an open
    # 1m candle. A 5-minute job might miss minute-level opportunities by design.
    prior_vol = frame.volume.rolling(20).mean().shift(1)
    for pos in range(len(frame) - 1, max(25, len(frame) - 4), -1):
        r = frame.iloc[pos]
        closed_ms = int(r.open_ms) + 60_000
        if (closed_ms <= setup_open_ms + 300_000 or
                now.timestamp() * 1000 - closed_ms > settings.ready_expiry_seconds * 1000):
            continue
        if r.volume <= 0 or r.volume < settings.volume_multiplier * float(prior_vol.iloc[pos]):
            continue
        taker_ratio = float(r.taker_buy / r.volume)
        if side == "LONG" and (r.close > r.open and r.close > float(ema.iloc[pos])
                               and taker_ratio >= settings.min_taker_buy_share_long):
            return datetime.fromtimestamp(closed_ms / 1000, timezone.utc)
        if side == "SHORT" and (r.close < r.open and r.close < float(ema.iloc[pos])
                                and taker_ratio <= settings.max_taker_buy_share_short):
            return datetime.fromtimestamp(closed_ms / 1000, timezone.utc)
    return None


def _floor_step(qty: float, step: Decimal) -> Decimal:
    value = Decimal(str(qty))
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _tick_price(value: float, tick: Decimal, rounding: str) -> float:
    number = Decimal(str(value))
    return float((number / tick).to_integral_value(rounding=rounding) * tick)


def _adx(frame: pd.DataFrame, period: int = 14) -> float:
    """Wilder ADX on fully closed 5m candles; NaN means unknown, not sideways."""
    up, down = frame.high.diff(), -frame.low.diff()
    plus = up.where((up > down) & (up > 0), 0.0)
    minus = down.where((down > up) & (down > 0), 0.0)
    prev = frame.close.shift(1)
    tr = pd.concat((frame.high - frame.low, (frame.high - prev).abs(),
                    (frame.low - prev).abs()), axis=1).max(axis=1)
    smoothed_tr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus.ewm(alpha=1 / period, adjust=False).mean() / smoothed_tr
    minus_di = 100 * minus.ewm(alpha=1 / period, adjust=False).mean() / smoothed_tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
    return float(dx.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


def _range_candidate(snapshot: MarketSnapshot, settings: ScalpSettings, now: datetime,
                     atr: float, atr_pct: float, full_spread_limit: float) -> ScalpObservation | None:
    """Independent bounded range-reversal setup, never a blind limit-order suggestion.

    Require low ADX, material range vs costs, edge retest on closed candles,
    and a recent *closed* 1m reversal with auditable taker-volume confirmation.
    """
    if not settings.enable_range_scalp:
        return None
    five, one = snapshot.frames["5m"], snapshot.frames["1m"]
    if len(five) < 65 or len(one) < 30:
        return None
    adx = _adx(five)
    if not math.isfinite(adx) or adx > settings.range_max_adx:
        return None
    # Exclude the latest bar when deriving the boundaries to avoid moving levels.
    previous = five.iloc[-31:-1]
    bottom, top = float(previous.low.min()), float(previous.high.max())
    mid = (bottom + top) / 2
    width_pct = (top - bottom) / mid * 100 if mid > 0 else 0
    if not settings.range_min_width_pct <= width_pct <= settings.range_max_width_pct:
        return None
    current = float(one.close.iloc[-1])
    edge_width = (top - bottom) * 0.22
    if current < bottom - edge_width * .25 or current > top + edge_width * .25:
        return None  # broken range, require reclassification on next scans
    long_edge = current <= bottom + edge_width
    short_edge = current >= top - edge_width
    if not long_edge and not short_edge:
        return ScalpObservation(snapshot.venue, snapshot.symbol, "WAIT",
                                f"SIDEWAYS · ADX {adx:.1f}; ราคาอยู่กลางกรอบ {bottom:.10g}–{top:.10g}",
                                now, strategy="RANGE_REVERSAL", market_regime="SIDEWAYS")
    side = "LONG" if long_edge else "SHORT"
    if snapshot.venue == "BINANCE_TH_SPOT" and side == "SHORT":
        return ScalpObservation(snapshot.venue, snapshot.symbol, "EXIT_WATCH",
                                "SIDEWAYS · ใกล้แนวต้าน; Spot ขายได้เฉพาะเหรียญที่ถือ ไม่เปิด Short",
                                now, side="SELL", strategy="RANGE_REVERSAL", market_regime="SIDEWAYS")
    # A closed 5m candle must have actually visited the edge in the last 10m.
    edge_touched = any((float(r.low) <= bottom + edge_width if side == "LONG"
                        else float(r.high) >= top - edge_width)
                       for _, r in five.tail(2).iterrows())
    if not edge_touched:
        return ScalpObservation(snapshot.venue, snapshot.symbol, "WAIT",
                                "SIDEWAYS · ยังไม่มีแท่ง 5m ทดสอบขอบกรอบล่าสุด", now,
                                side=side, strategy="RANGE_REVERSAL", market_regime="SIDEWAYS")
    if snapshot.spread_bps > full_spread_limit or not 0.06 <= atr_pct <= 3.0:
        return ScalpObservation(snapshot.venue, snapshot.symbol, "RISK_BLOCK",
                                "SIDEWAYS · Spread หรือ ATR ไม่ผ่านเกณฑ์", now,
                                side=side, strategy="RANGE_REVERSAL", market_regime="SIDEWAYS")
    entry = snapshot.ask if side == "LONG" else snapshot.bid
    fee = (settings.spot_fee_each_side_pct if snapshot.venue == "BINANCE_TH_SPOT"
           else max(settings.futures_fee_each_side_pct, snapshot.instrument.taker_fee_pct or 0))
    cost = 2 * (fee + settings.slippage_each_side_pct) / 100 + snapshot.spread_bps / 10_000
    # Beyond the range edge, with a volatility cushion, tick rounded outward.
    stop_raw = (bottom - .20 * atr) if side == "LONG" else (top + .20 * atr)
    stop = _tick_price(stop_raw, snapshot.instrument.tick_price,
                       ROUND_DOWN if side == "LONG" else ROUND_UP)
    risk_fraction = abs(entry - stop) / entry
    if not (stop < entry if side == "LONG" else stop > entry) or not .003 <= risk_fraction <= .025:
        return ScalpObservation(snapshot.venue, snapshot.symbol, "RISK_BLOCK",
                                "SIDEWAYS · Stop นอกช่วงความเสี่ยง 0.3–2.5%", now,
                                side=side, strategy="RANGE_REVERSAL", market_regime="SIDEWAYS")
    # TP2 strictly inside opposite boundary. Reject if costs erase net reward.
    target_raw = (top - .15 * atr) if side == "LONG" else (bottom + .15 * atr)
    tp2 = _tick_price(target_raw, snapshot.instrument.tick_price,
                      ROUND_DOWN if side == "LONG" else ROUND_UP)
    gain = (tp2 - entry) / entry if side == "LONG" else (entry - tp2) / entry
    net_rr = (gain - cost) / (risk_fraction + cost)
    if gain <= 0 or net_rr < settings.min_net_rr:
        return ScalpObservation(snapshot.venue, snapshot.symbol, "RISK_BLOCK",
                                f"SIDEWAYS · โอกาสถึงฝั่งตรงข้ามไม่คุ้มต้นทุน (Net R:R {net_rr:.2f})", now,
                                side=side, strategy="RANGE_REVERSAL", market_regime="SIDEWAYS")
    tp1 = _tick_price(entry + (tp2 - entry) * .55, snapshot.instrument.tick_price,
                      ROUND_DOWN if side == "LONG" else ROUND_UP)
    qty = _floor_step(min(settings.capital_usdt * settings.risk_per_trade_pct / 100 /
                          (entry * (risk_fraction + cost)),
                          settings.capital_usdt * settings.max_notional_multiple / entry),
                      snapshot.instrument.step_qty)
    notional = float(qty) * entry
    if (qty < snapshot.instrument.min_qty or Decimal(str(notional)) < snapshot.instrument.min_notional
            or min(snapshot.bid_depth_usdt, snapshot.ask_depth_usdt) <
            notional * settings.min_depth_to_notional_ratio):
        return ScalpObservation(snapshot.venue, snapshot.symbol, "RISK_BLOCK",
                                "SIDEWAYS · จำนวนขั้นต่ำหรือ Depth ไม่เพียงพอ", now,
                                side=side, strategy="RANGE_REVERSAL", market_regime="SIDEWAYS")
    # The newest closed 1m candle must reverse at the edge, with complete
    # taker-buy evidence. Bitget incomplete public fills => WATCH, never READY.
    row = one.iloc[-1]
    age = (now.timestamp() * 1000 - (int(row.open_ms) + 60_000)) / 1000
    prior_volume = float(one.volume.iloc[-21:-1].mean())
    ratio = float(row.taker_buy / row.volume) if row.volume > 0 else float("nan")
    confirmed = (0 <= age <= settings.ready_expiry_seconds and
                 float(row.volume) >= prior_volume * settings.volume_multiplier and
                 ((side == "LONG" and row.close > row.open and
                   ratio >= settings.min_taker_buy_share_long) or
                  (side == "SHORT" and row.close < row.open and
                   ratio <= settings.max_taker_buy_share_short)))
    setup_open = int(five.open_ms.iloc[-1])
    setup_id = hashlib.sha256(f"{snapshot.venue}:{snapshot.symbol}:RANGE:{side}:{setup_open}".encode()).hexdigest()[:24]
    deadline = datetime.fromtimestamp((setup_open + 300_000) / 1000, timezone.utc) + timedelta(
        minutes=settings.setup_expiry_minutes)
    confirmed_at = datetime.fromtimestamp((int(row.open_ms) + 60_000) / 1000, timezone.utc) if confirmed else None
    return ScalpObservation(snapshot.venue, snapshot.symbol, "READY" if confirmed else "WATCH",
                            f"SIDEWAYS · ADX {adx:.1f} · {'1m กลับตัวยืนยัน' if confirmed else 'รอแท่ง 1m กลับตัวพร้อม Volume/Flow'}; "
                            f"กรอบ {bottom:.10g}–{top:.10g}", now, side=side, setup_id=setup_id,
                            entry=entry, stop=stop, tp1=tp1, tp2=tp2, qty=float(qty),
                            notional_usdt=notional, risk_usdt=notional * (risk_fraction + cost),
                            net_rr=net_rr, spread_bps=snapshot.spread_bps,
                            last_closed_1m=confirmed_at,
                            expires_at=confirmed_at + timedelta(seconds=settings.ready_expiry_seconds) if confirmed_at else None,
                            setup_expires_at=deadline, strategy="RANGE_REVERSAL", market_regime="SIDEWAYS")


def evaluate_scalp(snapshot: MarketSnapshot, settings: ScalpSettings,
                   *, now: datetime | None = None) -> ScalpObservation:
    now = now or snapshot.checked_at
    if now.tzinfo is None or snapshot.checked_at.tzinfo is None:
        raise ValueError("Time zone not set")
    base = (snapshot.venue, snapshot.symbol)

    def status(name: str, reason: str, **kwargs) -> ScalpObservation:
        return ScalpObservation(*base, name, reason, now, spread_bps=snapshot.spread_bps, **kwargs)

    if not 0 <= (now - snapshot.checked_at).total_seconds() <= 60:
        return status("DATA_UNAVAILABLE", "Quote เก่ากว่า 60 วินาที")
    fifteen = snapshot.frames["15m"]
    five = snapshot.frames["5m"]
    one = snapshot.frames["1m"]
    atr = _atr(five)
    current = float(one.close.iloc[-1])
    atr_pct = atr / current * 100
    # On highly volatile coins a fixed 12-bps cap blocks the market all day.
    # Permit spread up to 25% of recent 5m ATR (absolute ceiling 25 bps),
    # while still counting the ACTUAL observed spread as a trading cost below.
    # This is a liquidity constraint, not an endorsement of profitable fills.
    adaptive_spread_bps = max(settings.max_spread_bps,
                              min(25.0, atr_pct * 100 * 0.25))
    # Range strategies are independent of trend-breakout requirements; retain
    # their own cost, depth, stop, volume and time-limited evidence gates.
    range_result = _range_candidate(snapshot, settings, now, atr, atr_pct,
                                    adaptive_spread_bps)
    if range_result is not None:
        return range_result
    if snapshot.spread_bps > adaptive_spread_bps:
        return status("RISK_BLOCK", f"Spread {snapshot.spread_bps:.1f} bps สูงเกิน"
                      f"เกณฑ์ตามความผันผวน {adaptive_spread_bps:.1f} bps")
    if not 0.10 <= atr_pct <= 3.0:
        return status("RISK_BLOCK", f"ATR 5m = {atr_pct:.2f}% ไม่เหมาะกับทุน Scalp")
    ema9, ema21 = _ema(fifteen.close, 9), _ema(fifteen.close, 21)
    trend_up = (fifteen.close.iloc[-1] > ema21.iloc[-1] and
                ema9.iloc[-1] > ema21.iloc[-1] and
                ema21.iloc[-1] > ema21.iloc[-4])
    trend_down = (fifteen.close.iloc[-1] < ema21.iloc[-1] and
                  ema9.iloc[-1] < ema21.iloc[-1] and
                  ema21.iloc[-1] < ema21.iloc[-4])
    if trend_up:
        side = "LONG"
    elif trend_down:
        side = "SHORT"
    else:
        return status("WAIT", "15m EMA9/21 ยังไม่ยืนยันทิศทาง")
    if snapshot.venue == "BINANCE_TH_SPOT" and side == "SHORT":
        return status("EXIT_WATCH", "Spot แนวโน้มลง: เฝ้าพิจารณาขายเหรียญที่ถือ; ห้ามเปิด Short", side="SELL")
    if (side == "LONG" and float(five.close.iloc[-1]) < float(_ema(five.close, 21).iloc[-1])) or (
            side == "SHORT" and float(five.close.iloc[-1]) > float(_ema(five.close, 21).iloc[-1])):
        return status("WAIT", "5m ไม่สอดคล้องกับ 15m", side=side)
    setup = _setup_5m(five, side, settings, now)
    if setup is None:
        return status("WAIT", "รอ 5m Breakout จากกรอบเดิมที่ปิดแท่งและ Volume ผ่าน", side=side)
    opened_ms, breakout_close, breakout_extreme = setup
    setup_expires = datetime.fromtimestamp((opened_ms + 300_000) / 1000, timezone.utc) + timedelta(
        minutes=settings.setup_expiry_minutes)
    setup_id = hashlib.sha256(f"{snapshot.venue}:{snapshot.symbol}:{side}:{opened_ms}".encode()).hexdigest()[:24]
    confirmation = _one_minute_confirmation(one, side, settings, now, opened_ms)
    entry = snapshot.ask if side == "LONG" else snapshot.bid
    # Bid/ask must still be within a small envelope around the confirmed 5m
    # breakout. No "chase price" after a large move.
    if abs(entry / breakout_close - 1) > min(0.006, max(0.002, atr / current * 0.65)):
        return status("RISK_BLOCK", "ราคาปัจจุบันไกลจากแท่ง Breakout มาก ไม่ไล่ราคา", side=side,
                      setup_id=setup_id)
    if (side == "LONG" and entry <= breakout_extreme) or (
            side == "SHORT" and entry >= breakout_extreme):
        return status("RISK_BLOCK", "ราคาหลุดโครงสร้างแท่ง 5m", side=side, setup_id=setup_id)
    stop_distance = max(entry * 0.0035, atr * 0.9)
    # Stop beyond 5m breakout candle extreme, with small volatility buffer.
    if side == "LONG":
        stop = min(entry - stop_distance, breakout_extreme - atr * 0.10)
    else:
        stop = max(entry + stop_distance, breakout_extreme + atr * 0.10)
    stop = _tick_price(stop, snapshot.instrument.tick_price,
                       ROUND_DOWN if side == "LONG" else ROUND_UP)
    if stop <= 0:
        return status("RISK_BLOCK", "Stop ต่ำกว่าศูนย์หลังปัดตาม Tick Size", side=side,
                      setup_id=setup_id)
    risk_fraction = abs(entry - stop) / entry
    if not 0.003 <= risk_fraction <= 0.025:
        return status("RISK_BLOCK", f"Stop ห่างราคา {risk_fraction*100:.2f}% นอกกรอบ 0.3–2.5%",
                      side=side, setup_id=setup_id)
    fee = (settings.spot_fee_each_side_pct if snapshot.venue == "BINANCE_TH_SPOT"
           else max(settings.futures_fee_each_side_pct, snapshot.instrument.taker_fee_pct or 0))
    # Price targets use the reference bid/ask, but add the observed spread as
    # a separate conservative round-trip budget for possible exit widening.
    full_cost = 2 * (fee + settings.slippage_each_side_pct) / 100 + snapshot.spread_bps / 10_000
    max_risk = settings.capital_usdt * settings.risk_per_trade_pct / 100
    qty_raw = min(max_risk / (entry * (risk_fraction + full_cost)),
                  settings.capital_usdt * settings.max_notional_multiple / entry)
    qty_dec = _floor_step(qty_raw, snapshot.instrument.step_qty)
    notional = float(qty_dec) * entry
    if (qty_dec < snapshot.instrument.min_qty or
            Decimal(str(notional)) < snapshot.instrument.min_notional):
        return status("RISK_BLOCK", "ทุน/ขนาด Position ต่ำกว่าขั้นต่ำ Binance TH/Global ของคู่เหรียญนี้",
                      side=side, setup_id=setup_id)
    if min(snapshot.bid_depth_usdt, snapshot.ask_depth_usdt) < (
            notional * settings.min_depth_to_notional_ratio):
        return status("RISK_BLOCK", "สภาพคล่อง 20 ระดับไม่พอสำหรับขนาด Position", side=side,
                      setup_id=setup_id)
    # Net RR includes both-side fees and execution slippage. TP2 is an
    # illustrative target; strategy reachability still requires backtesting.
    profit_fraction = max(risk_fraction * 2.2,
                          full_cost + settings.min_net_rr * (risk_fraction + full_cost) * 1.06)
    if profit_fraction > 0.055:
        return status("RISK_BLOCK", "เป้ากำไรสุทธิไกลเกิน 5.5% สำหรับ Scalp", side=side,
                      setup_id=setup_id)
    tp1_pct = full_cost + (risk_fraction + full_cost) * 0.8
    sign = 1 if side == "LONG" else -1
    tp1, tp2 = entry * (1 + sign * tp1_pct), entry * (1 + sign * profit_fraction)
    tp1 = _tick_price(tp1, snapshot.instrument.tick_price,
                      ROUND_UP if side == "LONG" else ROUND_DOWN)
    tp2 = _tick_price(tp2, snapshot.instrument.tick_price,
                      ROUND_UP if side == "LONG" else ROUND_DOWN)
    if tp2 <= 0:
        return status("RISK_BLOCK", "TP2 ไม่ถูกต้องหลังปัดตาม Tick Size", side=side,
                      setup_id=setup_id)
    net_rr = (abs(tp2 - entry) / entry - full_cost) / (risk_fraction + full_cost)
    if net_rr < settings.min_net_rr:
        return status("RISK_BLOCK", "Net R:R หลังค่าธรรมเนียม/Spread ไม่ถึงเกณฑ์", side=side,
                      setup_id=setup_id)
    expires = confirmation + timedelta(seconds=settings.ready_expiry_seconds) if confirmation else None
    if confirmation and expires and expires <= now:
        confirmation = None
        expires = None
    source_note = ("Public Fills Buy/Sell (ไม่ใช่ Taker ที่รับรอง)"
                   if snapshot.venue == "BITGET_USDT_FUTURES" else "Taker Flow")
    return status("READY" if confirmation else "WATCH",
                  f"ผ่าน 15m/5m และแท่ง 1m {source_note} ยืนยัน; ตรวจราคาอีกครั้ง" if confirmation
                  else f"พบกรอบ 5m; รอ 1m Volume + {source_note} ยืนยัน (ยังไม่ใช่จุดซื้อ)",
                  side=side, setup_id=setup_id, entry=entry, stop=stop, tp1=tp1, tp2=tp2,
                  qty=float(qty_dec), notional_usdt=notional,
                  risk_usdt=notional * (risk_fraction + full_cost), net_rr=net_rr,
                  last_closed_1m=confirmation, expires_at=expires, setup_expires_at=setup_expires)
