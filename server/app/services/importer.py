"""导入引擎：把简历文本行拆成 Template 结构（section → block → slot）。

口径（t5 任务 + captain 逐条验收）：

* **只做结构化切分，禁止润色**：所有文本片段来自原文，逐字保留（含 ``PM₂.₅``、
  ``（Python）``、``CET4：``、``AI&金融``、``K-means``）。数字一个都不能丢。
* **section 必须带 ``bound_package_kind``**（education/internship/project/campus/skill），
  否则下游无法把经历重排进 Package。
* **职业技能行整句保留**（用户 2026-10-23 裁决）：``skills`` 只派生 ``tokens`` 做匹配，
  ``line`` 是唯一渲染源，绝不产出 tag 块。
* 解析不出来时**降级而不是报错**：返回低置信度草稿 + ``needs_llm_fallback`` 标记，
  交给 LLM 结构化 + 用户确认（契约不允许 import 直接抛错）。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from .extract import (
    COLUMN_GAP_RE,
    DATE_SPAN_RE,
    DocLine,
    ExtractedDoc,
    SENTENCE_RE,
    join_fragments,
    normalize_text,
)
from . import skills as skills_mod

#: 章节标题别名（归一化后匹配）。value = (bound_package_kind, 是否技能/荣誉等特殊块)
SECTION_ALIASES: dict[str, str] = {
    # 中文
    "教育背景": "education",
    "教育经历": "education",
    "学习经历": "education",
    "学历背景": "education",
    "实习经历": "internship",
    "实习经验": "internship",
    "工作经历": "internship",
    "工作经验": "internship",
    "职业经历": "internship",
    "项目经历": "project",
    "项目经验": "project",
    "科研项目": "project",
    "研究项目": "project",
    "科研经历": "project",
    "校园活动": "campus",
    "校园经历": "campus",
    "学生工作": "campus",
    "社会实践": "campus",
    "校园实践": "campus",
    "职业技能": "skills",
    "专业技能": "skills",
    "技能清单": "skills",
    "技能与证书": "skills",
    "技能证书": "skills",
    "技能": "skills",
    "荣誉奖项": "awards",
    "获奖情况": "awards",
    "荣誉": "awards",
    "自我评价": "summary",
    "个人总结": "summary",
    # 英文（归一化会转小写并去空白）
    "education": "education",
    "internship": "internship",
    "experience": "internship",
    "workexperience": "internship",
    "professionalexperience": "internship",
    "researchprojects": "project",
    "projects": "project",
    "projectexperience": "project",
    "campusactivities": "campus",
    "activities": "campus",
    "leadership": "campus",
    "extracurricularactivities": "campus",
    "skills": "skills",
    "skills&certificates": "skills",
    "technicalskills": "skills",
    "honors&awards": "awards",
    "awards": "awards",
    "summary": "summary",
    "profile": "summary",
}

#: kind → 该区块的 block_type
KIND_BLOCK_TYPE = {
    "education": "section",
    "internship": "section",
    "project": "section",
    "campus": "section",
    "skills": "skills",
    "awards": "awards",
    "summary": "summary",
    "other": "section",
}

_LABEL_RE = re.compile(r"^([\u4e00-\u9fffA-Za-z（）()·\- ]{2,16})[：:]\s*(.*)$")
_ROLE_SPLIT_RE = re.compile(r"\s+[-–—|]\s+")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

#: 结果从句/递进连词：这类句子不单独成 bullet（「最终交付…」「从而…」并入上一条）
_CONTINUATION_PREFIXES = (
    "最终", "从而", "进而", "因此", "所以", "并且", "并", "同时", "以及", "此外",
    "另外", "其后", "随后", "继而", "亦", "且", "并最终",
)


def normalize_heading(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip()).replace("：", "").replace(":", "").lower()


def classify_heading(line: DocLine) -> str | None:
    """章节标题识别：字典命中优先；Markdown/DOCX 的标题样式作为兜底。"""
    key = normalize_heading(line.stripped)
    if key in SECTION_ALIASES:
        return SECTION_ALIASES[key]
    if line.level and len(line.stripped) <= 24:
        return "other"
    return None


def _has_date(text: str) -> bool:
    return bool(DATE_SPAN_RE.search(text or ""))


def _trailing_date(text: str) -> tuple[str | None, str]:
    """``杭州拓端…实习生    2026.07 - 2026.10`` → (日期, 剩余文本)。"""
    stripped = (text or "").strip()
    match = DATE_SPAN_RE.search(stripped)
    if not match:
        return None, stripped
    if match.end() < len(stripped.rstrip(" .。，,")):
        return None, stripped
    return match.group(0).strip(), stripped[: match.start()].rstrip(" \t-–—|")


def _leading_date(text: str) -> tuple[str | None, str]:
    stripped = (text or "").strip()
    match = DATE_SPAN_RE.match(stripped)
    if not match:
        return None, stripped
    return match.group(0).strip(), stripped[match.end():].strip(" \t-–—|")


_SPACE_RUN_RE = re.compile(r"[ \t\u00a0\u3000]{2,}")


def _clean_text(text: str) -> str:
    """折叠 PDF 列对齐产生的连续空白（只改排版空白，不改任何字符）。"""
    return _SPACE_RUN_RE.sub(" ", (text or "").replace("\t", " ")).strip()


_DEGREE_RE = re.compile(r"(本科|硕士|博士|大专|学士|研究生|Bachelor|Master|Ph\.?D)")

_CITY_RE = re.compile(r"^[^,，]{1,20}[,，]\s*[^,，]{1,20}$")


def _looks_city(text: str) -> bool:
    """``Wuhan, China`` / ``Shanghai, China`` 这类城市列（不与专业名混淆）。"""
    stripped = (text or "").strip()
    return bool(_CITY_RE.match(stripped)) and "大学" not in stripped and "University" not in stripped


def _is_entry_start(kind: str, line: DocLine, lines: Sequence[DocLine], index: int) -> bool:
    if not line.bold and not line.level:
        # 非加粗行只有在「教育背景」且行首直接是日期时才作为 entry（TXT/MD 兜底）
        if not (kind == "education" and _has_date(line.stripped) and line.stripped[:1].isdigit()):
            return False
    text = line.stripped
    if _LABEL_RE.match(text) and len(text) > 40:
        return False
    if _has_date(text) and DATE_SPAN_RE.search(text).start() <= 2:
        return True
    if _has_date(text):
        return True
    if index + 1 < len(lines) and _has_date(lines[index + 1].stripped):
        return True
    # 标题折行：加粗标题占两行、日期落在第三行（英文长项目名常见）
    if (
        index + 2 < len(lines)
        and lines[index + 1].bold
        and not lines[index + 1].bullet
        and _has_date(lines[index + 2].stripped)
    ):
        return True
    return False


def _loose_entry_start(line: DocLine) -> bool:
    """无加粗样式来源（Markdown / TXT / 粘贴文本）的 entry 起始判据。

    PDF 靠加粗字体区分条目标题；md/txt 没有样式，只能用「行内出现日期区间且行不长」来判断。
    """
    if line.bullet:
        return False
    text = line.stripped
    if not text or len(text) > 160:
        return False
    if text.endswith(("。", ".", "；", ";")):
        return False
    match = DATE_SPAN_RE.search(text)
    if not match:
        return False
    # 日期在行首（教育背景）或行尾（项目/实习标题）才算条目标题
    return match.start() <= 2 or match.end() >= len(text) - 2


def _fold_lines(lines: Sequence[DocLine]) -> str:
    text = ""
    for line in lines:
        text = join_fragments(text, _clean_text(line.stripped))
    return _clean_text(text)


def _merge_sentences(text: str) -> list[str]:
    """句子 → bullet：结果从句并入上一条，避免把「最终交付…」切成独立条目。"""
    sentences = [item.strip() for item in SENTENCE_RE.findall(text) if item.strip()]
    bullets: list[str] = []
    for sentence in sentences:
        if bullets and (sentence.startswith(_CONTINUATION_PREFIXES) or len(sentence) < 8):
            bullets[-1] = join_fragments(bullets[-1], sentence)
        else:
            bullets.append(sentence)
    return [bullet.strip() for bullet in bullets if bullet.strip()]


def _bullets_from_body(kind: str, body: Sequence[DocLine]) -> tuple[list[str], list[str]]:
    """返回 (bullets, facts)。教育/荣誉用 facts（整行事实，不切句）。"""
    if not body:
        return [], []
    has_marker = any(line.bullet for line in body)
    if has_marker:
        bullets: list[str] = []
        for line in body:
            text = _clean_text(line.stripped)
            if line.bullet or not bullets:
                bullets.append(text)
            else:
                bullets[-1] = _clean_text(join_fragments(bullets[-1], text))
        return [bullet for bullet in bullets if bullet], []

    if kind in ("education", "awards"):
        facts: list[str] = []
        for line in body:
            text = _clean_text(line.stripped)
            if not facts or _LABEL_RE.match(text) or _has_date(text):
                facts.append(text)
            else:
                facts[-1] = _clean_text(join_fragments(facts[-1], text))
        return [], facts

    # 中文简历正文没有项目符号：整段折行 → 句子 → bullet
    flow = _fold_lines(body)
    if any(_LABEL_RE.match(line.stripped) for line in body):
        # 带「曾获荣誉：」「主要活动：」这类标签的段落按标签分条
        bullets: list[str] = []
        for line in body:
            text = _clean_text(line.stripped)
            if _LABEL_RE.match(text) or not bullets:
                bullets.append(text)
            else:
                bullets[-1] = _clean_text(join_fragments(bullets[-1], text))
        return [bullet for bullet in bullets if bullet], []
    return _merge_sentences(flow), []


def _parse_entry(kind: str, entry_lines: Sequence[DocLine], lang: str) -> dict[str, Any]:
    title_line = entry_lines[0]
    body = list(entry_lines[1:])
    segments = [seg.strip() for seg in COLUMN_GAP_RE.split(title_line.stripped) if seg.strip()]

    date_range: str | None = None
    if segments:
        # 列式：日期在最后一列（中文）或第一列（教育背景）
        date_range, rest = _trailing_date(segments[-1])
        if date_range and rest:
            segments[-1] = rest
        elif date_range and not rest:
            segments.pop()
        else:
            lead, rest = _leading_date(segments[0])
            if lead:
                date_range = lead
                if rest:
                    segments[0] = rest
                else:
                    segments.pop(0)

    role_from_body = ""
    if date_range is None and body:
        head = body[0]
        head_segments = [seg.strip() for seg in COLUMN_GAP_RE.split(head.stripped) if seg.strip()]
        candidate = head_segments[-1] if head_segments else ""
        probe, rest = _trailing_date(candidate)
        if probe:
            date_range = probe
            if len(head_segments) > 1:
                role_from_body = " ".join(head_segments[:-1]).strip()
                if rest:
                    role_from_body = (role_from_body + " " + rest).strip()
            else:
                role_from_body = rest
            body = body[1:]
        elif head.italic:
            role_from_body = head.stripped
            body = body[1:]

    entry: dict[str, Any] = {
        "kind": kind,
        "title": "",
        "org": "",
        "role": "",
        "date_range": date_range or "",
        "degree_major": "",
        "city": "",
        "raw_title": title_line.stripped,
    }

    # 末列常是地点（``Wuhan, China``）：抽出来放 city，别当成专业/角色
    if len(segments) > 1 and _looks_city(segments[-1]):
        entry["city"] = segments.pop()

    if kind == "education":
        if segments:
            entry["org"] = segments[0]
        if len(segments) > 1:
            entry["degree_major"] = " ".join(segments[1:]).strip()
        if not entry["degree_major"] and entry["org"]:
            # 单列排版（md/txt）：`示例大学-数据科学学院 数据科学与大数据技术 本科` 整行落在 org
            match = _DEGREE_RE.search(entry["org"])
            if match and match.start() > 0:
                head = entry["org"][: match.start()].strip()
                tail = entry["org"][match.start():].strip()
                if head:
                    entry["org"] = head
                    entry["degree_major"] = tail
        if not entry["degree_major"] and role_from_body:
            entry["degree_major"] = role_from_body
    elif kind == "campus":
        if segments:
            entry["org"] = segments[0]
        if len(segments) > 1:
            entry["role"] = " ".join(segments[1:]).strip()
        elif " " in entry["org"]:
            # 单列排版（md/txt）：`示例大学 班长` 里末段是角色
            head, _, tail = entry["org"].rpartition(" ")
            if head and len(tail) <= 20:
                entry["org"], entry["role"] = head.strip(), tail.strip()
        if not entry["role"] and role_from_body:
            entry["role"] = role_from_body
    else:
        # 列式：``标题 | 角色 | 组织/赛事名``；中文常见「标题 - 角色」
        head_text = segments[0] if segments else ""
        parts = _ROLE_SPLIT_RE.split(head_text)
        if len(parts) >= 2:
            entry["title"] = " - ".join(parts[:-1]).strip()
            entry["role"] = parts[-1].strip()
        else:
            entry["title"] = head_text
        if len(segments) > 1 and not entry["role"]:
            entry["role"] = segments[1]
        if len(segments) > 2:
            entry["org"] = " ".join(segments[2:]).strip()
        if kind == "internship" and not entry["org"]:
            entry["org"] = entry["title"]

    if kind in ("project", "internship", "campus") and not entry["role"] and role_from_body:
        entry["role"] = role_from_body

    bullets, facts = _bullets_from_body(kind, body)
    entry["bullets"] = bullets
    entry["facts"] = facts
    return entry


def _split_entries(kind: str, lines: Sequence[DocLine], lang: str) -> list[dict[str, Any]]:
    groups: list[list[DocLine]] = []
    loose: list[DocLine] = []
    current: list[DocLine] | None = None
    styled = any(line.bold or line.level for line in lines)
    for index, line in enumerate(lines):
        is_start = _is_entry_start(kind, line, lines, index) or (
            not styled and _loose_entry_start(line)
        )
        if is_start:
            # 英文长标题会折成两行加粗：上一行没有日期且正文为空 → 视为同一 entry 的标题续行
            if (
                current is not None
                and len(current) == 1
                and not current[0].bullet
                and not _has_date(current[0].stripped)
                and not _has_date(line.stripped)
                and line.bold
                and abs(line.x0 - current[0].x0) <= 3
            ):
                merged = DocLine(
                    text=join_fragments(current[0].stripped, line.stripped),
                    page=line.page,
                    top=current[0].top,
                    x0=current[0].x0,
                    size=current[0].size,
                    bold=True,
                )
                # 就地替换（不能重新赋值 current，否则 groups 里留的是旧列表，正文会丢）
                current[0] = merged
                continue
            current = [line]
            groups.append(current)
        elif current is not None:
            current.append(line)
        else:
            loose.append(line)
    entries = [_parse_entry(kind, group, lang) for group in groups]
    if loose:
        for entry in entries:
            entry["loose_prefix"] = [line.stripped for line in loose]
            break
        else:
            entries.append(
                {
                    "kind": kind,
                    "title": "",
                    "org": "",
                    "role": "",
                    "date_range": "",
                    "degree_major": "",
                    "bullets": _merge_sentences(_fold_lines(loose)),
                    "facts": [],
                    "loose_prefix": [],
                }
            )
    return entries


def _group_skill_lines(body: Sequence[DocLine]) -> list[str]:
    if not body:
        return []
    base_x0 = min(line.x0 for line in body)
    rows: list[str] = []
    for line in body:
        text = _clean_text(line.stripped)
        new_row = bool(_LABEL_RE.match(text)) or line.x0 <= base_x0 + 2 or not rows
        if new_row:
            rows.append(text)
        else:
            rows[-1] = join_fragments(rows[-1], text)
    return [row for row in rows if row]


def sections_from_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 blocks 派生 sections 摘要（heading / block_type / entry_count 全部同源）。"""
    sections: list[dict[str, Any]] = []
    for block in blocks:
        block_type = block.get("block_type")
        if block_type not in ("section", "skills", "awards", "summary"):
            continue
        bound = block.get("bound_package_kind")
        kind = "skills" if (block_type == "skills" or bound == "skill") else (bound or block_type)
        sections.append(
            {
                "kind": kind,
                "heading": block.get("heading") or "",
                "block_type": block_type,
                "bound_package_kind": bound,
                "entry_count": int(block.get("entry_count") or 0),
            }
        )
    return sections


def parse_document(doc: ExtractedDoc) -> dict[str, Any]:
    """抽取结果 → 草稿结构（blocks / skills / identity hints）。"""
    lang = doc.lang
    lines = [line for line in doc.lines if line.stripped]
    headings: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        kind = classify_heading(line)
        if kind:
            headings.append((index, kind))

    # 开头的 `# 张三` 这类标题级别行不是章节，属于抬头信息
    if headings:
        first_known = next((i for i, (_, kind) in enumerate(headings) if kind != "other"), None)
        if first_known is None:
            headings = []
        elif first_known > 0:
            headings = headings[first_known:]

    warnings = list(doc.warnings)
    blocks: list[dict[str, Any]] = []
    order = 10

    header_lines = lines[: headings[0][0]] if headings else lines[:3]
    if header_lines:
        header_text = [line.stripped for line in header_lines]
        identity = _identity_hints(header_text)
        slots = [
            {"slot_key": "candidate.name", "slot_type": "text", "bound_field": "profile.name_zh",
             "suggested_value": identity.get("name") or "", "required": True},
            {"slot_key": "candidate.school", "slot_type": "text", "bound_field": "profile.school_zh",
             "suggested_value": identity.get("school") or "", "required": True},
            {"slot_key": "candidate.available", "slot_type": "text", "bound_field": "profile.available_note",
             "suggested_value": identity.get("available") or "", "required": False},
            {"slot_key": "candidate.phone", "slot_type": "text", "bound_field": "profile.phone",
             "suggested_value": identity.get("phone") or "", "required": False},
            {"slot_key": "candidate.email", "slot_type": "text", "bound_field": "profile.email",
             "suggested_value": identity.get("email") or "", "required": False},
            {"slot_key": "candidate.photo", "slot_type": "image", "bound_field": "profile.photo_path",
             "suggested_value": "", "required": False},
        ]
        blocks.append(
            {
                "temp_id": "tb-header",
                "parent_temp_id": None,
                "order_index": 0,
                "block_type": "header",
                "heading": None,
                "bound_package_kind": None,
                "confidence": 0.95 if identity.get("name") else 0.6,
                "preview_text": " / ".join(header_text)[:200],
                "text": header_text,
                "slots": slots,
            }
        )

    if not headings:
        warnings.append(
            {
                "code": "NO_SECTION_HEADING",
                "count": 1,
                "message": "未识别到章节标题，已按整篇文本生成低置信度草稿，建议转 LLM 结构化后人工确认",
                "severity": "warn",
            }
        )

    found_kinds: list[str] = []
    entry_counts: dict[str, int] = {}
    for heading_index, (line_index, kind) in enumerate(headings):
        end = headings[heading_index + 1][0] if heading_index + 1 < len(headings) else len(lines)
        body = lines[line_index + 1 : end]
        heading_text = lines[line_index].stripped
        found_kinds.append(kind)
        order += 10
        section_id = f"tb-s{heading_index + 1}"
        block_type = KIND_BLOCK_TYPE.get(kind, "section")

        if kind == "skills":
            rows = skills_mod.build_skill_rows(_group_skill_lines(body), start_order=10)
            entry_counts["skills"] = len(rows)
            blocks.append(
                {
                    "temp_id": section_id,
                    "parent_temp_id": None,
                    "order_index": order,
                    "block_type": "skills",
                    "heading": heading_text,
                    "bound_package_kind": "skill",
                    "confidence": 0.95,
                    "entry_count": len(rows),
                    "preview_text": " / ".join(row["line"] for row in rows)[:200],
                    "skill_lines": rows,
                    # 技能块只绑定 profile.skills_json（整句行数组），不做 tag 渲染
                    "slots": [
                        {"slot_key": "skills.lines", "slot_type": "longtext",
                         "bound_field": "profile.skills_json", "required": True}
                    ],
                }
            )
            continue

        entries = _split_entries(kind, body, lang)
        entry_counts[kind] = len(entries)
        blocks.append(
            {
                "temp_id": section_id,
                "parent_temp_id": None,
                "order_index": order,
                "block_type": block_type,
                "heading": heading_text,
                "bound_package_kind": kind,
                "confidence": 0.92 if entries else 0.5,
                "entry_count": len(entries),
                "preview_text": ((entries[0].get("raw_title") or "") if entries else "")[:200],
                "slots": [],
            }
        )
        for entry_index, entry in enumerate(entries, start=1):
            blocks.append(
                {
                    "temp_id": f"{section_id}-e{entry_index}",
                    "parent_temp_id": section_id,
                    "order_index": order + entry_index,
                    "block_type": "entry",
                    "heading": None,
                    "bound_package_kind": kind,
                    "confidence": 0.85 if entry.get("date_range") else 0.6,
                    "preview_text": ((entry.get("raw_title") or entry.get("title") or ""))[:200],
                    "entry": entry,
                    "slots": _entry_slots(kind, entry),
                }
            )

    section_count = len([kind for kind in found_kinds if kind in ("education", "internship", "project", "campus", "skills")])
    residual_cid = doc.raw_text.count("(cid:")
    replaced = doc.raw_text.count("\ufffd")
    needs_llm = section_count < 2 or not any(b["block_type"] == "header" for b in blocks)
    if needs_llm:
        warnings.append(
            {
                "code": "IMPORT_FALLBACK_LLM",
                "count": 1,
                "message": "启发式解析可用的结构不足，草稿已保留原文，建议转 LLM 结构化后由用户确认",
                "severity": "warn",
            }
        )

    draft = {
        "lang": lang,
        "parser": doc.parser,
        "pages": doc.pages,
        # D-25：sections[] 由 blocks **派生**（blocks 是唯一真值源），避免两套结构漂移
        "sections": sections_from_blocks(blocks),
        "section_kinds": list(dict.fromkeys(found_kinds)),
        "entry_counts": entry_counts,
        "blocks": blocks,
        "skills": [row for block in blocks if block["block_type"] == "skills" for row in block.get("skill_lines", [])],
        "stats": doc.stats(),
        "warnings": warnings,
        "needs_llm_fallback": needs_llm,
        "quality": {
            "sections_found": len(dict.fromkeys(found_kinds)),
            "cid_residual": residual_cid,
            "replacement_chars": replaced,
            # 仅表示未做二次数字核对（导入阶段禁止润色，原文逐字保留）
            "numbers_second_pass": False,
        },
    }
    return draft


def _entry_slots(kind: str, entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    if kind == "education":
        slots.append({"slot_key": "entry.org", "slot_type": "text", "bound_field": "profile.school_zh",
                      "suggested_value": entry.get("org") or "", "required": True})
        slots.append({"slot_key": "entry.degree_major", "slot_type": "text", "bound_field": "profile.major",
                      "suggested_value": entry.get("degree_major") or "", "required": False})
    else:
        slots.append({"slot_key": "entry.title", "slot_type": "text", "bound_field": "package.title",
                      "suggested_value": entry.get("title") or "", "required": True})
        slots.append({"slot_key": "entry.role", "slot_type": "text", "bound_field": "package.role",
                      "suggested_value": entry.get("role") or "", "required": False})
    slots.append({"slot_key": "entry.date_range", "slot_type": "date_range", "bound_field": None,
                  "suggested_value": entry.get("date_range") or "", "required": False})
    slots.append({"slot_key": "entry.bullets", "slot_type": "longtext", "bound_field": None,
                  "suggested_value": "".join(entry_lines(entry)), "required": False})
    return slots


def entry_lines(entry: Mapping[str, Any]) -> list[str]:
    """条目正文的**唯一**取法：``bullets`` 与 ``facts`` 一视同仁，按原文顺序拼。

    教育/荣誉段落在草稿里存成 ``facts``（整行事实，不切句），项目/实习存成 ``bullets``。
    组装（t6）与渲染（t8）都必须走这个函数，否则 GPA / CET / 课程这类 ``facts`` 会被静默丢掉。
    """
    lines = [str(item) for item in (entry.get("bullets") or []) if str(item).strip()]
    lines.extend(str(item) for item in (entry.get("facts") or []) if str(item).strip())
    return lines


def _identity_hints(header_lines: Sequence[str]) -> dict[str, str]:
    joined = "\n".join(header_lines)
    hints: dict[str, str] = {}
    for line in header_lines:
        text = line.strip()
        if not hints.get("name") and re.fullmatch(r"[\u4e00-\u9fff·]{2,6}|[A-Z][A-Z .'\-]{2,40}", text):
            hints["name"] = text
    phone = _PHONE_RE.search(joined)
    if phone:
        hints["phone"] = phone.group(0)
    email = _EMAIL_RE.search(joined)
    if email:
        hints["email"] = email.group(0)
    for line in header_lines:
        if "到岗" in line or "available" in line.lower():
            match = re.search(r"(?:到岗时间|Available)\s*[：:]\s*([^｜|\n]+)", line, re.IGNORECASE)
            if match:
                hints["available"] = match.group(1).strip()
            break
    for line in header_lines:
        text = re.split(r"[-｜|,，]", line)[0].strip()
        if text and text not in (hints.get("name"),) and len(text) <= 40 and not _PHONE_RE.search(text):
            if re.search(r"大学|学院|University|College|Institute", text):
                hints["school"] = text
                break
    return hints


def render_markdown(draft: Mapping[str, Any]) -> str:
    """把草稿按 block 层级缩进打印，给用户直接过目。"""
    lines: list[str] = [f"# 导入草稿（lang={draft.get('lang')} · parser={draft.get('parser')}）", ""]
    stats = draft.get("stats") or {}
    lines.append(
        f"页数 {stats.get('pages')} · 字符 {stats.get('chars')} · 空行 {stats.get('lines')} · "
        f"图片 {stats.get('images')} · cid 清理 {stats.get('cid_missing')}"
    )
    lines.append("")
    for block in draft.get("blocks") or []:
        depth = 1 if block.get("parent_temp_id") else 0
        indent = "  " * depth
        kind = block.get("block_type")
        if kind == "header":
            lines.append(f"{indent}- **header** (confidence {block.get('confidence')})")
            for text in block.get("text") or []:
                lines.append(f"{indent}  - {text}")
        elif kind == "skills":
            lines.append(f"{indent}- **skills** 「{block.get('heading')}」 {block.get('entry_count')} 行")
            for row in block.get("skill_lines") or []:
                lines.append(f"{indent}  - {row['line']}")
        elif kind == "entry":
            entry = block.get("entry") or {}
            header = " · ".join(
                filter(None, [entry.get("title") or entry.get("org"), entry.get("role"), entry.get("date_range"),
                              entry.get("degree_major")])
            )
            lines.append(f"{indent}- **entry** {header}")
            for body_line in entry_lines(entry):
                lines.append(f"{indent}  - {body_line}")
        else:
            lines.append(f"{indent}- **{kind}** 「{block.get('heading')}」 {block.get('entry_count')} entry")
    return "\n".join(lines) + "\n"
