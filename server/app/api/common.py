"""API 层小工具：统一信封、请求体解析、分页参数。"""

from __future__ import annotations

from typing import Any, Mapping, TypeVar

from flask import g, jsonify, request

from .. import db as db_mod
from ..errors import ApiError
from ..models import StrictModel, parse_body

T = TypeVar("T", bound=StrictModel)


def ok(data: Any, status: int = 200, headers: Mapping[str, str] | None = None):
    response = jsonify({"ok": True, "data": data, "request_id": getattr(g, "request_id", "")})
    response.status_code = status
    for key, value in (headers or {}).items():
        response.headers[key] = value
    return response


def created(data: Any, location: str):
    return ok(data, status=201, headers={"Location": location})


def accepted(data: Any):
    return ok(data, status=202)


def no_content(headers: Mapping[str, str] | None = None):
    response = jsonify({})
    response.status_code = 204
    response.set_data(b"")
    for key, value in (headers or {}).items():
        response.headers[key] = value
    return response


def raw_body() -> Mapping[str, Any]:
    """读取 JSON 对象请求体；非对象/非法 JSON 一律 422。"""

    if not request.data:
        return {}
    if not request.is_json:
        raise ApiError(
            "UNSUPPORTED_MEDIA_TYPE",
            "请求体必须是 application/json",
            details={"content_type": request.content_type or ""},
        )
    payload = request.get_json(silent=True)
    if payload is None:
        raise ApiError("BAD_REQUEST", "请求体不是合法 JSON")
    if not isinstance(payload, Mapping):
        raise ApiError("VALIDATION_ERROR", "请求体必须是 JSON 对象", details={"fields": [{"field": "$", "rule": "object", "message": "需要对象"}]})
    return payload


def parsed(model: type[T]) -> T:
    return parse_body(model, raw_body())


def require_id(name: str = "id") -> str:
    value = request.view_args.get(name) if request.view_args else None
    value = value or request.args.get(name)
    if not value:
        raise ApiError("VALIDATION_ERROR", f"缺少路径参数 {name}", details={"fields": [{"field": name, "rule": "required", "message": "必填"}]})
    return value


def _int_arg(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ApiError(
            "VALIDATION_ERROR",
            f"参数 {name} 必须是整数",
            details={"fields": [{"field": name, "rule": "int", "message": "必须是整数"}]},
        ) from None
    if value < minimum or value > maximum:
        raise ApiError(
            "VALIDATION_ERROR",
            f"参数 {name} 超出范围（{minimum}..{maximum}）",
            details={"fields": [{"field": name, "rule": "range", "message": f"{minimum}..{maximum}"}]},
        )
    return value


def limit(default: int = 20, maximum: int = 100) -> int:
    return _int_arg("limit", default, minimum=1, maximum=maximum)


def offset() -> int:
    raw_cursor = request.args.get("cursor")
    if raw_cursor:
        try:
            return max(0, int(raw_cursor))
        except ValueError:
            raise ApiError("VALIDATION_ERROR", "cursor 非法", details={"fields": [{"field": "cursor", "rule": "int", "message": "必须是整数游标"}]}) from None
    return _int_arg("offset", 0, minimum=0, maximum=10_000_000)


def list_envelope(items: list[dict[str, Any]], total: int, *, limit_value: int, offset_value: int) -> dict[str, Any]:
    next_offset = offset_value + len(items)
    return {
        "items": items,
        "next_cursor": str(next_offset) if next_offset < total and items else None,
        "total_estimate": total,
        "limit": limit_value,
        "offset": offset_value,
    }


def now_iso() -> str:
    return db_mod.utcnow_iso()
