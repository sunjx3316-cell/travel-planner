# -*- coding: utf-8 -*-
"""中文 OCR(RapidOCR):读取图片中的中文/英文文字。

用法: python scripts/ocr_cn.py <图片路径>
首次运行会自动下载识别模型(~15MB)。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

img_path = sys.argv[1] if len(sys.argv) > 1 else None
if not img_path or not Path(img_path).exists():
    print("用法: python scripts/ocr_cn.py <图片路径>")
    sys.exit(1)

from rapidocr_onnxruntime import RapidOCR  # noqa: E402

engine = RapidOCR()
result, _ = engine(str(Path(img_path).resolve()))
if not result:
    print("未识别到文字")
    sys.exit(0)
for box, text, score in result:
    print(f"{text}  (置信度 {score:.2f})")
