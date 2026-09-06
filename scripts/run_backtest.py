# -*- coding: utf-8 -*-
"""快捷入口：python scripts/run_backtest.py [--help]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from luv2.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
