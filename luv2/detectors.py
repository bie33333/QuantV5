# -*- coding: utf-8 -*-
"""涨停事件识别层。

- 动态涨停价：按 板块 / ST / 日期规则计算（不写死 10%）
- 事件字段：sealed / touched / one_word / board_count / 封板字段
- 市场情绪原始指标（涨停家数、晋级率、炸板率、昨日涨停收益等）

所有函数均为纯函数 + pandas；trade_date 一律用 "YYYY-MM-DD" 字符串。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .utils import pct_limit, limit_price, limit_down_price

DAILY_COLS = [
    "trade_date", "code", "open", "high", "low", "close", "pre_close",
    "vol", "amount", "turnover_rate", "free_turnover", "total_mv_yi",
    "circ_mv_yi", "limit_up_price", "limit_down_price", "limit_pct",
    "touched", "sealed", "is_limit_down", "one_word",
    "first_seal_time", "break_count", "seal_amount", "seal_ratio",
    "board_count", "industry", "is_st", "name", "board", "money_flow_ratio",
]

FLOAT_FILL = {
    "turnover_rate": 0.0, "free_turnover": 0.0, "total_mv_yi": np.nan,
    "circ_mv_yi": np.nan, "limit_up_price": np.nan, "limit_down_price": np.nan,
    "limit_pct": np.nan,
}


def detect_daily(raw: pd.DataFrame, basic: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """把原始日线(raw) + 股票基础表(basic) 加工成规范日线（含涨停事件列）。

    raw 必需列: trade_date, code, open, high, low, close
    可选列: vol(手), amount(元), turnover_rate(%), free_turnover(%),
            total_mv_yi/circ_mv_yi(亿元, 可缺省), pre_close
    basic 必需列: code, name, board, is_st, industry(题材代理)
    """
    df = raw.copy()
    df["trade_date"] = df["trade_date"].astype(str)
    df["code"] = df["code"].astype(str)

    for c in ["vol", "amount", "turnover_rate", "free_turnover",
              "total_mv_yi", "circ_mv_yi", "pre_close"]:
        if c not in df.columns:
            df[c] = np.nan

    # 合并基础信息
    b = basic[["code", "name", "board", "is_st", "industry"]].copy()
    b["code"] = b["code"].astype(str)
    df = df.merge(b, on="code", how="left")
    df["is_st"] = df["is_st"].fillna(False).astype(bool)
    df["industry"] = df["industry"].fillna("未知").astype(str)
    df["name"] = df["name"].fillna(df["code"])

    df = df.sort_values(["code", "trade_date"]).reset_index(drop=True)

    # 前收盘：缺失时取自身前一行 close（跨股分组）；首日取 open
    g = df.groupby("code", sort=False)["close"]
    prev_close = g.shift(1)
    df["pre_close"] = df["pre_close"].where(df["pre_close"].notna(), prev_close)
    first = df.groupby("code", sort=False).cumcount() == 0
    df.loc[first & df["pre_close"].isna(), "pre_close"] = df.loc[first & df["pre_close"].isna(), "open"]

    # 涨跌停价
    df["limit_pct"] = [
        pct_limit(c, st, cfg, d)
        for c, st, d in zip(df["code"], df["is_st"], df["trade_date"])
    ]
    df["limit_up_price"] = [
        limit_price(pc, pct) for pc, pct in zip(df["pre_close"], df["limit_pct"])
    ]
    df["limit_down_price"] = [
        limit_down_price(pc, pct) for pc, pct in zip(df["pre_close"], df["limit_pct"])
    ]
    eps = 1e-6
    # touched: 盘中触及涨停价；sealed: 收盘封死(收在涨停价)
    df["touched"] = df["high"] >= df["limit_up_price"] - eps
    df["sealed"] = (df["close"] >= df["limit_up_price"] - eps) & df["touched"]
    df["is_limit_down"] = df["close"] <= df["limit_down_price"] + eps
    # 一字板：开=高=低=收=涨停价
    df["one_word"] = (
        df["sealed"]
        & (df["open"] >= df["limit_up_price"] - eps)
        & (df["low"] >= df["limit_up_price"] - eps)
    )

    # 封板质量字段（若 raw 已带则保留；否则 NaN，由 scoring 走中性处理）
    for c in ["first_seal_time", "break_count", "seal_amount", "seal_ratio", "money_flow_ratio"]:
        if c not in df.columns:
            df[c] = np.nan
        else:
            df[c] = df[c]

    # 连板数：仅在其自身连续交易日中“连续封板”才累计
    df["board_count"] = _compute_board_count(df)

    df = df.sort_values(["code", "trade_date"]).reset_index(drop=True)
    return df[DAILY_COLS]


def _compute_board_count(df: pd.DataFrame) -> np.ndarray:
    """逐股滚动：当日 sealed 且与上一根K线为连续交易日时 = 上日count+1，否则重计。

    停牌导致缺K线会自然打断连板链（前一根K线并非上一交易日）。
    """
    codes = df["code"].to_numpy()
    sealed = df["sealed"].to_numpy()
    dates = df["trade_date"].to_numpy()
    # 全局交易日位置索引
    cal = {d: i for i, d in enumerate(np.unique(dates))}
    out = np.zeros(len(df), dtype=np.int64)
    for i in range(len(df)):
        c = codes[i]
        if i > 0 and codes[i - 1] == c:
            prev_pos = cal[dates[i - 1]]
            cur_pos = cal[dates[i]]
            if cur_pos - prev_pos == 1 and sealed[i]:
                out[i] = out[i - 1] + 1
            elif cur_pos - prev_pos == 1 and not sealed[i]:
                out[i] = 0
            elif cur_pos - prev_pos != 1:
                # 停牌缺口：连板链重置（若今日封板则从 1 起）
                out[i] = 1 if sealed[i] else 0
        else:
            out[i] = 1 if sealed[i] else 0
    return out


# ------------------------------------------------------------------
# 市场日度情绪原始指标
# ------------------------------------------------------------------

def market_daily_features(daily: pd.DataFrame) -> pd.DataFrame:
    """由规范日线汇总出每个交易日的市场情绪原始指标（供 market 引擎打分）。

    返回列：
      trade_date, lu_count(封板家数), ld_count(跌停家数),
      lianban_count(>=2板家数), highest_board(最高板),
      promotion_rate(晋级率), break_rate(炸板率),
      y_lu_ret(昨日涨停股今日均收益), y_lb_ret(昨日连板股今日均收益)
    """
    if daily.empty:
        return pd.DataFrame()
    d = daily[daily["sealed"] | daily["touched"] | True].copy()
    # 用每个交易日的全集便于对齐
    dates = np.sort(daily["trade_date"].unique())
    rows = []
    by_date = {dt: g for dt, g in daily.groupby("trade_date", sort=True)}

    prev_lu: set[str] = set()          # 昨日封板股 code
    prev_lb_codes: set[str] = set()    # 昨日连板股(>=2) code
    prev_lu_close: dict[str, float] = {}
    prev_lb_close: dict[str, float] = {}

    for dt in dates:
        g = by_date[dt]
        sealed = g[g["sealed"]]
        lu_codes = set(sealed["code"])
        ld_count = int((g["is_limit_down"]).sum())
        lianban = sealed[sealed["board_count"] >= 2]
        lianban_count = len(lianban)
        highest_board = int(sealed["board_count"].max()) if len(sealed) else 0

        # 晋级率：昨日封板股今日仍封板占比（仅统计今日有行情者）
        today_codes = set(g["code"])
        prev_avail = [c for c in prev_lu if c in today_codes]
        promo = (len(prev_lu & lu_codes) / len(prev_avail)) if prev_avail else np.nan

        # 炸板率：触及涨停但未封死 / 触及家数
        touched = g[g["touched"]]
        n_touched = len(touched)
        n_break = int((touched["sealed"] == False).sum())  # noqa: E712
        break_rate = n_break / n_touched if n_touched else np.nan

        # 昨日涨停/连板股今日收益
        def _avg_ret(codes_set: set[str], closes: dict[str, float]) -> float:
            vals = []
            sub = g[g["code"].isin(codes_set)]
            for _, r in sub.iterrows():
                c0 = closes.get(r["code"])
                if c0 and not np.isnan(r["close"]):
                    vals.append(r["close"] / c0 - 1.0)
            return float(np.mean(vals)) if vals else np.nan

        y_lu_ret = _avg_ret(prev_lu, prev_lu_close)
        y_lb_ret = _avg_ret(prev_lb_codes, prev_lb_close)

        rows.append({
            "trade_date": dt, "lu_count": len(lu_codes), "ld_count": ld_count,
            "lianban_count": lianban_count, "highest_board": highest_board,
            "promotion_rate": promo, "break_rate": break_rate,
            "y_lu_ret": y_lu_ret, "y_lb_ret": y_lb_ret,
        })

        prev_lu = lu_codes
        prev_lb_codes = set(lianban["code"])
        prev_lu_close = {r["code"]: r["close"] for _, r in sealed.iterrows()}
        prev_lb_close = {r["code"]: r["close"] for _, r in lianban.iterrows()}

    return pd.DataFrame(rows)
