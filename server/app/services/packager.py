"""对话式打包：把一段「我干了什么」的自由文本落成 Package 草稿（纯本地、零出网）。

用户在对话面板里口述经历，DSH Skill / Web 前端把这段文本交给 ``POST /packages/draft``：
本模块用启发式把**原文逐字保留**地切成「抬头 + 要点 + 可量化结果」，缺什么就返回问题清单
（``questions[]``），让对话继续补，而不是编内容。真正的措辞改写（多 tone 变体）走
``/packages/{id}/variants/generate``（需要 consent preview）。

红线：
- 只做切分与字段归位，**不改写、不润色、不补数字**；原文一个字都不凭空生成。
- 纯本机计算，不碰 LLM、不读 ``data/imports/**``。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

from . import skills as skills_mod

# --------------------------------------------------------------------------------------
# 规则表
# --------------------------------------------------------------------------------------

#: 组织名后缀（中文简历里最稳的判据）
ORG_SUFFIX_RE = re.compile(
    r"(?:公司|集团|银行|证券|科技|网络|传媒|工作室|实验室|研究院|研究所|大学|学院|医院|事务所|中心|基金会|协会)$"
)
ORG_INLINE_RE = re.compile(
    r"(?:公司|集团|银行|科技|传媒|工作室|实验室|研究院|研究所|事务所)[\u4e00-\u9fffA-Za-z]{0,12}"
)

ROLE_HINTS: tuple[str, ...] = (
    "实习生",
    "工程师",
    "分析师",
    "经理",
    "主管",
    "负责人",
    "队长",
    "组长",
    "成员",
    "队员",
    "助理",
    "研究员",
    "设计师",
    "运营",
    "顾问",
    "助教",
    "主席",
    "部长",
    "干事",
    "开发",
    "Intern",
    "Engineer",
    "Analyst",
    "Manager",
    "Lead",
    "Leader",
    "Member",
    "Assistant",
)

DATE_TOKEN = (
    r"(?:\d{4}[.\-/年]\s?\d{1,2}[月]?(?:\s?[.\-/]\s?\d{1,2}[日]?)?"
    r"|\d{4}[.\-/]\d{1,2}|\d{1,2}/\d{4}|\d{4}年?)"
)
DATE_SPAN_RE = re.compile(
    rf"({DATE_TOKEN})\s*(?:-|–|—|~|～|至|到)\s*({DATE_TOKEN}|至今|今|现在|Present|Now|Current)",
    re.IGNORECASE,
)

LOCATION_RE = re.compile(r"^(?:北京|上海|广州|深圳|杭州|武汉|南京|成都|西安|苏州|长沙|重庆|天津|青岛|厦门|合肥|郑州|Remote|异地)\b")

#: 量化结果：「从 1.2k 提升到 8.5k」「下降 62%」「增长 3 倍」
METRIC_PAIR_RE = re.compile(
    r"([\u4e00-\u9fffA-Za-z]{0,8}?)\s*(?:从|由)?\s*([0-9]+(?:\.[0-9]+)?\s*[kKmMwW万千百%]?)\s*"
    r"(?:提升|提高|增长|上升|增至|涨到|降低|下降|减少|降至|降到|缩短|压缩)(?:了|至|到)?\s*"
    r"([0-9]+(?:\.[0-9]+)?\s*[kKmMwW万千百%]?)?"
)
METRIC_VERB_RE = re.compile(r"(提升|提高|增长|上升|降低|下降|减少|缩短|压缩|覆盖|服务|节省|节省了)")
PERCENT_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?%")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

#: 句子切分：中文句末标点 + 换行；保留标点本身
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；!?;])\s*|\n+")

MAX_BULLETS = 12
MIN_BULLET_CHARS = 8

KIND_HINTS: dict[str, tuple[str, ...]] = {
    "internship": ("实习", "intern"),
    "project": ("项目", "project", "课题", "比赛", "竞赛"),
    "education": ("教育", "课程", "gpa", "学业"),
    "award": ("获奖", "奖项", "荣誉", "奖学金", "award"),
    "activity": ("校园", "社团", "学生会", "志愿", "活动", "班委"),
    "custom": (),
}


# --------------------------------------------------------------------------------------
# 基础判定
# --------------------------------------------------------------------------------------
def _clean(text: str) -> str:
    return re.sub(r"[ \t\u00a0\u3000]{2,}", " ", str(text or "")).strip()


def _sentences(text: str) -> list[str]:
    parts = [_clean(chunk) for chunk in SENTENCE_SPLIT_RE.split(str(text or ""))]
    return [part for part in parts if part]


def _fold(parts: Sequence[str]) -> list[str]:
    """把过碎的句子折回上一条（「结果转化率…」这种从句不单独成条）。"""
    folded: list[str] = []
    for part in parts:
        if folded and (
            len(part) < MIN_BULLET_CHARS
            or part.startswith(("其中", "并", "且", "同时", "此外", "以及", "从而", "最终", "进而", "也", "还"))
            or not re.search(r"[\u4e00-\u9fffA-Za-z]{2,}", part)
        ):
            folded[-1] = f"{folded[-1]} {part}".strip()
        else:
            folded.append(part)
    return folded


def guess_kind(text: str, hint: str | None = None) -> str:
    """先看用户显式声明，再从文本里找最靠前的类目词。"""
    if hint:
        return hint
    lowered = str(text or "").lower()
    best: tuple[int, str] = (len(lowered) + 1, "project")
    for kind, words in KIND_HINTS.items():
        for word in words:
            index = lowered.find(word)
            if index >= 0 and index < best[0]:
                best = (index, kind)
    return best[1]


def detect_dates(text: str) -> dict[str, Any]:
    match = DATE_SPAN_RE.search(str(text or ""))
    if not match:
        return {"start_date": None, "end_date": None, "is_current": False, "raw": None}
    start = _clean(match.group(1)).replace("年", "-").replace(".", "-").rstrip("-月")
    end_raw = _clean(match.group(2))
    is_current = end_raw.lower() in ("至今", "今", "现在", "present", "now", "current")
    end = None if is_current else end_raw.replace("年", "-").replace(".", "-").rstrip("-月")
    return {"start_date": start, "end_date": end, "is_current": is_current, "raw": match.group(0).strip()}


def _strip_dates(text: str) -> str:
    return _clean(DATE_SPAN_RE.sub(" ", str(text or "")))


ORG_PREFIX_RE = re.compile(r"^(?:在|于|到|至|就职于|任职于|加入|供职于)\s*")
#: 单位后缀在句中时把尾巴剪掉：``在杭州拓端数据科技有限公司做数据处理实习生`` → 公司全名
ORG_TAIL_RE = re.compile(
    r"^(?P<name>[\u4e00-\u9fffA-Za-z0-9（）()·&\. ]{2,40}?(?:公司|集团|银行|证券|科技|网络|传媒|工作室|实验室|研究院|研究所|大学|学院|医院|事务所|中心|基金会|协会))"
)


def _org_candidate(chunk: str) -> str | None:
    candidate = _clean(ORG_PREFIX_RE.sub("", _clean(chunk)))
    if not candidate:
        return None
    match = ORG_TAIL_RE.match(candidate)
    if match:
        candidate = _clean(match.group("name"))
    if 2 <= len(candidate) <= 40 and ORG_SUFFIX_RE.search(candidate):
        return candidate
    return None


def detect_org(text: str) -> str | None:
    for line in _sentences(text):
        for chunk in re.split(r"[|｜·、,，\-—–]", _strip_dates(line)):
            found = _org_candidate(chunk)
            if found:
                return found
    match = ORG_INLINE_RE.search(str(text or ""))
    return _clean(match.group(0)) if match else None


def detect_role(text: str) -> str | None:
    stripped = _strip_dates(text)
    for chunk in re.split(r"[|｜·、,，\-—–\n]", stripped):
        candidate = _clean(chunk)
        if not candidate or len(candidate) > 24:
            continue
        if any(hint.lower() in candidate.lower() for hint in ROLE_HINTS):
            return candidate
    return None


def detect_location(text: str) -> str | None:
    for chunk in re.split(r"[|｜·、,，\-—–\n]", _strip_dates(text)):
        candidate = _clean(chunk)
        if candidate and LOCATION_RE.match(candidate):
            return candidate
    return None


def detect_tech(text: str) -> list[str]:
    """技术栈：只收录能对上别名表 / 有明确大小写特征的词，不做语义猜测。"""
    found: list[str] = []
    lowered = str(text or "").lower()
    # SKILL_ALIASES: 规范 token -> 别名元组；只做归一，不参与渲染
    for canonical, aliases in skills_mod.SKILL_ALIASES.items():
        for alias in aliases:
            if len(alias) < 2:
                continue
            if re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", lowered):
                if canonical not in found:
                    found.append(canonical)
                break
    # 保留原文里出现的专有大写词（SQL / A/B / K-means 这类）
    for token in re.findall(r"[A-Za-z][A-Za-z0-9+#./-]{1,18}", str(text or "")):
        if token.isupper() and len(token) >= 2 and token.lower() not in {a.lower() for a in found}:
            if token not in found:
                found.append(token)
    return found[:12]


def detect_outcomes(bullets: Iterable[str]) -> list[dict[str, Any]]:
    """只提取原文里明写的「X → Y」「提升 62%」，不补值。"""
    outcomes: list[dict[str, Any]] = []
    for bullet in bullets:
        for match in METRIC_PAIR_RE.finditer(bullet):
            metric = _clean(match.group(1)) or _clean(bullet[:12])
            outcomes.append(
                {
                    "metric": metric,
                    "from": _clean(match.group(2)),
                    "to": _clean(match.group(3)) or None,
                    "evidence": _clean(match.group(0)),
                }
            )
        if not METRIC_PAIR_RE.search(bullet) and PERCENT_RE.search(bullet):
            outcomes.append(
                {
                    "metric": _clean(PERCENT_RE.sub("", bullet))[:16] or "百分比指标",
                    "from": None,
                    "to": _clean(PERCENT_RE.search(bullet).group(0)),
                    "evidence": _clean(bullet),
                }
            )
    return outcomes[:8]


def collect_questions(
    package: dict[str, Any], bullets: Sequence[str], outcomes: Sequence[dict[str, Any]]
) -> list[dict[str, str]]:
    """缺什么问什么 —— 只问「原始信息缺口」，不问风格。

    每问都带 ``field``，前端据此把答案回填到对应字段，而不是让用户自己猜问题对应哪一格。
    """
    questions: list[dict[str, str]] = []

    def ask(field: str, question: str) -> None:
        questions.append({"field": field, "question": question})

    if not package.get("title"):
        ask("title", "这段经历叫什么名字？（项目名 / 岗位名，会显示在简历条目标题上）")
    if not package.get("org"):
        ask("org", "在哪家公司 / 学校 / 组织做的？")
    if not package.get("role"):
        ask("role", "你在这件事里的角色是什么？（如：后端开发实习生 / 队长 / 队员）")
    if not package.get("start_date"):
        ask("date_range", "起止时间是什么？（例：2026.07 - 2026.10，仍在做就说「至今」）")
    if not bullets:
        ask("bullets", "具体做了哪几件事？一件事一句话，我来帮你分条。")
    if not outcomes:
        ask("outcome", "有没有可量化的结果？（QPS、覆盖率、准确率、节省时间等，数字照原样说）")
    return questions


def bullet_keys(count: int) -> list[str]:
    return [f"b{index + 1}" for index in range(count)]


def draft_package(
    text: str,
    *,
    kind: str | None = None,
    lang: str | None = None,
    title: str | None = None,
    org: str | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    """把自由文本落成 Package 草稿（**不落库**，由用户确认后 POST /packages）。"""
    body = str(text or "").strip()
    resolved_kind = guess_kind(body, kind)
    sentences = _fold(_sentences(body))
    dates = detect_dates(body)
    resolved_org = org or detect_org(body)
    resolved_role = role or detect_role(body)

    # 抬头行（含组织/角色/日期的那句）不重复当要点
    bullets: list[str] = []
    for sentence in sentences:
        cleaned = _clean(DATE_SPAN_RE.sub("", sentence))
        cleaned = _clean(re.sub(r"\s*[|｜]\s*", " ", cleaned))
        if not cleaned or len(cleaned) < MIN_BULLET_CHARS:
            continue
        if resolved_org and cleaned.startswith(resolved_org) and len(cleaned) <= len(resolved_org) + 12:
            continue
        if resolved_role and cleaned == resolved_role:
            continue
        bullets.append(sentence if DATE_SPAN_RE.search(sentence) is None else cleaned)
    bullets = bullets[:MAX_BULLETS]

    outcomes = detect_outcomes(bullets)
    package: dict[str, Any] = {
        "title": title or _guess_title(body, resolved_org, resolved_role, resolved_kind),
        "kind": resolved_kind,
        "org": resolved_org,
        "role": resolved_role,
        "start_date": dates["start_date"],
        "end_date": dates["end_date"],
        "is_current": dates["is_current"],
        "location": detect_location(body),
        "summary": bullets[0] if bullets else None,
        "tech_stack": detect_tech(body),
        "tags": [],
        "outcomes": outcomes,
        "status": "draft",
        "source": "authored",
    }
    if package["summary"] and len(str(package["summary"])) > 200:
        package["summary"] = str(package["summary"])[:200]

    keys = bullet_keys(len(bullets))
    facts = [
        {
            "bullet_key": key,
            "fact": bullet,
            "chars": len(bullet),
            "has_metric": bool(NUMBER_RE.search(bullet)),
        }
        for key, bullet in zip(keys, bullets)
    ]

    warnings: list[str] = []
    if not package["tech_stack"]:
        warnings.append("NO_TECH_STACK_DETECTED")
    if bullets and not outcomes:
        warnings.append("NO_QUANTIFIED_OUTCOME")
    if resolved_kind == "project" and not package["role"]:
        warnings.append("ROLE_UNSPECIFIED")

    return {
        "package": package,
        "bullets": facts,
        "variants": [],
        "questions": collect_questions(package, bullets, outcomes),
        "warnings": warnings,
        "stats": {
            "chars": len(body),
            "bullets": len(bullets),
            "with_metric": sum(1 for item in facts if item["has_metric"]),
            "outcomes": len(outcomes),
        },
        "lang": lang or ("en" if re.search(r"[A-Za-z]{4,}", body) and not re.search(r"[\u4e00-\u9fff]", body) else "zh"),
    }


def _guess_title(text: str, org: str | None, role: str | None, kind: str) -> str | None:
    """标题优先级：首行短句 > 「角色 @ 组织」> 组织名。绝不生造。"""
    first = _sentences(text)
    if first:
        candidate = _clean(DATE_SPAN_RE.sub("", first[0]))
        candidate = _clean(re.sub(r"\s*[|｜]\s*", " ", candidate))
        if 2 <= len(candidate) <= 40 and ORG_SUFFIX_RE.search(candidate) is None:
            if not (role and candidate == role):
                return candidate
    if role and org:
        return f"{role} @ {org}"
    return org


def apply_bullets(package_id: str, facts: Sequence[dict[str, Any]], *, repo: Any, tone: str = "impact", lang: str = "zh") -> int:
    """把草稿的 facts 落成**未核实**的变体（原文即变体，不做改写）。

    用户确认后调用；返回写入条数。重复的 (bullet_key, tone, lang) 走 conflict="update"。
    """
    written = 0
    for fact in facts:
        text = str(fact.get("fact") or "").strip()
        if not text:
            continue
        repo.add_variant(
            package_id,
            {
                "bullet_key": fact.get("bullet_key") or f"b{written + 1}",
                "tone": tone,
                "lang": lang,
                "text": text,
                "verified": False,
                "llm_generated": False,
            },
            conflict="update",
        )
        written += 1
    return written
