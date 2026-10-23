"""Package 标题/角色推导的回归测试（captain 工单：解析盲区 + 标题退化兜底）。

三类断言：

1. ``split_title_role`` 在白名单角色词上拆得干净，且不会把「数据分析」这类词误当角色；
2. 真库里 5 条派生包（来源真实简历）保持原样：title 与 role 各自独立；
3. 标题等于机构名时（实习/校园段常见）显示标题退化为「机构 · 角色」并保留 raw_title，
   且**导出的 PDF 条目头只出现一次机构名**（不能印两遍「公司 · 职位」）。
"""

from __future__ import annotations

import io
import unittest

from app.services import import_service, render


class SplitTitleRoleTest(unittest.TestCase):
    def test_suffix_role_is_split(self):
        self.assertEqual(import_service.split_title_role("门店选址与订单量预测 队长"), ("门店选址与订单量预测", "队长", False))
        self.assertEqual(import_service.split_title_role("品牌策划赛道 - 队长"), ("品牌策划赛道", "队长", False))
        self.assertEqual(import_service.split_title_role("增长实验 · 组员"), ("增长实验", "组员", False))

    def test_role_word_inside_title_is_not_split(self):
        title, role, ambiguous = import_service.split_title_role("队长会议纪要与复盘")
        self.assertEqual(role, "")
        self.assertTrue(ambiguous, "含角色词但拆不动时必须回报 ambiguous，让上层报警而不是静默")

    def test_english_role_is_split(self):
        self.assertEqual(import_service.split_title_role("Churn Analysis Team Member"), ("Churn Analysis", "Team Member", False))


class DeriveTitleRoleTest(unittest.TestCase):
    """真库 5 条派生包的实况（captain 直查 package WHERE source='imported'）。"""

    REAL_ROWS = [
        # (title, org, role, kind)  —— 真实简历里所有条目都带「 - 」分隔，importer 已切开
        ("赛车类游戏版本AB测试对照数据分析", None, "队长", "project"),
        ("小象超市门店选址与订单量预测模型（美团商业分析大赛）", None, "队员", "project"),
        ("2026年全国高校商业精英挑战赛品牌策划竞赛品牌策划赛道", None, "队长", "project"),
        ("示例大学", "示例大学", "学习委员", "activity"),
        ("杭州拓端数据科技有限公司", "杭州拓端数据科技有限公司", "数据处理实习生", "internship"),
    ]

    def test_real_rows_keep_title_and_role_separate(self):
        for title, org, role, _kind in self.REAL_ROWS:
            with self.subTest(title=title, role=role):
                got_title, got_role, warnings, _evidence = import_service.derive_title_role(
                    {"title": title, "org": org, "role": role}
                )
                self.assertEqual(got_role, role, "角色必须独立成列，不能留在标题里")
                self.assertEqual(warnings, [], "真实数据不该产生警告")
                if org and title == org:
                    # 标题退化兜底：显示标题 = 机构 · 角色
                    self.assertEqual(got_title, f"{org} · {role}")
                else:
                    self.assertEqual(got_title, title)

    def test_derived_title_keeps_raw_title_in_evidence(self):
        _title, _role, _warnings, evidence = import_service.derive_title_role(
            {"title": "示例大学", "org": "示例大学", "role": "学习委员"}
        )
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["kind"], "raw_title")
        self.assertEqual(evidence["value"], "示例大学")
        self.assertEqual(evidence["derived"], "示例大学 · 学习委员")

    def test_unsplittable_title_emits_warning(self):
        title, role, warnings, _evidence = import_service.derive_title_role(
            {"title": "队长会议纪要与复盘", "org": "某社团", "role": ""}
        )
        self.assertEqual(title, "队长会议纪要与复盘")
        self.assertEqual(role, "")
        self.assertEqual([w["code"] for w in warnings], ["TITLE_ROLE_UNSPLIT"])

    def test_no_role_at_all_is_silent(self):
        title, role, warnings, evidence = import_service.derive_title_role(
            {"title": "门店选址与订单量预测", "org": "美团", "role": ""}
        )
        self.assertEqual((title, role, warnings, evidence), ("门店选址与订单量预测", "", [], None))


class PdfNoDuplicateOrgTest(unittest.TestCase):
    """标题＝机构名时，PDF 条目头必须只出现一次机构名。"""

    def _ir(self, entry):
        return {
            "lang": "zh",
            "header": {"name": "张三", "contact_line": "13800138000"},
            "sections": [
                {
                    "kind": "experience",
                    "heading": "实习经历",
                    "entries": [entry],
                }
            ],
        }

    def _text(self, ir) -> str:
        result = render.render_pdf(ir, density="original")
        return "\n".join(line for line in str(render.extract_pdf_text(result.data)).splitlines() if line.strip())

    def test_derived_title_does_not_repeat_org(self):
        # 归档后 package.title = "杭州拓端数据科技有限公司 · 数据处理实习生"，org/role 仍是分列值
        text = self._text(
            self._ir(
                {
                    "title": "杭州拓端数据科技有限公司 · 数据处理实习生",
                    "org": "杭州拓端数据科技有限公司",
                    "role": "数据处理实习生",
                    "date": "2026.07 - 2026.10",
                    "bullets": ["把日处理时间从 8 小时降到 24 分钟。"],
                }
            )
        )
        head = [line for line in text.splitlines() if "杭州拓端" in line][0]
        self.assertEqual(head.count("杭州拓端数据科技有限公司"), 1, f"条目头重复印了机构名：{head}")
        self.assertIn("数据处理实习生", head)

    def test_plain_title_not_repeated_by_org(self):
        text = self._text(
            self._ir(
                {
                    "title": "示例大学",
                    "org": "示例大学",
                    "role": "学习委员",
                    "date": "2024.9 - 至今",
                    "bullets": ["担任班级学习委员。"],
                }
            )
        )
        head = [line for line in text.splitlines() if "示例大学" in line and "学习委员" in line][0]
        self.assertEqual(head.count("示例大学"), 1, f"条目头重复印了机构名：{head}")


if __name__ == "__main__":
    unittest.main()
