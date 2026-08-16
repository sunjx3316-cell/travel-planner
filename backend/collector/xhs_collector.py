# -*- coding: utf-8 -*-
"""小红书采集器(完整实现,待账号登录后激活)。

设计原则(与用户确认):
1. 合规与安全:低频小规模(间隔 5-10s,单账号每日 <200 次);仅个人学习演示;
   不上线运营、不公开部署、不展示原始全文(UI 展示 AI 总结)。
2. 登录:反爬硬门槛是真实账号 cookie —— login_wizard() 弹出浏览器,
   由用户手动登录一次,脚本保存 cookie 供复用;绝不自研绕过登录验证。
3. 流程:搜索页("城市+景区+攻略/避雷") -> 笔记详情页(标题/正文/图片 CDN) -> 入库。

注意:小红书前端选择器可能随改版变化,采集前建议用 login_wizard 登录后
先在浏览器里核对一遍;selectors 见下方常量,集中维护。

用法(先登录,再采集):
    python scripts/collect_xhs.py --login        # 弹浏览器,手动登录,保存 cookie
    python scripts/collect_xhs.py                # 为所有缺笔记的景区采集
    python scripts/collect_xhs.py 故宫博物院     # 指定景区名采集
"""
import json
import os
import re
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
COOKIE_PATH = DATA_DIR / "xhs_cookies.json"
IMG_DIR = DATA_DIR / "images"

# 浏览器已下载到工作区 .browsers(沙箱环境),自动指向它,避免用户侧重复下载
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(PROJECT_ROOT / ".browsers"))

# 采集纪律
REQUEST_INTERVAL = 8      # 秒
DAILY_LIMIT = 200         # 单账号每日请求上限
LIMIT_FILE = DATA_DIR / "xhs_daily_count.json"

# 选择器(改版时集中维护)
SEL_SEARCH_INPUT = 'input[placeholder*="搜索"]'
SEL_NOTE_ITEM = ".note-item"
SEL_NOTE_LINK = "a[href*='/explore/']"
SEL_NOTE_TITLE = "title"
SEL_NOTE_TEXT = ".note-text, #detail-desc, meta[name='description']"
SEL_NOTE_AUTHOR = ".author-wrapper .username, .user-name, meta[name='author']"
SEL_NOTE_IMAGES = ".swiper-slide img, #detail-img img, img[src*='xhscdn']"

# 防爬/验证码特征(命中即暂停并提示人工处理)
# 注意:只用强特征短语,避免"滑动""验证"等普通文字误报
CAPTCHA_HINTS = ["安全验证", "拖动滑块", "向右滑动", "滑块验证", "请完成验证", "captcha", "验证码"]
LOGIN_HINTS = ["登录已过期", "请先登录"]
# 网页端访问限制/笔记不可浏览特征
ACCESS_LIMIT_HINTS = ["访问限制", "pcweb_access_limit"]
NOTE_UNAVAILABLE = "暂时无法浏览"


def _save_debug_shot(page, tag: str) -> Path:
    """保存调试截图,返回路径。"""
    debug_dir = DATA_DIR / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    shot = debug_dir / f"{tag}_{int(time.time())}.png"
    try:
        page.screenshot(path=str(shot))
        return shot
    except Exception:
        return Path("(截图失败)")


def _load_daily_count() -> int:
    if LIMIT_FILE.exists():
        try:
            data = json.loads(LIMIT_FILE.read_text(encoding="utf-8"))
            if data.get("date") == time.strftime("%Y-%m-%d"):
                return int(data.get("count", 0))
        except Exception:
            pass
    return 0


def _bump_daily_count(n: int = 1) -> int:
    cur = _load_daily_count() + n
    LIMIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    LIMIT_FILE.write_text(
        json.dumps({"date": time.strftime("%Y-%m-%d"), "count": cur}, ensure_ascii=False),
        encoding="utf-8",
    )
    return cur


def _rate_limit() -> None:
    """限速:两次请求间隔 + 每日上限。"""
    if _load_daily_count() >= DAILY_LIMIT:
        raise RuntimeError(
            f"今日请求已达上限({DAILY_LIMIT}),明天再采;或删除 {LIMIT_FILE} 重置(谨慎)"
        )
    time.sleep(REQUEST_INTERVAL)


def _save_cookies(context) -> None:
    cookies = context.cookies()
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_PATH.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
    print(f"[cookie] 已保存 {len(cookies)} 条 -> {COOKIE_PATH}")


def _load_cookies(context) -> bool:
    if not COOKIE_PATH.exists():
        return False
    cookies = json.loads(COOKIE_PATH.read_text(encoding="utf-8"))
    if cookies:
        context.add_cookies(cookies)
        return True
    return False


def login_wizard(headless: bool = False) -> None:
    """弹出浏览器,用户手动登录一次,保存 cookie。唯一的人肉环节。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(locale="zh-CN", viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.goto("https://www.xiaohongshu.com", timeout=60000)
        print("请在浏览器中完成扫码/手机号登录,完成后回到此窗口按回车...")
        input()
        _save_cookies(ctx)
        browser.close()
    print("[登录] cookie 已就绪,可开始采集")


def _handle_interstitial(page) -> bool:
    """检测验证码/登录墙并处理。返回 True 表示可继续。

    交互终端:input() 等待用户完成验证;非交互环境:等待窗口期(用户若看到
    可见浏览器窗口可手动完成滑块),超时未解决则中止。
    """
    body = page.content()
    hit = [h for h in CAPTCHA_HINTS if h in body]
    if not hit:
        for hint in LOGIN_HINTS:
            if hint in body:
                raise RuntimeError(f"会话可能已失效(检测到「{hint}」),请重新运行 --login 登录")
        return True
    print(f"[拦截] 检测到「{hit[0]}」验证,请在浏览器窗口内完成(滑块/验证码)...")
    try:
        input("处理完成后按回车继续...")
    except EOFError:
        time.sleep(90)  # 给可见窗口的人工处理留时间
    body2 = page.content()
    if any(h in body2 for h in CAPTCHA_HINTS):
        raise RuntimeError("验证码未在等待窗口内解决;请在交互式终端运行采集并人工处理")
    return True


def _warm_up(page) -> None:
    """主页预热:先访问首页建立会话,降低搜索页触发风控的概率。"""
    try:
        page.goto("https://www.xiaohongshu.com", timeout=60000)
        page.wait_for_timeout(3000)
        _bump_daily_count()
    except Exception:
        pass


def _collect_search_links(page, keyword: str, max_notes: int = 30) -> list:
    """搜索页收集笔记链接,返回 note_id 列表。含等待/重试/0 命中诊断。"""
    url = (f"https://www.xiaohongshu.com/search_result?keyword={keyword}"
           f"&source=web_search_result_notes")
    ids: list = []
    for attempt in range(2):  # 一次自动重载重试
        try:
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"  [搜索] 加载异常: {e}")
            time.sleep(3)
            continue
        _bump_daily_count()
        # 网页端访问限制:整个会话被风控,继续采集无意义
        body = page.content()
        if "pcweb_access_limit" in page.url or any(h in body for h in ACCESS_LIMIT_HINTS):
            shot = _save_debug_shot(page, "access_limit")
            raise RuntimeError(
                f"会话处于网页端访问限制(截图 {shot});请等风控冷却(建议数小时)后再试"
            )
        if not _handle_interstitial(page):
            return []
        # 等待笔记卡片出现(最多 15s),提前出现则提前继续
        try:
            page.wait_for_selector(SEL_NOTE_LINK, timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(2000)
        for _ in range(4):  # 滚动触发懒加载
            page.mouse.wheel(0, 1500)
            page.wait_for_timeout(1000)
        hrefs = page.eval_on_selector_all(
            SEL_NOTE_LINK, "els => els.map(e => e.getAttribute('href') || '')"
        )
        ids = []
        for h in hrefs:
            m = re.search(r"/explore/([0-9a-fA-F]{24})", h)
            if m and m.group(1) not in ids:
                ids.append(m.group(1))
            if len(ids) >= max_notes:
                break
        if ids:
            break
        # 0 命中:留证据排查(截图 + 标题 + 正文片段)
        title = ""
        body = ""
        shot = None
        try:
            title = page.title()
            body = page.locator("body").inner_text()[:200].replace("\n", " ")
            debug_dir = DATA_DIR / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            shot = debug_dir / f"search_{int(time.time())}.png"
            page.screenshot(path=str(shot))
        except Exception:
            pass
        print(f"  [搜索] 0 命中(第{attempt + 1}次): 标题=[{title[:60]}] 页面文本=[{body[:120]}]")
        print(f"  [搜索] 调试截图: {shot}")
        if attempt == 0:
            try:
                page.reload(wait_until="domcontentloaded")
            except Exception:
                pass
            page.wait_for_timeout(5000)
    print(f"  [搜索] {keyword}: 命中 {len(ids)} 篇")
    return ids


def _collect_note_detail(page, note_id: str) -> dict:
    """笔记详情页:标题/正文/作者/图片 CDN。笔记不可浏览(仅App可见)时跳过。"""
    page.goto(f"https://www.xiaohongshu.com/explore/{note_id}", timeout=60000)
    _bump_daily_count()
    if not _handle_interstitial(page):
        return {}
    page.wait_for_timeout(2500)
    if NOTE_UNAVAILABLE in page.content():
        print(f"    [详情] {note_id} 网页端不可浏览(仅App可见),跳过")
        return {}
    page.wait_for_timeout(2500)

    title = page.title().replace(" - 小红书", "").strip()
    text = ""
    try:
        text = page.locator(SEL_NOTE_TEXT).first.inner_text().strip()
    except Exception:
        try:
            text = page.locator("meta[name='description']").first.get_attribute("content") or ""
        except Exception:
            pass
    author = ""
    try:
        author = page.locator(SEL_NOTE_AUTHOR).first.inner_text().strip()
    except Exception:
        author = ""
    images = page.eval_on_selector_all(
        SEL_NOTE_IMAGES,
        "els => els.map(e => e.getAttribute('src') || e.getAttribute('data-src') || '')"
        ".filter(s => s && s.includes('xhscdn'))",
    )
    # 图片源可能带 URL 编码参数,统一取原始地址
    images = [re.sub(r"![a-z]+-.*$", "", i) for i in images if i.startswith("http")]
    images = list(dict.fromkeys(images))
    return {"note_id": note_id, "title": title, "content": text,
            "author": author, "images": images[:9], "source_url": f"https://www.xiaohongshu.com/explore/{note_id}"}


def _classify_note(title: str, content: str) -> str:
    t = f"{title} {content}"
    if any(k in t for k in ("避雷", "踩坑", "劝退", "避坑", "别去", "不推荐", "坑")):
        return "avoid"
    if any(k in t for k in ("攻略", "路线", "一日游", "打卡", "怎么玩", "玩法")):
        return "guide"
    return "mixed"


def probe_session(headless: bool = False, keyword: str = "北京 攻略") -> str:
    """探测当前会话状态(采集前先探一下):
    normal / access_limited / login_expired / error。"""
    from playwright.sync_api import sync_playwright

    if not COOKIE_PATH.exists():
        return "error: 未找到登录 cookie,请先运行 --login"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            locale="zh-CN",
            viewport={"width": 1280, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
        )
        _load_cookies(ctx)
        page = ctx.new_page()
        _warm_up(page)
        try:
            page.goto(
                f"https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_search_result_notes",
                timeout=60000, wait_until="domcontentloaded",
            )
        except Exception as e:
            browser.close()
            return f"error: 页面加载失败 {e}"
        _bump_daily_count()
        page.wait_for_timeout(6000)
        body = page.content()
        result = ""
        if "pcweb_access_limit" in page.url or any(h in body for h in ACCESS_LIMIT_HINTS):
            shot = _save_debug_shot(page, "probe_limit")
            result = f"access_limited(截图 {shot});请等风控冷却(数小时)后再采"
        elif any(h in body for h in LOGIN_HINTS):
            result = "login_expired;请重新运行 --login"
        else:
            try:
                n = page.locator(SEL_NOTE_LINK).count()
            except Exception:
                n = 0
            if n > 0:
                result = f"normal(搜索到 {n} 条笔记,可以采集)"
            else:
                shot = _save_debug_shot(page, "probe_unknown")
                result = f"unknown(未检测到限制也未检测到笔记,截图 {shot})"
        browser.close()
        return result


def _download_images(spot_id: int, note_id: str, urls: list) -> list:
    """下载图片到本地,返回相对 data/ 的路径列表(前端经 /media 访问)。"""
    folder = IMG_DIR / str(spot_id) / note_id
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, url in enumerate(urls[:9], 1):
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            if r.status_code == 200 and r.content:
                ext = ".jpg"
                p = folder / f"{i}{ext}"
                p.write_bytes(r.content)
                # Windows 路径分隔符统一为 /,保证前端 /media 路由与 URL 拼接正确
                paths.append(str(p.relative_to(DATA_DIR)).replace("\\", "/"))
        except Exception as e:
            print(f"    [图片] {note_id}/{i} 下载失败: {e}")
    return paths


def collect_spot(spot_id: int, spot_name: str, city: str, headless: bool = True,
                 max_notes: int = 30, download_images: bool = True) -> list:
    """采集一个景区的攻略/避雷笔记并入库,返回入库笔记数。

    前提:已执行 login_wizard() 保存 cookie(COOKIE_PATH 存在)。
    """
    from playwright.sync_api import sync_playwright

    if not COOKIE_PATH.exists():
        raise RuntimeError("未找到登录 cookie,请先运行: python scripts/collect_xhs.py --login")

    from backend.app.db import get_conn

    notes = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(
            locale="zh-CN",
            viewport={"width": 1280, "height": 900},
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
        )
        _load_cookies(ctx)
        page = ctx.new_page()
        _warm_up(page)  # 主页预热降低风控
        for kw_suffix in ("攻略", "避雷", "一日游"):
            _rate_limit()
            keyword = f"{city} {spot_name} {kw_suffix}"
            ids = _collect_search_links(page, keyword, max_notes=max_notes)
            for nid in ids:
                try:
                    _rate_limit()
                    d = _collect_note_detail(page, nid)
                except Exception as e:
                    print(f"    [详情] {nid} 失败: {e}")
                    continue
                if not d or not d.get("content"):
                    continue
                images = []
                if download_images:
                    images = _download_images(spot_id, nid, d["images"])
                notes.append({
                    "title": d["title"][:200],
                    "content": d["content"][:4000],
                    "author_hash": d.get("author", "")[:32] or nid,
                    "note_type": _classify_note(d["title"], d["content"]),
                    "images_json": json.dumps(images or d["images"], ensure_ascii=False),
                    "source_url": d["source_url"],
                    "is_sample": 0,
                })
        browser.close()

    conn = get_conn()
    try:
        n = 0
        for note in notes:
            cur = conn.execute(
                "INSERT OR IGNORE INTO notes(spot_id, title, content, author_hash, "
                "images_json, note_type, source_url, is_sample, fetched_at) "
                "VALUES(?,?,?,?,?,?,?,0,datetime('now','localtime'))",
                (spot_id, note["title"], note["content"], note["author_hash"],
                 note["images_json"], note["note_type"], note["source_url"]),
            )
            n += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    print(f"[完成] {city} {spot_name}: 采集 {len(notes)} 篇,入库 {n} 篇")
    return notes
