# -*- coding: utf-8 -*-
"""城市规划推荐(/api/plans/cityplan-recommend)测试:每城天数 + 起始城 + 城市顺序。"""
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def _spot_ids(city_name, n=3):
    cities = client.get("/api/cities").json()
    city = next(c for c in cities if c["name"] == city_name)
    spots = client.get(f"/api/cities/{city['id']}/spots").json()
    assert len(spots) >= n, f"{city_name} 景点不足 {n}"
    return [s["id"] for s in spots[:n]]


def test_start_city_equals_departure_when_in_list():
    """出发地=西安 且西安在清单里 → 从西安开始"""
    ids = _spot_ids("西安", 3) + _spot_ids("兰州", 2)
    r = client.post("/api/plans/cityplan-recommend",
                    json={"spot_ids": ids, "total_days": 4, "start_city": "西安"})
    assert r.status_code == 200
    rec = r.json()
    assert rec["start_city"] == "西安"
    assert "出发" in rec["start_reason"]
    assert set(rec["order"]) == {"西安", "兰州"}
    assert rec["order"][0] == "西安"
    assert sum(rec["city_days"].values()) == 4
    assert 1 <= rec["city_days"]["兰州"] <= 3


def test_start_city_absent_picks_nearest():
    """出发地=成都 不在清单(西安+兰州) → 取最近城市(兰州)"""
    ids = _spot_ids("西安", 2) + _spot_ids("兰州", 2)
    r = client.post("/api/plans/cityplan-recommend",
                    json={"spot_ids": ids, "total_days": 5, "start_city": "成都"})
    assert r.status_code == 200
    rec = r.json()
    assert rec["start_city"] in ("西安", "兰州")
    assert "最近" in rec["start_reason"] or "不在行程" in rec["start_reason"]
    assert rec["order"][0] == rec["start_city"]
    assert set(rec["order"]) == {"西安", "兰州"}


def test_days_proportional_to_spot_count():
    """项目多的城市天数 ≥ 项目少的;总天数吻合"""
    ids = _spot_ids("西安", 6) + _spot_ids("兰州", 2)
    r = client.post("/api/plans/cityplan-recommend",
                    json={"spot_ids": ids, "total_days": 6, "start_city": ""})
    assert r.status_code == 200
    rec = r.json()
    assert rec["city_days"]["西安"] >= rec["city_days"]["兰州"]
    assert sum(rec["city_days"].values()) == 6
    assert all(d >= 1 for d in rec["city_days"].values())


def test_no_departure_falls_back_to_geo():
    """未填出发地 → 仍返回完整推荐,reason 提示可补充"""
    ids = _spot_ids("北京", 2) + _spot_ids("西安", 2)
    r = client.post("/api/plans/cityplan-recommend",
                    json={"spot_ids": ids, "total_days": 4, "start_city": ""})
    assert r.status_code == 200
    rec = r.json()
    assert rec["start_city"] in ("北京", "西安")
    assert "出发" in rec["start_reason"] or "未填" in rec["start_reason"]
    assert len(rec["order"]) == 2


def test_empty_cart_rejected():
    r = client.post("/api/plans/cityplan-recommend",
                    json={"spot_ids": [], "total_days": 3, "start_city": "西安"})
    assert r.status_code == 422   # 校验层拒绝空清单(与 citytour 一致)
