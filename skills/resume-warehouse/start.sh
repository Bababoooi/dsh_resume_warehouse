#!/usr/bin/env bash
# resume-warehouse 一键启动（幂等）：
#   1) .venv / 依赖缺失 → 自动跑 scripts/bootstrap.sh
#   2) 已在运行 → 直接复用，不重复起进程
#   3) 起后端 → 等 data/runtime/app_port → 打印真实本地 URL（端口被占用会自动顺延）
#
# 用法：
#   bash skills/resume-warehouse/start.sh
#   SKIP_PREFLIGHT=1 bash skills/resume-warehouse/start.sh
#   RESUME_WAREHOUSE_HOME=/path/to/repo bash skills/resume-warehouse/start.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${RESUME_WAREHOUSE_HOME:-$(cd "$HERE/../.." && pwd)}"
PORT_FILE="$ROOT/data/runtime/app_port"
LOG_FILE="$ROOT/data/logs/app.log"
PY_BIN="${PY_BIN:-$(command -v python3 || command -v python)}"
export PY_BIN

if [ ! -f "$ROOT/server/server.py" ]; then
  echo "[start][错误] 找不到 $ROOT/server/server.py。请设置 RESUME_WAREHOUSE_HOME 指向仓库根目录。" >&2
  exit 1
fi

json_field() { # $1=key（端口文件是 JSON：port/host/url/pid/started_at）
  "$PY_BIN" -c 'import json,sys
try:
    print(json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2]) or "")
except Exception:
    raise SystemExit(1)' "$PORT_FILE" "$1" 2>/dev/null || true
}

alive() { # $1=port
  "$PY_BIN" -c 'import socket,sys
s = socket.socket()
s.settimeout(1.0)
try:
    s.connect(("127.0.0.1", int(sys.argv[1])))
except Exception:
    raise SystemExit(1)
finally:
    s.close()' "$1" 2>/dev/null
}

# ---- 已在运行？------------------------------------------------------------
if [ -f "$PORT_FILE" ]; then
  RUN_PORT="$(json_field port)"
  RUN_PID="$(json_field pid)"
  if [ -n "$RUN_PORT" ] && alive "$RUN_PORT" && [ -n "$RUN_PID" ] && kill -0 "$RUN_PID" 2>/dev/null; then
    echo "[start] 已在运行，复用现有实例"
    echo "URL=http://127.0.0.1:$RUN_PORT"
    echo "PID=$RUN_PID"
    echo "PORT_FILE=$PORT_FILE"
    exit 0
  fi
  echo "[start] 端口文件陈旧（端口 ${RUN_PORT:-?} 不通或进程已退出），重新启动"
fi

# ---- 依赖引导 -------------------------------------------------------------
if [ ! -d "$ROOT/.venv" ]; then
  echo "[start] 未发现 .venv，执行 bootstrap（首次约 1-2 分钟）"
  bash "$ROOT/scripts/bootstrap.sh"
fi

# ---- 启动（后台）----------------------------------------------------------
mkdir -p "$ROOT/data/logs"
echo "[start] 启动后端 …（日志：${LOG_FILE}）"
# </dev/null：否则后台子进程继承调用方的 stdin/stdout，脚本已退出但父命令仍挂着
( cd "$ROOT" && nohup bash scripts/run.sh >>"$LOG_FILE" 2>&1 </dev/null & )

# ---- 等待就绪 -------------------------------------------------------------
DEADLINE=$((SECONDS + 90))
while [ $SECONDS -lt $DEADLINE ]; do
  PORT="$(json_field port)"
  if [ -n "$PORT" ] && alive "$PORT"; then
    echo "[start] 就绪"
    echo "URL=http://127.0.0.1:$PORT"
    echo "PORT_FILE=$PORT_FILE"
    echo "HEALTH=http://127.0.0.1:$PORT/api/v1/health"
    exit 0
  fi
  sleep 1
done

echo "[start][错误] 90 秒内未就绪。最近日志：" >&2
tail -n 30 "$LOG_FILE" >&2 || true
exit 1
