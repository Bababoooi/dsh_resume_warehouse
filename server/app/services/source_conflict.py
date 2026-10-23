"""中英两份简历里「同一字段不同值」的检测（只在本地比对，不发任何网络请求）。

用户自己的中文版与英文版简历存在真实不一致（实测：GPA 3.56/4 vs 3.57/4.0、
86.53/100 vs 86.86/100、到岗 2027年1月下旬 vs Early July 2026 —— 相差 5 个月）。
这里**不合并、不四舍五入、不替用户选**：中文版出中文的数、英文版出英文的数，
同时给出一条 ``SOURCE_CONFLICT`` 警告，由用户在导出页确认以哪份为准。

数据来源：``import_job.draft_json``（用户自己提交的导入草稿），按 ``lang`` 分组。
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from typing import Any

from .. import db as db_mod

#: 从简历文本里抽「GPA 3.56/4」「86.53/100」这类成绩
GPA_PATTERN = re.compile(r"(?:GPA|绩点)\s*[:：]?\s*(\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?)", re.I)
SCORE_PATTERN = re.compile(r"(\d{2,3}(?:\.\d+)?\s*/\s*100)")
#: 到岗时间
AVAILABLE_PATTERNS = (
    re.compile(r"到岗时间\s*[:：]\s*([^\n|｜/]{2,40})"),
    re.compile(r"Available\s*[:：]\s*([^\n|｜/]{2,40})", re.I),
)

FIELD_LABELS = {"gpa": "GPA", "score": "百分制成绩", "available": "到岗时间"}


def _draft_texts(draft: dict[str, Any]) -> list[str]:
    """把草稿里所有可见文本摊平成字符串列表（含 entry facts/bullets 与技能行）。"""
    out: list[str] = []
    for block in draft.get("blocks") or []:
        for key in ("heading", "preview_text"):
            value = block.get(key)
            if isinstance(value, str) and value.strip():
                out.append(value)
        entry = block.get("entry") or {}
        for key in ("title", "org", "role", "degree_major", "raw_title"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                out.append(value)
        for key in ("facts", "bullets"):
            for item in entry.get(key) or []:
                if isinstance(item, str) and item.strip():
                    out.append(item)
        for slot in block.get("slots") or []:
            value = slot.get("suggested_value")
            if isinstance(value, str) and value.strip():
                out.append(value)
    for row in draft.get("skills") or []:
        if isinstance(row, dict) and str(row.get("line") or "").strip():
            out.append(str(row["line"]))
    return out


def _extract(texts: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    joined = "\n".join(texts)
    match = GPA_PATTERN.search(joined)
    if match:
        found["gpa"] = re.sub(r"\s+", "", match.group(1))
    match = SCORE_PATTERN.search(joined)
    if match and "gpa" in found:
        found["score"] = re.sub(r"\s+", "", match.group(1))
    for pattern in AVAILABLE_PATTERNS:
        match = pattern.search(joined)
        if match:
            found["available"] = match.group(1).strip(" ｜|")
            break
    return found


def _latest_committed_by_lang(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    # 已提交的优先；没有已提交的（例如用户只导入了没提交）就用最新草稿
    rows = conn.execute(
        "SELECT id, draft_json, created_at, status FROM import_job "
        "WHERE deleted_at IS NULL AND draft_json IS NOT NULL "
        "ORDER BY (status = 'committed') DESC, created_at DESC, id DESC"
    ).fetchall()
    picked: dict[str, dict[str, Any]] = {}
    for row in rows:
        draft = db_mod.loads_json(row["draft_json"], {}) or {}
        lang = str(draft.get("lang") or "")
        if not lang or lang in picked:
            continue
        picked[lang] = {"import_id": row["id"], "draft": draft}
    return picked


def detect(conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """返回中英不一致的字段列表（无冲突返回空列表，不抛异常）。"""
    conn = conn or db_mod.get_conn()
    try:
        picked = _latest_committed_by_lang(conn)
    except sqlite3.Error:
        return []
    if "zh" not in picked or "en" not in picked:
        return []
    zh = _extract(_draft_texts(picked["zh"]["draft"]))
    en = _extract(_draft_texts(picked["en"]["draft"]))
    conflicts: list[dict[str, Any]] = []
    for field, zh_value in zh.items():
        en_value = en.get(field)
        if not en_value:
            continue
        if zh_value.replace(" ", "") == en_value.replace(" ", ""):
            continue
        conflicts.append(
            {
                "field": field,
                "label": FIELD_LABELS.get(field, field),
                "zh_value": zh_value,
                "en_value": en_value,
                "zh_import_id": picked["zh"]["import_id"],
                "en_import_id": picked["en"]["import_id"],
            }
        )
    return conflicts


#: 用户决议的语言标签（`user_profile.extra.conflict_resolution.fields` 的值）
RESOLUTION_LABELS = {"zh": "中文版", "en": "英文版"}


def _resolved(item: dict[str, Any], resolution: Mapping[str, Any] | None) -> str | None:
    """这条冲突有没有被用户决议过？返回 ``zh`` / ``en``，未决议返回 ``None``。

    决议存在 ``user_profile.extra.conflict_resolution``：
    ``{"default": "zh", "fields": {"gpa": "zh", "score": "zh", "available": "zh"}, ...}``。
    只认 `fields` 里的逐字段决议；`default` 是元信息，**不**用来兜底（否则等于替用户
    决定他没确认过的字段）。
    """
    if not isinstance(resolution, Mapping):
        return None
    # 只有用户本人的决定才算数：`decided_by` 缺省视为未确认，自动流程（写 "auto"、
    # 或者干脆不写）不许给自己发免单，否则警告会在无人拍板时被静默降级。
    if str(resolution.get("decided_by") or "").strip().lower() != "user":
        return None
    fields = resolution.get("fields") or {}
    if not isinstance(fields, Mapping):
        return None
    value = str(fields.get(item["field"]) or "").strip().lower()
    # 只认逐字段决议：`default` 是「这次拍板的主导语言」这类元信息，
    # 拿它兜底会把用户没确认过的字段也降级成 info（等于替用户决定）。
    return value if value in RESOLUTION_LABELS else None


def warnings_for(
    conflicts: list[dict[str, Any]], resolution: Mapping[str, Any] | None = None
) -> list[dict[str, Any]]:
    """把冲突转成响应里的 warning（code 固定 SOURCE_CONFLICT，一次一条/字段）。

    已决议的字段降级为 ``info`` 并带上 ``details.resolved`` / ``decided_at``：
    用户已经拍过板，就不该每次导出都拿一条黄色警告再问一遍。**未决议**的字段保持
    ``warn`` 原样——降级只发生在「用户真的选过」的字段上，不做按 ``default`` 的批量放过
    （逐字段决议优先，``default`` 只在该字段没写时兜底）。
    """
    out: list[dict[str, Any]] = []
    for item in conflicts:
        decided = _resolved(item, resolution)
        details: dict[str, Any] = {
            "field": item["field"],
            "zh_value": item["zh_value"],
            "en_value": item["en_value"],
        }
        if decided:
            details["resolved"] = decided
            details["decided_at"] = (resolution or {}).get("decided_at")
            details["value_used"] = item["zh_value"] if decided == "zh" else item["en_value"]
            message = (
                f"「{item['label']}」中英不一致（中文版 {item['zh_value']} / 英文版 {item['en_value']}），"
                f"已按{RESOLUTION_LABELS[decided]}为准（可在个人资料里改）"
            )
            out.append(
                {
                    "code": "SOURCE_CONFLICT",
                    "severity": "info",
                    "message": message,
                    "details": details,
                }
            )
            continue
        out.append(
            {
                "code": "SOURCE_CONFLICT",
                "severity": "warn",
                "message": (
                    f"中英简历的「{item['label']}」不一致：中文版 {item['zh_value']} / "
                    f"英文版 {item['en_value']}，请确认以哪份为准"
                ),
                "details": details,
            }
        )
    return out
