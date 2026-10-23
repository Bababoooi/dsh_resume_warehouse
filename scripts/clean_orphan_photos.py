#!/usr/bin/env python3
"""清理 `data/profile/` 下不再被使用的照片（captain m01505 ②）。

背景：照片是内容寻址存储（``photo_<sha16>.<ext>``），``DELETE /profile/photo`` 只解绑
不删文件（合理：可撤销），所以破坏性探针或反复确认会留下没人用的 PNG。

两级判定（都不碰 ``data/imports/**`` 用户原始简历）：

* **孤儿 orphan**：既不是当前简历照片（``user_profile.photo_path``），也没被任何
  导入草稿的 ``extracted_photo.file`` 引用 —— 默认即可清理；
* **游离 detached**：文件只被 ``attachment`` 表登记（历史候选附件），既不在简历里
  也不在草稿里 —— 需要显式 ``--prune-detached`` 才清，避免误删用户还想手动确认的候选。

用法::

    python3 scripts/clean_orphan_photos.py                              # 只报告（dry-run）
    python3 scripts/clean_orphan_photos.py --delete                     # 删孤儿
    python3 scripts/clean_orphan_photos.py --delete --prune-detached    # 连游离候选一起
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app import db as db_mod  # noqa: E402


_ADDRESSED_RE = re.compile(r"[0-9a-f]{16}")


def _draft_refs(conn) -> dict[str, list[str]]:
    """导入草稿里还留着的照片候选 → {rel_path: [import_id, ...]}（用户稍后可能要确认）。"""
    refs: dict[str, list[str]] = {}
    for import_id, draft_json in conn.execute("SELECT id, draft_json FROM import_job").fetchall():
        if not draft_json:
            continue
        try:
            draft = json.loads(draft_json)
        except (TypeError, ValueError):
            continue
        rel = ((draft or {}).get("extracted_photo") or {}).get("file")
        if rel:
            refs.setdefault(str(rel).replace("\\", "/"), []).append(str(import_id))
    return refs


def _draft_files(conn) -> set[str]:
    """导入草稿里还留着的照片候选（用户可能稍后确认，不能当垃圾清掉）。"""
    return set(_draft_refs(conn))


def _profile_file(conn) -> str | None:
    row = conn.execute("SELECT photo_path FROM user_profile WHERE id = 'me'").fetchone()
    return str(row[0]).replace("\\", "/") if row and row[0] else None


def classify(paths: db_mod.Paths, conn) -> tuple[list[Path], list[Path]]:
    """返回 ``(孤儿, 游离)``，都按路径排序，稳定可测。"""
    profile_dir = paths.root / "profile"
    if not profile_dir.exists():
        return [], []
    in_use = _draft_files(conn)
    current = _profile_file(conn)
    if current:
        in_use.add(current)
    registered_shas = {
        str(sha)[:16]
        for (sha,) in conn.execute("SELECT sha256 FROM attachment WHERE kind = 'photo'").fetchall()
        if sha
    }
    orphans: list[Path] = []
    detached: list[Path] = []
    for path in sorted(profile_dir.glob("photo_*")):
        # 只处理内容寻址命名 photo_<16 位 hex>.<ext>；其它名字（例如人工放进来的
        # 联调素材 photo_from_zh_resume.png）没有 sha、删了无法重建，脚本不替人判断。
        token = path.stem.rsplit("_", 1)[-1]
        if not _ADDRESSED_RE.fullmatch(token):
            continue
        rel = path.relative_to(paths.root).as_posix()
        if rel in in_use:
            continue
        (detached if token in registered_shas else orphans).append(path)
    return orphans, detached


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="列出/删除 data/profile 下不再使用的照片")
    parser.add_argument("--delete", action="store_true", help="真的删除（默认只报告）")
    parser.add_argument(
        "--prune-detached", action="store_true", help="连只被 attachment 表登记的游离候选一起删"
    )
    parser.add_argument("--data-dir", default=None, help="覆盖 DATA_DIR（默认读 .env）")
    parser.add_argument(
        "--explain", action="store_true", help="逐个文件说明为什么保留/可清（诊断用，不动文件）"
    )
    args = parser.parse_args(argv)

    paths = db_mod.get_paths()
    if args.data_dir:
        paths = db_mod.Paths(db_mod.resolve_data_root(args.data_dir))
    conn = db_mod.get_conn()
    try:
        if args.explain:
            return _explain(paths, conn)
        orphans, detached = classify(paths, conn)
        targets = list(orphans) + (detached if args.prune_detached else [])
        for path in targets:
            size = path.stat().st_size
            print(f"{'删除' if args.delete else '待清'} {path}（{size} 字节）")
            if args.delete:
                path.unlink()
        for path in detached:
            if not args.prune_detached:
                print(f"游离候选（加 --prune-detached 才删） {path}")
        if not targets and not detached:
            print("没有需要清理的照片。")
            return 0
        print(f"共清理 {len(targets)} 个；模式={'delete' if args.delete else 'dry-run'}")
        if not args.delete:
            print("加 --delete 才会真删。")
        return 0
    finally:
        db_mod.close_conn()


def _explain(paths: db_mod.Paths, conn) -> int:
    """逐个照片文件打印「谁在引用它」，用于判断某张图到底能不能清。"""
    profile_dir = paths.root / "profile"
    draft_refs = _draft_refs(conn)
    current = _profile_file(conn)
    attachments = {
        str(sha)[:16]: str(rel or "")
        for sha, rel in conn.execute("SELECT sha256, '' FROM attachment WHERE kind = 'photo'").fetchall()
        if sha
    }
    if not profile_dir.exists():
        print("没有 data/profile 目录。")
        return 0
    for path in sorted(profile_dir.iterdir()):
        if not path.is_file():
            continue
        rel = path.relative_to(paths.root).as_posix()
        token = path.stem.rsplit("_", 1)[-1]
        reasons: list[str] = []
        if rel == current:
            reasons.append("当前简历照片 (user_profile.photo_path)")
        if rel in draft_refs:
            reasons.append(f"{len(draft_refs[rel])} 个导入草稿引用：{', '.join(draft_refs[rel][:3])}")
        if token in attachments:
            reasons.append("attachment 表已登记（历史候选附件）")
        addressed = bool(_ADDRESSED_RE.fullmatch(token))
        verdict = "保留" if reasons else ("可清（孤儿）" if addressed else "保留（非内容寻址命名）")
        print(f"{path.name}  [{verdict}]  {'; '.join(reasons) or '无引用'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
