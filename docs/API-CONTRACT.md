# API-CONTRACT — 前后端唯一联调契约

> **冻结 v1.38**（2026-10-23 09:3x，用户决定「按中文简历内的 GPA 及到岗时间为准，这个可以由用户修改」）：① `SOURCE_CONFLICT` 增**已决议形态**（`severity="info"` + `details.resolved/decided_at`，**只降噪不改值**，移除决议即回 `warn`）→ 新增 **§8.4.1**；② 新增 **`GET`/`PUT /profile/education-facts`**（教育段补充行真源 = `template_block.static_text`，写前**整库 sqlite backup 快照**、单条 UPDATE 事务、失败不改半行；**禁止新增 profile 字段**）——已实测，实现即契约；③ §8.6.1 定 `available_note` 为**唯一渲染真源**（`available_date` 不参与渲染；`available_note_en` 空则回退中文）。
> **冻结 v1.37**（2026-10-23）：① §14.1 新增 **`PACKAGE_SKIPPED`**（`reason ∈ {no_kind_mapping, empty_entry}` 同码两分支，51 → **52**）；② §5.1 新增 **三分支判定表**（顺序写死：先 `kind`→再正文→最后映射建包）与 `T-7`；③ §8 builds：`GET /builds` 增 `include_archived`、`DELETE` 默认改**归档**（硬删须 `?hard=1&confirm=<id>` + 快照）、`PATCH` 增 `archived` 键；新增 `T-8`（归档写入口未接线）；④ §16.1 基线刷新为 `100 / 113 / 0 / 13`。
> **冻结 v1.36**（2026-10-23）：① §6.2.4 新增 **`requirements[].matched_evidence[]`**（`{source: package|skills_json|profile, ref_id|null, quote}`）——技能栏/院校/届别命中此前只能塞进空的 `matched_package_ids`，导致「有证据」与「没匹配到」不可区分；`matched_package_ids` 收窄为**只表示经历包**，「没匹配到」改判据为**两个数组皆空**；② §6.2.5 枚举扩为**四值** `llm|heuristic|local_override|manual` + 优先级 `manual > local_override > heuristic > llm`（修正此前把 `manual` 判为误写的文档错），补「自动链路不得改写 manual 行」「界面须可见标记」「撤销需显式 `auto`」。
> **冻结 v1.35**（2026-10-23）：① 新增 **§6.2 `jd_analyze` 的输入来源与预算**——`fields[].source` 增 **`packages`**（只发包标题/org/role/日期/bullet 文本，禁 `skills_json[].tokens`/变体 id/附件路径/照片），常量 **12 包 / 6000 字符** + `context{packages_included,skipped,chars}`，ConsentModal 与 preview 字段清单必须能逐条列出这 N 条；② `candidate_status_source` 扩为 **`llm | heuristic | local_override`**（本地有证据而模型判 `missing` → 改判 `partial` + `LLM_STATUS_OVERRIDDEN`；**无证据不得改判**）；③ `matched_package_ids` 定为**本地计算、不采信模型**、元素必须指向 `status='ready'`；④ 警告码增 **`PACKAGES_TRUNCATED`/`LLM_STATUS_OVERRIDDEN`/`MATCHED_PACKAGE_NOT_READY`**（48 → **51**）；⑤ `GET /builds` 列表字段边界写死（**不返回 `layout`/`page_count`/`density`**，只 `est_pages`）。
> **冻结 v1.34**（2026-10-23）：① §16.0 新增 **M9**（「从文档数条目」的脚本必须同时接受加粗/不加粗/带反引号三种写法，并以「两种独立数法相等」自校验；事故：`make_index.py` 正则不认加粗行 → 分母 119 vs 真值 152，覆盖率 76% 报成 93%）；② §17.8 登记 **t12 AC harness 抓到的 6 处产品缺陷**（T-1..T-6，均已修，含 `provider=off` 仍发请求→`LLM_DISABLED` 硬拦、405→`METHOD_NOT_ALLOWED`）。
> **冻结 v1.33**（2026-10-23）：① 新增 **§8.6 页眉构成白名单**（只有 `name`/`phone`/`email`/`available_note`，`degree`/`major`/`grad_year`/`city` 一律不得进页眉，`education_line` 字段禁止存在）与 **§8.6.2 教育段日期必须渲染 `date_range` 原文**（不得用 `grad_year` 顶替）；② `variants/generate` 明确 `lang` 语义（`zh|en`，`deepseek-chat`，新变体 `verified=0`，上云按 m00265 脱敏）；③ `LANG_FALLBACK` 增加**逐条清单** `entries[]` 与 `meta.lang_fallback_lines`；④ 补齐两条路由 `PUT /builds/{id}`（`PATCH` 真别名）与 `GET /builds/{id}/selections`（`only_in_code` 97/95/2 → 0）；⑤ `PACKAGE_MISSING` 补 `details{section,heading}` 与 `ir.meta.omitted_sections`。
> **冻结 v1.32**（2026-10-23）：§16.2 白名单行**合并去重**（原文残留「显式非码白名单｜三类」旧行与本轮五类行并存、且旧行计数 20 已过期），并为「白名单命中」补**可复跑的分类统计脚本**与期望值（env 25 / sql 2 / reason 12 / i18n 6 / reportlab 5 = 50）。
> **冻结 v1.31**（2026-10-23）：① §14.1 把 `NAMING_SANITIZED`/`NAMING_TRUNCATED`/`NO_VARIABLE`/`NAMING_COLLISION_SUFFIXED` 那一行**拆成 4 行**（四个独立语义），表头 = **48 条**，口径「一行一条码、无折算」+ **两条判据（行数==48 且 行数==去重码数）**——单条行数判据拦不住合并行；② §16.0 新增 **M7**（跨文件累计数只在真源出现一次）与 **M8**（一格多值的表必须按单元格展开取数，不许 `grep -o` 取首码）；③ §16.2 白名单命中改为**分类可审**（五类各计数）。
> **冻结 v1.30**（2026-10-23）：① §14.1 表头计数**纠错并简化口径**——实测 45 行 = 45 个互不重复的码，删除已失效的「1 行 4 码合并」折算说明（旧的四码合并行早已拆开），口径改为「一行一条码」；② §16.2 `NON_CODE` 白名单扩到**五类**（新增 i18n 词表 key `EDUCATION/EXPERIENCE/INTERNSHIP/PROJECTS/SKILLS/SUMMARY/CAMPUS/HONORS` 与 reportlab 常量 `LEFTPADDING/RIGHTPADDING/TOPPADDING/BOTTOMPADDING/VALIGN`，理由：大写命名的非码标识被正则误捕会让判据天天假红）→ 未登记码 **0**、白名单命中 50。
> **冻结 v1.29**（2026-10-23）：新增 **§8.5 语言契约**（8.5.1 结构词表确定性映射含 7 种 block.kind + 字段标签 + 日期格式；8.5.2 变体按 `lang` 过滤 + `LANG_FALLBACK`；8.5.3 导入必须产出同语言资产 `import_job.source_lang`；8.5.4 **`degree_en`/`major_en` 独立列**而非并入 `profile_fields_source`）+ 警告码新增 2 条 `LANG_FALLBACK`/`LANG_HEADING_UNMAPPED`（**总数以 §14.1 表头为准 = 45；此处不写累计数**，避免与表头漂移）。
> **冻结 v1.28**（2026-10-23）：① 错误码补齐 3 条实现已发漏登（`FETCH_UNREACHABLE`/`NO_DEFAULT_TEMPLATE`/`TIMEOUT`）→ **40 条**；② 警告码增 6 条（`SOURCE_CONFLICT`/`SKILLS_EMPTY`/`TEMPLATE_EMPTY`/`PHOTO_MISSING`/`PACKAGE_MISSING`/`COMPANY_PROFILE_SKIPPED`）→ **46 条**；③ §5.1 增**commit 必须持久化的三类内容**与分层铁律（渲染层/索引层互不反推）；④ `SOURCE_CONFLICT` 触发与不触发条件写清。
> **冻结 v1.27**（2026-10-23）：§5 新增 **清理脚本「产出优先」铁律**（归档前必须按 I14/R-c 过滤；判定 SQL 与 `DATA-MODEL` 同一份；含 `status='committed' AND deleted_at IS NOT NULL` 恒为 0 的监控口径），与 supervisor 的 INT-21/22 共用一条约束，不各写一套。
> **冻结 v1.26**（2026-10-23）：① 新增 **同源条款**（同一 commit 产出的 `template` 与派生 `package` 必须同事务、都能反查回同一 `import_job`，不允许只写一个）；② 新增 **「删导入不删模板」** 规则（`DELETE /imports/{id}` 响应增 `template_retained{kept,template_id,note}`，**禁止隐式级联删模板**——与「派生包随导入联动」是两条方向相反的规则）；③ `DATA-MODEL` 增 **`result_template_id` 生命周期规则 R-a/R-b/R-c** 与不变量 **I14**（溯源不断链，含清理脚本硬校验 SQL）。
> **冻结 v1.25**（2026-10-23）：① 补 3 条路由（`POST /company-profiles` 手动建档 201/409、`DELETE /imports/{id}` **软删可恢复**、`POST /imports/{id}/restore`），`only_in_code` 归零（84/84）；② §16.1 写入**现行基线**（`code_total=84`、`documented_total=111`、`matched=84`、`only_in_code=0`、`only_in_docs=27`）与构成说明；③ §5.1 `commit` 增可选 **`also_create_packages`**（默认 false、幂等键 `source_import_job_id + source_entry_temp_id`、响应 `created_packages[]` 恒在），并定 **`verified` 口径：原文=1 / LLM 改写=0**（理由：原文即事实）。
> **冻结 v1.24**（2026-10-23）：① §16.0 新增 **M5**（跨 agent 指代按内容不按编号：本文档 `D-39` = 门槛动词分组，supervisor 清单 `D-39` = `check_export_pdf.py --right-margin`）与 **M6**（文件头只写版本、不写条目结论）；② §14.1 计数口径改写为 **36 个独立码 + 1 行 4 码合并 = 40**，并写明「计数只作冒烟，判定靠条目」，行数 37 时先查合并写法。
> **冻结 v1.23**（2026-10-23）：① §2 补 **health 响应体路径**（业务字段全在 `data` 下；按顶层取 `port`/`llm_ready`/`build` 得 `null` 是取错层，不是字段丢失；`db.schema_version` 非契约常量）；② §17.8 登记 **D-41**（并列档位截断，04:17:29 修复）、**D-42**（门槛不匹配时 `gap_notes` 为空，04:17:29 修复），并新增 **§17.8.2 院校信号缺陷族**（D-39/41/42 同源同害，**保留为回归判据，不得回退**）。
> **冻结 v1.22**（2026-10-23）：§7 门槛动词分组与并列档位**实测转绿**——`detect_school_gate`（mtime `04:17:29`）10/10 用例符合契约（`优先` → `hard_filter=false`；`仅限 985/211` → `threshold="985/211"` + `["985","211"]`；`、`/`和` 两种并列写法等价）。§17.8 缺陷 **#8 标记已修复**并保留为回归判据（AC-ANL-12）。
> **冻结 v1.21**（2026-10-23）：① §7 新增 **门槛动词分组定版**（硬 `仅限/必须/要求…` / 软 `优先/更佳/加分…` / 明确负向；优先级 **负向 > 硬 > 软**），并给出 **8 行参数化用例表**（AC-ANL-11/12 逐行断言）；② 与实现实测对齐：`985/211 院校优先` → `hard_filter=false` + `["985","211"]` + `不限（偏好 985/211）`（D-39 **已修复 04:15:24**，记录于 §17.8）；③ 新增实现缺陷 **#8 并列档位截断**（`仅限 985/211` 只回 `["985"]`，P1 归 coder）。
> **冻结 v1.20**（2026-10-23）：① 修复 **§14 错误码表表头丢失**（分隔行上方只剩说明块，整表无表头）与 **`IMPORT_DRAFT_PRUNED` 行多一格**（D-40）；② **§16.0 M3 自检脚本升级**：空行分隔的续行块沿用上一张表列数（旧版漏检，D-40 即因此漏了 3 版）；全库 mismatch **0**。
> **冻结 v1.20**（2026-10-23）：① 修复 **§14 错误码表表头丢失**（分隔行上方只剩说明块，整表无表头）与 **`IMPORT_DRAFT_PRUNED` 行多一格**（D-40）；② **§16.0 M3 自检脚本升级**：空行分隔的续行块沿用上一张表列数（旧版漏检，D-40 即因此漏了 3 版）；全库 mismatch **0**。
> **冻结 v1.19**（2026-10-23）：① 新增 **§16.0 元规则 M1–M4**（判据自身的纪律）：**M1 码位以实现为准、文档不得先行登记实现里不存在的码**（与 §16.2「实现发的码必须登记」成对）；**M2 任何「现状是 X」必须附 mtime/git hash/实跑输出**；**M3 表格必须是矩形**（附可跑自检脚本，当前 mismatch **0**）；**M4 自报行数一律用 `wc -l`**；② 修复 5 处表格列数缺陷（`|` 转义与反引号内 `|` 之前被误当分隔符，导致按列解析错位）。
> **冻结 v1.18**（2026-10-23）：① §6.1 补 **`recognized`** 字段与「院校层次未识别」语义（D-37/ANL-09：未收录 ≠ 普通本科 → `其他` + `recognized:false`，且不得据此给负面结论）；② §7 补 **`preferred_tiers` 非硬门槛偏好**语义（D-37/ANL-10：`hard_filter=false` 时允许且应当非空、`threshold` 须以「不限」开头且含「偏好」、JD 无院校词时必须为空）；③ §8.4 写明 export `warnings[]` 的**三段来源与合并顺序**；④ §14.1 新增 `PAGE_FIT_DOWNGRADED`/`PAGE_OVERFLOW_TWO_PAGES`（单页降档，D-38）并按实现补登 7 条降级码，总数 →**40**；白名单同步；⑤ §8.4 export 增 **`density`** 参数（默认 `"original"`，回显 `layout{}`），ADR-21。
> **冻结 v1.17**（2026-10-23）：① 新增 **§17 已实现端点补充契约**（按代码登记 39 条：Package 族、Template 族、LLM 补充、Job、File、Import 列表、杂项），并列出 **7 条实测口径偏差**（已改文档 4 条、报 coder 3 条）；② **§16.1 三数标 `PENDING(canonical-script)`**——路由一致性改由 coder 交付的 `scripts/check_route_parity.py` 唯一定义，三人跑同脚本 JSON 逐字节相同才算达标；③ 全文档**一格一路由**改净（方法单元格与路径单元格均不得合写）；④ **D-33 闭环**：§14.1 截断旧注改为四行分工表；⑤ 新增错误码 **`FILE_IN_USE`**(409, 36→37) 与 `details.reason` `NO_DEFAULT_TEMPLATE`/`MULTIPLE_DEFAULT_TEMPLATES`；⑥ §5.2 定义 **无默认模板时 assemble 必须拒绝**（不静默取最新）。
> **冻结 v1.15**（2026-10-23）：① 按实现补登 **10 条从未登记的警告码**（§14.1，总数 20→30；`OUTPUT_TRUNCATED` 恢复登记并在 §14.1 写明与 `LLM_TRUNCATED` 的分工）；② `DELETE /profile/photo` 六字段响应表落定（不是 204）；③ 新增 **§16 文档—实现一致性判据**（路由双向 + 码位，含当前基线）；④ 补 **`DATA_DIR` 必须位于 `data/` 内**的机器强制约束。
> **冻结 v1.14**（2026-10-23）：照片路由按代码三行表重写（`POST`/`PUT`/`DELETE /profile/photo`，删掉代码里从未注册的独立确认子路径）；`DELETE` 已实现为 **200 + `previous_photo_path`/`previous_attachment_id`/`restore_endpoint`**（可撤销）；`PUT` 的 `attachment_id`/`sha256` 互斥；`/health.build` 为四键对象；新增警告码 **`IMPORT_FALLBACK_LLM`**（19→20）。
> **冻结 v1.13**（2026-10-23）：`/health` 增 **`build`**（D-27，进程是否当前代码的唯一判据）+ `started_at`；§5.1 `job_id` 定为**必需**（同源 `import_parse` 审计记录）；新增警告码 **`PHOTO_DECODE_FAILED`** 与不变量「`available=true` 必须有 `attachment_id`」（warnings 18→19）。
> **冻结 v1.12**（2026-10-23，IMPORT lane）：§5.1 上传语义定版为 **201 + 内联 `draft`**（取消 202/job 轮询；`ImportJob` 降为历史与审计）；**`blocks` 为草稿唯一真值源**，`sections[]`/`section_kinds`/`entry_counts`/`skills` 为服务端派生（`sections[] = {kind, heading, entry_count}`，`heading` 必须同源，D-25）；登记 `quality` 四字段语义（含 `numbers_second_pass`，旧名 `numbers_lost_unknown` 废弃）；`PHOTO_DETECTED` 补 `severity="warn"` + `details{attachment_id,sha256,width,height}` 与「只产出候选」（D-23）。
> **冻结 v1.11**（2026-10-23）。v1.11（D-19）：§6.1 新增 `competitiveness` 契约（校名必须被消费，ADR-20）、`requirements[].candidate_status`；§7 增 `school_preference` + `hiring_preferences` 四项必答项与反编造要求；§8.1.1 增 `builds/suggest` 的 `competitiveness_summary`/`school_signal_used`；§14.1 增三条警告码。
> **冻结 v1.10**（2026-10-23）。v1.10：`GET /profile` 增 `skills_json`（逐行原文 + 派生 `tokens`，ADR-19）；§14.1 新增警告码 `COURSES_TRIMMED`（`trim_courses=true` 且发生裁剪时产生）。
> **冻结 v1.9**（2026-10-23）。v1.9：§11 `app_port`/`app_url` 指向 ARCHITECTURE §3.3 的**冻结 JSON 五字段**契约（`port/host/url/pid/started_at`，原子写入，消费者一律 `json["port"]`，禁止当纯数字解析）。
> **冻结 v1.8**（2026-10-23）。v1.8：§14/§14.1 表头写入**可机械复算的计数口径**（36 / 14 及各一条验证命令），供 t11 直接跑。
> **冻结 v1.7**（2026-10-23）。v1.1–v1.6 逐版变更见 §15 变更记录；错误码全表 36 条、warnings 码表 14 条为当前基线。前端（uier）与后端（builder）**只能**按本文件对接；任何字段改名/语义变更必须先改本文件并通知双方。
> 数据形态以 `docs/DATA-MODEL.md` 为准；错误码全表见 §14，命名模板规则见 §9，LLM 字段清单见 §10.2。

---

## 1. 通则

| 项 | 约定 |
|---|---|
| Base URL | `http://127.0.0.1:8765`（端口可能顺延，真实端口由 `data/runtime.json` 与 UI 顶部显示；**不要硬编码**，前端读 `window.__APP_CONFIG__.apiBase`） |
| API 前缀 | `/api/v1` |
| 编码 | 请求/响应统一 `application/json; charset=utf-8`；`ensure_ascii=false`（中文原样，不转 `\uXXXX`） |
| 上传 | `multipart/form-data`，字段名 `file`，单文件 ≤ 20 MB |
| 认证 | **无**。仅监听 `127.0.0.1`，不开放局域网。若未来需要，走 `X-Local-Token`（本期不做） |
| CORS | 关闭。前端与 API 同源（由 Flask 托管静态资源） |
| 幂等 | `POST` 创建类端点支持 `Idempotency-Key` 头（10 分钟内同 key 返回同一资源，`Idempotency-Replayed: true`） |
| 请求追踪 | 响应恒带 `X-Request-Id`（服务端生成，或在请求未带时生成；客户端可主动传） |
| 时间 | 响应内所有时间为 ISO-8601 带偏移，如 `2026-10-23T02:41:00+08:00` |
| 分页 | 列表端点：`?limit=1..100`（默认 20）、`?cursor=<opaque>`；响应 `data.items[]` + `data.next_cursor`（无更多为 `null`）。**不用 offset 分页** |
| 排序 | `?sort=` 白名单：`updated_desc`(默认) / `created_desc` / `title_asc` / `relevance`（仅搜索） |
| 布尔 | JSON `true/false`（DB 内是 0/1，出库转换） |
| 空值 | 缺省字段用 `null`，不省略键（前端可依赖键存在） |

### 1.1 成功响应信封

```json
{ "ok": true, "data": { }, "request_id": "req_01J9Z3K2" }
```

列表：

```json
{ "ok": true, "data": { "items": [], "next_cursor": null, "total_estimate": 12 }, "request_id": "req_01J9Z3K2" }
```

### 1.2 错误响应信封

```json
{
  "ok": false,
  "error": {
    "code": "NAMING_MISSING_VAR",
    "message": "命名模板缺少变量值：{school}（UserProfile.school_zh 为空）",
    "details": { "missing_vars": ["school"], "pattern": "{position}-{name}-{school}" },
    "hint": "请在「个人信息」里填写中文学学校，或在命名覆盖里指定 school"
  },
  "request_id": "req_01J9Z3K2"
}
```

- `code` 是**机器可判定**的稳定标识（前端按 code 分支，不解析 message）。
- `message` 是中文人话，可直接展示。
- `details` 结构按 code 定义（§14）。
- `hint` 可选，给出可执行的下一步。
- **500 响应永不包含 traceback**。

### 1.3 状态码使用

| 码 | 语义 |
|---|---|
| 200 | 成功（含「校验不通过但已计算」的纯函数端点，见 §9.2） |
| 201 | 创建成功，带 `Location` 头 |
| 202 | 已受理长任务，`data.job_id` |
| 204 | 删除成功，无 body |
| 400 | 请求本身不合法（如路径穿越） |
| 403 | 出网被策略拒绝（`EGRESS_BLOCKED`） |
| 404 | 资源不存在 |
| 409 | 冲突/状态非法（重复、一次性令牌已用、任务在跑） |
| 410 | 已过期（consent 预览） |
| 413 | 文件过大 |
| 415 | 媒体类型不支持 |
| 422 | 语义校验失败（字段值、命名、槽位） |
| 428 | 需要先完成 consent 预览 |
| 429 | 上游限流 |
| 500 | 服务端错误（渲染/存储/字体） |
| 502 / 504 | 上游 LLM 异常 / 超时 |
| 503 | LLM 不可用（未配置/已关闭） |

---

### `DATA_DIR` 约束（本地落盘硬边界）

`DATA_DIR` 被 `server/app/db.py:40-55` 强制约束在 `resume-warehouse/data/` **之内**：解析后若不在该目录内（包括指向 `tmp/`、项目根、绝对路径越界），直接抛
`RuntimeError: DATA_DIR 必须位于 <...>/data 之内，实际解析为 <...>（拒绝在项目外落盘）`。

- **临时/测试库只能写 `data/.tmp_xxx/`**（例 `DATA_DIR=data/.tmp_del`），**不能写 `tmp/`**——后者会直接启动失败。
- 与 §5 的隐私边界同源：这条是「数据只落本地」的**机器强制**版本，不是约定。

## 2. 健康与环境

### `GET /api/v1/health`
```json
{ "ok": true, "data": { "status": "ok", "uptime_s": 3.9, "port": 8799,
  "db": { "ok": true, "path": ".../data/app.db", "schema_version": 5 },
  "llm_ready": true, "version": "1.0.0",
  "build": { "id": "b8c335e-dirty", "git_head": "b8c335e", "git_dirty": true, "source": "src-b84125d32182" },
  "time": "2026-10-23T03:46:53+08:00", "warnings": [] }, "request_id": "..." }
```

**响应体路径（极易误判，v1.23 补）**：**所有业务字段都在 `data` 之下**，顶层只有 `ok` 与 `request_id`。按顶层取 `port` / `llm_ready` / `build` 会**全部得到 `null`**，看起来像「字段丢了」，实际是取错层。正确写法：`health.data.port`、`health.data.llm_ready`、`health.data.build.id`、`health.data.db.schema_version`。判据脚本请一律用这个路径（captain 2026-10-23 因取顶层差点误报回归）。`data.db.schema_version` 是**数据相关值**（当时实测 5），迁移后会变，**不作契约常量**，只作「实例是否同一份库」的旁证。

**实测校正（v1.16）**：`data.db` 是**对象**（`ok`/`path`/`schema_version`），不是 `"ok"` 字符串；时间字段是 **`data.time`**（响应时刻），**不是** `started_at`（进程启动时刻另有其值）；另有 `data.llm_ready` 与 `data.version`。前端不得按旧示例解析。

**`build` 是「进程跑的到底是不是当前代码」的唯一判据（D-27），结构固定为四键对象**（`server/app/buildinfo.py:build_info()`）：

| 键 | 类型 | 含义 |
|---|---|---|
| `id` | str | **判据本体**：有 git 时为 `"<short-sha>"` 或 `"<short-sha>-dirty"`；无 git 时为源码指纹 `"src-<12位>"` |
| `git_head` | str \| null | `git rev-parse --short HEAD`；无 git 为 `null` |
| `git_dirty` | bool \| null | 工作区是否有未提交改动；无 git 为 `null` |
| `source` | str | 源码指纹 `src-<sha256 前 12 位>`（对 `server/app/**/*.py` 的 `(相对路径, mtime_ns, size)` 排序后取摘要，改一行即变） |

实测样例：`{"id":"b8c335e-dirty","git_head":"b8c335e","git_dirty":true,"source":"src-92d5c1a4f0b3"}`。**行为验证前核对 `build.id` 与当前 `git rev-parse --short HEAD`（或重启后是否变化）**。Python **不热重载**，改了代码但没重启的进程会继续回旧行为——实测过一次「拿旧进程验 job_id/PHOTO_DETECTED，得出两者都缺失」的错误结论，差点误判实现。

- 行为验证/回归**必须**先 `curl /health` 核对 `build.id` 与当前 `git rev-parse --short HEAD` 一致（`-dirty` 后缀不影响判定）；不一致先重启，**不得**用旧进程的结论判定代码。
- `/env` 的 `build` 必须与 `/health.data.build` **逐键等值**（同一进程内 `lru_cache` 计算一次）。

### `GET /api/v1/env`
启动体检报告（`data/logs/preflight.json` 的对外版本）。UI 首次加载必调，用于顶部状态条。
```json
{ "ok": true, "data": {
  "python": "3.13.9", "venv": ".venv", "system_site_packages": true,
  "packages": { "flask": "3.1.0", "reportlab": "4.5.1", "pydantic": "2.12.4", "jinja2": "3.1.6",
                "httpx": "0.28.1", "pdfplumber": "0.11.9", "pypdf": "6.9.2", "python-docx": "1.2.0" },
  "missing_packages": [],
  "fonts": { "primary": "STSongti-SC-Regular", "bold": "STSongti-SC-Bold", "ok": true,
             "chain": ["/System/Library/Fonts/Supplemental/Songti.ttc#6", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"] },
  "render": { "pdf_primary": "reportlab", "pdf_fallback": "chrome", "chrome_available": true,
              "soffice_available": false, "weasyprint_available": false },
  "llm": { "provider": "deepseek", "model": "deepseek-chat", "key_set": true,
           "reachable": null, "ready": true, "last_check_at": null },
  "paths": { "data_root": ".../resume-warehouse/data", "db": ".../data/app.db", "writable": true },
  "warnings": []
}, "request_id": "..." }
```

---

## 3. UserProfile（单例）

### `GET /api/v1/profile`
```json
{ "ok": true, "data": {
  "id": "me", "name_zh": "张三", "name_en": "SAN ZHANG",
  "school_zh": "示例大学", "school_en": "Example University",
  "degree": "本科", "major": "管理科学（商业数据分析）", "grad_year": 2028,
  "phone": "13800000000", "email": "you@example.com",
  "city": "武汉", "available_date": null, "available_note": "2027年1月下旬",
  "photo_path": "files/ab/abcdef....png",
  "skills_json": [
    { "line": "数据分析类：掌握Python、R、SQL等编程语言，可独立进行数据清洗、统计分析与可视化处理",
      "category": "数据分析类", "tokens": ["python","r","sql","数据清洗","统计分析","可视化"], "order": 10 }
  ],
  "links_json": [{ "label": "GitHub", "url": "https://github.com/xxx" }],
  "extra_json": {},
  "completeness": 0.83,
  "missing": ["school_en", "city"],
  "updated_at": "2026-10-23T02:41:00+08:00"
}, "request_id": "..." }
```

### `PUT /api/v1/profile`
部分更新（未出现的键不改；显式 `null` 清空）。`id` 不可改。
- 校验：`name_zh` 必填；`phone` 匹配 `^\+?[0-9\- ]{7,20}$`；`email` 需含 `@` 与 `.`；`grad_year` 1900–2100。
- 失败：`VALIDATION_ERROR` + `details.fields[{field,rule,message}]`。
- **响应绝不回显 API key**（与 profile 无关，但同一套脱敏器）。

### 教育段补充行：`GET` / `PUT /api/v1/profile/education-facts`（**实现即契约，2026-10-23 09:2x 实测**）

> 这一对端点的存在理由是：**GPA / 主修课程这类「教育段补充行」的真源是 `template_block.static_text`，`user_profile` 里没有 `gpa`/`score`/`courses` 字段，也不得新增。** 形态是 用户原文的整段文字（全角标点、括号内分数、`CET4：562` 这种混排），一旦结构化进 profile 就要再定义一遍格式与渲染规则，还会与导入回填（`profile_fields_source`）打架——**一个真源，两个入口（读/写）**。

| 方法 | 路径 | 语义 | 响应/失败 |
|---|---|---|---|
| `GET` | `/profile/education-facts` | 读默认模板 `education` 条目的补充行（`static_text` 按行切分、去空行）。**没有模板时不报错**，返回全 `null`/`[]` | `200 {template_id, template_name, block_id, lines[], updated_at}`；无模板 → `{template_id:null, template_name:null, block_id:null, lines:[], updated_at:null}` |
| `PUT` | `/profile/education-facts` | 用 `lines` **整体替换**该块 `static_text`（`"\n".join(lines)`）；**`[]` = 清空**（写 `NULL`，合法不是错误） | `200` 为 `GET` 同形 + `snapshot{path,md5}` + `saved:true` |

**请求体与上限（`server/app/models.py:133 EducationFactsIn` + `services/education_facts.py:29/31`）**：`{"lines": ["…", "…"]}`；`lines` **≤ 12 项**（pydantic `max_length=12`）、每行 **≤ 400 字符**（`MAX_LINE_CHARS`）；空数组合法。

| 失败 | 码 | 触发 |
|---|---|---|
| `422` | `VALIDATION_ERROR` `details.fields[{field:"lines", rule:"too_long"}]` | `lines` 超过 12 项（实测报文含 `List should have at most 12 items after validation, not 13`） |
| `409` | `NO_DEFAULT_TEMPLATE` `details{candidates:[], count:0}` + hint「先导入一份简历生成模板」 | 库里还没有任何模板（实测） |
| `422` | `TEMPLATE_INVALID` `details{template_id, template_name}` + hint「重新导入…或确认教育段是否完整」 | 默认模板里没有 `education` 条目——**不许自动建块**（在用户不知情时改变版式） |

**写前快照（实现即契约）**：写之前用 **sqlite backup API**（不是 `cp`，WAL 未 checkpoint 时会少事务）把整库备份到 `data/runtime/app.db.pre_edu_<stamp>`，响应里回 `snapshot{path, md5}`。**不是** `job` 记录、也**不是**逐行 undo——审计口径是「文件级快照 + md5」，与 `data/backups/` 的既有做法一致。

**事务与「不改半行」**：`_validate()` 在任何写库之前完成；真正的写入是**单条 UPDATE + 单事务**，失败即整条回滚，不存在「写了前两行」。

### 照片端点（`photo_source` 决定来源）

**路由以代码为准（v1.14 校正）**：照片只有三条路由，全部挂在 `/profile/photo` 上（`POST` 上传 / `PUT` 确认 / `DELETE` 清除）；另有一个只读的 `GET /files/profile-photo` 取字节。文档此前写过一个独立的「确认候选」子路径，**代码里从未注册**，已删除（见 §15 变更记录）。

| 方法 | 路径 | body | 语义 | 实测 |
|---|---|---|---|---|
| `POST` | `/profile/photo` | multipart `file` | **上传**新照片（`png/jpg/webp`，≤5 MB），落 `data/profile/photo_<sha256>.<ext>`，写 `photo_path` + `photo_source="manual"`，并建一条 `kind="photo"` 的 attachment 供复用 | 缺 `file` → `422 VALIDATION_ERROR`「缺少上传文件字段 file」 |
| `PUT` | `/profile/photo` | JSON `{attachment_id}` **或** `{sha256}` | **确认**使用一张**已入库**的照片（导入候选或此前上传的）；确认语义**恒置** `photo_source="imported"`（手动上传走 `POST` → `manual`） | 字段非法 → `422` |
| `DELETE` | `/profile/photo` | 无 | **清除**当前照片引用；回 **`200`** 六字段对象（见下）；幂等：再删时 `previous_photo_path=null` | 实测回 200 + `{"ok":true,"data":{...}}`（`server/app/api/profile.py:116-143`） |
| `GET` | `/files/profile-photo` | 无 | 返回图片字节（`image/png`/`image/jpeg`）；与 `GET /profile` 分开，避免二进制塞进 JSON | 无照片 → `404` |

**`PUT` 的字段互斥（实现即契约，`server/app/models.py:PhotoConfirmIn`）**：`attachment_id` 与 `sha256` **必须且只能提供一个**；两个都给或都不给 → `422 VALIDATION_ERROR`。附件不存在 → `404 NOT_FOUND`；附件 `kind != "photo"` → `422`（`details.fields[].rule="kind=photo"`）。成功回 `{photo_path, photo_source, attachment_id, sha256, bytes, confirmed:true}`。

**`DELETE` 只清引用，不删文件（高危操作保护）**：只置 `photo_path=null` 并清 `photo_source` / `photo_attachment_id`；**照片文件按内容寻址保留**（`data/profile/photo_<sha256>.<ext>`，可能被其它记录复用——同内容复用是上传侧的既有约定）。

**`DELETE` 响应体（200，六字段，实现即契约）**：删照片是「用户点错就丢设置」的高危操作，前端要拿到原路径与恢复方式才能提示「已移除 · 撤销」。

| 字段 | 类型 | 说明 |
|---|---|---|
| `cleared` | bool | 恒 `true`；幂等重删也是 `true`（`previous_photo_path` 为 `null`） |
| `previous_photo_path` | str \| null | 删除前的 `photo_path`（如 `profile/photo_7f7cf27d1307694c.png`）；本次本无照片则为 `null` |
| `previous_attachment_id` | str \| null | 删除前绑定的 `kind="photo"` 附件 id；**撤销就用它** |
| `photo_url` | null | 恒 `null`（UI 据此清空 `<img src>`，不需要再查一次） |
| `note` | str | 人读说明：「照片已从简历解绑；文件保留在 `data/profile/` 以便撤销」 |
| `restore_endpoint` | str | 恒 `"PUT /api/v1/profile/photo"`；撤销 = 用 `previous_attachment_id`（或原 `sha256`）再 `PUT` 一次 |

- **文件不删**：照片按内容寻址、可能被多处引用；孤儿清理走 `scripts/clean_orphan_photos.py`，不在本端点内做。
- **不是 204**：任何实现改动都必须保持「200 + 上述六字段」，否则撤销能力丢失（AC-PHOTO-05 已按此写，P0 不降级）。

> 唯一例外：`POST` 上传时若同名内容文件已存在（同 `sha256`）则复用、不覆盖。
- `GET /profile` 的 `data` 增：`photo_source`（`manual\|imported\|none`）、`has_photo`(bool)、`photo{width,height,bytes,sha256}`（无照片时为 `null`）。
- **照片字节永不进任何 LLM payload**（§10.2.1）；导出时是否渲染由 `app_setting.photo_in_export`（默认 `true`）与单次导出的 `include_photo` 参数共同决定。

---

## 4. Package 与 Variant

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/packages` | `?q=` FTS 搜索、`?kind=`、`?status=`、`?tag=`、`?org=`、分页 |
| `POST` | `/packages` | 创建，201 |
| `GET` | `/packages/{id}` | 含 variants（可 `?include=variants` 才带，默认不带） |
| `PATCH` | `/packages/{id}` | 部分更新 |
| `DELETE` | `/packages/{id}` | 软删除，204 |
| `POST` | `/packages/{id}/restore` | 恢复软删除，200 |
| `POST` | `/packages/{id}/duplicate` | 复制为新草稿，201 |
| `GET` | `/packages/{id}/variants` | 该包全部变体，按 `bullet_key,tone` |
| `POST` | `/packages/{id}/variants` | 新建变体，201 |
| `PATCH` | `/variants/{id}` | 改 text/tone/verified |
| `DELETE` | `/variants/{id}` | 204 |
| `POST` | `/packages/{id}/variants/generate` | **LLM 生成变体**（需先 preview），202 → `job_id` |

### `POST /api/v1/packages` 请求
```json
{
  "title": "订单中台重构", "kind": "project",
  "org": "某某科技有限公司", "role": "后端开发实习生",
  "start_date": "2025-06", "end_date": "2025-09", "is_current": false,
  "location": "武汉", "summary": "主导订单中台服务拆分与可观测性建设",
  "tech_stack_json": ["Python", "Go", "PostgreSQL", "Kubernetes"],
  "tags_json": ["分布式", "可观测性"], 
  "outcomes_json": [{ "metric": "QPS", "from": "1.2k", "to": "8.5k" }],
  "variants": [
    { "bullet_key": "b1", "tone": "impact", "lang": "zh",
      "text": "重构订单中台读写链路，QPS 由 1.2k 提升至 8.5k，P99 延迟下降 62%",
      "keywords_json": ["高并发", "性能优化"], "verified": true }
  ]
}
```
响应 201：完整对象 + `variants[]`。
校验：`is_current=true` 时 `end_date` 必须为 `null`（`VALIDATION_ERROR`）。

### `POST /api/v1/packages/{id}/variants/generate`
请求：
```json
{
  "preview_id": "pv_01J9Z...",          // ← 必填，见 §10.1
  "bullet_keys": ["b1", "b3"],           // 只对这几条生成
  "tones": ["impact", "technical", "ats"],
  "lang": "en",                          // zh | en（v1.33 明确：生成英文变体传 "en"）
  "constraints": { "max_chars": 120, "no_fabrication": true }
}
```
响应 202：`{"ok":true,"data":{"job_id":"job_...","expected_variants":6,"lang":"en"}}`。

**语言与合规（v1.33）**：`lang` 决定生成语言与落库 `variant.lang`（`zh` 用 `deepseek-chat`，`en` 同样走 `deepseek-chat`）。**上云范围仍按 m00265**：姓名/电话/邮箱/证件照**不参与**（见 §10.2.1 脱敏）；新变体一律 **`verified=false`**、`llm_generated=1`，进校对页待确认后才可被导出选用。
任务完成后 `GET /jobs/{id}` → `result_json.variants[]`（**不自动入库**；由前端展示、用户逐条确认后调 `POST /packages/{id}/variants` 落库，`llm_generated=1`、`verified=0`）。

---

## 5. 导入 → 模板 → 区块 → 槽位

### 5.1 Import

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/imports` | multipart 上传简历，**201 → `{import_id, draft, sections, quality, needs_llm_fallback, warnings, extracted_photo}`（同步内联，不轮询）** |
| `GET` | `/imports/{id}` | **可选的历史查询**（审计/回看用），不是状态轮询通道 |
| `GET` | `/imports/{id}/draft` | 解析出的 blocks/slots 草稿（可编辑的 JSON） |
| `PUT` | `/imports/{id}/draft` | 保存用户对草稿的修改 |
| `POST` | `/imports/{id}/commit` | 落库成 Template，201 |
| `GET` | `/imports` | 历史列表 |

**（v1.12 定版）上传是同步语义**：本地解析单页 PDF 约 200 ms，`202 + job 轮询` 是为远端异步任务设计的，在这里只换来一个 job 状态机和一个轮询 UI，收益为零。因此：

- **成功码 201**，响应体内联 `draft`（完整草稿，可直接喂校对页），**没有** `202`/`queued` 中间态；
- `needs_llm_fallback=true` 只**打标返回**：请求内**不触发任何 LLM 调用**（`llm_call_log` 应无新增行、`LlmPreview` 不产生）；转不转 LLM 由用户在草稿页显式点按钮决定；
- 响应体**同时含 `import_id` 与 `job_id`（均为必需，同源）**，并内联 `draft`。`job_id` 指向一条**已 `succeeded`** 的 `import_parse` 审计记录（`Job.result.import_id` 必须等于响应里的 `import_id`）；它的用途是**审计/追溯**，客户端**不得**依赖轮询它（`GET /jobs/{id}` 只是可选的历史查询）。实测样例：`job_id="01a1652059637461b9ce53034f4f7d17"`。
- `ImportJob` 的定位是「**历史与审计记录，不承担轮询职责**」（`status ∈ draft/committed/failed`，`draft`/`committed` 在同一次请求或下一次 commit 内到达）；
- 若客户端实现了 `GET /imports/{id}` 轮询，它读到的只是已落库的同一份草稿——**不得**把「等 status 变化」写成必需流程。

**`blocks` 是草稿的唯一真值源（D-25）**。`sections[]` 是**派生摘要**，只允许由 `blocks` 计算，字段固定为 `{kind, heading, entry_count}`（实现另有 `block_type`/`bound_package_kind` 供渲染，属**只读派生**）：

- `heading` **必须等于**对应 section block 的 `heading`（同源，否则双真值源必然漂移）；
- 用户编辑 `PUT /imports/{id}/draft` 时只改 `blocks`，`sections[]`/`section_kinds`/`entry_counts`/`skills` **由服务端重算**，客户端提交的这三个字段一律忽略（不报错，直接覆盖）；
- 任何 `sections[]` 与 `blocks` 不一致的响应都算实现缺陷（验收 AC-IMPORT-11）。

**`quality` 字段语义（草稿质量，供校对页提示，不参与渲染）**：

| 键 | 类型 | 语义 |
|---|---|---|
| `sections_found` | int | 识别出的 section 种类数 |
| `cid_residual` | int | 兜底替换后仍残留的 `(cid:N)` 数，**期望 0** |
| `replacement_chars` | int | 被替换/清理的字符数 |
| `numbers_second_pass` | bool | **仅表示「未做二次数字核对」**：导入阶段禁止润色，原文逐字保留，故恒为 `false`。语义是「数字未经第二遍校验」而不是「数字丢了」；旧名 `numbers_lost_unknown` 已废弃，实现按 `numbers_second_pass` 写即可 |

`POST /imports` 校验：扩展名 ∈ `pdf/docx/md/txt/html` **且** magic bytes 匹配（`%PDF` / `PK\x03\x04`）。失败 `UNSUPPORTED_MEDIA_TYPE`(415) / `IMPORT_UNSUPPORTED`(422)。
扫描件无文本层（提取字符 < 20）→ `IMPORT_NO_TEXT_LAYER`(422)，`details.chars_extracted`。

`GET /imports/{id}/draft` 响应片段（**这是 uier 校对页的数据源**）：
```json
{ "ok": true, "data": {
  "import_id": "imp_01J9Z...", "status": "draft", "parser": "pdf",
  "stats": { "pages": 2, "chars": 4965, "words": 635, "images": 1, "cid_missing": 16 },
  "extracted_photo": {
    "available": true, "source": "embedded_image",
    "file": "data/profile/candidate_imp_01J9Z.png",
    "width": 266, "height": 266,
    "rendered": { "page": 1, "w_pt": 89.3, "h_pt": 89.3, "x0_pt": 497.1, "top_offset_pt": 3.8 },
    "probable_kind": "id_photo", "applied": false },
  "warnings": [
    { "code": "CID_GLYPH_MISSING", "count": 16,
      "message": "已将 16 处 (cid:127) 项目符号还原为列表项", "severity": "info" },
    { "code": "PHOTO_DETECTED", "count": 1, "severity": "warn",
      "message": "检测到 1 张图片（疑似证件照），已提取为候选，需你确认后才写入 profile",
      "details": { "attachment_id": "att_01J9Z...", "sha256": "9f2c…", "width": 266, "height": 266 } }
  ],
  "blocks": [
    { "temp_id": "tb1", "parent_temp_id": null, "order_index": 10, "block_type": "header",
      "heading": null, "confidence": 0.92,
      "preview_text": "SAN ZHANG",
      "slots": [
        { "slot_key": "candidate.name", "slot_type": "text", "bound_field": "profile.name_en",
          "suggested_value": "SAN ZHANG", "required": true },
        { "slot_key": "candidate.phone", "slot_type": "text", "bound_field": "profile.phone",
          "suggested_value": "+86 138-0000-0000", "required": true }
      ] },
    { "temp_id": "tb5", "parent_temp_id": "tb2", "order_index": 20, "block_type": "bullet_list",
      "heading": null, "confidence": 0.78,
      "preview_text": "• CET-4: 562 | CET-6: 508",
      "slots": [{ "slot_key": "package.bullets", "slot_type": "computed",
                  "bound_field": "package.bullets", "required": false }] }
  ]
}, "request_id": "..." }
```
`confidence < 0.6` 的 block 前端标黄，要求用户确认。

**`extracted_photo` 与 `PHOTO_DETECTED` 的语义（D-23 的契约依据）**：导入只**产出候选**——`extracted_photo.applied` 必须为 `false`，`user_profile.photo_path` **不得**被导入流程写入。用户在校对页点「用作证件照」后，由 `PUT /api/v1/profile/photo` 显式落库（`photo_source="imported"`）。因此：

- `PHOTO_DETECTED` 必发（只要识别到内嵌图），`severity="warn"`，`details` 至少含 `attachment_id` / `sha256` / `width` / `height`；
- **不变量（v1.12）**：`extracted_photo.available === true` **必须**带非空 `attachment_id`。解码失败（如裸 `/FlateDecode` raw RGB 像素，PIL 无法识别）时**必须**同时满足：`available=false`（或字段整体为 `null`）、`warnings[]` 含 **`PHOTO_DECODE_FAILED`**、`extracted_photo.reason` 写明失败原因（如 `raw_pixels_undecodable`）。**禁止**出现「可选却点不动」的候选：`available=true` 且无 `attachment_id` 属实现缺陷（AC-IMPORT-14 专测）。
- 「上传即 `applied=true` 并写 `photo_path`」**违反契约**（对照验收 AC-IMPORT-03）。

`POST /imports/{id}/commit` 请求（**v1.25 增可选 `also_create_packages`**）：
```json
{ "template_name": "英文-双页-含照片", "lang": "en", "page_limit": 2,
  "set_default": false, "layout_json": { "paper": "A4", "columns": 1 },
  "also_create_packages": false }
```

**`also_create_packages`（v1.25 新增，P1，默认 `false`）**——解决「导入自己的简历后仓库里没有真实经历，组装只能拼示例数据」这个产品级缺口：

| 规则 | 内容 |
|---|---|
| 默认值 | **`false`，行为与 v1.24 完全一致**（向后兼容；t10 既有判据不得因此变红） |
| `true` 时做什么 | 对 draft 里每个 `kind ∈ {internship, project, activity}` 的 entry **各建 1 个 `package`**：`kind` = 该 section 的 `bound_package_kind`；`title` = entry `title`；`org`/`date_range` → `org`/`start_date`/`end_date`/`is_current`；entry 的 bullets → 多个 `PackageBulletVariant` |
| `verified` 口径 | **原文 entry 的 bullet → `verified=1`；LLM 改写/润色的 variant → `verified=0`**。理由：**「原文即事实」**——简历原文是用户自己写的既成事实，不经二次确认即可用于导出；模型产出的是**新语句**，未经人确认不得冒充事实。UI 上 `verified=0` 的 variant 必须带「AI 改写·待确认」标记，且**默认不进入勾选**（见 ACCEPTANCE AC-PKG-14） |
| 幂等 | 唯一键 `(source_import_job_id, source_entry_temp_id)`：**同一次 commit 重复执行 → 不产生重复包**；已存在的包只更新 `title/org/date` 与新增的 variant |
| 响应 | 201 的 body 增 **`created_packages[]`**：`[{id, title, kind, source_entry_temp_id}]`；未开启或没有可建 entry 时为空数组 `[]`（**字段恒在**，不得按需省略） |
| 失败样例 | `also_create_packages=true` 但 draft 里 `kind=education` 的 entry 不建包（**不是错误**，静默跳过）；若 `bound_package_kind` 缺失 → 按 draft 的 `kind` 映射，映射不出则跳过并 `warnings[PACKAGE_SKIPPED]{entry_temp_id, reason:"no_kind_mapping"}` |

201 → 完整 template 对象（含 blocks+slots），且 **`created_packages[]` 字段恒在**（未开启时为空数组）。
**同源条款（v1.26）**：同一个 `commit` 同时产出 `template`（→ 回填 `import_job.result_template_id`）与派生 `package`（→ `package.source_import_job_id`）时，**两者必须在同一事务内写入、且都能反查回同一个 `import_job`**：

- 不允许只写其中一个：只写模板 → 包里断链；只写包 → 模板溯源断（见 `DATA-MODEL` 的 `result_template_id` 生命周期规则 **R-a**）。
- 反查断言（双向）：`GET /imports/{id}` 的 `result_template_id` 与 `SELECT id FROM package WHERE source_import_job_id=?` 必须都能拿到且非空（当 `also_create_packages=true` 且存在可建 entry 时）。
- 事务边界：模板落库失败 ⇒ 包也不得落库（**全成功或全不落**）；比对 `data/app.db` 的行数差即可判定是否出现了「半成品 commit」。
**commit 必须持久化的三类内容（v1.28 定版，实测缺口驱动）**

> 起因（2026-10-23 首份 PDF）：`import_job.draft_json` 里教育段有 `专业成绩：GPA 3.56/4 86.53/100 CET4：562 CET6:508`、`主修课程：统计学(92)…` 两整段与技能 3 行整句，但 commit 之后 `user_profile.degree/major/grad_year/city` 全为 NULL、`skills_json = []`、**`template_block.static_text` 12 个块全空**，导出 PDF 只剩「示例大学」一行 + `SKILLS_EMPTY`。**这不是渲染问题，是提交时把内容丢了。**

| 内容类别 | 必须落到 | 合法/非法边界 |
|---|---|---|
| **① 静态段正文**（教育 `facts`、技能整句、任何无槽位的整段文字） | `template_block.static_text` | **源草稿该块有内容 ⇒ `static_text` 不得为空**（空 = 非法，导出会静默少一段）；源草稿本就无内容 ⇒ 允许空，但该块**不得渲染空标题** |
| **② 可结构化到档案的字段**（`degree`/`major`/`grad_year`/`city`/`available_date`） | `user_profile.*` 对应列 | commit 从草稿回填；**源里没有的字段必须保持 NULL，不得填默认值或推断值**（防「猜」）；已存在的手工值**不得被草稿覆盖**（除非 `overwrite_profile=true`） |
| **③ 技能整句** | `user_profile.skills_json[].line`（渲染层） | 与 `template_block.static_text` 二者**至少一处**承载同一内容，不得两边都丢；`tokens` 只作索引层 |

**回填可回溯**：commit 回填 `user_profile` 时同时写 `profile_fields_source`（`{field: "import:<import_job_id>" \| "manual"}`），响应体回显 `profile_filled[]`（字段名列表）与 `profile_fields_source`。用户可在个人信息页看到「此字段来自 2026-10-23 的导入」并可一键改为手填值（改后 source 变 `manual`）。

**分层铁律（防止为改匹配而动渲染）**：渲染只许读**渲染层**（`static_text` / `skills_json[].line`），匹配只许读**索引层**（`skills_json[].tokens`、FTS）。**任何层都不得从另一层反推重写**——需要新匹配词就补 `tokens`，需要改文案就改 `line`，两者互不影响。

**导入派生的包随导入生命周期联动（v1.25，P0）**：`DELETE /imports/{id}` 软删时，**该 job 派生出的 `package` 必须在同一事务里一并软删**；`POST /imports/{id}/restore` 一并恢复（`deleted_at` 置 NULL）。手工创建的包（`source_import_job_id IS NULL`）**不受影响**。

- **为什么必须联动（写进正文，别只写在验收里）**：不联动不会报错、不会告警，用户只会在仓库里看到「**幽灵经历**」——已删简历里的项目继续出现在组装候选里，**静默混入导出内容**。这是本项目最不能接受的一类失败：不报错的错误。
- **不物理删行**：删除只写 `deleted_at`，文件与行都保留；真删由 `scripts/prune_probe_data.py --prune-import-jobs` 在用户明确同意后执行。
**清理脚本的「产出优先」铁律（v1.27，与 INT-21/22 同一约束）**：`scripts/prune_probe_data.py --prune-import-jobs`（及同族清理脚本）归档任何 `import_job` 前，**必须**按 `DATA-MODEL` 不变量 **I14 / 规则 R-c** 过滤：

- **不得归档**：`status='committed'`、`result_template_id IS NOT NULL`、或其模板仍存活（`template.deleted_at IS NULL`）的来源行。
- 判定 SQL（与 `DATA-MODEL` 内嵌的同一段，**只此一份**，不得各写一套）：
  ```sql
  SELECT i.id FROM import_job i LEFT JOIN template t ON t.id = i.result_template_id
   WHERE i.deleted_at IS NOT NULL AND (i.status='committed' OR t.deleted_at IS NULL);
  -- 结果集非空 ⇒ 禁止归档，逐行告警并跳过
  ```
- 违反后果（真实事故，2026-10-23）：唯一活跃默认模板「中文-单页-审」的来源行 `01a165188d92700783d126474f4875be` 被按「同指纹留最新」归档，`committed` 活跃数 6 → 0，**模板在、溯源断**，后续 IMP-17 会删错/漏删。
- 监控口径：`SELECT count(*) FROM import_job WHERE status='committed' AND deleted_at IS NOT NULL` 应恒为 **0**（当前实测 0）。
- **幂等去重键**：`UNIQUE(source_import_job_id, source_entry_temp_id)`。**禁止用「标题相同」当去重键**——重名项目（如两个「数据平台重构」）会被误合并，判据也随之变成猜谜。
- 若 `also_create_packages=false`（默认），**不产生任何 `package`**（反向条款：不得因为 draft 里有 entry 就顺手建包）。

**删除导入后模板怎么办（v1.26 定版）**：`DELETE /imports/{id}` 只软删导入行，**不删除它生成的模板**（模板是独立实体，用户可能仍在用）。响应里**必须**带提示字段：

```json
{ "import_id": "…", "deleted": true, "deleted_at": "…",
  "restore_endpoint": "POST /api/v1/imports/{id}/restore",
  "template_retained": { "kept": true, "template_id": "…", "note": "该导入生成的模板仍保留在模板列表；如需删除请调用 DELETE /api/v1/templates/{id}" },
  "note": "已从导入历史隐藏，文件仍在本机；可随时恢复" }
```

- **不做隐式级联**：删导入**不**级联删模板。删模板是另一个端点，必须由用户显式发起（与 §5 的「派生包随导入联动」是**两条方向相反的规则**：包是导入的产物、模板是独立资产——不要为了「一致性」把它们统一成级联，那会静默销毁用户的排版）。
- 若模板已被单独删除（`template.deleted_at` 非空），`template_retained` 回 `{"kept": false, "template_id": "…", "note": "该模板已被删除"}`。

### 5.2 Template

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/templates` | `?lang=&include_deleted=` |
| `POST` | `/templates` | 手建空模板，201 |
| `GET` | `/templates/{id}` | `?include=blocks` |
| `PATCH` | `/templates/{id}` | 更新模板元信息 |
| `DELETE` | `/templates/{id}` | 软删除模板（`deleted_at` 置位） |
| `POST` | `/templates/{id}/default` | 设为唯一默认 |
| `GET` | `/templates/{id}/blocks` | 区块树（`flat[]` + `tree[]` 两种表示） |
| `POST` | `/templates/{id}/blocks` | 新增区块，201 |
| `PATCH` | `/blocks/{id}` | 更新区块 |
| `DELETE` | `/blocks/{id}` | 级联删除区块（含槽位） |
| `POST` | `/templates/{id}/blocks/reorder` | `{ "moves": [{"id":"tb5","parent_block_id":"tb2","order_index":30}] }` |
| `GET` | `/blocks/{id}/slots` | 列出槽位 |
| `POST` | `/blocks/{id}/slots` | 新增槽位 |
| `PATCH` | `/slots/{id}` | 更新槽位 |
| `DELETE` | `/slots/{id}` | 删除槽位 |
| `POST` | `/templates/{id}/validate` | 结构校验（悬空 bound_field、必填槽位缺默认值等）→ 200 `{valid, issues[]}` |

**实现档位（v1.17 定版，给 t10 判红用）**：`GET /templates`、`GET /templates/{id}`、`GET /templates/default`、`DELETE /templates/{id}` **已实现**；`POST /templates/{id}/default`、`POST /templates/{id}/blocks/reorder`、`POST /templates/{id}/validate` 为 **P1（t10 前置，需实现）**；其余写侧（`POST /templates`、`POST /templates/{id}/blocks`、`POST /blocks`、`PATCH`/`DELETE /blocks/{id}`、`GET`/`POST /blocks/{id}/slots`、`PATCH`/`DELETE /slots/{id}`、`GET /templates/{id}/blocks`）标 **`[P2 未实现]`**。理由：模板结构的**首次生成走导入校对**（`PUT /imports/{id}/draft` → `commit`），post-hoc 编辑属增强。详见 §17.2.1。

#### `POST /templates/{id}/default` 为什么是 P1（而不是可延后）

`GET /templates/default` 是**读**默认，`POST /templates/{id}/default` 是**写**唯一默认——**两个都要有**，语义不同不可互相替代。真库实测：3 个模板 `is_default` 全为 `0`。若没有写侧，用户永远无法确定默认模板，t8 组装会落到「不知道用哪个」的不确定态。

**因此 assemble 在无默认模板时的行为必须显式定义（不留空白）**：

| 情形 | 行为 | 响应 |
|---|---|---|
| 请求显式给了 `template_id` | 用给定的模板 | 正常组装 |
| 未给 `template_id`，且**恰好一个** `is_default=true` | 用它 | 正常组装 |
| 未给 `template_id`，且**没有** `is_default=true`（真库现状） | **拒绝**，不猜 | **409 `CONFLICT`**，`details{reason:"NO_DEFAULT_TEMPLATE", candidates:[{id,name,updated_at}]}`，`hint:"先在 Templates 页『设为默认』，或组装时显式选模板"` |
| 未给 `template_id`，且**多个** `is_default=true`（历史脏数据） | **拒绝**，不猜 | **409 `CONFLICT`**，`details{reason:"MULTIPLE_DEFAULT_TEMPLATES", ids:[...]}` |
| 库里有模板但**全部软删** | 拒绝 | 404 `NOT_FOUND`（`details.resource="template"`） |

> **为什么拒绝而不是「取最新」**：默认模板决定简历的版式与章节顺序，静默取最新会让用户拿到一份自己没选过的排版，且失败不可见——这正是本项目反复拒绝的「静默成功」。`candidates[]` 让前端直接渲染选择器，用户一步就能修好。`details.reason` 的取值 `NO_DEFAULT_TEMPLATE` / `MULTIPLE_DEFAULT_TEMPLATES` 属**错误码细则**，不单列错误码行（§16.2 白名单）。

### `POST /api/v1/blocks` 请求
```json
{ "template_id": "tpl_01J9Z...", "parent_block_id": null, "order_index": 40,
  "block_type": "entry", "heading": "教育背景", "bound_package_kind": "education",
  "style_json": { "size": 12, "bold": true, "space_before": 8, "rule": "bottom" },
  "max_bullets": 3, "repeat_per_package": true }
```

### `POST /api/v1/slots` 请求
```json
{ "block_id": "tb_01J9Z...", "slot_key": "candidate.school", "slot_type": "text",
  "required": true, "bound_field": "profile.school_zh", "max_chars": 40 }
```
`slot_key` 必须匹配 `^[a-z][a-z0-9_.]{0,40}$`（允许点号，如 `candidate.name`；不允许连续点与首尾点），否则 `VALIDATION_ERROR`；`bound_field` 不在白名单（`profile.*` / `package.*` / `position.*` / `build.*`）→ `TEMPLATE_INVALID`。

---

## 6. JD 与需求

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/jds` | 粘贴 JD 文本或上传文件，201 |
| `GET` | `/jds` | 列 JD（`?status=&company=`） |
| `GET` | `/jds/{id}` | JD 详情（`?include=requirements`） |
| `PATCH` | `/jds/{id}` | 改 JD |
| `DELETE` | `/jds/{id}` | 删 JD（软删） |
| `POST` | `/jds/{id}/analyze` | 分析技能需求（LLM 或 `method=heuristic`），202 → job |
| `GET` | `/jds/{id}/requirements` | 需求列表 |
| `PATCH` | `/requirements/{id}` | 人工修正（改后 `source=manual`） |
| `DELETE` | `/requirements/{id}` | |
| `POST` | `/jds/{id}/match` | 计算需求 ↔ package 的匹配度（本地打分，**不联网**）→ 200 |

`POST /jds` 请求：
```json
{ "raw_text": "岗位职责：...", "title": "数据分析实习生", "company_name": "某某科技",
  "source_url": "https://...", "lang": "zh" }
```

`POST /jds/{id}/analyze` 请求：
```json
{ "method": "auto", "preview_id": "pv_...", "max_requirements": 25 }
```
- `method=auto`：LLM 可用 → `llm`；否则 → `heuristic`（并回 `LLM_DISABLED` 的警告而不是错误）。
- 若 `method=llm` 或 `auto` 且 LLM 就绪，**必须**带 `preview_id`，否则 `LLM_CONSENT_REQUIRED`。

`GET /jds/{id}/requirements` 响应：
```json
{ "ok": true, "data": { "items": [
  { "id": "req_1", "skill": "SQL", "category": "hard", "priority": "must", "weight": 0.9,
    "evidence_hint": "熟练使用 SQL 进行多表关联分析", "raw_quote": "…", "source": "llm",
    "candidate_status": "satisfied",
    "matched_package_ids_json": ["pkg_a", "pkg_b"] }
], "analysis_method": "llm", "analyzed_at": "..." }, "request_id": "..." }
```

`POST /jds/{id}/match` 响应（本地算法：关键词/标签/向量无关的集合命中 + 权重和）：
```json
{ "ok": true, "data": { "scores": [
  { "package_id": "pkg_a", "score": 0.82, "hits": ["SQL", "A/B 测试"], "gaps": ["Tableau"] }
], "coverage": 0.71, "top_gaps": ["Tableau", "英文口语"] }, "request_id": "..." }
```

### 6.1 竞争力评估 `competitiveness`（**校名必须参与判断**，ADR-20）

**为什么存在**：校名进了 payload 但分析 schema 里没有字段消费它 → 隐私成本付了、分析收益为零，属净损失。因此 `competitiveness` 是**契约必需字段**，不是可选增强。

`POST /jds/{id}/analyze` 的 job 完成后，`GET /jds/{id}` 的 `data` 增：

```json
"competitiveness": {
  "school_tier": "985",
  "school_signal": "985 院校 + 目标岗位限 2026 届本科及以上，院校层次满足明示门槛",
  "degree_fit": "strong",
  "major_fit": "medium",
  "experience_fit": "medium",
  "verdict": "medium",
  "gap_notes": ["缺少 Tableau 实操证据", "无相关行业实习"]
}
```

| 字段 | 类型 | 约束 |
|---|---|---|
| `school_tier` | enum | `C9` / `985` / `211` / `双一流` / `普通本科` / `海外` / `其他`。**优先取 `UserProfile.school_tier` 手工值**；未填时由 LLM 依据校名推断，并在 `warnings[]` 加 `SCHOOL_TIER_INFERRED` |
| `recognized` | bool | **`school_tier` 是否来自可信来源**：`UserProfile.school_tier` 手填 → `true`；由校名推断命中内置表 → `true`；推断不出来 → `false`。**`recognized=false` 时 `school_tier` 恒为 `其他`** |

| `school_signal` | str | 一句话说明校名**在该岗位筛选中的作用**；**长度 ≥8 且必须含校名或院校层次词**（禁「表现良好」式模板套话，AC-ANL-06 反向断言） |
| `degree_fit` / `major_fit` / `experience_fit` | enum | `strong` / `medium` / `weak` |
| `verdict` | enum | `strong` / `medium` / `weak`，整体竞争力判断 |
| `gap_notes` | str[] | 可投递的短板，供 Builds 页「往哪打」提示 |

**院校层次的「未识别」语义（定版，D-37 / ANL-09）**

七枚举与「未识别」是两件事，契约按下面写死，**不许实现者自行发明**：

| 情形 | `school_tier` | `recognized` | warning |
|---|---|---|---|
| 用户在 `UserProfile.school_tier` 手填 | 手填值 | `true` | 无 |
| 校名命中内置表（C9 / 985 / 211 / 双一流） | 对应档 | `true` | `SCHOOL_TIER_INFERRED`（`severity=info`，`details{recognized:true}`） |
| 纯英文校名或含海外词（`麻省理工学院` / `Stanford University` / `National University of Singapore`） | `海外` | `true` | 同上（`severity=info`） |
| **未收录的中文校名**（`XX大学` / `某某学院`） | **`其他`** | **`false`** | `SCHOOL_TIER_INFERRED`（`severity=warn`，`details{recognized:false}`，message 必须含「未能识别」并建议手填） |

硬要求：

1. **「未收录」不等于「普通本科」**。内置表覆盖有限，把漏收录的校名判成 `普通本科` 属于**编造事实**（方向与「编造门槛」相反，后果同样是误导用户）。推断链路**必须返回 `None` → 落 `其他`**，不得有「默认 普通本科」的分支。
2. **海外院校按校名判定**，不只看 JD 文本层：纯英文校名（无中日韩字符且含 ≥3 个字母）一律 `海外`。
3. **`recognized=false` 时的行为约束**：`competitiveness.verdict`、`gap_notes`、`school_signal` **不得出现**「层次偏低 / 院校竞争力偏弱 / 学历背景不足」这类结论；`school_signal` 必须如实写「院校层次未识别（<校名>），按『其他』记录，不影响其他维度评分，建议手填」。**用「没收录」去否定用户是编造。**

> 实测基线（2026-10-23 04:1x，`.venv/bin/python -c "from app.services.jd_analysis import tier_from_school_name"`）：`清华大学/北京大学→C9`、`北京师范大学/中国人民大学/示例大学→985`、`上海大学/南京信息工程大学→211`、`麻省理工学院/Stanford University/National University of Singapore→海外`、`XX大学/某某学院→None`（→落 `其他` + `recognized:false`）。

- 逐条需求的落地表达：`requirements[].candidate_status ∈ {satisfied, partial, missing}`；`candidate_status_source ∈ {llm, heuristic, local_override, manual}`（四值 + 优先级 `manual > local_override > heuristic > llm`，见 §6.2.5）；证据见 `matched_package_ids`（只表示经历包）与 `matched_evidence[]`（证据全集），见 §6.2.4。
- `method=heuristic`（离线）时 `competitiveness` 仍需返回：`school_tier` 取 `UserProfile.school_tier` 或 `其他`，`school_signal` 由模板串（含校名 + tier 词）生成，**不得返回 `null`**。

### 6.2 `jd_analyze` 的输入来源与预算（v1.35，**经历要点必须参与对照**）

**为什么加这一节**：真库里一次真实分析，六条 requirement 的 `matched_package_ids` 全是 `[]`，而仓库里就有对应的 A/B 测试项目与 SQL/Python 要点——**系统把用户自己的经历判成了「不存在」**。模型只能看到 JD 文本与姓名/学校，看不到经历，于是「missing」是必然结论。这不是模型的错，是 payload 缺料。

#### 6.2.1 新增 payload 来源 `packages`（**沿用包模型，不新造数据类型**）

`/llm/preview` 的 `fields[].source` 枚举新增 **`packages`**，语义 = **「本次参与对照的经历要点集合」**。

**只允许发送**：包标题 `title` / `org` / `role` / 日期（`start_date`–`end_date`）/ bullet 文本（`package_bullet_variant.text`）。

**禁止发送**（出现即判隐私违规，`assert_no_identity` 同级）：

| 禁止项 | 理由 |
|---|---|
| `skills_json[].tokens` | 派生索引层，只服务本地匹配；发送会让模型误以为要点里出现过这些词（I17 分层不互推） |
| 变体 id / 包 id | 纯内部标识，模型用不到；回传反而诱发编造引用 |
| 附件路径 / `photo_path` / 任何 `data/**` 路径 | 路径泄露本机结构（§5.4 `EXCLUDED_PATHS`） |
| 证件照字节 / `sha256` | m00265 硬线：照片永不出本机 |

#### 6.2.2 预算常量（契约常量，唯一来源；不许散落在代码里）

| 常量 | 值 | 超限处置 |
|---|---|---|
| 参与对照的包数上限 | **12** | 超出部分按 `order` 截断，发 **`PACKAGES_TRUNCATED{included, skipped}`** |
| 经历要点总字符上限 | **6000**（按包顺序累加，超限即停） | 同上，`skipped` 为实际未纳入的包数 |

响应（`jd analyze` 的 job `result_json` 与 `GET /jds/{id}` 的 `data`）增：

```json
"context": { "packages_included": 7, "skipped": 5, "chars": 5842 }
```

- `packages_included + skipped` 必须等于**本次参与选择的包总数**（t11 直接比对，可机械验）。
- `chars` 是**实际发送的要点字符数**（不含标签与分隔符），必须 ≤ 6000。

#### 6.2.3 隐私声明必须同步（否则用户核对不了）

- ConsentModal 的「**会发送**」清单新增一项：**「N 条经历要点（项目/实习标题、时间、要点文本）」**，N 必须等于 `context.packages_included`。
- `/llm/preview` 的字段清单**必须能逐条列出这 N 条**（每包至少一行 `fields[]`，`source="packages"`，`label` 写 `<包标题> · 要点 ×k`）——只给总数、不给清单等于让用户盲签。
- 「**不会发送**」清单不变：姓名、电话、邮箱、证件照（m00265）。

#### 6.2.4 `matched_package_ids` 与 `matched_evidence` 的语义（**本地计算，不得采信模型输出**）

**为什么需要两个字段**（真库实测暴露）：六条 requirement 里有「partial / matched 数 0 / 证据片段：数据分析类：掌握Python」——它**确实匹配到了**，证据是 `skills_json` 第 1 行，但技能栏不属于任何 package，只能塞进 `matched_package_ids=[]`。这直接违反旧契约「空数组必须意味着确实没匹配到」：技能栏命中会带着空数组，界面与下游**无法区分「真的没有」与「有证据但不属于任何包」**。同理「985/211 院校优先」的证据来自 `user_profile.school`、「毕业届别」来自 `grad_year`。

**新字段** `requirements[].matched_evidence[]`，元素：

```json
{ "source": "package" | "skills_json" | "profile",
  "ref_id": "pkg_a" | null,
  "quote": "赛车类游戏版本AB测试对照数据分析",
  "field": "school_tier",
  "derived": true,
  "rule": "校名「示例大学」→ 本地层次表" }
```

> 后三个键**可选**：`field` 只在 `source="profile"` 时出现（指出证据来自哪个档案字段，取值见下方约束表）；`derived` / `rule` 只在**派生证据**时出现。

| 字段 | 约束 |
|---|---|
| `source` | 三枚举：`package`（经历包）/ `skills_json`（技能栏某一行）/ `profile`（档案字段：`school` / `school_tier` / `degree` / `major` / `grad_year` / `city` / `available_date`） |
| `ref_id` | `source="package"` 时**必须**是 `status='ready'` 的包 id；`skills_json` / `profile` 时必须为 **`null`**（这两个来源没有行 id，硬塞 id 等于编造引用） |
| `quote` | **原文 ≥8 字符的连续片段**（沿用 ANL-17）：`package` → 必须能在该包某个 variant `text` 里**逐字找到**；`skills_json` → 必须能在 `skills_json[].line` 里**逐字找到**；`profile` → 必须等于该字段值本身或它的连续子串。**找不到即 FAIL**（不许改写、不许概括） |
| `field` | **仅 `source="profile"` 时必须有**：`school` / `school_tier` / `grad_year` / `degree` / `major` / `city` / `available_date`（v1.39 从 `degree`/`major` 两项扩为七项）。缺失 → 该条判 FAIL（无法指出证据来源字段） |
| `derived` | **可选，默认 `false`（省略即 false）**。`true` = **本地确定性推算，不是原文引用**：原文里并没有「985」「2027」这些字，是系统用本地规则算出来的。**界面必须标成「推算」，不得与「原文命中」混排**（同一列表里两者图标/措辞必须可区分） |
| `rule` | `derived=true` 时**必须**有：一句话写明推算规则，可复算。现有两条规则原文：`手工填写 school_tier` 或 `校名「{school}」→ 本地层次表`（层次取 `tier_from_school_name`，与竞争力判断**同一张表**）；`grad_year {grad} ≥ JD 要求 {wanted}`（年份来自 JD 文本 `20\d{2}` + 「届/及以后/以后/之后/起」）。**`rule` 里不得出现模型生成的自然语言** |

**两个字段的分工（收窄后的定版语义）**

| 表达 | 含义 |
|---|---|
| `matched_package_ids` | **只表示命中的经历包**。非空 ⇒ 有真实经历支撑（Builds 页可据此推荐包） |
| `matched_evidence` | 证据全集（经历 + 技能栏 + 档案）。`matched_package_ids` 中的每个 id **必须**在 `matched_evidence` 里有一条 `source="package", ref_id=该 id` 的对应项（两处不许打架） |
| 「没匹配到」的判据 | **`matched_package_ids == [] 且 matched_evidence == []`** 才算确实没匹配到。任一非空 ⇒ 有证据，`candidate_status` 不得为 `missing` |

其他规则（不变）：

| 规则 | 说明 |
|---|---|
| **计算方** | **本地**（`services/match.py` 的词表/子串打分），**禁止**把模型返回的 id 数组直接入库 |
| 元素有效性 | 每个包 id 必须指向 `status='ready'`；指向已删/未就绪 → 记 **`MATCHED_PACKAGE_NOT_READY{requirement_id, package_ids[], statuses[]}`** 并**剔除**该 id（同时剔除对应 `matched_evidence` 项） |
| 允许为空 | 空数组必须意味着「**确实没匹配到**」，不能意味着「**没算**」——实现必须在返回前跑过匹配（AC-ANL-15 反向断言） |

> **两个 `source` 不是同一个东西（v1.39 显式区分，此前歧义踩过一次）**：`matched_evidence[].source` 答的是「**证据来自哪**」（`package` / `skills_json` / `profile`），`requirements[].candidate_status_source` 答的是「**谁下的这个判断**」（`llm` / `heuristic` / `local_override` / `manual`）。两者**正交**：同一条 requirement 完全可以是「证据来自 `profile`、判断由 `llm` 下」，也可以是「证据来自 `package`、判断被 `local_override` 改过」。**判据里禁止用其中一个去断言另一个**。

#### 6.2.5 `candidate_status_source` 枚举扩为**四值**与优先级

`candidate_status_source ∈ { llm, heuristic, local_override, manual }`。

> **`manual` 是真语义，必须保留**：人工 PATCH `candidate_status` 后 `source='manual'`（实现见 `server/app/repos.py:1293`）。此前本文档把枚举钉成三值并写「`manual` 是误写」，那是**文档错、实现对**——人工改判与模型推断是两件事，不能因为枚举不好看就把人的决定抹平。

**优先级（高 → 低）**：**`manual` > `local_override` > `heuristic` > `llm`**。

| 规则 | 说明 |
|---|---|
| 自动链路不得覆盖 `manual` | 任何重算/分析/补匹配流程，**不得修改 `candidate_status_source == 'manual'` 那行的 `candidate_status`**；可以补/更新 `matched_package_ids` 与 `matched_evidence`（那属于事实层，人工改的是判断层） |
| 界面必须标注 | 人工改过的条目要给**可见标记**（Builds/Requirements 列表行显示「已人工修正」角标 + hover 显示原自动判定值），否则用户不知道哪条是自己改的 |
| 撤销人工改判 | 需显式 `PATCH {"candidate_status": null, "candidate_status_source": "auto"}` 语义（把 `source` 清回自动态并重算）；不带该参数的重算一律跳过 manual 行 |

> **本地覆盖规则**：当本地匹配到证据（`matched_package_ids` 或 `matched_evidence` 非空）而模型给出 `candidate_status="missing"` 时，系统**必须**改判 `partial`、`candidate_status_source="local_override"`，并发 **`LLM_STATUS_OVERRIDDEN{requirement, from:"missing", to:"partial", matched_package_ids[], matched_evidence[]}`**。
>
> **反向约束（同样硬）**：**无证据时不得改判**——`matched_package_ids == [] 且 matched_evidence == []` 时，`missing` 必须原样保留。否则「没有」会被伪造成「有」，用户会照着不存在的经历去面试。

- 改判只允许 `missing → partial`（唯一方向）；`satisfied`/`partial` 不因本地命中而上调（避免把「沾边」变「满足」）。
- `manual` 行**永不**被 `local_override` 覆盖（优先级决定），且不因重算而被改写。
- `heuristic` 路径（离线）两个匹配字段同样必须由本地计算填。

---

## 7. 公司画像

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/company-profiles/analyze` | 由「公司名 + 可选 jd_id」分析，202 → job（LLM 需 preview）。**可选**先抓官网/招聘页公开文本作为上下文（`fetch.allow`，默认取 `app_setting.allow_web_fetch`） |
| `POST` | `/fetch/public-page` | **下行通道唯一入口**：抓取单个公开页面并抽正文，见下方 |
| `POST` | `/company-profiles` | **手动建档**（不走 LLM）：`CompanyIn`（`company_name` 必填 1–120 字，其余字段可选）→ **201** + `Location: /api/v1/company-profiles/{id}`；`company_name` 已存在 → **409** `CONFLICT` `details{company_name,id}` + `hint` 指向 `PATCH` |
| `GET` | `/company-profiles` | `?company_name=` |
| `GET` | `/company-profiles/{id}` | 读公司画像 |
| `PATCH` | `/company-profiles/{id}` | 改公司画像（改后 `method=manual`） |
| `DELETE` | `/company-profiles/{id}` | 删公司画像 |

`POST /company-profiles/analyze` 请求：
```json
{ "company_name": "某某科技", "jd_id": "jd_01J9Z...", "notes": "面试官强调结果导向",
  "preview_id": "pv_...", "refresh": false }
```
- `refresh=false` 且缓存未过期（`expires_at` 未到, 默认 30 天）→ **不调用 LLM**，200 直接返回缓存，`data.cache_hit=true`。
- **允许下行抓取公开页**（用户已授权，默认开启）：`sources_json` 可为 `jd`、`user_note`、`public_page`（带 `url` 与 `fetched_at`）。抓取只取正文文本，**不携带任何用户数据**；失败/被关闭 → 自动降级为「只用粘贴的 JD + 备注」（`warnings[{code:"FETCH_UNAVAILABLE"}]`），**不阻塞**分析。
- 请求可带 `"fetch": {"allow": true, "url": "https://..."}`：不给 `url` 时由 `company_name` 推导候选（官网 `https://<公司名>.com` 之类**不瞎猜**——只在 `company_profile.website` 已知或用户给了 `url` 时才抓）。

**`hiring_preferences_json` 的必答项（缺任一 → 该次分析判 `confidence` 扣减并在 `warnings[]` 记 `PROFILE_FIELD_MISSING`）**
1. **院校偏好**：是否卡 985/211/双一流、是否偏好本地院校、是否看重第一学历 —— 落到 `school_preference`；
2. 学历与届别门槛（本科/硕士、是否限当届）；
3. 硬性技能门槛（must 级工具）与加分项；
4. 风格偏好（量化成果 / 一页纸 / 业务影响）。

**`school_preference` 反编造要求（AC-ANL-07）**：JD 与抓取文本**均未提院校**时，`threshold="不限"`、`hard_filter=false`、`preferred_tiers=[]`，且 `evidence` 必须说明“依据：仅见『本科及以上』，未见院校层次要求”。**禁止**在无依据时填 `985/211` 或 `hard_filter=true`。

**`preferred_tiers` 的「非硬门槛偏好」语义（定版，D-37 / ANL-10）**

「优先」和「硬卡」是两件事。现状实测会把前者丢掉：JD 写「985/211 优先，但不设院校门槛」→ `hard_filter=false, threshold="不限", preferred_tiers=[]`，**「优先」信息消失**。契约写死：

| 输入 | `hard_filter` | `threshold` | `preferred_tiers` |
|---|---|---|---|
| 「仅限 / 要求 985」这类硬门槛 | `true` | 门槛原文 | 门槛档位 |
| **「985/211 优先，但不设院校门槛」** | **`false`** | **以「不限」开头且含「偏好」二字**，例 `不限（偏好 985/211）` | **非空**（如 `["985","211"]`） |
| JD 全文无任何院校词 | `false` | `不限` | **必须 `[]`** |

硬要求：

1. `hard_filter=false` 时 `preferred_tiers` **允许且应当非空**——它就是「优先」的载体，不得因为「不是硬门槛」而清空。
2. 此时 `threshold` 必须以「不限」开头、含「偏好」二字，**防止 UI 把偏好渲染成硬门槛**：唯一硬门槛判据是 `school_preference.hard_filter`。
3. **反向**：JD 全文无院校词时 `preferred_tiers` 必须为 `[]`，不得凭岗位类型造偏好（这是「编造门槛」的反向变体）。
4. `hard_filter=true` 而用户 `recognized=false`（见 §6.1）时**不得判不合格**——未知不是劣势。

##### 门槛动词分组：**「优先」不是门槛**（D-39，定版）

实测（`server/app/services/jd_analysis.py`，2026-10-23）证明：只要把 `优先` 与 `仅限/必须` 编进同一组动词，「985/211 院校优先」就会被判成 `hard_filter=true`，用户在 UI 上看到「这家公司卡 985/211」而**放弃本来能投的岗位**——这是本项目里唯一一种「错得让人少投一家公司」的错误，比显示错字严重得多。

因此动词**必须分三组**（实现里已拆为 `HARD_VERBS` / `SOFT_VERBS`，见 `jd_analysis.py:31-35`）：

| 组 | 词表（示例，允许扩充同义词） | 对 `hard_filter` 的作用 |
|---|---|---|
| **硬** | 仅限 / 限 / 限定 / 只招 / 必须 / 须 / 要求 / 门槛 / 起 / 起步 / 及以上 / 以上 | 可为 `true` |
| **软** | 优先 / 更佳 / 加分 / 青睐 / 欢迎 / 倾向 | **恒为 `false`**，只写 `preferred_tiers` + `threshold` |
| **明确负向** | 不设门槛 / 不限院校 / 院校不限 / 无院校要求 | 强制 `false`，且清空 `preferred_tiers`（除非同句另有软动词，见优先级） |

**优先级**：明确负向 **>** 硬 **>** 软。即「985/211 院校优先，但不设院校门槛」→ `hard_filter=false` + `preferred_tiers=["985","211"]` + `threshold` 含「偏好」（负向压过硬/软，但**不吞掉偏好信息**）。

**并列档位不得截断**：`985/211`、`985、211`、`985 和 211`、`985 或 211` 都是**两个档位**。硬门槛时 `preferred_tiers` 必须含全部档位、`threshold` 保留原文的并列写法（如 `"985/211"`）；只取首个匹配（`"985"`）属于**信息丢失**——用户会误以为自己没有 211 就完全没戏。

参数化用例（**判据表，AC-ANL-11/12 逐行断言**）：

| # | JD 片段 | `hard_filter` | `threshold` | `preferred_tiers` |
|---|---|---|---|---|
| 1 | `985/211 院校优先` | `false` | 以「不限」开头且含「偏好」 | `["985","211"]` |
| 2 | `985/211 院校优先，但不设院校门槛` | `false` | 同上 | `["985","211"]` |
| 3 | `211 院校优先，985 优先` | `false` | 含「偏好」 | 含 `211` 与 `985` |
| 4 | `仅限 985/211 院校` | `true` | `"985/211"`（保留并列原文） | `["985","211"]` |
| 5 | `要求 985 及以上` | `true` | 含 `985` | `["985"]` |
| 6 | `不设院校门槛，学历不限` | `false` | `不限` | `[]` |
| 7 | `本科及以上学历，计算机相关专业` | `false` | `不限` | `[]` |
| 8 | `985 优先，但仅限硕士`（软 + 学历硬） | `false` | 含「偏好」 | `["985"]` |

**实测（`detect_school_gate`，2026-10-23 04:17:29，10/10 通过）**：用例 1–8 全部符合本表；另测 `仅限 985、211 院校` 与 `仅限 985 和 211 院校` 均回 `threshold="985/211"` + `["985","211"]`。上述为**回归判据**，任何回退（尤其把 `优先` 并回硬动词、或只取首个并列档位）均判实现缺陷。

#### `POST /api/v1/fetch/public-page`

请求：`{ "url": "https://jobs.example.com/jd/123" }`

200：
```json
{ "ok": true, "data": {
  "url": "https://jobs.example.com/jd/123", "final_url": "https://jobs.example.com/jd/123",
  "host": "jobs.example.com", "title": "数据分析实习生 - 招聘",
  "text": "岗位职责……", "chars": 1830, "truncated": false,
  "from_cache": false, "fetched_at": "2026-10-23T02:51:12+08:00",
  "warnings": []
}, "request_id": "..." }
```
- 只有 `GET`；请求**无 body、无 query 除 URL**，`User-Agent: ResumeWarehouse/1.0 (local)`，无 cookie、无登录态。
- 校验失败：host 不在白名单 → 403 `EGRESS_BLOCKED` `details{reason:"host_not_allowed", host}`；`allow_web_fetch=false` → 403 `details{reason:"fetch_disabled"}`；解析到私有 IP → 403 `details{reason:"private_address"}`；跳转超 3 跳 → 403 `details.reason="too_many_redirects"`；正文 < 200 字符 → 422 `VALIDATION_ERROR` `details.reason="EMPTY_BODY"`（调用方据此降级 D15）；超时 15 s → 504 `TIMEOUT`。
- 抓到的正文缓存到 `data/files/`（按 URL 的 sha256），24 h 内 `from_cache=true`；缓存只在本地，**永不二次上云**。

响应：
```json
{ "ok": true, "data": {
  "id": "cp_1", "company_name": "某某科技", "industry": "互联网", "company_stage": "大厂",
  "culture_signals_json": [{ "signal": "结果导向", "evidence": "JD 高频出现『落地』『闭环』" }],
  "hiring_preferences_json": ["偏好量化成果", "一页纸", "强调业务影响"],
  "school_preference": {
    "threshold": "985/211",
    "preferred_tiers": ["985", "211"],
    "hard_filter": false,
    "evidence": "JD 写『本科及以上，2026 届』，未提院校层次；同公司往年校招公示提到 985/211 优先",
    "confidence": 0.62
  },
  "interview_focus_json": ["SQL 实操", "指标体系设计"],
  "tone": "务实", "keywords_json": ["增长", "归因", "指标体系"],
  "sources_json": [{ "type": "jd", "ref": "jd_01J9Z..." }],
  "confidence": 0.66, "method": "llm", "cache_hit": false,
  "last_analyzed_at": "...", "expires_at": "..."
}, "request_id": "..." }
```

---

## 8. Build（组装与导出）

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/builds` | 创建（模板 + 选包 + 命名），201 |
| `GET` | `/builds` | `?status=&template_id=&include_archived=`。**默认 `include_archived` 关闭**（只返回 `archived_at IS NULL`）；`1/true/yes/on` 时含已归档。**列表项不含 `layout`、不含 `page_count`**（见下方说明），只含 `est_pages`（assemble 时估算，可能为 `null`） |
| `GET` | `/builds/{id}` | `?include=selections,artifacts` |
| `PATCH` | `/builds/{id}` | 改 position/company/naming/field_values/sections_order，以及 **`archived: true|false`**（写/清 `archived_at`，幂等）。**实现现状（2026-10-23 08:1x）：`repos.py:1658 set_archived()` 已存在，但 `PATCH` 的允许键列表未接线、也没有独立归档路由 → 归 coder（§17.8 `T-8`）** |
| `PUT` | `/builds/{id}` | **`PATCH` 的别名**（v1.33 补齐，同语义同校验；前端 PUT 与 PATCH 均可）。两者行为**必须完全一致**，禁止一处改字段另一处不改 |
| `GET` | `/builds/{id}/selections` | 读当前选择集合（与 `PUT` 对称；返回 `{selections:[…], snapshot_at}`，无选择时 `[]` 而非 404） |
| `DELETE` | `/builds/{id}` | **默认 = 归档**（写 `archived_at`，200 `{id, archived_at, archived:true, restore_endpoint:"PATCH /api/v1/builds/{id}"}`，selections/artifacts **原样保留**）。**硬删必须显式**：`?hard=1&confirm=<build_id>`（`confirm` 必须等于路径 id，否则 422 `VALIDATION_ERROR` `details.reason="CONFIRM_MISMATCH"`），且**先落快照**（该行 + selections + artifacts 导出 JSON 到 `data/exports/_trash/`）。理由见 `DATA-MODEL` 不变量 **I24/I25**：物理删行会让 `data/exports/` 里的 PDF 变成没人指向的孤儿，用户再也看不到自己导出过什么 |
| `PUT` | `/builds/{id}/selections` | **整体替换**选择集合（幂等） |
| `POST` | `/builds/{id}/assemble` | 组装成 IR（内存）+ 估算页数 + 告警 → 200 |
| `GET` | `/builds/{id}/preview` | 返回 HTML 预览页（`text/html`），供 iframe 展示 |
| `POST` | `/builds/{id}/export` | 导出，202 → job（PDF 是 CPU 活儿，>2 s 走 job） |
| `GET` | `/builds/{id}/artifacts` | 产物列表 |
| `GET` | `/artifacts/{id}/download` | 下载（`Content-Disposition` 用最终文件名，RFC 5987 编码中文） |
| `POST` | `/builds/{id}/suggest` | LLM 建议「哪些包/变体最匹配该 JD」，202 → job（需 preview） |

**`GET /builds` 列表 vs 组装/导出 的字段边界（v1.35，T-1 家族收口）**

| 字段 | 列表 `GET /builds` | `POST /builds/{id}/assemble` | `POST /builds/{id}/export` |
|---|---|---|---|
| `est_pages` | ✅（assemble 时估算，未组装则为 `null`） | ✅ | ✅ |
| `layout{available_height_pt,text_width_pt,body_pt,leading}` | ❌ **不返回** | ✅ | ✅ |
| `density` | ❌ 不返回（属 build 配置，详情 `GET /builds/{id}` 可见） | ✅ | ✅ |
| `artifacts[]` | ❌（列表不 join 产物表，`?include=` 也不支持） | ❌ | ✅ |

**为什么列表不返回 `layout`**：`layout` 是**某次渲染的实测结果**（可用高度、实际字号、实际行距），只有 assemble/export 跑过才有值；列表里给一个「上次沿用」的 `layout` 会让人误以为它描述当前配置。**所以契约侧不补字段，改为把边界写死**——列表拿 `est_pages` 估页数、要精确页数与版式就调 assemble 或读 `GET /builds/{id}/artifacts` 的导出记录。
> 这也解释了实测现象：`GET /builds` 里 `pages` 为 `None`——**列表根本没有 `pages` 这个键**，取不到不等于「算出来是空」。

### 8.1 `POST /api/v1/builds`
```json
{ "name": "字节-数据分析-2026秋招",
  "template_id": "tpl_01J9Z...", "jd_id": "jd_01J9Z...", "company_profile_id": null,
  "position": "数据分析实习生", "company": "某某科技", "lang": "zh",
  "naming_pattern": "{position}-{name}-{school}",
  "naming_overrides_json": {},
  "field_values_json": { "summary.text": "3 年数据分析实践，擅长指标体系与增长归因" } }
```
- `naming_pattern` 校验见 §9.3；非法 → 422（`NAMING_*`）。
- `position` 为空但 `jd_id` 有 `title` 时自动继承。

### 8.1.1 `POST /api/v1/builds/{id}/suggest` 响应（job 完成后 `GET /jobs/{id}` 的 `result_json`）
```json
{ "suggestions": [ { "package_id": "pkg_a", "variant_ids": ["var_1"],
                     "reason": "命中 must 级『指标体系』与『SQL』，且有可量化结果" } ],
  "competitiveness_summary": { "verdict": "medium", "school_tier": "985",
                               "school_signal_used": true,
                               "coverage": { "advantage": ["…"], "neutral": [], "gap": ["…"] } },
  "school_signal_used": true }
```
- `school_signal_used`：本次建议**是否真的用到了校名/院校层次**做取舍（`false` 时必须在 `warnings[]` 里给 `SCHOOL_SIGNAL_UNUSED`，防止"发了但没用"再次退回净损失）。
- `competitiveness_summary` 与 assemble 的字段**同名同结构**，保证前端一套渲染。

### 8.2 `PUT /api/v1/builds/{id}/selections`
```json
{ "selections": [
  { "package_id": "pkg_a", "order_index": 0,
    "variant_ids_json": ["var_1", "var_5"], "overrides_json": { "org_display": "某某科技有限公司" } },
  { "package_id": "pkg_b", "order_index": 1, "variant_ids_json": ["var_9"], "overrides_json": {} }
] }
```
- 幂等整体替换；`package.status != 'ready'` → `CONFLICT`(409, `details.reason="PACKAGE_NOT_READY"`)。
- 自动写 `snapshot_json`。

### 8.3 `POST /api/v1/builds/{id}/assemble` 响应
```json
{ "ok": true, "data": {
  "build_id": "rb_01J9Z...", "status": "assembled",
  "est_pages": 1.24, "page_limit": 1,
  "sections": [ { "block_id": "tb2", "heading": "教育背景", "entries": 1, "bullets": 2 } ],
  "missing_slots": [],
  "competitiveness_summary": {
    "verdict": "medium", "school_tier": "985", "school_signal_used": true,
    "coverage": { "advantage": ["985 院校满足明示门槛", "SQL/指标体系命中 3/4 条 must 要求"],
                  "neutral": ["无 Tableau 证据"],
                  "gap": ["缺相关行业实习"] }
  },
  "warnings": [ { "code": "PAGE_OVERFLOW", "severity": "warn",
                  "message": "预计 1.24 页，超出模板 1 页限制", "suggestion": "减少 1–2 条 bullet 或切换紧凑样式" } ],
  "ir_hash": "abc123"
}, "request_id": "..." }
```

### 8.4 `POST /api/v1/builds/{id}/export`
```json
{ "format": "pdf", "engine": "auto", "overwrite": false, "verify_text": true, "density": "original" }
```
- `engine`: `auto`（reportlab → 失败回退 chrome）/ `reportlab` / `chrome` / `docx`（`format=docx` 时强制）。
- `verify_text` 默认 `true`：导出后抽取文本与 IR 比对，结果写 `text_verified`。
- **`density`**（v1.18 新增，默认 `"original"`）：`"original"` = 用户原件密度（边距 8.3/16.4/14.8/15.6 pt，可用高度 **817.65 pt**，版心 **564.9 pt**，目标单页正文 ≥10.0 pt）；`"relaxed"` = 通用审美密度（15/16 mm，可用高度 751.5 pt，允许 2 页）。取值非法 → 422 `VALIDATION_ERROR`。**默认必须是 `original`**：用户的现有简历就是这个密度，产物不该更松散（ARCHITECTURE ADR-21）。响应回显 `density` 与 `layout{available_height_pt, text_width_pt, body_pt, leading}`，便于 t11 直接断言。
- **`warnings` 的来源（定版）**：导出响应的 `warnings[]` 是三段合并而成——① **排版判定**（`PAGE_FIT_DOWNGRADED` / `PAGE_OVERFLOW_TWO_PAGES` / `PAGE_OVERFLOW`，来自单页适配循环，见 ARCHITECTURE §7.5.1 与 `details` 字段约定）；② **内容裁剪**（`EMOJI_STRIPPED` / `COURSES_TRIMMED` / `MISSING_SLOTS_RENDERED`）；③ **文本校验**（`TEXT_LAYER_MISMATCH` / `CID_GLYPH_MISSING` / `CID_GLYPH_RESIDUAL`）。数组顺序按 ①→②→③，同码只保留一条并合并 `details`。**任何一条都不得只写日志不上响应**——用户看不到的告警等于没告警。
- 202 → `{"job_id": "...", "queued": true}`；完成后 `GET /jobs/{id}` →
```json
{ "ok": true, "data": {
  "job_id": "job_01J9Z...", "status": "succeeded", "progress": 100,
  "result_json": {
    "artifacts": [ { "id": "art_1", "format": "pdf", "engine": "reportlab",
      "filename": "数据分析实习生-张三-示例大学.pdf",
      "rel_path": "2026/rb_01J9Z/数据分析实习生-张三-示例大学.pdf",
      "bytes": 84211, "sha256": "...", "text_verified": true, "text_diff_json": [],
      "warnings_json": [ { "code": "EMOJI_STRIPPED", "count": 0 } ],
      "download_url": "/api/v1/artifacts/art_1/download" } ],
    "naming": { "pattern": "{position}-{name}-{school}", "resolved": "数据分析实习生-张三-示例大学",
                "variables": { "position": "数据分析实习生", "name": "张三", "school": "示例大学" } }
  }
}, "request_id": "..." }
```
- `text_verified=false` 时 `warnings_json` 必带 `TEXT_LAYER_MISMATCH`，UI 必须显著提示（ATS 风险）。

---

#### 8.4.1 来源冲突的用户决议（`extra_json.conflict_resolution`，v1.38）

用户已就中英来源不一致做出决定：**以中文简历的 GPA 与到岗时间为准，且允许用户随时改**。契约层面把「冲突」拆成两态，**决议只降噪，不改值**：

| 态 | 判据 | `SOURCE_CONFLICT` | 渲染值 |
|---|---|---|---|
| **未决议** | `extra_json.conflict_resolution.fields[field]` 不存在 | `severity="warn"`，message 请用户确认 | 按语言各取各来源（zh 出中文数、en 出英文表述），**禁止合并** |
| **已决议** | 该 `field` 的值 ∈ `{"zh","en"}` | `severity="info"`，`details{field, zh_value, en_value, resolved, decided_at}`，message「已按中文版为准（可在个人资料里改）」 | **与未决议完全相同**——仍是按语言取对应真值（en 侧现在已是中文数值的英译，例 `Available: Late January 2027` / `GPA 3.56/4`） |

三条硬规则：

1. **决议不是开关，也不是数据迁移**：它只写 `extra_json`，**不改 `template_block.static_text`，不改 `user_profile` 的数值**。想改数值请走 `PUT /profile/education-facts`（教育段）或 `PUT /profile`（到岗时间）——**两个入口，别混**。
2. **可逆**：删除 `fields[field]` 即回到 `warn`（验收 AC-CONFLICT-02 必测反向，防「决议写死永不恢复」）。
3. **`decided_by` 必须是 `"user"`**：自动化流程（含 LLM）**不得**自行写 `conflict_resolution`；若实现要「自动推荐一个默认值」，只能作为 UI 建议，落库必须由用户点击。

### 8.5 语言（`lang`）契约：词表、变体过滤、导入语言

> 起因（2026-10-23 实测）：库中 `template` 活跃 1 条 `lang='zh'`，`package_bullet_variant` **54 条全为 `lang='zh'`，零条 `en`**；而英文导出产物正文是「教育背景 / 项目经历 / 【示例】小象超市…」。即 **`lang=en` 的导出实际是「中文模板 + 中文变体 + 英文文件名」**——语言这一维在数据里没有对立面。本节把三处缺口定死。

#### 8.5.1 结构词表（**确定性映射，本地硬编码，不走 LLM**）

`template_block.heading` 渲染时按下表映射；**不在表中的自定义 heading（如用户手写的「科研经历」）保留原文并记 `LANG_HEADING_UNMAPPED{heading, lang}`**，**不得静默直译、不得交给 LLM 翻译**。

| `block.kind` | zh | en |
|---|---|---|
| `education` | 教育背景 | Education |
| `experience` | 实习经历 | Experience |
| `projects` | 项目经历 | Projects |
| `campus` | 校园活动 | Campus Activities |
| `skills` | 职业技能 | Skills |
| `summary` | 个人总结 | Summary |
| `honors` | 荣誉奖项 | Honors & Awards |

字段标签与格式（同表硬编码）：

| 项 | zh | en |
|---|---|---|
| 到岗 | `到岗时间：2027年1月下旬` | `Available: Late Jan 2027` |
| 就读期间 | `2024.09 – 2028.06` | `Sep 2024 – Jun 2028` |
| GPA 标签 | `专业成绩` | `GPA` |
| 主修课程 | `主修课程：…` | `Relevant Coursework: …` |
| 证件照 | 显示（右上） | 显示（右上） |

#### 8.5.2 变体按 `lang` 过滤（**允许回退，不许静默回退**）

- 装配 `lang=en` 时**只取 `variant.lang='en'`**；`lang=zh` 只取 `'zh'`。不得混用两种语言的 bullet。
- 某条目**一条 en 变体都没有** ⇒ 记 **`LANG_FALLBACK`**，导出页显示「以下条目沿用中文原文」，条目仍然渲染（**不得留空段**）。
  - `details{entry_count, bullet_count, entries:[{entry_key, title, lines:[{text, chars}]}], sample[]}`——**必须有逐条清单，不能只给总数**：用户要能点进去看哪几句是中文。
  - 导出响应另给 `meta.lang_fallback_lines`（回退渲染行数，整数）与 `warnings[LANG_FALLBACK].details.entries` 行数**相等**（两处口径一致，t11 直接比对）。
- 反向条款：`LANG_FALLBACK` 为 0 时不得出现在 `warnings[]`；`lang=zh` 导出**永不**产生 `LANG_FALLBACK`（zh 是原始语言）。

#### 8.5.3 导入必须产出对应语言的资产

`POST /imports` 时检测并落 `import_job.source_lang ∈ {zh, en, unknown}`（按正文 CJK 字符占比，阈值 ≥30% 判 `zh`，≤5% 判 `en`，中间判 `unknown`）。`commit` 且 `also_create_packages=true` 时，创建的 `package_bullet_variant.lang` **必须等于 `import_job.source_lang`**（`unknown` 时退回 `template.lang`），**不得一律写 `'zh'`**。

反向条款：`source_lang='en'` 的导入**不得**产出 `lang='zh'` 变体；同一 `bullet_key` 允许同时存在 `zh`/`en` 两条变体（唯一键为 `(package_id, bullet_key, tone, lang)`）。

#### 8.5.4 `degree`/`major` 的多语言：**新增独立列，不并入 `profile_fields_source`**

**定版选择：新增 `user_profile.degree_en` / `major_en`**（沿用既有 `name_zh`/`name_en`、`school_zh`/`school_en` 的双列先例），理由是**可空、可测、可反向断言**；`profile_fields_source` 只记「来源」，不承担承载值。

- `degree_en`/`major_en` 可为 NULL；NULL 时 **en 版省略该行**并记 `PROFILE_FIELD_MISSING{field:"degree_en"}`，**不得把「本科」塞进英文简历**。
- 反向条款：**zh 版不得出现 `B.M.`/`B.S.`/`M.S.` 等英文学位缩写**（`degree_en` 只进 en 版）。
- 取值示例：用户英文简历写 `B.M. in Management Science (Business Data Analytics)` → `degree_en='B.M.'`、`major_en='Management Science (Business Data Analytics)'`；`degree='本科'`、`major='管理科学（商务数据分析）'` 保持中文侧。

### 8.6 页眉构成白名单与教育段日期（v1.33，CMP-40 / CMP-39）

#### 8.6.1 页眉只允许四类内容

用户原简历（中文第十版、英文版**都是**）页眉只有姓名 + 联系方式。实现曾把 `education_line` 拼成 `本科 | 管理科学（商业数据分析） | 2028` 放进页眉，与教育段**重复**一次。

> **页眉（`ir.header`）只允许**：`name`（按 `lang` 取 `name_zh`/`name_en`）、`phone`、`email`、`available_note`。
> **`degree`/`major`/`grad_year`/`city` 一律不得进页眉**——它们属教育段与个人资料页。

**`available_note` 的来源优先级（v1.38 定版，用户决定：中文简历为准、可自行修改）**：

| `lang` | 取值顺序 | 缺失时 |
|---|---|---|
| `zh` | `user_profile.available_note` | 省略该行（**不报冲突**，记 `PROFILE_FIELD_MISSING`） |
| `en` | ① `extra_json.available_note_en` → ② `available_note`（中文原文） | 两级都空才省略 + `PROFILE_FIELD_MISSING` |

- `available_date` **不参与渲染**（历史列，仅在旧数据兼容与筛选里可读）。
- `extra_json.available_note_en` 为空时**回退中文值**，不省略——用户明确要求中英两版都显示到岗时间。
- **`available_note` 是唯一可编辑真源**；`available_note_en` 是可选的英译表述，**不得**反过来作为中文值来源，也**不得**由 `available_date` 拼接生成。


- **禁止字段名**：`education_line`（拼串字段**不得存在**，出现即判违规；其历史语义已由教育段承担）。
- **机器判据**：导出 PDF 的**前 4 行文本**内出现 `本科|硕士|博士|大专|B\.M\.|B\.S\.|M\.S\.|M\.Sc\.|Ph\.D\.|Bachelor|Master` 任一 ⇒ **FAIL**。
- 允许的行数与呼吸感由 `density` 决定，**但内容项固定为上述四类**。

#### 8.6.2 教育段日期必须渲染 `entry.date_range` 原文

实测：`draft.entry.date_range = 2024.9-2028.6`，PDF 教育段日期却只剩 `2028`（被 `grad_year` 顶替）。

> 教育段日期列**必须**渲染 `entry.date_range` 原文（`2024.9-2028.6`）；
> **不得替换为 `grad_year`**。`grad_year` 只用于**筛选/排序**与英文 `Class of 2028` 表述，**不进日期列**。

- 缺 `date_range` 时：日期列**留空**（不猜、不用 `grad_year` 兜底），并记 `warnings[PROFILE_FIELD_MISSING]{fields:["date_range"]}`。
- 机器判据：PDF 教育段抽取文本必须包含 `2024` 与 `2028` 两个年份串（`2024.9-2028.6` 或 `Sep 2024 – Jun 2028` 等归一化后）；只出现单个年份 ⇒ FAIL。

## 9. 命名模板（用户偏好 `{position}-{name}-{school}`）

### 9.1 语法

```
pattern   := ( literal | var | escape )*
var       := '{' name ( ':' fmt )? '}'
name      := [a-z][a-z0-9_]*          // 白名单见 9.3，未知名字 → NAMING_UNKNOWN_VAR
fmt       := strftime 子集: %Y %m %d %H %M   // 仅 date 支持
escape    := '{{' → '{' ,  '}}' → '}'
```

- 默认值：`{position}-{name}-{school}`（用户偏好「岗位-姓名-学校」）。
- 例：`数据分析实习生-张三-示例大学.pdf`（扩展名由 `format` 决定，**不在模板里写**；写了 `{ext}` 视为未知变量）。
- 模板本身必须以 `.` 之外的可见字符结尾；净化后为空 → `NAMING_EMPTY`。

### 9.2 解析规则（`services/naming.py::resolve`）

| 变量 | 来源（按顺序回退） | 语言相关 | 缺失时 |
|---|---|---|---|
| `{name}` | `profile.name_zh`（`lang=zh`）/ `profile.name_en`（`lang=en`） | ✅ | `NAMING_MISSING_VAR` |
| `{school}` | `profile.school_zh` / `profile.school_en` | ✅ | `NAMING_MISSING_VAR` |
| `{position}` | `build.position` → `job_description.title` → `build.naming_overrides_json.position` | ❌ | `NAMING_MISSING_VAR` |
| `{company}` | `build.company` → `company_profile.company_name` → `naming_overrides_json.company` | ❌ | `NAMING_MISSING_VAR` |
| `{date}` | 导出时刻（本地时区） | ❌ | 不会缺失；默认 `YYYYMMDD`，可用 `{date:%Y-%m-%d}` |
| `{version}` | `naming_overrides_json.version` → 默认 `v1` | ❌ | 不会缺失 |
| `{lang}` | `build.lang` | ❌ | 不会缺失 |

- **优先级**：`naming_overrides_json` 里显式给的同名变量 **覆盖** 上面的自动来源（但值为空字符串视为未给）。
- 解析完再净化（§9.4）；净化造成的改动记 `warnings[]`（`NAMING_SANITIZED`）。

### 9.3 `POST /api/v1/naming/validate`（纯函数，**恒 200**）
```json
// 请求
{ "pattern": "{position}-{name}-{school}", "build_id": "rb_01J9Z...", "format": "pdf" }
// 200 响应（合法）
{ "ok": true, "data": {
  "valid": true, "resolved": "数据分析实习生-张三-示例大学",
  "filename": "数据分析实习生-张三-示例大学.pdf",
  "variables": [ { "name": "position", "value": "数据分析实习生", "source": "build.position" },
                 { "name": "name", "value": "张三", "source": "profile.name_zh" },
                 { "name": "school", "value": "示例大学", "source": "profile.school_zh" } ],
  "warnings": [], "errors": [] }, "request_id": "..." }
// 200 响应（不合法）
{ "ok": true, "data": {
  "valid": false, "resolved": null, "filename": null, "variables": [
    { "name": "position", "value": "数据分析实习生", "source": "build.position" },
    { "name": "name", "value": "张三", "source": "profile.name_zh" },
    { "name": "school", "value": null, "source": null } ],
  "warnings": [],
  "errors": [ { "code": "NAMING_MISSING_VAR", "vars": ["school"],
                "message": "变量 {school} 无值：UserProfile.school_zh 为空" } ] }, "request_id": "..." }
```
> 为什么纯函数返 200：这是 UI 边输边校验的接口，`valid:false` 是正常业务结果而非请求错误。**导出时**同样的错误会以 422 + 同款 `code` 返回，前端可复用同一套渲染逻辑。

### 9.4 净化规则（顺序执行，全部可测）

1. Unicode `NFC` 归一化。
2. 剥离 emoji（`unicodedata.category(c) == "So"`）与控制字符（`Cc`）。
3. 替换禁止字符 `\ / : * ? " < > |` 为 `-`。
4. 折叠连续 `-`、连续空格为单个；空格改 `-`（文件名不含空格）。
5. 去掉首尾的 `空格 . - _`。
6. 若包含 `..` → 替换为 `._`；若结果 ∈ Windows 保留名（`CON PRN AUX NUL COM1-9 LPT1-9`，大小写不敏感）→ 前缀 `_`。
7. 截断到 **120 个字符**（同时保证 UTF-8 ≤ 200 字节，避免 APFS 255 字节上限）；截断写 `NAMING_TRUNCATED` 警告。
8. 净化后为空 → `NAMING_EMPTY`；超过上限未被允许 → 不会发生（截断优先）。

写盘时若目标已存在且 `overwrite=false` → 追加 `-2`、`-3`…（**不改动 `resolved`，只改实际 `filename`**，并在 artifact 上标 `collision_suffix: "-2"`）。

### 9.5 命名相关错误码

| code | HTTP | details |
|---|---|---|
| `NAMING_UNKNOWN_VAR` | 422 | `{unknown_vars:[...], allowed_vars:[...]}` |
| `NAMING_MISSING_VAR` | 422 | `{missing_vars:[...], pattern, source_checked:{school:"profile.school_zh"}}` |
| `NAMING_EMPTY` | 422 | `{pattern, sanitized:""}` |
| `NAMING_TOO_LONG` | 422 | 仅在**模板字面量本身**超 200 字符时（截断不覆盖这种情况）`{len, max:200}` |
| `NAMING_SYNTAX` | 422 | 未闭合 `{`、非法 fmt `{unclosed_at:12}` |
| `NAMING_INVALID_CHARS` | 422 | 保留：仅当净化后仍含路径分隔符（防御性，正常不会触发） |

### 9.4.1 命名相关 `warnings` 码（不是错误，`valid` 仍可为 true）

| code | 触发 | 前端表现 |
|---|---|---|
| `NAMING_SANITIZED` | 任一净化步骤改变了字符（`/`→`-`、非法字符、保留名加前缀、`..`→`._`） | 灰字「文件名已自动规范化」 |
| `NAMING_TRUNCATED` | 触发 120 字符截断 | 黄字「名称过长已截断，可缩短模板」 |
| `EMOJI_STRIPPED` | 剥离 emoji/控制字符 | 黄字「已移除表情符号」 |
| `NO_VARIABLE` | 模板不含任何变量（纯字面量） | 灰字「该名称不含变量，多次导出可能重名」 |
| `NAMING_COLLISION_SUFFIXED` | 同名冲突后追加 `-2`/`-3` | 绿字「已另存为 xxx-2.pdf」 |

> 硬要求：**模板缺变量必须报错，绝不产出残缺文件名**（如 `-张三-示例大学.pdf` 或 `数据分析实习生--示例大学.pdf` 都是禁止的）。

---

## 10. LLM 适配层（唯一出网口）

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/llm/status` | 当前 provider/model/key_set/ready/last_error |
| `POST` | `/llm/preview` | **生成将发送的完整 payload + 字段清单**（不发送） |
| `GET` | `/llm/previews/{id}` | 回看某次预览（审计/复现） |
| `POST` | `/llm/complete` | 携带 `preview_id` 真正发送 |
| `POST` | `/llm/previews/{id}/reject` | 用户取消（`status=rejected`） |
| `GET` | `/llm/egress-log` | 出网审计列表（`?since=&limit=`，**只有字段名，无正文**） |

### 10.1 `POST /api/v1/llm/preview`

请求（**只传 ID，不传正文** —— 这是「显式选中片段」的机器保证）：
```json
{
  "purpose": "bullets_generate",
  "provider_override": null,
  "selections": {
    "package_ids": ["pkg_a"],
    "variant_ids": ["var_1", "var_5", "var_9"],
    "include_summary": false,
    "jd_id": null,
    "company_profile_id": null,
    "extra_instruction": "语气务实，避免形容词堆砌"
  },
  "options": { "temperature": 0.3, "max_tokens": 1200, "auto_redact": ["phone", "email"] }
}
```
- 服务端**只**按 ID 取内容；`package_ids` 里未在 `variant_ids` 出现的 bullet 不进 payload。
- `include_summary=false` 时 `package.summary` 不进 payload。
- `attachment.privacy='private'` 的内容、`profile.phone/email` **永不进 payload**（即使被 `extra_instruction` 提到也会被剥除）。
- 请求体里携带自由文本（`extra_instruction`）是允许的，但会在 `fields[]` 中作为 `kind:"user_instruction"` 明示。

### 10.2 响应：**「将发送字段清单」的结构（契约核心）**

```json
{ "ok": true, "data": {
  "preview_id": "pv_01J9Z3K2ABCD",
  "purpose": "bullets_generate",
  "provider": "deepseek",
  "model": "deepseek-chat",
  "endpoint_host": "api.deepseek.com",
  "expires_at": "2026-10-23T02:51:12+08:00",

  "payload": {
    "model": "deepseek-chat",
    "temperature": 0.3,
    "max_tokens": 1200,
    "response_format": { "type": "json_object" },
    "messages": [
      { "role": "system", "content": "你是简历改写助手。只可改写给定句子，不得新增事实。" },
      { "role": "user", "content": "[pkg_a] 订单中台重构 / 后端开发实习生\n- 重构订单中台读写链路…\n- …" }
    ]
  },
  "payload_sha256": "9f2c1d…",
  "total_chars": 1284,
  "est_tokens": 812,

  "fields": [
    { "path": "messages[0].content", "label": "系统指令（内置，固定）", "kind": "system_prompt",
      "source": "builtin", "source_id": null, "chars": 42, "est_tokens": 30, "included": true, "redacted": false },
    { "path": "messages[1].content", "label": "订单中台重构 · impact bullet", "kind": "resume_fragment",
      "source": "package_bullet_variant", "source_id": "var_1", "package_title": "订单中台重构",
      "chars": 74, "est_tokens": 48, "included": true, "redacted": false },
    { "path": "messages[1].content", "label": "订单中台重构 · technical bullet", "kind": "resume_fragment",
      "source": "package_bullet_variant", "source_id": "var_5", "package_title": "订单中台重构",
      "chars": 96, "est_tokens": 61, "included": true, "redacted": false },
    { "path": "messages[1].content#instruction", "label": "附加指令（用户输入）", "kind": "user_instruction",
      "source": "request", "source_id": null, "chars": 16, "est_tokens": 12, "included": true, "redacted": false }
  ],

  "excluded": {
    "packages_total": 12, "packages_selected": 1,
    "variants_total": 41, "variants_selected": 2,
    "skipped": [
      { "kind": "resume_source_file", "reason": "隐私文件不参与 LLM", "count": 2 },
      { "kind": "profile_pii", "reason": "手机/邮箱不入 payload", "count": 2 }
    ],
    "note": "未选中的 10 个 Package 与 39 条变体不会被发送"
  },

  "redactions": [
    { "path": "messages[1].content", "match": "phone", "value_preview": "178****0929",
      "replacement": "[PHONE]", "count": 1 }
  ],

  "warnings": [ { "code": "PROMPT_NEAR_LIMIT", "message": "预计 812 tokens，接近建议上限 1000" } ]
}, "request_id": "..." }
```

### 10.2.1 宽路径脱敏契约（用户拍板，必须逐条实现）

**可发送**：经历/项目文本（选中的 variant）、JD 文本、公司名与岗位名、用户备注、下行抓到的公开页面正文、**学校名的真实值**、学历/专业/届别/城市/到岗时间。
**候选人档案段（可上云七项）**：`{school, school_tier, degree, major, grad_year, city, available_date}` 按真实值发送；这是 `prompts.py` 的 `ALLOWED_SOURCES` 增 `"profile"` 的唯一契约依据（定义见 DATA-MODEL §1「可上云的候选人档案段」）。字段投影用白名单（`llm_brief()`），**不得**整行序列化 profile。

**永不上云**：姓名、电话、邮箱、照片、身份证/学号 —— 在 `services/llm_payload.py` 里替换为占位符后发送，真实值只在 `render_*` 阶段回填。

> **v1.6 口径变更（用户 m00265 最终版，覆盖此前「学校名也脱敏」）**：学校名**真实传输**（撤销 `[SCHOOL]` 占位符）——院校层次、校招节奏、届别推应届身份都有分析价值，标识风险低于收益；姓名/电话/邮箱是纯标识零分析价值，仍必须脱敏。

| 字段 | 占位符 | 备注 |
|---|---|---|
| `name_zh` / `name_en` | `[NAME]` | 正文中出现的姓名（含英文大写形式）一并替换 |
| `phone` | `[PHONE]` | 覆盖 `+86`、空格、短横线变体 |
| `email` | `[EMAIL]` | |
| 照片 | **无字段** | `payload` 内不得出现 base64 图像；`photo_*` 一律不进 `fields[]` |
| 身份证/学号 | `[ID]` | 正则命中 |

- `fields[]` 每项在脱敏命中时 `redacted:true`，`excluded.skipped[]` 必须有 `{"kind":"profile_identity","reason":"姓名/联系方式/照片不入 payload","count":N}`。
- `redactions[]` 每项 `{path, match, value_preview, replacement, count}`；`replacement` 必须是上表占位符之一。
- 服务端**必须**有自检：`assert not re.search(real_name|real_phone|real_email, json.dumps(payload))`，命中即 500 `INTERNAL`（宁可失败也不发出去）。**学校名不在自检名单内**（允许真实出现）。验收 AC-PRIV-12。
- LLM 输出中的 `[NAME]`/`[PHONE]`/`[EMAIL]`/`[ID]` 占位符**原样入库**，渲染时回填。

**前端契约（uier 必读）**
- 必须至少映射展示 `fields[{label, kind, chars, included}]`，`kind` 的中文名：`resume_fragment`=简历片段 / `system_prompt`=系统指令 / `user_instruction`=你的附加要求 / `jd_text`=JD 原文 / `company_note`=公司备注。
- 必须展示 `excluded.note` 与 `redactions`（脱敏更要说清楚）。
- 「确认发送」按钮文案必须包含 `est_tokens` 与目标 `provider/model`。
- `payload` 可折叠展示（`<pre>` + 等宽字体），但**默认收起**。
- 取消 → 调 `reject`，不保留任何发送可能。

### 10.3 `POST /api/v1/llm/complete`
```json
{ "preview_id": "pv_01J9Z3K2ABCD", "expected_payload_sha256": "9f2c1d…" }
```
- 必填 `preview_id`；`expected_payload_sha256` 可选但推荐（双保险）。
- 服务端：`UPDATE llm_preview SET status='consumed', consumed_at=... WHERE id=? AND status='pending' AND expires_at > now` → 受影响行数必须为 1，否则按 §14 报错。**一次性**。
- 响应：
```json
{ "ok": true, "data": {
  "preview_id": "pv_01J9Z3K2ABCD",
  "raw_text": "{\"variants\":[...]}",
  "parsed": { "variants": [ { "bullet_key": "b1", "tone": "impact", "text": "…" } ] },
  "usage": { "prompt_tokens": 812, "completion_tokens": 260, "total_tokens": 1072 },
  "provider": "deepseek", "model": "deepseek-chat", "latency_ms": 2140,
  "finish_reason": "stop"
}, "request_id": "..." }
```
- `parsed` 由 `purpose` 决定 schema（见各业务端点）；解析失败不抛错而是 `parsed=null` + `warnings[{code:"LLM_JSON_UNPARSABLE"}]`，由调用方决定是否重试。

### 10.4 失败与重试（连接级 / HTTP 级 / 鉴权级 三类，路径不同）

| 失败类别 | 判定依据 | 是否重试 | 最终错误 |
|---|---|---|---|
| **连接级异常**（TLS 握手失败 / DNS / 连接被拒 / 协议中断） | 没有 HTTP 状态码：**`httpx.ConnectError`、`httpx.ReadError`、`httpx.RemoteProtocolError`、`httpx.ConnectTimeout`、`ssl.SSLError`（含伪装成 ConnectError 的 `[SSL: UNEXPECTED_EOF_WHILE_READING]`）** 任一命中即归此类。实测 `[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1032)` 约 **1/12** 概率 | **是**，上限 `LLM_MAX_RETRIES`（默认 **2**：1 次不够，实测 2 次后 12/12 成功） | `LLM_UNREACHABLE`(503)，`details{kind:"connect", host, attempts, reason}`。**禁止**映射为 `LLM_NOT_CONFIGURED` 或 401 语义 |
| **HTTP 级错误**（429 / 5xx / 读超时） | 有状态码或已在等响应体 | **是**，同一上限 `LLM_MAX_RETRIES` | `LLM_RATE_LIMITED`(429) / `LLM_UPSTREAM_ERROR`(502) / `LLM_TIMEOUT`(504) |
| **鉴权失败**（401 / 403） | 有状态码 | **否**（错的 key 重试也是错的） | `LLM_UPSTREAM_ERROR`(502)，`details.http_status` |

> 两种可重试类别**共用** `LLM_MAX_RETRIES`（默认 2，即最多 3 次尝试），不设第二个开关——实测的失败是同一类「瞬态网络」问题，分开配置只会让其一被漏调。

**consent 与重试的关系（关键）**
- 只有在**拿到 HTTP 响应**（任意状态码）后才把 `llm_preview.status` 置 `consumed`。连接级失败意味着请求体根本没发出去 → preview **仍为 `pending`**，用户可以原样再点一次「发送」，不触发 `LLM_CONSENT_MISMATCH`。
- 同一次 complete 内部的自动重试**不重复计费审计**：`llm_call_log` 记 N 条 attempt（`attempt_no`），只有最后一次决定 `ok`。

**上游超时预算**：**以 `GET /api/v1/settings` 的 `data.timeouts` 为准**（实测默认 `connect_s=5.0`、`read_s=175.0`、`total_s=180.0`；v1.16 前本文写的 60/90 与实现不符，已废）。`.env` 的 `LLM_TIMEOUT_SECONDS` 可调；连接级重试不累加 total 预算，每次 attempt 独立计时。前端**不要硬编码**这三个数，一律读 `settings.timeouts`。

**错误码**：`LLM_DISABLED`(503) / `LLM_NOT_CONFIGURED`(503) / `LLM_JSON_MODE_PRECONDITION`(422, 本地) / `LLM_UNREACHABLE`(503) / `LLM_UPSTREAM_ERROR`(502) / `LLM_TIMEOUT`(504) / `LLM_RATE_LIMITED`(429) / `LLM_BAD_RESPONSE`(502) / `EGRESS_BLOCKED`(403)。

### 10.5 上游调用约定（服务端实测硬约束，2026-10-23）

> 架构侧同步见 `ARCHITECTURE.md` §5.5（F1–F4）。**这一节是 builder 实现 `llm_client` / `llm_prompt` 时必须逐条满足的前置条件。**

**1. `response_format=json_object` 的前置条件（F2）**
- 服务端要求 messages 中出现**字面量 `json`**，否则 400：`Prompt must contain the word 'json' in some form to use 'response_format' of type 'json_object'`（`deepseek-chat` 与 `deepseek-reasoner` 一致）。
- 约定：所有 JSON 用途由 `llm_prompt.build_messages()` 注入固定指令（含 `json` 字样），**发送前本地断言**。
- 断言失败属于**本地前置校验失败，不是服务端错误**：返回 422 **`LLM_JSON_MODE_PRECONDITION`**，`details{reason:"PROMPT_MISSING_JSON_LITERAL", purpose}`，**零出网**（`llm_call_log` 记一条 `rejected`，`http_status=null`）。
- 这属于我们自己的 bug，不是可重试的上游错误 —— **禁止**归入 `LLM_UPSTREAM_ERROR` 或任何重试路径。

**2. `deepseek-reasoner` 支持 `json_object`（F3，修正此前假设）**
- 实测 `max_tokens=512` → 200 + 合法 `{"ok":true}`。**不得**因「reasoner 不支持 json 模式」关闭 `response_format` 或改走纯文本。
- 降级链保留：`json.loads` 失败 → 从文本里抽取第一个 `{…}` → pydantic schema 校验；理由改为「模型**可能**返回非法 JSON」。全部失败 → `parsed=null` + `warnings[{code:"LLM_JSON_UNPARSABLE"}]`。

**3. 推理截断导致空输出（F4）**
- `deepseek-reasoner` 的 `reasoning_tokens` 与输出 `content` **共享 `max_tokens` 预算**：`max_tokens=16` → `finish_reason="length"`、`content=""`、`reasoning_content` 非空。
- 处理：`content` 为空（或 strip 后为空）视为**无有效输出** → **`LLM_TRUNCATED`**(502)，`details.reason="empty_content"`。**不自动重试**（重试同样烧预算）；UI 提示「输出被截断，请提高输出上限」。
- 非空但 `finish_reason="length"`（半截 JSON / 半句话）→ **同样是错误** `LLM_TRUNCATED`(502)，`details.reason="partial_json"`。**不存在「截断了但仍可用」的成功路径**（半截简历 bullet 不可交付），因此不返回 `warnings`、不落库。
- **不变量：空 `content` 永不入库** —— 不写 `package_bullet_variant`、不写 `jd_requirement`、不写 `company_profile`、不写 build 字段。
- 默认 `max_tokens`：分析类用途（`jd_analyze` / `company_profile` / `match_score`）**≥ 2048**；生成类用途（`bullets_generate` / `rewrite`）≥ 900。可由 `app_setting.max_tokens_analysis` / `max_tokens_generate` 调高。

**4. 响应字段的透出约定**
- 必须原样透出：`finish_reason`、`usage{prompt_tokens, completion_tokens, total_tokens}`、`completion_tokens_details.reasoning_tokens`（若上游给）。
- **两个码互不重叠、判定只看 `finish_reason` + 解析结果**：

| `finish_reason` | `content` | 结果 | 落库 |
|---|---|---|---|
| `length` | 空 | **`LLM_TRUNCATED`**(502)，`details.reason="empty_content"` | 否 |
| `length` | 非空（半截 JSON 或半句话） | **`LLM_TRUNCATED`**(502)，`details.reason="partial_json"` | 否 |
| `stop` | 完整但非法 JSON / 缺必填字段 | **`LLM_BAD_RESPONSE`**(502) | 否 |
| `stop` | 合法且字段齐全 | 200 | 是 |
| 其他（`content_filter`/`tool_calls`/缺失） | 任意 | `LLM_BAD_RESPONSE`(502)，`details.reason` 原样带 `finish_reason` | 否 |

- **`LLM_TRUNCATED` 的 `details` 必带**：`finish_reason`（固定 `"length"`）、`completion_tokens`、`max_tokens`；上游若给 `completion_tokens_details.reasoning_tokens` 则一并带（reasoner 场景就是靠它定位「推理烧光预算」）。前端据此提示「输出被截断（{completion_tokens}/{max_tokens} tokens），请提高输出上限或缩短输入」。
- **截断错误码单一真源**：`LLM_TRUNCATED`(502)。它同时覆盖「截断成空」与「截断成半截 JSON」；不用 `LLM_BAD_RESPONSE` 表达截断（`LLM_BAD_RESPONSE` 只表示上游返回了**完整但不是合法 JSON / 缺字段**）。理由（captain 2026-10-23 裁定）：截断是独立故障模式，处置动作（提高 `max_tokens` / 缩短输入）与非法 JSON（改 prompt / schema）完全不同，且必须能单独计数回答「是不是我的 max_tokens 给低了」。

---

## 11. 设置

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/settings` | `?include_secrets=false`（**永远没有 secrets**） |
| `PUT` | `/settings` | 更新 `provider/model/model_analysis/base_url/timeouts/auto_redact/naming_template/default_engine/verify_text/photo_in_export/allow_web_fetch/max_tokens_analysis/max_tokens_generate`（写入 `.env` 与 `app_setting`） |
| `POST` | `/settings/api-key` | 仅写：`{api_key}` → 写入 `.env` 的 `LLM_API_KEY`（`chmod 600`）；响应 `{key_set:true}`，**不回显** |
| `DELETE` | `/settings/api-key` | 清除：把 `LLM_API_KEY=` 置空（保留变量名，不删行） |
| `POST` | `/settings/provider/test` | 探活：`GET {base}/models`，5 s 超时，返回 `{reachable, http_status, models[], latency_ms, error_code?}` |
| `GET` | `/settings/export-all` | 数据可携带：打包 `app.db + files/ + exports/` 为单个 zip（**绝不包含 `.env`**），返回 `{path, bytes, sha256}`；同步生成，>2 s 转 Job |

`GET /settings` 响应（**key 只以布尔存在**）：
```json
{ "ok": true, "data": {
  "provider": "deepseek", "model": "deepseek-chat", "model_analysis": "deepseek-chat",
  "base_url": "https://api.deepseek.com/v1",
  "key_set": true, "key_field": "LLM_API_KEY",
  "timeouts": { "connect_s": 5.0, "read_s": 175.0, "total_s": 180.0 },
  "allowed_hosts": ["api.deepseek.com"],
  "auto_redact": ["name", "phone", "email"],
  "allow_web_fetch": true,
  "fetch_hosts": ["jobs.bytedance.com", "*.zhipin.com", "*.lagou.com", "*.liepin.com"],
  "photo_in_export": true,
  "app_port": 8765,
  "app_url": "http://127.0.0.1:8765",
  "ui": { "theme": "light", "page_size": "A4", "last_template_id": "tpl_01J9Z..." }
}, "request_id": "..." }
```

**`auto_redact` 的可选值只有 `name` / `phone` / `email` / `id`（v1.17 定版，P1 待 coder 收口）**

- **`school` 不在可选值内**：请求带 `school` → 422 `VALIDATION_ERROR`。理由：ADR-20 规定校名**必须真实发送且必须被消费**；允许用户关掉它会让 `school_signal` 退化为 `SCHOOL_SIGNAL_UNUSED`——付了隐私成本、收益归零。
- **`name` 永远脱敏**（即使 `auto_redact` 不含 `name` 也照样替换）——用户不可关闭。
- ⚠️ 实现现状（`models.py:SettingsPatch` 的 Literal 仍含 `"school"`）与本节不符，**P1 归 coder**（§17.8 第 6 项）；**契约以本节为准**。

> - `allow_web_fetch`：下行抓取总开关（默认 `true`）；`fetch_hosts` 为**只读派生值**（内置招聘站表 + 已确认公司官网域名），`PUT` 传了也忽略。
> - `photo_in_export`：导出是否默认带照片（默认 `true`，单次导出可用 `include_photo` 覆盖）。
> - `app_port` / `app_url`：**实际监听端口与地址**，与 `data/runtime/app_port` 同源（只读）。该文件的契约见 ARCHITECTURE §3.3：**JSON 五字段** `{port,host,url,pid,started_at}`，原子写入，消费者一律 `json["port"]`，**不得当纯数字解析**。
> - `provider` 枚举固定 `deepseek \| openai_compatible \| off`；**`ollama` 不受支持**（用户决策，见 ARCHITECTURE ADR-17），传入即 422 `VALIDATION_ERROR` `details.reason="UNSUPPORTED_PROVIDER"`。
> - `allowed_hosts` 与 `key_field` 是**只读派生值**（分别来自 `LLM_BASE_URL` 主机名与固定变量名），`PUT /settings` 传了也忽略。
> - `model_analysis` 见 ARCHITECTURE §5.3（重推理任务单独用 `LLM_MODEL_ANALYSIS`）。
> - 硬要求：**key 的任何片段（含后 4 位）都不允许出现在任何响应、日志、错误消息里**。

---

## 12. 文件与产物

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/files/{attachment_id}` | 下载/预览原件（`Content-Type` 按 mime；`Content-Security-Policy: sandbox`） |
| `GET` | `/artifacts/{id}/download` | 下载导出产物，`Content-Disposition: attachment; filename*=UTF-8''<encoded>` |
| `GET` | `/artifacts/{id}/thumb` | 可选：PDF 首页缩略图（无渲染依赖时返回 404，前端降级为图标） |

所有路径参数先解析并断言在 `data/` 内，否则 `PATH_ESCAPE`(400)。

---

## 13. Job（长任务）

`GET /api/v1/jobs/{id}`
```json
{ "ok": true, "data": {
  "id": "job_01J9Z...", "kind": "build_export", "status": "running", "progress": 40,
  "message": "正在排版…", "result_json": null, "error_json": null,
  "created_at": "...", "finished_at": null
}, "request_id": "..." }
```
- `status ∈ {queued, running, succeeded, failed, interrupted}`。
- 轮询建议 500 ms，前端用 `setTimeout` 递归而非 `setInterval`（避免堆叠）。
- 进程重启后 `running → interrupted`，UI 显示「已中断，可重试」。
- 并发限制：同一 `build_id` 的导出同时只允许 1 个，否则 `JOB_IN_PROGRESS`(409)。

---

## 14. 错误码全表

> **本表共 40 条。** 统计方式（机械可复算，t11 直接跑，期望 **40**）：
> `awk '/^## 14\. 错误码全表/,/^## 14\.1/' docs/API-CONTRACT.md | grep -Ec '^\| `[A-Z][A-Z0-9_]+` \| [0-9]{3} \|'`
> 即「表格行 + 3 位 HTTP 状态码」才算一条错误码。**增删任何一条必须同步改本行数字**，t11 计数对不上即判文档缺陷。
> **v1.28 补齐 3 条实现已发但文档漏登的码**（`FETCH_UNREACHABLE` / `NO_DEFAULT_TEMPLATE` / `TIMEOUT`，来源 `server/app/errors.py` 共 40 条与本节逐条比对，`code-only=0`）。`NO_DEFAULT_TEMPLATE` 此前只写在 §5.2 的 `details.reason` 位置，**实为独立错误码**，已纠正。
| 错误码 | HTTP | 含义 | `details` |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | 字段级校验失败 | `{fields:[{field,rule,message}]}` |
| `BAD_REQUEST` | 400 | JSON 解析失败/缺 body/Content-Type 错 | `{reason:"invalid_json",at:12}` |
| `NOT_FOUND` | 404 | 资源不存在 | `{resource,id}` |
| `CONFLICT` | 409 | 状态冲突（如 `PACKAGE_NOT_READY`） | `{reason, ...}` |
| `FILE_IN_USE` | 409 | 删附件时仍被引用（v1.17 新增，D-34）：`user_profile.photo_path` / 导入候选 / `build_artifact` 任一引用该附件 → 拒绝物理删除 | `{referenced_by:[{kind:"profile_photo"\|"import_candidate"\|"build_artifact", id}]}` |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | 上传类型不支持 | `{ext,mime}` |
| `PAYLOAD_TOO_LARGE` | 413 | >20 MB | `{limit_bytes}` |
| `PATH_ESCAPE` | 400 | 路径越界 | `{requested}` |
| `IMPORT_UNSUPPORTED` | 422 | 无法解析的文档 | `{parser,reason}` |
| `IMPORT_NO_TEXT_LAYER` | 422 | 扫描件/无文本层 | `{chars_extracted}` |
| `TEMPLATE_INVALID` | 422 | 区块/槽位结构非法 | `{issues:[{block_id,slot_key,rule}]}` |
| `MISSING_SLOTS` | 422 | **必填**槽位（`required=1`）无值 → 组装中止。可选槽位缺值**不**报此码，改走 200 + `warnings[MISSING_SLOTS_RENDERED]`（见 §8.3） | `{missing:[{block_id,slot_key,label}]}` |
| `NAMING_UNKNOWN_VAR` | 422 | 未知变量 | §9.5 |
| `NAMING_MISSING_VAR` | 422 | 变量无值 | §9.5 |
| `NAMING_EMPTY` | 422 | 净化后为空 | §9.5 |
| `NAMING_TOO_LONG` | 422 | 模板字面量超长 | §9.5 |
| `NAMING_SYNTAX` | 422 | 语法错误 | §9.5 |
| `NAMING_INVALID_CHARS` | 422 | 仍含非法字符 | §9.5 |
| `LLM_DISABLED` | 503 | `provider=off` | `{provider}` |
| `LLM_UNREACHABLE` | 503 | 连接被拒/DNS 失败/TLS 失败（尚未拿到 HTTP 响应） | `{host,reason:"Connection refused",latency_ms}` |
| `LLM_NOT_CONFIGURED` | 503 | 缺 key/base_url | `{provider,missing:["api_key"]}` |
| `LLM_JSON_MODE_PRECONDITION` | 422 | **本地**前置校验：要求 `json_object` 但 prompt 不含字面量 `json`（**零出网**） | `{reason:"PROMPT_MISSING_JSON_LITERAL",purpose}` |
| `LLM_CONSENT_REQUIRED` | 428 | 未带 `preview_id` | `{purpose}` |
| `LLM_CONSENT_EXPIRED` | 410 | 预览超 600 s | `{preview_id,expires_at}` |
| `LLM_CONSENT_MISMATCH` | 409 | payload 哈希不符 / 已消费 | `{preview_id,status}` |
| `LLM_UPSTREAM_ERROR` | 502 | 上游 5xx/协议错 | `{http_status,upstream_code}` |
| `LLM_TIMEOUT` | 504 | 超时 | `{timeout_s}` |
| `LLM_RATE_LIMITED` | 429 | 上游限流 | `{retry_after_s}` |
| `LLM_BAD_RESPONSE` | 502 | 上游返回完整响应但**不是合法 JSON / 缺必填字段**（不含截断） | `{reason}` |
| `LLM_TRUNCATED` | 502 | **`finish_reason="length"` 导致输出被截断**（`content` 无论空或半截）；不重试、不落库 | `{reason:"empty_content"\|"partial_json", finish_reason:"length", completion_tokens, max_tokens, reasoning_tokens?}` |
| `EGRESS_BLOCKED` | 403 | host 不在白名单 | `{host,allowed_hosts}` |
| `RENDER_FAILED` | 500 | PDF/DOCX 渲染失败 | `{engine,reason}` |
| `FONT_UNAVAILABLE` | 500 | 中文字体缺失 | `{chain_tried}` |
| `STORAGE_ERROR` | 500 | 磁盘/权限 | `{path,reason}` |
| `FETCH_UNREACHABLE` | 502 | 下行通道无法连接目标站点（DNS/TCP/TLS 失败；与 `FETCH_FAILED` 降级**不同**：本码表示「连不上」，`FETCH_FAILED` 是「连上了但拿不到可用 JD 文本」）。`server/app/errors.py:58` | `{host, reason, stage:"dns"/"connect"/"tls"}` |
| `NO_DEFAULT_TEMPLATE` | 409 | `assemble` 时无默认模板且请求未显式给 `template_id`（**禁止静默取最新**，见 §5.2） | `{candidates:[{id,name,is_default}]}` |
| `TIMEOUT` | 504 | 下行抓取/公开页请求超时（`fetch_client`；与 `LLM_TIMEOUT` 分开计数） | `{host, timeout_s, stage}` |
| `JOB_IN_PROGRESS` | 409 | 同资源已有任务 | `{job_id}` |
| `JOB_INTERRUPTED` | 409 | 任务因重启中断 | `{job_id}` |
| `INTERNAL` | 500 | 兜底 | 无（不泄露内部细节） |

---

### 14 附注：两类**不是服务端错误**的失败

| 情形 | 承载错误码 | details | 性质 |
|---|---|---|---|
| prompt 不含字面量 `json` 却要求 `json_object` | **`LLM_JSON_MODE_PRECONDITION`**(422) | `{reason:"PROMPT_MISSING_JSON_LITERAL", purpose, missing:"literal 'json' in messages"}` | **本地前置校验失败**（我们自己的 bug）。零出网、不重试、不计入上游错误率；前端文案「内部错误，请反馈」 |
| 上游返回 200 但 `finish_reason="length"`（推理烧光预算）：`content` 为空或半截 JSON | **`LLM_TRUNCATED`**(502) | `{reason:"empty_content"\|"partial_json", finish_reason:"length", reasoning_tokens:16, max_tokens:16}` | 上游**行为**错误但状态码正常。不自动重试；**空内容永不入库** |

> **错误码单一真源（v1.4 定稿）**：① 本地前置校验失败 → **新增 422 `LLM_JSON_MODE_PRECONDITION`**（零出网、不重试、不计入上游错误率）；② 截断（`finish_reason="length"`）→ **新增 502 `LLM_TRUNCATED`**（覆盖空内容与半截 JSON，不再借用 `LLM_BAD_RESPONSE`）；③ `LLM_BAD_RESPONSE` 仅保留「完整但非法 JSON / 缺字段」语义。前端按 `details.reason` 分支给文案：前者「内部错误，请反馈」，截断「输出被截断，请提高上限后重试」。

---

## 14.1 `warnings[]` 码表（非错误，可同时存在多条）

> **本表共 53 条。** 口径：**一行一条码、无折算**（v1.31 把 `NAMING_SANITIZED`/`NAMING_TRUNCATED`/`NO_VARIABLE`/`NAMING_COLLISION_SUFFIXED` 那行拆成 4 行；v1.35 增 `PACKAGES_TRUNCATED`/`LLM_STATUS_OVERRIDDEN`/`MATCHED_PACKAGE_NOT_READY` 三条）。**两条判据缺一不可**：① 行数 == 53；② **行数 == 去重码数**（即首列每格恰一个码——①单独不够，合并行会让行数 < 码数）。
>
> ```bash
> awk '/^## 14\.1/,/^## 15\./' docs/API-CONTRACT.md | grep -Ec '^\| `[A-Z][A-Z0-9_]+`'
> # 判据①行数（期望 53）；判据②按首列 split 展开后的去重码数（期望同为 53）
> ```
>
> 复算时若**行数与总数不等**，先查是否有一行写了多个码（那会让「行数 < 码数」）——**表头数字与表格内容必须同一次提交内同步**（M3 纪律）。变更沿革：v1.29 增 `LANG_FALLBACK`/`LANG_HEADING_UNMAPPED`（2 条）；v1.28 增 `SOURCE_CONFLICT`/`SKILLS_EMPTY`/`TEMPLATE_EMPTY`/`PHOTO_MISSING`/`PACKAGE_MISSING`/`COMPANY_PROFILE_SKIPPED`（6 条，全部为 `server/app` 已发而文档漏登，`code-only=0`）；v1.10 增 `COURSES_TRIMMED`，v1.17 增 `PAGE_FIT_DOWNGRADED`/`PAGE_OVERFLOW_TWO_PAGES`（单页版式降档，D-38）并补齐实现已发的 7 条 fetch/fallback 码。
> **警告码只表示「已产出、可继续」；失败一律进 §14 错误码**（例：`LLM_TRUNCATED` 是错误码，不是 warning；`OUTPUT_TRUNCATED` 是「截断但可用」的 warning——两者判据见 §14.1 四行分工表）。

业务响应里的 `warnings` 一律是 `[{code, message, severity, ...extra}]`，`severity ∈ {info, warn}`。前端按 `code` 分支渲染，**不得**只显示 message（message 可本地化变更）。

| code | 出现处 | 含义 |
|---|---|---|
| `CID_GLYPH_MISSING` | import draft | `(cid:N)` 字形缺失，已按列表标记处理（`count` 必填） |
| `PHOTO_DETECTED` | import draft | `severity="warn"`；检出内嵌图，**只产出候选**（`extracted_photo.applied=false`，不写 `photo_path`）；`details{attachment_id, sha256, width, height}` |
| `PHOTO_DECODE_FAILED` | import draft | `severity="warn"`；检出图片但**解码失败**（裸 FlateDecode raw RGB 等），**不产出候选**：`extracted_photo.available=false` 且无 `attachment_id`；`details{reason, bytes, hint}`（提示用户改上传独立图片或用其它简历） |
| `IMPORT_FALLBACK_LLM` | import draft | `severity="warn"`；**启发式解析可用结构不足**（识别到的 section < 2 或没有 header 块）→ 已启用 AI 兜底整理。语义：「整份稿子有 AI 参与过」，用户对照原件核对；前端据此在草稿顶部挂「已由 AI 兜底整理」横幅。**不要并入 `LOW_CONFIDENCE_BLOCKS`**：后者是「某几块没把握」（局部校对），本条是「整篇有 AI 参与」（整篇复核）——层级不同，且直接关系隐私口径的用户可见面 |
| `LOW_CONFIDENCE_BLOCKS` | import draft | 存在置信度 <0.6 的区块（附 `block_ids[]`） |
| `NO_SECTION_HEADING` | import draft | `severity="warn"`；未能识别出区块标题（`server/app/services/importer.py:531`），草稿结构靠启发式切分，需人工核对 |
| `IMAGE_DECODE_FAILED` | import draft | `severity="info"`；**内嵌图**（非证件照）无法解码，已跳过（`extract.py:281`），不影响文本导入；与 `PHOTO_DECODE_FAILED` 区别：后者指**证件照候选**解码失败 |
| `PDF_UNREADABLE` | import draft | `severity="error"`；PDF 损坏/加密，已按「无文本层」处理（`extract.py:328`），建议改用粘贴文本导入 |
| `TEXT_ENCODING_REPLACED` | import draft | `severity="error"`；正文出现 `U+FFFD` 替换字符（`count` = 个数，`extract.py:556`），属保真硬失败信号 |
| `CID_GLYPH_RESIDUAL` | import draft | `severity="error"`；仍有 `(cid:` 标记残留（`count` = 个数，`extract.py:566`），**不得直接提交模板** |
| `NO_TECH_STACK_DETECTED` | package draft | Package 未识别到技术栈（`packager.py:346`），建议用户补条目，不影响保存 |
| `NO_QUANTIFIED_OUTCOME` | package draft | 有 bullet 但无量化结果（`packager.py:348`），提示补充数字指标 |
| `ROLE_UNSPECIFIED` | package draft | `kind="project"` 但未写角色（`packager.py:350`） |
| `OUTPUT_TRUNCATED` | llm/complete | `severity="warn"`（`llm_client.py:421`）；`finish_reason="length"` **但正文非空且可解析** → 仍有可用产出，调用方应视为不完整并提示补 `max_tokens`。**与 §14 的 `LLM_TRUNCATED` 分工**：本条=「有产出但不完整」，`LLM_TRUNCATED`=「空或半截 JSON，不可用」（见 §10.5） |
| `LLM_EMPTY_CONTENT` | llm/complete | `severity="warn"`（`llm_client.py:450`）；模型返回空正文（usage 已记录、未落库），前端提示重试 |
| `PACKAGES_TRUNCATED` | jd analyze（LLM payload） | **参与对照的包数/字符数超限被截断**：`details{included, skipped, chars, limit_packages:12, limit_chars:6000}`；`context.packages_included + skipped == 选包总数`（§6.2.2） |
| `LLM_STATUS_OVERRIDDEN` | jd analyze | **模型判 `missing` 但本地匹配到证据 → 改判 `partial`**：`details{requirement, from:"missing", to:"partial", matched_package_ids[], matched_evidence[]}`，且 `candidate_status_source="local_override"`；**无证据（两个数组皆空）时不得改判**；`manual` 行永不被覆盖（§6.2.5） |
| `STATUS_WITHOUT_EVIDENCE` | jd analyze | **I26 的执行码**：某条 requirement 的 `candidate_status ∈ {satisfied, partial}` 但 `matched_package_ids` 与 `matched_evidence` **都为空的**——说命中却拿不出凭据。`details{requirement, from, to, action, evidence_count}`，`action ∈ {downgraded, flagged}`：`satisfied` 且零证据 → **降为 `partial`**（`to="partial"`）+ `candidate_status_source="local_override"` + `action="downgraded"`；`partial` 且零证据 → **保留结论**但打标 `action="flagged"`（界面显示「仅模型判断，未找到依据」）。**`candidate_status_source=="manual"` 的行一律跳过**（人工结论不降级、不告警）。`evidence_count` 恒为 `0`（否则不该发这个码） |
| `MATCHED_PACKAGE_NOT_READY` | jd analyze | **`matched_package_ids` 指向的包 `status != 'ready'`（已删/未就绪）**：`details{requirement_id, package_ids[], statuses[]}`，该 id 与对应 `matched_evidence` 项一并剔除；「没匹配到」= 两个数组皆空（§6.2.4） |

| `PROFILE_INCOMPLETE` | assemble / export | UserProfile 缺字段（附 `missing_fields[]`） |
| `MISSING_SLOTS_RENDERED` | assemble | 槽位无值，已渲染占位符 |
| `SCHOOL_TIER_INFERRED` | jd/analyze | `UserProfile.school_tier` 为空，院校层次由 LLM 依校名推断（UI 应提示用户可手填固定下来） |
| `COMPETITIVENESS_FALLBACK` | jd/analyze | 模型未给出竞争力评估，已用**本地规则补齐**（`details{}`）；此时校名仍参与判断，`school_signal_used` 不得为 false |
| `SCHOOL_SIGNAL_FALLBACK` | jd/analyze | 模型的院校结论是套话或未点出层次，已改用本地可核对表述（`details{raw_signal}`）；防「一句话糊过去」 |
| `COMPANY_PROFILE_FALLBACK` | company/profile | 模型未返回可解析的公司画像，已改用本地规则（`details{}`） |
| `SCHOOL_FILTER_FALLBACK` | company/profile | 模型声称有院校硬门槛**但没给出层次** → 按「不限」处理（`details{raw}`）：宁可当无门槛，也不编造门槛 |
| `FETCH_TRUNCATED` | fetch/public-page | 页面超 2 MB，只取前 2 MB（`details{bytes}`） |
| `FETCH_FAILED` | company-profiles/analyze | 抓公司官网失败（`details{url, reason}`），**已降级为只用粘贴的 JD 文本分析**，不得因此让整个分析失败 |
| `FETCH_DISABLED` | company-profiles/analyze | 用户关掉了联网（`allow_web_fetch=false`）或本次选择不联网，`details{url}`；只走 JD 文本 |
| `SCHOOL_SIGNAL_UNUSED` | builds/suggest | 本次建议**未使用**校名/院校层次（`school_signal_used=false`），防「发了但没用」退回净损失（ADR-20） |
| `PROFILE_FIELD_MISSING` | company/profile | `hiring_preferences_json` 四项必答项缺任一（院校偏好/学历届别/硬技能门槛/风格偏好） |
| `COURSES_TRIMMED` | assemble / export | `trim_courses=true` 时裁掉了课程（`details{before, after}`），保留「主修课程：」前缀且 ≥3 门。默认 `trim_courses=false` 不产生此警告 |
| `PAGE_OVERFLOW` | assemble / export | 估计页数超 `page_limit` |
| `PAGE_FIT_DOWNGRADED` | assemble / export（PDF） | **为塞进单页而降了字号档**：`details{from_pt, to_pt, used_height_pt, available_height_pt, reason:"single_page_fit"}`；前端必须有可见提示，不得静默降档 |
| `PAGE_OVERFLOW_TWO_PAGES` | assemble / export（PDF） | **三档都装不下、允许落到第 2 页**：`details{pages, overflow_pt, suggestion:"精简要点"}`；此时不得再降字号（9.5pt 硬下限），也不得静默 |
| `EMOJI_STRIPPED` | export | 导出前剥离 emoji/控制字符（附 `count`） |
| `TEXT_LAYER_MISMATCH` | export | 导出后文本层校验差异 >2%（ATS 风险，必须显著提示） |
| `NAMING_SANITIZED` | naming | 任一净化步骤改变了字符（`/`→`-`、非法字符、保留名加前缀、`..`→`._`）；UI 灰字「文件名已自动规范化」（见 §9.4.1） |
| `NAMING_TRUNCATED` | naming | 触发 120 字符截断（同时保证 UTF-8 ≤ 200 字节）；UI 黄字「名称过长已截断，可缩短模板」 |
| `NO_VARIABLE` | naming | 模板不含任何变量（纯字面量）；UI 灰字「该名称不含变量，多次导出可能重名」 |
| `NAMING_COLLISION_SUFFIXED` | naming | 同名冲突后追加 `-2`/`-3`；UI 绿字「已另存为 xxx-2.pdf」 |
| `PROMPT_NEAR_LIMIT` | llm preview | 预计 tokens 接近建议上限 |
| `LLM_JSON_UNPARSABLE` | llm complete | 上游返回非 JSON / schema 不符（`parsed=null`） |
| `SOURCE_CONFLICT` | compose / export | **中英来源同字段值不等且都非空**（例：GPA `3.56/4` vs `3.57/4.0`、到岗 `2027年1月下旬` vs `Early July 2026`）。**两种形态**：**（a）未决议**（`user_profile.extra_json.conflict_resolution.fields[field]` 不存在）→ `severity="warn"`，`details{field, zh_value, en_value}`，message 请用户确认，处置=**按语言各取各自来源值**（zh 版出中文数、en 版出英文数），**禁止合并成一个数**；**（b）已决议**（该 `field` 有决议值）→ `severity="info"`，`details{field, zh_value, en_value, resolved:"zh"|"en", decided_at:"<ISO>"}`，message=「已按中文版为准（可在个人资料里改）」。**决议只影响提示级别与文案，不改渲染值**——渲染仍按语言取自对应真值（en 段现在已经是中文数值的英译表述，如 `Available: Late January 2027` / `GPA 3.56/4`）；**移除 `resolution` 即回到 (a) 的 `warn`**（决议不是单向开关）。**一侧为空 ⇒ 不是冲突**，记 `PROFILE_FIELD_MISSING` |
| `SKILLS_EMPTY` | compose | 技能区无内容可渲染（`skills_json` 为空且该块无 `static_text`）。**本码是「内容没留下来」的信号，不是渲染缺陷**——根因见 `DATA-MODEL` 不变量 I15 |
| `TEMPLATE_EMPTY` | compose | 模板无任何可用 block（全软删或未生成），降级为最小骨架并提示重建 |
| `PHOTO_MISSING` | compose | 要求带照片（`photo_in_export=true`）但 `photo_path` 为空或文件缺失 → **不留白位**，按无照片排版 |
| `PACKAGE_MISSING` | compose / export | 选定条目引用的 `package_id` 在库中不存在（已删除或指向他库）→ **该条目跳过**并在 warnings 说明，不静默丢弃。`details{package_id, entry_key, section, heading}`；同时把被省略的节记入 `ir.meta.omitted_sections[]`（渲染层据此不输出空节标题）。**与任何其它码不合并书写**（M8） |
| `PACKAGE_SKIPPED` | import commit（`also_create_packages=true`） | 某个 entry **没有建包**，且这是**有意为之**（非错误）。`details{entry_temp_id, reason, kind?, title?}`，`reason ∈ {no_kind_mapping, empty_entry}` **同一码两个分支，不拆成两个码**：`no_kind_mapping` = section 的 `bound_package_kind` 缺失/无法映射到 `{internship,project,activity}`；`empty_entry` = 有标题但**正文为空**（不生成点开一无所有的空经历包）。**反向条款**：这两种情况**禁止静默 `continue`**——旧实现 `if not kind: continue` 会假装建过（§17.8 `T-7`） |
| `COMPANY_PROFILE_SKIPPED` | jd analyze | 公司画像分析被跳过（LLM 不可用/未配置），JD 分析照常返回 |
| `LANG_FALLBACK` | compose / export | `lang=en` 装配时某条目**一条 en 变体都没有**，该条目沿用中文原文（**允许回退，不许静默回退**）。`details{entry_count, bullet_count, sample[]}`。反向：`lang=zh` 导出永不产生本码 | 
| `LANG_HEADING_UNMAPPED` | compose / export | 自定义 `template_block.heading` 不在 §8.5.1 词表内（例「科研经历」）→ **保留原文**并提示，**不得静默直译或交给 LLM 翻译**。`details{heading, lang}` | 
| `IMPORT_DRAFT_PRUNED` | import create | `severity="info"`（`import_service.py:150-158`）：新建导入时清理**过久的未提交草稿**（只留最近 `MAX_DRAFT_KEEP` 条 / `DRAFT_TTL_DAYS` 天），在被清理之外的条件下不产生；`details`：`{count, pruned_ids[], max_keep, ttl_days}`|

> **截断的码位分工（v1.17 定版，D-33 已清）**：v1.6 曾把 `OUTPUT_TRUNCATED` 删除，理由是「`finish_reason="length"` 一律不可交付」——**该假设被实测推翻**（`llm_client.py:417-422`：`length` 但 JSON 合法且正文非空，产出可用）。v1.15 按实现恢复该 warning，与 502 错误码按**可用性**分工：
>
> | 情形 | 判定 | 码位 |
> |---|---|---|
> | `finish_reason="length"` + `content` 空 | 不可用 | **502 `LLM_TRUNCATED`**（`details.reason="empty_content"`） |
> | `finish_reason="length"` + 半截 JSON 不可解析 | 不可用 | **502 `LLM_TRUNCATED`**（`details.reason="partial_json"`） |
> | `finish_reason="length"` + JSON 合法且非空 | **可用但不完整** | **200 + `warnings[OUTPUT_TRUNCATED]`**，`details{finish_reason,completion_tokens,max_tokens}`，前端常驻横幅 |
> | `finish_reason="stop"` + JSON 非法/缺字段 | 不可用 | **502 `LLM_BAD_RESPONSE`**（`details.reason="invalid_json"` / 缺字段名） |
>
> 四行互不重叠，避免 t11 判歧义。**旧版「已删除」的表述即本行取代，不再保留。**

---

## 15. 契约变更流程

1. 先改本文件（含变更记录表），再改 `app/models.py`（pydantic 是契约的代码化）。
2. 破坏性变更必须升 `/api/v1` → `/api/v2`（本期不做，直接避免破坏性变更）。
3. `tests/test_contract.py` 用 pydantic schema 与本文示例做快照比对；示例 JSON 漂移即失败。

### 变更记录

| 日期 | 变更 | 影响 |
|---|---|---|
| 2026-10-23 | **v1.13** D-26/D-27：`/health` 增 `build`（git short sha 或源码 mtime 摘要）+ `started_at`（行为验证前必须核对，防旧进程误判）；§5.1 `job_id` 必需；新增 `PHOTO_DECODE_FAILED` 与「候选必须可点」不变量 | coder：`view()` 恒返回 `job_id`，解码失败置 `available=false` + 警告；uier：状态条显示 `build` |
| 2026-10-23 | **v1.12** IMPORT lane 定版：§5.1 上传改 **201 + 内联 draft**（取消 202 轮询语义）；`blocks` 唯一真值源 + `sections[]` 派生定义；`quality` 四字段；`PHOTO_DETECTED` 补 `severity=warn`/`details` 与「只产出候选」 | coder 确认 `POST /imports` 返回 201 且 `applied=false`；uier 校对页不再轮询 |
| 2026-10-23 | v1.0 初版 | — |
| 2026-10-23 | v1.1 并入 UserProfile 端点（§3）、命名模板规则与 6 个错误码（§9）、字段清单结构（§10.2）、`excluded/redactions` 语义 | uier 需实现 consent 弹窗；builder 需实现 `naming.resolve` 与 `consent` 服务 |
| 2026-10-23 | v1.2 补 `BAD_REQUEST`/`LLM_UNREACHABLE`、`/settings/export-all`、§9.4.1 命名 warnings、§14.1 `warnings` 码表 | 与 ACCEPTANCE 的错误码逐条对齐；builder 按码表实现 warning 生成 |
| 2026-10-23 | **v1.7** 上云边界最终口径（用户 m00265）：§10.2.1 删除 `[SCHOOL]` 占位符行，明确学校名**真实传输**；`assert_no_identity` 抓取名单收敛为 `name/phone/email`；`auto_redact` 默认改 `["name","phone","email"]` | 不新增/不删错误码（36 错误码 / 14 警告码不变）；builder 改 `llm_payload.py` 与自检名单；uier 改 ConsentModal 文案 |
| 2026-10-23 | **v1.17** 新增 §17（按代码补登 39 条已实现端点 + 7 条实测偏差）；§16.1 三数转 `PENDING(canonical-script)` 并规定一格一路由；§14.1 截断旧注改四行分工表（D-33）；新增 `FILE_IN_USE`(409) 与两条 `details.reason`；§5.2 定义无默认模板时 assemble 拒绝 | **错误码 36→37**、警告码 **30→31**（28 行 + 折算 3；补登 `IMPORT_DRAFT_PRUNED`）。builder：`DELETE /files/{id}` 加引用守卫、`POST /packages` 丢 `end_date` 的 bug、`auto_redact` 去掉 `school`；uier：`GET /files` 的 `original_name` 只本机展示、无默认模板时渲染选择器 |
| 2026-10-23 | **v1.6** 一致性收口：§10.5 用「`finish_reason` × `content` × 解析结果」四行表把 `LLM_TRUNCATED`(502) 与 `LLM_BAD_RESPONSE`(502) 划成互不重叠（`length` 一律截断错误，`stop` 才可能是非法 JSON）；`LLM_TRUNCATED.details` 增加 `completion_tokens`；**删除 warning `OUTPUT_TRUNCATED`**（不存在「截断仍可用」的成功路径，避免与错误码语义重复）；`slot_key` 正则放宽允许点号；`MISSING_SLOTS` 明确仅指 `required=1` | 不新增错误码；总数保持 36 错误码 / 14 警告码 |
| 2026-10-23 | **v1.5** 按用户决策「坚持 DeepSeek 路线」移除 Ollama：§11 明确 `provider` 枚举 `deepseek \| openai_compatible \| off`（传 ollama → 422 `details.reason="UNSUPPORTED_PROVIDER"`）；§2 `/env` 示例删 `OLLAMA_NOT_INSTALLED`；§14.1 删该警告码 | 不新增错误码（复用 `VALIDATION_ERROR`）。builder 不得实现 ollama 分支；uier 不展示本地模型入口 |
| 2026-10-23 | **v1.4** 按 captain 决断 ①③④⑤：出网拆上行/下行两通道（§7 新增 `POST /fetch/public-page`）；§3 照片端点（上传/从导入件抽取/删除/取字节）+ `photo_source`；§5.1 draft 增 `extracted_photo`；**新增 §10.2.1 宽路径脱敏契约**；§10.4 连接级判定加入 `ssl.SSLError`；§10.5 截断改用新码 `LLM_TRUNCATED`；§11 增 `allow_web_fetch/photo_in_export/app_port` | 新增 502 `LLM_TRUNCATED`（截断，含空内容与半截 JSON）；`LLM_BAD_RESPONSE` 收窄为「完整但非法 JSON/缺字段」。builder 需实现 `fetch_client` + `fetch_guard` 与占位符脱敏自检；uier 需实现照片开关与抓取开关 |
| 2026-10-23 | **v1.3** 按 captain 回归实测 F1–F4：§10.4 拆分「连接级 vs HTTP 级」两类重试预算与 consent 消耗时机；新增 **§10.5 上游调用约定**（json_object 前置、reasoner 支持 json_object、推理截断、`max_tokens` 下限）；§14 附注两类非服务端错误；§14.1 增 `OUTPUT_TRUNCATED` | 新增 422 `LLM_JSON_MODE_PRECONDITION`；`LLM_MAX_RETRIES` 默认调为 2。builder 需实现连接级重试与 `PROMPT_MISSING_JSON_LITERAL` 前置断言、空 `content` 拒收；uier 需区分「不可达-可重试」与「鉴权-去设置」两种文案 |

---

## 16. 文档—实现一致性判据（可执行，防漂移）

人工核对发现「文档说 A、实现是 B」的成本极高（本项目已发生 3 次：`job_id`、照片确认子路径、`IMPORT_FALLBACK_LLM` 未登记）。以下两条判据一次消灭这类整族问题，**改契约后必须重跑**。

### 16.0 元规则（判据自身的纪律，v1.19 增）

这四条约束的是**判据**，不是产品行为。它们来自本项目已实际发生的误判，违反任何一条都会让 t11 判错人。

| 编号 | 元规则 | 为什么 | 违反后果 |
|---|---|---|---|
| **M1** | **码位以实现为准：文档不得先行登记实现里不存在的码** | 反向的「实现发的码必须登记」已由 §16.2 强制；若文档再单方面造码，t11 会把「文档写了、实现没有」判成实现缺陷 | 例：`SCHOOL_TIER_UNRECOGNIZED` 被否，改用单码 `SCHOOL_TIER_INFERRED` + `details.recognized` |
| **M2** | **任何「现状是 X」必须附证据：文件 `mtime` 或 git hash，或实跑输出** | 本项目已发生 3 次「旧快照当现状」（`job_id`、院校分层、`.command` 末四位） | 判据假红/假绿，返工 |
| **M3** | **表格必须是矩形**：同一张表每行列数相等 | 列数不一致会让任何按列解析的脚本（FWD/REV、字段比对）在这一行错位，且**肉眼看不出来** | 见下 M3 自检命令 |
| **M4** | **自报行数一律用 `wc -l`**（不许用 `splitlines()`） | 文件末尾是否带换行会让两者差 1，导致「文档被截断/多一行」的伪告警 | 巡检数字对不上 |
| **M5** | **跨 agent 指代一律按内容，不按编号** | supervisor 的 `D-39` = `data/eval/check_export_pdf.py` 的 `--right-margin` 默认 42.5pt（会把紧排原件判假红），本文档的 `D-39` = 门槛动词分组；`ANL-11/12` 两边切法也不同（本文档=语义二分+并列档位，清单=分组表+`gap_notes`）。**同一个号在不同文件里是两件事** | t11 各说各话；引用时请写「§7 门槛动词分组（本文档 D-39）」「清单里那条 `--right-margin`」这种内容指代 |
| **M6** | **文件头/表头只写版本与「以条目行为准」，不写具体条目结论** | 冻结说明写「某条 KNOWN-FAIL」而条目行已写「已修复」→ 同一文件两个结论（已发生：D-43） | t11 撞到自相矛盾，无法判定 |
| **M7** | **跨文件累计数只在真源出现一次**：文件头/冻结说明/变更记录**不得**写「错误码 N 条、警告码 M 条」这类跨文件累计数，只写「新增 K 条」；累计数唯一真源 = §14 与 §14.1 表头 | 同一数字写在两处，改一处必漏另一处 | 真实事故：v1.29 冻结行写「警告码 → 48」而表头已是 45，t11 撞车 |
| **M8** | **一格多值的表，取数必须按单元格 split 展开，不许 `grep -o` 取首个匹配** | 合并行会让「按行取首码」少算 | 真实事故：`NAMING_SANITIZED / … / NAMING_COLLISION_SUFFIXED` 一行四码被 `grep -oE` 只数到 1，造成 45 vs 48 之争；配套判据 = **行数 == 去重码数** |
| **M9** | **凡「从文档里数条目」的脚本，必须同时接受加粗/不加粗/带反引号三种写法，并自校验「解析条数 == 另一种独立方式数出的条数」，不等即非零退出** | M8 管「一格多值」，M9 管「一行多种写法」；两种都是**取数侧的盲区**，而盲区会直接伪造覆盖率 | 真实事故：`tests/acceptance/make_index.py` 正则 `^\|\s*`?(AC-[A-Z]+-[0-9]+)`?\s*\|` **不认加粗行**，`docs/ACCEPTANCE.md` 有 28 行是 `| **AC-…** |` → 账本分母 **119** 而真值 **152**，覆盖率被算高（76% 报成 93%）。**修复方向**：文档侧统一不加粗（见 §0 格式纪律），脚本侧正则改为 `^\|\s*`{0,2}(AC-[A-Z]+-[0-9]+)`{0,2}\s*\|` 并以「两种数法相等」为硬门 |

**M3 自检（每次改表后必须跑，期望 `表格列数 mismatch = 0`）**。要点：先抹掉 `\|` 转义，再把反引号内的 `|` 也视为普通字符，然后才按 `|` 切分。

```bash
cd resume-warehouse && python3 - <<'EOF'
import glob,re
def cells(line):
    s=line.replace("\\|","\x00")                      # (1) 转义竖线不是分隔符
    s=re.sub(r"`[^`]*`",lambda m:m.group(0).replace("|","\x01"),s)  # (2) 反引号内的竖线不是分隔符
    p=s.split("|")
    if p and p[0].strip()=="":p=p[1:]
    if p and p[-1].strip()=="":p=p[:-1]
    return p
bad=0
for f in sorted(glob.glob("docs/*.md")):
    if "REVIEW-CHECKLIST" in f: continue
    L=open(f,encoding="utf-8").read().split("\n");i=0;last=None
    while i<len(L):
        if L[i].startswith("|"):
            j=i
            while j<len(L) and L[j].startswith("|"): j+=1
            if j-i>=2 and re.match(r'^\|[\s:\-|]+\|$',L[i+1]):
                last=len(cells(L[i]))        # 表头决定本表列数
            if last is not None:
                for k in range(i,j):          # (3) 空行分隔的续行仍属上一张表
                    if len(cells(L[k]))!=last:
                        print("MISMATCH %s:%d 期望%d列 实得%d列"%(f,k+1,last,len(cells(L[k]))));bad+=1
            i=j
        else:i+=1
print("表格列数 mismatch =",bad)
EOF
```

**这个脚本自身踩过三个坑（别再退回旧版）**：① 不抹转义竖线 → 含 `\|` 的行全部误判；② 不处理反引号内的竖线 → 含正则/命令的行误判；③ **只按「表头 + 分隔行」切块** → 空行分隔的续行块会漏检（`IMPORT_DRAFT_PRUNED` 就这样漏了 3 版）。第 ③ 条的语义是：**Markdown 里空行不断表**，续行仍属上一张表。

**这个脚本自身踩过三个坑（别再退回旧版）**：① 不抹转义竖线 → 含 `\|` 的行全部误判；② 不处理反引号内 `|` → 含正则/命令的行误判；③ **只按「表头+分隔行」切块** → 空行分隔的续行块会漏检（`IMPORT_DRAFT_PRUNED` 就这样漏了 3 版）。第 ③ 条的语义是：**Markdown 里空行不断表**，续行仍属上一张表。

> 只对 `docs/*.md` 里**属于本项目的 5 份**生效；`docs/REVIEW-CHECKLIST.md` 与 `docs/DESIGN.md` 是他人产物，脚本跳过（不替他人改文件，但要把 mismatch 报给 owner）。

### 16.1 路由一致性（双向）

```bash
cd resume-warehouse && python3 - <<'EOF'
import re,pathlib
root=pathlib.Path(".").resolve(); docs=root/"docs"; api=root/"server/app/api"
def norm(p):
    p=p.split("?")[0].split("#")[0].rstrip("/")
    p=re.sub(r"<[^>]+>","*",p); p=re.sub(r"\{[^}]+\}","*",p); return p or "/"
code={}
for f in api.rglob("*.py"):
    for m in re.finditer(r'@\w+\.(get|post|put|patch|delete)\(\s*"([^"]+)"',f.read_text(encoding="utf-8")):
        code[(m.group(1).upper(),norm(m.group(2)))]=f.name
docset=set()
for f in docs.glob("*.md"):
    if f.name=="REVIEW-CHECKLIST.md": continue
    txt=f.read_text(encoding="utf-8")
    for m in re.finditer(r'`(GET|POST|PUT|PATCH|DELETE) (/[^`\s]+)`',txt):
        p=m.group(2); docset.add((m.group(1),norm(p[len("/api/v1"):] if p.startswith("/api/v1") else p)))
    # 兼容表格两列式写法：| `POST` | `/profile/photo` | …  （v1.16 补，避免「文档写了但判据看不见」）
    for m in re.finditer(r'\|\s*`(GET|POST|PUT|PATCH|DELETE)`\s*\|\s*`(/[^`\s]+)`',txt):
        p=m.group(2); docset.add((m.group(1),norm(p[len("/api/v1"):] if p.startswith("/api/v1") else p)))
rev=sorted(k for k in code if k not in docset); fwd=sorted(k for k in docset if k not in code)
print("REV 代码有、文档无 =",len(rev)); [print("  ",k) for k in rev]
print("FWD 文档有、代码无 =",len(fwd)); [print("  ",k) for k in fwd]
EOF
```

| 方向 | 期望 | 当前基线（v1.17，2026-10-23） |
|---|---|---|
| **REV**（代码注册、文档未写） | **必须 0** | **`PENDING(canonical-script)`** —— 见下方「数字为何不写死」 |
| **FWD**（文档写了、代码未实现） | 允许（spec-first），但必须 ⊆ 未实现清单并随 lane 收缩 | **`PENDING(canonical-script)`**；真缺口已全部登记于 §17.2.1 的 P1/P2 分档与未开工 lane |
| **码位**（代码在发但文档未登记） | **必须 0** | **0**（§16.2 脚本，2026-10-23 03:5x 实测；与 supervisor 独立复跑一致） |

**数字为何不写死（v1.17 定版，captain 2026-10-23 裁定）**

同一批文档，三个人三个数：planner 39/18、supervisor 20/46、captain 21/31。**不是谁算错，是「一条路由」缺定义**——路径参数怎么归一、一格两路由怎么写、多方法装饰器算一条还是两条，每个脚本各自选择。**一个无法收敛的指标不能当 t11 的判据。**

因此：

1. **唯一权威实现** = `scripts/check_route_parity.py`（coder 交付）：输出稳定排序 JSON，归一化规则写死在脚本头，带 `--self-test` 内置脏格式样本。
2. **达标标准** = coder / planner / supervisor **各自跑同一个脚本，JSON 逐字节相同**。此后不再接受「我的脚本算出来是 N」。
3. 脚本落地前，本节**只登记口径与入口，不登记数字**；任何临时数字必须标注「临时实现，非契约」。

**判据演进记录（保留，用于说明为何要收敛口径）**

| 版本 | 脚本 | 解析样式 | REV | FWD | 结论 |
|---|---|---|---|---|---|
| 初版 | 本节旧脚本 | 只认 `` `METHOD /path` `` 内联 | 39 | 18 | **不可用**：两栏表格里的已文档路由被误判为未写（假高） |
| 更二 | REVIEW-CHECKLIST §2.1.2 | 内联 + 两栏表格（含多方法单元格） | 20 | 46 | 修掉假高，但 FWD 反升（暴露真缺口） |
| 现行 | `scripts/check_route_parity.py` | 归一化规则写死脚本头 | `PENDING` | `PENDING` | 唯一权威 |

> **格式纪律（本条由 captain 裁定，比数字更重要）**：契约只允许**一行一路由**——路径单元格内不得出现两条路由（如旧的 `` `/jds` / `GET /jds/{id}` ``），方法单元格也不得多方法合写（如 `` `PATCH` / `DELETE` ``）。任何解析器遇到这两种写法都会分叉。v1.17 已全文档改净（`grep -c '| `[A-Z]\+` / `'` = 0）。

**§16.1 的显式豁免清单（不为它们造端点；判据永久可跑）**

| 命中项 | 为什么豁免 | 处置 |
|---|---|---|
| `GET /files/../../.env` | 它是**安全反例**：证明路径穿越被拒（`../../` 规范化后落到 root 外） | 保留在契约里当反例 |
| `GET /settings.app_port/app_url` | 文档**笔误**：应为 `/settings` 响应里的 `app_port`、`app_url` 两个字段 | 已在本表豁免，不新增端点 |
| `POST /templates` | **确认不存在该端点**：模板唯一来源是 `POST /imports/{id}/commit`（§17.2 注、偏差 7） | 契约保留说明，不实现 |

> **REV/FWD 是常驻判据（v1.17 定版，权威实现为 `scripts/check_route_parity.py`）**：任何人新增路由或码位而不同步本契约，即视为**文档缺陷，归新增者**，不是「实现缺陷」。t11 每次复核必须先跑 §16.1/§16.2，基线非 0 即拒收。

**现行基线（2026-10-23，`scripts/check_route_parity.py`，JSON 逐字节可复现）**：

```bash
cd resume-warehouse && .venv/bin/python scripts/check_route_parity.py | .venv/bin/python -c \
  "import json,sys; d=json.load(sys.stdin); print(d['counts'], 'only_in_code=', len(d['only_in_code']), 'invariants_ok=', d['invariants_ok'])"
```

| 指标 | 值 | 含义 |
|---|---|---|
| `code_total` | **102** | 代码注册的路由数 |
| `documented_total` | **115** | 文档声明的路由数（含未实现族） |
| `matched` | **102** | 双向都有的（= `code_total` ⇒ `only_in_code=0`） |
| `only_in_code` | **0** | 代码有、文档没有 —— **必须归零**，否则判文档缺陷 |
| `only_in_docs` | **13** | 文档有、代码没有 —— 全部是**尚未实现的 P2 族**，不是缺陷 |
| `invariants_ok` | **true** | 脚本自带不变量（一行一路由、无多方法合写等） |

`only_in_docs` 的 13 条构成（用于确认「没有误写」，逐条列出以便 t11 对账）：`blocks` 写侧 **5**（`POST /blocks`、`PATCH /blocks/*`、`DELETE /blocks/*`、`GET /blocks/*/slots`、`POST /blocks/*/slots`）、`slots` 写侧 **3**（`POST /slots`、`PATCH /slots/*`、`DELETE /slots/*`）、`templates` 写侧 **4**（`POST /templates`、`PATCH /templates/*`、`GET /templates/*/blocks`、`POST /templates/*/blocks`）、`artifacts` 缩略图 **1**（`GET /artifacts/*/thumb`）。这些都是 t10/P2 待交付项，文档侧已标 `[P2 未实现]`（见 §17.2.1 模板写侧分级）。**注意：本表数字随实现推进变化，判据只认脚本输出，不认此处数字**（数字仅作「是否有人新增未登记路由」的对照锚点）。

> 上一版本节的「三数」（39/18、20/46、21/31）以及第三方口头的「43」都已作废——口径不一致的根源是「一条路由」缺少唯一定义，现已由脚本固定。**引用路由数一律以本脚本输出为准**（M2）。

### 16.2 码位一致性（代码 → 文档）

```bash
cd resume-warehouse && python3 - <<'EOF'
import re,pathlib
docs=pathlib.Path("docs"); app=pathlib.Path("server/app")
doc_codes={m.group(1) for f in docs.glob("*.md") if f.name!="REVIEW-CHECKLIST.md"
           for m in re.finditer(r'^\| `([A-Z][A-Z0-9_]{4,})` \|',f.read_text(encoding="utf-8"),re.M)}
lit={m.group(1) for f in app.rglob("*.py")
     for m in re.finditer(r'"([A-Z][A-Z0-9_]{5,})"',f.read_text(encoding="utf-8"))}
NON_CODE=re.compile(r'^(LLM_[A-Z0-9_]+|APP_[A-Z0-9_]+|DATA_DIR|COMMIT|ROLLBACK|'
                    r'PACKAGE_NOT_READY|PACKAGE_NEEDS_VERIFIED_VARIANT|PACKAGE_SKIPPED|'
                    r'TEMPLATE_VERSION_CONFLICT|IDENTITY_PRESENT_IN_PAYLOAD|PROMPT_MISSING_JSON_LITERAL|'
                    r'NO_DEFAULT_TEMPLATE|MULTIPLE_DEFAULT_TEMPLATES|EMPTY_BODY|TIMEOUT|'
                    r'HOST_NOT_ALLOWED|FETCH_DISABLED|PRIVATE_ADDRESS|TOO_MANY_REDIRECTS|'
                    r'COMPANY_PROFILE_SKIPPED|METHOD_HEURISTIC|'
                    # 第三节：i18n 词表 key（UPPER 只是为了稳定，不是码）
                    r'EDUCATION|EXPERIENCE|INTERNSHIP|PROJECTS|SKILLS|SUMMARY|CAMPUS|HONORS|'
                    # 第四节：reportlab 常量（表格样式属性名，不是码）
                    r'LEFTPADDING|RIGHTPADDING|TOPPADDING|BOTTOMPADDING|VALIGN)$')
miss=sorted(c for c in lit-doc_codes if not NON_CODE.match(c))
print("未登记码 =",len(miss)); [print("  ",c) for c in miss]
EOF
```

| 项 | 期望 | 当前基线 |
|---|---|---|
| 未登记码（代码在发 `"CODE"` 字面量但 §14/§14.1 没有） | **0** | **0**（v1.30 实测；口径 = 本节脚本，白名单扩到五类后重跑） |
| 白名单命中（**分类可审**，v1.31） | 五类共 **50** 条：环境变量 `LLM_*`/`APP_*`/`DATA_DIR` **25**、SQL 事务词 `COMMIT`/`ROLLBACK` **2**、`details.reason` 值 **12**、i18n 词表 key **6**、reportlab 常量 **5** | 分类数随白名单同步改；**任何类别 >5 条的增幅都要在变更记录里说明理由**（白名单会退化成「把红吃掉的垃圾桶」） |

> **白名单分类计数（可复跑，v1.31 增）**——白名单是唯一能把红吃掉的机制，**只写总数 50 视为不可校验**，必须逐类给出：
>
> ```python
> import re,pathlib
> app=pathlib.Path("server/app")
> lit={m.group(1) for f in app.rglob("*.py")
>      for m in re.finditer(r'"([A-Z][A-Z0-9_]{5,})"',f.read_text(encoding="utf-8"))}
> cat={"env":r'^(LLM_[A-Z0-9_]+|APP_[A-Z0-9_]+|DATA_DIR)$',
>      "sql":r'^(COMMIT|ROLLBACK)$',
>      "reason":r'^(PACKAGE_NOT_READY|PACKAGE_NEEDS_VERIFIED_VARIANT|PACKAGE_SKIPPED|TEMPLATE_VERSION_CONFLICT|IDENTITY_PRESENT_IN_PAYLOAD|PROMPT_MISSING_JSON_LITERAL|NO_DEFAULT_TEMPLATE|MULTIPLE_DEFAULT_TEMPLATES|EMPTY_BODY|TIMEOUT|HOST_NOT_ALLOWED|FETCH_DISABLED|PRIVATE_ADDRESS|TOO_MANY_REDIRECTS|COMPANY_PROFILE_SKIPPED|METHOD_HEURISTIC)$',
>      "i18n":r'^(EDUCATION|EXPERIENCE|INTERNSHIP|PROJECTS|SKILLS|SUMMARY|CAMPUS|HONORS)$',
>      "reportlab":r'^(LEFTPADDING|RIGHTPADDING|TOPPADDING|BOTTOMPADDING|VALIGN)$'}
> hit={k:sum(1 for c in lit if re.match(rx,c)) for k,rx in cat.items()}
> print(hit, "合计", sum(hit.values()))
> # 期望 {"env":25,"sql":2,"reason":12,"i18n":6,"reportlab":5} 合计 50（2026-10-23 04:39 实测）
> ```
>
> **纪律**：新增任何 `"XXX_YYY"` 字面量（错误码/警告码/`details.reason`）当次就要进 §14/§14.1 或白名单，否则本节判据下一轮就红——**契约自己会报漂移**，不用等人发现。

---

## 17. 已实现端点补充契约（按代码登记，REV 基线归零）

**为什么有这一节**：§16.1 的 REV 判据跑出 **39 条「代码注册了、契约没写」**的端点。它们不是笔误——是前端**无从知道**的能力（尤其 `/packages/*` 子资源、`/templates` 全套、`/llm/previews*`）。缺这些，t8 只能读代码猜契约，t10 联调必对不上。本节把它们补全，使 **REV = 0**。

**证据等级（本书纪律：写「现状」必须附实跑证据）**：
- ✅ **实测**：2026-10-23 03:46–03:53 对临时实例实跑（`DATA_DIR=data/.tmp_planner`，端口 8799），命令见 §17.9。
- ⚠️ **据 schema/code 推定**：参数与校验来自 `server/app/models.py` 的 pydantic 模型，未逐条实跑（标注「推定」）。失败样例中「enum/required → 422」由 `StrictModel` + `extra_forbidden` 保证，属结构性确定。

每行给出 t11 需要的五要素：**method + path / 一句话语义 / 请求参数（名:类型,是否必填）/ 成功响应关键字段 / 一个失败样例（code + 触发条件）**。

### 17.1 Package 族

| 端点 | 语义 | 请求参数 | 成功响应关键字段（实测） | 失败样例 |
|---|---|---|---|---|
| `GET /packages` | 列 Package（默认过滤已软删） | `limit: int,否` 默认 50／上限 200；`offset: int,否`；`kind: enum,否`；`status: enum,否`；`q: str,否`（FTS） | `items[]`（每项含 `variants[]`）、`next_cursor`、`total_estimate`、`limit`、`offset` | 422 `VALIDATION_ERROR`（`kind` 不在 6 枚举内） |
| `GET /packages/stats` | 工作台四个数字 | 无 | `packages`、`variants`、`unverified`、`ready`、`templates`（五键，实测 `{"packages":1,"variants":1,"unverified":0,"ready":0,"templates":1}`） | 无（幂等只读） |
| `POST /packages` | 新建 Package（可同时落 variants） | `title: str,是`（≤120）；`kind: enum,是`；`org/role/location/summary: str,否`；`start_date/end_date: str,否`（`YYYY` 或 `YYYY-MM`）；`is_current: bool,否`；`tech_stack/tags: str[],否`；`outcomes: [{metric,from,to}] 或 str[],否`；`evidence: str[],否`；`status: enum,否`（默认 `draft`）；`source: enum,否`；`variants: VariantIn[],否` | **201** + 完整对象：`id`、`content_hash`、`variants[]`、`created_at` 等 21 键（实测） | 422 `VALIDATION_ERROR`：`is_current=true` 且带 `end_date`；或 variant 缺 `bullet_key/tone/lang` |
| `POST /packages/draft` | 对话式打包：自由文本 → **草稿（不落库、零出网）** | `text: str,是`（1–8000）；`kind/lang/title/org/role,否` | `PackageDraftOut`：解析出的字段 + `missing[]` + `warnings[]` | 422 `VALIDATION_ERROR`（`text` 为空） |
| `GET /packages/{id}` | 单个 Package（不含 variants） | 路径 `id` | `id/title/kind/org/role/start_date/end_date/is_current/location/summary/status/source/content_hash/deleted_at/created_at/updated_at/tech_stack[]/tags[]/outcomes[]/evidence[]`（实测 21 键） | 404 `NOT_FOUND`（`details.resource="package"`） |
| `PUT /packages/{id}` | 局部更新（未提供字段不变） | 同 `POST` 但全可选 | 更新后完整对象 | 404 `NOT_FOUND`；422（日期格式非法） |
| `DELETE /packages/{id}` | 软删（`deleted_at` 置位，可 restore） | 路径 `id` | `{id, deleted_at}` | 404 `NOT_FOUND` |
| `POST /packages/{id}/restore` | 撤销软删 | 路径 `id` | 恢复后的对象（`deleted_at=null`） | 409 `CONFLICT`（未删除时 restore） |
| `POST /packages/{id}/duplicate` | 复制为新草稿 | 路径 `id`；可选 `title` | **201** + 新对象，标题默认追加「（副本）」（实测） | 404 `NOT_FOUND` |
| `GET /packages/{id}/variants` | 列 bullet 变体 | `tone: enum,否`；`verified: bool,否`；`bullet_key: str,否`；`limit/offset,否` | `items[]` + `next_cursor/total_estimate/limit/offset` + **`groups`、`bullet_keys[]`、`tones[]`**（分组计数，实测） | 404 `NOT_FOUND`（父 Package 不存在） |
| `POST /packages/{id}/variants` | 新增变体 | `bullet_key: str,是`（≤40）；`text: str,是`（≤400）；`tone: enum,是`（`impact/technical/leadership/concise/ats`）；`lang: enum,是`；`keywords: str[],否`；`metrics: [{...}],否`；`verified: bool,否` | **201** + 变体对象（含 `char_len`、`llm_generated`） | 422 `VALIDATION_ERROR`（`tone` 越界，实测报「Input should be 'impact'…」） |
| `PUT /packages/{id}/variants/{variant_id}` | 改变体（局部） | 同 `POST` 全可选 + `verified` | 更新后变体对象 | 404 `NOT_FOUND`；422（`text` 超 400） |
| `DELETE /packages/{id}/variants/{variant_id}` | 删变体（硬删） | 路径两 id | `{deleted: true, id}` | 404 `NOT_FOUND` |
| `POST /packages/{id}/verify` | 批量核验变体（**必须给 ids**） | `variant_ids: str[],是`（1–500）；`verified: bool,否`（默认 true） | `{updated: int, verified_ids[]}` | 422 `VALIDATION_ERROR`（缺 `variant_ids`，实测报 field required） |
| `POST /packages/{id}/variants/generate` | LLM 生成变体（**必须先有 consent preview**） | `preview_id: str,是`；`bullet_keys: str[],否`；`tone/lang,否`；`count: int,否` | `{variants[], preview_id, warnings[]}` | 428 `LLM_CONSENT_REQUIRED`（无 preview）；409 `LLM_CONSENT_MISMATCH`（payload 变了）；503 `LLM_DISABLED` |
| `POST /packages/reindex` | 重建 FTS 全文索引 | 无（`{}` 可） | `{indexed: int}`（实测 `{"indexed":3}`） | 500 `STORAGE_ERROR`（索引损坏时） |

**别名路由（v1.17 定版）：长路径是唯一推荐，短路径 `deprecated`**

同一处理器挂了两套路径。**契约推荐且唯一支持的写法是带父 id 的长路径**（`/packages/{id}/variants/{variant_id}`）——它能校验变体归属、防止跨 Package 越权改。**不带父 id 的短路径（`/variants/{variant_id}`）标记 `deprecated`**：不删（已有前端可能已写），但**不再为其新增行为**，且任何校验差异以长路径为准。t11 只按长路径判验收；短路径被调用时行为必须与长路径**逐字段一致**（当前二者指向同一处理器，故一致）。

| 端点 | 语义 | 请求参数 | 成功响应关键字段 | 失败样例 |
|---|---|---|---|---|
| `PATCH /packages/{id}` | `PUT /packages/{id}` 的别名（局部更新） | 同 PUT | 同 PUT | 同 PUT |
| `PATCH /packages/{id}/variants/{variant_id}` | `PUT .../variants/{variant_id}` 的别名 | 同 PUT | 同 PUT | 同 PUT |
| `PUT /packages/{id}/variants/{variant_id}` | 已登记于上表（此处仅补别名对照） | 同上 | 同上 | 同上 |
| `PATCH /variants/{variant_id}` | 变体更新的**无父级短路径**别名 | 同 PUT | 同 PUT | 404 `NOT_FOUND`（变体不存在） |
| `PUT /variants/{variant_id}` | 同上（短路径） | 同 PUT | 同 PUT | 404 `NOT_FOUND` |
| `DELETE /variants/{variant_id}` | 变体删除的短路径别名 | 无 | `{deleted:true,id}` | 404 `NOT_FOUND` |

### 17.2 Template 族

| 端点 | 语义 | 请求参数 | 成功响应关键字段（实测） | 失败样例 |
|---|---|---|---|---|
| `GET /templates` | 列模板（软删过滤） | `limit/offset,否`；`lang: enum,否` | `items[]`（模板摘要，**不含 blocks**）、`next_cursor`、`total_estimate`、`limit`、`offset` | 422（`lang` 越界） |
| `GET /templates/{id}` | 模板详情**含 blocks 与 slots** | 路径 `id` | `id/name/lang/source_kind/source_file_id/page_limit/is_default/target_role_family/layout/created_at/updated_at/blocks[]`（每 block 含 `slot` 或 `slots[]`）（实测） | 404 `NOT_FOUND` |
| `GET /templates/default` | 取默认模板（前端首屏） | 无 | 同 `GET /templates/{id}` | 404 `NOT_FOUND`（**实测**：`{"code":"NOT_FOUND","message":"还没有默认模板","details":{"resource":"template"},"hint":"先导入一份简历生成模板"}`） |
| `DELETE /templates/{id}` | 软删模板 | 路径 `id` | `{id, deleted_at}` | 404 `NOT_FOUND`；409 `CONFLICT` `details.reason="TEMPLATE_IS_DEFAULT"`（默认模板需先切换，推定） |

> 注：**没有** `POST /templates` 路由。**模板的唯一来源 = `POST /imports/{id}/commit`**（或后续 builtin 种子）。`models.TemplateIn` 目前未被任何端点使用（§17.8 第 7 项，P2）：它作为 `POST /templates`（P2）的**预留模型**存在，**契约明确它当前不参与任何读写**——不允许「模型留着、端点没有、两边都不解释」的状态。若 P2 不做，coder 应删除该模型。

### 17.2.1 模板写侧分级（**P0 未降级**；以下全部尚未实现）

**核心路径不变**：首次结构生成 = 「导入校对」——`PUT /imports/{id}/draft` 改草稿 → `POST /imports/{id}/commit` 生成 `template_block`（**已实现、已实测**，见 §5.1）。因此 **post-hoc 编辑模板不是核心路径**，它是「模板复用/微调」的增强。

| 端点 | 级别 | 语义 | 请求参数 | 成功响应关键字段 | 失败样例 |
|---|---|---|---|---|---|
| `POST /templates/{id}/default` | **P1（t10 前置）** | 设为唯一默认（读侧 `GET /templates/default` 已实现，**写侧缺**） | 无 | `{id, is_default:true}`，其余模板被置 false | 404 `NOT_FOUND` |
| `POST /templates/{id}/blocks/reorder` | **P1（t10 前置）** | 批量重排 block 顺序 | `order: [{block_id:str, order_index:int}],是` | `{blocks[]}`（新顺序） | 422 `VALIDATION_ERROR`（id 不属于该模板） |
| `POST /templates/{id}/validate` | **P1（t10 前置）** | 结构体检（无 header / 缺 required slot / page_limit 冲突） | 无 | `{valid:bool, issues:[{code,block_id,message}]}` | 无（体检结果恒 200） |
| `POST /templates` | `[P2 未实现]` | 手工建模板（当前唯一来源是 import commit） | `TemplateIn`（`name/source_kind/lang/page_limit/layout/is_default`） | 201 + 模板对象 | 422 `VALIDATION_ERROR` |
| `POST /templates/{id}/blocks` | `[P2 未实现]` | 新增 block | `BlockIn`（`order_index/block_type/heading/bound_package_kind/style/page_break_before/max_bullets/static_text/repeat_per_package`） | 201 + block 对象 | 422（`order_index` 冲突/类型越界） |
| `PATCH /templates/{id}` | `[P2 未实现]` | 改模板元信息 | 同 `TemplateIn` 全可选 | 更新后模板对象 | 404 `NOT_FOUND` |
| `POST /blocks/{id}/slots` | `[P2 未实现]` | 给 block 加槽位 | `SlotIn`（`slot_key/…`，`slot_key` 正则 `^[a-z][a-z0-9_.]{0,40}$`） | 201 + slot 对象 | 422（`slot_key` 非法/重复） |
| `POST /blocks` | `[P2 未实现]` | 独立建 block（不带模板上下文，**推荐用 `/templates/{id}/blocks`**） | `BlockIn` + `template_id` | 201 + block | 422 |
| `PATCH /blocks/{id}` | `[P2 未实现]` | 改 block | 同 `BlockIn` 全可选 | 更新后 block | 404 |
| `DELETE /blocks/{id}` | `[P2 未实现]` | 删 block（连带 slots） | 无 | `{deleted:true}` | 409 `CONFLICT`（block 被 build 引用） |
| `PATCH /slots/{id}` | `[P2 未实现]` | 改槽位 | `SlotIn` 全可选 | 更新后 slot | 404 |
| `DELETE /slots/{id}` | `[P2 未实现]` | 删槽位 | 无 | `{deleted:true}` | 409 `CONFLICT`（required slot 且有 build 引用） |
| `GET /templates/{id}/blocks` | `[P2 未实现]` | 单独列 block（`GET /templates/{id}` 已内联返回 `blocks[]`，此端点冗余） | `parent_block_id: str,否` | `{items[]}` | 404 |

> **分级规则（给 t11）**：`P1` = t10 前置，未实现记 `PENDING(P1)` 但仍要跑用例（记录当前 404）；`[P2 未实现]` = 增强项，**未实现不算缺陷**，只要求契约不误导（不得让用户以为 P0 流程缺块）。

### 17.3 LLM 适配层补充

| 端点 | 语义 | 请求参数 | 成功响应关键字段（实测） | 失败样例 |
|---|---|---|---|---|
| `GET /llm/status` | provider 就绪状态（**不含 key**） | 无 | `provider`、`provider_label`、`base_url`、`model`、`model_analysis`、`key_set`(bool)、`ready`、`not_ready_reason`、`reachable`、`last_check_at`、`allowed_hosts[]`、`timeouts{}`（实测） | 无（恒 200；未配置时 `ready=false`） |
| `POST /llm/preview` | **建 consent preview（不调上游）** | `purpose: enum,是`（见 `GET /llm/purposes`）；`provider_override: enum,否`；`selections: {...},否`；`options: {...},否` | `preview_id`、`purpose`、`provider`、`model`、`endpoint_host`、`expires_at`、`payload{}`、`payload_sha256`、`est_tokens`、`fields[]`、`redactions[]`、`warnings[]`（实测） | 422 `VALIDATION_ERROR`（`purpose` 越界）；503 `LLM_DISABLED` |
| `GET /llm/previews` | 列 preview（审计用） | `limit/offset,否`；`status: enum,否` | `items[]`、`next_cursor`、`total_estimate`、`limit`、`offset` | 无 |
| `GET /llm/previews/{preview_id}` | 取单个 preview（**前端确认框数据源**） | 路径 `preview_id` | `preview_id/purpose/provider/model/endpoint_host/expires_at/payload/payload_sha256/est_tokens/fields[]/redactions[]/status/seconds_left/created_at`（实测 13 键） | 404 `NOT_FOUND`；410 `LLM_CONSENT_EXPIRED`（过期后取用） |
| `POST /llm/previews/{preview_id}/reject` | 用户拒绝（作废 preview） | 路径 `preview_id` | `{preview_id, status:"rejected"}`（实测） | 404 `NOT_FOUND` |
| `GET /llm/purposes` | 用途清单（前端渲染字段说明） | 无 | `purposes[]`，每项 `{purpose, tier("analysis"/"chat"), json_mode, max_tokens}`（实测：`jd_analyze` 4096、`company_profile` 3072、`build_suggest` 4096…） | 无 |
| `GET /llm/egress-log` | **上行外发审计**（只有字段名与主机，无内容） | `limit/offset,否` | `items[]`（`endpoint_host/field_names/payload_bytes/ok/error_code/created_at`）、`next_cursor` 等 | 无（P1 运维端点，前端可不展示） |

### 17.4 Job 族

| 端点 | 语义 | 请求参数 | 成功响应关键字段（实测） | 失败样例 |
|---|---|---|---|---|
| `GET /jobs` | 列作业（审计） | `status: enum,否`；`kind: str,否`；`limit/offset,否` | `items[]`，每项 `{id, kind, status, progress, message, result_json, error_json, created_at, finished_at}`、`next_cursor`、`total_estimate` | 无 |
| `GET /jobs/{job_id}` | 取单个作业 | 路径 `job_id` | 同上，单对象；**`result_json` 在此为对象** | 404 `NOT_FOUND`（`details.resource="job"`） |

> ⚠️ **`result_json` 类型不一致**（实测）：列表返回**字符串**（`"{\"import_id\":…}"`），详情返回**对象**。前端必须 `JSON.parse` 容错，见 §17.8 偏差 4。

### 17.5 File 族

| 端点 | 语义 | 请求参数 | 成功响应关键字段（实测） | 失败样例 |
|---|---|---|---|---|
| `POST /files` | 上传任意附件（通用） | `multipart/form-data`，字段 `file: file,是` | **201** + `{id, sha256, original_name, ext, mime, bytes, kind, privacy}` | 413 `PAYLOAD_TOO_LARGE`；415 `UNSUPPORTED_MEDIA_TYPE` |
| `GET /files` | 列附件 | `limit/offset,否`（默认 50 上限 200）；`kind: str,否` | `items[]`（同上结构）、`next_cursor`、`total_estimate` | 无 |
| `GET /files/{attachment_id}` | **下载附件字节** | 路径 `attachment_id` | **二进制流**（实测 `Content-Type: application/pdf`，200），**不是 JSON 信封** | 404 `NOT_FOUND` |
| `DELETE /files/{attachment_id}` | 删附件（**有引用守卫**） | 路径 `attachment_id` | `{deleted: true, id}` | **409 `FILE_IN_USE`** + `details{referenced_by[]}`（被证件照/导入候选/产物引用时，v1.17 定版）；404 `NOT_FOUND` |
| `GET /files/profile-photo` | **取证件照字节**（前端头像） | 无 | 二进制流（`image/png` 或 `image/jpeg`） | 404 `NOT_FOUND`（**实测**：`{\"code\":\"NOT_FOUND\",\"message\":\"尚未上传照片\",\"details\":{\"resource\":\"profile_photo\"}}`） |

> 二进制端点**不走** `{ok,data,request_id}` 信封——前端不能用统一 `resp.json()`；错误时才回信封（实测 404 为 JSON）。

**`GET /files` 返回的 `original_name` 是用户真实文件名**（实测 `sample_zh.pdf`）。契约允许本机展示（用户要认得自己的文件），但**永不进任何 LLM payload / 审计外发记录 / 导出文件名**——与 §5.4 的 `EXCLUDED_PATHS` 同源。`GET /files/{id}` 下载响应头里的 `Content-Disposition` 同样只用本机展示，不参与命名模板。

### 17.6 Import 列表与详情（补充 §5.1）

| 端点 | 语义 | 请求参数 | 成功响应关键字段（实测） | 失败样例 |
|---|---|---|---|---|
| `GET /imports` | 列导入记录 | `limit/offset,否`（默认 20）；`status: enum,否` | `items[]`（`import_id/job_id/status/parser/attachment_id/template_id/created_at/updated_at`）、`next_cursor`、`total_estimate` | 无 |
| `GET /imports/{id}` | 导入详情（**不含 draft**） | 路径 `import_id` | 同列表项单对象（实测 `status:"committed"`、`template_id` 有值） | 404 `NOT_FOUND` |
| `POST /imports/{id}/export-draft` | 把 draft 导出为 Markdown 草稿 | 路径 `import_id` | 201 + `{attachment_id, filename, bytes}` | 409 `CONFLICT` `details.reason="IMPORT_ALREADY_COMMITTED"`（提交后 draft 冻结，推定）；422（未生成 draft） |
| `DELETE /imports/{id}` | **软删导入历史**（`import_job.deleted_at`，可恢复；**文件与行都保留**，真删走 `scripts/prune_probe_data.py --prune-import-jobs` 且需用户同意） | 路径 `import_id` | `{import_id, deleted:true, deleted_at, restore_endpoint, template_retained:{kept,template_id,note}, note}`（实测 `:117-130`） | 404 `NOT_FOUND` `details{resource:"import",id}`；**重复删不报错**：`WHERE deleted_at IS NULL` 命中 0 行 → 仍回 200 且 `deleted_at` 保持首次值（幂等，便于重试） |
| `POST /imports/{id}/restore` | 撤销软删 | 路径 `import_id` | `{import_id, deleted:false, deleted_at:null}` | 404 `NOT_FOUND`（id 不存在）；**对未删记录调用亦 200**（幂等） |

> ⚠️ **`job_id` 在详情里会变 null**（实测）：`POST /imports` 返回 `job_id`，但 `GET /imports/{id}` 在 commit 后为 `job_id: null`。见 §17.8 偏差 3。

### 17.7 杂项

| 端点 | 语义 | 请求参数 | 成功响应关键字段（实测） | 失败样例 |
|---|---|---|---|---|
| `GET /now` | **`internal`** 调试端点（服务器时间；前端对齐时区/倒计时可用，但**不做兼容承诺**） | 无 | `{now: "2026-10-23T03:46:56+08:00"}` | 无 |
| `GET /naming/template` | 取当前命名的默认模板串 | 无 | `{naming_template: "{position}-{name}-{school}"}` | 无 |
| `PUT /naming/template` | 改默认命名模板 | `{naming_template: str,是}`（≤200，须含合法变量） | `{naming_template: "..."}` + `warnings[]` | 422 `VALIDATION_ERROR`（未知变量 `{foo}`，由 §9.1 语法校验） |

> `POST /naming/validate` 已在 §9.3 登记；**实测补充**它的真正入参不是 `context`，而是**扁平字段**：`{pattern, lang, position, company, overrides{}, date}`；`variables[].source` 取值实测有 `"build.position"` 与 `"override"`；缺变量时 `valid=false` + `errors[]` 每条带 `field`，且 `resolved="-"`、`filename=""`。

### 17.8 实测发现的口径偏差（4 条文档错、3 条实现缺陷）

**文档侧（本轮已按实测改正）**

1. **`/health` 的 `data` 形态**：实测 `{"db":{"ok":true,"path":…,"schema_version":4},"time":"…","llm_ready":true,"version":"1.0.0","build":{…},"warnings":[]}` —— `db` 是**对象**不是 `"ok"` 字符串；时间字段是 **`time`** 不是 `started_at`。§2 已改。
2. **`/settings.timeouts` 实际值**：实测 `{connect_s:5.0, read_s:175.0, total_s:180.0}`，与 §10.4 早前写的 60/90 **不符**。§10.4 已改为「以 `/settings` 实际返回为准」。前端**不得硬编码**这三个数。
3. **列表 `limit` 的语义**：实测 `GET /jobs?limit=3` 回 `limit:1`——**响应里的 `limit` 是「本页实际返回条数」**，不是请求值。前端分页不得依赖它。
4. **`result_json` 列表/详情类型不一致**：列表为字符串、详情为对象，见 §17.4。

**实现侧（我不改代码，报 coder）**

| # | 严重度 | 归谁 | 现象 | 处置 |
|---|---|---|---|---|
| **`D-35`** | **P0** | coder | **`is_current` 恒为 1，`end_date` 被静默清空**（详见 §17.8.1） | 修 `repos.py:686` + 数据修复 |
| 6 | **P1** | coder | **`auto_redact` 仍允许 `"school"`**（`models.py:SettingsPatch` 的 Literal 含 `"school"`）：用户勾一次即让整条竞争力链路退化（`school_signal` 无输入 → `SCHOOL_SIGNAL_UNUSED`），与 **ADR-20**「校名必须被消费」直接冲突 | 从可选值中移出 `"school"`；`auto_redact` 只允许 `name`/`phone`/`email`/`id` |
| 7 | **P2** | coder | **`models.TemplateIn` 无端点使用**：模板无法手工创建 | 删掉，或明确保留为预留模型（§17.2.1 已写明「模板唯一来源 = import commit」，**不得两边都留着不解释**） |
| **`D-39`** | **P2** | coder（**已修复，2026-10-23 04:15:24**） | **「优先」曾被判成硬门槛**：`SCHOOL_GATE_RE` 一度把 `优先` 与 `仅限/必须` 编进同一组动词 → 「985/211 院校优先」输出 `hard_filter=true`，用户会被告知「该公司卡 985」而放弃可投岗位。现拆为 `HARD_VERBS`/`SOFT_VERBS`（`jd_analysis.py:31-35`），实测 `['985/211 院校优先']` → `false` + `['985','211']` + `不限（偏好 985/211）` | 判据见 §7 参数化用例 1–3、8（AC-ANL-11），**不得回退成单组动词** |
| **`D-41`** | **P2** | coder（**已修复，2026-10-23 04:17:29**） | **并列档位曾遭截断**：`["仅限 985/211 院校"]` 曾回 `threshold='985'`、`preferred_tiers=['985']`（丢 `211`；根因 `SCHOOL_HARD_RE` 的 `only` 分支只捕获单个档位） | 实测通过：`仅限 985/211` / `985、211` / `985 和 211` 均回 `threshold='985/211'` + `["985","211"]`。见 §17.8.2（保留为回归判据 AC-ANL-12） |
| **`D-42`** | **P2** | coder（**已修复，2026-10-23 04:17:29**） | **门槛不匹配时不给理由**：`gate_failed=true` 但 `gap_notes` 为空，用户只看到 `verdict="weak"` 不知道该补什么 | 实测 `jd_analysis.py:387-393` 已插入「院校层次「X」不在 JD 门槛「985/211」内，需靠经历或成绩补足」；`recognized=false` 时**不得**产生该结论。见 §17.8.2 |

**实现侧（v1.34 追加：t12 AC harness 真跑发现的 6 处产品缺陷，均已修）**

| # | 严重度 | 归谁 | 现象 | 处置 |
|---|---|---|---|---|
| **`T-1`..`T-6`** | **P0/P1** | coder（**已修复，2026-10-23 06:1x，t12 AC harness 真跑发现**） | **六处产品缺陷**（accepted harness 抓出、coder 修、captain 抽查）：① `export_service.precheck_naming` 调不存在的 `BuildRepo().require()` → 导出预检 500，改 `get()` + `NOT_FOUND`；② 同文件 `assemble()` 在模板被软删时**静默继续** → 改 409 `NO_DEFAULT_TEMPLATE`（不猜最新模板）；③ 同文件 md 导出写 `engine='markdown'` 违反 schema CHECK → 改 `jinja2`；④ `naming.raise_on_errors` 的 422 缺 `hint`（AC-NAME-04 要求可执行提示）→ 补；⑤ `consent.complete()` 在 `provider=off` 时**仍发请求** → 改硬拦 503 `LLM_DISABLED`（**连已确认预览也不发**，见 §5.3 零出网）；⑥ `errors.py` 405 原被映射成 400 → 新增 `METHOD_NOT_ALLOWED: 405` | 逐条回归：`tests/acceptance` 六个用例；⑤ 另加「off 时 `outbound_calls == 0`」 | 
| **`T-7`** | **P1** | coder（**已修复，2026-10-23 08:0x**） | **`also_create_packages` 对「建不出包」的 entry 静默 `if not kind: continue`**：映射不出 `bound_package_kind` 时不建包、不告警、不记录，`created_packages[]` 里也没有——用户以为经历已入库，仓库里却没有。同类隐患：只有标题没有正文的 entry 会生成「点开一无所有的空经历包」。**根因是「跳过」没有出口**，不是判断写错 | 分三支并各自有出口：education → 静默跳过（契约规定，正常）；无正文 → 不建包 + `warnings[PACKAGE_SKIPPED{reason:"empty_entry"}]`；映射不出 → 不建包 + `warnings[PACKAGE_SKIPPED{reason:"no_kind_mapping"}]`。判定顺序写死在 §5.1「三分支判定」，AC-IMPORT-21 覆盖 |
| **`T-8`** | **P1** | coder（**未修复，2026-10-23 08:1x**） | **`resume_build` 归档没有写入口**：`repos.py:1658 set_archived()` 已实现、`GET /builds?include_archived` 已读，但 `PATCH /builds/{id}` 的允许键白名单里没有 `archived`，也没有独立归档路由 → 前端**无法归档**，而 `DELETE` 仍是硬删（`api/builds.py:134`）。后果：用户想「收起来」只能硬删，产物变孤儿 | 按 §8 表接线：`PATCH {archived:true|false}` 写/清 `archived_at`；`DELETE` 改默认归档，硬删须 `?hard=1&confirm=<id>` 且先落快照。AC-BUILD-16 覆盖 |

#### 17.8.1 `D-35`（P0，归 coder）：`is_current` 恒真 + `end_date` 静默清空

**根因（一行三目运算符，`server/app/repos.py:686`）**

```python
payload[key] = 1 if isinstance(value, bool) and key in ("is_current",) else (int(value) if key == "is_current" else value)
```

条件只看「是不是 bool」，**不看 bool 的值** → `False` 也编码成 `1`。于是 `PackageIn.is_current=False` 落库成 `1`；`create()`（`repos.py:541-542`）随后看到真值就执行 `payload["end_date"] = None`。

**后果（用户可见的数据损坏）**：用户填的结束时间被抹掉，简历上这条经历写成「至今」。**100% 复现，非偶发。**

**证据**

```bash
# 真库现状：18 行 package，18 行 is_current=1，18 行 end_date 为 NULL
sqlite3 data/app.db "select count(*), sum(is_current), sum(end_date is null) from package;"
# 18|18|18

# 两次不同 body 均复现
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"title":"t","kind":"project","start_date":"2024-01","end_date":"2024-06"}' \
  http://127.0.0.1:8765/api/v1/packages | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d['start_date'],d['end_date'],d['is_current'])"
# 2024-01 None True
```

**接受判据（t11 复验）**：`POST /packages` 带 `end_date:"2024-06"` → 回读 `end_date == "2024-06"` 且 `is_current is false`；`PATCH /packages/{id}` 同样往返相等。见 **AC-BUILD-13**。

**数据修复的契约依据（防止用「按 `created_at` 推算」之类办法填假数据）**：`package.end_date` 的**唯一权威来源**是 ① 用户显式输入，或 ② 该 Package 来源 `import_job.draft_json` 中对应 entry 的 `date_range`（实测草稿里含 `date_range` 的 entry 有 **182 条**，可作恢复源）。**两者都拿不到时留 `null` 并写 `warnings`，不得猜测。**

> 编号说明：`D-*` 缺陷编号的主档在 `docs/REVIEW-CHECKLIST.md`（supervisor 产物，不在我写入范围）。本节登记 `D-35` 的契约侧与验收侧内容，登记编号由 captain/supervisor 同步。

#### 17.8.2 院校信号缺陷族（D-39 / D-41 / D-42，全部已修复，**保留为回归判据**）

三条同源、同类、同害：**它们不会让人觉得「文档写错了」，而是直接让人少投一家公司或误判自己没戏**。因此单独成节，判据（AC-ANL-09/10/11/12）必须长期保留，任何一条回退都按实现缺陷处理，不得以「需要重新设计」为由删除断言。

| 编号 | 现象 | 危害（为什么单独列） | 修复时点 | 回归判据 |
|---|---|---|---|---|
| **D-39** | `优先` 与 `仅限/必须` 编进同一组动词 → 「985/211 院校优先」输出 `hard_filter=true` | 用户被告知「这家卡 985」，**放弃本来能投的岗位** | **04:15:24** | AC-ANL-11（用例 1/2/3/8 + 动词分组反向断言） |
| **D-41** | 并列档位截断：`仅限 985/211` 只回 `["985"]`，丢 `211` | **211 硕士被判不达标**，且用户无法从 UI 看出「211 其实被认了」 | **04:17:29** | AC-ANL-12（`985/211`、`985、211`、`985 和 211` 三种写法） |
| **D-42** | 门槛不匹配时 `gap_notes` 为空（只给 `weak` 不给理由） | 用户只看到「弱」，不知道弱在哪，**无法补足**；比不给结论更糟 | **04:17:29** | AC-ANL-11 附加断言：`gate_failed=true` 时 `gap_notes` 非空且含门槛值与用户层次原文 |

**诚实性约束（三条共用）**：`recognized=false`（院校未识别）时**不得**产生 D-42 那类「不在门槛内」的结论——未知不是劣势，`gap_notes` 只能写「未识别，按『其他』记录」。已修复版本（`jd_analysis.py:387-393`）按此实现，改代码时不得丢失该分支。

### 17.9 本节的实跑复现命令

```bash
cd resume-warehouse
rm -rf data/.tmp_planner && mkdir -p data/.tmp_planner
DATA_DIR=data/.tmp_planner .venv/bin/python server/server.py --port 8799 &
B=http://127.0.0.1:8799/api/v1
curl -s $B/health | python3 -m json.tool
curl -s -F "file=@data/imports/sample_zh.pdf" $B/imports -o /tmp/imp.json   # 201
IMP=$(python3 -c "import json;print(json.load(open('/tmp/imp.json'))['data']['import_id'])")
curl -s -X POST -H 'Content-Type: application/json' -d '{"template_name":"探测模板","set_default":true}' $B/imports/$IMP/commit
curl -s -X POST -H 'Content-Type: application/json' -d '{"title":"t","kind":"project","end_date":"2024-06"}' $B/packages   # 复现偏差 5
curl -s $B/settings | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['timeouts'])"
```

> 复现完**必须** `rm -rf data/.tmp_planner` 并确认没有残留进程；临时库只能写 `data/.tmp_xxx/`（§1.5）。
