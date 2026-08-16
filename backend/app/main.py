# -*- coding: utf-8 -*-
"""应用入口:FastAPI + 前端静态资源。启动方式(项目根目录):
    .venv\\Scripts\\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import load_dotenv

load_dotenv()  # 先于一切读环境变量的模块,支持任意方式启动

from .db import init_db  # noqa: E402
from .models import StatusOut  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATA_DIR = PROJECT_ROOT / "data"

app = FastAPI(title="旅行智规 Travel Planner", version="0.1.0")

init_db()

from .routers import cart, cities, plans, spots  # noqa: E402

app.include_router(cities.router)
app.include_router(spots.router)
app.include_router(cart.router)
app.include_router(plans.router)


@app.get("/api/status", response_model=StatusOut)
def status():
    from ..ai.pipeline import get_llm

    return StatusOut(
        llm_available=get_llm().available,
        data_source="示例数据(待小红书采集)",
        version=app.version,
    )


# 采集的景区图片(本地路径以 images/ 开头,前端通过 /media 访问)
# 注意:必须挂在 "/" 兜底之前,否则被前端静态服务吞掉
if DATA_DIR.exists():
    app.mount("/media", StaticFiles(directory=str(DATA_DIR)), name="media")

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
