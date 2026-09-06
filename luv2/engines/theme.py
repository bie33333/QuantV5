# -*- coding: utf-8 -*-
"""第二层 · Theme Engine（板块强度层）。

按 题材/行业(industry 代理) 每日动态计算 THEME_SCORE(0~100) 与持续性，
取消静态"热点行业名单"。数据粒度：日期 × 题材。

THEME_SCORE 因子(规格书权重)：
  涨停数量20 / 3日收益15 / 5日收益10 / 成交额增长15 / 全市场占比10 /
  连板家数10 / 最高板10 / 晋级率10
持续性 = 过去5日 THEME_RAW 加权均值 [1,2,3,4,5]；final = blend*raw + (1-blend)*persistence
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_theme_table(daily: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """输入规范日线，输出 (trade_date, industry) 粒度的板块评分表。"""
    d = daily.copy()
    d["industry"] = d["industry"].astype(str)
    w = cfg["theme"]["weights"]
    pers = cfg["theme"]["persistence"]
    blend = float(pers.get("blend", 0.5))

    # 全市场涨停家数（按日）
    lu_daily = d[d["sealed"]].groupby("trade_date").size().rename("mkt_lu")

    # 个股自身 N 日收益（供板块 3/5 日收益）
    d = d.sort_values(["code", "trade_date"]).copy()
    g = d.groupby("code", sort=False)["close"]
    d["r3"] = d["close"] / g.shift(3) - 1.0
    d["r5"] = d["close"] / g.shift(5) - 1.0

    # 主题日度原始聚合
    agg = d.groupby(["trade_date", "industry"]).agg(
        amount=("amount", "sum"),
        r3_mean=("r3", "mean"),
        r5_mean=("r5", "mean"),
    ).reset_index()
    sealed = d[d["sealed"]]
    ev = sealed.groupby(["trade_date", "industry"]).agg(
        lu_count=("code", "count"),
        lianban_count=("code", lambda x: int((sealed.loc[x.index, "board_count"] >= 2).sum())),
        highest_board=("board_count", "max"),
    ).reset_index()
    promo = _theme_promotion(d)

    t = agg.merge(ev, on=["trade_date", "industry"], how="outer")
    t["lu_count"] = t["lu_count"].fillna(0)
    t["lianban_count"] = t["lianban_count"].fillna(0)
    t["highest_board"] = t["highest_board"].fillna(0)
    t["r3_mean"] = t["r3_mean"].fillna(np.nan)
    t["r5_mean"] = t["r5_mean"].fillna(np.nan)
    t["amount"] = t["amount"].fillna(0.0)
    t = t.merge(promo, on=["trade_date", "industry"], how="left")
    t = t.merge(lu_daily, on="trade_date", how="left")
    t["mkt_lu"] = t["mkt_lu"].fillna(0)
    t["market_share"] = t["lu_count"] / t["mkt_lu"].clip(lower=1)

    t = t.sort_values(["industry", "trade_date"]).reset_index(drop=True)
    # 成交额增长：amount(t)/mean(amount 前5日) - 1
    t["amount_growth"] = t.groupby("industry")["amount"].transform(
        lambda s: s / s.shift(1).rolling(5, min_periods=2).mean() - 1.0)

    t = _score_themes(t, w)
    # 持续性 & 最终分
    t["raw_score"] = t["raw_score"].fillna(0.0)
    t["persistence"] = t.groupby("industry")["raw_score"].transform(
        lambda s: _weighted_hist(s, pers["weights"]))
    t["persistence"] = t["persistence"].fillna(t["raw_score"])
    t["score"] = (blend * t["raw_score"] + (1 - blend) * t["persistence"]).clip(0, 100)
    return t


def _theme_promotion(daily: pd.DataFrame) -> pd.DataFrame:
    """主题晋级率 = 主题内 昨日封板股中今日仍封板 / 昨日封板股中今日有行情者。

    逐日推进，集合运算，天然处理停牌与题材切换。
    """
    rows: list[dict] = []
    dates = np.sort(daily["trade_date"].unique())
    sealed_by_date: dict[str, pd.DataFrame] = {}
    codes_by_date: dict[str, set] = {}
    for dt, g in daily.groupby("trade_date", sort=True):
        sg = g[g["sealed"]]
        sealed_by_date[str(dt)] = sg
        codes_by_date[str(dt)] = set(g["code"])

    prev_theme_lu: dict[str, set] = {}   # 主题 -> 昨日封板code
    for dt in dates:
        dt = str(dt)
        lu = sealed_by_date.get(dt)
        if lu is None:
            continue
        today_by_theme: dict[str, set] = {}
        for _, r in lu.iterrows():
            today_by_theme.setdefault(str(r["industry"]), set()).add(r["code"])
        codes_today = codes_by_date.get(dt, set())
        themes = set(prev_theme_lu) | set(today_by_theme)
        for th in themes:
            prev = prev_theme_lu.get(th, set())
            cur = today_by_theme.get(th, set())
            avail = prev & codes_today          # 昨日封板、今日有行情
            num = prev & cur
            promo = len(num) / len(avail) if avail else np.nan
            rows.append({"trade_date": dt, "industry": th, "promotion_rate": promo})
        prev_theme_lu = {th: set(codes) for th, codes in today_by_theme.items()}
    return pd.DataFrame(rows)


def _score_themes(t: pd.DataFrame, w: dict) -> pd.DataFrame:
    """按日截面百分位归一 → 加权求和 → raw_score(0~100)。"""
    feat = [
        ("lu_count",       float(w.get("limit_up_count", 20))),
        ("lianban_count",  float(w.get("lianban_count", 10))),
        ("highest_board",  float(w.get("highest_board", 10))),
        ("market_share",   float(w.get("market_share", 10))),
        ("amount_growth",  float(w.get("amount_growth", 15))),
        ("promotion_rate", float(w.get("promotion_rate", 10))),
        ("r3_mean",        float(w.get("ret_3d", 15))),
        ("r5_mean",        float(w.get("ret_5d", 10))),
    ]
    t = t.copy()
    t["raw_score"] = 0.0
    for col, wi in feat:
        if col not in t.columns:
            continue
        vals = t[col].astype(float).fillna(np.nan)
        rank = vals.groupby(t["trade_date"]).rank(pct=True)
        pos_ok = vals.where(vals > 0, np.nan).notna()
        if col in ("lu_count", "lianban_count", "highest_board", "market_share"):
            pos_ok = pd.Series(True, index=t.index)
        score = np.where(pos_ok, rank.fillna(0.5) * wi, 0.0)
        score = np.clip(score, 0.0, wi)
        # 计数类当日至少1家才有意义；无样本(NaN)→ 0
        score = np.where(vals.isna(), 0.0, score)
        t["raw_score"] = t["raw_score"] + score
    total = sum(wi for _, wi in feat)
    if total > 0:
        t["raw_score"] = (t["raw_score"] / total * 100.0).clip(0, 100)
    return t


def _weighted_hist(s: pd.Series, weights: list) -> pd.Series:
    """滚动加权历史(最近权重高)，返回与 s 等长序列。"""
    wts = np.asarray(weights, dtype=float)
    return s.rolling(len(wts), min_periods=2).apply(
        lambda x: float(np.dot(x, wts[:len(x)]) / wts[:len(x)].sum()), raw=True)


def theme_lookup(table: pd.DataFrame) -> dict:
    """(date, industry) -> 行 dict 快速查找。"""
    out: dict = {}
    for _, r in table.iterrows():
        out[(str(r["trade_date"]), str(r["industry"]))] = r.to_dict()
    return out
