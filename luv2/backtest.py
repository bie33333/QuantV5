# -*- coding: utf-8 -*-
"""事件驱动回测引擎（经典知行风控参数集版）。

每日循环（先卖后买，卖出约束优先）：
  d 开盘 : 执行昨日候选（竞价 → 终版评分 → 闸门 → 模拟排板/成交）
  d 收盘前 : 持仓三级出场评估（硬止损 / 右侧移动止盈 / 时间强平）
  d 收盘后 : 组合熔断检查（账户权益自峰值回撤 ≥ 阈值 → 清仓空仓，
             等权指数重新站上 MA20 → 解除熔断并重置权益峰值基线）
  d 收盘 : 候选生成（明日打板；受 弱市空仓(指数≤MA20) + 连板晋级率≥30% 硬闸门约束）
严格数据边界：信号只用 ≤d-1 收盘数据；竞价用 d 开盘；出场/熔断用 d 盘内/收盘；
任何跨日收益标签不得进入信号。

开仓硬闸门（gates.market=True 时生效）：
  ① 弱市空仓 : 等权指数(全组合收盘均值收益累积) ≤ MA20 → 不交易
  ② 晋级率  : 昨日涨停股今日续板占比 ≥ threshold(0.30) → 否则不交易
  ③ 熔断    : 触发后空仓等待，指数站回 MA20 上方才恢复
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engines.auction import auction_score
from .engines.stock import enrich_rolling, score_stock
from .execution import buy_cost, decide_fill, estimate_fill, sell_cost
from .sources import DataBundle
from .strategy_rules import compute_shares, eval_exit, grade_of, one_word_limit_down, target_pct


@dataclass
class GateCfg:
    """消融开关：Model A/B/C/D"""
    market: bool = True
    theme: bool = True
    leadership: bool = True
    auction: bool = True
    exec_gate: bool = True
    allow_c: bool = True          # 70~75 分允许以半仓(B档)参与（基线；正式阈值75）
    min_score: float | None = None
    min_leadership: float | None = None


# ----------------------------------------------------------------------
# 市场闸门辅助（等权指数 + 连板晋级率）
# ----------------------------------------------------------------------

def _market_filter_cfg(cfg: dict) -> dict:
    return cfg.get("market", {}).get("filter", {}) or {}


def index_above_ma_map(daily: pd.DataFrame, period: int = 20) -> dict[str, bool]:
    """等权价格指数代理：逐日全组合收盘价均值 → MA(period) → 是否站上。

    采用「收盘价均值」而非「收益复利」，与市场通用指数(价格水平+均线)口径一致。
    合成数据价格整体上行(均值含涨停复利效应)，MA20 跟随价格水平，仅在快速回撤
    段给出「指数≤MA20 → 弱市不交易」信号。真实数据源建议后续接入官方指数行情
    (如 510300/000001.SH)，本代理作为无指数源时的近似。
    """
    d = daily[daily["close"].notna()]
    if len(d) == 0:
        return {}
    lvl = d.groupby("trade_date")["close"].mean().sort_index()
    ma = lvl.rolling(period, min_periods=period).mean()
    out: dict[str, bool] = {}
    for dt in lvl.index:
        lv = float(lvl.loc[dt])
        mv = ma.loc[dt]
        out[str(dt)] = bool(pd.notna(mv) and lv > mv)
    return out


def promotion_rate_map(market_df: pd.DataFrame) -> dict[str, float]:
    """trade_date -> 连板晋级率（昨日涨停今日续板占比）；缺失/NaN → 0.0。"""
    if market_df is None or len(market_df) == 0:
        return {}
    out: dict[str, float] = {}
    for _, r in market_df.iterrows():
        v = r.get("promotion_rate")
        out[str(r["trade_date"])] = 0.0 if (v is None or pd.isna(v)) else float(v)
    return out


# ----------------------------------------------------------------------
# 次日溢价（历史事件统计，仅供选股打分）
# ----------------------------------------------------------------------

def build_premium_map(daily: pd.DataFrame) -> dict:
    """每股历史涨停事件的次日表现（只含已发生的下一交易日bar）。

    返回 code -> [ {e_date, n_date, open_ret, high_ret, close_ret} ... ]
    """
    d2 = daily.sort_values(["code", "trade_date"]).copy()
    g = d2.groupby("code", sort=False)
    for col, src in [("n_date", "trade_date"), ("n_open", "open"), ("n_high", "high"),
                     ("n_close", "close")]:
        d2[col] = g[src].shift(-1)
    ev = d2[d2["sealed"]].dropna(subset=["n_date"])
    out: dict[str, list] = {}
    for _, r in ev.iterrows():
        e_close = float(r["close"])
        if e_close <= 0:
            continue
        rec = {
            "e_date": str(r["trade_date"]), "n_date": str(r["n_date"]),
            "open_ret": float(r["n_open"]) / e_close - 1.0,
            "high_ret": float(r["n_high"]) / e_close - 1.0,
            "close_ret": float(r["n_close"]) / e_close - 1.0,
        }
        out.setdefault(str(r["code"]), []).append(rec)
    for k in out:
        out[k].sort(key=lambda x: x["n_date"])
    return out


def premium_stats(premium_map: dict, code: str, upto_date: str) -> dict | None:
    entries = [e for e in premium_map.get(code, []) if e["n_date"] <= upto_date]
    if not entries:
        return None
    return {
        "n": len(entries),
        "avg_open": float(np.mean([e["open_ret"] for e in entries])),
        "avg_high": float(np.mean([e["high_ret"] for e in entries])),
        "avg_close": float(np.mean([e["close_ret"] for e in entries])),
        "neg_prob": float(np.mean([1.0 if e["close_ret"] < 0 else 0.0 for e in entries])),
    }


# ----------------------------------------------------------------------
# 主回测
# ----------------------------------------------------------------------

def _close_position(p: dict, d: str, px: float, reason: str, cash: float,
                    trades: list) -> float:
    """按价格 px 平仓 p；返回更新后的 cash。"""
    proceeds = p["shares"] * px
    scost = sell_cost(proceeds, p["_cfg"])
    net = proceeds - scost - p["entry_cash"]
    p.update(status="closed", exit_date=d, exit_price=px, exit_reason=reason,
             net_pnl=net, ret=net / p["entry_cash"] if p["entry_cash"] else 0.0,
             sell_cost=scost)
    trades.append({**{k: p[k] for k in ("pid", "code", "name", "theme", "entry_date",
                                        "entry_price", "shares", "entry_cash", "exit_date",
                                        "exit_price", "exit_reason", "ret", "net_pnl",
                                        "grade", "final_score", "exec_prob", "t1_open",
                                        "t1_close", "regime_entry", "sentiment_entry",
                                        "theme_score_entry", "hold_days")},
                   "parts": p["parts"]})
    return cash + proceeds - scost


def run_backtest(bundle: DataBundle, cfg: dict, gates: GateCfg | None = None,
                 label: str = "D", rng_seed: int | None = None) -> dict:
    """运行一次事件驱动回测，返回结果 dict（供 metrics/report 使用）。"""
    gates = gates or GateCfg()
    scfg = cfg["stock"]
    bcfg = cfg["backtest"]
    pcfg = cfg["position"]
    rng = np.random.RandomState(rng_seed if rng_seed is not None
                                 else int(cfg["execution"].get("rng_seed", 20260906)))

    # ---- 市场闸门（基于全历史构造，避免窗口起点 MA 缺失）----
    mf = _market_filter_cfg(cfg)
    ma_period = int((mf.get("index") or {}).get("ma_period", 20))
    above_ma = index_above_ma_map(bundle.daily, ma_period)
    promo_map = promotion_rate_map(bundle.market)
    promo_cfg = (mf.get("limit_up_promotion") or {})
    promo_enabled = bool(promo_cfg.get("enabled", False))
    promo_thr = float(promo_cfg.get("min_promote_ratio", 0.30))

    daily = enrich_rolling(bundle.daily)
    daily = daily[daily["trade_date"].between(bcfg["start"], bcfg["end"])].copy()
    if daily.empty:
        return {"empty": True}
    dates = np.sort(daily["trade_date"].unique())
    by_date: dict[str, pd.DataFrame] = {}
    for dt, g in daily.groupby("trade_date", sort=True):
        by_date[str(dt)] = g.set_index("code", drop=False)
    idx_map = {d: i for i, d in enumerate(dates)}

    # 市场情绪 / 板块表
    sent = bundle.sentiment.set_index("trade_date")
    sent_map = {str(d): row for d, row in sent.iterrows()}
    theme_table = bundle.theme_table
    theme_lu = {}
    for _, r in theme_table.iterrows():
        theme_lu[(str(r["trade_date"]), str(r["industry"]))] = r

    premium_map = build_premium_map(daily)
    warmup = max(60, int(cfg["market"].get("adaptive_window", 60)))

    # 账户
    cash = float(pcfg["initial_capital"])
    equity_prev = float(pcfg["initial_capital"])
    positions: list[dict] = []
    orders: list[dict] = []       # 上一日形成、今日待执行
    trades: list[dict] = []
    orders_log: list[dict] = []   # 全部候选+结果（含未成交）
    equity_curve: list[dict] = []
    daily_stats: list[dict] = []
    cb_events: list[dict] = []
    pid = 0
    min_score = gates.min_score if gates.min_score is not None else float(scfg.get("min_score", 75))
    min_lead = gates.min_leadership if gates.min_leadership is not None \
        else float(scfg.get("min_leadership", 8))

    # 组合熔断状态
    cb_cfg = cfg.get("circuit_breaker", {}) or {}
    cb_enabled = bool(cb_cfg.get("enabled", True))
    cb_dd = float(cb_cfg.get("max_dd_exit", 0.12))
    cb_on = False
    equity_peak = float(pcfg["initial_capital"])

    def _entry_gate_ok(d: str) -> tuple[bool, bool, bool]:
        """当日是否允许开新仓 → (弱市/晋级率达标, 熔断未触发, 最终可开仓)。"""
        mkt_ok = True
        if gates.market and mf.get("enabled", True):
            ok_ma = above_ma.get(d, False)
            ok_pr = (not promo_enabled) or (promo_map.get(d, 0.0) >= promo_thr)
            mkt_ok = bool(ok_ma and ok_pr)
        gate_ok = mkt_ok and (not cb_on)
        return mkt_ok, (not cb_on), gate_ok

    for d in dates:
        gd = by_date[d]
        smap = sent_map.get(d)
        if smap is None:
            # 数据缺市场情绪行时以中性值记账
            smap = {"sentiment": 50.0, "regime": "NORMAL", "permission": True, "pos_mult": 1.0,
                    "lu_count": 0, "highest_board": 0}
        sentiment_now = float(smap["sentiment"])
        regime_now = str(smap["regime"])

        # ---------- a) 竞价 + 执行（昨日候选） ----------
        pending = orders
        orders = []
        pending.sort(key=lambda o: o["final_est"], reverse=True)
        for o in pending:
            code = o["code"]
            rec = {"date": d, **{k: o.get(k) for k in ("code", "name", "industry", "theme_score",
                                                       "pre_score", "pre_score_pct")}}
            if code not in gd.index:
                rec.update(outcome="no_bar")
                orders_log.append(rec)
                continue
            row = gd.loc[code]
            # 竞价
            ar = float(row["open"]) / float(row["pre_close"]) - 1.0 if row["pre_close"] else 0.0
            auc = auction_score(ar, cfg)
            if gates.auction and (auc["hard_reject"] or auc["auction_score"] < float(cfg["auction"].get("min_score", 6.0))):
                rec.update(outcome="auction_reject", auction_score=auc["auction_score"],
                           auction_ret=ar, final_est=o["final_est"])
                orders_log.append(rec)
                continue
            final_score = o["pre_score"] + (auc["auction_score"] if gates.auction else 0.0)
            if not gates.auction:
                final_score = o["pre_score_pct"]          # 无竞价模型用 0~100 折算
            rec.update(final_score=final_score, auction_score=auc["auction_score"] if gates.auction else 15.0)
            if final_score < min_score:
                rec.update(outcome="low_score")
                orders_log.append(rec)
                continue
            # 板块闸门（安全兜底，形成时已查）
            tkey = (o["p_date"], o["industry"])
            tro = theme_lu.get(tkey)
            if gates.theme and (tro is None or float(tro["score"]) < float(cfg["theme"].get("min_score", 50))):
                rec.update(outcome="theme_gate")
                orders_log.append(rec)
                continue
            # 成交模拟
            est = estimate_fill(row, auc, cfg, rng)
            prob = est["prob"]
            if gates.exec_gate and prob < float(cfg["execution"].get("min_exec_prob", 0.3)):
                rec.update(outcome="exec_low", exec_prob=prob, reason=est["reason"])
                orders_log.append(rec)
                continue
            # 信号分级 & 仓位
            mkt_ctx = {"sentiment": float(o.get("sentiment_p", 50.0)), "regime": o["regime_p"],
                       "pos_mult": float(o["pos_mult_p"])}
            grade = grade_of(final_score, o["parts"], mkt_ctx, {"score": o["theme_score"]},
                             auc["auction_score"] if gates.auction else 15.0, cfg)
            if grade == "C":
                if not gates.allow_c:
                    rec.update(outcome="observe_C", grade="C", final_score=final_score)
                    orders_log.append(rec)
                    continue
                grade = "B"   # 裸模型近似：≥70 即可买
            if not gates.market:
                mkt_ctx = {"sentiment": 70.0, "regime": "STRONG", "pos_mult": 1.0}
            target = target_pct(grade, prob, mkt_ctx, cfg)
            price = est["price"]
            equity_base = equity_prev
            # 主题仓位上限（仅统计在持）
            theme_expo = sum(p["shares"] * price for p in positions
                             if p["status"] == "open" and p["theme"] == o["industry"])
            budget = min(cash, equity_base * target)
            budget = min(budget, max(equity_base * float(pcfg["theme_cap"]) - theme_expo, 0.0))
            budget = min(budget, cash)
            shares = compute_shares(budget, price, int(pcfg.get("lot_size", 100)))
            n_pos = len([p for p in positions if p.get("status") == "open"])
            if shares <= 0 or n_pos >= int(pcfg.get("max_positions", 2)):
                rec.update(outcome="no_cash")
                orders_log.append(rec)
                continue
            if any(p["status"] == "open" and p["code"] == code for p in positions):
                rec.update(outcome="dup_position")
                orders_log.append(rec)
                continue
            if gates.exec_gate:
                filled, ratio = decide_fill(prob, rng)
            else:
                filled, ratio = True, 1.0     # 无成交模拟：涨停即买入（v1 近似）
            if not filled:
                rec.update(outcome="no_fill", exec_prob=prob)
                orders_log.append(rec)
                continue
            if ratio < 1.0:
                shares = int(shares * ratio // int(pcfg.get("lot_size", 100))) * int(pcfg.get("lot_size", 100))
                if shares <= 0:
                    rec.update(outcome="no_fill_partial", exec_prob=prob)
                    orders_log.append(rec)
                    continue
            cost = buy_cost(shares * price, cfg)
            if shares * price + cost > cash + 1e-6:
                rec.update(outcome="no_cash")
                orders_log.append(rec)
                continue
            pid += 1
            pos = {
                "pid": pid, "code": code, "name": o["name"], "theme": o["industry"],
                "entry_date": d, "entry_price": price, "shares": shares,
                "entry_cash": shares * price + cost, "cost": cost,
                "grade": grade, "exec_prob": float(prob), "final_score": float(final_score),
                "parts": o["parts"], "regime_entry": regime_now,
                "sentiment_entry": sentiment_now, "theme_score_entry": float(o["theme_score"]),
                "exit_date": None, "exit_price": None, "exit_reason": None,
                "hold_days": 0, "status": "open", "t1_open": None, "t1_close": None,
                "peak_price": float(price), "_cfg": cfg,
            }
            cash -= shares * price + cost
            positions.append(pos)
            rec.update(outcome="filled", shares=shares, price=price, exec_prob=prob, grade=grade)
            orders_log.append(rec)

        # ---------- b) 出场评估（经典三级；持仓须早于今日入场，满足 T+1） ----------
        for p in positions:
            if p["status"] != "open" or p["entry_date"] == d:
                continue
            hd = idx_map[d] - idx_map[p["entry_date"]]
            p["hold_days"] = hd
            row = by_date[d].loc[p["code"]] if p["code"] in by_date[d].index else None
            if row is None:
                continue
            # 记录 T+1 参照（用于评价指标，不参与决策）
            if hd == 1:
                p["t1_open"] = float(row["open"]) / p["entry_price"] - 1.0
                p["t1_close"] = float(row["close"]) / p["entry_price"] - 1.0
            # 峰值跟踪（含当日 high；用于右侧移动止盈）
            p["peak_price"] = max(float(p.get("peak_price") or p["entry_price"]),
                                  float(row["high"]))
            ex = eval_exit(p, row, cfg)
            if ex is not None:
                cash = _close_position(p, d, float(ex["price"]), ex["reason"], cash, trades)

        # ---------- c) 组合熔断（账户权益自峰值回撤 ≥ 阈值 → 清仓空仓） ----------
        def _m2m() -> float:
            mv = 0.0
            for p in positions:
                if p["status"] != "open":
                    continue
                r = by_date[d].loc[p["code"]] if p["code"] in by_date[d].index else None
                mv += p["shares"] * (float(r["close"]) if r is not None else p["entry_price"])
            return cash + mv

        eq_m2m = _m2m()
        if cb_enabled:
            if not cb_on:
                equity_peak = max(equity_peak, eq_m2m)
                if equity_peak > 0 and eq_m2m <= equity_peak * (1.0 - cb_dd) + 1e-9:
                    cb_on = True
                    cb_events.append({"date": d, "equity": round(eq_m2m, 2),
                                      "peak": round(equity_peak, 2),
                                      "drawdown": round(eq_m2m / equity_peak - 1.0, 6)})
                    # 全部清仓（一字跌停封死或当日新买入(T+1规则)无法卖出者顺延）
                    for p in [x for x in positions
                              if x["status"] == "open" and x["entry_date"] != d]:
                        r = by_date[d].loc[p["code"]] if p["code"] in by_date[d].index else None
                        if r is None or one_word_limit_down(r):
                            continue
                        cash = _close_position(p, d, float(r["close"]), "CIRCUIT_BREAKER",
                                               cash, trades)
            else:
                # 熔断解除：等权指数重新站上 MA20（同时重置权益峰值基线）
                if above_ma.get(d, False):
                    cb_on = False
                    eq_now = _m2m()
                    equity_peak = eq_now

        # ---------- d) 候选生成（今日封板 → 明日打板；受市场硬闸门约束） ----------
        mkt_ok, _cb_free, entry_ok = _entry_gate_ok(d)
        if idx_map[d] >= warmup and entry_ok:
            sealed = gd[gd["sealed"]]
            lu_by_theme: dict[str, list] = {}
            market_highest = 0
            for _, r in sealed.iterrows():
                th = str(r["industry"])
                lu_by_theme.setdefault(th, []).append(r)
                market_highest = max(market_highest, int(r["board_count"]))
            for th, rows in lu_by_theme.items():
                tro = theme_lu.get((d, th))
                theme_score = float(tro["score"]) if tro is not None else 0.0
                if gates.theme and theme_score < float(cfg["theme"].get("min_score", 50)):
                    continue
                board_vals = [int(r["board_count"]) for r in rows]
                theme_highest = max(board_vals)
                unique_h = board_vals.count(theme_highest) == 1
                amts = {str(r["code"]): float(r["amount"]) for r in rows}
                top_amt_code = max(amts, key=amts.get) if amts else None
                rows_sorted = sorted(rows, key=lambda r: -int(r["board_count"]))
                for r in rows_sorted:
                    code = str(r["code"])
                    if bool(r["is_st"]):
                        continue
                    if float(r["close"]) < float(cfg["data"]["universe"].get("min_price", 3)):
                        continue
                    # 流动性下限：成交额过小不参与
                    if float(r["amount"]) < 5e7:
                        continue
                    if int(r["board_count"]) >= 6:
                        continue
                    premium = premium_stats(premium_map, code, d)
                    ctx = {"theme_score": theme_score, "theme_highest": theme_highest,
                           "theme_lu_count": len(rows), "unique_height": unique_h,
                           "theme_top_amount": code == top_amt_code,
                           "market_highest": market_highest, "premium": premium}
                    parts = score_stock(r, ctx, cfg)
                    lead = parts.get("market_position", 0)
                    if gates.leadership and lead < min_lead:
                        continue
                    o_pos_mult = float(smap["pos_mult"]) if gates.market else 1.0
                    orders.append({
                        "code": code, "name": str(r["name"]), "industry": th,
                        "p_date": d, "parts": parts,
                        "pre_score": parts["pre_score"],
                        "pre_score_pct": parts["pre_score_pct"],
                        "theme_score": theme_score,
                        "board_count": int(r["board_count"]),
                        "final_est": parts["pre_score_pct"],
                        "regime_p": "STRONG" if not gates.market else regime_now,
                        "pos_mult_p": o_pos_mult,
                        "sentiment_p": 70.0 if not gates.market else sentiment_now,
                    })

        # ---------- e) 收盘记账 ----------
        live = [p for p in positions if p["status"] == "open"]
        m2m = 0.0
        for p in live:
            row = by_date[d].loc[p["code"]] if p["code"] in by_date[d].index else None
            m2m += p["shares"] * (float(row["close"]) if row is not None else p["entry_price"])
        equity = cash + m2m
        equity_curve.append({"date": d, "equity": equity, "cash": cash,
                             "positions": len(live),
                             "exposure": (m2m / equity if equity else 0.0),
                             "sentiment": sentiment_now, "regime": regime_now,
                             "lu_count": int(smap.get("lu_count", 0)),
                             "market_ok": bool(mkt_ok), "cb_on": bool(cb_on),
                             "above_ma": bool(above_ma.get(d, False)),
                             "promo_rate": promo_map.get(d)})
        daily_stats.append({"date": d, "orders": len(orders),
                            "open_positions": len(live)})
        equity_prev = equity

    return {
        "label": label, "equity": pd.DataFrame(equity_curve), "trades": pd.DataFrame(trades),
        "orders": pd.DataFrame(orders_log), "daily_stats": pd.DataFrame(daily_stats),
        "sentiment": bundle.sentiment, "theme_table": bundle.theme_table,
        "circuit_breakers": pd.DataFrame(cb_events),
        "empty": False,
    }


def prepare_bundle(bundle: DataBundle, cfg: dict) -> DataBundle:
    """给 bundle 附加 sentiment / theme_table（由 engines 计算一次，供多轮复用）。"""
    if getattr(bundle, "sentiment", None) is None:
        from .engines.market import compute_sentiment
        bundle.sentiment = compute_sentiment(bundle.market, cfg)
    if getattr(bundle, "theme_table", None) is None:
        from .engines.theme import build_theme_table
        bundle.theme_table = build_theme_table(bundle.daily, cfg)
    return bundle
