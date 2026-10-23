"""GET /health —— 存活与自检摘要（不需要任何依赖）。"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app

from .. import buildinfo
from .. import config as config_mod
from .. import db as db_mod
from . import common

bp = Blueprint("health", __name__)

STARTED_AT = time.time()


def _runtime_port(cfg: config_mod.Config) -> int:
    """实际监听端口：优先 app 启动时绑定的值，其次本次进程写的端口文件。

    绝不以「配置里的 APP_PORT」当作已绑定端口——端口顺延时那会报错值。
    """
    bound = current_app.extensions.get("bound_port")
    if isinstance(bound, int) and bound > 0:
        return bound
    port_file = db_mod.get_paths().root / "runtime" / "app_port"
    if port_file.exists():
        raw = port_file.read_text(encoding="utf-8").strip()
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                # 只认本进程写的端口文件，避免把别的实例的端口当成自己的
                if data.get("pid") not in (None, os.getpid()):
                    return cfg.app_port
                if data.get("port"):
                    return int(data["port"])
            return int(raw)
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    return cfg.app_port


def health_payload() -> dict:
    cfg: config_mod.Config = current_app.extensions.get("cfg") or config_mod.get_config()
    db_state: dict[str, object]
    try:
        conn = db_mod.get_conn()
        version = conn.execute("SELECT MAX(version) FROM schema_migration").fetchone()[0]
        conn.execute("SELECT 1").fetchone()
        db_state = {"ok": True, "path": str(db_mod.get_paths().db), "schema_version": version or 0}
    except Exception as exc:  # pragma: no cover - 只读诊断
        db_state = {"ok": False, "path": str(db_mod.get_paths().db), "error": f"{type(exc).__name__}: {exc}"}
    warnings: list[str] = []
    if not db_state.get("ok"):
        warnings.append("数据库不可用")
    if not cfg.ready:
        warnings.append(f"LLM 未就绪：{cfg.not_ready_reason}")
    status = "ok" if db_state.get("ok") else "degraded"
    return {
        "status": status,
        "uptime_s": round(time.time() - STARTED_AT, 1),
        "port": _runtime_port(cfg),
        "db": db_state,
        "llm_ready": cfg.ready,
        "version": config_mod.APP_VERSION,
        # D-27：一条命令判断「这个进程是不是当前代码」（git short sha，或 server/app 源码指纹）
        "build": buildinfo.build_info(),
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "warnings": warnings,
    }


@bp.get("/health")
def health():
    return common.ok(health_payload())
