"""Standalone Streamlit entrypoint for the isolated Orbit Model Lab experiment.

No CSV upload, account credentials, brokerage orders or production Telegram.
Live REST requests use public data from only the selected exchange.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import streamlit as st

from orbit_model_lab_engine import (DataUnavailable, MODELS, SYMBOLS, VENUES,
                                    ResearchSettings, fetch_candles,
                                    research_report, validate_candles)


st.set_page_config(page_title="Orbit Model Lab", page_icon="🪐", layout="wide")
st.markdown("""
<style>
.block-container {max-width:1100px; padding-top:1.1rem;}
div[data-testid="stMetric"] {background:#112b3a; color:white; padding:14px; border-radius:14px;}
div[data-testid="stMetric"] label {color:#c2e7e5 !important;}
.orbit-head {background:linear-gradient(115deg,#083148,#0c3541,#06483e);color:#fff;
    border-radius:20px;padding:23px;margin-bottom:14px;border:1px solid #3e827f;}
.orbit-head h1 {color:white;font-size:clamp(1.65rem,5vw,2.7rem);margin:0 0 4px;}
.orbit-head p {color:#c6eee7;margin:3px 0;}
</style>
""", unsafe_allow_html=True)
st.markdown("""<div class="orbit-head"><h1>🪐 Orbit Model Lab 2.0</h1>
<p>สแกนตลาดจริง · เปรียบเทียบ 4 Playbooks · Backtest หลังหักต้นทุน</p>
<p>แอปทดลองแยกจาก Orbit หลัก | READ ONLY · PAPER RESEARCH</p></div>""",
            unsafe_allow_html=True)
st.warning("⚠️ ไม่มีโมเดลใดรับประกันกำไร แอปนี้ไม่สั่งซื้อขายและไม่เปลี่ยน Telegram เดิม "
           "ผล Backtest ใช้เพื่อศึกษาความเสี่ยง ไม่ใช่การอนุมัติให้เข้าเทรด")


@st.cache_data(ttl=180, show_spinner=False)
def history(venue: str, symbol: str, days: int) -> pd.DataFrame:
    return fetch_candles(venue, symbol, days)


def demo_candles() -> pd.DataFrame:
    """Explicitly marked synthetic data, only for checking UI/algorithm."""
    rng = np.random.default_rng(20261103)
    count = 2500
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    end_ms = now_ms // 300_000 * 300_000
    opened = end_ms - np.arange(count, 0, -1) * 300_000
    increments = rng.normal(0, 0.0035, count)
    prices = 100 * np.exp(np.cumsum(increments))
    opening = np.concatenate(([100], prices[:-1]))
    high = np.maximum(opening, prices) * (1 + rng.uniform(0, .0012, count))
    low = np.minimum(opening, prices) * (1 - rng.uniform(0, .0012, count))
    frame = pd.DataFrame({"open_ms": opened, "open": opening, "high": high,
                          "low": low, "close": prices,
                          "volume": rng.uniform(1000, 14000, count)})
    return validate_candles(frame, now=datetime.now(timezone.utc))


with st.container(border=True):
    st.markdown("#### ⚙️ เลือกตลาดและต้นทุนที่ใช้จริง")
    left, mid, right = st.columns([1.25, 1, .7])
    with left:
        venue = st.selectbox("Exchange", list(VENUES),
                             format_func=lambda x: VENUES[x][0])
    with mid:
        symbol = st.selectbox("เหรียญ", SYMBOLS, index=0)
    with right:
        days = st.selectbox("ย้อนหลัง", (7, 14, 30), index=1,
                            format_func=lambda d: f"{d} วัน")
    fee_col, slip_col, risk_col = st.columns(3)
    with fee_col:
        fee_bps = st.number_input("Fee ต่อข้าง (bps)", min_value=0.0,
                                  max_value=100.0, value=10.0, step=1.0)
    with slip_col:
        slip_bps = st.number_input("Slippage ต่อข้าง (bps)", min_value=0.0,
                                   max_value=100.0, value=5.0, step=1.0)
    with risk_col:
        risk_pct = st.number_input("Risk/Trade (%)", min_value=0.1,
                                   max_value=2.0, value=0.5, step=0.1)
    refresh_col, mode_col = st.columns([1, 2])
    with refresh_col:
        refresh = st.button("🔄 โหลดข้อมูลตลาดล่าสุด", use_container_width=True)
    with mode_col:
        mode = st.radio("แหล่งข้อมูล", ("ข้อมูลตลาดจริง", "ข้อมูลจำลองสำหรับทดสอบ"),
                        horizontal=True, label_visibility="collapsed")

if refresh:
    history.clear()
settings = ResearchSettings(fee_each_side_bps=float(fee_bps),
                            slippage_each_side_bps=float(slip_bps),
                            risk_pct=float(risk_pct))

st.caption(f"ต้นทุนไป–กลับที่ใช้ใน Backtest = {settings.round_trip_bps:.0f} bps "
           f"({settings.round_trip_bps/100:.2f}% ของมูลค่าดีล) · "
           "ค่า Fee ที่กรอกเป็นสมมติฐาน ผู้ใช้ควรตรวจบัญชี/ระดับ VIP ของ Exchange จริง")

try:
    if mode == "ข้อมูลตลาดจริง":
        with st.spinner("กำลังโหลดแท่งเทียน 5m ที่ปิดแล้วจากตลาดที่เลือก..."):
            candles = history(venue, symbol, days)
        source = VENUES[venue][0]
        st.success(f"✅ ข้อมูลตลาดจริง: {source} · {symbol} · {len(candles):,} แท่ง 5m")
    else:
        candles = demo_candles()
        source = "SYNTHETIC DEMO — ไม่ใช่ตลาดจริง"
        st.error("🧪 DEMO DATA · ราคาจำลองทั้งหมด ห้ามนำราคาและผลทดสอบไปใช้เทรด")
    report, raw, features = research_report(
        candles, settings, allow_short=(venue != "BINANCE_TH_SPOT" and mode == "ข้อมูลตลาดจริง"))
except (DataUnavailable, ValueError, KeyError, IndexError, ZeroDivisionError) as exc:
    st.error(f"⛔ DATA BLOCK · {exc}")
    st.info("ระบบไม่สร้างราคาปลอมหรือใช้ข้อมูลอีก Exchange แทน ให้ลองรีเฟรช "
            "หรือเลือกตลาดอื่นที่ต้องการศึกษาด้วยตนเอง")
    st.stop()

last_closed = features.index[-1].to_pydatetime()
last_close = float(features.close.iloc[-1])
col1, col2, col3 = st.columns(3)
col1.metric("Close ล่าสุด · 5m", f"{last_close:.8f}" if last_close < .01 else f"{last_close:,.4f}")
col2.metric("แท่งปิดแล้ว", f"{len(features):,}")
col3.metric("ต้นทุนไป–กลับ", f"{settings.round_trip_bps:.0f} bps")
st.caption(f"แหล่งข้อมูล: {source} · แท่ง 5m เปิดเวลา {last_closed:%Y-%m-%d %H:%M} UTC "
           "(ราคาปิดของแท่ง ไม่ใช่ Bid/Ask สดหรือราคาที่ส่งคำสั่งได้)")

tab1, tab2, tab3 = st.tabs(("📡 Radar", "🧪 Backtest", "🩺 Data & Risk"))

with tab1:
    st.subheader("สถานะโมเดลจากแท่ง 5m ล่าสุด")
    st.caption("สัญญาณเกิดหลังแท่งปิด; ราคาเข้าจำลองเร็วที่สุดคือ Open แท่งถัดไป "
               "จึงไม่แสดงราคา Entry/TP/SL ที่รับรองการส่งคำสั่งได้")
    for name in MODELS:
        sig = int(raw[name]["signals"].iloc[-1])
        holdout = report[(report.Model == name) & (report.Window == "Holdout 30%")].iloc[0]
        verdict = str(holdout["Verdict"])
        if sig:
            state = "🟡 LONG WATCH" if sig > 0 else "🟠 SHORT WATCH"
        else:
            state = "⚪ NO PATTERN"
        with st.container(border=True):
            st.markdown(f"**{name}** · {state}")
            st.caption(f"ผล Holdout: {verdict} · {int(holdout['Trades'])} ดีล "
                       "· ยังไม่มี READY หรือคำแนะนำซื้อขาย")
    if mode == "ข้อมูลตลาดจริง":
        st.info("📌 แม้มี WATCH ระบบก็ยังไม่เปิดคำสั่ง Futures และไม่ปลดล็อก READY "
                "จนกว่าจะผ่านการทดสอบอย่างเพียงพอ")

with tab2:
    st.subheader("Train 70% / Holdout 30% · ค่าธรรมเนียมรวมแล้ว")
    st.dataframe(report, hide_index=True, use_container_width=True,
                 column_config={"Win %": st.column_config.NumberColumn(format="%.1f%%"),
                                "Mean net/trade %": st.column_config.NumberColumn(format="%.3f%%"),
                                "Profit factor": st.column_config.NumberColumn(format="%.2f"),
                                "Capital return %": st.column_config.NumberColumn(format="%.2f%%"),
                                "Max closed-trade DD %": st.column_config.NumberColumn(format="%.2f%%")})
    model = st.selectbox("ดูดีลย้อนหลัง", MODELS)
    trades = raw[model]["holdout"]
    if trades.empty:
        st.info("ไม่มีดีลที่ปิดครบในช่วง Holdout ไม่สามารถประเมินความแม่นยำได้")
    else:
        st.dataframe(trades.tail(40), hide_index=True, use_container_width=True)
        equity = (1 + trades.capital_return_pct / 100).cumprod()
        st.line_chart(pd.DataFrame({"Paper capital index": equity.values},
                                   index=pd.DatetimeIndex(trades.time)))
    st.warning("ผลนี้เป็นการจำลอง ไม่ใช่เงินจริง: หัก Fee/Slippage ที่ตั้งไว้แล้ว "
               "แต่ยังไม่มี Historical Order Book, Funding, Margin, Latency, "
               "Liquidation และ Market Impact จึงไม่ใช่ผลตอบแทนที่รับประกัน")

with tab3:
    st.subheader("ข้อจำกัดด้านข้อมูลและเกณฑ์อนุมัติ")
    st.markdown("""
- ✅ แท่งเทียนมาจาก Exchange ที่เลือกเท่านั้น ไม่มี Spot→Futures ทดแทน
- ✅ ตรวจความต่อเนื่องของแท่ง 5m, รูปแบบ OHLC และเวลาปิดล่าสุด
- ✅ ใช้เฉพาะแท่งที่ปิดแล้วและเข้าจำลองที่ **แท่งถัดไป**
- ✅ มี Stop, Target 2R, Time Exit และนับ Stop ก่อน Target เมื่อชนพร้อมกัน
- 🟡 ค่า Fee/Slippage เป็นสมมติฐาน ต้องตรวจให้ตรงบัญชีจริง
- ⚪ ยังคงต้องการข้อมูล Funding, Book/Trades ย้อนหลังและ Forward Paper Trading
- ⛔ ไม่ส่งคำสั่งเทรด ไม่ใช้ Leverage และไม่แก้ระบบแจ้งเตือนเดิม
""")
    st.info("เกณฑ์ RESEARCH PASS: Holdout อย่างน้อย 100 ดีล/โมเดล, "
            "Profit Factor ≥1.20, กำไรเฉลี่ยสุทธิบวก และ Drawdown จากดีลปิด ≤10%. "
            "ผ่านเกณฑ์นี้ก็ยังเป็น PAPER ONLY ไม่ใช่การรับรองกำไร")
    st.caption("หมายเหตุ: เปรียบเทียบหลายโมเดลบน Holdout เดียวกันอาจเกิด selection bias "
               "และ Max Drawdown ที่เห็นวัดจากดีลที่ปิด ไม่ใช่ Intraday Mark-to-Market")

st.divider()
st.caption("Orbit Model Lab 2.0 · experiment/orbit-model-lab · แยกจาก main / Telegram เดิม")
