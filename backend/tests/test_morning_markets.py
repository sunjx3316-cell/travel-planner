from backend.app.schedule import MORNING, EVENING, recommend_time
from backend.app.routers.plans import _classify_spot, _build_city_plan
import sqlite3
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def isolated_catalog(tmp_path, monkeypatch):
    from backend.app import db
    target = tmp_path / 'travel.db'
    catalog = Path(__file__).resolve().parents[2] / 'bundled_data/travel.db'
    with sqlite3.connect(catalog.as_uri() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(target) as destination:
            source.backup(destination)
    monkeypatch.setattr(db, 'DB_PATH', target)


def test_morning_market_overrides_food_street_and_commercial_tags():
    spot = {'name': '青云民生市场', 'tags': ['美食街', '早市'], 'lng': 109.409, 'lat': 24.312,
            'commercial': {'type': '娱乐'}}
    assert recommend_time(spot['name'], spot['tags'], spot['commercial'])[0] == MORNING
    assert _classify_spot(spot, (109.411, 24.314)) == 'small'
    assert recommend_time('普通美食街', ['美食街'])[0] == EVENING


def test_morning_market_is_not_absorbed_into_adjacent_night_market():
    from backend.app.routers.plans import _compose_city_days
    morning = {'id': 1, 'name': '青云民生市场', 'tags': ['美食街', '早市'],
               'lng': 109.409, 'lat': 24.312, 'rating': 0, 'city_name': '柳州'}
    night = {'id': 2, 'name': '测试夜市', 'tags': ['夜市'],
             'lng': 109.410, 'lat': 24.312, 'rating': 0, 'city_name': '柳州'}
    chunks, overflow, _ = _compose_city_days([morning, night], 1, (109.411, 24.314))
    assert not overflow
    assert morning in chunks[0]
    city = {'id': 0, 'name': '柳州', 'city_name': '柳州', 'lng': 109.411, 'lat': 24.314, 'rating': 0}
    plan = _build_city_plan('test', 'test', [city], {'柳州': [morning, night]}, 1, '轻松', False)
    items = [it for day in plan['daily'] for it in day['items']]
    assert next(it for it in items if '青云' in it['spot'])['time'] == MORNING
    assert next(it for it in items if '测试夜市' in it['spot'])['time'] == EVENING


def test_arrival_cannot_relabel_breakfast_as_afternoon():
    market = {'id': 1, 'name': '青云民生市场', 'tags': ['美食街', '早市'],
              'lng': 109.409, 'lat': 24.312, 'rating': 0, 'city_name': '柳州'}
    city = {'id': 0, 'name': '柳州', 'city_name': '柳州', 'lng': 109.411, 'lat': 24.314, 'rating': 0}
    start = {'id': -1, 'name': '出发地', 'city_name': '出发地', 'lng': 108.32, 'lat': 22.82, 'rating': 0}
    plan = _build_city_plan('test', 'test', [start, city], {'柳州': [market]}, 1, '轻松', False)
    assert not any('青云' in it['spot'] for day in plan['daily'] for it in day['items'])
    assert any('青云' in it['spot'] for it in plan['unscheduled'])
