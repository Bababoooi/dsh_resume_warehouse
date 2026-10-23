"""Package ↔ JD 打分排序（纯本地、可解释、权重可配）。

契约（API-CONTRACT §8 / t8 任务书）要求四维打分，且**必须能解释**：

===============  =========================================================
维度             含义
===============  =========================================================
``skills``       技能覆盖：JD 需求条目（按 must/should/nice 加权）被 package
                 命中的比例——命中来自 ``tech_stack`` / ``tags`` / 标题 /
                 摘要 / 变体文本，且复用 ``skills.SKILL_ALIASES`` 归一
``outcomes``     成果相关度：有没有量化结果（``outcomes_json`` 或含数字/百分号
                 的要点），以及这些结果是否落在 JD 关键词上
``recency``      时效：结束时间越近越高；``至今`` 视为满分
``role``         角色层级：package.role 与目标岗位的语义词重合度 + 层级契合
===============  =========================================================

权重默认 ``{skills:0.45, outcomes:0.25, recency:0.15, role:0.15}``，可由
``POST /builds/{id}/assemble`` 的 ``weights`` 或 ``app_setting.match_weights``
覆盖；权重会被**归一化**后使用，返回体里回显实际使用的权重（可复现）。

本模块零网络、零 IO：输入是已经取出来的 dict，输出是 dict。
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from . import skills as skills_mod

DEFAULT_WEIGHTS: dict[str, float] = {
    "skills": 0.45,
    "outcomes": 0.25,
    "recency": 0.15,
    "role": 0.15,
}

PRIORITY_WEIGHT = {"must": 3.0, "should": 2.0, "nice": 1.0}

_NUMERIC_RE = re.compile(r"\d")
_DATE_RE = re.compile(r"(\d{4})\s*[.\-/年]\s*(\d{1,2})?")
_PRESENT_WORDS = ("至今", "present", "now", "current")

# 岗位层级词：命中即认为 package 与该层级接近（同组内得分 1.0，跨组 0.5）
LEVELS: tuple[tuple[str, ...], ...] = (
    ("实习生", "intern", "internship"),
    ("助理", "assistant", "associate", "专员"),
    ("工程师", "engineer", "分析师", "analyst", "专员"),
    ("高级", "senior", "资深", "主管", "supervisor", "lead", "负责人"),
    ("经理", "manager", "总监", "director", "head"),
)

_STOP_TOKENS = frozenset(
    {
        "and", "or", "the", "of", "in", "to", "for", "with", "a", "an",
        "与", "和", "及", "或", "的", "等", "优先", "熟悉", "掌握", "具备", "了解",
        "要求", "负责", "参与", "能够", "以上", "相关", "经验", "能力",
    }
)


def normalize_weights(weights: Mapping[str, Any] | None) -> dict[str, float]:
    """把外部权重归一化：缺项补默认、非法值丢弃、总和缩放到 1。"""
    merged = dict(DEFAULT_WEIGHTS)
    if weights:
        for key in DEFAULT_WEIGHTS:
            value = weights.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                merged[key] = float(value)
    total = sum(merged.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {key: round(value / total, 4) for key, value in merged.items()}


def _haystack(package: Mapping[str, Any], variants: Sequence[Mapping[str, Any]]) -> str:
    """package 的可检索文本（小写、空白折叠）。"""
    parts: list[str] = [
        str(package.get("title") or ""),
        str(package.get("org") or ""),
        str(package.get("role") or ""),
        str(package.get("summary") or ""),
    ]
    parts.extend(str(item) for item in package.get("tech_stack") or [])
    parts.extend(str(item) for item in package.get("tags") or [])
    for item in package.get("outcomes") or []:
        if isinstance(item, Mapping):
            parts.append(str(item.get("metric") or ""))
            parts.append(str(item.get("evidence") or ""))
        else:
            parts.append(str(item))
    for variant in variants:
        parts.append(str(variant.get("text") or ""))
    return skills_mod.normalize(" ".join(parts))


def _skill_hit(requirement: Mapping[str, Any], haystack: str, original: str) -> bool:
    """需求条目是否被 package 命中（token 归一优先，原词兜底）。"""
    skill = str(requirement.get("skill") or "").strip()
    if not skill:
        return False
    tokens = [token for token in skills_mod.derive_tokens(skill)]
    if tokens and any(token in haystack for token in tokens):
        return True
    # 兜底：原词（去空白/小写）出现在原文里即算命中
    needle = skills_mod.normalize(skill)
    return bool(needle) and needle in skills_mod.normalize(original)


def score_package(
    package: Mapping[str, Any],
    variants: Sequence[Mapping[str, Any]],
    requirements: Sequence[Mapping[str, Any]],
    *,
    target_role: str | None = None,
    weights: Mapping[str, float] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """给单个 package 打分，返回 ``{score, breakdown, hits, gaps, reason}``。"""
    active = weights or DEFAULT_WEIGHTS
    haystack = _haystack(package, variants)
    original = " ".join(
        [str(package.get("title") or ""), str(package.get("summary") or "")]
        + [str(item) for item in package.get("tech_stack") or []]
        + [str(variant.get("text") or "") for variant in variants]
    )

    # --- skills ---------------------------------------------------------
    total_weight = 0.0
    hit_weight = 0.0
    hits: list[str] = []
    gaps: list[str] = []
    for requirement in requirements:
        weight = PRIORITY_WEIGHT.get(str(requirement.get("priority") or "should"), 2.0)
        weight *= float(requirement.get("weight") or 1.0)
        total_weight += weight
        if _skill_hit(requirement, haystack, original):
            hit_weight += weight
            hits.append(str(requirement.get("skill") or ""))
        else:
            gaps.append(str(requirement.get("skill") or ""))
    skills_score = (hit_weight / total_weight) if total_weight else 0.0

    # --- outcomes -------------------------------------------------------
    outcomes = [item for item in package.get("outcomes") or []]
    quantified_texts = [
        str(variant.get("text") or "")
        for variant in variants
        if _NUMERIC_RE.search(str(variant.get("text") or ""))
    ]
    if outcomes or quantified_texts:
        base = min(1.0, (len(outcomes) + len(quantified_texts)) / 3.0)
        # 量化结果落在 JD 关键词上再加成（最多补到 1.0）
        bonus = 0.0
        if hits:
            joined = " ".join([str(item) for item in outcomes] + quantified_texts)
            normalized = skills_mod.normalize(joined)
            bonus = 0.25 if any(skills_mod.normalize(hit) in normalized for hit in hits) else 0.0
        outcomes_score = min(1.0, base + bonus)
    else:
        outcomes_score = 0.0

    # --- recency --------------------------------------------------------
    recency_score = _recency(package, today or date.today())

    # --- role -----------------------------------------------------------
    role_score, role_note = _role_fit(package, target_role)

    breakdown = {
        "skills": round(skills_score, 4),
        "outcomes": round(outcomes_score, 4),
        "recency": round(recency_score, 4),
        "role": round(role_score, 4),
    }
    score = round(sum(breakdown[key] * active[key] for key in active), 4)
    return {
        "package_id": package.get("id"),
        "score": score,
        "breakdown": breakdown,
        "weights": dict(active),
        "hits": _dedupe(hits),
        "gaps": _dedupe(gaps),
        "reason": _reason(breakdown, active, _dedupe(hits), role_note),
    }


def _recency(package: Mapping[str, Any], today: date) -> float:
    """结束时间越近越高；「至今」满分；解析不出给 0.5（不惩罚未知）。"""
    if package.get("is_current"):
        return 1.0
    for key in ("end_date", "start_date"):
        text = str(package.get(key) or "").strip()
        if not text:
            continue
        if any(word in text.lower() for word in _PRESENT_WORDS):
            return 1.0
        match = _DATE_RE.search(text)
        if not match:
            continue
        year = int(match.group(1))
        month = int(match.group(2) or 6)
        months = (today.year - year) * 12 + (today.month - month)
        if months <= 12:
            return 1.0
        if months <= 36:
            return 0.8
        if months <= 60:
            return 0.6
        if months <= 96:
            return 0.4
        return 0.2
    return 0.5


def _role_fit(package: Mapping[str, Any], target_role: str | None) -> tuple[float, str]:
    role = str(package.get("role") or "")
    if not target_role:
        return 0.5, "未指定目标岗位"
    if not role:
        return 0.4, "package 未填角色"
    target_tokens = _tokens(target_role)
    role_tokens = _tokens(role)
    overlap = target_tokens & role_tokens
    token_score = len(overlap) / max(1, len(target_tokens))
    level_score = _level_score(target_role, role)
    score = min(1.0, 0.6 * token_score + 0.4 * level_score)
    note = f"角色「{role}」与目标「{target_role}」"
    if overlap:
        note += "，共同词：" + "、".join(sorted(overlap)[:3])
    return score, note


def _tokens(text: str) -> set[str]:
    """中英混排粗切词：中文按二元组、英文按单词。"""
    normalized = skills_mod.normalize(text)
    tokens: set[str] = set()
    for word in re.findall(r"[a-z][a-z0-9+#.]*", normalized):
        if word not in _STOP_TOKENS:
            tokens.add(word)
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
    for index in range(len(cjk) - 1):
        tokens.add(cjk[index : index + 2])
    return tokens


def _level_of(text: str) -> int | None:
    lowered = text.lower()
    for index, words in enumerate(LEVELS):
        if any(word in lowered for word in words):
            return index
    return None


def _level_score(target: str, role: str) -> float:
    target_level = _level_of(target)
    role_level = _level_of(role)
    if target_level is None or role_level is None:
        return 0.5
    if target_level == role_level:
        return 1.0
    return 0.5 if abs(target_level - role_level) == 1 else 0.2


def _reason(
    breakdown: Mapping[str, float],
    weights: Mapping[str, float],
    hits: Sequence[str],
    role_note: str,
) -> str:
    parts = []
    if hits:
        parts.append("命中 " + "、".join(list(hits)[:3]))
    for key, label in (
        ("skills", "技能覆盖"),
        ("outcomes", "成果量化"),
        ("recency", "时效"),
        ("role", "角色契合"),
    ):
        contribution = breakdown[key] * weights[key]
        parts.append(f"{label} {breakdown[key]:.2f}×{weights[key]:.2f}={contribution:.2f}")
    parts.append(role_note)
    return "；".join(parts)


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def rank_packages(
    packages: Sequence[Mapping[str, Any]],
    variants_by_package: Mapping[str, Sequence[Mapping[str, Any]]],
    requirements: Sequence[Mapping[str, Any]],
    *,
    target_role: str | None = None,
    weights: Mapping[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """批量打分并按分数降序返回，附覆盖率与主要缺口。"""
    active = normalize_weights(weights)
    scores = [
        score_package(
            package,
            variants_by_package.get(str(package.get("id")), []),
            requirements,
            target_role=target_role,
            weights=active,
            today=today,
        )
        for package in packages
    ]
    scores.sort(key=lambda item: item["score"], reverse=True)
    hit_skills = {skill for item in scores for skill in item["hits"]}
    all_skills = _dedupe([str(req.get("skill") or "") for req in requirements])
    covered = [skill for skill in all_skills if skill in hit_skills]
    return {
        "scores": scores,
        "weights": active,
        "coverage": {
            "ratio": round(len(covered) / len(all_skills), 4) if all_skills else 0.0,
            "covered": covered,
            "uncovered": [skill for skill in all_skills if skill not in hit_skills],
        },
        "top_gaps": [skill for skill in all_skills if skill not in hit_skills][:8],
    }
