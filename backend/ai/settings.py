"""Installation-local AI preferences. Secrets never appear in public status."""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data/private/ai_settings.json"


class AISettings:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("TRAVEL_AI_SETTINGS_PATH") or DEFAULT_PATH)
        self.lock = RLock()
        self.mode = "local"
        self.saved_key = ""
        self.use_env = True
        self.onboarded = False
        self.revision = 0
        self.connection = {"state": "untested"}
        self.last_call = None
        self.load_error = False
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                key = data.get("api_key", "")
                if not isinstance(key, str) or len(key) > 512 or any(ch.isspace() for ch in key):
                    raise ValueError("Invalid saved key")
                self.mode = "ai" if data.get("mode") == "ai" else "local"
                self.saved_key = key
                self.use_env = data.get("use_env", True) is True
                self.onboarded = data.get("onboarded", False) is True
            except (OSError, ValueError, TypeError, AttributeError):
                self.load_error = True

    def credentials(self):
        with self.lock:
            key = self.saved_key or (os.environ.get("DEEPSEEK_API_KEY", "").strip() if self.use_env else "")
            return self.mode, key, self.revision

    def public(self):
        with self.lock:
            mode, key, _ = self.credentials()
            return {"mode": mode, "provider": "DeepSeek", "model": "deepseek-chat",
                    "configured": bool(key), "enabled": mode == "ai" and bool(key),
                    "onboarded": self.onboarded,
                    "key_source": "local" if self.saved_key else "environment" if key else "none",
                    "connection": dict(self.connection) if key else {"state": "unconfigured"},
                    "last_call": dict(self.last_call) if self.last_call else None,
                    "load_error": self.load_error}

    def update(self, *, mode, api_key=None, clear_key=False):
        if mode not in ("local", "ai"):
            raise ValueError("请选择本地规划或 AI 增强")
        if api_key is not None:
            api_key = api_key.strip()
            if not api_key or len(api_key) > 512 or any(ch.isspace() for ch in api_key):
                raise ValueError("Key 不能为空、含空白或超过 512 个字符")
        with self.lock:
            key = "" if clear_key else api_key if api_key is not None else self.saved_key
            use_env = False if clear_key else self.use_env
            effective = key or (os.environ.get("DEEPSEEK_API_KEY", "").strip() if use_env else "")
            if mode == "ai" and not effective:
                raise ValueError("请先填写自己的 DeepSeek API Key")
            data = {"mode": mode, "api_key": key, "use_env": use_env, "onboarded": True}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.is_symlink() or self.path.parent.is_symlink():
                raise OSError("Settings path must not be a symlink")
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                                 prefix="ai-", suffix=".tmp", delete=False) as temp:
                    temp_path = Path(temp.name)
                    os.chmod(temp_path, 0o600)
                    json.dump(data, temp, ensure_ascii=False)
                    temp.flush()
                    os.fsync(temp.fileno())
                os.replace(temp_path, self.path)
            finally:
                if temp_path and temp_path.exists():
                    temp_path.unlink()
            changed_key = key != self.saved_key or use_env != self.use_env
            self.mode, self.saved_key, self.use_env = mode, key, use_env
            self.revision += 1
            self.onboarded = True
            self.load_error = False
            if changed_key:
                self.connection = {"state": "untested"}
                self.last_call = None
            return self.public()

    def record(self, revision, *, purpose, ok, message):
        with self.lock:
            if revision != self.revision:
                return
            result = {"state": "success" if ok else "failed", "purpose": purpose,
                      "message": message, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            self.connection = result
            if purpose != "connection_test":
                self.last_call = result


_settings = None


def get_settings():
    global _settings
    if _settings is None:
        _settings = AISettings()
    return _settings
