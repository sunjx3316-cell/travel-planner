# -*- coding: utf-8 -*-
"""景点图片台账：记录存储位置、来源与授权状态，避免把平台图片直接当作可发布资产。"""
from datetime import datetime
from urllib.parse import urlparse

from ..app.db import get_conn

VALID_RIGHTS = {"pending", "verified", "rejected"}


def _valid_storage_path(value: str) -> bool:
    """允许本地受控 images/ 路径或 HTTPS/COS/CDN URL，不接受任意 file: 地址。"""
    value = (value or "").strip()
    if value.startswith("images/"):
        return True
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def ingest_media(spot_id: int, item: dict, conn=None) -> dict:
    """登记一张图片；只有 verified 图片会由景点详情 API 返回。"""
    if not isinstance(item, dict):
        raise ValueError("图片记录必须是对象")
    storage_path = (item.get("storage_path") or "").strip()
    origin_url = (item.get("origin_url") or "").strip()
    provider = (item.get("provider") or "").strip()
    rights_status = (item.get("rights_status") or "pending").strip()
    if not _valid_storage_path(storage_path):
        raise ValueError("storage_path 必须是 images/... 或 HTTPS 存储/CDN 地址")
    if not origin_url or not provider:
        raise ValueError("origin_url 和 provider 必填，用于追溯来源")
    if rights_status not in VALID_RIGHTS:
        raise ValueError("rights_status 只能是 pending / verified / rejected")

    own = conn is None
    conn = conn or get_conn()
    try:
        if conn.execute("SELECT 1 FROM spots WHERE id=?", (spot_id,)).fetchone() is None:
            raise ValueError(f"景点 id={spot_id} 不存在")
        cur = conn.execute(
            "INSERT OR IGNORE INTO spot_media(spot_id, storage_path, origin_url, provider, license_note, "
            "rights_status, captured_at, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (spot_id, storage_path, origin_url, provider, (item.get("license_note") or "").strip(),
             rights_status, (item.get("captured_at") or "").strip(),
             datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        return {"added": cur.rowcount, "public": rights_status == "verified"}
    finally:
        if own:
            conn.close()
