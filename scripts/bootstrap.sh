#!/usr/bin/env bash
# 幂等建立 resume-warehouse 的 Python 环境。
#
# 设计要点（实测而来）：
# * 系统 Python 已装 flask/pydantic/reportlab 等，裸 venv 没有 → 必须 --system-site-packages；
# * 重复执行必须安全：venv 已存在就复用，不重复创建、不升级已有包；
# * 失败**明确报错并退出非零**，绝不静默降级。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv"
PY="${PYTHON:-python3}"
REQUIRED=(flask pydantic httpx jinja2 reportlab pdfplumber pypdf docx markdown bs4)

log() { printf '[bootstrap] %s\n' "$*"; }
die() { printf '[bootstrap][错误] %s\n' "$*" >&2; exit 1; }

command -v "$PY" >/dev/null 2>&1 || die "找不到 python3（可用 PYTHON=/path/to/python3 指定）"

if [ ! -d "$VENV" ]; then
  log "创建虚拟环境 ${VENV}（--system-site-packages）"
  "$PY" -m venv --system-site-packages "$VENV" || die "创建 venv 失败（检查 python3 -m venv 是否可用）"
else
  log "复用已有虚拟环境 $VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"
log "Python $(python --version 2>&1) @ ${VENV}"

missing=()
for mod in "${REQUIRED[@]}"; do
  if ! python - "$mod" <<'PY'
import importlib, sys
try:
    importlib.import_module(sys.argv[1])
except Exception:
    raise SystemExit(1)
PY
  then
    missing+=("$mod")
  fi
done

if [ ${#missing[@]} -gt 0 ]; then
  log "缺少依赖：${missing[*]}（尝试安装）"
  pkgs=()
  for mod in "${missing[@]}"; do
    case "$mod" in
      bs4) pkgs+=("beautifulsoup4") ;;
      docx) pkgs+=("python-docx") ;;
      *) pkgs+=("$mod") ;;
    esac
  done
  python -m pip install --disable-pip-version-check "${pkgs[@]}" || die "pip 安装失败：${pkgs[*]}。请联网后重试，或手动安装后再次运行本脚本。"
  for mod in "${missing[@]}"; do
    python - "$mod" <<'PY' || die "安装后仍无法 import ${mod}"
import importlib, sys
importlib.import_module(sys.argv[1])
PY
  done
fi

log "依赖自检通过：${REQUIRED[*]}"

# 数据目录与权限（幂等）
mkdir -p "$ROOT/data/files" "$ROOT/data/exports" "$ROOT/data/imports" "$ROOT/data/logs" "$ROOT/data/tmp" "$ROOT/data/runtime"
[ -f "$ROOT/.env" ] || log "未发现 .env（可复制 .env.example 后填入 LLM_API_KEY；无 key 时服务仍可启动，LLM 通道会报 LLM_NOT_CONFIGURED）"

log "完成。启动：$ROOT/scripts/run.sh"
