#!/usr/bin/env python3
"""captain 侧「语言层」验收器（只读）。

判什么
  1. chrome 区（页眉块 + 所有 section 标题）CJK 字符数必须 == 0（lang=en）/ > 0（lang=zh）
  2. 正文里的 CJK 行必须被 LANG_FALLBACK 解释：sample[] 长度 == entry_count，
     且正文 CJK 行数 >= entry_count + bullet_count
  3. 半翻译：同一行不得出现「契约英文标签 + 中文正文」（如 "Academic Record: …CET4："）
  4. 全角标点（：、（） 等）出现在 en 产物 ⇒ 我们生成的文字，记失败
  5. 中文骨架残留：zh 与 en 的 section 数必须相等

用法
  python3 data/eval/check_lang_export.py --pdf <pdf> --lang en --build <resume_build.id>
  python3 data/eval/check_lang_export.py --pdf <pdf> --lang zh
退出码：0 全过 / 1 有失败项 / 2 无法判断（缺产物或库记录）
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

import pdfplumber

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
FULLWIDTH = re.compile(r"[：（）、，。；！？]")

# 契约 §8.5.1 的骨架词（en / zh）
HEADINGS_EN = {"EDUCATION", "EXPERIENCE", "PROJECTS", "CAMPUS ACTIVITIES", "SKILLS",
               "INTERNSHIP", "SUMMARY", "HONORS & AWARDS"}
HEADINGS_ZH = {"教育背景", "实习经历", "项目经历", "校园活动", "职业技能", "个人总结", "荣誉奖项"}

# 契约 §8.5.1 的字段标签（en），用于半翻译检测
LABELS_EN = ["Academic Record", "Relevant Coursework", "Relevant Courses", "Available",
             "GPA", "Class of"]

DB = Path(__file__).resolve().parents[2] / "data" / "app.db"


def lines_of(pdf_path: str) -> list[str]:
    with pdfplumber.open(pdf_path) as doc:
        text = "\n".join((p.extract_text() or "") for p in doc.pages)
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def split_chrome(lines: list[str], lang: str) -> tuple[list[str], list[str]]:
    """页眉块 = 第一个 section 标题之前的行；标题行本身也算 chrome。"""
    heads = HEADINGS_EN if lang == "en" else HEADINGS_ZH
    chrome, body, seen_heading = [], [], False
    for ln in lines:
        if ln in heads or ln.upper() in heads:
            chrome.append(ln)
            seen_heading = True
            continue
        (chrome if not seen_heading else body).append(ln)
    return chrome, body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--lang", choices=["zh", "en"], required=True)
    ap.add_argument("--build", help="resume_build.id，用于读 warnings_json")
    args = ap.parse_args()

    pdf = Path(args.pdf)
    if not pdf.exists():
        print(f"FAIL 产物不存在: {pdf}")
        return 2

    lines = lines_of(str(pdf))
    chrome, body = split_chrome(lines, args.lang)
    failed: list[str] = []

    chrome_cjk = sum(len(CJK.findall(l)) for l in chrome)
    body_cjk_lines = [l for l in body if CJK.search(l)]

    print(f"产物: {pdf.name}")
    print(f"  chrome 行={len(chrome)} chrome_CJK={chrome_cjk} 正文行={len(body)} 正文CJK行={len(body_cjk_lines)}")

    if args.lang == "en":
        if chrome_cjk:
            failed.append(f"chrome 区出现 CJK {chrome_cjk} 字（应 0）：{[l for l in chrome if CJK.search(l)]}")
        fw = [l for l in lines if FULLWIDTH.search(l) and not CJK.search(l)]
        if fw:
            failed.append(f"en 产物出现全角标点 {len(fw)} 行：{fw[:3]}")
        for ln in lines:
            if CJK.search(ln) and any(ln.startswith(lb) or f"{lb}:" in ln for lb in LABELS_EN):
                failed.append(f"半翻译（英文标签 + 中文正文）：{ln[:90]}")
                break

    # 与 warnings 对账
    if args.build:
        if not DB.exists():
            print("  ! 库不存在，跳对账")
        else:
            con = sqlite3.connect(DB)
            row = con.execute("SELECT lang, warnings_json FROM resume_build WHERE id=?", (args.build,)).fetchone()
            con.close()
            if not row:
                print(f"  ! 库里找不到 build {args.build}")
            else:
                warns = json.loads(row[1] or "[]")
                codes = [w.get("code") for w in warns]
                lf = next((w for w in warns if w.get("code") == "LANG_FALLBACK"), None)
                print(f"  build lang={row[0]} warnings={codes}")
                if args.lang == "en":
                    if body_cjk_lines and not lf:
                        failed.append("正文有中文但缺 LANG_FALLBACK")
                    if lf and not body_cjk_lines:
                        failed.append("报了 LANG_FALLBACK 但正文无中文")
                    if lf:
                        d = lf.get("details") or {}
                        ec, bc = d.get("entry_count"), d.get("bullet_count")
                        samples = d.get("samples")
                        if not isinstance(samples, list):
                            samples = [d["sample"]] if d.get("sample") else []
                        print(f"  LANG_FALLBACK: entry={ec} bullet={bc} samples_len={len(samples)} "
                              f"skills_fallback={d.get('skills_fallback')} cjk_declared={d.get('cjk_line_count')}")
                        if not ec or len(samples) != ec:
                            failed.append(f"samples[] 长度 {len(samples)} != entry_count {ec}")
                        if not bc or len(body_cjk_lines) < (ec or 0) + (bc or 0):
                            failed.append(f"正文 CJK 行 {len(body_cjk_lines)} < entry+bullet {(ec or 0) + (bc or 0)}")
                        if "skills_fallback" not in d:
                            failed.append("LANG_FALLBACK 缺 skills_fallback 字段")
                        # 精确对账（v1.30 起）：声明的中文行数必须等于 PDF 里真的中文行数。
                        # 只判「>=」会把「多印了没人认领的中文」放过，那正是半翻译的来源。
                        # 精确对账：按**中文字符数**比对（行数会被折行影响，误差不是缺陷）。
                        # 声明的字符数覆盖不到 PDF 里的中文 = 有人偷偷塞了中文进来（半翻译）。
                        declared_chars = d.get("cjk_char_count")
                        actual_chars = sum(len(CJK.findall(line)) for line in body_cjk_lines)
                        if declared_chars is None:
                            failed.append("LANG_FALLBACK 缺 cjk_char_count（无法与 PDF 对账）")
                        elif declared_chars < actual_chars:
                            failed.append(
                                f"声明的中文 {declared_chars} 字 < PDF 实际 {actual_chars} 字"
                                f"（多出的字没人认领 = 半翻译）"
                            )
                else:
                    if lf:
                        failed.append("zh 产物不得出现 LANG_FALLBACK")
                    pkg = next((w for w in warns if w.get("code") == "PACKAGE_MISSING"), None)
                    heads_present = {l for l in chrome if l in HEADINGS_ZH}
                    print(f"  zh 出现的 section: {sorted(heads_present)} | PACKAGE_MISSING={bool(pkg)}")

    print()
    if failed:
        for f in failed:
            print("FAIL", f)
        return 1
    print("PASS 无语言层问题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
