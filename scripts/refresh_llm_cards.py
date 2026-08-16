# -*- coding: utf-8 -*-
"""用真实 DeepSeek 重算全部景区口碑卡(需要 .env 已配置 DEEPSEEK_API_KEY)。

用法: python scripts/refresh_llm_cards.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.config import load_dotenv  # noqa: E402

load_dotenv()

from backend.ai.pipeline import get_llm, summarize_spot  # noqa: E402
from backend.app.db import get_conn  # noqa: E402


def main() -> None:
    if not get_llm().available:
        print("未检测到 DEEPSEEK_API_KEY,请先配置 .env")
        return
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
            conn.commit()
            done += 1
            print(f"  [{done}] {r['name']}: {card.get('source')} | 信任度 {card.get('trust_score')}")
        print(f"完成: {done} 张口碑卡已由 DeepSeek 重算")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
