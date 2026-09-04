# -*- coding: utf-8 -*-
"""API 集成测试:使用独立测试库(TRAVEL_DB_PATH,见 conftest.py)。"""
from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def _loads(s):
    import json

    try:
        return json.loads(s or "[]")
    except Exception:
        return []


def test_status():
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert "llm_available" in body and "version" in body


def test_cities():
    r = client.get("/api/cities")
    assert r.status_code == 200
    cities = r.json()
    assert len(cities) >= 10          # 原 10 城 + 5A 扩充
    assert all("spot_count" in c for c in cities)
    bj = next(c for c in cities if c["name"] == "北京")
    assert bj["spot_count"] >= 10     # 5 原景区 + 5 个新增 5A


def test_city_spots():
    cities = client.get("/api/cities").json()
    bj = next(c for c in cities if c["name"] == "北京")
    r = client.get(f"/api/cities/{bj['id']}/spots")
    assert r.status_code == 200
    spots = r.json()
    assert len(spots) >= 10
    assert any(s["name"] == "故宫博物院" for s in spots)
    assert any(s["grade"] == "5A" for s in spots)   # 5A 徽标数据
    assert all("data_source" in s and "source_updated_at" in s for s in spots)


def test_5a_national_seeded():
    """全国 5A 景区已入库(30+ 省市,100+ 景区)"""
    from backend.app.db import get_conn

    conn = get_conn()
    try:
        n5a = conn.execute("SELECT COUNT(*) c FROM spots WHERE grade='5A'").fetchone()["c"]
        ncity = conn.execute("SELECT COUNT(*) c FROM cities").fetchone()["c"]
        provinces = conn.execute(
            "SELECT COUNT(DISTINCT province) c FROM cities WHERE province!=''"
        ).fetchone()["c"]
    finally:
        conn.close()
    assert n5a >= 100
    assert ncity >= 100
    assert provinces >= 30


def test_spot_detail():
    cities = client.get("/api/cities").json()
    bj = next(c for c in cities if c["name"] == "北京")
    spots = client.get(f"/api/cities/{bj['id']}/spots").json()
    gugong = next(s for s in spots if s["name"] == "故宫博物院")
    r = client.get(f"/api/spots/{gugong['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "故宫博物院"
    assert len(body["notes"]) == 4
    assert "images" in body
    assert "source_url" in body["notes"][0]
    assert "fetched_at" in body["notes"][0]


def test_submit_user_review_rebuilds_summary_and_dedupes():
    """用户评价匿名入库、重算口碑卡，并按内容去重。"""
    from backend.app.db import get_conn

    cities = client.get("/api/cities").json()
    bj = next(c for c in cities if c["name"] == "北京")
    spot = next(s for s in client.get(f"/api/cities/{bj['id']}/spots").json()
                if s["name"] == "故宫博物院")
    body = {
        "title": "周末实测",
        "note_type": "avoid",
        "content": "周六上午检票排队约四十分钟，建议提前预约并避开中午。",
    }
    try:
        first = client.post(f"/api/spots/{spot['id']}/reviews", json=body)
        assert first.status_code == 200
        assert first.json()["added"] == 1 and first.json()["summary_rebuilt"] is True
        duplicate = client.post(f"/api/spots/{spot['id']}/reviews", json=body)
        assert duplicate.status_code == 409
        detail = client.get(f"/api/spots/{spot['id']}").json()
        assert detail["summary"] is not None
        assert any((n.get("source_url") or "").startswith("user:") for n in detail["notes"])
    finally:
        # 该用例验证写入行为，但不能改变后续种子数据断言。
        conn = get_conn()
        try:
            conn.execute("DELETE FROM notes WHERE spot_id=? AND title=? AND content=?",
                         (spot["id"], body["title"], body["content"]))
            conn.commit()
        finally:
            conn.close()
        client.post(f"/api/spots/{spot['id']}/summarize")


def test_image_assets_only_return_verified():
    """待审核图片不应被景点详情 API 发布。"""
    from backend.app.db import get_conn
    from backend.collector.media_source import ingest_media

    cities = client.get("/api/cities").json()
    bj = next(c for c in cities if c["name"] == "北京")
    spot = next(s for s in client.get(f"/api/cities/{bj['id']}/spots").json()
                if s["name"] == "故宫博物院")
    paths = ("images/test-pending.jpg", "images/test-verified.jpg")
    conn = get_conn()
    try:
        ingest_media(spot["id"], {"storage_path": paths[0], "origin_url": "https://example.com/pending",
                                    "provider": "official", "rights_status": "pending"}, conn=conn)
        ingest_media(spot["id"], {"storage_path": paths[1], "origin_url": "https://example.com/verified",
                                    "provider": "official", "rights_status": "verified"}, conn=conn)
        detail = client.get(f"/api/spots/{spot['id']}").json()
        assert paths[1] in detail["images"]
        assert paths[0] not in detail["images"]
        assert detail["image_assets"][0]["provider"] == "official"
    finally:
        conn.execute("DELETE FROM spot_media WHERE spot_id=? AND storage_path IN (?, ?)",
                     (spot["id"], *paths))
        conn.commit()
        conn.close()


def test_summarize_creates_consensus():
    """故宫示例笔记 -> mock 管线应产出共识差评(闭馆/排队)"""
    cities = client.get("/api/cities").json()
    bj = next(c for c in cities if c["name"] == "北京")
    spots = client.get(f"/api/cities/{bj['id']}/spots").json()
    gugong = next(s for s in spots if s["name"] == "故宫博物院")
    r = client.post(f"/api/spots/{gugong['id']}/summarize")
    assert r.status_code == 200
    card = r.json()
    assert len(card["consensus_issues"]) >= 1
    assert 0 <= card["trust_score"] <= 100
    assert card["note_count"] == 4
    # 已持久化,详情接口能读到
    detail = client.get(f"/api/spots/{gugong['id']}").json()
    assert detail["summary"] is not None


def test_cart_flow():
    cities = client.get("/api/cities").json()
    bj = next(c for c in cities if c["name"] == "北京")
    spots = client.get(f"/api/cities/{bj['id']}/spots").json()
    sid = spots[0]["id"]

    assert client.post(f"/api/cart/{sid}").status_code == 201
    assert client.post(f"/api/cart/{sid}").status_code == 201  # 重复添加幂等
    cart = client.get("/api/cart").json()
    assert len(cart) == 1
    assert cart[0]["spot_id"] == sid

    assert client.delete(f"/api/cart/{sid}").status_code == 200
    assert len(client.get("/api/cart").json()) == 0

    # 清空端点
    client.post(f"/api/cart/{sid}")
    assert len(client.get("/api/cart").json()) == 1
    assert client.delete("/api/cart").status_code == 200
    assert len(client.get("/api/cart").json()) == 0


def test_supplement_sample_notes_idempotent():
    """示例笔记增量补种:重复初始化不重复插入;新景区补上、老景区不动"""
    from backend.app.db import get_conn, init_db

    init_db()  # 第二次初始化,应幂等
    conn = get_conn()
    try:
        disney = conn.execute(
            "SELECT COUNT(*) c FROM notes n JOIN spots s ON s.id=n.spot_id WHERE s.name='上海迪士尼乐园'"
        ).fetchone()["c"]
        gugong = conn.execute(
            "SELECT COUNT(*) c FROM notes n JOIN spots s ON s.id=n.spot_id WHERE s.name='故宫博物院'"
        ).fetchone()["c"]
    finally:
        conn.close()
    assert disney == 2   # 新补种
    assert gugong == 4   # 已有则不动


def test_plans_generate():
    cities = client.get("/api/cities").json()
    bj = next(c for c in cities if c["name"] == "北京")
    spots = client.get(f"/api/cities/{bj['id']}/spots").json()
    body = {
        "city_id": bj["id"],
        "days": 2,
        "style": "轻松",
        "spot_ids": [s["id"] for s in spots[:4]],
    }
    r = client.post("/api/plans/generate", json=body)
    assert r.status_code == 200
    plans = r.json()
    assert len(plans) == 3
    p0 = plans[0]["plan"]
    assert "daily" in p0 and len(p0["daily"]) > 0
    assert p0["daily"][0]["items"][0]["spot"]


def test_seed_coords_backfilled():
    """种子景区坐标已回填(供路线距离校验)"""
    from backend.app.db import get_conn

    conn = get_conn()
    try:
        row = conn.execute("SELECT lng, lat FROM spots WHERE name='故宫博物院'").fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["lng"] is not None and abs(row["lng"] - 116.397) < 0.01
    assert row["lat"] is not None


def test_plans_include_distance_note():
    """跨区景点(八达岭->天坛)应出现直线距离提示"""
    cities = client.get("/api/cities").json()
    bj = next(c for c in cities if c["name"] == "北京")
    spots = client.get(f"/api/cities/{bj['id']}/spots").json()
    body = {"city_id": bj["id"], "days": 2, "style": "轻松",
            "spot_ids": [s["id"] for s in spots[:4]]}
    plans = client.post("/api/plans/generate", json=body).json()
    why_text = " ".join(it["why"] for p in plans for day in p["plan"]["daily"] for it in day["items"])
    assert "km" in why_text


def test_plans_child_style_intensity_hint():
    """亲子风格对登山类景区应提示强度"""
    cities = client.get("/api/cities").json()
    bj = next(c for c in cities if c["name"] == "北京")
    spots = client.get(f"/api/cities/{bj['id']}/spots").json()
    body = {"city_id": bj["id"], "days": 3, "style": "亲子",
            "spot_ids": [s["id"] for s in spots[:4]]}
    plans = client.post("/api/plans/generate", json=body).json()
    why_text = " ".join(it["why"] for p in plans for day in p["plan"]["daily"] for it in day["items"])
    assert "强度较高" in why_text


def test_media_mount_serves_local_images():
    """采集图片经 /media 可访问(挂载必须优先于前端兜底)"""
    from backend.app.main import DATA_DIR

    probe = DATA_DIR / "media_probe.txt"
    probe.write_text("probe", encoding="utf-8")
    try:
        r = client.get("/media/media_probe.txt")
        assert r.status_code == 200
        assert r.text == "probe"
    finally:
        probe.unlink(missing_ok=True)


def test_plans_llm_path(monkeypatch):
    """配置假 key 时,方案生成应走 LLM 分支并标注来源 DeepSeek"""
    from backend.ai import pipeline as pl

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": (
                '{"plans": [{"name": "LLM方案", "summary": "由LLM生成", '
                '"daily": [{"day": 1, "title": "t", '
                '"items": [{"spot": "故宫博物院", "why": "w"}]}], "tips": []}]}'
            )}}]}

    def fake_post(url, **kwargs):
        return FakeResp()

    monkeypatch.setattr("backend.ai.llm.requests.post", fake_post)
    old_key = pl._llm.api_key
    pl._llm.api_key = "sk-fake"
    try:
        cities = client.get("/api/cities").json()
        bj = next(c for c in cities if c["name"] == "北京")
        spots = client.get(f"/api/cities/{bj['id']}/spots").json()
        body = {"city_id": bj["id"], "days": 2, "style": "轻松",
                "spot_ids": [s["id"] for s in spots[:2]]}
        r = client.post("/api/plans/generate", json=body)
    finally:
        pl._llm.api_key = old_key

    assert r.status_code == 200
    plans = r.json()
    assert len(plans) == 3                        # 不足时自动补齐到 3 套
    assert plans[0]["plan"]["name"] == "LLM方案"   # LLM 方案排最前
    assert plans[0]["plan"]["source"] == "DeepSeek"
    filled = [p for p in plans if p["plan"].get("source", "").startswith("启发式补齐")]
    assert len(filled) == 2                       # 2 套为 mock 补齐并如实标注


def test_roadtrip_multi_city():
    """自驾模式:跨城市路线,含路段距离/时间估算"""
    cities = client.get("/api/cities").json()
    bj = next(c for c in cities if c["name"] == "北京")
    cd = next(c for c in cities if c["name"] == "承德")
    bj_spots = client.get(f"/api/cities/{bj['id']}/spots").json()
    cd_spots = client.get(f"/api/cities/{cd['id']}/spots").json()
    mutianyu = next(s for s in bj_spots if s["name"] == "慕田峪长城")
    gongwang = next(s for s in bj_spots if s["name"] == "恭王府")
    bishu = next(s for s in cd_spots if s["name"] == "承德避暑山庄及周围寺庙")

    body = {"spot_ids": [gongwang["id"], mutianyu["id"], bishu["id"]],
            "days": 3, "style": "轻松"}
    r = client.post("/api/plans/roadtrip", json=body)
    assert r.status_code == 200
    plans = r.json()
    assert len(plans) == 3
    p0 = plans[0]["plan"]
    assert "route" in p0 and len(p0["route"]) == 3   # 2 段 + 1 段闭环返回
    legs = p0["route"]
    assert all(l["km"] > 0 and l["hours"] > 0 for l in legs)
    assert all(l["from_lng"] is not None and l["to_lng"] is not None for l in legs)  # 地图渲染用坐标
    assert legs[-1]["closing"] is True                       # 环线闭环段
    assert legs[-1]["to"] == legs[0]["from"]                 # 终点返回起点
    assert "承德" in legs[1]["to_city"] or "承德" in legs[0]["to_city"]


def test_roadtrip_no_close_loop():
    """close_loop=False 时不生成闭环段"""
    cities = client.get("/api/cities").json()
    bj = next(c for c in cities if c["name"] == "北京")
    cd = next(c for c in cities if c["name"] == "承德")
    bj_spots = client.get(f"/api/cities/{bj['id']}/spots").json()
    cd_spots = client.get(f"/api/cities/{cd['id']}/spots").json()
    ids = [next(s for s in bj_spots if s["name"] == "恭王府")["id"],
           next(s for s in cd_spots if s["name"] == "承德避暑山庄及周围寺庙")["id"]]
    r = client.post("/api/plans/roadtrip", json={"spot_ids": ids, "days": 2, "close_loop": False})
    assert r.status_code == 200
    legs = r.json()[0]["plan"]["route"]
    assert len(legs) == 1                     # 2 个点 → 1 段,不闭合
    assert legs[0].get("closing") is None


def test_gannan_loop_seeded():
    """甘南环线非评级自然景区已入库"""
    from backend.app.db import get_conn

    conn = get_conn()
    try:
        n = conn.execute(
            "SELECT COUNT(*) c FROM spots WHERE name IN "
            "('扎尕那','拉卜楞寺','郎木寺','黄河九曲第一湾','桑科草原')"
        ).fetchone()["c"]
        grade_null = conn.execute(
            "SELECT COUNT(*) c FROM spots WHERE name='扎尕那' AND grade IS NULL"
        ).fetchone()["c"]
    finally:
        conn.close()
    assert n == 5
    assert grade_null == 1   # 非评级


def test_roadtrip_gannan():
    """甘南环线自驾:跨县路线,里程估算合理"""
    cities = client.get("/api/cities").json()
    spots_ids = []
    for cname, sname in (("夏河", "拉卜楞寺"), ("迭部", "扎尕那"), ("若尔盖", "黄河九曲第一湾")):
        c = next(x for x in cities if x["name"] == cname)
        ss = client.get(f"/api/cities/{c['id']}/spots").json()
        spots_ids.append(next(s for s in ss if s["name"] == sname)["id"])
    r = client.post("/api/plans/roadtrip", json={"spot_ids": spots_ids, "days": 4, "style": "轻松"})
    assert r.status_code == 200
    plans = r.json()
    assert len(plans) == 3
    km0 = plans[0]["plan"]["route"][0]["km"]
    assert km0 > 50   # 拉卜楞寺→扎尕那 实际约 130km+,估算不应为 0


def test_loops_api():
    """环线 API:5 条环线,含点位与元信息"""
    r = client.get("/api/loops")
    assert r.status_code == 200
    loops = r.json()
    assert len(loops) >= 5
    gannan = next(l for l in loops if l["name"] == "甘南环线")
    assert len(gannan["spots"]) >= 15
    assert any(s["name"] == "扎尕那" for s in gannan["spots"])
    assert gannan["days"] != ""
    assert gannan["desc"] != ""
    # 环线点位带坐标与分类(供地图渲染)
    zh = next(s for s in gannan["spots"] if s["name"] == "扎尕那")
    assert zh["lng"] is not None and zh["lat"] is not None
    assert zh["category"] in ("自然", "人文", "综合")


def test_loops_seeded_in_db():
    """多环线点位已入库且带环线标签"""
    from backend.app.db import get_conn

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT tags FROM spots WHERE tags LIKE '%环线:%'"
        ).fetchall()
    finally:
        conn.close()
    tags = [t for r in rows for t in _loads(r["tags"])]
    loops = {t.split(":", 1)[1] for t in tags if t.startswith("环线:")}
    assert len(rows) >= 45                 # 5 条环线共 49 个点位
    assert loops >= {"甘南环线", "川西环线", "青甘环线", "滇西北环线", "北疆环线"}


def test_province_spots_endpoint():
    """省级景点散点:含坐标与分类"""
    r = client.get("/api/province/%E6%B2%B3%E5%8C%97%E7%9C%81/spots")  # 河北省
    assert r.status_code == 200
    spots = r.json()
    assert len(spots) >= 5
    for s in spots:
        assert s["lng"] is not None and s["lat"] is not None
        assert s["category"] in ("自然", "人文", "综合")
    assert any(s["category"] == "人文" for s in spots)


def test_4a_seeded():
    """4A 景区首批入库,新增城市可点"""
    from backend.app.db import get_conn

    conn = get_conn()
    try:
        n4a = conn.execute("SELECT COUNT(*) c FROM spots WHERE grade='4A'").fetchone()["c"]
        taiyuan = conn.execute("SELECT COUNT(*) c FROM cities WHERE name='太原'").fetchone()["c"]
        zhouzhuang = conn.execute(
            "SELECT COUNT(*) c FROM spots WHERE name='周庄古镇' AND grade='4A'"
        ).fetchone()["c"]
    finally:
        conn.close()
    assert n4a >= 60
    assert taiyuan == 1
    assert zhouzhuang == 1


def test_city_match_prefix_logic():
    """多边形城市名匹配(模拟前端 matchCityByPolygon):自治州/后缀剥离+前缀匹配"""
    from backend.app.db import get_conn

    conn = get_conn()
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM cities").fetchall()}
    finally:
        conn.close()

    def match(poly):
        n = poly.rstrip("市地区自治州盟")
        if n in names:
            return n
        for name in names:
            if poly.startswith(name):
                return name
        return None

    assert match("承德市") == "承德"
    assert match("湘西土家族苗族自治州") == "湘西"
    assert match("阿坝藏族羌族自治州") == "阿坝"
    assert match("张家界市") == "张家界"
    assert match("甘孜藏族自治州") == "甘孜"
    assert match("恩施土家族苗族自治州") == "恩施"
    assert match("完全没收录的地方") is None


def test_prices_seeded():
    """门票参考价已入库,高价景点可识别"""
    from backend.app.db import get_conn

    conn = get_conn()
    try:
        np = conn.execute("SELECT COUNT(*) c FROM spots WHERE price IS NOT NULL").fetchone()["c"]
        jiuqu = conn.execute(
            "SELECT price FROM spots WHERE name='黄河九曲第一湾'"
        ).fetchone()["price"]
        disney = conn.execute(
            "SELECT price FROM spots WHERE name='上海迪士尼乐园'"
        ).fetchone()["price"]
    finally:
        conn.close()
    assert np >= 150
    assert jiuqu == 100
    assert disney == 475


def test_alternatives_seeded():
    """高门票景点平替已入库(含自动创建的平替景点)"""
    from backend.app.db import get_conn

    conn = get_conn()
    try:
        n = conn.execute("SELECT COUNT(*) c FROM spot_alternatives").fetchone()["c"]
        huanle = conn.execute(
            "SELECT COUNT(*) c FROM spots WHERE name='上海欢乐谷'"
        ).fetchone()["c"]
    finally:
        conn.close()
    assert n >= 20
    assert huanle == 1


def test_jiuqu_alternatives():
    """黄河九曲第一湾:双平替(杂威冻列用户实测 + 索克藏寺)"""
    cities = client.get("/api/cities").json()
    reg = next(c for c in cities if c["name"] == "若尔盖")
    spots = client.get(f"/api/cities/{reg['id']}/spots").json()
    jiuqu = next(s for s in spots if s["name"] == "黄河九曲第一湾")
    d = client.get(f"/api/spots/{jiuqu['id']}").json()
    names = [a["alt_name"] for a in d["alternatives"]]
    assert "杂威冻列(洛华湾观景)" in names
    assert "索克藏寺(免费观景)" in names
    zl = next(a for a in d["alternatives"] if a["alt_name"].startswith("杂威冻列"))
    assert zl["downsides"]   # 缺点如实标注


def test_spot_alternatives_api():
    """迪士尼详情含平替(上海欢乐谷+缺点);故宫无平替为空列表"""
    cities = client.get("/api/cities").json()
    sh = next(c for c in cities if c["name"] == "上海")
    spots = client.get(f"/api/cities/{sh['id']}/spots").json()
    disney = next(s for s in spots if s["name"] == "上海迪士尼乐园")
    d = client.get(f"/api/spots/{disney['id']}").json()
    assert len(d["alternatives"]) >= 1
    alt = d["alternatives"][0]
    assert alt["alt_name"] == "上海欢乐谷"
    assert alt["price_note"]
    assert len(alt["downsides"]) >= 2

    bj = next(c for c in cities if c["name"] == "北京")
    bj_spots = client.get(f"/api/cities/{bj['id']}/spots").json()
    gugong = next(s for s in bj_spots if s["name"] == "故宫博物院")
    d2 = client.get(f"/api/spots/{gugong['id']}").json()
    assert d2["alternatives"] == []


def test_stays_seeded():
    """住宿知识库已入库(区域级)"""
    from backend.app.db import get_conn

    conn = get_conn()
    try:
        n = conn.execute("SELECT COUNT(*) c FROM stays").fetchone()["c"]
        xiahe = conn.execute(
            "SELECT COUNT(*) c FROM stays WHERE city='夏河'"
        ).fetchone()["c"]
    finally:
        conn.close()
    assert n >= 35
    assert xiahe >= 2


def test_stays_no_ad_keywords():
    """住宿数据防暗广:不含商家名/引流词"""
    from backend.app.db import get_conn

    conn = get_conn()
    try:
        rows = conn.execute("SELECT note FROM stays").fetchall()
    finally:
        conn.close()
    bad = ["微信", "vx", "链接", "团购", "私信", "找我", "订房热线"]
    for r in rows:
        note = r[0] or ""
        assert not any(k in note for k in bad), f"疑似暗广: {note}"


def test_roadtrip_has_stays():
    """自驾方案每日含住宿推荐(区域+价格+距终点里程)"""
    cities = client.get("/api/cities").json()
    spots_ids = []
    for cname, sname in (("夏河", "拉卜楞寺"), ("迭部", "扎尕那"), ("若尔盖", "黄河九曲第一湾")):
        c = next(x for x in cities if x["name"] == cname)
        ss = client.get(f"/api/cities/{c['id']}/spots").json()
        spots_ids.append(next(s for s in ss if s["name"] == sname)["id"])
    r = client.post("/api/plans/roadtrip", json={"spot_ids": spots_ids, "days": 3, "style": "轻松"})
    assert r.status_code == 200
    p0 = r.json()[0]["plan"]
    for day in p0["daily"]:
        stay = day.get("stay")
        assert stay and stay["town"] and stay["price"]
        assert stay["km_from_last"] >= 0
        # 自驾/环线方案每日也有美食推荐(吃什么)
        assert day.get("foods") and day["foods"]["dishes"], f"第{day['day']}天缺美食推荐"


def test_roadtrip_gannan_has_foods():
    """甘南环线自驾方案含当地美食(拉卜楞寺→扎尕那等沿线)"""
    cities = client.get("/api/cities").json()
    spots_ids = []
    for cname, sname in (("夏河", "拉卜楞寺"), ("迭部", "扎尕那"), ("若尔盖", "黄河九曲第一湾")):
        c = next(x for x in cities if x["name"] == cname)
        ss = client.get(f"/api/cities/{c['id']}/spots").json()
        spots_ids.append(next(s for s in ss if s["name"] == sname)["id"])
    r = client.post("/api/plans/roadtrip", json={"spot_ids": spots_ids, "days": 3, "style": "轻松"})
    assert r.status_code == 200
    all_foods = [d["name"] for day in r.json()[0]["plan"]["daily"] for d in day.get("foods", {}).get("dishes", [])]
    assert any(k in " ".join(all_foods) for k in ("藏包", "酸奶", "藏香猪", "糌粑", "青稞"))


def test_single_city_plans_have_stays():
    """单城市方案每日含住宿推荐"""
    cities = client.get("/api/cities").json()
    bj = next(c for c in cities if c["name"] == "北京")
    spots = client.get(f"/api/cities/{bj['id']}/spots").json()
    body = {"city_id": bj["id"], "days": 2, "style": "轻松",
            "spot_ids": [s["id"] for s in spots[:4]]}
    plans = client.post("/api/plans/generate", json=body).json()
    for day in plans[0]["plan"]["daily"]:
        assert day.get("stay") and day["stay"]["town"]


def test_roadtrip_start_city():
    """出发地锚定:路线从出发地出发,闭环返回出发地"""
    cities = client.get("/api/cities").json()
    spots_ids = []
    for cname, sname in (("夏河", "拉卜楞寺"), ("迭部", "扎尕那"), ("若尔盖", "黄河九曲第一湾")):
        c = next(x for x in cities if x["name"] == cname)
        ss = client.get(f"/api/cities/{c['id']}/spots").json()
        spots_ids.append(next(s for s in ss if s["name"] == sname)["id"])
    r = client.post("/api/plans/roadtrip", json={
        "spot_ids": spots_ids, "days": 4, "style": "轻松",
        "close_loop": True, "start_city": "兰州",
    })
    assert r.status_code == 200
    legs = r.json()[0]["plan"]["route"]
    assert legs[0]["from"].startswith("出发地·兰州")
    assert legs[-1]["to"].startswith("出发地·兰州")   # 闭环回出发地
    assert legs[-1]["closing"] is True
    # 每日第一项包含出发地
    day1 = r.json()[0]["plan"]["daily"][0]
    assert day1["items"][0]["spot"].startswith("出发地·兰州")


def test_alternatives_map_coords():
    """平替与主景点均带坐标(供地图对比)"""
    cities = client.get("/api/cities").json()
    sh = next(c for c in cities if c["name"] == "上海")
    spots = client.get(f"/api/cities/{sh['id']}/spots").json()
    disney = next(s for s in spots if s["name"] == "上海迪士尼乐园")
    d = client.get(f"/api/spots/{disney['id']}").json()
    assert d["lng"] is not None and d["lat"] is not None
    for a in d["alternatives"]:
        assert a["alt_lng"] is not None and a["alt_lat"] is not None


def test_foods_seeded_and_api():
    """城市美食:西安必吃小吃+美食街,防暗广数据卫生"""
    from backend.app.db import get_conn

    conn = get_conn()
    try:
        n = conn.execute("SELECT COUNT(*) c FROM city_foods").fetchone()["c"]
    finally:
        conn.close()
    assert n >= 90

    cities = client.get("/api/cities").json()
    xa = next(c for c in cities if c["name"] == "西安")
    r = client.get(f"/api/cities/{xa['id']}/foods")
    assert r.status_code == 200
    data = r.json()
    names = [d["name"] for d in data["dishes"]]
    assert "肉夹馍(腊汁肉)" in names and "羊肉泡馍" in names
    streets = [s["name"] for s in data["streets"]]
    assert "回民街" in streets and "洒金桥 / 大皮院" in streets
    for d in data["dishes"] + data["streets"]:
        assert not any(k in (d.get("note", "") + d["name"]) for k in ("微信", "链接", "团购", "私信"))


def test_museums_seeded():
    """著名博物馆已入库(城市模式项目)"""
    from backend.app.db import get_conn

    conn = get_conn()
    try:
        n = conn.execute("SELECT COUNT(*) c FROM spots WHERE tags LIKE '%博物馆%'").fetchone()["c"]
        gm = conn.execute(
            "SELECT COUNT(*) c FROM spots WHERE name='中国国家博物馆'"
        ).fetchone()["c"]
    finally:
        conn.close()
    assert n >= 20
    assert gm == 1


def test_citytour_multi_city():
    """城市模式:多城串联,每日一城含住宿+美食,城间有路线与交通推荐"""
    cities = client.get("/api/cities").json()
    ids = []
    for cname, sname in (("西安", "陕西历史博物馆"), ("西安", "秦始皇兵马俑博物馆"),
                         ("兰州", "甘肃省博物馆")):
        c = next(x for x in cities if x["name"] == cname)
        ss = client.get(f"/api/cities/{c['id']}/spots").json()
        ids.append(next(s for s in ss if s["name"] == sname)["id"])
    r = client.post("/api/plans/citytour", json={
        "spot_ids": ids, "days": 3, "style": "轻松", "start_city": "兰州",
        "city_days": {"西安": 2, "兰州": 1},
    })
    assert r.status_code == 200
    plans = r.json()
    assert len(plans) == 3
    p0 = plans[0]["plan"]
    # 出发地=目的地城市(兰州):以兰州为起点
    assert p0["route"][0]["from"] == "兰州"
    titles = " ".join(day["title"] for day in p0["daily"])
    assert "西安" in titles and "兰州" in titles
    # 每城天数可调:西安 2 天;多天时景点分摊到每天(两个博物馆各占一天,而非全塞第 1 天)
    xa_days = [d for d in p0["daily"] if "西安" in d["title"]]
    assert len(xa_days) == 2
    xa_items = [it["spot"] for d in xa_days for it in d["items"]]
    assert "陕西历史博物馆" in xa_items and "秦始皇兵马俑博物馆" in xa_items
    xa_day = xa_days[0]
    assert xa_day["stay"]["town"]                          # 住宿
    assert xa_day["foods"]["dishes"]                       # 必吃
    # 交通感知(兰州→西安约 3h):若到达日判定在途,则上午项目应改期并提示,而非硬排
    if any("在途" in it["why"] for it in xa_day["items"]) or "在途" in (xa_day.get("note") or ""):
        assert not any(it.get("time") in ("清晨", "上午") for it in xa_day["items"])
    else:
        assert any("博物馆" in it["why"] for it in xa_day["items"])
    # 城间交通推荐
    assert p0["route"][0]["transport"]["rail"]
    assert p0["route"][0]["transport"]["recommend"]


def test_schedule_slot_rules():
    """时段规则:雪山大景区→全天,小吃/美食街→晚上,博物馆→上午"""
    from backend.app.schedule import recommend_time

    assert recommend_time("玉龙雪山", ["雪山", "自然"])[0] == "全天"
    assert recommend_time("梅里雪山", ["雪山"])[0] == "全天"
    assert recommend_time("回民街", ["美食街", "小吃"])[0] == "晚上"
    assert recommend_time("尚水美食街", ["美食街"])[0] == "晚上"
    assert recommend_time("陕西历史博物馆", ["博物馆"])[0] == "上午"
    assert recommend_time("大理古城", ["古城"])[0] in ("下午", "晚上")


def test_citytour_travel_aware_arrival():
    """交通感知:西安出发→桂林(约4.9h在途),桂林第 1 天提示在途且不排上午"""
    cities = client.get("/api/cities").json()
    ids = []
    for cname, sname in (("西安", "陕西历史博物馆"), ("桂林", "漓江风景名胜区")):
        c = next(x for x in cities if x["name"] == cname)
        ss = client.get(f"/api/cities/{c['id']}/spots").json()
        ids.append(next(s for s in ss if s["name"] == sname)["id"])
    r = client.post("/api/plans/citytour", json={
        "spot_ids": ids, "days": 2, "style": "轻松",
        "city_days": {"西安": 1, "桂林": 1}, "start_city": "西安"})
    assert r.status_code == 200
    p0 = r.json()[0]["plan"]
    gl_day = next(d for d in p0["daily"] if "桂林" in d["title"])
    assert "在途" in gl_day.get("note", "")
    assert not any(it.get("time") in ("清晨", "上午") for it in gl_day["items"])


def test_food_streets_have_coords():
    """美食街/聚集区带坐标(供"城市美食地图"标注)"""
    cities = client.get("/api/cities").json()
    xa = next(c for c in cities if c["name"] == "西安")
    r = client.get(f"/api/cities/{xa['id']}/foods")
    data = r.json()
    huimin = next(s for s in data["streets"] if s["name"] == "回民街")
    assert huimin["lng"] is not None and huimin["lat"] is not None
    # 多数美食街有坐标
    n_with = sum(1 for s in data["streets"] if s["lng"] is not None)
    assert n_with >= len(data["streets"]) - 1


def test_food_streets_are_spots():
    """美食街升级为正式景点:上图/加购物车/有口碑卡"""
    cities = client.get("/api/cities").json()
    xa = next(c for c in cities if c["name"] == "西安")
    spots = client.get(f"/api/cities/{xa['id']}/spots").json()
    huimin = next((s for s in spots if s["name"] == "回民街"), None)
    assert huimin is not None                        # 已上图(景区列表可见)
    assert "美食街" in huimin["tags"]                 # 标签
    # 地图端点带坐标
    fs = client.get("/api/province/%E9%99%95%E8%A5%BF%E7%9C%81/spots").json()
    hm_map = next(s for s in fs if s["name"] == "回民街")
    assert hm_map["lng"] is not None and hm_map["lat"] is not None
    d = client.get(f"/api/spots/{huimin['id']}").json()
    assert d["summary"] is not None and d["summary"]["note_count"] >= 1   # 有口碑卡(评价界面)
    # 可加购物车
    assert client.post(f"/api/cart/{huimin['id']}").status_code == 201
    cart = client.get("/api/cart").json()
    assert any(it["spot_id"] == huimin["id"] for it in cart)
    client.delete(f"/api/cart/{huimin['id']}")


def test_landmarks_as_spots():
    """公园/商圈/商业街与景点同机制:上图/标签/口碑/加购物车"""
    cities = client.get("/api/cities").json()
    bj = next(c for c in cities if c["name"] == "北京")
    spots = client.get(f"/api/cities/{bj['id']}/spots").json()
    wf = next((s for s in spots if s["name"] == "王府井商圈"), None)
    assert wf is not None and "商圈" in wf["tags"]
    # 商圈分类为人文
    fs = client.get("/api/province/%E5%8C%97%E4%BA%AC%E5%B8%82/spots").json()
    wf_map = next(s for s in fs if s["name"] == "王府井商圈")
    assert wf_map["category"] == "人文"
    assert wf_map["lng"] is not None

    cd = next(c for c in cities if c["name"] == "成都")
    cd_spots = client.get(f"/api/cities/{cd['id']}/spots").json()
    rm = next((s for s in cd_spots if s["name"] == "人民公园"), None)
    assert rm is not None and "公园" in rm["tags"]
    d = client.get(f"/api/spots/{rm['id']}").json()
    assert d["summary"] is not None                 # 有口碑卡(评价界面)
    assert client.post(f"/api/cart/{rm['id']}").status_code == 201
    client.delete(f"/api/cart/{rm['id']}")

    # 与美食街同名者标签合并(中央大街 = 美食街 + 商圈)
    hr = next(c for c in cities if c["name"] == "哈尔滨")
    hr_spots = client.get(f"/api/cities/{hr['id']}/spots").json()
    zydj = next(s for s in hr_spots if s["name"] == "中央大街")
    assert "美食街" in zydj["tags"] and "商圈" in zydj["tags"]

    # 商圈类型/档次标注(含商场类)
    xa = next(c for c in cities if c["name"] == "西安")
    xa_spots = client.get(f"/api/cities/{xa['id']}/spots").json()
    xiaozhai = next(s for s in xa_spots if s["name"] == "西安小寨商圈")
    assert xiaozhai["commercial"]["type"] == "混合"
    assert xiaozhai["commercial"]["tier"] == "中低端"
    wf = next(s for s in spots if s["name"] == "王府井商圈")
    assert wf["commercial"]["type"] == "商业" and wf["commercial"]["tier"] == "中高端"
    skp = next(s for s in spots if s["name"] == "北京SKP")
    assert skp["commercial"]["tier"] == "高端"


def test_citytour_time_scheduling():
    """城市模式:每日景点带推荐时段并按时段排序;无闭环"""
    cities = client.get("/api/cities").json()
    ids = []
    for cname, sname in (("西安", "陕西历史博物馆"), ("西安", "回民街")):
        c = next(x for x in cities if x["name"] == cname)
        ss = client.get(f"/api/cities/{c['id']}/spots").json()
        ids.append(next(s for s in ss if s["name"] == sname)["id"])
    r = client.post("/api/plans/citytour", json={"spot_ids": ids, "days": 2, "style": "轻松"})
    assert r.status_code == 200
    p0 = r.json()[0]["plan"]
    # 无闭环(城市模式默认不回程)
    assert not any(l.get("closing") for l in p0["route"])
    # 2 个景点分摊到 2 天(顺序与库内 id 相关,跨天汇总断言)
    assert len(p0["daily"]) == 2
    t_map = {it["spot"]: it["time"] for d in p0["daily"] for it in d["items"]}
    assert t_map["陕西历史博物馆"] == "上午"
    assert t_map["回民街"] == "晚上"
    day1_times = [it.get("time") for it in p0["daily"][0]["items"] if it.get("time")]
    assert all(t in ("清晨", "上午", "下午", "傍晚", "晚上", "全天") for t in day1_times)
    # 每天内按时段排序(休整日/备选项无时段,跳过)
    order = ["清晨", "上午", "下午", "傍晚", "晚上", "全天"]
    for d in p0["daily"]:
        idx = [order.index(it.get("time")) for it in d["items"] if it.get("time")]
        assert idx == sorted(idx)   # 已按时段排序
    assert p0["daily"][0]["items"][0]["time_reason"]   # 有理由


def test_citytour_stay_by_anchor():
    """城市模式住宿:按玩的地点选区域(锚点→最近住宿+商圈描述+地铁提示)"""
    cities = client.get("/api/cities").json()
    ids = []
    for cname, sname in (("西安", "陕西历史博物馆"), ("西安", "西安小寨商圈"), ("西安", "回民街")):
        c = next(x for x in cities if x["name"] == cname)
        ss = client.get(f"/api/cities/{c['id']}/spots").json()
        ids.append(next(s for s in ss if s["name"] == sname)["id"])
    r = client.post("/api/plans/citytour", json={"spot_ids": ids, "days": 2, "style": "轻松"})
    assert r.status_code == 200
    stay = r.json()[0]["plan"]["daily"][0]["stay"]
    assert stay["area_label"]           # 区域描述(如"钟楼商圈附近(地铁2号线)")
    assert "附近" in stay["area_label"] or "地铁" in stay["area_label"]
    assert stay["fit_note"] and "km" in stay["fit_note"]   # 距离合理性
    assert stay["town"] and stay["price"]


def test_index_page():
    r = client.get("/")
    assert r.status_code == 200
    assert "旅行智规" in r.text
