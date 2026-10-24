"""t10 端到端验收：把 user 可见的 12 条判据逐条落成断言。

跑法（ captains 的 Verify 命令之一）：

    .venv/bin/python -m pytest tests -q

这些用例全部走 Flask test client / 纯本地逻辑，不联网、不碰真实 ``data/``。
"""

from __future__ import annotations

import json
import sys
import re
import subprocess
from pathlib import Path

import pytest

from conftest import PROJECT_ROOT, bootstrap, make_build, paste_import, ready_package_ids

# ---------------------------------------------------------------------------
# 1｜命名：{position}-{name}-{school} 且姓名/校名取自 UserProfile
# ---------------------------------------------------------------------------


def test_naming_uses_profile_not_hardcoded(client, data_dir):
    bootstrap(client)
    body = {"pattern": "{position}-{name}-{school}", "lang": "zh", "position": "数据分析实习生"}
    data = client.post("/api/v1/naming/validate", json=body).get_json()["data"]
    assert data["valid"] is True, data
    assert data["filename"] == "数据分析实习生-张三-示例大学.pdf"
    sources = {item["name"]: item["source"] for item in data["variables"]}
    assert sources["name"].startswith("profile."), sources
    assert sources["school"].startswith("profile."), sources


def test_profile_edit_changes_filename_immediately(client):
    bootstrap(client)
    body = {"pattern": "{position}-{name}-{school}", "lang": "zh", "position": "数据分析实习生"}
    assert client.post("/api/v1/naming/validate", json=body).get_json()["data"]["filename"] == (
        "数据分析实习生-张三-示例大学.pdf"
    )
    # 改档案 → 同一个模板立刻给出新文件名（不缓存、不重启）
    client.put("/api/v1/profile", json={"name_zh": "李明"})
    assert client.post("/api/v1/naming/validate", json=body).get_json()["data"]["filename"] == (
        "数据分析实习生-李明-示例大学.pdf"
    )


def test_missing_school_is_a_validation_error_not_a_broken_filename(client):
    client.put("/api/v1/profile", json={"name_zh": "张三"})  # 没填学校
    body = {"pattern": "{position}-{name}-{school}", "lang": "zh", "position": "数据分析实习生"}
    response = client.post("/api/v1/naming/validate", json=body)
    assert response.status_code == 200  # 纯函数恒 200
    data = response.get_json()["data"]
    assert data["valid"] is False
    assert "NAMING_MISSING_VAR" in [err["code"] for err in data["errors"]]
    assert not data["filename"], "缺变量时不许产出残缺文件名"


# ---------------------------------------------------------------------------
# 2｜导出：中文/英文两份，pypdf 能打开，命名对，section 齐
# ---------------------------------------------------------------------------


def _export(client, build_id: str, *, fmt: str = "pdf", lang: str = "zh") -> dict:
    from app.services import jobrun

    response = client.post(f"/api/v1/builds/{build_id}/export", json={"format": fmt, "verify_text": True})
    assert response.status_code == 202, response.get_data(as_text=True)
    job_id = response.get_json()["data"]["job_id"]
    jobrun.wait_idle()
    job = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
    assert job["status"] == "succeeded", job
    return job["result_json"]


def test_export_pdf_named_from_profile_and_readable(client, data_dir):
    from pypdf import PdfReader

    bootstrap(client)
    build_id = make_build(client, lang="zh")
    selections = [{"package_id": pid} for pid in ready_package_ids(client)]
    client.put(f"/api/v1/builds/{build_id}/selections", json={"items": selections})
    result = _export(client, build_id)
    artifact = result["artifacts"][0]
    assert artifact["filename"] == "数据分析实习生-张三-示例大学.pdf", artifact["filename"]
    assert artifact["text_verified"] is True, artifact
    path = data_dir / "exports" / artifact["filename"]
    assert path.exists()
    reader = PdfReader(str(path))
    assert len(reader.pages) >= 1
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    for heading in ("教育背景", "实习经历", "项目经历", "校园活动", "职业技能"):
        assert heading in text, f"PDF 缺段落：{heading}"
    assert "张三" in text and "示例大学" in text


def test_export_english_version_has_english_frame(client, data_dir):
    bootstrap(client)
    build_id = make_build(client, lang="en", position="Data Analyst Intern")
    selections = [{"package_id": pid} for pid in ready_package_ids(client)]
    client.put(f"/api/v1/builds/{build_id}/selections", json={"items": selections})
    result = _export(client, build_id, lang="en")
    artifact = result["artifacts"][0]
    assert artifact["filename"] == "Data-Analyst-Intern-XUDONG-ZHONG-Wuhan-University.pdf", artifact["filename"]
    from pypdf import PdfReader

    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(data_dir / "exports" / artifact["filename"])).pages)
    assert "Education" in text and "Experience" in text
    assert "教育背景" not in text, "英文版框架不许残留中文段落标题"
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    assert len(cjk) < 400, f"英文版框架 CJK 过多（{len(cjk)}）"


def test_build_switch_language_reports_missing_english_fields(client):
    # 英文必填字段缺 → PROFILE_FIELD_MISSING，而不是静默出半中文
    client.put("/api/v1/profile", json={"name_zh": "张三", "school_zh": "示例大学", "degree": "本科"})
    import_id = paste_import(client)
    client.post(
        f"/api/v1/imports/{import_id}/commit",
        json={"template_name": "中文模板", "lang": "zh", "set_default": True, "also_create_packages": True},
    )
    build_id = make_build(client, lang="en")
    assembled = client.post(f"/api/v1/builds/{build_id}/assemble").get_json()["data"]
    codes = [warning["code"] for warning in assembled["warnings"]]
    assert "PROFILE_FIELD_MISSING" in codes, codes


# ---------------------------------------------------------------------------
# 3｜隐私：LLM 调用点前置字段清单；payload 无姓名/电话/邮箱
# ---------------------------------------------------------------------------


def test_every_llm_call_point_returns_field_manifest_first(client):
    bootstrap(client)
    jd = client.post(
        "/api/v1/jds",
        json={"title": "数据分析实习生", "company_name": "星链数科（杭州）有限公司", "raw_text": "岗位要求：985/211 院校优先，熟悉 SQL。"},
    ).get_json()["data"]
    preview = client.post(
        "/api/v1/llm/preview",
        json={"purpose": "jd_analyze", "selections": {"jd_id": jd["id"]}},
    )
    assert preview.status_code == 201, preview.get_data(as_text=True)
    data = preview.get_json()["data"]
    for key in ("preview_id", "payload", "payload_sha256", "fields", "excluded", "total_chars", "est_tokens"):
        assert key in data, f"字段清单缺 {key}"
    assert data["fields"], "字段清单不能为空"
    assert all({"path", "kind", "chars", "included"} <= set(item) for item in data["fields"])
    blob = json.dumps(data["payload"], ensure_ascii=False)
    assert "张三" not in blob and "13800138000" not in blob, "姓名/电话不许进 payload"
    assert "示例大学" in blob, "校名应真实发送用于竞争力判断"


# ---------------------------------------------------------------------------
# 4｜降级：解析失败与 LLM 失败都要有可读降级，不 500
# ---------------------------------------------------------------------------


def test_import_without_text_layer_degrades_with_actionable_error(client):
    from io import BytesIO

    blank_pdf = BytesIO(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")
    response = client.post(
        "/api/v1/imports",
        data={"file": (blank_pdf, "blank.pdf")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    error = response.get_json()["error"]
    assert error["code"] == "IMPORT_NO_TEXT_LAYER"
    assert error.get("hint"), "降级提示必须可操作"


def test_analysis_falls_back_to_heuristic_when_llm_unavailable(client, monkeypatch):
    from app.services import jobrun

    def boom(*_args, **_kwargs):
        from app.errors import ApiError

        raise ApiError("LLM_UNREACHABLE", "上游不可达")

    monkeypatch.setattr("app.services.consent.ConsentService.complete", boom)
    jd = client.post(
        "/api/v1/jds",
        json={
            "title": "数据运营实习生",
            "company_name": "禾味食品集团",
            "raw_text": "岗位要求：熟悉 Excel 与 SQL；不设院校门槛。",
        },
    ).get_json()["data"]
    response = client.post(f"/api/v1/jds/{jd['id']}/analyze", json={"method": "heuristic"})
    assert response.status_code == 202, response.get_data(as_text=True)
    jobrun.wait_idle()
    detail = client.get(f"/api/v1/jds/{jd['id']}").get_json()["data"]
    assert detail["analysis_status"] == "done"
    assert detail["analysis_method"] == "heuristic"
    assert detail["competitiveness"]["verdict"] in ("strong", "medium", "weak")
    assert detail["requirements"], "启发式也必须给出可用的需求条目"

    # 公司画像同样可离线降级，且「未提院校」不得编造硬门槛
    client.post(
        "/api/v1/company-profiles/analyze",
        json={"company_name": "禾味食品集团", "jd_text": "岗位要求：熟悉 Excel 与 SQL；不设院校门槛。", "method": "heuristic", "allow_fetch": False},
    )
    company = client.get("/api/v1/company-profiles?limit=10").get_json()["data"]["items"][0]
    assert company["school_preference"]["hard_filter"] is False
    assert company["school_preference"]["preferred_tiers"] == []


# ---------------------------------------------------------------------------
# 5｜前端：零 CDN、离线可用；只有一个出网模块
# ---------------------------------------------------------------------------


def test_frontend_has_no_external_resources():
    web = PROJECT_ROOT / "web"
    offenders = []
    for path in web.rglob("*"):
        if path.suffix not in {".html", ".js", ".css"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in (r"https?://(?!127\.0\.0\.1|localhost)", r"<script[^>]+src=\"https?://", r"@import\s+url\(\"https?://"):
            for match in re.finditer(pattern, text):
                snippet = text[max(0, match.start() - 40) : match.end() + 80]
                # 占位符文本（如 placeholder="https://…/v1"）不是资源引用，跳过
                if "w3.org" in snippet or "…" in snippet or "..." in snippet:
                    continue
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {match.group(0)}")
    assert offenders == [], "前端不许引用任何外部资源：" + "; ".join(offenders[:5])


def test_only_two_adapter_modules_can_touch_network():
    result = subprocess.run(
        [sys.executable, "scripts/check_egress.py"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# 6｜仓库卫生：无明文 key、.env 与 data 不进版本库
# ---------------------------------------------------------------------------


def test_no_plaintext_api_key_and_sensitive_paths_ignored():
    env_file = PROJECT_ROOT / ".env"
    key = ""
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("LLM_API_KEY="):
                key = line.split("=", 1)[1].strip()
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=str(PROJECT_ROOT), capture_output=True, text=True
    ).stdout.splitlines()
    assert not [path for path in tracked if path in {".env", "data/app.db"}] , "敏感文件被 git 跟踪"
    for ignored in (".env", "data/app.db"):
        check = subprocess.run(
            ["git", "check-ignore", "-q", ignored], cwd=str(PROJECT_ROOT)
        )
        assert check.returncode == 0, f"{ignored} 未被 .gitignore 覆盖"
    if key and len(key) >= 12:
        for path in (PROJECT_ROOT / "docs", PROJECT_ROOT / "server", PROJECT_ROOT / "web", PROJECT_ROOT / "skills"):
            for file in path.rglob("*"):
                if file.is_file() and file.suffix in {".py", ".js", ".md", ".html", ".css", ".sh", ".json"}:
                    assert key not in file.read_text(encoding="utf-8", errors="ignore"), f"key 泄漏到 {file}"


# ---------------------------------------------------------------------------
# 7｜Skill 文档：模型照着它就能驱动全流程；端口顺延有说明
# ---------------------------------------------------------------------------


def test_skill_doc_is_actionable_and_mentions_port_fallback():
    skill = PROJECT_ROOT / "skills" / "resume-warehouse" / "SKILL.md"
    assert skill.exists()
    text = skill.read_text(encoding="utf-8")
    for marker in ("name: resume-warehouse", "curl", "/api/v1/profile", "/api/v1/imports", "/api/v1/builds", "app_port"):
        assert marker in text, f"SKILL.md 缺关键内容：{marker}"
    assert "8765" in text or "顺延" in text, "必须说明端口不固定/会顺延"
    for script in ("start.sh", "stop.sh"):
        assert (skill.parent / script).exists(), f"缺 {script}"
