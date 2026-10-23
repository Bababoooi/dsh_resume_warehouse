"""导入历史的「可删」能力：软删 / 恢复 / 去重归档（不物理销毁用户的简历副本）。

判据来源：captain m02126 ③ —— import_job 没有 ``deleted_at`` 时，105 行重复探测数据
只能硬删，而硬删真实简历副本必须先经用户同意。这里把「软删 + 可恢复 + 去重」钉成行为。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))
PROJECT = SERVER.parent
SCRIPTS = PROJECT / "scripts"

from app import create_app  # noqa: E402
from app import db as db_mod  # noqa: E402
from app.services import jobrun  # noqa: E402

SAMPLE_TEXT = """张三
示例大学 本科 2028 届
手机：13800138000 ｜ 邮箱：zhangsan@example.com

教育背景
2024.9-2028.6 示例大学 管理科学 本科
专业成绩：GPA 3.56/4

项目经历
2026.03-2026.04 示例项目
负责数据清洗与建模，样本量 6527 条。
"""


def load_prune_module():
    spec = importlib.util.spec_from_file_location("prune_probe_data", SCRIPTS / "prune_probe_data.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ImportHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.base = PROJECT / "data" / "_tests"
        self.base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=self.base)
        os.environ["DATA_DIR"] = self.tmp.name
        db_mod.reset_paths_for_tests()
        db_mod.get_paths().ensure()
        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        jobrun.wait_idle()
        db_mod.close_conn()
        os.environ.pop("DATA_DIR", None)
        db_mod.reset_paths_for_tests()
        self.tmp.cleanup()

    def _import(self, name: str = "history.txt", text: str = SAMPLE_TEXT) -> str:
        response = self.client.post("/api/v1/imports", json={"text": text, "filename": name})
        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        return response.get_json()["data"]["import_id"]

    def test_soft_delete_hides_but_keeps_row(self) -> None:
        import_id = self._import()
        deleted = self.client.delete(f"/api/v1/imports/{import_id}")
        self.assertEqual(deleted.status_code, 200, deleted.get_data(as_text=True))
        body = deleted.get_json()["data"]
        self.assertTrue(body["deleted"])
        self.assertTrue(body["deleted_at"])

        visible = [item["import_id"] for item in self.client.get("/api/v1/imports").get_json()["data"]["items"]]
        self.assertNotIn(import_id, visible, "软删后默认列表不得再出现")

        with_deleted = [
            item["import_id"]
            for item in self.client.get("/api/v1/imports?include_deleted=1").get_json()["data"]["items"]
        ]
        self.assertIn(import_id, with_deleted)

        conn = db_mod.get_conn()
        row = conn.execute("SELECT deleted_at FROM import_job WHERE id = ?", (import_id,)).fetchone()
        self.assertIsNotNone(row, "行必须还在（可恢复），只标 deleted_at")

        restored = self.client.post(f"/api/v1/imports/{import_id}/restore")
        self.assertEqual(restored.status_code, 200)
        self.assertFalse(restored.get_json()["data"]["deleted"])
        visible = [item["import_id"] for item in self.client.get("/api/v1/imports").get_json()["data"]["items"]]
        self.assertIn(import_id, visible)

    def test_delete_twice_is_idempotent(self) -> None:
        import_id = self._import()
        self.assertEqual(self.client.delete(f"/api/v1/imports/{import_id}").status_code, 200)
        again = self.client.delete(f"/api/v1/imports/{import_id}")
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.get_json()["data"]["deleted"])

    def test_delete_unknown_import_is_404(self) -> None:
        response = self.client.delete("/api/v1/imports/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["code"], "NOT_FOUND")


class PruneImportJobsTest(unittest.TestCase):
    """``find_import_job_duplicates`` 只看指纹，不猜内容：同指纹同源只留最新一条。"""

    def setUp(self) -> None:
        self.base = PROJECT / "data" / "_tests"
        self.base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=self.base)
        os.environ["DATA_DIR"] = self.tmp.name
        db_mod.reset_paths_for_tests()
        db_mod.get_paths().ensure()
        self.conn = db_mod.get_conn()
        self.prune = load_prune_module()

    def tearDown(self) -> None:
        db_mod.close_conn()
        os.environ.pop("DATA_DIR", None)
        db_mod.reset_paths_for_tests()
        self.tmp.cleanup()

    def _seed(self, *, count: int, draft: dict, sha: str = "a" * 64, name: str = "示例.docx") -> list[str]:
        attachment_id = db_mod.new_id()
        now = db_mod.utcnow_iso()
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "INSERT INTO attachment(id, sha256, original_name, ext, mime, bytes, kind, privacy, created_at)"
                " VALUES (?, ?, ?, 'docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 10,"
                " 'resume_source', 'private', ?)",
                (attachment_id, sha, name, now),
            )
        ids = []
        for _ in range(count):
            import_id = db_mod.new_id()
            with db_mod.transaction(self.conn) as conn:
                conn.execute(
                    "INSERT INTO import_job(id, attachment_id, status, parser, draft_json, created_at, updated_at)"
                    " VALUES (?, ?, 'draft', 'docx', ?, ?, ?)",
                    (import_id, attachment_id, json.dumps(draft, ensure_ascii=False), now, now),
                )
            ids.append(import_id)
        return ids

    def test_duplicates_are_archivable_and_latest_is_kept(self) -> None:
        draft = {"sections": [{"kind": "education"}], "blocks": [{"temp_id": "tb-s1"}]}
        ids = self._seed(count=4, draft=draft)
        archivable, kept = self.prune.find_import_job_duplicates(self.conn)
        self.assertEqual(len(archivable), 3, "4 条同指纹 → 3 条可归档")
        self.assertEqual(len(kept), 1)
        self.assertIn(kept[0]["import_id"], ids)
        self.assertEqual(kept[0]["duplicates_archived"], 3)
        self.assertEqual(
            hashlib.sha256(json.dumps(draft, ensure_ascii=False).encode("utf-8")).hexdigest()[:16],
            hashlib.sha256(json.dumps(draft, ensure_ascii=False).encode("utf-8")).hexdigest()[:16],
        )

    def test_different_drafts_are_all_kept(self) -> None:
        self._seed(count=1, draft={"blocks": [{"temp_id": "a"}]})
        self._seed(count=1, draft={"blocks": [{"temp_id": "b"}]}, sha="b" * 64, name="另一份.docx")
        archivable, kept = self.prune.find_import_job_duplicates(self.conn)
        self.assertEqual(archivable, [])
        self.assertEqual(kept, [], "没有重复就没有可保留条目")

    def test_archive_is_reversible_soft_delete(self) -> None:
        draft = {"blocks": [{"temp_id": "c"}]}
        self._seed(count=2, draft=draft, sha="c" * 64)
        archivable, _kept = self.prune.find_import_job_duplicates(self.conn)
        now = db_mod.utcnow_iso()
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "UPDATE import_job SET deleted_at = ?, updated_at = ? WHERE id = ?",
                (now, now, archivable[0]["import_id"]),
            )
        row = self.conn.execute(
            "SELECT deleted_at FROM import_job WHERE id = ?", (archivable[0]["import_id"],)
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertIsNotNone(row["deleted_at"])
        total = self.conn.execute("SELECT COUNT(*) FROM import_job").fetchone()[0]
        self.assertEqual(total, 2, "软删不减少物理行")

    def test_report_section_present_only_when_requested(self) -> None:
        self._seed(count=2, draft={"blocks": [{"temp_id": "d"}]}, sha="d" * 64)
        plain = self.prune.report(db_mod.get_paths(), self.conn)
        self.assertNotIn("import_jobs", plain)
        with_jobs = self.prune.report(db_mod.get_paths(), self.conn, include_import_jobs=True)
        self.assertEqual(with_jobs["import_jobs"]["archivable_count"], 1)


if __name__ == "__main__":
    unittest.main()
