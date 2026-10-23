"""构建标识（D-27）。

用途：任何人（包括 captain 与 t10 验收）用一条命令就能判断
「这个正在跑的进程是不是当前代码」，而不是靠行为结论反推实现质量。

判据来源：captain m01420 —— pid 46958 是改代码前起的，Python 不热重载，
它跑的是旧代码，导致一轮行为验证全错。

取值优先级：

1. ``git rev-parse --short HEAD``（+ ``-dirty`` 后缀）—— 仓库里有 git 时最直观；
2. 源码指纹 ``src-<12 位 sha256>`` —— 对 ``server/app/**/*.py`` 的
   ``(相对路径, mtime_ns, size)`` 排序后取摘要，改一行代码就会变。
"""

from __future__ import annotations

import hashlib
import subprocess
from functools import lru_cache
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent.parent


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(  # noqa: S603 - 只跑 git，参数固定
            ["git", *args],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def source_digest(app_dir: Path | None = None) -> str:
    """``server/app`` 下所有 .py 的内容无关指纹（含 mtime/size，重写即变）。"""
    root = app_dir or APP_DIR
    entries: list[str] = []
    for path in sorted(root.rglob("*.py")):
        try:
            stat = path.stat()
        except OSError:  # pragma: no cover - 文件刚被删
            continue
        entries.append(f"{path.relative_to(root).as_posix()}:{stat.st_mtime_ns}:{stat.st_size}")
    digest = hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()[:12]
    return f"src-{digest}"


@lru_cache(maxsize=1)
def build_info() -> dict[str, object]:
    head = _git("rev-parse", "--short", "HEAD")
    dirty = _git("status", "--porcelain") if head else None
    source = source_digest()
    if head:
        identifier = f"{head}-dirty" if dirty else head
    else:
        identifier = source
    return {
        "id": identifier,
        "git_head": head,
        "git_dirty": bool(dirty) if head else None,
        "source": source,
    }


def build_id() -> str:
    return str(build_info()["id"])
