#!/usr/bin/env python3
"""把两份 JD 样张跑成可复核的分析结果（t7 自测产物）。

产物：

* ``data/exports/jd_a_school.json``   —— A 例（明示 985/211 门槛）
* ``data/exports/jd_b_noschool.json`` —— B 例（全文不提院校）
* ``data/exports/jd_c_hard.json``     —— C 例（明示硬门槛「仅限 985/211」）

设计约束（与 ``build_import_draft.py`` 一致）：

* **零出网**：只走启发式（``method=heuristic``），不调用任何 LLM、不发 HTTP；
* 只读 ``data/eval/jd_samples/**``，不写库以外的任何用户数据；
* 产物同时写 ``meta``（生成时间、输入 sha256、判据来源），便于 t10 复核「产物是否新于代码」。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

import os  # noqa: E402

PROJECT = SERVER.parent
SAMPLES = PROJECT / "data" / "eval" / "jd_samples"
EXPORTS = PROJECT / "data" / "exports"

#: 三例夹具（captain 04:14 重做）：偏好 / 无信号 / 硬门槛。旧 ``jd_school_filtered.md``
#: 因「说明文字自污染」（前言里的「不得编造 985/211」被当成 JD 正文）已废弃删除。
TARGETS = {
    "jd_a_school.json": "jd_school_preference.md",
    "jd_b_noschool.json": "jd_no_school.md",
    "jd_c_hard.json": "jd_school_hard.md",
}

PROFILE = {
    "name_zh": "示例同学",
    "school_zh": "示例大学",
    "degree": "硕士",
    "major": "管理科学（商业数据分析）",
    "grad_year": 2028,
    "city": "武汉",
    "skills": [
        {"line": "数据分析类：Python、SQL、Excel、数据可视化", "category": "数据分析类"},
    ],
}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def analyze(text: str) -> dict:
    from app.services import jd_analysis

    requirements = jd_analysis.heuristic_requirements(text, profile=PROFILE, packages=())
    school_preference = jd_analysis.detect_school_gate([text])
    warnings: list[dict] = []
    competitiveness = jd_analysis.competitiveness(
        profile=PROFILE,
        school_preference=school_preference,
        requirements=requirements,
        warnings=warnings,
    )
    return {
        "school_preference": school_preference,
        "competitiveness": competitiveness,
        "requirements": requirements,
        "warnings": warnings,
        "match": jd_analysis.match_packages(requirements, []),
    }


def main() -> int:
    if not SAMPLES.exists():
        print(f"缺少样张目录：{SAMPLES}", file=sys.stderr)
        return 1
    EXPORTS.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, source in TARGETS.items():
        path = SAMPLES / source
        if not path.exists():
            print(f"跳过（缺失）：{path}", file=sys.stderr)
            continue
        text = path.read_text(encoding="utf-8")
        payload = {
            "meta": {
                "generated_by": "server/scripts/build_jd_samples.py",
                "source": f"data/eval/jd_samples/{source}",
                "source_sha256": sha256(text),
                "method": "heuristic",
                "network": "none",
                "profile": "data/_tests 隔离档案（示例同学 / 示例大学 / 硕士）",
                "criteria": "docs/API-CONTRACT.md §6.1 §7 + data/eval/jd_samples/expectations.json",
            },
            "jd": {"title": source, "chars": len(text)},
            **analyze(text),
        }
        target = EXPORTS / filename
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append((target, target.stat().st_size, sha256(target.read_text(encoding="utf-8"))))
        pref = payload["school_preference"]
        print(
            f"{target.name}: hard_filter={pref['hard_filter']} threshold={pref['threshold']!r} "
            f"verdict={payload['competitiveness']['verdict']} requirements={len(payload['requirements'])}"
        )
    for path, size, digest in written:
        print(f"  {path.relative_to(PROJECT)}  {size} bytes  sha256={digest[:12]}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("DATA_DIR", str(PROJECT / "data" / "_tests" / "jd_samples_build"))
    raise SystemExit(main())
