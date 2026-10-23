"""C4 的取证脚本自检：`expected_but_unchanged` 不能是个永远为空的摆设。

`scripts/recompute_jd_links.py` 的 `--report` 里有三个容易「看起来没问题」的坑：

1. `expected_but_unchanged` 永远 `[]` —— 那它挡不住「空转当收敛」；
2. `checked_against` 缺失 —— 空列表会被读成「没查」；
3. `changed` 标了 true 但 `before == after` —— 假报变化。

这里用**假数据**直接喂 `collect_expected_but_unchanged()`：真实库里每条都对齐时列表本就该为空，
所以「空」这件事必须靠单测证明是「查过且确实没有」，而不是「逻辑没写」。

用例全部不连库、不起服务（`noservice`），毫秒级。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.noservice

ROOT = Path(__file__).resolve().parents[1]


def _script():
    path = ROOT / "scripts" / "recompute_jd_links.py"
    spec = importlib.util.spec_from_file_location("recompute_jd_links_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROFILE = {"skills": [{"line": "数据分析类：掌握Python、R、SQL等编程语言"}]}
PACKAGES = [{"id": "pkg_1", "title": "门店选址与订单预测", "tech_stack": ["R"]}]


def _row(skill: str, *, status: str, matched: list, evidence: list) -> dict:
    return {
        "id": f"req_{skill[:4]}",
        "skill": skill,
        "changed": False,
        "before": {"skill": skill, "status": "missing", "source": "llm", "matched": [], "evidence": [], "hint": ""},
        "after": {"skill": skill, "status": status, "source": "llm", "matched": matched, "evidence": evidence, "hint": ""},
    }


def test_reports_requirement_with_evidence_but_still_empty():
    """技能文本命中了 skills_json，重算后却还是 missing/空 → 必须被点名。"""
    module = _script()
    rows = [_row("熟练掌握 SQL、Python", status="missing", matched=[], evidence=[])]
    requirements = [{"id": "req_sql", "skill": "熟练掌握 SQL、Python"}]

    found = module.collect_expected_but_unchanged("jd_1", rows, requirements, PACKAGES, PROFILE)

    assert len(found) == 1, found
    assert found[0]["evidence_sources"] == ["skills_json"], found
    assert found[0]["why_expected"] == "命中本地证据源但重算后仍为空"
    assert found[0]["jd_id"] == "jd_1" and found[0]["requirement_id"] == "req_sql"


def test_linked_requirement_is_not_reported():
    """真的命中了就不是「空转」——不该出现在列表里。"""
    module = _script()
    rows = [_row("熟练掌握 SQL、Python", status="partial", matched=["pkg_1"], evidence=["skills_json:掌握Python"])]
    requirements = [{"id": "req_sql", "skill": "熟练掌握 SQL、Python"}]

    assert module.collect_expected_but_unchanged("jd_1", rows, requirements, PACKAGES, PROFILE) == []


def test_requirement_without_any_evidence_stays_out():
    """用户确实没有的技能（Rust）不该被当成「应命中未命中」。"""
    module = _script()
    rows = [_row("熟悉 Rust 后端开发", status="missing", matched=[], evidence=[])]
    requirements = [{"id": "req_rust", "skill": "熟悉 Rust 后端开发"}]

    assert module.collect_expected_but_unchanged("jd_1", rows, requirements, PACKAGES, PROFILE) == []


def test_brief_has_the_six_contract_keys():
    """before/after 复用 `_brief()` 的六键，别另发明字段。"""
    module = _script()
    brief = module._brief({"skill": "s", "candidate_status": "missing", "candidate_status_source": "llm"})
    assert set(brief) == {"skill", "status", "source", "matched", "evidence", "hint"}, brief


def test_report_carries_command_and_checked_against(tmp_path, monkeypatch):
    """报告必须自带 `command`（本次 argv 原样）与 `checked_against`。

    手写这两个字段就是自欺：一旦实际命令与之不符，任何人都无法复盘这次重算动过什么
    （T-19 同族）。这里真跑一次 dry-run，只验证键存在且 command 里含本次脚本名。
    """
    import json
    import os
    import shutil
    import subprocess
    import sys

    module = _script()
    data_dir = ROOT / "data" / "_tests" / "relink-report"
    if data_dir.exists():
        shutil.rmtree(data_dir)
    (data_dir / "runtime").mkdir(parents=True, exist_ok=True)

    db_src = ROOT / "data" / "app.db"
    if not db_src.exists():  # 干净检出时没有真库，跳过（不伪造数据）
        pytest.skip("没有 data/app.db，跳过真库重算的报告字段检查")
    shutil.copy2(db_src, data_dir / "app.db")

    report = data_dir / "report.json"
    env = dict(os.environ, DATA_DIR=str(data_dir))
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "recompute_jd_links.py"), "--report", str(report)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(report.read_text())
    assert payload["mode"] == "dry-run"
    assert payload["command"].endswith(f"--report {report}")
    assert "recompute_jd_links.py" in payload["command"]
    assert payload["checked_against"]
    assert isinstance(payload["expected_but_unchanged"], list)
    assert payload["outbound_calls"] == 0
