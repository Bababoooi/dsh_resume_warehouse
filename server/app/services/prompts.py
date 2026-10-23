"""LLM 提示词模板（与调用点一一对应）。

硬约束（captain F2 实测）：只要请求体带 ``response_format={"type":"json_object"}``，
prompt 里就必须出现字面量 ``json``，否则 DeepSeek 直接 400。因此凡是 JSON 模式
的模板都显式写「以 json 返回」，并由 ``llm_client._assert_json_hint`` 本地前置校验。

隐私：模板只接收**已选中**的 Package / 变体 / 档案摘要，绝不接收
``data/imports/**`` 原文、照片、手机号与邮箱（这些在 consent 层结构上排除）。
"""

from __future__ import annotations

from typing import Any, Mapping

#: 系统提示：按 purpose 固定，不含任何用户数据
SYSTEM_PROMPTS: dict[str, str] = {
    "jd_analyze": (
        "你是资深技术招聘顾问。除 JD 外，你还会收到**候选人档案**（学校/院校、学历、专业、"
        "毕业届别、城市、到岗时间、技能行）与**仓库经历**（该候选人已保存的项目/实习要点原文）。"
        "请把职位描述拆解为结构化要求，并**逐条对照候选人现状**给出"
        "candidate_status（satisfied/partial/missing），同时评估候选人对该岗位的院校竞争力："
        "公司是否卡院校档次、候选人的学校在这个招聘池里是优势还是劣势、学历与专业是否匹配。"
        "**判定规则（硬性）**：仓库经历与档案技能行是你的首要证据。只要某条要求在这些文本里"
        "有对应证据，candidate_status 就不得写 missing，evidence_hint 必须引用那段原文的片段"
        "（例如写到「把 6527 条门店订单接入预测流程」的 A/B 测试项目，就引用它）；"
        "只有确实找不到任何对应文本时才写 missing，并在 evidence_hint 里说明「已检索档案与 N 条经历，"
        "未出现 X」。禁止以「档案未列出」为由忽略仓库里写明的事实。"
        "院校（校名）是判断竞争力的核心依据之一，必须使用，不要回避。"
        "院校（校名）是判断竞争力的核心依据之一，必须使用，不要回避。"
        "以 json 返回，字段：{title, company_name, "
        "requirements:[{skill, category, priority, weight, evidence_hint, raw_quote, candidate_status}], "
        "keywords:[], summary, "
        "competitiveness:{school_tier, school_signal, degree_fit, major_fit, experience_fit, verdict, gap_notes:[]}}。"
        "其中 school_tier 写院校档次（如 985/211/双一流/普通本科/海外院校），"
        "school_signal 用一句话说明「校名在该岗位筛选中的作用，对本人是优势还是劣势」，"
        "verdict ∈ strong|medium|weak 是该岗位竞争力总评。只输出 json，不要解释。"
    ),
    "company_profile": (
        "你是了解中国互联网与制造业招聘偏好的职业顾问。根据公司名、JD、用户笔记与**候选人档案**"
        "（含院校/学校），推理该公司的招聘偏好、面试关注点与文化信号。"
        "hiring_preferences 必须回答一条**院校偏好**：是否卡 985/211/双一流、是否偏好本地院校、"
        "是否看重第一学历；据此判断候选人的学校在该公司是加分、中性还是劣势。"
        "以 json 返回，字段：{company_name, industry, company_stage, size_hint, culture_signals:[], "
        "hiring_preferences:[], school_preference:{threshold, preferred_tiers:[], hard_filter, evidence, confidence}, "
        "interview_focus:[], tone, keywords:[], confidence}。"
        "school_preference.threshold 写门槛（如「985/211 优先，非硬卡」），preferred_tiers 写偏好的院校层次，"
        "hard_filter 表示是否硬性过滤（true/false）。不确定时把 confidence 调低，不要编造事实。只输出 json。"
    ),
    "build_suggest": (
        "你是简历组装策略专家。给定岗位要求、候选人档案（含院校/学校）与经历包（Package），"
        "请挑选最匹配的组合、排序并给出每条 bullet 的取舍理由；"
        "选包时必须把**院校信号**纳入考虑（校名是否满足该校招池的门槛、是否需要靠经历厚度补足），"
        "并在 school_signal_used 里如实标注本次是否真的用了院校信号。"
        "以 json 返回，字段：{selected:[{package_id, order, reason, variant_ids}], "
        "dropped:[{package_id, reason}], notes:[], "
        "coverage:{must:[], should:[], missing:[], advantage:[]}, "
        "competitiveness_summary, school_signal_used}。"
        "coverage.advantage 写校名/学历带来的真实优势（如「985 硕士满足硬门槛」）。只输出 json。"
    ),
    "bullets_generate": (
        "你是简历措辞教练。基于用户提供的真实经历要点改写 bullet：保留事实与量化指标，"
        "不虚构任何数字或职责；每条不超过 60 字（英文 30 词）。以 json 返回，字段："
        "{variants:[{bullet_key, tone, lang, text, keywords:[], metrics:[]}]}。只输出 json。"
    ),
    "summary_polish": (
        "你是中文简历润色编辑。把用户给的自我评价压缩到 2-3 句、去掉形容词堆砌、保留可验证事实。"
        "直接输出润色后的纯文本，不要 json、不要解释。"
    ),
}

#: 每个调用点允许出现在 payload 里的数据种类（用于文档与静态检查）
#:
#: ``profile`` = 候选人档案段，**只允许** {school, degree, major, grad_year, city,
#: available_date, skills}（``ProfileRepo.llm_brief`` 的固定输出）。姓名、电话、邮箱、
#: 照片结构上不在该段里，且 ``services/privacy.assert_no_identity`` 在出网前二次拦截。
#: ``packages`` = 仓库里已就绪的经历要点段（JD 分析用）：只有标题/单位/职位/时间/要点
#: 原文，**不含** 变体 id、tokens 或任何附件字节。带上它是为了避免「仓库里有 A/B 测试
#: 项目，模型却说档案未体现」这类把用户判空的错误。
#: 校名按真实值发送：它是判断竞争力的核心依据（用户 2026-10-23 强调）。
ALLOWED_SOURCES: dict[str, tuple[str, ...]] = {
    "jd_analyze": ("system_prompt", "jd_text", "company_note", "user_instruction", "profile", "packages"),
    "company_profile": ("system_prompt", "jd_text", "company_note", "user_instruction", "profile"),
    "build_suggest": ("system_prompt", "package", "variant", "jd_text", "user_instruction", "profile"),
    "bullets_generate": ("system_prompt", "package", "variant", "user_instruction", "profile"),
    "summary_polish": ("system_prompt", "package", "user_instruction", "profile"),
}


def system_prompt(purpose: str) -> str:
    prompt = SYSTEM_PROMPTS.get(purpose)
    if prompt is None:
        raise KeyError(f"未知 purpose={purpose!r}，没有对应的系统提示词")
    return prompt


def requires_json(purpose: str) -> bool:
    return purpose != "summary_polish"


def user_instruction(purpose: str) -> str:
    base = {
        "jd_analyze": "请按系统提示拆解下面这段 JD，输出 json。",
        "company_profile": "请按系统提示推理这家公司的招聘偏好，输出 json。",
        "build_suggest": "请按系统提示给出组装建议，输出 json。",
        "bullets_generate": "请按系统提示改写下面的经历要点，输出 json。",
        "summary_polish": "请按系统提示润色下面这段自我评价，直接输出正文。",
    }
    return base.get(purpose, "请按系统提示完成任务。")


def _render_item(item: Any) -> str:
    """列表项渲染：纯文本原样；经历条目压成一行（标题 · 单位 · 职位 … 要点）。"""
    if not isinstance(item, Mapping):
        return str(item)
    head = " · ".join(
        str(item.get(key) or "").strip()
        for key in ("title", "org", "role", "period")
        if str(item.get(key) or "").strip()
    )
    bullets = item.get("bullets") or item.get("lines") or []
    body = "；".join(str(part).strip() for part in bullets if str(part or "").strip())
    if head and body:
        return f"{head}：{body}"
    return head or body


def render_user_content(purpose: str, sections: Mapping[str, Any]) -> str:
    """把已脱敏的结构化片段拼成用户消息正文（确定性顺序，便于 sha256 复算）。"""
    lines: list[str] = [user_instruction(purpose), ""]
    for title, body in sections.items():
        if body in (None, "", [], {}):
            continue
        lines.append(f"## {title}")
        if isinstance(body, str):
            lines.append(body)
        elif isinstance(body, list):
            for item in body:
                lines.append(f"- {_render_item(item)}")
        elif isinstance(body, Mapping):
            for key, value in body.items():
                if isinstance(value, list):
                    lines.append(f"- {key}: " + "; ".join(str(v) for v in value))
                elif value not in (None, ""):
                    lines.append(f"- {key}: {value}")
        lines.append("")
    return "\n".join(lines).strip()
