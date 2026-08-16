# -*- coding: utf-8 -*-
"""下载前端静态资源:中国地图 GeoJSON 与 ECharts,保存到 frontend/assets/。

本机系统 curl/Schannel 异常,统一走 Python urllib(实测 HTTPS 正常)。
"""
import json
import os
import urllib.request

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "assets")


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (travel-planner setup)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def save(name, data):
    with open(os.path.join(ASSETS, name), "wb") as f:
        f.write(data)
    print(f"OK {name} ({len(data) // 1024} KB)")


def main():
    os.makedirs(ASSETS, exist_ok=True)

    geo_urls = [
        "https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json",
        "https://geo.datav.aliyun.com/areas_v3/bound/100000.json",
    ]
    for u in geo_urls:
        try:
            data = fetch(u)
            json.loads(data)  # 校验 JSON
            save("china.json", data)
            break
        except Exception as e:
            print(f"geo fail {u}: {e}")

    echarts_urls = [
        "https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js",
        "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js",
        "https://registry.npmmirror.com/echarts/5.6.0/files/dist/echarts.min.js",
    ]
    for u in echarts_urls:
        try:
            save("echarts.min.js", fetch(u))
            break
        except Exception as e:
            print(f"echarts fail {u}: {e}")


if __name__ == "__main__":
    main()
