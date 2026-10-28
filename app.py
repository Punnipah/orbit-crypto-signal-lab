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
                          TIMEFRAMES, count_time_gaps, fetch_catalog, fetch_klines, search_catalog)
from coinglass_overlay import CoinGlassSnapshot, confirm_signal
from public_derivatives import DerivativesDataError, evaluate_derivatives, fetch_with_fallback
from research_engine import latest_reasons, prepare_features, with_signal


BKK = ZoneInfo("Asia/Bangkok")


def money(value: float) -> str:
    return f"{value:,.5f}" if value < 10 else f"{value:,.2f}"


@st.cache_data(ttl=3600, show_spinner=False)
def get_catalog():
    return fetch_catalog()


@st.cache_data(ttl=180, show_spinner=False)
def get_candles(symbol: str, tf: str, n: int):
    return fetch_klines(symbol, tf, n)


@st.cache_data(ttl=180, show_spinner=False)
def get_derivatives(symbol: str):
    return fetch_with_fallback(symbol)


def plot_prices(f: pd.DataFrame, symbol: str, timeframe: str):
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
        with st.form("coinglass_entry"):
            a, b = st.columns(2)
            with a:
                date_seen = st.date_input("วันที่ที่อ่านข้อมูล (ไทย)", value=now_th.date())
            with b:
                time_seen = st.time_input("เวลาที่อ่านข้อมูล (ไทย)", value=now_th.time().replace(second=0, microsecond=0))
            a, b = st.columns(2)
            with a:
                funding = st.number_input("Funding Rate (%)", value=0.0, min_value=-5.0,
                                          max_value=5.0, step=0.001, format="%.4f")
            with b:
                oi_change = st.number_input("OI Change 24h (%)", value=0.0, min_value=-100.0,
                                            max_value=1000.0, step=0.1, format="%.2f")
            ratio = st.number_input("Long/Short Accounts Ratio", value=1.0, min_value=0.01,
                                    max_value=50.0, step=0.01, format="%.3f")
            a, b = st.columns(2)
            with a:
                long_liq = st.number_input("Liquidated Long 24h (USD)", value=0.0,
                                           min_value=0.0, step=100000.0, format="%.2f")
            with b:
                short_liq = st.number_input("Liquidated Short 24h (USD)", value=0.0,
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
st.caption("v2.2 · Binance Spot + Binance/Bybit Futures public · CoinGlass เสริม · ไม่ส่งออเดอร์ · ไม่มี API Key")
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
    st.subheader("ข้อมูลอนุพันธ์อัตโนมัติ — Binance / Bybit Futures")
    st.caption("คู่ USDT · ลอง Binance ก่อน ถ้าใช้ไม่ได้จึงลอง Bybit · ข้อมูลตลาดเดียวต่อครั้ง ไม่ใช่ CoinGlass · กราฟ Spot มาจาก Binance")
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
        f_cols[0].metric("Funding ล่าสุด (%)", f"{derivatives.funding_rate_pct:+.4f}%")
        f_cols[1].metric("OI เปลี่ยน 24 ชม.", f"{derivatives.oi_change_24h_pct:+.2f}%")
        f_cols[0].metric("Long/Short Accounts", f"{derivatives.long_short_account_ratio:.3f}")
        f_cols[1].metric("OI มูลค่า (USDT)", f"{derivatives.oi_notional_usdt:,.0f}")
        st.caption(f"ที่มา: {derivatives.source} · Funding {derivatives.funding_at.astimezone(BKK):%d/%m %H:%M} · OI {derivatives.oi_at.astimezone(BKK):%d/%m %H:%M} · L/S {derivatives.ratio_at.astimezone(BKK):%d/%m %H:%M} (เวลาไทย)")
        st.info("OI Change 24h ของ Binance คำนวณจากมูลค่า OI; ของ Bybit คำนวณจากปริมาณสัญญา จึงเทียบค่าข้ามแหล่งตรง ๆ ไม่ได้ · Liquidations รวมหลายตลาดไม่มีใน Public API ชุดนี้")
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
    st.subheader(f"{colors[final_signal]} Final Signal: {final_signal}")
    st.caption(f"Technical: {raw} · Binance Futures: {auto['status']} · CoinGlass: {cg['status'] if snapshot else 'ไม่ได้กรอก (เสริม)'}")
    if final_signal != "WAIT":
        st.warning("สัญญาณนี้อาศัย Spot + Futures จากแหล่งที่ระบุ หากไม่มี CoinGlass จะยังไม่ใช่สัญญาณที่ CoinGlass ยืนยัน และยังไม่มีสถิติทดสอบกฎอนุพันธ์ร่วม")
    # Two metrics per row are legible on narrow mobile viewports.
    last = analyzed.iloc[-1]
    metrics = [("ราคาปิด", money(float(last["close"]))),
               ("Technical Score", f"{int(last['score']):+d}/{7 if timeframe == '1d' else 9}"),
               ("RSI", f"{float(last['rsi']):.1f}"),
               ("ADX", f"{float(last['adx']):.1f}"),
               ("Volume Ratio", f"{float(last['volume_ratio']):.2f}×")]
    for offset in range(0, len(metrics), 2):
        cols = st.columns(2)
        for col, (name, value) in zip(cols, metrics[offset:offset + 2]):
            col.metric(name, value)
    st.plotly_chart(plot_prices(analyzed, symbol, timeframe), width="stretch")
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
        st.write("Pivot High:", money(float(last["pivot_high"])) if pd.notna(last["pivot_high"]) else "ไม่พร้อม")
        st.write("Pivot Low:", money(float(last["pivot_low"])) if pd.notna(last["pivot_low"]) else "ไม่พร้อม")
        st.write("ATR(14):", money(float(last["atr"])))
        if final_signal == "BUY":
            entry = float(last["close"])
            stop = max(0, min(entry - 1.5 * float(last["atr"]), float(last["support50"]) - 0.2 * float(last["atr"])))
            distance = entry - stop
            planned_qty = min(capital * risk_pct / 100 / distance, capital * allocation / 100 / entry) if distance > 0 else 0
            st.success(f"ราคาอ้างอิง {money(entry)} · SL {money(stop)} · TP(2R) {money(entry + 2 * distance)}")
            st.write(f"ขนาดสถานะเชิงตัวอย่าง: {planned_qty:.6f} {selected['base']} (ก่อนค่าธรรมเนียม)")
        else:
            st.info("แสดงแผนเข้าซื้อเมื่อ BUY ผ่านตัวกรองที่เปิดใช้อยู่เท่านั้น · SELL สำหรับ Spot คือขาย/ลดเหรียญที่ถือ")
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
    3. อ่าน **Technical Signal** จาก Spot, **Auto Signal** จาก Binance Futures และ **Final Signal** ที่รวมตัวกรองเสริม
    4. เปิดแท็บ **Backtest** และ **Walk-forward** เพื่อตรวจสถิติย้อนหลัง (เฉพาะกลยุทธ์เทคนิค)
    5. CoinGlass เป็นข้อมูลเสริมแบบกรอกเอง; ถ้าไม่กรอกจะใช้ผล Futures แต่หากกรอกแล้วมีข้อเตือน/หมดอายุ จะเป็น `WAIT`

    ### ข้อจำกัดสำคัญ
    - CoinGlass API ทางการเป็นบริการที่ใช้ API Key และแพ็กเกจชำระเงิน ณ วันที่ตรวจสอบ ดังนั้นโหมดฟรีต้องกรอกค่าด้วยมือ
    - ผล Backtest/Walk-forward **ไม่ได้รวม Binance Futures หรือ CoinGlass** จึงห้ามตีความว่าได้พิสูจน์กลยุทธ์รวมแล้ว
    - ข้อมูลอนุพันธ์มาจาก Binance USDⓈ-M Futures หรือ Bybit USDT Linear Futures เฉพาะคู่ USDT ที่รองรับ; เป็นข้อมูลตลาดเดียวที่ระบุชัด ไม่ใช่ CoinGlass
    - ไม่ได้รับข้อมูล Liquidations 24h ครบจาก Public API ที่ใช้ จึงไม่ใช้ใน Auto Signal
    - ข้อมูลจาก Binance Spot อาจไม่ตรงกับตลาดที่ผู้ใช้ซื้อขายจริง รวมถึงอาจถูกจำกัดการเข้าถึงบางเครือข่าย/ภูมิภาค
    - ไม่มีการส่งออเดอร์, ไม่มีการใช้ Leverage, ไม่มีการเปิด Short และไม่มีแจ้งเตือน Push ในรุ่นนี้
    - Market Structure เป็น Pivot/BOS/Sweep ตามกฎ ไม่ได้ครอบคลุมข่าว, On-chain, Order Book History หรือระบบสถาบันทั้งหมด
    - Walk-forward เป็นการทดสอบเกณฑ์คะแนน 5/6/7 เฉพาะชุดกฎนี้ และอาจมีตัวอย่างน้อยเกินกว่าจะสรุปผล
    - ข้อมูลราคาที่ใช้มีจำนวนจำกัดตามที่เลือก; โปรดดูจำนวนดีลและสภาวะตลาดก่อนสรุปความน่าเชื่อถือ
    """)
