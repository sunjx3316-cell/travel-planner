# -*- coding: utf-8 -*-
"""评价采集框架:任何来源的信息,喂进来就自动入库并重算 AI 口碑卡。

设计目标「只要获取信息就能做」:
- 拿到任意来源的文本(网页复制/接口返回/用户提交),按标准 item 结构喂给
  `ingest_items(spot_id, items)` 即可 —— 自动去重、自动分类(攻略/避雷/混合)、
  自动重算 AI 口碑卡(暗广过滤/共识差评/信任度);
- 接入新来源只需实现一个 `ReviewSource.fetch(spot) -> list[item]`。

item 标准结构:
    {
      "type": "guide"|"avoid"|"mixed"|""(空=自动分类),
      "title": "标题",
      "content": "正文(必须有,否则仅当评分条目)",
      "author": "作者昵称(会做匿名哈希)",
      "source": "mafengwo|ctrip|dianping|amap|baidu|xhs|user",
      "url": "来源链接(去重键;无则用内容哈希)",
      "score": 4.6 | None,          # 官方聚合评分
      "comment_count": 21000 | None,# 评论数/热度
      "tags": ["排队", "价格"]      # 可选主题标签
    }

用法:
    # 手工粘贴任意文本(最常用)
    python scripts/import_reviews.py --spot 故宫 --source mafengwo --text "..."

    # 批量文件(每行一条;可带 [avoid]/[guide] 前缀或 `标题 | 内容`)
    python scripts/import_reviews.py --spot 故宫 --file reviews.txt

    # 应用内用户评价
    POST /api/spots/{spot_id}/reviews   {"content": "...", "title": "..."}
"""
import hashlib
import json
import sqlite3
from datetime import datetime

from ..app.db import get_conn
from ..ai import pipeline

VALID_TYPES = ("guide", "avoid", "mixed")


def auto_classify(content: str, title: str = "") -> str:
    """按词表自动分类:同时有避雷词和攻略意图->mixed;只有避雷词->avoid;否则 guide。"""
    text = f"{title} {content}"
    neg = sum(1 for k in pipeline.AVOID_WORDS if k in text)
    guide = sum(1 for k in ("攻略", "推荐", "路线", "怎么去", "行程", "游玩",
                            "建议", "提醒", "开放时间", "交通") if k in text)
    if neg >= 1 and guide >= 1:
        return "mixed"
    if neg >= 1:
        return "avoid"
    return "guide"


class ReviewSource:
    """数据源基类:实现 fetch(spot) 返回 list[item] 即接入一个新来源。"""

    name = "base"
    label = "未命名来源"

    def fetch(self, spot: dict) -> list:
        raise NotImplementedError(
            f"[{self.label}] 未实现自动抓取。请先手工获取数据,然后用脚本/接口喂入:\n"
            f"  python scripts/import_reviews.py --spot {spot.get('name', '?')} --source {self.name} --text \"...\""
        )


class GenericPaste(ReviewSource):
    """手工粘贴/任意文本来源:item 直接入库(最通用的接入方式)。"""

    name = "paste"
    label = "手工粘贴(通用)"

    def __init__(self, items: list):
        self.items = items

    def fetch(self, spot: dict) -> list:
        return self.items


class AmapRating(ReviewSource):
    """高德官方评分/评论数(需 .env 配 AMAP_KEY,lbs.amap.com 免费申请)。

    高德 POI 搜索的 biz_ext 字段(评分/评论数)不一定每城都有,拉不到就返回空,
    不影响其他来源。"""

    name = "amap"
    label = "高德评分"

    def fetch(self, spot: dict) -> list:
        from . import amap_poi
        import requests

        key = amap_poi.get_key()
        city = spot.get("city_name", "")
        resp = requests.get(
            amap_poi.AMAP_TEXT_URL,
            params={"key": key, "city": city, "keywords": spot["name"],
                    "offset": 1, "extensions": "all"},
            timeout=30,
        )
        data = resp.json()
        if data.get("status") != "1" or not data.get("pois"):
            return []
        p = data["pois"][0]
        biz = p.get("biz_ext") or {}
        try:
            rating = float(biz.get("rating") or 0) or None
        except (TypeError, ValueError):
            rating = None
        try:
            comments = int(biz.get("comment_num") or 0) or None
        except (TypeError, ValueError):
            comments = None
        if rating is None and comments is None:
            return []
        return [{
            "type": "guide", "title": "高德官方评分",
            "content": f"高德评分 {rating} 分,评论 {comments} 条" if rating else f"高德评论 {comments} 条",
            "source": "amap", "url": f"amap:{spot['name']}",
            "score": rating, "comment_count": comments,
        }]


class BaiduRating(ReviewSource):
    """百度地图评分/评论数(需 .env 配 BAIDU_AK,百度地图开放平台申请)。"""

    name = "baidu"
    label = "百度评分"

    def fetch(self, spot: dict) -> list:
        import os
        import requests

        ak = os.environ.get("BAIDU_AK", "").strip()
        if not ak:
            raise RuntimeError("BAIDU_AK 未配置:请在 .env 中填写百度地图开放平台 key")
        resp = requests.get(
            "https://api.map.baidu.com/place/v2/search",
            params={"ak": ak, "query": spot["name"], "region": spot.get("city_name", ""),
                    "output": "json", "scope": 2, "page_size": 1},
            timeout=30,
        )
        data = resp.json()
        results = data.get("results") or []
        if not results:
            return []
        r = results[0]
        detail = r.get("detail_info") or {}
        rating = detail.get("overall_rating")
        comments = detail.get("comment_num")
        if rating is None and comments is None:
            return []
        return [{
            "type": "guide", "title": "百度地图评分",
            "content": f"百度评分 {rating} 分,评论 {comments} 条" if rating else f"百度评论 {comments} 条",
            "source": "baidu", "url": f"baidu:{spot['name']}",
            "score": float(rating) if rating is not None else None,
            "comment_count": int(comments) if comments is not None else None,
        }]


# 建议来源与现状(供 --list-sources 展示)
SOURCE_GUIDE = {
    "paste": "手工粘贴任意文本(网页复制/聊天记录/自己写的评价),最通用",
    "amap": "高德官方评分/评论数,需 AMAP_KEY(lbs.amap.com 免费申请)",
    "baidu": "百度地图评分/评论数,需 BAIDU_AK(百度地图开放平台)",
    "xhs": "小红书笔记,见 scripts/collect_xhs.py --login 登录后自动采集",
    "mafengwo": "马蜂窝攻略:当前建议复制文本走 paste;自动抓取待做(需过 cookie 反爬)",
    "ctrip": "携程点评:反爬强+法律风险,不建议自动抓取,复制文本走 paste",
    "dianping": "大众点评:字体加密+账号风控+法律风险,不建议,复制文本走 paste",
}


def normalize_item(it: dict) -> dict:
    """规范化单条 item;非法结构抛 ValueError。"""
    if not isinstance(it, dict):
        raise ValueError("item 必须是 dict")
    content = (it.get("content") or "").strip()
    title = (it.get("title") or content[:40]).strip()
    ntype = it.get("type") or ""
    if ntype and ntype not in VALID_TYPES:
        raise ValueError(f"非法 type: {ntype}(应为 guide/avoid/mixed 或空=自动)")
    if not content and it.get("score") is None:
        raise ValueError("item 缺少 content(评分条目除外)")
    source = (it.get("source") or "user").strip()
    author = (it.get("author") or "").strip()
    url = (it.get("url") or "").strip()
    score = it.get("score")
    comments = it.get("comment_count")
    return {
        "type": ntype or (auto_classify(content, title) if content else "guide"),
        "title": title,
        "content": content,
        "author": author,
        "source": source,
        "url": url,
        "score": float(score) if score is not None else None,
        "comment_count": int(comments) if comments is not None else None,
    }


def ingest_items(spot_id: int, items: list, conn: sqlite3.Connection = None,
                 reprocess: bool = True) -> dict:
    """入库一批 item 并重算该景点口碑卡。

    返回 {"added": 新增笔记数, "scores": 更新的评分来源数, "summary": bool 是否重算}。
    """
    own = conn is None
    conn = conn or get_conn()
    added = 0
    scores = 0
    try:
        spot = conn.execute("SELECT id, name FROM spots WHERE id=?", (spot_id,)).fetchone()
        if spot is None:
            raise ValueError(f"景点 id={spot_id} 不存在")
        now = datetime.now().isoformat(timespec="seconds")
        for raw in items:
            it = normalize_item(raw)
            # 聚合指标(评分/评论数):更新 poi_rating,不入 notes
            if it["score"] is not None or it["comment_count"] is not None:
                cur = conn.execute(
                    "UPDATE spots SET poi_rating=? WHERE id=? "
                    "AND (poi_rating IS NULL OR poi_rating<?)",
                    (it["score"], spot_id, it["score"] or 0))
                scores += cur.rowcount
            if not it["content"]:
                continue
            author_hash = (hashlib.sha256(it["author"].encode("utf-8")).hexdigest()[:16]
                           if it["author"] else "")
            # 去重:来源链接优先,无链接用内容哈希
            url = it["url"] or "hash:" + hashlib.sha256(it["content"].encode("utf-8")).hexdigest()[:32]
            cur = conn.execute(
                "INSERT OR IGNORE INTO notes(spot_id, title, content, author_hash, note_type, "
                "source_url, fetched_at, is_sample) VALUES(?,?,?,?,?,?,?,0)",
                (spot_id, it["title"], it["content"], author_hash, it["type"],
                 f"{it['source']}:{url}", now))
            added += cur.rowcount
        conn.commit()
        if reprocess and (added or scores):
            _reprocess_spot(conn, spot_id, spot["name"])
    finally:
        if own:
            conn.close()
    return {"added": added, "scores": scores, "summary": bool(added or scores)}


def _reprocess_spot(conn: sqlite3.Connection, spot_id: int, spot_name: str) -> None:
    """用该景点全部笔记重算 AI 口碑卡并落库。"""
    rows = conn.execute(
        "SELECT title, content, author_hash, note_type FROM notes WHERE spot_id=? ORDER BY id",
        (spot_id,)).fetchall()
    notes = [dict(r) for r in rows]
    if not notes:
        return
    out = pipeline.summarize_spot(spot_name, notes)
    conn.execute(
        "INSERT OR REPLACE INTO spot_summaries(spot_id, summary_json, updated_at) VALUES(?,?,?)",
        (spot_id, json.dumps(out, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")))
    conn.commit()


def list_missing(conn: sqlite3.Connection = None, limit: int = 30) -> list:
    """列出还没有真实笔记(仅示例)的景点,供采集参考。"""
    own = conn is None
    conn = conn or get_conn()
    try:
        rows = conn.execute(
            "SELECT s.id, s.name, c.name AS city FROM spots s "
            "JOIN cities c ON c.id = s.city_id "
            "WHERE NOT EXISTS (SELECT 1 FROM notes n WHERE n.spot_id = s.id AND n.is_sample = 0) "
            "ORDER BY s.id LIMIT ?", (limit,)).fetchall()
        return [{"id": r["id"], "name": r["name"], "city": r["city"]} for r in rows]
    finally:
        if own:
            conn.close()
