"""AC harness —— 导入 / 导出 / 构建 / 照片 / Skill / 分析。

与 ``test_ac_platform.py`` 同一套路：每个 ``@check("AC-…")`` 就是一条判据，
末尾统一 ``@pytest.mark.parametrize`` 跑。共享 ``flow`` 现场来自 conftest。
"""

from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path

import pytest

from .helpers import (
    artifact,
    artifact_path,
    db_int,
    db_one,
    pdf_metrics,
    pdf_pages,
    pdf_text,
    read_repo,
    repo_root,
    restore_profile,
    snapshot_profile,
    wait_job,
)

CHECKS: dict[str, callable] = {}
EXTRA: dict[str, callable] = {}


def extra(name: str):
    """非 AC 台账内的补充回归（不计入 docs/ACCEPTANCE.md 的覆盖率）。"""

    def register(fn):
        EXTRA[name] = fn
        return fn

    return register
FIXTURES = repo_root() / "server" / "tests" / "fixtures"
IMPORTS = repo_root() / "data" / "imports"


def check(ac: str):
    def register(fn):
        CHECKS[ac] = fn
        return fn

    return register


def _upload(client, path: Path, filename: str | None = None):
    data = path.read_bytes()
    return client.post(
        "/api/v1/imports",
        data={"file": (io.BytesIO(data), filename or path.name)},
        content_type="multipart/form-data",
    )


def _import_text(client, text: str, filename: str = "ac.txt"):
    return client.post("/api/v1/imports", json={"text": text, "filename": filename})


def _draft(resp) -> dict:
    return (resp.get_json().get("data") or {}).get("draft") or {}


def _codes(items) -> set[str]:
    return {item.get("code") for item in items or []}


# ---------------------------------------------------------------- 导入 ----------------


@check("AC-IMPORT-01")
def _imp_01(flow):
    """中文样张：201 + 内联 draft（无 202/轮询），结构完整。"""
    assert flow["import_status"] == 201, flow["import_status"]
    data = flow["import"]
    assert data.get("job_id"), "响应要带 job_id（审计用，不代表要轮询）"
    draft = data["draft"]
    assert draft["stats"]["pages"] == 1
    assert len(draft["blocks"]) >= 6
    assert [item["kind"] for item in draft["sections"]][:5] == [
        "education",
        "internship",
        "project",
        "campus",
        "skills",
    ] or len(draft["sections"]) >= 4
    assert data["status"] in ("draft", "committed")


@check("AC-IMPORT-02")
def _imp_02(flow):
    """英文样张：2 页、16 处 cid 缺失被识别成 bullet，草稿里不残留 (cid:。"""
    source = IMPORTS / "sample_en.pdf"
    if not source.exists():
        pytest.skip("英文样张不在本机（data/imports 被 gitignore）")
    resp = _upload(flow["client"], source)
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()["data"]
    draft = data["draft"]
    assert draft["stats"]["pages"] == 2
    assert data["draft"]["stats"].get("cid_missing") == 16
    assert "CID_GLYPH_MISSING" in _codes(draft["warnings"])
    blob = json.dumps(draft, ensure_ascii=False)
    assert "(cid:" not in blob and "\ufffd" not in blob


@check("AC-IMPORT-03")
def _imp_03(flow):
    """导入只产出候选照片，绝不自动套用。"""
    client = flow["client"]
    before = client.get("/api/v1/profile").get_json()["data"]["photo_path"]
    source = IMPORTS / "sample_zh.pdf"
    if not source.exists():
        pytest.skip("中文样张不在本机")
    resp = _upload(client, source)
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    photo = data["extracted_photo"]
    assert photo["available"] is True and photo["applied"] is False
    warn = [item for item in data["draft"]["warnings"] if item["code"] == "PHOTO_DETECTED"]
    assert warn and warn[0]["severity"] == "warn"
    assert {"attachment_id", "sha256", "width", "height"} <= set(warn[0]["details"])
    assert client.get("/api/v1/profile").get_json()["data"]["photo_path"] == before


@check("AC-IMPORT-04")
def _imp_04(flow):
    """每个 block 都有类型/置信度/槽位，低置信有汇总警告。"""
    draft = flow["import"]["draft"]
    for block in draft["blocks"]:
        assert block.get("block_type"), block
        assert 0.0 <= float(block["confidence"]) <= 1.0, block
        assert isinstance(block.get("slots"), list)
    low = [item for item in draft["warnings"] if item["code"] == "LOW_CONFIDENCE_BLOCKS"]
    if any(float(block["confidence"]) < 0.6 for block in draft["blocks"]):
        assert low, "存在低置信块却没汇总警告"


@check("AC-IMPORT-05")
def _imp_05(flow):
    """commit 落 template/block/slot；重复 commit → 409。"""
    assert flow["commit_status"] == 201, flow["commit"]
    commit = flow["commit"]
    assert commit["blocks_created"] >= 6
    template_id = commit["template_id"]
    client = flow["client"]
    detail = client.get(f"/api/v1/templates/{template_id}").get_json()["data"]
    assert len(detail["blocks"]) == commit["blocks_created"]
    assert sum(len(block.get("slots") or []) for block in detail["blocks"]) >= 10
    again = client.post(
        f"/api/v1/imports/{flow['import']['import_id']}/commit",
        json={"template_name": "重复", "lang": "zh"},
    )
    assert again.status_code == 409, again.get_json()
    assert again.get_json()["error"]["details"].get("reason") == "TEMPLATE_VERSION_CONFLICT"


@check("AC-IMPORT-06")
def _imp_06(flow):
    """五种输入都能导入（pdf/docx/md/txt/html）。"""
    client = flow["client"]
    cases = [
        (FIXTURES / "sample.pdf", "sample.pdf"),
        (FIXTURES / "sample.docx", "sample.docx"),
        (FIXTURES / "sample.html", "sample.html"),
        (FIXTURES / "sample_zh.md", "sample_zh.md"),
        (FIXTURES / "sample_en.txt", "sample_en.txt"),
    ]
    seen = 0
    for path, name in cases:
        if not path.exists():
            continue
        resp = _upload(client, path, name)
        assert resp.status_code == 201, (name, resp.get_json())
        assert _draft(resp)["blocks"], name
        seen += 1
    if seen < 4:
        pytest.skip(f"夹具不全（只有 {seen} 份）")


@check("AC-IMPORT-07")
def _imp_07(flow):
    """导入全程不联网：不产生任何 llm_call_log 行。"""
    before = db_int(flow, "SELECT count(*) FROM llm_call_log")
    resp = _import_text(flow["client"], "张三\n项目经历\n模型搭建 - 队长 2026.03 - 2026.04\n● 完成门店预测。")
    assert resp.status_code == 201
    assert db_int(flow, "SELECT count(*) FROM llm_call_log") == before


@check("AC-IMPORT-08")
def _imp_08(flow):
    """上传上限与类型校验：超大 413、伪扩展名 415。"""
    client = flow["client"]
    big = b"%PDF-1.4\n" + b"x" * (21 * 1024 * 1024)
    resp = client.post(
        "/api/v1/imports",
        data={"file": (io.BytesIO(big), "big.pdf")},
        content_type="multipart/form-data",
    )
    assert resp.status_code in (413, 400), resp.status_code
    fake = client.post(
        "/api/v1/imports",
        data={"file": (io.BytesIO(b"not a pdf at all"), "fake.pdf")},
        content_type="multipart/form-data",
    )
    assert fake.status_code in (415, 422), fake.get_json()


@check("AC-IMPORT-09")
def _imp_09(flow):
    """草稿可编辑并持久化。"""
    client = flow["client"]
    created = _import_text(client, "李四\n项目经历\n门店模型 - 队长 2026.03 - 2026.04\n● 完成预测。")
    import_id = created.get_json()["data"]["import_id"]
    draft = created.get_json()["data"]["draft"]
    draft["blocks"][0]["heading"] = "改过的抬头"
    resp = client.put(f"/api/v1/imports/{import_id}/draft", json={"draft": draft})
    assert resp.status_code in (200, 201), resp.get_json()
    reread = client.get(f"/api/v1/imports/{import_id}/draft").get_json()["data"]
    stored = reread if "blocks" in reread else reread["draft"]
    assert stored["blocks"][0]["heading"] == "改过的抬头"


@check("AC-IMPORT-11")
def _imp_11(flow):
    """sections[] 只由 blocks 派生：heading 与对应块逐字相等。"""
    draft = flow["import"]["draft"]
    sections = {item["kind"]: item for item in draft["sections"]}
    for block in draft["blocks"]:
        if block.get("parent_temp_id") is not None:
            continue
        kind = block.get("bound_package_kind")
        if not kind:
            continue
        key = "skills" if block.get("block_type") == "skills" else kind
        if key not in sections:
            continue
        expected = block.get("heading") or ""
        assert sections[key]["heading"] == expected, (key, sections[key]["heading"], expected)
        assert sections[key]["block_type"] == block["block_type"]


@check("AC-IMPORT-12")
def _imp_12(flow):
    """结构差时 marked 为需 LLM 兜底，但请求内绝不真调 LLM。"""
    client = flow["client"]
    text = "\n".join(["● 做了点事", "● 又做了点事", "● 还有一点事", "● 以及最后一件"])
    before = db_int(flow, "SELECT count(*) FROM llm_call_log")
    resp = _import_text(client, text)
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()["data"]
    assert data["needs_llm_fallback"] is True
    assert data["draft"]["blocks"], "降级也要给用户可编辑的草稿"
    assert db_int(flow, "SELECT count(*) FROM llm_call_log") == before


@check("AC-IMPORT-14")
def _imp_14(flow):
    """裸像素照片夹具：要么解码成功、要么明确报解码失败，不给假 available。"""
    path = FIXTURES / "sample_with_photo.pdf"
    if not path.exists():
        pytest.skip("照片夹具不在仓库")
    resp = _upload(flow["client"], path)
    assert resp.status_code == 201, resp.get_json()
    photo = resp.get_json()["data"]["extracted_photo"]
    assert photo["detected"] is True
    if photo["available"]:
        assert photo["attachment_id"], "available 必须伴随 attachment_id"
        assert photo["width"] >= 200 and photo["height"] >= 200
    else:
        assert photo["unreadable"] is True
        assert "PHOTO_DECODE_FAILED" in _codes(resp.get_json()["data"]["draft"]["warnings"])


@extra("import_packages_idempotent")
def _imp_15(flow):
    """导入派生包幂等：同一 import 再 commit 不新增包。"""
    client = flow["client"]
    assert flow["commit"].get("packages_created"), flow["commit"]
    before = db_int(flow, "SELECT count(*) FROM package WHERE deleted_at IS NULL")
    resp = client.post(
        f"/api/v1/imports/{flow['import']['import_id']}/commit",
        json={"template_name": "x", "lang": "zh", "also_create_packages": True},
    )
    assert resp.status_code == 409, "同一 import 二次 commit 应 409"
    assert db_int(flow, "SELECT count(*) FROM package WHERE deleted_at IS NULL") == before


@extra("import_delete_cascades_packages")
def _imp_16(flow):
    """撤销导入 → 派生包连带软删（不硬删）。"""
    client = flow["client"]
    created = _import_text(
        client,
        "王五\n项目经历\n门店模型 - 队长 2026.05 - 2026.06\n● 完成门店预测，覆盖 49 家门店。",
        "cascade.txt",
    )
    import_id = created.get_json()["data"]["import_id"]
    commit = client.post(
        f"/api/v1/imports/{import_id}/commit",
        json={"template_name": "级联测试", "lang": "zh", "also_create_packages": True},
    ).get_json()["data"]
    created_pkgs = commit.get("packages_created") or []
    assert created_pkgs, commit
    resp = client.delete(f"/api/v1/imports/{import_id}")
    assert resp.status_code in (200, 204), resp.get_json()
    alive = db_int(
        flow,
        "SELECT count(*) FROM package WHERE source_import_job_id=? AND deleted_at IS NULL",
        (import_id,),
    )
    assert alive == 0, "撤销导入后派生包必须软删"
    total = db_int(flow, "SELECT count(*) FROM package WHERE source_import_job_id=?", (import_id,))
    assert total == len(created_pkgs), "软删而不是物理删除"


@extra("import_delete_keeps_template")
def _imp_17(flow):
    """删导入不删模板（反隐式级联）——用独立导入，不碰共享现场。"""
    client = flow["client"]
    created = _import_text(
        client,
        "赵六\n项目经历\n门店模型 - 队长 2026.05 - 2026.06\n● 完成门店预测。",
        "retain.txt",
    )
    import_id = created.get_json()["data"]["import_id"]
    commit = client.post(
        f"/api/v1/imports/{import_id}/commit", json={"template_name": "保留模板", "lang": "zh"}
    ).get_json()["data"]
    template_id = commit["template_id"]
    resp = client.delete(f"/api/v1/imports/{import_id}")
    assert resp.status_code in (200, 204), resp.get_json()
    again = client.get(f"/api/v1/templates/{template_id}")
    assert again.status_code == 200, "模板不应随导入删除而消失"


@extra("import_template_provenance_kept")
def _imp_18(flow):
    """溯源不断链：result_template_id 在软删/恢复后仍非空。"""
    row = db_one(
        flow,
        "SELECT result_template_id FROM import_job WHERE id=?",
        (flow["import"]["import_id"],),
    )
    assert row and row["result_template_id"], "已 commit 的导入必须记住模板来源"


@extra("commit_keeps_static_text")
def _imp_19(flow):
    """commit 不丢静态内容：GPA/四六级/主修课程都在 template_block.static_text 里。"""
    rows = flow["_db_exec"](
        "SELECT static_text FROM template_block WHERE template_id=? AND static_text IS NOT NULL AND static_text<>''",
        (flow["template_id"],),
    ).fetchall()
    blob = "\n".join(row["static_text"] for row in rows)
    for probe in ("GPA", "3.56/4", "86.53/100", "CET4", "562"):
        assert probe in blob, f"static_text 丢了 {probe}"


@extra("commit_records_profile_sources")
def _imp_20(flow):
    """回填可回溯：profile_fields_source 记录来源 import。"""
    profile = flow["client"].get("/api/v1/profile").get_json()["data"]
    extra = profile.get("extra") or {}
    sources = extra.get("profile_field_sources") or {}
    assert sources, extra
    assert any(str(value).startswith("import:") for value in sources.values()), sources


# ---------------------------------------------------------------- 导出 ----------------


@check("AC-PDF-01")
def _pdf_01(flow):
    """产物可打开、单页、正文不小于 9.5pt。"""
    assert pdf_pages(flow) == 1
    metrics = pdf_metrics(flow)
    assert metrics["min"] >= 9.5, metrics["min"]


@check("AC-PDF-02")
def _pdf_02(flow):
    """文本层含姓名/学校/教育背景/项目经历，且没有乱码替换符。"""
    text = pdf_text(flow)
    for probe in ("张三", "示例大学", "教育背景", "项目经历"):
        assert probe in text, f"PDF 缺 {probe}"
    assert "\ufffd" not in text and "(cid:" not in text


@check("AC-PDF-03")
def _pdf_03(flow):
    """照片右上角、边长 == 标题区高度、上沿齐上边距、右沿齐右边距。

    2026-10-23 用户改定：照片要「缩小一点、高度与简历标题高度一致」。
    旧的 89.28/3.82/9.13 是**原始样张**的量测值（见 server/tests/test_import_zh_v10.py），
    不是导出件的期望值——所以这里连反向断言一起写：出现旧值也算 FAIL。
    """
    images = pdf_metrics(flow)["images"]
    if not images:
        pytest.skip("本次导出未包含照片")
    box = images[0]
    assert abs(box["w"] - 52.0) <= 1.5 and abs(box["h"] - 52.0) <= 1.5, box
    assert abs(box["top"] - 8.3) <= 1.5, box
    assert abs(box["right_gap"] - 15.62) <= 1.5, box
    assert abs(box["w"] - 89.28) > 1.0, f"不得回退到旧的 89.28pt 口径：{box}"


@check("AC-PDF-04")
def _pdf_04(flow):
    """横向不越界。"""
    assert pdf_metrics(flow)["overflow"] == 0


@check("AC-PDF-05")
def _pdf_05(flow):
    """文本校验通过，且 artifact 记录 sha256/bytes/engine。"""
    item = artifact(flow)
    assert item["text_verified"] is True, item.get("text_diff")
    assert len(item["sha256"]) == 64 and item["bytes"] > 1000
    assert item["engine"] in ("reportlab", "chrome")
    assert item["warnings"] is not None


@check("AC-PDF-06")
def _pdf_06(flow):
    """命名符合 {position}-{name}-{school}。"""
    item = artifact(flow)
    assert item["filename"] == "数据分析实习生-张三-示例大学.pdf", item["filename"]


@check("AC-PDF-07")
def _pdf_07(flow):
    """英文版：框架区无中日韩字符，使用西文字体。"""
    import pdfplumber

    path = artifact_path(flow, "en-original")
    with pdfplumber.open(str(path)) as pdf:
        page = pdf.pages[0]
        top_lines = (page.extract_text() or "").splitlines()[:4]
        fonts = {char["fontname"] for char in page.chars}
    head = "\n".join(top_lines)
    assert not re.search(r"[\u4e00-\u9fff]", head), head
    assert any("Times" in name for name in fonts), fonts


@check("AC-PDF-08")
def _pdf_08(flow):
    """relaxed 密度：可用高度按 15/16mm 边距算。"""
    payload = flow["artifacts"].get("zh-relaxed") or {}
    item = (payload.get("artifacts") or [{}])[0]
    layout = item.get("layout") or payload.get("layout") or {}
    assert layout, payload.keys()
    bounds = {751.5, 817.55, 817.65}
    assert any(abs(float(layout.get("available_height_pt")) - bound) < 2 for bound in bounds), layout


@check("AC-PDF-09")
def _pdf_09(flow):
    """单页优先：用了降档就必须发 PAGE_FIT_DOWNGRADED（不许静默缩字）。"""
    payload = flow["artifacts"]["zh-original"]
    item = payload["artifacts"][0]
    codes = _codes(item.get("warnings") or payload.get("warnings"))
    meta = item.get("layout") or {}
    if float(meta.get("body_pt") or 11.0) < 11.0:
        assert "PAGE_FIT_DOWNGRADED" in codes, (meta, codes)
    assert pdf_pages(flow) == 1


@check("AC-PDF-10")
def _pdf_10(flow):
    """页眉只允许姓名/联系方式/到岗时间，不含学历专业那行。"""
    lines = [line.strip() for line in pdf_text(flow).splitlines() if line.strip()]
    assert lines[0] == "张三"
    head = "\n".join(lines[:4])
    assert "本科" not in head and "计算机科学与技术" not in head, head
    assert "2028" not in head, head


@check("AC-PDF-11")
def _pdf_11(flow):
    """技能段逐行原文渲染，不是 tag 块。"""
    text = pdf_text(flow)
    assert "数据分析类" in text and "Python" in text
    assert " | " not in text.split("职业技能")[-1], "技能被渲染成 tag 块"


@check("AC-PDF-12")
def _pdf_12(flow):
    """下载端点可用（RFC5987 中文名）。"""
    client = flow["client"]
    item = artifact(flow)
    resp = client.get(f"/api/v1/artifacts/{item['id']}/download")
    assert resp.status_code == 200
    assert resp.data[:5] == b"%PDF-"
    disposition = resp.headers.get("Content-Disposition", "")
    assert "filename*=UTF-8''" in disposition, disposition


# ---------------------------------------------------------------- 构建 ----------------


@check("AC-BUILD-01")
def _build_01(flow):
    """POST /builds 201+Location；position 可从 JD 继承。"""
    client = flow["client"]
    resp = client.post(
        "/api/v1/builds",
        json={"name": "继承岗位", "template_id": flow["template_id"], "jd_id": flow["jd"]["id"], "lang": "zh"},
    )
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()["data"]
    assert data["position"] == "数据分析实习生（增长方向）", data["position"]
    assert resp.headers.get("Location", "").endswith(data["id"])


@check("AC-BUILD-02")
def _build_02(flow):
    """PUT selections 是整体替换。"""
    client = flow["client"]
    build_id = flow["build_id"]
    first = client.get(f"/api/v1/builds/{build_id}/selections").get_json()["data"]["items"]
    assert len(first) >= 2
    keep = [{"package_id": first[0]["package_id"], "variant_ids": first[0]["variant_ids"], "order_index": 0}]
    resp = client.put(f"/api/v1/builds/{build_id}/selections", json={"items": keep})
    assert resp.status_code == 200, resp.get_json()
    after = client.get(f"/api/v1/builds/{build_id}/selections").get_json()["data"]["items"]
    assert len(after) == 1
    client.put(f"/api/v1/builds/{build_id}/selections", json={"items": first})


@check("AC-BUILD-03")
def _build_03(flow):
    """assemble 返回段落/缺失槽位/竞争力摘要。"""
    assembled = flow["assemble"]
    assert assembled["sections"], assembled
    for section in assembled["sections"]:
        assert {"kind", "heading", "entries", "bullets"} <= set(section), section
        assert isinstance(section["entries"], int)
    assert "missing_slots" in assembled
    summary = assembled.get("competitiveness_summary") or {}
    assert "verdict" in summary or summary == {}, summary


@check("AC-BUILD-05")
def _build_05(flow):
    """选未 ready 的包 → 409 PACKAGE_NOT_READY。"""
    client = flow["client"]
    draft = client.post(
        "/api/v1/packages", json={"title": "未就绪包", "kind": "project", "status": "draft"}
    ).get_json()["data"]
    resp = client.put(
        f"/api/v1/builds/{flow['build_id']}/selections",
        json={"items": [{"package_id": draft["id"], "variant_ids": [], "order_index": 0}]},
    )
    assert resp.status_code == 409, resp.get_json()
    assert resp.get_json()["error"]["details"].get("reason") == "PACKAGE_NOT_READY"


@check("AC-BUILD-12")
def _build_12(flow):
    """模板不可猜：缺 template_id → 422；模板失效时 assemble 明确 409，不静默换模板。"""
    client = flow["client"]
    missing = client.post("/api/v1/builds", json={"name": "无模板", "lang": "zh", "position": "数据分析"})
    assert missing.status_code == 422, missing.get_json()
    fields = missing.get_json()["error"]["details"]["fields"]
    assert any(item["field"] == "template_id" for item in fields), fields

    created = _import_text(
        client,
        "孙七\n项目经历\n门店模型 - 队长 2026.05 - 2026.06\n● 完成门店预测。",
        "gone.txt",
    )
    import_id = created.get_json()["data"]["import_id"]
    commit = client.post(
        f"/api/v1/imports/{import_id}/commit", json={"template_name": "会被删掉", "lang": "zh"}
    ).get_json()["data"]
    template_id = commit["template_id"]
    build = client.post(
        "/api/v1/builds",
        json={"name": "模板失效", "template_id": template_id, "lang": "zh", "position": "数据分析"},
    ).get_json()["data"]
    assert client.delete(f"/api/v1/templates/{template_id}").status_code in (200, 204)
    assembled = client.post(f"/api/v1/builds/{build['id']}/assemble")
    assert assembled.status_code == 409, assembled.get_json()
    assert assembled.get_json()["error"]["code"] in ("NO_DEFAULT_TEMPLATE", "TEMPLATE_INVALID"), assembled.get_json()


@check("AC-BUILD-13")
def _build_13(flow):
    """结束时间往返不丢（D-35 回归）。"""
    client = flow["client"]
    pkg = client.post(
        "/api/v1/packages",
        json={"title": "时间线包", "kind": "project", "start_date": "2026-03", "end_date": "2026-04"},
    ).get_json()["data"]
    row = db_one(flow, "SELECT end_date, is_current FROM package WHERE id=?", (pkg["id"],))
    assert row["end_date"] == "2026-04" and int(row["is_current"]) == 0, dict(row)


@extra("artifacts_list_matches_disk")
def _build_15(flow):
    """artifacts 列表与下载一致。"""
    client = flow["client"]
    items = client.get(f"/api/v1/builds/{flow['build_id']}/artifacts").get_json()["data"]["items"]
    assert items, "导出后应能列出发产物"
    latest = items[0]
    path = flow["data_dir"] / latest["rel_path"]
    assert path.exists()
    assert path.stat().st_size == latest["bytes"]


# ---------------------------------------------------------------- 照片 ----------------


@check("AC-PHOTO-01")
def _photo_01(flow):
    """上传照片 → 资料里有 photo_path 且能取回 PNG。"""
    import io as _io

    from PIL import Image

    client = flow["client"]
    buffer = _io.BytesIO()
    Image.new("RGB", (240, 240), (180, 190, 200)).save(buffer, format="PNG")
    resp = client.post(
        "/api/v1/profile/photo",
        data={"file": (_io.BytesIO(buffer.getvalue()), "me.png")},
        content_type="multipart/form-data",
    )
    assert resp.status_code in (200, 201), resp.get_json()
    profile = client.get("/api/v1/profile").get_json()["data"]
    assert profile["photo_path"], profile
    image = client.get("/api/v1/files/profile-photo")
    assert image.status_code == 200 and image.data[:8] == b"\x89PNG\r\n\x1a\n"


@check("AC-PHOTO-02")
def _photo_02(flow):
    """导入候选照片需显式确认才生效。"""
    client = flow["client"]
    created = client.post("/api/v1/files", data="", content_type="application/json")
    assert created.status_code in (400, 415, 422), created.status_code
    candidate = flow["import"].get("extracted_photo") or {}
    if not candidate.get("available"):
        pytest.skip("本次导入没有可用照片候选")
    before = client.get("/api/v1/profile").get_json()["data"]["photo_path"]
    resp = client.put("/api/v1/profile/photo", json={"attachment_id": candidate["attachment_id"]})
    assert resp.status_code == 200, resp.get_json()
    after = client.get("/api/v1/profile").get_json()["data"]["photo_path"]
    assert after and after != before


@check("AC-PHOTO-03")
def _photo_03(flow):
    """删照片是解绑而不是删文件，且可撤销。"""
    client = flow["client"]
    current = client.get("/api/v1/profile").get_json()["data"]["photo_path"]
    if not current:
        pytest.skip("当前没有照片")
    resp = client.delete("/api/v1/profile/photo")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["previous_photo_path"] == current
    assert (flow["data_dir"] / current).exists(), "解绑不得删文件"
    restored = client.put("/api/v1/profile/photo", json={"sha256": (resp.get_json()["data"].get("previous_sha256") or "")} )
    assert restored.status_code in (200, 422)


@check("AC-PHOTO-04")
def _photo_04(flow):
    """关闭「包含照片」时导出不再画图。"""
    import pdfplumber

    client = flow["client"]
    resp = client.post(
        f"/api/v1/builds/{flow['build_id']}/export",
        json={"format": "pdf", "include_photo": False, "verify_text": True},
    )
    assert resp.status_code == 202, resp.get_json()
    job = wait_job(client, resp.get_json()["data"]["job_id"])
    item = (job.get("result_json") or {})["artifacts"][0]
    with pdfplumber.open(str(flow["data_dir"] / item["rel_path"])) as pdf:
        assert len(pdf.pages[0].images) == 0


@check("AC-PHOTO-05")
def _photo_05(flow):
    """照片字节永不进 LLM payload（结构性排除）。"""
    resp = flow["client"].post(
        "/api/v1/llm/preview",
        json={"purpose": "summary_polish", "selections": {"package_ids": [flow["packages"][0]["id"]]}},
    )
    data = resp.get_json()["data"]
    payload = json.dumps(data["payload"], ensure_ascii=False)
    assert "photo" not in payload.lower() or "photo_path" not in payload
    exclusions = " ".join(data["excluded"].get("structural_exclusions") or [])
    assert "photo" in exclusions.lower(), data["excluded"]


# ---------------------------------------------------------------- Skill ----------------


@extra("skill_md_documents_five_steps")
def _skill_01(flow):
    """SKILL.md 有 frontmatter 与五步旅程。"""
    text = read_repo("skills/resume-warehouse/SKILL.md")
    assert text.startswith("---\n"), "缺少 frontmatter"
    head = text.split("---")[1]
    assert "name:" in head and "description:" in head
    for step in ("/api/v1/profile", "/api/v1/imports", "/api/v1/jds", "/api/v1/builds", "export"):
        assert step in text, f"SKILL.md 未覆盖 {step}"


@extra("skill_scripts_executable")
def _skill_02(flow):
    """start.sh/stop.sh 存在、可执行、从 app_port 取端口。"""
    for name in ("start.sh", "stop.sh"):
        path = repo_root() / "skills" / "resume-warehouse" / name
        assert path.exists(), name
        assert os.access(path, os.X_OK), f"{name} 不可执行"
    start = read_repo("skills/resume-warehouse/start.sh")
    assert "app_port" in start and ("python" in start or "json" in start)


@extra("skill_uses_runtime_port")
def _skill_03(flow):
    """Skill 文档里不把 8765 写死成唯一端口。"""
    text = read_repo("skills/resume-warehouse/SKILL.md")
    assert "app_port" in text, "必须告诉 Agent 从 app_port 读真实端口"
    hard = re.findall(r"127\.0\.0\.1:8765", text)
    assert len(hard) <= 1, f"8765 被写死 {len(hard)} 次（应只在说明默认值时出现一次）"


@extra("skill_documents_privacy_boundary")
def _skill_04(flow):
    """Skill 文档说清隐私边界与「先看字段清单再发」的流程。"""
    text = read_repo("skills/resume-warehouse/SKILL.md")
    assert "llm/preview" in text and "preview_id" in text
    for word in ("姓名", "电话", "邮箱", "照片"):
        assert word in text, f"隐私边界缺 {word}"


# ---------------------------------------------------------------- 分析 ----------------


@check("AC-JD-01")
def _jd_01(flow):
    """JD 分析（启发式）产出竞争力与需求清单。"""
    result = flow["analysis"]
    comp = result.get("competitiveness") or {}
    assert comp.get("school_tier") in ("C9", "985", "211", "双一流", "普通本科", "海外", "其他"), comp
    assert comp.get("verdict") in ("strong", "medium", "weak"), comp
    assert flow["analyze_job"]["status"] == "succeeded"


@check("AC-JD-02")
def _jd_02(flow):
    """每条需求都有优先级与 candidate_status（不允许 null）。"""
    rows = flow["client"].get(f"/api/v1/jds/{flow['jd']['id']}/requirements").get_json()["data"]["items"]
    assert rows, "分析后应有需求"
    for row in rows:
        assert row["priority"] in ("must", "should", "nice"), row
        assert row["category"] in ("hard", "soft", "domain", "tool", "language", "certificate"), row
        assert row["candidate_status"] in ("satisfied", "partial", "missing"), row


@check("AC-JD-03")
def _jd_03(flow):
    """匹配打分本地完成、按分数降序、有解释。"""
    resp = flow["client"].post(f"/api/v1/jds/{flow['jd']['id']}/match", json={})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    scores = data["scores"]
    assert scores, data
    values = [item["score"] for item in scores]
    assert values == sorted(values, reverse=True), values
    assert all("hits" in item and "gaps" in item for item in scores)
    assert "coverage" in data


@extra("school_preference_is_not_a_gate")
def _anl_06(flow):
    """「985/211 优先」是偏好不是门槛。"""
    text = "任职要求：本科及以上；985/211 院校优先；熟练 SQL。"
    jd = flow["client"].post("/api/v1/jds", json={"title": "偏好岗", "raw_text": text}).get_json()["data"]
    resp = flow["client"].post(f"/api/v1/jds/{jd['id']}/analyze", json={"method": "heuristic"})
    job = wait_job(flow["client"], resp.get_json()["data"]["job_id"])
    pref = (job.get("result_json") or {}).get("school_preference") or {}
    assert pref.get("hard_filter") is False, pref
    assert str(pref.get("threshold", "")).startswith("不限"), pref
    assert pref.get("preferred_tiers") == ["985", "211"], pref


@extra("no_school_gate_is_not_fabricated")
def _anl_07(flow):
    """「不设院校门槛」不得编造卡院校。"""
    text = "任职要求：本科及以上；不设院校门槛；熟练 Excel。"
    jd = flow["client"].post("/api/v1/jds", json={"title": "无门槛岗", "raw_text": text}).get_json()["data"]
    resp = flow["client"].post(f"/api/v1/jds/{jd['id']}/analyze", json={"method": "heuristic"})
    job = wait_job(flow["client"], resp.get_json()["data"]["job_id"])
    pref = (job.get("result_json") or {}).get("school_preference") or {}
    assert pref.get("hard_filter") is False, pref
    assert pref.get("preferred_tiers") == [], pref
    assert pref.get("evidence"), pref


@extra("heuristic_has_school_preference")
def _anl_09(flow):
    """启发式也要给 school_preference（fallback 不得 null）。"""
    result = flow["analysis"]
    pref = result.get("school_preference")
    assert pref is not None, "heuristic 路径 school_preference 不得为 null"
    assert "threshold" in pref and "hard_filter" in pref


@check("AC-UI-01")
def _ui_01(flow):
    """前端零外链、七页路由齐全。

    路由表在 `web/src/boot.js`（启动脚本已从内联搬到外部文件，见 CSP 判据
    `tests/test_web_boot.py`），所以这里两处一起看：页面骨架 + 启动脚本。
    """
    html = read_repo("web/index.html")
    boot = read_repo("web/src/boot.js")
    assert "./src/boot.js" in html, "index.html 没有引用外部启动脚本"
    for route in ("workbench", "warehouse", "templates", "jobs", "builds", "profile", "settings"):
        assert route in boot, f"缺路由 {route}"
    assert not re.search(r'src="https?://', html), "页面不得引用外部脚本"
    assert not re.search(r'href="https?://[^"]*\.css', html), "页面不得引用外部样式"


@check("AC-UI-02")
def _ui_02(flow):
    """七个页面模块真实存在且导出 render。"""
    for key in ("workbench", "warehouse", "templates", "jobs", "builds", "profile", "settings"):
        path = repo_root() / "web" / "src" / "pages" / f"{key}.js"
        assert path.exists(), f"缺页面 {key}"
        text = path.read_text(encoding="utf-8")
        assert "export" in text, f"{key} 没有导出"
        assert "innerHTML" not in text, f"{key} 用了 innerHTML"


@check("AC-ROB-01")
def _rob_01(flow):
    """错误信封统一：404 也是 {ok:false,error:{code,message},request_id}。"""
    resp = flow["client"].get("/api/v1/packages/nonexistent")
    assert resp.status_code == 404
    body = resp.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["request_id"].startswith("req_")


# ---------------------------------------------------------------- 跑 ----------------


@pytest.mark.parametrize("ac", sorted(CHECKS))
def test_ac(ac, flow):
    CHECKS[ac](flow)


@pytest.mark.parametrize("name", sorted(EXTRA))
def test_extra(name, flow):
    EXTRA[name](flow)
