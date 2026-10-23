"""LLM 适配层：OpenAI 兼容协议 + 重试 + JSON 解析降级 + 截断识别。

**本项目唯一允许发起外部 HTTP 的模块**（ARCHITECTURE §5 / AC-PRIV-10）。

实测结论（captain 2026-10 探测，优先级高于 planner 的保守假设）：
* F1 DeepSeek 偶发 TLS 握手抖动（``ConnectError`` / ``UNEXPECTED_EOF_WHILE_READING``），
  没有 HTTP 状态码；必须把**连接级异常**纳入重试，且错误归类为「网络不可达」，
  绝不能报成「key 无效」。
* F2 ``response_format=json_object`` 要求 prompt 中出现字面量 ``json``，否则服务端 400。
  这里做本地前置校验，直接暴露开发者错误而不是浪费一次请求。
* F3 ``deepseek-reasoner`` 支持 json_object；仍保留「正文抽 JSON → schema 校验」降级链。
* F4 reasoner 会把 ``max_tokens`` 烧在推理上：``finish_reason=length`` 且正文为空
  是独立的截断错误，绝不当作成功写库。
"""

from __future__ import annotations

import json
import logging
import re
import ssl
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import httpx

from .. import config as config_mod
from ..errors import ApiError
from . import egress_guard

log = logging.getLogger("app.llm")

#: 可重试的 HTTP 状态码（服务端明确失败）
RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
#: HTTP 层重试上限（契约 §10：同一预览最多 1 次，避免重复计费/重复生成）。
#: 连接级异常不受此限，用满 LLM_MAX_RETRIES（F1）。
HTTP_RETRY_CAP = 1
#: 连接级异常（TLS 抖动、连接被重置、读超时前后的断流）
RETRY_EXCEPTIONS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
    httpx.ReadTimeout,
    httpx.PoolTimeout,
    ssl.SSLError,
    ConnectionResetError,
)


@dataclass
class Timeouts:
    """连接/读取/总预算。

    ``connect_s`` 曾是 5 秒，实测在部分网络下 **TLS 握手本身就要 8.6–9.8 秒**
    （curl 到 ``https://api.deepseek.com/v1/models`` 的 total 也在 8–9 秒量级），于是每次调用
    都在 5 秒处被自己掐断，重试三次全灭、表现为 ``LLM_TIMEOUT reason=ConnectTimeout`` ——
    用户看到的是「AI 一直失败」，而端点其实只是握手慢。httpx 的 connect 预算覆盖 TCP+TLS，
    所以这里给到 20 秒（仍受总预算约束），把「慢」与「不可达」区分开。
    """

    connect_s: float = 20.0
    read_s: float = 60.0
    total_s: float = 90.0

    @classmethod
    def from_config(cls, cfg: config_mod.Config) -> "Timeouts":
        read = float(cfg.llm_timeout_seconds or 60)
        return cls(connect_s=min(20.0, read), read_s=read, total_s=read)

    def as_httpx(self) -> httpx.Timeout:
        return httpx.Timeout(self.total_s, connect=self.connect_s, read=self.read_s, write=self.read_s)

    def as_dict(self) -> dict[str, float]:
        return {"connect_s": self.connect_s, "read_s": self.read_s, "total_s": self.total_s}


@dataclass
class LlmResult:
    ok: bool
    raw_text: str
    parsed: Any
    model: str
    provider: str
    endpoint_host: str
    latency_ms: int
    finish_reason: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    # 警告是结构化对象（code/severity/message/details），不是一句人话：
    # 前端与验收脚本都要能按 code 与 severity 判定，而不是字符串匹配。
    warnings: list[dict[str, Any]] = field(default_factory=list)
    attempts: int = 1
    http_status: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "raw_text": self.raw_text,
            "parsed": self.parsed,
            "model": self.model,
            "provider": self.provider,
            "endpoint_host": self.endpoint_host,
            "latency_ms": self.latency_ms,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "warnings": self.warnings,
            "attempts": self.attempts,
        }


# --------------------------------------------------------------------------------------
# JSON 提取与校验
# --------------------------------------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> tuple[Any, str | None]:
    """从模型正文里尽力抽 JSON，返回 (obj, error_reason)。

    顺序：整体 ``json.loads`` → 去 ``` 围栏 → 截取首个 ``{`` 到末个 ``}``。
    """
    if text is None:
        return None, "empty_text"
    candidate = text.strip()
    if not candidate:
        return None, "empty_text"
    for attempt in _candidates(candidate):
        try:
            return json.loads(attempt), None
        except (ValueError, TypeError):
            continue
    return None, "unparsable_json"


def _candidates(text: str):
    yield text
    fenced = _FENCE_RE.search(text)
    if fenced:
        yield fenced.group(1).strip()
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        yield text[first : last + 1]
    first_bracket = text.find("[")
    last_bracket = text.rfind("]")
    if first_bracket != -1 and last_bracket > first_bracket:
        yield text[first_bracket : last_bracket + 1]


def validate_schema(obj: Any, validator: Callable[[Any], Any] | None, *, purpose: str) -> tuple[Any, list[dict[str, str]]]:
    """schema 校验失败**不**抛错：返回 (None, warning)，让上游决定降级。"""
    if validator is None:
        return obj, []
    try:
        return validator(obj), []
    except Exception as exc:  # noqa: BLE001 - pydantic/自定义校验都走这里
        return None, [
            {
                "code": "LLM_JSON_UNPARSABLE",
                "message": f"返回结构不符合 {purpose} 的 schema：{str(exc)[:200]}",
            }
        ]


# --------------------------------------------------------------------------------------
# 客户端
# --------------------------------------------------------------------------------------


class LlmClient:
    def __init__(self, cfg: config_mod.Config | None = None) -> None:
        self.cfg = cfg or config_mod.get_config()
        self.timeouts = Timeouts.from_config(self.cfg)

    # -- 配置门禁 --------------------------------------------------------------
    def ensure_ready(self, provider: str | None = None) -> str:
        """provider/key 检查；不满足抛结构化错误（绝不发请求）。"""
        provider = (provider or self.cfg.llm_provider or "").strip()
        if provider in ("", "off"):
            raise ApiError(
                "LLM_DISABLED",
                "AI 功能已关闭",
                hint="在设置页选择 DeepSeek / OpenAI 兼容 / Ollama 之一后即可使用",
            )
        if not self.cfg.llm_base_url:
            raise ApiError("LLM_NOT_CONFIGURED", "尚未配置 LLM Base URL", details={"field": "llm_base_url"})
        if not self.cfg.llm_model:
            raise ApiError("LLM_NOT_CONFIGURED", "尚未配置模型名", details={"field": "llm_model"})
        if provider != "ollama" and not self.cfg.llm_api_key:
            raise ApiError(
                "LLM_NOT_CONFIGURED",
                "尚未配置 API Key",
                details={"field": "llm_api_key", "provider": provider},
                hint="在设置页填写 API Key（只写入本地 .env，权限 600）",
            )
        return provider

    def _headers(self, provider: str) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        # key 只作为请求头存在，绝不进日志 / 响应 / 字段清单
        if provider != "ollama" and self.cfg.llm_api_key:
            headers["Authorization"] = f"Bearer {self.cfg.llm_api_key}"
        return headers

    # -- 请求 ------------------------------------------------------------------
    def chat(
        self,
        payload: Mapping[str, Any],
        *,
        purpose: str,
        provider: str | None = None,
        model: str | None = None,
        attempts: int | None = None,
        validator: Callable[[Any], Any] | None = None,
        json_mode: bool | None = None,
    ) -> LlmResult:
        """发送一次（含重试）chat/completions 请求。

        ``payload`` 就是 preview 里逐字展示给用户的请求体；这里不再改写内容，
        只补充 provider 相关头。调用方必须先完成 consent（见 services/consent.py）。
        """
        provider = self.ensure_ready(provider)
        url = (self.cfg.llm_base_url or "").rstrip("/") + "/chat/completions"
        host = egress_guard.assert_allowed(url, self.cfg)
        model = model or str(payload.get("model") or self.cfg.llm_model)

        body = dict(payload)
        body["model"] = model
        want_json = body.get("response_format", {}).get("type") == "json_object" if isinstance(body.get("response_format"), Mapping) else (json_mode or False)
        if want_json:
            self._assert_json_hint(body)

        retries = self._retry_budget(attempts)
        started = time.monotonic()
        last_error: ApiError | None = None
        conn_retries = 0
        http_retries = 0
        attempt_no = 0
        while True:
            attempt_no += 1
            try:
                with httpx.Client(timeout=self.timeouts.as_httpx(), follow_redirects=False) as client:
                    response = client.post(url, json=body, headers=self._headers(provider))
                latency_ms = int((time.monotonic() - started) * 1000)
                if response.status_code in RETRY_STATUS and http_retries < retries:
                    http_retries += 1
                    last_error = self._status_error(response, provider)
                    self._sleep(http_retries, response.headers.get("Retry-After"))
                    continue
                return self._parse_response(
                    response,
                    provider=provider,
                    model=model,
                    host=host,
                    latency_ms=latency_ms,
                    purpose=purpose,
                    validator=validator,
                    attempt_no=attempt_no,
                    max_tokens=body.get("max_tokens"),
                )
            except RETRY_EXCEPTIONS as exc:
                # F1：连接级/TLS 抖动没有状态码，必须按 max_retries 重试；
                # 归类为「网络不可达」，绝不报成 key 无效。
                last_error = self._network_error(exc)
                conn_retries += 1
                if conn_retries <= retries:
                    self._sleep(conn_retries, None)
                    continue
                log.warning(
                    "LLM 连接失败 purpose=%s host=%s attempts=%s err=%s",
                    purpose,
                    host,
                    attempt_no,
                    type(exc).__name__,
                )
                raise last_error from None
            except httpx.HTTPError as exc:  # 其他 httpx 异常（编码/协议）
                raise ApiError(
                    "LLM_UNREACHABLE",
                    "无法连接 LLM 服务",
                    details={"reason": type(exc).__name__},
                ) from None

    def _retry_budget(self, attempts: int | None) -> int:
        if attempts is not None:
            return max(0, attempts)
        # 契约 §10：同一预览最多重试 1 次；F1：连接级抖动用满 LLM_MAX_RETRIES。
        # 这里取 max_retries（连接级），HTTP 层再按「仅 1 次」收敛，见 _status_error 调用处。
        return max(0, int(self.cfg.llm_max_retries or 0))

    def _sleep(self, attempt_no: int, retry_after: str | None) -> None:
        delay = 0.4 * attempt_no
        if retry_after:
            try:
                delay = min(5.0, max(delay, float(retry_after)))
            except ValueError:
                pass
        time.sleep(min(delay, 5.0))

    def _assert_json_hint(self, body: Mapping[str, Any]) -> None:
        text = " ".join(
            str(message.get("content", "")) for message in body.get("messages", []) if isinstance(message, Mapping)
        )
        if "json" not in text.lower():
            # 本地前置校验失败：零出网、不重试、不计入上游错误率（API-CONTRACT §10.5-1）
            raise ApiError(
                "LLM_JSON_MODE_PRECONDITION",
                "提示词模板缺少 json 字样，已在本机拦截（未发送任何数据）",
                details={
                    "reason": "PROMPT_MISSING_JSON_LITERAL",
                    "purpose": body.get("response_format"),
                    "missing": "literal 'json' in messages",
                },
                hint="这是提示词模板问题：请在系统指令里保留「以 json 返回」字样（F2）",
            )

    # -- 响应处理 --------------------------------------------------------------
    def _status_error(self, response: httpx.Response, provider: str) -> ApiError:
        status_code = response.status_code
        snippet = ""
        try:
            data = response.json()
            error = data.get("error") if isinstance(data, Mapping) else None
            if isinstance(error, Mapping):
                snippet = str(error.get("message") or error.get("type") or "")
            else:
                snippet = str(error or "")
        except ValueError:
            snippet = response.text[:200]
        snippet = config_mod.redact(snippet)[:300]

        if status_code == 429:
            return ApiError(
                "LLM_RATE_LIMITED",
                "LLM 上游限流，请稍后重试",
                details={"http_status": status_code, "upstream": snippet},
            )
        if status_code in (401, 403):
            return ApiError(
                "LLM_UPSTREAM_ERROR",
                "LLM 服务拒绝鉴权（API Key 可能无效或过期）",
                details={"http_status": status_code, "provider": provider, "upstream": snippet},
                hint="在设置页更新 API Key；连接类错误不会报成这个",
            )
        if status_code == 400 and "json" in snippet.lower():
            return ApiError(
                "LLM_UPSTREAM_ERROR",
                "上游拒绝 JSON 模式（prompt 需包含 'json'）",
                details={"http_status": status_code, "upstream": snippet},
            )
        return ApiError(
            "LLM_UPSTREAM_ERROR",
            f"LLM 服务返回 {status_code}",
            details={"http_status": status_code, "provider": provider, "upstream": snippet},
        )

    @staticmethod
    def _network_error(exc: BaseException) -> ApiError:
        """连接级异常 → 网络不可达（**不是** key 问题，避免误导用户）。"""
        if isinstance(exc, (httpx.TimeoutException,)):
            return ApiError("LLM_TIMEOUT", "LLM 请求超时", details={"reason": type(exc).__name__})
        return ApiError(
            "LLM_UNREACHABLE",
            "无法连接 LLM 服务（网络或 TLS 握手中断，已自动重试）",
            details={"reason": type(exc).__name__, "hint": "可重试；若持续失败请检查网络或 Base URL"},
        )

    def _parse_response(
        self,
        response: httpx.Response,
        *,
        provider: str,
        model: str,
        host: str,
        latency_ms: int,
        purpose: str,
        validator: Callable[[Any], Any] | None,
        attempt_no: int,
        max_tokens: Any = None,
    ) -> LlmResult:
        if response.status_code >= 400:
            raise self._status_error(response, provider)
        try:
            data = response.json()
        except ValueError:
            raise ApiError(
                "LLM_BAD_RESPONSE",
                "LLM 返回的不是 JSON",
                details={"http_status": response.status_code, "body_preview": response.text[:200]},
            ) from None

        choices = data.get("choices") or []
        if not choices:
            raise ApiError("LLM_BAD_RESPONSE", "LLM 返回缺少 choices", details={"keys": sorted(data)})
        choice = choices[0] or {}
        message = choice.get("message") or {}
        raw_text = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""
        finish_reason = choice.get("finish_reason")

        usage_raw = data.get("usage") or {}
        details = usage_raw.get("completion_tokens_details") or {}
        usage = {
            "prompt_tokens": int(usage_raw.get("prompt_tokens") or 0),
            "completion_tokens": int(usage_raw.get("completion_tokens") or 0),
            "total_tokens": int(usage_raw.get("total_tokens") or 0),
            "reasoning_tokens": int(details.get("reasoning_tokens") or 0) if isinstance(details, Mapping) else 0,
        }

        # F4：推理耗尽预算导致正文为空 → 明确失败，绝不写库
        if finish_reason == "length" and not raw_text.strip():
            raise ApiError(
                "LLM_TRUNCATED",
                "LLM 输出被截断：推理消耗了全部 max_tokens，正文为空",
                details={
                    "reason": "empty_content",
                    "finish_reason": finish_reason,
                    "reasoning_tokens": usage["reasoning_tokens"],
                    "completion_tokens": usage["completion_tokens"],
                    "max_tokens": max_tokens,
                    "model": model,
                },
                hint="提高 max_tokens（分析链路建议 ≥2048）或改用 deepseek-chat",
            )

        warnings: list[dict[str, Any]] = []
        if finish_reason == "length" and raw_text.strip():
            warnings.append(
                {
                    "code": "OUTPUT_TRUNCATED",
                    "severity": "warn",
                    "message": "模型输出可能被截断（finish_reason=length），请检查内容完整性",
                    "details": {
                        "finish_reason": finish_reason,
                        "completion_tokens": usage.get("completion_tokens"),
                        "max_tokens": max_tokens,
                    },
                }
            )
        parsed: Any = None
        if raw_text.strip():
            parsed, error_reason = extract_json(raw_text)
            if parsed is None and error_reason:
                warnings.append(
                    {
                        "code": "LLM_JSON_UNPARSABLE",
                        "message": "模型返回内容无法解析为 JSON，已保留原文",
                    }
                )
            elif parsed is not None:
                parsed, schema_warnings = validate_schema(parsed, validator, purpose=purpose)
                warnings.extend(schema_warnings)
                if parsed is None and finish_reason == "length":
                    raise ApiError(
                        "LLM_TRUNCATED",
                        "LLM 输出在半截 JSON 处被截断",
                        details={
                            "reason": "partial_json",
                            "finish_reason": finish_reason,
                            "reasoning_tokens": usage["reasoning_tokens"],
                            "max_tokens": max_tokens,
                        },
                        hint="提高 max_tokens 后重试",
                    )
        else:
            warnings.append(
                {
                    "code": "LLM_EMPTY_CONTENT",
                    "severity": "warn",
                    "message": "模型返回空正文（已记录 usage，未落库）",
                    "details": {
                        "finish_reason": finish_reason,
                        "completion_tokens": usage.get("completion_tokens"),
                        "max_tokens": max_tokens,
                    },
                }
            )

        log.info(
            "LLM 调用完成 purpose=%s provider=%s model=%s host=%s latency_ms=%s attempts=%s tokens=%s reasoning_tokens=%s finish=%s",
            purpose,
            provider,
            model,
            host,
            latency_ms,
            attempt_no,
            usage["total_tokens"],
            usage["reasoning_tokens"],
            finish_reason,
        )
        if reasoning:
            log.debug("reasoning_content 长度=%s（只观察，不影响成功判定）", len(reasoning))

        return LlmResult(
            ok=True,
            raw_text=raw_text,
            parsed=parsed,
            model=model,
            provider=provider,
            endpoint_host=host,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            usage=usage,
            warnings=warnings,
            attempts=attempt_no,
            http_status=response.status_code,
        )

    # -- 连通性测试 ------------------------------------------------------------
    def probe_models(self, *, timeout_s: float = 20.0) -> dict[str, Any]:
        """GET {base}/models：设置页「测试连接」与 doctor 共用。

        默认从 5 秒放宽到 20 秒：实测这条网络下 TLS 握手要 8.6–9.8 秒，5 秒的探针会把
        "握手慢" 报成 "连不上"，而同一时刻真实对话调用是成功的。探针仍受 ``timeout_s`` 硬约束，
        不会无限等。
        """
        provider = self.cfg.llm_provider or "off"
        started = time.monotonic()
        if provider == "off" or not self.cfg.llm_base_url:
            return {
                "reachable": False,
                "http_status": None,
                "models": [],
                "latency_ms": 0,
                "error_code": "LLM_DISABLED" if provider == "off" else "LLM_NOT_CONFIGURED",
            }
        url = (self.cfg.llm_base_url or "").rstrip("/") + "/models"
        try:
            egress_guard.assert_allowed(url, self.cfg)
        except ApiError as exc:
            return {
                "reachable": False,
                "http_status": None,
                "models": [],
                "latency_ms": 0,
                "error_code": exc.code,
            }
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout_s, connect=min(20.0, timeout_s))) as client:
                response = client.get(url, headers=self._headers(provider))
            latency_ms = int((time.monotonic() - started) * 1000)
            models: list[str] = []
            if response.status_code < 400:
                try:
                    data = response.json()
                    models = [str(item.get("id")) for item in (data.get("data") or []) if isinstance(item, Mapping)]
                except ValueError:
                    models = []
            return {
                "reachable": response.status_code < 400,
                "http_status": response.status_code,
                "models": models,
                "latency_ms": latency_ms,
                "error_code": None if response.status_code < 400 else "LLM_UPSTREAM_ERROR",
            }
        except RETRY_EXCEPTIONS as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            return {
                "reachable": False,
                "http_status": None,
                "models": [],
                "latency_ms": latency_ms,
                "error_code": "LLM_TIMEOUT" if isinstance(exc, httpx.TimeoutException) else "LLM_UNREACHABLE",
            }


def get_client(cfg: config_mod.Config | None = None) -> LlmClient:
    return LlmClient(cfg)
