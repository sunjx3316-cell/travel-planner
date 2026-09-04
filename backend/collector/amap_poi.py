# -*- coding: utf-8 -*-
"""高德地图 POI 数据源:正式版扩充城市与景区名单。

需要高德开放平台 key(个人开发者免费申请): https://lbs.amap.com
配置方式: .env 中 AMAP_KEY=xxxx(或系统环境变量)。

用法: .venv\\Scripts\\python scripts\\fetch_poi.py [城市名...]
"""
import json
import os
from dataclasses import dataclass
from datetime import datetime

import requests

AMAP_TEXT_URL = "https://restapi.amap.com/v3/place/text"
AMAP_PROVIDER = "amap"


def get_key() -> str:
    key = os.environ.get("AMAP_KEY", "").strip()
    if not key:
        raise RuntimeError("AMAP_KEY 未配置:请在 .env 中填写高德开放平台 key(lbs.amap.com 免费申请)")
    return key


def _parse_poi(p: dict, keyword: str = "") -> dict | None:
    """把高德返回转为内部候选结构；坐标/名称不合法的记录直接丢弃。"""
    loc = (p.get("location") or "").split(",")
    try:
        lng, lat = float(loc[0]), float(loc[1])
    except (IndexError, ValueError):
        return None
    name = (p.get("name") or "").strip()
    if not name:
        return None
    biz = p.get("biz_ext") or {}
    try:
        rating = float(biz.get("rating") or 0) or None
    except (TypeError, ValueError):
        rating = None
    try:
        comment_count = int(biz.get("comment_num") or 0) or None
    except (TypeError, ValueError):
        comment_count = None
    return {
        "amap_id": str(p.get("id") or p.get("poi_id") or "").strip(),
        "name": name,
        "address": (p.get("address") or "").strip(),
        "rating": rating,
        "comment_count": comment_count,
        "lng": lng,
        "lat": lat,
        "type": (p.get("type") or "").strip(),
        "typecode": (p.get("typecode") or "").strip(),
        "keyword": keyword,
    }


def _request(params: dict) -> dict:
    """单一请求出口：不吞掉 HTTP/JSON/高德业务错误，便于任务重试。"""
    resp = requests.get(AMAP_TEXT_URL, params={"key": get_key(), **params}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if str(data.get("status")) != "1":
        raise RuntimeError(f"高德返回错误: {data.get('info') or data.get('infocode') or 'unknown'}")
    return data


def fetch_scenic_spots(city: str, keywords: str = "景点", page: int = 1) -> list:
    """按城市拉取景点类 POI，保留高德 POI ID 以支持后续更新与去重。"""
    data = _request({"city": city, "citylimit": "true", "keywords": keywords,
                     "offset": 25, "page": page, "extensions": "all"})
    return [item for p in data.get("pois", []) if (item := _parse_poi(p, keywords))]


@dataclass
class ImportStats:
    added: int = 0
    updated: int = 0
    skipped: int = 0
    source_records: int = 0


def _merge_tags(old_tags: str | None, poi_type: str, keyword: str = "") -> str:
    try:
        merged = list(json.loads(old_tags or "[]"))
    except (TypeError, json.JSONDecodeError):
        merged = []
    for tag in [*[(x.strip()) for x in (poi_type or "").split(";")], keyword]:
        if tag and tag not in merged:
            merged.append(tag)
    return json.dumps(merged[:8], ensure_ascii=False)


def _fallback_external_id(poi: dict) -> str:
    return f"{poi['name']}@{poi['lng']:.6f},{poi['lat']:.6f}"


def import_into_db_stats(conn, city_id: int, pois: list) -> ImportStats:
    """把高德候选写入主表与来源表。

    优先按高德 POI ID 匹配，其次按同城同名匹配。重复抓取只更新数据与来源快照，
    不会制造重复景点或重复证据。
    """
    stats = ImportStats()
    now = datetime.now().isoformat(timespec="seconds")
    for p in pois:
        if not p["name"]:
            stats.skipped += 1
            continue
        amap_id = p.get("amap_id") or ""
        external_id = amap_id or _fallback_external_id(p)
        row = None
        if amap_id:
            row = conn.execute("SELECT * FROM spots WHERE amap_poi_id=?", (amap_id,)).fetchone()
        if row is None:
            row = conn.execute("SELECT * FROM spots WHERE city_id=? AND name=?", (city_id, p["name"])).fetchone()
        if row is None:
            cur = conn.execute(
                "INSERT INTO spots(city_id, name, poi_rating, address, tags, lng, lat, amap_poi_id, "
                "data_source, source_updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (city_id, p["name"], p.get("rating"), p.get("address", ""),
                 _merge_tags(None, p.get("type", ""), p.get("keyword", "")), p["lng"], p["lat"],
                 amap_id or None, AMAP_PROVIDER, now),
            )
            spot_id = cur.lastrowid
            stats.added += 1
        else:
            spot_id = row["id"]
            conn.execute(
                "UPDATE spots SET poi_rating=COALESCE(?, poi_rating), "
                "address=CASE WHEN ?<>'' THEN ? ELSE address END, tags=?, lng=?, lat=?, "
                "amap_poi_id=COALESCE(?, amap_poi_id), data_source=?, source_updated_at=? WHERE id=?",
                (p.get("rating"), p.get("address", ""), p.get("address", ""),
                 _merge_tags(row["tags"], p.get("type", ""), p.get("keyword", "")), p["lng"], p["lat"],
                 amap_id or None, AMAP_PROVIDER, now, spot_id),
            )
            stats.updated += 1
        payload = {k: p.get(k) for k in ("amap_id", "name", "address", "type", "typecode", "lng", "lat", "rating", "comment_count", "keyword")}
        conn.execute(
            "INSERT INTO spot_sources(spot_id, provider, external_id, source_url, payload_json, fetched_at, confidence) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(spot_id, provider, external_id) DO UPDATE SET "
            "payload_json=excluded.payload_json, fetched_at=excluded.fetched_at, confidence=excluded.confidence",
            (spot_id, AMAP_PROVIDER, external_id, None, json.dumps(payload, ensure_ascii=False), now, 0.8),
        )
        stats.source_records += 1
    return stats


def import_into_db(conn, city_id: int, pois: list) -> int:
    """兼容旧调用：返回实际新增数。新采集任务请使用 import_into_db_stats。"""
    return import_into_db_stats(conn, city_id, pois).added


# ---------- 多关键词聚合扩充(正式版主力通道) ----------

CITY_KEYWORDS = ["景点", "博物馆", "海洋馆", "科技馆", "动物园", "公园",
                 "古镇", "温泉", "游乐园", "街区", "滑雪场"]
JUNK_KW = ("酒店", "宾馆", "饭店", "餐厅", "食府", "诊所", "医院", "银行",
           "学校", "公司", "政府", "超市", "KTV", "洗浴", "足疗")


def fetch_city_pois(city: str, limit: int = 40, pages_per_keyword: int = 1) -> list:
    """按城市多关键词聚合拉取可玩 POI,去重并过滤酒店/餐厅等噪音。"""
    get_key()  # 配置缺失应该立即失败，而不是吞掉后得到“零结果”。
    out = []
    seen = set()
    errors = []
    for kw in CITY_KEYWORDS:
        if len(out) >= limit:
            break
        for page in range(1, max(1, pages_per_keyword) + 1):
            try:
                pois = fetch_scenic_spots(city, kw, page)
            except Exception as exc:
                errors.append(f"{kw}: {exc}")
                break
            if not pois:
                break
            for p in pois:
                text = f"{p['name']} {p.get('type', '')}"
                if any(j in text for j in JUNK_KW):
                    continue
                key = p.get("amap_id") or (p["name"], round(p["lng"], 4), round(p["lat"], 4))
                if key in seen:
                    continue
                seen.add(key)
                out.append(p)
                if len(out) >= limit:
                    break
            if len(out) >= limit or len(pois) < 25:
                break
    if not out and errors:
        raise RuntimeError("; ".join(errors[:3]))
    return out[:limit]


# ---------- 通用景区探索(挖掘未评级自然景区) ----------

AMAP_AROUND_URL = "https://restapi.amap.com/v3/place/around"


def fetch_keyword_pois(district: str, keywords: list, limit: int = 40) -> list:
    """按地区+关键词搜索 POI(适合挖掘未评级自然景区,如草原/湖泊/峡谷)。

    例: fetch_keyword_pois("甘南藏族自治州", ["草原", "湖泊", "峡谷"])
    """
    out = []
    seen = set()
    for kw in keywords:
        page = 1
        while len(out) < limit and page <= 3:
            data = _request({"city": district, "citylimit": "true", "keywords": kw,
                             "offset": 25, "page": page, "extensions": "base"})
            if not data.get("pois"):
                break
            for p in data["pois"]:
                item = _parse_poi(p, kw)
                if not item or not item["name"]:
                    continue
                key = (item["name"], item["lng"], item["lat"])
                if key in seen:
                    continue
                seen.add(key)
                out.append(item)
            page += 1
        if len(out) >= limit:
            break
    return out[:limit]


def fetch_around_pois(lng: float, lat: float, keywords: list,
                      radius: int = 30000, limit: int = 40) -> list:
    """以某点为中心,周边半径内关键词搜索(适合沿路线挖掘沿途景点)。"""
    out = []
    seen = set()
    for kw in keywords:
        resp = requests.get(AMAP_AROUND_URL, params={"key": get_key(), "location": f"{lng},{lat}",
                            "keywords": kw, "radius": radius, "offset": 25, "extensions": "base"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1":
            continue
        for p in data.get("pois", []):
            item = _parse_poi(p, kw)
            if not item or not item["name"]:
                continue
            key = (item["name"], item["lng"], item["lat"])
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        if len(out) >= limit:
            break
    return out[:limit]


def import_explore_pois(conn, city_name: str, province: str, pois: list,
                        tag: str = "探索发现") -> int:
    """把探索到的 POI 导入为景点(grade 空 = 非评级)。城市不存在则自动创建。"""
    row = conn.execute("SELECT id FROM cities WHERE name=?", (city_name,)).fetchone()
    if row is None:
        lng = sum(p["lng"] for p in pois) / len(pois) if pois else None
        lat = sum(p["lat"] for p in pois) / len(pois) if pois else None
        cur = conn.execute(
            "INSERT INTO cities(name, province, lng, lat) VALUES(?,?,?,?)",
            (city_name, province, lng, lat),
        )
        cid = cur.lastrowid
    else:
        cid = row["id"]
    added = 0
    for p in pois:
        tags = [tag]
        if p.get("keyword"):
            tags.append(p["keyword"])
        cur = conn.execute(
            "INSERT OR IGNORE INTO spots(city_id, name, address, tags, lng, lat) VALUES(?,?,?,?,?,?)",
            (cid, p["name"], p.get("address", ""),
             json.dumps(tags, ensure_ascii=False), p["lng"], p["lat"]),
        )
        added += cur.rowcount
    conn.commit()
    return added
