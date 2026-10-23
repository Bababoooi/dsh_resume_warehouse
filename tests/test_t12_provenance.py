"""t12 剩余两项的可验证证据。

1. **F-04**：``llm_call_log`` 必须记 ``purpose``，否则事后无法证明「分析档走
   ``LLM_MODEL_ANALYSIS``、对话档走 ``LLM_MODEL``」——preview 行一旦过期/清理，
   只剩 preview_id 就查不出这次调用属于哪条链路。
2. **F-03 幂等**：导入派生包的溯源写进 schema v8 的真列
   （``source_import_job_id`` / ``source_entry_temp_id``），不再靠 tags 承担幂等；
   同一份简历导两次不产生第二份包。
"""

from __future__ import annotations

TEXT = """张三
13800138000 | zhangsan@example.com
教育背景
2024.9-2028.6 示例大学 计算机科学与技术 本科
实习经历
示例科技 后端实习生 2026.07 - 2026.10
负责接口开发，QPS 提升 30%。
项目经历
数据看板 队长 2026.03 - 2026.04
搭建指标看板，覆盖 12 个业务域。
"""


def _import(client, filename: str, text: str = TEXT) -> str:
    resp = client.post("/api/v1/imports", json={"text": text, "filename": filename})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]["import_id"]


def _commit(client, import_id: str, name: str):
    resp = client.post(
        f"/api/v1/imports/{import_id}/commit",
        json={"template_name": name, "lang": "zh", "also_create_packages": True},
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]


def test_packages_carry_source_provenance_columns(app_env):
    """派生的每条包都要留下「来自哪个导入、哪条 entry」的真列，供撤销与去重使用。"""
    from app.repos import PackageRepo

    _app, client, _dir = app_env
    import_id = _import(client, "prov.txt")
    _commit(client, import_id, "溯源模板")

    packages = PackageRepo().list(limit=50, include_variants=False)["items"]
    imported = [item for item in packages if item.get("source") == "imported"]
    assert imported, "提交后应派生 package"
    for item in imported:
        assert item["source_import_job_id"] == import_id, item["title"]
        assert item["source_entry_temp_id"], item["title"]


def test_second_commit_does_not_duplicate_packages(app_env):
    """同一份简历再导一次（新 import_job）不能产出第二套包——幂等靠内容指纹兜底。"""
    _app, client, _dir = app_env
    first = _import(client, "dup-a.txt")
    first_result = _commit(client, first, "模板一")
    assert first_result["packages_created"], first_result

    second = _import(client, "dup-b.txt")  # 同名内容 → 内容寻址会复用同一份附件
    second_result = _commit(client, second, "模板二")
    assert second_result["packages_created"] == [], second_result
    assert second_result["packages_reused"], second_result


def test_llm_call_log_records_purpose(app_env, monkeypatch):
    """调用日志必须写 purpose（一次性读到 preview 的 purpose 即可，不必真发请求）。"""
    from app import db as db_mod
    from app.repos import JdRepo, LlmLogRepo
    from app.services import consent as consent_mod
    from app.adapters import llm_client

    _app, client, _dir = app_env
    jd = client.post(
        "/api/v1/jds",
        json={
            "title": "数据分析实习生",
            "company_name": "星链数科（杭州）有限公司",
            "raw_text": "岗位要求：985/211 院校优先，熟悉 SQL。",
        },
    ).get_json()["data"]
    preview = client.post(
        "/api/v1/llm/preview",
        json={"purpose": "jd_analyze", "selections": {"jd_id": jd["id"]}},
    )
    assert preview.status_code == 201, preview.get_data(as_text=True)
    preview_id = preview.get_json()["data"]["preview_id"]

    class FakeClient:
        def ensure_ready(self, *_a, **_k):
            return None

        def chat(self, payload, **kwargs):  # noqa: ANN001, ARG002
            return llm_client.LlmResult(
                ok=True,
                endpoint_host="api.deepseek.com",
                raw_text='{"requirements": [{"skill": "SQL"}]}',
                parsed={"requirements": [{"skill": "SQL"}]},
                usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                provider="deepseek",
                model="deepseek-reasoner",
                latency_ms=12,
                finish_reason="stop",
            )

    service = consent_mod.ConsentService(conn=db_mod.get_conn(), client=FakeClient())
    # sha 必须与预览时逐字一致（consent 会做一次性校验）
    service.complete(preview_id, preview.get_json()["data"]["payload_sha256"])

    rows = LlmLogRepo(db_mod.get_conn()).list(limit=5)
    assert rows, "调用后必须有日志行"
    assert rows[0]["purpose"] == "jd_analyze", rows[0]
