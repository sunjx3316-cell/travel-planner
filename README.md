# 旅行智规 Travel Planner

## v1.1.0 源码更新：两种规划模式

首次打开先选择 **本地规划** 或 **AI 增强**，之后从顶部模式按钮切换；两者共用资料、清单、工作坊与最终行程，不创建两套重复页面。

- **本地规划（默认）**：无需 API Key，即使环境里已有 Key 也不会自动调用 AI。使用本地地图、内置评价与图片、规则路线、拖动微调、最终行程和日历 PDF。运行本机服务后，内置功能无需互联网；外部来源链接、资料更新和在线票价仍需联网。
- **AI 增强**：在本机页面填写自己的 **DeepSeek 官方 API Key**。连接测试由用户主动触发，会产生少量 Token 费用；保存 Key 不触发测试。当前城市／自驾方案由规则排程，再由 AI 补充说明与提醒，不宣称 AI 已核验所有评价或实时交通。
- 每份方案单独标明本地生成、AI 参与或失败回退。切换模式不追溯修改已生成方案；需要重新生成才按新模式执行。失败不阻断本地推荐，部分 AI 响应不会使其余候选方案丢失。
- Key 保存在忽略提交的 `data/private/ai_settings.json`，不写入前端存储、返回接口或进入发行包。此文件当前不加密，勿分享它或 `.env`。旧 `.env` 的 Key 可作为本机配置来源，但默认仍为本地模式。“移除 Key”会移除本应用的保存值并停用环境变量回退，不撤销供应商账户的 Key。
- 设置仅允许本机 loopback 直接访问，拒绝局域网、代理及跨站写入。在可信局域网开启 AI 后，其他使用者的规划也可能消耗该账户额度；本版不是公网多用户密钥托管服务。

离线排程改进：总天数最多 30 天，自驾共同核算驾驶与游玩时间，长途拆日、闭环预留返程；“时间优先”方案主动取舍候选，剩余点保留在清单。城市模式不强加返程，跨城到达日优先安排可调整的半日项目，全天景点顺延；住宿按当天实际地点估算。所有时间与里程仍是规则估算，不替代真实导航、预约和天气核实。

回归命令：`python -m pytest backend/tests -q`；`node scripts/test_workshop.cjs`、`node scripts/test_map.cjs`、`node scripts/test_planning_preferences.cjs`。新增模式安全测试及单城、多城、甘南环线、亲子／紧凑／轻松的时间预算测试。

本节功能已包含在 v1.1.0 源码中。下方的 **v1.0.1 仍是已有的免安装 Release**，不包含本次双模式和算法更新；本次仅更新源码，未重新发布下载包。体验新功能请使用最新源码或本机已更新的程序。

## v1.0.1 快速使用（2026-10-28）

Windows 用户从 [Releases](https://github.com/sunjx3316-cell/travel-planner/releases/latest) 下载 `travel-planner-1.0.1-windows-x64.zip`，**完整解压**后双击 `start.bat`，访问 http://127.0.0.1:8000/ 。无需安装 Python，无需填写 Key。关闭启动窗口停止服务。端口占用时先关闭旧版，勿同时启动两个实例。

同 Wi-Fi 手机体验可运行 `start-lan.bat`，仅在可信局域网放行防火墙；默认启动不会开放局域网。请勿直接将本地单用户版本暴露公网。

顶部 **铁路** 可单独查询；**方案 → 选择铁路** 或 **工作坊 → 铁路交通** 把完整路线加入当前草稿；点 **确认行程** 后，在 **我的行程** 查看并导出日历式 PDF（含铁路页）。独立交通清单不会自动混入最终方案，可从工作坊手动选用。铁路按实际出发日期保存，不会自动压缩景点安排或推算每天交通冲突。

发行版包含 `bundled_data/manifest.json` 中列出的全部评价目录和已核验图片台账，图片署名与来源保留；弱证据不是已证实共识。无网络也可查看内置资料、编辑、用规则生成方案和导出 PDF；AI 实时生成、在线票价核验及未缓存的省级地图等在线能力需要网络。铁路是静态时刻快照，不是实时售票或余票保证。

源码部署（Python 3.13）：`python -m venv .venv`，安装 `pip install -r backend/requirements.txt`，然后 `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`。首次启动自动从随仓库附带的只读资料创建 `data/travel.db`，不会覆盖已有库。个人清单、保存方案及密钥不会随发行版分发。可选 API Key 请自行复制 `.env.example` 为 `.env` 后配置。

开发者打包使用 `python scripts/build_release.py --runtime <已安装后端依赖的嵌入式Python目录>`，生成全新目录与 SHA-256 校验文件，不覆盖运行中的旧版。`scripts/build_portable.py` 是旧版构建脚本，不用于本次发行。

升级请保留旧版文件夹及浏览器数据作为备份，新版解压到新文件夹；不要把旧库直接覆盖到新版，否则会丢失更新资料。浏览器草稿保存在相同地址的本机存储，不提供跨设备同步。

下文保留项目早期功能说明；最新数据范围以随包 manifest 为准，早期示例数量与旧打包说明不再作为当前版本承诺。

开局一张中国地图,选出想去的城市和景区,AI 整合攻略口碑(含暗广过滤与避雷共识),生成多套行程方案。

## 功能

- 🏛️ **全国评级数据**:5A 117 个 + 4A 89 个 + 5 条环线 49 个非评级点位;
  **27 个著名博物馆**;**177 个有景点城市全覆盖**:美食 648 条(每城均有必吃+美食街,美食街带坐标可上图),
  **住宿 150 条**(区域级防暗广),含延安/遵义/井冈山等红色旅游城市
- 🗺️ **地图选点(三级)**:全国地图仅选省 → 点击省份切换到**该省地图**(直接标注景点散点,
  按 🌿自然/🏯人文/🌐综合 分类着色与筛选;图层可切 **🏞景区 / 🏮美食街 / 全部**) →
  点景点看口碑卡;「← 返回全国」随时退出
- 🏞️ **景区口碑卡**:AI 攻略整合(亮点/玩法/花费)+ 暗广检测 + 真实下限(避雷共识)+ 信任度
- 💰 **门票价格 + 平替推荐**:全量景点参考价(274 个),识别 93 个高价(≥100 元)景点;
  **20 组平替**(迪士尼→欢乐谷、莫高窟→榆林窟、黄河九曲第一湾→杂威冻列/索克藏寺等),
  每条如实标注缺点,可查看/改选平替,**支持「🗺 地图对比」(主景点+平替同图标注)
- 🛒 **想去清单**:购物车式管理,按城市分组,可清空
- **行程工作坊**：生成方案后按天切换，点选一项才展开编辑；支持时间/备注调整、清单地点替换、跨天移动、自由安排、撤销和本机草稿恢复。只做本地规则检查，不会因为编辑重复调用 AI。手动调整后撤下旧路线、住宿及交通推算，避免显示过期结果。
- **最终行程与 PDF**：确认后在“我的行程”展示唯一版本，可继续编辑或直接下载中文 A4 PDF，也保留打印另存入口。草稿和最终行程仅存当前浏览器；PDF 在本机服务内存中生成，不写入数据库或上传到第三方。
- 🏙 **城市模式**:城市 tab 顶部即**规划工作台** —— 选城市 → 加想玩的 →
  **出发地 + 总天数 → 「🤖 获取推荐」**:算法按可玩项目数分配**每城玩几天**、
  依据出发地便利推荐**起始城市**(出发地不在行程内时自动取最近的城)并给出**城市游玩顺序**;
  **点击已选城市标签 → 地图自动切到该省并定位,同时列出有啥玩的**;
  一键「✅ 按推荐生成」或手调每城天数后生成;**无闭环/出发点(那是自驾模式的)**,
  核心是**时段规划**:每个景点给出推荐游玩时段
  (🕐清晨/上午/下午/傍晚/晚上/全天 + 理由,按时段排一天行程,如省博上午、商圈下午、夜市晚上)
  + **每日"前往下一城"交通建议**(高铁/自驾/航班估算);
  **住宿按"当天玩的地点"锚点算法推荐**:几何中心→选最近住宿区域,
  输出"**XX商圈附近(地铁X号线)**"式描述 + "距当天各景点 X-Ykm,位置居中"合理性说明;
  城市详情分区块展示:**🏛 博物馆 / 🛍 商圈·商业街(含商场) / 🌳 公园 / 🏮 美食街 / 🏞 景区**;
  **商圈标注类型(商业/娱乐/混合)与档次(高端/中高端/中低端)**
- 🚗 **自驾模式**:以景点为单位的跨城路线,**先填出发地**(路线从出发地起止,闭环返回),
  **2-opt 优化消除路线交叉**,最近邻/评分/反向 3 套方案,每日附**住宿推荐 + 当地必吃/美食街**
- 🏔️ **精选环线(5 条)**:甘南/川西/青甘/滇西北/北疆,共 49 个非评级绝美点位;
  「环线」页选择环线 → **地图自动切换到该区域并标注全部点位** → 整条加入清单 →
  自驾模式生成路线 → **路线以闭环折线画在地图上**(🔁 默认闭合返回起点,可关;3 套方案可切换)
- 🔍 **景区探索工具**:`scripts/explore_area.py` 按地区+关键词挖掘未评级自然景区;
  `scripts/explore_route.py` 以环线每个点位为中心做周边搜索,自动发现沿途新景点(需高德 AMAP_KEY)

## 快速开始

### 铁路工作台已整合（v0.5）

无需单独启动 rail-atlas，继续打开旅行智规的 `http://127.0.0.1:8000/`。
“城市 → 出发地旁 → 铁路交通”，或“我的行程 → 规划铁路交通”进入。
支持铁路推荐、自由编辑、多方案对比；选定完整路线后，点顶部“加入交通清单”，
会返回“我的行程”。交通清单单独保存在本机浏览器，不自动改动每日景点安排，
当前日历 PDF 仍导出景点日程，不包含独立交通清单。

铁路页面只有打开时才装载数据和计算线程，关闭后卸载，主地图不叠加铁路地图。
匿名票价查询统一走 `/api/rail/fares`：每 IP 每分钟 12 批、每批最多 8 个区间、
全局单批处理、25 秒网络预算、10 分钟缓存。遇到验证或不可用则保持“待核价”，
不读取账号，不购票，不绕过访问限制。静态时刻表、已保存参考价和换乘余量都不是
余票或实际开行保证。来源与授权说明见 [铁路来源](frontend/rail/NOTICE.md)。

本次地图小标使用原生圆点；已移除拖动/绘制结束时触发的自动移位与重新绘制逻辑。
离线回归：`node scripts/test_map.cjs`、`node scripts/test_workshop.cjs`、
`node scripts/test_rail_integration.cjs`、`node scripts/test_rail_bridge.mjs`、
`node --test scripts/rail-tests/*.test.mjs`，以及 `python -m pytest backend/tests/test_rail_fares.py`。

```powershell
# 1. 首次:安装依赖(沙箱内 pip 不可用,使用引导脚本)
.venv\Scripts\python.exe scripts\bootstrap_deps.py

# 1b. (可选)一键准备演示数据:重建库(旧库自动备份)并预计算全部 16 张口碑卡
.venv\Scripts\python.exe scripts\prepare_demo.py

# 2. 启动
.\scripts\start.ps1
# 或: .venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

# 3. 打开浏览器
http://127.0.0.1:8000
```

## 打包「免安装便携版」(发给别人体验,对方只需填 AI key)

```powershell
# 一键构建:内置嵌入式 Python 3.13 + 全部运行时依赖(无需对方装 Python)
.venv\Scripts\python.exe scripts\build_portable.py
# 产物: dist/旅行智规-免安装版-v0.1.0.zip
```

收件人用法:解压 → 双击 `start.bat` → 首次运行提示粘贴 DeepSeek API Key
(直接回车 = 示例数据模式)→ 浏览器自动打开 `http://127.0.0.1:8000`。
Key 保存在包内 `.env`,随时可改;内置 `data/travel.db`(600+ 景点/AI 示例口碑卡)。
构建脚本自带自测:内置运行时导入关键模块 + 起服务验证 `/api/status`。

**手机同 Wi-Fi 访问**:服务绑定 `0.0.0.0`,启动窗口会打印
`手机同 Wi-Fi 访问: http://电脑IP:8000`(首次需在防火墙放行 Python),
手机浏览器打开即可体验。

**跨网络手机访问 / 安装到桌面**:使用 Docker + Caddy 部署到公网 HTTPS 域名，手机无需与电脑同一 Wi-Fi；部署说明见 [腾讯云部署](docs/腾讯云部署.md)。

## 配置

复制 `.env.example` 为 `.env`:

```
DEEPSEEK_API_KEY=sk-xxxxxxxx   # 已配置:AI 管线用 DeepSeek 大模型
AMAP_KEY=xxxxxxxx              # 可选;高德开放平台,用于 POI 扩充景区名单
```

- **DeepSeek 已激活**:口碑卡与行程方案由真实大模型生成(来源标注 "DeepSeek")。
  若未配置 key,自动降级启发式 mock,链路完整可演示。
- 配置高德 key → 运行 `scripts\fetch_poi.py` 自动扩充城市景区名单。
- 重新用 LLM 计算全部口碑卡: `python scripts\refresh_llm_cards.py`

## 小红书采集(待账号登录激活)

采集器已完整实现(`backend/collector/xhs_collector.py`),只需你登录一次:

```powershell
# 1. 首次:弹出浏览器,手动登录一次(保存 cookie,后续复用)
.venv\Scripts\python.exe scripts\collect_xhs.py --login

# 2. 采集:为所有缺笔记的景区采集攻略/避雷笔记(自动下载图片、重算 AI 口碑卡)
.venv\Scripts\python.exe scripts\collect_xhs.py
#    或指定景区: .venv\Scripts\python.exe scripts\collect_xhs.py 故宫博物院 西湖
```

采集纪律:请求间隔 8 秒、单账号每日上限 200 次(超出自动停止,次日恢复);
笔记按标题/正文自动分类(避雷/攻略/混合),来源链接去重;图片下载到 `data/images/`。

## 评价采集框架(喂数据即出 AI 口碑卡)

任何来源的信息,按标准结构喂进来,自动去重/分类/重算口碑卡(暗广过滤+共识差评+信任度):

```powershell
# 1. 手工粘贴任意文本(最通用;网页复制/自己写的评价都行,自动分类攻略/避雷)
.venv\Scripts\python.exe scripts\import_reviews.py --spot 故宫 --source mafengwo --text "排队2小时门票60,值得但人多"

# 2. 批量文件(每行一条;支持 [avoid] 前缀 或 `标题 | 内容`)
.venv\Scripts\python.exe scripts\import_reviews.py --spot 玉龙雪山 --file reviews.txt

# 3. 高德/百度官方评分(需对应 key,见 .env 模板)
.venv\Scripts\python.exe scripts\import_reviews.py --spot 故宫 --source amap --score 4.6

# 4. 看看哪些景点还没有真实笔记(供采集)
.venv\Scripts\python.exe scripts\import_reviews.py --missing

# 5. 应用内用户评价(P2 自产口碑): POST /api/spots/{id}/reviews
```

框架文件: `backend/collector/review_source.py`(标准 item 结构 + ReviewSource 基类 +
ingest_items 入库管线);接入新来源只需实现一个 `fetch(spot) -> list[item]`。
来源现状: amap/baidu 评分接口已实现(填 key 即用);马蜂窝/携程反爬+法律风险,
当前建议复制文本走 paste;小红书见 collect_xhs.py。

## 景点数据扩充(两条路)

**A. 内置精选景点(无需 key,已入库)** —— 斗南花市/天津海洋博物馆/环球影城/海洋馆/
科技馆/主题乐园/花市/名楼/特色街区等 80+ 个大众可玩点,与 5A/4A 互补
(`backend/app/seed_popular.py`)。

**B. 高德 POI 批量扩充(需 AMAP_KEY,可无限丰富)** —— 在 `.env` 填高德 key 后:

```powershell
# 多关键词聚合(景点/博物馆/海洋馆/科技馆/动物园/公园/古镇/温泉/游乐园/街区/滑雪场),
# 自动过滤酒店餐厅等噪音,同名去重
.venv\Scripts\python.exe scripts\fetch_poi.py              # 全部城市
.venv\Scripts\python.exe scripts\fetch_poi.py 北京 上海    # 指定城市
.venv\Scripts\python.exe scripts\fetch_poi.py --limit 60   # 每城最多 60 条
```

另: `scripts/explore_area.py` 按地区+关键词挖掘未评级自然景区(需高德 key)。

## 图片辅助分析(模型无原生看图能力,用工具链替代)

截图/图片放到工作区后,可用以下脚本把内容"翻译"成文字:

```powershell
.venv\Scripts\python.exe scripts\decode_qr.py <图片路径>   # 二维码解码(opencv)
.venv\Scripts\python.exe scripts\ocr_cn.py <图片路径>      # 中文 OCR(RapidOCR,首次自动下模型)
powershell -File scripts\ocr.ps1 <图片路径>                # 英文 OCR(Windows 系统级)
```

## 环线与沿途挖掘

```powershell
# 1. 前端「环线」页:5 条精选环线(甘南/川西/青甘/滇西北/北疆),一键整条加入清单
#    → 清单切「自驾模式」→ 生成整条环线路线(最近邻/评分/反向 + DeepSeek 润色命名)

# 2. 沿路线自动挖掘沿途未收录景点(需 AMAP_KEY):
.venv\Scripts\python.exe scripts\explore_route.py 甘南环线              # 预览
.venv\Scripts\python.exe scripts\explore_route.py 甘南环线 --import     # 导入数据库

# 3. 按地区+关键词挖掘(草原/湖泊/峡谷...):
.venv\Scripts\python.exe scripts\explore_area.py 甘南藏族自治州 --kw 草原,湖泊
```

## 测试

```powershell
.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.venv\Scripts\python.exe -m pytest backend/tests # 管线/LLM/API/PDF 集成测试
node scripts/test_workshop.cjs                   # 离线工作坊编辑与草稿测试
.venv\Scripts\python.exe scripts\smoke_test.py  # 端到端冒烟(需服务已启动)
.venv\Scripts\python.exe scripts\e2e_check.py   # 真实浏览器 e2e(需 chromium,见下)
```

- 测试使用独立数据库 `data/test_travel.db`,不影响正式数据。
- **Playwright/Chromium**(采集器与 e2e 用):沙箱内需 `PLAYWRIGHT_BROWSERS_PATH` 指向工作区,
  且安装/运行命令需更高权限(命名管道限制)。用户侧终端运行不受限:
  `playwright install chromium` 即可。

## 目录结构

```
backend/
  app/            # FastAPI 应用:路由、SQLite 模型、种子数据
  ai/             # AI 加工管线(核心):prompts / llm / pipeline
  collector/      # 小红书采集器(骨架,待账号就绪激活)
frontend/         # 纯静态页面:地图、口碑卡、清单、方案
scripts/          # 引导脚本(装依赖/下载静态资源)
data/             # SQLite 数据库(运行时生成)
```

## AI 加工管线(核心设计)

对每个景区的 N 篇笔记执行:
1. **攻略整合** — 提炼亮点、玩法、花费区间
2. **暗广打分** — 通篇溢美无细节 / 反复点名商家 / 只报喜不报忧 → 营销嫌疑
3. **避雷挖掘** — 只从避雷类笔记提取负面点,标注具体性(1-5)与可验证性(1-5)
4. **共识统计** — 同一负面点被 ≥2 个独立账号提到 → "共识差评",权重加倍
5. **尬黑过滤** — 具体性 <2 且可验证性 <2 的情绪发泄类负面点丢弃

**混合策略**:LLM 为主,确定性规则兜底——
- LLM 漏报共识差评时,用关键词规则自动补齐,核心特性不因模型波动丢失
- 方案数量不足 3 套时,用规则规划器补齐并如实标注来源

## 数据来源与合规

- 当前:内置示例数据(10 城 44 景区 + 标注 is_sample 的示例笔记,仅用于演示管线)
- 正式:小红书采集(需用户登录授权 cookie,低频小规模,见 `backend/collector/xhs_collector.py`)
- 本项目仅用于个人学习演示,不上线运营、不公开部署、不展示原始全文

## 路线图

- [x] 地图选点 / 景区列表 / 购物车 / mock AI 管线 / 多方案生成
- [x] 测试套件(管线/LLM 集成/API 集成,26 例)
- [x] 高德 POI 数据源(配置 AMAP_KEY 后运行 `scripts\fetch_poi.py`)
- [x] 小红书采集器完整实现(登录向导/搜索/详情/图片/限速/去重,待账号激活)
- [x] 路线距离校验(直线距离提示 / 亲子强度提示)
- [x] DeepSeek LLM 加工激活(真实口碑卡 + 方案生成,含混合兜底)
- [ ] 小红书采集激活(需要用户登录一次)
