# -*- coding: utf-8 -*-
"""下载省级 GeoJSON(从全国地图的 adcode 逐省拉取),存 frontend/assets/provinces/。"""
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "frontend" / "assets"
PROV_DIR = ASSETS / "provinces"
CHINA_PATH = ASSETS / "china.json"


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (travel-planner setup)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main():
    PROV_DIR.mkdir(parents=True, exist_ok=True)
    china = json.loads(CHINA_PATH.read_text(encoding="utf-8"))
    items = []
    for f in china.get("features", []):
        props = f.get("properties", {})
        name = props.get("name", "")
        adcode = props.get("adcode", "")
        if name and adcode:
            items.append((name, str(adcode)))
    print(f"全国地图共 {len(items)} 个省级行政区")

    ok = 0
    prov_map = {}
    for name, adcode in items:
        dest = PROV_DIR / f"{adcode}.json"
        if dest.exists():
            ok += 1
            prov_map[name] = adcode
            continue
        url = f"https://geo.datav.aliyun.com/areas_v3/bound/{adcode}_full.json"
        try:
            data = fetch(url)
            json.loads(data)  # 校验
            dest.write_bytes(data)
            prov_map[name] = adcode
            ok += 1
            print(f"  OK {name} ({adcode}) {len(data) // 1024}KB")
        except Exception as e:
            print(f"  FAIL {name} ({adcode}): {e}")

    (ASSETS / "province_map.json").write_text(
        json.dumps(prov_map, ensure_ascii=False), encoding="utf-8"
    )
    print(f"完成: {ok}/{len(items)} 个省,索引 -> frontend/assets/province_map.json")


if __name__ == "__main__":
    main()
