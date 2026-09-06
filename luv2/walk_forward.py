# -*- coding: utf-8 -*-
"""分层消融（Model A/B/C/D）与 Walk-Forward 样本外验证。

消融：逐层加入 市场情绪 → 板块 → 龙头/竞价/成交模拟（规格书 §48）。
Walk-Forward：按时间切训练/测试窗口滚动，只统计样本外（§30/§35）。
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd

from .backtest import GateCfg, run_backtest
from .metrics import compute_metrics


# ---------------- 消融 ----------------

def make_ablation_gates() -> dict[str, GateCfg]:
    return {
        # A: 原 v1 近似 —— 无任何环境/成交过滤，score>=70 即买（涨停即成交）
        "A": GateCfg(market=False, theme=False, leadership=False, auction=False,
                     exec_gate=False, allow_c=True, min_score=70.0),
        # B: A + 市场情绪闸门
        "B": GateCfg(market=True, theme=False, leadership=False, auction=False,
                     exec_gate=False, allow_c=True, min_score=70.0),
        # C: B + 板块强度闸门
        "C": GateCfg(market=True, theme=True, leadership=False, auction=False,
                     exec_gate=False, allow_c=True, min_score=70.0),
        # D: 完整 v2（龙头/竞价/成交模拟）——与主基线 GateCfg() 一致
        "D": GateCfg(),
    }


def run_ablation(bundle, cfg: dict) -> dict:
    res = {}
    for name, g in make_ablation_gates().items():
        cfg_i = copy.deepcopy(cfg)
        r = run_backtest(bundle, cfg_i, gates=g, label=name,
                         rng_seed=int(cfg["execution"].get("rng_seed", 20260906)))
        m = compute_metrics(r, cfg_i)
        res[name] = {
            "gates": {k: getattr(g, k) for k in
                      ("market", "theme", "leadership", "auction", "exec_gate", "allow_c")},
            "metrics": _pick(m),
            "trade_count": m.get("trade_count", 0),
        }
    return res


def _pick(m: dict) -> dict:
    keys = ["total_return", "cagr", "max_drawdown", "win_rate", "profit_factor",
            "expectancy", "execution_rate", "avg_hold_days", "t1_avg_close", "t1_win_rate",
            "max_consec_losses"]
    return {k: m.get(k) for k in keys}


# ---------------- Walk-Forward ----------------

def make_folds(all_dates: list[str], test_months: int = 6, step_months: int = 3,
               min_train_days: int = 250) -> list[dict]:
    """把全部交易日切成滚动 train/test 折。返回每折 {label, train_end, test_start, test_end}。"""
    idx_all = list(range(len(all_dates)))
    months = {d[:7]: i for i, d in enumerate(all_dates)}
    # 用月 index 计算
    mlist = sorted(set(d[:7] for d in all_dates))
    folds = []
    # 允许最后 test 为 ≤test_months 的残段
    k = 0
    while k + test_months <= len(mlist):
        test_m = mlist[k + test_months - 1]
        train_m = mlist[k - 1] if k > 0 else mlist[0]
        folds.append({"test_start": f"{mlist[k]}-01", "test_end": f"{test_m}-31",
                      "train_end": f"{train_m}-31"})
        k += step_months
    if not folds:
        return []
    # 过滤训练期过短的折
    out = []
    for f in folds:
        train_days = sum(1 for d in all_dates if d <= f["train_end"])
        if train_days < min_train_days:
            continue
        out.append(f)
    return out


def run_walk_forward(bundle, cfg: dict, gates: GateCfg | None = None) -> dict:
    dates = np.sort(bundle.daily["trade_date"].unique())
    dates = [d for d in dates if cfg["backtest"]["start"] <= d <= cfg["backtest"]["end"]]
    folds = make_folds(dates)
    gates = gates or GateCfg()
    rows = []
    for f in folds:
        c = copy.deepcopy(cfg)
        c["backtest"]["start"] = f["test_start"]
        c["backtest"]["end"] = f["test_end"]
        r = run_backtest(bundle, c, gates=gates, label=f['test_start'][:7],
                         rng_seed=int(cfg["execution"].get("rng_seed", 20260906)))
        m = compute_metrics(r, c)
        rows.append({"fold": f['test_start'][:7], "trades": m.get("trade_count", 0),
                     **_pick(m)})
    return {"folds": rows}
