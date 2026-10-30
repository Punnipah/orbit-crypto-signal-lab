"""UI-only presentation helpers; never transform WAIT into BUY/SHORT."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re


PAIRS = ("BTCUSDT", "PEPEUSDT", "DOGEUSDT", "ETHUSDT", "SOLUSDT")
ALIASES = {"BITCOIN": "BTC", "ETHEREUM": "ETH", "DOGECOIN": "DOGE", "RIPPLE": "XRP"}


def normalize_symbol(value: str) -> str:
    """Only USDT pairs are used by the quick UI. Never interpolate raw text in APIs."""
    if not isinstance(value, str):
        raise ValueError("ใส่ชื่อเหรียญ")
    cleaned = re.sub(r"[\s/_-]+", "", value.strip().upper())
    cleaned = ALIASES.get(cleaned, cleaned)
    if not cleaned.endswith("USDT"):
        cleaned += "USDT"
    if not re.fullmatch(r"[A-Z0-9]{2,20}USDT", cleaned):
        raise ValueError("ใช้คู่ USDT เช่น BTC, PEPE, DOGE, ETH หรือ SOL")
    return cleaned


@dataclass(frozen=True)
class SignalLook:
    tag: str
    title: str
    helper: str
    tone: str  # good / warning / danger / neutral


def spot_look(status: str) -> SignalLook:
    mapping = {
        "MTF_READY": SignalLook("SPOT BUY", "จังหวะเข้า MTF ผ่าน", "ตรวจราคาและต้นทุนจริงก่อนตัดสินใจ", "good"),
        "READY_NOW": SignalLook("SPOT BUY", "แผนล็อกเข้าเงื่อนไข", "ตรวจราคาและต้นทุนจริงก่อนตัดสินใจ", "good"),
        "WAIT_ZONE": SignalLook("WAIT", "รอเข้าโซนซื้อ", "Entry Zone ยังไม่ถูกแตะ", "warning"),
        "WAIT_TOUCH": SignalLook("WAIT", "รอยืนยันแท่งเทียน", "ราคาแตะโซนแล้ว แต่ยังไม่พร้อมเข้า", "warning"),
        "WAIT_RECLAIM": SignalLook("WAIT", "รอราคา Reclaim", "ยังไม่มีแท่งปิดยืนยัน", "warning"),
        "WAIT_BREAK": SignalLook("WAIT", "รอการยืนยันโครงสร้าง", "ยังไม่ใช่จังหวะเข้า", "warning"),
        "WAIT_MTF": SignalLook("WAIT", "รอหลาย Timeframe", "เงื่อนไข MTF ยังไม่ผ่าน", "warning"),
        "WAIT_RISK": SignalLook("WAIT", "ความเสี่ยงยังไม่ผ่าน", "R:R ยังไม่เหมาะสม", "warning"),
        "MTF_WAIT": SignalLook("WAIT", "กำลังรอสัญญาณ Spot", "ข้อมูลยังไม่ครบเงื่อนไขซื้อ", "warning"),
        "INVALIDATED": SignalLook("CANCELLED", "แผนนี้ถูกยกเลิก", "ห้ามใช้ Entry Zone ของแผนเดิม", "danger"),
        "PASSED": SignalLook("MISSED", "จังหวะเดิมผ่านไปแล้ว", "ไม่ไล่ราคา", "neutral"),
        "EXPIRED": SignalLook("EXPIRED", "แผนหมดอายุแล้ว", "ต้องสร้างแผนใหม่", "neutral"),
    }
    return mapping.get(status, SignalLook("WAIT", "ข้อมูลหรือสัญญาณยังไม่พร้อม",
                                          "ตรวจการเชื่อมต่อและรายละเอียด", "neutral"))


def futures_look(status: str, direction: str) -> SignalLook:
    if status == "READY_LONG":
        return SignalLook("LONG · READY", "พิจารณา Long ได้ตามเงื่อนไข", "ยืนยันราคา Futures ก่อนตัดสินใจ", "good")
    if status == "READY_SHORT":
        return SignalLook("SHORT · READY", "พิจารณา Short ได้ตามเงื่อนไข", "ยืนยันราคา Futures ก่อนตัดสินใจ", "good")
    if status == "WATCH_LONG":
        return SignalLook("LONG · WATCH", "รอราคา Retest สำหรับ Long", "ห้ามไล่ราคา", "warning")
    if status == "WATCH_SHORT":
        return SignalLook("SHORT · WATCH", "รอราคา Retest สำหรับ Short", "ห้ามไล่ราคา", "warning")
    if status == "INVALIDATED":
        return SignalLook("CANCELLED", "Setup Futures ถูกยกเลิก", "รอ Setup ใหม่", "danger")
    if status == "RISK_BLOCK":
        return SignalLook("RISK BLOCK", "ระบบพักสัญญาณ Futures", "ตัวกรองความเสี่ยงไม่ผ่าน", "danger")
    if status in {"NO_SETUP", "NO_TREND"}:
        return SignalLook("WAIT", "ยังไม่มีจังหวะ Long/Short", "ไม่ฝืนเปิดสถานะ", "warning")
    return SignalLook("NO DATA", "ข้อมูล Futures ยังไม่พร้อม", "ไม่มีการคำนวณสัญญาณทดแทน", "neutral")


def concise_price(value: float | None) -> str:
    if value is None or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return "—"
    if value >= 1000:
        return f"{value:,.2f}"
    if value >= 1:
        return f"{value:,.4f}"
    if value >= 0.01:
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return f"{value:.10f}".rstrip("0").rstrip(".")
