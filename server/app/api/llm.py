"""LLM 通道：状态、预览（将发送字段清单）、一次性授权发送、取消、出网审计。

数据上云只有一个出口：``adapters/llm_client.py``；
本模块只负责「先给用户看清单，再按确认发送」，绝不绕过 consent。
"""

from __future__ import annotations

from datetime import datetime

from flask import Blueprint, request

from .. import config as config_mod
from ..adapters import egress_guard
from ..errors import ApiError
from ..models import CompleteIn, PreviewIn
from ..repos import LlmLogRepo, PreviewRepo, SettingsRepo
from ..services.consent import ConsentService
from . import common

bp = Blueprint("llm", __name__)


@bp.get("/llm/status")
def status():
    cfg = config_mod.get_config()
    settings = SettingsRepo()
    return common.ok(
        {
            "provider": cfg.provider,
            "provider_label": cfg.preset.label,
            "base_url": cfg.base_url,
            "model": cfg.model,
            "model_analysis": cfg.model_analysis,
            "key_set": cfg.key_set,
            "ready": cfg.ready,
            "not_ready_reason": cfg.not_ready_reason,
            "reachable": settings.get("llm_last_check_reachable"),
            "last_check_at": settings.get("llm_last_check_at"),
            "allowed_hosts": egress_guard.allowed_hosts(cfg),
            "timeouts": {
                "connect_s": cfg.connect_timeout,
                "read_s": cfg.read_timeout,
                "total_s": float(cfg.timeout_seconds),
            },
            "max_retries": cfg.max_retries,
            "purposes": [
                "jd_analyze",
                "company_profile",
                "build_suggest",
                "bullets_generate",
                "summary_polish",
            ],
        }
    )


@bp.post("/llm/preview")
def preview():
    payload = common.parsed(PreviewIn)
    service = ConsentService()
    result = service.build_preview(
        {
            "purpose": payload.purpose,
            "provider_override": payload.provider_override,
            "selections": payload.selections.model_dump(exclude_none=True),
            "options": payload.options.model_dump(exclude_none=True),
        }
    )
    return common.created(result, f"/api/v1/llm/previews/{result['preview_id']}")


@bp.get("/llm/previews/<preview_id>")
def get_preview(preview_id: str):
    return common.ok(ConsentService().get_preview(preview_id))


@bp.post("/llm/complete")
def complete():
    payload = common.parsed(CompleteIn)
    if not (payload.preview_id or "").strip():
        # 没有 preview_id 说明用户还没看「将发送字段清单」——这是同意门禁（428），不是找不到资源
        raise ApiError(
            "LLM_CONSENT_REQUIRED",
            "缺少 preview_id：请先 POST /llm/preview 查看将发送的字段清单并确认",
            hint="先调用 POST /api/v1/llm/preview，拿到 preview_id 与 payload_sha256 再发送",
            details={"required": ["preview_id", "expected_payload_sha256"]},
        )
    result = ConsentService().complete(payload.preview_id, payload.expected_payload_sha256)
    return common.ok(result)


@bp.post("/llm/previews/<preview_id>/reject")
def reject(preview_id: str):
    return common.ok(ConsentService().reject(preview_id))


@bp.get("/llm/egress-log")
def egress_log():
    repo = LlmLogRepo()
    items = repo.list(limit=common.limit(default=20, maximum=200))
    for item in items:
        # 审计只保留字段名与大小，不返回正文
        item.pop("payload_json", None)
    payload = common.list_envelope(items, len(items), limit_value=len(items) or 1, offset_value=0)
    return common.ok(payload)


@bp.get("/llm/previews")
def list_previews():
    repo = PreviewRepo()
    limit_value = common.limit(default=20, maximum=100)
    rows = repo.conn.execute(
        "SELECT id, purpose, provider, model, status, created_at, expires_at FROM llm_preview"
        " ORDER BY created_at DESC LIMIT ?",
        (limit_value,),
    ).fetchall()
    items = [dict(row) for row in rows]
    payload = common.list_envelope(items, len(items), limit_value=limit_value, offset_value=0)
    return common.ok(payload)


@bp.get("/llm/purposes")
def purposes():
    from ..adapters import providers

    return common.ok(
        {
            "purposes": [
                {
                    "purpose": spec.purpose,
                    "tier": spec.tier,
                    "json_mode": spec.json_mode,
                    "max_tokens": spec.max_tokens,
                }
                for spec in providers.PURPOSE_SPECS.values()
            ]
        }
    )


@bp.get("/now")
def now():
    return common.ok({"now": datetime.now().astimezone().isoformat(timespec="seconds")})
