"""Structured review imports preserve uncertainty, references, and application IDs."""
import json
import sqlite3
import zipfile
import pytest

from backend.collector.curated_reviews import import_bundle, read_bundle


@pytest.mark.parametrize('filename', ['145地点评价补充.json', '144地点评价补充.json', '有增量地点补丁.json'])
def test_supplement_filename_and_ambiguous_archive(tmp_path, filename):
    bundle = {'format_version': 'poi-reviews-v1', 'pois': []}
    path = tmp_path / 'supplement.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(filename, json.dumps(bundle))
    assert read_bundle(path) == bundle
    with zipfile.ZipFile(path, 'a') as archive:
        archive.writestr('景点评价.json', json.dumps(bundle))
    with pytest.raises(ValueError):
        read_bundle(path)


def test_import_exact_precedence_idempotence_and_unmatched_preservation():
    conn = sqlite3.connect(':memory:')
    conn.executescript('CREATE TABLE cities(id INTEGER PRIMARY KEY,name TEXT);'
                       'CREATE TABLE spots(id INTEGER PRIMARY KEY,city_id INTEGER,name TEXT);'
                       "INSERT INTO cities VALUES(1,'南京');"
                       "INSERT INTO spots VALUES(78,1,'夫子庙-秦淮风光带');"
                       "INSERT INTO spots VALUES(99,1,'夫子庙秦淮风光带');")
    poi = {'city': '南京', 'name': '夫子庙-秦淮风光带', 'review_status': 'weak_evidence',
           'sources': [{'id': 's1', 'url': 'https://example.com', 'visible_date': '5天前'},
                       {'id': 's2', 'url': 'https://example.com', 'visible_date': '未知'}],
           'bottom_line_cautions': [{'text': '当次排队，不能泛化', 'source_refs': ['s1']}],
           'coverage': {'xhs_research_status': 'sources_read'}}
    unknown = {**poi, 'name': '尚未收录'}
    bundle = {'pois': [poi, unknown], 'updated_at': '2026-10-03'}
    report = import_bundle(conn, bundle, 'abc')
    import_bundle(conn, bundle, 'abc')
    assert report['matched'] == 1 and len(report['unmatched']) == 1
    assert report['source_records'] == 4 and report['distinct_source_urls'] == 1
    rows = conn.execute('SELECT spot_id,payload_json FROM curated_reviews').fetchall()
    assert len(rows) == 2
    matching = next(row for row in rows if row[0] == 78)
    assert json.loads(matching[1]) == poi
    assert next(row for row in rows if row[0] is None)
