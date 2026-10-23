"""确定性中英映射（纯本地，不调用 LLM）。

英文简历的「框架」必须真的是英文：section 标题、字段标签、日期、姓名/校名形态。
正文（经历段落）允许暂时沿用中文原文，但**必须发 ``LANG_FALLBACK`` 告诉用户**，
不能让人拿着一份自以为英文的简历去投递。

未收录的自定义标题不做机器翻译：保留原文 + ``LANG_HEADING_UNMAPPED`` 警告。
"""

from __future__ import annotations

import re
from typing import Iterable

#: 中文 section 标题 → 英文（用户简历实测用到的 + 常见变体）
#: 契约 ``docs/API-CONTRACT.md §8.5.1`` 的结构词表 —— **唯一真源**。
#: 这里的值必须与契约表逐字相等（``server/tests/test_i18n_contract.py`` 会解析文档比对），
#: 改动必须先改契约，再照抄到这里，不许在实现里自创译名。
HEADING_BY_KIND: dict[str, tuple[str, str]] = {
    "education": ("教育背景", "Education"),
    "experience": ("实习经历", "Experience"),
    "projects": ("项目经历", "Projects"),
    "campus": ("校园活动", "Campus Activities"),
    "skills": ("职业技能", "Skills"),
    "summary": ("个人总结", "Summary"),
    "honors": ("荣誉奖项", "Honors & Awards"),
}

#: 中文标题 → 英文（由 ``HEADING_BY_KIND`` 反推，避免第二份真源）
HEADING_ZH_TO_EN: dict[str, str] = {zh: en for zh, en in HEADING_BY_KIND.values()}

#: 字段标签
#: 契约 §8.5.1「字段标签与格式」表 —— 同样是唯一真源。
LABELS: dict[str, dict[str, str]] = {
    "available": {"zh": "到岗时间", "en": "Available"},
    "gpa": {"zh": "专业成绩", "en": "GPA"},
    "courses": {"zh": "主修课程", "en": "Relevant Coursework"},
}

#: 中文标签 → 英文（由 ``LABELS`` 反推）
LABEL_ZH_TO_EN: dict[str, str] = {item["zh"]: item["en"] for item in LABELS.values()}

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

#: ``2026.03`` / ``2026年3月`` / ``2026-03`` / ``03/2026``
DATE_POINT_PATTERNS = (
    re.compile(r"(?P<year>(?:19|20)\d{2})\s*[.\-/年]\s*(?P<month>\d{1,2})\s*月?"),
    re.compile(r"(?P<month>\d{1,2})\s*/\s*(?P<year>(?:19|20)\d{2})"),
)

PRESENT_TOKENS = ("至今", "现在", "Present", "present", "Now", "now", "Current")
RANGE_SPLIT_RE = re.compile(r"\s*(?:-|–|—|~|～|至|to)\s*")


def cjk_count(text: str) -> int:
    return len(CJK_RE.findall(str(text or "")))


def has_cjk(text: str) -> bool:
    return bool(CJK_RE.search(str(text or "")))


def heading_en(zh_heading: str) -> str | None:
    """中文标题 → 英文；未收录返回 None（调用方保留原文并告警）。"""
    text = str(zh_heading or "").strip()
    if not text:
        return None
    return HEADING_ZH_TO_EN.get(text) or HEADING_ZH_TO_EN.get(text.replace(" ", ""))


def label_en(zh_label: str) -> str:
    return LABEL_ZH_TO_EN.get(str(zh_label or "").strip(), str(zh_label or ""))


def _month_name(month: int) -> str:
    return MONTHS[month - 1] if 1 <= month <= 12 else ""


def date_point_en(token: str) -> str | None:
    """``2026.03`` → ``Mar 2026``；无法解析返回 None。"""
    text = str(token or "").strip()
    for pattern in DATE_POINT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        month = _month_name(int(match.group("month")))
        if not month:
            return None
        return f"{month} {match.group('year')}"
    if re.fullmatch(r"(?:19|20)\d{2}", text):
        return text
    return None


def date_range_en(text: str) -> str | None:
    """把中文写法日期区间整个转成英文；遇到无法完整解析的片段返回 None。

    ``2026.03 - 2026.10`` → ``Mar 2026 – Oct 2026``；``2026.03 - 至今`` → ``Mar 2026 – Present``。
    """
    raw = str(text or "").strip()
    if not raw:
        return None
    for token in PRESENT_TOKENS:
        raw = raw.replace(token, " Present ")
    parts = [part.strip() for part in RANGE_SPLIT_RE.split(raw) if part.strip()]
    if not parts or len(parts) > 3:
        return None
    converted: list[str] = []
    for part in parts:
        if part == "Present":
            converted.append("Present")
            continue
        point = date_point_en(part)
        if point is None:
            return None
        converted.append(point)
    return " – ".join(converted)


def translate_labels_in_text(text: str) -> str:
    """把文本里的中文标签（到岗时间：…）换成英文（Available: …），其它字符原样保留。"""
    out = str(text or "")
    for zh, en in LABEL_ZH_TO_EN.items():
        out = re.sub(rf"{re.escape(zh)}\s*[:：]", f"{en}: ", out)
    return out


def unmapped_headings(headings: Iterable[str]) -> list[str]:
    """返回含中文且没有英文映射的标题（用于 LANG_HEADING_UNMAPPED）。"""
    result: list[str] = []
    for heading in headings:
        text = str(heading or "").strip()
        if not text or not has_cjk(text):
            continue
        if heading_en(text):
            continue
        result.append(text)
    return result
