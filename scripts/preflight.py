#!/usr/bin/env python3
"""启动前体检：Python 依赖、SQLite、字体、数据目录、端口、.env。

默认打印人话；`--json` 打印结构化结果（AC-ENV-03：Agent/Skill 要能机器判定）。
退出码 0 = 全绿 / 1 = 有降级（可启动）/ 2 = 有硬伤（不可启动）。run.sh 会先跑本脚本。
"""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

OK = "\033[32m✓\033[0m"
BAD = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"

failures: list[str] = []
warnings: list[str] = []


def line(status: str, label: str, detail: str) -> None:
    print(f"  {status} {label:<26} {detail}")


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _port_report(port: int) -> dict:
    free = port_free(port)
    fallback = None
    if not free:
        fallback = next((p for p in range(port + 1, port + 40) if port_free(p)), None)
    return {"preferred": port, "free": free, "fallback": fallback}


def collect_json() -> dict:
    """把体检事实收成一份可机器判定的 JSON（不打印、不退出）。"""
    from app import config as config_mod
    from app.services import envcheck

    cfg = config_mod.load_config()
    packages = envcheck.packages_report()
    sqlite = envcheck.sqlite_report()
    fonts = envcheck.fonts_report()
    render = envcheck.render_report()
    runtime = envcheck.runtime_report()
    data_dirs = {}
    writable = True
    for name, path in (
        ("data", cfg.data_dir),
        ("files", cfg.data_dir / "files"),
        ("exports", cfg.data_dir / "exports"),
        ("imports", cfg.data_dir / "imports"),
    ):
        data_dirs[name] = {"path": str(path), "exists": path.exists()}
    try:
        probe_dir = cfg.data_dir / "tmp"
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe = probe_dir / ".preflight"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        writable = False
        data_dirs["error"] = str(exc)

    env_path = ROOT / ".env"
    env_mode = oct(env_path.stat().st_mode & 0o777) if env_path.exists() else None
    port = _port_report(cfg.app_port)

    checks: list[dict] = []

    def add(kind: str, item: str, ok: bool, detail: str) -> None:
        checks.append({"kind": kind, "item": item, "ok": bool(ok), "detail": detail})

    add("python", "version", sys.version_info >= (3, 10), f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    add("deps", "missing", not packages.get("missing"), ", ".join(packages.get("missing") or []) or "all")
    add("sqlite", "fts5", bool(sqlite.get("fts5")), str(sqlite.get("version")))
    add("fonts", "chinese", bool(fonts.get("ok")), str(fonts.get("primary")))
    add("engines", "reportlab", bool(render.get("pdf_primary")), str(render.get("pdf_primary")))
    add("engines", "chrome", bool(render.get("chrome_available")), str(render.get("pdf_fallback")))
    add("data_dirs", "writable", writable, str(cfg.data_dir))
    add("config", ".env", env_mode == "0o600", str(env_mode))
    add("config", "llm", bool(cfg.ready), cfg.not_ready_reason or f"{cfg.provider} · {cfg.model}")
    add("config", "data_dir_inside", cfg.data_dir.resolve().is_relative_to(ROOT / "data"), str(cfg.data_dir))
    add("ports", str(cfg.app_port), port["free"], "空闲" if port["free"] else f"顺延到 {port['fallback']}")

    fatal = {"missing", "fts5", "chinese", "writable", "data_dir_inside", port["preferred"] and str(cfg.app_port)}
    failures = [item for item in checks if not item["ok"] and item["item"] in {"missing", "fts5", "chinese", "writable", "data_dir_inside"}]
    if not port["free"] and not port["fallback"]:
        failures.append({"kind": "ports", "item": str(cfg.app_port), "ok": False, "detail": "无空闲端口"})
    warnings = [item for item in checks if not item["ok"] and item not in failures]

    return {
        "ok": not failures,
        "python": {"version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", "ok": sys.version_info >= (3, 10)},
        "venv": runtime.get("venv"),
        "system_site_packages": runtime.get("system_site_packages"),
        "deps": [
            {"name": name, "ok": True, "version": version}
            for name, version in (packages.get("packages") or {}).items()
        ]
        + [{"name": name, "ok": False, "version": None} for name in packages.get("missing_packages") or []],
        "fonts": [
            {
                "family": item.get("font") or item.get("engine"),
                "engine": item.get("engine"),
                "path": item.get("path"),
                "ok": bool(item.get("available")),
            }
            for item in (fonts.get("chain") or [])
            if isinstance(item, dict)
        ],
        "engines": {
            "reportlab": {"ok": bool(render.get("pdf_primary")), "reason": str(render.get("pdf_primary"))},
            "chrome": {"ok": bool(render.get("chrome_available")), "reason": str(render.get("pdf_fallback"))},
            "soffice": {"ok": bool(render.get("soffice_available")), "reason": "可选回退"},
        },
        "ports": {"preferred": cfg.app_port, "free": port["free"], "actual": cfg.app_port if port["free"] else port["fallback"]},
        "data_dirs": data_dirs,
        "config": {"env_mode": env_mode, "key_set": bool(cfg.key_set), "llm_ready": bool(cfg.ready), "provider": cfg.provider, "model": cfg.model},
        "failures": failures,
        "warnings": warnings,
        "exit_code": 2 if failures else (1 if warnings else 0),
    }


def main_json() -> int:
    body = collect_json()
    print(json.dumps(body, ensure_ascii=False, indent=2))
    return int(body["exit_code"])


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--json" in argv:
        return main_json()
    print("resume-warehouse 启动前体检\n")
    print("  【运行环境】")
    version = sys.version_info
    line(OK if version >= (3, 10) else BAD, "Python", f"{version.major}.{version.minor}.{version.micro}")
    if version < (3, 10):
        failures.append("Python 版本过低（需要 >= 3.10）")

    from app import config as config_mod
    from app import db as db_mod
    from app.services import envcheck

    cfg = config_mod.load_config()
    packages = envcheck.packages_report()
    missing = packages.get("missing") or []
    line(OK if not missing else BAD, "Python 依赖", "全部可用" if not missing else f"缺少 {', '.join(missing)}")
    if missing:
        failures.append(f"缺少依赖：{', '.join(missing)}（运行 scripts/bootstrap.sh）")

    sqlite = envcheck.sqlite_report()
    line(OK if sqlite.get("fts5") else BAD, "SQLite", f"{sqlite.get('version')} · FTS5={'on' if sqlite.get('fts5') else 'off'}")
    if not sqlite.get("fts5"):
        failures.append("SQLite 缺少 FTS5（经历包全文检索不可用）")

    fonts = envcheck.fonts_report()
    line(OK if fonts.get("ok") else BAD, "中文字体", f"{fonts.get('primary')} / {fonts.get('bold')}" if fonts.get("ok") else "未找到可嵌入宋体")
    if not fonts.get("ok"):
        failures.append("缺少可嵌入的中文字体（PDF 导出会失败）")

    print("\n  【数据目录】")
    for name, path in (
        ("data", cfg.data_dir),
        ("app.db", cfg.data_dir / "app.db"),
        ("files/", cfg.data_dir / "files"),
        ("exports/", cfg.data_dir / "exports"),
        ("imports/", cfg.data_dir / "imports"),
    ):
        exists = path.exists()
        line(OK if exists else WARN, name, str(path) + ("" if exists else "（首次启动会自动创建）"))

    try:
        probe = cfg.data_dir / "tmp"
        probe.mkdir(parents=True, exist_ok=True)
        test_file = probe / ".preflight"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        line(OK, "写入权限", str(cfg.data_dir))
    except OSError as exc:
        line(BAD, "写入权限", str(exc))
        failures.append(f"数据目录不可写：{cfg.data_dir}")

    print("\n  【配置】")
    env_path = ROOT / ".env"
    if env_path.exists():
        mode = oct(env_path.stat().st_mode & 0o777)
        line(OK if mode == "0o600" else WARN, ".env", f"{env_path.name} 权限 {mode}")
        if mode != "0o600":
            warnings.append(".env 权限不是 600（建议 chmod 600 .env）")
    else:
        line(WARN, ".env", "不存在（服务仍可启动，LLM 通道不可用）")
        warnings.append("未配置 .env；可在设置页或复制 .env.example 后填 LLM_API_KEY")

    line(OK if cfg.key_set else WARN, "API Key", "已配置" if cfg.key_set else "未配置")
    line(OK if cfg.ready else WARN, "LLM 通道", f"{cfg.provider} · {cfg.model} · {cfg.base_url or '无 base_url'}")
    if not cfg.ready:
        warnings.append(f"LLM 通道不可用：{cfg.not_ready_reason}")
    line(OK if cfg.data_dir.resolve().is_relative_to(ROOT / "data") else BAD, "DATA_DIR 归属", str(cfg.data_dir))
    if not cfg.data_dir.resolve().is_relative_to(ROOT / "data"):
        failures.append("DATA_DIR 必须位于 resume-warehouse/data 内")

    print("\n  【端口】")
    port = cfg.app_port
    free = port_free(port)
    if free:
        line(OK, f"127.0.0.1:{port}", "空闲")
    else:
        fallback = next((p for p in range(port + 1, port + 40) if port_free(p)), None)
        if fallback:
            line(WARN, f"127.0.0.1:{port}", f"被占用，将顺延到 {fallback}")
            warnings.append(f"端口 {port} 被占用，服务会使用 {fallback}（实际端口见 data/runtime/app_port）")
        else:
            line(BAD, f"127.0.0.1:{port}", "被占用且附近无空闲端口")
            failures.append("找不到可用端口")

    print()
    for item in warnings:
        print(f"  {WARN} {item}")
    if failures:
        print()
        for item in failures:
            print(f"  {BAD} {item}")
        print("\n体检未通过。")
        return 1
    print("体检通过，可以启动。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
