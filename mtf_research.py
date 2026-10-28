"""Causal Spot-only research subset of the v2.7 MTF entry logic.

Historical Order Book, aggTrades, CoinGlass, Futures and BTC-regime snapshots
are NOT available in this local dataset. Results must never be presented as
validation of the live full-signal gate.
"""

from __future__ import annotations

from datetime import timedelta
import numpy as np
import pandas as pd

from backtest_engine import BacktestConfig, simulate
from binance_data import TIMEFRAMES, count_time_gaps
from entry_planner import plan_entry


def _known_at(base_close: pd.DatetimeIndex, other: pd.DataFrame,
              timeframe: str, columns: tuple[str, ...]) -> pd.DataFrame:
    """Merge only already CLOSED candles, rejecting old unmatched context."""
    left = pd.DataFrame({"at": base_close})
    right = other.loc[:, list(columns)].copy()
    right["known_at"] = other.index + timedelta(minutes=TIMEFRAMES[timeframe])
    right = right.sort_values("known_at").reset_index(drop=True)
    merged = pd.merge_asof(left.sort_values("at"), right, left_on="at",
                           right_on="known_at", direction="backward")
    age = (merged["at"] - merged["known_at"]).dt.total_seconds()
    stale = age.isna() | (age > TIMEFRAMES[timeframe] * 60)
    for name in columns:
        merged.loc[stale, name] = np.nan
    return merged.loc[:, list(columns)].reset_index(drop=True)


def historical_mtf_features(frames: dict[str, pd.DataFrame], config: BacktestConfig) -> pd.DataFrame:
    """Signals at 1h CLOSE, executed no sooner than next 1h OPEN."""
    required = ("15m", "1h", "4h", "1d")
    if any(tf not in frames or frames[tf].empty for tf in required):
        raise ValueError("ต้องมีข้อมูลวิเคราะห์ครบ 15m / 1h / 4h / 1d")
    for tf in required:
        if count_time_gaps(frames[tf], tf):
            raise ValueError("มีช่องว่างแท่งเทียน จึงไม่รัน MTF Backtest")
    config.check()

    hour = frames["1h"].copy()
    when = hour.index + timedelta(hours=1)
    fast = _known_at(when, frames["15m"], "15m",
                     ("signal", "open", "close", "volume_ratio", "score", "taker_buy_share20"))
    four = _known_at(when, frames["4h"], "4h",
                     ("trend", "higher_trend", "structure_bias", "score"))
    daily = _known_at(when, frames["1d"], "1d",
                      ("trend", "structure_bias", "score"))
    fast.index = hour.index
    four.index = hour.index
    daily.index = hour.index

    # Cross-timeframe weighted signal. All other context must have been known
    # at the corresponding 1h candle's close; no forward-filled future candle.
    alignment = 50 + 50 * (
        .30 * (daily["score"] / 7).clip(-1, 1) +
        .30 * (four["score"] / 9).clip(-1, 1) +
        .25 * (hour["score"] / 9).clip(-1, 1) +
        .15 * (fast["score"] / 9).clip(-1, 1)
    )
    shared_gate = (
        (daily["trend"] == 1) & (daily["structure_bias"] >= 0) &
        (four["trend"] == 1) & (four["higher_trend"] == 1) &
        (four["structure_bias"] >= 0) & (hour["signal"] == "BUY") &
        (fast["signal"] == "BUY") & (fast["close"] > fast["open"]) &
        (fast["volume_ratio"] >= .75) &
        (fast["taker_buy_share20"] >= .52) &
        (hour["taker_buy_share20"] >= .52)
    )
    hour["mtf_strength"] = alignment
    hour["mtf_base_gate"] = shared_gate.fillna(False)
    hour["mtf_entry_low"] = np.nan
    hour["mtf_entry_high"] = np.nan
    hour["mtf_stop"] = np.nan
    hour["mtf_tp2"] = np.nan
    for i in np.flatnonzero(hour["mtf_base_gate"].to_numpy(dtype=bool)):
        row = hour.iloc[i]
        plan = plan_entry(
            row, "1h", "BUY", (hour.index[i] + timedelta(hours=1)).to_pydatetime(),
            capital=config.capital, risk_pct=config.risk_per_trade_pct,
            max_allocation_pct=config.max_allocation_pct,
            fee_pct=config.fee_pct, slippage_pct=config.slippage_pct,
            current_price=float(row["close"]),
        )
        if plan.status == "READY":
            hour.iloc[i, hour.columns.get_loc("mtf_entry_low")] = plan.entry_low
            hour.iloc[i, hour.columns.get_loc("mtf_entry_high")] = plan.entry_high
            hour.iloc[i, hour.columns.get_loc("mtf_stop")] = plan.stop_loss
            hour.iloc[i, hour.columns.get_loc("mtf_tp2")] = plan.take_profit_2
    return hour


def run_mtf_backtest(features: pd.DataFrame, config: BacktestConfig, cutoff: int,
                     *, start: int = 250, end: int | None = None) -> dict:
    f = features.copy()
    f["signal"] = np.where(
        f["mtf_base_gate"] & f["mtf_entry_low"].notna() & (f["mtf_strength"] >= cutoff),
        "BUY", "WAIT",
    )
    return simulate(f, config, start=start, end=end,
                    precomputed_signals=True, planned_levels=True)


def mtf_walk_forward(features: pd.DataFrame, config: BacktestConfig) -> dict:
    """Choose a strength cutoff on train only, evaluate disjoint test windows."""
    n = len(features)
    if n < 1500:
        return {"status": "INSUFFICIENT", "reason": "ต้องมีอย่างน้อย 1500 แท่ง 1h สำหรับ MTF Walk-forward", "folds": []}
    start_test = max(950, int(n * .60))
    test_size = max(200, int(n * .12))
    train_size = max(700, int(n * .45))
    folds = []
    while start_test + 100 < n and len(folds) < 4:
        train_start = max(250, start_test - train_size)
        test_end = min(n, start_test + test_size)
        fitness = []
        for threshold in (65, 70, 75):
            trial = run_mtf_backtest(features, config, threshold, start=train_start, end=start_test)
            stats = trial["stats"]
            score = (stats["return_pct"] - .5 * stats["max_drawdown_pct"]
                     if stats["trades"] >= 5 else -1e6)
            fitness.append((score, threshold))
        best, chosen = max(fitness, key=lambda x: (x[0], -abs(x[1] - 70)))
        if best <= -1e6:
            chosen = 70
        tested = run_mtf_backtest(features, config, chosen, start=start_test, end=test_end)
        folds.append({"train_start": features.index[train_start],
                      "train_end": features.index[start_test - 1],
                      "test_start": tested["start"], "test_end": tested["end"],
                      "score_cutoff": chosen, "train_qualified": best > -1e6,
                      **tested["stats"]})
        start_test = test_end
    return {"status": "OK" if folds else "INSUFFICIENT", "folds": folds,
            "reason": "ฝึกเฉพาะอดีต ทดสอบช่วงถัดไปแบบไม่มีการใช้ข้อมูลอนาคต; ไม่รวมข้อมูล Order Book/Futures/CoinGlass/BTC"}

