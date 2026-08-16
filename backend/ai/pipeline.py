# -*- coding: utf-8 -*-
"""AI 内容加工管线:攻略整合 -> 暗广打分 -> 避雷挖掘 -> 共识统计。

- 配置了 DEEPSEEK_API_KEY 时走 LLM(backend/ai/prompts.py 的提示词);
- 未配置时走启发式 mock,保证无 key 也能完整演示全流程。
"""
from . import prompts
from .llm import LLMClient

_llm = LLMClient()

# ---- mock 启发式词表 ----
AD_KEYWORDS = ["绝了", "此生必去", "必去", "冲", "绝美", "天花板", "yyds", "必打卡",
               "不来后悔", "超值", "仙境", "窒息", "大片", "壁纸"]
AD_COMMERCE = ["链接", "主页", "团购", "私信", "微信", "找我", "摄影师", "民宿", "探店"]
CONCRETE_HINTS = ["元", "小时", "分钟", "排队", "门票", "地铁", "号线", "公里", "开放",
                  "闭馆", "预约", "停车", "人少", "人多", "免费", "安检", "限流", "清场"]
NEGATIVE_HINTS = ["但是", "不过", "缺点", "遗憾", "坑", "避雷", "别", "不要", "不值", "贵",
                  "差", "挤", "闭馆", "抢不到", "智商税", "不开放", "排队", "一般般", "错过"]
AVOID_WORDS = ["坑", "别", "避雷", "不要", "不值", "排队", "贵", "差", "闭馆", "抢不到",
               "智商税", "不开放", "挤", "限流", "清场", "收费", "禁行", "错过", "人多"]


def get_llm() -> LLMClient:
    return _llm


# ---------- mock 启发式实现 ----------

def _mock_ad_score(content: str) -> dict:
    text = content
    score = 0
    signals = []
    hits = [k for k in AD_KEYWORDS if k.lower() in text.lower()]
    if hits:
        score += min(40, len(hits) * 10)
        signals.append(f"溢美词命中: {'、'.join(hits[:4])}")
    commerce = [k for k in AD_COMMERCE if k.lower() in text.lower()]
    if commerce:
        score += 25
        signals.append(f"引流/带货词: {'、'.join(commerce[:3])}")
    concrete = sum(1 for k in CONCRETE_HINTS if k in text)
    if concrete < 2:
        score += 25
        signals.append("缺少具体细节(数字/时间/地点)")
    if any(k in text for k in NEGATIVE_HINTS):
        score -= 20
        signals.append("含负面/中立信息,广告嫌疑下调")
    return {"score": max(0, min(100, score)), "signals": signals[:3]}


def _mock_avoid_points(content: str) -> list:
    pts = []
    for sent in content.replace("。", "\n").replace("!", "\n").replace("！", "\n").split("\n"):
        s = sent.strip()
        if len(s) < 4 or not any(k in s for k in AVOID_WORDS):
            continue
        specificity = 0
        if any(ch.isdigit() for ch in s):
            specificity += 2
        if any(k in s for k in ["元", "小时", "分钟", "公里", "排队", "门票", "闭馆", "预约", "限流", "收费"]):
            specificity += 2
        if len(s) >= 15:
            specificity += 1
        pts.append({"point": s[:60], "specificity": min(5, specificity)})
    return pts


def mock_summarize(spot_name: str, notes: list) -> dict:
    guide_notes = [n for n in notes if n.get("note_type") in ("guide", "mixed")]
    texts = [n.get("content", "") for n in notes]

    ad_scores = [_mock_ad_score(t) for t in texts]
    ad_ratio = round(sum(s["score"] for s in ad_scores) / (len(ad_scores) * 100), 2) if ad_scores else 0.0
    ad_signals = [sig for s in ad_scores for sig in s["signals"]][:5]

    pts = []
    for n in notes:
        for p in _mock_avoid_points(n.get("content", "")):
            pts.append({**p, "evidence": n.get("title", ""), "verifiable": min(5, p["specificity"] + 1)})
    # 与 LLM 规则一致:空洞情绪发泄(具体性<2 且可验证性<2)不进入候选
    pts = [p for p in pts if not (p["specificity"] < 2 and p["verifiable"] < 2)]

    # 关键词级共识:同一负面关键词被 >=2 个独立账号提到 -> 共识差评
    kw_authors = {}
    kw_best = {}
    for n in notes:
        author = n.get("author_hash") or "?"
        for p in _mock_avoid_points(n.get("content", "")):
            for kw in AVOID_WORDS:
                if kw in p["point"]:
                    kw_authors.setdefault(kw, set()).add(author)
                    if p["specificity"] > kw_best.get(kw, {}).get("specificity", -1):
                        kw_best[kw] = {**p, "evidence": n.get("title", ""),
                                       "verifiable": min(5, p["specificity"] + 1)}
    consensus = []
    seen_cons = set()
    for kw, authors in kw_authors.items():
        if len(authors) >= 2:
            b = kw_best[kw]
            key = b["point"][:12]
            if key in seen_cons:
                continue  # 同一负面点被多个关键词命中,只记一次
            seen_cons.add(key)
            consensus.append({**b, "consensus": True, "mentions": len(authors)})
    consensus.sort(key=lambda x: -x["mentions"])

    # 非共识点:具体性最高的前 3,与共识差评去重
    consensus_keys = {c["point"][:12] for c in consensus}
    seen = set()
    others = []
    for p in sorted(pts, key=lambda x: -x["specificity"]):
        key = p["point"][:12]
        if key in seen or key in consensus_keys:
            continue
        seen.add(key)
        others.append({**p, "consensus": False, "mentions": 1})
        if len(others) >= 3:
            break

    trust = max(10, 100 - int(ad_ratio * 100) - len(consensus) * 8 - len(others) * 3)
    return {
        "highlights": [n["title"] for n in guide_notes[:3]] or ["暂无攻略数据"],
        "play_style": ["参考示例攻略,接入真实采集后由 LLM 提炼"],
        "cost_range": "待采集",
        "ad_ratio": ad_ratio,
        "ad_signals": ad_signals,
        "avoid_points": consensus + others,
        "consensus_issues": [c["point"] for c in consensus],
        "trust_score": trust,
        "source": "示例数据(启发式 mock)",
        "note_count": len(notes),
    }


# ---------- LLM 路径 ----------

def llm_summarize(spot_name: str, notes: list) -> dict:
    lines = []
    for i, n in enumerate(notes, 1):
        body = (n.get("content") or "").replace("\n", " ")[:1500]
        lines.append(f"[{i}] 类型:{n.get('note_type', 'guide')} | 标题:{n.get('title', '')}\n正文:{body}")
    user = prompts.ANALYZE_USER.format(spot=spot_name, notes="\n\n".join(lines))
    return _llm.chat_json(prompts.ANALYZE_SYSTEM, user, temperature=0.3)


def _merge_consensus_fallback(out: dict, spot_name: str, notes: list) -> None:
    """LLM 漏报共识差评时,用确定性关键词规则兜底(混合策略):
    保证"共识差评"这一核心特性不因 LLM 输出波动而丢失。"""
    if out.get("consensus_issues"):
        return
    fb = mock_summarize(spot_name, notes)
    out["consensus_issues"] = fb["consensus_issues"]
    existing = {p.get("point") for p in out.get("avoid_points", [])}
    for p in fb.get("avoid_points", []):
        if p.get("consensus") and p.get("point") not in existing:
            out.setdefault("avoid_points", []).append(p)


def summarize_spot(spot_name: str, notes: list) -> dict:
    """统一入口:LLM 优先(带共识兜底),失败或未配置 key 时退回 mock。"""
    if _llm.available and notes:
        try:
            out = llm_summarize(spot_name, notes)
            _merge_consensus_fallback(out, spot_name, notes)
            out["source"] = f"DeepSeek({len(notes)} 篇笔记)"
            out["note_count"] = len(notes)
            return out
        except Exception as e:  # 任何 LLM 错误都退回 mock,保证演示不中断
            out = mock_summarize(spot_name, notes)
            out["source"] = f"示例数据(启发式 mock;LLM 失败: {type(e).__name__})"
            return out
    return mock_summarize(spot_name, notes)
