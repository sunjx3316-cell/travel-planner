"""Pending release references remain local-only and never become licensed assets."""
import hashlib
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app import db
from backend.app.main import app


@pytest.fixture(params=['xhs_screenshot', 'web_photo'])
def bundled_reference(tmp_path,monkeypatch,request):
    database=tmp_path/'data/travel.db';database.parent.mkdir()
    with db.get_conn() as original,sqlite3.connect(database) as target:
        original.backup(target)
    monkeypatch.setattr(db,'DB_PATH',database)
    monkeypatch.setattr(db,'PROJECT_ROOT',tmp_path)
    content=b'\xff\xd8\xffbundled-reference-fixture'
    filename=hashlib.sha256(content).hexdigest()+'.jpg'
    photo=tmp_path/'bundled_data/reference-photos'/filename
    photo.parent.mkdir(parents=True);photo.write_bytes(content)
    provider=request.param
    folder='xhs-screenshots' if provider=='xhs_screenshot' else 'web-photos'
    with db.get_conn() as c:
        sid=c.execute('SELECT id FROM spots LIMIT 1').fetchone()[0]
        media=c.execute('''INSERT INTO spot_media
            (spot_id,storage_path,origin_url,provider,license_note,rights_status,captured_at,created_at)
            VALUES(?,?,?,?,?,?,?,?)''',(sid,'private/'+folder+'/release-references/'+filename,
            'https://example.com/scenic-photo',provider,
            'Cropped reference; authorization not verified','pending','2026-10-29','2026-10-29')).lastrowid
    return sid,media,photo


def owner(peer='127.0.0.1'):
    return TestClient(app,base_url='http://127.0.0.1:8000',client=(peer,1000))


def test_bundled_reference_fallback_preserves_pending(bundled_reference):
    sid,mid,photo=bundled_reference
    assert not (db.DB_PATH.parent/'private/xhs-screenshots/release-references'/photo.name).exists()
    with owner() as client:
        response=client.get(f'/api/local-reference-images/{mid}')
        assert response.status_code==200 and response.content==photo.read_bytes()
        assert response.headers['cache-control']=='private, no-store'
        detail=client.get(f'/api/spots/{sid}').json()
        asset=next(a for a in detail['image_assets'] if a.get('local_reference'))
        assert asset['rights_status']=='pending'
    with db.get_conn() as c:
        assert c.execute('SELECT rights_status FROM spot_media WHERE id=?',(mid,)).fetchone()[0]=='pending'


@pytest.mark.parametrize('peer,headers',[
    ('192.168.1.9',{}),
    ('127.0.0.1',{'X-Forwarded-For':'127.0.0.1'}),
    ('127.0.0.1',{'Origin':'https://evil.example'}),
    ('127.0.0.1',{'Sec-Fetch-Site':'cross-site'}),
])
def test_bundled_reference_not_exposed_to_other_clients(bundled_reference,peer,headers):
    sid,mid,_=bundled_reference
    with owner(peer) as client:
        assert client.get(f'/api/local-reference-images/{mid}',headers=headers).status_code==403
        detail=client.get(f'/api/spots/{sid}',headers=headers).json()
        assert not any(a.get('local_reference') for a in detail['image_assets'])


@pytest.mark.parametrize('registered_path',[
    'private/xhs-screenshots/unreviewed-photo.jpg',
    'private/xhs-screenshots/release-references/not-a-hash.jpg',
    'private/xhs-screenshots/../../outside.jpg',
])
def test_only_exact_release_reference_paths_can_fallback(bundled_reference,registered_path):
    _,mid,_=bundled_reference
    with db.get_conn() as c:
        c.execute('UPDATE spot_media SET storage_path=? WHERE id=?',(registered_path,mid))
    with owner() as client:
        assert client.get(f'/api/local-reference-images/{mid}').status_code==404
