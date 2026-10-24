"""pytest 夹具：每次会话一个临时 DATA_DIR + 一个 Flask test client。

纪律（captain 定的）：**测试绝不碰真实 ``data/app.db``**。
``DATA_DIR`` 必须落在项目内的 ``data/_tests/`` 下（``db.resolve_data_root`` 会拒绝外部路径），
而且每次 setup 都重新 ``set_config(load_config())``，否则缓存的旧 Config 会把写入导回真实库
（这条曾经真的发生过：91 条重复草稿落进用户真库）。
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys_path = str(PROJECT_ROOT / "server")


def pytest_configure(config):  # noqa: ARG001
    """把 ``server/`` 放进 sys.path，测试可以 ``from app import create_app``。"""
    import sys

    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)


# 会「拉起现场」的夹具：临时 DATA_DIR、建库迁移、Flask app、真服务、真浏览器。
# 一条用例只要不请求它们，就不该付出任何现场成本（应当毫秒级）。
SERVICE_FIXTURES = frozenset(
    {"app_env", "client", "data_dir", "flow", "pdf_text", "pdf_metrics", "site", "session"}
)


def pytest_collection_modifyitems(config, items):  # noqa: ARG001
    """自动给「不碰服务」的用例打 ``noservice`` 标记。

    为什么需要：单文件跑一次若要等整包（session 级夹具起真服务/真浏览器），就没人会去跑
    单文件，护栏形同虚设。标记是按**夹具名**自动打的——新增纯逻辑用例零成本，
    ``pytest -m noservice`` 永远只跑毫秒级那一层。

    只按夹具名判定、不按目录：目录会随重构搬移，夹具名才是真实依赖。
    """
    for item in items:
        fixtures = set(getattr(item, "fixturenames", ()) or ())
        if SERVICE_FIXTURES.isdisjoint(fixtures):
            item.add_marker(pytest.mark.noservice)


@pytest.fixture()
def app_env():
    """临时数据目录 + 已迁移的 app；yield 一个 (app, client, data_dir) 三元组。"""
    from app import config as config_mod
    from app import create_app
    from app import db as db_mod

    old = os.environ.get("DATA_DIR")
    tmpdir = tempfile.mkdtemp(prefix="rw-e2e-", dir=str(PROJECT_ROOT / "data" / "_tests"))
    os.environ["DATA_DIR"] = tmpdir
    config_mod.set_config(config_mod.load_config())
    db_mod.reset_paths_for_tests()
    app = create_app()
    client = app.test_client()
    try:
        yield app, client, Path(tmpdir)
    finally:
        try:
            from app.services import jobrun

            jobrun.wait_idle()
        finally:
            db_mod.close_conn()
            if old is None:
                os.environ.pop("DATA_DIR", None)
            else:
                os.environ["DATA_DIR"] = old
            config_mod.set_config(config_mod.load_config())
            db_mod.reset_paths_for_tests()
            shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture()
def client(app_env):
    return app_env[1]


@pytest.fixture()
def data_dir(app_env):
    return app_env[2]


# ---------------------------------------------------------------------------
# 共用小工具
# ---------------------------------------------------------------------------

PASTE_ZH = """张三
示例大学-本科28届 | 到岗时间：2027年1月下旬
手机号码：13800138000 | 邮箱：zhangsan@example.com

教育背景
2024.9-2028.6 示例大学-经济与管理学院 管理科学（商业数据分析） 本科
专业成绩：GPA 3.56/4 86.53/100 CET4：562 CET6:508
主修课程：统计学(92)、数据分析与处理（R）(91)、数据结构与程序设计（Python）（90）、数据库系统原理（SQL）（90）等。

实习经历
杭州拓端数据科技有限公司 - 数据处理实习生 2026.07 - 2026.10
担任数据处理实习生期间，独立负责合肥市2019年12月—2025年12月共6年、2200余天的17项逐日环境指标全链路治理。
针对导师提出的臭氧统计口径差异问题，完成全周期数据口径溯源核查，最终交付数据完整率99.7%、指标口径一致性100%的标准化数据集。

项目经历
小象超市门店选址与订单量预测模型（美团商业分析大赛） - 队员 2026.03 - 2026.04
针对门店选址与订单预测业务需求，通过整合49家门店多维度运营数据，对比12种回归模型后选定Ridge回归算法搭建订单预测模型。
在2026年全国高校商业精英挑战赛品牌策划竞赛品牌策划赛道获得校级二等奖。

校园活动
2024.9 - 至今 示例大学 学习委员
曾获荣誉：2024-2025年度经济与管理学院社会活动积极分子等。
主要活动：示例大学第三十六届珞珈金秋艺术节情景剧校三等奖。

职业技能
数据分析类：掌握Python、R、SQL等编程语言，可独立进行数据清洗、统计分析与可视化处理
基础办公类：掌握Excel的数据透视表、VLOOKUP函数等常用工具
AI开发类：可以借助AI Agent对重复性数据梳理工作进行自动化，提升处理效率
"""


def paste_import(client, text: str = PASTE_ZH, filename: str = "pasted.txt") -> str:
    """用粘贴文本导入（不依赖 data/imports 里的真实简历，测试可离线跑）。"""
    response = client.post("/api/v1/imports", json={"text": text, "filename": filename})
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["data"]["import_id"]


def upload(client, path: Path) -> str:
    payload = path.read_bytes()
    response = client.post(
        "/api/v1/imports",
        data={"file": (io.BytesIO(payload), path.name)},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["data"]["import_id"]


def bootstrap(client, *, template_name: str = "中文模板", packages: bool = True) -> dict:
    """一条命令把档案 + 模板 + 派生包准备好（大多数用例的前置）。"""
    profile = {
        "name_zh": "张三",
        "name_en": "SAN ZHANG",
        "school_zh": "示例大学",
        "school_en": "Example University",
        "degree": "本科",
        "major": "管理科学（商业数据分析）",
        "grad_year": 2028,
        "city": "武汉",
        "available_note": "2027年1月下旬",
        "extra": {
            "degree_en": "B.M.",
            "major_en": "Management Science (Business Data Analytics)",
            "city_en": "Wuhan",
            "available_note_en": "Early July 2026",
        },
    }
    response = client.put("/api/v1/profile", json=profile)
    assert response.status_code == 200, response.get_data(as_text=True)

    import_id = paste_import(client)
    response = client.post(
        f"/api/v1/imports/{import_id}/commit",
        json={"template_name": template_name, "lang": "zh", "set_default": True, "also_create_packages": packages},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["data"]


def default_template_id(client, lang: str = "zh") -> str:
    response = client.get(f"/api/v1/templates/default?lang={lang}")
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()["data"]["id"]


def make_build(client, *, lang: str = "zh", position: str = "数据分析实习生", company: str = "星链数科（杭州）有限公司") -> str:
    response = client.post(
        "/api/v1/builds",
        json={
            "name": f"{position}-{lang}",
            "template_id": default_template_id(client),
            "position": position,
            "company": company,
            "lang": lang,
        },
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    return response.get_json()["data"]["id"]


def ready_package_ids(client) -> list[str]:
    response = client.get("/api/v1/packages?status=ready&limit=50")
    assert response.status_code == 200, response.get_data(as_text=True)
    return [item["id"] for item in response.get_json()["data"]["items"]]
