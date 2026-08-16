# -*- coding: utf-8 -*-
"""2-opt 消除路线交叉测试。"""
from backend.app.routers import plans


def _orient(a, b, c):
    return (b["lng"] - a["lng"]) * (c["lat"] - a["lat"]) - (b["lat"] - a["lat"]) * (c["lng"] - a["lng"])


def _cross(a, b, c, d):
    return _orient(a, b, c) * _orient(a, b, d) < 0 and _orient(c, d, a) * _orient(c, d, b) < 0


def _count_crossings(order):
    """统计闭环中非相邻边段的交叉数。"""
    n = len(order)
    cnt = 0
    for i in range(n):
        for j in range(i + 1, n):
            if j - i == 1 or (i == 0 and j == n - 1):
                continue  # 相邻边
            if _cross(order[i], order[(i + 1) % n], order[j], order[(j + 1) % n]):
                cnt += 1
    return cnt


def _spot(lng, lat):
    return {"name": f"{lng},{lat}", "lng": lng, "lat": lat, "rating": 0, "city_name": "测试城"}


def test_tour_len_includes_closing_leg():
    pts = [_spot(0, 0), _spot(3, 0), _spot(3, 4)]
    assert plans._tour_len(pts) > 10   # 两段 + 闭合段(4+3+5=12)


def test_two_opt_removes_crossing():
    """蝴蝶结形交叉布局:2-opt 后应无交叉且总长更短"""
    # (0,0)→(10,10)→(0,10)→(10,0) 会形成交叉
    pts = [_spot(0, 0), _spot(10, 10), _spot(0, 10), _spot(10, 0)]
    before = _count_crossings(pts)
    opt = plans._two_opt(pts)
    after = _count_crossings(opt)
    assert before >= 1
    assert after == 0
    assert plans._tour_len(opt) < plans._tour_len(pts)


def test_two_opt_no_worse_on_small_loop():
    pts = [_spot(102.5, 35.2), _spot(103.2, 34.2), _spot(102.6, 34.1),
           _spot(102.0, 34.0), _spot(101.3, 33.7)]
    opt = plans._two_opt(pts)
    assert plans._tour_len(opt) <= plans._tour_len(pts) + 1e-9
