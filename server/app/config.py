"""配置中心（唯一读取 .env / 环境变量的地方）。

契约（ARCHITECTURE §5.3）:
  * 变量名固定一套 ``LLM_*``，不按 provider 分裂（禁止 DEEPSEEK_API_KEY）。
  * 加载优先级：进程环境变量 > <repo>/.env > 内置默认值。
  * API key 只以 ``key_set: bool`` 对外暴露；日志/异常/响应一律经 :func:`redact`。
  * ``DATA_DIR`` 只允许解析到 ``<repo>/data`` 之内，越界即 ConfigError。

本模块**不** import Flask，也不发起任何网络请求（出网只有 adapters/llm_client.py）。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

# --------------------------------------------------------------------------------------
# 路径常量
# --------------------------------------------------------------------------------------

SERVER_DIR = Path(__file__).resolve().parent.parent  # <repo>/server
PROJECT_ROOT = SERVER_DIR.parent  # <repo>
ENV_PATH = PROJECT_ROOT / ".env"
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

#: 允许的 provider（``off`` 是一等公民：离线也必须完整可用）
PROVIDERS = ("deepseek", "openai_compatible", "ollama", "off")

#: 版本号（/api/v1/health 与导出产物标注）
APP_VERSION = "1.0.0"

#: .env 中受管的键（白名单外的一律不读取，避免误读无关变量）
ENV_KEYS = (
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_MODEL_ANALYSIS",
    "LLM_API_KEY",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
    "APP_PORT",
    "DATA_DIR",
)

DEFAULTS: dict[str, str] = {
    "LLM_PROVIDER": "deepseek",
    "LLM_BASE_URL": "",
    "LLM_MODEL": "",
    "LLM_MODEL_ANALYSIS": "",
    "LLM_API_KEY": "",
    "LLM_TIMEOUT_SECONDS": "90",
    "LLM_MAX_RETRIES": "1",
    "APP_PORT": "8765",
    "DATA_DIR": "./data",
}

# --------------------------------------------------------------------------------------
# 脱敏
# --------------------------------------------------------------------------------------

_SK_PATTERN = re.compile(r"(sk-[A-Za-z0-9_\-]{4,})")
_BEARER_PATTERN = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.IGNORECASE)


def redact(value: Any) -> str:
    """把任何文本里的 API key 片段替换为 ``sk-***``。

    用于日志 formatter、异常消息、HTTP 响应（settings 端点连后四位都不给）。
    """

    text = value if isinstance(value, str) else str(value)
    text = _SK_PATTERN.sub("sk-***", text)
    text = _BEARER_PATTERN.sub(r"\1sk-***", text)
    return text


def mask_secret(secret: str) -> str:
    """给 ``value_preview`` 用的中间打码（``178****0929``）。**不用于 API key**。"""

    if not secret:
        return ""
    if len(secret) <= 4:
        return "*" * len(secret)
    if len(secret) <= 8:
        return secret[:1] + "*" * (len(secret) - 2) + secret[-1:]
    keep = 3
    return secret[:keep] + "*" * (len(secret) - keep * 2) + secret[-keep:]


class ConfigError(RuntimeError):
    """配置非法（启动期致命）。"""


# --------------------------------------------------------------------------------------
# .env 解析（不引入 python-dotenv，零新依赖）
# --------------------------------------------------------------------------------------


def parse_env_file(path: Path) -> dict[str, str]:
    """解析 ``KEY=VALUE`` 形式的 .env；保留注释与顺序由写入侧负责。"""

    if not path.exists():
        return {}
    out: dict[str, str] = {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:  # 权限错误等：不吞，交给调用方给出明确提示
        raise ConfigError(f"无法读取 {path}: {exc}") from exc
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :].strip()
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key not in ENV_KEYS:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            # 行尾注释：仅当 '#' 前有空白时剥离，避免误伤含 # 的值
            hash_at = value.find(" #")
            if hash_at != -1:
                value = value[:hash_at].rstrip()
        out[key] = value
    return out


def resolve_env(
    file_values: Mapping[str, str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """按 ``环境变量 > .env > 默认值`` 合并，返回完整配置字典（含 key 明文，勿外传）。"""

    environ = os.environ if environ is None else environ
    file_values = parse_env_file(ENV_PATH) if file_values is None else dict(file_values)
    merged: dict[str, str] = dict(DEFAULTS)
    for key in ENV_KEYS:
        file_value = file_values.get(key, "")
        if file_value != "" or key not in file_values:
            merged[key] = file_value if file_value != "" else DEFAULTS[key]
        env_value = environ.get(key)
        if env_value is not None and env_value != "":
            merged[key] = env_value
    return merged


# --------------------------------------------------------------------------------------
# Provider 预设
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderPreset:
    name: str
    base_url: str
    model: str
    analysis_model: str
    needs_key: bool
    label: str


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "deepseek": ProviderPreset(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        analysis_model="deepseek-reasoner",
        needs_key=True,
        label="DeepSeek（默认）",
    ),
    "openai_compatible": ProviderPreset(
        name="openai_compatible",
        base_url="",
        model="gpt-4o-mini",
        analysis_model="gpt-4o-mini",
        needs_key=True,
        label="OpenAI 兼容（自定义 base_url）",
    ),
    "ollama": ProviderPreset(
        name="ollama",
        base_url="http://127.0.0.1:11434/v1",
        model="qwen2.5:7b",
        analysis_model="qwen2.5:7b",
        needs_key=False,
        label="本地 Ollama",
    ),
    "off": ProviderPreset(
        name="off",
        base_url="",
        model="",
        analysis_model="",
        needs_key=False,
        label="关闭 AI（离线模式）",
    ),
}


def host_of(url: str) -> str:
    """从 URL 取 host（不引入 urllib.parse 之外的依赖；不含 userinfo）。"""

    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    return (parts.hostname or "").lower()


# --------------------------------------------------------------------------------------
# 运行时配置对象
# --------------------------------------------------------------------------------------


@dataclass
class Config:
    provider: str
    base_url: str
    model: str
    model_analysis: str
    api_key: str = field(default="", repr=False)  # 永不进 repr / 日志
    timeout_seconds: int = 90
    max_retries: int = 1
    app_port: int = 8765
    data_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data")
    warnings: list[str] = field(default_factory=list)

    # ---- 环境变量同名别名（adapters 统一按 LLM_* 名字读取）--------------------------
    @property
    def llm_provider(self) -> str:
        return self.provider

    @property
    def llm_base_url(self) -> str:
        return self.base_url

    @property
    def llm_model(self) -> str:
        return self.model

    @property
    def llm_model_analysis(self) -> str:
        return self.model_analysis

    @property
    def llm_api_key(self) -> str:
        return self.api_key

    @property
    def llm_timeout_seconds(self) -> int:
        return self.timeout_seconds

    @property
    def llm_max_retries(self) -> int:
        return self.max_retries

    # ---- 派生属性 -------------------------------------------------------------------
    @property
    def key_set(self) -> bool:
        return bool(self.api_key.strip())

    @property
    def preset(self) -> ProviderPreset:
        return PROVIDER_PRESETS.get(self.provider, PROVIDER_PRESETS["off"])

    @property
    def endpoint_host(self) -> str:
        return host_of(self.base_url)

    @property
    def allowed_hosts(self) -> list[str]:
        host = self.endpoint_host
        return [host] if host else []

    @property
    def chat_path(self) -> str:
        return "/chat/completions"

    @property
    def ready(self) -> bool:
        if self.provider == "off":
            return False
        if not self.base_url:
            return False
        if self.preset.needs_key and not self.key_set:
            return False
        return True

    @property
    def not_ready_reason(self) -> str:
        if self.provider == "off":
            return "LLM 已关闭（provider=off）"
        if not self.base_url:
            return "缺少 LLM_BASE_URL"
        if self.preset.needs_key and not self.key_set:
            return "未配置 LLM_API_KEY"
        return ""

    @property
    def connect_timeout(self) -> float:
        """连接预算（含 TLS 握手）。

        实测这台机器上到 DeepSeek 的 **TLS 握手要 8.6–9.8 秒**，5 秒预算会让每次调用都在
        connect 阶段被掐断（``LLM_TIMEOUT reason=ConnectTimeout``），看起来像"AI 坏了"。
        给到 20 秒，与 ``adapters/llm_client.Timeouts`` 保持同一个数。
        """
        return min(20.0, float(self.timeout_seconds))

    @property
    def read_timeout(self) -> float:
        return max(5.0, float(self.timeout_seconds) - self.connect_timeout)

    @property
    def consent_retry_cap(self) -> int:
        """同一 preview 只允许重试 1 次（API-CONTRACT §10.4）。"""

        return min(max(self.max_retries, 0), 1)

    # ---- 路径 ---------------------------------------------------------------------
    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def imports_dir(self) -> Path:
        return self.data_dir / "imports"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def runtime_path(self) -> Path:
        return self.data_dir / "runtime.json"

    @property
    def egress_log_path(self) -> Path:
        return self.logs_dir / "llm-egress.jsonl"

    def public_dict(self) -> dict[str, Any]:
        """给 ``GET /settings`` / ``GET /env`` 的安全快照（**不含 key**）。"""

        return {
            "provider": self.provider,
            "model": self.model,
            "model_analysis": self.model_analysis,
            "base_url": self.base_url,
            "key_set": self.key_set,
            "key_field": "LLM_API_KEY",
            "timeouts": {
                "connect_s": self.connect_timeout,
                "read_s": self.read_timeout,
                "total_s": self.timeout_seconds,
            },
            "allowed_hosts": self.allowed_hosts,
            "ready": self.ready,
        }


def _to_int(value: str, default: int, *, low: int, high: int, name: str, warnings: list[str]) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        warnings.append(f"{name} 不是整数，已回退默认值 {default}")
        return default
    if parsed < low or parsed > high:
        clamped = min(max(parsed, low), high)
        warnings.append(f"{name}={parsed} 超出范围 [{low},{high}]，已收敛为 {clamped}")
        return clamped
    return parsed


def load_config(
    *,
    environ: Mapping[str, str] | None = None,
    env_file_values: Mapping[str, str] | None = None,
    data_dir_override: Path | None = None,
) -> Config:
    """构造 :class:`Config`。缺失/非法值降级并记 warnings，不在启动期崩。"""

    values = resolve_env(env_file_values, environ)
    warnings: list[str] = []

    provider = (values.get("LLM_PROVIDER") or "deepseek").strip().lower()
    if provider not in PROVIDERS:
        warnings.append(f"LLM_PROVIDER={provider!r} 不在白名单 {PROVIDERS}，已按 off 处理")
        provider = "off"
    preset = PROVIDER_PRESETS[provider]

    base_url = (values.get("LLM_BASE_URL") or "").strip() or preset.base_url
    if base_url:
        base_url = base_url.rstrip("/")
    if provider not in ("off",) and not base_url:
        warnings.append("provider 需要 LLM_BASE_URL，但当前为空")

    model = (values.get("LLM_MODEL") or "").strip() or preset.model
    model_analysis = (values.get("LLM_MODEL_ANALYSIS") or "").strip() or model
    timeout_seconds = _to_int(
        values.get("LLM_TIMEOUT_SECONDS", "90"),
        90,
        low=5,
        high=600,
        name="LLM_TIMEOUT_SECONDS",
        warnings=warnings,
    )
    max_retries = _to_int(
        values.get("LLM_MAX_RETRIES", "1"),
        1,
        low=0,
        high=3,
        name="LLM_MAX_RETRIES",
        warnings=warnings,
    )
    app_port = _to_int(
        values.get("APP_PORT", "8765"),
        8765,
        low=1024,
        high=65535,
        name="APP_PORT",
        warnings=warnings,
    )

    raw_data_dir = data_dir_override or Path(values.get("DATA_DIR") or "./data")
    if not raw_data_dir.is_absolute():
        raw_data_dir = (PROJECT_ROOT / raw_data_dir).resolve()
    else:
        raw_data_dir = raw_data_dir.resolve()
    if not raw_data_dir.is_relative_to(PROJECT_ROOT):
        raise ConfigError(
            f"DATA_DIR 必须解析到 {PROJECT_ROOT} 之内，实际得到 {raw_data_dir}（ARCHITECTURE §5.3 禁令）"
        )

    return Config(
        provider=provider,
        base_url=base_url,
        model=model,
        model_analysis=model_analysis,
        api_key=(values.get("LLM_API_KEY") or "").strip(),
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        app_port=app_port,
        data_dir=raw_data_dir,
        warnings=warnings,
    )


# --------------------------------------------------------------------------------------
# .env 写入（``PUT /settings`` / ``POST /settings/api-key``）
# --------------------------------------------------------------------------------------

_ENV_LINE = re.compile(r"^(\s*(?:export\s+)?)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$")


def update_env_file(updates: Mapping[str, str], *, path: Path = ENV_PATH) -> None:
    """就地更新 .env 的指定键（保留注释/顺序），原子替换 + ``chmod 600``。

    * 只写 :data:`ENV_KEYS` 白名单内的键；
    * 传入空字符串表示「清空值但保留键名」（AC-LLM-05 要求）；
    * 写前写后都不打印值（key 不进日志）。
    """

    unknown = set(updates) - set(ENV_KEYS)
    if unknown:
        raise ConfigError(f"不允许写入 .env 的键：{sorted(unknown)}")

    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()

    remaining = dict(updates)
    for index, line in enumerate(lines):
        match = _ENV_LINE.match(line)
        if not match:
            continue
        prefix, key, eq, _old = match.groups()
        if key in remaining:
            lines[index] = f"{prefix}{key}{eq}{remaining.pop(key)}"

    for key, value in remaining.items():
        lines.append(f"{key}={value}")

    payload = "\n".join(lines).rstrip("\n") + "\n"
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise ConfigError(f"写入 {path} 失败：{exc}") from exc


# 进程内单例（Flask app 持有；测试可替换）
_current: Config | None = None


def get_config() -> Config:
    global _current
    if _current is None:
        _current = load_config()
    return _current


def set_config(cfg: Config) -> Config:
    global _current
    _current = cfg
    return cfg
