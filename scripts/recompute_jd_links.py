#!/usr/bin/env python3
"""重算已存 JD 的匹配结论（F-08）——**纯本地，零出网**。

背景：`jd_requirement` 六行的 `matched_package_ids_json` 全是 `[]`、`candidate_status_source`
全是 `llm`，页面上仍显示「未体现 A/B 测试」这类旧结论。根因是分析当时本地匹配还没接上
（仓库要点 / 档案技能行没有被当作证据）。现在 `jd_analysis.link_requirements` 已经能用
可引用原文重算，但**历史行不会自己变**——这个脚本就是用来补齐的。

安全约定：
* 默认 dry-run，只打印 `before → after`，不改库；
* `--apply` 前把 `data/app.db` 备份到 `data/runtime/` 并打印 md5（可回滚）；
* 全程不联网：脚本不 import 任何 llm/httpx 模块，`--apply` 后会对比 `llm_call_log`
  行数，多一行就报错退出（证明零出网）。

用法：
    python scripts/recompute_jd_links.py                 # 看看会变成什么
    python scripts/recompute_jd_links.py --apply         # 真的写回（先自动备份）
    python scripts/recompute_jd_links.py --jd <id> --json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app import db as db_mod  # noqa: E402
from app import config as config_mod  # noqa: E402
from app.repos import JdRepo, PackageRepo, ProfileRepo  # noqa: E402
from app.services import jd_analysis  # noqa: E402


def md5_of(path: Path) -> str:
    digest = hashlib.md5()  # noqa: S324 - 只作备份一致性校验，不做安全用途
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup_db(db_path: Path, runtime_dir: Path) -> Path:
    """一致性备份（用 sqlite backup API，不直接 copy 正在写的库）。"""
    runtime_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = runtime_dir / f"app.db.pre_links_{stamp}"
    source = sqlite3.connect(str(db_path))
    dest = sqlite3.connect(str(target))
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    return target


def _count_llm_calls(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM llm_call_log").fetchone()
    return int(row[0]) if row else 0


def _brief(requirement: dict[str, Any]) -> dict[str, Any]:
    return {
        "skill": requirement.get("skill"),
        "status": requirement.get("candidate_status"),
        "source": requirement.get("candidate_status_source"),
        "matched": requirement.get("matched_package_ids") or [],
        # 证据也要进 before/after 对比：只比 status/命中包 id 会漏掉「补上可核对引文」
        # 这一类变化，dry-run 就会谎报「无变化」（t15 实测踩过）。
        "evidence": [f"{item.get('source')}:{(item.get('quote') or '')[:24]}" for item in (requirement.get("matched_evidence") or [])],
        "hint": (requirement.get("evidence_hint") or requirement.get("raw_quote") or "")[:40],
    }


def _expected_sources(skill: str, packages: list[dict[str, Any]], profile: dict[str, Any] | None) -> list[str]:
    """这条 requirement 的文本**是否命中了本地证据源**（与重算结果无关地独立判断）。

    为什么要单独算一遍：`expected_but_unchanged` 要挡的是「空转当收敛」——
    重算跑完、状态还是 missing、命中包还是空，但技能文本明明能在本地证据里找到
    （技能行里写着「熟练掌握 SQL、Python」）。这种行必须被点名，不能混在「无变化」里。

    只做归一化子串比较，不产生任何写操作，也不联网。
    """
    needles = [needle for needle in jd_analysis._needles(skill) if len(needle) >= 2]
    if not needles:
        return []
    sources: list[str] = []
    package_texts = [jd_analysis._norm(jd_analysis._package_corpus(package)) for package in packages]
    skill_lines = [jd_analysis._norm(str(row.get("line") or "")) for row in ((profile or {}).get("skills") or [])]
    for needle in needles:
        if any(needle in text for text in package_texts):
            sources.append("package")
        if any(needle in line for line in skill_lines):
            sources.append("skills_json")
    return sorted(set(sources))


def _python_name() -> str:
    """报告里记的命令统一写成 `python3`，便于人读与对账（不代表解释器绝对路径）。"""
    return "python3"


def collect_expected_but_unchanged(
    jd_id: str,
    rows: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
    packages: list[dict[str, Any]],
    profile: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """挑出「本地证据明明有、重算后却还是空」的条目（空转当收敛）。

    抽成独立函数是为了能被单测直接喂假数据 —— 真实库里如果每条都已对齐，
    这个列表本来就该是空的；空列表不等于「没查」，所以报告里另带 `checked_against`。
    """
    out: list[dict[str, Any]] = []
    for row, requirement in zip(rows, requirements, strict=False):
        after = row["after"]
        if after["status"] != "missing" or after["matched"] or after["evidence"]:
            continue
        sources = _expected_sources(str(requirement.get("skill") or ""), packages, profile)
        if sources:
            out.append(
                {
                    "jd_id": jd_id,
                    "requirement_id": requirement.get("id"),
                    "skill": requirement.get("skill"),
                    "why_expected": "命中本地证据源但重算后仍为空",
                    "evidence_sources": sources,
                }
            )
    return out


def recompute(
    *,
    apply: bool,
    jd_id: str | None,
    out_json: bool,
    report_path: Path | None = None,
    snapshot: dict[str, str] | None = None,
) -> int:
    cfg = config_mod.load_config()
    paths = db_mod.get_paths()
    paths.ensure()
    conn = db_mod.get_conn()

    packages_repo = PackageRepo()
    profile = ProfileRepo().get()
    # ready 包才参与匹配：draft 里常有半句话，拿它当证据会误导用户
    envelope = packages_repo.list(status="ready", limit=200, include_variants=True)
    packages = [package for package in (envelope.get("items") or []) if package.get("variants")]

    jds = JdRepo().get(jd_id) if jd_id else None
    if jd_id and jds is None:
        print(f"找不到 JD：{jd_id}", file=sys.stderr)
        return 2
    jd_ids = [jd_id] if jd_id else [
        str(row["id"]) for row in conn.execute("SELECT id FROM job_description ORDER BY created_at")
    ]

    before_calls = _count_llm_calls(conn)
    report: list[dict[str, Any]] = []
    expected_but_unchanged: list[dict[str, Any]] = []
    changes = 0
    for current in jd_ids:
        requirements = JdRepo().list_requirements(current)
        if not requirements:
            continue
        before = [_brief(dict(req)) for req in requirements]
        working = [dict(req) for req in requirements]
        warnings: list[dict[str, Any]] = []
        jd_analysis.link_requirements(working, packages, profile=profile, warnings=warnings)
        after = [_brief(req) for req in working]
        rows = []
        for old, new, req in zip(before, after, working, strict=True):
            changed = old != new
            changes += int(changed)
            rows.append(
                {
                    "id": req.get("id"),
                    # 列名叫 `skill`，但它存的是**整条需求描述文本**（「熟练掌握 SQL、Python」），
                    # 不是一个技能关键词——别按名字猜成 key，也别去找叫 `text` 的列。
                    "skill": req.get("skill"),
                    "changed": changed,
                    "before": old,
                    "after": new,
                }
            )
            if apply and changed:
                JdRepo().set_local_link(
                    str(req["id"]),
                    candidate_status=req.get("candidate_status"),
                    candidate_status_source=req.get("candidate_status_source"),
                    matched_package_ids=req.get("matched_package_ids") or [],
                    matched_evidence=req.get("matched_evidence") or [],
                    evidence_hint=req.get("evidence_hint"),
                    raw_quote=req.get("raw_quote"),
                )
        for row in rows:
            if row["changed"] and row["before"] == row["after"]:
                print(f"!! 自检失败：{row['id']} 标了 changed 但 before == after", file=sys.stderr)
                return 4
        expected_but_unchanged.extend(collect_expected_but_unchanged(current, rows, working, packages, profile))
        report.append({"jd_id": current, "requirements": rows, "warnings": warnings})

    after_calls = _count_llm_calls(conn)
    outbound_calls = after_calls - before_calls
    from datetime import datetime, timezone

    payload = {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "mode": "apply" if apply else "dry-run",
        "outbound_calls": outbound_calls,
        "jds": report,
        # 键必须存在（可以是空数组）：验收用它挡「空转当收敛」（T-16）
        "expected_but_unchanged": expected_but_unchanged,
        # 说明这次「预期命中」的判断查过哪些证据源（避免 expected_but_unchanged 为空被读成「没查」）
        "checked_against": "skills_json+packages(title/org/role/tech_stack/tags/variants)+profile(degree/major)",
        # 原样记录本次进程的命令行（手写字符串会与实际执行脱节）
        "command": " ".join([_python_name(), *sys.argv]),
    }
    if snapshot is not None:
        payload["snapshot"] = snapshot
    if outbound_calls != 0:
        print(f"!! 出现 {outbound_calls} 次上游调用，违反「只允许本地重算」", file=sys.stderr)
        return 3
    if out_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"JD 数：{len(report)}　参与匹配的 ready 包：{len(packages)}　变化条目：{changes}")
        for block in report:
            print(f"\n# JD {block['jd_id']}")
            for row in block["requirements"]:
                mark = "→" if row["changed"] else "="
                old, new = row["before"], row["after"]
                print(f"  {mark} {old['skill']}")
                print(f"      状态 {old['status']}({old['source']}) → {new['status']}({new['source']})")
                print(f"      命中 {old['matched']} → {new['matched']}")
                if row["changed"]:
                    print(f"      证据 {new['evidence'] or '（无）'}")
        print(f"\n上游调用：{outbound_calls}（必须为 0）")

    if report_path is not None:
        target = Path(report_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"报告已写入 {target}（mode={payload['mode']}，expected_but_unchanged={len(expected_but_unchanged)}）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本地重算 JD 匹配结论（零出网）")
    parser.add_argument("--apply", action="store_true", help="真的写回（会先备份 app.db）")
    parser.add_argument("--jd", default=None, help="只处理这一条 JD")
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    parser.add_argument(
        "--report",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help=(
            "把结构化报告写盘（省略路径时写 data/exports/relink_report_<UTC>.json）。"
            "本文件必须由真实运行产生，禁止手工编辑：报告里的 command/snapshot/outbound_calls "
            "都由本次进程自己写下，手改会让人无法回溯这次重算到底动过什么。"
        ),
    )
    args = parser.parse_args(argv)

    snapshot: dict[str, str] | None = None
    if args.apply:
        cfg = config_mod.load_config()
        paths = db_mod.get_paths()
        if paths.db.exists():
            backup = backup_db(paths.db, Path(paths.root) / "runtime")
            snapshot = {
                "path": str(backup),
                "md5": md5_of(backup),
                # 备份后、apply 前的源库 md5：回滚时用来确认「还原到哪个版本」
                "source_md5_before_apply": md5_of(paths.db),
            }
            print(f"已备份 {paths.db} → {backup}")
            print(f"备份 md5={snapshot['md5']}　源文件 md5={snapshot['source_md5_before_apply']}")
    report_path: Path | None = None
    if args.report is not None:
        if args.report:
            report_path = Path(args.report)
        else:
            from datetime import datetime, timezone

            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            report_path = db_mod.get_paths().root / "exports" / f"relink_report_{stamp}.json"
    return recompute(apply=args.apply, jd_id=args.jd, out_json=args.json, report_path=report_path, snapshot=snapshot)


if __name__ == "__main__":
    raise SystemExit(main())
