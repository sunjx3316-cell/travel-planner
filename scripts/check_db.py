# -*- coding: utf-8 -*-
"""检查正式库状态:坐标回填 / 去重索引 / 示例数据。"""
import sqlite3

conn = sqlite3.connect(r"D:\Harness工作区\travel-planner\data\travel.db")
conn.row_factory = sqlite3.Row
try:
    n = conn.execute("SELECT COUNT(*) c FROM spots WHERE lng IS NOT NULL").fetchone()["c"]
    total = conn.execute("SELECT COUNT(*) c FROM spots").fetchone()["c"]
    idx = conn.execute(
        "SELECT COUNT(*) c FROM sqlite_master WHERE type='index' AND name='idx_notes_source'"
    ).fetchone()["c"]
    gugong = conn.execute("SELECT lng, lat FROM spots WHERE name='故宫博物院'").fetchone()
    notes = conn.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"]
    print(f"带坐标景区: {n}/{total} | 去重索引: {idx} | 笔记总数: {notes}")
    print(f"故宫坐标: {tuple(gugong)}")
finally:
    conn.close()
