import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.routers.plans import _compose_city_days

client = TestClient(app)


def ids_for(*pairs):
    cities = {c["name"]: c["id"] for c in client.get('/api/cities').json()}
    return [next(s['id'] for s in client.get(f'/api/cities/{cities[city]}/spots').json() if s['name'] == name)
            for city, name in pairs]


def test_city_open_route_never_forces_return_and_respects_days():
    ids = ids_for(('桂林', '漓江风景名胜区'), ('桂林', '象鼻山'), ('南宁', '广西壮族自治区博物馆'))
    response = client.post('/api/plans/citytour', json={'spot_ids': ids, 'days': 3, 'start_city': '桂林', 'close_loop': False})
    assert response.status_code == 200
    for entry in response.json():
        plan = entry['plan']
        assert len(plan['daily']) == 3
        assert not any(leg.get('closing') for leg in plan['route'])
        assert not any('返程' in day.get('note', '') for day in plan['daily'])
        assert plan['generation']['state'] == 'local'


def test_city_days_constraints_and_missing_city_default():
    ids = ids_for(('北京', '恭王府'), ('西安', '陕西历史博物馆'))
    assert client.post('/api/plans/citytour', json={'spot_ids': ids, 'days': 1}).status_code == 400
    assert client.post('/api/plans/cityplan-recommend', json={'spot_ids': ids, 'total_days': 1}).status_code == 400
    for mapping in ({'北京': 3, '西安': 3}, {'北京': -1}, {'北京': 31}):
        assert client.post('/api/plans/citytour', json={'spot_ids': ids, 'days': 3, 'city_days': mapping}).status_code == 400
    r = client.post('/api/plans/citytour', json={'spot_ids': ids, 'days': 4, 'city_days': {'北京': 2}})
    assert r.status_code == 200
    assert all(len(p['plan']['daily']) == 4 for p in r.json())


def test_arrival_reorders_full_day_excursion():
    ids = ids_for(('兰州', '甘肃省博物馆'), ('西安', '秦始皇兵马俑博物馆'), ('西安', '陕西历史博物馆'))
    r = client.post('/api/plans/citytour', json={'spot_ids': ids, 'days': 3, 'start_city': '兰州', 'city_days': {'兰州': 1, '西安': 2}})
    plan = r.json()[0]['plan']
    xa = [day for day in plan['daily'] if '西安' in day['title']]
    assert not any(it.get('time') == '全天' for it in xa[0]['items'])
    assert any(it['spot'] == '秦始皇兵马俑博物馆' for it in xa[1]['items'])


def test_rest_insertion_never_exceeds_requested_days():
    spots = [{'id': i, 'name': f'测试公园{i}', 'lng': 110 + i * .01, 'lat': 30,
              'tags': ['公园'], 'rating': 4.5, 'commercial': None} for i in range(5)]
    chunks, overflow, rest = _compose_city_days(spots, 6, (110, 30), 'C')
    assert len(chunks) == len(rest) == 6
    assert not overflow
    assert sum(len(chunk) for chunk in chunks) == 5


def test_remote_night_market_not_added_to_full_day():
    big = {'id': 1, 'name': '测试乐园', 'lng': 110, 'lat': 30, 'tags': [], 'rating': 4.5}
    night = {'id': 2, 'name': '测试夜市', 'lng': 110.2, 'lat': 30, 'tags': [], 'rating': 4.5}
    chunks, overflow, _ = _compose_city_days([big, night], 1, (110, 30))
    assert chunks == [[big]]
    assert night in overflow


@pytest.mark.parametrize('style,cap,budget', [('轻松', 5, 7.5), ('紧凑', 6, 9), ('亲子', 4.5, 7)])
def test_gannan_loop_budget_all_spots_accounted_for(style, cap, budget, monkeypatch):
    monkeypatch.setattr('backend.ai.llm.requests.post', lambda *a, **k: pytest.fail('No AI in local mode'))
    loop = next(lp for lp in client.get('/api/loops').json() if lp['name'] == '甘南环线')
    ids = [s['id'] for s in loop['spots']]
    r = client.post('/api/plans/roadtrip', json={'spot_ids': ids, 'days': 7, 'style': style, 'start_city': '兰州'})
    assert r.status_code == 200
    for record in r.json():
        p = record['plan']
        assert len(p['daily']) == 7
        assert p['required_days'] >= 1
        assert all(day['driving_hours'] <= cap + .01 and day['activity_hours'] <= budget + .01 for day in p['daily'])
        items = [it for day in p['daily'] for it in day['items']] + p['unscheduled']
        assert {it['spot_id'] for it in items if 'spot_id' in it} == set(ids)
        assert len([it for it in items if 'spot_id' in it]) == len(ids)
        if p['route'][-1]['km'] > 1 and p['route_incomplete']:
            assert any(it['spot'].startswith('返程：') for it in items)
        assert all('rail' not in leg['transport'] for leg in p['route'])
    assert r.json()[1]['plan']['route_incomplete'] is False


def test_few_spots_many_days_keeps_requested_length():
    ids = ids_for(('北京', '恭王府'), ('北京', '故宫博物院'))
    r = client.post('/api/plans/roadtrip', json={'spot_ids': ids, 'days': 8, 'close_loop': False})
    assert r.status_code == 200
    assert all(len(p['plan']['daily']) == 8 for p in r.json())


def test_failed_ai_returns_three_local_plans(ai_config, monkeypatch):
    import requests
    ai_config.update(mode='ai', api_key='fake-key')
    def fail(*args, **kwargs): raise requests.Timeout('redact this')
    monkeypatch.setattr('backend.ai.llm.requests.post', fail)
    ids = ids_for(('北京', '恭王府'), ('北京', '故宫博物院'))
    for endpoint in ('citytour', 'roadtrip'):
        r = client.post('/api/plans/' + endpoint, json={'spot_ids': ids, 'days': 3})
        assert r.status_code == 200 and len(r.json()) == 3
        assert all(p['plan']['generation']['state'] == 'fallback' for p in r.json())
        assert all('超时' in p['plan']['generation']['message'] for p in r.json())
