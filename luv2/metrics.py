# -*- coding: utf-8 -*-
"""回测绩效指标（规格书 §33/§42~44）。

核心关注：Expectancy / Profit Factor / Max Drawdown / Execution Rate。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(eq: pd.Series) -> float:
    if len(eq) == 0:
        return 0.0
    roll_max = eq.cummax()
    dd = (eq / roll_max - 1.0).min()
    return float(dd)


def compute_metrics(res: dict, cfg: dict) -> dict:
    eq = res["equity"]
    trades = res["trades"]
    orders = res["orders"]
    out: dict = {}

    if eq is None or len(eq) == 0:
        return {"error": "no equity"}

    eq = eq.reset_index(drop=True)
    equity = eq["equity"].astype(float)
    start_eq = float(equity.iloc[0])
    end_eq = float(equity.iloc[-1])
    days = len(eq)
    years = max(days / 244.0, 1e-9)
    total_ret = end_eq / start_eq - 1.0
    out["total_return"] = float(total_ret)
    out["cagr"] = float((end_eq / start_eq) ** (1 / years) - 1.0) if start_eq > 0 else 0.0
    out["max_drawdown"] = max_drawdown(equity)
    out["start_date"] = str(eq["date"].iloc[0])
    out["end_date"] = str(eq["date"].iloc[-1])
    out["trading_days"] = int(days)

    # ---------- 交易级 ----------
    n_tr = len(trades)
    out["trade_count"] = int(n_tr)
    if n_tr > 0:
        rets = trades["ret"].astype(float)
        wins = rets[rets > 0]
        losses = rets[rets <= 0]
        gross_win = float((trades.loc[rets > 0, "net_pnl"]).sum())
        gross_loss = float(-(trades.loc[rets <= 0, "net_pnl"]).sum())
        out["win_rate"] = float((rets > 0).mean())
        out["avg_win"] = float(wins.mean()) if len(wins) else 0.0
        out["avg_loss"] = float(losses.mean()) if len(losses) else 0.0
        out["profit_factor"] = float(gross_win / gross_loss) if gross_loss > 0 else (np.inf if gross_win > 0 else 0.0)
        out["expectancy"] = float(rets.mean())           # 每笔平均净收益(含成本)
        out["max_consec_losses"] = int(_max_consec(rets.to_numpy()))
        # 收益分布
        out["median_ret"] = float(rets.median())
        out["best_trade"] = float(rets.max())
        out["worst_trade"] = float(rets.min())
        # T+1 统计（以次日收盘相对入场价）
        t1 = trades["t1_close"].dropna().astype(float)
        t1o = trades["t1_open"].dropna().astype(float)
        out["t1_avg_open"] = float(t1o.mean()) if len(t1o) else np.nan
        out["t1_avg_close"] = float(t1.mean()) if len(t1) else np.nan
        out["t1_median_close"] = float(t1.median()) if len(t1) else np.nan
        out["t1_win_rate"] = float((t1 > 0).mean()) if len(t1) else np.nan
        # 退出原因分布
        out["exit_reason"] = trades["exit_reason"].value_counts().to_dict()
        out["avg_hold_days"] = float(trades["hold_days"].mean()) if n_tr else 0.0
        # 年度/月度收益
        out["annual_returns"] = _annual_returns(eq)
    else:
        out.update({"win_rate": 0.0, "profit_factor": 0.0, "expectancy": 0.0})

    # ---------- 执行统计 ----------
    if orders is not None and len(orders):
        oc = orders["outcome"].value_counts().to_dict()
        out["order_outcome"] = oc
        n_orders = int(len(orders))
        n_filled = int(oc.get("filled", 0))
        out["candidate_count"] = n_orders
        out["execution_rate"] = n_filled / n_orders if n_orders else 0.0
        out["missed_rate"] = 1.0 - out["execution_rate"]
    else:
        out["execution_rate"] = 0.0
    return out


def _max_consec(arr: np.ndarray) -> int:
    best = cur = 0
    for x in arr:
        cur = cur + 1 if x <= 0 else 0
        best = max(best, cur)
    return best


def _annual_returns(eq: pd.DataFrame) -> dict:
    e = eq.copy()
    e["year"] = e["date"].astype(str).str[:4]
    out: dict[str, float] = {}
    for yr, g in e.groupby("year"):
        if len(g) < 5:
            continue
        out[str(yr)] = float(g["equity"].iloc[-1] / g["equity"].iloc[0] - 1.0)
    return out
