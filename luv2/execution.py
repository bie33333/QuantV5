# -*- coding: utf-8 -*-
"""成交模拟与交易成本。

规格书原则：禁止「涨停=买入成功」。用 日线可观测代理 估计成交概率：
  - 当日未封板 → 0（不打非涨停接力）
  - 一字开并封死 → 极低（仅炸板/撤单带来的成交机会）
  - 换手开板并封死 → 基准概率 + 竞价健康修正 - 过热修正
真实 Level-2 时代可替换成排队深度模型（本模块接口预留）。
"""
from __future__ import annotations

import numpy as np


def estimate_fill(today_row, auction: dict, cfg: dict, rng) -> dict:
    """today_row: 打板当日(T)该股日线行(须 sealed/one_word 等)。
    auction: auction_score() 输出。返回概率与成交价。"""
    ecfg = cfg["execution"]
    price = float(today_row["limit_up_price"])
    sealed = bool(today_row["sealed"])
    if not sealed:
        return {"prob": 0.0, "price": price, "partial_ratio": 0.0, "reason": "not_sealed"}
    one_word_open = bool(today_row["one_word"])
    base = float(ecfg["base_fill_prob"]["sealed_one_word"] if one_word_open
                 else ecfg["base_fill_prob"]["sealed_close"])
    # 竞价修正
    ar = float(auction.get("auction_ret", 0.0))
    bonus = float(ecfg.get("exec_bonus", {}).get("healthy", 0.0)) if 0.02 <= ar <= 0.08 \
        else float(ecfg.get("exec_bonus", {}).get("overheated", 0.0)) if ar >= 0.095 else 0.0
    prob = float(np.clip(base + bonus, 0.0, 1.0))
    reason = "one_word_seal" if one_word_open else "churn_seal"
    return {"prob": prob, "price": price, "partial_ratio": 0.0, "reason": reason,
            "one_word": one_word_open}


def decide_fill(prob: float, rng) -> tuple[bool, float]:
    """prob → (是否成交, 部分成交比例 0.5/1.0)。"""
    if prob <= 0:
        return False, 0.0
    r = rng.rand()
    if r < prob * 0.6:            # 高概率区全成交
        return True, 1.0
    if r < prob:                  # 中等区部分成交
        return True, 0.5
    return False, 0.0


# ---------------- 成本 ----------------

def buy_cost(amount: float, cfg: dict) -> float:
    c = cfg["cost"]
    comm = max(amount * float(c["commission"]), float(c["min_commission"]))
    slip = amount * float(c.get("slippage", 0.001))
    return comm + slip


def sell_cost(amount: float, cfg: dict) -> float:
    c = cfg["cost"]
    comm = max(amount * float(c["commission"]), float(c["min_commission"]))
    stamp = amount * float(c["stamp_duty"])
    slip = amount * float(c.get("slippage", 0.001))
    return comm + stamp + slip
