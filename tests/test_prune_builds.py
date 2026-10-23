"""``scripts/prune_builds.py`` 的行为测试（t15 返工：归档 ≠ 删除）。

用户看到的问题是「组装页列了 43 条同名构建」，但历史导出的记录不该被一条命令抹掉。
这组测试钉住三条：

1. **默认只归档**：写 ``archived_at``，行、选题、产物记录都还在；
2. ``GET /builds`` 默认看不到归档记录，``?include_archived=1`` 能看回来；
3. ``--hard-delete`` 必须显式 ``--yes``，否则直接拒绝；``--list-orphan-files`` 只列不删。
"""

from __future__ import annotations

import json
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "prune_builds.py"


def _template_id(db_path):
    """构建必须挂在模板上；测试直接插一条最小模板（模板写侧走 import commit）。"""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO template (id, name, lang, source_kind, page_limit, is_default, created_at, updated_at)"
            " VALUES ('tplprune', '归档测试模板', 'zh', 'builtin', 1, 0, datetime('now'), datetime('now'))"
        )
    return "tplprune"


def _packages(client, count=1):
    ids = []
    for index in range(count):
        response = client.post(
            "/api/v1/packages",
            json={
                "title": f"构建夹具项目{index}",
                "kind": "project",
                "org": "示例科技",
                "role": "数据分析实习生",
                "start_date": "2025-01",
                "end_date": "2025-06",
            },
        )
        assert response.status_code == 201, response.get_json()
        package_id = response.get_json()["data"]["id"]
        variant = client.post(
            f"/api/v1/packages/{package_id}/variants",
            json={"bullet_key": "b1", "tone": "impact", "lang": "zh", "text": "把订单预测接入流程，周转提升 39.3%。", "verified": True},
        )
        assert variant.status_code == 201, variant.get_json()
        ready = client.patch(f"/api/v1/packages/{package_id}", json={"status": "ready"})
        assert ready.status_code == 200, ready.get_json()
        ids.append(package_id)
    return ids


def _profile(client):
    """导出要用 {name}/{school}/{position} 三个变量，先把档案与岗位备好。"""
    saved = client.put(
        "/api/v1/profile",
        json={"name_zh": "张三", "school_zh": "示例大学", "degree": "本科", "major": "管理科学"},
    )
    assert saved.status_code == 200, saved.get_json()


def _build(client, package_ids, *, name="归档测试", template_id="tplprune", position="数据分析实习生"):
    _profile(client)
    response = client.post(
        "/api/v1/builds",
        json={"name": name, "lang": "zh", "template_id": template_id, "position": position},
    )
    assert response.status_code == 201, response.get_json()
    build_id = response.get_json()["data"]["id"]
    picked = client.put(
        f"/api/v1/builds/{build_id}/selections",
        json={"selections": [{"package_id": pid, "variant_ids": [], "order_index": i} for i, pid in enumerate(package_ids)]},
    )
    assert picked.status_code in (200, 204), picked.get_json()
    return build_id


def test_prune_defaults_to_archiving_and_list_hides_it(app_env):
    app, client, data_dir = app_env
    db_path = Path(data_dir) / "app.db"
    _template_id(db_path)
    package_ids = _packages(client, 2)
    # 同名同内容的两次构建 = 同一签名，后一次是重复
    first = _build(client, package_ids[:1])
    second = _build(client, package_ids[:1])
    _build(client, package_ids)  # 第三个签名不同，不该被动

    dry = subprocess.run(
        [sys.executable, str(SCRIPT), "--data-dir", data_dir],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "保留：" in dry.stdout
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM resume_build WHERE archived_at IS NOT NULL").fetchone()[0] == 0

    applied = subprocess.run(
        [sys.executable, str(SCRIPT), "--data-dir", data_dir, "--apply"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "已归档" in applied.stdout
    with sqlite3.connect(db_path) as conn:
        archived = conn.execute(
            "SELECT id FROM resume_build WHERE archived_at IS NOT NULL"
        ).fetchall()
        # 归档的是较旧的那一条，行还在（不是删除）
        assert [row[0] for row in archived] == [first]
        assert conn.execute("SELECT COUNT(*) FROM resume_build").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM build_selection").fetchone()[0] >= 3

    listed = client.get("/api/v1/builds").get_json()["data"]
    ids = [item["id"] for item in listed["items"]]
    assert first not in ids and second in ids
    shown = client.get("/api/v1/builds?include_archived=1").get_json()["data"]["items"]
    assert first in [item["id"] for item in shown]


def test_hard_delete_requires_explicit_confirmation(app_env):
    _app, client, data_dir = app_env
    _template_id(Path(data_dir) / "app.db")
    _build(client, _packages(client))
    refused = subprocess.run(
        [sys.executable, str(SCRIPT), "--data-dir", data_dir, "--hard-delete"],
        capture_output=True,
        text=True,
    )
    assert refused.returncode == 2
    assert "不可恢复" in refused.stderr


def test_list_orphan_files_reports_without_deleting(app_env):
    _app, _client, data_dir = app_env
    exports = Path(data_dir) / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    orphan = exports / "没人引用的-1.pdf"
    orphan.write_bytes(b"%PDF-1.4 orphan")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--data-dir", data_dir, "--list-orphan-files", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    names = [item["file"] for item in payload["orphan_files"]]
    assert "没人引用的-1.pdf" in names
    assert orphan.exists()  # 只列不删
    entry = next(item for item in payload["orphan_files"] if item["file"] == "没人引用的-1.pdf")
    assert entry["bytes"] == len(b"%PDF-1.4 orphan") and entry["mtime"]


def test_hard_delete_with_confirm_removes_rows_and_reports_orphans(app_env):
    """显式确认后的物理删除：行没了，产物文件还在（只报孤儿数，不删文件）。"""
    _app, client, data_dir = app_env
    db_path = Path(data_dir) / "app.db"
    _template_id(db_path)
    build_id = _build(client, _packages(client))

    response = client.post(
        f"/api/v1/builds/{build_id}/export",
        json={"engine": "reportlab"},
    )
    assert response.status_code in (200, 202), response.get_json()
    deadline = time.time() + 60
    while time.time() < deadline:
        with sqlite3.connect(db_path) as conn:
            artifact = conn.execute(
                "SELECT rel_path FROM build_artifact WHERE build_id=?", (build_id,)
            ).fetchone()
        if artifact:
            break
        time.sleep(0.4)
    assert artifact, "导出没有产出产物行"
    rel_path = artifact[0]

    with sqlite3.connect(db_path) as conn:
        before_artifacts = conn.execute("SELECT COUNT(*) FROM build_artifact").fetchone()[0]
        before_selections = conn.execute("SELECT COUNT(*) FROM build_selection").fetchone()[0]
    assert before_artifacts == 1 and before_selections == 1

    removed = client.delete(f"/api/v1/builds/{build_id}?hard=1&confirm={build_id}")
    assert removed.status_code == 204, removed.get_json()
    assert removed.headers.get("X-Orphaned-Artifacts") == "1"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM resume_build WHERE id=?", (build_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM build_artifact").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM build_selection").fetchone()[0] == 0
    # 磁盘文件不动：删数据库行不等于删用户的导出
    assert (Path(data_dir) / rel_path).exists()
