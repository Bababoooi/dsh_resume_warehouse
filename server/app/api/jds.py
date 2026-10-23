"""JD（岗位需求）分析：CRUD、异步分析（202）、人工修正需求、本地匹配打分。

三条契约要点：

* ``POST /jds/{id}/analyze`` 走 jobrun 返回 **202**；LLM 路径必须先有 consent preview
  （``method=llm``，或 ``method=auto`` 且 LLM 就绪），缺 preview → **428**
  ``LLM_CONSENT_REQUIRED``（ANL-02 / BLK-4）。
* LLM 不可用时 ``method=auto`` 自动降级为启发式，**仍然产出 competitiveness**
  （ANL-01：关掉 AI 不等于看不到竞争力评估）。
* ``POST /jds/{id}/match`` **纯本地**打分，不联网（ANL-03）。
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, request

from ..errors import ApiError
from ..models import JdAnalyzeIn, JdIn, JdMatchIn, RequirementPatch, parse_body
from ..repos import CompanyRepo, JdRepo, PackageRepo, PreviewRepo, ProfileRepo
from ..services import company_analysis, jd_analysis, jobrun
from . import common

bp = Blueprint("jds", __name__)


def _view(jd: dict[str, Any]) -> dict[str, Any]:
    view = {
        "id": jd["id"],
        "title": jd.get("title"),
        "company_name": jd.get("company_name"),
        "raw_text": jd.get("raw_text"),
        "source_url": jd.get("source_url"),
        "lang": jd.get("lang"),
        "analysis_status": jd.get("analysis_status"),
        "analysis_method": jd.get("analysis_method"),
        "competitiveness": jd.get("competitiveness") or {},
        "created_at": jd.get("created_at"),
        "updated_at": jd.get("updated_at"),
    }
    if "requirements" in jd:
        view["requirements"] = [_requirement_view(item) for item in jd["requirements"]]
    return view


def _requirement_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "skill": row["skill"],
        "category": row["category"],
        "priority": row["priority"],
        "weight": row.get("weight"),
        "evidence_hint": row.get("evidence_hint"),
        "raw_quote": row.get("raw_quote"),
        "source": row.get("source"),
        "candidate_status": row.get("candidate_status"),
        "candidate_status_source": row.get("candidate_status_source"),
        "matched_package_ids": row.get("matched_package_ids") or [],
        "matched_evidence": row.get("matched_evidence") or [],
    }


def _require_jd(jd_id: str) -> dict[str, Any]:
    return JdRepo().get(jd_id, with_requirements=True)


@bp.get("/jds")
def list_jds():
    limit_value = common.limit(50)
    offset_value = common.offset()
    items = JdRepo().list(limit=limit_value + 1)
    has_more = len(items) > limit_value
    items = items[:limit_value]
    total = len(JdRepo().list(limit=1000))
    return common.ok(
        common.list_envelope(
            [_view({**item, "competitiveness": {}}) for item in items],
            total,
            limit_value=limit_value,
            offset_value=offset_value,
        )
    )


@bp.post("/jds")
def create_jd():
    payload = parse_body(JdIn, common.raw_body())
    jd_id = JdRepo().create(payload.model_dump())
    location = f"/api/v1/jds/{jd_id}"
    return common.created(_view(_require_jd(jd_id)), location)


@bp.get("/jds/<jd_id>")
def get_jd(jd_id: str):
    return common.ok(_view(_require_jd(jd_id)))


@bp.patch("/jds/<jd_id>")
def patch_jd(jd_id: str):
    repo = JdRepo()
    repo.get(jd_id, with_requirements=False)
    body = common.raw_body()
    allowed = {"title", "company_name", "source_url", "lang"}
    patch = {key: value for key, value in body.items() if key in allowed}
    if not patch:
        raise ApiError(
            "BAD_REQUEST",
            "没有可更新的字段",
            details={"allowed": sorted(allowed)},
        )
    from .. import db as db_mod

    with db_mod.transaction() as conn:
        assignments = ", ".join(f"{key} = ?" for key in patch)
        conn.execute(
            f"UPDATE job_description SET {assignments}, updated_at = ? WHERE id = ?",
            [*patch.values(), db_mod.utcnow_iso(), jd_id],
        )
    return common.ok(_view(_require_jd(jd_id)))


@bp.delete("/jds/<jd_id>")
def delete_jd(jd_id: str):
    from .. import db as db_mod

    JdRepo().get(jd_id, with_requirements=False)
    with db_mod.transaction() as conn:
        conn.execute("DELETE FROM job_description WHERE id = ?", (jd_id,))
    return common.no_content()


@bp.get("/jds/<jd_id>/requirements")
def list_requirements(jd_id: str):
    jd = _require_jd(jd_id)
    return common.ok(
        {"items": [_requirement_view(item) for item in jd["requirements"]], "jd_id": jd_id}
    )


def _llm_ready() -> bool:
    from .. import config as config_mod
    from ..adapters import providers

    cfg = config_mod.get_config()
    try:
        providers.resolve_route("jd_analyze", cfg)
    except Exception:
        return False
    return bool(cfg.ready)


def _require_preview(preview_id: str | None, *, purpose: str) -> dict[str, Any]:
    if not preview_id:
        raise ApiError(
            "LLM_CONSENT_REQUIRED",
            "调用模型前必须先预览「将发送字段清单」并确认",
            details={"purpose": purpose, "next_step": "POST /api/v1/llm/preview"},
            hint="先把这一步要通过网络的字段列出来给你确认，确认后再分析",
        )
    preview = PreviewRepo().get(preview_id)
    if preview.get("purpose") != purpose:
        raise ApiError(
            "LLM_CONSENT_MISMATCH",
            "该预览不是用于本操作的，请重新预览",
            details={"expected_purpose": purpose, "actual_purpose": preview.get("purpose")},
        )
    return preview


def _flag_unready_matches(
    requirements: list[dict[str, Any]],
    model_ids: dict[str, list[str]],
    all_packages: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    """AC-ANL-15 ②：模型点名的包若不是 ready，剔除并如实告知，而不是悄悄丢掉。

    ``matched_package_ids`` 一律由本地重算（AC-ANL-15 ①）；这里只解释「模型说的为什么没算数」，
    用户才不会以为自己的 draft 包坏掉了。
    """
    status_by_id = {str(item.get("id")): str(item.get("status") or "") for item in all_packages}
    for req in requirements:
        if not isinstance(req, dict):
            continue
        ids = model_ids.get(str(req.get("skill") or "")) or []
        not_ready = [pid for pid in ids if status_by_id.get(pid) != "ready"]
        local = [pid for pid in (req.get("matched_package_ids") or []) if status_by_id.get(pid) == "ready"]
        req["matched_package_ids"] = local
        if not_ready:
            warnings.append(
                {
                    "code": "MATCHED_PACKAGE_NOT_READY",
                    "severity": "warn",
                    "message": f"「{req.get('skill')}」指向的经历包尚未核实（非 ready），未计入匹配",
                    "details": {
                        "requirement": str(req.get("skill") or ""),
                        "package_ids": not_ready,
                        "statuses": [status_by_id.get(pid, "missing") for pid in not_ready],
                    },
                }
            )


@bp.post("/jds/<jd_id>/analyze")
def analyze_jd(jd_id: str):
    jd = _require_jd(jd_id)
    payload = parse_body(JdAnalyzeIn, common.raw_body() or {})

    use_llm = payload.method == "llm" or (payload.method == "auto" and _llm_ready())
    preview: dict[str, Any] | None = None
    if use_llm:
        preview = _require_preview(payload.preview_id, purpose="jd_analyze")
    elif payload.method == "auto":
        # LLM 未就绪：不报错、不阻塞，直接降级（ANL-01）
        use_llm = False

    profile = ProfileRepo()
    brief = profile.llm_brief()
    raw_profile = profile.get()
    sha = payload.expected_payload_sha256 or (preview or {}).get("payload_sha256")
    jd_repo = JdRepo()
    jd_repo.update_status(jd_id, "analyzing", "llm" if use_llm else "heuristic")

    def work(report) -> dict[str, Any]:
        warnings: list[dict[str, Any]] = []
        report(20, "读取 JD 文本")
        text = jd_analysis.strip_notes(jd["raw_text"])

        school_pref: dict[str, Any] = company_analysis.school_preference_from(jd_text=text)
        all_packages = PackageRepo().list(limit=50).get("items", [])
        # 只有 ready 的包能当「证据」：draft 还没核实，archived/软删的更不该出现在 JD 结论里。
        packages = [item for item in all_packages if str(item.get("status") or "") == "ready"]
        if use_llm:
            from ..services.consent import ConsentService

            report(45, "等待模型返回结构化需求")
            result = ConsentService().complete(payload.preview_id, sha)
            parsed = result.get("parsed") or {}
            warnings.extend(result.get("warnings") or [])
            requirements = jd_analysis.normalize_requirements(
                (parsed or {}).get("requirements"), profile=raw_profile, packages=packages
            )
            competitiveness = jd_analysis.normalize_competitiveness(
                (parsed or {}).get("competitiveness"),
                profile=raw_profile,
                school_preference=school_pref,
                requirements=requirements,
                warnings=warnings,
            )
            method = "llm"
        else:
            report(45, "本地启发式拆解 JD")
            requirements = jd_analysis.heuristic_requirements(
                text, profile=raw_profile, packages=packages
            )
            # 离线路径同样要挂证据：启发式只按关键词判「有没有这条要求」，
            # 但「凭什么说用户满足」必须能点回原文（I21）——否则本地模式就是黑盒。
            jd_analysis.link_requirements(requirements, packages, profile=raw_profile, warnings=warnings)
            competitiveness = jd_analysis.competitiveness(
                profile=raw_profile,
                school_preference=school_pref,
                requirements=requirements,
                warnings=warnings,
            )
            method = "heuristic"
            # 降级必须说出来：用户要知道「这份竞争力评估是本地规则算的，不是模型判的」
            warnings.append(
                {
                    "code": "COMPETITIVENESS_FALLBACK",
                    "severity": "info",
                    "message": "未调用模型，竞争力评估由本地规则生成（院校门槛/学历/专业/经历四维同样计入）",
                    "details": {
                        "method": "heuristic",
                        "reason": "LLM_UNAVAILABLE"
                        if payload.method == "auto"
                        else "METHOD_HEURISTIC",
                        "school_filter_source": school_pref.get("confidence")
                        and "jd_text"
                        or "none",
                    },
                }
            )

        report(75, "写入需求表")
        # 本地把 requirement 与仓库经历对上：模型看不到仓库时会说「档案未体现 A/B 测试」，
        # 而用户仓库里就有这么一个项目。命中即填 matched_package_ids，并否决「明明有却说没有」。
        # 模型自述的 id 一律不采信（它看不到仓库）；先记下来，只用于提示「你指的包还没核实」。
        model_ids: dict[str, list[str]] = {
            str(req.get("skill") or ""): [str(item) for item in (req.get("matched_package_ids") or [])]
            for req in requirements
            if isinstance(req, dict)
        }
        jd_analysis.link_requirements(requirements, packages, profile=raw_profile, warnings=warnings)
        _flag_unready_matches(requirements, model_ids, all_packages, warnings)
        count = jd_repo.replace_requirements(jd_id, requirements, method=method)
        jd_repo.set_competitiveness(jd_id, competitiveness)

        # 公司名在 JD 里有 → 顺手把院校偏好挂到公司档案（不覆盖人工值）
        if jd.get("company_name"):
            try:
                company_repo = CompanyRepo()
                existing = company_repo.find_by_name(jd["company_name"])
                if existing is None:
                    company_repo.upsert(
                        jd["company_name"],
                        {
                            "school_preference": school_pref,
                            "sources": [{"kind": "jd", "jd_id": jd_id}],
                            "confidence": school_pref.get("confidence"),
                        },
                        method=method,
                    )
            except Exception:  # 画像写入失败不该让分析整体失败
                warnings.append(
                    {
                        "code": "COMPANY_PROFILE_SKIPPED",
                        "severity": "info",
                        "message": "公司档案未写入（不影响本次分析结果）",
                        "details": {"company_name": jd.get("company_name")},
                    }
                )

        report(95, "整理结果")
        return {
            "jd_id": jd_id,
            "method": method,
            "requirements_count": count,
            "requirements": requirements,
            "competitiveness": competitiveness,
            "school_preference": school_pref,
            "warnings": warnings,
            "model": None,
        }

    job_id = jobrun.submit("jd_analyze", work, message="分析岗位需求")
    return common.accepted(
        {
            "job_id": job_id,
            "jd_id": jd_id,
            "method": "llm" if use_llm else "heuristic",
        }
    )


@bp.patch("/requirements/<requirement_id>")
def patch_requirement(requirement_id: str):
    payload = parse_body(RequirementPatch, common.raw_body())
    patch = payload.model_dump(exclude_unset=True)
    if not patch:
        raise ApiError("BAD_REQUEST", "没有可更新的字段")
    row = JdRepo().update_requirement(requirement_id, patch)
    return common.ok(_requirement_view(row))


@bp.delete("/requirements/<requirement_id>")
def delete_requirement(requirement_id: str):
    jd_id = JdRepo().delete_requirement(requirement_id)
    return common.ok({"deleted": requirement_id, "jd_id": jd_id})


@bp.post("/jds/<jd_id>/match")
def match(jd_id: str):
    payload = parse_body(JdMatchIn, common.raw_body() or {})
    jd = _require_jd(jd_id)
    requirements = jd.get("requirements") or []
    if not requirements:
        raise ApiError(
            "CONFLICT",
            "该 JD 还没有解析出需求条目，请先分析",
            details={"jd_id": jd_id, "analysis_status": jd.get("analysis_status")},
            hint="先调用 POST /api/v1/jds/{id}/analyze",
        )
    repo = PackageRepo()
    if payload.package_ids:
        packages = [repo.get(pkg_id) for pkg_id in payload.package_ids]
    else:
        packages = repo.list(limit=200).get("items", [])
    result = jd_analysis.match_packages(requirements, packages)
    return common.ok(
        {
            "jd_id": jd_id,
            "scores": result["scores"],
            "coverage": result["coverage"],
            "top_gaps": result["top_gaps"],
            "requirements_used": len(requirements),
        }
    )
