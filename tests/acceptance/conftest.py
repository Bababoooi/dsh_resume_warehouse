"""验收 harness 的共享现场：一个临时 DATA_DIR、一条真跑通的五步旅程。

为什么要 session 级：AC 里的断言都是「这条旅程跑出来之后，某个可观察事实成立」。
每次断言都重跑导入 + commit + 组装 + 导出会让 80 多条用例跑成几分钟，也没意义——
真正要防的是「代码改了但事实不再成立」，所以现场跑一次、断言各自读现场。
"""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RESUME_TEXT = """张三
13800138000 | zhangsan@example.com
到岗时间：2027年1月下旬
教育背景
2024.9-2028.6 示例大学-信息学院 计算机科学与技术 本科
专业成绩：GPA 3.56/4 86.53/100 CET4：562 CET6:508
主修课程：统计学(92)、数据分析与处理（R）(91)、数据结构与程序设计（Python）（90）、数据库系统原理（SQL）（90）、管理学(90)、企业战略管理(90)、机器学习(89)等。
实习经历
示例科技（杭州）有限公司 - 后端实习生 2026.07 - 2026.10
● 负责撮合系统接口开发，QPS 从 1200 提升到 6527，接口耗时下降 39.3%。
● 用 K-means 对慢查询聚类，覆盖 49 家门店、12 种场景，p=0.018。
项目经历
门店选址与订单预测模型 - 队长 2026.03 - 2026.04
● 覆盖 2200 余天历史订单，召回率 92.3%，超出基线 17 项指标。
● 用 PM₂.₅ 与 PM₁₀ 做外部特征，AUC 提升 3.56/4 分位点。
校园活动
2024.9 - 至今 示例大学 学习委员
曾获荣誉：2024-2025 学年社会实践积极分子
主要活动：组织第三十六届校园科技节，参与 AI&金融 工作坊
职业技能
数据分析类：掌握 Python、R、SQL 等编程语言，可独立进行数据清洗、统计分析与可视化处理
基础办公类：掌握 Excel 的数据透视表、VLOOKUP 函数等常用工具
AI开发类：可以借助 AI Agent 对重复性数据挖掘工作进行自动化
"""

JD_TEXT = (
    "岗位职责：负责增长实验设计与指标体系建设；搭建订单预测模型。\n"
    "任职要求：2027 届及以后毕业，本科及以上学历，985/211 院校优先；"
    "熟练掌握 SQL、Python；有 A/B 测试经验者优先。"
)


def _app_with_temp_dir():
    from app import config as config_mod
    from app import create_app
    from app import db as db_mod

    tmpdir = tempfile.mkdtemp(prefix="rw-ac-", dir=str(PROJECT_ROOT / "data" / "_tests"))
    os.environ["DATA_DIR"] = tmpdir
    config_mod.set_config(config_mod.load_config())
    db_mod.reset_paths_for_tests()
    app = create_app()
    return app, db_mod, Path(tmpdir)


@pytest.fixture(scope="session")
def flow():
    """跑通「录入 → 导入 → 分析 → 组装 → 导出」，把现场交给所有 AC 用例。"""
    from app import db as db_mod
    from app import config as config_mod

    old = os.environ.get("DATA_DIR")
    app, _db, data_dir = _app_with_temp_dir()
    client = app.test_client()
    ctx: dict = {"app": app, "client": client, "data_dir": data_dir, "errors": []}

    def _exec(sql: str, params: tuple = ()):
        conn = _db.get_conn()
        with _db.transaction(conn):
            return conn.execute(sql, params)

    ctx["_db_exec"] = _exec

    # ① 个人资料（命名模板的唯一来源）
    profile = {
        "name_zh": "张三",
        "name_en": "ZHANG SAN",
        "school_zh": "示例大学",
        "school_en": "Example University",
        "degree": "本科",
        "major": "计算机科学与技术",
        "grad_year": 2028,
        "phone": "13800138000",
        "email": "zhangsan@example.com",
        "city": "杭州",
        "available_note": "2027年1月下旬",
        "skills": [
            {"line": "数据分析类：掌握 Python、R、SQL 等编程语言", "category": "数据分析类"},
            {"line": "基础办公类：掌握 Excel 的数据透视表、VLOOKUP 函数", "category": "基础办公类"},
            {"line": "AI开发类：可以借助 AI Agent 对重复性数据挖掘工作进行自动化", "category": "AI开发类"},
        ],
    }
    resp = client.put("/api/v1/profile", json=profile)
    ctx["profile"] = resp.get_json()["data"] if resp.status_code == 200 else {}

    # ② 导入 + commit（派生模板与经历包）
    imp = client.post("/api/v1/imports", json={"text": RESUME_TEXT, "filename": "ac-resume.txt"})
    ctx["import_status"] = imp.status_code
    ctx["import"] = imp.get_json()["data"] if imp.status_code < 400 else {}
    import_id = ctx["import"].get("import_id")
    commit = client.post(
        f"/api/v1/imports/{import_id}/commit",
        json={"template_name": "AC 模板", "lang": "zh", "set_default": True, "also_create_packages": True},
    )
    ctx["commit_status"] = commit.status_code
    ctx["commit"] = commit.get_json()["data"] if commit.status_code < 400 else {}
    ctx["template_id"] = ctx["commit"].get("template_id")

    # ③ JD + 启发式分析（不花真 token）
    jd = client.post(
        "/api/v1/jds",
        json={"title": "数据分析实习生（增长方向）", "company_name": "星链数科（杭州）有限公司", "raw_text": JD_TEXT},
    )
    ctx["jd"] = jd.get_json()["data"]
    analyze = client.post(f"/api/v1/jds/{ctx['jd']['id']}/analyze", json={"method": "heuristic"})
    ctx["analyze_status"] = analyze.status_code
    job_id = (analyze.get_json().get("data") or {}).get("job_id")
    ctx["analyze_job"] = _wait_job(client, job_id) if job_id else {}
    ctx["analysis"] = (ctx["analyze_job"].get("result_json") or {})

    # ④ 组装 + 导出（zh / en / relaxed 各一份）
    packages = client.get("/api/v1/packages?limit=50&include_variants=1").get_json()["data"]["items"]
    ctx["packages"] = packages
    build = client.post(
        "/api/v1/builds",
        json={
            "name": "AC 构建",
            "template_id": ctx.get("template_id"),
            "jd_id": ctx["jd"]["id"],
            "position": "数据分析实习生",
            "company": "星链数科（杭州）有限公司",
            "lang": "zh",
            "naming_pattern": "{position}-{name}-{school}",
        },
    )
    ctx["build"] = build.get_json()["data"]
    build_id = ctx["build"]["id"]
    selections = [
        {
            "package_id": item["id"],
            "variant_ids": [v["id"] for v in item.get("variants") or []],
            "order_index": index,
        }
        for index, item in enumerate(packages[:5])
    ]
    client.put(f"/api/v1/builds/{build_id}/selections", json={"items": selections})
    ctx["assemble"] = client.post(f"/api/v1/builds/{build_id}/assemble").get_json()["data"]
    ctx["artifacts"] = {}
    build_en = client.post(
        "/api/v1/builds",
        json={
            "name": "AC 英文版",
            "template_id": ctx["template_id"],
            "lang": "en",
            "position": "Data Analyst Intern",
            "naming_pattern": "{position}-{name}-{school}",
        },
    )
    assert build_en.status_code == 201, build_en.get_json()
    build_en_id = build_en.get_json()["data"]["id"]
    client.put(f"/api/v1/builds/{build_en_id}/selections", json={"items": selections})
    ctx["build_id_en"] = build_en_id

    for lang, density in (("zh", "original"), ("en", "original"), ("zh", "relaxed")):
        target = build_en_id if lang == "en" else build_id
        export = client.post(
            f"/api/v1/builds/{target}/export",
            json={"format": "pdf", "lang": lang, "density": density, "verify_text": True},
        )
        payload = export.get_json().get("data") or {}
        job = _wait_job(client, payload.get("job_id"))
        ctx["artifacts"][f"{lang}-{density}"] = job.get("result_json") or {}
        if lang == "zh" and density == "original":
            ctx["export_job"] = job
    ctx["build_id"] = build_id

    try:
        yield ctx
    finally:
        try:
            from app.services import jobrun

            jobrun.wait_idle()
        finally:
            _db.close_conn()
            if old is None:
                os.environ.pop("DATA_DIR", None)
            else:
                os.environ["DATA_DIR"] = old
            config_mod.set_config(config_mod.load_config())
            _db.reset_paths_for_tests()
            shutil.rmtree(str(data_dir), ignore_errors=True)


def _wait_job(client, job_id, *, timeout_s: float = 120.0):
    import time

    deadline = time.time() + timeout_s
    body: dict = {}
    while time.time() < deadline:
        resp = client.get(f"/api/v1/jobs/{job_id}")
        body = resp.get_json().get("data") or {}
        if body.get("status") in ("succeeded", "failed", "interrupted"):
            return body
        time.sleep(0.05)
    return body


@pytest.fixture(scope="session")
def pdf_text(flow):
    """zh 主产物的抽取文本（pdfplumber），多个 AC 复用。"""
    import pdfplumber

    artifact = (flow["artifacts"].get("zh-original") or {}).get("artifacts") or []
    assert artifact, "zh 导出没有产物"
    path = flow["data_dir"] / "exports" / artifact[0]["filename"]
    assert path.exists(), f"产物不存在：{path}"
    with pdfplumber.open(str(path)) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        ctx = {"path": path, "text": text, "pages": len(pdf.pages), "pdf": None}
    return ctx


@pytest.fixture(scope="session")
def pdf_metrics(flow):
    """逐字符量出来的版式事实：最小字号、照片框、行高。"""
    import pdfplumber

    artifact = (flow["artifacts"].get("zh-original") or {}).get("artifacts") or []
    path = flow["data_dir"] / "exports" / artifact[0]["filename"]
    sizes: list[float] = []
    images: list[dict] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            for char in page.chars:
                if str(char.get("text") or "").strip():
                    sizes.append(round(float(char["size"]), 2))
            for image in page.images:
                box = {
                    "x0": float(image["x0"]),
                    "top": float(image["top"]) + max(0.0, -float(page.mediabox[1])),
                    "w": float(image["x1"]) - float(image["x0"]),
                    "h": float(image["bottom"]) - float(image["top"]),
                    "page_w": float(page.mediabox[2]),
                }
                images.append(box)
    return {"sizes": sorted(set(sizes)), "min_size": min(sizes) if sizes else 0.0, "images": images, "path": path}


def pdf_bytes_ok(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def png_bytes() -> bytes:
    """一张 200×200 的 PNG，用于照片相关用例（不依赖仓库里的真实证件照）。"""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (200, 200), (200, 210, 220)).save(buffer, format="PNG")
    return buffer.getvalue()


def json_dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
