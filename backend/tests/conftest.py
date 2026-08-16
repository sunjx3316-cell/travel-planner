# -*- coding: utf-8 -*-
"""pytest 公共配置:注入项目根路径到 sys.path,并使用独立测试库。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # travel-planner
sys.path.insert(0, str(ROOT))

# 在导入 backend.app.main 之前指定独立测试库,避免污染正式数据
os.environ["TRAVEL_DB_PATH"] = str(ROOT / "data" / "test_travel.db")
# 屏蔽真实 DeepSeek key(config.load_dotenv 用 setdefault,不会覆盖已存在的空值),
# 保证测试走确定性 mock;LLM 路径由 test_llm.py 用假 key 单独覆盖
os.environ["DEEPSEEK_API_KEY"] = ""
