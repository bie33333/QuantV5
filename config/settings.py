# -*- coding: utf-8 -*-
"""运行配置：路径 / 环境 / token 解析。"""
from __future__ import annotations

import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE / "config" / "model_v2.yaml"
OUT_DIR = BASE / "outputs"
WEBAPP_DIR = BASE / "webapp"

TZ = "Asia/Shanghai"
DATE_FMT = "%Y-%m-%d"

# 数据源工作目录（真实数据本地缓存，不入库不入 git）
CACHE_DIR = BASE / ".data_cache"


def resolve_tushare_token(yaml_cfg: dict) -> str:
    """token 优先级：环境变量 TUSHARE_TOKEN > yaml tushare.token"""
    env = os.environ.get("TUSHARE_TOKEN", "").strip()
    yml = (yaml_cfg.get("data", {}).get("tushare", {}) or {}).get("token", "") or ""
    return env or yml
