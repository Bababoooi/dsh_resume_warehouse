#!/usr/bin/env python3
"""导入拆解评分器（captain 自用验收工具，只读产出，不改任何文件）。

用法：
    python3 data/eval/check_import_draft.py [draft_json_path]
默认读 data/exports/import_draft_zh_v10.json。

判据全部以 data/eval/expected_zh_v10.json 为准（文件驱动，不硬编码条数/数字）：
  1) 结构   —— `sections_expected` 的 heading / entry_count / block_type / bound_package_kind
                + `entry.org` / `entry.date_range` 必须在该段内逐字出现
  2) 数字   —— `must_contain_numbers_verbatim` 逐串子串命中（禁止交给 LLM 打分）
  3) 字符   —— `must_survive_special_chars` 逐串命中（全角/下标/括号不被清洗）
  4) 退化   —— `forbidden_degradation` 是**描述文本**，先翻译成真实模式 ((cid:/U+FFFD) 再查
  5) bullet —— internship/project 条目应有 ≥1 条 bullet（软判据，只告警）

草稿结构兼容两种（真实产出是第一种）：
  A. 扁平 blocks：`{"blocks":[{block_type: header|section|entry|skills, parent_temp_id, heading,
     bound_package_kind, entry_count, entry:{org,date_range,bullets,...}}], "skills":[{line,tokens}]}`
  B. 嵌套：`{"sections":[{heading, entries:[...]}]}`

退出码：0 全过；1 存在 hard_fail；2 前置缺失（fixture/draft 不存在）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

FIXTURE = Path("data/eval/expected_zh_v10.json")
DEFAULT_DRAFT = Path("data/exports/import_draft_zh_v10.json")

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"

SECTION_TYPES = ("section", "skills")
ENTRY_TYPES = ("entry",)


# --------------------------------------------------------------------------- 基础工具
def load_json(path: Path):
    if not path.exists():
        print(f"{RED}前置缺失{RESET}: {path} 不存在（先跑导入）")
        raise SystemExit(2)
    return json.loads(path.read_text(encoding="utf-8"))


def walk_strings(node, out: list[str]) -> list[str]:
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            walk_strings(v, out)
    elif isinstance(node, list):
        for v in node:
            walk_strings(v, out)
    return out


def _sort_key(b):
    return b.get("order_index") if isinstance(b.get("order_index"), int) else 0


# --------------------------------------------------------------------------- 结构归一
class Section:
    __slots__ = ("heading", "block_type", "kind", "entry_count", "entries")

    def __init__(self, heading, block_type, kind, entry_count, entries):
        self.heading = heading
        self.block_type = block_type
        self.kind = kind
        self.entry_count = entry_count
        self.entries = entries

    @property
    def text(self) -> str:
        chunks: list[str] = []
        for e in self.entries:
            walk_strings(e, chunks)
        return "\n".join(chunks)

    @property
    def bullets(self) -> list[str]:
        out: list[str] = []
        for e in self.entries:
            if isinstance(e, dict):
                b = e.get("bullets")
                if isinstance(b, list):
                    out.extend(x for x in b if isinstance(x, str))
        return out


def _norm_entry_flat(block: dict) -> dict:
    entry = block.get("entry")
    if isinstance(entry, dict):
        return {"__flat__": True, **entry}
    return {"__flat__": True, "raw": block.get("preview_text") or ""}


def normalize_flat(blocks: list) -> list[Section]:
    secs_raw = [b for b in blocks if isinstance(b, dict) and b.get("block_type") in SECTION_TYPES]
    secs_raw.sort(key=_sort_key)
    out: list[Section] = []
    for s in secs_raw:
        kids = [b for b in blocks
                if isinstance(b, dict)
                and b.get("block_type") in ENTRY_TYPES
                and b.get("parent_temp_id") == s.get("temp_id")]
        kids.sort(key=_sort_key)
        out.append(Section(
            heading=(s.get("heading") or "").strip(),
            block_type=s.get("block_type"),
            kind=s.get("bound_package_kind"),
            entry_count=s.get("entry_count"),
            entries=[_norm_entry_flat(k) for k in kids],
        ))
    return out


def normalize_nested(sections: list) -> list[Section]:
    out: list[Section] = []
    for s in sections:
        if not isinstance(s, dict):
            out.append(Section("", None, None, None, []))
            continue
        heading = ""
        for k in ("heading", "title", "name"):
            v = s.get(k)
            if isinstance(v, str) and v.strip():
                heading = v.strip()
                break
        entries = s.get("entries") or s.get("items")
        if not isinstance(entries, list):
            one = s.get("entry")
            entries = [one] if isinstance(one, dict) else []
        out.append(Section(heading, s.get("block_type"), s.get("bound_package_kind"),
                           s.get("entry_count"), [e for e in entries if isinstance(e, dict)]))
    return out


def normalize(draft):
    if isinstance(draft, dict) and isinstance(draft.get("blocks"), list) \
            and any(isinstance(b, dict) and b.get("block_type") for b in draft["blocks"]):
        return normalize_flat(draft["blocks"]), "blocks(扁平)"
    if isinstance(draft, list):
        return normalize_nested(draft), "<顶层数组>"
    if isinstance(draft, dict):
        for key in ("sections", "blocks", "outline"):
            v = draft.get(key)
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return normalize_nested(v), key
        inner = draft.get("data")
        if isinstance(inner, (dict, list)):
            return normalize(inner)
    return [], "<未识别>"


# --------------------------------------------------------------------------- 判据
def derive_forbidden(descriptions) -> list[tuple[str, str]]:
    """把「不得出现 X」的描述翻译成可查的真实模式；空模式表示由结构判据覆盖。"""
    out: list[tuple[str, str]] = []
    for desc in descriptions:
        if "(cid:" in desc:
            out.append(("(cid: 字形缺失标记", "(cid:"))
        if "U+FFFD" in desc:
            out.append(("U+FFFD 替换字符", "\ufffd"))
        if "丢" in desc and ("行" in desc or "bullet" in desc):
            out.append(("丢行/丢 bullet", ""))
    return out


def main() -> int:
    fixture = load_json(FIXTURE)
    draft_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DRAFT
    draft = load_json(draft_path)

    nums = fixture["must_contain_numbers_verbatim"]
    chars = fixture["must_survive_special_chars"]

    # 基准自检：防止判据被改软（曾误留长度 1 的 "1"）
    problems = []
    if len(nums) != len(set(nums)):
        problems.append("数字判据存在重复条目")
    tiny = [s for s in nums + chars if len(s) <= 1]
    if tiny:
        problems.append(f"含长度<=1 的伪判据: {tiny}")
    if problems:
        print(f"{RED}✗ 基线自身失效{RESET}: {'; '.join(problems)}")
        print("  结果不可信 → 判 FAIL（归 captain/用户，不归实现方）")
        return 1

    haystack = "\n".join(walk_strings(draft, []))
    failures: list[str] = []
    warnings: list[str] = []

    print(f"{DIM}草稿: {draft_path}（{draft_path.stat().st_size} B）{RESET}")

    # ---- 1. 结构 ----
    sections, shape = normalize(draft)
    expected = fixture["sections_expected"]
    print(f"\n== 1. 结构（期望 {len(expected)} 段 / 实际 {len(sections)} 段，形态 {shape}）==")
    if not sections:
        keys = list(draft) if isinstance(draft, dict) else type(draft).__name__
        print(f"  {RED}✗ 找不到段落{RESET}（草稿顶层：{keys}）")
        failures.append("草稿中找不到 section/blocks 结构")
    else:
        if len(sections) != len(expected):
            failures.append(f"段落数 {len(sections)} != 期望 {len(expected)}")
        for i, exp in enumerate(expected):
            got = sections[i] if i < len(sections) else Section("", None, None, None, [])
            exp_h = (exp.get("heading") or "").strip()
            notes: list[str] = []
            if exp_h != got.heading:
                failures.append(f"section[{i}] 标题不匹配：期望 {exp_h!r} 实际 {got.heading!r}")
            exp_type = exp.get("block_type")
            if exp_type and got.block_type and got.block_type != exp_type:
                # 真实产出里「职业技能」是 block_type=skills，期望也是 skills；不一致才算错
                notes.append(f"block_type {got.block_type!r} != {exp_type!r}")
                failures.append(f"section[{i}] block_type {got.block_type!r} != {exp_type!r}")
            exp_kind = exp.get("bound_package_kind")
            if exp_kind and got.kind and got.kind != exp_kind:
                notes.append(f"bound_package_kind {got.kind!r} != {exp_kind!r}")
                failures.append(f"section[{i}] bound_package_kind {got.kind!r} != {exp_kind!r}")
            if "entry_count" in exp:
                n = len(got.entries)
                if n != exp["entry_count"]:
                    notes.append(f"entry_count {n} != {exp['entry_count']}")
                    failures.append(f"section[{i}] entry_count {n} != {exp['entry_count']}")
            sample = exp.get("entry") or {}
            sec_text = got.text
            for field in ("org", "date_range"):
                want = (sample.get(field) or "").strip()
                if want and want.replace(" ", "") not in sec_text.replace(" ", ""):
                    notes.append(f"{field} 未出现：{want!r}")
                    failures.append(f"section[{i}] 条目 {field} 缺失：{want!r}")
            mark = f"{GREEN}✓{RESET}" if not notes else f"{YELLOW}✗{RESET}"
            print(f"  {mark} [{i}] {got.heading or exp_h!r}"
                  + (f"  [{got.block_type}/{got.kind}, {len(got.entries)} 条]" if got.block_type else "")
                  + (f"  ← {'; '.join(notes)}" if notes else ""))

    # ---- 2. 数字 ----
    missing = [s for s in nums if s not in haystack]
    print(f"\n== 2. 数字保真（{len(nums)} 串，逐串子串命中）==")
    for s in missing:
        print(f"  {RED}✗ 缺失{RESET} {s!r}")
    print(f"  命中 {len(nums) - len(missing)}/{len(nums)}")
    if missing:
        failures.append(f"数字缺失 {len(missing)} 串: {missing}")

    # ---- 3. 特殊字符 ----
    lost = [s for s in chars if s not in haystack]
    print(f"\n== 3. 特殊字符存活（{len(chars)} 串）==")
    for s in lost:
        print(f"  {RED}✗ 丢失/被清洗{RESET} {s!r}")
    print(f"  存活 {len(chars) - len(lost)}/{len(chars)}")
    if lost:
        failures.append(f"特殊字符丢失 {len(lost)} 串: {lost}")

    # ---- 4. 退化痕迹 ----
    print("\n== 4. 禁止的退化痕迹 ==")
    for label, pattern in derive_forbidden(fixture["forbidden_degradation"]):
        if pattern == "":
            print(f"  {DIM}·{RESET} {label}（由结构/bullet 判据覆盖）")
            continue
        hit = pattern in haystack
        print(f"  {f'{RED}✗ 命中{RESET}' if hit else f'{GREEN}✓ 无{RESET}'} {label}")
        if hit:
            failures.append(f"出现退化痕迹 {label}")

    # ---- 5. bullet（软）----
    print("\n== 5. bullet 形态（软判据）==")
    total_b = 0
    for i, sec in enumerate(sections):
        if sec.kind in ("skills",) or sec.block_type == "skills":
            continue
        for j, entry in enumerate(sec.entries):
            b = entry.get("bullets") if isinstance(entry, dict) else None
            n = len(b) if isinstance(b, list) else 0
            total_b += n
            if n == 0 and sec.kind in ("internship", "project", "campus"):
                label = (entry.get("org") or entry.get("title") or "?") if isinstance(entry, dict) else "?"
                warnings.append(f"section[{i}].entry[{j}] 无 bullet（{label}）")
    print(f"  抓到 bullet 共 {total_b} 条")
    for w in warnings[:8]:
        print(f"  {YELLOW}!{RESET} {w}")
    if len(warnings) > 8:
        print(f"  {YELLOW}!{RESET} …另有 {len(warnings) - 8} 条同类")

    # ---- 附加：技能区索引层（不渲染）----
    skills = draft.get("skills") if isinstance(draft, dict) else None
    if isinstance(skills, list):
        with_tokens = sum(1 for s in skills if isinstance(s, dict) and s.get("tokens"))
        print(f"\n== 6. 技能索引层（附加）==")
        print(f"  skills {len(skills)} 行 / 带 tokens {with_tokens} 行"
              f"（line 是唯一渲染源，tokens 只给 matcher）")
        bad = [s for s in skills if isinstance(s, dict) and not s.get("line")]
        if bad:
            failures.append(f"{len(bad)} 行 skills 缺 line（会渲染成空行）")

    print("\n" + "=" * 64)
    if failures:
        print(f"{RED}结果: FAIL（hard_fail {len(failures)} 项）{RESET}")
        for f in failures:
            print(f"  - {f}")
        print("\n归属：数字/字符丢失、(cid: 残留、段落切错 → coder 的解析实现；"
              "基准被改坏 → captain/用户。")
        return 1
    print(f"{GREEN}结果: PASS{RESET}（结构 + 数字 + 字符 + 无退化痕迹 全过）")
    if warnings:
        print(f"{YELLOW}软告警 {len(warnings)} 项{RESET}（不阻断，但要确认这些条目真的没有 bullet）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
