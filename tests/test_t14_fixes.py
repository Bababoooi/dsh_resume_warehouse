"""t14 修掉的五个真缺陷的回归钉子。

每一条都对应一次「界面看起来正常、数据其实是错的」事故，所以断言打在**数据层事实**上，
不打在返回值文案上。
"""

from __future__ import annotations

import json

from app.services import importer


def test_bare_four_digits_are_not_dates():
    """`示例数据科技7193a0 - 数据实习生 2026.07 - 2026.10` 曾被 `7193` 抢先命中，
    整行被当正文吞掉，条目标题/单位/日期全丢。"""
    from app.services.importer import DATE_SPAN_RE

    assert DATE_SPAN_RE.search("示例数据科技有限公司7193a0 - 数据实习生 2026.07 - 2026.10").group(0) == (
        "2026.07 - 2026.10"
    )
    assert DATE_SPAN_RE.search("2024.9-2028.6 示例大学").group(0).strip() == "2024.9-2028.6"
    assert DATE_SPAN_RE.search("09/2024 – 06/2028").group(0) == "09/2024 – 06/2028"
    assert DATE_SPAN_RE.search("2026.07 - 至今").group(0) == "2026.07 - 至今"
    assert DATE_SPAN_RE.search("2026 年 7 月 - 2026.10").group(0) == "2026 年 7 月 - 2026.10"


def test_marker_suffix_does_not_break_entry_head():
    """同一行带随机后缀时仍要认成条目标题（曾经的解析盲区）。"""
    doc = importer.parse_document(_doc("示例数据科技有限公司9f3a1c - 数据实习生 2026.07 - 2026.10"))
    entries = [b for b in doc["blocks"] if b.get("block_type") == "entry"]
    assert entries, doc["blocks"]
    entry = entries[0]["entry"]
    assert entry.get("org") == "示例数据科技有限公司9f3a1c", entry
    assert entry.get("date_range") == "2026.07 - 2026.10", entry


def _doc(entry_line: str):
    from app.services.extract import DocLine, ExtractedDoc

    lines = [
        DocLine("张三", page=1, top=10, x0=10, size=20, bold=True),
        DocLine("实习经历", page=1, top=40, x0=10, size=13, bold=True),
        DocLine(entry_line, page=1, top=60, x0=10, size=11, bold=True),
        DocLine("负责报表自动化，月均节省 39.3 小时。", page=1, top=72, x0=30, size=11),
    ]
    return ExtractedDoc(parser="pdf", pages=1, lines=lines, images=[], warnings=[], cid_count=0, raw_text="")


def test_content_key_ignores_block_temp_id(client, data_dir):
    """派生包的幂等键必须是「内容指纹」：两份不同简历的第 3 个块都叫 tb-s3-e1，
    若拿 temp_id 去重，第二份简历的经历会一条都进不了仓库。"""
    from app.services.import_service import _content_key

    first = _content_key("门店模型", "2026-03", "2026-04", ["覆盖 6527 家门店"])
    second = _content_key("门店模型", "2026-03", "2026-04", ["覆盖 6527 家门店"])
    other = _content_key("门店模型", "2026-03", "2026-04", ["覆盖 100 家门店"])
    assert first == second
    assert first != other


def test_profile_extra_keeps_education_range(client):
    """commit 的 extra 只能合并：整份覆盖会丢掉 education_date_range，
    导出教育段就只剩 grad_year（用户看到「2028」而不是「2024.9 - 2028.6」）。"""
    text = (
        "李四\n13800138001\n教育背景\n2024.9-2028.6 示例大学-信息学院 计算机科学与技术 本科\n"
        "实习经历\n示例数据科技有限公司 - 数据实习生 2026.07 - 2026.10\n● 负责报表自动化。\n"
    )
    import_id = client.post(
        "/api/v1/imports", json={"text": text, "filename": "extra.txt", "lang": "zh"}
    ).get_json()["data"]["import_id"]
    client.post(f"/api/v1/imports/{import_id}/commit", json={"template_name": "extra", "lang": "zh"})
    profile = client.get("/api/v1/profile").get_json()["data"]
    assert profile["extra"].get("education_date_range") == "2024.9-2028.6", profile["extra"]


def test_candidate_profile_has_seven_keys_even_when_empty(client):
    """jd_analyze 的档案段七项必须都在：缺 available_date 时模型只能猜「没填」。"""
    from app.services.consent import ConsentService

    service = ConsentService()
    brief = service.profile.llm_brief()
    for key in ("school", "degree", "major", "grad_year", "city", "available_date"):
        assert key in brief, (key, brief)
    rendered = json.dumps({k: (v if v not in ("", None) else None) for k, v in brief.items()}, ensure_ascii=False)
    assert "available_date" in rendered
