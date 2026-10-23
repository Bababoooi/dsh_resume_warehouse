"""P0 事故脚本 `scripts/repair_package_is_current.py` 的行为锁。

判据（captain m01849 §三②）：
* 默认 dry-run，只列清单、绝不写库；
* `--apply` 只改**能确定判定**的行（草稿里反解出唯一结束时间）→ 回填 end_date + is_current=0；
* 反解不到 / 互相矛盾 → 进「需人工确认」，不许猜；
* 写库前后各一次快照。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
PROJECT = SERVER.parent
for path in (SERVER, PROJECT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app import db as db_mod  # noqa: E402


def _load_script():
    target = PROJECT / "scripts" / "repair_package_is_current.py"
    spec = importlib.util.spec_from_file_location("repair_is_current", target)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


repair = _load_script()


ENTRY_DRAFT = {
    "blocks": [
        {"block_type": "section", "bound_package_kind": "project", "heading": "项目经历"},
        {
            "block_type": "entry",
            "bound_package_kind": "project",
            "heading": "小象超市",
            "entry": {
                "title": "小象超市门店选址与订单量预测建模",
                "org": "全国大学生商业分析大赛",
                "role": "队长",
                "date_range": "2026.03 - 2026.04",
                "bullets": ["做了点事"],
            },
        },
        {
            "block_type": "entry",
            "bound_package_kind": "internship",
            "heading": "实习",
            "entry": {
                "title": "杭州拓端数据科技有限公司",
                "org": "杭州拓端数据科技有限公司",
                "role": "数据处理实习生",
                "date_range": "2026.07 - 至今",
                "bullets": ["实习做的事"],
            },
        },
    ]
}


class RepairIsCurrentTest(unittest.TestCase):
    def setUp(self) -> None:
        base = PROJECT / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name)
        os.environ["DATA_DIR"] = str(self.data_dir)
        db_mod.reset_paths_for_tests()
        db_mod.get_paths().ensure()
        conn = db_mod.get_conn()
        now = db_mod.utcnow_iso()
        conn.execute(
            "INSERT OR IGNORE INTO attachment (id, sha256, original_name, ext, mime, bytes, kind,"
            " privacy, created_at) VALUES ('att1', ?, 'zh.pdf', 'pdf', 'application/pdf', 10,"
            " 'resume_source', 'private', ?)",
            ("a" * 64, now),
        )
        conn.execute(
            "INSERT INTO import_job (id, attachment_id, status, parser, draft_json, created_at, updated_at)"
            " VALUES (?, 'att1', 'draft', 'pdf', ?, ?, ?)",
            ("ij1", json.dumps(ENTRY_DRAFT, ensure_ascii=False), now, now),
        )
        for package_id, title, start in (
            ("p1", "小象超市门店选址与订单量预测建模", "2026-03"),
            ("p2", "小象超市门店选址与订单量预测建模（副本）", "2026-03"),
            ("p3", "杭州拓端数据科技有限公司", "2026-07"),
            ("p4", "查无此经历的项目", "2025-01"),
        ):
            conn.execute(
                "INSERT INTO package (id, title, kind, start_date, end_date, is_current, status, source,"
                " tech_stack_json, tags_json, outcomes_json, evidence_json, created_at, updated_at)"
                " VALUES (?, ?, 'project', ?, NULL, 1, 'draft', 'authored', '[]', '[]', '[]', '[]', ?, ?)",
                (package_id, title, start, now, now),
            )
        conn.commit()

    def tearDown(self) -> None:
        db_mod.close_conn()
        os.environ.pop("DATA_DIR", None)
        db_mod.reset_paths_for_tests()

    def _classify(self) -> dict:
        conn = sqlite3.connect(self.data_dir / "app.db")
        conn.row_factory = sqlite3.Row
        try:
            return repair.classify(conn)
        finally:
            conn.close()

    def test_parse_end_date_variants(self) -> None:
        cases = {
            "2026.03 - 2026.04": ("2026-04", "ok"),
            "2024.9-2028.6": ("2028-06", "ok"),
            "09/2024 – 06/2028": ("2028-06", "ok"),
            "2026.07 - 至今": (None, "present"),
            "2026.07 - Present": (None, "present"),
            "": (None, "unparsed"),
            "不知道": (None, "unparsed"),
        }
        for raw, expected in cases.items():
            self.assertEqual(repair.parse_end_date(raw), expected, raw)

    def test_dry_run_lists_but_does_not_write(self) -> None:
        result = self._classify()
        self.assertEqual(result["affected_total"], 4)
        self.assertEqual({item["id"] for item in result["fixable"]}, {"p1", "p2"})
        self.assertEqual({item["id"] for item in result["possibly_legit"]}, {"p3"})
        self.assertEqual({item["id"] for item in result["manual"]}, {"p4"})
        for item in result["fixable"]:
            self.assertEqual(item["proposed_end_date"], "2026-04")
            self.assertEqual(item["evidence"], "2026.03 - 2026.04")

        # classify 是纯读：跑完数据库一个字节都不该变
        conn = db_mod.get_conn()
        rows = conn.execute("SELECT end_date, is_current FROM package ORDER BY id").fetchall()
        self.assertEqual([(row["end_date"], row["is_current"]) for row in rows], [(None, 1)] * 4)

    def test_apply_backfills_only_determinable_rows_and_snapshots(self) -> None:
        exit_code = repair.main(["--data-dir", str(self.data_dir), "--apply"])
        self.assertEqual(exit_code, 0)

        conn = db_mod.get_conn()
        rows = {
            row["id"]: (row["end_date"], row["is_current"])
            for row in conn.execute("SELECT id, end_date, is_current FROM package")
        }
        self.assertEqual(rows["p1"], ("2026-04", 0))
        self.assertEqual(rows["p2"], ("2026-04", 0))
        self.assertEqual(rows["p3"], (None, 1), "原文「至今」的行不许被改")
        self.assertEqual(rows["p4"], (None, 1), "反解不到的行不许被猜")
        self.assertEqual(
            len(list((self.data_dir / "backups").glob("app-*-pre-repair-is-current.db"))), 1
        )
        self.assertEqual(
            len(list((self.data_dir / "backups").glob("app-*-post-repair-is-current.db"))), 1
        )

    def test_conflicting_drafts_stay_manual(self) -> None:
        conn = db_mod.get_conn()
        conflicting = {
            "blocks": [
                {
                    "block_type": "entry",
                    "bound_package_kind": "project",
                    "entry": {"title": "查无此经历的项目", "date_range": "2025.01 - 2025.02"},
                },
                {
                    "block_type": "entry",
                    "bound_package_kind": "project",
                    "entry": {"title": "查无此经历的项目", "date_range": "2025.01 - 2025.05"},
                },
            ]
        }
        now = db_mod.utcnow_iso()
        conn.execute(
            "INSERT INTO import_job (id, attachment_id, status, parser, draft_json, created_at, updated_at)"
            " VALUES ('ij2', 'att1', 'draft', 'pdf', ?, ?, ?)",
            (json.dumps(conflicting, ensure_ascii=False), now, now),
        )
        conn.commit()
        result = self._classify()
        self.assertIn("p4", {item["id"] for item in result["manual"]})
        manual = next(item for item in result["manual"] if item["id"] == "p4")
        self.assertIn("矛盾", manual["reason"])
        self.assertEqual(sorted(manual["conflicts"]), ["2025-02", "2025-05"])

    PROBE_TITLE = "探测夹具项目标题"

    def _seed_probe_rows(self, count: int = 3) -> list[str]:
        conn = db_mod.get_conn()
        now = db_mod.utcnow_iso()
        ids = []
        for index in range(count):
            package_id = f"probe{index}"
            ids.append(package_id)
            conn.execute(
                "INSERT INTO package (id, title, kind, start_date, end_date, is_current, status, source,"
                " tags_json, tech_stack_json, outcomes_json, evidence_json, created_at, updated_at)"
                " VALUES (?, ?, 'project', '2026-03', NULL, 0, 'draft', 'authored', '[]', '[]', '[]', '[]', ?, ?)",
                (package_id, self.PROBE_TITLE + ("（副本）" if index else ""), now, now),
            )
        conn.commit()
        return ids

    def test_archive_probe_rows_is_reversible_and_keeps_fixture(self) -> None:
        ids = self._seed_probe_rows(3)
        repair.main(
            ["--data-dir", str(self.data_dir), "--archive-probe-rows", "--probe-title", self.PROBE_TITLE]
        )

        conn = db_mod.get_conn()
        rows = {
            row["id"]: dict(row)
            for row in conn.execute(
                "SELECT id, deleted_at, tags_json FROM package WHERE title LIKE ?",
                (self.PROBE_TITLE + "%",),
            )
        }
        kept_id = ids[0]
        self.assertIsNone(rows[kept_id]["deleted_at"], "最早一条要保留做夹具")
        self.assertIn(repair.FIXTURE_TAG, repair.load_tags(rows[kept_id]["tags_json"]))
        for package_id in ids[1:]:
            self.assertIsNotNone(rows[package_id]["deleted_at"], "其余行软删")
            self.assertIn(repair.PROBE_TAG, repair.load_tags(rows[package_id]["tags_json"]))
        # 物理行必须还在（软删 ≠ 删除）
        self.assertEqual(len(rows), 3)
        # 默认列表不再返回
        listing = self.client_listing()
        self.assertNotIn(ids[1], [item["id"] for item in listing])

        # --restore 反向恢复
        repair.main(["--data-dir", str(self.data_dir), "--restore"])
        conn2 = db_mod.get_conn()
        remaining = [
            row["id"]
            for row in conn2.execute("SELECT id FROM package WHERE deleted_at IS NOT NULL")
        ]
        self.assertEqual(remaining, [], "恢复后没有残留软删行")

    def client_listing(self) -> list[dict]:
        from app import create_app  # noqa: PLC0415

        client = create_app().test_client()
        return client.get("/api/v1/packages").get_json()["data"]["items"]

    def test_archive_skips_rows_referenced_by_build(self) -> None:
        ids = self._seed_probe_rows(2)
        conn = db_mod.get_conn()
        now = db_mod.utcnow_iso()
        conn.execute(
            "INSERT OR IGNORE INTO template (id, name, lang, source_kind, page_limit, created_at, updated_at)"
            " VALUES ('tplfix', '夹具模板', 'zh', 'builtin', 1, ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO resume_build (id, name, template_id, lang, status, naming_pattern, created_at, updated_at)"
            " VALUES ('b1', '夹具构建', 'tplfix', 'zh', 'draft', '{position}-{name}-{school}', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO build_selection (id, build_id, package_id, order_index, created_at)"
            " VALUES ('s1', 'b1', ?, 0, ?)",
            (ids[1], now),
        )
        conn.commit()
        probes = repair.find_probe_rows(conn, title_pattern=self.PROBE_TITLE)
        self.assertEqual({item["id"] for item in probes}, {ids[0]}, "被 build 引用的行不许归档")

    def test_report_markdown_lists_rows(self) -> None:
        target = self.data_dir / "report.md"
        repair.main(["--data-dir", str(self.data_dir), "--report", str(target)])
        text = target.read_text(encoding="utf-8")
        self.assertIn("Package 时间线异常行", text)
        self.assertIn("p1", text)
        self.assertIn("**NULL**", text)
        self.assertIn("不删任何行", text)


if __name__ == "__main__":
    unittest.main()
