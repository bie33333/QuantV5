# -*- coding: utf-8 -*-
"""第三层 · Stock Engine（个股评分）。

候选 = T-1 封板股（T日打板接力对象）。因子（合计100，其中非竞价85 + 竞价15）：
  市场地位20 板块强度15 连板结构10 换手10 量价8 封板质量8
  次日溢价7 资金5 市值2 | 竞价15(T日9:25追加)

注意：所有滚动统计用 shift(1)（不含当日），历史溢价只统计 T+1 已发生的
事件（事件日 < 当日），严格无未来函数。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def enrich_rolling(daily: pd.DataFrame) -> pd.DataFrame:
    """给规范日线附加滚动上下文列（前20日，不含当日）：
       free_turn_med20 / vol_ma20
    """
    d = daily.sort_values(["code", "trade_date"]).copy()
    g = d.groupby("code", sort=False)
    d["free_turn_med20"] = g["free_turnover"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=5).median())
    d["vol_ma20"] = g["vol"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=5).mean())
    return d


def _band(v: float, bands) -> float:
    """bands: [[lo, hi, score], ...]，取 v∈[lo,hi) 的分值。"""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    for lo, hi, sc in bands:
        if lo <= v < hi:
            return float(sc)
    return float(bands[-1][2])


def score_stock(row, ctx: dict, cfg: dict) -> dict:
    """对单只封板股(T-1)计算 85 分制因子分解。

    ctx 键：
      theme_score / theme_persistence / theme_highest / theme_lu_count
      unique_height(bool) / theme_top_amount(bool)
      market_highest(int) / premium(stats dict|None)
    row: 该股在封板日 D 的规范日线行。
    """
    scfg = cfg["stock"]
    w = scfg["weights"]
    parts: dict[str, float] = {}

    board = int(row["board_count"])
    theme_highest = int(ctx.get("theme_highest", board))
    gap = max(theme_highest - board, 0)

    # 1) 市场地位 20
    if gap == 0:
        base = 18.0
    elif gap == 1:
        base = 15.0
    elif gap == 2:
        base = 8.0
    else:
        base = 3.0
    bonus = 0.0
    if gap == 0 and ctx.get("unique_height"):
        bonus = 2.0
    if ctx.get("theme_top_amount") and bonus < 2.0:
        bonus = max(bonus, 2.0)
    parts["market_position"] = float(np.clip(base + bonus, 0, float(w.get("market_position", 20))))

    # 2) 板块强度 15（取自 theme 层 final score）
    ts = float(ctx.get("theme_score", 0) or 0)
    bp = [(50, 6), (60, 9), (70, 11), (80, 13), (90, 15)]
    parts["theme_strength"] = float(_interp(ts, bp))

    # 3) 连板结构 10（结合市场最高板做相对高度修正）
    base_tbl = {int(k): float(v) for k, v in scfg.get("board_structure_base", {}).items()}
    b_score = base_tbl.get(board, 0.0)
    mkt_top = int(ctx.get("market_highest", 0))
    rh = scfg.get("relative_height_penalty", {})
    if mkt_top >= int(rh.get("market_top", 6)) and board <= int(rh.get("stock_below", 3)):
        b_score *= float(rh.get("factor", 0.5))
    parts["board_structure"] = float(np.clip(b_score, 0, float(w.get("board_structure", 10))))

    # 4) 换手结构 10（相对自身20日中位换手）
    med = row.get("free_turn_med20")
    cur = row.get("free_turnover")
    if med is not None and cur is not None and not np.isnan(med) and not np.isnan(cur) and med > 0:
        rt = float(cur) / float(med)
        parts["turnover"] = _band(rt, scfg.get("turnover_bands"))
        if np.isnan(parts["turnover"]):
            parts["turnover"] = 4.0
    else:
        parts["turnover"] = 4.0

    # 5) 量价关系 8（量比 vs 前20日均量，放量合理>极端爆量）
    vr_col = row.get("vol_ma20")
    if vr_col is not None and not np.isnan(vr_col) and vr_col > 0 and row.get("vol"):
        vr = float(row["vol"]) / float(vr_col)
        vb = [(0, 0.5, 3), (0.5, 1.0, 5), (1.0, 2.0, 8), (2.0, 3.5, 7),
              (3.5, 5.0, 4), (5.0, 1e9, 0)]
        parts["volume_price"] = _band(vr, vb)
    else:
        parts["volume_price"] = 4.0

    # 6) 封板质量 8
    parts["board_quality"] = _board_quality(row, scfg)

    # 7) 历史次日溢价 7（事件日严格早于当日）
    parts["next_day_premium"] = _premium_score(ctx.get("premium"), float(w.get("next_day_premium", 7)))

    # 8) 资金结构 5（龙虎榜净买入/成交额；NaN=未上榜中性）
    mf = row.get("money_flow_ratio")
    if mf is None or np.isnan(mf):
        parts["money_flow"] = float(w.get("money_flow", 5)) * 0.5
    elif mf > 0.05:
        parts["money_flow"] = float(w.get("money_flow", 5))
    elif mf > 0.02:
        parts["money_flow"] = float(w.get("money_flow", 5)) * 0.8
    elif mf > 0:
        parts["money_flow"] = float(w.get("money_flow", 5)) * 0.6
    elif mf > -0.02:
        parts["money_flow"] = float(w.get("money_flow", 5)) * 0.3
    else:
        parts["money_flow"] = float(w.get("money_flow", 5)) * 0.1

    # 9) 市值 2（辅助，20~50亿最优）
    mv = row.get("total_mv_yi")
    if mv is None or np.isnan(mv):
        parts["market_cap"] = 1.0
    else:
        sc = _band(float(mv), scfg.get("market_cap_yi"))
        parts["market_cap"] = 2.0 if np.isnan(sc) else sc

    pre = float(sum(parts.values()))
    parts["pre_score"] = pre
    parts["pre_score_pct"] = pre / 85.0 * 100.0
    return parts


def _board_quality(row, scfg: dict) -> float:
    """时间/炸板/封单三块压缩到 8 分；字段缺失时中性化。"""
    time_score = 1.8
    ft = row.get("first_seal_time")
    one_word = bool(row.get("one_word", False))
    if ft is not None and not (isinstance(ft, float) and np.isnan(ft)):
        t = str(ft)[:5]
        if one_word:
            time_score = 2.2
        elif t <= "09:35":
            time_score = 3.5
        elif t <= "10:00":
            time_score = 2.8
        elif t <= "11:00":
            time_score = 2.0
        elif t <= "13:30":
            time_score = 1.2
        elif t <= "14:30":
            time_score = 0.6
        else:
            time_score = 0.0
    elif one_word:
        time_score = 2.2

    bc = row.get("break_count")
    if bc is not None and not (isinstance(bc, float) and np.isnan(bc)):
        bc = int(bc)
        break_score = {0: 3.0, 1: 2.0, 2: 1.0}.get(bc, 0.0)
    else:
        break_score = 2.0

    sr = row.get("seal_ratio")
    if sr is not None and not np.isnan(sr):
        seal_score = 1.5 if sr > 0.3 else (1.0 if sr > 0.15 else (0.6 if sr > 0.05 else 0.3))
    else:
        seal_score = 0.8

    return float(np.clip(time_score + break_score + seal_score, 0.0, 8.0))


def _premium_score(stats, weight: float) -> float:
    """stats: {n, avg_open, avg_high, avg_close, neg_prob}，n<3 中性。"""
    if not stats or stats.get("n", 0) < 3:
        return weight * 0.5
    # 以 T+1 收盘均收益与负收益概率为主，开盘/最高为辅
    avg_c = float(stats.get("avg_close", 0.0))
    neg = float(stats.get("neg_prob", 0.5))
    open_ok = float(stats.get("avg_open", 0.0)) > 0.005
    hi_ok = float(stats.get("avg_high", 0.0)) > 0.03
    if avg_c > 0.02 and neg < 0.3:
        base = 1.0
    elif avg_c > 0.0 and neg < 0.45:
        base = 0.72
    elif avg_c > -0.01:
        base = 0.5
    else:
        base = 0.25
    if open_ok:
        base += 0.15
    if hi_ok:
        base += 0.15
    return float(np.clip(base, 0, 1) * weight)


def _interp(x: float, pts: list[tuple[float, float]]) -> float:
    """分段线性插值（pts 升序）。x<=x0→y0; x>=xn→yn。"""
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x < x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]
