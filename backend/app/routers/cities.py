# -*- coding: utf-8 -*-
"""城市与景区查询。"""
from fastapi import APIRouter, HTTPException

from ..db import get_conn
from ..models import CityOut, LoopOut, SpotMapOut, SpotOut

router = APIRouter(prefix="/api", tags=["cities"])


@router.get("/cities", response_model=list[CityOut])
def list_cities():
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT c.*, COUNT(s.id) AS spot_count
               FROM cities c LEFT JOIN spots s ON s.city_id = c.id
               GROUP BY c.id ORDER BY c.id"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.get("/cities/{city_id}/spots", response_model=list[SpotOut])
def city_spots(city_id: int):
    conn = get_conn()
    try:
        city = conn.execute("SELECT id FROM cities WHERE id=?", (city_id,)).fetchone()
        if city is None:
            raise HTTPException(404, "城市不存在")
        rows = conn.execute(
            """SELECT s.*, c.name AS city_name,
                      (SELECT 1 FROM spot_summaries ss WHERE ss.spot_id = s.id) AS has_summary
               FROM spots s JOIN cities c ON c.id = s.city_id
               WHERE s.city_id = ?
               ORDER BY s.poi_rating DESC, s.id""",
            (city_id,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = _loads(d.get("tags"))
        d["commercial"] = _loads(d.get("commercial")) if d.get("commercial") else None
        d["has_summary"] = bool(d.get("has_summary"))
        out.append(d)
    return out


@router.get("/loops", response_model=list[LoopOut])
def list_loops():
    """精选自驾环线(含全部点位,可一键加入清单)。"""
    from ..categories import classify_spot
    from ..seed_loops import LOOPS

    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT s.id, s.name, s.tags, s.grade, s.lng, s.lat, c.name AS city_name
               FROM spots s JOIN cities c ON c.id = s.city_id
               WHERE s.tags LIKE '%环线:%' ORDER BY s.id"""
        ).fetchall()
    finally:
        conn.close()
    groups = {}
    for r in rows:
        tags = _loads(r["tags"])
        loop = next((t.split(":", 1)[1] for t in tags if t.startswith("环线:")), None)
        if not loop:
            continue
        groups.setdefault(loop, []).append({
            "id": r["id"], "name": r["name"], "city_name": r["city_name"],
            "lng": r["lng"], "lat": r["lat"],
            "tags": [t for t in tags if not t.startswith("环线:")],
            "grade": r["grade"],
            "category": classify_spot(r["name"], [t for t in tags if not t.startswith("环线:")]),
        })
    out = []
    for name, spots in groups.items():
        meta = LOOPS.get(name, {})
        out.append({"name": name, "desc": meta.get("desc", ""),
                    "days": meta.get("days", ""), "spots": spots})
    return out


@router.get("/province/{province}/spots", response_model=list[SpotMapOut])
def province_spots(province: str):
    """省级地图景点散点(带自然/人文分类)。"""
    from ..categories import classify_spot

    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT s.id, s.name, s.lng, s.lat, s.grade, s.tags, c.name AS city_name
               FROM spots s JOIN cities c ON c.id = s.city_id
               WHERE c.province = ? AND s.lng IS NOT NULL
               ORDER BY s.id""",
            (province,),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        tags = _loads(d["tags"])
        d["tags"] = tags
        d["category"] = classify_spot(d["name"], tags)
        d["commercial"] = _loads(d.get("commercial")) if d.get("commercial") else None
        out.append(d)
    return out


@router.get("/cities/{city_id}/foods")
def city_foods(city_id: int):
    """城市美食:必吃小吃 + 美食街(区域级,防暗广)。"""
    conn = get_conn()
    try:
        city = conn.execute("SELECT name FROM cities WHERE id=?", (city_id,)).fetchone()
        if city is None:
            raise HTTPException(404, "城市不存在")
        rows = conn.execute(
            "SELECT * FROM city_foods WHERE city=? ORDER BY kind, id", (city["name"],)
        ).fetchall()
    finally:
        conn.close()
    dishes, streets = [], []
    for r in rows:
        d = dict(r)
        item = {"name": d["name"], "where": d["where_hint"] or "",
                "price_low": d["price_low"], "price_high": d["price_high"],
                "note": d["note"] or "", "lng": d["lng"], "lat": d["lat"]}
        (dishes if d["kind"] == "dish" else streets).append(item)
    return {"city": city["name"], "dishes": dishes, "streets": streets}


@router.get("/province/{province}/foods")
def province_foods(province: str):
    """省级地图上的美食街/聚集点(带坐标,可上图标注)。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT f.name, f.lng, f.lat, f.where_hint, c.name AS city_name
               FROM city_foods f JOIN cities c ON c.name = f.city
               WHERE c.province = ? AND f.kind = 'street' AND f.lng IS NOT NULL
               ORDER BY f.id""",
            (province,),
        ).fetchall()
    finally:
        conn.close()
    return [{"name": r["name"], "city_name": r["city_name"],
             "lng": r["lng"], "lat": r["lat"], "where": r["where_hint"] or ""}
            for r in rows]


def _loads(s):
    import json

    try:
        return json.loads(s or "[]")
    except Exception:
        return []
