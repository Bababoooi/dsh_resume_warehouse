"""C3 的本地匹配对照：同一次运行里既要有「确实没有」的反向，也要有「确实命中」的正向。

为什么必须是**同一次运行的两个方向**：只断言「熟悉 Rust 后端开发 → missing」会有假绿风险——
如果 `link_requirements()` 因为任何原因永远返回空（证据源没传进来、归一化写错、profile 字段名
改了），这条断言照样通过，而用户看到的却是「我会 SQL 它也说没有」。反过来只断言「SQL 命中了」
也不行：把什么都不命中当成「保守」。

所以这里一对儿一起测：
* 反向：`熟悉 Rust 后端开发` → `matched_package_ids == []`、`matched_evidence == []`、`candidate_status == "missing"`；
* 正向：`熟练掌握 SQL、Python` → 命中且 `matched_evidence[0]["source"] == "skills_json"`。

两条都只调本地纯函数（`app.services.jd_analysis.link_requirements`），不连库、不起服务、不联网——
所以它属于 `noservice` 层，跑一次是毫秒级。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.noservice

# 一个「有货」的最小现场：档案里有 SQL/Python 技能行，仓库里有一个 A/B 测试项目。
PROFILE = {
    "name_zh": "张三",
    "school_zh": "示例大学",
    "degree": "本科",
    "major": "计算机科学与技术",
    "skills": [
        {"line": "数据分析类：掌握Python、R、SQL等编程语言，可独立进行数据清洗、统计分析与可视化处理", "category": "数据分析类"},
        {"line": "基础办公类：掌握Excel的数据透视表、VLOOKUP函数等常用工具", "category": "基础办公类"},
    ],
}

PACKAGES = [
    {
        "id": "pkg_ab_test",
        "title": "赛车类游戏版本AB测试对照数据分析",
        "org": "示例科技（杭州）有限公司",
        "role": "队长",
        "tech_stack": ["Python", "SQL"],
        "tags": ["AB测试", "数据分析"],
        "variants": [
            {
                "id": "var_1",
                "lang": "zh",
                "tone": "impact",
                "verified": 1,
                "text": "通过三版本 AB 测试对比分析，把核心指标的口径统一，输出可复用的分析报告。",
            }
        ],
    }
]


# 一个「不含 SQL/Python 字样」的仓库：用来证明 skills_json 这条路自己是通的，
# 而不是永远被 package 的 tech_stack 抢在前面（否则「skills_json 命中」这条断言是偶然）。
PACKAGES_WITHOUT_SKILL_TOKENS = [
    {
        "id": "pkg_site_selection",
        "title": "门店选址与订单预测模型",
        "org": "示例零售有限公司",
        "role": "队长",
        "tech_stack": ["R"],
        "tags": ["建模"],
        "variants": [{"id": "var_2", "lang": "zh", "tone": "impact", "verified": 1, "text": "对比 12 种回归模型后选定 Ridge 回归搭建订单预测模型。"}],
    }
]


def _link(skill: str, packages: list[dict] | None = None) -> dict:
    """只喂一条需求，返回它被本地匹配改写后的样子。"""
    from app.services import jd_analysis

    requirement = {"id": "req_x", "skill": skill, "candidate_status": "missing", "candidate_status_source": "llm"}
    warnings: list[dict] = []
    jd_analysis.link_requirements([requirement], PACKAGES if packages is None else packages, profile=PROFILE, warnings=warnings)
    return requirement


def test_skill_the_user_really_lacks_stays_missing():
    """反向：用户确实不会 Rust —— 必须稳定判 missing，且不许编造证据。"""
    requirement = _link("熟悉 Rust 后端开发")

    assert requirement["candidate_status"] == "missing", requirement
    assert requirement["matched_package_ids"] == [], requirement
    assert requirement.get("matched_evidence") == [], requirement


def test_skill_the_user_really_has_is_linked_with_quote():
    """正向对照：同一套现场、同一个函数，SQL/Python 必须命中且能引回技能行原文。

    没有这条，上面那条反向用例在「函数永远返回空」时也是绿的（假绿）。
    """
    requirement = _link("熟练掌握 SQL、Python", PACKAGES_WITHOUT_SKILL_TOKENS)

    assert requirement["candidate_status"] != "missing", requirement
    evidence = requirement.get("matched_evidence") or []
    assert evidence, requirement
    # 只靠技能行时没有「命中哪个经历包」——这时不该编造 package id，但证据必须给出
    assert evidence[0]["source"] == "skills_json", evidence
    assert requirement.get("matched_package_ids") == [], requirement
    # 引文必须真的能在来源里找到（≥8 字），否则 evidence 只是装饰
    assert len(evidence[0]["quote"]) >= 8, evidence
    assert "SQL" in evidence[0]["quote"].upper() or "Python" in evidence[0]["quote"], evidence


def test_skills_json_path_also_wins_when_package_has_no_such_tokens():
    """`skills_json` 这条证据源单独也要能命中：仓库里没有 SQL/Python 字样时，只能靠技能行。"""
    requirement = _link("熟练掌握 SQL、Python", PACKAGES_WITHOUT_SKILL_TOKENS)
    sources = {item["source"] for item in (requirement.get("matched_evidence") or [])}
    assert sources == {"skills_json"}, requirement


def test_both_directions_in_one_go_and_result_is_not_hardcoded():
    """两条需求一起跑：一条空、一条命中——证明结果跟着**内容**走，不是跟着调用次数走。"""
    from app.services import jd_analysis

    requirements = [
        {"id": "req_lack", "skill": "熟悉 Rust 后端开发", "candidate_status": "missing", "candidate_status_source": "llm"},
        {"id": "req_have", "skill": "熟练掌握 SQL、Python", "candidate_status": "missing", "candidate_status_source": "llm"},
    ]
    jd_analysis.link_requirements(requirements, PACKAGES, profile=PROFILE, warnings=[])
    lack, have = requirements

    assert lack["candidate_status"] == "missing" and lack["matched_package_ids"] == []
    assert have["candidate_status"] != "missing" and have["matched_package_ids"]
