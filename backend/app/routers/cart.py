# -*- coding: utf-8 -*-
"""购物车:想去清单。"""
from datetime import datetime

from fastapi import APIRouter, HTTPException

from ..db import get_conn
from ..models import CartItemOut

router = APIRouter(prefix="/api", tags=["cart"])


@router.get("/cart", response_model=list[CartItemOut])
def get_cart():
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT ci.id, ci.spot_id, ci.added_at, s.name, c.name AS city_name
               FROM cart_items ci
               JOIN spots s ON s.id = ci.spot_id
               JOIN cities c ON c.id = s.city_id
               ORDER BY ci.id"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.post("/cart/{spot_id}", status_code=201)
def add_to_cart(spot_id: int):
    conn = get_conn()
    try:
        exists = conn.execute("SELECT 1 FROM spots WHERE id=?", (spot_id,)).fetchone()
        if exists is None:
            raise HTTPException(404, "景区不存在")
        conn.execute(
            "INSERT OR IGNORE INTO cart_items(spot_id, added_at) VALUES(?,?)",
            (spot_id, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.delete("/cart")
def clear_cart():
    conn = get_conn()
    try:
        conn.execute("DELETE FROM cart_items")
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.delete("/cart/{spot_id}")
def remove_from_cart(spot_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM cart_items WHERE spot_id=?", (spot_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
