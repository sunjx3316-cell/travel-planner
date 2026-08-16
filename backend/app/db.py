# -*- coding: utf-8 -*-
"""SQLite 连接与初始化。"""
import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
# 测试可覆盖:TRAVEL_DB_PATH 环境变量
DB_PATH = Path(os.environ.get("TRAVEL_DB_PATH", str(DATA_DIR / "travel.db")))
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    from . import seed  # 延迟导入,避免循环依赖

    conn = get_conn()
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        # 轻量迁移:为旧库补列
        for col in ("lng", "lat", "grade", "price", "commercial", "amap_poi_id",
                    "data_source", "source_updated_at"):
            if col == "price":
                ddl = "ALTER TABLE spots ADD COLUMN price REAL"
            elif col == "commercial":
                ddl = "ALTER TABLE spots ADD COLUMN commercial TEXT"
            elif col in ("amap_poi_id", "data_source", "source_updated_at"):
                ddl = f"ALTER TABLE spots ADD COLUMN {col} TEXT"
            else:
                ddl = ("ALTER TABLE spots ADD COLUMN grade TEXT" if col == "grade"
                       else "ALTER TABLE spots ADD COLUMN %s REAL" % col)
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError:
                pass  # 列已存在
        # 轻量迁移:city_foods 补坐标列(美食街标注用)
        for col in ("lng", "lat"):
            try:
                conn.execute(f"ALTER TABLE city_foods ADD COLUMN {col} REAL")
            except sqlite3.OperationalError:
                pass
        conn.commit()
        count = conn.execute("SELECT COUNT(*) AS c FROM cities").fetchone()["c"]
        if count == 0:
            seed.seed_all(conn)
        seed.update_coords(conn)  # 新库补坐标 / 老库回填坐标
        seed.supplement_sample_notes(conn)  # 老库增量补种示例笔记(幂等)
        seed.seed_5a(conn)  # 全国 5A 景区扩充(幂等)
        seed.seed_loops(conn)  # 精选自驾环线(甘南等,幂等)
        seed.seed_4a(conn)  # 4A 级景区(首批,逐步完善)
        seed.seed_prices(conn)  # 门票参考价
        seed.seed_alternatives(conn)  # 高门票景点平替推荐
        seed.seed_stays(conn)  # 住宿推荐(区域级,防暗广)
        seed.seed_foods(conn)  # 城市美食(必吃小吃+美食街,区域级防暗广)
        seed.seed_food_spots(conn)  # 美食街升级为景点(可上图/加购物车/看口碑)
        seed.seed_landmarks(conn)  # 公园 + 商圈/商业街(与景点同机制)
        seed.seed_museums(conn)  # 著名博物馆(城市模式项目)
        seed.seed_popular(conn)  # 精选大众可玩景点(花市/海洋馆/主题乐园等)
    finally:
        conn.close()
