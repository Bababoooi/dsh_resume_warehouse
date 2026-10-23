"""**下行只读**抓取客户端：唯一允许读取外部网页的模块。

与 ``llm_client.py``（唯一允许**上行**发数据的模块）的分工必须守住：

* 这里只做 ``GET``，不带任何用户字段（无 cookie、无 Authorization、无查询参数拼用户数据），
  UA 固定为 ``ResumeWarehouse/1.0 (local)`` —— 抓的是公开页面，不是「带着用户资料去问」。
* 域名白名单 + 开关 + 超时 + 跳转上限 + 私网地址拦截，任何一条不满足就拒绝，
  失败一律降级为「只用用户粘贴的 JD」，**不阻断分析**。

抓取结果按 URL 的 sha256 缓存到 ``data/files/``（24 小时），离线时同一页面不会反复打对方站点。
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx

from .. import config as config_mod
from .. import db as db_mod
from ..errors import ApiError

USER_AGENT = "ResumeWarehouse/1.0 (local)"
FETCH_TIMEOUT_SECONDS = 15.0
MAX_REDIRECTS = 3
MIN_BODY_CHARS = 200
CACHE_TTL_SECONDS = 24 * 3600
MAX_BYTES = 2 * 1024 * 1024

#: 未配置白名单时的默认集合（招聘/公司主页常见站点；用户可在设置里关掉整个功能）
DEFAULT_ALLOWED_HOSTS: tuple[str, ...] = (
    "www.zhipin.com",
    "zhipin.com",
    "jobs.bytedance.com",
    "careers.tencent.com",
    "talent.alibaba.com",
    "hr.163.com",
    "campus.meituan.com",
    "jobs.jd.com",
    "career.huawei.com",
    "www.liepin.com",
    "www.lagou.com",
    "www.yingjiesheng.com",
    "www.nowcoder.com",
)

_TAG_RE = re.compile(r"<(?P<tag>script|style|noscript)[^>]*>.*?</(?P=tag)>", re.S | re.I)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_BLOCK_RE = re.compile(r"</?(?:p|div|br|li|tr|h[1-6]|section|article)[^>]*>", re.I)
_TAG_ANY_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u00a0\u3000]+")
_BLANK_RE = re.compile(r"\n{3,}")


@dataclass
class FetchResult:
    url: str
    final_url: str
    host: str
    title: str
    text: str
    chars: int
    truncated: bool
    from_cache: bool
    fetched_at: str
    warnings: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "host": self.host,
            "title": self.title,
            "text": self.text,
            "chars": self.chars,
            "truncated": self.truncated,
            "from_cache": self.from_cache,
            "fetched_at": self.fetched_at,
            "warnings": list(self.warnings),
        }


# --------------------------------------------------------------------------------------
# 白名单与开关
# --------------------------------------------------------------------------------------


def allowed_hosts(cfg: config_mod.Config | None = None) -> list[str]:
    """白名单来自设置（``app_setting.fetch_allowed_hosts``），缺省用内置集合。"""
    extra: list[str] = []
    try:
        from ..repos import SettingsRepo  # 局部导入，避免循环

        raw = SettingsRepo().get_raw("fetch_allowed_hosts")
        if raw:
            # 设置层已按 JSON 解码（list / str 都可能出现），不要再假定是原始字符串
            if isinstance(raw, (list, tuple)):
                parsed = list(raw)
            else:
                text = str(raw).strip()
                parsed = json.loads(text) if text.startswith("[") else [text]
            if isinstance(parsed, list):
                extra = [str(item).strip().lower() for item in parsed if str(item).strip()]
    except Exception:  # 配置缺失不该让抓取功能整体不可用
        extra = []
    hosts = [host.lower() for host in DEFAULT_ALLOWED_HOSTS]
    for host in extra:
        if host not in hosts:
            hosts.append(host)
    return hosts


def fetch_enabled() -> bool:
    """``allow_web_fetch`` 默认开启（用户授权过），设置里可关。"""
    try:
        from ..repos import SettingsRepo

        raw = SettingsRepo().get_raw("allow_web_fetch")
    except Exception:
        return True
    if raw is None:
        return True
    return str(raw).strip().lower() not in ("0", "false", "off", "no", "")


def _host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _assert_public_host(host: str) -> None:
    """私网/回环/链路本地一律拒绝——防止把本机服务当成「网页」抓。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ApiError(
            "EGRESS_BLOCKED",
            f"域名无法解析：{host}",
            details={"reason": "unresolvable_host", "host": host},
            hint="请检查网址是否正确，或直接粘贴 JD 正文",
        )
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ApiError(
                "EGRESS_BLOCKED",
                "拒绝抓取内网地址",
                details={"reason": "private_address", "host": host, "address": address},
                hint="只能抓取公开网页；内网地址一律拒绝",
            )


def validate_url(url: str, *, cfg: config_mod.Config | None = None) -> str:
    """校验并归一化 URL；任何不满足条件的情况抛 403 ``EGRESS_BLOCKED``。"""
    raw = (url or "").strip()
    if not raw:
        raise ApiError(
            "EGRESS_BLOCKED",
            "缺少要抓取的网址",
            details={"reason": "missing_url"},
            hint="请提供公司招聘页/官网 URL，或直接粘贴 JD 正文",
        )
    if not fetch_enabled():
        raise ApiError(
            "EGRESS_BLOCKED",
            "联网抓取已在设置里关闭",
            details={"reason": "fetch_disabled"},
            hint="可在设置页打开「允许联网读取公司公开页面」，或直接粘贴 JD 正文",
        )
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https"):
        raise ApiError(
            "EGRESS_BLOCKED",
            "只支持 http/https 网址",
            details={"reason": "unsupported_scheme", "scheme": parts.scheme},
        )
    host = (parts.hostname or "").lower()
    allow = allowed_hosts(cfg)
    if not host or not any(host == item or host.endswith("." + item) for item in allow):
        raise ApiError(
            "EGRESS_BLOCKED",
            f"域名不在允许列表内：{host or '(空)'}",
            details={"reason": "host_not_allowed", "host": host, "allowed_hosts": allow},
            hint="可在设置里把该公司域名加入抓取白名单；或不抓网页，直接粘贴 JD 正文",
        )
    _assert_public_host(host)
    return raw


# --------------------------------------------------------------------------------------
# 缓存
# --------------------------------------------------------------------------------------


def _cache_path(url: str) -> Any:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    files = db_mod.get_paths().files
    files.mkdir(parents=True, exist_ok=True)
    return files / f"fetch_{digest[:32]}.json"


def _read_cache(url: str) -> dict[str, Any] | None:
    path = _cache_path(url)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    age = time.time() - float(payload.get("_cached_at") or 0)
    if age > CACHE_TTL_SECONDS:
        return None
    return payload


def _write_cache(url: str, payload: Mapping[str, Any]) -> None:
    path = _cache_path(url)
    data = dict(payload)
    data["_cached_at"] = time.time()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), "utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------------------
# HTML → 纯文本
# --------------------------------------------------------------------------------------


def html_to_text(html: str) -> tuple[str, str]:
    """返回 ``(title, text)``；去掉 script/style/注释，块级标签转换行。"""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = _TAG_ANY_RE.sub("", title_match.group(1)).strip() if title_match else ""
    body = _COMMENT_RE.sub(" ", html)
    body = re.sub(r"<title[^>]*>.*?</title>", " ", body, flags=re.S | re.I)
    body = _TAG_RE.sub(" ", body)
    body = _BLOCK_RE.sub("\n", body)
    body = _TAG_ANY_RE.sub(" ", body)
    body = (
        body.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    lines = [_WS_RE.sub(" ", line).strip() for line in body.splitlines()]
    text = "\n".join(line for line in lines if line)
    text = _BLANK_RE.sub("\n\n", text).strip()
    return title, text


# --------------------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------------------


def fetch_public_page(
    url: str,
    *,
    cfg: config_mod.Config | None = None,
    use_cache: bool = True,
    client: httpx.Client | None = None,
) -> FetchResult:
    """抓一个公开页面。**只读、只 GET、零用户字段**；失败抛 ApiError（调用方降级）。"""
    target = validate_url(url, cfg=cfg)
    host = _host_of(target)
    warnings: list[dict[str, Any]] = []

    if use_cache:
        cached = _read_cache(target)
        if cached is not None:
            text = str(cached.get("text") or "")
            return FetchResult(
                url=target,
                final_url=str(cached.get("final_url") or target),
                host=str(cached.get("host") or host),
                title=str(cached.get("title") or ""),
                text=text,
                chars=len(text),
                truncated=bool(cached.get("truncated")),
                from_cache=True,
                fetched_at=str(cached.get("fetched_at") or db_mod.utcnow_iso()),
                warnings=[],
            )

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    owns_client = client is None
    http = client or httpx.Client(
        timeout=httpx.Timeout(connect=5.0, read=FETCH_TIMEOUT_SECONDS, write=5.0, pool=5.0),
        follow_redirects=False,
    )
    try:
        current = target
        for _hop in range(MAX_REDIRECTS + 1):
            try:
                response = http.get(current, headers=headers)
            except httpx.TimeoutException as exc:
                raise ApiError(
                    "TIMEOUT",
                    "抓取超时（15 秒）",
                    details={"reason": "timeout", "url": current},
                    hint="对方站点响应过慢；可直接粘贴 JD 正文继续分析",
                    http_status=504,
                ) from exc
            except httpx.HTTPError as exc:
                raise ApiError(
                    "FETCH_UNREACHABLE",
                    "抓取失败：无法连接目标站点",
                    details={"reason": "network_error", "url": current, "error": type(exc).__name__},
                    hint="可直接粘贴 JD 正文继续分析",
                ) from exc

            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    break
                current = str(httpx.URL(current).join(location))
                validate_url(current, cfg=cfg)  # 每一跳都重新过白名单与私网检查
                continue
            break
        else:
            raise ApiError(
                "EGRESS_BLOCKED",
                "跳转次数过多（>3）",
                details={"reason": "too_many_redirects", "url": target},
            )

        if response.status_code >= 400:
            raise ApiError(
                "EGRESS_BLOCKED",
                f"目标站点返回 {response.status_code}",
                details={"reason": "http_error", "status": response.status_code, "url": str(response.url)},
                hint="该页面可能需登录或有反爬限制；可直接粘贴 JD 正文",
            )

        content_type = (response.headers.get("content-type") or "").lower()
        if "html" not in content_type and "text" not in content_type:
            raise ApiError(
                "EGRESS_BLOCKED",
                f"不支持的内容类型：{content_type or '未知'}",
                details={"reason": "unsupported_content_type", "content_type": content_type},
            )

        raw = response.content[:MAX_BYTES]
        truncated = len(response.content) > MAX_BYTES
        html = raw.decode(response.encoding or "utf-8", errors="replace")
        title, text = html_to_text(html)
        if truncated:
            warnings.append(
                {
                    "code": "FETCH_TRUNCATED",
                    "severity": "warn",
                    "message": "页面超过 2MB，只取前 2MB 内容",
                    "details": {"bytes": MAX_BYTES},
                }
            )
        if len(text) < MIN_BODY_CHARS:
            # 契约 §7：正文过短是「页面没用」，不是「出网被拒」→ 422 VALIDATION_ERROR
            raise ApiError(
                "VALIDATION_ERROR",
                "抓到的正文太短（<200 字符），判定为无效页面",
                details={
                    "reason": "EMPTY_BODY",
                    "chars": len(text),
                    "url": str(response.url),
                    "fields": [
                        {
                            "field": "url",
                            "rule": "EMPTY_BODY",
                            "message": "页面正文不足 200 字符，可能是脚本渲染的空壳",
                        }
                    ],
                },
                hint="可直接粘贴 JD 正文继续分析",
            )

        fetched_at = db_mod.utcnow_iso()
        result = FetchResult(
            url=target,
            final_url=str(response.url),
            host=_host_of(str(response.url)) or host,
            title=title[:200],
            text=text,
            chars=len(text),
            truncated=truncated,
            from_cache=False,
            fetched_at=fetched_at,
            warnings=warnings,
        )
        _write_cache(
            target,
            {
                "url": target,
                "final_url": result.final_url,
                "host": result.host,
                "title": result.title,
                "text": result.text,
                "truncated": result.truncated,
                "fetched_at": fetched_at,
            },
        )
        return result
    finally:
        if owns_client:
            http.close()


def probe_host(host: str) -> bool:
    """给设置页用的轻量判断：域名是否在白名单内（不联网）。"""
    target = (host or "").strip().lower()
    return bool(target) and any(
        target == item or target.endswith("." + item) for item in allowed_hosts()
    )
