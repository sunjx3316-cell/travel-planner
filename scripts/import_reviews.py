# -*- coding: utf-8 -*-
"""评价数据导入工具(配合 backend/collector/review_source.py 框架)。

用法:
    # 1. 手工粘贴一条(最常用;任意来源文本都行,自动分类攻略/避雷)
    python scripts/import_reviews.py --spot 故宫 --source mafengwo --text "排队2小时门票60,值得但人多"

    # 2. 批量文件(每行一条;支持 `[avoid]` / `[guide]` 前缀 或 `标题 | 内容` 格式)
    python scripts/import_reviews.py --spot 玉龙雪山 --file reviews.txt

    # 3. 指定类型与来源
    python scripts/import_reviews.py --spot 兵马俑 --type avoid --source ctrip --text "缆车排队3小时,坑"

    # 4. 看看哪些景点还没有真实笔记(供采集)
    python scripts/import_reviews.py --missing

    # 5. 列出内置来源说明
    python scripts/import_reviews.py --list-sources
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from backend.app.db import get_conn  # noqa: E402
from backend.collector import review_source  # noqa: E402


def _find_spot(name: str):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT s.id, s.name, c.name AS city_name FROM spots s "
            "JOIN cities c ON c.id = s.city_id WHERE s.name=? LIMIT 1", (name,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        print(f"✗ 找不到景点: {name}(可先在地图/城市页加入该城景点,或用 --missing 看现有景点)")
        sys.exit(1)
    return row


def _parse_file(path: Path) -> list:
    """解析批量文件:每行一条笔记。
    支持格式:
      [avoid] 内容
      标题 | 内容
      纯内容(自动分类)
    """
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
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
        items.append({"type": ntype, "title": title.strip(), "content": content.strip()})
    return items


def main() -> None:
    ap = argparse.ArgumentParser(description="评价数据导入(喂数据即出 AI 口碑卡)")
    ap.add_argument("--spot", help="景点名称(必填,导入时用)")
    ap.add_argument("--source", default="paste", help="来源: paste/amap/baidu/xhs/mafengwo/ctrip/dianping")
    ap.add_argument("--type", dest="ntype", default="", help="guide/avoid/mixed;留空自动分类")
    ap.add_argument("--text", help="单条正文")
    ap.add_argument("--title", default="", help="标题(可选)")
    ap.add_argument("--author", default="", help="作者昵称(可选,自动匿名化)")
    ap.add_argument("--url", default="", help="来源链接(可选,用于去重)")
    ap.add_argument("--score", type=float, help="官方评分(如 4.6),只更新聚合评分")
    ap.add_argument("--file", help="批量文件路径")
    ap.add_argument("--missing", action="store_true", help="列出还没有真实笔记的景点")
    ap.add_argument("--list-sources", action="store_true", help="列出内置来源说明")
    ap.add_argument("--dry-run", action="store_true", help="只解析不写库")
    args = ap.parse_args()

    if args.list_sources:
        print("内置来源:")
        for name, desc in review_source.SOURCE_GUIDE.items():
            print(f"  {name:<10} {desc}")
        return
    if args.missing:
        spots = review_source.list_missing()
        print(f"还没有真实笔记的景点({len(spots)} 个,前 30):")
        for s in spots:
            print(f"  {s['id']}  {s['name']} ({s['city']})")
        return
    if not args.spot:
        ap.error("--spot 必填")

    spot = _find_spot(args.spot)
    items = []
    if args.file:
        items = _parse_file(Path(args.file))
        print(f"解析文件 {args.file}: {len(items)} 条")
    elif args.text:
        items = [{"type": args.ntype, "title": args.title, "content": args.text,
                  "author": args.author, "url": args.url}]
    elif args.score is not None:
        items = [{"type": "guide", "title": f"{args.source}官方评分", "content": "",
                  "score": args.score}]
    else:
        ap.error("请提供 --text / --file / --score 之一")

    for it in items:
        it.setdefault("source", args.source)
        it.setdefault("type", args.ntype)
    if args.dry_run:
        print("dry-run,以下将入库:")
        for it in items:
            n = review_source.normalize_item(it)
            print(f"  [{n['type']}] {n['title'][:30]} | {n['content'][:60]}")
        return

    result = review_source.ingest_items(spot["id"], items)
    print(f"✓ {spot['name']}({spot['city_name']}): 新增笔记 {result['added']} 条,"
          f"评分更新 {result['scores']} 处,口碑卡{'已重算' if result['summary'] else '未变'}")
    if result["added"]:
        print("  打开 http://127.0.0.1:8000 看该景点详情页即可看到新口碑卡")


if __name__ == "__main__":
    main()
