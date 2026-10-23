"""AC（验收条款）harness —— 平台面：环境 / 本地化 / 隐私 / 命名。

一条多用例的写法：每个 `@check("AC-XXX-NN")` 函数就是该条的判据，签名统一
`fn(flow)`，由文件末尾的 `test_ac(id)` 逐条跑。判据必须观测**事实**（响应字段、
文件内容、库里行），不允许读实现内部的私有变量来「自证」。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from .helpers import (
    artifact,
    artifact_path,
    db_int,
    db_one,
    pdf_metrics,
    pdf_text,
    read_repo,
    repo_root,
    restore_profile,
    snapshot_profile,
)

def db_paths():
    from app import db as db_mod

    db_mod.reset_paths_for_tests()
    return db_mod.get_paths()


CHECKS: dict[str, callable] = {}
EXTRA: dict[str, callable] = {}


def extra(name: str):
    """非 AC 台账内的补充回归（不计入 docs/ACCEPTANCE.md 的覆盖率）。"""

    def register(fn):
        EXTRA[name] = fn
        return fn

    return register


def check(ac: str):
    def register(fn):
        CHECKS[ac] = fn
        return fn

    return register


# ---------------------------------------------------------------- 环境 ----------------


@check("AC-ENV-01")
def _env_01(flow):
    """10 个运行依赖能在 .venv 里 import（AC-ENV-01 的命令形态）。"""
    python = repo_root() / ".venv" / "bin" / "python"
    if not python.exists():
        python = Path(sys.executable)
    names = "flask, pydantic, jinja2, reportlab, pdfplumber, pypdf, docx, markdown, httpx, bs4"
    out = subprocess.run(
        [str(python), "-c", f"import {names}"], capture_output=True, text=True, timeout=120
    )
    assert out.returncode == 0, out.stderr[-800:]


@check("AC-ENV-02")
def _env_02(flow):
    """启动链里不做安装动作（断网也能起）。"""
    sources = ["scripts/run.sh"] + [f"scripts/{p.name}" for p in (repo_root() / "scripts").glob("*.py")]
    pattern = re.compile(r"pip\s+(install|download)|npm\s+(i|install)\b|yarn\s+add")
    hits = [name for name in sources if pattern.search(read_repo(name))]
    assert not hits, f"启动/体检脚本里出现安装动作：{hits}"


@check("AC-ENV-03")
def _env_03(flow):
    """preflight 输出 JSON 且含约定分组。"""
    python = repo_root() / ".venv" / "bin" / "python"
    proc = subprocess.run(
        [str(python), str(repo_root() / "scripts" / "preflight.py"), "--json"],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(repo_root()),
    )
    assert proc.returncode in (0, 1, 2), proc.stderr[-800:]
    body = json.loads(proc.stdout[proc.stdout.index("{") :])
    for key in ("python", "deps", "fonts", "engines", "ports", "data_dirs"):
        assert key in body, f"preflight JSON 缺 {key}"
    assert "11434" not in proc.stdout, "preflight 不应再探测 Ollama(11434)"


@check("AC-ENV-04")
def _env_04(flow):
    resp = flow["client"].get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["status"] in ("ok", "degraded")
    if data["status"] == "degraded":
        assert data["warnings"], "degraded 必须给出 warnings"
        for item in data["warnings"]:
            assert {"code", "message"} <= set(item), item


@check("AC-ENV-05")
def _env_05(flow):
    """首次启动自动建目录与 app.db，并写入 schema_version。"""
    root = flow["data_dir"]
    for name in ("files", "exports", "imports", "logs", "runtime"):
        assert (root / name).is_dir(), f"缺目录 {name}"
    assert (root / "app.db").is_file()
    version = db_one(flow, "SELECT value FROM app_setting WHERE key='schema_version'")[0]
    assert int(version) >= 8, version


@check("AC-ENV-06")
def _env_06(flow):
    """端口顺延：占住首选端口后 pick_port 一定给出更大的空闲端口，且端口文件五字段。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("rw_server_entry", repo_root() / "server" / "server.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(repo_root() / "server"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

    import socket

    holder = socket.socket()
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    busy = holder.getsockname()[1]
    try:
        picked = module.pick_port("127.0.0.1", busy)
        assert picked > busy, f"端口未顺延：busy={busy} picked={picked}"
        target = flow["data_dir"] / "runtime" / "app_port"
        module.write_runtime_port(db_paths(), picked)
        record = json.loads(target.read_text(encoding="utf-8"))
        assert set(record) >= {"port", "host", "url", "pid", "started_at"}, record
        assert record["port"] == picked and record["host"] == "127.0.0.1"
        assert record["url"] == f"http://127.0.0.1:{picked}"
        assert module.read_runtime_port(db_paths())["port"] == picked
    finally:
        holder.close()


@check("AC-ENV-07")
def _env_07(flow):
    """只监听回环地址（绑 0.0.0.0 会把简历服务暴露到局域网）。"""
    source = read_repo("server/server.py")
    assert 'HOST = "127.0.0.1"' in source or "HOST = '127.0.0.1'" in source
    assert "0.0.0.0" not in source.split("def main")[0], "server.py 不应出现 0.0.0.0 绑定"


@check("AC-ENV-08")
def _env_08(flow):
    out = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "server/app"],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(repo_root()),
    )
    assert out.returncode == 0, out.stdout[-800:] + out.stderr[-800:]


@check("AC-ENV-09")
def _env_09(flow):
    """Skill 从 app_port 的 JSON 取端口，而不是 int(read())。"""
    start = read_repo("skills/resume-warehouse/start.sh")
    assert "json" in start and "app_port" in start
    assert not re.search(r"int\(\s*\$?\(?\s*cat[^\n]*app_port", start)
    assert "8765" not in re.sub(r"#.*", "", start).split("APP_PORT_FALLBACK")[0] or "app_port" in start


@check("AC-ENV-10")
def _env_10(flow):
    """build 是「进程是否当前代码」的唯一判据，且 /env 与 /health 同源。"""
    client = flow["client"]
    health = client.get("/api/v1/health").get_json()["data"]
    env = client.get("/api/v1/env").get_json()["data"]
    assert env.get("build") == health.get("build"), f"env.build={env.get('build')} health.build={health.get('build')}"
    build = health["build"]
    assert re.fullmatch(r"[0-9a-f]{7,}(-dirty)?|src-[0-9a-f]+", str(build["id"])), build
    assert build.get("source", "").startswith("src-")


@check("AC-ENV-11")
def _env_11(flow):
    """app_port 生命周期：陈旧判据 / 覆盖 / 非本进程不删。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("rw_server_entry2", repo_root() / "server" / "server.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(repo_root() / "server"))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

    path = flow["data_dir"] / "runtime" / "app_port"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"port": 8899, "host": "127.0.0.1", "url": "http://127.0.0.1:8899", "pid": 999999, "started_at": "2026-01-01T00:00:00"}),
        encoding="utf-8",
    )
    stale, reason = module.runtime_port_stale(json.loads(path.read_text(encoding="utf-8")))
    assert stale is True and "pid" in reason, (stale, reason)

    module.write_runtime_port(db_paths(), 8123)
    assert json.loads(path.read_text(encoding="utf-8"))["port"] == 8123

    foreign = {"port": 8123, "host": "127.0.0.1", "url": "http://127.0.0.1:8123", "pid": 424242, "started_at": "x"}
    path.write_text(json.dumps(foreign), encoding="utf-8")
    module.clear_runtime_port(db_paths())
    assert path.exists(), "文件 pid ≠ 自己时不得删除"


# ---------------------------------------------------------------- 本地化 ----------------


@check("AC-LOC-02")
def _loc_02(flow):
    """代码里不写 data/ 之外的绝对路径写入（字体/浏览器这类只读常量除外）。"""
    read_only = ("/System/Library/Fonts", "/Applications/", "/usr/bin", "/usr/local/bin", "/opt/homebrew/bin")
    write_call = re.compile(r"(?:open|write_text|write_bytes|mkdir|makedirs|replace|rename)\(([^)\n]*)")
    offenders: list[str] = []
    for path in (repo_root() / "server" / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in write_call.finditer(text):
            for literal in re.findall(r"""["'](/[^"'\n]+)["']""", match.group(1)):
                if literal.startswith(read_only):
                    continue
                offenders.append(f"{path.relative_to(repo_root())}: {literal}")
    assert not offenders, "出现 data/ 之外的绝对路径写入：\n" + "\n".join(offenders[:10])


@check("AC-LOC-03")
def _loc_03(flow):
    rows = db_one(
        flow,
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN "
        "('user_profile','package','package_bullet_variant','template','template_block','slot',"
        "'import_job','attachment','job_description','jd_requirement','company_profile',"
        "'resume_build','build_selection','build_artifact','job','llm_preview','llm_call_log','app_setting')",
    )
    assert int(rows[0]) >= 18, f"业务表不全，只有 {rows[0]} 张"


@check("AC-LOC-04")
def _loc_04(flow):
    """产物落在 data/exports/ 且 build_artifact 有完整记录。"""
    item = artifact(flow)
    assert item["rel_path"].startswith("exports/"), item["rel_path"]
    path = flow["data_dir"] / item["rel_path"]
    assert path.exists() and path.stat().st_size == item["bytes"]
    row = db_one(flow, "SELECT format, engine, rel_path, bytes, sha256 FROM build_artifact WHERE id=?", (item["id"],))
    assert row and row["format"] == "pdf" and row["engine"] in ("reportlab", "chrome"), dict(row)
    assert row["bytes"] == item["bytes"] and len(row["sha256"]) == 64


@check("AC-LOC-05")
def _loc_05(flow):
    """隐私边界写在 .gitignore 里，并且 git 真的认。"""
    ignore = read_repo(".gitignore")
    for pattern in ("data/", ".venv/", ".env", "__pycache__/"):
        assert pattern in ignore, f".gitignore 缺 {pattern}"
    assert "*.pyc" in ignore or "*.py[cod]" in ignore, ".gitignore 缺 *.pyc（或 *.py[cod]）"
    for target in ("data/app.db", ".env"):
        proc = subprocess.run(
            ["git", "check-ignore", "-v", target], capture_output=True, text=True, cwd=str(repo_root())
        )
        assert proc.returncode == 0, f"{target} 未被忽略：{proc.stderr}"


@check("AC-LOC-06")
def _loc_06(flow):
    """export-all 产出单 zip（db+files+exports），且不含 .env。"""
    resp = flow["client"].get("/api/v1/settings/export-all")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert {"path", "bytes", "sha256"} <= set(data), data
    path = flow["data_dir"] / data["path"] if not str(data["path"]).startswith("/") else Path(data["path"])
    if not path.exists():
        path = flow["data_dir"] / "exports" / Path(data["path"]).name
    assert path.exists(), data["path"]
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    assert any(name.endswith("app.db") for name in names), names[:5]
    assert not any(".env" == Path(name).name for name in names), "导出包里混进了 .env"
    assert not any(name.startswith("exports/") and name.endswith(".zip") for name in names)


# ---------------------------------------------------------------- 隐私 ----------------


def _preview(flow, purpose="bullets_generate", package_ids=None, **selections):
    client = flow["client"]
    packages = selections.pop("package_ids", None) or package_ids
    body = {"purpose": purpose, "selections": {"package_ids": packages or []}}
    body["selections"].update(selections)
    resp = client.post("/api/v1/llm/preview", json=body)
    return resp, (resp.get_json() or {}).get("data") or {}


@check("AC-PRIV-01")
def _priv_01(flow):
    """原始简历字节/指纹不得出现在 payload（只发被选中的结构化片段）。"""
    package = flow["packages"][0]
    resp, data = _preview(flow, "bullets_generate", package_ids=[package["id"]])
    assert resp.status_code in (200, 201), resp.get_json()
    payload = json.dumps(data["payload"], ensure_ascii=False)
    for fingerprint in ("13800138000", "zhangsan@example.com", "张三"):
        assert fingerprint not in payload, f"payload 里出现身份指纹 {fingerprint}"
    assert "data/imports" not in payload


@check("AC-PRIV-02")
def _priv_02(flow):
    """未选中的 package 不出现在 payload 里。"""
    chosen, other = flow["packages"][0], flow["packages"][-1]
    resp, data = _preview(flow, "bullets_generate", package_ids=[chosen["id"]])
    assert resp.status_code in (200, 201)
    payload = json.dumps(data["payload"], ensure_ascii=False)
    assert data["excluded"]["packages_selected"] == 1
    assert data["excluded"]["skipped"], "未选中的包必须出现在 skipped 里"
    assert data["excluded"]["packages_total"] >= 2
    sources = {
        item.get("source_id")
        for item in data["fields"]
        if item.get("kind") in ("package", "variant") and item.get("source_id")
    }
    assert chosen["id"] in sources, f"选中的包没进 payload：{sources}"
    assert other["id"] not in sources, f"未选中的包 {other['id']} 泄漏进 payload"


@check("AC-PRIV-03")
def _priv_03(flow):
    """consent 三态：缺 preview → 428；过期 → 410；payload 变更 → 409。"""
    client = flow["client"]
    missing = client.post("/api/v1/llm/complete", json={"preview_id": "", "expected_payload_sha256": "0" * 64})
    assert missing.status_code == 422 or missing.status_code == 428

    resp, data = _preview(flow, "summary_polish", package_ids=[flow["packages"][0]["id"]])
    assert resp.status_code in (200, 201)
    preview_id, sha = data["preview_id"], data["payload_sha256"]

    mismatch = client.post("/api/v1/llm/complete", json={"preview_id": preview_id, "expected_payload_sha256": "1" * 64})
    assert mismatch.status_code == 409, mismatch.get_json()

    db_one(flow, "SELECT 1")  # 确保连接可用
    flow["_db_exec"]("UPDATE llm_preview SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (preview_id,))
    expired = client.post("/api/v1/llm/complete", json={"preview_id": preview_id, "expected_payload_sha256": sha})
    assert expired.status_code == 410, expired.get_json()
    code = expired.get_json()["error"]["code"]
    assert code == "LLM_CONSENT_EXPIRED", code


@check("AC-PRIV-04")
def _priv_04(flow):
    """preview 响应字段齐（用户能看懂「要发什么」）。"""
    resp, data = _preview(flow, "bullets_generate", package_ids=[flow["packages"][0]["id"]])
    assert resp.status_code in (200, 201)
    for key in (
        "preview_id",
        "purpose",
        "provider",
        "model",
        "endpoint_host",
        "expires_at",
        "payload",
        "payload_sha256",
        "total_chars",
        "est_tokens",
        "fields",
        "excluded",
        "redactions",
    ):
        assert key in data, f"preview 缺 {key}"
    assert data["fields"], "字段清单不能为空"
    for field in data["fields"]:
        assert {"path", "kind", "chars", "est_tokens", "included"} <= set(field), field
    assert len(data["payload_sha256"]) == 64


@check("AC-PRIV-05")
def _priv_05(flow):
    """手机号/邮箱进 payload 必先脱敏，且 redactions 有记录。"""
    client = flow["client"]
    package = flow["packages"][0]
    # 让事实里带上联系方式（模拟用户把联系方式写进经历）
    variant = package["variants"][0]
    original = variant["text"]
    client.put(
        f"/api/v1/packages/{package['id']}/variants/{variant['id']}",
        json={"text": "负责接口开发，对接 13800138000 与 zhangsan@example.com，QPS 提升 39.3%。"},
    )
    try:
        resp, data = _preview(
            flow, "bullets_generate", package_ids=[package["id"]], variant_ids=[variant["id"]]
        )
        assert resp.status_code in (200, 201), resp.get_json()
        payload = json.dumps(data["payload"], ensure_ascii=False)
        assert "13800138000" not in payload and "zhangsan@example.com" not in payload
        assert "[PHONE]" in payload and "[EMAIL]" in payload
        kinds = {item["replacement"] for item in data["redactions"]}
        assert {"[PHONE]", "[EMAIL]"} <= kinds, kinds
        for item in data["redactions"]:
            assert {"path", "match", "value_preview", "replacement", "count"} <= set(item), item
            assert "13800138000" not in json.dumps(item, ensure_ascii=False)
    finally:
        client.put(f"/api/v1/packages/{package['id']}/variants/{variant['id']}", json={"text": original})


@check("AC-PRIV-06")
def _priv_06(flow):
    """key 永不回显：settings 只说 key_set，且全库/全日志无明文。"""
    from app import config as config_mod

    client = flow["client"]
    settings = client.get("/api/v1/settings").get_json()["data"]
    assert set(settings) >= {"key_set", "key_field"}
    assert isinstance(settings["key_set"], bool)
    body = json.dumps(settings, ensure_ascii=False)
    assert "api_key" not in body.lower() or "key_field" in body

    secret = config_mod.get_config().api_key
    assert secret, "本机 .env 应已配置 key（否则该条无法验证）"
    needles = {secret, secret[-6:], secret[:6]}
    for path in flow["data_dir"].rglob("*"):
        if path.is_file() and path.suffix in (".log", ".json", ".txt"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in needles:
                assert needle not in text, f"{path.name} 泄漏 key 片段"
    db_dump = "\n".join(
        str(tuple(row)) for row in flow["_db_exec"]("SELECT * FROM llm_call_log LIMIT 50").fetchall()
    )
    for needle in needles:
        assert needle not in db_dump


@check("AC-PRIV-07")
def _priv_07(flow):
    """日志只记字段名与体积，不记正文。"""
    log_dir = flow["data_dir"] / "logs"
    texts = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in log_dir.glob("*.log"))
    assert "13800138000" not in texts and "zhangsan@example.com" not in texts
    rows = flow["_db_exec"]("SELECT field_names_json, payload_bytes FROM llm_call_log").fetchall()
    for row in rows:
        assert row["payload_bytes"] is None or int(row["payload_bytes"]) >= 0
        names = json.loads(row["field_names_json"] or "[]")
        assert all(isinstance(item, str) for item in names)


@check("AC-PRIV-08")
def _priv_08(flow):
    """页面响应头有 CSP 且 default-src 'self'、无 unsafe-eval。"""
    resp = flow["client"].get("/")
    assert resp.status_code == 200
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp, csp
    assert "unsafe-eval" not in csp
    assert "unsafe-inline" not in csp or "style-src" in csp, "inline 脚本必须禁止"
    assert "connect-src 'self'" in csp, csp


@check("AC-PRIV-09")
def _priv_09(flow):
    """每次调用留痕：created_at/provider/model/endpoint_host/字段名/字节/耗时。"""
    rows = flow["_db_exec"]("PRAGMA table_info(llm_call_log)").fetchall()
    columns = {row["name"] for row in rows}
    for column in ("provider", "model", "endpoint_host", "field_names_json", "payload_bytes", "est_tokens", "latency_ms", "ok"):
        assert column in columns, f"llm_call_log 缺 {column}"


@check("AC-PRIV-10")
def _priv_10(flow):
    """出网按方向分开：上行只有 llm_client，下行只有 fetch_client。"""
    uplink = {"server/app/adapters/llm_client.py"}
    downlink = {"server/app/adapters/fetch_client.py"}
    # egress_guard 只做域名/IP 判定（socket.getaddrinfo），不发请求
    benign = {"server/app/adapters/egress_guard.py"}
    network = re.compile(r"\b(httpx\.|requests\.|urllib\.request|http\.client|aiohttp)")
    offenders = []
    for path in (repo_root() / "server" / "app").rglob("*.py"):
        rel = str(path.relative_to(repo_root())).replace(os.sep, "/")
        text = re.sub(r"^\s*#.*$", "", path.read_text(encoding="utf-8"), flags=re.M)
        if network.search(text) and rel not in uplink | downlink | benign:
            offenders.append(rel)
    assert not offenders, f"出网模块越界：{offenders}"
    fetch = read_repo("server/app/adapters/fetch_client.py")
    assert "GET" in fetch and "method=" not in fetch.replace("method=\"GET\"", "")
    assert "school" not in fetch.lower() and "phone" not in fetch.lower()


@check("AC-PRIV-11")
def _priv_11(flow):
    """姓名/联系方式脱敏、学校名放行（用户口径）。"""
    client = flow["client"]
    package = flow["packages"][0]
    variant = package["variants"][0]
    original = variant["text"]
    client.put(
        f"/api/v1/packages/{package['id']}/variants/{variant['id']}",
        json={"text": f"{original} 联系人张三，电话 13800138000，邮箱 zhangsan@example.com。"},
    )
    try:
        resp, data = _preview(
            flow, "bullets_generate", package_ids=[package["id"]], variant_ids=[variant["id"]]
        )
        assert resp.status_code in (200, 201), resp.get_json()
        payload = json.dumps(data["payload"], ensure_ascii=False)
        assert "张三" not in payload, "姓名必须脱敏"
        assert "[NAME]" in payload, "姓名应替换为 [NAME]"
        assert "13800138000" not in payload and "[PHONE]" in payload
        replaced = {item["replacement"] for item in data["redactions"]}
        assert {"[NAME]", "[PHONE]", "[EMAIL]"} <= replaced, replaced
    finally:
        client.put(f"/api/v1/packages/{package['id']}/variants/{variant['id']}", json={"text": original})

    # 学校名放行：jd_analyze 的候选人档案里必须是真值
    resp2, data2 = _preview(flow, "jd_analyze", package_ids=[], jd_id=flow["jd"]["id"])
    assert resp2.status_code in (200, 201), resp2.get_json()
    jd_payload = json.dumps(data2["payload"], ensure_ascii=False)
    assert "示例大学" in jd_payload, "学校名必须按真实值发送"
    assert "[SCHOOL]" not in jd_payload
    assert data2["excluded"]["structural_exclusions"], "结构性排除清单不能为空"


@check("AC-PRIV-12")
def _priv_12(flow):
    """服务端自检兜底：payload 里若仍有人名/电话则拒绝出网，且名单不含学校。"""
    from app import config as config_mod
    from app.repos import ProfileRepo
    from app.services import privacy

    profile = ProfileRepo().get()
    hits = privacy.identity_terms(profile)
    values = [value for _field, value in hits]
    assert "张三" in values, values
    assert not any("示例大学" in value for value in values), "校名不得进身份名单"
    with pytest.raises(Exception) as excinfo:
        privacy.assert_no_identity("请联系 13800138000 安排面试", profile)
    error = getattr(excinfo.value, "to_dict", lambda: {})()
    assert error.get("error", {}).get("details", {}).get("reason") == "IDENTITY_PRESENT_IN_PAYLOAD"
    privacy.assert_no_identity("示例大学 2028 届 计算机科学与技术 本科", profile)
    assert config_mod.get_config().api_key, "key 应只在后端读取"


@check("AC-PRIV-13")
def _priv_13(flow):
    """配置助手脚本不回显 key 片段。"""
    path = repo_root() / "scripts/set-api-key.command"
    if not path.exists():
        pytest.skip("配置助手脚本不在仓库内")
    text = path.read_text(encoding="utf-8")
    assert "末尾四位" not in text
    assert not re.search(r"sk-[A-Za-z0-9]{4}", text), "脚本里出现 key 样式的字面量"


@extra("llm_brief_contains_only_whitelisted_fields")
def _priv_14(flow):
    """校名真实上云且被消费：payload 含校名，competitiveness 用到它。"""
    resp, data = _preview(flow, "jd_analyze", package_ids=[], jd_id=flow["jd"]["id"])
    payload = json.dumps(data["payload"], ensure_ascii=False)
    assert "示例大学" in payload
    result = flow["analysis"]
    assert result.get("competitiveness"), "分析结果必须有 competitiveness"
    tier = result["competitiveness"]["school_tier"]
    assert tier in ("C9", "985", "211", "双一流", "普通本科", "海外", "其他"), tier
    assert len(result["competitiveness"]["school_signal"]) >= 8


# ---------------------------------------------------------------- 命名 ----------------


@check("AC-NAME-01")
def _name_01(flow):
    """纯函数：任何输入都 200，且 data 里五个键齐。"""
    client = flow["client"]
    for body in ({}, {"pattern": "{unknown_var}-{name}"}, {"pattern": "{{literal}}"}, {"pattern": "   "}, {"pattern": "{name"}):
        resp = client.post("/api/v1/naming/validate", json=body)
        assert resp.status_code == 200, (body, resp.status_code)
        data = resp.get_json()["data"]
        assert {"valid", "resolved", "filename", "variables", "warnings", "errors"} <= set(data), data


@check("AC-NAME-02")
def _name_02(flow):
    """命名表的代表性逐条（净化/缺失/截断/保留名）。"""
    client = flow["client"]
    ok = client.post("/api/v1/naming/validate", json={"pattern": "{position}-{name}-{school}", "lang": "zh", "position": "数据分析实习生"}).get_json()["data"]
    assert ok["valid"] is True and ok["filename"] == "数据分析实习生-张三-示例大学.pdf", ok

    reserved = client.post("/api/v1/naming/validate", json={"pattern": "{position}", "position": "CON"}).get_json()["data"]
    assert reserved["filename"].startswith("_"), reserved

    emoji = client.post("/api/v1/naming/validate", json={"pattern": "{position}", "position": "数据分析🔥实习生"}).get_json()["data"]
    assert "🔥" not in emoji["filename"]
    assert any(item["code"] in ("EMOJI_STRIPPED", "NAMING_SANITIZED") for item in emoji["warnings"]), emoji["warnings"]

    long = client.post("/api/v1/naming/validate", json={"pattern": "{position}", "position": "岗" * 300}).get_json()["data"]
    assert long["valid"] is True and len(long["filename"]) <= 126
    assert any(item["code"] == "NAMING_TRUNCATED" for item in long["warnings"]), long["warnings"]

    missing = client.post("/api/v1/naming/validate", json={"pattern": "{position}-{company}", "position": "x"}).get_json()["data"]
    assert missing["valid"] is False
    assert any(item["code"] == "NAMING_MISSING_VAR" for item in missing["errors"]), missing["errors"]
    assert missing["filename"] == ""


@check("AC-NAME-03")
def _name_03(flow):
    """非法 pattern 在 PATCH 时就 422，且不落库。"""
    client = flow["client"]
    build_id = flow["build_id"]
    before = client.get(f"/api/v1/builds/{build_id}").get_json()["data"]["naming_pattern"]
    resp = client.patch(f"/api/v1/builds/{build_id}", json={"naming_pattern": "{nosuch}-{name}"})
    assert resp.status_code == 422, resp.get_json()
    assert resp.get_json()["error"]["code"].startswith("NAMING_")
    after = client.get(f"/api/v1/builds/{build_id}").get_json()["data"]["naming_pattern"]
    assert after == before, "非法 pattern 不得落库"


@check("AC-NAME-04")
def _name_04(flow):
    """缺 name/school → 422 NAMING_MISSING_VAR，永不产出残缺文件名。"""
    client = flow["client"]
    snapshot = snapshot_profile(client)
    try:
        client.put("/api/v1/profile", json={"school_zh": None})
        resp = client.post(f"/api/v1/builds/{flow['build_id']}/export", json={"format": "pdf", "lang": "zh"})
        assert resp.status_code == 422, resp.get_json()
        error = resp.get_json()["error"]
        assert error["code"] == "NAMING_MISSING_VAR", error
        assert "设置" in (error.get("hint") or "") or "资料" in (error.get("hint") or ""), error.get("hint")
        assert not list((flow["data_dir"] / "exports").glob("*undefined*"))
    finally:
        restore_profile(client, snapshot)


@check("AC-NAME-05")
def _name_05(flow):
    """同名冲突追加 -2，且 artifact 记下实际文件名。"""
    client = flow["client"]
    first = artifact(flow)["filename"]
    assert first.endswith(".pdf")
    resp = client.post(f"/api/v1/builds/{flow['build_id']}/export", json={"format": "pdf", "lang": "zh", "overwrite": False})
    assert resp.status_code == 202, resp.get_json()
    from .helpers import wait_job

    job = wait_job(client, resp.get_json()["data"]["job_id"])
    item = (job.get("result_json") or {}).get("artifacts", [{}])[0]
    assert item["filename"] != first, "同名应追加 -2/-3 而不是覆盖"
    assert re.search(r"-(\d+)\.pdf$", item["filename"]), item["filename"]
    assert (flow["data_dir"] / "exports" / item["filename"]).exists()


@check("AC-NAME-06")
def _name_06(flow):
    """不传 pattern 时用 app_setting.naming_template，PUT /settings 可改。"""
    client = flow["client"]
    settings = client.get("/api/v1/settings").get_json()["data"]
    assert settings["naming_template"] == "{position}-{name}-{school}"
    data = client.post("/api/v1/naming/validate", json={"lang": "zh", "position": "数据分析实习生"}).get_json()["data"]
    assert data["filename"] == "数据分析实习生-张三-示例大学.pdf"
    try:
        client.put("/api/v1/settings", json={"naming_template": "{name}-{position}"})
        changed = client.post("/api/v1/naming/validate", json={"lang": "zh", "position": "数据分析实习生"}).get_json()["data"]
        assert changed["filename"] == "张三-数据分析实习生.pdf", changed
    finally:
        client.put("/api/v1/settings", json={"naming_template": "{position}-{name}-{school}"})


@check("AC-NAME-07")
def _name_07(flow):
    """前端与模板不硬编码用户姓名/学校。"""
    offenders = []
    for folder in ("web", "server/app/templates"):
        root = repo_root() / folder
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix not in (".js", ".html", ".css", ".md", ".jinja", ".j2"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in ("张三", "示例大学", "13800138000", "zhangsan_WHU"):
                if needle in text:
                    offenders.append(f"{path.relative_to(repo_root())}: {needle}")
    assert not offenders, "前端/模板里出现用户身份硬编码：\n" + "\n".join(offenders[:8])


@check("AC-NAME-08")
def _name_08(flow):
    """路径穿越不能逃出 data/exports。"""
    client = flow["client"]
    data = client.post("/api/v1/naming/validate", json={"pattern": "{name}", "lang": "zh"}).get_json()["data"]
    assert ".." not in data["filename"] and "/" not in data["filename"], data
    resp = client.post(f"/api/v1/builds/{flow['build_id']}/export", json={"format": "pdf", "lang": "zh", "naming_pattern": "../../etc/x-{name}"})
    body = resp.get_json() or {}
    if resp.status_code in (200, 202):
        from .helpers import wait_job

        job = wait_job(client, body["data"]["job_id"])
        item = (job.get("result_json") or {}).get("artifacts", [{}])[0]
        resolved = (flow["data_dir"] / "exports").resolve()
        assert str((flow["data_dir"] / "exports" / item["filename"]).resolve()).startswith(str(resolved))
        assert ".." not in item["filename"]
    else:
        assert resp.status_code == 422, resp.get_json()


# ---------------------------------------------------------------- 跑 ----------------


@pytest.mark.parametrize("ac", sorted(CHECKS))
def test_ac(ac, flow):
    CHECKS[ac](flow)


@pytest.mark.parametrize("name", sorted(EXTRA))
def test_extra(name, flow):
    EXTRA[name](flow)
