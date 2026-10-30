"""Bybit public linear-USDT *watch-only* backup for Binance Futures outages.

Bybit V5 kline does not expose historical taker buy base quantity. Therefore
this adapter must NEVER be used with require_taker_flow=True or emit READY.
"""

from __future__ import annotations

from datetime import datetime
import json
import math
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from futures_daytrade import FuturesDataError, TIMEFRAME_MINUTES


BASE = "https://api.bybit.com"
TF = {"15m": "15", "1h": "60", "4h": "240"}
SYMBOL = re.compile(r"[A-Z0-9]{2,20}USDT\Z")


def _read(endpoint: str, params: dict) -> dict:
    url = BASE + endpoint + "?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "OrbitFuturesBackup/5.2 read-only"})
    try:
        with urlopen(req, timeout=18) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise FuturesDataError(f"Bybit linear API HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise FuturesDataError("Bybit linear API network/timeout") from None
    except (ValueError, TypeError):
        raise FuturesDataError("Bybit linear API JSON ไม่ถูกต้อง") from None
    if not isinstance(payload, dict) or payload.get("retCode") != 0:
        raise FuturesDataError("Bybit linear API ไม่พร้อมหรือส่งรหัสผิดพลาด")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise FuturesDataError("Bybit linear API ไม่มี result")
    # Server time is top-level in V5; keep it for freshness checks on tickers.
    server_time = payload.get("time")
    if isinstance(server_time, (int, str)):
        result["_orbit_server_time"] = server_time
    return result


def fetch_backup_pair(requested: str) -> str:
    """Verify a trading linear perpetual contract; never guess token multipliers."""
    if not SYMBOL.fullmatch(requested):
        raise FuturesDataError("Bybit Symbol ไม่ถูกต้อง")
    candidates = (requested, "1000" + requested)
    for candidate in candidates:
        result = _read("/v5/market/instruments-info", {"category": "linear", "symbol": candidate})
        rows = result.get("list", [])
        for row in rows if isinstance(rows, list) else []:
            if (isinstance(row, dict) and row.get("symbol") == candidate
                    and row.get("status") == "Trading" and row.get("contractType") == "LinearPerpetual"
                    and row.get("quoteCoin") == "USDT"):
                return candidate
    raise FuturesDataError(f"Bybit ไม่พบสัญญา Perpetual สำหรับ {requested}")


def fetch_backup_klines(symbol: str, timeframe: str, *, now: datetime) -> pd.DataFrame:
    if not SYMBOL.fullmatch(symbol) or timeframe not in TF or now.tzinfo is None:
        raise FuturesDataError("Bybit timeframe/symbol/clock ไม่ถูกต้อง")
    result = _read("/v5/market/kline", {"category": "linear", "symbol": symbol,
                                         "interval": TF[timeframe], "limit": 250})
    candles = result.get("list")
    if not isinstance(candles, list) or len(candles) < 101:
        raise FuturesDataError("Bybit Futures candles ไม่เพียงพอ")
    rows = []
    interval_ms = TIMEFRAME_MINUTES[timeframe] * 60_000
    now_ms = int(now.timestamp() * 1000)
    for item in candles:
        if not isinstance(item, list) or len(item) < 6:
            raise FuturesDataError("Bybit Futures candle format ไม่ถูกต้อง")
        opened = int(item[0])
        if opened + interval_ms > now_ms:
            continue  # never interpret an unclosed bar
        rows.append((opened, *(float(v) for v in item[1:6])))
    frame = pd.DataFrame(rows, columns=["opened", "open", "high", "low", "close", "volume"])
    if len(frame) < 100:
        raise FuturesDataError("Bybit closed bars ไม่เพียงพอ")
    frame = frame.sort_values("opened")
    frame.index = pd.to_datetime(frame["opened"], unit="ms", utc=True)
    frame["closed"] = frame["opened"] + interval_ms - 1
    frame["taker_buy"] = float("nan")  # Explicit unavailable evidence; DO NOT fabricate.
    if (frame.index.has_duplicates or
            (frame.index.to_series().diff().dt.total_seconds().tail(30).dropna()
             != TIMEFRAME_MINUTES[timeframe] * 60).any() or
            now_ms - (int(frame["opened"].iloc[-1]) + interval_ms) > 2 * interval_ms):
        raise FuturesDataError("Bybit Futures candles ขาดช่วงหรือไม่สด")
    if (not frame[["open", "high", "low", "close", "volume"]].map(math.isfinite).all().all()
            or (frame[["open", "high", "low", "close"]] <= 0).any().any()
            or (frame["volume"] < 0).any()
            or (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any()
            or (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any()):
        raise FuturesDataError("Bybit Futures OHLC ผิดรูปแบบ")
    return frame


def fetch_backup_ticker(symbol: str, *, now: datetime) -> tuple[float, float, float]:
    if not SYMBOL.fullmatch(symbol) or now.tzinfo is None:
        raise FuturesDataError("Bybit Futures ticker symbol/clock ไม่ถูกต้อง")
    result = _read("/v5/market/tickers", {"category": "linear", "symbol": symbol})
    rows = result.get("list", [])
    if not isinstance(rows, list) or len(rows) != 1 or rows[0].get("symbol") != symbol:
        raise FuturesDataError("Bybit Futures ticker ไม่มีคู่ที่ต้องการ")
    try:
        last, mark, funding = (float(rows[0][key]) for key in ("lastPrice", "markPrice", "fundingRate"))
    except (TypeError, ValueError, KeyError):
        raise FuturesDataError("Bybit Futures mark/funding ไม่พร้อม") from None
    stamp = result.get("_orbit_server_time")
    if not isinstance(stamp, (str, int)):
        raise FuturesDataError("Bybit Futures server time ไม่พร้อม")
    if (not all(math.isfinite(v) for v in (last, mark, funding)) or
            min(last, mark) <= 0 or
            abs(now.timestamp() * 1000 - int(stamp)) > 180_000):
        raise FuturesDataError("Bybit Futures ราคาไม่สมเหตุผลหรือไม่สด")
    return last, mark, funding * 100
