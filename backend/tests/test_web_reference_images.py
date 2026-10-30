import sqlite3

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from backend.app import db
from backend.app.routers.local_reference_images import reference_assets,reference_image

def request(peer='127.0.0.1',headers=()):
    return Request({'type':'http','method':'GET','scheme':'http','path':'/',
        'server':('127.0.0.1',8000),'client':(peer,12345),'query_string':b'',
        'headers':[(b'host',b'127.0.0.1:8000'),*headers]})

@pytest.fixture
def web_media(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DB_PATH',tmp_path/'travel.db')
    path=tmp_path/'private/web-photos/batch/photo.jpg';path.parent.mkdir(parents=True)
    path.write_bytes(b'\xff\xd8web-reference-fixture')
    with db.get_conn() as conn:
        conn.execute('CREATE TABLE spot_media(id INTEGER PRIMARY KEY,spot_id INTEGER,storage_path TEXT,provider TEXT,rights_status TEXT,origin_url TEXT,license_note TEXT,captured_at TEXT,created_at TEXT)')
        conn.execute('INSERT INTO spot_media VALUES(1,2,?,?,?,?,?,?,?)',
            ('private/web-photos/batch/photo.jpg','web_photo','pending','https://example.com/source','Private reference only','2026-10-30','2026-10-30'))
    return path

def test_web_reference_uses_own_label_and_private_root(web_media):
    response=reference_image(1,request())
    assert str(response.path)==str(web_media)
    assert response.headers['cache-control']=='private, no-store'
    with db.get_conn() as conn:
        assets=reference_assets(conn,2,request())
        assert assets[0]['provider']=='网页实景图 · 仅本机参考'
        assert assets[0]['rights_status']=='pending'

@pytest.mark.parametrize('peer,headers',[
    ('192.168.1.9',()),('127.0.0.1',((b'x-forwarded-for',b'127.0.0.1'),)),
    ('127.0.0.1',((b'origin',b'https://evil.example'),)),
    ('127.0.0.1',((b'sec-fetch-site',b'cross-site'),))])
def test_web_references_not_visible_to_other_clients(web_media,peer,headers):
    with pytest.raises(HTTPException) as error:reference_image(1,request(peer,headers))
    assert error.value.status_code==403
    with db.get_conn() as conn:assert reference_assets(conn,2,request(peer,headers))==[]

@pytest.mark.parametrize('path',[
    'private/web-photos/../../outside.jpg','private/xhs-screenshots/other.jpg',
    'private/web-photos/missing.jpg','private/web-photos/source.json'])
def test_web_reference_path_confinement(web_media,path):
    with db.get_conn() as conn:conn.execute('UPDATE spot_media SET storage_path=? WHERE id=1',(path,))
    with pytest.raises(HTTPException) as error:reference_image(1,request())
    assert error.value.status_code==404
