# -*- coding: utf-8 -*-
"""沿路线挖掘工具测试(纯逻辑,无需网络)。"""
from backend.collector import route_explore


def test_collect_discoveries_dedupe_and_skip_existing():
    centers = [{"name": "A", "lng": 1.0, "lat": 1.0},
               {"name": "B", "lng": 2.0, "lat": 2.0}]

    def fake_fetch(lng, lat):
        if lng == 1.0:
            return [{"name": "新景点X", "address": "a", "lng": 1.1, "lat": 1.1,
                     "type": "风景", "keyword": "草原"},
                    {"name": "已收录景点", "address": "b", "lng": 1.2, "lat": 1.2,
                     "type": "风景", "keyword": "湖泊"}]
        return [{"name": "新景点X", "address": "a", "lng": 1.1, "lat": 1.1,
                 "type": "风景", "keyword": "草原"}]  # 与 A 中心重复

    found = route_explore.collect_discoveries(
        centers, fake_fetch, existing_names=["已收录景点", "A", "B"]
    )
    assert len(found) == 1                     # 去重 + 排除已有
    assert found[0]["name"] == "新景点X"
    assert found[0]["near"] == "A"             # 标记附近中心点


def test_route_centers_from_loop():
    centers = route_explore.route_centers_from_loop("甘南环线")
    assert len(centers) >= 15
    zhalana = next(c for c in centers if c["name"] == "扎尕那")
    assert zhalana["lng"] is not None and zhalana["lat"] is not None


def test_route_centers_unknown_loop():
    import pytest

    with pytest.raises(ValueError, match="未找到环线"):
        route_explore.route_centers_from_loop("不存在的环线")
