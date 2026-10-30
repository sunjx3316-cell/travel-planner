"""Create a new, sanitized release snapshot without copying personal databases.

Starts from the previous public snapshot and imports only allowlisted catalog
tables and approved scenic media. Source is opened read-only; destination must
be a fresh staging directory. No raw research folders or user settings copied.
"""
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from refresh_public_catalog import clean

ROOT = Path(__file__).resolve().parents[1]
from backend.collector.review_digest import fingerprint

TABLES = ('cities', 'spots', 'spot_alternatives', 'stays', 'city_foods',
          'spot_sources', 'curated_reviews')
PRIVATE_TABLES = ('cart_items', 'plans', 'notes', 'spot_summaries')
FOLDERS = {'xhs_screenshot': 'xhs-screenshots', 'web_photo': 'web-photos'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source_db, digests, destination, version):
    source_db = source_db.resolve()
    destination = destination.resolve()
    assert destination.is_relative_to(ROOT / 'output')
    assert not destination.exists(), 'Never overwrite a staging snapshot'
    assert re.fullmatch(r'\d+\.\d+\.\d+', version)
    destination.mkdir(parents=True)
    public = ROOT / 'bundled_data'
    # This base already has empty personal tables; never copy the source DB.
    shutil.copy2(public / 'travel.db', destination / 'travel.db')
    old_photos = {p['media_id']: p for p in json.loads(
        (public / 'reference-photos.json').read_text(encoding='utf-8'))}
    source = sqlite3.connect(source_db.as_uri() + '?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    source.execute('BEGIN')
    dest = sqlite3.connect(destination / 'travel.db')
    dest.execute('PRAGMA foreign_keys=ON')
    dest.execute('PRAGMA secure_delete=ON')
    for table in PRIVATE_TABLES:
        assert dest.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
    with dest:
        for table in TABLES:
            columns = [r[1] for r in dest.execute(f'PRAGMA table_info({table})')]
            pk = next(r[1] for r in dest.execute(f'PRAGMA table_info({table})') if r[5])
            names = ','.join('"' + c + '"' for c in columns)
            rows = source.execute(f'SELECT {names} FROM {table}').fetchall()
            assert {r[0] for r in dest.execute(f'SELECT "{pk}" FROM {table}')}.issubset(
                {r[pk] for r in rows}), 'Catalog deletion requires separate review'
            assignments = ','.join(f'"{c}"=excluded."{c}"' for c in columns if c != pk)
            sql = f'INSERT INTO {table}({names}) VALUES({",".join("?" for _ in columns)}) ON CONFLICT("{pk}") DO UPDATE SET {assignments}'
            for row in rows:
                values = [json.dumps(clean(json.loads(row[c])), ensure_ascii=False)
                          if c.endswith('_json') and row[c] else clean(row[c]) for c in columns]
                dest.execute(sql, values)
        dest.execute('DELETE FROM spot_media')
        records = []
        media = source.execute("SELECT m.*,s.name,c.name city FROM spot_media m JOIN spots s ON s.id=m.spot_id JOIN cities c ON c.id=s.city_id WHERE m.rights_status='verified' OR (m.rights_status='pending' AND m.provider IN ('xhs_screenshot','web_photo')) ORDER BY m.id").fetchall()
        assert len({r['spot_id'] for r in media}) == len(media), 'Select one reviewed photo per place'
        for row in media:
            storage = row['storage_path']
            if storage.startswith('/bundled-images/'):
                original = public / 'images' / Path(storage).name
            else:
                original = (source_db.parent / storage).resolve()
                assert original.is_relative_to(source_db.parent)
            assert original.is_file(), 'Registered media file is missing'
            data = original.read_bytes()
            suffix = original.suffix.lower()
            assert suffix in ('.jpg', '.jpeg', '.png', '.webp')
            source_hash = sha(original)
            if row['rights_status'] == 'verified':
                folder = 'images'
            else:
                provider_folder = FOLDERS[row['provider']]
                assert original.is_relative_to((source_db.parent / 'private' / provider_folder).resolve())
                # Keep the prior release's reviewed crops, not its raw page captures.
                old = old_photos.get(row['id'])
                if old:
                    assert old['spot_id'] == row['spot_id'] and old['source_sha256'] == source_hash
                    final = public / old['file']
                    assert sha(final) == old['sha256']
                    data, suffix = final.read_bytes(), final.suffix.lower()
                folder = 'reference-photos'
            digest = hashlib.sha256(data).hexdigest()
            file = destination / folder / (digest + suffix)
            file.parent.mkdir(exist_ok=True)
            if file.exists():
                assert file.read_bytes() == data
            else:
                file.write_bytes(data)
            with Image.open(file) as im:
                width, height = im.size
                im.verify()
            if row['rights_status'] == 'verified':
                storage = '/bundled-images/' + file.name
                note = row['license_note']
            else:
                storage = 'private/' + FOLDERS[row['provider']] + '/release-references/' + file.name
                note = (row['license_note'] or '') + '；用户明确要求纳入发布包；公开转载授权未核实，仅本机参考，不代表已授权。'
                records.append({'media_id': row['id'], 'spot_id': row['spot_id'], 'city': row['city'],
                    'name': row['name'], 'provider': row['provider'], 'file': str(file.relative_to(destination)).replace('\\','/'),
                    'sha256': digest, 'source_sha256': source_hash, 'width': width, 'height': height,
                    'source_url': clean(row['origin_url']), 'attribution': clean(note), 'rights_status': 'pending',
                    'public_redistribution_authorization': 'not_verified', 'included_by': 'explicit_user_request',
                    'modifications': 'reviewed_photo_no_inpainting', 'display_scope': 'loopback_only'})
            dest.execute('INSERT INTO spot_media(id,spot_id,storage_path,origin_url,provider,license_note,rights_status,captured_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                (row['id'], row['spot_id'], storage, clean(row['origin_url']), row['provider'], clean(note),
                 row['rights_status'], row['captured_at'], row['created_at']))
        dest.execute('UPDATE release_metadata SET version=?', (version,))
    edited = json.loads(digests.read_text(encoding='utf-8-sig'))
    payloads = {r[0]: json.loads(r[1]) for r in dest.execute('SELECT catalog_key,payload_json FROM curated_reviews')}
    assert len(edited) == len(payloads) == len({r['catalog_key'] for r in edited})
    for record in edited:
        payload = payloads[record['catalog_key']]
        record['input_hash'] = fingerprint(payload)
        ids = {s['id'] for s in payload.get('sources', [])}
        assert all(set(p['source_refs']).issubset(ids) for g in record['groups'] for p in g['points'])
    for name, value in [('review-digests.json', clean(edited)), ('reference-photos.json', records)]:
        (destination / name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    counts = {t: dest.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
              for t in (*TABLES, 'spot_media', *PRIVATE_TABLES)}
    counts.update(review_status=dict(dest.execute('SELECT review_status,count(*) FROM curated_reviews GROUP BY review_status')),
        images=len(list((destination/'images').iterdir())), reference_photos=len(records),
        pictured_places=dest.execute('SELECT count(distinct spot_id) FROM spot_media').fetchone()[0],
        review_digest_places=len(edited), review_digest_points=sum(len(g['points']) for r in edited for g in r['groups']))
    # Read semantic cells before VACUUM and reject machine paths/session signatures.
    for table in (*TABLES, 'spot_media'):
        for row in dest.execute(f'SELECT * FROM {table}'):
            for cell in row:
                if isinstance(cell, str):
                    assert not re.search(r'xsec_token|[CD]:[\\/](?:Users|Harness)|data[\\/]private[\\/]',cell,re.I), table
    assert not dest.execute('PRAGMA foreign_key_check').fetchall()
    dest.execute('VACUUM')
    assert dest.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    dest.close()
    source.close()
    manifest = {'version': version, 'catalog_updated_at': datetime.now(timezone.utc).isoformat(),
        'counts': counts, 'privacy': 'No credentials, cookies, carts, saved itineraries, raw notes, research pages, comment screenshots or login captures. Scenic reference photographs retain pending rights and source credits; loopback-only display.',
        'files': {str(p.relative_to(destination)).replace('\\','/'): sha(p) for p in sorted(destination.rglob('*')) if p.is_file()}}
    (destination/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'version': version, 'counts': counts, 'source_read_only': True}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-db', type=Path, required=True)
    parser.add_argument('--digests', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    prepare(args.source_db, args.digests, args.destination, args.version)
