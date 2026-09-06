# -*- coding: utf-8 -*-
"""配置加载：yaml → 简单嵌套 dict（进程内单一事实源）。"""
from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "model_v2.yaml"


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else DEFAULT_CONFIG
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg


def deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典（override 覆盖 base），用于 CLI 参数覆盖。"""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out
