"""AC harness —— 证据可回溯：AC-ANL-16 / 17 / 18（§6.2.4 §6.2.5，I21–I23）。

这三条不测「分析有没有跑」，测的是**用户能不能核对**：

* 16：每条判定都能点回原文（三源之一 + ≥8 字引文逐字可查）；
* 17：「没匹配到」只有一种含义——两个数组都空，别让技能栏命中被误判成缺失；
* 18：人工改判压过重算，撤销必须显式。

为什么值得单独写：JD 分析最容易「看起来有结论、实际不可核对」。模型说「你不满足
A/B 测试」而用户仓库里就有一个 A/B 测试项目，属于把人判低的一类错误，必须有护栏。
"""

from __future__ import annotations

import json

CHECKS: dict[str, callable] = {}


def check(ac: str):
    def register(fn):
        CHECKS[ac] = fn
        return fn

    return register


import pytest

from .helpers import restore_profile, snapshot_profile


@pytest.fixture(autouse=True)
def _restore_profile(flow):
    """本文件会改个人资料（加技能、加专业）。改完必须还原：

    `AC-SKILL-01` 拿 profile.skills 去比对「导出 PDF 里的技能行」，资料一旦被
    我们改掉，那条用例就会拿着新技能去旧 PDF 里找，红得毫无道理（顺序依赖）。
    """
    snapshot = snapshot_profile(flow["client"])
    yield
    restore_profile(flow["client"], snapshot)


SOURCES = {"package", "skills_json", "profile"}
STATUSES = {"satisfied", "partial", "missing"}

# 刻意让「技能栏」与「项目要点」都能命中：SQL/Python 只在技能行，A/B 测试只在项目里。
JD_TEXT = """岗位：数据分析实习生

岗位职责：
1. 负责业务数据的日常分析与报表产出；
2. 参与增长实验设计，归纳实验结论。

任职要求：
1. 熟练掌握 SQL、Python，能独立完成数据清洗与分析；
2. 有 A/B 测试经验，理解显著性检验；
3. 熟悉 Tableau 可视化。
"""


def _setup(flow) -> dict:
    """造一个「有技能、有项目、有 JD」的最小现场，返回可复用的 id。"""
    client = flow["client"]

    profile = client.put(
        "/api/v1/profile",
        json={
            "name_zh": "张三",
            "school_zh": "示例大学",
            "degree": "本科",
            "major": "统计学",
            "grad_year": 2028,
            "skills": [
                {"line": "数据分析类：掌握Python、SQL等编程语言，可独立进行数据清洗与可视化处理"},
                {"line": "基础办公类：Excel 数据透视表、VLOOKUP"},
            ],
        },
    )
    assert profile.status_code == 200, profile.get_data(as_text=True)

    package = client.post(
        "/api/v1/packages",
        json={
            "title": "游戏版本 A/B 测试分析",
            "kind": "project",
            "role": "数据分析",
            "status": "ready",
            "variants": [
                {
                    "bullet_key": "ab",
                    "tone": "impact",
                    "lang": "zh",
                    "text": "独立完成 A/B 测试设计与显著性检验，实验组留存提升 3.9%，p=0.018。",
                    "verified": True,
                }
            ],
        },
    )
    assert package.status_code == 201, package.get_data(as_text=True)
    package_id = package.get_json()["data"]["id"]

    jd = client.post("/api/v1/jds", json={"title": "数据分析实习生", "company_name": "示例科技", "raw_text": JD_TEXT})
    assert jd.status_code == 201, jd.get_data(as_text=True)
    jd_id = jd.get_json()["data"]["id"]

    detail = _analyze_and_wait(flow, jd_id)
    requirements = detail["data"].get("requirements") or []
    assert requirements, "启发式分析一条 requirement 都没产出"

    return {"package_id": package_id, "jd_id": jd_id, "requirements": requirements}


def _analyze_and_wait(flow, jd_id: str) -> dict:
    """分析是异步的（202 + job_id）：等到 job 结束再读，否则读到的是空表。"""
    from .helpers import wait_job

    client = flow["client"]
    started = client.post(f"/api/v1/jds/{jd_id}/analyze", json={"method": "heuristic"})
    assert started.status_code in (200, 202), started.get_data(as_text=True)
    body = started.get_json()["data"]
    if body.get("job_id"):
        wait_job(client, body["job_id"])
    detail = client.get(f"/api/v1/jds/{jd_id}?include=requirements")
    assert detail.status_code == 200, detail.get_data(as_text=True)
    return detail.get_json()


def _corpora(flow) -> tuple[dict[str, str], list[str]]:
    """来源原文：包 → 全部变体正文；技能行 → 原文。校验引文时逐字比对。"""
    client = flow["client"]
    packages = client.get("/api/v1/packages?limit=100&include_variants=1").get_json()["data"]["items"]
    corpus = {}
    for item in packages:
        texts = [str(v.get("text") or "") for v in item.get("variants") or []]
        corpus[item["id"]] = "\n".join(texts + [str(item.get("title") or ""), str(item.get("summary") or "")])
    skills = [str(row.get("line") or "") for row in (client.get("/api/v1/profile").get_json()["data"].get("skills") or [])]
    return corpus, skills


def validate_evidence(requirement: dict, corpus: dict[str, str], skills: list[str], profile: dict) -> list[str]:
    """AC-ANL-16 的校验器本体（也与反向用例共用）。

    返回问题列表；空列表 = 该条判定可回溯。
    """
    problems: list[str] = []
    for item in requirement.get("matched_evidence") or []:
        source = item.get("source")
        quote = str(item.get("quote") or "")
        ref_id = item.get("ref_id")
        if source not in SOURCES:
            problems.append(f"未知来源 {source!r}")
            continue
        if source == "package":
            if not ref_id:
                problems.append("source=package 但 ref_id 为空")
                continue
            blob = corpus.get(str(ref_id))
            if blob is None:
                problems.append(f"ref_id {ref_id} 不是库里已核实的经历包")
                continue
        else:
            if ref_id is not None:
                problems.append(f"source={source} 的 ref_id 必须是 null，实际 {ref_id!r}")
            blob = "\n".join(skills) if source == "skills_json" else "\n".join(
                str(profile.get(key) or "") for key in ("degree", "major")
            )
        if len(quote) < 8:
            problems.append(f"引文太短（{len(quote)} 字）：{quote!r}")
        elif quote not in blob:
            problems.append(f"引文在来源里找不到：{quote!r}")
    return problems


@check("AC-ANL-16")
def test_ac_anl_16_matched_evidence_is_traceable(flow):
    ctx = _setup(flow)
    corpus, skills = _corpora(flow)
    profile = flow["client"].get("/api/v1/profile").get_json()["data"]

    with_evidence = [req for req in ctx["requirements"] if req.get("matched_evidence")]
    assert with_evidence, "没有任何 requirement 带 matched_evidence，用户无从核对"

    for requirement in ctx["requirements"]:
        problems = validate_evidence(requirement, corpus, skills, profile)
        assert not problems, f"「{requirement.get('skill')}」证据不可回溯：{problems}"

    # 反向：把引文改一个字，校验器必须判 FAIL —— 证明上面的「全过」不是因为校验器不干活。
    polluted = json.loads(json.dumps(with_evidence[0]))
    polluted["matched_evidence"][0]["quote"] = "这句话在来源里根本不存在，长度也够。"
    assert validate_evidence(polluted, corpus, skills, profile), "引文被改写却仍判通过：校验器是空的"


@check("AC-ANL-17")
def test_ac_anl_17_missing_only_when_both_arrays_empty(flow):
    ctx = _setup(flow)
    for requirement in ctx["requirements"]:
        evidence = requirement.get("matched_evidence") or []
        package_ids = requirement.get("matched_package_ids") or []
        status = requirement.get("candidate_status")
        assert status in STATUSES, f"candidate_status 非法：{status!r}"

        if status == "missing":
            assert not evidence, f"「{requirement.get('skill')}」判为缺失却带着证据：{evidence}"
            assert not package_ids, f"「{requirement.get('skill')}」判为缺失却带着包 id：{package_ids}"
        else:
            assert evidence or package_ids, f"「{requirement.get('skill')}」非缺失状态却没有任何证据"

        # 两处不许打架：matched_package_ids 里每个 id 都要有 package 源的对应项。
        package_refs = {str(item.get("ref_id")) for item in evidence if item.get("source") == "package"}
        assert set(map(str, package_ids)) <= package_refs, (
            f"「{requirement.get('skill')}」的 matched_package_ids 与 matched_evidence 不一致："
            f"{package_ids} vs {package_refs}"
        )

    # 技能栏命中必须有对应项：SQL/Python 只出现在 skills_json，包里没有。
    skill_hits = [
        req
        for req in ctx["requirements"]
        if any(item.get("source") == "skills_json" for item in (req.get("matched_evidence") or []))
    ]
    assert skill_hits, "技能栏里的 SQL/Python 没有被当成证据（又退化成「你没这技能」）"
    for requirement in skill_hits:
        assert requirement.get("candidate_status") != "missing"


@check("AC-ANL-18")
def test_ac_anl_18_manual_override_survives_recompute(flow):
    ctx = _setup(flow)
    client = flow["client"]
    target = ctx["requirements"][0]
    requirement_id = target["id"]

    patched = client.patch(f"/api/v1/requirements/{requirement_id}", json={"candidate_status": "satisfied"})
    assert patched.status_code == 200, patched.get_data(as_text=True)
    assert patched.get_json()["data"]["candidate_status_source"] == "manual"

    # 重算也是异步的：不等它跑完就去读，读到的是旧行、旧 id，后面 PATCH 必然 404。
    after = _analyze_and_wait(flow, ctx["jd_id"])["data"]["requirements"]
    kept = [row for row in after if row["skill"] == target["skill"] and row["category"] == target["category"]]
    assert kept, "重算后这条 requirement 消失了"
    assert kept[0]["candidate_status"] == "satisfied", "重算把人工改判覆盖掉了（用户白改）"
    assert kept[0]["candidate_status_source"] == "manual"

    # 撤销：显式给 auto，下一次重算才会接管。
    # 注意 id 会在重算时换新（DELETE+INSERT 保持「一派生一主表」的简单性），
    # 所以这里必须用重算后那一行的 id，而不是最初记下的那个。
    requirement_id = kept[0]["id"]
    revoked = client.patch(f"/api/v1/requirements/{requirement_id}", json={"candidate_status_source": "auto"})
    assert revoked.status_code == 200, revoked.get_data(as_text=True)
    assert revoked.get_json()["data"]["candidate_status_source"] != "manual"

    final = _analyze_and_wait(flow, ctx["jd_id"])["data"]["requirements"]
    row = [r for r in final if r["skill"] == target["skill"] and r["category"] == target["category"]][0]
    assert row["candidate_status_source"] != "manual", "撤销之后重算仍被人工值压着"


if __name__ == "__main__":  # 手跑：python -m tests.acceptance.test_ac_anl_evidence
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
