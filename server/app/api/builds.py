"""简历构建（build）：CRUD、选中经历、组装、预览、导出、产物下载。

契约要点（docs/API-CONTRACT.md §8）：

* ``POST /builds`` 201 + Location；``position`` 为空且有 ``jd_id`` → 继承 JD 标题；
* ``PUT /builds/{id}/selections`` **整体替换**；选中的 package 非 ``ready`` → 409
  ``PACKAGE_NOT_READY``（宁可挡住也不出一份「未核实」的简历）；
* ``POST /builds/{id}/assemble`` 200，返回 sections/missing_slots/warnings/competitiveness_summary；
* ``POST /builds/{id}/export`` 202 + job_id（渲染可能几百毫秒到几秒，走 job 不阻塞）；
* ``GET /artifacts/{id}/download`` 用 RFC 5987 ``filename*=UTF-8''`` 输出中文名。
"""

from __future__ import annotations

import io
from flask import Blueprint, Response, request, send_file

from ..errors import ApiError
from ..models import BuildIn, SelectionIn, parse_body
from ..repos import BuildRepo, JdRepo, PackageRepo, TemplateRepo
from ..services import export_service, jobrun, naming, render, samples
from ..services.storage import Storage
from . import common

bp = Blueprint("builds", __name__)


def _require(build_id: str) -> dict:
    return BuildRepo().get(build_id, with_selections=False)


def _require_with_selections(build_id: str) -> dict:
    return BuildRepo().get(build_id, with_selections=True)


def _with_download_url(items: list[dict]) -> list[dict]:
    out = []
    for item in items:
        row = dict(item)
        row["download_url"] = f"/api/v1/artifacts/{row.get('id')}/download"
        out.append(row)
    return out


def _view(build: dict, *, include: set[str]) -> dict:
    payload = dict(build)
    payload["artifacts"] = (
        _with_download_url(BuildRepo().list_artifacts(build["id"])) if "artifacts" in include else []
    )
    if "selections" not in include:
        payload.pop("selections", None)
    return payload


def _parse_include() -> set[str]:
    raw = request.args.get("include") or ""
    return {part.strip() for part in raw.split(",") if part.strip()}


@bp.get("/builds")
def list_builds():
    status = request.args.get("status")
    template_id = request.args.get("template_id")
    limit_value = common.limit(50, 200)
    offset_value = common.offset()
    include_archived = str(request.args.get("include_archived") or "").lower() in {"1", "true", "yes", "on"}
    builds = BuildRepo()
    items = builds.list(
        limit=200, status=status, template_id=template_id, include_archived=include_archived
    )
    total = len(items)
    window = items[offset_value : offset_value + limit_value]
    return common.ok(common.list_envelope(window, total, limit_value=limit_value, offset_value=offset_value))


@bp.post("/builds")
def create_build():
    data = parse_body(BuildIn, common.raw_body())
    templates = TemplateRepo()
    templates.require(data.template_id)
    naming.raise_pattern_errors(data.naming_pattern)
    position = (data.position or "").strip()
    if not position and data.jd_id:
        try:
            position = str(JdRepo().get(data.jd_id, with_requirements=False).get("title") or "")
        except ApiError:
            position = ""
    build_id = BuildRepo().create(
        {
            "name": data.name,
            "template_id": data.template_id,
            "jd_id": data.jd_id,
            "company_profile_id": data.company_profile_id,
            "position": position or None,
            "company": data.company,
            "lang": data.lang,
            "naming_pattern": data.naming_pattern,
            "naming_overrides": data.naming_overrides,
        }
    )
    return common.created(_view(_require(build_id), include={"selections", "artifacts"}), f"/api/v1/builds/{build_id}")


@bp.get("/builds/<build_id>")
def get_build(build_id: str):
    include = _parse_include() or {"selections"}
    build = _require_with_selections(build_id) if "selections" in include else _require(build_id)
    return common.ok(_view(build, include=include))


@bp.patch("/builds/<build_id>")
@bp.put("/builds/<build_id>")
def patch_build(build_id: str):
    _require(build_id)
    body = common.raw_body()
    patch: dict = {}
    for key in ("name", "template_id", "jd_id", "company_profile_id", "position", "company", "lang", "status", "naming_pattern", "est_pages"):
        if key in body:
            patch[key] = body[key]
    for key, column in (
        ("naming_overrides", "naming_overrides"),
        ("field_values", "field_values"),
        ("sections_order", "sections_order"),
    ):
        if key in body:
            patch[column] = body[key]
    if "naming_pattern" in patch:
        # 非法模板不许落库：否则要到导出才炸，用户还会以为已经保存成功（AC-NAME-03）
        naming.raise_pattern_errors(str(patch["naming_pattern"] or ""))
    builds = BuildRepo()
    updated = builds.update(build_id, patch) if patch else builds.get(build_id, with_selections=False)
    if "archived" in body:
        # 「不想看见这份简历」≠「删掉它」：归档只写 archived_at，行与产物都留着（AC-BUILD-16）
        updated = builds.set_archived(build_id, archived=bool(body["archived"]))
    return common.ok(_view(updated, include={"selections"}))


@bp.delete("/builds/<build_id>")
def delete_build(build_id: str):
    """默认**归档**（行、选题、产物全保留）；真删要 ``?hard=1&confirm=<build_id>``。

    用户点「删除」时想要的多半是「别在列表里烦我」，而物理删除会立刻让
    ``data/exports/`` 里的 PDF 变成孤儿——磁盘上那 22 个无主 PDF 就是这么来的。
    """
    build = _require(build_id)
    hard = str(request.args.get("hard") or "").lower() in {"1", "true", "yes", "on"}
    if not hard:
        BuildRepo().set_archived(build_id, archived=True)
        return common.no_content()

    confirm = request.args.get("confirm") or ""
    if confirm != build["id"]:
        raise ApiError(
            "CONFIRM_MISMATCH",
            "物理删除需要确认构建 id 一致，本次未删除任何数据",
            details={"expected": build["id"], "got": confirm},
            hint="确认无误请带上 confirm=<build_id>；多数情况下用归档（不带 hard）就够了",
        )
    builds = BuildRepo()
    orphans = [item["rel_path"] for item in builds.list_artifacts(build_id)]
    builds.delete(build_id)
    still_referenced = {str(row["rel_path"]) for row in builds.conn.execute(
        "SELECT rel_path FROM build_artifact"
    ).fetchall()}
    orphaned = sorted(rel for rel in orphans if rel not in still_referenced)
    response = common.no_content()
    response.headers["X-Orphaned-Artifacts"] = str(len(orphaned))
    return response


@bp.put("/builds/<build_id>/selections")
def put_selections(build_id: str):
    build = _require(build_id)
    body = common.raw_body()
    raw_items = None
    if isinstance(body, dict):
        raw_items = body.get("selections")
        if raw_items is None:
            raw_items = body.get("items")
    if raw_items is None:
        raw_items = body if isinstance(body, list) else []
    items = [parse_body(SelectionIn, item) for item in raw_items]

    packages = PackageRepo()
    not_ready: list[dict] = []
    selected: list[dict] = []
    for index, item in enumerate(items):
        package = packages.get(item.package_id, with_variants=False)
        if package is None:
            raise ApiError(
                "NOT_FOUND",
                "选中的经历不存在",
                details={"resource": "package", "id": item.package_id},
            )
        if str(package.get("status")) != "ready":
            not_ready.append(
                {"package_id": item.package_id, "title": package.get("title"), "status": package.get("status")}
            )
            continue
        selected.append(
            {
                "package_id": item.package_id,
                "variant_ids": list(item.variant_ids),
                "order_index": item.order_index if item.order_index else index,
                "overrides": item.overrides,
                "snapshot": package,
            }
        )
    if not_ready:
        raise ApiError(
            "CONFLICT",
            f"{len(not_ready)} 条经历还没有已核实的要点，不能进简历",
            details={"reason": "PACKAGE_NOT_READY", "packages": not_ready},
            hint="在 #/warehouse 里把该经历的至少一条要点标为「已核实」，或把状态设为 ready",
        )

    builds = BuildRepo()
    builds.clear_selections(build_id)
    for item in selected:
        builds.add_selection(
            build_id,
            {
                "package_id": item["package_id"],
                "variant_ids": item["variant_ids"],
                "order_index": item["order_index"],
                "overrides": item["overrides"],
                "snapshot": item["snapshot"],
            },
        )
    updated = builds.get(build_id)
    return common.ok({"build_id": build_id, "selections": updated.get("selections") or [], "count": len(selected)})


@bp.get("/builds/<build_id>/selections")
def get_selections(build_id: str):
    _require(build_id)
    return common.ok({"items": BuildRepo().list_selections(build_id)})


@bp.post("/builds/<build_id>/suggest")
def suggest_selections(build_id: str):
    """给出一份「默认该选哪些经历」的本地建议（不联网、不调模型）。

    演示数据必须排除：``tags`` 含 ``sample`` 或标题以 ``【示例】`` 开头的经历一律不进建议，
    并在 ``excluded`` 里交代原因——用户看到「少了一条」时要知道为什么。

    ``apply=true`` 时顺手把建议写成该 build 的 selections（整体替换），供前端一键采纳。
    """
    _require(build_id)
    body = common.raw_body() or {}
    limit = int(body.get("limit") or 0) or None

    page = PackageRepo().list(status="ready", limit=200, include_variants=False)
    rows = [row for row in page.get("items") or [] if not row.get("deleted_at")]
    real, demo = samples.split(rows)
    # 新的经历在前：先比开始时间，再比结束时间（「至今」排在最前）
    real.sort(
        key=lambda row: (str(row.get("start_date") or ""), str(row.get("end_date") or "9999-99")),
        reverse=True,
    )
    chosen = real[:limit] if limit else real

    selections = [
        {
            "package_id": str(row.get("id")),
            "title": row.get("title"),
            "order_index": index,
            "reason": "ready",
        }
        for index, row in enumerate(chosen)
    ]
    excluded = [
        {"package_id": str(row.get("id")), "title": row.get("title"), "reason": "sample"}
        for row in demo
    ]

    applied = False
    if body.get("apply"):
        builds = BuildRepo()
        builds.clear_selections(build_id)
        for item in selections:
            builds.add_selection(
                build_id,
                {
                    "package_id": item["package_id"],
                    "variant_ids": [],
                    "order_index": item["order_index"],
                    "overrides": {},
                    "snapshot": PackageRepo().get(item["package_id"], with_variants=False),
                },
            )
        applied = True

    return common.ok(
        {
            "build_id": build_id,
            "mode": "heuristic",
            "applied": applied,
            "selections": selections,
            "excluded": excluded,
            "ready_total": len(rows),
            "selected_total": len(selections),
        }
    )


@bp.post("/builds/<build_id>/assemble")
def assemble_build(build_id: str):
    assembled = export_service.assemble(build_id)
    ir = assembled["ir"]
    payload = {
        "build_id": build_id,
        "status": "assembled",
        "lang": ir.get("lang"),
        "page_limit": (assembled.get("template") or {}).get("page_limit") or 1,
        "est_pages": 1 if len(ir.get("sections") or []) else 0,
        "sections": [
            {
                "kind": section.get("kind"),
                "heading": section.get("heading"),
                "entries": len(section.get("entries") or []),
                "bullets": sum(
                    len(entry.get("bullets") or []) + len(entry.get("facts") or [])
                    for entry in section.get("entries") or []
                ),
                "skills": len(section.get("skills") or []),
            }
            for section in ir.get("sections") or []
        ],
        "header": ir.get("header"),
        "missing_slots": assembled["missing_slots"],
        "competitiveness_summary": assembled["competitiveness_summary"],
        "warnings": assembled["warnings"],
        "ir": ir,
    }
    BuildRepo().update(build_id, {"status": "assembled", "warnings": assembled["warnings"], "est_pages": payload["est_pages"]})
    return common.ok(payload)


@bp.get("/builds/<build_id>/preview")
def preview_build(build_id: str):
    """预览：默认返回 IR（json）；``?format=html`` 返回可嵌入 iframe 的自包含 HTML。"""
    if (request.args.get("format") or "json").lower() == "html":
        ir = export_service.assemble(build_id)["ir"]
        html = render.render_html(ir)
        return Response(html, mimetype="text/html; charset=utf-8")
    ir = export_service.assemble(build_id)["ir"]
    return common.ok(ir)


@bp.post("/builds/<build_id>/export")
def export_build(build_id: str):
    _require(build_id)
    body = common.raw_body()
    fmt = str(body.get("format") or "pdf").lower()
    engine = str(body.get("engine") or "auto").lower()
    overwrite = bool(body.get("overwrite"))
    verify = body.get("verify_text", True)
    density = str(body.get("density") or "original").lower()
    include_photo = body.get("include_photo")
    include_photo = None if include_photo is None else bool(include_photo)
    trim_courses = body.get("trim_courses")
    trim_courses = None if trim_courses is None else bool(trim_courses)
    if density not in ("original", "relaxed"):
        raise ApiError(
            "VALIDATION_ERROR",
            "density 只能是 original 或 relaxed",
            details={"fields": [{"field": "density", "rule": "enum", "message": "original|relaxed"}]},
        )
    if engine not in ("auto", "reportlab", "chrome", "docx", "html", "markdown"):
        raise ApiError(
            "VALIDATION_ERROR",
            "engine 取值非法",
            details={"fields": [{"field": "engine", "rule": "enum", "message": "auto|reportlab|chrome|docx"}]},
        )

    # 命名先在本请求里算一遍：缺 {name}/{school} 或模板非法 → 立刻 422，不排 job、不落文件
    extra_pattern = body.get("naming_pattern")
    export_service.precheck_naming(
        build_id,
        pattern=str(extra_pattern) if extra_pattern else None,
        extension="html" if fmt == "html" else ("md" if fmt == "md" else "pdf"),
    )

    def work(report):
        report(20, "组装内容")
        result = export_service.export(
            build_id,
            fmt=fmt,
            overwrite=overwrite,
            density=density,
            verify_text=bool(verify),
            include_photo=include_photo,
            naming_pattern=str(extra_pattern) if extra_pattern else None,
            trim_courses=trim_courses,
        )
        report(100, "导出完成")
        # 契约 §8：job.result_json.artifacts[] 是数组（将来可能一次出多份）
        return {
            "artifacts": [result["artifact"]],
            "naming": result.get("naming"),
            "layout": result.get("layout"),
            "warnings": result.get("warnings") or [],
            "build_id": build_id,
        }

    job_id = jobrun.submit("build_export", work, message=f"导出 {fmt}")
    return common.accepted(
        {
            "job_id": job_id,
            "queued": True,
            "build_id": build_id,
            "format": fmt,
            "density": density,
            "layout": {
                "available_height_pt": render.DENSITY[density]["top"] and round(
                    render.PAGE_H - render.DENSITY[density]["top"] - render.DENSITY[density]["bottom"], 2
                ),
                "text_width_pt": round(
                    render.PAGE_W - render.DENSITY[density]["left"] - render.DENSITY[density]["right"], 2
                ),
            },
        }
    )


@bp.get("/builds/<build_id>/artifacts")
def list_artifacts(build_id: str):
    _require(build_id)
    items = BuildRepo().list_artifacts(build_id)
    for item in items:
        item["download_url"] = f"/api/v1/artifacts/{item['id']}/download"
    return common.ok({"items": items})


@bp.get("/artifacts/<artifact_id>/download")
def download_artifact(artifact_id: str):
    artifact = BuildRepo().get_artifact(artifact_id)
    if artifact is None:
        raise ApiError("NOT_FOUND", "产物不存在", details={"resource": "artifact", "id": artifact_id})
    target = Storage().resolve_export_rel(str(artifact["rel_path"]))
    if not target.exists():
        raise ApiError(
            "NOT_FOUND",
            "产物文件已不在磁盘上（data/exports 被清理过）",
            details={"resource": "artifact_file", "rel_path": artifact["rel_path"]},
            hint="重新导出一次即可",
        )
    data = target.read_bytes()
    filename = str(artifact["filename"])
    response = send_file(
        io.BytesIO(data),
        mimetype=_mime_for(str(artifact["format"])),
        as_attachment=True,
        download_name=filename,
    )
    response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{_quote(filename)}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _quote(text: str) -> str:
    from urllib.parse import quote

    return quote(text, safe="")


def _mime_for(fmt: str) -> str:
    return {
        "pdf": "application/pdf",
        "html": "text/html",
        "md": "text/markdown",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }.get(fmt, "application/octet-stream")

