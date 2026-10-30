# 1.2.0 — 2026-10-30

- 1,034个地点有对应图，新增网页实景参考图支持；保留183个目的地、1,333处地点及精简评价，不把攻略建议当作独立亲历证据。
- 汇总本地补图批次、地点核对与去重结果，替换15处质量较差的旧图；仅发布最终景点图，不夹带评论页、整页攻略或登录截图。
- 493张参考图保持pending权利标记、原来源和署名，仅本机回环访问；其余已核验图库台账保持原许可，不把用户发布要求当作权利人授权。
- 修正溪布街已核实的武陵源坐标，不批量改动其他点位。
- 排除博物馆后仍有23处缺图；南京武庙文保碑为小图，高清替代仍待补充，不声称全库图像已齐。
- 保留重点评价／可追溯来源、本地与DeepSeek双模式、单城／多城／环线、铁路推荐和手动查询、工作坊与日历PDF。
- 新增只读源库、白名单目录合并与全新发布快照流程；清除个人清单、保存方案、原始笔记和私有配置。对发布包逐文件密钥比对、全量参考图访问隔离与干净启动验收。

# 1.1.1 — 2026-10-29

- **主要变化：评论参考方式重做。** 从堆叠长段表述改为“特点／提前留意／玩法条件”重点摘要，原表述与来源可展开；具体负面、个人偏好、历史条件与分歧分开保留，不把推荐攻略冒充独立亲历或普遍共识。
- 更新1,333处对应摘要及来源关联，保留证据不足提示。柳州9地与大理9处新增资料纳入，183个目的地目录保持一致。
- 加入18张景点参考照片，逐张核对、精确裁去网页与翻页界面；不发布评论页、攻略整页和登录截图。
- 参考照片保留来源及pending权利标记，按用户要求随包提供；程序中仅本机专用入口可读，不宣称已获公开转载许可。
- 早市类地点优先上午；新增私图访问隔离与发行包干净解压检查。
- 继续保留本地／DeepSeek双模式、单城／多城／环线、铁路规划、拖动工作坊、最终行程与日历PDF。

# 1.1.0 — 2026-10-28

同步发布源码和 Windows x64 免安装 Release。内置运行环境、评价及图片保持完整，不包含个人密钥、清单或保存方案；旧版下载包保留。

- 首次模式选择和详细介绍；默认本地规划，可自行设置 DeepSeek API 并主动测试。
- Key 仅保存在本机私有配置，默认不触发调用；设置接口限制本机操作并防跨站写入。
- 逐方案标记 AI 实际参与／失败回退，保留三套候选并防止 AI 润色破坏日程结构。
- 自驾按总天数、驾驶及游玩预算排程，回程计入日程；新增时间优先取舍方案。
- 修复城市强加返程、跨城到达日全天项目冲突、休整日超出天数、住宿距离误导等问题。
- 环线候选与完整行程区分，超出预算的安排单列备选；移除自驾景点间虚构的高铁提示。
- 切换页面／规划方式时保留出发地、风格及每城天数，避免填写的参数丢失。
- 压缩自驾日历的重复说明与留白，修复 PDF 孤立尾页。
- 扩展解压包验收：空配置启动、首次模式选择状态、单城／多城／环线离线推荐、铁路与 PDF、私有数据隔离。

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
