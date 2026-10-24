"""AC harness —— 用户拍板「以中文简历内的 GPA / 到岗时间为准」后的三条新条款。

planner 在 `docs/ACCEPTANCE.md` 登记了三条（157→160），本文件是它们的执行体：

| 编号 | 判据 |
|---|---|
| AC-CONFLICT-02 | 已决议字段降级为 `info` 且渲染值不变；删决议回 `warn`；`decided_by != "user"` 不得降级 |
| AC-PROF-01 | 教育段补充行可读写、快照可核、`[]` 合法、13 项 422 且一字不改、无默认模板 409、无教育块 422 |
| AC-PROF-02 | 改到岗时间两份 PDF 都变、英文表述优先、`available_date` 不参与渲染 |

三处负向都真跑（不是注释里的承诺）：删决议、`decided_by=auto`、无教育块的模板 ——
任何一条「静默通过」都会让用户在不知情的情况下拿到降级后的警告或旧数字。

「没有默认模板」「模板缺教育块」这两种现场需要**独立空库**，不能拿 `flow` 的库去
临时改默认模板（会污染同会话里其它 AC）。它们走 `_fresh_env()`：子进程 + 仓库内临时
`DATA_DIR`，跑完即弃。
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

CHECKS: dict[str, callable] = {}


def check(ac: str):
    def register(fn):
        CHECKS[ac] = fn
        return fn

    return register


ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# 造现场：英文草稿（flow 自带的只有中文草稿）
# --------------------------------------------------------------------------- #
def _seed_en_draft(gpa: str = "3.57/4.0") -> None:
    """插一条英文导入草稿（`GPA: 3.57/4.0`），让 `source_conflict.detect()` 有东西可比。"""
    _seed_draft(lang="en", gpa=gpa)


def _seed_zh_draft(gpa: str = "3.56/4") -> None:
    """插一条中文导入草稿（`GPA：3.56/4`）。

    `flow` 是 session 作用域：别的模块可能改掉/归档掉它那条中文导入草稿，
    于是 `detect()` 只剩英文一侧 → 「没检测到 GPA 冲突」。用例要自给自足，
    不能依赖前面没跑过谁。
    """
    _seed_draft(lang="zh", gpa=gpa)


def _seed_draft(*, lang: str, gpa: str) -> None:
    from app import db as db_mod

    conn = db_mod.get_conn()
    sha = hashlib.sha256(f"{lang}-draft-{gpa}".encode()).hexdigest()
    attachment_id = f"ac-{lang}-draft-{uuid.uuid4().hex[:8]}"
    now = db_mod.utcnow_iso()
    heading = "EDUCATION" if lang == "en" else "教育背景"
    fact = f"GPA: {gpa}" if lang == "en" else f"GPA：{gpa}"
    draft = {
        "lang": lang,
        "blocks": [
            {"temp_id": "tb-header", "block_type": "header", "heading": "ZHANG SAN", "preview_text": "ZHANG SAN"},
            {
                "temp_id": "tb-s1",
                "block_type": "section",
                "heading": heading,
                "preview_text": fact,
                "entry": {"facts": [fact], "bullets": []},
            },
        ],
    }
    with db_mod.transaction(conn):
        conn.execute(
            "INSERT INTO attachment (id, sha256, original_name, ext, mime, bytes, kind, privacy, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (attachment_id, sha, f"ac-{lang}-resume.txt", "txt", "text/plain", 128, "resume_source", "private", now),
        )
        conn.execute(
            "INSERT INTO import_job (id, attachment_id, status, parser, draft_json, stats_json, warnings_json,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                f"ac-{lang}-job-{uuid.uuid4().hex[:8]}",
                attachment_id,
                "committed",
                "txt",
                json.dumps(draft, ensure_ascii=False),
                "{}",
                "[]",
                now,
                now,
            ),
        )


def _drop_en_drafts() -> None:
    from app import db as db_mod

    conn = db_mod.get_conn()
    with db_mod.transaction(conn):
        rows = conn.execute(
            "SELECT attachment_id FROM import_job WHERE id LIKE 'ac-en-job-%' OR id LIKE 'ac-zh-job-%'"
        ).fetchall()
        conn.execute("DELETE FROM import_job WHERE id LIKE 'ac-en-job-%' OR id LIKE 'ac-zh-job-%'")
        for row in rows:
            conn.execute("DELETE FROM attachment WHERE id = ?", (row["attachment_id"],))


def _set_resolution(resolution: dict | None) -> None:
    from app.repos import ProfileRepo

    repo = ProfileRepo()
    profile = repo.get() or {}
    extra = dict(profile.get("extra") or {})
    if resolution is None:
        extra.pop("conflict_resolution", None)
    else:
        extra["conflict_resolution"] = resolution
    repo.upsert({"extra": extra})


RESOLVED_BY_USER = {
    "default": "zh",
    "fields": {"gpa": "zh"},
    "decided_at": "2026-10-23T09:30:00+08:00",
    "decided_by": "user",
}


ZH_GPA_LINE = "专业成绩：GPA 3.56/4 86.53/100 CET4：562 CET6：508"


def _ensure_zh_gpa(client) -> list[str]:
    """保证中文教育段里有 GPA 3.56/4（`flow` 是 session 作用域，别的用例可能改过它）。

    返回**原始** lines，调用方负责还原。冲突检测要的是「中文有 3.56/4、英文草稿有 3.57/4.0」，
    两侧都得现成，缺一侧就等于「没有冲突可测」。
    """
    original = list(client.get("/api/v1/profile/education-facts").get_json()["data"]["lines"])
    if any("3.56/4" in line for line in original):
        return original
    client.put("/api/v1/profile/education-facts", json={"lines": [*original, ZH_GPA_LINE]})
    return original


def _restore_lines(client, lines: list[str]) -> None:
    client.put("/api/v1/profile/education-facts", json={"lines": lines})


def _with_conflict(fn, client):
    """给需要「中英 GPA 冲突」的用例装上草稿，跑完拆掉并还原资料里的决议。"""
    from app.repos import ProfileRepo

    repo = ProfileRepo()
    original_extra = dict((repo.get() or {}).get("extra") or {})
    original_lines = _ensure_zh_gpa(client)
    _seed_zh_draft()
    _seed_en_draft()
    try:
        fn()
    finally:
        _drop_en_drafts()
        _restore_lines(client, original_lines)
        repo.upsert({"extra": original_extra})


# --------------------------------------------------------------------------- #
# 导出取文本
# --------------------------------------------------------------------------- #
def _wait_job(client, job_id: str, *, timeout_s: float = 120.0) -> dict:
    from .helpers import wait_job

    return wait_job(client, job_id, timeout_s=timeout_s)


def _pdf_text(flow: dict, job: dict) -> str:
    import pdfplumber

    artifacts = (job.get("result_json") or {}).get("artifacts") or []
    assert artifacts, job
    rel = artifacts[0]["rel_path"]
    path = Path(rel) if Path(rel).is_absolute() else Path(flow["data_dir"]) / rel
    with pdfplumber.open(path) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def _export_text(flow: dict, build_id: str) -> str:
    client = flow["client"]
    export = client.post(f"/api/v1/builds/{build_id}/export", json={"format": "pdf", "overwrite": True})
    assert export.status_code == 202, export.get_json()
    job = _wait_job(client, export.get_json()["data"]["job_id"])
    assert job["status"] == "succeeded", job
    return _pdf_text(flow, job)


# --------------------------------------------------------------------------- #
# AC-CONFLICT-02
# --------------------------------------------------------------------------- #
@check("AC-CONFLICT-02")
def test_ac_conflict_02_resolved_is_info_and_value_unchanged(flow):
    """已决议 → `info` + `resolved`/`decided_at` + `value_used` 就是中文原值，PDF 里也用这个值。"""
    from app.services import source_conflict

    def body():
        _set_resolution(RESOLVED_BY_USER)
        conflicts = source_conflict.detect()
        gpa = [item for item in conflicts if item["field"] == "gpa"]
        assert gpa, f"没检测到 GPA 冲突，实际：{[c['field'] for c in conflicts]}"

        warnings = source_conflict.warnings_for(conflicts, RESOLVED_BY_USER)
        warning = next(w for w in warnings if w["details"]["field"] == "gpa")
        assert warning["severity"] == "info", warning
        assert warning["details"]["resolved"] == "zh"
        assert warning["details"]["decided_at"] == "2026-10-23T09:30:00+08:00"
        assert warning["details"]["value_used"] == "3.56/4", warning
        assert "已按中文版为准" in warning["message"]

        client = flow["client"]
        export = client.post(f"/api/v1/builds/{flow['build_id']}/export", json={"format": "pdf", "overwrite": True})
        job = _wait_job(client, export.get_json()["data"]["job_id"])
        text = _pdf_text(flow, job)
        assert "3.56/4" in text, text[:400]
        assert "3.57" not in text, "英文草稿的 GPA 被渲染进了中文版"
        got = [w for w in (job.get("result_json") or {}).get("warnings") or [] if w.get("code") == "SOURCE_CONFLICT"]
        assert any(w["severity"] == "info" and w["details"].get("value_used") == "3.56/4" for w in got), got

    _with_conflict(body, flow["client"])


@check("AC-CONFLICT-02")
def test_ac_conflict_02_without_resolution_falls_back_to_warn(flow):
    """反向：把 `conflict_resolution` 从 `extra` 删掉 → 立刻回到 `warn`（不许写死降级）。"""
    from app.services import source_conflict

    def body():
        _set_resolution(None)
        warnings = source_conflict.warnings_for(source_conflict.detect(), None)
        assert warnings, "没有冲突可测（英文草稿没被读到）"
        for item in warnings:
            assert item["severity"] == "warn", item
            assert "resolved" not in item["details"], item

        client = flow["client"]
        export = client.post(f"/api/v1/builds/{flow['build_id']}/export", json={"format": "pdf", "overwrite": True})
        job = _wait_job(client, export.get_json()["data"]["job_id"])
        got = [w for w in (job.get("result_json") or {}).get("warnings") or [] if w.get("code") == "SOURCE_CONFLICT"]
        assert got and all(w["severity"] == "warn" for w in got), got

    _with_conflict(body, flow["client"])


@check("AC-CONFLICT-02")
def test_ac_conflict_02_non_user_decision_is_not_honoured(flow):
    """再反向：`decided_by != "user"`（自动流程自己写一条）**不得**降级。"""
    from app.services import source_conflict

    def body():
        conflicts = source_conflict.detect()
        assert conflicts
        for decided_by in ("auto", "system", "", None):
            resolution = dict(RESOLVED_BY_USER)
            if decided_by is None:
                resolution.pop("decided_by", None)
            else:
                resolution["decided_by"] = decided_by
            warnings = source_conflict.warnings_for(conflicts, resolution)
            assert warnings
            assert all(w["severity"] == "warn" for w in warnings), (decided_by, warnings)
            assert all("resolved" not in w["details"] for w in warnings), (decided_by, warnings)

    _with_conflict(body, flow["client"])


# --------------------------------------------------------------------------- #
# AC-PROF-01｜教育段补充行
# --------------------------------------------------------------------------- #
@check("AC-PROF-01")
def test_ac_prof_01_roundtrip_snapshot_and_clear(flow):
    from .helpers import db_one

    client = flow["client"]
    before = client.get("/api/v1/profile/education-facts").get_json()["data"]
    assert before["lines"], "默认模板教育段没有可读的补充行，现场不成立"

    new_lines = ["专业成绩：GPA 3.90/4 90.00/100 CET4：600 CET6:560", before["lines"][-1]]
    saved = client.put("/api/v1/profile/education-facts", json={"lines": new_lines}).get_json()["data"]
    assert saved["lines"] == new_lines
    assert saved["saved"] is True

    snapshot = saved["snapshot"]
    path = Path(snapshot["path"])
    assert path.exists(), snapshot
    assert hashlib.md5(path.read_bytes()).hexdigest() == snapshot["md5"]
    assert path.parent.name == "runtime"

    assert client.get("/api/v1/profile/education-facts").get_json()["data"]["lines"] == new_lines

    cleared = client.put("/api/v1/profile/education-facts", json={"lines": []}).get_json()["data"]
    assert cleared["lines"] == []
    row = db_one(flow, "SELECT static_text FROM template_block WHERE id = ?", (cleared["block_id"],))
    assert row["static_text"] is None

    client.put("/api/v1/profile/education-facts", json={"lines": before["lines"]})
    assert client.get("/api/v1/profile/education-facts").get_json()["data"]["lines"] == before["lines"]


@check("AC-PROF-01")
def test_ac_prof_01_too_many_lines_422_changes_nothing(flow):
    """13 行 → 422，并且**一条都不改**（校验必须早于落库与快照）。"""
    from .helpers import db_one

    client = flow["client"]
    before = client.get("/api/v1/profile/education-facts").get_json()["data"]
    original = db_one(flow, "SELECT static_text FROM template_block WHERE id = ?", (before["block_id"],))["static_text"]

    response = client.put("/api/v1/profile/education-facts", json={"lines": ["x"] * 13})
    assert response.status_code == 422, response.get_json()
    error = response.get_json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["fields"][0]["field"] == "lines"

    assert client.get("/api/v1/profile/education-facts").get_json()["data"]["lines"] == before["lines"]
    assert db_one(flow, "SELECT static_text FROM template_block WHERE id = ?", (before["block_id"],))["static_text"] == original


def _fresh_env(script: str) -> list[dict]:
    """在「仓库内临时 DATA_DIR + 独立子进程」里跑一段脚本，返回它 print 出来的 JSON 行。"""
    tmp = ROOT / "data" / "_tests" / f"ac-zhpref-{uuid.uuid4().hex[:8]}"
    tmp.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["DATA_DIR"] = str(tmp)
    env["PYTHONPATH"] = str(ROOT / "server")
    proc = subprocess.run(
        [sys.executable, "-c", script], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=180
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            out.append(json.loads(line))
    return out


@check("AC-PROF-01")
def test_ac_prof_01_without_default_template_is_409(flow):  # noqa: ARG001 —— 只需要一个已建的现场
    """没有默认模板 → 409 `NO_DEFAULT_TEMPLATE`（不是 500，也不是静默建一个）。"""
    script = """
import json
from app import create_app
app = create_app(); c = app.test_client()
c.put("/api/v1/profile", json={"name_zh": "张三"})
r = c.put("/api/v1/profile/education-facts", json={"lines": ["专业成绩：GPA 3.5/4"]})
print(json.dumps({"status": r.status_code, "body": r.get_json()}, ensure_ascii=False))
"""
    rows = _fresh_env(script)
    assert rows, "子进程没有输出"
    row = rows[0]
    assert row["status"] == 409, row
    assert row["body"]["error"]["code"] == "NO_DEFAULT_TEMPLATE", row


@check("AC-PROF-01")
def test_ac_prof_01_template_without_education_block_is_422(flow):  # noqa: ARG001
    """模板里没有教育段条目 → 422 `TEMPLATE_INVALID`，且**不自动建块**。"""
    script = """
import json
from app import create_app, db
from app.repos import TemplateRepo
app = create_app(); c = app.test_client()
c.put("/api/v1/profile", json={"name_zh": "张三"})
repo = TemplateRepo()
tid = repo.create({"name": "无教育段模板", "lang": "zh", "is_default": True})
repo.add_block(tid, {"block_type": "header", "order_index": 0})
r = c.put("/api/v1/profile/education-facts", json={"lines": ["专业成绩：GPA 3.5/4"]})
count = db.get_conn().execute("SELECT COUNT(*) AS n FROM template_block WHERE template_id = ?", (tid,)).fetchone()["n"]
print(json.dumps({"status": r.status_code, "body": r.get_json(), "blocks": count}, ensure_ascii=False))
"""
    rows = _fresh_env(script)
    assert rows, "子进程没有输出"
    row = rows[0]
    assert row["status"] == 422, row
    assert row["body"]["error"]["code"] == "TEMPLATE_INVALID", row
    assert row["blocks"] == 1, "接口偷偷给模板建了教育块"


# --------------------------------------------------------------------------- #
# AC-PROF-02｜到岗时间参与渲染，available_date 不参与
# --------------------------------------------------------------------------- #
@check("AC-PROF-02")
def test_ac_prof_02_available_note_reaches_both_languages(flow):
    """改 `available_note` → 中文版跟着变；英文版只在有 en 表述时显示，缺了就省略（不得印中文）。"""
    client = flow["client"]
    marker = "2027年3月中旬"

    client.put("/api/v1/profile", json={"available_note": marker, "extra": {"available_note_en": None}})
    zh_text = _export_text(flow, flow["build_id"])
    en_text = _export_text(flow, flow["build_id_en"])
    assert marker in zh_text, zh_text[:400]
    assert marker not in en_text, (
        "英文版缺 en 表述时不得回退中文（会把「2027年3月中旬」印进英文简历）；应省略该行并发 "
        "PROFILE_FIELD_MISSING{reason=avoid_chinese_in_english_export}"
    )

    client.put("/api/v1/profile", json={"available_note": marker, "extra": {"available_note_en": "mid-March 2027"}})
    en_text = _export_text(flow, flow["build_id_en"])
    assert "mid-March 2027" in en_text, en_text[:400]
    assert marker not in en_text, "英文版同时出现了中文值，说明两条字段在打架"

    client.put("/api/v1/profile", json={"available_note": "2027年1月下旬", "extra": {"available_note_en": None}})


@check("AC-PROF-02")
def test_ac_prof_02_available_date_does_not_render(flow):
    """`available_date` 是历史字段：写 `2028` 进去，两份 PDF 都不许出现。"""
    client = flow["client"]
    client.put("/api/v1/profile", json={"available_date": "2031-07"})
    try:
        for key in ("build_id", "build_id_en"):
            text = _export_text(flow, flow[key])
            assert "2031" not in text, f"{key} 的 PDF 里出现了 available_date 的值"
    finally:
        client.put("/api/v1/profile", json={"available_date": None})


@pytest.mark.parametrize("ac", sorted(CHECKS))
def test_ac_zhpref(ac, flow):
    CHECKS[ac](flow)
