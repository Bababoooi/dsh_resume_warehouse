"""t12 修的三处用户可见缺陷的回归测试（后端侧）。

三条都不是"顺手改改"，各自对应一个真实故障：

1. ``GET /packages`` 把 ``include_variants`` 写死 False → 前端「经历库」5 张卡片全显示
   「这条还没有要点」、顶部「表述变体 0」，而库里其实有 22 条活跃变体。
2. ``POST /templates/{id}/blocks/reorder``：契约 P1 端点，之前根本不存在（用户在模板页
   拖动没有后端可调）。
3. ``POST /templates/{id}/validate``：只读体检，恒 200，让用户在导出前看到「缺 header /
   块没槽位 / 必填槽位没值」，而不是等 PDF 出来才发现某段是空的。
"""

from __future__ import annotations

PACKAGE_TEXT = """张三
13800138000 | zhangsan@example.com
教育背景
2024.9-2028.6 示例大学 计算机科学与技术 本科
实习经历
示例科技 后端实习生 2026.07 - 2026.10
负责接口开发，QPS 提升 30%。
项目经历
数据看板 队长 2026.03 - 2026.04
搭建指标看板，覆盖 12 个业务域。
"""


def _seed(app_env):
    """导入 → commit（同时派生 package），返回 (client, template_id, import_id)。"""
    _app, client, _dir = app_env
    resp = client.post("/api/v1/imports", json={"text": PACKAGE_TEXT, "filename": "seed.txt"})
    assert resp.status_code == 201, resp.get_json()
    import_id = resp.get_json()["data"]["import_id"]
    commit = client.post(
        f"/api/v1/imports/{import_id}/commit",
        json={
            "template_name": "t12 回归模板",
            "lang": "zh",
            "set_default": True,
            "also_create_packages": True,
        },
    )
    assert commit.status_code == 201, commit.get_json()
    data = commit.get_json()["data"]
    return client, data["template_id"], import_id


def test_packages_list_hides_variants_by_default(app_env):
    """轻量列表不能带变体正文（列表页/统计不需要，带上会让响应膨胀十几倍）。"""
    client, _template_id, _import_id = _seed(app_env)
    light = client.get("/api/v1/packages?limit=5")
    assert light.status_code == 200
    items = light.get_json()["data"]["items"]
    assert items, "导入之后应该至少有一个派生 package"
    assert all("variants" not in item for item in items)


def test_packages_list_returns_variants_when_asked(app_env):
    """``?include_variants=1`` 必须真的带上 variants 且非空——这正是前端经历库的诉求。"""
    client, _template_id, _import_id = _seed(app_env)
    full = client.get("/api/v1/packages?limit=5&include_variants=1")
    assert full.status_code == 200
    items = full.get_json()["data"]["items"]
    assert items
    with_variants = [item for item in items if item.get("variants")]
    assert with_variants, "库里明明有变体，列表却一条都不给"
    # 变体要带上正文，否则前端仍然无法显示要点
    first = with_variants[0]["variants"][0]
    assert first.get("text"), first
    assert first.get("tone"), first


def test_include_variants_accepts_true_yes_on(app_env):
    """查询参数字面量容错：1/true/yes/on 都算真（与 import 端点同口径）。"""
    client, _template_id, _import_id = _seed(app_env)
    for literal in ("1", "true", "yes", "on", "TRUE"):
        resp = client.get(f"/api/v1/packages?limit=5&include_variants={literal}")
        assert resp.status_code == 200
        items = resp.get_json()["data"]["items"]
        assert any(item.get("variants") for item in items), literal


def test_template_blocks_reorder_keeps_children_in_their_section(app_env):
    """重排只改 ``order_index``：父块按给定顺序编号，子块留在各自父级内部。"""
    client, template_id, _import_id = _seed(app_env)
    blocks = client.get(f"/api/v1/templates/{template_id}").get_json()["data"]["blocks"]
    parents = [block for block in blocks if not block.get("parent_block_id")]
    children = [block for block in blocks if block.get("parent_block_id")]
    assert parents and children

    reversed_ids = [block["id"] for block in reversed(parents)] + [block["id"] for block in children]
    resp = client.post(f"/api/v1/templates/{template_id}/blocks/reorder", json={"block_ids": reversed_ids})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["data"]["order"] == reversed_ids

    after = client.get(f"/api/v1/templates/{template_id}").get_json()["data"]["blocks"]
    by_id = {block["id"]: block for block in after}
    # 父块按请求里的先后被重新编号（10、20、30…），也就是顺序真的反过来了
    parent_ids = [block["id"] for block in parents]
    reordered_orders = [by_id[pid]["order_index"] for pid in reversed(parent_ids)]
    assert reordered_orders == sorted(reordered_orders), reordered_orders
    # 内容与父子关系一个字都没动
    for block in blocks:
        assert by_id[block["id"]]["block_type"] == block["block_type"]
        assert by_id[block["id"]]["parent_block_id"] == block["parent_block_id"]
        assert by_id[block["id"]]["heading"] == block["heading"]


def test_template_reorder_rejects_partial_block_list(app_env):
    """少给/多给 block 一律 422：不猜"没给的块放哪"，否则会静默把某块挪到末尾。"""
    client, template_id, _import_id = _seed(app_env)
    blocks = client.get(f"/api/v1/templates/{template_id}").get_json()["data"]["blocks"]
    partial = [block["id"] for block in blocks[:2]]
    resp = client.post(f"/api/v1/templates/{template_id}/blocks/reorder", json={"block_ids": partial})
    assert resp.status_code == 422, resp.get_json()
    error = resp.get_json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["reason"] == "BLOCK_IDS_MISMATCH"
    assert error["details"]["missing"], "要告诉用户少了哪些块"
    assert error["details"]["expected_count"] == len(blocks)


def test_template_validate_is_read_only_and_reports_issues(app_env):
    """validate 恒 200、不改一行；把问题列成 issues[] 交给前端。"""
    client, template_id, _import_id = _seed(app_env)
    before = client.get(f"/api/v1/templates/{template_id}").get_json()["data"]["blocks"]

    resp = client.post(f"/api/v1/templates/{template_id}/validate")
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["valid"] is True
    assert data["issues"] == []
    assert data["checked"] == len(before)

    after = client.get(f"/api/v1/templates/{template_id}").get_json()["data"]["blocks"]
    assert [b["order_index"] for b in after] == [b["order_index"] for b in before]


def test_template_validate_flags_missing_header_and_empty_block(app_env):
    """真正有问题的模板要被点名（缺 header、块无槽位）——这才是用户在导出前想看到的。"""
    from app import db as db_mod
    from app.repos import TemplateRepo

    _app, client, _dir = app_env
    repo = TemplateRepo()
    template_id = repo.create({"name": "坏模板", "lang": "zh", "source_kind": "builtin", "page_limit": 1})
    # 只有一个 section 块、没有 header、也没有任何 slot
    repo.add_block(template_id, {"block_type": "section", "heading": "教育背景", "order_index": 10})
    db_mod.get_conn().commit()

    resp = client.post(f"/api/v1/templates/{template_id}/validate")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["valid"] is False
    codes = {issue["code"] for issue in data["issues"]}
    assert "NO_HEADER" in codes
    assert "BLOCK_WITHOUT_SLOTS" in codes
