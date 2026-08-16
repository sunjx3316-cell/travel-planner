# -*- coding: utf-8 -*-
"""高德地图 POI 数据源:正式版扩充城市与景区名单。

需要高德开放平台 key(个人开发者免费申请): https://lbs.amap.com
配置方式: .env 中 AMAP_KEY=xxxx(或系统环境变量)。

用法: .venv\\Scripts\\python scripts\\fetch_poi.py [城市名...]
"""
import json
import os

import requests

AMAP_TEXT_URL = "https://restapi.amap.com/v3/place/text"


def get_key() -> str:
    key = os.environ.get("AMAP_KEY", "").strip()
    if not key:
        raise RuntimeError("AMAP_KEY 未配置:请在 .env 中填写高德开放平台 key(lbs.amap.com 免费申请)")
    return key


def fetch_scenic_spots(city: str, keywords: str = "景点", page: int = 1) -> list:
    """按城市拉取景点类 POI。返回 [{name, address, rating, lng, lat, type}]"""
    resp = requests.get(
        AMAP_TEXT_URL,
        params={
            "key": get_key(),
            "city": city,
            "keywords": keywords,
            "offset": 25,
            "page": page,
            "extensions": "base",
        },
        timeout=30,
    )
    data = resp.json()
    if data.get("status") != "1":
        raise RuntimeError(f"高德返回错误: {data.get('info')}")
    pois = []
    for p in data.get("pois", []):
        loc = p.get("location", "").split(",")
        try:
            lng, lat = float(loc[0]), float(loc[1])
        except (IndexError, ValueError):
            continue
        biz = p.get("biz_ext", {}) or {}
        try:
            rating = float(biz.get("rating") or 0) or None
        except ValueError:
            rating = None
        pois.append({
            "name": p.get("name", "").strip(),
            "address": p.get("address", ""),
            "rating": rating,
            "lng": lng,
            "lat": lat,
            "type": p.get("type", ""),
        })
    return pois


def import_into_db(conn, city_id: int, pois: list) -> int:
    """将 POI 写入 spots 表(同名跳过)。返回实际新增数。"""
    added = 0
    for p in pois:
        if not p["name"]:
            continue
        tags = [t.strip() for t in (p["type"] or "").split(";") if t.strip()][:3]
        cur = conn.execute(
            "INSERT OR IGNORE INTO spots(city_id, name, poi_rating, address, tags, lng, lat) "
            "VALUES(?,?,?,?,?,?,?)",
            (city_id, p["name"], p["rating"], p["address"],
             json.dumps(tags, ensure_ascii=False), p["lng"], p["lat"]),
        )
        added += cur.rowcount
    return added


# ---------- 多关键词聚合扩充(正式版主力通道) ----------

CITY_KEYWORDS = ["景点", "博物馆", "海洋馆", "科技馆", "动物园", "公园",
                 "古镇", "温泉", "游乐园", "街区", "滑雪场"]
JUNK_KW = ("酒店", "宾馆", "饭店", "餐厅", "食府", "诊所", "医院", "银行",
           "学校", "公司", "政府", "超市", "KTV", "洗浴", "足疗")


def fetch_city_pois(city: str, limit: int = 40) -> list:
    """按城市多关键词聚合拉取可玩 POI,去重并过滤酒店/餐厅等噪音。"""
    out = []
    seen = set()
    for kw in CITY_KEYWORDS:
        if len(out) >= limit:
            break
        try:
            pois = fetch_scenic_spots(city, kw)
        except Exception:
            continue
        for p in pois:
            if not p["name"] or any(j in p["name"] for j in JUNK_KW):
                continue
            key = (p["name"], round(p["lng"], 4), round(p["lat"], 4))
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
    return out[:limit]


# ---------- 通用景区探索(挖掘未评级自然景区) ----------

AMAP_AROUND_URL = "https://restapi.amap.com/v3/place/around"


def _parse_poi(p: dict, keyword: str = "") -> dict:
    loc = p.get("location", "").split(",")
    try:
        lng, lat = float(loc[0]), float(loc[1])
    except (IndexError, ValueError):
        return None
    return {"name": p.get("name", "").strip(), "address": p.get("address", ""),
            "lng": lng, "lat": lat, "type": p.get("type", ""), "keyword": keyword}


def fetch_keyword_pois(district: str, keywords: list, limit: int = 40) -> list:
    """按地区+关键词搜索 POI(适合挖掘未评级自然景区,如草原/湖泊/峡谷)。

    例: fetch_keyword_pois("甘南藏族自治州", ["草原", "湖泊", "峡谷"])
    """
    out = []
    seen = set()
    for kw in keywords:
        page = 1
        while len(out) < limit and page <= 3:
            resp = requests.get(
                AMAP_TEXT_URL,
                params={"key": get_key(), "city": district, "keywords": kw,
                        "offset": 25, "page": page, "extensions": "base"},
                timeout=30,
            )
            data = resp.json()
            if data.get("status") != "1" or not data.get("pois"):
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
        resp = requests.get(
            AMAP_AROUND_URL,
            params={"key": get_key(), "location": f"{lng},{lat}", "keywords": kw,
                    "radius": radius, "offset": 25, "extensions": "base"},
            timeout=30,
        )
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
