# -*- coding: utf-8 -*-
"""高德 POI 模块测试(模拟 HTTP 响应,无需真实 key)。"""
import sqlite3

import pytest

from backend.collector import amap_poi


class FakeResp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p

    def raise_for_status(self):
        return None


AMAP_OK = {
    "status": "1",
    "info": "OK",
    "pois": [
        {"id": "AMAP-A", "name": "测试景区A", "address": "某路1号", "location": "116.1,39.9",
         "type": "风景名胜;国家级景点", "biz_ext": {"rating": "4.8"}},
        {"name": "测试景区B", "address": "", "location": "bad",   # 坐标非法,应跳过
         "type": "", "biz_ext": {}},
        {"name": "测试景区C", "address": "某路3号", "location": "117.2,40.1",
         "type": "公园", "biz_ext": {"rating": "3.9"}},
    ],
}


def test_get_key_raises_without_key(monkeypatch):
    monkeypatch.delenv("AMAP_KEY", raising=False)
    with pytest.raises(RuntimeError, match="AMAP_KEY"):
        amap_poi.get_key()


def test_fetch_scenic_spots_parses(monkeypatch):
    captured = {}

    def fake_get(url, **kwargs):
        captured["params"] = kwargs.get("params", {})
        return FakeResp(AMAP_OK)

    monkeypatch.setattr("backend.collector.amap_poi.requests.get", fake_get)
    monkeypatch.setattr(amap_poi, "get_key", lambda: "test-key")

    pois = amap_poi.fetch_scenic_spots("北京")
    assert len(pois) == 2              # 非法坐标被跳过
    assert pois[0]["rating"] == 4.8
    assert pois[0]["amap_id"] == "AMAP-A"
    assert pois[0]["lng"] == 116.1 and pois[0]["lat"] == 39.9
    assert captured["params"]["key"] == "test-key"
    assert captured["params"]["city"] == "北京"
    assert captured["params"]["keywords"] == "景点"


def test_fetch_scenic_spots_error_status(monkeypatch):
    monkeypatch.setattr(amap_poi, "get_key", lambda: "test-key")
    monkeypatch.setattr(
        "backend.collector.amap_poi.requests.get",
        lambda url, **kw: FakeResp({"status": "0", "info": "INVALID_USER_KEY"}),
    )
    with pytest.raises(RuntimeError, match="INVALID_USER_KEY"):
        amap_poi.fetch_scenic_spots("北京")


def test_import_into_db_dedup():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE spots (id INTEGER PRIMARY KEY, city_id INTEGER, name TEXT, "
        "poi_rating REAL, address TEXT, tags TEXT, lng REAL, lat REAL, "
        "amap_poi_id TEXT, data_source TEXT, source_updated_at TEXT, "
        "UNIQUE(city_id, name))"
    )
    conn.execute("CREATE TABLE spot_sources (id INTEGER PRIMARY KEY, spot_id INTEGER, provider TEXT, external_id TEXT, source_url TEXT, payload_json TEXT, fetched_at TEXT, confidence REAL, UNIQUE(spot_id, provider, external_id))")
    pois = [{"amap_id": "B0TEST", "name": "新景区", "address": "a", "rating": 4.5, "lng": 1.0, "lat": 2.0,
             "type": "风景名胜", "typecode": "110000", "keyword": "景点"}]
    assert amap_poi.import_into_db(conn, 1, pois) == 1
    row = conn.execute("SELECT * FROM spots").fetchone()
    assert row[2] == "新景区" and row[3] == 4.5
    assert amap_poi.import_into_db(conn, 1, pois) == 0  # 同名去重
    assert conn.execute("SELECT COUNT(*) FROM spot_sources").fetchone()[0] == 1


def test_fetch_keyword_pois(monkeypatch):
    """地区+关键词搜索:解析/去重/空名过滤"""
    captured = {}

    def fake_get(url, **kwargs):
        captured["params"] = kwargs.get("params", {})
        return FakeResp({"status": "1", "info": "OK", "pois": [
            {"name": "桑科草原", "address": "a", "location": "102.4,35.1", "type": "风景名胜"},
            {"name": "当周草原", "address": "b", "location": "102.9,34.9", "type": "风景名胜"},
            {"name": "桑科草原", "address": "a", "location": "102.4,35.1", "type": "风景名胜"},  # 重复
            {"name": "", "address": "", "location": "0,0", "type": ""},  # 空名
        ]})

    monkeypatch.setattr("backend.collector.amap_poi.requests.get", fake_get)
    monkeypatch.setattr(amap_poi, "get_key", lambda: "k")
    pois = amap_poi.fetch_keyword_pois("甘南藏族自治州", ["草原"], limit=10)
    assert len(pois) == 2
    assert captured["params"]["city"] == "甘南藏族自治州"
    assert pois[0]["keyword"] == "草原"


def test_fetch_around_pois(monkeypatch):
    """周边搜索:location 参数与解析"""
    captured = {}

    def fake_get(url, **kwargs):
        captured["params"] = kwargs.get("params", {})
        return FakeResp({"status": "1", "info": "OK", "pois": [
            {"name": "湖畔营地", "address": "c", "location": "102.5,35.2", "type": "休闲"},
        ]})

    monkeypatch.setattr("backend.collector.amap_poi.requests.get", fake_get)
    monkeypatch.setattr(amap_poi, "get_key", lambda: "k")
    pois = amap_poi.fetch_around_pois(102.5, 35.2, ["湖泊"], radius=20000)
    assert len(pois) == 1
    assert captured["params"]["location"] == "102.5,35.2"
    assert captured["params"]["radius"] == 20000


def test_import_explore_pois_creates_city():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE cities (id INTEGER PRIMARY KEY, name TEXT UNIQUE, province TEXT, lng REAL, lat REAL)")
    conn.execute(
        "CREATE TABLE spots (id INTEGER PRIMARY KEY, city_id INTEGER, name TEXT, address TEXT, "
        "tags TEXT, lng REAL, lat REAL, UNIQUE(city_id, name))"
    )
    pois = [{"name": "绝美山谷", "address": "x", "lng": 102.0, "lat": 34.0, "keyword": "峡谷"}]
    n = amap_poi.import_explore_pois(conn, "甘南州", "甘肃省", pois)
    assert n == 1
    city = conn.execute("SELECT * FROM cities").fetchone()
    assert city[1] == "甘南州"          # 城市自动创建
    assert city[3] is not None          # 中心坐标
    spot = conn.execute("SELECT * FROM spots").fetchone()
    assert "探索发现" in spot[4] and "峡谷" in spot[4]
