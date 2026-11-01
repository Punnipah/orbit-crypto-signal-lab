"""v5.9.3 explicit exchange and reconciled-flow health, read-only."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from scalp_marketdata import MarketDataError, get_exchange_catalog


LABELS = {
    "BINANCE_TH_SPOT": "Spot · Binance TH",
    "BINANCE_GLOBAL_USDM": "Futures · Binance Global",
    "BITGET_USDT_FUTURES": "Futures · Bitget",
}


@dataclass(frozen=True)
class Health:
    venue: str
    symbol: str
    state: str
    detail: str
    checked_at: datetime
    can_approve_short: bool = False


def classify(venue: str, symbol: str, *, error: str | None = None,
             snapshot=None, catalog_only: bool = False,
             now: datetime | None = None) -> Health:
    """Data quality != strategy-ready; never report Spot/Bitget as Short READY."""
    if venue not in LABELS:
        raise ValueError("unknown venue")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("timezone-aware diagnostic required")
    if error:
        err = str(error)[:200]
        code = re.search(r"\bHTTP\s*(403|451|429)\b", err, re.IGNORECASE)
        if code and code.group(1) in ("403", "451"):
            status = "ACCESS_BLOCKED"
            detail = f"HTTP {code.group(1)} · Exchange ปฏิเสธการเข้าถึงจากสภาพแวดล้อมนี้"
        elif code and code.group(1) == "429":
            status, detail = "RATE_LIMITED", "HTTP 429 · API จำกัดจำนวนคำขอ"
        elif "network" in err.lower() or "timeout" in err.lower():
            status, detail = "NETWORK_ERROR", "เชื่อมต่อ API ไม่สำเร็จหรือหมดเวลา"
        elif "ไม่ใช่คู่" in err or "symbol" in err.lower():
            status, detail = "SYMBOL_UNAVAILABLE", "คู่เหรียญนี้ไม่ผ่านข้อมูลตลาดที่เลือก"
        else:
            status, detail = "DATA_UNAVAILABLE", "ข้อมูลตลาดที่เลือกยังยืนยันไม่ได้"
        return Health(venue, symbol, status, detail + " · ไม่ใช้ราคา Spot แทน Futures", now)
    if catalog_only:
        return Health(venue, symbol, "API_REACHABLE", "ตรวจ Exchange Catalog ได้เท่านั้น · "
                      "ยังไม่ได้ตรวจแท่ง, Mark, Funding, Order Book และ Flow", now)
    if snapshot is None or snapshot.venue != venue or snapshot.symbol != symbol:
        return Health(venue, symbol, "DATA_UNAVAILABLE", "ไม่มี Snapshot ตลาดนี้ที่ยืนยันแล้ว", now)
    age = (now - snapshot.checked_at).total_seconds()
    if age < -5 or age > 90:
        return Health(venue, symbol, "STALE_DATA", f"ข้อมูลเก่า/เวลาผิด ({age:.0f} วินาที)", now)
    if venue == "BINANCE_TH_SPOT":
        return Health(venue, symbol, "SPOT_ONLY", "Spot ใช้ประเมิน LONG หรือขายเหรียญที่ถือ · "
                      "ไม่ใช่แหล่งอนุมัติ SHORT Futures", now)
    if venue == "BITGET_USDT_FUTURES":
        one = snapshot.frames.get("1m")
        verified = (bool(snapshot.flow_reconciled) and one is not None and
                    "taker_buy" in one and bool(one.taker_buy.tail(4).notna().any()))
        if not verified:
            return Health(venue, symbol, "FLOW_UNAVAILABLE", "ราคา Futures พร้อม แต่ Public "
                          "Buy/Sell Flow ของแท่ง 1m ยังตรวจเทียบปริมาณไม่ครบ · "
                          "ไม่อาจอนุมัติ READY", now)
        return Health(venue, symbol, "FUTURES_FLOW_VERIFIED", "Bitget Futures + Public Buy/Sell "
                      "Volume Proxy ตรวจเทียบแท่ง 1m แล้ว (ไม่ใช่ Certified Taker Flow) "
                      "· ยังต้องผ่านสัญญาณและข้อจำกัดความเสี่ยง", now,
                      can_approve_short=True)
    return Health(venue, symbol, "FUTURES_DATA_READY", "ข้อมูล Futures ตลาดนี้มาครบ ณ รอบที่ตรวจ "
                  "· ยังต้องผ่านกฎกลยุทธ์และความเสี่ยงก่อน READY", now,
                  can_approve_short=True)


def probe_catalog(venue: str, symbol: str) -> Health:
    """Best-effort optional UI probe: public exchangeInfo only, not trading."""
    if venue not in LABELS:
        raise ValueError("unknown venue")
    try:
        catalog = get_exchange_catalog(venue)
        if symbol not in catalog:
            return classify(venue, symbol, error=f"symbol {symbol} not tradable")
        return classify(venue, symbol, catalog_only=True)
    except (MarketDataError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        return classify(venue, symbol, error=str(exc))
