import json

import pytest
import requests
from fastapi.testclient import TestClient

from backend.ai.llm import LLMClient
from backend.ai.settings import AISettings
from backend.app.main import app

client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
HEADERS = {"X-Travel-Settings": "1", "Origin": "http://127.0.0.1"}


@pytest.mark.parametrize("value", [{"bad": "type"}, "fake key", "x" * 513])
def test_corrupt_saved_key_fails_closed(tmp_path, value):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"mode": "ai", "api_key": value}), encoding="utf-8")
    config = AISettings(path)
    assert config.public()["load_error"]
    assert config.credentials()[0:2] == ("local", "")


def test_default_local_even_when_env_key_exists(monkeypatch, ai_config):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-private-key")
    monkeypatch.setattr("backend.ai.llm.requests.post", lambda *a, **k: pytest.fail("Local mode must not call AI"))
    assert not LLMClient().available
    assert ai_config.public()["configured"]
    with pytest.raises(RuntimeError):
        LLMClient().chat_json("system", "user")
    assert ai_config.public()["last_call"] is None


def test_persistence_no_secrets_in_response_and_no_auto_test(ai_config, monkeypatch):
    monkeypatch.setattr("backend.ai.llm.requests.post", lambda *a, **k: pytest.fail("Saving is free"))
    r = client.post("/api/ai/settings", headers=HEADERS, json={"mode": "ai", "api_key": "fake-private-key"})
    assert r.status_code == 200 and r.json()["connection"]["state"] == "untested"
    assert r.json()["onboarded"]
    assert "fake-private-key" not in r.text
    assert "no-store" in r.headers["cache-control"]
    assert AISettings(ai_config.path).credentials()[0:2] == ("ai", "fake-private-key")
    assert "fake-private-key" not in client.get("/api/status").text
    client.post("/api/ai/settings", headers=HEADERS, json={"mode": "local"})
    assert not LLMClient().available
    assert AISettings(ai_config.path).credentials()[1] == "fake-private-key"


def test_clear_suppresses_environment_and_survives_restart(ai_config, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-env-key")
    r = client.post("/api/ai/settings", headers=HEADERS, json={"mode": "local", "clear_key": True})
    assert not r.json()["configured"]
    assert AISettings(ai_config.path).credentials()[1] == ""


@pytest.mark.parametrize("headers", [{}, {"X-Travel-Settings": "1", "Origin": "https://evil.test"},
                                    {**HEADERS, "X-Forwarded-For": "127.0.0.1"}])
def test_csrf_and_proxy_rejected(headers, ai_config):
    assert client.post("/api/ai/settings", headers=headers, json={"mode": "ai", "api_key": "fake"}).status_code == 403
    assert not ai_config.public()["enabled"]


def test_lan_and_rebinding_rejected():
    lan = TestClient(app, base_url="http://127.0.0.1", client=("192.168.1.2", 50000))
    rebinding = TestClient(app, base_url="http://evil.test", client=("127.0.0.1", 50000))
    for c in (lan, rebinding):
        assert c.get("/api/ai/settings").status_code == 403
        assert c.post("/api/ai/test", headers=HEADERS).status_code == 403


@pytest.mark.parametrize("body", [{"mode": "bad", "api_key": "secret"}, {"mode": "ai", "api_key": {"secret": 1}},
                                 {"mode": "ai"}, {"mode": "ai", "api_key": "secret\nvalue"}])
def test_invalid_inputs_never_echo_key(body):
    r = client.post("/api/ai/settings", headers=HEADERS, json=body)
    assert r.status_code == 400
    assert "secret" not in r.text


def test_write_failure_preserves_state(ai_config, monkeypatch):
    ai_config.update(mode="local", api_key="old-fake")
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr("backend.ai.settings.os.replace", fail)
    r = client.post("/api/ai/settings", headers=HEADERS, json={"mode": "ai", "api_key": "new-fake"})
    assert r.status_code == 500
    assert ai_config.credentials()[0:2] == ("local", "old-fake")
    assert AISettings(ai_config.path).credentials()[0:2] == ("local", "old-fake")


def test_test_is_explicit_real_response_required(ai_config, monkeypatch):
    ai_config.update(mode="local", api_key="fake-private-key")
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": '{"ok":true}'}}]}
    captured = []
    def post(url, **kwargs):
        captured.append(kwargs)
        return Response()
    monkeypatch.setattr("backend.ai.llm.requests.post", post)
    r = client.post("/api/ai/test", headers=HEADERS)
    assert r.json()["connection"]["state"] == "success"
    assert r.json()["last_call"] is None  # connection test isn't plan generation
    assert r.json()["mode"] == "local"
    assert len(captured) == 1 and captured[0]["json"]["max_tokens"] == 32
    assert captured[0]["allow_redirects"] is False


@pytest.mark.parametrize("status", [401, 402, 429, 500])
def test_http_failure_is_redacted(ai_config, monkeypatch, status):
    ai_config.update(mode="ai", api_key="fake-private-key")
    def post(*args, **kwargs):
        resp = requests.Response()
        resp.status_code = status
        raise requests.HTTPError("fake-private-key reflected upstream", response=resp)
    monkeypatch.setattr("backend.ai.llm.requests.post", post)
    r = client.post("/api/ai/test", headers=HEADERS)
    assert r.json()["connection"]["state"] == "failed"
    assert "fake-private-key" not in r.text


def test_old_request_cannot_overwrite_new_key_status(ai_config):
    ai_config.update(mode="ai", api_key="key-one")
    revision = ai_config.revision
    ai_config.update(mode="local", api_key="key-two")
    ai_config.record(revision, purpose="generation", ok=True, message="old request")
    assert ai_config.public()["connection"]["state"] == "untested"


def test_private_settings_not_served(ai_config):
    ai_config.update(mode="local", api_key="fake-private-key")
    for url in ("/data/private/ai_settings.json", "/media/private/ai_settings.json", "/private/ai_settings.json"):
        assert client.get(url).status_code == 404


def test_partial_ai_preserves_three_routes():
    from backend.app.routers.plans import _polish_plans, _local_generation
    base = [{"name": str(i), "daily": [{"day": 1, "items": [{"spot": "test"}]}],
             "generation": _local_generation()} for i in range(3)]
    out = _polish_plans(base, [{"name": "AI"}])
    assert len(out) == 3
    assert out[0]["generation"]["state"] == "ai"
    assert out[1]["generation"]["state"] == "local"
    assert out[0]["daily"] == base[0]["daily"]
    assert base[0]["name"] == "0"
