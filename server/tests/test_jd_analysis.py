"""t7 岗位需求分析：A/B 两例由 ``data/eval/jd_samples/expectations.json`` 驱动。

判据来源：

* ``docs/REVIEW-CHECKLIST.md`` ANL-01..08（尤其是 ANL-07 A 正例 7 条、ANL-08 B 反例 5 条）；
* ``docs/API-CONTRACT.md`` §6（analyze 202 + 428 前置、match 纯本地、requirements 人工修正）。

样张与期望文件都在 ``data/``（被 gitignore）；文件缺失时用例 **SKIP 而不是 fail**，
这样仓库在干净 clone 后仍可跑通其余测试。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

PROJECT = SERVER.parent
SAMPLES = PROJECT / "data" / "eval" / "jd_samples"

from app import create_app  # noqa: E402
from app import db as db_mod  # noqa: E402
from app.services import jd_analysis  # noqa: E402
from app.services import jobrun  # noqa: E402

TIERS = {"C9", "985", "211", "双一流", "普通本科", "海外", "其他"}
VERDICTS = {"strong", "medium", "weak"}
STATUSES = {"satisfied", "partial", "missing"}


def load_expectations() -> dict:
    path = SAMPLES / "expectations.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class JdBaseTest(unittest.TestCase):
    def setUp(self) -> None:
        base = PROJECT / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self._tmp.cleanup)
        os.environ["DATA_DIR"] = self._tmp.name
        db_mod.reset_paths_for_tests()
        db_mod.get_paths().ensure()
        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        # 后台任务（jobrun）还在写这个临时库 → 先等它收尾，否则临时目录被删，
        # 任务线程会拿着已删除的 SQLite 连接空转（实测表现为「任务超时未结束」且无异常）。
        jobrun.wait_idle()
        db_mod.close_conn()
        os.environ.pop("DATA_DIR", None)
        db_mod.reset_paths_for_tests()

    # -- helpers ---------------------------------------------------------
    def seed_profile(self, **overrides) -> dict:
        body = {
            "name_zh": "张三",
            "school_zh": "示例大学",
            "degree": "硕士",
            "major": "管理科学（商业数据分析）",
            "grad_year": 2028,
            "city": "武汉",
            "skills": [
                {"line": "数据分析类：Python、SQL、Excel、数据可视化", "category": "数据分析类"},
            ],
        }
        body.update(overrides)
        response = self.client.put("/api/v1/profile", json=body)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["data"]

    def create_jd(self, text: str, *, title: str = "数据分析实习生", company: str = "示例公司") -> dict:
        response = self.client.post(
            "/api/v1/jds", json={"title": title, "company_name": company, "raw_text": text}
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["data"]

    def run_analyze(self, jd_id: str, *, method: str = "heuristic") -> dict:
        response = self.client.post(f"/api/v1/jds/{jd_id}/analyze", json={"method": method})
        self.assertEqual(response.status_code, 202, response.get_data(as_text=True))
        job_id = response.get_json()["data"]["job_id"]
        for _ in range(100):
            job = self.client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
            if job["status"] in ("succeeded", "failed", "interrupted"):
                self.assertEqual(job["status"], "succeeded", job)
                return job
            time.sleep(0.05)
        self.fail("分析任务超时未结束")

    def analyze_heuristic(self, jd_id: str) -> dict:
        self.run_analyze(jd_id, method="heuristic")
        return self.client.get(f"/api/v1/jds/{jd_id}").get_json()["data"]

    def error(self, response) -> dict:
        payload = response.get_json()
        self.assertFalse(payload["ok"], payload)
        return payload["error"]


class SchoolTierTest(unittest.TestCase):
    """院校层次推断：只认内置小表，认不出必须回 None（不得降级成「普通本科」）。"""

    CASES = [
        ("示例大学", "985"),
        ("北京邮电大学", "211"),
        ("北京师范大学", "985"),
        ("中国人民大学", "985"),
        ("上海大学", "211"),
        ("南京信息工程大学", "211"),
        ("麻省理工学院", "海外"),
        ("MIT", "海外"),
        ("Stanford University", "海外"),
    ]

    def test_known_schools_map_to_expected_tier(self) -> None:
        for school, expected in self.CASES:
            with self.subTest(school=school):
                self.assertEqual(jd_analysis.tier_from_school_name(school), expected)

    def test_unknown_school_is_none_not_plain_undergrad(self) -> None:
        # 反面教训：旧实现「校名含『大学』→ 普通本科」会把双非院校误判成层次已知
        self.assertIsNone(jd_analysis.tier_from_school_name("XX大学"))
        self.assertIsNone(jd_analysis.tier_from_school_name("某某职业技术学院"))

    def test_unknown_tier_downgrades_to_other_with_warning(self) -> None:
        warnings: list[dict] = []
        result = jd_analysis.competitiveness(
            profile={"school_zh": "XX大学", "degree": "本科"},
            school_preference={"threshold": "不限", "hard_filter": False},
            requirements=[],
            warnings=warnings,
        )
        self.assertEqual(result["school_tier"], "其他")
        self.assertFalse(result["school_tier_recognized"])
        self.assertIn("SCHOOL_TIER_INFERRED", [w.get("code") for w in warnings])

    def test_manual_school_tier_wins_over_inference(self) -> None:
        warnings: list[dict] = []
        result = jd_analysis.competitiveness(
            profile={"school_zh": "XX大学", "school_tier": "211", "degree": "本科"},
            school_preference={"threshold": "不限", "hard_filter": False},
            requirements=[],
            warnings=warnings,
        )
        self.assertEqual(result["school_tier"], "211")
        self.assertTrue(result["school_tier_recognized"])


class SchoolGateTest(unittest.TestCase):
    """门槛表述六种：偏好（不卡）、明确不设、完全未提、偏好+不设、否定式、纯硬门槛。"""

    def gate(self, text: str) -> dict:
        return jd_analysis.detect_school_gate([jd_analysis.strip_notes(text)])

    def test_a_preference_is_not_a_gate(self) -> None:
        # D-39：真实 JD 写的是「985/211 院校优先」——这是偏好，不是硬门槛。
        # 判成门槛会让用户放弃本来能投的岗位（产品级错误，captain 实测过）。
        pref = self.gate("要求：2027 届及以后毕业，硕士及以上学历，985/211 院校优先。")
        self.assertFalse(pref["hard_filter"])
        self.assertTrue(pref["threshold"].startswith("不限"))
        self.assertIn("偏好", pref["threshold"])
        self.assertEqual(pref["preferred_tiers"], ["985", "211"])
        self.assertIn("优先", pref["evidence"])
        self.assertIn("985/211", pref["evidence"])

    def test_b_no_gate(self) -> None:
        pref = self.gate("要求：本科及以上学历，不设院校门槛。")
        self.assertFalse(pref["hard_filter"])
        self.assertEqual(pref["threshold"], "不限")

    def test_c_silent(self) -> None:
        pref = self.gate("要求：本科及以上学历，熟悉 Excel。")
        self.assertFalse(pref["hard_filter"])
        self.assertEqual(pref["threshold"], "不限")
        self.assertRegex(pref["evidence"], r"(未出现|未提|仅见)")

    def test_d_preference_without_hard_gate(self) -> None:
        pref = self.gate("985/211 优先，但不设院校门槛。")
        self.assertFalse(pref["hard_filter"])
        self.assertIn("不限", pref["threshold"])
        self.assertEqual(pref["preferred_tiers"], ["985", "211"])

    def test_e_negated_requirement(self) -> None:
        pref = self.gate("本岗位不要求 985 院校出身。")
        self.assertFalse(pref["hard_filter"])
        self.assertEqual(pref["threshold"], "不限")

    def test_f_hard_tier_only(self) -> None:
        pref = self.gate("仅限 985 院校应届生投递。")
        self.assertTrue(pref["hard_filter"])
        self.assertEqual(pref["threshold"], "985")

    def test_review_notes_are_ignored(self) -> None:
        # 样张里的 `> 用途：…` 评审注释会误伤门槛检测
        pref = self.gate("> 用途：验证 985 门槛\n要求：本科及以上学历，不设院校门槛。")
        self.assertFalse(pref["hard_filter"])


class SchoolGateMultiTierTest(unittest.TestCase):
    """斜杠/顿号/「或…均可」形态必须把层次收全，否则 211 会被判成不达标（captain 实测 P0）。"""

    def gate(self, text: str) -> dict:
        return jd_analysis.detect_school_gate(text)

    def test_slash_form_collects_all_tiers(self) -> None:
        pref = self.gate("仅限 985/211 院校")
        self.assertTrue(pref["hard_filter"])
        self.assertEqual(pref["preferred_tiers"], ["985", "211"])
        self.assertEqual(pref["threshold"], "985/211")

    def test_triple_slash_collects_three(self) -> None:
        pref = self.gate("仅限 985/211/双一流 院校")
        self.assertEqual(pref["preferred_tiers"], ["985", "211", "双一流"])

    def test_enumeration_and_or_forms(self) -> None:
        for text in ("985、211 院校均可", "985 或 211 均可", "985/211 任一"):
            with self.subTest(text=text):
                pref = self.gate(text)
                self.assertTrue(pref["hard_filter"], text)
                self.assertEqual(pref["preferred_tiers"], ["985", "211"], text)

    def test_evidence_quotes_full_clause(self) -> None:
        pref = self.gate("仅限 985/211 院校投递")
        self.assertIn("211", pref["evidence"], "证据不能只引被正则截断的「仅限 985」")


class SchoolGateSatisfactionTest(unittest.TestCase):
    """门槛判定用集合包含：211 硕士投「仅限 985/211」必须算达标。"""

    def compet(
        self,
        tier: str | None,
        gate_text: str,
        *,
        school: str = "示例大学",
    ) -> dict:
        warnings: list[dict] = []
        profile: dict = {"school_zh": school, "degree": "硕士"}
        if tier:
            profile["school_tier"] = tier
        return jd_analysis.competitiveness(
            profile=profile,
            school_preference=jd_analysis.detect_school_gate(gate_text),
            requirements=[],
            warnings=warnings,
        )

    def test_211_satisfies_985_or_211_gate(self) -> None:
        result = self.compet("211", "仅限 985/211 院校")
        self.assertEqual(result["gap_notes"], [], "211 满足门槛，不该有缺口说明")
        self.assertIn("满足", result["school_signal"])
        self.assertNotEqual(result["verdict"], "weak", "211 不该被 985/211 门槛判成弱")

    def test_985_satisfies_same_gate(self) -> None:
        result = self.compet("985", "仅限 985/211 院校")
        self.assertIn("满足", result["school_signal"])

    def test_out_of_set_tier_gets_human_gap_note(self) -> None:
        result = self.compet("其他", "仅限 985/211 院校")
        self.assertEqual(result["verdict"], "weak")
        self.assertTrue(result["gap_notes"], "门槛不满足时必须解释原因")
        self.assertIn("院校层次", result["gap_notes"][0])
        self.assertIn("985/211", result["gap_notes"][0])

    def test_unknown_tier_never_claims_low_tier(self) -> None:
        result = self.compet(None, "仅限 985/211 院校", school="XX大学")
        self.assertFalse(result["school_tier_recognized"])
        self.assertEqual(result["gap_notes"], [], "层次未知不得断言「偏低/不在门槛内」")
        self.assertIn("建议在个人资料里手填", result["school_signal"])
        self.assertNotEqual(result["verdict"], "weak")


class JdHeuristicTest(JdBaseTest):
    """ANL-01：LLM 不可用时启发式也产出 competitiveness + requirements。"""

    def test_heuristic_produces_competitiveness_even_without_llm(self) -> None:
        self.seed_profile()
        jd = self.create_jd("要求：本科及以上学历，985/211 院校优先。熟悉 SQL、Python 与 Excel。")
        jd = self.analyze_heuristic(jd["id"])
        self.assertEqual(jd["analysis_status"], "done")
        self.assertEqual(jd["analysis_method"], "heuristic")
        compet = jd["competitiveness"]
        self.assertIn(compet["school_tier"], TIERS)
        self.assertIn(compet["verdict"], VERDICTS)
        self.assertTrue(compet["school_signal"])
        self.assertGreaterEqual(len(compet["school_signal"]), 8)
        self.assertIsInstance(compet["gap_notes"], list)
        self.assertTrue(jd["requirements"], "启发式也得抽得出需求")
        for item in jd["requirements"]:
            self.assertIn(item["candidate_status"], STATUSES)
            self.assertEqual(item["source"], "heuristic")

    def test_analyze_requires_preview_on_llm_path(self) -> None:
        jd = self.create_jd("要求：本科及以上。")
        response = self.client.post(f"/api/v1/jds/{jd['id']}/analyze", json={"method": "llm"})
        self.assertEqual(response.status_code, 428)
        error = self.error(response)
        self.assertEqual(error["code"], "LLM_CONSENT_REQUIRED")
        self.assertEqual(error["details"]["purpose"], "jd_analyze")

    def test_match_is_local_and_returns_scores(self) -> None:
        self.seed_profile()
        jd = self.create_jd("要求：熟悉 SQL、Python。")
        self.analyze_heuristic(jd["id"])
        package = self.client.post(
            "/api/v1/packages",
            json={
                "title": "门店订单量预测",
                "kind": "project",
                "summary": "用 SQL 与 Python 做门店订单量预测。",
                "tech_stack": ["Python", "SQL"],
                "tags": ["数据分析"],
            },
        ).get_json()["data"]
        # 断网也能打分（match 是纯本地）
        from unittest import mock

        with mock.patch("httpx.Client.post", side_effect=AssertionError("match 不许联网")):
            response = self.client.post(f"/api/v1/jds/{jd['id']}/match", json={})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()["data"]
        self.assertGreaterEqual(len(data["scores"]), 1)
        self.assertEqual(data["scores"][0]["package_id"], package["id"])
        self.assertGreater(data["scores"][0]["score"], 0)
        self.assertIsInstance(data["scores"][0]["hits"], list)

    def test_manual_requirement_change_affects_match(self) -> None:
        self.seed_profile()
        jd = self.create_jd("要求：熟悉 SQL。")
        jd = self.analyze_heuristic(jd["id"])
        requirement = jd["requirements"][0]
        before = self.client.post(f"/api/v1/jds/{jd['id']}/match", json={}).get_json()["data"]
        patched = self.client.patch(
            f"/api/v1/requirements/{requirement['id']}", json={"priority": "nice", "weight": 0}
        )
        self.assertEqual(patched.status_code, 200, patched.get_data(as_text=True))
        self.assertEqual(patched.get_json()["data"]["source"], "manual")
        after = self.client.post(f"/api/v1/jds/{jd['id']}/match", json={}).get_json()["data"]
        self.assertEqual(after["requirements_used"], before["requirements_used"])
        deleted = self.client.delete(f"/api/v1/requirements/{requirement['id']}")
        self.assertEqual(deleted.status_code, 200)
        after_delete = self.client.post(f"/api/v1/jds/{jd['id']}/match", json={})
        if before["requirements_used"] > 1:
            data = after_delete.get_json()["data"]
            self.assertEqual(data["requirements_used"], before["requirements_used"] - 1)
        else:
            # 需求被删空后再打分没有依据 → 409（而不是返回 0 分假装正常）
            self.assertEqual(after_delete.status_code, 409)

    def test_match_without_requirements_is_409(self) -> None:
        jd = self.create_jd("要求：本科。")
        response = self.client.post(f"/api/v1/jds/{jd['id']}/match", json={})
        self.assertEqual(response.status_code, 409)


class JdSampleExpectationsTest(JdBaseTest):
    """ANL-07 / ANL-08：A 正例与 B 反例逐条按 ``assertions[]`` 断言。

    expectations.json 用「路径 + 操作符」描述判据（path 支持点号与 ``[]`` 数组展开），
    所以这里写一个很小求值器，而不是把 7+5 条判据硬编码进测试——文件驱动才是判据来源。
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.expectations = load_expectations()

    CASES = ("jd_school_preference", "jd_no_school", "jd_school_hard")

    def _sample(self, case: str) -> tuple[str, dict]:
        if not self.expectations:
            self.skipTest("data/eval/jd_samples/expectations.json 不存在")
        spec = self.expectations.get(case)
        if not isinstance(spec, dict) or "file" not in spec:
            self.skipTest(f"expectations.json 缺 {case}")
        path = SAMPLES / spec["file"]
        if not path.exists():
            self.skipTest(f"样张缺失：{path}")
        return path.read_text(encoding="utf-8"), spec

    # -- 断言求值器 ------------------------------------------------------
    @staticmethod
    def _resolve(document: dict, path: str) -> list:
        """按点号路径取值；``[]`` 表示展开数组（每个元素都要满足同一断言）。"""
        values: list = [document]
        for part in path.split("."):
            expand = part.endswith("[]")
            key = part[:-2] if expand else part
            nxt: list = []
            for value in values:
                if not isinstance(value, dict) or key not in value:
                    nxt.append(None)
                    continue
                item = value[key]
                if expand:
                    if isinstance(item, list):
                        nxt.extend(item)
                    else:
                        nxt.append(None)
                else:
                    nxt.append(item)
            values = nxt
        return values

    def _check(self, document: dict, assertion: dict) -> None:
        path, op = assertion["path"], assertion["op"]
        values = self._resolve(document, path)
        label = f"{path} ({op})"
        if op == "equals":
            for value in values:
                self.assertEqual(value, assertion["value"], label)
        elif op == "nonempty":
            for value in values:
                self.assertTrue(value, f"{label} 不能为空：{value!r}")
        elif op == "in":
            for value in values:
                self.assertIn(value, assertion["value"], label)
        elif op == "regex":
            for value in values:
                self.assertRegex(str(value), assertion["value"], label)
        elif op == "not_regex":
            for value in values:
                self.assertNotRegex(str(value), assertion["value"], label)
        elif op == "contains":
            for value in values:
                self.assertIn(str(assertion["value"]), str(value), label)
        elif op == "every_has_field":
            field = assertion["field"]
            allowed = assertion.get("value_in")
            self.assertTrue(values, f"{label} 没有可检查的元素")
            for value in values:
                self.assertIsInstance(value, dict, label)
                self.assertIn(field, value, f"{label} 缺字段 {field}")
                if allowed:
                    self.assertIn(value[field], allowed, label)
        else:  # pragma: no cover - 未知操作符必须显式失败，不能静默通过
            self.fail(f"expectations.json 里有未实现的操作符：{op}")

    def _analyze_case(self, case: str) -> tuple[dict, dict, str]:
        text, spec = self._sample(case)
        profile = self.seed_profile()
        jd = self.create_jd(text, title=spec.get("position", "数据分析实习生"), company=spec["company"])
        jd = self.analyze_heuristic(jd["id"])
        pref = jd_analysis.detect_school_gate([text])
        document = {
            "company_profile": {"school_preference": {"school_preference": pref, **pref}},
            "competitiveness": jd["competitiveness"],
            "requirements": jd["requirements"],
        }
        # 公司画像与 JD 分析共用同一套门槛判定；把两种嵌套写法都铺平，避免断言路径差异造成假红
        document["company_profile"]["school_preference"] = pref
        return document, spec, text, profile

    def _assert_case(self, case: str) -> None:
        document, spec, _text, _profile = self._analyze_case(case)
        self.assertTrue(spec["assertions"], "expectations 里没有任何断言")
        for assertion in spec["assertions"]:
            with self.subTest(case=case, path=assertion["path"]):
                self._check(document, assertion)

    def test_all_expectation_cases(self) -> None:
        """A 偏好 / B 无信号 / C 硬门槛：逐条按文件驱动断言。"""
        for case in self.CASES:
            with self.subTest(case=case):
                self._assert_case(case)

    def test_preference_is_not_a_gate(self) -> None:
        """D-39：偏好判成门槛会让用户放弃能投的岗位。"""
        pref = jd_analysis.detect_school_gate("985/211 院校优先，专业不限")
        self.assertFalse(pref["hard_filter"])
        self.assertEqual(pref["preferred_tiers"], ["985", "211"])
        self.assertTrue(pref["threshold"].startswith("不限"))
        self.assertIn("偏好", pref["threshold"])
        self.assertIn("优先", pref["evidence"])

    def test_hard_gate_stays_hard(self) -> None:
        pref = jd_analysis.detect_school_gate("仅限 985/211 院校在读硕士及以上")
        self.assertTrue(pref["hard_filter"])
        self.assertIn("985", pref["threshold"])
        self.assertIn("仅限", pref["evidence"])

    def test_same_sentence_preference_and_gate_differ(self) -> None:
        soft = jd_analysis.detect_school_gate("985/211 院校优先")
        hard = jd_analysis.detect_school_gate("仅限 985/211 院校")
        self.assertFalse(soft["hard_filter"])
        self.assertTrue(hard["hard_filter"])
        self.assertNotEqual(soft["threshold"], hard["threshold"])

    def test_str_and_list_are_identical(self) -> None:
        """脚枪：传裸 str 曾按字符迭代 → 静默返回「未提及」（骗过 captain 与 supervisor）。"""
        text = "要求：985/211 院校优先，本科及以上学历。"
        self.assertEqual(
            jd_analysis.detect_school_gate(text),
            jd_analysis.detect_school_gate([text]),
        )
        multi = ["第一段：不设院校门槛。", "第二段：985 优先。"]
        self.assertEqual(jd_analysis.detect_school_gate(multi), jd_analysis.detect_school_gate("\n".join(multi)))

    def test_no_school_words_never_invents_gate(self) -> None:
        pref = jd_analysis.detect_school_gate("要求：本科及以上学历，熟悉 Excel、SQL。")
        self.assertFalse(pref["hard_filter"])
        self.assertEqual(pref["preferred_tiers"], [])
        self.assertRegex(pref["evidence"], r"(未提|未出现|没有|不限|无.{0,2}院校|不设)")

    def test_case_b_payload_carries_real_school(self) -> None:
        """BLK-9 / X-F9：分析 payload 必须含真实校名，且不含姓名/电话/邮箱。"""
        _document, _spec, _text, profile = self._analyze_case("jd_no_school")
        preview = self.client.post(
            "/api/v1/llm/preview",
            json={"purpose": "jd_analyze"},
        )
        if preview.status_code == 503:
            self.skipTest("LLM 未配置，跳过 payload 断言")
        self.assertEqual(preview.status_code, 201, preview.get_data(as_text=True))
        payload = json.dumps(preview.get_json()["data"]["payload"], ensure_ascii=False)
        self.assertIn(profile["school_zh"], payload)
        self.assertNotIn(profile["name_zh"], payload)
        self.assertNotIn("[SCHOOL]", payload)


if __name__ == "__main__":
    unittest.main()


class HeuristicFallbackTest(JdBaseTest):
    """离线路径必须自证「这是规则算的」：不返回 null，且带降级警告（captain t7 收尾要求）。"""

    def seed_profile(self) -> None:  # noqa: D401 - 覆盖父类，附 school_tier
        self.client.put(
            "/api/v1/profile",
            json={
                "name_zh": "示例同学",
                "school_zh": "示例大学",
                "school_tier": "985",
                "degree": "硕士",
                "major": "管理科学（商业数据分析）",
                "grad_year": 2028,
            },
        )

    def test_heuristic_emits_fallback_warnings(self) -> None:
        jd = self.create_jd("仅限 985/211 院校，硕士及以上学历，熟悉 SQL 与 Python。", title="硬门槛")
        job = self.run_analyze(jd["id"], method="heuristic")
        payload = job["result_json"]
        self.assertEqual(payload["method"], "heuristic")
        self.assertIsNotNone(payload["competitiveness"], "启发式也必须产出 competitiveness")
        self.assertIsNotNone(payload["school_preference"], "启发式也必须产出 school_preference")
        codes = {item["code"] for item in payload["warnings"]}
        self.assertIn("COMPETITIVENESS_FALLBACK", codes)
        self.assertTrue(payload["school_preference"]["hard_filter"])
        self.assertEqual(payload["school_preference"]["preferred_tiers"], ["985", "211"])
        # 落库后读回来仍是同一份（前端刷新不丢字段）
        detail = self.client.get(f"/api/v1/jds/{jd['id']}").get_json()["data"]
        self.assertIsNotNone(detail.get("competitiveness"))

    def test_company_heuristic_emits_school_filter_fallback(self) -> None:
        self.seed_profile()
        response = self.client.post(
            "/api/v1/company-profiles/analyze",
            json={
                "company_name": "禾味食品集团",
                "method": "heuristic",
                "jd_text": "岗位：数据运营实习生。本科及以上学历，专业不限，熟悉 Excel。",
            },
        )
        self.assertEqual(response.status_code, 202, response.get_data(as_text=True))
        job_id = response.get_json()["data"]["job_id"]
        for _ in range(100):
            job = self.client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
            if job["status"] in ("succeeded", "failed", "interrupted"):
                break
            time.sleep(0.05)
        self.assertEqual(job["status"], "succeeded", job)
        codes = {item["code"] for item in job["result_json"]["warnings"]}
        self.assertIn("SCHOOL_FILTER_FALLBACK", codes)
        profile = job["result_json"]["profile"]
        pref = json.loads(profile["school_preference_json"]) if isinstance(
            profile.get("school_preference_json"), str
        ) else profile.get("school_preference")
        self.assertIsNotNone(pref, "公司画像必须带 school_preference")
        self.assertFalse(pref["hard_filter"], "JD 未提院校时不得编造门槛")


class JdSampleArtifactTest(unittest.TestCase):
    """D-24：``data/exports/jd_*.json`` 必须与当前夹具逐字对得上（产物旧于夹具 = 不可用）。"""

    EXPORTS = PROJECT / "data" / "exports"
    SAMPLES = PROJECT / "data" / "eval" / "jd_samples"

    def _artifact(self, name: str) -> dict:
        path = self.EXPORTS / name
        if not path.exists():
            self.skipTest(f"缺少产物 {path}（先跑 server/scripts/build_jd_samples.py）")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_exports_track_current_fixtures(self) -> None:
        cases = {
            "jd_a_school.json": "jd_school_preference.md",
            "jd_b_noschool.json": "jd_no_school.md",
            "jd_c_hard.json": "jd_school_hard.md",
        }
        for artifact_name, fixture_name in cases.items():
            fixture = self.SAMPLES / fixture_name
            if not fixture.exists():
                self.skipTest(f"缺少夹具 {fixture}")
            data = self._artifact(artifact_name)
            expected = hashlib.sha256(fixture.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            self.assertEqual(
                data["meta"]["source_sha256"], expected,
                f"{artifact_name} 的输入指纹与 {fixture_name} 不一致，请重跑 build_jd_samples.py",
            )
            self.assertEqual(data["meta"]["network"], "none", "样张产物必须是零出网生成的")
            self.assertEqual(data["meta"]["method"], "heuristic")

    def test_preference_artifact_is_not_a_gate(self) -> None:
        data = self._artifact("jd_a_school.json")
        pref = data["school_preference"]
        self.assertFalse(pref["hard_filter"], "「985/211 院校优先」不得判成硬门槛")
        self.assertEqual(pref["preferred_tiers"], ["985", "211"])
        self.assertTrue(pref["threshold"].startswith("不限"))
        self.assertIn("优先", pref["evidence"])

    def test_hard_artifact_stays_hard(self) -> None:
        data = self._artifact("jd_c_hard.json")
        pref = data["school_preference"]
        self.assertTrue(pref["hard_filter"])
        self.assertRegex(pref["threshold"], r"985|211")

    def test_no_school_artifact_does_not_invent_gate(self) -> None:
        data = self._artifact("jd_b_noschool.json")
        pref = data["school_preference"]
        self.assertFalse(pref["hard_filter"])
        self.assertEqual(pref["preferred_tiers"], [])
        self.assertRegex(pref["evidence"], r"(未提|未出现|没有|不限|无.{0,2}院校|不设)")


class EvidenceQuotingTest(unittest.TestCase):
    """F-09（captain m06463 ②）：证据必须能引回原文 ≥8 字，且不许把「没有」判成「有」。"""

    PROFILE = {
        "skills": [
            {"line": "数据分析类：掌握Python、R、SQL等编程语言，可独立进行数据清洗、统计分析与可视化处理"},
        ],
        "degree": "本科",
        "major": "管理科学（商业数据分析）",
    }

    PACKAGE = {
        "id": "pkg-ab",
        "title": "赛车类游戏版本AB测试对照数据分析",
        "org": "拓端数据科技",
        "role": "队长",
        "tech_stack": ["Python"],
        "variants": [
            {"lang": "zh", "text": "通过 A/B 测试对照分析，广告投放效率提升 39.3%。"},
            {"lang": "en", "text": "Ran A/B tests on ad placement and lifted efficiency by 39.3%."},
        ],
    }

    def test_skills_json_counts_as_evidence_with_quote(self):
        reqs = [{"skill": "SQL", "candidate_status": "missing", "raw_quote": None}]
        overridden = jd_analysis.link_requirements(reqs, [self.PACKAGE], profile=self.PROFILE)
        req = reqs[0]
        self.assertEqual(overridden, 1)
        self.assertEqual(req["candidate_status"], "partial")
        self.assertEqual(req["candidate_status_source"], "local_override")
        self.assertIn("SQL", req["evidence_hint"])
        self.assertGreaterEqual(len(req["evidence_hint"]), 8)
        self.assertEqual(req["matched_profile_evidence"], [self.PROFILE["skills"][0]["line"]])

    def test_all_variants_are_scanned_including_english(self):
        reqs = [{"skill": "A/B 测试", "candidate_status": "missing"}]
        jd_analysis.link_requirements(reqs, [self.PACKAGE], profile=self.PROFILE)
        self.assertEqual(reqs[0]["matched_package_ids"], ["pkg-ab"])
        hint = reqs[0]["evidence_hint"]
        self.assertGreaterEqual(len(hint), 8)
        self.assertIn("ab", jd_analysis._norm(hint), "引文必须真的含命中词（归一化后比对）")

    def test_missing_skill_stays_missing(self):
        """反向：用户确实没有的技能必须稳定保持 missing，不许为了好看改判。"""
        reqs = [{"skill": "区块链共识算法", "candidate_status": "missing"}]
        overridden = jd_analysis.link_requirements(reqs, [self.PACKAGE], profile=self.PROFILE)
        self.assertEqual(overridden, 0)
        self.assertEqual(reqs[0]["candidate_status"], "missing")
        self.assertEqual(reqs[0]["matched_package_ids"], [])
        self.assertFalse(reqs[0].get("evidence_hint"))

    def test_quote_must_be_at_least_eight_chars(self):
        """引不到 ≥8 字原文就不算命中（防止单字技能蒙对）。"""
        package = {"id": "pkg-tiny", "title": "R", "variants": [{"text": "R"}]}
        reqs = [{"skill": "R", "candidate_status": "missing"}]
        overridden = jd_analysis.link_requirements(reqs, [package], profile={"skills": []})
        self.assertEqual(overridden, 0)
        self.assertEqual(reqs[0]["candidate_status"], "missing")
