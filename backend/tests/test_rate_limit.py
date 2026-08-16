# -*- coding: utf-8 -*-
"""公共 API 防护：贵接口限流、普通读取保持可用。"""
from fastapi.testclient import TestClient

from backend.app.main import app, rate_limiter


def setup_function():
    rate_limiter._hits.clear()


def test_expensive_endpoint_is_rate_limited(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr("backend.app.main._rate_limit_enabled", lambda: True)
    monkeypatch.setattr("backend.app.main._rate_policy", lambda _: ("test", 2, 60))
    for _ in range(2):
        response = client.get("/api/status", headers={"X-Client-IP": "203.0.113.10"})
        assert response.status_code == 200
    response = client.get("/api/status", headers={"X-Client-IP": "203.0.113.10"})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1


def test_different_clients_have_independent_buckets(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr("backend.app.main._rate_limit_enabled", lambda: True)
    monkeypatch.setattr("backend.app.main._rate_policy", lambda _: ("test", 1, 60))
    assert client.get("/api/status", headers={"X-Client-IP": "203.0.113.10"}).status_code == 200
    assert client.get("/api/status", headers={"X-Client-IP": "203.0.113.11"}).status_code == 200
