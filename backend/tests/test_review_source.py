# -*- coding: utf-8 -*-
"""评价采集框架测试:入库/去重/自动分类/评分/口碑卡重算。"""
import json
import sqlite3

from backend.app.db import get_conn
from backend.collector import review_source


def _spot_id(conn):
    return conn.execute("SELECT id FROM spots LIMIT 1").fetchone()["id"]


def test_auto_classify():
    assert review_source.auto_classify("排队2小时门票60,坑") == "avoid"
    assert review_source.auto_classify("从东门进,先看主殿,再沿湖走一圈") == "guide"
    assert review_source.auto_classify("攻略不错但排队太久") == "mixed"


def test_ingest_creates_note_and_summary():
    conn = get_conn()
    sid = _spot_id(conn)
    r = review_source.ingest_items(sid, [{
        "type": "avoid", "title": "实测", "content": "下午缆车排队2小时,门票90不值,建议上午去",
        "author": "张三", "source": "ctrip",
    }], conn=conn)
    assert r["added"] == 1 and r["summary"] is True
    note = conn.execute("SELECT * FROM notes WHERE spot_id=?", (sid,)).fetchone()
    assert note["note_type"] == "avoid"
    assert note["is_sample"] == 0
    assert note["author_hash"] and note["author_hash"] != "张三"  # 匿名化
    card = json.loads(conn.execute(
        "SELECT summary_json FROM spot_summaries WHERE spot_id=?", (sid,)).fetchone()["summary_json"])
    assert card["note_count"] >= 1
    conn.close()


def test_dedupe_same_content():
    conn = get_conn()
    sid = _spot_id(conn)
    it = {"type": "guide", "content": "重复内容测试12345", "source": "paste"}
    r1 = review_source.ingest_items(sid, [dict(it)], conn=conn)
    r2 = review_source.ingest_items(sid, [dict(it)], conn=conn)
    assert r1["added"] == 1
    assert r2["added"] == 0   # 内容哈希去重
    conn.close()


def test_score_updates_poi_rating():
    conn = get_conn()
    sid = _spot_id(conn)
    r = review_source.ingest_items(sid, [{
        "type": "guide", "content": "", "score": 4.6, "comment_count": 21000, "source": "amap",
    }], conn=conn)
    assert r["added"] == 0 and r["scores"] >= 1
    rating = conn.execute("SELECT poi_rating FROM spots WHERE id=?", (sid,)).fetchone()["poi_rating"]
    assert rating == 4.6
    conn.close()


def test_normalize_validation():
    try:
        review_source.normalize_item({"content": ""})
        raise AssertionError("应拒绝空 content")
    except ValueError:
        pass
    try:
        review_source.normalize_item({"content": "x", "type": "bad"})
        raise AssertionError("应拒绝非法 type")
    except ValueError:
        pass
    n = review_source.normalize_item({"content": "排队久", "type": ""})
    assert n["type"] in ("guide", "avoid", "mixed")


def test_list_missing():
    conn = get_conn()
    missing = review_source.list_missing(conn=conn, limit=5)
    assert isinstance(missing, list)
    if missing:
        assert "name" in missing[0] and "city" in missing[0]
    conn.close()
