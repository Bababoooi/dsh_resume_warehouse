#!/usr/bin/env python3
"""caption 侧导出 PDF 独立验收器（只读，不写库、不改文件）。

用途：t8 出第一份真 PDF 之前先把「判据工具」写好并自验，
     免得产物到手时才发现判据本身不可用（我们已经栽过三次）。

用法：
    python3 data/eval/check_export_pdf.py --pdf <path> [--expect-pages 1]
        [--min-size 9.5] [--photo] [--draft <draft.json>] [--identity <profile.json>]

判据（与 docs/ACCEPTANCE.md 对齐）：
    pages            == --expect-pages（默认 1）
    min_size         >= --min-size（默认 9.5pt，正文可读下限）
    photo            --photo 时要求恰 1 张图，且 89.28±0.5pt、距顶 3.82±1、距右 9.13±1
    bullets          --draft 时要求 PDF 文本行里「·」开头的条目数 == draft bullet 总数
    identity         --identity 时要求姓名/电话/邮箱**在 PDF 里出现**（本机渲染须回填真值）
    overflow         所有字符 x1 <= page.width - right_margin + 1（默认右边距 42.5pt）

退出码：0 全过 / 1 有 FAIL / 2 用法或输入错误。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PHOTO_SIZE_PT = 89.28
PHOTO_TOP_PT = 3.82
PHOTO_RIGHT_PT = 9.13
# 版心右边距按 density 取值（见 ARCHITECTURE §7.5.1）：
#   original = 用户原件密度（右 15.62pt）—— 默认
#   relaxed  = 通用边距（右 42.5pt = 15mm）
DENSITY_RIGHT_PT = {"original": 15.62, "relaxed": 42.5}
MARGIN_X_PT = DENSITY_RIGHT_PT["original"]

TOL_SIZE = 0.5
TOL_POS = 1.0
TOL_OVERFLOW = 1.0


def median(values):
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return None
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


def load_draft_bullets(path: Path) -> tuple[int, list[str]]:
    """draft 里的要点总数：entry.bullets 与 education 的 facts 都算正文条目。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    blocks = data.get("blocks") or []
    total = 0
    texts: list[str] = []
    for block in blocks:
        if block.get("block_type") != "entry":
            continue
        entry = block.get("entry") or {}
        for key in ("bullets", "facts"):
            for item in entry.get(key) or []:
                if str(item).strip():
                    total += 1
                    texts.append(str(item).strip())
    return total, texts


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="导出 PDF 独立验收器（只读）")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--expect-pages", type=int, default=1)
    parser.add_argument("--min-size", type=float, default=9.5)
    parser.add_argument("--photo", action="store_true")
    parser.add_argument("--draft")
    parser.add_argument("--identity")
    parser.add_argument("--density", choices=("original", "relaxed"), default="original",
                        help="版式密度，决定版心右边距（original=15.62pt / relaxed=42.5pt）")
    parser.add_argument("--right-margin", type=float, default=None,
                        help="显式指定版心右边距（pt），覆盖 --density；0=跳过溢出检查")
    parser.add_argument("--json-out")
    args = parser.parse_args(argv)

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"[FATAL] 找不到 PDF: {pdf_path}", file=sys.stderr)
        return 2

    try:
        import pdfplumber
    except ImportError:
        print("[FATAL] 需要 pdfplumber（/opt/anaconda3/bin/python3 已自带）", file=sys.stderr)
        return 2

    right_margin_pt = (args.right_margin if args.right_margin is not None
                       else DENSITY_RIGHT_PT[args.density])
    checks: list[dict] = []
    info: dict = {"density": args.density}

    def record(name, ok, detail, hint=None):
        checks.append({"check": name, "status": "PASS" if ok else "FAIL",
                       "detail": detail, "hint": hint})

    with pdfplumber.open(pdf_path) as doc:
        pages = doc.pages
        info["pages"] = len(pages)
        record("pages", len(pages) == args.expect_pages,
               f"实测 {len(pages)} 页，期望 {args.expect_pages} 页",
               None if len(pages) == args.expect_pages else "掉页通常是正文装不下：应走降档阶梯并发 PAGE_FIT_DOWNGRADED")

        sizes: list[float] = []
        all_chars = []
        for page in pages:
            for ch in page.chars:
                if not ch["text"].strip():
                    continue
                all_chars.append((page, ch))
                sizes.append(round(float(ch.get("size") or 0.0), 2))
        info["min_size"] = min(sizes) if sizes else None
        info["size_mode_top3"] = Counter(sizes).most_common(3)
        info["median_size"] = median(sizes)
        info["chars"] = len(sizes)
        min_size = info["min_size"]
        record("min_size", min_size is not None and min_size >= args.min_size,
               f"最小字号 {min_size}pt（阈值 {args.min_size}pt），众数 {info['size_mode_top3']}",
               None if (min_size or 0) >= args.min_size else "缩到阈值以下＝拿可读性换页数，不可接受")

        # 溢出：字符右缘不得超过可用版心
        overflow = []
        skip_overflow = float(right_margin_pt) <= 0
        for page, ch in all_chars:
            if skip_overflow:
                break
            limit = float(page.width) - float(right_margin_pt) + TOL_OVERFLOW
            if float(ch["x1"]) > limit:
                overflow.append({"text": ch["text"], "x1": round(float(ch["x1"]), 2),
                                 "limit": round(limit, 2), "page": pages.index(page) + 1})
        info["overflow_count"] = None if skip_overflow else len(overflow)
        info["right_margin_pt"] = None if skip_overflow else float(right_margin_pt)
        if not skip_overflow:
            record("no_horizontal_overflow", not overflow,
                   f"越界字符 {len(overflow)} 个" + (f"，例 {overflow[:3]}" if overflow else ""),
                   None if not overflow else "英文长词应整词换行，不得越出版心")

        # 照片几何（mediaBox 下边非 0 时必须归一化，这是 pdfplumber 的已知陷阱）
        if args.photo:
            images = []
            for idx, page in enumerate(pages, start=1):
                # pdfplumber 的 mediabox 为 (x0, top, x1, bottom) 顶下坐标系；
                # top 通常是负值（页面下边非 0），需用 -top 归一化到物理纸张顶边。
                mbox = page.mediabox
                mbox_top = float(mbox.top if hasattr(mbox, "top") else mbox[1])
                bottom_off = -mbox_top
                for im in page.images:
                    top_page = float(im["top"]) + bottom_off
                    images.append({
                        "page": idx,
                        "w": round(float(im["x1"]) - float(im["x0"]), 2),
                        "h": round(float(im["bottom"]) - float(im["top"]), 2),
                        "x0": round(float(im["x0"]), 2),
                        "top_from_page_top": round(top_page, 2),
                        "right_gap": round(float(page.width) - float(im["x1"]), 2),
                        "mediabox_bottom": round(bottom_off, 2),
                    })
            info["images"] = images
            one = len(images) == 1
            record("photo_count", one, f"图片数 {len(images)}，期望 1",
                   None if one else "照片必须恰 1 张（用户明确要求保留）")
            if one:
                im = images[0]
                ok_size = abs(im["w"] - PHOTO_SIZE_PT) <= TOL_SIZE and abs(im["h"] - PHOTO_SIZE_PT) <= TOL_SIZE
                record("photo_size", ok_size,
                       f"{im['w']}×{im['h']}pt，期望 {PHOTO_SIZE_PT}±{TOL_SIZE}",
                       None if ok_size else "照片尺寸被改动（不得随字号降档缩放）")
                ok_top = abs(im["top_from_page_top"] - PHOTO_TOP_PT) <= TOL_POS
                record("photo_top", ok_top,
                       f"距页顶 {im['top_from_page_top']}pt（已按 mediabox.bottom={im['mediabox_bottom']} 归一），期望 {PHOTO_TOP_PT}±{TOL_POS}",
                       None if ok_top else "距顶偏移；注意 mediabox 下边非 0 时 pdfplumber 的 top 会整体偏移")
                ok_right = abs(im["right_gap"] - PHOTO_RIGHT_PT) <= TOL_POS
                record("photo_right", ok_right,
                       f"距右缘 {im['right_gap']}pt，期望 {PHOTO_RIGHT_PT}±{TOL_POS}",
                       None if ok_right else "右边距偏移（98.42 是照片左边位置，不是边距）")

        # 要点完整性：PDF 里「·」开头的行数必须等于 draft 条目总数
        if args.draft:
            draft_total, draft_texts = load_draft_bullets(Path(args.draft))
            text = "\n".join((p.extract_text() or "") for p in pages)
            opened = [ln for ln in text.splitlines() if ln.strip().startswith(("·", "•"))]
            info["draft_entries"] = draft_total
            info["pdf_bullet_lines"] = len(opened)
            record("bullets_not_trimmed", len(opened) == draft_total,
                   f"PDF 条目行 {len(opened)}，draft 条目 {draft_total}",
                   None if len(opened) == draft_total else "少了条目＝裁内容换页数，比掉页更不可接受")
            missing = [t for t in draft_texts[:40]
                       if not any(_squash(t) in _squash(ln) for ln in text.splitlines())]
            info["draft_texts_missing"] = len(missing)
            record("entry_text_present", not missing,
                   f"草稿条目中未在 PDF 文本层找到 {len(missing)} 条" + (f"，例 {missing[:2]}" if missing else ""),
                   None if not missing else "正文被改写或截断（只允许排版换行，不允许改字）")

        # 身份回填：本机渲染必须把真名/电话/邮箱填回去
        if args.identity:
            profile = json.loads(Path(args.identity).read_text(encoding="utf-8"))
            text = "\n".join((p.extract_text() or "") for p in pages)
            flat = _squash(text)
            expected = {k: profile.get(k) for k in ("name_zh", "phone", "email") if profile.get(k)}
            absent = [k for k, v in expected.items() if _squash(str(v)) not in flat]
            info["identity_expected"] = list(expected)
            info["identity_absent"] = absent
            record("identity_restored", not absent,
                   f"应出现 {list(expected)}，未找到 {absent}",
                   None if not absent else "脱敏只作用于上行 payload；本机 PDF 必须回填真值")

    failed = [c for c in checks if c["status"] == "FAIL"]
    report = {"pdf": str(pdf_path), "info": info, "checks": checks,
              "verdict": "PASS" if not failed else "FAIL", "failed": len(failed)}
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                                       encoding="utf-8")
    return 0 if not failed else 1


def _squash(text: str) -> str:
    return "".join(str(text).split())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
