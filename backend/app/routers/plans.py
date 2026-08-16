# -*- coding: utf-8 -*-
"""行程方案生成:LLM 优先(多套方案),无 key 时走确定性 mock 规划器。"""
import json
import math
from datetime import datetime

from fastapi import APIRouter, HTTPException

from ...ai.pipeline import get_llm
from ...ai import prompts
from ..db import get_conn
from ..models import (CityPlanRecommendRequest, CityTourRequest, PlanGenerateRequest,
                      PlanOut, RoadtripRequest)

router = APIRouter(prefix="/api", tags=["plans"])

STYLE_PER_DAY = {"轻松": 2, "紧凑": 4, "亲子": 2}
STYLE_DESC = {
    "轻松": "每天2个景点,节奏慢,留足休息时间",
    "紧凑": "每天3-4个景点,效率优先,适合体力好的人",
    "亲子": "每天2个景点,避开高强度项目,节奏适中",
}


def _load_context(city_id: int, spot_ids: list):
    conn = get_conn()
    try:
        city = conn.execute("SELECT * FROM cities WHERE id=?", (city_id,)).fetchone()
        if city is None:
            raise HTTPException(404, "城市不存在")
        rows = conn.execute(
            "SELECT s.id, s.name, s.poi_rating, s.tags, s.lng, s.lat, c.name AS city_name, "
            "ss.summary_json FROM spots s "
            "JOIN cities c ON c.id = s.city_id "
            "LEFT JOIN spot_summaries ss ON ss.spot_id = s.id "
            "WHERE s.id IN (%s)" % ",".join("?" * len(spot_ids)),
            list(spot_ids),
        ).fetchall()
    finally:
        conn.close()
    spots = []
    for r in rows:
        d = dict(r)
        summary = {}
        if d.get("summary_json"):
            try:
                summary = json.loads(d["summary_json"])
            except Exception:
                summary = {}
        spots.append({
            "id": d["id"],
            "name": d["name"],
            "city_name": d["city_name"],
            "rating": d["poi_rating"] or 0,
            "tags": _loads(d.get("tags")),
            "lng": d.get("lng") if d.get("lng") is not None else city["lng"],
            "lat": d.get("lat") if d.get("lat") is not None else city["lat"],
            "consensus": summary.get("consensus_issues", []),
            "trust": summary.get("trust_score", 0),
        })
    spots.sort(key=lambda x: x["id"])
    return dict(city), spots


def _haversine_km(a: dict, b: dict) -> float:
    """两点直线距离(km),基于近似球面。"""
    import math

    R = 6371.0
    lat1, lon1 = math.radians(a["lat"]), math.radians(a["lng"])
    lat2, lon2 = math.radians(b["lat"]), math.radians(b["lng"])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


# 亲子风格需提示强度的项目
HIGH_INTENSITY_TAGS = ("登山", "雪山", "徒步", "爬山", "索道", "攀岩")


def _loads(s):
    try:
        return json.loads(s or "[]")
    except Exception:
        return []


# ---------- mock 规划器 ----------

def mock_plans(city: dict, spots: list, days: int, style: str) -> list:
    if not spots:
        return []
    per_day = STYLE_PER_DAY.get(style, 2)
    use_days = max(1, min(days, math.ceil(len(spots) / per_day)))

    ordered = {
        "紧凑": sorted(spots, key=lambda x: -x["rating"]),
        "轻松": list(spots),
        "亲子": sorted(spots, key=lambda x: -x["rating"]),
    }.get(style, list(spots))

    def chunks(lst, n):
        return [lst[i:i + n] for i in range(0, len(lst), n)]

    daily_chunks = chunks(ordered, per_day)[:use_days]

    all_consensus = []
    for s in spots:
        all_consensus.extend(s["consensus"])
    low_trust = [s["name"] for s in spots if 0 < s["trust"] < 50]

    plans = []
    variants = [
        ("A", f"{style}·按热度排序", "优先玩评分最高的景点,效率与体验平衡"),
        ("B", f"{style}·按你的选择顺序", "完全按你加入清单的顺序走,尊重直觉"),
        ("C", f"{style}·口碑优先", "优先安排口碑信任度高的景点,避坑优先"),
    ]
    for tag, name, summary_text in variants:
        seq = ordered if tag == "A" else (list(spots) if tag == "B" else sorted(spots, key=lambda x: -x["trust"]))
        dc = chunks(seq, per_day)[:use_days]
        daily = []
        for i, chunk in enumerate(dc, 1):
            items = []
            prev = None
            for s in chunk:
                why = f"评分 {s['rating']}"
                if prev is not None:
                    dist = _haversine_km(prev, s)
                    if dist >= 15:
                        why += f";距上一站直线约 {dist:.0f}km,注意交通耗时"
                if style == "亲子" and any(t in s["tags"] for t in HIGH_INTENSITY_TAGS):
                    why += ";强度较高,亲子需评估体力"
                if s["consensus"]:
                    why += f";避雷共识: {s['consensus'][0]}"
                items.append({"spot": s["name"], "why": why})
                prev = s
            daily.append({"day": i, "title": f"第{i}天 · {city['name']}核心行程", "items": items,
                          "stay": _pick_stay(chunk)})
        tips = [f"风格说明:{STYLE_DESC[style]}"]
        if all_consensus:
            tips.append(f"全程避雷提醒: {all_consensus[0]}")
        if low_trust:
            tips.append(f"信任度偏低需降低预期: {', '.join(low_trust[:3])}")
        plans.append({
            "name": f"{tag} | {name}",
            "summary": summary_text,
            "daily": daily,
            "tips": tips,
        })
    return plans


# ---------- LLM 规划 ----------

def _inject_stays(plans: list, spots: list) -> list:
    """为 LLM 生成的方案按每日景点回填住宿推荐(算法计算,防暗广)。"""
    by_name = {s["name"]: s for s in spots}
    for p in plans:
        for day in p.get("daily", []):
            chunk = [by_name[it["spot"]] for it in day.get("items", [])
                     if it.get("spot") in by_name]
            if chunk:
                day["stay"] = _pick_stay(chunk)
    return plans


def llm_plans(city: dict, spots: list, days: int, style: str) -> list:
    spots_txt = "\n".join(
        f"- {s['name']}(评分{s['rating']}, 避雷共识: {'; '.join(s['consensus'][:2]) or '无'}, "
        f"信任度{s['trust']})"
        for s in spots
    )
    user = prompts.PLAN_USER.format(
        city=city["name"],
        days=days,
        style=style,
        spots=spots_txt,
        plan_count=3,
    )
    out = get_llm().chat_json(prompts.PLAN_SYSTEM, user, temperature=0.7)
    raw = out.get("plans", [])
    if not isinstance(raw, list):
        raw = []
    # 只保留结构有效的方案,并标注来源
    valid = []
    for p in raw:
        if isinstance(p, dict) and isinstance(p.get("daily"), list) and p["daily"]:
            p["source"] = "DeepSeek"
            valid.append(p)
    valid = _inject_stays(valid, spots)  # 回填住宿推荐(算法计算)
    # 数量不足时用确定性 mock 补齐,保证始终返回 3 套(混合策略)
    if len(valid) < 3:
        seen = {p.get("name") for p in valid}
        for mp in mock_plans(city, spots, days, style):
            if len(valid) >= 3:
                break
            if mp["name"] not in seen:
                seen.add(mp["name"])
                mp["source"] = "启发式补齐(LLM 方案不足)"
                valid.append(mp)
    plans = valid[:3]
    if not plans:
        raise ValueError("LLM 返回空方案")
    return plans


@router.post("/plans/generate", response_model=list[PlanOut])
def generate_plan(req: PlanGenerateRequest):
    city, spots = _load_context(req.city_id, req.spot_ids)
    if not spots:
        raise HTTPException(400, "清单中没有有效景区")

    if get_llm().available:
        try:
            plans = llm_plans(city, spots, req.days, req.style)
            source = "DeepSeek"
        except Exception:
            plans = mock_plans(city, spots, req.days, req.style)
            source = "启发式 mock(LLM 失败降级)"
    else:
        plans = mock_plans(city, spots, req.days, req.style)
        source = "启发式 mock(未配置 DEEPSEEK_API_KEY)"

    plan_json = {"source": source, "city": city["name"], "days": req.days,
                 "style": req.style, "plans": plans}

    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO plans(plan_json, created_at) VALUES(?,?)",
            (json.dumps(plan_json, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        pid = cur.lastrowid
    finally:
        conn.close()
    return [PlanOut(id=pid, plan={**p, "source": p.get("source") or source}) for p in plans]


# ================= 城市模式(以城市为单位,可多城串联) =================

def _load_foods(city: str) -> dict:
    """城市美食(必吃+美食街,区域级防暗广)。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM city_foods WHERE city=? ORDER BY kind, id", (city,)
        ).fetchall()
    finally:
        conn.close()
    dishes, streets = [], []
    for r in rows:
        d = dict(r)
        item = {"name": d["name"], "where": d["where_hint"] or "",
                "price_low": d["price_low"], "price_high": d["price_high"],
                "note": d["note"] or ""}
        (dishes if d["kind"] == "dish" else streets).append(item)
    return {"dishes": dishes[:6], "streets": streets[:4]}


def _allocate_city_days(counts: dict, needs: dict, total_days: int) -> tuple:
    """多城市天数分配(均衡版,从下限向上加,绝不从理想往下砍):

    1. 下限:需要≥2天的城市至少 2 天,其余至少 1 天;
    2. 富余天数按"项目耗时"need 从多到少分配,每城封顶 cap = 总天数//城市数 + 1
       (内容多的城市不能独吞,也不会被砍到 1 天);
    3. 城市数>天数等极端情况才被迫压回 1 天;
    4. 放不下的城市(分配<理想)由方案溢出+警告,让用户取舍,不挤占他城。
    返回 (out, ideal, hints)。"""
    if not counts:
        return {}, {}, []
    n = len(counts)
    base = max(1, total_days // n)
    cap = base + 1
    ideal = {c: max(1, math.ceil(needs.get(c, 0) or 0)) for c in counts}
    # 下限:总天数足够(≥2×城市数)时每城至少 2 天,避免"511"式畸形分布
    floor = 2 if total_days >= 2 * n else 1
    out = {c: floor for c in counts}
    if sum(out.values()) > total_days:
        # 城市数>天数:从"需要天数最少"的城市压回(每城至少 1 天)
        for c in sorted(counts, key=lambda x: needs.get(x, 0)):
            if sum(out.values()) <= total_days:
                break
            if out[c] > 1:
                out[c] -= 1
        return out, ideal, [c for c in counts if out[c] < ideal[c]]
    spare = total_days - sum(out.values())
    for c in sorted(counts, key=lambda x: -needs.get(x, 0)):
        while spare > 0 and out[c] < min(ideal[c], cap):
            out[c] += 1
            spare -= 1
    while spare > 0:
        cand = [c for c in counts if out[c] < cap]
        if not cand:
            cand = list(counts)
        c = max(cand, key=lambda x: (needs.get(x, 0), out[x]))
        out[c] += 1
        spare -= 1
    hints = [c for c in counts if out[c] < ideal[c]]
    return out, ideal, hints


FUN_KW = ("美食街", "小吃", "夜市", "步行街", "商业街", "酒吧", "夜景", "夜游", "灯光",
          "不夜城", "商圈", "小吃街", "街区")
BIG_KW = ("雪山", "冰川", "徒步", "穿越", "登山", "漂流", "主题乐园", "乐园", "动物园",
          "熊猫", "迪士尼", "环球", "峡谷", "冰雪", "野生动物", "滑雪", "雪场", "水乐园",
          "泰山", "峨眉山", "庐山", "恒山", "嵩山", "井冈山")
DAY_ONLY_KW = ("博物馆", "纪念馆", "科技馆", "美术馆", "溶洞", "展览", "故居", "书院")
FAR_KM = 25.0      # 距市中心≥25km → 远项目(往返+游玩基本一天)
FUN_CAP_KM = 8.0   # 娱乐点距当天景点≤8km 视为"同片区",优先搭配


def _classify_spot(s: dict, center: tuple) -> str:
    """项目分级:big=大项目/远项目(整天) | fun=娱乐(晚间填充) | small=小项目(半日)。"""
    from ..schedule import EVENING, recommend_time

    text = f"{s['name']} {' '.join(s.get('tags') or [])}"
    lng, lat = s.get("lng"), s.get("lat")
    # 远项目优先:即使是小吃街/商圈,离市中心太远也按整天算(如阳朔西街)
    if center and lng is not None and lat is not None and \
            _haversine_km(s, {"lng": center[0], "lat": center[1]}) >= FAR_KM:
        return "big"
    slot, _ = recommend_time(s["name"], s.get("tags") or [], s.get("commercial"))
    if s.get("commercial") or slot == EVENING or any(k in text for k in FUN_KW):
        return "fun"     # 商圈/美食街/夜市/夜景:晚间娱乐
    if any(k in text for k in BIG_KW):
        return "big"     # 雪山/乐园/徒步等:大项目
    return "small"       # 博物馆/塔/城墙/公园等:半日


def _slot_of(s: dict) -> str:
    from ..schedule import recommend_time
    return recommend_time(s["name"], s.get("tags") or [], s.get("commercial"))[0]


def _compose_city_days(city_spots: list, cd: int, center: tuple, variant: str = "A",
                       reserve_last: bool = False) -> tuple:
    """把一个城市的景点排进 cd 天(按"项目消耗天数"模型):

    - 大项目/远项目:独占一天,配 1 个就近娱乐(优先同片区≤8km);
    - 小项目:半日,宽松时 1 个/天(行程散开、留休息日),紧凑时 2 个/天;
    - 娱乐(小吃街/商场/夜市):晚间填充,就近搭配(大雁塔+大唐不夜城、钟楼+钟楼商圈自动同天);
    - 同片区就近聚合成天(小项目按距离就近成对);
    - reserve_last=True:最后一天留给返程,大项目不排最后一天(放不下进 overflow);
    - 放不下的进 overflow(提示延长/舍弃);天数宽松时插「休整日」。
    返回 (chunks, overflow, loose):chunks 长度=cd。
    """
    big, small, fun = [], [], []
    for s in city_spots:
        {"big": big, "small": small, "fun": fun}[_classify_spot(s, center)].append(s)

    chunks = []
    overflow = []
    used_fun = set()

    def has_fun(day):
        return any(id(x) in used_fun for x in day)

    def nearest_fun(day, max_km=None):
        # 锚点=可夜游的景点(博物馆等白天型不算),娱乐优先绑到能晚上一起逛的景点
        anchors = [s for s in day if not any(k in s.get("name", "") for k in DAY_ONLY_KW)]
        if not anchors:
            anchors = day
        best, bd = None, None
        for f in fun:
            if id(f) in used_fun:
                continue
            d = min((_haversine_km(f, s) for s in anchors if s.get("lng") is not None), default=999)
            if max_km is not None and d > max_km:
                continue
            if bd is None or d < bd:
                best, bd = f, d
        return best

    # 1) 大项目:独占一天 + 就近娱乐(同片区优先,否则任意未用娱乐)
    #    若 reserve_last,最后一天留给返程,大项目只占前面的天
    big_days = max(0, cd - 1) if reserve_last else cd
    for i, b in enumerate(big):
        if i >= big_days:
            overflow.append(b)
            continue
        day = [b]
        f = nearest_fun(day, FUN_CAP_KM) or nearest_fun(day)
        if f:
            day.append(f)
            used_fun.add(id(f))
        chunks.append(day)

    # 2) 小项目排天(不同变体 = 不同天的安排 + 不同取舍):
    #    A 经典:就近成对(同片区聚合);B 高分:按评分降序成对(溢出丢低分);
    #    C 轻松:每天 1 个 + 时段互补(上午/下午交替,宁可溢出也不挤)
    if variant == "B":
        small.sort(key=lambda s: -(s.get("rating") or 0))
    elif variant == "C":
        small.sort(key=lambda s: (_slot_of(s) != "下午", -(s.get("rating") or 0)))
    remain = cd - len(chunks)
    if variant == "C":
        per = 1
    else:
        tight = remain < math.ceil(len(small) / 2)
        per = 1 if (not tight and remain >= len(small)) else 2
    while small:
        day = []
        take = min(per, len(small))
        nxt = small.pop(0)
        day.append(nxt)
        for _ in range(take - 1):
            if not small:
                break
            if variant == "A":
                # 就近成对(同片区)
                nxt = min(small, key=lambda s: _haversine_km(day[-1], s))
                small.remove(nxt)
            else:
                # B/C: 按时段互补配对(上午类+下午类),同向者放后面
                cur_slot = _slot_of(day[-1])
                alt = next((s for s in small if _slot_of(s) != cur_slot), None)
                nxt = alt if alt is not None else small.pop(0)
                if alt is not None:
                    small.remove(alt)
            day.append(nxt)
        f = nearest_fun(day, FUN_CAP_KM) or nearest_fun(day)
        if f:
            day.append(f)
            used_fun.add(id(f))
        chunks.append(day)

    # 3) 剩余娱乐:先补到还没配娱乐的实排天;剩下的留给休整日逛街吃
    spare_fun = []
    for f in fun:
        if id(f) in used_fun:
            continue
        target = next((d for d in chunks if d and not has_fun(d)), None)
        if target:
            target.append(f)
            used_fun.add(id(f))
        else:
            spare_fun.append(f)

    # 4) 天数超出:截断进 overflow;不足:均匀插休整日(每 2 个实排天插 1 天),
    #    休整日不放景点,但配商场/小吃街(≤2 个/天)轻松逛吃
    rest_flags = [False] * cd
    if len(chunks) > cd:
        overflow += [s for d in chunks[cd:] for s in d]
        chunks = chunks[:cd]
    elif len(chunks) < cd:
        final = []
        flags = []
        cnt = 0
        for d in chunks:
            final.append(d)
            flags.append(False)
            cnt += 1
            if cnt >= 2 and len(final) < cd:
                final.append([])
                flags.append(True)
                cnt = 0
        while len(final) < cd:
            final.append([])
            flags.append(True)
        # 休整日:塞商场/小吃街(最多 2 个),剩的娱乐才进 overflow
        for i, is_rest in enumerate(flags):
            if is_rest and spare_fun:
                final[i] = spare_fun[:2]
                del spare_fun[:2]
        chunks = final
        rest_flags = flags
    overflow += spare_fun
    return chunks, overflow, rest_flags


def _build_city_plan(name: str, summary: str, order: list, groups: dict, days: int,
                     style: str, close_loop: bool, city_days: dict = None,
                     variant: str = "A") -> dict:
    """按城市顺序生成城市之旅方案:每城可多天(景点/博物馆/美食/住宿)。"""
    from ..schedule import (AFTERNOON, EVENING, SLOT_ORDER, SUNSET, recommend_time)

    legs = _route_legs(order)
    if close_loop and len(order) >= 2:
        last = order[-1]
        first = order[0]
        if last.get("id") != -1 or first.get("id") == -1:  # 回程到出发地/首城
            km = _haversine_km(last, first) * ROAD_FACTOR
            legs.append({
                "from": last["name"], "from_city": last["city_name"],
                "to": first["name"], "to_city": first["city_name"],
                "from_lng": last["lng"], "from_lat": last["lat"],
                "to_lng": first["lng"], "to_lat": first["lat"],
                "km": round(km), "hours": round(km / HIGHWAY_KMH, 1),
                "closing": True,
                "transport": _transport_leg(last, first),
            })
    total_km = sum(l["km"] for l in legs)

    cities = [n for n in order if n.get("id") != -1]
    # 回程段(城市模式也需预留返程时间):末城 → 出发地(有虚拟出发节点用它,否则回首城)
    return_leg = None
    dep_node = next((n for n in order if n.get("id") == -1), None)
    if dep_node is None and cities:
        dep_node = cities[0]
    if dep_node is not None and cities and dep_node is not cities[-1]:
        last_city = cities[-1]
        straight = _haversine_km(last_city, dep_node)
        km = straight * ROAD_FACTOR
        driving_h = round(km / HIGHWAY_KMH, 1)
        rail_h = round(straight / 260 + 1, 1) if straight <= 1500 else None
        if straight <= 350:
            ret_h = driving_h
        elif straight <= 1500:
            ret_h = rail_h
        else:
            ret_h = 4.0
        return_leg = {
            "from": last_city["name"], "from_city": last_city["city_name"],
            "to": dep_node["name"], "to_city": dep_node["city_name"],
            "from_lng": last_city["lng"], "from_lat": last_city["lat"],
            "to_lng": dep_node["lng"], "to_lat": dep_node["lat"],
            "km": round(km), "hours": driving_h, "travel_h": ret_h, "closing": True,
            "transport": _transport_leg(last_city, dep_node),
        }
        legs.append(return_leg)
    total_km = sum(l["km"] for l in legs)
    counts = {c["name"]: len(groups.get(c["name"], [])) for c in cities}
    # 城市中心(用于"远项目"判定)
    centers = {}
    conn = get_conn()
    try:
        for r in conn.execute("SELECT name, lng, lat FROM cities WHERE lng IS NOT NULL").fetchall():
            centers[r["name"]] = (r["lng"], r["lat"])
    finally:
        conn.close()
    # 每城"项目耗时":大项目/远项目 1 天 + 小项目 0.5 天(娱乐随行不占天)
    needs = {}
    for cn in cities:
        cname = cn["name"]
        big_n = sum(1 for s in groups[cname] if _classify_spot(s, centers.get(cname)) == "big")
        small_n = sum(1 for s in groups[cname] if _classify_spot(s, centers.get(cname)) == "small")
        needs[cname] = big_n + small_n * 0.5
    if city_days:
        # 用户/推荐给了每城天数:只保留行程内的城市;总和不足总天数时补足(多余天给项目多的城)
        city_days = {k: max(1, int(v or 1)) for k, v in city_days.items() if k in counts}
        diff = days - sum(city_days.values())
        while diff > 0:
            c = max(city_days, key=lambda x: (counts.get(x, 0), city_days[x]))
            city_days[c] += 1
            diff -= 1
    else:
        # 未指定:按"项目耗时"比例分配(每城≥1天,放不下的城市溢出警告)
        city_days, _, _ = _allocate_city_days(counts, needs, days)

    # 按每城天数展开(每城 cd 天)
    expanded = []
    for cn in cities:
        cd = city_days.get(cn["name"], 1)
        for k in range(cd):
            expanded.append((cn, k, cd))
    use = expanded[: max(1, min(len(expanded), days))]
    # 城际交通耗时:决定换城当天从几点开始玩(到达日≥3h 在途→砍上午;出发日≥3h→砍晚上)
    incoming, outgoing = {}, {}
    for leg in legs:
        if leg.get("closing"):
            continue
        th = leg.get("travel_h") or leg["hours"]
        incoming.setdefault(leg["to_city"], th)
        outgoing[leg["from_city"]] = th
    daily = []
    overflow_warn = []   # 各城放不下的项目汇总,用于偏紧提示
    # 每个城市先排好天(大/小/娱乐分级 + 同片区就近聚合),缓存避免重复计算
    comp_cache = {}
    for day_no, (cn, k, cd) in enumerate(use, 1):
        city_name = cn["name"]
        city_spots = groups[city_name]
        key = city_name
        if key not in comp_cache:
            # 末城有返程时,最后一天留给返程(大项目不排最后一天)
            reserve = (cn is cities[-1]) and return_leg and return_leg.get("travel_h", 0) >= 1.5
            comp_cache[key] = _compose_city_days(city_spots, cd, centers.get(city_name), variant, reserve)
            # 溢出只在城市第一次进入时累计一次(缓存去重)
            overflow_warn += [s for s in comp_cache[key][1]
                              if _classify_spot(s, centers.get(city_name)) != "fun"]
        chunks, overflow, rest_flags = comp_cache[key]
        day_spots = chunks[k]
        # 溢出提示挂在最后一个"实排"天(休整日不算,避免逛街吃那天被塞溢出项)
        real_ks = [i for i, c in enumerate(chunks) if c and not rest_flags[i]]
        last_real = real_ks[-1] if real_ks else cd - 1
        items = []
        item_spots = {}
        for s in day_spots:
            if s.get("grade"):
                tag = f"{s['grade']}景区"
            elif "博物馆" in (s.get("tags") or []):
                tag = "博物馆"
            else:
                tag = ""
            why = f"{s['city_name']}" + (f" · {tag}" if tag else "")
            # 大项目/远项目统一按"全天"展示(与分级一致),其余按时段推荐
            if _classify_spot(s, centers.get(city_name)) == "big":
                slot, reason = "全天", "大项目/远郊景区,含往返交通需一整天,尽早出发"
            else:
                slot, reason = recommend_time(s["name"], s.get("tags") or [], s.get("commercial"))
                if slot == "全天":
                    # 未分类的小项目兜底为半日,绝不显示"全天"
                    slot, reason = AFTERNOON, "半日可逛,下午光线好"
            it = {"spot": s["name"], "why": why, "time": slot, "time_reason": reason}
            items.append(it)
            item_spots[id(it)] = s
        # 全天(大项目)排最前,其余按时段升序(如:全天石林 → 晚上夜市)
        items.sort(key=lambda it: (0 if it.get("time") == "全天" else 1,
                                   SLOT_ORDER.get(it.get("time"), 99)))

        # ---- 弹性时段:同片区可叠加(步行 ≤3.5km 算相邻),不搞"一段只能一处" ----
        WALK_KM = 3.5

        def _coords(it):
            s = item_spots.get(id(it))
            return (s["lng"], s["lat"]) if s and s.get("lng") is not None else None

        def _near(it1, it2):
            c1, c2 = _coords(it1), _coords(it2)
            if not c1 or not c2:
                return False
            return _haversine_km({"lng": c1[0], "lat": c1[1]},
                                 {"lng": c2[0], "lat": c2[1]}) <= WALK_KM

        # 1) 晚上块吸收相邻的"可夜游"小项目(如:大雁塔+大唐不夜城,步行即达一起逛)
        for n_it in [x for x in items if x.get("time") == "晚上"]:
            for it in list(items):
                if it is n_it or it.get("time") not in ("上午", "下午", "傍晚"):
                    continue
                if any(k in it["spot"] for k in DAY_ONLY_KW):
                    continue
                if _near(it, n_it):
                    it["time"] = "晚上"
                    it["time_reason"] = f"紧邻{n_it['spot'].split('·')[0]},步行即达,晚上一起逛"
        # 2) 同一时段内的相邻项目合并展示(如:下午 城墙+兴庆宫 一块儿逛)
        merged = []
        by_block = {}
        for it in items:
            by_block.setdefault(it.get("time"), []).append(it)
        for block, blist in by_block.items():
            out = []
            for it in blist:
                partner = next((o for o in out if _near(it, o)), None)
                if partner and block in ("上午", "下午", "晚上"):
                    partner["spot"] = partner["spot"].split("·")[0] + " + " + it["spot"].split("·")[0]
                    partner["why"] = "两处相邻(步行/骑行即达),可一起安排"
                else:
                    out.append(it)
            merged.extend(out)
        items = merged

        # 3) 只剩"相距较远"的同段项目才错峰互换/改期
        used_slots = set()
        for it in items:
            t = it.get("time")
            if t not in ("上午", "下午"):
                continue
            if t in used_slots:
                alt = "下午" if t == "上午" else "上午"
                if alt not in used_slots:
                    it["time"] = alt
                    it["time_reason"] = "与同天另一项目错峰,该时段可灵活互换"
                    used_slots.add(alt)
                else:
                    it["time"] = ""
                    it["time_reason"] = "时段冲突,建议安排到其他天"
            else:
                used_slots.add(t)
        items.sort(key=lambda it: (0 if it.get("time") == "全天" else 1,
                                   SLOT_ORDER.get(it.get("time"), 99)))
        if not items:
            items = [{"spot": "🧘 休整日", "why": "不安排景点,可逛商场/小吃街或自由活动",
                      "time": "", "time_reason": ""}]
        # 该城最后一个实排天:放不下的项目给出提示(非娱乐=建议延长/舍弃;娱乐=晚间备选)
        if k == last_real:
            for s in overflow:
                if _classify_spot(s, centers.get(city_name)) == "fun":
                    items.append({"spot": s["name"], "why": "晚间备选,有精力可顺路逛逛",
                                  "time": "", "time_reason": ""})
                else:
                    items.append({"spot": s["name"], "why": "项目过多,建议延长天数或取舍",
                                  "time": "", "time_reason": ""})
        # 交通时间感知:到达日砍上午、出发日砍晚上,并给出在途提示
        notes = []
        if rest_flags[k] and items:
            notes.append("🧘 休整日:不赶景点,轻松逛吃")
        in_h = incoming.get(city_name)
        if k == 0 and in_h and in_h >= 3:
            kept, dropped = [], []
            for it in items:
                if SLOT_ORDER.get(it.get("time"), 99) < SLOT_ORDER[AFTERNOON]:
                    dropped.append(it)
                else:
                    kept.append(it)
            items = kept
            for it in dropped:
                items.append({"spot": it["spot"],
                              "why": f"上午在途({it['time']}场次来不及),建议延长天数或改到次日",
                              "time": "", "time_reason": ""})
            notes.append(f"🚄 上午在途:从上一站出发约 {in_h:.1f}h,抵达后行程从下午开始")
        out_h = outgoing.get(city_name)
        if k == cd - 1 and out_h and out_h >= 3:
            kept, dropped = [], []
            for it in items:
                if it.get("time") in (SUNSET, EVENING):
                    dropped.append(it)
                else:
                    kept.append(it)
            items = kept
            for it in dropped:
                items.append({"spot": it["spot"],
                              "why": f"傍晚在途前往下一城({it['time']}场次来不及),建议提前或改期",
                              "time": "", "time_reason": ""})
            notes.append(f"🚄 傍晚出发前往下一城(约 {out_h:.1f}h),当晚行程不宜排太晚")
        # 返程预留:最后一天下午留给回程(用户例:7天行程,第7天下午回家)
        if day_no == len(use) and return_leg and return_leg.get("travel_h", 0) >= 1.5:
            ret_h = return_leg["travel_h"]
            # 到达日(上午在途)时上午块不可用,下午项只能舍弃不能挪到上午
            am_block_ok = not (k == 0 and (incoming.get(city_name) or 0) >= 3)
            kept, dropped = [], []
            am_count = sum(1 for it in items if it.get("time") == "上午")
            for it in items:
                t = it.get("time")
                if t in ("全天", "傍晚", "晚上"):
                    dropped.append(it)
                elif t == "下午":
                    # 灵活的下午项(公园/塔/广场)挪到上午,不砍
                    if am_block_ok and am_count < 2 and not any(k in it["spot"] for k in DAY_ONLY_KW):
                        it["time"] = "上午"
                        it["time_reason"] = "返程日下午留给回程,该活动灵活调整到上午"
                        am_count += 1
                        kept.append(it)
                    else:
                        dropped.append(it)
                else:
                    kept.append(it)
            items = kept
            for it in dropped:
                items.append({"spot": it["spot"],
                              "why": f"下午返程回{return_leg['to_city']}(约{ret_h:.1f}h),该时段留给回程",
                              "time": "", "time_reason": ""})
            notes.append(f"🚄 返程:第{day_no}天下午返回{return_leg['to_city']}(约{ret_h:.1f}h),"
                         f"当天行程只排上午,下午留出返程时间")
            if not items:
                items = [{"spot": "🧳 返程日", "why": f"上午自由活动,下午返回{return_leg['to_city']}",
                          "time": "", "time_reason": ""}]
        items.sort(key=lambda it: (0 if it.get("time") == "全天" else 1,
                                   SLOT_ORDER.get(it.get("time"), 99)))
        title = f"第{day_no}天 · {city_name}" + (f"(第{k + 1}天)" if cd > 1 else "")
        # 前往下一城交通(该城最后一天且后面还有城市)
        next_transport = None
        if day_no < len(use) and use[day_no][0]["name"] != city_name:
            nxt_city = use[day_no][0]["name"]
            order_names = [c["name"] for c in order if c.get("id") != -1]
            idx = order_names.index(city_name) if city_name in order_names else -1
            if 0 <= idx < len(legs) and legs[idx]["to_city"] == nxt_city:
                tr = legs[idx].get("transport", {})
                next_transport = {
                    "to": nxt_city, "km": legs[idx]["km"],
                    "rail": tr.get("rail"), "recommend": tr.get("recommend"),
                }
        daily.append({
            "day": day_no, "title": title, "items": items,
            "note": "；".join(notes) if notes else "",
            "stay": _pick_stay(city_spots), "foods": _load_foods(city_name),
            "next_transport": next_transport,
        })
    if len(expanded) > len(use):
        daily.append({"day": len(use) + 1,
                      "title": "剩余城市(天数不足,建议延长)",
                      "items": [{"spot": c["name"] + " 继续游览", "why": "增加天数后可纳入"} for c, _, _ in expanded[len(use):]],
                      "stay": {"town": "", "price": "", "km_from_last": 0, "note": ""}})
    days_txt = " · ".join(f"{c} {city_days.get(c, 1)}天" for c in [cn["name"] for cn in cities])
    tips = [f"全程约 {total_km}km,途经 {len(cities)} 城 · 每城天数: {days_txt}"]
    if overflow_warn:
        names = "、".join(s["name"] for s in overflow_warn[:4])
        tips.append(f"⚠️ 行程偏紧:有 {len(overflow_warn)} 个项目放不下({names} 等),"
                    f"建议延长天数或从中取舍")
    if close_loop:
        tips.append("🔁 回程:末城返回出发城市")
    elif return_leg:
        tips.append(f"🔁 返程:第{len(use)}天下午从{return_leg['from_city']}返回"
                    f"{return_leg['to_city']}(约{return_leg['travel_h']:.1f}h),当天只排上午")
    return {"name": name, "summary": summary, "route": legs, "daily": daily, "tips": tips}


@router.post("/plans/citytour", response_model=list[PlanOut])
def citytour_plan(req: CityTourRequest):
    spots = _load_spots_multi(req.spot_ids)
    if not spots:
        raise HTTPException(400, "清单为空,请先加入想去的地方")

    groups = {}
    for s in spots:
        groups.setdefault(s["city_name"], []).append(s)

    city_nodes = []
    for c, g in groups.items():
        g0 = g[0]
        city_nodes.append({"id": 0, "name": c, "city_name": c,
                           "lng": g0["lng"], "lat": g0["lat"],
                           "rating": max((x["rating"] for x in g), default=0),
                           "grade": None, "tags": []})

    start = _resolve_start(req.start_city)
    if start and any(c["name"] == start["city_name"] for c in city_nodes):
        # 出发地本身就是目的地城市之一:以该城为起点,不建虚拟节点
        first_city = next(c for c in city_nodes if c["name"] == start["city_name"])
        rest = [c for c in city_nodes if c["name"] != start["city_name"]]
        order_a = [first_city] + _two_opt(rest)
        order_b = [first_city] + _two_opt(sorted(rest, key=lambda c: -c["rating"]))
        order_c = [first_city] + list(reversed(rest))
    elif start:
        order_a = _two_opt([start] + city_nodes)
        order_b = _two_opt([start] + sorted(city_nodes, key=lambda c: -c["rating"]))
        order_c = [start] + list(reversed(order_a[1:])) if len(order_a) > 1 else order_a
    else:
        order_a = _two_opt(city_nodes)
        order_b = _two_opt(sorted(city_nodes, key=lambda c: -c["rating"]))
        order_c = list(reversed(order_a))

    plans = [
        _build_city_plan("A | 经典串联", "城市就近串联;城内按片区就近成对(同片区同天)", order_a, groups, req.days, req.style, req.close_loop, req.city_days, "A"),
        _build_city_plan("B | 高分优先", "城市与城内项目都按评分排;溢出优先舍弃低分项", order_b, groups, req.days, req.style, req.close_loop, req.city_days, "B"),
        _build_city_plan("C | 轻松错峰", "每天只排 1 个景点,上午/下午错峰;行程更松、留白更多", order_c, groups, req.days, req.style, req.close_loop, req.city_days, "C"),
    ]
    # 用真实排期补全摘要(即使无 LLM,3 套方案也各有差异)
    for p in plans:
        day_txt = "；".join(
            f"第{d['day']}天:{','.join(i['spot'].split('·')[0] for i in d['items'][:4])}"
            for d in p["daily"][:6])
        p["summary"] = f"{p['summary']} | 每日:{day_txt}"
    source = "启发式(城市模式)"
    if get_llm().available:
        try:
            # 把真实每日排期喂给 LLM:名字/概述贴合实际,并产出每天实操提醒
            plan_txt = "\n".join(
                f"方案「{p['name']}」\n" + "\n".join(
                    f"  第{d['day']}天 {d['title']}: "
                    + "、".join(f"{i.get('time') or ''}{i['spot'].split('·')[0]}" for i in d['items'][:5])
                    for d in p["daily"][:6])
                for p in plans)
            user = prompts.CITYPLAN_USER.format(count=3, plans=plan_txt, style=req.style)
            out = get_llm().chat_json(prompts.CITYPLAN_SYSTEM, user, temperature=0.7)
            raw = out.get("plans", [])
            valid = [p for p in raw if isinstance(p, dict) and p.get("name")]
            if valid:
                for i, p in enumerate(valid[:3]):
                    base = plans[i % len(plans)]
                    base["name"] = p.get("name", base["name"])
                    if p.get("summary"):
                        base["summary"] = p["summary"]
                    if p.get("tips"):
                        # 保留启发式的 ⚠️ 偏紧警告,再叠加 LLM 提示
                        warns = [t for t in base.get("tips", []) if t.startswith("⚠️")]
                        base["tips"] = (warns + p["tips"])[:6]
                    # 每天 AI 实操提醒:合并进当天 note(与在途/休整提示并存)
                    day_notes = p.get("day_notes") or {}
                    for d in base["daily"]:
                        n = day_notes.get(str(d["day"])) or day_notes.get(d["day"])
                        if n and isinstance(n, str) and n.strip():
                            d["note"] = "；".join(x for x in (d.get("note", ""), n.strip()) if x)
                source = "DeepSeek 智能润色 + 启发式(城市模式)"
        except Exception:
            pass

    plan_json = {"source": source, "mode": "citytour", "plans": plans}
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO plans(plan_json, created_at) VALUES(?,?)",
            (json.dumps(plan_json, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        pid = cur.lastrowid
    finally:
        conn.close()
    return [PlanOut(id=pid, plan={**p, "source": source}) for p in plans]


@router.post("/plans/cityplan-recommend")
def cityplan_recommend(req: CityPlanRecommendRequest):
    """城市规划推荐:每城玩几天 + 起始城 + 城市顺序(依据出发地便利)。"""
    spots = _load_spots_multi(req.spot_ids)
    if not spots:
        raise HTTPException(400, "清单为空")
    groups = {}
    for s in spots:
        groups.setdefault(s["city_name"], []).append(s)

    # 每城推荐天数:按"项目耗时"分配(大项目1天+小项目0.5天);放不下的城市溢出+警告,不挤占他城
    counts = {c: len(g) for c, g in groups.items()}
    conn = get_conn()
    try:
        centers = {r["name"]: (r["lng"], r["lat"])
                   for r in conn.execute("SELECT name, lng, lat FROM cities WHERE lng IS NOT NULL")}
    finally:
        conn.close()
    needs = {}
    for c, g in groups.items():
        big_n = sum(1 for s in g if _classify_spot(s, centers.get(c)) == "big")
        small_n = sum(1 for s in g if _classify_spot(s, centers.get(c)) == "small")
        needs[c] = big_n + small_n * 0.5
    raw, ideal, hints = _allocate_city_days(counts, needs, req.total_days)
    warn = ""
    if hints:
        names = "、".join(f"{c}(需{ideal[c]}天,仅排{raw[c]}天)" for c in hints)
        warn = (f"⚠️ {names} 项目较多,当前天数放不下,请自行取舍或延长;"
                f"不影响其他城市游玩")
    elif len(groups) > req.total_days:
        warn = f"⚠️ 城市数({len(groups)})多于天数({req.total_days}),行程会非常赶,建议减少城市或增加天数"

    # 城市顺序与起始城:出发地在列表内则以它为起点;否则取距出发地最近的城市
    city_nodes = [{"id": 0, "name": c, "city_name": c,
                   "lng": g[0]["lng"], "lat": g[0]["lat"],
                   "rating": max((x["rating"] for x in g), default=0), "grade": None, "tags": []}
                  for c, g in groups.items()]
    start = _resolve_start(req.start_city)
    if start and any(c["name"] == start["city_name"] for c in city_nodes):
        first_city = next(c for c in city_nodes if c["name"] == start["city_name"])
        rest = [c for c in city_nodes if c["name"] != start["city_name"]]
        order = [first_city] + _two_opt(rest)
        start_reason = f"你从 {start['city_name']} 出发,直接从该城开始最方便"
    elif start:
        nearest = min(city_nodes, key=lambda c: _haversine_km(start, c))
        order = [nearest] + _two_opt([c for c in city_nodes if c["name"] != nearest["name"]])
        start_reason = (f"出发地 {start['city_name']} 不在行程中,"
                        f"建议从最近的 {nearest['name']} 开始(直线约 {round(_haversine_km(start, nearest))}km)")
    else:
        order = _two_opt(city_nodes)
        start_reason = "未填出发地,按城市位置就近开始(建议补充出发地更精准)"

    return {
        "start_city": order[0]["name"],
        "start_reason": start_reason,
        "order": [c["name"] for c in order],
        "city_days": raw,
        "min_days": ideal,
        "warn": warn,
        "reasons": {
            "days": {c: f"{len(groups[c])} 个可玩项目(大项目 {max(0, ideal[c]-1)}+),建议 {raw[c]} 天" for c in groups},
            "order": "城市就近串联(2-opt 优化)",
        },
    }


@router.get("/plans", response_model=list[dict])
def recent_plans(limit: int = 3):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, plan_json, created_at FROM plans ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["plan_json"] = json.loads(d["plan_json"] or "{}")
        out.append(d)
    return out


# ================= 自驾模式(多城市) =================

ROAD_FACTOR = 1.4      # 直线距离 → 公路距离估算系数
HIGHWAY_KMH = 80       # 平均公路时速估算


def _load_spots_multi(spot_ids: list) -> list:
    """加载多城市景点(坐标缺失时回退城市坐标)。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT s.id, s.name, s.poi_rating, s.grade, s.tags, s.commercial, "
            "COALESCE(s.lng, c.lng) AS lng, COALESCE(s.lat, c.lat) AS lat, "
            "c.name AS city_name FROM spots s "
            "JOIN cities c ON c.id = s.city_id "
            "WHERE s.id IN (%s) ORDER BY s.id" % ",".join("?" * len(spot_ids)),
            list(spot_ids),
        ).fetchall()
    finally:
        conn.close()
    spots = []
    for r in rows:
        d = dict(r)
        spots.append({
            "id": d["id"], "name": d["name"], "city_name": d["city_name"],
            "rating": d["poi_rating"] or 0, "grade": d.get("grade"),
            "tags": _loads(d.get("tags")),
            "commercial": _loads(d.get("commercial")) if d.get("commercial") else None,
            "lng": d["lng"], "lat": d["lat"],
        })
    return spots


def _nearest_order(spots: list, start_idx: int = None) -> list:
    """最近邻串联;start_idx=None 时从最接近几何中心的点出发。"""
    if not spots:
        return []
    if len(spots) == 1:
        return list(spots)
    unvisited = list(spots)
    if start_idx is not None:
        start = unvisited.pop(start_idx)
    else:
        clng = sum(s["lng"] for s in unvisited) / len(unvisited)
        clat = sum(s["lat"] for s in unvisited) / len(unvisited)
        start = min(unvisited, key=lambda s: _haversine_km(s, {"lng": clng, "lat": clat}))
        unvisited.remove(start)
    order = [start]
    cur = start
    while unvisited:
        nxt = min(unvisited, key=lambda s: _haversine_km(cur, s))
        order.append(nxt)
        unvisited.remove(nxt)
        cur = nxt
    return order


def _tour_len(order: list) -> float:
    """闭环总长(含返回起点的闭合段)。"""
    total = 0.0
    for i in range(len(order)):
        a = order[i]
        b = order[(i + 1) % len(order)]
        total += _haversine_km(a, b)
    return total


def _two_opt(order: list) -> list:
    """2-opt 优化闭环:翻转路段消除交叉并缩短总里程(标准 TSP 启发式)。"""
    best = list(order)
    n = len(best)
    if n < 4:
        return best
    improved = True
    while improved:
        improved = False
        for i in range(n - 1):
            for j in range(i + 1, n):
                if j - i == 1 or (i == 0 and j == n - 1):
                    continue  # 相邻边无需翻转
                new = best[:i + 1] + best[i + 1:j + 1][::-1] + best[j + 1:]
                if _tour_len(new) < _tour_len(best) - 1e-9:
                    best = new
                    improved = True
    return best


def _route_legs(order: list) -> list:
    legs = []
    for i in range(len(order) - 1):
        a, b = order[i], order[i + 1]
        straight = _haversine_km(a, b)
        km = straight * ROAD_FACTOR
        driving_h = round(km / HIGHWAY_KMH, 1)
        rail_h = round(straight / 260 + 1, 1) if straight <= 1500 else None
        # 有效交通耗时:按推荐方式取(自驾/高铁/航班含机场往返)
        if straight <= 350:
            travel_h = driving_h
        elif straight <= 1500:
            travel_h = rail_h
        else:
            travel_h = 4.0   # 航班门到门约 4h
        legs.append({
            "from": a["name"], "from_city": a["city_name"],
            "to": b["name"], "to_city": b["city_name"],
            "from_lng": a["lng"], "from_lat": a["lat"],
            "to_lng": b["lng"], "to_lat": b["lat"],
            "km": round(km), "hours": driving_h, "travel_h": travel_h,
            "transport": _transport_leg(a, b),
        })
    return legs


def _transport_leg(a: dict, b: dict) -> dict:
    """跨城市交通推荐(估算):自驾/高铁/航班 + 推荐方式。"""
    straight = _haversine_km(a, b)
    driving_km = round(straight * ROAD_FACTOR)
    driving_h = round(driving_km / HIGHWAY_KMH, 1)
    out = {"driving": f"{driving_km}km / 约{driving_h}h"}
    if straight <= 1500:
        rail_h = round(straight / 260 + 1, 1)
        rail_price = round(straight * 0.45)
        out["rail"] = f"高铁约{rail_h}h / 二等座约¥{rail_price}"
    if straight >= 400:
        out["flight"] = "航班约2-3h(含机场往返,淡旺季价差大)"
    if straight <= 350:
        out["recommend"] = "自驾/城际大巴较优"
    elif straight <= 1500:
        out["recommend"] = "高铁首选(班次多、准点)"
    else:
        out["recommend"] = "航班 + 落地租车"
    return out


# 地铁线路提示(住宿区域 → 附近线路;无地铁城市标注)
METRO_HINTS = {
    "北京·前门/王府井": "2号线、8号线", "北京·中关村/西直门": "4号线、13号线",
    "上海·南京东路": "2号线、10号线", "上海·陆家嘴": "2号线",
    "广州·天河/珠江新城": "3号线、5号线", "成都市区": "2号线、3号线",
    "重庆·解放碑/洪崖洞": "1号线、6号线", "杭州·西湖周边": "1号线(龙翔桥)",
    "长沙·五一广场": "1号线、2号线", "西安·钟楼/回民街": "2号线、6号线",
    "兰州中心": "1号线", "哈尔滨·中央大街": "2号线",
    "郑州·二七广场": "1号线、3号线", "南京·新街口/夫子庙": "1号线、2号线",
    "武汉·户部巷/江汉路": "2号线、6号线", "济南·泉城广场": "1号线、2号线",
    "合肥·淮河路": "1号线、2号线", "福州·三坊七巷": "1号线",
    "苏州·平江路周边": "1号线、4号线", "沈阳·中街": "1号线",
    "贵阳·喷水池": "1号线、2号线", "南宁·中山路周边": "1号线",
    "昆明·翠湖周边": "1号线", "南昌·八一广场周边": "1号线、2号线",
}


def _pick_stay(day_spots: list) -> dict:
    """按当天玩的地点推荐住宿:几何锚点(质心) → 选距锚点最近/服务匹配的住宿区域。

    输出含区域描述(如"钟楼商圈附近(地铁2号线)")与距离合理性说明。
    区域级推荐,不点名具体商家(防暗广)。
    """
    if not day_spots:
        return {"town": "", "price": "", "km_from_last": 0, "note": "",
                "area_label": "", "fit_note": ""}
    last = day_spots[-1]
    city = last["city_name"]
    # 同城景点做几何锚点
    pts = [s for s in day_spots if s.get("id") != -1 and s.get("lng") is not None
           and s["city_name"] == city]
    if not pts:
        pts = [s for s in day_spots if s.get("lng") is not None]
    anchor = None
    if pts:
        anchor = {"lng": sum(s["lng"] for s in pts) / len(pts),
                  "lat": sum(s["lat"] for s in pts) / len(pts)}

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT town, price_low, price_high, note, serve, lng, lat "
            "FROM stays WHERE city=? ORDER BY id", (city,)
        ).fetchall()
        # 该城商圈/地标(用于区域描述)
        biz = conn.execute(
            "SELECT name, lng, lat FROM spots WHERE city_id=(SELECT id FROM cities WHERE name=?) "
            "AND tags LIKE '%商圈%' AND lng IS NOT NULL",
            (city,),
        ).fetchall()
    finally:
        conn.close()

    # 选住宿:距锚点最近的优先;无坐标或未收录则回退"城区"
    best = None
    if anchor and rows:
        def _d(r):
            if r["lng"] is None:
                return 1e9
            return _haversine_km(anchor, {"lng": r["lng"], "lat": r["lat"]})
        best = min(rows, key=_d)
        if _d(best) > 30:   # 太远视为未匹配
            best = None
    if best is None and rows:
        # 服务匹配兜底
        for r in rows:
            serve = r["serve"] or ""
            if any(s["name"] in serve for s in day_spots):
                best = r
                break
        if best is None:
            best = rows[0]

    if best is None:
        return {"town": f"{city}城区", "price": "线上比价", "km_from_last": 0,
                "note": "当地住宿,建议线上比价后预订", "area_label": f"{city}城区",
                "fit_note": "住宿数据待补充"}

    km = round(_haversine_km(last, {"lng": best["lng"], "lat": best["lat"]}) * ROAD_FACTOR) \
        if best["lng"] is not None else 0
    lo = f"{int(best['price_low'])}" if best["price_low"] else "?"
    hi = f"{int(best['price_high'])}" if best["price_high"] else "?"

    # 区域描述:优先引用距锚点最近的商圈名
    area_label = best["town"]
    if anchor and biz:
        near = min(biz, key=lambda b: _haversine_km(anchor, {"lng": b["lng"], "lat": b["lat"]}))
        if _haversine_km(anchor, {"lng": near["lng"], "lat": near["lat"]}) < 3:
            area_label = f"{near['name']}附近"
    metro = METRO_HINTS.get(best["town"]) or METRO_HINTS.get(city)
    if metro:
        area_label += f"(地铁{metro})"

    # 距离合理性说明
    fit_note = ""
    if anchor and pts:
        ds = sorted(_haversine_km(anchor, {"lng": s["lng"], "lat": s["lat"]}) for s in pts)
        fit_note = f"距当天各景点约 {max(0, round(ds[0] * ROAD_FACTOR))}-{round(ds[-1] * ROAD_FACTOR)}km,位置居中交通方便"

    return {
        "town": best["town"], "price": f"¥{lo}-{hi}/晚",
        "km_from_last": km, "note": best["note"] or "",
        "area_label": area_label, "fit_note": fit_note,
    }


def _chunk_foods(chunk: list) -> dict:
    """按当天行程所到城市聚合美食推荐(必吃+美食街,去重限量)。"""
    merged = {"dishes": [], "streets": []}
    seen_d, seen_s = set(), set()
    for s in chunk:
        if s.get("id") == -1:  # 出发地节点跳过
            continue
        fd = _load_foods(s["city_name"])
        for d in fd["dishes"]:
            if d["name"] not in seen_d:
                seen_d.add(d["name"])
                merged["dishes"].append(d)
        for st in fd["streets"]:
            if st["name"] not in seen_s:
                seen_s.add(st["name"])
                merged["streets"].append(st)
    merged["dishes"] = merged["dishes"][:5]
    merged["streets"] = merged["streets"][:3]
    return merged


def _roadtrip_plan(name: str, summary: str, order: list, style: str, close_loop: bool = True) -> dict:
    per_day = STYLE_PER_DAY.get(style, 2)
    legs = _route_legs(order)
    # 环线闭环:终点返回起点(构成真正的"环")
    if close_loop and len(order) >= 3:
        first, last = order[0], order[-1]
        km = _haversine_km(last, first) * ROAD_FACTOR
        legs.append({
            "from": last["name"], "from_city": last["city_name"],
            "to": first["name"], "to_city": first["city_name"],
            "from_lng": last["lng"], "from_lat": last["lat"],
            "to_lng": first["lng"], "to_lat": first["lat"],
            "km": round(km), "hours": round(km / HIGHWAY_KMH, 1),
            "closing": True,
        })
    total_km = sum(l["km"] for l in legs)
    total_h = sum(l["hours"] for l in legs)
    chunks = [order[i:i + per_day] for i in range(0, len(order), per_day)]
    daily = []
    prev = None
    for i, chunk in enumerate(chunks, 1):
        items = []
        for s in chunk:
            if s.get("id") == -1:  # 出发地
                why = "🚩 出发地"
            else:
                tag = f"{s['grade']}景区" if s.get("grade") else f"评分{s['rating']}"
                why = f"{s['city_name']} · {tag}"
            if prev is not None:
                km = _haversine_km(prev, s) * ROAD_FACTOR
                why += f";距上一站约{round(km)}km / {(km / HIGHWAY_KMH):.1f}h"
            items.append({"spot": s["name"], "why": why})
            prev = s
        daily.append({"day": i, "title": f"第{i}天 · 自驾路段", "items": items,
                      "stay": _pick_stay(chunk), "foods": _chunk_foods(chunk)})
    cities = sorted({s["city_name"] for s in order})
    tips = [f"全程约 {total_km}km,累计驾驶约 {total_h}h(直线距离×1.4 估算,实际以导航为准)"]
    if close_loop and len(order) >= 3:
        tips.append(f"🔁 闭环环线:终点返回起点「{first['name']}」({first['city_name']}),真正环一圈")
    if len(cities) > 1:
        tips.append(f"途经 {len(cities)} 个城市: {' → '.join(cities[:6])}{'...' if len(cities) > 6 else ''},建议提前订沿途住宿")
    return {"name": name, "summary": summary, "route": legs, "daily": daily, "tips": tips}


def _llm_roadtrip(spots: list, base_order: list, style: str, fallback: list) -> list:
    """LLM 为启发式路线撰写方案名/概述/提示(距离仍为估算值,保证可信)。"""
    route_txt = " → ".join(f"{s['name']}({s['city_name']})" for s in base_order)
    user = prompts.ROADTRIP_USER.format(route=route_txt, style=style, plan_count=3)
    out = get_llm().chat_json(prompts.ROADTRIP_SYSTEM, user, temperature=0.7)
    raw = out.get("plans", [])
    valid = [p for p in raw if isinstance(p, dict) and p.get("name")]
    if not valid:
        raise ValueError("LLM 返回空方案")
    merged = []
    for i, p in enumerate(valid[:3]):
        base = fallback[i % len(fallback)]
        m = dict(base)
        m["name"] = p.get("name", base["name"])
        m["summary"] = p.get("summary", base["summary"])
        if p.get("tips"):
            m["tips"] = p["tips"]
        merged.append(m)
    return merged


def _resolve_start(req_start: str):
    """解析出发地城市 → 虚拟起点景点;未提供或找不到返回 None。"""
    name = (req_start or "").strip()
    if not name:
        return None
    conn = get_conn()
    try:
        row = conn.execute("SELECT name, lng, lat FROM cities WHERE name=?", (name,)).fetchone()
    finally:
        conn.close()
    if row is None or row["lng"] is None:
        return None
    return {"id": -1, "name": f"出发地·{row['name']}", "city_name": row["name"],
            "rating": 0, "grade": None, "lng": row["lng"], "lat": row["lat"]}


@router.post("/plans/roadtrip", response_model=list[PlanOut])
def roadtrip_plan(req: RoadtripRequest):
    spots = _load_spots_multi(req.spot_ids)
    if len(spots) < 2:
        raise HTTPException(400, "自驾模式至少需要 2 个景区(可跨城市加入清单)")

    start = _resolve_start(req.start_city)
    max_rating_idx = max(range(len(spots)), key=lambda i: spots[i]["rating"])
    if start:
        # 出发地固定在起点,2-opt 对全程(含出发/返回段)优化
        base = _two_opt([start] + _nearest_order(spots))
        b_order = _two_opt([start] + _nearest_order(spots, max_rating_idx))
        c_order = [start] + list(reversed(base[1:])) if len(base) > 1 else base
    else:
        base = _two_opt(_nearest_order(spots))
        b_order = _two_opt(_nearest_order(spots, max_rating_idx))
        c_order = list(reversed(base))
    fallback = [
        _roadtrip_plan("A | 最短路线", "最近邻+2-opt 优化串联,总里程最短且路线少交叉", base, req.style, req.close_loop),
        _roadtrip_plan("B | 高分优先", "从评分最高的景区出发串联(同样 2-opt 优化)", b_order, req.style, req.close_loop),
        _roadtrip_plan("C | 反向环线", "最短路线反向,适合不同出发方向", c_order, req.style, req.close_loop),
    ]
    source = "启发式(自驾估算)"
    if get_llm().available:
        try:
            fallback = _llm_roadtrip(spots, base, req.style, fallback)
            source = "DeepSeek 润色 + 启发式(自驾估算)"
        except Exception:
            pass

    plan_json = {"source": source, "mode": "roadtrip", "plans": fallback}
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO plans(plan_json, created_at) VALUES(?,?)",
            (json.dumps(plan_json, ensure_ascii=False), datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        pid = cur.lastrowid
    finally:
        conn.close()
    return [PlanOut(id=pid, plan={**p, "source": source}) for p in fallback]
