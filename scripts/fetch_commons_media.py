# -*- coding: utf-8 -*-
"""下载 Wikimedia Commons 自由许可的景点缩略图，并写入图片授权台账。

示例：
  python scripts/fetch_commons_media.py --spot 故宫博物院 --spot 布达拉宫
  python scripts/fetch_commons_media.py --spot 故宫博物院 --data-dir D:\\...\\data
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.app.db import DATA_DIR, get_conn, init_db  # noqa: E402
from backend.collector.wikimedia_media import download_and_ingest  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="获取 Wikimedia Commons 自由许可景点缩略图")
    parser.add_argument("--spot", action="append", required=True, help="景点精确名称；可重复传入")
    parser.add_argument("--data-dir", default=str(DATA_DIR), help="图片写入的 data 目录")
    args = parser.parse_args()
    init_db()
    conn = get_conn()
    try:
        for name in args.spot:
            spot = conn.execute("SELECT id, name FROM spots WHERE name=? LIMIT 1", (name,)).fetchone()
            if spot is None:
                print(f"[SKIP] 未找到景点：{name}")
                continue
            try:
                result = download_and_ingest(spot["id"], spot["name"], Path(args.data_dir), conn=conn)
                if result["added"]:
                    print(f"[OK] {name} -> {result['path']}")
                else:
                    print(f"[SKIP] {name}: {result.get('reason', '图片已登记')}")
            except Exception as exc:
                print(f"[ERROR] {name}: {exc}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
