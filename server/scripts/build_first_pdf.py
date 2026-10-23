#!/usr/bin/env python3
"""用现有库数据出第一份 PDF（t8 联调；不造数据、不联网）。

跑法::

    PYTHONPATH=server python3 server/scripts/build_first_pdf.py

它做四件事：

1. 取「唯一活跃 package」+「默认模板」+ 档案真值，建两个 build（zh / en）；
2. 每个 build 选中该 package（优先选 verified 变体）；
3. 调 ``export_service.export`` 出 PDF（reportlab，单页优先，装不下按阶梯降档）；
4. 打印产物路径、命名、版式实测值与 warnings，并用 pdfplumber 独立量一遍
   页数 / 最小字号 / 照片坐标，作为「不由渲染器自证」的交叉核对。

**不写死任何测试数据**：包/模板/档案都从真库读，缺了就报错退出。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app import db as db_mod  # noqa: E402
from app.repos import BuildRepo, PackageRepo, ProfileRepo, TemplateRepo  # noqa: E402
from app.services import export_service  # noqa: E402


def _pick_packages() -> list[dict]:
    """取全部「可复用」经历（有 verified 变体），保持仓库顺序。

    只挑一条会让 PDF 只剩实习段——真实使用时用户当然要把项目/校园一起带上，
    所以这里按 kind 顺序尽量取全；某个段落确实没有经历时由 compose 发 PACKAGE_MISSING 说明省略。
    """
    repo = PackageRepo()
    page = repo.list(limit=100, include_variants=True)
    active = [row for row in page["items"] if not row.get("deleted_at")]
    usable = [
        row
        for row in active
        if any(int(item.get("verified") or 0) == 1 for item in row.get("variants") or [])
    ]
    if not usable:
        raise SystemExit("没有可用的经历包：先在 #/warehouse 里核实一条要点，或导入简历派生经历")
    order = {"internship": 0, "project": 1, "activity": 2, "award": 3, "education": 4, "custom": 5}
    usable.sort(key=lambda row: (order.get(row.get("kind"), 9), row.get("created_at") or ""))
    return usable


def _pick_template() -> dict:
    repo = TemplateRepo()
    template = repo.resolved_default(lang="zh") or repo.default()
    if template is None:
        raise SystemExit("没有默认模板：先在 #/import 里 commit 一份简历，或 POST /templates/{id}/default")
    return template


def _build(lang: str, packages: list[dict], template: dict, position: str) -> str:
    builds = BuildRepo()
    name = "首份导出（中文）" if lang == "zh" else "首份导出（英文）"
    build_id = builds.create(
        {
            "name": name,
            "template_id": template["id"],
            "lang": lang,
            "position": position,
            "naming_pattern": "{position}-{name}-{school}",
        }
    )
    index = 0
    for package in packages:
        variants = package.get("variants") or []
        verified = [item["id"] for item in variants if int(item.get("verified") or 0) == 1]
        builds.add_selection(
            build_id,
            {
                "package_id": package["id"],
                "variant_ids": verified or [item["id"] for item in variants],
                "order_index": index,
            },
        )
        index += 1
    return build_id


def _measure(path: Path) -> dict:
    """用 pdfplumber 独立量：页数、最小正文字号、照片框。"""
    import pdfplumber

    out: dict = {"pages": 0, "min_font": None, "photo": None}
    with pdfplumber.open(str(path)) as pdf:
        out["pages"] = len(pdf.pages)
        sizes: list[float] = []
        for page in pdf.pages:
            for char in page.chars:
                if char.get("text", "").strip():
                    sizes.append(round(float(char["size"]), 2))
            if page.images and out["photo"] is None:
                img = page.images[0]
                mediabox = page.mediabox
                bottom = max(0.0, -float(mediabox[1]))
                out["photo"] = {
                    "w_pt": round(float(img["srcsize"][0]) and float(img["width"]), 2),
                    "h_pt": round(float(img["height"]), 2),
                    "x0_pt": round(float(img["x0"]), 2),
                    "top_offset_pt": round(float(img["top"]) + bottom, 2),
                    "right_gap_pt": round(float(mediabox[2]) - float(img["x1"]), 2),
                }
        out["min_font"] = min(sizes) if sizes else None
    return out


def main() -> int:
    profile = ProfileRepo().get()
    packages = _pick_packages()
    template = _pick_template()
    position = "数据分析实习生"
    print(f"档案：{profile.get('name_zh')} / {profile.get('school_zh')}")
    print(f"packages：{len(packages)} 条")
    print(f"template：{template['id']}  {template.get('name')}（{template.get('lang')}）")

    report: dict = {}
    for lang in ("zh", "en"):
        build_id = _build(lang, packages, template, position)
        result = export_service.export(build_id, fmt="pdf", overwrite=False)
        artifact = result["artifact"]
        path = db_mod.get_paths().exports / artifact["filename"]
        measured = _measure(path)
        print(f"\n== {lang} ==")
        print(f"build_id      : {build_id}")
        print(f"PDF           : {path}")
        print(f"文件名        : {artifact['filename']}")
        print(
            f"版式          : 正文 {result['layout']['body_pt']}pt / 行距 {result['layout']['leading']} / "
            f"可用高 {result['layout']['available_height_pt']}pt / 版心宽 {result['layout']['text_width_pt']}pt"
        )
        print(f"文本层校验    : text_verified={artifact['text_verified']}")
        print(f"pdfplumber 量 : {json.dumps(measured, ensure_ascii=False)}")
        if result["warnings"]:
            print("warnings      : " + json.dumps(result["warnings"], ensure_ascii=False)[:600])
        report[lang] = {
            "build_id": build_id,
            "path": str(path.relative_to(db_mod.get_paths().root.parent)),
            "filename": artifact["filename"],
            "body_pt": result["layout"]["body_pt"],
            "measured": measured,
            "warnings": [item["code"] for item in result["warnings"]],
        }

    out = db_mod.get_paths().root / "exports" / "first_pdf_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
