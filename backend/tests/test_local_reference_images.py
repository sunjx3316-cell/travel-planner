import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.app import db
from backend.app.main import app


@pytest.fixture
def private_media(tmp_path, monkeypatch):
    database = tmp_path / 'travel.db'
    with db.get_conn() as original, sqlite3.connect(database) as copy:
        original.backup(copy)
    monkeypatch.setattr(db, 'DB_PATH', database)
    image = tmp_path / 'private/xhs-screenshots/sample.jpg'
    image.parent.mkdir(parents=True)
    image.write_bytes(b'\xff\xd8\xfftest-image')
    with db.get_conn() as conn:
        spot_id = conn.execute('SELECT id FROM spots LIMIT 1').fetchone()[0]
        cur = conn.execute('''INSERT INTO spot_media
            (spot_id,storage_path,origin_url,provider,license_note,rights_status,captured_at,created_at)
            VALUES(?,?,?,?,?,?,?,?)''', (spot_id, 'private/xhs-screenshots/sample.jpg',
            'https://www.xiaohongshu.com/explore/example', 'xhs_screenshot',
            'Private reference, public reuse not authorized', 'pending', '2026-10-28', '2026-10-28'))
        media_id = cur.lastrowid
    return spot_id, media_id, image


def owner_client(host='127.0.0.1', peer='127.0.0.1'):
    return TestClient(app, base_url=f'http://{host}:8000', client=(peer, 12345))


def test_owner_can_view_but_rights_stay_pending(private_media):
    spot, media, image = private_media
    with owner_client() as client:
        details = client.get(f'/api/spots/{spot}').json()
        reference = next(a for a in details['image_assets'] if a.get('local_reference'))
        assert reference['rights_status'] == 'pending'
        response = client.get(reference['storage_path'])
        assert response.status_code == 200 and response.content == image.read_bytes()
        assert response.headers['cache-control'] == 'private, no-store'
        assert client.get('/data/private/xhs-screenshots/sample.jpg').status_code == 404


@pytest.mark.parametrize('host,peer,headers', [
    ('127.0.0.1', '192.168.1.5', {}), ('evil.example', '127.0.0.1', {}),
    ('127.0.0.1', '127.0.0.1', {'X-Forwarded-For': '127.0.0.1'}),
    ('127.0.0.1', '127.0.0.1', {'Origin': 'https://evil.example'}),
    ('127.0.0.1', '127.0.0.1', {'Sec-Fetch-Site': 'cross-site'}),
])
def test_non_owner_cannot_list_or_read(private_media, host, peer, headers):
    spot, media, _ = private_media
    with owner_client(host, peer) as client:
        detail = client.get(f'/api/spots/{spot}', headers=headers).json()
        assert not any(a.get('local_reference') for a in detail['image_assets'])
        assert client.get(f'/api/local-reference-images/{media}', headers=headers).status_code == 403


def test_registered_path_cannot_escape_private_root(private_media, tmp_path):
    _, media, _ = private_media
    (tmp_path / 'outside.jpg').write_bytes(b'private')
    with db.get_conn() as conn:
        conn.execute('UPDATE spot_media SET storage_path=? WHERE id=?', ('private/xhs-screenshots/../../outside.jpg', media))
    with owner_client() as client:
        assert client.get(f'/api/local-reference-images/{media}').status_code == 404
