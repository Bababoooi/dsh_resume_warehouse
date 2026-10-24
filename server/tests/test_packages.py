"""t6 经历包（Package）：PKG-01..07 + 对话式打包 + 变体生成的 consent 前置。

判据来源：docs/REVIEW-CHECKLIST.md §1.3（PKG-01..07）。
所有用例都对着真 SQLite（``data/_tests/<tmp>/app.db``）与 Flask test client 跑，
FTS 用 ``select count(*) from package_fts`` 反证「不是 LIKE 冒充」。
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

from llm_key import LLM_KEY_READY, LLM_KEY_REASON
from pathlib import Path
from unittest import mock

SERVER = Path(__file__).resolve().parent.parent
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from app import create_app  # noqa: E402
from app import db as db_mod  # noqa: E402
from app.services import packager  # noqa: E402

BASE_PACKAGE = {
    "title": "小象超市门店选址与订单量预测建模",
    "kind": "project",
    "org": "全国大学生商业分析大赛",
    "role": "队长",
    "start_date": "2026-03",
    "end_date": "2026-04",
    "summary": "用 6527 条门店订单做选址与销量预测，方案获赛区一等奖。",
    "tech_stack": ["Python", "SQL", "LightGBM"],
    "tags": ["数据分析", "建模"],
}

THREE_TONES = [
    {
        "bullet_key": "b1",
        "tone": "impact",
        "lang": "zh",
        "text": "把 6527 条门店订单接入预测流程，试点门店备货周转提升 39.3%。",
        "verified": True,
    },
    {
        "bullet_key": "b1",
        "tone": "technical",
        "lang": "zh",
        "text": "用 LightGBM 做订单量回归，特征 1220 维，离线 MAPE 降到 8.1%。",
    },
    {
        "bullet_key": "b1",
        "tone": "ats",
        "lang": "zh",
        "text": "订单量预测 / 门店选址 / Python / SQL / LightGBM / 数据建模",
    },
]


class PackageBaseTest(unittest.TestCase):
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

    # -- helpers ---------------------------------------------------------
    def create(self, **overrides) -> dict:
        body = dict(BASE_PACKAGE)
        body.update(overrides)
        response = self.client.post("/api/v1/packages", json=body)
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        self.assertTrue(response.headers.get("Location", "").startswith("/api/v1/packages/"))
        return response.get_json()["data"]

    def error(self, response) -> dict:
        payload = response.get_json()
        self.assertFalse(payload["ok"], payload)
        return payload["error"]

    def count(self, sql: str, params: tuple = ()) -> int:
        row = db_mod.get_conn().execute(sql, params).fetchone()
        return int(row[0] or 0)


class PackageCrudTest(PackageBaseTest):
    """PKG-01 / PKG-06 / PKG-07：CRUD、软删恢复、校验、归档。"""

    def test_pkg01_create_201_with_variants_and_location(self) -> None:
        package = self.create(variants=THREE_TONES)
        self.assertEqual(package["title"], BASE_PACKAGE["title"])
        self.assertEqual({v["tone"] for v in package["variants"]}, {"impact", "technical", "ats"})
        # 默认详情不带 variants，?include=variants 才带
        detail = self.client.get(f"/api/v1/packages/{package['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("variants", detail.get_json()["data"])
        with_variants = self.client.get(f"/api/v1/packages/{package['id']}?include=variants")
        self.assertEqual(len(with_variants.get_json()["data"]["variants"]), 3)

    def test_pkg01_delete_is_soft_and_restore_brings_it_back(self) -> None:
        package = self.create()
        deleted = self.client.delete(f"/api/v1/packages/{package['id']}")
        self.assertEqual(deleted.status_code, 204)
        listing = self.client.get("/api/v1/packages").get_json()["data"]
        self.assertNotIn(package["id"], [item["id"] for item in listing["items"]])
        self.assertEqual(self.client.get(f"/api/v1/packages/{package['id']}").status_code, 404)
        restored = self.client.post(f"/api/v1/packages/{package['id']}/restore")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.get_json()["data"]["id"], package["id"])
        listing = self.client.get("/api/v1/packages").get_json()["data"]
        self.assertIn(package["id"], [item["id"] for item in listing["items"]])

    def test_pkg06_is_current_with_end_date_is_422(self) -> None:
        response = self.client.post(
            "/api/v1/packages",
            json={"title": "x", "kind": "project", "is_current": True, "end_date": "2025-09"},
        )
        self.assertEqual(response.status_code, 422)
        error = self.error(response)
        self.assertEqual(error["code"], "VALIDATION_ERROR")
        field = error["details"]["fields"][0]
        self.assertIn("is_current", f"{field['field']} {field['message']} {field['rule']}")

    def test_pkg07_archived_hides_from_default_list(self) -> None:
        package = self.create()
        patched = self.client.patch(f"/api/v1/packages/{package['id']}", json={"status": "archived"})
        self.assertEqual(patched.status_code, 200)
        listing = self.client.get("/api/v1/packages").get_json()["data"]
        self.assertNotIn(package["id"], [item["id"] for item in listing["items"]])
        archived = self.client.get(f"/api/v1/packages?status=archived").get_json()["data"]
        self.assertIn(package["id"], [item["id"] for item in archived["items"]])
        # 归档不等于删除：按 id 仍可取到
        self.assertEqual(self.client.get(f"/api/v1/packages/{package['id']}").status_code, 200)

    def test_stats_counts_packages_variants_unverified(self) -> None:
        package = self.create(variants=THREE_TONES)
        stats = self.client.get("/api/v1/packages/stats").get_json()["data"]
        self.assertEqual(stats["packages"], 1)
        self.assertEqual(stats["variants"], 3)
        # b1 只有 impact 那条 verified → 其余 bullet_key 之外的待核实不计；
        # 这里三个 tone 同属 b1，只要有一条 verified，b1 就不算待核实
        self.assertEqual(stats["unverified"], 0)
        self.client.post(
            f"/api/v1/packages/{package['id']}/variants",
            json={"bullet_key": "b2", "tone": "impact", "lang": "zh", "text": "另一条未核实的事实"},
        )
        self.assertEqual(self.client.get("/api/v1/packages/stats").get_json()["data"]["unverified"], 1)

    def test_duplicate_creates_draft_with_unverified_variants(self) -> None:
        package = self.create(variants=THREE_TONES)
        response = self.client.post(f"/api/v1/packages/{package['id']}/duplicate")
        self.assertEqual(response.status_code, 201)
        copy = response.get_json()["data"]
        self.assertNotEqual(copy["id"], package["id"])
        self.assertEqual(copy["status"], "draft")
        self.assertTrue(copy["title"].endswith("（副本）"))
        self.assertFalse(any(variant["verified"] for variant in copy["variants"]))


class PackageTimelineTest(PackageBaseTest):
    """时间线保真（P0 回归）：repos._encode 的 bool→int 三目曾把 False 写成 1。

    症状：``POST /packages`` 不传 ``is_current`` 时，``end_date`` 被抹成 NULL、
    整条经历变成「至今在职」。真库 18 行全部命中。这里全部走**写进去再读出来**的
    往返断言（HTTP + SQL 双向回读），不用 mock——mock 恰恰会漏掉这种转换错误。
    """

    def test_end_date_survives_roundtrip_when_is_current_absent(self) -> None:
        package = self.create(start_date="2023-07", end_date="2024-06")
        self.assertEqual(package["end_date"], "2024-06", "结束时间不许被静默丢弃")
        self.assertFalse(package["is_current"])

        detail = self.client.get(f"/api/v1/packages/{package['id']}").get_json()["data"]
        self.assertEqual(detail["end_date"], "2024-06")
        self.assertFalse(detail["is_current"])

        row = db_mod.get_conn().execute(
            "SELECT start_date, end_date, is_current FROM package WHERE id = ?",
            (package["id"],),
        ).fetchone()
        self.assertEqual(row["end_date"], "2024-06", "DB 原始行也必须保留结束时间")
        self.assertEqual(int(row["is_current"]), 0, "is_current 必须是整数 0，不是 1")

    def test_explicit_false_is_current_also_keeps_end_date(self) -> None:
        package = self.create(start_date="2023-07", end_date="2024-06", is_current=False)
        self.assertEqual(package["end_date"], "2024-06")
        self.assertFalse(package["is_current"])

    def test_is_current_true_with_end_date_is_rejected_and_model_guard_stays(self) -> None:
        # models.py 的这条校验是唯一挡住该 bug 扩散的闸门，不许为了「写入更宽松」删掉它
        response = self.client.post(
            "/api/v1/packages",
            json={"title": "x", "kind": "project", "is_current": True, "end_date": "2025-09"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.error(response)["code"], "VALIDATION_ERROR")

    def test_patch_end_date_only_keeps_is_current_false(self) -> None:
        package = self.create(start_date="2023-07", end_date="2024-06")
        patched = self.client.patch(
            f"/api/v1/packages/{package['id']}", json={"end_date": "2024-08"}
        )
        self.assertEqual(patched.status_code, 200, patched.get_data(as_text=True))
        data = patched.get_json()["data"]
        self.assertEqual(data["end_date"], "2024-08")
        self.assertFalse(data["is_current"], "只改结束时间不许把行变成「至今」")

    def test_explicit_is_current_true_clears_end_date(self) -> None:
        package = self.create(start_date="2023-07", end_date="2024-06")
        patched = self.client.patch(
            f"/api/v1/packages/{package['id']}", json={"is_current": True}
        )
        self.assertEqual(patched.status_code, 200, patched.get_data(as_text=True))
        data = patched.get_json()["data"]
        self.assertTrue(data["is_current"])
        self.assertIsNone(data["end_date"], "显式「至今在职」清空结束时间是合法语义")

    def test_no_repo_uses_the_broken_bool_ternary(self) -> None:
        """静态防回归：`1 if isinstance(value, bool) ...` 这种写法全仓一处都不许留。"""
        offenders = []
        for path in sorted((SERVER / "app").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "1 if isinstance(value, bool)" in line:
                    offenders.append(f"{path.relative_to(SERVER)}:{lineno}")
        self.assertEqual(offenders, [], f"bool→int 三目写法又有残留：{offenders}")


class PackageReadyGateTest(PackageBaseTest):
    """PKG-02：ready 必须至少一条 verified 变体（I1）。"""

    def test_pkg02_ready_without_verified_is_409_then_ok(self) -> None:
        package = self.create()
        response = self.client.patch(f"/api/v1/packages/{package['id']}", json={"status": "ready"})
        self.assertEqual(response.status_code, 409)
        error = self.error(response)
        self.assertEqual(error["code"], "CONFLICT")
        self.assertEqual(error["details"]["reason"], "PACKAGE_NEEDS_VERIFIED_VARIANT")
        self.assertIn("unverified", error["details"])

        variant = self.client.post(
            f"/api/v1/packages/{package['id']}/variants",
            json={"bullet_key": "b1", "tone": "impact", "lang": "zh", "text": "真实发生的事实", "verified": True},
        ).get_json()["data"]
        self.assertTrue(variant["verified"])
        again = self.client.patch(f"/api/v1/packages/{package['id']}", json={"status": "ready"})
        self.assertEqual(again.status_code, 200, again.get_data(as_text=True))
        self.assertEqual(again.get_json()["data"]["status"], "ready")


class PackageVariantTest(PackageBaseTest):
    """PKG-03：三 tone 共存 + UNIQUE(package_id,bullet_key,tone,lang) → 409。"""

    def test_pkg03_three_tones_coexist(self) -> None:
        package = self.create(variants=THREE_TONES)
        data = self.client.get(f"/api/v1/packages/{package['id']}/variants").get_json()["data"]
        tones = {item["tone"] for item in data["items"]}
        self.assertTrue({"impact", "technical", "ats"} <= tones, tones)
        self.assertEqual(data["bullet_keys"], ["b1"])

    def test_pkg03_duplicate_tone_lang_is_409(self) -> None:
        package = self.create(variants=THREE_TONES)
        duplicate = self.client.post(
            f"/api/v1/packages/{package['id']}/variants",
            json={"bullet_key": "b1", "tone": "impact", "lang": "zh", "text": "重复的同一格"},
        )
        self.assertEqual(duplicate.status_code, 409)
        error = self.error(duplicate)
        self.assertEqual(error["code"], "CONFLICT")
        self.assertEqual(error["details"]["bullet_key"], "b1")
        self.assertIn("existing_variant_id", error["details"])

    def test_verified_flag_is_boolean_not_string(self) -> None:
        package = self.create(variants=THREE_TONES)
        stored = db_mod.get_conn().execute(
            "SELECT verified FROM package_bullet_variant WHERE package_id = ?", (package["id"],)
        ).fetchall()
        self.assertTrue(all(int(row[0]) in (0, 1) for row in stored))
        self.assertEqual(sum(int(row[0]) for row in stored), 1)


class PackageSearchTest(PackageBaseTest):
    """PKG-04：中文 FTS5（不是 LIKE 冒充）。"""

    def test_pkg04_chinese_query_hits_fts(self) -> None:
        package = self.create()
        self.client.post(
            f"/api/v1/packages/{package['id']}/variants",
            json={"bullet_key": "b1", "tone": "impact", "lang": "zh", "text": "重构门店订单履约链路，缺货率下降 12%"},
        )
        fts_rows = self.count("SELECT COUNT(*) FROM package_fts")
        self.assertGreaterEqual(fts_rows, 1, "package_fts 必须有行（否则是 LIKE 冒充）")
        result = self.client.get("/api/v1/packages?q=订单").get_json()["data"]
        self.assertGreaterEqual(result["total_estimate"], 1)
        self.assertIn(package["id"], [item["id"] for item in result["items"]])
        empty = self.client.get("/api/v1/packages?q=").get_json()["data"]
        self.assertIn("next_cursor", empty)

    def test_search_miss_returns_empty_list(self) -> None:
        self.create()
        result = self.client.get("/api/v1/packages?q=不存在的关键词甲乙丙").get_json()["data"]
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total_estimate"], 0)


@unittest.skipUnless(LLM_KEY_READY, LLM_KEY_REASON)
class PackageGenerateTest(PackageBaseTest):
    """PKG-05：变体生成必须先有 consent preview，且结果不自动入库。"""

    def _preview(self, package_id: str, purpose: str = "bullets_generate") -> str:
        from app.models import PreviewIn
        from app.services.consent import ConsentService

        request = PreviewIn(
            purpose=purpose,
            selections={"package_ids": [package_id], "bullet_keys": ["b1"], "tones": ["impact", "technical"]},
        )
        preview = ConsentService(conn=db_mod.get_conn()).build_preview(request.model_dump(exclude_none=True))
        return preview["preview_id"]

    def test_pkg05_generate_without_preview_is_428(self) -> None:
        package = self.create()
        response = self.client.post(f"/api/v1/packages/{package['id']}/variants/generate", json={})
        self.assertEqual(response.status_code, 428)
        error = self.error(response)
        self.assertEqual(error["code"], "LLM_CONSENT_REQUIRED")
        self.assertEqual(error["details"]["purpose"], "bullets_generate")

    def test_pkg05_generate_202_and_does_not_persist(self) -> None:
        package = self.create()
        preview_id = self._preview(package["id"])
        before = self.count("SELECT COUNT(*) FROM package_bullet_variant")

        canned = {
            "preview_id": preview_id,
            "raw_text": "{}",
            "parsed": {
                "variants": [
                    {"bullet_key": "b1", "tone": "impact", "lang": "zh", "text": "把订单履约链路压到 3 天", "keywords": []},
                    {"bullet_key": "b1", "tone": "technical", "lang": "zh", "text": "用 Flink 重写 ETL", "keywords": []},
                ]
            },
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            "provider": "deepseek",
            "model": "deepseek-chat",
            "latency_ms": 12,
            "finish_reason": "stop",
            "warnings": [],
            "started_at": db_mod.utcnow_iso(),
        }
        with mock.patch("app.services.consent.ConsentService.complete", return_value=canned):
            response = self.client.post(
                f"/api/v1/packages/{package['id']}/variants/generate",
                json={"preview_id": preview_id, "bullet_keys": ["b1"], "tones": ["impact", "technical"]},
            )
            self.assertEqual(response.status_code, 202, response.get_data(as_text=True))
            accepted = response.get_json()["data"]
            self.assertTrue(accepted["job_id"])
            self.assertEqual(accepted["expected_variants"], 2)

            job = {}
            for _ in range(200):
                job = self.client.get(f"/api/v1/jobs/{accepted['job_id']}").get_json()["data"]
                if job["status"] in ("succeeded", "failed"):
                    break
                time.sleep(0.05)
        self.assertEqual(job["status"], "succeeded", job)
        variants = job["result_json"]["variants"]
        self.assertEqual(len(variants), 2)
        self.assertTrue(all(item["llm_generated"] for item in variants))
        self.assertFalse(any(item["verified"] for item in variants))
        self.assertEqual(
            self.count("SELECT COUNT(*) FROM package_bullet_variant"), before, "生成结果不得自动入库"
        )

    def test_generate_rejects_foreign_purpose_preview(self) -> None:
        package = self.create()
        preview_id = self._preview(package["id"], purpose="summary_polish")
        response = self.client.post(
            f"/api/v1/packages/{package['id']}/variants/generate",
            json={"preview_id": preview_id},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.error(response)["code"], "LLM_CONSENT_MISMATCH")


class PackagerTest(unittest.TestCase):
    """对话式打包（纯本地启发式，零出网）：从一段话里抽结构 + 列出要问的问题。"""

    TEXT = (
        "在杭州拓端数据科技有限公司做数据处理实习生，2026.07 - 2026.10。"
        "负责清洗 1220 万行交易数据，把日报从 4 小时压到 20 分钟，效率提升 92%。"
        "用 Python 和 SQL 搭了自动核对脚本，把差错率从 3.1% 降到 0.4%。"
    )

    def test_extracts_org_role_dates_metrics(self) -> None:
        draft = packager.draft_package(self.TEXT)
        package = draft["package"]
        self.assertEqual(package["kind"], "internship")
        self.assertIn("拓端数据", package["org"] or "")
        self.assertIn("实习生", package["role"] or "")
        self.assertEqual(package["start_date"], "2026-07")
        self.assertEqual(package["end_date"], "2026-10")
        self.assertFalse(package["is_current"])
        # 索引层是归一后的规范 token（小写），渲染走原文，两者分离
        self.assertIn("python", package["tech_stack"])
        self.assertIn("sql", package["tech_stack"])
        self.assertGreaterEqual(len(draft["bullets"]), 2)
        self.assertTrue(any(bullet["has_metric"] for bullet in draft["bullets"]))
        self.assertGreaterEqual(len(package["outcomes"]), 1)
        self.assertEqual(draft["stats"]["bullets"], len(draft["bullets"]))

    def test_flags_missing_information_as_questions(self) -> None:
        draft = packager.draft_package("做了一个数据看板。")
        codes = {question["field"] for question in draft["questions"]}
        self.assertIn("org", codes)
        self.assertIn("date_range", codes)
        self.assertTrue(draft["warnings"])
        self.assertEqual(draft["package"]["status"], "draft")

    def test_respects_explicit_overrides_and_bullet_cap(self) -> None:
        long_text = "\n".join(f"第 {index} 条：把某个流程的耗时从 {index * 3} 分钟压到 {index} 分钟。" for index in range(1, 20))
        draft = packager.draft_package(long_text, kind="project", title="自建 ETL 平台", org="某公司", role="开发")
        self.assertEqual(draft["package"]["kind"], "project")
        self.assertEqual(draft["package"]["title"], "自建 ETL 平台")
        self.assertLessEqual(len(draft["bullets"]), packager.MAX_BULLETS)
        keys = [bullet["bullet_key"] for bullet in draft["bullets"]]
        self.assertEqual(len(keys), len(set(keys)), "bullet_key 必须唯一")

    def test_package_draft_endpoint_is_offline(self) -> None:
        base = SERVER.parent / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            os.environ["DATA_DIR"] = tmp
            db_mod.reset_paths_for_tests()
            db_mod.get_paths().ensure()
            client = create_app().test_client()
            try:
                with mock.patch("httpx.Client.post", side_effect=AssertionError("打包不得出网")):
                    response = client.post("/api/v1/packages/draft", json={"text": self.TEXT})
                self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
                data = response.get_json()["data"]
                self.assertEqual(data["package"]["kind"], "internship")
            finally:
                db_mod.close_conn()
                os.environ.pop("DATA_DIR", None)
                db_mod.reset_paths_for_tests()


if __name__ == "__main__":
    unittest.main()
