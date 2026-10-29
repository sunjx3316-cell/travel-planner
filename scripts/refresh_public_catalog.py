"""Refresh public catalog and reviewed digests, never copying user/private tables.

This does not build, tag, or publish a release. Existing licensed image files and
release version markers are retained. Source database is opened read-only.
"""
import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.collector.review_digest import fingerprint

def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k not in {'evidence', 'feedback_file'}}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, str) and value.startswith(('http://', 'https://')):
        parts = urlsplit(value)
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if k.lower() not in {'xsec_token', 'xsec_source', 'access_token', 'auth_token'}]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return value

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source-db', type=Path, required=True)
    p.add_argument('--digests', type=Path, required=True)
    args = p.parse_args()
    public = ROOT / 'bundled_data'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    work = ROOT / 'output' / ('public-catalog-' + stamp)
    work.mkdir(parents=True)
    for name in ('travel.db', 'manifest.json', 'review-digests.json'):
        if (public / name).exists():
            shutil.copy2(public / name, work / ('before-' + name))
    staged = work / 'travel.db'
    shutil.copy2(public / 'travel.db', staged)
    source = sqlite3.connect(args.source_db.resolve().as_uri() + '?mode=ro', uri=True)
    dest = sqlite3.connect(staged)
    dest.execute('PRAGMA foreign_keys=ON')
    dest.execute('PRAGMA secure_delete=ON')
    # Already-public snapshot must not contain personal/runtime content.
    for table in ('cart_items', 'plans', 'notes', 'spot_summaries'):
        assert dest.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
    with dest:
        for table in ('cities', 'spots', 'spot_sources', 'curated_reviews'):
            columns = [r[1] for r in dest.execute(f'PRAGMA table_info({table})')]
            pk = next(r[1] for r in dest.execute(f'PRAGMA table_info({table})') if r[5])
            names = ','.join('"' + c + '"' for c in columns)
            rows = source.execute(f'SELECT {names} FROM {table}').fetchall()
            current = {r[0] for r in dest.execute(f'SELECT "{pk}" FROM {table}')}
            assert current.issubset({r[columns.index(pk)] for r in rows}), 'Unexpected catalog deletion'
            assignments = ','.join(f'"{c}"=excluded."{c}"' for c in columns if c != pk)
            sql = f'INSERT INTO {table}({names}) VALUES({",".join("?" for _ in columns)}) ON CONFLICT("{pk}") DO UPDATE SET {assignments}'
            for row in rows:
                row = list(row)
                if 'payload_json' in columns:
                    ix = columns.index('payload_json')
                    row[ix] = json.dumps(clean(json.loads(row[ix])), ensure_ascii=False)
                dest.execute(sql, row)
        assert not dest.execute("SELECT id FROM spot_media WHERE rights_status != 'verified'").fetchall()
        assert not dest.execute('PRAGMA foreign_key_check').fetchall()
    edited = json.loads(args.digests.read_text(encoding='utf-8-sig'))
    payloads = {r[0]: json.loads(r[1]) for r in dest.execute('SELECT catalog_key,payload_json FROM curated_reviews')}
    assert len(edited) == len(payloads)
    for record in edited:
        payload = payloads[record['catalog_key']]
        record['input_hash'] = fingerprint(payload)
        ids = {s['id'] for s in payload.get('sources', [])}
        assert all(set(point['source_refs']).issubset(ids) for g in record['groups'] for point in g['points'])
    (work / 'review-digests.json').write_text(json.dumps(edited, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    counts = {t: dest.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
              for t in ('cities', 'spots', 'curated_reviews', 'spot_media', 'cart_items', 'plans', 'notes')}
    counts['review_status'] = dict(dest.execute('SELECT review_status,COUNT(*) FROM curated_reviews GROUP BY review_status'))
    counts['images'] = len(list((public / 'images').glob('*')))
    counts['review_digest_places'] = len(edited)
    counts['review_digest_points'] = sum(len(g['points']) for r in edited for g in r['groups'])
    dest.execute('VACUUM')
    assert dest.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    # Examine semantic JSON, not opaque compressed SQLite storage.
    text = '\n'.join(r[0] for r in dest.execute('SELECT payload_json FROM curated_reviews'))
    assert not re.search(r'xsec_token=|[CD]:[\\/](?:Users|Harness)', text, re.I)
    assert 'data/private/' not in text and 'data\\private\\' not in text
    dest.close(); source.close()
    shutil.copy2(staged, public / 'travel.db')
    shutil.copy2(work / 'review-digests.json', public / 'review-digests.json')
    manifest = json.loads((public / 'manifest.json').read_text(encoding='utf-8'))
    manifest['counts'] = counts
    manifest['catalog_updated_at'] = datetime.now(timezone.utc).isoformat()
    manifest['privacy'] = 'No credentials, cookies, carts, saved plans, raw notes, private screenshots or temporary platform access signatures. Verified public images only.'
    manifest['files'] = {str(f.relative_to(public)).replace('\\', '/'): hashlib.sha256(f.read_bytes()).hexdigest()
                         for f in sorted(public.rglob('*')) if f.is_file() and f.name != 'manifest.json'}
    (public / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'counts': counts, 'backup': str(work), 'release_created': False}, ensure_ascii=False))

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
