"""Read-only public Binance market data (no account, no orders, no API key)."""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


BASE_URL = "https://data-api.binance.vision/api/v3"
TIMEFRAMES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
HIGHER_TIMEFRAME = {"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1d"}
POPULAR_QUOTES = ["USDT", "USDC", "FDUSD", "BTC", "ETH", "EUR", "TRY", "BRL"]
COIN_ALIASES = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "ripple": "XRP",
                "dogecoin": "DOGE", "cardano": "ADA", "chainlink": "LINK"}


class PublicDataError(RuntimeError):
    pass


def _get_json(endpoint: str, params: dict | None = None):
    qs = "?" + urlencode(params) if params else ""
    request = Request(BASE_URL + endpoint + qs, headers={"User-Agent": "OrbitSignalLab/2.0 read-only"})
    try:
        with urlopen(request, timeout=25) as res:
            return json.load(res)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise PublicDataError(f"ข้อมูลตลาดสาธารณะไม่พร้อมใช้งาน: {exc}") from exc


def fetch_catalog() -> list[dict]:
    payload = _get_json("/exchangeInfo")
    result = []
    for item in payload.get("symbols", []):
        if item.get("status") != "TRADING" or not item.get("isSpotTradingAllowed", False):
            continue
        result.append({"symbol": item["symbol"], "base": item["baseAsset"], "quote": item["quoteAsset"]})
    if not result:
        raise PublicDataError("ไม่พบคู่เหรียญ Spot ที่ซื้อขายอยู่")
    return sorted(result, key=lambda x: x["symbol"])


def search_catalog(catalog: list[dict], query: str, quote: str = "USDT") -> list[dict]:
    q = query.strip().upper()
    q = COIN_ALIASES.get(q.lower(), q)
    matches = [entry for entry in catalog if (quote == "ทั้งหมด" or entry["quote"] == quote)
               and (not q or q in entry["symbol"] or q in entry["base"])]
    return matches


def fetch_spot_last_price(symbol: str) -> tuple[float, datetime]:
    """Fetch public last-traded Spot price, with request time (not trade time).

    Binance's symbol-price ticker provides no trade timestamp. A successful
    response cannot prove liquidity or that the underlying trade is recent.
    """
    if not symbol.isascii() or not symbol.isalnum() or len(symbol) > 24:
        raise PublicDataError("คู่เหรียญไม่ถูกต้อง")
    response = _get_json("/ticker/price", {"symbol": symbol})
    if not isinstance(response, dict) or response.get("symbol") != symbol:
        raise PublicDataError("ราคา Spot ล่าสุดไม่ตรงคู่เหรียญ")
    try:
        price = float(response["price"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PublicDataError("ราคา Spot ล่าสุดไม่ใช่ตัวเลข") from exc
    if not math.isfinite(price) or price <= 0:
        raise PublicDataError("ราคา Spot ล่าสุดผิดปกติ")
    return price, datetime.now(timezone.utc)


def parse_klines(rows: list) -> pd.DataFrame:
    if not rows:
        raise PublicDataError("ไม่มีข้อมูลแท่งเทียนในช่วงที่เลือก")
    f = pd.DataFrame(rows)
    if f.shape[1] < 7:
        raise PublicDataError("รูปแบบข้อมูลแท่งเทียนไม่ถูกต้อง")
    # Binance full klines also expose taker-buy volume at index 9.
    # Earlier synthetic/third-party test rows can have only seven fields:
    # missing aggressor data must remain NaN, never be fabricated as 50/50.
    has_taker = f.shape[1] >= 11
    f = f.iloc[:, [0, 1, 2, 3, 4, 5, 6] + ([9] if has_taker else [])].copy()
    f.columns = ["open_ms", "open", "high", "low", "close", "volume", "close_ms"] + (["taker_buy_base"] if has_taker else [])
    if not has_taker:
        f["taker_buy_base"] = float("nan")
    f["open_ms"] = pd.to_numeric(f["open_ms"], errors="raise").astype("int64")
    f["close_ms"] = pd.to_numeric(f["close_ms"], errors="raise").astype("int64")
    for col in ("open", "high", "low", "close", "volume", "taker_buy_base"):
        f[col] = pd.to_numeric(f[col], errors="raise").astype(float)
    f.index = pd.to_datetime(f["open_ms"], unit="ms", utc=True)
    f.index.name = "timestamp_utc"
    f = f.drop(columns=["open_ms", "close_ms"])
    f = f[~f.index.duplicated(keep="last")].sort_index()
    if (f[["open", "high", "low", "close"]] <= 0).any().any() or (f["volume"] < 0).any():
        raise PublicDataError("พบราคาหรือ Volume ผิดปกติ")
    if ((f["taker_buy_base"] < 0) | (f["taker_buy_base"] > f["volume"] * (1 + 1e-8))).any():
        raise PublicDataError("Taker Buy Volume อยู่นอกช่วง Volume รวม")
    return f


def fetch_klines(symbol: str, timeframe: str, candles: int = 3000) -> pd.DataFrame:
    """Fetch up to 10k *completed* candles in backward pages; all in UTC."""
    if not symbol.isascii() or not symbol.isalnum() or len(symbol) > 24:
        raise PublicDataError("รหัสคู่เหรียญไม่ถูกต้อง")
    if timeframe not in TIMEFRAMES:
        raise PublicDataError("Timeframe ไม่ถูกต้อง")
    if not 250 <= candles <= 10000:
        raise PublicDataError("เลือกประวัติ 250–10,000 แท่ง")
    step_ms = TIMEFRAMES[timeframe] * 60_000
    current_ms = int(time.time() * 1000)
    # Always end at the close of the last committed candle.
    end_ms = (current_ms // step_ms) * step_ms - 1
    output = []
    remaining = candles
    while remaining > 0:
        limit = min(1000, remaining)
        page = _get_json("/klines", {"symbol": symbol, "interval": timeframe,
                                    "limit": limit, "endTime": end_ms})
        if not isinstance(page, list) or not page:
            break
        # Binance kline format has opening time at [0].
        output.extend(page)
        remaining -= len(page)
        oldest_ms = int(page[0][0])
        if oldest_ms >= end_ms or len(page) < limit:
            break
        end_ms = oldest_ms - 1
    data = parse_klines(output)
    # Defensive check if an upstream service ever returns an unclosed candle.
    data = data.loc[(data.index.view("int64") // 1_000_000 + step_ms) <= current_ms]
    if len(data) < 250:
        raise PublicDataError(f"{symbol} มีข้อมูลปิดแท่งเพียง {len(data)} แท่ง (ต้องมีอย่างน้อย 250)")
    return data.tail(candles)


def count_time_gaps(data: pd.DataFrame, timeframe: str) -> int:
    expected = TIMEFRAMES[timeframe] * 60
    diffs = data.index.to_series().diff().dt.total_seconds().dropna()
    return int((diffs != expected).sum())
