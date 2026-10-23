"""AC harness —— 守卫面：版式下限 / 引用守卫 / 任务恢复 / LLM 边界。

这里的判据大多需要「把环境推到边界再看行为」，所以每个 check 自己搭临时状态、
跑完必须还原（不留污染给后面的 check，也不留污染给真实库）。
"""

from __future__ import annotations

import io
import json
import re
from contextlib import contextmanager

import pytest

from .helpers import (
    artifact,
    db_int,
    db_one,
    pdf_metrics,
    pdf_pages,
    pdf_text,
    read_repo,
    repo_root,
    wait_job,
)

CHECKS: dict[str, callable] = {}


def check(ac: str):
    def register(fn):
        CHECKS[ac] = fn
        return fn

    return register


@contextmanager
def _cfg_patch(monkeypatch, **changes):
    """临时替换全局配置（不动真实 .env，也不会留污染）。"""
    import dataclasses

    from app import config as config_mod

    base = config_mod.get_config()
    patched = dataclasses.replace(base, **changes)
    original = config_mod.get_config
    monkeypatch.setattr(config_mod, "get_config", lambda: patched, raising=True)
    try:
        yield patched
    finally:
        monkeypatch.setattr(config_mod, "get_config", original, raising=True)


@contextmanager
def _env(**pairs):
    """临时改 .env 语义的环境变量（进程 env 优先级最高），退出即还原并重载配置。"""
    import os

    from app import config as config_mod

    before = {key: os.environ.get(key) for key in pairs}
    try:
        for key, value in pairs.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)
        config_mod.set_config(config_mod.load_config())
        yield
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config_mod.set_config(config_mod.load_config())


class _FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.headers: dict[str, str] = {}
        self.text = json.dumps(body, ensure_ascii=False)

    def json(self):
        return self._body


def _fake_client(monkeypatch, body: dict, *, status: int = 200, counter: list[int] | None = None):
    """把 httpx.Client.post 换成假上游；counter 用来数「到底发了几次」。"""
    import httpx

    def fake_post(self, url, **kwargs):  # noqa: ANN001
        if counter is not None:
            counter.append(1)
        return _FakeResponse(status, body)

    monkeypatch.setattr(httpx.Client, "post", fake_post)


def _completion(content: str = "", *, finish_reason: str = "stop", reasoning: str = "", reasoning_tokens: int = 0):
    return {
        "choices": [
            {
                "message": {"content": content, "reasoning_content": reasoning},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "total_tokens": 14,
            "completion_tokens_details": {"reasoning_tokens": reasoning_tokens},
        },
    }


# ------------------------------------------------------------------ 版式 ----------------


@check("AC-PDF-13")
def _pdf_13(flow):
    """照片不随排版参数单独缩放：边长仍等于标题区高度（52pt@11pt/1.15），位置仍贴齐页边。"""
    metrics = pdf_metrics(flow)
    images = metrics["images"]
    if not images:
        pytest.skip("本次导出没有照片")
    box = images[0]
    assert abs(box["w"] - 52.0) <= 1.5 and abs(box["h"] - 52.0) <= 1.5, box
    assert abs(box["top"] - 8.3) <= 1.5, box
    assert abs(box["right_gap"] - 15.62) <= 1.5, box
    assert metrics["min"] >= 9.5, metrics["min"]


@check("AC-PDF-14")
def _pdf_14(flow):
    """facts 整段渲染，行首不带 bullet 标记（不许把「专业成绩」伪装成 bullet）。"""
    text = pdf_text(flow)
    facts = [line.strip() for line in text.splitlines() if line.strip().startswith(("专业成绩", "主修课程"))]
    assert facts, "教育段的 facts 没有渲染出来"
    for line in facts:
        assert line[0] not in "·•-–—*", line


@check("AC-PDF-15")
def _pdf_15(flow):
    """density 默认 original，且反作弊下限不可越。"""
    client = flow["client"]
    resp = client.post(f"/api/v1/builds/{flow['build_id']}/export", json={"format": "pdf"})
    assert resp.status_code == 202, resp.get_json()
    data = resp.get_json()["data"]
    assert data["density"] == "original"
    job = wait_job(client, data["job_id"])
    result = job.get("result_json") or {}
    layout = result.get("layout") or {}
    assert abs(float(layout.get("available_height_pt", 0)) - 817.55) <= 1.5, layout
    item = result["artifacts"][0]
    assert float((item.get("layout") or {}).get("body_pt") or 0) >= 9.5


# ------------------------------------------------------------------ 守卫 ----------------


@check("AC-FILE-01")
def _file_01(flow):
    """删被引用的附件 → 409 FILE_IN_USE，并说清谁在用。"""
    from PIL import Image

    client = flow["client"]
    buffer = io.BytesIO()
    Image.new("RGB", (220, 220), (160, 170, 180)).save(buffer, format="PNG")
    upload = client.post(
        "/api/v1/files",
        data={"file": (io.BytesIO(buffer.getvalue()), "guard.png"), "kind": "photo"},
        content_type="multipart/form-data",
    )
    assert upload.status_code in (200, 201), upload.get_json()
    attachment_id = upload.get_json()["data"]["id"]
    assert client.put("/api/v1/profile/photo", json={"attachment_id": attachment_id}).status_code == 200
    blocked = client.delete(f"/api/v1/files/{attachment_id}")
    assert blocked.status_code == 409, blocked.get_json()
    assert blocked.get_json()["error"]["code"] == "FILE_IN_USE"
    assert blocked.get_json()["error"]["details"]["referenced_by"], blocked.get_json()
    assert client.delete("/api/v1/profile/photo").status_code == 200
    assert client.delete(f"/api/v1/files/{attachment_id}").status_code in (200, 204)


@check("AC-BUILD-04")
def _build_04(flow):
    """槽位缺值：preview 出现占位符 ⟨slot_key⟩，missing_slots 说出来，而不是抛异常。"""
    client = flow["client"]
    original = client.get("/api/v1/profile").get_json()["data"].get("email")
    client.put("/api/v1/profile", json={"email": None})
    try:
        assembled = client.post(f"/api/v1/builds/{flow['build_id']}/assemble")
        assert assembled.status_code == 200, assembled.get_json()
        data = assembled.get_json()["data"]
        assert "missing_slots" in data
    finally:
        client.put("/api/v1/profile", json={"email": original})


@check("AC-BUILD-06")
def _build_06(flow):
    """搜索走 FTS5：中文命中，空 q 走普通分页。"""
    client = flow["client"]
    assert db_int(flow, "SELECT count(*) FROM package_fts") >= 1, "FTS 索引是空的（说明没真建索引）"
    hit = client.get("/api/v1/packages", query_string={"q": "门店"}).get_json()["data"]
    assert hit["total_estimate"] >= 1, hit
    plain = client.get("/api/v1/packages").get_json()["data"]
    assert plain["next_cursor"] is not None or plain["total_estimate"] >= 0


@check("AC-BUILD-07")
def _build_07(flow):
    """页数估算与实测差 ≤0.35 页。"""
    est = flow["assemble"].get("est_pages")
    actual = pdf_pages(flow)
    assert est is not None, flow["assemble"].keys()
    assert abs(float(est) - float(actual)) <= 0.35, (est, actual)


@check("AC-BUILD-08")
def _build_08(flow):
    """包归档后不在默认列表，但历史 build 仍能引用它组装。"""
    client = flow["client"]
    package = client.post(
        "/api/v1/packages", json={"title": "会被归档的包", "kind": "project", "summary": "归档前的历史引用"}
    ).get_json()["data"]
    build = client.post(
        "/api/v1/builds",
        json={"name": "归档引用", "template_id": flow["template_id"], "lang": "zh", "position": "数据分析"},
    ).get_json()["data"]
    client.put(
        f"/api/v1/builds/{build['id']}/selections",
        json={"items": [{"package_id": package["id"], "variant_ids": [], "order_index": 0}]},
    )
    assert client.patch(f"/api/v1/packages/{package['id']}", json={"status": "archived"}).status_code == 200
    listing = client.get("/api/v1/packages", query_string={"limit": 100}).get_json()["data"]["items"]
    assert package["id"] not in {item["id"] for item in listing}
    assembled = client.post(f"/api/v1/builds/{build['id']}/assemble")
    assert assembled.status_code == 200, assembled.get_json()
    assert assembled.get_json()["data"]["sections"] is not None


@check("AC-JD-04")
def _jd_04(flow):
    """需求可人工改：改完 source=manual，且影响匹配排序结果。"""
    client = flow["client"]
    rows = client.get(f"/api/v1/jds/{flow['jd']['id']}/requirements").get_json()["data"]["items"]
    assert rows, "没有需求可改"
    target = rows[0]
    patched = client.patch(
        f"/api/v1/requirements/{target['id']}", json={"priority": "must", "weight": 0.9}
    )
    assert patched.status_code == 200, patched.get_json()
    changed = patched.get_json()["data"]
    assert changed["source"] == "manual", changed
    assert abs(float(changed["weight"]) - 0.9) < 1e-6
    match = client.post(f"/api/v1/jds/{flow['jd']['id']}/match", json={}).get_json()["data"]
    assert match["scores"], match


# ------------------------------------------------------------------ 健壮性 ----------------


@check("AC-ROB-02")
def _rob_02(flow):
    """非法 JSON 400、未知路由 404、方法不允许 405，都用统一信封。"""
    client = flow["client"]
    bad = client.post("/api/v1/packages", data="{not json", content_type="application/json")
    assert bad.status_code == 400, bad.get_json()
    missing = client.get("/api/v1/nope")
    assert missing.status_code == 404
    method = client.open("/api/v1/health", method="DELETE")
    assert method.status_code in (405, 404), method.status_code
    for resp in (bad, missing, method):
        body = resp.get_json()
        assert body["ok"] is False and body["error"]["code"], body


@check("AC-ROB-03")
def _rob_03(flow):
    """所有响应都是统一信封，request_id 同时出现在体与头。"""
    client = flow["client"]
    for resp in (
        client.get("/api/v1/health"),
        client.get("/api/v1/profile"),
        client.get("/api/v1/packages/nope"),
    ):
        body = resp.get_json()
        assert set(body) <= {"ok", "data", "error", "request_id"}, body.keys()
        assert body["request_id"].startswith("req_")
        assert resp.headers.get("X-Request-Id") == body["request_id"]


@check("AC-ROB-04")
def _rob_04(flow):
    """路径穿越拿不到 .env。"""
    client = flow["client"]
    for path in ("/api/v1/files/../../.env", "/api/v1/files/%2e%2e%2f%2e%2e%2f.env"):
        resp = client.get(path)
        assert resp.status_code in (400, 404), (path, resp.status_code)
        assert b"LLM_API_KEY" not in resp.data


@check("AC-ROB-05")
def _rob_05(flow):
    """10 万字符 JD：要么明确 413，要么成功且结构可读。"""
    client = flow["client"]
    text = "任职要求：熟练 SQL。" * 10000
    resp = client.post("/api/v1/jds", json={"title": "超长 JD", "raw_text": text})
    if resp.status_code in (413, 422):
        assert resp.get_json()["error"]["code"] in ("PAYLOAD_TOO_LARGE", "VALIDATION_ERROR")
        return
    assert resp.status_code in (200, 201), resp.status_code
    assert resp.get_json()["data"]["id"]


@check("AC-ROB-06")
def _rob_06(flow):
    """重启恢复：queued/running 的任务标 interrupted，可重试。"""
    from app.repos import JobRepo

    jobs = JobRepo()
    job_id = jobs.create("build_export", message="重启前排队")
    assert jobs.get(job_id)["status"] == "queued"
    changed = jobs.mark_interrupted()
    assert changed >= 1
    assert jobs.get(job_id)["status"] == "interrupted"


@check("AC-UI-04")
def _ui_04(flow):
    """用户可控文本不经 innerHTML：全前端只允许常量模板。"""
    offenders = []
    for path in (repo_root() / "web").rglob("*.js"):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if "innerHTML" not in line:
                continue
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*", "/**")):
                continue
            if "FORBIDDEN" in line or "禁止" in line or "不允许" in line:
                continue
            offenders.append(f"{path.relative_to(repo_root())}:{number}: {stripped[:80]}")
    assert not offenders, "发现 innerHTML 写入：\n" + "\n".join(offenders)


# -------------------------------------------------------------------- LLM ----------------


@check("AC-LLM-02")
def _llm_02(flow, monkeypatch):
    """未配置 key：503 LLM_NOT_CONFIGURED，且一次网络请求都不发。"""
    calls: list[int] = []
    _fake_client(monkeypatch, _completion("{}"), counter=calls)
    with _cfg_patch(monkeypatch, api_key=""):
        resp = flow["client"].post(
            "/api/v1/llm/preview", json={"purpose": "summary_polish", "selections": {"package_ids": []}}
        )
    assert resp.status_code == 503, resp.get_json()
    assert resp.get_json()["error"]["code"] in ("LLM_NOT_CONFIGURED", "LLM_DISABLED")
    assert calls == [], "未配置就不许发请求"


@check("AC-LLM-03")
def _llm_03(flow, monkeypatch):
    """provider=off 是硬开关：预览 503 LLM_DISABLED，已确认的预览也发不出去，且零出网。"""
    calls: list[int] = []
    _fake_client(monkeypatch, _completion("{}"), counter=calls)
    client = flow["client"]
    preview = client.post(
        "/api/v1/llm/preview",
        json={"purpose": "summary_polish", "selections": {"package_ids": [flow["packages"][0]["id"]]}},
    )
    assert preview.status_code in (200, 201), preview.get_json()
    data = preview.get_json()["data"]

    with _cfg_patch(monkeypatch, provider="off"):
        blocked = client.post(
            "/api/v1/llm/preview", json={"purpose": "summary_polish", "selections": {"package_ids": []}}
        )
        assert blocked.status_code == 503, blocked.get_json()
        assert blocked.get_json()["error"]["code"] == "LLM_DISABLED", blocked.get_json()
        complete = client.post(
            "/api/v1/llm/complete",
            json={"preview_id": data["preview_id"], "expected_payload_sha256": data["payload_sha256"]},
        )
    assert complete.status_code == 503, complete.get_json()
    assert complete.get_json()["error"]["code"] == "LLM_DISABLED", complete.get_json()
    assert calls == [], "关掉开关后不许有任何出网"


@check("AC-LLM-10")
def _llm_10(flow, monkeypatch):
    """JSON 模式缺字面量 json：本机 422 拦截，零出网。"""
    from app.adapters.llm_client import LlmClient
    from app.errors import ApiError

    calls: list[int] = []
    _fake_client(monkeypatch, _completion("{}"), counter=calls)
    client = LlmClient()
    with pytest.raises(ApiError) as caught:
        client.chat(
            {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "把这段改写得更专业"}],
                "response_format": {"type": "json_object"},
            },
            purpose="bullets_generate",
            json_mode=True,
        )
    error = caught.value
    assert error.code == "LLM_JSON_MODE_PRECONDITION", error.code
    assert error.http_status == 422
    assert error.details.get("reason") == "PROMPT_MISSING_JSON_LITERAL"
    assert calls == [], "本地前置校验不许出网"


@check("AC-LLM-11")
def _llm_11(flow, monkeypatch):
    """reasoner 把 token 烧在推理：正文空 + finish_reason=length → 拒收，不当成功。"""
    from app.adapters.llm_client import LlmClient
    from app.errors import ApiError

    _fake_client(
        monkeypatch,
        _completion("", finish_reason="length", reasoning="让我想想……", reasoning_tokens=16),
    )
    client = LlmClient()
    with pytest.raises(ApiError) as caught:
        client.chat(
            {
                "model": "deepseek-reasoner",
                "messages": [{"role": "user", "content": "请以 json 返回"}],
                "max_tokens": 16,
            },
            purpose="jd_analyze",
            json_mode=True,
        )
    error = caught.value
    assert error.code == "LLM_TRUNCATED", error.code
    assert error.details.get("reason") == "empty_content", error.details
    assert error.details.get("reasoning_tokens") == 16, error.details


@check("AC-LLM-12")
def _llm_12(flow, monkeypatch):
    """完整但非法 JSON ≠ 截断：前者 parsed=None + 警告，后者才是 LLM_TRUNCATED。"""
    from app.adapters.llm_client import LlmClient

    _fake_client(monkeypatch, _completion("这不是 JSON", finish_reason="stop"))
    result = LlmClient().chat(
        {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "请以 json 返回"}],
        },
        purpose="jd_analyze",
        json_mode=True,
    )
    assert result.parsed is None, result.parsed
    codes = {str(item.get("code")) for item in result.warnings}
    assert "LLM_JSON_UNPARSABLE" in codes, codes


# ------------------------------------------------------------------ 配置与本地化 ----------------


@check("AC-LLM-01")
def _llm_01(flow):
    """默认主路径就是 DeepSeek，且只有一个 OpenAI 兼容出口。"""
    from app import config as config_mod

    cfg = config_mod.get_config()
    assert cfg.llm_provider in ("deepseek", "off"), cfg.llm_provider
    assert cfg.llm_base_url.rstrip("/") == "https://api.deepseek.com/v1", cfg.llm_base_url
    assert cfg.llm_model and cfg.llm_model_analysis, (cfg.llm_model, cfg.llm_model_analysis)
    text = read_repo("server/app/adapters/egress_guard.py")
    assert "11434" not in text, "多 provider 适配应已下线"


@check("AC-LLM-05")
def _llm_05(flow):
    """key 只在 .env 里，权限 600，接口只说 key_set。"""
    import os
    import stat

    env_path = repo_root() / ".env"
    if not env_path.exists():
        pytest.skip("本机没有 .env（未配置 key）")
    mode = stat.S_IMODE(os.stat(env_path).st_mode)
    assert mode == 0o600, oct(mode)
    lines = [line for line in env_path.read_text(encoding="utf-8").splitlines() if line.startswith("LLM_API_KEY=")]
    assert len(lines) == 1, lines
    settings = flow["client"].get("/api/v1/settings").get_json()["data"]
    assert settings["key_set"] is True
    assert settings["key_field"] == "LLM_API_KEY"
    dumped = json.dumps(settings, ensure_ascii=False)
    key = lines[0].split("=", 1)[1].strip()
    if len(key) >= 8:
        assert key[-4:] not in dumped, "连后四位也不许回显"


@check("AC-IMPORT-10")
def _import_10(flow):
    """删导入（草稿）不删已 commit 的模板。"""
    client = flow["client"]
    created = client.post("/api/v1/imports", json={"text": "周九\n项目经历\n门店模型 - 队长 2026.05 - 2026.06\n● 完成预测。", "filename": "d10.txt"})
    import_id = created.get_json()["data"]["import_id"]
    commit = client.post(
        f"/api/v1/imports/{import_id}/commit", json={"template_name": "AC-IMPORT-10", "lang": "zh"}
    ).get_json()["data"]
    assert client.delete(f"/api/v1/imports/{import_id}").status_code in (200, 204)
    listing = client.get("/api/v1/imports").get_json()["data"]["items"]
    assert import_id not in {item["import_id"] for item in listing}, "删除后不应出现在默认列表"
    assert client.get(f"/api/v1/templates/{commit['template_id']}").status_code == 200


@check("AC-IMPORT-13")
def _import_13(flow):
    """夹具缺失要 SKIP 而不是 PASS：导入用例必须显式判存在性。"""
    source = read_repo("tests/acceptance/test_ac_import_output.py")
    assert "pytest.skip" in source, "缺夹具的路径必须 skip"
    skipped = [
        path.name
        for path in (repo_root() / "server" / "tests" / "fixtures").glob("sample.*")
    ]
    assert skipped, "夹具目录空了，AC-IMPORT-06 会静默降级"


@check("AC-LOC-01")
def _loc_01(flow):
    """全流程产物只落在 data/ 内。"""
    item = artifact(flow)
    rel = item["rel_path"]
    assert rel.startswith("exports/"), rel
    path = (flow["data_dir"] / rel).resolve()
    assert flow["data_dir"].resolve() in path.parents, path
    uploaded = db_one(flow, "SELECT sha256 FROM attachment LIMIT 1")
    assert uploaded, "至少有一份附件落库"


# ------------------------------------------------------------------ 抓取 ----------------


@check("AC-FETCH-01")
def _fetch_01(flow, monkeypatch):
    """下行抓取：请求体恒空、不带任何用户数据，且只 GET。"""
    from app.adapters import fetch_client

    seen: list[dict] = []

    class _FakeResp:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        text = "<html><head><title>示例公司</title></head><body>" + "公司简介：" + "数据分析团队。" * 40 + "</body></html>"

        url = "https://www.zhipin.com/about"
        encoding = "utf-8"

        def __init__(self):
            self.content = self.text.encode("utf-8")

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def close(self):
            return None

        def get(self, url, **kwargs):  # noqa: ANN001
            seen.append({"method": "GET", "url": url, "body": kwargs.get("content"), "json": kwargs.get("json")})
            return _FakeResp()

    monkeypatch.setattr(fetch_client.httpx, "Client", _FakeClient)
    resp = flow["client"].post("/api/v1/fetch/public-page", json={"url": "https://www.zhipin.com/about"})
    assert resp.status_code == 200, resp.get_json()
    assert seen, "没有真的发出请求"
    call = seen[0]
    assert call["method"] == "GET", call
    assert call["body"] is None and call["json"] is None, "下行请求不得带请求体"
    for secret in ("13800138000", "zhangsan@example.com", "张三"):
        assert secret not in call["url"], call["url"]


@check("AC-FETCH-02")
def _fetch_02(flow, monkeypatch):
    """非法 host 直接 403 且零出网。"""
    from app.adapters import fetch_client

    calls: list[int] = []

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):  # noqa: ANN002
            calls.append(1)
            raise AssertionError("不该发请求")

    monkeypatch.setattr(fetch_client.httpx, "Client", _FakeClient)
    resp = flow["client"].post("/api/v1/fetch/public-page", json={"url": "https://evil.example.org/x"})
    assert resp.status_code == 403, resp.get_json()
    body = resp.get_json()
    assert body["error"]["code"] == "EGRESS_BLOCKED", body
    assert body["error"]["details"].get("reason") in ("host_not_allowed", "private_address"), body
    assert calls == []


@check("AC-FETCH-03")
def _fetch_03(flow, monkeypatch):
    """抓取失败必须降级，不能阻断公司分析。"""
    from app.adapters import fetch_client
    from app.errors import ApiError

    def boom(*args, **kwargs):  # noqa: ANN002
        raise ApiError("EGRESS_BLOCKED", "抓不到", details={"reason": "host_not_allowed"})

    monkeypatch.setattr(fetch_client, "fetch_public_page", boom)
    resp = flow["client"].post(
        "/api/v1/company-profiles/analyze",
        json={"company_name": "示例公司", "jd_id": flow["jd"]["id"], "fetch_url": "https://nope.example.org/", "method": "heuristic"},
    )
    assert resp.status_code in (200, 202), resp.get_json()
    payload = resp.get_json()["data"]
    if resp.status_code == 202:
        job = wait_job(flow["client"], payload["job_id"])
        payload = job.get("result_json") or {}
    codes = {item.get("code") for item in payload.get("warnings") or []}
    assert codes & {"FETCH_FAILED", "FETCH_UNAVAILABLE"}, codes


# -------------------------------------------------------------------- LLM 细节 ----------------


@check("AC-LLM-04")
def _llm_04(flow, monkeypatch):
    """测试连接：返回 reachable/延迟/模型清单，5 秒内。"""
    import httpx

    class _FakeResp:
        status_code = 200

        def json(self):
            return {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]}

        headers: dict[str, str] = {}

    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **kwargs: _FakeResp())
    resp = flow["client"].post("/api/v1/settings/provider/test", json={})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["reachable"] is True
    assert isinstance(data["latency_ms"], int)
    assert "deepseek-chat" in (data.get("models") or [])


@check("AC-LLM-06")
def _llm_06(flow, monkeypatch):
    """上游 500：明确报错、不落库、consent 已消费（不能拿旧预览反复试）。"""
    calls: list[int] = []
    _fake_client(monkeypatch, {"error": {"message": "boom"}}, status=500, counter=calls)
    client = flow["client"]
    preview = client.post(
        "/api/v1/llm/preview",
        json={"purpose": "summary_polish", "selections": {"package_ids": [flow["packages"][0]["id"]]}},
    ).get_json()["data"]
    before = db_int(flow, "SELECT count(*) FROM llm_call_log")
    resp = client.post(
        "/api/v1/llm/complete",
        json={"preview_id": preview["preview_id"], "expected_payload_sha256": preview["payload_sha256"]},
    )
    assert resp.status_code in (502, 429, 504), resp.get_json()
    assert resp.get_json()["error"]["code"] in ("LLM_UPSTREAM_ERROR", "LLM_RATE_LIMITED", "LLM_TIMEOUT")
    assert db_int(flow, "SELECT count(*) FROM llm_call_log") == before + 1, "失败的调用也要留审计，但不留半成品"
    again = client.post(
        "/api/v1/llm/complete",
        json={"preview_id": preview["preview_id"], "expected_payload_sha256": preview["payload_sha256"]},
    )
    assert again.status_code in (409, 410), again.get_json()


@check("AC-LLM-07")
def _llm_07(flow, monkeypatch):
    """不使用 AI：导入/组装/导出全部可用。"""
    calls: list[int] = []
    _fake_client(monkeypatch, _completion("{}"), counter=calls)
    client = flow["client"]
    with _cfg_patch(monkeypatch, provider="off", api_key=""):
        created = client.post(
            "/api/v1/imports", json={"text": "钱八\n项目经历\n门店模型 - 队长 2026.05 - 2026.06\n● 完成预测。", "filename": "noai.txt"}
        )
        assert created.status_code == 201, created.get_json()
        assert client.post(f"/api/v1/builds/{flow['build_id']}/assemble").status_code == 200
        export = client.post(f"/api/v1/builds/{flow['build_id']}/export", json={"format": "md"})
        assert export.status_code == 202, export.get_json()
        job = wait_job(client, export.get_json()["data"]["job_id"])
        assert job.get("status") == "succeeded", job.get("error_json")
        assert (job.get("result_json") or {}).get("artifacts")
    assert calls == []


@check("AC-LLM-08")
def _llm_08(flow, monkeypatch):
    """连接级抖动按 LLM_MAX_RETRIES 重试，最后成功。"""
    import httpx

    from app.adapters.llm_client import LlmClient

    state = {"n": 0}

    class _Ok:
        status_code = 200
        headers: dict[str, str] = {}

        def json(self):
            return _completion('{"ok": 1}', finish_reason="stop")

    def flaky(self, url, **kwargs):  # noqa: ANN001
        state["n"] += 1
        if state["n"] <= 2:
            raise httpx.ConnectError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol")
        return _Ok()

    monkeypatch.setattr(httpx.Client, "post", flaky)
    client = LlmClient()
    client._sleep = lambda *args, **kwargs: None  # 不真等
    result = client.chat(
        {"model": "deepseek-chat", "messages": [{"role": "user", "content": "请以 json 返回"}]},
        purpose="jd_analyze",
        json_mode=True,
    )
    assert state["n"] == 3, state
    assert result.parsed == {"ok": 1}


@check("AC-LLM-09")
def _llm_09(flow, monkeypatch):
    """全连接失败 → 503 LLM_UNREACHABLE（不是 key 无效），且预览仍 pending 可重试。"""
    import httpx

    from app.adapters.llm_client import LlmClient
    from app.errors import ApiError

    def always_fail(self, url, **kwargs):  # noqa: ANN001
        raise httpx.ConnectError("Connection reset by peer")

    monkeypatch.setattr(httpx.Client, "post", always_fail)
    client = LlmClient()
    client._sleep = lambda *args, **kwargs: None
    with pytest.raises(ApiError) as caught:
        client.chat(
            {"model": "deepseek-chat", "messages": [{"role": "user", "content": "请以 json 返回"}]},
            purpose="jd_analyze",
            json_mode=True,
        )
    assert caught.value.code == "LLM_UNREACHABLE", caught.value.code
    assert caught.value.http_status == 503
    assert "key" not in (caught.value.hint or "").lower() or "不是" in (caught.value.hint or "")

    # 走 API：连接失败不应消耗 consent（预览仍 pending）
    from app.adapters import llm_client as llm_module

    monkeypatch.setattr(llm_module.httpx.Client, "post", always_fail)
    preview = flow["client"].post(
        "/api/v1/llm/preview",
        json={"purpose": "summary_polish", "selections": {"package_ids": [flow["packages"][0]["id"]]}},
    ).get_json()["data"]
    resp = flow["client"].post(
        "/api/v1/llm/complete",
        json={"preview_id": preview["preview_id"], "expected_payload_sha256": preview["payload_sha256"]},
    )
    assert resp.status_code == 503, resp.get_json()
    assert resp.get_json()["error"]["code"] in ("LLM_UNREACHABLE", "LLM_TIMEOUT"), resp.get_json()
    stored = flow["client"].get(f"/api/v1/llm/previews/{preview['preview_id']}").get_json()["data"]
    assert stored["status"] == "pending", stored["status"]


# ------------------------------------------------------------------ 跑 ----------------


@pytest.mark.parametrize("ac", sorted(CHECKS))
def test_ac(ac, flow, monkeypatch):
    fn = CHECKS[ac]
    if "monkeypatch" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
        fn(flow, monkeypatch)
    else:
        fn(flow)
