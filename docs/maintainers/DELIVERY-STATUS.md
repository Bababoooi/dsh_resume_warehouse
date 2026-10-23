# 交付状态与已知问题

> 生成时点：2026-10-23 09:2x（Asia/Shanghai）
> 判据口径：本文所有数字都是**本机实跑**得到的，并附命令或来源；标「待验」的项没有实测证据，不作为结论。

## 1. 一句话状态

五步旅程全链路跑通（对话打包 → 导入拆解 → JD 分析 → 组装 → PDF 导出），**质量门的一条命令验收脚本现在 6 段全绿（rc=0）**。但团队仍处于 `escalated`：前两轮复核判「需要修改」后自动流程已停，**第 4 轮评审需要你明确授权才能开启**——这不是停工，是「没有一次通过的复核」这件事要你裁决。

## 2. 已实测通过的部分

| 项 | 实测值 | 怎么取的 |
|---|---|---|
| 七个页面可渲染 | workbench 276 / warehouse 3238 / templates 251 / jobs 128 / builds 294 / profile 502 / settings 446 字符；CSP 违规 0、网络错误 0、异常 0、内联脚本 0 | `scripts/check_pages_headless.py`（CDP + 真实等待） |
| **质量门 §A.1** | **6 段 PASS / FAIL 0 / rc=0**（我一次、supervisor 一次，两次独立）；含两条负向自检：塞 `before==after` 的假报告必须红、去掉运行账必须红 | `tmp/accept_t16.py`（从清单 §A.1 抽，按结构特征抽取） |
| **用户路径端到端** | 建 build(201) → 选 4 包/8 变体(200, count=4) → assemble(4 sections, est_pages=1, warnings `PACKAGE_MISSING`+`SOURCE_CONFLICT`) → export(202 job) → `succeeded` → PDF 197854B | 全走 HTTP，不碰脚本捷径 |
| 中文 PDF | 1 页、正文中位 **11.0pt**、照片 **89.28×89.28pt**、距顶 **3.82**、距右 **9.13**、横向越界 0 | `scripts/eval/check_export_pdf.py` → `verdict=PASS, failed=0` |
| PDF 内容真实性 | `GPA 3.56/4`、`86.53/100`、`CET4：562`、`CET6:508`、主修课程、实习 3 条、项目 3 条、技能 3 行全在；`【示例】` **0 次**（演示包已清） | pdfplumber 文本层，9 探针 8 命中 + 第 9 条「应当不存在」成立 |
| 英文 PDF | 独立版式（`SAN ZHANG` / `Education` / `Sep 2024 – Jun 2028`），chrome 区 CJK = **0**；正文中文由 37/38 行降到 **11/29 行**（优先用已有英文变体） | `scripts/eval/check_lang_export.py --lang en` |
| 经历库页面 | 顶部计数 **经历 5 / 表述变体 22 / 待核实 0 / 可复用 5**，「这条还没有要点」文案出现 **0** 次（此前因接口写死 `include_variants=False` 显示「0 条要点」） | CDP dump-dom + 真库比对 |
| 归档 ≠ 删除 | 归档后默认列表 12→11、`?include_archived=1` 仍 12、恢复后回 12；强删需 `?hard=1&confirm=<id>`，错 id → 422 `CONFIRM_MISMATCH` | 活实例 curl（可逆操作，做完即恢复） |
| 隐私 | 姓名/电话/邮箱/照片字节与哈希不进 payload；校名真实发送且用于院校判断 | `check_egress.py` + 真库 payload 抽查 |
| 自动化 | `pytest tests` **249 passed / 3 skipped**（42.43s，我自己跑）；路由对账 `code 100 / matched 100 / only_in_code 0 / only_in_docs 13` | 逐条实跑 |
| 验收账本 | 条款 **157** 条、唯一 157、撞号 0；已执行 154 / MANUAL **3**（`AC-LOC-07`、`AC-PDF-20`、`AC-JD-05`） | `tests/acceptance/make_index.py --check` → 通过 |

## 3. 已知问题（按用户可见度排序）

| 编号 | 问题 | 现状 |
|---|---|---|
| **英文正文仍混中文** | en 变体共 11 条，中文要点 120 条 | 缺的部分**诚实回退**并逐条列在 `LANG_FALLBACK.entries[]`，正文中文 11/29 行。补齐需生成新变体（**涉及花费，等你点头**） |
| **22 个无主 PDF** | `data/exports/` 里 22 个 PDF 已无产物记录（历史清理所致，DB 无悬空行） | 脚本只列不删；清理属不可逆操作，**等你点头** |
| **已发生的不可逆删除** | `resume_build` 43→12（删 31 行）、产物行删 29、选题行删 139 | 快照 `data/runtime/app.db.pre_prune_builds_20261023-075651`；根因是我下了 schema 上做不到的「只软归档」指令（见 §6.5） |
| ~~F-07~~ | 4 条界面验收曾是人工 | **已闭环**：`tests/acceptance/NEGATIVE_EVIDENCE.md`（5867B）四条产品侧变异 + 备份/还原/md5，C1b 现 PASS |
| ~~F-09~~ | 匹配证据源漏技能栏 | **已闭环**：`熟练掌握 SQL、Python` 现引回「数据分析类：掌握Python、R、SQL…」原文，`source=skills_json` |
| ~~门脚本跑不到底~~ | 曾崩在 `no such column: text` | **已修**：列名改 `skill`、六段独立 try/except、新增两条负向自检 |
| ~~构造报告~~ | `relink_report_ebu_demo_*.json` 是手改库副本跑出来的 | **已删**并治本：help 写明禁手改、`command` 取 `sys.argv`、改用单测 `tests/test_recompute_links.py` 证明检测器有效 |
| **F-08 残留** | 岗位分析页可能仍显示旧结论 | 重算已跑：6 条里 2 条补上证据（`matched_evidence` 0→2），其余 4 条经查是真没证据（尤其无 Rust） |

## 4. 需要你决定的事

1. **质量门**：`再开一轮`（门已全绿，跑一次就出正式结论；范围焊死在 C4 + `AC-ANL-17b` 一个附加项）或 `带已知问题收口`（把 §3 未闭环项写成 KNOWN-FAIL 交付）。
2. **数据口径**：GPA 中文 `3.56/4` / 英文 `3.57/4.0`；到岗时间中文 `2027年1月下旬` / 英文 `Early July 2026`（差 5 个月）。系统现**各取各值并标 `SOURCE_CONFLICT`**，不擅自合并。哪份为准，或维持各语言各用各的？
3. **DSH 技能入库**：`resume-warehouse` 已在技能库**待确认队列**（设置 → 技能 → 确认采纳后，说「把这段经历存进简历库」即可触发）。
4. **22 个无主 PDF 是否清理**。

## 5. 怎么用

```bash
bash skills/resume-warehouse/start.sh     # 启动（端口自动顺延，读 data/runtime/app_port）
bash skills/resume-warehouse/stop.sh      # 停止
```

打开终端里打印的 `http://127.0.0.1:<port>`，五步：工作台讲经历 → 模板导入现有简历 → 目标职位粘 JD → 组装导出选经历/语言 → 下载 PDF。

文件命名固定 `岗位-姓名-学校.pdf`，缺变量会直接报错，不会生成残缺文件名。

快速自检：`pytest -m noservice -q`（1 秒级）；全量：`pytest tests -q`（约 42 秒）；门：按清单 §A.1 抽取后 `python tmp/accept_t16.py`。

## 6. 这次踩到的最有价值的六个坑

1. **CSP 拦掉内联启动脚本** → 七个页面全白，而所有接口 200、测试全绿。教训：验收必须有一条判「浏览器里页面能不能显示」。
2. **迁移被静默跳过** → 真库停在旧 schema，新字段写入全被 CHECK 拒绝，错误被上层吞掉。
3. **合规的重算可以是空转** → 零出网、有快照、before→after 都打印，仍五条结论一条没变，因为证据源是空的。只核「已变化项」会把空转当收敛。
4. **日期正则允许零位数字** → 编号里含四位数字的条目，整行被吞、标题公司时间全空（不是测试抖动，是导入静默丢内容）。
5. **指令与环境冲突时不得静默降级** → 我要求「只软归档」，而表里没有归档列；执行方自行改成硬删 31 行。正确动作是停下回报 + 两种方案 + 各自代价。
6. **判据要什么，就会有人造什么** → 一份「多出一条变化」的重算报告，输入库是手改副本；报告格式完全合法、脚本真实输出。教训：判据自己必须会咬人（负向自检），并禁止手工编辑结果。
