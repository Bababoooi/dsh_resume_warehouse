"""命名模板校验（POST /naming/validate）。

纯函数：**任何输入都返回 200**（``valid`` + ``errors``/``warnings``），
真正导出时才把 ``errors`` 升级为 422 且不落任何文件。
"""

from __future__ import annotations

from flask import Blueprint

from ..repos import ProfileRepo, SettingsRepo
from ..services import naming
from ..models import NamingValidateIn
from . import common

bp = Blueprint("naming", __name__)


@bp.post("/naming/validate")
def validate():
    payload = common.parsed(NamingValidateIn)
    settings = SettingsRepo()
    pattern = payload.pattern if payload.pattern is not None else ""
    if not pattern:
        pattern = str(settings.get("naming_template") or "{position}-{name}-{school}")
    profile = ProfileRepo().get()
    result = naming.resolve_filename(
        pattern,
        lang=payload.lang,
        profile=profile,
        position=payload.position,
        company=payload.company,
        overrides=payload.overrides or {},
        date_value=payload.date,
    )
    body = result.as_dict()
    body["pattern"] = pattern
    body["lang"] = payload.lang
    return common.ok(body)


@bp.get("/naming/template")
def get_template():
    settings = SettingsRepo()
    return common.ok({"naming_template": settings.get("naming_template")})


@bp.put("/naming/template")
def put_template():
    payload = common.raw_body()
    pattern = str(payload.get("naming_template") or "").strip()
    if not pattern:
        raise common.ApiError("NAMING_EMPTY", "命名模板不能为空", details={"field": "naming_template"})
    probe = naming.resolve_filename(pattern, profile=ProfileRepo().get())
    if probe.errors:
        naming.raise_on_errors(probe)
    SettingsRepo().set("naming_template", pattern)
    return common.ok({"naming_template": pattern, "preview": probe.as_dict()})
