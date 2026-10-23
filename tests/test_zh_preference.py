"""用户拍板「以中文简历内的 GPA / 到岗时间为准」后的三处消费点。

对应三件事：

1. 个人资料页的「到岗时间」必须真的改得动：`available_note` 是真值，
   `extra.available_note_zh` 要跟着同步（否则 LLM 侧还读旧原文），
   英文版没写英文表述时回退中文值而不是留空。
2. `extra.conflict_resolution` 被真正消费：已决议字段的 `SOURCE_CONFLICT`
   降级为 `info` 并带 `resolved`，**未决议**字段保持 `warn`。
3. 教育段补充行（GPA / 主修课程）可读写：`/profile/education-facts`。

纯逻辑用例走 `noservice`（毫秒级）；碰库的走 `app_env` 临时目录，绝不碰真实 `data/app.db`。
"""

from __future__ import annotations

import hashlib
import json

import pytest


# --------------------------------------------------------------------------- #
# 1｜到岗时间：PUT 后 extra 同步、英文版回退中文值
# --------------------------------------------------------------------------- #
class AvailableNoteTest:
    """PUT /profile 改到岗时间 → 中文/英文两条渲染路径都跟着变。"""

    @pytest.fixture()
    def env(self, app_env):
        app, client, data_dir = app_env
        client.put(
            "/api/v1/profile",
            json={
                "name_zh": "张三",
                "school_zh": "示例大学",
                "available_note": "2027年1月下旬",
                "extra": {"available_note_en": "Early July 2026"},
            },
        )
        return app, client, data_dir

    def test_put_available_note_syncs_extra_zh(self, env):
        """界面只写 `available_note`，`extra.available_note_zh` 必须自动跟随。"""
        _, client, _ = env
        data = client.put("/api/v1/profile", json={"available_note": "2027年2月下旬"}).get_json()["data"]
        assert data["available_note"] == "2027年2月下旬"
        assert data["extra"]["available_note_zh"] == "2027年2月下旬"
        # 英文表述没被顺手覆盖（那是用户显式写下的另一条信息）
        assert data["extra"]["available_note_en"] == "Early July 2026"

    def test_clearing_available_note_removes_extra_zh(self, env):
        _, client, _ = env
        data = client.put("/api/v1/profile", json={"available_note": None}).get_json()["data"]
        assert data["available_note"] is None
        assert "available_note_zh" not in (data["extra"] or {})

    def test_en_header_falls_back_to_chinese_note(self, env):
        """英文版没写英文表述时，页眉第三行用中文真值——不能空着。"""
        from app.services import compose

        _, client, _ = env
        client.put("/api/v1/profile", json={"available_note": "2027年2月下旬", "extra": {"available_note_en": None}})
        profile = client.get("/api/v1/profile").get_json()["data"]
        ir = compose.build_ir(
            {"id": "b1", "lang": "en", "position": "Data Analyst Intern", "company": None},
            selections=[],
            packages={},
            variants_by_package={},
            blocks=[],
            profile=profile,
        )
        assert ir["header"]["available"] == "2027年2月下旬", ir["header"]

    def test_en_header_prefers_english_note_when_present(self, env):
        from app.services import compose

        _, client, _ = env
        client.put("/api/v1/profile", json={"available_note": "2027年2月下旬", "extra": {"available_note_en": "Late Feb 2027"}})
        profile = client.get("/api/v1/profile").get_json()["data"]
        ir = compose.build_ir(
            {"id": "b1", "lang": "en", "position": "Data Analyst Intern", "company": None},
            selections=[],
            packages={},
            variants_by_package={},
            blocks=[],
            profile=profile,
        )
        assert ir["header"]["available"] == "Late Feb 2027"


# --------------------------------------------------------------------------- #
# 2｜conflict_resolution：决议字段降级为 info，未决议仍是 warn
# --------------------------------------------------------------------------- #
CONFLICTS = [
    {"field": "gpa", "label": "GPA", "zh_value": "3.56/4", "en_value": "3.57/4.0"},
    {"field": "available", "label": "到岗时间", "zh_value": "2027年1月下旬", "en_value": "Early July 2026"},
]


def test_resolved_field_is_info_with_reason():
    from app.services import source_conflict

    resolution = {
        "default": "zh",
        "fields": {"gpa": "zh"},
        "decided_at": "2026-10-23T09:30:00+08:00",
        "decided_by": "user",
    }
    warnings = {w["details"]["field"]: w for w in source_conflict.warnings_for(CONFLICTS, resolution)}

    gpa = warnings["gpa"]
    assert gpa["severity"] == "info"
    assert gpa["details"]["resolved"] == "zh"
    assert gpa["details"]["decided_at"] == "2026-10-23T09:30:00+08:00"
    assert "已按中文版为准" in gpa["message"]
    assert gpa["details"]["value_used"] == "3.56/4"


def test_unresolved_field_stays_warn():
    """`default` 不是用来批量放过的：没逐字段决议的仍然 warn。"""
    from app.services import source_conflict

    resolution = {
        "default": "zh",
        "fields": {"gpa": "zh"},
        "decided_at": "2026-10-23T09:30:00+08:00",
        "decided_by": "user",
    }
    warnings = {w["details"]["field"]: w for w in source_conflict.warnings_for(CONFLICTS, resolution)}

    assert warnings["gpa"]["severity"] == "info"
    assert warnings["available"]["severity"] == "warn", warnings["available"]
    assert "resolved" not in warnings["available"]["details"]


def test_without_resolution_every_warning_stays_warn():
    """反向：把 `conflict_resolution` 删掉 → 回到 warn（这条防「降级写死」）。"""
    from app.services import source_conflict

    for item in source_conflict.warnings_for(CONFLICTS, None):
        assert item["severity"] == "warn", item
        assert "resolved" not in item["details"]


def test_export_pipeline_uses_resolution_from_extra(app_env):
    """导出这条链真的读了 `extra.conflict_resolution`，不是只有单测里能跑。"""
    app, client, _ = app_env
    client.put("/api/v1/profile", json={"name_zh": "张三", "school_zh": "示例大学"})
    from app import db as db_mod
    from app.repos import ProfileRepo

    ProfileRepo().upsert(
        {
            "extra": {
                "conflict_resolution": {
                    "default": "zh",
                    "fields": {"gpa": "zh"},
                    "decided_at": "2026-10-23T09:30:00+08:00",
                    "decided_by": "user",
                }
            }
        }
    )
    profile = ProfileRepo().get()
    assert profile["extra"]["conflict_resolution"]["fields"]["gpa"] == "zh"
    # 导出的 warning 构造函数接收的正是这份决议
    from app.services import source_conflict

    warnings = source_conflict.warnings_for(
        CONFLICTS, (profile.get("extra") or {}).get("conflict_resolution")
    )
    assert {w["severity"] for w in warnings} == {"info", "warn"}
    from app import config as config_mod

    assert db_mod.get_paths().db != config_mod.PROJECT_ROOT / "data" / "app.db"


# --------------------------------------------------------------------------- #
# 3｜教育段补充行（GPA / 主修课程）
# --------------------------------------------------------------------------- #
EDUCATION_LINES = [
    "专业成绩：GPA 3.56/4 86.53/100 CET4：562 CET6:508",
    "主修课程：统计学(92)、数据分析与处理（R）(91)",
]


@pytest.fixture()
def edu_env(app_env):
    """临时库里造一个默认模板 + 教育段 section/entry（含 static_text）。"""
    app, client, data_dir = app_env
    from app.repos import TemplateRepo

    repo = TemplateRepo()
    template_id = repo.create({"name": "中文-单页-审", "lang": "zh"})
    section_id = repo.add_block(
        template_id, {"block_type": "section", "heading": "教育背景", "bound_package_kind": "education", "order_index": 10}
    )
    repo.add_block(
        template_id,
        {
            "block_type": "entry",
            "parent_block_id": section_id,
            "order_index": 11,
            "bound_package_kind": "education",
            "static_text": "\n".join(EDUCATION_LINES),
        },
    )
    return app, client, data_dir


def test_education_facts_read(edu_env):
    _, client, _ = edu_env
    data = client.get("/api/v1/profile/education-facts").get_json()["data"]
    assert data["lines"] == EDUCATION_LINES
    assert data["template_name"] == "中文-单页-审"
    assert data["block_id"]


def test_education_facts_write_and_snapshot(edu_env):
    _, client, data_dir = edu_env
    new_lines = ["专业成绩：GPA 3.90/4 90.00/100 CET4：600 CET6:560", "主修课程：统计学(95)"]
    data = client.put("/api/v1/profile/education-facts", json={"lines": new_lines}).get_json()["data"]
    assert data["lines"] == new_lines

    snapshot = data["snapshot"]
    from pathlib import Path

    path = Path(snapshot["path"])
    assert path.exists(), snapshot
    assert hashlib.md5(path.read_bytes()).hexdigest() == snapshot["md5"]
    assert path.parent.name == "runtime"

    # 落库了，再读一次不是内存里的值
    again = client.get("/api/v1/profile/education-facts").get_json()["data"]
    assert again["lines"] == new_lines


def test_education_facts_clear_is_not_an_error(edu_env):
    _, client, _ = edu_env
    data = client.put("/api/v1/profile/education-facts", json={"lines": []}).get_json()["data"]
    assert data["lines"] == []

    from app import db as db_mod

    row = db_mod.get_conn().execute(
        "SELECT static_text FROM template_block WHERE id = ?", (data["block_id"],)
    ).fetchone()
    assert row["static_text"] is None


def test_education_facts_rejects_too_many_lines(edu_env):
    _, client, _ = edu_env
    response = client.put("/api/v1/profile/education-facts", json={"lines": ["x"] * 13})
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_education_facts_without_template_is_empty_not_500(app_env):
    _, client, _ = app_env
    response = client.get("/api/v1/profile/education-facts")
    assert response.status_code == 200
    assert response.get_json()["data"]["lines"] == []
    assert response.get_json()["data"]["template_id"] is None
