"""Orbit Model Lab: public same-venue candles and causal, paper-only research.

Never places orders, claims a win probability, or changes production signals.
The earliest simulated entry is the OPEN following a completed signal candle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


INTERVAL_MS = 300_000
VENUES = {
    "BINANCE_TH_SPOT": ("Binance TH · Spot", "https://api.binance.th/api/v1/klines"),
    "BINANCE_GLOBAL_USDM": ("Binance Global · USDT Futures", "https://fapi.binance.com/fapi/v1/klines"),
    "BITGET_USDT_FUTURES": ("Bitget · USDT Futures", "https://api.bitget.com/api/v3/market/candles"),
}
SYMBOLS = ("PEPEUSDT", "BTCUSDT", "DOGEUSDT", "ETHUSDT", "SOLUSDT")
MODELS = (
    "EMA Pullback",
    "BB20 Range Bounce",
    "Breakout + Retest",
    "Liquidity Sweep + Reclaim",
)


class DataUnavailable(RuntimeError):
    """A venue, a timestamp, or historic candles could not be trusted."""


def _read_json(url: str, params: dict) -> object:
    req = Request(url + "?" + urlencode(params), headers={"User-Agent": "OrbitModelLab/2.0 public-readonly"})
    try:
        with urlopen(req, timeout=15) as response:
            return json.load(response)
    except HTTPError as exc:
        raise DataUnavailable(f"Exchange HTTP {exc.code}; ตลาดนี้ไม่พร้อมใช้งานจากเซิร์ฟเวอร์") from None
    except (URLError, TimeoutError, OSError):
        raise DataUnavailable("Exchange timeout/network; ไม่ใช้ข้อมูลตลาดอื่นแทน") from None
    except (ValueError, TypeError):
        raise DataUnavailable("Exchange ส่ง JSON ไม่ถูกต้อง") from None


def validate_candles(data: pd.DataFrame, *, now: datetime | None = None,
                     require_fresh: bool = True) -> pd.DataFrame:
    """Reject gaps, duplicates, impossible OHLC, partial and stale bars."""
    if not {"open_ms", "open", "high", "low", "close", "volume"}.issubset(data.columns):
        raise DataUnavailable("OHLCV fields ไม่ครบ")
    frame = data.copy()
    for col in ("open_ms", "open", "high", "low", "close", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna()
    frame = frame.sort_values("open_ms")
    if len(frame) < 500 or frame.open_ms.duplicated().any():
        raise DataUnavailable("ข้อมูลแท่งปิดไม่ครบ 500 แท่งหรือมีแท่งซ้ำ")
    frame["open_ms"] = frame.open_ms.astype("int64")
    if (frame.open_ms.diff().dropna() != INTERVAL_MS).any():
        raise DataUnavailable("ข้อมูล 5m มีช่วงเวลาขาด/ซ้ำ ไม่อนุญาต Backtest")
    if ((frame[["open", "high", "low", "close"]] <= 0).any().any()
            or (frame.volume < 0).any()
            or (frame.high < frame[["open", "low", "close"]].max(axis=1)).any()
            or (frame.low > frame[["open", "high", "close"]].min(axis=1)).any()):
        raise DataUnavailable("ข้อมูล OHLCV ผิดสมเหตุผล")
    if now is not None:
        if now.tzinfo is None:
            raise DataUnavailable("Timestamp ต้องระบุ timezone")
        lag = int(now.timestamp() * 1000) - (int(frame.open_ms.iloc[-1]) + INTERVAL_MS)
        if lag < 0 or (require_fresh and lag > 2 * INTERVAL_MS + 45_000):
            raise DataUnavailable("แท่ง 5m ยังไม่ปิดหรือข้อมูลช้าเกิน 10 นาที")
    frame.index = pd.to_datetime(frame.open_ms, unit="ms", utc=True)
    return frame


def fetch_candles(venue: str, symbol: str, days: int = 14,
                  *, now: datetime | None = None) -> pd.DataFrame:
    """Download selected *same-venue* closed 5m bars; never silently fallback."""
    if venue not in VENUES or symbol not in SYMBOLS or not re.fullmatch(r"[A-Z0-9]+USDT", symbol):
        raise DataUnavailable("ตลาดหรือคู่เหรียญไม่รองรับ")
    if days not in (7, 14, 30):
        raise DataUnavailable("เลือกข้อมูลย้อนหลัง 7, 14 หรือ 30 วัน")
    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        raise DataUnavailable("เวลาตลาดต้องมี timezone")
    # Leave one closed candle worth of tolerance for HTTP response latency.
    end_ms = int(stamp.timestamp() * 1000) // INTERVAL_MS * INTERVAL_MS
    start_ms = end_ms - days * 86_400_000 - 50 * INTERVAL_MS
    cursor = start_ms
    rows: list[tuple] = []
    url = VENUES[venue][1]
    # 30 days at 5m is 8,640 bars; 10 pages at 1,000 rows + warmup.
    for _ in range(15):
        if cursor >= end_ms:
            break
        chunk_end = min(end_ms - 1, cursor + 999 * INTERVAL_MS)
        if venue == "BITGET_USDT_FUTURES":
            params = {"category": "USDT-FUTURES", "symbol": symbol,
                      "interval": "5m", "startTime": cursor,
                      "endTime": chunk_end, "limit": 1000}
        else:
            params = {"symbol": symbol, "interval": "5m",
                      "startTime": cursor, "endTime": chunk_end, "limit": 1000}
        payload = _read_json(url, params)
        if venue == "BITGET_USDT_FUTURES":
            if not isinstance(payload, dict) or payload.get("code") != "00000":
                raise DataUnavailable("Bitget ตอบกลับไม่สำเร็จ")
            payload = payload.get("data")
        if not isinstance(payload, list) or not payload:
            raise DataUnavailable("Exchange ไม่ส่งแท่งเทียนตามช่วงที่ร้องขอ")
        parsed = []
        for item in payload:
            if not isinstance(item, (list, tuple)) or len(item) < 6:
                raise DataUnavailable("รูปแบบแท่งเทียนไม่ถูกต้อง")
            try:
                parsed.append((int(item[0]), *(float(item[i]) for i in range(1, 6))))
            except (ValueError, TypeError, OverflowError):
                raise DataUnavailable("ค่าตัวเลขของแท่งเทียนไม่ถูกต้อง") from None
        parsed.sort(key=lambda x: x[0])
        latest = parsed[-1][0]
        if latest < cursor or latest >= end_ms:
            raise DataUnavailable("เวลาของแท่งเทียนผิดขอบเขต")
        rows.extend(parsed)
        cursor = latest + INTERVAL_MS
    else:
        raise DataUnavailable("จำนวนหน้า API เกินขีดจำกัด")
    if cursor < end_ms:
        raise DataUnavailable("ข้อมูลย้อนหลังไม่ครบช่วง")
    data = pd.DataFrame(rows, columns=["open_ms", "open", "high", "low", "close", "volume"])
    # Disallow duplicate bars even if pagination overlaps.
    return validate_candles(data, now=stamp)


def indicators(data: pd.DataFrame) -> pd.DataFrame:
    """Features use the present/past closed candle only, never future shifts."""
    f = validate_candles(data, require_fresh=False)
    c = f.close
    f["ema9"] = c.ewm(span=9, adjust=False, min_periods=30).mean()
    f["ema21"] = c.ewm(span=21, adjust=False, min_periods=30).mean()
    mid = c.rolling(20).mean()
    std = c.rolling(20).std(ddof=0)
    f["bb_lower"] = (mid - 2 * std).shift(1)
    f["bb_upper"] = (mid + 2 * std).shift(1)
    f["bb_mid"] = mid.shift(1)
    true_range = pd.concat([(f.high-f.low), (f.high-c.shift()).abs(),
                            (f.low-c.shift()).abs()], axis=1).max(axis=1)
    f["atr"] = true_range.rolling(14).mean()
    f["prev_high20"] = f.high.rolling(20).max().shift(1)
    f["prev_low20"] = f.low.rolling(20).min().shift(1)
    f["avg_volume20"] = f.volume.rolling(20).mean().shift(1)
    return f


def model_signals(f: pd.DataFrame, model: str, allow_short: bool) -> pd.Series:
    """Return 1/-1/0 for long/short/none, observed at each candle close."""
    if model not in MODELS:
        raise ValueError("Unknown model")
    c = f.close
    if model == "EMA Pullback":
        long = ((f.ema9 > f.ema21) & (f.ema21 > f.ema21.shift(3)) &
                (f.low <= f.ema9) & (c > f.ema9) & (c > f.open) &
                (f.volume >= f.avg_volume20 * .8))
        short = ((f.ema9 < f.ema21) & (f.ema21 < f.ema21.shift(3)) &
                 (f.high >= f.ema9) & (c < f.ema9) & (c < f.open) &
                 (f.volume >= f.avg_volume20 * .8))
    elif model == "BB20 Range Bounce":
        flat = (abs(f.ema9 - f.ema21) / c < .0035)
        long = flat & (c.shift(1) < f.bb_lower.shift(1)) & (c > f.bb_lower)
        short = flat & (c.shift(1) > f.bb_upper.shift(1)) & (c < f.bb_upper)
    elif model == "Breakout + Retest":
        volume_ok = f.volume > f.avg_volume20 * 1.1
        prior_up = c.shift(1) > f.prev_high20.shift(1)
        prior_down = c.shift(1) < f.prev_low20.shift(1)
        long = (prior_up & (f.low <= f.prev_high20.shift(1) * 1.0015) &
                (c >= f.prev_high20.shift(1)) & volume_ok)
        short = (prior_down & (f.high >= f.prev_low20.shift(1) * .9985) &
                 (c <= f.prev_low20.shift(1)) & volume_ok)
    else:
        prior_sweep_low = ((f.low.shift(1) < f.prev_low20.shift(1)) &
                           (c.shift(1) > f.prev_low20.shift(1)))
        prior_sweep_high = ((f.high.shift(1) > f.prev_high20.shift(1)) &
                            (c.shift(1) < f.prev_high20.shift(1)))
        long = prior_sweep_low & (c > f.open) & (c > c.shift(1))
        short = prior_sweep_high & (c < f.open) & (c < c.shift(1))
    out = pd.Series(np.where(long.fillna(False), 1,
                             np.where(short.fillna(False) & allow_short, -1, 0)),
                    index=f.index, dtype=int)
    return out


@dataclass(frozen=True)
class ResearchSettings:
    fee_each_side_bps: float = 10.0
    slippage_each_side_bps: float = 5.0
    risk_pct: float = 0.5
    max_bars: int = 12

    def validate(self) -> None:
        if not (0 <= self.fee_each_side_bps <= 100 and
                0 <= self.slippage_each_side_bps <= 100 and
                0 < self.risk_pct <= 2 and 3 <= self.max_bars <= 96):
            raise ValueError("Research settings out of bounds")

    @property
    def round_trip_bps(self) -> float:
        return 2 * (self.fee_each_side_bps + self.slippage_each_side_bps)


def simulate(f: pd.DataFrame, signals: pd.Series, settings: ResearchSettings,
             start: int, end: int) -> pd.DataFrame:
    """Sequential one-position paper replay; next open, stop-first, after-cost."""
    settings.validate()
    if not 100 <= start < end <= len(f):
        raise ValueError("Invalid test window")
    events = []
    i = start
    while i + settings.max_bars < end:
        side = int(signals.iloc[i - 1])
        if side == 0:
            i += 1
            continue
        entry = float(f.open.iloc[i])
        atr = float(f.atr.iloc[i - 1])
        if not (math.isfinite(atr) and atr > 0 and entry > 0):
            i += 1
            continue
        distance = max(1.5 * atr, .003 * entry)
        if distance / entry > .04:
            i += 1
            continue
        stop = entry - side * distance
        target = entry + side * 2 * distance
        reason = "TIME"
        exit_price = float(f.close.iloc[i + settings.max_bars - 1])
        elapsed = settings.max_bars
        for j in range(i, i + settings.max_bars):
            row = f.iloc[j]
            # A gap beyond stop is filled at the worse opening price.
            if (row.low <= stop if side == 1 else row.high >= stop):
                exit_price = min(float(row.open), stop) if side == 1 else max(float(row.open), stop)
                reason, elapsed = "STOP", j-i+1
                break
            if (row.high >= target if side == 1 else row.low <= target):
                exit_price, reason, elapsed = target, "TARGET", j-i+1
                break
        gross = side * (exit_price / entry - 1)
        net = gross - settings.round_trip_bps / 10_000
        # No leverage; capital allocation is capped at 100%.
        allocation = min(1.0, (settings.risk_pct / 100) / (distance / entry))
        events.append({"time": f.index[i], "side": "LONG" if side == 1 else "SHORT",
                       "entry": entry, "exit": exit_price, "reason": reason,
                       "gross_pct": gross * 100, "net_pct": net * 100,
                       "capital_return_pct": net * allocation * 100})
        i += elapsed
    return pd.DataFrame(events)


def summarize(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0, "win_rate": None, "mean_net_pct": None,
                "profit_factor": None, "total_capital_pct": 0.0, "drawdown_pct": 0.0}
    returns = trades.net_pct.astype(float)
    gains, losses = returns.clip(lower=0).sum(), -returns.clip(upper=0).sum()
    equity = (1 + trades.capital_return_pct.astype(float) / 100).cumprod()
    curve = pd.concat([pd.Series([1.0]), equity.reset_index(drop=True)], ignore_index=True)
    dd = (1 - curve / curve.cummax()).max() * 100
    return {"trades": int(len(trades)), "win_rate": float((returns > 0).mean() * 100),
            "mean_net_pct": float(returns.mean()),
            "profit_factor": float(gains / losses) if losses > 0 else (None if gains == 0 else math.inf),
            "total_capital_pct": float((equity.iloc[-1] - 1) * 100),
            "drawdown_pct": float(dd)}


def research_report(data: pd.DataFrame, settings: ResearchSettings,
                    *, allow_short: bool) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    """Fixed-rule chronological train/holdout; no threshold fitted to holdout."""
    f = indicators(data)
    cut = int(len(f) * .7)
    out, raw = [], {}
    for name in MODELS:
        sig = model_signals(f, name, allow_short)
        train = simulate(f, sig, settings, 100, cut)
        test = simulate(f, sig, settings, cut, len(f))
        raw[name] = {"train": train, "holdout": test, "signals": sig}
        for period, tr in (("Train 70%", train), ("Holdout 30%", test)):
            metrics = summarize(tr)
            # A positive holdout with few trades is not proof of edge.
            if metrics["trades"] == 0:
                verdict = "NO TRADES · NOT VALIDATED"
            elif (metrics["mean_net_pct"] or 0) <= 0 or (
                    metrics["profit_factor"] is not None and metrics["profit_factor"] < 1):
                verdict = "NEGATIVE HOLDOUT · NO EDGE SHOWN"
            elif metrics["trades"] < 100:
                verdict = "LOW SAMPLE · PAPER ONLY"
            elif (metrics["profit_factor"] is not None and
                  metrics["profit_factor"] >= 1.2 and
                  metrics["drawdown_pct"] <= 10):
                verdict = "RESEARCH PASS · PAPER ONLY"
            else:
                verdict = "RESEARCH FAIL"
            out.append({"Model": name, "Window": period, "Trades": metrics["trades"],
                        "Win %": metrics["win_rate"], "Mean net/trade %": metrics["mean_net_pct"],
                        "Profit factor": metrics["profit_factor"],
                        "Capital return %": metrics["total_capital_pct"],
                        "Max closed-trade DD %": metrics["drawdown_pct"],
                        "Verdict": verdict if period.startswith("Holdout") else "TRAIN · NOT DECISION"})
    return pd.DataFrame(out), raw, f
