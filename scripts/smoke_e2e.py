#!/usr/bin/env python3
"""端到端冒烟：真起一个后端进程，走完「档案 → 导入 → 分析 → 组装 → 导出」。

跑法（captain 的 Verify 命令之一）：

    .venv/bin/python scripts/smoke_e2e.py            # 默认临时 DATA_DIR，跑完即删
    .venv/bin/python scripts/smoke_e2e.py --keep     # 保留数据目录（调试用）

它只做**用户真会做的事**，不做任何 poke-private-internals 的检查：

1. ``GET /api/v1/health`` 必须是 ok，且 ``db.schema_version`` 存在；
2. ``PUT /api/v1/profile`` 写档案 → ``POST /naming/validate`` 当场回 ``{position}-{name}-{school}.pdf``；
   把姓名改掉，同一条模板立刻给出新文件名（证明没有硬编码、也没有缓存）；
3. ``POST /api/v1/imports``（粘贴文本，不依赖 data/imports 里的真实简历）→ ``commit``
   with ``also_create_packages`` → 经历库里有包；
4. ``POST /api/v1/jds`` + ``analyze(method=heuristic)`` → 需求与竞争力结论齐全（不联网）；
5. ``POST /api/v1/builds`` → ``PUT selections`` → ``POST export`` → 轮询 job →
   产物文件名等于第 2 步算出来的名字，PDF 能被 pypdf 打开且五段齐全。

退出码 0＝全绿；任何一步不符就打印失败原因并以 1 退出。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
PY = PROJECT / ".venv" / "bin" / "python"
DEFAULT_DATA = PROJECT / "data" / "_smoke_e2e"

PASTE_TEXT = """张三
示例大学-本科26届 | 到岗时间：2026年7月
手机号码：13800138000 | 邮箱：zhangsan@example.com

教育背景
2022.9-2026.6 示例大学-管理学院 信息管理与信息系统 本科
专业成绩：GPA 3.72/4 88.50/100 CET4：580

实习经历
示例科技有限公司 - 数据分析实习生 2025.07 - 2025.10
搭建订单看板，把日报生成时间从 3 小时压缩到 20 分钟，覆盖 128 家门店。
针对异常订单做归因分析，定位 7 类主因，客诉率下降 18%。

项目经历
门店销量预测模型 - 队长 2025.03 - 2025.05
整合 49 家门店两年订单数据，对比 12 种回归模型后选定 Ridge，预测误差降到 9.4%。

校园活动
2022.9 - 至今 示例大学 学习委员
曾获荣誉：校级三好学生。

职业技能
数据分析类：掌握 Python、SQL，可独立完成数据清洗与可视化
基础办公类：熟练使用 Excel 数据透视表与 VLOOKUP
"""


class Smoke:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.failures: list[str] = []
        self.checks = 0

    # -- 基础 HTTP -----------------------------------------------------------
    def call(self, method: str, path: str, payload=None, *, expect=(200,), raw=False):
        url = self.base + path
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:  # 让断言看到真实的错误体
            body, status = exc.read(), exc.code
        if raw:
            return status, body
        try:
            parsed = json.loads(body or b"{}")
        except json.JSONDecodeError:
            parsed = {"_raw": body[:400].decode("utf-8", "ignore")}
        if status not in expect:
            self.failures.append(f"{method} {path} → {status}（期望 {expect}）：{json.dumps(parsed, ensure_ascii=False)[:300]}")
        return status, parsed

    def ok(self, label: str, condition: bool, detail: str = "") -> None:
        self.checks += 1
        if condition:
            print(f"  ✓ {label}")
        else:
            print(f"  ✗ {label}  {detail}")
            self.failures.append(f"{label} {detail}".strip())


def free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(data_dir: Path) -> tuple[subprocess.Popen, str]:
    env = dict(os.environ)
    env["DATA_DIR"] = str(data_dir)
    env["PYTHONUNBUFFERED"] = "1"
    port = free_port()
    proc = subprocess.Popen(
        [str(PY), "server/server.py", "--port", str(port)],
        cwd=str(PROJECT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 40
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            raise SystemExit(f"服务启动即退出：\n{out[-2000:]}")
        try:
            with urllib.request.urlopen(base + "/api/v1/health", timeout=2) as response:
                if response.status == 200:
                    return proc, base
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.25)
    proc.terminate()
    raise SystemExit("服务 40s 内未就绪")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="保留临时数据目录")
    parser.add_argument("--data-dir", default=None, help="指定数据目录（默认 data/_smoke_e2e）")
    args = parser.parse_args()

    data_dir = Path(args.data_dir) if args.data_dir else DEFAULT_DATA
    if data_dir.exists() and not args.keep:
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    proc, base = start_server(data_dir)
    smoke = Smoke(base)
    try:
        print(f"[1/5] 健康检查  {base}")
        _status, health = smoke.call("GET", "/api/v1/health")
        data = health.get("data") or {}
        smoke.ok("health=ok", data.get("status") == "ok", str(data)[:200])
        smoke.ok("db.schema_version 存在", bool((data.get("db") or {}).get("schema_version")))

        print("[2/5] 档案 + 命名模板")
        profile = {
            "name_zh": "张三",
            "name_en": "SAN ZHANG",
            "school_zh": "示例大学",
            "school_en": "Example University",
            "degree": "本科",
            "major": "信息管理与信息系统",
            "grad_year": 2026,
            "phone": "13800138000",
            "email": "zhangsan@example.com",
            "city": "杭州",
            "available_note": "2026年7月",
            "extra": {"degree_en": "B.M.", "major_en": "Information Management", "city_en": "Hangzhou", "available_note_en": "July 2026"},
        }
        _status, saved = smoke.call("PUT", "/api/v1/profile", profile)
        smoke.ok("档案写入", (saved.get("data") or {}).get("name_zh") == "张三")

        pattern = {"pattern": "{position}-{name}-{school}", "lang": "zh", "position": "数据分析实习生"}
        _status, naming = smoke.call("POST", "/api/v1/naming/validate", pattern)
        expected_name = (naming.get("data") or {}).get("filename")
        smoke.ok(
            "文件名 = 岗位-姓名-学校",
            expected_name == "数据分析实习生-张三-示例大学.pdf",
            str(expected_name),
        )
        sources = {item["name"]: item["source"] for item in (naming.get("data") or {}).get("variables", [])}
        smoke.ok("姓名来自 UserProfile", str(sources.get("name", "")).startswith("profile."), str(sources))
        smoke.ok("校名来自 UserProfile", str(sources.get("school", "")).startswith("profile."), str(sources))

        # 改档案 → 文件名立刻联动（证明没有硬编码，也没有缓存）
        smoke.call("PUT", "/api/v1/profile", {"name_zh": "李四"})
        _status, renamed = smoke.call("POST", "/api/v1/naming/validate", pattern)
        smoke.ok(
            "改档案后文件名联动",
            (renamed.get("data") or {}).get("filename") == "数据分析实习生-李四-示例大学.pdf",
            str((renamed.get("data") or {}).get("filename")),
        )
        smoke.call("PUT", "/api/v1/profile", {"name_zh": "张三"})

        # 缺学校必须报错而不是产出残缺名
        smoke.call("PUT", "/api/v1/profile", {"school_zh": None})
        _status, broken = smoke.call("POST", "/api/v1/naming/validate", pattern)
        broken_data = broken.get("data") or {}
        codes = [err.get("code") for err in broken_data.get("errors") or []]
        smoke.ok("缺学校 → NAMING_MISSING_VAR", "NAMING_MISSING_VAR" in codes, str(codes))
        smoke.ok("缺学校 → 不产出文件名", not broken_data.get("filename"), str(broken_data.get("filename")))
        smoke.call("PUT", "/api/v1/profile", {"school_zh": "示例大学"})

        print("[3/5] 导入 → 模板 + 经历包")
        _status, imported = smoke.call("POST", "/api/v1/imports", {"text": PASTE_TEXT, "filename": "smoke.txt"}, expect=(200, 201))
        import_id = (imported.get("data") or {}).get("import_id") or ""
        smoke.ok("导入草稿", bool(import_id), str(imported)[:200])
        blocks = ((imported.get("data") or {}).get("blocks") or [])
        smoke.ok("草稿按块拆开（≥6 块）", len(blocks) >= 6, f"blocks={len(blocks)}")
        _status, committed = smoke.call(
            "POST",
            f"/api/v1/imports/{import_id}/commit",
            {"template_name": "冒烟模板", "lang": "zh", "set_default": True, "also_create_packages": True},
            expect=(201,),
        )
        created = (committed.get("data") or {}).get("packages_created") or []
        smoke.ok("导入派生经历包", bool(created), str((committed.get("data") or {}).get("packages_created"))[:200])

        _status, packages = smoke.call("GET", "/api/v1/packages?limit=50&include_variants=1")
        items = (packages.get("data") or {}).get("items") or []
        ready = [item for item in items if item.get("status") == "ready"]
        smoke.ok("经历库有可用条目", bool(ready), f"items={len(items)} ready={len(ready)}")

        print("[4/5] JD 分析（离线启发式）")
        _status, jd = smoke.call(
            "POST",
            "/api/v1/jds",
            {
                "title": "数据分析实习生",
                "company_name": "星链数科（杭州）有限公司",
                "raw_text": "岗位要求：985/211 院校优先；熟悉 SQL、Python；有数据分析实习经验。",
            },
            expect=(200, 201),
        )
        jd_id = (jd.get("data") or {}).get("id") or ""
        smoke.ok("JD 入库", bool(jd_id))
        smoke.call("POST", f"/api/v1/jds/{jd_id}/analyze", {"method": "heuristic"}, expect=(200, 202))
        deadline = time.time() + 30
        detail = {}
        while time.time() < deadline:
            _status, got = smoke.call("GET", f"/api/v1/jds/{jd_id}")
            detail = got.get("data") or {}
            if detail.get("analysis_status") == "done":
                break
            time.sleep(0.3)
        smoke.ok("JD 分析完成", detail.get("analysis_status") == "done", str(detail.get("analysis_status")))
        competition = detail.get("competitiveness") or {}
        smoke.ok("竞争力结论齐全", competition.get("verdict") in ("strong", "medium", "weak"), str(competition)[:160])
        smoke.ok("校名被真正消费", bool(competition.get("school_signal")), str(competition.get("school_signal"))[:120])
        smoke.ok("需求条目非空", bool(detail.get("requirements")), f"n={len(detail.get('requirements') or [])}")
        _status, matched = smoke.call("POST", f"/api/v1/jds/{jd_id}/match")
        smoke.ok("本地匹配打分", bool((matched.get("data") or {}).get("scores")), str(matched)[:160])

        print("[5/5] 组装 → 导出 PDF")
        _status, templ = smoke.call("GET", "/api/v1/templates/default?lang=zh")
        template_id = (templ.get("data") or {}).get("id") or ""
        _status, build = smoke.call(
            "POST",
            "/api/v1/builds",
            {
                "name": "冒烟构建",
                "template_id": template_id,
                "jd_id": jd_id or None,
                "position": "数据分析实习生",
                "company": "星链数科（杭州）有限公司",
                "lang": "zh",
            },
            expect=(201,),
        )
        build_id = (build.get("data") or {}).get("id") or ""
        smoke.ok("构建记录", bool(build_id))
        selections = [{"package_id": item["id"]} for item in ready]
        smoke.call("PUT", f"/api/v1/builds/{build_id}/selections", {"items": selections})
        _status, assembled = smoke.call("POST", f"/api/v1/builds/{build_id}/assemble")
        sections = (assembled.get("data") or {}).get("sections") or []
        smoke.ok("组装出段落", len(sections) >= 3, f"sections={[s.get('heading') for s in sections]}")

        _status, exported = smoke.call("POST", f"/api/v1/builds/{build_id}/export", {"format": "pdf", "verify_text": True}, expect=(202,))
        job_id = (exported.get("data") or {}).get("job_id") or ""
        deadline = time.time() + 120
        job = {}
        while time.time() < deadline:
            _status, got = smoke.call("GET", f"/api/v1/jobs/{job_id}")
            job = got.get("data") or {}
            if job.get("status") in ("succeeded", "failed"):
                break
            time.sleep(0.4)
        smoke.ok("导出任务成功", job.get("status") == "succeeded", json.dumps(job.get("error_json"), ensure_ascii=False)[:300])
        result = job.get("result_json") or {}
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                result = {}
        artifacts = result.get("artifacts") or []
        smoke.ok("产出 1 个 PDF", len(artifacts) == 1 and artifacts[0].get("format") == "pdf", str(artifacts)[:200])
        artifact = artifacts[0] if artifacts else {}
        smoke.ok("文件名 = 岗位-姓名-学校", artifact.get("filename") == "数据分析实习生-张三-示例大学.pdf", str(artifact.get("filename")))
        smoke.ok("文本层校验通过", artifact.get("text_verified") is True, str(artifact.get("warnings_json"))[:200])

        pdf_path = data_dir / "exports" / str(artifact.get("filename") or "")
        smoke.ok("PDF 落盘", pdf_path.exists(), str(pdf_path))
        if pdf_path.exists():
            try:
                from pypdf import PdfReader

                reader = PdfReader(io.BytesIO(pdf_path.read_bytes()))
                text = "\n".join((page.extract_text() or "") for page in reader.pages)
                smoke.ok("PDF 可打开且单页", len(reader.pages) == 1, f"pages={len(reader.pages)}")
                smoke.ok("PDF 含姓名", "张三" in text)
                smoke.ok("PDF 含校名", "示例大学" in text)
                smoke.ok("PDF 段落齐全", all(h in text for h in ("教育背景", "实习经历", "项目经历")), text[:200])
            except Exception as exc:  # noqa: BLE001
                smoke.ok("PDF 可解析", False, repr(exc))

        # 下载链接必须可用（用户点「下载」就是这条）
        if artifact.get("id"):
            status, body = smoke.call("GET", f"/api/v1/artifacts/{artifact['id']}/download", raw=True)
            smoke.ok("产物下载可用", status == 200 and body[:4] == b"%PDF", f"status={status}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        if not args.keep:
            shutil.rmtree(data_dir, ignore_errors=True)

    print()
    if smoke.failures:
        print(f"FAILED：{len(smoke.failures)}/{smoke.checks} 项不符")
        for item in smoke.failures:
            print(f"  - {item}")
        return 1
    print(f"PASS：{smoke.checks} 项检查全绿（数据目录：{'保留 ' + str(data_dir) if args.keep else '已清理'}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
