"""Read-only Kraken, Binance, and Bybit Futures snapshots, separate from CoinGlass.

No order endpoints, account data, credentials, or web scraping. Each snapshot
belongs to exactly one exchange; OI values/units are provider-specific.
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
KRAKEN_BASE = "https://futures.kraken.com"


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
    oi_unit: str = "USDT"
    funding_unit: str = "percent"
    provider: str = "Binance"


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


def _kraken_request(path: str, params: dict | None = None) -> dict:
    url = KRAKEN_BASE + path
    if params:
        url += "?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "OrbitSignalLab/2.3"})
    try:
        with urlopen(req, timeout=12) as response:
            data = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
        raise DerivativesDataError(f"Kraken Futures Public API ไม่พร้อมใช้งาน: {exc}") from exc
    if not isinstance(data, dict):
        raise DerivativesDataError("Kraken คืนข้อมูลไม่ถูกต้อง")
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
            source="Bybit USDT Linear Futures (single exchange; OI 24h based on quantity)",
            provider="Bybit")
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


def parse_kraken(symbol: str, instrument: str, tickers: dict, oi: dict, ratios: dict,
                 *, now: datetime | None = None) -> DerivativesSnapshot:
    """Kraken analytics: OI uses contract units; funding is venue-native raw.

    These units are deliberately not relabeled as USD notional or Binance-like
    percent. Kraken analytics timestamps are seconds, unlike ticker ISO time.
    """
    now = now or datetime.now(timezone.utc)
    try:
        matching = [t for t in tickers["tickers"] if t.get("symbol") == instrument
                    and t.get("tag") == "perpetual" and t.get("suspended") is False]
        if len(matching) != 1:
            raise DerivativesDataError("Kraken ไม่มีสัญญา Perpetual ที่เปิดซื้อขายสำหรับเหรียญนี้")
        ticker = matching[0]
        observed = datetime.fromisoformat(ticker["lastTime"].replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise DerivativesDataError("Kraken Ticker ไม่มี timezone")
        oid = oi["result"]
        rid = ratios["result"]
        oi_stamps, oi_data = oid["timestamp"], oid["data"]
        ratio_stamps, ratio_data = rid["timestamp"], rid["data"]
        if not oi_stamps or len(oi_stamps) != len(oi_data) or not ratio_stamps or len(ratio_stamps) != len(ratio_data):
            raise DerivativesDataError("Kraken Analytics ไม่ครบ")
        oi_points = sorted(zip(oi_stamps, oi_data), key=lambda item: int(item[0]))
        ratio_points = sorted(zip(ratio_stamps, ratio_data), key=lambda item: int(item[0]))
        oi_at = datetime.fromtimestamp(int(oi_points[-1][0]), tz=timezone.utc)
        previous = [p for p in oi_points[:-1] if int(p[0]) <= int(oi_points[-1][0]) - 86400]
        if not previous or int(oi_points[-1][0]) - int(previous[-1][0]) > 26 * 3600:
            raise DerivativesDataError("Kraken OI มีประวัติย้อนหลังไม่ครบ 24 ชั่วโมง")
        # Kraken OI chart OHLC: [open, high, low, close].
        latest_oi = _number(oi_points[-1][1][3], "Kraken OI ล่าสุด")
        old_oi = _number(previous[-1][1][3], "Kraken OI 24 ชั่วโมงก่อน")
        ratio_at = datetime.fromtimestamp(int(ratio_points[-1][0]), tz=timezone.utc)
        ratio = _number(ratio_points[-1][1], "Kraken Long/Short")
        funding = _number(ticker["fundingRate"], "Kraken Funding native")
        if min(latest_oi, old_oi, ratio) <= 0 or ratio > 50:
            raise DerivativesDataError("Kraken OI หรือ Long/Short ไม่ถูกต้อง")
        for label, stamp, limit in (("Ticker", observed, timedelta(minutes=20)),
                                    ("OI", oi_at, timedelta(hours=3)),
                                    ("Long/Short", ratio_at, timedelta(hours=3))):
            age = now - stamp
            if age > limit or age < -timedelta(minutes=5):
                raise DerivativesDataError(f"Kraken {label} เก่าหรือเวลาผิดปกติ")
        return DerivativesSnapshot(
            symbol=symbol, observed_at=observed, funding_rate_pct=funding,
            oi_change_24h_pct=(latest_oi / old_oi - 1) * 100,
            long_short_account_ratio=ratio, oi_notional_usdt=latest_oi,
            funding_at=observed, oi_at=oi_at, ratio_at=ratio_at,
            source=f"Kraken Futures {instrument} (single exchange)",
            oi_unit="contracts", funding_unit="Kraken raw (not normalized)",
            provider="Kraken")
    except (KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
        raise DerivativesDataError("รูปแบบข้อมูล Kraken ไม่ครบหรือเปลี่ยนแปลง") from exc


def fetch_kraken(symbol: str) -> DerivativesSnapshot:
    if not symbol.isascii() or not symbol.isalnum() or not symbol.endswith("USDT") or len(symbol) > 24:
        raise DerivativesDataError("Kraken comparison ต้องเป็นคู่ Spot USDT")
    coin = symbol[:-4]
    if not coin or not coin.isalnum():
        raise DerivativesDataError("สัญลักษณ์ Kraken ไม่ถูกต้อง")
    instrument = "PF_" + ("XBT" if coin == "BTC" else coin) + "USD"
    ticker = _kraken_request("/derivatives/api/v3/tickers")
    # Validate symbol from the ticker list before requesting expensive analytics.
    active = [t for t in ticker.get("tickers", []) if t.get("symbol") == instrument
              and t.get("tag") == "perpetual" and t.get("suspended") is False]
    if not active:
        raise DerivativesDataError(f"ไม่พบ Kraken Futures {instrument} ที่กำลังซื้อขาย")
    root = f"/api/charts/v1/analytics/{instrument}"
    oi = _kraken_request(root + "/open-interest", {"interval": 3600})
    ratio = _kraken_request(root + "/long-short-ratio", {"interval": 3600})
    return parse_kraken(symbol, instrument, ticker, oi, ratio)


def fetch_with_fallback(symbol: str) -> DerivativesSnapshot:
    """Try a verified public endpoint first; never combine venue data."""
    try:
        return fetch_kraken(symbol)
    except DerivativesDataError as first:
        try:
            return fetch_derivatives(symbol)
        except DerivativesDataError as second:
            try:
                return fetch_bybit(symbol)
            except DerivativesDataError as third:
                raise DerivativesDataError(f"Kraken: {first} | Binance: {second} | Bybit: {third}") from third


def evaluate_derivatives(technical_signal: str, snapshot: DerivativesSnapshot | None,
                         price_change_24h_pct: float) -> dict:
    """Cautious, unbacktested heuristics, NOT a CoinGlass confirmation."""
    if snapshot is None:
        return {"signal": "WAIT", "status": "MISSING", "reasons": ["ไม่มีข้อมูล Futures ที่ครบ/สดพอ"]}
    if technical_signal not in ("BUY", "SELL"):
        return {"signal": "WAIT", "status": "TECHNICAL_WAIT", "reasons": ["ฝั่งเทคนิคยังไม่ยืนยัน BUY/SELL"]}
    oi, funding, ratio = (snapshot.oi_change_24h_pct, snapshot.funding_rate_pct,
                          snapshot.long_short_account_ratio)
    funding_comparable = snapshot.funding_unit == "percent"
    reasons = []
    if technical_signal == "BUY":
        if price_change_24h_pct <= 0 or oi < 1:
            reasons.append("ราคาและ OI 24h ไม่ยืนยันแรงซื้อพร้อมกัน")
        if (funding_comparable and abs(funding) > 0.05) or ratio > 1.6:
            reasons.append("Funding หรือ Long crowding เกินกรอบระวัง")
    else:
        if price_change_24h_pct >= 0 or oi < 1:
            reasons.append("ราคาและ OI 24h ไม่ยืนยันแรงขายพร้อมกัน")
        if (funding_comparable and abs(funding) > 0.05) or ratio < 0.625:
            reasons.append("Funding หรือ Short crowding เกินกรอบระวัง")
    if reasons:
        return {"signal": "WAIT", "status": "CAUTION", "reasons": reasons}
    return {"signal": technical_signal, "status": "SUPPORTED", "reasons": [
        f"{snapshot.source} สนับสนุนแนวโน้มตามเกณฑ์ทดลอง (ไม่ใช่ CoinGlass หรือการพิสูจน์กำไร)",
        "Funding Kraken แสดงเพื่อทราบเท่านั้น ไม่ใช้เกณฑ์ crowding เนื่องจากหน่วยไม่เทียบเท่า Binance" if not funding_comparable else
        "Funding ใช้เกณฑ์ crowding เฉพาะแหล่งที่หน่วยเป็นเปอร์เซ็นต์ตามที่กำหนด"]}
