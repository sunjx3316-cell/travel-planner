# -*- coding: utf-8 -*-
"""采集入口的名单约束，避免城市别名与本地种子库脱节。"""
from scripts.fetch_poi import PILOT_CITIES


def test_pilot_cities_use_seed_city_names():
    assert len(PILOT_CITIES) == len(set(PILOT_CITIES)) == 20
    # 种子库使用行政区全称“黄山市”；“黄山”会导致该城市被静默跳过。
    assert "黄山市" in PILOT_CITIES
    assert "黄山" not in PILOT_CITIES
