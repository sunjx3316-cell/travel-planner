# -*- coding: utf-8 -*-
"""从高德 POI 扩充景区名单(正式版数据源,多关键词聚合)。

用法:
    python scripts/fetch_poi.py              # 扩充全部种子城市
    python scripts/fetch_poi.py 北京 上海    # 只扩充指定城市
    python scripts/fetch_poi.py --limit 60   # 每城最多 60 条

前置: .env 中配置 AMAP_KEY(高德开放平台免费申请, https://lbs.amap.com)
"""
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

from backend.app.db import get_conn  # noqa: E402
from backend.collector.amap_poi import fetch_city_pois, import_into_db  # noqa: E402


def main() -> None:
    args = sys.argv[1:]
    limit = 40
    if "--limit" in args:
        i = args.index("--limit")
        limit = int(args[i + 1])
        del args[i:i + 2]
    targets = args or None
    conn = get_conn()
    try:
        cities = conn.execute("SELECT id, name FROM cities ORDER BY id").fetchall()
        total = 0
        for c in cities:
            if targets and c["name"] not in targets:
                continue
            try:
                pois = fetch_city_pois(c["name"], limit)
            except Exception as e:
                print(f"  ✗ {c['name']}: {e}")
                continue
            added = import_into_db(conn, c["id"], pois)
            conn.commit()
            total += added
            print(f"  ✓ {c['name']}: 拉到 {len(pois)} 条,新增 {added} 条")
            time.sleep(0.3)  # 温和限速
        print(f"完成,共新增 {total} 条景区数据")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
