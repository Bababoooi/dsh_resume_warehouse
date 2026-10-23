"""前端可用性的机器判据：离线自包含、页面真的挂载、没有任何外部资源。

这三条必须在 CI 里可验，否则「零 CDN 离线可用」只是口号：

1. ``GET /`` 能返回界面，且 ``GET /src/pages/<每个路由>.js`` 都 200（缺一个页面就是半成品）；
2. ``web/`` 下不出现任何外部 http(s) 地址（字体、图标、脚本一律本地）；
3. 页面代码不用 ``innerHTML``（用户内容只走 Text 节点，避免 XSS 与解析开销）。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "web"
BOOT = WEB / "src" / "boot.js"


def shell_source() -> str:
    """页面骨架 + 启动脚本。

    启动脚本已从 ``index.html`` 的内联 ``<script type="module">`` 搬成外部文件
    ``web/src/boot.js``（CSP ``script-src 'self'`` 会拦内联脚本，见
    ``tests/test_web_boot.py``），所以「外壳里有没有这段代码」要两处合起来看。
    """
    return (WEB / "index.html").read_text(encoding="utf-8") + "\n" + BOOT.read_text(encoding="utf-8")


def test_index_served(app_env):
    _app, client, _data = app_env
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '<script type="module" src="./src/boot.js"></script>' in html
    assert 'id="view"' in html
    assert "mountPage" in BOOT.read_text(encoding="utf-8")


def test_every_route_has_a_page_module(app_env):
    _app, client, _data = app_env
    html = shell_source()
    routes = re.findall(r"^\s*(\w+): \{ label:", html, re.M)
    assert len(routes) >= 7, f"路由表异常：{routes}"
    for route in routes:
        path = WEB / "src" / "pages" / f"{route}.js"
        assert path.is_file(), f"路由 {route} 没有页面模块"
        response = client.get(f"/src/pages/{route}.js")
        assert response.status_code == 200, f"{route}.js 不能被浏览器取到"
        assert "export" in response.get_data(as_text=True)


def test_no_external_resources_anywhere():
    offenders = []
    sources = [WEB / "index.html", *(WEB / "src").rglob("*.js"), *(WEB / "src").rglob("*.css")]
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"https?://[^\s\"'()<>]+", text):
            url = match.group(0)
            # SVG 命名空间与注释里的本地地址不是资源引用
            if "w3.org" in url or url.startswith(("http://127.0.0.1", "http://localhost")) or "…" in url:
                continue
            offenders.append(f"{path.relative_to(WEB)}: {url}")
    assert offenders == [], f"前端不许引用外部资源：{offenders}"


def test_pages_never_use_innerHtml():
    offenders = []
    for path in [*(WEB / "src" / "pages").rglob("*.js"), WEB / "src" / "api.js"]:
        text = path.read_text(encoding="utf-8")
        if re.search(r"\.innerHTML\s*=", text):
            offenders.append(str(path.relative_to(WEB)))
    assert offenders == [], f"页面禁止 innerHTML：{offenders}"


def test_api_client_is_wired_to_v1_envelope():
    text = (WEB / "src" / "api.js").read_text(encoding="utf-8")
    assert "/api/v1/health" in text
    assert "payload.ok === false" in text, "必须按统一错误信封处理失败"
    assert "payload.data" in text


def test_static_assets_are_not_cached_aggressively(app_env):
    _app, client, _data = app_env
    response = client.get("/src/api.js")
    assert response.status_code == 200
    assert "no-cache" in response.headers.get("Cache-Control", "")


def test_api_prefix_is_not_shadowed_by_static_route(app_env):
    _app, client, _data = app_env
    # 静态路由用的是 <path:filename>，必须不吞掉 /api/**
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/definitely-not-a-route").status_code == 404


@pytest.mark.parametrize("path", ["/nope.js", "/src/pages/missing.js", "/../etc/passwd"])
def test_static_route_rejects_missing_or_escaping(app_env, path):
    _app, client, _data = app_env
    assert client.get(path).status_code == 404


# ---------------------------------------------------------------------------
# 顶栏的两个「一眼就坏」的缺陷（t12 修的）：面包屑只显示一根斜杠、状态灯永远 idle
# ---------------------------------------------------------------------------


def test_breadcrumbs_are_passed_as_objects_not_bare_strings():
    """``topBar`` 读的是 ``{label, href, current}``；传字符串会渲染成一串空 span + 斜杠。

    实测过：``crumbs: ["简历仓库", ROUTES[...].crumb]`` 在页面上就是一根 ``/``。
    """
    html = shell_source()
    assert 'crumbs: ["简历仓库"' not in html, "面包屑不能传裸字符串"
    block = html[html.index("crumbs:") : html.index("crumbs:") + 260]
    assert "label:" in block, block
    assert "current: true" in block, block


def test_status_bar_is_probed_on_boot_and_dispatches_rw_status():
    """状态条此前永远 idle：没有任何地方派发 ``rw:status``。启动时必须探一次并派发。"""
    html = shell_source()
    assert "rw:status" in html
    # 必须有真实的探针代码（而不是只在注释里说"页面层会派发"）
    assert "/api/v1/llm/status" in html, "AI 状态要来自真实端点"
    assert "/api/v1/env" in html, "字体状态要来自真实端点"
    probe = html[html.index("async function probeStatus") :]
    assert 'out.ai = "ok"' in probe
    assert 'out.font = "ok"' in probe
    assert 'new CustomEvent("rw:status"' in probe


def test_status_labels_match_probe_states():
    """派发的是 ok/warn/bad/idle 四个键，文案表必须都有对应项。"""
    html = shell_source()
    for key in ('ok: "DeepSeek 已就绪"', 'warn: "模型未配置"', 'bad: "调用失败"', 'ok: "中文字体可用"'):
        assert key in html, key
