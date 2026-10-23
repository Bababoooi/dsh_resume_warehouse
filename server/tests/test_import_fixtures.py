"""t5 导入链路的回归测试：MD / TXT / DOCX 三种格式 + 提交模板 + 草稿编辑 + 模板接口。

全部使用 `server/tests/fixtures/` 下的自造脱敏样例（张三 / 示例大学），不触碰用户真实简历。
跑法：cd resume-warehouse && python -m unittest discover -s server/tests -v
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

from app import create_app  # noqa: E402
from app import db as db_mod  # noqa: E402
from app.repos import TemplateRepo  # noqa: E402

from app.services import importer as importer_mod  # noqa: E402
from app.services import import_service  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: sample_zh.docx 不入库（.gitignore 排除 *.docx），测试时用 python-docx 现造
DOCX_SECTIONS = (
    ("教育背景", [
        "2026.9-2030.6 示例大学-信息管理学院 信息管理与信息系统 本科",
        "专业成绩：GPA 3.65/4 89.30/100 CET4：588 CET6:540",
        "主修课程：管理信息系统(94)、数据结构（Python）(92)、数据库系统原理（SQL）(90)、统计学(89)、运筹学(88)等。",
    ]),
    ("实习经历", [
        "示例信息技术有限公司 - 产品运营实习生 2028.07 - 2028.10",
        "负责 15 万条用户反馈的分类标注，搭建 6 类标签体系，标注一致性提升到 94.3%。",
        "用 PM₂.₅ 科普专题做 A/B 测试，专题页点击率提升 11.2%（p=0.024），沉淀 1 份运营 SOP。",
    ]),
    ("项目经历", [
        "校园知识库检索增强问答 - 队长 2028.03 - 2028.05",
        "基于 3421 篇校内文档构建检索增强问答，答案命中率 82.5%，平均响应 1.4 秒。",
        "设计 Ridge 与 K-means 组合的排序策略，人工评测满意度提升 9.1%。",
    ]),
    ("校园活动", [
        "2026.9 - 至今 示例大学 学习委员",
        "曾获荣誉：2027 年院级三好学生",
        "主要活动：组织 5 场读书会，累计参与 168 人次。",
    ]),
    ("职业技能", [
        "数据分析类：掌握 Python、SQL，熟悉 Tableau 可视化",
        "基础办公类：熟练使用 Excel 数据透视表与 VLOOKUP 函数",
        "AI开发类：可以使用大模型接口完成文本分类与摘要",
    ]),
)


def build_docx() -> bytes:
    """现造一份脱敏 DOCX（标题用 Heading 样式，方便解析器用样式判别章节）。"""
    from docx import Document

    document = Document()
    document.add_paragraph("李四")
    document.add_paragraph("示例大学 · 信息管理学院 · 本科 2030 届 ｜ 到岗时间：2029 年 7 月")
    document.add_paragraph("手机号码：13900139000 ｜ 邮箱：lisi@example.com")
    for heading, paragraphs in DOCX_SECTIONS:
        document.add_heading(heading, level=1)
        for text in paragraphs:
            document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class ImportAppTest(unittest.TestCase):
    """每个用例一个独立 DATA_DIR + Flask test client。"""

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
    def upload(self, filename: str, payload: bytes, field: str = "file"):
        return self.client.post(
            "/api/v1/imports",
            data={field: (io.BytesIO(payload), filename)},
            content_type="multipart/form-data",
        )

    def upload_fixture(self, name: str):
        return self.upload(name, (FIXTURES / name).read_bytes())

    def paste(self, text: str, **extra):
        body = {"text": text, "filename": "pasted.txt"}
        body.update(extra)
        return self.client.post("/api/v1/imports", json=body)

    def data_of(self, response):
        self.assertIn(response.status_code, (200, 201), response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"], payload)
        return payload["data"]

    def error_of(self, response):
        payload = response.get_json()
        self.assertFalse(payload["ok"], payload)
        return payload["error"]

    def blocks_by_kind(self, data, block_type):
        return [b for b in data["blocks"] if b["block_type"] == block_type]

    # -- 三种格式 -------------------------------------------------------
    def test_markdown_import_builds_five_sections(self) -> None:
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        self.assertEqual(data["parser"], "md")
        self.assertEqual(data["status"], "draft")
        self.assertEqual(
            data["section_kinds"], ["education", "internship", "project", "campus", "skills"]
        )
        self.assertEqual(data["entry_counts"]["project"], 1)
        header = self.blocks_by_kind(data, "header")
        self.assertEqual(len(header), 1)
        self.assertTrue(header[0]["slots"])

    def test_markdown_keeps_numbers_and_special_chars(self) -> None:
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        blob = str(data["blocks"]) + str(data["skills"])
        for needle in ("3.72/4", "90.10/100", "601", "552", "12 万", "p=0.031", "6820"):
            self.assertIn(needle, blob, f"数字丢失：{needle}")
        for needle in ("PM₂.₅", "K-means", "Ridge", "CET4：", "（Python）", "（SQL）"):
            self.assertIn(needle, blob, f"特殊字符丢失：{needle}")

    def test_markdown_skills_stay_whole_sentences(self) -> None:
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        rows = data["skills"]
        self.assertEqual(len(rows), 3)
        self.assertEqual([r["category"] for r in rows], ["数据分析类", "基础办公类", "AI开发类"])
        for row in rows:
            self.assertTrue(row["line"].startswith(row["category"] + "："))
            self.assertTrue(row["tokens"], f"{row['category']} 未派生索引 token")

    def test_txt_import_parses_english_sections(self) -> None:
        data = self.data_of(self.upload_fixture("sample_en.txt"))
        self.assertEqual(data["parser"], "txt")
        self.assertIn("education", data["section_kinds"])
        self.assertIn("skills", data["section_kinds"])
        self.assertNotIn("(cid:", str(data["blocks"]))

    def test_docx_import_parses_headings_and_bullets(self) -> None:
        data = self.data_of(self.upload("sample_zh.docx", build_docx()))
        self.assertEqual(data["parser"], "docx")
        self.assertEqual(len(data["section_kinds"]), 5)
        self.assertEqual(data["entry_counts"]["internship"], 1)
        self.assertEqual(data["entry_counts"]["skills"], 3)

    def test_pasted_text_is_accepted_as_job(self) -> None:
        text = (FIXTURES / "sample_en.txt").read_text(encoding="utf-8")
        data = self.data_of(self.paste(text))
        self.assertEqual(data["parser"], "txt")
        self.assertTrue(data["blocks"])

    # -- 失败路径 -------------------------------------------------------
    def test_unsupported_extension_is_rejected(self) -> None:
        response = self.upload("resume.exe", b"MZ\x90\x00binary")
        self.assertEqual(response.status_code, 415)
        self.assertEqual(self.error_of(response)["code"], "UNSUPPORTED_MEDIA_TYPE")

    def test_extension_mismatch_with_magic_bytes(self) -> None:
        response = self.upload("resume.pdf", (FIXTURES / "sample_zh.md").read_bytes())
        self.assertEqual(response.status_code, 415)

    def test_scanned_pdf_without_text_layer_returns_422(self) -> None:
        # 只有 magic bytes 的“扫描件”：抽不到文本层
        response = self.upload("scan.pdf", b"%PDF-1.4\n%%EOF\n")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.error_of(response)["code"], "IMPORT_NO_TEXT_LAYER")

    def test_too_short_paste_returns_422(self) -> None:
        response = self.paste("太短")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.error_of(response)["code"], "IMPORT_NO_TEXT_LAYER")

    def test_missing_import_returns_404(self) -> None:
        response = self.client.get("/api/v1/imports/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.error_of(response)["code"], "NOT_FOUND")

    # -- 草稿编辑与提交 --------------------------------------------------
    def test_draft_can_be_edited_before_commit(self) -> None:
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        import_id = data["import_id"]
        blocks = data["blocks"]
        header = next(b for b in blocks if b["block_type"] == "header")
        header["heading"] = "张三（已编辑）"
        response = self.client.put(f"/api/v1/imports/{import_id}/draft", json={"blocks": blocks})
        updated = self.data_of(response)
        self.assertEqual(updated["blocks"][0]["heading"], "张三（已编辑）")
        # 提交时用的是编辑后的草稿
        commit = self.data_of(
            self.client.post(
                f"/api/v1/imports/{import_id}/commit",
                json={"template_name": "编辑后模板", "lang": "zh"},
            )
        )
        block = next(
            b for b in commit["template"]["blocks"] if b["block_type"] == "header"
        )
        self.assertEqual(block["heading"], "张三（已编辑）")

    def test_commit_creates_default_template_with_blocks_and_slots(self) -> None:
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        commit = self.data_of(
            self.client.post(
                f"/api/v1/imports/{data['import_id']}/commit",
                json={"template_name": "示例模板", "lang": "zh", "set_default": True},
            )
        )
        self.assertTrue(commit["template"]["is_default"])
        template = self.client.get(f"/api/v1/templates/{commit['template_id']}").get_json()["data"]
        self.assertEqual(template["lang"], "zh")
        self.assertEqual(template["source_kind"], "imported_md")
        self.assertEqual(len(template["blocks"]), len(data["blocks"]))
        kinds = {b["block_type"] for b in template["blocks"]}
        self.assertTrue({"header", "section", "entry", "skills"} <= kinds)
        slots = [s for b in template["blocks"] for s in (b.get("slots") or [])]
        self.assertGreaterEqual(len(slots), 10)
        keys = {s["slot_key"] for s in slots}
        self.assertIn("candidate.name", keys)
        self.assertIn("entry.date_range", keys)
        # 板块必须带 schema 允许的 bound_package_kind
        section_kinds = {b["bound_package_kind"] for b in template["blocks"] if b["block_type"] == "section"}
        self.assertEqual(section_kinds, {"education", "internship", "project", "activity"})

    def test_commit_twice_returns_conflict(self) -> None:
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        self.client.post(
            f"/api/v1/imports/{data['import_id']}/commit", json={"template_name": "第一次"}
        )
        second = self.client.post(
            f"/api/v1/imports/{data['import_id']}/commit", json={"template_name": "第二次"}
        )
        self.assertEqual(second.status_code, 409)
        self.assertEqual(self.error_of(second)["code"], "CONFLICT")

    def test_only_one_default_template_exists(self) -> None:
        first = self.data_of(self.upload_fixture("sample_zh.md"))
        second = self.data_of(self.upload_fixture("sample_en.txt"))
        t1 = self.data_of(
            self.client.post(
                f"/api/v1/imports/{first['import_id']}/commit",
                json={"template_name": "中文", "lang": "zh", "set_default": True},
            )
        )
        t2 = self.data_of(
            self.client.post(
                f"/api/v1/imports/{second['import_id']}/commit",
                json={"template_name": "英文", "lang": "en", "set_default": True},
            )
        )
        repo = TemplateRepo(db_mod.get_conn())
        self.assertFalse(repo.get(t1["template_id"])["is_default"])
        self.assertTrue(repo.get(t2["template_id"])["is_default"])

    def test_export_draft_writes_both_artifacts(self) -> None:
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        files = self.data_of(
            self.client.post(f"/api/v1/imports/{data['import_id']}/export-draft")
        )
        for key in ("json", "md"):
            rel = files[key]["path"]
            self.assertTrue(rel.startswith("exports/import_draft_"), rel)
            path = db_mod.get_paths().root / rel
            self.assertTrue(path.exists(), f"未落盘：{path}")
            self.assertGreater(path.stat().st_size, 0)
        md = (db_mod.get_paths().root / files["md"]["path"]).read_text(encoding="utf-8")
        self.assertIn("教育背景", md)

    # -- 模板接口 -------------------------------------------------------
    def test_templates_endpoint_filters_by_lang(self) -> None:
        zh = self.data_of(self.upload_fixture("sample_zh.md"))
        en = self.data_of(self.upload_fixture("sample_en.txt"))
        self.client.post(
            f"/api/v1/imports/{zh['import_id']}/commit", json={"template_name": "中文", "lang": "zh"}
        )
        self.client.post(
            f"/api/v1/imports/{en['import_id']}/commit", json={"template_name": "英文", "lang": "en"}
        )
        zh_list = self.data_of(self.client.get("/api/v1/templates?lang=zh"))
        en_list = self.data_of(self.client.get("/api/v1/templates?lang=en"))
        self.assertEqual([i["name"] for i in zh_list["items"]], ["中文"])
        self.assertEqual([i["name"] for i in en_list["items"]], ["英文"])

    # -- captain P1/P2：模板默认解析 + 导入去重/草稿修剪 ----------------
    def test_first_commit_becomes_default(self) -> None:
        """P1 规则 A：全局还没有 default 时，第一个 commit 出来的模板自动当默认。"""
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        res = self.client.post(f"/api/v1/imports/{data['import_id']}/commit", json={"template_name": "首个"})
        committed = self.data_of(res)
        template = self.data_of(self.client.get(f"/api/v1/templates/{committed['template_id']}"))
        self.assertTrue(template["is_default"])
        default = self.data_of(self.client.get("/api/v1/templates/default"))
        self.assertEqual(default["id"], template["id"])
        self.assertFalse(default["resolved"], "这是显式默认，不该标成兜底")

    def test_templates_envelope_exposes_resolved_default(self) -> None:
        """P1 规则 B：即便全部 is_default=0，GET /templates 也要给出确定的模板。"""
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        committed = self.data_of(
            self.client.post(f"/api/v1/imports/{data['import_id']}/commit", json={"template_name": "唯一"})
        )
        template = self.data_of(self.client.get(f"/api/v1/templates/{committed['template_id']}"))
        # 模拟历史数据：把 is_default 清掉
        from app.repos import TemplateRepo  # noqa: PLC0415

        TemplateRepo().update(template["id"], {"is_default": False})
        listed = self.data_of(self.client.get("/api/v1/templates"))
        self.assertIsNotNone(listed["resolved_default"], "t8 不能因为没 default 就 500")
        self.assertEqual(listed["resolved_default"]["id"], template["id"])
        fallback = self.data_of(self.client.get("/api/v1/templates/default"))
        self.assertTrue(fallback["resolved"])

    def test_same_file_is_not_stored_twice(self) -> None:
        """P2 去重：同一份文件重复上传返回同一条草稿，不再多存一份 draft_json。"""
        first = self.data_of(self.upload_fixture("sample_zh.md"))
        second = self.data_of(self.upload_fixture("sample_zh.md"))
        self.assertTrue(second["reused"], "重复上传应标记 reused")
        self.assertEqual(second["import_id"], first["import_id"])
        rows = db_mod.get_conn().execute("SELECT COUNT(*) FROM import_job").fetchone()[0]
        self.assertEqual(rows, 1, "重复上传不得新增 import_job 行")

    def test_draft_pruning_keeps_recent_only(self) -> None:
        """P2 清理：未提交草稿超过上限时清理最旧的，并给出 IMPORT_DRAFT_PRUNED 提示。"""
        from app.services import import_service  # noqa: PLC0415

        original = import_service.MAX_DRAFT_KEEP
        import_service.MAX_DRAFT_KEEP = 1
        self.addCleanup(setattr, import_service, "MAX_DRAFT_KEEP", original)
        self.data_of(self.upload_fixture("sample_zh.md"))
        self.data_of(self.upload_fixture("sample_en.txt"))
        data = self.data_of(self.upload_fixture("sample.docx"))
        warnings = {w["code"]: w for w in data["warnings"]}
        self.assertIn("IMPORT_DRAFT_PRUNED", warnings)
        self.assertGreaterEqual(warnings["IMPORT_DRAFT_PRUNED"]["count"], 1)
        drafts = db_mod.get_conn().execute(
            "SELECT COUNT(*) FROM import_job WHERE status = 'draft'"
        ).fetchone()[0]
        self.assertEqual(drafts, 1)

    def test_default_template_404_before_any_import(self) -> None:
        response = self.client.get("/api/v1/templates/default")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.error_of(response)["code"], "NOT_FOUND")

    def test_import_detail_matches_draft(self) -> None:
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        detail = self.data_of(self.client.get(f"/api/v1/imports/{data['import_id']}"))
        self.assertEqual(detail["import_id"], data["import_id"])
        self.assertEqual(len(detail["blocks"]), len(data["blocks"]))
        listed = self.data_of(self.client.get("/api/v1/imports"))
        self.assertEqual(listed["items"][0]["import_id"], data["import_id"])

    # -- 生成物不变式 ----------------------------------------------------
    def test_draft_never_contains_cid_or_replacement_char(self) -> None:
        for name in ("sample_zh.md", "sample_en.txt"):
            data = self.data_of(self.upload_fixture(name))
            blob = str(data)
            self.assertNotIn("(cid:", blob, name)
            self.assertNotIn("\ufffd", blob, name)

    # -- captain 复查（t5 第一轮独立验证）要求的三处自洽性 ------------------
    def test_sections_summary_heading_matches_blocks(self) -> None:
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        blocks_headings = {}
        for block in data["blocks"]:
            if block["block_type"] == "section":
                blocks_headings[block["bound_package_kind"]] = block["heading"]
            elif block["block_type"] == "skills":
                blocks_headings["skills"] = block["heading"]
        for summary in data["sections"]:
            self.assertTrue(summary["heading"], f"摘要缺 heading：{summary}")
            self.assertEqual(summary["heading"], blocks_headings[summary["kind"]])
            self.assertEqual(summary["block_type"], "skills" if summary["kind"] == "skills" else "section")
            key = "skills" if summary["kind"] == "skills" else summary["kind"]
            self.assertEqual(summary["entry_count"], data["entry_counts"][key])

    def test_quality_flag_is_not_misleading(self) -> None:
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        quality = data["draft"]["quality"]
        self.assertIn("numbers_second_pass", quality)
        self.assertNotIn("numbers_lost_unknown", quality)

    def test_education_facts_render_verbatim_like_bullets(self) -> None:
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        education = next(
            b["entry"] for b in data["blocks"]
            if b["block_type"] == "entry" and b["bound_package_kind"] == "education"
        )
        self.assertTrue(education["facts"], "教育段没有 facts")
        self.assertEqual(education["bullets"], [])
        markdown = import_service.as_markdown(data["draft"])
        for fact in education["facts"]:
            self.assertIn(fact, markdown, f"facts 未逐字渲染：{fact}")
        lines = importer_mod.entry_lines(education)
        self.assertEqual(lines, list(education["facts"]))

    def test_header_never_reaches_prompt_blocks(self) -> None:
        from app.services import import_service

        data = self.data_of(self.upload_fixture("sample_zh.md"))
        safe = import_service.blocks_for_prompt(data["draft"])
        self.assertNotIn("header", {b["block_type"] for b in safe})
        blob = str(safe)
        for secret in ("13800138000", "zhangsan@example.com", "张三"):
            self.assertNotIn(secret, blob, f"抬头信息泄漏进 prompt 块：{secret}")
        # 经历/项目文本仍完整保留
        self.assertIn("校园二手交易平台成交预测", blob)

    def test_photo_absent_for_text_sources(self) -> None:
        data = self.data_of(self.upload_fixture("sample_zh.md"))
        self.assertFalse(data["extracted_photo"]["available"])
        self.assertEqual(data["extracted_photo"]["source"], "none")


if __name__ == "__main__":
    unittest.main()
