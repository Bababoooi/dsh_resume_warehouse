"""公司招聘偏好分析：从 JD + 公司名 +（可选）官网/招聘页正文推导画像。

三条硬约束（docs/API-CONTRACT §7 + REVIEW-CHECKLIST ANL-05/ANL-08）：

1. **不编造院校门槛**：JD 与抓取文本都没提院校时，必须 ``threshold="不限"``、
   ``hard_filter=false``、``preferred_tiers=[]``，并在 evidence 里写清依据。
2. **四个必答项**：院校偏好 / 学历届别 / 硬技能门槛 / 风格偏好，缺任一项扣 confidence
   并发 ``PROFILE_FIELD_MISSING`` —— 少了「院校偏好」这条，画像对用户的价值就缺一角。
3. **零用户字段外带**：抓取只 GET 公开页（见 ``fetch_client``），这里组装的 payload
   只含公司名/JD/抓取正文，不带任何用户资料（用户资料由 consent 层按 purpose 决定）。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from . import jd_analysis
from .. import db as db_mod

#: 画像四必答项（缺一项即扣 confidence + warning）
REQUIRED_PREFERENCES: tuple[tuple[str, str], ...] = (
    ("school", "院校偏好（是否卡 985/211/双一流、是否偏好本地院校、是否看重第一学历）"),
    ("education", "学历与届别（最低学历、是否限届、是否接受在读）"),
    ("skills", "硬技能门槛（必须会什么工具/方法，有没有替代路径）"),
    ("style", "风格偏好（偏执行还是偏研究、汇报对象、节奏）"),
)

_STYLE_HINTS: tuple[tuple[str, str], ...] = (
    (r"(扁平|直接沟通|简单|不搞形式|务实)", "沟通直接、反感形式主义"),
    (r"(快节奏|高强度|抗压|节奏快|加班)", "节奏快、需要抗压"),
    (r"(数据驱动|用数据说话|指标体系)", "重视数据驱动决策"),
    (r"(结果导向|交付|落地|闭环)", "结果导向、看重落地"),
    (r"(成长|学习|培养|导师|带教)", "强调成长与带教"),
    (r"(研究|洞察|探索|创新)", "鼓励研究与探索"),
)

_STAGE_HINTS: tuple[tuple[str, str], ...] = (
    (r"(上市公司|已上市|A股|港股|美股)", "上市公司"),
    (r"(独角兽|C轮|D轮|E轮)", "成长期公司"),
    (r"(A轮|B轮|天使|种子)", "早期公司"),
    (r"(国企|央企|事业单位|集团)", "集团/国企"),
    (r"(初创|创业)", "初创团队"),
)

_SIZE_HINTS: tuple[tuple[str, str], ...] = (
    (r"(\d{3,5})\s*人以上", "千人以上"),
    (r"(\d{2,3})\s*[-~至]\s*(\d{2,4})\s*人", "数百人规模"),
    (r"(50|100)\s*人(以下|以内)", "小团队"),
)

_SCHOOL_LOCAL_RE = re.compile(r"(本地|本市|省内|属地)(院校|高校|大学)")


def _find(text: str, patterns: Iterable[tuple[str, str]]) -> list[str]:
    found: list[str] = []
    for pattern, label in patterns:
        if re.search(pattern, text) and label not in found:
            found.append(label)
    return found


def school_preference_from(
    *,
    jd_text: str,
    fetched_texts: Sequence[str] = (),
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """院校偏好：先看 JD，再看抓取正文；都没有就是「不限」并说明依据。"""
    texts = [jd_analysis.strip_notes(jd_text), *(jd_analysis.strip_notes(t) for t in fetched_texts)]
    gate = jd_analysis.detect_school_gate(texts)
    preference = dict(gate)
    preference.setdefault("confidence", 0.6)
    joined = "\n".join(str(t or "") for t in texts)
    if _SCHOOL_LOCAL_RE.search(joined):
        preference["local_preference"] = True
        preference["evidence"] = (preference.get("evidence") or "") + "；另提到偏好本地院校"
    if existing:
        # 用户手填过的字段优先（人工 > 机器）
        for key in ("threshold", "preferred_tiers", "hard_filter"):
            if existing.get(key) not in (None, "", []):
                preference[f"detected_{key}"] = preference.get(key)
                preference[key] = existing[key]
        if existing.get("evidence"):
            preference["user_evidence"] = existing["evidence"]
    return preference


def hiring_preferences_from(*, jd_text: str, fetched_texts: Sequence[str] = ()) -> list[str]:
    """四必答项逐条落成一句人话（缺的项由调用方补 ``PROFILE_FIELD_MISSING``）。"""
    joined = "\n".join([jd_analysis.strip_notes(jd_text), *(jd_analysis.strip_notes(t) for t in fetched_texts)])
    gate = jd_analysis.detect_school_gate([joined])
    if gate["hard_filter"]:
        school_line = f"院校：{gate['threshold']} 为硬门槛（{gate['evidence']}）"
    elif gate.get("preferred_tiers"):
        school_line = f"院校：不设硬门槛，但 {'/'.join(gate['preferred_tiers'])} 更受偏好（{gate['evidence']}）"
    else:
        school_line = f"院校：未设门槛（{gate['evidence']}）"

    degree = jd_analysis.DEGREE_RE.search(joined)
    if degree:
        edu_line = f"学历：{degree.group(0)}"
        cohort = re.search(r"(20\d{2})\s*届", joined)
        if cohort:
            edu_line += f"，限 {cohort.group(1)} 届"
        if "在读" in joined or "实习" in joined:
            edu_line += "，接受在读"
    else:
        edu_line = "学历：JD 未明确最低学历"

    must_skills: list[str] = []
    for line in joined.splitlines():
        if not re.search(r"(熟练|精通|掌握|会写|能用|会用)", line):
            continue
        clause = re.split(r"[；;。]", line.strip().lstrip("0123456789.、 ）)"))[0]
        clause = clause.strip()[:48]
        if clause and clause not in must_skills:
            must_skills.append(clause)
        if len(must_skills) >= 3:
            break
    skills_line = (
        "硬技能：" + "；".join(must_skills)
        if must_skills
        else "硬技能：JD 未列具体工具门槛"
    )

    styles = _find(joined, _STYLE_HINTS)
    style_line = f"风格：{'、'.join(styles)}" if styles else "风格：JD 未体现团队风格"

    return [school_line, edu_line, skills_line, style_line]


def heuristic_profile(
    *,
    company_name: str,
    jd_text: str,
    fetched_texts: Sequence[str] = (),
    sources: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """纯本地画像（零出网）：LLM 不可用时的降级路径，字段结构与 LLM 路径一致。"""
    joined = "\n".join([jd_analysis.strip_notes(jd_text), *(jd_analysis.strip_notes(t) for t in fetched_texts)])
    preferences = hiring_preferences_from(jd_text=jd_text, fetched_texts=fetched_texts)
    school_pref = school_preference_from(jd_text=jd_text, fetched_texts=fetched_texts)
    missing: list[str] = []

    lines = {line.split("：", 1)[0].strip(): line for line in preferences}
    checks = {
        "school": bool(school_pref.get("evidence")),
        "education": "未明确最低学历" not in lines.get("学历", ""),
        "skills": "未列具体工具门槛" not in lines.get("硬技能", ""),
        "style": "未体现团队风格" not in lines.get("风格", ""),
    }
    for key, label in REQUIRED_PREFERENCES:
        if not checks.get(key):
            missing.append(label)

    confidence = round(max(0.25, 0.85 - 0.15 * len(missing)), 2)
    keywords = jd_analysis.keyword_list(joined, limit=10)
    return {
        "company_name": company_name,
        "industry": _industry_of(joined, company_name),
        "company_stage": next(iter(_find(joined, _STAGE_HINTS)), None),
        "size_hint": next(iter(_find(joined, _SIZE_HINTS)), None),
        "culture_signals": _find(joined, _STYLE_HINTS),
        "hiring_preferences": preferences,
        "interview_focus": _interview_focus(joined, keywords),
        "tone": _tone_of(joined),
        "keywords": keywords,
        "sources": list(sources),
        "school_preference": school_pref,
        "confidence": confidence,
        "method": "heuristic",
        "missing_required": missing,
    }


def _industry_of(text: str, company_name: str) -> str | None:
    mapping = (
        (r"电商|零售|天猫|京东|抖音商城", "电商零售"),
        (r"金融|银行|证券|保险|基金", "金融"),
        (r"游戏", "游戏"),
        (r"人工智能|大模型|算法|AI", "人工智能"),
        (r"教育|培训", "教育"),
        (r"医疗|医药|健康", "医疗健康"),
        (r"制造|工业|供应链|物流", "制造与供应链"),
        (r"咨询|会计|审计", "专业服务"),
        (r"数据|分析|BI", "数据服务"),
    )
    for pattern, label in mapping:
        if re.search(pattern, text) or re.search(pattern, company_name):
            return label
    return None


def _interview_focus(text: str, keywords: Sequence[str]) -> list[str]:
    focus: list[str] = []
    if re.search(r"(项目|案例|经历)", text):
        focus.append("会追问具体项目：目标、你的角色、怎么验证结论")
    if re.search(r"(Excel|SQL|python|Python|建模|统计)", text):
        focus.append("可能现场考工具题（SQL 手写 / Excel 透视 / Python 处理）")
    if re.search(r"(沟通|协作|对接|汇报)", text):
        focus.append("会看跨部门沟通与汇报表达")
    if re.search(r"(指标|KPI|复盘|归因)", text):
        focus.append("会问指标体系与归因思路")
    if not focus and keywords:
        focus.append(f"围绕核心业务词准备：{'、'.join(list(keywords)[:4])}")
    return focus[:4]


def _tone_of(text: str) -> str | None:
    if re.search(r"(务实|踏实|直接|不搞形式)", text):
        return "务实直接"
    if re.search(r"(活泼|年轻|有梗|轻松)", text):
        return "轻松活泼"
    if re.search(r"(严谨|规范|合规|专业)", text):
        return "严谨规范"
    return None


def normalize_profile(
    raw: Any,
    *,
    company_name: str,
    fallback: Mapping[str, Any],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    """把 LLM 输出归一：缺字段用本地兜底补，枚举/结构错就整体退启发式。"""
    if not isinstance(raw, Mapping):
        warnings.append(
            {
                "code": "COMPANY_PROFILE_FALLBACK",
                "severity": "warn",
                "message": "模型未返回可解析的公司画像，已改用本地规则",
                "details": {},
            }
        )
        return dict(fallback)

    def _as_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [part.strip() for part in re.split(r"[；;\n]", value) if part.strip()]
        return []

    school_raw = raw.get("school_preference")
    if isinstance(school_raw, Mapping):
        gate = jd_analysis.detect_school_gate([""])  # 只用结构兜底，不引入新的文本判断
        preference = {
            "threshold": str(school_raw.get("threshold") or fallback["school_preference"]["threshold"])[:40],
            "preferred_tiers": [
                tier for tier in _as_list(school_raw.get("preferred_tiers"))
                if tier in jd_analysis.TIER_ORDER
            ],
            "hard_filter": bool(school_raw.get("hard_filter")),
            "evidence": str(school_raw.get("evidence") or fallback["school_preference"]["evidence"])[:240],
            "confidence": _confidence(school_raw.get("confidence"), fallback["school_preference"].get("confidence", 0.6)),
        }
        # 反编造护栏：模型说「硬卡但门槛是『不限』」或「硬卡却给不出层次」→ 降级为不限
        if preference["hard_filter"] and (
            not preference["preferred_tiers"] or preference["threshold"] in ("", "不限", None) or gate["threshold"] == "不限"
        ):
            preference["hard_filter"] = False
            preference["preferred_tiers"] = []
            if not preference["threshold"] or preference["threshold"] == "不限":
                preference["threshold"] = "不限"
            warnings.append(
                {
                    "code": "SCHOOL_FILTER_FALLBACK",
                    "severity": "warn",
                    "message": "模型声称有院校硬门槛但未给出层次，已按「不限」处理（防编造）",
                    "details": {"raw": str(school_raw)[:160]},
                }
            )
    else:
        preference = dict(fallback["school_preference"])

    preferences = _as_list(raw.get("hiring_preferences")) or list(fallback["hiring_preferences"])
    missing: list[str] = []
    joined = "\n".join(preferences)
    checks = {
        "school": bool(preference.get("evidence")) or "院校" in joined,
        "education": bool(re.search(r"(学历|届|本科|硕士|博士)", joined)),
        "skills": bool(re.search(r"(技能|工具|Excel|SQL|Python|熟练|掌握)", joined)),
        "style": bool(re.search(r"(风格|节奏|沟通|团队|文化)", joined)),
    }
    for key, label in REQUIRED_PREFERENCES:
        if not checks.get(key):
            missing.append(label)
            preferences.append(f"{label}：JD 与公开页面均未提及")

    confidence = _confidence(raw.get("confidence"), fallback["confidence"])
    if missing:
        confidence = round(max(0.3, confidence - 0.1 * len(missing)), 2)
        warnings.append(
            {
                "code": "PROFILE_FIELD_MISSING",
                "severity": "warn",
                "message": f"画像缺少 {len(missing)} 项必答内容，已标注为「未提及」",
                "details": {"missing": missing},
            }
        )
    return {
        "company_name": company_name,
        "industry": str(raw.get("industry") or fallback.get("industry") or "")[:40] or None,
        "company_stage": str(raw.get("company_stage") or fallback.get("company_stage") or "")[:40] or None,
        "size_hint": str(raw.get("size_hint") or fallback.get("size_hint") or "")[:40] or None,
        "culture_signals": _as_list(raw.get("culture_signals")) or list(fallback["culture_signals"]),
        "hiring_preferences": preferences[:8],
        "interview_focus": _as_list(raw.get("interview_focus")) or list(fallback["interview_focus"]),
        "tone": str(raw.get("tone") or fallback.get("tone") or "")[:20] or None,
        "keywords": _as_list(raw.get("keywords")) or list(fallback["keywords"]),
        "sources": list(fallback.get("sources") or []),
        "school_preference": preference,
        "confidence": confidence,
        "method": "llm",
        "missing_required": missing,
    }


def _confidence(value: Any, default: float | None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default if default is not None else 0.6)
    return round(min(1.0, max(0.0, number)), 2)


# --------------------------------------------------------------------------------------
# 缓存（30 天）
# --------------------------------------------------------------------------------------

CACHE_TTL_DAYS = 30


def is_fresh(profile: Mapping[str, Any] | None, *, ttl_days: int = CACHE_TTL_DAYS) -> bool:
    """画像是否仍在缓存期内（``expires_at`` 或 ``last_analyzed_at + ttl``）。"""
    if not profile:
        return False
    expires = profile.get("expires_at")
    now = db_mod.parse_iso(db_mod.utcnow_iso())
    if expires:
        try:
            return db_mod.parse_iso(str(expires)) > now
        except (TypeError, ValueError):
            return False
    analyzed = profile.get("last_analyzed_at")
    if not analyzed:
        return False
    try:
        return (now - db_mod.parse_iso(str(analyzed))).days < ttl_days
    except (TypeError, ValueError):
        return False


def expiry_iso(*, ttl_days: int = CACHE_TTL_DAYS) -> str:
    now = db_mod.parse_iso(db_mod.utcnow_iso())
    from datetime import timedelta

    return db_mod.to_iso(now + timedelta(days=ttl_days))
