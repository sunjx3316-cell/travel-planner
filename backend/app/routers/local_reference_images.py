"""Owner-only reference screenshots; never mark pending third-party media licensed."""
import ipaddress
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from .. import db

router = APIRouter(prefix="/api/local-reference-images", tags=["local references"])


def _loopback(value):
    try:
        return ipaddress.ip_address(value).is_loopback
    except (ValueError, TypeError):
        return False


def local_owner(request):
    if not request.client or not _loopback(request.client.host):
        return False
    if request.url.hostname != "localhost" and not _loopback(request.url.hostname):
        return False
    if any(h in request.headers for h in ("forwarded", "x-forwarded-for", "x-forwarded-host", "x-client-ip")):
        return False
    if request.headers.get("sec-fetch-site") not in (None, "none", "same-origin"):
        return False
    origin = request.headers.get("origin")
    if origin:
        actual, expected = urlsplit(origin), urlsplit(str(request.base_url))
        if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
            return False
    return True


def reference_assets(conn, spot_id, request):
    if not local_owner(request):
        return []
    rows = conn.execute(
        "SELECT id,origin_url,license_note,captured_at,created_at FROM spot_media "
        "WHERE spot_id=? AND provider='xhs_screenshot' AND rights_status='pending' "
        "ORDER BY created_at DESC,id DESC LIMIT 1", (spot_id,),
    ).fetchall()
    return [{"storage_path": f"/api/local-reference-images/{row['id']}",
             "provider": "小红书截图 · 仅本机参考", "license_note": row["license_note"],
             "origin_url": row["origin_url"], "captured_at": row["captured_at"],
             "created_at": row["created_at"], "rights_status": "pending", "local_reference": True}
            for row in rows]


@router.get("/{media_id}")
def reference_image(media_id: int, request: Request):
    if not local_owner(request):
        raise HTTPException(403, "参考截图仅供运行程序的本机查看")
    conn = db.get_conn()
    try:
        row = conn.execute(
            "SELECT storage_path FROM spot_media WHERE id=? "
            "AND provider='xhs_screenshot' AND rights_status='pending'", (media_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(404, "参考截图不存在")
    private_root = (db.DB_PATH.parent / "private/xhs-screenshots").resolve()
    candidate = (db.DB_PATH.parent / row["storage_path"]).resolve()
    if not candidate.is_relative_to(private_root) or candidate.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(404, "参考截图不存在")
    if not candidate.is_file():
        # Explicitly selected release photos only; never expose research folders.
        expected_parent = private_root / 'release-references'
        if candidate.parent != expected_parent or not re.fullmatch(r'[0-9a-f]{64}\.jpg', candidate.name):
            raise HTTPException(404, "参考截图不存在")
        candidate = db.PROJECT_ROOT / 'bundled_data/reference-photos' / candidate.name
        if not candidate.is_file():
            raise HTTPException(404, "参考截图不存在")
    return FileResponse(candidate, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
