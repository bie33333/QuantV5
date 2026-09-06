# -*- coding: utf-8 -*-
"""结果序列化：把回测结果整理成 前端可用的 JSON（数值降维，控制体积）。"""
from __future__ import annotations

import json
import math
from datetime import datetime

import numpy as np
import pandas as pd

from .metrics import compute_metrics, max_drawdown


def _f(x, nd=6):
    if x is None:
        return None
    if isinstance(x, (np.floating, float)):
        if math.isnan(x) or math.isinf(x):
            return None
        return round(float(x), nd)
    if isinstance(x, (np.integer, int)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def to_web(result: dict, cfg: dict, ablation: dict | None = None,
           walk_forward: dict | None = None, bundle=None) -> dict:
    m = compute_metrics(result, cfg)
    eq = result["equity"]
    # 回撤序列
    dd = (eq["equity"].astype(float) / eq["equity"].astype(float).cummax() - 1.0).round(6)
    eq_series = [{"date": str(a), "equity": round(float(b), 2), "drawdown": round(float(c), 6),
                  "sentiment": _f(d), "regime": e, "positions": int(f),
                  "market_ok": _f(g), "cb_on": _f(h)}
                 for a, b, c, d, e, f, g, h in zip(
                     eq["date"], eq["equity"], dd,
                     eq.get("sentiment", [None] * len(eq)),
                     eq.get("regime", [""] * len(eq)),
                     eq.get("positions", [0] * len(eq)),
                     eq.get("market_ok", [None] * len(eq)),
                     eq.get("cb_on", [None] * len(eq)))]
    # 节流：>600 点则抽样
    if len(eq_series) > 600:
        step = math.ceil(len(eq_series) / 600)
        eq_series = eq_series[::step]
        if eq_series[-1] != eq["date"].iloc[-1]:
            eq_series.append(eq_series[-1])

    trades = result["trades"]
    trade_rows = []
    for _, r in trades.iterrows():
        trade_rows.append({
            "pid": int(r["pid"]), "entry_date": str(r["entry_date"]), "code": r["code"],
            "name": r["name"], "theme": r["theme"], "entry_price": _f(r["entry_price"]),
            "shares": int(r["shares"]), "exit_date": str(r["exit_date"] or ""),
            "exit_price": _f(r["exit_price"]), "exit_reason": r["exit_reason"],
            "ret": _f(r["ret"], 5), "net_pnl": _f(r["net_pnl"]),
            "grade": r["grade"], "final_score": _f(r["final_score"]),
            "exec_prob": _f(r["exec_prob"]), "hold_days": int(r["hold_days"]),
            "regime": r["regime_entry"], "sentiment_entry": _f(r["sentiment_entry"]),
            "theme_score": _f(r["theme_score_entry"]),
            "t1_open": _f(r["t1_open"], 5), "t1_close": _f(r["t1_close"], 5),
        })

    orders = result["orders"]
    order_rows = []
    cols = ["date", "code", "name", "industry", "theme_score", "pre_score_pct",
            "auction_score", "auction_ret", "final_score", "outcome", "grade",
            "exec_prob", "final_est"]
    for _, r in orders.iterrows():
        row = {}
        for c in cols:
            row[c] = _f(r[c]) if c in r else None
        order_rows.append(row)
    order_rows.sort(key=lambda x: str(x.get("date", "")), reverse=True)
    if len(order_rows) > 800:
        order_rows = order_rows[:800]

    sent = result.get("sentiment")
    sent_rows = []
    if sent is not None and len(sent):
        for _, r in sent.iterrows():
            sent_rows.append({"date": str(r["trade_date"]), "sentiment": _f(r["sentiment"], 2),
                              "regime": r["regime"], "lu_count": _f(r.get("lu_count")),
                              "ld_count": _f(r.get("ld_count")),
                              "promotion_rate": _f(r.get("promotion_rate"), 4),
                              "break_rate": _f(r.get("break_rate"), 4),
                              "highest_board": _f(r.get("highest_board"))})
        if len(sent_rows) > 800:
            step = math.ceil(len(sent_rows) / 800)
            sent_rows = sent_rows[::step]

    theme = result.get("theme_table")
    theme_dates_sample = []
    if theme is not None and len(theme):
        tdates = sorted(theme["trade_date"].astype(str).unique())
        sample_idx = list(range(0, len(tdates), max(1, len(tdates) // 24)))
        for di in sample_idx:
            dt = tdates[di]
            sub = theme[theme["trade_date"] == dt].sort_values("score", ascending=False).head(8)
            theme_dates_sample.append({
                "date": dt,
                "themes": [{"name": str(r["industry"]), "score": _f(r["score"], 1),
                            "persistence": _f(r["persistence"], 1),
                            "lu_count": int(r["lu_count"]), "highest": int(r["highest_board"])}
                           for _, r in sub.iterrows()],
            })
        if len(theme_dates_sample) == 0 and len(tdates):
            pass

    notes = []
    if bundle is not None:
        notes = list(bundle.notes)
    notes.append("日线粒度近似：真实数据源下 首封时间/炸板/封单/龙虎榜/竞价 等高频字段缺失或为估计值，对应因子走中性处理；"
                 "成交概率为日线代理模型（非 Level-2 排队深度）。")
    notes.append("交易/风控规则 = 经典知行参数集：单票40%/最多2只/硬止损5%/右侧移动止盈(触发15%、回撤6%)/"
                 "持有≤15日/账户回撤熔断12%(清仓空仓，指数站回MA20恢复)/弱市空仓(指数≤MA20)/连板晋级率≥30%。")
    notes.append("出场价为日线可达价近似：止损与移动止盈=min(开盘, 触发价)（跳空击穿按开盘价，保守且真实可达）；"
                 "时间强平=当日开盘；熔断清仓=当日收盘价（与记账口径一致）。一字跌停封死当日无法卖出、顺延。")
    notes.append("回测使用事件驱动：信号只用 T-1 收盘前数据；竞价用 T 开盘；成交模拟用 T 盘内；严禁跨日未来函数。")
    notes.append("本系统为研究与教学用途；回测结果 ≠ 未来收益，打板策略受排队/滑点/撤单/监管与交易规则变化影响，实盘需谨慎。")

    cb_rows = []
    cb = result.get("circuit_breakers")
    if cb is not None and len(cb):
        for _, r in cb.iterrows():
            cb_rows.append({"date": str(r["date"]), "equity": _f(r["equity"]),
                            "peak": _f(r["peak"]), "drawdown": _f(r["drawdown"], 4)})

    return {
        "meta": {
            "model": cfg["meta"]["model_name"],
            "version": cfg["meta"]["version"],
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "start": cfg["backtest"]["start"],
            "end": cfg["backtest"]["end"],
            "source": (bundle.source if bundle else cfg["data"]["source"]),
            "config": {
                "stock_min_score": cfg["stock"]["min_score"],
                "theme_min_score": cfg["theme"]["min_score"],
                "auction_min_score": cfg["auction"].get("min_score", 6.0),
                "exec_min_prob": cfg["execution"]["min_exec_prob"],
                "single_max": cfg["position"]["single_max"],
                "max_positions": cfg["position"]["max_positions"],
                "theme_cap": cfg["position"]["theme_cap"],
                "initial_capital": cfg["position"]["initial_capital"],
                "regimes": cfg["market"]["regimes"],
                "weights_stock": cfg["stock"]["weights"],
                "weights_market": cfg["market"]["weights"],
                "exit": {
                    "stop_loss": cfg["exit"].get("stop_loss", 0.05),
                    "trail_trigger": cfg["exit"].get("trail_trigger", 0.15),
                    "trail_drop": cfg["exit"].get("trail_drop", 0.06),
                    "max_hold_days": cfg["exit"].get("max_hold_days", 15),
                },
                "circuit_breaker": cfg.get("circuit_breaker", {}),
                "market_filter": cfg["market"].get("filter", {}),
            },
        },
        "metrics": m,
        "equity": eq_series,
        "sentiment": sent_rows,
        "theme_samples": theme_dates_sample,
        "trades": trade_rows,
        "orders": order_rows,
        "ablation": ablation,
        "walk_forward": walk_forward,
        "circuit_breakers": cb_rows,
        "notes": notes,
    }


def dump_json(obj: dict, path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
