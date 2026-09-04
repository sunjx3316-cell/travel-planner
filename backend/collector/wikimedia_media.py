# -*- coding: utf-8 -*-
"""从 Wikimedia Commons 获取可复用景点缩略图，并把作者/许可随图片台账入库。

仅作为首批公开授权图片源：逐项保留文件页与许可，拒绝未知/非自由许可。
"""
import hashlib
import re
from pathlib import Path

import requests

from .media_source import ingest_media

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
ALLOWED_LICENSES = ("CC0", "Public domain", "CC BY", "CC-BY", "CC BY-SA", "CC-BY-SA")


def _plain(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value or "")).strip()


def _metadata_value(meta: dict, key: str) -> str:
    return _plain(((meta.get(key) or {}).get("value") or ""))


def _is_reusable(license_name: str) -> bool:
    normalized = license_name.lower()
    if any(value in normalized for value in ("cc-by-nc", "cc by-nc", "noncommercial", "no derivatives", "cc-by-nd")):
        return False
    return any(value.lower() in normalized for value in ALLOWED_LICENSES)


def search_asset(query: str) -> dict | None:
    """搜索一张有可追溯自由许可的缩略图；不下载时也可用于人工核验。"""
    response = requests.get(COMMONS_API, params={
        "action": "query", "format": "json", "generator": "search", "gsrsearch": query,
        "gsrnamespace": 6, "gsrlimit": 8, "prop": "imageinfo",
        "iiprop": "url|extmetadata", "iiurlwidth": 1200,
    }, timeout=30, headers={"User-Agent": "TravelPlannerLearningDemo/0.1 (contact: local-demo)"})
    response.raise_for_status()
    pages = (response.json().get("query") or {}).get("pages") or {}
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        license_name = _metadata_value(meta, "LicenseShortName") or _metadata_value(meta, "UsageTerms")
        thumb_url = info.get("thumburl") or info.get("url")
        origin_url = info.get("descriptionurl") or ""
        if not thumb_url or not origin_url or not _is_reusable(license_name):
            continue
        author = _metadata_value(meta, "Artist") or "作者信息见文件页"
        license_url = _metadata_value(meta, "LicenseUrl")
        return {
            "thumb_url": thumb_url,
            "origin_url": origin_url,
            "provider": "wikimedia_commons",
            "license_note": f"{license_name}; 作者: {author}" + (f"; 许可: {license_url}" if license_url else ""),
        }
    return None


def download_and_ingest(spot_id: int, spot_name: str, data_dir: Path, conn=None) -> dict:
    """下载一张缩略图到 data/images/wikimedia，并登记为已核验公开授权资产。"""
    asset = search_asset(spot_name)
    if asset is None:
        return {"added": 0, "reason": "未找到可用自由许可图片"}
    response = requests.get(asset["thumb_url"], timeout=45,
                            headers={"User-Agent": "TravelPlannerLearningDemo/0.1 (contact: local-demo)"})
    response.raise_for_status()
    if len(response.content) > 8 * 1024 * 1024:
        return {"added": 0, "reason": "缩略图超过 8MB，跳过"}
    content_type = response.headers.get("content-type", "").lower()
    suffix = ".png" if "png" in content_type else ".webp" if "webp" in content_type else ".jpg"
    token = hashlib.sha256(asset["origin_url"].encode("utf-8")).hexdigest()[:16]
    safe_name = re.sub(r"[^\w\-]+", "-", spot_name, flags=re.UNICODE).strip("-")[:40] or "spot"
    rel = f"images/wikimedia/{safe_name}-{token}{suffix}"
    target = data_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(response.content)
    result = ingest_media(spot_id, {
        "storage_path": rel, "origin_url": asset["origin_url"], "provider": asset["provider"],
        "license_note": asset["license_note"], "rights_status": "verified",
    }, conn=conn)
    result["path"] = rel
    result["license_note"] = asset["license_note"]
    return result
