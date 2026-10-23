"""个人档案单例（GET/PUT /profile，POST /profile/photo）。

* 档案是命名模板的唯一数据来源，前端禁止硬编码姓名/校名；
* ``PUT`` 是部分更新：显式 ``null`` 清空，未提供的键保持原值；
* 照片只在本机保存与渲染，**永不进入 LLM payload**。
"""

from __future__ import annotations

import io
from typing import Any

from flask import Blueprint, request, send_file

from ..errors import ApiError
from ..models import EducationFactsIn, PhotoConfirmIn, ProfilePatch
from ..repos import AttachmentRepo, ProfileRepo
from ..services import education_facts
from ..services.storage import Storage, validate_upload
from . import common

bp = Blueprint("profile", __name__)

PHOTO_EXTS = ("png", "jpg", "jpeg")


def _photo_payload(profile: dict[str, Any]) -> dict[str, Any]:
    path = profile.get("photo_path")
    extra = profile.get("extra") or {}
    return {
        "photo_path": path,
        "photo_url": f"/api/v1/files/profile-photo" if path else None,
        "photo_source": extra.get("photo_source") or ("uploaded" if path else None),
    }


@bp.get("/profile")
def get_profile():
    repo = ProfileRepo()
    view = repo.public_view()
    view.update(_photo_payload(view))
    return common.ok(view)


@bp.put("/profile")
def put_profile():
    patch = common.parsed(ProfilePatch)
    repo = ProfileRepo()
    payload = patch.model_dump(exclude_unset=True)
    if not payload:
        raise ApiError("VALIDATION_ERROR", "没有需要更新的字段", details={"fields": []})
    profile = repo.upsert(payload)
    view = repo.public_view()
    view.update(_photo_payload(profile))
    return common.ok(view)


@bp.get("/profile/education-facts")
def get_education_facts():
    """教育段补充行（GPA / 主修课程）：读默认模板里的那一行原文。"""
    return common.ok(education_facts.read())


@bp.put("/profile/education-facts")
def put_education_facts():
    """写回默认模板教育段的 `static_text`（写前落快照，空数组 = 清空）。"""
    body = common.parsed(EducationFactsIn)
    return common.ok(education_facts.write(list(body.lines)))


@bp.post("/profile/photo")
def upload_photo():
    file = request.files.get("file") or request.files.get("photo")
    if file is None:
        raise ApiError("VALIDATION_ERROR", "缺少上传文件字段 file", details={"fields": [{"field": "file", "rule": "required", "message": "请选择照片文件"}]})
    data = file.read()
    filename = file.filename or "photo.png"
    validate_upload(filename, data, allowed=PHOTO_EXTS)
    storage = Storage()
    stored = storage.save_attachment(
        data,
        original_name=filename,
        kind="photo",
        privacy="private",
        allowed_exts=PHOTO_EXTS,
    )
    repo = ProfileRepo()
    current = repo.get()
    extra = dict(current.get("extra") or {})
    extra["photo_source"] = "uploaded"
    extra["photo_attachment_id"] = stored.attachment_id
    rel_path = stored.path.relative_to(storage.paths.root).as_posix()
    repo.upsert({"photo_path": rel_path, "extra": extra})
    profile = repo.get()
    payload = _photo_payload(profile)
    payload.update({"attachment_id": stored.attachment_id, "bytes": stored.bytes, "deduplicated": stored.deduplicated})
    return common.ok(payload)


@bp.put("/profile/photo")
def confirm_photo():
    """确认导入候选照片（D-23）：导入阶段只返回候选，用户显式确认后才写 photo_path。"""
    body = common.parsed(PhotoConfirmIn)
    attachments = AttachmentRepo()
    row = attachments.get(body.attachment_id) if body.attachment_id else attachments.get_by_sha(body.sha256)
    if row is None:
        raise ApiError("NOT_FOUND", "找不到该照片附件", details={"resource": "attachment", "attachment_id": body.attachment_id, "sha256": body.sha256})
    if row["kind"] != "photo":
        raise ApiError(
            "VALIDATION_ERROR",
            "该附件不是照片",
            details={"fields": [{"field": "attachment_id", "rule": "kind=photo", "message": f"实际 kind={row['kind']}"}]},
        )
    storage = Storage()
    path = storage.locate_attachment(row)
    if not path.exists():
        raise ApiError("NOT_FOUND", "照片文件已不存在", details={"resource": "photo", "sha256": row["sha256"]})
    rel_path = path.relative_to(storage.paths.root).as_posix()
    repo = ProfileRepo()
    current = repo.get()
    extra = dict(current.get("extra") or {})
    extra["photo_source"] = "imported"
    extra["photo_attachment_id"] = row["id"]
    repo.upsert({"photo_path": rel_path, "extra": extra})
    payload = _photo_payload(repo.get())
    payload.update({"attachment_id": row["id"], "sha256": row["sha256"], "bytes": row["bytes"], "confirmed": True})
    return common.ok(payload)


@bp.delete("/profile/photo")
def delete_photo():
    """清除当前照片（只解绑，不删文件）。

    契约补注（captain m01505 ③）：这是「点错就丢设置」的高危操作，所以**不返回 204**，
    而是回 200 并带上 ``previous_photo_path``，前端可据此做撤销提示
    （撤销 = ``PUT /profile/photo`` 用同一个 attachment_id / sha256 再确认一次）。
    文件本身不删：照片是内容寻址、可能被多处引用；清理孤儿走 ``scripts/clean_orphan_photos.py``。
    """
    repo = ProfileRepo()
    current = repo.get()
    previous = current.get("photo_path")
    previous_attachment = (current.get("extra") or {}).get("photo_attachment_id")
    extra = dict(current.get("extra") or {})
    extra.pop("photo_source", None)
    extra.pop("photo_attachment_id", None)
    repo.upsert({"photo_path": None, "extra": extra})
    return common.ok(
        {
            "cleared": True,
            "previous_photo_path": previous,
            "previous_attachment_id": previous_attachment,
            "photo_url": None,
            "note": "照片已从简历解绑；文件保留在 data/profile/ 以便撤销"
            "（PUT /profile/photo 传 attachment_id 或 sha256 即可恢复）",
            "restore_endpoint": "PUT /api/v1/profile/photo",
        }
    )


@bp.get("/files/profile-photo")
def get_photo():
    repo = ProfileRepo()
    profile = repo.get()
    rel = profile.get("photo_path")
    if not rel:
        raise ApiError("NOT_FOUND", "尚未上传照片", details={"resource": "profile_photo"})
    storage = Storage()
    path = storage.paths.assert_within(storage.paths.root / rel)
    if not path.exists():
        raise ApiError("NOT_FOUND", "照片文件已不存在", details={"resource": "profile_photo", "rel_path": rel})
    response = send_file(io.BytesIO(path.read_bytes()), mimetype="image/png", as_attachment=False, download_name=path.name)
    response.headers["Content-Security-Policy"] = "sandbox"
    response.headers["Cache-Control"] = "private, max-age=60"
    return response
