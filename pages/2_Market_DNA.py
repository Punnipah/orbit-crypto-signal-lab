"""Read-only Market DNA screen for the separate Orbit Model Lab app."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orbit_model_lab_engine import DataUnavailable, SYMBOLS, VENUES, fetch_candles, validate_candles
from orbit_market_dna import analyze_candles, fetch_depth, fetch_tape

st.set_page_config(page_title="Orbit · Market DNA", page_icon="🧬", layout="wide")
st.markdown("""
<style>
html,body,.stApp,[data-testid="stAppViewContainer"]{background:#061521!important;color:#f5fbff!important}
[data-testid="stAppViewContainer"] .block-container{max-width:1080px;padding:1.2rem 1rem 4rem!important}
[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,[data-testid="stMarkdownContainer"] h3,
[data-testid="stWidgetLabel"] p,[data-testid="stCaptionContainer"] *,label,
[data-testid="stAlert"] * {color:#f5fbff!important;opacity:1!important}
[data-baseweb="select"]>div,[data-testid="stSelectbox"]>div>div{background:#173648!important;color:white!important}
[data-baseweb="select"] *{color:white!important}
[data-testid="stButton"] button{background:#18c6a1!important;color:#06231f!important;font-weight:800!important;border:2px solid #8cf6dc!important}
[data-testid="stButton"] button *{color:#06231f!important}
.dna-panel{background:#103045;border:1.5px solid #5590ae;border-radius:18px;padding:17px;margin:8px 0 15px}
.dna-label{font-size:15px;font-weight:750;color:#d6ebfa!important}
.dna-value{font-size:clamp(1.35rem,3.3vw,2rem);font-weight:900;color:white!important;overflow-wrap:anywhere}
.dna-note{color:#e2eff8!important;font-size:15px;line-height:1.5;margin-top:8px}
.dna-badge{display:inline-block;border-radius:22px;padding:4px 12px;background:#235369;color:#fff!important;font-weight:850}
@media(max-width:660px){[data-testid="stAppViewContainer"] .block-container{padding:.8rem .65rem 3rem!important}.dna-panel{padding:14px}}
</style>
""", unsafe_allow_html=True)


def fmt(value: float) -> str:
    if value < .00001:
        return f"{value:.10f}".rstrip('0').rstrip('.')
    if value < .01:
        return f"{value:.8f}".rstrip('0').rstrip('.')
    return f"{value:,.4f}"


def panel(title: str, value: str, description: str = '') -> None:
    st.markdown(f'<div class="dna-panel"><div class="dna-label">{escape(title)}</div>'
                f'<div class="dna-value">{escape(value)}</div>'
                f'<div class="dna-note">{escape(description)}</div></div>', unsafe_allow_html=True)


@st.cache_data(ttl=90, show_spinner=False)
def candles(venue: str, symbol: str, days: int) -> pd.DataFrame:
    return fetch_candles(venue, symbol, days)


@st.cache_data(ttl=40, show_spinner=False)
def tape(venue: str, symbol: str) -> dict:
    return fetch_tape(venue, symbol)


@st.cache_data(ttl=25, show_spinner=False)
def depth(venue: str, symbol: str) -> dict:
    return fetch_depth(venue, symbol)


st.title("🧬 Orbit Market DNA")
st.markdown("**ราคา · Tape · Liquidity · หลักฐานการเคลื่อนไหว**")
st.info("RESEARCH ONLY · ไม่ระบุตัวตนวาฬ ไม่ส่งออเดอร์ ไม่ยืนยัน BUY/SHORT หรือโอกาสกำไร")
a, b, c = st.columns(3)
with a:
    venue = st.selectbox("เลือกตลาด", list(VENUES), format_func=lambda v: VENUES[v][0])
with b:
    symbol = st.selectbox("คู่เหรียญ", SYMBOLS)
with c:
    days = st.selectbox("แท่งราคา", [7, 14], index=0, format_func=lambda d: f"{d} วัน")
if st.button("🔄 รีเฟรชข้อมูลตลาด", use_container_width=True):
    candles.clear(); tape.clear(); depth.clear(); st.rerun()

try:
    df = validate_candles(candles(venue, symbol, days), now=datetime.now(timezone.utc))
    dna = analyze_candles(df)
except DataUnavailable as exc:
    st.error(f"CANDLE DATA BLOCK · {exc}")
    st.stop()
except Exception:
    st.error("CANDLE ERROR · ไม่สามารถยืนยันข้อมูลราคาที่ใช้ได้")
    st.stop()

closed_th = dna.candles_closed_at.astimezone(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M")
st.caption(f"{VENUES[venue][0]} · {symbol} · แท่ง 5m ล่าสุดปิด {closed_th} น. (ไทย) · {len(df):,} แท่ง · ราคาเป็นข้อมูลตลาดที่เลือกเท่านั้น")
cols = st.columns(3)
with cols[0]: panel("ราคาปิดล่าสุด (USDT)", fmt(dna.close), "ราคาแท่งปิด ไม่ใช่ Bid/Ask ปัจจุบัน")
with cols[1]: panel("Regime 1H", dna.regime, "การจัดหมวดตามราคาย้อนหลัง ไม่ใช่การพยากรณ์")
with cols[2]: panel("ATR 5m / ราคา", f"{dna.volatility_pct:.3f}%", "ความผันผวนที่สังเกตได้")
cols = st.columns(2)
with cols[0]: panel("แนวรับจาก 96 แท่งก่อน (USDT)", fmt(dna.support), "ระดับอ้างอิง ไม่ได้หมายความว่าราคาจะเด้ง")
with cols[1]: panel("แนวต้านจาก 96 แท่งก่อน (USDT)", fmt(dna.resistance), "ระดับอ้างอิง ไม่ได้หมายความว่าราคาจะกลับตัว")

st.subheader("📊 ราคา 5m และโซนสำคัญ")
chart = df[["close"]].tail(144).copy()
chart["Support"] = dna.support
chart["Resistance"] = dna.resistance
st.line_chart(chart, height=240, use_container_width=True)

st.subheader("🔎 Price Response · จากแท่งราคาปิด")
for item in dna.observations:
    st.markdown(f'<div class="dna-panel"><span class="dna-badge">{escape(item.quality)}</span>'
                f'<div class="dna-value" style="font-size:1.18rem;margin-top:8px">{escape(item.name)}</div>'
                f'<div class="dna-note">{escape(item.observation)}</div>'
                f'<div class="dna-note">ข้อจำกัด: {escape(item.detail)}</div></div>', unsafe_allow_html=True)

st.subheader("📼 Tape · ธุรกรรมสาธารณะล่าสุด")
try:
    t = tape(venue, symbol)
    if t["sample_age_sec"] > 180:
        raise DataUnavailable("ข้อมูล Tape จาก Cache เก่าเกิน 3 นาที")
    z = st.columns(3)
    with z[0]: panel("Aggressive Buy · สัดส่วนมูลค่า", f'{t["buy_share_pct"]:.1f}%', "ตัวอย่างธุรกรรมล่าสุด ไม่ใช่ทั้งตลาด")
    with z[1]: panel("Aggressive Sell · สัดส่วนมูลค่า", f'{t["sell_share_pct"]:.1f}%', "ไม่ทราบตัวตนผู้ส่งคำสั่ง")
    with z[2]: panel("คุณภาพข้อมูล", f'{t["trades"]} trades', f'ครอบคลุม {t["window_sec"]} วินาทีล่าสุด · อายุ {t["sample_age_sec"]} วินาที')
    st.caption(f'OBSERVED_RECENT_FILLS · {t["source"]} · ข้อมูลจากตลาดเดียวกับแท่งราคา')
except DataUnavailable as exc:
    st.warning(f"TAPE DATA UNAVAILABLE · {exc} · ไม่มีการเดาค่า Buy/Sell Flow")

st.subheader("📚 Order Book · Snapshot เท่านั้น")
try:
    book = depth(venue, symbol)
    d = st.columns(3)
    with d[0]: panel("Spread", f'{book["spread_bps"]:.2f} bps')
    with d[1]: panel("Top-20 Bid depth share", f'{book["bid_depth_share_pct"]:.1f}%', "มูลค่าที่ตั้งรอ ไม่ใช่คำสั่งซื้อที่เกิดจริง")
    with d[2]: panel("สถานะ", "SNAPSHOT ONLY", "ภาพครั้งเดียวไม่ใช้ยืนยัน Absorption หรือ OFI")
except DataUnavailable as exc:
    st.warning(f"DEPTH UNAVAILABLE · {exc}")

st.markdown("**วิธีตีความ:** Tape = ธุรกรรมที่เกิดขึ้น, Depth = คำสั่งที่รอในสมุด, Candles = ผลรวมราคาในช่วงเวลา ทั้งสามอย่างไม่ควรถูกนำมาปะปนเป็น 'วาฬซื้อแน่นอน' โดยไม่มีหลักฐาน")
st.warning("ยังไม่มีหลักฐานว่า Market DNA ทำกำไรสุทธิได้หลังต้นทุน · ไม่ใช้เป็นคำสั่งเปิดสถานะเงินจริง โดยเฉพาะ Futures ที่มีความเสี่ยงสูง")
