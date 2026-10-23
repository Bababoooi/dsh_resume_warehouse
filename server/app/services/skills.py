"""职业技能的「展示层 / 索引层」分离（用户 2026-10-23 裁决）。

用户原话：「拆成 tag 我感觉会失去简历上的规整感，HR 看到一堆 tag 却不知道具体情况
会很莫名其妙吧。」因此：

* **展示层**：``line`` 是唯一渲染源，逐字保留简历原文，任何导出都直接印它；
  绝不出现 tag 块、标签云、「 | 」分隔的技能标签。
* **索引层**：``tokens`` 只给 JD 匹配用，允许随时重建；删空后匹配降级为
  「整句子串匹配」，不得报错、不得丢行。
* **别名表**（``SKILL_ALIASES``）只参与匹配归一，不参与渲染。

数据结构（存 ``UserProfile.skills_json`` / ``ImportJob.draft_json``）::

    {"line": "数据分析类：掌握Python、R、SQL等编程语言…",
     "category": "数据分析类",
     "tokens": ["python", "r", "sql", "数据清洗", "统计分析", "可视化"],
     "order": 10}
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence

#: 匹配别名表 —— 只做归一，**不参与渲染**。key 为归一后的 token，value 为别名集合。
SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "python": ("python", "py"),
    "r": ("r", "r语言"),
    "sql": ("sql", "mysql", "postgres", "postgresql", "sqlite", "hive sql"),
    "excel": ("excel", "vlookup", "数据透视表", "pivot table", "表格函数"),
    "clustering": ("k-means", "kmeans", "k-means++", "聚类", "clustering"),
    "regression": ("ridge", "lasso", "回归", "regression", "线性回归"),
    "statistics": ("统计学", "统计分析", "假设检验", "ab测试", "ab test", "显著性检验"),
    "visualization": ("可视化", "tableau", "power bi", "powerbi", "matplotlib", "echarts"),
    "pandas": ("pandas", "numpy", "scipy"),
    "ml": ("机器学习", "machine learning", "sklearn", "scikit-learn"),
    "llm": ("llm", "大模型", "ai agent", "agent", "prompt"),
    "spark": ("spark", "hadoop", "大数据"),
    "java": ("java", "spring"),
    "golang": ("golang", "go语言"),
    "flask": ("flask",),
    "word": ("word", "文档排版"),
    "ppt": ("ppt", "powerpoint", "演示文稿"),
    # 中文能力词（只在索引层出现，不参与渲染）
    "data_cleaning": ("数据清洗",),
    "data_mining": ("数据挖掘",),
    "data_analysis": ("数据分析", "数据处理"),
    "modeling": ("建模", "模型搭建"),
    "deep_learning": ("深度学习",),
    "crawler": ("数据采集", "爬虫"),
    "automation": ("自动化",),
    "reporting": ("分析报告", "文档撰写"),
}

_CATEGORY_RE = re.compile(r"^\s*([^：:]{1,20})[：:]\s*(.+)$")


def normalize(text: str) -> str:
    """NFKC + 小写 + 去空白，只用于匹配，不改写原文。"""
    return unicodedata.normalize("NFKC", text or "").strip().lower().replace(" ", "")


def split_category(line: str) -> tuple[str | None, str]:
    """``数据分析类：掌握Python…`` → (``数据分析类``, ``掌握Python…``)。"""
    match = _CATEGORY_RE.match(line or "")
    if not match:
        return None, (line or "").strip()
    return match.group(1).strip(), match.group(2).strip()


_ASCII_ALIAS_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _alias_hit(alias: str, normalized_text: str) -> bool:
    """别名命中判定。

    纯英文别名必须命中**词边界**，否则 ``r`` 会在 ``for`` / ``design`` 里乱命中，
    ``sql`` 会在 ``mysqldump`` 里命中。中文别名直接子串匹配。
    """
    needle = normalize(alias)
    if not needle:
        return False
    if not needle.isascii():
        return needle in normalized_text
    pattern = _ASCII_ALIAS_RE_CACHE.get(needle)
    if pattern is None:
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])")
        _ASCII_ALIAS_RE_CACHE[needle] = pattern
    return pattern.search(normalized_text) is not None


def derive_tokens(line: str) -> list[str]:
    """从整句原文派生匹配用 tokens（确定性、可重建、绝不渲染）。

    只输出别名表里的**规范 token**：不把原文碎片塞进索引层，否则 ``tokens`` 会变成
    半个 tag 列表，把「展示层保持整句」的裁决偷偷破坏掉。
    """
    normalized_line = normalize(line)
    tokens: list[str] = []
    hits: list[tuple[int, str]] = []
    for canonical, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            if _alias_hit(alias, normalized_line):
                hits.append((-len(normalize(alias)), canonical))
                break
    # 长别名优先命中（避免 "r" 抢 "ridge"、"sql" 抢 "mysql"）
    for _, canonical in sorted(hits):
        if canonical not in tokens:
            tokens.append(canonical)
    return tokens


def build_skill_rows(lines: Sequence[str], *, start_order: int = 10, step: int = 10) -> list[dict[str, Any]]:
    """技能行 → ``skills_json`` 结构。空行跳过，但**一行都不丢**。"""
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(lines):
        line = (raw or "").strip()
        if not line:
            continue
        category, _ = split_category(line)
        rows.append(
            {
                "line": line,
                "category": category,
                "tokens": derive_tokens(line),
                "order": start_order + index * step,
            }
        )
    return rows


def row_match_score(row: Mapping[str, Any], required_tokens: Iterable[str]) -> float:
    """一行技能与 JD 要求 token 的重合度（0–1）。

    ``tokens`` 被删空时降级为整句子串匹配：只要 JD token 出现在 ``line`` 里就算命中，
    不报错、不丢行。
    """
    wanted = {normalize(token) for token in required_tokens if normalize(token)}
    if not wanted:
        return 0.0
    row_tokens = {normalize(token) for token in (row.get("tokens") or []) if normalize(token)}
    if row_tokens:
        return len(wanted & row_tokens) / len(wanted)
    line_key = normalize(str(row.get("line") or ""))
    if not line_key:
        return 0.0
    return sum(1 for token in wanted if token in line_key) / len(wanted)


def rank_rows(rows: Sequence[Mapping[str, Any]], required_tokens: Iterable[str]) -> list[dict[str, Any]]:
    """按相关度排序技能行（默认保持原序；此函数只在调用方显式要求时使用）。"""
    scored = [
        {**row, "match_score": round(row_match_score(row, required_tokens), 3)}
        for row in rows
    ]
    return sorted(scored, key=lambda item: (-item["match_score"], item.get("order") or 0))
