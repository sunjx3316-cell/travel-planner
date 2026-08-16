---
name: summarize-reviews
description: 把原始旅游攻略/点评文本总结成结构化口碑卡(亮点/玩法/花费/暗广识别/避雷共识/信任度)。支持任意来源文本(小红书/马蜂窝/携程/应用内评价),可选接入 DeepSeek 提炼,无 key 时用启发式规则兜底。
when_to_use: 需要把一堆游记/评价/点评文本提炼成"这个景点到底怎么样、有什么坑、值不值得去"的结构化结论时;或为旅行规划应用生成景点口碑数据时。
---

# 总结攻略（summarize-reviews）

## 技能目标

输入**原始攻略/点评文本**（一条或多条，任意来源），输出**结构化口碑卡 JSON**：
亮点、典型玩法、花费区间、暗广信号、避雷点、共识差评、信任度评分。

## 工作流（按此顺序执行）

1. **收集**：获取该景点的多条原始文本（网页复制/接口返回/用户提交均可）。
2. **切分与分类**：每条文本按 `[avoid]`/`[guide]`/`[mixed]` 前缀或自动词表分类：
   - 有避雷词（坑/别/不要/排队/贵/差/闭馆/限流…）→ `avoid`
   - 同时有攻略意图（攻略/推荐/路线/怎么去/门票/建议…）→ `mixed`
   - 否则 → `guide`
3. **暗广检测**（重点，防营销号）：
   - 溢美词（绝了/此生必去/必去/天花板/绝美/不来后悔…）命中多 → 广告嫌疑高
   - 引流/带货词（链接/主页/私信/微信/找我/团购/探店…）→ 广告嫌疑高
   - 缺少具体细节（无数字/时间/地点/价格）→ 广告嫌疑高
   - 含负面/中立信息 → 嫌疑下调
4. **避雷挖掘**：拆句找含避雷词的句子，标注**具体性**（有数字/时间/价格/排队等=高）与**可验证性**（"周一闭馆""门票另收费"这类可核实=高）；空洞情绪发泄（"太差""再也不来"）丢弃。
5. **共识差评**：同一负面关键词被 **≥2 个独立作者**提到 → 共识差评（最高优先级，多来源交叉验证）。
6. **信任度 0-100**：综合数据可信度、暗广占比、负面点具体性、是否有共识差评。
7. **可选 DeepSeek 提炼**：配置 `DEEPSEEK_API_KEY` 时走 LLM 生成更自然的表述；失败或无 key 时用规则结果兜底。

## 输出格式（JSON）

```json
{
  "spot": "景点名",
  "highlights": ["亮点 3-5 条"],
  "play_style": ["典型玩法 2-4 条"],
  "cost_range": "花费区间描述",
  "ad_ratio": 0.0,
  "ad_signals": ["暗广信号"],
  "avoid_points": [{"point": "负面点", "evidence": "来源", "specificity": 1-5, "verifiable": 1-5}],
  "consensus_issues": ["被 2+ 独立账号提到的共识差评"],
  "trust_score": 0
}
```

## 使用方式

### 方式 A：直接运行技能脚本（最快）

```powershell
# 每条文本一行(或空行分隔);支持 [avoid] 前缀 和 `标题 | 内容`
python skills/summarize-reviews/summarize.py --spot 故宫 < notes.txt
python skills/summarize-reviews/summarize.py -f notes.txt
echo "排队2小时门票60,值得但人多" | python skills/summarize-reviews/summarize.py --spot 玉龙雪山
```

### 方式 B：接入旅行智规应用（落库 + 自动重算口碑卡）

```powershell
.venv\Scripts\python.exe scripts\import_reviews.py --spot 故宫 --file notes.txt
# 或 POST /api/spots/{id}/reviews  {"content": "..."}
```

应用侧框架：`backend/collector/review_source.py`（标准 item 结构 + 去重 + 重算），
AI 管线：`backend/ai/pipeline.py` + `backend/ai/prompts.py`。

### 方式 C：作为 Agent 技能手动执行

按上面「工作流」步骤逐条处理文本，最后输出 JSON 卡片。注意：
- 必须区分"真实避雷"与"尬黑"（看具体性/可验证性）
- 必须识别暗广（溢美+引流+缺细节 = 高度怀疑）
- 共识差评 = 多来源交叉验证的负面点，最有价值
