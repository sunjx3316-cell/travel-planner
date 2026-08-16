# -*- coding: utf-8 -*-
"""前端真实浏览器 e2e 检查(需要 chromium 已安装)。

用法: python scripts/e2e_check.py
说明: 浏览器默认装在工作区 .browsers 目录(沙箱限制),
      脚本会自动设置 PLAYWRIGHT_BROWSERS_PATH。
"""
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # 控制台 GBK 兼容

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".browsers"))

from playwright.sync_api import sync_playwright  # noqa: E402

BASE = "http://127.0.0.1:8000"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console: {m.text}") if m.type == "error" else None)

        page.goto(BASE, wait_until="networkidle", timeout=60000)
        # 清空清单,保证可复现
        page.evaluate("async () => { await fetch('/api/cart', {method:'DELETE'}); }")
        page.wait_for_timeout(300)
        print("1. title:", page.title())
        print("2. 地图 canvas:", page.locator("#map canvas").count())
        print("3. 模式徽标:", page.locator("#mode-badge").inner_text())
        print("4. 返回按钮初始隐藏:", not page.locator("#map-back").is_visible())

        # 全国 → 省份地图(景点散点) → 分类筛选 → 返回
        page.evaluate("renderProvinceMap('河北省')")
        page.wait_for_timeout(1500)
        print("4b. 省份地图 canvas:", page.locator("#map canvas").count())
        print("4c. 返回按钮可见:", page.locator("#map-back").is_visible())
        print("4e. 筛选条可见:", page.locator("#map-filters").is_visible())
        page.locator(".filter-chip", has_text="自然").click()
        page.wait_for_timeout(600)
        print("4f. 自然筛选激活:", page.locator(".filter-chip.active").inner_text())
        page.evaluate("setSpotFilter('全部')")
        page.wait_for_timeout(400)

        # 环线地图视图
        page.evaluate("renderLoopMap('甘南环线')")
        page.wait_for_timeout(1500)
        print("4g. 环线地图 canvas:", page.locator("#map canvas").count())
        print("4h. 环线地图提示:", page.locator("#map-hint").inner_text()[:40])

        # 路线地图渲染(API 生成真实路线并画图)
        rname = page.evaluate("""async () => {
            const loops = await (await fetch('/api/loops')).json();
            const lp = loops.find(l => l.name === '甘南环线');
            const ids = lp.spots.slice(0, 6).map(s => s.id);
            const r = await fetch('/api/plans/roadtrip', {method:'POST',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify({spot_ids: ids, days: 5, style: '轻松'})});
            const plans = await r.json();
            drawRouteOnMap(plans[0].plan);
            return plans[0].plan.name;
        }""")
        page.wait_for_timeout(1200)
        print("4i. 路线地图渲染:", rname, "| canvas:", page.locator("#map canvas").count())

        page.locator("#map-back").click()
        page.wait_for_timeout(800)
        print("4d. 返回后按钮隐藏:", not page.locator("#map-back").is_visible())

        print("5. 省市卡片数:", page.locator(".city-card").count())

        # 省市 → 城市 → 景区(两级导航)
        page.locator(".city-card", has_text="北京市").click()
        page.wait_for_timeout(500)
        page.locator(".city-card", has_text="北京").first.click()
        page.wait_for_timeout(600)
        print("5. 北京景区行数:", page.locator(".spot-row").count())

        page.locator(".spot-row", has_text="故宫博物院").locator("button", has_text="详情").click()
        page.wait_for_timeout(600)
        print("6. 详情标题:", page.locator(".detail-head h2").inner_text())
        print("7. 避雷共识框:", page.locator(".panel-box.avoid").count())
        print("8. 信任度:", page.locator(".trust-badge").inner_text())

        page.locator("button", has_text="+ 加入想去清单").click()
        page.wait_for_timeout(500)
        print("9. 清单计数:", page.locator("#cart-count").inner_text())

        # 城市 tab 规划工作台:已选城市 chip → 地图定位;获取推荐 → 按推荐生成
        page.evaluate("renderCities(null)")
        page.locator(".tabs button", has_text="城市").click()
        page.wait_for_timeout(400)
        print("14. 规划工作台:", page.locator(".plan-box").count())
        chip = page.locator(".city-chip").first
        print("15. 已选城市 chip:", chip.count())
        if chip.count():
            chip.click()
            page.wait_for_timeout(1800)
            print("15b. focusCity 省份地图 canvas:", page.locator("#map canvas").count())
            print("15c. spots tab 激活:", page.locator("#tab-spots").is_visible())
        page.evaluate("renderCities(null)")
        page.locator(".tabs button", has_text="城市").click()
        page.wait_for_timeout(400)
        page.locator("#plan-start").fill("西安")   # 出发地不在清单 → 取最近城市
        page.locator("button", has_text="获取推荐").click()
        page.wait_for_timeout(1500)
        rec = page.locator(".rec-box")
        print("16. 推荐框:", rec.count())
        if rec.count():
            txt = rec.inner_text()
            print("17. 推荐内容:", " | ".join(l for l in txt.splitlines() if l.strip())[:120])
            assert "起始城市" in txt and "每城天数" in txt
            page.locator(".rec-box button", has_text="按推荐生成").click()
            page.wait_for_timeout(20000)   # DeepSeek 需处理完整每日排期,约 7-15s
            print("18. 推荐生成方案卡:", page.locator(".plan-card").count())

        page.locator(".tabs button", has_text="清单").click()
        page.wait_for_timeout(300)
        gen = page.locator("#tab-cart button", has_text="生成城市之旅")
        print("10. 生成城市之旅按钮:", gen.count())
        if gen.count():
            gen.click()
            page.wait_for_timeout(20000)
            print("11. 方案卡片数:", page.locator(".plan-card").count())
            print("12. 方案名:", page.locator(".plan-card h4").first.inner_text())

        print("13. 页面错误:", errors if errors else "无")
        browser.close()


if __name__ == "__main__":
    main()
