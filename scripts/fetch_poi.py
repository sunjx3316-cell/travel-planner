# -*- coding: utf-8 -*-
"""从高德 POI 扩充景区名单，并保存可追溯来源记录。

用法:
    python scripts/fetch_poi.py --pilot      # 首批 20 个热门城市（默认）
    python scripts/fetch_poi.py --all        # 扩充全部种子城市（注意配额）
    python scripts/fetch_poi.py 北京 上海    # 只扩充指定城市
    python scripts/fetch_poi.py --limit 60   # 每城最多 60 条

前置: .env 中配置 AMAP_KEY(高德开放平台免费申请, https://lbs.amap.com)
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 读取 .env(与 start.ps1 同规则)
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from backend.app.db import get_conn, init_db  # noqa: E402
from backend.collector.amap_poi import fetch_city_pois, import_into_db_stats  # noqa: E402

PILOT_CITIES = ("北京", "上海", "广州", "成都", "重庆", "西安", "杭州", "三亚", "丽江", "长沙",
                "厦门", "苏州", "南京", "青岛", "桂林", "张家界", "黄山", "哈尔滨", "大理", "拉萨")


def main() -> None:
    ap = argparse.ArgumentParser(description="从高德采集结构化 POI 候选，并留下来源与采集时间")
    ap.add_argument("cities", nargs="*", help="指定城市；不填时默认 --pilot")
    ap.add_argument("--pilot", action="store_true", help="首批 20 个热门城市（默认）")
    ap.add_argument("--all", action="store_true", help="扩充全部已收录城市，注意 API 配额")
    ap.add_argument("--limit", type=int, default=40, help="每城最多保留多少候选点（默认 40）")
    ap.add_argument("--pages", type=int, default=1, help="每个关键词最大页数（默认 1）")
    ap.add_argument("--sleep", type=float, default=0.5, help="两城间隔秒数（默认 0.5）")
    ap.add_argument("--dry-run", action="store_true", help="只请求和展示，不写入数据库")
    args = ap.parse_args()
    if args.all and args.cities:
        ap.error("--all 与指定城市不能同时使用")
    init_db()
    conn = get_conn()
    try:
        cities = conn.execute("SELECT id, name FROM cities ORDER BY id").fetchall()
        names = {c["name"] for c in cities}
        targets = None if args.all else (args.cities or PILOT_CITIES)
        if targets:
            unknown = [name for name in targets if name not in names]
            if unknown:
                print(f"提示: 以下城市尚未收录，跳过: {', '.join(unknown)}")
        total_added = total_updated = total_sources = 0
        for c in cities:
            if targets and c["name"] not in targets:
                continue
            try:
                pois = fetch_city_pois(c["name"], args.limit, args.pages)
            except Exception as e:
                print(f"  ✗ {c['name']}: {e}")
                continue
            if args.dry_run:
                print(f"  · {c['name']}: 候选 {len(pois)} 条 | " + "、".join(p["name"] for p in pois[:5]))
            else:
                stats = import_into_db_stats(conn, c["id"], pois)
                conn.commit()
                total_added += stats.added
                total_updated += stats.updated
                total_sources += stats.source_records
                print(f"  ✓ {c['name']}: 候选 {len(pois)} | 新增 {stats.added} | 更新 {stats.updated} | 来源快照 {stats.source_records}")
            time.sleep(max(0, args.sleep))
        if not args.dry_run:
            print(f"完成: 新增 {total_added}，更新 {total_updated}，写入/刷新来源快照 {total_sources}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
