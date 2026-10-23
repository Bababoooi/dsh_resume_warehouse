"""经历包（Package）与 bullet 变体：/packages 下的 CRUD、搜索、对话式打包与变体生成。

不变量 I1：``status=ready`` 必须至少 1 条 ``verified=1`` 的 bullet（repo 层强制，
409 + ``details.reason="PACKAGE_NEEDS_VERIFIED_VARIANT"`` + ``details.unverified[]``）。

契约 §4：PATCH 部分更新、软删可 ``restore``、``duplicate`` 复制为新草稿、
``variants/generate`` 必须先有 consent preview 且结果**不自动入库**。
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, request

from ..errors import ApiError
from ..models import (
    BulkVerifyIn,
    GenerateVariantsIn,
    PackageDraftIn,
    PackageIn,
    PackagePatch,
    VariantIn,
    VariantPatch,
)
from ..repos import PackageRepo, PreviewRepo
from ..services import jobrun, packager
from . import common

bp = Blueprint("packages", __name__)


def _require_variant(repo: PackageRepo, package_id: str, variant_id: str) -> dict[str, Any]:
    variant = repo.get_variant(variant_id)
    if variant["package_id"] != package_id:
        raise ApiError(
            "NOT_FOUND",
            "该 bullet 变体不属于此经历包",
            details={"resource": "variant", "id": variant_id, "package_id": package_id},
        )
    return variant


def _with_variants_flag() -> bool:
    """契约：``GET /packages/{id}`` 默认不带 variants，``?include=variants`` 才带。"""
    include = (request.args.get("include") or "").lower()
    return bool(include) and ("variant" in include or include in ("all", "full"))


# --------------------------------------------------------------------------------------
# 列表 / 健康度 / 创建 / 草稿 / 详情
# --------------------------------------------------------------------------------------
#: 查询参数里表示「真」的字面量（与 import 端点的 `_truthy` 同口径）
_TRUTHY = ("1", "true", "yes", "on")


def _truthy_arg(name: str) -> bool:
    return str(request.args.get(name, "")).strip().lower() in _TRUTHY


@bp.get("/packages")
def list_packages():
    repo = PackageRepo()
    limit_value = common.limit(default=50, maximum=200)
    offset_value = common.offset()
    result = repo.list(
        kind=request.args.get("kind") or None,
        status=request.args.get("status") or None,
        tag=request.args.get("tag") or None,
        org=request.args.get("org") or None,
        q=request.args.get("q") or None,
        limit=limit_value,
        offset=offset_value,
        # 列表默认轻量（不带 variants）；前端 #/warehouse 要显示每条经历有几个要点，
        # 会显式带 ?include_variants=1。此前这里写死 False 导致界面永远「0 条要点」。
        include_variants=_truthy_arg("include_variants"),
    )
    payload = common.list_envelope(
        result["items"], result["total_estimate"], limit_value=limit_value, offset_value=offset_value
    )
    return common.ok(payload)


@bp.get("/packages/stats")
def package_stats():
    """库健康度（工作台的「经历 / 变体 / 待核实 / 模板」四个数字）。"""
    return common.ok(PackageRepo().stats())


@bp.post("/packages")
def create_package():
    payload = common.parsed(PackageIn)
    data = payload.model_dump(exclude_none=True)
    variants = data.pop("variants", None) or []
    repo = PackageRepo()
    package_id = repo.create(data)
    for variant in variants:
        repo.add_variant(package_id, variant, conflict="update")
    package = repo.require(package_id)
    return common.created(package, f"/api/v1/packages/{package_id}")


@bp.post("/packages/draft")
def draft_package():
    """对话式打包：自由文本 → Package 草稿（**不落库**，纯本地启发式，零出网）。"""
    payload = common.parsed(PackageDraftIn)
    return common.ok(
        packager.draft_package(
            payload.text,
            kind=payload.kind,
            lang=payload.lang,
            title=payload.title,
            org=payload.org,
            role=payload.role,
        )
    )


@bp.get("/packages/<package_id>")
def get_package(package_id: str):
    repo = PackageRepo()
    package = repo.get(package_id, with_variants=False)
    if package is None:
        raise ApiError("NOT_FOUND", "经历包不存在", details={"resource": "package", "id": package_id})
    if _with_variants_flag():
        package["variants"] = repo.list_variants(package_id)
    return common.ok(package)


@bp.patch("/packages/<package_id>")
@bp.put("/packages/<package_id>")
def update_package(package_id: str):
    payload = common.parsed(PackagePatch)
    repo = PackageRepo()
    repo.require(package_id)
    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        raise ApiError("VALIDATION_ERROR", "没有需要更新的字段", details={"fields": []})
    return common.ok(repo.update(package_id, patch))


@bp.delete("/packages/<package_id>")
def delete_package(package_id: str):
    repo = PackageRepo()
    repo.require(package_id)
    repo.delete(package_id)
    return common.no_content()


@bp.post("/packages/<package_id>/restore")
def restore_package(package_id: str):
    return common.ok(PackageRepo().restore(package_id))


@bp.post("/packages/<package_id>/duplicate")
def duplicate_package(package_id: str):
    repo = PackageRepo()
    repo.require(package_id)
    new_id = repo.duplicate(package_id)
    return common.created(repo.require(new_id), f"/api/v1/packages/{new_id}")


# --------------------------------------------------------------------------------------
# 变体
# --------------------------------------------------------------------------------------
@bp.get("/packages/<package_id>/variants")
def list_variants(package_id: str):
    repo = PackageRepo()
    repo.require(package_id)
    items = repo.list_variants(package_id)
    lang = request.args.get("lang") or None
    tone = request.args.get("tone") or None
    bullet_key = request.args.get("bullet_key") or None
    if lang:
        items = [v for v in items if v.get("lang") == lang]
    if tone:
        items = [v for v in items if v.get("tone") == tone]
    if bullet_key:
        items = [v for v in items if v.get("bullet_key") == bullet_key]
    payload = common.list_envelope(items, len(items), limit_value=max(len(items), 1), offset_value=0)
    payload["groups"] = len({(v.get("bullet_key"), v.get("tone")) for v in items})
    payload["bullet_keys"] = sorted({v.get("bullet_key") for v in items})
    payload["tones"] = sorted({v.get("tone") for v in items})
    return common.ok(payload)


@bp.post("/packages/<package_id>/variants")
def add_variant(package_id: str):
    payload = common.parsed(VariantIn)
    repo = PackageRepo()
    variant = repo.add_variant(package_id, payload.model_dump(exclude_none=True))
    return common.created(variant, f"/api/v1/variants/{variant['id']}")


@bp.patch("/variants/<variant_id>")
@bp.put("/variants/<variant_id>")
@bp.patch("/packages/<package_id>/variants/<variant_id>")
@bp.put("/packages/<package_id>/variants/<variant_id>")
def update_variant(variant_id: str, package_id: str | None = None):
    """变体更新。**推荐**用嵌套路由 ``/packages/{pid}/variants/{vid}``；``/variants/{id}``
    保留可用但已标 ``deprecated``（响应头 ``Deprecation``），因为它无法校验归属。"""
    payload = common.parsed(VariantPatch)
    repo = PackageRepo()
    if package_id is not None:
        _require_variant(repo, package_id, variant_id)
    else:
        repo.get_variant(variant_id)
    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        raise ApiError("VALIDATION_ERROR", "没有需要更新的字段", details={"fields": []})
    result = repo.update_variant(variant_id, patch)
    if package_id is None:
        return _deprecated(common.ok(result), f"/api/v1/packages/{result['package_id']}/variants/{variant_id}")
    return common.ok(result)


@bp.delete("/variants/<variant_id>")
@bp.delete("/packages/<package_id>/variants/<variant_id>")
def delete_variant(variant_id: str, package_id: str | None = None):
    repo = PackageRepo()
    if package_id is not None:
        _require_variant(repo, package_id, variant_id)
    else:
        repo.get_variant(variant_id)
    variant = repo.get_variant(variant_id)
    repo.delete_variant(variant_id)
    if package_id is None:
        return _deprecated(
            common.no_content(), f"/api/v1/packages/{variant['package_id']}/variants/{variant_id}"
        )
    return common.no_content()


def _deprecated(response, successor: str):
    """给「无归属校验」的旧路由打弃用标记（response header，不改响应体）。"""
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = f'<{successor}>; rel="successor-version"'
    return response


@bp.post("/packages/<package_id>/verify")
def bulk_verify(package_id: str):
    payload = common.parsed(BulkVerifyIn)
    repo = PackageRepo()
    repo.require(package_id)
    updated = 0
    for variant_id in payload.variant_ids:
        variant = repo.get_variant(variant_id)
        if variant["package_id"] != package_id:
            continue
        repo.update_variant(variant_id, {"verified": payload.verified})
        updated += 1
    return common.ok({"updated": updated, "verified": payload.verified, "package": repo.require(package_id)})


# --------------------------------------------------------------------------------------
# LLM 生成变体（必先 consent preview；结果只进 job，不自动入库）
# --------------------------------------------------------------------------------------
@bp.post("/packages/<package_id>/variants/generate")
def generate_variants(package_id: str):
    payload = common.parsed(GenerateVariantsIn)
    repo = PackageRepo()
    repo.require(package_id)

    if not payload.preview_id:
        raise ApiError(
            "LLM_CONSENT_REQUIRED",
            "生成变体前必须先预览将发送的字段并确认",
            details={"endpoint": "POST /api/v1/llm/preview", "purpose": "bullets_generate"},
            hint="先调 /api/v1/llm/preview 拿到 preview_id，再把 preview_id 一起提交",
        )

    preview = PreviewRepo().get(payload.preview_id)
    if preview["purpose"] != "bullets_generate":
        raise ApiError(
            "LLM_CONSENT_MISMATCH",
            "该预览的用途不是变体生成",
            details={"preview_purpose": preview["purpose"], "expected": "bullets_generate"},
        )
    if preview["status"] != "pending":
        raise ApiError(
            "LLM_CONSENT_MISMATCH",
            "该预览已被使用或已放弃，请重新预览",
            details={"status": preview["status"]},
        )

    tones = payload.tones or ["impact"]
    expected = len(payload.bullet_keys or []) * len(tones) or len(tones)
    sha = payload.expected_payload_sha256 or preview["payload_sha256"]

    def work(report) -> dict[str, Any]:
        from ..services.consent import ConsentService

        report(30, "正在生成变体")
        service = ConsentService()
        result = service.complete(payload.preview_id, sha)
        parsed = result.get("parsed") or {}
        raw_variants = parsed.get("variants") if isinstance(parsed, dict) else None
        if not isinstance(raw_variants, list):
            raw_variants = []
        normalized: list[dict[str, Any]] = []
        for item in raw_variants[: max(expected, 1) * 2]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            key = item.get("bullet_key") or item.get("key")
            if payload.bullet_keys and key not in payload.bullet_keys:
                # 模型常把标题当 key 回显（如 "racing_game_ab_test_analysis"），
                # 与库里真实 bullet_key 对不上 → 落库后会变成一对「孤儿变体」，
                # 导出时既匹配不到事实、又会和正确 key 的变体重名。这里按请求键顺序归一。
                key = payload.bullet_keys[min(len(normalized), len(payload.bullet_keys) - 1)]
            normalized.append(
                {
                    "bullet_key": key,
                    "tone": item.get("tone") or tones[0],
                    "lang": item.get("lang") or payload.lang,
                    "text": text[:400],
                    "keywords": item.get("keywords") or [],
                    "verified": False,
                    "llm_generated": True,
                    "source": "llm_rewrite",
                }
            )
        report(90, "解析模型输出")
        return {
            "package_id": package_id,
            "expected_variants": expected,
            "variants": normalized,
            "warnings": result.get("warnings") or [],
            "usage": result.get("usage") or {},
            "model": result.get("model"),
            "note": "结果未入库：用户逐条确认后再 POST /packages/{id}/variants",
        }

    job_id = jobrun.submit("bullets_generate", work, message="生成 bullet 变体")
    return common.accepted({"job_id": job_id, "expected_variants": expected, "package_id": package_id})


@bp.post("/packages/reindex")
def reindex():
    return common.ok({"indexed": PackageRepo().rebuild_index()})
