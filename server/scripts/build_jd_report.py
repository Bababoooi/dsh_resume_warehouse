#!/usr/bin/env python3
"""把三份 JD 样张走一遍**真实 API**（启发式路径，零出网），产出可复核报告。

产物：``data/exports/jd_analysis_report.json``

* 走 ``POST /api/v1/jds`` → ``POST /api/v1/jds/{id}/analyze``（method=heuristic）→ ``GET /api/v1/jds/{id}``
  的完整往返，不是直接调函数——这样报告同时证明「路由存在且串起来了」；
* 数据根用临时目录（``data/_tests/jd_report``），不碰用户真实库；
* 全程不发 HTTP 请求到外部（``method=heuristic`` 且未配置抓取 URL）。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

PROJECT = SERVER.parent
SAMPLES = PROJECT / "data" / "eval" / "jd_samples"
EXPORTS = PROJECT / "data" / "exports"
TMP_ROOT = PROJECT / "data" / "_tests" / "jd_report"

CASES = {
    "jd_school_preference": ("jd_school_preference.md", "星链数科（杭州）有限公司"),
    "jd_no_school": ("jd_no_school.md", "禾味食品集团"),
    "jd_school_hard": ("jd_school_hard.md", "恒锐资本管理有限公司"),
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def poll(client, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/v1/jobs/{job_id}").get_json()["data"]
        if body.get("status") in {"succeeded", "failed", "interrupted"}:
            return body
        time.sleep(0.05)
    raise RuntimeError(f"任务 {job_id} 超时未结束")


def main() -> int:
    if TMP_ROOT.exists():
        shutil.rmtree(TMP_ROOT)
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    os.environ["DATA_DIR"] = str(TMP_ROOT)

    from app import create_app
    from app import db as db_mod

    db_mod.reset_paths_for_tests()
    db_mod.get_paths().ensure()
    app = create_app()
    client = app.test_client()

    # 档案（competitiveness 需要院校/学历；姓名不会被发送，因为这里零出网）
    client.put(
        "/api/v1/profile",
        json={
            "name_zh": "示例同学",
            "school_zh": "示例大学",
            "school_tier": "985",
            "degree": "硕士",
            "major": "管理科学（商业数据分析）",
            "grad_year": 2028,
            "city": "武汉",
        },
    )

    report: dict = {
        "meta": {
            "generated_by": "server/scripts/build_jd_report.py",
            "api_base": "/api/v1",
            "method": "heuristic",
            "network": "none",
            "llm_called": False,
            "profile": "示例同学 / 示例大学（985，手填） / 硕士 / 管科",
            "cases": {},
        },
        "cases": {},
    }

    for key, (filename, company) in CASES.items():
        path = SAMPLES / filename
        if not path.exists():
            print(f"跳过（缺失）：{path}", file=sys.stderr)
            continue
        text = path.read_text(encoding="utf-8")
        created = client.post(
            "/api/v1/jds",
            json={"title": f"{company} · 样张", "company_name": company, "raw_text": text, "lang": "zh"},
        )
        if created.status_code != 201:
            raise SystemExit(f"创建 JD 失败：{created.status_code} {created.get_data(as_text=True)}")
        jd_id = created.get_json()["data"]["id"]

        analyzed = client.post(f"/api/v1/jds/{jd_id}/analyze", json={"method": "heuristic"})
        if analyzed.status_code != 202:
            raise SystemExit(f"分析失败：{analyzed.status_code} {analyzed.get_data(as_text=True)}")
        job = poll(client, analyzed.get_json()["data"]["job_id"])
        if job.get("status") != "succeeded":
            raise SystemExit(f"分析任务失败：{job.get('error_json')}")

        detail = client.get(f"/api/v1/jds/{jd_id}").get_json()["data"]
        requirements = client.get(f"/api/v1/jds/{jd_id}/requirements").get_json()["data"]["items"]
        match = client.post(f"/api/v1/jds/{jd_id}/match", json={})

        report["cases"][key] = {
            "source": f"data/eval/jd_samples/{filename}",
            "source_sha256": sha256_file(path),
            "jd_id": jd_id,
            "job": {
                "status": job.get("status"),
                "progress": job.get("progress"),
                "result": job.get("result_json"),
            },
            "jd": detail,
            "requirements": requirements,
            "match": match.get_json()["data"] if match.status_code == 200 else {"status": match.status_code},
        }
        report["meta"]["cases"][key] = {
            "company": company,
            "school_preference": (report["cases"][key]["job"]["result"] or {}).get("school_preference"),
            "verdict": ((report["cases"][key]["job"]["result"] or {}).get("competitiveness") or {}).get("verdict"),
        }
        pref = (report["cases"][key]["job"]["result"] or {}).get("school_preference") or {}
        print(
            f"{key}: hard_filter={pref.get('hard_filter')} threshold={pref.get('threshold')!r} "
            f"preferred={pref.get('preferred_tiers')} requirements={len(requirements)}"
        )

    report["meta"]["path_differences"] = {
        "llm": [
            "requirements[].raw_quote/evidence_hint 由模型给出，措辞更接近原文段落，条数受 max_tokens 限制",
            "competitiveness.school_signal/gap_notes 由模型撰写（自由文本），candidate_status 也由模型判断",
            "可能增发 warning：LLM_JSON_UNPARSABLE / OUTPUT_TRUNCATED / SCHOOL_TIER_INFERRED",
        ],
        "heuristic": [
            "requirements[] 由关键词字典 + 权重表生成（skill/category/priority/weight 固定可复现）",
            "competitiveness 四维由规则计算（degree_fit/major_fit/experience_fit），candidate_status 由包与技能命中推导",
            "必定附带 COMPETITIVENESS_FALLBACK（jd）与 SCHOOL_FILTER_FALLBACK（company）说明「未调用模型」",
        ],
        "shared": "两者字段集合完全一致（competitiveness/requirements/school_preference 均非 null），前端无需分支",
    }

    EXPORTS.mkdir(parents=True, exist_ok=True)
    target = EXPORTS / "jd_analysis_report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{target.relative_to(PROJECT)}  {target.stat().st_size} bytes")

    db_mod.close_conn()
    os.environ.pop("DATA_DIR", None)
    db_mod.reset_paths_for_tests()
    shutil.rmtree(TMP_ROOT, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
