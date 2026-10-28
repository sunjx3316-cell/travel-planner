# -*- coding: utf-8 -*-
"""DeepSeek client with an explicit local-mode gate and redacted diagnostics."""
import json

import requests

from .settings import get_settings

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"


def safe_error(error):
    if isinstance(error, requests.Timeout):
        return "请求超时，请稍后重试"
    if isinstance(error, requests.ConnectionError):
        return "网络连接失败，请检查网络"
    if isinstance(error, requests.HTTPError):
        code = getattr(error.response, "status_code", None)
        return {401: "Key 无效或已失效", 403: "API 访问被拒绝", 402: "账户余额不足",
                429: "请求过于频繁或额度受限"}.get(code, "AI 服务暂不可用")
    return "AI 返回格式无效，未采用其结果"


class LLMClient:
    @property
    def available(self) -> bool:
        mode, key, _ = get_settings().credentials()
        return mode == "ai" and bool(key)

    def chat_json(self, system: str, user: str, temperature: float = 0.4) -> dict:
        return self._request(system, user, temperature, purpose="generation")

    def test_connection(self):
        return self._request('Return only JSON: {"ok":true}', 'Return JSON {"ok":true}',
                             0, purpose="connection_test", testing=True)

    def _request(self, system, user, temperature, *, purpose, testing=False):
        settings = get_settings()
        mode, key, revision = settings.credentials()
        if not key or (mode != "ai" and not testing):
            raise RuntimeError("当前为本地规划模式或未配置 Key")
        payload = {"model": MODEL,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                   "temperature": temperature, "response_format": {"type": "json_object"}}
        if testing:
            payload["max_tokens"] = 32
        try:
            resp = requests.post(
            DEEPSEEK_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload, timeout=(10, 20 if testing else 90), allow_redirects=False,
            )
            resp.raise_for_status()
            result = json.loads(resp.json()["choices"][0]["message"]["content"])
            if not isinstance(result, dict) or (testing and result.get("ok") is not True):
                raise ValueError("Invalid object")
            settings.record(revision, purpose=purpose, ok=True, message="连接测试成功" if testing else "AI 请求成功")
            return result
        except Exception as error:
            message = safe_error(error)
            settings.record(revision, purpose=purpose, ok=False, message=message)
            raise RuntimeError(message) from None
