"""设置中心（GET/PUT /settings、API key、连通性测试、全量导出）。

* ``GET /settings`` **永不返回 key 的任何片段**，只给 ``key_set`` 布尔与字段名；
* key 只写进项目根 ``.env``（chmod 600），并立刻刷新内存配置；
* ``export-all`` 打包 db + files + exports + imports，**不含 .env**。
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from flask import Blueprint

from .. import config as config_mod
from ..errors import ApiError
from ..adapters import llm_client
from ..models import ApiKeyIn, SettingsPatch
from ..repos import SettingsRepo
from ..services.storage import Storage
from . import common

bp = Blueprint("settings", __name__)


def _view(cfg: config_mod.Config, repo: SettingsRepo) -> dict[str, Any]:
    all_settings = repo.all()
    return {
        "provider": cfg.provider,
        "provider_label": cfg.preset.label,
        "base_url": cfg.base_url,
        "model": cfg.model,
        "model_analysis": cfg.model_analysis,
        "key_set": cfg.key_set,
        "key_field": "LLM_API_KEY",
        "ready": cfg.ready,
        "not_ready_reason": cfg.not_ready_reason,
        "timeouts": {
            "connect_s": cfg.connect_timeout,
            "read_s": cfg.read_timeout,
            "total_s": float(cfg.timeout_seconds),
        },
        "max_retries": cfg.max_retries,
        "allowed_hosts": cfg.allowed_hosts,
        "auto_redact": all_settings.get("auto_redact") or [],
        "photo_in_export": all_settings.get("photo_in_export"),
        "allow_web_fetch": all_settings.get("allow_web_fetch"),
        "max_tokens_analysis": all_settings.get("max_tokens_analysis"),
        "max_tokens_generate": all_settings.get("max_tokens_generate"),
        "app_port": cfg.app_port,
        "naming_template": all_settings.get("naming_template"),
        "default_engine": all_settings.get("default_engine"),
        "verify_text": all_settings.get("verify_text"),
        "page_limit": all_settings.get("page_limit"),
        "ui": {
            "theme": all_settings.get("theme"),
            "page_size": all_settings.get("page_limit"),
            "last_template_id": all_settings.get("last_template_id"),
        },
        "data_root": str(cfg.data_dir),
    }


def _write_env(updates: dict[str, str]) -> None:
    """写 .env 并统一把配置错误转成 500 STORAGE_ERROR（路径/权限问题）。"""

    try:
        config_mod.update_env_file(updates)
    except config_mod.ConfigError as exc:
        raise ApiError("STORAGE_ERROR", "写入 .env 失败", hint=str(exc)) from exc


def _reload() -> config_mod.Config:
    cfg = config_mod.load_config()
    config_mod.set_config(cfg)
    return cfg


@bp.get("/settings")
def get_settings():
    return common.ok(_view(config_mod.get_config(), SettingsRepo()))


@bp.put("/settings")
def put_settings():
    payload = common.parsed(SettingsPatch)
    patch = payload.model_dump(exclude_unset=True, exclude_none=True)
    repo = SettingsRepo()
    env_updates: dict[str, str] = {}
    if "provider" in patch:
        env_updates["LLM_PROVIDER"] = str(patch["provider"])
    if "base_url" in patch:
        env_updates["LLM_BASE_URL"] = str(patch["base_url"]).strip()
    if "model" in patch:
        env_updates["LLM_MODEL"] = str(patch["model"]).strip()
    if "model_analysis" in patch:
        env_updates["LLM_MODEL_ANALYSIS"] = str(patch["model_analysis"]).strip()
    if "timeout_seconds" in patch:
        env_updates["LLM_TIMEOUT_SECONDS"] = str(patch["timeout_seconds"])
    if "max_retries" in patch:
        env_updates["LLM_MAX_RETRIES"] = str(patch["max_retries"])
    if env_updates:
        _write_env(env_updates)
    for key in (
        "auto_redact",
        "naming_template",
        "default_engine",
        "verify_text",
        "photo_in_export",
        "allow_web_fetch",
        "max_tokens_analysis",
        "max_tokens_generate",
    ):
        if key in patch:
            repo.set(key, patch[key])
    if "ui" in patch and isinstance(patch["ui"], dict):
        ui = patch["ui"]
        mapping = {"theme": "theme", "page_size": "page_limit", "last_template_id": "last_template_id"}
        for ui_key, setting_key in mapping.items():
            if ui_key in ui:
                repo.set(setting_key, ui[ui_key])
    cfg = _reload()
    return common.ok(_view(cfg, repo))


@bp.post("/settings/api-key")
def set_api_key():
    payload = common.parsed(ApiKeyIn)
    value = payload.api_key.strip()
    if not value:
        raise ApiError("VALIDATION_ERROR", "API key 不能为空", details={"fields": [{"field": "api_key", "rule": "required", "message": "不能为空"}]})
    _write_env({"LLM_API_KEY": value})
    _reload()
    return common.ok({"key_set": True, "key_field": "LLM_API_KEY"})


@bp.delete("/settings/api-key")
def clear_api_key():
    _write_env({"LLM_API_KEY": ""})
    _reload()
    return common.ok({"key_set": False, "key_field": "LLM_API_KEY"})


@bp.post("/settings/provider/test")
def test_provider():
    cfg = config_mod.get_config()
    client = llm_client.LlmClient(cfg)
    # 用配置里的连接预算（默认 20s）：5 秒的探针在 TLS 握手慢的网络下会误报"连不上"
    result = client.probe_models(timeout_s=float(getattr(cfg, "connect_timeout", 20.0)))
    repo = SettingsRepo()
    repo.set("llm_last_check_at", datetime.now().astimezone().isoformat(timespec="seconds"))
    repo.set("llm_last_check_reachable", bool(result.get("reachable")))
    return common.ok(result)


@bp.get("/settings/export-all")
def export_all():
    """把 db + files + exports + imports 打成一个 zip 落盘（不含 .env）。

    契约 v1.4：返回 ``{path, bytes, sha256}``（本机路径，供 UI 展示「备份已生成」），
    不再以附件流返回——备份属于本地数据，用户可在文件管理器直接取用。
    """
    storage = Storage()
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    dest = storage.paths.exports / f"resume-warehouse-backup-{stamp}.zip"
    storage.export_all_zip(dest)
    payload = dest.read_bytes()
    return common.ok(
        {
            "path": str(dest.relative_to(storage.paths.root)),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    )
