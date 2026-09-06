# -*- coding: utf-8 -*-
"""第一层 · Market Regime Engine（市场情绪层）。

8 因子 → 0~100 情绪分（规格书权重）→ 状态映射 → 交易权限(硬闸门)。
因子原始值先做「滚动自适应百分位映射」(window=adaptive_window，不含当日)，
再按 越高越好 / 越低越好 折算到该因子权重区间，避免固定阈值失效。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# 特征 → (方向, 权重键)；权重在 config.market.weights 中
FEATURES = {
    "limit_up_count":        ("higher", "limit_up_count"),
    "limit_down_count":      ("lower",  "limit_down_count"),
    "promotion_rate":        ("higher", "promotion_rate"),
    "y_lu_ret":              ("higher", "yesterday_lu_avg_ret"),
    "y_lb_ret":              ("higher", "yesterday_lb_avg_ret"),
    "break_rate":            ("lower",  "break_rate"),
    "highest_board":         ("higher", "highest_board"),
    "lianban_count":         ("higher", "lianban_count"),
}

REGIME_ORDER = ["VERY_STRONG", "STRONG", "NORMAL", "WEAK", "FROZEN"]


def compute_sentiment(mkt: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """mkt: market_daily_features 输出。返回增加 因子分/sentiment/regime/permission/pos_mult 列。"""
    out = mkt.copy().sort_values("trade_date").reset_index(drop=True)
    w = cfg["market"]["weights"]
    win = int(cfg["market"].get("adaptive_window", 60))

    total_w = 0.0
    for col, (direction, key) in FEATURES.items():
        wi = float(w.get(key, 0))
        total_w += wi
        if col not in out.columns:
            out[col + "_score"] = 0.0
            continue
        # 滚动分位数锚（窗口前移一天，避免用到当日自身 → 无未来函数）
        s = out[col].astype(float)
        q_lo = s.shift(1).rolling(win, min_periods=15).quantile(0.20)
        q_hi = s.shift(1).rolling(win, min_periods=15).quantile(0.80)
        span = (q_hi - q_lo).replace(0, np.nan)
        # 无有效锚点时退化为线性映射到 [0,1]
        fmin, fmax = _feature_minmax(col)
        raw_lin = np.clip((s - fmin) / (fmax - fmin), 0, 1) if fmax > fmin else s * 0 + 0.5
        norm = pd.Series(np.where(
            span.notna() & q_lo.notna(),
            np.clip((s - q_lo) / span, 0, 1),
            raw_lin,
        ), index=out.index)
        if direction == "lower":
            norm = 1.0 - norm
        out[col + "_score"] = (norm * wi).clip(0, wi)

    # 情绪总分 = Σ 因子分（权重合计应=100；异常则归一）
    score_cols = [c for c in out.columns if c.endswith("_score")]
    out["sentiment"] = out[score_cols].sum(axis=1)
    if abs(total_w - 100.0) > 1e-6 and total_w > 0:
        out["sentiment"] = out["sentiment"] / total_w * 100.0
    out["sentiment"] = out["sentiment"].clip(0, 100)

    # 状态映射
    regimes = cfg["market"]["regimes"]
    perm_map = cfg["market"]["permission"]
    mult_map = cfg["market"]["position_multiplier"]
    regs: list[str] = []
    perms: list[bool] = []
    mults: list[float] = []
    for v in out["sentiment"]:
        reg = "FROZEN"
        for name, (lo, hi) in regimes.items():
            if lo <= v < hi:
                reg = name
                break
        regs.append(reg)
        perms.append(bool(perm_map.get(reg, False)))
        mults.append(float(mult_map.get(reg, 0.0)))
    out["regime"] = regs
    out["permission"] = perms
    out["pos_mult"] = mults
    return out


def _feature_minmax(col: str) -> tuple[float, float]:
    """固定极值（仅当自适应锚缺失时兜底，近似即可）。"""
    lo_hi = {
        "limit_up_count": (0.0, 3.0),      # 由合成/真实取值域决定，仅兜底
        "limit_down_count": (0.0, 2.0),
        "promotion_rate": (0.0, 1.0),
        "y_lu_ret": (-0.09, 0.09),
        "y_lb_ret": (-0.09, 0.09),
        "break_rate": (0.0, 1.0),
        "highest_board": (0.0, 8.0),
        "lianban_count": (0.0, 2.5),
    }
    return lo_hi.get(col, (0.0, 1.0))
