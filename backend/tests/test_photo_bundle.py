import hashlib
import importlib.util
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('photo_import', Path(__file__).parents[2] / 'scripts/import_photo_bundle.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_photo_package_matching_checksums_and_real_format(tmp_path):
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE curated_reviews(city TEXT,name TEXT,spot_id INTEGER)')
    conn.execute("INSERT INTO curated_reviews VALUES('北京','景点',99)")
    data = b'\x89PNG\r\n\x1a\nexample'
    filename = '景点照片-第02包.zip'
    item = dict(city='北京', name='景点', catalog_id=2, status='available', file='照片/0002.jpg',
                archive_part=filename, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                license_code='CC-BY-SA-4.0', license_url='https://creativecommons.org/licenses/by-sa/4.0/',
                source_url='https://commons.wikimedia.org/wiki/File:Example.png', author='Author')
    bundle = dict(format_version='poi-photo-package-v1', records=[item], archive_parts=[{'file_name': filename}])

    def write():
        with zipfile.ZipFile(tmp_path / filename, 'w') as archive:
            archive.writestr('全部照片清单.json', json.dumps(bundle))
            archive.writestr(item['file'], data)

    write()
    photos, _, report = module.prepare(tmp_path, conn)
    assert photos[0][0] == 99  # Never use the catalog id as the app id.
    assert report['photos'] == 1
    assert module.photo_extension(data) == '.png'
    assert photos[0][2] == data
    item['sha256'] = 'bad'
    write()
    with pytest.raises(ValueError, match='校验失败'):
        module.prepare(tmp_path, conn)
