"""日期区间识别：四位数字 + 横线**不是**日期（否则解析结果由 marker 决定）。

实测过的真实故障：条目标题 `示例数据科技ac934678 - 数据实习生 2026.07 - 2026.10` 被
`4678 -` 抢先匹配，`_loose_entry_start` 判定「日期不在行尾」→ 整行被吞进 bullets，
entry 的 title/org/date_range 全空，派生经历包因此被 `no_title` 跳过。
marker 里恰好出现 `9346`/`dd28` 这类四位数字才会触发，所以它只在部分测试轮次里红。
"""

from __future__ import annotations

import pytest

from app.services.extract import DATE_SPAN_RE
from app.services import extract, importer


@pytest.mark.parametrize(
    "line, expect_entry",
    [
        ("示例数据科技ac934678 - 数据实习生 2026.07 - 2026.10", True),
        ("示例数据科技acdd2858 - 数据实习生 2026.07 - 2026.10", True),
        ("示例数据科技ac12ab34 - 数据实习生 2026.07 - 2026.10", True),
        ("门店模型 - 队长 2024.9-2028.6", True),
        ("2024.9 - 至今 示例大学 学习委员", True),
        ("09/2024 – 06/2028 Example University", True),
    ],
)
def test_four_digit_marker_is_not_a_date(line, expect_entry):
    assert bool(DATE_SPAN_RE.search(line)) is expect_entry
    # 关键点：匹配必须落在行首或行尾的真实日期上，而不是 marker 里的四位数字
    match = DATE_SPAN_RE.search(line)
    assert match is not None
    assert match.start() <= 2 or match.end() >= len(line) - 2, (line, match.group(0), match.span())


def test_bullet_line_with_marker_still_parses_entry_head():
    text = (
        "实习经历\n示例数据科技有限公司ac934678 - 数据实习生 2026.07 - 2026.10\n"
        "● 负责报表自动化，月均节省 39.3 小时，批次 ac934678。\n"
    )
    draft = importer.parse_document(extract.extract(text.encode(), "txt"))
    entries = [block for block in draft["blocks"] if block["block_type"] == "entry"]
    assert entries, "至少要解析出一条 entry"
    entry = entries[0]["entry"]
    assert entry["org"].startswith("示例数据科技有限公司")
    assert entry["date_range"] == "2026.07 - 2026.10"
    assert entry["bullets"], "正文不能被吞进标题行"
