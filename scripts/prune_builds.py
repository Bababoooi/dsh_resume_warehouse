#!/usr/bin/env python3
"""把「同一份内容反复导出」积下的重复构建**归档**（默认 dry-run，绝不硬删）。

    .venv/bin/python scripts/prune_builds.py                      # 看看会归档几条
    .venv/bin/python scripts/prune_builds.py --apply              # 真归档（写 archived_at）
    .venv/bin/python scripts/prune_builds.py --list-orphan-files  # 列出没人引用的产物文件

语义（t15 返工后）：

* **归档 ≠ 删除**：只写 `resume_build.archived_at`（schema v12），行、选题、产物记录
  全都保留；`GET /builds` 默认不显示归档记录，`?include_archived=1` 还能看回来。
* 判据保守：同一签名才算重复——签名 = (name, lang, template_id, position, company,
  所选经历包集合)；每个签名只留**最新一条**。
* `--ignore-name`：忽略构建名，只按内容签名判重（更激进，会归档改过名的历史导出）。
* `--hard-delete` 是**不可恢复**的物理删除，必须同时给 `--yes`，脚本会先打印影响面；
  它不会删磁盘文件。
* 本脚本**从不删除磁盘文件**；`--list-orphan-files` 只列出「`data/exports/` 里存在、
  但没有任何 `build_artifact` 记录」的文件（名字 + 大小 + mtime），是否真删由用户决定。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _db_path(data_dir: str | None) -> Path:
    if data_dir:
        return Path(data_dir).expanduser().resolve() / "app.db"
    return ROOT / "data" / "app.db"


def _now() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def _signature(conn: sqlite3.Connection, build: sqlite3.Row, *, ignore_name: bool = False) -> tuple[Any, ...]:
    rows = conn.execute(
        "SELECT package_id FROM build_selection WHERE build_id=? ORDER BY package_id",
        (build["id"],),
    ).fetchall()
    return (
        "" if ignore_name else build["name"],
        build["lang"],
        build["template_id"],
        build["position"] or "",
        build["company"] or "",
        tuple(row[0] for row in rows),
    )


def classify(
    conn: sqlite3.Connection, *, min_age_hours: float = 0.0, ignore_name: bool = False
) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    builds = conn.execute(
        "SELECT id, name, lang, template_id, position, company, status, created_at, archived_at "
        "FROM resume_build ORDER BY created_at DESC, id DESC"
    ).fetchall()
    groups: dict[tuple[Any, ...], list[sqlite3.Row]] = defaultdict(list)
    for build in builds:
        groups[_signature(conn, build, ignore_name=ignore_name)].append(build)

    keep: list[dict[str, Any]] = []
    drop: list[dict[str, Any]] = []
    cutoff = None
    if min_age_hours > 0:
        cutoff = _dt.datetime.now().astimezone() - _dt.timedelta(hours=min_age_hours)

    for signature, members in groups.items():
        members = sorted(members, key=lambda b: (b["created_at"], b["id"]), reverse=True)
        for index, build in enumerate(members):
            item = {
                "id": build["id"],
                "name": build["name"],
                "lang": build["lang"],
                "status": build["status"],
                "created_at": build["created_at"],
                "archived_at": build["archived_at"],
                "signature": {"name": signature[0], "lang": signature[1], "packages": len(signature[5])},
            }
            if index == 0:
                keep.append({**item, "reason": "newest_of_signature"})
                continue
            if cutoff is not None:
                try:
                    ts = _dt.datetime.fromisoformat(build["created_at"])
                except ValueError:
                    ts = None
                if ts is not None and ts > cutoff:
                    keep.append({**item, "reason": "too_new"})
                    continue
            drop.append({**item, "reason": "duplicate_of_newer"})
    return {
        "total": len(builds),
        "groups": len(groups),
        "keep": keep,
        "drop": drop,
        "already_archived": sum(1 for b in builds if b["archived_at"]),
    }


def archive(conn: sqlite3.Connection, drop_ids: list[str]) -> dict[str, int]:
    if not drop_ids:
        return {"archived": 0}
    marks = ",".join("?" for _ in drop_ids)
    stamp = _now()
    with conn:
        count = conn.execute(
            f"UPDATE resume_build SET archived_at=?, updated_at=? WHERE id IN ({marks}) AND archived_at IS NULL",
            (stamp, stamp, *drop_ids),
        ).rowcount
    return {"archived": count}


def hard_delete(conn: sqlite3.Connection, drop_ids: list[str]) -> dict[str, int]:
    """不可恢复：连产物行与选题行一起物理删除（磁盘文件不动）。"""
    if not drop_ids:
        return {"builds": 0, "artifacts": 0, "selections": 0}
    marks = ",".join("?" for _ in drop_ids)
    params = tuple(drop_ids)
    with conn:
        artifacts = conn.execute(
            f"DELETE FROM build_artifact WHERE build_id IN ({marks})", params
        ).rowcount
        selections = conn.execute(
            f"DELETE FROM build_selection WHERE build_id IN ({marks})", params
        ).rowcount
        builds = conn.execute(f"DELETE FROM resume_build WHERE id IN ({marks})", params).rowcount
    return {"builds": builds, "artifacts": artifacts, "selections": selections}


def orphan_files(conn: sqlite3.Connection, exports_dir: Path | None = None) -> list[dict[str, Any]]:
    """`data/exports/` 里有文件、但没有任何 build_artifact 指向它的那些（只列不删）。"""
    conn.row_factory = sqlite3.Row
    referenced = {str(row[0]) for row in conn.execute("SELECT rel_path FROM build_artifact").fetchall()}
    exports_dir = exports_dir or (ROOT / "data" / "exports")
    found: list[dict[str, Any]] = []
    if not exports_dir.is_dir():
        return found
    data_root = exports_dir.parent
    for path in sorted(exports_dir.glob("*.pdf")):
        rel = path.relative_to(data_root).as_posix()
        if rel in referenced:
            continue
        stat = path.stat()
        found.append(
            {
                "rel_path": rel,
                "file": path.name,
                "bytes": stat.st_size,
                "mtime": _dt.datetime.fromtimestamp(stat.st_mtime)
                .astimezone()
                .replace(microsecond=0)
                .isoformat(),
            }
        )
    return found


def _after_delete_unreferenced(conn: sqlite3.Connection, drop_ids: list[str]) -> dict[str, Any]:
    if not drop_ids:
        return {"unreferenced": [], "existing_on_disk": []}
    marks = ",".join("?" for _ in drop_ids)
    params = tuple(drop_ids)
    still = {
        str(row[0])
        for row in conn.execute(
            f"SELECT rel_path FROM build_artifact WHERE build_id NOT IN ({marks})", params
        ).fetchall()
    }
    gone = {
        str(row[0])
        for row in conn.execute(
            f"SELECT rel_path FROM build_artifact WHERE build_id IN ({marks})", params
        ).fetchall()
    }
    unreferenced = sorted(gone - still)
    return {
        "unreferenced": unreferenced,
        "existing_on_disk": [rel for rel in unreferenced if (ROOT / "data" / rel).exists()],
    }


def render(
    report: dict[str, Any],
    *,
    hard: bool,
    applied: dict[str, int] | None,
    orphans: list[dict[str, Any]] | None,
) -> str:
    verb = "删除" if hard else "归档"
    lines: list[str] = []
    if report.get("total"):
        lines.append(
            f"构建总数：{report['total']}　签名数：{report['groups']}　已归档：{report['already_archived']}　"
            f"保留：{len(report['keep'])}　重复待{verb}：{len(report['drop'])}"
        )
        for item in report["drop"][:20]:
            lines.append(
                f"  - {item['id']}  {item['name']}（{item['lang']}，{item['status']}，{item['created_at']}）"
            )
        if len(report["drop"]) > 20:
            lines.append(f"  … 另有 {len(report['drop']) - 20} 条同类记录")
        files = report.get("files") or {}
        if files.get("unreferenced"):
            lines.append(f"{verb}后不再被引用的产物记录：{len(files['unreferenced'])} 个（磁盘文件不会动）")
            for rel in files.get("existing_on_disk", [])[:10]:
                lines.append(f"  · data/{rel}")
    if orphans is not None:
        lines.append(f"磁盘上没有产物记录的 PDF：{len(orphans)} 个（只列不删）")
        for item in orphans:
            lines.append(f"  · {item['file']}　{item['bytes']} 字节　{item['mtime']}")
    if applied is not None:
        if hard:
            lines.append(
                f"已物理删除：构建 {applied['builds']} 条 / 产物行 {applied['artifacts']} 条 / "
                f"选题行 {applied['selections']} 条　**不可恢复**"
            )
        else:
            lines.append(f"已归档：{applied.get('archived', 0)} 条（行仍保留，?include_archived=1 可见）")
    elif report.get("total"):
        lines.append("当前为 dry-run：什么都没改。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="归档重复的简历构建记录（默认 dry-run，硬删需显式开关）")
    parser.add_argument("--apply", action="store_true", help="真正写库（默认为 dry-run）")
    parser.add_argument("--data-dir", default=os.environ.get("DATA_DIR"), help="数据目录（默认 ./data）")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")
    parser.add_argument("--min-age-hours", type=float, default=0.0, help="只处理这么多小时以前的重复记录")
    parser.add_argument(
        "--ignore-name",
        action="store_true",
        help="忽略构建名字，只按「语言+模板+岗位+公司+所选经历」判重复（更激进；会归档改过名的历史导出）",
    )
    parser.add_argument(
        "--hard-delete", action="store_true", help="物理删除而非归档（不可恢复，必须同时给 --yes）"
    )
    parser.add_argument("--yes", action="store_true", help="确认执行 --hard-delete")
    parser.add_argument(
        "--list-orphan-files",
        action="store_true",
        help="列出 data/exports/ 里没有任何产物记录的 PDF（名字/大小/mtime），只列不删",
    )
    args = parser.parse_args(argv)

    if args.hard_delete and not args.yes:
        print(
            "--hard-delete 会物理删除构建行、产物行与选题行，**不可恢复**。确认请再加 --yes。",
            file=sys.stderr,
        )
        return 2

    db_path = _db_path(args.data_dir)
    if not db_path.exists():
        print(f"找不到数据库：{db_path}", file=sys.stderr)
        return 2
    conn = sqlite3.connect(str(db_path))
    try:
        exports_dir = db_path.parent / "exports"
        orphans = orphan_files(conn, exports_dir) if args.list_orphan_files else None
        if args.list_orphan_files and not args.apply:
            if args.json:
                print(json.dumps({"orphan_files": orphans}, ensure_ascii=False, indent=2))
            else:
                print(render({}, hard=False, applied=None, orphans=orphans))
            return 0

        report = classify(conn, min_age_hours=args.min_age_hours, ignore_name=args.ignore_name)
        drop_ids = [item["id"] for item in report["drop"]]
        report["files"] = _after_delete_unreferenced(conn, drop_ids)
        applied = None
        if args.apply:
            applied = hard_delete(conn, drop_ids) if args.hard_delete else archive(conn, drop_ids)
        if args.json:
            print(
                json.dumps(
                    {**report, "mode": "hard-delete" if args.hard_delete else "archive", "applied": applied, "orphan_files": orphans},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(render(report, hard=args.hard_delete, applied=applied, orphans=orphans))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
