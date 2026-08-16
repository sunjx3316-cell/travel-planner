# -*- coding: utf-8 -*-
"""沿环线自动挖掘沿途景点(需 .env 配置 AMAP_KEY)。

用法:
    python scripts/explore_route.py 甘南环线                       # 预览沿途发现
    python scripts/explore_route.py 甘南环线 --kw 草原,湖泊 --limit 60
    python scripts/explore_route.py 甘南环线 --import              # 导入数据库
"""
import argparse
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 读取 .env
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from backend.collector import amap_poi, route_explore  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="沿环线自动挖掘沿途景点(需 AMAP_KEY)")
    ap.add_argument("loop", help="环线名,如 甘南环线(可选: 川西环线/青甘环线/滇西北环线/北疆环线)")
    ap.add_argument("--kw", default=",".join(route_explore.DEFAULT_KEYWORDS), help="关键词,逗号分隔")
    ap.add_argument("--radius", type=int, default=20000, help="搜索半径(米)")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--import", dest="do_import", action="store_true", help="导入数据库")
    args = ap.parse_args()

    centers = route_explore.route_centers_from_loop(args.loop)
    keywords = [k.strip() for k in args.kw.split(",") if k.strip()]
    print(f"环线 {args.loop}: {len(centers)} 个点位,以每个点位为中心搜索半径 {args.radius}m")

    from backend.app.db import get_conn

    conn = get_conn()
    try:
        existing = {r[0] for r in conn.execute("SELECT name FROM spots").fetchall()}
    finally:
        conn.close()
    print(f"已收录景点 {len(existing)} 个,将跳过同名发现")

    fetcher = route_explore.amap_around_fetcher(keywords, radius=args.radius)
    found = route_explore.collect_discoveries(centers, fetcher, existing, limit=args.limit)
    print(f"沿途新发现 {len(found)} 个景点:")
    for i, p in enumerate(found, 1):
        print(f"  {i:2d}. {p['name'][:26]:<28} 近「{p.get('near','')}」 [{p.get('keyword','')}]")

    if args.do_import and found:
        conn = get_conn()
        try:
            # 按中心点城市分组导入(城市取中心点所在城市,简化:用环线名建一个"环线发现"城市)
            n = amap_poi.import_explore_pois(conn, f"{args.loop}·沿途", "", found,
                                             tag="探索发现")
            print(f"已导入 {n} 条(城市: {args.loop}·沿途,标签: 探索发现)")
        finally:
            conn.close()


if __name__ == "__main__":
    main()
