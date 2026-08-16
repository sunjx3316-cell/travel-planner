# -*- coding: utf-8 -*-
"""解码截图中的二维码内容。用法: python scripts/_decode_qr.py <图片路径>"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import cv2
import numpy as np

img_path = sys.argv[1] if len(sys.argv) > 1 else None
if not img_path:
    print("用法: python scripts/_decode_qr.py <图片路径>")
    sys.exit(1)

# cv2.imread 不支持中文路径,用字节流解码
try:
    raw = Path(img_path).read_bytes()
    img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
except Exception as e:
    print("读取失败:", e)
    sys.exit(1)
if img is None:
    print("无法解码图片:", img_path)
    sys.exit(1)

detector = cv2.QRCodeDetector()
data, points, _ = detector.detectAndDecode(img)
if data:
    print("二维码内容:", data)
    if data.startswith("http"):
        print("类型: URL,可直接在电脑浏览器打开")
else:
    print("未直接检测到二维码,尝试放大后二次检测...")
    # 放大 2 倍再试(小二维码常需放大)
    bigger = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    data2, _, _ = detector.detectAndDecode(bigger)
    if data2:
        print("二维码内容(放大后):", data2)
        if data2.startswith("http"):
            print("类型: URL,可直接在电脑浏览器打开")
    else:
        print("放大后仍未检测到二维码;请人工确认图片内容")
