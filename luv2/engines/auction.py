# -*- coding: utf-8 -*-
"""第四层 · Auction Engine（竞价层，T日 9:25）。

竞价不能只看涨幅：过高(近一字)≠好。输出 0~15 分 + 硬否决标记。
输入行：T日（打板当日）行情，auction_ret = open/pre_close - 1。
"""
from __future__ import annotations

import numpy as np


def auction_score(auction_ret: float, cfg: dict) -> dict:
    acfg = cfg["auction"]
    hard_reject = auction_ret < float(acfg.get("hard_reject_below", -0.03))
    sc = 0.0
    for lo, hi, s in acfg.get("rules", []):
        if lo <= auction_ret < hi:
            sc = float(s)
            break
    else:
        sc = 6.0
    note = "normal"
    if auction_ret >= 0.095:
        note = "overheated(近一字)"
    elif auction_ret >= 0.08:
        note = "high_open"
    elif auction_ret >= 0.0:
        note = "healthy"
    else:
        note = "weak_open"
    return {"auction_score": float(np.clip(sc, 0, 15)), "hard_reject": bool(hard_reject),
            "auction_ret": float(auction_ret), "note": note}
