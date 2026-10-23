"""公司招聘偏好：画像 CRUD、异步分析（202 + 30 天缓存）、下行抓取唯一入口。

关键契约（docs/API-CONTRACT §7）：

* ``POST /company-profiles/analyze``：``refresh=false`` 且缓存未过期 → **200 + cache_hit=true**，
  不调 LLM、不联网；否则 202 job。
* 抓取只在「用户给了 url」或「画像已有 website」时发生，且受 ``allow_web_fetch`` 开关约束，
  抓不到就降级为只用 JD 文本（**绝不因抓取失败让分析失败**）。
* ``POST /fetch/public-page`` 是**下行唯一入口**：只 GET 公开页、零用户字段。
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, request

from ..errors import ApiError
from ..models import CompanyAnalyzeIn, CompanyIn, CompanyPatch, FetchIn, parse_body
from ..repos import CompanyRepo, JdRepo
from ..services import company_analysis, jobrun
from . import common

bp = Blueprint("company_profiles", __name__)


def _view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "company_name": row.get("company_name"),
        "industry": row.get("industry"),
        "company_stage": row.get("company_stage"),
        "size_hint": row.get("size_hint"),
        "culture_signals": row.get("culture_signals") or [],
        "hiring_preferences": row.get("hiring_preferences") or [],
        "interview_focus": row.get("interview_focus") or [],
        "tone": row.get("tone"),
        "keywords": row.get("keywords") or [],
        "sources": row.get("sources") or [],
        "school_preference": row.get("school_preference") or {},
        "confidence": row.get("confidence"),
        "method": row.get("method"),
        "website": row.get("website"),
        "last_analyzed_at": row.get("last_analyzed_at"),
        "expires_at": row.get("expires_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


@bp.get("/company-profiles")
def list_companies():
    limit_value = common.limit(50)
    offset_value = common.offset()
    repo = CompanyRepo()
    items = repo.list(limit=limit_value, offset=offset_value)
    return common.ok(
        common.list_envelope(
            [_view(item) for item in items],
            repo.count(),
            limit_value=limit_value,
            offset_value=offset_value,
        )
    )


@bp.post("/company-profiles")
def create_company():
    payload = parse_body(CompanyIn, common.raw_body())
    repo = CompanyRepo()
    existing = repo.find_by_name(payload.company_name)
    if existing is not None:
        raise ApiError(
            "CONFLICT",
            "该公司档案已存在",
            details={"company_name": payload.company_name, "id": existing["id"]},
            hint=f"PATCH /api/v1/company-profiles/{existing['id']}",
        )
    row = repo.upsert(payload.company_name, payload.model_dump(), method="manual")
    return common.created(_view(row), f"/api/v1/company-profiles/{row['id']}")


@bp.get("/company-profiles/<company_id>")
def get_company(company_id: str):
    return common.ok(_view(CompanyRepo().get(company_id)))


@bp.patch("/company-profiles/<company_id>")
def patch_company(company_id: str):
    payload = parse_body(CompanyPatch, common.raw_body())
    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        raise ApiError("BAD_REQUEST", "没有可更新的字段")
    patch.setdefault("method", "manual")
    return common.ok(_view(CompanyRepo().patch(company_id, patch)))


@bp.delete("/company-profiles/<company_id>")
def delete_company(company_id: str):
    CompanyRepo().delete(company_id)
    return common.no_content()


@bp.post("/fetch/public-page")
def fetch_public_page():
    payload = parse_body(FetchIn, common.raw_body())
    from ..adapters import fetch_client

    result = fetch_client.fetch_public_page(payload.url, use_cache=payload.use_cache)
    return common.ok(result.as_dict())


def _fetch_texts(payload: CompanyAnalyzeIn, existing: dict[str, Any] | None) -> tuple[list[str], list[dict[str, Any]]]:
    """抓取公开页：没给 URL 且档案没有 website 时**不抓**（契约 §7）。"""
    from ..adapters import fetch_client

    warnings: list[dict[str, Any]] = []
    target = payload.fetch_url or (existing or {}).get("website")
    if not payload.allow_fetch:
        if target:
            warnings.append(
                {
                    "code": "FETCH_DISABLED",
                    "severity": "info",
                    "message": "本次选择了不联网，只用你粘贴的 JD 文本分析",
                    "details": {"url": target},
                }
            )
        return [], warnings
    if not target:
        return [], warnings
    try:
        result = fetch_client.fetch_public_page(target)
    except ApiError as exc:
        warnings.append(
            {
                "code": "FETCH_FAILED",
                "severity": "warn",
                "message": f"抓取公司页面失败（{exc.code}），已降级为只用 JD 文本分析",
                "details": {"url": target, "reason": (exc.details or {}).get("reason")},
            }
        )
        return [], warnings
    warnings.extend(result.warnings)
    return [result.text], warnings


@bp.post("/company-profiles/analyze")
def analyze_company():
    payload = parse_body(CompanyAnalyzeIn, common.raw_body())
    repo = CompanyRepo()
    existing = repo.find_by_name(payload.company_name)

    jd_text = payload.jd_text or ""
    if payload.jd_id:
        jd_row = JdRepo().get(payload.jd_id, with_requirements=False)
        jd_text = jd_text or jd_row.get("raw_text") or ""
    if not jd_text and not payload.fetch_url and not (existing or {}).get("website"):
        raise ApiError(
            "VALIDATION_ERROR",
            "至少需要 JD 文本或公司页面 URL 之一",
            details={
                "fields": [
                    {"field": "jd_text", "rule": "required_without_url", "message": "请粘贴 JD 或提供公司页面 URL"}
                ]
            },
        )

    if not payload.refresh and company_analysis.is_fresh(existing):
        return common.ok({"cache_hit": True, "profile": _view(existing), "hint": "30 天内的分析结果，未重复调用模型"})

    use_llm = payload.method == "llm" or (payload.method == "auto" and _llm_ready())
    preview: dict[str, Any] | None = None
    if use_llm and payload.preview_id:
        from ..repos import PreviewRepo

        preview = PreviewRepo().get(payload.preview_id)
        if preview.get("purpose") != "company_profile":
            raise ApiError(
                "LLM_CONSENT_MISMATCH",
                "该预览不是用于公司画像分析的，请重新预览",
                details={"expected_purpose": "company_profile", "actual_purpose": preview.get("purpose")},
            )
    elif use_llm:
        # 没有 preview 就不发数据，直接降级到本地规则（不报 428：用户没要求必须用 AI）
        use_llm = False

    sha = payload.expected_payload_sha256 or (preview or {}).get("payload_sha256")

    def work(report) -> dict[str, Any]:
        report(20, "读取 JD 与公司信息")
        fetched, warnings = _fetch_texts(payload, existing)
        fallback = company_analysis.heuristic_profile(
            company_name=payload.company_name,
            jd_text=jd_text,
            fetched_texts=fetched,
            sources=[{"kind": "jd", "chars": len(jd_text)}]
            + ([{"kind": "web", "chars": len(fetched[0])}] if fetched else []),
        )
        if use_llm:
            from ..services.consent import ConsentService

            report(55, "等待模型返回公司画像")
            result = ConsentService().complete(payload.preview_id, sha)
            warnings.extend(result.get("warnings") or [])
            profile = company_analysis.normalize_profile(
                (result.get("parsed") or {}).get("company"),
                company_name=payload.company_name,
                fallback=fallback,
                warnings=warnings,
            )
        else:
            report(55, "本地规则生成公司画像")
            profile = dict(fallback)
            for item in profile.pop("missing_required", []) or []:
                warnings.append(
                    {
                        "code": "PROFILE_FIELD_MISSING",
                        "severity": "warn",
                        "message": "画像缺少一项必答内容，已标注为「未提及」",
                        "details": {"missing": item},
                    }
                )
            # 降级必须说出来：院校偏好是本地规则从 JD/页面里读的，不是模型推理的
            warnings.append(
                {
                    "code": "SCHOOL_FILTER_FALLBACK",
                    "severity": "info",
                    "message": "未调用模型，院校偏好由本地规则从 JD 原文提取（未见院校表述时按「不限」处理，不编造门槛）",
                    "details": {
                        "method": "heuristic",
                        "reason": "LLM_UNAVAILABLE" if payload.method == "auto" else "METHOD_HEURISTIC",
                        "jd_chars": len(jd_text),
                        "fetched_chars": sum(len(t) for t in fetched),
                    },
                }
            )

        report(80, "写入公司档案")
        profile["expires_at"] = company_analysis.expiry_iso()
        profile["website"] = payload.fetch_url or (existing or {}).get("website")
        row = repo.upsert(payload.company_name, profile, method=profile.get("method") or "heuristic")
        report(95, "整理结果")
        return {"profile": row, "warnings": warnings, "fetched_chars": sum(len(t) for t in fetched)}

    job_id = jobrun.submit("company_analyze", work, message="分析公司招聘偏好")
    return common.accepted(
        {"job_id": job_id, "company_name": payload.company_name, "method": "llm" if use_llm else "heuristic"}
    )


def _llm_ready() -> bool:
    from .. import config as config_mod
    from ..adapters import providers

    cfg = config_mod.get_config()
    try:
        providers.resolve_route("company_profile", cfg)
    except Exception:
        return False
    return bool(cfg.ready)
