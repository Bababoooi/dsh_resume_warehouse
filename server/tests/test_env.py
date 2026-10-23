"""``GET /api/v1/env`` 回归测试。

两次真实故障的护栏：
① `reportlab` 的 `TTFont().face.name` 是 `TTFNameBytes`（bytes 子类）→ jsonify 抛
   `TypeError: Object of type TTFNameBytes is not JSON serializable` → 500；
② 不能用 `str()` 取字体名（会得到 ``b'STSongti-SC-Regular'`` 这种脏值）。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent.parent
SERVER = PROJECT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))


class EnvEndpointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        base = PROJECT / "data" / "_tests"
        base.mkdir(parents=True, exist_ok=True)
        cls._tmp = tempfile.TemporaryDirectory(dir=base)
        os.environ["DATA_DIR"] = cls._tmp.name

        from app import config as config_mod
        from app import db as db_mod
        from app import create_app

        db_mod.reset_paths_for_tests()
        cls._db = db_mod
        cls.app = create_app(config_mod.load_config())
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._db.close_conn()
        cls._db.reset_paths_for_tests()
        os.environ.pop("DATA_DIR", None)
        cls._tmp.cleanup()

    def test_env_returns_200_and_is_json_serializable(self) -> None:
        response = self.client.get("/api/v1/env")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:800])
        body = json.loads(response.get_data(as_text=True))
        self.assertTrue(body["ok"])
        # 整份文档可序列化（bytes 已被出口防线转成 str）
        json.dumps(body, ensure_ascii=False)
        data = body["data"]
        for key in ("python", "venv", "system_site_packages", "packages", "missing_packages", "sqlite", "fonts", "render", "llm", "paths", "warnings"):
            self.assertIn(key, data)

    def test_font_names_are_clean_strings(self) -> None:
        data = self.client.get("/api/v1/env").get_json()["data"]
        fonts = data["fonts"]
        self.assertTrue(fonts["ok"], f"字体自检失败：{fonts}")
        self.assertEqual(fonts["primary"]["name"], "STSongti-SC-Regular")
        self.assertEqual(fonts["bold"]["name"], "STSongti-SC-Bold")
        self.assertIsInstance(fonts["primary"]["name"], str)
        # 反向断言：整份响应里不能出现 bytes 的 repr
        raw = self.client.get("/api/v1/env").get_data(as_text=True)
        self.assertNotIn("b'", raw)

    def test_no_bytes_leak_in_deep_payload(self) -> None:
        """递归扫一遍：响应里任何层级的字符串都不该是 bytes repr。"""

        def walk(node: object, path: str = "data") -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    self.assertIsInstance(key, str)
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")
            elif isinstance(node, str):
                self.assertFalse(node.startswith("b'") and node.endswith("'"), f"{path} 像 bytes repr：{node[:60]}")
            else:
                self.assertIn(type(node), (int, float, bool, type(None)), f"{path} 类型不可序列化：{type(node)}")

        walk(self.client.get("/api/v1/env").get_json()["data"])


if __name__ == "__main__":
    unittest.main()
