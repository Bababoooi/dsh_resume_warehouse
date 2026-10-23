"""t6 收尾项的行为锁（captain m01927 §三）。

覆盖：
* `POST /templates/{id}/default` 显式设默认；没有显式默认时 `require_default` 抛
  409 `NO_DEFAULT_TEMPLATE` 并给 `candidates[]`（**绝不静默取最新**）。
* `auto_redact` 不再接受 `"school"`（校名按真实值发送）→ 422。
* `/variants/{id}` 保留可用但带 `Deprecation` 响应头（嵌套路由是推荐写法）。
* `OUTPUT_TRUNCATED` / `LLM_EMPTY_CONTENT` 必须带 `severity="warn"` 与
  `details{finish_reason, completion_tokens, max_tokens}`。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SERVER = Path(__file__).resolve().parent.parent
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from app import create_app  # noqa: E402
from app import db as db_mod  # noqa: E402
from app.adapters import llm_client  # noqa: E402
from app.errors import ApiError  # noqa: E402
from app.repos import PackageRepo, TemplateRepo  # noqa: E402


class FollowupBase(unittest.TestCase):
    def setUp(self) -> None:
        base = SERVER.parent / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self._tmp.cleanup)
        os.environ["DATA_DIR"] = self._tmp.name
        db_mod.reset_paths_for_tests()
        db_mod.get_paths().ensure()
        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        db_mod.close_conn()
        os.environ.pop("DATA_DIR", None)
        db_mod.reset_paths_for_tests()

    def make_template(self, name: str = "中文模板", *, lang: str = "zh", is_default: bool = False) -> dict:
        repo = TemplateRepo()
        template_id = repo.create(
            {
                "name": name,
                "lang": lang,
                "source_kind": "builtin",
                "page_limit": 1,
                "is_default": is_default,
                "layout": {},
            }
        )
        return repo.require(template_id)


class TemplateDefaultTest(FollowupBase):
    def test_explicit_default_endpoint_marks_resolved_false(self) -> None:
        first = self.make_template("第一份")
        second = self.make_template("第二份")
        self.assertTrue(first["is_default"], "第一条自动成为默认（规则 A）")

        response = self.client.post(f"/api/v1/templates/{second['id']}/default")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()["data"]
        self.assertTrue(data["is_default"])
        self.assertFalse(data["resolved"], "显式设置不是兜底")

        default_view = self.client.get("/api/v1/templates/default").get_json()["data"]
        self.assertEqual(default_view["id"], second["id"])
        self.assertFalse(default_view["resolved"])

    def test_no_default_template_raises_409_with_candidates(self) -> None:
        self.make_template("甲模板")
        self.make_template("乙模板")
        conn = db_mod.get_conn()
        conn.execute("UPDATE template SET is_default = 0")
        conn.commit()

        with self.assertRaises(ApiError) as ctx:
            TemplateRepo().require_default()
        error = ctx.exception
        self.assertEqual(error.code, "NO_DEFAULT_TEMPLATE")
        self.assertEqual(error.http_status, 409)
        candidates = error.details["candidates"]
        self.assertEqual(len(candidates), 2, "必须把候选给前端，不许静默挑一个")
        self.assertEqual({item["name"] for item in candidates}, {"甲模板", "乙模板"})
        self.assertIn("default", error.hint)

    def test_require_default_accepts_explicit_default(self) -> None:
        template = self.make_template("唯一模板")
        row = TemplateRepo().require_default(lang="zh")
        self.assertEqual(row["id"], template["id"])


class AutoRedactSettingTest(FollowupBase):
    def test_school_is_rejected(self) -> None:
        response = self.client.put("/api/v1/settings", json={"auto_redact": ["phone", "school"]})
        self.assertEqual(response.status_code, 422, response.get_data(as_text=True))
        error = response.get_json()["error"]
        self.assertEqual(error["code"], "VALIDATION_ERROR")
        self.assertIn("auto_redact", json.dumps(error["details"], ensure_ascii=False))

    def test_phone_email_id_name_are_accepted(self) -> None:
        response = self.client.put(
            "/api/v1/settings", json={"auto_redact": ["phone", "email", "id", "name"]}
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))


class VariantDeprecationTest(FollowupBase):
    def setUp(self) -> None:
        super().setUp()
        created = self.client.post(
            "/api/v1/packages",
            json={
                "title": "接口弃用验证",
                "kind": "project",
                "start_date": "2025-01",
                "end_date": "2025-02",
                "variants": [{"bullet_key": "b1", "tone": "impact", "lang": "zh", "text": "占位文本"}],
            },
        )
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        self.package = created.get_json()["data"]
        self.variant_id = self.package["variants"][0]["id"]

    def test_top_level_variant_routes_are_marked_deprecated(self) -> None:
        response = self.client.patch(f"/api/v1/variants/{self.variant_id}", json={"text": "改过的文本"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.headers.get("Deprecation"), "true")
        self.assertIn(f"/packages/{self.package['id']}/variants/{self.variant_id}", response.headers.get("Link", ""))

    def test_nested_route_is_not_deprecated(self) -> None:
        response = self.client.patch(
            f"/api/v1/packages/{self.package['id']}/variants/{self.variant_id}",
            json={"text": "嵌套路由改的文本"},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertNotIn("Deprecation", response.headers)


class _FakeResponse:
    """只实现 `_parse_response` 需要的三个面：status_code / headers / json()。"""

    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict:
        return self._payload


def _attachment_path(paths, row) -> str:
    from app.services.storage import Storage

    return str(Storage().attachment_path(row["sha256"], row["ext"], row["kind"]))


class BuildArtifactGuardTest(FollowupBase):
    """守卫必须同时覆盖「构建产物」这条引用（captain m02047 §三）。

    导出 PDF 之后，artifact 会把文件登记在 ``build_artifact.rel_path``；此时删同一份
    内容的附件必须同样 409，且 ``referenced_by`` 要指向「构建产物」而不是照片标签。
    这里不等 t8：直接造一条 artifact 行，证明拦截范围真的包含它。
    """

    def _photo_attachment(self) -> dict:
        payload = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
        response = self.client.post(
            "/api/v1/files",
            data={"kind": "photo", "file": (__import__("io").BytesIO(payload), "shot.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["data"]

    def test_artifact_reference_blocks_deletion_with_readable_label(self) -> None:
        attachment = self._photo_attachment()
        conn = db_mod.get_conn()
        now = db_mod.utcnow_iso()
        template = self.make_template("导出夹具模板")
        conn.execute(
            "INSERT INTO resume_build (id, name, template_id, lang, status, naming_pattern, created_at, updated_at)"
            " VALUES ('buildsmoke', '夹具构建', ?, 'zh', 'exported', '{position}-{name}-{school}', ?, ?)",
            (template["id"], now, now),
        )
        from app.repos import AttachmentRepo

        row = AttachmentRepo().get(attachment["id"])
        # 真实导出场景：artifact 落在 data/exports/ 下，文件名与附件不同，
        # 守卫必须靠**内容哈希**认出「这份文件就是那个附件」，不能只靠文件名。
        rel_path = "exports/t6-export-fixture.pdf"
        paths = db_mod.get_paths()
        export_file = paths.exports / "t6-export-fixture.pdf"
        export_file.write_bytes(open(_attachment_path(paths, row), "rb").read())
        conn.execute(
            "INSERT INTO build_artifact (id, build_id, format, engine, filename, rel_path, bytes, sha256, created_at)"
            " VALUES ('artsmoke', 'buildsmoke', 'pdf', 'reportlab', '导出.pdf', ?, ?, ?, ?)",
            (rel_path, row["bytes"], row["sha256"], now),
        )
        conn.commit()

        response = self.client.delete(f"/api/v1/files/{attachment['id']}")
        self.assertEqual(response.status_code, 409, response.get_data(as_text=True))
        error = response.get_json()["error"]
        self.assertEqual(error["code"], "FILE_IN_USE")
        labels = " ".join(error["details"]["referenced_by"])
        self.assertIn("构建产物", labels, f"必须指向构建产物，实际：{labels}")
        self.assertIn("t6-export-fixture.pdf", labels)
        self.assertNotIn("个人资料照片", labels, "这里没有把照片设成 profile 照片，不该出现该标签")


class TruncationWarningTest(unittest.TestCase):
    """LLM 警告必须是「结构化可判定」的，而不是只有一句人话。"""

    def _response(self, *, content: str, finish_reason: str, completion_tokens: int = 12) -> dict:
        return {
            "id": "cmpl-test",
            "model": "deepseek-chat",
            "choices": [
                {"index": 0, "finish_reason": finish_reason, "message": {"content": content}}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": completion_tokens, "total_tokens": 22},
        }

    def test_output_truncated_carries_severity_and_details(self) -> None:
        client = llm_client.LlmClient()
        payload = self._response(content='{"a": 1}', finish_reason="length")
        result = client._parse_response(
            _FakeResponse(payload),
            provider="deepseek",
            model="deepseek-chat",
            host="api.deepseek.com",
            latency_ms=10,
            purpose="bullets_generate",
            validator=None,
            attempt_no=1,
            max_tokens=512,
        )
        warning = next(w for w in result.warnings if w["code"] == "OUTPUT_TRUNCATED")
        self.assertEqual(warning["severity"], "warn")
        self.assertEqual(warning["details"]["finish_reason"], "length")
        self.assertEqual(warning["details"]["completion_tokens"], 12)
        self.assertEqual(warning["details"]["max_tokens"], 512)

    def test_empty_content_carries_severity_and_details(self) -> None:
        client = llm_client.LlmClient()
        payload = self._response(content="   ", finish_reason="stop", completion_tokens=0)
        result = client._parse_response(
            _FakeResponse(payload),
            provider="deepseek",
            model="deepseek-chat",
            host="api.deepseek.com",
            latency_ms=10,
            purpose="summary_polish",
            validator=None,
            attempt_no=1,
            max_tokens=800,
        )
        warning = next(w for w in result.warnings if w["code"] == "LLM_EMPTY_CONTENT")
        self.assertEqual(warning["severity"], "warn")
        self.assertEqual(warning["details"]["finish_reason"], "stop")
        self.assertEqual(warning["details"]["completion_tokens"], 0)
        self.assertEqual(warning["details"]["max_tokens"], 800)


if __name__ == "__main__":
    unittest.main()
