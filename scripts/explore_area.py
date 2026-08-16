# -*- coding: utf-8 -*-
"""通用景区探索工具:按地区+关键词挖掘未评级自然景区(需 AMAP_KEY)。

用法:
    python scripts/explore_area.py 甘南藏族自治州 --kw 草原,湖泊,峡谷,寺院,观景台
    python scripts/explore_area.py 甘南藏族自治州 --kw 草原,湖泊 --limit 30 --import --city 甘南州

说明: --import 会把探索结果导入数据库(grade 空=非评级,标签"探索发现"),
      之后即可加入清单用自驾模式串联路线。
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

from backend.collector import amap_poi  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="按地区+关键词探索自然景区(需 .env 配置 AMAP_KEY)")
    ap.add_argument("district", help="地区,如 甘南藏族自治州")
    ap.add_argument("--kw", default="草原,湖泊,峡谷,寺院,观景台", help="关键词,逗号分隔")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--import", dest="do_import", action="store_true", help="导入数据库")
    ap.add_argument("--city", default=None, help="导入时归属城市名(默认用地区名)")
    args = ap.parse_args()

    keywords = [k.strip() for k in args.kw.split(",") if k.strip()]
    print(f"探索 {args.district} 关键词: {keywords}")
    pois = amap_poi.fetch_keyword_pois(args.district, keywords, limit=args.limit)
    print(f"命中 {len(pois)} 条:")
    for i, p in enumerate(pois, 1):
        print(f"  {i:2d}. {p['name'][:28]:<30} [{p['keyword']}] {p['type'][:20]}")

    if args.do_import and pois:
        from backend.app.db import get_conn

        conn = get_conn()
        try:
            city = args.city or args.district
            n = amap_poi.import_explore_pois(conn, city, "", pois)
            print(f"已导入 {n} 条到城市「{city}」(标签: 探索发现)")
        finally:
            conn.close()


if __name__ == "__main__":
    main()
