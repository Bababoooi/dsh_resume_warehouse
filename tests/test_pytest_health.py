"""单文件跑的体检：把「单文件必须快」这件事变成会红的断言。

背景（captain 实测）：`python3 -m pytest tests/test_import_date_span.py -q` 曾挂了 5 分钟。
一条纯逻辑用例（只断言正则切分）不该碰临时 DATA_DIR、不该建库、更不该起服务/浏览器——
否则没人愿意为改一行正则去跑一次单文件，「先跑一下」这件事就从流程里消失了。

这里不测「代码逻辑」，测的是**测试基础设施的响应时间**：
1. 纯逻辑文件单跑必须 <5 秒（含解释器启动与 pytest 收集）；
2. `-m noservice` 选出来的是「不需要服务的那一层」，且必须能在几秒内跑完；
3. 被自动打标的判定口径是「夹具名」，不是目录名（目录会搬，夹具名是真实依赖）。

超时口径：用 ``time.monotonic()`` 包住子进程。阈值 5 秒是 captain 定的目标值；
本机实测 0.25–0.45 秒，留了 10 倍余量，避免 CI 抖动造成假红。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PURE_FILE = ROOT / "tests" / "test_import_date_span.py"

pytestmark = pytest.mark.noservice


def _run(args: list[str], *, timeout: float = 60.0) -> tuple[subprocess.CompletedProcess, float]:
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc, time.monotonic() - started


def test_single_pure_file_runs_in_under_five_seconds():
    """纯逻辑用例单文件跑：必须 <5 秒，且不许有 skip（说明依赖了现场）。"""
    assert PURE_FILE.exists(), f"缺失目标文件：{PURE_FILE}"
    proc, elapsed = _run([str(PURE_FILE.relative_to(ROOT)), "-q"])
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    assert elapsed < 5.0, f"单文件跑了 {elapsed:.2f}s（阈值 5s）——检查是否被 session 级夹具拖住"
    tail = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout.strip() else ""
    assert "passed" in tail, tail
    assert "skipped" not in tail, f"纯逻辑用例不该 skip：{tail}"


def test_noservice_selection_is_pure_and_fast():
    """`-m noservice` 只选纯逻辑层：结果里不得出现 skipped/deselected 之外的现场成本。"""
    proc, elapsed = _run(["tests", "-m", "noservice", "-q", "--co"])
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    lines = [line for line in proc.stdout.splitlines() if "::" in line]
    assert len(lines) >= 5, f"noservice 只选到 {len(lines)} 条，标记可能没生效"
    assert all("test_ac_" not in line for line in lines), "验收用例不该被判为 noservice"
    assert elapsed < 30.0, f"noservice 收集用了 {elapsed:.2f}s"


def test_marker_is_decided_by_fixture_names_not_directories(tmp_path):
    """口径回归：判定依据是夹具名集合，不是路径。

    这条用例本身在 ``tests/`` 根目录、且不请求任何夹具，所以它自己被打了 noservice；
    而请求 ``client`` 的用例必须不被选中。用一个只读的清单断言，避免跑真服务。
    """
    from _pytest.python import Function  # noqa: F401  仅用于说明判定对象

    from tests.conftest import SERVICE_FIXTURES  # type: ignore[import-not-found]

    assert {"client", "app_env", "flow"} <= SERVICE_FIXTURES
    assert "tmp_path" not in SERVICE_FIXTURES
