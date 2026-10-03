"""Validate and import a poi-reviews-v1 ZIP. Back up the database before any write."""
import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.collector.curated_reviews import import_bundle, read_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    bundle = read_bundle(args.archive)
    digest = hashlib.sha256(args.archive.read_bytes()).hexdigest()
    if not args.db.is_file():
        parser.error("目标数据库不存在，拒绝创建空库")
    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        if not args.dry_run:
            backup = args.db.with_name(args.db.name + ".before-reviews-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".bak")
            with sqlite3.connect(backup) as destination:
                conn.backup(destination)
            print("Backup:", backup)
        report = import_bundle(conn, bundle, digest, args.dry_run)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "unmatched"}, ensure_ascii=False))
        print("Unmatched:", len(report["unmatched"]))
        for row in report["unmatched"][:20]:
            print(row["city"], row["name"], row["reason"])
    finally:
        conn.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
