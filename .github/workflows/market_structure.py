"""Causal market structure: pivots known only after right-side confirmation."""

from __future__ import annotations

import numpy as np
import pandas as pd


def structure_features(frame: pd.DataFrame, pivot_bars: int = 3) -> pd.DataFrame:
    if pivot_bars < 1 or pivot_bars > 10:
        raise ValueError("pivot_bars ต้องอยู่ระหว่าง 1–10")
    n = len(frame)
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    closes = frame["close"].to_numpy(dtype=float)
    pivot_high = np.full(n, np.nan)
    pivot_low = np.full(n, np.nan)
    bias = np.zeros(n, dtype=int)
    bos_up = np.zeros(n, dtype=bool)
    bos_down = np.zeros(n, dtype=bool)
    choch_up = np.zeros(n, dtype=bool)
    choch_down = np.zeros(n, dtype=bool)
    sweep_high = np.zeros(n, dtype=bool)
    sweep_low = np.zeros(n, dtype=bool)
    last_high, last_low = np.nan, np.nan
    current_bias = 0

    for i in range(n):
        if i >= 2 * pivot_bars:
            center = i - pivot_bars
            left = center - pivot_bars
            neighborhood_h = highs[left:i + 1]
            neighborhood_l = lows[left:i + 1]
            # Strictly unique extrema; known only at bar i.
            if int(np.sum(neighborhood_h == highs[center])) == 1 and highs[center] == np.max(neighborhood_h):
                last_high = highs[center]
            if int(np.sum(neighborhood_l == lows[center])) == 1 and lows[center] == np.min(neighborhood_l):
                last_low = lows[center]

        pivot_high[i] = last_high
        pivot_low[i] = last_low
        if i > 0 and np.isfinite(last_high):
            bos_up[i] = closes[i] > last_high and closes[i - 1] <= last_high
            sweep_high[i] = highs[i] > last_high and closes[i] < last_high
        if i > 0 and np.isfinite(last_low):
            bos_down[i] = closes[i] < last_low and closes[i - 1] >= last_low
            sweep_low[i] = lows[i] < last_low and closes[i] > last_low
        if bos_up[i]:
            choch_up[i] = current_bias == -1
            current_bias = 1
        elif bos_down[i]:
            choch_down[i] = current_bias == 1
            current_bias = -1
        bias[i] = current_bias

    return pd.DataFrame({"pivot_high": pivot_high, "pivot_low": pivot_low,
                         "structure_bias": bias, "bos_up": bos_up, "bos_down": bos_down,
                         "choch_up": choch_up, "choch_down": choch_down,
                         "sweep_high": sweep_high, "sweep_low": sweep_low}, index=frame.index)
