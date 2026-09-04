# -*- coding: utf-8 -*-
"""景区详情与 AI 分析触发。"""
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...ai.pipeline import summarize_spot
from ..db import get_conn
from ..models import SpotDetailOut, SummaryCard

router = APIRouter(prefix="/api", tags=["spots"])


def _loads(s, default=None):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


@router.get("/spots/{spot_id}", response_model=SpotDetailOut)
def spot_detail(spot_id: int):
    conn = get_conn()
    try:
        s = conn.execute(
            """SELECT s.*, c.name AS city_name FROM spots s
               JOIN cities c ON c.id = s.city_id WHERE s.id = ?""",
            (spot_id,),
        ).fetchone()
        if s is None:
            raise HTTPException(404, "景区不存在")
        notes = conn.execute(
            "SELECT title, content, note_type, is_sample, images_json, source_url, fetched_at "
            "FROM notes WHERE spot_id=? ORDER BY id",
            (spot_id,),
        ).fetchall()
        summary = conn.execute(
            "SELECT summary_json FROM spot_summaries WHERE spot_id=?", (spot_id,)
        ).fetchone()
        media = conn.execute(
            "SELECT storage_path, provider, license_note, origin_url, captured_at, created_at "
            "FROM spot_media WHERE spot_id=? AND rights_status='verified' "
            "ORDER BY created_at DESC, id DESC",
            (spot_id,),
        ).fetchall()
        alts = conn.execute(
            """SELECT a.price_note, a.note, a.downsides_json,
                      s.id AS alt_id, s.name AS alt_name, s.grade AS alt_grade,
                      s.lng AS alt_lng, s.lat AS alt_lat, c.name AS alt_city
               FROM spot_alternatives a
               JOIN spots s ON s.id = a.alt_spot_id
               JOIN cities c ON c.id = s.city_id
               WHERE a.spot_id = ?""",
            (spot_id,),
        ).fetchall()
    finally:
        conn.close()

    d = dict(s)
    d["tags"] = _loads(d.get("tags"), [])
    d["commercial"] = _loads(d.get("commercial")) if d.get("commercial") else None
    d["notes"] = [dict(n) for n in notes]
    d["summary"] = _loads(summary["summary_json"]) if summary else None
    # 只返回已核验授权的台账图片；历史笔记图片仅作为兼容补充。
    d["image_assets"] = [dict(item) for item in media]
    images = [item["storage_path"] for item in media]
    for n in notes:
        imgs = _loads(n["images_json"], [])
        if isinstance(imgs, list):
            images.extend(imgs)
    d["images"] = images[:9]
    # 平替推荐
    d["alternatives"] = [
        {
            "alt_id": a["alt_id"], "alt_name": a["alt_name"],
            "alt_city": a["alt_city"], "alt_grade": a["alt_grade"],
            "alt_lng": a["alt_lng"], "alt_lat": a["alt_lat"],
            "price_note": a["price_note"] or "",
            "note": a["note"] or "",
            "downsides": _loads(a["downsides_json"], []),
        }
        for a in alts
    ]
    return d


@router.post("/spots/{spot_id}/summarize", response_model=SummaryCard)
def run_summarize(spot_id: int):
    conn = get_conn()
    try:
        s = conn.execute(
            "SELECT name FROM spots WHERE id=?", (spot_id,)
        ).fetchone()
        if s is None:
            raise HTTPException(404, "景区不存在")
        notes = conn.execute(
            "SELECT * FROM notes WHERE spot_id=? ORDER BY id", (spot_id,)
        ).fetchall()
    finally:
        conn.close()

    if not notes:
        card = SummaryCard(source="暂无笔记数据,待小红书采集", note_count=0)
    else:
        card = SummaryCard(**summarize_spot(s["name"], [dict(n) for n in notes]))

    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO spot_summaries(spot_id, summary_json, updated_at) VALUES(?,?,?)",
            (spot_id, card.model_dump_json(), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
    return card


# ---------- 应用内用户评价(P2 自产评价:合规、可控、长期口碑主源) ----------

class ReviewIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    title: str = ""
    note_type: str = ""   # guide/avoid/mixed,空=自动


@router.post("/spots/{spot_id}/reviews")
def add_review(spot_id: int, review: ReviewIn):
    """用户提交一条评价 → 自动入库 + 重算该景点 AI 口碑卡。"""
    from ...collector import review_source

    try:
        result = review_source.ingest_items(spot_id, [{
            "type": review.note_type, "title": review.title, "content": review.content,
            "source": "user",
        }])
    except ValueError as e:
        raise HTTPException(400, str(e))
    if result["added"] == 0:
        raise HTTPException(409, "这条内容已提交过(去重)")
    return {"added": result["added"], "summary_rebuilt": result["summary"]}
