"""演示/示例经历的判据与护栏（用户不会想在自己的简历里看到「没做过」的经历）。

三个层次各锁一条：

1. ``services/samples.is_sample`` 的判据只有两条（tags 含 sample / 标题以【示例】开头），
   真数据不会被误判；
2. ``POST /builds/{id}/suggest`` 默认选包必须排除演示数据，并在 ``excluded`` 里交代原因；
3. 若用户手动把演示包选进 build，``assemble`` 必须发 ``SAMPLE_PACKAGE_INCLUDED`` 警告——
   可以选，但不能静默印进成品。
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from app import config as config_mod
from app import db as db_mod
from app import create_app
from app.services import samples

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SamplesBase(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = os.environ.get("DATA_DIR")
        self._tmpdir = tempfile.mkdtemp(prefix="rw-sample-", dir=str(PROJECT_ROOT / "data" / "_tests"))
        os.environ["DATA_DIR"] = self._tmpdir
        config_mod.set_config(config_mod.load_config())
        db_mod.reset_paths_for_tests()
        self.app = create_app()
        self.client = self.app.test_client()
        # 档案：命名模板需要姓名与学校
        self.client.put("/api/v1/profile", json={"name_zh": "张三", "school_zh": "示例大学"})
        from app.repos import TemplateRepo

        self.template_id = TemplateRepo().create({"name": "内置模板", "lang": "zh", "source_kind": "builtin"})

    def tearDown(self) -> None:
        try:
            from app.services import jobrun

            jobrun.wait_idle()
        finally:
            db_mod.close_conn()
            if self._old_env is None:
                os.environ.pop("DATA_DIR", None)
            else:
                os.environ["DATA_DIR"] = self._old_env
            config_mod.set_config(config_mod.load_config())
            db_mod.reset_paths_for_tests()
            shutil.rmtree(self._tmpdir, ignore_errors=True)

    # helpers ---------------------------------------------------------------
    def _package(self, title: str, *, tags: list[str], verified: bool = True) -> str:
        payload = {
            "title": title,
            "kind": "project",
            "org": "示例公司",
            "role": "队长",
            "start_date": "2026-03",
            "status": "draft",
            "tags": tags,
            "variants": [
                {"bullet_key": "b1", "tone": "impact", "lang": "zh", "text": f"{title} 的要点", "verified": verified}
            ],
        }
        created = self.client.post("/api/v1/packages", json=payload)
        self.assertEqual(created.status_code, 201, created.get_json())
        package_id = created.get_json()["data"]["id"]
        if verified:
            patched = self.client.patch(
                f"/api/v1/packages/{package_id}", json={"status": "ready"}
            )
            self.assertEqual(patched.status_code, 200, patched.get_json())
        return package_id

    def _build(self) -> str:
        created = self.client.post(
            "/api/v1/builds",
            json={"name": "演示护栏", "template_id": self.template_id, "position": "数据分析实习生"},
        )
        self.assertEqual(created.status_code, 201, created.get_json())
        return created.get_json()["data"]["id"]


class IsSampleTest(unittest.TestCase):
    def test_detects_tag_title_and_keeps_real_data(self) -> None:
        self.assertTrue(samples.is_sample({"title": "普通经历", "tags": ["sample"]}))
        self.assertTrue(samples.is_sample({"title": "【示例】小象超市门店选址", "tags": []}))
        self.assertTrue(samples.is_sample({"title": "普通经历", "tags": '["数据分析","sample"]'}))
        self.assertFalse(samples.is_sample({"title": "杭州拓端数据科技有限公司 · 数据处理实习生", "tags": ["数据分析"]}))
        self.assertFalse(samples.is_sample({"title": "【示例】x", "tags": ["示例"]}) is False)
        self.assertFalse(samples.is_sample(None))

    def test_warning_is_none_for_real_rows(self) -> None:
        self.assertIsNone(samples.included_warning([{"id": "1", "title": "小象超市门店选址", "tags": []}]))
        warning = samples.included_warning([{"id": "2", "title": "【示例】x", "tags": []}])
        self.assertEqual(warning["code"], "SAMPLE_PACKAGE_INCLUDED")
        self.assertEqual(warning["details"]["packages"][0]["package_id"], "2")


class SuggestExcludesSampleTest(SamplesBase):
    def test_suggest_returns_real_packages_only(self) -> None:
        real = self._package("小象超市门店选址与订单量预测", tags=["数据分析"])
        demo = self._package("【示例】小象超市门店选址与订单量预测建模", tags=["数据分析", "sample"])
        build_id = self._build()

        response = self.client.post(f"/api/v1/builds/{build_id}/suggest", json={})
        self.assertEqual(response.status_code, 200, response.get_json())
        data = response.get_json()["data"]
        ids = [item["package_id"] for item in data["selections"]]
        self.assertIn(real, ids)
        self.assertNotIn(demo, ids, "演示包绝不能进默认选包")
        self.assertEqual([item["package_id"] for item in data["excluded"]], [demo])
        self.assertEqual(data["excluded"][0]["reason"], "sample")

    def test_suggest_apply_writes_selections_without_sample(self) -> None:
        real = self._package("赛车类游戏版本AB测试对照数据分析", tags=["数据分析"])
        self._package("【示例】小象超市门店选址与订单量预测建模", tags=["sample"])
        build_id = self._build()

        response = self.client.post(f"/api/v1/builds/{build_id}/suggest", json={"apply": True})
        self.assertEqual(response.status_code, 200)
        selections = self.client.get(f"/api/v1/builds/{build_id}/selections").get_json()["data"]["items"]
        self.assertEqual([item["package_id"] for item in selections], [real])


class ExportGuardTest(SamplesBase):
    def test_selected_sample_package_produces_warning(self) -> None:
        demo = self._package("【示例】小象超市门店选址与订单量预测建模", tags=["sample"])
        build_id = self._build()
        put = self.client.put(
            f"/api/v1/builds/{build_id}/selections", json={"selections": [{"package_id": demo}]}
        )
        self.assertEqual(put.status_code, 200, put.get_json())

        assembled = self.client.post(f"/api/v1/builds/{build_id}/assemble")
        self.assertEqual(assembled.status_code, 200, assembled.get_json())
        data = assembled.get_json()["data"]
        codes = [warning["code"] for warning in data["warnings"]]
        self.assertIn("SAMPLE_PACKAGE_INCLUDED", codes, "选了演示包必须告警，不能静默印进成品")
        warning = next(item for item in data["warnings"] if item["code"] == "SAMPLE_PACKAGE_INCLUDED")
        self.assertEqual(warning["details"]["packages"][0]["package_id"], demo)

    def test_no_warning_for_real_packages(self) -> None:
        real = self._package("小象超市门店选址与订单量预测", tags=["数据分析"])
        build_id = self._build()
        self.client.put(f"/api/v1/builds/{build_id}/selections", json={"selections": [{"package_id": real}]})
        data = self.client.post(f"/api/v1/builds/{build_id}/assemble").get_json()["data"]
        self.assertNotIn("SAMPLE_PACKAGE_INCLUDED", [warning["code"] for warning in data["warnings"]])


if __name__ == "__main__":
    unittest.main()
