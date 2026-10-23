"""t5 真实验收：用 captain 人工标注的基准逐条判 `sample_zh.pdf` 的解析结果。

基准文件 `data/eval/expected_zh_v10.json` 与素材 `data/imports/*.pdf` 含真实 PII，
都在 `data/` 下（已 gitignore），仅本机使用、从不作为 LLM 输入。文件缺失时用例自动跳过，
因此在干净的克隆里 `unittest discover` 仍然全绿。

跑法：cd resume-warehouse && python -m unittest server.tests.test_import_zh_v10 -v
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

PROJECT = SERVER.parent
PDF_ZH = PROJECT / "data" / "imports" / "sample_zh.pdf"
PDF_EN = PROJECT / "data" / "imports" / "sample_en.pdf"
BASELINE = PROJECT / "data" / "eval" / "expected_zh_v10.json"

from app.services import extract, importer, photo  # noqa: E402


def load_baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def parse_pdf(path: Path):
    doc = extract.extract(path.read_bytes(), "pdf")
    draft = importer.parse_document(doc)
    return doc, draft


def draft_text(draft: dict) -> str:
    """把草稿里所有用户可见文本拼成一串，用于「逐字保真」类断言。"""
    chunks: list[str] = []
    for block in draft.get("blocks") or []:
        for key in ("heading", "preview_text"):
            if block.get(key):
                chunks.append(str(block[key]))
        chunks.extend(str(item) for item in block.get("text") or [])
        entry = block.get("entry") or {}
        for value in entry.values():
            if isinstance(value, str):
                chunks.append(value)
            elif isinstance(value, list):
                chunks.extend(str(item) for item in value)
        for slot in block.get("slots") or []:
            if slot.get("suggested_value"):
                chunks.append(str(slot["suggested_value"]))
    for row in draft.get("skills") or []:
        chunks.append(str(row.get("line") or ""))
    return "\n".join(chunks)


@unittest.skipUnless(PDF_ZH.exists(), f"缺少验收素材：{PDF_ZH}")
@unittest.skipUnless(BASELINE.exists(), f"缺少验收基准：{BASELINE}")
class ZhV10BaselineTest(unittest.TestCase):
    """6 项硬指标（captain 逐条判）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = load_baseline()
        cls.doc, cls.draft = parse_pdf(PDF_ZH)
        cls.text = draft_text(cls.draft)

    # ① 5 个 section
    def test_hard_1_all_five_sections_found(self) -> None:
        expected = {
            "教育背景": "education",
            "实习经历": "internship",
            "项目经历": "project",
            "校园活动": "campus",
            "职业技能": "skills",
        }
        found = self.draft["section_kinds"]
        headings = [b.get("heading") for b in self.draft["blocks"] if b["block_type"] in ("section", "skills")]
        missing = [kind for kind in expected.values() if kind not in found]
        self.assertEqual(missing, [], f"缺少章节：{missing}；实得 section_kinds={found}")
        for zh in expected:
            self.assertIn(zh, headings, f"章节标题未识别：{zh}")

    # ② entry 数逐一相等
    def test_hard_2_entry_counts_match_baseline(self) -> None:
        sections = self.baseline["sections_expected"]
        mismatches = []
        for item in sections:
            kind = item["bound_package_kind"]
            if item["block_type"] == "skills":
                continue  # 技能按行计，下面单独判
            want = item.get("entry_count", item.get("line_count"))
            got = self.draft["entry_counts"].get(kind)
            if got != want:
                mismatches.append(f"{kind}: 期望 {want} 实得 {got}")
        self.assertEqual(mismatches, [], "；".join(mismatches))
        skills = [s for s in sections if s["block_type"] == "skills"]
        if skills:
            want = skills[0]["line_count"]
            self.assertEqual(len(self.draft["skills"]), want)

    # ③ 数字零丢失（禁止润色）
    def test_hard_3_every_number_survives_verbatim(self) -> None:
        needed = list(dict.fromkeys(self.baseline["must_contain_numbers_verbatim"]))
        missing = [needle for needle in needed if needle not in self.text]
        self.assertEqual(missing, [], f"数字缺失 {len(missing)} 条：{missing}")

    # ④ 特殊字符保真
    def test_hard_4_special_characters_survive(self) -> None:
        needed = list(dict.fromkeys(self.baseline["must_survive_special_chars"]))
        missing = [needle for needle in needed if needle not in self.text]
        self.assertEqual(missing, [], f"特殊字符缺失：{missing}")

    # ⑤ 禁止降级
    def test_hard_5_no_cid_no_replacement_char(self) -> None:
        self.assertEqual(self.text.count("(cid:"), 0, "草稿里残留 (cid: 标记")
        self.assertEqual(self.text.count("\ufffd"), 0, "草稿里出现 U+FFFD 替换字符")
        self.assertEqual(self.doc.cid_count, 0)
        # 非空行数不得少于原件的 -2
        self.assertGreaterEqual(
            len([line for line in self.doc.lines if line.stripped]),
            self.baseline["text_chars"] // 40,
        )

    # ⑥ 照片抽取
    def test_hard_6_photo_extracted_with_expected_geometry(self) -> None:
        self.assertTrue(self.baseline["has_photo"])
        self.assertEqual(len(self.doc.images), 1, "应抽出 1 张内嵌图")
        info = photo.payload(self.doc)
        # 只做检测（没落盘）时 available=False 是刻意的：available=true 必须意味着能点开附件
        self.assertTrue(info["detected"])
        self.assertFalse(info["available"])
        self.assertFalse(info["unreadable"])
        self.assertEqual((info["width"], info["height"]), (266, 266))
        rendered = info["rendered"]
        self.assertAlmostEqual(rendered["w_pt"], 89.28, places=1)
        self.assertAlmostEqual(rendered["h_pt"], 89.28, places=1)
        png, width, height = photo.to_png(self.doc.images[0].data)
        self.assertEqual((width, height), (266, 266))
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_photo_geometry_uses_physical_page_coordinates(self) -> None:
        """CMP-20：距页顶 3.82pt（±1）。样张 MediaBox 下边 = 7.83，pdfplumber 的 top 先归一化过，
        不折算会得到 -4.01，从而把「照片位置」误判成错 7.83pt。"""
        rendered = photo.payload(self.doc)["rendered"]
        self.assertAlmostEqual(rendered["w_pt"], 89.28, delta=0.5)
        self.assertAlmostEqual(rendered["h_pt"], 89.28, delta=0.5)
        self.assertAlmostEqual(rendered["x0_pt"], 497.08, delta=0.5)
        self.assertAlmostEqual(rendered["top_offset_pt"], 3.82, delta=0.5)
        self.assertGreaterEqual(rendered["top_offset_pt"], 0.0, "距页顶不可能为负")
        # 距页右是边距，不是 x0：595.5 - 586.37 = 9.13
        self.assertAlmostEqual(rendered["right_gap_pt"], 9.13, delta=0.5)
        self.assertGreater(rendered["x0_pt"], 400, "x0 是照片左边的绝对坐标，别和边距混用")

    # 附加：结构与细节（不是硬门，但错了会明显影响可用性）
    def test_internship_and_project_bullet_counts(self) -> None:
        entries = {
            (block["bound_package_kind"], block["entry"]["date_range"]): block["entry"]
            for block in self.draft["blocks"]
            if block["block_type"] == "entry"
        }
        internship = [
            entry for (kind, _), entry in entries.items() if kind == "internship"
        ]
        self.assertEqual(len(internship), 1)
        self.assertEqual(len(internship[0]["bullets"]), 3, internship[0]["bullets"])
        projects = [entry for (kind, _), entry in entries.items() if kind == "project"]
        self.assertEqual(len(projects), 3)
        for project in projects:
            self.assertEqual(len(project["bullets"]), 2, project.get("raw_title"))

    def test_education_facts_and_course_list(self) -> None:
        education = next(
            block["entry"]
            for block in self.draft["blocks"]
            if block["block_type"] == "entry" and block["bound_package_kind"] == "education"
        )
        self.assertEqual(education["date_range"], "2024.9-2028.6")
        self.assertIn("示例大学", education["org"])
        facts = " ".join(education["facts"])
        for needle in ("GPA 3.56/4", "86.53/100", "CET4：562", "CET6:508"):
            self.assertIn(needle, facts)
        courses = len(re.findall(r"[(（]\s*\d{2,3}\s*[)）]", facts))
        self.assertGreaterEqual(courses, 7, f"主修课程少于 7 门（实得 {courses}）：{facts}")

    def test_skill_lines_stay_whole_sentences(self) -> None:
        rows = self.draft["skills"]
        self.assertEqual([row["category"] for row in rows], ["数据分析类", "基础办公类", "AI开发类"])
        for row in rows:
            self.assertIn(row["line"].strip(), self.text)
            self.assertNotIn(" | ", row["line"], "技能行不得拆成 tag 块")

    def test_campus_entry_has_honors_and_activities(self) -> None:
        campus = next(
            block["entry"]
            for block in self.draft["blocks"]
            if block["block_type"] == "entry" and block["bound_package_kind"] == "campus"
        )
        self.assertEqual(campus["role"], "学习委员")
        joined = " ".join(campus["bullets"])
        self.assertIn("曾获荣誉", joined)
        self.assertIn("主要活动", joined)


@unittest.skipUnless(PDF_EN.exists(), f"缺少验收素材：{PDF_EN}")
class EnPdfTest(unittest.TestCase):
    """英文简历：16 处 (cid:127) 必须清洗成 bullet，双页不得串栏。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.doc, cls.draft = parse_pdf(PDF_EN)
        cls.text = draft_text(cls.draft)

    def test_cid_markers_are_cleaned_and_counted(self) -> None:
        self.assertEqual(self.doc.cid_count, 16)
        self.assertEqual(self.text.count("(cid:"), 0)
        self.assertEqual(self.text.count("\ufffd"), 0)
        warnings = {item["code"]: item for item in self.draft["warnings"]}
        self.assertIn("CID_GLYPH_MISSING", warnings)
        self.assertEqual(warnings["CID_GLYPH_MISSING"]["count"], 16)

    def test_two_pages_do_not_cross_columns(self) -> None:
        self.assertEqual(self.doc.pages, 2)
        # 第 2 页的校园 bullet 必须挂在校园活动条目下，而不是混进项目经历
        campus = next(
            block["entry"]
            for block in self.draft["blocks"]
            if block["block_type"] == "entry" and block["bound_package_kind"] == "campus"
        )
        self.assertGreaterEqual(len(campus["bullets"]), 4)
        self.assertEqual(len(self.doc.images), 1)
        photo_info = photo.payload(self.doc)
        self.assertTrue(photo_info["detected"])
        self.assertFalse(photo_info["unreadable"])

    def test_all_projects_have_title_role_and_date(self) -> None:
        projects = [
            block["entry"]
            for block in self.draft["blocks"]
            if block["block_type"] == "entry" and block["bound_package_kind"] == "project"
        ]
        self.assertEqual(len(projects), 4)
        for project in projects:
            self.assertTrue(project["title"], project)
            self.assertTrue(project["role"], project)
            self.assertTrue(project["date_range"], project)


if __name__ == "__main__":
    unittest.main()
