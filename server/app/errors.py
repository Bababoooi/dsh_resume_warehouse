"""统一错误模型与错误码表（API-CONTRACT §14 的代码化）。

规则：
* 任何业务失败一律 ``raise ApiError(...)``，由 Flask 错误处理器转成
  ``{"ok": false, "error": {...}, "request_id": ...}``。
* 500 响应体**不含 traceback**（traceback 只进日志，且经 :func:`config.redact` 脱敏）。
* ``code`` 是前端分支依据；``message`` 是中文人话；``details`` 结构见契约。
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from . import config as config_mod

log = logging.getLogger("app.errors")

#: code → HTTP 状态码（与 API-CONTRACT §14 逐条对齐）
ERROR_STATUS: dict[str, int] = {
    "VALIDATION_ERROR": 422,
    "BAD_REQUEST": 400,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "FILE_IN_USE": 409,
    "UNSUPPORTED_MEDIA_TYPE": 415,
    "PAYLOAD_TOO_LARGE": 413,
    "METHOD_NOT_ALLOWED": 405,
    "PATH_ESCAPE": 400,
    "IMPORT_UNSUPPORTED": 422,
    "IMPORT_NO_TEXT_LAYER": 422,
    "TEMPLATE_INVALID": 422,
    "NO_DEFAULT_TEMPLATE": 409,
    "MISSING_SLOTS": 422,
    "NAMING_UNKNOWN_VAR": 422,
    "NAMING_MISSING_VAR": 422,
    "NAMING_EMPTY": 422,
    "NAMING_TOO_LONG": 422,
    "NAMING_SYNTAX": 422,
    "NAMING_INVALID_CHARS": 422,
    "LLM_JSON_MODE_PRECONDITION": 422,
    "LLM_DISABLED": 503,
    "LLM_UNREACHABLE": 503,
    "LLM_NOT_CONFIGURED": 503,
    "LLM_CONSENT_REQUIRED": 428,
    "LLM_CONSENT_EXPIRED": 410,
    "LLM_CONSENT_MISMATCH": 409,
    "LLM_UPSTREAM_ERROR": 502,
    "LLM_TIMEOUT": 504,
    "LLM_RATE_LIMITED": 429,
    "LLM_BAD_RESPONSE": 502,
    "LLM_TRUNCATED": 502,
    "EGRESS_BLOCKED": 403,
    # 下行抓取（app/adapters/fetch_client.py，唯一允许读外部网页的模块）
    "TIMEOUT": 504,
    "FETCH_UNREACHABLE": 502,
    "RENDER_FAILED": 500,
    "FONT_UNAVAILABLE": 500,
    "STORAGE_ERROR": 500,
    "JOB_IN_PROGRESS": 409,
    "CONFIRM_MISMATCH": 422,
    "JOB_INTERRUPTED": 409,
    "INTERNAL": 500,
}

#: 中文兜底文案（端点可传更具体的 message）
DEFAULT_MESSAGES: dict[str, str] = {
    "VALIDATION_ERROR": "请求字段校验未通过",
    "BAD_REQUEST": "请求格式不合法",
    "NOT_FOUND": "资源不存在",
    "CONFLICT": "当前状态不允许该操作",
    "UNSUPPORTED_MEDIA_TYPE": "不支持的文件类型",
    "PAYLOAD_TOO_LARGE": "文件超过大小上限",
    "PATH_ESCAPE": "路径越界：只允许访问 data/ 内的文件",
    "NAMING_UNKNOWN_VAR": "命名模板包含未知变量",
    "NAMING_MISSING_VAR": "命名模板缺少变量值",
    "NAMING_EMPTY": "命名模板净化后为空",
    "NAMING_TOO_LONG": "命名模板过长",
    "NAMING_SYNTAX": "命名模板语法错误",
    "NAMING_INVALID_CHARS": "命名模板包含非法字符",
    "LLM_DISABLED": "AI 功能已关闭（provider=off）",
    "LLM_UNREACHABLE": "无法连接 LLM 服务",
    "LLM_NOT_CONFIGURED": "尚未配置 LLM",
    "LLM_CONSENT_REQUIRED": "发送前必须先预览「将发送字段清单」",
    "LLM_CONSENT_EXPIRED": "预览已过期，请重新预览",
    "LLM_CONSENT_MISMATCH": "预览与本次发送不一致或已被使用",
    "LLM_UPSTREAM_ERROR": "LLM 服务返回异常",
    "LLM_TIMEOUT": "LLM 请求超时",
    "LLM_RATE_LIMITED": "LLM 上游限流，请稍后重试",
    "LLM_BAD_RESPONSE": "LLM 返回内容无法解析",
    "EGRESS_BLOCKED": "出网被策略拒绝：目标主机不在白名单",
    "TIMEOUT": "外部页面响应超时",
    "FETCH_UNREACHABLE": "无法连接目标站点",
    "RENDER_FAILED": "渲染失败",
    "FONT_UNAVAILABLE": "中文字体不可用，已禁用 PDF 导出",
    "STORAGE_ERROR": "本地存储写入失败",
    "JOB_IN_PROGRESS": "该资源已有任务在进行",
    "CONFIRM_MISMATCH": "确认信息不一致，未执行任何删除",
    "JOB_INTERRUPTED": "任务因进程重启而中断，可重试",
    "INTERNAL": "服务器内部错误",
}


class ApiError(Exception):
    """契约错误。``code`` 必须在 :data:`ERROR_STATUS` 内。"""

    def __init__(
        self,
        code: str,
        message: str | None = None,
        *,
        details: Mapping[str, Any] | None = None,
        hint: str | None = None,
        http_status: int | None = None,
    ) -> None:
        if code not in ERROR_STATUS:
            raise ValueError(f"未知错误码 {code!r}（必须先在 API-CONTRACT §14 注册）")
        self.code = code
        self.message = message or DEFAULT_MESSAGES.get(code, code)
        self.details = dict(details or {})
        self.hint = hint
        self.http_status = http_status or ERROR_STATUS[code]
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": config_mod.redact(self.message)}
        if self.details:
            error["details"] = _redact_deep(self.details)
        if self.hint:
            error["hint"] = config_mod.redact(self.hint)
        return {"ok": False, "error": error}


def _redact_deep(value: Any) -> Any:
    if isinstance(value, str):
        return config_mod.redact(value)
    if isinstance(value, Mapping):
        return {key: _redact_deep(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact_deep(item) for item in value]
    return value


# --------------------------------------------------------------------------------------
# 便捷构造器
# --------------------------------------------------------------------------------------


def validation_error(fields: list[dict[str, str]], *, message: str | None = None) -> ApiError:
    return ApiError(
        "VALIDATION_ERROR",
        message or "字段校验未通过",
        details={"fields": fields},
        hint="请修正标红字段后重试",
    )


def bad_request(reason: str = "invalid_json", **extra: Any) -> ApiError:
    return ApiError("BAD_REQUEST", details={"reason": reason, **extra})


def not_found(resource: str, resource_id: str | None = None) -> ApiError:
    return ApiError("NOT_FOUND", details={"resource": resource, "id": resource_id})


def internal_error() -> ApiError:
    return ApiError("INTERNAL")


def llm_error(code: str, *, message: str | None = None, **details: Any) -> ApiError:
    return ApiError(code, message, details=details)


# --------------------------------------------------------------------------------------
# Flask 装配
# --------------------------------------------------------------------------------------


def _request_id() -> str:
    from flask import g

    return getattr(g, "request_id", "")


def register_error_handlers(app: Flask) -> None:
    """把 ApiError / HTTPException / 未捕获异常统一成契约信封。"""

    @app.errorhandler(ApiError)
    def _handle_api_error(exc: ApiError):  # pragma: no cover - 由测试覆盖
        payload = exc.to_dict()
        payload["request_id"] = _request_id()
        return jsonify(payload), exc.http_status

    @app.errorhandler(HTTPException)
    def _handle_http_exception(exc: HTTPException):  # pragma: no cover
        code_map = {
            400: "BAD_REQUEST",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            413: "PAYLOAD_TOO_LARGE",
            415: "UNSUPPORTED_MEDIA_TYPE",
        }
        code = code_map.get(exc.code or 500, "INTERNAL")
        api_err = ApiError(code, details={"http_status": exc.code, "reason": (exc.name or "").lower()})
        payload = api_err.to_dict()
        payload["request_id"] = _request_id()
        return jsonify(payload), api_err.http_status

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):  # pragma: no cover
        # traceback 只进日志，响应体绝不泄露内部细节
        log.exception("未捕获异常: %s", config_mod.redact(repr(exc)))
        payload = ApiError("INTERNAL").to_dict()
        payload["request_id"] = _request_id()
        return jsonify(payload), 500
