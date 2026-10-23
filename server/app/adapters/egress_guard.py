"""出网闸门：唯一允许发起外部 HTTP 的模块集合（``adapters/llm_client.py``）。

ARCHITECTURE §5 的「唯一出网模块」约束在这里落成可验证的代码：
* 白名单只由当前配置的 ``LLM_BASE_URL`` 推导，不做远程拉取；
* 任何非白名单 host 一律 ``EGRESS_BLOCKED``；
* 生产代码里除 llm_client 外不得出现 ``httpx``/``requests``/``urllib.request`` 调用，
  由 ``scripts/check_egress.py`` 静态扫描守住。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

from .. import config as config_mod
from ..errors import ApiError

#: 明确禁止的出网目标（本地回环以外的一切都要走白名单）
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class EgressDecision:
    allowed: bool
    host: str
    reason: str


def allowed_hosts(cfg: config_mod.Config | None = None) -> list[str]:
    """从配置推导白名单（去重、保序）。"""
    cfg = cfg or config_mod.get_config()
    hosts: list[str] = []
    for raw in (cfg.llm_base_url,):
        host = config_mod.host_of(raw or "")
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def check(url: str, cfg: config_mod.Config | None = None) -> EgressDecision:
    cfg = cfg or config_mod.get_config()
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https"):
        return EgressDecision(False, host, f"unsupported_scheme:{parsed.scheme}")
    if not host:
        return EgressDecision(False, host, "missing_host")
    if host in allowed_hosts(cfg):
        return EgressDecision(True, host, "whitelisted")
    return EgressDecision(False, host, "not_in_whitelist")


def assert_allowed(url: str, cfg: config_mod.Config | None = None) -> str:
    """通过返回 host，否则抛 403 EGRESS_BLOCKED（不泄露 key 或完整 URL）。"""
    decision = check(url, cfg)
    if not decision.allowed:
        cfg = cfg or config_mod.get_config()
        raise ApiError(
            "EGRESS_BLOCKED",
            "出网被拒绝：目标主机不在白名单内",
            details={"host": decision.host, "allowed_hosts": allowed_hosts(cfg)},
            hint="如需更换 LLM 服务，请先在设置页保存新的 Base URL（白名单会自动更新）",
        )
    return decision.host


def assert_hosts(urls: Iterable[str], cfg: config_mod.Config | None = None) -> list[str]:
    return [assert_allowed(url, cfg) for url in urls]
