"""Local-owner settings only. LAN clients cannot read or alter credentials."""
import ipaddress
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError
from starlette.concurrency import run_in_threadpool

from ...ai.llm import LLMClient
from ...ai.settings import get_settings

router = APIRouter(prefix="/api/ai", tags=["AI settings"])


def _loopback(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def require_local_owner(request):
    host = request.url.hostname
    if not request.client or not _loopback(request.client.host) or not (host == "localhost" or _loopback(host or "")):
        raise HTTPException(403, "仅限在运行程序的电脑上，通过 localhost 或 127.0.0.1 管理 AI 设置")
    if any(h in request.headers for h in ("forwarded", "x-forwarded-for", "x-forwarded-host", "x-client-ip")):
        raise HTTPException(403, "代理访问不能修改本机 AI 设置")
    if request.method != "GET":
        origin = request.headers.get("origin")
        expected = urlsplit(str(request.base_url))
        actual = urlsplit(origin) if origin else None
        if request.headers.get("x-travel-settings") != "1" or (actual and
                (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc)):
            raise HTTPException(403, "请从本机应用设置窗口操作")


def reply(data):
    return JSONResponse(data, headers={"Cache-Control": "no-store"})


class Update(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str
    api_key: SecretStr | None = None
    clear_key: bool = False


@router.get("/settings")
def read_settings(request: Request):
    require_local_owner(request)
    return reply(get_settings().public())


@router.post("/settings")
async def update_settings(request: Request):
    require_local_owner(request)
    try:
        body = await request.body()
        if len(body) > 4096:
            raise ValueError()
        update = Update.model_validate_json(body)
    except (ValidationError, ValueError):
        raise HTTPException(400, "设置格式不正确") from None
    try:
        data = await run_in_threadpool(get_settings().update, mode=update.mode,
                                      api_key=update.api_key.get_secret_value() if update.api_key is not None else None,
                                      clear_key=update.clear_key)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    except OSError:
        raise HTTPException(500, "本机设置保存失败，原配置未改变；请检查目录权限") from None
    return reply(data)


@router.post("/test")
def test_connection(request: Request):
    require_local_owner(request)
    if not get_settings().public()["configured"]:
        raise HTTPException(400, "请先保存 Key，再测试连接")
    try:
        LLMClient().test_connection()
    except RuntimeError:
        pass
    return reply(get_settings().public())
