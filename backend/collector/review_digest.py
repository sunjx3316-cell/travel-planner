"""Conservative, source-linked reading layer; never replaces review evidence.

Topic labels are navigation aids, not new facts or sentiment scores. Excerpts
are verbatim and explicitly distinguished from the complete original point.
"""
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

VERSION = 'extractive-v1'
COLUMNS = ('highlights', 'bottom_line_cautions', 'preferences',
           'practical_conditions', 'comment_insights', 'disagreements')
TOPICS = (
    ('预约入场', ('预约', '入场', '接待', '检票', '闭馆', '开放时间')),
    ('排队客流', ('排队', '客流', '拥挤', '人少', '人多', '等候')),
    ('费用选择', ('票价', '门票', '收费', '另付', '套餐', '消费')),
    ('体力与步行', ('体力', '爬坡', '台阶', '登坡', '步行', '爬沙')),
    ('天气与季节', ('天气', '季节', '暴晒', '太热', '花期', '水位', '潮汐', '退潮')),
    ('拍照观景', ('拍照', '摄影', '机位', '日落', '落日', '俯瞰', '全景', '光线')),
    ('文物展陈', ('文物', '展陈', '展品', '展览', '藏品')),
    ('建筑园林', ('建筑', '园林', '古树', '绿荫', '红墙', '古建')),
    ('角色体验', ('角色', '职业', '模拟', '扮演')),
    ('游乐项目', ('过山车', '滑梯', '攀爬', '刺激', '游乐')),
    ('演出活动', ('表演', '演出', '无人机', '灯光秀', '合唱')),
    ('讲解导览', ('讲解', '导览', '导游', '展签')),
    ('散步休闲', ('散步', '漫步', '闲逛', '休闲', '短逛')),
    ('风味小吃', ('小吃', '口味', '甜口', '凉拌粉', '卷粉', '早餐')),
    ('配套服务', ('工作人员', '服务', '厕所', '卫生间', '餐厅', '休息', '停车')),
    ('滨水景观', ('江景', '滨江', '江面', '海景', '沙滩', '礁石', '浪花')),
)

def fingerprint(review):
    evidence = {key: review.get(key) for key in (*COLUMNS, 'sources', 'review_status')}
    return hashlib.sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def topic(text, fallback):
    # Prefer the first topic actually mentioned, rather than generic rule order.
    matches = [(text.find(word), -len(word), label) for label, words in TOPICS
               for word in words if word in text]
    return min(matches)[2] if matches else fallback

def context(text, qualification):
    value = text + ' ' + qualification
    labels = []
    if re.search(r'历史|以前|过往|当年|改善前|旧版|旧游|回忆|20(?:0\d|1\d|2[0-5])年', value):
        labels.append('含历史信息')
    if re.search(r'当次|当天|自述|作者|评论者|个人|偏好|觉得', value):
        labels.append('个人/当次体验')
    if re.search(r'未核|不确定|未知|尚未|不能|不保证|不代表|不推|未明确|无法', value):
        labels.append('有适用边界')
    return labels

def excerpt(text):
    if len(text) <= 84:
        return text, False
    # Only cut at existing punctuation; do not invent or rephrase a conclusion.
    boundaries = [m.end() for m in re.finditer(r'[。；;，,]', text) if 18 <= m.end() <= 84]
    if not boundaries:
        return text, False
    return text[:max(boundaries)].rstrip('，,；;') + '…', True

def build_review_digest(review):
    known = {s.get('id') for s in review.get('sources', []) if isinstance(s, dict)}
    groups = []
    specs = (
        ('features', '有什么特点', ('highlights',), '体验特点'),
        ('cautions', '提前留意', ('bottom_line_cautions', 'disagreements'), '注意事项'),
        ('conditions', '玩法与条件', ('preferences', 'practical_conditions', 'comment_insights'), '玩法条件'),
    )
    total = sum(len(review.get(k, [])) for k in COLUMNS)
    for key, title, columns, fallback in specs:
        candidates, seen = [], set()
        for column in columns:
            for index, point in enumerate(review.get(column, [])):
                if not isinstance(point, dict) or not isinstance(point.get('text'), str):
                    continue
                text = point['text'].strip()
                refs = point.get('source_refs', [])
                if not text or not refs or not set(refs).issubset(known):
                    continue  # Unlinked material remains in original, not elevated.
                normalized = re.sub(r'\s+', '', text)
                if normalized in seen:
                    continue
                seen.add(normalized)
                short, is_excerpt = excerpt(text)
                qualification = point.get('qualification') or ''
                candidates.append(dict(label=topic(text, fallback), text=short,
                    is_excerpt=is_excerpt, context=context(text, qualification),
                    qualification=qualification, original_text=text,
                    source_refs=list(refs), origin_column=column, origin_index=index))
        # Diversity first, not a fabricated reliability/consensus ranking.
        chosen, remaining, labels = [], [], set()
        for point in candidates:
            if point['label'] not in labels and len(chosen) < 2:
                chosen.append(point); labels.add(point['label'])
            else:
                remaining.append(point)
        chosen.extend(remaining[:max(0, 2-len(chosen))])
        if chosen:
            groups.append(dict(key=key, title=title, points=chosen))
    return dict(version=VERSION, method='source_linked_extractive',
                input_hash=fingerprint(review), original_point_count=total,
                displayed_point_count=sum(len(g['points']) for g in groups), groups=groups)


@lru_cache(maxsize=4)
def _read_edited(path, mtime_ns, size):
    records = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return {r['catalog_key']: r for r in records}


def get_review_digest(review, catalog_key, path):
    """Use an audited semantic edit only for exactly the evidence it reviewed."""
    result = _get_edited_digest(review, catalog_key, path)
    if result is None:
        result = _get_edited_digest(review, catalog_key,
            Path(__file__).resolve().parents[2] / 'bundled_data/review-digests.json')
    return result if result is not None else build_review_digest(review)


def _get_edited_digest(review, catalog_key, path):
    try:
        path = Path(path)
        info = path.stat()
        record = _read_edited(str(path), info.st_mtime_ns, info.st_size).get(catalog_key)
        if record and record['input_hash'] == fingerprint(review):
            known = {s.get('id') for s in review.get('sources', [])}
            groups = record['groups']
            if len(groups) > 3 or len({g['key'] for g in groups}) != len(groups):
                raise ValueError('Invalid groups')
            for group in groups:
                if group['key'] not in {'features', 'cautions', 'conditions'} or len(group['points']) > 2:
                    raise ValueError('Invalid digest group')
                for point in group['points']:
                    if not point.get('text') or not point.get('label') or not point.get('source_refs') or not set(point['source_refs']).issubset(known):
                        raise ValueError('Invalid digest point')
            return dict(version='semantic-v1', method='semantic_reviewed', groups=groups,
                        original_point_count=sum(len(review.get(k, [])) for k in COLUMNS),
                        displayed_point_count=sum(len(g['points']) for g in groups),
                        input_hash=record['input_hash'])
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return None
