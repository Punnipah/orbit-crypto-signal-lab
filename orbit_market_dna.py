"""Market DNA research: same-venue public candles, tape and depth. Read-only.

No identity inference, performance promises, executable signals, or orders.
A single depth snapshot is NOT order-flow imbalance (OFI).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from orbit_model_lab_engine import DataUnavailable, validate_candles


@dataclass(frozen=True)
class Evidence:
    name: str
    observation: str
    quality: str  # OBSERVED, PROXY, or UNAVAILABLE
    detail: str


@dataclass(frozen=True)
class MarketDNA:
    support: float
    resistance: float
    recent_low: float
    recent_high: float
    close: float
    volatility_pct: float
    location_pct: float
    regime: str
    candles_closed_at: datetime
    observations: tuple[Evidence, ...]


def analyze_candles(data: pd.DataFrame) -> MarketDNA:
    """Evaluate only closed 5-minute bars; comparisons exclude the last bar."""
    f = validate_candles(data, require_fresh=False)
    if len(f) < 576:
        raise DataUnavailable("ต้องมีแท่ง 5m อย่างน้อย 576 แท่ง")
    last, prev = f.iloc[-1], f.iloc[-2]
    window = f.iloc[-97:-1]
    support, resistance = float(window.low.min()), float(window.high.max())
    close = float(last.close)
    width = resistance - support
    location = 100 * (close - support) / width if width > 0 else 50.0
    h1 = f[["open", "high", "low", "close", "volume"]].resample(
        "1h", label="left", closed="left"
    ).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
    counts = f.close.resample("1h", label="left", closed="left").count()
    h1 = h1.loc[counts == 12].dropna()
    if len(h1) < 25:
        raise DataUnavailable("แท่ง 1H ที่ปิดครบไม่เพียงพอ")
    sma20 = h1.close.iloc[-21:-1].mean()
    slope_pct = (float(h1.close.iloc[-1]) / float(h1.close.iloc[-6]) - 1) * 100
    if abs(slope_pct) < 0.5 and abs(float(h1.close.iloc[-1]) / sma20 - 1) < .008:
        regime = "SIDEWAYS / MIXED"
    elif slope_pct > 0 and float(h1.close.iloc[-1]) > sma20:
        regime = "UPWARD PRESSURE"
    elif slope_pct < 0 and float(h1.close.iloc[-1]) < sma20:
        regime = "DOWNWARD PRESSURE"
    else:
        regime = "MIXED"
    true_range = pd.concat([f.high - f.low, (f.high - f.close.shift()).abs(),
                            (f.low - f.close.shift()).abs()], axis=1).max(axis=1)
    atr = float(true_range.iloc[-14:].mean())
    if not math.isfinite(atr) or atr <= 0:
        raise DataUnavailable("ATR ไม่พร้อม")
    vbase = float(f.volume.iloc[-21:-1].mean())
    vol_ratio = float(last.volume) / vbase if vbase > 0 else 0.0
    prior_low = float(f.low.iloc[-25:-1].min())
    prior_high = float(f.high.iloc[-25:-1].max())
    bar_range = float(last.high-last.low)
    where_close = (close - float(last.low)) / bar_range if bar_range > 0 else 0.5
    narrow = bar_range <= 0.85 * float((f.high-f.low).iloc[-21:-1].median())
    notes: list[Evidence] = []
    if float(last.low) < prior_low and close > prior_low:
        notes.append(Evidence("Liquidity sweep · downside", "กวาดต่ำกว่าจุดต่ำเดิมแล้วปิดกลับเหนือระดับ", "OBSERVED", "ตรวจเฉพาะแท่ง 5m ที่ปิดแล้ว; ไม่ยืนยันผู้เล่นรายใหญ่"))
    elif float(last.high) > prior_high and close < prior_high:
        notes.append(Evidence("Liquidity sweep · upside", "กวาดสูงกว่าจุดสูงเดิมแล้วปิดกลับต่ำกว่า", "OBSERVED", "ตรวจเฉพาะแท่ง 5m ที่ปิดแล้ว; ไม่ยืนยันผู้เล่นรายใหญ่"))
    else:
        notes.append(Evidence("Liquidity sweep", "ไม่พบการกวาดกรอบ 24 แท่งแบบปิดกลับ", "OBSERVED", "การไม่พบรูปแบบไม่ใช่การคาดการณ์ทิศทาง"))
    if vol_ratio >= 1.5 and narrow:
        label = "ราคาปิดค่อนทางบน" if where_close >= .65 else ("ราคาปิดค่อนทางล่าง" if where_close <= .35 else "ราคาปิดกลางแท่ง")
        notes.append(Evidence("Absorption-like candle", f"Volume {vol_ratio:.2f}x แต่ช่วงแท่งแคบ; {label}", "PROXY", "ลักษณะนี้อาจเกิดจากหลายเหตุ ไม่ใช่หลักฐานว่ามีวาฬรับหรือเทขาย"))
    else:
        notes.append(Evidence("Absorption-like candle", f"ยังไม่มีรูปแบบ Volume/Range ตามเกณฑ์ (Volume {vol_ratio:.2f}x)", "PROXY", "ต้องใช้ข้อมูล Tape/Depth ตามเวลาเพื่อประเมินจริง"))
    if close < support:
        notes.append(Evidence("Range location", "ปิดต่ำกว่ากรอบ 96 แท่งก่อนหน้า", "OBSERVED", "ระวังการหลุดหลอกและการกลับตัว"))
    elif close > resistance:
        notes.append(Evidence("Range location", "ปิดสูงกว่ากรอบ 96 แท่งก่อนหน้า", "OBSERVED", "ระวังการทะลุหลอกและการกลับตัว"))
    else:
        notes.append(Evidence("Range location", f"อยู่ที่ {location:.0f}% ของกรอบ 96 แท่ง", "OBSERVED", "0%=แนวรับ, 100%=แนวต้านจากอดีต"))
    return MarketDNA(support, resistance, prior_low, prior_high, close, atr / close * 100,
                     location, regime, f.index[-1].to_pydatetime() + pd.Timedelta(minutes=5), tuple(notes))


def _request(url: str, params: dict) -> object:
    req = Request(url + "?" + urlencode(params), headers={"User-Agent": "OrbitMarketDNA/1.0 public-readonly"})
    try:
        with urlopen(req, timeout=8) as response:
            return json.load(response)
    except HTTPError as exc:
        raise DataUnavailable(f"Public API HTTP {exc.code}") from None
    except (TimeoutError, URLError, OSError, ValueError, TypeError):
        raise DataUnavailable("Public API ไม่พร้อม") from None


def _trades_payload(venue: str, symbol: str) -> tuple[list, str]:
    if venue == "BINANCE_TH_SPOT":
        raw = _request("https://api.binance.th/api/v1/aggTrades", {"symbol": symbol, "limit": 500})
        return raw, "BINANCE_TH_AGGTRADES"
    if venue == "BINANCE_GLOBAL_USDM":
        raw = _request("https://fapi.binance.com/fapi/v1/aggTrades", {"symbol": symbol, "limit": 500})
        return raw, "BINANCE_FUTURES_AGGTRADES"
    if venue == "BITGET_USDT_FUTURES":
        raw = _request("https://api.bitget.com/api/v3/market/fills", {"category": "USDT-FUTURES", "symbol": symbol, "limit": 100})
        if not isinstance(raw, dict) or str(raw.get("code")) != "00000":
            raise DataUnavailable("Bitget public fills error")
        return raw.get("data"), "BITGET_FUTURES_FILLS"
    raise DataUnavailable("ไม่มี Tape endpoint สำหรับตลาดที่เลือก")


def summarize_tape(venue: str, trades: list, *, now: datetime | None = None) -> dict:
    """Recent public fills only. Side = aggressor; never infer whale identity."""
    if not isinstance(trades, list):
        raise DataUnavailable("Trade payload ผิดรูปแบบ")
    rows = []
    for t in trades:
        try:
            if venue in ("BINANCE_TH_SPOT", "BINANCE_GLOBAL_USDM"):
                price, qty, timestamp = float(t["p"]), float(t["q"]), int(t["T"])
                aggressor_buy = not bool(t["m"])
            elif venue == "BITGET_USDT_FUTURES":
                price = float(t["price"])
                qty = float(t["size"])
                timestamp = int(t.get("ts", t.get("time", t.get("timestamp"))))
                aggressor_buy = str(t["side"]).lower() == "buy"
                if str(t["side"]).lower() not in ("buy", "sell"):
                    continue
            else:
                raise DataUnavailable("unsupported venue")
            if price > 0 and qty > 0 and timestamp > 1_000_000_000_000:
                rows.append((timestamp, price, qty, aggressor_buy))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    if len(rows) < 25:
        raise DataUnavailable("Trade sample ไม่พอ (ขั้นต่ำ 25 รายการ)")
    stamp = max(r[0] for r in rows)
    clock = now or datetime.now(timezone.utc)
    age_s = clock.timestamp() - stamp / 1000
    if age_s < -30 or age_s > 180:
        raise DataUnavailable("Trade sample เก่าเกิน 3 นาทีหรือเวลาผิด")
    buy = sum(p * q for _, p, q, b in rows if b)
    sell = sum(p * q for _, p, q, b in rows if not b)
    if buy + sell <= 0:
        raise DataUnavailable("ไม่มีปริมาณซื้อขายใช้คำนวณ")
    return {"trades": len(rows), "buy_share_pct": 100 * buy / (buy + sell),
            "sell_share_pct": 100 * sell / (buy + sell),
            "sample_age_sec": round(age_s), "latest_ms": stamp,
            "window_sec": round((stamp - min(x[0] for x in rows)) / 1000),
            "venue": venue, "quality": "OBSERVED_RECENT_FILLS"}


def fetch_tape(venue: str, symbol: str) -> dict:
    raw, endpoint = _trades_payload(venue, symbol)
    report = summarize_tape(venue, raw)
    report["source"] = endpoint
    return report


def summarize_depth(venue: str, book: dict) -> dict:
    if not isinstance(book, dict) or not isinstance(book.get("bids"), list) or not isinstance(book.get("asks"), list):
        raise DataUnavailable("Order book ไม่ครบ")
    def total(levels):
        result = []
        for level in levels[:20]:
            try:
                p, q = float(level[0]), float(level[1])
                if p > 0 and q > 0:
                    result.append((p, q))
            except (ValueError, TypeError, IndexError):
                continue
        return result
    bids, asks = total(book["bids"]), total(book["asks"])
    if len(bids) < 5 or len(asks) < 5:
        raise DataUnavailable("Order book มีระดับราคาไม่พอ")
    bid, ask = max(p for p, _ in bids), min(p for p, _ in asks)
    if bid >= ask:
        raise DataUnavailable("Bid/Ask ไม่สมเหตุผล")
    bq, aq = sum(p*q for p, q in bids), sum(p*q for p, q in asks)
    return {"bid": bid, "ask": ask, "spread_bps": (ask-bid) / ((ask+bid)/2) * 10_000,
            "bid_depth_share_pct": 100*bq/(bq+aq), "quality": "SNAPSHOT_ONLY_NOT_OFI"}


def fetch_depth(venue: str, symbol: str) -> dict:
    if venue == "BINANCE_TH_SPOT":
        result = _request("https://api.binance.th/api/v1/depth", {"symbol": symbol, "limit": 100})
    elif venue == "BINANCE_GLOBAL_USDM":
        result = _request("https://fapi.binance.com/fapi/v1/depth", {"symbol": symbol, "limit": 100})
    else:
        raise DataUnavailable("ยังไม่มี Order Book parser ที่ตรวจสอบแล้วสำหรับตลาดนี้")
    return summarize_depth(venue, result)
