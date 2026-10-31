"""Independent, public Bitget USDT-perpetual Futures data for Orbit Scalp.

Never called Binance Futures; never substitute its prices into a Binance
observation. Bitget 1m candles omit aggressor volume. We use public trade
``side=buy/sell`` as a separately labelled volume proxy, not an exchange-
certified taker/aggressor classification. Only complete reconciled 1m bars
receive that proxy. Missing or inconsistent fills => NaN => no READY.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from scalp_marketdata import (Instrument, MarketDataError, MarketSnapshot, PERIOD,
                              SYMBOL, parse_depth, parse_quote)


BASE = "https://api.bitget.com"
ROOT = "/api/v3/market/"
CATEGORY = "USDT-FUTURES"


def _api(path: str, params: dict | None = None):
    url = BASE + ROOT + path + ("?" + urlencode(params) if params else "")
    req = Request(url, headers={"User-Agent": "OrbitScalpBitget/5.7 public read-only"})
    try:
        with urlopen(req, timeout=12) as res:
            raw = json.load(res)
    except HTTPError as exc:
        raise MarketDataError(f"Bitget Public Futures HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise MarketDataError("Bitget Public Futures timeout/network") from None
    except (ValueError, TypeError):
        raise MarketDataError("Bitget Public Futures invalid JSON") from None
    if (not isinstance(raw, dict) or raw.get("code") != "00000"
            or "data" not in raw):
        raise MarketDataError("Bitget Public Futures response rejected")
    return raw["data"]


def get_bitget_catalog() -> dict[str, Instrument]:
    rows = _api("instruments", {"category": CATEGORY})
    if not isinstance(rows, list):
        raise MarketDataError("Bitget instruments invalid")
    instruments = {}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("symbol"), str)
                or not SYMBOL.fullmatch(row["symbol"]) or row.get("status") != "online"
                or row.get("type") != "perpetual" or row.get("quoteCoin") != "USDT"):
            continue
        try:
            # Bitget quantityMultiplier/priceMultiplier are actual increments,
            # not the number of decimal places. Do not infer from precision.
            tick = Decimal(str(row["priceMultiplier"]))
            step = Decimal(str(row["quantityMultiplier"]))
            minimum = Decimal(str(row["minOrderQty"]))
            notional = Decimal(str(row["minOrderAmount"]))
            fee_pct = float(row["takerFeeRate"]) * 100
            if (not all(v.is_finite() and v > 0 for v in (tick, step, minimum, notional))
                    or not math.isfinite(fee_pct) or not 0.01 <= fee_pct <= 1):
                continue
            instruments[row["symbol"]] = Instrument(row["symbol"], minimum, step,
                                                      notional, tick, fee_pct)
        except (ValueError, TypeError, KeyError, InvalidOperation):
            continue
    if not instruments:
        raise MarketDataError("Bitget ไม่มีสัญญา USDT Perpetual ที่ตรวจขั้นต่ำได้")
    return instruments


def parse_bitget_candles(rows: object, interval: str, now: datetime) -> pd.DataFrame:
    if interval not in PERIOD or not isinstance(rows, list) or len(rows) < 60:
        raise MarketDataError(f"Bitget {interval} candles insufficient")
    parsed = []
    for item in rows:
        if not isinstance(item, list) or len(item) < 7:
            raise MarketDataError("Bitget candle format invalid")
        try:
            opened = int(item[0])
            o, h, lo, c, v = map(float, item[1:6])
        except (ValueError, TypeError, OverflowError):
            raise MarketDataError("Bitget candle numeric invalid") from None
        if (not all(map(math.isfinite, (o, h, lo, c, v)))
                or min(o, h, lo, c) <= 0 or v < 0
                or h < max(o, lo, c) or lo > min(o, h, c)):
            raise MarketDataError("Bitget OHLC impossible")
        parsed.append((opened, o, h, lo, c, v))
    frame = pd.DataFrame(parsed, columns=["open_ms", "open", "high", "low", "close", "volume"])
    frame = frame.sort_values("open_ms")
    if frame.open_ms.duplicated().any():
        raise MarketDataError("Bitget duplicate candle")
    frame = frame.loc[frame.open_ms + PERIOD[interval] <= int(now.timestamp() * 1000)].copy()
    if len(frame) < 55:
        raise MarketDataError("Bitget closed candle history incomplete")
    if (frame.open_ms.diff().tail(55).dropna() != PERIOD[interval]).any():
        raise MarketDataError("Bitget candle gap")
    lag = int(now.timestamp() * 1000) - (int(frame.open_ms.iloc[-1]) + PERIOD[interval])
    if not 0 <= lag <= PERIOD[interval] + 45_000:
        raise MarketDataError("Bitget candle stale")
    frame["taker_buy"] = float("nan")
    frame.index = pd.to_datetime(frame.open_ms, unit="ms", utc=True)
    return frame


def reconcile_recent_fills(frame: pd.DataFrame, raw: object, now: datetime) -> int:
    """Fill the buy-side public-trade proxy for fully reconciled 1m bars.

    The public endpoint returns at most 100 latest trades. If they don't span
    an entire bar or differ materially from exchange kline base volume, the
    bar remains NaN. Zero-volume bars never qualify.
    """
    if not isinstance(raw, list) or not raw or len(raw) > 100:
        raise MarketDataError("Bitget public fills missing/invalid")
    fills = []
    for row in raw:
        if not isinstance(row, dict) or row.get("side") not in ("buy", "sell"):
            raise MarketDataError("Bitget fills missing side")
        try:
            timestamp = int(row["ts"])
            size = float(row["size"])
        except (ValueError, TypeError, KeyError):
            raise MarketDataError("Bitget fills invalid timestamp/size") from None
        if not math.isfinite(size) or size <= 0:
            raise MarketDataError("Bitget fills invalid size")
        fills.append((timestamp, size, row["side"]))
    earliest, latest = min(x[0] for x in fills), max(x[0] for x in fills)
    if latest > int(now.timestamp() * 1000) + 60_000:
        raise MarketDataError("Bitget fill timestamp future-dated")
    complete = 0
    for idx in range(max(0, len(frame) - 5), len(frame)):
        opened = int(frame.open_ms.iloc[idx])
        closed = opened + 60_000
        if earliest > opened or latest < closed:
            continue
        trades = [(size, side) for ts, size, side in fills if opened <= ts < closed]
        vol = float(frame.volume.iloc[idx])
        if vol <= 0 or not trades:
            continue
        covered = sum(size for size, _ in trades)
        if not 0.95 <= covered / vol <= 1.05:
            continue
        buy = sum(size for size, side in trades if side == "buy")
        frame.iloc[idx, frame.columns.get_loc("taker_buy")] = min(vol, buy)
        complete += 1
    return complete


def fetch_bitget_snapshot(symbol: str, *, catalog: dict[str, Instrument] | None = None,
                          now: datetime | None = None) -> MarketSnapshot:
    if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
        raise MarketDataError("Bitget symbol invalid")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise MarketDataError("Timezone missing")
    instruments = catalog if catalog is not None else get_bitget_catalog()
    if symbol not in instruments:
        raise MarketDataError(f"Bitget {symbol} not online or minimum order unknown")
    stamp = _api("time")
    try:
        server_ms = int(stamp["serverTime"])
    except (TypeError, ValueError, KeyError):
        raise MarketDataError("Bitget server time missing") from None
    if abs(server_ms - int(now.timestamp() * 1000)) > 60_000:
        raise MarketDataError("Bitget runner clock skew")
    p = {"category": CATEGORY, "symbol": symbol}
    frames = {tf: parse_bitget_candles(
        _api("candles", {**p, "interval": tf, "limit": 140}), tf, now)
        for tf in ("15m", "5m", "1m")}
    tickers = _api("tickers", p)
    if (not isinstance(tickers, list) or len(tickers) != 1
            or not isinstance(tickers[0], dict) or tickers[0].get("symbol") != symbol):
        raise MarketDataError("Bitget ticker mismatch")
    tick = tickers[0]
    bid, ask = parse_quote({"symbol": symbol, "bidPrice": tick.get("bid1Price"),
                            "askPrice": tick.get("ask1Price"), "bidQty": tick.get("bid1Size"),
                            "askQty": tick.get("ask1Size")}, symbol)
    if abs(int(tick.get("ts", 0)) - int(now.timestamp() * 1000)) > 30_000:
        raise MarketDataError("Bitget quote stale")
    try:
        mark, funding = float(tick["markPrice"]), float(tick["fundingRate"])
    except (ValueError, TypeError, KeyError):
        raise MarketDataError("Bitget mark price / funding missing") from None
    if (not math.isfinite(mark) or mark <= 0 or not math.isfinite(funding)
            or abs(mark / ((bid + ask) / 2) - 1) > 0.005
            or abs(funding) > 0.003):
        raise MarketDataError("Bitget mark/last deviation or funding too large")
    raw_depth = _api("orderbook", {**p, "limit": 20})
    if not isinstance(raw_depth, dict):
        raise MarketDataError("Bitget depth invalid")
    bid_depth, ask_depth = parse_depth({"bids": raw_depth.get("b"),
                                        "asks": raw_depth.get("a")})
    if abs(((bid + ask) / 2) / float(frames["1m"].close.iloc[-1]) - 1) > 0.035:
        raise MarketDataError("Bitget price differs from last 1m close")
    fills = _api("fills", {**p, "limit": 100})
    reconcile_recent_fills(frames["1m"], fills, now)
    # Missing coverage is NOT a network failure: the engine can show WATCH,
    # but a NaN 1m taker flow cannot pass either LONG/SHORT confirmation.
    return MarketSnapshot("BITGET_USDT_FUTURES", symbol, frames, bid, ask, bid_depth,
                          ask_depth, instruments[symbol], now)
