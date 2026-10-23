"""JD（岗位需求）分析：启发式拆解 + LLM 输出归一 + 本地匹配打分。

三条设计约束（来自 docs + captain 实测口径）：

1. **启发式必须也能产出 `competitiveness`**（契约 §6.1）：LLM 不可用时不许返回 `None`，
   否则「关掉 AI 就看不到竞争力评估」——那等于把校名白发了。
2. **`candidate_status` 逐条对照候选人现状**：只列岗位要什么、不判候选人满足度，
   等于把判断推给用户。这里用档案（学历/专业/届数/技能行）+ 经历包做本地判定。
3. **匹配打分纯本地**（§6 的 `/jds/{id}/match`）：不联网、不调 LLM，只有集合命中与权重和。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence

from . import skills as skills_mod

#: 院校层次词表（用于判「JD 是否提院校门槛」与「候选人层次」）
TIER_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"C9|九校联盟", "C9"),
    (r"985", "985"),
    (r"211", "211"),
    (r"双一流|一流大学|一流学科", "双一流"),
    (r"海外院校|海归|留学|QS\s*\d+|世界排名", "海外"),
)
TIER_ORDER = ("C9", "985", "211", "双一流", "普通本科", "海外", "其他")

#: 院校门槛的「正向」表述（有门槛）与「负向」表述（明确不限）
#: 门槛动词分两档——**「优先」不是门槛**。混在一起会把「不卡但偏 985」误判成「只招 985」，
#: 用户会因此放弃本来能投的岗位（captain 实测 D-39）。
HARD_VERBS = r"(?:仅限|限|限定|只招|必须|须|要求|门槛|起|起步|及以上|以上)"
SOFT_VERBS = r"(?:优先|更佳|加分|青睐|欢迎|倾向)"

#: 硬门槛：层次词在前（「985/211 院校及以上」）或门槛词在前（「要求 985」「仅限 211」）
SCHOOL_HARD_RE = re.compile(
    r"(?P<tiers>(?:C9|985|211|双一流|一流大学|一流学科)[^\n。；;，,]{0,12}?)"
    rf"(?:院校|学校|高校)?\s*{HARD_VERBS}"
    r"|(?P<only>(?:仅限|限|限定|只招|必须|须|要求|面向)\s*(?:C9|985|211|双一流))"
)
#: 偏好（软）：「985/211 院校优先」—— 记录偏好，但 hard_filter 必须为 false
SCHOOL_SOFT_RE = re.compile(
    r"(?P<tiers>(?:C9|985|211|双一流|一流大学|一流学科)[^\n。；;，,]{0,12}?)"
    rf"(?:院校|学校|高校)?\s*{SOFT_VERBS}"
)
#: 「985 或 211 均可 / 985/211 任一」—— 仍是硬门槛（满足其一即可），必须把层次收全
SCHOOL_EITHER_RE = re.compile(
    r"(?P<tiers>(?:C9|985|211|双一流|一流大学|一流学科)"
    r"(?:\s*(?:[/、或]|和|及)\s*(?:C9|985|211|双一流|一流大学|一流学科))+\s*(?:院校|学校|高校)?"
    r"\s*(?:均可|皆可|任一|之一|满足其一))"
)
SCHOOL_NEGATIVE_RE = re.compile(
    r"(?:不设|不限|不卡|无|没有|不要求|无需|不需要)(?:任何)?(?:院校|学校)(?:门槛|要求|限制)?"
    r"|院校(?:门槛)?(?:不限|无要求)"
    r"|(?:不|无需|不需要)\s*要求\s*(?:C9|985|211|双一流|院校|学历层次)"
)

DEGREE_RE = re.compile(r"(硕士|研究生|本科|博士|大专|专科)(?:及以上|以上)?")
MAJOR_RE = re.compile(
    r"(统计学|数学|计算机|管理科学|经济学|金融|会计|市场营销|电子商务|信息管理|软件工程|"
    r"数据科学|人工智能|新闻传播|汉语言文学|心理学|工业工程|物流管理|财务管理)"
)

PRIORITY_MARKERS: tuple[tuple[str, str], ...] = (
    (r"必须|须|要求|任职资格|硬性|限", "must"),
    (r"优先|加分|更佳|更好|preferred|plus", "nice"),
)
SECTION_RE = re.compile(r"^(?:#{1,6}\s*)?(?P<name>[^\n:：]{2,20})[:：]\s*$|^(?:#{1,6}\s*)?(?P<head>[^\n]{2,20})$")

CATEGORY_BY_TOKEN: dict[str, str] = {
    "python": "tool", "r": "tool", "sql": "tool", "excel": "tool", "spark": "tool",
    "java": "tool", "golang": "tool", "flask": "tool", "word": "tool", "ppt": "tool",
    "tableau": "tool", "powerbi": "tool", "superset": "tool",
    "statistics": "hard", "clustering": "hard", "regression": "hard", "ab_test": "hard",
    "data_analysis": "hard", "data_cleaning": "hard", "data_mining": "hard",
    "modeling": "hard", "deep_learning": "hard", "visualization": "hard",
    "english": "language", "cet": "certificate",
}

#: 软技能词（JD 里常写但不可量化）→ 只进 requirements 的 soft 类，不计入匹配权重
SOFT_SKILLS: tuple[str, ...] = (
    "沟通", "协作", "表达", "逻辑", "抗压", "细致", "主动", "学习能力", "责任心", "耐心",
)

MUST_TOKENS: tuple[str, ...] = ("必须", "要求", "硬性", "须", "至少")


# ----------------------------------------------------------------------------------
# 文本工具
# ----------------------------------------------------------------------------------


NOTE_LINE_RE = re.compile(r"^\s*(?:>|<!--).*$", re.M)


def strip_notes(text: str) -> str:
    """去掉样张/粘贴文本里的说明性注释（以 ``>`` 开头的引用块、HTML 注释）。

    这些行是「文档写给评审看的」，不是 JD 正文；留着会让门槛检测抓到
    「`threshold` 不得编造『985/211』之类门槛」这种反例说明，进而误判成 JD 有要求。
    """
    cleaned = NOTE_LINE_RE.sub("", str(text or ""))
    cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.S)
    return cleaned


def _lines(text: str) -> list[str]:
    return [line.strip() for line in str(text or "").splitlines()]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[。；;！!？?\n]", str(text or ""))
    return [part.strip(" -·\t") for part in parts if part and part.strip(" -·\t")]


def _priority_of(line: str) -> str:
    lowered = line.lower()
    for pattern, priority in PRIORITY_MARKERS:
        if re.search(pattern, lowered):
            return priority
    return "should"


def _weight_of(priority: str, category: str) -> float:
    base = {"must": 0.9, "should": 0.6, "nice": 0.3}.get(priority, 0.5)
    if category == "soft":
        base = min(base, 0.3)
    return round(base, 2)


# ----------------------------------------------------------------------------------
# 院校信号
# ----------------------------------------------------------------------------------


CLAUSE_BOUNDARY = "。；;！!？?\n"


def _clause_at(text: str, start: int, end: int) -> str:
    """取命中片段所在的整个分句 —— 层次词常与门槛动词隔开（「仅限 985/211 院校」）。"""
    left = max(text.rfind(ch, 0, start) for ch in CLAUSE_BOUNDARY) + 1
    rights = [text.find(ch, end) for ch in CLAUSE_BOUNDARY]
    rights = [pos for pos in rights if pos != -1]
    right = min(rights) if rights else len(text)
    return text[left:right].strip()


def _tiers_in(snippet: str) -> list[str]:
    """按出现顺序收全层次词（``985/211/双一流`` 收三个，不是只收第一个）。"""
    found: list[tuple[int, str]] = []
    for tier_pattern, tier in TIER_PATTERNS[:4]:
        for match in re.finditer(tier_pattern, snippet):
            found.append((match.start(), tier))
    ordered: list[str] = []
    for _pos, tier in sorted(found):
        if tier not in ordered:
            ordered.append(tier)
    return ordered


def detect_school_gate(texts: Iterable[str] | str) -> dict[str, Any]:
    """判断文本里有没有「院校门槛」表述，以及是硬门槛还是仅仅偏好。

    这是 ANL-08（防编造）的核心，也是 D-39（偏好 ≠ 门槛）的核心：

    * 只有**硬门槛动词**（仅限/要求/须/及以上…）出现才算 ``hard_filter=true``；
    * **偏好动词**（优先/更佳/加分…）只写进 ``preferred_tiers`` + ``threshold="不限（偏好 …）"``，
      ``hard_filter`` 必须为 ``false`` —— 用户不该因为「优先」放弃能投的岗位；
    * 否定表述（不设院校门槛 / 不要求 985）判 ``false``，但偏好信息保留；
    * 两种都没有 → 「未提及」，evidence 明确说明依据，**绝不编造门槛**。

    传 ``str`` 与传 ``[str]`` 结果**逐字相等**：裸字符串曾被按字符迭代，
    于是永远匹配不到、静默返回「未提及」（captain 与 supervisor 都被骗过一次）。
    """
    if isinstance(texts, str):
        texts = [texts]
    joined = "\n".join(str(t or "") for t in texts)

    def _negated(index: int) -> bool:
        return bool(re.search(r"(?:不|无需|不需要|没有|不设|不限)\s*$", joined[max(0, index - 4):index]))

    def _collect(pattern: re.Pattern[str]) -> tuple[list[str], list[str]]:
        quotes: list[str] = []
        found: list[str] = []
        for match in pattern.finditer(joined):
            if _negated(match.start()):
                continue  # 「不要求 985」会被正向式误吃
            snippet = match.group(0).strip()
            if not snippet:
                continue
            clause = _clause_at(joined, match.start(), match.end())
            # 证据优先引完整分句（「仅限 985/211 院校」而不是被正则截断的「仅限 985」）
            quoted = clause if clause and snippet in clause and len(clause) <= 60 else snippet
            quotes.append(quoted[:120])
            # 层次必须从**整个分句**里收（「仅限 985/211 院校」的 211 在命中片段之外）
            for tier in _tiers_in(clause if clause else snippet):
                if tier not in found:
                    found.append(tier)
        return quotes, found

    hard_quotes, hard_tiers = _collect(SCHOOL_HARD_RE)
    soft_quotes, soft_tiers = _collect(SCHOOL_SOFT_RE)
    either_quotes, either_tiers = _collect(SCHOOL_EITHER_RE)
    if either_quotes and not hard_quotes:
        # 「985 或 211 均可」= 满足其一即可的硬门槛，不是「未提及」
        hard_quotes = either_quotes
        hard_tiers = either_tiers

    # 否定表述：「专业不限」这类与院校无关的话不算，必须点到院校/层次
    negations = [
        m for m in SCHOOL_NEGATIVE_RE.finditer(joined)
        if re.search(r"院校|学校|985|211|双一流|C9|层次", m.group(0))
    ]
    neg_quote = negations[0].group(0).strip()[:40] if negations else ""

    if hard_quotes:
        # 硬门槛（同句另有偏好也按硬门槛判，证据引硬门槛那句）
        return {
            "threshold": "/".join(hard_tiers) if hard_tiers else "院校门槛",
            "preferred_tiers": list(dict.fromkeys([*hard_tiers, *soft_tiers])),
            "hard_filter": True,
            "evidence": f"JD 原文：「{hard_quotes[0]}」",
            "confidence": 0.8,
        }
    if neg_quote and soft_tiers:
        # D 例：明说不设门槛，但保留「优先」信息
        return {
            "threshold": f"不限（偏好 {'/'.join(soft_tiers)}）",
            "preferred_tiers": soft_tiers,
            "hard_filter": False,
            "evidence": f"JD 同时出现「{soft_quotes[0][:40]}」与「{neg_quote}」，按「不设硬门槛、{'/'.join(soft_tiers)} 优先」处理",
            "confidence": 0.55,
        }
    if neg_quote:
        return {
            "threshold": "不限",
            "preferred_tiers": [],
            "hard_filter": False,
            "evidence": f"JD 原文写明「{neg_quote}」",
            "confidence": 0.6,
        }
    if soft_quotes:
        # A 例：只有偏好，不是门槛
        return {
            "threshold": f"不限（偏好 {'/'.join(soft_tiers)}）" if soft_tiers else "不限（偏好院校背景）",
            "preferred_tiers": soft_tiers,
            "hard_filter": False,
            "evidence": f"JD 原文：「{soft_quotes[0]}」（属偏好表述，不是硬门槛）",
            "confidence": 0.65,
        }
    return {
        "threshold": "不限",
        "preferred_tiers": [],
        "hard_filter": False,
        "evidence": "依据：JD 全文未出现院校层次要求（仅见学历/专业要求）",
        "confidence": 0.7,
    }


#: 常见海外院校缩写（只用于「明显是海外校」的判定，不追求覆盖率）
OVERSEAS_HINTS: tuple[str, ...] = (
    "麻省理工", "斯坦福", "哈佛", "牛津", "剑桥", "耶鲁", "普林斯顿", "加州大学", "加州理工",
    "哥伦比亚大学", "康奈尔", "帝国理工", "伦敦政治经济", "伦敦大学", "新加坡国立", "南洋理工",
    "香港大学", "香港中文", "香港科技", "东京大学", "京都大学", "早稻田", "首尔大学", "多伦多",
    "麦吉尔", "墨尔本", "悉尼大学", "新南威尔士", "卡内基梅隆", "密歇根", "伊利诺伊",
    "MIT", "Stanford", "Harvard", "Oxford", "Cambridge", "Yale", "Princeton", "Berkeley",
    "Columbia", "Cornell", "UCLA", "NYU", "CMU", "ETH", "EPFL", "NUS", "NTU", "HKU",
    "HKUST", "CUHK", "Imperial College", "LSE", "UCL", "Tokyo", "Kyoto", "Seoul",
    "University of", "College of", "Institute of Technology", "School of Management",
)

KNOWN_C9: tuple[str, ...] = (
    "清华大学", "北京大学", "复旦大学", "上海交通大学", "浙江大学",
    "中国科学技术大学", "南京大学", "哈尔滨工业大学", "西安交通大学",
)
KNOWN_985: tuple[str, ...] = (
    "北京师范大学", "中国人民大学", "示例大学", "华中科技大学", "中山大学", "厦门大学",
    "四川大学", "同济大学", "南开大学", "天津大学", "北京航空航天大学", "北京理工大学",
    "东南大学", "华东师范大学", "山东大学", "吉林大学", "湖南大学", "中南大学", "重庆大学",
    "大连理工大学", "华南理工大学", "兰州大学", "东北大学", "西北工业大学", "中国农业大学",
    "中央民族大学", "国防科技大学", "电子科技大学", "西北农林科技大学",
)
KNOWN_211: tuple[str, ...] = (
    "郑州大学", "苏州大学", "上海财经大学", "中央财经大学", "对外经济贸易大学",
    "北京邮电大学", "西安电子科技大学", "南京航空航天大学", "华中师范大学", "暨南大学",
    "西南财经大学", "中南财经政法大学", "上海大学", "南京信息工程大学", "北京交通大学",
    "北京科技大学", "中国传媒大学", "华中农业大学", "南京师范大学", "华南师范大学",
)


def tier_from_school_name(school: str | None) -> str | None:
    """按校名推断院校层次——**推断不出就返回 None**，绝不默认成「普通本科」。

    内置小表只覆盖常见校名（C9/985/211 的一部分 + 常见海外缩写），
    **未收录不等于普通本科**：名单覆盖有限，漏掉一所校名就把用户判成「普通本科」
    属于编造事实（方向与「编造门槛」相反，但后果一样是误导用户）。
    因此未命中一律返回 ``None``，由调用方落到诚实的「其他」桶并提示用户手填
    ``UserProfile.school_tier``（该字段存在就是为了纠正这里的推断）。
    """
    name = (school or "").strip()
    if not name:
        return None
    if any(item in name for item in KNOWN_C9):
        return "C9"
    if any(item in name for item in KNOWN_985):
        return "985"
    if any(item in name for item in KNOWN_211):
        return "211"
    lowered = name.lower()
    if any(hint.lower() in lowered for hint in OVERSEAS_HINTS):
        return "海外"
    # 纯英文校名（无中文）通常意味着海外/合办 → 归入「海外」，但仍不算已识别
    if not re.search(r"[\u4e00-\u9fff]", name) and re.search(r"[A-Za-z]{3,}", name):
        return "海外"
    return None


def competitiveness(
    *,
    profile: Mapping[str, Any],
    school_preference: Mapping[str, Any],
    requirements: Sequence[Mapping[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    """生成 §6.1 的 ``competitiveness``（LLM 与启发式共用同一套兜底）。

    诚实性原则：层次识别不出来时落「其他」并提示手填，**不让未知拖垮其他评分项**
    （verdict/gap_notes 里不得出现「院校层次偏低」这类结论）。
    """
    # 档案里是 school_zh / school_en；也接受已归一化的 school（LLM 上下文用短名）
    school = str(
        profile.get("school") or profile.get("school_zh") or profile.get("school_en") or ""
    ).strip()
    tier = (profile.get("school_tier") or "").strip() or None
    recognized = bool(tier)
    if not tier:
        tier = tier_from_school_name(school)
        recognized = bool(tier)
        if recognized:
            warnings.append(
                {
                    "code": "SCHOOL_TIER_INFERRED",
                    "severity": "info",
                    "message": f"院校层次未手填，已按校名推断为「{tier}」；可在个人资料里改",
                    "details": {"school": school, "tier": tier, "recognized": True},
                }
            )
        else:
            warnings.append(
                {
                    "code": "SCHOOL_TIER_INFERRED",
                    "severity": "warn",
                    "message": "未能识别院校层次，已按「其他」处理；建议在个人资料里手填 school_tier",
                    "details": {"school": school, "recognized": False},
                }
            )
    tier = tier or "其他"
    unknown = not recognized and tier == "其他"

    degree = (profile.get("degree") or "").strip()
    gate = bool(school_preference.get("hard_filter"))
    tiers = list(school_preference.get("preferred_tiers") or [])
    satisfied_gate = (not gate) or (tier in tiers) or (not tiers)
    gate_failed = gate and not satisfied_gate and not unknown
    school_label = f"{school or '未填校名'}"

    if unknown:
        signal = (
            f"院校层次未识别（{school_label}），已按「其他」记录，不影响其他维度评分；"
            "建议在个人资料里手填院校层次"
        )
    elif gate and satisfied_gate:
        signal = f"{tier} 院校（{school_label}）满足 JD 明示的 {'/'.join(tiers) or '院校'} 门槛"
    elif gate:
        signal = f"{tier} 院校（{school_label}）与 JD 门槛 {'/'.join(tiers)} 不匹配，需靠经历补足"
    elif tiers:
        signal = f"{tier} 院校（{school_label}）；该 JD 未设硬门槛，但 {'/'.join(tiers)} 更受偏好"
    else:
        signal = f"{tier} 院校（{school_label}），该 JD 未设院校门槛，校名不构成劣势"

    degree_req = detect_degree_requirement(requirements)
    degree_fit = _fit_from_requirement(degree, degree_req)
    major_fit = _major_fit(profile, requirements)
    experience_fit = _experience_fit(profile, requirements)

    gaps = [req["skill"] for req in requirements if req.get("candidate_status") == "missing"][:5]
    gap_notes = [f"缺少「{gap}」的证据" for gap in gaps]
    if gate_failed:
        # 只说「弱」不说原因，用户会困惑；unknown 时不写「偏低」（诚实性要求）
        gap_notes.insert(
            0,
            f"院校层次「{tier}」不在 JD 门槛「{'/'.join(tiers)}」内，需靠经历或成绩补足",
        )
    verdict = _verdict(degree_fit, major_fit, experience_fit, gate_failed)
    return {
        "school_tier": tier,
        "school_tier_recognized": recognized,
        "school_signal": signal,
        "degree_fit": degree_fit,
        "major_fit": major_fit,
        "experience_fit": experience_fit,
        "verdict": verdict,
        "gap_notes": gap_notes,
    }


def detect_degree_requirement(requirements: Sequence[Mapping[str, Any]]) -> str | None:
    for req in requirements:
        text = f"{req.get('skill', '')} {req.get('raw_quote', '')} {req.get('evidence_hint', '')}"
        match = DEGREE_RE.search(text)
        if match:
            return match.group(1)
    return None


def _degree_rank(word: str | None) -> int:
    return {"大专": 1, "专科": 1, "本科": 2, "硕士": 3, "研究生": 3, "博士": 4}.get(word or "", 0)


def _fit_from_requirement(actual: str | None, required: str | None) -> str:
    if not required:
        return "strong"
    have, need = _degree_rank(actual), _degree_rank(required)
    if have >= need and need:
        return "strong"
    if have and have == need - 1:
        return "medium"
    return "weak"


def _major_fit(profile: Mapping[str, Any], requirements: Sequence[Mapping[str, Any]]) -> str:
    major = (profile.get("major") or "").strip()
    if not major:
        return "medium"
    wanted = set()
    for req in requirements:
        text = f"{req.get('skill', '')} {req.get('raw_quote', '')}"
        wanted.update(m.group(0) for m in MAJOR_RE.finditer(text))
    if not wanted:
        return "medium"
    if any(item[:2] in major for item in wanted):
        return "strong"
    return "medium"


def _experience_fit(profile: Mapping[str, Any], requirements: Sequence[Mapping[str, Any]]) -> str:
    statuses = [req.get("candidate_status") for req in requirements if req.get("category") != "soft"]
    if not statuses:
        return "medium"
    satisfied = sum(1 for s in statuses if s == "satisfied")
    ratio = satisfied / len(statuses)
    if ratio >= 0.7:
        return "strong"
    if ratio >= 0.4:
        return "medium"
    return "weak"


def _verdict(degree_fit: str, major_fit: str, experience_fit: str, gate_failed: bool) -> str:
    if gate_failed:
        return "weak"
    score = {"strong": 2, "medium": 1, "weak": 0}
    total = score[degree_fit] + score[major_fit] + score[experience_fit]
    if total >= 5:
        return "strong"
    if total >= 3:
        return "medium"
    return "weak"


# ----------------------------------------------------------------------------------
# 需求抽取
# ----------------------------------------------------------------------------------


def _candidate_vocabulary(profile: Mapping[str, Any], packages: Sequence[Mapping[str, Any]]) -> set[str]:
    """候选人已有的技能 token（档案技能行 + 经历包技术栈/标签/正文）。"""
    vocab: set[str] = set()
    for row in profile.get("skills") or []:
        for token in row.get("tokens") or []:
            vocab.add(str(token))
        category, body = skills_mod.split_category(str(row.get("line") or ""))
        if category:
            vocab.update(token for token in skills_mod.derive_tokens(body))
    degree = profile.get("degree")
    if degree:
        vocab.add(str(degree))
    major = profile.get("major")
    if major:
        vocab.add(str(major))
    for package in packages:
        for key in ("tech_stack", "tags"):
            for item in package.get(key) or []:
                vocab.add(str(item).lower())
        text = " ".join(
            str(package.get(field) or "") for field in ("title", "summary", "role", "org")
        )
        vocab.update(skills_mod.derive_tokens(text))
    return vocab


def _status_for(skill: str, category: str, vocab: set[str], text_blob: str) -> str:
    token = skills_mod.normalize(skill)
    candidates = {token}
    candidates.update(skills_mod.derive_tokens(skill))
    if candidates & vocab:
        return "satisfied"
    needle = skill.strip().lower()
    if needle and needle in text_blob:
        return "partial"
    if category == "soft":
        return "partial"
    return "missing"


def _requirement(
    skill: str,
    *,
    category: str,
    priority: str,
    quote: str,
    vocab: set[str],
    text_blob: str,
    source: str,
) -> dict[str, Any]:
    return {
        "skill": skill[:80],
        "category": category,
        "priority": priority,
        "weight": _weight_of(priority, category),
        "evidence_hint": (quote[:200] if quote else None),
        "raw_quote": (quote[:300] if quote else None),
        "source": source,
        "candidate_status": _status_for(skill, category, vocab, text_blob),
        "candidate_status_source": source,
        "matched_package_ids": [],
    }


def _skill_category(skill: str) -> str:
    token = skills_mod.normalize(skill)
    if token in CATEGORY_BY_TOKEN:
        return CATEGORY_BY_TOKEN[token]
    if skill in SOFT_SKILLS:
        return "soft"
    if re.search(r"(英语|英文|CET|雅思|托福|日语)", skill):
        return "language"
    if re.search(r"(证书|资格证|认证)", skill):
        return "certificate"
    if re.search(r"(行业|领域|业务|电商|金融|增长|供应链)", skill):
        return "domain"
    return "hard"


def heuristic_requirements(
    text: str,
    *,
    profile: Mapping[str, Any],
    packages: Sequence[Mapping[str, Any]] = (),
    max_requirements: int = 25,
) -> list[dict[str, Any]]:
    """从 JD 原文抽需求：技能词（别名表）+ 软件/语言/证书 + 软技能。"""
    text = strip_notes(text)
    vocab = _candidate_vocabulary(profile, packages)
    blob = " ".join(
        [
            *(str(p.get("summary") or "") for p in packages),
            *(str(p.get("title") or "") for p in packages),
            *((str(t) for p in packages for t in (p.get("tech_stack") or []))),
        ]
    ).lower()
    lower = text.lower()
    found: dict[str, dict[str, Any]] = {}

    for canonical, aliases in skills_mod.SKILL_ALIASES.items():
        for alias in aliases:
            if not alias:
                continue
            if alias.lower() not in lower:
                continue
            sentence = _quote_for(text, alias)
            if not sentence:
                continue
            priority = _priority_of(sentence)
            display = _display_name(canonical, alias, sentence)
            if display.lower() in found:
                found[display.lower()]["priority"] = _stronger(found[display.lower()]["priority"], priority)
                continue
            found[display.lower()] = _requirement(
                display,
                category=_skill_category(canonical),
                priority=priority,
                quote=sentence,
                vocab=vocab,
                text_blob=blob,
                source="heuristic",
            )
            break

    for tool in ("Tableau", "Power BI", "Superset", "Hive", "Spark", "Docker", "Git"):
        if tool.lower() in lower and tool.lower() not in found:
            sentence = _quote_for(text, tool)
            found[tool.lower()] = _requirement(
                tool,
                category="tool",
                priority=_priority_of(sentence or ""),
                quote=sentence or "",
                vocab=vocab,
                text_blob=blob,
                source="heuristic",
            )

    for soft in SOFT_SKILLS:
        if soft in text and soft.lower() not in found:
            sentence = _quote_for(text, soft)
            found[soft.lower()] = _requirement(
                soft,
                category="soft",
                priority="should",
                quote=sentence or "",
                vocab=vocab,
                text_blob=blob,
                source="heuristic",
            )

    # 学历/届别/专业 这类结构性要求也进 requirements（否则 competitiveness 无处可依）
    degree = DEGREE_RE.search(text)
    if degree and "学历" not in found:
        sentence = _quote_for(text, degree.group(0))
        found["学历"] = _requirement(
            degree.group(0) + "及以上" if "以上" not in (sentence or "") else degree.group(0),
            category="certificate",
            priority="must" if "及以上" in (sentence or "") else _priority_of(sentence or ""),
            quote=sentence or degree.group(0),
            vocab=vocab,
            text_blob=blob,
            source="heuristic",
        )

    ordered = sorted(
        found.values(),
        key=lambda r: ({"must": 0, "should": 1, "nice": 2}[r["priority"]], r["skill"].lower()),
    )
    return ordered[:max_requirements]


def _stronger(left: str, right: str) -> str:
    order = {"must": 0, "should": 1, "nice": 2}
    return left if order.get(left, 1) <= order.get(right, 1) else right


def _display_name(canonical: str, alias: str, sentence: str) -> str:
    pretty = {
        "python": "Python", "r": "R", "sql": "SQL", "excel": "Excel", "clustering": "聚类",
        "regression": "回归", "statistics": "统计学", "visualization": "数据可视化",
        "pandas": "Pandas", "ml": "机器学习", "llm": "LLM", "spark": "Spark",
        "java": "Java", "golang": "Go", "flask": "Flask", "word": "Word", "ppt": "PPT",
        "data_analysis": "数据分析", "data_cleaning": "数据清洗", "data_mining": "数据挖掘",
        "modeling": "建模", "deep_learning": "深度学习", "crawler": "爬虫",
        "automation": "自动化", "reporting": "数据报表",
    }
    if canonical in pretty:
        return pretty[canonical]
    return alias if alias.isascii() else canonical


def _quote_for(text: str, needle: str) -> str:
    for sentence in _sentences(text):
        if needle.lower() in sentence.lower():
            return sentence[:300]
    return ""


# ----------------------------------------------------------------------------------
# 归一化 LLM 输出
# ----------------------------------------------------------------------------------


def normalize_requirements(
    raw: Any,
    *,
    profile: Mapping[str, Any],
    packages: Sequence[Mapping[str, Any]] = (),
    max_requirements: int = 25,
) -> list[dict[str, Any]]:
    """把 LLM 的 requirements 归一成库表能落的结构（缺字段补齐 + candidate_status 兜底）。"""
    vocab = _candidate_vocabulary(profile, packages)
    items: list[dict[str, Any]] = []
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, str):
            entry = {"skill": entry}
        if not isinstance(entry, Mapping):
            continue
        skill = str(entry.get("skill") or "").strip()
        if not skill:
            continue
        category = entry.get("category")
        if category not in ("hard", "soft", "domain", "tool", "language", "certificate"):
            category = _skill_category(skill)
        priority = entry.get("priority")
        if priority not in ("must", "should", "nice"):
            priority = _priority_of(str(entry.get("raw_quote") or entry.get("evidence_hint") or ""))
        status = entry.get("candidate_status")
        status_source = "llm"
        if status not in ("satisfied", "partial", "missing"):
            status = _status_for(skill, category, vocab, "")
            status_source = "heuristic"
        items.append(
            {
                "skill": skill[:80],
                "category": category,
                "priority": priority,
                "weight": float(entry.get("weight") if entry.get("weight") is not None else _weight_of(priority, category)),
                "evidence_hint": (str(entry.get("evidence_hint"))[:200] if entry.get("evidence_hint") else None),
                "raw_quote": (str(entry.get("raw_quote"))[:300] if entry.get("raw_quote") else None),
                "source": "llm",
                "candidate_status": status,
                "candidate_status_source": status_source,
                "matched_package_ids": [],
            }
        )
    if not items:
        return heuristic_requirements(
            "", profile=profile, packages=packages, max_requirements=max_requirements
        )
    items.sort(key=lambda r: ({"must": 0, "should": 1, "nice": 2}[r["priority"]], r["skill"].lower()))
    return items[:max_requirements]


def _coerce_tier(value: Any) -> str | None:
    """把模型给的层次归一成 ``TIER_ORDER`` 里的单个值。

    实测 deepseek-reasoner 会返回 ``"985/211/双一流"`` 这种复合串（它把 JD 的门槛原样抄回来）。
    直接判 ``not in TIER_ORDER`` 再回退会把模型已经读对的信息丢掉，所以这里按 ``TIER_ORDER``
    取**最高**一档（985/211/双一流 → 985），只在完全认不出时返回 None 交给本地推断。
    """
    text = str(value or "").strip()
    if not text:
        return None
    if text in TIER_ORDER:
        return text
    for tier in TIER_ORDER:
        if tier in text:
            return tier
    return None


def normalize_competitiveness(
    raw: Any,
    *,
    profile: Mapping[str, Any],
    school_preference: Mapping[str, Any],
    requirements: Sequence[Mapping[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    """LLM 的 competitiveness 过一遍护栏：枚举非法/缺字段/套话一律回退到本地推断。"""
    fallback = competitiveness(
        profile=profile,
        school_preference=school_preference,
        requirements=requirements,
        warnings=warnings,
    )
    if not isinstance(raw, Mapping):
        warnings.append(
            {
                "code": "COMPETITIVENESS_FALLBACK",
                "severity": "warn",
                "message": "模型未给出竞争力评估，已用本地规则补齐（校名仍参与判断）",
                "details": {},
            }
        )
        return fallback

    tier = _coerce_tier(raw.get("school_tier"))
    if tier is None:
        tier = fallback["school_tier"]
    signal = str(raw.get("school_signal") or "").strip()
    school = (profile.get("school") or "").strip()
    tier_words = re.search(r"C9|985|211|双一流|普通本科|海外|院校|学校|门槛", signal)
    # AC-ANL-06 反向断言：≥8 字且必须点出「校名或院校层次词」，禁「综合素质良好」式套话
    if len(signal) < 8 or not tier_words or (school and school not in signal and not tier_words):
        signal = fallback["school_signal"]
        warnings.append(
            {
                "code": "SCHOOL_SIGNAL_FALLBACK",
                "severity": "warn",
                "message": "模型的院校结论是套话或未点出院校层次，已改用本地可核对表述",
                "details": {"raw_signal": signal[:120]},
            }
        )
    result = {
        "school_tier": tier,
        "school_tier_recognized": bool(fallback.get("school_tier_recognized")) if tier == fallback["school_tier"] else True,
        "school_signal": signal,
        "degree_fit": _enum(raw.get("degree_fit"), fallback["degree_fit"]),
        "major_fit": _enum(raw.get("major_fit"), fallback["major_fit"]),
        "experience_fit": _enum(raw.get("experience_fit"), fallback["experience_fit"]),
        "verdict": _enum(raw.get("verdict"), fallback["verdict"]),
        "gap_notes": [str(note)[:120] for note in (raw.get("gap_notes") or []) if str(note).strip()][:8],
    }
    if not result["gap_notes"]:
        result["gap_notes"] = fallback["gap_notes"]
    return result


def _enum(value: Any, fallback: str) -> str:
    return value if value in ("strong", "medium", "weak") else fallback


# ----------------------------------------------------------------------------------
# 本地匹配打分（§6 /jds/{id}/match）
# ----------------------------------------------------------------------------------


def match_packages(
    requirements: Sequence[Mapping[str, Any]],
    packages: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """集合命中 + 权重和。**纯本地**：不联网、不调 LLM（契约 §6）。"""
    scored: list[dict[str, Any]] = []
    covered_skills: set[str] = set()
    total_weight = sum(float(req.get("weight") or 0) for req in requirements) or 1.0
    for package in packages:
        corpus = _package_corpus(package)
        hits: list[str] = []
        gaps: list[str] = []
        score = 0.0
        for req in requirements:
            if _package_hits(package, corpus, req):
                hits.append(req["skill"])
                covered_skills.add(req["skill"].lower())
                score += float(req.get("weight") or 0)
            else:
                gaps.append(req["skill"])
        scored.append(
            {
                "package_id": package["id"],
                "title": package.get("title"),
                "score": round(min(1.0, score / total_weight), 3),
                "hits": hits[:12],
                "gaps": gaps[:12],
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    all_skills = [req["skill"] for req in requirements]
    top_gaps = [skill for skill in all_skills if skill.lower() not in covered_skills][:8]
    coverage = round(len(covered_skills) / len(requirements), 3) if requirements else 0.0
    return {"scores": scored, "coverage": coverage, "top_gaps": top_gaps}


def _package_corpus(package: Mapping[str, Any]) -> str:
    parts: list[str] = [
        str(package.get("title") or ""),
        str(package.get("summary") or ""),
        str(package.get("org") or ""),
        str(package.get("role") or ""),
        " ".join(str(item) for item in (package.get("tech_stack") or [])),
        " ".join(str(item) for item in (package.get("tags") or [])),
    ]
    for variant in package.get("variants") or []:
        parts.append(str(variant.get("text") or ""))
    return " ".join(parts).lower()


def _package_hits(package: Mapping[str, Any], corpus: str, req: Mapping[str, Any]) -> bool:
    skill = str(req.get("skill") or "").strip()
    if not skill:
        return False
    lowered = skill.lower()
    if lowered in corpus:
        return True
    tokens = skills_mod.derive_tokens(skill) or {skills_mod.normalize(skill)}
    for token in tokens:
        if token and token in corpus:
            return True
        aliases = skills_mod.SKILL_ALIASES.get(token) or ()
        for alias in aliases:
            if alias and alias.lower() in corpus:
                return True
    return False


#: 归一化时丢弃的「技能前置动词/程度词」——「熟练掌握 SQL」要与「SQL」等价
_SKILL_FILLER_RE = re.compile(
    r"^(?:熟练|熟悉|掌握|精通|了解|具备|拥有|良好的?|较强的?|扎实的?|丰富的?"
    r"|能够|会|使用|运用|开展|进行|能力|经验|相关|背景|者|优先|等)+"
)
_SKILL_SPLIT_RE = re.compile(r"[、,，;；/／|｜和与及]|(?:\band\b)")
#: 归一化后要去掉的「尾部修饰」——「A/B 测试经验」要与「A/B 测试」等价
_SKILL_SUFFIX_RE = re.compile(r"(?:经验|能力|背景|要求|优先|者|等|相关|方面)+$")


def _norm(text: object) -> str:
    """匹配用归一化：全角转半角、小写、只留字母数字与汉字。

    这一步让「A/B 测试」与「AB 测试」、「SQL」与「sql」、「Ｐｙｔｈｏｎ」与
    「python」相等——它们说的是同一件事，不该因为写法差异判成「没有」。
    """
    raw = unicodedata.normalize("NFKC", str(text or ""))
    kept = [ch for ch in raw.lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff"]
    return "".join(kept)


def _needles(skill: str) -> list[str]:
    """把一条 requirement 的 skill 文本拆成可匹配的针（归一化后）。"""
    out: list[str] = []

    def push(value: str) -> None:
        needle = _norm(value)
        stripped = _SKILL_SUFFIX_RE.sub("", needle)
        for candidate in (needle, stripped):
            if len(candidate) >= 2 and candidate not in out:
                out.append(candidate)

    push(skill)
    for token in skills_mod.derive_tokens(skill) or []:
        push(token)
        for alias in skills_mod.SKILL_ALIASES.get(token) or ():
            push(alias)
    for piece in _SKILL_SPLIT_RE.split(str(skill or "")):
        piece = _SKILL_FILLER_RE.sub("", piece.strip())
        push(piece)
    return out


QUOTE_MIN_CHARS = 8
"""证据引文的最短长度（captain m06463 ②：引不到 ≥8 字原文就不许算命中）。"""

_SEGMENT_RE = re.compile(r"[，,。；;、\n\r]+")


def _quote_from(text: str, needles: Sequence[str], *, limit: int = 200) -> str | None:
    """从**原文**里切出含命中词的片段（≥ ``QUOTE_MIN_CHARS`` 字），切不出就返回 None。

    为什么按标点切片而不是按字符位置：``_norm`` 会把标点与空格全部丢掉，
    归一化串的下标回不到原文。按「、，；」切成小段既保证引文读起来是句人话，
    也保证引文里确实含那个命中词——这样 ``evidence_hint`` 才可被人工核对。
    """
    raw = str(text or "").strip()
    if not raw:
        return None
    wanted = [needle for needle in needles if needle]
    if not wanted:
        return None
    for segment in _SEGMENT_RE.split(raw):
        piece = segment.strip(" 　\t")
        if len(piece) < QUOTE_MIN_CHARS:
            continue
        plain = _norm(piece)
        if any(needle in plain for needle in wanted):
            return piece[:limit]
    # 整段都没标点（常见于技能行）：整行既长又含命中词，就整行引
    if len(raw) >= QUOTE_MIN_CHARS:
        plain = _norm(raw)
        if any(needle in plain for needle in wanted):
            return raw[:limit]
    return None


def _package_sources(package: Mapping[str, Any]) -> list[str]:
    """一个经历包的**全部**可引用原文（zh 与 en 变体都算）。

    只扫 zh 会漏掉用户专门写好的英文表述；title/org/role/tech_stack 里也常直接
    写着技能名（「数据处理实习生」含「数据处理」），这些同样是人能核对的证据。
    """
    sources: list[str] = [
        str(package.get("title") or ""),
        str(package.get("org") or ""),
        str(package.get("role") or ""),
        str(package.get("summary") or ""),
        "、".join(str(item) for item in (package.get("tech_stack") or [])),
        "、".join(str(item) for item in (package.get("tags") or [])),
    ]
    for variant in package.get("variants") or []:
        sources.append(str(variant.get("text") or ""))
    return [source for source in sources if source.strip()]


def _hit_snippet(package: Mapping[str, Any], needles: Sequence[str], *, limit: int = 200) -> str | None:
    """在命中的经历包里找一段原文引文（可溯源、含命中词、≥8 字）。"""
    for source in _package_sources(package):
        quote = _quote_from(source, needles, limit=limit)
        if quote:
            return quote
    return None


def link_requirements(
    requirements: Sequence[Mapping[str, Any]],
    packages: Sequence[Mapping[str, Any]] = (),
    *,
    profile: Mapping[str, Any] | None = None,
    warnings: list[dict[str, Any]] | None = None,
) -> int:
    """给每条 requirement 填 ``matched_package_ids``，并否决「明明有证据却说没有」。

    这是**本地计算**，不采信模型自述：模型看不到仓库时会写「档案未体现 A/B 测试
    经验」，而用户仓库里就有一个 A/B 测试项目——把用户判成「没有」，是全项目
    最坏的一类错误（会让人低估自己）。

    证据有两处：仓库经历要点（→ ``matched_package_ids``）与档案技能行
    （→ ``matched_profile_evidence``）。任一处命中都不许写 ``missing``。

    规则（captain 2026-10-23 工单）：
    1. 命中即填该包 id 列表；
    2. 命中但模型给 ``missing`` → 本地改写为 ``partial``，发
       ``LLM_STATUS_OVERRIDDEN{requirement,from,to,matched_package_ids,evidence_source}``，
       ``candidate_status_source`` 记 ``local_override``；
    3. 命中且 ``raw_quote`` 为空 → 用命中原文补引文（可溯源）。
    """
    # 每条证据都带原文源：corpus 只用来判断「有没有」，sources 用来切引文
    corpora: list[tuple[Mapping[str, Any], str, list[str]]] = []
    for package in packages or ():
        if not package.get("id"):
            continue
        corpus = _norm(_package_corpus(package))
        if corpus:
            corpora.append((package, corpus, _package_sources(package)))

    # 三源证据：skills_json 行 / 档案字段（degree、major）。用 kind 记住来自哪一源，
    # 后面要按 §6.2.4 写成 {source, ref_id, quote}，用户才能点回原文核对。
    skill_lines: list[tuple[str, str, str, str]] = []  # (kind, field, 原文, 归一化)
    if profile:
        for row in profile.get("skills") or []:
            line = str(row.get("line") or "").strip() if isinstance(row, Mapping) else str(row or "").strip()
            if line:
                skill_lines.append(("skills_json", "line", line, _norm(line)))
        # 档案结构化字段同样是证据源（§6.2.4 的 profile）：届别、院校层次这类结论
        # 若只靠模型自证，用户点开界面看不到任何依据——真库曾出现 3/6 行
        # 「判 satisfied/partial 但 matched_evidence 为空」，正是 I26 要堵的洞。
        for field_name in (
            "school",
            "school_tier",
            "grad_year",
            "degree",
            "major",
            "city",
            "available_date",
        ):
            text = str(profile.get(field_name) or "").strip()
            if text:
                skill_lines.append(("profile", field_name, text, _norm(text)))

    overridden = 0
    for req in requirements or ():
        requires = _needles(str(req.get("skill") or ""))
        if not requires:
            req["matched_package_ids"] = []
            continue
        hits: list[str] = []
        quote: str | None = None
        evidence: list[dict[str, Any]] = []
        for package, corpus, sources in corpora:
            if not any(needle in corpus for needle in requires):
                continue
            candidate_quote = None
            for source in sources:
                candidate_quote = _quote_from(source, requires)
                if candidate_quote:
                    break
            if not candidate_quote:
                # 命中词出现过但切不出 ≥8 字原文 ⇒ 不算命中（captain m06463 ②）
                continue
            hits.append(str(package["id"]))
            evidence.append(
                {
                    "source": "package",
                    "ref_id": str(package["id"]),
                    "quote": candidate_quote,
                    "package_title": str(package.get("title") or ""),
                }
            )
            if quote is None:
                quote = candidate_quote
        req["matched_package_ids"] = hits

        profile_hits: list[str] = []
        profile_quote: str | None = None
        for kind, field_name, line, blob in skill_lines:
            if not any(needle in blob for needle in requires):
                continue
            line_quote = _quote_from(line, requires)
            if not line_quote and kind == "profile":
                # 档案字段常是短值（「985」「2028」），按 §6.2.4 允许
                # quote 等于该字段值本身——短值不该因此丢掉"可核对"的资格。
                line_quote = line
            if not line_quote:
                continue
            profile_hits.append(line)
            evidence.append(
                {
                    "source": kind,
                    "ref_id": None,
                    "quote": line_quote,
                    "field": field_name,
                }
            )
            if profile_quote is None:
                profile_quote = line_quote
        if profile_hits:
            req["matched_profile_evidence"] = profile_hits[:3]
        if not hits and not profile_hits:
            # 派生证据：两条本地确定性规则（不调模型、可复算）。它们**不是原文引用**
            # ——原文里并没有「985」「2027」这几个字，所以带 derived=True 与 rule，
            # 界面必须显示成「推算」而不是「原文命中」。
            for derived in (
                _derived_school_tier_evidence(req, profile),
                _derived_grad_year_evidence(req, profile),
            ):
                if derived is None:
                    continue
                evidence.append(derived)
                profile_hits.append(str(derived.get("quote") or ""))
                if profile_quote is None:
                    profile_quote = str(derived.get("quote") or "")
        req["matched_evidence"] = evidence

        if quote is None and profile_quote is not None:
            quote = profile_quote
        if quote:
            req["evidence_hint"] = quote[:200]
        if not hits and not profile_hits:
            # 「没匹配到」的唯一定义：两个数组都空（§6.2.4 / I22）。此时保留模型结论
            # （通常是 missing），绝不为了好看改判。
            req["matched_evidence"] = []
            continue
        status = str(req.get("candidate_status") or "")
        if status == "missing":
            req["candidate_status"] = "partial"
            req["candidate_status_source"] = "local_override"
            overridden += 1
            if warnings is not None:
                warnings.append(
                    {
                        "code": "LLM_STATUS_OVERRIDDEN",
                        "severity": "warn",
                        "message": (
                            f"「{req.get('skill')}」被判为缺失，但仓库/档案里有命中该要求的证据，已改为部分满足"
                        ),
                        "details": {
                            "requirement": str(req.get("skill") or ""),
                            "from": "missing",
                            "to": "partial",
                            "matched_package_ids": hits,
                            "evidence_source": (
                                "packages" if hits else "profile.skills"
                            ),
                            "evidence_hint": (quote or "")[:80],
                        },
                    }
                )
        if not req.get("raw_quote") and quote:
            req["raw_quote"] = quote[:200]
        _enforce_evidence_backing(req, warnings)
    return overridden


_YEAR_IN_TEXT_RE = re.compile(r"(20\d{2})\s*届|(20\d{2})\s*年?\s*(及以后|以后|之后|起)")
_TIER_NEEDLES = ("985", "211", "双一流", "c9", "普通本科", "海外")


def _derived_school_tier_evidence(
    req: Mapping[str, Any], profile: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    """院校层次：校名 → 层次（本地小表 + 用户手填优先）。

    为什么需要它：JD 写「985/211 优先」时，档案里存的是校名而不是「985」三个字，
    只做原文子串匹配必然空手而归；但系统其实**知道**示例大学是 985（`tier_from_school_name`
    与竞争力判断用的是同一张表），不拿它当证据，用户就会看到「满足，但没有任何依据」。
    """
    if not profile:
        return None
    text = _norm(str(req.get("skill") or "") + " " + str(req.get("category") or ""))
    if not any(needle in text for needle in _TIER_NEEDLES):
        return None
    tier = str(profile.get("school_tier") or "").strip()
    rule = "手工填写 school_tier"
    if not tier:
        school = str(profile.get("school") or profile.get("school_zh") or "").strip()
        if not school:
            return None
        try:
            tier = str(tier_from_school_name(school) or "").strip()
        except Exception:  # 识别失败不该让整条分析崩
            tier = ""
        rule = f"校名「{school}」→ 本地层次表"
    if not tier:
        return None
    if not any(needle in _norm(tier) for needle in _TIER_NEEDLES):
        return None
    return {
        "source": "profile",
        "ref_id": None,
        "quote": tier,
        "field": "school_tier",
        "derived": True,
        "rule": rule,
    }


def _derived_grad_year_evidence(
    req: Mapping[str, Any], profile: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    """届别年份：`grad_year` ≥ JD 要求年份即满足（2028 届 满足「2027 届及以后」）。

    数字比较不能靠子串匹配：JD 写「2027 届」而档案写「2028」，子串永远不命中，
    于是正确的 satisfied 会被冤成「无依据」。
    """
    if not profile:
        return None
    skill = str(req.get("skill") or "")
    match = _YEAR_IN_TEXT_RE.search(skill)
    if not match:
        return None
    wanted = int(match.group(1) or match.group(2))
    grad = str(profile.get("grad_year") or "").strip()
    if not grad.isdigit():
        return None
    if int(grad) < wanted:
        return None
    return {
        "source": "profile",
        "ref_id": None,
        "quote": grad,
        "field": "grad_year",
        "derived": True,
        "rule": f"grad_year {grad} ≥ JD 要求 {wanted}",
    }


def _enforce_evidence_backing(req: dict[str, Any], warnings: list[dict[str, Any]] | None
) -> None:
    """I26：说命中就得拿得出凭据。

    两个方向都要管：
    * ``satisfied`` 却零证据 → 降为 ``partial`` 并告警（人判的行不降，尊重手工结论）；
    * ``partial`` 却零证据 → 保留结论但告警，让界面显示「仅模型判断，未找到依据」。

    为什么不能只告警不降级：``satisfied`` 是「我满足这条」，进了组装就会被当成
    已具备能力去写简历；没有凭据的 satisfied 等于让模型替候选人背书。
    """
    source = str(req.get("candidate_status_source") or "")
    if source == "manual":
        return
    status = str(req.get("candidate_status") or "")
    if status not in ("satisfied", "partial"):
        return
    has_evidence = bool(req.get("matched_package_ids") or req.get("matched_evidence"))
    if has_evidence:
        return
    from_status = status
    if status == "satisfied":
        req["candidate_status"] = "partial"
        req["candidate_status_source"] = "local_override"
        action = "downgraded"
    else:
        action = "flagged"
    if warnings is not None:
        warnings.append(
            {
                "code": "STATUS_WITHOUT_EVIDENCE",
                "severity": "warn",
                "message": (
                    f"「{req.get('skill')}」被判为{('满足' if from_status == 'satisfied' else '部分满足')}，"
                    "但在仓库与档案里找不到可核对的依据"
                    + ("，已降为部分满足" if action == "downgraded" else "，请人工确认")
                ),
                "details": {
                    "requirement": str(req.get("skill") or ""),
                    "from": from_status,
                    "to": str(req.get("candidate_status") or ""),
                    "action": action,
                    "evidence_count": 0,
                },
            }
        )


def keyword_list(text: str, *, limit: int = 12) -> list[str]:
    """高频业务关键词（本地、确定性），用于公司画像与 JD 摘要。"""
    stop = {"以及", "进行", "相关", "能够", "负责", "参与", "协助", "支持", "完成", "以上", "优先", "要求"}
    counts: dict[str, int] = {}
    for token in re.findall(r"[\u4e00-\u9fff]{2,6}", str(text or "")):
        if token in stop:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, count in ranked if count >= 2][:limit]
