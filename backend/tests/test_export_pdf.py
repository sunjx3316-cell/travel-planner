from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.app.routers.export import router, calendar_period

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_rail_attached_pdf_and_time_validation():
    plan = {'name':'铁路联动测试','daily':[{'items':[{'spot':'桂林博物馆','time':'上午'}]}],
            'rail_journeys':[{'date':'2026-10-29','from':'天津','to':'桂林','risk':'需核实',
              'legs':[{'train':'G123','from':'天津西','to':'桂林北','departure':1380,'arrival':1920}]}]}
    response=client.post('/api/plans/export-pdf',json=plan)
    assert response.status_code==200
    text=''.join(p.extract_text() for p in PdfReader(BytesIO(response.content)).pages)
    assert 'G123' in text and '铁路交通' in text and '+1天' in text
    plan['rail_journeys'][0]['legs'][0]['arrival']=10
    assert client.post('/api/plans/export-pdf',json=plan).status_code==422


def test_confirmed_plan_pdf_chinese_and_no_stale_derived_results():
    response = client.post('/api/plans/export-pdf', json={
        'name': '北京专属行程', 'summary': '修改后的安排', 'workshop_changed': True,
        'daily': [{'items': [{'spot': '故宫博物院', 'time': '09:00-11:00', 'why': '提前预约 <不会执行>'}],
                   'stay': {'town': '过期住宿'}}], 'tips': ['过期交通建议']})
    assert response.status_code == 200
    assert response.content.startswith(b'%PDF')
    assert response.headers['cache-control'] == 'no-store'
    assert 'filename*=UTF-8' in response.headers['content-disposition']
    reader = PdfReader(BytesIO(response.content))
    text = ''.join(page.extract_text() for page in reader.pages)
    assert '故宫博物院' in text and '09:00-11:00' in text
    assert '<不会执行>' in text
    assert '过期住宿' not in text and '过期交通建议' not in text
    assert float(reader.pages[0].mediabox.width) > float(reader.pages[0].mediabox.height)
    assert '上午' in text and '下午' in text and '日历式行程表' in text


def test_calendar_grouping_and_all_days_preserved():
    assert calendar_period('09:00-11:00') == 'morning'
    assert calendar_period('下午') == 'afternoon'
    assert calendar_period('19:00-21:00') == 'other'
    assert calendar_period('全天') == 'other'
    assert calendar_period('25:00-26:00') == 'other'
    response = client.post('/api/plans/export-pdf', json={'daily': [
        {'items': [{'spot': f'地点{i}', 'time': '上午'}]} for i in range(9)]})
    assert response.status_code == 200
    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) >= 3
    text = ''.join(page.extract_text() for page in reader.pages)
    for i in range(9):
        assert f'地点{i}' in text and f'第 {i+1} 天' in text


def test_pdf_limits_and_multipage_long_chinese():
    assert client.post('/api/plans/export-pdf', json={'daily': []}).status_code == 422
    assert client.post('/api/plans/export-pdf', json={'daily': [{'items': [{'spot': 'x'*301}]}]}).status_code == 422
    response = client.post('/api/plans/export-pdf', json={'name': '长行程', 'daily': [
        {'note': '请核对预约。'*70, 'items': [{'spot': '景点 '+str(i), 'why': '保留交通休息时间。'*70} for i in range(5)]}
        for _ in range(5)]})
    assert response.status_code == 200
    assert len(PdfReader(BytesIO(response.content)).pages) > 1


def test_three_day_calendar_is_one_page_and_all_day_is_not_an_overflow_slot():
    response = client.post('/api/plans/export-pdf', json={
        'name': '漓江经典三日全览', 'summary': '首日漓江，次日博物馆和山水公园，第三日双塔与飞虎队遗址。',
        'daily': [
            {'items': [{'spot': '漓江风景名胜区', 'time': '全天', 'why': '桂林 · 5A景区', 'time_reason': '往返交通预留一整天'}]},
            {'items': [{'spot': '桂林博物馆', 'time': '上午'}, {'spot': '桂林市山水公园', 'time': '下午'}]},
            {'items': [{'spot': '日月双塔文化公园', 'time': '上午'}, {'spot': '桂林飞虎队遗址公园', 'time': '下午'}]},
        ]})
    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert 'ALL DAY / 全天' in text
    assert '其他时段' not in text and '无额外备注' not in text
    assert '桂林飞虎队遗址公园' in text


def test_long_cells_keep_their_final_text_and_distinguish_evening():
    response = client.post('/api/plans/export-pdf', json={'daily': [
        {'items': [{'spot': '夜游安排', 'time': '19:00-21:00', 'why': '很长的出行提醒。'*180 + '文本结束标记'}],
         'note': '次日注意事项'*120 + '备注结束标记'},
        {'items': [{'spot': '自由探索', 'time': '', 'why': '仅供参考'}]},
    ]})
    assert response.status_code == 200
    reader = PdfReader(BytesIO(response.content))
    text = ''.join(page.extract_text() for page in reader.pages)
    assert 'NIGHT / 晚间' in text and 'FLEX / 时间待定' in text
    joined = ''.join(text.split())
    assert '文本结束标记' in joined and '备注结束标记' in joined


def test_shared_travel_references_are_printed_once():
    day = {'items': [{'spot': '当天景点', 'time': '上午'}],
           'stay': {'town': '共同住宿区', 'price': '200-500'}, 'foods': {'dishes': [{'name': '共同美食'}]}}
    response = client.post('/api/plans/export-pdf', json={'daily': [day, day, day], 'tips': ['预约提醒', '返程提醒']})
    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) == 1
    text = ''.join(page.extract_text() for page in reader.pages)
    assert text.count('共同住宿区') == 1 and text.count('共同美食') == 1
    assert '预约提醒' in text and '返程提醒' in text


def test_driving_calendar_does_not_make_memo_only_pages():
    days = []
    for i in range(7):
        days.append({'note': '驾驶约 3.9h · 游览与驾驶合计约 6.4h（另留餐饮和休息）',
            'stay': {'town': f'第{i+1}天住宿参考区', 'price': '120-350/晚'},
            'foods': {'dishes': [{'name': '当地特色美食'}]},
            'items': [
                {'spot': f'转场：出发地 → 第{i+1}天目的地', 'time': '09:00-13:13',
                 'why': '驾驶约 3.2 小时，以导航复核；时间段含必要休息'},
                {'spot': f'第{i+1}天风景区', 'time': '13:13-15:43', 'why': '目的地 · 预留约 2.5 小时游览',
                 'time_reason': '参考时段：下午；开放时间待确认'},
                {'spot': '转场：风景区 → 次日目的地', 'time': '15:43-16:25',
                 'why': '驾驶约 0.7 小时，以导航复核；时间段含必要休息'}]})
    response = client.post('/api/plans/export-pdf', json={'name': '七日自驾行程', 'daily': days})
    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) == 3
    text = ''.join(page.extract_text() for page in reader.pages)
    assert '第7天风景区' in ''.join(text.split()) and '第7天住宿参考区' in ''.join(text.split())
