"""Orbit Live Signal: high-contrast, real-market conditional trade planner.

Standalone experimental Streamlit app. No synthetic market data or trading API.
The original Orbit production application and Telegram alerts are untouched.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from orbit_model_lab_engine import VENUES, SYMBOLS, DataUnavailable, fetch_candles
from orbit_live_planner import LivePlan, build_live_plan


st.set_page_config(page_title="Orbit Live Signal", page_icon="🪐", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
:root {color-scheme:dark}
html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"],
[data-testid="stHeader"], [data-testid="stMain"], .stApp {
  background: #061521 !important;
  color: #f5fbff !important;
}
[data-testid="stAppViewContainer"] .block-container {
  max-width: 1100px; padding: 1.3rem 1rem 5rem !important;
}
html, body, p, span, div, label, li {font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif}
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4,
[data-testid="stWidgetLabel"] p,
label, [data-testid="stCaptionContainer"], .stCaption {color: #f5fbff !important; opacity:1 !important}
h1, h2, h3 {font-weight: 850 !important; letter-spacing: -.02em}
button, input, select, [data-baseweb="select"], [data-testid="stNumberInput"] {
  color: #ffffff !important;
}
[data-baseweb="select"] > div,
[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"] > div > div {
  background: #153449 !important;
  color: #ffffff !important;
  border-color: #71a9c3 !important;
  opacity: 1 !important;
}
[data-baseweb="select"] span,
[data-baseweb="select"] input,
[data-baseweb="select"] svg,
[data-testid="stNumberInput"] button,
[data-testid="stNumberInput"] svg {color:#ffffff !important; fill:#ffffff !important}
[data-testid="stButton"] button {
  background: #20cda4 !important; color: #06231f !important;
  font-weight: 850 !important; border: 2px solid #8cf6dd !important;
}
[data-testid="stButton"] button * {color:#06231f !important}
[data-testid="stAlert"] {background:#163142 !important; border: 1px solid #ffbd73 !important}
[data-testid="stAlert"] * {color:#ffffff !important}
hr {border-color: #35546b !important}
.orbit-hero {border:1.5px solid #4b8ea6;border-radius:22px;padding:20px 20px 17px;
  background:linear-gradient(125deg,#123648 0%,#092335 53%,#14213c 100%);margin-bottom:18px}
.orbit-hero h1 {font-size:clamp(1.8rem,5vw,2.7rem) !important;line-height:1.12;margin:4px 0 !important;color:#ffffff}
.orbit-kicker {font-size:14px;letter-spacing:.13em;font-weight:900;color:#76f4d3 !important}
.orbit-sub {color:#dbebf8 !important;font-weight:650;font-size:16px}
.orbit-card {background:#102d40;border:1.5px solid #4d8ca5;border-radius:20px;
 padding:18px;margin:0 0 14px;min-height:143px;overflow-wrap:anywhere}
.orbit-card h4 {color:#d6ecff !important;margin:0 0 9px !important;font-size:15px !important;font-weight:800 !important}
.orbit-value {font-size:clamp(1.4rem,4vw,2.25rem);color:#ffffff !important;letter-spacing:.015em;
  font-weight:900;line-height:1.21;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.orbit-value.signal {color:#78ffca !important}
.orbit-value.wait {color:#ffdb82 !important}
.orbit-value.block {color:#ffb2b2 !important}
.orbit-help {font-size:14px;line-height:1.5;color:#d0e6f5 !important;font-weight:650;margin-top:11px}
.orbit-zone {background:#0f293a;border:1.5px solid #4e8ea6;border-radius:17px;
  padding:16px;margin-bottom:14px;min-height:158px}
.orbit-zone h4 {color:#84f3da !important;font-size:16px !important;margin:0 0 10px}
.orbit-range {font-size:clamp(1.20rem,3vw,1.65rem);font-weight:900;color:#ffffff !important;
  font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.orbit-note {font-size:14px;line-height:1.6;color:#e2f0fa !important;font-weight:650;margin-top:10px}
.orbit-check {background:#112d40;border-radius:13px;padding:11px 14px;margin-bottom:8px;
 border:1px solid #426b83;font-weight:750;color:#ffffff !important}
.orbit-section {font-size:clamp(1.24rem,3.6vw,1.7rem);font-weight:850;
 color:#f4fbff !important;margin:12px 0 13px}
.orbit-source {border-radius:13px;padding:13px;background:#0e293a;
 border:1px solid #3e7389;color:#e3f4ff !important;font-weight:650;line-height:1.55}
@media(max-width:680px){
 [data-testid="stAppViewContainer"] .block-container {padding: .75rem .65rem 4rem !important}
 .orbit-hero{padding:17px 16px}
 .orbit-card{min-height:auto;padding:15px;margin-bottom:8px}
 .orbit-value{font-size:1.7rem}
 .orbit-zone{min-height:auto}
 [data-testid="stHorizontalBlock"] {row-gap: .1rem}
}
</style>
""", unsafe_allow_html=True)


def safe(value: object) -> str:
    return escape(str(value), quote=True)


def price(value: float | None) -> str:
    if value is None or not pd.notna(value):
        return "—"
    if value < .00001:
        return f"{value:.10f}".rstrip("0").rstrip(".")
    if value < .001:
        return f"{value:.9f}".rstrip("0").rstrip(".")
    if value < .1:
        return f"{value:.7f}".rstrip("0").rstrip(".")
    if value < 10:
        return f"{value:.5f}".rstrip("0").rstrip(".")
    return f"{value:,.2f}"


def card(label: str, value: str, note: str = "", tone: str = "") -> None:
    st.markdown(
        f'<div class="orbit-card"><h4>{safe(label)}</h4>'
        f'<div class="orbit-value {safe(tone)}">{safe(value)}</div>'
        f'<div class="orbit-help">{safe(note)}</div></div>',
        unsafe_allow_html=True,
    )


def section(label: str) -> None:
    st.markdown(f'<div class="orbit-section">{safe(label)}</div>', unsafe_allow_html=True)


@st.cache_data(ttl=180, show_spinner=False)
def market_data(venue: str, symbol: str, days: int) -> pd.DataFrame:
    return fetch_candles(venue, symbol, days)


st.markdown('''<div class="orbit-hero">
<div class="orbit-kicker">REAL MARKET · CLOSED 5M CANDLES · READ ONLY</div>
<h1>🪐 ORBIT LIVE SIGNAL</h1>
<div class="orbit-sub">แผนเฝ้ารอเข้า Spot / Futures จากราคาตลาดจริง · 4H / 1H / 15M / 5M</div>
</div>''', unsafe_allow_html=True)

selectors = st.columns([1, 1, 1], gap="small")
with selectors[0]:
    venue = st.selectbox("ตลาดจริง", list(VENUES), format_func=lambda x: VENUES[x][0])
with selectors[1]:
    symbol = st.selectbox("เหรียญ", SYMBOLS, index=0)
with selectors[2]:
    days = st.selectbox("ข้อมูลย้อนหลัง", [7, 14, 30], index=1, format_func=lambda x: f"{x} วัน")

details = st.columns([1, 1, 1], gap="small")
with details[0]:
    capital = st.number_input("ทุนอ้างอิง (USDT)", min_value=10.0, max_value=1000000.0, value=75.0, step=5.0)
with details[1]:
    risk_pct = st.selectbox("เสี่ยงต่อแผน", [0.25, 0.5, 1.0], index=1, format_func=lambda x: f"{x:g}% ของทุน")
with details[2]:
    fee_bps = st.number_input("Fee ต่อข้าง (bps)", min_value=0.0, max_value=100.0, value=10.0, step=1.0)

if st.button("🔄 ดึงแท่งล่าสุดจาก Exchange", use_container_width=True):
    market_data.clear()
    st.rerun()

try:
    with st.spinner("กำลังตรวจข้อมูลแท่งปิดจากตลาดที่เลือก..."):
        candles = market_data(venue, symbol, days)
        # Recheck freshness on every page load, not just when cache was filled.
        from orbit_model_lab_engine import validate_candles
        candles = validate_candles(candles, now=datetime.now(timezone.utc))
        plan: LivePlan = build_live_plan(candles, venue, capital_usdt=capital,
                                        fee_each_side_bps=fee_bps,
                                        risk_pct=risk_pct)
except DataUnavailable as exc:
    st.error(f"ข้อมูลตลาดยังไม่พร้อม · {exc}")
    st.markdown('<div class="orbit-source">⛔ ไม่มีการแทนราคาด้วยตลาดอื่นหรือข้อมูลจำลอง กรุณาเลือก Exchange / เหรียญอื่น หรือกดดึงข้อมูลใหม่</div>', unsafe_allow_html=True)
    st.stop()
except Exception:
    st.error("เกิดข้อผิดพลาดในการวิเคราะห์ข้อมูลตลาด กรุณากดดึงข้อมูลใหม่")
    st.stop()

closed_th = plan.closed_at.astimezone(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M")
st.markdown(
    f'<div class="orbit-source">📡 {safe(VENUES[venue][0])} · {safe(symbol)} · '
    f'แท่ง 5m ล่าสุดปิด {safe(closed_th)} น. (ไทย) · '
    f'{len(candles):,} แท่งจริง · อัปเดตอัตโนมัติเมื่อข้อมูลแคชหมด (ประมาณ 3 นาที)</div>',
    unsafe_allow_html=True,
)

top = st.columns(3, gap="small")
with top[0]:
    card("ราคาปิด 5m (USDT)", price(plan.reference_close), "ราคาอ้างอิง ไม่ใช่ราคา Bid/Ask ซื้อขายทันที")
with top[1]:
    tone = "signal" if plan.status.startswith("SIGNAL") else ("wait" if plan.status.startswith("WATCH") else "block")
    card("สถานะตอนนี้", plan.status, "SIGNAL ต้องตรวจสเปรดและยืนยันราคาจริงอีกครั้ง", tone)
with top[2]:
    card("แนวโน้มหลายกรอบเวลา", plan.regime, plan.strength)

section("🎯 3 โซนเฝ้ารอเข้าราคา")
st.markdown('<div class="orbit-source">โซนเหล่านี้เป็นระดับเฝ้ารอสถานการณ์ในอนาคต ไม่ใช่คำสั่งให้เข้าทุกโซน หากยัง WATCH / NO TRADE ให้รอยืนยันแท่งปิดก่อน</div>', unsafe_allow_html=True)
zone_cols = st.columns(3, gap="small")
for col, (name, lower, upper, condition) in zip(zone_cols, plan.entry_zones):
    with col:
        st.markdown(
            f'<div class="orbit-zone"><h4>{safe(name)}</h4>'
            f'<div class="orbit-range">{safe(price(lower))}<br>ถึง {safe(price(upper))}</div>'
            f'<div class="orbit-note">{safe(condition)}</div></div>',
            unsafe_allow_html=True,
        )

section("🛡️ ระดับคุมความเสี่ยง (อ้างอิงตามเงื่อนไข)")
levels = st.columns(3, gap="small")
with levels[0]:
    card("ราคาเข้าอ้างอิง", price(plan.entry_reference), "หากยังไม่เกิดสัญญาณ เป็นเพียงสมมติฐาน")
with levels[1]:
    card("STOP LOSS", price(plan.stop), "ไม่ใช่คำสั่ง Stop ที่ส่งเข้า Exchange")
with levels[2]:
    card("TAKE PROFIT 1", price(plan.take_profit_1), "ระดับเป้าหมายตัวอย่างที่ 1.5R")
more = st.columns(3, gap="small")
with more[0]:
    card("TAKE PROFIT 2", price(plan.take_profit_2), "ระดับเป้าหมายตัวอย่างที่ 2.5R")
with more[1]:
    card("เพดานเงินที่เสี่ยง", f"{plan.risk_usdt:.2f} USDT" if plan.risk_usdt is not None else "—", "ตามทุนและ % เสี่ยงที่ตั้งไว้")
with more[2]:
    card("มูลค่าสถานะสูงสุด", f"{plan.max_notional_usdt:.2f} USDT" if plan.max_notional_usdt is not None else "—", "ไม่รวมเลเวอเรจ · ต้องตรวจขั้นต่ำ Exchange")

section("✅ ตรวจการยืนยัน 4 กรอบเวลาและต้นทุน")
check_cols = st.columns(2, gap="small")
for i, (name, passed) in enumerate(plan.checks):
    with check_cols[i % 2]:
        st.markdown(
            f'<div class="orbit-check">{"✅" if passed else "◻️"} {safe(name)}</div>',
            unsafe_allow_html=True,
        )

section("🔎 เหตุผลของสถานะ")
for explanation in plan.explanations:
    st.markdown(f'<div class="orbit-check">• {safe(explanation)}</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="orbit-source">ATR = {plan.atr_pct:.3f}% ของราคา · RSI 5m = {plan.rsi:.1f} · '
    f'Volume เทียบ 20 แท่งก่อน = {plan.volume_ratio:.2f}x · '
    f'ค่าธรรมเนียมใช้ตัวเลขที่ตั้งไว้ และประเมิน Slippage เพิ่มข้างละ 5 bps</div>',
    unsafe_allow_html=True,
)

st.warning("⚠️ แผนนี้ใช้ข้อมูลตลาดจริง แต่กฎสัญญาณยังไม่มีผลพิสูจน์ว่าทำกำไรได้สม่ำเสมอ ไม่ใช่คำสั่งซื้อขายอัตโนมัติ การเทรด Futures เสี่ยงขาดทุนสูง และราคาเข้า / Stop / TP อาจไม่ถูกจับคู่ตามคาด")
