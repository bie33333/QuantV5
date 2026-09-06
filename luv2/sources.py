# -*- coding: utf-8 -*-
"""数据源适配层。

- SyntheticSource : 内置合成数据生成器。按 A 股规则合成完整日线 + 涨停事件
                    （首封时间/炸板/封单/一字/龙虎榜/题材），用于无 token 时
                    端到端跑通全流水线（字段可靠性 = SIM）。
- TushareSource   : 真实数据（daily / daily_basic / stock_basic 按日全市场拉取，
                    本地缓存可续传）。涨停价/一字/封板等高频字段由日线估计
                    （seal/event 字段 NaN → 引擎中性处理；可靠性 = EST/NA）。
                    token: 环境变量 TUSHARE_TOKEN 或 config.data.tushare.token。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .detectors import DAILY_COLS, detect_daily, market_daily_features
from .utils import infer_board, limit_price, pct_limit, round_price

THEMES = [
    "机器人", "通信/光模块", "半导体", "AI应用", "低空经济", "医药生物",
    "军工", "汽车零部件", "有色金属", "电力设备/储能", "基础化工", "消费电子",
]


@dataclass
class DataBundle:
    """数据打包：basic + 规范日线 + 市场日度原始指标。"""
    basic: pd.DataFrame
    daily: pd.DataFrame
    market: pd.DataFrame          # market_daily_features 输出（原始指标，未打分）
    notes: list = field(default_factory=list)
    source: str = "synthetic"
    sentiment: pd.DataFrame | None = None     # prepare_bundle 填充
    theme_table: pd.DataFrame | None = None   # prepare_bundle 填充


# ----------------------------------------------------------------------
# 合成源
# ----------------------------------------------------------------------

class SyntheticSource:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        scfg = cfg["data"]["synthetic"]
        self.rng = np.random.RandomState(int(scfg.get("seed", 20260906)))

    def load(self) -> DataBundle:
        scfg = self.cfg["data"]["synthetic"]
        start = str(scfg.get("start", "2023-01-02"))
        end = str(scfg.get("end", "2025-12-31"))
        calendar = _trading_calendar(start, end)
        basic = self._make_basic(int(scfg.get("n_stocks", 240)))
        daily = self._simulate(calendar, basic)
        daily["board_count"] = _compute_board_count_simple(daily)
        market = market_daily_features(daily)
        notes = [
            "数据源: synthetic 合成数据（含涨停事件/竞价/封单等全字段，可靠性=SIM）",
            f"股票数 {len(basic)}，交易日 {len(calendar)}（{start} ~ {end}，按自然交易日近似，未对齐真实节假日）",
        ]
        return DataBundle(basic=basic, daily=daily, market=market, notes=notes, source="synthetic")

    # ---------------- 基础表 ----------------
    def _make_basic(self, n: int) -> pd.DataFrame:
        rng = self.rng
        rows = []
        prefix_pool = ["000", "001", "002", "300", "600", "601", "603", "688"]
        used = set()
        name_syl = ["华", "中", "科", "创", "云", "天", "海", "泰", "瑞", "金",
                    "盛", "东", "新", "博", "亚", "光", "信", "联", "达", "恒"]
        for i in range(n):
            while True:
                p = prefix_pool[i % len(prefix_pool)]
                code = p + f"{rng.randint(0, 9999):04d}"
                if code not in used:
                    used.add(code)
                    break
            board = infer_board(code)
            is_st = rng.rand() < 0.05
            nm = "".join(rng.choice(name_syl, 2)) + ("科技" if rng.rand() < 0.5 else "股份")
            if is_st:
                nm = "ST" + nm
            theme = THEMES[rng.randint(0, len(THEMES))]
            rows.append({
                "code": code, "name": nm, "board": board, "is_st": is_st,
                "industry": theme, "list_date": "2022-01-01",
            })
        return pd.DataFrame(rows)

    # ---------------- 日线模拟 ----------------
    def _simulate(self, calendar: list[str], basic: pd.DataFrame) -> pd.DataFrame:
        rng = self.rng
        cfg = self.cfg
        n_stocks = len(basic)
        base_price = rng.uniform(6, 45, n_stocks)
        mv_yi = rng.uniform(18, 160, n_stocks)          # 总市值(亿元)
        circ_ratio = rng.uniform(0.4, 0.95, n_stocks)
        q = rng.uniform(0, 1, n_stocks)                  # 个股"股性"持久因子
        beta_theme = rng.uniform(0.5, 1.3, n_stocks)

        theme_idx = {t: i for i, t in enumerate(THEMES)}
        stock_theme = np.array([theme_idx[x] for x in basic["industry"]])
        n_theme = len(THEMES)

        # 题材热度潜变量（随机游走 + 主升浪片段）
        th = np.full((len(calendar), n_theme), np.nan)
        hot_episode: dict[int, tuple[int, int, float]] = {}  # theme -> (start,end,intensity)
        # 市场情绪潜变量（生成日度情绪 → 驱动涨停家数）
        mood = np.zeros(len(calendar))
        mood[0] = 55.0
        for i in range(1, len(calendar)):
            mood[i] = min(95, max(12, mood[i - 1] + rng.normal(0, 4.5) + (6.5 if rng.rand() < 0.03 else 0) - (9.0 if rng.rand() < 0.04 else 0)))

        # 主题热度由 mood + 各自片段构成
        for i in range(len(calendar)):
            for t in range(n_theme):
                th[i, t] = 0.0
        for t in range(n_theme):
            if rng.rand() < 0.6:  # 约6成题材在窗口内被点火
                s = int(rng.randint(0, len(calendar) - 60))
                ln = int(rng.randint(8, 28))
                e = min(len(calendar), s + ln)
                intens = rng.uniform(0.6, 1.0)
                hot_episode[t] = (s, e, intens)
                for i in range(s, e):
                    th[i, t] += intens * np.exp(-abs(i - (s + e) / 2) / (ln / 2.2))
        for i in range(1, len(calendar)):
            th[i] = th[i - 1] * 0.85 + th[i] + rng.normal(0, 0.06, n_theme)

        # 涨跌停事件状态机
        rows: list[dict] = []
        prev_close = base_price.copy()        # 上一交易日收盘
        prev_open = base_price.copy()
        sealed_streak = np.zeros(n_stocks, dtype=int)   # 当前连板高度（今日封板后）
        prev_sealed = np.zeros(n_stocks, dtype=bool)
        yesterday_info: dict[int, dict] = {}

        lu_max = max(4, min(60, int(n_stocks * 0.28)))

        for i, dt in enumerate(calendar):
            m = mood[i]
            # 目标涨停家数（随市场情绪缩放；受股票池规模约束）
            n_lu = int(np.clip(
                round(4 + 26 * (m / 100.0) ** 2.0 + rng.normal(0, 3)),
                2, lu_max))
            theme_hot = np.argsort(-th[i])[:4]

            # 行情基线因子收益
            mkt_ret = rng.normal((m - 50) / 7000.0, 0.010)
            theme_ret = mkt_ret + (th[i] * 0.004) + rng.normal(0, 0.004, n_theme)

            # 选定涨停标的
            chosen: dict[int, dict] = {}
            # 1) 昨日封板股：以概率决定是否连板（晋级）
            cand_cont = [s for s in range(n_stocks) if prev_sealed[s]]
            rng.shuffle(cand_cont)
            for s in cand_cont:
                if len(chosen) >= n_lu:
                    break
                tm = stock_theme[s]
                hot = tm in theme_hot
                # 高位(>=3)继续打板依赖题材热度
                p = (0.80 if hot else 0.52) if m >= 50 else (0.35 if hot else 0.18)
                if rng.rand() < p:
                    chosen[s] = {"cont": True}
            # 2) 剩余名额：首板/低位板，热点题材优先（分题材供给）
            leftover = max(n_lu - len(chosen), 0)
            pool = [s for s in range(n_stocks) if s not in chosen and not prev_sealed[s]
                    and not basic.iloc[s]["is_st"]]
            score_pool = sorted(
                pool,
                key=lambda s: (q[s] * 0.5 + (1.0 if stock_theme[s] in theme_hot else 0.25)
                               + rng.rand() * 0.6),
                reverse=True)
            made_first = 0
            for s in score_pool:
                if made_first >= leftover:
                    break
                tm = stock_theme[s]
                hot = tm in theme_hot
                p_first = 0.42 if (hot and m >= 45) else (0.22 if hot else (0.10 if m >= 50 else 0.03))
                if rng.rand() < p_first:
                    chosen[s] = {"cont": False}
                    made_first += 1

            # 盘中触板未封（炸板）标的（与情绪负相关）
            n_break = int(np.clip(round(n_lu * (0.05 + (1 - m / 100) * 0.45) * rng.uniform(0.6, 1.4)), 0, 14))
            brk_pool = [s for s in range(n_stocks) if s not in chosen and not basic.iloc[s]["is_st"]]
            rng.shuffle(brk_pool)
            touched_break = set(brk_pool[:n_break])

            # ------- 逐股出K线 -------
            for s in range(n_stocks):
                st = basic.iloc[s]
                is_stock_st = bool(st["is_st"])
                lim_pct = pct_limit(st["code"], is_stock_st, cfg, dt)
                lp = limit_price(prev_close[s], lim_pct)

                ev = chosen.get(s)
                is_break = s in touched_break
                suspended = rng.rand() < (0.004 if ev else 0.015)
                if suspended:
                    continue

                tm = stock_theme[s]
                tr = theme_ret[tm] if not is_stock_st else theme_ret[tm] * 0.6
                base_vol_pct = 0.8 + 3.5 * (1.0 / (0.5 + mv_yi[s] / 60.0))  # 小市值换手高

                if ev:
                    streak = sealed_streak[s] if ev.get("cont") else 0
                    new_streak = streak + 1
                    hot = tm in theme_hot
                    # 一字板概率随高度/热度上升
                    p_one = min(0.5, 0.05 + new_streak * 0.06 + (0.12 if hot else 0))
                    one_word = rng.rand() < p_one
                    seal_amt_pct = rng.uniform(0.04, 0.22) if hot else rng.uniform(0.02, 0.10)
                    amount_mv = rng.uniform(0.02, 0.10 if one_word else 0.16) * (1 + new_streak * 0.12)
                    turnover = base_vol_pct * amount_mv * 2.2
                    amt = mv_yi[s] * 1e8 * turnover / 100.0
                    if one_word:
                        open_p = lp
                        low_p = lp
                        amt = mv_yi[s] * 1e8 * rng.uniform(0.004, 0.012)  # 一字极少成交
                        first_t = "09:30:05"
                        breaks = 0
                        seal_ratio = rng.uniform(0.3, 0.8)
                    else:
                        gap = rng.uniform(0.005, 0.055)
                        open_p = min(round_price(prev_close[s] * (1 + gap)), lp)
                        breaks = int(rng.choice([0, 0, 0, 1, 1, 2]))
                        seal_ratio = rng.uniform(0.08, 0.35)
                        first_t = _pick_seal_time(rng, new_streak, hot)
                    close_p = lp
                    high_p = lp
                    low_p = min(open_p, lp) * (1 - rng.uniform(0.0, 0.05))
                    vol = amt / (lp * 100)
                    if is_stock_st:
                        low_p = max(low_p, round_price(prev_close[s] * (1 - lim_pct)))
                    rows.append(_row(dt, st, open_p, high_p, low_p, close_p,
                                     prev_close[s], vol, amt, turnover, mv_yi[s] * circ_ratio[s],
                                     mv_yi[s], lp, lim_pct, True, True,
                                     open_p >= lp - 1e-6, first_t, breaks,
                                     amt * seal_ratio, seal_ratio, s, ev, True))
                    prev_close[s] = close_p
                    sealed_streak[s] = new_streak
                    prev_sealed[s] = True
                elif is_break:
                    open_p = min(round_price(prev_close[s] * (1 + rng.uniform(0.01, 0.05))), lp)
                    gap_dn = rng.uniform(0.02, 0.045)
                    close_p = round_price(lp * (1 - gap_dn))
                    high_p = lp
                    low_p = min(open_p, close_p) * (1 - rng.uniform(0.01, 0.04))
                    turnover = base_vol_pct * rng.uniform(2.0, 3.2)
                    amt = mv_yi[s] * 1e8 * turnover / 100.0
                    vol = amt / ((open_p + close_p) / 2 * 100)
                    rows.append(_row(dt, st, open_p, high_p, low_p, close_p,
                                     prev_close[s], vol, amt, turnover, mv_yi[s] * circ_ratio[s],
                                     mv_yi[s], lp, lim_pct, True, False,
                                     False, np.nan, np.nan, np.nan, np.nan, None, False))
                    prev_close[s] = close_p
                    sealed_streak[s] = 0
                    prev_sealed[s] = False
                else:
                    # 常规行情
                    idio = rng.normal(0, 0.02)
                    ret = tr * beta_theme[s] * 0.6 + idio
                    if prev_sealed[s]:
                        # 昨日涨停今日未晋级：往往冲高回落/低开
                        ret += rng.normal(-0.03 if m < 55 else 0.0, 0.025)
                    close_p = max(round_price(prev_close[s] * (1 + ret)), 0.5)
                    open_p = round_price(prev_close[s] * (1 + rng.normal(ret * 0.3, 0.012)))
                    hi_lo = abs(rng.normal(0, 0.02)) + 0.006
                    high_p = max(open_p, close_p) * (1 + hi_lo * rng.uniform(0.3, 1.0))
                    low_p = min(open_p, close_p) * (1 - hi_lo * rng.uniform(0.3, 1.0))
                    # 常规波动几乎不触及涨跌停（合成保证清洗度）
                    turnover = base_vol_pct * rng.uniform(0.5, 1.6)
                    amt = mv_yi[s] * 1e8 * turnover / 100.0
                    vol = amt / ((open_p + close_p) / 2 * 100)
                    touched = high_p >= lp - 1e-6
                    rows.append(_row(dt, st, open_p, high_p, low_p, close_p,
                                     prev_close[s], vol, amt, turnover, mv_yi[s] * circ_ratio[s],
                                     mv_yi[s], lp, lim_pct, touched, False,
                                     False, np.nan, np.nan, np.nan, np.nan, None, False))
                    prev_close[s] = close_p
                    sealed_streak[s] = 0
                    prev_sealed[s] = False

            # 连板高度衰减（未封板即已置0）
        daily = pd.DataFrame(rows).sort_values(["code", "trade_date"]).reset_index(drop=True)
        return daily


def _row(dt, st, open_p, high_p, low_p, close_p, pre_close, vol, amt, turnover,
         circ_mv, total_mv, lp, lim_pct, touched, sealed, one_word, first_t,
         breaks, seal_amount, seal_ratio, stock_idx=None, cont_flag=None,
         is_event=False):
    rng = np.random.RandomState((int(dt.replace("-", "")) * 10007 + (stock_idx or 0) * 13) % (2**31))
    mf = np.nan
    if is_event or cont_flag is not None:
        mf = np.nan if rng.rand() < 0.45 else float(np.clip(rng.normal(0.02, 0.05), -0.12, 0.18))
    name = st["name"]
    return {
        "trade_date": dt, "code": st["code"], "open": float(open_p), "high": float(high_p),
        "low": float(low_p), "close": float(close_p), "pre_close": float(pre_close),
        "vol": float(vol), "amount": float(amt), "turnover_rate": float(turnover),
        "free_turnover": float(turnover * 1.25), "total_mv_yi": float(total_mv),
        "circ_mv_yi": float(circ_mv), "limit_up_price": float(lp),
        "limit_down_price": float(round_price(pre_close * (1 - lim_pct))),
        "limit_pct": float(lim_pct), "touched": bool(touched), "sealed": bool(sealed),
        "is_limit_down": False, "one_word": bool(one_word),
        "first_seal_time": first_t, "break_count": breaks, "seal_amount": seal_amount,
        "seal_ratio": seal_ratio, "board_count": 0,
        "industry": st["industry"], "is_st": bool(st["is_st"]), "name": name,
        "board": st["board"], "money_flow_ratio": mf,
    }


def _pick_seal_time(rng, streak, hot):
    if streak >= 3 and hot:
        pool = ["09:31:00", "09:32:30", "09:34:00", "09:30:40"]
    elif hot:
        pool = ["09:33:00", "09:36:20", "09:40:10", "09:47:00"]
    else:
        pool = ["10:05:00", "10:40:00", "11:05:00", "13:20:00", "14:05:00"]
    return str(rng.choice(pool))


def _compute_board_count_simple(df: pd.DataFrame) -> pd.Series:
    """基于规范列重算 board_count（df 须已按 code/trade_date 排序）。"""
    out = np.zeros(len(df), dtype=int)
    codes = df["code"].to_numpy()
    sealed = df["sealed"].to_numpy()
    dates = df["trade_date"].to_numpy()
    cal = {d: i for i, d in enumerate(np.unique(dates))}
    for i in range(len(df)):
        if sealed[i]:
            if i > 0 and codes[i - 1] == codes[i] and cal[dates[i]] - cal[dates[i - 1]] == 1:
                out[i] = out[i - 1] + 1
            else:
                out[i] = 1
    return pd.Series(out, index=df.index)


def _trading_calendar(start: str, end: str) -> list[str]:
    days = pd.bdate_range(start=start, end=end)
    return [d.strftime("%Y-%m-%d") for d in days]


# ----------------------------------------------------------------------
# Tushare 真实数据源（按日全市场拉取 + 本地缓存）
# ----------------------------------------------------------------------

class TushareSource:
    def __init__(self, cfg: dict, token: str):
        self.cfg = cfg
        self.token = token
        try:
            import tushare as ts
            ts.set_token(token)
            self.pro = ts.pro_api()
        except Exception as e:  # pragma: no cover
            raise RuntimeError(f"Tushare 初始化失败: {e}")

    def load(self) -> DataBundle:
        from config.settings import CACHE_DIR
        cfg = self.cfg["data"]
        start = self.cfg["backtest"]["start"]
        end = self.cfg["backtest"]["end"]
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        daily = self._load_daily(start, end, CACHE_DIR)
        basic = self._load_basic(CACHE_DIR)
        basic["board"] = basic["code"].map(infer_board)
        # 涨停事件/封板字段：日线估计（缺失高频字段 NaN → 引擎中性处理）
        canonical = detect_daily(daily, basic, self.cfg)
        # total_mv 修正（daily_basic 提供真实市值，若已缓存则覆盖）
        db = self._load_daily_basic(start, end, CACHE_DIR)
        if db is not None and len(db):
            keep = ["trade_date", "code", "turnover_rate", "free_turnover", "total_mv_yi", "circ_mv_yi"]
            canonical = (canonical
                         .drop(columns=[c for c in keep if c not in ("trade_date", "code")])
                         .merge(db[keep], on=["trade_date", "code"], how="left")
                         .sort_values(["code", "trade_date"])
                         .reset_index(drop=True))
        canonical = canonical.sort_values(["code", "trade_date"]).reset_index(drop=True)
        market = market_daily_features(canonical)
        notes = [
            "数据源: tushare 真实日线/daily_basic",
            "高频字段(首封时间/炸板次数/封单/龙虎榜/竞价)为日线估计或缺失 → 因子走中性/ESTIMATED",
            f"token 已配置, 区间 {start} ~ {end}",
        ]
        return DataBundle(basic=basic, daily=canonical, market=market, notes=notes, source="tushare")

    def _load_basic(self, cache_dir) -> pd.DataFrame:
        fp = cache_dir / "stock_basic.csv"
        if fp.exists():
            b = pd.read_csv(fp, dtype={"ts_code": str})
        else:
            df = self.pro.stock_basic(exchange="", list_status="L",
                                      fields="ts_code,symbol,name,industry,market,list_date")
            b = df.rename(columns={"ts_code": "code", "symbol": "symbol"})
            b.to_csv(fp, index=False, encoding="utf-8-sig")
        b["is_st"] = b["name"].astype(str).str.contains("ST", na=False)
        b["industry"] = b["industry"].fillna("未知")
        if "list_date" in b.columns:
            b["list_date"] = b["list_date"].astype(str).str.replace(r"(\d{4})(\d{2})(\d{2})", r"\1-\2-\3", regex=True)
        # 过滤：仅主板/创业板/科创板（去掉北交所）
        b["board"] = b["code"].map(infer_board)
        keep = ["MAIN_SZ", "MAIN_SH", "GEM", "STAR"]
        b = b[b["board"].isin(keep)].copy()
        return b[["code", "name", "board", "is_st", "industry", "list_date"]]

    @staticmethod
    def _fmt(d: str) -> str:
        """YYYYMMDD -> YYYY-MM-DD"""
        return f"{d[0:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d

    def _load_daily(self, start: str, end: str, cache_dir) -> pd.DataFrame:
        """按交易日批量拉取全市场日线并缓存（交易日历来自 trade_cal）。"""
        fp = cache_dir / "daily.parquet"
        cal = self.pro.trade_cal(exchange="SSE", start_date=start.replace("-", ""),
                                 end_date=end.replace("-", ""), is_open="1")
        dates = [self._fmt(str(x)) for x in sorted(cal["cal_date"].astype(str).tolist())]
        frames: list[pd.DataFrame] = []
        done: set[str] = set()
        if fp.exists():
            old = pd.read_parquet(fp)
            if len(old):
                old["trade_date"] = old["trade_date"].astype(str).map(self._fmt)
                frames.append(old)
                done = set(old["trade_date"].unique())
        todo = [d for d in dates if d not in done]
        print(f"[tushare] 交易日 {len(dates)} 日，缓存命中 {len(done)}，待拉取 {len(todo)}")
        for i, d in enumerate(todo):
            raw = self.pro.daily(trade_date=d.replace("-", ""))
            if raw is None or raw.empty:
                continue
            df = raw[["trade_date", "ts_code", "open", "high", "low", "close",
                      "pre_close", "vol", "amount"]].rename(
                columns={"ts_code": "code"})
            df["trade_date"] = df["trade_date"].astype(str).map(self._fmt)
            df["amount"] = df["amount"] * 1000.0      # tushare 单位千元 → 元
            frames.append(df)
            if (i + 1) % 20 == 0:
                print(f"  ... {i+1}/{len(todo)}")
        if frames:
            out = pd.concat(frames, ignore_index=True)
            out.to_parquet(fp, index=False)
        else:
            out = pd.DataFrame()
        return out

    def _load_daily_basic(self, start, end, cache_dir):
        fp = cache_dir / "daily_basic.parquet"
        if fp.exists():
            old = pd.read_parquet(fp)
            if len(old):
                old["trade_date"] = old["trade_date"].astype(str).map(self._fmt)
                return old
            return None
        cal = self.pro.trade_cal(exchange="SSE", start_date=start.replace("-", ""),
                                 end_date=end.replace("-", ""), is_open="1")
        dates = [self._fmt(str(x)) for x in sorted(cal["cal_date"].astype(str).tolist())]
        frames = []
        for i, d in enumerate(dates):
            try:
                df = self.pro.daily_basic(trade_date=d.replace("-", ""),
                                          fields="trade_date,ts_code,turnover_rate,turnover_rate_f,total_mv,circ_mv")
            except Exception:
                continue
            if df is None or df.empty:
                continue
            df = df.rename(columns={"ts_code": "code", "turnover_rate_f": "free_turnover"})
            df["trade_date"] = df["trade_date"].astype(str).map(self._fmt)
            df["total_mv_yi"] = df["total_mv"] / 1e4
            df["circ_mv_yi"] = df["circ_mv"] / 1e4
            frames.append(df[["trade_date", "code", "turnover_rate", "free_turnover", "total_mv_yi", "circ_mv_yi"]])
            if (i + 1) % 40 == 0:
                print(f"  basic ... {i+1}/{len(dates)}")
        if frames:
            out = pd.concat(frames, ignore_index=True)
            out.to_parquet(fp, index=False)
            return out
        return None


def load_data(cfg: dict, token: str | None = None) -> DataBundle:
    """数据加载门面：按配置选源；tushare 无 token/失败时回退 synthetic。

    合成源支持本地缓存（同参数二次运行免重新生成）。
    """
    src = cfg["data"]["source"]
    if src == "tushare":
        token = token or ""
        if not token:
            print("[warn] 未配置 TUSHARE_TOKEN → 回退 synthetic 合成数据")
        else:
            try:
                return TushareSource(cfg, token).load()
            except Exception as e:
                print(f"[warn] Tushare 加载失败({e}) → 回退 synthetic 合成数据")
    print("[info] 使用 synthetic 合成数据源")
    cached = _load_synthetic_cache(cfg)
    if cached is not None:
        print("[info] 命中合成数据缓存，跳过生成")
        return cached
    bundle = SyntheticSource(cfg).load()
    _save_synthetic_cache(bundle, cfg)
    return bundle


def _synthetic_fp(cfg) -> Path:
    from config.settings import CACHE_DIR
    return CACHE_DIR / "synthetic"


def _synthetic_fingerprint(cfg) -> dict:
    s = cfg["data"]["synthetic"]
    return {"n_stocks": s.get("n_stocks", 320), "seed": s.get("seed", 20260906),
            "start": s.get("start", "2023-01-02"), "end": s.get("end", "2025-09-30")}


def _save_synthetic_cache(bundle: DataBundle, cfg: dict) -> None:
    try:
        import json
        base = _synthetic_fp(cfg)
        base.mkdir(parents=True, exist_ok=True)
        bundle.daily.to_parquet(base / "daily.parquet")
        bundle.market.to_parquet(base / "market.parquet")
        bundle.basic.to_csv(base / "basic.csv", index=False, encoding="utf-8-sig")
        (base / "meta.json").write_text(json.dumps(_synthetic_fingerprint(cfg)),
                                        encoding="utf-8")
    except Exception as e:
        print(f"[warn] 合成缓存写入失败({e})")


def _load_synthetic_cache(cfg: dict) -> DataBundle | None:
    try:
        import json
        base = _synthetic_fp(cfg)
        files = [base / "daily.parquet", base / "market.parquet",
                 base / "basic.csv", base / "meta.json"]
        if not all(f.exists() for f in files):
            return None
        meta = json.loads((base / "meta.json").read_text(encoding="utf-8"))
        if meta != _synthetic_fingerprint(cfg):
            return None
        daily = pd.read_parquet(base / "daily.parquet")
        market = pd.read_parquet(base / "market.parquet")
        basic = pd.read_csv(base / "basic.csv", encoding="utf-8-sig")
        s = cfg["data"]["synthetic"]
        notes = [
            "数据源: synthetic 合成数据（缓存命中；含涨停事件/竞价/封单等全字段，可靠性=SIM）",
            f"股票数 {len(basic)}，{s.get('start')} ~ {s.get('end')}（按自然交易日近似）",
        ]
        return DataBundle(basic=basic, daily=daily, market=market, notes=notes,
                          source="synthetic")
    except Exception:
        return None
