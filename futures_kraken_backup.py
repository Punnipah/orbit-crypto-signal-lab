"""Public Kraken USD-margined perpetual data, exclusively for WATCH-only research.

This venue does not provide historical taker-buy volume through candle API.
Never turn Kraken observations into READY signals or mix venue OHLC/tickers.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from futures_daytrade import FuturesDataError, TIMEFRAME_MINUTES

BASE = "https://futures.kraken.com"
CONTRACTS = {"BTCUSDT": "PF_XBTUSD", "PEPEUSDT": "PF_PEPEUSD",
             "DOGEUSDT": "PF_DOGEUSD"}


def _read(path: str, params: dict | None = None) -> dict:
    url = BASE + path + ("?" + urlencode(params) if params else "")
    req = Request(url, headers={"Accept": "application/json",
                                "User-Agent": "OrbitKrakenPublicMonitor/5.3 read-only"})
    try:
        with urlopen(req, timeout=15) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise FuturesDataError(f"Kraken Futures HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise FuturesDataError("Kraken Futures network/timeout") from None
    except (ValueError, TypeError):
        raise FuturesDataError("Kraken Futures JSON invalid") from None
    if not isinstance(payload, dict) or payload.get("result") == "error":
        raise FuturesDataError("Kraken Futures API unavailable")
    return payload


def _ticker(symbol: str) -> dict:
    payload = _read("/derivatives/api/v3/tickers", {"symbol": symbol})
    rows = payload.get("tickers")
    if not isinstance(rows, list):
        raise FuturesDataError("Kraken ticker list unavailable")
    matches = [x for x in rows if isinstance(x, dict) and x.get("symbol") == symbol
               and x.get("tag") == "perpetual"]
    if len(matches) != 1:
        raise FuturesDataError(f"Kraken perpetual missing: {symbol}")
    return matches[0]


def fetch_kraken_pair(requested: str) -> str:
    """Use an explicit spot-to-USD-perpetual mapping; never guess multipliers."""
    if requested not in CONTRACTS:
        raise FuturesDataError(f"Kraken pair not supported: {requested}")
    symbol = CONTRACTS[requested]
    _ticker(symbol)
    return symbol


def fetch_kraken_klines(symbol: str, timeframe: str, *, now: datetime) -> pd.DataFrame:
    if symbol not in CONTRACTS.values() or timeframe not in TIMEFRAME_MINUTES or now.tzinfo is None:
        raise FuturesDataError("Kraken candle symbol/timeframe invalid")
    payload = _read(f"/api/charts/v1/trade/{symbol}/{timeframe}", {"count": 180})
    candles = payload.get("candles")
    if not isinstance(candles, list):
        raise FuturesDataError("Kraken candles unavailable")
    interval_ms = TIMEFRAME_MINUTES[timeframe] * 60_000
    now_ms = int(now.timestamp() * 1000)
    rows = []
    for item in candles:
        if not isinstance(item, dict):
            raise FuturesDataError("Kraken candle invalid")
        try:
            opened = int(item["time"])
            values = [float(item[k]) for k in ("open", "high", "low", "close", "volume")]
        except (ValueError, TypeError, KeyError):
            raise FuturesDataError("Kraken candle fields invalid") from None
        if opened + interval_ms <= now_ms:
            rows.append((opened, *values))
    frame = pd.DataFrame(rows, columns=["opened", "open", "high", "low", "close", "volume"])
    if len(frame) < 100:
        raise FuturesDataError("Kraken candles insufficient")
    frame = frame.sort_values("opened")
    frame.index = pd.to_datetime(frame["opened"], unit="ms", utc=True)
    frame["closed"] = frame["opened"] + interval_ms - 1
    frame["taker_buy"] = float("nan")
    if (frame.index.has_duplicates or
            (frame.index.to_series().diff().dt.total_seconds().tail(30).dropna()
             != TIMEFRAME_MINUTES[timeframe] * 60).any() or
            now_ms - (int(frame["opened"].iloc[-1]) + interval_ms) > 2 * interval_ms):
        raise FuturesDataError("Kraken candles stale or missing")
    prices = frame[["open", "high", "low", "close", "volume"]]
    if (not prices.map(math.isfinite).all().all() or
            (frame[["open", "high", "low", "close"]] <= 0).any().any() or
            (frame["volume"] < 0).any() or
            (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any() or
            (frame["low"] > frame[["open", "close", "high"]].min(axis=1)).any()):
        raise FuturesDataError("Kraken OHLC invalid")
    return frame


def fetch_kraken_ticker(symbol: str, *, now: datetime) -> tuple[float, float, float]:
    if symbol not in CONTRACTS.values() or now.tzinfo is None:
        raise FuturesDataError("Kraken ticker symbol/clock invalid")
    row = _ticker(symbol)
    try:
        last = float(row["last"])
        mark = float(row["markPrice"])
        # Kraken fundingRate is an *absolute USD amount*, unlike the
        # dimensionless relativeFundingRate required by our percentage checks.
        funding = float(row["relativeFundingRate"])
        stamp = datetime.fromisoformat(row["lastTime"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        raise FuturesDataError("Kraken ticker fields unavailable") from None
    if (not all(math.isfinite(x) for x in (last, mark, funding)) or min(last, mark) <= 0 or
            stamp.tzinfo is None or abs((now - stamp).total_seconds()) > 180):
        raise FuturesDataError("Kraken ticker stale/invalid")
    return last, mark, funding * 100
