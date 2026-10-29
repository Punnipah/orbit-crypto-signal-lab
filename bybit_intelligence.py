"""Best-effort independent Bybit public-market corroboration (no API key).

Spot order-book/trades and linear perpetual OI/funding are always identified
separately; the two instrument types must not be treated as a single book.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


URL = "https://api.bybit.com/v5/market"


@dataclass(frozen=True)
class BybitEvidence:
    symbol: str
    spot_mid: float | None
    spot_bid_depth_share: float | None
    spot_aggressor_buy_share: float | None
    spot_latest_trade_at: datetime | None
    futures_oi_change_24h_pct: float | None
    futures_funding_rate_pct: float | None
    source_status: tuple[str, ...]
    source: str = "Bybit public Spot depth/trades; Bybit USDT linear perpetual OI/funding"


def _as_positive(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("ข้อมูลราคา/ปริมาณ Bybit ผิดรูปแบบ") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError("ข้อมูลราคา/ปริมาณ Bybit ใช้ไม่ได้")
    return number


def _result(payload: object, label: str) -> dict:
    if not isinstance(payload, dict) or payload.get("retCode") != 0:
        detail = payload.get("retMsg", "ไม่มีรายละเอียด") if isinstance(payload, dict) else "ผิดรูปแบบ"
        raise ValueError(f"{label}: Bybit API ไม่พร้อม ({str(detail)[:100]})")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError(f"{label}: ผลข้อมูลไม่ใช่ object")
    return result


def parse_bybit_evidence(symbol: str, spot_book: object, spot_trades: object,
                         futures_oi: object, futures_ticker: object, *, now: datetime) -> BybitEvidence:
    """Partial data are allowed but NEVER replaced with guessed values."""
    if now.tzinfo is None:
        raise ValueError("ต้องมี timezone")
    mid = bid_share = trade_share = oi_pct = funding_pct = None
    latest_trade = None
    status = []

    try:
        res = _result(spot_book, "Spot Book")
        if res.get("s") != symbol:
            raise ValueError("Spot Book symbol ไม่ตรง")
        bids = res.get("b", [])
        asks = res.get("a", [])
        if not bids or not asks:
            raise ValueError("Bid/Ask ว่าง")
        bid, ask = _as_positive(bids[0][0]), _as_positive(asks[0][0])
        if ask <= bid:
            raise ValueError("Bid/Ask เรียงผิด")
        when = datetime.fromtimestamp(int(res["ts"]) / 1000, timezone.utc)
        if not timedelta(0) <= now - when <= timedelta(minutes=3):
            raise ValueError("Order Book ไม่สด")
        mid = (bid + ask) / 2
        near_bid = sum(_as_positive(p)*_as_positive(q) for p, q in bids
                       if float(p) >= mid * .995)
        near_ask = sum(_as_positive(p)*_as_positive(q) for p, q in asks
                       if float(p) <= mid * 1.005)
        if near_bid + near_ask > 0:
            bid_share = near_bid / (near_bid + near_ask)
        status.append("Bybit Spot Book: OK")
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, OSError) as exc:
        status.append(f"Bybit Spot Book: MISSING/STALE ({exc})")
        mid = bid_share = None

    try:
        res = _result(spot_trades, "Spot Trades")
        trades = res.get("list", [])
        if not trades or not isinstance(trades, list):
            raise ValueError("ไม่มี Spot Trades")
        buy = sell = 0.0
        latest_ms = 0
        for trade in trades:
            if trade.get("symbol") != symbol or trade.get("side") not in ("Buy", "Sell"):
                raise ValueError("Spot Trades symbol/side ผิด")
            val = _as_positive(trade["price"]) * _as_positive(trade["size"])
            if trade["side"] == "Buy":
                buy += val
            else:
                sell += val
            latest_ms = max(latest_ms, int(trade["time"]))
        latest_trade = datetime.fromtimestamp(latest_ms / 1000, timezone.utc)
        if not timedelta(0) <= now - latest_trade <= timedelta(minutes=15):
            raise ValueError("รายการเทรดล่าสุดเก่า/เป็นอนาคต")
        if buy + sell > 0:
            trade_share = buy / (buy + sell)
        status.append(f"Bybit Spot Trades: OK ({len(trades)} ดีล)")
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, OSError) as exc:
        status.append(f"Bybit Spot Trades: MISSING/STALE ({exc})")
        trade_share = latest_trade = None

    try:
        res = _result(futures_oi, "Linear OI")
        if res.get("symbol") != symbol or res.get("category") != "linear":
            raise ValueError("Linear OI symbol/category ไม่ตรง")
        history = []
        for point in res.get("list", []):
            stamp = datetime.fromtimestamp(int(point["timestamp"]) / 1000, timezone.utc)
            history.append((stamp, _as_positive(point["openInterest"])))
        if len(history) < 2:
            raise ValueError("OI ประวัติไม่พอ")
        history.sort()
        recent, current = history[-1]
        if not timedelta(0) <= now - recent <= timedelta(hours=3):
            raise ValueError("OI ล่าสุดเก่า")
        target = recent - timedelta(hours=24)
        old_at, previous = min(history, key=lambda p: abs(p[0] - target))
        if abs(old_at - target) > timedelta(hours=1, minutes=30):
            raise ValueError("OI ย้อนหลังไม่ถึง 24 ชม.")
        oi_pct = (current / previous - 1) * 100
        status.append("Bybit USDT Linear OI: OK (เทียบสัญญาเดียวกัน 24h)")
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, OSError) as exc:
        status.append(f"Bybit USDT Linear OI: MISSING ({exc})")

    try:
        res = _result(futures_ticker, "Linear Ticker")
        tickers = [x for x in res.get("list", []) if x.get("symbol") == symbol]
        if not tickers:
            raise ValueError("ไม่พบ Funding ของคู่เหรียญ")
        funding = float(tickers[0]["fundingRate"])
        if not math.isfinite(funding) or abs(funding) > .1:
            raise ValueError("Funding นอกขอบเขต")
        funding_pct = funding * 100  # raw fraction -> percentage
        status.append("Bybit USDT Linear Funding: OK")
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, OSError) as exc:
        status.append(f"Bybit USDT Linear Funding: MISSING ({exc})")

    return BybitEvidence(symbol, mid, bid_share, trade_share, latest_trade,
                         oi_pct, funding_pct, tuple(status))


def _get(path: str, params: dict):
    url = URL + path + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "OrbitPro/Final read-only"})
    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        return {"retCode": -1, "retMsg": str(exc)}


def fetch_bybit_evidence(symbol: str) -> BybitEvidence:
    if not symbol.isascii() or not symbol.isalnum() or not symbol.endswith("USDT"):
        raise ValueError("Bybit อัตโนมัติเฉพาะ USDT ที่มีตลาด Spot และ USDT Linear")
    tasks = (
        ("/orderbook", {"category": "spot", "symbol": symbol, "limit": 100}),
        ("/recent-trade", {"category": "spot", "symbol": symbol, "limit": 60}),
        ("/open-interest", {"category": "linear", "symbol": symbol,
                            "intervalTime": "1h", "limit": 30}),
        ("/tickers", {"category": "linear", "symbol": symbol}),
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(_get, path, args) for path, args in tasks]
        payloads = [f.result() for f in futures]
    return parse_bybit_evidence(symbol, *payloads, now=datetime.now(timezone.utc))
