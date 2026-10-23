"""导入编排：上传/粘贴 → 抽取 → 结构草稿 → 提交为 Template。

职责边界：

* ``extract.py`` 负责逐字保真（PDF/DOCX/MD/TXT/HTML → 文本行 + 内嵌图）；
* ``importer.py`` 负责结构化切分（section → entry → bullet / skills）；
* 本模块只做「落盘 + 落库 + 提交模板」的编排，不重新解释文本。

降级口径（契约 §5.2）：扫描件/无可解析结构时返回草稿 + warnings，**不抛 422 顶掉导入**；
只有「一个字都没抽出来」（chars < 20）才按 ``IMPORT_NO_TEXT_LAYER`` 拒绝，否则用户连
手动粘贴的入口都没有。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from ..errors import ApiError
from ..repos import ImportRepo, JobRepo, ProfileRepo, TemplateRepo
from . import extract as extract_mod
from . import importer, photo as photo_mod
from .storage import Storage, sha256_bytes

#: 少于该字符数视为「没有文本层」（扫描件），与契约 IMPORT_NO_TEXT_LAYER 对齐
MIN_TEXT_CHARS = 20
#: 未提交草稿保留上限（条数 / 天数）；超出即清理，见 ImportRepo.prune_drafts
MAX_DRAFT_KEEP = 20
DRAFT_TTL_DAYS = 7
#: 粘贴文本的默认文件名（决定 parser 与落盘扩展名）
DEFAULT_PASTE_NAME = "pasted.txt"

#: 草稿语义 kind → template_block.bound_package_kind（schema 域：project/internship/education/award/activity/custom）
#: 技能块不属于任何 Experience Package（它来自 profile.skills_json），因此映射为 NULL。
BOUND_KIND = {
    "project": "project",
    "internship": "internship",
    "education": "education",
    "campus": "activity",
    "awards": "award",
    "skill": None,
    "skills": None,
    "summary": None,
    "other": None,
}

#: parser → template.source_kind（schema 只允许这 5 个值；纯文本粘贴归 builtin）
SOURCE_KIND = {
    "pdf": "imported_pdf",
    "docx": "imported_docx",
    "md": "imported_md",
    "html": "imported_html",
    "txt": "builtin",
}


def _parser_for(filename: str | None, parser: str | None) -> str:
    if parser:
        return parser
    detected = extract_mod.parser_for_name(filename or DEFAULT_PASTE_NAME)
    return detected or "txt"


def run_import(
    data: bytes,
    *,
    filename: str,
    parser: str | None = None,
    lang: str | None = None,
    storage: Storage | None = None,
) -> dict[str, Any]:
    """上传/粘贴 → 生成草稿。返回可直接当作 API 响应的字典。"""
    store = storage or Storage()
    chosen = _parser_for(filename, parser)
    if chosen not in extract_mod.PARSERS:
        raise ApiError(
            "IMPORT_UNSUPPORTED",
            f"不支持的解析器 {chosen}",
            details={"supported": sorted(extract_mod.PARSERS)},
        )

    # 原始文件先落盘（data/imports 或 data/files），永远保留来源
    stored = store.save_attachment(data, original_name=filename, kind="resume_source", privacy="private")

    # P2 去重：同一份文件已经有未提交草稿就直接复用 —— 用户重复点上传不该多存一份
    # 完整 draft_json（那是把真实简历在本机存多份副本）。
    existing = ImportRepo().find_open_by_source_sha(stored.sha256)
    if existing:
        reuse = view(existing)
        reuse["reused"] = True
        reuse["reused_from_sha256"] = stored.sha256
        return reuse

    doc = extract_mod.extract(data, chosen)
    if doc.text_chars < MIN_TEXT_CHARS:
        raise ApiError(
            "IMPORT_NO_TEXT_LAYER",
            "抽取到的文本不足 20 个字符，可能是扫描件或图片型 PDF",
            details={"chars_extracted": doc.text_chars, "parser": chosen, "pages": doc.pages},
            hint="可以把简历内容直接粘贴成文本再导入，或换一份带文本层的 PDF",
        )

    draft = importer.parse_document(doc)
    if lang:
        draft["lang"] = lang
    doc.lang = draft["lang"]
    extracted_photo, photo_stored, photo_warnings = photo_mod.save(
        doc, store, original_name=filename.rsplit(".", 1)[0] or "resume"
    )
    draft["extracted_photo"] = extracted_photo
    draft["source"] = {
        "attachment_id": stored.attachment_id,
        "sha256": stored.sha256,
        "original_name": stored.original_name,
        "bytes": stored.bytes,
        "rel_path": str(stored.path.relative_to(store.paths.root)).replace("\\", "/"),
    }
    warnings = list(draft.get("warnings") or []) + list(photo_warnings)

    # D-23：照片只作候选（AC-IMPORT-03）。这里**不写** user_profile.photo_path，
    # 也不把 attachment 标成已应用；用户显式确认（PUT /profile/photo）后才会生效。
    photo_info = draft.get("extracted_photo") or {}
    if photo_info.get("available") and photo_stored is not None:
        photo_info["applied"] = False
        photo_info["confirmed"] = False
        photo_info["attachment_id"] = photo_stored.attachment_id
        photo_info["sha256"] = photo_stored.sha256
        warnings.append(
            {
                "code": "PHOTO_DETECTED",
                "count": 1,
                "severity": "warn",
                "message": "检测到照片，确认后才会用于简历",
                "details": {
                    "attachment_id": photo_stored.attachment_id,
                    "sha256": photo_stored.sha256,
                    "width": photo_info.get("width"),
                    "height": photo_info.get("height"),
                },
            }
        )
    draft["warnings"] = warnings

    repo = ImportRepo()
    import_id = repo.create(stored.attachment_id, chosen)
    repo.update(import_id, status="draft", draft=draft, stats=draft.get("stats"), warnings=warnings)

    # 草稿过期清理（P2）：插入**之后**再裁，保证「未提交草稿 ≤ MAX_DRAFT_KEEP」这个字面承诺成立。
    pruned = repo.prune_drafts(max_keep=MAX_DRAFT_KEEP, ttl_days=DRAFT_TTL_DAYS, keep=(import_id,))
    if pruned:
        warnings.append(
            {
                "code": "IMPORT_DRAFT_PRUNED",
                "count": len(pruned),
                "severity": "info",
                "message": f"已清理 {len(pruned)} 条过久的未提交导入草稿（只留最近 {MAX_DRAFT_KEEP} 条 / {DRAFT_TTL_DAYS} 天）",
                "details": {"pruned_ids": pruned[:10], "max_keep": MAX_DRAFT_KEEP, "ttl_days": DRAFT_TTL_DAYS},
            }
        )
        draft["warnings"] = warnings
        repo.update(import_id, draft=draft, warnings=warnings)

    # D-20：导入是同步 201（约 200ms），job 只承担历史/审计，不用于轮询；
    # needs_llm_fallback 只打标，绝不在请求内调用 LLM。
    jobs = JobRepo()
    job_id = jobs.create("import_parse", message="解析简历并生成草稿")
    jobs.update(
        job_id,
        status="succeeded",
        progress=100,
        result={"import_id": import_id, "status": "draft", "needs_llm_fallback": bool(draft.get("needs_llm_fallback"))},
    )
    return view(import_id, draft=draft, photo_stored=photo_stored, job_id=job_id)


def view(
    import_id: str,
    *,
    draft: Mapping[str, Any] | None = None,
    photo_stored: Any | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    repo = ImportRepo()
    row = repo.get(import_id)
    payload: dict[str, Any] = {
        "import_id": row["id"],
        # 同步导入：job_id 指向一条已完成的 import_parse 审计记录（D-20），不用于轮询
        "job_id": job_id,
        "status": row["status"],
        "parser": row["parser"],
        "attachment_id": row.get("attachment_id"),
        "template_id": row.get("result_template_id"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "stats": row.get("stats") or {},
        "warnings": row.get("warnings") or [],
    }
    body = draft if draft is not None else (row.get("draft") or {})
    payload["lang"] = body.get("lang") or "zh"
    payload["draft"] = body
    payload["extracted_photo"] = body.get("extracted_photo")
    if photo_stored is not None and body.get("extracted_photo", {}).get("file"):
        payload["extracted_photo"]["attachment_id"] = photo_stored.attachment_id
    payload["sections"] = body.get("sections") or []
    payload["section_kinds"] = body.get("section_kinds") or []
    payload["entry_counts"] = body.get("entry_counts") or {}
    payload["blocks"] = body.get("blocks") or []
    payload["skills"] = body.get("skills") or []
    payload["needs_llm_fallback"] = bool(body.get("needs_llm_fallback"))
    payload.setdefault("reused", False)
    return payload


def update_draft(import_id: str, draft: Mapping[str, Any]) -> dict[str, Any]:
    repo = ImportRepo()
    row = repo.get(import_id)
    if row["status"] in ("committed",):
        raise ApiError("CONFLICT", "该导入已提交为模板，不能再改草稿", details={"status": row["status"]})
    if not isinstance(draft, Mapping) or not draft.get("blocks"):
        raise ApiError("VALIDATION_ERROR", "草稿必须包含 blocks", details={"fields": [{"field": "blocks", "rule": "required"}]})
    repo.update(
        import_id,
        status="draft",
        draft=dict(draft),
        stats=draft.get("stats") or {},
        warnings=draft.get("warnings") or [],
    )
    return view(import_id, draft=draft)


#: 永不允许进入 LLM payload 的草稿块类型（抬头含真实姓名/手机/邮箱/照片）
HEADER_BLOCK_TYPES = ("header",)


def blocks_for_prompt(draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    """拼 payload 时取草稿块的口径：**结构上**剔除 header 与任何身份槽位。

    这是继 ``ProfileRepo.llm_brief()`` 白名单之后的第二道口子：即便将来有人直接把导入草稿
    丢给 LLM，抬头里的姓名/电话/邮箱/照片也不会跟着走。
    """
    safe: list[dict[str, Any]] = []
    for block in draft.get("blocks") or []:
        if (block.get("block_type") or "") in HEADER_BLOCK_TYPES:
            continue
        clone = {key: value for key, value in block.items() if key != "slots"}
        clone["slots"] = [
            slot for slot in (block.get("slots") or [])
            if not str(slot.get("bound_field") or "").startswith(("profile.name", "profile.phone", "profile.email", "profile.photo"))
        ]
        safe.append(clone)
    return safe


def as_markdown(draft: Mapping[str, Any]) -> str:
    return importer.render_markdown(draft)


def write_artifacts(
    import_id: str,
    *,
    storage: Storage | None = None,
    stem: str | None = None,
    draft: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """把草稿导出成 `data/exports/` 下的 json + md（给用户直接过目）。

    ``stem`` 可指定固定文件名（验收用的 `import_draft_zh_v10`），否则按 import_id 尾号命名。
    """
    store = storage or Storage()
    row = ImportRepo().get(import_id)
    body = draft if draft is not None else (row.get("draft") or {})
    stem = stem or f"import_draft_{row['id'][-8:]}"
    json_bytes = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
    md_bytes = as_markdown(body).encode("utf-8")
    json_path, json_rel, _ = store.write_export(f"{stem}.json", json_bytes, overwrite=True)
    md_path, md_rel, _ = store.write_export(f"{stem}.md", md_bytes, overwrite=True)
    return {
        "json": {"path": json_rel, "bytes": len(json_bytes), "sha256": sha256_bytes(json_bytes)},
        "md": {"path": md_rel, "bytes": len(md_bytes), "sha256": sha256_bytes(md_bytes)},
    }


def _section_kind_of(block: Mapping[str, Any], by_temp: Mapping[str, Mapping[str, Any]]) -> str | None:
    """沿 parent_temp_id 向上找最近的 section/skills 块，返回它的语义 kind。"""
    kind = block.get("bound_package_kind") or block.get("kind")
    if block.get("block_type") in ("section", "skills", "awards") and kind:
        return str(kind)
    parent = block.get("parent_temp_id")
    seen = 0
    while parent and seen < 6:
        node = by_temp.get(str(parent))
        if node is None:
            return None
        node_kind = node.get("bound_package_kind") or node.get("kind")
        if node.get("block_type") in ("section", "skills", "awards") and node_kind:
            return str(node_kind)
        parent = node.get("parent_temp_id")
        seen += 1
    return None


def _static_text_for(block: Mapping[str, Any], by_temp: Mapping[str, Mapping[str, Any]]) -> str | None:
    """把草稿里的「静态内容」落到模板块（提交那一刻就存住，别指望 profile 还在）。

    用户导入自己的简历时，GPA/CET/课程/技能行这些**不是** package 里的东西，
    而是整份简历的固定文本；不在这里存住，导出时就只剩一个空骨架
    （t8 实测：commit 后 PDF 里教育段只有校名一行、技能段整段消失）。
    """
    block_type = str(block.get("block_type") or "")
    if block_type == "skills":
        raw_rows = block.get("skills") or block.get("skill_lines") or []
        lines = [
            str(row.get("line") if isinstance(row, Mapping) else row or "").strip()
            for row in raw_rows
        ]
        text = "\n".join(line for line in lines if line)
        return text or None
    if block_type != "entry":
        return None
    kind = _section_kind_of(block, by_temp)
    entry = block.get("entry") or {}
    if kind == "education":
        facts = [str(item).strip() for item in entry.get("facts") or [] if str(item).strip()]
        if not facts:
            facts = [str(item).strip() for item in importer.entry_lines(entry) if str(item).strip()]
        return "\n".join(facts) or None
    if kind == "awards":
        bullets = [str(item).strip() for item in entry.get("bullets") or [] if str(item).strip()]
        return "\n".join(bullets) or None
    return None


DEGREE_WORDS = ("博士", "硕士", "本科", "大专", "专科", "MBA")


def _profile_from_draft(
    draft: Mapping[str, Any], by_temp: Mapping[str, Mapping[str, Any]], import_id: str
) -> dict[str, Any]:
    """从**用户自己提交的简历草稿**回填档案里能确定的字段（不猜、不编）。

    只回填能从原文直接读出的：学历/专业/毕业届别/城市/技能行，以及按语言分开的到岗时间。
    姓名/学校/手机/邮箱仍走 ``apply_identity`` 这条显式通道。
    """
    derived: dict[str, Any] = {}
    sources: dict[str, str] = {}
    marker = f"import:{import_id}"

    for block in draft.get("blocks") or []:
        if block.get("block_type") != "entry":
            continue
        if _section_kind_of(block, by_temp) != "education":
            continue
        entry = block.get("entry") or {}
        degree_major = str(entry.get("degree_major") or "")
        for word in DEGREE_WORDS:
            if word in degree_major:
                derived["degree"] = "大专" if word in ("大专", "专科") else word
                sources["degree"] = marker
                major = re.sub(r"\s+", " ", degree_major.replace(word, "")).strip(" |、,;；")
                if major:
                    derived["major"] = major
                    sources["major"] = marker
                break
        date_range = str(entry.get("date_range") or "").strip()
        if date_range:
            # 入学—毕业区间原样留档：导出教育段必须还原 2024.9 - 2028.6，不能只剩毕业年
            derived["extra"] = {"education_date_range": date_range}
            sources["extra"] = marker
        years = [int(token) for token in re.findall(r"(?:19|20)\d{2}", date_range)]
        if years:
            derived["grad_year"] = max(years)
            sources["grad_year"] = marker
        city = str(entry.get("city") or "").strip()
        if not city:
            # 中文简历的学校/单位里通常带城市（「示例大学-经济与管理学院」），没有城市列时据此推出
            city = _city_from_org(str(entry.get("org") or ""))
        if city:
            derived["city"] = city.split(",")[0].strip()
            sources["city"] = marker
        break

    skills = [
        {
            "line": str(row.get("line") or "").strip(),
            "category": row.get("category"),
            "tokens": list(row.get("tokens") or []),
            "order": int(row.get("order") or index * 10),
        }
        for index, row in enumerate(draft.get("skills") or [])
        if isinstance(row, Mapping) and str(row.get("line") or "").strip()
    ]
    if skills:
        derived["skills"] = skills
        sources["skills"] = marker

    # 到岗时间按语言各存一份：两份简历原文不一致时（用户口径：不要合并成一个数）
    available: dict[str, str] = {}
    for block in draft.get("blocks") or []:
        if block.get("block_type") != "header":
            continue
        for slot in block.get("slots") or []:
            if (slot.get("bound_field") or "") != "profile.available_note":
                continue
            value = str(slot.get("suggested_value") or "").strip()
            if value:
                lang = str(draft.get("lang") or "zh")
                available[lang] = value
                sources["available_note"] = marker
    return {"fields": derived, "sources": sources, "available": available}


def commit(
    import_id: str,
    *,
    template_name: str,
    lang: str | None = None,
    page_limit: int = 1,
    set_default: bool = False,
    layout: Mapping[str, Any] | None = None,
    apply_identity: bool = False,
    apply_photo: bool = False,
    also_create_packages: bool = False,
    overwrite_profile: bool = False,
) -> dict[str, Any]:
    """草稿 → Template（blocks + slots）。

    档案写入口径：身份字段要 ``apply_identity``、照片要 ``apply_photo``，两者都默认关闭
    （导入只产出候选，用户显式确认才落到 user_profile）。
    """
    imports = ImportRepo()
    row = imports.get(import_id)
    if row["status"] == "committed" and row.get("result_template_id"):
        raise ApiError(
            "CONFLICT",
            "该导入已提交过模板",
            details={"reason": "TEMPLATE_VERSION_CONFLICT", "template_id": row["result_template_id"]},
            hint="可以直接使用该模板，或在导入列表里新建一次导入",
        )
    draft = row.get("draft") or {}
    blocks: Sequence[Mapping[str, Any]] = draft.get("blocks") or []
    if not blocks:
        raise ApiError("TEMPLATE_INVALID", "草稿里没有可提交的块", details={"reason": "empty_blocks"})

    templates = TemplateRepo()
    template_id = templates.create(
        {
            "name": template_name,
            "source_kind": SOURCE_KIND.get(row["parser"], "builtin"),
            "source_file_id": row.get("attachment_id"),
            "lang": lang or draft.get("lang") or "zh",
            "page_limit": page_limit,
            "is_default": set_default,
            "layout": dict(layout or {"source": "import", "import_id": import_id}),
        }
    )

    created: dict[str, str] = {}
    by_temp = {str(block["temp_id"]): block for block in blocks}
    for block in blocks:
        parent_temp = block.get("parent_temp_id")
        slot_list = block.get("slots") or []
        block_id = templates.add_block(
            template_id,
            {
                "parent_block_id": created.get(parent_temp) if parent_temp else None,
                "order_index": int(block.get("order_index") or 0),
                "block_type": block.get("block_type") or "section",
                "heading": block.get("heading"),
                "bound_package_kind": BOUND_KIND.get(block.get("bound_package_kind") or "", None),
                "style": {"confidence": block.get("confidence"), "import_id": import_id},
                "static_text": _static_text_for(block, by_temp),
                "repeat_per_package": block.get("block_type") != "header",
            },
        )
        created[block["temp_id"]] = block_id
        for slot in slot_list:
            templates.add_slot(
                block_id,
                {
                    "slot_key": slot["slot_key"],
                    "slot_type": slot.get("slot_type") or "text",
                    "required": bool(slot.get("required")),
                    "bound_field": slot.get("bound_field"),
                    "default_value": slot.get("suggested_value") or None,
                    "list_source": slot.get("list_source"),
                },
            )

    # 档案写入口径：照片永远带上（用户导入了就用）；姓名等身份字段必须显式 apply_identity
    identity: dict[str, Any] = {}
    for block in blocks:
        if block.get("block_type") != "header":
            continue
        for slot in block.get("slots") or []:
            field = (slot.get("bound_field") or "").removeprefix("profile.")
            value = slot.get("suggested_value")
            if field and value:
                identity[field] = value

    photo_info = draft.get("extracted_photo") or {}
    profiles = ProfileRepo()
    patch: dict[str, Any] = {}
    # D-23：提交模板同样不自动套用照片；只有显式 apply_photo=true 才写 photo_path
    if apply_photo and photo_info.get("file"):
        patch["photo_path"] = photo_info["file"]
    if apply_identity:
        patch.update(identity)

    # 静态内容回填：学历/专业/届别/城市/技能行/按语言分开的到岗时间
    # —— 这些都是用户自己上传的简历里写着的，不回填的话导出就是一副空骨架。
    derived = _profile_from_draft(draft, by_temp, import_id)
    existing_sources = dict(
        ((profiles.get() or {}).get("extra") or {}).get("profile_field_sources") or {}
    )
    manual_fields = {field for field, source in existing_sources.items() if source == "manual"}
    current_profile = profiles.get() or {}
    derived_fields: dict[str, Any] = {}
    skipped_manual: list[str] = []
    for key, value in derived["fields"].items():
        if key in patch:
            continue
        if key in manual_fields and not overwrite_profile:
            skipped_manual.append(key)
            continue
        # 源里没有的字段保持 NULL（不用默认值填充）；已有非空值也不覆盖
        current_value = current_profile.get(key)
        if current_value not in (None, "", [], {}, 0) and not overwrite_profile:
            # 值已经一致 = 这次导入同样是它的来源，标记写进 sources（可追溯，不改数据）；
            # 值不一致 = 用户手改过或来自别处，保持原样并只在响应里报 skipped。
            if current_value == value:
                derived["sources"].setdefault(key, f"import:{import_id}")
            else:
                skipped_manual.append(key)
            continue
        derived_fields[key] = value
    patch.update(derived_fields)
    extra: dict[str, Any] = {}
    if derived["sources"]:
        extra["profile_field_sources"] = derived["sources"]
        extra["profile_fields_source"] = f"import:{import_id}"
    if derived["available"]:
        for lang_key, value in derived["available"].items():
            extra[f"available_note_{lang_key}"] = value
        if derived["available"].get("zh") and not patch.get("available_note"):
            patch["available_note"] = derived["available"]["zh"]
    if extra:
        # 注意顺序：derived 里可能已经写了 extra（如 education_date_range），
        # 这里只能**合并**，整体赋值会把入学—毕业区间丢掉，导出教育段就只剩 grad_year。
        merged_extra = dict(patch.get("extra") or {})
        merged_extra.update((profiles.get() or {}).get("extra") or {})
        merged_extra.update(extra)
        patch["extra"] = merged_extra

    if patch:
        # 首次建档案时 upsert 需要姓名，否则只写照片会 422：能从 header 读到姓名就一起写
        if not profiles.exists() and not patch.get("name_zh") and identity.get("name_zh"):
            patch["name_zh"] = identity["name_zh"]
        if profiles.exists() or patch.get("name_zh"):
            profiles.upsert(patch)
        else:
            patch = {}
            apply_identity = False

    package_result = None
    if also_create_packages:
        package_result = create_packages_from_draft(
            draft, import_id=import_id, lang=lang or draft.get("lang") or "zh"
        )

    package_warnings = (package_result or {}).get("warnings") or []
    if package_warnings:
        merged = list(row.get("warnings") or []) + package_warnings
        imports.update(import_id, status="committed", template_id=template_id, warnings=merged)
    else:
        imports.update(import_id, status="committed", template_id=template_id)
    template = templates.get(template_id) or {}
    return {
        "import_id": import_id,
        "template_id": template_id,
        "template": template,
        "blocks_created": len(created),
        "photo_applied": bool(apply_photo and photo_info.get("file")),
        "photo_candidate": {
            "attachment_id": photo_info.get("attachment_id"),
            "file": photo_info.get("file"),
            "available": bool(photo_info.get("available")),
            "confirm_endpoint": "PUT /api/v1/profile/photo",
        },
        "identity_applied": bool(apply_identity),
        "profile_fields_source": (patch.get("extra") or {}).get("profile_field_sources") or {},
        "profile_fields_skipped_manual": skipped_manual,
        "packages_created": (package_result or {}).get("created", []),
        "packages_reused": (package_result or {}).get("reused", []),
        "packages_skipped": (package_result or {}).get("skipped", []),
        "packages_warnings": package_warnings,
    }


#: 角色词白名单：只在「标题末尾」命中且前面还有内容时才拆，避免把「数据分析」里的词当角色
ROLE_WORDS: tuple[str, ...] = (
    "队长", "副队长", "队员", "组员", "组长", "副组长", "负责人", "学习委员", "班长", "团支书",
    "主席", "副主席", "部长", "副部长", "干事", "成员", "实习生", "助理", "研究员", "分析师",
    "工程师", "设计师", "运营", "顾问", "助教", "讲师", "主管", "经理", "总监",
    "Leader", "Lead", "Member", "Team Member", "Intern", "Assistant", "Manager", "Analyst",
)
#: 标题与角色之间可能出现的分隔符（导入的标题行常是「标题 - 角色 日期」被切剩的形态）
_ROLE_SEP_RE = re.compile(r"\s*(?:[-–—·|｜/]|\s{2,})\s*$")


def split_title_role(text: str) -> tuple[str, str, bool]:
    """把「标题 角色」拆成 (title, role, ambiguous)。

    只在角色词**位于末尾且前面仍有内容**时拆；拆不动返回 (原文, "", True) 交给上层发警告。
    ``ambiguous=True`` 表示原文里出现过角色词但没能干净拆出。
    """
    raw = str(text or "").strip()
    if not raw:
        return "", "", False
    for word in sorted(ROLE_WORDS, key=len, reverse=True):
        if not raw.endswith(word):
            continue
        head = raw[: len(raw) - len(word)]
        # 「队长会议纪要」不是角色；必须是分隔符或空白收尾
        if not head or not (head.endswith((" ", "\t", "-", "–", "—", "·", "|", "｜", "/")) or head.endswith("　")):
            continue
        title = _ROLE_SEP_RE.sub("", head).strip()
        if title:
            return title, word, False
    touched = any(word in raw for word in ROLE_WORDS)
    return raw, "", touched


def derive_title_role(
    entry: Mapping[str, Any],
) -> tuple[str, str, list[dict[str, Any]], dict[str, Any] | None]:
    """从导入草稿的一条 entry 推出 (package title, role, warnings, evidence)。

    三级兜底：
    1. entry 已经给了 role（真实草稿都是「标题 - 角色 日期」，importer 已切开）→ 直接用；
    2. 没给 role 但标题以角色词结尾 → 拆出来（盲区修复：``门店选址与订单量预测 队长``）；
    3. 标题就等于机构名（实习/校园段把公司名当标题）→ 用 ``机构 · 角色`` 作显示标题，
       原值放 evidence 里溯源；没有 role 就保持机构名不变。
    """
    warnings: list[dict[str, Any]] = []
    title = str(entry.get("title") or "").strip()
    org = str(entry.get("org") or "").strip()
    role = str(entry.get("role") or "").strip()
    raw_title = title or org
    evidence: dict[str, Any] | None = None

    if title and not role:
        title, role, ambiguous = split_title_role(title)
        if ambiguous:
            warnings.append(
                {
                    "code": "TITLE_ROLE_UNSPLIT",
                    "severity": "warn",
                    "message": "条目标题里似乎含角色词，但没能干净拆出，已原样保留",
                    "details": {"raw_title": raw_title, "temp_id": entry.get("temp_id")},
                }
            )
            title = raw_title

    if org and title and title == org and role:
        derived = f"{org} · {role}"
        evidence = {
            "kind": "raw_title",
            "value": raw_title,
            "derived": derived,
            "note": "标题与机构同名，显示用「机构 · 角色」，原值保留在此",
        }
        title = derived

    return title or org, role, warnings, evidence


#: 草稿语义 kind → package.kind（schema 域）
PACKAGE_KIND = {
    "internship": "internship",
    "project": "project",
    "campus": "activity",
    "awards": "award",
    "education": "education",
}


def create_packages_from_draft(
    draft: Mapping[str, Any], *, import_id: str, lang: str
) -> dict[str, Any]:
    """把导入草稿里的每条经历落成 Package（幂等、可级联撤销）。

    设计口径：

    * **lang 取这次导入的语言**（英文简历产英文变体），不一律写 zh；
    * 每条 entry → 一个 package，entry 的 bullets/facts → 多个变体（原文照录，
      ``verified=1``：这是用户自己写的字，不是模型编的）；
    * 幂等键 = schema v8 的 ``package(source_import_job_id, source_entry_temp_id)``
      （DATA-MODEL I12 的 UNIQUE 约束，由部分唯一索引兜底）；跨导入的同一条经历再用
      ``ckey`` 内容指纹去重。``tags`` 里的 ``import:/entry:/ckey:`` 只作历史兼容与可读标记，
      不再承担幂等职责；
    * ``DELETE /imports/{id}`` 按 ``source_import_job_id`` 连带软删。
    """
    from ..repos import PackageRepo

    packages = PackageRepo()
    tag_import = f"import:{import_id}"
    created: list[str] = []
    reused: list[str] = []
    skipped: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    existing = {str(item.get("id")): item for item in packages.list(limit=500)["items"]}
    existing_by_key: dict[str, str] = {}
    existing_by_source: dict[tuple[str, str], str] = {}
    for package_id, package in existing.items():
        job_id = str(package.get("source_import_job_id") or "")
        entry_id = str(package.get("source_entry_temp_id") or "")
        if job_id and entry_id:
            existing_by_source.setdefault((job_id, entry_id), package_id)
        for tag in package.get("tags") or []:
            tag = str(tag)
            # 幂等键要跨导入成立：同一份简历导入多次（不同 import_job）也只留一份经历。
            # 只认内容指纹 `ckey:`；`entry:` 标签里的 temp_id 是**每份草稿都相同**的
            # 「第 3 个块第 1 条」，拿它去重会把「另一份简历的项目」误判成同一段经历
            # （实测：导入第二份简历时 3 个包全被复用，新简历的经历一条都进不了仓库）。
            if tag.startswith("ckey:"):
                existing_by_key.setdefault(tag, package_id)

    for block in draft.get("blocks") or []:
        if block.get("block_type") != "entry":
            continue
        raw_kind = str(block.get("bound_package_kind") or "")
        kind = PACKAGE_KIND.get(raw_kind)
        entry = block.get("entry") or {}
        temp_id = str(block.get("temp_id") or "")
        if kind == "education":
            # 契约 §5.4：教育经历进 user_profile 与模板 static_text，不是可复用 package；
            # 这里静默跳过是**规定行为**，不许当失败记。
            continue
        if not kind:
            # 映射不出 kind 就不能「假装建过」：必须留一条可核对的告警，否则用户看到
            # 「导了 5 段经历、仓库里只有 4 条」却查不到原因。
            skipped.append({"temp_id": temp_id, "reason": "no_kind_mapping"})
            warnings.append(
                {
                    "code": "PACKAGE_SKIPPED",
                    "severity": "warn",
                    "message": "有一段经历无法判断类型，没有建成经历包",
                    "details": {
                        "reason": "no_kind_mapping",
                        "temp_id": temp_id,
                        "bound_package_kind": raw_kind,
                        "title": str(entry.get("title") or entry.get("org") or "")[:80],
                    },
                }
            )
            continue
        title = str(entry.get("title") or entry.get("org") or "").strip()
        if not title:
            skipped.append({"temp_id": temp_id, "reason": "no_title"})
            continue
        title, derived_role, title_warnings, title_evidence = derive_title_role(
            {**entry, "temp_id": temp_id}
        )
        warnings.extend(title_warnings)
        start, end = _split_date_range(str(entry.get("date_range") or ""))
        lines = [str(line).strip() for line in importer.entry_lines(entry) if str(line).strip()]
        if not lines:
            # 只有标题、没有正文的经历不该变成一条空包：用户在仓库里看到「有名字、
            # 点开什么都没有」的经历比少一条更困惑。留告警说明为什么没建。
            skipped.append({"temp_id": temp_id, "reason": "empty_entry"})
            warnings.append(
                {
                    "code": "PACKAGE_SKIPPED",
                    "severity": "warn",
                    "message": "有一段经历只有标题没有正文，没有建成经历包",
                    "details": {
                        "reason": "empty_entry",
                        "temp_id": temp_id,
                        "title": title[:80],
                    },
                }
            )
            continue
        # 标记只用于溯源（含 import_id），不参与去重
        entry_tag = f"entry:{import_id}:{temp_id}"
        content_key = "ckey:" + _content_key(title, start, end, lines)
        hit = (existing_by_source.get((import_id, temp_id)) if temp_id else None) or existing_by_key.get(
            content_key
        )
        if hit:
            reused.append(hit)
            continue
        try:
            package_id = packages.create(
                {
                    "title": title,
                    "kind": kind,
                    "org": entry.get("org") or None,
                    "role": derived_role or None,
                    "start_date": start,
                    "end_date": end,
                    "is_current": end is None and bool(start),
                    "location": entry.get("city") or None,
                    "summary": None,
                    "status": "ready",
                    "source": "imported",
                    "source_import_job_id": import_id,
                    "source_entry_temp_id": temp_id or None,
                    "tags": [tag_import, entry_tag, content_key] + ([lang] if lang else []),
                    "evidence": [title_evidence] if title_evidence else None,
                }
            )
        except ApiError as exc:
            skipped.append({"temp_id": temp_id, "reason": exc.code})
            continue
        for index, line in enumerate(lines):
            packages.add_variant(
                package_id,
                {
                    "bullet_key": f"b{index + 1}",
                    "tone": "original",
                    "lang": lang,
                    "text": line[:400],
                    "verified": True,
                    "llm_generated": False,
                    "source": "imported_verbatim",
                },
                conflict="update",
            )
        created.append(package_id)
    return {
        "created": created,
        "reused": reused,
        "skipped": skipped,
        "warnings": warnings,
    }


def _content_key(title: str, start: str | None, end: str | None, lines: Sequence[str]) -> str:
    """同一条经历的内容指纹：跨导入/跨批次都能认出「已经打包过」。"""
    digest = hashlib.sha1(
        "\n".join([title, start or "", end or "", *lines]).encode("utf-8")
    ).hexdigest()
    return digest[:12]


#: 常见校名/单位首段里能直接看出的城市（只认确定性前缀，不做模糊猜测）
_CITY_HINTS = (
    "北京", "上海", "天津", "重庆", "武汉", "广州", "深圳", "杭州", "南京", "成都", "西安",
    "苏州", "长沙", "合肥", "厦门", "青岛", "大连", "济南", "郑州", "福州", "宁波", "无锡",
)


def _city_from_org(org: str) -> str:
    """从「示例大学-经济与管理学院」这类单位名里取出城市；取不到返回空串。"""
    text = str(org or "").strip()
    for city in _CITY_HINTS:
        if text.startswith(city):
            return city
    return ""


def _split_date_range(text: str) -> tuple[str | None, str | None]:
    """``2026.07 - 2026.10`` → (``2026-07``, ``2026-10``)；「至今」→ (start, None)。"""
    raw = str(text or "").strip()
    if not raw:
        return None, None
    if re.search(r"至今|present|now", raw, re.I):
        head = re.split(r"[-–—~～至]|\bto\b", raw, maxsplit=1)[0]
        return _norm_date(head), None
    parts = [part for part in re.split(r"\s*[-–—~～]\s*|\s+to\s+", raw) if part.strip()]
    if not parts:
        return None, None
    start = _norm_date(parts[0])
    end = _norm_date(parts[1]) if len(parts) > 1 else None
    return start, end


def _norm_date(token: str) -> str | None:
    match = re.search(r"((?:19|20)\d{2})\s*[.\-/年]?\s*(\d{1,2})?", str(token))
    if not match:
        return None
    year, month = match.group(1), match.group(2)
    if month:
        return f"{year}-{int(month):02d}"
    return f"{year}"


def cascade_soft_delete_packages(import_id: str) -> list[str]:
    """导入历史被软删时，连带软删由它派生的 package（保持「撤销」的语义）。

    首选 schema v8 的 ``source_import_job_id`` 反查（契约 I13 的口径）；对 v8 之前创建、
    只留了 ``tags=['import:<id>']`` 的历史行仍按标签兜底，避免老数据删不掉。
    """
    from ..repos import PackageRepo

    repo = PackageRepo()
    tag = f"import:{import_id}"
    removed: list[str] = []
    for package in repo.list(limit=500)["items"]:
        by_source = str(package.get("source_import_job_id") or "") == import_id
        by_tag = tag in [str(item) for item in package.get("tags") or []]
        if by_source or by_tag:
            repo.delete(str(package["id"]))
            removed.append(str(package["id"]))
    return removed
