"""t4 隐私与 LLM 前置校验的回归测试（不联网、不碰真实数据）。

跑法：cd resume-warehouse && python -m unittest discover -s server/tests -v
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SERVER = Path(__file__).resolve().parent.parent
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import httpx  # noqa: E402

from app import config as config_mod  # noqa: E402
from app import db as db_mod  # noqa: E402
from app.adapters import llm_client  # noqa: E402
from app.errors import ApiError  # noqa: E402
from app.repos import JdRepo, PackageRepo, ProfileRepo  # noqa: E402
from app.services import consent, privacy, prompts  # noqa: E402


def make_cfg(**overrides) -> config_mod.Config:
    values = {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "model_analysis": "deepseek-reasoner",
        "api_key": "sk-test-DEADBEEF",
        "timeout_seconds": 30,
        "max_retries": 2,
    }
    values.update(overrides)
    return config_mod.Config(**values)


class TempDatabase(unittest.TestCase):
    """每个用例一个独立数据目录（SQLite + 线程局部连接）。"""

    def setUp(self) -> None:
        # DATA_DIR 必须落在项目 data/ 内（ARCHITECTURE §5.3），所以用 data/_tests/<uuid>
        base = SERVER.parent / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self._tmp.cleanup)
        data_dir = Path(self._tmp.name)
        os.environ["DATA_DIR"] = str(data_dir)
        db_mod.reset_paths_for_tests()
        self.paths = db_mod.get_paths()
        self.paths.ensure()
        self.conn = db_mod.get_conn()
        db_mod.migrate(self.conn)

    def tearDown(self) -> None:
        db_mod.close_conn()
        os.environ.pop("DATA_DIR", None)
        db_mod.reset_paths_for_tests()


class RedactionBoundaryTest(TempDatabase):
    def setUp(self) -> None:
        super().setUp()
        ProfileRepo(self.conn).upsert(
            {
                "name_zh": "张三",
                "name_en": "San Zhang",
                "school_zh": "示例大学",
                "degree": "硕士",
                "major": "计算机技术",
                "grad_year": 2026,
                "phone": "17812340929",
                "email": "me@example.com",
            }
        )

    def test_llm_brief_has_school_but_never_name_or_contact(self) -> None:
        brief = ProfileRepo(self.conn).llm_brief()
        self.assertNotIn("name", brief)
        self.assertEqual(brief["school"], "示例大学")  # 用户 m00265：校名真实上云
        self.assertNotIn("phone", brief)
        self.assertNotIn("email", brief)
        self.assertNotIn("photo_path", brief)

    def test_name_redaction_is_forced_even_when_user_disables(self) -> None:
        service = consent.ConsentService(conn=self.conn, cfg=make_cfg(), client=mock.Mock())
        for auto_redact in (False, None, True):
            kinds = service._redact_kinds(auto_redact)
            self.assertIn("name", kinds, f"auto_redact={auto_redact} 时姓名必须仍脱敏")
            self.assertNotIn("school", kinds)
        # 关掉开关时手机号可不脱敏（用户自己的数据，由他决定），姓名不允许
        self.assertNotIn("phone", service._redact_kinds(False))
        self.assertIn("phone", service._redact_kinds(True))

    def test_dynamic_pattern_replaces_real_name_only(self) -> None:
        profile = ProfileRepo(self.conn).get()
        redactor = consent.Redactor(["name"], consent.build_dynamic_patterns(profile))
        text = "我在示例大学做项目，负责人是张三（San Zhang）。"
        cleaned = redactor.apply(text, path="messages[1].content")
        self.assertNotIn("张三", cleaned)
        self.assertNotIn("San Zhang", cleaned)
        self.assertIn("[NAME]", cleaned)

    def test_assert_blocks_name_phone_email_and_photo_hash(self) -> None:
        profile = ProfileRepo(self.conn).get()
        digest = "a" * 64
        for text in (
            "候选人张三",
            "电话 17812340929",
            "邮箱 me@example.com",
            f"photo {digest}",
        ):
            with self.assertRaises(ApiError) as ctx:
                privacy.assert_no_identity(text, profile, [digest])
            self.assertEqual(ctx.exception.code, "INTERNAL")
            self.assertEqual(ctx.exception.details.get("reason"), "IDENTITY_PRESENT_IN_PAYLOAD")

    def test_assert_allows_school_name(self) -> None:
        profile = ProfileRepo(self.conn).get()
        privacy.assert_no_identity("示例大学 2026 届硕士，计算机技术专业", profile, [])

    def test_preview_payload_excludes_name_keeps_jd_and_experience(self) -> None:
        package = PackageRepo(self.conn).create(
            {
                "title": "简历仓库系统",
                "kind": "project",
                "role": "后端",
                "summary": "本地简历打包与定制生成系统",
                "start_date": "2025-03",
                "end_date": "2025-09",
            }
        )
        PackageRepo(self.conn).add_variant(
            package,
            {
                "bullet_key": "b1",
                "tone": "impact",
                "lang": "zh",
                "text": "实现 SQLite 存储与 consent 预览链路，接口全部本地可用。",
                "verified": True,
            }
        )
        service = consent.ConsentService(conn=self.conn, cfg=make_cfg(), client=mock.Mock())
        preview = service.build_preview(
            {
                "purpose": "bullets_generate",
                "selections": {"package_ids": [package], "include_summary": True},
                "options": {},
            }
        )
        body = str(preview["payload"])
        self.assertNotIn("张三", body)
        self.assertNotIn("17812340929", body)
        self.assertNotIn("me@example.com", body)
        self.assertIn("示例大学", body)          # 校名照常发送
        self.assertIn("实现 SQLite 存储", body)   # 正向防伪：经历文本真的在
        # 无真名出现时 redactions 为空是正常的（清单仍如实给出结构排除项）
        self.assertIsInstance(preview["redactions"], list)
        self.assertIn("profile.phone", preview["excluded"]["structural_exclusions"])

    def test_payload_carries_real_school_and_no_school_placeholder(self) -> None:
        """校名真实发送：payload 里出现「示例大学」，且绝无 [SCHOOL] 占位符。"""
        package = PackageRepo(self.conn).create(
            {
                "title": "简历仓库系统",
                "kind": "project",
                "role": "后端",
                "start_date": "2025-03",
                "end_date": "2025-09",
            }
        )
        PackageRepo(self.conn).add_variant(
            package,
            {
                "bullet_key": "b1",
                "tone": "impact",
                "lang": "zh",
                "text": "实现本地 SQLite 存储与一键导出。",
                "verified": True,
            },
        )
        service = consent.ConsentService(conn=self.conn, cfg=make_cfg(), client=mock.Mock())
        preview = service.build_preview(
            {
                "purpose": "bullets_generate",
                "selections": {"package_ids": [package], "include_summary": True},
                "options": {},
            }
        )
        payload_json = consent.canonical_payload_bytes(preview["payload"]).decode("utf-8")
        self.assertIn("示例大学", payload_json)
        self.assertEqual(payload_json.count("[SCHOOL]"), 0)

    def test_consent_copy_never_claims_school_is_redacted(self) -> None:
        """文案与行为同一件事：任何提到「学校」的行都必须是「真实发送」的说法。"""
        source = (SERVER / "app" / "services" / "consent.py").read_text(encoding="utf-8")
        offenders = []
        for line_no, line in enumerate(source.splitlines(), start=1):
            if "学校" not in line:
                continue
            if "占位符" in line or "[SCHOOL]" in line:
                offenders.append(f"consent.py:{line_no} {line.strip()}")
            elif "脱敏" in line and "真实" not in line:
                offenders.append(f"consent.py:{line_no} {line.strip()}")
        self.assertEqual(offenders, [], "文案仍在说学校名被脱敏/占位化")

    def test_consent_note_mentions_phone_email_default_redaction(self) -> None:
        """用户可感知的告知：电话/邮箱是「默认脱敏、可关闭」，不是含糊的永不发送。"""
        source = (SERVER / "app" / "services" / "consent.py").read_text(encoding="utf-8")
        self.assertIn("电话、邮箱默认脱敏", source)
        self.assertIn("可在设置里关闭脱敏", source)


class JsonPreconditionTest(TempDatabase):
    def test_json_mode_without_literal_json_fails_locally_with_zero_egress(self) -> None:
        client = llm_client.LlmClient(make_cfg())
        calls = {"post": 0}

        def fake_post(*args, **kwargs):
            calls["post"] += 1
            raise AssertionError("不应发起任何 HTTP 请求")

        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "把你的回答放在 JSON 里"}],
            "response_format": {"type": "json_object"},
        }
        payload["messages"] = [{"role": "user", "content": "只回一句中文总结"}]
        with mock.patch.object(httpx.Client, "post", side_effect=fake_post):
            with self.assertRaises(ApiError) as ctx:
                client.chat(payload, purpose="bullets_generate")
        self.assertEqual(ctx.exception.code, "LLM_JSON_MODE_PRECONDITION")
        self.assertEqual(ctx.exception.details.get("reason"), "PROMPT_MISSING_JSON_LITERAL")
        self.assertEqual(calls["post"], 0)
        from app.errors import ERROR_STATUS
        self.assertEqual(ERROR_STATUS["LLM_JSON_MODE_PRECONDITION"], 422)


class TruncationTest(TempDatabase):
    def test_empty_content_with_finish_length_is_truncated_error(self) -> None:
        client = llm_client.LlmClient(make_cfg())
        request = httpx.Request("POST", "https://api.deepseek.com/v1/chat/completions")
        response = httpx.Response(
            200,
            request=request,
            json={
                "choices": [{"message": {"content": "", "reasoning_content": "想了很多"}, "finish_reason": "length"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 16, "total_tokens": 26,
                          "completion_tokens_details": {"reasoning_tokens": 16}},
            },
        )
        with self.assertRaises(ApiError) as ctx:
            client._parse_response(  # noqa: SLF001 - 直接测解析分支
                response,
                provider="deepseek",
                model="deepseek-reasoner",
                host="api.deepseek.com",
                latency_ms=10,
                purpose="jd_analyze",
                validator=None,
                attempt_no=1,
                max_tokens=16,
            )
        self.assertEqual(ctx.exception.code, "LLM_TRUNCATED")
        self.assertEqual(ctx.exception.details.get("reason"), "empty_content")
        self.assertEqual(ctx.exception.details.get("reasoning_tokens"), 16)


if __name__ == "__main__":
    unittest.main()


class SchoolSignalTest(TempDatabase):
    """校名要「发出去且真的被用到」（用户 2026-10-23 强调：校名是竞争力核心依据）。"""

    def setUp(self) -> None:
        super().setUp()
        ProfileRepo(self.conn).upsert(
            {
                "name_zh": "张三",
                "name_en": "San Zhang",
                "school_zh": "示例大学",
                "degree": "本科",
                "major": "管理科学（商业数据分析）",
                "grad_year": 2028,
                "phone": "13800138000",
                "email": "me@example.com",
                "city": "武汉",
            }
        )
        self.jd = JdRepo(self.conn).create(
            {
                "title": "数据分析实习生",
                "company_name": "某互联网公司",
                "raw_text": "要求：熟悉 SQL、Python，具备统计分析能力；985/211 优先。",
            }
        )

    def _preview(self, purpose: str) -> dict:
        service = consent.ConsentService(conn=self.conn, cfg=make_cfg(), client=mock.Mock())
        return service.build_preview(
            {"purpose": purpose, "selections": {"jd_id": self.jd}, "options": {}}
        )

    def test_jd_analyze_payload_carries_profile_with_real_school(self) -> None:
        preview = self._preview("jd_analyze")
        body = consent.canonical_payload_bytes(preview["payload"]).decode("utf-8")
        self.assertIn("候选人档案", body)
        self.assertIn("示例大学", body)
        self.assertNotIn("张三", body)
        self.assertNotIn("13800138000", body)
        self.assertNotIn("me@example.com", body)
        # 清单里如实登记了档案段（fields 有 kind=profile）
        self.assertTrue(any(item["kind"] == "profile" for item in preview["fields"]))
        # 允许来源契约里承认 profile
        self.assertIn("profile", prompts.ALLOWED_SOURCES["jd_analyze"])

    def test_all_analysis_purposes_allow_profile_source(self) -> None:
        for purpose in ("jd_analyze", "company_profile", "build_suggest"):
            self.assertIn("profile", prompts.ALLOWED_SOURCES[purpose], purpose)

    def test_prompts_actually_use_school_signal(self) -> None:
        """不许「发了但不用」：三个分析 purpose 的 schema 必须带院校维度。"""
        source = (SERVER / "app" / "services" / "prompts.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("院校"), 3)
        self.assertIn("school_tier", source)
        self.assertIn("school_signal", source)
        self.assertIn("school_preference", source)
        self.assertIn("school_signal_used", source)
        self.assertIn("competitiveness", source)
