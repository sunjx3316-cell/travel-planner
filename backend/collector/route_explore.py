# -*- coding: utf-8 -*-
"""沿环线/路线自动挖掘沿途景点(框架核心,纯逻辑可单测)。

流程:以每个点位为中心做周边关键词搜索 → 合并去重 → 排除已收录景点 → 预览/导入。
需要 .env 配置 AMAP_KEY(高德开放平台,免费)。
"""
from . import amap_poi

DEFAULT_KEYWORDS = ["草原", "湖泊", "峡谷", "观景台", "湿地", "雪山"]


def collect_discoveries(centers: list, fetch_around, existing_names: list,
                        limit: int = 300) -> list:
    """沿多个中心点收集周边新景点。

    centers: [{"name", "lng", "lat"}, ...]
    fetch_around: 可调用 (lng, lat) -> [{"name","address","lng","lat","type","keyword"}, ...]
    existing_names: 已收录景点名(跳过)
    返回去重后不在已有名单中的发现,每条带 near(附近中心点)。
    """
    seen = set(existing_names)
    out = []
    for c in centers:
        try:
            pois = fetch_around(c["lng"], c["lat"])
        except Exception:
            continue
        for p in pois:
            name = (p.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            out.append({**p, "near": c["name"]})
            if len(out) >= limit:
                return out
    return out


def route_centers_from_loop(loop_name: str) -> list:
    """从内置环线数据取中心点列表。"""
    from ..app.seed_loops import CITY_COORDS_LOOPS, LOOPS

    loop = LOOPS.get(loop_name)
    if not loop:
        raise ValueError(f"未找到环线: {loop_name}(可选: {', '.join(LOOPS)})")
    centers = []
    for _province, city, spot, _tags, slng, slat in loop["spots"]:
        lng, lat = CITY_COORDS_LOOPS[city]
        centers.append({"name": spot, "lng": slng if slng is not None else lng,
                        "lat": slat if slat is not None else lat})
    return centers


def amap_around_fetcher(keywords: list, radius: int = 20000, limit: int = 20):
    """构造 amap 周边搜索 fetcher(供 collect_discoveries 使用)。"""
    def _fetch(lng, lat):
        return amap_poi.fetch_around_pois(lng, lat, keywords, radius=radius, limit=limit)
    return _fetch
