# 1.0.1 — 2026-10-28

- 修复铁路对比页确认后未交接到旅行最终安排，导致 PDF 缺少铁路行程的问题。
- 已保存的铁路行程可直接“加入旅行安排”，保留原有每日景点和历史参考票价，无需重新规划。
- 铁路“已定行程”卡片增加删除确认和当前页面撤销；不连带删除已加入旅行安排的副本。
- 更新缓存版本、启动器、后端版本号和完整免安装包；内置评价和图片保持不变。
- 增加代码文件校验清单，便携版解压验收核对两项修复确实存在。

# 1.0.0 — 2026-10-28

- Separate top-level railway entry; lazy-loaded recommendations, comparison and manual rail editing.
- Attach complete railway journeys to a travel-plan draft; save with final itinerary and export to calendar PDF / print.
- Drag day cards across morning/afternoon/day columns, recover drafts, undo and confirm one final version.
- Simplified native map markers avoid expensive redraws during dragging.
- Bundle curated review evidence and attributed photographs; preserve weak-evidence labels and removed-place decisions.
- Private user state and credentials excluded. Media routes serve images only, not the database.
- Self-contained Windows x64 portable release, local-only default, explicit LAN launcher, checksum manifest.
