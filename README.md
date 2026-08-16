# 旅行智规 Travel Planner

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
.venv\Scripts\python.exe -m pytest              # 91 个用例:管线/LLM 集成/API 集成测试
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
