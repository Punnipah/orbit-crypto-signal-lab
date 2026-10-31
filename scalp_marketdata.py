"""Strict, read-only venue-native Binance TH Spot / Binance USD-M market data.

Binance TH Spot and Binance Global USD-M perpetuals are distinct venues.
An HTTP 451/403/429 on Futures is an unavailable signal, never a reason to
substitute Spot prices, spot OHLCs or another exchange for a Futures READY.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


SPOT_URL = "https://api.binance.th"
FUTURES_URL = "https://fapi.binance.com"
PERIOD = {"1m": 60_000, "5m": 300_000, "15m": 900_000}
SYMBOL = re.compile(r"[A-Z0-9]{2,18}USDT\Z")


class MarketDataError(RuntimeError):
    pass


@dataclass(frozen=True)
class Instrument:
    symbol: str
    min_qty: Decimal
    step_qty: Decimal
    min_notional: Decimal
    tick_price: Decimal


@dataclass(frozen=True)
class MarketSnapshot:
    venue: str
    symbol: str
    frames: dict[str, pd.DataFrame]
    bid: float
    ask: float
    bid_depth_usdt: float
    ask_depth_usdt: float
    instrument: Instrument
    checked_at: datetime

    @property
    def spread_bps(self) -> float:
        return (self.ask - self.bid) / ((self.ask + self.bid) / 2) * 10_000


def _get_json(base: str, route: str, params: dict | None = None) -> object:
    url = base + route + ("?" + urlencode(params) if params else "")
    request = Request(url, headers={"User-Agent": "OrbitScalpSignal/5.6 (public read-only)"})
    try:
        with urlopen(request, timeout=12) as response:
            if response.status != 200:
                raise MarketDataError(f"Market endpoint HTTP {response.status}")
            return json.load(response)
    except HTTPError as exc:
        # HTTP 451 is a location/access restriction, not an invitation to route
        # around the exchange's policy or silently change trading venue.
        raise MarketDataError(f"{base} HTTP {exc.code} (venue unavailable)") from None
    except (URLError, TimeoutError, OSError):
        raise MarketDataError(f"{base} network/timeout") from None
    except (ValueError, TypeError):
        raise MarketDataError(f"{base} JSON ไม่ถูกต้อง") from None


def venue_base(venue: str) -> tuple[str, str]:
    if venue == "BINANCE_TH_SPOT":
        return SPOT_URL, "/api/v1"
    if venue == "BINANCE_GLOBAL_USDM":
        return FUTURES_URL, "/fapi/v1"
    raise MarketDataError("ไม่รองรับตลาดที่ระบุ")


def get_exchange_catalog(venue: str) -> dict[str, Instrument]:
    base, prefix = venue_base(venue)
    payload = _get_json(base, prefix + "/exchangeInfo")
    if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
        raise MarketDataError("exchangeInfo format ผิด")
    catalog: dict[str, Instrument] = {}
    for row in payload["symbols"]:
        if not isinstance(row, dict) or not isinstance(row.get("symbol"), str):
            continue
        symbol = row["symbol"]
        if not SYMBOL.fullmatch(symbol) or row.get("status") != "TRADING":
            continue
        if venue == "BINANCE_GLOBAL_USDM" and (row.get("contractType") != "PERPETUAL"
                                                     or row.get("quoteAsset") != "USDT"):
            continue
        filters = {f.get("filterType"): f for f in row.get("filters", []) if isinstance(f, dict)}
        lot = filters.get("LOT_SIZE", {})
        # Futures may specify separate MARKET_LOT_SIZE; this is an indicative
        # sizing preview, never an exchange order.
        minimum = filters.get("MIN_NOTIONAL", filters.get("NOTIONAL", {}))
        try:
            instr = Instrument(symbol=symbol,
                               min_qty=Decimal(str(lot["minQty"])),
                               step_qty=Decimal(str(lot["stepSize"])),
                               min_notional=Decimal(str(minimum.get("minNotional", minimum.get("notional")))),
                               tick_price=Decimal(str(filters["PRICE_FILTER"]["tickSize"])))
            if any(v <= 0 or not v.is_finite() for v in
                   (instr.min_qty, instr.step_qty, instr.min_notional, instr.tick_price)):
                continue
            catalog[symbol] = instr
        except (KeyError, ValueError, InvalidOperation, TypeError):
            continue
    if not catalog:
        raise MarketDataError("ไม่มีคู่เหรียญพร้อมกฎซื้อขายที่ตรวจสอบได้")
    return catalog


def parse_closed_klines(rows: object, interval: str, now: datetime) -> pd.DataFrame:
    if interval not in PERIOD or now.tzinfo is None or not isinstance(rows, list):
        raise MarketDataError("Kline/timeframe ไม่ถูกต้อง")
    if len(rows) < 60:
        raise MarketDataError(f"{interval}: ข้อมูลไม่พอ 60 แท่ง")
    parsed = []
    for r in rows:
        if not isinstance(r, (list, tuple)) or len(r) < 11:
            raise MarketDataError(f"{interval}: OHLC array ไม่ครบ")
        try:
            opened, closed = int(r[0]), int(r[6])
            o, h, l, c, vol, taker = map(float, (r[1], r[2], r[3], r[4], r[5], r[9]))
        except (ValueError, TypeError, OverflowError):
            raise MarketDataError(f"{interval}: ตัวเลขผิด") from None
        if (not all(map(math.isfinite, (o, h, l, c, vol, taker)))
                or min(o, h, l, c) <= 0 or vol < 0 or taker < 0 or taker > vol * 1.00001
                or h < max(o, l, c) or l > min(o, h, c)
                or closed < opened or closed > opened + PERIOD[interval]):
            raise MarketDataError(f"{interval}: ค่า OHLC/volume ไม่สมเหตุผล")
        parsed.append((opened, o, h, l, c, vol, taker))
    frame = pd.DataFrame(parsed, columns=["open_ms", "open", "high", "low", "close", "volume", "taker_buy"])
    if frame.open_ms.duplicated().any() or not frame.open_ms.is_monotonic_increasing:
        raise MarketDataError(f"{interval}: แท่งซ้ำหรือเวลาย้อนกลับ")
    now_ms = int(now.timestamp() * 1000)
    frame = frame.loc[frame.open_ms + PERIOD[interval] <= now_ms].copy()
    if len(frame) < 55:
        raise MarketDataError(f"{interval}: แท่งปิดไม่พอ")
    if (frame.open_ms.diff().tail(55).dropna() != PERIOD[interval]).any():
        raise MarketDataError(f"{interval}: มีช่องว่างแท่งเทียน")
    last_closed_ms = int(frame.open_ms.iloc[-1]) + PERIOD[interval]
    if not 0 <= now_ms - last_closed_ms <= PERIOD[interval] + 45_000:
        raise MarketDataError(f"{interval}: ข้อมูลเก่าหรือเวลาตลาดผิด")
    frame.index = pd.to_datetime(frame.open_ms, unit="ms", utc=True)
    return frame


def parse_quote(payload: object, symbol: str) -> tuple[float, float]:
    if not isinstance(payload, dict) or payload.get("symbol") != symbol:
        raise MarketDataError("Bid/Ask symbol mismatch")
    try:
        bid, ask = float(payload["bidPrice"]), float(payload["askPrice"])
        bid_qty, ask_qty = float(payload["bidQty"]), float(payload["askQty"])
    except (ValueError, TypeError, KeyError):
        raise MarketDataError("Bid/Ask ไม่ครบ") from None
    if (not all(map(math.isfinite, (bid, ask, bid_qty, ask_qty))) or
            bid <= 0 or ask <= bid or bid_qty <= 0 or ask_qty <= 0):
        raise MarketDataError("Bid/Ask ผิดปกติหรือไม่มีสภาพคล่อง")
    return bid, ask


def parse_depth(payload: object) -> tuple[float, float]:
    if not isinstance(payload, dict):
        raise MarketDataError("Order book format ผิด")
    out = []
    for name in ("bids", "asks"):
        levels = payload.get(name)
        if not isinstance(levels, list) or not levels:
            raise MarketDataError("Order book ว่าง")
        result = 0.0
        for row in levels[:20]:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                raise MarketDataError("Order book level ผิด")
            try:
                p, q = float(row[0]), float(row[1])
            except (TypeError, ValueError):
                raise MarketDataError("Order book ตัวเลขผิด") from None
            if not math.isfinite(p * q) or p <= 0 or q < 0:
                raise MarketDataError("Order book ราคา/จำนวนผิด")
            result += p * q
        out.append(result)
    if min(out) <= 0:
        raise MarketDataError("Order book ไม่มีสภาพคล่อง")
    return out[0], out[1]


def fetch_snapshot(venue: str, symbol: str, *, catalog: dict[str, Instrument] | None = None,
                   now: datetime | None = None) -> MarketSnapshot:
    if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
        raise MarketDataError("Symbol ต้องเป็นคู่ USDT ที่ถูกต้อง")
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise MarketDataError("Time zone ไม่ถูกต้อง")
    base, prefix = venue_base(venue)
    market = catalog if catalog is not None else get_exchange_catalog(venue)
    if symbol not in market:
        raise MarketDataError(f"{symbol} ไม่ใช่คู่ TRADING ที่ตรวจขั้นต่ำได้ใน {venue}")
    stamp = _get_json(base, prefix + "/time")
    try:
        exchange_ms = int(stamp["serverTime"])
    except (TypeError, ValueError, KeyError):
        raise MarketDataError("Exchange time ไม่ถูกต้อง") from None
    if abs(exchange_ms - int(now.timestamp() * 1000)) > 60_000:
        raise MarketDataError("นาฬิกา runner/ตลาดต่างกันเกิน 60 วินาที")
    frames = {}
    for tf in ("15m", "5m", "1m"):
        rows = _get_json(base, prefix + "/klines", {"symbol": symbol, "interval": tf, "limit": 140})
        frames[tf] = parse_closed_klines(rows, tf, now)
    quote = _get_json(base, prefix + "/ticker/bookTicker", {"symbol": symbol})
    bid, ask = parse_quote(quote, symbol)
    depth = _get_json(base, prefix + "/depth", {"symbol": symbol, "limit": 20})
    bid_depth, ask_depth = parse_depth(depth)
    # Avoid a correct but old candle series paired with a wildly different
    # quote. Volatile gaps are not an entry opportunity when data disagree.
    last_close = float(frames["1m"].close.iloc[-1])
    if abs((ask + bid) / (2 * last_close) - 1) > 0.035:
        raise MarketDataError("Quote แตกต่างจากแท่ง 1m ล่าสุดผิดปกติ")
    return MarketSnapshot(venue, symbol, frames, bid, ask, bid_depth, ask_depth, market[symbol], now)
