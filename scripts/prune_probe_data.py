#!/usr/bin/env python3
"""数据卫生体检 / 清理（captain P2/P3）——**默认 dry-run，只报告不动手**。

覆盖三类历史垃圾：

1. **重复导入草稿**：同一份源文件（``attachment.sha256``）被反复上传生成多条
   ``import_job``，每条都存了一份完整 ``draft_json``（真实简历在本机被存多份）。
   只保留每个 sha 最新的一条未提交草稿，其余列为候选。
2. **重复命名模板**：同名同语言的模板（探测时 commit 多次产生），保留最新一条。
3. **孤儿/游离照片**：委托 ``clean_orphan_photos.classify`` 判定，
   孤儿随 ``--delete`` 删除，游离候选需再加 ``--prune-detached``。

用法::

    python3 scripts/prune_probe_data.py                      # 只报告（默认）
    python3 scripts/prune_probe_data.py --delete              # 删重复草稿/模板 + 孤儿照片
    python3 scripts/prune_probe_data.py --delete --prune-detached
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
SCRIPTS_DIR = Path(__file__).resolve().parent
for extra in (SERVER_DIR, SCRIPTS_DIR):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from app import db as db_mod  # noqa: E402

OPEN_STATUSES = ("queued", "parsing", "draft")


def _draft_bytes(draft_json: str | None) -> int:
    return len(draft_json.encode("utf-8")) if draft_json else 0


def find_duplicate_drafts(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """同一源文件 sha 的多条未提交草稿：保留最新一条，其余（含字节数）列为候选。"""
    placeholders = ", ".join("?" for _ in OPEN_STATUSES)
    rows = conn.execute(
        "SELECT j.id, j.created_at, j.draft_json, a.sha256, a.original_name"
        " FROM import_job j JOIN attachment a ON a.id = j.attachment_id"
        f" WHERE j.status IN ({placeholders})"
        " AND j.deleted_at IS NULL"
        # 有产出的行（指向模板）绝不进硬删候选：溯源比「省磁盘」重要
        " AND j.result_template_id IS NULL"
        " ORDER BY j.created_at DESC",
        OPEN_STATUSES,
    ).fetchall()
    grouped: dict[str, list[Any]] = {}
    for row in rows:
        grouped.setdefault(str(row["sha256"]), []).append(row)
    duplicates: list[dict[str, Any]] = []
    for sha, items in grouped.items():
        for row in items[1:]:
            duplicates.append(
                {
                    "import_id": str(row["id"]),
                    "sha256": sha,
                    "original_name": row["original_name"],
                    "created_at": row["created_at"],
                    "bytes": _draft_bytes(row["draft_json"]),
                    "reason": f"同一份源文件已有更新的草稿（{items[0]['id']}）",
                }
            )
    return duplicates


def find_duplicate_templates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """同名同语言模板只留最新一条（探测 commit 产生的重名模板）。"""
    rows = conn.execute(
        "SELECT id, name, lang, updated_at FROM template WHERE deleted_at IS NULL"
        " ORDER BY updated_at DESC, created_at DESC"
    ).fetchall()
    seen: set[tuple[str, str]] = set()
    duplicates: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row["name"]), str(row["lang"]))
        if key in seen:
            duplicates.append(
                {
                    "template_id": str(row["id"]),
                    "name": row["name"],
                    "lang": row["lang"],
                    "updated_at": row["updated_at"],
                    "reason": "同名同语言已有更新模板",
                }
            )
        else:
            seen.add(key)
    return duplicates


def _load_photo_module():
    import importlib.util

    script = SCRIPTS_DIR / "clean_orphan_photos.py"
    spec = importlib.util.spec_from_file_location("clean_orphan_photos", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def is_provenance(row: Any) -> bool:
    """这一行是不是「有产出的证据」——**永远不许归档**。

    规则缺陷教训（真库 04:22 那次清理）：唯一活跃的默认模板「中文-单页-审」的来源
    ``import_job`` 比后来的重复 draft **更早**，只按「留最新」就被归档了，
    模板从此看不到自己是哪份简历生成的。因此 ``committed`` 或指向模板的行优先保留。
    """
    if isinstance(row, sqlite3.Row):
        status = str(row["status"] or "")
        template_id = row["result_template_id"]
    else:
        status = str(row.get("status") or "")
        template_id = row.get("result_template_id")
    return status == "committed" or bool(template_id)


def find_import_job_duplicates(
    conn: sqlite3.Connection,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按 draft_json 内容指纹给导入历史去重。

    返回 ``(archivable, kept)``。每组的保留优先级：

    1. ``status='committed'`` 或 ``result_template_id IS NOT NULL`` 的行 —— **全部保留**
       （模板来源/有产出的证据，溯源不能断）；
    2. 其余未提交草稿里按 ``created_at`` 留**最新**一条；
    3. 剩下的才进 ``archivable``。

    只动 ``deleted_at IS NULL`` 的行；archive 是软删，可 restore。
    """
    rows = conn.execute(
        "SELECT j.id, j.status, j.created_at, j.result_template_id, j.draft_json,"
        " a.original_name, a.sha256"
        " FROM import_job j LEFT JOIN attachment a ON a.id = j.attachment_id"
        " WHERE j.deleted_at IS NULL"
        " ORDER BY j.created_at DESC, j.id DESC"
    ).fetchall()
    groups: dict[tuple[str, str], list[sqlite3.Row]] = {}
    for row in rows:
        draft_json = row["draft_json"] or ""
        digest = hashlib.sha256(draft_json.encode("utf-8")).hexdigest()[:16]
        key = (str(row["sha256"] or ""), digest)
        groups.setdefault(key, []).append(row)

    archivable: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for group in groups.values():
        protected = [row for row in group if is_provenance(row)]
        rest = [row for row in group if not is_provenance(row)]
        survivors = list(protected)
        dropped: list[sqlite3.Row] = []
        if protected:
            # 组里已有「有产出的证据」：同指纹的纯草稿全是重复，全部可归档
            dropped.extend(rest)
        elif rest:
            survivors.append(rest[0])  # 已按 created_at DESC 排序，首条即最新
            dropped.extend(rest[1:])
        for row in dropped:
            draft_json = row["draft_json"] or ""
            archivable.append(
                {
                    "import_id": str(row["id"]),
                    "status": row["status"],
                    "result_template_id": row["result_template_id"],
                    "original_name": row["original_name"],
                    "created_at": row["created_at"],
                    "bytes": len(draft_json.encode("utf-8")),
                }
            )
        if len(group) > 1 and survivors:
            newest = max(survivors, key=lambda row: (str(row["created_at"] or ""), str(row["id"])))
            kept.append(
                {
                    "import_id": str(newest["id"]),
                    "status": newest["status"],
                    "result_template_id": newest["result_template_id"],
                    "original_name": newest["original_name"],
                    "created_at": newest["created_at"],
                    "duplicates_archived": len(group) - len(survivors),
                    "provenance_kept": [str(row["id"]) for row in protected],
                }
            )
    kept.sort(key=lambda item: item["created_at"] or "", reverse=True)
    archivable.sort(key=lambda item: item["created_at"] or "", reverse=True)
    return archivable, kept


def assert_no_live_template_provenance(
    conn: sqlite3.Connection, archivable: list[dict[str, Any]]
) -> None:
    """硬校验：任何待归档行若指向仍存活的模板 → 立即中止（防止再次切断溯源）。"""
    offenders: list[dict[str, Any]] = []
    for item in archivable:
        template_id = item.get("result_template_id")
        if not template_id:
            continue
        row = conn.execute(
            "SELECT id, name, deleted_at FROM template WHERE id = ?", (template_id,)
        ).fetchone()
        if row is not None and row["deleted_at"] is None:
            offenders.append(
                {"import_id": item["import_id"], "template_id": row["id"], "template_name": row["name"]}
            )
    if offenders:
        print("中止：以下待归档的导入记录仍是存活模板的来源，归档会切断溯源：", file=sys.stderr)
        for item in offenders:
            print(
                f"  import {item['import_id']} → 模板「{item['template_name']}」({item['template_id']})",
                file=sys.stderr,
            )
        raise SystemExit(1)


def report(
    paths: db_mod.Paths, conn: sqlite3.Connection, *, include_import_jobs: bool = False
) -> dict[str, Any]:
    duplicates = find_duplicate_drafts(conn)
    templates = find_duplicate_templates(conn)
    photos = _load_photo_module()
    orphans, detached = photos.classify(paths, conn)
    payload: dict[str, Any] = {
        "drafts": {
            "count": len(duplicates),
            "bytes": sum(item["bytes"] for item in duplicates),
            "items": duplicates,
        },
        "templates": {"count": len(templates), "items": templates},
        "photos": {
            "orphans": [str(p.relative_to(paths.root)) for p in orphans],
            "detached": [str(p.relative_to(paths.root)) for p in detached],
        },
    }
    if include_import_jobs:
        archivable, kept = find_import_job_duplicates(conn)
        assert_no_live_template_provenance(conn, archivable)
        payload["import_jobs"] = {
            "archivable": archivable,
            "kept": kept,
            "archivable_count": len(archivable),
            "kept_count": len(kept),
            "bytes": sum(item["bytes"] for item in archivable),
            "provenance_kept_count": sum(len(item["provenance_kept"]) for item in kept),
            "committed_archivable": sum(1 for item in archivable if item["status"] == "committed"),
        }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="列出/清理探测产生的重复数据与孤儿照片（默认 dry-run）")
    parser.add_argument("--delete", action="store_true", help="真的删除（默认只报告）")
    parser.add_argument("--prune-detached", action="store_true", help="连只被 attachment 登记的游离照片一起删")
    parser.add_argument(
        "--prune-import-jobs",
        action="store_true",
        help="按 draft_json 指纹给导入历史去重（保留每个源最新一条，软删其余）",
    )
    parser.add_argument("--data-dir", default=None, help="覆盖 DATA_DIR（默认读 .env）")
    parser.add_argument(
        "--delete-drafts",
        action="store_true",
        help="额外**硬删**重复的未提交草稿行（不可恢复；默认不删，只做可 restore 的软归档）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（给脚本/Skill 复用）")
    args = parser.parse_args(argv)

    paths = db_mod.get_paths()
    if args.data_dir:
        paths = db_mod.Paths(db_mod.resolve_data_root(args.data_dir))
    conn = db_mod.get_conn()
    try:
        result = report(paths, conn, include_import_jobs=args.prune_import_jobs)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            drafts = result["drafts"]
            print(f"== 重复导入草稿：{drafts['count']} 条，共 {drafts['bytes']} 字节 draft_json ==")
            for item in drafts["items"]:
                print(f"  {item['import_id']}  {item['original_name']}  {item['created_at']}  {item['bytes']} 字节")
            print(f"== 同名模板：{result['templates']['count']} 条 ==")
            for item in result["templates"]["items"]:
                print(f"  {item['template_id']}  {item['name']}（{item['lang']}）  {item['updated_at']}")
            print(f"== 孤儿照片：{len(result['photos']['orphans'])} 个；游离候选：{len(result['photos']['detached'])} 个 ==")
            for rel in result["photos"]["orphans"]:
                print(f"  孤儿 {rel}")
            for rel in result["photos"]["detached"]:
                print(f"  游离候选（--prune-detached 才删） {rel}")

        jobs = result.get("import_jobs")
        if jobs:
            print(
                f"== 导入历史去重：将归档 {jobs['archivable_count']} 行 / 保留 {jobs['kept_count']} 个不同结果"
                f"（其中 committed 来源保留 {jobs['provenance_kept_count']} 行、待归档里 committed "
                f"{jobs['committed_archivable']} 行；共 {jobs['bytes']} 字节 draft_json） =="
            )
            for item in jobs["kept"]:
                tags = ""
                if item.get("provenance_kept"):
                    tags = f"  [来源证据保留 {len(item['provenance_kept'])} 行]"
                print(
                    f"  保留 {item['import_id']}  {item['original_name']}  {item['created_at']}"
                    f"  （归档重复 {item['duplicates_archived']} 行）{tags}"
                )
            for item in jobs["archivable"][:10]:
                print(f"  归档 {item['import_id']}  {item['original_name']}  {item['created_at']}  {item['bytes']} 字节")
            if jobs["archivable_count"] > 10:
                print(f"  … 其余 {jobs['archivable_count'] - 10} 行略")

        if not args.delete:
            print("\n当前是 dry-run：加 --delete 才会真的清理。")
            return 0

        archived_jobs = [item["import_id"] for item in result.get("import_jobs", {}).get("archivable", [])]
        if archived_jobs:
            assert_no_live_template_provenance(conn, result["import_jobs"]["archivable"])
        # 硬删（不可恢复）必须显式加 --delete-drafts；--delete 只做可 restore 的软归档
        deleted_drafts = (
            [item["import_id"] for item in result["drafts"]["items"]] if args.delete_drafts else []
        )
        if result["drafts"]["items"] and not args.delete_drafts:
            print(
                f"\n提示：{len(result['drafts']['items'])} 条重复草稿未动（硬删不可恢复）；"
                "确认要删时再加 --delete-drafts。"
            )
        deleted_templates = [item["template_id"] for item in result["templates"]["items"]]
        with db_mod.transaction(conn) as tx:
            for import_id in deleted_drafts:
                tx.execute("DELETE FROM import_job WHERE id = ?", (import_id,))
            now = db_mod.utcnow_iso()
            for import_id in archived_jobs:
                tx.execute(
                    "UPDATE import_job SET deleted_at = ?, updated_at = ?"
                    " WHERE id = ? AND deleted_at IS NULL",
                    (now, now, import_id),
                )
            for template_id in deleted_templates:
                tx.execute(
                    "UPDATE template SET deleted_at = ?, updated_at = ? WHERE id = ?",
                    (db_mod.utcnow_iso(), db_mod.utcnow_iso(), template_id),
                )
        photos = _load_photo_module()
        orphan_paths = [paths.root / rel for rel in result["photos"]["orphans"]]
        detached_paths = [paths.root / rel for rel in result["photos"]["detached"]]
        removed = 0
        for path in orphan_paths + (detached_paths if args.prune_detached else []):
            if path.exists():
                path.unlink()
                removed += 1
        print(
            f"\n已清理：草稿 {len(deleted_drafts)}、导入历史 {len(archived_jobs)}（软删可恢复）、"
            f"模板 {len(deleted_templates)}（软删）、照片文件 {removed}"
        )
        return 0
    finally:
        db_mod.close_conn()


if __name__ == "__main__":
    raise SystemExit(main())
