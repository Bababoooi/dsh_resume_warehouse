"""t8：内容完整性（D-46）、英文版 i18n、Package 派生与构建 API 的回归测试。

这些用例锁的是用户能看见的后果：

* 点了「确认入库」之后 GPA / CET / 主修课程 / 技能行必须真的进库（D-46）；
* 英文版**框架**必须是英文（标题/标签/日期/姓名/学历），正文沿用中文时必须告警；
* 导入派生出的 Package 幂等、可级联撤销；
* 构建 → 组装 → 导出 → 下载 全链路可跑，且手填字段不被导入覆盖。
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import config as config_mod
from app import db as db_mod
from app import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ZH_PDF = PROJECT_ROOT / "data" / "imports" / "sample_zh.pdf"

#: D-46 五探针：用户简历里必须原样进库的内容
PROBES = ("GPA 3.56/4", "86.53/100", "CET4：562", "CET6:508", "主修课程：")


class T8Base(unittest.TestCase):
    def setUp(self) -> None:  # noqa: D401
        self._old_env = os.environ.get("DATA_DIR")
        self._tmpdir = tempfile.mkdtemp(prefix="rw-t8-", dir=str(PROJECT_ROOT / "data" / "_tests"))
        os.environ["DATA_DIR"] = self._tmpdir
        config_mod.set_config(config_mod.load_config())
        db_mod.reset_paths_for_tests()
        self.app = create_app()
        self.client = self.app.test_client()

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
    def _import_zh(self) -> str:
        payload = ZH_PDF.read_bytes()
        response = self.client.post(
            "/api/v1/imports",
            data={"file": (io.BytesIO(payload), ZH_PDF.name)},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["data"]["import_id"]

    def _commit(self, import_id: str, **extra) -> dict:
        body = {"template_name": "中文模板", "lang": "zh", "set_default": True}
        body.update(extra)
        response = self.client.post(f"/api/v1/imports/{import_id}/commit", json=body)
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["data"]

    def _profile_row(self) -> dict:
        conn = sqlite3.connect(db_mod.get_paths().db)
        conn.row_factory = sqlite3.Row
        try:
            return dict(conn.execute("SELECT * FROM user_profile WHERE id='me'").fetchone())
        finally:
            conn.close()


@unittest.skipUnless(ZH_PDF.exists(), "缺少真实简历样本")
class CommitKeepsContentTest(T8Base):
    """D-46：commit 不得丢静态内容。"""

    def test_static_text_and_profile_are_filled(self) -> None:
        import_id = self._import_zh()
        result = self._commit(import_id)
        self.assertEqual(result["blocks_created"], 12)

        conn = sqlite3.connect(db_mod.get_paths().db)
        try:
            statics = [
                row[0] or ""
                for row in conn.execute("SELECT static_text FROM template_block")
            ]
        finally:
            conn.close()
        merged = "\n".join(statics)
        for probe in PROBES:
            with self.subTest(probe=probe):
                self.assertIn(probe, merged, f"commit 把「{probe}」丢了")

        row = self._profile_row()
        self.assertEqual(row["degree"], "本科")
        self.assertIn("管理科学", row["major"] or "")
        self.assertTrue(row["grad_year"])
        self.assertTrue(row["city"])
        skills = json.loads(row["skills_json"] or "[]")
        self.assertEqual(len(skills), 3)
        self.assertTrue(all(item.get("line") for item in skills))
        sources = json.loads(row["extra_json"] or "{}").get("profile_field_sources") or {}
        self.assertTrue(sources.get("degree", "").startswith("import:"), sources)

    def test_manual_values_are_not_overwritten(self) -> None:
        self.client.put(
            "/api/v1/profile",
            json={"name_zh": "张三", "degree": "硕士", "extra": {"profile_field_sources": {"degree": "manual"}}},
        )
        import_id = self._import_zh()
        result = self._commit(import_id)
        self.assertIn("degree", result["profile_fields_skipped_manual"])
        self.assertEqual(self._profile_row()["degree"], "硕士")

    def test_overwrite_profile_flag_wins(self) -> None:
        self.client.put(
            "/api/v1/profile",
            json={"name_zh": "张三", "degree": "硕士", "extra": {"profile_field_sources": {"degree": "manual"}}},
        )
        import_id = self._import_zh()
        self._commit(import_id, overwrite_profile=True)
        self.assertEqual(self._profile_row()["degree"], "本科")


@unittest.skipUnless(ZH_PDF.exists(), "缺少真实简历样本")
class PackagesFromImportTest(T8Base):
    """导入派生的 Package：幂等、语言正确、可级联撤销。"""

    def test_packages_created_with_import_language(self) -> None:
        import_id = self._import_zh()
        result = self._commit(import_id, also_create_packages=True)
        created = result["packages_created"]
        # 实习 1 + 项目 3 + 校园 1（教育走档案，不落 package）
        self.assertEqual(len(created), 5)
        detail = self.client.get(f"/api/v1/packages/{created[0]}").get_json()["data"]
        self.assertIn(f"import:{import_id}", detail["tags"])
        variants = self.client.get(f"/api/v1/packages/{created[0]}/variants").get_json()["data"]["items"]
        self.assertTrue(variants)
        self.assertTrue(all(item["lang"] == "zh" for item in variants))
        self.assertTrue(all(item["tone"] == "original" for item in variants))

    def test_creating_twice_reuses_instead_of_duplicating(self) -> None:
        from app.services import import_service

        import_id = self._import_zh()
        self._commit(import_id, also_create_packages=True)
        draft = json.loads(
            sqlite3.connect(db_mod.get_paths().db)
            .execute("SELECT draft_json FROM import_job WHERE id=?", (import_id,))
            .fetchone()[0]
        )
        again = import_service.create_packages_from_draft(draft, import_id=import_id, lang="zh")
        self.assertEqual(again["created"], [])
        self.assertEqual(len(again["reused"]), 5)

    def test_delete_import_cascades_packages(self) -> None:
        import_id = self._import_zh()
        self._commit(import_id, also_create_packages=True)
        before = self.client.get("/api/v1/packages").get_json()["data"]["total_estimate"]
        self.assertEqual(before, 5)
        response = self.client.delete(f"/api/v1/imports/{import_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["data"]["packages_deleted"]), 5)
        self.assertEqual(self.client.get("/api/v1/packages").get_json()["data"]["total_estimate"], 0)


@unittest.skipUnless(ZH_PDF.exists(), "缺少真实简历样本")
class EnglishBuildTest(T8Base):
    """英文版：框架英文 + 缺英文值时省略而不是塞中文 + 中文正文必须告警。"""

    def _seed(self) -> tuple[str, str]:
        # 命名模板需要 {name}/{school}：先把档案填上（真实使用里用户在导入确认时就填了）
        self.client.put(
            "/api/v1/profile",
            json={"name_zh": "张三", "name_en": "SAN ZHANG", "school_zh": "示例大学", "school_en": "Wuhan University"},
        )
        import_id = self._import_zh()
        self._commit(import_id, also_create_packages=True)
        package = self.client.get("/api/v1/packages").get_json()["data"]["items"][0]
        template = self.client.get("/api/v1/templates/default").get_json()["data"]
        build = self.client.post(
            "/api/v1/builds",
            json={
                "name": "EN smoke",
                "template_id": template["id"],
                "position": "Data Analyst Intern",
                "company": "Example Co",
                "lang": "en",
            },
        )
        self.assertEqual(build.status_code, 201, build.get_data(as_text=True))
        build_id = build.get_json()["data"]["id"]
        selection = self.client.put(
            f"/api/v1/builds/{build_id}/selections",
            json={"items": [{"package_id": package["id"], "variant_ids": []}]},
        )
        self.assertEqual(selection.status_code, 200, selection.get_data(as_text=True))
        return build_id, package["id"]

    def test_english_build_warns_instead_of_silently_falling_back(self) -> None:
        build_id, _ = self._seed()
        response = self.client.post(f"/api/v1/builds/{build_id}/assemble")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()["data"]
        codes = [w["code"] for w in data["warnings"]]
        self.assertIn("LANG_FALLBACK", codes, codes)
        fallback = next(w for w in data["warnings"] if w["code"] == "LANG_FALLBACK")
        details = fallback["details"]
        self.assertGreaterEqual(details["bullet_count"], 1)
        # 口径必须可核：samples 与回退条目数一一对应，技能区单独标记
        self.assertEqual(len(details["samples"]), details["entry_count"], details)
        self.assertIsInstance(details["skills_fallback"], bool)
        self.assertEqual(len(details["entries"]), details["entry_count"], details)

    def test_english_build_prefers_english_variant_over_stale_ids(self) -> None:
        """反向断言：有 en 变体就绝不许回退（哪怕组装页存着上次的 zh variant_ids）。"""
        package = self.client.post(
            "/api/v1/packages",
            json={"title": "AB 测试项目", "kind": "project", "status": "draft"},
        ).get_json()["data"]
        zh = self.client.post(
            f"/api/v1/packages/{package['id']}/variants",
            json={
                "bullet_key": "b1",
                "tone": "impact",
                "lang": "zh",
                "text": "中文原文：广告效率提升 39.3%。",
                "verified": True,
            },
        ).get_json()["data"]["id"]
        en = self.client.post(
            f"/api/v1/packages/{package['id']}/variants",
            json={"bullet_key": "b1", "tone": "impact", "lang": "en", "text": "Lifted ad efficiency by 39.3%."},
        ).get_json()["data"]["id"]
        self.assertTrue(zh and en)
        # 只有 ready 的包会进组装；draft 是「还没写完」，不该出现在成品里
        promote = self.client.patch(f"/api/v1/packages/{package['id']}", json={"status": "ready"})
        self.assertEqual(promote.status_code, 200, promote.get_data(as_text=True))
        import_id = self._import_zh()
        self._commit(import_id, also_create_packages=False)
        template = self.client.get("/api/v1/templates/default").get_json()["data"]
        build = self.client.post(
            "/api/v1/builds",
            json={"name": "英文优先", "template_id": template["id"], "position": "Data Analyst", "lang": "en"},
        ).get_json()["data"]
        self.client.put(
            f"/api/v1/builds/{build['id']}/selections",
            json={"items": [{"package_id": package["id"], "variant_ids": [zh]}]},
        )
        assembled = self.client.post(f"/api/v1/builds/{build['id']}/assemble").get_json()["data"]
        bullets = [
            bullet
            for section in assembled["ir"]["sections"]
            for entry in section.get("entries") or []
            for bullet in entry.get("bullets") or []
        ]
        self.assertTrue(any("Lifted ad efficiency" in text for text in bullets), bullets)
        self.assertFalse(any("广告效率提升" in text for text in bullets), "有 en 变体却被回退")
        # 教育段正文只有中文，回退它是诚实的；这里只断言「有 en 变体的条目」没被回退
        fallback = next((w for w in assembled["warnings"] if w["code"] == "LANG_FALLBACK"), None)
        if fallback:
            titles = [str(item.get("title") or "") for item in fallback["details"]["entries"]]
            self.assertNotIn("AB 测试项目", titles, titles)

    def test_english_export_chrome_has_no_chinese(self) -> None:
        import pdfplumber

        build_id, _ = self._seed()
        assembled = self.client.post(f"/api/v1/builds/{build_id}/assemble").get_json()["data"]
        data_header = assembled.get("header") or {}
        data_sections = assembled.get("sections") or []
        response = self.client.post(
            f"/api/v1/builds/{build_id}/export", json={"format": "pdf", "verify_text": True}
        )
        self.assertEqual(response.status_code, 202, response.get_data(as_text=True))
        job_id = response.get_json()["data"]["job_id"]
        from app.services import jobrun

        jobrun.wait_idle()
        job = self.client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
        self.assertEqual(job["status"], "succeeded", job)
        artifacts = job["result_json"]["artifacts"]
        self.assertTrue(artifacts)
        path = db_mod.get_paths().exports / artifacts[0]["rel_path"].split("/")[-1]
        with pdfplumber.open(path) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        from app.services import i18n

        # 「框架区」= 抬头字段 + 段落标题；正文允许暂用中文但必须有 LANG_FALLBACK
        chrome = [
            item
            for item in (
                data_header.get("name"),
                data_header.get("education_line"),
                data_header.get("contact_line"),
                data_header.get("available"),
            )
            if item
        ] + [section.get("heading") for section in data_sections]
        chrome_cjk = sum(i18n.cjk_count(str(item)) for item in chrome)
        self.assertEqual(chrome_cjk, 0, chrome)
        self.assertIn("Education", text)


class BuildApiTest(T8Base):
    """构建 API 的最小闭环（无需真实简历）。"""

    def _template(self) -> str:
        from app.repos import TemplateRepo

        return TemplateRepo().create({"name": "内置模板", "lang": "zh", "source_kind": "builtin"})

    def test_build_crud_and_selection_guard(self) -> None:
        template_id = self._template()
        created = self.client.post(
            "/api/v1/builds", json={"name": "首次构建", "template_id": template_id, "position": "数据分析"}
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.headers.get("Location"))
        build_id = created.get_json()["data"]["id"]
        self.assertEqual(self.client.get(f"/api/v1/builds/{build_id}").status_code, 200)

        package = self.client.post(
            "/api/v1/packages", json={"title": "草稿包", "kind": "project", "status": "draft"}
        ).get_json()["data"]
        rejected = self.client.put(
            f"/api/v1/builds/{build_id}/selections", json={"items": [{"package_id": package["id"]}]}
        )
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected.get_json()["error"]["details"]["reason"], "PACKAGE_NOT_READY")

        # 默认 DELETE 是**归档**不是物理删：行、选题、产物都留着，否则 data/exports
        # 里的 PDF 立刻变孤儿（磁盘上那 22 个无主 PDF 就是这么产生的）。
        self.assertEqual(self.client.delete(f"/api/v1/builds/{build_id}").status_code, 204)
        archived = self.client.get(f"/api/v1/builds/{build_id}")
        self.assertEqual(archived.status_code, 200)
        self.assertIsNotNone(archived.get_json()["data"].get("archived_at"))
        # 真删必须显式 hard + confirm；confirm 不对要拦下且不产生副作用
        self.assertEqual(
            self.client.delete(f"/api/v1/builds/{build_id}?hard=1&confirm=wrong").status_code, 422
        )
        self.assertEqual(self.client.get(f"/api/v1/builds/{build_id}").status_code, 200)
        self.assertEqual(
            self.client.delete(f"/api/v1/builds/{build_id}?hard=1&confirm={build_id}").status_code, 204
        )
        self.assertEqual(self.client.get(f"/api/v1/builds/{build_id}").status_code, 404)

    def test_assemble_requires_selection(self) -> None:
        template_id = self._template()
        build_id = self.client.post(
            "/api/v1/builds", json={"name": "空构建", "template_id": template_id}
        ).get_json()["data"]["id"]
        response = self.client.post(f"/api/v1/builds/{build_id}/assemble")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["sections"], [])


if __name__ == "__main__":
    unittest.main()
