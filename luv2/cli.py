# -*- coding: utf-8 -*-
"""命令行入口：数据 → 完整引擎 → 报表 JSON。

示例：
  python -m luv2.cli --source synthetic
  python -m luv2.cli --source tushare --start 2024-01-01 --end 2026-06-30
  python -m luv2.cli --ablation --walk-forward
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .backtest import GateCfg, prepare_bundle, run_backtest
from .config import load_config
from .metrics import compute_metrics
from .report import dump_json, to_web
from .sources import load_data

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="luv2", description="LimitUp_Factor_Model v2.0 回测")
    p.add_argument("--config", default=None, help="model_v2.yaml 路径")
    p.add_argument("--source", choices=["auto", "synthetic", "tushare"], default="auto")
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--no-ablation", action="store_true")
    p.add_argument("--walk-forward", action="store_true")
    p.add_argument("--out-dir", default=None)
    p.add_argument("--token", default=None, help="Tushare token（缺省读环境变量 TUSHARE_TOKEN）")
    p.add_argument("--version", action="version", version=__version__)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    cfg = load_config(args.config)
    if args.start:
        cfg["backtest"]["start"] = args.start
    if args.end:
        cfg["backtest"]["end"] = args.end
    if args.source and args.source != "auto":
        cfg["data"]["source"] = args.source

    from config.settings import resolve_tushare_token  # noqa: E402
    token = args.token or resolve_tushare_token(cfg)
    if cfg["data"]["source"] == "tushare" and not token:
        print("[error] 数据源为 tushare 但未提供 token。设置环境变量 TUSHARE_TOKEN 或 --token。")
        return 2

    bundle = load_data(cfg, token)
    prepare_bundle(bundle, cfg)

    print(f"\n=== 运行完整 v2.0 模型 [{cfg['backtest']['start']} ~ {cfg['backtest']['end']}] ===")
    seed = args.seed if args.seed is not None else int(cfg["execution"].get("rng_seed", 20260906))
    res = run_backtest(bundle, cfg, gates=GateCfg(), label="D", rng_seed=seed)
    if res.get("empty"):
        print("[error] 区间内无数据")
        return 1
    m = compute_metrics(res, cfg)
    _print_summary(m)

    ablation = None
    if not args.no_ablation:
        print("\n=== 分层消融 A/B/C/D ===")
        from .walk_forward import run_ablation
        ablation = run_ablation(bundle, cfg)
        _print_ablation(ablation)

    wf = None
    if args.walk_forward:
        print("\n=== Walk-Forward（样本外）===")
        from .walk_forward import run_walk_forward
        wf = run_walk_forward(bundle, cfg, gates=GateCfg())
        for row in wf.get("folds", []):
            print(f"  fold {row['fold']}: 交易{row['trades']:>3} | 收益 {_pct(row['total_return']):>8} | "
                  f"回撤 {_pct(row['max_drawdown']):>8} | PF {_fmt(row['profit_factor'])} | "
                  f"期望 {_pct(row['expectancy'])}")

    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir is None:
        out_dir = Path(cfg["report"]["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    web = to_web(res, cfg, ablation=ablation, walk_forward=wf, bundle=bundle)
    rp = out_dir / cfg["report"]["result_json"]
    dump_json(web, rp)
    print(f"\n报表已写入: {rp}")
    return 0


def _pct(x):
    return "nan" if x is None else f"{x * 100:.2f}%"


def _fmt(x):
    return "nan" if x is None else f"{x:.3f}"


def _print_summary(m: dict) -> None:
    def g(k):
        return m.get(k)

    print("-" * 72)
    print(f"  总收益        {_pct(g('total_return')):>12}   年化(CAGR)  {_pct(g('cagr')):>12}")
    print(f"  最大回撤      {_pct(g('max_drawdown')):>12}   交易笔数    {g('trade_count')}")
    print(f"  胜率          {_pct(g('win_rate')):>12}   盈亏比(PF)  {_fmt(g('profit_factor'))}")
    print(f"  期望/笔       {_pct(g('expectancy')):>12}   T+1胜率     {_pct(g('t1_win_rate'))}")
    print(f"  T+1均收(close){_pct(g('t1_avg_close')):>12}   成交率      {_pct(g('execution_rate'))}")
    print(f"  连续亏损次数  {g('max_consec_losses')}                退出原因: "
          + ", ".join(f"{k}={v}" for k, v in (g('exit_reason') or {}).items()))
    print("-" * 72)


def _print_ablation(ab: dict) -> None:
    print(f"  {'模型':<6}{'交易':>6}{'总收益':>10}{'回撤':>10}{'胜率':>9}{'PF':>8}{'期望/笔':>10}{'成交率':>9}")
    for name in ["A", "B", "C", "D"]:
        a = ab.get(name, {})
        mt = a.get("metrics", {})
        print(f"  {name:<6}{a.get('trade_count', 0):>6}{_pct(mt.get('total_return')):>10}"
              f"{_pct(mt.get('max_drawdown')):>10}{_pct(mt.get('win_rate')):>9}"
              f"{_fmt(mt.get('profit_factor')):>8}{_pct(mt.get('expectancy')):>10}"
              f"{_pct(mt.get('execution_rate')):>9}")


if __name__ == "__main__":
    raise SystemExit(main())
