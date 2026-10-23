#!/usr/bin/env python3
"""把「标题＝机构名」的历史派生包标题改成「机构 · 角色」（默认 dry-run）。

背景：导入派生 package 时，校园/实习段的 entry 标题常常就是机构名（``示例大学``、
``杭州拓端数据科技有限公司``），UI 列表里看不出这段经历是什么。规则改成显示标题
``机构 · 角色``，原文保留在 ``evidence`` 里溯源（新导入已由
``import_service.derive_title_role`` 自动处理；本脚本只补历史行）。

安全约束：
* 默认 dry-run，只打印计划；
* ``--apply`` 前自动 ``sqlite3 backup`` 到 ``data/runtime/app.db.pre-titles-<ts>.db``；
* 只改 ``title`` 与 ``evidence``，不动 role/org/变体/时间线；
* 只处理 ``source='imported'`` 且 ``title == org`` 且 ``role`` 非空的行；
* ``--revert <snapshot>`` 从快照恢复（打印命令，不代跑）。
"""

from __future__ import annotations

import argparse
import datetime
import json
import sqlite3
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "server"))

import os  # noqa: E402

os.environ.setdefault("DATA_DIR", str(PROJECT / "data"))

from app import db as db_mod  # noqa: E402


def snapshot(conn: sqlite3.Connection, tag: str) -> Path:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = PROJECT / "data" / "runtime" / f"app.db.pre-titles-{stamp}-{tag}.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    out = sqlite3.connect(dest)
    with out:
        conn.backup(out)
    out.close()
    return dest


def plan(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, org, role, evidence_json FROM package"
        " WHERE deleted_at IS NULL AND source = 'imported'"
        "   AND org IS NOT NULL AND role IS NOT NULL AND role != '' AND title = org"
        " ORDER BY created_at"
    ).fetchall()
    items: list[dict] = []
    for row in rows:
        derived = f"{row['org']} · {row['role']}"
        evidence = json.loads(row["evidence_json"] or "[]")
        entry = {
            "kind": "raw_title",
            "value": row["title"],
            "derived": derived,
            "note": "标题与机构同名，显示用「机构 · 角色」，原值保留在此（repair_package_titles 补录）",
        }
        if not any(item.get("kind") == "raw_title" for item in evidence):
            evidence = [entry, *evidence]
        items.append({"id": row["id"], "title": row["title"], "role": row["role"], "derived": derived, "evidence": evidence})
    return items


def apply(conn: sqlite3.Connection, items: list[dict]) -> int:
    changed = 0
    now = db_mod.utcnow_iso()
    with db_mod.transaction(conn) as tx:
        for item in items:
            tx.execute(
                "UPDATE package SET title = ?, evidence_json = ?, updated_at = ? WHERE id = ?",
                (item["derived"], json.dumps(item["evidence"], ensure_ascii=False), now, item["id"]),
            )
            changed += 1
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description="把「标题＝机构名」的派生包标题改成「机构 · 角色」")
    ap.add_argument("--apply", action="store_true", help="真的写库（默认只 dry-run）")
    ap.add_argument("--json", action="store_true", help="输出结构化结果")
    args = ap.parse_args()

    conn = db_mod.get_conn()
    items = plan(conn)
    if not items:
        print("待处理 0 行：没有「标题＝机构名」的派生包。")
        return 0

    print(f"待处理 {len(items)} 行（dry-run={'否' if args.apply else '是'}）：")
    for item in items:
        print(f"  {item['id']}  「{item['title']}」→「{item['derived']}」")

    if not args.apply:
        print("这是 dry-run：加 --apply 才会写库（会先打快照）。")
        if args.json:
            print(json.dumps({"planned": items}, ensure_ascii=False, indent=2))
        return 0

    snap = snapshot(conn, "pre")
    print(f"快照：{snap}")
    changed = apply(conn, items)
    post = snapshot(conn, "post")
    print(f"已更新 {changed} 行；改后快照：{post}")
    print(f"回滚：cp '{snap}' '{PROJECT / 'data' / 'app.db'}'")
    if args.json:
        print(json.dumps({"changed": changed, "snapshot": str(snap), "items": items}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
