"""Orbit Paper Trading page: hypothetical positions only, no exchange orders."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orbit_model_lab_engine import DataUnavailable, VENUES, SYMBOLS, fetch_candles, validate_candles
from orbit_live_planner import build_live_plan
from orbit_paper_simulator import (
    PaperError, new_account, request_paper_position, advance_account, cancel_pending,
    account_metrics, estimate_open_net, dump_account, load_account,
)

st.set_page_config(page_title="Orbit · Paper Trading", page_icon="🧪",layout="wide")
st.markdown("""
<style>
html,body,.stApp,[data-testid="stAppViewContainer"] {background:#061522!important;color:#f6fcff!important}
[data-testid="stAppViewContainer"] .block-container {max-width:1080px;padding:1rem 1rem 4rem!important}
[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,[data-testid="stMarkdownContainer"] h3,
[data-testid="stWidgetLabel"] p,[data-testid="stCaptionContainer"] *,
[data-testid="stAlert"] *,label {color:#f8fcff!important;opacity:1!important}
[data-baseweb="select"]>div,[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"]>div>div {background:#15364a!important;color:white!important;border-color:#80a9bd!important}
[data-baseweb="select"] *{color:white!important}
[data-testid="stButton"] button[kind="primary"]{background:#1ad8aa!important;color:#07251f!important;font-weight:900!important}
[data-testid="stButton"] button[kind="primary"] *{color:#07251f!important}
.paper-hero{border:2px solid #4b99b3;background:linear-gradient(110deg,#123648,#081e37);
border-radius:20px;padding:20px;margin-bottom:12px}
.paper-hero h1 {font-size:clamp(1.7rem,4.8vw,2.5rem)!important;color:#fff!important;margin:0 0 9px}
.paper-hero p{color:#e4f4fb!important;font-size:16px;font-weight:700}
.paper-card{padding:17px;background:#123246;border:1.5px solid #528da7;
border-radius:17px;margin:8px 0;overflow-wrap:anywhere}
.paper-label{color:#d8edfb!important;font-size:15px;font-weight:750}
.paper-value{color:#fff!important;font-size:clamp(1.4rem,3.5vw,2rem);font-weight:900;
font-variant-numeric:tabular-nums}
.paper-note{font-size:14px;color:#ddecf7!important;font-weight:650}
@media(max-width:680px){[data-testid="stAppViewContainer"] .block-container{padding:.7rem .65rem 4rem!important}
.paper-card{padding:13px}}
</style>""",unsafe_allow_html=True)

def fmt(v):
    if v is None:return "—"
    if v<.00001:return f"{v:.10f}".rstrip("0").rstrip(".")
    if v<.01:return f"{v:.8f}".rstrip("0").rstrip(".")
    return f"{v:,.4f}"

def card(label,value,note=""):
    st.markdown(f'<div class="paper-card"><div class="paper-label">{escape(str(label))}</div>'
                f'<div class="paper-value">{escape(str(value))}</div>'
                f'<div class="paper-note">{escape(str(note))}</div></div>',unsafe_allow_html=True)

@st.cache_data(ttl=90,show_spinner=False)
def get_bars(venue,symbol,days):
    return fetch_candles(venue,symbol,days)

st.markdown('<div class="paper-hero"><h1>🧪 ORBIT PAPER TRADING</h1>'
            '<p>ฝึกทดสอบสมมติฐาน BUY/LONG/SHORT ด้วยเงินจำลอง • ไม่มีการซื้อขายเงินจริง</p>'
            '</div>',unsafe_allow_html=True)
st.warning("PAPER ONLY · การจับคู่ราคาและผลกำไรเป็นการจำลองด้วยแท่ง OHLC 5 นาที ไม่ได้เปิดสถานะจริง ไม่มีการใช้ API Key หรือ Leverage")

if "orbit_paper" not in st.session_state:
    st.session_state.orbit_paper=new_account()
account=st.session_state.orbit_paper
active=account["active"]

# Backup controls are deliberately above market-data calls: still available if an API fails.
with st.expander("💾 สำรอง / กู้คืนบัญชี",expanded=False):
    st.download_button("⬇️ ดาวน์โหลดบัญชี JSON",dump_account(account).encode("utf-8"),
                       file_name="orbit_paper_account.json",mime="application/json",use_container_width=True)
    file=st.file_uploader("นำเข้าไฟล์ JSON ที่สำรองไว้",type=["json"])
    if file is not None and st.button("📥 กู้คืนบัญชี",use_container_width=True):
        try:
            st.session_state.orbit_paper=load_account(file.getvalue())
            st.rerun()
        except PaperError as e: st.error(str(e))
    st.caption("ข้อมูลอยู่ใน Streamlit Session เท่านั้น ถ้าแอปรีสตาร์ตให้กู้คืนจาก JSON")
if active and active["status"]=="PENDING":
    if st.button("ยกเลิกคำขอจำลองที่ยังรอจับคู่",key="cancel_top"):
        st.session_state.orbit_paper=cancel_pending(account)
        st.rerun()

st.subheader("💼 บัญชีทดลอง")
m=account_metrics(account)
a,b,c=st.columns(3)
with a: card("ทุนตั้งต้น",f'{account["starting_usdt"]:,.2f} USDT')
with b: card("ยอดคงเหลือจากดีลปิด",f'{m["balance_usdt"]:,.2f} USDT')
with c: card("กำไร/ขาดทุนสะสม",f'{m["realized_usdt"]:+,.2f} USDT',"ยังไม่รวมสถานะเปิด")
st.caption(f'ปิดแล้ว {m["trades"]} ดีล · Win Rate {m["win_rate"]:.1f}%' if m["win_rate"] is not None
           else "ยังไม่มีดีลปิด จึงไม่มี Win Rate")

st.subheader("📡 ตลาดและเหรียญ")
if active:
    venue,symbol=active["venue"],active["symbol"]
    st.info("มีสถานะทดลองอยู่ จึงล็อกตลาดและเหรียญจนกว่าจะปิดสถานะ")
    st.write(f"**{VENUES[venue][0]} · {symbol}**")
else:
    x,y=st.columns(2)
    with x:venue=st.selectbox("ตลาด",list(VENUES),format_func=lambda z:VENUES[z][0])
    with y:symbol=st.selectbox("เหรียญ",SYMBOLS)
if st.button("🔄 ตรวจแท่ง 5 นาทีล่าสุด",use_container_width=True):
    get_bars.clear();st.rerun()

try:
    now=datetime.now(timezone.utc)
    days=7
    if active:
        age_days=(now.timestamp()*1000-active["requested_ms"])/86400000
        days=30 if age_days>12 else (14 if age_days>5 else 7)
    bars=validate_candles(get_bars(venue,symbol,days),now=now)
    if active:
        account=advance_account(account,bars,now=now)
        st.session_state.orbit_paper=account
        active=account["active"]
    current=float(bars.close.iloc[-1])
    closed=(bars.index[-1].to_pydatetime()+pd.Timedelta(minutes=5))
except (DataUnavailable,PaperError) as e:
    st.error(f"DATA BLOCK · {e}")
    st.warning("ไม่เดาราคาเมื่อข้อมูลหาย/ล่าช้า และไม่ใช้ตลาดอื่นแทน")
    st.stop()
except Exception:
    st.error("DATA ERROR · ไม่สามารถตรวจสอบราคาจากตลาดที่เลือก")
    st.stop()

th=closed.astimezone(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M")
st.caption(f"{VENUES[venue][0]} · {symbol} · 5m ปิดล่าสุด {th} (ไทย) · {len(bars):,} แท่ง")
x,y=st.columns(2)
with x: card("ราคาปิด 5m อ้างอิง",fmt(current),"ไม่ใช่ Bid/Ask ปัจจุบัน")
with y: card("สถานะจำลอง",active["status"] if active else "ไม่มีสถานะ")
with st.expander("📈 ดูกราฟราคา 5m"):
    st.line_chart(bars.close.tail(120),height=250)

plan=None
try:
    plan=build_live_plan(bars,venue)
    st.info(f"Orbit Planner: {plan.status} · {plan.regime} · เป็นสัญญาณวิจัย ยังไม่พิสูจน์ผลกำไร")
except DataUnavailable:
    st.info("ข้อมูลไม่พร้อมให้ Orbit Planner ประเมิน แต่ยังเก็บสมมติฐานส่วนตัวได้")

if active and active["status"]=="PENDING":
    st.subheader("⏳ รอจำลองการเข้า")
    st.write(f"**{active['direction']} · {symbol}** · จะใช้ OPEN ของแท่ง 5m ที่เริ่มหลังเวลาขอเปิด")
    st.caption("ต้องรอแท่งนั้นปิดก่อนจึงบันทึกผลจำลองได้ ไม่ใช้ราคาจากอดีตมาเป็น Fill ทันที")
elif active and active["status"]=="OPEN":
    st.subheader("📍 สถานะจำลองที่ยังเปิด")
    x,y,z=st.columns(3)
    with x: card("ENTRY",fmt(active["entry_exec"]))
    with y: card("STOP",fmt(active["stop"]))
    with z: card("TP",fmt(active["target"]))
    card("กำไร/ขาดทุนค้าง (ประมาณ)",f'{estimate_open_net(active,current):+,.4f} USDT',
         "Mark-to-market จากแท่งปิดและต้นทุนสมมติ ยังไม่ใช่กำไรจริง")
    st.caption(f'ถือแล้ว {active["bars_held"]}/{active["max_hold_bars"]} แท่ง · '
               f'Notional {active["notional_usdt"]:.2f} USDT · ไม่มี Leverage')
    st.warning("ปิดจำลองเมื่อแท่งใหม่แตะ Stop/TP หรือครบเวลา เมื่อแตะทั้งสองฝั่งในแท่งเดียวจะนับ Stop ก่อน")
else:
    st.subheader("🎮 ทดลองสร้างสถานะ Paper")
    origin=st.radio("ต้นทางของสมมติฐาน",["ทดลองจากความคิดฉัน","จำลองตาม SIGNAL ของ Orbit"],horizontal=True)
    valid=bool(plan and plan.status.startswith("SIGNAL ") and
               plan.direction in ({"BUY"} if venue=="BINANCE_TH_SPOT" else {"LONG","SHORT"}))
    if origin=="จำลองตาม SIGNAL ของ Orbit" and not valid:
        st.warning("Orbit ยังไม่มี SIGNAL ยืนยันในแท่งล่าสุด จึงไม่เปิด Paper ตามโมเดล แต่สามารถทดสอบสมมติฐานตัวเองได้")
    x,y=st.columns(2)
    with x:
        if origin=="จำลองตาม SIGNAL ของ Orbit" and valid:
            direction="LONG" if plan.direction in ("BUY","LONG") else "SHORT"
            st.write(f"**ทิศทางที่ Orbit ยืนยัน:** {direction}")
        else:
            direction=st.radio("ทิศทาง",["LONG"] if venue=="BINANCE_TH_SPOT" else ["LONG","SHORT"],horizontal=True)
        risk=st.selectbox("ความเสี่ยงสูงสุดต่อสถานะ (ทุนจำลอง)",[.25,.5,1.],index=0,format_func=lambda v:f"{v:g}%")
        stop=st.number_input("ระยะ Stop จาก Entry (%)",min_value=.2,max_value=5.,value=1.,step=.1)
    with y:
        reward=st.selectbox("ระยะ TP เมื่อเทียบกับ Stop",[1.,1.5,2.,2.5,3.],index=2,format_func=lambda v:f"{v:g}R")
        fee=st.number_input("Fee ต่อข้าง (bps)",min_value=0.,max_value=100.,value=10.,step=1.)
        slip=st.number_input("Slippage สมมติต่อข้าง (bps)",min_value=0.,max_value=100.,value=5.,step=1.)
    hold=st.selectbox("หมดอายุการถือ (ไม่มี TP/SL)",[12,24,48,96],index=1,format_func=lambda n:f"{5*n} นาที")
    st.caption("ขนาดสถานะคำนวณจากทุนจำลองและ Risk Budget ไม่ใช้ Leverage · ไม่ส่งคำสั่ง Exchange")
    if st.button("🧪 เปิดสถานะจำลองเท่านั้น",type="primary",use_container_width=True,
                 disabled=(origin=="จำลองตาม SIGNAL ของ Orbit" and not valid)):
        try:
            st.session_state.orbit_paper=request_paper_position(
                account,venue=venue,symbol=symbol,direction=direction,
                requested_at=datetime.now(timezone.utc),reference_close=current,
                risk_pct=risk,stop_pct=stop,reward_r=reward,fee_bps=fee,
                slippage_bps=slip,max_hold_bars=hold,
                source="ORBIT_PAPER_SIGNAL" if origin=="จำลองตาม SIGNAL ของ Orbit"
                       else "MANUAL_PAPER_HYPOTHESIS")
            st.rerun()
        except PaperError as e:st.error(str(e))

st.subheader("📑 Paper Journal")
m=account_metrics(account)
if account["trades"]:
    history=pd.DataFrame(account["trades"][::-1])
    cols=["source","symbol","direction","entry","exit","reason","net_usdt","balance_after_usdt"]
    st.dataframe(history[cols],hide_index=True,use_container_width=True)
    st.download_button("⬇️ ส่งออก CSV",history.to_csv(index=False).encode("utf-8-sig"),
                       file_name="orbit_paper_trades.csv",mime="text/csv",use_container_width=True)
    st.caption(f'จำนวนดีลปิด {m["trades"]} · Max Closed-trade Drawdown {m["max_drawdown_pct"]:.2f}%')
else:st.info("ยังไม่มีดีลที่ปิด ผลกำไรและ Win Rate จะปรากฏเมื่อการจำลองปิดสถานะ")

st.download_button("💾 สำรอง JSON ล่าสุด",dump_account(account).encode("utf-8"),
                   file_name="orbit_paper_account.json",mime="application/json",use_container_width=True)
with st.expander("⚙️ เริ่มบัญชีจำลองใหม่"):
    capital=st.number_input("ทุนเริ่มต้นใหม่ (USDT)",min_value=10.,max_value=100000.,value=75.)
    confirm=st.checkbox("เข้าใจว่าประวัติใน Session จะหายถ้าไม่ได้สำรอง JSON")
    if st.button("รีเซ็ตบัญชีจำลอง",disabled=not confirm):
        st.session_state.orbit_paper=new_account(capital)
        st.rerun()

st.caption("ข้อจำกัด: ไม่มี Funding, Liquidation, Partial Fill, Bid/Ask แบบสด หรือการเปิดสถานะจริง; หากข้อมูล 5m ขาดช่วง ระบบจะหยุดแทนการเดาราคาย้อนหลัง")
