"""Import independently zipped, attributed catalog photos without changing reviews."""
import argparse
import hashlib
import json
import re
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def photo_extension(data):
    if data.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    raise ValueError('不支持的照片格式')


def prepare(folder, conn):
    archives = sorted(folder.glob('景点照片-*.zip'))
    if not archives:
        raise ValueError('没有照片分包')
    manifest = None
    photos = []
    seen = set()
    for path in archives:
        with zipfile.ZipFile(path) as archive:
            raw = archive.read('全部照片清单.json')
            bundle = json.loads(raw)
            if bundle.get('format_version') != 'poi-photo-package-v1':
                raise ValueError('不支持的照片清单格式')
            if manifest is not None and bundle != manifest:
                raise ValueError('分包清单不一致')
            manifest = bundle
            records = {r['file']: r for r in bundle['records'] if r['status'] == 'available'}
            for entry in archive.infolist():
                if not entry.filename.startswith('照片/') or entry.is_dir():
                    continue
                item = records.get(entry.filename)
                if not item or item['archive_part'] != path.name or entry.filename in seen:
                    raise ValueError('照片不在对应分包清单或重复')
                if entry.file_size > 20 * 1024 * 1024:
                    raise ValueError('照片超过20MB')
                data = archive.read(entry)
                digest = hashlib.sha256(data).hexdigest()
                if digest != item['sha256'] or len(data) != item['bytes']:
                    raise ValueError('照片校验失败: ' + entry.filename)
                photo_extension(data)
                code = re.sub(r'[\s-]+', ' ', item.get('license_code', '')).upper()
                if not (re.fullmatch(r'CC BY(?: SA)? [234]\.\d(?: [A-Z]{2})?', code)
                        or code.startswith('CC0') or code == 'PUBLIC DOMAIN (COPYRIGHT HOLDER RELEASE)'):
                    raise ValueError('未识别的许可: ' + code)
                if not item.get('author') or not item.get('license_url') or not item.get('source_url'):
                    raise ValueError('缺少署名或许可链接')
                # Catalog numbering is not an application spot ID. Reuse the exact
                # city/name mapping already established for the review catalog.
                matches = conn.execute('SELECT spot_id FROM curated_reviews WHERE city=? AND name=? AND spot_id IS NOT NULL',
                                       (item['city'], item['name'])).fetchall()
                if len(matches) != 1:
                    raise ValueError('景点无法唯一匹配: ' + item['city'] + item['name'])
                photos.append((matches[0][0], item, data))
                seen.add(entry.filename)
            expected = {r['file'] for r in bundle['records'] if r.get('archive_part') == path.name and r['status'] == 'available'}
            if expected - seen:
                raise ValueError('分包照片缺失: ' + path.name)
    report = {'parts': len(archives), 'photos': len(photos),
              'missing_parts': [p['file_name'] for p in manifest['archive_parts'] if not (folder / p['file_name']).is_file()],
              'catalog_without_photo': sum(r['status'] != 'available' for r in manifest['records'])}
    return photos, manifest, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not args.db.is_file():
        parser.error('数据库不存在')
    with sqlite3.connect(args.db) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        photos, manifest, report = prepare(args.folder, conn)
        if not args.dry_run:
            backup = args.db.with_name(args.db.name + '.before-photos-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.bak')
            with sqlite3.connect(backup) as destination:
                conn.backup(destination)
            target = args.db.parent / 'images' / 'catalog-photos'
            target.mkdir(parents=True, exist_ok=True)
            # Hash-addressed files cannot overwrite older or unrelated assets.
            for spot_id, item, data in photos:
                dest = target / (item['sha256'] + photo_extension(data))
                if dest.exists():
                    if hashlib.sha256(dest.read_bytes()).hexdigest() != item['sha256']:
                        raise ValueError('已有照片校验失败')
                else:
                    dest.write_bytes(data)
            now = datetime.now(timezone.utc).isoformat()
            with conn:
                for spot_id, item, data in photos:
                    note = '作者：' + item['author'] + '；许可：' + item['license_code'] + '；' + item['license_url']
                    for key in ('attribution', 'modifications', 'scope_note', 'location_warning', 'quality_note', 'resolution_note', 'attribution_warning'):
                        if item.get(key):
                            note += '；' + str(item[key])
                    note += '；历史照片，不代表当前现场状况；许可与对应依据来自所提供清单'
                    conn.execute('''INSERT INTO spot_media(spot_id,storage_path,origin_url,provider,license_note,rights_status,captured_at,created_at)
                        VALUES(?,?,?,?,?,'verified',?,?) ON CONFLICT(spot_id,storage_path) DO UPDATE SET
                        origin_url=excluded.origin_url,license_note=excluded.license_note,captured_at=excluded.captured_at''',
                        (spot_id, 'images/catalog-photos/' + item['sha256'] + photo_extension(data), item['source_url'],
                         'Wikimedia Commons', note, item.get('captured_at') or '', now))
            provenance = args.db.parent / 'photo-imports'
            provenance.mkdir(parents=True, exist_ok=True)
            manifest_path = provenance / ('manifest-' + hashlib.sha256(json.dumps(manifest, ensure_ascii=False).encode()).hexdigest()[:16] + '.json')
            if not manifest_path.exists():
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            print('Backup:', backup)
        print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    main()
