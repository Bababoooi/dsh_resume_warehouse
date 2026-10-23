"""教育段的「补充行」（GPA / 主修课程）——最小可改入口。

背景：中文简历里的 `专业成绩：GPA 3.56/4 86.53/100 CET4：562 CET6:508` 与
`主修课程：…` 这两行，导入时被原样存进默认模板教育条目的 `template_block.static_text`，
而**界面上没有任何地方能改**：用户改了 GPA，导出还是旧数字。

这里只做一件事：读写那一个 entry block 的 `static_text`（按行）。不做整套模板编辑器。

安全边界：
* 只碰默认模板里 `bound_package_kind='education'` 的那个 entry block，别的块一律不动；
* 写前落快照（`data/runtime/app.db.pre_edu_<stamp>`）并返回路径与 md5，改坏了能回滚；
* `lines: []` 是合法请求（清空该段），不是错误——清空后教育段不再出现这两行。
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import db as db_mod
from ..errors import ApiError
from ..repos import TemplateRepo

#: 一次最多几行（两条成绩行 + 课程行足够；给点余量但不至于被当正文框用）
MAX_LINES = 12
#: 单行上限（课程列表可能很长，但不能无限）
MAX_LINE_CHARS = 400


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(conn: sqlite3.Connection, *, tag: str = "edu") -> dict[str, str]:
    """把当前库整份备份到 `data/runtime/`，返回 ``{path, md5}``。

    用 sqlite 自己的 backup API（不是 `cp`）：WAL 未 checkpoint 时直接拷文件可能少事务。
    """
    paths = db_mod.get_paths()
    runtime = Path(paths.root) / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    dest = runtime / f"app.db.pre_{tag}_{_stamp()}"
    target = sqlite3.connect(dest)
    try:
        conn.backup(target)
    finally:
        target.close()
    return {"path": str(dest), "md5": _md5(dest)}


def _education_entry(repo: TemplateRepo, template_id: str) -> dict[str, Any] | None:
    blocks = repo.list_blocks(template_id)
    sections = {
        block["id"]
        for block in blocks
        if block.get("block_type") == "section" and block.get("bound_package_kind") == "education"
    }
    for block in blocks:
        if block.get("block_type") != "entry":
            continue
        if block.get("parent_block_id") in sections:
            return block
    # 兜底：有些模板把 entry 直接挂在教育 section 之外，但仍标着 education
    for block in blocks:
        if block.get("block_type") == "entry" and block.get("bound_package_kind") == "education":
            return block
    return None


def _pick_template(repo: TemplateRepo) -> dict[str, Any]:
    template = repo.default() or repo.resolved_default(lang="zh") or repo.resolved_default()
    if template is None:
        raise ApiError(
            "NO_DEFAULT_TEMPLATE",
            "还没有模板，教育段补充行无从读写",
            details={"candidates": [], "count": 0},
            hint="先导入一份简历生成模板（POST /api/v1/imports → commit）",
        )
    return template


def _split(text: str | None) -> list[str]:
    if not text:
        return []
    return [line.strip() for line in str(text).splitlines() if line.strip()]


def read(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """返回默认模板教育段当前的补充行（没有模板 / 没有内容都返回空列表，不抛错）。"""
    conn = conn or db_mod.get_conn()
    repo = TemplateRepo(conn)
    template = repo.default() or repo.resolved_default(lang="zh") or repo.resolved_default()
    if template is None:
        return {"template_id": None, "template_name": None, "block_id": None, "lines": [], "updated_at": None}
    block = _education_entry(repo, template["id"])
    lines = _split(block.get("static_text") if block else None)
    return {
        "template_id": template["id"],
        "template_name": template.get("name"),
        "block_id": block["id"] if block else None,
        "lines": lines,
        "updated_at": block.get("updated_at") if block else None,
    }


def _validate(lines: list[str]) -> list[str]:
    if len(lines) > MAX_LINES:
        raise ApiError(
            "VALIDATION_ERROR",
            f"教育段补充行最多 {MAX_LINES} 行",
            details={"fields": [{"field": "lines", "rule": f"max_items={MAX_LINES}", "message": f"给了 {len(lines)} 行"}]},
        )
    cleaned: list[str] = []
    for index, line in enumerate(lines):
        text = str(line).strip()
        if not text:
            continue
        if len(text) > MAX_LINE_CHARS:
            raise ApiError(
                "VALIDATION_ERROR",
                f"第 {index + 1} 行超过 {MAX_LINE_CHARS} 字",
                details={
                    "fields": [
                        {"field": f"lines[{index}]", "rule": f"max_length={MAX_LINE_CHARS}", "message": f"实际 {len(text)} 字"}
                    ]
                },
            )
        cleaned.append(text)
    return cleaned


def write(lines: list[str], conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    """把 `lines` 写回默认模板教育段的 `static_text`（空数组 = 清空该段）。"""
    conn = conn or db_mod.get_conn()
    repo = TemplateRepo(conn)
    template = _pick_template(repo)
    block = _education_entry(repo, template["id"])
    if block is None:
        raise ApiError(
            "TEMPLATE_INVALID",
            "默认模板里没有教育段条目，无法写入补充行",
            details={"template_id": template["id"], "template_name": template.get("name")},
            hint="重新导入一份中文简历生成模板，或在模板页确认教育段是否完整",
        )

    cleaned = _validate(lines)
    snap = snapshot(conn, tag="edu")
    text = "\n".join(cleaned) if cleaned else None
    now = db_mod.utcnow_iso()
    with db_mod.transaction(conn) as tx:
        tx.execute(
            "UPDATE template_block SET static_text = ?, updated_at = ? WHERE id = ?",
            (text, now, block["id"]),
        )
    payload = read(conn)
    payload.update({"snapshot": snap, "saved": True})
    return payload
