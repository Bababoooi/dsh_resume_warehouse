"""组装：把「构建 + 选中的 package/变体 + 模板 + 档案」拼成与渲染无关的 IR。

设计要点
--------

* **IR 是唯一真值**：HTML 预览、PDF、DOCX、文本校验全部从同一份 IR 渲染，
  因此 `compare_text` 的差异只可能来自引擎，不会来自「两份数据」。
* **模板决定结构，package 提供内容**：`template_block` 给出 section 顺序与标题，
  `build.sections_order` 可覆盖（用户在导出页拖拽）。
* **三条用户裁决写死在这里**（ARCHITECTURE §7.6）：
  1. 荣誉不单独成节——`awards` 不产生独立 section，而是并进「校园活动」的 bullet；
  2. 职业技能**逐行原文**，不做 tag 化、不切分；
  3. 教育段 `facts` 整段文字（行首不加 ``·``）。
* 照片只在渲染阶段读字节（`photo_path` 传相对路径），**永不进 LLM payload**。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from . import i18n

SECTION_KINDS: tuple[str, ...] = ("education", "internship", "project", "activity", "awards")

HEADINGS_ZH: dict[str, str] = {
    "education": "教育背景",
    "internship": "实习经历",
    "project": "项目经历",
    "activity": "校园活动",
    "awards": "荣誉奖项",
    "skills": "职业技能",
    "summary": "个人简介",
}

#: 英文标题严格照抄契约 §8.5.1（Title Case，不是全大写）
HEADINGS_EN: dict[str, str] = {
    "education": i18n.HEADING_BY_KIND["education"][1],
    "internship": i18n.HEADING_BY_KIND["experience"][1],
    "project": i18n.HEADING_BY_KIND["projects"][1],
    "activity": i18n.HEADING_BY_KIND["campus"][1],
    "awards": i18n.HEADING_BY_KIND["honors"][1],
    "skills": i18n.HEADING_BY_KIND["skills"][1],
    "summary": i18n.HEADING_BY_KIND["summary"][1],
}

#: package.kind → section kind（DB 里 campus 落 activity、award 落 awards）
PACKAGE_TO_SECTION: dict[str, str] = {
    "education": "education",
    "internship": "internship",
    "project": "project",
    "activity": "activity",
    "custom": "project",
    "award": "awards",
}

_SPACE_RE = re.compile(r"[ \t\u00a0\u3000]{2,}")
_ZH_DATE_RE = re.compile(r"(\d{4})\s*[.\-/年]\s*(\d{1,2})?\s*(?:月)?\s*(?:[-–—~至]\s*(\d{4})?\s*[.\-/年]?\s*(\d{1,2})?\s*(?:月)?)?\s*(至今|今|present|now)?", re.I)


def tidy(text: str) -> str:
    """折叠排版空白（不删字、不改标点），把软换行并回一行。"""
    if not text:
        return ""
    merged = " ".join(part.strip() for part in str(text).splitlines() if part.strip())
    return _SPACE_RE.sub(" ", merged).strip()


def heading_for(kind: str, lang: str) -> str:
    table = HEADINGS_EN if lang == "en" else HEADINGS_ZH
    return table.get(kind, kind.upper() if lang == "en" else kind)


def format_date_range(start: str | None, end: str | None, *, is_current: bool, lang: str) -> str:
    """日期区间：中文 ``2026.07 - 2026.10`` / 英文 ``07/2026 – 10/2026``。"""
    def parse(value: str | None) -> tuple[str, str] | None:
        if not value:
            return None
        match = re.search(r"(\d{4})\s*[.\-/年]\s*(\d{1,2})?", str(value))
        if not match:
            return None
        return match.group(1), match.group(2) or ""

    left = parse(start)
    right = parse(end)
    if is_current or (end and re.search(r"至今|present|now", str(end), re.I)):
        right = None
        current = True
    else:
        current = False

    if lang == "en":
        def show(item: tuple[str, str] | None) -> str:
            if item is None:
                return "Present"
            year, month = item
            name = i18n._month_name(int(month)) if month else ""
            return f"{name} {year}" if name else year
    else:
        def show(item: tuple[str, str] | None) -> str:
            if item is None:
                return "至今"
            year, month = item
            return f"{year}.{int(month)}" if month else year

    if left is None and right is None and not current:
        return ""
    if left is None:
        return show(right) if not current else "至今" if lang != "en" else "Present"
    tail = "Present" if (current and lang == "en") else ("至今" if current else show(right))
    if tail is None or tail == "":
        return show(left)
    joiner = " – " if lang == "en" else " - "
    return f"{show(left)}{joiner}{tail}"


def _education_date_text(date_range: str, grad_year: str, lang: str) -> str:
    """教育段日期：导入时的 ``2024.9 - 2028.6`` 原样还原（中英各自格式），无区间才退毕业年。"""
    text = (date_range or "").strip()
    if text:
        parts = [part.strip() for part in re.split(r"\s*[-–—~至]\s*", text) if part.strip()]
        if len(parts) >= 2:
            start, end = parts[0], parts[-1]
            if lang == "en":
                return f"{i18n.date_point_en(start)} – {i18n.date_point_en(end)}"
            return f"{start} - {end}"
        if lang == "en" and grad_year:
            return f"Class of {grad_year}"
        return text
    if not grad_year:
        return ""
    return f"Class of {grad_year}" if lang == "en" else grad_year


def _variant_texts(
    package: Mapping[str, Any],
    variants: Sequence[Mapping[str, Any]],
    chosen_ids: Sequence[str],
    *,
    lang: str,
    fallback: dict[str, Any] | None = None,
    entry_title: str = "",
) -> list[str]:
    """取该 package 的要点文本：**本语言变体优先**，没有才回退。

    顺序：显式 ``variant_ids`` 里**属于本语言**的 > 本语言 verified > 本语言全部 >
    任意语言（回退，必须逐条记账 → ``LANG_FALLBACK.details.entries[]``）。

    为什么要先按语言筛 ``variant_ids``：组装页里的 variant_ids 是**上一次**选择留下的，
    切到英文后沿用它们会让整篇「英文版」其实全是中文原文（实测 38 行里 37 行中文，
    而仓库里明明有 11 条英文变体）。语言是导出的硬属性，不该被上一次的勾选悄悄覆盖。
    """
    by_id = {str(item.get("id")): item for item in variants}
    same_lang_pool = [item for item in variants if str(item.get("lang") or "zh") == lang]
    ordered: list[Mapping[str, Any]] = []
    for variant_id in chosen_ids:
        item = by_id.get(str(variant_id))
        if item is not None and str(item.get("lang") or "zh") == lang:
            ordered.append(item)
    if not ordered and same_lang_pool:
        verified = [item for item in same_lang_pool if int(item.get("verified") or 0) == 1]
        ordered = verified or same_lang_pool
    if not ordered and variants:
        # 这个包确实没有本语言变体：允许沿用其它语言正文，但必须让用户看见
        ordered = list(variants)

    seen: set[str] = set()
    texts: list[str] = []
    fell_back: list[dict[str, Any]] = []
    for item in ordered:
        # 同一 bullet_key 只保留一条（防止 impact + technical 双写同一事实）
        key = str(item.get("bullet_key") or item.get("text"))
        if key in seen:
            continue
        seen.add(key)
        text = tidy(str(item.get("text") or ""))
        if not text:
            continue
        texts.append(text)
        item_lang = str(item.get("lang") or "zh")
        if item_lang != lang:
            fell_back.append(
                {
                    "title": entry_title or tidy(str(package.get("title") or "")),
                    "bullet_key": str(item.get("bullet_key") or ""),
                    "variant_id": str(item.get("id") or ""),
                    "variant_lang": item_lang,
                    "preview": text[:40],
                    "reason": f"该要点没有 {lang} 变体",
                }
            )
    if not texts:
        # 没有任何变体时退回 package.summary，避免整条经历凭空消失
        summary = tidy(str(package.get("summary") or ""))
        if summary:
            texts.append(summary)

    if fallback is not None and texts:
        if fell_back:
            fallback["used"] = True
            fallback["entries"] += 1
            fallback["bullets"] += len(fell_back)
            title = entry_title or tidy(str(package.get("title") or ""))
            if title and title not in fallback["titles"]:
                fallback["titles"].append(title)
            fallback["samples"].append(tidy(texts[0])[:60])
            # entries[] 按「条目」聚合、每条列出回退的要点（用户要能一眼看出是哪几句）
            fallback.setdefault("details", []).append(
                {
                    "title": title,
                    "bullet_count": len(fell_back),
                    "bullets": fell_back,
                    "reason": f"该条目没有 {lang} 变体",
                }
            )
    return texts



def _rendered_cjk_lines(sections: Sequence[Mapping[str, Any]], *, lang: str) -> list[str]:
    """按渲染口径数「会印到纸上的、含中文的行」。

    为什么要单独算：``LANG_FALLBACK`` 只记账「变体回退」，可英文简历里的中文还有
    别的来路（学历行的中文标签、技能区原文、条目标题本身）。用户看到的是一行行中文，
    不是我们的数据结构，所以声明必须按**行**给，才能和 PDF 抽取结果对得上。
    """
    if lang != "en":
        return []
    lines: list[str] = []

    def push(text: Any) -> None:
        value = tidy(str(text or ""))
        if value and i18n.has_cjk(value):
            lines.append(value)

    for section in sections:
        for entry in section.get("entries") or []:
            # 条目头是**一行**（标题 · 角色 · 机构 · 日期右对齐），三处中文只占一行，
            # 逐字段数会多算，与 PDF 对不上。
            head = " ".join(tidy(str(entry.get(key) or "")) for key in ("title", "role", "org"))
            push(head)
            for bullet in entry.get("bullets") or []:
                push(bullet)
            for fact in entry.get("facts") or []:
                push(fact)
        for line in section.get("skills") or []:
            push(line)
    return lines


def _entry_from_package(
    package: Mapping[str, Any],
    variants: Sequence[Mapping[str, Any]],
    selection: Mapping[str, Any],
    *,
    lang: str,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    overrides = selection.get("overrides") or {}
    entry_title = tidy(str(overrides.get("title_display") or package.get("title") or ""))
    texts = _variant_texts(
        package,
        variants,
        selection.get("variant_ids") or [],
        lang=lang,
        fallback=fallback,
        entry_title=entry_title,
    )

    return {
        "package_id": package.get("id"),
        "title": tidy(str(overrides.get("title_display") or _lang_value(package, "title", lang) or "")),
        "org": tidy(str(overrides.get("org_display") or _lang_value(package, "org", lang) or "")),
        "role": tidy(str(overrides.get("role_display") or _lang_value(package, "role", lang) or "")),
        "location": tidy(str(overrides.get("location_display") or package.get("location") or "")),
        "date": format_date_range(
            package.get("start_date"),
            package.get("end_date"),
            is_current=bool(package.get("is_current")),
            lang=lang,
        ),
        "bullets": texts,
        "facts": [],
    }


def _education_from_profile(
    profile: Mapping[str, Any], *, lang: str, warnings: list[dict[str, Any]] | None = None
) -> dict[str, Any] | None:
    school = profile.get("school_en") if lang == "en" else profile.get("school_zh")
    school = school or profile.get("school_zh") or profile.get("school_en")
    extra_profile = profile.get("extra") or {}
    if lang == "en":
        degree = str(extra_profile.get("degree_en") or "")
        major = str(extra_profile.get("major_en") or "")
        if not (degree or major) and warnings is not None:
            warnings.append(
                {
                    "code": "PROFILE_FIELD_MISSING",
                    "severity": "warn",
                    "message": "英文版缺少学历/专业的英文值，已省略该行（不会把中文写进英文简历）",
                    "details": {"fields": ["degree_en", "major_en"], "lang": "en"},
                }
            )
    else:
        degree = profile.get("degree") or ""
        major = profile.get("major") or ""
    grad_year = str(extra_profile.get("education_date_range") or "") or str(profile.get("grad_year") or "")
    if not (school or major or degree):
        return None
    facts: list[str] = []
    extra = profile.get("extra") or {}
    for key in ("gpa", "ranking", "cet", "courses"):
        value = extra.get(key)
        if isinstance(value, str) and value.strip():
            label = {"gpa": "GPA", "ranking": "排名", "cet": "语言", "courses": "主修课程"}[key]
            facts.append(f"{label}：{value.strip()}")
    title = school
    if lang == "en":
        # 英文习惯是「B.M. in Management Science」；空格直拼会读成
        # 「Wuhan University B.M. Management Science」，缺连接词。
        if degree and major:
            org = f"{degree} in {major}"
        else:
            org = " ".join(part for part in (degree, major) if part)
    else:
        org = " ".join(part for part in (degree, major) if part)
    return {
        "package_id": None,
        "title": tidy(title),
        "org": tidy(org),
        "role": "",
        "location": tidy(
            str(
                ((profile.get("extra") or {}).get("city_en") or "")
                if lang == "en"
                else (profile.get("city") or "")
            )
        ),
        "date": tidy(_education_date_text(str(extra_profile.get("education_date_range") or ""), grad_year, lang)),
        # 同值别名：组装 IR 的消费方既有读 `date` 的（渲染），也有要 `date_range` 的
        # （导出验收与命名模板），两处必须是同一个字符串，不能各算一遍。
        "date_range": tidy(
            _education_date_text(str(extra_profile.get("education_date_range") or ""), grad_year, lang)
        ),
        "bullets": [],
        "facts": [
            tidy(i18n.translate_labels_in_text(item) if lang == "en" else item)
            for item in facts
            if tidy(item)
        ],
    }


def _lang_value(obj: Mapping[str, Any], base: str, lang: str) -> Any:
    """``lang=en`` 且存在非空 ``<base>_en`` 时取英文列，否则回落中文列。

    英文版不能靠导出时现翻（那会破坏「预览==导出」「同输入同产物」「用户改过不被
    覆盖」三件事），所以英文原文存在库里；缺英文就整行回退并计入 LANG_FALLBACK。
    """
    if lang == "en":
        value = obj.get(f"{base}_en")
        if value is not None and str(value).strip():
            return value
    return obj.get(base)


def _static_texts(
    blocks: Sequence[Mapping[str, Any]], *, lang: str = "zh"
) -> dict[str, list[str]]:
    """按 section kind 归集模板里的静态文本（``template_block.static_text``）。

    静态文本是「用户自己简历里就写死的那几行」——教育段的 GPA/CET/主修课程、
    技能逐行原文。它们不属于任何 Experience Package，必须从模板块读回来；
    否则导出时会因为 profile 某字段为空而整段消失（t8 实测到的空骨架问题）。
    """
    by_id = {str(block.get("id")): block for block in blocks}
    out: dict[str, list[str]] = {}

    def kind_of(block: Mapping[str, Any]) -> str | None:
        node: Mapping[str, Any] | None = block
        depth = 0
        while node is not None and depth < 6:
            if node.get("block_type") == "skills":
                return "skills"
            raw = node.get("bound_package_kind") or node.get("block_type")
            if raw in HEADINGS_ZH or raw in ("skill", "award"):
                return {"skill": "skills", "award": "awards"}.get(str(raw), str(raw))
            node = by_id.get(str(node.get("parent_block_id"))) if node.get("parent_block_id") else None
            depth += 1
        return None

    for block in sorted(blocks, key=lambda item: int(item.get("order_index") or 0)):
        zh_text = str(block.get("static_text") or "").strip()
        en_text = str(block.get("static_text_en") or "").strip()
        text = en_text if (lang == "en" and en_text) else zh_text
        if not text:
            continue
        kind = kind_of(block)
        if not kind:
            continue
        out.setdefault(kind, []).extend(line.strip() for line in text.splitlines() if line.strip())
    return out


def _sections_from_template(blocks: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """从模板顶层块推出 ``[(kind, heading)]``（保持 order_index 顺序）。"""
    result: list[tuple[str, str]] = []
    for block in sorted(
        (item for item in blocks if not item.get("parent_block_id")),
        key=lambda item: int(item.get("order_index") or 0),
    ):
        block_type = str(block.get("block_type") or "")
        if block_type == "skills":
            result.append(("skills", str(block.get("heading") or "")))
            continue
        if block_type in {"section", "awards", "summary"}:
            kind = str(block.get("bound_package_kind") or block_type)
            kind = {"skill": "skills", "award": "awards"}.get(kind, kind)
            if kind in {"section"} or kind not in HEADINGS_ZH:
                continue
            result.append((kind, str(block.get("heading") or "")))
    return result


def _default_sections() -> list[tuple[str, str]]:
    return [("education", ""), ("internship", ""), ("project", ""), ("activity", ""), ("skills", "")]


def _apply_order(sections: list[dict[str, Any]], order: Iterable[str]) -> list[dict[str, Any]]:
    order_list = [str(item) for item in order if str(item)]
    if not order_list:
        return sections
    ranked = {kind: index for index, kind in enumerate(order_list)}
    return sorted(sections, key=lambda section: (ranked.get(section["kind"], 999), sections.index(section)))


COURSES_LABEL = "主修课程："
COURSES_MIN_KEEP = 3


def trim_courses(ir: dict[str, Any], *, min_keep: int = COURSES_MIN_KEEP) -> tuple[int, int]:
    """把教育段「主修课程：」整句裁到 ``min_keep`` 门（AC-SKILL-04）。

    用户口径：课程默认全留（``trim_courses`` 默认 **false**），只有在导出时显式打开才裁，
    且必须保留「主修课程：」前缀、至少 3 门、把「裁剪前 N 门 → 裁剪后 M 门」写进 warnings。
    只改 ``facts`` 里的课程行，其他事实（GPA/四六级）一个字都不动。
    """
    before = after = 0
    for section in ir.get("sections") or []:
        if section.get("kind") != "education":
            continue
        for entry in section.get("entries") or []:
            facts = entry.get("facts") or []
            for index, line in enumerate(list(facts)):
                text = str(line or "")
                pos = text.find("主修课程")
                if pos < 0:
                    continue
                tail_start = pos + len(COURSES_LABEL)
                prefix = text[:tail_start]
                body = text[tail_start:]
                suffix = "等。" if body.rstrip().endswith("等。") else ""
                items = [item for item in re.split(r"[、，,；;]", body.rstrip("等。")) if item.strip()]
                before += len(items)
                kept = items[: max(int(min_keep), COURSES_MIN_KEEP)]
                after += len(kept)
                facts[index] = prefix + "、".join(kept) + suffix
            entry["facts"] = facts
    return before, after


def build_ir(
    build: Mapping[str, Any],
    *,
    selections: Sequence[Mapping[str, Any]],
    packages: Mapping[str, Mapping[str, Any]],
    variants_by_package: Mapping[str, Sequence[Mapping[str, Any]]],
    blocks: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any],
    include_photo: bool = True,
) -> dict[str, Any]:
    """生成 IR。``packages`` 是 ``package_id -> package``，避免重复查询。"""
    lang = str(build.get("lang") or "zh")
    warnings: list[dict[str, Any]] = []

    # ---- header -------------------------------------------------------
    name = (profile.get("name_en") or profile.get("name_zh")) if lang == "en" else (
        profile.get("name_zh") or profile.get("name_en")
    )
    school = (profile.get("school_en") or profile.get("school_zh")) if lang == "en" else (
        profile.get("school_zh") or profile.get("school_en")
    )
    extra_profile = profile.get("extra") or {}
    # 页眉组成白名单（契约 §8.6）：姓名 / 手机 / 邮箱 / 到岗时间。
    # 学历、专业、届别属于「教育背景」段正文：契约 §8.6.1 明令禁止把它们做成页眉字段，
    # 否则同一信息会在页眉与教育段各出现一次（用户实测报过「页眉重复教育信息」）。
    contact_bits = [str(profile.get("phone") or ""), str(profile.get("email") or "")]
    _missing_en: list[str] = []
    if lang == "en":
        for key, label in (("city_en", "city"), ("available_note_en", "available_note")):
            if not str(extra_profile.get(key) or "").strip():
                _missing_en.append(label)
        if _missing_en and warnings is not None:
            warnings.append(
                {
                    "code": "PROFILE_FIELD_MISSING",
                    "severity": "warn",
                    "message": "英文版缺少城市/到岗时间的英文值，已省略（不会把中文写进英文简历）",
                    "details": {"fields": _missing_en, "lang": "en"},
                }
            )
    header = {
        "name": tidy(str(name or "")),
        "school": tidy(str(school or "")),
        "contact_line": tidy(" | ".join(part for part in contact_bits if part)),
        "city": tidy(
            str(
                extra_profile.get("city_en") or ""
                if lang == "en"
                else (profile.get("city") or "")
            )
        ),
        "available": tidy(
            str(
                # 英文版：优先用户写的英文表述；没写就回退中文真值（用户口径「中文简历为准」），
                # 不要留空——页眉第三行空着会让英文版看起来像没填到岗时间。
                extra_profile.get(f"available_note_{lang}")
                or profile.get("available_note")
                or profile.get("available_date")
                or ""
            )
        ),
        "labels": (
            {"available": i18n.label_en("到岗时间")}
            if lang == "en"
            else {"available": "到岗时间"}
        ),
        "photo_path": None,
        "target_position": tidy(str(build.get("position") or "")),
        "target_company": tidy(str(build.get("company") or "")),
    }
    photo_path = str(profile.get("photo_path") or "").strip()
    if include_photo and photo_path:
        header["photo_path"] = photo_path
    elif not photo_path:
        warnings.append(
            {
                "code": "PHOTO_MISSING",
                "severity": "info",
                "message": "个人资料里没有照片，导出时按无照片版式排版（不留空洞）",
                "details": {"include_photo": include_photo},
            }
        )

    # ---- sections -----------------------------------------------------
    template_sections = _sections_from_template(blocks)
    if not template_sections:
        warnings.append(
            {
                "code": "TEMPLATE_EMPTY",
                "severity": "warn",
                "message": "模板没有可用的 section 块，已按默认顺序（教育/实习/项目/校园/技能）排版",
                "details": {"template_id": build.get("template_id")},
            }
        )
        template_sections = _default_sections()

    # awards 不单独成节（用户裁决）：并进 activity
    merged: list[tuple[str, str]] = []
    for kind, heading in template_sections:
        if kind == "awards":
            if not any(item[0] == "activity" for item in merged):
                merged.append(("activity", ""))
            continue
        if kind == "summary":
            continue
        if kind not in {item[0] for item in merged}:
            merged.append((kind, heading))

    sections: list[dict[str, Any]] = []

    summary_text = tidy(str((build.get("field_values") or {}).get("summary.text") or ""))
    if summary_text:
        sections.append(
            {
                "kind": "summary",
                "heading": heading_for("summary", lang),
                "entries": [{"title": "", "org": "", "role": "", "date": "", "bullets": [summary_text], "facts": []}],
                "skills": [],
            }
        )

    static_by_kind = _static_texts(blocks, lang=lang)
    fallback_state: dict[str, Any] = {
        "used": False,
        "entries": 0,
        "bullets": 0,
        "titles": [],
        "skills": False,
        "samples": [],
    }
    omitted_sections: list[str] = []
    unmapped_headings: list[str] = []

    for kind, heading in merged:
        heading = heading or heading_for(kind, lang)
        if lang == "en" and i18n.has_cjk(heading):
            mapped = i18n.heading_en(heading)
            if mapped:
                heading = mapped
            else:
                unmapped_headings.append(heading)
        entries: list[dict[str, Any]] = []
        if kind == "education":
            profile_entry = _education_from_profile(profile, lang=lang, warnings=warnings)
            facts = list(static_by_kind.get("education") or [])
            if lang == "en" and facts:
                # 有英文原文就整行英文；没有就整行保留中文（不许半翻译），并计入回退
                if any(i18n.has_cjk(item) for item in facts):
                    fallback_state["used"] = True
                    fallback_state["entries"] += 1
                    fallback_state["bullets"] += len(facts)
                    fallback_state["titles"].append("教育背景")
                    fallback_state["samples"].append(tidy(facts[0])[:60])
                    fallback_state.setdefault("details", []).append(
                        {
                            "title": "教育背景",
                            "bullet_count": len(facts),
                            "bullets": [
                                {"bullet_key": "education", "variant_lang": "zh", "preview": tidy(item)[:40], "reason": "教育背景正文只有中文"}
                                for item in facts
                            ],
                            "reason": "该条目没有 en 变体",
                        }
                    )
            if profile_entry is not None:
                if facts:
                    profile_entry["facts"] = [tidy(item) for item in facts if tidy(item)]
                entries.append(profile_entry)
            elif facts:
                entries.append(
                    {
                        "package_id": None,
                        "title": "",
                        "org": "",
                        "role": "",
                        "location": "",
                        "date": "",
                        "bullets": [],
                        "facts": [tidy(item) for item in facts if tidy(item)],
                    }
                )
        if kind == "activity":
            # 荣誉（award）并进校园活动，作为额外 bullet（用户裁决 1）
            pass
        for selection in sorted(selections, key=lambda item: int(item.get("order_index") or 0)):
            package_id = str(selection.get("package_id") or "")
            package = packages.get(package_id)
            if package is None:
                warnings.append(
                    {
                        "code": "PACKAGE_MISSING",
                        "severity": "warn",
                        "message": "选中的经历已被删除，本次跳过",
                        "details": {"package_id": package_id},
                    }
                )
                continue
            section_kind = PACKAGE_TO_SECTION.get(str(package.get("kind") or "project"), "project")
            if section_kind == "awards":
                section_kind = "activity"
            if section_kind != kind:
                continue
            entry = _entry_from_package(
                package,
                variants_by_package.get(package_id, []),
                selection,
                lang=lang,
                fallback=fallback_state,
            )
            if not entry["bullets"] and not entry["title"]:
                continue
            entries.append(entry)

        skills_lines: list[str] = []
        if kind == "skills":
            for row in profile.get("skills") or []:
                line = (
                    _lang_value(row, "line", lang)
                    if isinstance(row, Mapping)
                    else str(row)
                )
                text = tidy(str(line or ""))
                if text:
                    skills_lines.append(text)
            if not skills_lines:
                # 档案里还没回填技能行时，用模板里存住的原文（用户导入简历那一刻的逐行文本）
                skills_lines = list(static_by_kind.get("skills") or [])
            if lang == "en" and any(i18n.has_cjk(line) for line in skills_lines):
                # 技能区回退单独用 skills_fallback 标记，不计入 entry_count/samples（口径要对得上）
                fallback_state["used"] = True
                fallback_state["skills"] = True
                fallback_state["bullets"] += len(skills_lines)
            if not skills_lines:
                warnings.append(
                    {
                        "code": "SKILLS_EMPTY",
                        "severity": "info",
                        "message": "个人资料里还没有职业技能行，技能区将不输出",
                        "details": {},
                    }
                )
            missing = _missing_raw_skills(profile.get("skills") or [])
            if missing:
                warnings.append(
                    {
                        "code": "MISSING_SLOTS_RENDERED",
                        "severity": "warn",
                        "message": f"技能行缺少原文（{len(missing)} 条），已按分类名占位输出",
                        "details": {"slot_keys": ["skills.lines"], "count": len(missing)},
                    }
                )

        if not entries and not skills_lines:
            # 模板里有这一段、但仓库里没有对应内容：不能静默省略（用户会以为系统漏了）
            omitted_sections.append(heading)
            warnings.append(
                {
                    "code": "PACKAGE_MISSING",
                    "severity": "info",
                    "message": f"「{heading}」本次没有可用内容，已省略该段",
                    "details": {"section": kind, "heading": heading},
                }
            )
            continue
        sections.append({"kind": kind, "heading": heading, "entries": entries, "skills": skills_lines})

    cjk_lines = _rendered_cjk_lines(sections, lang=lang)
    if cjk_lines:
        # 有任何中文行，就必须被这条 warning 声明（没有用到回退也要声明，
        # 否则用户会以为「英文版里冒出中文」是 bug，其实是档案里缺英文值）。
        fallback_state["used"] = True

    if fallback_state["used"]:
        warnings.append(
            {
                "code": "LANG_FALLBACK",
                "severity": "warn",
                "message": (
                    f"英文版有 {fallback_state['entries']} 个条目 / {fallback_state['bullets']} 条要点"
                    "没有英文变体，沿用中文原文（导出页会标注）"
                ),
                "details": {
                    "entry_count": fallback_state["entries"],
                    "bullet_count": fallback_state["bullets"],
                    "skills_fallback": bool(fallback_state["skills"]),
                    "samples": fallback_state["samples"][:12],
                    "sample": (fallback_state["samples"] or [""])[0],
                    "entries": (fallback_state.get("details") or [])[:20],
                    "titles": fallback_state["titles"][:20],
                    # 与 PDF 抽取口径对齐：英文版正文里含中文的行数（逐行列出，便于核对）
                    "cjk_line_count": len(cjk_lines),
                    # 行数会被排版折行影响（一句话可能占两行），字符数不会。
                    # 对账用字符数，行数只作参考。
                    "cjk_char_count": sum(i18n.cjk_count(line) for line in cjk_lines),
                    "cjk_lines": [line[:60] for line in cjk_lines[:20]],
                    "lang": lang,
                },
            }
        )
    if unmapped_headings:
        warnings.append(
            {
                "code": "LANG_HEADING_UNMAPPED",
                "severity": "warn",
                "message": f"有 {len(unmapped_headings)} 个自定义标题没有英文映射，已保留原文",
                "details": {"headings": unmapped_headings[:5], "count": len(unmapped_headings)},
            }
        )

    sections = _apply_order(sections, build.get("sections_order") or [])

    ir = {
        "build_id": build.get("id"),
        "lang": lang,
        "header": header,
        "sections": sections,
        "naming": {
            "pattern": build.get("naming_pattern"),
            "overrides": build.get("naming_overrides") or {},
            "position": build.get("position"),
            "company": build.get("company"),
        },
        "meta": {
            "template_id": build.get("template_id"),
            "jd_id": build.get("jd_id"),
            "package_count": len({item.get("package_id") for item in selections if item.get("package_id")}),
            "entry_count": sum(len(section["entries"]) for section in sections),
            "bullet_count": sum(
                len(entry["bullets"]) + len(entry["facts"])
                for section in sections
                for entry in section["entries"]
            ),
            "skill_count": sum(len(section["skills"]) for section in sections),
            "omitted_sections": omitted_sections,
        },
        "warnings": warnings,
    }
    return ir


def _missing_raw_skills(rows: Sequence[Any]) -> list[int]:
    """技能行里只有分类名、没有原文的条目（渲染会缺内容）。"""
    missing: list[int] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        line = tidy(str(row.get("line") or ""))
        if not line:
            missing.append(index)
    return missing


def iter_texts(ir: Mapping[str, Any]) -> list[str]:
    """IR 里应当出现在 PDF 文本层的全部字符串（按渲染顺序）。"""
    texts: list[str] = []
    header = ir.get("header") or {}
    for key in ("name", "contact_line", "available"):
        value = str(header.get(key) or "").strip()
        if value:
            texts.extend(part for part in re.split(r"\s*\|\s*", value) if part)
    for section in ir.get("sections") or []:
        heading = str(section.get("heading") or "").strip()
        if heading:
            texts.append(heading)
        for entry in section.get("entries") or []:
            for key in ("title", "org", "role", "date", "location"):
                value = str(entry.get(key) or "").strip()
                if value:
                    texts.append(value)
            for line in list(entry.get("bullets") or []) + list(entry.get("facts") or []):
                if str(line).strip():
                    texts.append(str(line).strip())
        for line in section.get("skills") or []:
            if str(line).strip():
                texts.append(str(line).strip())
    return texts
