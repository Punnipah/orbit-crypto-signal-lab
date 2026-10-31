"""Headless, read-only Orbit MTF + Frozen Watch checks for scheduled monitoring.

Reuses the same underlying timeframe, futures, microstructure, BTC, risk and
watch evaluators as the Streamlit dashboard. Optional CoinGlass is MANUAL;
missing or invalid exchange evidence is never synthesized as a BUY.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import re
from urllib.parse import parse_qs, urlparse

import pandas as pd

from binance_data import HIGHER_TIMEFRAME, TIMEFRAMES, fetch_catalog, fetch_klines, fetch_spot_last_price
from btc_market import btc_context_checks, btc_regime
from bybit_intelligence import fetch_bybit_evidence
from coinglass_overlay import CoinGlassSnapshot
from confluence import combine_timeframes
from market_microstructure import fetch_microstructure, microstructure_checks
from multi_timeframe import RuleCheck, build_timeframe_report
from public_derivatives import DerivativesDataError, fetch_with_fallback
from research_engine import prepare_features, with_signal
from risk_audit import audit_entry
from rally_watch import RallySettings, evaluate_rally
from watch_plans import decode_watch, evaluate_watch


SYMBOL_RE = re.compile(r"[A-Z0-9]{2,20}USDT\Z")


@dataclass(frozen=True)
class MonitorSettings:
    symbols: tuple[str, ...]
    history_candles: int = 1000
    capital: float = 10000
    risk_pct: float = 1.0
    max_allocation_pct: float = 30
    fee_pct: float = 0.1
    slippage_pct: float = 0.05
    min_net_rr: float = 1.5
    pivot_bars: int = 3
    rally_watch_above_zone_pct: float = 3.0
    rally_missed_above_zone_pct: float = 8.0
    rally_confirmation_bars: int = 2
    rally_min_volume_ratio: float = 0.8
    rally_candidate_max_above_new_zone_pct: float = 1.0

    def rally_settings(self) -> RallySettings:
        settings = RallySettings(self.rally_watch_above_zone_pct,
                                 self.rally_missed_above_zone_pct,
                                 self.rally_confirmation_bars,
                                 self.rally_min_volume_ratio,
                                 self.rally_candidate_max_above_new_zone_pct)
        settings.validate()
        return settings


@dataclass(frozen=True)
class Observation:
    symbol: str
    mode: str  # FROZEN or LIVE_MTF
    status: str
    observed_at: datetime
    last_price: float | None
    alignment: float | None
    futures_source: str
    coinglass_status: str
    reason: str
    watch_token: str | None = None
    watch_url: str | None = None
    entry_low: float | None = None
    entry_high: float | None = None
    stop_loss: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    trigger_at: datetime | None = None
    failed_checks: tuple[str, ...] = ()
    opportunity_status: str = "NONE"
    opportunity_reason: str = ""
    opportunity_distance_pct: float | None = None
    opportunity_volume_ratio: float | None = None
    opportunity_frozen_atr_pct: float | None = None
    opportunity_confirmed_at: datetime | None = None
    candidate_low: float | None = None
    candidate_high: float | None = None


def read_settings(path: str | Path) -> MonitorSettings:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Monitor config ต้องเป็น JSON object")
    allowed = set(MonitorSettings.__dataclass_fields__)
    if set(data) - allowed:
        raise ValueError("Monitor config มีชื่อช่องที่ระบบไม่รู้จัก")
    if not isinstance(data.get("symbols"), list) or not 1 <= len(data["symbols"]) <= 10:
        raise ValueError("ต้องระบุเหรียญ 1–10 คู่ใน symbols")
    symbols = tuple(data["symbols"])
    if (len(set(symbols)) != len(symbols)
            or not all(isinstance(s, str) and SYMBOL_RE.fullmatch(s) for s in symbols)):
        raise ValueError("สัญลักษณ์ต้องเป็นคู่ USDT และไม่ซ้ำ เช่น PEPEUSDT")
    settings = MonitorSettings(**{**data, "symbols": symbols})
    numeric = (settings.capital, settings.risk_pct, settings.max_allocation_pct,
               settings.fee_pct, settings.slippage_pct, settings.min_net_rr)
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) for v in numeric):
        raise ValueError("พารามิเตอร์ความเสี่ยงไม่ใช่ตัวเลขที่ใช้ได้")
    if (not isinstance(settings.history_candles, int) or not 500 <= settings.history_candles <= 2000
            or not isinstance(settings.pivot_bars, int) or not 2 <= settings.pivot_bars <= 6
            or not 100 <= settings.capital <= 1e9
            or not 0.25 <= settings.risk_pct <= 3
            or not 5 <= settings.max_allocation_pct <= 100
            or not 0 <= settings.fee_pct <= 2 or not 0 <= settings.slippage_pct <= 2
            or not 1 <= settings.min_net_rr <= 2.5):
        raise ValueError("พารามิเตอร์ Monitor อยู่นอกช่วงที่รองรับ")
    settings.rally_settings()
    return settings


def parse_watch_links(raw: str, symbols: tuple[str, ...]) -> dict[str, tuple[str, str | None]]:
    """Accept SYMBOL=URL or SYMBOL=TOKEN lines from an Actions secret.

    No request is made to the supplied URL. The token itself is parsed and
    validated locally; a mismatched symbol is rejected loudly.
    """
    result: dict[str, tuple[str, str | None]] = {}
    for original in raw.splitlines():
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError("ORBIT_WATCH_LINKS ต้องเขียน SYMBOL=ลิงก์แผน แต่ละบรรทัด")
        symbol, value = (part.strip() for part in line.split("=", 1))
        if symbol not in symbols or symbol in result:
            raise ValueError("ORBIT_WATCH_LINKS มีคู่ที่ไม่ได้เลือกหรือซ้ำกัน")
        token = value
        url = None
        if value.startswith("https://") or value.startswith("http://"):
            parsed = urlparse(value)
            if not parsed.netloc or parsed.username or parsed.password or not parsed.hostname:
                raise ValueError("URL แผนไม่ถูกต้อง")
            values = parse_qs(parsed.query).get("watch", [])
            if len(values) != 1:
                raise ValueError("ลิงก์ต้องมี ?watch= ที่ถูกต้อง")
            token = values[0]
            url = value
        plan = decode_watch(token)
        if plan.symbol != symbol:
            raise ValueError(f"แผนที่ล็อกเป็น {plan.symbol} ไม่ใช่ {symbol}")
        result[symbol] = (token, url)
    return result


def read_manual_coinglass(path: str | Path) -> dict[str, CoinGlassSnapshot]:
    """Never scrape CoinGlass or manufacture 24h derivatives/liquidation fields."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"snapshots"} or not isinstance(data["snapshots"], dict):
        raise ValueError("CoinGlass ต้องเป็น {\"snapshots\": {...}}")
    out: dict[str, CoinGlassSnapshot] = {}
    numeric_names = ("funding_rate_pct", "oi_change_24h_pct", "long_short_account_ratio",
                     "long_liquidations_usd_24h", "short_liquidations_usd_24h")
    for name, entry in data["snapshots"].items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Z0-9]{2,20}", name):
            raise ValueError("ชื่อเหรียญ CoinGlass ไม่ถูกต้อง")
        if not isinstance(entry, dict) or set(entry) != {"observed_at", *numeric_names}:
            raise ValueError(f"CoinGlass {name} ขาดช่องหรือมีช่องแปลกปลอม")
        try:
            at = datetime.fromisoformat(entry["observed_at"])
            values = [float(entry[n]) for n in numeric_names]
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"CoinGlass {name} มีวันที่/ตัวเลขไม่ถูกต้อง") from exc
        if at.tzinfo is None or not all(math.isfinite(v) for v in values):
            raise ValueError(f"CoinGlass {name} ต้องมี timezone และตัวเลขที่ใช้ได้")
        out[name] = CoinGlassSnapshot(name, at, *values)
    return out


def unavailable(symbol: str, now: datetime, error: str, *,
                watch_token: str | None = None, watch_url: str | None = None) -> Observation:
    return Observation(symbol, "FROZEN" if watch_token else "LIVE_MTF", "DATA_UNAVAILABLE",
                       now, None, None, "MISSING", "UNKNOWN", error,
                       watch_token=watch_token, watch_url=watch_url)


def analyze_symbol(symbol: str, settings: MonitorSettings, *,
                   now: datetime, watch: tuple[str, str | None] | None,
                   manual_cg: CoinGlassSnapshot | None,
                   btc_bars: tuple[pd.DataFrame, pd.DataFrame] | None = None,
                   return_live_also: bool = False) -> Observation | tuple[Observation, Observation]:
    """Read data once, using the same mandatory veto rules as Orbit's MTF tab.

    Network failures in optional cross-exchange evidence are non-fatal; those
    in mandatory sources always result in WAIT or DATA_UNAVAILABLE, not BUY.
    """
    if symbol not in settings.symbols or now.tzinfo is None:
        raise ValueError("symbol/now ไม่ถูกต้อง")
    token, url = watch if watch else (None, None)
    frames = {tf: fetch_klines(symbol, tf, settings.history_candles) for tf in TIMEFRAMES}
    try:
        price, _requested_at = fetch_spot_last_price(symbol)
    except (ValueError, RuntimeError, OSError):
        price = None
    try:
        derivatives = fetch_with_fallback(symbol)
    except (DerivativesDataError, ValueError, RuntimeError, OSError):
        derivatives = None
    evaluated = {tf: with_signal(prepare_features(frames[tf], frames[HIGHER_TIMEFRAME[tf]],
                                                 tf, pivot_bars=settings.pivot_bars))
                 for tf in TIMEFRAMES}
    reports = {tf: build_timeframe_report(
        frames[tf], evaluated[tf], tf, base_asset=symbol[:-4], derivatives=derivatives,
        coinglass=manual_cg, now=now, current_price=price,
        capital=settings.capital, risk_pct=settings.risk_pct,
        max_allocation_pct=settings.max_allocation_pct,
        fee_pct=settings.fee_pct, slippage_pct=settings.slippage_pct,
    ) for tf in TIMEFRAMES}
    order_notional = (reports["1h"].entry.notional
                      if reports["1h"].entry.notional is not None
                      else settings.capital * settings.max_allocation_pct / 100)
    try:
        micro = fetch_microstructure(symbol, round(float(order_notional), 4))
    except (ValueError, RuntimeError, OSError):
        micro = None
    try:
        if symbol == "BTCUSDT":
            btc_four, btc_daily = frames["4h"], frames["1d"]
        elif btc_bars is not None:
            btc_four, btc_daily = btc_bars
        else:
            btc_four = fetch_klines("BTCUSDT", "4h", settings.history_candles)
            btc_daily = fetch_klines("BTCUSDT", "1d", settings.history_candles)
        btc = btc_regime(btc_four, btc_daily, now=now)
    except (ValueError, RuntimeError, OSError, KeyError, IndexError):
        btc = None
    try:
        bybit = fetch_bybit_evidence(symbol)
    except (ValueError, RuntimeError, OSError):
        bybit = None

    risk = audit_entry(reports["1h"].entry, fee_pct=settings.fee_pct,
                       slippage_pct=settings.slippage_pct, min_net_rr=settings.min_net_rr)
    extra = list(microstructure_checks(micro, now=now, requested_notional=order_notional))
    extra.extend(btc_context_checks(btc))
    extra.extend(risk.checks)
    if bybit is not None and bybit.spot_mid is not None and micro is not None:
        mid = (micro.bid + micro.ask) / 2
        deviation = abs(bybit.spot_mid / mid - 1) * 100
        extra.append(RuleCheck("Spot สอง Exchange ไม่ต่างกันผิดปกติ (≤1.5%)",
                               deviation <= 1.5, f"Binance/Bybit {deviation:.2f}%"))
    for tf in ("1h", "15m"):
        share = reports[tf].taker_buy_share20
        extra.append(RuleCheck(f"แรงซื้อเชิงรุกจากแท่ง {tf} 20 แท่ง ≥52%",
                               pd.notna(share) and share >= 0.52,
                               f"Taker Buy {share*100:.1f}%" if pd.notna(share)
                               else "Taker Buy ไม่พร้อม"))
    if micro is not None and price is not None:
        mid = (micro.bid + micro.ask) / 2
        extra.append(RuleCheck("Spot Last Price ใกล้ Bid/Ask (ไม่เกิน 1%)",
                               abs(price - mid) / mid <= 0.01, f"Mid {mid}"))
    verdict = combine_timeframes(reports, additional_checks=extra)
    failed = tuple(check.label for check in verdict.checks if check.passed is False)
    cg_status = reports["15m"].coinglass_status if manual_cg is not None else "NOT_ENTERED"
    futures_name = derivatives.source if derivatives is not None else "MISSING"
    plan = verdict.entry
    live_observation = Observation(
        symbol, "LIVE_MTF", "MTF_READY" if verdict.status == "READY" else "MTF_WAIT",
        now, price, verdict.alignment_index, futures_name, cg_status,
        "; ".join(verdict.reasons[:3]) or "ยังไม่ถึงเกณฑ์รวม",
        entry_low=plan.entry_low if plan else None,
        entry_high=plan.entry_high if plan else None,
        stop_loss=plan.stop_loss if plan else None,
        tp1=plan.take_profit_1 if plan else None,
        tp2=plan.take_profit_2 if plan else None,
        trigger_at=reports["15m"].last_close, failed_checks=failed)
    if token is not None:
        try:
            plan = decode_watch(token)
            result = evaluate_watch(plan, frames["15m"], now=now, current_price=price,
                                    mtf_buy=verdict.signal == "BUY")
            rally = evaluate_rally(plan, frames["15m"], now=now, current_price=price,
                                   frozen_status=result.status,
                                   context_ready=(derivatives is not None and micro is not None
                                                  and btc is not None and btc.clean
                                                  and verdict.alignment_index is not None
                                                  and all(check.passed for check in extra[:2])),
                                   live_mtf_ready=verdict.status == "READY",
                                   new_entry=verdict.entry, settings=settings.rally_settings())
        except Exception as exc:
            # Frozen URL parsing and lifecycle are optional; a bad old plan
            # must never turn a valid LIVE MTF scan into DATA_UNAVAILABLE.
            if return_live_also:
                return (live_observation,
                        unavailable(symbol, now, f"แผนที่บันทึกไว้ตรวจไม่ได้ ({type(exc).__name__})",
                                    watch_token=token, watch_url=url))
            raise
        frozen_observation = Observation(
            symbol, "FROZEN", result.status, now, price,
            verdict.alignment_index, futures_name, cg_status, result.reason,
            token, url, plan.entry_low, plan.entry_high, plan.stop_loss,
            plan.take_profit_1, plan.take_profit_2, result.triggered_at, failed,
            rally.status, rally.reason, rally.distance_pct,
            rally.volume_ratio, rally.frozen_atr_pct, rally.latest_confirmed_at,
            rally.new_entry_low, rally.new_entry_high)
        return (live_observation, frozen_observation) if return_live_also else frozen_observation
    return live_observation
