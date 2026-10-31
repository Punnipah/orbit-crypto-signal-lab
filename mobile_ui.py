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
.orb-version { color: #8fa8bb; font-size: 11px; margin-top: 5px; letter-spacing: 1.2px; }
.orb-live { white-space: nowrap; color: #85eac1; background:#0d302e;
  border:1px solid #1e6157; font-size:10px; letter-spacing:.5px;
  font-weight:800; padding:7px 9px; border-radius:40px; }
.orb-section { display:flex; justify-content:space-between; align-items:center; gap:10px;
  margin-top:11px; margin-bottom:9px; }
.orb-section strong { color:#e9f5fa; font-size:17px; font-weight:780; }
.orb-subtle { color:#93acbd; font-size:12px; }
.orb-hero { border:1px solid #36586b; background: linear-gradient(125deg,#173849,#0b2231 67%,#17294c);
  box-shadow: 0 15px 42px #00000045; border-radius:24px; padding:21px;
  margin: 13px 0 10px; overflow:hidden; }
.orb-hero.good {border-color:#287967; background:linear-gradient(115deg,#12342f,#0d202f 70%);}
.orb-hero.danger {border-color:#7b344a; background:linear-gradient(115deg,#361d2d,#111e2e 80%);}
.orb-hero.warning {border-color:#65603e;}
.orb-hero-title {font-size:13px; color:#a6bfce; margin-bottom:5px; font-weight:600;}
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
.orb-kv-label {color:#8ca7b7;font-size:11px;font-weight:700;letter-spacing:.3px;}
.orb-pair-grid {display:grid; grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:9px 0;}
.orb-pair {background:#10202e;border:1px solid #264152;border-radius:15px;padding:14px 12px;}
.orb-pair.active-long {border-color:#1eab7e;background:#11362d;}
.orb-pair.active-short {border-color:#da687d;background:#352332;}
.orb-pair h4 {margin:0;color:#edf7fa;font-size:15px;}
.orb-pair p {margin:5px 0 0;color:#99b3c2;font-size:12px;}
.orb-footnote {font-size:11px; color:#7896a8; padding:9px 0 2px;}
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
  border-color:#374b55 !important; opacity:.75 !important;
}
div.stButton > button:hover:not(:disabled), div.stDownloadButton > button:hover:not(:disabled) {
  background:#1d5c61 !important; border-color:#70e9bb !important;
}
div[data-testid="stSegmentedControl"] button,
div[data-testid="stPills"] button {color:#142b37 !important;}
div[data-testid="stSegmentedControl"] button[aria-checked="true"],
div[data-testid="stPills"] button[aria-checked="true"] {
  background:#174c49 !important; color:#e6fff5 !important;
  border-color:#55d7ae !important;
}
div[data-testid="stExpander"] {border:1px solid #263d4d; border-radius:14px; background:#0d1a28;}
@media(max-width:640px) {
 .block-container {padding:0.65rem 0.75rem 8rem !important;}
 .orb-brand {margin:1px 0 11px;}
 .orb-mark {width:38px;height:38px;flex-basis:38px;border-radius:13px;}
 .orb-live {font-size:9px;padding:6px 7px;}
 .orb-hero {padding:16px;margin-top:10px;border-radius:19px;}
 div[data-testid="stMetricValue"] {font-size:1.18rem;}
 div[data-testid="stMetricLabel"] {font-size:.75rem;}
 div[data-testid="stDataFrame"] {max-width:100%;}
 h2 {font-size:1.28rem!important;}
 div.st-key-orbit_screen {position:fixed;z-index:995;bottom:max(9px,env(safe-area-inset-bottom));
   left:10px;right:10px;box-shadow:0 13px 45px #000000b0;}
 div.st-key-orbit_screen button {font-size:12px !important; min-height:48px !important;}
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
         <div class="orb-version">ULTIMATE SIGNAL · V5.8</div></div>
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


@st.cache_data(ttl=45, show_spinner=False)
def _scalp_live(venue: str, symbol: str, refresh_id: int):
    """Independent, venue-native public data; never call exchange order APIs."""
    from scalp_engine import evaluate_scalp, read_scalp_settings
    from scalp_marketdata import fetch_snapshot

    settings = read_scalp_settings(ROOT / "scalp_config.json")
    snap = fetch_snapshot(venue, symbol)
    return evaluate_scalp(snap, settings), snap, settings


def scalp_screen() -> None:
    """Mobile review of v5.8 AUTO REGIME Spot/Futures signals and health."""
    from scalp_marketdata import MarketDataError

    st.markdown("## ⏱️ Scalp Signal v5.8 · AUTO REGIME")
    st.caption("Trend Breakout หรือ Sideways Range Reversal → แท่ง 1m ปิดยืนยัน · PAPER ONLY · ไม่มีการส่งออร์เดอร์")
    market = st.radio("เลือกตลาด", ["Spot · Binance TH", "Futures · Binance Global",
                                   "Futures · Bitget (ตลาดแยก)"],
                      horizontal=True, key="scalp_market")
    venue = ("BINANCE_TH_SPOT" if market.startswith("Spot") else
             "BITGET_USDT_FUTURES" if "Bitget" in market else "BINANCE_GLOBAL_USDM")
    pairs = ["BTCUSDT", "ETHUSDT", "PEPEUSDT", "DOGEUSDT"]
    symbol = st.selectbox("คู่เหรียญ USDT", pairs, key="scalp_symbol")
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
        return
    colors = {"READY": "good", "WATCH": "warning", "EXIT_WATCH": "warning",
              "RISK_BLOCK": "danger"}
    color = colors.get(ob.state, "warning")
    heading = {"READY": "READY · พิจารณาได้เฉพาะช่วงเวลาสั้น ๆ",
               "WATCH": "WATCH · ยังไม่ใช่สัญญาณเข้า",
               "EXIT_WATCH": "SELL WATCH · Spot ขาลง",
               "RISK_BLOCK": "RISK BLOCK · งดเข้า",
               "WAIT": "WAIT · รอรูปแบบราคา"}.get(ob.state, ob.state)
    st.markdown(f'<div class="orb-hero {color}">'
                f'<div class="orb-hero-title">{escape(symbol)} · {escape(market)}</div>'
                f'<div class="orb-hero-value">{escape(heading)}</div>'
                f'<div class="orb-hero-note">{escape(ob.reason)}</div></div>',
                unsafe_allow_html=True)
    st.caption(f"Market Regime: {ob.market_regime} · Strategy: {ob.strategy} · "
               "Sideways จะเข้าใกล้ขอบกรอบเท่านั้น ไม่เข้าเมื่อราคากลางกรอบ")
    if ob.early_reversal_note:
        st.info(ob.early_reversal_note + " · เป็นข้อมูลเฝ้าดูเท่านั้น ไม่ยกเลิก RISK BLOCK")
    st.markdown(f"**Bid:** `{concise_price(snap.bid)}` · "
                f"**Ask:** `{concise_price(snap.ask)}` · **Spread:** `{snap.spread_bps:.1f} bps`")
    st.caption(f"อ้างอิงข้อมูล ณ {snap.checked_at.astimezone(BKK):%d/%m/%Y %H:%M:%S} น. (ไทย) "
               "· แท่ง 1m/5m/15m ปิดจริง · Bid/Ask อาจเปลี่ยนทันที")
    if ob.entry is not None:
        st.markdown("### แผนจำลอง (ไม่ใช่ออร์เดอร์)")
        _price_grid([("Entry Bid/Ask", ob.entry), ("Stop Loss", ob.stop),
                     ("TP1", ob.tp1), ("TP2", ob.tp2)])
        st.caption(f"Position ~{ob.notional_usdt:.2f} USDT / Qty {ob.qty:g} · "
                   f"ความเสี่ยงสุทธิจำลอง {ob.risk_usdt:.3f} USDT · "
                   f"Net TP2 R:R ~{ob.net_rr:.2f}:1")
        if ob.expires_at:
            st.warning(f"READY หมดอายุ {ob.expires_at.astimezone(BKK):%H:%M:%S} น. "
                       "· ก่อนซื้อให้ตรวจราคาจริงและ Spread ใหม่")
    st.info(f"ทุนตั้งต้นจำลอง {cfg.capital_usdt:.0f} USDT · เสี่ยงต่อครั้ง "
            f"{cfg.risk_per_trade_pct:.2f}% · เพดานความเสี่ยงของการแจ้งเตือน "
            f"{cfg.daily_risk_budget_pct:.1f}%/วัน (ไม่ใช่ระบบติดตามออร์เดอร์จริง)")
    st.caption("Telegram Scalp ทำงานจาก GitHub Actions ทุก ~5 นาทีเมื่อ Scheduler ทำงาน "
               "· ปิดเว็บได้ · สัญญาณ 1 นาทีอาจพลาดเพราะรอบสแกน · "
               "ต้องเปิดใช้งาน Workflow orbit-scalp-signal.yml ก่อน")
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
    st.markdown('<div class="orb-section"><strong>แผนราคา</strong><span class="orb-subtle">USDT · ไม่ใช่คำสั่งซื้อ</span></div>',
                unsafe_allow_html=True)
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
    return replace(result, source=source), frames["15m"].tail(90)[["close"]], funding, pair, failure


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
    _price_grid([("ENTRY LOW", ob.entry_low), ("ENTRY HIGH", ob.entry_high),
                 ("STOP LOSS", ob.stop), ("TAKE PROFIT 1", ob.tp1),
                 ("TAKE PROFIT 2", ob.tp2)])
    if ob.state.startswith("READY"):
        st.success("แท่ง 15M ยืนยันแล้วและราคาล่าสุดยังอยู่ในโซน · ตรวจออร์เดอร์จริงก่อนตัดสินใจ")
    elif ob.state.startswith("WATCH"):
        st.info("รอ Retest — ยังไม่ใช่สัญญาณเข้า อย่าไล่ราคา")
    else:
        st.caption("ยังไม่มีแผนเข้าที่ผ่านเงื่อนไข จึงไม่สร้างราคา Entry/SL/TP สมมติ")
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
    st.line_chart(chart, height=210)
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
