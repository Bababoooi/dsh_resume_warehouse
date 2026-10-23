"""启动回归测试：编译通过 ≠ 能跑起来。

覆盖三件事：
① 进程内 ``create_app()`` + test_client → ``/api/v1/health`` 200 且 status=ok；
② 进程外真启动 ``server/server.py``，轮询 health 直到 200（15s 超时打印 stderr），
   并断言 ``data/runtime/app_port`` 写的就是实际端口；
③ 端口顺延：先占住 8765，再启动，断言实际端口 ≠ 8765 且端口文件写的是新端口。

跑法：cd resume-warehouse && python -m unittest discover -s server/tests -v
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent.parent
SERVER = PROJECT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fetch_health(port: int, timeout: float = 1.0) -> tuple[int, dict]:
    url = f"http://127.0.0.1:{port}/api/v1/health"
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - 本机地址
        return response.status, json.loads(response.read().decode("utf-8"))


def wait_until_healthy(port: int, process: subprocess.Popen, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read().decode("utf-8", "ignore") if process.stderr else ""
            raise AssertionError(f"服务进程提前退出（code={process.returncode}）：\n{stderr[-3000:]}")
        try:
            status, payload = fetch_health(port)
            if status == 200 and payload.get("data", {}).get("status") in ("ok", "degraded"):
                return payload
        except (urllib.error.URLError, ConnectionError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(0.2)
    stderr = ""
    if process.poll() is None:
        process.terminate()
    if process.stderr:
        try:
            stderr = process.stderr.read().decode("utf-8", "ignore")
        except Exception:  # pragma: no cover - 进程已退出
            stderr = ""
    raise AssertionError(f"15s 内 health 未返回 200（last_error={last_error!r}）：\n{stderr[-3000:]}")


class BootTest(unittest.TestCase):
    def setUp(self) -> None:
        base = PROJECT / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        self._tmp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name)
        self.env = dict(os.environ)
        self.env["DATA_DIR"] = str(self.data_dir)
        self.env.setdefault("LLM_PROVIDER", "deepseek")
        self.processes: list[subprocess.Popen] = []

    def tearDown(self) -> None:
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:  # pragma: no cover
                    process.kill()
        for process in self.processes:
            if process.stderr:
                process.stderr.close()

    # -- ① 进程内 -----------------------------------------------------------------
    def test_in_process_app_health(self) -> None:
        os.environ["DATA_DIR"] = str(self.data_dir)
        from app import config as config_mod
        from app import db as db_mod
        from app import create_app

        db_mod.reset_paths_for_tests()
        try:
            app = create_app(config_mod.load_config(environ=self.env))
            client = app.test_client()
            response = client.get("/api/v1/health")
            self.assertEqual(response.status_code, 200)
            body = response.get_json()
            self.assertTrue(body["ok"])
            self.assertIn(body["data"]["status"], ("ok", "degraded"))
            self.assertIn("version", body["data"])
            # D-27：必须能一条命令判断「这个进程是不是当前代码」
            build = body["data"]["build"]
            self.assertTrue(build["id"], build)
            self.assertTrue(str(build["source"]).startswith("src-"), build)
            # 别名同样可用
            self.assertEqual(client.get("/api/health").status_code, 200)
            # 统一错误格式
            missing = client.get("/api/v1/packages/does-not-exist")
            self.assertEqual(missing.status_code, 404)
            self.assertFalse(missing.get_json()["ok"])
            self.assertEqual(missing.get_json()["error"]["code"], "NOT_FOUND")
        finally:
            db_mod.close_conn()
            db_mod.reset_paths_for_tests()
            os.environ.pop("DATA_DIR", None)

    # -- ② 进程外真启动 -----------------------------------------------------------
    def _start(self, port: int) -> tuple[subprocess.Popen, int]:
        process = subprocess.Popen(
            [sys.executable, str(SERVER / "server.py"), "--port", str(port)],
            cwd=str(PROJECT),
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.processes.append(process)
        return process, port

    def test_subprocess_boots_and_writes_port_file(self) -> None:
        port = free_port()
        process, _ = self._start(port)
        payload = wait_until_healthy(port, process)
        self.assertIn(payload["data"]["status"], ("ok", "degraded"))

        port_file = self.data_dir / "runtime" / "app_port"
        self.assertTrue(port_file.exists(), "data/runtime/app_port 未生成")
        recorded = json.loads(port_file.read_text(encoding="utf-8"))
        self.assertEqual(recorded["port"], port)
        self.assertEqual(recorded["url"], f"http://127.0.0.1:{port}")
        # 三值必须相等：/health.port == app_port.port == 实际 curl 的端口
        self.assertEqual(payload["data"]["port"], port, "/health 报的不是实际绑定端口")

        process.terminate()
        code = process.wait(timeout=10)
        self.assertIn(code, (0, -15, -9))
        # D-26：优雅退出时，自己写的端口文件要清掉（否则下次启动就是陈旧指针）
        if not port_file.exists():
            return
        leftover = json.loads(port_file.read_text(encoding="utf-8"))
        self.assertNotEqual(leftover.get("pid"), recorded["pid"], "退出后端口文件仍指向已死进程")

    # -- ③ 端口顺延 ----------------------------------------------------------------
    def test_port_fallback_when_busy(self) -> None:
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        blocked_port = free_port()
        blocker.bind(("127.0.0.1", blocked_port))
        blocker.listen(1)
        self.addCleanup(blocker.close)

        process, _ = self._start(blocked_port)
        deadline = time.monotonic() + 15.0
        recorded: dict | None = None
        port_file = self.data_dir / "runtime" / "app_port"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stderr = process.stderr.read().decode("utf-8", "ignore") if process.stderr else ""
                raise AssertionError(f"服务进程提前退出（code={process.returncode}）：\n{stderr[-3000:]}")
            if port_file.exists():
                try:
                    recorded = json.loads(port_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    recorded = None
                if recorded:
                    break
            time.sleep(0.2)
        self.assertIsNotNone(recorded, "15s 内未写出端口文件")
        actual = recorded["port"]
        self.assertNotEqual(actual, blocked_port, "端口顺延失效：仍然报告被占用的端口")
        self.assertGreater(actual, blocked_port)
        payload = wait_until_healthy(actual, process)
        # 端口顺延后，/health、端口文件、实际监听三者必须一致
        self.assertEqual(payload["data"]["port"], actual)
        self.assertEqual(recorded["port"], actual)

    # -- ④ 陈旧端口文件（D-26）-----------------------------------------------------
    def test_stale_port_file_is_overwritten(self) -> None:
        """文件指向已死 pid + 不可连端口 → 必须被本次真实端口覆盖。"""
        runtime = self.data_dir / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        stale_port = free_port()
        (runtime / "app_port").write_text(
            json.dumps({"port": stale_port, "host": "127.0.0.1", "url": f"http://127.0.0.1:{stale_port}",
                        "pid": 999_999, "started_at": "2020-01-01T00:00:00+08:00"}),
            encoding="utf-8",
        )
        port = free_port()
        process, _ = self._start(port)
        payload = wait_until_healthy(port, process)
        recorded = json.loads((runtime / "app_port").read_text(encoding="utf-8"))
        self.assertEqual(recorded["port"], port, "陈旧端口文件未被覆盖（用户会打开白屏地址）")
        self.assertEqual(recorded["pid"], process.pid)
        self.assertEqual(payload["data"]["port"], port)

    def test_port_file_of_other_instance_is_not_deleted(self) -> None:
        """退出清理只认自己的 pid（多实例时不能删掉别人的指针）。"""
        import importlib.util  # noqa: PLC0415

        from app import db as db_mod  # noqa: E402

        # 直接按文件加载 server.py：仓库里的 ``server/`` 目录会让 ``import server`` 命中命名空间包
        spec = importlib.util.spec_from_file_location("rw_server_entry", SERVER / "server.py")
        assert spec and spec.loader
        server_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server_mod)

        runtime = self.data_dir / "runtime"
        runtime.mkdir(parents=True, exist_ok=True)
        target = runtime / "app_port"
        target.write_text(json.dumps({"port": 4321, "pid": 999_998}), encoding="utf-8")
        paths = db_mod.Paths(self.data_dir)
        server_mod.clear_runtime_port(paths)
        self.assertTrue(target.exists(), "不该删除别的实例写的端口文件")
        target.write_text(json.dumps({"port": 4321, "pid": os.getpid()}), encoding="utf-8")
        server_mod.clear_runtime_port(paths)
        self.assertFalse(target.exists(), "自己写的端口文件退出时应清掉")


if __name__ == "__main__":
    unittest.main()
