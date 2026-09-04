# -*- coding: utf-8 -*-
"""登记景点图片的来源与授权状态；不下载或抓取第三方图片。"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.app.db import get_conn  # noqa: E402
from backend.collector.media_source import ingest_media  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="登记图片台账（只发布授权已核验图片）")
    parser.add_argument("--spot", required=True, help="景点名")
    parser.add_argument("--storage-path", required=True, help="images/... 或 HTTPS COS/CDN URL")
    parser.add_argument("--origin-url", required=True, help="图片原始来源或授权凭证链接")
    parser.add_argument("--provider", required=True, help="如 official / user / licensed_partner")
    parser.add_argument("--rights-status", default="pending", choices=("pending", "verified", "rejected"))
    parser.add_argument("--license-note", default="", help="授权说明或凭证编号")
    parser.add_argument("--captured-at", default="", help="来源内容时间，ISO 格式可选")
    args = parser.parse_args()

    conn = get_conn()
    try:
        spot = conn.execute("SELECT id, name FROM spots WHERE name=? LIMIT 1", (args.spot,)).fetchone()
        if spot is None:
            parser.error(f"找不到景点：{args.spot}")
        result = ingest_media(spot["id"], vars(args), conn=conn)
    finally:
        conn.close()
    print(f"✓ {spot['name']}：{'新增' if result['added'] else '已存在'}；"
          f"{'可在前台展示' if result['public'] else '待审核，不会在前台展示'}")


if __name__ == "__main__":
    main()
