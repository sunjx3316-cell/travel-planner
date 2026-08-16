# -*- coding: utf-8 -*-
"""端到端冒烟测试:验证核心 API 链路。用法: python scripts/smoke_test.py [base_url]"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # 控制台 GBK 兼容

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASS, FAIL = 0, 0


def req(method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=60) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {extra}")


print("== 1. 状态 ==")
st, status = req("GET", "/api/status")
check("GET /api/status", st == 200 and "llm_available" in status, status)

print("== 2. 城市 ==")
st, cities = req("GET", "/api/cities")
check("GET /api/cities", st == 200 and len(cities) >= 100, f"count={len(cities)}")
check("城市含景区数", all("spot_count" in c for c in cities))
bj = next(c for c in cities if c["name"] == "北京")
print(f"    北京 spot_count = {bj['spot_count']}")

print("== 3. 北京景区 ==")
st, spots = req("GET", f"/api/cities/{bj['id']}/spots")
check("GET /api/cities/{id}/spots", st == 200 and len(spots) >= 10, f"count={len(spots)}")
check("含 5A 景区", any(s.get("grade") == "5A" for s in spots))
gugong = next(s for s in spots if s["name"] == "故宫博物院")

print("== 4. AI 分析(故宫, mock 管线) ==")
st, card = req("POST", f"/api/spots/{gugong['id']}/summarize")
check("POST /api/spots/{id}/summarize", st == 200, status)
check("有亮点", len(card.get("highlights", [])) > 0)
check("有避雷点", len(card.get("avoid_points", [])) > 0)
check("共识差评 >=1", len(card.get("consensus_issues", [])) >= 1, card.get("consensus_issues"))
check("信任度 0-100", 0 <= card.get("trust_score", -1) <= 100, card.get("trust_score"))
print(f"    共识差评: {card.get('consensus_issues')}")
print(f"    暗广占比: {card.get('ad_ratio')} 信号: {card.get('ad_signals')}")
print(f"    信任度: {card.get('trust_score')}  来源: {card.get('source')}")

print("== 5. 景区详情(含口碑卡) ==")
st, detail = req("GET", f"/api/spots/{gugong['id']}")
check("GET /api/spots/{id}", st == 200 and detail["summary"] is not None)
check("含示例笔记", len(detail.get("notes", [])) == 4, f"notes={len(detail.get('notes', []))}")

print("== 6. 购物车 ==")
req("POST", f"/api/cart/{gugong['id']}")
req("POST", "/api/cart/17")  # 西湖(杭州)
st, cart = req("GET", "/api/cart")
check("加入清单", st == 200 and len(cart) == 2, f"count={len(cart)}")
req("DELETE", f"/api/cart/{gugong['id']}")
st, cart2 = req("GET", "/api/cart")
check("移除", len(cart2) == 1)

print("== 7. 行程方案(mock 规划器) ==")
st, plans = req("POST", "/api/plans/generate", {
    "city_id": bj["id"], "days": 2, "style": "轻松",
    "spot_ids": [s["id"] for s in spots[:4]],
})
check("POST /api/plans/generate", st == 200 and len(plans) == 3, f"plans={len(plans)}")
p0 = plans[0]["plan"]
check("方案含每日行程", "daily" in p0 and len(p0["daily"]) > 0)
print(f"    方案1: {p0['name']} | {p0['summary']}")
print(f"    第1天: {[i['spot'] for i in p0['daily'][0]['items']]}")

print("== 8. 前端页面 ==")
with urllib.request.urlopen(BASE + "/", timeout=30) as resp:
    html = resp.read().decode("utf-8")
check("GET / 返回首页", "旅行智规" in html and "echarts.min.js" in html)

print(f"\n结果: {PASS} 通过, {FAIL} 失败")
sys.exit(1 if FAIL else 0)
