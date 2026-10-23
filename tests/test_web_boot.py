"""启动脚本与 CSP 的自洽性——这两条曾让「整站 7 页全白但接口全绿」。

案情（2026-10-23，两次都栽在「页面打不开、API 全 200」）：

1. ``GET /`` 的 CSP 是 ``script-src 'self'``，而启动脚本当时是 **内联**
   ``<script type="module">``（9000+ 字符）——浏览器直接拒绝执行，
   应用根本没启动，只剩静态外壳与骨架条。
2. 把它搬成 ``web/src/boot.js`` 后，里面的 import 仍按 **web 根目录** 写
   ``./src/components/...``，于是解析成 ``/src/src/components/...`` 全部 404，
   页面依旧全白——而这次连错误都进不了 catch（模块加载失败不进 try）。

所以判据必须是「结构」而不是「截图字节数」，这两条就是护栏。
"""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"
INDEX = WEB / "index.html"
BOOT = WEB / "src" / "boot.js"

LOADER_CSP_HEADER = "Content-Security-Policy"
PAGE_CSP = __import__("app", fromlist=["PAGE_CSP"]).PAGE_CSP


def _script_tags(html: str) -> list[tuple[str, str]]:
    """返回 [(attrs, body), ...]。"""
    return [
        (m.group("attrs") or "", m.group("body") or "")
        for m in re.finditer(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", html, re.S)
    ]


def test_no_inline_script_under_strict_csp():
    """CSP 不给 `unsafe-inline` 时，`index.html` 不许有内联脚本。

    没有这条，任何人把启动脚本粘回 `index.html` 都会让整站静默白屏。
    """
    assert "'unsafe-inline'" not in PAGE_CSP.split("script-src", 1)[1].split(";", 1)[0], (
        "PAGE_CSP 的 script-src 不应放宽到 'unsafe-inline'"
    )
    inline = [(attrs, body) for attrs, body in _script_tags(INDEX.read_text(encoding="utf-8")) if "src=" not in attrs and body.strip()]
    assert inline == [], f"index.html 里还有 {len(inline)} 段内联脚本，会被 CSP 拦掉：{inline[:1]}"


def test_index_loads_boot_module_from_src():
    """启动脚本必须是外部模块文件，且路径指向 `src/boot.js`。"""
    html = INDEX.read_text(encoding="utf-8")
    tags = _script_tags(html)
    module_srcs = [attrs for attrs, _ in tags if 'type="module"' in attrs and "src=" in attrs]
    assert module_srcs, "index.html 里没有 type=module 的外链脚本"
    assert any("./src/boot.js" in attrs for attrs in module_srcs), module_srcs
    assert BOOT.exists(), "web/src/boot.js 不存在"


def test_boot_js_has_no_extra_src_prefix():
    """boot.js 的 import 相对它自己的位置，不许再出现 `./src/` 前缀。

    这是 404 的根因（`/src/src/components/*.js`），grep 计数必须为 0。
    """
    text = BOOT.read_text(encoding="utf-8")
    offenders = [line.strip() for line in text.splitlines() if "./src/" in line]
    assert offenders == [], f"boot.js 仍有 `./src/` 前缀（会解析成 /src/src/...）：{offenders}"


def test_every_boot_import_resolves_to_an_existing_file():
    """把 boot.js 里的相对 import 落到磁盘上逐个核对，缺一个就是白屏。"""
    text = BOOT.read_text(encoding="utf-8")
    specifiers = re.findall(r"""from\s+["'](\.[^"']+)["']""", text)
    specifiers += re.findall(r"""import\(\s*[`"'](\.[^`"']+)[`"']""", text)
    assert specifiers, "boot.js 没有任何相对 import，说明解析写错了"

    base = BOOT.parent
    missing = []
    for spec in specifiers:
        cleaned = spec.replace("${key}", "workbench")
        target = (base / cleaned).resolve()
        if not target.exists():
            missing.append(f"{spec} -> {target}")
    assert missing == [], f"boot.js 有 {len(missing)} 个 import 指不到文件：{missing}"


def test_index_declares_icon_without_network_404():
    """`<link rel="icon">` 必须指向存在的东西或 data:，否则每次巡检都多一条 404 噪声。"""
    html = INDEX.read_text(encoding="utf-8")
    match = re.search(r'<link[^>]+rel="icon"[^>]*>', html)
    assert match, "index.html 没有声明 rel=icon"
    tag = match.group(0)
    href = re.search(r'href="([^"]+)"', tag)
    assert href, tag
    value = href.group(1)
    if value.startswith("data:"):
        return
    assert (WEB / value.lstrip("./")).exists(), f"favicon 指向不存在的文件：{value}"


def test_page_csp_is_served_with_strict_script_src(app_env):
    """行为侧：`GET /` 的 CSP 头必须还是 `script-src 'self'`（放宽了就与上面对不上）。"""
    _app, client, _data_dir = app_env
    response = client.get("/")
    csp = response.headers.get(LOADER_CSP_HEADER, "")
    assert "script-src 'self'" in csp, csp
    assert "'unsafe-inline'" not in csp.split("script-src", 1)[1].split(";", 1)[0], csp
    body = response.get_data(as_text=True)
    assert '<script type="module" src="./src/boot.js"></script>' in body
