"""导入：多格式冒烟（docx / html / pdf）+ 照片候选口径（D-23）+ sections 与 blocks 同源（D-25）。

夹具由 captain 补齐（``server/tests/fixtures/sample.docx|html|pdf``）；缺夹具时 **SKIP** 而不是 fail，
避免 CI 假红。photos 相关用例需要用户真实简历（``data/imports/sample_zh.pdf``），
同样缺则 skip。
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from app import config as config_mod  # noqa: E402
from app import create_app  # noqa: E402
from app import db as db_mod  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PROJECT = SERVER.parent
REAL_ZH = PROJECT / "data" / "imports" / "sample_zh.pdf"
SEVERITIES = {"info", "warn"}


class ImportFormatsTest(unittest.TestCase):
    """三种格式各走一遍 POST /imports（断言：201 + 内联 draft + warnings 口径）。"""

    def setUp(self) -> None:
        base = SERVER.parent / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self._tmp.cleanup)
        os.environ["DATA_DIR"] = self._tmp.name
        config_mod.set_config(config_mod.load_config())   # 配置中心是单例，必须显式换掉旧 data_dir
        db_mod.reset_paths_for_tests()
        db_mod.get_paths().ensure()
        self.client = create_app().test_client()

    def tearDown(self) -> None:
        db_mod.close_conn()
        os.environ.pop("DATA_DIR", None)
        config_mod.set_config(config_mod.load_config())
        db_mod.reset_paths_for_tests()

    def upload(self, name: str, payload: bytes):
        return self.client.post(
            "/api/v1/imports",
            data={"file": (io.BytesIO(payload), name)},
            content_type="multipart/form-data",
        )

    def _load(self, name: str) -> bytes:
        path = FIXTURES / name
        if not path.exists():
            self.skipTest(f"缺少夹具 {path}（应由仓库提交，缺失时 skip 而不是 fail）")
        return path.read_bytes()

    def _import(self, name: str) -> dict:
        response = self.upload(name, self._load(name))
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"], payload)
        return payload["data"]

    # -- 三种格式 --------------------------------------------------------------
    def test_pdf_fixture_builds_draft(self) -> None:
        data = self._import("sample.pdf")
        self.assertEqual(data["parser"], "pdf")
        self.assertEqual(data["status"], "draft")
        self.assertTrue(data["blocks"])
        self.assertTrue(data["section_kinds"])
        # needs_llm_fallback 只表示「结构不足或没有抬头」，绝不在请求内调 LLM
        has_header = any(block["block_type"] == "header" for block in data["blocks"])
        self.assertEqual(data["needs_llm_fallback"], not has_header)

    def test_docx_fixture_builds_draft(self) -> None:
        data = self._import("sample.docx")
        self.assertEqual(data["parser"], "docx")
        self.assertTrue(data["blocks"])
        self.assertTrue(data["section_kinds"])

    def test_html_fixture_builds_draft(self) -> None:
        data = self._import("sample.html")
        self.assertEqual(data["parser"], "html")
        self.assertTrue(data["blocks"])
        self.assertTrue(data["section_kinds"])

    def test_import_is_inline_201_with_job_id(self) -> None:
        """D-20：201 + 内联 draft + job_id（同步解析，不轮询）。"""
        data = self._import("sample.docx")
        self.assertIn("draft", data)
        self.assertIn("blocks", data)
        self.assertTrue(data.get("job_id"), "201 响应必须带 job_id")
        job = self.client.get(f"/api/v1/jobs/{data['job_id']}")
        self.assertEqual(job.status_code, 200)
        self.assertEqual(job.get_json()["data"]["status"], "succeeded")

    # -- D-25：sections 由 blocks 派生 -----------------------------------------
    def test_sections_are_derived_from_blocks(self) -> None:
        data = self._import("sample.docx")
        summary_blocks = [
            block
            for block in data["blocks"]
            if block["block_type"] in ("section", "skills", "awards", "summary")
            and block.get("parent_temp_id") is None
        ]
        self.assertEqual(len(data["sections"]), len(summary_blocks))
        for section, block in zip(data["sections"], summary_blocks):
            self.assertEqual(section["heading"], block["heading"] or "")
            self.assertEqual(section["block_type"], block["block_type"])
            self.assertEqual(section["bound_package_kind"], block.get("bound_package_kind"))

    def test_warning_severity_uses_info_or_warn(self) -> None:
        """D-22：severity 只有 info|warn（不允许 "warning"）。"""
        for name in ("sample.docx", "sample.html", "sample.pdf"):
            data = self._import(name)
            for warning in data["warnings"]:
                self.assertIn(warning["severity"], SEVERITIES, warning)


class PhotoCandidateTest(unittest.TestCase):
    """D-23：导入只把照片当**候选**，确认后才写 user_profile.photo_path。"""

    def setUp(self) -> None:
        if not REAL_ZH.exists():
            self.skipTest(f"缺少真实简历 {REAL_ZH}")
        base = SERVER.parent / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self._tmp.cleanup)
        os.environ["DATA_DIR"] = self._tmp.name
        config_mod.set_config(config_mod.load_config())   # 配置中心是单例，必须显式换掉旧 data_dir
        db_mod.reset_paths_for_tests()
        db_mod.get_paths().ensure()
        self.client = create_app().test_client()

    def tearDown(self) -> None:
        db_mod.close_conn()
        os.environ.pop("DATA_DIR", None)
        config_mod.set_config(config_mod.load_config())
        db_mod.reset_paths_for_tests()

    def _import_real(self) -> dict:
        response = self.client.post(
            "/api/v1/imports",
            data={"file": (io.BytesIO(REAL_ZH.read_bytes()), REAL_ZH.name)},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["data"]

    def test_import_does_not_apply_photo(self) -> None:
        data = self._import_real()
        photo = data["extracted_photo"]
        self.assertTrue(photo["available"])
        self.assertFalse(photo["applied"], "导入阶段不得把照片标记为已应用")
        self.assertFalse(photo["confirmed"])
        self.assertTrue(photo.get("attachment_id"))
        self.assertIsNone(
            self.client.get("/api/v1/profile").get_json()["data"].get("photo_path"),
            "导入阶段不得写 user_profile.photo_path",
        )

    def test_import_emits_photo_detected_warning(self) -> None:
        data = self._import_real()
        warnings = {w["code"]: w for w in data["warnings"]}
        self.assertIn("PHOTO_DETECTED", warnings, "AC-IMPORT-03 要求必有 PHOTO_DETECTED")
        entry = warnings["PHOTO_DETECTED"]
        self.assertEqual(entry["severity"], "warn")
        details = entry["details"]
        self.assertTrue(details["attachment_id"])
        self.assertEqual(len(details["sha256"]), 64)
        self.assertEqual((details["width"], details["height"]), (266, 266))

    def test_confirm_photo_writes_profile(self) -> None:
        data = self._import_real()
        # user_profile 是单例且 name_zh 必填（DATA-MODEL）：先有档案才能挂照片
        self.client.put("/api/v1/profile", json={"name_zh": "张三"})
        attachment_id = data["extracted_photo"]["attachment_id"]
        response = self.client.put("/api/v1/profile/photo", json={"attachment_id": attachment_id})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_json()["data"]
        self.assertTrue(body["confirmed"])
        self.assertTrue(body["photo_path"].startswith("profile/photo_"))
        profile = self.client.get("/api/v1/profile").get_json()["data"]
        self.assertEqual(profile["photo_path"], body["photo_path"])
        self.assertEqual(profile["photo_source"], "imported")
        served = self.client.get("/api/v1/files/profile-photo")
        self.assertEqual(served.status_code, 200)
        self.assertTrue(served.data.startswith(b"\x89PNG"))

    def test_confirm_photo_requires_exactly_one_selector(self) -> None:
        response = self.client.put("/api/v1/profile/photo", json={})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()["error"]["code"], "VALIDATION_ERROR")

    def test_commit_does_not_apply_photo_by_default(self) -> None:
        data = self._import_real()
        response = self.client.post(
            f"/api/v1/imports/{data['import_id']}/commit",
            json={"template_name": "照片候选模板", "lang": "zh"},
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        body = response.get_json()["data"]
        self.assertFalse(body["photo_applied"])
        self.assertTrue(body["photo_candidate"]["available"])
        self.assertIsNone(self.client.get("/api/v1/profile").get_json()["data"].get("photo_path"))


class PhotoDecodeTest(unittest.TestCase):
    """m01420 A/B：``/FlateDecode`` 裸像素必须能重建；解码失败必须显式告警而不是静默丢图。"""

    FIXTURE = SERVER / "tests" / "fixtures" / "sample_with_photo.pdf"

    def setUp(self) -> None:
        base = SERVER.parent / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self._tmp.cleanup)
        os.environ["DATA_DIR"] = self._tmp.name
        config_mod.set_config(config_mod.load_config())   # 配置中心是单例，必须显式换掉旧 data_dir
        db_mod.reset_paths_for_tests()
        db_mod.get_paths().ensure()
        self.client = create_app().test_client()

    def tearDown(self) -> None:
        db_mod.close_conn()
        os.environ.pop("DATA_DIR", None)
        config_mod.set_config(config_mod.load_config())
        db_mod.reset_paths_for_tests()

    def _upload(self) -> dict:
        if not self.FIXTURE.exists():
            self.skipTest(f"缺少夹具 {self.FIXTURE}")
        response = self.client.post(
            "/api/v1/imports",
            data={"file": (io.BytesIO(self.FIXTURE.read_bytes()), self.FIXTURE.name)},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["data"]

    def test_raw_flate_pixels_are_decoded(self) -> None:
        """Word/WPS 导出的 PDF 把内嵌 PNG 写成裸 RGB 像素（无容器头），必须能重建。"""
        from PIL import Image

        from app.services import photo as photo_mod

        raw = bytes([200, 210, 225]) * (200 * 200)
        converted = photo_mod.to_png(raw, width=200, height=200, colorspace="DeviceRGB", bits=8)
        self.assertIsNotNone(converted, "裸像素流必须能重建为 PNG")
        png, width, height = converted
        self.assertEqual((width, height), (200, 200))
        with Image.open(io.BytesIO(png)) as frame:
            self.assertEqual(frame.size, (200, 200))

        data = self._upload()
        photo = data["extracted_photo"]
        self.assertTrue(photo["available"])
        self.assertTrue(photo.get("attachment_id"), "available=true 必须有 attachment_id")
        self.assertFalse(photo["unreadable"])
        self.assertIn("PHOTO_DETECTED", {w["code"] for w in data["warnings"]})
        self.assertEqual((photo["width"], photo["height"]), (200, 200))

    def test_decode_failure_is_explicit_not_silent(self) -> None:
        """解码失败 → available=false + unreadable=true + PHOTO_DECODE_FAILED（不得静默丢图）。"""
        from unittest import mock

        with mock.patch("app.services.photo.to_png", return_value=None):
            data = self._upload()
        photo = data["extracted_photo"]
        self.assertFalse(photo["available"], "解码失败不得声称有可用照片")
        self.assertTrue(photo.get("detected"))
        self.assertTrue(photo.get("unreadable"))
        self.assertIsNone(photo.get("file"))
        self.assertIsNone(photo.get("attachment_id"))
        warnings = {w["code"]: w for w in data["warnings"]}
        self.assertIn("PHOTO_DECODE_FAILED", warnings)
        entry = warnings["PHOTO_DECODE_FAILED"]
        self.assertEqual(entry["severity"], "warn")
        self.assertIn("src_width", entry["details"])
        self.assertIn("bytes", entry["details"])
        self.assertNotIn("PHOTO_DETECTED", warnings, "解码失败时不应同时给出可确认的候选")

    def test_available_implies_attachment_id(self) -> None:
        """不变式：任何情况下都不得出现 available=true 却没有 attachment_id。"""
        data = self._upload()
        photo = data["extracted_photo"]
        if photo.get("available"):
            self.assertTrue(photo.get("attachment_id"))
            self.assertTrue(photo.get("file"))


class ProfilePhotoLifecycleTest(unittest.TestCase):
    """DELETE /profile/photo 是「点错就丢设置」的高危操作：必须回上一个路径供撤销（captain m01505 ③）。"""

    def setUp(self) -> None:
        base = SERVER.parent / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self._tmp.cleanup)
        os.environ["DATA_DIR"] = self._tmp.name
        config_mod.set_config(config_mod.load_config())   # 配置中心是单例，必须显式换掉旧 data_dir
        db_mod.reset_paths_for_tests()
        db_mod.get_paths().ensure()
        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        db_mod.close_conn()
        os.environ.pop("DATA_DIR", None)
        config_mod.set_config(config_mod.load_config())
        db_mod.reset_paths_for_tests()

    def _seed(self) -> dict:
        res = self.client.put("/api/v1/profile", json={"name_zh": "张三", "school_zh": "示例大学"})
        self.assertEqual(res.status_code, 200, res.get_json())

        from PIL import Image  # noqa: PLC0415

        buffer = io.BytesIO()
        Image.new("RGB", (240, 240), (200, 180, 160)).save(buffer, format="PNG")
        res = self.client.post(
            "/api/v1/profile/photo",
            data={"file": (io.BytesIO(buffer.getvalue()), "avatar.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 200, res.get_json())
        return res.get_json()["data"]

    def test_delete_returns_previous_path_for_undo(self) -> None:
        uploaded = self._seed()
        self.assertTrue(uploaded["photo_path"])
        res = self.client.delete("/api/v1/profile/photo")
        self.assertEqual(res.status_code, 200, "高危操作应回 200 + 可撤销信息，而不是静默 204")
        data = res.get_json()["data"]
        self.assertTrue(data["cleared"])
        self.assertEqual(data["previous_photo_path"], uploaded["photo_path"])
        self.assertEqual(data["restore_endpoint"], "PUT /api/v1/profile/photo")
        self.assertIsNone(self.client.get("/api/v1/profile").get_json()["data"]["photo_path"])
        # 文件没删（内容寻址可复用），撤销 = PUT 同一个 attachment_id
        self.assertIsNone(data["photo_url"])
        restore = self.client.put("/api/v1/profile/photo", json={"attachment_id": data["previous_attachment_id"]})
        self.assertEqual(restore.status_code, 200, restore.get_json())
        self.assertEqual(self.client.get("/api/v1/profile").get_json()["data"]["photo_path"], uploaded["photo_path"])

    def test_delete_when_no_photo_is_idempotent(self) -> None:
        self.client.put("/api/v1/profile", json={"name_zh": "张三"})
        res = self.client.delete("/api/v1/profile/photo")
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.get_json()["data"]["previous_photo_path"])


class FileDeleteGuardTest(unittest.TestCase):
    """captain m01767（P0）：DELETE /files 必须先查引用；被引用 → 409 FILE_IN_USE，字节不许删。"""

    def setUp(self) -> None:
        base = SERVER.parent / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self._tmp.cleanup)
        os.environ["DATA_DIR"] = self._tmp.name
        config_mod.set_config(config_mod.load_config())
        db_mod.reset_paths_for_tests()
        db_mod.get_paths().ensure()
        self.client = create_app().test_client()

    def tearDown(self) -> None:
        db_mod.close_conn()
        os.environ.pop("DATA_DIR", None)
        config_mod.set_config(config_mod.load_config())
        db_mod.reset_paths_for_tests()

    def _upload_photo(self) -> dict:
        from PIL import Image  # noqa: PLC0415

        self.client.put("/api/v1/profile", json={"name_zh": "张三"})
        buffer = io.BytesIO()
        Image.new("RGB", (240, 240), (10, 20, 30)).save(buffer, format="PNG")
        res = self.client.post(
            "/api/v1/profile/photo",
            data={"file": (io.BytesIO(buffer.getvalue()), "avatar.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(res.status_code, 200, res.get_json())
        return res.get_json()["data"]

    def test_referenced_photo_cannot_be_deleted(self) -> None:
        photo = self._upload_photo()
        path = db_mod.get_paths().root / photo["photo_path"]
        self.assertTrue(path.exists())
        res = self.client.delete(f"/api/v1/files/{photo['attachment_id']}")
        self.assertEqual(res.status_code, 409, res.get_data(as_text=True))
        error = res.get_json()["error"]
        self.assertEqual(error["code"], "FILE_IN_USE")
        self.assertIn("个人资料照片", error["details"]["referenced_by"], "人话标签，不是表名")
        self.assertIn("解除绑定", error["hint"])
        self.assertTrue(path.exists(), "被引用时绝不能删字节，否则照片永久丢失")
        row = db_mod.get_conn().execute(
            "SELECT 1 FROM attachment WHERE id = ?", (photo["attachment_id"],)
        ).fetchone()
        self.assertIsNotNone(row, "行也不能先删")

    def test_unreferenced_photo_can_be_deleted(self) -> None:
        photo = self._upload_photo()
        self.assertEqual(self.client.delete("/api/v1/profile/photo").status_code, 200)
        path = db_mod.get_paths().root / photo["photo_path"]
        self.assertTrue(path.exists(), "解除绑定不删文件（可撤销）")
        res = self.client.delete(f"/api/v1/files/{photo['attachment_id']}")
        self.assertEqual(res.status_code, 204, res.get_data(as_text=True))
        self.assertFalse(path.exists(), "未被引用时才真的删字节")


class CleanOrphanPhotosTest(unittest.TestCase):
    """scripts/clean_orphan_photos.py 的判定：只碰内容寻址命名，且当前照片/草稿候选永不误删。"""

    def setUp(self) -> None:
        base = SERVER.parent / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self._tmp.cleanup)
        os.environ["DATA_DIR"] = self._tmp.name
        config_mod.set_config(config_mod.load_config())
        db_mod.reset_paths_for_tests()
        paths = db_mod.get_paths()
        paths.ensure()
        self.paths = paths
        self.conn = db_mod.get_conn()

    def tearDown(self) -> None:
        db_mod.close_conn()
        os.environ.pop("DATA_DIR", None)
        config_mod.set_config(config_mod.load_config())
        db_mod.reset_paths_for_tests()

    def test_orphan_detached_and_manual_files(self) -> None:
        import importlib.util  # noqa: PLC0415

        script = SERVER.parent / "scripts" / "clean_orphan_photos.py"
        spec = importlib.util.spec_from_file_location("clean_orphan_photos", script)
        module = importlib.util.module_from_spec(spec)
        self.assertIsNotNone(spec.loader)
        spec.loader.exec_module(module)

        profile_dir = self.paths.root / "profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / "photo_aaaaaaaaaaaaaaaa.png").write_bytes(b"orphan")
        (profile_dir / "photo_bbbbbbbbbbbbbbbb.png").write_bytes(b"detached")
        (profile_dir / "photo_cccccccccccccccc.png").write_bytes(b"current")
        (profile_dir / "photo_from_zh_resume.png").write_bytes(b"manual asset")

        self.conn.execute(
            "INSERT INTO attachment (id, sha256, original_name, ext, mime, bytes, kind, privacy, created_at)"
            " VALUES ('01a1', ?, 'b.png', 'png', 'image/png', 8, 'photo', 'private', '2026-01-01T00:00:00')",
            ("b" * 64,),
        )
        from app.repos import ProfileRepo  # noqa: PLC0415

        ProfileRepo().upsert({"name_zh": "张三", "photo_path": "profile/photo_cccccccccccccccc.png"})

        orphans, detached = module.classify(self.paths, self.conn)
        self.assertEqual([p.name for p in orphans], ["photo_aaaaaaaaaaaaaaaa.png"])
        self.assertEqual([p.name for p in detached], ["photo_bbbbbbbbbbbbbbbb.png"])

        exit_code = module.main(["--data-dir", self._tmp.name, "--delete"])
        self.assertEqual(exit_code, 0)
        self.assertFalse((profile_dir / "photo_aaaaaaaaaaaaaaaa.png").exists(), "孤儿应被删除")
        self.assertTrue((profile_dir / "photo_bbbbbbbbbbbbbbbb.png").exists(), "游离候选默认保留")
        self.assertTrue((profile_dir / "photo_cccccccccccccccc.png").exists(), "当前照片不得删")
        self.assertTrue((profile_dir / "photo_from_zh_resume.png").exists(), "非内容寻址命名不得删")


if __name__ == "__main__":
    unittest.main()
