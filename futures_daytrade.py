"""Read-only USD-M futures day trade candidate detector.

Independent from Spot and frozen watch plans. Closed bars only, trend 4h/1h,
15m breakout/retest. WATCH is NOT an entry; READY is an unexecuted candidate.
No orders, private exchange endpoints, leverage or PnL claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


BASE = "https://fapi.binance.com"
TIMEFRAME_MINUTES = {"15m": 15, "1h": 60, "4h": 240}
SYMBOL_RE = re.compile(r"[A-Z0-9]{2,20}USDT\Z")


@dataclass(frozen=True)
class FuturesSettings:
    symbols: tuple[str, ...]
    capital_usdt: float = 1000.0
    risk_per_signal_pct: float = 0.5
    max_notional_multiple: float = 1.0
    min_net_reward_risk: float = 2.0
    round_trip_cost_pct: float = 0.16
    breakout_lookback: int = 12
    setup_expiry_bars: int = 6
    breakout_volume_ratio: float = 1.2
    entry_zone_atr_fraction: float = 0.45
    max_risk_distance_pct: float = 3.0
    max_mark_last_deviation_pct: float = 0.35
    max_abs_funding_rate_pct: float = 0.3


@dataclass(frozen=True)
class FuturesObservation:
    symbol: str
    state: str
    reason: str
    checked_at: datetime
    direction: str = "NONE"
    setup_id: str = ""
    breakout_level: float | None = None
    entry_low: float | None = None
    entry_high: float | None = None
    stop: float | None = None
    tp1: float | None = None
    tp2: float | None = None
    last_price: float | None = None
    atr: float | None = None
    risk_usdt: float | None = None
    notional_usdt: float | None = None
    net_rr_tp2: float | None = None
    signal_candle: datetime | None = None
    source: str = "BINANCE"


class FuturesDataError(RuntimeError):
    pass


def read_futures_settings(path: str | Path) -> FuturesSettings:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) - set(FuturesSettings.__dataclass_fields__):
        raise ValueError("Futures settings มีช่องไม่รองรับ")
    items = payload.get("symbols")
    if (not isinstance(items, list) or not 1 <= len(items) <= 10 or
            any(not isinstance(x, str) or not SYMBOL_RE.fullmatch(x) for x in items) or
            len(set(items)) != len(items)):
        raise ValueError("symbols ต้องเป็นคู่ USDT Futures ไม่ซ้ำ 1–10 คู่")
    settings = FuturesSettings(**{**payload, "symbols": tuple(items)})
    checks = {
        "capital_usdt": (settings.capital_usdt, 100, 1e7),
        "risk_per_signal_pct": (settings.risk_per_signal_pct, 0.1, 1.0),
        "max_notional_multiple": (settings.max_notional_multiple, 0.1, 2.0),
        "min_net_reward_risk": (settings.min_net_reward_risk, 2.0, 3.0),
        "round_trip_cost_pct": (settings.round_trip_cost_pct, 0.01, 1.0),
        "breakout_volume_ratio": (settings.breakout_volume_ratio, 1.0, 4.0),
        "entry_zone_atr_fraction": (settings.entry_zone_atr_fraction, 0.1, 0.7),
        "max_risk_distance_pct": (settings.max_risk_distance_pct, 0.3, 5.0),
        "max_mark_last_deviation_pct": (settings.max_mark_last_deviation_pct, 0.1, 1.0),
        "max_abs_funding_rate_pct": (settings.max_abs_funding_rate_pct, 0.01, 1.0),
    }
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           or v < lo or v > hi for v, lo, hi in checks.values()):
        raise ValueError("Futures risk settings ไม่อยู่ในช่วงที่ปลอดภัยสำหรับระบบตัวอย่าง")
    if (type(settings.breakout_lookback) is not int or not 8 <= settings.breakout_lookback <= 30 or
            type(settings.setup_expiry_bars) is not int or not 2 <= settings.setup_expiry_bars <= 10):
        raise ValueError("breakout_lookback / setup_expiry_bars ไม่ถูกต้อง")
    return settings


def _read_public(endpoint: str, params: dict | None = None):
    request = Request(BASE + endpoint + ("?" + urlencode(params) if params else ""),
                      headers={"User-Agent": "OrbitFuturesDayTrade/1.0 read-only"})
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        raise FuturesDataError(f"Binance USD-M API HTTP {exc.code}") from None
    except (URLError, OSError, TimeoutError) as exc:
        raise FuturesDataError(f"Binance USD-M API network/timeout ({type(exc).__name__})") from None
    except ValueError:
        raise FuturesDataError("Binance USD-M API JSON format ไม่ถูกต้อง") from None


def fetch_futures_catalog() -> set[str]:
    payload = _read_public("/fapi/v1/exchangeInfo")
    if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
        raise FuturesDataError("Futures Catalog format ไม่ถูกต้อง")
    return {row["symbol"] for row in payload["symbols"]
            if isinstance(row, dict) and isinstance(row.get("symbol"), str)
            and row.get("status") == "TRADING" and row.get("contractType") == "PERPETUAL"
            and row.get("quoteAsset") == "USDT"}


def parse_futures_klines(rows: list, *, now: datetime, timeframe: str) -> pd.DataFrame:
    if now.tzinfo is None or timeframe not in TIMEFRAME_MINUTES or not isinstance(rows, list):
        raise FuturesDataError("วันที่/Timeframe/แถวเทียนไม่ถูกต้อง")
    if len(rows) < 100 or any(not isinstance(r, list) or len(r) < 11 for r in rows):
        raise FuturesDataError("จำนวน/รูปแบบแท่ง Futures ไม่พอ")
    columns = ["opened", "open", "high", "low", "close", "volume", "closed", "taker_buy"]
    frame = pd.DataFrame([[r[i] for i in (0, 1, 2, 3, 4, 5, 6, 9)] for r in rows], columns=columns)
    for field in ("opened", "closed", "open", "high", "low", "close", "volume", "taker_buy"):
        frame[field] = pd.to_numeric(frame[field], errors="raise")
    frame["opened"] = frame["opened"].astype("int64")
    frame.index = pd.to_datetime(frame["opened"], unit="ms", utc=True)
    frame = frame.sort_index()
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise FuturesDataError("เวลา Futures Klines ไม่ต่อเนื่อง")
    now_ms = int(now.timestamp() * 1000)
    period_ms = TIMEFRAME_MINUTES[timeframe] * 60_000
    frame = frame.loc[(frame["opened"] + period_ms) <= now_ms].copy()
    if len(frame) < 100 or now_ms - (int(frame["opened"].iloc[-1]) + period_ms) > 2 * period_ms:
        raise FuturesDataError(f"แท่ง {timeframe} ปิดช้าหรือขาดช่วง")
    if ((frame["open"] <= 0) | (frame["high"] <= 0) | (frame["low"] <= 0)
            | (frame["close"] <= 0) | (frame["volume"] < 0)
            | (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
            | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
            | (frame["taker_buy"] < 0) | (frame["taker_buy"] > frame["volume"])).any():
        raise FuturesDataError("OHLC/volume Futures ไม่สมเหตุผล")
    recent_diff = frame.index.to_series().diff().dt.total_seconds().tail(30).dropna()
    if (recent_diff != TIMEFRAME_MINUTES[timeframe] * 60).any():
        raise FuturesDataError(f"แท่ง {timeframe} มีช่วงเวลาขาด")
    return frame


def fetch_futures_klines(symbol: str, timeframe: str, *, now: datetime) -> pd.DataFrame:
    if not SYMBOL_RE.fullmatch(symbol) or timeframe not in TIMEFRAME_MINUTES:
        raise FuturesDataError("Symbol/interval Futures ไม่ถูกต้อง")
    rows = _read_public("/fapi/v1/klines", {"symbol": symbol, "interval": timeframe, "limit": 250})
    return parse_futures_klines(rows, now=now, timeframe=timeframe)


def fetch_futures_ticker(symbol: str, *, now: datetime) -> tuple[float, float, float]:
    ticker = _read_public("/fapi/v1/ticker/price", {"symbol": symbol})
    premium = _read_public("/fapi/v1/premiumIndex", {"symbol": symbol})
    try:
        if ticker["symbol"] != symbol or premium["symbol"] != symbol:
            raise ValueError("symbol mismatch")
        last = float(ticker["price"])
        mark = float(premium["markPrice"])
        funding_pct = float(premium["lastFundingRate"]) * 100
        if any(not math.isfinite(x) for x in (last, mark, funding_pct)) or last <= 0 or mark <= 0:
            raise ValueError("invalid price")
        last_at = datetime.fromtimestamp(int(ticker["time"]) / 1000, timezone.utc)
        mark_at = datetime.fromtimestamp(int(premium["time"]) / 1000, timezone.utc)
        if any(abs((now - stamp).total_seconds()) > 180 for stamp in (last_at, mark_at)):
            raise ValueError("stale mark/last")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FuturesDataError("Futures ticker/mark/funding ขาดหรือไม่สด") from exc
    return last, mark, funding_pct


def _atr(frame: pd.DataFrame) -> pd.Series:
    prior_close = frame["close"].shift(1)
    true_range = pd.concat([frame["high"] - frame["low"],
                            (frame["high"] - prior_close).abs(),
                            (frame["low"] - prior_close).abs()], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()


def _direction(frame1h: pd.DataFrame, frame4h: pd.DataFrame) -> str:
    def trend(frame):
        close = frame["close"].astype(float)
        fast = close.ewm(span=20, adjust=False).mean().iloc[-1]
        slow = close.ewm(span=50, adjust=False).mean().iloc[-1]
        if close.iloc[-1] > fast > slow:
            return "LONG"
        if close.iloc[-1] < fast < slow:
            return "SHORT"
        return "WAIT"
    d1, d4 = trend(frame1h), trend(frame4h)
    return d1 if d1 == d4 else "WAIT"


def _format_id(when: pd.Timestamp, direction: str) -> str:
    return f"{direction}:{when.isoformat()}"


def evaluate_futures(symbol: str, frames: dict[str, pd.DataFrame], *,
                     last: float, mark: float, funding_pct: float,
                     now: datetime, settings: FuturesSettings,
                     require_taker_flow: bool = True) -> FuturesObservation:
    """Return WATCH/READY only for recent confirmed closed-bar events.

    Historical pattern matching is not a validated predictive edge or backtest.
    """
    blank = lambda status, reason: FuturesObservation(symbol, status, reason, now, last_price=last)
    if symbol not in settings.symbols or now.tzinfo is None:
        raise ValueError("symbol/clock invalid")
    if (not all(x in frames for x in ("15m", "1h", "4h")) or
            any(len(frames[x]) < 100 for x in ("15m", "1h", "4h"))):
        return blank("DATA_UNAVAILABLE", "แท่ง Futures ไม่พอ")
    if not all(math.isfinite(x) and x > 0 for x in (last, mark)) or not math.isfinite(funding_pct):
        return blank("DATA_UNAVAILABLE", "ราคา/ทุน funding ไม่พร้อม")
    if abs(last / mark - 1) * 100 > settings.max_mark_last_deviation_pct:
        return blank("RISK_BLOCK", "Mark และ Last ต่างกันมากเกินกำหนด")
    if abs(funding_pct) > settings.max_abs_funding_rate_pct:
        return blank("RISK_BLOCK", "Funding สูงผิดปกติ")
    direction = _direction(frames["1h"], frames["4h"])
    if direction == "WAIT":
        return blank("NO_TREND", "แนวโน้ม 1H และ 4H ไม่ตรงกัน")
    bars = frames["15m"]
    atr_values = _atr(bars)
    atr_now = float(atr_values.iloc[-1])
    if not math.isfinite(atr_now) or atr_now <= 0:
        return blank("DATA_UNAVAILABLE", "ATR คำนวณไม่ได้")

    # Most-recent breakout within 6 bars; do not react to an ancient setup.
    candidate = None
    end = len(bars) - 1
    earliest = max(settings.breakout_lookback + 25, end - settings.setup_expiry_bars)
    for i in range(end, earliest - 1, -1):
        prior = bars.iloc[i - settings.breakout_lookback:i]
        candle = bars.iloc[i]
        mean_volume = float(bars["volume"].iloc[i - 20:i].mean())
        if not math.isfinite(mean_volume) or mean_volume <= 0:
            continue
        high_break = float(prior["high"].max())
        low_break = float(prior["low"].min())
        bullish = direction == "LONG" and candle["close"] > high_break and candle["close"] > candle["open"]
        bearish = direction == "SHORT" and candle["close"] < low_break and candle["close"] < candle["open"]
        if not (bullish or bearish):
            continue
        buy_share = float(candle["taker_buy"] / candle["volume"]) if candle["volume"] > 0 else float("nan")
        if candle["volume"] / mean_volume < settings.breakout_volume_ratio:
            continue
        if require_taker_flow and (not math.isfinite(buy_share) or
                (direction == "LONG" and buy_share < 0.52) or
                (direction == "SHORT" and buy_share > 0.48)):
            continue
        candidate = (i, high_break if bullish else low_break)
        break
    if candidate is None:
        return blank("NO_SETUP", "ยังไม่เกิด breakout ที่ยืนยันด้วย Volume/Taker Flow")
    breakout_at, level = candidate
    atr_breakout = float(atr_values.iloc[breakout_at])
    if not math.isfinite(atr_breakout) or atr_breakout <= 0:
        return blank("DATA_UNAVAILABLE", "ATR ที่จุดเบรกเอาต์ไม่พร้อม")
    started_at = bars.index[breakout_at]
    setup_id = _format_id(started_at, direction)
    succeeding = bars.iloc[breakout_at + 1:]
    buffer = atr_breakout * settings.entry_zone_atr_fraction
    entry_low, entry_high = ((level, level + buffer) if direction == "LONG"
                             else (level - buffer, level))
    # Fatal failed retest: never reissue entry from this broken setup.
    if ((direction == "LONG" and (succeeding["close"] < level - 0.5 * atr_breakout).any())
            or (direction == "SHORT" and (succeeding["close"] > level + 0.5 * atr_breakout).any())):
        return FuturesObservation(symbol, "INVALIDATED", "หลัง breakout ราคาปิดทะลุระดับยกเลิก setup",
                                  now, direction, setup_id, level, entry_low, entry_high,
                                  last_price=last, atr=atr_breakout, signal_candle=started_at.to_pydatetime())

    if direction == "LONG":
        stop = min(float(bars["low"].iloc[max(0, breakout_at - 4):breakout_at + 1].min()),
                   level - 0.8 * atr_breakout) - 0.1 * atr_breakout
    else:
        stop = max(float(bars["high"].iloc[max(0, breakout_at - 4):breakout_at + 1].max()),
                   level + 0.8 * atr_breakout) + 0.1 * atr_breakout
    entry_reference = (entry_low + entry_high) / 2
    risk_distance = (entry_reference - stop) if direction == "LONG" else (stop - entry_reference)
    if risk_distance <= 0 or risk_distance / entry_reference * 100 > settings.max_risk_distance_pct:
        return FuturesObservation(symbol, "RISK_BLOCK", "Stop ห่าง/ใกล้ผิดเกณฑ์ของแผน",
                                  now, direction, setup_id, level, entry_low, entry_high,
                                  stop=stop, last_price=last, atr=atr_breakout)
    costs = entry_reference * settings.round_trip_cost_pct / 100
    net_rr = settings.min_net_reward_risk
    target_move = net_rr * (risk_distance + costs) + costs
    sign = 1 if direction == "LONG" else -1
    tp1 = entry_reference + sign * (risk_distance * 1.5 + costs * 2.5)
    tp2 = entry_reference + sign * target_move
    if min(tp1, tp2) <= 0:
        return blank("RISK_BLOCK", "ราคาเป้าหมายไม่สมเหตุผล")
    risk_budget = settings.capital_usdt * settings.risk_per_signal_pct / 100
    units = min(risk_budget / (risk_distance + costs),
                settings.capital_usdt * settings.max_notional_multiple / entry_reference)
    theoretical_risk = units * (risk_distance + costs)
    notional = units * entry_reference

    # A closed retest confirmation is actionable only while live Futures ticker
    # remains in the mapped entry zone. No chase of prices outside zone.
    recent = succeeding.iloc[-1] if len(succeeding) else None
    if recent is not None and breakout_at < end:
        if direction == "LONG":
            retest = (float(recent["low"]) <= level + buffer and
                      float(recent["close"]) >= level + 0.1 * atr_breakout and
                      float(recent["close"]) > float(recent["open"]) and
                      float(recent["close"]) > level)
        else:
            retest = (float(recent["high"]) >= level - buffer and
                      float(recent["close"]) <= level - 0.1 * atr_breakout and
                      float(recent["close"]) < float(recent["open"]) and
                      float(recent["close"]) < level)
        # Reject a 15m bar with no trades and a ticker that has already escaped.
        retest &= float(recent["volume"]) > 0
    else:
        retest = False
    in_zone = entry_low <= last <= entry_high
    # Alternate exchange candles lack historical taker-side flow. They may
    # produce a directional WATCH, but NEVER an actionable READY candidate.
    status = "READY_" + direction if retest and in_zone and require_taker_flow else "WATCH_" + direction
    reason = ("15m retest ยืนยันแล้ว ราคา Futures ยังอยู่ใน Entry Zone"
              if retest and in_zone and require_taker_flow else
              "Volume breakout เบื้องต้น (ขาด Taker Flow): WATCH เท่านั้น ไม่ใช่จุดเข้า"
              if not require_taker_flow else
              "Breakout ยืนยันแล้ว รอ retest เข้าโซน; ห้ามไล่ราคา")
    return FuturesObservation(symbol, status, reason, now, direction, setup_id,
                              level, entry_low, entry_high, stop, tp1, tp2, last,
                              atr_breakout, theoretical_risk, notional, net_rr,
                              started_at.to_pydatetime())
