"""Transparent long-only spot simulation; uses the same signals as the dashboard.

No actual orders. All signals become actionable no earlier than the *next* bar.
Conservatively prioritize stop over target if both are hit inside one candle.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from research_engine import with_signal


@dataclass(frozen=True)
class BacktestConfig:
    capital: float = 10000.0
    risk_per_trade_pct: float = 1.0
    max_allocation_pct: float = 30.0
    fee_pct: float = 0.1
    slippage_pct: float = 0.05
    max_drawdown_pct: float = 25.0

    def check(self):
        if self.capital <= 0:
            raise ValueError("เงินจำลองต้องมากกว่า 0")
        if not (0 < self.risk_per_trade_pct <= 5 and 0 < self.max_allocation_pct <= 100):
            raise ValueError("ค่าความเสี่ยงหรือสัดส่วนเงินไม่ถูกต้อง")
        if not (0 <= self.fee_pct <= 5 and 0 <= self.slippage_pct <= 5):
            raise ValueError("ค่าธรรมเนียมหรือ Slippage ไม่ถูกต้อง")
        if not (1 <= self.max_drawdown_pct <= 100):
            raise ValueError("Max Drawdown Limit ไม่ถูกต้อง")


def _stats(trades: list[dict], equity: pd.DataFrame, capital: float, benchmark: float) -> dict:
    if equity.empty:
        return {"trades": 0, "return_pct": 0.0, "win_rate_pct": 0.0,
                "profit_factor": None, "max_drawdown_pct": 0.0,
                "expectancy_pct": None, "benchmark_pct": benchmark}
    pnl = [float(t["pnl"]) for t in trades]
    wins = [v for v in pnl if v > 0]
    losses = [v for v in pnl if v < 0]
    pf = sum(wins) / -sum(losses) if losses else (math.inf if wins else None)
    curve = equity["equity"]
    dd = (1 - curve / curve.cummax()).max() * 100
    return {"trades": len(trades), "return_pct": (curve.iloc[-1] / capital - 1) * 100,
            "win_rate_pct": 100 * len(wins) / len(trades) if trades else 0.0,
            "profit_factor": pf, "max_drawdown_pct": float(dd),
            "expectancy_pct": float(np.mean([t["return_pct"] for t in trades])) if trades else None,
            "benchmark_pct": benchmark}


def simulate(features: pd.DataFrame, config: BacktestConfig,
             *, threshold: int | None = None, start: int = 250, end: int | None = None) -> dict:
    """Run the historical technical strategy with spot-only execution.

    CoinGlass is excluded because a historical dataset has not been obtained.
    """
    config.check()
    f = with_signal(features, threshold=threshold)
    n = len(f)
    end = n if end is None else min(n, end)
    start = max(250, start)
    if end - start < 2:
        raise ValueError("ช่วง Backtest ต้องมีอย่างน้อย 2 แท่งหลัง Warm-up")

    fee = config.fee_pct / 100
    slip = config.slippage_pct / 100
    cash, units = config.capital, 0.0
    entry_price, entry_cost, entry_at, stop, target = 0.0, 0.0, None, None, None
    peak_equity = config.capital
    blocked, force_exit = False, False
    records: list[dict] = []
    equity_records: list[dict] = []

    def close_position(price: float, at, reason: str):
        nonlocal cash, units, entry_price, entry_cost, entry_at, stop, target
        if units <= 0:
            return
        fill = max(0, price * (1 - slip))
        gross_proceeds = units * fill
        net_proceeds = gross_proceeds * (1 - fee)
        pnl = net_proceeds - entry_cost
        records.append({"entry_time": entry_at, "exit_time": at, "entry_price": entry_price,
                        "exit_price": fill, "pnl": pnl, "return_pct": 100 * pnl / entry_cost,
                        "reason": reason, "side": "LONG"})
        cash += net_proceeds
        units, entry_price, entry_cost, entry_at, stop, target = 0.0, 0.0, 0.0, None, None, None

    for i in range(start, end):
        current = f.iloc[i]
        prev = f.iloc[i - 1]
        open_price = float(current["open"])
        if not np.isfinite(open_price) or open_price <= 0:
            continue

        # Use ONLY the signal on i-1's closed candle at today's opening.
        if units > 0 and (force_exit or prev["signal"] == "SELL"):
            close_position(open_price, current.name, "drawdown_stop" if force_exit else "sell_signal")
        force_exit = False

        if units == 0 and not blocked and prev["signal"] == "BUY":
            atr, support = float(prev["atr"]), float(prev["support50"])
            if np.isfinite(atr) and atr > 0:
                fill = open_price * (1 + slip)
                proposed_stop = fill - 1.5 * atr
                if np.isfinite(support):
                    proposed_stop = min(proposed_stop, support - 0.2 * atr)
                proposed_stop = max(0.0, proposed_stop)
                distance = fill - proposed_stop
                if distance > 0 and distance / fill <= 0.15:
                    risk_money = cash * config.risk_per_trade_pct / 100
                    budget = cash * config.max_allocation_pct / 100
                    amount = min(risk_money / distance, budget / (fill * (1 + fee)))
                    cost = amount * fill * (1 + fee)
                    if amount > 0 and cost <= cash:
                        cash -= cost
                        units, entry_price, entry_cost, entry_at = amount, fill, cost, current.name
                        stop, target = proposed_stop, fill + 2 * distance

        if units > 0:
            # If both stop and target are inside the candle, count the STOP first.
            if float(current["low"]) <= stop:
                close_position(min(open_price, stop), current.name, "stop_loss")
            elif float(current["high"]) >= target:
                close_position(target, current.name, "take_profit_2R")

        marked_equity = cash + units * float(current["close"])
        peak_equity = max(peak_equity, marked_equity)
        if marked_equity < peak_equity * (1 - config.max_drawdown_pct / 100):
            blocked = True
            force_exit = units > 0
        equity_records.append({"timestamp": current.name, "equity": marked_equity})

    # Close any remaining position at final CLOSE, with transaction costs.
    if units > 0:
        close_position(float(f.iloc[end - 1]["close"]), f.index[end - 1], "period_end")
        equity_records[-1]["equity"] = cash

    curve = pd.DataFrame(equity_records).set_index("timestamp")
    price_return = (float(f.iloc[end - 1]["close"]) / float(f.iloc[start]["open"]) - 1) * 100
    stats = _stats(records, curve, config.capital, price_return)
    return {"stats": stats, "trades": pd.DataFrame(records), "equity": curve,
            "start": f.index[start], "end": f.index[end - 1], "threshold": threshold,
            "blocked_by_drawdown": blocked}


def walk_forward(features: pd.DataFrame, config: BacktestConfig) -> dict:
    """Rolling train-only optimization then disjoint forward test windows."""
    n = len(features)
    if n < 1500:
        return {"status": "INSUFFICIENT", "reason": "Walk-forward ต้องการอย่างน้อย 1,500 แท่ง", "folds": []}
    earliest = 250
    usable = n - earliest
    train_size = max(700, int(usable * 0.5))
    test_size = max(200, int(usable * 0.15))
    start_test = earliest + train_size
    folds: list[dict] = []
    while start_test + 100 < n and len(folds) < 4:
        train_start = start_test - train_size
        test_end = min(start_test + test_size, n)
        scores = []
        for threshold in (5, 6, 7):
            run = simulate(features, config, threshold=threshold, start=train_start, end=start_test)
            stats = run["stats"]
            # Penalize drawdown and require a minimum number of sample trades.
            fitness = (stats["return_pct"] - 0.5 * stats["max_drawdown_pct"]
                       if stats["trades"] >= 5 else -1e6)
            scores.append((fitness, threshold))
        best_score, chosen = max(scores, key=lambda x: (x[0], -abs(x[1] - 6)))
        if best_score <= -1e6:
            chosen = 6
        tested = simulate(features, config, threshold=chosen, start=start_test, end=test_end)
        folds.append({"train_start": features.index[train_start], "train_end": features.index[start_test - 1],
                      "test_start": tested["start"], "test_end": tested["end"], "threshold": chosen,
                      "train_qualified": best_score > -1e6, **tested["stats"]})
        start_test = test_end
    return {"status": "OK" if folds else "INSUFFICIENT", "folds": folds,
            "reason": "ฝึกเฉพาะช่วงอดีต แล้วประเมินช่วงถัดไปโดยไม่ปรับด้วยผลช่วงทดสอบ"}
