"""Provider 常量表与调用点→模型路由（唯一允许出现模型名的位置）。

为什么要集中：任务书要求「双模型路由」——对话式打包/措辞改写用 ``LLM_MODEL``，
JD 解析/公司偏好/匹配打分/组装策略用 ``LLM_MODEL_ANALYSIS``。模型名一旦散落
在业务代码里，切换 provider 时必然漏改。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .. import config as config_mod

Purpose = Literal["jd_analyze", "bullets_generate", "company_profile", "build_suggest", "summary_polish"]
Tier = Literal["chat", "analysis"]

#: 三种 provider 的默认 base_url 与名称（供 UI 提示与 doctor 使用）
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "label": "DeepSeek", "requires_key": "yes"},
    "openai_compatible": {"base_url": "", "label": "OpenAI 兼容", "requires_key": "yes"},
    "ollama": {"base_url": "http://127.0.0.1:11434/v1", "label": "本地 Ollama", "requires_key": "no"},
    "off": {"base_url": "", "label": "已关闭", "requires_key": "no"},
}


@dataclass(frozen=True)
class PurposeSpec:
    """一个调用点的完整策略：模型档位、是否 JSON、采样参数、token 预算。"""

    purpose: Purpose
    tier: Tier
    json_mode: bool
    temperature: float
    max_tokens: int
    #: 该调用点 prompt 必须包含的字面量（DeepSeek 对 json_object 的硬前置条件）
    prompt_must_contain: str | None = None


#: 调用点 → 策略。**新增调用点必须在这里登记**，否则 runs 会 500。
PURPOSE_SPECS: dict[str, PurposeSpec] = {
    # 分析链路（deepseek-reasoner）：JD 拆解、公司偏好、匹配打分、组装策略
    "jd_analyze": PurposeSpec("jd_analyze", "analysis", True, 0.2, 4096, "json"),
    "company_profile": PurposeSpec("company_profile", "analysis", True, 0.3, 3072, "json"),
    "build_suggest": PurposeSpec("build_suggest", "analysis", True, 0.2, 4096, "json"),
    # 对话链路（deepseek-chat）：措辞改写、摘要润色
    "bullets_generate": PurposeSpec("bullets_generate", "chat", True, 0.7, 3072, "json"),
    "summary_polish": PurposeSpec("summary_polish", "chat", False, 0.6, 1024, None),
}

#: 阶位 → 配置字段名（不要在别处硬编码 LLM_MODEL 的读取）
TIER_FIELDS: dict[str, str] = {"chat": "llm_model", "analysis": "llm_model_analysis"}


@dataclass(frozen=True)
class Route:
    purpose: str
    tier: Tier
    provider: str
    base_url: str
    model: str
    endpoint_host: str
    json_mode: bool
    temperature: float
    max_tokens: int

    @property
    def chat_url(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    @property
    def models_url(self) -> str:
        return self.base_url.rstrip("/") + "/models"

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "purpose": self.purpose,
            "tier": self.tier,
            "provider": self.provider,
            "model": self.model,
            "endpoint_host": self.endpoint_host,
            "json_mode": self.json_mode,
        }


def spec_for(purpose: str) -> PurposeSpec:
    spec = PURPOSE_SPECS.get(purpose)
    if spec is None:
        raise KeyError(f"未知 purpose={purpose!r}；已登记：{sorted(PURPOSE_SPECS)}")
    return spec


def resolve_route(
    purpose: str,
    cfg: config_mod.Config,
    *,
    provider_override: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Route:
    """按调用点选模型与 endpoint。provider_override 只换通道，不换模型档位语义。"""
    spec = spec_for(purpose)
    provider = (provider_override or cfg.llm_provider or "deepseek").strip()
    base_url = cfg.llm_base_url or PROVIDER_PRESETS.get(provider, {}).get("base_url", "")
    model = getattr(cfg, TIER_FIELDS[spec.tier], None) or cfg.llm_model
    if provider == "ollama" and not base_url:
        base_url = PROVIDER_PRESETS["ollama"]["base_url"]
    return Route(
        purpose=purpose,
        tier=spec.tier,
        provider=provider,
        base_url=base_url,
        model=model,
        endpoint_host=config_mod.host_of(base_url),
        json_mode=spec.json_mode,
        temperature=spec.temperature if temperature is None else temperature,
        max_tokens=max(spec.max_tokens, 2048) if max_tokens is None else max_tokens,
    )
