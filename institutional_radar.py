"""Orbit v5.9.6: transparent, read-only institutional-*style* playbooks.

These are public-market proxies, NOT proprietary institutional models or a
claim that identifiable whales executed a trade. In particular, a single L2
depth snapshot is NOT event-by-event order-flow imbalance (Cont et al.).

No private APIs, cross-venue fallbacks, orders, MTF overrides or new READY.
All observations use the venue's closed candles and already-fetched quotes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

import pandas as pd

from model_radar import _candidate
from scalp_engine import ScalpSettings, _atr
from scalp_marketdata import MarketSnapshot


@dataclass(frozen=True)
class MicrostructureEvidence:
    rolling_vwap: float | None
    five_min_volume_ratio: float | None
    recent_taker_buy_share: float | None
    bid_depth_share: float | None
    explanation: str


@dataclass(frozen=True)
class InstitutionalPlaybook:
    name: str
    state: str
    side: str
    reason: str
    reference_level: float | None = None
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    net_rr: float | None = None


@dataclass(frozen=True)
class InstitutionalRadar:
    evidence: MicrostructureEvidence
    playbooks: tuple[InstitutionalPlaybook, ...]


NAMES = ("Liquidity Sweep → Reclaim", "Breakout → Retest", "Rolling VWAP Reclaim")
VENUES = {"BINANCE_TH_SPOT", "BINANCE_GLOBAL_USDM", "BITGET_USDT_FUTURES"}


def _none(name: str, message: str, *, state: str = "NO_SETUP", side: str = "NONE",
          level: float | None = None) -> InstitutionalPlaybook:
    return InstitutionalPlaybook(name, state, side, message, level)


def _valid_closed(snap: MarketSnapshot, stamp: datetime) -> bool:
    if (stamp.tzinfo is None or snap.checked_at.tzinfo is None or
            not 0 <= (stamp - snap.checked_at).total_seconds() <= 60 or
            snap.venue not in VENUES or not math.isfinite(snap.bid) or
            not math.isfinite(snap.ask) or snap.bid <= 0 or snap.ask <= snap.bid):
        return False
    stamp_ms = int(snap.checked_at.timestamp() * 1000)
    for tf, period in (("1m", 60_000), ("5m", 300_000), ("15m", 900_000)):
        df = snap.frames.get(tf)
        if df is None or len(df) < 55:
            return False
        try:
            end_ms = int(df.open_ms.iloc[-1]) + period
            if not 0 <= stamp_ms - end_ms <= period + 45_000:
                return False
            if not (df.open_ms.tail(55).diff().dropna() == period).all():
                return False
            for c in ("open", "high", "low", "close", "volume"):
                if not pd.to_numeric(df[c].tail(55), errors="coerce").map(math.isfinite).all():
                    return False
            if (df[["open", "high", "low", "close"]].tail(55) <= 0).any().any():
                return False
            if (df.volume.tail(55) < 0).any():
                return False
        except (KeyError, TypeError, ValueError, OverflowError):
            return False
    last_one_close = float(snap.frames["1m"].close.iloc[-1])
    if abs(snap.bid / last_one_close - 1) > .02:
        return False
    return True


def _flow_share(snap: MarketSnapshot) -> float | None:
    # Bitget's raw candle data has no authenticated taker-buy. Require its
    # adapter's prior public-fills reconciliation before using directional flow.
    if snap.venue == "BITGET_USDT_FUTURES" and not snap.flow_reconciled:
        return None
    last = snap.frames["1m"].tail(3)
    try:
        buy = last.taker_buy.astype(float)
        volumes = last.volume.astype(float)
        if (not buy.notna().all() or not (volumes > 0).all() or
                not ((buy >= 0) & (buy <= volumes * 1.00001)).all() or
                not buy.map(math.isfinite).all()):
            return None
        return float(buy.sum() / volumes.sum())
    except (AttributeError, KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


def _rolling_vwap(frame: pd.DataFrame, end: int | None = None, length: int = 48) -> float:
    f = frame.iloc[:end].tail(length) if end is not None else frame.tail(length)
    volume = f.volume.astype(float)
    typical = (f.high.astype(float) + f.low.astype(float) + f.close.astype(float)) / 3
    total = float(volume.sum())
    return float((typical * volume).sum() / total) if total > 0 else math.nan


def _plan(name: str, snap: MarketSnapshot, cfg: ScalpSettings, *, side: str,
          level: float, stop: float, target: float, reason: str,
          flow: float | None, volume_ratio: float, support_now: bool) -> InstitutionalPlaybook:
    if side == "SHORT" and snap.venue == "BINANCE_TH_SPOT":
        return _none(name, f"Spot ไม่เปิด SHORT · {reason} · เป็นจุดเฝ้าระวังการขาย",
                     state="EXIT_WATCH", side="SELL", level=level)
    if not support_now:
        return _none(name, "ราคา Bid/Ask ล่าสุดไม่ยืนฝั่งที่ควรยืนยันแล้ว · รอดูใหม่",
                     state="PRICE_BLOCK", side=side, level=level)
    if volume_ratio < 1.10:
        return _none(name, f"มีรูปแบบราคา แต่ปริมาณซื้อขาย {volume_ratio:.2f}x ต่ำกว่า 1.10x",
                     state="VOLUME_BLOCK", side=side, level=level)
    if flow is None:
        return _none(name, "มีรูปแบบราคา แต่ Buy/Sell aggressor ที่ตรวจครบ 1m ไม่มี · ไม่อนุมาน",
                     state="FLOW_BLOCK", side=side, level=level)
    confirmed = (flow >= cfg.min_taker_buy_share_long if side == "LONG"
                 else flow <= cfg.max_taker_buy_share_short)
    if not confirmed:
        return _none(name, f"มีรูปแบบราคา แต่ Buy Flow 1m {flow:.1%} ยังไม่ยืนยัน {side}",
                     state="FLOW_BLOCK", side=side, level=level)
    if (snap.spread_bps > cfg.max_spread_bps or
            min(snap.bid_depth_usdt, snap.ask_depth_usdt) <
            cfg.capital_usdt * cfg.min_depth_to_notional_ratio):
        return _none(name, "Spread/Depth ไม่ผ่านกฎต้นทุนและสภาพคล่องเดิม",
                     state="COST_BLOCK", side=side, level=level)
    candidate = _candidate(name, snap, cfg, side, stop, target, reason)
    return InstitutionalPlaybook(name,
                                 "SETUP_WATCH" if candidate.state == "MODEL_WATCH"
                                 else candidate.state,
                                 side, candidate.reason, level,
                                 candidate.entry, candidate.stop,
                                 candidate.target, candidate.net_rr)


def evaluate_institutional_radar(
        snap: MarketSnapshot, cfg: ScalpSettings,
        *, now: datetime | None = None) -> InstitutionalRadar:
    """Three independently explainable *research* hypotheses, never READY.

    No probabilities or implied win rate. Conditions use previous bars for
    historical support/break levels; even the signal bar is already closed.
    """
    stamp = now or snap.checked_at
    if not _valid_closed(snap, stamp):
        return InstitutionalRadar(
            MicrostructureEvidence(None, None, None, None,
                                   "Data audit ไม่ผ่าน: ตลาด/เวลา/แท่งปิดไม่พร้อม"),
            tuple(_none(n, "ข้อมูลไม่ครบหรือเก่า · ห้ามสร้างแผน", state="DATA_BLOCK")
                  for n in NAMES))
    five = snap.frames["5m"]
    prev20, latest = five.iloc[-21:-1], five.iloc[-1]
    support = float(prev20.low.min())
    resistance = float(prev20.high.max())
    prior_mean = float(prev20.volume.mean())
    atr = _atr(five)
    volume_ratio = float(latest.volume) / prior_mean if prior_mean > 0 else math.nan
    vwap = _rolling_vwap(five)
    flow = _flow_share(snap)
    depths = (snap.bid_depth_usdt, snap.ask_depth_usdt)
    if (not all(math.isfinite(x) and x > 0 for x in (support, resistance, atr, vwap))
            or not math.isfinite(volume_ratio) or volume_ratio < 0
            or not all(math.isfinite(x) and x > 0 for x in depths)):
        return InstitutionalRadar(
            MicrostructureEvidence(None, None, None, None, "ATR/Volume/Order Book ไม่พร้อม"),
            tuple(_none(n, "Volume/ATR/Depth ไม่พร้อม", state="DATA_BLOCK") for n in NAMES))
    bid_share = depths[0] / sum(depths)
    evidence = MicrostructureEvidence(
        vwap, volume_ratio, flow, bid_share,
        "1m aggressor (3 แท่งปิด), Order Book 20 ระดับ ณ จุดเดียว, "
        "Rolling 48×5m candle VWAP proxy · ไม่ใช่ L2 OFI / whale identity")

    # 1. Sweep/reclaim: wick takes previous 20-bar extreme and closes back
    # inside, with volume/1m-flow evidence. Classic 'stop hunt' nomenclature
    # does not prove intent, so we deliberately avoid that label.
    if (float(latest.low) < support - atr * .03 and float(latest.close) > support
            and float(latest.close) > float(latest.open)):
        sweep = _plan(NAMES[0], snap, cfg, side="LONG", level=support,
                      stop=float(latest.low) - atr * .15,
                      target=resistance, reason="5m ปิดกลับเหนือ Low 20 แท่งหลังแทงหลุด",
                      flow=flow, volume_ratio=volume_ratio,
                      support_now=snap.bid >= support)
    elif (float(latest.high) > resistance + atr * .03 and
          float(latest.close) < resistance and
          float(latest.close) < float(latest.open)):
        sweep = _plan(NAMES[0], snap, cfg, side="SHORT", level=resistance,
                      stop=float(latest.high) + atr * .15,
                      target=support, reason="5m ปิดกลับใต้ High 20 แท่งหลังแทงทะลุ",
                      flow=flow, volume_ratio=volume_ratio,
                      support_now=snap.ask <= resistance)
    else:
        sweep = _none(NAMES[0], "ไม่มีแท่งปิดที่กวาดสุดกรอบ 20×5m และกลับเข้ากรอบ")

    # 2. Break/retest: previous closed 5m bar broke a 20-bar range; latest
    # closed bar retests that precise prior ceiling/floor without breaking it.
    before_breakout = five.iloc[-22:-2]
    roof = float(before_breakout.high.max())
    floor = float(before_breakout.low.min())
    broken = five.iloc[-2]
    previous_volume = float(five.volume.iloc[-22:-2].mean())
    if (float(broken.close) > roof and float(broken.close) > float(broken.open)
            and float(broken.volume) >= previous_volume * 1.10 and
            float(latest.low) <= roof + .25 * atr and
            float(latest.close) > roof + .05 * atr and
            float(latest.close) > float(latest.open)):
        retest = _plan(NAMES[1], snap, cfg, side="LONG", level=roof,
                       stop=min(float(latest.low), roof) - atr * .15,
                       target=roof + (roof - floor) * .618,
                       reason="5m ปิดทะลุ High เดิมแล้วรีเทสต์แนวรับ; TP จำลองใช้ 0.618×กรอบ",
                       flow=flow, volume_ratio=volume_ratio,
                       support_now=snap.bid > roof)
    elif (float(broken.close) < floor and float(broken.close) < float(broken.open)
          and float(broken.volume) >= previous_volume * 1.10 and
          float(latest.high) >= floor - .25 * atr and
          float(latest.close) < floor - .05 * atr and
          float(latest.close) < float(latest.open)):
        retest = _plan(NAMES[1], snap, cfg, side="SHORT", level=floor,
                       stop=max(float(latest.high), floor) + atr * .15,
                       target=floor - (roof - floor) * .618,
                       reason="5m ปิดหลุด Low เดิมแล้วรีเทสต์แนวต้าน; TP จำลองใช้ 0.618×กรอบ",
                       flow=flow, volume_ratio=volume_ratio,
                       support_now=snap.ask < floor)
    else:
        retest = _none(NAMES[1], "ยังไม่มีแท่ง 5m ทะลุกรอบก่อนหน้าและกลับรีเทสต์สำเร็จ")

    # 3. Rolling candle-VWAP reclaim/rejection (NOT trade-by-trade VWAP).
    old_vwap = _rolling_vwap(five, end=-1)
    previous_close = float(five.close.iloc[-2])
    if (previous_close < old_vwap - .20 * atr and
            float(latest.close) > vwap + .05 * atr and
            float(latest.close) > float(latest.open)):
        vwap_play = _plan(NAMES[2], snap, cfg, side="LONG", level=vwap,
                          stop=min(float(latest.low), float(five.low.iloc[-2])) - .15 * atr,
                          target=max(float(prev20.high.max()), vwap + 1.5 * atr),
                          reason="5m กลับมายืน Rolling VWAP 48 แท่ง; ไม่ใช่ VWAP ของทุกดีล",
                          flow=flow, volume_ratio=volume_ratio,
                          support_now=snap.bid > vwap)
    elif (previous_close > old_vwap + .20 * atr and
          float(latest.close) < vwap - .05 * atr and
          float(latest.close) < float(latest.open)):
        vwap_play = _plan(NAMES[2], snap, cfg, side="SHORT", level=vwap,
                          stop=max(float(latest.high), float(five.high.iloc[-2])) + .15 * atr,
                          target=min(float(prev20.low.min()), vwap - 1.5 * atr),
                          reason="5m หลุด Rolling VWAP 48 แท่ง; ไม่ใช่ VWAP ของทุกดีล",
                          flow=flow, volume_ratio=volume_ratio,
                          support_now=snap.ask < vwap)
    else:
        vwap_play = _none(NAMES[2], "ยังไม่พบการปิดแท่งยืนยันกลับข้าม Rolling VWAP")
    return InstitutionalRadar(evidence, (sweep, retest, vwap_play))
