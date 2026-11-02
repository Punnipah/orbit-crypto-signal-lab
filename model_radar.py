"""Read-only reference-model radar, inspired by public trading research.

Two independent, closed-candle observation models. This module does NOT
issue READY, change MTF/Scalp risk gates, or make exchange requests/orders.
The displayed theoretical plan is never a validated executable signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

import pandas as pd

from scalp_engine import ScalpSettings, _adx, _atr, _ema
from scalp_marketdata import MarketSnapshot


@dataclass(frozen=True)
class ModelView:
    model: str
    state: str
    side: str
    reason: str
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    net_rr: float | None = None


def _candidate(model: str, snap: MarketSnapshot, cfg: ScalpSettings,
               side: str, stop: float, target: float, reason: str) -> ModelView:
    entry = snap.ask if side == "LONG" else snap.bid
    if not all(math.isfinite(x) and x > 0 for x in (entry, stop, target)):
        return ModelView(model, "DATA_BLOCK", side, "ข้อมูลราคาหรือระดับไม่สมเหตุผล")
    if not ((stop < entry < target) if side == "LONG" else (target < entry < stop)):
        return ModelView(model, "COST_BLOCK", side, "เป้าหมายไม่อยู่ฝั่งกำไร")
    risk = abs(entry-stop)/entry
    if not .003 <= risk <= .025:
        return ModelView(model, "COST_BLOCK", side, f"Stop ห่าง {risk*100:.2f}% นอกกรอบเดิม 0.3–2.5%")
    fee = (max(cfg.spot_fee_each_side_pct, snap.instrument.taker_fee_pct or 0)
           if snap.venue == "BINANCE_TH_SPOT"
           else max(cfg.futures_fee_each_side_pct, snap.instrument.taker_fee_pct or 0))
    cost = 2*(fee + cfg.slippage_each_side_pct)/100 + snap.spread_bps/10_000
    net_rr = (abs(target-entry)/entry-cost)/(risk+cost)
    if net_rr < cfg.min_net_rr:
        return ModelView(model, "COST_BLOCK", side,
                         f"Net R:R {net_rr:.2f} ต่ำกว่า {cfg.min_net_rr:.2f} · {reason}",
                         entry, stop, target, net_rr)
    if snap.venue == "BITGET_USDT_FUTURES" and not snap.flow_reconciled:
        return ModelView(model, "FLOW_BLOCK", side,
                         "พบรูปแบบ แต่ Public Buy/Sell Flow ยังตรวจครบแท่งไม่ได้ · ไม่มี READY",
                         entry, stop, target, net_rr)
    return ModelView(model, "MODEL_WATCH", side,
                     f"รูปแบบ+Net R:R ผ่านเบื้องต้น · {reason} · ไม่ใช่ READY",
                     entry, stop, target, net_rr)


def evaluate_reference_models(snap: MarketSnapshot, cfg: ScalpSettings,
                              *, now: datetime | None = None) -> tuple[ModelView, ModelView]:
    """Evaluate BB mean reversion and EMA pullback only on supplied closed candles.

    Does not infer Futures from Spot; avoids any external data fallback.
    """
    names = ("BB20 Mean Reversion", "EMA9/21 Pullback")
    stamp = now or snap.checked_at
    if (stamp.tzinfo is None or snap.checked_at.tzinfo is None or
            not 0 <= (stamp-snap.checked_at).total_seconds() <= 60 or
            snap.venue not in {"BINANCE_TH_SPOT", "BINANCE_GLOBAL_USDM", "BITGET_USDT_FUTURES"}):
        return tuple(ModelView(name, "DATA_BLOCK", "NONE", "ข้อมูลเวลา/ตลาดไม่พร้อม") for name in names)
    five, fifteen = snap.frames.get("5m"), snap.frames.get("15m")
    if five is None or fifteen is None or len(five) < 55 or len(fifteen) < 55:
        return tuple(ModelView(name, "DATA_BLOCK", "NONE", "แท่งปิด 5m/15m ไม่ครบ") for name in names)
    atr = _atr(five)
    close = float(five.close.iloc[-1])
    if not math.isfinite(atr) or atr <= 0 or close <= 0 or snap.spread_bps < 0:
        return tuple(ModelView(name, "DATA_BLOCK", "NONE", "ATR/Spread ไม่พร้อม") for name in names)

    # Model 1: 5m closes back inside a 20-bar Bollinger envelope after a
    # prior closed 5m outside; use previous bands for non-repainting tests.
    source = five.close.astype(float)
    mean = source.rolling(20).mean().shift(1)
    deviation = source.rolling(20).std(ddof=0).shift(1)
    lower, upper = mean-2*deviation, mean+2*deviation
    trend_strength = _adx(fifteen)
    last, prev = len(five)-1, len(five)-2
    if not math.isfinite(trend_strength) or trend_strength > cfg.range_max_adx:
        bb = ModelView(names[0], "NO_PATTERN", "NONE", "15m ADX ไม่ใช่ตลาด Sideways · ไม่สวนเทรนด์")
    elif source.iloc[prev] < lower.iloc[prev] and source.iloc[last] >= lower.iloc[last]:
        stop = min(float(five.low.tail(10).min()), snap.ask-1.2*atr)
        bb = _candidate(names[0], snap, cfg, "LONG", stop, float(mean.iloc[last]),
                        "BB กลับขึ้นในกรอบจากด้านล่าง")
    elif (snap.venue != "BINANCE_TH_SPOT" and
          source.iloc[prev] > upper.iloc[prev] and source.iloc[last] <= upper.iloc[last]):
        stop = max(float(five.high.tail(10).max()), snap.bid+1.2*atr)
        bb = _candidate(names[0], snap, cfg, "SHORT", stop, float(mean.iloc[last]),
                        "BB กลับลงในกรอบจากด้านบน")
    else:
        bb = ModelView(names[0], "NO_PATTERN", "NONE", "ยังไม่มีแท่ง 5m ปิดกลับเข้ากรอบ BB20")

    # Model 2: 15m EMA9/21 trend + 5m pullback that closes back across
    # the current 5m EMA9. Uses no future candles and no cross-venue prices.
    fast, slow = _ema(fifteen.close.astype(float), 9), _ema(fifteen.close.astype(float), 21)
    ema5 = _ema(source, 9)
    up = (fast.iloc[-1] > slow.iloc[-1] and
          fifteen.close.iloc[-1] > slow.iloc[-1] and slow.iloc[-1] > slow.iloc[-4])
    down = (fast.iloc[-1] < slow.iloc[-1] and
            fifteen.close.iloc[-1] < slow.iloc[-1] and slow.iloc[-1] < slow.iloc[-4])
    crossed_up = (float(five.low.iloc[-1]) <= float(ema5.iloc[-1]) and
                  source.iloc[-1] > float(ema5.iloc[-1]) and
                  source.iloc[-1] > float(five.open.iloc[-1]))
    crossed_down = (float(five.high.iloc[-1]) >= float(ema5.iloc[-1]) and
                    source.iloc[-1] < float(ema5.iloc[-1]) and
                    source.iloc[-1] < float(five.open.iloc[-1]))
    if up and crossed_up:
        stop = min(float(five.low.tail(10).min()), snap.ask-1.2*atr)
        target = float(five.high.iloc[-25:-1].max())
        ema = _candidate(names[1], snap, cfg, "LONG", stop, target,
                         "15m แนวโน้มขึ้น + 5m ยืนเหนือ EMA9")
    elif down and crossed_down and snap.venue != "BINANCE_TH_SPOT":
        stop = max(float(five.high.tail(10).max()), snap.bid+1.2*atr)
        target = float(five.low.iloc[-25:-1].min())
        ema = _candidate(names[1], snap, cfg, "SHORT", stop, target,
                         "15m แนวโน้มลง + 5m กลับใต้ EMA9")
    elif down and snap.venue == "BINANCE_TH_SPOT":
        ema = ModelView(names[1], "EXIT_WATCH", "SELL",
                        "Spot แนวโน้มลง · ห้ามแปลงเป็น Futures SHORT")
    else:
        ema = ModelView(names[1], "NO_PATTERN", "NONE", "ยังไม่มี 15m Trend + 5m EMA Pullback ที่ปิดยืนยัน")
    return bb, ema
