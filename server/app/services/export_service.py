"""导出编排：build → IR → 渲染 → 命名 → 落盘 → 文本校验。

一次导出要做对六件事（顺序不能换）：

1. **组装**：选中的 package/变体 + 模板 + 档案 → IR（``compose.build_ir``）；
2. **缺失即警告**：模板 required 槽位缺值、经历被删 → 进 warnings，不静默吞；
3. **命名**：``naming.resolve_filename`` 用档案真值解析 ``{position}-{name}-{school}``，
   变量缺失直接 422（绝不出残缺文件名），也不落任何文件；
4. **渲染**：reportlab 单页优先、按阶梯降档，降档/溢出都进 warnings；
5. **落盘**：``Storage.write_export`` 同名冲突追加 ``-2``/``-3``；
6. **文本校验**：抽 PDF 文本层逐条比对 IR 里的字符串，缺一条 → ``text_verified=False``
   并附 ``TEXT_LAYER_MISMATCH``（用户看到的字必须能从文件里抽出来）。
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Mapping, Sequence

from .. import db as db_mod
from ..errors import ApiError
from ..repos import (
    BuildRepo,
    PackageRepo,
    ProfileRepo,
    TemplateRepo,
)
from . import compose, naming, render, samples, source_conflict

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = ("pdf", "html", "md")
TEXT_VERIFY_FORMATS = ("pdf",)


def _photo_bytes(rel_path: str | None) -> bytes | None:
    """读档案照片字节（仅本机渲染用；**永不进 LLM payload**）。"""
    if not rel_path:
        return None
    paths = db_mod.get_paths()
    from pathlib import Path

    candidate = paths.assert_within(Path(paths.root) / rel_path)
    if not candidate.exists():
        return None
    return candidate.read_bytes()


def _missing_template_slots(blocks: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """模板里 required 但档案/构建设置里没有值的槽位。"""
    missing: list[dict[str, Any]] = []
    for block in blocks:
        for slot in block.get("slots") or []:
            if not slot.get("required"):
                continue
            if slot.get("default_value"):
                continue
            bound = str(slot.get("bound_field") or "")
            if bound.startswith("profile.") or bound.startswith("package.") or bound.startswith("build."):
                # 这三类由 compose 在运行时取值，缺了会在 IR 里体现（PHOTO_MISSING/SKILLS_EMPTY 等）
                continue
            missing.append(
                {
                    "block_id": block.get("id"),
                    "slot_key": slot.get("slot_key"),
                    "slot_type": slot.get("slot_type"),
                    "reason": "required_without_value",
                }
            )
    return missing


def assemble(build_id: str) -> dict[str, Any]:
    """组装 IR（不落盘）。返回 ``{ir, missing_slots, warnings, competitiveness_summary}``。"""
    builds = BuildRepo()
    build = builds.get(build_id)
    template_id = build.get("template_id")
    if not template_id:
        raise ApiError(
            "VALIDATION_ERROR",
            "构建没有绑定模板，无法组装",
            details={"fields": [{"field": "template_id", "rule": "required", "message": "缺少模板"}]},
        )
    template = TemplateRepo().get(template_id)
    if template is None:
        # 模板被删/失效时绝不静默换一份：明确让用户重选（也不猜「最新模板」）
        raise ApiError(
            "NO_DEFAULT_TEMPLATE",
            "这份简历绑定的模板已不存在，请重新选择模板",
            details={"template_id": template_id, "candidates": []},
            hint="在组装页重新选择模板，或到模板页恢复它",
        )
    blocks = (template or {}).get("blocks") or []
    profile = ProfileRepo().get()

    packages_repo = PackageRepo()
    packages: dict[str, Mapping[str, Any]] = {}
    variants: dict[str, Sequence[Mapping[str, Any]]] = {}
    selections = builds.list_selections(build_id)
    warnings: list[dict[str, Any]] = []
    for selection in selections:
        package_id = str(selection.get("package_id") or "")
        package = packages_repo.get(package_id)
        if package is None:
            warnings.append(
                {
                    "code": "PACKAGE_MISSING",
                    "severity": "warn",
                    "message": "选中的经历已不存在，本次跳过",
                    "details": {"package_id": package_id},
                }
            )
            continue
        packages[package_id] = package
        variants[package_id] = package.get("variants") or []

    field_values = build.get("field_values") or {}
    include_photo = bool(field_values.get("include_photo", True))
    ir = compose.build_ir(
        build,
        selections=selections,
        packages=packages,
        variants_by_package=variants,
        blocks=blocks,
        profile=profile,
        include_photo=include_photo,
    )

    missing_slots = _missing_template_slots(blocks)
    if missing_slots:
        ir["warnings"].append(
            {
                "code": "MISSING_SLOTS_RENDERED",
                "severity": "warn",
                "message": f"模板有 {len(missing_slots)} 个必填槽位没有值，已按空白渲染",
                "details": {"slot_keys": [item["slot_key"] for item in missing_slots][:10], "count": len(missing_slots)},
            }
        )

    # 中英简历同字段不一致（用户口径：不合并，各按语言出值，只提示）
    conflicts = source_conflict.detect()
    if conflicts:
        # 用户已经拍过板的字段（extra.conflict_resolution）降级为 info，别再每次导出都追问一遍
        resolution = (profile.get("extra") or {}).get("conflict_resolution")
        ir["warnings"].extend(source_conflict.warnings_for(conflicts, resolution))

    # 演示数据护栏：选进了 `【示例】…` / tags 含 sample 的经历时，必须在成品警告里说出来，
    # 否则用户会拿到一份「自己没做过」的简历而毫无察觉。
    sample_warning = samples.included_warning(list(packages.values()))
    if sample_warning:
        ir["warnings"].append(sample_warning)

    summary = _competitiveness_summary(build)

    # 可追溯性（契约）：这份简历到底用了哪几段经历、命名变量取了什么值，
    # 必须落库，否则用户在导出页问「有没有漏掉我的实习」时无处可查。
    _record_usage(builds, build, ir, selections, packages)

    return {
        "build": build,
        "template": template,
        "ir": ir,
        "missing_slots": missing_slots,
        "source_conflicts": conflicts,
        "warnings": _merge_warnings(ir["warnings"] + warnings),
        "competitiveness_summary": summary,
    }


def _record_usage(
    builds: Any,
    build: Mapping[str, Any],
    ir: Mapping[str, Any],
    selections: Sequence[Mapping[str, Any]],
    packages: Mapping[str, Mapping[str, Any]],
) -> None:
    """把「实际渲染了什么」写回 build（幂等，可反复 assemble）。"""
    sections_order = [
        {
            "kind": section.get("kind"),
            "heading": section.get("heading"),
            "entry_count": len(section.get("entries") or []),
            "skill_count": len(section.get("skills") or []),
        }
        for section in ir.get("sections") or []
    ]
    field_values = dict(build.get("field_values") or {})
    field_values.update(
        {
            "naming": ir.get("naming") or {},
            "meta": ir.get("meta") or {},
            "rendered_at": db_mod.utcnow_iso(),
            "omitted_sections": (ir.get("meta") or {}).get("omitted_sections") or [],
        }
    )
    try:
        builds.update(
            build["id"], {"sections_order": sections_order, "field_values": field_values}
        )
    except ApiError:  # pragma: no cover - update 失败不应阻断组装
        logger.warning("无法写回 build 使用记录：%s", build.get("id"))

    existing = {str(item.get("package_id")): item for item in selections}
    for package_id, package in packages.items():
        selection = existing.get(package_id) or {}
        variants = package.get("variants") or []
        snapshot = {
            "package_id": package_id,
            "title": package.get("title"),
            "kind": package.get("kind"),
            "org": package.get("org"),
            "role": package.get("role"),
            "variant_count": len(selection.get("variant_ids") or []) or len(variants),
            "bullet_count": len(variants),
            "langs": sorted({str(item.get("lang") or "zh") for item in variants}),
            "verified_count": sum(1 for item in variants if int(item.get("verified") or 0) == 1),
            "snapshot_at": db_mod.utcnow_iso(),
        }
        try:
            builds.update_selection_snapshot(build["id"], package_id, snapshot)
        except (ApiError, AttributeError):  # pragma: no cover
            logger.debug("写 selection snapshot 失败：%s", package_id)


def _competitiveness_summary(build: Mapping[str, Any]) -> dict[str, Any] | None:
    """把 JD 分析里的竞争力结论带进组装结果（供导出页提示「优势/缺口」）。"""
    jd_id = build.get("jd_id")
    if not jd_id:
        return None
    from ..repos import JdRepo

    try:
        jd = JdRepo().get(jd_id, with_requirements=False)
    except ApiError:
        return None
    competitiveness = jd.get("competitiveness") or {}
    if not competitiveness:
        return None
    return {
        "verdict": competitiveness.get("verdict"),
        "school_tier": competitiveness.get("school_tier"),
        "school_signal": competitiveness.get("school_signal"),
        "coverage": {
            "advantage": competitiveness.get("advantage") or [],
            "neutral": competitiveness.get("neutral") or [],
            "gap": competitiveness.get("gap_notes") or [],
        },
    }


def _merge_warnings(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """同码合并（契约 §8：同码只留一条，details 合并计数）。"""
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        code = str(item.get("code") or "")
        if not code:
            continue
        if code not in merged:
            merged[code] = {
                "code": code,
                "severity": item.get("severity") or "info",
                "message": item.get("message") or "",
                "details": dict(item.get("details") or {}),
                "count": 1,
            }
            continue
        current = merged[code]
        current["count"] += 1
        details = item.get("details") or {}
        for key, value in details.items():
            # 同一个 warning 在 assemble 与 export 各出现一次时，计数类字段取最大值，
            # 不能相加（否则 entry_count 会变成 2 倍，口径立刻失去可核性）
            if isinstance(value, int) and isinstance(current["details"].get(key), int):
                current["details"][key] = max(current["details"][key], value)
    return list(merged.values())


def _naming(build: Mapping[str, Any], *, lang: str, extension: str) -> naming.NamingResult:
    profile = ProfileRepo().get()
    existing = _existing_exports(extension)
    return naming.resolve_filename(
        str(build.get("naming_pattern") or "{position}-{name}-{school}"),
        lang=lang,
        profile=profile,
        position=build.get("position"),
        company=build.get("company"),
        overrides=build.get("naming_overrides") or {},
        extension=extension,
        exists=existing,
    )


def _existing_exports(extension: str) -> list[str]:
    directory = db_mod.get_paths().exports
    if not directory.exists():
        return []
    return [path.name for path in directory.iterdir() if path.suffix.lstrip(".").lower() == extension]


def precheck_naming(build_id: str, *, pattern: str | None = None, extension: str = "pdf") -> dict[str, Any]:
    """导出前先把命名算出来：缺变量/非法模板当场 422，别等 job 里才失败。

    AC-NAME-04：缺 name/school 必须同步 422（``NAMING_MISSING_VAR``）且**不落任何文件**；
    返回解析结果供调用方原样回显（pattern/resolved/filename/variables）。
    """
    build = BuildRepo().get(build_id, with_selections=True)
    if build is None:
        raise ApiError("NOT_FOUND", "构建记录不存在", details={"build_id": build_id})
    lang = str(build.get("lang") or "zh")
    resolved = dict(build)
    if pattern:
        resolved["naming_pattern"] = pattern
    result = _naming(resolved, lang=lang, extension=extension)
    if result.errors:
        naming.raise_on_errors(result)
    return result.as_dict()


def export(
    build_id: str,
    *,
    fmt: str = "pdf",
    overwrite: bool = False,
    density: str = "original",
    verify_text: bool = True,
    include_photo: bool | None = None,
    naming_pattern: str | None = None,
    trim_courses: bool | None = None,
) -> dict[str, Any]:
    """导出产物并落库 ``build_artifact``。返回 ``{artifacts, naming, warnings}``。"""
    fmt = fmt.lower()
    if fmt not in SUPPORTED_FORMATS:
        raise ApiError(
            "VALIDATION_ERROR",
            f"不支持的导出格式：{fmt}",
            details={"fields": [{"field": "format", "rule": "enum", "message": "可选 pdf/html/md"}]},
        )
    assembled = assemble(build_id)
    ir = assembled["ir"]
    build = assembled["build"]
    lang = str(build.get("lang") or "zh")
    warnings = list(assembled["warnings"])

    # AC-SKILL-04：课程裁剪默认关；显式打开才裁，且必须留痕（前缀 + ≥3 门 + warnings）
    if trim_courses is None:
        trim_courses = bool((build.get("field_values") or {}).get("trim_courses"))
    if trim_courses:
        before, after = compose.trim_courses(ir)
        if before != after:
            warnings.append(
                {
                    "code": "COURSES_TRIMMED",
                    "severity": "info",
                    "message": f"按设置裁剪主修课程：裁剪前 {before} 门 → 裁剪后 {after} 门",
                    "details": {"before": before, "after": after, "min_keep": compose.COURSES_MIN_KEEP},
                }
            )

    naming_build = dict(build)
    if naming_pattern:
        naming_build["naming_pattern"] = naming_pattern
    result = _naming(
        naming_build,
        lang=lang,
        extension="html" if fmt == "html" else ("md" if fmt == "md" else "pdf"),
    )
    if result.errors:
        naming.raise_on_errors(result)
    for item in result.warnings:
        # NamingWarning 只有 code/message/field；导出侧统一按 info 上报
        warnings.append(
            {
                "code": item.code,
                "severity": "info",
                "message": item.message,
                "details": {"field": item.field},
            }
        )

    if fmt == "pdf":
        # 「包含照片」开关默认开启（用户要求简历里保留照片）；显式关闭时不画图，布局不得错位。
        stored = (build.get("field_values") or {}).get("include_photo", True)
        wants_photo = bool(stored) if include_photo is None else include_photo
        photo = _photo_bytes((ir.get("header") or {}).get("photo_path")) if wants_photo else None
        rendered = render.render_pdf(ir, density=density, photo_bytes=photo)
        data = rendered.data
        engine = "reportlab"
        warnings.extend(rendered.warnings)
        meta = rendered.meta
        text_diff: dict[str, Any] | None = None
        if verify_text:
            expected = compose.iter_texts(ir)
            actual = render.extract_pdf_text(data)
            text_diff = render.compare_text(expected, actual)
            if not text_diff["ok"]:
                warnings.append(
                    {
                        "code": "TEXT_LAYER_MISMATCH",
                        "severity": "error",
                        "message": f"PDF 文本层缺少 {text_diff['missing_count']} 段文字（文件与预览不一致）",
                        "details": {"missing": text_diff["missing"], "expected_count": text_diff["expected_count"]},
                    }
                )
    elif fmt == "html":
        data = render.render_html(ir).encode("utf-8")
        engine = "html"
        meta = {"density": density}
        text_diff = None
    else:
        data = _render_markdown(ir).encode("utf-8")
        engine = "jinja2"  # 契约 §8 engine 枚举只有这四个，markdown 归到 jinja2 模板引擎
        meta = {"density": density}
        text_diff = None

    path, rel_path, write_warnings = db_mod_store().write_export(result.filename, data, overwrite=overwrite)
    for item in write_warnings:
        warnings.append({"code": "NAMING_COLLISION_SUFFIXED", "severity": "info", "message": item, "details": {}})

    verified = None if text_diff is None else bool(text_diff["ok"])
    artifact_id = BuildRepo().add_artifact(
        build_id,
        {
            "format": fmt,
            "engine": engine,
            "filename": path.name,
            "rel_path": rel_path,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "text_verified": verified,
            "text_diff": (text_diff or {}).get("missing") or [],
            "warnings": warnings,
        },
    )
    status = "exported" if fmt == "pdf" else build.get("status") or "assembled"
    BuildRepo().update(build_id, {"status": status, "warnings": _merge_warnings(warnings)})
    return {
        "artifact": {
            "id": artifact_id,
            "format": fmt,
            "engine": engine,
            "filename": path.name,
            "rel_path": rel_path,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "text_verified": verified,
            "text_diff": text_diff,
            "warnings": _merge_warnings(warnings),
            "layout": meta.get("layout"),
            "download_url": f"/api/v1/artifacts/{artifact_id}/download",
        },
        "naming": {
            "pattern": str(build.get("naming_pattern") or ""),
            "resolved": result.resolved,
            "filename": result.filename,
            "variables": [item.as_dict() for item in result.variables],
        },
        "layout": meta.get("layout"),
        "warnings": _merge_warnings(warnings),
        "missing_slots": assembled["missing_slots"],
    }


def db_mod_store():
    from .storage import Storage

    return Storage()


def _render_markdown(ir: Mapping[str, Any]) -> str:
    header = ir.get("header") or {}
    lines: list[str] = []
    if header.get("name"):
        lines.append(f"# {header['name']}")
    for key in ("contact_line", "available"):
        if header.get(key):
            lines.append(str(header[key]))
    for section in ir.get("sections") or []:
        lines.append("")
        lines.append(f"## {section.get('heading')}")
        if section.get("kind") == "skills":
            lines.extend(str(line) for line in section.get("skills") or [])
            continue
        for entry in section.get("entries") or []:
            head = " ".join(
                part for part in (entry.get("title"), entry.get("role"), entry.get("date")) if part
            )
            if head:
                lines.append(f"**{head}**")
            if entry.get("org"):
                lines.append(str(entry["org"]))
            for line in list(entry.get("bullets") or []) + list(entry.get("facts") or []):
                lines.append(f"- {line}")
    return "\n".join(lines).strip() + "\n"
