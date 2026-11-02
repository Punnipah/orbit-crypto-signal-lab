"""Orbit Model Lab: causal, paper-only comparison of two simple baselines.

Input CSV must contain timestamp, open, high, low, close, volume.
Signals use completed candles; next-candle open is the earliest simulated fill.
This is educational research, not live trading advice.
"""
import numpy as np
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Orbit Model Lab", layout="wide")
st.title("Orbit Model Lab — Paper Research")
st.caption("Independent experiment branch • No orders, no Telegram, no live signals")
uploaded = st.file_uploader("Upload historical OHLCV CSV", type=["csv"])
fee_bps = st.number_input("Round-trip trading costs (bps)", min_value=0.0, max_value=500.0, value=30.0, step=5.0)
if uploaded:
    try:
        df = pd.read_csv(uploaded)
        required = {"timestamp","open","high","low","close","volume"}
        if not required.issubset(df.columns):
            raise ValueError("Required columns: " + ", ".join(sorted(required)))
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="raise")
        df = df.sort_values("timestamp").drop_duplicates("timestamp").set_index("timestamp")
        for col in ["open","high","low","close","volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.replace([np.inf,-np.inf],np.nan).dropna(subset=list(required-{"timestamp"}))
        if len(df)<120 or (df[["open","high","low","close"]]<=0).any().any() or (df["volume"]<0).any():
            raise ValueError("Need at least 120 valid candles and positive OHLC/nonnegative volume")
        if ((df["high"]<df[["open","close","low"]].max(axis=1)) | (df["low"]>df[["open","close","high"]].min(axis=1))).any():
            raise ValueError("Inconsistent OHLC rows")
        close=df["close"]
        ema_fast=close.ewm(span=9,adjust=False,min_periods=30).mean()
        ema_slow=close.ewm(span=21,adjust=False,min_periods=30).mean()
        mean=close.rolling(20,min_periods=20).mean()
        std=close.rolling(20,min_periods=20).std()
        models={
          "EMA 9/21 crossover": ((ema_fast>ema_slow)&(ema_fast.shift(1)<=ema_slow.shift(1))).astype(int),
          "BB20 lower-band reversion": (close<mean-2*std).astype(int)
        }
        # A fixed 3-candle holding period; overlapping entries are ignored.
        split=int(len(df)*0.7)
        results=[]
        for name, signal in models.items():
            for label, lo, hi in [("Train (first 70%)",30,split),("Holdout (last 30%)",split,len(df)-3)]:
                rets=[]; i=lo
                while i<hi:
                    if signal.iloc[i-1]:
                        entry=float(df["open"].iloc[i])
                        exit_price=float(df["open"].iloc[i+3])
                        rets.append((exit_price/entry-1)-fee_bps/10000)
                        i+=3
                    else:
                        i+=1
                arr=np.array(rets)
                results.append({"Model":name,"Period":label,"Trades":len(arr),
                                "Win rate %":round(float((arr>0).mean()*100),2) if len(arr) else None,
                                "Mean net trade %":round(float(arr.mean()*100),3) if len(arr) else None,
                                "Sum trade returns % (not portfolio P&L)":round(float(arr.sum()*100),2) if len(arr) else None})
        st.dataframe(pd.DataFrame(results),use_container_width=True,hide_index=True)
        st.warning("Research limitations: fixed 3-bar holding, no intrabar stop/fills, funding, order-book depth or market impact. Holdout is not walk-forward. Do not infer future profitability.")
    except Exception as exc:
        st.error(str(exc))
else:
    st.info("Upload an OHLCV CSV to compare baseline signals on a chronological holdout.")
