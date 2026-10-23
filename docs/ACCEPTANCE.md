# ACCEPTANCE — 可测验收基线

> 冻结 **v1.32**（2026-10-23 09:3x）：新增 **AC-CONFLICT-02**（已决议降级 + **反向恢复**）、**AC-PROF-01**（`education-facts` 写入/快照/不清半行/真源结构断言）、**AC-PROF-02**（到岗时间单一真源 + `available_date` 不参与渲染的反向断言）。
> 冻结 **v1.31**（2026-10-23）：新增 **AC-IMPORT-21**（`also_create_packages` 三分支各有出口 + 顺序断言）、**AC-BUILD-16**（归档 ≠ 删除，含 `CONFIRM_MISMATCH` 与无悬空行反向断言）。
> 冻结 **v1.30**（2026-10-23）：新增 **AC-ANL-16/17/18**（`matched_evidence` 三源可回溯、两个数组皆空才算没匹配到、人工改判优先级与不可覆盖）。
> 冻结 **v1.29**（2026-10-23）：新增 **AC-ANL-13/14/15**（`jd_analyze` 带经历要点 + 预算 12/6000、本地覆盖改判与反向约束、`matched_package_ids` 本地计算且指向 ready 包）。
> 冻结 **v1.28**（2026-10-23）：① **修复 3 处 AC ID 撞号**（`AC-NAME-01`(P1)→**AC-NAME-09**、`AC-PDF-11`(P1)→**AC-PDF-19**、`AC-PDF-12`(P2)→**AC-PDF-20**），撞号会让后一条条款在账本里被覆盖、永远无法单独判定；② §0 新增硬规则「一条 ID 一条条款」+ 可复跑判据；③ §14 模板区声明「状态行不计入条款总数」；④ §15 补两行映射（英文简历、PDF 结构与打印）。
> 冻结 **v1.27**（2026-10-23）：① **条目 ID 格式纪律**（首列一律不加粗/不加反引号，全文一种写法）——历史 28 行加粗已统一，根因是取数脚本正则不认加粗行（M9）；② **AC-LLM-03** 增「已确认预览也不得在 `provider=off` 下发送」判据（`outbound_calls == 0`）。
> 冻结 **v1.26**（2026-10-23）：**AC-PDF-15 ④ 反作弊口径改定**（中位字号 ≥10.5 pt、行距比 ∈[1.10,1.25]）；新增 **AC-PDF-18**（首档 11 pt、条目头单行 + 日期列 12%–22%、反向断言「不得靠裁内容换字号」）。
> 冻结 **v1.25**（2026-10-23）：新增 **AC-PDF-16**（页眉白名单、前 4 行无学位词）、**AC-PDF-17**（教育段日期原文）、**AC-EN-04**（英文变体生成与合规）、**AC-BUILD-15**（`PUT` 是 `PATCH` 真别名）。
> 冻结 **v1.24**（2026-10-23）：新增 **AC-EN-01**（en 版骨架区 CJK 计数 = 0）、**AC-EN-02**（en 变体两种情况都不许空段 + `LANG_FALLBACK`）、**AC-EN-03**（语言不影响结构）。
> 冻结 **v1.23**（2026-10-23）：新增 **AC-IMPORT-19**（commit 三类内容不得丢，I15）、**AC-IMPORT-20**（回填可回溯 `profile_fields_source`）、**AC-CONFLICT-01**（中英 `SOURCE_CONFLICT` 分语言取值，禁合并）、**AC-NAME-01**（英文名全大写不互推）。
> 冻结 **v1.22**（2026-10-23）：新增 **AC-IMPORT-17**（删导入不删模板，反隐式级联，P0）、**AC-IMPORT-18**（溯源不断链 I14 + R-c 校验，P0）。
> 冻结 **v1.20**（2026-10-23）：§0 判定规则新增「**状态口径**」——条目状态一律以条目行为准，文件头只写版本与条目编号（M6），呼应 D-43。
> 冻结 **v1.19**（2026-10-23）：`AC-ANL-12` 状态标注口径调整（**结论见条目行**，此处不再重复）。
> 冻结 **v1.18**（2026-10-23）：新增 **AC-ANL-11**（门槛动词分组「优先≠门槛」，P0，逐行跑 §7 用例 1/2/3/5/6/7/8，含动词分组反向断言）、**AC-ANL-12**（并列档位不得截断，P0，`985/211`、`985、211`、`985 和 211` 三种写法）。
> 冻结 **v1.17**（2026-10-23）：修复 **10 处表格列数缺陷**（`AC-PDF-11..15`/`AC-FILE-01`/`AC-BUILD-12..13`/`AC-ANL-09..10` 补「验证方式」列、`AC-LLM-11` 多余分隔合并）；判据文本未改。执行表列自检见 API-CONTRACT §16.0 M3，当前 mismatch **0**。
> 冻结 **v1.16**（2026-10-23）：`AC-PDF-11` 改为 `density="original"` 口径（可用高度 817.65pt / 版心 564.9pt）；新增 **AC-PDF-15**（density 默认值、非法值 422、反作弊下限）；`facts` 整段渲染见 AC-PDF-14。
> 冻结 **v1.15**（2026-10-23）：新增 **AC-ANL-09**（未识别≠普通本科，D-37）、**AC-ANL-10**（优先 vs 硬门槛）、**AC-PDF-11..14**（单页降档留痕/两页兜底/照片不降档/`facts` 整段渲染，D-38）。
> 冻结 **v1.14**（2026-10-23）：新增 **AC-BUILD-13**（P0，`is_current`/`end_date` 日期往返回归，锁 `is_current` 只能来自显式输入与 422 护栏；根因 `repos.py:686`，状态见条目行与 API-CONTRACT §17.8.1）。
> 冻结 **v1.13**（2026-10-23）：新增 **AC-FILE-01**（删附件引用守卫 409 `FILE_IN_USE`）与 **AC-BUILD-12**（无默认模板时 assemble 必须拒绝，不静默取最新）；路由一致性判据（REV/FWD）改由 `scripts/check_route_parity.py` 唯一定义，三数标 `PENDING(canonical-script)`。
> 冻结 **v1.12**（2026-10-23）：AC-LLM-11 按实现拆三档（`empty_content`/`partial_json` → 502；**可解析截断 → 200 + `OUTPUT_TRUNCATED` 警告**）；AC-PHOTO-05 保持 P0（`DELETE` 已回 200 六字段，不派 coder）；§13 与 §16 一致性判据联动。
> 冻结 **v1.11**（2026-10-23）：新增 **AC-ENV-10**（`/health.build` 唯一判据，D-27）、**AC-ENV-11**（`app_port` 生命周期，D-26）、**AC-IMPORT-14**（照片候选不变量 + `PHOTO_DECODE_FAILED`）；AC-IMPORT-01 改「`job_id` 必需且同源」。
> 冻结 **v1.10**（2026-10-23）：导入 lane 定版——AC-IMPORT-01 改 **201 + 内联 draft**；AC-IMPORT-03 补「导入只产出候选、`photo_path` 不被写入」判据；新增 **AC-IMPORT-11**（`blocks` 唯一真值源/`sections[]` 派生自洽）、**AC-IMPORT-12**（`needs_llm_fallback` 不打 LLM）、**AC-IMPORT-13**（夹具缺失记 `SKIP(no-fixture)`，不得记 PASS）；AC-PHOTO-01 增「距页面右缘 9.13 pt」。
> 冻结 **v1.9**（2026-10-23）。v1.9（D-19）：新增 **§8.2 竞争力与院校偏好** —— **AC-ANL-06**（竞争力必须消费校名）、**AC-ANL-07**（院校偏好不许编造）、**AC-PRIV-14**（校名真实上云且七项齐全）。
> 冻结 **v1.8**（2026-10-23）。v1.8：§7 新增 **AC-SKILL-01..04**（技能区逐字等于 `skills_json[].line` / 反向断言无 tag 块与标签云 / `tokens` 缺失降级不丢行 / `trim_courses` 默认关且裁剪进 warnings）；AC-UI-02/04 路径改 `web/`；路径口径随 D-15 统一为 `server/app/` + `web/`。
> 冻结 **v1.7**（2026-10-23）。v1.7：§12.1 新增集成硬门 **INT-13**（端口顺延后 `实际 bind == /health.data.port == json["port"]` 三值相等）与 **INT-14**（全部只读 GET 冒烟：200 + `json.loads` 成功 + 体内无 `b'` 脏值 + `/env` 字体名断言），并写入「反向 grep 判据须先实测基线为 0」的入册元规则；AC-ENV-06/09 改按 §3.3 的 JSON 五字段口径。
> 冻结 **v1.6**（2026-10-23）。v1.6：新增 AC-PRIV-13（`设置API密钥.command` 只回显 key_set/指纹，禁止任何 key 片段——对应 captain 的 D-08 闭环）。
> 冻结 **v1.5**（2026-10-23）。v1.5 按用户 m00265 收窄脱敏面：AC-PRIV-11 改为「姓名/电话/邮箱/照片脱敏、**学校名以真实值传输**」，AC-PRIV-12 增对照组（只含校名不得误报）。
> 冻结 **v1.4**（2026-10-23）。v1.4 收口：新增 AC-LLM-12（`LLM_TRUNCATED` 与 `LLM_BAD_RESPONSE` 互不重叠）；AC-LLM-11 补 `details.completion_tokens` 与「`length` + 非空 content 同样是截断错误、零警告」；`text_verified` 字段名统一（AC-PDF-05）；warnings 表已无截断码。
> 冻结 **v1.3**（2026-10-23）。v1.2 增照片（PHOTO）、下行抓取（FETCH）、宽路径脱敏（AC-PRIV-11/12）、端口顺延（AC-ENV-06/09）；v1.3 按用户决策**移除 Ollama**（重写 AC-LLM-01/03、KI-05，删除其警告码），并修复文件内 1 个 NUL 字节（此前会让 `grep` 判为 binary）。本文是**唯一验收口径**：`spec-verifier` / `qa` / `reviewer` 只按本文判定，不按口头描述判定。
> 每条都写成 **可执行或可观察** 的形式。凡标注「命令」的条目，必须在 `.venv` 内原样跑通；凡标注「手工」的条目，必须留截图或抓包文本作为证据。
> 配套：`docs/ARCHITECTURE.md`（选型与降级）、`docs/DATA-MODEL.md`（字段与不变量）、`docs/API-CONTRACT.md`（端点与错误码）、`docs/DESIGN-BRIEF.md`（界面硬约束）。

---

## 0. 环境与判定规则

| 项 | 值 |
|---|---|
| 基准机器 | 本机 macOS 26.5.1 arm64，Python 3.13.9（`/opt/anaconda3/bin/python3`），Node v22.22.1（仅用于语法检查，不承担运行时） |
| 解释器 | `resume-warehouse/.venv/bin/python`（`python3 -m venv --system-site-packages .venv` 创建；**裸 venv 会缺 flask，禁止用**） |
| 服务地址 | `http://127.0.0.1:8765` |
| **状态口径** | **本文档内任何条目的当前状态，一律以「条目行」为准**；文件头的冻结说明只记录**版本号与本次新增/改动的条目编号**，不写具体条目的通过/失败结论（M6）。复验命令：`grep -n 'KNOWN-FAIL' docs/ACCEPTANCE.md` 只应出现在条目行的判据描述里，不得出现在文件头 |
| 数据目录 | `data/app.db`、`data/files/`、`data/exports/` |
| 禁止项 | 任何 `pip install` / `npm install` 作为启动前置；任何 CDN 资源；任何把 `data/**` 内容作为 LLM 输入的路径 |
| **通过门槛** | **P0 必须 100% 通过**；P1 允许最多 2 项 `KNOWN-FAIL`，但必须在 `docs/ACCEPTANCE-RUN.md` 里写明原因与替代方案；出现任何 `BLOCKER` 级缺陷即整体不通过 |

**优先级**
- `P0`：核心链路（能装、能跑、能存、能出 PDF、能守住隐私）。缺一即不可交付。
- `P1`：完整体验（UI 细节、性能、降级提示、DOCX、批量）。
- `P2`：增强（可延后，不计入本次交付判定）。

**SKIP 与 PASS 的边界（v1.10 定版）**：用例**只能**因「缺少夹具/缺少前置资源」记 `SKIP(<reason>)`，且理由必须写成 `SKIP(no-fixture)` 这类机器可读形式；**夹具缺失不得记 PASS，也不得记 FAIL**——记 PASS 会让未验证的路径被当成已验证，记 FAIL 会把环境缺失算到实现头上。夹具位置：`server/tests/fixtures/sample.docx|sample.html|sample.pdf`（`.gitignore` 对该目录放行）；执行记录必须单列 SKIP 计数。

**一条 ID 一条条款（v1.28）**：**一个 AC ID 只对应一条条款，禁止复用；新增条款必须取该前缀下未被占用的号**。
判据（条款区重复 ID 必须为 0）：
```bash
python3 - <<'EOF'
import re,collections
L=open('docs/ACCEPTANCE.md',encoding='utf-8').read().split('\n')
tpl=next(i for i,l in enumerate(L) if l.startswith('## 14.'))
ids=[l.split('|')[1].strip() for i,l in enumerate(L) if i<tpl and re.match(r'^\|\s*AC-[A-Z]+-[0-9]+\s*\|',l)]
dup={k:v for k,v in collections.Counter(ids).items() if v>1}
print('条款',len(ids),'唯一',len(set(ids)),'重复',len(dup),dup)
EOF
```
**为什么这条是硬规则**：`AC-NAME-01`/`AC-PDF-11`/`AC-PDF-12` 曾被各写了两条（P0 与 P1/P2 各一），账本按下标覆盖状态，结果**后一条永远无法被单独判过或判红**——`SAN ZHANG` 全大写是用户亲自要求的特性，却一度在账本里是隐形的。撞号不是格式问题，是**让条款消失**。

**条目 ID 格式纪律（v1.27，M9）**：表格首列的条目 ID **一律不加粗、不加反引号**，全文只有一种写法。
原因：`tests/acceptance/make_index.py` 的解析正则不认加粗行，28 行 `| **AC-…** |` 被整批漏掉，账本分母 119 vs 真值 152，覆盖率把 76% 报成 93%——**取数脚本的盲区会直接伪造覆盖率**。今后新增条目照抄既有行的写法；脚本侧同时按 M9 用「两种数法相等」自校验。
本条已把历史遗留的 28 行统一为不加粗（原先加粗并非有意语义区分，只是分批编辑的残留）。

**证据约定**：每项通过后，在 `docs/ACCEPTANCE-RUN.md` 追加一行 `AC-xxx | PASS | <命令或证据路径> | <时间>`。无证据 = 未通过。

**一条命令跑全量自动化项**

```bash
cd resume-warehouse && .venv/bin/python -m pytest tests/acceptance -q --timeout=120
```

本文中标 `[auto]` 的条目必须对应一个 `tests/acceptance/test_ac_*.py` 里的测试函数，函数名 = 条目 ID 的小写加下划线（如 `test_ac_pdf_01`），保证可反查。

---

## 1. 环境与启动（ENV）

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-ENV-01 | P0 | `.venv/bin/python -c "import flask, pydantic, jinja2, reportlab, pdfplumber, pypdf, docx, markdown, httpx, bs4"` 退出码 0 | 命令 |
| AC-ENV-02 | P0 | `run.sh` 在**断网**下能完成「预检 → 起服务 → 打印 URL」；脚本内**不含** `pip install` / `npm install` / `curl` 安装动作 | 命令 `grep -nE "pip (install\|download)\|npm (i\|install)\|yarn add" run.sh scripts/*.py` 应无命中 + 断网实测 |
| AC-ENV-03 | P0 | `scripts/preflight.py` 输出 JSON，含 `python.version`、`deps[]`（每项 name/ok/version）、`fonts[]`（family/path/ok）、`engines`（reportlab/chrome/soffice 各自 ok+reason）、`ports`（8765 free / 顺延后的实际端口）、`data_dirs`（可写）；**不探测 11434**（Ollama 不在支持范围）；退出码 0=全绿，1=有降级，2=致命 | 命令 `.venv/bin/python scripts/preflight.py \| python -m json.tool` |
| AC-ENV-04 | P0 | `GET /api/v1/health` 返回 200 且 `data.status in {ok,degraded}`；`degraded` 时 `warnings[]` 非空且每条有 `code/message/hint` | auto `test_ac_env_04` |
| AC-ENV-05 | P1 | 首次启动自动建 `data/`、`data/files/`、`data/exports/`、`data/app.db`，并写入 `app_setting.schema_version` | auto `test_ac_env_05` |
| AC-ENV-06 | P0 | 8765 被占用时**顺延到下一个空闲端口**（8766→8799），把实际端口**原子**写入 `data/runtime/app_port`（**JSON 五字段** `port/host/url/pid/started_at`，格式冻结见 ARCHITECTURE §3.3）；启动横幅、日志、`GET /settings.app_port/app_url`、`data/runtime/app_port` 四者一致。**禁止静默失败、禁止让用户自己猜端口** | 手工：`python -m http.server 8765` 占位后 `./scripts/run.sh`，比对四处端口 |
| AC-ENV-07 | P0 | 服务只监听 `127.0.0.1`，不监听 `0.0.0.0` | 命令 `lsof -nP -iTCP:8765 -sTCP:LISTEN` 显示 `127.0.0.1:8765` |
| AC-ENV-08 | P1 | `.venv/bin/python -m compileall -q app` 通过；`ruff check app` 无 error 级问题 | 命令 |
| AC-ENV-10 | P0 | **`/health.build` 是「进程是否当前代码」的唯一判据**：`curl /health` 的 `data.build` == `git rev-parse --short HEAD`；改一行代码不重启 → `build` **不变**（用于识破旧进程）；`/env.build` == `/health.build` | auto `test_ac_env_10` + 手工 |
| AC-ENV-11 | P0 | **`app_port` 生命周期**：① 预置陈旧文件（`pid=99999` 不存在、`port=8899` 不可连）→ 启动后文件被覆盖为新值；② 预置 `pid` 存活且端口可连 → 启动流程不抢写、报「已有实例」；③ 优雅退出后文件被删除，但**若文件中 pid ≠ 自己则不删**；④ preflight 的 `lsof` 一致性检查在 pid/端口不符时产出 WARN（不阻断启动） | auto `test_ac_env_11` |
| AC-ENV-09 | P0 | **DSH Skill 与 run.sh 都从 `data/runtime/app_port` 取真实端口（`json.loads(...)["port"]`，禁止 `int(read())`）**：Skill 在端口顺延后仍能连上（不出现硬编码 8765）；文件不存在时 Skill 给出「先跑 ./scripts/run.sh」的明确提示而不是连接失败 | auto `test_ac_env_09`（顺延端口后跑 skill cli 探活） |

---

## 2. 数据本地性（LOC）

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-LOC-01 | P0 | 全流程（建包→导入→组装→导出）结束后，新增文件**只**出现在 `data/` 内；仓库其它路径无新文件（`git status --porcelain` 只显示预期源码变更） | 命令 + auto `test_ac_loc_01` |
| AC-LOC-02 | P0 | 代码中不出现 `data/` 之外的绝对路径写入；可用 `grep -rn "open(.*['\"]/" app/` 复查，命中必须能解释为只读（字体/引擎路径） | 命令 |
| AC-LOC-03 | P0 | `data/app.db` 单文件包含全部业务表（Package/Template/JD/Build/UserProfile…），无外部数据库连接串 | auto `test_ac_loc_03` |
| AC-LOC-04 | P1 | 导出的 PDF 落在 `data/exports/`，文件名符合命名模板，且 `build_artifact` 有对应记录（路径/大小/sha256/engine） | auto `test_ac_loc_04` |
| AC-LOC-05 | P0 | `.gitignore` 含 `data/`、`.venv/`、`.env`、`*.pyc`、`__pycache__/`；`git check-ignore -v data/app.db .env` 均命中 | 命令 |
| AC-LOC-06 | P1 | 提供「导出全部数据」能力：`GET /api/v1/settings/export-all` 产出单个 zip（db+files+exports），不含 `.env` | auto `test_ac_loc_06` |
| AC-LOC-07 | P2 | 提供「清空数据」需二次确认（输入 `DELETE`），且清空后仍能正常启动（自动重建 schema） | 手工 |

---

## 3. 隐私与出网（PRIV）

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-PRIV-01 | P0 | `data/imports/**`、`data/files/**` 的原始字节**永不出现在任何 HTTP 请求体中**。测试：把导入样张全文写入包，发起 LLM 生成，抓取 `llm_client` 的 request body，断言 body 中不含样张里独有的指纹串（如 `zhong_xudong` / 手机号 / 邮箱） | auto `test_ac_priv_01`（monkeypatch httpx transport 记录 body） |
| AC-PRIV-02 | P0 | 未显式选中的 Package / Variant **不出现在** preview 的 payload 里 | auto `test_ac_priv_02` |
| AC-PRIV-03 | P0 | `POST /api/v1/llm/complete` 缺 `preview_id` → 428 `LLM_CONSENT_REQUIRED`；过期（>600 s）→ 410 `LLM_CONSENT_EXPIRED`；payload 哈希与预览不符 **或** 同一 `preview_id` 二次使用 → 409 `LLM_CONSENT_MISMATCH` | auto `test_ac_priv_03` |
| AC-PRIV-04 | P0 | `POST /api/v1/llm/preview` 响应必须含 `preview_id`、`provider`、`model`、`endpoint_host`、`expires_at`、`payload`（逐字将发送体）、`payload_sha256`、`total_chars`、`est_tokens`、`fields[]`（每项 `path/label/kind/source/chars/est_tokens/included/redacted`）、`excluded{packages_total,packages_selected,variants_total,variants_selected,skipped[],note}`、`redactions[]`、`warnings[]`；缺任一字段即失败 | auto `test_ac_priv_04` |
| AC-PRIV-05 | P0 | 手机号/邮箱进入任何 LLM payload 前必被脱敏为 `[PHONE]` / `[EMAIL]`，且 `redactions[]` 记录 `field/value_preview/replacement`；`value_preview` 中间打码（`178****0929`） | auto `test_ac_priv_05` |
| AC-PRIV-06 | P0 | API Key 永不回显：`GET /api/v1/settings` 只返回 `key_set: true/false`；任何响应体、日志文件、`llm_call_log` 表都不含 key 明文子串（用测试 key `sk-test-DEADBEEF` 扫全库全日志） | auto `test_ac_priv_06` |
| AC-PRIV-07 | P0 | 日志中不出现 payload 正文：`data/logs/*.log` 对 preview 请求只记 `fields 名称 + token 数 + sha256 前 8 位` | auto `test_ac_priv_07` |
| AC-PRIV-08 | P1 | 页面响应头含 `Content-Security-Policy`，且 `default-src 'self'`，无 `unsafe-eval`；`connect-src` 仅含 `'self'` | auto `test_ac_priv_08` |
| AC-PRIV-09 | P1 | 出网审计：`llm_call_log` 每次调用都留痕：`created_at/provider/model/endpoint_host/field_names_json/payload_bytes/est_tokens/http_status/latency_ms/ok/error_code`（**只存字段名，不存正文**），可在设置页「出网审计」查看 | auto + 手工 |
| AC-PRIV-10 | P0 | **出网按方向分开验，判定口径是「是否携带用户数据」**：① 上行——`grep -rn "httpx\|requests\|urllib.request" app/` 的命中只允许出现在 `adapters/llm_client.py` 与 `adapters/fetch_client.py`；② 只有 `llm_client.py` 的请求可能带用户数据（测试里给 `llm_client` 装 recording transport，断言其 body 已脱敏）；③ 非 loopback 的 socket 连接若来自其他模块，测试必须失败。**不把 `fetch_client` 判为违规**（它只发公开 URL、请求体恒空，见 AC-FETCH-01） | auto `test_ac_priv_10` |
| AC-PRIV-11 | P0 | **脱敏面收敛为「姓名 + 联系方式 + 照片」，学校名放行**（用户 m00265 最终口径）：构造含真实姓名/学校/电话/邮箱的 payload → `payload_json` 中**不得**出现姓名（中英，含 bullet 里的自称）、电话（含 `+86`/空格/短横线变体）、邮箱的**任何**明文子串，对应位置出现 `[NAME]`/`[PHONE]`/`[EMAIL]`；**但 `school_zh`/`school_en` 必须以真实值出现在 payload 中**（断言 `real_school in payload_json` 为真，且**不得**出现 `[SCHOOL]` 占位符，`grep -c "\[SCHOOL\]"` 在 payload 中为 0）；照片字节不得出现（无 base64）；`fields[]` 中命中项 `redacted=true`；`excluded.skipped[]` 含 `kind="profile_identity"` 且 `reason` 写明「姓名/联系方式/照片」 | auto `test_ac_priv_11` |
| AC-PRIV-13 | P0 | **`设置API密钥.command` 不回显 key 任何字符片段**：`grep -c '末尾四位' 设置API密钥.command` = **0**；`grep -Ec 'sk-[A-Za-z0-9]{4,}' 设置API密钥.command` = **0**；`grep -c '指纹' 设置API密钥.command` **≥1**（允许 SHA-256 前 8 位作身份锚点）。功能面：写入后 `.env` 权限 **600**、其余行原样保留、非 `sk-` 前缀与过短 key 均拒绝且 md5 不变、输出中不出现 key 任一字符 | auto `test_ac_priv_13` + 手工双击 |
| AC-PRIV-12 | P0 | **服务端自检兜底且名单不含学校名**：`llm_payload.build()` 末尾调用 `assert_no_identity(payload, profile)`；① 人为注入一处真实姓名 → 抛异常并返回 500 `INTERNAL`，**且 httpx 调用计数 = 0**（宁可失败也不发出去）；② 对照组：payload 只含真实学校名（姓名/电话/邮箱均已脱敏）→ **不触发**自检、正常发送（防止把学校名误列进黑名单） | auto `test_ac_priv_12` |

---

## 4. 命名模板（NAME）

**默认模板**：`{position}-{name}-{school}`，产物示例 `数据分析实习生-张三-示例大学.pdf`。
**变量集**：`{company} {position} {date} {name} {school} {version} {lang}`（`{date}` 支持 `{date:%Y-%m-%d}` 格式子句）。
**取数来源**：`{name}`=`user_profile.name_zh`（`lang=en`→`name_en`）、`{school}`=`school_zh/school_en`、`{position}`=`build.position`→`jd.title`、`{company}`=`build.company`→`company_profile.company_name`。
**规则、净化顺序与错误码的唯一定义在 `docs/API-CONTRACT.md` §9**；本节只做验收断言。

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-NAME-01 | P0 | `POST /api/v1/naming/validate` 是纯函数：**任何输入都返回 200**，`data` 含 `valid/resolved/filename/variables[]/warnings[]/errors[]`；不写库、不抛 5xx、不落文件 | auto `test_ac_name_01` |
| AC-NAME-02 | P0 | 下表逐条通过。夹具：`profile{name_zh:张三, school_zh:示例大学}`、`build{position:数据分析实习生, company:字节跳动, lang:zh, version:v1}`、导出时刻 `2026-10-23` | auto `test_ac_name_02`（参数化） |

| # | pattern | 期望（`data.valid` / `data.filename` / `data.errors[0].code` / `warnings`） |
|---|---|---|
| 1 | `{position}-{name}-{school}` | `true` / `数据分析实习生-张三-示例大学.pdf` / — / `[]` |
| 2 | `{company}_{position}_{name}_{date:%Y-%m-%d}` | `true` / `字节跳动_数据分析实习生_张三_2026-10-23.pdf` / — / `[]` |
| 3 | `{name}_{version}` | `true` / `张三_v1.pdf` / — / `[]` |
| 4 | `{date}`（默认格式） | `true` / `20261023.pdf` / — / `[]` |
| 5 | `{lang}/{name}` | `true` / `zh-张三.pdf` / — / 含 `NAMING_SANITIZED`（`/`→`-`） |
| 6 | `{position}-{name}` 且 `name_zh` 为空 | `false` / `null` / `NAMING_MISSING_VAR`（`missing_vars=["name"]`） |
| 7 | `{position}-{name}-{school`（未闭合） | `false` / `null` / `NAMING_SYNTAX` |
| 8 | `{salary}`（未知变量） | `false` / `null` / `NAMING_UNKNOWN_VAR`（`unknown_vars=["salary"]`） |
| 9 | `{position}` 且 `build.position` 空且 JD 无 title | `false` / `null` / `NAMING_MISSING_VAR`（`missing_vars=["position"]`） |
| 10 | 模板字面量 201 字符 | `false` / `null` / `NAMING_TOO_LONG`（`{len:201,max:200}`） |
| 11 | 纯字面量 `中文简历`（无变量） | `true` / `中文简历.pdf` / — / 含 `NO_VARIABLE` |
| 12 | `../../etc/{name}` | `true` / 结果**不含** `..`、不含 `/`、不以 `.` 开头 / — / 含 `NAMING_SANITIZED` |
| 13 | `{name}` 含 emoji `张三🚀` | `true` / `张三.pdf` / — / 含 `EMOJI_STRIPPED` |
| 14 | `{name}` 含 `: * ? " < > \|` | `true` / 全部替换为 `-` 并折叠 / — / 含 `NAMING_SANITIZED` |
| 15 | ` {position} - {name} `（首尾空格 + 变量间空格） | `true` / `数据分析实习生-张三.pdf`（空格→`-`、连续 `-` 折叠、首尾裁掉）/ — / `[]` |
| 16 | `CON`（Windows 保留名） | `true` / `_CON.pdf` / — / 含 `NAMING_SANITIZED` |
| 17 | `{name}` 重复至 >120 字符（模板字面量仍 <200） | `true` / 截断到 120 字符 / — / 含 `NAMING_TRUNCATED` |

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-NAME-03 | P0 | `PATCH /api/v1/builds/{id}` 写入非法 `naming_pattern` → 422 + `NAMING_*` 码且**不落库**；若库中已有不可解析的 pattern（历史数据），`POST /builds/{id}/export` 也返回同款 422 且**不产生任何文件**（`data/exports/` 前后文件数不变） | auto `test_ac_name_03` |
| AC-NAME-04 | P0 | 缺 `name_zh`/`school_zh` 时（pattern 合法但值缺失）导出返回 422 `NAMING_MISSING_VAR`，`hint` 指向「去设置填个人信息」；**永不**产出 `undefined.pdf` / `-示例大学.pdf` / `数据分析实习生--示例大学.pdf` / `..pdf`（正则拒收任何以 `-` 开头或含 `--` 的产物名） | auto `test_ac_name_04` |
| AC-NAME-05 | P1 | 同名已存在：`overwrite=false` → 追加 `-2`/`-3`（`resolved` 不变，artifact 记 `collision_suffix`）；`overwrite=true` → 覆盖且新增 artifact 版本 | auto `test_ac_name_05` |
| AC-NAME-06 | P1 | 不传 `pattern` 时用 `app_setting.naming_template`，初始值 `{position}-{name}-{school}`；`PUT /api/v1/settings` 可改，改后立即生效 | auto `test_ac_name_06` |
| AC-NAME-07 | P1 | 前端与模板无硬编码姓名/学校：`grep -rn "张三\|示例大学" app/` 无命中（示例数据必须在 `data/`） | 命令 |
| AC-NAME-08 | P1 | 落盘路径安全：任意 `pattern` 下 `os.path.realpath(产物路径)` 仍以 `data/exports/` 开头；`{name}=../../x` 不会逃逸 | auto `test_ac_name_08` |

---

## 5. 导入与解析（IMPORT）

**回归素材（本机、含隐私，不得入库 Git）**：`data/imports/sample_zh.pdf`（中文单页，1791 字符）、`data/imports/sample_en.pdf`（英文双页，含照片，`(cid:127)` × 16）。

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-IMPORT-01 | P0 | 导入中文样张：`POST /api/v1/imports`（multipart）→ **201**，响应体**内联** `draft`（无需轮询、无 `202`/`queued` 中间态）；`draft.stats.pages=1`、`stats.chars` 在 1600–2000；`import_id` 与 **`job_id` 均非空**且同源（`GET /jobs/{job_id}` → `status="succeeded"`、`result.import_id == import_id`），客户端**不轮询**；`GET /imports/{id}`（可选历史查询）返回同一份 `draft`（`blocks` 数量与内容一致）；`llm_call_log` 无新增行 | auto `test_ac_import_01` |
| AC-IMPORT-02 | P0 | 导入英文样张：`stats.pages=2`、`stats.cid_missing=16`；`warnings[]` 含 `code=CID_GLYPH_MISSING` 且 `count=16`；**draft 正文不含 `(cid:127)` 字面量**；对应 16 处被识别为列表项（`block_type=list` 或以 `-\|•\|·` 开头的 bullet） | auto `test_ac_import_02` |
| AC-IMPORT-03 | P0 | **导入只产出候选、绝不自动生效**：英文样张 → `warnings[]` 含 `PHOTO_DETECTED`（`severity="warn"`，`details` 含 `attachment_id`/`sha256`/`width`/`height`）；`extracted_photo.applied === false`；**`GET /profile` 的 `photo_path` 仍为空**（上传前后同值）；只有显式 `PUT /profile/photo` 后 `photo_path` 才非空且 `photo_source="imported"`。反向判据：导入响应后立即查 `user_profile.photo_source` 必须仍是 `none` | auto `test_ac_import_03` + 手工核对导出页缩略图 |
| AC-IMPORT-04 | P1 | draft 的每个 block 有 `block_type`、`confidence`∈[0,1]、`slots[]`；低置信 block（<0.6）在 `warnings` 里汇总为 `LOW_CONFIDENCE_BLOCKS` 且带 block id 列表 | auto |
| AC-IMPORT-05 | P0 | `POST /api/v1/imports/{id}/commit` 后生成 `template` + `template_block` + `slot`；再次 commit 同一 import → 409 `CONFLICT`（`details.reason="IMPORT_ALREADY_COMMITTED"`） | auto |
| AC-IMPORT-06 | P1 | 支持 `pdf/docx/md/txt/html` 五种输入；`docx` 走 python-docx 解析段落与标题层级；`md` 走 markdown→HTML→结构；`html` 走 bs4 并剥离 script/style | auto（各一份最小夹具） |
| AC-IMPORT-07 | P0 | 解析全程**不联网**：`egress_guard` 生效时导入流程仍成功 | auto（与 AC-PRIV-10 共用守卫） |
| AC-IMPORT-08 | P1 | 上传大小上限 20MB；超限 413 `PAYLOAD_TOO_LARGE`；扩展名/magic 不符 415 `UNSUPPORTED_MEDIA_TYPE`；损坏 PDF 422 `IMPORT_UNSUPPORTED`（扫描件无文本层 → 422 `IMPORT_NO_TEXT_LAYER`），且不落库半成品 | auto |
| AC-IMPORT-09 | P1 | 草稿可编辑：`PUT /api/v1/imports/{id}/draft` 修改 block 类型/heading/slot 绑定并持久化，刷新页面不丢 | auto |
| AC-IMPORT-11 | P0 | **`blocks` 唯一真值源、`sections[]` 只派生**：对英文样张 draft，逐条断言 `sections[].heading == blocks 中同 kind 的 section block.heading`；`sections[].entry_count` 等于该 section 下 entry block 数；`PUT /imports/{id}/draft` 只改 `blocks`（改一个 heading）后重新 `GET`，`sections[]` 已随之更新（客户端提交的 `sections` 被服务端重算覆盖，不报错） | auto `test_ac_import_11` |
| AC-IMPORT-12 | P0 | **`needs_llm_fallback` 不打 LLM**：构造低结构文本（纯 bullet 无标题）触发 `needs_llm_fallback=true` → 响应仍 201 且内联 draft；`llm_call_log` **无新增行**、无 `LlmPreview` 产生；转 LLM 必须由用户在校对页显式点击后另发请求 | auto `test_ac_import_12`（mock `llm_client` 计数为 0） |
| AC-IMPORT-14 | P0 | **照片候选不变量**：对裸 `/FlateDecode` raw 像素夹具（`doc.images[0].data` 为 120000 字节 raw RGB，PIL 无法识别）→ 响应 `201`，`warnings[]` 含 **`PHOTO_DECODE_FAILED`**（`severity="warn"`，`details.reason` 非空）；`extracted_photo.available === false` **且无 `attachment_id`**；**断言不存在「`available=true` 且 `attachment_id` 为空」的组合**（这类候选在 UI 上点不动）；`GET /profile` 的 `photo_path` 不变 | auto `test_ac_import_14` |
| AC-IMPORT-13 | P1 | **夹具缺失记 SKIP，不得记 PASS**：`server/tests/fixtures/sample.docx\|sample.html\|sample.pdf` 任一缺失时，对应用例结果必须是 `SKIP(no-fixture)`（不是 PASS、不是 FAIL），并计入执行记录的 SKIP 列 | 手工核对执行记录 + `ls server/tests/fixtures/` |
| AC-IMPORT-15 | P0 | **导入派生包幂等**（I12）：`POST /imports/{id}/commit` 带 `also_create_packages=true`，对同一 `import_id` **连续执行两次**；第二次后 `SELECT count(*) FROM package WHERE source_import_job_id=?` 必须与第一次相同（不增加），且第二次 201 的 `created_packages[]` 只含**已存在被复用**的 id（或空数组）。反向断言：`source_entry_temp_id` 为 NULL 的派生包不得存在（否则幂等键失效） | auto `test_ac_import_15` |
| AC-IMPORT-16 | P0 | **撤销连带**（I13）：`DELETE /imports/{id}` → `SELECT count(*) FROM package WHERE source_import_job_id=? AND deleted_at IS NULL` 必须为 **0**；`POST /imports/{id}/restore` → 全部回到非 NULL（等于删除前的包数）。反向断言：**手工创建**的包（`source_import_job_id IS NULL`）不受影响 | auto `test_ac_import_16` |
| AC-PKG-14 | P1 | **`verified` 口径可区分**（原文即事实）：导入派生包中，`variant.source ∈ {imported_verbatim, llm_rewrite}`；前者 `verified=1`、后者 `verified=0`；导出时**默认只勾选 `verified=1`**，`verified=0` 的 variant UI 必须显示「AI 改写·待确认」字样。反向断言：`verified=0` 的 variant 默认**不在** `BuildSelection` 里 | auto `test_ac_pkg_14` |
| AC-IMPORT-17 | P0 | **删导入不删模板**（v1.26，反隐式级联）：对「已 commit 且产出模板」的导入执行 `DELETE /imports/{id}` → 200 且 `template_retained.kept == true`、`template_retained.template_id` 非空；随后 `GET /templates/{该 id}` 必须 **200**（模板仍在）。反向断言：`template.deleted_at` 仍为 NULL，且**不得**因删导入而出现任何模板删除。若模板已被单独删除 → `kept == false` 且 `note` 含「已被删除」 | auto `test_ac_import_17` |
| AC-IMPORT-18 | P0 | **溯源不断链**（I14 + R-a/R-c）：① 对已 commit 的导入，`import_job.result_template_id` 非空且**永不被清空**（软删、恢复、清理脚本跑完后仍非空）；② 执行 R-c 的 SQL（`import_job.deleted_at IS NOT NULL AND template.deleted_at IS NULL`）结果集必须为 **空**；③ 清理脚本对命中行必须跳过并告警，不得归档。反向断言：把某模板软删后，其来源行**才**允许被归档 | auto `test_ac_import_18` |
| AC-IMPORT-19 | P0 | **commit 三类内容不得丢**（I15，v1.28 实测缺口驱动）：对含教育 `facts`（含 GPA/四六级）与技能整句的草稿执行 commit 后，① `template_block` 中对应块的 `static_text` **非空且包含草稿里的关键数字**（`3.56`、`562`、`508` 至少各命中一次）；② `user_profile` 的 `degree`/`major`/`grad_year`/`city` 按草稿回填（非 NULL）；③ `skills_json` 非空且 `line` 与草稿逐字相等。**反向断言**：草稿里没有的字段必须为 NULL，不得出现默认值；导出后 `SKILLS_EMPTY` 不得出现 | auto `test_ac_import_19` |
| AC-IMPORT-20 | P0 | **回填可回溯**（`profile_fields_source`）：commit 后响应含 `profile_filled[]` 与 `profile_fields_source`；DB 里被回填字段的 source 值为 `import:<import_job_id>` 且该 id 存在；用户在个人信息页改值后 source 变 `manual`；**再次 commit 不得覆盖 manual 值**（除 `overwrite_profile=true`） | auto `test_ac_import_20` |
| AC-IMPORT-21 | P0 | **`also_create_packages` 三分支各有出口（§5.1 / T-7）**：用同一份 fixture 草稿（含 education 条目、映射不出 kind 的条目、只有标题无正文的条目）执行 `commit{also_create_packages:true}` → ① education **不建包且不告警**；② 映射不出 → 不建包 + `warnings[PACKAGE_SKIPPED{reason:"no_kind_mapping", entry_temp_id}]`；③ 空正文 → 不建包 + `warnings[PACKAGE_SKIPPED{reason:"empty_entry", entry_temp_id}]`；④ `created_packages[]` 长度 == 实际新建包数（不虚报）。**反向断言**：任何被跳过的 entry **不得**出现在 `created_packages[]`；`reason` 只能是这两个值（不得新增第三值）。**顺序断言**：把「先判正文」的实现换上去跑同一 fixture → 包数**必须不变**（若变则该实现顺序违规） | auto `test_ac_import_21` |
| AC-BUILD-16 | P0 | **归档 ≠ 删除（DATA-MODEL I24/I25，§8 builds 表）**：① `PATCH /builds/{id} {"archived":true}` → `archived_at` 非空；② `GET /builds` **默认不含**该 build，`?include_archived=1` **含**；③ 归档后 `GET /builds/{id}?include=selections,artifacts` 的 selections/artifacts **条数与归档前逐条相等**（产物不被牵连）；④ `DELETE /builds/{id}` **不带 `hard`** → 只归档，`SELECT count(*) FROM resume_build` **不变**；⑤ `DELETE ?hard=1` 缺 `confirm` 或 `confirm != id` → 422 `CONFIRM_MISMATCH`；带正确 confirm → 行消失且 `data/exports/_trash/` 出现该 build 的 JSON 快照。**反向断言**：任何路径都不得让 `build_artifact.build_id` 指向不存在的行（`SELECT count(*) FROM build_artifact WHERE build_id NOT IN (SELECT id FROM resume_build)` 恒为 0） | auto `test_ac_build_16` |
| AC-CONFLICT-01 | P0 | **中英来源冲突**（`SOURCE_CONFLICT`）：同一用户存在 zh/en 两份来源且某字段值不等（GPA `3.56/4` vs `3.57/4.0`；到岗 `2027年1月下旬` vs `Early July 2026`）时，① zh 版 PDF 抽取文本含中文值且**不含**英文值，en 版反之；② 响应 `warnings[]` 含 `SOURCE_CONFLICT{field,zh_value,en_value}`，**字段数与冲突字段数相等**；③ 导出页有可见提示行。**反向断言**：一侧为空时**不得**报 `SOURCE_CONFLICT`（应记 `PROFILE_FIELD_MISSING`）；四个值不得被合并成单一数值 | auto `test_ac_conflict_01` |
| AC-CONFLICT-02 | P0 | **已决议形态与可逆性（§8.4.1 / §14.1）**：前置用真库既有冲突（GPA `3.56/4` vs `3.57/4.0`、到岗 `2027年1月下旬` vs `Early July 2026`）。① 未决议：导出 `warnings[]` 中该 field 的 `SOURCE_CONFLICT.severity === "warn"`；② 写 `extra_json.conflict_resolution.fields.gpa="zh"` 后重导 → 同 field 的 `severity === "info"`、`details.resolved === "zh"`、`details.decided_at` 为 ISO 串、message 含「中文版」；③ **渲染值不变**：前后两次导出的英文 PDF 都含 `GPA 3.56/4`，且 `3.57` 出现 **0** 次；④ **反向恢复**：删除 `fields.gpa` 后重导 → `severity` 回到 `"warn"`（把这条单独断言，防「决议写死永不恢复」）；⑤ `decided_by !== "user"` 的记录不得降级为 info（自动流程不许自己拍板）。量法：`POST /builds/{id}/export` 返回体的 `warnings[]` 逐条断言 + pdfplumber 抽文本计数，**不许读代码常量** | auto `test_ac_conflict_02` |
| AC-PROF-01 | P0 | **教育段补充行 `GET`/`PUT /profile/education-facts`（§3，实现即契约）**：① `GET` 返回 `{template_id,template_name,block_id,lines[],updated_at}`，`lines` 与 `template_block.static_text` 按行切分**逐条相等**（去空行、trim）；② `PUT {"lines":["专业成绩：GPA 3.56/4  86.53/100  CET4：562  CET6:508"]}` → 200 且回读 `static_text` **逐字相等**、`saved===true`、`snapshot.path` 落在 `data/runtime/app.db.pre_edu_*` 且 `snapshot.md5` 与文件实算一致；③ `PUT {"lines":[]}` → 200、`static_text` 为 NULL、`GET` 回 `lines:[]`（**合法**）；④ **不改半行**：`PUT` 含 13 项 → 422 `VALIDATION_ERROR` `details.fields[0].rule=="too_long"`，且 `static_text` 与请求前**逐字相同**；⑤ 空库（临时 `DATA_DIR`）→ `GET` 200 全 `null`/`[]`、`PUT` 409 `NO_DEFAULT_TEMPLATE`；⑥ 默认模板无 education 条目 → 422 `TEMPLATE_INVALID` 且**不自动建块**（块数前后相等，建块即 FAIL）。**真源断言**：`PRAGMA table_info(user_profile)` 中不得出现 `gpa`/`score`/`courses`/`education_facts` 列 | auto `test_ac_prof_01` |
| AC-PROF-02 | P0 | **到岗时间单一真源（§8.6.1 / DATA-MODEL）**：① 只改 `available_note=2027年2月上旬`（不动 `available_note_en`、不动 `available_date`）→ 中文 PDF 含「2027年2月上旬」，英文 PDF 含该中文原文（回退生效，不省略该行、无 `PROFILE_FIELD_MISSING`）；② 再设 `extra.available_note_en="Early February 2027"` → 英文 PDF 含 `Early February 2027`、中文 PDF 仍含「2027年2月上旬」；③ **反向断言**：把 `available_date` 改成 `2028-05` 而 `available_note` 不动 → 两份 PDF 均**不含** `2028`（证明 `available_date` 不参与渲染）；④ 两份 PDF 的页眉前 4 行都不含学位词（与 AC-PDF-16 联判） | auto `test_ac_prof_02` |
| AC-NAME-09 | P1 | **英文名全大写且不互推**：`name_en` 按抬头原样入库，英文版 PDF 抬头抽取文本匹配 `^[A-Z][A-Z ]+$`（例 `SAN ZHANG`）；中文版不出现 `name_en`；`name_en` 为空时英文版回退 `name_zh` 并记 `PROFILE_FIELD_MISSING`。**反向断言**：任意路径不得由 `name_zh` 生成拼音、不得把 `name_en` 转 Title Case | auto `test_ac_name_01` |
| AC-EN-01 | P0 | **en 版骨架区零 CJK**（v1.29）：用 `lang=en` 导出后，PDF 抽取文本中 **chrome 区域**（section 标题、字段标签、日期、姓名、校名、学历、专业）CJK 字符计数 = **0**。判定脚本按 `API-CONTRACT §8.5.1` 词表逐项断言（`Education`/`Available:`/`Sep 2024 – Jun 2028`/`SAN ZHANG` 等必须命中，`教育背景`/`到岗`/`本科` 必须 0 命中）。**反向断言**：`degree_en` 为 NULL 时 en 版**省略该行**且 `warnings` 含 `PROFILE_FIELD_MISSING`，不得写「本科」 | auto `test_ac_en_01` |
| AC-EN-02 | P0 | **en 变体的两种情形都不许空**：① 存在 `variant.lang='en'` ⇒ 正文 bullet 用英文（CJK 计数 ≤ 阈值）；② **一条 en 变体都没有** ⇒ 条目**仍渲染中文原文**（**不得出现空段/空标题**），且 `warnings[]` 必有 `LANG_FALLBACK{entry_count,bullet_count,sample[]}`、导出页有「以下条目沿用中文原文」提示。反向断言：`lang=zh` 导出**不得**出现 `LANG_FALLBACK` | auto `test_ac_en_02` |
| AC-EN-03 | P1 | **语言不影响结构**：同一份 `BuildSelection` 分别以 `lang=zh`、`lang=en` 导出，PDF 的 **section 数相等、每 section 条目数相等**（语言只改文字，不改版式与取舍）；`page_count` 允许不同但 `density` 与 `layout` 字段必须一致 | auto `test_ac_en_03` |
| AC-PDF-16 | P0 | **页眉白名单**（CMP-40，v1.33）：导出 PDF 后取**前 4 行**文本，`grep -Ec '本科\|硕士\|博士\|大专\|B\.M\.\|B\.S\.\|M\.S\.\|M\.Sc\.\|Ph\.D\.\|Bachelor\|Master'` 必须为 **0**；且 `ir.header` 不得含 `education_line` 键（结构断言）。正向断言：页眉必须含姓名与至少一项联系方式；`available_note` 存在时按 `lang` 标签渲染 | auto `test_ac_pdf_16` |
| AC-PDF-17 | P0 | **教育段日期原文**（CMP-39）：`entry.date_range='2024.9-2028.6'` 时 PDF 教育段抽取文本必须**同时含 `2024` 与 `2028`**；**反向断言**：日期列不得只渲染 `grad_year`（只含单个年份即 FAIL）；`date_range` 为空时日期列留空 + `PROFILE_FIELD_MISSING{fields:["date_range"]}`，不得用 `grad_year` 兜底 | auto `test_ac_pdf_17` |
| AC-EN-04 | P0 | **英文变体生成**（CMP-37）：`POST /packages/{id}/variants/generate` 带 `lang:"en"` + preview_id → 202；完成后 `result_json.variants[]` 全为英文（CJK 计数 ≤ 阈值），落库后 `lang='en'`、`verified=0`、`llm_generated=1`；**上云合规**：preview 的 `fields[]` 不含姓名/电话/邮箱，照片字节不出本机。反向断言：未确认的 `verified=0` 变体**不得**被导出自动选用 | auto `test_ac_en_04` |
| AC-BUILD-15 | P1 | **`PUT` 是 `PATCH` 的真别名**（v1.33）：同一 payload 分别以 `PUT`、`PATCH` 发到 `/builds/{id}` → 响应体与 DB 结果逐字段相等；`GET /builds/{id}/selections` 与 `PUT /builds/{id}/selections` 对称（无选择时返回 `[]` 而非 404） | auto `test_ac_build_15` |
| AC-IMPORT-10 | P2 | 导入历史可删除（删 draft，不删已 commit 的 template） | 手工 |

---

## 6. 导出与中文（PDF）

**最终路径（已实测确认）**
1. **首选 `reportlab`**：`TTFont("STSongti-SC-Regular", "/System/Library/Fonts/Supplemental/Songti.ttc", subfontIndex=6)` + `subfontIndex=1`→`STSongti-SC-Bold`。实测提取文本与源文本**逐字相等**。
2. **回退 `Chrome headless`**（`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --headless=new --disable-gpu --no-sandbox --user-data-dir=<tmp> --no-pdf-header-footer --print-to-pdf=...`），字体栈锁定 `"STHeiti", "Arial Unicode MS"`（**禁用** Songti SC / Hiragino：ToUnicode 会把汉字映射成康熙部首）。
3. **永久排除**：weasyprint（`libpango-1.0-0` 缺失）、`soffice` 转 PDF（`DeploymentException` / `Signal 6`，无产物）、`UnicodeCIDFont("STSong-Light")`（`·` 丢字）。
4. **兜底**：DOCX（python-docx）+ Markdown 纯文本（ATS 友好）。

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-PDF-01 | P0 | `scripts/preflight.py` 的 `engines.reportlab.ok=true` 且 `engines.reportlab.fonts` 含 `STSongti-SC-Regular`、`STSongti-SC-Bold` | 命令 |
| AC-PDF-02 | P0 | 导出一份包含全字符集的测试简历，用 pdfplumber 提取文本，**必须逐字包含**：`·`（U+00B7）、`「」`、`《》`、`①②③`、`％`、`０-９`（全角）、`±÷≠≤≥`、`①`、以及罕字 `龘鑫彧甯喆珺屾赟`。断言 `src in extracted` 对每个字符成立 | auto `test_ac_pdf_02` |
| AC-PDF-03 | P0 | 中文正文无缺字：`extracted.count("\ufffd") == 0` 且不含 `\x00`；`"高级工程师" in extracted` 为真（防康熙部首替换） | auto `test_ac_pdf_03` |
| AC-PDF-04 | P0 | 中英混排不掉字：`TypeScript · React`、`GPA 3.8/4.0`、`2024.03–2024.09`（全角与半角连字符）均原样可提取 | auto |
| AC-PDF-05 | P0 | 渲染后 `verify_text=true` 的自动校验开启：导出流程对每页做 extract→normalize（去空白）→与源文本比对，差异率 >2% 时 `build_artifact.text_verified=0` 且 `warnings_json` 含 `TEXT_LAYER_MISMATCH`（通过为 `text_verified=1`，未校验为 `NULL`）（**不阻断导出**，但必须显式告警） | auto `test_ac_pdf_05` |
| AC-PDF-06 | P0 | 回退链可验证：强制 `engine=chrome` 也能产出 PDF 且 `test_ac_pdf_02/03` 同样通过；强制 `engine=reportlab` 失败时（注入异常）自动回退 chrome 并在响应 `engine_used` 中如实标注 | auto（monkeypatch 注入失败） |
| AC-PDF-07 | P1 | `engine=auto` 时优先 reportlab；两者都失败 → 返回 500 `RENDER_FAILED`（`details.engine` 标明试过的引擎），`hint` 建议改 DOCX，且**不留半成品文件** | auto |
| AC-PDF-08 | P0 | emoji（🚀✅🎯）在导出前被剥离/替换，`warnings` 含 `EMOJI_STRIPPED`，产物中不出现 `\x00` 豆腐 | auto |
| AC-PDF-09 | P1 | 页面尺寸 A4（595.28×841.89pt ±2），页边距与模板 `style_json` 一致；`page_count ≤ build.page_limit`，超限时 `warnings` 含 `PAGE_OVERFLOW`（含 `suggestion`）且 `est_pages` 保留小数 | auto |
| AC-PDF-10 | P1 | DOCX 导出可用：python-docx 打开无异常，段落数 > 10，中文可读 | auto |
| AC-PDF-11 | P0 | **单页降档必须留痕且不越下限（D-38）**：`POST /builds/{id}/export` 带 `density:"original"`（默认）→ 响应回显 `layout{available_height_pt:817.65±0.5, text_width_pt:564.9±0.5, body_pt, leading}`；若 10.5pt 装不下，`warnings` **必须**含 `PAGE_FIT_DOWNGRADED` 且 `details{from_pt:10.5, to_pt:10.0, reason:"single_page_fit", used_height_pt, available_height_pt}` 齐全；**正文字号不得低于 9.5pt**（PDF 字体大小分布 min ≥9.5±0.1，`original` 档正常应为 10.0）；`page_count == 1`；**反向断言**：未降档时不得出现该 warning | auto |
| AC-PDF-12 | P0 | **两页兜底不静默**：构造超量夹具使三档均装不下 → `page_count == 2` 且 `warnings` 含 `PAGE_OVERFLOW_TWO_PAGES`，`details{pages:2, overflow_pt, suggestion}` 齐全；**反向断言**：此时字号仍 ≥9.5pt（不得为塞两页继续缩字） | auto |
| AC-PDF-13 | P1 | **照片不参与降档**：带照片 + 触发降档的夹具 → 照片渲染尺寸仍为 `89.28±0.5 pt`、距顶 `3.82±1 pt`、距右缘 `9.13±1 pt`；正文最小字号 ≥9.5pt；两者同时成立才算通过（防「顺手把照片也缩小」） | auto |
| AC-PDF-14 | P1 | **`facts` 整段渲染**：教育段 `facts[]` 每条在 PDF 中以整段出现，**行首无 `·`/`•`/`-`**（按行首字符断言），悬挂缩进与 bullet 文本左边界差 ≤1pt；`facts` 为空 → 渲染 `N/A` 且**无空行**（页内连续空行数 ≤1） | auto |
| AC-PDF-15 | P0 | **`density` 默认 `original` 且反作弊下限不可越（ADR-21 / ADR-22）**：① 不传 `density` → 响应 `density=="original"`、`layout.available_height_pt≈817.65`、`layout.text_width_pt≈564.9`；② 传 `"relaxed"` → 可用高度 ≈751.5、版心 ≈510.5；③ 传 `"tight"` 之类非法值 → **422 `VALIDATION_ERROR`**（不得静默回落）；④ **反作弊（v1.33 改定）**：任何档位下 PDF **正文字号中位 ≥10.5 pt**、**行距比 ∈ [1.10,1.25]**、页边距 ≥ `original`（8.3/14.8 pt）——越线即判失败，即使 `page_count==1` | auto |
| AC-PDF-18 | P0 | **首档 11 pt + 条目头单行（ADR-22）**：① 未降档的 `original` 导出，正文字号中位 **=== 11.0 pt**（±0.2）且行距比 ≈1.15；仅当 `PAGE_FIT_DOWNGRADED` 出现时才允许 10.5/10.0；**9.5 pt 出现必须伴随 `PAGE_FIT_DOWNGRADED` + 三档均失败的原因码**，单独出现即 FAIL。② 条目头**单行**：逐条目量渲染纵向跨度 ≤ 1.6×行高，超行条目数必须 **0**；日期列宽度落在 **12%–22% 版心**（67.8–124.3 pt）。③ **反向断言（防「靠裁内容换字号」）**：导出 PDF 的条目数 == `build.selections` 的 `variant_ids` 总数（逐条比对，不是只比总数），且正文行数 ≤ 原件的 1.25 倍（原件 33 行 ⇒ 上限 41 行）。三组必须同时成立：**内容不减 + 字号达标 + 单页** | auto |

### 6.1 照片（PHOTO）

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-PHOTO-01 | P0 | **有照片时渲染在右上角，且边长与标题区等高**：A4 595.5×842.2 pt 下，照片边长 == 标题区实测高度（11pt/1.15 时 52.0 pt，±1.5）、上沿 == 上边距 8.3 pt（±1.5）、右沿 == 右边距 15.62 pt（±1.5）；**反向断言**：`size ≈ 89.28` 且 `top ≈ 3.82`（旧口径）判 FAIL——那是原始样张的值，不是导出件应有的值；与姓名区不重叠；`include_photo=true` 时 PDF 内恰 1 个图像对象，中英两版一致 | auto `test_ac_photo_01`（先用 `_header_story` 量标题高度再比 bbox） |
| AC-PHOTO-02 | P0 | **无照片时布局不得错位**：同一模板在 `include_photo=false` 或 `photo_source=none` 下导出，姓名块扩到整行宽度、无空白方块占位、节距不变，`page_count` 与有照片时相同；pdfplumber 页面 `images == []` 且无 `\ufffd`/`\x00` | auto `test_ac_photo_02` |
| AC-PHOTO-03 | P0 | **照片字节不得出现在任何 LLM payload**：对所有 purpose 取 preview → `payload_json` 中无 base64 图像特征（`data:image/`、超长 base64 串、图片 sha256），`fields[]` 无任何 `photo` 项；配套：`llm-egress.jsonl` 中不出现图片哈希 | auto `test_ac_photo_03` |
| AC-PHOTO-05 | P0 | **删照片可撤销**：`DELETE /api/v1/profile/photo` → **200**（不是 204）+ `data.previous_photo_path` 非空且等于删除前的 `photo_path`；`data.cleared === true`；随后 `GET /profile` 的 `photo_path` 为空、`photo_source="none"`；再次 `DELETE` → 200 且 `previous_photo_path === null`（幂等）；照片文件**仍在** `data/profile/` 下（只清引用不删文件） | auto `test_ac_photo_05` |
| AC-PHOTO-04 | P0 | 导出页「包含照片」开关**默认开启**（`app_setting.photo_in_export=true`），单次导出可覆盖（`include_photo=false`）；无照片时按钮给「继续导出（无照片）」的可继续路径，**不得阻断**导出 | auto + 手工 UI |
| AC-FILE-01 | P1 | **删附件有引用守卫**（v1.17 / `FILE_IN_USE`）：证件照或导入候选或 `build_artifact` 引用某附件时 `DELETE /api/v1/files/{id}` → **409 `FILE_IN_USE`** + `details.referenced_by[]`（非空、含引用方 kind 与 id）；解绑引用后再删 → 200；**判据**：先删再查 `data/files/` 里该文件仍在（不得物理删除） | auto |
| AC-PDF-19 | P1 | 导出的 PDF 可被 `pypdf` 打开且 `len(reader.pages) >= 1`（结构合法） | auto |
| AC-PDF-20 | P2 | 预览页 `@media print` 与 PDF 版式一致（A4 margin 相同） | 手工 |

---

## 7. 经历库与组装（BUILD）

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-BUILD-01 | P0 | 创建 Package → 加 bullet_key → 加 3 个 tone 的 variant → `status` 从 `draft` 改 `ready` 时，若 `verified` 数为 0 → 409 `CONFLICT`（`details.reason="PACKAGE_NEEDS_VERIFIED_VARIANT"`，`details.unverified=[...]`） | auto |
| AC-BUILD-02 | P0 | 组装 `POST /api/v1/builds/{id}/assemble`：只把**显式选中的 variant** 编入；未选中的 variant 文本不出现在 preview HTML | auto `test_ac_build_02` |
| AC-BUILD-03 | P0 | 未绑定 `user_profile` 时组装仍成功但 `warnings` 含 `PROFILE_INCOMPLETE`（列出缺失字段） | auto |
| AC-BUILD-12 | P0 | **无默认模板时 assemble 拒绝而非猜**（v1.17）：构造「模板存在但 `is_default` 全 0」→ `POST /builds/{id}/assemble` 不带 `template_id` → **409 `CONFLICT`** + `details.reason="NO_DEFAULT_TEMPLATE"` + `candidates[]` 非空；显式传 `template_id` → 200；构造两个 `is_default=1` → 409 `MULTIPLE_DEFAULT_TEMPLATES`。**反向断言**：不得返回 200 且静默用最新模板 | auto |
| AC-BUILD-13 | P0 | **日期往返不丢（D-35 回归）**：① `POST /api/v1/packages` 带 `start_date:"2024-01", end_date:"2024-06"`（**不传 `is_current`**）→ 响应与 `GET /api/v1/packages/{id}` 回读均 `end_date=="2024-06"`、`is_current is False`；② `PATCH` 改 `end_date:"2024-09"` → 回读相等；③ **反向断言**：库里不得出现 `is_current=1 AND end_date IS NOT NULL` 之外的「未显式传 is_current 却为 1」（`select count(*) from package where is_current=1 and end_date is not null` 恒 0，且新建行的 `is_current` 必须为 0）；④ **护栏不许删**：`is_current=true` + `end_date` → **422 `VALIDATION_ERROR`**（若返回 200，即使结果「看起来对」也判失败）。**实测现状为失败**：真库 18/18 行 `is_current=1` 且 `end_date IS NULL`（根因 `server/app/repos.py:686`），故本条当前记 KNOWN-FAIL，修好前 t11 不得判 pass | auto |
| AC-BUILD-04 | P1 | 模板槽位缺失时 preview 渲染占位 `⟨slot_key⟩`，并在 `missing_slots[]` 返回；不抛异常 | auto |
| AC-BUILD-05 | P1 | 排序稳定：`build_selection.sort_order` 决定输出顺序，重复 assemble 结果一致（同输入同输出，`ir_hash` 相同） | auto |
| AC-BUILD-06 | P1 | 搜索：`GET /api/v1/packages?q=订单` 走 FTS5 且中文命中（实测 FTS5 在本机可用）；空 `q` 走普通分页 | auto |
| AC-BUILD-07 | P1 | 页数估算与实测接近：assemble 的 `est_pages` 与导出 PDF 的实际页数差值 ≤ 0.35 页（对 3 个夹具） | auto |
| AC-SKILL-01 | P0 | **技能区逐字等于 `skills_json[].line`**：导出 PDF 的技能行文本（`pdfplumber` 抽取、`str.strip()`、合并行内空白后）与 `skills_json[].line` 逐条 `==` 相等；行数与顺序都与 `order` 一致 | auto `test_ac_skill_01`（夹具含全角冒号、顿号、`Python`/`R`/`SQL` 混排） |
| AC-SKILL-02 | P0 | **反向断言：PDF/预览 HTML 中不得出现 tag 块**——技能区文本不得含「空格+竖线+空格」分隔的三段以上短词（正则 `[A-Za-z\u4e00-\u9fa5]{1,12}( \\\| [A-Za-z\u4e00-\u9fa5]{1,12}){2,}`）、不得含标签云容器（技能区内 `class` 命中 `tag`/`chip`/`pill`/`badge` 的列表节点数为 0），且技能区 DOM 节点数 == 行数（不是 token 数） | auto `test_ac_skill_02` |
| AC-SKILL-03 | P1 | **`tokens` 缺失时匹配降级但不丢行**：把某行 `tokens` 置 `[]`/删除后，JD 匹配改走 `line` 子串匹配（仍能命中 `SQL`），assemble 与导出**不报错**、该行仍完整渲染 | auto `test_ac_skill_03` |
| AC-SKILL-04 | P1 | **课程裁剪默认关且有痕**：`trim_courses` 默认 `false` → 课程行原文全留；显式开 `true` → 输出保留「主修课程：」前缀且**课程数 ≥3**，并把「裁剪前 N 门 → 裁剪后 M 门」写进 build 的 `warnings[]`（`code="COURSES_TRIMMED"`），build 详情可见 | auto `test_ac_skill_04` |
| AC-BUILD-08 | P2 | 包可归档（软删），归档后不出现在默认列表，但历史 build 仍能引用 | auto |

---

## 8. JD 与公司画像（JD）

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-JD-01 | P0 | LLM 不可用时 `POST /api/v1/jds/{id}/analyze`（`method=auto`）走本地启发式：202→job 完成，`GET /jds/{id}/requirements` 返回 `items[]`（≥1 条），`analysis_method="heuristic"`，且**不产生** `LLM_*` 错误（最多一条 warning） | auto |
| AC-JD-02 | P0 | LLM 可用时：`analyze` 必须先返回 `preview`（字段清单），**未经 `complete` 不产生任何需求记录** | auto |
| AC-JD-03 | P1 | `POST /api/v1/jds/{id}/match`（**本地打分，不联网**）返回 `coverage`∈[0,1]、`scores[]{package_id,score,hits[],gaps[]}`、`top_gaps[]`；`egress_guard` 生效时仍成功 | auto |
| AC-JD-04 | P1 | 需求可人工改（`PATCH /api/v1/requirements/{id}`，改后 `source="manual"`），改 `weight`/`priority` 后 `match` 的 `coverage` 随之变化 | auto |
| AC-JD-05 | P2 | CompanyProfile 可由用户手填/由 LLM 建议，字段含 `culture_tags[]`、`hiring_signals[]`、`source_urls[]` | 手工 |

---

### 8.1 公开页面下行抓取（FETCH）

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-FETCH-01 | P0 | **下行请求体恒空、不含任何用户数据**：`POST /fetch/public-page` 抓一次（本地假服务器）→ 捕获请求，断言 `body == b""`、`query` 只有 URL 本身、无 cookie、`User-Agent` 固定；断言请求里不含姓名/邮箱/电话/学校名 | auto `test_ac_fetch_01` |
| AC-FETCH-02 | P0 | **白名单与关断**：host 不在白名单 → 403 `EGRESS_BLOCKED` `details.reason="host_not_allowed"` 且**零出网**；解析到私有 IP → 403 `details.reason="private_address"`；`allow_web_fetch=false` → 403 `details.reason="fetch_disabled"`；跳转 >3 跳 → 403 `too_many_redirects` | auto `test_ac_fetch_02` |
| AC-FETCH-03 | P0 | **抓取失败必须降级不阻断**：正文 < 200 字符（SPA 空壳）/超时/403 → 公司分析仍返回 200，`warnings` 含 `FETCH_UNAVAILABLE`，且分析只基于用户粘贴的 JD 与备注；`public_fetch_log` 有记录（只有 URL 与元信息，无用户数据） | auto `test_ac_fetch_03` |

---

### 8.2 竞争力与院校偏好（ANL，ADR-20）

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-ANL-06 | P0 | **竞争力必须消费校名**：用真实 JD 跑 `jd/analyze`（LLM 路径）→ `competitiveness.school_tier` ∈ `C9/985/211/双一流/普通本科/海外/其他` 且非空；`verdict` ∈ `strong/medium/weak`；`school_signal` **长度 ≥8 且含校名（`示例大学`）或院校层次词（`985`/`211`/`双一流`/`本科院校`）**——纯模板套话（如「表现良好」「具备竞争力」）判失败；`requirements[]` 每条都有 `candidate_status` ∈ `satisfied/partial/missing`。离线 `method=heuristic` 时 `competitiveness` 仍非 null（`school_tier` 取 `UserProfile.school_tier` 或 `其他`） | auto `test_ac_anl_06` + 人工抽验 1 次真实 JD |
| AC-ANL-07 | P0 | **院校偏好不许编造**：`company/profile` 响应 `school_preference.threshold` 非空且 ∈ `不限/本科及以上/985/211/双一流/目标院校清单`；**JD 与抓取文本均未提院校**时 → `hard_filter=false`、`preferred_tiers=[]`、`threshold="不限"`，且 `evidence` 说明依据（如「仅见『本科及以上』，未见院校层次要求」）；若 JD 明写「985/211」→ `hard_filter=true` 且 `evidence` 引用原句 | auto `test_ac_anl_07`（两个夹具：无院校要求 / 明写 985） |
| AC-ANL-09 | P0 | **「未识别 ≠ 普通本科」**（D-37）：① `UserProfile.school` 置 `XX大学`（未收录）→ `competitiveness.school_tier == "其他"` 且 **`recognized is False`**，`warnings` 含 `SCHOOL_TIER_INFERRED` 且 `details.recognized is False`、`severity=="warn"`；② **反向断言**：`school_tier` **不得**为 `普通本科`（把没收录判成普通本科 = 编造）、`verdict`/`gap_notes`/`school_signal` 均不得出现「层次偏低 / 院校竞争力偏弱 / 学历背景不足」；③ `麻省理工学院`、`Stanford University` → `海外`；④ 手填 `school_tier="985"` 后 `recognized is True` 且无 warn 级 `SCHOOL_TIER_INFERRED` | auto |
| AC-ANL-10 | P1 | **「优先」不得被硬门槛逻辑吞掉**（D-37）：JD 文本含「985/211 优先，但不设院校门槛」→ `hard_filter is False`、`threshold` **以「不限」开头且含「偏好」**、`preferred_tiers` **非空**；**反向断言**：JD 全文无院校词 → `preferred_tiers == []`（不得造偏好） | auto |
| AC-ANL-11 | P0 | **门槛动词分组：优先≠门槛**（D-39，参数化逐行）：直接调 `detect_school_gate([...])`（**列表入参**，与 `company_analysis.py:71` 真实调用一致）跑 §7 用例表 1/2/3/8：`hard_filter is False`、`threshold` 以「不限」开头且含「偏好」、`preferred_tiers` 含对应档位；再用用例 5/6/7 做对照（`要求 985 及以上` → `True`；`不设院校门槛` → `False` 且 `[]`；无院校词 → `[]`）。**反向断言**：`HARD_VERBS` 与 `SOFT_VERBS` 必须是两个独立常量，`优先` 只允许出现在 `SOFT_VERBS` 里（人工核对一次，防回退） | auto `test_ac_anl_11` |
| AC-ANL-12 | P0 | **并列档位不得截断**：`detect_school_gate(["仅限 985/211 院校"])` → `hard_filter is True`、`preferred_tiers == ["985","211"]`（实测 2026-10-23 04:17:29 已通过，**保留为回归判据**）、`threshold` 保留并列原文（须同时含 `985` 与 `211`）；另测 `985、211` 与 `985 和 211` 两种写法等价。判据取自 §7「并列档位不得截断」 | auto `test_ac_anl_12` |
| AC-ANL-13 | P0 | **`jd_analyze` 必须带经历要点（§6.2）**：`POST /llm/preview` 的 `fields[]` 至少有一项 `source="packages"`，其 `source_id` 指向**包**、`label` 含包标题；payload 文本里能找到该包的 bullet 原文片段。**反向断言**：payload 不含 `skills_json[].tokens` 的任一 token、不含 `package_id`/`variant_id`/`photo_path`/任何 `data/**` 路径。预算：`context.packages_included ≤ 12`、`context.chars ≤ 6000`、`packages_included + skipped == 选包总数`；超限时 `warnings` 含 `PACKAGES_TRUNCATED{included,skipped}` | auto `test_ac_anl_13` |
| AC-ANL-14 | P0 | **本地覆盖改判与反向约束（§6.2.5）**：构造「模型判 `missing`、本地命中 1 个 ready 包」→ 结果 `candidate_status="partial"`、`candidate_status_source="local_override"`、`warnings` 含 `LLM_STATUS_OVERRIDDEN{requirement,from:"missing",to:"partial",matched_package_ids[]}`；**反向**：`matched_package_ids=[]` 时模型给的 `missing` **必须原样保留**（改判即 FAIL）——不得把「没有」伪造成「有」。另断言改判方向唯一：`satisfied`/`partial` 不因本地命中而上调 | auto `test_ac_anl_14` |
| AC-ANL-15 | P0 | **`matched_package_ids` 本地计算且指向 ready 包（§6.2.4）**：① 模型返回的 id 数组若被直接采信（构造模型编造一个不存在的 id）→ 该 id 必须**不出现**在库中结果；② 指向 `status!='ready'` 的包（软删或 draft）→ 剔除 + `warnings` 含 `MATCHED_PACKAGE_NOT_READY{requirement_id,package_ids[],statuses[]}`；③ 空数组必须是「算了但没匹配到」——用 `order`/词表构造一条确定不该命中的 requirement，断言 `[]` 且无 `MATCHED_PACKAGE_NOT_READY` | auto `test_ac_anl_15` |
| AC-ANL-16 | P0 | **`matched_evidence` 三源可回溯（§6.2.4 / I21）**：`GET /jds/{id}?include=requirements` 每条 requirement 带 `matched_evidence[]`，逐项断言 ① `source ∈ {package,skills_json,profile}`；② `source="package"` ⇒ `ref_id` 非空且该包 `status=='ready'`；③ `source∈{skills_json,profile}` ⇒ `ref_id is null`；④ `quote` 长度 ≥8 且**能在来源里逐字找到**（package→variant `text`、skills_json→`skills_json[].line`、profile→该字段值）。**反向断言**：构造一条 `quote` 被改写的记录 → 校验器必须判 FAIL | auto `test_ac_anl_16` |
| AC-ANL-17 | P0 | **「没匹配到」是两个数组皆空（§6.2.4 / I22）**：真库场景复现——「数据分析类：掌握Python」这类**技能栏命中**的 requirement 必须 `matched_evidence` 非空（`source="skills_json"`, `ref_id=null`）而 `matched_package_ids` 可为 `[]`，且 `candidate_status != "missing"`；反向：两个数组皆空的 requirement 才允许 `missing`。另断言 `matched_package_ids` 中每个 id 在 `matched_evidence` 里都有 `source="package"` 的对应项（两处不许打架） | auto `test_ac_anl_17` |
| AC-ANL-18 | P0 | **人工改判优先级与不可覆盖（§6.2.5 / I23）**：① `PATCH /requirements/{id} {"candidate_status":"satisfied"}` → `candidate_status_source=="manual"`；② 随后触发重算（`POST /jds/{id}/analyze` 或本地重算）→ 该行 `candidate_status` **仍为 satisfied**、`source` 仍为 `manual`，但 `matched_*` 允许更新；③ 撤销需显式 `{"candidate_status_source":"auto"}`，否则重算继续跳过；④ 界面/响应可识别人工标记（`candidate_status_source=="manual"` 时前端显示「已人工修正」角标）。反向断言：重算把 manual 行改回 `missing` 即 FAIL | auto `test_ac_anl_18` |
| AC-PRIV-14 | P0 | **校名真实上云且被断言**：抓取一次 `jd/analyze` 的 `payload_json`，断言 `"示例大学" in payload_json` 为真（**不得**变成 `[SCHOOL]`，`payload_json.count("[SCHOOL]") == 0`）、`profile` 段七项（`school/school_tier/degree/major/grad_year/city/available_date`）齐全；同时 `name_zh`/`phone`/`email` 的真实值计数为 0，`payload_json` 无 base64 图像 | auto `test_ac_priv_14` |

## 9. LLM Provider（LLM）

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-LLM-01 | P0 | **`deepseek` 是默认可用的唯一主路径**：`LLM_PROVIDER=deepseek` 缺省、`LLM_BASE_URL=https://api.deepseek.com/v1`；`PUT /api/v1/settings` 可改 `model` 与 `base_url`（自定义 OpenAI 兼容地址作为**高级项**保留，枚举 `deepseek \| openai_compatible \| off`）；`POST /api/v1/settings/api-key` 写 key（`chmod 600` 写 `.env`）；`GET /api/v1/settings` 只回 `key_set/key_field`，不含 key 任何片段；**不得出现 `ollama` 档位**（`providers.py` 无该分支，`PUT` 传 `provider="ollama"` → 422 `VALIDATION_ERROR` `details.reason="UNSUPPORTED_PROVIDER"`） | auto |
| AC-LLM-02 | P0 | 未配置 key 时调用 `llm/preview` → 503 `LLM_NOT_CONFIGURED`，提示去设置；**不发起任何网络请求** | auto |
| AC-LLM-03 | P0 | **`provider=off` 是完全不上云的一等开关**：置 `off` 后全部 LLM 端点（`/llm/preview`、`/llm/complete`）→ 503 `LLM_DISABLED`，`llm_call_log` 零新增、`httpx` 调用计数 = 0（**含「已确认预览」这一情形**：先 `POST /llm/preview` 拿到 `preview_id`，再把 provider 置 `off` 调 `POST /llm/complete`，仍须 503 `LLM_DISABLED` 且 `outbound_calls == 0`——`off` 与 consent 冲突时以 `off` 为准，不得因预览已确认而放行）；同时导入、组装、导出、命名等本地功能**全部照常可用**；`GET /env` 的 `warnings[]` 不含任何 Ollama 相关条目（该警告码已删除） | auto |
| AC-LLM-04 | P1 | 「测试连接」`POST /api/v1/settings/provider/test` 返回 `reachable/http_status/models[]/latency_ms/error_code?`；超时 5 s 内返回而不挂死 | auto |
| AC-LLM-05 | P0 | Key 存 `.env` 的 `LLM_API_KEY=`（`chmod 600`，单变量、provider 无关）；进程内不写入任何可序列化对象；重启后 `key_set=true` 仍成立；`.env` 中不得出现 `DEEPSEEK_API_KEY` 之类的分裂变量名 | auto + 命令 `ls -l .env` |
| AC-LLM-06 | P1 | 兜底路径：provider 返回 429/500/超时 → 前端收到 `LLM_UPSTREAM_ERROR` 或 `LLM_TIMEOUT`，且**已生成的部分结果不落库**（事务回滚） | auto |
| AC-LLM-07 | P2 | 支持「不使用 AI」模式：全部功能（导入、组装、导出）在不配置任何 provider 时可用 | auto |
| AC-LLM-08 | P0 | **连接级异常按瞬态重试**：monkeypatch transport 使前 2 次抛 `httpx.ConnectError`（内层 `[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol`）；参数化覆盖 `httpx.ConnectError` / `httpx.ReadError` / `httpx.RemoteProtocolError` / `ssl.SSLError` 四种连接级形态，均应进同一重试路径，第 3 次返回 200 → 最终 200；`llm_call_log` 记 3 条 attempt（`attempt_no=1..3`）、只有最后一条 `ok=1`；`llm_preview` 只被消费 1 次；重试上限来自 `LLM_MAX_RETRIES`（默认 2） | auto `test_ac_llm_08` |
| AC-LLM-09 | P0 | **连接级失败不消耗 consent，且与鉴权失败可区分**：3 次全抛 `ConnectError` → 503 `LLM_UNREACHABLE`（`details.kind="connect"`、`details.http_status` 为 null）；`llm_preview.status` 仍为 `pending`，同一 `preview_id` 可再次 `complete` 并成功（**不得**报 `LLM_CONSENT_MISMATCH`）。对照组：上游 401 → 502 `LLM_UPSTREAM_ERROR`（`details.http_status=401`）且**重试次数为 0** | auto `test_ac_llm_09` |
| AC-LLM-10 | P0 | **`json_object` 前置条件在本地守门**：构造不含字面量 `json` 的 messages → 422 `LLM_JSON_MODE_PRECONDITION`（`details.reason="PROMPT_MISSING_JSON_LITERAL"`），且 **httpx 调用计数 = 0**（零出网）；同时参数化断言 `llm_prompt.build_messages()` 对**每个** JSON 用途注入的指令串含 `json` | auto `test_ac_llm_10` |
| AC-LLM-11 | P0 | **推理截断的空输出拒收**：fake 上游返回 `finish_reason="length"`、`content=""`、`reasoning_content` 非空、`reasoning_tokens == max_tokens` → 502 **`LLM_TRUNCATED`**（`details.reason="empty_content"`, `finish_reason="length"`），**零入库**（`package_bullet_variant` / `jd_requirement` / `company_profile` 行数不变）、**不自动重试**（attempt 数 = 1）；`details` 必含 `finish_reason="length"`、`completion_tokens`、`max_tokens`、`reasoning_tokens`；`finish_reason="length"` 但 `content` 非空时按可解析性分两种（实现即契约，`server/app/adapters/llm_client.py:421/450`）：（a）**半截 JSON 不可解析** → 502 `LLM_TRUNCATED` `details.reason="partial_json"`，零入库；（b）**正文非空且 JSON 可解析** → 200 + `warnings[]` 含 **`OUTPUT_TRUNCATED`**（`severity="warn"`），产出照常落库但必须标不完整，UI 提示补 `max_tokens`；`finish_reason="length"` 且 `content=""` → 502 `LLM_TRUNCATED` `details.reason="empty_content"`（见右列分档） | auto `test_ac_llm_11`（三档） + 手工|
| AC-LLM-12 | P0 | **`LLM_TRUNCATED` 与 `LLM_BAD_RESPONSE` 互不重叠**：① `finish_reason="stop"` + `content` 为完整非法 JSON（如 `{"a":`）→ 502 `LLM_BAD_RESPONSE`（`details.reason` 非 `empty_content`/`partial_json`）、`llm_call_log.error_code="LLM_BAD_RESPONSE"`、**重试 0 次**；② `finish_reason="stop"` + 合法 JSON 但缺必填字段 → 同 `LLM_BAD_RESPONSE`；③ 统计断言：截断场景 `error_code` 只能是 `LLM_TRUNCATED`，反例场景只能 `LLM_BAD_RESPONSE`（两个计数互斥）。警示码表**不含** `OUTPUT_TRUNCATED`（已删除） | auto `test_ac_llm_12` |

---

## 10. 前端（UI）

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-UI-01 | P0 | 断网（模拟）下所有页面可加载：无 CDN、无外链字体/图片请求（Network 面板无外部域名） | 手工（DevTools Offline + 截图） |
| AC-UI-02 | P0 | 零构建：`web/` 下只有 `.html/.js/.css/.svg`，无 `node_modules`、无打包产物；用 `python -m http.server` 直接也能打开静态页骨架 | 命令 `ls web/ && grep -rn "https://" web/` 无命中（零外部资源） |
| AC-UI-03 | P0 | ConsentModal：调用任何 LLM 能力前必然出现；`Esc` = 取消；Enter **不**触发发送；`excluded` 与 `redactions` 在主视野可见（不折叠）；过期后按钮变「重新生成预览」 | 手工 + auto（DOM 断言） |
| AC-UI-04 | P0 | 用户可控文本不通过 `innerHTML` 注入：`grep -rn "innerHTML" web/` 命中项必须逐个说明为常量模板；简历预览走服务端 jinja2（autoescape on） | 命令 + 评审 |
| AC-UI-05 | P1 | 导出对话框实时显示命名解析结果；缺变量时红字 + 「去填个人信息」深链；默认值 `{position}-{name}-{school}` | 手工 |
| AC-UI-06 | P1 | 长任务有 `JobToast`（进度/阶段/可取消仅 queued）；服务重启后变「已中断」 | 手工 |
| AC-UI-07 | P1 | 1280×800 下无横向滚动条；三栏在 1440+ 展开 | 手工截图 |
| AC-UI-08 | P1 | 字体不可用/引擎不可用时顶部红条出现且 PDF 按钮禁用（用 `preflight` 注入降级态验证） | 手工 |
| AC-UI-09 | P1 | 错误按 `error.code` 分支展示，`hint` 作为下一步；不把 `details` 原样 JSON 抛给用户 | 手工 |

---

## 11. 健壮性与降级（ROB）

| ID | 级别 | 断言 | 验证 |
|---|---|---|---|
| AC-ROB-01 | P0 | 数据库 WAL 模式开启；并发 5 个请求写不同表不出现 `database is locked`（busy_timeout=5000） | auto `test_ac_rob_01` |
| AC-ROB-02 | P1 | 非法 JSON → 400 `BAD_REQUEST`；未知路由 → 404 `NOT_FOUND` 统一信封；方法不允许 → 405 | auto |
| AC-ROB-03 | P1 | 所有响应（含错误）为统一信封 `{ok, data?, error?, request_id}`；`request_id` 出现在响应头与日志 | auto |
| AC-ROB-04 | P1 | 路径穿越防护：`GET /api/v1/files/../../.env` → 400/404，绝不返回文件内容 | auto |
| AC-ROB-05 | P1 | 大输入：10 万字符 JD 不崩（422 `PAYLOAD_TOO_LARGE` 或成功处理，二者择一但必须明确） | auto |
| AC-ROB-06 | P2 | 任务表重启恢复：`queued` 任务标 `interrupted`，可重试 | auto |

---

## 12. 端到端场景（E2E）

| ID | 级别 | 场景 | 通过标准 |
|---|---|---|---|
| AC-E2E-01 | P0 | **从零到一份可投简历**：启动 → 填 UserProfile → 建 1 个包（2 条事实 × 2 tone，标 verified）→ 导入中文样张为模板 → 建 build（选包/选 bullet）→ 组装 → 命名 `{position}-{name}-{school}` → 导出 PDF | 产出 `data/exports/数据分析实习生-张三-示例大学.pdf`；pdfplumber 提取含「张三」「示例大学」且无 `\ufffd`；`build_artifact` 有记录 |
| AC-E2E-02 | P0 | **JD 定制**：粘贴 JD → 分析（LLM 或启发式）→ 匹配 → 按缺口调选包 → 导出 `{company}_{position}_{name}.pdf` | 命名解析正确；PDF 中含 JD 前 3 个 must 技能词中至少 2 个（若用户选择对应 bullet） |
| AC-E2E-03 | P0 | **隐私全链路**：新建含手机号的包 → 触发生成 → 检查 Consent 字段清单 → 抓包确认只发选中片段且手机号脱敏 → 检查日志无正文 | 抓包 body 无原文/无手机号；日志无正文 |
| AC-E2E-04 | P1 | **断网全链路**：拔网线/关 WiFi，完成 AC-E2E-01 全部步骤（LLM 相关跳过，用启发式） | 全流程成功，无卡死、无 30 s 超时 |
### 12.1 集成硬门（INT 系列，t11 直接照跑）

> 编号沿用 `docs/REVIEW-CHECKLIST.md` 的 INT 序列（INT-01..12 在那里）。**本节是 INT-11 的补充项**，因为 INT-11 只比对「文件里的端口 == 实际端口」，漏掉了一种会**绿着放过去**的死端口：实现把配置值写进 `/health` 而不是实际 bind 端口。

| ID | 级别 | 场景 | 通过标准（三处交叉，任一不等 → 判 coder，**BLOCKER**） |
|---|---|---|---|
| **INT-13** | P0 | **端口顺延后三值必须相等**（captain 2026-10-23 实测：实例跑在 8766 时 `/api/v1/health` 仍回 `"port": 8765`，读的是配置值） | ① 用 `python3 -m http.server 8765` 占住默认端口再起服务；② 从 `data/runtime/app_port` 取 `json["port"]`（记 P1）；③ `curl -s http://127.0.0.1:$P1/api/v1/health \| python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["port"])'`（记 P2）；④ `lsof -nP -iTCP:$P1 -sTCP:LISTEN` 确认实际 bind（记 P3）。断言 **P1 == P2 == P3**，且 P1 ≠ 8765。判据：任一不等即死端口，前端与用户会拿到连不上的地址 → **BLOCKER，判 coder** |
| **INT-14** | P0 | **只读 GET 端点 JSON 可序列化冒烟**（captain 2026-10-23 实测：`GET /api/v1/env` 500 `TypeError: Object of type TTFNameBytes is not JSON serializable`，`envcheck.py:122` 的 `font.face.name` 是 reportlab 的 `bytes` 子类） | 对全部只读 GET（`/health` `/env` `/profile` `/packages` `/packages/{id}` `/templates` `/templates/{id}` `/jds` `/jds/{id}` `/company-profiles` `/jds/{id}/requirements` `/builds` `/builds/{id}` `/builds/{id}/selections` `/artifacts` `/jobs/{id}` `/settings`）逐条断言：① 状态码 **200**；② `json.loads(body)` 成功；③ `b"b'" not in body`（防 bytes 被 `str()` 成 `b'...'` 脏值）；④ `/api/v1/env` 额外断言 `data.fonts.primary.name == "STSongti-SC-Regular"`。**任何一条 500 或含 `b'` → 判 coder，BLOCKER** |

**入册教训（必须遵守的元规则）**：反向 grep 判据**必须先在当前代码上跑一遍、确认基线为 0 才允许写进本文档或 REVIEW-CHECKLIST**。反例：`cut -c[0-9]+-` 会误命中合法的 `cut -c1-8`（SHA-256 取前 8 位），清单自带假红 → t11 照着假红判错人。正确写法见 §3.3 的 `int(read())` 反向判据与 §3.2 的 key 片段判据，两者都已在本机实测基线为 0。

| AC-E2E-05 | P1 | **重启一致性**：导出中途 `kill` 服务 → 重启 → 任务显示「已中断」，库无半成品 artifact，可重试成功 | 手工 + auto |

---

## 13. 已知问题清单（不视为验收失败，但必须如实呈现）

| 编号 | 现象 | 影响 | 处置 |
|---|---|---|---|
| KI-01 | 英文样张 `sample_en.pdf` 抽取文本含 **16 处 `(cid:127)`**（Symbol 项目符号，ToUnicode 缺失） | 若当正文会污染简历 | 解析层识别为列表标记并剥离；`warnings` 记 `CID_GLYPH_MISSING count=16`；**不得报「缺字」错误**（AC-IMPORT-02 已覆盖） |
| KI-02 | Chrome 回退渲染用 Songti SC / Hiragino 时，提取文本变康熙部首（高→U+2FBC） | ATS 解析失败 | 回退路径字体栈锁定 STHeiti / Arial Unicode MS；导出后强制文本一致性校验（AC-PDF-05） |
| KI-03 | `soffice --convert-to pdf` 本机崩溃（`DeploymentException` / Signal 6） | 无法用 LibreOffice 转 PDF | 永久排除，不做运行时探测重试 |
| KI-04 | weasyprint import 即失败（缺 `libpango-1.0-0`） | 无法用 HTML→PDF 主力方案 | 永久排除 |
| KI-05 | 本机无 Ollama 服务（11434 关闭，无 CLI/App）；用户拍板**坚持 DeepSeek 路线**，不做本地模型 | 早期文档曾列 Ollama 为 provider，会误导实现与终验 | **明确不做**：provider 仅 `deepseek`/`openai_compatible`/`off`；预检不探测 11434；UI 无「本地模型」入口；需要完全离线用 `off`（AC-LLM-03） |
| KI-06 | reportlab 表格单元格不解析 `<b>`；需 `registerFontFamily` + `addMapping` | 富文本静默失效 | 单元格一律用 `Paragraph`；字体家族注册放 `fonts.py` 单点 |
| KI-07 | emoji 在 reportlab 渲染为 `\x00` | 产物豆腐、文本校验误判 | 导出前剥离并 `EMOJI_STRIPPED` 告警 |
| KI-08 | 无 `PingFang.ttc`；`Hiragino Sans GB.ttc` 为 PostScript 轮廓（`TTFError`） | 字体选择受限 | 字体链固定：Songti.ttc(idx6/idx1) → Arial Unicode → STHeiti |
| KI-09 | macOS 无 `timeout` 命令 | 脚本跨平台性 | 统一用 Python 侧超时（socket/urllib/httpx timeout） |
| KI-10 | 裸 `python -m venv .venv` 缺 flask | 启动失败 | 文档与 `run.sh` 强制 `--system-site-packages`，preflight 校验 |
| KI-11 | **TLS 抖包**：约 1/12 请求握手期失败（`httpx.ConnectError` + `[SSL: UNEXPECTED_EOF_WHILE_READING]`，无 HTTP 状态码；重试 2 次后 12/12 成功） | 误判为「服务不可用」会错误禁用 AI 功能 | 按瞬态处理（`LLM_MAX_RETRIES=2`，连接级与 HTTP 级共用），最终 503 `LLM_UNREACHABLE`；不消耗 preview（AC-LLM-08/09） |
| KI-12 | `response_format=json_object` 硬性要求 prompt 含字面量 `json`，否则 400 `Prompt must contain the word 'json' …` | 浪费一次出网并误报上游错误 | 本地前置断言 → 422 `VALIDATION_ERROR`，零出网（AC-LLM-10） |
| KI-13 | `deepseek-reasoner` 的 `max_tokens` 过小时推理烧光预算：`finish_reason=length`、`content=""`、`reasoning_tokens=max_tokens` | 空内容入库会污染经历库/需求库 | 空 `content` 拒收（502 `LLM_TRUNCATED`）+ 分析链路 `max_tokens ≥ 2048`（AC-LLM-11） |
| KI-14 | **中文样张 PDF 有照片**：1 页 A4（595.5×842.2 pt），内嵌 1 张 266×266 JPEG，渲染在右上角 89.3×89.3 pt（`x0=497.1`，距顶 3.8 pt），与姓名区并列；用户要求**中英两版都保留照片** | 若沿用旧版「PDF 不含照片」假设，会丢失用户要求的内容 | 照片默认渲染（`photo_in_export=true`）；导入时抽候选图；无照片时按 AC-PHOTO-02 重排不留空洞 |
| KI-15 | 公司官网多为 SPA 或反爬，抓回的 HTML 正文可能 < 200 字符 | 拿空壳喂 LLM 会得到无意义分析 | 正文 < 200 字符视同抓取失败 → 降级用粘贴 JD；`warnings` 记 `FETCH_UNAVAILABLE`（AC-FETCH-03） |

---

## 14. 验收执行记录模板

> **本模板中的 AC 编号仅作状态引用，不计入条款总数。**
> 统计口径：条款区 = 本文件 §14 之前的部分；`条款行` 与 `唯一 AC ID` 必须相等且重复 ID 为 0（见 §0 规则）。

```markdown
# ACCEPTANCE-RUN — <日期>

| AC ID | 结果 | 证据 | 执行人 |
|---|---|---|---|
| AC-ENV-01 | PASS | `.venv/bin/python -c "import flask,..."` exit 0 | qa |
| AC-PDF-02 | PASS | tests/acceptance/test_ac_pdf_02.py | qa |
| AC-IMPORT-02 | KNOWN-FAIL | 素材未提供，仅跑合成夹具 | qa |

## 结论
- P0 通过率：__/__
- P1 KNOWN-FAIL：__ 项（上限 2）
- BLOCKER：无 / 有（列出）
- 总判定：PASS / FAIL
```

---

## 15. 与硬约束的对应关系（自查表）

| 硬约束 | 覆盖条目 |
|---|---|
| ① 数据只落本地 | AC-LOC-01..07、AC-ROB-04 |
| ② 上云出口 = `llm_client`（上行，唯一携带用户数据）；下行抓取是独立通道 `fetch_client` | AC-PRIV-06/07/10、AC-FETCH-01/02、AC-LLM-01/05 |
| ③ 发送前 UI 展示字段清单，只发选中片段；宽路径下姓名/电话/邮箱/学校/照片一律占位符 | AC-PRIV-01..05、AC-PRIV-11/12、AC-PHOTO-03、AC-UI-03、AC-E2E-03 |
| ④ 无联网才能启动的依赖（LLM 走 DeepSeek 主路径，`off` 可完全离线） | AC-ENV-02/03、AC-UI-02、AC-E2E-04 |
| ⑤ 后端不赌安装 | AC-ENV-01/08（Flask 已预装并实测） |
| 追加 1：UserProfile 单例、前端不硬编码 | AC-NAME-04/06/07、AC-BUILD-03 |
| 追加 2：命名模板 `{position}-{name}-{school}` + 缺变量报错 | AC-NAME-01..07 |
| 追加 3：data/** 不进 LLM、.gitignore、cid:127 已知问题 | AC-LOC-05、AC-PRIV-01、AC-IMPORT-02、KI-01 |
| 中文 PDF 不缺字 | AC-PDF-02/03/04/05/06、AC-E2E-01 |
| 照片（中英两版都保留） | AC-PHOTO-01/02/03/04、KI-14 |
| 端口顺延 + 真实地址可被 Skill 读到 | AC-ENV-06/09 |
| 公司官网/招聘页抓取（默认开、可关、失败降级） | AC-FETCH-01/02/03、KI-15 |
| 离线可用 | AC-E2E-04、AC-PRIV-10、AC-IMPORT-07 |
| 英文简历（抬头全大写 `SAN ZHANG`、语言契约、en 变体） | AC-NAME-09（P1，原与 `AC-NAME-01` 撞号）、AC-EN-01/02/03/04、AC-CONFLICT-01 |
| 中英来源冲突（用户已决议：以中文简历的 GPA/到岗时间为准，可自行修改） | AC-CONFLICT-01（未决议两值不合并）、**AC-CONFLICT-02（已决议降为 info + 反向恢复）** |
| 教育段补充行真源 = 模板 `static_text`（不造第二真源） | **AC-PROF-01**（含「profile 不得出现 gpa/score/courses 列」的结构断言） |
| 到岗时间唯一渲染真源 = `available_note`（`available_date` 不参与渲染） | **AC-PROF-02** |
| PDF 结构合法与打印版式一致 | AC-PDF-19（P1，原撞 `AC-PDF-11`）、AC-PDF-20（P2，原撞 `AC-PDF-12`） |
