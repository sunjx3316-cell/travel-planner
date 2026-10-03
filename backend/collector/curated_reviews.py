"""Import structured, source-linked review research without regenerating its conclusions."""
import hashlib
import json
import re
import sqlite3
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

COLUMNS = ("highlights", "bottom_line_cautions", "preferences", "practical_conditions",
           "comment_insights", "disagreements")
DDL = """
CREATE TABLE IF NOT EXISTS curated_reviews (
    catalog_key TEXT PRIMARY KEY,
    spot_id INTEGER REFERENCES spots(id),
    city TEXT NOT NULL,
    name TEXT NOT NULL,
    review_status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    dataset_updated_at TEXT,
    imported_at TEXT NOT NULL,
    archive_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_curated_reviews_spot ON curated_reviews(spot_id);
"""


def normalize(value):
    return re.sub(r"[\s·•（）()\-—]", "", value or "").casefold()


def city_key(value):
    value = normalize(value)
    return value[:-1] if value.endswith("市") else value


def read_bundle(path):
    with zipfile.ZipFile(path) as archive:
        info = next((i for i in archive.infolist() if i.filename == "景点评价.json"), None)
        if not info or info.file_size > 30 * 1024 * 1024:
            raise ValueError("缺少景点评价.json 或文件超过30MB")
        bundle = json.loads(archive.read(info).decode("utf-8-sig"))
    if bundle.get("format_version") != "poi-reviews-v1" or not isinstance(bundle.get("pois"), list):
        raise ValueError("不支持的评价格式")
    seen = set()
    for poi in bundle["pois"]:
        key = (poi.get("city"), poi.get("name"))
        if not all(key) or key in seen:
            raise ValueError(f"空名称或重复目录：{key}")
        seen.add(key)
        if poi.get("review_status") not in {"summary_ready", "weak_evidence", "no_evidence"}:
            raise ValueError(f"无效评价状态：{key}")
        sources = poi.get("sources", [])
        ids = [s.get("id") for s in sources]
        if None in ids or len(set(ids)) != len(ids):
            raise ValueError(f"来源编号重复或缺失：{key}")
        for column in COLUMNS:
            for point in poi.get(column, []):
                if not isinstance(point, dict) or not point.get("text"):
                    raise ValueError(f"评价条目不完整：{key}/{column}")
                if set(point.get("source_refs", [])) - set(ids):
                    raise ValueError(f"来源引用失效：{key}/{column}")
    return bundle


def import_bundle(conn, bundle, archive_hash, dry_run=False):
    spots = conn.execute("SELECT s.id,s.name,c.name AS city FROM spots s JOIN cities c ON c.id=s.city_id").fetchall()
    candidates = {}
    exact = {}
    for spot in spots:
        candidates.setdefault((city_key(spot[2]), normalize(spot[1])), []).append(spot[0])
        exact.setdefault((spot[2], spot[1]), []).append(spot[0])
    report = {"catalog_rows": len(bundle["pois"]), "matched": 0, "unmatched": [],
              "statuses": dict(Counter(p["review_status"] for p in bundle["pois"])),
              "source_records": 0, "distinct_source_urls": 0}
    urls = set()
    now = datetime.now(timezone.utc).isoformat()
    if not dry_run:
        conn.executescript(DDL)
    with conn:
        for poi in bundle["pois"]:
            matches = exact.get((poi["city"], poi["name"])) or candidates.get((city_key(poi["city"]), normalize(poi["name"])), [])
            spot_id = matches[0] if len(matches) == 1 else None
            if spot_id:
                report["matched"] += 1
            else:
                report["unmatched"].append({"city": poi["city"], "name": poi["name"], "reason": "多重匹配" if matches else "未精确匹配"})
            report["source_records"] += len(poi.get("sources", []))
            urls.update(s["url"] for s in poi.get("sources", []) if s.get("url"))
            if not dry_run:
                # City/name is the identity; archive numbering is not an application spot ID.
                key = hashlib.sha256((poi["city"] + "\0" + poi["name"]).encode()).hexdigest()
                conn.execute("""INSERT INTO curated_reviews VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(catalog_key) DO UPDATE SET spot_id=excluded.spot_id,
                    review_status=excluded.review_status,payload_json=excluded.payload_json,
                    dataset_updated_at=excluded.dataset_updated_at,imported_at=excluded.imported_at,
                    archive_hash=excluded.archive_hash""",
                    (key, spot_id, poi["city"], poi["name"], poi["review_status"],
                     json.dumps(poi, ensure_ascii=False), bundle.get("updated_at"), now, archive_hash))
    report["distinct_source_urls"] = len(urls)
    return report
