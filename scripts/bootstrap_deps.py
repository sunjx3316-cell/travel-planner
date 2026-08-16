# -*- coding: utf-8 -*-
"""沙箱内 pip 解包 wheel 被拦截,此脚本绕过 pip:
从清华镜像拉取 wheel -> 手动解包进 venv 的 site-packages。

用法: python scripts/bootstrap_deps.py
"""
import os
import re
import shutil
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_SITE = ROOT / ".venv" / "Lib" / "site-packages"
WHEELS_DIR = ROOT / ".pip-wheels"
MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"

# 依赖清单(含传递依赖;uvicorn 不用 [standard] 附加,Windows 上收益有限)
# 支持 "pkg==ver" 锁定版本(pydantic 2.13.4 要求 pydantic-core==2.46.4)
PKGS = [
    "fastapi", "starlette", "pydantic", "pydantic-core==2.46.4", "typing-extensions",
    "annotated-types", "anyio", "sniffio", "idna", "click", "colorama", "h11", "uvicorn",
    "requests", "certifi", "charset-normalizer", "urllib3",
    "typing-inspection", "annotated-doc",
    # 测试
    "pytest", "iniconfig", "packaging", "pluggy", "pygments", "httpx", "httpcore",
    # 小红书采集器 + 前端 e2e
    "playwright", "pyee", "greenlet",
    # 二维码/图像分析(诊断用)
    "opencv-python-headless", "numpy",
    # 中文 OCR(RapidOCR,ONNX 轻量方案)
    "rapidocr-onnxruntime", "onnxruntime", "pillow", "pyyaml", "pyclipper", "shapely",
]

UA = {"User-Agent": "Mozilla/5.0 (travel-planner bootstrap)"}


def fetch(url, binary=False):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def pick_wheel(html, pkg, pin=None):
    # href 形如 ../../packages/xx/.../name.whl#sha256=...
    links = re.findall(r'href="([^"]+?\.whl)(?:#[^"]*)?"', html)
    links = [l.split("#")[0] for l in links]
    if not links:
        raise RuntimeError(f"no wheel for {pkg}")

    def version(name):
        m = re.search(r"-(?P<ver>\d+(?:\.\d+)+)-(?:py2\.py3|py\d|cp\d|abi3|none)", name)
        if not m:
            return (0,)
        return tuple(int(x) for x in m.group("ver").split("."))

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

    if pin is not None:
        candidates = [n for n in links if version(n) == pin]
        if not candidates:
            raise RuntimeError(f"pinned version {'.'.join(map(str, pin))} not found for {pkg}")
    else:
        best_ver = max({version(n) for n in links})
        candidates = [n for n in links if version(n) == best_ver]
    best = max(candidates, key=platform)
    return urllib.parse.urljoin(f"{MIRROR}/{pkg}/", best).split("#")[0]


def download(pkg_spec):
    if "==" in pkg_spec:
        pkg, pin_s = pkg_spec.split("==", 1)
        pin = tuple(int(x) for x in pin_s.split("."))
    else:
        pkg, pin = pkg_spec, None
    html = fetch(f"{MIRROR}/{pkg}/").decode("utf-8", "replace")
    url = pick_wheel(html, pkg, pin)
    name = url.rsplit("/", 1)[-1]
    dest = WHEELS_DIR / name
    if not dest.exists():
        print(f"  download {name}")
        dest.write_bytes(fetch(url))
    return dest


def installed_version(wheel: Path):
    """返回该 wheel 对应 dist-info 名;若 site-packages 已有同名版本则跳过安装。"""
    with zipfile.ZipFile(wheel) as z:
        for n in z.namelist():
            if n.endswith(".dist-info/METADATA"):
                return n.split("/")[0]
    return None


def install_wheel(wheel: Path):
    dist_info = installed_version(wheel)
    if dist_info and (VENV_SITE / dist_info).exists():
        print(f"  skip {wheel.name} (已安装)")
        return
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        for n in names:
            if n.endswith("/"):
                continue
            parts = n.split("/")
            if len(parts) >= 2 and parts[-2].endswith(".data"):
                # .data/purelib、.data/platlib 内容需落到 site 根;.data/scripts、.data/data 本项目不需要
                if parts[-2] in (".data/purelib", ".data/platlib"):
                    rel = "/".join(parts[2:])
                    dst = VENV_SITE / rel
                else:
                    continue
            else:
                dst = VENV_SITE / n
            dst.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as src, open(dst, "wb") as out:
                shutil.copyfileobj(src, out)
    print(f"  installed {wheel.name}")


def main():
    os.makedirs(WHEELS_DIR, exist_ok=True)
    os.makedirs(VENV_SITE, exist_ok=True)
    for pkg in PKGS:
        print(f"[{pkg}]")
        try:
            w = download(pkg)
            install_wheel(w)
        except Exception as e:
            print(f"  FAIL {pkg}: {e}")
    print("bootstrap done")


if __name__ == "__main__":
    main()
