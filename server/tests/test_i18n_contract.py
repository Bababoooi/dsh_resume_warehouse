"""i18n 词表与契约的唯一真源校验。

契约 ``docs/API-CONTRACT.md §8.5.1`` 是结构词表与字段标签的**唯一真源**；
实现里的 ``i18n.py`` 只许照抄。这里解析文档表格逐字比对，双向都要绿：

* 文档里有的，实现必须一模一样（少了/写错 ⇒ FAIL）；
* 实现里有的，文档必须登记（自创译名 ⇒ FAIL）。
"""

from __future__ import annotations

import unittest
from pathlib import Path

from app.services import i18n

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "API-CONTRACT.md"


def _section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    stop = text.index(end, begin)
    return text[begin:stop]


def _rows(block: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        if not cells or set("".join(cells)) <= set("-: "):
            continue
        rows.append(cells)
    return rows


@unittest.skipUnless(CONTRACT.exists(), "缺少契约文档")
class HeadingTableTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = CONTRACT.read_text(encoding="utf-8")
        block = _section(self.text, "#### 8.5.1", "#### 8.5.2")
        # 8.5.1 里还有一张「字段标签与格式」表，结构词表只到它之前
        block = block.split("字段标签与格式")[0]
        rows = [row for row in _rows(block) if len(row) == 3]
        self.rows = [
            row for row in rows if not row[0].startswith("项") and row[0] != "block.kind"
        ]

    def test_every_documented_heading_matches_implementation(self) -> None:
        self.assertTrue(self.rows, "契约 §8.5.1 结构词表解析为空")
        for kind, zh, en in self.rows:
            if kind not in i18n.HEADING_BY_KIND:
                self.fail(f"契约登记了 {kind}，i18n.HEADING_BY_KIND 里没有")
            self.assertEqual(i18n.HEADING_BY_KIND[kind], (zh, en), f"{kind} 的译名与契约不一致")

    def test_no_extra_headings_in_implementation(self) -> None:
        documented = {row[0] for row in self.rows}
        extra = set(i18n.HEADING_BY_KIND) - documented
        self.assertFalse(extra, f"实现里有契约未登记的 kind：{sorted(extra)}")

    def test_label_values_match_contract(self) -> None:
        self.assertEqual(i18n.LABELS["available"]["en"], "Available")
        self.assertEqual(i18n.LABELS["gpa"], {"zh": "专业成绩", "en": "GPA"})
        self.assertEqual(i18n.LABELS["courses"], {"zh": "主修课程", "en": "Relevant Coursework"})
        block = _section(self.text, "字段标签与格式", "#### 8.5.2")
        self.assertIn("Relevant Coursework", block)
        self.assertIn("Available:", block)

    def test_labels_have_no_undocumented_keys(self) -> None:
        documented_zh = {"到岗时间", "专业成绩", "主修课程"}
        extra = {item["zh"] for item in i18n.LABELS.values()} - documented_zh
        self.assertFalse(extra, f"i18n.LABELS 出现契约表外的 key：{sorted(extra)}")

    def test_label_rendering_uses_ascii_colon(self) -> None:
        for key in ("available", "gpa", "courses"):
            self.assertNotIn("：", f"{i18n.LABELS[key]['en']}:")


class DateFormatTest(unittest.TestCase):
    def test_month_names_and_present(self) -> None:
        self.assertEqual(i18n.date_range_en("2026.03 - 2026.10"), "Mar 2026 – Oct 2026")
        self.assertEqual(i18n.date_range_en("2026.03 - 至今"), "Mar 2026 – Present")
        self.assertEqual(i18n.date_point_en("2024年9月"), "Sep 2024")

    def test_unparsable_returns_none(self) -> None:
        self.assertIsNone(i18n.date_range_en("去年夏天"))


if __name__ == "__main__":
    unittest.main()
