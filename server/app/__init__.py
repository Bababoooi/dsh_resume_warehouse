"""应用工厂：初始化顺序、日志、请求信封与蓝图注册。

顺序（ARCHITECTURE §3）：配置 → 数据目录/迁移 → 日志 → 错误处理器 → 蓝图。
所有响应统一 ``{"ok": true, "data": ..., "request_id": "req_..."}``；
``jsonify`` 关闭 ASCII 转义，中文原样输出。
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import time
import uuid
from typing import Any

from flask import Flask, g, jsonify, request, abort
from werkzeug.exceptions import HTTPException

from . import config as config_mod
from . import db as db_mod
from .errors import ApiError, register_error_handlers

__all__ = ["create_app"]


class RedactFilter(logging.Filter):
    """日志兜底脱敏：任何记录里出现真实 key 都替换成 sk-***。"""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            cfg = config_mod.get_config()
            secret = cfg.api_key
        except Exception:  # 配置尚未加载时不阻塞日志
            return True
        if secret and len(secret) >= 8:
            message = record.getMessage()
            if secret in message:
                record.msg = message.replace(secret, "sk-***")
                record.args = ()
        return True


def _configure_logging(cfg: config_mod.Config, paths: db_mod.Paths) -> None:
    root = logging.getLogger()
    if getattr(root, "_resume_warehouse_configured", False):
        return
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    file_handler = logging.handlers.RotatingFileHandler(
        paths.logs / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactFilter())
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(RedactFilter())
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    root._resume_warehouse_configured = True  # type: ignore[attr-defined]
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


PAGE_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


def create_app(cfg: config_mod.Config | None = None) -> Flask:
    cfg = cfg or config_mod.load_config()
    config_mod.set_config(cfg)

    paths = db_mod.get_paths()
    paths.ensure()
    # 运行时端口文件目录（端口顺延后 run.sh / Skill 都读它）
    (paths.root / "runtime").mkdir(parents=True, exist_ok=True)

    _configure_logging(cfg, paths)

    conn = db_mod.get_conn()
    applied = db_mod.migrate(conn)
    log = logging.getLogger("app.factory")
    log.info(
        "启动：data_root=%s db=%s 迁移=%s provider=%s model=%s key_set=%s",
        paths.root,
        paths.db,
        applied or "up-to-date",
        cfg.provider,
        cfg.model,
        cfg.key_set,
    )

    app = Flask(__name__, static_folder=None, template_folder=None)
    app.config.update(
        MAX_CONTENT_LENGTH=20 * 1024 * 1024,
        JSON_AS_ASCII=False,
        PROPAGATE_EXCEPTIONS=False,
        APP_CFG=cfg,
        PATHS=paths,
    )
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    app.extensions["cfg"] = cfg
    app.extensions["paths"] = paths

    @app.before_request
    def _attach_request_id() -> None:  # type: ignore[unused-ignore]
        g.request_id = "req_" + uuid.uuid4().hex[:16]
        g.started_at = time.perf_counter()
        if not request.is_json:
            return None
        return None

    @app.after_request
    def _finalize(response):  # type: ignore[no-untyped-def]
        rid = getattr(g, "request_id", "")
        if rid:
            response.headers.setdefault("X-Request-Id", rid)
        started = getattr(g, "started_at", None)
        if started is not None:
            response.headers["X-Elapsed-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # 页面面（HTML/CSS/JS 与下载）统一加 CSP：离线自包含，只允许自己这一个源。
        # AC-PRIV-08：default-src 'self' / 无 unsafe-eval / connect-src 仅 'self'。
        if not request.path.startswith("/api/"):
            response.headers.setdefault("Content-Security-Policy", PAGE_CSP)
        return response

    register_error_handlers(app)

    # 蓝图（前缀 /api/v1；健康检查额外暴露 /api/health）
    from .api import register_blueprints

    register_blueprints(app)

    @app.get("/api/health")
    def _health_alias():  # type: ignore[no-untyped-def]
        from .api.health import health_payload

        return jsonify({"ok": True, "data": health_payload(), "request_id": getattr(g, "request_id", "")})

    # 前端静态资源（web/ 目录，同源、无 CDN）。只允许读 web/ 下的文件，
    # 且绝不碰 /api/**：Werkzeug 的静态段优先级高于 path 转换器，但保险起见再挡一次。
    from pathlib import Path as _Path

    from flask import send_from_directory

    web_root = _Path(config_mod.PROJECT_ROOT) / "web"

    @app.get("/")
    def _index():  # type: ignore[no-untyped-def]
        return send_from_directory(web_root, "index.html")

    @app.get("/<path:filename>")
    def _web_asset(filename: str):  # type: ignore[no-untyped-def]
        if filename.startswith("api/") or filename == "api":
            abort(404)
        target = (web_root / filename).resolve()
        try:
            target.relative_to(web_root.resolve())
        except ValueError:
            abort(404)
        if not target.is_file():
            abort(404)
        response = send_from_directory(web_root, filename)
        # 本地开发：不让浏览器缓存 JS/CSS，改完刷新即生效
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    @app.teardown_appcontext
    def _close_request_conn(exc: BaseException | None = None):  # type: ignore[no-untyped-def]
        """E) 请求结束释放本线程的 SQLite 连接。

        Flask 的 ``threaded=True`` 会复用工作线程；连接是线程局部的，
        不在这里关就会随线程常驻（WAL 句柄 + 未提交事务），长跑进程句柄只增不减。
        后台任务线程由 ``services/jobrun.py::_run`` 的 ``finally`` 负责。
        """
        db_mod.close_conn()

    return app


def json_ok(data: Any, status: int = 200, headers: dict[str, str] | None = None):
    response = jsonify({"ok": True, "data": data, "request_id": getattr(g, "request_id", "")})
    response.status_code = status
    for key, value in (headers or {}).items():
        response.headers[key] = value
    return response


def json_no_content(headers: dict[str, str] | None = None):
    response = jsonify({})
    response.status_code = 204
    response.set_data(b"")
    for key, value in (headers or {}).items():
        response.headers[key] = value
    return response


# 供测试/脚本使用的别名
def default_app() -> Flask:  # pragma: no cover - 便捷入口
    os.environ.setdefault("APP_ENV", "local")
    return create_app()


__all__.append("json_ok")
__all__.append("json_no_content")
__all__.append("HTTPException")
__all__.append("ApiError")
__all__.append("db_mod")
