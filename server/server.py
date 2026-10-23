#!/usr/bin/env python3
"""resume-warehouse 本地服务入口。

只监听 127.0.0.1；端口默认取 ``APP_PORT``（8765），被占用则顺延到下一个空闲端口，
并把实际端口写入 ``data/runtime/app_port``——run.sh / DSH Skill / 启动横幅都读它。
启动时把上一次残留的 running/queued 任务标为 interrupted（ARCHITECTURE §6）。
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import signal
import socket
import sys
from datetime import datetime
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app import create_app  # noqa: E402
from app import config as config_mod  # noqa: E402
from app import db as db_mod  # noqa: E402

HOST = "127.0.0.1"
PORT_SCAN_LIMIT = 40


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError as exc:
            if exc.errno in (errno.EADDRINUSE, errno.EACCES):
                return False
            raise
    return True


def pick_port(host: str, preferred: int) -> int:
    for candidate in range(preferred, preferred + PORT_SCAN_LIMIT):
        if port_is_free(host, candidate):
            return candidate
    raise SystemExit(
        f"无法启动：{preferred}–{preferred + PORT_SCAN_LIMIT - 1} 范围内没有空闲端口。"
        f"请关闭占用端口的程序，或在 .env 里改 APP_PORT。"
    )


def _pid_alive(pid: int) -> bool:
    """进程是否存活（``os.kill(pid, 0)`` 不投递信号，只做权限/存在性检查）。"""
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - 别人的进程，存在但不可查
        return True
    except OSError:
        return False
    return True


def _port_connectable(port: int, *, timeout: float = 0.3) -> bool:
    if port <= 0:
        return False
    try:
        with socket.create_connection((HOST, port), timeout=timeout):
            return True
    except OSError:
        return False


def read_runtime_port(paths: db_mod.Paths) -> dict[str, object] | None:
    target = paths.root / "runtime" / "app_port"
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def runtime_port_stale(record: dict[str, object] | None) -> tuple[bool, str]:
    """判定端口文件是否陈旧（D-26）。

    陈旧 = 文件里的 pid 已死，**或**那个端口连不上。两者的后果相同：
    用户按文件里的地址打开浏览器就是白屏，而启动脚本/前端只认这个文件。
    """
    if not record:
        return True, "没有端口文件"
    try:
        pid = int(record.get("pid") or 0)
        port = int(record.get("port") or 0)
    except (TypeError, ValueError):
        return True, "端口文件内容损坏"
    if not _pid_alive(pid):
        return True, f"pid {pid} 已不存活"
    if not _port_connectable(port):
        return True, f"端口 {port} 不可连接"
    return False, f"pid {pid} 正在 {port} 运行"


def write_runtime_port(paths: db_mod.Paths, port: int) -> Path:
    runtime_dir = paths.root / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    target = runtime_dir / "app_port"

    previous = read_runtime_port(paths)
    stale, reason = runtime_port_stale(previous)
    if previous and not stale:
        # 另一个活着的实例仍在服务：不静默抢它的地址，但要说清楚（禁止静默失败）
        print(f"警告：已有实例在 http://{HOST}:{previous.get('port')} 运行（{reason}）；"
              f"本实例用 {port}，端口文件改指本实例", flush=True)
    elif previous:
        print(f"端口文件陈旧（{reason}），已覆盖为本次真实端口 {port}", flush=True)

    payload = {
        "port": port,
        "host": HOST,
        "url": f"http://{HOST}:{port}",
        "pid": os.getpid(),
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def clear_runtime_port(paths: db_mod.Paths) -> None:
    """退出时清掉端口文件 —— **只在文件里的 pid 是自己时**才删（D-26）。"""
    target = paths.root / "runtime" / "app_port"
    record = read_runtime_port(paths)
    if not record:
        return
    try:
        owner = int(record.get("pid") or 0)
    except (TypeError, ValueError):
        owner = 0
    if owner != os.getpid():
        return
    try:
        target.unlink()
    except OSError:  # pragma: no cover - 并发删除
        pass


def banner(port: int, cfg: config_mod.Config, db_path: Path) -> str:
    lines = [
        "resume-warehouse 已启动",
        f"  地址    http://{HOST}:{port}",
        f"  数据    {db_path}",
        f"  LLM     {cfg.provider} / {cfg.model}（分析 {cfg.model_analysis}）",
        f"  密钥    {'已配置' if cfg.key_set else '未配置（LLM 通道不可用）'}",
        "  停止    Ctrl+C",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="启动 resume-warehouse 本地服务")
    parser.add_argument("--port", type=int, default=None, help="覆盖 APP_PORT（仍会自动顺延）")
    parser.add_argument("--no-reload", action="store_true", help="兼容旧脚本，无实际作用")
    args = parser.parse_args(argv)

    cfg = config_mod.load_config()
    if args.port:
        cfg.app_port = args.port
    config_mod.set_config(cfg)

    app = create_app(cfg)
    paths = db_mod.get_paths()
    paths.ensure()

    # 上次残留的后台任务 → interrupted
    from app.repos import JobRepo

    interrupted = JobRepo().mark_interrupted()
    if interrupted:
        app.logger.warning("检测到 %s 个残留任务，已标记为 interrupted", interrupted)

    port = pick_port(HOST, cfg.app_port)
    if port != cfg.app_port:
        app.logger.warning("端口 %s 被占用，已顺延到 %s", cfg.app_port, port)
    runtime_file = write_runtime_port(paths, port)
    # 实际监听端口进 app 状态：/health 必须报真的绑定端口，而不是配置值
    app.extensions["bound_port"] = port

    print(banner(port, cfg, paths.db), flush=True)
    print(f"  端口文件 {runtime_file}", flush=True)

    def _shutdown(signum, frame):  # noqa: ARG001
        print("\n正在停止…", flush=True)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # 单进程多线程：SQLite 每线程一条连接（db.get_conn 已按线程局部实现）
    try:
        app.run(host=HOST, port=port, threaded=True, debug=False, use_reloader=False)
    finally:
        clear_runtime_port(paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
