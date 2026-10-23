"""测试用的「有没有配 LLM key」判定。

为什么需要它：变体生成/分析类用例必须先建 consent preview，而 build_preview 会在
没有 key 时直接 503/报「尚未配置 API Key」。这类用例在**新克隆的仓库**（无 .env）里
必然报错——那不是实现坏了，是环境没配。跳过并写明原因，比让它红更诚实。
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def has_llm_key() -> bool:
    if os.environ.get("LLM_API_KEY", "").strip():
        return True
    env_file = ROOT / ".env"
    if not env_file.exists():
        return False
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("LLM_API_KEY="):
                return bool(line.split("=", 1)[1].strip())
    except OSError:
        return False
    return False


LLM_KEY_READY = has_llm_key()
LLM_KEY_REASON = "未配置 LLM_API_KEY（没有 .env 或 key 为空），跳过需要真调用前的 consent 用例"
