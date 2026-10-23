#!/usr/bin/env python3
"""七个页面逐个真跑一遍：用 Chrome DevTools Protocol 读真实 DOM 与控制台。

为什么不用 `--virtual-time-budget --screenshot`
-----------------------------------------------
截图方案把时间「冻住」了：页面脚本还没跑完就截图，得到一张 8KB 的空壳，
看起来像「页面白屏」，实际是测量方法错。截图字节数还会随缓存/时序漂移，
用它当判据会同时产生假红与假绿——本项目已经栽过一次（CSP 把内联启动
脚本拦掉，7 个页面全白，但截图字节数看上去「只有 2 页异常」）。

这里改成 CDP：
  1. 起 Chrome，带 `--remote-debugging-port` 与 `--remote-allow-origins=*`；
  2. 连上页面 target，`Log.enable` / `Runtime.enable` / `Page.enable`；
  3. `Page.navigate` 到 `#/<route>`，然后**真实 sleep**（默认 2.0s）；
  4. `Runtime.evaluate` 取 `#view` 的 `innerText` 与 `h1`；
  5. 同时收集 `Log.entryAdded`（含 CSP 违规）与 `Runtime.exceptionThrown`。

判据（任一不满足即 FAIL，退出码 1）
  * `#view` 正文 ≥ `--min-chars`（默认 120）；
  * `#view` 里能取到该页标题（`ROUTES[key].label` 或 `h1`）；
  * 该页没有 CSP 违规、没有未捕获异常。

用法
----
    .venv/bin/python scripts/check_pages_headless.py            # 全部 7 页
    .venv/bin/python scripts/check_pages_headless.py --route builds
    .venv/bin/python scripts/check_pages_headless.py --base http://127.0.0.1:8765
    .venv/bin/python scripts/check_pages_headless.py --json      # 机器可读

依赖：`websocket-client`（本仓库 .venv 已装；缺了就装到 .venv 里，别在启动链上装）。
Chrome 路径可用 `--chrome /path/to/chrome` 覆盖，默认走 macOS 常见路径。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "web" / "index.html"

#: 值是该页 `#view` 里**实际会出现**的标题（页面 `page({title})` 与导航文案可能不同，
#: 例如导航写「目标职位」而页面标题是「岗位」）。命中任意一个即可。
ROUTES: dict[str, str] = {
    "workbench": "工作台",
    "warehouse": "经历库",
    "templates": "模板",
    "jobs": "岗位",
    "builds": "组装",
    "profile": "个人资料",
    "settings": "设置",
}

#: 导航文案（只作报告参考，不当判据）
NAV_LABELS: dict[str, str] = {
    "workbench": "工作台",
    "warehouse": "经历库",
    "templates": "模板",
    "jobs": "目标职位",
    "builds": "组装导出",
    "profile": "个人资料",
    "settings": "设置",
}

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)


@dataclass
class PageResult:
    route: str
    text: str = ""
    heading: str = ""
    #: CSP 违规（`Log.entryAdded` 的 `source=security`）——安全策略把东西拦了
    csp_violations: list[str] = field(default_factory=list)
    #: 网络错误（`source=network`，含 404/500）——路径或接口写错了
    net_errors: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    error: str = ""
    elapsed_ms: int = 0

    @property
    def text_len(self) -> int:
        return len(self.text.strip())

    def failures(self, expect: str, min_chars: int) -> list[str]:
        out: list[str] = []
        if self.error:
            out.append(f"导航失败：{self.error}")
        if self.text_len < min_chars:
            out.append(f"#view 正文只有 {self.text_len} 字符（要求 ≥{min_chars}）")
        haystack = f"{self.heading}\n{self.text}"
        if expect not in haystack:
            out.append(f"没找到该页标题「{expect}」")
        if self.csp_violations:
            out.append(f"CSP 违规 {len(self.csp_violations)} 条")
        if self.net_errors:
            out.append(f"网络错误 {len(self.net_errors)} 条")
        if self.exceptions:
            out.append(f"未捕获异常 {len(self.exceptions)} 条")
        return out

    def as_dict(self) -> dict:
        return {
            "route": self.route,
            "text_len": self.text_len,
            "heading": self.heading,
            "csp_violations": self.csp_violations,
            "net_errors": self.net_errors,
            "exceptions": self.exceptions,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
        }


def find_chrome(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    found = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    if found:
        return found
    raise SystemExit("找不到 Chrome/Chromium；用 --chrome 指定可执行文件路径")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(url: str, *, timeout: float = 2.0) -> dict:
    request = urllib.request.Request(url, headers={"Origin": "http://127.0.0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310 - 只连本机
        return json.loads(resp.read().decode("utf-8") or "{}")


def wait_for_debugger(port: int, *, timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    last: Exception | None = None
    while time.time() < deadline:
        try:
            return http_json(f"http://127.0.0.1:{port}/json/version", timeout=1.0)
        except (urllib.error.URLError, OSError, ValueError) as exc:  # pragma: no cover - 环境相关
            last = exc
            time.sleep(0.2)
    raise SystemExit(f"Chrome 调试端口 {port} 没起来：{last}")


def page_target(port: int) -> dict:
    """取一个可用的页面 target（about:blank 优先）。"""
    deadline = time.time() + 10.0
    while time.time() < deadline:
        targets = http_json(f"http://127.0.0.1:{port}/json/list")
        pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
        if pages:
            return pages[0]
        time.sleep(0.2)
    raise SystemExit("Chrome 没有可用的页面 target")


class Session:
    """一条 CDP 连接；同步收消息，按 id 匹配响应，其余事件进钩子。"""

    def __init__(self, ws_url: str) -> None:
        try:
            import websocket  # type: ignore[import-not-found]
        except ImportError:  # pragma: no cover - 依赖缺失时给出可执行指令
            raise SystemExit("缺少 websocket-client：请先装进 .venv（启动链不做安装动作）")
        self._ws = websocket.create_connection(ws_url, timeout=10.0)
        self._next_id = 0
        self._pending: dict[int, dict] = {}
        self.on_event = lambda method, params: None  # 由调用方覆盖

    def call(self, method: str, params: dict | None = None, *, timeout: float = 10.0) -> dict:
        self._next_id += 1
        msg_id = self._next_id
        self._ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            if msg_id in self._pending:
                return self._pending.pop(msg_id)
            raw = self._ws.recv()
            if not raw:
                continue
            message = json.loads(raw)
            if "id" in message:
                self._pending[int(message["id"])] = message
            elif "method" in message:
                self.on_event(message["method"], message.get("params") or {})
        raise TimeoutError(f"CDP {method} 超时")

    def drain(self, seconds: float) -> None:
        """在给定时间内只收事件（不阻塞太久）。"""
        deadline = time.time() + seconds
        self._ws.settimeout(0.25)
        try:
            while time.time() < deadline:
                try:
                    raw = self._ws.recv()
                except Exception:  # noqa: BLE001 - 超时/关闭都只是「没消息」
                    continue
                if not raw:
                    continue
                message = json.loads(raw)
                if "id" in message:
                    self._pending[int(message["id"])] = message
                elif "method" in message:
                    self.on_event(message["method"], message.get("params") or {})
        finally:
            self._ws.settimeout(10.0)

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:  # noqa: BLE001 - 关闭失败不影响结果
            pass


def evaluate(session: Session, expression: str) -> object:
    out = session.call(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": False},
    )
    result = (out.get("result") or {}).get("result") or {}
    return result.get("value")


def probe_page(session: Session, base: str, route: str, *, settle: float) -> PageResult:
    result = PageResult(route=route)
    started = time.time()
    seen_csp: list[str] = []
    seen_net: list[str] = []
    seen_exceptions: list[str] = []

    def on_event(method: str, params: dict) -> None:
        if method == "Log.entryAdded":
            entry = params.get("entry") or {}
            if entry.get("level") != "error":
                return
            source = str(entry.get("source") or "")
            text = str(entry.get("text") or "")
            url = str(entry.get("url") or "")
            if source == "security":
                seen_csp.append(text)
            elif source == "network":
                seen_net.append(f"{text} {url}".strip())
            else:
                # 其余 error 级日志（脚本报错等）也按网络/脚本错误记，不混进 CSP
                seen_net.append(f"{source}: {text}")
        elif method == "Runtime.exceptionThrown":
            detail = (params.get("exceptionDetails") or {})
            text = (
                (detail.get("exception") or {}).get("description")
                or detail.get("text")
                or "未知异常"
            )
            seen_exceptions.append(str(text).splitlines()[0])

    session.on_event = on_event
    with_errors = session.call("Runtime.enable")
    if with_errors.get("error"):
        result.error = str(with_errors["error"])
    session.call("Log.enable")
    session.call("Page.enable")
    session.call("Log.clear")
    session.call("Runtime.discardConsoleEntries")

    session.call("Page.navigate", {"url": f"{base}/#/route".replace("/route", f"/{route}")})
    time.sleep(settle)
    session.drain(0.4)

    result.text = str(evaluate(session, "document.querySelector('#view')?.innerText || ''") or "")
    result.heading = str(evaluate(session, "document.querySelector('#view h1, #view h2')?.innerText || document.querySelector('#view .page__title')?.innerText || ''") or "")
    result.csp_violations = seen_csp
    result.net_errors = seen_net
    result.exceptions = seen_exceptions
    result.elapsed_ms = int((time.time() - started) * 1000)
    return result


def inline_scripts(html: str) -> list[str]:
    """粗粒度扫出「没有 src 的 <script ...>」片段（用于报告，不作为判据）。"""
    import re

    out = []
    for match in re.finditer(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", html, re.S):
        attrs = match.group("attrs") or ""
        if "src=" not in attrs and match.group("body").strip():
            out.append(attrs.strip()[:60])
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="七个页面的无头巡检（CDP，真跑 DOM）")
    parser.add_argument("--base", default=None, help="服务地址；默认读 data/runtime/app_port")
    parser.add_argument("--route", action="append", choices=sorted(ROUTES), help="只查指定页（可重复）")
    parser.add_argument("--chrome", default=os.environ.get("CHROME_PATH"), help="Chrome 可执行文件")
    parser.add_argument("--min-chars", type=int, default=120, help="#view 正文最少字符数")
    parser.add_argument("--settle", type=float, default=2.0, help="导航后真实等待秒数")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--timeout", type=float, default=60.0, help="整轮超时秒数")
    args = parser.parse_args(argv)

    base = args.base
    if not base:
        port_file = ROOT / "data" / "runtime" / "app_port"
        try:
            record = json.loads(port_file.read_text(encoding="utf-8"))
            base = str(record.get("url") or f"http://127.0.0.1:{record['port']}")
        except (OSError, ValueError, KeyError):
            base = "http://127.0.0.1:8765"
    base = base.rstrip("/")

    routes = args.route or list(ROUTES)
    chrome = find_chrome(args.chrome)
    debug_port = free_port()
    profile_dir = Path(tempfile.mkdtemp(prefix="rw-pages-"))
    cmd = [
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
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    results: list[PageResult] = []
    try:
        wait_for_debugger(debug_port)
        target = page_target(debug_port)
        session = Session(target["webSocketDebuggerUrl"])
        try:
            deadline = time.time() + args.timeout
            for route in routes:
                if time.time() > deadline:
                    results.append(PageResult(route=route, error="整轮超时"))
                    continue
                results.append(probe_page(session, base, route, settle=args.settle))
        finally:
            session.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - 环境相关
            proc.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)

    rows = []
    failed = 0
    for result in results:
        expect = ROUTES[result.route]
        problems = result.failures(expect, args.min_chars)
        if problems:
            failed += 1
        rows.append({"result": result, "problems": problems})

    if args.json:
        print(json.dumps([{**r["result"].as_dict(), "problems": r["problems"]} for r in rows], ensure_ascii=False, indent=2))
    else:
        inline = inline_scripts(INDEX.read_text(encoding="utf-8"))
        print(f"巡检地址：{base}    内联脚本：{len(inline)} 处（应为 0）")
        print(f"{'页面':<12}{'正文字符':>8}  {'CSP':>4}  {'网络':>4}  {'异常':>4}  标题 / 结论")
        for row in rows:
            result = row["result"]
            status = "FAIL" if row["problems"] else "PASS"
            print(
                f"{result.route:<12}{result.text_len:>8}  {len(result.csp_violations):>4}  "
                f"{len(result.net_errors):>4}  {len(result.exceptions):>4}  "
                f"{result.heading or '-'}  [{status}]"
            )
            for problem in row["problems"]:
                print(f"    - {problem}")
            for violation in result.csp_violations[:3]:
                print(f"    ! CSP: {violation}")
            for net in result.net_errors[:3]:
                print(f"    ! NET: {net}")
            for exception in result.exceptions[:3]:
                print(f"    ! {exception}")
        print(f"\n合计 {len(rows)} 页，失败 {failed} 页")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
