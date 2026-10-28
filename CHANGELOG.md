# 1.1.0 源码更新 — 2026-10-28

本次上传源码，未重新发布免安装 Release；现有 v1.0.1 下载包保持不变。

- 首次模式选择和详细介绍；默认本地规划，可自行设置 DeepSeek API 并主动测试。
- Key 仅保存在本机私有配置，默认不触发调用；设置接口限制本机操作并防跨站写入。
- 逐方案标记 AI 实际参与／失败回退，保留三套候选并防止 AI 润色破坏日程结构。
- 自驾按总天数、驾驶及游玩预算排程，回程计入日程；新增时间优先取舍方案。
- 修复城市强加返程、跨城到达日全天项目冲突、休整日超出天数、住宿距离误导等问题。
- 环线候选与完整行程区分，超出预算的安排单列备选；移除自驾景点间虚构的高铁提示。
- 切换页面／规划方式时保留出发地、风格及每城天数，避免填写的参数丢失。
- 压缩自驾日历的重复说明与留白，修复 PDF 孤立尾页。

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
