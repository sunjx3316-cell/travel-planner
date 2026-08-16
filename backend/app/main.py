# -*- coding: utf-8 -*-
"""应用入口:FastAPI + 前端静态资源。启动方式(项目根目录):
    .venv\\Scripts\\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
"""
from collections import deque
import os
from pathlib import Path
from threading import Lock
from time import monotonic

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import load_dotenv

load_dotenv()  # 先于一切读环境变量的模块,支持任意方式启动

from .db import init_db  # noqa: E402
from .models import StatusOut  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATA_DIR = PROJECT_ROOT / "data"

app = FastAPI(title="旅行智规 Travel Planner", version="0.1.0")


class InMemoryRateLimiter:
    """单实例部署的轻量限流器。

    生产容器只接受 Caddy 的内网转发，Caddy 覆盖 X-Client-IP，因此不能从公网
    直连数据库或伪造来源。若将来扩成多副本，应替换为 Redis / 腾讯云 WAF 限流。
    """

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()

    def allow(self, client: str, bucket: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = monotonic()
        key = (client, bucket)
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] >= window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = max(1, int(window_seconds - (now - hits[0])) + 1)
                return False, retry_after
            hits.append(now)
            # 防止低频随机 IP 让内存字典无限增长。
            if len(self._hits) > 10000:
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < window_seconds}
            return True, 0


rate_limiter = InMemoryRateLimiter()


def _rate_policy(path: str) -> tuple[str, int, int]:
    """按成本而非仅按 HTTP 方法划分：AI/规划接口比读地图昂贵得多。"""
    if path.endswith("/summarize") or path.startswith("/api/plans/"):
        return "expensive", 5, 60
    if path.endswith("/reviews"):
        return "review", 12, 60
    return "default", 180, 60


def _rate_limit_enabled() -> bool:
    """Allow deterministic tests to opt out; production defaults to protected."""
    return os.environ.get("RATE_LIMIT_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


@app.middleware("http")
async def protect_public_api(request: Request, call_next):
    """限制公共 API 的突发流量，并拒绝异常大的请求体。"""
    if not request.url.path.startswith("/api/") or not _rate_limit_enabled():
        return await call_next(request)
    length = request.headers.get("content-length")
    if length:
        try:
            if int(length) > 128 * 1024:
                return JSONResponse({"detail": "请求体过大"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "非法 Content-Length"}, status_code=400)
    client = (request.headers.get("x-client-ip") or request.client.host or "unknown").split(",", 1)[0].strip()
    bucket, limit, window = _rate_policy(request.url.path)
    allowed, retry_after = rate_limiter.allow(client, bucket, limit, window)
    if not allowed:
        return JSONResponse(
            {"detail": "请求过于频繁，请稍后再试"}, status_code=429,
            headers={"Retry-After": str(retry_after)},
        )
    return await call_next(request)

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
