# -*- coding: utf-8 -*-
"""仓位管理与退出规则（经典知行参数集，对应 V3.0 规格 §6 / §7 参数表）。

仓位：
  target = grade_base × 市场情绪乘数(=1.0，经典集不缩放)
         × (exec_p_factor[0] + exec_p_factor[1]*exec_prob)
  硬顶：单票≤single_max、持仓≤max_positions、同题材≤theme_cap、分级硬顶

退出（经典三级出场，每交易日收盘后评估；entry_date == 当日不评估，满足 A股 T+1）：
  先卖约束：一字跌停封死（开=收=跌停 且 振幅<0.2%）→ 无法卖出，顺延
  ① 硬止损    : 当日最低 ≤ 买入价×0.95  → 卖出价 = min(开盘, 买入价×0.95)
  ② 右侧止盈  : 持仓峰值(含当日最高) ≥ 买入价×1.15 且
                当日最低 ≤ 峰值×0.94      → 卖出价 = min(开盘, 峰值×0.94)
  ③ 时间强平  : 持仓 ≥ max_hold_days(15) 个交易日 → 卖出价 = 当日开盘
优先级：止损 > 止盈 > 时间（与 V3.0 表格一致；止损用保守价先触发）。
说明：min(开盘, 触发价) 为日线粒度的可成交近似——开盘已跳空击穿则按开盘价
（更差但真实可达），否则按触发价（价格确实触及该价位）。
"""
from __future__ import annotations

import numpy as np


def grade_of(final_score: float, parts: dict, market_ctx: dict, theme_ctx: dict,
             auction_score: float, cfg: dict) -> str:
    """信号分级：A/B/C（C=只观察不交易）。经典集下 A/B 仓位一致，仅作记录。"""
    if final_score < 70:
        return "C"
    if final_score >= 85:
        strong_mkt = market_ctx["sentiment"] >= 65 and market_ctx["regime"] in ("VERY_STRONG", "STRONG")
        strong_theme = theme_ctx["score"] >= 70
        strong_lead = parts.get("market_position", 0) >= 18
        if strong_mkt and strong_theme and strong_lead:
            return "A"
        return "B"
    if final_score >= 75:
        return "B"
    return "C"


def target_pct(grade: str, exec_prob: float, market_ctx: dict, cfg: dict) -> float:
    """返回目标仓位比例（资金曲线基数 equity_ref）。"""
    pcfg = cfg["position"]
    base = float(pcfg["grade"].get(grade, 0.0))
    mult = float(market_ctx.get("pos_mult", 0.0))
    target = base * mult
    ef = pcfg.get("exec_p_factor", [0.6, 0.4])
    target *= (float(ef[0]) + float(ef[1]) * float(exec_prob))
    cap = float(pcfg["grade_caps"].get(grade, 0.15))
    return float(np.clip(target, 0.0, min(cap, float(pcfg["single_max"]))))


def compute_shares(budget: float, price: float, lot: int = 100) -> int:
    if price <= 0 or budget <= 0:
        return 0
    return int(budget / (price * lot)) * lot


def one_word_limit_down(row) -> bool:
    """一字跌停封死：收盘=跌停价 且 全日振幅 <0.2%（近似 V3.0 开=收=跌停 判据）。"""
    try:
        is_ld = bool(row["is_limit_down"])
    except (KeyError, TypeError):
        is_ld = False
    if not is_ld:
        return False
    pc = float(row["pre_close"]) if row["pre_close"] and row["pre_close"] == row["pre_close"] else 0.0
    if pc <= 0:
        return False
    amp = float(row["high"]) - float(row["low"])
    return amp <= pc * 0.002 + 1e-9


def eval_exit(pos: dict, today_row, cfg: dict) -> dict | None:
    """持仓 pos 在 today 收盘后的三级出场评估。

    today_row: 当日完整日线（open/high/low/close/pre_close/is_limit_down）。
    调用方须先以当日 high 更新 pos["peak_price"]。
    返回 None=继续持有；否则 {'price','reason'}。
    reason: STOP_LOSS | TRAIL_PROFIT | MAX_HOLD
    """
    ecfg = cfg["exit"]

    # 卖出约束：一字跌停封死 → 无法卖出，顺延
    if ecfg.get("sell_one_word_down", True) and one_word_limit_down(today_row):
        return None

    open_p = float(today_row["open"])
    low_p = float(today_row["low"])
    entry = float(pos["entry_price"])
    if entry <= 0:
        return None

    # ① 硬止损
    stop = float(ecfg.get("stop_loss", 0.05))
    stop_px = entry * (1.0 - stop)
    if low_p <= stop_px + 1e-9:
        return {"price": float(min(open_p, stop_px)), "reason": "STOP_LOSS"}

    # ② 右侧止盈（移动止盈）：峰值已 ≥ 触发线 且 自峰值回撤 ≥ 阈值
    trigger = float(ecfg.get("trail_trigger", 0.15))
    drop = float(ecfg.get("trail_drop", 0.06))
    peak = float(pos.get("peak_price") or entry)
    if peak >= entry * (1.0 + trigger) - 1e-9 and low_p <= peak * (1.0 - drop) + 1e-9:
        return {"price": float(min(open_p, peak * (1.0 - drop))), "reason": "TRAIL_PROFIT"}

    # ③ 时间强平
    hold_days = int(pos.get("hold_days", 0))
    max_hold = int(ecfg.get("max_hold_days", 15))
    if hold_days >= max_hold:
        return {"price": float(open_p), "reason": "MAX_HOLD"}

    return None
