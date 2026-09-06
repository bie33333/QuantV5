# -*- coding: utf-8 -*-
"""把 outputs/result.json 渲染为单文件可视化看板 outputs/dashboard.html。

用法: python scripts/build_dashboard.py [--result outputs/result.json]
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--result", default=str(BASE / "outputs" / "result.json"))
    p.add_argument("--template", default=str(BASE / "webapp" / "dashboard_template.html"))
    p.add_argument("--out", default=str(BASE / "outputs" / "dashboard.html"))
    p.add_argument("--echarts", default=str(BASE / ".tmp_assets" / "echarts.min.js"))
    args = p.parse_args()

    data = json.loads(Path(args.result).read_text(encoding="utf-8"))
    html = Path(args.template).read_text(encoding="utf-8")

    echarts_js = Path(args.echarts).read_text(encoding="utf-8")
    html = html.replace('<script src="assets/echarts.min.js"></script>',
                        "<script>\n" + echarts_js + "\n</script>")

    payload = json.dumps(data, ensure_ascii=False)
    payload = payload.replace("</", "<\\/")   # 防 script 闭合注入
    html = html.replace("/*__DATA__*/null", payload)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"看板已生成: {out} ({out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
