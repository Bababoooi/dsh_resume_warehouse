"""Pydantic v2 请求模型与校验工具。

约定：
* 请求体解析失败 → ``ApiError("VALIDATION_ERROR", details={"fields":[{field,rule,message}]})``；
* 部分更新用 ``model_fields_set`` 区分「未提供」与「显式 null」；
* 所有枚举与 CHECK 约束保持与 ``app/schema.sql`` 一致（改动需同时改两处）。
"""

from __future__ import annotations

import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from . import config as config_mod
from .errors import validation_error

# --------------------------------------------------------------------------------------
# 枚举字面量（与 schema.sql 对应）
# --------------------------------------------------------------------------------------

PackageKind = Literal["project", "internship", "education", "award", "activity", "custom"]
PackageStatus = Literal["draft", "ready", "archived"]
PackageSource = Literal["authored", "imported", "llm_assisted"]
BulletTone = Literal["impact", "technical", "leadership", "concise", "ats"]
Lang = Literal["zh", "en"]
Degree = Literal["本科", "硕士", "博士", "大专", "其他"]
AttachmentKind = Literal["resume_source", "photo", "evidence", "export", "other"]
Privacy = Literal["private", "shareable"]
BlockType = Literal["header", "summary", "section", "entry", "bullet_list", "skills", "awards", "footer", "freeform"]
SlotType = Literal["text", "longtext", "date_range", "taglist", "url", "image", "computed"]
JdCategory = Literal["hard", "soft", "domain", "tool", "language", "certificate"]
JdPriority = Literal["must", "should", "nice"]
LlmPurpose = Literal["jd_analyze", "bullets_generate", "company_profile", "build_suggest", "summary_polish"]
ProviderName = Literal["deepseek", "openai_compatible", "ollama", "off"]

PHONE_RE = re.compile(r"^\+?[0-9\- ]{7,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
SLOT_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
DATE_RE = re.compile(r"^(\d{4})(-(\d{2}))?$")  # YYYY 或 YYYY-MM

# --------------------------------------------------------------------------------------
# 基类与错误格式化
# --------------------------------------------------------------------------------------


class StrictModel(BaseModel):
    """禁止未知字段（契约变更必须显式），并允许用字段别名对外。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=False)


_RULE_BY_ERROR_TYPE = {
    "missing": "required",
    "string_too_short": "min_length",
    "string_too_long": "max_length",
    "string_pattern_mismatch": "pattern",
    "literal_error": "enum",
    "enum": "enum",
    "int_parsing": "type",
    "float_parsing": "type",
    "bool_parsing": "type",
    "string_type": "type",
    "model_type": "type",
    "greater_than_equal": "min",
    "less_than_equal": "max",
    "value_error": "value",
    "list_type": "type",
}


def _field_path(error: Mapping[str, Any]) -> str:
    loc = [str(part) for part in error.get("loc", ()) if part not in ("body", "query", "path")]
    return ".".join(loc) or "(body)"


def format_validation_error(exc: PydanticValidationError) -> Any:
    """Pydantic 错误 → 契约 ``VALIDATION_ERROR``。"""
    fields: list[dict[str, str]] = []
    for error in exc.errors():
        etype = str(error.get("type", "value_error"))
        fields.append(
            {
                "field": _field_path(error),
                "rule": _RULE_BY_ERROR_TYPE.get(etype, etype),
                "message": config_mod.redact(str(error.get("msg", "invalid"))),
            }
        )
    return validation_error(fields)


def parse_body(model: type[BaseModel], payload: Any) -> Any:
    """统一入口：解析失败抛 ApiError，而不是 Flask 500。"""
    try:
        return model.model_validate(payload)
    except PydanticValidationError as exc:
        raise format_validation_error(exc) from None


# --------------------------------------------------------------------------------------
# UserProfile
# --------------------------------------------------------------------------------------


class SkillLine(StrictModel):
    """职业技能的一行：``line`` 是唯一渲染源（逐字原文），``tokens`` 只给匹配用。

    用户 2026-10-23 裁决：简历上保持整句原文，**禁止**渲染成 tag 块/标签云；
    tokens 是派生索引，允许重建、缺失时匹配降级为整句子串匹配。
    """

    line: str = Field(min_length=1, max_length=400)
    category: str | None = Field(default=None, max_length=40)
    tokens: list[str] = Field(default_factory=list)
    order: int | None = Field(default=None, ge=0, le=9999)


class PhotoConfirmIn(StrictModel):
    """PUT /profile/photo：确认使用某张**已入库**的照片（导入候选或此前上传的）。"""

    attachment_id: str | None = Field(default=None, max_length=64)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)

    @model_validator(mode="after")
    def _exactly_one(self) -> "PhotoConfirmIn":
        if bool(self.attachment_id) == bool(self.sha256):
            raise ValueError("attachment_id 与 sha256 必须且只能提供一个")
        return self


class EducationFactsIn(StrictModel):
    """PUT /profile/education-facts：教育段补充行（GPA / 主修课程），空数组 = 清空。"""

    lines: list[str] = Field(default_factory=list, max_length=12)


class ProfilePatch(StrictModel):
    """PUT /profile：全部可选；显式 null 表示清空（name_zh 不可清空）。"""

    name_zh: str | None = Field(default=None, min_length=1, max_length=40)
    name_en: str | None = Field(default=None, max_length=80)
    school_zh: str | None = Field(default=None, max_length=80)
    school_en: str | None = Field(default=None, max_length=120)
    degree: Degree | None = None
    major: str | None = Field(default=None, max_length=80)
    grad_year: int | None = Field(default=None, ge=1900, le=2100)
    phone: str | None = None
    email: str | None = None
    city: str | None = Field(default=None, max_length=40)
    available_date: str | None = Field(default=None, max_length=20)
    available_note: str | None = Field(default=None, max_length=200)
    links: list[dict[str, str]] | None = None
    extra: dict[str, Any] | None = None
    skills: list[SkillLine] | None = None
    # 院校层次：用户手填优先（推断不出来时就是靠它纠正，见 services/jd_analysis.py）
    school_tier: Literal["C9", "985", "211", "双一流", "普通本科", "海外", "其他"] | None = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not PHONE_RE.match(value):
            raise ValueError("手机号格式应为可选的 + 与 7-20 位数字/连字符/空格")
        return value

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not EMAIL_RE.match(value):
            raise ValueError("邮箱格式不合法")
        return value

    @field_validator("name_zh", "name_en", "school_zh", "school_en", "major", "city", "available_date", "available_note")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return None if value == "" else value


# --------------------------------------------------------------------------------------
# Package / Variant
# --------------------------------------------------------------------------------------


class PackageIn(StrictModel):
    title: str = Field(min_length=1, max_length=120)
    kind: PackageKind
    org: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=120)
    start_date: str | None = Field(default=None, max_length=10)
    end_date: str | None = Field(default=None, max_length=10)
    is_current: bool = False
    location: str | None = Field(default=None, max_length=80)
    summary: str | None = Field(default=None, max_length=600)
    tech_stack: list[str] | None = None
    tags: list[str] | None = None
    #: 契约 §4 的 outcomes 是 ``[{metric, from, to}]``；也接受纯字符串（老数据/手填）
    outcomes: list[dict[str, Any] | str] | None = None
    evidence: list[str] | None = None
    status: PackageStatus = "draft"
    source: PackageSource = "authored"
    #: 创建时一并落库的 bullet 变体（201 响应会带回来）
    variants: list["VariantIn"] | None = None

    @field_validator("start_date", "end_date")
    @classmethod
    def _date(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not DATE_RE.match(value):
            raise ValueError("日期格式应为 YYYY 或 YYYY-MM")
        return value

    @model_validator(mode="after")
    def _current_has_no_end(self) -> "PackageIn":
        if self.is_current and self.end_date:
            raise ValueError("is_current=true 时 end_date 必须为空")
        return self


class PackagePatch(PackageIn):
    """PUT /packages/{id}：语义同 ProfilePatch，未提供的字段保持不变。"""

    title: str | None = Field(default=None, min_length=1, max_length=120)  # type: ignore[assignment]
    kind: PackageKind | None = None  # type: ignore[assignment]
    is_current: bool | None = None  # type: ignore[assignment]
    status: PackageStatus | None = None  # type: ignore[assignment]
    source: PackageSource | None = None  # type: ignore[assignment]


class PackageDraftIn(StrictModel):
    """对话式打包：一段自由文本 → Package 草稿（不落库、零出网）。"""

    text: str = Field(min_length=1, max_length=8000)
    kind: PackageKind | None = None
    lang: Lang | None = None
    title: str | None = Field(default=None, max_length=120)
    org: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, max_length=120)


class GenerateVariantsIn(StrictModel):
    """POST /packages/{id}/variants/generate：必须先有 consent preview（契约 §4）。"""

    preview_id: str | None = Field(default=None, max_length=64)
    bullet_keys: list[str] = Field(default_factory=list, max_length=50)
    tones: list[BulletTone] = Field(default_factory=list, max_length=10)
    lang: Lang = "zh"
    constraints: dict[str, Any] = Field(default_factory=dict)
    expected_payload_sha256: str | None = Field(default=None, min_length=64, max_length=64)


class VariantIn(StrictModel):
    bullet_key: str = Field(min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=400)
    tone: BulletTone
    lang: Lang
    keywords: list[str] = Field(default_factory=list)
    metrics: list[dict[str, Any]] = Field(default_factory=list)
    verified: bool = False
    quality_score: float | None = Field(default=None, ge=0, le=1)


class VariantPatch(StrictModel):
    text: str | None = Field(default=None, min_length=1, max_length=400)
    tone: BulletTone | None = None
    lang: Lang | None = None
    keywords: list[str] | None = None
    metrics: list[dict[str, Any]] | None = None
    verified: bool | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)


# --------------------------------------------------------------------------------------
# Template / Block / Slot
# --------------------------------------------------------------------------------------


class BlockIn(StrictModel):
    parent_block_id: str | None = None
    order_index: int = Field(ge=0)
    block_type: BlockType
    heading: str | None = Field(default=None, max_length=80)
    bound_package_kind: PackageKind | None = None
    style: dict[str, Any] = Field(default_factory=dict)
    page_break_before: bool = False
    max_bullets: int | None = Field(default=None, ge=1, le=12)
    static_text: str | None = None
    repeat_per_package: bool = True


class SlotIn(StrictModel):
    slot_key: str
    slot_type: SlotType
    required: bool = False
    bound_field: str | None = Field(default=None, max_length=80)
    default_value: str | None = None
    max_chars: int | None = Field(default=None, ge=1, le=5000)
    pattern: str | None = None
    list_source: Literal["profile.links_json", "package.tech_stack_json", "package.tags_json"] | None = None

    @field_validator("slot_key")
    @classmethod
    def _slot_key(cls, value: str) -> str:
        if not SLOT_KEY_RE.match(value):
            raise ValueError("slot_key 需匹配 ^[a-z][a-z0-9_]{0,40}$")
        return value


# --------------------------------------------------------------------------------------
# JD / Company
# --------------------------------------------------------------------------------------


class JdIn(StrictModel):
    title: str | None = Field(default=None, max_length=120)
    company_name: str | None = Field(default=None, max_length=120)
    raw_text: str = Field(min_length=1, max_length=20000)
    source_url: str | None = Field(default=None, max_length=500)
    lang: Lang = "zh"


class RequirementIn(StrictModel):
    skill: str = Field(min_length=1, max_length=80)
    category: JdCategory
    priority: JdPriority
    weight: float = Field(default=0.5, ge=0, le=1)
    evidence_hint: str | None = Field(default=None, max_length=200)
    raw_quote: str | None = Field(default=None, max_length=300)
    source: Literal["llm", "heuristic", "manual"] = "manual"


class JdAnalyzeIn(StrictModel):
    """``method=auto`` 时：LLM 就绪就必须带 preview，否则走启发式（ANL-01/ANL-02）。"""

    method: Literal["auto", "llm", "heuristic"] = "auto"
    preview_id: str | None = None
    expected_payload_sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    company_profile_id: str | None = None


class JdMatchIn(StrictModel):
    package_ids: list[str] = Field(default_factory=list, max_length=200)


class RequirementPatch(StrictModel):
    skill: str | None = Field(default=None, min_length=1, max_length=80)
    category: JdCategory | None = None
    priority: JdPriority | None = None
    weight: float | None = Field(default=None, ge=0, le=1)
    evidence_hint: str | None = Field(default=None, max_length=200)
    raw_quote: str | None = Field(default=None, max_length=300)
    candidate_status: Literal["satisfied", "partial", "missing"] | None = None
    # 撤销人工改判：显式给 auto 才会让下一次重算覆盖它（§6.2.5 / I23）。
    candidate_status_source: Literal["auto"] | None = None


class CompanyAnalyzeIn(StrictModel):
    company_name: str = Field(min_length=1, max_length=120)
    jd_id: str | None = None
    jd_text: str | None = Field(default=None, max_length=20000)
    website: str | None = Field(default=None, max_length=500)
    fetch_url: str | None = Field(default=None, max_length=500)
    allow_fetch: bool = True
    refresh: bool = False
    method: Literal["auto", "llm", "heuristic"] = "auto"
    preview_id: str | None = None
    expected_payload_sha256: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")


class FetchIn(StrictModel):
    url: str = Field(min_length=1, max_length=500)
    use_cache: bool = True


class CompanyPatch(StrictModel):
    industry: str | None = None
    company_stage: str | None = None
    size_hint: str | None = None
    culture_signals: list[str] | None = None
    hiring_preferences: list[str] | None = None
    interview_focus: list[str] | None = None
    tone: str | None = None
    keywords: list[str] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    method: Literal["llm", "heuristic", "manual"] | None = None
    website: str | None = Field(default=None, max_length=500)
    school_preference: dict[str, Any] | None = None


# --------------------------------------------------------------------------------------
# Build / Selection
# --------------------------------------------------------------------------------------



class CompanyIn(CompanyPatch):
    company_name: str = Field(min_length=1, max_length=120)
    website: str | None = Field(default=None, max_length=500)
    school_preference: dict[str, Any] | None = None


class BuildIn(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    template_id: str
    jd_id: str | None = None
    company_profile_id: str | None = None
    position: str | None = Field(default=None, max_length=80)
    company: str | None = Field(default=None, max_length=80)
    lang: Lang = "zh"
    naming_pattern: str = "{position}-{name}-{school}"
    naming_overrides: dict[str, str] = Field(default_factory=dict)


class SelectionIn(StrictModel):
    package_id: str
    variant_ids: list[str] = Field(default_factory=list)
    order_index: int = Field(default=0, ge=0)
    overrides: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------------------
# 命名模板 / 设置 / LLM
# --------------------------------------------------------------------------------------


class NamingValidateIn(StrictModel):
    pattern: str = Field(default="", max_length=200)
    lang: Lang = "zh"
    position: str | None = None
    company: str | None = None
    overrides: dict[str, str] = Field(default_factory=dict)
    date: str | None = None


class SettingsPatch(StrictModel):
    provider: ProviderName | None = None
    base_url: str | None = Field(default=None, max_length=300)
    model: str | None = Field(default=None, max_length=120)
    model_analysis: str | None = Field(default=None, max_length=120)
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    # 只允许这四类：phone/email/id 可关（关掉也会被本机身份校验兜住），name 恒生效。
    # **不含 school**——校名按真实值发送（用户 2026-10-23 最终口径），传 school 会 422。
    auto_redact: list[Literal["phone", "email", "id", "name"]] | None = None
    naming_template: str | None = Field(default=None, max_length=200)
    default_engine: Literal["reportlab", "chrome", "docx"] | None = None
    verify_text: bool | None = None
    photo_in_export: bool | None = None
    allow_web_fetch: bool | None = None
    max_tokens_analysis: int | None = Field(default=None, ge=512, le=8192)
    max_tokens_generate: int | None = Field(default=None, ge=256, le=8192)
    ui: dict[str, Any] | None = None


class ApiKeyIn(StrictModel):
    api_key: str = Field(min_length=8, max_length=400)


class LlmSelections(StrictModel):
    package_ids: list[str] = Field(default_factory=list, max_length=50)
    variant_ids: list[str] = Field(default_factory=list, max_length=200)
    # bullets_generate（t6 变体改写）用：只把这几条事实 / 这几种语气送出去，
    # 其余经历与变体一律不读（「未选中的包与变体绝不进入 payload」）。
    bullet_keys: list[str] = Field(default_factory=list, max_length=50)
    tones: list[str] = Field(default_factory=list, max_length=10)
    lang: Lang | None = None
    include_summary: bool = True
    jd_id: str | None = None
    company_profile_id: str | None = None
    extra_instruction: str | None = Field(default=None, max_length=1000)


class LlmOptions(StrictModel):
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=64, le=8000)
    # None = 跟随 app_setting.auto_redact（默认脱敏电话/邮箱/身份证，姓名恒脱敏）。
    # 早期默认 False 会造成「用户没点开关 → 手机号原样上云」，属真实缺陷。
    auto_redact: bool | None = None


class PreviewIn(StrictModel):
    purpose: LlmPurpose
    provider_override: ProviderName | None = None
    selections: LlmSelections = Field(default_factory=LlmSelections)
    options: LlmOptions = Field(default_factory=LlmOptions)


class CompleteIn(StrictModel):
    preview_id: str
    expected_payload_sha256: str = Field(min_length=64, max_length=64)


class BulkVerifyIn(StrictModel):
    variant_ids: list[str] = Field(min_length=1, max_length=500)
    verified: bool = True
