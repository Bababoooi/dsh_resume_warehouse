#!/usr/bin/env python3
"""生成 `tests/acceptance/AC_INDEX.md`：逐条列出哪些验收条款被 harness 覆盖。

用法（仓库根目录）：

    .venv/bin/python tests/acceptance/make_index.py            # 写账本
    .venv/bin/python tests/acceptance/make_index.py --check     # 只校验，不写

两个判据来源：
* `docs/ACCEPTANCE.md` —— 条款清单（唯一真源，优先级也取自它）；
* `tests/acceptance/` —— `@check("AC-…")` 实际执行的函数，`manual.py` 里
  声明「只能人工验」的条目（必须写清原因）。

为什么有这个 `--check`：账本曾经因为正则不认 `| **AC-…** |` 这种加粗行，
分母少算 27 条最新 P0，覆盖率被高报成 93%（真实 76%）。人不会发现，机器能。
所以生成的账本现在自带一道自校验：分母必须等于文档里的唯一 AC 数、每条都必须
有状态，否则非零退出并打印差值。
"""

from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "ACCEPTANCE.md"
HARNESS = ROOT / "tests" / "acceptance"

AC_RE = re.compile(r"AC-[A-Z]+-[0-9]+")
# 三种写法都认（M9）：`| AC-… |`、`| **AC-…** |`、`` | `AC-…` | ``。
# 只认第一种曾让 27 条最新 P0 凭空消失；只做去重又会把「撞号」藏成「重复行」。
ROW_RE = re.compile(r"^\|\s*(?:\*\*)?\s*`?(AC-[A-Z]+-[0-9]+)`?\s*(?:\*\*)?\s*\|")
CLAUSE_END_RE = re.compile(r"^##\s*14\.?\s|^##\s*14\s")
CHECK_RE = re.compile(r'^@check\("(AC-[A-Z]+-[0-9]+)"\)')
DEF_RE = re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\(")
MANUAL_RE = re.compile(r'^\s*"(AC-[A-Z]+-[0-9]+)"\s*:\s*"([^"]+)"', re.M)


def clause_rows() -> list[tuple[int, str, str]]:
    """[(行号, ac_id, 优先级)] —— 只取条款区（§14 执行记录模板之前）。

    §14 里那张「执行记录模板」表格也以 ``| AC-… |`` 开头，但那是状态示例，
    不是条款：算进分母会让分母虚高（152 就是这么来的）。
    """
    rows: list[tuple[int, str, str]] = []
    for number, line in enumerate(DOC.read_text(encoding="utf-8").splitlines(), start=1):
        if CLAUSE_END_RE.match(line):
            break
        stripped = line.strip()
        match = ROW_RE.match(stripped)
        if not match:
            continue
        cells = [cell.strip().strip("*").strip("`") for cell in stripped.strip("|").split("|")]
        priority = cells[1] if len(cells) > 1 else ""
        if not re.fullmatch(r"P[0-2]", priority):
            continue  # 分隔行/表头/无优先级的引用行
        rows.append((number, match.group(1), priority))
    return rows


def collisions(rows: list[tuple[int, str, str]]) -> dict[str, list[tuple[int, str]]]:
    """同一 AC ID 落了两个**不同优先级** ⇒ 撞号（不是重复行）。"""
    seen: dict[str, list[tuple[int, str]]] = {}
    for number, ac, priority in rows:
        seen.setdefault(ac, []).append((number, priority))
    return {
        ac: hits
        for ac, hits in seen.items()
        if len({priority for _n, priority in hits}) > 1
    }


def documented() -> list[tuple[str, str]]:
    """[(ac_id, 优先级)]，按文档顺序、按 ID 去重（撞号由 --check 报错）。"""
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for _number, ac, priority in clause_rows():
        if ac in seen:
            continue
        rows.append((ac, priority))
        seen.add(ac)
    return rows


def executed() -> dict[str, str]:
    """{AC: "文件::函数"}，按 @check 装饰器后面那行 def 取名。"""
    found: dict[str, str] = {}
    for path in sorted(HARNESS.glob("test_ac_*.py")):
        pending: str | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            match = CHECK_RE.match(line)
            if match:
                pending = match.group(1)
                continue
            if pending and DEF_RE.match(line):
                name = DEF_RE.match(line).group(1)
                found.setdefault(pending, f"{path.name}::{name}")
                pending = None
    return found


def manual() -> dict[str, str]:
    path = HARNESS / "manual.py"
    if not path.exists():
        return {}
    return {ac: reason for ac, reason in MANUAL_RE.findall(path.read_text(encoding="utf-8"))}


def group_of(ac: str) -> str:
    return ac.split("-")[1]


def build() -> tuple[list[str], dict[str, int], list[str]]:
    raw = clause_rows()
    rows = documented()
    done = executed()
    hand = manual()
    ids = {ac for ac, _ in rows}
    unknown = sorted((set(done) | set(hand)) - ids)
    both = sorted(set(done) & set(hand))

    groups: dict[str, list[str]] = {}
    for ac, _ in rows:
        groups.setdefault(group_of(ac), []).append(ac)

    lines = ["# AC 覆盖账本（自动生成，勿手改）", ""]
    lines += [
        f"- 条款总数（分母）：**{len(rows)}**",
        f"- 已执行（断言）：**{len([ac for ac in ids if ac in done])}**",
        f"- 人工验（MANUAL）：**{len([ac for ac in ids if ac in hand])}**",
        f"- 未覆盖：**{len([ac for ac in ids if ac not in done and ac not in hand])}**",
        "",
        "重新生成：`.venv/bin/python tests/acceptance/make_index.py`　自校验："
        "`.venv/bin/python tests/acceptance/make_index.py --check`",
        "",
        "## 按分组",
        "",
        "| 分组 | 条款 | 已执行 | MANUAL | 覆盖率 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name in sorted(groups):
        items = groups[name]
        hit = [ac for ac in items if ac in done]
        hand_hit = [ac for ac in items if ac in hand]
        lines.append(
            f"| {name} | {len(items)} | {len(hit)} | {len(hand_hit)} | "
            f"{len(hit) * 100 // len(items)}% |"
        )

    lines += ["", "## 逐条明细", "", "| AC ID | 优先级 | 状态 | 执行位置 / 原因 |", "| --- | --- | --- | --- |"]
    for ac, priority in rows:
        if ac in done:
            lines.append(f"| {ac} | {priority} | 已执行 | `{done[ac]}` |")
        elif ac in hand:
            lines.append(f"| {ac} | {priority} | MANUAL | {hand[ac]} |")
        else:
            lines.append(f"| {ac} | {priority} | **未覆盖** | — |")

    if unknown:
        lines += ["", "## harness 里有、文档里没有的编号", ""]
        lines += [f"- `{ac}`" for ac in unknown]
    if both:
        lines += ["", "## 既执行又标 MANUAL（矛盾，必须修）", ""]
        lines += [f"- `{ac}`" for ac in both]

    stats = {
        "total": len(rows),
        "executed": len([ac for ac in ids if ac in done]),
        "manual": len([ac for ac in ids if ac in hand]),
    }
    problems: list[str] = []
    for ac, hits in sorted(collisions(raw).items()):
        spots = "、".join(f"L{number}（{priority}）" for number, priority in hits)
        problems.append(f"撞号：{ac} 在条款区出现多次且优先级不同 —— {spots}")
    # 门①：分母必须等于条款行数（同 ID 复述两行也会让分母少算一条，必须报出来）
    if len(raw) != len(rows):
        repeats = sorted({ac for ac, n in collections.Counter(ac for _n, ac, _p in raw).items() if n > 1})
        problems.append(
            f"分母 {len(rows)} ≠ 条款行数 {len(raw)}：{len(repeats)} 个编号重复出现 —— {', '.join(repeats[:8])}"
        )
    # 门②：每条都必须落状态（已执行或 MANUAL），留空即失败
    uncovered = [ac for ac, _priority in rows if ac not in done and ac not in hand]
    if uncovered:
        problems.append(f"未覆盖 {len(uncovered)} 条：{', '.join(uncovered[:8])}")
    if unknown:
        problems.append(f"未知编号 {len(unknown)} 个：{', '.join(unknown)}")
    if both:
        problems.append(f"既执行又 MANUAL {len(both)} 个：{', '.join(both)}")
    return lines, stats, problems


def claims_from_index(path: Path) -> set[str]:
    """AC_INDEX.md 里被标成「已执行」的编号（落盘账本的自述）。"""
    if not path.exists():
        return set()
    claimed: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        for ac in re.findall(r"AC-[A-Z]+-[0-9]+", line):
            if "已执行" in line:
                claimed.add(ac)
    return claimed


def main(argv: list[str]) -> int:
    lines, stats, problems = build()
    check_only = "--check" in argv

    target = HARNESS / "AC_INDEX.md"
    text = "\n".join(lines) + "\n"
    if not check_only:
        target.write_text(text, encoding="utf-8")
    elif target.exists() and target.read_text(encoding="utf-8") != text:
        problems.append("AC_INDEX.md 与当前代码/文档不一致，请重新生成")

    missing = stats["total"] - stats["executed"] - stats["manual"]
    print(
        f"分母 {stats['total']} / 已执行 {stats['executed']} / MANUAL {stats['manual']} / 未覆盖 {missing}"
    )
    raw = clause_rows()
    print(f"条款区行数 {len(raw)}、撞号 {len(collisions(raw))} 处")
    if check_only:
        # 门③：落盘账本自称「已执行」的条目，必须真有 @check 支撑（防账本自说自话）
        claimed = claims_from_index(target)
        unbacked = sorted(claimed - set(executed()))
        if unbacked:
            problems.append(f"账本自称已执行但无 @check {len(unbacked)} 条：{', '.join(unbacked[:8])}")
        print(f"--check：{'通过' if not problems else '失败'}")
    else:
        print(f"写入 {target.relative_to(ROOT)}")
    for item in problems:
        print(f"  ✗ {item}", file=sys.stderr)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
