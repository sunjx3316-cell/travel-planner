# -*- coding: utf-8 -*-
"""景点分类器测试。"""
from backend.app.categories import classify_spot


def test_nature():
    assert classify_spot("九寨沟", []) == "自然"
    assert classify_spot("青海湖", []) == "自然"
    assert classify_spot("草原", ["草原"]) == "自然"
    assert classify_spot("茶卡盐湖", ["盐湖"]) == "自然"
    # 梅里雪山飞来寺:雪山(自然)+寺(人文) → 综合
    assert classify_spot("梅里雪山飞来寺", []) == "综合"


def test_human():
    assert classify_spot("故宫博物院", ["历史", "博物馆"]) == "人文"
    assert classify_spot("布达拉宫", []) == "人文"
    assert classify_spot("大昭寺", []) == "人文"
    assert classify_spot("莫高窟", []) == "人文"
    assert classify_spot("平遥古城", []) == "人文"
    assert classify_spot("禾木村", ["村落"]) == "人文"


def test_comprehensive():
    assert classify_spot("颐和园", ["园林", "湖泊"]) == "综合"
    assert classify_spot("五台山", ["佛教"]) == "综合"


def test_unknown_falls_back():
    assert classify_spot("某某秘境", []) in ("自然", "人文", "综合")
