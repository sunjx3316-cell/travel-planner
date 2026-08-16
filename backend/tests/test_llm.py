# -*- coding: utf-8 -*-
"""LLM 集成单元测试:假 key + 模拟 DeepSeek HTTP 响应,验证解析与管线降级。"""
from backend.ai import pipeline
from backend.ai.llm import LLMClient


class FakeResponse:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


PAYLOAD = (
    '{"highlights": ["亮点A"], "play_style": ["玩法B"], "cost_range": "100元", '
    '"ad_ratio": 0.25, "ad_signals": ["信号"], '
    '"avoid_points": [{"point": "排队1小时", "evidence": "某帖", "specificity": 4, "verifiable": 4}], '
    '"consensus_issues": ["排队1小时"], "trust_score": 70}'
)


def test_llm_client_chat_json_parses(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json", {})
        return FakeResponse(PAYLOAD)

    monkeypatch.setattr("backend.ai.llm.requests.post", fake_post)

    client = LLMClient()
    client.api_key = "sk-fake"
    out = client.chat_json("system", "user")
    assert out["highlights"] == ["亮点A"]
    assert out["trust_score"] == 70
    assert captured["json"]["model"] == "deepseek-chat"
    assert captured["json"]["response_format"]["type"] == "json_object"
    assert captured["json"]["messages"][0]["role"] == "system"


def test_llm_summarize_pipeline(monkeypatch):
    """LLM 路径整链路:prompt 组装 -> 响应解析 -> summarize_spot 输出"""
    notes = [
        {"title": "攻略", "content": "门票60,排队30分钟,下午5点闭馆。",
         "author_hash": "a1", "note_type": "guide"},
        {"title": "避雷", "content": "排队1小时,人很多。",
         "author_hash": "a2", "note_type": "avoid"},
    ]
    captured = {}

    def fake_post(url, **kwargs):
        captured["user"] = kwargs["json"]["messages"][1]["content"]
        return FakeResponse(PAYLOAD)

    monkeypatch.setattr("backend.ai.llm.requests.post", fake_post)
    old_key = pipeline._llm.api_key
    pipeline._llm.api_key = "sk-fake"
    try:
        out = pipeline.summarize_spot("测试景区", notes)
    finally:
        pipeline._llm.api_key = old_key

    assert out["source"].startswith("DeepSeek")
    assert out["note_count"] == 2
    assert out["consensus_issues"] == ["排队1小时"]
    assert "测试景区" in captured["user"]      # prompt 含景区名
    assert "排队30分钟" in captured["user"]     # prompt 含笔记正文


def test_llm_fallback_on_error(monkeypatch):
    """LLM 抛错自动降级 mock,不中断演示"""

    def boom(url, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("backend.ai.llm.requests.post", boom)
    old_key = pipeline._llm.api_key
    pipeline._llm.api_key = "sk-fake"
    try:
        out = pipeline.summarize_spot("测试景区", [
            {"title": "t", "content": "排队1小时。", "author_hash": "a", "note_type": "avoid"},
        ])
    finally:
        pipeline._llm.api_key = old_key

    assert out["source"].startswith("示例数据")
    assert "LLM 失败" in out["source"]
