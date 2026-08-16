# -*- coding: utf-8 -*-
"""采集器纯逻辑测试(不依赖 playwright / 真实登录)。"""
import json
import shutil

import pytest

from backend.app.db import PROJECT_ROOT
from backend.collector import xhs_collector as xhs


@pytest.fixture
def tmp_dir():
    d = PROJECT_ROOT / "data" / "test_collector_tmp"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_classify_note():
    assert xhs._classify_note("故宫避雷帖", "这门票太坑了") == "avoid"
    assert xhs._classify_note("一日游攻略", "路线如下") == "guide"
    assert xhs._classify_note("随便逛逛", "今天天气不错") == "mixed"


def test_daily_count_persist_and_bump(tmp_dir, monkeypatch):
    monkeypatch.setattr(xhs, "LIMIT_FILE", tmp_dir / "cnt.json")
    assert xhs._load_daily_count() == 0
    xhs._bump_daily_count()
    xhs._bump_daily_count()
    assert xhs._load_daily_count() == 2


def test_daily_count_date_reset(tmp_dir, monkeypatch):
    monkeypatch.setattr(xhs, "LIMIT_FILE", tmp_dir / "cnt.json")
    (tmp_dir / "cnt.json").write_text(
        json.dumps({"date": "2000-01-01", "count": 99}), encoding="utf-8"
    )
    assert xhs._load_daily_count() == 0  # 日期不是今天 -> 重置


def test_rate_limit_blocks_at_limit(tmp_dir, monkeypatch):
    monkeypatch.setattr(xhs, "LIMIT_FILE", tmp_dir / "cnt.json")
    monkeypatch.setattr(xhs, "DAILY_LIMIT", 1)
    xhs._bump_daily_count()
    with pytest.raises(RuntimeError, match="上限"):
        xhs._rate_limit()


def test_download_images_relative_paths(tmp_dir, monkeypatch):
    class FakeResp:
        status_code = 200
        content = b"fakeimage"

    monkeypatch.setattr("backend.collector.xhs_collector.requests.get", lambda url, **kw: FakeResp())
    monkeypatch.setattr(xhs, "IMG_DIR", tmp_dir / "images")
    monkeypatch.setattr(xhs, "DATA_DIR", tmp_dir)

    paths = xhs._download_images(7, "abc123", ["http://x/1.jpg", "http://x/2.jpg"])
    assert len(paths) == 2
    assert all(p.startswith("images/") for p in paths)   # 相对路径,前端经 /media 访问
    assert (tmp_dir / paths[0]).exists()
