# -*- coding: utf-8 -*-
"""Wikimedia Commons 图片许可过滤不依赖网络的单元测试。"""
from backend.collector.wikimedia_media import _is_reusable


def test_only_free_reusable_licenses_are_accepted():
    assert _is_reusable("CC BY-SA 4.0")
    assert _is_reusable("CC0")
    assert _is_reusable("Public domain")
    assert not _is_reusable("CC BY-NC 4.0")
    assert not _is_reusable("All rights reserved")
