#!/usr/bin/env python3
"""出网边界静态检查（AC-PRIV-10）。

规则：**上行**数据出口只允许 `server/app/adapters/llm_client.py` 一处。
其他模块出现 ``httpx.`` / ``requests.`` / ``urllib.request`` / ``http.client``
等真实网络调用即判失败（``fetch_client`` 属于下行只读抓取，单独白名单）。

用法：
    python scripts/check_egress.py          # 输出违规明细
    python scripts/check_egress.py --json   # 机器可读
退出码：0 合规；1 有违规。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "server" / "app"

# 唯一允许发起上行请求的模块
UPLINK_ALLOWED = {"server/app/adapters/llm_client.py"}
# 下行只读抓取（t7 使用；不得携带用户简历/个人数据）
DOWNLINK_ALLOWED = {"server/app/adapters/fetch_client.py"}

NETWORK_CALL = re.compile(
    r"""(?x)
    (?:
        httpx\.(?:Client|AsyncClient|get|post|request|stream|head|put|delete)\b
      | requests\.(?:get|post|put|patch|delete|head|request|Session)\b
      | urllib\.request\.(?:urlopen|Request|build_opener)\b
      | urllib\.request\.urlretrieve\b
      | http\.client\.(?:HTTPConnection|HTTPSConnection)\b
      | socket\.create_connection\b
      | socket\.socket\(
      | aiohttp\.(?:ClientSession|request)\b
    )
    """
)
# 明显的注释/字符串说明可以放过，但不做语义分析——宁可误报也不漏报
COMMENT_PREFIXES = ("#", "//")


def scan() -> dict:
    violations: list[dict] = []
    scanned = 0
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        scanned += 1
        if rel in UPLINK_ALLOWED or rel in DOWNLINK_ALLOWED:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # pragma: no cover
            violations.append({"file": rel, "line": 0, "code": "不可读（非 UTF-8）", "snippet": ""})
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(COMMENT_PREFIXES):
                continue
            match = NETWORK_CALL.search(line)
            if match:
                violations.append(
                    {
                        "file": rel,
                        "line": number,
                        "code": match.group(0),
                        "snippet": stripped[:120],
                    }
                )
    return {
        "ok": not violations,
        "scanned_files": scanned,
        "uplink_allowed": sorted(UPLINK_ALLOWED),
        "downlink_allowed": sorted(DOWNLINK_ALLOWED),
        "violations": violations,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="出网边界静态检查")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    args = parser.parse_args(argv)

    result = scan()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("出网边界检查")
        print(f"  扫描 {result['scanned_files']} 个模块")
        print(f"  上行白名单：{', '.join(result['uplink_allowed'])}")
        print(f"  下行白名单：{', '.join(result['downlink_allowed'])}")
        if result["ok"]:
            print("  ✓ 合规：除白名单外没有任何模块发起网络调用")
        else:
            print(f"  ✗ 发现 {len(result['violations'])} 处违规：")
            for item in result["violations"]:
                print(f"    - {item['file']}:{item['line']}  {item['code']}")
                print(f"      {item['snippet']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
