"""Read-only Binance USD-M Futures snapshot, separate from CoinGlass.

No order endpoints, account data, credentials, or web scraping. The OI value
is Binance USDT-M contract notional, NOT multi-exchange aggregated OI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE = "https://fapi.binance.com"
BYBIT_BASE = "https://api.bybit.com"


class DerivativesDataError(Exception):
    pass


@dataclass(frozen=True)
class DerivativesSnapshot:
    symbol: str
    observed_at: datetime
    funding_rate_pct: float
    oi_change_24h_pct: float
    long_short_account_ratio: float
    oi_notional_usdt: float
    funding_at: datetime
    oi_at: datetime
    ratio_at: datetime
    source: str = "Binance USDⓈ-M Futures (single exchange)"


def _request(path: str, params: dict) -> dict | list:
    req = Request(f"{API_BASE}{path}?{urlencode(params)}", headers={"User-Agent": "OrbitSignalLab/2.2"})
    try:
        with urlopen(req, timeout=12) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        raise DerivativesDataError(f"Binance Futures API ไม่พร้อมใช้งาน: {exc}") from exc


def _bybit_request(path: str, params: dict) -> dict:
    request = Request(f"{BYBIT_BASE}{path}?{urlencode(params)}", headers={"User-Agent": "OrbitSignalLab/2.2"})
    try:
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        raise DerivativesDataError(f"Bybit Public API ไม่พร้อมใช้งาน: {exc}") from exc
    if not isinstance(data, dict) or data.get("retCode") != 0:
        raise DerivativesDataError("Bybit ไม่ส่งข้อมูลที่ใช้ได้")
    return data


def _time(ms: int | str) -> datetime:
    return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)


def _number(value: object, label: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise DerivativesDataError(f"{label} ไม่ใช่ตัวเลข") from exc
    if not math.isfinite(v):
        raise DerivativesDataError(f"{label} ไม่ใช่ตัวเลขที่ใช้ได้")
    return v


def parse_snapshot(symbol: str, mark: dict, oi_history: list, ratios: list,
                   *, now: datetime | None = None) -> DerivativesSnapshot:
    """Require two OI observations >=24h apart for a real 24h delta."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise DerivativesDataError("ต้องใช้เวลาที่ระบุเขตเวลา")
    if mark.get("symbol") != symbol or not isinstance(oi_history, list) or not isinstance(ratios, list):
        raise DerivativesDataError("ข้อมูล Futures ไม่ตรงสัญลักษณ์หรือไม่ครบ")
    if len(oi_history) < 2 or not ratios:
        raise DerivativesDataError("ข้อมูล OI หรือ Long/Short มีไม่เพียงพอ")
    observed = _time(mark["time"])
    oi_rows = sorted(oi_history, key=lambda r: int(r["timestamp"]))
    latest_oi = oi_rows[-1]
    oi_at = _time(latest_oi["timestamp"])
    # Hourly samples: only use the same-hour observation a day earlier.
    historical = [r for r in oi_rows[:-1]
                  if _time(r["timestamp"]) <= oi_at - timedelta(hours=24)]
    if not historical:
        raise DerivativesDataError("ยังไม่มี OI ย้อนหลังครบ 24 ชั่วโมง")
    old = historical[-1]
    old_at = _time(old["timestamp"])
    if oi_at - old_at > timedelta(hours=26):
        raise DerivativesDataError("ข้อมูล OI ย้อนหลังมีช่องว่างเกินกำหนด")
    oi_value = _number(latest_oi["sumOpenInterestValue"], "OI ล่าสุด")
    old_value = _number(old["sumOpenInterestValue"], "OI 24h ก่อน")
    if oi_value <= 0 or old_value <= 0:
        raise DerivativesDataError("มูลค่า OI ต้องมากกว่าศูนย์")
    if latest_oi.get("symbol") not in (None, symbol):
        raise DerivativesDataError("สัญลักษณ์ OI ไม่ตรง")
    recent_ratio = max(ratios, key=lambda r: int(r["timestamp"]))
    if recent_ratio.get("symbol") not in (None, symbol):
        raise DerivativesDataError("สัญลักษณ์ Long/Short ไม่ตรง")
    ratio = _number(recent_ratio["longShortRatio"], "Long/Short")
    funding = _number(mark["lastFundingRate"], "Funding") * 100
    if not 0 < ratio <= 50 or abs(funding) > 5:
        raise DerivativesDataError("ค่าตัวชี้วัด Futures อยู่นอกขอบเขต")
    ratio_at = _time(recent_ratio["timestamp"])
    for label, at, limit in (("Funding", observed, timedelta(minutes=20)),
                             ("OI", oi_at, timedelta(hours=3)),
                             ("Long/Short", ratio_at, timedelta(hours=3))):
        age = now - at
        if age < -timedelta(minutes=5) or age > limit:
            raise DerivativesDataError(f"ข้อมูล {label} เก่าหรือเวลาไม่ถูกต้อง")
    return DerivativesSnapshot(
        symbol=symbol, observed_at=observed, funding_rate_pct=funding,
        oi_change_24h_pct=(oi_value / old_value - 1) * 100,
        long_short_account_ratio=ratio, oi_notional_usdt=oi_value,
        funding_at=observed, oi_at=oi_at, ratio_at=ratio_at)


def fetch_derivatives(symbol: str) -> DerivativesSnapshot:
    """Fetch 3 Binance public endpoints; gracefully reject unsupported pairs."""
    if not symbol.isascii() or not symbol.isalnum() or not symbol.endswith("USDT") or len(symbol) > 24:
        raise DerivativesDataError("รองรับเฉพาะคู่ Futures USDT ที่มีใน Binance USDⓈ-M")
    mark = _request("/fapi/v1/premiumIndex", {"symbol": symbol})
    oi = _request("/futures/data/openInterestHist", {"symbol": symbol, "period": "1h", "limit": 30})
    ratios = _request("/futures/data/globalLongShortAccountRatio", {"symbol": symbol, "period": "1h", "limit": 2})
    try:
        return parse_snapshot(symbol, mark, oi, ratios)
    except (KeyError, TypeError, OverflowError, ValueError) as exc:
        raise DerivativesDataError("รูปแบบข้อมูล Futures ไม่ครบหรือเปลี่ยนแปลง") from exc


def parse_bybit(symbol: str, ticker_payload: dict, oi_payload: dict, ratio_payload: dict,
                *, now: datetime | None = None) -> DerivativesSnapshot:
    """Bybit: OI % is based on contract quantity, unlike Binance's notional delta."""
    now = now or datetime.now(timezone.utc)
    try:
        tick = ticker_payload["result"]["list"][0]
        if tick["symbol"] != symbol:
            raise DerivativesDataError("สัญลักษณ์ Bybit ไม่ตรง")
        oi_rows = sorted(oi_payload["result"]["list"], key=lambda r: int(r["timestamp"]))
        ratios = ratio_payload["result"]["list"]
        if len(oi_rows) < 2 or not ratios:
            raise DerivativesDataError("Bybit OI/Long-Short ไม่ครบ")
        last = oi_rows[-1]
        oi_at = _time(last["timestamp"])
        olds = [r for r in oi_rows[:-1] if _time(r["timestamp"]) <= oi_at - timedelta(hours=24)]
        if not olds or oi_at - _time(olds[-1]["timestamp"]) > timedelta(hours=26):
            raise DerivativesDataError("Bybit OI ย้อนหลังไม่ครบ 24h")
        current_qty = _number(last["openInterest"], "Bybit OI")
        old_qty = _number(olds[-1]["openInterest"], "Bybit OI 24h")
        if min(current_qty, old_qty) <= 0:
            raise DerivativesDataError("Bybit OI ไม่ถูกต้อง")
        latest_ratio = max(ratios, key=lambda r: int(r["timestamp"]))
        if latest_ratio["symbol"] != symbol:
            raise DerivativesDataError("Bybit Ratio ไม่ตรงสัญลักษณ์")
        buy, sell = _number(latest_ratio["buyRatio"], "buyRatio"), _number(latest_ratio["sellRatio"], "sellRatio")
        if not 0 < sell <= 1 or not 0 < buy <= 1:
            raise DerivativesDataError("Bybit Ratio ไม่ถูกต้อง")
        observed = _time(ticker_payload["time"])
        ratio_at = _time(latest_ratio["timestamp"])
        for label, stamp, max_age in (("Funding", observed, timedelta(minutes=20)),
                                      ("OI", oi_at, timedelta(hours=3)),
                                      ("Long/Short", ratio_at, timedelta(hours=3))):
            age = now - stamp
            if age < -timedelta(minutes=5) or age > max_age:
                raise DerivativesDataError(f"Bybit {label} เก่าหรือเวลาไม่ถูกต้อง")
        funding = _number(tick["fundingRate"], "Funding") * 100
        notional = _number(tick["openInterestValue"], "OI USD")
        ratio = buy / sell
        if notional <= 0 or not 0 < ratio <= 50 or abs(funding) > 5:
            raise DerivativesDataError("Bybit Futures ค่าอยู่นอกช่วง")
        return DerivativesSnapshot(
            symbol=symbol, observed_at=observed, funding_rate_pct=funding,
            oi_change_24h_pct=(current_qty / old_qty - 1) * 100,
            long_short_account_ratio=ratio, oi_notional_usdt=notional,
            funding_at=observed, oi_at=oi_at, ratio_at=ratio_at,
            source="Bybit USDT Linear Futures (single exchange; OI 24h based on quantity)")
    except (KeyError, IndexError, TypeError, OverflowError, ValueError) as exc:
        raise DerivativesDataError("รูปแบบข้อมูล Bybit ไม่ครบหรือเปลี่ยนแปลง") from exc


def fetch_bybit(symbol: str) -> DerivativesSnapshot:
    if not symbol.isascii() or not symbol.isalnum() or not symbol.endswith("USDT") or len(symbol) > 24:
        raise DerivativesDataError("Bybit Futures รองรับเฉพาะคู่ USDT")
    params = {"category": "linear", "symbol": symbol}
    ticker = _bybit_request("/v5/market/tickers", params)
    oi = _bybit_request("/v5/market/open-interest", {**params, "intervalTime": "1h", "limit": 30})
    ratio = _bybit_request("/v5/market/account-ratio", {**params, "period": "1h", "limit": 2})
    return parse_bybit(symbol, ticker, oi, ratio)


def fetch_with_fallback(symbol: str) -> DerivativesSnapshot:
    """Try Binance first; Bybit only if unavailable, never mix sources."""
    try:
        return fetch_derivatives(symbol)
    except DerivativesDataError as first:
        try:
            return fetch_bybit(symbol)
        except DerivativesDataError as second:
            raise DerivativesDataError(f"Binance: {first} | Bybit: {second}") from second


def evaluate_derivatives(technical_signal: str, snapshot: DerivativesSnapshot | None,
                         price_change_24h_pct: float) -> dict:
    """Cautious, unbacktested heuristics, NOT a CoinGlass confirmation."""
    if snapshot is None:
        return {"signal": "WAIT", "status": "MISSING", "reasons": ["ไม่มีข้อมูล Futures ที่ครบ/สดพอ"]}
    if technical_signal not in ("BUY", "SELL"):
        return {"signal": "WAIT", "status": "TECHNICAL_WAIT", "reasons": ["ฝั่งเทคนิคยังไม่ยืนยัน BUY/SELL"]}
    oi, funding, ratio = (snapshot.oi_change_24h_pct, snapshot.funding_rate_pct,
                          snapshot.long_short_account_ratio)
    reasons = []
    if technical_signal == "BUY":
        if price_change_24h_pct <= 0 or oi < 1:
            reasons.append("ราคาและ OI 24h ไม่ยืนยันแรงซื้อพร้อมกัน")
        if funding > 0.05 or funding < -0.05 or ratio > 1.6:
            reasons.append("Funding หรือ Long crowding เกินกรอบระวัง")
    else:
        if price_change_24h_pct >= 0 or oi < 1:
            reasons.append("ราคาและ OI 24h ไม่ยืนยันแรงขายพร้อมกัน")
        if funding < -0.05 or funding > 0.05 or ratio < 0.625:
            reasons.append("Funding หรือ Short crowding เกินกรอบระวัง")
    if reasons:
        return {"signal": "WAIT", "status": "CAUTION", "reasons": reasons}
    return {"signal": technical_signal, "status": "SUPPORTED", "reasons": [
        "Binance Futures สนับสนุนแนวโน้มตามเกณฑ์ทดลอง (ไม่ใช่ CoinGlass หรือการพิสูจน์กำไร)"]}
