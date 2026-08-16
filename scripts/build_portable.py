# -*- coding: utf-8 -*-
"""构建「填 key 即用」免安装便携版。

收件人无需安装 Python:包内自带嵌入式 Python 3.13 运行时,
运行时依赖从清华镜像拉取 wheel 并解包进 runtime/Lib/site-packages(绕过 pip)。
产物: dist/旅行智规-免安装版/ 及其 zip。
首次双击 start.bat 时提示填写 DeepSeek API Key 并保存到 .env,然后自动启动并打开浏览器。
"""
import json
import os
import re
import shutil
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "dist" / "旅行智规-免安装版"
RUNTIME = BUILD / "runtime"
SITE = RUNTIME / "Lib" / "site-packages"
WHEELS = ROOT / ".pip-wheels"
MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
UA = {"User-Agent": "Mozilla/5.0 (travel-planner build-portable)"}

PY_VER = "3.13.15"
EMBED_URL = (f"https://registry.npmmirror.com/-/binary/python/{PY_VER}/"
             f"python-{PY_VER}-embed-amd64.zip")

# 与当前开发环境 venv 一致的运行时依赖(已验证可用组合)
RUNTIME_PKGS = [
    "fastapi==0.141.1", "starlette==1.6.0", "pydantic==2.13.4", "pydantic-core==2.46.4",
    "typing-extensions==4.16.0", "annotated-types==0.8.0", "typing-inspection==0.4.4",
    "annotated-doc==0.0.5", "anyio==4.14.2", "sniffio==1.3.1", "idna==3.18",
    "click==8.4.2", "colorama==0.4.6", "h11==0.16.0", "uvicorn==0.52.3",
    "requests==2.34.2", "certifi==2026.7.22", "charset-normalizer==3.5.0", "urllib3==2.7.0",
]

START_BAT = r"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 旅行智规 - 智能旅游规划
echo.
echo  ==========================================
echo   旅行智规 · 启动
echo  ==========================================
if exist .env goto start
echo.
echo  首次运行:请输入 DeepSeek API Key。可去 platform.deepseek.com 免费申请。
echo  直接回车可跳过,以「示例数据模式」运行,不带 AI 实时分析。
echo.
set /p "KEY=请输入 DeepSeek API Key: "
echo DEEPSEEK_API_KEY=%KEY%> .env
echo.
echo  已保存到 .env,可用记事本随时修改后重启。
echo.
:start
for /f %%i in ('runtime\python.exe get_lan_ip.py') do set LANIP=%%i
echo  本机访问: http://127.0.0.1:8000
if defined LANIP if not "%LANIP%"=="127.0.0.1" (
  echo  手机同 Wi-Fi 访问: http://%LANIP%:8000
  echo  提示:首次需在 Windows 防火墙放行 Python,手机需与电脑连同一 Wi-Fi。
)
start "" /b cmd /c "timeout /t 4 /nobreak >nul & start http://127.0.0.1:8000"
echo  正在启动服务,本机浏览器将自动打开;关闭本窗口即停止。
echo.
runtime\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
pause
"""

README_TXT = """旅行智规 · 免安装版(v0.1)
================================

一、怎么用
  1. 解压整个文件夹到任意位置(路径最好不含中文和空格)。
  2. 双击「start.bat」。
  3. 首次运行会提示填写 DeepSeek API Key(https://platform.deepseek.com 免费申请),
     直接回车可跳过 —— 以「示例数据模式」运行,内置 600+ 景点/美食/住宿。
  4. 浏览器自动打开 http://127.0.0.1:8000 即可使用。
  5. 关闭黑色窗口即停止服务。

二、手机也能看
  启动后窗口会显示「手机同 Wi-Fi 访问: http://192.168.x.x:8000」:
  - 手机与电脑连同一个 Wi-Fi,用手机浏览器打开该地址即可体验;
  - 首次需在 Windows 防火墙弹窗中点「允许访问」;
  - 电脑关机或关掉窗口后手机就无法访问了。

三、更换/填写 Key
  用记事本打开 .env,把 DEEPSEEK_API_KEY 改成你的 key,保存后重启 start.bat。

四、功能速览
  - 地图选城市/景区/环线,购物车式清单
  - 城市模式:选城市 -> 出发地+总天数 -> 「获取推荐」分配每城几天与起始城市
  - 自驾模式:跨城路线 2-opt 优化,闭环返回
  - AI 口碑卡:避雷共识、平替推荐、时段规划、住宿锚点推荐、返程预留
  - 示例数据模式不带 AI 实时分析;填 Key 后所有 AI 能力自动开启

五、数据说明
  当前内置为「示例数据」(含 AI 预生成的示例口碑卡)。
  正式数据计划从小红书/携程等渠道采集后由 AI 加工,本版暂未包含。
  本项目仅用于个人学习演示。
"""

ENV_EXAMPLE = "# 复制为 .env 并填入你的 Key;或直接运行 start.bat 按提示填写\nDEEPSEEK_API_KEY=\n"


def fetch(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def fetch_retry(url, tries=4):
    """拉取带重试(镜像偶发 SSL 断连)。"""
    last = None
    for i in range(tries):
        try:
            return fetch(url)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise last


def pick_wheel(html, pkg, pin):
    links = re.findall(r'href="([^"]+?\.whl)(?:#[^"]*)?"', html)
    links = [l.split("#")[0] for l in links]
    if not links:
        raise RuntimeError(f"no wheel for {pkg}")

    def version(name):
        m = re.search(r"-(?P<ver>\d+(?:\.\d+)+)-(?:py2\.py3|py\d|cp\d|abi3|none)", name)
        return tuple(int(x) for x in m.group("ver").split(".")) if m else (0,)

    def platform(name):
        s = 0
        if name.endswith(("py3-none-any.whl", "py2.py3-none-any.whl")):
            s += 100
        if re.search(r"cp313", name):
            s += 80
        elif re.search(r"cp\d", name):
            s += 30
        if "win_amd64" in name:
            s += 50
        elif "win32" in name:
            s += 20
        if "abi3" in name:
            s += 10
        return s

    candidates = [n for n in links if version(n) == pin]
    if not candidates:
        raise RuntimeError(f"pinned {pkg} {'.'.join(map(str, pin))} not found on mirror")
    best = max(candidates, key=platform)
    return urllib.parse.urljoin(f"{MIRROR}/{pkg}/", best).split("#")[0]


def download_wheel(pkg_spec):
    # 文件系统缓存优先(.pip-wheels 下按 包名-版本 匹配),命中则完全不访问网络
    pkg, pin_s = pkg_spec.split("==", 1)
    pkg_u = pkg.replace("-", "_")
    for stem in (pkg_u, pkg):
        matches = sorted(WHEELS.glob(f"{stem}-{pin_s}-*.whl"))
        if matches:
            return matches[0]
    pin = tuple(int(x) for x in pin_s.split("."))
    html = fetch_retry(f"{MIRROR}/{pkg}/").decode("utf-8", "replace")
    url = pick_wheel(html, pkg, pin)
    name = url.rsplit("/", 1)[-1]
    dest = WHEELS / name
    if not dest.exists():
        print(f"  download {name}")
        dest.write_bytes(fetch_retry(url))
    return dest


def extract_wheel(wheel: Path, site: Path):
    """解包 wheel 进 site-packages(处理 .data/purelib 与 .data/platlib)。"""
    with zipfile.ZipFile(wheel) as z:
        for n in z.namelist():
            if n.endswith("/"):
                continue
            parts = n.split("/")
            if len(parts) >= 2 and parts[-2].endswith(".data"):
                if parts[-2] in (".data/purelib", ".data/platlib"):
                    dst = site / "/".join(parts[2:])
                else:
                    continue
            else:
                dst = site / n
            dst.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as src, open(dst, "wb") as out:
                shutil.copyfileobj(src, out)


def step(msg):
    print(f"\n== {msg} ==")


def backup_db(src, dst):
    """SQLite backup API 生成一致快照(服务运行中也可安全复制)。"""
    for attempt in range(6):
        try:
            s = sqlite3.connect(src)
            d = sqlite3.connect(dst)
            s.backup(d)
            d.commit()
            d.close()
            s.close()
            return
        except sqlite3.OperationalError as e:
            time.sleep(1)
            if attempt == 5:
                raise


def clean_db(path):
    conn = sqlite3.connect(path)
    try:
        for t in ("cart_items", "plans"):
            try:
                conn.execute(f"DELETE FROM {t}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
    finally:
        conn.close()


def build():
    if BUILD.exists():
        shutil.rmtree(BUILD)
    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(SITE, exist_ok=True)
    os.makedirs(WHEELS, exist_ok=True)

    # 1. 嵌入式 Python 运行时
    step("1/6 下载嵌入式 Python")
    embed_zip = WHEELS / f"python-{PY_VER}-embed-amd64.zip"
    if not embed_zip.exists():
        print(f"  download {EMBED_URL.split('/')[-1]}")
        embed_zip.write_bytes(fetch_retry(EMBED_URL))
    with zipfile.ZipFile(embed_zip) as z:
        z.extractall(RUNTIME)
    print("  runtime extracted")
    # 覆盖已有的 python*. _pth(名字随版本,如 python313._pth):
    # _pth 存在时 sys.path 完全由它决定(PYTHONPATH/cwd 均被忽略),
    # 因此显式加入 site-packages 与包根目录(..)
    pths = list(RUNTIME.glob("python*._pth"))
    pth = pths[0] if pths else RUNTIME / "python313._pth"
    pth.write_text("python313.zip\n.\nLib\\site-packages\n..\nimport site\n", encoding="utf-8")
    for extra in RUNTIME.glob("python*._pth"):
        if extra != pth:
            extra.unlink()
    for dll in ("vcruntime140.dll", "vcruntime140_1.dll"):
        if not (RUNTIME / dll).exists():
            print(f"  WARN {dll} 缺失(接收方机器若无 VC 运行库需自备)")

    # 2. 运行时依赖 wheel
    step("2/6 拉取并解包运行时依赖")
    for spec in RUNTIME_PKGS:
        w = download_wheel(spec)
        extract_wheel(w, SITE)
        print(f"  ok {w.name}")

    # 3. 应用代码与数据
    step("3/6 拷贝应用代码/前端/数据")
    for name in ("backend", "frontend"):
        shutil.copytree(ROOT / name, BUILD / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"))
    db_dst = BUILD / "data" / "travel.db"
    (BUILD / "data").mkdir(exist_ok=True)
    backup_db(ROOT / "data" / "travel.db", db_dst)
    clean_db(db_dst)
    print(f"  travel.db -> {db_dst} (cart/plans 已清空)")

    # 4. 启动脚本与说明
    step("4/6 生成 start.bat / .env.example / 使用说明")
    (BUILD / "start.bat").write_text(START_BAT, encoding="utf-8")
    (BUILD / ".env.example").write_text(ENV_EXAMPLE, encoding="utf-8")
    (BUILD / "使用说明.txt").write_text(README_TXT, encoding="utf-8")
    shutil.copy(ROOT / "scripts" / "get_lan_ip.py", BUILD / "get_lan_ip.py")

    # 5. 自测:用内置运行时导入关键模块 + 启动服务验证
    step("5/6 自测:内置运行时导入 + 起服务")
    py = RUNTIME / "python.exe"
    check = BUILD / "_check_runtime.py"
    check.write_text(
        "import sqlite3, ssl, json, urllib.request\n"
        "import fastapi, starlette, pydantic, pydantic_core, uvicorn, requests\n"
        "print('IMPORTS_OK', fastapi.__version__, pydantic.VERSION)\n",
        encoding="utf-8")
    out = run(py, ["_check_runtime.py"], BUILD)
    if "Traceback" in out or "IMPORTS_OK" not in out:
        raise RuntimeError(f"内置运行时导入失败:\n{out}")
    print("  imports ok:", [l for l in out.splitlines() if "IMPORTS_OK" in l][0])
    probe_server(py)
    check.unlink(missing_ok=True)

    # 6. 压缩
    step("6/6 打包 zip")
    zip_name = ROOT / "dist" / "旅行智规-免安装版-v0.1.0.zip"
    zip_name.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(BUILD.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(BUILD.parent))
    size_mb = zip_name.stat().st_size / 1048576
    print(f"\n完成! {zip_name} ({size_mb:.1f} MB)")


def run(py, args, cwd):
    import subprocess
    import tempfile
    log = tempfile.NamedTemporaryFile("w+", suffix=".log", delete=False, encoding="utf-8")
    log.close()
    out_f = open(log.name, "wb")
    try:
        p = subprocess.run([str(py), *args], cwd=str(cwd), stdout=out_f,
                           stderr=subprocess.STDOUT, timeout=180,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    finally:
        out_f.close()
    text = open(log.name, "r", encoding="utf-8", errors="replace").read()
    os.unlink(log.name)
    return text


def probe_server(py):
    import subprocess
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "DEEPSEEK_API_KEY": ""}
    child_log = BUILD / "probe_child.log"
    with open(child_log, "wb") as out_f:
        proc = subprocess.Popen(
            [str(py), "-m", "uvicorn", "backend.app.main:app",
             "--host", "127.0.0.1", "--port", "8011"],
            cwd=str(BUILD), stdout=out_f, stderr=subprocess.STDOUT, env=env)
        try:
            ok = False
            last_err = ""
            for _ in range(60):
                time.sleep(1)
                try:
                    body = urllib.request.urlopen("http://127.0.0.1:8011/api/status", timeout=3).read()
                    st = json.loads(body)
                    assert "llm_available" in st and "data_source" in st
                    ok = True
                    break
                except Exception as e:
                    last_err = f"{type(e).__name__}: {e}"
            if not ok:
                detail = child_log.read_text("utf-8", "replace")[-800:]
                raise RuntimeError(f"便携版服务未就绪,最后错误: {last_err}\n子进程日志:\n{detail}")
            print("  服务就绪:", json.dumps(st, ensure_ascii=False))
            cities = json.loads(urllib.request.urlopen("http://127.0.0.1:8011/api/cities", timeout=5).read())
            print("  城市数:", len(cities), "| 含 lng:", any(c.get("lng") for c in cities))
            html = urllib.request.urlopen("http://127.0.0.1:8011/", timeout=5).read().decode("utf-8", "replace")
            print("  首页含地图容器:", 'id="map"' in html)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
    child_log.unlink(missing_ok=True)


if __name__ == "__main__":
    build()
