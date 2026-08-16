# -*- coding: utf-8 -*-
"""AI 加工管线单元测试:暗广打分 / 避雷挖掘 / 尬黑过滤 / 共识统计。"""
from backend.ai import pipeline


def _note(content, author="a1", note_type="guide"):
    return {"title": "t", "content": content, "author_hash": author, "note_type": note_type}


# ---------- 暗广打分 ----------

def test_ad_score_high_for_praise_only():
    """通篇溢美、无具体细节 -> 营销嫌疑高"""
    s = pipeline._mock_ad_score("真的太震撼了!!!此生必去!!!绝美!!!不来后悔!!!姐妹们冲!!!")
    assert s["score"] >= 60


def test_ad_score_low_for_concrete_guide():
    """含门票/时间/排队等具体信息 -> 嫌疑低"""
    s = pipeline._mock_ad_score("门票60元,排队2小时,地铁1号线直达,闭馆时间17点,人少的时候体验很好。")
    assert s["score"] < 40


def test_ad_ratio_reflects_mix():
    """混合输入:1 篇疑似暗广 + 3 篇正常 -> 占比约 0.25 上下"""
    notes = [
        _note("绝了!!!必去!!!冲!!!", "a1"),
        _note("门票60,排队30分钟,下午4点闭馆。", "a2"),
        _note("地铁直达,人少,值得逛2小时。", "a3"),
        _note("旺季排队1小时,建议早去,门票可预约。", "a4"),
    ]
    out = pipeline.mock_summarize("测试景区", notes)
    assert 0 < out["ad_ratio"] <= 0.4


# ---------- 避雷挖掘与尬黑过滤 ----------

def test_avoid_extraction_finds_specific():
    pts = pipeline._mock_avoid_points("门票另收费不含大门票,排队40分钟,下午5点闭馆。")
    assert len(pts) >= 1
    assert all(p["specificity"] >= 3 for p in pts)


def test_gabhei_emotional_rant_filtered():
    """情绪发泄型尬黑(无细节)不进入口碑卡"""
    notes = [_note("太差了,又挤又乱,没什么好看的,浪费我半天时间,垃圾,再也不去了。", "a1", "avoid")]
    out = pipeline.mock_summarize("测试景区", notes)
    for p in out["avoid_points"]:
        assert not (p["specificity"] < 2 and p["verifiable"] < 2)


# ---------- 共识统计 ----------

def test_consensus_two_independent_authors():
    """同一负面关键词被 2 个独立账号提到 -> 共识差评"""
    notes = [
        _note("节假日排队1小时以上,安检很慢,建议早去。", "a1", "avoid"),
        _note("旺季排队太久,体验差,门票还要预约。", "a2", "avoid"),
    ]
    out = pipeline.mock_summarize("测试景区", notes)
    assert len(out["consensus_issues"]) >= 1
    assert any("排队" in c for c in out["consensus_issues"])


def test_no_consensus_single_author():
    """同一账号重复吐槽不算共识"""
    notes = [
        _note("排队1小时,排队2小时,一直排队。", "a1", "avoid"),
    ]
    out = pipeline.mock_summarize("测试景区", notes)
    assert len(out["consensus_issues"]) == 0


def test_consensus_mentions_count():
    notes = [
        _note("排队1小时,很挤。", "a1", "avoid"),
        _note("排队40分钟,人挤人。", "a2", "avoid"),
        _note("排队半小时,还行。", "a3", "avoid"),
    ]
    out = pipeline.mock_summarize("测试景区", notes)
    hits = [c for c in out["consensus_issues"] if "排队" in c]
    assert hits and hits[0] and out["avoid_points"][0]["mentions"] >= 3


# ---------- 输出结构 ----------

def test_summarize_structure():
    notes = [_note("门票60,排队30分钟,值得逛。", "a1")]
    out = pipeline.mock_summarize("测试景区", notes)
    assert set(out) >= {"highlights", "play_style", "cost_range", "ad_ratio",
                        "ad_signals", "avoid_points", "consensus_issues", "trust_score"}
    assert 0 <= out["trust_score"] <= 100
    assert 0 <= out["ad_ratio"] <= 1
    assert out["note_count"] == 1


def test_summarize_empty_notes():
    out = pipeline.mock_summarize("测试景区", [])
    assert out["trust_score"] >= 0
