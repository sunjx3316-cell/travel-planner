from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from backend.app.routers.export import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


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


def test_pdf_limits_and_multipage_long_chinese():
    assert client.post('/api/plans/export-pdf', json={'daily': []}).status_code == 422
    assert client.post('/api/plans/export-pdf', json={'daily': [{'items': [{'spot': 'x'*301}]}]}).status_code == 422
    response = client.post('/api/plans/export-pdf', json={'name': '长行程', 'daily': [
        {'note': '请核对预约。'*70, 'items': [{'spot': '景点 '+str(i), 'why': '保留交通休息时间。'*70} for i in range(5)]}
        for _ in range(5)]})
    assert response.status_code == 200
    assert len(PdfReader(BytesIO(response.content)).pages) > 1
