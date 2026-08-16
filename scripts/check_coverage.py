# -*- coding: utf-8 -*-
"""检查各景区笔记与口碑卡覆盖情况。"""
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

conn = sqlite3.connect(r"D:\Harness工作区\travel-planner\data\travel.db")
conn.row_factory = sqlite3.Row
try:
    total = conn.execute("SELECT COUNT(*) c FROM spots").fetchone()["c"]
    with_notes = conn.execute(
        "SELECT COUNT(DISTINCT spot_id) c FROM notes"
    ).fetchone()["c"]
    with_summary = conn.execute(
        "SELECT COUNT(*) c FROM spot_summaries"
    ).fetchone()["c"]

    print(f"景区总数: {total} | 有笔记: {with_notes} | 有AI口碑卡: {with_summary}")
    print()
    print("--- 有口碑卡的景区(可分析) ---")
    rows = conn.execute(
        """SELECT c.name city, s.name, COUNT(n.id) notes
           FROM spot_summaries ss
           JOIN spots s ON s.id = ss.spot_id
           JOIN cities c ON c.id = s.city_id
           LEFT JOIN notes n ON n.spot_id = s.id
           GROUP BY s.id ORDER BY c.id, s.id"""
    ).fetchall()
    for r in rows:
        src = "?"
        try:
            import json
            src = json.loads(conn.execute(
                "SELECT summary_json FROM spot_summaries WHERE spot_id=?",
                (conn.execute("SELECT id FROM spots WHERE name=? AND city_id=(SELECT id FROM cities WHERE name=?)",
                              (r["name"], r["city"])).fetchone()["id"],)).fetchone()[0]).get("source", "?")
        except Exception:
            pass
        print(f"  {r['city']} {r['name']}: {r['notes']} 篇笔记 | {src}")

    print()
    print("--- 没有笔记、也没有口碑卡的景区 ---")
    rows2 = conn.execute(
        """SELECT c.name city, s.name FROM spots s
           JOIN cities c ON c.id = s.city_id
           WHERE NOT EXISTS (SELECT 1 FROM notes n WHERE n.spot_id = s.id)
           ORDER BY c.id, s.id"""
    ).fetchall()
    for r in rows2:
        print(f"  {r['city']} {r['name']}")
finally:
    conn.close()
