# -*- coding: utf-8 -*-
"""通用小工具：A股价格四舍五入 / 板块判定 / 常量。"""
from __future__ import annotations

import math


def round_price(x: float, tick: float = 0.01) -> float:
    """按最小变动价位四舍五入（A股报价四舍五入到分，规避 Python banker's rounding）。"""
    n = round(1.0 / tick)
    return math.floor(x * n + 0.5) / n


def infer_board(code: str) -> str:
    """按代码前缀推断板块，返回受限枚举字符串。"""
    code = code.split(".")[0]
    if code.startswith(("688", "689")):
        return "STAR"            # 科创板
    if code.startswith(("300", "301")):
        return "GEM"             # 创业板
    if code.startswith(("8", "4", "92")):
        return "BJ"              # 北交所
    if code.startswith(("60", "68")):
        return "MAIN_SH"
    return "MAIN_SZ"             # 00/001/002/003 深主板


def is_star(code: str) -> bool:
    return infer_board(code) == "STAR"


def pct_limit(code: str, is_st: bool, cfg: dict, trade_date: str | None = None) -> float:
    """根据 板块 / ST状态 / 日期 动态返回涨跌幅限制（规则参数化，不硬编码）。"""
    rules = cfg.get("limit_rules", {})
    board = infer_board(code)
    if board == "STAR":
        return float(rules.get("star", 0.20))
    if board == "GEM":
        return float(rules.get("gem", 0.20))
    if board == "BJ":
        return float(rules.get("bj", 0.30))
    if is_st:
        # 上交所主板风险警示 2026-07-06 起 10%；其余主板 ST 维持 5%（近似）
        eff_date = rules.get("st_main_sse_date", "2026-07-06")
        if board == "MAIN_SH" and trade_date and trade_date >= eff_date:
            return float(rules.get("st_main", 0.10))
        return float(rules.get("st_main", 0.05))
    return float(rules.get("main", 0.10))


def limit_price(pre_close: float, pct: float, tick: float = 0.01) -> float:
    """涨停价 = round(pre_close * (1+pct), tick)。"""
    return round_price(pre_close * (1.0 + pct), tick)


def limit_down_price(pre_close: float, pct: float, tick: float = 0.01) -> float:
    return round_price(pre_close * (1.0 - pct), tick)


def trading_minutes() -> list[str]:
    """A股连续竞价分钟序列 09:31-11:30 / 13:01-15:00（用于分钟级标识）。"""
    out: list[str] = []
    for hh in range(9, 12):
        for mm in range(0, 60):
            t = f"{hh:02d}:{mm:02d}"
            if t < "09:31" or ("11:31" <= t <= "12:59"):
                continue
            out.append(t)
    for hh in range(13, 16):
        for mm in range(0, 60):
            t = f"{hh:02d}:{mm:02d}"
            if t >= "15:01":
                continue
            out.append(t)
    return out


def to_minutes_int(t: str) -> int:
    """HH:MM -> 分钟数（当天 0 点起）"""
    hh, mm = t.split(":")
    return int(hh) * 60 + int(mm)
