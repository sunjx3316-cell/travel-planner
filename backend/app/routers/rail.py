"""Bounded, anonymous public fare lookup for the embedded railway workbench.

No passenger account, ticket inventory or booking endpoint is used. A failed
lookup stays unquoted; it must never become a zero-price or estimated fare.
"""
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
import json
import re
from threading import Lock
from time import monotonic

import requests
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/api/rail", tags=["rail"])
_cache = OrderedDict()
_gate = Lock()
_init_url = "https://kyfw.12306.cn/otn/leftTicket/init?linktypeid=dc"


def _now():
    return datetime.now(timezone.utc).isoformat()


def parse_fares(encoded):
    if not isinstance(encoded, str) or len(encoded) % 10:
        return {}
    fares = {}
    for offset in range(0, len(encoded), 10):
        record = encoded[offset:offset + 10]
        if not re.fullmatch(r"[A-Z0-9][0-9]{5}.{4}", record):
            continue
        amount = int(record[1:6]) / 10
        seat = "W" if record[6] == "3" else record[0]
        if amount > 0:
            fares[seat] = min(fares.get(seat, amount), amount)
    return fares


def extract_rows(payload, pair):
    rows = payload.get("data", {}).get("result") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or payload.get("status") is False:
        raise ValueError("票价来源未返回可用数据，保持待核价。")
    result = []
    for raw in rows:
        fields = raw.split("|") if isinstance(raw, str) else []
        if len(fields) <= 39 or fields[6:8] != [pair["from"], pair["to"]]:
            continue
        fares = parse_fares(fields[39])
        if fares:
            result.append(dict(train=fields[3], date=pair["date"], **{
                "from": fields[6], "to": fields[7], "departure": fields[8],
                "arrival": fields[9], "fares": fares, "queriedAt": _now(),
                "source": "12306公开查询"}))
    return result


def validate_pair(pair):
    if not isinstance(pair, dict):
        raise ValueError("票价查询参数无效。")
    if any(not isinstance(pair.get(k), str) or not re.fullmatch(r"[A-Z]{3}", pair[k]) for k in ("from", "to")):
        raise ValueError("车站代码无效。")
    if pair["from"] == pair["to"]:
        raise ValueError("请选择不同的起终点。")
    text = pair.get("date", "")
    if not isinstance(text, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        raise ValueError("日期格式无效。")
    day = date.fromisoformat(text)
    today = datetime.now(timezone(timedelta(hours=8))).date()
    if not today <= day <= today + timedelta(days=22):
        raise ValueError("所选日期尚无可查询票价，价格保持待核价。")
    required = pair.get("required", [])
    if not isinstance(required, list) or len(required) > 4 or any(not isinstance(t, str) or not re.fullmatch(r"[A-Z]?[0-9]{1,6}", t) for t in required):
        raise ValueError("每个区间最多核对 4 个有效车次。")
    for key in ("fromName", "toName"):
        if key in pair and (not isinstance(pair[key], str) or len(pair[key]) > 25):
            raise ValueError("车站名称过长。")
    return {key: pair[key] for key in ("from", "to", "date", "required", "fromName", "toName") if key in pair}


def _fetch(session, url, deadline, params=None, as_json=True):
    remaining = deadline - monotonic()
    if remaining < 0.3:
        raise TimeoutError()
    # All callers supply a fixed official host. Never follow external redirects.
    with session.get(url, params=params, timeout=min(6, remaining), allow_redirects=False, stream=True) as response:
        if response.status_code != 200:
            raise ValueError("票价来源暂不可用，未尝试绕过。")
        if not as_json:
            return None
        chunks, size = [], 0
        for chunk in response.iter_content(16384):
            size += len(chunk)
            if size > 2 * 1024 * 1024 or monotonic() >= deadline:
                raise TimeoutError()
            chunks.append(chunk)
        try:
            payload = json.loads(b"".join(chunks))
        except (ValueError, UnicodeError):
            raise ValueError("票价来源返回了验证或错误页面，未尝试绕过。") from None
        if not isinstance(payload, dict):
            raise ValueError("票价来源数据格式无效。")
        return payload


def _specific_train(session, pair, train, deadline):
    if not pair.get("fromName") or not pair.get("toName"):
        return None
    search = _fetch(session, "https://search.12306.cn/search/v1/train/search", deadline,
                    {"keyword": train, "date": pair["date"].replace("-", "")})
    matches = search.get("data")
    if not isinstance(matches, list):
        return None
    match = next((r for r in matches if isinstance(r, dict) and r.get("station_train_code") == train), None)
    number = match.get("train_no", "") if match else ""
    if not isinstance(number, str) or not re.fullmatch(r"[A-Za-z0-9_]{8,20}", number):
        return None
    payload = _fetch(session, "https://kyfw.12306.cn/otn/czxx/queryByTrainNo", deadline, {
        "train_no": number, "from_station_telecode": pair["from"],
        "to_station_telecode": pair["to"], "depart_date": pair["date"]})
    stops = payload.get("data", {}).get("data")
    if not isinstance(stops, list):
        return None
    start = next((s for s in stops if isinstance(s, dict) and s.get("station_name") == pair["fromName"]), None)
    end = next((s for s in stops if isinstance(s, dict) and s.get("station_name") == pair["toName"]), None)
    if not start or not end or int(start.get("station_no", 0)) >= int(end.get("station_no", 0)):
        return None
    prices = _fetch(session, "https://kyfw.12306.cn/otn/leftTicket/queryTicketPrice", deadline, {
        "train_no": number, "from_station_no": start["station_no"], "to_station_no": end["station_no"],
        "seat_types": "O9M1342W6", "train_date": pair["date"]})
    data = prices.get("data")
    if prices.get("status") is not True or not isinstance(data, dict):
        return None
    aliases = {"1": "A1", "2": "A2", "3": "A3", "4": "A4", "6": "A6", "9": "A9", "O": "O", "M": "M", "P": "P", "W": "WZ"}
    fares = {}
    for seat, key in aliases.items():
        value = data.get(key)
        if isinstance(value, str) and re.fullmatch(r"[¥￥]\s*[0-9]+(?:\.[0-9]+)?", value):
            amount = float(re.sub(r"[¥￥\s]", "", value))
            if amount > 0:
                fares[seat] = amount
    if not fares:
        return None
    return dict(train=train, **{"from": pair["from"], "to": pair["to"], "date": pair["date"],
        "departure": start.get("start_time"), "arrival": end.get("arrive_time"), "fares": fares,
        "queriedAt": _now(), "source": "12306区间票价查询"})


def _quote_pair(session, pair, deadline):
    key = (pair["from"], pair["to"], pair["date"])
    cached = _cache.get(key)
    fresh = cached and monotonic() - cached[0] < 600
    rows = list(cached[1]["rows"]) if fresh else []
    required = pair.get("required", [])
    if fresh and all(any(row["train"] == train for row in rows) for train in required):
        return {**cached[1], "pair": pair, "cached": True}
    if not session.cookies:
        _fetch(session, _init_url, deadline, as_json=False)
    if not fresh:
        params = {"leftTicketDTO.train_date": pair["date"], "leftTicketDTO.from_station": pair["from"],
                  "leftTicketDTO.to_station": pair["to"], "purpose_codes": "ADULT"}
        payload = _fetch(session, "https://kyfw.12306.cn/otn/leftTicket/queryG", deadline, params)
        path = payload.get("c_url", "")
        if payload.get("status") is False and isinstance(path, str) and re.fullmatch(r"leftTicket/query[A-Z]?", path):
            payload = _fetch(session, "https://kyfw.12306.cn/otn/" + path, deadline, params)
        rows = extract_rows(payload, pair)
    for train in required:
        if not any(row["train"] == train for row in rows):
            try:
                row = _specific_train(session, pair, train, deadline)
                if row:
                    rows.append(row)
            except (requests.RequestException, ValueError, TypeError, AttributeError, TimeoutError):
                pass  # Missing prices remain unknown, never guessed.
    value = dict(pair=pair, rows=rows, queriedAt=_now(), source="12306公开查询", cached=False)
    _cache[key] = (monotonic(), value)
    _cache.move_to_end(key)
    while len(_cache) > 160:
        _cache.popitem(last=False)
    return value


def _quote_batch(pairs):
    if not _gate.acquire(blocking=False):
        return JSONResponse({"error": "票价查询繁忙，请稍后重试。"}, 429, headers={"Retry-After": "5"})
    try:
        deadline = monotonic() + 25
        results = []
        with requests.Session() as session:
            session.headers.update({"Accept": "application/json", "Referer": _init_url})
            for raw in pairs:
                try:
                    pair = validate_pair(raw)
                    results.append(_quote_pair(session, pair, deadline))
                except (requests.RequestException, TimeoutError):
                    results.append({"pair": raw, "rows": [], "error": "票价来源连接失败或超时，请稍后重试。"})
                except (ValueError, TypeError, AttributeError):
                    results.append({"pair": raw, "rows": [], "error": "参数或票价来源暂不可用，保持待核价；未尝试绕过。"})
        return JSONResponse({"results": results}, headers={"Cache-Control": "no-store"})
    finally:
        _gate.release()


@router.post("/fares")
async def fares(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16000:
            return JSONResponse({"error": "请求过大"}, 413)
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError):
        return JSONResponse({"error": "JSON 格式无效"}, 400)
    pairs = payload.get("pairs") if isinstance(payload, dict) else None
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 8:
        return JSONResponse({"error": "每批支持 1–8 个区间"}, 400)
    return await run_in_threadpool(_quote_batch, pairs)
