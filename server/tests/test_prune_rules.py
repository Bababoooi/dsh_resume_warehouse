"""清理脚本的规则门：**模板来源不许被归档**。

背景（2026-10-23 真库事故）：``prune_probe_data.py --prune-import-jobs`` 原本对每组
「同 sha + 同 draft 指纹」只留**最新**一条，于是唯一活跃的默认模板「中文-单页-审」
的来源 ``import_job``（比后来的重复 draft 更早）被当成旧重复归档，溯源链断裂且不报错。

修法（本文件钉死）：``status='committed'`` 或 ``result_template_id IS NOT NULL`` 的行
永远保留；只有纯草稿重复才可归档。另加硬校验：待归档集合里但凡出现「指向仍存活模板」
的行就 ``SystemExit(1)``。
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
PROJECT = SERVER.parent
for extra in (SERVER, PROJECT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import prune_probe_data as prune  # noqa: E402


def _insert_template(conn: sqlite3.Connection, template_id: str, name: str = "中文-单页-审") -> None:
    conn.execute(
        "INSERT INTO template (id, name, source_kind, lang, page_limit, layout_json, is_default,"
        " created_at, updated_at) VALUES (?, ?, 'imported_pdf', 'zh', 1, '{}', 1, ?, ?)",
        (template_id, name, "2026-10-23T03:31:00+08:00", "2026-10-23T03:31:00+08:00"),
    )


def _insert_import(
    conn: sqlite3.Connection,
    import_id: str,
    *,
    status: str,
    created_at: str,
    draft_json: str = '{"blocks": []}',
    result_template_id: str | None = None,
    deleted_at: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO import_job (id, attachment_id, status, parser, draft_json, result_template_id,"
        " created_at, updated_at, deleted_at) VALUES (?, ?, ?, 'pdf', ?, ?, ?, ?, ?)",
        (
            import_id,
            "att-provenance",
            status,
            draft_json,
            result_template_id,
            created_at,
            created_at,
            deleted_at,
        ),
    )


class PruneProvenanceTest(unittest.TestCase):
    """同一指纹里既有 committed 又有 draft 时，必须归档 draft、保留 committed。"""

    def setUp(self) -> None:
        # DATA_DIR 必须落在项目内（ARCHITECTURE §5.3）：临时目录放 data/_tests/ 下
        sandbox = PROJECT / "data" / "_tests"
        sandbox.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=sandbox, prefix="prune-rules-")
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "app.db"
        from app import db as db_mod

        db_mod.reset_paths_for_tests(self.tmp.name)
        self.addCleanup(db_mod.close_conn)
        self.conn = db_mod.get_conn()
        self.conn.execute(
            "INSERT INTO attachment (id, sha256, original_name, ext, mime, bytes, kind, privacy,"
            " created_at) VALUES ('att-provenance', ?, 'sample_zh.pdf', 'pdf',"
            " 'application/pdf', 1024, 'resume_source', 'private', '2026-10-23T03:31:00+08:00')",
            ("a" * 64,),
        )
        self.conn.commit()
        self.addCleanup(self._teardown_db)

    def _teardown_db(self) -> None:
        try:
            self.conn.close()
        except Exception:  # pragma: no cover - 连接可能已被关
            pass

    def test_prune_never_archives_template_provenance(self) -> None:
        """先 draft 后 committed 的同指纹两条 → 归档 draft，保留 committed 与它的模板。"""
        _insert_template(self.conn, "tpl-default")
        _insert_import(
            self.conn,
            "imp-committed",
            status="committed",
            created_at="2026-10-23T03:31:10+08:00",
            result_template_id="tpl-default",
        )
        # 更晚的重复草稿：指纹相同、无产出
        _insert_import(
            self.conn,
            "imp-draft-later",
            status="draft",
            created_at="2026-10-23T03:38:34+08:00",
        )
        self.conn.commit()

        archivable, kept = prune.find_import_job_duplicates(self.conn)

        ids_archivable = {item["import_id"] for item in archivable}
        self.assertIn("imp-draft-later", ids_archivable)
        self.assertNotIn("imp-committed", ids_archivable, "模板来源行不许被归档")

        # 归档后 committed 行仍可见，它引用的模板仍存活
        prune.assert_no_live_template_provenance(self.conn, archivable)
        self.conn.execute(
            "UPDATE import_job SET deleted_at = '2026-10-23T04:00:00+08:00' WHERE id = 'imp-draft-later'"
        )
        self.conn.commit()
        live = self.conn.execute(
            "SELECT COUNT(*) FROM import_job WHERE status = 'committed' AND deleted_at IS NULL"
        ).fetchone()[0]
        self.assertEqual(live, 1)
        template = self.conn.execute(
            "SELECT deleted_at FROM template WHERE id = 'tpl-default'"
        ).fetchone()
        self.assertIsNotNone(template)
        self.assertIsNone(template["deleted_at"])

    def test_committed_rows_are_never_candidates_even_when_older(self) -> None:
        """只有 committed 行、没有草稿重复时，归档集合为空。"""
        _insert_template(self.conn, "tpl-a")
        _insert_import(
            self.conn, "imp-c1", status="committed", created_at="2026-10-23T03:31:10+08:00",
            result_template_id="tpl-a",
        )
        _insert_import(
            self.conn, "imp-c2", status="committed", created_at="2026-10-23T03:47:00+08:00",
            result_template_id="tpl-a",
        )
        self.conn.commit()
        archivable, _ = prune.find_import_job_duplicates(self.conn)
        self.assertEqual(archivable, [])

    def test_guard_aborts_when_archive_would_cut_provenance(self) -> None:
        """防御性校验：待归档里混进指向存活模板的行 → 直接中止（exit 1）。"""
        _insert_template(self.conn, "tpl-live")
        self.conn.commit()
        bogus = [
            {
                "import_id": "imp-x",
                "status": "draft",
                "result_template_id": "tpl-live",
                "original_name": "x.pdf",
                "created_at": "2026-10-23T03:31:10+08:00",
                "bytes": 10,
            }
        ]
        with self.assertRaises(SystemExit) as ctx:
            prune.assert_no_live_template_provenance(self.conn, bogus)
        self.assertEqual(ctx.exception.code, 1)

    def test_hard_delete_list_excludes_rows_with_template(self) -> None:
        """``--delete`` 的硬删候选也不许包含有产出的行。"""
        _insert_template(self.conn, "tpl-b")
        _insert_import(
            self.conn, "imp-new", status="draft", created_at="2026-10-23T03:47:00+08:00"
        )
        _insert_import(
            self.conn, "imp-with-tpl", status="draft", created_at="2026-10-23T03:31:00+08:00",
            result_template_id="tpl-b",
        )
        self.conn.commit()
        drafts = prune.find_duplicate_drafts(self.conn)
        ids = {item["import_id"] for item in drafts}
        self.assertNotIn("imp-with-tpl", ids)


if __name__ == "__main__":
    unittest.main()
