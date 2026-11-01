"""Orbit v5.0 mobile-first Spot/Futures/Alerts screens.

The deep research and frozen-plan editor remain in app.py (Lab screen).
Only read-only public market data; no exchange API keys or orders.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from binance_data import fetch_klines
from futures_daytrade import (FuturesDataError, evaluate_futures, fetch_futures_catalog,
                              fetch_futures_klines, fetch_futures_ticker,
                              read_futures_settings)
from futures_paper import paper_stats
from futures_backup import fetch_backup_pair, fetch_backup_klines, fetch_backup_ticker
from futures_kraken_backup import fetch_kraken_pair, fetch_kraken_klines, fetch_kraken_ticker
from futures_research import evaluate_historical_proxy, fetch_history
from futures_symbols import FuturesPair, resolve_futures_pair
from mobile_logic import PAIRS, SignalLook, concise_price, futures_look, normalize_symbol, spot_look
from monitor_engine import analyze_symbol, read_settings
from watch_plans import decode_watch
from indicative_zones import indicative_zone, support_resistance


ROOT = Path(__file__).resolve().parent
BKK = ZoneInfo("Asia/Bangkok")
SPOT = "🎯 Spot"
FUTURES = "⚡ Futures"
SCALP = "⏱️ Scalp"
ALERTS = "🔔 Alerts"
LAB = "🔬 Lab"


def style() -> None:
    st.markdown("""
<style>
/* Orbit v5.0: mobile-first, roomy touch targets, intentional visual hierarchy. */
:root { color-scheme: dark; }
[data-testid="stAppViewContainer"] {
  background: radial-gradient(ellipse 100% 450px at 50% -75px, #1b4654 0%, #0c2130 48%, #07121f 83%, #060c16 100%);
  color: #e8f1f7;
}
.block-container { max-width: 1000px; padding-top: 1.1rem; padding-bottom: 7rem; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { background: #0b1825; }
.orb-brand { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin: 0 0 15px; }
.orb-brand-left { display: flex; align-items: center; gap: 11px; }
.orb-mark { width: 43px; height: 43px; flex: 0 0 43px; border-radius: 15px;
  display: grid; place-items: center; font-size: 25px; color: #041119;
  background: linear-gradient(145deg,#a0ffe1,#45e3ba 55%,#43acee); box-shadow: 0 5px 30px #3acfac40; }
.orb-name { font-size: clamp(18px,4.8vw,27px); font-weight: 850; color: #f0f9ff; line-height: 1.05;
  letter-spacing: -.75px; }
.orb-name em { font-style: normal; color: #70e9bb; }
.orb-version { color: #d1e5f1; font-size: 12px; margin-top: 5px; letter-spacing: .8px; font-weight:700; }
.orb-live { white-space: nowrap; color: #85eac1; background:#0d302e;
  border:1px solid #1e6157; font-size:10px; letter-spacing:.5px;
  font-weight:800; padding:7px 9px; border-radius:40px; }
.orb-section { display:flex; justify-content:space-between; align-items:center; gap:10px;
  margin-top:11px; margin-bottom:9px; }
.orb-section strong { color:#e9f5fa; font-size:17px; font-weight:780; }
.orb-subtle { color:#d3e5f0; font-size:13px; font-weight:600; }
.orb-hero { border:1px solid #36586b; background: linear-gradient(125deg,#173849,#0b2231 67%,#17294c);
  box-shadow: 0 15px 42px #00000045; border-radius:24px; padding:21px;
  margin: 13px 0 10px; overflow:hidden; }
.orb-hero.good {border-color:#287967; background:linear-gradient(115deg,#12342f,#0d202f 70%);}
.orb-hero.danger {border-color:#7b344a; background:linear-gradient(115deg,#361d2d,#111e2e 80%);}
.orb-hero.warning {border-color:#65603e;}
.orb-hero-title {font-size:14px; color:#e1eff6; margin-bottom:5px; font-weight:700;}
.orb-hero-value {font-size:clamp(25px,7vw,39px); font-weight:850; letter-spacing:-.9px;
  line-height:1.13; color:#f5fbff; overflow-wrap:anywhere; font-variant-numeric:tabular-nums;}
.orb-hero-detail { margin-top:9px; display:flex; flex-wrap:wrap; align-items:center; gap:7px; }
.orb-chip {display:inline-flex; align-items:center; border-radius:40px; font-weight:800;
  font-size:11px; padding:6px 10px; letter-spacing:.35px;}
.orb-chip.good {background:#134435;color:#90ffd4;}
.orb-chip.warning {background:#473e22;color:#ffdc91;}
.orb-chip.danger {background:#4b2433;color:#ffabb8;}
.orb-chip.neutral {background:#293b4d;color:#d2e2ec;}
.orb-hero-note { font-size:13px; color:#d1e2ea; padding-top:10px; line-height:1.45; }
.orb-kv-grid {display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; margin:10px 0 14px;}
.orb-kv {border:1px solid #2c4b59; background:linear-gradient(145deg,#142c39,#0c1d2c);padding:15px 13px;border-radius:17px;min-width:0;}
.orb-kv b {font-size:clamp(14px,3.8vw,21px);display:block; color:#eefaff; margin-top:6px;
  overflow-wrap:anywhere; letter-spacing:-.3px; font-variant-numeric:tabular-nums;}
.orb-kv-label {color:#d8e9f2;font-size:13px;font-weight:750;letter-spacing:.2px;}
.orb-pair-grid {display:grid; grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:9px 0;}
.orb-pair {background:#10202e;border:1px solid #264152;border-radius:15px;padding:14px 12px;}
.orb-pair.active-long {border-color:#1eab7e;background:#11362d;}
.orb-pair.active-short {border-color:#da687d;background:#352332;}
.orb-pair h4 {margin:0;color:#edf7fa;font-size:15px;}
.orb-pair p {margin:5px 0 0;color:#d7e7f0;font-size:13px;line-height:1.5;}
.orb-footnote {font-size:13px; color:#c8e0ef; padding:9px 0 2px;line-height:1.55;}
/* Scalp watch levels: high contrast and tabular digits even on small phones. */
.orb-zone {background:#122f40;border:1px solid #4e8298;border-radius:16px;
  padding:16px;margin:10px 0;box-shadow:0 4px 18px #0005;}
.orb-zone.in-zone {border-color:#f2cb6b;background:#302d25;}
.orb-zone.invalid {border-color:#ca7281;background:#322530;}
.orb-zone-head {display:flex;justify-content:space-between;align-items:center;gap:8px;
  flex-wrap:wrap;color:#f1f8ff;font-size:16px;font-weight:800;}
.orb-zone-state {font-size:13px;font-weight:800;color:#ffe3a0;}
.orb-zone-prices {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:11px 0;}
.orb-zone-price {background:#061b29;border:1px solid #456c7f;border-radius:11px;padding:10px;
  min-width:0;color:#fff;font-size:clamp(17px,4.7vw,25px);line-height:1.35;
  font-weight:850;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;letter-spacing:.1px;}
.orb-zone-price small {display:block;font-size:12px;color:#c6dce8;margin-bottom:5px;font-weight:700;}
.orb-zone-sub {color:#e0eff8;font-size:14px;line-height:1.6;}
/* v5.9 readability patch: keep every trade state and risk calculation unchanged. */
[data-testid="stMarkdownContainer"] > p,
[data-testid="stMarkdownContainer"] > ul > li,
[data-testid="stMarkdownContainer"] > ol > li { color:#edf6fc; line-height:1.65; }
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p,
div[data-testid="stMetricLabel"] { color:#d2e5f1 !important; font-size:13px; font-weight:650; }
div[data-testid="stMetricValue"] { color:#f7fcff !important; font-weight:800; }
[data-testid="stWidgetLabel"] p,
[data-testid="stExpander"] summary,
[data-testid="stAlert"] p { color:#f1f8fd !important; font-weight:650; }
div[data-testid="stSegmentedControl"] button,
div[data-testid="stPills"] button {font-weight:800 !important;}
div[data-testid="stSegmentedControl"] button p,
div[data-testid="stPills"] button p {color:inherit !important;}
div[data-testid="stSegmentedControl"] button, div[data-testid="stPills"] button {min-height:42px;}
div[data-testid="stSegmentedControl"] button {border-radius:14px !important; font-weight:750;}
div.st-key-orbit_screen {background:#0a1d2be8;border:1px solid #224657;border-radius:18px;padding:6px;backdrop-filter:blur(16px);}
[data-testid="stVerticalBlockBorderWrapper"] {border-color:#254057;}
div.stButton > button {min-height:45px; border-radius:13px; font-weight:750;}
/* Streamlit's light secondary-button defaults were nearly invisible on dark Orbit. */
div.stButton > button, div.stDownloadButton > button,
div.stFormSubmitButton > button {
  background:#163749 !important; color:#efffff !important;
  border:1px solid #3e7780 !important;
}
div.stButton > button p, div.stDownloadButton > button p,
div.stFormSubmitButton > button p {color:inherit !important;}
div.stButton > button:disabled, div.stDownloadButton > button:disabled {
  background:#1d303b !important; color:#a2b4c0 !important;
  border-color:#526c7c !important; opacity:1 !important;
}
div.stButton > button:hover:not(:disabled), div.stDownloadButton > button:hover:not(:disabled) {
  background:#1d5c61 !important; border-color:#70e9bb !important;
}
/* Streamlit live DOM uses button[data-variant], not the older test-id wrappers.
   Keep every selector readable even when unselected controls default to white. */
button[data-variant="segmented_control"],
button[data-variant="pills"] {
  background:#193749 !important;
  color:#f5fbff !important;
  border:1px solid #5a8296 !important;
  opacity:1 !important;
  font-weight:800 !important;
}
button[data-variant="segmented_control"] p,
button[data-variant="pills"] p,
button[data-variant="segmented_control"] span,
button[data-variant="pills"] span {
  color:#f5fbff !important;
  opacity:1 !important;
}
button[data-variant="segmented_control"][aria-checked="true"],
button[data-variant="pills"][aria-checked="true"] {
  background:#174c49 !important; color:#e6fff5 !important;
  border-color:#55d7ae !important;
}
div[data-testid="stExpander"] {border:1px solid #263d4d; border-radius:14px; background:#0d1a28;}
@media(max-width:640px) {
 .block-container {padding:0.65rem 0.75rem 2.5rem !important;}
 .orb-brand {margin:1px 0 11px;}
 .orb-mark {width:38px;height:38px;flex-basis:38px;border-radius:13px;}
 .orb-live {font-size:9px;padding:6px 7px;}
 .orb-hero {padding:16px;margin-top:10px;border-radius:19px;}
 div[data-testid="stMetricValue"] {font-size:1.18rem;}
 div[data-testid="stMetricLabel"] {font-size:.75rem;}
 div[data-testid="stDataFrame"] {max-width:100%;}
 h2 {font-size:1.28rem!important;}
 /* Mobile: navigation stays in document flow. A fixed five-item control
    wrapped into two rows on iOS and covered zone prices and confirmation. */
 div.st-key-orbit_screen {position:static !important;inset:auto !important;
   margin-bottom:12px;box-shadow:none;}
 div.st-key-orbit_screen button {font-size:12px !important;min-height:44px !important;}
 div.st-key-orbit_screen [data-testid="stSegmentedControl"] {overflow-x:auto;}
}
</style>
""", unsafe_allow_html=True)


def top_navigation() -> str:
    st.markdown("""
<div class="orb-brand">
  <div class="orb-brand-left">
    <div class="orb-mark">◉</div>
    <div><div class="orb-name">ORBIT <em>LAB</em></div>
         <div class="orb-version">ULTIMATE SIGNAL · V5.9.2</div></div>
  </div>
  <div class="orb-live">● READ ONLY</div>
</div>
""", unsafe_allow_html=True)
    value = st.segmented_control("เลือกหน้าจอ", [SPOT, FUTURES, SCALP, ALERTS, LAB], default=SPOT,
                                 key="orbit_screen", width="stretch", label_visibility="collapsed")
    return value or SPOT


def chosen_symbol(watch_token: str | None = None) -> str:
    preferred = "PEPEUSDT"
    if watch_token:
        try:
            preferred = decode_watch(watch_token).symbol
        except (ValueError, TypeError):
            pass
    # Opening a new bookmarked ?watch= link must select its own coin, even
    # when a previous mobile coin widget already has session state.
    if watch_token and st.session_state.get("orbit_mobile_loaded_watch") != watch_token:
        st.session_state["orbit_mobile_pair"] = preferred if preferred in PAIRS else "🔎 อื่น ๆ"
        st.session_state["orbit_mobile_active_custom"] = preferred
        if preferred not in PAIRS:
            st.session_state["orbit_mobile_custom"] = preferred
        st.session_state["orbit_mobile_loaded_watch"] = watch_token
    if "orbit_mobile_pair" not in st.session_state:
        st.session_state["orbit_mobile_pair"] = preferred if preferred in PAIRS else "🔎 อื่น ๆ"
        if preferred not in PAIRS:
            st.session_state["orbit_mobile_custom"] = preferred
            st.session_state["orbit_mobile_active_custom"] = preferred
    selection = st.pills("เหรียญที่ติดตาม", [*PAIRS, "🔎 อื่น ๆ"],
                         selection_mode="single", key="orbit_mobile_pair", width="stretch",
                         label_visibility="collapsed")
    if selection and selection != "🔎 อื่น ๆ":
        return selection
    with st.container(border=True):
        raw = st.text_input("ค้นหาเหรียญอื่น · เช่น XRP, BONK, Bitcoin", key="orbit_mobile_custom",
                            placeholder="พิมพ์ชื่อเหรียญหรือคู่ USDT")
        try:
            symbol = normalize_symbol(raw)
        except ValueError:
            st.caption("ใส่ชื่อเหรียญ เช่น XRP หรือ XRPUSDT แล้วกดใช้เหรียญนี้")
            return st.session_state.get("orbit_mobile_active_custom", preferred)
        if st.button("ใช้เหรียญนี้", key="mobile_apply_custom", width="stretch"):
            st.session_state["orbit_mobile_active_custom"] = symbol
        return st.session_state.get("orbit_mobile_active_custom", preferred)


def _signal_card(look: SignalLook, symbol: str, price: float | None,
                 price_label: str, quote: str = "USDT") -> None:
    name = escape(symbol.replace("USDT", "/USDT"))
    st.markdown(f"""
<div class="orb-hero {look.tone}">
  <div class="orb-hero-title">{name} · {escape(price_label)}</div>
  <div class="orb-hero-value">{escape(concise_price(price))} <span style="font-size:14px;color:#91a9bc">{escape(quote)}</span></div>
  <div class="orb-hero-detail"><span class="orb-chip {look.tone}">{escape(look.tag)}</span></div>
  <div class="orb-hero-note"><b>{escape(look.title)}</b> · {escape(look.helper)}</div>
</div>""", unsafe_allow_html=True)


def _price_grid(items: list[tuple[str, float | None]]) -> None:
    cards = "".join(f'<div class="orb-kv"><span class="orb-kv-label">{escape(label)}</span>'
                    f'<b>{escape(concise_price(val))}</b></div>' for label, val in items)
    st.markdown(f'<div class="orb-kv-grid">{cards}</div>', unsafe_allow_html=True)


def _fixed_tp_panel(plan, *, approved_signal: bool = False) -> None:
    """Display an independent 10-USDT price-move plan with honest blockers."""
    label = "LONG" if plan.side == "LONG" else "SHORT"
    st.markdown(f"**{label} · TP ระยะราคา 10 USDT**"
                + (" · หลังยืนยันสัญญาณ" if approved_signal else " · ตัวอย่างจากราคาล่าสุด"))
    _price_grid([("ราคาอ้างอิง (USDT)", plan.entry),
                 ("ราคา TP +/−10 USDT", plan.target)])
    if plan.move_pct is not None:
        st.caption(f"ระยะราคา {plan.move_pct:,.3f}% · "
                   f"Notional จำลอง {plan.notional_usdt:.2f} USDT")
    if plan.gross_profit_usdt is not None:
        st.caption(f"กำไรก่อนต้นทุนประมาณ {plan.gross_profit_usdt:+.4f} USDT · "
                   f"Fee/Spread/Slippage ประมาณ {plan.estimated_cost_usdt:.4f} USDT · "
                   f"สุทธิประมาณ {plan.estimated_net_usdt:+.4f} USDT"
                   + (f" · Net R:R {plan.net_rr:.2f}:1" if plan.net_rr is not None else ""))
    if plan.state == "ALTERNATIVE_READY":
        st.success("🟢 TP 10 USDT ผ่านเกณฑ์จำลอง · " + plan.reason)
    elif plan.state == "WATCH_ONLY":
        st.info("⚪ TP 10 USDT เป็นเพียงตัวอย่างราคา · " + plan.reason)
    else:
        st.error("🔴 TP 10 USDT ไม่ผ่านเกณฑ์ · " + plan.reason)
    st.caption("10 USDT หมายถึงผลต่างของราคาต่อ 1 เหรียญ/สัญญาตามคู่ราคา "
               "ไม่ใช่กำไรสุทธิ 10 USDT ของทั้งไม้ · PAPER ONLY")


def _pepe_daily_ten_panel(plan, capital_thb: float, *, approved_signal: bool = False) -> None:
    """One simulated PEPE position with a 10-human-point target, not an order."""
    from scalp_fixed_tp import pepe_point_unit

    unit = pepe_point_unit(plan.entry)
    st.markdown("**🎯 PEPE · 1 ไม้/วัน · TP 10 จุด**" +
                (" · หลังยืนยันสัญญาณ" if approved_signal else " · ราคาเฝ้าดูเท่านั้น"))
    _price_grid([("ราคาอ้างอิง Entry (USDT)", plan.entry),
                 ("TP +10 จุด (USDT)", plan.target)])
    st.caption(f"นิยาม 1 จุด = {unit:f} USDT · 10 จุด = {unit * 10:f} USDT "
               "· หน่วยจุดปรับตามหลักทศนิยมของราคา PEPE ไม่ใช่ Tick ของตลาด")
    if plan.target is not None:
        gross_pct = (abs(plan.target - plan.entry) / plan.entry) * 100
        gross_thb = capital_thb * gross_pct / 100
        st.markdown(f"**กำไรขั้นต้นจำลองจากทุน {capital_thb:,.0f} บาท: "
                    f"+{gross_thb:,.2f} บาท (+{gross_pct:.2f}%)**")
        if plan.estimated_net_usdt is not None and plan.notional_usdt > 0:
            net_thb = capital_thb * plan.estimated_net_usdt / plan.notional_usdt
            st.caption(f"ประมาณการสุทธิหลัง Fee/Spread/Slippage: {net_thb:+,.2f} บาท "
                       "· สมมติใช้ทุนทั้งหมด ไม่มี Leverage และอัตราแลกเปลี่ยนคงที่")
    if plan.state == "ALTERNATIVE_READY" and approved_signal:
        st.success("🟢 แผน TP 10 จุดผ่านเกณฑ์จำลอง · ตรวจราคาจริงก่อนตัดสินใจ")
    elif plan.state == "WATCH_ONLY":
        st.info("⚪ ยังไม่ยืนยันจุดเข้า · " + plan.reason)
    else:
        st.error("🔴 ยังใช้ TP 10 จุดนี้ไม่ได้ · " + plan.reason)
    st.caption("เป้าหมายรายวันไม่ใช่การรับประกันกำไร · PAPER ONLY · "
               "ห้ามบังคับเปิดไม้เมื่อสัญญาณหรือความเสี่ยงไม่ผ่าน")


def _watch_price_panel(plan, title: str, quote: str = "USDT") -> None:
    """Always distinguish provisional levels from a validated entry plan."""
    st.markdown(f"### 🧭 {title} · ราคาเฝ้าดู")
    if plan is None:
        st.warning("ยังคำนวณโซนที่น่าเชื่อถือไม่ได้จากแท่งราคาที่ปิดแล้ว · "
                   "ไม่มีการใช้ราคาเดาหรือราคาจากตลาดอื่นทดแทน")
        return
    st.info("**คาดการณ์เพื่อเฝ้าดูเท่านั้น — ยังเข้าไม่ได้** · "
            "ตัวเลขปรับตามแท่งใหม่ ไม่ใช่คำสั่ง Limit หรือเป้ากำไรที่รับประกัน")
    _price_grid([("รอราคาเข้า · LOW", plan.low), ("รอราคาเข้า · HIGH", plan.high),
                 ("จุดยกเลิกสมมติฐาน", plan.invalidation),
                 ("เป้าหมายจำลอง 1", plan.target_1),
                 ("เป้าหมายจำลอง 2", plan.target_2)])
    st.caption(f"{quote} · อ้างอิง {plan.basis} · "
               "ถึงโซนต้องประเมินใหม่ทั้งแนวโน้ม Volume/Flow, Spread, Fee, "
               "Stop และ Net R:R; ถ้าไม่ผ่านยังคง WAIT")


def _support_resistance_panel(candles: pd.DataFrame, quote: str = "USDT",
                              current_price: float | None = None) -> None:
    st.markdown("### 📊 แนวรับ–แนวต้าน (แสดงไม่ว่าสถานะใด)")
    levels = support_resistance(candles)
    if levels is None:
        st.warning("ข้อมูลแท่งราคาที่ปิดแล้วไม่พอคำนวณแนวรับ–แนวต้าน")
        return
    support, resistance = levels
    broken_support = (current_price is not None and current_price > 0 and
                      current_price < support.low)
    broken_resistance = (current_price is not None and current_price > 0 and
                         current_price > resistance.high)
    st.markdown(
        '<div class="orb-zone-prices">'
        f'<div class="orb-zone-price"><small>{"🔴 แนวรับเดิมที่หลุด" if broken_support else "🟢 แนวรับ"} ({escape(quote)})</small>'
        f'{escape(concise_price(support.low))}<small>ถึง {escape(concise_price(support.high))}</small></div>'
        f'<div class="orb-zone-price"><small>{"🟠 แนวต้านเดิมที่ทะลุ" if broken_resistance else "🔴 แนวต้าน"} ({escape(quote)})</small>'
        f'{escape(concise_price(resistance.low))}<small>ถึง {escape(concise_price(resistance.high))}</small></div>'
        '</div>', unsafe_allow_html=True)
    if broken_support:
        st.warning("แนวรับอ้างอิงนี้อยู่เหนือราคาล่าสุดแล้ว จึงไม่ถือเป็นจุดรอซื้อ · "
                   "ต้องรอโครงสร้างแนวรับใหม่จากแท่งปิด")
    if broken_resistance:
        st.warning("แนวต้านอ้างอิงนี้อยู่ใต้ราคาล่าสุดแล้ว จึงไม่ถือเป็นจุดเปิด Short · "
                   "รอประเมินแนวต้านใหม่")
    st.caption("ประเมินจากแท่งราคาที่ปิดแล้วและ ATR · เป็นระดับเฝ้าดู ไม่ได้แปลว่าราคาจะเด้ง/ย่อตรงนี้แน่นอน")


@st.cache_data(ttl=45, show_spinner=False)
def _scalp_live(venue: str, symbol: str, refresh_id: int):
    """Independent, venue-native public data; never call exchange order APIs."""
    from scalp_engine import evaluate_scalp, read_scalp_settings
    from scalp_marketdata import fetch_snapshot

    settings = read_scalp_settings(ROOT / "scalp_config.json")
    snap = fetch_snapshot(venue, symbol)
    return evaluate_scalp(snap, settings), snap, settings


@st.cache_data(ttl=300, show_spinner=False)
def _whale_history_public(days: int):
    from whale_history import fetch_public_history
    return fetch_public_history(days=days)


@st.cache_data(ttl=300, show_spinner=False)
def _validation_history_public(days: int):
    from validation_history import fetch_public_history
    return fetch_public_history(days=days)


@st.cache_data(ttl=300, show_spinner=False)
def _near_history_public(days: int):
    from near_ready_history import fetch_public
    return fetch_public(days=days)


def _near_live_panel(snap, cfg, ob) -> None:
    """Research-only watch; NEVER promote an engine WAIT to trade READY."""
    try:
        from near_ready_tracker import near_candidates
        events = near_candidates(snap, cfg, ob)
        if not events:
            return
        st.markdown("### 🟡 NEAR READY · ใกล้ผ่านเกณฑ์ (ยังเข้าไม่ได้)")
        for event in events:
            st.warning(f"{event['sd']} · ผ่าน 4/5 เงื่อนไขเบื้องต้น · "
                       f"ยังขาด **{event['fail']}** · "
                       "รอยืนยันแท่ง 1m/5m และตรวจ Spread/Stop/ค่าธรรมเนียม/Net R:R "
                       "อีกครั้งก่อนอนุมัติ READY")
        st.caption("NEAR READY เป็นการเฝ้าดูเท่านั้น ไม่สร้าง Entry/TP/SL ใหม่ "
                   "ไม่ยกเลิก RISK BLOCK และไม่ใช่สัญญาณซื้อขาย")
    except (ValueError, TypeError, KeyError, IndexError, OverflowError):
        st.caption("Near Ready ยังประเมินไม่ได้จากข้อมูลรอบนี้ · ไม่ส่งผลต่อสัญญาณหลัก")


@st.cache_data(ttl=90, show_spinner=False)
def _spot_research_snapshot(symbol: str):
    """Explicit opt-in research source; NEVER handed to a Futures engine."""
    from scalp_marketdata import fetch_snapshot
    return fetch_snapshot("BINANCE_TH_SPOT", symbol)


@st.cache_data(ttl=240, show_spinner=False)
def _health_catalog_probe(venue: str, symbol: str):
    from futures_data_health import probe_catalog
    return probe_catalog(venue, symbol)


def _short_watch_panel(snap, *, substituted_source: bool = False) -> None:
    """This research panel never returns or changes an approved signal."""
    from short_opportunity import evaluate_short_watch
    watch = evaluate_short_watch(snap)
    st.markdown("### 📉 SHORT Opportunity Watch · เฝ้าดูแรงขาย")
    market = "Spot · Binance TH" if snap.venue == "BINANCE_TH_SPOT" else snap.venue
    st.caption(f"แหล่งข้อมูลจริง: {market} · {snap.symbol} · "
               f"ณ {snap.checked_at.astimezone(BKK):%d/%m/%Y %H:%M:%S} น. ไทย · "
               "ใช้แท่งที่ปิดแล้ว; ไม่เปิด SHORT ใน Spot")
    if substituted_source:
        st.error("⚠️ นี่คือ Spot Research เพื่ออธิบายทิศทางเท่านั้น "
                 "ห้ามใช้ราคา/Volume/Spread นี้แทนข้อมูล Futures ที่ถูกบล็อก "
                 "และห้ามยกระดับเป็น Futures READY")
    if watch.state == "SHORT_WATCH":
        st.warning("🟠 SHORT WATCH · " + watch.reason)
    elif watch.state == "EARLY_WATCH":
        st.info("🟡 EARLY SHORT WATCH · " + watch.reason)
    elif watch.state == "INSUFFICIENT_DATA":
        st.warning("⚪ SHORT DATA INCOMPLETE · " + watch.reason)
    else:
        st.info("⚪ NO SHORT SETUP · " + watch.reason)
    if watch.checks:
        with st.expander("🔍 หลักฐานฝั่ง Short จาก 1H/15m/5m/1m"):
            for label, ok, note in watch.checks:
                st.markdown(f"{'✅' if ok else '⚪'} **{label}** — {note}")
            st.caption("จำนวนข้อที่ผ่านไม่ใช่เปอร์เซ็นต์ชนะ "
                       "· ไม่ได้ทดสอบค่า Fee, Stop, Depth หรือ Net R:R ในส่วนเฝ้าดูนี้")
    st.caption("SHORT WATCH เป็นเพียงการสังเกตตลาด ไม่ใช่ Entry, Stop Loss, Take Profit "
               "หรือคำสั่ง Futures · READY เดิมต้องผ่านกฎครบแยกต่างหาก")


def _data_health_panel(venue: str, symbol: str, *, snap=None, error: str | None = None) -> None:
    """Explain upstream venue limitations without creating any trading route."""
    from futures_data_health import LABELS, classify
    health = classify(venue, symbol, snapshot=snap, error=error)
    with st.expander("🩺 Futures Data Health · ตรวจว่าตลาดพร้อมหรือถูกบล็อก", expanded=bool(error)):
        st.markdown(f"**ตลาดที่เลือก:** {LABELS[venue]} · `{symbol}`")
        label = f"{health.state} · {health.detail}"
        if health.state in ("ACCESS_BLOCKED", "DATA_UNAVAILABLE", "STALE_DATA"):
            st.error(label)
        elif health.state in ("RATE_LIMITED", "NETWORK_ERROR", "SYMBOL_UNAVAILABLE", "WATCH_ONLY"):
            st.warning(label)
        else:
            st.info(label)
        st.caption("API ทำงานได้ ไม่ได้แปลว่ามีสัญญาณเข้าซื้อขาย · "
                   "ห้ามเอาข้อมูลอีกตลาดมาสร้าง Futures READY")
        if st.button("🔎 ตรวจ Exchange Catalog ทั้ง 3 ตลาด (เฉพาะการเข้าถึง)",
                     key=f"data_health_probe_{venue}_{symbol}"):
            with st.spinner("ตรวจ public exchangeInfo เท่านั้น..."):
                for source in LABELS:
                    status = _health_catalog_probe(source, symbol)
                    st.markdown(f"- **{LABELS[source]}:** `{status.state}` — {status.detail}")
            st.caption("ตรวจเฉพาะรายชื่อคู่เหรียญและข้อกำหนดตลาด ไม่ได้ยืนยัน "
                       "แท่ง Futures/Mark/Funding/Order Book/Flow")
    if error and venue != "BINANCE_TH_SPOT":
        show = st.checkbox("📉 ดู SHORT Watch จาก Binance TH Spot (เพื่อศึกษาทิศทางเท่านั้น)",
                           key=f"spot_short_research_{venue}_{symbol}")
        if show:
            from scalp_marketdata import MarketDataError
            try:
                with st.spinner("กำลังโหลดข้อมูล Spot แยกเพื่อการศึกษา..."):
                    spot = _spot_research_snapshot(symbol)
                _short_watch_panel(spot, substituted_source=True)
            except (MarketDataError, ValueError, TypeError, KeyError) as exc:
                st.warning("Spot research ก็ยังไม่พร้อม: " + str(exc)[:125])


def _validation_panel(venue: str, symbol: str) -> None:
    """Purely explanatory paper dashboard, not an input to live entry gates."""
    with st.expander("🧪 Orbit v5.9.1 · Professional Validation / Near Ready Tracker"):
        st.caption("สแกนอิสระทุก ~5 นาทีจาก GitHub Actions · เก็บสถานะ READY / WAIT / "
                   "WATCH / RISK BLOCK / DATA UNAVAILABLE · ไม่ใช่คำสั่งซื้อขายจริง "
                   "และอาจไม่ตรงรอบกับ Telegram ทุกครั้ง")
        show = st.checkbox("📊 โหลดประวัติการตรวจสัญญาณ", value=False,
                           key=f"validation_show_{venue}_{symbol}")
        if not show:
            return
        days = st.selectbox("ช่วงข้อมูลที่เก็บได้จริง", [1, 7, 30], index=1,
                            format_func=lambda x: f"{x} วัน",
                            key=f"validation_days_{venue}_{symbol}")
        try:
            from validation_logic import (replay_all, missed_opportunities,
                                          performance, walk_forward_report)
            all_rows = _validation_history_public(days)["rows"]
            records = [r for r in all_rows if r["v"] == venue and r["s"] == symbol]
            if not records:
                st.info("ยังไม่มีบันทึกของตลาด/คู่เหรียญนี้ โปรดตรวจ Workflow Validation")
                return
            recorded = len(records)
            valid = sum(r["st"] != "DATA_UNAVAILABLE" for r in records)
            ready = sum(r["st"] == "READY" for r in records)
            bucket = [r["t"] // 300_000 for r in records]
            observed_span = max(bucket) - min(bucket) + 1
            captured = 100 * recorded / observed_span if observed_span else 0
            left, right = st.columns(2)
            with left:
                st.metric("รอบบันทึก", str(recorded))
                st.metric("แหล่งข้อมูลใช้ได้", f"{valid}/{recorded}")
            with right:
                st.metric("READY ที่บันทึก (อาจซ้ำ Setup)", str(ready))
                st.metric("Coverage ในช่วงที่มีบันทึก", f"{captured:.1f}%")
            last = datetime.fromtimestamp(max(r["t"] for r in records) / 1000,
                                          timezone.utc).astimezone(BKK)
            st.caption(f"บันทึกล่าสุด {last:%d/%m/%Y %H:%M:%S} (ไทย) · "
                       "Coverage นับช่วงระหว่างบันทึกแรกกับล่าสุด ไม่ใช่รับประกัน 24 ชั่วโมง")

            target_options = ["TP1 เดิม", "TP2 เดิม"]
            if symbol == "PEPEUSDT":
                target_options.append("PEPE 10 จุด (ต้องผ่าน R:R เดิม)")
            selected = st.selectbox("สมมติฐานเป้าปิดเต็มไม้สำหรับ Paper Replay",
                                    target_options, key=f"validation_tp_{venue}_{symbol}")
            target = ("tp10" if selected.startswith("PEPE") else
                      "tp2" if selected.startswith("TP2") else "tp1")
            outcomes = replay_all(all_rows, venue, symbol, target)
            stats = performance(outcomes)
            st.markdown("**ผล Paper Replay หลังประมาณค่า Fee / Slippage / Spread**")
            a, b = st.columns(2)
            with a:
                st.metric("ผลจำลองที่ปิดแล้ว", f"{stats['n']} ไม้")
                st.metric("Win Rate จำลอง", (f"{stats['win_rate'] * 100:.1f}%"
                                                 if stats["win_rate"] is not None else "ข้อมูลยังไม่พอ"))
            with b:
                st.metric("Net ผลรวมจำลอง (USDT)", f"{stats['net_usdt']:+,.2f}")
                st.metric("Expectancy ต่อไม้ (R)", (f"{stats['expectancy_r']:+.2f}R"
                                                   if stats["expectancy_r"] is not None else "ข้อมูลยังไม่พอ"))
            c, d = st.columns(2)
            with c:
                st.metric("Profit Factor จำลอง", (f"{stats['profit_factor']:.2f}"
                                                  if stats["profit_factor"] is not None else "ยังประเมินไม่ได้"))
            with d:
                st.metric("Max Drawdown จำลอง", (f"{stats['max_drawdown_usdt']:,.2f} USDT"
                                                  if stats["max_drawdown_usdt"] is not None else "ยังประเมินไม่ได้"))
            st.caption("การเข้าใช้ราคาเปิดแท่ง 1m ถัดไป (ต้องห่างแผนไม่เกิน 0.3%) "
                       "· คิดต้นทุนสองฝั่ง · หาก SL และ TP ถูกแตะในแท่งเดียวกันให้ SL ก่อน "
                       "· ไม่มีข้อมูลแท่งครบจะไม่นับเป็นไม้ชนะ/แพ้ · ไม่ใช่ผลจากบัญชีจริง")
            if outcomes:
                detail = pd.DataFrame(outcomes).sort_values("t").copy()
                detail["เวลาไทย"] = pd.to_datetime(detail["t"], unit="ms", utc=True).dt.tz_convert(BKK)
                finished = detail.loc[detail["net_usdt"].notna()].copy()
                if len(finished):
                    finished["สะสม USDT"] = finished["net_usdt"].cumsum()
                    st.line_chart(finished.set_index("เวลาไทย")[["สะสม USDT"]], height=190)
                view = detail[["เวลาไทย", "side", "state", "entry", "exit", "net_usdt",
                               "net_r", "mfe_pct", "mae_pct", "ambiguous_stop_first"]].tail(50)
                view.columns = ["เวลาไทย", "ฝั่ง", "ผลจำลอง", "Entry", "Exit", "Net USDT",
                                "Net R", "MFE %", "MAE %", "SL/TP แตะพร้อมกัน"]
                st.dataframe(view.iloc[::-1], hide_index=True, width="stretch")
                st.download_button("⬇️ ดาวน์โหลด Paper Results CSV",
                                   detail.to_csv(index=False).encode("utf-8-sig"),
                                   f"Orbit_V59_Paper_{venue}_{symbol}.csv",
                                   mime="text/csv", key=f"validation_csv_{venue}_{symbol}")
            else:
                st.info("ยังไม่มีสัญญาณ READY จากรอบที่บันทึกได้ · ไม่สร้างผลจำลองขึ้นมา")

            st.markdown("**Missed Opportunity Watch (ไม่ใช่กำไรที่พลาดจริง)**")
            missed = missed_opportunities(all_rows, venue, symbol)
            if missed:
                report = pd.DataFrame(missed)
                st.caption(f"มี {len(report)} เหตุการณ์ที่มีทิศทางและข้อมูลอนาคตครบ 30 นาที "
                           "· เป็นเพียงราคาที่เคลื่อนไหว ไม่ได้ยืนยันว่าเข้าได้หรือทำกำไร")
                if symbol == "PEPEUSDT":
                    st.metric("ราคาเคยไปถึงระยะ 10 จุด หลัง WAIT/WATCH/BLOCK",
                              str(int(report["reached_10_points"].fillna(False).sum())))
                st.dataframe(report.tail(30).iloc[::-1], hide_index=True, width="stretch")
            else:
                st.caption("ยังไม่มีเหตุการณ์ที่มีทิศทางและแท่งปิดครบ 30 นาที · ไม่เดาโอกาสที่พลาด")

            st.markdown("**🟡 Near Ready → Missed Opportunity Tracker (บันทึกตั้งแต่ v5.9.1)**")
            try:
                from near_ready_tracker import forward_excursions
                near_events = [r for r in _near_history_public(days)["rows"]
                               if r["v"] == venue and r["s"] == symbol]
                if near_events:
                    followups = forward_excursions(near_events, all_rows, venue, symbol)
                    complete = [r for r in followups if r["state"] == "OBSERVED_30M"]
                    pending = len(followups) - len(complete)
                    aa, bb = st.columns(2)
                    with aa:
                        st.metric("Near Ready (รอบสแกน)", len(near_events))
                        st.metric("หน้าต่าง 30m ที่ข้อมูลครบ", len(complete))
                    with bb:
                        st.metric("ข้อมูลยังไม่ครบ/รอย้อนหลัง", pending)
                        st.metric("ราคาเคยไปทางที่เฝ้า ≥0.5%",
                                  sum(bool(r["reached_0_5pct"]) for r in complete))
                    if symbol == "PEPEUSDT":
                        st.metric("PEPE ราคาเคยไปทางที่เฝ้าถึง 10 จุด (Gross)",
                                  sum(bool(r["reached_10_points"]) for r in complete))
                    if followups:
                        view = pd.DataFrame(followups)
                        view["เวลาไทย"] = pd.to_datetime(view["t"], unit="ms", utc=True).dt.tz_convert(BKK)
                        st.dataframe(view[["เวลาไทย", "side", "failed_gate", "state",
                                           "favorable_pct", "adverse_pct", "reached_10_points"]]
                                     .tail(40).iloc[::-1], hide_index=True, width="stretch")
                        st.download_button("⬇️ ดาวน์โหลด Near Ready Follow-up CSV",
                                           view.to_csv(index=False).encode("utf-8-sig"),
                                           f"Orbit_V591_Near_{venue}_{symbol}.csv", mime="text/csv",
                                           key=f"near_csv_{venue}_{symbol}")
                    st.caption("นับไม่ซ้ำหนึ่งเหตุการณ์ต่อฝั่งต่อช่วง 30 นาที · "
                               "ใช้แต่แท่ง 1m ที่ปิดหลังสแกนจริงครบ 30 นาที "
                               "· favorable/adverse เป็นการแกว่งของราคา ไม่ได้จำลองออร์เดอร์ "
                               "· ไม่หักค่าธรรมเนียมและไม่ใช่กำไรที่พลาด")
                else:
                    st.caption("ยังไม่มี Near Ready ที่บันทึกโดย Workflow v5.9.1 "
                               "· ไม่ประเมินย้อนหลังโดยเดาจากรูปกราฟ")
            except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
                st.caption("Near Ready History ยังไม่พร้อม: " + str(exc)[:115])

            st.markdown("**Walk-Forward: รายงานช่วงเวลาต่อเนื่อง**")
            windows = walk_forward_report(outcomes)
            if windows:
                st.dataframe(pd.DataFrame(windows), hide_index=True, width="stretch")
                st.caption("เปรียบเทียบช่วง Train 7 วัน กับช่วงถัดไป 7 วันตามลำดับเวลา "
                           "· ไม่มีการปรับโมเดลย้อนหลัง · ตัวอย่างน้อยยังสรุปความสามารถทำกำไรไม่ได้")
            else:
                st.caption("ต้องสะสมข้อมูลและผลที่ปิดครบอย่างน้อย 14 วันจึงเริ่มทำรายงานตามเวลาได้")
            counts = pd.Series([r["why"] for r in records if r["st"] != "READY"])
            if not counts.empty:
                st.markdown("**สาเหตุ WAIT / BLOCK ที่พบบ่อย**")
                st.dataframe(counts.value_counts().head(8).rename_axis("เหตุผล").reset_index(name="ครั้ง"),
                             hide_index=True, width="stretch")
        except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
            st.warning("Professional Validation ยังโหลด/ประเมินไม่ได้: " + str(exc)[:130])


def _whale_panel(snap) -> None:
    """Independent research overlay: NEVER passed to the BUY/SHORT risk engine."""
    from whale_footprint import analyze_footprint, fetch_large_prints
    from whale_history import history_for

    st.markdown("### 🐋 Whale Footprint · ร่องรอยแรงซื้อขาย")
    try:
        observation = analyze_footprint(snap)
    except (ValueError, KeyError, TypeError) as exc:
        st.warning(f"Whale Footprint ยังประเมินไม่ได้: {str(exc)[:90]}")
        st.caption("ข้อมูลส่วนนี้ไม่มีผลต่อสัญญาณและความเสี่ยงของ Scalp")
        return

    labels = {
        "FLOW_UNAVAILABLE": "⚪ FLOW UNAVAILABLE · ยังไม่มีข้อมูลยืนยัน",
        "POSSIBLE_BID_ABSORPTION": "🟢 POSSIBLE BID ABSORPTION · อาจมีแรงรับ",
        "POSSIBLE_ASK_ABSORPTION": "🔴 POSSIBLE ASK ABSORPTION · อาจมีแรงขาย",
        "BUY_PRESSURE": "🟢 BUY PRESSURE · แรงซื้อเชิงรุก",
        "SELL_PRESSURE": "🔴 SELL PRESSURE · แรงขายเชิงรุก",
        "MIXED": "🟡 MIXED FLOW · ยังไม่ชัด",
    }
    st.info(labels[observation.classification] + " · " + observation.explanation)
    left, right = st.columns(2)
    with left:
        st.metric("Taker Buy 5m" if snap.venue != "BITGET_USDT_FUTURES" else "Flow 5m",
                  (f"{observation.taker_buy_share_5m * 100:.1f}%"
                   if observation.taker_buy_share_5m is not None else "ไม่พร้อม"))
        st.metric("Volume 5m เทียบฐาน 40 นาที", f"{observation.volume_ratio_5m:.2f}x")
    with right:
        st.metric("CVD Proxy 5m", (f"{observation.delta_5m_usdt:+,.1f} USDT"
                                    if observation.delta_5m_usdt is not None else "ไม่พร้อม"))
        st.metric("Bid Depth Share · 20 ระดับ", f"{observation.bid_depth_share * 100:.1f}%")
    st.caption("ใช้แท่ง 1m ที่ปิดแล้ว 5 แท่ง + Order Book จากตลาดที่เลือกเท่านั้น · "
               "Delta เป็นตัวแทนแรงซื้อขายเชิงรุก ไม่ใช่ตัวตนหรือเจตนาของวาฬ · "
               "Order Book ยกเลิกคำสั่งได้")
    st.warning("ข้อมูลวาฬเป็นเพียงหลักฐานประกอบ **ไม่ใช่ปุ่ม BUY/SHORT** · "
               "ไม่ยกเลิกเงื่อนไข Volume 1m/5m, Spread, Stop Loss, Fee, Depth, Net R:R "
               "หรือ RISK BLOCK ของ Orbit v5.8.4")

    with st.expander("🔎 ตรวจธุรกรรมก้อนใหญ่ของตลาดนี้ (ข้อมูลสดแยก)"):
        key = f"whale_prints_{snap.venue}_{snap.symbol}"
        if st.button("🔄 โหลด Aggregate Trades / Public Fills", key=key + "_button"):
            try:
                value = fetch_large_prints(snap)
                st.session_state[key] = value
            except (ValueError, TypeError, RuntimeError) as exc:
                st.session_state.pop(key, None)
                st.warning(f"ธุรกรรมก้อนใหญ่ไม่พร้อม: {str(exc)[:100]}")
        value = st.session_state.get(key)
        if value is not None:
            age = (datetime.now(timezone.utc) - value.latest_at).total_seconds()
            if 0 <= age <= 120:
                st.caption(f"แหล่งข้อมูล: {value.source} · ล่าสุด {age:.0f} วินาที · "
                           f"ตัวอย่าง {value.sample_size} รายการ ช่วง {value.window_seconds:.0f} วินาที")
                a, b = st.columns(2)
                with a:
                    st.metric("รายการใหญ่ฝั่งซื้อ", f"{value.buy_count} รายการ")
                    st.caption(f"มูลค่า {value.buy_usdt:,.0f} USDT")
                with b:
                    st.metric("รายการใหญ่ฝั่งขาย", f"{value.sell_count} รายการ")
                    st.caption(f"มูลค่า {value.sell_usdt:,.0f} USDT")
                st.caption(f"นิยามรายการใหญ่ = สูงกว่า 5 เท่าของค่ามัธยฐานในตัวอย่าง "
                           f"และไม่น้อยกว่า {value.threshold_usdt:,.0f} USDT · "
                           "ตัวอย่างล่าสุดอาจครอบคลุมเวลาไม่ครบ 5 นาที")
            else:
                st.info("ตัวอย่างธุรกรรมเก่าแล้ว · กดโหลดใหม่")

    with st.expander("📚 ประวัติ Whale Footprint · เก็บจริงสูงสุด 30 วัน"):
        show = st.checkbox("โหลดประวัติจาก GitHub (แยกจากแอปและ Telegram)",
                           key=f"whale_history_{snap.venue}_{snap.symbol}")
        if show:
            days = st.selectbox("ดูย้อนหลัง", [1, 7, 30], index=1,
                                format_func=lambda x: f"{x} วัน",
                                key=f"whale_days_{snap.venue}_{snap.symbol}")
            try:
                data = history_for(_whale_history_public(days), snap.venue, snap.symbol)
            except (ValueError, TypeError, RuntimeError) as exc:
                st.info(str(exc)[:130])
                data = []
            if data:
                table = pd.DataFrame(data).sort_values("t").copy()
                table["เวลาไทย"] = pd.to_datetime(table["t"], unit="ms", utc=True).dt.tz_convert(BKK)
                # CVD integrates distinct 5m intervals, not repeated Streamlit refreshes.
                table["CVD สะสม (USDT)"] = table["d"].fillna(0).cumsum()
                latest = table.iloc[-1]
                st.caption(f"บันทึกจริง {len(table)} ช่วง · ล่าสุด "
                           f"{latest['เวลาไทย']:%d/%m/%Y %H:%M} (ไทย) · "
                           "เริ่มนับเมื่อ Workflow ทำงาน ไม่มีข้อมูลสมมติย้อนหลัง")
                st.line_chart(table.set_index("เวลาไทย")[["CVD สะสม (USDT)"]],
                              height=220)
                readable = table[["เวลาไทย", "p", "d", "b", "x", "g"]].tail(40).copy()
                readable.columns = ["เวลาไทย", "ราคา", "Delta USDT", "Buy Share",
                                    "Volume x", "ข้อสังเกต"]
                st.dataframe(readable.iloc[::-1], hide_index=True, width="stretch")
                if st.checkbox("📊 แสดงธุรกรรมก้อนใหญ่ย้อนหลัง (เฉพาะช่วงที่ API ส่งข้อมูล)",
                               key=f"whale_large_history_{snap.venue}_{snap.symbol}"):
                    large = table[["เวลาไทย", "lb", "ls"]].tail(40).copy()
                    large.columns = ["เวลาไทย", "ฝั่งซื้อ USDT", "ฝั่งขาย USDT"]
                    st.dataframe(large.iloc[::-1], hide_index=True, width="stretch")
                    st.caption("ช่องว่างหมายถึง API ไม่มีข้อมูลที่ตรวจสอบได้ ไม่ใช่ไม่มีคนซื้อขาย")
                st.download_button("⬇️ ดาวน์โหลดประวัติ CSV", readable.to_csv(index=False).encode("utf-8-sig"),
                                   f"Orbit_Whale_{snap.venue}_{snap.symbol}.csv",
                                   mime="text/csv", key=f"whale_csv_{snap.venue}_{snap.symbol}")
            else:
                st.caption("ยังไม่มีประวัติสำหรับคู่เหรียญ/ตลาดนี้ หรือยังไม่เปิด Workflow เก็บข้อมูล")
        st.caption("ข้อมูลเป็นภาพรวมตลาดและธุรกรรมสาธารณะ · ไม่ใช่ประวัติผลกำไร "
                   "ไม่รวมข้อมูลนอกตลาดที่เลือก และยังไม่ยืนยันความแม่นยำเชิงสถิติ")


@st.fragment(run_every="60s")
def scalp_screen() -> None:
    """On-page live read-only scan; stops when the Streamlit session closes."""
    from scalp_marketdata import MarketDataError
    from scalp_engine import scalp_evidence, scalp_watch_zones, _adx
    from zone_signal import evaluate_zone

    from scalp_fixed_tp import fixed_tp_preview, pepe_daily_ten_preview

    st.markdown("## 🎯 Scalp Signal v5.9.2 · SHORT WATCH + DATA HEALTH + NEAR READY")
    st.caption("อัปเดตเองทุก ~60 วินาทีขณะเปิดหน้าเว็บ · กดปุ่มเพื่อตรวจทันที · "
               "Trend Breakout / Sideways / Early Reversal Watch · "
               "ใช้ข้อมูลตลาดสาธารณะ · PAPER ONLY · ไม่ส่งคำสั่งซื้อขาย")
    market = st.radio("เลือกตลาด", ["Spot · Binance TH", "Futures · Binance Global",
                                   "Futures · Bitget (ตลาดแยก)"],
                      horizontal=True, key="scalp_market")
    venue = ("BINANCE_TH_SPOT" if market.startswith("Spot") else
             "BITGET_USDT_FUTURES" if "Bitget" in market else "BINANCE_GLOBAL_USDM")
    pairs = ["BTCUSDT", "ETHUSDT", "PEPEUSDT", "DOGEUSDT"]
    symbol = st.selectbox("คู่เหรียญ USDT", pairs, key="scalp_symbol")
    tp_mode = st.selectbox(
        "รูปแบบ Take Profit", ["TP ตามแผนเดิม", "🎯 TP ระยะราคา 10 USDT",
                              "🎯 PEPE Daily 10 จุด · 1 ไม้/วัน"],
        key="scalp_tp_mode", width="stretch")
    fixed_tp = tp_mode == "🎯 TP ระยะราคา 10 USDT"
    daily_ten = tp_mode == "🎯 PEPE Daily 10 จุด · 1 ไม้/วัน"
    daily_capital_thb = 100_000.0
    daily_done = False
    if fixed_tp:
        st.caption("โหมดนี้เพิ่มเป้ากำไรทางเลือกโดยไม่เปลี่ยนจุดเข้าหรือ Stop Loss เดิม · "
                   "หากต้นทุนหรือ Net R:R ไม่ผ่าน จะไม่อนุมัติ TP 10 USDT")
    if daily_ten:
        st.caption("เป้าหมาย PEPE วันละหนึ่งไม้: TP +10 จุดจากราคาเข้า (ไม่ใช่ +10 USDT) "
                   "· สถานะ READY ต้องผ่านจุดเข้า/Stop/ต้นทุน/R:R แยกตามกฎเดิม")
        if symbol != "PEPEUSDT":
            st.warning("โหมด Daily 10 จุดรองรับเฉพาะ PEPEUSDT ในตอนนี้ · "
                       "กรุณาเปลี่ยนคู่เหรียญเป็น PEPEUSDT")
        else:
            daily_capital_thb = float(st.number_input(
                "ทุนจำลองสำหรับคำนวณกำไร (บาท)", min_value=100.0,
                max_value=100_000_000.0, value=100_000.0, step=1_000.0,
                key="scalp_daily_capital"))
            day_key = datetime.now(BKK).strftime("%Y-%m-%d")
            daily_done = st.checkbox(
                "วันนี้ปิดไม้แล้ว · หยุดแสดงแผนเข้าใหม่ของโหมด Daily",
                key=f"scalp_pepe_daily_done_{day_key}")
            st.caption("บันทึกการปิดไม้เป็นการทำเครื่องหมายด้วยตนเองเฉพาะเซสชันนี้ "
                       "· ไม่เชื่อมบัญชีซื้อขายและไม่คงอยู่หลังปิด/รีโหลดเว็บ")
            if daily_done:
                st.success("✅ วันนี้ปิดไม้แล้ว · งดเข้าเพิ่มในโหมด Daily 10 จุด")
    if "scalp_refresh" not in st.session_state:
        st.session_state["scalp_refresh"] = 0
    if st.button("🔄 ตรวจข้อมูลตลาดล่าสุด", key="scalp_refresh_button", width="stretch"):
        st.session_state["scalp_refresh"] += 1
    try:
        with st.spinner("กำลังตรวจแท่งที่ปิดแล้ว, Bid/Ask, Depth และกฎตลาดจริง..."):
            ob, snap, cfg = _scalp_live(venue, symbol, st.session_state["scalp_refresh"])
    except (MarketDataError, ValueError, RuntimeError, OSError, TypeError, KeyError) as exc:
        st.error("DATA UNAVAILABLE · ไม่สามารถยืนยันข้อมูลจากตลาดที่เลือกได้")
        st.caption(str(exc)[:230])
        if venue == "BINANCE_GLOBAL_USDM":
            st.warning("Binance Global Futures อาจบล็อกเครือข่ายด้วย HTTP 451/403 · "
                       "ระบบจะไม่เอาราคา Binance TH Spot หรือ Kraken มาสร้าง LONG/SHORT")
        _data_health_panel(venue, symbol, error=str(exc))
        _validation_panel(venue, symbol)
        return
    colors = {"READY": "good", "WATCH": "warning", "EXIT_WATCH": "warning",
              "RISK_BLOCK": "danger"}
    color = colors.get(ob.state, "warning")
    heading = {"READY": "READY · พิจารณาได้เฉพาะช่วงเวลาสั้น ๆ",
               "WATCH": "WATCH · ยังไม่ใช่สัญญาณเข้า",
               "EXIT_WATCH": "SELL WATCH · Spot ขาลง",
               "RISK_BLOCK": "RISK BLOCK · งดเข้า",
               "WAIT": "WAIT · รอรูปแบบราคา"}.get(ob.state, ob.state)
    hero_reason = ob.reason
    if daily_ten and symbol == "PEPEUSDT" and daily_done:
        heading = "DAILY DONE · ปิดไม้วันนี้แล้ว"
        hero_reason = "โหมด Daily 10 จุด: วันนี้ปิดไม้แล้ว · ไม่เสนอการเข้าใหม่"
        color = "good"
    st.markdown(f'<div class="orb-hero {color}">'
                f'<div class="orb-hero-title">{escape(symbol)} · {escape(market)}</div>'
                f'<div class="orb-hero-value">{escape(heading)}</div>'
                f'<div class="orb-hero-note">{escape(hero_reason)}</div></div>',
                unsafe_allow_html=True)
    if (fixed_tp or daily_ten) and ob.state == "READY" and not daily_done:
        st.warning("READY ด้านบนเป็นสัญญาณตาม TP เดิมเท่านั้น · "
                   "TP ทางเลือกต้องผ่านค่าธรรมเนียมและ Net R:R แยก จึงจะใช้เป็นแผนได้")
    st.caption(f"Market Regime: {ob.market_regime} · Strategy: {ob.strategy} · "
               "Sideways จะเข้าใกล้ขอบกรอบเท่านั้น ไม่เข้าเมื่อราคากลางกรอบ")
    if ob.early_reversal_note:
        st.info(ob.early_reversal_note + " · เป็นข้อมูลเฝ้าดูเท่านั้น ไม่ยกเลิก RISK BLOCK")
    st.markdown(f"**Bid:** `{concise_price(snap.bid)}` · "
                f"**Ask:** `{concise_price(snap.ask)}` · **Spread:** `{snap.spread_bps:.1f} bps`")
    st.caption(f"อ้างอิงข้อมูล ณ {snap.checked_at.astimezone(BKK):%d/%m/%Y %H:%M:%S} น. (ไทย) "
               "· แท่ง 1m/5m/15m ปิดจริง · Bid/Ask อาจเปลี่ยนทันที")
    _data_health_panel(venue, symbol, snap=snap)
    _short_watch_panel(snap)
    hour = snap.frames.get("1h")
    if hour is not None and len(hour) >= 55:
        hourly_adx = _adx(hour)
        h = hour.iloc[-13:-1]
        low_h, high_h = float(h.low.min()), float(h.high.max())
        width_h = ((high_h - low_h) / ((low_h + high_h) / 2) * 100
                   if low_h > 0 else 0)
        is_range_h = (hourly_adx <= cfg.range_max_adx and
                      cfg.range_min_width_pct <= width_h <= cfg.range_max_width_pct)
        st.caption(f"กรอบ 1H จากแท่งที่ปิดแล้ว: {concise_price(low_h)}–{concise_price(high_h)}"
                   f" · ADX 1H {hourly_adx:.1f} · "
                   + ("SIDEWAYS WATCH" if is_range_h else "ยังไม่ยืนยัน Sideways 1H")
                   + " · ไม่ใช่สัญญาณซื้อ")
    _near_live_panel(snap, cfg, ob)
    _whale_panel(snap)
    _validation_panel(venue, symbol)
    if fixed_tp:
        st.markdown("### 🎯 ตัวอย่าง TP ระยะราคา 10 USDT (ยังไม่ใช่สัญญาณเข้า)")
        sides = (["LONG"] if venue == "BINANCE_TH_SPOT" else
                 [ob.side] if ob.side in ("LONG", "SHORT") else ["LONG", "SHORT"])
        for example_side in sides:
            _fixed_tp_panel(fixed_tp_preview(snap, cfg, example_side))
    if daily_ten and symbol == "PEPEUSDT" and not daily_done:
        st.markdown("### 🎯 Daily 10 จุด · ราคาเฝ้าดู (ยังไม่ใช่สัญญาณเข้า)")
        daily_sides = (["LONG"] if venue == "BINANCE_TH_SPOT" else
                       [ob.side] if ob.side in ("LONG", "SHORT") else ["LONG", "SHORT"])
        for daily_side in daily_sides:
            _pepe_daily_ten_panel(pepe_daily_ten_preview(snap, cfg, daily_side),
                                  daily_capital_thb)
    _support_resistance_panel(snap.frames["5m"], current_price=(snap.bid + snap.ask) / 2)
    st.markdown("### 🗺️ โซนเฝ้าราคา (สูงสุด 3 โซน · แสดงแม้ WAIT)")
    st.caption("เลือกเฉพาะแนวที่ยังไม่ถูกทะลุจาก EMA21 / จุดกลับตัว / แท่ง 5m ปิดแล้ว · "
               "โซนเดิมที่หลุดจะไม่ถูกนำกลับมาใช้เป็นจุดรอซื้อหรือ Short · "
               "ไม่ใช่แผนแบ่งซื้อ 3 ไม้")
    watch_sides = (["LONG"] if venue == "BINANCE_TH_SPOT" else
                   [ob.side] if ob.side in ("LONG", "SHORT") else ["LONG", "SHORT"])
    for watch_side in watch_sides:
        zones = scalp_watch_zones(snap, watch_side)
        if zones:
            st.markdown(f"**{'BUY / LONG — โซนแนวรับ' if watch_side == 'LONG' else 'SHORT — โซนแนวต้าน'}**")
            evaluated = [(zone, evaluate_zone(snap, cfg, zone, watch_side)) for zone in zones]
            ready = [(zone, decision) for zone, decision in evaluated if decision.state == "ZONE_READY"]
            # One primary candidate per direction: overlapping zones must not
            # look like instructions to open three positions simultaneously.
            primary_name = (min(ready, key=lambda item: abs(
                (item[0]["low"] + item[0]["high"]) / 2 -
                (snap.ask if watch_side == "LONG" else snap.bid)))[0]["name"]
                if ready else None)
            for zone, decision in evaluated:
                label = {"ZONE_READY": "🟢 ZONE READY · ผ่านเงื่อนไขจำลอง",
                         "WAIT_PRICE": "⚪ WAIT PRICE · รอเข้าโซน",
                         "WAIT_CONFIRM": "🟡 CONFIRMING · รอยืนยัน 1m/5m",
                         "MISSED": "🟠 MISSED · เด้งไกลแล้ว ไม่ไล่ราคา",
                         "RISK_BLOCK": "🔴 RISK BLOCK · งดเข้า",
                         "INVALIDATED": "🔴 โซนหลุด · งดเข้า",
                         "DATA_UNAVAILABLE": "⚠️ DATA UNAVAILABLE"}[decision.state]
                css = ("in-zone" if zone["state"] == "IN_ZONE" else
                       "invalid" if decision.state in ("RISK_BLOCK", "INVALIDATED") else "")
                low, high = concise_price(zone["low"]), concise_price(zone["high"])
                location = ("อยู่ในโซน · ตรวจแท่งยืนยัน" if zone["state"] == "IN_ZONE"
                            else (f"ห่างจากขอบโซน {zone['distance_pct'] * 100:.1f} bps"
                                  if zone["distance_pct"] < 0.01 else
                                  f"ห่างจากขอบโซน {zone['distance_pct']:.2f}%"))
                st.markdown(
                    f'<div class="orb-zone {css}">'
                    f'<div class="orb-zone-head"><span>{escape(zone["name"])}</span>'
                    f'<span class="orb-zone-state">{escape(label)}</span></div>'
                    f'<div class="orb-zone-prices">'
                    f'<div class="orb-zone-price"><small>ราคาต่ำ (USDT)</small>{escape(low)}</div>'
                    f'<div class="orb-zone-price"><small>ราคาสูง (USDT)</small>{escape(high)}</div>'
                    f'</div>'
                    f'<div class="orb-zone-sub">อ้างอิง: {escape(zone["basis"])}'
                    f' · {escape(location)}</div></div>',
                    unsafe_allow_html=True)
                if decision.state == "ZONE_READY" and zone["name"] != primary_name:
                    st.info("โซนยืนยันซ้อนกัน · ใช้โซนที่ใกล้ราคามากที่สุดเป็นแผนหลักเพียงหนึ่งโซน")
                elif decision.state == "ZONE_READY":
                    st.success(f"{label} · {decision.reason}")
                    if fixed_tp:
                        st.caption("แผนเดิมผ่าน READY แต่ต้องตรวจ TP 10 USDT แยกอีกครั้ง")
                        _price_grid([("ENTRY ที่ยืนยัน", decision.entry),
                                     ("STOP LOSS เดิม", decision.stop)])
                        _fixed_tp_panel(fixed_tp_preview(
                            snap, cfg, watch_side, entry=decision.entry,
                            stop=decision.stop, qty=decision.qty, signal_ready=True),
                            approved_signal=True)
                        with st.expander("TP1/TP2 ของแผนเดิม (ยังคงอยู่)"):
                            _price_grid([("TP1 เดิม", decision.tp1),
                                         ("TP2 เดิม", decision.tp2)])
                    elif daily_ten and symbol == "PEPEUSDT":
                        if daily_done:
                            st.warning("วันนี้ทำเครื่องหมายว่าปิดไม้แล้ว · ไม่เปิดแผน Daily ใหม่")
                        else:
                            _price_grid([("ENTRY ที่ยืนยัน", decision.entry),
                                         ("STOP LOSS เดิม", decision.stop)])
                            _pepe_daily_ten_panel(pepe_daily_ten_preview(
                                snap, cfg, watch_side, entry=decision.entry,
                                stop=decision.stop, qty=decision.qty,
                                signal_ready=True), daily_capital_thb, approved_signal=True)
                        with st.expander("TP1/TP2 ของแผนเดิม (ยังคงอยู่)"):
                            _price_grid([("TP1 เดิม", decision.tp1),
                                         ("TP2 เดิม", decision.tp2)])
                    else:
                        _price_grid([("ENTRY ล่าสุด", decision.entry), ("STOP LOSS", decision.stop),
                                     ("TP1 จำลอง", decision.tp1), ("TP2 จำลอง", decision.tp2)])
                        st.caption(f"Net R:R ~{decision.net_rr:.2f}:1 · Qty จำลอง {decision.qty:g}")
                    st.caption(f"หมดอายุ {decision.expires_at.astimezone(BKK):%H:%M:%S} น. · "
                               "ตรวจ Bid/Ask ใหม่ก่อนตัดสินใจ; ไม่ส่งคำสั่งซื้อขาย")
                elif decision.state == "WAIT_PRICE":
                    st.caption("⚪ ยังไม่ถึงโซน · ระบบจะประเมินใหม่เมื่อข้อมูลรีเฟรช")
                elif decision.state in ("RISK_BLOCK", "INVALIDATED"):
                    st.error(f"{label} · {decision.reason}")
                elif decision.state == "MISSED":
                    st.warning(f"{label} · {decision.reason}")
                else:
                    st.warning(f"{label} · {decision.reason}")
                if zone["state"] == "IN_ZONE" or (zone["state"] == "WATCH" and
                                                      decision.state in ("ZONE_READY", "WAIT_CONFIRM")):
                    with st.expander(f"🔎 เหตุผลของ {zone['name']} {watch_side} · 15m / 5m / 1m",
                                     expanded=False):
                        for check_name, passed, explanation in decision.checks:
                            st.markdown(f"{'✅' if passed else '🟡'} **{check_name}** — {explanation}")
                        st.caption("เงื่อนไขต้นทุน/Depth/Stop/Net R:R ตรวจต่อเมื่อแท่งยืนยันผ่าน · "
                                   "การผ่านเชิงเทคนิคไม่ใช่อัตราชนะที่รับประกัน")
        else:
            st.warning(("BUY / LONG" if watch_side == "LONG" else "SHORT") +
                       " · ยังไม่มีโซนโครงสร้างที่ไม่ถูกทะลุในข้อมูลแท่ง 5m ล่าสุด · "
                       "ไม่อ้างแนวเดิมที่หลุดเป็นจุดเข้า และไม่คาดเดาราคาใหม่")
            st.caption("ติดตาม Bid/Ask และแนวรับ–แนวต้านอ้างอิงด้านบนต่อได้ · "
                       "ระบบจะค้นหาโซนใหม่เมื่อแท่ง 5m ปิดและข้อมูลรีเฟรช")
    st.caption("แต่ละโซนตรวจสถานะของตัวเองทุกครั้งที่หน้า Scalp รีเฟรช (~60 วินาที) · "
               "ZONE READY เป็นสัญญาณจำลองแยกจาก Strategy ด้านบน และยังไม่ผ่านการพิสูจน์ผลกำไร · "
               "ถึงโซนไม่ได้แปลว่าเข้าได้ทันที")
    with st.expander("🔎 ตรวจหลักฐานของสัญญาณ (ไม่ใช่เปอร์เซ็นต์ชนะ)"):
        for name, passed, explanation in scalp_evidence(snap, cfg, ob):
            st.markdown(f"{'✅' if passed else '🟡'} **{name}** — {explanation}")
        st.caption("สัญญาณ READY ต้องผ่านกฎเพิ่มเติม เช่น โครงสร้างราคา Stop/TP, "
                   "Depth, Net R:R และอายุสัญญาณ ไม่ใช่นับจำนวนเครื่องหมายถูก")
    if ob.entry is not None:
        st.markdown("### แผนจำลอง (ไม่ใช่ออร์เดอร์)")
        if fixed_tp and ob.state == "READY" and ob.side in ("LONG", "SHORT"):
            _price_grid([("Entry Bid/Ask", ob.entry), ("Stop Loss เดิม", ob.stop)])
            _fixed_tp_panel(fixed_tp_preview(
                snap, cfg, ob.side, entry=ob.entry, stop=ob.stop,
                qty=ob.qty, signal_ready=True), approved_signal=True)
            with st.expander("TP1/TP2 ของแผนเดิม (ยังคงอยู่)"):
                _price_grid([("TP1 เดิม", ob.tp1), ("TP2 เดิม", ob.tp2)])
        elif (daily_ten and symbol == "PEPEUSDT" and not daily_done and
              ob.state == "READY" and ob.side in ("LONG", "SHORT")):
            _price_grid([("Entry Bid/Ask", ob.entry), ("Stop Loss เดิม", ob.stop)])
            _pepe_daily_ten_panel(pepe_daily_ten_preview(
                snap, cfg, ob.side, entry=ob.entry, stop=ob.stop,
                qty=ob.qty, signal_ready=True), daily_capital_thb,
                approved_signal=True)
            with st.expander("TP1/TP2 ของแผนเดิม (ยังคงอยู่)"):
                _price_grid([("TP1 เดิม", ob.tp1), ("TP2 เดิม", ob.tp2)])
        else:
            _price_grid([("Entry Bid/Ask", ob.entry), ("Stop Loss", ob.stop),
                         ("TP1", ob.tp1), ("TP2", ob.tp2)])
        st.caption(f"Position ~{ob.notional_usdt:.2f} USDT / Qty {ob.qty:g} · "
                   f"ความเสี่ยงสุทธิจำลอง {ob.risk_usdt:.3f} USDT · "
                   f"Net TP2 R:R ของแผนเดิม ~{ob.net_rr:.2f}:1")
        if ob.expires_at:
            st.warning(f"READY หมดอายุ {ob.expires_at.astimezone(BKK):%H:%M:%S} น. "
                       "· ก่อนซื้อให้ตรวจราคาจริงและ Spread ใหม่")
    st.info(f"ทุนตั้งต้นจำลอง {cfg.capital_usdt:.0f} USDT · เสี่ยงต่อครั้ง "
            f"{cfg.risk_per_trade_pct:.2f}% · เพดานความเสี่ยงของการแจ้งเตือน "
            f"{cfg.daily_risk_budget_pct:.1f}%/วัน (ไม่ใช่ระบบติดตามออร์เดอร์จริง)")
    st.caption("อัปเดตอัตโนมัติเฉพาะขณะเปิดหน้า Scalp ใน Streamlit เท่านั้น · "
               "เมื่อปิดเว็บจะไม่มีการสแกนเบื้องหลัง · ไม่มีการรับประกันกำไร")
    if venue == "BITGET_USDT_FUTURES":
        st.warning("Bitget เป็นตลาด Futures คนละแห่งกับ Binance Global · "
                   "READY ต้องมี Public Trade Fills Buy/Sell (ไม่ใช่ Taker ที่รับรอง) "
                   "ซึ่งตรวจยอดทั้งแท่ง 1m ได้ครบจริง · "
                   "ถ้าข้อมูลไม่ครบจะไม่มี READY · ไม่ใช้เป็นราคาเข้า Binance Global")


@st.cache_data(ttl=120, show_spinner=False)
def _spot_summary(symbol: str, watch_token: str | None, manual_snapshot):
    settings = replace(read_settings(ROOT / "monitor_config.json"), symbols=(symbol,))
    watch = (watch_token, None) if watch_token else None
    return analyze_symbol(symbol, settings, now=datetime.now(timezone.utc),
                          watch=watch, manual_cg=manual_snapshot)


@st.cache_data(ttl=180, show_spinner=False)
def _spot_chart(symbol: str) -> pd.DataFrame:
    return fetch_klines(symbol, "1h", 250).tail(90)[["close"]]


@st.cache_data(ttl=180, show_spinner=False)
def _spot_watch_candles(symbol: str) -> pd.DataFrame:
    # fetch_klines explicitly requires at least 250 closed candles. Asking for
    # 90 raised PublicDataError on every Spot watch panel, leaving all prices
    # blank even though the underlying API was healthy.
    return fetch_klines(symbol, "1h", 250).tail(60)


def _navigate_lab(symbol: str):
    # Button on_click callbacks run before the next rerun, safe for widget state.
    st.session_state["orbit_screen"] = LAB
    st.session_state["coin_search"] = symbol.removesuffix("USDT")


def spot_screen(symbol: str, watch_token: str | None) -> None:
    st.markdown('<div class="orb-section"><strong>Spot Signal</strong><span class="orb-subtle">15M · 1H · 4H · 1D</span></div>',
                unsafe_allow_html=True)
    snap = st.session_state.get("coinglass_snapshot")
    if snap is not None and snap.symbol != symbol.removesuffix("USDT"):
        snap = None
    selected_watch = None
    if watch_token:
        try:
            plan = decode_watch(watch_token)
            if plan.symbol == symbol:
                selected_watch = watch_token
        except (ValueError, TypeError):
            st.warning("ลิงก์แผนที่ล็อกไว้ไม่ถูกต้อง")
    try:
        with st.spinner("กำลังวิเคราะห์ Spot และ 4 Timeframes..."):
            observation = _spot_summary(symbol, selected_watch, snap)
    except (ValueError, RuntimeError, KeyError, TypeError, OSError, IndexError) as exc:
        st.error("ข้อมูล Spot ยังไม่พร้อม กรุณาลองใหม่")
        with st.expander("รายละเอียดข้อผิดพลาด"):
            st.caption(type(exc).__name__)
        if st.button("🔁 ลองใหม่", width="stretch", key="spot_retry"):
            _spot_summary.clear()
            st.rerun()
        return
    look = spot_look(observation.status)
    _signal_card(look, symbol, observation.last_price, "BINANCE SPOT")
    try:
        _support_resistance_panel(_spot_watch_candles(symbol),
                                  current_price=observation.last_price)
    except (ValueError, RuntimeError, KeyError, TypeError, OSError, IndexError):
        st.warning("แนวรับ–แนวต้าน Spot ยังไม่มีข้อมูลแท่ง 1h ที่ตรวจสอบได้")
    st.markdown('<div class="orb-section"><strong>แผนราคา</strong><span class="orb-subtle">USDT · ไม่ใช่คำสั่งซื้อ</span></div>',
                unsafe_allow_html=True)
    if observation.entry_low is None or observation.entry_high is None:
        try:
            estimated = indicative_zone(_spot_watch_candles(symbol))
        except (ValueError, RuntimeError, KeyError, TypeError, OSError, IndexError):
            estimated = None
        _watch_price_panel(estimated, "Spot · รอซื้อจากแนวรับ")
    else:
        _price_grid([("ENTRY LOW", observation.entry_low), ("ENTRY HIGH", observation.entry_high),
                     ("STOP LOSS", observation.stop_loss), ("TAKE PROFIT 1", observation.tp1),
                     ("TAKE PROFIT 2", observation.tp2)])
    if observation.mode == "FROZEN":
        st.caption("🔒 แผนที่ล็อกไว้ · จุดราคาเดิมไม่ขยับตามตลาด")
    else:
        st.caption("📍 แผน MTF สด · เปลี่ยนได้เมื่อมีแท่งเทียนใหม่")
    rally_text = {"BREAKOUT_WATCH": "🚀 ราคาเริ่มหนี Entry Zone",
                  "MISSED_ENTRY": "⚠️ ราคาไปไกลจาก Entry Zone",
                  "NEW_SETUP_CANDIDATE": "🔄 พบโอกาสพิจารณาแผนใหม่"}
    if observation.opportunity_status in rally_text:
        st.warning(rally_text[observation.opportunity_status] + " · " + observation.opportunity_reason)
    score = f"{observation.alignment:.1f}/100" if observation.alignment is not None else "—"
    st.markdown(f'<div class="orb-footnote">MTF Alignment: {score} (ไม่ใช่ Win Rate) · Futures Context: '
                + escape(observation.futures_source) + '</div>', unsafe_allow_html=True)
    a, b = st.columns(2)
    with a:
        st.button("🔬 วิเคราะห์ละเอียด", on_click=_navigate_lab, args=(symbol,), width="stretch")
    with b:
        if st.button("↻ รีเฟรช", width="stretch", key="spot_refresh"):
            _spot_summary.clear()
            _spot_chart.clear()
            st.rerun()
    with st.expander("📈 กราฟ Spot 1H", expanded=False):
        if st.toggle("โหลดกราฟราคา 1H", value=False, key=f"orbit_spot_chart_{symbol}"):
            try:
                st.line_chart(_spot_chart(symbol), height=190)
            except (ValueError, RuntimeError, TypeError, OSError):
                st.caption("กราฟ Spot ยังไม่พร้อม")
    with st.expander("ℹ️ ทำไมถึงแสดงสถานะนี้?", expanded=False):
        st.write(observation.reason)
        for label in observation.failed_checks[:12]:
            st.caption("• " + label)
        st.caption("ข้อมูล CoinGlass ต้องกรอกเองใน Lab; ผลที่ขาดข้อมูลหลักจะไม่ถูกตีความว่า READY")
    st.markdown('<div class="orb-footnote">READ ONLY · ไม่มีคำสั่งซื้อขาย · Telegram ผ่าน GitHub Actions แยกต่างหาก</div>',
                unsafe_allow_html=True)


@st.cache_data(ttl=900, show_spinner=False)
def _futures_catalog() -> set[str]:
    return fetch_futures_catalog()


@st.cache_data(ttl=120, show_spinner=False)
def _futures_snapshot(symbol: str, capital: float, risk_pct: float):
    now = datetime.now(timezone.utc)
    source, failure = "BINANCE", ""
    try:
        pair = resolve_futures_pair(symbol, _futures_catalog())
        frames = {tf: fetch_futures_klines(pair.contract, tf, now=now) for tf in ("15m", "1h", "4h")}
        last, mark, funding = fetch_futures_ticker(pair.contract, now=now)
    except (FuturesDataError, ValueError, RuntimeError, OSError) as exc:
        failure = "Binance: " + str(exc)[:100]
        try:
            source = "BYBIT_WATCH_ONLY"
            contract = fetch_backup_pair(symbol)
            pair = resolve_futures_pair(symbol, {contract})
            frames = {tf: fetch_backup_klines(contract, tf, now=now) for tf in ("15m", "1h", "4h")}
            last, mark, funding = fetch_backup_ticker(contract, now=now)
        except (FuturesDataError, ValueError, RuntimeError, OSError) as bybit_exc:
            failure += " | Bybit: " + str(bybit_exc)[:100]
            source = "KRAKEN_WATCH_ONLY"
            contract = fetch_kraken_pair(symbol)
            pair = FuturesPair(symbol, contract)
            frames = {tf: fetch_kraken_klines(contract, tf, now=now) for tf in ("15m", "1h", "4h")}
            last, mark, funding = fetch_kraken_ticker(contract, now=now)
    settings = replace(read_futures_settings(ROOT / "futures_daytrade_config.json"),
                       symbols=(pair.contract,), capital_usdt=capital,
                       risk_per_signal_pct=risk_pct)
    result = evaluate_futures(pair.contract, frames, last=last, mark=mark,
                              funding_pct=funding, now=now, settings=settings,
                              require_taker_flow=(source == "BINANCE"))
    return replace(result, source=source), frames["15m"].tail(90), funding, pair, failure


def futures_screen(symbol: str) -> None:
    st.markdown('<div class="orb-section"><strong>Futures Day Trade</strong><span class="orb-subtle">Long & Short · 15M</span></div>',
                unsafe_allow_html=True)
    cfg = read_futures_settings(ROOT / "futures_daytrade_config.json")
    if "orbit_futures_capital" not in st.session_state:
        st.session_state["orbit_futures_capital"] = float(cfg.capital_usdt)
    if "orbit_futures_risk" not in st.session_state:
        st.session_state["orbit_futures_risk"] = float(cfg.risk_per_signal_pct)
    capital = st.session_state["orbit_futures_capital"]
    risk_pct = st.session_state["orbit_futures_risk"]
    try:
        with st.spinner("กำลังตรวจสัญญาณ Futures 15M / 1H / 4H..."):
            ob, chart, funding_pct, pair, failure = _futures_snapshot(symbol, capital, risk_pct)
    except (FuturesDataError, ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        _signal_card(futures_look("DATA_UNAVAILABLE", "NONE"), symbol, None, "USD-M FUTURES")
        st.warning("Futures API ไม่พร้อมในขณะนี้ · ไม่แสดงสัญญาณทดแทน")
        with st.expander("รายละเอียด"):
            st.caption(str(exc)[:180])
        if st.button("↻ ลองใหม่", width="stretch", key="futures_retry"):
            _futures_snapshot.clear()
            _futures_catalog.clear()
            st.rerun()
        return
    look = futures_look(ob.state, ob.direction)
    contract_label = ("KRAKEN USD PERPETUAL · WATCH ONLY" if ob.source == "KRAKEN_WATCH_ONLY"
                      else "BYBIT USDT PERPETUAL · WATCH ONLY" if ob.source == "BYBIT_WATCH_ONLY"
                      else "BINANCE USDⓈ-M PERPETUAL")
    quote = "USD" if ob.source == "KRAKEN_WATCH_ONLY" else "USDT"
    _signal_card(look, pair.contract, ob.last_price, contract_label, quote=quote)
    if ob.source != "BINANCE":
        st.warning("⚠️ " + failure + " · แสดง " +
                   ("Kraken USD" if ob.source == "KRAKEN_WATCH_ONLY" else "Bybit USDT") +
                   " Futures สำรองเพื่อเฝ้าดูเท่านั้น (WATCH ONLY) · ไม่มีข้อมูล Taker Flow ย้อนหลัง "
                   "จึงไม่ออก READY หรือสัญญาณเข้าซื้อขาย")
        if ob.source == "KRAKEN_WATCH_ONLY":
            st.caption("ข้อมูล Kraken เป็นสัญญา USD Perpetual ไม่ใช่ USDT; "
                       "ไม่ผสมราคาจาก Binance หรือ Bybit และไม่ใช้แทนราคา USDT แบบหนึ่งต่อหนึ่ง")
    if pair.multiplier != 1:
        st.info(f"สัญญา {pair.contract} = {pair.multiplier:,} {pair.underlying} · "
                f"ราคาต่อ {pair.underlying} ≈ {concise_price(pair.unit_price(ob.last_price))} {quote} · "
                "Entry/SL/TP ด้านล่างเป็นราคาต่อหน่วยสัญญา Futures")
    long_active = ob.direction == "LONG"
    short_active = ob.direction == "SHORT"
    st.markdown(f"""
<div class="orb-pair-grid">
  <div class="orb-pair {'active-long' if long_active else ''}">
    <h4>↗ LONG</h4><p>{'แนวโน้มสนับสนุน' if long_active else 'ยังไม่ผ่านเงื่อนไข'}</p>
  </div>
  <div class="orb-pair {'active-short' if short_active else ''}">
    <h4>↘ SHORT</h4><p>{'แนวโน้มสนับสนุน' if short_active else 'ยังไม่ผ่านเงื่อนไข'}</p>
  </div>
</div>""", unsafe_allow_html=True)
    st.markdown('<div class="orb-section"><strong>แผนเข้า–ออก</strong><span class="orb-subtle">ประเมินจาก Futures</span></div>',
                unsafe_allow_html=True)
    _support_resistance_panel(chart, quote, current_price=ob.last_price)
    if ob.entry_low is None or ob.entry_high is None:
        _watch_price_panel(indicative_zone(chart, side="LONG"),
                           "Futures · แนวรับสำหรับเฝ้า LONG", quote)
        _watch_price_panel(indicative_zone(chart, side="SHORT"),
                           "Futures · แนวต้านสำหรับเฝ้า SHORT", quote)
    else:
        _price_grid([("ENTRY LOW", ob.entry_low), ("ENTRY HIGH", ob.entry_high),
                     ("STOP LOSS", ob.stop), ("TAKE PROFIT 1", ob.tp1),
                     ("TAKE PROFIT 2", ob.tp2)])
    if ob.state.startswith("READY"):
        st.success("แท่ง 15M ยืนยันแล้วและราคาล่าสุดยังอยู่ในโซน · ตรวจออร์เดอร์จริงก่อนตัดสินใจ")
    elif ob.state.startswith("WATCH"):
        st.info("รอ Retest — ยังไม่ใช่สัญญาณเข้า อย่าไล่ราคา")
    else:
        st.caption("ยังไม่มีสัญญาณเข้าที่ผ่านเงื่อนไข · ราคาคาดการณ์ด้านบนเป็นเพียงโซนเฝ้าดู ไม่ใช่ Entry/SL/TP ที่อนุมัติ")
    if ob.net_rr_tp2 is not None:
        st.caption(f"Net R:R TP2 ≈ {ob.net_rr_tp2:.1f}:1 (ประเมินต้นทุน) · "
                   f"Risk จำลอง ≈ {ob.risk_usdt:.2f} {quote} · Notional ≈ {ob.notional_usdt:.2f} {quote}")
    a, b = st.columns(2)
    with a:
        st.caption(f"Funding ล่าสุด: {funding_pct:+.4f}%")
    with b:
        if st.button("↻ รีเฟรช", key="futures_refresh", width="stretch"):
            _futures_snapshot.clear()
            st.rerun()
    st.markdown('<div class="orb-section"><strong>กราฟ Futures 15M</strong><span class="orb-subtle">แท่งที่ปิดแล้ว</span></div>',
                unsafe_allow_html=True)
    st.line_chart(chart[["close"]], height=210)
    with st.expander("⚙️ ทุนและความเสี่ยงจำลอง", expanded=False):
        st.number_input(f"ทุนสมมติ ({quote})", min_value=100.0, max_value=10_000_000.0,
                        step=100.0, key="orbit_futures_capital")
        st.slider("เสี่ยงต่อสัญญาณ (%)", min_value=0.1, max_value=1.0, step=0.1,
                  key="orbit_futures_risk")
        st.caption("ค่าในหน้านี้เป็นแบบจำลอง ไม่ใช่ยอดเงินจริงหรือค่า Leverage ของ Exchange; "
                   "Telegram ใช้ค่าที่อยู่ใน futures_daytrade_config.json บน GitHub")
    with st.expander("ℹ️ รายละเอียดสัญญาณและข้อจำกัด", expanded=False):
        st.write(ob.reason)
        st.caption("1H+4H ต้องไปทิศเดียวกัน, 15M breakout และ Volume/Taker ยืนยัน, "
                   "รอ Retest กับราคายังอยู่ในโซนก่อนขึ้น READY")
        st.caption("ยังไม่มีผล Backtest/Walk-forward ของ Futures ชุดใหม่นี้ · "
                   "ฟิวเจอร์สมีความเสี่ยงสูง โดยเฉพาะ Leverage, Funding, Slippage และการถูก Liquidate")
    st.markdown('<div class="orb-footnote">READ ONLY · ไม่มีออร์เดอร์จริง · การแจ้งเตือน Telegram Futures ต้องติดตั้ง Workflow ใหม่บน GitHub</div>',
                unsafe_allow_html=True)


@st.cache_data(ttl=90, show_spinner=False)
def _public_paper_state() -> dict:
    repository = os.environ.get("ORBIT_PUBLIC_REPOSITORY", "Punnipah/orbit-crypto-signal-lab")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Repository ID ไม่ถูกต้อง")
    raw_url = (f"https://raw.githubusercontent.com/{repository}/orbit-futures-state/"
               ".orbit-futures/daytrade-alerts.json")
    with urlopen(Request(raw_url, headers={"User-Agent": "OrbitMobile/5.0"}), timeout=12) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or payload.get("schema") != 2:
        raise ValueError("ข้อมูลติดตามยังไม่ได้อัปเกรดเป็น v5")
    return payload


def alerts_screen() -> None:
    st.markdown('<div class="orb-section"><strong>Signal Tracker</strong><span class="orb-subtle">FUTURES · PAPER ONLY</span></div>',
                unsafe_allow_html=True)
    st.caption("ติดตามผลจำลองของสัญญาณ Futures จาก GitHub · ไม่ใช่ผลเทรดในบัญชีจริง")
    source = "GitHub public state"
    state = None
    uploaded = st.file_uploader("มีไฟล์ State JSON? อัปโหลดเพื่อดูผลแทน GitHub ได้", type=["json"],
                                key="orbit_paper_import", label_visibility="collapsed")
    if uploaded is not None:
        try:
            state = json.load(uploaded)
            if state.get("schema") != 2 or not isinstance(state.get("paper"), dict):
                raise ValueError("State ไม่ใช่ v5")
            source = "ไฟล์ที่เลือก"
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            st.error("ไฟล์ไม่ใช่ Futures State v5 ที่รองรับ")
            return
    else:
        try:
            state = _public_paper_state()
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError):
            st.info("ยังอ่านประวัติจาก GitHub ไม่ได้ · ต้องอัปเดต Workflow v5 และรันสำเร็จอย่างน้อยหนึ่งครั้ง "
                    "(ถ้า Repository เป็น Private ให้ดาวน์โหลด JSON จาก state branch มาอัปโหลด)")
            return
    health = state.get("health", {})
    paper = state.get("paper", {})
    history = paper.get("history", [])
    if not isinstance(history, list):
        st.warning("ประวัติในไฟล์ไม่ถูกต้อง")
        return
    metrics = paper_stats(history)
    checked = health.get("last_scan_at")
    st.markdown('<div class="orb-section"><strong>สถานะระบบ</strong><span class="orb-subtle">อ่านจาก '+escape(source)+'</span></div>',
                unsafe_allow_html=True)
    if checked:
        try:
            last = datetime.fromisoformat(checked)
            if last.tzinfo is None:
                raise ValueError("missing timezone")
            lag = (datetime.now(timezone.utc) - last).total_seconds() / 60
            stamp = last.astimezone(BKK).strftime("%d/%m %H:%M")
            coverage = health.get("market_data_ok", 0)
            monitored = health.get("monitored", 0)
            if lag > 40 or lag < -2:
                st.warning(f"⚠️ Futures Monitor ตรวจครั้งสุดท้าย {stamp} น. · ข้อมูลเก่าหรือเวลาไม่ถูกต้อง")
            elif health.get("status") != "OK" or not monitored or coverage != monitored:
                st.warning(f"⚠️ Futures Monitor ตรวจล่าสุด {stamp} น. · ข้อมูลพร้อม {coverage}/{monitored} คู่")
            else:
                st.success(f"● ระบบตรวจล่าสุด {stamp} น. · ข้อมูลที่ผ่าน: "
                           f"{coverage}/{monitored} คู่")
        except (TypeError, ValueError, OverflowError):
            st.warning("เวลาตรวจครั้งล่าสุดไม่ถูกต้อง")
    else:
        st.caption("ยังไม่พบข้อมูลรอบตรวจ")
    a, b = st.columns(2)
    a.metric("Paper ที่กำลังติดตาม", len(paper.get("active", {})))
    b.metric("Paper ที่ปิดแล้ว", metrics["trades"])
    a, b = st.columns(2)
    a.metric("Win Rate จำลอง", f"{metrics['win_rate_pct']:.1f}%" if metrics["win_rate_pct"] is not None else "—")
    b.metric("Expectancy จำลอง", f"{metrics['expectancy_r']:+.2f}R" if metrics["expectancy_r"] is not None else "—")
    a, b = st.columns(2)
    a.metric("Profit Factor", f"{metrics['profit_factor']:.2f}" if metrics["profit_factor"] is not None else "—")
    b.metric("Max Drawdown", f"{metrics['max_drawdown_r']:.2f}R")
    st.caption("ประมาณการหลังต้นทุนคงที่ แต่ยังไม่รวม Funding จริง/คำสั่งที่อาจไม่ได้ Fill; "
               "จำนวนดีลน้อยไม่สามารถยืนยันความได้เปรียบของกลยุทธ์")
    if metrics["trades"] < 100:
        st.warning(f"ผลทดลองยังไม่เพียงพอ: มี {metrics['trades']} ดีลจำลอง · "
                   "ยังไม่ควรใช้ Win Rate นี้อ้างความแม่นยำ")
    active = paper.get("active", {})
    if active:
        with st.expander(f"⏳ แผนจำลองที่ยังติดตาม ({len(active)})", expanded=True):
            for item in active.values():
                st.write(f"{item.get('requested', item.get('symbol'))} · {item.get('side')} · "
                         f"{'เข้า Paper แล้ว' if item.get('entry_at') else 'ยังรอเข้า'}")
    if history:
        df = pd.DataFrame(history)
        keep = [c for c in ("requested", "symbol", "side", "status", "net_r_estimate", "closed_at") if c in df]
        st.markdown("#### ผลสัญญาณจำลอง")
        st.dataframe(df[keep].iloc[::-1], hide_index=True, width="stretch")
        st.download_button("↓ ดาวน์โหลด Paper Journal CSV", df.to_csv(index=False).encode("utf-8-sig"),
                           file_name="orbit_futures_paper_journal.csv", mime="text/csv", width="stretch")
    else:
        st.info("ยังไม่มี Paper Trade ที่จบแล้ว · ระบบจะเริ่มเก็บหลังมีสัญญาณ READY และแท่งใหม่ตามมา")


@st.cache_data(ttl=3600, show_spinner=False)
def _proxy_research(symbol: str, days: int):
    pair = resolve_futures_pair(symbol, _futures_catalog())
    now = datetime.now(timezone.utc)
    frames = {tf: fetch_history(pair.contract, tf, days=days, now=now)
              for tf in ("15m", "1h", "4h")}
    settings = replace(read_futures_settings(ROOT / "futures_daytrade_config.json"),
                       symbols=(pair.contract,))
    return evaluate_historical_proxy(pair.contract, frames, settings)


def research_futures_panel() -> None:
    """A deliberately labelled technical proxy; not proof the live full signal wins."""
    with st.expander("🧪 Futures Technical Research · ทดลองย้อนหลัง", expanded=False):
        st.warning("งานวิจัยนี้ตรวจเฉพาะกฎแท่งปิดของ Futures: ยังไม่มี Mark/Funding ในอดีต, "
                   "Order Book, การเติมออร์เดอร์จริง และค่าทุนที่เปลี่ยนตามตลาด "
                   "จึงไม่ใช่ผล Backtest ที่พิสูจน์สัญญาณครบชุด")
        coin = st.selectbox("คู่ Futures ที่ต้องการทดสอบ", PAIRS, index=1,
                            key="orbit_futures_research_pair")
        days = st.select_slider("ข้อมูลย้อนหลัง (วัน)", options=[30, 45, 60], value=45,
                                key="orbit_futures_research_days")
        if st.button("▶ วิเคราะห์ข้อมูลย้อนหลัง", key="orbit_run_futures_proxy", width="stretch"):
            try:
                with st.spinner("กำลังดึงข้อมูลย้อนหลังและประเมินทีละแท่งที่ปิดแล้ว..."):
                    report = _proxy_research(coin, days)
                st.session_state["orbit_futures_proxy_report"] = report
            except (FuturesDataError, ValueError, RuntimeError, OSError, TypeError, KeyError) as exc:
                st.error("ยังประเมิน Futures Historical Proxy ไม่ได้: " + str(exc)[:160])
        report = st.session_state.get("orbit_futures_proxy_report")
        if report is None:
            return
        st.caption(f"ผลล่าสุด: {report.symbol} · ตรวจ {report.evaluated_bars:,} แท่ง 15M · "
                   "ใช้แท่ง 1H/4H ที่ปิดแล้ว ณ เวลานั้นเท่านั้น")
        a, b, c = st.columns(3)
        a.metric("ดีลจำลอง", report.all_stats["trades"])
        b.metric("Win Rate", f"{report.all_stats['win_rate_pct']:.1f}%"
                 if report.all_stats["win_rate_pct"] is not None else "—")
        c.metric("Expectancy", f"{report.all_stats['expectancy_r']:+.2f}R"
                 if report.all_stats["expectancy_r"] is not None else "—")
        if report.all_stats["trades"] < 100:
            st.warning("จำนวนดีลจำลองไม่พอสำหรับยืนยันความแม่นยำ แม้ผลชั่วคราวจะเป็นบวก")
        split = pd.DataFrame([{"ช่วง": "ครึ่งแรก", "ดีล": report.early_stats["trades"],
                               "Expectancy (R)": report.early_stats["expectancy_r"]},
                              {"ช่วง": "ครึ่งหลัง (Holdout)", "ดีล": report.later_stats["trades"],
                               "Expectancy (R)": report.later_stats["expectancy_r"]}])
        st.dataframe(split, hide_index=True, width="stretch")
        st.caption("แบ่งช่วงตามเวลาโดยไม่ใช้ข้อมูลครึ่งหลังปรับเกณฑ์ · เป็น Holdout ของ Technical Proxy "
                   "ไม่ใช่ Walk-forward ของระบบ Futures เต็มรูปแบบ")
