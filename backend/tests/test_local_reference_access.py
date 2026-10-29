import sqlite3

import pytest
from starlette.requests import Request
from fastapi import HTTPException

from backend.app.routers.local_reference_images import local_owner, reference_image

def request(peer='127.0.0.1', host='127.0.0.1:8000', headers=()):
    return Request({'type': 'http', 'method': 'GET', 'scheme': 'http', 'path': '/',
                    'server': ('127.0.0.1', 8000), 'client': (peer, 12345),
                    'query_string': b'', 'headers': [(b'host', host.encode()), *headers]})

@pytest.mark.parametrize('r', [request(peer='192.168.1.5'), request(host='evil.example'),
    request(headers=[(b'x-forwarded-for', b'127.0.0.1')]),
    request(headers=[(b'origin', b'https://evil.example')]),
    request(headers=[(b'sec-fetch-site', b'cross-site')])])
def test_external_or_spoofed_reference_access_denied(r):
    assert not local_owner(r)
    with pytest.raises(HTTPException) as error:
        reference_image(1, r)
    assert error.value.status_code == 403

def test_pending_reference_remains_private_and_path_confined(tmp_path, monkeypatch):
    from backend.app import db
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'travel.db')
    image = tmp_path / 'private/xhs-screenshots/test.jpg'
    image.parent.mkdir(parents=True)
    image.write_bytes(b'\xff\xd8test')
    with db.get_conn() as conn:
        conn.execute('CREATE TABLE spot_media(id INTEGER PRIMARY KEY,storage_path TEXT,provider TEXT,rights_status TEXT)')
        conn.execute('INSERT INTO spot_media VALUES(1,?,?,?)', ('private/xhs-screenshots/test.jpg', 'xhs_screenshot', 'pending'))
    response = reference_image(1, request())
    assert response.headers['cache-control'] == 'private, no-store'
    with db.get_conn() as conn:
        assert conn.execute('SELECT rights_status FROM spot_media').fetchone()[0] == 'pending'
        conn.execute("UPDATE spot_media SET storage_path='private/xhs-screenshots/../../outside.jpg'")
    with pytest.raises(HTTPException) as error:
        reference_image(1, request())
    assert error.value.status_code == 404
