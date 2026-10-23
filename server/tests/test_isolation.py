"""测试隔离门：跑测试不许污染用户真实数据库。

背景（2026-10-23 实测事故）：``reset_paths_for_tests()`` 曾经只清路径缓存却复用旧
``Config`` 单例，于是「测试用临时 DATA_DIR 建 app、repo 却拿到真实 data/app.db」，
一套全量测试往真实库里写了 91 条重复导入草稿。根因修完后，这条门把行为钉死：

* 假测试库里写东西 → 真实 ``data/app.db`` 的四张核心表行数必须**逐字不变**；
* 临时目录用完即删，不在 ``data/`` 下留垃圾；
* 真实库只读打开（``mode=ro``），连 PRAGMA 都不写。
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

PROJECT = SERVER.parent
REAL_DB = PROJECT / "data" / "app.db"
TABLES = ("import_job", "package", "template", "attachment", "user_profile")


def counts(db_path: Path) -> dict[str, int] | None:
    """只读打开并数行；库文件不存在时返回 None（干净 clone 场景）。"""
    if not db_path.exists():
        return None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        result: dict[str, int] = {}
        for table in TABLES:
            try:
                result[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except sqlite3.OperationalError:
                result[table] = -1  # 表还不存在（空库）也如实记录，便于比对
        return result
    finally:
        conn.close()


from app import create_app  # noqa: E402
from app import db as db_mod  # noqa: E402
from app.services import jobrun  # noqa: E402


class TestIsolationTest(unittest.TestCase):
    def test_writes_land_in_temp_db_not_real_db(self) -> None:
        before = counts(REAL_DB)

        base = PROJECT / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            os.environ["DATA_DIR"] = tmp
            try:
                db_mod.reset_paths_for_tests()
                db_mod.get_paths().ensure()
                self.assertTrue(db_mod.get_paths().db.is_relative_to(Path(tmp).resolve()), "连接必须指向临时库")

                app = create_app()
                client = app.test_client()

                # 四类写入：档案 / 经历包 / 模板（导入 commit）/ 附件
                self.assertEqual(client.put("/api/v1/profile", json={"name_zh": "隔离测试"}).status_code, 200)
                package = client.post(
                    "/api/v1/packages", json={"title": "隔离测试经历", "kind": "project"}
                )
                self.assertEqual(package.status_code, 201)
                imported = client.post(
                    "/api/v1/imports",
                    json={
                        "text": "教育背景\n2024.9-2028.6 示例大学 本科\n\n项目经历\n2026.03-2026.04 隔离测试项目\n负责数据清洗与建模。",
                        "filename": "isolation.txt",
                    },
                )
                self.assertEqual(imported.status_code, 201, imported.get_data(as_text=True))
                import_id = imported.get_json()["data"]["import_id"]
                committed = client.post(f"/api/v1/imports/{import_id}/commit", json={"template_name": "隔离模板"})
                self.assertEqual(committed.status_code, 201, committed.get_data(as_text=True))
                # 附件写入：带一枚真 PNG，确认文件落临时库的 files/ 下
                import io

                png = bytes.fromhex(
                    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                    "0000000a49444154789c6360000002000100ee0e0d0a0000000049454e44ae426082"
                )
                uploaded = client.post(
                    "/api/v1/files",
                    data={"kind": "evidence", "privacy": "private", "file": (io.BytesIO(png), "probe.png")},
                    content_type="multipart/form-data",
                )
                self.assertEqual(uploaded.status_code, 201, uploaded.get_data(as_text=True))

                temp_counts = counts(Path(tmp) / "app.db")
                self.assertIsNotNone(temp_counts)
                self.assertGreaterEqual(temp_counts["package"], 1)
                self.assertGreaterEqual(temp_counts["import_job"], 1)
                self.assertGreaterEqual(temp_counts["template"], 1)
                self.assertGreaterEqual(temp_counts["attachment"], 1)
            finally:
                jobrun.wait_idle()
                db_mod.close_conn()
                os.environ.pop("DATA_DIR", None)
                db_mod.reset_paths_for_tests()

        after = counts(REAL_DB)
        self.assertEqual(before, after, f"真实库被测试污染：{before} → {after}")

    def test_reset_points_at_new_dir_even_with_cached_config(self) -> None:
        cfg_before = None
        try:
            base = PROJECT / "data" / "_tests"
            base.mkdir(parents=True, exist_ok=True)
            first = tempfile.TemporaryDirectory(dir=base)
            second = tempfile.TemporaryDirectory(dir=base)
            try:
                os.environ["DATA_DIR"] = first.name
                db_mod.reset_paths_for_tests()
                db_mod.get_paths().ensure()
                from app import config as config_mod

                cfg_before = config_mod.get_config()
                conn_one = db_mod.get_conn()
                conn_one.execute("SELECT 1").fetchone()
                first_db = db_mod.get_paths().db

                # 换数据根：即使 Config 单例还缓存着旧值，路径与连接都必须跟着走
                os.environ["DATA_DIR"] = second.name
                db_mod.reset_paths_for_tests()
                db_mod.get_paths().ensure()
                second_db = db_mod.get_paths().db
                self.assertNotEqual(first_db, second_db)
                conn_two = db_mod.get_conn()
                self.assertIsNot(conn_two, conn_one, "换库后必须重连，不能复用旧连接")
                self.assertEqual(Path(second_db).parent.name, Path(second.name).name)
            finally:
                for tmp in (first, second):
                    tmp.cleanup()
        finally:
            jobrun.wait_idle()
            db_mod.close_conn()
            os.environ.pop("DATA_DIR", None)
            db_mod.reset_paths_for_tests()


if __name__ == "__main__":
    unittest.main()
