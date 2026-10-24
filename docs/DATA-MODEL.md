# DATA-MODEL — 数据模型与关系

> **冻结 v1.18.1**（2026-10-23 09:3x）：`available_date` 标为**不参与渲染**、`available_note` 定为到岗时间唯一真源、新增 `extra_json.available_note_en` 与 `extra_json.conflict_resolution` 两列语义；教育段补充行真源仍是 `template_block.static_text`（**不得新增 `gpa`/`courses` 列**）。
> **冻结 v1.18**（2026-10-23）：`resume_build` 增 **`archived_at`**（归档 ≠ 删除）+ 「归档 vs 软删」对照表 + 不变量 **I24**（归档不删行，硬删须显式并留快照）/ **I25**（`build_selection`/`build_artifact` 不得悬空）。
> **冻结 v1.17**（2026-10-23）：`jd_requirement` 增 **`matched_evidence_json`**（证据全集，三源）与 **`candidate_status`/`candidate_status_source`** 四值枚举列；新增不变量 **I21**（证据可回溯）/ **I22**（「没匹配到」= 两数组皆空）/ **I23**（人工判断不被自动覆盖）。
> **冻结 v1.16**（2026-10-23）：新增 **§2.4 页眉与教育段渲染来源**（页眉四类白名单、`education_line` 禁止存在、教育段 `date` 只取 `date_range` 原文）。
> **冻结 v1.15**（2026-10-23）：新增 `user_profile.degree_en`/`major_en`（**独立列**，不并入 `profile_fields_source`，理由：双列先例 + 可空可测可反向断言）+ `import_job.source_lang`（zh/en/unknown，commit 创建变体的 `lang` 来源）；新增 **§2.3 语言维度**与不变量 **I18/I19/I20**。
> **冻结 v1.14**（2026-10-23）：新增 `user_profile.profile_fields_source`（回填可回溯）+ **§2.2 commit 回填与分层铁律**（不变量 **I15/I16/I17**：静态内容不得丢失 / 档案字段有则填无则 NULL / 渲染层与索引层不互推）+ **`name_en` 全大写且不互推**口径。
> **冻结 v1.13**（2026-10-23）：`ImportJob.result_template_id` 生命周期定版（**R-a** 写入后不可清空 / **R-b** 模板独立存活 / **R-c** 模板活着则来源行禁止归档，附清理脚本校验 SQL）+ 新增不变量 **I14 溯源不断链**。
> **冻结 v1.12**（2026-10-23）：`Package` 增 `source_import_job_id`（FK → `import_job.id`）与 `source_entry_temp_id`，唯一键支撑导入派生包幂等；新增不变量 **I12**（同 job 重复 commit 包数不增）与 **I13**（软删/恢复连带派生包）。
> **冻结 v1.11**（2026-10-23）：修复 `ResumeBuild` 表 `density` 行末尾 `||` 导致 `naming_overrides_json` 被吞并（已恢复独立成行）、`school_tier` 行多一格；表列自检见 API-CONTRACT §16.0 M3（mismatch **0**）。
> **冻结 v1.10**（2026-10-23）：`ResumeBuild` 增 **`density`**（`original`|`relaxed`，默认 `original`，ADR-21）。
> **冻结 v1.9**（2026-10-23）：① `UserProfile.school_tier` 补「未识别 ≠ 普通本科」语义（推断不出写 `其他` + `recognized=false`）；② 新增 **§2.2 `facts` 与 `bullets`**（教育段整段文字 vs 要点列表，渲染规则与空值处理不同）。
> **冻结 v1.4**（2026-10-23）。v1.4：`school_zh`/`school_en` 改为**允许上云**（用户 m00265），`auto_redact` 默认收敛为 `["name","phone","email"]`，不变量 I10 相应改写。
> **v1.3**（2026-10-23）。v1.3：`slot_key` 允许点号（`^[a-z][a-z0-9_.]{0,40}$`）；`required` 语义分层（1=缺值 422 中止 / 0=渲染占位 + warning）；其他 `(cid:N)` 复用 `CID_GLYPH_MISSING` 不新造码。

> 配套：`docs/ARCHITECTURE.md`（存储约定 §4）、`docs/API-CONTRACT.md`（这些实体的 JSON 形态与端点）。
> 本文是 `app/schema.sql` 的直接依据：**字段名、类型、可空性、约束以本文为准**。
> 冻结版本 **v1.2**（2026-10-23，并入 UserProfile / 命名模板变量集 / 真实回归素材约束）。
> v1.6 变更（2026-10-23，D-19）：`UserProfile` 新增 **`school_tier`** 一等列（原藏在 `extra_json`）；新增「**可上云的候选人档案段**」七项白名单（`school/school_tier/degree/major/grad_year/city/available_date`，为 `ALLOWED_SOURCES` 增 `"profile"` 的契约依据）。
> v1.5 变更（2026-10-23，用户裁决）：`UserProfile` 新增 **`skills_json`**（逐行原文为唯一渲染源 + `tokens` 为派生索引，§1.1，ADR-19）；`AppSetting` 增 `trim_courses=false`。
> v1.2 变更（按 captain 决断 ④⑤）：`UserProfile` 增 `photo_source` 与照片元信息、照片目录改为 `data/profile/`（PDF 默认**含**照片）；`ImportJob` 增 `extracted_photo_json`；`AppSetting` 增 `allow_web_fetch` / `photo_in_export` 并把 `auto_redact` 扩到姓名与学校；新增支撑表 `PublicFetchLog`（下行抓取审计）；不变量增 I10/I11；上云边界改为**宽路径 + 占位符脱敏**。

---

## 0. 通用约定

| 约定 | 规则 |
|---|---|
| 主键 | `id TEXT PRIMARY KEY`，UUIDv7 文本（时间有序，便于 `ORDER BY id`） |
| 时间 | `TEXT`，ISO-8601 带时区，如 `2026-10-23T02:41:00+08:00`；`*_at` 字段一律 UTC 存储、展示层转本地 |
| 布尔 | `INTEGER 0/1`，带 `CHECK (x IN (0,1))` |
| 列表 | `TEXT` JSON 数组（`'["Python","Go"]'`），列名后缀 `_json`；查询用 `json_each` |
| 枚举 | `TEXT` + `CHECK (x IN (...))`；**不允许**用魔术数字 |
| 软删除 | 只有 `package` 与 `template` 有 `deleted_at`（可回收）；其余物理删除 |
| 外键 | `PRAGMA foreign_keys=ON`；`ON DELETE` 显式声明（见各表） |
| 审计 | 所有表带 `created_at`、`updated_at`（触发器或 DAO 统一写） |

实体总览（13 业务 + 3 支撑）：

```
UserProfile(单例)        JobDescription ──< JDRequirement
                          └──< CompanyProfile（可独立存在，按 company 名去重）
Package ──< PackageBulletVariant
   └──< PackageAttachment（可选，证据文件）
Template ──< TemplateBlock ──< Slot
ResumeBuild ──< BuildSelection（选中的 package + 选中 variant 快照）
   ├── ResumeBuild.field_values_json（槽位填充值快照）
   └──< BuildArtifact（导出产物）
ImportJob ──> Template（commit 后产出）
Job（长任务） / LlmPreview / LlmCallLog / AppSetting / SchemaMigration（支撑表）
```

---

## 1. UserProfile（单例，本地库）

**为什么是单例**：个人信息是「简历头部与文件命名的唯一数据源」，不允许前端硬编码、不允许散落在每个 build 里。任何导出都必须从这里（或 build 的显式覆盖字段）取值。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | 固定值 `"me"` | 单例哨兵，插入时写死 |
| `name_zh` | TEXT | NOT NULL, len 1–40 | 中文姓名，如 `张三`；`{name}` 在 `lang=zh` 时取此值 |
| `name_en` | TEXT | NULL, len 0–80 | 英文姓名，如 `SAN ZHANG`；`lang=en` 时取此值；缺失则 `{name}` 解析失败 |
| `school_zh` | TEXT | NULL, len 0–80 | 如 `示例大学` |
| `school_en` | TEXT | NULL, len 0–120 | 如 `Example University` |
| `school_tier` | TEXT | CHECK IN (`C9`,`985`,`211`,`双一流`,`普通本科`,`海外`,`其他`), NULL | **院校层次，一等列**（原藏在 `extra_json`，v1.6 升格）。用户可手填；空则 LLM 依校名推断并告警 `SCHOOL_TIER_INFERRED`。供 `jd/analyze` 的 `competitiveness.school_tier` 直接取用 。**「未识别 ≠ 普通本科」**：推断不出时写 `其他` 并置 `recognized=false`（API-CONTRACT §6.1「未识别语义」），`competitiveness` 不得据此给出「层次偏低」结论|
| `degree` | TEXT | CHECK IN (`本科`,`硕士`,`博士`,`大专`,`其他`) | |
| `major` | TEXT | NULL, len 0–80 | 如 `管理科学（商业数据分析）` |
| `grad_year` | INTEGER | 1900–2100 或 NULL | 毕业年份 |
| `phone` | TEXT | NULL, `^\+?[0-9\- ]{7,20}$` | 存储原样；**导出为 DOCX/PDF 时不脱敏**（这是本人简历），但**永不进入 LLM payload** |
| `email` | TEXT | NULL, RFC 简化校验 | 同上 |
| `city` | TEXT | NULL | 现居/期望城市 |
| `degree_en` | TEXT | NULL 允许 | 英文学位，例 `B.M.` / `B.S.` / `M.S.`。**只进 en 版**；NULL ⇒ en 版省略该行 + `PROFILE_FIELD_MISSING`。**zh 版不得出现本列值**（见 §2.3） |
| `major_en` | TEXT | NULL 允许 | 英文专业，例 `Management Science (Business Data Analytics)`。规则同 `degree_en` |
| `available_date` | TEXT | NULL, `YYYY-MM` 或 `YYYY-MM-DD` | **不参与渲染**（历史列，保留以兼容旧数据与筛选）。到岗时间的渲染真源是 `available_note`，见下 |
| `available_note` | TEXT | NULL | **到岗时间的唯一可编辑真源**（中文），如 `2027年1月下旬`。页眉/命名的 `available` 一律取它 |
| `extra_json.available_note_en` | TEXT | NULL | `available_note` 的**可选**英文表述（如 `Late January 2027`）。**空则回退 `available_note`**（不是省略行） |
| `extra_json.conflict_resolution` | JSON | default `{}` | 中英冲突的用户决议：`{"default":"zh","fields":{"gpa":"zh","score":"zh","available":"zh"},"decided_at":"<ISO>","decided_by":"user","reason":"…"}`。**只影响 `SOURCE_CONFLICT` 的提示级别，不改渲染值** |
| `photo_path` | TEXT | NULL，相对仓库根，形如 `data/profile/photo_<sha256>.png` | 证件照。**中英两版 PDF/DOCX/HTML 默认都渲染**（用户明确要求保留照片）；仅本地渲染，**永不进任何 LLM payload** |
| `photo_source` | TEXT | CHECK IN (`manual`,`imported`,`none`), default `none` | `manual`=用户上传/替换；`imported`=从导入简历的内嵌图抽取并经用户确认；`none`=无照片 |
| `photo_width` / `photo_height` | INTEGER | NULL | 像素尺寸（导入的候选图为 266×266，见 §7） |
| `photo_bytes` | INTEGER | NULL | 文件字节数 |
| `photo_sha256` | TEXT | NULL | 内容哈希（去重 + 变更检测） |
| `skills_json` | TEXT | default `[]`，JSON 数组 | **职业技能行**（用户裁决：不拆 tag，见下 §1.1）。每项 `{line, category, tokens, order}` |
| `profile_fields_source` | TEXT | NOT NULL DEFAULT `'{}'`, CHECK `json_valid` | 字段来源映射：`{"degree":"import:<id>","city":"manual"}`。**只记录、不驱动渲染**；改值即改来源（写 `manual`）。见 §2.2 |
| `links_json` | TEXT | default `[]` | `[{"label":"GitHub","url":"..."}]` |
| `extra_json` | TEXT | default `{}` | 扩展字段（籍贯、政治面貌等），键值自由 |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

**对外只读快照**：`GET /api/v1/profile` 返回上述字段 + `completeness`（0–1，按必填权重算）+ `missing[]`（缺失的字段名，用于命名校验与 UI 提示）。

**隐私红线（写入 schema 注释并在 API 层强制）**
- **永不上云**：`name_zh` / `name_en` / `phone` / `email` / 照片（`photo_path` 及任何二进制）/ 身份证与学号类字段。**`school_zh` / `school_en` 允许真实上云**（v1.3 口径，见 ARCHITECTURE ADR-18）。发送前在 `services/llm_payload.py` 统一替换为占位符 `[NAME]` / `[PHONE]` / `[EMAIL]` / `[SCHOOL]` / `[ID]`，**真实值只在本机渲染阶段回填**（见 ARCHITECTURE §5.4、API-CONTRACT §10.2.1、不变量 I10）。
- 允许上云的宽路径内容：经历/项目文本（用户显式选中的 variant）、JD 文本、公司名、岗位名、用户备注、下行抓到的公开页面正文。

**「可上云的候选人档案段」= 七项白名单（`prompts.py` 的 `ALLOWED_SOURCES` 增 `"profile"` 的契约依据）**

```json
{ "school": "示例大学", "school_tier": "985", "degree": "本科", "major": "管理科学（商业数据分析）",
  "grad_year": 2028, "city": "武汉", "available_date": "2027-01-下旬" }
```

- 这七项**按真实值发送**（校名不脱敏）——它们是竞争力判断的输入，不是标识符；
- **永不在内**：`name_zh`/`name_en`/`phone`/`email`/照片字节与哈希/身份证学号；
- `ALLOWED_SOURCES` 若含 `"profile"`，**只能**按本段七项取字段（实现上用 `llm_brief()` 白名单投影，不是把整行 profile 序列化）；漏一项或带错一项都属实现违规（AC-PRIV-14）。
- `UserProfile` 不出现在 FTS 索引里。

### 1.1 `skills_json`：展示层与索引层分离（用户裁决，**不拆 tag**）

**决策背景**：用户明确否决把技能拆成 tag/标签云——「HR 看到一堆 tag 不知道具体情况，会莫名其妙」。简历是给人看的成品，技能区必须保留**整句原文**。但 JD 匹配又需要精确 token，因此拆两层：

```json
[
  {"line": "数据分析类：掌握Python、R、SQL等编程语言，可独立进行数据清洗、统计分析与可视化处理",
   "category": "数据分析类",
   "tokens": ["python", "r", "sql", "数据清洗", "统计分析", "可视化"],
   "order": 10}
]
```

| 键 | 类型 | 约束 |
|---|---|---|
| `line` | str | **唯一渲染源**（逐字为真值，含标点与全角字符）。PDF/预览/DOCX 只读它，一个字都不改 |
| `category` | str | 展示用的行首分类（「数据分析类：」），可为空串；**不单独成节、不单独渲染** |
| `tokens` | str[] | **派生索引**，只供 JD 匹配与排序。允许重建、允许缺失、**禁止参与任何渲染** |
| `order` | int | 展示顺序（升序） |

**硬约束（实现必查）**
- 渲染管线（`services/assembler.py` → `render_*.py`）**只能读 `line`**；matcher（`services/jd_analyzer.py`）**只能读 `tokens`**。两者不得互相污染——PDF 里出现 ` | ` 分隔的 tag 块、或匹配器去解析 `line` 做分词，都算实现违规。
- `tokens` 缺失/为空 → 匹配降级为**整句子串匹配**（`line.lower()` 里 `in` 判断技能名），**不得报错、不得丢行**。
- `tokens` 生成规则：规范化小写 + 别名归一（`Python`/`py`→`python`；`R`→`r`；`SQL`→`sql`；`VLOOKUP`/`数据透视表`→`excel`）。别名表是**「匹配用别名表，不影响渲染」**，落代码常量表（`services/skills_alias.py`）并在文件头注明该用途。
- `skills_json` 属**本地上云白名单**（可发送，因为它是经历/技能文本），但发送前仍走 §1 的宽路径与占位符规则（其中若含姓名等标识，按同一规则脱敏）。



---

## 2. Package（经历包：项目 / 实习 / 教育 / 奖项）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | | |
| `title` | TEXT | NOT NULL, 1–120 | 包名，如 `订单中台重构` |
| `kind` | TEXT | CHECK IN (`project`,`internship`,`education`,`award`,`activity`,`custom`) | |
| `org` | TEXT | NULL | 公司/学校/组织，如 `某某科技` |
| `role` | TEXT | NULL | 担任角色，如 `后端开发实习生` |
| `start_date` | TEXT | NULL, `YYYY-MM` | 允许只有年月 |
| `end_date` | TEXT | NULL, `YYYY-MM` | |
| `is_current` | INTEGER | 0/1, default 0 | 进行中（渲染为 `至今`） |
| `location` | TEXT | NULL | 城市/远程 |
| `summary` | TEXT | NULL, ≤600 | 一句话概述；**默认不进 LLM payload**，需显式选中 |
| `tech_stack_json` | TEXT | default `[]` | `["Python","Go","PostgreSQL"]` |
| `tags_json` | TEXT | default `[]` | 自由标签：`["分布式","可观测性"]` |
| `outcomes_json` | TEXT | default `[]` | `[{"metric":"QPS","from":"1.2k","to":"8.5k","unit":""}]` |
| `evidence_json` | TEXT | default `[]` | 证据链接/文件 id（本地） |
| `status` | TEXT | CHECK IN (`draft`,`ready`,`archived`), default `draft` | `ready` 才允许被 build 选中 |
| `source` | TEXT | CHECK IN (`authored`,`imported`,`llm_assisted`) | 来源追溯 |
| `content_hash` | TEXT | NULL | 用于「同一段落被多处引用」的去重与变更检测 |
| `source_import_job_id` | TEXT | NULL, FK → `import_job.id` | **派生来源**：由 `committed` 的导入 job 自动生成时为该 job 的 id；手工/LLM 新建为 NULL。**幂等键的一半** |
| `source_entry_temp_id` | TEXT | NULL | **幂等键的另一半**：draft 里该 entry 的稳定临时 id（`draft_json.blocks[].entries[].temp_id`）。与 `source_import_job_id` 组成唯一索引 `UNIQUE(source_import_job_id, source_entry_temp_id)` |
| `deleted_at` | TEXT | NULL | 软删除 |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

索引：`(kind)`, `(status)`, `(org)`, `(deleted_at)`, **`UNIQUE(source_import_job_id, source_entry_temp_id)`**（部分索引：`WHERE source_import_job_id IS NOT NULL`）；FTS5 见 §14。

**规则**
- `is_current=1` 时 `end_date` 必须为 NULL。
- `status` 从 `draft` → `ready` 需满足：至少 1 个 `verified=1` 的 `PackageBulletVariant`。
- 删除是软删除；软删除后不出现在默认列表，但已导出的 build 仍可追溯（`BuildSelection` 存快照）。

---

### 2.1 派生字段铁律：`is_current` 与 `end_date`（本次数据损坏的成因，D-35）

这一小节单独存在，是因为 `is_current` 曾被实现「推导」出来，导致真库 **18/18 行**被写成「进行中 + 结束时间为空」。**派生规则一旦含糊，损坏是批量且静默的**，所以在此冻结。

| 规则 | 内容 |
|---|---|
| **R1** | `is_current` **只能来自显式输入**（`POST`/`PATCH` 请求体里的布尔字段），默认 `false`。 |
| **R2** | **禁止**从 `end_date` 是否存在推导 `is_current`；**禁止**因缺省值把 `is_current` 置真（`False` 必须编码为 `0`，不得写成 `1`）。 |
| **R3** | `end_date` **只能**由两种原因变化：① 用户显式修改；② `is_current=true` 时被清空（唯一允许的自动清空）。除此之外任何写入路径不得丢弃它。 |
| **R4** | 校验护栏：`is_current=true` 且带 `end_date` → **422**。这条是唯一阻止静默覆盖的护栏，**不许为了「写入更宽松」而删除**。 |
| **R5** | `end_date` 的**唯一权威来源** = 用户输入，或该 Package 来源 `import_job.draft_json` 中对应 entry 的 `date_range`（实测草稿含 `date_range` 的 entry 有 **182 条**）。两者都拿不到 → 留 `null` 并写 `warnings`，**不得用 `created_at`、`updated_at` 或任何时间戳推算**。 |
| **R6** | 布尔入库编码统一：`True → 1`、`False → 0`（**代码层面禁止** `1 if isinstance(v,bool) else …` 这类只看类型不看值的写法，`server/app/repos.py:686` 即反例）。 |

> 验收：`AC-BUILD-13`（P0，日期往返 + 反向断言 `is_current=false` + 锁住 422 护栏）；缺陷登记见 `docs/API-CONTRACT.md §17.8.1`（D-35）。

---

## 2.2 `facts` 与 `bullets`：整段文字 vs 要点列表（用户真实简历驱动）

教育段在用户原简历里是**整段文字**（`专业成绩：GPA 3.56/4　86.53/100　CET4：562　CET6:508`、`主修课程：…（R）(91)…`），不是 bullet。两类内容渲染规则不同，**存的东西也必须分开**：

| | `facts[]`（整段事实） | `bullets[]` / `PackageBulletVariant`（要点） |
|---|---|---|
| 用于 | **教育**段、技能段等「一句话陈述」 | 经历 / 项目段的成果要点 |
| PDF 渲染 | **整段文字**，行首**不得有 `·`**；悬挂缩进与 bullet 文本齐平（即首行与后续行左边界一致） | 行首带项目符号，悬挂缩进 |
| 空值 | `facts` 为空 → 渲染 `N/A`，**不得留空行** | 无 bullet 视为内容缺失（`MISSING_SLOTS`/`warnings` 处理） |
| 上云 | 可发（属经历文本） | 可发 |

**为什么不用一处**：把整段 `主修课程：…` 拆成 N 条 bullet 会改变用户原意与版面（一行变五行，直接破单页）；反之把成果要点写成整段会丢掉可扫读性。AC-PDF-10 断言 `facts` 渲染无行首符号，AC-SKILL-01 断言技能行逐字相等。

### 2.2 commit 回填与分层铁律（v1.28）

**新列 `user_profile.profile_fields_source`**：`TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(...))`，形如 `{"degree":"import:01a165…","major":"import:01a165…","city":"manual"}`。用途：回答「这个字段是哪来的」，让用户在个人信息页能区分**导入带进来的**与**自己填的**；改值即改来源，写 `manual`。

| 不变量 | 断言 | 违反后果 |
|---|---|---|
| **I15 静态内容不得丢失** | 源草稿某块有正文 ⇒ 对应 `template_block.static_text` 非空 | 导出静默少一段（真实事故：教育 facts 与技能整句全丢，PDF 只剩校名 + `SKILLS_EMPTY`） |
| **I16 档案字段只许「有则填、无则 NULL」** | commit 后 `user_profile` 的每个可回填字段，要么等于草稿值（含 source 记录），要么为 NULL 且草稿确实没有该字段 | 填默认值 = 编造；覆盖手填值 = 数据丢失 |
| **I17 分层不互推** | 渲染路径不读 `tokens`；匹配路径不读 `line`/`static_text` 并回写 | 为改匹配而动了出稿文案（用户看到的简历被悄悄改写） |

**回填范围与优先级**：`degree`/`major`/`grad_year`/`city`/`available_date`/`skills_json` 六项可由 commit 回填；**`name_zh`/`name_en`/`phone`/`email`/`school_zh`/`school_en`/`photo_*` 一律不由 commit 覆盖**（身份与联系信息只认用户显式输入或照片候选确认）。

**`name_en` 排版口径（v1.28）**：英文名按**用户英文简历抬头原样**保存并用**全大写**渲染（例 `SAN ZHANG`）；`name_zh` 与 `name_en` 是**两个独立字段**，**任何一方都不得从另一方推导**（不拼音转写、不 Title Case 转换）。中文版只渲染 `name_zh`，英文版只渲染 `name_en`；`name_en` 缺失时英文版回退 `name_zh` 并在导出 warnings 记 `PROFILE_FIELD_MISSING`。

### 2.3 语言维度（v1.29）

**一句话**：`lang` 不是一个渲染开关，而是**数据的对立面**——没有 `lang='en'` 的资产，就不该产出自信的英文简历。

| 不变量 | 断言 | 违反后果 |
|---|---|---|
| **I18 变体语言单一** | 一次装配只用一种 `lang` 的 variant；某条目缺该语言变体 ⇒ 必须出现 `LANG_FALLBACK` | 中英混排（半句英文半句中文），用户拿到一份自己不认识的简历 |
| **I19 导入产出同语言资产** | `import_job.source_lang='en'` ⇒ 该次 commit 创建的变体 `lang='en'`（`unknown` 退回 `template.lang`） | 导入英文简历却只得到中文变体 → 英文导出必然 `LANG_FALLBACK` 满屏 |
| **I20 语言字段不串版** | `degree_en`/`major_en` 的值不得出现在 zh 版；`degree`/`major` 的中文值不得出现在 en 版 | 「本科」塞进英文简历 / `B.M.` 出现在中文简历 |
| **I21 证据三源可回溯** | `jd_requirement.matched_evidence_json` 每项 `source ∈ {package, skills_json, profile}`；`source="package"` ⇒ `ref_id` 非空且指向 `status='ready'` 的包；`skills_json`/`profile` ⇒ `ref_id IS NULL`；`quote` 非空、长度 ≥8、且**能在所指来源里逐字找到** | 证据不可回溯 = 无法核对，等于让模型自证；界面会显示点不开的引用 |
| **I22 「没匹配到」是两个数组皆空** | `matched_package_ids_json=[] **且** matched_evidence_json=[]` 才是「确实没匹配到」；任一非空 ⇒ `candidate_status` 不得为 `missing` | 技能栏/院校/届别命中却显示 `matched=0`（真库已发生）→ 用户以为自己的经历不被认可 |
| **I23 人工判断不被自动覆盖** | `candidate_status_source='manual'` 的行，任何重算/分析只可更新 `matched_*`（事实层），**不得改写 `candidate_status`（判断层）**；撤销需显式传 `candidate_status_source="auto"` | 用户手工改过的判断被后台任务悄悄改回，且无任何提示 |
| **I26 说命中就得拿得出凭据** | `candidate_status ∈ {satisfied, partial}` ⇒ **必须**满足其一：① `matched_evidence_json` 非空；或 ② 该条携带 `STATUS_WITHOUT_EVIDENCE` 告警（`details.action` 区分 `downgraded` / `flagged`）。**`candidate_status_source='manual'` 豁免** | **系统替候选人背书**：`satisfied` 会被组装当成「已具备能力」写进简历，用户拿去投递时无从核对。**原始反例（2026-10-23 真库六条）**：修复前 3 行 `satisfied` 却零证据（「毕业届别」「985/211 院校优先」「SQL/Python」）；修复后实测 `4/6 有证据`，另 2 行零证据但状态诚实（1 `partial` 已打 `flagged`、1 `missing`）。**降级而非仅告警**，因为无凭据的 satisfied 就是撒谎 |

**结构词表**：`API-CONTRACT §8.5.1`（7 种 `block.kind` + 字段标签 + 日期格式），**本地硬编码，不走 LLM**；不在表内的自定义 heading 保留原文 + `LANG_HEADING_UNMAPPED`。

### 2.4 页眉与教育段渲染来源（v1.33）

| IR 字段 | 唯一允许来源 | 禁止 |
|---|---|---|
| `ir.header.name` | `user_profile.name_zh`（`lang=zh`）/ `name_en`（`lang=en`，全大写渲染） | 拼音转写、Title Case 转换 |
| `ir.header.phone` / `email` | `user_profile.phone` / `email` | 拼接、脱敏后回填（页眉只在本机渲染，明文） |
| `ir.header.available_note` | `user_profile.available_note`（中文真值，**唯一可编辑来源**）；`lang=en` 时取 `extra_json.available_note_en`，**为空则回退中文值**（v1.38 改：旧口径「省略该行 + `PROFILE_FIELD_MISSING`」作废——用户明确要求中英两版都显示到岗时间） | 用 `available_date` 作为渲染来源；用 `grad_year` 拼接「2028 年毕业可到岗」 |
| （**不得存在**）`education_line` | — | **禁止**把 `degree`/`major`/`grad_year`/`city` 拼进页眉（与教育段重复，用户原件也没有） |
| `education.entry.date` | `import_job.draft_json.entry.date_range` 原文 | **禁止**用 `grad_year` 顶替；缺 `date_range` 时留空 + `PROFILE_FIELD_MISSING` |

**理由**：用户原简历（中文第十版、英文版**都是**）页眉只有姓名 + 联系方式。把学历塞进页眉既踩了「重复」，也让英文页眉出现「本科」这类中文字——两条都是用户一眼能看见的瑕疵。

## 3. PackageBulletVariant（同一条经历的多版本描述）

一条 bullet 的「同一事实」可以有多个措辞版本（结果导向 / 技术细节 / 领导力 / 精简），组装时按 JD 与版面挑一个。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | | |
| `package_id` | TEXT FK → package(id) ON DELETE CASCADE | NOT NULL | |
| `bullet_key` | TEXT | NOT NULL, ≤40 | 同一事实的稳定标识，如 `b1`、`latency`；同 package 内唯一 `(package_id, bullet_key, tone)` |
| `text` | TEXT | NOT NULL, 1–400 | bullet 正文（中文或英文，由 `lang` 标示） |
| `tone` | TEXT | CHECK IN (`impact`,`technical`,`leadership`,`concise`,`ats`) | |
| `lang` | TEXT | CHECK IN (`zh`,`en`) | 同一事实的中英双版本各占一行 |
| `keywords_json` | TEXT | default `[]` | 用于 JD 匹配打分（技能词、工具名） |
| `metrics_json` | TEXT | default `[]` | 该 bullet 内含的量化指标，供一致性检查 |
| `char_len` | INTEGER | 生成列或写入时计算 | 便于版面预估（中文按 1、英文按 0.55 权重） |
| `llm_generated` | INTEGER | 0/1, default 0 | 追溯来源 |
| `verified` | INTEGER | 0/1, default 0 | 用户确认事实无误（未 verify 的不得进入默认选择） |
| `quality_score` | REAL | NULL, 0–1 | 可选：LLM 评分或人工星级归一 |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

唯一约束：`UNIQUE(package_id, bullet_key, tone, lang)`。
排序：`ORDER BY bullet_key, tone`。

**为什么不用「一条 bullet 一列」**：variant 是**可重组的最小单元**，组装器只认 `variant_id`；这保证「按需调用 Warehouse 内 Package 组装」时能精确到句。

---

## 4. Template（可重组简历模板）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | | |
| `name` | TEXT | NOT NULL, 1–80 | 如 `单页-中文-技术岗` |
| `source_kind` | TEXT | CHECK IN (`imported_pdf`,`imported_docx`,`imported_md`,`imported_html`,`builtin`) | |
| `source_file_id` | TEXT | NULL, FK → attachment(id) | 导入原件 |
| `lang` | TEXT | CHECK IN (`zh`,`en`,`mixed`) | |
| `page_limit` | INTEGER | 1–3, default 1 | 目标页数（超页要在 assemble 阶段告警） |
| `layout_json` | TEXT | default `{}` | 页面级：`{"paper":"A4","margins_mm":[16,16,14,14],"columns":1,"font":{"body":"STSongti-SC-Regular","size":10.5,"leading":15},"accent":"#1a6b4f"}` |
| `is_default` | INTEGER | 0/1, default 0 | 全局唯一（partial unique index） |
| `target_role_family` | TEXT | NULL | 如 `数据分析`、`后端`，用于推荐 |
| `deleted_at` | TEXT | NULL | 软删除 |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

**从导入到可重组的三步**（契约见 API §5）：`ImportJob`（解析）→ 用户在 UI 里校对 blocks/slots → `commit` 后落 `Template + TemplateBlock + Slot`。**未 commit 的草稿只存在于 ImportJob.draft_json**，不污染模板库。

---

## 5. TemplateBlock（模板的区块树）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | | |
| `template_id` | TEXT FK → template(id) ON DELETE CASCADE | NOT NULL | |
| `parent_block_id` | TEXT FK → template_block(id) ON DELETE CASCADE | NULL | 支持嵌套（section 内含 entry） |
| `order_index` | INTEGER | NOT NULL | 同父级内排序，允许稀疏（10,20,30）便于插入 |
| `block_type` | TEXT | CHECK IN (`header`,`summary`,`section`,`entry`,`bullet_list`,`skills`,`awards`,`footer`,`freeform`) | |
| `heading` | TEXT | NULL | 区块标题，如 `教育背景`、`PROJECT EXPERIENCE` |
| `bound_package_kind` | TEXT | NULL, CHECK 同 package.kind | 声明「本区块消费哪类包」，如 education 区块绑 `education` |
| `style_json` | TEXT | default `{}` | `{"size":12,"bold":true,"space_before":6,"space_after":3,"rule":"bottom","color":"#111"}` |
| `page_break_before` | INTEGER | 0/1, default 0 | |
| `max_bullets` | INTEGER | NULL | 每 entry 最多渲染几条 bullet（版面控制） |
| `static_text` | TEXT | NULL | 不变文本（如 `专业技能` 的分隔说明） |
| `repeat_per_package` | INTEGER | 0/1, default 1 | 1 = 每个选中包重复一次（entry），0 = 只渲染一次 |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

唯一约束：`UNIQUE(template_id, parent_block_id, order_index)`。
删除策略：删父块级联删子块（`ON DELETE CASCADE`）。

---

## 6. Slot（区块内的具名变量 —— 「命名模板变量」）

Slot 是模板与数据之间的**唯一绑定点**。渲染时只有两种来源：`bound_field`（从 UserProfile / Package / Build 取值）或 `field_values_json`（用户在 build 时手填）。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | | |
| `block_id` | TEXT FK → template_block(id) ON DELETE CASCADE | NOT NULL | |
| `slot_key` | TEXT | NOT NULL, `^[a-z][a-z0-9_.]{0,40}$` | 变量名，如 `candidate.name`、`candidate.school`、`position.title`、`package.company` |
| `slot_type` | TEXT | CHECK IN (`text`,`longtext`,`date_range`,`taglist`,`url`,`image`,`computed`) | |
| `required` | INTEGER | 0/1, default 0 | `required=1` 缺值 → assemble 中止 422 `MISSING_SLOTS`；`required=0` 缺值 → 渲染占位符 + warning `MISSING_SLOTS_RENDERED`，仍 200 |
| `bound_field` | TEXT | NULL | 形如 `profile.name_zh`、`profile.school_zh`、`package.role`、`package.org`、`build.position`；`NULL` 表示用户手填 |
| `default_value` | TEXT | NULL | |
| `max_chars` | INTEGER | NULL | 超出要告警（版面溢出风险） |
| `pattern` | TEXT | NULL | 正则校验（如日期） |
| `list_source` | TEXT | NULL, CHECK IN (`profile.links_json`,`package.tech_stack_json`,`package.tags_json`) | `taglist` 类型的数据来源 |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

唯一约束：`UNIQUE(block_id, slot_key)`。

**保留 slot_key 命名空间（渲染器认识的固定变量）**

| slot_key | 语义 | 取值来源 |
|---|---|---|
| `candidate.name` | 姓名 | `bound_field=profile.name_zh`（或 `name_en`，按 template.lang） |
| `candidate.school` | 学校 | `profile.school_zh` / `school_en` |
| `candidate.degree` `candidate.major` `candidate.grad_year` | 学历 | profile |
| `candidate.phone` `candidate.email` `candidate.city` | 联系方式 | profile（**本地渲染，永不进 LLM**） |
| `candidate.available` | 到岗时间 | `profile.available_date` / `available_note` |
| `candidate.photo` | 照片 | `profile.photo_path`（PDF/DOCX/HTML 均支持；无照片时该槽位整体省略，且**不得留空洞**，见 ARCHITECTURE §7.2） |
| `position.title` | 目标岗位 | `build.position`（来自 JD 或手填） |
| `position.company` | 目标公司 | `build.company` / CompanyProfile.company_name |
| `build.date` | 生成日期 | 导出时刻 |
| `package.*` | 包内字段 | `package.title/org/role/start_date/end_date/summary` |

自定义 slot 必须用 `snake_case`，渲染器遇到未知 `bound_field` → `TEMPLATE_INVALID`(422)。

---

## 7. ImportJob（导入的历史与审计记录，**不承担轮询职责**）

> **v1.7 定位变更**：上传是**同步语义**（201 + 内联 draft），因此 `ImportJob` 不是状态机驱动的前端轮询对象，而是**历史与审计记录**：一次导入 = 一行，`status` 只表达「草稿 / 已提交 / 失败」三种终态。字段级别名与旧实现里 `queued`/`parsing` 的值仍被接受（只读历史），但**新写入只用 `draft`/`committed`/`failed`**。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | | |
| `attachment_id` | TEXT FK → attachment(id) | NOT NULL | 原件 |
| `status` | TEXT | CHECK IN (`draft`,`committed`,`failed`)；历史行可为 `queued`/`parsing`（只读，不再新写）, default `draft` | 终态语义：`draft` 已产出草稿待用户校对；`committed` 已落库为模板；`failed` 解析失败（错误码见 API-CONTRACT §14） |
| `source_lang` | TEXT | CHECK IN (`zh`,`en`,`unknown`), default `unknown` | 导入源语言（正文 CJK 占比：≥30% → `zh`，≤5% → `en`，其余 `unknown`）。**commit 创建的变体 `lang` 取自本列**（`unknown` 退回 `template.lang`），见 `API-CONTRACT §8.5.3`；**禁止一律写 `zh`** |
| `parser` | TEXT | CHECK IN (`pdf`,`docx`,`md`,`html`,`txt`) | |
| `draft_json` | TEXT | default `{}` | 解析出的完整草稿：`{lang, parser, pages, blocks[], sections[], section_kinds[], entry_counts{}, skills[], stats, warnings[], needs_llm_fallback, quality{}}`。**`blocks` 是唯一真值源**；`sections[]`（`{kind, heading, entry_count}`）、`section_kinds`、`entry_counts`、`skills` 均由 blocks **派生**，`PUT` 时服务端重算（D-25）；`quality` 四键语义见 API-CONTRACT §5.1（`numbers_second_pass` 恒 false = 未做二次数字核对） |
| `stats_json` | TEXT | default `{}` | `{"pages":1,"chars":1791,"words":85,"images":1,"cid_missing":0,"has_photo":true}` |
| `warnings_json` | TEXT | default `[]` | 如 `[{"code":"CID_GLYPH_MISSING","count":16}]` |
| `extracted_photo_json` | TEXT | default `null` | 内嵌图候选：`{"available":true,"file":"data/profile/candidate_<imp>.png","width":266,"height":266,"rendered":{"page":1,"w_pt":89.3,"h_pt":89.3,"x0_pt":497.1,"top_offset_pt":3.8},"probable_kind":"id_photo","applied":false}`；用户确认后才写 `user_profile.photo_path` |
| `result_template_id` | TEXT | NULL, FK → template(id) | commit 后回填；**写入后不可清空**（R-a），见下方生命周期规则 |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

**`result_template_id` 生命周期规则（v1.26 定版，源自真实事故）**

| 规则 | 内容 |
|---|---|
| **R-a 写入后不可清空** | `commit` 回填 `result_template_id` 后，**任何路径都不得把它写回 NULL**（软删、恢复、清理脚本一律不动该列）。溯源链断掉是不可恢复损失：模板还在、却再也答不出「这份模板是从哪份简历来的」 |
| **R-b 模板独立存活** | `import_job` 被软删**不影响** `template`：模板是独立实体，用户可能长期在用 |
| **R-c 归档禁令（给清理脚本的硬校验）** | **只要 `result_template_id` 指向的 template 还活着（`deleted_at IS NULL`），该 `import_job` 就不允许被归档/清理**。清理脚本（`scripts/prune_probe_data.py`、`clean_orphan_photos.py` 同族）在归档前必须跑这条 SQL 校验，命中即跳过并告警 |

```sql
-- R-c 的机械校验：结果集必须为空，否则禁止归档这些行
SELECT i.id FROM import_job i
  JOIN template t ON t.id = i.result_template_id
 WHERE i.deleted_at IS NOT NULL      -- 待归档
   AND t.deleted_at IS NULL;         -- 但模板还活着 → 禁止
```

> 真实事故（2026-10-23）：清理脚本按「同指纹留最新」归档了 6 条 `status='committed'` 的 `import_job`，其中 `01a165188d92700783d126474f4875be` 正是唯一活跃默认模板「中文-单页-审」的来源行。模板没丢，**溯源断了**。此后 committed/有产出的行永不归档。
**已知解析陷阱（必须写进 importer 的规则）**
- `(cid:127)`：本机英文样张 `data/imports/sample_en.pdf` 里出现 **16 次**，实测**全部位于 bullet 行首**（ReportLab 生成的 Symbol 项目符号，ToUnicode 缺失）。处理：识别为「列表项标记」→ 从文本中剥离并置 `list_marker=true`，**不得**留在正文里，也不得当作缺字报警（计入 `warnings_json` 的 `CID_GLYPH_MISSING`，文案为「已将 16 处 (cid:127) 项目符号还原为列表项」）。
- 其他 `(cid:N)`（N≠127）→ 计入 `warnings_json[{code:"CID_GLYPH_MISSING", nib:N}]`（**复用** §14.1 的 `CID_GLYPH_MISSING`，不新造码），该行标 `needs_review=true`，导出前必须人工确认。
- 扫描件（无文本层，`chars < 20`）→ `IMPORT_NO_TEXT_LAYER`(422)，不做 OCR。
- **内嵌照片抽取**：中文样张实测 1 张 **266×266 JPEG**，渲染在 A4（595.5×842.2 pt）**右上角 89.28×89.28 pt 方块**（`x0=497.08`，距页顶 3.82 pt，**距页面右缘 9.13 pt**）。用 `pdfplumber page.images` / `pypdf` 抽原始字节，落 `data/profile/candidate_<import_id>.<ext>`，写 `extracted_photo_json`；**不自动**写 profile，必须用户在校对页确认（`PUT /profile/photo`）。
- Canva 类 PDF 常有背景图 + 分栏文字：必须按 `chars` 的 `(x0, top)` 聚簇成行，不能依赖 `extract_text` 的默认顺序。

---

## 8. Attachment（本地文件引用）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | | |
| `sha256` | TEXT | NOT NULL UNIQUE | 内容寻址；磁盘路径 `data/files/<前2位>/<sha256>.<ext>` |
| `original_name` | TEXT | NOT NULL | 只存库，不参与磁盘命名 |
| `ext` | TEXT | NOT NULL | `pdf/docx/md/html/txt/png/jpg` |
| `mime` | TEXT | NOT NULL | |
| `bytes` | INTEGER | NOT NULL | |
| `kind` | TEXT | CHECK IN (`resume_source`,`photo`,`evidence`,`export`,`other`) | |
| `privacy` | TEXT | CHECK IN (`private`,`shareable`), default `private` | `private` → 永不进 LLM payload（**`resume_source` 一定是 private**） |
| `created_at` | TEXT | NOT NULL | |

---

## 9. JobDescription + JDRequirement

### 9.1 JobDescription

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | | |
| `title` | TEXT | NULL, ≤120 | JD 里的岗位名 |
| `company_name` | TEXT | NULL, ≤120 | 用于关联 CompanyProfile |
| `raw_text` | TEXT | NOT NULL | 用户粘贴的 JD 原文（**允许进 LLM，因为是公开岗位信息**） |
| `attachment_id` | TEXT | NULL | 若来自文件 |
| `source_url` | TEXT | NULL | 来源链接（不自动抓取） |
| `lang` | TEXT | CHECK IN (`zh`,`en`) | |
| `analysis_status` | TEXT | CHECK IN (`none`,`analyzing`,`done`,`failed`), default `none` | |
| `analysis_method` | TEXT | CHECK IN (`llm`,`heuristic`,`manual`) | 离线降级时标 `heuristic` |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

### 9.2 JDRequirement

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | | |
| `jd_id` | TEXT FK → job_description(id) ON DELETE CASCADE | NOT NULL | |
| `skill` | TEXT | NOT NULL, ≤80 | 规范化后的技能名，如 `SQL`、`A/B 测试` |
| `category` | TEXT | CHECK IN (`hard`,`soft`,`domain`,`tool`,`language`,`certificate`) | |
| `priority` | TEXT | CHECK IN (`must`,`should`,`nice`) | |
| `weight` | REAL | 0–1, default 0.5 | 匹配打分用 |
| `evidence_hint` | TEXT | NULL, ≤200 | JD 原句里的证据片段 |
| `raw_quote` | TEXT | NULL | 原文引用（≤300） |
| `source` | TEXT | CHECK IN (`llm`,`heuristic`,`manual`) | |
| `matched_package_ids_json` | TEXT | default `[]`；元素必须指向 `status='ready'` 的 package id | **只表示命中的经历包**（可重算，缓存）。非空 ⇒ 有真实经历支撑；与 `matched_evidence_json` 中 `source="package"` 的项**必须一一对应** |
| `matched_evidence_json` | TEXT | default `[]`；元素 `{source, ref_id, quote}`，`source` CHECK IN (`package`,`skills_json`,`profile`)，`quote` 非空且 ≥8 字符 | **证据全集**（经历 + 技能栏 + 档案）。`source="package"` 时 `ref_id` 非空且指向 ready 包；`skills_json`/`profile` 时 `ref_id` 必须为 `null` |
| `candidate_status` | TEXT | CHECK IN (`satisfied`,`partial`,`missing`), NULL | 对照候选人现状的判断 |
| `candidate_status_source` | TEXT | CHECK IN (`llm`,`heuristic`,`local_override`,`manual`), default `llm` | 优先级 **`manual` > `local_override` > `heuristic` > `llm`**；自动链路不得改写 `manual` 行的 `candidate_status` |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

唯一约束：`UNIQUE(jd_id, lower(skill), category)`（重跑分析时 upsert）。
排序：`priority` 权重 + `weight DESC`。

---

## 10. CompanyProfile（公司招聘偏好）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | | |
| `company_name` | TEXT | NOT NULL UNIQUE | 唯一键即公司名（规范化：去空格、全角转半角） |
| `industry` | TEXT | NULL | |
| `company_stage` | TEXT | NULL | `大厂`/`创业公司`/`外企`/`国企`… 自由文本 |
| `size_hint` | TEXT | NULL | |
| `culture_signals_json` | TEXT | default `[]` | `[{"signal":"结果导向","evidence":"JD 原文…"}]` |
| `hiring_preferences_json` | TEXT | default `[]` | 简历偏好：`["偏好量化成果","一页纸","英文简历"]` |
| `interview_focus_json` | TEXT | default `[]` | |
| `tone` | TEXT | NULL | 建议语气：`务实`/`学术`/`活泼` |
| `keywords_json` | TEXT | default `[]` | 高频词 |
| `sources_json` | TEXT | default `[]` | `[{"type":"jd","ref":"jd_xxx"},{"type":"user_note","ref":""}]`；**只允许 JD 与用户手输，不抓网页** |
| `confidence` | REAL | 0–1 | LLM 自评或规则置信度 |
| `method` | TEXT | CHECK IN (`llm`,`heuristic`,`manual`) | |
| `last_analyzed_at` | TEXT | NULL | TTL 判定基准 |
| `expires_at` | TEXT | NULL | 默认 `last_analyzed_at + 30d` |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

**约束**：`sources_json` 里**不得**出现简历内容；CompanyProfile 只由「JD 文本 + 公司名 + 用户笔记」推导。任何需要联网搜索公司信息的能力**本期不做**（离线优先）。

---

## 11. ResumeBuild（一次定制简历的构建）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | | |
| `name` | TEXT | NOT NULL, ≤120 | 内部名，如 `字节-数据分析-2026秋招` |
| `template_id` | TEXT FK → template(id) ON DELETE RESTRICT | NOT NULL | |
| `jd_id` | TEXT FK → job_description(id) ON DELETE SET NULL | NULL | |
| `company_profile_id` | TEXT FK → company_profile(id) ON DELETE SET NULL | NULL | |
| `position` | TEXT | NULL, ≤80 | 目标岗位名（命名模板 `{position}` 的首选来源） |
| `company` | TEXT | NULL, ≤80 | 目标公司名（`{company}` 来源） |
| `lang` | TEXT | CHECK IN (`zh`,`en`), default `zh` | 决定 `{name}`/`{school}` 取中/英字段，也决定 PDF 排版 |
| `status` | TEXT | CHECK IN (`draft`,`assembled`,`exported`,`failed`), default `draft` | |
| `naming_pattern` | TEXT | NOT NULL, default `{position}-{name}-{school}` | 命名模板（规则见 API-CONTRACT §9） |
| `density` | TEXT | CHECK IN (`original`,`relaxed`), default `original` | 版式密度：`original` = 用户原件密度（单页优先，正文 ≥10.0 pt）；`relaxed` = 通用边距（允许 2 页并告警）。常量见 ARCHITECTURE §7.5.1，ADR-21 |
| `naming_overrides_json` | TEXT | default `{}` | 变量覆盖：`{"version":"v5","school":"示例大学"}` |
| `field_values_json` | TEXT | default `{}` | 手填槽位：`{"summary.text":"..."}` |
| `sections_order_json` | TEXT | default `[]` | 用户拖拽后的区块顺序（template_block id 列表） |
| `warnings_json` | TEXT | default `[]` | 组装告警：`[{"code":"PAGE_OVERFLOW","detail":"预计 1.4 页"}]` |
| `est_pages` | REAL | NULL | 组装时估算 |
| `archived_at` | TEXT | NULL, **schema v10 新增** | **归档时间**（不是删除）。语义见下方「归档 vs 软删」，与 `package.deleted_at` **不是同一套措辞** |
| `created_at` / `updated_at` | TEXT | NOT NULL | |

**归档 vs 软删（两套语义，禁止混用同一套措辞）**

| 概念 | 列 | 含义 | 可见性 | 可逆 | 下游影响 |
|---|---|---|---|---|---|
| **归档（build）** | `resume_build.archived_at` | 「这次构建我已不需要了，从默认列表里收起来」——**行一直在，选择集合与产物都还在** | `GET /builds` **默认过滤**；`?include_archived=1` 可见 | 可逆：`archived_at = NULL` 即恢复 | **不影响** `build_selection` / `build_artifact`，也不影响 `package` / `template` |
| **软删（package / import_job）** | `package.deleted_at` / `import_job.deleted_at` | 「这个对象不该再被引用了」——**下游引用必须失效或降级** | 详情可见但标记已删；列表默认过滤 | 可逆（`restore` 端点） | **必须联动**：派生包同事务、`matched_package_ids` 剔除、`PACKAGE_MISSING` 等 |

一句话：**归档是「我不想看见它」，软删是「它不该再被用」**。把归档写成软删，会造出「已归档 build 的产物指向已删包」这种半删状态。

**不变量 I24（归档不删行）**：`resume_build` 只允许通过 `archived_at` 表达「不需要了」；**任何清理脚本不得物理删除 `resume_build` 行**，硬删必须显式（独立脚本 + `--hard` 参数）且**先落快照**（该行 + 其 `build_selection`/`build_artifact` 导出为 JSON）。违反后果：`data/exports/` 里的 PDF 变成无主孤儿——文件在、行没了，用户再也看不到自己导出过什么。

**不变量 I25（无悬空行）**：`build_selection.build_id` 与 `build_artifact.build_id` 必须始终能对应到 `resume_build` 的行。归档**不动**这两张表；只有硬删才可能产生悬空行，因此硬删必须在同一事务里处理子表。

**快照语义**：build 一旦 `exported`，其选择集合（`BuildSelection`）与 `field_values_json` 即视为快照；之后修改 Package 不改变已导出文件（但可「重新组装」生成新 build 版本）。

---

## 12. BuildSelection（选中的包与变体）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | | |
| `build_id` | TEXT FK → resume_build(id) ON DELETE CASCADE | NOT NULL | |
| `package_id` | TEXT | NOT NULL | 不设 FK：允许包被软删后仍保留快照 |
| `variant_ids_json` | TEXT | NOT NULL, default `[]` | 该包被选中的 bullet variant id 列表（有序） |
| `order_index` | INTEGER | NOT NULL default 0 | 该包在区块内的顺序 |
| `overrides_json` | TEXT | default `{}` | 该包的渲染覆盖：`{"org_display":"某某科技有限公司","hide_dates":false}` |
| `snapshot_json` | TEXT | default `{}` | 打包时的只读快照（title/org/role/dates/bullets 文本），保证可追溯 |
| `created_at` | TEXT | NOT NULL | |

唯一约束：`UNIQUE(build_id, package_id)`。

---

## 13. BuildArtifact（导出产物）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | TEXT PK | | |
| `build_id` | TEXT FK → resume_build(id) ON DELETE CASCADE | NOT NULL | |
| `format` | TEXT | CHECK IN (`pdf`,`docx`,`html`,`md`) | |
| `engine` | TEXT | CHECK IN (`reportlab`,`chrome`,`docx`,`jinja2`) | 哪个引擎产出（可追溯 D5/D6） |
| `filename` | TEXT | NOT NULL | 最终文件名（已净化、已解析命名模板） |
| `rel_path` | TEXT | NOT NULL | 相对 `data/exports/`，如 `2026/rb_xxx/数据分析实习生-张三-示例大学.pdf` |
| `bytes` | INTEGER | NOT NULL | |
| `sha256` | TEXT | NOT NULL | |
| `text_verified` | INTEGER | 0/1/NULL | PDF 文本层一致性校验结果（NULL=未校验，如 docx） |
| `text_diff_json` | TEXT | default `[]` | 不一致明细（`[{"expected":"高","got":"U+2FBC"}]`，最多 20 条） |
| `warnings_json` | TEXT | default `[]` | 如 `[{"code":"EMOJI_STRIPPED","count":2}]` |
| `created_at` | TEXT | NOT NULL | |

---

## 14. 支撑表

### 14.1 Job（长任务，>2 s 的操作）
`id`, `kind`(`import_parse`,`jd_analyze`,`company_analyze`,`bullets_generate`,`build_export`,`build_batch`), `status`(`queued`,`running`,`succeeded`,`failed`,`interrupted`), `progress`(0–100), `message`, `result_json`, `error_json`, `created_at`, `finished_at`。

### 14.2 LlmPreview（consent 状态机，服务端唯一真源）
| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | TEXT PK | `preview_id` |
| `purpose` | TEXT | CHECK IN (`jd_analyze`,`bullets_generate`,`company_profile`,`build_suggest`,`summary_polish`) |
| `provider` / `model` / `endpoint_host` | TEXT | 发送时的目标 |
| `payload_json` | TEXT | **将要发出的完整请求体**（可直接回显给 UI） |
| `payload_sha256` | TEXT | 一致性校验 |
| `field_manifest_json` | TEXT | 字段清单（结构见 API-CONTRACT §10.2） |
| `est_tokens` | INTEGER | |
| `redactions_json` | TEXT | 已脱敏项 |
| `status` | TEXT | `pending` / `consumed` / `expired` / `rejected` |
| `consumed_at` | TEXT | 一次性 |
| `expires_at` | TEXT | `created_at + 600s` |
| `created_at` | TEXT | |

### 14.3 LlmCallLog（出网审计，**不含正文**）
`id`, `preview_id`, `provider`, `model`, `endpoint_host`, `field_names_json`（**只有字段名**）, `payload_bytes`, `est_tokens`, `http_status`, `latency_ms`, `ok`, `error_code`, `created_at`。

### 14.4 AppSetting
`key TEXT PK`, `value TEXT`（JSON 标量）, `updated_at`。存 UI 偏好与少量全局配置。**不存 API key**（key 只在 `.env`）。

已约定的 key（其余可自由扩展，但必须走 `PUT /api/v1/settings`）：

| key | 默认值 | 说明 |
|---|---|---|
| `naming_template` | `{position}-{name}-{school}` | 导出文件名模板（解析规则见 API-CONTRACT §9） |
| `default_engine` | `auto` | `auto` / `reportlab` / `chrome` |
| `verify_text` | `true` | 导出后是否做文本层一致性校验 |
| `page_limit` | `1` | 默认页数上限（模板可覆盖） |
| `theme` | `light` | UI 主题 |
| `auto_redact` | `["name","phone","email"]` | 进 payload 前强制脱敏的字段（**不可被 UI 关闭**，只读展示；见 I10） |
| `allow_web_fetch` | `true` | 下行抓取总开关（用户已授权默认开启）；关掉后 `/fetch/public-page` 与公司分析里的抓取一律 403 `EGRESS_BLOCKED` |
| `photo_in_export` | `true` | 导出默认是否带照片（单次导出的 `include_photo` 可覆盖） |
| `last_template_id` | `null` | 上次选中的模板 |
| `trim_courses` | `false` | **课程裁剪开关，默认关**（用户裁决）：`false`=主修课程原文全留；`true` 时按 JD 裁，但必须保留「主修课程：」前缀与 ≥3 门，并把裁剪前后门数写进 `warnings[COURSES_TRIMMED]{before,after}` |
| `max_tokens_analysis` | `2048` | 分析类用途（JD 需求/公司偏好/匹配打分）的输出上限；reasoner 的推理 token 与输出共享此预算，低于 2048 极易烧空（KI-13） |
| `max_tokens_generate` | `900` | 生成类用途（变体生成/改写措辞）的输出上限 |

### 14.5 PublicFetchLog（下行抓取审计，**不含任何用户数据**）

`id TEXT PK`, `host TEXT NOT NULL`, `url TEXT NOT NULL`, `http_status INTEGER`, `bytes INTEGER`, `chars INTEGER`, `from_cache INTEGER CHECK IN (0,1)`, `ok INTEGER`, `error_code TEXT`, `created_at TEXT NOT NULL`.

- 记录**只有 URL 与结果元信息**；请求体恒空，所以这张表结构上不可能含用户数据。
- 与 `LlmCallLog` 分开存：一张是「上行」（可能带用户数据但只记字段名），一张是「下行」（只有公开 URL）。

### 14.6 SchemaMigration
`version INTEGER PK`, `applied_at TEXT`.

---

## 15. 关系与不变量（实现必查）

| # | 不变量 | 检查点 |
|---|---|---|
| I1 | `Package.status='ready'` 前必须有 ≥1 个 `verified=1` 的 variant | DAO 层 |
| I2 | `Template.is_default=1` 全局唯一 | partial unique index |
| I3 | `Slot.block_id` 所属模板与 build 的 `template_id` 一致 | assembler |
| I4 | `BuildSelection.package_id` 必须属于 `status='ready'` 或已在该 build 快照中 | assembler |
| I5 | `llm_preview.status` 只能 `pending → consumed/expired/rejected`，不可逆 | consent service（用 `UPDATE ... WHERE status='pending'` 的受影响行数判定竞态） |
| I6 | `attachment.privacy='private'` 的附件不得出现在 `LlmPreview.payload_json` 中 | consent 构造时断言 + 单测 |
| I7 | 出口文件名 = `BuildArtifact.filename`，且必须以 `data/exports/` 为根 | export service 双重断言 |
| I8 | 同一 build 的同格式重复导出：默认新建 artifact（版本递增），除非 `overwrite=true` | export service |
| I9 | `ResumeBuild.naming_pattern` 中出现的变量必须可解析（见 API §9.3） | 创建/更新/导出前各校验一次 |
| I10 | **姓名/电话/邮箱/照片永不出现在任何 `payload_json`**（学校名允许出现）：构造后必须跑 `assert_no_identity(payload, profile)`，命中即 500 `INTERNAL`（宁可失败也不发） | `llm_payload.build()` 末尾硬断言 + 单测 |
| I11 | **下行抓取请求体必须为空**：`fetch_client` 只传 URL，`fetch_host` 不在白名单即拒；`PublicFetchLog` 中不得出现任何 `user_profile` 字段值 | `fetch_guard` + 静态闸门 |

| I12 | **导入派生包幂等**：`(source_import_job_id, source_entry_temp_id)` 唯一；断言 = 对同一 `import_id` 连续 `commit` 两次且均 `also_create_packages=true`，`SELECT count(*) FROM package WHERE source_import_job_id=?` **第二次不得增加** | DAO 层 + AC-IMPORT-15 |
| I13 | **撤销连带**：`DELETE /imports/{id}` 软删后，该 job 派生的 `package.deleted_at` **必须全部非空**；`restore` 后全部回到 NULL。断言 = 软删后 `SELECT count(*) FROM package WHERE source_import_job_id=? AND deleted_at IS NULL` 为 **0** | DAO 层 + AC-IMPORT-16 |
| I14 | **溯源不断链**：`∀ tmpl: template.deleted_at IS NULL ⇒ 其来源 import_job.deleted_at IS NULL`（即 `result_template_id` 指向的模板活着时，来源行不得被归档/软删）。断言 = 上方 R-c 的 SQL 结果集为空；清理脚本归档前必须执行 | DAO 层 / 清理脚本 + AC-IMPORT-18 |
---

## 16. 真实回归素材（用户本机，含隐私）

| 文件 | 实测 | 用途 |
|---|---|---|
| `data/imports/sample_zh.pdf` | 1 页，1791 字符，85 words，1 张图，Canva 生成，8 种嵌入字体（SourceHanSans/Serif、NotoSans、HelloFont 等），**`(cid:N)` = 0** | 中文模板导入回归（单页密集排版，最难的版面） |
| `data/imports/sample_en.pdf` | 2 页，4965 字符，**`(cid:127)` × 16**（全部为 bullet 行首项目符号），ReportLab 生成，含照片 | 英文模板导入 + 照片处理 + cid 陷阱回归 |
| `data/profile/photo_from_zh_resume.png` | captain 已从中文样张抽出的证件照（原图 266×266，渲染框 89.3×89.3 pt，右上角 `x0=497.1`、距顶 3.8 pt） | 照片链路回归素材（`photo_source=imported`）|

**隐私规则（写入 schema 注释与代码注释；AC-PRIV-01 / AC-PRIV-10 / AC-LOC-05 验证）**
1. `data/**` 下的任何文件、以及 `attachment.privacy='private'` 的内容，**一律不得作为 LLM 输入**；只能由本地解析器（pdfplumber/python-docx）读取。
2. `data/imports/**` 允许作为**导入素材**被本地解析，但解析结果进入模板/包之后，只有用户在 consent 弹窗里**显式勾选**的片段才可能被发送。
3. 这两个文件是开发者本机素材，**不随代码分发**；`data/` 与 `.env` 必须写进 `.gitignore`（见 ARCHITECTURE §5）。
