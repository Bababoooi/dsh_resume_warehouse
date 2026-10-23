#!/usr/bin/env bash
# resume-warehouse 停止（只停本仓库 data/runtime/app_port 记录的进程）。
# 不用 pkill -f python：那会误杀用户机器上其它 Python 进程。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${RESUME_WAREHOUSE_HOME:-$(cd "$HERE/../.." && pwd)}"
PORT_FILE="$ROOT/data/runtime/app_port"
PY_BIN="${PY_BIN:-$(command -v python3 || command -v python)}"

if [ ! -f "$PORT_FILE" ]; then
  echo "[stop] 没有端口文件，服务可能未启动：$PORT_FILE"
  exit 0
fi

PID="$("$PY_BIN" -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8")).get("pid") or "")' "$PORT_FILE" 2>/dev/null || true)"
PORT="$("$PY_BIN" -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8")).get("port") or "")' "$PORT_FILE" 2>/dev/null || true)"

if [ -z "${PID:-}" ]; then
  echo "[stop] 端口文件里没有 pid，跳过"
  exit 0
fi

if ! kill -0 "$PID" 2>/dev/null; then
  echo "[stop] 进程 $PID 已不在运行（端口 ${PORT:-?}）"
  exit 0
fi

echo "[stop] 停止 pid=${PID}（端口 ${PORT:-?}）"
kill "$PID" 2>/dev/null || true
i=0
while [ $i -lt 20 ]; do
  kill -0 "$PID" 2>/dev/null || { echo "[stop] 已停止"; exit 0; }
  i=$((i + 1))
  sleep 0.25
done
echo "[stop] 未响应 SIGTERM，发送 SIGKILL"
kill -9 "$PID" 2>/dev/null || true
echo "[stop] 已强制停止"
