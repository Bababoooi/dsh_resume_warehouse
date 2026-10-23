#!/usr/bin/env python3
"""回填 ``package.source_import_job_id`` / ``source_entry_temp_id``（schema v8 之前创建的行）。

背景：schema v8 给 ``package`` 加了溯源两列，但 v8 之前由 ``POST /imports/{id}/commit``
派生出来的包只有 ``tags=['import:<job>','entry:<temp>']``。契约 I12 的幂等键
``UNIQUE(source_import_job_id, source_entry_temp_id)`` 要有真值才有意义，所以这里把
标签里的历史信息搬进列。

默认 dry-run；``--apply`` 才写库，写前自动存快照到 ``data/runtime/app.db.pre-provenance-<ts>.db``，
并在 ``--report`` 指定的 markdown 里留下「哪几行填上了、依据是什么」。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
from datetime import datetime
from typing import Any

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "server"))

from app import db as db_mod  # noqa: E402


def _loads(raw: Any) -> Any:
    if raw in (None, ""):
        return None
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _entry_ids(draft: Any) -> set[str]:
    """草稿里所有 entry 块的 temp_id（以及父块的 temp_id）。"""
    ids: set[str] = set()
    for block in (draft or {}).get("blocks") or []:
        if not isinstance(block, dict):
            continue
        temp = str(block.get("temp_id") or "")
        if not temp:
            continue
        ids.add(temp)
    return ids


def plan(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    """算出「能填」「需人工」两类。

    判据只有一条：包上带着 ``import:<job>`` 与 ``entry:<temp>`` 两个标签，且该 job 的草稿里
    真的存在这个 ``temp``。两个条件都成立才写；否则交给人工，不猜。
    """
    drafts: dict[str, set[str]] = {}
    for row in conn.execute(
        "SELECT id, draft_json FROM import_job WHERE deleted_at IS NULL"
    ).fetchall():
        drafts[str(row["id"])] = _entry_ids(_loads(row["draft_json"]))

    fillable: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    done: list[dict[str, Any]] = []

    # 只处理活跃行：软删的重复包不写溯源（它们不参与组装，写了只是噪声），单独计数
    rows = conn.execute(
        "SELECT id, title, tags_json, source_import_job_id, source_entry_temp_id, deleted_at"
        " FROM package WHERE source = 'imported' ORDER BY created_at"
    ).fetchall()
    for row in rows:
        tags = [str(tag) for tag in (_loads(row["tags_json"]) or []) if str(tag)]
        job_tags = [tag.split(":", 1)[1] for tag in tags if tag.startswith("import:")]
        entry_tags = [tag.split(":", 1)[1] for tag in tags if tag.startswith("entry:")]
        record = {
            "id": str(row["id"]),
            "title": str(row["title"]),
            "current": {
                "source_import_job_id": row["source_import_job_id"],
                "source_entry_temp_id": row["source_entry_temp_id"],
            },
            "tags_job": job_tags,
            "tags_entry": entry_tags,
        }
        if row["deleted_at"]:
            record["reason"] = "已软删（重复派生包），不写溯源"
            manual.append(record)
            continue
        if row["source_import_job_id"] and row["source_entry_temp_id"]:
            done.append(record)
            continue
        if not job_tags or not entry_tags:
            record["reason"] = "标签里没有 import:/entry:，无法回溯来源"
            manual.append(record)
            continue
        candidates = [
            (job_id, temp)
            for job_id in job_tags
            for temp in entry_tags
            if temp in drafts.get(job_id, set())
        ]
        if not candidates:
            record["reason"] = "草稿里找不到该 entry（源导入可能已被清理）"
            manual.append(record)
            continue
        if len(candidates) > 1:
            record["reason"] = f"命中多条来源（{len(candidates)}），不猜"
            record["candidates"] = [{"source_import_job_id": j, "source_entry_temp_id": t} for j, t in candidates]
            manual.append(record)
            continue
        record["proposed"] = {
            "source_import_job_id": candidates[0][0],
            "source_entry_temp_id": candidates[0][1],
        }
        record["evidence"] = f"标签 import:{candidates[0][0]} + entry:{candidates[0][1]}，且该 job 草稿里存在此 entry"
        fillable.append(record)

    return {"fillable": fillable, "manual": manual, "already": done}


def snapshot(conn: sqlite3.Connection, label: str) -> pathlib.Path:
    target = PROJECT_ROOT / "data" / "runtime" / f"app.db.{label}-{datetime.now():%Y%m%d-%H%M%S}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = sqlite3.connect(str(target))
    try:
        conn.backup(backup)
    finally:
        backup.close()
    return target


def apply_fill(conn: sqlite3.Connection, items: list[dict[str, Any]]) -> int:
    written = 0
    with db_mod.transaction(conn) as tx:
        for item in items:
            proposed = item["proposed"]
            cur = tx.execute(
                "UPDATE package SET source_import_job_id = ?, source_entry_temp_id = ?, updated_at = ?"
                " WHERE id = ? AND (source_import_job_id IS NULL OR source_entry_temp_id IS NULL)",
                (
                    proposed["source_import_job_id"],
                    proposed["source_entry_temp_id"],
                    db_mod.utcnow_iso(),
                    item["id"],
                ),
            )
            written += max(0, cur.rowcount)
    return written


def render_markdown(result: dict[str, Any], *, written: int, dry_run: bool) -> str:
    lines = ["# 导入派生包溯源回填报告", ""]
    lines.append(f"- 模式：{'dry-run（未写库）' if dry_run else f'apply（写入 {written} 行）'}")
    live = len(result["fillable"]) + len(result["already"])
    lines.append(f"- 导入派生包总数：{len(result['fillable']) + len(result['manual']) + len(result['already'])}（其中活跃 {live}）")
    lines.append(f"- 已可填（本应回填）：{len(result['fillable'])} 行")
    lines.append(f"- 已是完整值：{len(result['already'])} 行")
    lines.append(f"- 需人工：{len(result['manual'])} 行")
    lines.append("")
    if result["fillable"]:
        lines += ["## 可回填明细", "", "| 包 ID | 标题 | import_job | entry temp | 依据 |", "| --- | --- | --- | --- | --- |"]
        for item in result["fillable"]:
            proposed = item["proposed"]
            lines.append(
                f"| `{item['id']}` | {item['title']} | `{proposed['source_import_job_id']}`"
                f" | `{proposed['source_entry_temp_id']}` | {item['evidence']} |"
            )
        lines.append("")
    if result["already"]:
        lines += ["## 已完整（无需处理）", "", "| 包 ID | 标题 | import_job | entry temp |", "| --- | --- | --- | --- |"]
        for item in result["already"]:
            cur = item["current"]
            lines.append(
                f"| `{item['id']}` | {item['title']} | `{cur['source_import_job_id']}` | `{cur['source_entry_temp_id']}` |"
            )
        lines.append("")
    if result["manual"]:
        lines += ["## 需人工核对", "", "| 包 ID | 标题 | 原因 |", "| --- | --- | --- |"]
        for item in result["manual"]:
            lines.append(f"| `{item['id']}` | {item['title']} | {item['reason']} |")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="回填 package 的导入溯源两列")
    parser.add_argument("--apply", action="store_true", help="真正写库（默认 dry-run）")
    parser.add_argument("--report", type=pathlib.Path, help="输出 markdown 报告路径")
    parser.add_argument("--json", action="store_true", help="把结构化计划打到 stdout")
    args = parser.parse_args(argv)

    paths = db_mod.get_paths()
    paths.ensure()
    conn = db_mod.get_conn()
    result = plan(conn)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    written = 0
    if args.apply and result["fillable"]:
        pre = snapshot(conn, "pre-provenance")
        print(f"快照：{pre}")
        written = apply_fill(conn, result["fillable"])
        post = snapshot(conn, "post-provenance")
        print(f"写后快照：{post}")
        print(f"回填 {written} 行")

    markdown = render_markdown(result, written=written, dry_run=not args.apply)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(markdown, encoding="utf-8")
        print(f"报告：{args.report}")
    if not args.json:
        print(markdown)

    if not args.apply:
        print("当前是 dry-run：加 --apply 才会写库（会先打快照）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
