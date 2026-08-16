# -*- coding: utf-8 -*-
"""轻量 .env 加载:不覆盖已存在的环境变量(便于测试屏蔽真实凭证)。"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"


def load_dotenv() -> None:
    if not ENV_PATH.exists():
        return
    # utf-8-sig:兼容旧版记事本保存时带 BOM 的 .env
    for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
