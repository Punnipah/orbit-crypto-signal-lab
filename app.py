"""Orbit Crypto Signal Lab — mobile-friendly, read-only market dashboard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from backtest_engine import BacktestConfig, simulate, walk_forward
from binance_data import (HIGHER_TIMEFRAME, POPULAR_QUOTES, PublicDataError,
                          TIMEFRAMES, count_time_gaps, fetch_catalog, fetch_klines,
                          fetch_spot_last_price, search_catalog)
from coinglass_overlay import CoinGlassSnapshot, confirm_signal, parse_quick_paste
from display_format import format_price, format_signed_price
from entry_planner import EntryPlan, plan_entry
from public_derivatives import DerivativesDataError, evaluate_derivatives, fetch_with_fallback
from research_engine import latest_reasons, prepare_features, with_signal


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


st.set_page_config(page_title="Orbit Crypto Signal Lab", page_icon="🪐", layout="wide")
st.markdown("""
<style>
/* Keep touch targets and charts readable in mobile Safari and Chrome. */
@media (max-width: 640px) {
  .block-container { padding-top: 0.8rem; padding-left: 0.65rem; padding-right: 0.65rem; }
  h1 { font-size: 1.65rem !important; }
  h2 { font-size: 1.35rem !important; }
  div[data-testid="stMetricValue"] { font-size: 1.32rem; }
  div[data-testid="stMetricLabel"] { font-size: 0.82rem; }
  div[data-testid="stDataFrame"] { max-width: 100%; }
}
</style>
""", unsafe_allow_html=True)
st.title("🪐 Orbit Crypto Signal Lab")
st.caption("v2.5 · Binance Spot + Kraken/Binance/Bybit Futures public · Entry Zone/SL/TP · CoinGlass เสริม · ไม่ส่งออเดอร์ · ไม่มี API Key")
st.info("📱 มือถือ: แตะเมนู **>** มุมซ้ายบนเพื่อค้นหาเหรียญ/ตั้งค่าความเสี่ยง แล้วปิดเมนูเพื่อดูกราฟ · ข้อมูล CoinGlass ที่กรอกจะอยู่เฉพาะในเซสชันนี้")

with st.sidebar:
    st.header("ค้นหาเหรียญ")
    try:
        catalog = get_catalog()
    except PublicDataError as exc:
        st.error(f"ไม่สามารถดึงรายการเหรียญได้: {exc}")
        st.info("ตรวจการเชื่อมต่ออินเทอร์เน็ตและลองใหม่ ภูมิภาคหรือเครือข่ายบางแห่งอาจจำกัด API")
        st.stop()
    quote = st.selectbox("สกุลเงินที่ใช้เทียบ", POPULAR_QUOTES + ["ทั้งหมด"], index=0)
    query = st.text_input("ค้นหารหัสเหรียญ / ชื่อที่รู้จัก", placeholder="เช่น BTC, Bitcoin, XRP, DOGE")
    matches = search_catalog(catalog, query, quote)
    if not matches:
        st.warning("ไม่พบคู่ตลาดที่ค้นหา ลองสกุลเงินที่ใช้เทียบอื่น")
        st.stop()
    labels = {item["symbol"]: f"{item['base']}/{item['quote']} · {item['symbol']}" for item in matches}
    symbols = list(labels)
    default = symbols.index("BTCUSDT") if "BTCUSDT" in symbols else 0
    symbol = st.selectbox("เลือกคู่เหรียญ", symbols, index=default, format_func=lambda s: labels[s])
    selected = next(item for item in matches if item["symbol"] == symbol)
    timeframe = st.selectbox("Timeframe", list(TIMEFRAMES), index=1)
    history_size = st.select_slider("จำนวนแท่งประวัติ", options=[1000, 1500, 3000, 5000, 8000], value=3000)
    pivot_bars = st.slider("ความเข้มงวดของ Pivot", 2, 6, value=3)
    st.divider()
    st.header("จำลองความเสี่ยง")
    capital = st.number_input("ทุนจำลอง (หน่วยสกุลราคา)", value=10000.0, min_value=100.0, step=500.0)
    risk_pct = st.slider("ยอมเสี่ยงต่อดีล (%)", 0.25, 3.0, 1.0, step=0.25)
    allocation = st.slider("สัดส่วนเงินสูงสุดต่อดีล (%)", 5, 100, 30, step=5)
    fee_pct = st.number_input("ค่าธรรมเนียมต่อด้าน (%)", 0.0, 2.0, value=0.1, step=0.05, format="%.2f")
    slip_pct = st.number_input("Slippage ต่อด้าน (%)", 0.0, 2.0, value=0.05, step=0.05, format="%.2f")
    limit_dd = st.slider("หยุดเปิดสถานะเมื่อ Drawdown ถึง (%)", 5, 50, 25, step=5)
    config = BacktestConfig(capital=capital, risk_per_trade_pct=risk_pct, max_allocation_pct=allocation,
                            fee_pct=fee_pct, slippage_pct=slip_pct, max_drawdown_pct=limit_dd)
    if st.button("🔄 ดึงข้อมูลใหม่", width="stretch"):
        get_catalog.clear()
        get_candles.clear()
        get_spot_quote.clear()
        get_derivatives.clear()
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

tabs = st.tabs(["📊 สัญญาณ", "🧪 Backtest", "🔁 Walk-forward", "📖 คู่มือ"])
with tabs[0]:
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
    if price_stale:
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

with tabs[1]:
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

with tabs[2]:
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

with tabs[3]:
    st.markdown("""
    ### วิธีใช้
    1. เลือกสกุลราคา แล้วพิมพ์รหัสเหรียญ (เช่น `BTC` หรือ `XRP`) ในแถบซ้าย
    2. เลือกคู่เหรียญและ Timeframe จากนั้นรอสักครู่ให้ระบบคำนวณข้อมูลราคา
    3. อ่าน **Technical Signal** จาก Spot, **Auto Signal** จาก Kraken/Binance/Bybit Futures (ชื่อผู้ให้ข้อมูลจะแสดงตามจริง) และ **Final Signal** ที่รวมตัวกรองเสริม
    4. เปิดแท็บ **Backtest** และ **Walk-forward** เพื่อตรวจสถิติย้อนหลัง (เฉพาะกลยุทธ์เทคนิค)
    5. CoinGlass เป็นข้อมูลเสริมแบบกรอกเอง; ถ้าไม่กรอกจะใช้ผล Futures แต่หากกรอกแล้วมีข้อเตือน/หมดอายุ จะเป็น `WAIT`
    6. อ่าน **Entry Zone / SL / TP1 / TP2** ใต้ Final Signal: ถ้ายังเป็น WAIT ให้เฝ้ารอ ไม่ใช่คำสั่งซื้อ; ติดตามเวลาปิดแท่งและหมดอายุของแผน

    ### ข้อจำกัดสำคัญ
    - CoinGlass API ทางการเป็นบริการที่ใช้ API Key และแพ็กเกจชำระเงิน ณ วันที่ตรวจสอบ ดังนั้นโหมดฟรีต้องกรอกค่าด้วยมือ
    - ผล Backtest/Walk-forward **ไม่ได้รวม Kraken/Binance/Bybit Futures หรือ CoinGlass** จึงห้ามตีความว่าได้พิสูจน์กลยุทธ์รวมแล้ว
    - **Entry Zone, SL และ TP ของ v2.5 ยังไม่ได้ Backtest/Walk-forward แบบครบกฎ**; เป็น heuristic เฝ้ารอเท่านั้น อาจคลาดเคลื่อนหรือไม่เกิดโซนที่ใช้ได้ในบางตลาด
    - ข้อมูลอนุพันธ์มาจาก Kraken Perpetual USD, Binance USDⓈ-M Futures หรือ Bybit USDT Linear Futures เฉพาะเหรียญที่รองรับ; เป็นข้อมูลตลาดเดียวที่ระบุชัด ไม่ใช่ CoinGlass
    - ไม่ได้รับข้อมูล Liquidations 24h ครบจาก Public API ที่ใช้ จึงไม่ใช้ใน Auto Signal
    - ข้อมูลจาก Binance Spot อาจไม่ตรงกับตลาดที่ผู้ใช้ซื้อขายจริง รวมถึงอาจถูกจำกัดการเข้าถึงบางเครือข่าย/ภูมิภาค
    - ไม่มีการส่งออเดอร์, ไม่มีการใช้ Leverage, ไม่มีการเปิด Short และไม่มีแจ้งเตือน Push ในรุ่นนี้
    - Market Structure เป็น Pivot/BOS/Sweep ตามกฎ ไม่ได้ครอบคลุมข่าว, On-chain, Order Book History หรือระบบสถาบันทั้งหมด
    - Walk-forward เป็นการทดสอบเกณฑ์คะแนน 5/6/7 เฉพาะชุดกฎนี้ และอาจมีตัวอย่างน้อยเกินกว่าจะสรุปผล
    - ข้อมูลราคาที่ใช้มีจำนวนจำกัดตามที่เลือก; โปรดดูจำนวนดีลและสภาวะตลาดก่อนสรุปความน่าเชื่อถือ
    """)
