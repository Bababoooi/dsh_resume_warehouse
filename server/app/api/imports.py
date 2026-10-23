"""导入相关端点（契约 §5）。

* ``POST /imports`` 同时支持 multipart 文件与 JSON 粘贴文本；
* 解析失败降级为草稿 + warnings（不 500、不 422，除非一个字都没抽到）；
* ``POST /imports/{id}/commit`` 才落 Template（section → block → slot）。
"""

from __future__ import annotations

from flask import Blueprint, current_app, request

from ..errors import ApiError, bad_request, not_found, validation_error
from ..repos import ImportRepo, TemplateRepo
from ..services import import_service, storage as storage_mod
from .common import created, limit as limit_param, list_envelope, offset as offset_param, ok, raw_body

bp = Blueprint("imports", __name__)

#: 表单字段候选名（前端/DSH Skill 可能用 file / document / upload）
_FILE_FIELDS = ("file", "document", "upload", "resume")


def _storage() -> storage_mod.Storage:
    return storage_mod.Storage()


def _form_lang(value: str | None) -> str | None:
    if not value:
        return None
    if value not in ("zh", "en"):
        raise validation_error([{"field": "lang", "rule": "one_of(zh,en)", "message": "lang 只能是 zh 或 en"}])
    return value


def _form_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).lower() in ("1", "true", "yes", "on")


@bp.post("/imports")
def create_import():
    content_type = request.content_type or ""
    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        upload = None
        for field in _FILE_FIELDS:
            candidate = request.files.get(field)
            if candidate is not None and candidate.filename:
                upload = candidate
                break
        if upload is not None:
            data = upload.read()
            if not data:
                raise bad_request("上传的文件是空的", details={"field": "file"})
            result = import_service.run_import(
                data,
                filename=upload.filename or "upload.pdf",
                parser=request.form.get("parser") or None,
                lang=_form_lang(request.form.get("lang")),
                storage=_storage(),
            )
        else:
            text = request.form.get("text") or ""
            if not text.strip():
                raise bad_request("缺少文件或粘贴文本", details={"fields": _FILE_FIELDS + ("text",)})
            result = import_service.run_import(
                text.encode("utf-8"),
                filename=request.form.get("filename") or import_service.DEFAULT_PASTE_NAME,
                parser=request.form.get("parser") or "txt",
                lang=_form_lang(request.form.get("lang")),
                storage=_storage(),
            )
    else:
        body = raw_body()
        text = str(body.get("text") or "")
        if not text.strip():
            raise validation_error(
                [{"field": "text", "rule": "required", "message": "text 不能为空（或用 multipart 上传文件）"}]
            )
        result = import_service.run_import(
            text.encode("utf-8"),
            filename=str(body.get("filename") or import_service.DEFAULT_PASTE_NAME),
            parser=str(body.get("parser") or "txt"),
            lang=_form_lang(body.get("lang")),
            storage=_storage(),
        )
    return created(result, location=f"/api/v1/imports/{result['import_id']}")


@bp.get("/imports")
def list_imports():
    include_deleted = _truthy(request.args.get("include_deleted"))
    rows = ImportRepo().list(
        limit=limit_param(20, 100), offset=offset_param(), include_deleted=include_deleted
    )
    items = []
    for row in rows:
        items.append(
            {
                "import_id": row["id"],
                "status": row["status"],
                "parser": row["parser"],
                "attachment_id": row.get("attachment_id"),
                "template_id": row.get("result_template_id"),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "deleted_at": row.get("deleted_at"),
                "deleted": bool(row.get("deleted_at")),
            }
        )
    limit_value = limit_param(20, 100)
    return ok(list_envelope(items, len(items), limit_value=limit_value, offset_value=offset_param()))


@bp.delete("/imports/<import_id>")
def delete_import(import_id: str):
    """软删导入历史（可恢复）。

    导入历史里存着用户真实简历的解析副本；这里只标 ``deleted_at``，文件与行都保留，
    真删由 ``scripts/prune_probe_data.py --prune-import-jobs`` 在用户同意后执行。
    """
    row = ImportRepo().soft_delete(import_id)
    # 模板是用户的资产：删导入历史只为清理草稿，模板必须留下（R-c 不断链）。
    kept_template_id = row.get("result_template_id")
    # v8 之后的派生包已在 soft_delete 的同一事务里按同一时间戳连带软删；
    # 这里只兜底处理没有 source_import_job_id 的老行（按 tags 反查）。
    cascaded = list(row.get("cascaded_package_ids") or [])
    # 老数据（v8 之前没有 source_import_job_id）只能靠 tags 兜底，且不与上面重复。
    for package_id in import_service.cascade_soft_delete_packages(import_id):
        if package_id not in cascaded:
            cascaded.append(package_id)
    return ok(
        {
            "import_id": row["id"],
            "deleted": True,
            "packages_deleted": cascaded,
            "deleted_at": row.get("deleted_at"),
            "template_retained": {"kept": bool(kept_template_id), "template_id": kept_template_id},
            "restore_endpoint": f"POST /api/v1/imports/{import_id}/restore",
            "note": "已从导入历史隐藏，文件仍在本机；可随时恢复",
        }
    )


@bp.post("/imports/<import_id>/restore")
def restore_import(import_id: str):
    row = ImportRepo().restore(import_id)
    return ok({"import_id": row["id"], "deleted": False, "deleted_at": row.get("deleted_at")})


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@bp.get("/imports/<import_id>")
def get_import(import_id: str):
    return ok(import_service.view(import_id))


@bp.get("/imports/<import_id>/draft")
def get_draft(import_id: str):
    row = ImportRepo().get(import_id)
    return ok(
        {
            "import_id": row["id"],
            "status": row["status"],
            "lang": (row.get("draft") or {}).get("lang") or "zh",
            "draft": row.get("draft") or {},
            "warnings": row.get("warnings") or [],
        }
    )


@bp.put("/imports/<import_id>/draft")
def put_draft(import_id: str):
    body = raw_body()
    draft = body.get("draft") if isinstance(body.get("draft"), dict) else body
    if not isinstance(draft, dict):
        raise validation_error([{"field": "draft", "rule": "object", "message": "draft 必须是对象"}])
    return ok(import_service.update_draft(import_id, draft))


@bp.post("/imports/<import_id>/commit")
def commit_import(import_id: str):
    body = raw_body() if request.data else {}
    template_name = body.get("template_name") or body.get("name") or f"导入模板 {import_id[-6:]}"
    page_limit = body.get("page_limit")
    if page_limit is not None and int(page_limit) not in (1, 2):
        raise validation_error([{"field": "page_limit", "rule": "one_of(1,2)", "message": "page_limit 只能是 1 或 2"}])
    result = import_service.commit(
        import_id,
        template_name=str(template_name),
        lang=_form_lang(body.get("lang")),
        page_limit=int(page_limit or 1),
        set_default=bool(body.get("set_default")),
        layout=body.get("layout_json") or body.get("layout") or None,
        apply_identity=bool(body.get("apply_identity")),
        apply_photo=bool(body.get("apply_photo")),
        also_create_packages=bool(body.get("also_create_packages")),
        overwrite_profile=bool(body.get("overwrite_profile")),
    )
    return created(result, location=f"/api/v1/templates/{result['template_id']}")


@bp.post("/imports/<import_id>/export-draft")
def export_draft(import_id: str):
    return ok(import_service.write_artifacts(import_id, storage=_storage()))


#: ---------------------------------------------------------------- templates
tpl = Blueprint("templates", __name__)


@tpl.get("/templates")
def list_templates():
    repo = TemplateRepo()
    lang = request.args.get("lang")
    if lang and lang not in ("zh", "en"):
        raise validation_error([{"field": "lang", "rule": "one_of(zh,en)", "message": "lang 只能是 zh 或 en"}])
    limit_value = limit_param(50, 200)
    items = [tpl_view(row, with_blocks=False) for row in repo.list(limit=limit_value, lang=lang)]
    envelope = list_envelope(items, len(items), limit_value=limit_value, offset_value=offset_param())
    # captain P1 规则 B：t8 不需要猜「用哪个模板」——这里直接给出解析结果。
    resolved = repo.resolved_default(lang=lang)
    envelope["resolved_default"] = tpl_view(resolved, with_blocks=False) if resolved else None
    return ok(envelope)


@tpl.get("/templates/<template_id>")
def get_template(template_id: str):
    row = TemplateRepo().get(template_id)
    if row is None:
        raise not_found("模板不存在", details={"resource": "template", "id": template_id})
    return ok(tpl_view(row))


@tpl.get("/templates/default")
def get_default_template():
    repo = TemplateRepo()
    explicit = repo.default()
    row = explicit or repo.resolved_default(lang=request.args.get("lang"))
    if row is None:
        raise ApiError("NOT_FOUND", "还没有默认模板", details={"resource": "template"}, hint="先导入一份简历生成模板")
    view = tpl_view(row)
    view["resolved"] = explicit is None  # true = 没有显式 default，按 updated_at 兜底
    return ok(view)


@tpl.post("/templates/<template_id>/default")
def set_default_template(template_id: str):
    """显式指定默认模板（t8 组装前置；没有默认模板时 assemble 必须 409，不许猜）。"""
    row = TemplateRepo().set_default(template_id)
    view = tpl_view(row, with_blocks=False)
    view["resolved"] = False  # 这次是显式设置，不是兜底
    return ok(view)


@tpl.delete("/templates/<template_id>")
def delete_template(template_id: str):
    from .common import no_content

    if not TemplateRepo().delete(template_id):
        raise not_found("模板不存在", details={"resource": "template", "id": template_id})
    return no_content()


def tpl_view(row: dict, *, with_blocks: bool = True) -> dict:
    data = {
        "id": row["id"],
        "name": row["name"],
        "lang": row["lang"],
        "source_kind": row.get("source_kind"),
        "source_file_id": row.get("source_file_id"),
        "page_limit": row.get("page_limit"),
        "is_default": bool(row.get("is_default")),
        "target_role_family": row.get("target_role_family"),
        "layout": row.get("layout") or {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if with_blocks:
        data["blocks"] = row.get("blocks") or []
    return data


#: 供 ``api/__init__.py`` 统一注册
imports_bp = bp
templates_bp = tpl
