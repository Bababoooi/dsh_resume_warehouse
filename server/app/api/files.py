"""本地文件存储：上传附件、下载原件、列出与删除。

磁盘命名由 SHA-256 决定（内容寻址），上传文件名只保存在数据库里，
避免路径穿越与同名覆盖；所有路径先 resolve 再断言落在 DATA_ROOT 内。
"""

from __future__ import annotations

import io

from flask import Blueprint, request, send_file

from ..errors import ApiError
from ..repos import AttachmentRepo
from ..services.storage import Storage, validate_upload
from . import common

bp = Blueprint("files", __name__)


@bp.post("/files")
def upload_file():
    file = request.files.get("file")
    if file is None:
        raise ApiError(
            "VALIDATION_ERROR",
            "缺少上传文件字段 file",
            details={"fields": [{"field": "file", "rule": "required", "message": "请选择文件"}]},
        )
    kind = request.form.get("kind") or "other"
    if kind not in ("resume_source", "photo", "evidence", "export", "other"):
        raise ApiError("VALIDATION_ERROR", "kind 非法", details={"fields": [{"field": "kind", "rule": "enum", "message": "resume_source|photo|evidence|export|other"}]})
    privacy = request.form.get("privacy") or ("private" if kind != "export" else "shareable")
    if privacy not in ("private", "shareable"):
        raise ApiError("VALIDATION_ERROR", "privacy 非法", details={"fields": [{"field": "privacy", "rule": "enum", "message": "private|shareable"}]})
    data = file.read()
    original_name = file.filename or "upload.bin"
    validate_upload(original_name, data)
    stored = Storage().save_attachment(data, original_name=original_name, kind=kind, privacy=privacy)
    payload = stored.as_dict()
    payload["location"] = f"/api/v1/files/{stored.attachment_id}"
    return common.created(payload, payload["location"])


@bp.get("/files")
def list_files():
    repo = AttachmentRepo()
    items = repo.list(
        kind=request.args.get("kind") or None,
        privacy=request.args.get("privacy") or None,
        limit=common.limit(default=50, maximum=200),
    )
    for item in items:
        item["location"] = f"/api/v1/files/{item['id']}"
    payload = common.list_envelope(items, len(items), limit_value=len(items) or 1, offset_value=0)
    return common.ok(payload)


@bp.get("/files/<attachment_id>")
def download_file(attachment_id: str):
    storage = Storage()
    path, row = storage.open_attachment(attachment_id)
    buffer = io.BytesIO(path.read_bytes())
    response = send_file(
        buffer,
        mimetype=row["mime"],
        as_attachment=True,
        download_name=row["original_name"],
        max_age=0,
    )
    response.headers["Content-Security-Policy"] = "sandbox"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.delete("/files/<attachment_id>")
def delete_file(attachment_id: str):
    storage = Storage()
    if not storage.get_attachment(attachment_id):
        raise ApiError("NOT_FOUND", "附件不存在", details={"resource": "attachment", "id": attachment_id})
    storage.delete_attachment(attachment_id, remove_file=True)
    return common.no_content()
