"""环境自检（/env、preflight.py、llm_probe.py 共用）。

只读探测：不下载、不联网（除显式调用的 LLM probe）、不写文件。
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from .. import config as config_mod

REQUIRED_PACKAGES: tuple[str, ...] = (
    "flask",
    "pydantic",
    "jinja2",
    "reportlab",
    "pdfplumber",
    "pypdf",
    "docx",
    "markdown",
    "httpx",
    "bs4",
)

#: 中文 PDF 冻结路径（docs/ARCHITECTURE §7.5）
SONGTI_PATH = Path("/System/Library/Fonts/Supplemental/Songti.ttc")
REGULAR_SUBFONT_INDEX = 6
BOLD_SUBFONT_INDEX = 1

CHROME_CANDIDATES: tuple[str, ...] = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
)


def _module_ok(name: str) -> tuple[bool, str | None, str | None]:
    """返回 (可导入, 版本, 错误信息)。"""

    import_name = {"docx": "docx", "bs4": "bs4"}.get(name, name)
    try:
        module = importlib.import_module(import_name)
    except Exception as exc:  # pragma: no cover - 环境差异
        return False, None, f"{type(exc).__name__}: {exc}"
    version = getattr(module, "__version__", None)
    if not version:
        dist_name = {"docx": "python-docx", "bs4": "beautifulsoup4"}.get(name, name)
        try:
            version = importlib.metadata.version(dist_name)
        except importlib.metadata.PackageNotFoundError:
            version = None
    return True, version, None


def packages_report() -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    missing: list[str] = []
    errors: dict[str, str] = {}
    for name in REQUIRED_PACKAGES:
        ok, version, error = _module_ok(name)
        packages[name] = version if ok else None
        if not ok:
            missing.append(name)
            if error:
                errors[name] = error
    return {"packages": packages, "missing_packages": missing, "import_errors": errors}


def sqlite_report() -> dict[str, Any]:
    info: dict[str, Any] = {"version": sqlite3.sqlite_version, "fts5": False, "json1": False}
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE _t USING fts5(x)")
            conn.execute("DROP TABLE _t")
            info["fts5"] = True
        except sqlite3.OperationalError:
            info["fts5"] = False
        try:
            conn.execute("SELECT json_extract('{\"a\":1}', '$.a')").fetchone()
            info["json1"] = True
        except sqlite3.OperationalError:
            info["json1"] = False
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover
        info["error"] = f"{type(exc).__name__}: {exc}"
    return info


def _coerce_text(value: Any) -> str:
    """reportlab 的 ``face.name`` 是 ``TTFNameBytes``（bytes 子类）。

    必须 ``decode``；``str()`` 会得到 "b'STSongti-SC-Regular'" 这种脏值混进 JSON。
    """
    if isinstance(value, (bytes, bytearray)):
        try:
            return bytes(value).decode("utf-8")
        except UnicodeDecodeError:  # pragma: no cover - 字体名正常都是 ASCII
            return repr(bytes(value))
    return str(value)


def _json_safe(value: Any) -> Any:
    """出口防线：递归转成 json 能序列化的类型（bytes→str、Path→str、tuple/set→list）。"""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (bytes, bytearray)):
        return _coerce_text(value)
    if isinstance(value, os.PathLike):
        return os.fspath(value)
    if isinstance(value, dict):
        return {_coerce_text(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return _coerce_text(value)


@lru_cache(maxsize=1)
def _font_names() -> dict[str, Any]:
    """用 reportlab 实际注册一次 Songti.ttc 的两个 subfont，确认字体名与可渲染性。"""

    result: dict[str, Any] = {"ok": False, "primary": None, "bold": None, "error": None}
    if not SONGTI_PATH.exists():
        result["error"] = f"字体文件不存在：{SONGTI_PATH}"
        return result
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except Exception as exc:  # pragma: no cover
        result["error"] = f"reportlab 不可用：{exc}"
        return result
    names: dict[str, str] = {}
    for label, index in (("regular", REGULAR_SUBFONT_INDEX), ("bold", BOLD_SUBFONT_INDEX)):
        font_name = f"EnvCheckSongti-{label}"
        try:
            font = TTFont(font_name, str(SONGTI_PATH), subfontIndex=index)
            pdfmetrics.registerFont(font)
            names[label] = _coerce_text(font.face.name)
        except Exception as exc:  # pragma: no cover
            result["error"] = f"加载 {label}(index={index}) 失败：{type(exc).__name__}: {exc}"
            return result
    result.update(
        {
            "ok": True,
            "primary": {"path": str(SONGTI_PATH), "subfont_index": REGULAR_SUBFONT_INDEX, "name": names["regular"]},
            "bold": {"path": str(SONGTI_PATH), "subfont_index": BOLD_SUBFONT_INDEX, "name": names["bold"]},
        }
    )
    return result


def fonts_report() -> dict[str, Any]:
    detail = _font_names()
    return {
        "primary": detail.get("primary"),
        "bold": detail.get("bold"),
        "ok": bool(detail.get("ok")),
        "chain": [
            {"engine": "reportlab", "font": "Songti.ttc", "subfont_index": REGULAR_SUBFONT_INDEX, "available": bool(detail.get("ok"))},
            {"engine": "chrome-headless", "font": "STHeiti/Arial Unicode", "available": bool(chrome_path())},
        ],
        "error": detail.get("error"),
    }


@lru_cache(maxsize=1)
def chrome_path() -> str | None:
    for candidate in CHROME_CANDIDATES:
        resolved = shutil.which(candidate) if os.sep not in candidate else (candidate if Path(candidate).exists() else None)
        if resolved:
            return resolved
    return None


def soffice_available() -> bool:
    return bool(shutil.which("soffice") or Path("/Applications/LibreOffice.app/Contents/MacOS/soffice").exists())


def weasyprint_available() -> bool:
    """探测 weasyprint 是否可用。

    注意：weasyprint 在缺系统库时会**往 stdout 打一段横幅**，而 preflight --json
    要求 stdout 只有 JSON —— 所以这里把探测期间的 stdout/stderr 一起吞掉。
    """
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        ok, _, _ = _module_ok("weasyprint")
    return ok


def render_report() -> dict[str, Any]:
    fonts = fonts_report()
    chrome = chrome_path()
    return {
        "pdf_primary": "reportlab" if fonts["ok"] else "chrome",
        "pdf_fallback": "chrome" if chrome else "docx",
        "chrome_available": bool(chrome),
        "chrome_path": chrome,
        "soffice_available": soffice_available(),
        "weasyprint_available": weasyprint_available(),
        "fonts_ok": fonts["ok"],
    }


def runtime_report() -> dict[str, Any]:
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    system_site = False
    pyvenv = Path(sys.prefix) / "pyvenv.cfg"
    if pyvenv.exists():
        try:
            system_site = "true" in pyvenv.read_text(encoding="utf-8").lower()
        except OSError:
            system_site = False
    return {
        "version": sys.version.split()[0],
        "executable": sys.executable,
        "venv": sys.prefix if in_venv else None,
        "in_venv": in_venv,
        "system_site_packages": system_site,
        "platform": sys.platform,
    }


def paths_report() -> dict[str, Any]:
    from .. import db as db_mod

    paths = db_mod.get_paths()
    try:
        paths.ensure()
        probe = paths.tmp / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        writable = True
        error = None
    except Exception as exc:  # pragma: no cover
        writable = False
        error = f"{type(exc).__name__}: {exc}"
    return {
        "project_root": str(config_mod.PROJECT_ROOT),
        "data_root": str(paths.root),
        "db": str(paths.db),
        "files": str(paths.files),
        "exports": str(paths.exports),
        "imports": str(paths.imports),
        "logs": str(paths.logs),
        "db_exists": paths.db.exists(),
        "writable": writable,
        "error": error,
    }


def llm_report(cfg: config_mod.Config | None = None) -> dict[str, Any]:
    cfg = cfg or config_mod.get_config()
    last_check = None
    try:
        from ..repos import SettingsRepo

        last_check = SettingsRepo().get("llm_last_check_at")
    except Exception:  # pragma: no cover - 数据库尚未就绪
        last_check = None
    return {
        "provider": cfg.provider,
        "provider_label": cfg.preset.label,
        "base_url": cfg.base_url,
        "model": cfg.model,
        "model_analysis": cfg.model_analysis,
        "key_set": cfg.key_set,
        "key_field": "LLM_API_KEY",
        "ready": cfg.ready,
        "not_ready_reason": cfg.not_ready_reason,
        "reachable": None,
        "last_check_at": last_check,
        "timeouts": {
            "connect_s": cfg.connect_timeout,
            "read_s": cfg.read_timeout,
            "total_s": float(cfg.timeout_seconds),
        },
        "allowed_hosts": cfg.allowed_hosts,
    }


def _build_info() -> dict[str, Any]:
    """与 /api/v1/health 的 build 同源（AC-ENV-10：进程是否当前代码的唯一判据）。"""
    from .. import buildinfo

    try:
        return buildinfo.build_info()
    except Exception as exc:  # 绝不因为取不到 git 让 /env 失败
        return {"id": "unknown", "error": type(exc).__name__}


def env_snapshot(cfg: config_mod.Config | None = None) -> dict[str, Any]:
    cfg = cfg or config_mod.get_config()
    runtime = runtime_report()
    packages = packages_report()
    fonts = fonts_report()
    render = render_report()
    paths = paths_report()
    sqlite = sqlite_report()
    warnings: list[str] = []
    if packages["missing_packages"]:
        warnings.append("缺少依赖：" + ", ".join(packages["missing_packages"]) + "（请运行 scripts/bootstrap.sh）")
    if not fonts["ok"]:
        warnings.append("中文 PDF 一级路径不可用（reportlab + Songti.ttc），将回退 Chrome/DOCX")
    if not cfg.ready:
        warnings.append(f"LLM 未就绪：{cfg.not_ready_reason}")
    if not paths["writable"]:
        warnings.append(f"数据目录不可写：{paths.get('error')}")
    if not sqlite.get("fts5"):
        warnings.append("SQLite 未启用 FTS5，搜索能力受限")
    return _json_safe({
        "python": runtime,
        "venv": runtime["venv"],
        "system_site_packages": runtime["system_site_packages"],
        "packages": packages["packages"],
        "missing_packages": packages["missing_packages"],
        "import_errors": packages["import_errors"],
        "sqlite": sqlite,
        "fonts": fonts,
        "render": render,
        "llm": llm_report(cfg),
        "paths": paths,
        "build": _build_info(),
        "warnings": warnings,
    })


def to_json(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2)


def python_ok() -> bool:  # pragma: no cover - 供脚本调用
    return sys.version_info >= (3, 10)


def git_status_clean() -> bool | None:  # pragma: no cover - 供 preflight 使用
    try:
        out = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5, cwd=config_mod.PROJECT_ROOT)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() == ""
