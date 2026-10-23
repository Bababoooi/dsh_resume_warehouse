"""T-1..T-6 的回归测试：t12 的 AC harness 真跑时抓出来的六处产品缺陷。

出处：`docs/API-CONTRACT.md` §17.8 的 T-1..T-6 行。这六条不是「顺手美化」，
是跑断言时真的 500 / 静默继续 / 违反 schema CHECK / 缺可执行提示 —— 所以每个
都得有一条「把旧代码放回去就会红」的用例，否则下次重构会悄悄把它们装回去。

| 编号 | 旧症状 | 本文件 |
|---|---|---|
| T-1 | `export_service.precheck_naming` 调不存在的 `BuildRepo().require()` → 导出预检 500 | `test_t1_precheck_naming_does_not_500` |
| T-2 | `assemble()` 在模板被软删时静默继续（猜最新模板） | `test_t2_assemble_refuses_when_template_gone` |
| T-3 | md 导出写 `engine='markdown'`，违反 `build_artifact.engine` 的 CHECK | `test_t3_md_export_uses_contract_engine` |
| T-4 | `naming.raise_on_errors` 的 422 没有 `hint`（AC-NAME-04 要求可执行提示） | `test_t4_naming_422_carries_actionable_hint` |
| T-5 | `provider=off` 时已确认的预览仍会发请求 | 既有 `test_ac_guards.py::AC-LLM-03`（含「零出网」断言） |
| T-6 | 405 被映射成 400 | `test_t6_method_not_allowed_is_405` |
"""

from __future__ import annotations

import pytest

from app.errors import ApiError


@pytest.fixture()
def site(app_env):
    """一个最小可用的现场：档案 + 一份 header 模板 + 一个绑定它的 build。"""
    from app.repos import BuildRepo, ProfileRepo, TemplateRepo

    _app, client, _data_dir = app_env
    ProfileRepo().upsert({"name_zh": "张三", "school_zh": "示例大学", "phone": "13800138000"})
    templates = TemplateRepo()
    template_id = templates.create({"name": "回归模板", "lang": "zh", "page_limit": 1, "is_default": True})
    block_id = templates.add_block(template_id, {"order_index": 0, "block_type": "header"})
    templates.add_slot(
        block_id,
        {
            "slot_key": "candidate.name",
            "slot_type": "text",
            "bound_field": "profile.name_zh",
            "required": True,
        },
    )
    build_id = BuildRepo().create(
        {"name": "回归构建", "template_id": template_id, "position": "后端实习生", "lang": "zh"}
    )
    return {"template_id": template_id, "build_id": build_id, "client": client}


def test_t1_precheck_naming_does_not_500(site):
    """T-1：预检必须真的算出文件名，而不是抛 `AttributeError: 'BuildRepo' object has no attribute 'require'`。"""
    from app.services import export_service

    result = export_service.precheck_naming(site["build_id"])
    assert result["filename"].endswith(".pdf")
    assert "张三" in result["filename"], result
    assert result["errors"] == [], result


def test_t2_assemble_refuses_when_template_gone(site):
    """T-2：模板没了必须 409 `NO_DEFAULT_TEMPLATE`，**不许**静默取一份最新模板继续组装。"""
    from app.repos import TemplateRepo
    from app.services import export_service

    assert TemplateRepo().delete(site["template_id"]) is True
    with pytest.raises(ApiError) as excinfo:
        export_service.assemble(site["build_id"])
    err = excinfo.value
    assert err.code == "NO_DEFAULT_TEMPLATE", err
    assert err.hint, "缺模板时必须告诉用户下一步（重新选模板），不能只丢错误码"
    assert err.details.get("template_id") == site["template_id"]


def test_t3_md_export_uses_contract_engine(site, app_env):
    """T-3：`build_artifact.engine` 只有 reportlab/chrome/docx/jinja2，md 必须落 `jinja2`。"""
    from app.services import export_service

    _app, _client, data_dir = app_env
    result = export_service.export(site["build_id"], fmt="md", verify_text=False)
    artifact = result["artifact"]
    assert artifact["format"] == "md"
    assert artifact["engine"] == "jinja2", "engine='markdown' 会违反 schema CHECK（T-3 的旧形态）"
    saved = (data_dir / artifact["rel_path"]).resolve()
    assert saved.exists(), artifact["rel_path"]
    assert saved.read_text(encoding="utf-8").strip(), "md 产物不许是空文件"


def test_t4_naming_422_carries_actionable_hint(site):
    """T-4：缺变量 / 未知变量必须 422 且带**可执行** hint —— 用户得知道去改哪里。"""
    from app.repos import ProfileRepo
    from app.services import export_service
    from app.services import naming as naming_mod

    ProfileRepo().upsert({"school_zh": None})  # 学校没填 → {school} 解析不出值
    with pytest.raises(ApiError) as excinfo:
        export_service.precheck_naming(site["build_id"], pattern="{position}-{name}-{school}")
    err = excinfo.value
    assert err.code == "NAMING_MISSING_VAR", err
    assert err.http_status == 422
    assert err.hint, "没有 hint 就等于告诉用户「自己猜」"
    assert "个人资料" in err.hint or "模板" in err.hint, err.hint
    assert err.details.get("field") == "school", err.details

    # 未知变量走另一条：hint 必须把可用变量列出来
    with pytest.raises(ApiError) as excinfo:
        naming_mod.raise_pattern_errors("{position}-{nmae}")
    unknown = excinfo.value
    assert unknown.code == "NAMING_UNKNOWN_VAR", unknown
    assert all("{" + name + "}" in unknown.hint for name in naming_mod.KNOWN_VARS[:3]), unknown.hint


def test_t6_method_not_allowed_is_405(site):
    """T-6：方法不对必须是 405 `METHOD_NOT_ALLOWED`，不是 400 `BAD_REQUEST`。"""
    resp = site["client"].put("/api/v1/health", json={})
    assert resp.status_code == 405, resp.get_json()
    body = resp.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "METHOD_NOT_ALLOWED", body["error"]
    assert body["error"]["details"]["http_status"] == 405
