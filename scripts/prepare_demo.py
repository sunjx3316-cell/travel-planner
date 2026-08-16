# -*- coding: utf-8 -*-
"""一键准备演示数据:重建数据库(旧库自动备份)+ 预计算全部景区口碑卡。

用法: python scripts/prepare_demo.py
说明: 正式采集的数据会被备份到 travel.db.bak,不会丢失。
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.ai.pipeline import summarize_spot  # noqa: E402
from backend.app.db import DB_PATH, get_conn, init_db  # noqa: E402


def main() -> None:
    if DB_PATH.exists():
        bak = DB_PATH.with_suffix(".db.bak")
        shutil.copy2(DB_PATH, bak)
        DB_PATH.unlink()
        print(f"旧库已备份 -> {bak.name}")

    init_db()

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT s.id, s.name FROM spots s "
            "WHERE EXISTS (SELECT 1 FROM notes n WHERE n.spot_id = s.id) "
            "ORDER BY s.id"
        ).fetchall()
        done = 0
        for r in rows:
            notes = conn.execute("SELECT * FROM notes WHERE spot_id=? ORDER BY id", (r["id"],)).fetchall()
            if not notes:
                continue
            card = summarize_spot(r["name"], [dict(n) for n in notes])
            conn.execute(
                "INSERT OR REPLACE INTO spot_summaries(spot_id, summary_json, updated_at) VALUES(?,?,?)",
                (r["id"], json.dumps(card, ensure_ascii=False),
                 datetime.now().isoformat(timespec="seconds")),
            )
            done += 1
        conn.commit()
        print(f"演示库就绪:{done} 个景区口碑卡已预计算(含 10 城市 / 41 景区 / 31 篇示例笔记)")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
