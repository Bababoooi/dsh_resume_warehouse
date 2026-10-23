#!/usr/bin/env python3
"""把 `data/imports/` 里的真实简历跑一遍导入，产出可人工过目的草稿文件。

用途（t5 验收）：
    cd resume-warehouse && python server/scripts/build_import_draft.py
产物：
    data/exports/import_draft_zh_v10.json / .md     ← 中文单页简历
    data/exports/import_draft_en_withphoto.json/.md ← 英文双页简历（含照片）

说明：
- 只读 `data/imports/**`（本机真实简历），写 `data/exports/**`；不联网、不调 LLM。
- 草稿保留原文，不做任何润色；照片会落到 `data/profile/`。
- 文件名含 PII，全部在 `data/` 下，已被 .gitignore 排除。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from app import db as db_mod  # noqa: E402
from app.repos import ImportRepo  # noqa: E402
from app.services import import_service  # noqa: E402
from app.services.storage import Storage  # noqa: E402

#: 素材文件名 → 导出 stem
TARGETS = {
    "sample_zh.pdf": "import_draft_zh_v10",
    "sample_en.pdf": "import_draft_en_withphoto",
}


def run_one(source: Path, stem: str) -> dict:
    storage = Storage()
    result = import_service.run_import(
        source.read_bytes(),
        filename=source.name,
        parser="pdf",
        storage=storage,
    )
    import_id = result["import_id"]
    draft = result["draft"]
    artifacts = import_service.write_artifacts(
        import_id, storage=storage, stem=stem, draft=draft
    )
    return {
        "source": str(source),
        "import_id": import_id,
        "stem": stem,
        "sections": draft.get("section_kinds"),
        "entry_counts": draft.get("entry_counts"),
        "skills": len(draft.get("skills") or []),
        "warnings": [w.get("code") for w in (draft.get("warnings") or [])],
        "photo": (draft.get("extracted_photo") or {}).get("file"),
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        choices=sorted(TARGETS.values()),
        help="只处理一个 stem（默认两份都跑）",
    )
    args = parser.parse_args()

    db_mod.reset_paths_for_tests()
    paths = db_mod.get_paths()
    paths.ensure()
    db_mod.migrate(db_mod.get_conn())

    report = []
    for name, stem in TARGETS.items():
        if args.only and args.only != stem:
            continue
        source = paths.imports / name
        if not source.exists():
            print(f"跳过（缺少素材）：{source}", file=sys.stderr)
            continue
        report.append(run_one(source, stem))

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report:
        print("没有可处理的素材", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
