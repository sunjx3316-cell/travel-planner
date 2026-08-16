# -*- coding: utf-8 -*-
"""小红书采集入口(需先登录一次)。

用法:
    python scripts/collect_xhs.py --login         # 首次:弹浏览器,手动登录,保存 cookie
    python scripts/collect_xhs.py --probe         # 探测会话状态(1 次请求,采集前先探)
    python scripts/collect_xhs.py                 # 为所有缺笔记的景区采集(有头模式)
    python scripts/collect_xhs.py 天坛公园 西湖    # 指定景区采集
    python scripts/collect_xhs.py --headless      # 无头模式(不弹窗,但不适合有滑块/验证码时)

采集完成后自动重算该景区的 AI 口碑卡。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.db import get_conn  # noqa: E402
from backend.collector import xhs_collector as xhs  # noqa: E402


def refresh_summary(spot_id: int, spot_name: str) -> None:
    from backend.ai.pipeline import summarize_spot

    conn = get_conn()
    try:
        notes = conn.execute("SELECT * FROM notes WHERE spot_id=? ORDER BY id", (spot_id,)).fetchall()
        if not notes:
            return
        card = summarize_spot(spot_name, [dict(n) for n in notes])
        conn.execute(
            "INSERT OR REPLACE INTO spot_summaries(spot_id, summary_json, updated_at) VALUES(?,?,?)",
            (spot_id, json.dumps(card, ensure_ascii=False),
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        print(f"  [AI] {spot_name} 口碑卡已更新(信任度 {card.get('trust_score')}, {card.get('note_count')} 篇)")
    finally:
        conn.close()


def main() -> None:
    args = sys.argv[1:]
    if "--login" in args:
        xhs.login_wizard(headless=False)
        return
    if "--probe" in args:
        print("探测会话状态(1 次搜索请求)...")
        print("结果:", xhs.probe_session(headless=False))
        return

    headless = "--headless" in args  # 默认有头模式(弹窗可见,可处理滑块)
    names = [a for a in args if not a.startswith("--")]
    conn = get_conn()
    try:
        if names:
            ph = ",".join("?" * len(names))
            rows = conn.execute(
                "SELECT s.id, s.name, c.name AS city FROM spots s "
                "JOIN cities c ON c.id = s.city_id WHERE s.name IN (%s) ORDER BY s.id" % ph,
                names,
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT s.id, s.name, c.name AS city FROM spots s "
                "JOIN cities c ON c.id = s.city_id "
                "WHERE NOT EXISTS (SELECT 1 FROM notes n WHERE n.spot_id = s.id) "
                "ORDER BY s.id"
            ).fetchall()
    finally:
        conn.close()

    if not rows:
        print("没有需要采集的景区(全部已有笔记,或名称不匹配)")
        return

    print(f"待采集 {len(rows)} 个景区(注意:单账号每日上限 {xhs.DAILY_LIMIT} 次请求)")
    print("即将弹出浏览器窗口;若出现滑块验证请手动完成,完成后回终端按回车继续")
    for i, r in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] {r['city']} {r['name']}")
        try:
            xhs.collect_spot(r["id"], r["name"], r["city"], headless=headless)
        except RuntimeError as e:
            print(f"  中止采集: {e}")
            break
        except Exception as e:
            print(f"  采集失败: {e}")
            continue
        try:
            refresh_summary(r["id"], r["name"])
        except Exception as e:
            print(f"  [AI] 口碑卡更新失败: {e}")


if __name__ == "__main__":
    main()
