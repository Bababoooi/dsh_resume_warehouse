"""浏览器级 AUTO 检查：AC-UI-05 / 06 / 07 / 09。

为什么必须真开浏览器：这四条判据都在「渲染之后」——红字与深链、三栏布局、错误码人话、
任务中断提示。用 requests 只能证明 HTML 里有字符串，证明不了用户真的看得见。

做法：
1. 用**临时 DATA_DIR** 起一个真服务（`server/server.py --port <空闲端口>`）；
2. 用 CDP 直连 Chrome（`scripts/check_pages_headless.py` 里那套 Session 复用），
   `Page.addScriptToEvaluateOnNewDocument` 注入 fetch 桩，再导航到 `#/...`；
3. 断言 `#view` 的可见文本 / 计算样式，而不是源码。

环境缺失（没有 Chrome / 没装 websocket-client）时 **skip** 而不是 fail：这类用例是
「有浏览器就更强」的护栏，不该在无头 CI 上制造假红。
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server" / "server.py"
CHECKER = ROOT / "scripts" / "check_pages_headless.py"


def check(ac: str):
    """账本（make_index）认的标记：`@check("AC-…")` 必须紧贴 `def` 上一行。"""

    def wrap(fn):
        fn.ac_id = ac
        return fn

    return wrap


def _load_checker():
    """复用巡检器的 CDP 小工具（Session/find_chrome/free_port/...），避免两套实现漂移。"""
    spec = importlib.util.spec_from_file_location("rw_pages_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["rw_pages_check"] = module
    spec.loader.exec_module(module)
    return module


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_health(base: str, *, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/api/v1/health", timeout=1.0) as resp:  # noqa: S310 - 本机
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = exc
            time.sleep(0.2)
    raise RuntimeError(f"服务没起来：{last}")


def _api(base: str, method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"{base}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(request, timeout=10.0) as resp:  # noqa: S310 - 本机
        return json.loads(resp.read().decode("utf-8"))


# fetch 桩：按 URL 子串匹配，命中就返回预置 body（不联网、不依赖后端数据形态）
STUB_JS = """
(() => {
  const original = window.fetch.bind(window);
  const table = %s;  // [{match, status, body}]
  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    const method = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
    for (const rule of table) {
      if (url.includes(rule.match) && (!rule.method || rule.method === method)) {
        const payload = typeof rule.body === "string" ? rule.body : JSON.stringify(rule.body);
        return new Response(payload, {status: rule.status || 200, headers: {"Content-Type": "application/json"}});
      }
    }
    return original(input, init);
  };
})();
"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    """一个真服务 + 一条 CDP 连接（模块级，四个用例共用，避免反复起浏览器）。"""
    checker = _load_checker()
    try:
        chrome = checker.find_chrome(os.environ.get("CHROME_PATH"))
    except SystemExit:
        pytest.skip("本机没有 Chrome/Chromium：浏览器级 AC 跳过（不判红）")
    try:
        import websocket  # noqa: F401
    except ImportError:
        pytest.skip("缺 websocket-client：浏览器级 AC 跳过（不判红）")

    # DATA_DIR 必须落在仓库内（ARCHITECTURE §5.3 禁令），所以不能用 tmp_path（/private/tmp）
    data_dir = ROOT / "data" / "_tests" / f"rw-ui-{uuid.uuid4().hex[:8]}"
    data_dir.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ)
    env.update(
        {
            "DATA_DIR": str(data_dir),
            "APP_PORT": str(port),
            "PYTHONPATH": str(ROOT / "server"),
            "PYTHONUNBUFFERED": "1",
        }
    )
    proc = subprocess.Popen(  # noqa: S603 - 固定命令
        [sys.executable, str(SERVER), "--port", str(port)],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_health(base)
        # 档案：姓名 + 学校齐（其余数据都用 fetch 桩替代，保持这条用例只测界面行为）
        _api(base, "PUT", "/api/v1/profile", {"name_zh": "张三", "school_zh": "示例大学", "phone": "13800138000"})

        debug_port = checker.free_port()
        profile_dir = tmp_path_factory.mktemp("rw-ui-chrome")
        proc_chrome = subprocess.Popen(  # noqa: S603 - 固定命令
            [
                chrome,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                f"--user-data-dir={profile_dir}",
                f"--remote-debugging-port={debug_port}",
                "--remote-allow-origins=*",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        checker.wait_for_debugger(debug_port)
        target = checker.page_target(debug_port)
        session = checker.Session(target["webSocketDebuggerUrl"])
        for method in ("Page.enable", "Runtime.enable", "Log.enable"):
            session.call(method)
        yield {"checker": checker, "session": session, "base": base}
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)
        try:
            session.close()  # type: ignore[possibly-undefined]
        except Exception:  # noqa: BLE001
            pass
        for process in (locals().get("proc_chrome"), proc):
            if process is None:
                continue
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover
                process.kill()


def _navigate(site: dict, route: str, stubs: list[dict] | None = None, *, settle: float = 1.6) -> str:
    """注入 fetch 桩 → 打开 route → 等真实时间 → 返回 `#view` 可见文本。"""
    checker = site["checker"]
    session = site["session"]
    # 关键：上一轮的桩必须按 identifier 精确移除。早先这里传的是空串（等于不删），
    # 桩会一轮轮累积、先匹配先赢——后面的用例拿到的其实是前面用例的假响应，
    # 于是「功能明明是好的，用例却红」。identifier 是 add 时返回的，必须存下来。
    previous = site.pop("stub_identifier", None)
    if previous:
        session.call("Page.removeScriptToEvaluateOnNewDocument", {"identifier": previous})
    if stubs:
        source = STUB_JS % json.dumps(stubs, ensure_ascii=False)
        added = session.call("Page.addScriptToEvaluateOnNewDocument", {"source": source})
        site["stub_identifier"] = ((added or {}).get("result") or {}).get("identifier")
    # 同一路由连续导航是「同文档跳转」，Chrome 不会重新加载页面 —— 上一轮的 DOM
    # （包括上一次的错误红字）会原样留着，看起来像「第二个错误码没渲染」。加时间戳
    # 强制真正的文档级 reload。
    bust = "" if "?" in route else f"?t={time.time_ns()}"
    session.call("Page.navigate", {"url": f"{site['base']}/{bust}#{route}"})
    time.sleep(settle)
    session.drain(0.3)
    return str(checker.evaluate(session, "document.querySelector('#view').innerText") or "")


def _eval(site: dict, expression: str):
    site["session"].call("Runtime.enable")
    return site["checker"].evaluate(site["session"], expression)


@check("AC-UI-07")
def test_ac_ui_07_no_horizontal_scroll_at_1280(site):
    """AC-UI-07：1280 宽无横向滚动；1440 宽组装页三栏都在。"""
    # 没有模板时组装页只显示一条警告、不会渲染三栏骨架；先给一个模板桩，
    # 否则这里测到的是「空态」而不是「三栏布局」（假绿）。
    stubs = [
        {"match": "/api/v1/profile", "body": {"ok": True, "data": {"name_zh": "张三", "school_zh": "示例大学", "missing": []}}},
        {
            "match": "/api/v1/templates",
            "body": {"ok": True, "data": {"items": [{"id": "tpl_stub", "name": "UI 模板", "lang": "zh", "is_default": True}]}},
        },
        {"match": "/naming/validate", "method": "POST", "body": {"ok": True, "data": {"valid": True, "filename": "后端实习生-张三-示例大学.pdf", "errors": [], "warnings": [], "variables": []}}},
    ]
    for width, height in ((1280, 800), (1440, 900)):
        _eval(site, f"window.innerWidth")  # 触发一次求值，确保页面已就绪
        site["session"].call(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
        )
        text = _navigate(site, "/builds", stubs)
        assert "这次投什么" in text, f"{width} 宽组装页没渲染出来：{text[:200]!r}"
        overflow = _eval(site, "document.scrollingElement.scrollWidth - window.innerWidth")
        assert overflow <= 1, f"{width}px 宽出现横向滚动：超出 {overflow}px"
    columns = _eval(
        site,
        """(() => {
          const el = document.querySelector('.split--build');
          if (!el) return 'no-split';
          return getComputedStyle(el).gridTemplateColumns.split(' ').filter(Boolean).length;
        })()""",
    )
    assert columns == 3, f"1440 宽组装页应是三栏，实际 {columns}"

    # 盲点补充（实测发现）：`document.scrollingElement` 只能抓到「整个文档级」的横向滚动。
    # 三栏被写死成固定像素宽时，外层容器 `overflow: hidden` 会把它**裁掉**而不是滚动，
    # 文档级 overflow 仍然是 0 —— 用户看到的是右栏被切掉，测试却绿。
    # 所以这里改测三栏容器自身：内容宽度必须塞得进它的可视宽度。
    for width, height in ((1280, 800), (1440, 900)):
        site["session"].call(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
        )
        _navigate(site, "/builds", stubs)
        box = _eval(
            site,
            """(() => {
              const el = document.querySelector('.split--build');
              if (!el) return 'no-split';
              return [Math.round(el.scrollWidth), Math.round(el.clientWidth), Math.round(window.innerWidth)].join('/');
            })()""",
        )
        assert box != "no-split", f"{width} 宽组装页没有三栏容器"
        content, viewport_box, window_w = (int(part) for part in box.split("/"))
        assert content <= viewport_box + 1, (
            f"{width}px 宽下三栏内容被裁切：容器内容宽 {content}px > 可视宽 {viewport_box}px（窗口 {window_w}px）"
        )


@check("AC-UI-09")
def test_ac_ui_09_error_codes_render_chinese_next_steps(site):
    """AC-UI-09：五种错误码都要出人话 + 下一步，绝不把 JSON 原样糊到脸上。"""
    cases = {
        "NOT_FOUND": "找不到这条数据",
        "CONFLICT": "数据已被改动",
        "VALIDATION_ERROR": "提交的内容有问题",
        "LLM_DISABLED": "模型通道已关闭",
        "FILE_IN_USE": "这个文件还有地方在用",
    }
    for code, title in cases.items():
        stubs = [
            {
                "match": "/api/v1/packages",
                "status": 409 if code == "CONFLICT" else 400,
                "body": {"ok": False, "error": {"code": code, "message": "演示用错误", "details": {"secret": "raw"}}},
            }
        ]
        text = _navigate(site, "/warehouse", stubs)
        assert title in text, f"{code} 没有渲染对应人话（期望「{title}」）：{text[:400]!r}"
        assert '"details"' not in text and '"ok":false' not in text.replace(" ", ""), f"{code} 把 JSON 糊到了界面上"


@check("AC-UI-06")
def test_ac_ui_06_interrupted_job_shows_chinese_notice(site):
    """AC-UI-06：导出中服务重启 → 任务变「已中断」，界面给人话而不是一直转圈。"""
    # 顺序即优先级（先匹配先赢）：子资源路径必须先于 `/api/v1/builds`，
    # 否则 `/builds/<id>/assemble` 会被「创建构建」那条规则吃掉。
    stubs = [
        {"match": "/api/v1/jobs/job_stub", "body": {"ok": True, "data": {"id": "job_stub", "status": "interrupted", "error_json": {"code": "JOB_INTERRUPTED", "message": "服务重启，任务已中断"}}}},
        {"match": "/naming/validate", "method": "POST", "body": {"ok": True, "data": {"valid": True, "filename": "后端实习生-张三-示例大学.pdf", "errors": [], "warnings": [], "variables": []}}},
        {"match": "/api/v1/profile", "body": {"ok": True, "data": {"name_zh": "张三", "school_zh": "示例大学", "missing": []}}},
        {"match": "/api/v1/templates", "body": {"ok": True, "data": {"items": [{"id": "tpl_stub", "name": "UI 模板", "lang": "zh", "is_default": True}]}}},
        {"match": "/selections", "method": "PUT", "body": {"ok": True, "data": {"build_id": "build_stub", "selections": []}}},
        {"match": "/assemble", "method": "POST", "body": {"ok": True, "data": {"sections": [{"heading": "项目经历", "entries": [{}, {}]}], "warnings": [], "competitiveness_summary": {}}}},
        {"match": "/export", "method": "POST", "status": 202, "body": {"ok": True, "data": {"job_id": "job_stub"}}},
        {"match": "/api/v1/builds", "method": "POST", "status": 201, "body": {"ok": True, "data": {"id": "build_stub"}}},
    ]
    _navigate(site, "/builds", stubs)
    assert _eval(site, "!!document.querySelector('#bd-position')"), "组装页没渲染出来"
    _eval(site, "(() => { const el=document.querySelector('#bd-position'); el.value='后端实习生'; el.dispatchEvent(new Event('input',{bubbles:true})); })()")
    time.sleep(0.8)
    clicked = _eval(
        site,
        """(() => {
          const btn = Array.from(document.querySelectorAll('button')).find((b) => (b.textContent || '').includes('组装预览'));
          if (!btn) return 'no-button';
          btn.click();
          return 'clicked';
        })()""",
    )
    assert clicked == "clicked", clicked
    time.sleep(1.0)
    exported = _eval(
        site,
        """(() => {
          const btn = Array.from(document.querySelectorAll('button')).find((b) => (b.textContent || '').includes('导出 PDF'));
          if (!btn) return 'no-export';
          btn.click();
          return 'clicked';
        })()""",
    )
    assert exported == "clicked", f"组装成功后应出现「导出 PDF」按钮：{exported}／{str(_eval(site, "document.querySelector('#view').innerText") or "")[-400:]!r}"
    time.sleep(1.5)
    text = str(_eval(site, "document.querySelector('#view').innerText") or "")
    assert "任务已中断" in text, f"中断没有给人话提示：{text[-600:]!r}"
    assert "正在渲染" not in text, "还在转圈：中断状态必须收尾"


@check("AC-UI-05")
def test_ac_ui_05_naming_error_links_to_profile(site):
    """AC-UI-05：清空岗位名 → 红字 + 「去个人资料」深链（报错必须带下一步）。"""
    stubs = [
        {"match": "/api/v1/profile", "body": {"ok": True, "data": {"name_zh": "", "school_zh": "", "missing": ["姓名", "学校"]}}},
        {"match": "/naming/validate", "method": "POST", "body": {"ok": True, "data": {"valid": False, "filename": "", "errors": [{"code": "NAMING_MISSING_VAR", "message": "缺少 {name}", "field": "name"}], "warnings": [], "variables": []}}},
    ]
    _navigate(site, "/builds", stubs, settle=2.0)
    text = str(_eval(site, "document.querySelector('#view').innerText") or "")
    assert "文件名还不能生成" in text, text[:400]
    tone = _eval(
        site,
        """(() => {
          const el = document.querySelector('#view .ui-callout--danger');
          if (!el) return 'no-danger';
          return el.getAttribute('role') === 'alert' ? 'alert' : 'no-alert';
        })()""",
    )
    assert tone == "alert", f"缺字段必须用红色提示（role=alert），实际 {tone}"
    link = _eval(
        site,
        """(() => {
          const a = Array.from(document.querySelectorAll('#view a')).find((x) => (x.textContent || '').includes('去个人资料'));
          return a ? a.getAttribute('href') : 'no-link';
        })()""",
    )
    assert link == "#/profile", f"深链缺失或指向不对：{link}"


@check("AC-UI-08")
def test_ac_ui_08_degraded_font_shows_banner_and_disables_export(site):
    """字体不可用：必须红条说清楚 + 导出按钮禁用（不能等用户点了才报 FONT_UNAVAILABLE）。

    注入口子在 `/api/v1/env`：它是启动自检的一部分，桩掉它等于模拟「这台机器没装宋体」，
    不需要真去 uninstall 字体，也不需要重起服务。
    """
    stubs = [
        {"match": "/api/v1/jobs/job_stub", "body": {"ok": True, "data": {"id": "job_stub", "status": "succeeded"}}},
        {"match": "/naming/validate", "method": "POST", "body": {"ok": True, "data": {"valid": True, "filename": "后端实习生-张三-示例大学.pdf", "errors": [], "warnings": [], "variables": []}}},
        {"match": "/api/v1/profile", "body": {"ok": True, "data": {"name_zh": "张三", "school_zh": "示例大学", "missing": []}}},
        {"match": "/api/v1/templates", "body": {"ok": True, "data": {"items": [{"id": "tpl_stub", "name": "UI 模板", "lang": "zh", "is_default": True}]}}},
        {
            "match": "/api/v1/env",
            "body": {
                "ok": True,
                "data": {
                    "fonts": {"ok": False, "primary": None, "bold": None, "chain": []},
                    "render": {"pdf_primary": "reportlab", "pdf_fallback": "chrome"},
                    "llm": {"ready": True},
                },
            },
        },
        {"match": "/selections", "method": "PUT", "body": {"ok": True, "data": {"build_id": "build_stub", "selections": []}}},
        {"match": "/assemble", "method": "POST", "body": {"ok": True, "data": {"sections": [{"heading": "项目经历", "entries": [{}]}], "warnings": [], "competitiveness_summary": {}}}},
        {"match": "/api/v1/builds", "method": "POST", "status": 201, "body": {"ok": True, "data": {"id": "build_stub"}}},
    ]
    text = _navigate(site, "/builds", stubs)
    assert "没有找到中文字体" in text, f"字体不可用却没有红条：{text[:300]!r}"

    # 先组装，再看导出按钮是否被禁用
    assert _eval(
        site,
        """(() => {
          const btn = Array.from(document.querySelectorAll('button')).find((b) => (b.textContent || '').includes('组装预览'));
          if (!btn) return 'no-button';
          btn.click();
          return 'clicked';
        })()""",
    ) == "clicked"
    time.sleep(1.5)
    export_state = _eval(
        site,
        """(() => {
          const btn = Array.from(document.querySelectorAll('button')).find((b) => (b.textContent || '').includes('导出 PDF'));
          if (!btn) return 'no-export';
          return btn.disabled ? 'disabled' : 'enabled';
        })()""",
    )
    assert export_state == "disabled", f"缺字体时导出按钮必须禁用，实际 {export_state}"
