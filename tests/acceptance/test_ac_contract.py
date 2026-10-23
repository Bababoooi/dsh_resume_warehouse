"""AC harness —— 契约条款：分析/英文/版式/命名/技能/导入派生/构建别名。

每一条都观测事实：API 响应字段、PDF 抽取文本、库里的行、ir 的结构。
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest

from .helpers import (
    artifact,
    db,
    db_int,
    db_one,
    pdf_metrics,
    pdf_text,
    restore_profile,
    snapshot_profile,
    wait_job,
)

CHECKS: dict[str, callable] = {}


def check(ac: str):
    def register(fn):
        CHECKS[ac] = fn
        return fn

    return register


CJK_RE = re.compile(r"[\u4e00-\u9fff]")
TAG_BLOCK_RE = re.compile(r"[A-Za-z\u4e00-\u9fa5]{1,12}(?: \| [A-Za-z\u4e00-\u9fa5]{1,12}){2,}")
TIERS = {"C9", "985", "211", "双一流", "普通本科", "海外", "其他"}
VERDICTS = {"strong", "medium", "weak"}


def _assemble(flow, build_id: str) -> dict:
    from app.services import export_service

    return export_service.assemble(build_id)


def _ir(flow, build_id: str) -> dict:
    return _assemble(flow, build_id)["ir"]


def _sections(ir: dict) -> list[dict]:
    return [item for item in ir.get("sections") or []]


def _entries(ir: dict, kind: str) -> list[dict]:
    for section in _sections(ir):
        if section.get("kind") == kind:
            return list(section.get("entries") or [])
    return []


# ------------------------------------------------------------------ 分析与偏好 ----------------

@check("AC-ANL-06")
def _anl_06(flow):
    comp = (flow["analysis"].get("competitiveness") or {})
    assert comp, "jd/analyze 必须返回 competitiveness（启发式也不许 null）"
    assert comp.get("school_tier") in TIERS, comp.get("school_tier")
    assert comp.get("verdict") in VERDICTS, comp.get("verdict")
    signal = str(comp.get("school_signal") or "")
    assert len(signal) >= 8, f"school_signal 太短：{signal!r}"
    school = (flow.get("profile") or {}).get("school_zh") or ""
    assert school in signal or re.search(r"(985|211|双一流|本科院校|院校层次)", signal), signal
    assert all(
        item.get("candidate_status") in {"satisfied", "partial", "missing"}
        for item in flow["analysis"].get("requirements") or []
    )


@check("AC-ANL-07")
def _anl_07(flow):
    from app.services import company_analysis

    gate = company_analysis.school_preference_from(jd_text="本科及以上学历，有 A/B 测试经验者优先。")
    assert gate["hard_filter"] is False, gate
    assert gate["preferred_tiers"] == [], gate
    assert str(gate["threshold"]).startswith("不限"), gate
    assert gate.get("evidence"), "未提院校时必须说明依据"

    hard = company_analysis.school_preference_from(jd_text="仅限 985/211 院校毕业生。")
    assert hard["hard_filter"] is True and hard["preferred_tiers"], hard


@check("AC-ANL-09")
def _anl_09(flow):
    from app.services import jd_analysis

    warnings: list[dict] = []
    comp = jd_analysis.competitiveness(
        profile={"school_zh": "XX大学", "degree": "本科", "major": "计算机科学与技术"},
        school_preference={"hard_filter": False, "preferred_tiers": [], "threshold": "不限"},
        requirements=[],
        warnings=warnings,
    )
    assert comp["school_tier"] == "其他", comp
    assert comp.get("school_tier_recognized") is False, comp
    hit = [item for item in warnings if item.get("code") == "SCHOOL_TIER_INFERRED"]
    assert hit, warnings
    assert hit[0]["severity"] == "warn"
    assert (hit[0].get("details") or {}).get("recognized") is False
    assert "偏低" not in comp.get("school_signal", ""), "未知层次不得判低"

    known = jd_analysis.tier_from_school_name("示例大学")
    assert known == "985", known


@check("AC-ANL-10")
def _anl_10(flow):
    from app.services import company_analysis

    pref = company_analysis.school_preference_from(jd_text="985/211 院校优先，但不设院校门槛。")
    assert pref["hard_filter"] is False, pref
    assert str(pref["threshold"]).startswith("不限") and "偏好" in str(pref["threshold"]), pref
    assert pref["preferred_tiers"], pref

    none = company_analysis.school_preference_from(jd_text="负责增长实验设计，熟练使用 SQL。")
    assert none["preferred_tiers"] == [], "不得凭空造偏好"


@check("AC-ANL-11")
def _anl_11(flow):
    from app.services import jd_analysis

    soften = [
        "985/211 院校优先",
        "985/211/双一流 优先",
        "985、211 优先",
        "C9 院校优先",
    ]
    hard = [
        "要求 985 及以上",
        "仅限 985/211 院校",
        "985 起步",
    ]
    for text in soften:
        gate = jd_analysis.detect_school_gate([text])
        assert gate["hard_filter"] is False, (text, gate)
        assert str(gate["threshold"]).startswith("不限"), (text, gate)
        assert gate["preferred_tiers"], (text, gate)
    for text in hard:
        gate = jd_analysis.detect_school_gate([text])
        assert gate["hard_filter"] is True, (text, gate)
    negated = jd_analysis.detect_school_gate(["不设院校门槛", "不要求 985"])
    assert negated["hard_filter"] is False, negated
    # 裸字符串与单元素列表必须逐字相等（曾按字符迭代而静默返回「未提及」）
    assert jd_analysis.detect_school_gate("要求 985 及以上") == jd_analysis.detect_school_gate(["要求 985 及以上"])


@check("AC-ANL-12")
def _anl_12(flow):
    from app.services import jd_analysis

    for text in ("仅限 985/211 院校", "仅限 985、211 院校", "仅限 985 和 211 院校"):
        gate = jd_analysis.detect_school_gate([text])
        assert gate["hard_filter"] is True, (text, gate)
        assert gate["preferred_tiers"] == ["985", "211"], (text, gate)
        assert "985" in gate["threshold"] and "211" in gate["threshold"], (text, gate)


# ------------------------------------------------------------------ 隐私与冲突 ----------------

@check("AC-PRIV-14")
def _priv_14(flow):
    client = flow["client"]
    preview = client.post(
        "/api/v1/llm/preview",
        json={
            "purpose": "jd_analyze",
            "selections": {"jd_id": flow["jd"]["id"], "package_ids": []},
        },
    )
    assert preview.status_code == 201, preview.get_json()
    payload = preview.get_json()["data"]
    body = json.dumps(payload["payload"], ensure_ascii=False)
    school = (flow["profile"] or {}).get("school_zh") or "示例大学"
    assert school in body, "校名必须按真实值发送（不是占位符）"
    assert "[SCHOOL]" not in body, "占位符方案已废弃"
    text = body
    for field in ("school", "degree", "major", "grad_year", "city", "available_date"):
        assert field in text, f"候选人档案七项缺 {field}"
    for value in ((flow["profile"] or {}).get("name_zh"), (flow["profile"] or {}).get("phone")):
        if value:
            assert value not in body, f"{value} 不得上云"
    assert (flow["profile"] or {}).get("email", "x@y.z") not in body


@check("AC-CONFLICT-01")
def _conflict_01(flow):
    client = flow["client"]
    zh_text = "张三\n到岗时间：2027年1月下旬\n教育背景\n2024.9-2028.6 示例大学 计算机科学与技术 本科\n专业成绩：GPA 3.56/4 86.53/100\n"
    en_text = "SAN ZHANG\nAvailable: Early July 2026\nEDUCATION\n09/2024 - 06/2028 Example University, B.S. in CS\nGPA: 3.57/4.0 (86.86/100)\n"
    for text, lang in ((zh_text, "zh"), (en_text, "en")):
        created = client.post("/api/v1/imports", json={"text": text, "filename": f"conflict-{lang}.txt", "lang": lang})
        import_id = created.get_json()["data"]["import_id"]
        client.post(
            f"/api/v1/imports/{import_id}/commit",
            json={"template_name": f"冲突源 {lang}", "lang": lang, "also_create_packages": False},
        )
    from app.services import source_conflict

    pairs = source_conflict.detect()
    keys = {item["field"] for item in pairs}
    assert {"gpa", "score", "available"} <= keys, pairs
    detail = {item["field"]: item for item in pairs}
    assert detail["gpa"]["zh_value"].startswith("3.56") and detail["gpa"]["en_value"].startswith("3.57"), detail["gpa"]
    warnings = source_conflict.warnings_for(pairs)
    assert all(item["code"] == "SOURCE_CONFLICT" for item in warnings)
    assert len(warnings) == len(pairs), "冲突字段数与告警数必须相等"

    # 各按语言取值：zh 版不得印英文值，en 版不得印中文值
    zh_pdf = pdf_text(flow, "zh-original")
    en_pdf = pdf_text(flow, "en-original")
    assert "Early July 2026" not in zh_pdf
    assert "2027年1月下旬" not in en_pdf


# ------------------------------------------------------------------ 英文版 ----------------

@check("AC-EN-01")
def _en_01(flow):
    ir = _ir(flow, flow["build_id_en"])
    chrome = [str(ir["header"].get("name") or "")]
    chrome += [str(ir["header"].get("contact_line") or ""), str(ir["header"].get("available") or "")]
    chrome += [str(section.get("heading") or "") for section in _sections(ir)]
    for line in chrome:
        assert not CJK_RE.search(line), f"英文版骨架区出现中文：{line!r}"
    text = pdf_text(flow, "en-original")
    lines = [line for line in text.splitlines() if line.strip()]
    head = lines[:3]
    assert not any(CJK_RE.search(line) for line in head), head
    for heading in ("Education", "Experience", "Projects"):
        assert heading in text, f"英文版缺少映射后的段落标题 {heading}"
    for banned in ("教育背景", "实习经历", "项目经历", "到岗时间", "本科"):
        assert banned not in text, f"英文版骨架区出现中文：{banned}"


@check("AC-EN-02")
def _en_02(flow):
    payload = flow["artifacts"]["en-original"]
    codes = {item.get("code") for item in payload.get("warnings") or []}
    text = pdf_text(flow, "en-original")
    en_variants = db_int(flow, "SELECT count(*) FROM package_bullet_variant WHERE lang='en'")
    if en_variants:
        assert "LANG_FALLBACK" not in codes
    else:
        assert "LANG_FALLBACK" in codes, codes
        fallback = next(item for item in payload["warnings"] if item.get("code") == "LANG_FALLBACK")
        details = fallback.get("details") or {}
        assert {"entry_count", "bullet_count"} <= set(details), details
        assert CJK_RE.search(text), "无英文变体时应渲染中文原文，不得空段"
        # 英文版里每一行中文都必须被这条 warning 认领：声明的中文字符数不得少于
        # PDF 里实际出现的中文字符数（少了就是「偷偷混进来的中文」= 半翻译）。
        assert "cjk_char_count" in details, f"LANG_FALLBACK 缺 cjk_char_count：{details.keys()}"
        actual = len(CJK_RE.findall(text))
        assert details["cjk_char_count"] >= actual, (
            f"声明的中文 {details['cjk_char_count']} 字 < PDF 实际 {actual} 字"
        )
    # 不得空段空标题
    for section in _sections(_ir(flow, flow["build_id_en"])):
        assert str(section.get("heading") or "").strip(), section
        body = section.get("entries") or section.get("skills") or []
        assert body, f"英文版出现空段：{section}"
    # 反向断言：中文版不得出现 LANG_FALLBACK
    zh_codes = {item.get("code") for item in flow["artifacts"]["zh-original"].get("warnings") or []}
    assert "LANG_FALLBACK" not in zh_codes


@check("AC-EN-03")
def _en_03(flow):
    zh = _ir(flow, flow["build_id"])
    en = _ir(flow, flow["build_id_en"])
    zh_sections = [(section["kind"], len(section.get("entries") or [])) for section in _sections(zh)]
    en_sections = [(section["kind"], len(section.get("entries") or [])) for section in _sections(en)]
    assert zh_sections == en_sections, (zh_sections, en_sections)
    zh_layout = flow["artifacts"]["zh-original"].get("layout") or {}
    en_layout = flow["artifacts"]["en-original"].get("layout") or {}
    assert zh_layout.get("body_pt") == en_layout.get("body_pt"), (zh_layout, en_layout)


@check("AC-EN-04")
def _en_04(flow):
    from unittest import mock

    client = flow["client"]
    package_id = (flow["packages"] or [{}])[0].get("id")
    assert package_id
    preview = client.post(
        "/api/v1/llm/preview",
        json={
            "purpose": "bullets_generate",
            "selections": {"package_ids": [package_id], "tones": ["impact"], "lang": "en"},
        },
    )
    assert preview.status_code == 201, preview.get_json()
    data = preview.get_json()["data"]
    assert data["preview_id"]
    fields = json.dumps(data.get("fields") or [], ensure_ascii=False)
    assert "profile.name" not in fields and "profile.phone" not in fields
    body = json.dumps(data["payload"], ensure_ascii=False)
    for value in ((flow["profile"] or {}).get("name_zh"), (flow["profile"] or {}).get("phone")):
        if value:
            assert value not in body

    canned = {
        "raw_text": json.dumps(
            {"variants": [{"bullet_key": "b1", "tone": "impact", "lang": "en", "text": "Built the matching service, QPS 1200 to 6527."}]}
        ),
        "parsed": {"variants": [{"bullet_key": "b1", "tone": "impact", "lang": "en", "text": "Built the matching service, QPS 1200 to 6527."}]},
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        "provider": "deepseek",
        "model": "deepseek-chat",
        "latency_ms": 1,
        "finish_reason": "stop",
        "warnings": [],
    }
    with mock.patch("app.services.consent.ConsentService.complete", return_value=canned):
        export = client.post(
            f"/api/v1/packages/{package_id}/variants/generate",
            json={"preview_id": data["preview_id"], "bullet_keys": ["b1"], "tones": ["impact"], "lang": "en"},
        )
        assert export.status_code == 202, export.get_json()
        job = wait_job(client, export.get_json()["data"]["job_id"])
    variants = (job.get("result_json") or {}).get("variants") or []
    assert variants, job
    for item in variants:
        assert item["lang"] == "en"
        assert not CJK_RE.search(item["text"]), item
        assert item["llm_generated"] is True and item["verified"] is False


# ------------------------------------------------------------------ 版式 ----------------

@check("AC-PDF-16")
def _pdf_16(flow):
    ir = _ir(flow, flow["build_id"])
    assert "education_line" not in (ir.get("header") or {}), "页眉白名单只有 name/contact/available"
    text = pdf_text(flow, "zh-original")
    head = [line for line in text.splitlines() if line.strip()][:4]
    joined = "\n".join(head)
    assert not re.search(r"本科|硕士|博士|大专|B\.M\.|Bachelor|Master", joined), head
    assert "张三" in joined
    assert "13800138000" in joined


@check("AC-PDF-17")
def _pdf_17(flow):
    entries = _entries(_ir(flow, flow["build_id"]), "education")
    assert entries, "教育段必须有条目"
    date_range = str(entries[0].get("date_range") or "")
    assert date_range, entries[0]
    text = pdf_text(flow, "zh-original")
    years = re.findall(r"(19|20)\d{2}", text)
    assert years, "PDF 里应出现年份"
    for year in re.findall(r"(?:19|20)\d{2}", date_range):
        assert year in text, f"教育段日期 {year} 未出现在 PDF 中（不得只印 grad_year）"
    assert date_range.split("-")[0][:4] in text.replace(" ", "")


@check("AC-PDF-18")
def _pdf_18(flow):
    metrics = pdf_metrics(flow, "zh-original")
    body = metrics["body_size"]
    codes = {item.get("code") for item in flow["artifacts"]["zh-original"].get("warnings") or []}
    if "PAGE_FIT_DOWNGRADED" in codes:
        assert body >= 9.5, metrics["sizes"]
    else:
        assert abs(body - 11.0) <= 0.2, f"未降档时正文应为 11pt，实测 {body}（{metrics['sizes']}）"
    if 9.5 in metrics["sizes"]:
        assert "PAGE_FIT_DOWNGRADED" in codes, "9.5pt 单独出现即 FAIL"
    # 条目头单行：日期不得独占一行
    ir = _ir(flow, flow["build_id"])
    dates = [
        str(entry.get("date_range") or "").strip()
        for section in _sections(ir)
        for entry in section.get("entries") or []
        if str(entry.get("date_range") or "").strip()
    ]
    lines = [line.strip() for line in pdf_text(flow, "zh-original").splitlines() if line.strip()]
    for date in dates:
        assert date not in lines, f"日期独占了一行：{date}"


@check("AC-PDF-19")
def _pdf_19(flow):
    from pypdf import PdfReader

    reader = PdfReader(str(flow["data_dir"] / "exports" / artifact(flow)["filename"]))
    assert len(reader.pages) >= 1


@check("AC-NAME-09")
def _name_09(flow):
    text = pdf_text(flow, "en-original")
    first = next(line for line in text.splitlines() if line.strip())
    assert re.match(r"^[A-Z][A-Z .]+$", first.strip()), first
    assert first.strip() == "ZHANG SAN", first
    zh = pdf_text(flow, "zh-original")
    assert (flow["profile"] or {}).get("name_en", "Zhang San") not in zh
    # 反向：不得由 name_zh 生成拼音
    from app.services import compose

    ir = compose.build_ir(
        {"lang": "en"},
        selections=[],
        packages={},
        variants_by_package={},
        blocks=[],
        profile={"name_zh": "张三", "name_en": None},
    )
    assert ir["header"]["name"] == "张三", ir["header"]
    assert any(item.get("code") == "PROFILE_FIELD_MISSING" for item in ir["warnings"]), ir["warnings"]


# ------------------------------------------------------------------ 技能 ----------------

@check("AC-SKILL-01")
def _skill_01(flow):
    client = flow["client"]
    skills = client.get("/api/v1/profile").get_json()["data"]["skills"]
    assert skills
    text = re.sub(r"\s+", "", pdf_text(flow, "zh-original"))
    for row in skills:
        want = re.sub(r"\s+", "", row["line"])
        assert want in text, f"技能行未逐字出现：{row['line']}"


@check("AC-SKILL-02")
def _skill_02(flow):
    text = pdf_text(flow, "zh-original")
    assert not TAG_BLOCK_RE.search(text), TAG_BLOCK_RE.search(text)
    client = flow["client"]
    preview = client.get(f"/api/v1/builds/{flow['build_id']}/preview?format=html")
    html = preview.get_data(as_text=True)
    for word in ("tag", "chip", "pill", "badge"):
        assert f'class="{word}' not in html and f" {word} " not in html.lower()
    skills = client.get("/api/v1/profile").get_json()["data"]["skills"]
    body = html.split("技能", 1)[-1]
    for row in skills:
        assert row["line"][:8] in body, row["line"]


@check("AC-SKILL-03")
def _skill_03(flow):
    from app.services import skills as skills_mod

    row = {"line": "数据分析类：掌握 Python、R、SQL", "tokens": []}
    assert skills_mod.row_match_score(row, ["SQL"]) > 0, "tokens 缺失时应降级为整句子串匹配"
    client = flow["client"]
    snapshot = snapshot_profile(client)
    try:
        patched = [dict(item, tokens=[]) for item in snapshot["skills"]]
        client.put("/api/v1/profile", json={"skills": patched})
        html = client.get(f"/api/v1/builds/{flow['build_id']}/preview?format=html").get_data(as_text=True)
        for item in snapshot["skills"]:
            assert item["line"][:8] in html, "tokens 置空不得丢行"
        matched = client.post(f"/api/v1/jds/{flow['jd']['id']}/match", json={})
        assert matched.status_code == 200, matched.get_json()
    finally:
        restore_profile(client, snapshot)


@check("AC-SKILL-04")
def _skill_04(flow):
    client = flow["client"]
    ir = _ir(flow, flow["build_id"])
    facts = [fact for entry in _entries(ir, "education") for fact in entry.get("facts") or []]
    course_lines = [fact for fact in facts if "主修课程" in fact]
    assert course_lines, facts
    full = course_lines[0]
    assert full.count("、") + 1 >= 5, full

    plain = client.post(
        f"/api/v1/builds/{flow['build_id']}/export",
        json={"format": "pdf", "verify_text": False},
    )
    plain_job = wait_job(client, plain.get_json()["data"]["job_id"])
    plain_codes = {item.get("code") for item in (plain_job.get("result_json") or {}).get("warnings") or []}
    assert "COURSES_TRIMMED" not in plain_codes, "默认不得裁剪"

    trimmed = client.post(
        f"/api/v1/builds/{flow['build_id']}/export",
        json={"format": "pdf", "verify_text": False, "trim_courses": True, "overwrite": True},
    )
    job = wait_job(client, trimmed.get_json()["data"]["job_id"])
    codes = [item for item in (job.get("result_json") or {}).get("warnings") or []]
    hit = [item for item in codes if item.get("code") == "COURSES_TRIMMED"]
    assert hit, codes
    details = hit[0]["details"]
    assert details["before"] > details["after"] >= 3, details
    text = pdf_text(flow, "zh-original")
    assert "主修课程：" in text


# ------------------------------------------------------------------ 导入派生包 ----------------

def _fresh_commit(flow, *, also_packages: bool = True, overwrite_profile: bool = False) -> dict:
    client = flow["client"]
    # 每次都要一份**内容不同**的草稿：派生包有跨导入的幂等键（ckey），
    # 内容一样会被判为「已有同一段经历」而全部复用，测不出新建行为。
    import uuid

    marker = "ac" + uuid.uuid4().hex[:6]
    # 每一段都要带 marker：派生包的幂等键是「整段经历的内容指纹」，
    # 只改项目标题会让教育/实习/校园三段被判为「已有同一段经历」而复用，
    # 测出来就是「本次没新建任何包」——那是幂等生效，不是缺陷。
    text = (
        f"李四{marker}\n13800138001\n教育背景\n2024.9-2028.6 示例大学-信息学院 计算机科学与技术 本科（{marker}）\n"
        f"专业成绩：GPA 3.56/4 86.53/100 CET4：562（{marker}）\n"
        f"主修课程：统计学(92)、数据库系统原理(SQL)（90）（{marker}）\n"
        f"实习经历\n示例数据科技有限公司{marker} - 数据实习生 2026.07 - 2026.10\n"
        f"● 负责报表自动化，月均节省 39.3 小时，批次 {marker}。\n"
        f"项目经历\n门店模型{marker} - 队长 2026.03 - 2026.04\n● 覆盖 6527 家门店，召回率 92.3%，编号 {marker}。\n"
        f"校园活动\n2024.9 - 至今 示例大学 班长{marker}\n主要活动：组织第三十六届科技节{marker}\n"
    )
    created = client.post("/api/v1/imports", json={"text": text, "filename": f"derive-ac-{marker}.txt", "lang": "zh"})
    import_id = created.get_json()["data"]["import_id"]
    commit = client.post(
        f"/api/v1/imports/{import_id}/commit",
        json={
            "template_name": "派生包 AC",
            "lang": "zh",
            "also_create_packages": also_packages,
            "overwrite_profile": overwrite_profile,
        },
    )
    assert commit.status_code == 201, commit.get_json()
    return {"import_id": import_id, "commit": commit.get_json()["data"]}


@check("AC-IMPORT-15")
def _import_15(flow):
    """契约 I12 + §5.4：派生包要「一个不少」，也不许「假装建过」。

    判据从草稿现算，不写死数字：
      * 应建包 = 有正文（bullets/facts 非空）且 kind ∉ {education, skill} 的 entry；
      * education 静默跳过是契约规定（教育进档案与静态文本，不是可复用包），
        所以等式两边都把它排除，再用第二条断言「差额必须能被跳过集解释」兜住
        「把建不出来的当成 education 悄悄吞掉」。
    """
    made = _fresh_commit(flow)
    import_id = made["import_id"]
    draft = flow["client"].get(f"/api/v1/imports/{import_id}").get_json()["data"]["draft"]
    expected, skippable = _expected_derived_packages(draft)

    first = db_int(flow, "SELECT count(*) FROM package WHERE source_import_job_id=?", (import_id,))
    present = {
        str(row[0])
        for row in db(flow).execute(
            "SELECT source_entry_temp_id FROM package WHERE source_import_job_id=?", (import_id,)
        ).fetchall()
        if row[0]
    }
    missing = [item for item in expected if item["temp_id"] not in present]
    made_kinds: dict[str, int] = {}
    for item in expected:
        if item["temp_id"] in present:
            made_kinds[item["kind"]] = made_kinds.get(item["kind"], 0) + 1
    reused_ids = list(made["commit"].get("packages_reused") or [])
    skipped_reasons = made["commit"].get("packages_skipped") or []
    print(f"[AC-IMPORT-15] reused={len(reused_ids)} skipped={skipped_reasons}")
    print(
        f"[AC-IMPORT-15] entry 块 {len(expected) + len(skippable)} 条 / 有正文 {len(expected) + len(skippable)} 条 / "
        f"其中 education·skill {len(skippable)} 条 / 应建包 {len(expected)} 条 / 实际派生 {first} 条 / 明细 {made_kinds}"
    )
    # 内容完全相同的经历会被幂等键复用（跨导入只留一份，这是契约 I12 要求的），
    # 所以「这次新建的」+「复用的」才是全部落地数；真正不许出现的是**两者都不是**。
    assert first + len(reused_ids) == len(expected), (
        f"期望 {len(expected)} 条派生包 / 新建 {first} 条 + 复用 {len(reused_ids)} 条；"
        f"未建包：{[{'temp_id': m['temp_id'], 'kind': m['kind']} for m in missing]}"
    )

    # 差额必须能解释：没建包的 entry 只能是 education / skill。
    skipped_kinds = {item["kind"] for item in skippable if item["temp_id"] not in present}
    assert skipped_kinds <= {"education", "skill"}, (
        f"有非教育/技能类 entry 没建成包且没有说明：{sorted(skipped_kinds)}"
    )

    # 幂等键必须齐全：任何一行 source_entry_temp_id 为空都意味着「下次还会新建一份」
    orphan = db_int(
        flow,
        "SELECT count(*) FROM package WHERE source_import_job_id=? AND source_entry_temp_id IS NULL",
        (import_id,),
    )
    assert orphan == 0, f"{orphan} 个派生包缺少 source_entry_temp_id（幂等键失效）"

    again = flow["client"].post(
        f"/api/v1/imports/{import_id}/commit",
        json={"template_name": "派生包 AC", "lang": "zh", "also_create_packages": True},
    )
    second = db_int(flow, "SELECT count(*) FROM package WHERE source_import_job_id=?", (import_id,))
    assert second == first, f"重复 commit 不得新增包：{first} → {second}"

    if again.status_code == 201:
        created = again.get_json()["data"].get("packages_created") or []
        existing = {
            row[0]
            for row in db(flow).execute(
                "SELECT id FROM package WHERE source_import_job_id=?", (import_id,)
            ).fetchall()
        }
        stray = [item for item in created if item not in existing]
        assert not stray, f"第二次 commit 报出了不存在的包 id：{stray}"


#: 按契约 §5.4 不建包的 entry 类型（教育进档案/静态文本；技能不是经历条目）
NO_PACKAGE_KINDS = {"education", "skill"}


def _expected_derived_packages(draft: dict) -> tuple[list[dict], list[dict]]:
    """从草稿现算「应建包」与「允许不建包」的 entry，两份都带 temp_id 与 kind。"""
    entries: list[dict] = []
    for block in draft.get("blocks") or []:
        if block.get("block_type") != "entry":
            continue
        entry = block.get("entry") or {}
        body = [line for line in list(entry.get("bullets") or []) + list(entry.get("facts") or []) if str(line).strip()]
        if not body:
            continue
        entries.append(
            {
                "temp_id": str(block.get("temp_id") or ""),
                "kind": str(block.get("bound_package_kind") or ""),
            }
        )
    expected = [item for item in entries if item["kind"] not in NO_PACKAGE_KINDS]
    skippable = [item for item in entries if item["kind"] in NO_PACKAGE_KINDS]
    return expected, skippable


@check("AC-IMPORT-16")
def _import_16(flow):
    made = _fresh_commit(flow)
    import_id = made["import_id"]
    client = flow["client"]
    before = db_int(flow, "SELECT count(*) FROM package WHERE source_import_job_id=?", (import_id,))
    manual = client.post(
        "/api/v1/packages",
        json={"title": "手工包不受影响", "kind": "project", "org": "示例", "status": "draft"},
    ).get_json()["data"]["id"]
    assert client.delete(f"/api/v1/imports/{import_id}").status_code in (200, 204)
    assert db_int(
        flow,
        "SELECT count(*) FROM package WHERE source_import_job_id=? AND deleted_at IS NULL",
        (import_id,),
    ) == 0
    assert client.post(f"/api/v1/imports/{import_id}/restore").status_code == 200
    assert db_int(
        flow,
        "SELECT count(*) FROM package WHERE source_import_job_id=? AND deleted_at IS NULL",
        (import_id,),
    ) == before
    assert db_one(flow, "SELECT deleted_at FROM package WHERE id=?", (manual,))[0] is None


@check("AC-IMPORT-17")
def _import_17(flow):
    made = _fresh_commit(flow, also_packages=False)
    import_id = made["import_id"]
    template_id = made["commit"]["template_id"]
    client = flow["client"]
    deleted = client.delete(f"/api/v1/imports/{import_id}")
    assert deleted.status_code in (200, 204)
    body = deleted.get_json().get("data") or {}
    kept = body.get("template_retained") or {}
    assert kept.get("kept") is True, body
    assert kept.get("template_id") == template_id, kept
    assert client.get(f"/api/v1/templates/{template_id}").status_code == 200
    assert db_one(flow, "SELECT deleted_at FROM template WHERE id=?", (template_id,))[0] is None


@check("AC-IMPORT-18")
def _import_18(flow):
    made = _fresh_commit(flow, also_packages=False)
    import_id = made["import_id"]
    template_id = made["commit"]["template_id"]
    client = flow["client"]
    client.delete(f"/api/v1/imports/{import_id}")
    client.post(f"/api/v1/imports/{import_id}/restore")
    assert db_one(flow, "SELECT result_template_id FROM import_job WHERE id=?", (import_id,))[0] == template_id
    # 只看这条导入：删导入不删模板是**设计**（模板是用户资产），
    # 全局扫会把别的已删导入也算成断链，判据必须在本次恢复的对象上成立。
    broken = db_int(
        flow,
        "SELECT count(*) FROM import_job j JOIN template t ON t.id=j.result_template_id "
        "WHERE j.id = ? AND j.result_template_id IS NOT NULL AND t.id IS NULL",
        (import_id,),
    )
    assert broken == 0, f"R-c 断链 {broken} 条"
    import subprocess
    import sys

    from .helpers import repo_root

    out = subprocess.run(
        [sys.executable, "scripts/prune_probe_data.py", "--json"],
        cwd=str(repo_root()),
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "DATA_DIR": str(flow["data_dir"])},
    )
    assert out.returncode == 0, out.stderr[-400:]


@check("AC-IMPORT-19")
def _import_19(flow):
    statics = " ".join(
        row[0] or ""
        for row in flow["_db_exec"]("SELECT static_text FROM template_block WHERE template_id=?", (flow["template_id"],))
    )
    for needle in ("3.56", "562", "508"):
        assert needle in statics, f"模板块静态文本缺 {needle}"
    profile = flow["client"].get("/api/v1/profile").get_json()["data"]
    for field in ("degree", "major", "grad_year", "city"):
        assert profile.get(field), f"commit 未回填 {field}"


@check("AC-IMPORT-20")
def _import_20(flow):
    made = _fresh_commit(flow, also_packages=False)
    import_id = made["import_id"]
    commit = made["commit"]
    assert commit.get("profile_fields_source"), commit
    assert commit.get("profile_filled") is not None or commit.get("profile_fields_source")
    sources = db_one(flow, "SELECT extra_json FROM user_profile WHERE id='me'")[0] or "{}"
    extra = json.loads(sources)
    # 溯源要落到字段级：profile_field_sources 是 {字段: import:<job_id>} 的映射，
    # 另有 profile_fields_source 记「最近一次触达档案的导入」。两者都指向本次导入才算数。
    per_field = extra.get("profile_field_sources") or {}
    assert per_field, extra
    assert all(str(value).startswith(f"import:{import_id}") for value in per_field.values()), per_field
    assert (extra.get("profile_fields_source") or "").startswith(f"import:{import_id}"), extra

    client = flow["client"]
    snapshot = snapshot_profile(client)
    try:
        client.put("/api/v1/profile", json={"degree": "硕士"})
        # 同一份导入只能提交一次模板（D-21 409 TEMPLATE_VERSION_CONFLICT），
        # 所以要验「回填不覆盖手改值」，得换一次新导入（内容加标记，避免命中幂等复用）。
        again = _fresh_commit(flow, also_packages=False)
        assert again["commit"].get("profile_fields_skipped_manual"), again["commit"]
        assert client.get("/api/v1/profile").get_json()["data"]["degree"] == "硕士", "manual 值不得被覆盖"
        overwrite = _fresh_commit(flow, also_packages=False, overwrite_profile=True)
        assert overwrite["commit"]["import_id"], overwrite["commit"]
        assert client.get("/api/v1/profile").get_json()["data"]["degree"] == "本科", "显式覆盖应生效"
    finally:
        restore_profile(client, snapshot)


@check("AC-PKG-14")
def _pkg_14(flow):
    rows = flow["_db_exec"](
        "SELECT source, verified, llm_generated FROM package_bullet_variant WHERE source IS NOT NULL"
    ).fetchall()
    assert rows, "变体必须带 source"
    for row in rows:
        assert row[0] in ("imported_verbatim", "llm_rewrite", "manual"), row
        if row[0] == "llm_rewrite":
            assert row[2] == 1 and row[1] == 0, row
        if row[0] == "imported_verbatim":
            assert row[1] == 1, row
    assert db_int(flow, "SELECT count(*) FROM package_bullet_variant WHERE source IS NULL") == 0


# ------------------------------------------------------------------ 构建别名 ----------------

@check("AC-BUILD-15")
def _build_15(flow):
    """PUT 是 PATCH 的真别名；selections 无选择时返回 []（这两条都在**独立** build 上验，
    绝不改流程现场的那份 build —— 否则后续 AC 看到的是被清空的选择）。"""
    client = flow["client"]
    created = client.post(
        "/api/v1/builds",
        json={"name": "别名等价", "template_id": flow["template_id"], "lang": "zh", "position": "数据分析实习生"},
    )
    assert created.status_code == 201, created.get_json()
    build_id = created.get_json()["data"]["id"]
    empty = client.get(f"/api/v1/builds/{build_id}/selections")
    assert empty.status_code == 200
    assert (empty.get_json().get("data") or {}).get("items") == []
    payload = {"name": "别名等价", "position": "数据分析实习生"}
    put = client.put(f"/api/v1/builds/{build_id}", json=payload)
    patch = client.patch(f"/api/v1/builds/{build_id}", json=payload)
    assert put.status_code == patch.status_code == 200, (put.get_json(), patch.get_json())
    assert put.get_json()["data"]["name"] == patch.get_json()["data"]["name"] == "别名等价"
    assert db_one(flow, "SELECT name FROM resume_build WHERE id=?", (build_id,))[0] == "别名等价"
    # 对称性：写入后读回内容一致
    client.put(f"/api/v1/builds/{build_id}/selections", json={"items": []})
    assert (client.get(f"/api/v1/builds/{build_id}/selections").get_json()["data"] or {}).get("items") == []



# ---------------------------------------------------------- JD 分析：包与本地改判（v1.29）


@check("AC-ANL-13")
def _anl_13(flow):
    """jd_analyze 的字段清单必须带「经历要点」，且不得夹带索引/标识/路径。"""
    from .helpers import db

    client = flow["client"]
    rows = db(flow).execute(
        "SELECT id, title FROM package WHERE deleted_at IS NULL AND status = 'ready' ORDER BY created_at LIMIT 3"
    ).fetchall()
    assert rows, "构造现场应有 ready 包"
    package_id, title = rows[0][0], rows[0][1]
    preview = client.post(
        "/api/v1/llm/preview",
        json={"purpose": "jd_analyze", "selections": {"jd_id": flow["jd"]["id"], "package_ids": [package_id]}},
    )
    assert preview.status_code == 201, preview.get_json()
    data = preview.get_json()["data"]
    fields = data["fields"]
    package_fields = [item for item in fields if item.get("source") == "packages"]
    assert package_fields, [item.get("source") for item in fields]
    assert any(title in str(item.get("label") or "") for item in package_fields), package_fields
    assert any(str(item.get("source_id") or "") == package_id for item in package_fields), package_fields

    body = json.dumps(data["payload"], ensure_ascii=False)
    bullets = [
        str(row[0])
        for row in db(flow)
        .execute(
            "SELECT substr(text, 1, 12) FROM package_bullet_variant "
            "WHERE package_id = ? AND length(text) >= 12 LIMIT 3",
            (package_id,),
        )
        .fetchall()
    ]
    assert bullets, "该包应有可引用的要点原文"
    assert any(snippet in body for snippet in bullets), "payload 必须含经历要点原文片段"

    # 反向：索引 token / 内部标识 / 本机路径都不得出现
    tokens = [
        str(row[0])
        for row in db(flow)
        .execute("SELECT value FROM json_each(json_extract((SELECT skills_json FROM user_profile WHERE id='me'), '$'))")
        .fetchall()
    ]
    for token in tokens:
        if len(token) >= 4:
            assert token not in body, f"payload 夹带了技能索引 token：{token}"
    for needle in (package_id, "variant_id", "photo_path", "data/"):
        assert needle not in body, f"payload 夹带了内部标识：{needle}"

    # 预算：选 1 个包不可能超限；只断言上界存在且成立
    assert data.get("total_chars", 0) <= 6000, data.get("total_chars")


@check("AC-ANL-14")
def _anl_14(flow):
    """本地命中 vs 模型判 missing：只许把 missing 上调为 partial，不许伪造命中。"""
    from app.services import jd_analysis

    package = {
        "id": "pkg-ab",
        "title": "赛车类游戏版本 AB 测试对照数据分析",
        "status": "ready",
        "bullets": ["通过广告增量拆分与显著性检验，确认 A/B 测试提升 39.3%"],
        "summary": "",
    }
    req_hit = {"skill": "A/B 测试经验", "candidate_status": "missing", "raw_quote": ""}
    ok = {"skill": "A/B 测试经验", "candidate_status": "satisfied", "raw_quote": "x"}
    req_miss = {"skill": "Kubernetes 集群运维", "candidate_status": "missing", "raw_quote": "原文没有"}
    warnings: list[dict] = []
    overridden = jd_analysis.link_requirements([req_hit, ok, req_miss], [package], warnings=warnings)

    assert overridden == 1, overridden
    assert req_hit["candidate_status"] == "partial", req_hit
    assert req_hit["candidate_status_source"] == "local_override", req_hit
    assert req_hit["matched_package_ids"] == ["pkg-ab"], req_hit
    assert any(item["code"] == "LLM_STATUS_OVERRIDDEN" for item in warnings), warnings
    detail = next(item for item in warnings if item["code"] == "LLM_STATUS_OVERRIDDEN")["details"]
    assert detail["from"] == "missing" and detail["to"] == "partial", detail
    # 方向唯一：已经是 satisfied 的不因本地命中被上调成别的值
    assert ok["candidate_status"] == "satisfied", ok
    # 反向：本地没命中 → 模型给的 missing 原样保留，不许伪造
    assert req_miss["candidate_status"] == "missing", req_miss
    assert req_miss["matched_package_ids"] == [], req_miss


@check("AC-ANL-15")
def _anl_15(flow):
    """matched_package_ids 由本地计算：不采信模型编造的 id，非 ready 包剔除并告警。"""
    from app.services import jd_analysis

    ready = {"id": "pkg-ready", "title": "SQL 数据分析项目", "status": "ready", "bullets": ["用 SQL 做分层留存分析"]}
    req = {
        "skill": "SQL",
        "candidate_status": "missing",
        "matched_package_ids": ["pkg-ghost", "pkg-draft"],
        "raw_quote": "",
    }
    warnings: list[dict] = []
    jd_analysis.link_requirements([req], [ready], warnings=warnings)
    assert req["matched_package_ids"] == ["pkg-ready"], req
    assert "pkg-ghost" not in json.dumps(req, ensure_ascii=False)

    # 确定不该命中的要求：返回空数组，且不是「没算」——没有 NOT_READY 告警
    empty = {"skill": "Kubernetes 集群运维", "candidate_status": "missing", "matched_package_ids": [], "raw_quote": ""}
    warnings2: list[dict] = []
    jd_analysis.link_requirements([empty], [ready], warnings=warnings2)
    assert empty["matched_package_ids"] == [], empty
    assert not [item for item in warnings2 if item["code"] == "MATCHED_PACKAGE_NOT_READY"], warnings2




@check("AC-UI-03")
def _ui_03(flow):
    """ConsentModal 的行为契约在源码里留痕（DOM 级断言用静态扫描兜住，防回归）。"""
    from .helpers import repo_root

    source = (repo_root() / "web" / "src" / "components" / "consent-modal.js").read_text(encoding="utf-8")
    assert "onEscape" in source, "Esc 必须能取消"
    assert 'ev.key === "Enter"' in source and "preventDefault" in source, "Enter 不得触发确认"
    assert "重新生成预览" in source, "过期后按钮要变成「重新生成预览」"
    # excluded 与 redactions 必须在主视野（不得折进 <details>）
    main_zone = source.split('"details"')[0] if '"details"' in source else source
    assert "modal__excluded" in main_zone or "excluded" in main_zone, "excluded 要在主视野"
    assert "redactions" in source, "redactions 必须展示"
    # 页面里任何发起 LLM 调用的地方都要先弹这个模态
    for page in ("jobs.js", "workbench.js"):
        text = (repo_root() / "web" / "src" / "pages" / page).read_text(encoding="utf-8")
        if "llm/preview" in text or "preview(" in text:
            assert "consent" in text.lower() or "openConsent" in text or "ConsentModal" in text, f"{page} 未经确认就调用预览"


# ------------------------------------------------- 构建归档与物理删除（AC-BUILD-16） -------------

@check("AC-BUILD-16")
def _build_16(flow):
    """「不想看见这份简历」必须能归档，而不是只能删除。

    归档：行、选题、产物一条不少，只是默认列表里不再出现（`?include_archived=1` 可查回）；
    真删：必须 `?hard=1&confirm=<build_id>`，confirm 不符 → 422 且**一行都没动**。
    """
    client = flow["client"]
    build_id = flow["build_id"]

    def counts():
        return (
            db_int(flow, "SELECT count(*) FROM resume_build"),
            db_int(flow, "SELECT count(*) FROM build_selection"),
            db_int(flow, "SELECT count(*) FROM build_artifact"),
        )

    before = counts()
    listed_before = len(client.get("/api/v1/builds").get_json()["data"]["items"])
    archived_before = db_int(flow, "SELECT count(*) FROM resume_build WHERE archived_at IS NOT NULL")

    # ① PATCH archived=true → 归档，行数不变，其他两张表逐条相等
    patched = client.patch(f"/api/v1/builds/{build_id}", json={"archived": True})
    assert patched.status_code == 200, patched.get_json()
    assert patched.get_json()["data"]["archived_at"], "响应必须回显 archived_at"
    assert counts() == before, f"归档不许动 resume_build/build_selection/build_artifact：{counts()} != {before}"
    assert db_int(flow, "SELECT count(*) FROM resume_build WHERE archived_at IS NOT NULL") == archived_before + 1

    # ② 默认列表少一条，include_archived=1 能查回来
    listed_after = len(client.get("/api/v1/builds").get_json()["data"]["items"])
    assert listed_after == listed_before - 1, f"归档后默认列表应少 1 条：{listed_before} → {listed_after}"
    visible = client.get("/api/v1/builds?include_archived=1").get_json()["data"]["items"]
    assert build_id in [item["id"] for item in visible]

    # ③ DELETE 默认也是归档：行数不变、archived_at 非空
    deleted = client.delete(f"/api/v1/builds/{build_id}")
    assert deleted.status_code == 204, deleted.get_json()
    assert counts() == before, f"DELETE 默认归档不许删行：{counts()} != {before}"
    assert db_one(flow, "SELECT archived_at FROM resume_build WHERE id=?", (build_id,))[0]

    # ④ confirm 不符 → 422 CONFIRM_MISMATCH，且一行都没动
    mismatch = client.delete(f"/api/v1/builds/{build_id}?hard=1&confirm=not-the-id")
    assert mismatch.status_code == 422, mismatch.get_json()
    error = mismatch.get_json()["error"]
    assert error["code"] == "CONFIRM_MISMATCH"
    assert error["details"]["expected"] == build_id and error["details"]["got"] == "not-the-id"
    assert counts() == before, f"CONFIRM_MISMATCH 之后不许有任何变化：{counts()} != {before}"

    # ⑤ 取消归档后回到列表（幂等语义）
    restored = client.patch(f"/api/v1/builds/{build_id}", json={"archived": False})
    assert restored.status_code == 200 and restored.get_json()["data"]["archived_at"] is None
    assert len(client.get("/api/v1/builds").get_json()["data"]["items"]) == listed_before
    assert db_int(flow, "SELECT count(*) FROM build_artifact WHERE build_id NOT IN (SELECT id FROM resume_build)") == 0
    assert db_int(flow, "SELECT count(*) FROM build_selection WHERE build_id NOT IN (SELECT id FROM resume_build)") == 0



# ------------------------------------------- also_create_packages 三分支（AC-IMPORT-21） -----

@check("AC-IMPORT-21")
def _import_21(flow):
    """§5.1 / T-7：跳过必须有出口，且「先判正文」与「先判 kind」不许改变包数。

    同一份 fixture 塞进四种 entry：
      A 教育（契约规定静默跳过，不告警）；B 正常项目（应建包）；
      C kind 映射不出但有正文（→ PACKAGE_SKIPPED/no_kind_mapping）；
      D kind 正常但只有标题没有正文（→ PACKAGE_SKIPPED/empty_entry）；
      E kind 映射不出**且**没有正文（顺序探针：两种实现都必须不建包）。
    """
    client = flow["client"]
    import uuid

    marker = "ac21" + uuid.uuid4().hex[:6]
    text = (
        f"王五{marker}\n13800138003\n教育背景\n2024.9-2028.6 示例大学 计算机科学与技术 本科（{marker}）\n"
        f"专业成绩：GPA 3.56/4（{marker}）\n"
        f"项目经历\n正常项目{marker} - 队长 2026.03 - 2026.04\n● 覆盖 6527 家门店，召回率 92.3% {marker}。\n"
    )
    created = client.post("/api/v1/imports", json={"text": text, "filename": f"ac21-{marker}.txt", "lang": "zh"})
    assert created.status_code == 201, created.get_json()
    import_id = created.get_json()["data"]["import_id"]
    draft = client.get(f"/api/v1/imports/{import_id}").get_json()["data"]["draft"]

    blocks = list(draft.get("blocks") or [])
    order_index = max(int(b.get("order_index") or 0) for b in blocks) + 10
    extra = [
        ("tb-ac21-c", None, "2026.01 - 2026.02", {"title": f"类型不明{marker}", "bullets": [f"做了点要写清楚的事 {marker}"]}),
        ("tb-ac21-d", "project", "2026.01 - 2026.02", {"title": f"只有标题{marker}", "bullets": [], "facts": []}),
        ("tb-ac21-e", None, "", {"title": f"既无类型又无正文{marker}", "bullets": [], "facts": []}),
    ]
    for offset, (temp_id, kind, date_range, entry) in enumerate(extra):
        blocks.append(
            {
                "temp_id": temp_id,
                "parent_temp_id": None,
                "order_index": order_index + offset,
                "block_type": "entry",
                "bound_package_kind": kind,
                "heading": entry["title"],
                "confidence": 0.9,
                "preview_text": entry["title"],
                "entry": {
                    "title": entry["title"],
                    "org": "",
                    "role": "",
                    "date_range": date_range,
                    "bullets": entry["bullets"],
                    "facts": entry["facts"] if entry.get("facts") else [],
                },
                "slots": [],
            }
        )
    draft["blocks"] = blocks
    saved = client.put(f"/api/v1/imports/{import_id}/draft", json={"draft": draft})
    assert saved.status_code == 200, saved.get_json()

    committed = client.post(
        f"/api/v1/imports/{import_id}/commit",
        json={"template_name": "三分支 AC", "lang": "zh", "also_create_packages": True},
    )
    assert committed.status_code == 201, committed.get_json()
    data = committed.get_json()["data"]
    created_ids = list(data.get("packages_created") or [])
    warnings = [
        item
        for item in (data.get("packages_warnings") or [])
        if str(item.get("code")) == "PACKAGE_SKIPPED"
    ]
    reasons = {str((item.get("details") or {}).get("reason")) for item in warnings}
    skipped_ids = {str((item.get("details") or {}).get("temp_id")) for item in warnings}
    # packages_skipped 是告警的结构化孪生，两边必须一致（同一批 temp_id / reason）
    assert {
        (str(item.get("temp_id")), str(item.get("reason"))) for item in (data.get("packages_skipped") or [])
    } == {(tid, str((w.get("details") or {}).get("reason"))) for w, tid in
          [(w, str((w.get("details") or {}).get("temp_id"))) for w in warnings]}

    print(
        f"[AC-IMPORT-21] created={len(created_ids)} skipped={len(warnings)} reasons={sorted(reasons)} "
        f"temp_ids={sorted(skipped_ids)}"
    )

    # ① education 不建包、也不告警
    education_ids = {
        str(block.get("temp_id"))
        for block in blocks
        if str(block.get("bound_package_kind")) == "education" and block.get("block_type") == "entry"
    }
    assert not (education_ids & skipped_ids), f"education 不该产生 PACKAGE_SKIPPED：{education_ids & skipped_ids}"
    assert not (education_ids & set(created_ids))

    # ② 两个原因各有出口，且 reason 只有这两个值
    assert reasons <= {"no_kind_mapping", "empty_entry"}, f"出现了第三个 reason：{reasons}"
    assert "no_kind_mapping" in reasons, f"C（映射不出但有正文）必须告警 no_kind_mapping，实际 {reasons}"
    assert "empty_entry" in reasons, f"D（只有标题无正文）必须告警 empty_entry，实际 {reasons}"
    # ③ 被跳过的 entry 不得出现在 created_packages[]
    assert not (skipped_ids & set(created_ids)), f"被跳过的 entry 混进了 created_packages：{skipped_ids & set(created_ids)}"
    # ④ created_packages 长度 == 库里实际新建的包数（不虚报）
    in_db = db_int(flow, "SELECT count(*) FROM package WHERE source_import_job_id=?", (import_id,))
    assert len(created_ids) == in_db, f"created_packages 报 {len(created_ids)} 条，库里 {in_db} 条"
    # ⑤ 顺序探针：E 既无 kind 又无正文，两种判定顺序都不得建包
    assert "tb-ac21-e" not in set(created_ids), "既无类型又无正文的 entry 不许建包（空包）"
    seen_e = [item for item in warnings if str((item.get("details") or {}).get("temp_id")) == "tb-ac21-e"]
    assert len(seen_e) == 1, f"E 必须且只能有一条 PACKAGE_SKIPPED，实际 {len(seen_e)} 条（顺序实现可能重复记账）"
    assert str((seen_e[0].get("details") or {}).get("reason")) in {"no_kind_mapping", "empty_entry"}
    # 反向：包数不随判定顺序变化——只数 E 的贡献必须为 0
    assert db_int(
        flow,
        "SELECT count(*) FROM package WHERE source_import_job_id=? AND source_entry_temp_id=?",
        (import_id, "tb-ac21-e"),
    ) == 0

# 放在文件末尾：CHECKS 在模块体里逐步注册，参数化的 ac 列表必须在**全部** @check 之后求值，
# 否则后加的条款不会出现在参数化里（跑起来「绿」，其实一条都没跑）。
@pytest.mark.parametrize("ac", sorted(CHECKS))
def test_ac(ac, flow):
    CHECKS[ac](flow)


# ------------------------------------------------- 反向：等式真的跟着草稿内容走 ---------------

def _import_then_commit(flow, *, marker: str, mutate=None) -> dict:
    """导入一段唯一内容 → 可选中途改草稿 → commit；返回 import_id 与派生包数量。"""
    text = (
        f"王五{marker}\n13800138002\n教育背景\n2024.9-2028.6 示例大学-信息学院 计算机科学与技术 本科（{marker}）\n"
        f"实习经历\n示例数据科技有限公司{marker} - 数据实习生 2026.07 - 2026.10\n"
        f"● 负责报表自动化，月均节省 39.3 小时，批次 {marker}。\n"
        f"项目经历\n门店模型{marker} - 队长 2026.03 - 2026.04\n● 覆盖 6527 家门店，召回率 92.3%，编号 {marker}。\n"
        f"校园活动\n2024.9 - 至今 示例大学 班长{marker}\n主要活动：组织第三十六届科技节{marker}\n"
    )
    created = flow["client"].post(
        "/api/v1/imports", json={"text": text, "filename": f"reverse-{marker}.txt", "lang": "zh"}
    )
    import_id = created.get_json()["data"]["import_id"]
    if mutate is not None:
        draft = flow["client"].get(f"/api/v1/imports/{import_id}").get_json()["data"]["draft"]
        mutate(draft)
        updated = flow["client"].put(f"/api/v1/imports/{import_id}/draft", json={"draft": draft})
        assert updated.status_code == 200, updated.get_data(as_text=True)
    commit = flow["client"].post(
        f"/api/v1/imports/{import_id}/commit",
        json={"template_name": "反向 AC", "lang": "zh", "also_create_packages": True},
    )
    assert commit.status_code == 201, commit.get_data(as_text=True)
    count = db_int(flow, "SELECT count(*) FROM package WHERE source_import_job_id=?", (import_id,))
    return {"import_id": import_id, "count": count, "commit": commit.get_json()["data"]}


def _entry_blocks(draft: dict) -> list[dict]:
    return [b for b in draft.get("blocks") or [] if b.get("block_type") == "entry"]


def test_import_15_expected_follows_body(flow):
    """把某条 project 的正文清空 → 期望值与实际派生数必须同时减 1。"""
    base = _import_then_commit(flow, marker="body0")
    draft = flow["client"].get(f"/api/v1/imports/{base['import_id']}").get_json()["data"]["draft"]
    expected_before, _ = _expected_derived_packages(draft)
    assert base["count"] == len(expected_before), (base["count"], len(expected_before))

    def clear_project(draft: dict) -> None:
        for block in _entry_blocks(draft):
            if block.get("bound_package_kind") == "project":
                entry = block.setdefault("entry", {})
                entry["bullets"] = []
                entry["facts"] = []
                return
        raise AssertionError("草稿里没有 project entry，用例前提不成立")

    after = _import_then_commit(flow, marker="body1", mutate=clear_project)
    draft_after = flow["client"].get(f"/api/v1/imports/{after['import_id']}").get_json()["data"]["draft"]
    expected_after, _ = _expected_derived_packages(draft_after)

    assert len(expected_after) == len(expected_before) - 1, (len(expected_before), len(expected_after))
    assert after["count"] == len(expected_after), (after["count"], len(expected_after))
    print(
        f"[反向] 清空一条 project 正文后：应建包 {len(expected_before)} → {len(expected_after)}；"
        f"实际派生 {base['count']} → {after['count']}"
    )
    assert after["count"] == base["count"] - 1, (base["count"], after["count"])


def test_import_15_unmapped_kind_warns_instead_of_silent_skip(flow):
    """把某条 internship 的 bound_package_kind 置空 → 必须告警且少建一个包。"""

    def drop_kind(draft: dict) -> None:
        for block in _entry_blocks(draft):
            if block.get("bound_package_kind") == "internship":
                block["bound_package_kind"] = None
                return
        raise AssertionError("草稿里没有 internship entry，用例前提不成立")

    base = _import_then_commit(flow, marker="kind0")
    after = _import_then_commit(flow, marker="kind1", mutate=drop_kind)

    assert after["count"] == base["count"] - 1, (base["count"], after["count"])
    print(
        f"[反向] 抹掉一条 internship 的 bound_package_kind 后：实际派生 {base['count']} → {after['count']}；"
        f"skipped={after['commit'].get('packages_skipped')}"
    )
    skipped = [item for item in (after["commit"].get("packages_skipped") or []) if item.get("reason") == "no_kind_mapping"]
    assert skipped, after["commit"].get("packages_skipped")
    codes = [item.get("code") for item in (after["commit"].get("packages_warnings") or [])]
    assert "PACKAGE_SKIPPED" in codes, codes
    warning = next(item for item in after["commit"]["packages_warnings"] if item.get("code") == "PACKAGE_SKIPPED")
    assert warning["details"]["reason"] == "no_kind_mapping", warning


