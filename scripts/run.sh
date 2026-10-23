#!/usr/bin/env bash
# 启动 resume-warehouse 本地服务（唯一入口）。
#
# - .venv 不存在会自动跑 scripts/bootstrap.sh（幂等）
# - 先跑 scripts/preflight.py 体检，失败则明确报错退出（不静默启动）
# - 真实端口由 server/server.py 决定（8765 被占用则顺延），并写入 data/runtime/app_port
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -d "$ROOT/.venv" ]; then
  echo "[run] 未发现 .venv，先执行 bootstrap"
  "$ROOT/scripts/bootstrap.sh"
fi

# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"

if [ "${SKIP_PREFLIGHT:-0}" != "1" ]; then
  python "$ROOT/scripts/preflight.py" || {
    echo "[run][错误] 启动前体检未通过，已中止。修复上面的问题后重试（或 SKIP_PREFLIGHT=1 跳过）。" >&2
    exit 1
  }
fi

exec python "$ROOT/server/server.py" "$@"
