#!/usr/bin/env python3
"""把「已提交但丢了静态内容」的模板补齐，并从用户自己的简历草稿回填档案。

背景（t8 实测）：commit 早期版本只把 header/entry 的槽位写进模板，**没有写
``template_block.static_text``**，也没有把学历/专业/届别/城市/技能行回填档案。
结果：用户导入自己的简历、提交成功后，导出的 PDF 里教育段只剩校名一行、
技能段整段消失（``SKILLS_EMPTY``）。

本脚本只做两件事，全是**从用户自己已提交的导入草稿里读出来的值**，不猜不编：

1. 给已提交模板的块补 ``static_text``：教育 entry 的 facts（GPA/CET/主修课程）、
   skills 块的逐行原文；
2. 回填 ``user_profile``：degree / major / grad_year / city / skills，
   以及按语言分开的 ``extra.available_note_zh`` / ``extra.available_note_en``，
   并写 ``extra.profile_field_sources`` 记录每个值的来源 import_job。

默认 dry-run；``--apply`` 才写库（写前自动打快照到 data/runtime/）。

用法::

    python3 server/scripts/backfill_template_static.py                # 只看
    python3 server/scripts/backfill_template_static.py --apply        # 落库
    python3 server/scripts/backfill_template_static.py --apply --snapshot
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db as db_mod  # noqa: E402
from app.repos import ImportRepo, ProfileRepo, TemplateRepo  # noqa: E402
from app.services import import_service  # noqa: E402


def _child_map(blocks: list[Mapping[str, Any]]) -> dict[str | None, list[Mapping[str, Any]]]:
    out: dict[str | None, list[Mapping[str, Any]]] = {}
    for block in blocks:
        out.setdefault(block.get("parent_temp_id") or block.get("parent_block_id"), []).append(block)
    for key, items in out.items():
        items.sort(key=lambda item: int(item.get("order_index") or 0))
    return out


def _texts_for_template(draft: Mapping[str, Any]) -> dict[tuple[str, int], str | None]:
    """按 (块类型, order_index) 算出每条静态文本，键与模板块一一对应。"""
    blocks = list(draft.get("blocks") or [])
    by_temp = {str(block["temp_id"]): block for block in blocks}
    out: dict[tuple[str, int], str | None] = {}
    for block in blocks:
        text = import_service._static_text_for(block, by_temp)
        if text:
            out[(str(block.get("block_type") or ""), int(block.get("order_index") or 0))] = text
    return out


def plan_template(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, result_template_id, draft_json FROM import_job "
        "WHERE result_template_id IS NOT NULL AND deleted_at IS NULL ORDER BY created_at DESC"
    ).fetchall()
    template_repo = TemplateRepo(conn)
    plan: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        template_id = row["result_template_id"]
        if not template_id or template_id in seen:
            continue
        seen.add(template_id)
        template = template_repo.get(template_id)
        if template is None:
            continue
        draft = db_mod.loads_json(row["draft_json"], {})
        texts = _texts_for_template(draft)
        updates: list[dict[str, Any]] = []
        for block in template.get("blocks") or []:
            key = (str(block.get("block_type") or ""), int(block.get("order_index") or 0))
            text = texts.get(key)
            if text and not (block.get("static_text") or "").strip():
                updates.append(
                    {
                        "block_id": block["id"],
                        "block_type": block["block_type"],
                        "order_index": block["order_index"],
                        "static_text": text,
                    }
                )
        if updates:
            plan.append(
                {
                    "template_id": template_id,
                    "template_name": template.get("name"),
                    "lang": template.get("lang"),
                    "import_id": row["id"],
                    "blocks": updates,
                }
            )
    return plan


def plan_profile(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT id, draft_json FROM import_job "
        "WHERE status = 'committed' AND deleted_at IS NULL ORDER BY created_at DESC"
    ).fetchall()
    picked: dict[str, sqlite3.Row] = {}
    for row in rows:
        lang = str((db_mod.loads_json(row["draft_json"], {}) or {}).get("lang") or "")
        if lang and lang not in picked:
            picked[lang] = row
    profile = ProfileRepo(conn).get() or {}
    patch: dict[str, Any] = {}
    sources: dict[str, str] = {}
    available: dict[str, str] = {}
    for lang, row in picked.items():
        draft = db_mod.loads_json(row["draft_json"], {})
        by_temp = {str(block["temp_id"]): block for block in draft.get("blocks") or []}
        derived = import_service._profile_from_draft(draft, by_temp, row["id"])
        for field, value in derived["fields"].items():
            current = profile.get(field)
            if field == "skills":
                if not current:
                    patch["skills"] = value
                    sources["skills"] = derived["sources"].get("skills", f"import:{row['id']}")
                continue
            if current in (None, "", 0):
                patch[field] = value
                sources[field] = derived["sources"].get(field, f"import:{row['id']}")
        available.update(derived["available"])
    if available:
        extra = dict(profile.get("extra") or {})
        for lang, value in available.items():
            key = f"available_note_{lang}"
            if not extra.get(key):
                extra[key] = value
        if sources:
            extra["profile_field_sources"] = {**sources, **dict(extra.get("profile_field_sources") or {})}
            extra["profile_fields_source"] = "import:backfill"
        patch["extra"] = extra
    return {"patch": patch, "sources": sources, "available": available}


def _snapshot(conn: sqlite3.Connection, label: str) -> Path:
    paths = db_mod.get_paths()
    target_dir = Path(paths.root) / "runtime"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"app.db.{label}.db"
    dest = sqlite3.connect(str(target))
    with dest:
        conn.backup(dest)
    dest.close()
    return target


def apply_plan(conn: sqlite3.Connection, templates: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
    updated_blocks = 0
    with db_mod.transaction(conn) as tx:
        for item in templates:
            for block in item["blocks"]:
                tx.execute(
                    "UPDATE template_block SET static_text = ?, updated_at = ? WHERE id = ?",
                    [block["static_text"], db_mod.utcnow_iso(), block["block_id"]],
                )
                updated_blocks += 1
    if profile["patch"]:
        ProfileRepo(conn).upsert(profile["patch"])
    return {"blocks_updated": updated_blocks, "profile_fields": sorted(profile["patch"])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="补齐模板块静态文本并回填档案（默认 dry-run）")
    parser.add_argument("--apply", action="store_true", help="真正写库")
    parser.add_argument("--snapshot", action="store_true", help="写库前打快照（--apply 时自动）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    conn = db_mod.get_conn()
    templates = plan_template(conn)
    profile = plan_profile(conn)

    report = {
        "mode": "apply" if args.apply else "dry-run",
        "templates": [
            {
                "template_id": item["template_id"],
                "template_name": item["template_name"],
                "lang": item["lang"],
                "import_id": item["import_id"],
                "blocks": [
                    {
                        "block_type": block["block_type"],
                        "order_index": block["order_index"],
                        "chars": len(block["static_text"]),
                        "preview": block["static_text"].splitlines()[0][:60],
                    }
                    for block in item["blocks"]
                ],
            }
            for item in templates
        ],
        "profile_patch": profile["patch"],
        "available_by_lang": profile["available"],
    }

    if args.apply:
        snapshot = _snapshot(conn, f"pre-backfill-{db_mod.utcnow_iso().replace(':', '').replace('-', '')}")
        report["snapshot"] = str(snapshot)
        report["applied"] = apply_plan(conn, templates, profile)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"模式：{report['mode']}")
        if not templates:
            print("模板：无需补齐（没有已提交模板缺 static_text）")
        for item in report["templates"]:
            print(f"模板 {item['template_name']}（{item['lang']}，来自 {item['import_id']}）需补 {len(item['blocks'])} 块：")
            for block in item["blocks"]:
                print(f"  - {block['block_type']}#{block['order_index']} {block['chars']} 字：{block['preview']}")
        print(f"档案回填：{sorted(report['profile_patch']) or '无'}")
        if report["available_by_lang"]:
            print(f"到岗时间（按语言）：{report['available_by_lang']}")
        if args.apply:
            print(f"快照：{report['snapshot']}")
            print(f"已写：{report['applied']}")
        else:
            print("当前是 dry-run：加 --apply 才会写库。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
