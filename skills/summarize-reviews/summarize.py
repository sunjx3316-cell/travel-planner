# -*- coding: utf-8 -*-
"""总结攻略技能:原始攻略/点评文本 → 结构化口碑卡 JSON。

用法:
    python summarize.py --spot 故宫 < notes.txt      # 每条一行/空行分隔
    python summarize.py --spot 玉龙雪山 -f notes.txt
    echo "排队2小时门票60,值得但人多" | python summarize.py --spot 玉龙雪山
    python summarize.py --spot 故宫 -n "标题 | 内容"  # 单条带标题

可选: 设置环境变量 DEEPSEEK_API_KEY 走 LLM 提炼;否则用启发式规则(同样可靠)。
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---------- 词表(与项目 backend/ai/pipeline.py 一致) ----------
AD_KEYWORDS = ["绝了", "此生必去", "必去", "冲", "绝美", "天花板", "yyds", "必打卡",
               "不来后悔", "超值", "仙境", "窒息", "大片", "壁纸"]
AD_COMMERCE = ["链接", "主页", "团购", "私信", "微信", "找我", "摄影师", "民宿", "探店"]
CONCRETE_HINTS = ["元", "小时", "分钟", "排队", "门票", "地铁", "号线", "公里", "开放",
                  "闭馆", "预约", "停车", "人少", "人多", "免费", "安检", "限流", "清场"]
AVOID_WORDS = ["坑", "别", "避雷", "不要", "不值", "排队", "贵", "差", "闭馆", "抢不到",
               "智商税", "不开放", "挤", "限流", "清场", "收费", "禁行", "错过", "人多"]
GUIDE_WORDS = ["攻略", "推荐", "路线", "怎么去", "行程", "游玩", "建议", "提醒",
               "开放时间", "交通", "门票"]


def classify(content: str, title: str = "") -> str:
    text = f"{title} {content}"
    neg = sum(1 for k in AVOID_WORDS if k in text)
    guide = sum(1 for k in GUIDE_WORDS if k in text)
    if neg >= 1 and guide >= 1:
        return "mixed"
    if neg >= 1:
        return "avoid"
    return "guide"


def parse_input(text: str) -> list:
    """切分输入为多条笔记。每条支持 [avoid]/[guide]/[mixed] 前缀 或 `标题 | 内容`。"""
    items = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        ntype = ""
        if line.startswith("[") and "]" in line:
            tag, line = line.split("]", 1)
            ntype = tag[1:].strip()
            line = line.strip()
        title, content = "", line
        if " | " in line:
            title, content = line.split(" | ", 1)
        items.append({"type": ntype or classify(content, title), "title": title.strip(),
                      "content": content.strip()})
    return items


def ad_score(content: str) -> dict:
    score = 0
    signals = []
    hits = [k for k in AD_KEYWORDS if k.lower() in content.lower()]
    if hits:
        score += min(40, len(hits) * 10)
        signals.append(f"溢美词命中: {'、'.join(hits[:4])}")
    commerce = [k for k in AD_COMMERCE if k.lower() in content.lower()]
    if commerce:
        score += 25
        signals.append(f"引流/带货词: {'、'.join(commerce[:3])}")
    concrete = sum(1 for k in CONCRETE_HINTS if k in content)
    if concrete < 2:
        score += 25
        signals.append("缺少具体细节(数字/时间/地点)")
    if any(k in content for k in ["但是", "不过", "缺点", "遗憾", "避雷", "别", "不要", "不值", "贵", "差", "挤", "排队"]):
        score -= 20
        signals.append("含负面/中立信息,广告嫌疑下调")
    return {"score": max(0, min(100, score)), "signals": signals[:3]}


def avoid_points(content: str) -> list:
    pts = []
    for sent in re.split(r"[。!！\n]", content):
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


def summarize_rule(spot: str, items: list) -> dict:
    texts = [it["content"] for it in items]
    ad_scores = [ad_score(t) for t in texts]
    ad_ratio = round(sum(s["score"] for s in ad_scores) / (len(ad_scores) * 100), 2) if ad_scores else 0.0
    ad_signals = [sig for s in ad_scores for sig in s["signals"]][:5]

    pts = []
    for it in items:
        for p in avoid_points(it["content"]):
            pts.append({**p, "evidence": it["title"] or "来源1", "verifiable": min(5, p["specificity"] + 1)})
    pts = [p for p in pts if not (p["specificity"] < 2 and p["verifiable"] < 2)]

    # 共识差评:同一负面词 ≥2 个独立作者
    kw_authors, kw_best = {}, {}
    for i, it in enumerate(items):
        author = f"作者{i + 1}"
        for p in avoid_points(it["content"]):
            for kw in AVOID_WORDS:
                if kw in p["point"]:
                    kw_authors.setdefault(kw, set()).add(author)
                    if p["specificity"] > kw_best.get(kw, {}).get("specificity", -1):
                        kw_best[kw] = {**p, "evidence": it["title"] or f"来源{i + 1}",
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

    consensus_keys = {c["point"][:12] for c in consensus}
    seen, others = set(), []
    for p in sorted(pts, key=lambda x: -x["specificity"]):
        key = p["point"][:12]
        if key in seen or key in consensus_keys:
            continue
        seen.add(key)
        others.append({**p, "consensus": False, "mentions": 1})
        if len(others) >= 3:
            break

    guides = [it for it in items if it["type"] in ("guide", "mixed")]
    trust = max(10, 100 - int(ad_ratio * 100) - len(consensus) * 8 - len(others) * 3)
    return {
        "spot": spot,
        "highlights": [it["title"] or it["content"][:20] for it in guides[:3]] or ["暂无攻略数据"],
        "play_style": ["由 DeepSeek 提炼" if os.environ.get("DEEPSEEK_API_KEY") else "按攻略文本归纳"],
        "cost_range": "待统计",
        "ad_ratio": ad_ratio,
        "ad_signals": ad_signals,
        "avoid_points": consensus + others,
        "consensus_issues": [c["point"] for c in consensus],
        "trust_score": trust,
        "note_count": len(items),
        "source": "启发式规则",
    }


def summarize_llm(spot: str, items: list) -> dict:
    """DeepSeek 提炼(失败自动回退规则)。"""
    import requests

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return summarize_rule(spot, items)
    lines = []
    for i, it in enumerate(items, 1):
        body = it["content"].replace("\n", " ")[:1500]
        lines.append(f"[{i}] 类型:{it['type']} | 标题:{it['title']}\n正文:{body}")
    system = ("你是一名旅行口碑分析员。警惕暗广(通篇溢美/缺细节/带引流词),"
              "区分真实避雷与尬黑(看具体性/可验证性),输出 JSON。")
    user = f"""景点:{spot}
以下是小×书等来源的 {len(items)} 篇笔记:
{chr(10).join(lines)}
请输出 JSON:
{{
  "highlights": ["亮点3-5条"],
  "play_style": ["典型玩法2-4条"],
  "cost_range": "花费区间",
  "ad_ratio": 0.0,
  "ad_signals": ["暗广信号"],
  "avoid_points": [{{"point":"负面点","evidence":"来源","specificity":1-5,"verifiable":1-5}}],
  "consensus_issues": ["被2+独立账号提到的共识差评,没有给[]"],
  "trust_score": 0
}}
要求:空洞情绪发泄不进 avoid_points;trust_score 综合可信度/暗广/负面具体性/共识。"""
    try:
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}],
                "temperature": 0.3, "response_format": {"type": "json_object"}},
            timeout=60)
        out = resp.json()["choices"][0]["message"]["content"]
        card = json.loads(out)
        card["spot"] = spot
        card["note_count"] = len(items)
        card["source"] = "DeepSeek"
        # 共识差评兜底:LLM 漏报时用规则补
        if not card.get("consensus_issues"):
            fb = summarize_rule(spot, items)
            card["consensus_issues"] = fb["consensus_issues"]
            for p in fb.get("avoid_points", []):
                if p.get("consensus") and p.get("point") not in {x.get("point") for x in card.get("avoid_points", [])}:
                    card.setdefault("avoid_points", []).append(p)
        return card
    except Exception:
        return summarize_rule(spot, items)


def main() -> None:
    ap = argparse.ArgumentParser(description="总结攻略:原始文本 → 口碑卡 JSON")
    ap.add_argument("--spot", required=True, help="景点/目的地名称")
    ap.add_argument("-f", "--file", help="输入文件(缺省读 stdin)")
    ap.add_argument("-n", "--note", help="单条笔记(支持 `标题 | 内容`)")
    args = ap.parse_args()

    if args.note:
        text = args.note
    elif args.file:
        text = open(args.file, encoding="utf-8").read()
    else:
        text = sys.stdin.read()

    items = parse_input(text)
    if not items:
        print(json.dumps({"spot": args.spot, "error": "没有可解析的文本"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    card = summarize_llm(args.spot, items) if os.environ.get("DEEPSEEK_API_KEY") else summarize_rule(args.spot, items)
    print(json.dumps(card, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
