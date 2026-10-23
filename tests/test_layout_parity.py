"""页眉白名单与「预览＝导出」的一致性回归。

两条真缺陷的看门狗：

1. **页眉重复教育信息**：``education_line`` 一度在页眉印「本科 | 管理科学（商业数据分析） | 2028」，
   同一信息在教育段又出现一次。契约 §8.6 白名单只允许 name / phone / email / available_note，
   §8.6.1 要求 ``education_line`` 字段**禁止存在**。
2. **所见非所得**：HTML 预览曾写死 10.5pt/1.62，而 PDF 是 11.0pt/1.15 —— 用户在预览里调版式，
   下 PDF 却不一致。现在两边都从 ``DENSITY``/``LADDER`` 派生。
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from app.services import compose, render

SERVER = Path(__file__).resolve().parents[1]
IR = {
    "lang": "zh",
    "header": {"name": "张三", "contact_line": "13800138000 | a@b.com", "available": "2027年1月下旬"},
    "sections": [
        {
            "kind": "education",
            "heading": "教育背景",
            "entries": [{"title": "示例大学", "date": "2024.9 - 2028.6", "facts": ["专业成绩：GPA 3.56/4"]}],
            "skills": [],
        }
    ],
    "warnings": [],
}


class HeaderWhitelistTest(unittest.TestCase):
    def test_education_line_is_gone_from_code(self):
        offenders = []
        for path in (SERVER / "app").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "education_line" in text:
                offenders.append(str(path.relative_to(SERVER)))
        self.assertEqual(offenders, [], f"education_line 必须彻底删除，仍在：{offenders}")

    def test_pdf_header_has_only_name_contact_available(self):
        result = render.render_pdf(IR, density="original")
        head = "\n".join(str(render.extract_pdf_text(result.data)).splitlines()[:4])
        self.assertIn("张三", head)
        self.assertIn("13800138000", head)
        self.assertIn("2027年1月下旬", head)
        for banned in ("本科", "管理科学（商业数据分析）", "2028"):
            self.assertNotIn(banned, head, f"页眉不许再印教育信息：{banned}")

    def test_iter_texts_matches_rendered_header(self):
        texts = compose.iter_texts(IR)
        self.assertIn("张三", texts)
        self.assertNotIn("本科 | 管理科学（商业数据分析） | 2028", " ".join(texts))


class PreviewMatchesExportTest(unittest.TestCase):
    def test_html_body_size_comes_from_ladder(self):
        html = render.render_html(IR)
        body_pt, ratio = render.LADDER[0]
        leading = round(body_pt * ratio, 2)
        style = html.split("<style>")[1].split("</style>")[0]
        self.assertIn(f"li{{font-size:{body_pt}pt;line-height:{leading}pt", style)
        self.assertIn(f".entry-sub{{font-size:{body_pt}pt", style)
        self.assertNotIn("font-size:10.5pt", style, "预览不许保留写死的小字号")

    def test_html_margins_and_photo_from_constants(self):
        style = render.render_html(IR).split("<style>")[1].split("</style>")[0]
        m = render.DENSITY["original"]
        self.assertIn(f"padding:{m['top']}pt {m['right']}pt {m['bottom']}pt {m['left']}pt", style)
        self.assertIn(f"top:{render.PHOTO['top']}pt;right:{render.PHOTO['right']}pt", style)
        self.assertIn(f"width:{render.PHOTO['size']}pt", style)

    def test_html_has_no_external_reference(self):
        html = render.render_html(IR)
        self.assertIsNone(re.search(r"https?://(?!127\.0\.0\.1)", html))
        self.assertNotIn("<script", html)


if __name__ == "__main__":
    unittest.main()
