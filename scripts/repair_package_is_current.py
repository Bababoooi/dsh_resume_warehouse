#!/usr/bin/env python3
"""修复「时间线被抹掉」的 Package 行（P0 事故的数据侧脚本）。

背景
----
``server/app/repos.py`` 的 ``PackageRepo._encode`` 曾把 bool→int 的三目写成
``1 if isinstance(value, bool) ...``，于是 ``is_current=False`` 落库成 ``1``，紧接着
``create()`` 认为「至今在职」并把用户填的 ``end_date`` 抹成 ``NULL``。结果真库 18 行
全部变成 ``is_current=1 / end_date=NULL``——简历上每条经历都会渲染成「至今」。

本脚本只做**数据**修复，默认为 dry-run：

* 默认：列出所有受影响行（id / title / start_date / end_date / is_current / source）。
* ``--apply``：只改**能确定判定**的行——``is_current=1`` 且 ``end_date IS NULL``，且能从
  ``import_job.draft_json`` 的 ``entry.date_range`` 反解出**唯一**结束时间 → 回填
  ``end_date`` 并把 ``is_current`` 置 0。
* 反解不到、或多条草稿给出**互相矛盾**的结束时间 → **不猜**，进「需人工确认」清单。
* 每次 ``--apply`` 前后各打一次快照到 ``data/backups/``（已被 .gitignore）。

用法::

    python3 scripts/repair_package_is_current.py                # 只列清单
    python3 scripts/repair_package_is_current.py --json         # 机器可读
    python3 scripts/repair_package_is_current.py --apply --report data/exports/probe_rows_report.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = PROJECT_ROOT / "data"

_COPY_SUFFIX_RE = re.compile(r"[（(](?:副本|复制|copy)[）)]\s*$", re.IGNORECASE)
_SPAN_SPLIT_RE = re.compile(r"\s*(?:-|–|—|~|～|至|to)\s*")
_PRESENT_TOKENS = ("至今", "现在", "目前", "present", "now", "current")
_YM_RE = re.compile(r"^(\d{4})[.\-/年]?\s*(\d{1,2})?\s*月?$")
_MY_RE = re.compile(r"^(\d{1,2})/(\d{4})$")


def normalize_title(text: str | None) -> str:
    """标题归一：去「（副本）」后缀、去空白、小写。"""
    value = (text or "").strip()
    value = _COPY_SUFFIX_RE.sub("", value)
    return re.sub(r"\s+", "", value).lower()


def normalize_org(text: str | None) -> str:
    return re.sub(r"\s+", "", (text or "")).lower()


def parse_end_date(date_range: str | None) -> tuple[str | None, str]:
    """从 ``entry.date_range`` 反解结束时间。

    返回 ``(end_date, status)``：
    * ``("2026-10", "ok")`` 能确定；
    * ``(None, "present")`` 原文就是「至今」——这条 ``is_current=1`` 可能是合法的；
    * ``(None, "unparsed")`` 解析不出来，交给人工。
    """
    text = (date_range or "").strip()
    if not text:
        return None, "unparsed"
    # 「至」本身是区间分隔符，所以「2026.07 - 至今」必须先判 present 再切分，
    # 否则会被切成 ("2026.07", "今") 而判成 unparsed。
    if any(token in text.lower() for token in _PRESENT_TOKENS):
        return None, "present"
    pieces = [piece.strip() for piece in _SPAN_SPLIT_RE.split(text) if piece.strip()]
    if not pieces:
        return None, "unparsed"
    tail = pieces[-1]
    if any(token in tail.lower() for token in _PRESENT_TOKENS):
        return None, "present"
    match = _MY_RE.match(tail)
    if match:
        return f"{match.group(2)}-{int(match.group(1)):02d}", "ok"
    match = _YM_RE.match(tail)
    if match:
        year, month = match.group(1), match.group(2)
        return (f"{year}-{int(month):02d}" if month else year), "ok"
    return None, "unparsed"


def load_import_entries(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """把所有导入草稿里的 entry 摊平成索引（标题/组织/时间区间）。"""
    entries: list[dict[str, Any]] = []
    rows = conn.execute(
        "SELECT id, draft_json, created_at FROM import_job WHERE draft_json IS NOT NULL"
        " ORDER BY created_at DESC"
    ).fetchall()
    for row in rows:
        try:
            draft = json.loads(row["draft_json"])
        except (TypeError, ValueError):
            continue
        for block in draft.get("blocks") or []:
            entry = block.get("entry") or {}
            date_range = entry.get("date_range")
            if not date_range:
                continue
            entries.append(
                {
                    "import_id": row["id"],
                    "import_created_at": row["created_at"],
                    "kind": block.get("bound_package_kind"),
                    "title": entry.get("title") or entry.get("org") or entry.get("degree_major"),
                    "org": entry.get("org"),
                    "role": entry.get("role"),
                    "date_range": date_range,
                }
            )
    return entries


def match_candidates(package: dict[str, Any], entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    title_key = normalize_title(package.get("title"))
    org_key = normalize_org(package.get("org"))
    hits = []
    for entry in entries:
        entry_title = normalize_title(entry.get("title"))
        entry_org = normalize_org(entry.get("org"))
        if title_key and entry_title and title_key == entry_title:
            hits.append(entry)
        elif org_key and entry_org and org_key == entry_org:
            hits.append(entry)
    return hits


def classify(conn: sqlite3.Connection) -> dict[str, Any]:
    """把受影响行分成三类：可确定修复 / 需人工确认 / 疑似合法（原文就是「至今」）。"""
    entries = load_import_entries(conn)
    rows = conn.execute(
        "SELECT id, title, kind, org, role, start_date, end_date, is_current, source, status,"
        " deleted_at, created_at FROM package WHERE is_current = 1 AND end_date IS NULL"
        " ORDER BY created_at, id"
    ).fetchall()

    fixable: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    possibly_legit: list[dict[str, Any]] = []
    for row in rows:
        package = dict(row)
        candidates = match_candidates(package, entries)
        ends: dict[str, list[str]] = {}
        statuses: set[str] = set()
        for candidate in candidates:
            end, status = parse_end_date(candidate.get("date_range"))
            statuses.add(status)
            if end:
                ends.setdefault(end, []).append(candidate.get("date_range"))

        record = {
            "id": package["id"],
            "title": package["title"],
            "kind": package["kind"],
            "org": package.get("org"),
            "start_date": package["start_date"],
            "end_date": package["end_date"],
            "is_current": package["is_current"],
            "source": package.get("source"),
            "status": package.get("status"),
            "deleted": bool(package.get("deleted_at")),
            "created_at": package["created_at"],
            "candidates": [
                {"import_id": c["import_id"], "date_range": c["date_range"], "title": c["title"]}
                for c in candidates[:5]
            ],
        }

        if len(ends) == 1:
            end = next(iter(ends))
            record["proposed_end_date"] = end
            record["evidence"] = ends[end][0]
            fixable.append(record)
        elif len(ends) > 1:
            record["reason"] = "多份草稿给出互相矛盾的结束时间：" + "、".join(sorted(ends))
            record["conflicts"] = {end: ranges[0] for end, ranges in sorted(ends.items())}
            manual.append(record)
        elif statuses == {"present"}:
            record["reason"] = "来源草稿原文就是「至今」，is_current=1 可能本身合法，需人工确认是否确实是当前在做"
            possibly_legit.append(record)
        elif "present" in statuses:
            record["reason"] = (
                "部分来源草稿写「至今」，另有 "
                f"{len(candidates) - 1} 条同名经历但时间区间解析不出结束时间，需人工确认"
            )
            manual.append(record)
        elif candidates:
            record["reason"] = "找到来源 entry 但时间区间解析不出结束时间"
            manual.append(record)
        else:
            record["reason"] = "在 import_job 草稿里找不到同名经历，无法反解结束时间"
            manual.append(record)
    return {
        "affected_total": len(rows),
        "fixable": fixable,
        "manual": manual,
        "possibly_legit": possibly_legit,
    }


PROBE_TAG = "probe-archived"
FIXTURE_TAG = "测试夹具"
DEFAULT_PROBE_TITLE = "小象超市门店选址与订单量预测建模"


def load_tags(raw: Any) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def find_probe_rows(conn: sqlite3.Connection, *, title_pattern: str = DEFAULT_PROBE_TITLE) -> list[dict[str, Any]]:
    """找出「测试探测行」：同标题的多次 POST 残留。

    判定条件（全部满足才动，宁可少动）：
    * 标题等于 ``title_pattern`` 或带「（副本）」后缀；
    * ``source='authored'``、``status='draft'``；
    * **没有任何 build 引用**（``build_selection`` 为 0）——被引用过的行不许归档。
    """
    like = f"{title_pattern}%"
    rows = conn.execute(
        "SELECT id, title, created_at, deleted_at, status, source, tags_json,"
        " (SELECT COUNT(*) FROM package_bullet_variant v WHERE v.package_id = package.id) AS variants,"
        " (SELECT COUNT(*) FROM build_selection s WHERE s.package_id = package.id) AS selections"
        " FROM package WHERE title LIKE ? ORDER BY created_at, id",
        (like,),
    ).fetchall()
    probes = []
    for row in rows:
        item = dict(row)
        if item["status"] != "draft" or item["source"] != "authored":
            continue
        if item["selections"]:
            continue
        probes.append(item)
    return probes


def archive_probe_rows(
    conn: sqlite3.Connection,
    *,
    title_pattern: str = DEFAULT_PROBE_TITLE,
    keep_id: str | None = None,
    fixture_id: str | None = None,
) -> dict[str, Any]:
    """把探测行**软删**（``deleted_at`` + ``probe-archived`` 标签），物理行不动。

    保留一行做本地回归夹具，并在标签里标明「测试夹具」，避免用户以为是自己的经历。
    """
    probes = find_probe_rows(conn, title_pattern=title_pattern)
    keep = keep_id or (probes[0]["id"] if probes else None)
    if fixture_id and not keep_id:
        keep = fixture_id
    archived: list[dict[str, Any]] = []
    kept = None
    now = dt.datetime.now().astimezone().replace(microsecond=0).isoformat()
    with conn:
        for item in probes:
            if item["id"] == keep:
                kept = item
                tags = load_tags(item["tags_json"])
                if FIXTURE_TAG not in tags:
                    tags.append(FIXTURE_TAG)
                conn.execute(
                    "UPDATE package SET tags_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(tags, ensure_ascii=False), now, item["id"]),
                )
                continue
            tags = load_tags(item["tags_json"])
            if PROBE_TAG not in tags:
                tags.append(PROBE_TAG)
            if item["deleted_at"]:
                continue
            conn.execute(
                "UPDATE package SET deleted_at = ?, tags_json = ?, updated_at = ? WHERE id = ?",
                (now, json.dumps(tags, ensure_ascii=False), now, item["id"]),
            )
            archived.append(item)
    return {"probes": probes, "archived": archived, "kept": kept, "title_pattern": title_pattern}


def list_archived_probe_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """当前处于软归档状态（``probe-archived`` 标签）的探测行。"""
    rows = conn.execute(
        "SELECT id, title, created_at, deleted_at,"
        " (SELECT COUNT(*) FROM package_bullet_variant v WHERE v.package_id = package.id) AS variants"
        " FROM package WHERE deleted_at IS NOT NULL"
        " AND EXISTS (SELECT 1 FROM json_each(package.tags_json) WHERE json_each.value = ?)"
        " ORDER BY created_at, id",
        (PROBE_TAG,),
    ).fetchall()
    return [dict(row) for row in rows]


def restore_probe_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """反向恢复：只动带 ``probe-archived`` 标签的行（不碰用户自己归档的）。"""
    rows = conn.execute(
        "SELECT id, title, created_at FROM package WHERE deleted_at IS NOT NULL"
        " AND EXISTS (SELECT 1 FROM json_each(package.tags_json) WHERE json_each.value = ?)"
        " ORDER BY created_at, id",
        (PROBE_TAG,),
    ).fetchall()
    restored = [dict(row) for row in rows]
    now = dt.datetime.now().astimezone().replace(microsecond=0).isoformat()
    with conn:
        for item in restored:
            conn.execute(
                "UPDATE package SET deleted_at = NULL, updated_at = ? WHERE id = ?", (now, item["id"])
            )
    return restored


def snapshot(conn: sqlite3.Connection, label: str) -> Path:
    """用 sqlite 在线备份打快照（不锁写、不复制 WAL 中间态）。"""
    backups = Path(conn.execute("PRAGMA database_list").fetchone()[2]).resolve().parent / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backups / f"app-{stamp}-{label}.db"
    with sqlite3.connect(target) as dest:
        conn.backup(dest)
    return target


def apply_fixes(conn: sqlite3.Connection, fixes: list[dict[str, Any]]) -> tuple[Path, Path, int]:
    """真正写库：只改 fixable 列表里的行（回填 end_date、is_current=0）。"""
    pre = snapshot(conn, "pre-repair-is-current")
    changed = 0
    now = dt.datetime.now().astimezone().replace(microsecond=0).isoformat()
    with conn:
        for item in fixes:
            cursor = conn.execute(
                "UPDATE package SET end_date = ?, is_current = 0, updated_at = ?"
                " WHERE id = ? AND is_current = 1 AND end_date IS NULL",
                (item["proposed_end_date"], now, item["id"]),
            )
            changed += cursor.rowcount or 0
    post = snapshot(conn, "post-repair-is-current")
    return pre, post, changed


def render_markdown(result: dict[str, Any], *, applied: int | None = None) -> str:
    lines = ["# Package 时间线异常行（is_current=1 且 end_date 为空）", ""]
    lines.append(f"- 受影响总计：**{result['affected_total']}** 行")
    lines.append(f"- 可自动修复（草稿里能反解出唯一结束时间）：**{len(result['fixable'])}** 行")
    lines.append(f"- 需人工确认：**{len(result['manual'])}** 行")
    lines.append(f"- 疑似本来合法（草稿原文「至今」）：**{len(result['possibly_legit'])}** 行")
    if applied is not None:
        lines.append(f"- 本次 `--apply` 实际改写：**{applied}** 行")
    lines += ["", "> 本清单由 `scripts/repair_package_is_current.py` 生成；默认 dry-run，**不删任何行**。"]

    def table(title: str, items: list[dict[str, Any]]) -> None:
        lines.extend(["", f"## {title}", ""])
        if not items:
            lines.append("（无）")
            return
        lines.append("| id | 标题 | 类型 | 起始 | 结束 | is_current | 状态 | 来源草稿证据 | 说明 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for item in items:
            evidence = item.get("evidence") or "—"
            note = item.get("reason") or ""
            lines.append(
                "| `{id}` | {title} | {kind} | {start} | {end} | {cur} | {status}{deleted} | {ev} | {note} |".format(
                    id=item["id"],
                    title=(item.get("title") or "").replace("|", "\\|"),
                    kind=item.get("kind") or "",
                    start=item.get("start_date") or "—",
                    end=item.get("end_date") or "**NULL**",
                    cur=item.get("is_current"),
                    status=item.get("status") or "",
                    deleted="（已软删）" if item.get("deleted") else "",
                    ev=str(evidence).replace("|", "\\|"),
                    note=note,
                )
            )

    table("可自动修复", result["fixable"])
    table("需人工确认", result["manual"])
    table("疑似本来合法（需人工确认是否确实在做）", result["possibly_legit"])
    return "\n".join(lines) + "\n"


def render_archive_section(info: dict[str, Any]) -> str:
    lines = ["", "## 已软归档的探测行（deleted_at 已置，物理行未删）", ""]
    lines.append(f"- 识别到同标题行：**{len(info['probes'])}** 行；软归档：**{len(info['archived'])}** 行")
    kept = info.get("kept")
    if kept:
        lines.append(f"- **保留哪一行**：`{kept['id']}`（{kept.get('title')}）")
        lines.append(
            f"  - **为什么保留**：它是这批探测行里**最早的一条**（创建于 {kept.get('created_at')}），"
            "作为 t6/t8 的本地回归夹具（打包 / 命名 / 导出链路都拿它当输入），删掉会让这几条链路的"
            "手工复验失去固定输入。"
        )
        lines.append(
            f"  - 已加标签「{FIXTURE_TAG}」，用户在列表里能看出它不是自己的经历；"
            "`--archive-probe-rows` 会**跳过它**，下次清理也不会归档。"
        )
    lines += ["", "> 可逆：`python3 scripts/repair_package_is_current.py --restore` 会把这些行恢复。", ""]
    rows = info.get("archived") or []
    already = info.get("archived_all") or []
    if not rows:
        lines.append(
            f"（本次没有新归档的行；当前处于软归档状态的共 {len(already)} 行，明细如下）"
        )
        rows = already
    if not rows:
        return "\n".join(lines) + "\n"
    lines.append("| id | 标题 | 创建时间 | 变体数 | 归档理由 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for item in rows:
        lines.append(
            "| `{id}` | {title} | {created} | {variants} | 同标题重复 POST 的测试残留；无 build 引用；正文与真实来源（简历 / import draft）重复 |".format(
                id=item["id"],
                title=(item.get("title") or "").replace("|", "\\|"),
                created=item.get("created_at") or "",
                variants=item.get("variants", 0),
            )
        )
    return "\n".join(lines) + "\n"


def _append_restore_section(path: Path, restored: list[dict[str, Any]]) -> None:
    header = "\n## 已恢复（--restore）\n\n"
    if not restored:
        body = "（没有带 probe-archived 标签的行可恢复）\n"
    else:
        rows = ["| id | 标题 | 创建时间 |", "| --- | --- | --- |"]
        rows += [
            "| `{id}` | {title} | {created} |".format(
                id=item["id"], title=(item.get("title") or "").replace("|", "\\|"), created=item.get("created_at") or ""
            )
            for item in restored
        ]
        body = "\n".join(rows) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    path.write_text(existing + header + body, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="修复 is_current=1/end_date=NULL 的 Package 行（默认 dry-run）")
    parser.add_argument("--data-dir", default=None, help="数据目录（默认 ./data）")
    parser.add_argument("--apply", action="store_true", help="真正写库（默认只列清单）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--report", default=None, help="同时把 markdown 清单写到该路径")
    parser.add_argument(
        "--archive-probe-rows",
        action="store_true",
        help="把测试探测行（同标题多次 POST 的残留）**软归档**（deleted_at + probe-archived 标签），保留一条做夹具",
    )
    parser.add_argument("--restore", action="store_true", help="撤销 --archive-probe-rows（只看 probe-archived 标签）")
    parser.add_argument("--probe-title", default=DEFAULT_PROBE_TITLE, help="探测行标题（默认小象超市门店选址…）")
    parser.add_argument("--keep-id", default=None, help="指定保留为夹具的 package id（默认最早一条）")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else DEFAULT_DATA
    db_path = data_dir / "app.db"
    if not db_path.exists():
        print(f"找不到数据库：{db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    archive_info: dict[str, Any] | None = None
    try:
        if args.restore:
            restored = restore_probe_rows(conn)
            print(f"已恢复 {len(restored)} 行（deleted_at 清空）")
            for item in restored:
                print(f"    [restored] {item['id']}  {item['title']}")
            if args.report:
                _append_restore_section(Path(args.report), restored)
        if args.archive_probe_rows:
            # 归档前先按顺序打快照（可逆的两个方向都有据可查）
            snapshot(conn, "pre-archive-probe")
            archive_info = archive_probe_rows(
                conn, title_pattern=args.probe_title, keep_id=args.keep_id
            )
            archive_info["archived_all"] = list_archived_probe_rows(conn)
            snapshot(conn, "post-archive-probe")
            kept = archive_info["kept"]
            print(
                f"探测行 {len(archive_info['probes'])} 行：软归档 {len(archive_info['archived'])} 行"
                f"，保留夹具 1 行（{kept['id'] if kept else '—'}）"
            )
            for item in archive_info["archived"]:
                print(f"    [archived] {item['id']}  {item['title']}")
        result = classify(conn)
        applied: int | None = None
        if args.apply:
            if result["fixable"]:
                pre, post, applied = apply_fixes(conn, result["fixable"])
                print(f"快照：{pre.name} → {post.name}", file=sys.stderr)
            else:
                applied = 0
                print("没有可自动修复的行，未写库。", file=sys.stderr)
    finally:
        pass

    if args.json:
        payload = dict(result)
        if applied is not None:
            payload["applied"] = applied
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"受影响 {result['affected_total']} 行（is_current=1 且 end_date 为空）")
        for label, key in (
            ("可自动修复", "fixable"),
            ("需人工确认", "manual"),
            ("疑似本来合法", "possibly_legit"),
        ):
            print(f"  {label}: {len(result[key])} 行")
        for item in result["fixable"]:
            print(f"    [fix] {item['id']}  {item['title']}  → end_date={item['proposed_end_date']}（证据 {item['evidence']}）")
        for item in result["manual"]:
            print(f"    [manual] {item['id']}  {item['title']}  —— {item['reason']}")
        for item in result["possibly_legit"]:
            print(f"    [check] {item['id']}  {item['title']}  —— {item['reason']}")
        if applied is None:
            print("\n当前是 dry-run：加 --apply 才会写库（会先打快照）。")

    if args.report:
        target = Path(args.report)
        target.parent.mkdir(parents=True, exist_ok=True)
        text = render_markdown(result, applied=applied)
        if archive_info is not None:
            text += render_archive_section(archive_info)
        target.write_text(text, encoding="utf-8")
        print(f"清单已写入 {target}", file=sys.stderr)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
