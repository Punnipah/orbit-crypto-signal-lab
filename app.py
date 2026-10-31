"""Orbit Crypto Signal Lab — mobile-friendly, read-only market dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from advanced_evidence import analyze_spot_evidence, interpret_spot_evidence
from backtest_engine import BacktestConfig, simulate, walk_forward
from btc_market import btc_context_checks, btc_regime
from binance_data import (HIGHER_TIMEFRAME, POPULAR_QUOTES, PublicDataError,
                          TIMEFRAMES, count_time_gaps, fetch_catalog, fetch_klines,
                          fetch_spot_last_price, search_catalog)
from coinglass_overlay import CoinGlassSnapshot, confirm_signal, parse_quick_paste
from confluence import combine_timeframes
from bybit_intelligence import fetch_bybit_evidence
from display_format import format_price, format_signed_price
from entry_planner import EntryPlan, plan_entry
from journal_utils import combine_journal, export_signal_journal, import_signal_journal
from indicative_zones import indicative_zone
from macro_liquidity import fetch_market_liquidity
from market_microstructure import fetch_microstructure, microstructure_checks
from monitor_engine import read_settings
from mtf_research import historical_mtf_features, mtf_walk_forward, run_mtf_backtest
from multi_timeframe import RuleCheck, build_timeframe_report
from public_derivatives import DerivativesDataError, evaluate_derivatives, fetch_with_fallback
from research_engine import latest_reasons, prepare_features, with_signal
from risk_audit import audit_entry
from rally_watch import evaluate_rally
from signal_outcomes import evaluate_recorded_signals
from watch_plans import decode_watch, encode_watch, evaluate_watch, new_watch_plan


BKK = ZoneInfo("Asia/Bangkok")


@st.cache_data(ttl=3600, show_spinner=False)
def get_catalog():
    return fetch_catalog()


@st.cache_data(ttl=180, show_spinner=False)
def get_candles(symbol: str, tf: str, n: int):
    return fetch_klines(symbol, tf, n)


@st.cache_data(ttl=15, show_spinner=False)
def get_spot_quote(symbol: str):
    return fetch_spot_last_price(symbol)


@st.cache_data(ttl=180, show_spinner=False)
def get_derivatives(symbol: str):
    return fetch_with_fallback(symbol)


@st.cache_data(ttl=25, show_spinner=False)
def get_microstructure(symbol: str, notional: float):
    return fetch_microstructure(symbol, notional)


@st.cache_data(ttl=180, show_spinner=False)
def get_bybit_context(symbol: str):
    try:
        return fetch_bybit_evidence(symbol), None
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        return None, str(exc)


@st.cache_data(ttl=900, show_spinner=False)
def get_market_liquidity():
    try:
        return fetch_market_liquidity(), None
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        return None, str(exc)


def plot_prices(f: pd.DataFrame, symbol: str, timeframe: str, plan: EntryPlan | None = None):
    recent = f.tail(180)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.77, 0.23], vertical_spacing=0.035)
    fig.add_trace(go.Candlestick(x=recent.index, open=recent["open"], high=recent["high"],
                                 low=recent["low"], close=recent["close"], name="ราคา"), row=1, col=1)
    for name, color in (("ema20", "#eab308"), ("ema50", "#60a5fa"), ("ema200", "#c084fc")):
        fig.add_trace(go.Scatter(x=recent.index, y=recent[name], mode="lines", name=name.upper(),
                                 line=dict(color=color, width=1.6)), row=1, col=1)
    last = recent.iloc[-1]
    for key, color, label in (("pivot_high", "#fb923c", "Pivot High"),
                              ("pivot_low", "#34d399", "Pivot Low")):
        if pd.notna(last[key]):
            fig.add_hline(y=float(last[key]), line_width=1, line_dash="dot", line_color=color,
                          annotation_text=label, row=1, col=1)
    if plan is not None and plan.entry_low is not None and plan.entry_high is not None:
        fig.add_hrect(y0=plan.entry_low, y1=plan.entry_high, fillcolor="rgba(16,185,129,0.15)",
                      line_width=1, line_color="#10b981", row=1, col=1,
                      annotation_text="Entry Zone (ทดลอง)", annotation_position="top left")
    colors = ["#22c55e" if c >= o else "#ef4444" for c, o in zip(recent["close"], recent["open"])]
    fig.add_trace(go.Bar(x=recent.index, y=recent["volume"], marker_color=colors,
                         opacity=0.65, name="Volume"), row=2, col=1)
    fig.update_layout(template="plotly_dark", height=490,
                      margin=dict(l=2, r=2, t=22, b=8), xaxis_rangeslider_visible=False,
                      legend=dict(orientation="h", y=1.06, x=0, font=dict(size=10)))
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    return fig


def render_watch_panel(symbol: str, frozen_plan, proposed_plan: EntryPlan | None,
                       bars_15m, current_quote, mtf_signal: str, *,
                       live_mtf_ready: bool = False, context_ready: bool = False):
    """Keep saved prices distinct from the ever-changing live MTF calculation."""
    st.subheader("🧷 แผนเฝ้าดูที่ล็อกไว้ · ย้อนกลับมาเปิดใหม่ได้")
    st.caption("แตะ Entry Zone ≠ ซื้อทันที · ระบบติดตามแท่ง 15m ที่ *ปิดแล้ว* ตั้งแต่เวลาล็อกแผน "
               "และตรวจซ้ำทุก 3 นาทีเมื่อเปิดหน้าเว็บไว้")

    if frozen_plan is not None and frozen_plan.symbol != symbol:
        st.warning(f"ลิงก์นี้เก็บแผน {frozen_plan.symbol} แต่กำลังดู {symbol} · "
                   "เลือกเหรียญในแผนก่อนจึงจะตรวจสถานะได้")
    elif frozen_plan is not None:
        st.markdown("**🔒 Entry Zone เดิม (ไม่เลื่อนตามราคาสด)**")
        st.code(f"{format_price(frozen_plan.entry_low)} – {format_price(frozen_plan.entry_high)}")
        c1, c2 = st.columns(2)
        c1.metric("Stop Loss", format_price(frozen_plan.stop_loss))
        c2.metric("TP1", format_price(frozen_plan.take_profit_1))
        st.caption(f"TP2 เดิม: **{format_price(frozen_plan.take_profit_2)}**")
        st.caption(f"ล็อก {frozen_plan.created_at.astimezone(BKK):%d/%m/%Y %H:%M} น. "
                   f"· หมดอายุ {frozen_plan.expires_at.astimezone(BKK):%d/%m/%Y %H:%M} น. "
                   "· ลิงก์นี้ไม่บันทึกข้อมูลในฐานข้อมูล")
        try:
            result = evaluate_watch(frozen_plan, bars_15m, now=datetime.now(timezone.utc),
                                    current_price=current_quote, mtf_buy=mtf_signal == "BUY")
            labels = {
                "WAIT_ZONE": "🟡 ยังไม่ถึงโซน — เฝ้าดูต่อ",
                "WAIT_TOUCH": "🟡 ราคาเพิ่งแตะโซน — ยังไม่ซื้อ",
                "WAIT_RECLAIM": "🟡 รอแท่งปิดกลับเหนือโซน",
                "WAIT_BREAK": "🔵 กลับเข้าโซนแล้ว — รอยืนยันโครงสร้าง",
                "WAIT_MTF": "🟡 มี Trigger แต่ MTF ยังไม่ผ่าน",
                "WAIT_RISK": "🟡 มี Trigger แต่ R:R ไม่คุ้ม",
                "READY_NOW": "🟢 Entry Trigger ผ่านแล้ว (มีเงื่อนไข)",
                "INVALIDATED": "🔴 แผนถูกยกเลิก — ไม่เข้าซื้อ",
                "PASSED": "⚪ จังหวะเดิมผ่านไปแล้ว — ห้ามไล่ราคา",
                "EXPIRED": "⚪ แผนหมดอายุ",
                "DATA_GAP": "🟠 ข้อมูลแท่งขาดช่วง",
                "DATA_STALE": "🟠 ข้อมูลแท่งเก่า",
                "DATA_MISSING": "🟠 ข้อมูลไม่ครบ",
            }
            label = labels.get(result.status, result.status)
            if result.status == "READY_NOW":
                st.success(f"**{label}** · {result.reason}")
            elif result.status == "INVALIDATED":
                st.error(f"**{label}** · {result.reason}")
            else:
                st.info(f"**{label}** · {result.reason}")
            # Price-escape advisories are separate from the original Frozen
            # entry trigger. They NEVER move the frozen entry/SL/TP.
            rally_rules = read_settings(Path(__file__).with_name("monitor_config.json")).rally_settings()
            rally = evaluate_rally(frozen_plan, bars_15m,
                                   now=datetime.now(timezone.utc), current_price=current_quote,
                                   frozen_status=result.status, context_ready=context_ready,
                                   live_mtf_ready=live_mtf_ready,
                                   new_entry=proposed_plan, settings=rally_rules)
            if rally.status == "BREAKOUT_WATCH":
                st.warning("🚀 **ราคาเริ่มวิ่งหนี Frozen Zone** · " + rally.reason)
            elif rally.status == "MISSED_ENTRY":
                st.warning("🟠 **โอกาสในแผนเดิมอาจผ่านไปแล้ว** · " + rally.reason)
            elif rally.status == "NEW_SETUP_CANDIDATE":
                st.info("🔄 **มีโซน MTF สดใหม่ให้ตรวจสอบ** · " + rally.reason)
                st.caption(f"โซนใหม่เพื่อ *พิจารณาเท่านั้น*: "
                           f"{format_price(rally.new_entry_low)}–{format_price(rally.new_entry_high)} USDT "
                           "· หากต้องการใช้ต้องล็อกแผนใหม่และอัปเดต GitHub Secret เอง")
            for text_label, date_time in (("แตะโซน", result.touched_at),
                                          ("แท่ง Reclaim", result.reclaimed_at),
                                          ("Trigger ยืนยัน", result.triggered_at)):
                if date_time is not None:
                    st.caption(f"{text_label}: {date_time.astimezone(BKK):%d/%m %H:%M} น. (แท่งปิด)")
            if result.next_candle_close is not None:
                st.caption(f"รอบแท่ง 15m ถัดไป: {result.next_candle_close.astimezone(BKK):%d/%m %H:%M} น. "
                           "· ระบบจะประเมินต่อเมื่อแท่งปิดจริง")
            if result.net_rr_tp2 is not None:
                st.caption(f"Net R:R ถึง TP2 ณ ราคาสด ≈ {result.net_rr_tp2:.2f}R "
                           "(รวมต้นทุนจำลอง ไม่ใช่ผลรับประกัน)")
            if result.status == "READY_NOW":
                st.warning("READY เป็นกฎทดลอง ไม่ใช่คำสั่งซื้อ ราคาอาจวิ่งก่อนส่งคำสั่งและ "
                           "SL อาจเกิด Slippage ได้ · ต้องตรวจราคา Bid/Ask และขนาดสถานะด้วยตนเอง")
        except (ValueError, TypeError, IndexError, KeyError) as exc:
            st.warning(f"ยังประเมินแผนที่ล็อกไว้ไม่ได้: {exc}")
    else:
        st.info("ยังไม่ได้ล็อกแผนสำหรับเหรียญนี้ · แผน MTF สดจะเปลี่ยนตามแท่งใหม่เสมอ")

    if frozen_plan is not None:
        if st.button("🗑️ เลิกใช้แผนที่ล็อกไว้", key="watch_clear", width="stretch"):
            st.query_params.pop("watch", None)
            st.rerun()
    if proposed_plan is not None and all(getattr(proposed_plan, field) is not None
                                         for field in ("entry_low", "entry_high", "stop_loss",
                                                       "take_profit_1", "take_profit_2")):
        st.caption("แผน MTF สดปัจจุบัน (ใช้เฉพาะเมื่อเลือกล็อกใหม่): "
                   f"{format_price(proposed_plan.entry_low)} – {format_price(proposed_plan.entry_high)}")
        hours = st.selectbox("เฝ้าดูแผนนี้นานเท่าไร", [12, 24, 48, 72], index=2,
                             format_func=lambda x: f"{x} ชั่วโมง", key="watch_hours")
        if st.button("🧷 ล็อก Entry Zone ปัจจุบันเป็นแผนเฝ้าดู", key="watch_save", width="stretch"):
            try:
                locked = new_watch_plan(symbol, proposed_plan, now=datetime.now(timezone.utc),
                                        hours=hours, fee_pct=fee_pct, slippage_pct=slip_pct,
                                        min_net_rr=min_rr)
                st.query_params["watch"] = encode_watch(locked)
                st.rerun()
            except (ValueError, TypeError) as exc:
                st.error(f"ล็อกแผนไม่ได้: {exc}")
    else:
        st.caption("แผนสดยังไม่มี Entry/SL/TP ครบ จึงยังล็อกแผนใหม่ไม่ได้")
    if frozen_plan is not None:
        st.success("📱 **วิธีกลับมาดูราคาเดิม:** เพิ่มหน้านี้เป็น Bookmark หรือแชร์/คัดลอก "
                   "URL ที่มี `?watch=` เก็บไว้ · เปิดลิงก์นั้นบนมือถือภายหลัง แผนเดิมจะกลับมา")
        app_url = st.context.url
        watch_value = st.query_params.get("watch")
        if app_url and watch_value:
            st.caption("**แตะไอคอน Copy มุมขวาของช่องนี้ แล้วเก็บใน Notes/LINE ส่วนตัว หรือ Bookmark:**")
            st.code(f"{app_url}?watch={watch_value}", language=None, wrap_lines=True)
        st.caption("ไม่มีบัญชี/ฐานข้อมูลเก็บให้: หากกลับเข้าเว็บจากลิงก์หน้าแรกที่ไม่มี `?watch=` "
                   "แผนจะไม่ถูกเรียกคืน · เว็บที่ปิดอยู่ไม่ส่งแจ้งเตือนเอง")


def coin_glass_panel(base_asset: str):
    snapshot = st.session_state.get("coinglass_snapshot")
    now_th = datetime.now(BKK)
    with st.expander("🧭 CoinGlass — ข้อมูลยืนยันสัญญาณ (กรอกเอง)", expanded=snapshot is None):
        st.markdown(f"อ่านข้อมูลจาก [CoinGlass](https://www.coinglass.com/) สำหรับเหรียญ **{base_asset}** แล้วกรอกข้อมูลล่าสุด")
        st.caption("Funding ใช้หน่วยเปอร์เซ็นต์ เช่น 0.01 = 0.01% · OI และ Liquidations ให้ใช้กรอบ 24 ชั่วโมง")
        st.caption("📱 กรอกเร็ว: วางตัวเลข 5 ค่าในช่องเดียวตามลำดับ Funding%, OI 24h%, L/S Ratio, Long Liq USD, Short Liq USD (คั่นด้วยคอมมา)")
        st.caption("⚠️ ถ้าค่ามาจากต่างตลาด (เช่น L/S ของ OKX แต่ OI รวมทุกกระดาน) ให้ใช้เพื่อประกอบการวิเคราะห์เท่านั้น เพราะชุดข้อมูลไม่ตรงขอบเขตกัน")
        pasted = st.text_area("วางตัวเลข CoinGlass 5 ค่า (ไม่บังคับ)",
                              placeholder="0.01, 2.50, 1.10, 120000, 90000", height=80,
                              help="เป็นเพียงตัวอย่างรูปแบบ ห้ามใช้เลขตัวอย่างเป็นข้อมูลตลาดจริง")
        values = None
        if pasted.strip():
            try:
                values = parse_quick_paste(pasted)
            except ValueError as exc:
                st.error(f"รูปแบบไม่ถูกต้อง: {exc}")
                values = None
        if values is not None:
            st.success("อ่านตัวเลขได้ 5 ค่าแล้ว กรุณาตรวจหน่วยและเหรียญก่อนบันทึก")
        with st.form("coinglass_entry"):
            a, b = st.columns(2)
            with a:
                date_seen = st.date_input("วันที่ที่อ่านข้อมูล (ไทย)", value=now_th.date())
            with b:
                time_seen = st.time_input("เวลาที่อ่านข้อมูล (ไทย)", value=now_th.time().replace(second=0, microsecond=0))
            a, b = st.columns(2)
            with a:
                funding = st.number_input("Funding Rate (%)", value=values[0] if values else 0.0, min_value=-5.0,
                                          max_value=5.0, step=0.001, format="%.4f")
            with b:
                oi_change = st.number_input("OI Change 24h (%)", value=values[1] if values else 0.0, min_value=-100.0,
                                            max_value=1000.0, step=0.1, format="%.2f")
            ratio = st.number_input("Long/Short Accounts Ratio", value=values[2] if values else 1.0, min_value=0.01,
                                    max_value=50.0, step=0.01, format="%.3f")
            a, b = st.columns(2)
            with a:
                long_liq = st.number_input("Liquidated Long 24h (USD)", value=values[3] if values else 0.0,
                                           min_value=0.0, step=100000.0, format="%.2f")
            with b:
                short_liq = st.number_input("Liquidated Short 24h (USD)", value=values[4] if values else 0.0,
                                            min_value=0.0, step=100000.0, format="%.2f")
            confirmed = st.checkbox("ยืนยันว่าคัดลอกจาก CoinGlass จริงและตรวจหน่วยแล้ว")
            if st.form_submit_button("บันทึก CoinGlass", width="stretch"):
                if not confirmed:
                    st.error("กรุณายืนยันก่อนบันทึก")
                else:
                    snapshot = CoinGlassSnapshot(
                        symbol=base_asset, observed_at=datetime.combine(date_seen, time_seen, tzinfo=BKK),
                        funding_rate_pct=float(funding), oi_change_24h_pct=float(oi_change),
                        long_short_account_ratio=float(ratio),
                        long_liquidations_usd_24h=float(long_liq),
                        short_liquidations_usd_24h=float(short_liq),
                    )
                    st.session_state["coinglass_snapshot"] = snapshot
                    st.success("บันทึกข้อมูลเรียบร้อย")
    return snapshot


st.set_page_config(page_title="Orbit 5 · Spot & Futures", page_icon="🪐",
                   layout="wide", initial_sidebar_state="collapsed")
# v5.0 MOBILE-FIRST: quick Spot, real USD-M Futures, and PAPER tracker each have
# read-only mobile cards. The entire original analysis/research workflow below
# remains available through Lab; none of its calculations are replaced.
import mobile_ui

mobile_ui.style()
screen = mobile_ui.top_navigation()
if screen != mobile_ui.LAB:
    if screen == mobile_ui.ALERTS:
        mobile_ui.alerts_screen()
    elif screen == mobile_ui.SCALP:
        mobile_ui.scalp_screen()
    else:
        active_symbol = mobile_ui.chosen_symbol(st.query_params.get("watch"))
        if screen == mobile_ui.FUTURES:
            mobile_ui.futures_screen(active_symbol)
        else:
            mobile_ui.spot_screen(active_symbol, st.query_params.get("watch"))
    st.stop()

st.markdown("## 🔬 Orbit Lab")
st.caption("กราฟเต็ม · Frozen Watch · CoinGlass · Backtest · Walk-forward · Telegram · Futures Research")
mobile_ui.research_futures_panel()

frozen_watch = None
watch_query_error = None
watch_token = st.query_params.get("watch")
if watch_token:
    try:
        frozen_watch = decode_watch(watch_token)
    except ValueError as exc:
        watch_query_error = str(exc)
if watch_query_error:
    st.warning(f"ลิงก์เฝ้าดูที่แนบมาอ่านไม่ได้: {watch_query_error} · เปิดแผนใหม่ได้")
elif frozen_watch is not None:
    st.success(f"🧷 **มีแผนที่ล็อกไว้สำหรับ {frozen_watch.symbol}** · "
               f"Entry {format_price(frozen_watch.entry_low)}–{format_price(frozen_watch.entry_high)} "
               "· ไม่ถูกเขียนทับเมื่อราคาเปลี่ยน")
    if st.session_state.get("orbit_watch_loaded_token") != watch_token:
        st.session_state["coin_search"] = frozen_watch.symbol[:-4]
        st.session_state["orbit_watch_loaded_token"] = watch_token
else:
    st.session_state.pop("orbit_watch_loaded_token", None)

with st.expander("⚙️ เลือกเหรียญและตั้งค่าการวิเคราะห์", expanded=False):
    st.subheader("ค้นหาเหรียญ")
    try:
        catalog = get_catalog()
    except PublicDataError as exc:
        st.error(f"ไม่สามารถดึงรายการเหรียญได้: {exc}")
        st.info("ตรวจการเชื่อมต่ออินเทอร์เน็ตและลองใหม่ ภูมิภาคหรือเครือข่ายบางแห่งอาจจำกัด API")
        st.stop()
    quote = st.selectbox("สกุลเงินที่ใช้เทียบ", POPULAR_QUOTES + ["ทั้งหมด"], index=0)
    query = st.text_input("ค้นหารหัสเหรียญ / ชื่อที่รู้จัก", placeholder="เช่น BTC, Bitcoin, XRP, DOGE",
                          key="coin_search")
    matches = search_catalog(catalog, query, quote)
    if not matches:
        st.warning("ไม่พบคู่ตลาดที่ค้นหา ลองสกุลเงินที่ใช้เทียบอื่น")
        st.stop()
    labels = {item["symbol"]: f"{item['base']}/{item['quote']} · {item['symbol']}" for item in matches}
    symbols = list(labels)
    preferred = frozen_watch.symbol if frozen_watch is not None else "BTCUSDT"
    default = symbols.index(preferred) if preferred in symbols else 0
    symbol = st.selectbox("เลือกคู่เหรียญ", symbols, index=default, format_func=lambda s: labels[s])
    selected = next(item for item in matches if item["symbol"] == symbol)
    timeframe = st.selectbox("Timeframe สำหรับกราฟละเอียด/Backtest เท่านั้น", list(TIMEFRAMES), index=1,
                             help="หน้า Single MTF วิเคราะห์ทั้ง 4 ช่วงเวลาให้อัตโนมัติ ไม่ต้องเลือก Timeframe")
    history_size = st.select_slider("จำนวนแท่งประวัติ", options=[1000, 1500, 3000, 5000, 8000], value=1000,
                                    help="เริ่มต้น 1000 แท่งเพื่อให้ตรงกับ Telegram Monitor v4.1; เปลี่ยนค่าได้เพื่อวิจัยเพิ่มเติม แต่สัญญาณสดอาจต่างจาก Monitor")
    pivot_bars = st.slider("ความเข้มงวดของ Pivot", 2, 6, value=3)
    st.divider()
    st.header("จำลองความเสี่ยง")
    capital = st.number_input("ทุนจำลอง (หน่วยสกุลราคา)", value=10000.0, min_value=100.0, step=500.0)
    risk_pct = st.slider("ยอมเสี่ยงต่อดีล (%)", 0.25, 3.0, 1.0, step=0.25)
    allocation = st.slider("สัดส่วนเงินสูงสุดต่อดีล (%)", 5, 100, 30, step=5)
    fee_pct = st.number_input("ค่าธรรมเนียมต่อด้าน (%)", 0.0, 2.0, value=0.1, step=0.05, format="%.2f")
    slip_pct = st.number_input("Slippage ต่อด้าน (%)", 0.0, 2.0, value=0.05, step=0.05, format="%.2f")
    limit_dd = st.slider("หยุดเปิดสถานะเมื่อ Drawdown ถึง (%)", 5, 50, 25, step=5)
    min_rr = st.slider("R:R สุทธิจำลองขั้นต่ำถึง TP2", 1.0, 2.5, 1.5, step=0.25,
                       help="คำนวณที่ขอบบน Entry Zone รวม fee และ slippage แบบจำลอง; ไม่ใช่ผลตอบแทนรับประกัน")
    config = BacktestConfig(capital=capital, risk_per_trade_pct=risk_pct, max_allocation_pct=allocation,
                            fee_pct=fee_pct, slippage_pct=slip_pct, max_drawdown_pct=limit_dd)
    if st.button("🔄 ดึงข้อมูลใหม่", width="stretch"):
        get_catalog.clear()
        get_candles.clear()
        get_spot_quote.clear()
        get_derivatives.clear()
        get_microstructure.clear()
        get_bybit_context.clear()
        get_market_liquidity.clear()
        st.rerun()

htf = HIGHER_TIMEFRAME[timeframe]
try:
    with st.spinner("กำลังดึงประวัติราคาและคำนวณตัวชี้วัด..."):
        base = get_candles(symbol, timeframe, history_size)
        if htf == timeframe:
            higher = base
        else:
            htf_count = min(10000, max(600, int(history_size * TIMEFRAMES[timeframe] / TIMEFRAMES[htf]) + 260))
            higher = get_candles(symbol, htf, htf_count)
        features = prepare_features(base, higher, timeframe, pivot_bars=pivot_bars)
        analyzed = with_signal(features)
except (PublicDataError, ValueError, KeyError, IndexError) as exc:
    st.error(f"ไม่สามารถวิเคราะห์คู่ {symbol} ได้: {exc}")
    st.info("บางเหรียญมีประวัติไม่เพียงพอหรือ API ถูกจำกัด ลองลดจำนวนแท่งหรือเลือกตลาดอื่น")
    st.stop()

gaps = count_time_gaps(base, timeframe)
last_closed_at = base.index[-1] + timedelta(minutes=TIMEFRAMES[timeframe])
price_stale = last_closed_at.to_pydatetime() < datetime.now(timezone.utc) - timedelta(minutes=TIMEFRAMES[timeframe] * 2)
if gaps:
    st.warning(f"พบช่วงแท่งเทียนขาดหาย {gaps} จุด: Backtest จะถูกปิดเพื่อไม่สร้างผลลัพธ์คลาดเคลื่อน")
else:
    st.caption(f"ข้อมูล: Binance Spot public · {len(base):,} แท่ง · ไม่มีช่องว่างเวลา · ล่าสุด {base.index[-1].tz_convert(BKK):%d/%m/%Y %H:%M} น. (เวลาเริ่มแท่งที่ปิดแล้ว)")
if price_stale:
    st.warning("ราคาล่าสุดอาจเก่าเกินไป: ระบบจะไม่ยืนยันสัญญาณสดจนกว่าข้อมูลจะอัปเดต")

tabs = st.tabs(["🎯 สัญญาณ MTF รวม", "📊 สัญญาณละเอียด", "🧪 Backtest", "🔁 Walk-forward", "📈 MTF Research", "📖 คู่มือ", "📡 Telegram แจ้งเตือน"])
def render_multi_timeframe_dashboard():
    st.subheader(f"🎯 Single Multi-Timeframe Signal · {selected['base']}/{selected['quote']}")
    st.caption(
        "เลือกเหรียญเพียงครั้งเดียว ระบบวิเคราะห์ 15m + 1h + 4h + 1d เบื้องหลัง แล้วสรุปสัญญาณและแผน Entry ชุดเดียว"
    )
    st.info(
        "คะแนนรวมถ่วงน้ำหนัก 1d 30% + 4h 30% + 1h 25% + 15m 15% "
        "· ใช้แนวโน้มใหญ่กำหนดทิศทาง, 1h วางโซนราคา, 15m ยืนยันจังหวะ "
        "· **ไม่เฉลี่ยราคา Entry ทั้งสี่กรอบ** และคะแนนไม่ใช่เปอร์เซ็นต์โอกาสทำกำไร"
    )
    if derivatives is None:
        st.warning("Futures อัตโนมัติไม่พร้อม: ทุก Timeframe จะคง Final = WAIT จนกว่าจะได้ข้อมูลที่ใช้ได้")
    else:
        st.caption(f"Futures ที่ใช้ร่วมกัน: **{derivatives.source}** · ไม่ใช่ข้อมูล CoinGlass")
    if snapshot is None:
        st.caption("CoinGlass: **ยังไม่ได้กรอก** (ตัวกรองเสริม) · กรอกได้ที่แท็บ **📊 สัญญาณละเอียด** แล้วกลับมาดูผลรวมนี้")
    else:
        st.caption("CoinGlass: ใช้ชุดข้อมูลที่บันทึกสำหรับเหรียญนี้มาตรวจทุกกรอบ · เกณฑ์อายุข้อมูลของแต่ละกรอบไม่เท่ากัน (15m=1 ชม., 1h=2 ชม., 4h=4 ชม., 1d=24 ชม.)")
    if spot_quote is None:
        st.warning("ราคา Spot ล่าสุดไม่พร้อม จึงไม่มี Timeframe ใดแสดง READY ได้")
    else:
        st.caption(f"Spot จาก Binance ณ เวลาร้องขอ {spot_quote_time.astimezone(BKK):%d/%m/%Y %H:%M:%S} น.: **{format_price(spot_quote)} {selected['quote']}** · ไม่ใช่ราคา Bid/Ask")

    frame_bars = {timeframe: base}
    data_errors = {}
    with st.spinner("กำลังเทียบแท่งปิด 15m / 1h / 4h / 1d ..."):
        for tf in TIMEFRAMES:
            if tf not in frame_bars:
                try:
                    frame_bars[tf] = get_candles(symbol, tf, history_size)
                except (PublicDataError, ValueError, KeyError, IndexError) as exc:
                    data_errors[tf] = str(exc)

        reports = {}
        evaluated_frames = {}
        for tf in TIMEFRAMES:
            if tf in data_errors:
                continue
            parent_tf = HIGHER_TIMEFRAME[tf]
            if parent_tf not in frame_bars:
                data_errors[tf] = f"ข้อมูลกรอบใหญ่ {parent_tf} ไม่พร้อม"
                continue
            try:
                frame = frame_bars[tf]
                frame_analyzed = (analyzed if tf == timeframe else
                                  with_signal(prepare_features(frame, frame_bars[parent_tf],
                                                               tf, pivot_bars=pivot_bars)))
                reports[tf] = build_timeframe_report(
                    frame, frame_analyzed, tf,
                    base_asset=selected["base"], derivatives=derivatives,
                    coinglass=snapshot, now=datetime.now(timezone.utc),
                    current_price=spot_quote, capital=capital, risk_pct=risk_pct,
                    max_allocation_pct=allocation, fee_pct=fee_pct,
                    slippage_pct=slip_pct,
                )
                evaluated_frames[tf] = frame_analyzed
            except (PublicDataError, ValueError, KeyError, IndexError, TypeError) as exc:
                data_errors[tf] = str(exc)

    # Anonymous order-flow and liquidity footprint checks. These extra
    # read-only public endpoints may be unavailable by region; fail closed.
    order_notional = (reports["1h"].entry.notional
                      if "1h" in reports and reports["1h"].entry.notional is not None
                      else capital * allocation / 100)
    micro = None
    micro_error = None
    try:
        micro = get_microstructure(symbol, round(float(order_notional), 4))
    except (PublicDataError, ValueError, KeyError, TypeError) as exc:
        micro_error = str(exc)

    btc_context = None
    btc_error = None
    try:
        if symbol == "BTCUSDT" and "4h" in frame_bars and "1d" in frame_bars:
            btc_four, btc_day = frame_bars["4h"], frame_bars["1d"]
        else:
            btc_four = get_candles("BTCUSDT", "4h", 1000)
            btc_day = get_candles("BTCUSDT", "1d", 1000)
        btc_context = btc_regime(btc_four, btc_day, now=datetime.now(timezone.utc))
    except (PublicDataError, ValueError, KeyError, TypeError, IndexError) as exc:
        btc_error = str(exc)

    # Optional independent evidence is never silently treated as present.
    # These results are observations, not substitutes for Futures/Spot gates.
    with st.spinner("กำลังตรวจ Order Flow, ตลาดอื่น และสภาพคล่องมหภาคจาก Public API ..."):
        bybit_context, bybit_error = get_bybit_context(symbol)
        macro_context, macro_error = get_market_liquidity()
    spot_evidence = {}
    for tf in ("15m", "1h"):
        if tf in evaluated_frames:
            try:
                spot_evidence[tf] = analyze_spot_evidence(evaluated_frames[tf], tf)
            except (ValueError, KeyError, TypeError, IndexError):
                pass

    risk_audit = audit_entry(reports["1h"].entry if "1h" in reports else None,
                             fee_pct=fee_pct, slippage_pct=slip_pct, min_net_rr=min_rr)

    extra = list(microstructure_checks(micro, now=datetime.now(timezone.utc),
                                       requested_notional=order_notional))
    extra.extend(btc_context_checks(btc_context))
    extra.extend(risk_audit.checks)
    if bybit_context is not None and bybit_context.spot_mid is not None and micro is not None:
        binance_mid = (micro.bid + micro.ask) / 2
        deviation_pct = abs(bybit_context.spot_mid / binance_mid - 1) * 100
        extra.append(RuleCheck(
            "Spot สอง Exchange ไม่ต่างกันผิดปกติ (≤1.5%)",
            deviation_pct <= 1.5,
            f"Binance vs Bybit ต่างกัน {deviation_pct:.2f}% · ข้ามกระดาน/ไม่ใช่ราคาเติมออเดอร์"))
    for tf in ("1h", "15m"):
        report = reports.get(tf)
        share = report.taker_buy_share20 if report else float("nan")
        extra.append(RuleCheck(
            f"แรงซื้อเชิงรุกจากแท่ง {tf} 20 แท่ง ≥52%",
            pd.notna(share) and share >= .52,
            f"Taker Buy {share*100:.1f}%" if pd.notna(share) else "Taker Buy Volume ไม่พร้อม",
        ))
    if micro is not None and spot_quote is not None:
        midpoint = (micro.bid + micro.ask) / 2
        extra.append(RuleCheck("Spot Last Price ใกล้ Bid/Ask (ไม่เกิน 1%)",
                               abs(spot_quote - midpoint) / midpoint <= .01,
                               f"Mid {format_price(midpoint)} {selected['quote']}"))

    verdict = combine_timeframes(reports, additional_checks=extra)
    required_sources = {
        "Spot MTF 4 กรอบ": len(reports) == 4,
        "Spot Quote": spot_quote is not None,
        "Futures Public": derivatives is not None,
        "Binance Book/Trades": micro is not None,
        "BTC Regime": btc_context is not None and btc_context.clean,
        "Taker Buy History": all(tf in spot_evidence and spot_evidence[tf].delta_share20 is not None
                                 for tf in ("15m", "1h")),
    }
    optional_sources = {
        "Bybit cross-exchange": bybit_context is not None
                                 and bybit_context.spot_mid is not None,
        "Bybit Linear OI 24h": bybit_context is not None
                               and bybit_context.futures_oi_change_24h_pct is not None,
        "DefiLlama market liquidity": macro_context is not None
                                      and macro_context.stablecoin_supply_usd is not None,
        "CoinGlass (กรอกเอง)": snapshot is not None,
    }
    st.caption(f"หลักฐานตลาดที่ดึงสำเร็จ: **ข้อมูลหลัก {sum(required_sources.values())}/{len(required_sources)} แหล่ง** "
               f"· ข้อมูลเสริม {sum(optional_sources.values())}/{len(optional_sources)} แหล่ง "
               "· จำนวนแหล่งข้อมูล **ไม่ใช่ % ชนะตลาด**; ข้อมูลที่ไม่มีจะไม่ถูกแต่งขึ้น")
    with st.expander("📚 Data Source Audit · แยกข้อมูลหลัก/เสริมและสถานะ", expanded=False):
        audit_rows = ([{"ประเภท": "หลัก", "หลักฐาน": name,
                       "สถานะ": "พร้อม" if ready else "ไม่พร้อม/ข้อมูลเก่า"}
                      for name, ready in required_sources.items()]
                      + [{"ประเภท": "เสริม", "หลักฐาน": name,
                          "สถานะ": "พร้อม" if ready else "ไม่มี/ไม่บังคับ"}
                         for name, ready in optional_sources.items()])
        st.dataframe(pd.DataFrame(audit_rows), hide_index=True, width="stretch")
        st.caption("แหล่งข้อมูลและขอบเขตตลาดแสดงในแต่ละส่วนด้านล่าง · ไม่มีข้อมูล Liquidation Heatmap/Whale Identity/Token Unlock อัตโนมัติครบทุกเหรียญ")
    st.caption("Smart Money Footprint (ไม่ระบุตัวตนเจ้ามือ): Binance Order Book/Spread/Aggressor Trades + Taker Buy Volume จากแท่งที่ปิดแล้ว + BTC Market Regime")
    if micro is not None:
        impact_text = f"{micro.ask_impact_bps:.1f}" if micro.ask_impact_bps is not None else "ไม่พร้อม"
        st.caption(f"Order Book {micro.source}: Spread {micro.spread_bps:.1f} bps · "
                   f"Bid Share {micro.near_bid_share*100:.1f}% · Aggressive Buy {micro.aggressor_buy_share*100:.1f}% · "
                   f"Impact ของมูลค่าซื้อจำลอง {impact_text} bps "
                   f"· เทรดล่าสุด {micro.last_trade_at.astimezone(BKK):%d/%m %H:%M:%S} น. (เวลาไทย)")
    elif micro_error:
        st.warning(f"Spot Order Book / Aggressor Trades ไม่พร้อม: {micro_error} — ไม่ยืนยัน MTF READY")
    if btc_context is not None:
        st.caption(f"BTC Regime: 4h {btc_context.trend_4h:+d} / 1d {btc_context.trend_1d:+d} "
                   "(+1 ขาขึ้น, 0 ไม่ชัด, -1 ขาลง) · ที่มา Binance BTCUSDT Spot")
    elif btc_error:
        st.caption(f"BTC Regime ไม่พร้อม: {btc_error}")
    if "15m" in reports and "1h" in reports:
        fast_flow = reports["15m"].taker_buy_share20
        hour_flow = reports["1h"].taker_buy_share20
        st.caption(f"Taker Buy Volume (แท่งปิด 20 แท่ง): 15m {fast_flow*100:.1f}% "
                   f"· 1h {hour_flow*100:.1f}% · เป็นตัวแทนแรงซื้อเชิงรุก ไม่ใช่ข้อมูลตัวตนผู้ถือรายใหญ่")

    with st.expander("🔬 Professional Evidence Desk · CVD / VWAP / Volume Profile / Cross-exchange / Macro",
                     expanded=False):
        st.caption("**ข้อมูลทั้งหมดเป็นหลักฐานประกอบ**: ไม่ใช่สัญญาณเจ้ามือตัวจริง และคะแนนใด ๆ ไม่ใช่โอกาสทำกำไร")
        for tf in ("15m", "1h"):
            if tf in spot_evidence:
                ev = spot_evidence[tf]
                st.markdown(f"**Order Flow {tf} — {ev.source}**")
                for detail in interpret_spot_evidence(ev):
                    st.write("• " + detail)
                if ev.candle_volume_poc is not None:
                    st.caption(f"Candle POC โดยประมาณ: {format_price(ev.candle_volume_poc)} {selected['quote']}")
            else:
                st.warning(f"หลักฐาน CVD/VWAP {tf} ไม่พร้อม; ไม่มีค่าแทน")
        st.divider()
        st.markdown("**Cross-exchange: Bybit (แยก Spot กับ USDT Linear Futures)**")
        if bybit_context is None:
            st.caption(f"ไม่พร้อม/ไม่รองรับ: {bybit_error or 'ไม่พบข้อมูล'} · ไม่ใช้ค่าทดแทนจาก Binance")
        else:
            for status_line in bybit_context.source_status:
                st.caption(status_line)
            if bybit_context.spot_mid is not None:
                st.write(f"• Spot Mid: {format_price(bybit_context.spot_mid)} {selected['quote']}"
                         + (f" · Bid Share {bybit_context.spot_bid_depth_share*100:.1f}%"
                            if bybit_context.spot_bid_depth_share is not None else ""))
            if bybit_context.spot_aggressor_buy_share is not None:
                st.write(f"• Spot Buy (60 trades ล่าสุดสูงสุด): {bybit_context.spot_aggressor_buy_share*100:.1f}%")
            if bybit_context.futures_oi_change_24h_pct is not None:
                st.write(f"• Linear OI Change 24h: {bybit_context.futures_oi_change_24h_pct:+.2f}%"
                         " · สัญญา Bybit เท่านั้น ไม่รวมกับ OI Kraken/Binance")
            if bybit_context.futures_funding_rate_pct is not None:
                st.write(f"• Linear Funding: {bybit_context.futures_funding_rate_pct:+.4f}%")
        st.divider()
        st.markdown("**Macro Liquidity — DefiLlama Free (ภาพรวมตลาด ไม่ใช่กระเป๋า Whale)**")
        if macro_context is None:
            st.caption(f"ข้อมูลไม่พร้อม: {macro_error or 'ไม่มีข้อมูล'}")
        else:
            if macro_context.stablecoin_supply_usd is not None:
                st.write(f"• USD-pegged Stablecoins (มูลค่า USD): {macro_context.stablecoin_supply_usd:,.0f}"
                         + (f" · 7d {macro_context.stablecoin_change_7d_pct:+.2f}%"
                            if macro_context.stablecoin_change_7d_pct is not None else ""))
            else:
                st.caption("Stablecoin circulation ไม่พร้อม/เก่า ไม่อนุมานเงินไหลเข้า Exchange")
            if macro_context.defi_tvl_usd is not None:
                st.write(f"• DeFi TVL: {macro_context.defi_tvl_usd:,.0f} USD"
                         + (f" · 7d {macro_context.defi_tvl_change_7d_pct:+.2f}%"
                            if macro_context.defi_tvl_change_7d_pct is not None else ""))
            else:
                st.caption("DeFi TVL ไม่พร้อม/เก่า; การเปลี่ยน TVL รวมผลราคาสินทรัพย์ด้วย")
        st.caption("ปฏิทินข่าวสำคัญ: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm "
                   "· ยังไม่มีการยืนยันข่าว Token Unlock/ETF Flow รายเหรียญอัตโนมัติ")
    st.divider()
    if verdict.status == "READY":
        st.success("🟢 MTF สด: BUY · ENTRY READY — เฉพาะแผน MTF สด; "
                   "ถ้ามีแผนล็อกให้ตรวจ Trigger ในกรอบ 🧷 ด้านล่างแยกต่างหาก")
    elif verdict.signal == "BUY":
        st.warning("🟡 MTF BUY BIAS · WAIT FOR ENTRY — ทิศทางหลายกรอบสนับสนุน แต่ยังไม่ถึงจังหวะซื้อ")
    else:
        st.warning("🟡 MTF SIGNAL: WAIT — ยังไม่ผ่านเงื่อนไขการซื้อรวมทุกกรอบ")

    if verdict.alignment_index is not None:
        st.metric("คะแนนสอดคล้องของ 4 Timeframe (ไม่ใช่โอกาสกำไร)",
                  f"{verdict.alignment_index:.1f}/100")
        st.progress(verdict.alignment_index / 100)
        st.caption("เกณฑ์ทดลองอย่างน้อย 70/100 · คะแนนรวมถูกทำให้เทียบกันได้ก่อนถ่วงน้ำหนัก ไม่ใช่อัตราชนะหรือความแม่นยำของการพยากรณ์")
    else:
        st.error("ข้อมูลไม่ครบทั้ง 4 กรอบ จึงไม่คำนวณคะแนน MTF และไม่ให้สัญญาณ BUY")

    plan = verdict.entry
    render_watch_panel(symbol, frozen_watch, plan, frame_bars.get("15m"),
                       spot_quote, verdict.signal, live_mtf_ready=verdict.status == "READY",
                       context_ready=(derivatives is not None and micro is not None
                                      and btc_context is not None and btc_context.clean
                                      and verdict.alignment_index is not None
                                      and all(check.passed for check in extra[:2])))
    st.divider()
    st.subheader("🎯 แผน MTF สด (คำนวณใหม่ตามแท่ง 1h — ไม่ใช่แผนที่ล็อกไว้)")
    if risk_audit.rr_tp2 is not None:
        st.caption(f"ตรวจ R:R หลัง fee/slippage จำลอง: TP1 {risk_audit.rr_tp1:.2f}R "
                   f"· TP2 {risk_audit.rr_tp2:.2f}R · ผ่านเกณฑ์อย่างน้อย {min_rr:.2f}R จึงมีสิทธิ์ READY")
    if plan is not None and plan.entry_low is not None:
        st.markdown(f"**Entry Zone ({selected['quote']}): `{format_price(plan.entry_low)}` – `{format_price(plan.entry_high)}`**")
        cols = st.columns(2)
        cols[0].metric("Stop Loss", format_price(plan.stop_loss))
        cols[1].metric("Take Profit 1 · 1.5R", format_price(plan.take_profit_1))
        cols = st.columns(2)
        cols[0].metric("Take Profit 2 · 2.5R", format_price(plan.take_profit_2))
        cols[1].metric("สถานะเข้า", "READY" if verdict.status == "READY" else "WAIT")
        st.caption(f"แนวรับที่ใช้อ้างอิง: {plan.anchor_name} {format_price(plan.anchor_price)} {selected['quote']} · โซนกว้าง ±0.30 ATR จากแท่ง 1h ที่ปิดแล้ว")
        if plan.expires_at is not None:
            st.caption(f"แผนสดหมดอายุ {plan.expires_at.astimezone(BKK):%d/%m %H:%M} น. "
                       "(รีเฟรชแล้วคำนวณใหม่; หากต้องการเฝ้าดูราคาเดิมให้ใช้ 🧷 ล็อกแผนด้านบน)")
        if verdict.status != "READY":
            st.info("โซนนี้มีไว้เฝ้ารอเท่านั้น **อย่าซื้อเพียงเพราะราคาเข้าโซน** จนกว่ากฎ MTF จะผ่านและตรวจราคาเสนอขายจริง")
    else:
        # Watch-only levels must not be promoted to the approved MTF entry plan.
        projected = indicative_zone(frame_bars["1h"]) if "1h" in frame_bars else None
        if projected is not None:
            st.info("🧭 **แผนราคาเฝ้าดูจากกรอบ 1h — ยังเข้าไม่ได้** · "
                    "เป็นสถานการณ์คาดการณ์จากแนวรับและ ATR ไม่ใช่สัญญาณ BUY")
            st.markdown(f"**รอราคาเข้าโซน ({selected['quote']}): "
                        f"{format_price(projected.low)} – {format_price(projected.high)}**")
            cols = st.columns(2)
            cols[0].metric("จุดยกเลิกสมมติฐาน", format_price(projected.invalidation))
            cols[1].metric("เป้าหมายจำลอง 1", format_price(projected.target_1))
            st.metric("เป้าหมายจำลอง 2", format_price(projected.target_2))
            st.caption("เมื่อราคาเข้าโซนต้องตรวจเงื่อนไข MTF และความเสี่ยงอีกครั้ง · "
                       "ถ้าไม่ผ่านยังเป็น WAIT; ระดับราคาจะคำนวณใหม่ตามแท่งที่ปิดแล้ว")
        else:
            st.warning("ข้อมูลแท่ง 1h ไม่พอสร้างโซนที่ตรวจสอบได้ · ไม่เดาราคาโดยไม่มีข้อมูล")

    times = []
    if verdict.next_15m_close is not None:
        times.append(f"ตรวจแท่ง 15m ถัดไป: {verdict.next_15m_close.astimezone(BKK):%d/%m %H:%M} น.")
    if verdict.next_1h_close is not None:
        times.append(f"ตรวจแท่ง 1h ถัดไป: {verdict.next_1h_close.astimezone(BKK):%d/%m %H:%M} น.")
    if times:
        st.caption(" · ".join(times) + " (เวลาไทย · ถ้าล็อกแผนไว้ ระบบจะรีเฟรชทุก 3 นาทีเมื่อหน้าเว็บเปิดอยู่)")

    with st.expander(f"🔎 ทำไม MTF ยังรอ? ดูเงื่อนไขรวม ({sum(c.passed is True for c in verdict.checks)} ผ่าน / {sum(c.passed is False for c in verdict.checks)} ไม่ผ่าน)",
                     expanded=verdict.status != "READY"):
        for check in verdict.checks:
            st.write(f"{'✅' if check.passed else '❌'} **{check.label}** — {check.detail}")
        if data_errors:
            for tf, err in data_errors.items():
                st.caption(f"ข้อมูล {tf} ไม่พร้อม: {err}")
        if snapshot is not None:
            for tf in ("15m", "1h"):
                if tf in reports and reports[tf].coinglass_blockers:
                    for blocker in reports[tf].coinglass_blockers:
                        st.warning(f"CoinGlass ({tf}): {blocker}")

    st.caption("Orbit v4.3 ใช้กฎ Spot v4.2: Rally Escape เป็นเพียงการเตือนราคาวิ่งหนี ไม่ใช่ BUY · Frozen Trigger ยังไม่ผ่าน Full Walk-forward · Telegram แยกที่ GitHub Actions · ไม่ส่งออเดอร์")
    st.divider()
    st.subheader("📝 บันทึกสัญญาณสำหรับติดตามผลจริง (Paper Journal)")
    if st.button("💾 บันทึกสัญญาณ MTF นี้ไว้ตรวจภายหลัง", width="stretch"):
        st.session_state.setdefault("orbit_paper_journal", [])
        st.session_state["orbit_paper_journal"].append({
            "observed_at_th": datetime.now(BKK).strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol, "mtf_signal": verdict.signal, "entry_status": verdict.status,
            "alignment_index_not_probability": verdict.alignment_index,
            "spot_last_quote": spot_quote, "entry_low": plan.entry_low if plan else None,
            "entry_high": plan.entry_high if plan else None,
            "stop_loss": plan.stop_loss if plan else None,
            "tp1": plan.take_profit_1 if plan else None,
            "tp2": plan.take_profit_2 if plan else None,
            "futures_source": derivatives.source if derivatives else "MISSING",
            "coinglass_status": "NOT_ENTERED" if snapshot is None else
                ",".join(r.coinglass_status for r in reports.values()),
            "spot_spread_bps": micro.spread_bps if micro else None,
            "aggressor_buy_share": micro.aggressor_buy_share if micro else None,
            "btc_4h_trend": btc_context.trend_4h if btc_context else None,
            "btc_1d_trend": btc_context.trend_1d if btc_context else None,
            "modeled_net_rr_tp2": risk_audit.rr_tp2,
            "fee_pct_per_side": fee_pct,
            "slippage_pct_per_side": slip_pct,
            "bybit_oi_24h_pct": bybit_context.futures_oi_change_24h_pct if bybit_context else None,
            "bybit_spot_aggressor_buy_share": bybit_context.spot_aggressor_buy_share if bybit_context else None,
            "spot_flow_delta_1h": spot_evidence["1h"].delta_share20 if "1h" in spot_evidence else None,
            "macro_stablecoin_7d_pct": macro_context.stablecoin_change_7d_pct if macro_context else None,
        })
        st.success("บันทึกสถานะแล้วในเซสชันนี้ (ยังไม่ใช่ดีลซื้อขายหรือผลกำไร)")
    journal = st.session_state.get("orbit_paper_journal", [])
    with st.expander("นำเข้า Paper Journal เดิมจากไฟล์ CSV (ไม่เก็บข้อมูลบนเซิร์ฟเวอร์ถาวร)"):
        uploaded_journal = st.file_uploader("เลือกไฟล์ Orbit_Paper_Signal_Journal.csv", type=["csv"], key="import_orbit_journal")
        if uploaded_journal is not None and st.button("นำเข้าบันทึก CSV"):
            try:
                restored = import_signal_journal(uploaded_journal.getvalue())
                journal = combine_journal(journal, restored)
                st.session_state["orbit_paper_journal"] = journal
                st.success(f"นำเข้าแล้ว รวม {len(journal)} รายการ")
            except ValueError as exc:
                st.error(f"นำเข้าไม่ได้: {exc}")
    if journal:
        st.caption(f"บันทึกแล้ว {len(journal)} รายการ · ข้อมูลนี้อยู่เฉพาะเซสชันเว็บ ควรดาวน์โหลด CSV เก็บเอง")
        st.download_button("ดาวน์โหลด Paper Journal CSV",
                           export_signal_journal(journal),
                           file_name="Orbit_Paper_Signal_Journal.csv", mime="text/csv")
        if st.button("🔎 ตรวจผลย้อนหลังเชิงสมมติของ READY Signal สำหรับเหรียญนี้"):
            try:
                hour_history = (frame_bars["1h"] if "1h" in frame_bars
                                else get_candles(symbol, "1h", history_size))
                outcomes = evaluate_recorded_signals(journal, hour_history, symbol)
                st.session_state["orbit_signal_outcomes"] = (symbol, outcomes)
            except (PublicDataError, ValueError, TypeError, KeyError) as exc:
                st.error(f"ไม่สามารถตรวจผลย้อนหลังได้: {exc}")
        saved_outcomes = st.session_state.get("orbit_signal_outcomes")
        if saved_outcomes is not None and saved_outcomes[0] == symbol:
            results = saved_outcomes[1]
            st.caption("**ผลสมมติเท่านั้น**: ต้องเป็น READY และราคาเปิดแท่ง 1h ถัดไปยังอยู่ในโซน; "
                       "ถือว่า Stop เกิดก่อน TP2 หากแท่งเดียวแตะทั้งคู่; ไม่มีการแบ่งขาย TP1 "
                       "หรือข้อมูล Fill จริง · ตรวจย้อนหลังสูงสุด 48 แท่ง")
            if results.empty:
                st.info("ยังไม่มี READY ที่บันทึกไว้สำหรับเหรียญนี้")
            else:
                filled = results[results["status"].isin(["HYPOTHETICAL_STOP", "HYPOTHETICAL_TP2"])]
                st.caption(f"ผลที่ลงเอยด้วย Stop/TP2 ได้: {len(filled)} รายการจาก {len(results)} READY ที่ตรวจ "
                           "· ไม่ใช่สถิติการเทรดจริง")
                if len(filled) < 30:
                    st.warning("ตัวอย่างสมมติน้อยกว่า 30 รายการ ห้ามอ้างว่าเป็น Win Rate ที่น่าเชื่อถือ")
                st.dataframe(results.sort_values("observed_at_th", ascending=False),
                             hide_index=True, width="stretch")
    return

with tabs[1]:
    bars_day = max(1, 1440 // TIMEFRAMES[timeframe])
    price_change24 = (base["close"].iloc[-1] / base["close"].iloc[-1 - bars_day] - 1) * 100
    max_age = {"15m": 1, "1h": 2, "4h": 4, "1d": 24}[timeframe]
    raw = str(analyzed["signal"].iloc[-1])
    st.subheader("ข้อมูลอนุพันธ์อัตโนมัติ — Kraken / Binance / Bybit")
    st.caption("คู่ Spot USDT · ลอง Kraken ก่อน จากนั้น Binance และ Bybit · Futures อาจเป็นสัญญา USD คนละตลาดกับ Spot · ไม่ใช่ CoinGlass")
    derivatives = None
    derivatives_error = None
    try:
        derivatives = get_derivatives(symbol)
    except (DerivativesDataError, ValueError, KeyError, TypeError) as exc:
        derivatives_error = str(exc)
    auto = evaluate_derivatives(raw, derivatives, float(price_change24))
    if derivatives is None:
        st.warning(f"ข้อมูล Futures ไม่พร้อม: {derivatives_error or 'ไม่มีข้อมูล'} — Auto Signal = WAIT")
    else:
        f_cols = st.columns(2)
        f_cols[0].metric("Funding ล่าสุด" + (" (%)" if derivatives.funding_unit == "percent" else " (raw)"),
                         format_signed_price(derivatives.funding_rate_pct) + ("%" if derivatives.funding_unit == "percent" else ""))
        f_cols[1].metric("OI เปลี่ยน 24 ชม.", f"{derivatives.oi_change_24h_pct:+.2f}%")
        f_cols[0].metric("Long/Short Accounts", f"{derivatives.long_short_account_ratio:.3f}")
        f_cols[1].metric(f"OI ล่าสุด ({derivatives.oi_unit})", f"{derivatives.oi_notional_usdt:,.0f}")
        st.caption(f"ที่มา: {derivatives.source} · Funding {derivatives.funding_at.astimezone(BKK):%d/%m %H:%M} · OI {derivatives.oi_at.astimezone(BKK):%d/%m %H:%M} · L/S {derivatives.ratio_at.astimezone(BKK):%d/%m %H:%M} (เวลาไทย)")
        st.info("OI Change 24h ของ Binance ใช้มูลค่า OI, ส่วน Bybit/Kraken ใช้ปริมาณสัญญา; เปรียบเทียบข้ามแหล่งตรง ๆ ไม่ได้ · Funding Kraken แสดงค่า raw เพื่อทราบ แต่ไม่ใช้เป็นเกณฑ์ crowding เพราะหน่วยไม่เทียบเท่า · ไม่มี Liquidations รวม CoinGlass")
    st.caption(f"Auto Signal (ทดลอง): **{auto['signal']}** · {auto['status']} · ยังไม่ได้ Backtest กฎ Futures ร่วมกับกลยุทธ์")
    for reason in auto["reasons"]:
        st.write("• " + reason)
    st.divider()
    st.markdown(f"**CoinGlass เป็นตัวกรองเสริม (เลือกใช้ได้)** · [เปิด CoinGlass สำหรับ {selected['base']}](https://www.coinglass.com/currencies/{selected['base']}/futures)")
    snapshot = coin_glass_panel(selected["base"])
    cg = confirm_signal(raw, snapshot, selected["base"], float(price_change24),
                        now=datetime.now(timezone.utc), max_age_hours=max_age)
    final_signal = auto["signal"]
    if snapshot is not None and cg["signal"] != raw:
        final_signal = "WAIT"  # An explicitly entered CoinGlass caution/invalid result vetoes.
    if price_stale or gaps:
        final_signal = "WAIT"
    colors = {"BUY": "🟢", "SELL": "🔴", "WAIT": "🟡"}
    futures_provider = f"{derivatives.provider} Futures" if derivatives is not None else "Public Futures"
    st.subheader(f"{colors[final_signal]} Final Signal: {final_signal}")
    st.caption(f"Technical: {raw} · {futures_provider}: {auto['status']} · CoinGlass: {cg['status'] if snapshot else 'ไม่ได้กรอก (เสริม)'}")
    if snapshot is not None and cg["blocking_reasons"]:
        st.warning("CoinGlass ไม่ผ่านเกณฑ์ จึงคง Final Signal เป็น WAIT (เกณฑ์ป้องกันความเสี่ยงเชิงทดลอง)")
        for blocker in cg["blocking_reasons"]:
            st.write("⚠️ " + blocker)
    if auto["signal"] == "WAIT" and raw != "WAIT":
        st.info("Auto Futures ไม่ผ่าน: " + "; ".join(auto["reasons"]))
    if final_signal != "WAIT":
        st.warning("สัญญาณนี้อาศัย Spot + Futures จากแหล่งที่ระบุ หากไม่มี CoinGlass จะยังไม่ใช่สัญญาณที่ CoinGlass ยืนยัน และยังไม่มีสถิติทดสอบกฎอนุพันธ์ร่วม")
    # Two metrics per row are legible on narrow mobile viewports.
    last = analyzed.iloc[-1]
    spot_quote = None
    spot_quote_time = None
    try:
        spot_quote, spot_quote_time = get_spot_quote(symbol)
    except PublicDataError as exc:
        st.caption(f"ราคา Spot ล่าสุดไม่พร้อม: {exc} — จะไม่แสดงสถานะ READY")
    entry_plan = plan_entry(
        last, timeframe, final_signal, last_closed_at.to_pydatetime(),
        capital=capital, risk_pct=risk_pct, max_allocation_pct=allocation,
        fee_pct=fee_pct, slippage_pct=slip_pct,
        data_ok=not (bool(gaps) or price_stale),
        current_price=spot_quote,
    )
    st.subheader("🎯 Entry Zone · SL · TP1 · TP2 (Spot Long)")
    status_text = {
        "READY": "🟢 เงื่อนไขซื้อผ่านบนแท่งที่ปิดแล้ว (ตรวจราคาจริงอีกครั้ง)",
        "WAIT_RETEST": "🟡 WAIT FOR ENTRY — รอราคาย่อลงเข้าโซน",
        "WAIT_RECLAIM": "🟡 WAIT — รอราคากลับเข้าโซน",
        "WAIT_CONFIRMATION": "🟡 WAIT — อยู่ในโซนแต่ยังไม่ผ่านตัวกรอง",
        "WAIT_LIVE_QUOTE": "🟡 WAIT — ไม่มีราคา Spot ล่าสุดที่ตรวจสอบได้",
        "INVALID": "🔴 SETUP INVALID — ยังไม่ควรสร้างแผนซื้อ",
        "NO_SETUP": "⚪ NO VALID SETUP — ยังไม่มีโซนเข้าซื้อที่เชื่อถือได้",
    }
    st.markdown("**" + status_text[entry_plan.status] + "**")
    st.write(entry_plan.reason)
    if spot_quote is not None:
        st.caption(
            f"ราคา Spot ล่าสุดที่ร้องขอจาก Binance: {format_price(spot_quote)} {selected['quote']} "
            f"· ขอข้อมูลเมื่อ {spot_quote_time.astimezone(BKK):%d/%m %H:%M:%S} น. "
            "(แหล่งนี้ไม่ระบุเวลาเทรดล่าสุด; ไม่ใช่ราคาเสนอซื้อ/ขายจริงและไม่ได้อัปเดตเองทุกวินาที)"
        )
    if entry_plan.entry_low is not None:
        st.markdown(
            f"**ช่วงเฝ้ารอเข้าซื้อ ({selected['quote']}):** "
            f"`{format_price(entry_plan.entry_low)}` – `{format_price(entry_plan.entry_high)}`"
        )
        cols = st.columns(2)
        cols[0].metric("Stop Loss", format_price(entry_plan.stop_loss))
        cols[1].metric("Take Profit 1 (1.5R)", format_price(entry_plan.take_profit_1))
        cols = st.columns(2)
        cols[0].metric("Take Profit 2 (2.5R)", format_price(entry_plan.take_profit_2))
        cols[1].metric("ขนาดสถานะ (เหรียญ)", format_price(entry_plan.position_qty))
        st.caption(f"อ้างอิง: {entry_plan.anchor_name} {format_price(entry_plan.anchor_price)} {selected['quote']} · โซนกว้าง ±0.30 ATR")
        st.caption(
            f"เงื่อนไขเข้า: ต้องมีแท่ง {timeframe} ปิดใน Entry Zone เหนือแนวรับอ้างอิงเป็นแท่งเขียว "
            "มี Volume ≥ 0.75×, Final BUY และราคา Spot ที่ร้องขอล่าสุดอยู่ในโซน; ตรวจคำเสนอขายจริง ณ เวลาจะซื้ออีกครั้ง"
        )
        st.caption(
            f"แท่งอ้างอิงปิด {entry_plan.last_closed_at.astimezone(BKK):%d/%m/%Y %H:%M} น. · "
            f"ตรวจแท่งถัดไป {entry_plan.next_check_at.astimezone(BKK):%d/%m %H:%M} น. · "
            f"แผนเดิมหมดอายุ {entry_plan.expires_at.astimezone(BKK):%d/%m %H:%M} น. (เวลาไทย; รีเฟรชจะคำนวณใหม่)"
        )
        st.caption(
            f"ความเสี่ยงจำลองไม่เกิน {entry_plan.risk_budget:,.2f} {selected['quote']} "
            f"· ความเสี่ยงคำนวณ {entry_plan.estimated_risk:,.2f} {selected['quote']} "
            f"· มูลค่าซื้อสูงสุดเชิงตัวอย่าง {entry_plan.notional:,.2f} {selected['quote']} "
            "(ใช้ราคาขอบบนของโซนและรวม fee/slippage ตามที่ตั้ง; ไม่รวมช่องว่างราคาหรือสภาพคล่องจริง)"
        )
    st.info("Entry Zone เป็นแผนเฝ้ารอจากข้อมูลแท่งที่ปิดแล้ว ไม่ใช่คำสั่งซื้อ; เมื่อ Final Signal = WAIT/SELL ห้ามตีความโซนเป็น BUY ที่ยืนยันแล้ว · กฎนี้ยังไม่ผ่าน Backtest/Walk-forward รวม")
    st.divider()
    metrics = [("ราคาปิด", format_price(float(last["close"]))),
               ("Technical Score", f"{int(last['score']):+d}/{7 if timeframe == '1d' else 9}"),
               ("RSI", f"{float(last['rsi']):.1f}"),
               ("ADX", f"{float(last['adx']):.1f}"),
               ("Volume Ratio", f"{float(last['volume_ratio']):.2f}×")]
    for offset in range(0, len(metrics), 2):
        cols = st.columns(2)
        for col, (name, value) in zip(cols, metrics[offset:offset + 2]):
            col.metric(name, value)
    st.plotly_chart(plot_prices(analyzed, symbol, timeframe, entry_plan), width="stretch")
    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("หลักฐานจากกราฟ")
        for line in latest_reasons(last, timeframe):
            st.write("• " + line)
        st.subheader("CoinGlass")
        for line in cg["reasons"]:
            st.write("• " + line)
        st.caption("CoinGlass เป็นตัวกรองเสริม: เมื่อกรอกแล้วไม่ผ่านหรือข้อมูลไม่ถูกต้องจะเปลี่ยนผลเป็น WAIT; หากไม่กรอกจะใช้ผลจาก Futures สาธารณะเท่านั้น")
    with right:
        st.subheader("Market Structure & Risk")
        st.write("Pivot High:", format_price(float(last["pivot_high"])) if pd.notna(last["pivot_high"]) else "ไม่พร้อม")
        st.write("Pivot Low:", format_price(float(last["pivot_low"])) if pd.notna(last["pivot_low"]) else "ไม่พร้อม")
        st.write("ATR(14):", format_price(float(last["atr"])))
        st.caption("แผน Entry Zone/SL/TP อยู่ด้านบน และจะเปลี่ยนตามราคา/Timeframe ที่เลือก; SELL สำหรับ Spot หมายถึงขาย/ลดเหรียญที่ถือ ไม่ใช่เปิด Short")
    st.warning("โปรแกรมนี้ไม่ส่งคำสั่งซื้อขาย และไม่รับประกันกำไร ราคาในกระดานที่ผู้ใช้เทรดจริงอาจต่างจากแหล่งข้อมูล")

with tabs[0]:
    render_multi_timeframe_dashboard()

with tabs[2]:
    st.subheader("Technical Strategy Backtest — ไม่รวม Futures และ CoinGlass")
    st.caption("จำลอง Spot ฝั่ง Long เท่านั้น · สัญญาณหลังแท่งปิด / เข้าแท่งถัดไป · Stop สำคัญกว่า Target ในแท่งเดียวกัน · รวมค่าธรรมเนียมและ Slippage")
    if gaps:
        st.error("ข้อมูลมีช่องว่าง จึงไม่สามารถรับรองคุณภาพการจำลองได้")
    else:
        result = simulate(features, config)
        s = result["stats"]
        metric_values = [("Return", f"{s['return_pct']:+.2f}%"),
                                            ("Win Rate", f"{s['win_rate_pct']:.1f}%"),
                                            ("Trades", str(s["trades"])),
                                            ("Profit Factor", "∞" if s["profit_factor"] == float("inf") else
                                             f"{s['profit_factor']:.2f}" if s["profit_factor"] is not None else "N/A"),
                                            ("Max Drawdown", f"{s['max_drawdown_pct']:.2f}%")]
        for offset in range(0, len(metric_values), 2):
            columns = st.columns(2)
            for col, (label, val) in zip(columns, metric_values[offset:offset + 2]):
                col.metric(label, val)
        st.caption(f"Buy & Hold ในช่วงเดียวกัน: {s['benchmark_pct']:+.2f}% · ผลย้อนหลังไม่ยืนยันผลในอนาคต")
        if s["trades"] < 30:
            st.warning("จำนวนการเทรดยังน้อยมาก ไม่เพียงพอสำหรับสรุปความน่าเชื่อถือ")
        st.line_chart(result["equity"], height=240)
        if not result["trades"].empty:
            st.dataframe(result["trades"].sort_values("exit_time", ascending=False), width="stretch")
            st.download_button("ดาวน์โหลด Trade Log CSV", result["trades"].to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"Orbit_Trade_Log_{symbol}_{timeframe}.csv", mime="text/csv")
        else:
            st.info("ยังไม่มีดีลที่เข้าเงื่อนไขในช่วงข้อมูลนี้")

with tabs[3]:
    st.subheader("Rolling Walk-forward — ไม่รวม Futures และ CoinGlass")
    st.write("แต่ละรอบเลือกเกณฑ์คะแนนจากข้อมูลฝึกเท่านั้น จากนั้นทดสอบบนช่วงเวลาถัดไปซึ่งไม่ได้ใช้ปรับเกณฑ์")
    if gaps:
        st.error("ไม่รัน Walk-forward เพราะประวัติราคามีช่องว่าง")
    else:
        wf = walk_forward(features, config)
        if wf["status"] == "INSUFFICIENT":
            st.warning(wf["reason"])
        else:
            data = pd.DataFrame(wf["folds"])
            st.dataframe(data, width="stretch")
            if int(data["trades"].sum()) < 30:
                st.warning("สัญญาณ Out-of-sample รวมยังน้อยกว่า 30 ดีล ผลยังไม่เพียงพอต่อการประเมินความน่าเชื่อถือ")
            st.caption("แต่ละช่วงเริ่มต้นด้วยทุนจำลองเท่ากัน ผลตอบแทนแต่ละช่วงไม่ควรบวกตรง ๆ แทนพอร์ตต่อเนื่อง")

with tabs[4]:
    st.subheader("📈 MTF Historical Research — เฉพาะข้อมูล Spot ที่ย้อนหลังได้")
    st.warning(
        "นี่เป็นการทดสอบ **ส่วนย่อยของ MTF**: กราฟ 15m/1h/4h/1d + Taker Buy Volume "
        "+ Entry จากแท่ง 1h ที่ปิดแล้ว · ไม่รวม Order Book, aggTrades, BTC regime, "
        "Kraken/Binance/Bybit Futures, DefiLlama, CoinGlass หรือ Frozen Watch Trigger ย้อนหลัง จึง **ไม่ใช่ Backtest ของ Full v4.1**"
    )
    st.caption("เข้าเทรดได้เร็วสุดที่ราคาเปิดแท่ง 1h ถัดไป และต้องยังอยู่ในโซนที่คำนวณจากแท่งก่อน · รวม fee/slippage จำลอง · TP2 เท่านั้น ไม่มีการแบ่งขาย TP1")
    if st.button("▶️ รันทดสอบ MTF Spot-only + Walk-forward", width="stretch"):
        try:
            with st.spinner("กำลังโหลดประวัติแท่งที่ปิดแล้วและทดสอบแยกช่วง Train/Test..."):
                n_hour = min(2500, max(history_size, 1500))
                research_count = {"15m": min(10000, 4 * n_hour),
                                  "1h": n_hour, "4h": max(1000, n_hour), "1d": 1000}
                history = {tf: get_candles(symbol, tf, n) for tf, n in research_count.items()}
                research_frames = {}
                for tf in TIMEFRAMES:
                    research_frames[tf] = with_signal(prepare_features(
                        history[tf], history[HIGHER_TIMEFRAME[tf]], tf, pivot_bars=pivot_bars))
                trial_features = historical_mtf_features(research_frames, config)
                fixed = run_mtf_backtest(trial_features, config, 70)
                wf_mtf = mtf_walk_forward(trial_features, config)
            s = fixed["stats"]
            st.caption("สัญญาณย้อนหลังใช้คะแนนเกณฑ์ 70 และแยกการเลือกเกณฑ์ Train/Test ของ Walk-forward")
            cols = st.columns(2)
            cols[0].metric("Trades (Spot-only MTF)", str(s["trades"]))
            cols[1].metric("Return", f"{s['return_pct']:+.2f}%")
            cols = st.columns(2)
            cols[0].metric("Win Rate", f"{s['win_rate_pct']:.1f}%")
            cols[1].metric("Max Drawdown", f"{s['max_drawdown_pct']:.2f}%")
            if s["trades"] < 30:
                st.warning("ยังมีดีลน้อยกว่า 30 ครั้ง สรุปความแม่นยำหรือประสิทธิภาพไม่ได้")
            st.line_chart(fixed["equity"], height=220)
            if not fixed["trades"].empty:
                st.download_button("ดาวน์โหลด MTF Research Trades CSV",
                                   fixed["trades"].to_csv(index=False).encode("utf-8-sig"),
                                   file_name=f"Orbit_MTF_Research_{symbol}.csv", mime="text/csv")
            if wf_mtf["status"] == "OK":
                folds = pd.DataFrame(wf_mtf["folds"])
                st.dataframe(folds, width="stretch")
                if not folds["train_qualified"].all() or int(folds["trades"].sum()) < 30:
                    st.warning("จำนวนดีล Train/Test ไม่พอ หรือบางช่วง Train เลือกเกณฑ์ไม่ได้ · ห้ามอ้างว่า MTF ผ่านการพิสูจน์")
            else:
                st.warning(wf_mtf["reason"])
        except (PublicDataError, ValueError, KeyError, IndexError, TypeError) as exc:
            st.error(f"MTF Research ไม่พร้อม: {exc}")
            st.info("บางเหรียญมีประวัติไม่ถึง 250 แท่ง Daily หรือไม่มี Taker Buy Volume; ไม่เติมข้อมูลปลอมเพื่อให้ผลดูดี")

with tabs[5]:
    st.markdown("""
    ### Orbit v4.3 Lab — วิธีใช้ขั้นสูง
    1. เลือกสกุลราคา แล้วพิมพ์รหัสเหรียญ (เช่น `BTC` หรือ `XRP`) ในแถบซ้าย
    2. เปิด **🎯 สัญญาณ MTF รวม** เพื่อวิเคราะห์ 15m+1h+4h+1d, Order Book, Taker Buy, BTC Market Regime, Futures สาธารณะ รวมทั้ง CVD/VWAP, Bybit และ DefiLlama ที่รองรับ แล้วสรุปผล **เป็นชุดเดียว**
    3. อ่าน **คะแนนความสอดคล้องถ่วงน้ำหนัก** (ไม่ใช่โอกาสทำกำไร) พร้อม Entry Zone / SL / TP และ **R:R หลังต้นทุนจำลอง** โดยอิงกรอบ 1h ชุดเดียว
    3.1. หากอยากเฝ้าราคาเดิม ให้กด **🧷 ล็อก Entry Zone ปัจจุบัน** ในหน้า MTF แล้ว **Bookmark/แชร์ URL ที่มี `?watch=`**: แผนเดิมจะไม่เปลี่ยนแม้แผน MTF สดคำนวณใหม่
    3.2. ดูสถานะ **WAIT_ZONE → WAIT_RECLAIM → WAIT_BREAK → READY_NOW**: ต้องมีแท่งปิด 15m ยืนยันหลังแตะโซน และ MTF/R:R สดยังผ่าน; หาก INVALIDATED/EXPIRED/PASSED ไม่ถือเป็นจุดซื้อ
    4. **READY เป็นเกณฑ์ทดลอง** และต้องผ่านทุกข้อ: คลิก **🔎 ทำไม MTF ยังรอ?** เพื่อดูหลักฐาน Spot, Futures และตัวกรองอื่นว่าขาดข้อใด อย่าซื้อจากโซนราคาอย่างเดียว
    5. ตรวจ **📚 Data Source Audit** และ **🔬 Professional Evidence Desk** เพื่อดูข้อมูลที่มาและความครบของแหล่ง (Bybit/DefiLlama อาจไม่รองรับเหรียญหรือเครือข่าย)
    6. เปิด **📊 สัญญาณละเอียด** หากต้องการดูกราฟ/หลักฐานแยกช่วงเวลา หรือกรอก CoinGlass ด้วยมือ ซึ่งเป็นตัวกรองเสริมในผล MTF
    7. เปิดแท็บ **🧪 Backtest** และ **🔁 Walk-forward** เพื่อตรวจสถิติเทคนิคเดิม; กดปุ่มใน **📈 MTF Research** เพื่อทดลองย้อนหลังส่วนย่อย MTF Spot-only ที่มีข้อมูลย้อนหลังจริง
    8. กด **💾 บันทึกสัญญาณ MTF นี้** เพื่อเก็บ Paper Journal และดาวน์โหลด CSV; สามารถนำเข้า CSV กลับมาภายหลัง แต่ยังไม่ใช่ประวัติดีลที่เกิดจริง
    9. กด **🔄 ดึงข้อมูลใหม่** เมื่อต้องการประเมินราคา/แท่งล่าสุดอีกครั้ง; แผนที่ล็อกไว้รีเฟรชหน้าเว็บเองทุกประมาณ 3 นาทีเมื่อเปิดหน้าเว็บอยู่ ไม่ส่ง Push ตอนปิดเว็บ

    ### ข้อจำกัดสำคัญ
    - CoinGlass API ทางการเป็นบริการที่ใช้ API Key และแพ็กเกจชำระเงิน ณ วันที่ตรวจสอบ ดังนั้นโหมดฟรีต้องกรอกค่าด้วยมือ
    - **ไม่สามารถระบุตัวเจ้ามือได้จาก Public API:** Order Book เป็นคำสั่งที่ยกเลิกได้และมีความเสี่ยง Spoofing; `aggTrades` และ Taker Buy Volume เป็นธุรกรรมที่ไม่เปิดเผยตัวผู้ซื้อขาย; Bid Share/Aggressor Buy เป็นเพียงตัวแทนแรงซื้อขาย
    - CVD ที่เพิ่มเป็น CVD จากแท่งปิด 20 แท่ง ขณะที่ VWAP และ Volume POC คำนวณประมาณจาก OHLCV; **ไม่ใช่** Tick-level Footprint หรือ Iceberg detector
    - Bybit ที่เพิ่มเป็นแหล่งข้อมูลแยกสำหรับ Spot และ USDT Linear Futures; ถ้าไม่มี/ถูกบล็อกจะแสดง MISSING แต่ไม่แทนค่าเป็น 0 และไม่ผสม OI จากตลาดอื่น
    - DefiLlama เป็นตัวชี้สภาพคล่องของตลาดโดยรวม ไม่ได้แสดงชื่อ Whale หรือการฝากเหรียญของผู้ถือรายใด
    - เกณฑ์ใหม่ด้าน Order Book, Spread, Slippage Impact, BTC Market Regime และแรงซื้อเป็น **สมมติฐานทดลอง** ไม่ใช่สูตรที่ผ่านการตรวจความแม่นยำหรือรับรองผลกำไร
    - **MTF Research ทดสอบส่วนย่อยบน Spot** ที่มีแท่งปิด, Taker Buy และ Entry 1h แต่ **ไม่ได้รวม Order Book, Aggressor Trades, BTC Regime, Bybit, DefiLlama, Futures, CoinGlass และระบบเฝ้าดูหลังแตะโซน**; ห้ามอ้างว่า Full v4.1 ผ่าน Backtest แล้ว
    - ข้อมูลอนุพันธ์มาจาก Kraken Perpetual USD, Binance USDⓈ-M Futures หรือ Bybit USDT Linear Futures เฉพาะเหรียญที่รองรับ; เป็นข้อมูลตลาดเดียวที่ระบุชัด ไม่ใช่ CoinGlass
    - ไม่ได้รับข้อมูล Liquidations 24h ครบจาก Public API ที่ใช้ จึงไม่ใช้ใน Auto Signal
    - ข้อมูลจาก Binance Spot อาจไม่ตรงกับตลาดที่ผู้ใช้ซื้อขายจริง รวมถึงอาจถูกจำกัดการเข้าถึงบางเครือข่าย/ภูมิภาค
    - ไม่มีการส่งออเดอร์หรือกำหนด Leverage; หน้า Spot ไม่ให้คำสั่ง Short แต่หน้า Futures v4.3 สามารถแสดงสัญญาณ Long/Short แบบอ่านข้อมูลอย่างเดียว; หากต้องการ Telegram ตอนปิดเว็บต้องติดตั้ง GitHub Actions แยก
    - แผนที่ล็อกไว้เก็บใน URL เท่านั้น ไม่มีฐานข้อมูลส่วนตัว; ต้องเก็บลิงก์ `?watch=` ไว้เอง และไม่ต้องกรอก API Key; หากปิดหน้าเว็บไม่มี background polling
    - กฎ Trigger ของ v4.0 เป็น heuristic ใหม่: แท่ง 15m ปิดเหนือโซน + Volume, แล้ว Break/Retest และ MTF ผ่าน ไม่ได้พิสูจน์ว่าจับจุดต่ำสุดหรือทำกำไรได้; การเริ่มเฝ้าดูระหว่างแท่งจะไม่นับแท่งที่ยังไม่ปิดย้อนหลัง
    - Market Structure เป็น Pivot/BOS/Sweep ตามกฎ ไม่ได้ครอบคลุมข่าว, On-chain, Order Book History หรือระบบสถาบันทั้งหมด
    - Walk-forward เทคนิคเดิมทดสอบคะแนน 5/6/7 ส่วน MTF Research เลือกเกณฑ์ 65/70/75 ในช่วงฝึกเท่านั้น; ตัวอย่างอาจน้อยเกินกว่าจะสรุปผล
    - ข้อมูลราคาที่ใช้มีจำนวนจำกัดตามที่เลือก; โปรดดูจำนวนดีลและสภาวะตลาดก่อนสรุปความน่าเชื่อถือ
    """)

with tabs[6]:
    st.subheader("📡 Telegram Monitor — Auto Spot BUY / Futures LONG & SHORT")
    st.info("**ต้องตั้งค่า GitHub Actions และ Telegram เพียงครั้งแรกก่อน** · การเปิดแอปนี้ไม่ได้เปิดตัวตรวจเบื้องหลังให้เอง")
    st.success("✅ **ไม่ต้อง Save หรือ Lock แผนเพื่อสแกนสด** · GitHub Actions สแกน Spot MTF "
               "ทุกเหรียญใน Config อัตโนมัติตามรอบ 15 นาที แม้มีแผนเก่าที่ล็อกไว้ "
               "และ Futures ตรวจ LONG/SHORT แยกต่างหากเมื่อข้อมูลพร้อม")
    st.markdown("""
    1. หากอัปเกรด Monitor อัตโนมัติ ให้อัปโหลด `app.py`, `alert_monitor.py`, `monitor_engine.py`, `monitor_alerts.py` ไปที่ root ของ GitHub เดิม (ไม่ต้องสร้าง Bot หรือ Secrets ใหม่; `monitor_config.json` ของเดิมใช้ต่อได้)
    2. สร้างบอท Telegram ด้วย **@BotFather** แล้วเริ่มแชตกับบอทเพื่ออนุญาตให้ส่งข้อความ
    3. เพิ่ม GitHub **Actions Secrets** `TELEGRAM_BOT_TOKEN` และ `TELEGRAM_CHAT_ID` (ห้ามส่ง Token ในแชตหรือใส่ลงไฟล์ GitHub)
    4. เปิด GitHub **Actions → Orbit Telegram Signal Monitor → Run workflow** เลือก **Send test** เพื่อทดสอบข้อความ
    5. `ORBIT_WATCH_LINKS` เป็น **ตัวเลือกเสริมเท่านั้น**: ถ้ามี ระบบจะตรวจ *ทั้ง MTF สดและแผนล็อก* แยกกัน; ถ้าไม่มี จะตรวจ MTF สดตามปกติ **ไม่ต้อง Save แผนก่อน**
    6. ข้อมูล CoinGlass ต้องกรอกเอง และสามารถนำค่าที่บันทึกไปเติมใน `monitor_coinglass_manual.json` (ถ้าเก่าเกิน 1 ชม. จะเป็นตัวกรองไม่ผ่าน)
    7. หากราคา **พุ่งหนีโซนโดยไม่เคยแตะ** จะมี `BREAKOUT_WATCH` / `MISSED_ENTRY` เฉพาะเมื่อแท่งปิด 15m และ Volume ยืนยัน; `NEW_SETUP_CANDIDATE` ต้องมี MTF สด READY และโซนใหม่ที่ไม่ไล่ราคา (ทั้งหมดไม่ใช่ BUY)

    คู่มือไทยโดยละเอียดอยู่ใน ZIP: **`UPGRADE_V42_TH.md`** และ **`MONITOR_TELEGRAM_SETUP_TH.md`**
    """)
    current_token = st.query_params.get("watch")
    if frozen_watch is not None and current_token and frozen_watch.symbol == symbol:
        base_url = st.context.url
        st.markdown("**คัดลอกบรรทัดนี้ไปใส่ Secret `ORBIT_WATCH_LINKS`:**")
        value = f"{symbol}={base_url}?watch={current_token}" if base_url else f"{symbol}={current_token}"
        st.code(value, language=None, wrap_lines=True)
    else:
        st.info("ยังไม่มีแผนล็อกก็ใช้งาน Auto BUY ได้ · ถ้าต้องการเฝ้าราคาเดิมค่อยล็อกแผนเพิ่มเติม")
    current_snapshot = st.session_state.get("coinglass_snapshot")
    if current_snapshot is not None and current_snapshot.symbol == selected["base"]:
        cg_data = {"snapshots": {current_snapshot.symbol: {
            "observed_at": current_snapshot.observed_at.isoformat(),
            "funding_rate_pct": current_snapshot.funding_rate_pct,
            "oi_change_24h_pct": current_snapshot.oi_change_24h_pct,
            "long_short_account_ratio": current_snapshot.long_short_account_ratio,
            "long_liquidations_usd_24h": current_snapshot.long_liquidations_usd_24h,
            "short_liquidations_usd_24h": current_snapshot.short_liquidations_usd_24h,
        }}}
        st.markdown("**CoinGlass ของเหรียญนี้ (คัดลอกเข้าไฟล์ Manual ที่ GitHub):**")
        st.code(json.dumps(cg_data, ensure_ascii=False, indent=2), language="json", wrap_lines=True)
        st.caption("หากติดตามหลายเหรียญ ให้รวมข้อมูลของแต่ละเหรียญอยู่ใต้ `snapshots` ในไฟล์เดียว ไม่ใช่อัปโหลด JSON หลายไฟล์")
    else:
        st.caption("CoinGlass: ยังไม่มีค่า Manual ที่บันทึกของเหรียญนี้ในเซสชัน · ระบบ Telegram จะระบุ NOT_ENTERED และไม่สมมติค่า")
    st.warning("GitHub Actions อาจรันช้าหรือข้ามรอบตามภาระระบบ; Telegram ไม่ใช่สัญญาณเรียลไทม์ "
               "และการแจ้ง READY เป็นกฎทดลองที่ยังไม่ผ่าน Full Walk-forward · "
               "Futures สำรองจาก Kraken/Bybit ยังเป็น WATCH ONLY เมื่อไม่มีข้อมูล Taker Flow ยืนยัน")


@st.fragment(run_every="180s")
def auto_refresh_locked_watch():
    """Full app rerun while the browser is open, without a paid scheduler."""
    if frozen_watch is None:
        return
    now_seconds = datetime.now(timezone.utc).timestamp()
    last_seconds = st.session_state.setdefault("orbit_watch_last_full_refresh", now_seconds)
    if now_seconds - last_seconds >= 175:
        st.session_state["orbit_watch_last_full_refresh"] = now_seconds
        st.rerun(scope="app")


auto_refresh_locked_watch()
