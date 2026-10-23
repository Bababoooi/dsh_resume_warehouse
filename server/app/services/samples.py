"""识别「演示/示例」经历包。

背景：为了让管线能跑通，仓库里长期存在一条 `【示例】小象超市…` 的演示包。一旦它被
自动选进用户简历，成品里就会出现一条用户从没做过的经历——比缺内容严重得多。
所以「是否演示数据」必须是**单一判据**，由 suggest（默认选包）、导出护栏、前端
选择器三处共用，避免各处各写一套字符串匹配而漏掉一处。

判据只有两条，宁可少判不可错判（漏判会让演示内容进成品）：

1. ``tags`` 里含 ``sample``（导入/演示脚本打标的就是它）；
2. 标题以 ``【示例】`` 开头。
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

SAMPLE_TAG = "sample"
SAMPLE_TITLE_PREFIX = "【示例】"


def _tags(row: Mapping[str, Any]) -> list[str]:
    raw = row.get("tags")
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return [raw]
        raw = parsed
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip().lower() for item in raw if str(item).strip()]
    return []


def is_sample(row: Mapping[str, Any] | None) -> bool:
    """这条经历是不是演示数据。``None`` 视为不是（避免空值把真数据误判成演示）。"""
    if not row:
        return False
    if SAMPLE_TAG in _tags(row):
        return True
    return str(row.get("title") or "").strip().startswith(SAMPLE_TITLE_PREFIX)


def split(rows: Sequence[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    """按演示/真实把经历列表拆成两份，保持原始顺序。"""
    real: list[Mapping[str, Any]] = []
    demo: list[Mapping[str, Any]] = []
    for row in rows:
        (demo if is_sample(row) else real).append(row)
    return real, demo


def included_warning(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """导出护栏：选进了演示经历时给一条用户读得懂的警告（不阻断，但绝不静默）。"""
    demo = [row for row in rows if is_sample(row)]
    if not demo:
        return None
    return {
        "code": "SAMPLE_PACKAGE_INCLUDED",
        "severity": "warn",
        "message": (
            f"简历里有 {len(demo)} 条是演示/示例经历（不是你的真实经历），"
            "成品会被当成真经历读——请确认是否要去掉"
        ),
        "details": {
            "packages": [
                {"package_id": str(row.get("id") or ""), "title": row.get("title")} for row in demo
            ],
            "hint": "在组装页取消勾选，或到经历库把该条归档（DELETE /api/v1/packages/{id}）",
        },
    }
