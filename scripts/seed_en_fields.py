#!/usr/bin/env python3
"""把英文简历里的原文灌进 ``*_en`` 列（一次性数据准备，可重入）。

为什么需要它：``lang=en`` 导出时，教育段原文、经历标题、技能整句若只有中文列可取，
渲染层只能整行回退，英文简历里就会出现中文。英文原文**存进库**（而不是导出时现翻），
才能同时保住三条：预览 == 导出、同输入同产物、用户改过的措辞不被覆盖。

用法::

    PYTHONPATH=server python3 scripts/seed_en_fields.py --mapping data/en_fields.json
    PYTHONPATH=server python3 scripts/seed_en_fields.py --mapping data/en_fields.json --apply

``data/en_fields.json`` 形状（**这是你自己的数据，别提交到仓库**）::

    {
      "education": [
        "Academic Record: GPA 3.56/4, 86.53/100 · CET-4 562, CET-6 508",
        "Relevant Coursework: Statistics (92), ..."
      ],
      "skills": {
        "数据分析类：掌握Python、R、SQL等编程语言…": "Data Analysis: Python, R and SQL; ..."
      },
      "packages": {
        "杭州拓端数据科技有限公司 · 数据处理实习生": {
          "title_en": "Hangzhou Tuoduan Data Technology Co., Ltd. · Data Processing Intern",
          "org_en": "Hangzhou Tuoduan Data Technology Co., Ltd.",
          "role_en": "Data Processing Intern"
        }
      }
    }

只写 ``template_block.static_text_en`` / ``user_profile.skills_json[].line_en`` /
``package.{title,org,role}_en``，不碰任何中文列；默认 dry-run，``--apply`` 才写库。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app import db as db_mod  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", required=True, help="英文映射 JSON 路径（含自身数据，勿入库）")
    ap.add_argument("--apply", action="store_true", help="真写库（默认只打印计划）")
    args = ap.parse_args()

    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    write = bool(args.apply)
    conn = db_mod.get_conn()
    planned: list[str] = []

    education = [str(x).strip() for x in (mapping.get("education") or []) if str(x).strip()]
    if education:
        rows = conn.execute(
            "SELECT id, static_text FROM template_block "
            "WHERE block_type='entry' AND bound_package_kind='education' "
            "AND COALESCE(static_text,'')!=''"
        ).fetchall()
        for row in rows:
            planned.append(f"template_block[{row['id'][:10]}] static_text_en ← {len(education)} 行")
            if write:
                with db_mod.transaction(conn) as c:
                    c.execute(
                        "UPDATE template_block SET static_text_en=?, updated_at=? WHERE id=?",
                        ("\n".join(education), db_mod.utcnow_iso(), row["id"]),
                    )

    skills_map = mapping.get("skills") or {}
    prof = conn.execute("SELECT id, skills_json FROM user_profile LIMIT 1").fetchone()
    if prof and skills_map:
        skills = json.loads(prof["skills_json"] or "[]")
        changed = 0
        for item in skills:
            if isinstance(item, dict) and str(item.get("line") or "") in skills_map:
                item["line_en"] = skills_map[str(item["line"])]
                changed += 1
        planned.append(f"user_profile[{prof['id'][:10]}] skills_json: {changed}/{len(skills)} 行加 line_en")
        if write and changed:
            with db_mod.transaction(conn) as c:
                c.execute(
                    "UPDATE user_profile SET skills_json=?, updated_at=? WHERE id=?",
                    (json.dumps(skills, ensure_ascii=False), db_mod.utcnow_iso(), prof["id"]),
                )

    pkg_map = mapping.get("packages") or {}
    if pkg_map:
        rows = conn.execute("SELECT id, title FROM package WHERE deleted_at IS NULL").fetchall()
        hit = 0
        for row in rows:
            fields = pkg_map.get(str(row["title"]))
            if not fields:
                continue
            hit += 1
            allowed = {k: v for k, v in fields.items() if k in ("title_en", "org_en", "role_en")}
            planned.append(f"package[{row['id'][:10]}] ← {sorted(allowed)}")
            if write and allowed:
                cols = ", ".join(f"{k}=?" for k in allowed)
                with db_mod.transaction(conn) as c:
                    c.execute(
                        f"UPDATE package SET {cols}, updated_at=? WHERE id=?",
                        [*allowed.values(), db_mod.utcnow_iso(), row["id"]],
                    )
        planned.append(f"package: {hit}/{len(rows)} 个命中英文映射")

    print(("APPLY" if write else "DRY-RUN") + " 计划：")
    for line in planned:
        print("  ·", line)
    if not write:
        print("\n未写库。确认后加 --apply。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
