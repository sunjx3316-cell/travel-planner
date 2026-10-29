import copy

from backend.collector.review_digest import build_review_digest, excerpt, fingerprint
from backend.collector.review_digest import get_review_digest
import json

def review():
    return {'sources': [{'id': 'a', 'url': 'https://example.com'}],
            'highlights': [{'text': '作者觉得文物展品很震撼', 'source_refs': ['a']}],
            'bottom_line_cautions': [], 'preferences': [], 'practical_conditions': [],
            'comment_insights': [], 'disagreements': []}

def test_preserves_evidence_and_uncertainty():
    value = review()
    value['practical_conditions'] = [{'text': '评论者回忆以前夜间蚊虫较多；不能说明目前仍如此。',
                                      'qualification': '历史个案，未核实当前状态', 'source_refs': ['a']}]
    before = copy.deepcopy(value)
    result = build_review_digest(value)
    assert value == before
    point = result['groups'][1]['points'][0]
    assert '含历史信息' in point['context'] and '有适用边界' in point['context']
    assert point['original_text'] == value['practical_conditions'][0]['text']
    assert not any(g['key'] == 'cautions' for g in result['groups'])

def test_no_unlinked_points_no_manufactured_consensus():
    value = review()
    value['highlights'].append({'text': '最受所有人欢迎', 'source_refs': ['missing']})
    result = build_review_digest(value)
    assert result['displayed_point_count'] == 1
    assert result['groups'][0]['points'][0]['label'] == '文物展陈'
    assert '共识' not in str(result)

def test_exact_duplicates_and_theme_diversity():
    value = review()
    value['highlights'] *= 3
    value['highlights'] += [{'text': '作者喜欢古树园林', 'source_refs': ['a']},
                            {'text': '有人喜欢散步', 'source_refs': ['a']}]
    points = build_review_digest(value)['groups'][0]['points']
    assert len(points) == 2
    assert len({p['label'] for p in points}) == 2

def test_verbatim_excerpt_and_hash():
    text = '作者当次体验了多种角色扮演游戏，' + '孩子偏好这些活动、家长觉得需要赶场；' * 7 + '不能泛化到所有家庭。'
    short, cut = excerpt(text)
    assert cut and text.startswith(short[:-1])
    value = review()
    first = fingerprint(value)
    value['highlights'][0]['text'] += '（个人体验）'
    assert fingerprint(value) != first
    assert build_review_digest({'sources': []})['groups'] == []


def test_edited_digest_requires_current_evidence_and_valid_refs(tmp_path):
    value = review()
    path = tmp_path / 'edited.json'
    record = {'catalog_key': 'k', 'input_hash': fingerprint(value), 'groups': [
        {'key': 'features', 'title': '有什么特点', 'points': [
            {'label': '文物展陈', 'text': '多次参观者仍觉得文物展品震撼。',
             'source_refs': ['a'], 'qualification': '作者个人体验'}]}]}
    path.write_text(json.dumps([record]), encoding='utf-8')
    assert get_review_digest(value, 'k', path)['method'] == 'semantic_reviewed'
    changed = copy.deepcopy(value)
    changed['highlights'][0]['text'] += '新证据'
    assert get_review_digest(changed, 'k', path)['method'] == 'source_linked_extractive'
    record['groups'][0]['points'][0]['source_refs'] = ['bad']
    path.write_text(json.dumps([record]), encoding='utf-8')
    assert get_review_digest(value, 'k', path)['method'] == 'source_linked_extractive'


def test_public_catalog_digests_are_complete_and_private_media_absent():
    import sqlite3
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    with sqlite3.connect((root / 'bundled_data/travel.db').as_uri() + '?mode=ro', uri=True) as conn:
        rows = conn.execute('SELECT catalog_key,payload_json FROM curated_reviews').fetchall()
        manifest = json.loads((root / 'bundled_data/manifest.json').read_text(encoding='utf-8'))
        assert len(rows) == manifest['counts']['curated_reviews'] > 0
        for key, payload in rows:
            value = json.loads(payload)
            assert get_review_digest(value, key, root / 'data/nonexistent-digest.json')['method'] == 'semantic_reviewed'
        for table in ('plans', 'cart_items', 'notes', 'spot_summaries'):
            assert conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
        assert not conn.execute("SELECT id FROM spot_media WHERE rights_status != 'verified'").fetchall()
