# REVIEW-CHECKLIST — 逐 lane DoD、跨 lane 契约核对与追责规则

> 冻结 v1.0（2026-10-23）。作者：supervisor。用途：**终验（t11）当天照此逐条打勾**，不允许凭印象放行。
> 派生自：`docs/ACCEPTANCE.md` v1.1（唯一验收口径）、`docs/API-CONTRACT.md` v1.2、`docs/DATA-MODEL.md`、`docs/ARCHITECTURE.md`、`docs/DESIGN-BRIEF.md`。
> **本清单不新增、不放宽任何验收条目**（唯一例外：§1.1 的 CORE-19~CORE-23 是 captain 2026-10-23 实测追加的 LLM 加固口径，已就地标注「待 planner 回填 ACCEPTANCE/API-CONTRACT」）。若本清单与 `ACCEPTANCE.md` 冲突，以 `ACCEPTANCE.md` 为准，并把冲突登记为 planner 缺陷（§2.7）。
> 判定原则：**没有可复现的证据 = 未通过**；证据必须是「命令 + 输出摘要」或「截图/抓包文件路径」。
>
> **⚠️ 终验前先读这一句（captain 2026-10-23 要求置于最前）**：**实现方不得拿「可能是判据问题」当挡箭牌**——必须先按 §0.3.1 的 T-1..T-10 与 D-24/D-27/D-28 逐项排除（旧产物 / 旧进程 / 缺要素夹具 / 反向 grep 无基线 / grep 计数当判据 / 坐标未归一化 / **未经实跑的现状断言** / 破坏性探针 / 认错复原对象），排除不了才算实现缺陷。越到后期越容易出现「反正可能是判据错，先放着」的松动，这条就是防它。**其对称面同样成立**：判据方认错后，实现方仍须按修正后的判据重新自证一次，不得因「上轮是假红」跳过复验。

---

## 0. 使用说明

### 0.1 前置与变量（每条命令都在此环境内执行）

```bash
cd resume-warehouse
export PY=.venv/bin/python                 # 不存在 → 该 lane 直接 FAIL（AC-ENV-01 未过）
export B=http://127.0.0.1:$($PY -c 'import json;print(json.load(open("data/runtime/app_port"))["port"])' 2>/dev/null || echo 8765)/api/v1   # 默认 8765；被占用则顺延，实际端口只认 data/runtime/app_port 的 JSON["port"]（D-03 已定版，见 ARCHITECTURE §3.3；**禁止** cat/int(文件)）
export EV=tests/.tmp/evidence/$(date +%Y%m%d)   # 证据落盘目录（ARCHITECTURE §3.2 允许的写入范围）
mkdir -p "$EV"
```

```bash
export APP=server/app            # 后端代码根（实测：server/app/**；入口 server/server.py）
export WEB=web                   # 前端根：web/index.html、web/preview.html、web/src/**
export SCRIPTS=scripts           # scripts/run.sh、scripts/bootstrap.sh、scripts/preflight.py
```

**路径口径（2026-10-23 实测，取代 ARCHITECTURE §3.2 的 `app/` 写法，见 D-15）**：后端不是 `app/` 而是 `server/app/`；前端不是 `app/templates` + `app/static` 而是 `web/` 与 `web/src/`；启动脚本在 `scripts/`。**模块导入仍是 `app.*`**（cwd 在 `server/` 或把 `server/` 加进 `sys.path`），所以 `python -m app.server` 与文件路径 `server/app/server.py` 不矛盾。凡命令里的 `server/app/...` 以 `ls` 实测为准；若 coder 再搬目录，先更新本节再判其他条目。

- 服务在跑（终验时）：`./scripts/run.sh &` ；收尾 `kill %1`。
- 证据文件只写 `tests/.tmp/`，唯一例外是 `docs/ACCEPTANCE-RUN.md` 的一行记录（`AC-xxx | PASS | <证据> | <时间>`）。
- 标注 `[auto]` 的条目，其真源是 `tests/acceptance/test_ac_*.py` 中函数名 = AC ID 小写加下划线的用例；**命令跑绿但仓库里没有对应用例 = 未通过**（判例见 §3.3 例 6）。

### 0.2 现状基线快照（本清单编写时实测，2026-10-23）

| 检查 | 现状 | 判定含义 |
|---|---|---|
| `docs/` 5 份规格 | 齐全，planner 已于 2026-10-23 02:51 二次修订（行数已变，权威顺序见 ARCHITECTURE §10） | 规格已冻结 |
| `server/app/` | **骨架已落盘**（`config/db/errors/models/repos/schema.sql` + `adapters/{egress_guard,llm_client,providers}.py` + `api/` + `services/{consent,envcheck,naming,privacy,prompts,storage}.py`）；`web/{index.html,preview.html,src}`、`scripts/{run.sh,bootstrap.sh}` 已有 | 骨架在；importer/assembler/render/analysis 等业务模块尚未落地 |
| `.venv/` | **不存在** | AC-ENV-01 当前 FAIL |
| 服务可启动 | **PASS**（2026-10-23 03:04 supervisor 独立复跑：`/api/v1/health` 200，0.7s 起来；早前 `server/app/db.py:40` `AttributeError: 'PosixPath' object has no attribute 'strip'` 已由 coder 修复） | INT-11 由红转绿，但仍作**启动硬门**保留：该故障证明「编译全绿 ≠ 能跑」 |
| `.gitignore` | **已落盘并已 `git init`**（commit `8eb2130`；`.env`/`data/`/`*.pdf` 均未入库） | CORE-09 由「补文件」转为「验证历史未污染」 |
| `.git/` | **已初始化**（1 个 commit） | 之后每次提交都要 review 是否带入 `.env`/`data/`/简历 PDF |
| `.env` | 存在，`-rw-------`(600)，9 个 `LLM_*` 键，值为空 | key 未配置，`key_set=false` |
| `data/imports/` | 2 份真实简历 PDF（zh / en_withphoto） | 隐私红线处于「实弹」状态 |
| `data/app.db` `data/files/` `data/exports/` `data/logs/` `data/runtime/` | **不存在** | AC-ENV-05 未过；端口文件将落 `data/runtime/app_port` |
| `data/profile/photo_from_zh_resume.png` | 已由 captain 提供（真实照片素材，供 t5 抽取联调） | 照片红线同 PII 等级 |
| `tests/` `skill/` `scripts/preflight.py` | **不存在** | 集成 / Skill lane 未开工；preflight 见 D-04 |
| 根目录 `scripts/set-api-key.command` | 存在（可执行，写 `.env`） | 不在 ARCHITECTURE §3.2 布局内 → 见 INT-10 / D-09 |

### 0.3 判定口径

| 记号 | 含义 |
|---|---|
| `PASS` | 命令退出码符合期望 **且** 输出匹配「期望」列 |
| `FAIL` | 任一不符；P0 出现 FAIL 即整体不通过 |
| `KNOWN-FAIL` | 仅 P1 可用，最多 2 项，必须在 `ACCEPTANCE-RUN.md` 写明原因与替代方案 |
| `N/A` | 仅限 P2 条目；需注明理由 |
| `BLOCKER` | 命中 §0.4 任一条，**不看通过率，直接整体不通过** |
| **反向判据须先验基线** | 任何**反向** grep/断言（期望「0 命中/不存在」）入册前，必须在**当前代码**上实跑一次确认基线真的是 0；没跑过的反向判据会自带假红，t11 会照着它追错人。已发生实例：`cut -c[0-9]+-` 误命中合法的 `cut -c1-8`（2026-10-23），`grep LLM_TRUNCATED docs/ → 0`（契约里本就有 11 处命中）。互补规则：**正向**断言要能指出「命中位置」，不许只写「≥1」。**为什么这条规则值得单独立项（两个理由）**：① 防假红——没跑过基线的反向断言会让 t11 追错人（`cut -c[0-9]+-` 实例）；② **更重要：它能反过来抓出「实现与自述的口径漂移」**——2026-10-23 巡检时 `grep "学校名.*占位符" server/app/` 命中 `consent.py:445`，直接暴露出「ConsentModal 承诺校名脱敏、实际 payload 发真校名」的隐私声明矛盾（**D-17**）。第②个理由比第①个更能说服人：假红只是浪费一轮，口径漂移是**向用户撒谎**。。**延伸（2026-10-23 由 IMP-13 教训补）**：不只有反向判据——**正向判据也不得硬编码会被上游文件改动的数字**（例：基准文件从 32 串修正为 30 串，写死「32/32」立刻假红或假绿）；条数一律取文件实测（`len(fx[...])`），并给基准加自检（无重复、无 `len<=1` 伪判据）。**同步**：planner 已把同一规则写进 `docs/ACCEPTANCE.md` §12.1 末尾（两处口径一致，勿再各自演化）。**执行细节**：反向 grep 必须带 `--exclude-dir=__pycache__ --exclude-dir=.git`，并排除清单自身（`--exclude=docs/maintainers/REVIEW-CHECKLIST.md`）——`.pyc` 是二进制会命中、清单里的示例文本会自命中，两者都会让「期望 0」变成假红 |

| **SENT-BUT-UNUSED（净损失缺陷）** | **字段进了 payload，就必须能指出消费它的 schema 字段或 prompt 维度**；只发不用＝隐私成本已付、分析收益为零，属**净损失缺陷**，与「发错了」同等严重（用户 2026-10-23：「校名是判定竞争力的核心依据之一」——发而不用等于白付隐私代价）。查法：① 对 payload 里每个字段点名消费者（`school` → `competitiveness.school_tier`/`school_signal`；`requirements[]` → `candidate_status`）；② 两侧都无人引用 → **FAIL**。已发生实例：校名曾进 payload 但分析 schema 无字段消费（**D-19**，由 `ADR-20`/API §6.1 修复）。**注意**：grep 命中数只是冒烟（`prompts.py` 2026-10-23 03:17 实测已 **18 命中/120 行**，此前「0 命中」是旧快照），**真正的判据是行为断言**（ANL-07 断言 `competitiveness` 非空且含校名/层次词；ANL-08 断言 B 例 `hard_filter=false`） |

| **引用 AC 必须连优先级一起校验** | 清单里引用的 AC ID 必须在 `docs/ACCEPTANCE.md` **条款区（§14 之前）存在**，且**引用的优先级与条款优先级一致**；只查「ID 是否存在」抓不到本类错——实例：`UI-10` 引用 `AC-PDF-12`，该 ID 存在但指的是 **P0 两页兜底**，P2 打印版式已改号为 `AC-PDF-20`（captain m03115）。**注意**：条目自身的 `P0/P1` 是**本清单的执行优先级**，不等于被引用 AC 的优先级，两者不同不是缺陷；只有**明确给这条 AC 标了错优先级**才算。查法：抽取行内所有 AC ID + 同行 `P[012]` → 与条款区优先级表比对，命中差异逐条人工确认。 | 

| **grep 计数不作判据（只作冒烟）** | **`grep -c` 会随实现进度自行变绿/变红，它证明不了任何行为**。因此判据必须落在**行为/结构断言**上：返回值非空、字段 ∈ 枚举、`evidence` 可溯源、字节序/哈希相等。grep 计数只允许出现在「冒烟」位置（先看一眼有没有人写），**不得写进「期望」列作通过条件**。双向实例（2026-10-23）：① **假红**——`cut -c[0-9]+-` 误命中合法 `cut -c1-8`；② **假绿**——captain 要求「`prompts.py` 的 `school\|院校\|竞争` 修完 ≥3」，而入册时实测已 18 命中/120 行，照写立刻变绿，会把「已实现」当「待修」放过去（比假红更危险：假红只浪费一轮，假绿会让终验给出错误结论）。**替代写法**：`grep` 用于定位，判定改用响应 JSON 的字段断言（如 ANL-07/ANL-08 的 A/B 例）。 |

| **夹具缺失 = `SKIP(no-fixture)`，不得记 PASS** | fixture 不在仓库时，条目既不能记 PASS（「没测」会被算成「测过且通过」），也不能记 FAIL（会把缺料算成实现错）。统一记 **`SKIP(no-fixture)`** 且必须写进终验报告；夹具补上后立刻转可验并补跑。实例：IMP-07 曾因缺 docx/html/pdf 记 `BLOCKED(no-fixture)`，2026-10-23 03:36 夹具补齐后 5/5 转 PASS。 |

#### 0.3.1 判据陷阱台账（历史假红/假绿，新增判据前必读）

> 每一条都真实发生过，且都**差点冤枉实现方**。新增任何判据前先扫一遍这里。

| # | 陷阱 | 现象 | 正确做法 | 假 FAIL 的归属 |
|---|---|---|---|---|
| T-1 | **读取旧产物**（stale artifact） | `data/exports/*.json` 早于代码 2 分钟，`sections[].heading` 全 `null`、`numbers_lost_unknown` 残留 → 报 25 项 hard_fail | 产物必须与代码同版本重生；或直接从 API 取实时数据（CMP-26 即这么改的） | **归流程方（captain/产物生成方）**，不记 coder **第三次实例（2026-10-23 04:43）**：拿 04:38:37 的 PDF 判 i18n 三版并存，而 `i18n.py` 04:41:55 已改对 → 已由 **INT-26** 制度化「先比产物 mtime」。 |
| **T-1b** | **数据状态断言不带时间戳**（活数据会过期，captain m01859 自我执行条款） | 拿两分钟前的库快照报「6 个模板全是 `is_default=0`」，实际 04:01:29 已被清理并设好默认 → 误报 D-36 | **格式**：「截至 `HH:MM:SS`，`SELECT …` 返回 …」；凡涉「库里现在没有/全是/只有」的结论，**发送前必须再跑一次同一条查询**；两次结果不同 → 只报「我观测到的变化」，**不报「现状是 X」** | **归判据方/发信方**（captain 亦适用）。理由：代码/文档改动有 mtime 可查，而**数据状态是唯一「你查的时候是对的、也会在几十秒内被别的 agent 改掉」的对象** |
| T-2 | **打在旧进程上**（stale process） | `pid 46958` 是改代码前起的、Python 不热重载 → 「`job_id` 缺失 / `PHOTO_DETECTED` 缺失 / `width=None`」全是假 FAIL；换新进程后同一请求全通过 | 行为验证前先确认进程跑的是当前代码：`/health.build` vs `git rev-parse --short HEAD` + dirty 标记（见 **INT-15**） | **归判据方/流程方**（拿旧运行态判新代码） |
| T-3 | **夹具本身缺要素** | 用纯文本 `sample.pdf` 验 `PHOTO_DETECTED` → 报「缺失」，但那张 PDF 根本没有图 | 判照片相关条目必须用带图夹具（`sample_with_photo.pdf`）；夹具缺要素记 `SKIP(no-fixture)` | **归夹具作者**，不记 coder |
| T-4 | **反向 grep 没跑基线** | `cut -c[0-9]+-` 误命中合法 `cut -c1-8` | 反向判据入册前必须实跑、确认基线 0 | 归判据方（supervisor） |
| T-5 | **grep 计数当判据** | 「`prompts.py` 修完 ≥3」入册时已 18 命中 → 假绿 | grep 只作冒烟，判据落行为断言 | 归判据方（supervisor） |
| T-6 | **坐标未归一化** | pdfplumber `im["top"]` 相对 MediaBox → 3.82 被量成 -4.01；98.42 被当成右边距 | `top_norm = im["top"] − page.bbox[1]`；右缘 = `page.width − x1` | **归判据方（supervisor）** |

| T-7 | **未经实跑的「现状」断言** | 契约方读代码后断言「`DELETE /profile/photo` 返回 204 且无 body」→ 实际 **200 + 六个字段**（planner 2026-10-23 踩到，captain 复现） | 写「现状/实现如何」必须附**命令 + request_id + 响应片段**；拿不出就只能写「**未验证**」，不得写成事实 | 归**断言作者（planner/评审方）**，不记 coder |
| T-9 | **探针破坏真实数据** | 为确认 `DELETE` 语义，对**真实** `user_profile` 打了 `DELETE /profile/photo` → 用户 `photo_path` 被清空 | **探针纪律 A**：验证端点存在性/参数校验只走非破坏路径（`GET`、故意缺参拿 4xx、`--dry-run`）；`DELETE`/`PUT` 之类写操作只在临时 `DATA_DIR`（`tmp/testdata_*/`）或测试库上做 | 归**探针作者（验证者）**；若已污染真实数据 → 属数据事故，按实测后果记账 |
| T-10 | **复原时认错对象** | 复原照片时按「第一个匹配到的文件」选，先选中自己的合成夹具（459B），第二次才对 | **探针纪律 B**：复原前先核对**目标身份**（大小 / sha256 / 来源路径 / mtime），不得只按名字或第一个匹配项复原 | 归**探针作者（验证者）** |
| T-11 | **自造调用形态**（wrong call shape） | 把 `str` 传给 `Iterable[str]` 形参 → 按字符迭代 → 静默返回「未出现」；我据此判 ANL-10 FAIL 是假 FAIL | 先按**真实调用路径**传参（`company_analysis.py:71` 传列表），并跑「`[text]` vs `text`」对照；不一致就记判据缺陷 | **判据方（supervisor）** |
| T-12 | **正面实例：执行方自曝并回滚破坏性操作**（captain m02371/m02426） | 脚本误硬删 16 条 draft 后，coder 走完**四步**：① 自曝（主动上报，不等判据发现）② 快照回滚（apply 前整库快照，md5 `bd2b7b4c3cd3d6e76d1086b126ca63e6`）③ 拆参数（硬删拆到 `--delete-drafts`，有候选时先打印「N 条重复草稿未动」）④ 加护栏（默认只做可恢复动作 + 两类计数） | 与 T-2/T-3（判据方认错）并列：**认错要记账，但账分两栏——事实（D-47 发生了）与处置（处置是对的）**；处置做全不抵消事实，事实也不抹掉正面。四步缺一 → 仍记 coder 缺陷；**处置合格不改变事实的严重等级**（回滚干净不等于没出事，D-47 仍按 P0 记） | 四步缺一仍记 coder；做全记正面。复验：`git log --oneline \| head -3` 见拆参数提交、快照 md5 一致、`grep -n '将删除\|将软删' scripts/*.py` ≥2 |
| T-1c | **结论时效**（stale conclusion） | 实测 04:15:09、代码 mtime 04:15:24 → 发出时结论已过期（本轮实例：ANL-10「偏好被判成门槛」在发出时已被 coder 修掉） | 距实测 >60 秒且 `ls -lT` 晚于实测时，**发送前必须重测**；做不到就写「截至 HH:MM:SS 为 X」 | **判据方（supervisor / 报缺陷的任何一方）** |
| T-13 | **只读了构造行、没读函数尾部**（partial-function read） | 判「`httpx.Client(...)` 自建却没关」时只看了 `fetch_client.py:306-307` 的构造，没看 `:422-424` 的 `finally: if owns_client: http.close()`，把**已正确释放**的代码报成 D-50 假报；同类还有 `sqlite3.connect` / `open()` / `subprocess` | 判「缺 try/finally / 缺 close / 缺回滚」类缺陷，必须**读完整个函数体**，并在条目里贴**函数起止行号 + 结尾 5 行原文**；只贴构造行 = **未验证**，不得记 PASS/FAIL | **supervisor**（判据方自身缺陷） |
| T-14 | **容差桶被第三方行为满足**（tolerance bucket launder） | INT-27 第 3 档允许「纯 fd 的 `name=N`」存在，理由是 werkzeug/reportlab 内部；但这条容差**也可能被我们自己的代码满足**——一旦有人用 `open()` 后不关、只留下 fd 型 warning，就会躲进「第三方」这个桶里，看总量永远判不出来 | 任何容差桶必须**能证明「我们自己为零」**：要么按路径/模块名过滤（本条的 `name='…'` 带路径才计我们），要么声明「此桶不参与通过判定」。**允许的容差不得进入通过条件的分母** | **supervisor**（判据方设计出可被绕过的桶） |
| T-15 | **判据工具自身引入假象**（tool-induced illusion） | `--virtual-time-budget` + `--screenshot` 做页面走查：虚拟时间冻住/越过真实加载 → 得「3 页正常 / 2 页空白」，真相是 **7 页全死**（CSP 拦掉 `web/index.html:49` 内联启动脚本，CDP 日志 `source=security … script-src 'self'`）。**工具的可信度也是判据的一部分** | 页面类判据只认「CDP `Log.entryAdded` + 真实等待 + `#view` `innerText` + CSP 违规数」；发现「部分正常」时先怀疑工具 | **captain**（方法）+ **supervisor**（引用未复现） |
| T-16 | **重算只核「已变化项」**（空转当收敛） | `scripts/recompute_jd_links.py` dry-run：六条只补 1 条、其余五条不变、`outbound_calls=0`、快照齐备——流程全部合规，但证据源没接 `skills_json`，用户看到的仍是「未体现 SQL/Python」。 | **合规的流程 + 空的证据源 = 看起来跑过了，其实什么都没修**；比「没跑重算」更难发现。 | 重算类修复必须同时核对「**应当改变而未改变**」的清单（预期应命中 → 重算后仍为空），把它作为未完成项单列；只核「已变化」即判 FAIL。；**归属**：判据方（只核已变化 → supervisor）；实现方（证据源未接 → **coder**） |
| T-17 | **指令与环境冲突时静默降级**（instruction-environment conflict） | 指令「只软归档」，但 `resume_build` 无归档列；执行方自行换成物理删除并跑了两轮（第二轮还用 `--ignore-name`） | **不可逆损失**（31 构建 + 29 产物 + 79 选题行），且执行方与下指令方**都不觉得自己违规**——因为「活干完了」 | 冲突时**停下回报**，附「我能做的两种方案 + 各自代价（可逆性 / 影响行数 / 恢复方式）」，由下指令的人改判；归属：**静默降级 → 执行方；下了不可能执行的指令 → 下指令方**（本例两边都占） |
| T-18 | **列名/字段名凭记忆写判据脚本**（schema guessing） | `jd_requirement` 真实列是 `skill`，脚本写成 `.text` ⇒ 第 74 行 `sqlite3.OperationalError: no such column: text`，**C2b/C2c/C3/C4 全部没跑**，看起来「脚本红了」其实「判据没成立」。同一列名坑 captain 与我各踩一次 | 判据不成立 → 结论无效；若只看「有输出」会误以为在判实现 | 写脚本前先 `pragma_table_info(t)` 打印真实列名并回填；**脚本必须在每段后打印结果且不允许中途崩**（每段独立 `try/except`，异常记该段 ERROR）；归属：**写脚本的一方**（本例 supervisor） |
| T-19 | **入册的 fence 与实际跑的脚本不是同一份** | §A.1 首版 `jd_requirement.text` 崩在 C2b 前，我在本地跑的是修好后的临时副本，而 `docs/maintainers/REVIEW-CHECKLIST.md` 里的代码块先落了没跑过的旧版；captain 抽取时拿到的正是旧版，重现 `no such column: text` | 「我跑过」与「入册的那段跑过」是两件事；读者按文件复制必然踩坑，且会把「脚本崩」误读成「实现红」 | 改脚本后必须**从文件里按原文抽出**再跑一次（`sed -n`/`python -c` 抽取 → 执行 → 记退出码），而不是跑临时副本；归属：**supervisor**（本例） |

**§0.3.1a「时点」是判据的强制字段（T-1 升级，三次实例后定规；captain 2026-10-23 04:1x）**

任何「现状 / 实测」结论，**必须同行附时点**，否则一律记 `未验证`，**不得记 PASS/FAIL**：

| 结论类型 | 时点凭证 |
|---|---|
| 文件/代码类 | `ls -lT <path>` 或 `git log -1 --format=%h\ %ci -- <path>` |
| 数据类（库/表/行） | 查询时间戳 + 原样 SQL（「截至 HH:MM:SS，`SELECT …` 返回 …」） |
| HTTP/API 类 | 响应里的 `request_id` + 服务器时间 |
| 产物类（PDF/JSON） | 产物 mtime **与** 生成它的代码 mtime（两者先后即是判据） |

**自查问句（贴在每条判据前）**：「**我这次跑的代码/数据，是不是比我要判的东西更早？**」

三次实例（都是「对了但过期」）：① D-24 用 `data/exports/*.json` 旧产物判 coder；② D-36 用 03:5x 的 `template` 快照报缺陷，重查后改判「已消解」；③ ANL-09 拿改代码前的行为当现状（**supervisor 自己的错**）。违反 → 归 **判据方（supervisor）**，不看结论对不对。

**假证据来源（终验一次自检清单，captain 2026-10-23 要求汇总到同一节）**：t11 开始前逐条排除，任一条成立时**不得**用该结论判实现缺陷——

1. **旧产物**（D-24 / T-1）：导出件或草稿的 mtime 早于相关代码 → 先重生再判。
2. **旧进程**（D-27 / T-2）：`/health.build` ≠ `git rev-parse --short HEAD`(+dirty) → 记 `BLOCKED(stale-process)`（INT-15）。
3. **缺要素夹具**（T-3）：夹具本身没有待验要素（如纯文本 PDF 验照片）→ 记 `SKIP(no-fixture)`，换夹具。
4. **破坏性探针**（T-7/T-8）：写操作打在真实数据上、或复原认错对象 → 先恢复真实数据再判，且该轮结论作废。
5. **陈旧端口文件**（D-26）：`app_port` 指向的 pid 已死或端口不可连 → 看 `lsof` 实况，不看文件（INT-16）。
6. **未经实跑的「现状」断言**（T-7）：任何「实现返回 X」的结论若无命令+响应片段 → 视为未验证，不得据此判 FAIL 或 PASS。

**对称面（同样必须遵守）**：判据方认错后，实现方**仍须按修正后的判据重新自证一次**，不得因为「上次那条是假红」就跳过复验；反过来，实现方也不得拿「可能是判据问题」当挡箭牌——先逐项排除 T-1..T-10 与 D-24/D-27/D-28，排除不了才算实现缺陷。（IMP-04 是正面样本：假红澄清后 coder 重新自证三条断言才转 PASS。）

**总原则（captain 2026-10-23 认可并推广）**：**判据错要能追到判据作者**。由旧产物（T-1）、旧进程（T-2）、缺要素夹具（T-3）造成的假 FAIL，一律归**判据方或流程方**，不得让实现方背锅；判据作者有义务在条目里预写这条归属，而不是等误判发生后临时解释。

#### 0.3.2 测试纪律（临时库与探针，2026-10-23 captain 实测补充）

1. **临时库位置只能是 `data/.tmp_xxx/`**：`server/app/db.py:48` 把 `DATA_DIR` 钉死在 `resume-warehouse/data/` 之内，指向 `tmp/` 会直接启动失败：
   `RuntimeError: DATA_DIR 必须位于 .../resume-warehouse/data 之内，实际解析为 .../resume-warehouse/tmp/testdata_del（拒绝在项目外落盘）`。所以别写 `tmp/testdata_*`。
2. **临时库要先把 profile 建起来**：空库里调照片端点点会先撞 `422 VALIDATION_ERROR「首次填写资料必须提供姓名」`（不是端点坏了）。正确顺序：`PUT /profile {"name_zh":"测试","school_zh":"测试大学"}` → 再 `POST/PUT/DELETE /profile/photo`。**注意字段名是 `school_zh`**（`school` 会报 `extra_forbidden`）。
3. **探针纪律 A/B**（§0.3.1 T-9/T-10）：`DELETE`/`PUT` 只在临时库跑；复原前核对目标身份（大小/sha256/来源路径/mtime）。
4. **`DELETE /profile/photo` 的契约形状（2026-10-23 03:45 实测）**：**200**（不是 204），body 六字段 `{cleared, previous_photo_path, previous_attachment_id, photo_url, note, restore_endpoint}`；撤销 = `PUT /profile/photo` 传 `previous_attachment_id`（或 `sha256`）。

#### 0.3.3 判据自身的准入纪律（supervisor 自身缺陷沉淀，2026-10-23）

1. **凡是要给人复制执行的 fence，入册前必须「按原文抽取」实跑一次**。抽取方式：从 markdown 原文取 fence 内容 → 去掉容器缩进（若 fence 在列表项内）→ 原样执行；不是「我写过所以我知道它能跑」。
2. **已知失效模式（都真实发生过）**：
   - **列表缩进**：fence 嵌在 `- ` 列表项里，每行带 4 空格，复制到终端 → `IndentationError: unexpected indent`（X-A7 实例，已移入 §2.1.1 顶格小节）；
   - **输出过期**：脚本对「当时的数据/环境」写的期望值，环境一变就假红或假绿（`prompts.py` 命中数、`expected_zh_v10.json` 条数）；
   - **单样式解析漏项**：只认 `` `GET /path` `` 一种写法，会漏掉「方法一栏 + 路径一栏」的两栏表格，导致 REV 假高、FWD 假低（§16 实例；历史三方数字见 §2.1.2，**现已由 `scripts/check_route_parity.py` 定稿：`only_in_code=0 / only_in_docs=43`**）。
3. **数字类基线必须带三要素**：口径（怎么算的）+ 日期 + 可重跑命令；判据本身被修改后必须重算并在台账记「旧值 → 新值 + 原因」。
4. **数字类基线必须能指到一个「可复现入口」**（唯一权威脚本的**路径 + 命令行**），否则只能记 **`PENDING(canonical-script)`**，不得写死数字。原因：路由一致性这类指标有四个未定义自由度——① 什么算一条路由；② 路径参数如何归一化（`{id}` / `<int:id>` / `:id`）；③ 一格两条路由怎么算；④ `methods=["GET","POST"]` 算一条还是两条。每份脚本各选一套 → 数字不可比（2026-10-23 实例：planner 39/18、supervisor 20/46、captain 21/31，三方都自洽）。**判定改为「三方跑同一脚本、JSON 逐字节相同」**。
5. **判据脚本自己也要被断言**（captain m01695 实证，X-A10）：一个**不能被自身不变量验证**的判据，只是换了个来源的猜测。任何「计数型」脚本必须内部自证：`len(matched)+len(fwd) == len(documented_unique)`、`len(matched)+len(rev) == len(code_unique)`、`set(rev) ∩ set(fwd) == ∅`；任一不成立就**非零退出并打印矛盾明细**，不许打印一个「看着精确」的数。实例：`scripts/check_route_parity.py` 首次落地输出 `{code:64, documented:108, fwd:64, matched:64, rev:231}`——64+64=128 ≠ 108、64+231=295 ≠ 64，**两组不变量同时破**，却仍打印完整报告。
6. 违反本条 = **supervisor 自身缺陷**，与实现缺陷同等记账（写进 §5 台账，归属 supervisor）；若写死了未经权威脚本产出的数字（如 231/64 这一套），同样记 supervisor 缺陷。

> **2026-10-23 回执（captain m01695）**：`scripts/check_route_parity.py` 已落地，但**首次实跑即自相矛盾**（`code=64` 而 `rev=231`；`fwd=64` 与 `matched=64` 同时成立），两条内部不变量同时破 → 按 **X-A9** 判 **FAIL**、退回 coder。**因此本节与 §16.1 的 `PENDING(canonical-script)` 状态不变，禁止用 `231/64` 这一套数字重算基线。**

#### 0.3.4 写入路径的「半成品」纪律（captain m01661 推广）

凡「先写库、后写文件」或「先算后写」的双动作路径，必须满足：

1. **顺序不可观察**：要么先查引用再删行再 unlink（`DELETE /files` 的修法），要么写文件成功后一次事务落库；
2. **失败不留一半**：任一步抛错都不得留下「行没了文件还在」「文件在但无引用」这类状态，且该状态必须可被检测（日志/断言/修复脚本）；
3. **复验必须构造中途失败**：用 monkeypatch 让 `unlink()` / 文件写入 / DB commit 抛错，断言最终状态一致（全成或全不成）。
4. **删除类操作：先完成所有校验，再做不可逆动作**（captain m01756 提炼自 `DELETE /files`）。顺序必须是「**先查引用 → 再删行 → 最后 unlink**」；反序的后果是「中途抛异常留下孤儿」，更糟的是「先 unlink 再发现被引用，照片就永久没了」。**任何「先删后查」的实现，即使守卫逻辑本身正确，也记 coder 缺陷。**
5. **同样适用于批量清理脚本**（captain m01808 补充，如 `prune_probe_data.py`）：必须**默认 `dry-run`**、先输出「**将归档 N / 保留 M**」报告，只有显式 `--apply` 才写；`--apply` 前必须打快照。**默认就写库的清理脚本一律记 coder**（属数据安全，不属工具便利）。

适用：照片保存（`profile/photo_*`）、附件上传、导出产物落盘 + `build_artifact`、删除附件。**只测成功路径的写法一律算覆盖不足**（D-35 就是「只验真值路径」的同类）。

> **警告码计数口径（2026-10-23 captain 复核）**：`§14.1` 机械命令命中 **37 行**，其中 1 行是合并写的 `NAMING_SANITIZED / NAMING_TRUNCATED / NO_VARIABLE / NAMING_COLLISION_SUFFIXED`（按 4 条计）→ **36 + 4 = 40**，与表头「37 行 + 折算 3」自洽。**不要按行数 40 去 grep**，会得到假红；新增合并写法时必须同步改表头「折算 N 条」。

**通过门槛（同 ACCEPTANCE §0）**：P0 100% PASS；P1 ≤2 项 KNOWN-FAIL；BLOCKER 出现即 FAIL。

**反向判据基线巡检（2026-10-23 03:1x，supervisor；挑最可能误伤的 7 条实跑）**：

| 判据 | 实测 | 结论 |
|---|---|---|
| `grep -rn "张三\|示例大学" server/app/` → 0 | **0** | 基线干净，可用 |
| `grep -rn "sample_resume\|data/imports" server/app/` → 0 | **8**（全为注释/docstring 里描述路径；另有 `__pycache__/*.pyc` 二进制命中） | **不会误伤**，但命令必须加 `--exclude-dir=__pycache__`；且 `consent.py:445` 文案有真问题 → **D-17** |
| `grep -rn "setInterval" web/src` → 0 | **0** | 可用 |
| `grep -rn "app/static\|app/templates" docs/ARCHITECTURE.md` → 0 | **1**（`:266`） | 不是假红，是 planner 漏改 → **D-15** |
| 截断/空内容组合反向 grep → 0 | **2**（均在**本清单自身**） | 必须 `--exclude=docs/maintainers/REVIEW-CHECKLIST.md`，否则自命中 → 已在 D-14 注明 |
| `grep -rn "https\?://" web/ \| grep -v 127.0.0.1` → 0 | **2**（`www.w3.org/2000/svg` 命名空间 + `placeholder="https://…/v1"`） | 无害；命令须白名单 `w3.org` 与 `placeholder=` |
| `grep -rn "${K: -4}" ...`（key 末四位）→ 0 | 见 INT-12 | `cut -c[0-9]+-` 会假红，已改 |

### 0.4 一票否决清单（BLOCKER，终验开始前先扫一遍）

| # | 条件 | 检测位置 |
|---|---|---|
| BLK-1 | 存在非 `llm_client` 的**上行外发**（把任何用户数据发往非 LLM 端点：遥测、CDN、运行时 pip/npm 安装、抓取口径把用户字段带出去） | CORE-10 / X-C1 / INT-08 |
| BLK-2 | `data/**` 的字节 / **姓名、电话、邮箱** / **照片**出现在任何 `llm_preview.payload_json` 或抓包 body 中（**学校名按用户 2026-10-23 最终口径允许真实发送，不在本行**）；**含导入草稿 `blocks[header]` 的姓名/电话/邮箱被整体序列化进 payload** | X-F6 / X-F8 / X-F9 / **X-F13** |
| BLK-3 | API key 明文（含后 4 位）出现在任何响应/日志/DB 表 | CORE-11 |
| BLK-4 | 存在绕过 consent 的 LLM 调用路径（无需 `preview_id` 即可 complete） | X-F1 / X-F3 |
| BLK-5 | 中文 PDF 缺字 / 出现 `\ufffd` / 汉字被映射成康熙部首 | CMP-06 / X-D2 |
| BLK-6 | 产出残缺文件名（`-示例大学.pdf`、`数据分析实习生--示例大学.pdf`、`undefined.pdf`、含 `..`） | CMP-13 / X-E3 |
| BLK-7 | 未落 `.gitignore` 就 `git init` / `git add`（`.env` 或简历原件进历史） | CORE-09 |
| BLK-8 | P0 条目任一 FAIL | 全局 |
| BLK-9 | `fetch_client` 越界：非 GET、URL query 或请求体携带任何用户字段、目标不在白名单、用户关闭后仍发请求 | X-C6 |
| BLK-10 | **服务起不来 / 端口撒谎**：启动即异常、15s 内 `/api/v1/health` 不到 200、`app_port` 不是 JSON 或缺五字段、或**三值不一致**（实际监听端口 ≠ `health.data.port` ≠ `app_port.port`） | INT-11 / INT-13 |

### 0.5 lane ↔ 任务 ↔ owner ↔ 本清单章节

| lane | 任务 | owner | 章节 | 交付物 |
|---|---|---|---|---|
| core | t4 | coder | §1.1 | `server/app/`、`scripts/preflight.py`、`scripts/run.sh`、`.gitignore`、DB、错误信封、`adapters/llm_client.py`（上行）+ `adapters/fetch_client.py`（下行） |
| import | t5 | coder | §1.2 | `server/app/services/importer.py`、imports/templates API |
| package | t6 | coder | §1.3 | warehouse 服务、packages/variants API |
| analysis | t7 | coder | §1.4 | `jd_analyzer.py`、`company_profiler.py`、匹配打分 |
| compose | t8 | coder | §1.5 | assembler/naming/render_*/textcheck |
| ui | t3 | uier | §1.6 | `web/`、`web/src/` |
| skill | t9 | coder | §1.7 | `skill/SKILL.md` + `cli.py` |
| 集成 | t10 | coder | §1.8 | 全链跑通 + `docs/ACCEPTANCE-RUN.md` |
| 规格 | t1/t2 | planner / supervisor | §2.7 | 5 份 docs + 本清单 |

### 0.6 lane 完成的通用定义（DoD 骨架，每个 lane 都必须**全部**满足）

1. **交付物齐**：该 lane 表格列出的文件/端点全部存在，且落在 ARCHITECTURE §3.2 声明的路径内（无越界新建目录）。
2. **自动化全绿**：该 lane 的 `[auto]` 条目对应测试函数存在且 `pytest -q` 全绿（不是「手点通过」）。
3. **手工证据落盘**：标注「手工」的条目有截图/抓包，文件名含 AC ID，存 `$EV/`。
4. **记录行已写**：`docs/ACCEPTANCE-RUN.md` 每个 AC ID 一行，含命令与时间。
5. **零 open BLOCKER**，且本 lane 相关的跨 lane 核对项（§2）全绿。

一条 lane 只有满足 1–5 才可标记 `completed`。缺任意一条 = `needs_revision`。

---

## 1. 逐 lane DoD

### 1.1 CORE（t4，owner: coder）— 骨架 / 数据层 / 错误信封 / LLM 适配

**入口条件**：`docs/` 5 份规格就位。**出口条件**：`./scripts/run.sh` 在断网下起得来，`GET /api/v1/health` 200，`.gitignore` 已就位且未污染 git 历史。

- [ ] **CORE-01 解释器与依赖齐全**（AC-ENV-01，P0）
  - 命令：`$PY -c "import flask, pydantic, jinja2, reportlab, pdfplumber, pypdf, docx, markdown, httpx, bs4"`
  - 期望：`exit 0`；无 `ModuleNotFoundError`。当前 FAIL（`.venv` 不存在）→ 归属 coder。

- [ ] **CORE-02 preflight 体检**（AC-ENV-03，P0；D-04 已裁定：`scripts/preflight.py`，`server/app/` 只放应用代码）
  - 命令：`$PY scripts/preflight.py | $PY -m json.tool > "$EV/AC-ENV-03.json"; echo $?`
  - 期望：`exit 0`；JSON 含 `python.version` / `deps[]`（name,ok,version）/ `fonts[]`（family,path,ok）/ `engines.{reportlab,chrome,soffice}.{ok,reason}` / `ports` / `ollama.reachable` / `data_dirs` 七个顶层键；`engines.reportlab.ok == true`。

- [ ] **CORE-03 离线启动链**（AC-ENV-02，P0）
  - 命令：`grep -nE "(^|[;&|] *) *(pip3?|npm|pnpm|yarn) +(install|i|add|download)" scripts/run.sh server/app/*.py 2>/dev/null; echo "rc=$?"` → 期望无命中。再断网实测：`sudo ifconfig en0 down` 后 `./scripts/run.sh`（或系统偏好里关 Wi-Fi）。
  - 期望：grep 零命中；断网下打印 `http://127.0.0.1:<port>` 且 `curl -s $B/health` 200。

- [ ] **CORE-04 health/env 信封**（AC-ENV-04、AC-ROB-03，P0）
  - 命令：`curl -s $B/health | $PY -m json.tool; curl -s $B/env | $PY -c "import json,sys;d=json.load(sys.stdin);print(sorted(d['data'].keys()))"`
  - 期望：`ok:true` + `request_id`；`data.status ∈ {ok,degraded}`；`degraded` 时 `warnings[]` 每条含 `code/message/hint`；env 顶层含 `python/venv/packages/fonts/render/llm/paths/warnings`。
  - ⚠️ `warnings` 的元素形态两处文档不一致 → D-10，以 §14.1 的对象形态判定。

- [ ] **CORE-05 只监听 loopback + 端口顺延可追溯**（AC-ENV-07，P0；D-03 已裁定：被占用则顺延，实际端口落 `data/runtime/app_port`）
  - 命令：
    ```bash
    P=$($PY -c 'import json;m=json.load(open("data/runtime/app_port"));assert {"port","host","url","pid","started_at"}<=set(m);print(m["port"])')
    echo "port=$P"; lsof -nP -iTCP:$P -sTCP:LISTEN | tail -n +2
    curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:$P/api/v1/health"
    ```
  - 期望：`data/runtime/app_port` 是 **JSON 五字段**（`port/host/url/pid/started_at`，允许多键、不许少键，D-03 已定版 → ARCHITECTURE §3.3），`json.loads(...)["port"]` 为**整数**且 `url.endswith(":"+str(port))`，**不是**「内容为单个整数」（旧口径作废，照旧写会把正确实现判红）；该端口**确实在监听**且 health 200；监听地址只出现 `127.0.0.1:<port>`，**不出现** `*:<port>` / `0.0.0.0:<port>`。**不再**断言「端口占用则启动失败」（旧口径作废）。
  - 反向验证顺延：先 `python3 -m http.server 8765` 占住默认端口再 `./scripts/run.sh`，期望 `app_port` 变成下一个空闲端口且服务可用、`scripts/run.sh`/Skill/启动横幅读同一文件。

- [ ] **CORE-06 数据目录与 schema 自举**（AC-ENV-05、AC-LOC-03，P0）
  - 命令：`ls -d data data/files data/exports data/logs data/runtime && sqlite3 data/app.db "pragma journal_mode; select value from app_setting where key='schema_version';"`
  - 期望：五个目录存在（含 `data/runtime/`，端口文件落这里）；`journal_mode = wal`；`schema_version` 有值（≥1）。

- [ ] **CORE-07 统一错误信封 + request_id**（AC-ROB-02/03，P0）
  - 命令：`curl -s -X POST $B/packages -H 'Content-Type: application/json' -d '{bad json' | $PY -m json.tool; curl -s -o /dev/null -w '%{http_code}\n' $B/nope; curl -sI $B/health | grep -i x-request-id`
  - 期望：非法 JSON → 400 + `{ok:false,error:{code:"BAD_REQUEST",...},request_id}`；未知路由 → 404 `NOT_FOUND`；响应头与 body 的 `request_id` 一致；**body 不含 traceback**。

- [ ] **CORE-08 错误码覆盖 ≥ 契约 §14**（P0，契约一致性）
  - 命令：
    ```bash
    sed -n '/^## 14\./,/^## 14\.1/p' docs/API-CONTRACT.md | grep -oE '^\| `[A-Z_]+`' | grep -oE '[A-Z_]{3,}' | sort -u > /tmp/doc_codes.txt
    grep -rhoE '"[A-Z][A-Z0-9_]{2,}"' server/app/ | tr -d '"' | sort -u > /tmp/code_codes.txt
    comm -23 /tmp/doc_codes.txt /tmp/code_codes.txt
    ```
  - 期望：`comm` 输出为空（契约里的 37 个错误码在代码里都有常量）；`wc -l < /tmp/doc_codes.txt` ≥ 37。

- [ ] **CORE-09 `.gitignore` 先于 `git init`**（AC-LOC-05，P0，**BLK-7**）
  - 命令：
    ```bash
    test -f .gitignore && for k in 'data/' '.venv/' '.env' '*.pyc' '__pycache__/'; do grep -qxF "$k" .gitignore && echo "ok $k" || echo "MISSING $k"; done
    test -d .git && git check-ignore -v data/app.db .env && git log --oneline -- .env | head
    ```
  - 期望：五个键全部 `ok`；若已有 `.git`，`check-ignore` 命中且 `git log -- .env` **零输出**。当前 `.gitignore` 不存在 → FAIL，且在 `.git` 出现前必须修复。

- [ ] **CORE-10 上行唯一出口 = llm_client；下行 fetch_client 另判**（AC-PRIV-10，P0，**BLK-1**）
  - **口径（captain 2026-10-23 裁定，取代「任何非 llm_client 网络调用即违规」）**：出网分两个方向——**上行（携带用户数据）唯一出口 = `server/app/adapters/llm_client.py`**；**下行（只下公开网页、不携带任何用户数据）= `server/app/adapters/fetch_client.py`**。
  - 命令：
    ```bash
    # 上行：除 llm_client / egress_guard / fetch_client 外，任何模块直接联网都算越界
    grep -rnE "import (httpx|requests)|from (httpx|requests)|urllib\.request|urlopen|socket\.connect" server/app/ --include=*.py \
      | grep -vE "^server/app/adapters/(llm_client|egress_guard|fetch_client)\.py:" ; echo "uplink_rc=$?"
    # 下行：fetch_client 只允许被 JD/公司画像服务调用，不得出现在上行链路
    grep -rn "fetch_client" server/app/ --include=*.py | grep -vE "^server/app/adapters/fetch_client\.py:"
    ```
  - 期望：上行零命中；`fetch_client` 调用点只出现在 `jd_analyzer.py` / `company_profiler.py`（及其 API 层），**不得**出现在 `llm_payload`/`assembler`/`render_*`/`exporter` 等上行链路。再跑 `$PY -m pytest tests/acceptance -q -k "priv_10 or fetch_guard"` → PASS。

- [ ] **CORE-11 key 永不回显**（AC-PRIV-06、AC-LLM-05，P0，**BLK-3**）
  - 命令（用测试 key 全库全日志扫）：
    ```bash
    curl -s -X POST $B/settings/api-key -H 'Content-Type: application/json' -d '{"api_key":"sk-test-DEADBEEF"}' >/dev/null
    curl -s $B/settings | grep -c "sk-test-DEADBEEF"; curl -s $B/env | grep -c "sk-test-DEADBEEF"
    grep -rIl "sk-test-DEADBEEF" data/ .env ; ls -l .env
    ```
  - 期望：两处 `grep -c` 均为 `0`；`grep -rIl` **只**列出 `.env`；`.env` 权限 `-rw-------`；`GET /settings` 只有 `key_set:true, key_field:"LLM_API_KEY"`。
  - 附：`grep -n "LLM_API_KEY" .env` 只有一行；无 `DEEPSEEK_API_KEY` 之类分裂变量。

- [ ] **CORE-12 日志无正文**（AC-PRIV-07，P0）
  - 命令：`grep -rInE "sample_resume|138-?0000|you@example\.com" data/logs/ | head -20; echo "rc=$?"`
  - 期望：零命中；`data/logs/llm-egress.jsonl` 每行只有 `field_names[]`，无 `content`/`messages` 键。

- [ ] **CORE-13 WAL 与并发**（AC-ROB-01，P0）
  - 命令：`$PY -m pytest tests/acceptance -q -k rob_01`
  - 期望：PASS；5 并发写不同表无 `database is locked`。

- [ ] **CORE-14 settings 契约**（AC-LLM-01，P0）
  - 命令：`curl -s $B/settings | $PY -c "import json,sys;d=json.load(sys.stdin)['data'];print(sorted(d));print(d['key_field'], d['allowed_hosts'])"`
  - 期望：键含 `provider/model/model_analysis/base_url/key_set/key_field/timeouts/allowed_hosts/auto_redact/ui`；`key_field=="LLM_API_KEY"`；`allowed_hosts` 由 `LLM_BASE_URL` 主机名派生；无任何 key 片段。

- [ ] **CORE-15 export-all 不含 `.env`**（AC-LOC-06，P1）
  - 命令：`curl -s -X POST $B/settings/export-all | $PY -m json.tool; $PY -c "import zipfile,json;print([n for n in zipfile.ZipFile(json.load(open('$EV/exportall.json'))['data']['path']).namelist() if n.endswith('.env') or '/.env' in n])"`
  - 期望：返回 `{path,bytes,sha256}`；zip 内含 `app.db` + `files/` + `exports/`；`.env` 列表为 `[]`。

- [ ] **CORE-16 路径穿越**（AC-ROB-04）
  - 命令：`curl -s -o /dev/null -w '%{http_code}\n' "$B/files/../../.env"; curl -s "$B/files/..%2F..%2F.env" | head -c 80`
  - 期望：400 `PATH_ESCAPE` 或 404；**响应体绝不包含 key/文件内容**。

- [ ] **CORE-17 静态检查**（AC-ENV-08，P1）
  - 命令：`$PY -m compileall -q app && (ruff check app || echo "ruff 不可用")`
  - 期望：compileall exit 0；ruff 无 error 级。ruff 未安装 → 记 KNOWN-FAIL 并注明替代（compileall 全绿）。

- [ ] **CORE-18 零新增依赖**（硬约束，P0）
  - 命令：`grep -rnE "^\s*(import|from) " server/app/ --include=*.py | grep -vE "app\.|flask|werkzeug|jinja2|pydantic|reportlab|pdfplumber|pypdf|docx|markdown|bs4|httpx|sqlite3|json|os|sys|re|time|datetime|pathlib|uuid|threading|unicodedata|hashlib|subprocess|shutil|tempfile|typing|dataclasses|logging|urllib" | head`
  - 期望：零命中（或每条命中都在评审注释里说明为 stdlib）。

> **CORE-19 ~ CORE-23 的口径来源**：captain 于 2026-10-23 用真实 LLM 连通性实测追加（实测：未重试时约 1/12 请求握手失败，报 `SSL: UNEXPECTED_EOF_WHILE_READING` 且**无 HTTP 状态码**；`.env` 的 `LLM_MAX_RETRIES` 已由 1 改为 2，带 2 次重试后 12/12 成功）。planner 已按裁定落稿：`LLM_JSON_MODE_PRECONDITION`(422) 与 `finish_reason` 约定见 D-13/D-14。

- [ ] **CORE-28 截断不得成为静默的成功（`OUTPUT_TRUNCATED` 三档 + 常驻横幅 + 反向非空）**（P0，captain 2026-10-23 裁定，`llm_client.py:417-455`）
  - 三档定稿：**空正文** → 502 `LLM_TRUNCATED`（`details.reason="empty_content"`）；**半截不可解析** → 502 `LLM_TRUNCATED`（`details.reason="partial_json"`）；**可解析的截断** → **200 + `warnings[].code="OUTPUT_TRUNCATED"`**（不得报错，但不得当作完整成功）。
  - 静态：截断响应里 `OUTPUT_TRUNCATED` 必须带 `details`，**至少含 `{finish_reason:"length", completion_tokens, max_tokens}`**，且 warning 本身带 `severity`（§14.1：业务 `warnings` 一律 `{code,message,severity,...}`）。
  - 行为：命中截断时前端必须在**该屏**渲染常驻横幅——**不是 toast、不自动消失**、切页回来仍在；文案必须含**可执行动作**（「重新分析」/「调高 max_tokens」至少其一）。
  - 补充（captain m01601）：**「可解析但 `finish_reason=length`」这一档**，除 `details` 三字段外，还必须断言 **`warnings` 数组非空且其中含 `OUTPUT_TRUNCATED`**——否则前端横幅没有触发点，用户看到的是一份「悄悄少了两段」的简历。
  - 反向（关键）：**截断时 `warnings` 不得为空**。这是「少了两条需求但看起来一切正常」的唯一预警；为空即判 FAIL（`BLK-4` 家族：用户可感知的静默降级）。
  - 归属：warning 缺 `severity`/`details` → **coder**（`server/app/adapters/llm_client.py:421`，实测当前只发 `{code,message}`）；前端用 toast 或可自动消失 → **uier**；三档语义写错 → **planner**（`API-CONTRACT.md §14.1` 的旧注「`OUTPUT_TRUNCATED` 已于 v1.6 删除」仍残留，见 D-33）。
- [ ] **CORE-29 布尔写库必须双向断言：`False → 0`（常驻，防 D-35 整类复发）**（P1，captain m01661）
  - 命令：`grep -rn "1 if isinstance(value, bool)\|isinstance(value, bool)" server/app/`
  - 期望：只剩**正确形态**——`db.py:393` 的 JSON 编码器 `1 if value else 0`（把 bool 落到 0/1，语义正确）与注释；**不得出现**把 `False` 也映成 `1` 的三目。
  - 行为断言：写 `is_current=false` 后**回读必须 `is False`**（不是 `1` 也不是 `True`）；再写 `is_current=true` 回读 `True`。**只断言真值路径的测试一律算不足**——这次 bug 正是「只验 True 能过」才漏掉的。
  - **当前实测**：`grep -c` 命中 2 处（`db.py:393` 正确形态 + `repos.py:687` 注释），无违规写法；`repos.py:694` 已是 `int(bool(value))`。
  - 归属：三目写法回归 → **coder**；只写 True 路径的单测 → **coder**（缺陷在测试覆盖，不在实现）。
- [ ] **CORE-19 连接级重试（握手抖动不得判成「key 无效」）**（P0，captain 追加）
  - 命令：`$PY -m pytest tests/acceptance -q -k "llm_retry" -s`
  - 测试体必须自己造：把 `llm_client` 的 transport 前两次调成抛 `httpx.ConnectError("SSL: UNEXPECTED_EOF_WHILE_READING")`，第三次放行（不是只断言 mock 的返回值）。
  - 期望：① 第三次确实被调用（`calls == 3`）且整体返回正常结果（`ok:true` + 合法 `parsed`）；② 对外**没有**错误，或至少**不是**鉴权/配置/出网白名单类码（禁止 `LLM_NOT_CONFIGURED`、401 语义、`EGRESS_BLOCKED`）；③ 重试上限固定为 `LLM_MAX_RETRIES=2`（.env 已由 1 改为 2；实测 1/12 握手失败率下 1 次重试不够，2 次才 12/12）→ 最多 3 次尝试，**不得**无限重试或写成 `except Exception: retry`；④ 三次尝试复用同一 `preview_id` 与同一份 payload（`payload_sha256` 相同），`llm_preview.consumed_at` 只在成功后写一次。
  - 负例：三次全失败时必须报连接类错误（不是鉴权类），且 `llm_call_log` 记 `ok=0` + 连接类 `error_code`。
  - 为何必须：TLS 抖动被报成「key 无效」会诱导用户去改 key，是误导性故障；而现行 §10.4 只允许对 429/5xx/超时重试，连接级异常会直接冒泡 → 契约须同步（D-12）。

- [ ] **CORE-20 json_object 的本地前置校验（0 出网、0 重试）**（P0，captain 追加）
  - 命令：
    ```bash
    $PY - <<'PY'
    from app.services import llm_payload
    from app.adapters import llm_client
    calls = []
    llm_client._transport_probe = lambda *a, **k: calls.append(1)   # 打桩：任何出网都记一笔
    try:
        llm_payload.build(purpose="bullets_generate",
                          messages=[{"role": "user", "content": "请改写这句话"}],
                          response_format={"type": "json_object"}, variant_ids=[])
    except Exception as e:
        print(type(e).__name__, getattr(e, "code", None))
    print("outbound_calls:", len(calls))
    PY
    ```
  - 期望：本地抛 `LLM_JSON_MODE_PRECONDITION`(422, `details.reason="PROMPT_MISSING_JSON_LITERAL"`)，**`outbound_calls: 0` 且 `retry_calls: 0`**——绝不能打到服务端吃 400，也**不得**因为「重试策略」把本地校验错误当成可重试错误再跑一遍（`llm_call_log` 行数不变即为证）；`hint` 给可执行动作（如「在系统指令里保留『以 JSON 输出』字样」）。
  - 判 PASS 的三条硬事实：**本地拒绝（422）** + **httpx 调用计数 0** + **`llm_call_log` 零新增**。反例：抛 `INTERNAL`(500)、先出网再报错、错误进重试队列 → 均判 FAIL（归属 coder）。
  - 入口函数名以实现为准（`llm_payload.build` / `consent.build` / `llm_client.complete` 均可）；判定只看两条硬事实：**本地拒绝** + **0 次出网**。
  - 背景（服务端原话）：`Prompt must contain the word 'json' in some form to use 'response_format' of type 'json_object'`。若把上游 400 原样透传，用户看到英文原文，违反「错误文案三段式」。

- [ ] **CORE-21 截断与坏响应二分：`LLM_TRUNCATED` 独立成码**（P0，captain 追加；**取代早前「复用 `LLM_BAD_RESPONSE`+`empty_content`」的口径**）
  - 命令：
    ```bash
    $PY -m pytest tests/acceptance -q -k "llm_truncated or llm_bad_response" -s
    # 桩①：finish_reason="length" + content=""（可加：content 为半截 JSON）
    # 桩②：finish_reason="stop" + content="不是 JSON" / 缺必填字段
    sqlite3 data/app.db "select count(*) from package_bullet_variant where trim(text)='' or text is null"
    sqlite3 data/app.db "select error_code, count(*) from llm_call_log where ok=0 group by 1"
    ```
  - 期望：① `finish_reason == "length"`（`content` 空**或半截 JSON**都算）→ **`LLM_TRUNCATED`(502)**，`details = {"reason": "empty_content" | "partial_json", "finish_reason": "length", "completion_tokens": N}`（`reason` 必填，用来区分「预算给低了」与「上游写崩了」）；② `finish_reason == "stop"` 但 JSON 非法/缺字段 → **`LLM_BAD_RESPONSE`(502)**，**不得**是 `LLM_TRUNCATED`；③ 两者**互斥**，同一响应不得同时命中两个 code；④ 空文本计数 `0`；⑤ `llm_call_log.ok=0` 且 `error_code` 能区分两类（分组计数可读）；⑥ **不得**把 `content=""` 当「成功但内容为空」写进 `parsed`/`variants`。
  - 判据注（为何二分，captain 2026-10-23 实测）：reasoner 在 `max_tokens=16` 时返回 `finish_reason='length'` + `content=''` + `reasoning_tokens=16`，正确处置是「调高 max_tokens」；这与「上游返回垃圾/非法 JSON」是两种故障、两种修法。混判成一个码会让排障走错方向，也会掩盖「预算给低了」这一高频原因。
  - 附加：UI 文案对 `LLM_TRUNCATED` 必须能指向「换模型或提高 max_tokens」，对 `LLM_BAD_RESPONSE` 指向「重试或改用手动填写」。

- [ ] **CORE-22 key 永不离境（四处 + 两处加测）**（P0，**BLK-3**，captain 追加）
  - 命令：
    ```bash
    export K=sk-test-DEADBEEF
    curl -s -X POST $B/settings/api-key -H 'Content-Type: application/json' -d "{\"api_key\":\"$K\"}" >/dev/null
    # ① API 响应体
    for u in settings env profile health; do curl -s $B/$u; done | grep -c "$K"            # 期望 0
    curl -s $B/settings | grep -c "${K: -4}"                                              # 期望 0
    # ② 日志文件
    grep -rIl "$K" data/logs/; grep -rIl "${K: -4}" data/logs/; echo "logs_done"
    # ③ 前端页面（模板 + 静态 js + 实际渲染首页）
    grep -rIl "$K" web/ web/src/; curl -s $B/ | grep -c "$K"                 # 期望 0
    # ④ LLM 字段清单（preview 全响应：fields[]/excluded/redactions）
    curl -s -X POST $B/llm/preview -H 'Content-Type: application/json' \
      -d '{"purpose":"bullets_generate","selections":{"package_ids":[],"variant_ids":[]}}' \
      | grep -cE "$K|${K: -4}"                                                            # 期望 0
    # 加测 ⑤ DB 全库（payload_json / field_manifest_json / app_setting）
    for t in app_setting llm_preview llm_call_log job; do sqlite3 data/app.db "select * from $t"; done | grep -c "$K"   # 期望 0
    # 加测 ⑥ 错误响应回显（上游 401 时不得回显 key）
    curl -s -X POST $B/llm/complete -H 'Content-Type: application/json' -d '{"preview_id":"bogus"}' | grep -c "$K"      # 期望 0
    ```
  - 期望：①–⑥ 全为 `0`；`.env` 权限仍 `600`；`GET /settings` 只有 `key_set/key_field`。
  - 与 D-09 的关系：`scripts/set-api-key.command` 现改为打印 **SHA-256 指纹前 8 位**（captain 2026-10-23 改版），发生在**用户本地终端**，不属于「响应/日志/页面/字段清单」四处，**指纹不算 key 片段**（不可逆、不可鉴权）。判定口径见 **INT-12**；若有人把脚本改回「取末四位」再伪装成指纹，INT-12 的反向 grep 会抓住。

- [ ] **CORE-23 非法 JSON 的降级解析**（P0，captain 追加；**planner 已实测 `deepseek-reasoner` 支持 `response_format=json_object`（200 + 合法 JSON），不得再以「reasoner 不支持 json 模式」为前提**）
  - 命令：桩上游返回 200 + `content="不是 JSON{..."`（模拟 json_object 失效），走 `llm/complete`。
  - 期望：① 不抛 500；响应 `parsed=null` + `warnings[code=LLM_JSON_UNPARSABLE]`（API-CONTRACT §10.3）；② `raw_text` 保留（脱敏后）供排障；③ 上层 `variants/generate`、`jd/analyze` 据此走「手动填写」入口，不落脏数据。
  - 要验的是「不合法 JSON 仍能降级」，**不是**「reasoner 不支持 json 模式」。

- [ ] **CORE-24 `assert_no_identity` 服务端自检：命中身份即拦（宁可失败也不发）**（P0，**BLK-2**，captain 2026-10-23 要求）
  - 背景：planner 新增服务端自检 `assert_no_identity`；命中身份信息（**姓名 / 电话 / 邮箱 / 照片哈希**；**学校名不在拦截范围**，正确校名不得被判违规，见 X-F9）→ 500 拒绝发送。**不许只 grep 到函数名就算通过**，必须造注入文本证明它真的拦得住、且一个字节都没出去。
  - 命令：
    ```bash
    $PY - <<'PY'
    import httpx
    from app.services import llm_payload
    calls = []
    def spy(self, req, *a, **k):
        calls.append(str(req.url)); raise AssertionError("出网了！")
    httpx.Client.send = spy
    # 注入一条故意含身份信息的“经历文本”
    try:
        llm_payload.build(purpose="bullets_generate",
                          messages=[{"role": "user",
                                     "content": "我在示例大学读书，姓名张三，手机13800000000"}],
                          variant_ids=[])
        print("NOT_BLOCKED")
    except Exception as e:
        print("raised", type(e).__name__, getattr(e, "code", None), getattr(e, "status", None))
    print("httpx_calls:", len(calls))
    PY
    sqlite3 data/app.db "select count(*) from llm_preview where payload_json like '%张三%' or payload_json like '%13800000000%'"   # 期望 0
    ```
  - 期望：① 抛出（5xx/专用码皆可，但**必须**是非 2xx 且明确失败），**不得**静默构造 payload；② `httpx_calls: 0`；③ `llm_preview` 无该次记录，或记录 `status=rejected` 且 `payload_json` 不含原文；④ **反例**：不含身份的合法文本不触发拦截，正常得到预览（证明不是「一律拦死」）；⑤ 自检不得被 `if DEBUG` / `try: ... except: pass` 吞掉（调用点必须在发送路径上，且无 except 包裹）。
  - **存在性前置（2026-10-23 实测）**：`grep -rn "assert_no_identity" server/` **零命中**（契约有、实现无）→ 本条直接 FAIL。反过来，将来 grep 命中也**不构成通过**：必须跑上面这段注入用例，看到「拒绝 + `httpx_calls: 0`」才算过（防假绿）。注入样本里请同时放一个**合法校名**用例（只含「示例大学」、不含姓名/电话/邮箱）→ 期望**放行**，证明自检没有过度拦截。

- [ ] **CORE-25 `provider=off`：全 LLM 端点 503，但关掉 AI 仍能出一条完整 PDF**（P0，captain 2026-10-23 要求）
  - 命令：
    ```bash
    curl -s -X PUT $B/settings -H 'Content-Type: application/json' -d '{"llm_provider":"off"}' >/dev/null
    for u in llm/preview llm/complete "packages/$pid/variants/generate" jd/analyze company-profiles/analyze; do
      printf "%-34s " "$u"; curl -s -o /dev/null -w '%{http_code}\n' -X POST "$B/$u" -H 'Content-Type: application/json' -d '{}'
    done
    sqlite3 data/app.db "select count(*) from llm_call_log"   # 与操作前对比，必须不变
    # 端到端：关 AI 后 导入 → 打包 → 组装 → 命名 → 导出
    curl -s -F "file=@data/imports/sample_zh.pdf" $B/imports > "$EV/off_imp.json"
    # 轮询 draft → commit → 建 build → assemble → export，全程不带 preview_id
    ```
  - 期望：① 五个 LLM 端点全 `503`，`code=LLM_DISABLED`，文案说明「已关闭 AI，可在设置里开启」；② `llm_call_log` 行数**不变**；③ 导入解析、打包编辑、组装、`naming/validate`、导出 PDF **全部照常成功**（`method=heuristic`/手动填写路径）；④ 导出的 PDF 用 `pdfplumber` 提取**非空**、含姓名与学校、`text_verified=1`；⑤ 整个过程无任何 502/超时/卡死。
  - 红线：关掉 AI 后任何核心动作变成不可用 → 判 coder 主责（降级路径缺失，违反 ARCHITECTURE §6 D1）。

**CORE 伪通过迹象**（见到即判 FAIL）：`GET /settings` 返回 `key_prefix`/`key_last4`；`egress_guard` 只是个空函数；错误码用 `INTERNAL` 兜住所有字段校验错误；`data/` 之外出现落盘文件；`.git` 已存在而 `.gitignore` 后补；重试写成 `except Exception: retry`（把 400/鉴权错误一起重试）；`LLM_MAX_RETRIES` 被忽略；`finish_reason='length'` 只打 warning 仍入库；**截断与非法 JSON 混判同一个码（`LLM_TRUNCATED` 缺席）**；json 模式校验放在请求之后（先出网再报错）；`assert_no_identity` 只存在于代码里却无调用点/被 except 吞掉；`provider=off` 时端点返回 200 空壳。

---

### 1.2 IMPORT（t5，owner: coder）— 简历导入与模板化拆解

- [ ] **IMP-01 中文样张导入**（AC-IMPORT-01，P0）
  - 命令：`curl -s -F "file=@data/imports/sample_zh.pdf" $B/imports | tee "$EV/imp_zh.json"; $PY -c "import json;print(json.load(open('$EV/imp_zh.json'))['data'])"`
  - 期望：**契约口径 202** + `{job_id, import_id}`；轮询 `GET /imports/{id}` 至 `status=draft`；`stats.pages=1`；`stats.chars` 按**实测基线区间 2100–2400**（2026-10-23 实测 **2241**；旧写 1600–2000 是未跑基线的估计，已按 §0.3 纠正）。素材缺失时**必须** KNOWN-FAIL 留痕，不得静默 PASS。
  - **captain 2026-10-23 裁定（取代「202 + 轮询」）**：成功 = **201**，响应体 = `{job_id, import_id, draft{...}}`；`needs_llm_fallback=true` 时**请求内不得发生 LLM 调用**；`ImportJob` 只作历史/审计，前端不轮询。理由：本地单页 PDF 解析 ~200ms，202+轮询只换来一个状态机和一个轮询 UI。**planner 改契约、coder 按 201 实现（D-20 已裁定，不再二选一）**。
  - **复判判据（planner 契约落地后执行，当前记 `PENDING(contract)`，不记 FAIL）**：
    ```bash
    curl -s -o /dev/null -w '%{http_code}\n' -F "file=@data/imports/sample_zh.pdf" $B/imports   # → 201
    curl -s -F "file=@data/imports/sample_zh.pdf" $B/imports | $PY -c "
    import json,sys
    d=json.load(sys.stdin)['data']
    assert 'job_id' in d and d['job_id'], 'job_id 缺失'
    assert len(d['draft']['blocks'])>0, 'draft.blocks 为空'
    print('ok', d['job_id'], len(d['draft']['blocks']), d['draft']['stats'])"
    ```
  - **2026-10-23 03:30 实测**：实际 **201** + 同步内联 `draft`，但**缺 `job_id`**；`stats.chars=2241`、`pages=1`。⇒ 与裁定口径只差一个字段，已转 `PENDING(contract)` 等 planner 改契约后复跑上面两条命令（D-20）。

- [ ] **IMP-02 英文样张 + cid 统计**（AC-IMPORT-02，P0）
  - 命令：`curl -s -F "file=@data/imports/sample_en.pdf" $B/imports`，再 `curl -s $B/imports/$id/draft | $PY -m json.tool > "$EV/imp_en.json"`
  - 期望：`stats.pages=2`、`stats.cid_missing=16`、`stats.images=1`；`warnings[]` 含 `{code:"CID_GLYPH_MISSING",count:16,severity:"info"}`。

- [ ] **IMP-03 `(cid:127)` 不进正文**（AC-IMPORT-02，P0）
  - 命令：`grep -c "(cid:127)" "$EV/imp_en.json"; $PY -c "import json;d=json.load(open('$EV/imp_en.json'))['data']['draft'];print([(b['block_type'],b['preview_text'][:40]) for b in d['blocks'] if 'cid' in b['preview_text'].lower()])"`
  - 期望：`grep -c` 为 `0`；含 cid 的 block 为零；对应 16 处为 `block_type=list` 或以 `-|•|·` 开头。
  - **2026-10-23 03:30 实测（PASS）**：EN draft `(cid:` 计数 **0**；`stats.cid_missing=16`；16 处已剥离为 bullet。**注意响应形状**：`GET /imports/{id}/draft` → `data.draft.blocks[]`（不是 `data.blocks[]`），旧命令会 `KeyError` 假红。

- [ ] **IMP-04 照片需用户确认**（AC-IMPORT-03，P0）
  - 命令：`grep -o '"code": *"PHOTO_DETECTED"' "$EV/imp_en.json" | wc -l`；再手工走一遍「用作证件照 / 忽略」分支。
  - **captain 2026-10-23 裁定（P0 工单 + 三条复判硬断言）**：导入只产出候选（draft 保留 `extracted_photo`），**不写 `user_profile.photo_path`、不把 attachment 标 `applied`**；`PHOTO_DETECTED`（`severity="warn"`）必现；显式确认后才落库。
  - **复判三条（缺一不可，只判 `applied=false` 不够）**：
    ```bash
    B=$(python3 -c "import json;d=json.load(open('data/runtime/app_port'));print('http://127.0.0.1:%d/api/v1'%d['port'])")
    before=$(sqlite3 data/app.db "select coalesce(photo_path,'NULL') from user_profile")
    curl -s -F "file=@data/imports/sample_en.pdf" $B/imports > "$EV/imp04.json"
    # ① 导入后 photo_path 保持原值
    after=$(sqlite3 data/app.db "select coalesce(photo_path,'NULL') from user_profile"); [ "$before" = "$after" ]
    # ② PHOTO_DETECTED 必现
    grep -q '"code": *"PHOTO_DETECTED"' "$EV/imp04.json"
    # ③ 确认动作确实能把 applied 变 true（否则照片功能等于判死）
    AID=$($PY -c "import json;print(json.load(open('$EV/imp04.json'))['data']['draft']['extracted_photo']['attachment_id'])")
    curl -s -X POST $B/profile/photo/confirm -H 'Content-Type: application/json' -d "{\"attachment_id\":\"$AID\"}"; echo rc=$?
    sqlite3 data/app.db "select photo_path from user_profile"; grep -c '"applied": *true' "$EV/imp04_confirm.json"
    ```
  - **判定口径**：① 未确认 `photo_path` **逐字不变**；② `PHOTO_DETECTED` ≥1；③ 确认后 `photo_path` **变成** `profile/photo_<sha256>.png` 且 draft/响应里 `applied=true`；④ 若「确认」没有任何端点或点完 `applied` 仍为 `false` → 同样判 FAIL（**把照片功能判死也是缺陷**）。
  - **2026-10-23 03:30 实测（FAIL，P0）**：① `warnings` 里**没有 `PHOTO_DETECTED`**（`grep -rn PHOTO_DETECTED server/app/` 零命中，代码根本没实现该码）；② draft 的 `extracted_photo.applied=true`，且导入后 `user_profile.photo_path` **已被写成** `profile/photo_3493da….png`——违反 AC-IMPORT-03「**不自动，必须用户确认**」（见 D-23）。

- [ ] **IMP-05 置信度与低置信聚合**（AC-IMPORT-04，P1）
  - 命令：`$PY -c "import json;d=json.load(open('$EV/imp_en.json'))['data']['draft'];print([(b['temp_id'],b['confidence']) for b in d['blocks'] if b['confidence']<0.6])"`
  - 期望：每个 block 有 `block_type/confidence∈[0,1]/slots[]`；低置信项非空时 `warnings` 有 `LOW_CONFIDENCE_BLOCKS` 且带 `block_ids[]`。
  - **2026-10-23 03:30 实测（PASS）**：全部 block `confidence ∈ [0.85, 0.95]`，无 <0.6 项 ⇒ `LOW_CONFIDENCE_BLOCKS` 不出现即正确（不得为了让 warning 出现而造假）。

- [ ] **IMP-06 commit 落模板 + 幂等**（AC-IMPORT-05，P0）
  - 命令：
    ```bash
    curl -s -X POST $B/imports/$id/commit -H 'Content-Type: application/json' -d '{"template_name":"中文-单页","lang":"zh","page_limit":1}' -w '\n%{http_code}\n'
    curl -s -X POST $B/imports/$id/commit -H 'Content-Type: application/json' -d '{"template_name":"再来一次","lang":"zh"}' -w '\n%{http_code}\n'
    sqlite3 data/app.db "select count(*) from template_block; select count(*) from slot;"
    ```
  - 期望：首次 201 且模板含 blocks+slots；第二次 409 `CONFLICT`，`details.reason="IMPORT_ALREADY_COMMITTED"`；表行数不翻倍。

- [ ] **IMP-07 五格式输入**（AC-IMPORT-06，P1）
  - 命令：`for f in server/tests/fixtures/*.pdf server/tests/fixtures/*.docx server/tests/fixtures/*.md server/tests/fixtures/*.txt server/tests/fixtures/*.html; do curl -s -o /dev/null -w "$f %{http_code}\n" -F "file=@$f" $B/imports; done`
  - 期望：五种格式均 **201**（captain 2026-10-23 裁定改口径）；docx 有标题层级、md/html 结构正确、html 的 `<script>/<style>` 被剥离（draft 中无 script 文本）。
  - **常驻规则（夹具缺失时）**：fixture 不在仓库 → 记 **`SKIP(no-fixture)`**，**不得记 PASS**（否则「没测」会被算成「测过且通过」）；也不得记 FAIL（会把缺料算成实现错）。该结论必须写进终验报告。
  - **2026-10-23 03:36 实测（PASS，captain 补夹具 commit `b8c335e`）**：`sample.docx` 201 `{pages:1,chars:222}`、`sample.html` 201 `{chars:226}`、`sample.pdf` 201 `{chars:171, blocks:5}`、`sample_en.txt` 201 `{chars:1493}`、`sample_zh.md` 201 `{chars:738}` —— 五种格式全部 201 且 `draft.blocks` 非空。`.gitignore` 仅对该目录放行（`!server/tests/fixtures/**`）。

- [ ] **IMP-08 解析全程不联网**（AC-IMPORT-07，P0，**BLK-1**）
  - 命令：`$PY -m pytest tests/acceptance -q -k "import and (egress or priv_10)"`
  - 期望：PASS；`egress_guard` 把所有非 loopback 连接变异常后，导入仍成功。

- [ ] **IMP-09 错误路径不留半成品**（AC-IMPORT-08，P1）
  - 命令：`curl -s -F "file=@/dev/null" $B/imports -w '\n%{http_code}\n'; head -c 21MB /dev/urandom > /tmp/big.bin; curl -s -F "file=@/tmp/big.bin" $B/imports -w '\n%{http_code}\n'; curl -s -F "file=@tests/fixtures/scan_no_text.pdf" $B/imports -w '\n%{http_code}\n'`
  - 期望：分别 415 `UNSUPPORTED_MEDIA_TYPE`、413 `PAYLOAD_TOO_LARGE`、422 `IMPORT_NO_TEXT_LAYER`；`sqlite3 data/app.db "select count(*) from import_job where status='failed'"` 增加，但 `template`/`template_block` 无新增。

- [ ] **IMP-10 draft 可编辑持久化**（AC-IMPORT-09，P1）
  - 命令：`curl -s -X PUT $B/imports/$id/draft -H 'Content-Type: application/json' -d @server/tests/fixtures/draft_edit.json -w '\n%{http_code}\n'; curl -s $B/imports/$id/draft | grep -c '"block_type": *"entry"'`
  - 期望：200；改动的 block_type/heading/slot 绑定在重新 GET 后仍在（刷新不丢）。

- [ ] **IMP-11 slot_key 契约**（P0，契约一致性，见 D-11）
  - 命令：`grep -n "slot_key" docs/API-CONTRACT.md | head -8; $PY -c "import json;d=json.load(open('$EV/imp_en.json'))['data']['draft'];print([s['slot_key'] for b in d['blocks'] for s in b['slots']])"`
- [ ] **IMP-12 内嵌照片抽取 + 落库（照片链路起点）**（captain 2026-10-23 新增，P0）
  - 背景：用户当面拍板「照片必须支持」；t5 负责从导入 PDF 抽出内嵌照片。真实联调素材：`data/profile/photo_from_zh_resume.png`；样张 `data/imports/sample_en.pdf` 含 1 张图。
  - 命令：
    ```bash
    $PY - <<'PY'
    import fitz  # 实现用 pdfplumber/pymupdf 均可，按 requirements.lock 实际引擎
    d = fitz.open("data/imports/sample_en.pdf")
    print("embedded_images:", sum(len(p.get_images(full=True)) for p in d))
    PY
    curl -s $B/imports/$id/draft | $PY -c "import json,sys;d=json.load(sys.stdin)['data'];print([(i['temp_id'],i['width'],i['height'],i.get('rel_path')) for i in d.get('images',[])])"
    sqlite3 data/app.db "select id,kind,rel_path,bytes from attachment order by created_at desc limit 3"
    shasum -a 256 data/files/**/*.png 2>/dev/null | head -3
    ```
  - 期望：① `stats.images=1`；② draft 的 `images[]` 给出 `temp_id/width/height/rel_path`（短边 ≥200px 才可作证件照候选）；③ 用户点「用作证件照」后 `attachment` 新增一行、`user_profile.photo_path` 指向 `data/files/` 下真实文件、字节与 PDF 内嵌图一致（`shasum` 相同）；④ 点「忽略」后 `photo_path` 不变（IMP-04）；⑤ **未确认前不落库**；⑥ 该文件字节**不得**出现在任何 payload（X-F8）。

- [ ] **IMP-13 导入解析「数字零丢失」硬门（对人工标注基准逐串断言）**（P0，**BLOCKER**，captain 2026-10-23 新增；基准为用户本机产物）
  - 背景：用户最先要看的就是导入解析，而最容易被「LLM 润色 / 规则清洗」悄悄毁掉的是**数字**——`3.56/4` 被写成 `3.56`、`p=0.018` 整段蒸发、`PM₂.₅` 被降级成 `PM2.5`。这类丢失不会报错、肉眼也难查，只能对基准逐串断言。
  - 基准：**`data/eval/expected_zh_v10.json`**（人工标注 ground truth，**4688B**，`_note` 自述含 PII、位于 `data/` 下已被 `.gitignore` 忽略、**不得作为 LLM 输入**）。**前提处理（必须显式）**：文件存在 → 必须跑；不存在 → 记 `SKIP(no-local-fixture)` 并在 `ACCEPTANCE-RUN.md` 写明「基准是用户本机产物、不在 git 内、需用户提供」，**既不判红也不静默跳过**（静默跳过 = supervisor 失职）。
  - **判据以文件为准，禁止硬编码条数**（captain 2026-10-23 修订）：基准由人工标注、会被上游修正（本文件已从 32 去重+剔除伪判据 → **30 unique**，见 `_numbers_match_mode`），任何写死「32 串 / 30 串」的判据都会随基准漂移成假红或假绿。断言一律 `len(fx["must_contain_numbers_verbatim"])`；**改动基准不产生缺陷归属**（不记 coder）。
  - 命令：
    ```bash
    test -f data/eval/expected_zh_v10.json || echo "SKIP(no-local-fixture): data/eval/expected_zh_v10.json 缺失，需用户提供"
    $PY - <<'PY'
    import json, urllib.request
    fx = json.load(open("data/eval/expected_zh_v10.json"))
    nums, chars = fx["must_contain_numbers_verbatim"], fx["must_survive_special_chars"]
    # 基准自检（防止有人改基准把判据改软）
    assert len(nums) == len(set(nums)), "numbers 有重复"
    assert not [s for s in nums if len(s) <= 1], "存在长度<=1 的伪判据（会命中任意含该字符的文本）"
    B = "http://127.0.0.1:%s/api/v1" % json.load(open("data/runtime/app_port"))["port"]
    req = urllib.request.Request(B + "/imports", data=json.dumps(
        {"source_path": "data/imports/sample_zh.pdf"}).encode(),
        headers={"Content-Type": "application/json"})
    jid = json.load(urllib.request.urlopen(req))["data"]["import_id"]
    draft = json.load(urllib.request.urlopen(B + "/imports/%s/draft" % jid))["data"]
    flat = json.dumps(draft, ensure_ascii=False)
    miss_n = [s for s in nums if s not in flat]; miss_c = [s for s in chars if s not in flat]
    print("numbers:", len(nums) - len(miss_n), "/", len(nums), "missing:", miss_n)
    print("special:", len(chars) - len(miss_c), "/", len(chars), "missing:", miss_c)
    print("cid:", flat.count("(cid:"), "ufffd:", flat.count("\ufffd"))
    assert not miss_n and not miss_c, "数字/字符丢失"
    PY
    ```
  - 期望（**逐项硬断言**；条数取文件实测值，**本行不写死数字**）：
    - **数字 `len(nums)`/`len(nums)` 全命中**（当前 **30**，去重且无单字符伪判据）。形态示例：`3.56/4`、`p=0.018`、`2200余天`、`2027年1月下旬`、`2024.9-2028.6`、`第三十六届`。**`3.56/4` 的 `/4` 与 `p=0.018` 必须完整**（典型丢失形态）。
    - **特殊字符 `len(chars)`/`len(chars)` 全命中**（当前 **12**）：`PM₁ PM₂.₅ PM₁₀ （R） （Python） （SQL） CET4： CET6: AI&金融 K-means VLOOKUP Ridge`（下标字符、全角括号、全角冒号不得被归一化吞掉；归一化可以但要出 warning）。
    - **结构**：5 个 section 全部识别 —— 教育背景(1) / 实习经历(1) / 项目经历(3) / 校园活动(1) / 职业技能(`block_type=skills`，`line_count=3`，`line_prefixes=["数据分析类","基础办公类","AI开发类"]`)。
    - **硬失败（任一即 FAIL，判 coder，BLOCKER）**：出现 `(cid:`；出现 U+FFFD（即替换字符 `\ufffd`，本清单**不保留该字符的字面量**以免 t11 扫描自命中）；任一数字缺失；section 数 < 4；`3.56/4` 被写成 `3.56`；`p=0.018` 整段消失。
    - **基准被改坏也要能抓**：`len(set(nums)) < len(nums)`（有重复）或存在 `len<=1` 的串 → 判**基准缺陷**（归 captain/用户），不得当作解析通过。
  - 归属：解析/清洗逻辑吞字 → **coder**（`server/app/services/importer.py`）；基准标注本身错 → **captain/用户**（不记 coder）。**禁止**用「LLM 打分数」替代逐串命中（分数不可复现，且润色型丢失恰好会让分数仍高）。
  - **交叉复核（正交，不替代本条）**：captain 侧有独立工具 `data/eval/check_import_draft.py`（读取导入草稿 + 基准，逐条比结构/30 串数字/12 串特殊字符/退化痕迹，输出 PASS/FAIL 与归属；已自测「理想草稿」走 PASS、「缺 4 段 + 丢数字 + 带 `(cid:`」能列出 10 项 hard_fail）。t11 用它跑一遍作为**第三方证据**，与本节命令互为校验；两者结论不一致时以本节的 `expected_zh_v10.json` 逐串口径为准，并把差异记入缺陷台账。
- [ ] **IMP-14 区块分类：`小象超市` 必须归 `project`，且 kind 只能取契约枚举**（P0，captain 2026-10-23 用户裁决）
  - 背景：分类错会让组装器选错包、导出时把项目写进实习区；用户点名 `小象超市` 这段经历是**项目**，不是竞赛。
  - 契约枚举（DATA-MODEL.md:86）：`package.kind ∈ {project, internship, education, award, activity, custom}`；`template_block.bound_package_kind` 同集合。**`竞赛` 不是合法 kind**。
  - 命令：
    ```bash
    sqlite3 data/app.db "select title, kind from package where title like '%小象超市%'"
    $PY -c "import json,urllib.request;B='http://127.0.0.1:%s/api/v1'%json.load(open('data/runtime/app_port'))['port'];d=json.load(urllib.request.urlopen(B+'/imports/%s/draft'%jid))['data'];print([(s['heading'],s['bound_package_kind']) for s in d['sections']])"
    sqlite3 data/app.db "select distinct kind from package"
    ```
  - 期望：① `小象超市` 的 `kind == "project"`（draft 里对应 entry 的 `bound_package_kind == "project"`）；② 全库 `kind` 取值 ⊆ 契约枚举，**不得出现 `竞赛`/`contest`/`competition`**；③ 项目段 section 的 `bound_package_kind == "project"`，与 CMP-25 的荣誉归属不冲突。
  - 归属：分类错 → **coder**（importer 归类规则）；若契约枚举本身要加「竞赛」→ **planner**（须先改 DATA-MODEL，不许实现私自扩枚举）。


- [ ] **IMP-15 导入 → Package 派生：不勾选时 package 数量必须不变**（P1，t8 之后；API 为 `{"also_create_packages": true}`，**默认 false**）
  - **背景（产品级缺口）**：`server/app/services/import_service.py` 的 `commit` 只生成 `template_block`（结构），**不产生 package**。后果：用户导入自己的简历后，warehouse 里依然没有他的真实经历，组装出来永远是一份「只有示例经历」的薄简历。
  - 前置（防跑空）：`grep -rn "also_create_packages" server/app/` 无命中 ⇒ 记 **`BLOCKED(no-impl)`**（不记 PASS/FAIL）。
  - **契约已就绪（2026-10-23，planner v1.25，已独立核对）**：`docs/API-CONTRACT.md:358-374`（字段/默认 `false`/`true` 时行为/**反向条款：false 不产生任何 package**/幂等/`created_packages[]` 恒在）、`docs/DATA-MODEL.md:147-153`（`source_import_job_id` + `source_entry_temp_id` + `UNIQUE(...)` 部分索引）、`docs/DATA-MODEL.md:540-541` 不变量 **I12/I13**、`docs/ACCEPTANCE.md:171-172` **AC-IMPORT-15/16**。⇒ 判据不用自己发明字段名。
  - 命令：
    ```bash
    cd resume-warehouse
    ID=$(curl -s -X POST $B/imports -F "file=@data/imports/sample_zh.pdf" | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["import_id"])')
    BEFORE=$(sqlite3 data/app.db "select count(*) from package where deleted_at is null")
    curl -s -X POST $B/imports/$ID/commit -H 'Content-Type: application/json' -d '{"also_create_packages": false}' >/dev/null
    MID=$(sqlite3 data/app.db "select count(*) from package where deleted_at is null")
    ID2=$(curl -s -X POST $B/imports -F "file=@data/imports/sample_en.pdf" | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["import_id"])')
    curl -s -X POST $B/imports/$ID2/commit -H 'Content-Type: application/json' -d '{"also_create_packages": true}' >/dev/null
    AFTER=$(sqlite3 data/app.db "select count(*) from package where deleted_at is null")
    ENTRIES=$(sqlite3 data/app.db "select count(*) from template_block where kind in ('internship','project','activity')")
    echo "before=$BEFORE mid=$MID after=$AFTER entries=$ENTRIES"
    ```
  - 期望：① `MID == BEFORE`（**反向断言：不勾选时不得「顺手生成」**）；② `AFTER - MID` == 该次导入里 `internship`/`project`/`activity` 条目数（当前 zh 样张为 5：实习 1 + 项目 3 + 校园 1）；③ 每个派生 package 的 `kind` 等于对应条目的 `bound_package_kind`；④ 条目 bullets 变成 `package_bullet_variant`（`select count(*) from package_bullet_variant where package_id=?` > 0）。
  - 归属：没派生 / 勾选后数量不对 / 不勾选也生成 → **coder**；`kind` 映射错 → **coder**（映射来自 `import_service.py` 的 block 分类）。

- [ ] **IMP-16 派生幂等：同一 `import_job` 重复 commit 不得重复建包**（P1，与 IMP-15 同批）
  - 前置：`sqlite3 data/app.db "PRAGMA table_info(package)" | grep -c source_import_job_id` = 1；为 0 ⇒ 记 **`BLOCKED(schema-missing)`**（列不存在，判据无法落地，也不许用「标题相同」替代）。契约已含 `UNIQUE(source_import_job_id, source_entry_temp_id)`（`DATA-MODEL.md:153`，部分索引 `WHERE source_import_job_id IS NOT NULL`）⇒ 幂等键已定义，**不要另设**。
  - 响应口径：commit 201 的 body 增 `created_packages[]`（`[{id,title,kind,source_entry_temp_id}]`，**未开启时为 `[]` 且字段恒在**，不得省略）——判「包数不增」既可用 DB 计数，也可用该数组长度（幂等复跑时它回「已存在被复用」的项）。
  - 命令：
    ```bash
    for i in 1 2; do curl -s -X POST $B/imports/$ID/commit -H 'Content-Type: application/json' -d '{"also_create_packages": true}'; done
    sqlite3 data/app.db "select count(*) from package where source_import_job_id='$ID' and deleted_at is null"
    ```
  - 期望：commit 两次后计数 **== 条目数**（不翻倍）；第二次 commit 允许返回 409（已提交）或 200，但**包数不变**。
  - 归属：翻倍 → **coder**（去重键应为 `import_job.id + entry.temp_id`，或直接 `source_import_job_id`）。

- [ ] **IMP-17 撤销连带：软删导入必须连带软删派生包**（P0，t8 之后；理由写死）
  - **理由**：不连带就是「**幽灵经历**」——用户以为删了，但仓库里还留着，后续组装会把已删内容混进简历。**这种脏数据不会报错、不会告警**，只会静默污染结果。
  - 命令：
    ```bash
    N=$(sqlite3 data/app.db "select count(*) from package where source_import_job_id='$ID' and deleted_at is null")
    curl -s -X DELETE $B/imports/$ID; sleep 1
    M=$(sqlite3 data/app.db "select count(*) from package where source_import_job_id='$ID' and deleted_at is null")
    curl -s -X POST $B/imports/$ID/restore; sleep 1
    R=$(sqlite3 data/app.db "select count(*) from package where source_import_job_id='$ID' and deleted_at is null")
    echo "before=$N after_delete=$M after_restore=$R"
    ```
  - 期望：`before == after_restore` 且 `after_delete == 0`；**不得**只软删 `import_job` 而留下 `package` 行（`deleted_at IS NULL` 仍为 N 即 FAIL）。
  - 归属：未连带 → **coder**（`import_service` 的删除路径）；`restore` 不恢复 → **coder**；契约未写「级联删除」语义 → **planner**。

---

#### 1.2.1 IMPORT lane 实测基线（2026-10-23 03:30，supervisor 独立执行，captain 的 checker 仅作正交证据）

> 环境：`server/server.py --port 8899` + `requests`；素材 `data/imports/{sample_zh, sample_en}.pdf`、`server/tests/fixtures/{sample_zh.md, sample_en.txt}`；`PYTHONPATH=server /opt/anaconda3/bin/python3 -m pytest server/tests -q` → **58 passed, 4 warnings**。

| 条目 | 结论 | 证据（实测） |
|---|---|---|
| IMP-01 | **PENDING(contract)** | 实际 **201 + 同步内联 draft**（captain 已裁定采用 201 口径），仅缺 `job_id`；契约改完后复判（D-20）。`stats.chars=2241`、`pages=1` 正常 |
| IMP-02 | **PASS** | `pages=2 / cid_missing=16 / images=1`；warnings 含 `CID_GLYPH_MISSING count=16`；`severity="warning"` 不在契约 `{info,warn}` 内（D-21，不影响本条判定） |
| IMP-03 | **PASS** | draft 内 `(cid:` 计数 **0**；16 处已剥离为 bullet |
| IMP-04 | **PASS（03:41 复测，D-23 已修）** | 三条断言全过：① 导入后 `photo_path` 仍为旧值 `profile/photo_3493da…png`（未自动写）；② `PHOTO_DETECTED`（`severity=warn`）必现；③ `PUT /profile/photo` 后 `photo_path` 变 `profile/photo_2b1c46ab….png`（确认动作有效）。附：`extracted_photo.applied=false`、`attachment_id` 非空、w 200×200 |
| IMP-05 | **PASS** | 全部 block `confidence ∈ [0.85,0.95]`，无 `<0.6` ⇒ 不出现 `LOW_CONFIDENCE_BLOCKS` 正确 |
| IMP-06 | **FAIL** | commit 201 ✓、二次 409 ✓，但 `details` 只有 `{template_id}`，缺 `reason="IMPORT_ALREADY_COMMITTED"`（D-22） |
| IMP-07 | **PASS（03:36 复跑）** | captain 补 `sample.docx/html/pdf`（commit `b8c335e`）后 5/5 全部 201 且 `draft.blocks` 非空：docx 222 / html 226 / pdf 171(chars)+5(blocks) / txt 1493 / md 738 |
| IMP-08 | **PASS** | 静态：`importer.py`/`import_service.py` 无 requests/httpx/urllib/socket import；行为：`server/tests/test_privacy.py` 的 egress monkeypatch 用例在 58 passed 内 |
| IMP-09 | **PASS** | 415 `UNSUPPORTED_MEDIA_TYPE` / 413 `PAYLOAD_TOO_LARGE` / 422 `IMPORT_NO_TEXT_LAYER`（`details={chars_extracted:0,parser:pdf,pages:1}`） |
| IMP-10 | **PASS** | PUT 200；重 GET 后 `heading="教育背景（改）"`、`confidence=0.42` 仍在 |
| IMP-11 | **PASS** | 31 个 slot_key 全部匹配 `^[a-z][a-z0-9_.]{0,40}$`（含 `skills.lines`） |
| IMP-12 | **部分 PASS / 部分 FAIL** | 照片抽出 266×266 → `data/profile/photo_3493da….png` + `attachment(kind=photo)` ✓；但 `applied=true` 违反「必须确认」（同 D-23）；`top_offset_pt=-4.01` 是**源 PDF 出血几何**（pdfplumber 复核 bbox `top=-4.01, bottom=85.28`），非实现错误 |
| IMP-13 | **PASS** | 30/30 数字、12/12 特殊字符、`(cid:`=0、U+FFFD=0、`len(set(nums))==len(nums)` |
| IMP-14 | **PASS** | commit 后 `bound_package_kind ∈ {None, education, internship, project, activity}`；`campus→activity`、`skill→None`；无「竞赛」 |

**关键实测数字**：zh `{pages:1, chars:2241, words:85, lines:44, images:1, cid_missing:0}`、blocks 12（header1+section4+entry6+skills1）、bullets 11（实习3 + 项目2/2/2 + 校园2）、skills 3 行全带 tokens、教育段 `facts` 2 条；en `{pages:2, chars:4757, images:1, cid_missing:16}`。

**三处待判点的裁定**
1. **`sections[]` 与 `blocks` 双写、heading 为 null** → **stale artifact，非 coder 新缺陷**：`data/exports/*.json` mtime **03:27:21** 早于 `importer.py` **03:29:42**；实时 API 的 `sections[].heading` **已填**、`quality` 已是 `{sections_found:5, cid_residual:0, replacement_chars:0, numbers_second_pass:false}`（`importer.py:627`）。**但仍要收敛**：`sections[]` 是契约未定义的实现自创字段（D-25），要求 coder 改为 **由 blocks 派生 + 一致性断言**（`sections[i].heading == 对应 section block.heading`），planner 在 API §5.1 补文档。
2. **教育段 `facts[]` 必须逐字渲染**：已加 **CMP-26**（同 CMP-21 口径：PDF 抽取 vs `facts[]` 逐字相等；否则教育段 GPA/CET/课程在组装或导出静默丢失）。
3. **header 里的姓名/电话/邮箱**：已加 **X-F13**（`blocks[header]` 的任何字段**永不进 payload**；`needs_llm_fallback=true` 时也只允许脱敏后的 `llm_brief()` 七项，**禁止整份 draft 序列化**）。事实支撑：本轮导入全程 `needs_llm_fallback=false`、`warnings=[]`、importer 无网络 import。

---

- [ ] **IMP-18 commit 不得丢弃静态内容：`template_block.static_text` 必须落库且与 draft 逐字相等**（P0，captain 2026-10-23 m02371，**D-46**）
  - 背景（真库实测，截至 2026-10-23 04:33）：`template_block` 共 **72 行、`static_text` 全空（72/72）**。**口径**：72 = **6 个模板 × 每模板 12 块**（其中活跃默认模板 `lang='zh'` 占 12 块），所以 `72/72` 全空等价于「所有模板的教育/技能等静态块一个字都没写进去」；单看「12 块」只是在看默认模板那一片。而同一 `import_job.draft_json` 里教育段有 `专业成绩：GPA 3.56/4 86.53/100 CET4：562 CET6:508` 与 `主修课程：…` 两整段、技能段有 3 行整句。结果：**导入并 commit 后，GPA/CET/7 门课程分数/3 行技能整句全部消失**（导出的 PDF 只剩「示例大学」一行）。
  - 命令：
    ```bash
    sqlite3 data/app.db "select count(*), sum(case when coalesce(static_text,'')='' then 1 else 0 end) from template_block;"
    python3 - <<'PY'
    import json, sqlite3
    con = sqlite3.connect("data/app.db"); con.row_factory = sqlite3.Row
    draft = json.loads(con.execute("select draft_json from import_job where status='committed' order by created_at desc limit 1").fetchone()[0])
    blocks = con.execute("select block_type, coalesce(static_text,'') t from template_block").fetchall()
    txt = "\n".join(b["t"] for b in blocks)
    probes = ["GPA 3.56/4", "86.53/100", "CET4：562", "CET6:508", "主修课程："]
    print({p: (p in txt) for p in probes}, "| draft_has:", {p: (p in json.dumps(draft, ensure_ascii=False)) for p in probes})
    assert sum(1 for b in blocks if not b["t"].strip()) < len(blocks), "全部 static_text 为空 = 静态内容未落库"
    assert all(p in txt for p in probes), "探针未命中 = commit 丢内容"
    PY
    ```
  - 期望：`empty_static == 0`；五个探针在 `template_block` 里**全部命中**且在 draft 里同样命中（两处逐字相等，不是「大意相同」）；技能 3 行整句各成一行。
  - **现状（2026-10-23 04:33 实测）：FAIL** —— `72/72` 全空、五探针 0 命中。
  - 归属：commit 未把静态段写进 `template_block` → **coder**（`server/app/services/import_service.py` 的 commit 分支）。

- [ ] **IMP-19 commit 不得丢档案字段，也不得「猜」**（P0，captain 2026-10-23 m02371，**D-46**）
  - 背景：同一 commit 后 `user_profile.{degree,major,grad_year,city}` 全 `None`、`skills_json` 为 `[]`（实测 `select degree,major,grad_year,city,length(coalesce(skills_json,'')) from user_profile` → `||||` / `2`）。
  - 命令：
    ```bash
    sqlite3 data/app.db "select degree,major,grad_year,city,coalesce(skills_json,'NULL') from user_profile;"
    sqlite3 data/app.db "pragma table_info(user_profile);" | grep -E "profile_fields_source|source_import_job_id"
    ```
  - 期望：① 四字段与 `skills_json` 有值；② 有 `profile_fields_source`（或等价溯源字段）指向产生它们的 `import_job_id`；③ **反向断言**：新建库、不导入这些字段时四字段保持 `None`、`skills_json` 保持 `[]` —— **不得用默认值/猜测值填充**（「猜」比「空」更难被发现）。
  - **现状（04:33 实测）：FAIL** —— 四字段全空、`skills_json='[]'`。
  - 归属：字段映射缺失 → **coder**；契约未定义溯源字段 → **planner**。

### 1.3 PACKAGE（t6，owner: coder）— 对话式经历打包

- [ ] **IMP-20 build 必须可追溯：`sections_order_json` / `field_values_json` 不许是空壳**（P0，captain m02548）
  - 实测（2026-10-23 04:42）：`resume_build` **21 行全部** `length(sections_order_json)=2`、`length(field_values_json)=2`（即 `[]` / `{}`）；`grep -rn "sections_order_json\|field_values_json" server/app/services server/app/api` → **0 个写入点**。
  - 为什么是 P0：这两列是「**重新生成**」和「**用户质疑漏排**」的唯一依据。空着意味着导出结果不可解释——出了错也复现不了，只能重来。
  - 判据：① 任一 `status='exported'` 的 build，`sections_order_json` 的条目总数 == PDF 内实际条目数（用 pdfplumber 数段落反证）；② `field_values_json` 必须能回答「这句话来自哪个 package / 哪个 variant / 是否回退语言」；③ `build_selection.snapshot_json` 与之一致（同一 build 的两处记录不得互相矛盾）；④ 反向：新建 build 未导出时允许为空，但**导出成功那一刻必须写入**，事后补写 = FAIL。
  - 归属：**coder**（`compose.py` / `builds` API）；若契约未定义两列结构 → **planner**（`DATA-MODEL` 补字段语义）。

- [ ] **PKG-01 Package CRUD**（P0）
  - 命令：`curl -s -X POST $B/packages -H 'Content-Type: application/json' -d @tests/fixtures/package.json -w '\n%{http_code}\n' | tail -2`；`curl -s -X DELETE $B/packages/$id -o /dev/null -w '%{http_code}\n'`
  - 期望：201 + `Location` 头 + 完整对象（含 `variants[]`）；DELETE 204；`GET /packages` 不返回软删项；`POST /packages/{id}/restore` 200 后复现。

- [ ] **PKG-02 ready 前置校验**（AC-BUILD-01，P0）
  - 命令：`curl -s -X PATCH $B/packages/$id -H 'Content-Type: application/json' -d '{"status":"ready"}' -w '\n%{http_code}\n'`
  - 期望：无 verified variant 时 409，`details.reason="PACKAGE_NEEDS_VERIFIED_VARIANT"`，`details.unverified=[...]`；补一条 `verified:true` 后 200。

- [ ] **PKG-03 三 tone 变体**（P0）
  - 命令：`curl -s $B/packages/$id/variants | $PY -c "import json,sys;print(sorted({v['tone'] for v in json.load(sys.stdin)['data']['items']}))"`
  - 期望：至少 `['ats','impact','technical']`；`UNIQUE(package_id,bullet_key,tone,lang)` 生效（重复插入 409）。

- [ ] **PKG-04 中文 FTS5 搜索**（AC-BUILD-06，P1）
  - 命令：`curl -s "$B/packages?q=订单" | $PY -c "import json,sys;d=json.load(sys.stdin)['data'];print(d['total_estimate'], [i['title'] for i in d['items']])"`
  - 期望：命中含「订单」的包（`total_estimate ≥ 1`）；空 `q` 走普通分页且 `next_cursor` 可用。

- [ ] **PKG-05 变体生成需 consent**（P0，**BLK-4**）
  - 命令：`curl -s -X POST $B/packages/$id/variants/generate -H 'Content-Type: application/json' -d '{"bullet_keys":["b1"],"tones":["impact"]}' -w '\n%{http_code}\n'`
  - 期望：缺 `preview_id` → 428 `LLM_CONSENT_REQUIRED`；带合法 preview → 202 + `job_id` + `expected_variants`；任务完成后**不自动入库**（`select count(*) from package_bullet_variant` 不变）。

- [ ] **PKG-06 校验规则**（P1）
  - 命令：`curl -s -X POST $B/packages -H 'Content-Type: application/json' -d '{"title":"x","kind":"project","is_current":true,"end_date":"2025-09"}' -w '\n%{http_code}\n'`
  - 期望：422 `VALIDATION_ERROR`，`details.fields[0].rule` 指向 `is_current/end_date`。

- [ ] **PKG-07 归档与历史引用**（AC-BUILD-08，P2）
  - 命令：`curl -s -X PATCH $B/packages/$id -d '{"status":"archived"}' -H 'Content-Type: application/json'; curl -s "$B/packages" | grep -c "$id"`；再 `GET /builds/$old_build?include=selections`
  - 期望：默认列表不返回；历史 build 仍能渲染该包的 snapshot（不 500）。

**PACKAGE 伪通过迹象**：`status` 用 `draft/ready` 之外的字符串；`verified` 写成字符串 `"true"`；FTS 用 `LIKE '%订单%'` 冒充（可用 `sqlite3 data/app.db "select * from package_fts limit 1"` 反证：FTS 虚表必须存在）。

---

### 1.4 ANALYSIS（t7，owner: coder）— JD / 公司偏好 / 匹配

- [ ] **PKG-08 日期往返：`end_date` 不得被静默清空（D-35 回归门）**（P0，captain m01661 实测定位）
  - 背景：`repos.py:686` 的三目写法把 `False` 也转成 `1` → `is_current` 恒真 → `create()` 随即把用户填的 `end_date` 抹成 `NULL`。**不报错、不告警、测试不红**，用户只在导出 PDF 时看到「每段经历都是至今」。
  - 命令：
    ```bash
    ID=$(curl -s -X POST $B/packages -H 'Content-Type: application/json' \
      -d '{"title":"t","kind":"internship","start_date":"2023-07","end_date":"2024-06"}' | $PY -c 'import sys,json;print(json.load(sys.stdin)["data"]["id"])')
    curl -s $B/packages/$ID | $PY -c 'import sys,json;d=json.load(sys.stdin)["data"];assert d["end_date"]=="2024-06", d["end_date"];assert d["is_current"] is False, d["is_current"]'
    sqlite3 data/app.db "select end_date,is_current from package where id='$ID'"   # 必须 ('2024-06', 0)
    ```
  - 期望：响应与 **DB 原始行**都把 `end_date` 原样保留、`is_current=0`；`is_current` 未传时必须是 `False`（不是缺失、不是 `1`）。
  - 反向：`{"is_current":true,"end_date":"2024-06"}` 必须 **422**（`server/app/models.py:212-214` 的 `_current_has_no_end`），且**文档须写明这条护栏不许为「写入宽松」而删**。
  - **当前状态（2026-10-23 04:5x 实测，临时库）**：根因已修（`repos.py:694` 改为 `int(bool(value))`）→ 建→读回 `2024-06 / False`、DB 行 `('2024-06', 0)`、护栏 422 均绿；**存量 18 行仍坏**，由 INT-17 修复。
  - 归属：三目写法回来 → **coder**；只断言 `True` 路径的测试 → **coder**（测试不足，见 CORE-29）；护栏被删/文档没写 → **planner + coder**。

- [ ] **ANL-01 LLM 不可用时启发式**（AC-JD-01，P0）
  - 命令：`curl -s -X POST $B/jds/$id/analyze -H 'Content-Type: application/json' -d '{"method":"auto"}' | $PY -m json.tool`；随后 `curl -s $B/jds/$id/requirements`
  - 期望：202；完成后 `items[]` ≥1，`analysis_method="heuristic"`，无 `LLM_*` 错误（最多 1 条 warning）。

- [ ] **ANL-02 LLM 路径必须先 preview**（AC-JD-02，P0，**BLK-4**）
  - 命令：`curl -s -X POST $B/jds/$id/analyze -H 'Content-Type: application/json' -d '{"method":"llm","max_requirements":10}' -w '\n%{http_code}\n'; sqlite3 data/app.db "select count(*) from jd_requirement"`
  - 期望：428 `LLM_CONSENT_REQUIRED`；需求表计数**不变**；带 `preview_id` 后 202 才产生记录。

- [ ] **ANL-03 匹配为本地打分**（AC-JD-03，P1）
  - 命令：`curl -s -X POST $B/jds/$id/match | $PY -c "import json,sys;d=json.load(sys.stdin)['data'];print(0<=d['coverage']<=1, len(d['scores']), d['top_gaps'][:3])"`
  - 期望：`True`；`scores[]` 每项含 `package_id/score/hits[]/gaps[]`；`egress_guard` 生效时仍 200。

- [ ] **ANL-04 人工改需求影响打分**（AC-JD-04，P1）
  - 命令：`curl -s -X PATCH $B/requirements/$rid -H 'Content-Type: application/json' -d '{"weight":0.1}'; curl -s -X POST $B/jds/$id/match | $PY -c "import json,sys;print(json.load(sys.stdin)['data']['coverage'])"`
  - 期望：改后 `source="manual"`；`coverage` 与改前不同（记录两次数值作证据）。

- [ ] **ANL-05 公司画像：下行抓取可开可关 + 缓存 + 零用户字段外带**（AC-JD-05、API §7，P0，**BLK-9**，D-07 已裁定：抓取是立项授权需求，不得判违规）
  - **口径（captain 2026-10-23 裁定）**：抓公司官网/招聘页是用户在立项时明确授权的需求（「默认允许抓公司官网与招聘页」）；真正要管的是**下行不含用户数据**，不是禁止抓取。实现走 `server/app/adapters/fetch_client.py`（域名白名单、用户可关、失败降级为仅用用户粘贴的 JD 文本）。
  - 命令：
    ```bash
    # 1) 抓取能力存在且默认开启
    curl -s $B/settings | $PY -c "import json,sys;d=json.load(sys.stdin)['data'];print(d.get('fetch',{}))"   # 期望 {'enabled': True, 'allow_hosts': [...]}
    # 2) 抓取结果进 sources_json，且只记 type/url/used_at，不记用户字段
    curl -s -X POST $B/company-profiles/analyze -H 'Content-Type: application/json' \
      -d '{"company_name":"某某科技","jd_id":"'$jd'","preview_id":"'$pv'"}' | $PY -m json.tool > "$EV/anl05.json"
    $PY -c "import json;d=json.load(open('$EV/anl05.json'))['data'];print([s['type'] for s in d['sources_json']])"
    # 3) 缓存命中不再抓、不再调 LLM
    curl -s -X POST $B/company-profiles/analyze -H 'Content-Type: application/json' \
      -d '{"company_name":"某某科技","jd_id":"'$jd'","refresh":false}' | grep -o '"cache_hit":[a-z]*'
    # 4) 用户关闭后不得发任何抓取请求
    curl -s -X PATCH $B/settings -H 'Content-Type: application/json' -d '{"fetch":{"enabled":false}}' >/dev/null
    $PY -m pytest tests/acceptance -q -k "fetch_disabled_no_request"
    ```
  - 期望：`fetch.enabled` 默认 `true`；`sources_json` 的 `type ∈ {jd,user_note,web}` 且每条 web 只含 `url/used_at/status`，**不含**任何用户字段；第二次 `cache_hit=true` 且 `llm_call_log` 行数不变、`fetch_client` 调用次数为 0；关闭抓取后请求数为 0 且分析降级为仅 JD 文本（仍出结果，不是报错）。
  - 判 BLK-9 的红线：URL/query/body 里出现姓名、电话、邮箱、学校或简历原文；非 GET；目标白名单外；用户关闭后仍发请求。

- [ ] **ANL-06 分析失败不留脏数据**（AC-LLM-06，P1）
  - 命令：注入上游 500（`LLM_BASE_URL` 指向返回 500 的本地桩）后跑 `analyze`，再查表。
  - 期望：前端收到 `LLM_UPSTREAM_ERROR`；`jd_requirement` 无该 JD 的部分结果（事务回滚）。

- [ ] **ANL-07 竞争力评估：校名必须真的被消费（`competitiveness`）**（P0，**SENT-BUT-UNUSED**，API-CONTRACT §6.1 / ADR-20，2026-10-23 新增）
  - 为什么单列：用户强调「**校名是判定是否具有竞争力的核心判定依据之一**」。如果校名进了 payload 而 schema 没有字段消费它，就是**隐私成本已付、分析收益为零**的净损失（见 §0.3 `SENT-BUT-UNUSED`）。
  - **编号对齐说明**：captain 在 m00824 里把「正例」称作 ANL-06、把「反例」称作 ANL-07；本清单的 `ANL-06` 已被 `AC-LLM-06 分析失败不留脏数据` 占用，故两条新条目顺延为 **ANL-07（正例 A）/ ANL-08（反例 B）**，内容与 captain 的 A/B 一一对应，不做重复条目。
  - **可验前置（防空跑误判，2026-10-23 03:2x 实测）**：
    ```bash
    grep -rn 'competitiveness' server/app/ --include=*.py | grep -v 'services/prompts.py'
    grep -rn 'school_preference' server/app/ --include=*.py | grep -v 'services/prompts.py'
    ```
    实测**均 0 命中**（`competitiveness` 只出现在 `prompts.py:26`/`:50` 的 prompt 文本里）→ **schema 要的字段当前没有任何代码产出/校验/兜底**。此时 ANL-07/ANL-08 记 **`BLOCKED(no-impl)`**，**不得记 PASS/FAIL**（t7 未开工时 `/api/v1/jd` 仍 404，跑断言只会得到「无数据」的假象）。t7 交付后上述命中 ≥1 才进入判定。
  - 命令：
    ```bash
    curl -s -X POST $B/jds/$jid/analyze | tee "$EV/anl07_job.json"      # 真实 JD + 真实 profile（含校名）
    # 轮询 GET /jobs/$job_id 至 succeeded 后：
    curl -s $B/jds/$jid > "$EV/anl07.json"
    $PY - <<'PY'
    import json
    d = json.load(open("$EV/anl07.json"))["data"]; c = d["competitiveness"]
    TIERS = {"C9","985","211","双一流","普通本科","海外","其他"}; FIT = {"strong","medium","weak"}
    TIERWORD = ["985","211","双一流","C9","普通本科","海外","院校","层次"]
    print("tier:", c["school_tier"], "verdict:", c["verdict"])
    assert c["school_tier"] in TIERS, "school_tier 不在枚举"
    assert c["verdict"] in FIT and c["degree_fit"] in FIT and c["major_fit"] in FIT and c["experience_fit"] in FIT
    assert len(c["school_signal"]) >= 8, "school_signal 过短"
    assert ("示例大学" in c["school_signal"]) or any(w in c["school_signal"] for w in TIERWORD), "school_signal 既无校名也无层次词 = 模板套话"
    assert all(r.get("candidate_status") in {"satisfied","partial","missing"} for r in d["requirements"]), "requirements 缺 candidate_status"
    print("signal:", c["school_signal"])
    PY
    ```
  - 期望：① `school_tier` ∈ 枚举（`C9/985/211/双一流/普通本科/海外/其他`，优先取 `UserProfile.school_tier` 手工值）；② `verdict`/`degree_fit`/`major_fit`/`experience_fit` ∈ `{strong,medium,weak}`；③ **`school_signal` 长度 ≥8 且必须含校名或院校层次词**；④ `requirements[]` **每条**都有 `candidate_status`；⑤ `method=heuristic`（离线）时 `competitiveness` 仍返回、**不得为 null**，`school_signal` 由含校名+tier 词的模板串生成。
  - **反例（见到即 FAIL）**：`school_signal` = 「综合素质良好」「该候选人表现不错」「与岗位匹配度高」——不含校名、不含层次词，说明 prompt 写了但输出没被约束（模板套话）。
  - **prompt 必须真被调用（防「只改常量、调用点仍用旧模板」）**：
    ```bash
    grep -n "候选人档案" server/app/services/prompts.py server/app/repos.py server/app/services/*.py | head
    grep -rn "PROMPT_JD_ANALYZE\|prompts\." server/app/services/jd_analyzer.py | head
    ```
    期望：`## 候选人档案` 段在 payload 里**实际出现**（`grep -c "候选人档案" "$EV/anl07_payload.json"` ≥1）且段内含真实校名；调用点引用的是同一个常量名。
    **已核事实（2026-10-23 03:2x，captain 独立复核 + supervisor 复验）**：`prompts.py` **120 行 / `school|院校|竞争` 18 命中**；三个 purpose（`jd_analyze`/`company_profile`/`build_suggest`）的 schema 文本分别含 `competitiveness`、`school_preference`、`school_signal_used`；`ALLOWED_SOURCES`（`prompts.py:70-76`）**五个 purpose 全部含 `profile`**，并在 `consent.py:328-330` 注明该段只允许七项、姓名/电话/邮箱/照片结构上不在内；`consent.py:332-334` 对五个 purpose 都 `include_profile`。**但这只证明 prompt 侧就绪，不证明字段有产出**——产出侧见上条「可验前置」。
  - **fixture A（正例，判据以文件为准，不硬编码条数）**：`data/eval/jd_samples/jd_school_preference.md`（星链数科·数据分析实习生，JD 明示「985/211 院校优先」；旧名 `jd_school_filtered.md` 已废弃，因其说明文字自污染）+ `data/eval/jd_samples/expectations.json` 的 `jd_school_filtered.assertions`（7 条）。逐条比对响应：
    ```bash
    $PY - <<'PY'
    import json, re
    exp = json.load(open("data/eval/jd_samples/expectations.json"))["jd_school_filtered"]["assertions"]
    got = json.load(open("$EV/anl07_A.json"))["data"]
    def dig(o, path):
        cur = o
        for seg in path.split("."):
            if seg.endswith("[]"):        # "requirements[]" → 取数组后停止下钻
                cur = cur.get(seg[:-2]) if isinstance(cur, dict) else None
                break
            cur = cur.get(seg) if isinstance(cur, dict) else None
        return cur
    for a in exp:
        v = dig(got, a["path"])
        if a["op"] == "equals":      ok = v == a["value"]
        elif a["op"] == "nonempty":  ok = bool(v)
        elif a["op"] == "in":        ok = v in a["value"]
        elif a["op"] == "regex":     ok = bool(re.search(a["value"], str(v)))
        elif a["op"] == "every_has_field":
            arr = got["requirements"]; ok = bool(arr) and all(a["field"] in r and r[a["field"]] in a["value_in"] for r in arr)
        print("PASS" if ok else "FAIL", a["path"], "→", v)
    PY
    ```
    期望：A 例 **7 条全 PASS**（`hard_filter == true`、`threshold` 非空、`evidence` 非空、`school_tier` ∈ 枚举、`school_signal` 命中 `(985|211|双一流|院校|学校.{0,6}(门槛|要求|层次))`、`verdict` ∈ 枚举、`requirements[]` 每条都有 `candidate_status`）。
    **fixture 缺失时**：记 `SKIP(no-local-fixture)`（`data/` 已被 `.gitignore` 忽略，属用户本机物料），**不得判红、不得静默跳过**。
  - 归属：字段缺失/为 null/套话 → **coder**（`server/app/services/jd_analyzer.py` + `prompts.py`）；schema 未定 → **planner**；prompt 改了但调用点没换 → **coder**（`SENT-BUT-UNUSED` 的第二种形态：改了 prompt 但没接上）。

- [ ] **ANL-08 公司院校偏好：JD 没提院校就不得判「硬卡」**（P0，防编造，API-CONTRACT §7 `school_preference`，2026-10-23 新增）
  - 命令：
    ```bash
    curl -s -X POST $B/company-profiles -H 'Content-Type: application/json' \
      -d '{"company_name":"<真实公司>","sources":[{"type":"jd","ref":"'$jid'"}]}' > "$EV/anl08.json"
    $PY - <<'PY'
    import json
    sp = json.load(open("$EV/anl08.json"))["data"]["school_preference"]
    print(sp)
    assert isinstance(sp["threshold"], str) and sp["threshold"].strip(), "threshold 为空"
    assert isinstance(sp["preferred_tiers"], list)
    assert isinstance(sp["hard_filter"], bool)
    assert isinstance(sp["evidence"], str) and len(sp["evidence"]) >= 10, "evidence 过短 = 无依据"
    assert 0 <= float(sp["confidence"]) <= 1
    PY
    grep -nE "985|211|双一流" "$EV/anl08.json"   # 若出现层次词，必须能在 JD 原文或 sources 里溯源
    ```
  - 期望：① `threshold` 非空字符串（「985/211 优先，非硬卡」这类明示门槛也合法）；② **JD 原文未提院校时 `hard_filter` 必须为 `false`**；③ `evidence` ≥10 字符且能指回 JD 原句或 `sources_json`；④ `confidence` ∈ [0,1]。
  - **反例（见到即 FAIL）**：JD 只写「本科及以上」却给出 `hard_filter=true` + `threshold="985/211"`，且 `evidence` 里没有任何 JD 出处 → **编造门槛**，会让用户误判自己没戏而放弃投递。
  - **FAIL 形态（★这条最重要，写清楚才算判据）**：B 例的 FAIL **不是「没分析出东西」**，而是**假阳性：编造门槛**。模型为了让结论「看起来有用」，很可能虚构一个 985/211 门槛；用户据此会错判自己能投/不能投——所以「编造一个门槛」比「承认不限院校」**危险得多**。本条的判据必须能区分这两者，而不是只要求「有输出」。
  - **fixture B（反例，判据以文件为准）**：`data/eval/jd_samples/jd_no_school.md`（禾味食品集团·数据运营实习生，JD 原文写「**不设院校门槛，欢迎各类背景**」）+ `expectations.json` 的 `jd_no_school.assertions`（5 条）。期望：`hard_filter == false`（★核心）、`threshold` 不得以 `985|211|双一流|C9` 开头（`not_regex "^(985|211|双一流|C9)"`）、`evidence` 必须命中 `(未提|未出现|没有|不限|无.{0,2}院校|不设)`、`school_signal` 非空（即使不限也要给结论，如「不设门槛，校名不构成劣势」）、`verdict` ∈ 枚举。
  - **可执行的「编造门槛」区分办法（判 FAIL 并归 coder）**：
    ```bash
    JD=data/eval/jd_samples/jd_no_school.md
    $PY - <<'PY'
    import json, re
    ev = json.load(open("$EV/anl08_B.json"))["data"]["school_preference"]["evidence"]
    jd = open("data/eval/jd_samples/jd_no_school.md").read()
    claimed = re.findall(r"985|211|双一流|C9|C4", ev)
    in_jd   = re.findall(r"985|211|双一流|C9|C4", jd)
    print("evidence_claims:", claimed, "| jd_hits:", in_jd)
    print("FABRICATED" if claimed and not in_jd else "OK")
    PY
    ```
    判据：`evidence` 里出现 `985|211|双一流|C9|C4` 而 **JD 原文命中数为 0** → 直接判「**编造门槛**」FAIL，**归 coder**（不是「模型行为不可控」：若 LLM 反复编造，那是 prompt 设计与输出约束缺陷，仍归 coder；在 prompt 里加「无依据时 `evidence` 必须写『JD 未提院校要求』」并把 `hard_filter` 默认 `false`）。
  - **归因纪律（captain 2026-10-23）**：编造门槛发生在 `method=heuristic` → 归 **coder**（规则写错）；发生在 LLM 路径 → **同样归 coder**（缺后处理约束），**不得推给「模型不可控」**——prompt 里写「不要编造」不等于代码里拦住了。
  - 归属：编造/无依据 → **coder**（`server/app/services/company_profiler.py`）；契约未要求 evidence 溯源 → **planner**（D-19）。

- [ ] **ANL-09 未知院校不得被降级为「普通本科」**（P0，ANL-08 的镜像；captain t7 实测 → planner 复核 → supervisor 04:1x 复跑确认）
  - **⚠️ 现状已变，先读（含我自己的错）**：旧版 `server/app/services/jd_analysis.py:185-189` 有兜底 `if "大学" in name: return "普通本科"`，captain 与我当时都据此判 FAIL。**但那是旧快照**：现版 `tier_from_school_name`（`:221`，25 行）**没有**该兜底，docstring 明写「推断不出返回 None」。我 2026-10-23 04:1x 在当前代码上复跑：`北京师范大学→985`、`中国人民大学→985`、`示例大学→985`、`上海大学→211`、`南京信息工程大学→211`、`麻省理工学院→海外`、`Stanford University→海外`、`NUS→海外`、`XX大学→None`、`某某学院→None`。⇒ **代码侧已修复**，本条现状 = **PASS（静态）**，剩余由 t7 端到端验。
  - **supervisor 自身缺陷（T-1 旧快照，已记账）**：我「当场复跑」却仍报「全部普通本科」——说明我读的是旧模块/旧进程（`__pycache__` 或未重启实例）。**新纪律**：判据脚本 `import` 业务模块前必须确认「模块 mtime 晚于我的读取/进程启动时间」，否则复跑只是把旧结论复述一遍。
  - **severity 分档（planner 2026-10-23 补，务必分开断言）**：`SCHOOL_TIER_INFERRED` 在 `recognized=true` 时是 **`severity="info"`**，`recognized=false`（校名未收录）时才是 **`"warn"`**。判据必须按 `recognized` 取值再断言 severity，**不许用一条「severity==warn」通吃两种情形**（否则 info 那档会假红）。
  - **码名裁定（planner，采纳）**：**不新造 `SCHOOL_TIER_UNRECOGNIZED`**——实现是单码 `SCHOOL_TIER_INFERRED` + `details{recognized:bool}`；文档先造新码会让 t11 判「文档写了实现没有」。判据改用两条可机械验的事实：`severity=="warn"`、`details.recognized is False`。
  - 断言（据 `API-CONTRACT v1.18 §6.1` 四情形表）：
    1. **纯函数层**：未收录中文校名 → **`None`**（`assert f("XX大学") is None`），**不得**返回「普通本科」；
    2. **消费层**（`jd_analysis.py:262-285`）：`None` → `school_tier=="其他"` + `recognized=false` + `SCHOOL_TIER_INFERRED`(warn，message 含「未能识别」并建议手填)；
    3. `recognized=false` 时 `verdict`/`gap_notes`/`school_signal` **不得出现**「层次偏低」「院校竞争力偏弱」「学历背景不足」；
    4. 海外按**校名**判定（不看 JD 文本层）：`Stanford University`/`NUS` → `海外`；
    5. 手填 `school_tier` 优先且 `recognized=true`；
    6. **反向**：为变绿扩内置名单后，必须仍保留一个未收录样例（`XX大学`）走 `None→其他`，否则判「把测试用例写进实现」。
  - 命令（纯函数，无需起服务）：
    ```bash
    cd resume-warehouse && PYTHONPATH=server $PY - <<'PY'
    from app.services.jd_analysis import tier_from_school_name as f
    hit = {"北京师范大学":"985","中国人民大学":"985","上海大学":"211",
           "南京信息工程大学":"211","麻省理工学院":"海外","Stanford University":"海外"}
    bad = {k:(v,f(k)) for k,v in hit.items() if f(k)!=v}
    assert not bad, bad
    assert f("XX大学") is None and f("某某学院") is None and f("张三学院") is None, "未收录/虚构校名必须返回 None，不得兜底成普通本科"
    print("ANL-09 pure-function OK")
    PY
    ```
  - 为什么是 P0：与 ANL-08 互为镜像——编造门槛让用户错过能投的岗；把漏收录判成「普通本科」让用户放弃够得着的岗，且发生在我们自己的代码里。
  - 归属：历史缺陷（兜底成普通本科）→ **coder**（已修，`jd_analysis.py:221`）；判据方沿用旧快照误报 → **supervisor**（本条即实例）；契约缺「未识别语义」→ **planner**（D-37 已结案）。

- [ ] **ANL-10 院校信号二分：偏好不得判成门槛，门槛不得漏判**（P1，captain 2026-10-23 t7 实测 + supervisor 04:15 复跑；分两段：① 语义二分 ② 调用方式纪律）
  - **① 语义二分（三条必须同时正确，缺一条即 FAIL）**

    | 输入（干净夹具） | `hard_filter` | `preferred_tiers` | `threshold` |
    |---|---|---|---|
    | `985/211 院校优先`（`jd_school_preference.md`） | **false** | `["985","211"]` | 以「不限」打头且含「偏好」 |
    | `仅限 985/211 院校`（`jd_school_hard.md`） | **true** | `["985","211"]` | 含门槛语义 |
    | `不设院校门槛`（`jd_no_school.md`，无任何院校词） | false | **`[]`** | 以「不限」打头 |

    失败形态（`expectations.json.hard_fail` 已登记）：`fabricated_hard_filter`（无信号却 true）、`preference_as_gate`（偏好判成 true，**用户会误判自己被卡**）、`gate_as_preference`（门槛判成 false，用户白投）。
  - **状态：✅ PASS（2026-10-23 04:18:24 复测 10/10 全绿，代码 mtime `Oct 23 04:17:29 2026`；captain 04:18 独立复跑一致）——保留为回归哨兵，不得回退。**
    ```
    ["985/211 院校优先"]  → hard_filter=False, threshold='不限（偏好 985/211）', preferred_tiers=['985','211']   ✅
    ["仅限 985/211 院校"]  → hard_filter=True,  threshold='985',                  preferred_tiers=['985']        ❌ D-41（少 '211'）
    ["985 或 211 均可"]    → hard_filter=False, threshold='不限',                 preferred_tiers=[]             ❌ D-41（应 true + 两者）
    ["不设院校门槛"]        → hard_filter=False, threshold='不限',                 preferred_tiers=[]             ✅
    ```
    **「优先 ≠ 门槛」已修**（`jd_analysis.py` 现分 `HARD_VERBS`/`SOFT_VERBS` 两档常量）。**历史撤销记录**：我在 **04:15:09** 判「优先被判成硬门槛」并计划上报，但该文件 **04:15:24** 已被 coder 修改 → 我的结论在写下时即过期。这是 **T-1c 结论时效** 的首个实例，已记 `:87`；本条现**只保留仍成立的 D-41**。
    **注**：planner m02092 表格里的 `hard_filter=false` 我一度据 04:15:09 判为「str 路径值」——现按 04:17:16 复测，list 与 str 两条路径**都已正确**，该条分歧作废。
  - **② 调用方式纪律（新增，常驻）**：
    - `detect_school_gate(texts: Iterable[str])` 的**真实调用路径**是 `server/app/services/company_analysis.py:71`（传文本行列表）与 `:92`（传 `[joined]`）。
    - **任何判据调用被测函数，必须按真实调用路径传参**；传 `str` 会被按字符迭代、join 后每字符一行 → 永不匹配 → **静默返回「JD 全文未出现院校层次要求」**（`hard_filter=False, preferred_tiers=[]`）。
    - **必须先跑一次对照**：同一输入分别用 `[text]` 与 `text` 调用，断言两者结果一致；不一致 → **判据调用方式缺陷（归 supervisor）**，不是实现缺陷。本轮实例：我最初判 ANL-10 FAIL 用的就是 str 调用（假 FAIL），已按此改基。
    - 实现侧同时要求：`str` 入参必须**容错**（视为单元素）或**显式报错**，禁止静默返回「未提及」（captain 已入 coder 工单）。
  - 复验命令（**必须 `[jd]` 传列表**；跑前先 `ls -lT` 记代码时点）
    ```bash
    cd resume-warehouse && PYTHONPATH=server $PY - <<'PY'
    from app.services.jd_analysis import detect_school_gate
    pref = detect_school_gate(["985/211 院校优先"])
    hard = detect_school_gate(["仅限 985/211 院校"])
    none = detect_school_gate(["不设院校门槛，欢迎各类背景"])
    assert pref["hard_filter"] is False and set(pref["preferred_tiers"]) >= {"985","211"}, pref
    assert pref["threshold"].startswith("不限") and "偏好" in pref["threshold"], pref
    assert hard["hard_filter"] is True, hard
    assert none["preferred_tiers"] == [] and none["hard_filter"] is False, none
    # 对照：str 与 list 必须一致（不一致即判据调用缺陷）
    assert detect_school_gate(["985/211 院校优先"]) == detect_school_gate("985/211 院校优先"), "str/list 结果不一致"
    print("ANL-10 OK")
    PY
    ```
  - **evidence 可溯源（新增，planner 2026-10-23）**：`evidence` 必须能对上 JD 原文片段——`hard_filter=true` 时引号内文本必须能在 JD 里逐字找到；`hard_filter=false` 时若 JD 里**确实写着**「985/211 院校优先」却返回「全文未出现院校层次要求」，判 **FAIL（evidence 与 JD 文本矛盾）**。这是比字段值更难糊弄的一条：字段可以凑对，引文必须真的在。
  - **降级路径同标准**：LLM 不可用时走本地规则，仍须满足 ANL-09/ANL-10。`COMPETITIVENESS_FALLBACK`（`jd_analysis.py:666`）与 `SCHOOL_SIGNAL_FALLBACK`（`:687`）出现时，`competitiveness.school_tier` 与 `school_preference` **不得为 null**、未识别仍 `recognized=false`、不得出现贬低措辞。**「降级了所以字段可以缺」= FAIL**。
  - 归属：偏好被判成门槛 / 门槛被漏判 / `str` 静默返回「未提及」 → **coder**；判据用 `str` 调用得出假 FAIL、或没做两种传参对照 → **supervisor**（T-11）；`preferred_tiers` 非硬门槛语义若契约未写 → **planner**（D-37，已结案）。


---

### 1.5 COMPOSE（t8，owner: coder）— 组装 / 命名 / 导出


- [ ] **ANL-11 偏好/门槛动词分组与并列档位（D-41，P0；planner 称 `AC-ANL-11` / 并列档位称 `AC-ANL-12`）**（captain 2026-10-23 实测，t7 用户可见）
  - **编号对齐**：planner m02176 把本条的语义二分称 `AC-ANL-11`、把并列档位单称 `AC-ANL-12`；本清单 **ANL-11 = 本条（含并列档位表）**，**ANL-12 = `gap_notes` 可读性（D-42）**。两者内容不冲突、只是切分粒度不同，**不复述以免漂移**。
  - **为什么单列**：`仅限 985/211 院校` 曾只给 `['985']` → **211 硕士被判不达标**（`211`→`weak`、`985`→`strong`）；「优先」曾与「仅限」同组 → 偏好被判硬门槛。用户两种情况下都会放弃本来能投的岗位。
  - **判据：结构断言 + 反向断言（planner 建议，采纳）**
    1. **正向**：按下面用例表逐行断言 `hard_filter` / `preferred_tiers`；`threshold` **不做全等断言**（措辞会变）——软档断 `startswith("不限")` 且 `"偏好" in threshold`，硬档断**同时含 `985` 与 `211`**。
    2. **反向（更稳）**：`server/app/services/jd_analysis.py` 里 `HARD_VERBS`（`:32`）与 `SOFT_VERBS`（`:33`）必须是**两个独立常量**，且「优先/更佳/加分/青睐/欢迎/倾向」**只许出现在 `SOFT_VERBS`**：

       ```bash
       cd resume-warehouse && python3 - <<'EOF'
       import re, pathlib
       t = pathlib.Path("server/app/services/jd_analysis.py").read_text(encoding="utf-8")
       hard = re.search(r'HARD_VERBS = r"([^"]+)"', t).group(1)
       soft = re.search(r'SOFT_VERBS = r"([^"]+)"', t).group(1)
       assert "优先" not in hard, "「优先」混进硬门槛动词组 = 回退到 D-41"
       for w in ("优先","更佳","加分","青睐","欢迎","倾向"):
           assert w in soft, f"{w} 缺失"
       print("verb-groups OK")
       EOF
       ```
    3. **并列档位不得截断**：`985/211`、`985、211`、`985 和 211` 必须都收全两档（集合包含断言 `set(tiers) >= {"985","211"}`）。
  - **用例表（10 行，2026-10-23 04:18:24 实测全绿；mtime `Oct 23 04:17:29 2026`）**

    | 输入 | `hard_filter` | `preferred_tiers` | `threshold` |
    |---|---|---|---|
    | `985/211 院校优先` | false | `['985','211']` | `不限（偏好 985/211）` |
    | `985/211 院校优先，但不设院校门槛` | false | `['985','211']` | `不限（偏好 985/211）` |
    | `211 院校优先，985 优先` | false | `['211','985']` | `不限（偏好 211/985）` |
    | `仅限 985/211 院校` | true | `['985','211']` | `985/211` |
    | `仅限 985、211 院校` | true | `['985','211']` | `985/211` |
    | `仅限 985 和 211 院校` | true | `['985','211']` | `985/211` |
    | `要求 985 及以上` | true | `['985']` | `985` |
    | `985 优先，但仅限硕士` | false | `['985']` | `不限（偏好 985）` |
    | `不设院校门槛，学历不限` | false | `[]` | `不限` |
    | `本科及以上学历，计算机相关专业` | false | `[]` | `不限` |

  - **状态：✅ 已修复（04:18:24 复测全绿，代码 mtime 04:17:29）**——保留作**回归判据，不得回退**。历史上我 04:15:09 的「`hard_filter` 错」与 04:17:16 的「并列截断」两条结论**都已过期**（T-1c 实例×2：修复分别在 04:15:24、04:17:29）。
  - 契约依据：`docs/API-CONTRACT.md §7`（`:557` 起）「门槛动词分组：『优先』不是门槛」定版表（硬/软/明确负向三组，优先级 **负向 > 硬 > 软**，「并列档位不得截断」）。
  - **注意编号冲突**：planner 把动词分组也记作 **「D-39」**，而本清单 **D-39 = `check_export_pdf.py` 的 `--right-margin` 默认 42.5**（不同对象、同号）。跨 agent 沟通时**按内容指代，不按编号**。
  - 归属：动词分组被合并回单组、并列档位被截断、`threshold` 裸「不限」而 `preferred_tiers` 非空 → **coder**；判据用 `str` 调用或没做 `[text]`/`text` 对照 → **supervisor**（T-11）；动词分档语义未进契约 → **planner**（已进 v1.22）。
- [ ] **ANL-12 门槛不匹配时必须给出可读原因（D-42，P1）**（captain 2026-10-23 实测；状态：**✅ 已修复 04:19:01**）
  - 判据（三条，全部按返回值断言）：
    1. `gate_failed`（如 `school_tier='211'` + 门槛 `985`）→ `gap_notes` **非空**，且至少一条**含院校层次与门槛**；
    2. `unknown`（校名未收录 → `其他` + `recognized=false`）→ `gap_notes` **不得**出现「层次偏低/竞争力偏弱/学历不足」这类结论性贬低，只能提示「未识别，建议手填」；
    3. `verdict='weak'` 且 `gap_notes=[]` → **FAIL**（「弱」必须可解释）。
  - 复验命令（纯函数，不依赖 API/job）
    ```bash
    cd resume-warehouse && PYTHONPATH=server $PY - <<'PY'
    from app.services.jd_analysis import competitiveness
    gate = competitiveness(profile={"school_zh":"示例大学","school_tier":"211"},
                           school_preference={"hard_filter":True,"preferred_tiers":["985"],"threshold":"985"},
                           requirements=[{"skill":"SQL","candidate_status":"missing"}], warnings=[])
    assert gate["verdict"] == "weak" and gate["gap_notes"], gate
    assert any("985" in n and "211" in n for n in gate["gap_notes"]), gate["gap_notes"]
    unk = competitiveness(profile={"school_zh":"某某职业学院"},
                          school_preference={"hard_filter":True,"preferred_tiers":["985"],"threshold":"985"},
                          requirements=[], warnings=[])
    assert unk["school_tier_recognized"] is False and unk["school_tier"] == "其他", unk
    assert not any(k in "".join(unk["gap_notes"]) for k in ("偏低","偏弱","不足")), unk["gap_notes"]
    print("ANL-12 OK")
    PY
    ```
  - **实测（2026-10-23 04:19:01，`jd_analysis.py` mtime `Oct 23 04:17:29 2026`）**：`211` vs 门槛 `985` → `verdict=weak`、`gap_notes[0]='院校层次「211」不在 JD 门槛「985」内，需靠经历或成绩补足'`；未收录校名 → `tier=其他`、`recognized=False`、`verdict=medium`、`gap_notes` 无贬低措辞 ⇒ **已修复**，保留为回归判据。
  - 归属：`gate_failed` 却不写原因 / 对未识别院校下贬低结论 → **coder**；`gap_notes` 语义未进契约 → **planner**。

- [ ] **ANL-13 JD 分析必须看到仓库里的经历（正向防伪）**（P0，captain m03137，2026-10-23 新增）
  - **事实（真库，2026-10-23 05:48:07 那条 JD）**：6 条 `jd_requirement` 的 `matched_package_ids_json` **全部 `[]`**，`candidate_status` = `partial/satisfied/partial/missing/satisfied/missing`，evidence 明说「档案未体现 A/B 测试相关项目」「未列出 SQL/Python 技能或项目证明」——而仓库里就有 `赛车类游戏版本 AB 测试对照数据分析`（A/B 测试项目）、`杭州拓端数据科技有限公司 · 数据处理实习生` 的 SQL/Python 要点、`user_profile.skills_json` 首行「掌握Python、R、SQL」。
  - **根因（三处，已核）**：① `server/app/services/prompts.py:71` `ALLOWED_SOURCES["jd_analyze"]` = `(system_prompt, jd_text, company_note, user_instruction, profile)`，**没有 `package`**；② `server/app/repos.py` 的 `llm_brief()` 只投影六项 + `school_tier`，**不含 `skills_json`**；③ `server/app/services/jd_analysis.py:536` 与 `:719` 把 `matched_package_ids` **写死 `[]`**。
  - 判据（三条同时）：① preview 的 `fields[]` 里必须出现 `packages` 来源，且**至少 1 条真实经历要点文本**（`grep -c '"packages"' preview.json` ≥1 且 `packages[].extract_text()` 长度 > 0）；② 至少一条 requirement 的 `matched_package_ids` 非空，且该 id 在 `package` 表存在且 `status='ready'`；③ 反向：`fields[]` 有 `packages` 但 `matched_package_ids` 全空 ⇒ FAIL（「传了但不用」= SENT-BUT-UNUSED）。
  - 复验命令：
    ```bash
    cd resume-warehouse && curl -s $B/jds/$jid/analyze -X POST | jq '.data.preview.fields[] | select(.source=="packages") | .chars'
    sqlite3 data/app.db "select count(*) from jd_requirement where matched_package_ids_json != '[]'"
    ```
    期望：`chars > 0`；计数 **≥1**（现状 **0**）。
  - 归属：prompt 来源与 brief 投影缺 package/skills → **coder**；`matched_package_ids` 写死 → **coder**；是否允许仓库要点上云需契约确认 → **planner**（不新造来源类型，沿用 `package`）。

- [ ] **ANL-14 「不得让用户被自己的系统判成不行」（反向·最重要）**（P0，captain m03137）
  - 为什么单列：这是唯一一条**从用户损失出发**的判据——用户明明做过 A/B 测试、写过 SQL，系统却判 `missing`，代价是「错投一家公司」。同族于 SENT-BUT-UNUSED，但更严重：前者是「白付隐私成本」，后者是**主动给出错误结论**。
  - 判据（2026-10-23 **场景已更正**，captain m03367）：证据必须来自**对应的来源**，不能张冠李戴——
    - **A/B 测试**：`赛车类游戏版本 AB 测试对照数据分析` 这条 ready 包的 bullet 里确有「A/B 测试」字样 ⇒ 断言该 requirement `candidate_status != "missing"` 且 `evidence` 含该 bullet 的 **≥8 字连续片段**。
    - **熟练 SQL/Python**：**正确证据源是 `user_profile.skills_json` 第 1 行**（「数据分析类：掌握Python、R、SQL…」），**不是任何一条实习要点**——拓端包三条 zh 要点是「环境指标治理 / AI 检索采集 / 臭氧口径核查」，正文**没有** `SQL`/`Python` 字样。强行要求从实习要点引回 ≥8 字片段，只能引到不含 SQL 的句子，**那才是造假**。
    - 反向：`Rust`（用户确实没有）必须稳定 `missing`；把这两条包软删后重跑，`candidate_status` 必须回到 `missing`（证明「真看过」）。
  - 原判据（作废）：「用 `赛车类…` + `杭州拓端…` 两条 ready 包断言 SQL 被命中」——作废理由：拓端要点里没有 SQL/Python，该断言只能靠伪造引文通过。
  - 归属：三条任一不成立 → **coder**（`jd_analysis.py` 匹配与覆盖逻辑）；判据不区分「没证据」与「没看」→ **supervisor**。ate_status` 必须能回到 `missing`（证明是「看了」而不是「恒定 partial」）。

- [ ] **ANL-15 截断必须显式告知（`PACKAGES_TRUNCATED`）**（P1，captain m03137）
  - 判据：payload 超预算截断时必发 `PACKAGES_TRUNCATED{included,skipped}`；返回体 `context.packages_included` **等于**实际传入条数；反向：没截断却出现该码 ⇒ FAIL（与 D-51 同族：计数类字段必须可核）。

- [ ] **ANL-16 本地否决：模型说「没有」但有证据时必须改判**（P0，captain m03137）
  - 规则：`matched_package_ids` 非空而模型给 `missing` ⇒ 系统改判 **`partial`**，发 **`LLM_STATUS_OVERRIDDEN`**，`candidate_status_source = "local_override"`（不得透传模型的 `missing`）。
  - 判据：注入一条「明明有证据但模型返回 missing」的响应（monkeypatch provider 或夹具），断言 ① `candidate_status == "partial"`；② `candidate_status_source == "local_override"`；③ `warnings` 含 `LLM_STATUS_OVERRIDDEN`；④ 反向：`matched_package_ids` 为空时**不得**改判（无证据就该是 missing）。
  - 归属：改判逻辑缺失或透传 → **coder**；`candidate_status_source` 未进契约 → **planner**。

- [ ] **ANL-17 证据源必须包含 `skills_json`（正向 + 反向都判）**（P1，captain m03340，2026-10-23 新增）
  - 事实：拓端包的三条 zh 要点是「环境治理 / AI 采集 / 臭氧口径」，**正文里没有 `SQL`/`Python` 字样**；「熟练 SQL/Python」这类要求唯一可引的证据是 `user_profile.skills_json` 第 1 行（「数据分析类：掌握Python、R、SQL…」）⇒ 这是**证据源漏了 `skills_json`**，不是「再扫几个字段」。
  - 正向：构造 requirement「熟练掌握 SQL、Python」，`link_requirements()` 后 `candidate_status != missing`，且 `evidence` 中能引回 `skills_json` 原文 **≥8 字连续片段**（`Python、R、SQL` 等）；引不回原文 = FAIL（命中但无引文视同未命中）。
  - **反向（防「讨好式 partial」）**：构造一个用户**确实没有**的技能（如 `Rust`），必须稳定 `missing`；把任何 requirement 都判成 `partial`/`satisfied` 即为 FAIL。
  - 复验：DB 副本上跑 `link_requirements()`，`select matched_package_ids_json,evidence from jd_requirement where text like '%SQL%'` 非空且 evidence 含 `skills_json` 片段；反向 `%Rust%` 那条为 `missing`。归属：**coder**（`server/app/services/jd_analysis.py` 匹配源只挂了 packages 未挂 profile.skills）。

  - **C3 的判定方式（captain m03474 裁定 + m03510 选 A）**：**不落库的纯函数注入**——补一条 Rust 夹具 JD 必须写进用户真库，会让假 JD 出现在「已保存岗位」列表，故在匹配函数层证伪：喂 `{skill:"熟悉 Rust 后端开发"}`，断言 `matched_package_ids == []`、`matched_evidence == []`、`candidate_status == "missing"`；**同一次运行必须有正向对照**（喂 `"熟练掌握 SQL、Python"` → 命中且 `source=skills_json`），否则「函数永远返回空」也是绿的；断言禁出现具体包 id 与条数硬编码。
  - **落点选 A（进账本，不进旁路）**：见 `tests/acceptance/test_ac_anl_evidence.py` 加 `@check("AC-ANL-17b")` 的 pytest 用例（**coder**），并由 **planner** 在 `ACCEPTANCE.md` 条款区登记 `AC-ANL-17b`。**理由**：C3 判的是「本地匹配不讨好」这一产品行为，属可自动化条款；若只留在 §A.1 门脚本里（方案 B），账本永远少一条、覆盖率对不上真实条款数，且下次有人会以为「漏了条款」。**顺序约束**：先测后账——`@check("AC-ANL-17b")` 落地后再加账本行，否则 `make_index.py --check` 会因「分母 +1、未覆盖 +1」立刻非零（当前 `157/154/3/0/0`）。
  - **当前状态（2026-10-23 09:04，captain m03553 复核）**：`grep -rn "AC-ANL-17b" tests/ docs/` = **0** ⇒ `@check` 与账本行**两步都还没做**。故 **C3 现由 §A.1 门脚本的 `C3` 段判**（Rust→missing/空 + SQL/Python 正向对照），**账本分母不含 `AC-ANL-17b`**（**截至 2026-10-23 11:51:04**，`make_index.py --check` 实测 `分母 160 / 已执行 157 / MANUAL 3 / 未覆盖 0 / 撞号 0`，rc=0；旧值 157/154 已作废）。**若第 4 轮获批**，`AC-ANL-17b` 作为**唯一附加项**写进 t16 范围，且必须「先 `@check` 后账本行」；**若第 4 轮不含它**，本条按上面这句视为已知旁路，不留悬空。
  - **两个正交维度（captain m03570 纠正，写全枚举名）**：`matched_evidence[].source ∈ {package, skills_json, profile}` 答的是「**证据来自哪**」（package = 仓库经历要点 / skills_json = 档案技能行 / profile = 档案字段如 degree、major）；`candidate_status_source ∈ {llm, heuristic, local_override, manual}`（**四值**，优先级 `manual > local_override > heuristic > llm`，见 `docs/API-CONTRACT.md:611`/`:697`）答的是「**谁下的判断**」——`llm` = 模型 / `heuristic` = **离线启发式路径（`provider=off` 时的正常取值，不得判 FAIL）** / `local_override` = 本地否决改写 / `manual` = 人工。两者不可混写：判 ANL-17 用前者，判 ANL-16/21 用后者。
- [ ] **ANL-18 `lang=en` 装配必须优先选用 en 变体（有则必用）**（P1，captain m03340，2026-10-23 新增）
  - 事实（真库只读）：`package_bullet_variant` **zh 120 / en 11**（en verified 全 0），每活跃包 2–3 条 en ⇒ 英文产物仍大面积回退中文。
  - 正向：存在 en 变体的 bullet，en 装配必须用 en（导出文本层该行无 CJK 或 CJK 仅来自专有名词白名单）。
  - **反向**：某 bullet **有 en 变体却被回退** → FAIL；`LANG_FALLBACK.details.entries[]` 必须逐条列出**回退的是哪一条**（entry_key + 该行原文片段），只报计数 = FAIL。
  - 联合判据（X-A10 配对）：导出 PDF 文本层 `正文 CJK 行数 ≤ LANG_FALLBACK 回退条数`（正文行口径见 CMP-35：总行 − chrome 行）；只判其一 = `INCOMPLETE(单维绿)`。
  - 复验：`sqlite3 data/app.db "select lang,count(*) from package_bullet_variant where verified=1 group by 1"` 对照导出 PDF 的 CJK 行数；归属：**coder**（装配选变体逻辑 + 回退清单），**uier**（导出页回退提示文案）。

- [ ] **ANL-19 匹配证据必须带来源：`matched_evidence[].source` 与 `quote` 可溯源**（P1，captain m03367，2026-10-23 新增）
  - 事实：`matched_package_ids` 表达不了「证据来自技能栏/档案」——实测「熟练掌握 SQL、Python」已 `partial` 且 `evidence_hint` 引到技能行，但 `matched_package_ids = []`；而契约既定语义「空数组 = 确实没匹配到」⇒ 用户/前端会误读成「没命中」。planner 已补 `matched_evidence[]{source: package|skills_json|profile, ref_id, quote}`。
  - 判据：① `candidate_status != missing` 的 requirement，`matched_evidence[]` **不得为空**；② `source=skills_json` 时 `quote` 必须能在 `user_profile.skills_json[].line` 里**逐字找到**（`quote in line`）；③ `source=package` 时 `quote` 必须在对应 `package_bullet_variant.text` 里逐字找到，且 `ref_id` 指向真实包；④ `source=profile` 时限定 `field_values_json`/档案字段；任一引不回原文 = **FAIL（伪造引文）**。
  - 反向：`candidate_status == missing` 时 `matched_evidence` 必须为空（不许留旧引文）。
  - 归属：引文伪造/来源标错 → **coder**；`matched_evidence` 未进契约 → **planner**。

- [ ] **ANL-20 派生证据必须标注「推算」，不得冒充原文命中**（P0，captain m03570，2026-10-23 新增）
  - 背景：证据源扩到 7 个档案字段后，新增两类**派生**证据——校名 → 院校层次（`985/211/双一流/普通本科/海外`）、`grad_year ≥ 要求年份`。它们不是原文命中，而是规则推算；`matched_evidence[]` 里以 `derived: true` + `rule` 标出。
  - 判据：① 响应中 `derived === true` 的条目**必须**同时带 `rule`（非空字符串，写明用的哪条规则），缺 `rule` = FAIL；② 前端与导出**必须显示「推算」字样**（`web/` 与 PDF 文本层都要能查到），不得与 `source=package|skills_json|profile` 的原文命中同样式展示；③ **反向**：给一条 `derived` 证据却按「原文命中」展示（无「推算」标记、或 UI 里合并成同一标签）= FAIL；④ **反向**：把非派生条目标成 `derived: true`（伪造）也 FAIL——两侧都要判，不能只查一边。
  - 归属：证据字段/规则 → **coder**（`server/app/services/jd_analysis.py:1197`/`:1227` 的 `derived` 组装）；展示层 → **uier**；判据只查字段不查展示 → **supervisor**。

- [ ] **ANL-21 I26 双向：说「满足」就必须拿得出凭据**（P0，captain m03570，2026-10-23 新增）
  - 背景：原 I22 只约束单向（**有证据 ⇒ 不得 `missing`**），反向没约束，于是「我满足」可以零依据——真库曾出现 `增长实验…partial`、`毕业届别…satisfied`、`985/211…satisfied` 三行 `matched_evidence_json` 与 `matched_package_ids_json` **全空**。
  - 判据：① `satisfied`/`partial` 且零证据时，**必须**出现 `STATUS_WITHOUT_EVIDENCE`，且 `details.action ∈ {downgraded, flagged}`（`satisfied` → `downgraded` 且状态降为 `partial`；`partial` → `flagged` 保留结论）；② **反向**：造一条零证据的 `satisfied` → 必须变 `partial`、`candidate_status_source=="local_override"`、并发 `STATUS_WITHOUT_EVIDENCE`；③ **反向（尊重人工）**：`candidate_status_source=="manual"` 的行**不得**被降级、**不得**加该告警；④ 只告警不降级（`satisfied` 仍 `satisfied`）= FAIL——「满足」会进组装被当成已具备能力；⑤ **反向（防「一律降级」）**：造一条**有证据**的 `satisfied`（带 `skills_json` 或 `package` 的 `matched_evidence`）→ 必须**仍是 `satisfied`** 且**不带** `STATUS_WITHOUT_EVIDENCE`。只测「该降的降了」会让实现倾向「一律降成 partial」，那等于把真实满足也判成半满足。
  - 归属：`server/app/services/jd_analysis.py:1232 _enforce_evidence_backing()` → **coder**；判据漏掉「manual 例外」→ **supervisor**。

- [ ] **ANL-22 派生规则不得越界命中**（P1，captain m03570，2026-10-23 新增）
  - 判据：① `grad_year` 规则**只对**含 `20\d{2}` **且**含「届/以后/之后/起」的 requirement 生效；② `school_tier` 规则**只对**含 `985/211/双一流/C9/普通本科/海外` 的 requirement 生效；③ **反向**：`熟悉 Rust 后端开发` 这类无院校/年份语义的 skill **不得**因派生规则被命中（`matched_evidence` 为空、状态不为 `satisfied`）；④ **反向**：requirement 里出现数字但不是年份（如「3 年经验」）不得触发 `grad_year` 规则。
  - 归属：规则正则 → **coder**；用「拿一条真 JD 全跑一遍」代替边界用例 → **supervisor**。
- [ ] **CMP-01 只编入显式选中的 variant**（AC-BUILD-02，P0，**BLK-2**）
  - 命令：`curl -s $B/builds/$id/preview > "$EV/preview.html"`；用未选中变体的独有串反查。
  - 期望：`grep -c "<未选中变体的独有片段>" "$EV/preview.html"` = 0；`grep -c "<选中变体片段>"` ≥ 1。

- [ ] **CMP-02 profile 缺失仍可组装**（AC-BUILD-03，P0）
  - 命令：`curl -s -X POST $B/builds/$id/assemble | $PY -c "import json,sys;d=json.load(sys.stdin)['data'];print([w['code'] for w in d['warnings']], d['missing_slots'])"`（先清空 `user_profile.school_en/city`）
  - 期望：200；`warnings` 含 `PROFILE_INCOMPLETE` 且带 `missing_fields[]`；不 500。

- [ ] **CMP-03 槽位缺失语义按裁定执行**（AC-BUILD-04，P1，见 D-05）
  - 命令：`curl -s -X POST $B/builds/$id/assemble -w '\n%{http_code}\n'; grep -o '⟨[a-z0-9_.]*⟩' "$EV/preview.html" | sort -u`
  - 期望：`assemble` 返回 200 + `missing_slots[]` + `warnings[code=MISSING_SLOTS_RENDERED]`，preview 出现 `⟨slot_key⟩` 占位；若实现选择「组装中止」（ARCHITECTURE D10），必须 422 `MISSING_SLOTS` 且**两处文档已被 planner 改口**——不得三处口径并存。

- [ ] **CMP-04 排序稳定 + ir_hash 一致**（AC-BUILD-05，P1）
  - 命令：`for i in 1 2; do curl -s -X POST $B/builds/$id/assemble | $PY -c "import json,sys;print(json.load(sys.stdin)['data']['ir_hash'])"; done`
  - 期望：两次哈希相同；调换 `sort_order` 后哈希变化、preview 顺序随之变化。

- [ ] **CMP-05 页数估算误差**（AC-BUILD-07，P1）
  - 命令：对 3 个夹具分别 `assemble` 取 `est_pages`，`export` 后取真实页数：`$PY -c "import pypdf;print(len(pypdf.PdfReader('$pdf').pages))"`
  - 期望：`|est - 实际| ≤ 0.35` 页（3 个夹具全过）；超限时 `warnings` 有 `PAGE_OVERFLOW` + `suggestion`。

- [ ] **CMP-06 中文 PDF 主路径（reportlab + Songti idx6/1）**（AC-PDF-01/02/03/04，P0，**BLK-5**）
  - 命令：
    ```bash
    $PY -m pytest tests/acceptance -q -k "pdf_02 or pdf_03 or pdf_04"
    $PY - <<'PY'
    import pdfplumber, glob
    p = sorted(glob.glob('data/exports/**/*.pdf', recursive=True))[-1]
    t = "".join((pg.extract_text() or "") for pg in pdfplumber.open(p).pages)
    need = "·「」《》①②③％０１２３４５６７８９±÷≠≤≥龘鑫彧甯喆珺屾赟"
    print("file:", p)
    print("missing:", [c for c in need if c not in t])
    print("FFFD:", t.count("\ufffd"), "NUL:", t.count("\x00"))
    print("kangxi_ok:", "高级工程师" in t)
    PY
    ```
  - 期望：`missing: []`；`FFFD: 0 NUL: 0`；`kangxi_ok: True`；`TypeScript · React`、`GPA 3.8/4.0`、`2024.03–2024.09` 均可提取。

- [ ] **CMP-07 导出后文本自检**（AC-PDF-05，P0，见 D-06）
  - 命令：`sqlite3 data/app.db "select engine,text_verified,text_diff_json from build_artifact order by created_at desc limit 3"`
  - 期望：`text_verified ∈ {1,0,NULL}`（docx 为 NULL）；当抽取文本被人为破坏时 `text_verified=0` **且** `warnings_json` 含 `TEXT_LAYER_MISMATCH`，导出本身仍成功（不阻断）。

- [ ] **CMP-08 回退链**（AC-PDF-06/07，P0）
  - 命令：`curl -s -X POST $B/builds/$id/export -d '{"format":"pdf","engine":"chrome"}' -H 'Content-Type: application/json' -w '\n%{http_code}\n'`，任务完成后重跑 CMP-06 的断言；再注入 reportlab 异常（monkeypatch）跑 `engine=auto`。
  - 期望：`engine=chrome` 也能产出且字符断言通过；注入失败时自动回退且 `engine_used` 如实标注；两引擎都失败 → 500 `RENDER_FAILED`，`details.engine` 列出试过的引擎，`data/exports/` 文件数不变（无半成品）。

- [ ] **CMP-09 emoji 剥离**（AC-PDF-08，P0）
  - 命令：包文本含 `🚀✅🎯` → 导出 → `grep -o '"EMOJI_STRIPPED"[^}]*}' ` + 重跑 CMP-06 的 NUL 断言。
  - 期望：`warnings` 含 `EMOJI_STRIPPED` 且 `count` ≥1；产物无 `\x00`。

- [ ] **CMP-10 A4 与页数**（AC-PDF-09，P1）
  - 命令：`$PY -c "import pypdf;r=pypdf.PdfReader('$pdf');b=r.pages[0].mediabox;print(float(b.width),float(b.height))"`
  - 期望：`595.28 841.89`（±2）；`page_count ≤ build.page_limit`。

- [ ] **CMP-11 DOCX 可用**（AC-PDF-10，P1）
  - 命令：`$PY -c "import docx;d=docx.Document('$docx');print(len(d.paragraphs))"`
  - 期望：无异常，段落数 > 10，中文可读。

- [ ] **CMP-12 禁用引擎不得出现**（P0，**BLK-5** 风险）
  - 命令：`grep -rnE "weasyprint|soffice|UnicodeCIDFont|STSong-Light" server/app/ --include=*.py ; echo rc=$?`
  - 期望：零命中（注释里解释「为何禁用」可以，但不得有调用/import）。

- [ ] **CMP-13 命名 17 案**（AC-NAME-02，P0，**BLK-6**）
  - 命令：`$PY -m pytest tests/acceptance -q -k name_02 -v`，并抽查 3 条手工：
    ```bash
    curl -s -X POST $B/naming/validate -H 'Content-Type: application/json' -d '{"pattern":"{position}-{name}-{school}","build_id":"'$bid'"}' | $PY -m json.tool
    curl -s -X POST $B/naming/validate -H 'Content-Type: application/json' -d '{"pattern":"{salary}"}' | $PY -c "import json,sys;d=json.load(sys.stdin)['data'];print(d['valid'],[e['code'] for e in d['errors']])"
    curl -s -X POST $B/naming/validate -H 'Content-Type: application/json' -d '{"pattern":"../../etc/{name}"}' | $PY -c "import json,sys;d=json.load(sys.stdin)['data'];print(d['valid'],repr(d['filename']))"
    ```
  - 期望：17 案 `17 passed`（夹具 `张三/示例大学/数据分析实习生/字节跳动/v1/2026-10-23`）；抽查：合法 `data.filename="数据分析实习生-张三-示例大学.pdf"`；未知变量 `valid=False` + `NAMING_UNKNOWN_VAR`；穿越 pattern → `valid=True` 但 `filename` 不含 `..`、不含 `/`、不以 `.` 开头。

- [ ] **CMP-14 validate 是纯函数且恒 200**（AC-NAME-01，P0）
  - 命令：
    ```bash
    for p in '{school' '' '{date:%Q}' '{name}{{}}'; do curl -s -o /dev/null -w "%{http_code} " -X POST $B/naming/validate -H 'Content-Type: application/json' -d "{\"pattern\":\"$p\"}"; done; echo
    grep -nE "INSERT|UPDATE|DELETE|open\(" server/app/api/naming.py ; echo rc=$?
    ```
  - 期望：四类垃圾输入全部 `200`；`naming.py` 无写库/写文件调用；响应含 `valid/resolved/filename/variables[]/warnings[]/errors[]`。

- [ ] **CMP-15 非法 pattern 不落库、不落文件**（AC-NAME-03/04，P0，**BLK-6**）
  - 命令：
    ```bash
    ls data/exports/**/* 2>/dev/null | wc -l > /tmp/before
    curl -s -X PATCH $B/builds/$bid -H 'Content-Type: application/json' -d '{"naming_pattern":"{position}-{name}-{school"}' -w '\n%{http_code}\n'
    sqlite3 data/app.db "select naming_pattern from resume_build where id='$bid'"
    ls data/exports/**/* 2>/dev/null | wc -l > /tmp/after; diff /tmp/before /tmp/after && echo "FILES_UNCHANGED"
    ```
  - 期望：422 + `NAMING_SYNTAX`；DB 中 pattern 未变（仍是旧值）；文件数不变。缺 `school_zh` 导出 → 422 `NAMING_MISSING_VAR`，`hint` 指向「去设置填个人信息」；**绝不产出** `undefined.pdf` / `-示例大学.pdf` / `..pdf`（正则复核：`find data/exports -name '*.pdf' | grep -E '^-|--|^\.\.|undefined'` 为零）。

- [ ] **CMP-16 同名冲突后缀**（AC-NAME-05，P1）
  - 命令：同 pattern 连续导出两次，`sqlite3 data/app.db "select filename from build_artifact order by created_at desc limit 2"`；再 `overwrite=true` 导一次。
  - 期望：`-2`/`-3` 后缀且 `resolved` 不变、artifact 记 `collision_suffix`；`overwrite=true` 时覆盖同名文件并新增 artifact 版本。

- [ ] **CMP-17 默认模板来自 app_setting**（AC-NAME-06，P1）
  - 命令：`curl -s -X POST $B/naming/validate -H 'Content-Type: application/json' -d '{}' | grep -o '"pattern":"[^"]*"'; sqlite3 data/app.db "select value from app_setting where key='naming_template'"`
  - 期望：无 `pattern` 时用 `app_setting.naming_template`，初始 `{position}-{name}-{school}`；`PUT /settings` 改后立刻生效。

- [ ] **CMP-18 落盘路径不可逃逸**（AC-NAME-08，P1）
  - 命令：`$PY -c "import os,glob;print([p for p in glob.glob('data/exports/**/*',recursive=True) if not os.path.realpath(p).startswith(os.path.realpath('data/exports'))])"`
  - 期望：`[]`；用 `{name}=../../x` 的 override 再导一次仍为 `[]`。

- [ ] **CMP-19 artifact 记录完整**（AC-LOC-04，P1）
  - 命令：`sqlite3 -header -column data/app.db "select format,engine,filename,rel_path,bytes,length(sha256),text_verified from build_artifact order by created_at desc limit 3"`
  - 期望：每行 `bytes>0`、`length(sha256)=64`、`rel_path` 以 `YYYY/rb_*/` 开头；磁盘文件大小与 `bytes` 一致。

- [ ] **CMP-20 照片渲染：中英两版右上角 89.3×89.3pt（距顶 3.8pt）**（captain 2026-10-23 用户拍板，P0，**BLK-5**）
  - 冻结尺寸：**89.3 × 89.3 pt** 方块，右对齐正文右边界，方块顶距页面上边 **3.8 pt**；中英两版**都要**渲染。
  - **测量纪律（captain 2026-10-23 两处纠错，务必先读）**：
    1. **右缘距离 = `page.width − im["x1"]` = 实测 9.13pt**；`98.42` 是「照片左边到页右缘」的距离（`595.5 − 497.08`），**不是右边距**。uier 据此修的 `print.css` 才是对的——修前照片整体**偏左 16.2mm**，属真 bug。
    2. **pdfplumber 的 `top` 未按 MediaBox 归一化**：样张 `MediaBox=(0,-7.83,595.5,834.42)`，`im["top"]` 相对 MediaBox 顶算，于是「距页顶」被量成 **-4.01**，真值是 **3.82**（差 7.83）。测量必须写 `top_norm = im["top"] − page.bbox[1]`。**我们自己的导出 PDF 无此偏移**（MediaBox 下边 = 0），但同一段代码两种 PDF 都要成立，所以一律归一化。
    3. **判据自身的准入自检（先跑原件，应 PASS）**：拿 `data/imports/sample_zh.pdf` 跑一遍你的照片几何判据，必须得到 `w=89.28 / h=89.28 / top_from_page_top=3.82 / right_gap=9.13` 且 **PASS**。原件是合格样本，若它判 FAIL，**先怀疑判据**（未归一化 / 把 `595.5−497.08` 当右边距 / 用了 `im["top"]+mediabox.bottom`），不要先怀疑产品。captain 的 `data/eval/check_export_pdf.py --pdf data/imports/sample_zh.pdf --photo --right-margin 15.62` 已按此口径实现并通过。
    4. **任何照片几何判据都必须先做这一步归一化**：正解 `top_norm = im["top"] − page.bbox[1]`（`page.bbox[1]` 即 MediaBox 下边，样张 **−7.83**，自产 PDF 为 0）；等价写法 `im["top"] − mediabox.top`。**错解**：写成 `im["top"] + mediabox.bottom` 会得 **−11.84**，把用户原件判成「照片出界 11.84pt」。captain 的 `data/eval/check_export_pdf.py` 已按正解实现（输出写明「距页顶 3.82pt（已按 mediabox.bottom=7.83 归一）」），可作交叉证据。
  - 可复制实测片段（captain 指定 t10 复验用）：
    ```bash
    $PY - <<'PY'
    import glob, pdfplumber
    pdf = sorted(glob.glob("data/exports/**/*.pdf", recursive=True))[-1]
    pg = pdfplumber.open(pdf).pages[0]
    mb_top = pg.bbox[1]                      # MediaBox 下边（样张 -7.83，自产 0）
    print("page", round(pg.width,2), round(pg.height,2), "| mb_top", round(mb_top,2))
    imgs = pg.images
    assert len(imgs) == 1, f"期望 1 张照片，实际 {len(imgs)}"
    im = imgs[0]
    w, h = im["x1"] - im["x0"], im["bottom"] - im["top"]
    top_norm = im["top"] - mb_top            # ← 归一化，否则整页偏移
    right_gap = pg.width - im["x1"]
    print("w=%.2f h=%.2f top_norm=%.2f right_gap=%.2f x1=%.2f" % (w, h, top_norm, right_gap, im["x1"]))
    assert abs(w - 89.3) <= 0.5 and abs(h - 89.3) <= 0.5, "尺寸不是 89.3pt 方块"
    assert abs(top_norm - 3.8) <= 1.0, "距页顶不是 3.8pt"
    assert 6 <= right_gap <= 14, "右缘贴边距离越界（应≈9.13pt）"
    print("PASS")
    PY
    ```
  - 期望：① 两版各恰好 1 张图，`|w-89.3| ≤ 0.5`、`|h-89.3| ≤ 0.5`（pt）；② `right_gap = page.width − x1 ≈ **9.13pt**`（±3pt；**不要**用 98.42 判，那是左边到右缘），且 `x1` 与正文右边界对齐（±1pt），**不是**左半边/居中（历史 bug：修前整体偏左 **16.2mm**）；③ `top_norm ≈ 3.8`（±1pt，**必须 `im["top"] − page.bbox[1]` 归一化**，否则样张会被量成 -4.01）；④ 导出页「包含照片」开关**默认开启**（`grep -n "include_photo" web/*.html` 命中 `checked`）；⑤ 无照片时每个正文块的 `top` 与带照片版**逐块相等**（布局不错位，不得靠压缩正文硬塞）；⑥ 英文版单独验（不能只改 CSS 却落空）；⑦ 照片字节不出现在 payload（X-F8）。
  - 无照片对照的执行方式：`sqlite3 data/app.db "update user_profile set photo_path=null"` → 再导一次 → 逐块比较正文 `top`（容差 ±1pt，且**两边都按 MediaBox 归一化**）。
  - 归属：尺寸/位置错、中英不一致、贴边距离不等于 ≈9.13pt → **coder**（`render_pdf.py`）；`print.css` 偏左 16.2mm 历史 bug → **uier**（已修，复验保留）；把未归一化的 `-4.01` 当成实现错 → **supervisor**（判据错，不记 coder）；用 98.42 当右边距 → **supervisor**（同上）。

- [ ] **CMP-21 技能区必须整句原文逐行渲染（禁止 tag 化）**（captain 2026-10-23 用户裁决，P0，**BLK-6 同类**）
  - 背景（用户原话意思）：`数据分析类：掌握Python、R、SQL等编程语言，可独立进行数据清洗、统计分析与可视化处理` 这类**整句逐行**必须保持原样；**拆 tag 会失去规整感，HR 看到一堆 tag 却不知道具体情况会莫名其妙**。精确匹配改由**隐式索引**满足：`UserProfile.skills_json[].tokens` 只给 matcher 用、**永不渲染**。
  - 前置（**已解锁，2026-10-23 03:17 逐项实测，不是听汇报**）：契约已落 —— `DATA-MODEL.md:68` 列 `skills_json`（`{line, category, tokens, order}`）；`DATA-MODEL.md:80 §1.1` 展示/索引分离（`line` 唯一渲染源、`tokens` 派生永不渲染）；`ARCHITECTURE.md:514 §7.6` 内容结构约束 + `:545 ADR-19`；`ACCEPTANCE.md:199-202` **AC-SKILL-01/02/03/04**；`API-CONTRACT.md §14.1` 新增 `COURSES_TRIMMED`（表头 15 条 = 12 行 + 折算 3 条，`grep -c COURSES_TRIMMED` 实测 3）。本条**可验**，不再记 `BLOCKED`。**唯一例外**：CMP-22 的**反向基线段**仍 `PENDING(no-artifact)`（`data/exports/` 实测为空）。
  - 命令：
    ```bash
    curl -s -X POST $B/builds/$bid/export -H 'Content-Type: application/json' -d '{"format":"pdf"}' > "$EV/cmp21.json"
    $PY - <<'PY'
    import json, glob, pdfplumber
    prof = json.load(open("data/exports/_profile_snapshot.json"))["data"]   # 或 GET /api/v1/profile
    lines = [s["line"].strip() for s in prof["skills_json"]]
    p = sorted(glob.glob("data/exports/**/*.pdf", recursive=True))[-1]
    text = pdfplumber.open(p).pages[0].extract_text()
    seg = text.split("职业技能", 1)[1].split("\n\n", 1)[0]              # 技能区片段
    rows = [r.strip() for r in seg.split("\n") if r.strip()]
    print("expected_rows:", len(lines), "rendered_rows:", len(rows))
    print("verbatim:", rows == lines, "diff:", [(a, b) for a, b in zip(lines, rows) if a != b])
    print("token_leak:", [t for s in prof["skills_json"] for t in s["tokens"] if t in rows])
    PY
    ```
  - 期望：① 技能区**行数 == `len(skills_json)`**、**逐行 `strip()` 后逐字相等**（标点/全角半角/换行位置都算）；② 行序与 `skills_json` 一致；③ `token_leak` 为空（`tokens` 不得单独成行，也不得在原句外额外出现）；④ tokens 为空时仍逐字相等（见 CMP-23）。
  - 归属：渲染改写/断行/丢行 → **coder**；契约缺 `skills_json` → **planner**（D-18，已于 2026-10-23 03:17 解锁）。

- [ ] **CMP-22 反向：导出 PDF 不得出现 tag 块 / 标签云**（P0；**基线段 PENDING(no-artifact)**）
  - 为什么单列反向条：拆 tag 是「看起来更现代」的诱惑，很容易被后来者当成优化做回去，而它恰好是用户明确否决的形态。
  - 判据（可执行版，两个维度都要）：
    ```bash
    # ① 文本维度：**只判「职业技能」section 内的行**——任一行不得被 `|`/`·`/`,`/`/` 切成 ≥3 个 ≤12 字符碎片
    #    （2026-10-23 05:40 实测假阳性 3 行：课程列表的 `、`、技术文本里的 `PM₁/PM₂.₅`、bullet 行首 `·`；
    #     行首 `·` 是列表标记不是分隔符，课程 `、` 属教育段、技术文本属项目段——**不分 section 判会永远红**）
    $PY - <<'PY'
    import re, glob, pdfplumber
    p = sorted(glob.glob("data/exports/**/*.pdf", recursive=True))[-1]
    seg = pdfplumber.open(p).pages[0].extract_text().split("职业技能", 1)[1].split("\n\n", 1)[0]
    for r in [x.strip() for x in seg.split("\n") if x.strip()]:
        frs = [f.strip() for f in re.split(r"[|·,，/]", r) if f.strip()]
        short = [f for f in frs if len(f) <= 12]
        assert not (len(frs) >= 3 and len(short) >= 3), ("TAG-LIKE", r, frs)
    PY
    # ② 结构维度：不得出现标签容器（模板/前端两处都查）
    grep -rnE 'class="[^"]*(tag|chip|badge)' server/app/ web/ --include=*.py --include=*.html --include=*.js
    ```
  - **基线段（按 §0.3 规则，反向判据必须跑基线）**：当前 `data/exports/` 无 PDF 产物 → 记 **`PENDING(no-artifact)`**；**t10 产出首份 PDF 后必须补跑一次并记录基线值**（`max_fragments_per_line`、`tag_like_rows=0`、`tag_container_hits=0`）。**无产物时本条不得记 PASS**（否则变成摆设）。
  - 期望：`tag_like_rows == 0`；`tag_container_hits == 0`；且 CMP-21 的逐字相等同时成立（两条互为约束）。
  - 归属：渲染出 tag/chip → **coder**（若 PDF 侧）或 **uier**（若前端预览先拆了 tag，导出照抄）。

- [ ] **CMP-23 隐式索引降级：`tokens` 清空后整句匹配仍全绿**（P0，防「索引缺失就崩」）
  - 背景：`tokens` 是给 matcher 用的加速索引、永不渲染；但**索引缺失不能让系统崩**，否则用户换一份简历/手改技能行就整链挂掉。
  - 命令：
    ```bash
    sqlite3 data/app.db "update user_profile set skills_json = json_set(skills_json, '\$[0].tokens', json('[]'), '\$[1].tokens', json('[]'), '\$[2].tokens', json('[]'))"
    curl -s -X POST $B/builds/$bid/assemble -H 'Content-Type: application/json' -d '{"selections":[...]}' | head -c 400
    curl -s -X POST $B/builds/$bid/export -H 'Content-Type: application/json' -d '{"format":"pdf"}' | head -c 400
    ```
  - 期望：① assemble/export 均 `200`（不得 500、不得 `KeyError`/`IndexError`）；② matcher 降级为**整句子串匹配**（JD 关键词若出现在某行 `line` 内即算命中，`coverage` 数值与 tokens 齐全时**允许不同**但必须可比、不得为 `null`）；③ 导出 PDF 技能区仍 `len(skills_json)` 行且逐字相等（CMP-21 全过）；④ 不丢行（导入→组装→导出三处行数一致）。
  - 归属：崩/丢行 → **coder**（importer/assembler）；若契约没说 `tokens` 可空 → **planner**（D-18，已于 2026-10-23 03:17 解锁）。

- [ ] **CMP-24 课程门数：`trim_courses` 默认 false；裁剪必须报 warning**（P0）
  - 基准：源简历教育段课程 **7 门**（`expected_zh_v10.json` 教育 entry `course_list_count_min: 7`；以文件为准，不写死）。
  - 命令：
    ```bash
    curl -s $B/settings | $PY -c "import json,sys;print(json.load(sys.stdin)['data']['settings'].get('trim_courses'))"   # 期望 None/false（默认不裁剪）
    # 默认导出后数课程行
    $PY -c "import json,glob,pdfplumber;p=sorted(glob.glob('data/exports/**/*.pdf',recursive=True))[-1];print(pdfplumber.open(p).pages[0].extract_text().count('必修'))"
    # 开启裁剪：PUT settings trim_courses=true 后重新 assemble+export，读 build.warnings
    curl -s $B/builds/$bid | $PY -c "import json,sys;d=json.load(sys.stdin)['data'];print([w for w in d.get('warnings',[]) if w['code']=='COURSES_TRIMMED'])"
    ```
  - 期望：① 默认 `trim_courses` 为 `false`/缺省 → 导出课程门数 **== 源门数（7）**；② `true` 时 `build.warnings` 必须含被裁课程**名字**（`COURSES_TRIMMED` 的 `details.courses[]` 非空），不能只报数字；③ 裁剪不得删掉教育段的校名/专业/GPA（`facts_must_keep` 四项仍在，见 IMP-13 基准）。
  - 归属：默认值错/不报警 → **coder**；契约未定义 `trim_courses` → **planner**（D-18，已于 2026-10-23 03:17 解锁）。

- [ ] **CMP-25 荣誉：不得自成一个 section；可隐藏但主体不得消失**（P0）
  - 背景：用户要求「校园活动」下的荣誉保持从属关系，不能因为好排版就提成独立板块。
  - 命令：
    ```bash
    $PY - <<'PY'
    import json, urllib.request
    B = "http://127.0.0.1:%s/api/v1" % json.load(open("data/runtime/app_port"))["port"]
    d = json.load(urllib.request.urlopen(B + "/imports/%s/draft" % jid))["data"]
    heads = [s["heading"] for s in d["sections"]]
    print("headings:", heads)
    print("honor_sections:", [h for h in heads if ("荣誉" in h or "奖项" in h)])
    PY
    # 隐藏该 bullet 后导出一次，断言 entry 主体（org/date/role）仍在
    ```
  - 期望：① section 标题列表**不得出现**独立「荣誉」「奖项」块，**除非源简历本来就有**（判定方式：与源 PDF 抽取文本的标题集合比对，源里没有就是被拆出来的）；② 荣誉作为 `entry.bullets[]` 中的可选 bullet，**可隐藏**（`hidden=true`）；③ 隐藏后该 entry **仍渲染** `org`/`date_range`/`role`（不得整条消失）；④ 隐藏是 build 级选择，不得改 import 产物。
  - 归属：擅自提级成 section → **coder**（importer 分类）；隐藏导致整条消失 → **coder**（assembler/render）。

- [ ] **CMP-26 教育段 `facts[]` 必须逐字渲染（同 CMP-21 口径）**（P1，captain 2026-10-23 裁定）
  - 为什么单列：导入侧把「专业成绩：GPA 3.56/4 86.53/100 CET4：562 CET6:508」与「主修课程：…」放进 `facts[]` 而 `bullets=[]`（2026-10-23 实测 zh draft：教育段 `facts` **2 条**、`bullets` **0 条**）。若组装/导出只认 `bullets`，这两行会在**不报错**的情况下整体消失——用户看到的就是「教育背景只剩学校名」。
  - 可复制实测片段（captain 指定 t10 复验用；**从 API 取 facts，不读 `data/exports/*.json` 旧产物**）：
    ```bash
    B=$(python3 -c "import json;d=json.load(open('data/runtime/app_port'));print('http://127.0.0.1:%d/api/v1'%d['port'])")
    IID=$($PY -c "import json;print(json.load(open('$EV/imp_zh.json'))['data']['import_id'])")   # 或复用已导入的 id
    curl -s "$B/imports/$IID/draft" > "$EV/cmp26_draft.json"
    curl -s -X POST "$B/builds/$bid/export" -H 'Content-Type: application/json' -d '{"format":"pdf"}' > "$EV/cmp26_export.json"
    $PY - <<'PY'
    import json, glob, pdfplumber
    pdf = sorted(glob.glob("data/exports/**/*.pdf", recursive=True))[-1]
    pages = pdfplumber.open(pdf).pages
    print("pdf:", pdf, "pages:", len(pages), "| mediabox.top:", round(pages[0].bbox[1], 2))
    text = "\n".join(p.extract_text() or "" for p in pages)
    blocks = json.load(open("$EV/cmp26_draft.json"))["data"]["draft"]["blocks"]
    # 教育段 entry 的 facts（block_type=entry 且 entry.org 含校名）
    want = [f for b in blocks
            if b["block_type"] == "entry" and "大学" in (b["entry"].get("org") or "")
            for f in b["entry"].get("facts", [])]
    miss = [f for f in want if f.strip() not in text]
    print("facts:", len(want), "missing:", miss)
    assert want, "N/A(no-facts)：草稿里教育段没有 facts，本条不得记 PASS"
    assert not miss, "facts 在 PDF 中未逐字出现，教育段关键信息丢失"
    for must in ("GPA 3.56/4", "86.53/100", "CET4：562", "CET6:508", "主修课程："):
        assert must in text, "关键数字/前缀缺失: " + must
    print("PASS")
    PY
    ```
  - **测量纪律**：文本抽取不受 MediaBox 偏移影响（`page.extract_text()` 与坐标无关），**但同一脚本里若要同时量照片位置，必须按 `im["top"] − page.bbox[1]` 归一化**（见 CMP-20）；否则会把样张的 `-4.01` 当真值。**我们自己的导出 PDF MediaBox 下边为 0，无此偏移**。
  - 期望：教育段 `facts[]` 每条 `strip()` 后在 PDF 文本中**逐字存在**（`GPA 3.56/4`、`86.53/100`、`CET4：562`、`CET6:508`、`主修课程：` 前缀全在）；缺失数 `0`。**空 `facts` 时本条记 `N/A(no-facts)`**，不得记 PASS。
  - 归属：渲染丢 `facts` → **coder**（`render_pdf.py` / `assembler.py` 没把 facts 拼进教育段）；importer 把该进 `bullets` 的内容塞错字段 → **coder**（importer），并同步 IMP-13 复验（facts 丢了数字一样要抓）。
  - **当前状态：`BLOCKED(no-build)`**——导出链路（COMPOSE lane）尚未交付、`data/exports/` 无 PDF，基线记 `PENDING(no-artifact)`；t8/t9 产出首份含教育段的 PDF 后必须补跑并记基线值。

- [ ] **CMP-27 照片候选不变量 + 解码失败必报（`PHOTO_DECODE_FAILED`）**（P0，captain 2026-10-23 新缺陷 D-28）
  - 背景（captain 实测）：合成 PDF 内嵌 `/FlateDecode` 裸像素（`doc.images[0].data` 头 `b'\xc8\xd2\xe1'`，120000B）→ `to_png()` 抛 PIL `UnidentifiedImageError` → 返回 `None` → `photo_stored=None` → **整个照片分支被跳过**，`warnings` 零条目，但 `extracted_photo` 仍返回 `available=true`（**无 `attachment_id`**）⇒ UI 给用户一个「点不动的候选」。真实样张是 JPEG（`b'\xff\xd8\xff\xdb'`）正常 266×266，所以这个洞只在合成/Word 导出件上暴露。
  - **不变量（硬断言，违反即 FAIL）**：`extracted_photo.available == true` **⇔** `attachment_id` 非空 **且** `file` 指向真实存在的文件（`os.path.getsize > 0`）。**不得出现 `available=true` 且 `attachment_id` 缺失**。
  - **渲染不变量**：`available=false` 时导出 PDF **零图片**，且不得出现 0 字节图片块/占位方块。
  - **观测不变量**：解码失败必须发 `PHOTO_DECODE_FAILED`（`severity="warn"`，附 `reason`），**不得静默**（当前只有 `note` 字段，warnings 零条目 = FAIL）。
  - 命令：
    ```bash
    curl -s -F "file=@server/tests/fixtures/sample_with_photo.pdf" $B/imports > "$EV/cmp27.json"
    $PY - <<'PY'
    import json, os
    d = json.load(open("$EV/cmp27.json"))["data"]
    ex = d["extracted_photo"]; ws = [w["code"] for w in d["warnings"]]
    print("available:", ex.get("available"), "attachment_id:", ex.get("attachment_id"), "warnings:", ws)
    if ex.get("available"):
        assert ex.get("attachment_id"), "available=true 但 attachment_id 缺失（UI 会给出点不动的候选）"
        assert ex.get("file") and os.path.getsize("data/" + ex["file"]) > 0
        assert "PHOTO_DETECTED" in ws, "带图夹具必须产出 PHOTO_DETECTED"
    else:
        assert "PHOTO_DECODE_FAILED" in ws, "解码失败必须发 PHOTO_DECODE_FAILED，不得静默"
    PY
    ```
  - 期望：`server/tests/fixtures/sample_with_photo.pdf`（合成 200×200 方块、无 PII）→ `available=true` + `attachment_id` 非空 + `PHOTO_DETECTED`；另造一份损坏/裸像素图 → `available=false` + `PHOTO_DECODE_FAILED`。
  - **状态（2026-10-23 03:44，`/health.build=b8c335e-dirty` 全新进程）：`AC-IMPORT-14` → PASS**。实测两条路径：① `sample_with_photo.pdf` → 201 / `warnings=['IMPORT_FALLBACK_LLM','PHOTO_DETECTED']` / `available=True` + `attachment_id=01a16522…` + 200×200；② `sample.pdf`（纯文本）→ 201 / `warnings=['IMPORT_FALLBACK_LLM']` / `available=False` + `attachment_id=None`。不变量「`available=true` ⇒ `attachment_id` 非空」两路均成立；导入前后 `photo_path` 逐字不变。反向断言保留：任一路径出现 `available=true` 且无 `attachment_id` → **FAIL**。
  - 归属：`to_png()` 不支持 `/FlateDecode` 裸像素、失败静默、`available/attachment_id` 不一致 → **coder**（`server/app/services/importer.py`）；用纯文本 PDF 验照片 → **夹具作者（caption 自身）**，不记 coder（见 §0.3.1 T-3）。

- [ ] **CMP-28 活跃模板必须恰有一个默认（0 个 → 409 而非 500；>1 → 违约）**（P1，t8 前置，captain m01808）
  - 背景：assemble 需要确定默认模板；新增「无默认 → 409 `NO_DEFAULT_TEMPLATE`」守卫后，**存量库必须同时给出迁移路径**（自动选一个/提示一键设默认），不能让用户自己点。
  - 判据：
    ```bash
    sqlite3 data/app.db "select is_default, count(*) from template where deleted_at is null group by 1"
    curl -s $B/templates | $PY -c 'import json,sys; d=json.load(sys.stdin)["data"]; print(d["resolved_default"] is not None)'
    ```
  - 期望：第一条**恰好一行 `1|1`**（活跃模板中仅 1 个默认）；第二条 `True`。0 个默认时 assemble 必须返回 **409 `NO_DEFAULT_TEMPLATE`**（不是 500、不是静默取第一条）；>1 个违反不变量 I2 → 记 coder。
  - **现状（2026-10-23 04:0x 实测）**：`template` 共 6 行、活跃 **1**（`中文-单页-审`，`is_default=1`），5 个同名「照片候选模板」已于 `04:01:29` 软删；`GET /templates` 的 `resolved_default` **非 null** ⇒ **captain m01808 描述的「6 个活跃全 `is_default=0`」是 03:5x 的快照，已被清理动作消解**（见 D-36）。

- [ ] **CMP-29 单页自适应阶梯：可用高度必须减去上下边距，原件密度优先**（P0，t10 前置，等 t8 产物；captain m01877 + m01941）
  - **⚠️ 证据等级（先读）**：uier 那组「10.5pt 溢出 56px≈15mm / 10pt 余 5.6mm」是**临时页面在 Chrome 里量的，且分母算错**——拿「内容高 1178.5px」比「纸张高 1122.5px」，**没减上下边距**。captain 按用户原件实测推翻：真实缺口 ≈**54mm**（`docs/DESIGN.md §12.4` 那组 px 数字因此作废，见 **D-38**）。本条的**真实基线只能由 t8 首份 PDF 产生**，在此之前记 **`BLOCKED(no-artifact)`**。
  - **用户原件实测参数**（`data/imports/sample_zh.pdf`；captain m01941 实测 + supervisor 复核一致）：页 `595.5×842.25pt`、`mediabox=(0,-7.83,595.5,834.42)`；边距 左 **14.83** / 右 **15.62** / 上 **8.26** / 下 **16.38** pt、正文高 **817.6pt**、版心宽 **565.0pt**、最小字号 **10.0pt**、1,707 字符 ⇒ 原件是「**5mm 级窄边距 + 10pt**」的紧排。
  - **判据（密度必须显式声明，不许隐式选择）**：
    1. **可用高度 = 页高 − 上边距 − 下边距**（15mm 边距 → `842.25 − 42.5 − 42.5 = 757.2pt`）。**禁止**用「内容高度 vs 纸张高度」比较（→ **X-A11 同类项⑨**）。
    2. `density="original"`（**默认**；边距 左 15.0 / 右 15.6 / 上 8.3 / 下 16.3 pt，容差 ±0.5）→ **`pages == 1` 且 `min(size) >= 10.0pt`**（≥10.0 而非 9.5：原件就是 10pt，产物不该更小）。
    3. `density="relaxed"`（15mm 边距）→ 允许 **2 页**，但必须发 `PAGE_FIT_DOWNGRADED`（或等价 warning）且前端可见；**静默换页 = FAIL**。
    4. 降档须发 `PAGE_FIT_DOWNGRADED{from_pt,to_pt}`；**静默缩字 = FAIL**。
    5. **反向（防凑页）**：边距不得小于原件 **±2pt**（左 ≥12.83 / 右 ≥13.62 / 上 ≥6.26 / 下 ≥14.38）；行距 ≥ **1.45**；**内容段数必须等于 draft 的 bullet 总数**（少一条＝裁内容换页数）。
    6. **照片不受排版调整影响**：89.28pt 见方、距顶 **3.82**、距右 **9.13**（照片比上边距高，属原件原样），**不许「为了排版美观」挪动**。
  - 命令（t8 出首份 PDF 后跑）：
    ```bash
    cd resume-warehouse && $PY - <<'PY'
    import glob, pdfplumber
    p = sorted(glob.glob("data/exports/**/*.pdf", recursive=True))[-1]
    doc = pdfplumber.open(p); pg = doc.pages[0]
    ch = [c for c in pg.chars if c["text"].strip()]
    top = min(c["top"] for c in ch); bot = max(c["bottom"] for c in ch)
    print("pages:", len(doc.pages), "page_h:", round(pg.height,2),
          "content_h:", round(bot-top,1), "usable(15mm):", round(pg.height-85.0,1))
    assert len(doc.pages) == 1                        # density=original
    assert min(c["size"] for c in ch) >= 10.0         # 原件 10pt 为下限
    PY
    ```
  - **交叉证据**：captain 侧只读验收器 `data/eval/check_export_pdf.py --pdf <PDF> --photo --right-margin <实际右侧边距>`；两边不一致 → **以 PDF 为准并回查**。
  - **⚠️ 调用陷阱（D-39）**：该脚本 `--right-margin` 默认 **42.5pt**，直接跑用户原件得 `overflow_count=63 / verdict FAIL`；填实际值 `--right-margin 15.62` 才是 `overflow_count=0 / verdict PASS`。**默认值不可信，必须显式传**。
  - 归属：缩字不报警 / 降档不告警 / 裁内容 / 压边距压行距 → **coder**；把「页高」当可用高度、或沿用 uier 那组错分母 → **supervisor**；`§12.4` 数字不作废 → **planner**（D-38）。

- [ ] **CMP-30 英文长词不得溢出右边距**（P1，同批 uier 结论）
  - 判据：`all(c["x1"] <= page.width - right_margin + 1 for page in pdf.pages for c in page.chars)`；用英文样张的 36 字符长词 `SupportVectorMachineHyperparameters` 作固定夹具。
  - 期望：`overflow = 0`（整词换行，不裁剪、不缩字号解决）。
  - 归属：未做断词/换行 → **coder**（render_pdf）；边距常量与 CSS 不一致 → **coder**（对齐 print.css）。

- [ ] **CMP-26b 教育段整段文字不得被拆成 bullet（反向断言）**（P1，CMP-26 配套）
  - 判据：PDF 里 `.doc__fact` 对应行**行首不得出现「·」**；同时 `facts[]` 每条以整段形式逐字出现（CMP-26 正向已覆盖）。
  - 命令：`$PY -c 'import pdfplumber,glob; pg=pdfplumber.open(sorted(glob.glob("data/exports/**/*.pdf",recursive=True))[-1]).pages[0]; bad=[l for l in pg.extract_text().split(chr(10)) if l.strip().startswith("·")]; print("bullet_lines:", bad)'`
  - 归属：把 `facts[]` 渲染成 bullet → **coder**（render_html/render_pdf）；把「整段」与「要点」混用 → **coder**。


**COMPOSE 伪通过迹象**：导出用 `reportlab` 但字体验证靠「看起来没方块」；`text_verified` 恒 `1`（不实际抽取）；`NAMING_*` 用 `VALIDATION_ERROR` 顶替；`{name}` 缺失时只 warning 不 422；照片用「大致右上角」或直接把图贴进标题行。

---

- [ ] **CMP-31 教育段与技能段的「内容不许消失」**（P0，captain 2026-10-23 m02371，**D-46** 的导出侧）
  - 与 **CMP-26b** 分工：CMP-26b 判「**不许拆成 bullet**」（形态），本条判「**不许消失**」（存在性）；两条必须同时绿，只有一条绿 = 内容仍在但形态错，或形态对但内容没了。
  - 命令（对当前默认模板真实导出，`--right-margin` 必须传实测值 15.62，见 D-39）：
    ```bash
    /opt/anaconda3/bin/python3 data/eval/check_export_pdf.py --pdf "data/exports/数据分析实习生-张三-示例大学.pdf" --photo --right-margin 15.62 | tail -5
    python3 - <<'PY'
    import pdfplumber, glob
    p = sorted(glob.glob("data/exports/*张三*.pdf"))[-1]
    t = pdfplumber.open(p).pages[0].extract_text() or ""
    for probe in ["GPA 3.56/4", "86.53/100", "CET4：562", "CET6:508", "主修课程："]:
        assert probe in t, f"教育段探针丢失: {probe}"
    assert "SKILLS_EMPTY" not in t
    assert len([l for l in t.split("\n") if l.startswith("·")]) >= 0
    print("CMP-31 OK")
    PY
    ```
  - 期望：五个教育探针**逐字存在**；教育段行首**无 `·`**（配合 CMP-26b）；技能段 3 行整句**且不得出现 `SKILLS_EMPTY`**；同时 section 标题与其 entry 必须**成组出现**（实测「校园活动」标题缺失而其 entry 行出现 → 若复跑仍如此，按「区块被拆散」记 coder）。
  - **现状（2026-10-23 04:35 实测）：FAIL** —— 中文产物全文仅 **151 字符**、五个探针 **0 命中**、无技能段。
  - 归属：内容在 commit 阶段已丢（先看 IMP-18/19）→ **coder**；若 commit 有内容而导出丢 → **coder**（`render_pdf`）。

- [ ] **CMP-32 中英不一致时：各取原值 + `SOURCE_CONFLICT`，禁止合并**（P1，**`BLOCKED(user-pending)`**，captain 2026-10-23 m02371）
  - 背景：中英两份简历自身矛盾——GPA `3.56/4 & 86.53/100` vs `3.57/4.0 & 86.86/100`；到岗时间 `2027年1月下旬` vs `Early July 2026`（**差 5 个月**）。用户尚未裁定以哪份为准。
  - 判据（用户拍板后启用）：① 同一 `build` 的中文产物该字段 == 中文来源值、英文产物 == 英文来源值，**互不覆盖**；② 两者不等时 `warnings` 必含 `SOURCE_CONFLICT{field, zh_value, en_value}`，且导出页**可见提示**；③ 反向：`warnings` 里出现合并后的第三个值（如 `3.56/4.0`）= FAIL。
  - **当前状态：`BLOCKED(user-pending)`** —— 不得记 PASS/FAIL；用户答复后把本条改为 PASS 判据并更新基线（届时同时关闭本条与 CMP-31 的「内容消失」误判风险）。
  - 归属：把两个数合并/静默取一侧 → **coder**；契约未要求 `SOURCE_CONFLICT` → **planner**。

### 1.5.1 首份 PDF 基线（2026-10-23 04:33–04:36，supervisor 实测）

产物：`data/exports/数据分析实习生-张三-示例大学.pdf`（131171B）、`data/exports/数据分析实习生-San-Zhang-Wuhan-University.pdf`（129490B），均 04:31 生成。

| 条目 | 实测 | 判定 |
|---|---|---|
| **CMP-20** 照片几何 | `w=h=89.28`、`x0=497.09`、`top_norm=3.82`、`right_gap=9.13`、图片数 1（中文版）；英文版同四项一致 | **PASS**（`check_export_pdf.py --photo --right-margin 15.62` → `verdict PASS`） |
| **CMP-29** 单页阶梯 | `pages=1`、`min size=10.0pt`、最大 22.0pt；但**全页仅 151 字符** | **基线不可用**（内容缺失，见 D-46）——**不得记 PASS**，D-46 修复后重跑 |
| **CMP-30** 长词不溢出 | 越界字符 `0`（右边界取 `width-15.62`） | **未覆盖**：目标长词未进入产物，`0 越界` 不能证明长词处理正确 |
| **CMP-26 / CMP-31** 教育段内容 | 五探针（`GPA 3.56/4`/`86.53/100`/`CET4：562`/`CET6:508`/`主修课程：`）**0 命中**；无技能段 | **FAIL**（D-46） |
| **D-48** 语言一致性 | en 产物 CJK 片段 **12 段**（chrome：`到岗时间`/`教育背景`/`项目经历`；正文：`小象超市…`/`全国大学生商业分析大赛`/`把 6527 条…`） | **FAIL**（三层判据全不满足；**不能写成「出现 CJK 即失败」**——正文里用户的中文机构名本就该保留，见 D-48 三层） |

**纪律**：`pages==1` 且 `min size>=10pt` 在「内容被丢掉」的情况下**也会成立**，所以 CMP-29 **必须与 CMP-31 联合判定**——单看页数和字号会把 D-46 判成 PASS。这条已写入 CMP-29 的期望段（「内容段数 == draft bullet 总数」本就是为此设的护栏，但当前 `draft` 与 `template_block` 不一致，护栏本身也被 D-46 绕过）。

- [ ] **CMP-33 i18n 单真源：以契约 §8.5.1 为唯一真源，判渲染后的产物而不是裸字符串**（P0，captain m02548，口径修订 m02575）
  - **时点事实（2026-10-23 04:43）**：`server/app/services/i18n.py:37` = `{"zh": "主修课程", "en": "Relevant Coursework"}`，**mtime 04:41:55**，已与契约 `docs/API-CONTRACT.md:829` 的 `Relevant Coursework: …` 一致；而最新 en 产物仍是 **04:38:37** 那批（印 `Relevant Courses:`）⇒ **这是「两版产物 + 一版当前代码」，不是三方并存**。原判 FAIL 属 **T-1 旧产物**，已改判 **`BLOCKED(stale-artifact)`**（INT-26）。
  - **04:52 新产物复核 → ✅ PASS（2026-10-23 04:57；三时点：代码 `render.py` 04:51:54 < 进程 pid 5245 04:51:55 < 产物 04:52:16/17）**：en 产物 chrome 区 L1–L6 **无 CJK**，section 标题为 `Education / Experience / Projects / Campus Activities / Skills`（判据**大小写不敏感**——实际产物是首字母大写，不是全大写 `EDUCATION`），无契约表外 key。
  - **判据正文（大小写口径，2026-10-23 04:57 修正）**：section 标题比对**一律大小写无关**（`str.casefold()` 后比较）。实际产物是首字母大写 `Education / Experience / Projects / Campus Activities / Skills`，而检查器若只写全大写 `EDUCATION` 就会把**正确实现判红**（captain 的脚本同时写了 `heads` 与 `ln.upper()` 才躲过去——那是运气，不是判据对）。
  - 判据（**可判形态**）：① 契约 §8.5.1 是唯一真源；② **不要求 `i18n.py` 的值里带冒号**——冒号是渲染层的分隔符，要求值内置冒号会让**正确实现也红**；测试断言应写成 `f"{i18n.LABELS['courses']['en']}:" == 契约值`（拼出分隔符后逐字相等）；③ 真正要判的是**渲染产物**里的标签与契约表逐字相等（扫 PDF 文本层，不看代码猜）；④ **反向**：`i18n.py` 出现契约表外的 label key ⇒ FAIL（否则加词表＝悄悄改契约）。
  - 归属：**coder**（渲染层拼分隔符/选 key）；契约表缺列 → **planner**；拿旧产物判 → **supervisor**（本条已自纠一次）。
- [ ] **CMP-34 禁止「半翻译」：标签已译、正文未译**（P1，captain m02548；**现状 `BLOCKED(stale-artifact)`**）
  - **现状：✅ PASS（2026-10-23 04:57，产物 04:52:17）** —— en 产物 L7 已是**整行中文原文** `专业成绩：GPA 3.56/4 86.53/100 CET4：562 CET6:508`，不再出现 `Academic Record:` 这类**英文前缀 + 中文正文**的拼装。
  - 上轮实测（04:38:37 旧产物）：`Academic Record: GPA 3.56/4 …` = 半翻译实例，已随重导消失。
  - **反向条款口径修正（04:57 实测）**：`CET4：` 这类**全角标点在用户草稿原文里就存在**，整行回退时必须原样保留 ⇒ 反向断言改为「**非回退行**（有英文变体、由我们生成的行）不得出现全角标点」，**不得**对回退行判 FAIL（否则把「诚实回退」判成缺陷）。
  - **判据正文（回退行豁免，2026-10-23 04:57 修正）**：**只有「非回退行」（有 en 变体、由我们生成的行）受本约束**；整行回退的中文原文（含 `CET4：` 这类全角标点）**必须原样保留**，对它判 FAIL 等于把「诚实回退」判成缺陷。判定方式：先按 CMP-37 的回退清单标记回退行，再对剩余行做本检查。
  - 判据：① 同一段落内不得同时出现**契约词表的英文标签**与**中文正文**；② 无英文变体时应**整行保留原文**并进 `LANG_FALLBACK`，**不许补英文前缀**（补前缀＝假装翻译过）；③ **反向**：`CET4：`（全角冒号）出现在 en 产物里 ⇒ FAIL（全角标点是我们生成的，不是用户数据）。
  - 归属：**coder**（`compose.py` / `render_*` 的逐字段翻译逻辑）。
- [ ] **CMP-35 `LANG_FALLBACK` 的计数必须与产物对得上**（P1，captain m02548；**现状 `BLOCKED(stale-artifact)`**）
  - **现状：✅ PASS（2026-10-23 04:57，产物 04:52:17）**：最新 en 产物的 `build_artifact.warnings_json` 报 `LANG_FALLBACK{entry_count:6, bullet_count:16, skills_fallback:true, samples:6, entries:6, lang:'en'}`；实算 en 产物 **CJK 行 41 / 总行 52**。三条判据全过：`len(samples)==entry_count`（6==6）✓、`skills_fallback` 布尔必填 ✓、`41 ≥ 6+16=22` ✓。
  - **captain 报的 `5 / 13` 来自 04:50:44 那版产物**（同轮内已被 04:52:17 覆盖）——按 T-1c 以**最新产物**为准，此处如实记录两版差异，不视为计数造假。
  - 判据：① `sample[]` 长度 == `entry_count`；② `skills_fallback` 布尔**必填**（技能行是否回退必须显式声明，不能靠箭头推）；③ **正文 CJK 行数 ≥ `entry_count + bullet_count`**（回退计数只会少不会多，少了就是没数全）；④ 不满足 ⇒ 记「计数与产物不符」，**不得**用「大意如此」放过。
  - **分母定义（2026-10-23 04:57 写死，两队必须用同一分母）**：`正文行 = 总文本行 − chrome 行`，其中 `chrome 行 = 页眉 1–4 行（姓名/学历行/联系方式/到岗时间）+ 5 个 section 标题行`（en 实测 = 9 行 ⇒ 52 − 9 = **43 行**）；`正文 CJK 行 = 正文行中至少含一个 `[\u4e00-\u9fff]` 的行`（en 实测 **41**）。**禁止**用「总行数」或「含标题行的行数」当分母——captain 报 `41/43`、supervisor 报 `41/52` 就是分母不同，两个都对但无法互校（X-A11 同类项）。
  - **captain 报的 `5/13` 已过期**（04:50:44 那版读数），以最新产物 `6/16` 为准 —— 这是 **T-1 的又一次实例**，按「谁发出谁记账」记在 **captain** 名下（不是 coder 缺陷）。
  - **口径写死（captain m02575）**：**「CJK 行」= 该行至少含一个 `[\u4e00-\u9fff]` 字符的文本行**（空行、纯 ASCII 行不计；一行里出现多个中文片段仍算 1 行）——否则 7/8 这种分歧还会再来一次。
  - **计数不达标时必须贴出全部 CJK 行**（行号 + 原文），否则复核者无法判断是「计数错了」还是「产物变了」。
  - 归属：**coder**。
- [ ] **CMP-36 空 section 不得静默消失**（P1，captain m02548；**现状 `BLOCKED(stale-artifact)`**）
  - **现状：✅ PASS（2026-10-23 04:57，产物 04:52:16/17）**：zh 产物段落齐全 `教育背景 / 实习经历 / 项目经历 / 校园活动 / 职业技能`（5 段），en 产物对应 5 个英文标题；模板 `template_block` 构成 `header 1 / section 4 / entry 6 / skills 1 = 12`，与「4 个 section + 1 个 skills 段」一一对上，**空 section 不再静默消失**。
  - 上轮实测（04:38:37 旧产物）：只有 EDUCATION/PROJECTS/SKILLS，缺 `实习经历`/`校园活动` 且未发 `PACKAGE_MISSING`。
  - 判据：① 模板有该 section 而渲染无内容 → `warnings` 必含 `PACKAGE_MISSING`（码已存在，`server/app/services/compose.py:479`）；② 导出页必须列出「本次无内容、已省略的段落」清单；③ **空段不渲染是对的，静默是错的**——反向：一个空段都没有却报 `PACKAGE_MISSING` ⇒ 同样 FAIL（计数造假）。
  - 归属：**coder**。

- [ ] **CMP-37 英文变体优先：有 `lang='en'` 变体就必须渲染英文，`LANG_FALLBACK` 只许出现在真没变体的条目上**（P0，t10 前置，captain m02680；**现状 `BLOCKED(no-en-variant)`**）
  - **现状（2026-10-23 04:57 实测）**：`select lang,count(*) from package_bullet_variant group by 1` → `zh 120 / en 0` ⇒ 英文版正文 **41/52 行是中文**（诚实回退，不是 bug），但「英文简历」当前**投不出去**。故记 `BLOCKED(no-en-variant)`（M1：契约已定、实现未到，不判 pass/fail），等 coder 完成「LLM 改写 + 导入英文简历产 en 变体」后启用。
  - 判据：① `lang=en` 导出时，凡存在 `lang='en'` 变体的条目/要点，正文**必须**用英文变体（逐条比对变体文本，不看概率）；② `LANG_FALLBACK` **只允许**出现在「确实没有任何 en 变体」的条目上，并须报**回退行数**与**逐条清单**（`entry_id`/`bullet_id`），不接受只报总数；③ **反向**：有 en 变体却仍渲染中文、或把「有变体但未被使用」也计入 `entry_count` ⇒ FAIL。
  - 归属：**coder**（`compose.py` 语言选择 + 变体生成链路）；变体表缺 `en` 列/约束 → **planner**。
- [ ] **CMP-38 两版 PDF 均不得横向越界；中文行首禁则必须靠悬挂标点解决，不许缩字号**（P1，captain m02680）
  - **现状（2026-10-23 04:57，`check_export_pdf.py --right-margin 15.62`）**：zh/en 两版均 `verdict FAIL / failed=1`，唯一失败 `no_horizontal_overflow`：越界字符 **1 个** `{'text': '、', 'x1': 582.83, 'limit': 580.88, 'page': 1}`（越界 **1.95pt**）。其余全 PASS：`pages=1`、`min_size=9.5`（众数 `(9.5,1510)`，`PAGE_FIT_DOWNGRADED` 10.5→9.5）、照片 `89.28×89.28 / top 3.82 / 距右 9.13 / 图片 1`、`text_verified` 真、`cid=0`、`U+FFFD=0`。
  - 判据：① 两版 `overflow_count == 0`；② 根因必须是**中文行首禁则**（`、。，；：）」』` 不得出现在行首）——修法是**悬挂标点**（行首标点挂到上一行行尾、或允许悬挂出界不超过半个字宽），**不得**用缩字号或压边距让检查器变绿；③ **反向**：`min_size` 因本次修复降到 `< 9.5pt`、或把 `--right-margin` 调大以「消除」越界 ⇒ FAIL。
  - 归属：**coder**（`render.py` 标点/换行处理）；判据侧边距写错 → **supervisor**（D-39 同族）。
- [ ] **CMP-39 教育段日期必须完整：起止两端都要在（「字段在库里、渲染时消失」同族）**（P0，captain m02680；**现状 FAIL**）
  - **现状（2026-10-23 04:57，产物 04:52:16/17）**：zh 教育段渲染成 `示例大学 2028`、en 渲染成 `Wuhan University 2028`；而 draft `entry.date_range = 2024.9-2028.6` ⇒ **入学 `2024.9` 丢失、毕业时间被截成 `2028`**，中英两版都缺。
  - **不归本条的相邻事实**：`校园活动` 段渲染成 `示例大学 2024.9 - 至今`，与 draft 原文 `2024.9 - 至今` **逐字一致**，不算缺陷（如认为「至今」本身不合理，属数据/口径问题，走 CMP-32 同类的人工裁决）。
  - 判据：① 教育段文本必须**同时**含 draft `date_range` 的起止（`2024.9` 与 `2028.6`；允许 `2024.9–2028.6`/`2024.9 - 2028.6` 等分隔符差异）；② 缺任一端 ⇒ FAIL；③ **反向**：判据写成「含 `2028` 即过」⇒ **判据本身 FAIL**（年份命中不能替代完整区间）。
  - 与 **CMP-31** 分工：CMP-31 查技能行与五探针（内容消失），**不覆盖日期字段**；本条专查日期型「库里有、渲染没了」。
  - 归属：**coder**（`render.py` / `compose.py` 的 `date_range` 渲染）。
- [ ] **CMP-40 页眉只允许 姓名 / 电话 / 邮箱 / 到岗时间；不得出现学历/专业/届别**（P1，captain m02680；**✅ PASS（05:23 新产物，captain 复核 + 我实测 05:31）**）
  - **现状（2026-10-23 04:57）**：zh 页眉第 2 行 `本科 | 管理科学（商业数据分析） | 2028`；**en 页眉第 2 行 `B.M. | Management Science (Business Data Analytics) | Class of 2028`**（captain 只报了 zh，en 同样重复）。用户原简历页眉只有姓名 + 联系方式，教育信息应在教育段出现一次。
  - **判据一（静态，跑一秒、不会过期）**：
    ```bash
    grep -rn "education_line" server/app --include=*.py    # 期望 0
    ```
    契约 `docs/API-CONTRACT.md §8.6.1`（v1.33）已写明 `education_line` **字段禁止存在**；**当前 6 命中**（2026-10-23 05:14 实测）：`server/app/services/compose.py:386`（生成）、`:669`（消费）、`server/app/services/render.py:196`/`:283`/`:320`（消费）、`server/app/services/export_service.py:403`（消费）。**生成端与消费端都要清零**——只删生成不删消费会留下 `KeyError` 或静默跳过。
  - **判据二（产物，按值比对而非关键词）**：页眉区（姓名行以下 3 行内）**不得出现** `user_profile.degree` / `major` / `grad_year` **三者的值**（`本科` / `管理科学（商业数据分析）` / `2028`；en 侧 `B.M.` / `Management Science (Business Data Analytics)` / `Class of 2028`）。**从 `user_profile` 直读值再比对**，不看「本科/学历」这类关键词——否则改文案就能绕过。
  - **判据三（反向，防修 A 破 B）**：教育段的 `date_range`（draft 里是 `2024.9 - 2028.6`）**必须出现在教育段内**——删页眉时容易把教育信息整体丢掉，这是 D-46 修好过的内容，不得回退；反向断言：教育段文本含 `2024.9` 且含 `2028.6`（与 CMP-39 联动）。
  - 判据（原有形态约束）：① 页眉（姓名行之后 1–2 行）只允许 `姓名 / 电话 / 邮箱 / 到岗时间`（en 对应 `name / phone / email / availability`）；② 出现 `degree`（本科 / B.M.）、`major`（管理科学 / Management Science）、`grad_year`（2028 / Class of 2028）任一 ⇒ FAIL；③ 
  - 归属：**coder**（`render.py` 页眉组装）；契约白名单未写 → **planner**（captain 已派）。

- [ ] **CMP-42 单真源跨渲染器一致：预览 HTML 的字号/行距必须从 `LADDER` 派生**（P1，captain m02781；**✅ PASS（05:23，实测 `li{font-size:11.0pt;line-height:12.65pt}`、全篇无 `10.5pt`；captain 独立复核同结论）**）
  - **现状（2026-10-23 05:14 实测）**：`server/app/services/render.py:188` `li{font-size:10.5pt;line-height:1.62}`、`:189` `.skills div{font-size:10.5pt;line-height:1.62}`、`:186` `.entry-sub{font-size:10.5pt}` —— **预览 HTML 内联写死 10.5pt / 1.62**；而 PDF 实际走 `LADDER = ((11.0,1.15),(10.5,1.15),(10.0,1.15),(9.5,1.15))`（`render.py:49`）。⇒ **预览所见非所得**：屏幕上 10.5pt/1.62，导出 11.0pt/1.15。
  - **为什么单列**：这一族错误的形态是**同一个值有多份副本**——契约常量、reportlab `LADDER`、`render_html()` 内联 CSS、uier 的 `print.css`。三处「各自对齐」只能防这一次，**只有判据能防第四次漂移**。
  - 判据：① `render_html()` 的输出（对同一 `build`）**不得出现** `10.5pt` / `1.62` 这类硬编码正文值；正文 `font-size` 必须等于 `LADDER[0][0]`（当前 11.0），`line-height` 必须等于 `LADDER[0][1]`（当前 1.15）。
  - **反向（证派生，不证巧合）**：用 `monkeypatch` 把 `LADDER` 改成首档 `(10.5, 1.30)`，断言 `render_html()` 输出里**出现** `10.5pt` 与 `1.30`；复位后再断言回到 `11pt`/`1.15`。只断言「相等」会被「两处都改」蒙混，**必须证明改一处另一处跟着动**。
  - 归属：`render_html()` 内联常量 → **coder**；`print.css` 与 `LADDER` 不一致 → **uier/coder**（见下条静态对账）；判据只查相等不查派生 → **supervisor**。

- [ ] **CMP-43 演示/示例包不得进产物；含 sample 必须发 `SAMPLE_PACKAGE_INCLUDED`**（P0，captain m02831，2026-10-23 新增）
  - **清理旧 selection 的前置（captain m02962）**：`build_selection` 里含示例包的 62 行属数据残留，清理**必须先打快照**（`sqlite3 data/app.db .backup` 或 `cp` 到 `data/backups/`），**优先软删/可 restore**，并给出清理前后计数（`before=62 / after=0`，快照路径与 md5 同列）。无快照的删除即使结果正确也记 **supervisor**（违反 INT-24）。
  - 事故：`…-16.pdf`（zh）与 `…-15.pdf`（en）项目经历第 1 条是 `【示例】小象超市门店选址与订单量预测建模`（`2026.3 - 至今`），第 3 条才是真身 `小象超市门店选址与订单量预测模型（美团商业分析大赛）`（`2026.03 - 2026.04`）。`build_selection` 两版 `order_index=1` 都是演示包 `01a165270e61753d82777e55fe70b3`（`status=draft`、tags 含 `sample`、标题带 `【示例】`）。
  - 我实测（05:31）：`【示例】` 计数 zh=**1**、en=**1**；`小象超市` 各 **2** 次（示例 + 真身）⇒ 用户视角是「同一项目写了两遍，其中一遍还标着示例」。
  - 判据（三条同时，缺一不可）：
    1. **产物文本层 `【示例】` 计数 == 0**；
    2. **项目经历条目数 == 该 build `selections` 去掉 sample 包后的数量**（不是「≥」）；
    3. **selections 含 sample 包 ⇒ 必须出现 `SAMPLE_PACKAGE_INCLUDED` 警告**；反向：无 sample 包却出现该警告 ⇒ FAIL。
  - **附带证据（演示数据污染统计）**：该包 `langs=["zh"]`，使 en 的 `LANG_FALLBACK` 计数虚高到 `entry_count=7`；归档后重导应下降——**新旧计数都要记入条目**。
  - 归属：**判据侧 + 数据侧**（captain 造的演示包留在真库未清理，**不记 coder**）。coder 只做两件事：默认选包排除 `sample`/`【示例】`；导出侧加护栏（含 sample 时告警且不默认选中）。
  - 复验命令：
    ```bash
    cd resume-warehouse && .venv/bin/python - <<'PY'
    import pdfplumber, glob, sqlite3
    for p in sorted(glob.glob("data/exports/*.pdf"))[-2:]:
        t = "\n".join((pg.extract_text() or "") for pg in pdfplumber.open(p).pages)
        print(p.split("/")[-1], "【示例】=", t.count("【示例】"))
    con = sqlite3.connect("data/app.db")
    print(con.execute("select b.lang, count(*), sum(case when p.tags_json like '%sample%' then 1 else 0 end) from build_selection s join resume_build b on b.id=s.build_id join package p on p.id=s.package_id group by b.lang").fetchall())
    PY
    ```
    期望：两版 `【示例】= 0`；sample 计数 0；若仍有 sample 则 `warnings_json` 必含 `SAMPLE_PACKAGE_INCLUDED`。

- [ ] **CMP-41 版式常量必须从产物 PDF 逐字符量（中位字号 11.0 / 行距比 1.10–1.25 / 条目头单行 / 正文 ≤41 行且条目数逐条相等）**（P0，t10 前置，captain m02768；契约 `ARCHITECTURE.md §7.5.1` v1.17 / `ACCEPTANCE.md:221` **AC-PDF-18** / ADR-22；**现状 `BLOCKED(no-fresh-artifact)`**）
  - **现状（2026-10-23 04:59，旧版式产物 04:52:16/17）**：zh/en 两版实测 `median_size=9.5`（众数 1510 字符 @9.5）、`baseline_diff_median=13.8`、**行距比 13.8/9.5 ≈ 1.45**、文本行 58；与新版式常量不符 ⇒ **旧版式**，且旧实现把降档做成「缩字 + 加大行距」（两头都错）。因产物早于版式定稿，记 `BLOCKED(no-fresh-artifact)`，**不按旧产物判 FAIL、不记 coder**。
  - **量法纪律（禁止自证）**：**不得**从 `render.py` 的常量或 `print.css` 的变量读值来「证明」字号达标——那等于「改常量即改通过」。必须从 **PDF 字符属性**量（pdfplumber `chars[].size` / `chars[].top` / `chars[].x0,x1`）。
  - 判据：
    1. **中位字号 === 11.0pt ± 0.2**（正文区 `chars[].size` 中位）；**正文区**出现 10.5/10.0 必须伴随 `PAGE_FIT_DOWNGRADED`（页眉联系方式 10.0pt 是设计字号，实测 zh-17 有 51 个 10.0pt 字符全在页眉行，**不纳入本判据**）；**9.5pt 单独出现即 FAIL**（紧急档须同时给出三档失败原因，不得静默降到 9.5）。
    2. **行距比 ∈ [1.10, 1.25]**：相邻行基线差中位 ÷ 中位字号。原件实测 `12.0/11.0 ≈ 1.09`；我们旧产物 `13.8/9.5 ≈ 1.45`。**行距比不随降档变化**——降档只动字号、不动行距（旧实现两头都改，是错的）。
    3. **条目头必须单行**：逐条目量渲染纵向跨度 ≤ **1.6 × 行高**，`超行条目数 == 0`；日期列宽 **67.8–124.3pt**（版心 565pt 的 12%–22%）。
    4. **正文行数 ≤ 41 行**（原件 33 行 × 1.25）+ **条目数逐条等于 `build.selections` 的 `variant_ids` 总数**——**逐条比，不只比总数**（防「靠裁内容换字号」：裁掉 3 条再加 3 条空条目，总数仍相等）。
    5. **证据须含三时点**（INT-26）：`产物 mtime ≥ render.py/compose.py mtime ≥ 进程 started_at`；不成立记 `STALE_ARTIFACT`，不记 coder。
  - **生成器也是判据（captain m03055）**：任何自动生成账本/索引/统计的脚本，必须自带「分母自校验 + `--check` 非零退出」，否则它的输出不得作为通过证据（实例：`make_index.py` 漏 27 行加粗 AC ⇒ 分母 119/146）。
- **X-A10 配对（必须联合判定）**：`pages==1` 与 `min>=9.5` 在「内容被裁掉」时同样成立 ⇒ **CMP-29 必须与 CMP-31 / 本条④联合判定**，任一条单维绿记 `INCOMPLETE(单维绿)`，不得记 PASS。
  - **静态对账（现在就能做，不依赖产物，2026-10-23 05:14 实测通过）**：`web/src/styles/print.css` 的 `--doc-fs` 四档 = `11pt / 10.5pt / 10pt / 9.5pt`（`:40`、`:114`、`:120`、`:90`），`--doc-lh` **全档 1.15**（`:41`、`:91`、`:115`、`:121`），与 `server/app/services/render.py:49` 的 `LADDER = ((11.0,1.15),(10.5,1.15),(10.0,1.15),(9.5,1.15))` **逐档相等**；条目头 `min-width:12%;max-width:22%`（`print.css:275-276`）与判据③的 67.8–124.3pt 同源。对账命令：
    ```bash
    grep -nE "\-\-doc-fs|--doc-lh" web/src/styles/print.css
    grep -n "LADDER" server/app/services/render.py
    ```
    **任一档不相等 ⇒ 记 uier/coder 漂移**；此对账**通过也不代表产物达标**（X-A10：静态一致 ≠ 渲染正确），产物侧仍须跑上面五条。
  - **可复用工具（只读）**：
    ```bash
    python3 data/eval/check_export_pdf.py --pdf <产物> --expect-pages 1 --min-size 10.0 \
        --photo 2 --right-margin 15.62 --identity <profile.json>
    python3 data/eval/check_lang_export.py --pdf <中/英产物> --build <build_id>
    ```
    前者管几何，后者管语言层（chrome CJK / 半翻译 / `LANG_FALLBACK` 计数对账）；**两者都只在各自覆盖的维度上下结论**（X-A10 第三次实例），不得据其 PASS 给内容层结案。
  - 归属：字号/行距/条目头/裁剪内容 → **coder**（`render.py`/`compose.py`）；版式常量与契约不一致 → **planner**；从代码常量「证明」达标、或用旧产物判 FAIL → **supervisor**。

- [ ] **CMP-44 「最近构建」默认列表不得刷屏（同 (position, lang) 只留最新 1 条）**（P3，captain m03168，2026-10-23 新增）
  - **事实（我复算，时点 2026-10-23 06:4x）**：`resume_build` 共 **43** 条（`exported 39 / assembled 2 / draft 2`），其中 `(数据分析实习生, zh)` **20 条**、`(数据分析实习生, en)` **19 条**——全是验证脚本反复导出留下的同名成对记录，用户打开「最近构建」会看到一屏同名条目。
  - 判据：① 默认列表里**同一 `(position, lang)` 只出现最新 1 条**；② 列表总数 ≤「真实导出过的作品数」（同一作品多次重导不算多件）；③ 每条至少显示可区分信息（导出时间 + 版本号），不得只显示标题。
  - **反向**：`GET /builds?include_archived=1` 仍必须能看到被归档记录 ⇒ **不允许真删**（历史是用户的资产）；反向断言：归档前后 `select count(*) from resume_build` **不变**、`build_artifact` 行数与磁盘文件数**前后不变**（「归档顺带删文件」= D-47 同族风险，直接 FAIL）。
  - 配套清理脚本：默认 `--dry-run`；`--apply` 前快照并打印 md5；**只软归档**（`status`/`archived_at`），不物理删除。
  - 复验：
    ```bash
    cd resume-warehouse && sqlite3 data/app.db "select position,lang,count(*) c from resume_build where status='exported' group by 1,2 having c>1"  # 期望空
    sqlite3 data/app.db "select count(*) from resume_build"   # 归档前后相等
    curl -s "$B/builds?include_archived=1" | python3 -c "import json,sys; d=json.load(sys.stdin)['data']; print(len(d['items']))"
    ```
  - 归属：脚本写错/物理删除 → **coder**；拿「有清理脚本」当通过、不看归档是否真只改状态 → **supervisor**。

- [ ] **CMP-45 七个页面必须能渲染出内容（不是「有壳无错」）**（P0，t10 门，captain m03184）
  - **缺口先记账（归 supervisor + captain）**：整套验收里**没有任何一条判「页面能不能看」**——账本全绿、接口全 200、`node --check` 全过、import/export 解析 0 缺失，但用户打开页面可能只有骨架。这是 X-A10「单一维度判据不得单独给 PASS」的极端形态：**我们一直在判 API 和数据，没人判用户看得见什么**。
  - 判据：对 7 条路由（`#/workbench` `#/warehouse` `#/builds` `#/templates` `#/profile` `#/jobs` `#/settings`）逐条无头截图 —— ① PNG **≥ 15000 字节**；② 能提取到该页 `ROUTES[key].label` 或主标题文本；任一不满足即 FAIL。
  - **反向（本条的灵魂，2026-10-23 改为根因级）**：判据不是「字节够大」，而是三条同时成立——① `#view` 内 `innerText` **≥ 120 字符**；② 该页标题/label 可提取；③ **CDP `Log.entryAdded` 中 `source=security` 的 CSP 违规数 = 0**（有任何一条必须 FAIL 并**打印原文**）。
  - **为什么要写 CSP 这一条**：真实事故（captain m03206）——`server/app/__init__.py:64` 定义 `PAGE_CSP` 含 `script-src 'self'`，`:136` 下发；而 `web/index.html:49` 是**内联 `<script type="module">`（9071 字符，整个 SPA 的启动脚本）** ⇒ 被 CSP 拦掉、应用不启动、7 个路由全只剩骨架（我的截图 7824–8153B 正是这个）。**只比字节数会在「下一种拦法」下再次变绿**，所以必须把 CSP 违规当作独立 FAIL 原因。
  - **不许用放宽 CSP 换通过**：给 `script-src` 加 `'unsafe-inline'` 来「修复」= FAIL（把安全面换成便利），见 CMP-47。
  - 命令（coder 交付 `scripts/check_pages_headless.py` 后）：
    ```bash
    cd resume-warehouse && .venv/bin/python scripts/check_pages_headless.py; echo rc=$?   # 期望七页全 ok、rc=0
    ```
  - 归属：空白页 → **coder**（页面模块/路由注册/渲染异常）；**账本缺「页面可渲染」判据 → supervisor + captain**（本条即补这个缺口）。
- [ ] **CMP-46 异步异常不得静默成白屏**（P1，captain m03184）
  - 判据：`index.html` 的装载路径必须捕获微任务 rejection；**人为让某页 `render()` 抛错时，页面必须出现明确错误文案**（不是白屏、不是只有骨架）。
  - 反向：**正常页面不得出现错误文案**（避免「到处挂个错误条」蒙混）。
  - 命令：改 `web/src/pages/<page>.js` 注入 `throw new Error("故意")` → 重跑 CMP-45 的截图 → 断言截图里能 OCR/查到错误文案（含「出错了」或错误码）；还原后断言无错误文案。
  - 归属：未捕获 → **coder**；判据只看「控制台无红」不看屏幕 → **supervisor**。

- [ ] **CMP-47 CSP 与页面形态自洽：严格 CSP 下不得有内联脚本**（P0，captain m03206）
  - 静态判据：`GET /` 响应的 `script-src` **不含 `'unsafe-inline'`** 时，`web/index.html` 内**不得存在无 `src` 的 `<script>`**。
  - 反向判据（同等重要）：若有人往 `PAGE_CSP` 的 `script-src` 里加 `'unsafe-inline'` 来让页面「修复」⇒ **FAIL**（安全面不得为便利让路）。
  - 命令：
    ```bash
    cd resume-warehouse && curl -sI http://127.0.0.1:${PORT}/ | grep -i 'content-security-policy'
    grep -n "<script" web/index.html        # 期望：每个 <script> 都带 src
    ```
  - 现状（2026-10-23 06:3x 我实测）：`web/index.html:49` 内联 `<script type="module">`（9071 字符、无 `src`）+ `script-src 'self'` ⇒ 必 FAIL。
  - 归属：内联脚本 → **coder**（搬成 `web/src/boot.js` 并保持 CSP 严格）；用放宽 CSP 换取通过 → **coder + supervisor**（我复核时报过关）。

- [ ] **CMP-48 「修复生效但用户看不到」必须被判：存量结论重算门**（P0，captain m03340，2026-10-23 新增）
  - **为什么单列**：F-08 的本质不是「代码没修」，而是**代码修好了、已存数据没重算**——页面读的是存量结论。账本判的是「当前代码行为」，**这类缺陷账本永远抓不到**。同族实例：`jd_requirement.matched_package_ids` 全 `[]`、`candidate_status_source` 全 `llm`，而 `link_requirements()` 在内存里已能算出命中。
  - 判据（四条同时）：① 存在**重算入口**（脚本或读时回填），支持 `--dry-run` 与 `--apply`，`--apply` 前留快照（`sqlite3 .backup` + md5）；② 重算全程 **`outbound_calls == 0`**（本地重算禁止出网，配合 `check_egress`）；③ 给出 **before → after 表**（逐行改前/改后值），不允许只报「已重算 N 行」；④ **用户可见路径复验**：`GET /jds/{id}`（或页面）返回的已是新值，而非只有内存里的函数结果。
  - ⑤ **核对「应当改变而未改变」的条目**（captain m03367）：重算后必须逐条列出「预期应命中但重算后仍为空」的 requirement，作为**未完成项**单列；只核对「已变化项」会把**空转当收敛**——实例：`scripts/recompute_jd_links.py` dry-run 六条只补 1 条、其余五条状态与命中都不变、`outbound_calls=0`、快照齐备、流程完全合规，但证据源没接 `skills_json`，SQL/Python 仍然匹配不到 ⇒ **一个合规的重算可以合法地保留错误结论**。
  - 反向：用户**没同意**就改存量 → FAIL（数据安全）；只改代码不重算、却在报告里写「已修复」→ FAIL；只报「已变化 N 条」而不列「应变化未变化」→ FAIL。
  - 复验示例：`sqlite3 data/app.db "select count(*) from jd_requirement where matched_package_ids_json!='[]'"`（before 0 → after ≥1）；`grep -c outbound data/exports/relink_report.json` = 0。归属：**coder**（重算脚本/读时回填）；只判「代码能算」不判「页面已变」→ **supervisor**。

- [ ] **CMP-49 MANUAL → AUTO 必须带负向验证（否则仍是 high）**（P0，captain m03340，2026-10-23 新增）
  - 规则：`AC-UI-05/06/07/09` 转 AUTO 后，**每条都要能真红**——故意打断页面（注入 JS 异常 / 摘掉某 DOM 节点）或桩 5 类错误码，断言该条 FAIL；只在报告里写「已转 AUTO」而拿不出负向执行记录，按 F-07 继续判 **high**。
  - 保留 MANUAL 的只允许三条：`AC-LOC-07`（要真删真库）、`AC-PDF-20`（浏览器打印预览）、`AC-JD-05`（AI 建议合并需人判断）；其余理由须重新论证。
  - **负向证据的格式（captain m03452）**：每条必须含 **命令 + 期望失败的断言 + 实际失败输出 ≥1 行原文**（例：`pytest -k ac_ui_05 -q` → `assert innerText >= 120` → `AssertionError: 0 >= 120`），只写「已负向验证」= FAIL；优先用 `--record` 从真实运行生成，不手写（手写无法证明真跑过）。
  - **判定式必须是集合判等，不是数量判等**（captain m03404）：`MANUAL ⊆ {AC-LOC-07, AC-PDF-20, AC-JD-05}` **且** `len(MANUAL) == 3`。只判「数量 == 3」会假绿——把该留的换掉、数量仍是 3 也能过。
  - 复验：`grep -c MANUAL tests/acceptance/AC_INDEX.md` = 3；每条 AUTO 的负向记录（命令 + 故意破坏方式 + 该条的 FAIL 输出）。归属：**coder**（用例）；「MANUAL 当灰地」→ **supervisor**。

- [ ] **CMP-50 归档语义与产物一致性（默认不可物理删）**（P0，captain m03422，2026-10-23 新增）
  - 背景：`prune_builds.py --apply` 把 43 条构建硬删到 12 条（见 **D-54**），根因是 `resume_build` 没有归档列而指令要求「软归档」——**下了一条物理上做不到的指令，执行方又静默降级**（T-17）。
  - 判据四条：
    1. **默认只归档**：schema v10 起 `prune_builds.py` 默认**只写 `archived_at`**；`--hard-delete` 必须显式、且要 `--yes` 确认并打印「不可恢复」字样；
    2. **读写语义**：`GET /builds` 默认 `archived_at IS NULL`；`?include_archived=1` 能查到归档行；**反向**：归档 N 条后默认列表条数必须减少 N；
    3. **无悬空行**：`SELECT count(*) FROM build_artifact WHERE build_id NOT IN (SELECT id FROM resume_build)` = 0，`build_selection` 同理（当前实测 0/0，留作回归）；
    4. **磁盘孤儿只列不删**：`--list-orphan-files` 输出「文件名 / 大小 / mtime」，删除动作等用户点头（实测 `data/exports/` **44 个 PDF 中 22 个无产物记录**）。
  - 复验：`sqlite3 data/app.db "select count(*) from build_artifact where build_id not in (select id from resume_build)"` = 0；`ls data/exports/*.pdf | wc -l` 与 `select count(distinct filename) from build_artifact` 并排报告（差值即孤儿，只列不删）。归属：**coder**（脚本/接口语义）；只判「没报错」不判「默认不删」→ **supervisor**。

- [ ] **CMP-51 存量回填必须逐行可对且带告警**（P0，captain m03570，2026-10-23 新增）
  - 背景：本轮 `--apply` 回填出 `relink_report_20261023T033716Z.json`（变化 2 条、`outbound_calls=0`）。只报「已重算 N 行」无法证明「谁变了、为什么变」。
  - 判据：① 报告 `changed[]` 与 `expected_but_unchanged[]` **逐行可对**（每条带 `id`/`skill`/`before`/`after`，不允许多份报告拼凑）；② 报告 `warnings[]` **必须包含** `STATUS_WITHOUT_EVIDENCE` 条目（本轮 2 条），且条数与真实被降级/被标记的 requirement 数相等；③ 报告 `outbound_calls == 0`；④ **反向**：只报「已重算 N 行」而无逐行 before/after，或 `warnings` 为空却声称「有 2 条无证据」= FAIL。
  - 归属：`scripts/recompute_jd_links.py --report` → **coder**；拿汇总数当逐行证据 → **supervisor**。

### 1.6 UI（t3，owner: uier）— 界面实装

- [ ] **UI-01 零外部资源**（AC-UI-01，P0，**BLK-1**）
  - 命令：`grep -rnE "https?://" web web/src | grep -v "www\.w3\.org" ; echo rc=$?`；再 DevTools Network Offline 加载 5 页并截图。
  - 期望：grep 零命中（`xmlns` 除外）；断网下 5 页全部可用，Network 面板无外部域名请求。

- [ ] **UI-02 零构建**（AC-UI-02，P0）
  - 命令：`find web/src -type f | sed 's/.*\.//' | sort -u; ls web/src | grep -c node_modules`
  - 期望：扩展名集合 ⊆ `{js,css,svg}`；`node_modules` 计数 `0`；无 `dist/`/`build/` 产物；`<script type="module" src="/static/app.js">` 直出。

- [ ] **UI-03 禁止 innerHTML 注入用户内容**（AC-UI-04，P0）
  - 命令：`grep -rn "innerHTML" web/src web`
  - 期望：零命中，或每条命中在同行注释里标明「常量模板、不含用户输入」，且评审逐条确认；简历预览走服务端 jinja2（`autoescape` 打开，可用 `{{ "<script>" }}` 夹具验证被转义）。

- [ ] **UI-04 ConsentModal 硬要求**（AC-UI-03、API §10.2 前端契约，P0，**BLK-4**）
  - 命令：`grep -n "preview_id" web/src/modules/consent.js | head`；DOM 断言用 `tests/acceptance/test_ac_ui_03.py`；手工：截图列表清单。
  - 期望：① 任何 LLM 动作前必弹；② `Esc` = 取消并调 `reject`；③ **Enter 不触发发送**；④ `excluded` 与 `redactions` **不折叠**、主视野可见（截图）；⑤ 按钮文案含 `est_tokens` 与 `provider/model`；⑥ 无「跳过预览直接 complete」的代码路径；⑦ 过期后按钮变「重新生成预览」；⑧ `fields[]` 按 `kind` 中文名渲染（§10.2 五类）。

- [ ] **UI-05 命名对话框**（AC-UI-05，P1）
  - 命令：手工输入 3 个 pattern（合法/缺变量/含 emoji），截图。
  - 期望：实时显示解析结果与最终文件名；缺变量时红字 + 「去填个人信息」深链；默认值 `{position}-{name}-{school}`；`warnings`（NAMING_SANITIZED/TRUNCATED/EMOJI_STRIPPED/NO_VARIABLE）按 code 展示灰/黄/绿文案。

- [ ] **UI-06 JobToast**（AC-UI-06，P1）
  - 命令：触发导入 job，截图；`kill` 服务重启后再看。
  - 期望：显示进度/阶段；仅 `queued` 可取消；重启后变「已中断，可重试」；轮询用 `setTimeout` 递归（`grep -n "setInterval" web/src` 应零命中）。

- [ ] **UI-07 响应式下限**（AC-UI-07，P1）
  - 命令：1280×800 与 1440×900 各截一张；`document.documentElement.scrollWidth <= clientWidth` 断言。
  - 期望：1280×800 无横向滚动条；1440+ 三栏展开。

- [ ] **UI-08 降级态红条**（AC-UI-08，P1）
  - 命令：让 `GET /env` 返回 `render.chrome_available=false, fonts.ok=false`（改写 `data/logs/preflight.json` 或临时桩），截图。
  - 期望：顶部红条出现；PDF 按钮禁用并有原因；不产生 500 页面。

- [ ] **UI-09 错误按 code 分支**（AC-UI-09，P1）
  - 命令：构造 422 `NAMING_MISSING_VAR`、503 `LLM_NOT_CONFIGURED`、500 `RENDER_FAILED` 三例，截图。
  - 期望：每例文案走「发生了什么 → 为什么 → 我能做什么」；`hint` 作为下一步；**不出现** `JSON.stringify(details)` 的原文。

- [ ] **UI-10 打印版式 = PDF**（AC-PDF-20、DESIGN 硬约束 10，P2）
  - 命令：`grep -n "@media print" web/src/*.css web/*.html`；`⌘P` 预览截图。
  - 期望：`@media print` 存在，A4 与 margin 与 PDF 一致（视觉比对）。

- [ ] **UI-11 可访问性底线**（DESIGN 硬约束 5/6，P1）
  - 命令：抽查主按钮/正文/警告三处对比度；Tab 走一遍焦点。
  - 期望：正文对比度 ≥ 4.5:1；焦点环可见（`outline: 2px solid` 自定义，非浏览器默认被 `outline:none` 干掉）；置信度/优先级/警告不只靠颜色（有文字或形状）。

- [ ] **UI-12 键盘可达**（DESIGN §6，P2）
  - 命令：手工 `⌘K` / `⌘S` / `Esc` / `J K Space`；拖动排序处检查「上移/下移」按钮。
  - 期望：快捷键按表生效；拖动排序有键盘替代路径。

- [ ] **UI-13 无硬编码身份**（AC-NAME-07，P1）
  - 命令：`grep -rn "张三\|示例大学" server/app/ ; echo rc=$?`
  - 期望：零命中（示例数据只能来自 `data/` 或接口）。**与 X-F9 不冲突**：学校名允许以真实值发给 LLM，但必须从 `user_profile` 读，不得在代码/模板/静态资源里写死。

- [ ] **UI-14 只消费契约字段**（P0，契约一致性）
  - 命令：把 `web/src/modules/views/*.js` 里访问的 `data.` 字段名抽出来，与 API-CONTRACT 逐段核对（`grep -rhoE "data\.[a-z_]+" web/src | sort -u`）。
  - 期望：零个「契约里不存在的字段」；若出现，判 uier 杜撰字段（判例 §3.3 例 5）。

---

### 1.7 SKILL（t9，owner: coder）— 独立 DSH Skill

- [ ] **SKL-01 SKILL.md 契约**（P0）
  - 命令：`head -6 skill/SKILL.md`
  - 期望：frontmatter 含 `name: resume-warehouse` 与单行 `description`，且 description 覆盖「打包经历 / 导入简历 / 按 JD 定制 / 导出 PDF」四个触发语。

- [ ] **SKL-02 薄封装、不直连 LLM**（P0，**BLK-1**）
  - 命令：`grep -rnE "httpx|requests|urllib|api\.deepseek\.com|11434|Authorization" skill/ ; echo rc=$?`
  - 期望：零命中（只允许出现 `127.0.0.1:8765`）；`skill/cli.py` 只做 HTTP 转发到本应用。

- [ ] **SKL-03 服务未启动时给指引**（P0）
  - 命令：停掉服务后 `$PY skill/cli.py doctor; echo rc=$?`
  - 期望：打印 `scripts/run.sh` 指引，**不自动拉起服务**，退出码非 0（明确失败而非假装成功）。

- [ ] **SKL-04 命令集覆盖四类动作**（P0）
  - 命令：`$PY skill/cli.py --help`
  - 期望：至少含 打包/加变体、导入并 commit、JD 分析+匹配、build+assemble+export 四组子命令；每条映射到 `/api/v1/*` 端点（对照 §14 契约）。

- [ ] **SKL-05 示例可跑**（P1）
  - 命令：`ls skill/examples/ && for f in skill/examples/*.sh; do bash "$f" --dry-run; done`
  - 期望：每个示例有 `--dry-run` 或明确前置说明；dry-run 不写数据。

- [ ] **SKL-06 不越界写盘、不加依赖**（P0）
  - 命令：`grep -nE "open\(|Path\(" skill/cli.py | head`；`grep -rn "pip install\|npm install" skill/ ; echo rc=$?`
  - 期望：写盘只允许 `/tmp` 与用户显式指定路径；零安装动作。

- [ ] **SKL-07 Skill 最小闭环**（P0，与集成 lane 共用证据）
  - 命令：`$PY skill/cli.py doctor && $PY skill/cli.py package add --file tests/fixtures/package.json && $PY skill/cli.py build export --build $bid --pattern '{position}-{name}-{school}'`
  - 期望：三步全 0；导出产物落在 `data/exports/`，文件名符合模板。

---

### 1.8 集成（t10，owner: coder）— 全链路

- [ ] **INT-01 冷启动到可用**（P0）
  - 命令：`rm -rf .venv data/app.db && ./scripts/run.sh & sleep 8 && curl -s $B/health | head -c 200`
  - 期望：自动建 `.venv`（`--system-site-packages`）、建库、打印 URL；health 200。（`data/imports/` 不得被删——真实素材。）

- [ ] **INT-02 E2E-01 从零到可投简历**（P0）
  - 命令：按 ACCEPTANCE §12 步骤脚本化执行（`tests/acceptance/test_e2e_01.py` 或 `tests/e2e/run_e2e_01.sh`）。
  - 期望：产出 `data/exports/数据分析实习生-张三-示例大学.pdf`；pdfplumber 提取含「张三」「示例大学」且 `\ufffd` 计数 0；`build_artifact` 有行。

- [ ] **INT-03 E2E-02 JD 定制**（P0）
  - 命令：同上，pattern 改 `{company}_{position}_{name}`。
  - 期望：命名解析正确；PDF 含 JD 前 3 个 must 技能词中至少 2 个（用户选中对应 bullet 时）。

- [ ] **INT-04 E2E-03 隐私全链路**（P0，**BLK-2/3/4**）
  - 命令：`$PY -m pytest tests/acceptance -q -k "e2e_03 or priv_01 or priv_04 or priv_05"` + 手工抓包（`tee` 保存 body）。
  - 期望：抓包 body 无原文指纹、无手机号/邮箱（出现 `[PHONE]`/`[EMAIL]`）；日志无正文；`llm_call_log` 只有字段名。

- [ ] **INT-05 E2E-04 断网全链路**（P1）
  - 命令：关 Wi-Fi 后跑 INT-02 的脚本（LLM 步骤跳过，`method=heuristic`）。
  - 期望：全流程成功，无卡死、无 30 s 超时。

- [ ] **INT-06 E2E-05 重启一致性**（P1）
  - 命令：导出中途 `kill` → 重启 → `GET /jobs/{id}`。
  - 期望：job 显示 `interrupted`；库里无半成品 artifact；重试成功。

- [ ] **INT-07 前后端字段一致**（P0）
  - 命令：`grep -rhoE "data\.[a-z_]+" web/src | sort -u` 与 API-CONTRACT 逐段比对；再跑 UI 全页，DevTools Console 无 `undefined` 渲染痕迹（截图）。
  - 期望：零字段漂移；页面上不出现 `undefined` / `null` 直出文案。

- [ ] **INT-08 上/下行分离审计**（P0，D-07 已裁定：抓取是授权需求，不是违规）
  - 命令：
    ```bash
    grep -rn "requests\|httpx\|fetch(" server/app/services/ server/app/api/ | grep -v "fetch_client"   # 上行链路不得直接联网
    grep -rn "fetch_client" server/app/ --include=*.py
    grep -rn "upstream\|uplink" server/app/ --include=*.py | head   # 实现若有显式口径注释，检查是否与裁定一致
    ```
  - 期望：上行链路（`llm_payload`/`assembler`/`render_*`/`export`/`warehouse`）零直接联网；`fetch_client` 只被 `jd_analyzer`/`company_profiler` 及其 API 层引用；实现范围 ⊆ ARCHITECTURE §3.2（含 `server/app/adapters/fetch_client.py` 与 `scripts/preflight.py`）。
  - 若发现「抓取把用户字段拼进 URL 或 POST body」→ 判 **BLK-9**，归属 coder；若发现「契约/文档仍写出网只有 llm_client 一个出口」→ 归属 planner（D-07 尚未闭环）。

- [ ] **INT-09 全量自动化**（P0）
  - 命令：`$PY -m pytest tests/acceptance -q --timeout=120`
  - 期望：全绿；用例数与 `[auto]` 条目数一致（`grep -c "\[auto\]" docs/ACCEPTANCE.md` 对照 `ls tests/acceptance/test_ac_*.py | wc -l`，差值需逐个说明）。

- [ ] **INT-10 目录布局无漂移**（P1）
  - 命令：`git status --porcelain | awk '{print $2}' | grep -vE "^(app|data|docs|skill|tests|run\.sh|\.gitignore|\.env\.example|requirements\.lock\.txt)"`
  - 期望：零输出（或每条都在 ARCHITECTURE §3.2 里被声明）。根目录 `scripts/set-api-key.command` 已由 captain 声明为**用户本地运维脚本**（D-09 已闭环，判据见 INT-12），只剩 `.DS_Store` 需忽略。

- [ ] **INT-11 服务必须真的起得来（启动硬门，t10 第一条执行项）**（P0，**BLK-10**，captain 2026-10-23 实测：4,400 行 `compileall` 全绿却一行跑不起来）
  - 背景①：`python3 server/server.py --port 8899` → `AttributeError: 'PosixPath' object has no attribute 'strip'`（`server/app/db.py:40`，`config.data_dir` 是 `Path` 而函数声明收 `str`）。**编译通过 ≠ 能运行**；此前没有任何一条断言覆盖「进程起来 + health 200 + 端口文件一致」。
  - 背景②（captain 2026-10-23 03:04 实测，**第二个真缺陷**）：实例跑在 **8766** 时 `/api/v1/health` 仍回 `"port": 8765` —— 它读的是**配置值**而非实际绑定端口，前端会拿到死端口。所以启动门不能只比 `app_port`，必须**三值交叉**（见 **INT-13**）。supervisor 03:07 复跑同一路径已正常（`health.data.port=8766`），故障已被 coder 修，门槛保留。
  - 命令（**子进程启动 + 轮询**，禁止 `sleep 3` 后盲 `curl`）：
    ```bash
    $PY - <<'PY'
    import json, os, socket, subprocess, sys, time, urllib.request
    env = dict(os.environ, PYTHONPATH="server")
    p = subprocess.Popen([sys.executable, "server/server.py", "--port", "8899"],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    def wait_health(port, deadline=15.0):
        t0 = time.time()
        while time.time() - t0 < deadline:
            if p.poll() is not None:
                print("EXITED", p.returncode); print((p.stdout.read() or "")[-2000:]); return None
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=1) as r:
                    if r.status == 200:
                        return json.loads(r.read())
            except Exception:
                time.sleep(0.2)
        return None
    body = wait_health(8899)
    print("health:", "OK" if body else "TIMEOUT/DEAD")
    # D-03 定版：app_port 必须是 JSON 五字段；禁止 int(文件内容) 兜底（会掩盖格式漂移）
    meta = json.loads(open("data/runtime/app_port").read())
    missing = {"port", "host", "url", "pid", "started_at"} - set(meta)
    health_port = (body or {}).get("data", {}).get("port")
    three_way = (health_port == meta.get("port") == 8899 and not missing
                 and str(meta.get("url", "")).endswith(":" + str(meta.get("port"))))
    print("health.data.port:", health_port, "app_port:", {k: meta.get(k) for k in ("port", "url")},
          "missing:", sorted(missing), "three_way_equal:", three_way)
    p.terminate(); p.wait(10); time.sleep(0.5)
    s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", 8899)); free = True
    except OSError:
        free = False
    finally:
        s.close()
    print("port_free_after_terminate:", free)   # kill -9 复活过的实例会污染后续端口测试
    sys.exit(0 if body and three_way and free else 1)
    PY
    ```
    （脚本头部另需 `import socket`；`p.terminate()` 后必须做这一步，否则残留 LISTEN 会让下一轮顺延测试假红。）
  - 期望：① 15s 内 `GET /api/v1/health` 返回 200，且响应是合法信封 `{ok:true,data:{status:"ok",port:...},request_id}`；② `data/runtime/app_port` 是 **JSON 五字段** `{"port":int,"host":str,"url":str,"pid":int,"started_at":ISO8601 带时区}`（允许多键、不许少键；**D-03 已定版 → ARCHITECTURE §3.3 v1.7**，本清单 D-16 记录来龙去脉），且 `url` 以 `:<port>` 结尾；③ **三值相等**：实际监听端口 == `health.data.port` == `app_port["port"]`（详见 INT-13）；④ `terminate()` 后同端口可立刻 bind（无残留 LISTEN）；⑤ FAIL 时必须能看到 traceback 尾部（不允许 `except: pass` 吞启动异常）；⑥ 「进程活着但 health 500/404」算 FAIL，不算过。
  - **实测记录（2026-10-23，supervisor 独立复跑两次）**：
    - 03:04 `--port 8899`：`health: OK`（0.7s，`data.status="ok"`、`data.port=8899`）；`app_port` 为 JSON 且 `port=8899` → 启动 PASS（`db.py:40` 的 `Path/strip` 已由 coder 修）。
    - 03:07 `--port 8766`（**非默认端口，专门验三值**）：`health.data.port=8766`、`app_port.port=8766`、`url=http://127.0.0.1:8766`；`terminate()` 后 8766 可立即 bind（`port_free_after_terminate: True`）→ **INT-13 当前为绿**（captain 03:04 看到的 `"port":8765` 撒谎已修）。
    - 这条门仍必须保留：确实发生过「4,400 行编译全绿但起不来」，也发生过「起来了但对外报错端口」。
  - 顺延复验（与 CORE-05 联动）：先 `python3 -m http.server 8765` 占住默认端口，再起服务 → 断言实际端口 ≠ 8765、`app_port` 同步更新、`/health` 仍 200。
  - 归属：启动即崩 → **coder**（`db.py:40` 类型不匹配是实现 bug，文档已写清启动命令）；若错误源于「文档没写启动命令或端口文件路径」→ planner。

- [ ] **INT-12 设置 API 密钥脚本：只回显 SHA-256 指纹，绝不回显 key 片段**（P0，**BLK-3**，captain 2026-10-23 改版并已实测）
  - 新事实：脚本输出改为 `✓ 已写入 …/.env（35 字符，指纹 82be8a4d）`，指纹 = `printf '%s' "$KEY" | shasum -a 256 | cut -c1-8`。**指纹不可逆、不可用于鉴权、不含 key 任何字符** → 旧的「不得回显 key 任何片段」判据会**误杀**这个合法实现，必须按下面收口。
  - 命令：
    ```bash
    grep -c '末尾四位' scripts/set-api-key.command                                     # ① 期望 0
    grep -c '指纹' scripts/set-api-key.command                                         # ② 期望 ≥1
    grep -n 'shasum -a 256' scripts/set-api-key.command                                # ② 必须能指出指纹由 SHA-256 生成
    grep -nE '\$\{KEY: *-?[0-9]+\}|tail -c ?4|rev \| cut -c1-4' scripts/set-api-key.command   # ③ 反向：期望 0（防「取末几位」冒充指纹）
    #    注：**不要**把这条写成 `cut -c[0-9]+-`——它会误命中合法的 `cut -c1-8`（2026-10-23 实测假红）
    ```
  - **行为断言（比 grep 强，必须跑）**：
    ```bash
    FAKE=sk-test-DEADBEEF42; cp .env "$EV/env.bak"; before=$(shasum -a 256 .env | cut -d' ' -f1)
    printf '%s\n' "$FAKE" | ./scripts/set-api-key.command > "$EV/cmd.out" 2>&1 || true   # 交互脚本按提示喂入
    for i in 0 1 2 3 4 5; do sub=${FAKE:$i:4}; n=$(grep -c "$sub" "$EV/cmd.out"); [ "$n" = 0 ] || echo "LEAK[$sub]=$n"; done
    grep -c 'DEADBEEF' "$EV/cmd.out"        # 期望 0
    stat -f '%Lp' .env                      # 期望 600
    grep -c "$FAKE" .env                    # 期望 ≥1（确实写入）
    ```
  - 期望：① 0；② ≥1 且 `shasum -a 256` 在脚本内；③ 0；行为：stdout 不含假 key 的**任意 4 字符连续子串**、`.env` 权限 600、`.env` 其余行字节不变（被改写行之外的 md5 比对）；**拒绝路径**（空输入 / Ctrl-C）下 `.env` 整体 md5 不变。
  - 归属：脚本是 captain 产物 → 缺陷归 **captain**；但若 `server/app/` 或前端把 key 回显出来，仍按 CORE-11 判 coder/uier。

- [ ] **INT-13 端口三值交叉相等：实际监听 == `health.data.port` == `app_port.port`**（P0，**BLK-10**，captain 2026-10-23 实测：实例在 8766，`/health` 仍回 `"port":8765`）
  - 背景：`/api/v1/health` 曾读**配置值**而非**实际绑定端口**。INT-11 只比「`app_port` == 期望端口」，这种情况下会**绿着放过去**，而前端（读 `/health.data.port` 或 `app_port`）拿到的是死端口。这是**第二个独立缺陷**，不能靠 INT-11 覆盖。
  - 三个场景都要跑（命令复用 INT-11 脚本，`PORT` 参数化，并在解析 `app_port` 后加一次真连）：
    ```python
    import socket as _s
    _s.create_connection(("127.0.0.1", meta["port"]), timeout=1).close()   # 该端口真的在 LISTEN
    assert body["data"]["port"] == meta["port"] == PORT
    assert meta["url"].endswith(":" + str(meta["port"]))
    ```
    - A 默认端口：不传 `--port` → 三值 == 8765（或顺延后的实际值）。
    - B **顺延**：`python3 -m http.server 8765` 占住 → 起服务 → `P = app_port["port"]`，断言 `P != 8765`、`health.data.port == P`、`url` 尾 == `P`、`P` 可连。
    - C 显式：`--port 8899` → 三值 == 8899。
  - 期望：三个场景**逐场景**三值相等且端口可连；任一不等即 FAIL。**典型 FAIL 形态**：`health.data.port=8765` 而 `app_port.port=8766`（读配置值）。
  - **实测记录（2026-10-23 03:07，supervisor，场景 C）**：`health.data.port=8766`、`app_port={"port":8766,"url":"http://127.0.0.1:8766"}`、`terminate()` 后可立即 bind → **当前为绿**（captain 03:04 的 `"port":8765` 撒谎已修）。门槛保留：这类「对外报错端口」只有非默认端口才暴露，默认端口跑永远假绿。
  - 归属：服务把配置值当绑定端口 → **coder**（`server.py` 取端口来源错）；若契约没定义 `health.data.port` 语义 → planner。

- [ ] **INT-14 只读 GET 端点必须 JSON 可序列化（不许 500，不许 `b'...'` 脏值）**（P0，captain 2026-10-23：`/api/v1/env` 500 `TypeError: Object of type TTFNameBytes is not JSON serializable`，`server/app/services/envcheck.py:122` `font.face.name`）
  - 背景：reportlab 的 `TTFont.face.name` 是 `bytes` 子类（`TTFNameBytes`），`json.dumps` 直接炸；若图省事套 `str()` 又会写出 `b'STSongti-SC-Regular'` 这种脏值（前端展示错误、Skill 解析失败）。这类「类型脏了才 500」会在所有元数据端点复发，且只在**有字体环境**才炸 → 无字体 CI 会假绿。
  - 端点清单（以 `X-A1` 路由导出为准，取 `GET` 且无路径参数者）：`/api/v1/health`、`/env`、`/profile`、`/packages`、`/imports`、`/templates`、`/jd`、`/company-profiles`、`/builds`、`/settings`、`/files`、`/jobs`。
  - 命令（起服务后循环；空库也应 200 + 空列表，不许 500）：
    ```python
    for path in PATHS:                      # PATHS 见上，base = f"http://127.0.0.1:{port}"
        with urllib.request.urlopen(base + path, timeout=5) as r:
            raw = r.read().decode()
        assert r.status == 200, (path, r.status, raw[:200])
        json.loads(raw)                      # 必须能解析
        assert "b'" not in raw, path         # 防 bytes 被 str() 后漏出
    ```
  - 期望（**分档**，因为未交付端点当前就是 404，一刀切「全 200」会假红）：
    - **已交付**端点：`200` + `json.loads` 成功 + 无 `b'`；`/api/v1/env` 额外断言 `data.fonts.ok is True`、`data.fonts.primary.name == "STSongti-SC-Regular"`、`primary.subfont_index == 6`、`data.fonts.bold.name == "STSongti-SC-Bold"`、`bold.subfont_index == 1`。
    - **未交付**端点：允许 `404`，但必须是**合法错误信封**（`{ok:false,error:{code,message},request_id}`）+ 可解析 + 无 `b'`；**`500` 永远 FAIL**（说明类型脏值炸在序列化处）。
    - **t10 全链完成后**：上面 12 条**全部**要求 `200`，此时 404 也算 FAIL（判 coder 漏实现 / 判 planner 漏排期）。
  - **实测记录（2026-10-23 03:07，supervisor，`--port 8766` 全量扫）**：
    ```
    /api/v1/health           200  json-ok  294B   dirty=no
    /api/v1/env              200  json-ok  2158B  dirty=no    ← captain 报的 500 已修
    /api/v1/profile          200  json-ok  475B   dirty=no
    /api/v1/packages         200  json-ok  128B   dirty=no
    /api/v1/settings         200  json-ok  802B   dirty=no
    /api/v1/files            200  json-ok  127B   dirty=no
    /api/v1/jobs             200  json-ok  127B   dirty=no
    /api/v1/{imports,templates,jd,company-profiles,builds}   404  json-ok  147B  dirty=no   ← 对应 lane 未开工
    ```
    即：**0 个 500、0 处 `b'`、6 个已交付端点全 200**；5 个 404 是 import/analysis/compose lane 未交付，属**进度基线**不属缺陷。`fonts.primary.name == "STSongti-SC-Regular"`、`fonts.bold.name == "STSongti-SC-Bold"` 已实测相符（captain 03:04 的 `envcheck.py:122` 已改）。门槛保留理由：只在**有字体机器**上炸，缺字体环境会假绿。
  - 归属：序列化/类型清洗缺 `str(face.name)` 或取 `.fontName` → **coder**（`envcheck.py:122`）；若字体名应暴露但契约未定义字段 → planner。

---

- [ ] **INT-15 行为验证前必须确认「进程跑的是当前代码」（陈旧进程门）**（P0，captain 2026-10-23 新缺陷 D-27）
  - 背景（captain 被坑一次）：`pid 46958` 是**改代码之前**起的，Python 不热重载 → 第一轮行为验证得到「`job_id` 缺失 / `PHOTO_DETECTED` 缺失 / `width=None`」，**全是假 FAIL**；换新进程后同一请求全通过。
  - **规则（硬）**：行为结论只有在「进程 = 当前代码」时才可用于判定实现缺陷。不一致时本条记 `BLOCKED(stale-process)`，**不得**把行为失败记到 coder 头上（归属见 §0.3.1 T-2：归判据方/流程方）。
  - 判据：**只用 `build.id` 做断言**：`build.id == build.git_head + ("-dirty" if build.git_dirty else "")`，且 `build.git_head` == 当前 `git rev-parse --short HEAD`。**`source` 每次进程启动都会变**（描述进程快照而非代码），**写进断言会产生假红**——只作信息字段。指纹 = `git rev-parse --short HEAD` + 工作区 dirty 标记。
    ```bash
    CUR=$(git rev-parse --short HEAD)$(git status --porcelain | grep -q . && echo "-dirty")
    GOT=$(curl -s $B/health | $PY -c "import json,sys;print(json.load(sys.stdin)['data'].get('build'))")
    echo "cur=$CUR got=$GOT"; [ "$CUR" = "$GOT" ] || echo "STALE-PROCESS: 不得用行为结论判实现缺陷"
    ```
  - **当前状态（2026-10-23 03:44 复测）：`build` 字段已落地，`AC-ENV-10` → PASS**——`/health.build = {"id":"b8c335e-dirty","git_head":"b8c335e","git_dirty":true,"source":"src-92d5…"}`（`server/app/api/health.py:72` → `buildinfo.build_info()`），与 `git rev-parse --short HEAD` + dirty 一致，`/env.build` 同值。字段落地前仍须手工确认「进程启动晚于最后一次改 `server/app`」（`ps -o lstart= -p <pid>` vs `find server/app -newer`）。
  - 归属：`build` 字段缺失/不一致 → **coder**（planner 已派工）；拿旧进程结论判实现 → **判据方（supervisor/验证者）**。

- [ ] **INT-16 `app_port` 生命周期：陈旧文件必须被覆盖，退出只在「自己是主人」时删**（P0，captain 2026-10-23 新缺陷 D-26）
  - 背景（captain 实测复现）：`127.0.0.1:8765` 在监听（pid 46958），而 `data/runtime/app_port` 写着 `{"port":8899,"pid":62604}`（62604 已死）→ 用户按文件里的 URL 打开即**白屏**。手删陈旧文件重跑后 = `8765/pid 73922`，与 `lsof` 一致。
  - 判据三条：
    1. **启动覆盖**：写文件前，若「文件里的 pid 不存活」**或**「该端口 `connect` 拒绝」→ 必须**覆盖**，不得复用（复用 = FAIL）。
    2. **退出条件**：优雅退出时**仅当**文件里的 `pid == 自己的 pid` 才删除该文件；否则保留（避免 B 进程删掉 A 进程的文件）。
    3. **一致性**：任一时刻 `app_port.pid` 必须存活且 `app_port.port` 可 `connect`（与 INT-13 的三值交叉互补：INT-13 管「端口对不对」，本条管「进程还活着吗」）。
  - 命令：
    ```bash
    lsof -nP -iTCP -sTCP:LISTEN | grep -E ":(8765|8899)" ; cat data/runtime/app_port
    $PY - <<'PY'
    import json, socket, os
    d = json.load(open("data/runtime/app_port")); pid, port = d["pid"], d["port"]
    alive = os.path.exists(f"/proc/{pid}") or os.popen(f"ps -p {pid} -o pid= ").read().strip() != ""
    s = socket.socket(); s.settimeout(1)
    ok = s.connect_ex(("127.0.0.1", port)) == 0; s.close()
    print("alive:", alive, "connectable:", ok)
    assert alive and ok, "app_port 指向死进程/死端口 → 陈旧文件，必须被启动流程覆盖"
    PY
    ```
  - 期望：文件与 `lsof` 实况一致；杀掉进程后重启 → 文件被覆盖为新 pid；`kill` 旧进程不得删掉新进程的文件。
  - 归属：覆盖/删除逻辑错 → **coder**（`server/app/services/envcheck.py` / 启动链）；用陈旧文件判实现 → **判据方**（§0.3.1 T-1 同类）。

- [ ] **INT-17 数据修复脚本必须可审计（dry-run 默认 / `--apply` 才写 / 快照 / 不可反解单列）**（P0 配套，D-35）
  - 命令：
    ```bash
    python3 scripts/repair_package_is_current.py                 # 默认 dry-run，只报告
    python3 scripts/repair_package_is_current.py --apply         # 才落库，且写前打快照
    ```
  - 期望：① dry-run **不改任何行**，并输出「受影响行数 / 可反解行数 / 不可反解行数」；② **dry-run 报告的受影响行数 == 真实受影响行数**（本次基准 **18**，`sqlite3 data/app.db "select count(*) from package where is_current=1 and end_date is null"` 同值）；③ `--apply` 前自动快照（`data/backups/package_is_current_<ts>.json` 或 DB 副本），快照可回滚；④ **反解来源只允许 `import_job.draft_json` 的 `entry.date_range`**，反解不出的行进 `manual_review[]`，**不许猜、不许按相邻段推断**；⑤ 修复后再跑 dry-run，受影响行数必须为 0。
  - **处置必须可逆**（captain m01695）：默认只允许**软归档/软删除**（可 `--restore` 反悔）；**硬删只在用户明确同意后执行**，且脚本必须把 `would_archive` 与 `would_delete` 分成两类清单输出。本条同样适用于 `DELETE /files` 与未来一切清理动作——「一次误点永久丢数据」不可接受。
  - 归属：脚本默认就写库 / 无快照 / 猜日期 / 不可逆删除 → **coder**；用脚本直接改真实库而不先确认 dry-run 行数 → **supervisor**（流程缺陷）。

- [ ] **INT-18 测试隔离门：跑测试不得改动用户真实数据**（P0，**数据安全**类，captain 2026-10-23 要求）
  - 背景：`reset_paths_for_tests()` 复用缓存 `Config` → 测试把行写进真实 `data/app.db`，`import_job` **45 → 105**；全程**测试全绿、API 全绿，只有库悄悄变脏**。这类缺陷靠「看测试结果」永远发现不了，只能靠「跑前跑后对比」。
  - 判据（可复跑）：
    ```bash
    cd resume-warehouse
    $PY - <<'PP' > /tmp/before.json
    import json, sqlite3
    c = sqlite3.connect("data/app.db")
    q = lambda s: c.execute(s).fetchone()[0]
    print(json.dumps({
      "import_job": q("select count(*) from import_job"),
      "package": q("select count(*) from package"),
      "package_active": q("select count(*) from package where deleted_at is null"),
      "template": q("select count(*) from template"),
      "attachment": q("select count(*) from attachment"),
      "photo_path": q("select photo_path from user_profile"),
    }, ensure_ascii=False))
    PP
    PYTHONPATH=server $PY -m unittest discover -s server/tests >/tmp/ut.log 2>&1; echo "unittest rc=$?"
    # 同一段脚本再跑一次 → /tmp/after.json
    diff /tmp/before.json /tmp/after.json && echo "IDENTICAL"
    ```
  - 期望：`diff` 输出为空（**逐字相等**）；`unittest rc` 与库状态**无关**（测试红也不能成为改库的理由）。
  - 反向：任一表行数或 `photo_path` 变化 → **记 coder（P0）**；写「跑测试会污染一点数据但不影响功能」→ **记 supervisor**（把数据安全降级为便利问题）。
  - 本判据已实跑（2026-10-23 04:0x，supervisor）：`before == after`，且 `import_job=105 / package=18（17 软删 + 1 活跃，tags 含「测试夹具」）/ template=6（1 活跃、is_default=1）/ attachment=12 / photo_path=profile/sample_photo.png`。

- [ ] **INT-19 uier「设计了但没实装」9 项必须逐项落到实现方**（P0，t10 门，captain m01877）
  - 背景：uier 在 `docs/DESIGN.md §19.2` 自列 9 项未实装——六页页面组装、PDF 页图、图片裁切上传、拖拽、JobToast 轮询、语言缺失数据源、多页预览、一键打印、骨架过渡。**这些属于 `web/src/pages/**` 或服务端，不在 t3 lane 内**，不能让它们以「组件层已完成」的名义溜过验收。
  - 判据：t10 终验前，下表每项必须有「实现方 + 文件路径 + 可跑命令 + 实测输出」四要素；任一为「待定/组件已就绪」→ **记 FAIL（归 coder/uier，按实现位置）**，不记 `PENDING`。
    ```bash
    grep -rn "TODO\|未实装\|待实现" web/src/pages server/app/services 2>/dev/null | head
    ```
  - 期望：9 项逐条有落点（形如 `拖拽 → web/src/pages/build.js:120 → HTML5 draggable + 事件`），且每条附一条可执行验证（DOM 断言或 API 调用），不允许「组件层已验证」作为整体结论。
  - 归属：页面/交互未接线 → **uier**；服务端支撑缺失（如 PDF 页图、JobToast 轮询 API）→ **coder**；两方都缺 → 记主责 + 连带（§3.1）。
  - 反向条款：若 9 项中有项被判定「本期不做」，必须由 captain 书面裁定并在此表标 `[本期不做]`，**不得静默消失**。

- [ ] **INT-20 进程新鲜度门：被测对象不得落后于代码**（P0，t10 前必跑，captain m02216；已各坑双方一次）
  - 事故实例：8765 上跑的进程启动于 **04:09 之前**，而 `server/app/api/jds.py` mtime `04:09:34`、`server/app/services/jd_analysis.py` mtime `04:17:29` → `GET /api/v1/jds` 返回 **404**，而进程内 `url_map` 有 **85 条路由**（`/jds` 8 条、`/company-profiles` 6 条齐全）；杀掉重启后全部 **200**。**404 是进程旧，不是缺陷。**
  - 判据（四条，全部机械可跑）：
    1. 取监听 pid 与启动时间：`lsof -nP -iTCP:$PORT -sTCP:LISTEN -t | xargs -I{} ps -o pid=,lstart= -p {}`；
    2. 取进程自述：`curl -s $B/health | python3 -c 'import json,sys;d=json.load(sys.stdin)["data"];print(d["build"]["id"],d["build"]["source"],d["port"],d["db"]["schema_version"])'` —— **注意字段在 `data` 之下**（`data.build.id`/`data.port`/`data.db.schema_version`），按顶层取会得到 `null`；
    3. 与源文件 mtime 比较：`find server -name '*.py' -newer <启动时间戳> | head`，**任一命中 ⇒ 判定「被测对象落后于代码」**，该轮端到端**整轮作废**并标 `STALE_PROCESS`（不记 coder 缺陷、不记 uier 缺陷）；
    4. 同一轮测试内 `data.build.source` **必须保持一致**（变化说明中途重启过），否则同样作废。
  - 复验命令（可粘贴）：
    ```bash
    cd resume-warehouse
    PORT=$(python3 -c 'import json;print(json.load(open("data/runtime/app_port"))["port"])')
    PID=$(lsof -nP -iTCP:$PORT -sTCP:LISTEN -t | head -1)
    START=$(ps -o lstart= -p $PID)
    echo "pid=$PID start=$START"
    STALE=$(find server -name '*.py' -newer <(date -j -f "%a %b %d %T %Y" "$START" "+%Y-%m-%dT%H:%M:%S") 2>/dev/null | head -5)
    echo "stale=${STALE:-none}"
    curl -s "http://127.0.0.1:$PORT/api/v1/health" | python3 -c 'import json,sys;d=json.load(sys.stdin)["data"];print("build=",d["build"]["id"],"port=",d["port"],"schema=",d["db"]["schema_version"])'
    ```
  - 期望：`stale=none` 且 `data.port` 与实际端口相等；出现 stale 时**先重启再判**，任何在 stale 进程上得到的 FAIL 都要重跑一次。
  - 归属：拿旧进程判实现 → **判据方（supervisor/captain）**（T-2）；长期没有「启动即自检 build 新鲜度」→ **coder**（可选增强）。
  - 与 INT-15 的关系：INT-15 管「陈旧 `app_port` 文件」，INT-20 管「进程本身落后于代码」，**两条都要跑**。

- [ ] **INT-21 清理/归档脚本必须「产出优先」：`committed` 行不得被归档**（P0，规则类；captain m02310，**归 captain 判据缺陷，不记 coder**）
  - **实例（真库）**：`prune_probe_data.py --prune-import-jobs` 按「同指纹留最新」归档了 81 行，其中 **6 行是 `status='committed'`**，包括唯一活跃默认模板「中文-单页-审」的来源行（04:22:27 被归档）；修复前后 `committed` 活跃数 **6 → 0**。
  - **为什么是 P0**：它**不报错、不告警**，只是把「这份模板从哪份简历来」的溯源断掉；而 **IMP-17**（删导入级联删派生包）依赖这条链——链断了会删错或漏删，与「幽灵经历」同族。
  - 命令：
    ```bash
    cd resume-warehouse
    BEFORE=$(sqlite3 data/app.db "select count(*) from import_job where status='committed' and deleted_at is null")
    $PY data/eval/prune_probe_data.py --prune-import-jobs --dry-run
    $PY data/eval/prune_probe_data.py --prune-import-jobs --apply
    AFTER=$(sqlite3 data/app.db "select count(*) from import_job where status='committed' and deleted_at is null")
    echo "committed: $BEFORE -> $AFTER"
    ```
  - 期望：`BEFORE == AFTER`；且 `SELECT count(*) FROM import_job WHERE result_template_id IS NOT NULL AND deleted_at IS NOT NULL AND created_at < '<prune 开始>'` = 0（有产出的来源行不得进场）。
  - **现行真库基线（截至 2026-10-23 04:27:36，我本人 SQL 直查 `data/app.db`，非引用他人）**：
    ```
    live_committed                     = 6
    live_import_job                    = 30   ← 24 保留 + 6 恢复
    Rc_violations（模板活但来源被归档）  = 0
    committed_no_provenance_active     = 0
    ```
    `live=30` **不是异常**，而是「同指纹组内 `committed` 与 `draft` 并存」的正常形态——它正是 INT-22/23 要覆盖的收敛目标：**该组内归档 draft、保留 committed**，跑完 `live` 应降到 24 且再次 prune 不再变化（幂等）。
  - 归属：脚本把 committed 归档 → **coder**（被规则坑到这个也算规则缺，见下）；**规则本身没写「产出优先」→ captain**。本条当前归属 **captain 判据缺陷**：他的三条件只写「留最新」。

- [ ] **INT-22 归档前的不交集前置：待归档集合 ∩ 存活模板来源 = ∅**（P0，与 INT-21 同批）
  - 命令（写进脚本，非 0 退出即中止）：
    ```bash
    sqlite3 data/app.db "
    SELECT count(*) FROM candidates c
    JOIN template t ON t.deleted_at IS NULL AND t.id = (SELECT result_template_id FROM import_job WHERE id = c.id);" | awk '{exit ($1>0)}'
    echo "rc=$?"   # 期望 0
    ```
  - 期望：`rc == 0`；非 0 时脚本**必须不写库**并打印被保护的 `import_job.id` 列表。
  - **「跳过并告警」的正确形态（captain m02345 裁定，写进脚本注释）**：命中冲突时**不是「跳过整个同指纹组」**，而是「**该组内归档 `draft`、保留 `committed`**」。理由：恢复后同指纹会同时存在一条 `committed` 与一条 `draft`（实测 `live import_job = 30` = 24 保留 + 6 恢复）；若整组跳过，下次清理又把 30 原样留下，永久不收敛；若整组归档，则会再次断链（回到 6 → 0 的事故）。正确语义 = **组内按产出优先挑保留者**。告警内容须写明：`group_hash`、保留的 `id`（committed）、归档的 `id`（draft）。
  - 归属：缺前置 → **coder**（脚本实现）；规则未要求 → **captain**。

- [ ] **INT-23 回归测试：prune 永不归档模板溯源**（P1）
  - 夹具：临时 `DATA_DIR`，写两条**同指纹** `import_job`（一条 `status='draft'`、一条 `status='committed'` + `result_template_id`），跑 prune，断言 committed 行与其 template 均存活、draft 被归档。
  - **必须覆盖真实形态（captain m02345 实测 `live=30`）**：恢复后同组内 `committed` 与 `draft` 并存，因此测试要额外断言 **再跑一次 prune 仍是「draft 归档、committed 存活」**（幂等收敛），不得出现 30 → 24 的循环。
  - 期望：`server/tests/test_prune_never_archives_template_provenance.py` 存在且通过；缺测试而只有脚本改对 → 记 **coder**（P1，回归哨兵缺失）。

- [ ] **INT-24 破坏性脚本必须先分列「不可恢复 / 可恢复」两类计数**（P0，captain 2026-10-23 m02371，**D-47**）
  - 适用：任何带 `--delete` / `--purge` / `--apply` 的维护脚本（`prune_probe_data.py`、`clean_orphan_photos.py`、未来的清理工具）。
  - 判据：执行前**必须**打印两类分开的计数，且默认只做可恢复动作（软删/软归档）：
    ```
    将删除 X 行（不可恢复）：<列出 id 前缀或前 5 条>
    将软删 Y 行（可恢复）：<同上>
    ```
    只有「共处理 N 行」这种单一计数 = FAIL；`--delete` 不区分 `--delete-drafts` 等子命令就直连硬删 = FAIL；`--apply` 前必须留整库快照并打印快照 md5。
  - 判定：缺计数分列 / 默认就硬删 / 无快照 → **coder**；命令命名让执行者无法预判破坏性（如 `--delete` 语焉不详）→ **captain（口径）**。
  - 现状（2026-10-23 04:20 前）：`prune_probe_data.py --delete` 一次硬删 **16 条 draft 行**（不可恢复），超出批准的「软归档 2 行」。

- [ ] **INT-25 现有脚本按 INT-24 逐个体检**（P1）
  - 清单：`scripts/clean_orphan_photos.py`、`scripts/prune_probe_data.py`（如有新增同类脚本一并纳入）。
  - 期望：每个脚本都满足 INT-24 的「两类计数 + 默认可恢复 + 快照 md5」三项；缺一项记 coder（P1），并在台账写清脚本名与缺失项。

- [ ] **INT-26 产物新鲜度门：导出物必须晚于被断言的代码/模板**（P0，t10 前置，captain m02575）
  - 为什么单列（与 INT-20 对称）：**INT-20 管「进程落后于代码」，INT-26 管「产物落后于代码与进程」**。今天两次事故正好各落一边——第一次是旧进程（`job_id`/`PHOTO_DETECTED` 假 FAIL），第二次是旧 PDF（`Relevant Courses:` 被判成「三版并存」，而 `i18n.py` 04:41:55 早已改对）。两次都不是判断力问题，是**没有一条规则要求先看时点**。
  - 判据（开跑任何针对导出物的断言**之前**）：
    ```bash
    ART=$(ls -t data/exports/*.pdf | head -1)
    NOW_T=$(stat -f %m "$ART")          # 产物 mtime（epoch）
    NEWEST_CODE=$(find server/app web -name '*.py' -o -name '*.js' -o -name '*.css' -newermt "@$NOW_T" | head -1)
    [ -z "$NEWEST_CODE" ] || echo "STALE_ARTIFACT: 产物晚于最新代码？否 —— 被 $NEWEST_CODE 超越"
    ```
    **规则**：`产物 mtime` ≥ `被断言代码/模板 mtime` 且 ≥ 进程 `started_at`；任一不成立 ⇒ 记 **`STALE_ARTIFACT`** 并**整条判据作废**，**不记 coder**（缺陷在流程：没人重导出）。
  - 判据并入时点三件套：产物 mtime / 代码 mtime / 进程 started_at，三者写进条目，缺一即「未验证」。
  - 归属：拿旧产物判实现 → **supervisor**；改完代码不重导出、或报告不贴三个时点 → **coder**（交付纪律）。

- [ ] **INT-28 账本类产物必须断言分母 == 文档唯一 AC 数（146），并自带 `--check`**（P0，captain m03055，2026-10-23 新增）
  - 为什么单列：`tests/acceptance/make_index.py:25` 的 `ROW_RE = r"^\|\s*`?(AC-[A-Z]+-[0-9]+)`?\s*\|"` **不认加粗行** `| **AC-…** |`（27 行）⇒ 账本分母 119、真值 **146**，覆盖率由 **76% 虚报成 93%**。这与 §2.1.6 是同一类「命令盲区」，但错在**判据生成器自身**——生成器也是判据（X-A10 延伸）。
  - **分母定版 = 149（不是 146，也不是 152）**（captain m03092）：`152` 把 §14 的 3 行状态模板（`AC-ENV-01 PASS` / `AC-PDF-02 PASS` / `AC-IMPORT-02 KNOWN-FAIL`）当条款多算了；`146` 是「唯一 ID 数」，但有 3 条真条款**撞号被吞**（`AC-NAME-01` 同名 P0/P1、`AC-PDF-11` 同名 P0/P1、`AC-PDF-12` 同名 P0/P2），撞号修完（`AC-NAME-09` / `AC-PDF-19` / `AC-PDF-20` 已立）后 **条款数 = 唯一 ID 数 = 149**。切片规则写死：**§14 之前为条款区**。
  - 判据：① 账本「条款总数」必须 == 条款区唯一 AC 数（当前 **149**）；② **同一 ID 出现两个不同优先级 ⇒ FAIL 并打印两行行号**（判撞号，不是判重复行——这是「覆盖率虚高」的第三种形态：两条条款共用一个号、其中一条永远隐形）；③ 每条 AC 必须有状态（`passed/skipped/uncovered`），未登记不得静默略过；③ `make_index.py --check` 在「分母不符 / 有未登记项 / 有覆盖但无 `@check`」时**非零退出**并打印差集；④ 反向两条：故意加一条未实现的 AC 行 → 红；**故意造一个撞号（同 ID 不同优先级）→ 必须红**（这条比分母更重要：分母随文档增长而变，撞号永远不该出现）。
  - 复验命令：
    ```bash
    cd resume-warehouse && python3 -c "
    import pathlib,re
    s=pathlib.Path('docs/ACCEPTANCE.md').read_text(encoding='utf-8')
    print(len(set(re.findall(r'AC-[A-Z]+-[0-9]+',s))))"   # 期望 146
    .venv/bin/python tests/acceptance/make_index.py --check; echo rc=$?   # 期望 0 且账本总数 146
    ```
  - 归属：生成器漏行 → **coder**；用虚高分母报覆盖率 → **supervisor**（我自己在 t13 前一版也照抄了 111/119）。

- [ ] **INT-27 测试卫生门：全量测试的 `ResourceWarning` 必须为 0（三档计数）**（P1，captain m02600，定版 m02652）
  - 为什么单列：全部通过的 210 条测试中藏着真实泄漏。**测试全部通过不等于测试干净**；长跑（t10 十几轮）会累积成 fd/连接耗尽。
  - **判据形态先修正一次（重要）**：`-W error::ResourceWarning` **不会**让这些用例失败——实测仍是 `Ran 210 tests … OK`、退出码 0，因为 warnings 在 GC/atexit 才发，落在 test 帧之外。**只判退出码 = 假绿**（本条自身就是 X-A10 的实例）。必须**数 stderr**：
    ```bash
    cd resume-warehouse && PYTHONPATH=server python3 -W always::ResourceWarning \
      -m unittest discover -s server/tests 2> "$EV/ut.stderr" | tail -2
    grep -c "ResourceWarning: unclosed" "$EV/ut.stderr"                        # 总闸
    grep -cE "unclosed file <_io\.[A-Za-z]+ name='[^']*'" "$EV/ut.stderr"   # 第 1 档：带真实路径
    grep -cE "unclosed file <_io\.[A-Za-z]+ name=[0-9]+>"    "$EV/ut.stderr"   # 第 3 档：纯 fd（第三方）
    grep -c  "ResourceWarning: unclosed database" "$EV/ut.stderr"             # 第 2 档
    ```
  - **三档（`Ran N` + `OK` 为前提）**：
    | 档 | 内容 | 期望 | 基线（2026-10-23 04:55，`-W always`，210 tests） | 归属 |
    |---|---|---|---|---|
    | 1 | `unclosed file` **带真实路径** | **0** | **1**：`server/tests/test_t6_followups.py:206` 裸 `open(...).read()`（`…/photo_8c6806d8d6093084.png`） | coder |
    | 2 | `unclosed database` | **0** | **6**：1 条 `test_t8_builds.py:161` + 5 条线程局部连接（`db.py:192 _local = threading.local()`；`close_conn()`（`db.py:233`）**全仓 0 个调用点**，`jobrun.py:37 jobs = JobRepo()` 的 worker 线程、请求线程退出都不关） | coder |
    | 3 | `unclosed file` **纯 fd**（`name=N`） | 允许存在 | **3**：werkzeug / reportlab 内部 | 第三方（**必须写明来源，且不得用作第 1/2 档的抵扣**，见 T-14） |
  - **归属判定不要看「出错帧」**：实测 10 条里有 6 条报在 `werkzeug/routing/rules.py:769/837`、1 条 `<string>:2`、1 条 `unittest/suite.py:107`——那是 **GC 触发时的栈顶**，不是分配点。要定位分配点用 `PYTHONTRACEMALLOC=8`（全量 >60s，**按模块**跑，如 `-m unittest server.tests.test_t8_builds`）。
  - 修法：`Path(...).read_bytes()`；`with sqlite3.connect(...)`/显式 `close()`；**线程退出钩子**调 `db.close_conn()`（`_run` 的 `finally` 与 Flask teardown 各一处）。
### 1.5.2 已知限制（不记 FAIL，也不得隐藏）

| 限制 | 证据（含时点） | 处置 |
|---|---|---|
| **英文版正文仍是中文**（`LANG_FALLBACK` 诚实回退，en 变体尚未生成：`package_bullet_variant` zh 120 / en 0） | `…-15.pdf`（05:23）正文 39/40 行为中文；`LANG_FALLBACK.details.entry_count=7`（含示例包，归档后应下降） | 记 `KNOWN-LIMIT(no-en-variant)`，CMP-37 保持 `BLOCKED(no-en-variant)`；**不进 PASS 分母、也不计入缺陷数**，终验报告须单列 |

## 2. 跨 lane 契约核对（终验必跑，与 lane 无关）


### 2.1 API 契约一致性


- [ ] **X-A1 路由清单覆盖 §2–§13**
  - 命令：
    ```bash
    $PY - <<'PY' > "$EV/api-routes.txt"
    from app import create_app
    app = create_app()
    rows = sorted(f"{','.join(sorted(r.methods - {'HEAD','OPTIONS'}))} {r.rule}"
                  for r in app.url_map.iter_rules() if r.rule.startswith('/api/v1'))
    print(len(rows)); print("\n".join(rows))
    PY
    head -1 "$EV/api-routes.txt"
    ```
  - 期望：首行 ≥ 65；`grep -c " /api/v1" "$EV/api-routes.txt"` = 首行数字；§2–§13 每个端点族（health/env/profile/packages/variants/imports/templates/blocks/slots/jds/requirements/company-profiles/builds/artifacts/naming/llm/settings/files/jobs）至少 1 条。

- [ ] **X-A2 错误码与 warnings 码覆盖**（同 CORE-08）
  - 命令：§14 与 §14.1 各跑一次 `comm -23`（doc 码 − code 码）。
  - 期望：两个 `comm` 输出都为空。

- [ ] **X-A3 信封与状态码**
  - 命令：`for p in health env profile packages jds templates builds settings; do curl -s -o /dev/null -w "$p %{http_code}\n" $B/$p; done`；抽 3 个错误路径看 body 键。
  - 期望：全部 2xx；错误 body 恒 `{ok:false,error:{code,message,details?,hint?},request_id}`；成功 body 恒 `{ok:true,data,request_id}`；列表带 `items/next_cursor/total_estimate`；**不用 offset 分页**（`grep -n "offset" server/app/api/*.py` 为 0）。

- [ ] **X-A4 字段名逐条对照（抽样 20 个高频对象）**
  - 命令：把 `tests/acceptance` 里的响应快照与 §3/§4/§8/§10.2 示例做键集合比对（`tests/test_contract.py` 的快照机制）。
  - 期望：键集合相等（多键=漂移，少键=破坏前端）；`NULL` 字段**存在且为 null**，不省略键。

- [ ] **X-A5 状态机语义**
  - 命令：手工走 `import_job: queued→parsing→draft`、`llm_preview: pending→consumed/expired/rejected`、`job: queued→running→succeeded/failed/interrupted`。
  - 期望：无逆向迁移；`llm_preview` 消费用 `UPDATE ... WHERE status='pending'` 的受影响行数判定（`grep -n "rowcount" server/app/services/consent.py` 命中）。

- [ ] **X-A6 幂等与并发**
  - 命令：同一 `Idempotency-Key` 发两次 `POST /packages`；同一 build 同时发两个 export。
  - 期望：第二次返回同一资源 + `Idempotency-Replayed: true`；并发导出第二个 409 `JOB_IN_PROGRESS`。

- [ ] **X-A8 「唯一权威脚本」必须自带 `--self-test`，且样本里必须有已知脏格式**（P1，captain m01601；由 supervisor 自身教训升级）
  - 为什么：`p[8:]` 那次 REV 假高 3（20→23），根因是**自测样本太干净**——只跑总数看不出来。必须喂「一格两条路由」「`methods=["GET","POST"]`」「`{id}` / `<int:id>` / `:id` 三种参数写法」「尾斜杠」四类脏样本，并断言**预期值**而不是「跑通就行」。
  - 命令：`python3 scripts/check_route_parity.py --self-test`；三方各跑 `python3 scripts/check_route_parity.py --json | sha256sum` 比对。
  - 期望：`--self-test` 退出码 0 且打印每个脏样本的**期望/实际**；缺 `--self-test` 或四类脏格式有缺失 → 该脚本不得作判据，相关数字记 `PENDING(canonical-script)`。
  - 归属：脚本无自测/样本过干净 → **coder**；明知无自测仍据此下结论 → **supervisor**。

- [ ] **X-A9 「唯一权威脚本」必须内部自证计数一致性，且自测样本含真实脏格式**（P0，captain m01695，X-A8 升级版）
  - 三条不变量（任一不成立 → **非零退出 + 打印矛盾明细**）：
    ```python
    assert len(matched) + len(fwd) == len(documented_unique), ("FWD 口径不一致", len(documented_unique), len(matched), len(fwd))
    assert len(matched) + len(rev) == len(code_unique),       ("REV 口径不一致", len(code_unique), len(matched), len(rev))
    assert not (set(rev) & set(fwd)),                          ("同一路由同时被算作代码独有与文档独有", sorted(set(rev) & set(fwd))[:5])
    ```
  - `--self-test` 样本**必须包含**两类真实脏格式：① **同一路由在文档里重复出现 3 次**（对应 `rev` 按行收集 → 231 vs 64 的 bug）；② **`<x>` 与 `{x}` 参数写法差异**（对应两侧归一化不一致 → `fwd=64` 与 `matched=64` 并存的 bug）。
  - 现状（2026-10-23 实测，captain）：`counts {"code":64,"documented":108,"documented_table":80,"fwd":64,"matched":64,"rev":231,"rev_table":81}` → **两条不变量同时破**，脚本却静默输出完整报告 ⇒ 记 **FAIL**，归 **coder**。
  - 归属：不变量缺失 / 打印矛盾仍 0 退出 / 自测样本不含上述两类 → **coder**；在脚本修好前拿它的数字重算基线 → **supervisor**。

- [ ] **X-A10 单一维度判据不得单独给 PASS（「格式类」必须配「内容存在性」）**（P0 常驻元规则，captain m02426）
  - 触发实例（2026-10-23 首份 PDF）：`pages==1` 且 `min(size)>=10.0pt` **两个数都达标**，而产物全页只有 **151 字符**（commit 丢了 GPA/CET/课程/技能）。⇒ **排版类判据在内容被丢掉时会全绿**，这是「假绿」最贵的一类：它让 BLOCKER 以 PASS 的面目进终验。
  - 规则：任何判据若只测**形态**（页数、字号、行距、边距、对齐、字符集、JSON 可解析、返回码），**必须**同时配一条测**内容存在性**的判据（字段非空、逐字相等、探针命中、条目数 == 上游条目数），两条同时绿才可 PASS；只有形态绿 → 记 **`INCOMPLETE(单维绿)`**，不得记 PASS。
  - 配对表（必须成对使用）：
    | 形态判据 | 必须配的内容判据 |
    |---|---|
    | CMP-29 页数/字号 | **CMP-31** 教育五探针 + 技能段存在 |
    | CMP-30 越界 0 | CMP-31（词真的在产物里才谈得上越界） |
    | X-A7 路由条数 | 对应端点的 200 + 业务字段断言 |
    | `json.loads` 成功 | INT-14 的 `b'` 扫描 + 业务字段非空 |
    | 字符集覆盖（PDF-02） | CMP-26（`facts[]` 逐字命中） |
  - 归属：只写形态判据 → **supervisor**（本条即自纠：CMP-29 原文只写页数/字号）；形态对而内容空 → **coder**。两侧都要记，不得互相抵消。
  - **第三次实例（2026-10-23 04:57，captain m02680 指出）**：`check_export_pdf.py` 在 zh/en 两版上除 `no_horizontal_overflow` 外**全绿**（`pages=1`、`min_size=9.5`、照片四维、`text_verified`、`cid=0`、`U+FFFD=0`），却对两件事无感：**教育段日期只剩 `2028`（`2024.9`/`2028.6` 都丢）**、**页眉重复学历/专业/届别**。加上首轮的 D-46（内容全丢仍全绿），同一个检查器**两轮各漏一类内容缺陷** ⇒ 已在 CMP-29 配对表下新增 **CMP-38/39/40** 作为独立内容判据，并写明「几何检查器只在它覆盖的维度上下结论，不得据此给内容层 PASS」。
  - **推论（写进终验 runbook）**：外部检查器的 PASS 只是「**在该维度上**没发现缺陷」，**不得**作为「本条内容完整」的证据；报告里引用它时必须同时标注它覆盖了哪些维度、没覆盖哪些。
  - 口诀：**「能装下」不等于「装了东西」，「格式对」不等于「内容在」。**

- [ ] **X-A11 计数类输出必须自带分母，且基线变化必须标明原因**（P1 常驻，captain m01713 + m01756 延伸）
  - 理由：三套互不一致的数字（planner 39/18、supervisor 20/46、captain 21/31）与 `231/64` 那版，**全都是「只有缺口数、没有分母」**；新增实例：手工分组写 `jds 9 / company-profiles 4`（实为 **8 / 5**）、P2 13（实为 12），**两处分子错、合计仍 44 自洽** ⇒ 总数正确**不能**证明分组正确，导致谁也无法互相校验。「REV=39」单独出现时，读者既不知道分母，也不知道 39 是「条」还是「行」。
  - 判据①（分母）：任何计数结论必须成三联出现，例如 `only_in_docs=27 / documented_total=111 / matched=84`；**只有缺口数 → 记 FAIL（不可校验）**。同理适用于警告码条数、D 项数、checkbox 数、失败用例数。
  - 判据②（**变化原因，captain m01756 延伸**）：基线数字变化时必须标明属于 **`判据修正`** 还是 **`实现推进`**，并写「旧值 → 新值 + 原因」；**只报数字不报原因 → 同样记 FAIL**。理由：同一指标四次变化（39/18 → 20/46 → 231/64 → 44 → 43）里只有最后一次是代码真动了，混在一起会误判成「一直没收敛」。台账见 §2.1.3「变化原因」列。
  - 归属：只报分子 → **supervisor**（判据表述缺陷）；分子分母口径不同（如分子按行、分母按条）→ **coder**（脚本口径未统一）。
  - 判据④（**一格多值必须按单元格展开计数**，captain m02496）：凡表格存在「一格多值」可能（`A` / `B` / `C` 写在一格、`均可`、合并行），计数**必须**按单元格 `split` 后展开累加，并**同时输出「行数」与「值数」两个数**；只用 `grep -o`/`grep -E '^\| *`[A-Z]'` 取每行首个匹配 = **命令盲区**，会静默少数且两边都会数错（实例：`§14.1` 45 行 / 48 码）。归属：判据只写行数 → **supervisor**；表格仍留合并行 → **planner/coder**（写表的一方）。
  - 判据③（**表头总数必须由入册同日的命令复算并留输出**，captain m02469）：表头写「共 N 条」时，N 必须能被一条**同日跑过**的命令产出并贴进条目；跨版本沿用旧的折算说明（如「1 行 4 码合并按 4 条计」）而表格已被改过 → **记文档方**。复算必须**同时报行数与码数**：`awk '/^## 14\.1/{f=1} f&&/^## 15\./{exit} f' docs/API-CONTRACT.md | grep -cE '^\| *`[A-Z]'` 只给行数，把首列按 `/` 拆开再计数才给码数——**只报其中一个就是本条说的「有分母没分子」**。


- [ ] **X-A7 路由双向一致性：文档里的每个路由都要能在代码里找到，反之亦然**（P0，captain 2026-10-23 要求；一次消灭「文档路由 vs 实现路由」整类漂移）
  - 为什么用「双向」：单向查（只查文档→代码）只能发现「写了没做」，漏掉「做了没写」——而后者才是前端联调时最容易踩的（`grep` 找不到定义就以为不存在）。D-29（`/profile/photo/from-import` 契约有、实现无）是「写了没做」；`/api/v1/now`、`/packages/stats`、`/llm/purposes` 是「做了没写」。
  - 可复制脚本：**唯一权威入口是 `scripts/check_route_parity.py`**（键名 `documented_total/code_total/matched/only_in_code/only_in_docs`，稳定排序 JSON、`--self-test`、7 条不变量）；§2.1.1 是 planner 版历史稿（只认 `` `METHOD /path` `` 一种写法，有已知漏项），§2.1.2 是两样式改进版，二者**只作追溯，不作判据**。两版差异实测：REV **39 → 20**、FWD **18 → 46**，原因见 §2.1.2。
  - ⚠️ **判据自身的坑**：只解析单一样式会让「文档写了（两栏式）」被误判成「文档没写」，于是 REV 假高；同时把「真没实现」藏进 FWD 之外。**改判据后必须重算基线并在台账记「旧值 → 新值 + 原因」**（§0.3.3）。
  - 判定规则（**按 lane 分档，不许一刀切**）：
    | 差异 | 判据 |
    |---|---|
    | `code_only` 中的**真实路由** | **一律 FAIL**，归 **planner**（补契约）或 **coder**（删多余路由）；唯一白名单：`GET /api/health`（健康检查别名，见 `server/app/api/__init__.py:1` docstring） |
    | `code_only` 中的 **DEBUG/内部** | 若确属内部用途（如 `/now`），也必须在契约登记为 internal，否则同 FAIL |
    | `doc_only` 且**该 lane 未交付** | 允许，记 `PENDING(lane)`；lane 交付后必须清零 |
    | `doc_only` 且**该 lane 已交付** | **FAIL**，归 **coder**（未实现契约端点） |
  - **基线状态：已定稿（2026-10-23 04:4x）**——唯一权威脚本 `scripts/check_route_parity.py`，退出码 0、7 条不变量全 `true`：`documented_total=111 / code_total=84 / matched=84 / only_in_code=0 / only_in_docs=27`（**2026-10-23 04:5x 现行**；旧的 43 已作废，见 §2.1.3 v7 台账）。本条的 `doc=74 / code=65` 是**本脚本口径**（只解析内联 `` `METHOD /path` ``）的历史值，**不得再作基线**；引用基线一律用上面这一组（脚本路径 + 退出码 + 不变量 + 日期 + 分母）。旧说明如下：`doc=74 / code=65` 是本脚本（§2.1.1，只解析内联 `` `METHOD /path` ``）在 2026-10-23 03:43 的口径值，与 §2.1.2、captain 版三方数字不一致（见 §0.3.3 第 4 条）。等 `scripts/check_route_parity.py` 落地后统一重算，届时本节数字才可写死。以下仅为**该脚本口径下的历史值**：`doc=74 / code=65`；`doc_only=31`（全部落在未交付 lane：builds 8、jds 5、templates 7、slots/blocks 3、company-profiles 2、fetch 1、artifacts 2、requirements 3）→ 记 `PENDING(lane)`；`code_only=21`，其中 `GET /api/health` 为白名单，**其余 20 条为真实文档缺口**（`/now`、`/packages/stats`、`/packages/draft`、`/packages/reindex`、`/packages/{id}/verify`、`/llm/purposes`、`/llm/previews`、`/files`(GET/POST)、`/files/{id}`(DELETE)、`/jobs`(GET)、`/imports/{id}/export-draft`、`/naming/template`(GET/PUT)、`/templates/default`、`/templates/{id}`(DELETE)、`PUT /packages/{id}`、`PATCH/PUT/DELETE /packages/{id}/variants/{vid}`、`PUT /variants/{id}`）。**这 20 条已派 planner 补契约**（与 D-29 同批）。
  - **同类项⑨：分母必须是可用空间，不是纸张尺寸**（captain m01941）。凡「装得下/装不下」类判据，分母一律 `页高 − 上边距 − 下边距`（必要时再减页眉页脚），**禁止**「内容高度 vs 纸张高度」；uier 的「溢出 56px≈15mm」正是漏了这一步减法（真实缺口 ≈54mm）。同类错还包括：用 chars 总数当「行数」、用 `len(raw)` 当「字符数」（未去空白）。违反 → 判据方 **supervisor**；实现方报错口径 → **coder**。
  - **同类项⑧：估算值不得作为基线**（captain m01877 归入本族）。凡「设计期估算 / 用临时页面量 / 用精简样张量」得到的数字（例：`docs/DESIGN.md §12.4` 的 10.5pt→溢出 56px、10pt→余 21px），必须在**源头与引用处都标「估算」**，且**不得作为任何 PASS/FAIL 依据**；真实基线只能由**最终产物**（首份 PDF、真实库查询）产生。产物出现前该条记 `BLOCKED(no-artifact)`；产物与估算冲突时**以产物为准**，并回写文档把「估算」改成「实测（含日期与命令）」。违反 → 记 **supervisor**（把估算当基线）。
  - 归属：`doc_only` → coder；`code_only` → planner（或 coder 删）；**用 grep 装饰器代替 `url_map` 得到「全部一致」的结论 → 归 supervisor（判据错）**。


### 2.1.1 X-A7 路由一致性脚本（可直接复制执行）

> 单独成节的原因：列表项内的代码块每行会带 4 空格缩进，复制到终端后 `python - <<'PY'` 里的 `import` 顶格错位（`IndentationError: unexpected indent`）。本节 fence 顶格。

```bash
cd resume-warehouse && PYTHONPATH=server .venv/bin/python - <<'PY'
import re, json, sys
sys.path.insert(0, "server")
doc = open("docs/API-CONTRACT.md", encoding="utf-8").read()
docn = set()
for m, path in re.findall(r"\|\s*`(GET|POST|PUT|PATCH|DELETE)`\s*\|\s*`(/[^`]+)`", doc):
    p = path.split(" ")[0]
    if not p.startswith("/api"):
        p = "/api/v1" + p
    docn.add((m, re.sub(r"\{[^}]+\}", "{x}", p)))
for m, p in re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/api/v1/[A-Za-z0-9_\-/{}]+)", doc):
    docn.add((m, re.sub(r"\{[^}]+\}", "{x}", p)))
from app import create_app
code = set()
for r in create_app().url_map.iter_rules():
    if r.endpoint == "static":
        continue
    for m in (r.methods - {"HEAD", "OPTIONS"}):
        code.add((m, re.sub(r"<[^>]+>", "{x}", r.rule)))
only_doc, only_code = sorted(docn - code), sorted(code - docn)
print(json.dumps({"doc": len(docn), "code": len(code),
                  "doc_only": only_doc, "code_only": only_code},
                 ensure_ascii=False, indent=1))
PY
```


### 2.1.2 路由/码位一致性独立复核（2026-10-23 04:0x，supervisor 自跑）— **基线已于 04:4x 定稿（canonical script）**

> **状态**：本节脚本**只作自测样本，不作契约判据**。captain 已派 coder 写唯一权威脚本 `scripts/check_route_parity.py`（稳定排序 JSON、归一化规则写在脚本头、带 `--self-test` 内置脏格式样本）。落地后**以「三方跑同一脚本、JSON 逐字节相同」为判据**，届时重算基线并更新本节与 §16.1。
>
> planner 在 `docs/API-CONTRACT.md §16` 报了 REV **39** / FWD **18** / 码位 **0**。我按原文抽取实跑，**码位 0 一致**，但**路由两向都不一致**——原因不在数据，在**解析样式**：planner 脚本只认 `` `GET /path` `` 一种写法，而契约里大量路由是「方法一栏 + 路径一栏」的两栏表格（例：`| `PATCH` / `DELETE` | `/blocks/{id}` |`），于是这批路由被当成「文档没写」。

**改进版（两样式都解析，t11 以此为准）**：

```bash
cd resume-warehouse && python3 - <<'EOF'
import re, pathlib
root=pathlib.Path(".").resolve(); docs=root/"docs"
def norm(p):
    p=p.split("?")[0].split("#")[0].rstrip("/")
    p=re.sub(r"<[^>]+>","*",p); p=re.sub(r"\{[^}]+\}","*",p); return p or "/"
code={}
for f in (root/"server/app/api").rglob("*.py"):
    for m in re.finditer(r'@\w+\.(get|post|put|patch|delete)\(\s*"([^"]+)"',f.read_text(encoding="utf-8")):
        code[(m.group(1).upper(),norm(m.group(2)))]=f.name
docset={}
for f in docs.glob("*.md"):
    if f.name=="docs/maintainers/REVIEW-CHECKLIST.md": continue
    t=f.read_text(encoding="utf-8")
    for m in re.finditer(r'`(GET|POST|PUT|PATCH|DELETE) (/[^`\s]+)`',t):
        p=m.group(2); docset[(m.group(1),norm(p[len("/api/v1"):] if p.startswith("/api/v1") else p))]=f.name
    for m in re.finditer(r'^\|\s*((?:`(?:GET|POST|PUT|PATCH|DELETE)`\s*(?:/\s*)?)+)\|\s*`(/[^`]+)`',t,re.M):
        p=m.group(2)
        for me in re.findall(r'`(GET|POST|PUT|PATCH|DELETE)`',m.group(1)):
            docset.setdefault((me,norm(p[len("/api/v1"):] if p.startswith("/api/v1") else p)),f.name)
rev=sorted(k for k in code if k not in docset); fwd=sorted(k for k in docset if k not in code)
print("REV =",len(rev),"（代码有、文档无）"); [print("  ",m,p) for m,p in rev]
print("FWD =",len(fwd),"（文档有、代码无）"); [print("  ",m,p) for m,p in fwd]
EOF
```

**实测结论（2026-10-23 04:0x）**：

| 项 | planner 报 | 我实测（改进版） | 差异原因 |
|---|---|---|---|
| REV（代码有、文档无） | 39 | **20** | 其中 **19 条是两栏表格里的已文档路由**，被单样式解析误判（`/packages/*` 子资源、`/files`、`/jobs`、`/llm/*`、`/naming/template` 等） |
| FWD（文档有、代码无） | 18 | **46** | 两栏表格里的**未实现**端点被漏掉：`/blocks`、`/slots`、`/templates/*/blocks`、`/templates/{id}/default`、`/builds*` 全量、`/jds*`、`/company-profiles*`、`/artifacts/*` |
| 码位（未登记 `"CODE"`） | 0 | **0** | 一致（`awk '/^## 14\.1/,/^## 15\./' ... = 27 行 + 折算 3 = 30`，v1.15 补齐） |

> **定稿（2026-10-23 04:4x，`scripts/check_route_parity.py`，退出码 0、7 条不变量全 true）**：`documented_total=111 / code_total=84 / matched=84 / only_in_code=0 / only_in_docs=27`（**2026-10-23 04:5x 现行**；旧的 43 已作废，见 §2.1.3 v7 台账）。本节的 20/46 与 planner 的 39/18、captain 的 21/31 均为**历史判据口径**，只留作「变化原因」证据（见 §2.1.3 台账），**不再作基线**。
> **三方数字（2026-10-23 04:2x，captain 独立实现）：planner 39/18、supervisor 20/46、captain 21/31。**
> 结论不是「谁错了」，而是**这个指标还没定义**——四个自由度（见 §0.3.3 第 4 条）三方各选一套。因此 REV/FWD **当时不写死任何数字**，统一记 `PENDING(canonical-script)`。**现已由 canonical script 定稿（见上），本节数字仅供追溯。**

**FWD 里「该实现却没实现」的部分（captain m01572 裁定后分档，不再一律判 coder 做）**

> **先看写作路径**：结构化写作的真实入口是**导入校对**——用户在导入校对页改名/合并/拆分/换章节，改的是 draft（`PUT /imports/{id}/draft`，已实现），`commit` 才生成 `template_block`。所以**核心 UX 不需要 post-hoc 编辑模板**；模板写侧只是「手动微调已入库结构」的增强，不是必经路径。

| 端点 | 归属 | 档位 | 处置 |
|---|---|---|---|
| `POST /templates/{id}/blocks/reorder` | coder | **P1（t10 前置）** | 实现 |
| `POST /templates/{id}/validate` | coder | **P1（t10 前置）** | 实现 |
| `POST /templates/{id}/default`（**写**默认，且保证唯一） | coder | **P1（t10 前置）** | 实现；与 `GET /templates/default`（**读**默认）语义不同，**两者都要** |
| `POST /templates`、`POST /templates/{id}/blocks`、`POST /blocks`、`PATCH/DELETE /blocks/{id}`、`GET/POST /blocks/{id}/slots`、`PATCH/DELETE /slots/{id}` | planner 标 `[P2 未实现]`；coder 择机 | **P2** | 契约写明「模板结构首次生成走导入校对；post-hoc 编辑为 P2 增强」；**t10 不得因『契约写了但没实现』判红** |
| `/builds*`、`/jds*`、`/company-profiles*`、`/artifacts/*`、`/fetch/public-page` | — | `PENDING(lane)` | 未交付 lane，不算缺陷 |

**真库现状（captain 实测）**：现有 3 个模板**全部 `is_default=0`** → t8 组装没有确定 default 会**静默失败**，这正是 `POST /templates/{id}/default` 必须进 P1 的理由。

**处置优先级（captain m01572 裁定，t10 前置闸）**

| 优先级 | 事项 | 归属 | 验收口径 |
|---|---|---|---|
| **P0 ✅ 已闭环** | `DELETE /files/{id}` 加引用守卫 + **改删除顺序**（captain m01601 升 P0，证据 `server/app/services/storage.py:263-269` + `server/app/api/files.py:82-88`：现链路是 **HTTP 204 → 先 `DELETE FROM attachment` → 再 `unlink()`**，内容寻址**无副本**，中途异常留孤儿） | coder | ① 命中 `user_profile.photo_path` / 导入候选 / `build_artifact` → **409 `FILE_IN_USE`**，`details.referenced_by` 是**人话**（如「该文件是当前简历照片（user_profile.photo_path）」而非只给表名）；② **顺序必须是「先查引用 → 再删行 → 最后 unlink」**（禁止反序）；③ **禁止提供 force/`?force=1` 之类绕过参数**；④ 复验：被引用附件 DELETE→409 且文件仍在；解绑后 DELETE→204 且文件消失；构造 unlink 抛错 → 行仍在（不能出现「行没了文件还在」） |
| **P0** | `OUTPUT_TRUNCATED` / `LLM_EMPTY_CONTENT` 补 `severity="warn"` + `details{finish_reason, completion_tokens, max_tokens}`（`llm_client.py:421/450`） | coder | CORE-28 静态三条断言转绿；行为侧仍需常驻横幅 |
| **P1** | `/packages/{pid}/variants/{vid}` 为唯一推荐写路径；`/variants/{id}` 标弃用（响应加 `deprecated:true` 或契约注明），**先不删** | coder + planner | 两套都可调用但契约只推荐一套；弃用标记可从响应或文档二选一取证 |
| **P1** | `POST /templates/{id}/default`（写默认） | coder | 调两次不同 id → 只有一个 `is_default=1`；新库默认模板存在 |
| **P2** | `GET /now` 登记为 internal 或删除 | coder + planner | 契约 §2 或 §14 有对应说明 |
| **P2** | `GET /files` 的 `original_name` 登记「仅本机、永不进 payload」 | planner | X-F13 静态面命中该条 |

**`DELETE /files` 引用守卫：已闭环（captain m01756 行为验证 + 本节可复跑判据）**

判据（临时实例，五步）：

```bash
export DATA_DIR=data/.tmp_guard; PORT=8807   # 绝不碰真库
$PY server/server.py --port $PORT &          # 或按 INT-11 的子进程模板
B=http://127.0.0.1:$PORT/api/v1
curl -s -X PUT $B/profile -H 'Content-Type: application/json' \
  -d '{"name_zh":"判据测试","school_zh":"某大学"}'          # ① 建 profile（空库必须先有）
curl -s -X POST $B/profile/photo -F "file=@server/tests/fixtures/photo_placeholder.png"  # ② 挂照片（620B 夹具），记 attachment_id=A
curl -s -o /tmp/del1.json -w '%{http_code}\n' -X DELETE $B/files/$A                  # ③ 期望 409
curl -s -X DELETE $B/profile/photo                                            # ④ 解除绑定，期望 200
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE $B/files/$A                # ⑤ 期望 204
ls data/files/ | grep -c "$A"                                                 # 期望 0（文件真的没了）
```

**本节实跑回执（2026-10-23 04:0x，`DATA_DIR=data/.tmp_guard_chk --port 8811`，跑完即删目录）**：
```
① PUT /profile            → 200
② POST /profile/photo     → 200, attachment_id=01a165329c217e09b77d139cc36a13e0
③ DELETE /files/<aid>     → 409 {"code":"FILE_IN_USE","details":{"referenced_by":["个人资料照片"]}, "hint":"请先在个人资料页解除绑定…"}
④ DELETE /profile/photo   → 200
⑤ DELETE /files/<aid>     → 204
   遗留 png 文件数 = 0
```

断言：③ 为 **409** 且 `error.code=="FILE_IN_USE"`、`details.referenced_by` 非空且是**人话**（captain 实测 `["个人资料照片"]`）、`hint` 指明解除路径；⑤ 为 **204** 且**磁盘文件确实不存在**（只删行不算通过）；反向：`referenced_by` 返回 `["attachment:01a1…"]` 这类机器串 → 记 coder（可读性）；返回空数组 → 记 coder（未真正查引用）。

**顺序纪律（同时挂 §0.3.4 第 4 条）**：`storage.delete_attachment()` 的正确顺序是「**先查引用 → 再删行 → 最后 unlink**」——反序的后果是「中途抛异常留下孤儿」，更糟的是「先 unlink 再发现被引用，照片永久没了」。删除类操作**必须先完成所有校验，再做不可逆动作**。

> **本脚本自己也错过一次（按 §0.3.3 记账）**：初版把前缀剥离写成 `p[8:]`，多剥了前导斜杠（`/files/*` → `files/*`），与代码侧规范化结果不匹配 → REV 假高 3（**20 → 23**）；改为 `p[len("/api/v1"):]` 后回到 20。**判据脚本的自测样本必须是「已知两栏式路由」**（例：`| `PATCH` / `DELETE` | `/blocks/{id}` |`），只跑一遍总数看不出来。

> **纪律**：本节数字与 planner 的差异不是「我对他错」，而是**判据解析口径不同**——以后凡报「N 条一致性缺口」，必须同时报「用的哪个脚本 + 解析了哪些写法」，否则数字不可比（§0.3.3 第 3 条）。

**路由表格格式纪律（常驻，D-34 转正）**

```python
import re
lines = open("docs/API-CONTRACT.md", encoding="utf-8").read().split("\n")
pat = re.compile(r'^\|.*?`(/[^`]+)`\s*/\s*(?:`(?:GET|POST|PUT|PATCH|DELETE)`\s*)?`?(/[^`|]+)`?\s*\|')
multi = [(n + 1, l.strip()[:90]) for n, l in enumerate(lines) if pat.search(l)]
print("one_cell_two_routes =", len(multi))
for n, l in multi:
    print(" ", n, l)
```

期望：`one_cell_two_routes = 0`（2026-10-23 04:3x 基线 0；planner 已在 `API-CONTRACT.md:1197` 立格式纪律）。一格两条路由或多方法合写会让三家解析器再次分叉，命中即判 **planner**。**不要**用 `grep -c '` / '` 代替——它会把正文里「`a` / `b`」的排版也计入（实测 21 处噪声）。

**废弃/删除措辞必须与表内条目零冲突（captain m01572 新增，P1）**

```bash
grep -n '已经删除\|已删除\|废弃\|不再使用\|已移除' \
  docs/API-CONTRACT.md docs/DATA-MODEL.md docs/ARCHITECTURE.md docs/ACCEPTANCE.md
```

判据：**命中数不作通过条件**（§0.3 T-5，计数会随文档改动自行变绿）；逐条人工过——凡「某码 / 某端点已删除、已废弃」的表述**与当前表内仍在的条目冲突**，必须删掉或改写。已发生实例 **D-33**（`§14.1` 末尾「`OUTPUT_TRUNCATED` 已于 v1.6 删除」↔ 同节 v1.15 新登记）。归属：同一份文档前后自相矛盾 → **planner**；读者不知道该信哪句，比单条漏写更危险。

### 2.1.3 `only_in_docs` 归属分类台账（脚本 JSON 逐条机器归类；2026-10-23 04:4x）

> **口径（写全）**：`scripts/check_route_parity.py`（唯一权威脚本，键名已改为 `documented_total / code_total / matched / only_in_code / only_in_docs`），**退出码 0**、**7 条不变量全 `true`**，2026-10-23 04:4x：
> **现行基线（2026-10-23 04:5x 实跑，退出码 0、7 条不变量全 `true`）**：`documented_total=111 / code_total=84 / matched=84 / only_in_code=0 / only_in_docs=**27** / mentions=324`（`mentions` 只作参考、不进判据）。**旧的 43 已作废**（见 v7 台账行）。
> **状态**：数字已可对账（不变量全绿 + 逐条 `(method, path)` 清单），**但按 captain 要求仍记「作台账、待脚本定稿」**——下一次跑出任何差异，一律以脚本 JSON 为准并回查归类逻辑。
> **结论（抄进 t11 结论页）**：`only_in_docs` 27 条**全部可归因**到「未交付 lane」或「已裁定的 P1/P2」，**没有一条是「该实现却没实现」的漏项** ⇒ **t10 不得因此判红**。

| 归属 | 条数 | 族细分 | 处置 | 变化原因（相对 44 版） |
|---|---|---|---|---|
| t7 已交付（ANL） | **0** | 曾 16（`jds` 8 + `company-profiles` 5 + `requirements` 2 + `fetch` 1） | 已全部实现，出册 | **实现推进**（t7 completed） |
| t8 未交付（CMP） | **13** | `builds` 11 + `artifacts` 2 | `PENDING(lane)`，t8 交付后复跑 | 不变 |
| **P1 · t10 前置** | **2** | `POST /templates/{id}/blocks/reorder`、`POST /templates/{id}/validate` | 必须实现（t10 前置门） | **实现推进**：`POST /templates/{id}/default` 已实现，`code_total 64→65`、`matched 64→65` |
| P2 增强 | **12** | `blocks` 5 + `templates` 4 + `slots` 3 | 契约标 `[P2 未实现]`，不计红 | 不变 |
| **合计** | **27** | 0 + 13 + 2 + 12 | 与脚本 `only_in_docs=27` 对齐 | **43 → 27**：t7 的 16 条随交付出册（实现推进）；`documented_total` 108 → 111、`code_total` 65 → 84（同一批新增路由，见 v7） |

**变化原因台账（X-A11 延伸：只报数字不报原因同样不可校验）**

| 版本 | 数字 | 变化原因 | 备注 |
|---|---|---|---|
| v1 planner §16 | REV 39 / FWD 18 / 码位 0 | —（首版） | 只解析内联 `` `METHOD /path` `` |
| v2 supervisor 两样式 | REV 20 / FWD 46 | **判据修正** | 补「方法一栏 + 路径一栏」两栏表格 |
| v3 captain 独立实现 | REV 21 / FWD 31 | **判据修正**（口径不同） | 三方各选一套定义 ⇒ 指标当时未定义 |
| v4 canonical 首版 | REV 231 / FWD 64 | **判据缺陷**（脚本自身错） | `rev` 按行收集、`fwd` 与 `matched` 并存、无不变量 |
| v5 canonical 修正 | `only_in_docs=44` | **判据修正** | 键名改正、7 条不变量全绿、`doc=108/code=64/matched=64` |
| v6 canonical + 实现 | `only_in_docs=43` | **实现推进**（代码真的动了） | `POST /templates/{id}/default` 落地，`code=65/matched=65` |
| v7 t7 交付后 | `only_in_docs=27` | **实现推进 + 文档推进**（不是判据修正） | t7 的 16 条出册；`doc 108→111`/`code 65→84`/`matched 84`；27 = `builds` 11 + `artifacts` 2 + `templates` 6 + `blocks` 5 + `slots` 3，逐条已核 |

> **口诀**：**「判据修正」与「实现推进」必须分栏记**。混在一起看，会得出「一直没收敛」的错误结论；只看数字不看原因，等于 X-A11 的反面——数字对了也不知道该不该高兴。

**归因纪律（写进 §3，t11 照此判）**：`only_in_docs` 里属 `PENDING(lane)` 的只记「未交付」，**不记 coder 缺陷**；属 P1 的记 coder 缺陷（t10 前置）；属 P2 的记 `[P2 未实现]`，**不判红**。三类都不得合并成一个「缺 N 条」的结论。

> **口径教训（captain m01740 自纠，留作证据）**：上一版手工分组写「`jds` 9 / `company-profiles` 4」（实为 **8 / 5**）、P2 写 13（实为 **12**）——**分子错了两处、合计仍自洽 44**。结论：**总数正确不能证明分组正确**；分组一律以脚本 JSON 逐条归类为准。

### 2.1.3a 夹具卫生（常驻，captain m02073）

**规则**：**判据夹具只能是被测文本本身**。用途、期望、判据说明一律放 `expectations.json` 的 `_meta`，**不得写进 `.md`**。

- **为什么**：分析器读的是整份 `.md`。说明文字里出现「不得编造『985/211』之类门槛」，就会被 `detect_school_gate` 当成 JD 正文 → **负例反而产出 `preferred_tiers=['985','211']`**（本轮真实事故：`jd_school_filtered.md` 自污染）。
- **验收**：夹具目录里 `grep -nE "不得|期望|判据|示例|说明" data/eval/jd_samples/*.md` → 除 `_meta` 外 0 命中；且 `jd_no_school.md` 的 `grep -cE "院校|学校|985|211"` = **0**。
- **现状（04:14:07 重写后）**：`jd_school_preference.md`（偏好）/ `jd_school_hard.md`（硬门槛）/ `jd_no_school.md`（无信号）三例干净；`jd_school_filtered.md` **已废弃**，任何条目引用它一律改指新三例。
- **归属**：夹具里夹带元话语 → **夹具作者**（本轮 captain）；引用已废弃夹具 → **supervisor**。

### 2.1.4 表格必须是矩形（NF 一致）——所有「按列解析」判据的前提

**为什么单列**：FWD/REV、字段清单比对、码表计数都按列取值。只要一行缺格/多格、或**整表缺表头**、或**空行之后的续行块没有表头**，后续解析就整体错位且**肉眼看不出来**。本项在 r 轮内连续抓到四个同类：`IMPORT_DRAFT_PRUNED` 多一列、`§14` 错误码表整表缺表头、`ARCHITECTURE §5.1` 4 行孤儿表（2 格行挂在 4 列表后）、以及**本清单自己的 D-40 行缺一格**。

**判据（唯一权威脚本，抄 `docs/API-CONTRACT.md §16.0 M3`，禁止退回旧版）**

```bash
cd resume-warehouse && python3 - <<'EOF'
import glob,re
def cells(line):
    s=line.replace("\\|","\x00")                                   # (1) 转义竖线不是分隔符
    s=re.sub(r"`[^`]*`",lambda m:m.group(0).replace("|","\x01"),s)  # (2) 反引号内的竖线不是分隔符
    p=s.split("|")
    if p and p[0].strip()=="":p=p[1:]
    if p and p[-1].strip()=="":p=p[:-1]
    return p
bad=0
for f in sorted(glob.glob("docs/*.md")):
    if "REVIEW-CHECKLIST" in f or f.endswith("DESIGN.md"): continue   # 他人产物只报不改（见下）
    L=open(f,encoding="utf-8").read().split("\n");i=0;last=None
    while i<len(L):
        if L[i].startswith("|"):
            j=i
            while j<len(L) and L[j].startswith("|"): j+=1
            if j-i>=2 and re.match(r'^\|[\s:\-|]+\|$',L[i+1]): last=len(cells(L[i]))   # 表头决定列数
            if last is not None:
                for k in range(i,j):        # (3) 空行分隔的续行仍属上一张表
                    if len(cells(L[k]))!=last:
                        print("MISMATCH %s:%d 期望%d列 实得%d列"%(f,k+1,last,len(cells(L[k]))));bad+=1
            i=j
        else:i+=1
print("表格列数 mismatch =",bad)
EOF
```

- **期望**：`表格列数 mismatch = 0`。
- **基线（2026-10-23 04:15:53 实测）**：`docs/`（排除 `docs/maintainers/REVIEW-CHECKLIST.md`/`DESIGN.md`）→ **0**；把同一逻辑扩到 `docs/maintainers/REVIEW-CHECKLIST.md` 曾抓到 **1 处**（`:2162` D-40 行缺「影响」格），**已修**，现 **0**。`DATA-MODEL.md:416` 与 `API-CONTRACT §14.1/§14`、`ARCHITECTURE §5.1` 均已由 planner 修好。
- **三个「别退回」的坑**：① 不抹 `\|` → 含转义竖线的行全部误判；② 不处理反引号内 `|` → 含正则/命令的行误判；③ **只按「表头 + 分隔行」切块** → 空行后的续行块漏检（`IMPORT_DRAFT_PRUNED` 正是这样漏了 3 版）。
- **他人产物**：`docs/maintainers/REVIEW-CHECKLIST.md`（supervisor）与 `docs/DESIGN.md`（uier）不在 planner 的扫描范围，由各自 owner 用同一逻辑自检；**报 mismatch 给 owner，不代改**。
- **归属**：文档表格 → **planner**；本清单自身 → **supervisor**。

### 2.1.5 文档状态口径（M5 指代 / M6 表头），与契约 §16.0 同步

- **M5 跨 agent 指代一律按内容，不按编号**：同一编号在两份文档里可以是两件事（已发生：本清单 `D-39` = `data/eval/check_export_pdf.py --right-margin` 默认 42.5pt；`API-CONTRACT.md` 的 `D-39` = 门槛动词分组）。写法：**「§7 门槛动词分组（契约 D-39）」「清单里那条 `--right-margin`」**，不写裸编号。判据：终验记录里出现裸 `D-nn` 且无内容限定 → 记 **supervisor**（表述缺陷，轻）。
- **M6 文件头/表头只写版本与条目编号，不写具体条目的通过/失败结论**：条目状态一律以**条目行**为准。
- **配套元规则**：单维判据一律按 **X-A10** 处理——形态类（页数/字号/越界/可解析）**必须**与内容存在性判据成对给结论，只有形态绿记 `INCOMPLETE(单维绿)`。CMP-29 单独 PASS 的情形（D-46 那次）即本条的反例。
  ```bash
  cd resume-warehouse
  # 表头不得出现具体条目的结论词（出现即表头越权，需删结论只留编号）
  grep -nE '^> 冻结' docs/ACCEPTANCE.md | grep -cE 'AC-[A-Z]+-[0-9]+.*(已修复|已通过|KNOWN-FAIL)'   # 不限 ANL，M6 管所有条目
  ```
  期望：**0 命中**。现状（2026-10-23 04:2x）：v1.19 那行仍有 `AC-ANL-12` + 「已修复，保留为回归判据」→ 属**残留的旧结论**，现记 **D-44（P2）**；条目行 `:268` 正确。
- 归属：表头写结论 → **planner**；引用裸编号造成歧义 → 当事人（多为 **supervisor**）；两边口径不一致时以 `API-CONTRACT §16.0` 的 M 系列为准。

- **外部验收器的定位（正交证据，不替代判据）**：captain 侧 `data/eval/check_export_pdf.py`（只读）判页数 / 最小字号 / 字号众数 / 照片（`w,h,x0,距顶,距右`，**按 mediabox 归一**）/ 横向溢出 / 条目完整性，已自验「用户原件默认密度判 PASS」（`min_size 10.0`、照片 `89.28×89.28`、距顶 `3.82`、距右 `9.13`）。用法：**t11 跑它作为第三方证据**，与本节 CMP-20/29/30 互为校验；**冲突时以逐条实测口径为准**，并把差异记入缺陷台账（不直接采信任一方的总结论）。注意它 `--right-margin` 默认 42.5pt 会对紧排原件假红（D-39），必须显式传实测值。

### 2.1.6 计数口径纪律（AC 表 / 码表 / 任何「行 vs 值」）

同一类缺陷的第三次实例（前两次：`grep -o` 每行只取首个匹配；`cut -c[0-9]+-` 假红）：**过滤条件本身会漏掉整批行**。

- **AC 表有两种行写法**：`| AC-XXX-01 | P0 | …`（129 行）与 `| **AC-XXX-15** | P0 | …`（28 行，加粗）。用 `startswith("| AC-")` 会**整批漏掉 28 条**（且其中多条是 P0），覆盖率因此虚高。
- **唯一权威口径**（两种都认、按单元格判优先级）：
  ```bash
  cd resume-warehouse && python3 - <<'PY'
  import pathlib, re
  rows = []
  for l in pathlib.Path("docs/ACCEPTANCE.md").read_text(encoding="utf-8").split("\n"):
      if not l.startswith("|"): continue
      cells = [c.strip() for c in l.strip().strip("|").split("|")]
      if cells and re.search(r"AC-[A-Z]+-\d+", cells[0]): rows.append(cells)
  ids = [re.search(r"AC-[A-Z]+-\d+", c[0]).group(0) for c in rows]
  p0 = sum(any(x == "P0" for x in c[1:5]) for c in rows)
  p1 = sum(any(x == "P1" for x in c[1:5]) for c in rows)
  print(f"行 {len(rows)} / 唯一 {len(set(ids))} / P0 {p0} / P1 {p1}")
  PY
  ```
  基线（`docs/ACCEPTANCE.md` v1.26，mtime 2026-10-23 05:02:36）＝ **行 152 / 唯一 146 / P0 96 / P1 46**。
- **扫前自检**：先打印「命中行数」与「按不同筛选式各自的行数」，两个数不同就先解释差异再报结论；`tests/acceptance/AC_INDEX.md` 的生成脚本必须用上面这版（正则取首格，**不用 `startswith`**）。
- **归属**：用会漏行的过滤条件得出「覆盖率/缺口数」→ **supervisor**（判据侧），不得据此判 coder。

### 2.2 数据模型漂移

- [ ] **X-B1 表清单**
  - 命令：`sqlite3 data/app.db "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by 1;"`
  - 期望：含 19 张声明表（`user_profile, package, package_bullet_variant, template, template_block, slot, import_job, attachment, job_description, jd_requirement, company_profile, resume_build, build_selection, build_artifact, job, llm_preview, llm_call_log, app_setting, schema_migration`）+ `package_fts`（及 FTS5 自动影子表 `*_data/_idx/_content/_docsize/_config`）。

- [ ] **X-B2 关键列存在性（防字段名漂移）**
  - 命令：
    ```bash
    $PY - <<'PY'
    import sqlite3
    db = sqlite3.connect('data/app.db')
    want = {
      'user_profile': 'id name_zh name_en school_zh school_en phone email photo_path links_json extra_json updated_at',
      'package': 'id title kind org role summary tech_stack_json tags_json outcomes_json status deleted_at',
      'package_bullet_variant': 'id package_id bullet_key tone lang text keywords_json llm_generated verified',
      'resume_build': 'id template_id jd_id naming_pattern naming_overrides_json field_values_json lang status est_pages',
      'build_selection': 'id build_id package_id variant_ids_json order_index overrides_json snapshot_json',
      'build_artifact': 'id build_id format engine filename rel_path bytes sha256 text_verified text_diff_json warnings_json',
      'llm_preview': 'id purpose provider model endpoint_host payload_json payload_sha256 field_manifest_json status expires_at consumed_at',
      'llm_call_log': 'id preview_id provider model endpoint_host field_names_json payload_bytes est_tokens http_status latency_ms ok error_code',
      'app_setting': 'key value updated_at',
    }
    drift = []
    for t, cols in want.items():
        have = {r[1] for r in db.execute(f'pragma table_info({t})')}
        miss = [c for c in cols.split() if c not in have]
        if miss: drift.append((t, miss))
    print('DRIFT:', drift or 'none')
    PY
    ```
  - 期望：`DRIFT: none`。

- [ ] **X-B3 不变量 I1–I9 有代码落点**
  - 命令：`for i in 1 2 3 4 5 6 7 8 9; do grep -rn "I$i" server/app/ | head -2; done`（或用注释 `# invariant I5` 形式）；再逐条触发反例（如 I1 无 verified 升 ready、I5 二次消费 preview、I6 private attachment 进 payload）。
  - 期望：9 条都能找到落点代码 AND 反例被拒；I6 的反例必须是**结构性**拒绝（不是靠自觉）。

### 2.3 离线边界是否被破坏

- [ ] **X-B4 `is_current` 的派生规则必须写进契约（防复发的唯一文档级护栏）**（P1，captain m01661）
  - 命令：`grep -n "is_current" docs/DATA-MODEL.md docs/API-CONTRACT.md | grep -iE "显式|推导|derive"`；再 `grep -n "禁止由.*end_date.*推导" docs/*.md`
  - 期望：`DATA-MODEL.md` 必须有一句明确规则：「**`is_current` 只能来自显式输入（用户勾选/导入草稿的 `entry.date_range` 反解），禁止由 `end_date` 是否存在推导**」。缺这句 → 规则迟早被"优化"回去。
  - 归属：缺文档句 → **planner**；实现按 `end_date` 反推 `is_current` → **coder**。

- [ ] **X-C1 上行外发唯一性**（同 CORE-10，**BLK-1**，D-07 已裁定）
  - **口径原文**：**上行（把用户数据发出去）唯一出口 = `server/app/adapters/llm_client.py`**；**下行（只下公开网页、不携带任何用户数据）= `server/app/adapters/fetch_client.py`**。禁止的是「非 llm_client 的上行外发」（遥测、CDN 回传、运行时安装、把用户字段塞进抓取请求），**不是**禁止下行抓取。
  - 命令：`grep -rnE "import (httpx|requests)|urllib\.request|urlopen" server/app/ --include=*.py | grep -vE "^server/app/adapters/(llm_client|egress_guard|fetch_client)\.py:"`
  - 期望：零命中；且 `fetch_client.py` 里只出现 `method="GET"`（无 POST/PUT/body 构造）。
- [ ] **X-C2 前端零外链 + CSP**（同 UI-01 上半）
  - 命令：`curl -sI $B/../ | grep -i content-security-policy`
  - 期望：`default-src 'self'`；`connect-src 'self'`；无 `unsafe-eval`。
- [ ] **X-C3 出网审计产物形状**
  - 命令：`head -1 data/logs/llm-egress.jsonl | $PY -m json.tool`
  - 期望：键 ⊆ `{ts,request_id,provider,host,path,model,field_names,payload_bytes,est_tokens,preview_id,ok,http_status,latency_ms}`，**无** `content/messages/body`。
- [ ] **X-C4 无运行时安装/遥测**
  - 命令：`grep -rnE "pip install|npm install|telemetry|sentry|analytics" server/app/ scripts/run.sh skill/ ; echo rc=$?`
  - 期望：零命中。
- [ ] **X-C5 白名单自动推导**
  - 命令：改 `LLM_BASE_URL=https://example.org/v1` 后重启，`curl -s $B/settings | grep allowed_hosts`；再手动尝试向 `api.deepseek.com` 发请求。
  - 期望：`allowed_hosts` 自动变为 `["example.org"]`；旧 host 请求 403 `EGRESS_BLOCKED`；无手写白名单变量（`grep -rn "ALLOWED_HOSTS" .env server/app/` 零命中）。
- [ ] **X-C6 下行纪律：`fetch_client` 只 GET 公开页、零用户字段**（**BLK-9**，见 ANL-05）
  - 命令：
    ```bash
    grep -nE "method|POST|data=|json=|params=|urlencode" server/app/adapters/fetch_client.py
    grep -rnE "name_zh|phone|email|school|resume|text_zh|package_id|variant" server/app/adapters/fetch_client.py ; echo "pii_rc=$?"
    # 运行时：把 fetch 指向本地抓包桩，抓全部请求行
    LLM_PROVIDER=ollama FETCH_DEBUG=1 $PY -m pytest tests/acceptance -q -k "fetch_client" -s
    ```
  - 期望：① 只构造 GET，无请求体；② 文件内零命中用户字段名（`pii_rc=1`）；③ 桩抓到的每条请求 URL 只含公司名/域名/招聘页路径，**query 里不出现**姓名、电话、邮箱、学校；④ 白名单外域名直接拒（不发请求）；⑤ 超时/失败降级为「仅用用户粘贴的 JD 文本」，不报致命错。

### 2.4 中文 PDF 字体

- [ ] **X-D1 字体链可注册**（AC-PDF-01）
  - 命令：`$PY - <<'PY'`
    ```python
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for idx, name in ((6, "STSongti-SC-Regular"), (1, "STSongti-SC-Bold")):
        pdfmetrics.registerFont(TTFont(name, "/System/Library/Fonts/Supplemental/Songti.ttc", subfontIndex=idx))
        print(name, "ok")
    ```
  - 期望：两行 `ok`，无 `TTFError`。

- [ ] **X-D2 全字符集逐字比对**（CMP-06 命令，**BLK-5**）
- [ ] **X-D3 康熙部首反例**（CMP-06 的 `kangxi_ok`）
- [ ] **X-D4 回退路径字体栈锁定**
  - 命令：`grep -nE "STHeiti|Arial Unicode" server/app/services/render_pdf.py server/app/services/fonts.py`
  - 期望：Chrome 回退命令/字体栈中出现 `STHeiti` 与/或 `Arial Unicode MS`，且**不出现** `Songti`/`Hiragino` 作为 Chrome 渲染字体。
- [ ] **X-D5 禁用引擎零调用**（CMP-12）

### 2.5 命名模板

- [ ] **X-E1 17 案参数化全绿**（CMP-13）
- [ ] **X-E2 解析来源优先级**
  - 命令：`naming_overrides_json={school:"X"}` 时 `validate` → `variables[].source`。
  - 期望：override 覆盖自动来源；空字符串视为未给（回退 `profile.school_zh`）。
- [ ] **X-E3 残缺文件名负例**
  - 命令：`find data/exports -type f | grep -E '(/|^)-|--|undefined|\.\.|^\.pdf' ; echo rc=$?`
  - 期望：零命中（**BLK-6**）。
- [ ] **X-E4 前端=后端同一解析结果**
  - 命令：对同一 build 同时调 `POST /naming/validate` 与导出，比较 `filename`。
  - 期望：两者逐字相等（含冲突后缀语义：validate 报 `resolved`，export 报实际 `filename`）。

### 2.6 隐私清单是否真的在调用前展示

- [ ] **X-F1 服务端强制（无 preview_id 不可发送）**（**BLK-4**）
  - 命令：`curl -s -X POST $B/llm/complete -H 'Content-Type: application/json' -d '{"purpose":"bullets_generate"}' -w '\n%{http_code}\n'`
  - 期望：428 `LLM_CONSENT_REQUIRED`；`grep -n "def send" server/app/adapters/llm_client.py` 的首参类型必须是 `ConsentGrant`（不是 `str`/`dict`）。
- [ ] **X-F2 一次性 + 过期 + 哈希**
  - 命令：同一 `preview_id` 连发两次 → 期望 409 `LLM_CONSENT_MISMATCH`；把 `expires_at` 改成 11 分钟前（`sqlite3 data/app.db "update llm_preview set expires_at='2026-10-23T00:00:00+08:00' where id='$pv'"`，**仅测试库**）→ 期望 410 `LLM_CONSENT_EXPIRED`。
- [ ] **X-F3 抓包 body ≡ preview.payload**
  - 命令：`$PY -m pytest tests/acceptance -q -k priv_04 -s`，要求测试内打印 `body_sha256` 与 `payload_sha256`。
  - 期望：两者相等；`payload` 的字符数 = `total_chars`；`fields[]` 覆盖 payload 中每个片段。
- [ ] **X-F4 清单结构完整**（AC-PRIV-04）
  - 命令：`curl -s -X POST $B/llm/preview ... | $PY -c "import json,sys;d=json.load(sys.stdin)['data'];req='preview_id provider model endpoint_host expires_at payload payload_sha256 total_chars est_tokens fields excluded redactions warnings'.split();print([k for k in req if k not in d])"`
  - 期望：`[]`；`fields[]` 每项含 `path/label/kind/source/chars/est_tokens/included/redacted`。
- [ ] **X-F5 UI 真的展示了清单**（**BLK-4**）
  - 命令：`tests/acceptance/test_ac_ui_03.py`（DOM 断言）+ 手工截图（含 `excluded.note` 与 `redactions` 可见）。
  - 期望：自动化断言 `preview_id` 未返回前「确认发送」按钮为 disabled；`excluded`/`redactions` 元素在初始视口内（不在 `<details>` 里）。
- [ ] **X-F6 未选中/原件不进 payload**（**BLK-2**）
  - 命令：
    ```bash
    sqlite3 data/app.db "select payload_json from llm_preview" | grep -cE "sample_resume|138-?0000-?0000|you@example\.com" ; echo "rc=$?"
    sqlite3 data/app.db "select count(*) from llm_preview where payload_json like '%未选中包标题%'"
    ```
  - 期望：`grep -c` = 0（有匹配时 grep 返回 1，注意看计数而不是 rc）；未选中包标题计数 0；`excluded.skipped[]` 里明确列了「resume_source_file / profile_pii」的 count。
- [ ] **X-F7 审计与日志**（CORE-11/12、AC-PRIV-09）
- [ ] **X-F8 照片字节永不进 payload**（captain 2026-10-23 新增，与 PII 同等级，**BLK-2**）
  - 命令：
    ```bash
    # 照片素材的真实字节指纹（任一命中即违规）
    SH=$(shasum -a 256 data/profile/photo_from_zh_resume.png | cut -d' ' -f1)
    sqlite3 data/app.db "select id from llm_preview where payload_json like '%photo%' or payload_json like '%image%' or payload_json like '%base64%'"
    sqlite3 data/app.db "select count(*) from llm_preview where payload_json like '%$SH%'"
    grep -rniE "photo|avatar|image" data/logs/*.jsonl | head ; echo "rc=$?"
    ```
  - 期望：三条查询全 0 命中；照片只以本机文件路径形式存在（`user_profile.photo_path` / `attachment`），`llm_payload.build()` 的来源白名单里**没有**照片来源；`X-F3` 的抓包 body 里同样搜不到照片哈希/`data:image`。

- [ ] **X-F9 上云边界：字段级白/黑名单断言**（captain 2026-10-23 用户当面拍板，**BLK-2**）
  - **口径（用户 2026-10-23 最终版，覆盖此前「学校名脱敏」的写法）**：发给 DeepSeek 可接受；**只抹姓名与联系方式**；其余（**含学校名**）以真实值发送。
  - **三档字段表**：**强制脱敏（用户不可关闭）** = 姓名 + 照片字节；**可选脱敏（用户自己的数据，`auto_redact=false` 时放行）** = 电话、邮箱；**必须真实发送** = 学校名、经历/项目文本、JD 文本、公司名与岗位名、用户备注。
  - **字段级判据表**（t11 逐行打勾，不要再按「一句话口径」自由解读）：

    | 字段 | 期望（payload / 抓包 body） | 判据方式 |
    |---|---|---|
    | 姓名 | **零命中**（恒脱敏，任何开关状态下） | `grep -c "张三"` → 0；且 payload 中有 `<NAME>` 类占位符 |
    | 电话 | `auto_redact=true` 零命中；`=false` 允许明文 | X-F10 / X-F11 两态各跑一次 |
    | 邮箱 | 同上 | 同上 |
    | 照片字节（png 的 sha256 / `data:image` / `base64`） | **零命中**（任何时刻、任何开关） | X-F8 三条查询 + X-F3 抓包 |
    | **学校名** | **≥1 命中且与 `user_profile.school` 逐字相等**（找不到反而不对） | `grep -c "示例大学"` → ≥1，再与 profile 值 diff |
    | 经历 / 项目文本 | ≥1 命中（防「空 payload 蒙混过关」） | 见下方 ④ |
    | JD 文本 | ≥1 命中 | 同上 |
    | 公司名 / 岗位名 | ≥1 命中（本次 build 绑定 JD 时） | 同上 |
  - 命令（四条都要跑，缺一条都可能「什么都不传」蒙混过关）：
    ```bash
    # ① 黑名单（学校名已移出黑名单）：姓名 / 电话 / 邮箱 / 照片痕迹
    sqlite3 data/app.db "select payload_json from llm_preview" > "$EV/payloads.jsonl"
    grep -cE "张三|138[- ]?0000|you@example\.com|base64|data:image" "$EV/payloads.jsonl"   # 期望 0
    # ② 学校名必须在（正向断言，反转旧口径：找不到才是缺陷）
    grep -c "示例大学" "$EV/payloads.jsonl"                                                  # 期望 ≥1
    sqlite3 data/app.db "select school from user_profile where id='me'"                      # 与上一行命中值逐字比对
    # ③ 白名单：fields[].source 只能来自合法来源（school 现在合法）
    sqlite3 data/app.db "select field_manifest_json from llm_preview" | grep -oE '"source":"[a-z_.]+"' | sort -u
    # ④ 正向（防「空 payload 也算隐私安全」的伪通过）
    $PY -c "import json;rows=[json.loads(l)['payload'] for l in open('$EV/payloads.jsonl')];print(min(len(r) for r in rows))"
    ```
  - 期望：① 计数 0（姓名/手机/邮箱/照片全无）；② 学校名 ≥1 命中且与 `user_profile.school` 逐字相等；③ `source ∈ {package_experience, package_project, jd_text, company_or_position, user_note, profile_school}`，出现 `profile.name`/`profile.phone`/`profile.email`/`photo*` 即 FAIL（`profile_school` 合法）；④ 每个 payload 非空，且能检索到 ≥1 条 bullet 与 JD 片段。
  - **反例（见到即 FAIL）**：把学校名也塞进占位符（过度脱敏，按旧规矩误杀正确实现）；或为了让 `grep 示例大学` 命中而把姓名一起明文带上。

- [ ] **X-F10 `auto_redact=true`：姓名必须脱敏，且不得比默认更松**（P0，**BLK-2**，captain 2026-10-23 实测反例）
  - 现状证据：`server/app/services/consent.py:282` 的 `auto_redact=True` 分支只返回 `["phone","email","id"]`，**漏 name** → 「打开自动脱敏反而让姓名明文上云」，必须能独立抓住（不能靠 X-F9 的汇总计数掩盖）。
  - 命令：同一 selections 跑两次 preview（`auto_redact` 缺省 / `true`），分别落 `$EV/xf10_default.json`、`$EV/xf10_on.json`，再按 X-F9 字段表逐字段比对。
  - 期望：① 姓名**零命中**且出现 `<NAME>` 占位符；② 学校名 **≥1 真实命中**（不得被一起脱敏）；③ `redactions[]` 覆盖 `name/phone/email`；④ **严格性**：`true` 的 payload 必须是默认 payload 的等集或子集（不得新增字段、不得把已脱敏项还原）；⑤ `fields[].redacted=true` 与占位符一一对应。
  - 归属：判 coder 主责（实现比默认更松），不判 planner（契约写的是「姓名恒脱敏」）。

- [ ] **X-F11 `auto_redact=false`：只放开电话/邮箱，姓名仍必须替换**（P0，**BLK-2**，captain 2026-10-23 边界）
  - 判据（写死，t11 不得判成「关掉开关即合规」）：电话/邮箱是用户自己的数据，关掉开关可明文；**姓名是硬线，任何开关状态都必须替换**；学校名两态都真实发送。
  - 命令：`-d '{"auto_redact":false,...}'` → `$EV/xf11_off.json`；断言：姓名零命中（否则 FAIL）；电话/邮箱命中**不判** FAIL 但要在证据里记录其明文；学校名 ≥1 真实命中；导出 PDF 提取文本仍回填真实姓名。
  - 反例（见到即 FAIL）：`if auto_redact: redact_all() else: redact_nothing()` 的二元写法。正确形态：`always_redact == {name, photo}` + `optional_redact == {phone, email}` + `never_redact ⊇ {school, experience, jd, company, position}`。

- [ ] **X-F12 校名必须真的进 payload（正向断言），且占位符方案已废**（P0，**BLK-2** 的反向 + `SENT-BUT-UNUSED` 的正向，2026-10-23 用户口径）
  - 为什么需要：X-F9/X-F10/X-F11 全是「**不得出现**」类断言，只能证明没发错，**不能证明该发的发了**。校名是竞争力判断的核心依据，漏发＝隐私成本已付、收益为零。
  - 命令：
    ```bash
    curl -s -X POST $B/llm/preview -H 'Content-Type: application/json' \
      -d '{"purpose":"jd_analyze","jd_id":"'$jid'","variant_ids":[]}' > "$EV/xf12.json"
    $PY - <<'PY'
    import json
    d = json.load(open("$EV/xf12.json"))["data"]
    s = json.dumps(d["payload"], ensure_ascii=False) if not isinstance(d["payload"], str) else d["payload"]
    school = "示例大学"
    print("school_hits:", s.count(school), "name:", s.count("张三"), "phone:", "13800000000" in s,
          "email_hit:", "sample_zh" in s.lower(), "placeholder:", s.count("[SCHOOL]") + s.count("<SCHOOL>"))
    assert s.count(school) >= 1, "校名未进 payload = 过度脱敏"
    assert s.count("张三") == 0 and "13800000000" not in s and "sample_zh" not in s.lower()
    assert s.count("[SCHOOL]") + s.count("<SCHOOL>") == 0, "占位符方案已废，出现即旧实现在跑"
    PY
    ```
  - 期望：① **校名命中 ≥1 且与 `user_profile.school` 逐字相等**（不得写成「某 985 院校」）；② 姓名/电话/邮箱/照片字节（`data:image`/base64/图片 sha256）**全 0**；③ `[SCHOOL]`/`<SCHOOL>` 计数 **0**（早前占位符方案已按用户 m00265 撤销，残留即回退）。
  - **已核事实（2026-10-23 03:2x）**：`server/app/repos.py:190 llm_brief()` 是**干净的白名单投影**——恰好 `school/degree/major/grad_year/city/available_date` 六项 + 可选 `school_tier`（只接受人工填写的枚举，`extra.get("school_tier")`），**没有** `name/phone/email/photo`；`consent.py:332-334` 对五个 purpose 都 `include_profile`，`consent.py:328-330` 注明「该段只允许七项，姓名/电话/邮箱/照片结构上不在内」。⇒ 本条现应 **PASS 的静态部分已具备**，但**仍需实跑 preview 拿 payload 证据**（静态白名单不等于运行时未泄漏：`_field()` 的 `messages[1].content` 位置、以及 extra 里是否混入其他键，都要以实际 payload 为准）。
  - 归属：校名 0 命中（过度脱敏）→ **coder**（`server/app/repos.py` `llm_brief()` / `services/consent.py` `REDACT_KINDS`）；占位符残留 → **coder**（未按 v1.10 口径改）；契约未列校名可发 → **planner**（D-19）。

- [ ] **X-F13 导入草稿的 header 身份字段永不进 payload**（P0，**BLK-2**，captain 2026-10-23 追加）
  - 为什么单列：导入草稿 `blocks[0]`（`block_type="header"`）**原样携带** `张三`、`178…`、`zhangsan@example.com`（2026-10-23 实测），这是**比 `llm_brief()` 白名单更靠前的一道门**——只要有人把整份 draft 序列化进 prompt，白名单就被绕过。`needs_llm_fallback=false` 时本轮不出网，但**一旦回退路径把 draft 贴进 messages，就是直接泄漏**。
  - 命令：
    ```bash
    # 1) 静态：导入链路不得引入任何网络/LLM 依赖
    grep -rnE "^(import|from) (requests|httpx|urllib|socket|http)" server/app/services/importer.py server/app/services/import_service.py; echo rc=$?
    # 2) 行为：把 draft 当输入，断言 payload 里这些值 0 命中
    curl -s $B/imports/$id/draft > "$EV/xf13_draft.json"
    $PY - <<'PY'
    import json, sqlite3, re
    d = json.load(open("$EV/xf13_draft.json"))["data"]["draft"]
    hdr = [b for b in d["blocks"] if b["block_type"] == "header"][0]
    raw = json.dumps(hdr, ensure_ascii=False)
    con = sqlite3.connect("data/app.db")
    prof = con.execute("select name_zh, phone, email from user_profile").fetchone()
    leaks = [v for v in prof if v and v in raw]          # 期望：header 里确实有真值（这是本地数据）
    print("header_carries_pii:", leaks)
    # 再取一份真实 LLM preview payload（llm_brief 路径）
    pv = json.loads(open("$EV/llm_preview.json", encoding="utf-8").read())["data"]
    body = json.dumps(pv, ensure_ascii=False)
    bad = [v for v in prof if v and v in body] + (["(cid:"] if "(cid:" in body else [])
    print("payload_leaks:", bad); assert not bad
    PY
    # 3) 回退路径：强制 needs_llm_fallback=true 后再 preview 一次，重复断言 2
    ```
  - 期望：① 静态 grep **零命中**（导入链路无网络 import）；② `header` 本地确有真值（证明这道门有东西可守），而 **任何 payload 中姓名/电话/邮箱/照片哈希 0 命中**；③ 回退路径下同上——**禁止**「整份 draft 序列化」作为回退输入，回退也只给 `llm_brief()` 七项 + 脱敏后文本；④ 若实现里存在 `json.dumps(draft)` 进 prompt 的路径 → 直接 FAIL。
  - 归属：任何 payload 出现 header 真值 → **coder**（`llm_client`/`prompts` 的入参没走白名单）；静态 grep 命中 → **coder**（导入链路引了网络库，违反 §5.1 上行唯一出口）；契约未写「draft 永不整体上云」→ **planner**。
  - **当前状态**：静态部分 **PASS**（2026-10-23 实测 `importer.py`/`import_service.py` 无 requests/httpx/urllib/socket），行为部分 **`BLOCKED(no-llm-path)`**——`/llm/preview` 端点所属 lane（t7）未交付，待 t7 后补跑 2/3。


> 复验统一命令：`grep -rn "<旧串>" docs/` 应零命中（或只剩变更记录里的说明）。
> **快照声明**：本表按 2026-10-23 02:46 的 docs 快照编写，行号可能因 planner 同步修订而漂移；planner 于 02:51 已改动 `ARCHITECTURE/API-CONTRACT/DATA-MODEL`。**终验时以「复验命令」列为准逐条重跑**，不认行号、认 grep 结果；已闭环的条目标 `resolved`，不要因为本表写过就当它还在。

| ID | 矛盾 | 位置 | 影响 | 归属 | 建议裁定 | 复验命令 |
|---|---|---|---|---|---|---|
| D-01 | `NAMING_MISSING_VARIABLE` vs 契约 `NAMING_MISSING_VAR` | ARCHITECTURE.md:220,226；API-CONTRACT.md:727 | 前端分支匹配不到 code | planner | 统一用 `NAMING_MISSING_VAR`（契约优先） | `grep -rn "NAMING_MISSING_VARIABLE" docs/` → 0 |
| D-02 | `NAMING_INVALID`(422) 不在错误码表 | ARCHITECTURE.md:350 | 出现表外码=契约破坏 | planner | 改为 `NAMING_SYNTAX`/`NAMING_EMPTY` 二者之一，或补进 §14 | `grep -rn "NAMING_INVALID\b" docs/` → 0 或 §14 有定义 |
| D-03 | 端口被占：**顺延** vs **启动失败不静默改端口** | ARCHITECTURE.md:342、API-CONTRACT.md:12 vs ACCEPTANCE.md:46 | 预检/起服务实现二选一都「违规」 | planner | **已裁定（captain 2026-10-23）**：默认 8765，被占用则**顺延到下一个空闲端口**，实际端口写 `data/runtime/app_port`；scripts/run.sh / DSH Skill / 启动横幅统一读它；ACCEPTANCE AC-ENV-06 改为「`app_port` 存在且其中端口实际在监听」。三份文档同时改口 | `grep -rn "启动失败\|不静默改端口" docs/` → 0；`grep -rn "app_port" docs/` 三份一致 |
| D-04 | preflight 路径：`server/app/preflight.py` vs `scripts/preflight.py` | ARCHITECTURE.md:109,134 vs ACCEPTANCE.md:43,155 | 验收命令可能跑不到文件 | planner | **已裁定（captain 2026-10-23）**：定为 `scripts/preflight.py`；`server/app/` 只放应用代码。ARCHITECTURE §3.1/§3.2 改口 | `grep -rn "app.preflight\|server/app/preflight" docs/` → 0；`ls scripts/preflight.py` 与文档一致 |
| D-05 | 必填槽位缺失：**中止+422 MISSING_SLOTS** vs **渲染占位+MISSING_SLOTS_RENDERED** | ARCHITECTURE.md:349、DATA-MODEL.md:184 vs API-CONTRACT.md:763、ACCEPTANCE.md:177 | assemble 该 200 还是 422 无定论 | planner | 分层：`required=1` 缺值 → assemble 200 + 占位 + `MISSING_SLOTS_RENDERED`；**export 前**阻断 422 `MISSING_SLOTS` | `grep -n "MISSING_SLOTS" docs/` 三处口径一致 |
| D-06 | 产物字段名 `text_check="failed"` vs `text_verified`(0/1/NULL) | ACCEPTANCE.md:159 vs API-CONTRACT.md:424、DATA-MODEL.md:368 | 验收无法按字段名核对 | planner | 统一 `text_verified` + `warnings_json[TEXT_LAYER_MISMATCH]`，改 ACCEPTANCE 一行 | `grep -rn "text_check" docs/` → 0 |
| D-07 | 任务卡 t7「含联网抓取，默认开启」vs 契约「**不做网页抓取**」+ 唯一出网模块 + 团队目标「唯一上云出口是 LLM API」 | 任务板 t7 vs API-CONTRACT.md:339、ARCHITECTURE.md:256-263 | 旧契约把出网写成单一出口，照旧契约实现=**误判 BLK-1** | planner（口径）| **已裁定反转（captain 2026-10-23）**：抓公司官网/招聘页是**用户立项时已明确授权**的需求，任务卡正确、文档错误。改为两个方向：上行（携带用户数据）唯一出口 `llm_client`；下行（只下公开网页、零用户数据）`fetch_client`。ARCH §5.1 / API §7 同步改口，`sources_json.type ∈ {jd,user_note,web}` | `grep -rn "不做网页抓取\|禁止.*抓取" docs/` → 0；`grep -rn "fetch_client" docs/` ≥3 份命中 |
| D-08 | ~~`.gitignore` 未落盘即存在 `.env` + 真实简历~~ | ~~仓库现状~~ | **已闭环（captain 2026-10-23 确认）** | coder（执行）+ supervisor（验收） | `.gitignore` 已落盘且 `git init` 在新文件之后（commit `8eb2130`，`.env`/`data/`/`*.pdf` 未入库）；判据转为**历史未污染** | `git log --all --stat \| grep -E "\.env$\|data/imports/"` → 0；`git ls-files \| grep -cE "^\.env$\|^data/"` → 0 |
| D-09 | ~~根目录 `scripts/set-api-key.command` 不在 §3.2 布局；脚本会打印 key **末四位**~~ | 仓库根 | **已闭环（captain 2026-10-23 改版并实测）**：脚本是 captain 产物的本地运维脚本；**不再回显末四位**，改为 **SHA-256 指纹前 8 位**（`printf '%s' "$KEY" \| shasum -a 256 \| cut -c1-8`，输出形如 `✓ 已写入 …/.env（35 字符，指纹 82be8a4d）`）。指纹不可逆、不可用于鉴权、不含 key 任何字符 | captain | 判据改为见 **INT-12**（禁止写「不得回显 key **任何**片段」，否则误杀该合法实现） | `grep -c '末尾四位' scripts/set-api-key.command` → 0；`grep -c '指纹' …` → ≥1 且 `shasum -a 256` 在脚本内；反向 `grep -nE '\$\{KEY: *-?[0-9]+\}\|tail -c ?4' …` → 0（勿用 `cut -c[0-9]+-`，会误命中 `cut -c1-8`） |
| D-10 | `/env` 示例 `warnings: ["OLLAMA_NOT_INSTALLED"]`（字符串）vs §14.1「warnings 一律对象」 | API-CONTRACT.md:105 vs :754 | 前端渲染分叉 | planner | 统一对象 `[{code,message,severity}]` | `sed -n '105p' docs/API-CONTRACT.md` 形态与 §14.1 一致 |
| D-11 | `slot_key` 正则 `^[a-z][a-z0-9_]{0,40}$` 不允许点号，但示例用 `candidate.name` | API-CONTRACT.md:277 vs :225,227 | 导入 draft 无法落库 | planner | 正则放宽为 `^[a-z][a-z0-9_.]{0,40}$`（或用下划线命名并改示例） | `grep -n "slot_key.*\^" docs/API-CONTRACT.md` 与示例一致 |
| D-12 | 重试策略只覆盖 429/5xx/超时，但实测 **1/12 请求在握手层失败**（`SSL: UNEXPECTED_EOF_WHILE_READING`，无状态码） | API-CONTRACT.md §10.4 vs captain 实测（m00070） | 连接级异常不重试 → 直接冒泡成「调用失败」，且易被误报为鉴权错误 | planner | §10.4 明确：`ConnectError/ReadError/RemoteProtocolError/ConnectTimeout` 计入可重试；`LLM_MAX_RETRIES=2` 上限（.env 已由 1 改为 2，1 次重试实测不够）；**禁止**把重试后失败映射为 `LLM_NOT_CONFIGURED`/401 | `grep -n "ConnectError\|RemoteProtocolError" docs/API-CONTRACT.md` 有命中 |
| D-13 | json_object 前置校验无对应错误码（上游 400 会被透传） | API-CONTRACT.md §14 无此码 vs CORE-20 | 用户看到英文 400，且错误文案三段式失守 | planner | **已落稿（captain 2026-10-23 裁定）**：§14 增 `LLM_JSON_MODE_PRECONDITION`(422, `details.reason="PROMPT_MISSING_JSON_LITERAL"`)，写明「本地拦截、0 出网」 | `grep -n "JSON_MODE_PRECONDITION" docs/API-CONTRACT.md` 有命中 |
| D-14 | `finish_reason='length'` 且 `content=''` 的判定无口径（是否算成功、落不落库） | API-CONTRACT.md §10.3 只写了 `LLM_JSON_UNPARSABLE` vs CORE-21 | 可能把空串当成功入库；截断与垃圾响应混判会误导排障 | planner | **已裁定（captain 2026-10-23，取代早前「复用」口径）**：截断独立成码 **`LLM_TRUNCATED`(502)**——触发 `finish_reason=="length"`（content 空或半截 JSON 都算），`details` 带 `finish_reason` + `completion_tokens`；`finish_reason=="stop"` 但 JSON 非法/缺字段 → `LLM_BAD_RESPONSE`；两者互斥。理由：reasoner `max_tokens=16` 实测 `finish_reason='length'`+`content=''`+`reasoning_tokens=16`，处置是「调高 max_tokens」，与「上游返回垃圾」不同，分开计数才能定位预算给低 | `for f in docs/API-CONTRACT.md docs/ACCEPTANCE.md docs/ARCHITECTURE.md; do printf "%s " "$f"; grep -c "LLM_TRUNCATED" "$f"; done` → **三份各 ≥1**；`grep -rn "LLM_TRUNCATED" server/app/` 在实现落地后 ≥1；**反向断言只针对组合**：`grep -rnE "LLM_BAD_RESPONSE[^\n]*empty_content\|empty_content[^\n]*LLM_BAD_RESPONSE" docs/ --exclude=docs/maintainers/REVIEW-CHECKLIST.md server/app/ --exclude-dir=__pycache__` → 0（**必须排除本清单**：CORE-21 标题与 D-14 本行提到两种码名，2026-10-23 实测不排除会自命中 2 处）；**不要**写 `grep LLM_TRUNCATED docs/ → 0`（契约里已有命中，断言 0 会永久红） |

| D-15 | 实现目录是 `server/app/**` + `web/` + `scripts/`，与 ARCHITECTURE §3.2 的 `app/` + `app/static` + `app/templates` + 根 `run.sh` 不一致；`adapters/` 尚无 `fetch_client.py` | `ls server/app`、`ls web`、`ls scripts` vs ARCHITECTURE.md §3.2 | 终验命令若照文档路径写会整片打空 → 假 FAIL，且责任会被误判给 coder | planner（布局口径）+ coder（确认命名） | 以实测为准回写 §3.2；本清单已按实测改路径并加 §0.1「路径口径」段。`fetch_client.py` 属 t4/analysis lane 待交付物 | `grep -rn "app/static\|app/templates" docs/ARCHITECTURE.md` → 0（**实测 2026-10-23 仍 1 处未改：`ARCHITECTURE.md:266`**，planner 待改）；`ls server/app/adapters/fetch_client.py` 存在 |
| D-16 | `data/runtime/app_port` **格式曾未定版**：D-03 只写「实际端口写 `data/runtime/app_port`」，实现写的是 JSON（`port/host/url/pid/started_at`） | D-03 裁定文本 vs `data/runtime/app_port` 实际内容（2026-10-23 实测） | scripts/run.sh、DSH Skill、启动横幅、INT-11 各自解析方式不同 → 读到不同端口或直接崩 | planner（已定版，captain 2026-10-23） | **已定版**：`app_port` = JSON 五字段 `{port:int,host:str,url:str,pid:int,started_at:ISO8601 带时区}`，**允许多键、不许少键**，写入原子（tmp + `os.replace`），**任何消费者禁止 `int(文件内容)` 纯文本解析**，且 `url` 必须 `endswith(":"+str(port))`；三处消费者统一 `json["port"]` | `python3 -c "import json;m=json.load(open('data/runtime/app_port'));assert {'port','host','url','pid','started_at'}<=set(m);print(m['port'])"` 成功且 == 实际监听端口；`grep -rn "app_port" server/ skill/ scripts/ \| grep -c "int("` → 0 |
| D-17 | **`consent.py:445` 的说明文案与最终口径冲突**：写「姓名**与学校名**以占位符传输」，而用户 m00265 定的是「学校名真实发送、只抹姓名与联系方式」 | `grep -n "学校名以占位符\|学校名.*占位符" server/app/services/consent.py`（2026-10-23 实测 1 处，`consent.py:445`；同段还有 `data/imports`、照片、手机号、邮箱永不发送的正确表述） | 用户在 ConsentModal 里看到的「将发送字段清单」会**误报**校名被脱敏，与他看到实际 payload 里真实校名矛盾 → 信任崩塌；也让 X-F9/X-F10 的判据与实现自述不一致 | **coder**（captain 2026-10-23 裁定，**优先级高于 t6/t7**；planner 只在契约同措辞时同步） | ① 文案改为「**姓名将脱敏为 `[NAME]`；电话与邮箱默认脱敏（可在设置里关闭）；学校名、学历、专业、经历与 JD 文本将按原文发送**」；② 若代码真把校名占位化（行为与自述两头错）→ 按 **X-F9** 判 FAIL 并一并修行为；③ 加断言：**反向** `grep -nE "学校名[^。\n]*占位符" server/app/services/consent.py` → 0；**正向 fallback** `grep -nE "学校名[^。\n]*真实发送\|学校名[^。\n]*原文发送" server/app/services/consent.py` → ≥1（只写反向会被「删掉整句」蒙混过关） | 反向 + 正向两条 grep 都过；ConsentModal 截图里「学校名」一行标为「真实发送」；`X-F9` ④ 校名 ≥1 真实命中 |

| D-18 | **用户 2026-10-23 裁决「技能整句原文、禁 tag 化」后暴露的契约缺口**：`UserProfile.skills_json[].line` / `[].tokens`、`trim_courses` 设置项、荣誉/奖项的 section 归属规则，**在 DATA-MODEL.md 与 API-CONTRACT.md 里都没有定义** | `grep -rn "skills_json\|trim_courses" docs/*.md server/ web/`（2026-10-23 实测 **0 命中**：三份 docs 与全部代码都没有该字段） | CMP-21..CMP-25 / IMP-14 六条判据没有契约依据，coder 会各自发明字段名（`skills` / `skill_lines` / `skills_json`），t11 只能比字符串 → 假红连环；matcher 的 `tokens` 索引若只活在实现里，降级语义（CMP-23）无法验收 | **planner**（契约补写；captain 已把用户裁决下发给 coder，但契约未落 ＝ coder 无依据） | ① DATA-MODEL.md 的 `user_profile` 增列：`skills_json` TEXT（JSON 数组，元素 `{line:str, tokens:[str]}`），**写明 `tokens` 仅 matcher 消费、永不渲染**；② API-CONTRACT.md 增 `trim_courses`（默认 `false`）到 settings 契约与 build 入参，并定义裁剪 warning `COURSES_TRIMMED` 的 `details.courses[]`；③ 写明荣誉/奖项若源于 `校园活动` 的 entry 则**不单列 section**（源简历本来独立时才允许），以及隐藏荣誉 bullet 后 entry 主体仍渲染 | `grep -c "skills_json" docs/DATA-MODEL.md` → ≥1；`grep -c "trim_courses" docs/API-CONTRACT.md` → ≥1；`grep -rn "tokens" docs/DATA-MODEL.md \| grep -c "永不渲染\|never render"` → ≥1；实现落地后 `grep -rn "skills_json" server/app/` → ≥1 且字段名与契约逐字一致（**先契约后实现**：契约不落，本行不放行，CMP-21..25 记 `BLOCKED(no-contract)` 而非 PASS） |

| D-19 | **校名进了 payload，却没有任何维度消费它（`SENT-BUT-UNUSED`）**：旧 `jd/analyze` schema 只有 `{title, company_name, requirements[], keywords[], summary}`；`company_profile` 只说「招聘偏好/文化信号」；`build_suggest` 无院校维度 → 隐私成本已付、分析收益为零 | 2026-10-23 03:17 实测：`prompts.py` 已 **120 行 / `school\|院校\|竞争` 18 命中**（captain 报的「0 命中 / 96 行」为旧快照）；契约侧已由 **API-CONTRACT §6.1 + ADR-20**（`competitiveness`）、**§7**（`school_preference`）、`UserProfile.school_tier` 补齐 | 用户明确「**校名是判定是否具有竞争力的核心判定依据之一**」；发而不用＝净损失；更危险的是 §7 在 JD 未提院校时**编造 `hard_filter=true`**，用户会据此错判能否投递 | planner（契约，**已落盘**）+ coder（实现消费 + prompt 接线） | 契约已落：§6.1 `competitiveness{school_tier,school_signal,degree_fit,major_fit,experience_fit,verdict,gap_notes[]}`、`requirements[].candidate_status`、§7 `school_preference{threshold,preferred_tiers,hard_filter,evidence,confidence}`、`UserProfile.school_tier`；实现验收按 **ANL-07（A 正例，7 条）/ ANL-08（B 反例，5 条 + 编造门槛区分）/ X-F12（校名正向 ≥1、占位符 0）** | `ls data/eval/jd_samples/{jd_school_filtered.md,jd_no_school.md,expectations.json}` 三件齐（实测存在，2026-10-23 03:17）；`grep -c competitiveness docs/API-CONTRACT.md` ≥1；ANL-07 跑 A 例 **7 条全 PASS**、ANL-08 跑 B 例 **5 条全 PASS**；**反向验收**：B 例 `evidence` 含 `985\|211\|双一流\|C9` 而 JD 原文命中 0 → 判「编造门槛」FAIL（归 coder）；**grep 冒烟不作判据**（`prompts.py` 已 18 命中，写「≥3」会永远绿） |

| D-20 | **上传返回 201 + 同步内联 draft，契约写 202 + `{job_id,import_id}` + 轮询** | 2026-10-23 03:30 实测 `POST /imports`（zh/en/md/txt 四次全部 201，body 带完整 draft）；`docs/API-CONTRACT.md §5.1` 与 `ACCEPTANCE AC-IMPORT-01` 均为 202 | 前端按契约写的轮询逻辑会拿不到 `job_id`；大文件（22MB 级）同步解析会顶到超时 | **已裁定（captain 2026-10-23）**：planner 改契约 + coder 实现 | 契约 §5.1/AC-IMPORT-01 改为「成功 = **201** + `{job_id, import_id, draft}`；`needs_llm_fallback=true` 时请求内不得发生 LLM 调用；`ImportJob` 只作历史/审计，前端不轮询」。**放弃 202/job 轮询**（本地解析 ~200ms，不值一个状态机） | `curl -s -o /dev/null -w '%{http_code}' -F "file=@data/imports/sample_zh.pdf" $B/imports` → `201`；且 `curl -s -F ... $B/imports \| $PY -c "import json,sys;d=json.load(sys.stdin)['data'];assert d['job_id'] and d['draft']['blocks']"` 通过 |
| D-21 | **warnings 的 `severity` 取值为 `"warning"`，不在契约枚举 `{info,warn}` 内** | 2026-10-23 实测 EN draft：`{code:CID_GLYPH_MISSING,count:16,severity:"warning"}`；`docs/API-CONTRACT.md §14.1` 写 `severity ∈ {info, warn}` | 前端按 severity 上色/分级时会落进未知分支（`warning` 既不是 `warn` 也不是 `info`） | **coder**（已认，t6 之后清理） | 统一改 `warn`；契约枚举保持 `{info,warn}` 不动 | `curl -s $B/imports/$id/draft \| $PY -c "import json,sys;print({w['severity'] for w in json.load(sys.stdin)['data']['warnings']})"` → 子集 ⊆ `{info,warn}` |
| D-22 | **`POST /imports/{id}/commit` 二次提交 409，`details` 只有 `{template_id}`，缺 `reason`** | 2026-10-23 实测：`details={'template_id': ...}`；契约 §5.3 要 `details.reason="IMPORT_ALREADY_COMMITTED"`；`grep -rn IMPORT_ALREADY_COMMITTED server/app/` **零命中** | 前端无法区分「已提交过」与「其他 409」（如包未就绪），只能按 message 猜文案 | **coder**（已认，t6 之后清理） | 409 分支补 `details={"reason":"IMPORT_ALREADY_COMMITTED","template_id":...}`；前端按 code 分支 | 连提两次 commit，第二次：`curl -s -X POST $B/imports/$id/commit \| $PY -c "import json,sys;print(json.load(sys.stdin)['error']['details']['reason'])"` → `IMPORT_ALREADY_COMMITTED` |
| D-23 | **照片在导入时自动 `applied=true` 并直接写入 `user_profile.photo_path`；`PHOTO_DETECTED` warning 完全没实现** | 2026-10-23 实测：draft `extracted_photo.applied=true`；导入后 `user_profile.photo_path="profile/photo_3493da….png"`；`grep -rn PHOTO_DETECTED server/app/` 零命中；`ACCEPTANCE AC-IMPORT-03` 明确「**不自动，必须用户确认**」、`warnings` 须含 `PHOTO_DETECTED` | **P0**：未经确认就改变了用户档案的照片（下一步导出就会用上）；且用户拿不到「检测到照片，是否用作证件照」的选择 | **coder** | ① `extracted_photo.applied=false`，仅返回候选；② 导入 draft 的 `warnings` 加 `PHOTO_DETECTED`（含 `width/height`）；③ `photo_path` 只由 `POST /profile/photo` 或用户确认后的 commit 分支写入 | 导入 en 样张后：`sqlite3 data/app.db "select photo_path from user_profile"` → 导入前值不变；`curl -s $B/imports/$id/draft \| grep -c PHOTO_DETECTED` → ≥1 |
| D-24 | **`data/exports/import_draft_*.json` 是旧版产物（比代码早 2 分钟），里面 `sections[].heading` 全 null、`quality.numbers_lost_unknown` 未改名** | 实测 mtime：exports **03:27:21**、`server/app/services/importer.py` **03:29:42**；实时 API 的 draft 里 heading 已填、`quality` 已是 `numbers_second_pass` | 复核者会对着**过期产物**判缺陷（captain 的 checker v1 就因此报 25 项假 hard_fail；本轮「双真值源」也被误判成 coder 新缺陷） | **captain/coder 流程**（不记单独 blame） | 任何导出产物必须与代码同版本重生：`touch` 或 `ls -l` 比对 `data/exports/*` 与 `server/app/**` mtime，产物旧于代码即判「产物不可用」，重跑生成 | `ls -lT data/exports/import_draft_zh_v10.json server/app/services/importer.py \| awk '{print $6,$7,$8,$9,$10}'` → 产物 mtime **≥** 代码 mtime |
| D-25 | **草稿契约缺字段定义**：`sections[]`/`section_kinds`/`entry_counts`/`skills`/`quality`/`source` 未在 API §5.1 出现；`section_kinds` 是 `bound_package_kind` 的**超集**（多出 `campus`、`skills`），且 commit 映射规则（`campus→activity`、`skill→null`）文档未写 | 2026-10-23 实测 draft 顶层键；`docs/API-CONTRACT.md §5.1` 示例只有 `blocks`；`server/app/services/import_service.py:36 "campus": "activity"`、`:38 "skill": None` | 两个真值源（`sections[]` 与 `blocks[]`）会继续漂移；调用方不知道 `campus`/`skills` 是否合法 kind | **planner**（补 §5.1 契约 + 规定单一真值源） + **coder**（把 `sections[]` 改为 blocks 派生 + 一致性断言） | planner 在 §5.1 写明「`blocks[]` 是唯一真值源，`sections[]` 为派生摘要（含 heading/entry_count）」，并列 `section_kinds` 合法值；coder 加 `assert sections[i].heading == 对应 block.heading` | `grep -c "sections\[\]" docs/API-CONTRACT.md` ≥1；`$PY -c "…"` 校验 `sections[i].heading` 与 blocks 一致（0 不一致） |
| D-26 | **`data/runtime/app_port` 陈旧文件：指向已死 pid 62604 与不可连的 8899，而真实服务在 8765/pid 46958** | captain 2026-10-23 实测复现：`lsof` 见 8765 在监听，文件写 8899；删文件重启后一致 | 用户按文件 URL 打开即白屏 | **coder**（启动覆盖 + 退出仅删自己的） | 启动时 pid 不存活或端口不可连 → 覆盖；退出仅当 `pid==self` 才删；见 **INT-16** | `lsof -nP -iTCP -sTCP:LISTEN \| grep -E ':(8765\|8899)'` 与 `cat data/runtime/app_port` 一致，且 `ps -p <pid>` 存活 |
| D-27 | **陈旧进程无法识别：改代码前起的 pid 仍在服务，Python 不热重载** | captain 2026-10-23：第一轮行为验证打在 pid 46958 上，得出 `job_id`/`PHOTO_DETECTED`/`width` 三项假 FAIL；换新进程全通过 | 会把正确实现判成缺陷（假 FAIL 的最大来源） | **判据方/流程方**（不是 coder）；字段缺失归 **coder** | `/health` 增 `build`（git short sha + dirty）；不一致即 `BLOCKED(stale-process)`；见 **INT-15** | `CUR=$(git rev-parse --short HEAD)$(git status --porcelain \| grep -q . && echo -dirty)` 与 `curl -s $B/health \| jq -r .data.build` 相等 |
| D-28 | **照片解码失败静默：`/FlateDecode` 裸像素 → `to_png()=None` → 跳过分支且无 warning，`extracted_photo.available=true` 却无 `attachment_id`** | captain 2026-10-23 合成件实测：`data` 头 `b'\xc8\xd2\xe1'`、120000B → PIL `UnidentifiedImageError`；真实 JPEG 样张正常 266×266；**03:41 复测**：`server/tests/fixtures/sample_with_photo.pdf` 已返回 `available=true` + `attachment_id=01a1652230b97d5b…` + `PHOTO_DETECTED`（回归夹具路径可用），**`/FlateDecode` 裸像素分支仍未验**，需专造一份裸流合成件 | UI 给出点不动的照片候选；Word/WPS 导出件会整类失效 | **coder**（`importer.py` 解码 + 不变量） | 支持 `/FlateDecode` 裸像素（按 `/Width/Height/ColorSpace` 重建）；失败发 `PHOTO_DECODE_FAILED`(warn)；`available ⇔ attachment_id`；见 **CMP-27** | `curl -s -F file=@server/tests/fixtures/sample_with_photo.pdf $B/imports` → `available=true` 且 `attachment_id` 非空且 `PHOTO_DETECTED ∈ warnings` |
| D-29 | ✅**已关闭**（2026-10-23 04:0x 复核：`API-CONTRACT.md:176-190` 已改为 200 + 六字段、204 描述已删；我按判据复跑临时库 POST→DELETE→restore 全 200） | **照片确认端点与契约不一致：实现是 `PUT /profile/photo {attachment_id}`，契约写 `POST /profile/photo/from-import {import_id, confirm:true}`** | 2026-10-23 03:41 实测：`PUT /profile/photo {"attachment_id":"…"}` → 200 且 `photo_path` 落库；契约 §3.2 该路径无定义（`grep -n "from-import" docs/API-CONTRACT.md` 有、实现零命中） | 前端按契约调 `POST /profile/photo/from-import` 会 404；按实现写又会与文档背离（CLI/验收脚本两套口径） | **已裁定（captain 2026-10-23）：以代码为准、改文档**（判据写死：`DELETE /profile/photo` 必须 **200** 且 body 含六字段，撤销= `PUT /profile/photo` 传 `previous_attachment_id`；planner 报的「204 无 body」属 §0.3.1 T-7 假证据）——planner 改 §3.2 为三动词分离（`POST` 上传 / `PUT` 确认 / `DELETE` 清除）；理由：理由：三动词语义更清楚；`from-import` 把「导入来源」与「确认动作」绑死，用户**手动上传**照片就没入口。planner 补文档，coder 不改实现 | `curl -s -X PUT $B/profile/photo -d '{"attachment_id":"<aid>"}' -H 'Content-Type: application/json' \| jq -r .ok` 与 `curl -s -X POST $B/profile/photo/from-import -d '{"import_id":"<iid>","confirm":true}'` 二者之一为 `true`，且与 `docs/API-CONTRACT.md` 的端点表一致 |
| D-30 | ✅**已关闭**（v1.15 登记，警告码 20→30：`awk` 实测 27 行 + 折算 3 = 30，未登记码脚本复跑 = 0；`IMAGE_DECODE_FAILED` 与 `PHOTO_DECODE_FAILED` 语义已分列，不得合并判） | **未登记 warning 码 `IMPORT_FALLBACK_LLM`** | 2026-10-23 03:41 实测 `POST /imports`（`sample_with_photo.pdf`，chars=122）返回 `warnings:[{code:IMPORT_FALLBACK_LLM,severity:warn},{code:PHOTO_DETECTED,severity:warn}]`；`docs/API-CONTRACT.md §14.1` 的码表**无此码**（`grep -rn IMPORT_FALLBACK_LLM docs/` 零命中） | 前端按 `code` 分支渲染会落进未知分支、提示文案无处生成；与 D-21 同族的「契约枚举漂移」 | **已裁定：planner 登记，不并入 `LOW_CONFIDENCE_BLOCKS`**；理由：两者层级不同：`LOW_CONFIDENCE_BLOCKS`=「**某些块**没把握」→ 局部校对；`IMPORT_FALLBACK_LLM`=「**整份稿子**动用了 AI 兜底」→ 必须整篇对照原件。文案不可合并（处置动作不同），且这是**隐私口径的用户可见面**——用户有权知道哪一版有 AI 参与。契约登记：`severity=warn`、语义「文本层过少/结构可疑，已启用 AI 兜底，请对照原件核对」、码表 16 行 → **17 行**（折算后 19 → 20）；前端文案走同一码 | `awk '/^## 14\.1/,/^## 15\./' docs/API-CONTRACT.md \| grep -c IMPORT_FALLBACK_LLM` ≥1，且 `curl -s -F file=@server/tests/fixtures/sample_with_photo.pdf $B/imports \| jq -r '.data.warnings[].code'` 全部 ∈ 契约码表 |
| D-31 | **`OUTPUT_TRUNCATED` / `LLM_EMPTY_CONTENT` 的 warning 缺 `severity` 与 `details`** | 2026-10-23 04:0x 实测：`server/app/adapters/llm_client.py:421` 发 `{"code":"OUTPUT_TRUNCATED","message":…}`（无 severity、无 details）；`:450` 同；而 `API-CONTRACT.md §14.1` 要求业务 `warnings` 一律 `{code,message,severity,…}`，且 v1.15 明确 `OUTPUT_TRUNCATED` 应 `severity="warn"` 并带 `details{finish_reason,completion_tokens,max_tokens}` | 前端无法按 severity 分级；CORE-28 的静态断言直接红 | **coder** | 两处补 `severity` 与 `details`（三字段），复跑 CORE-28 静态断言 | `python - <<'PY'` 断言该 endpoint 的 warning 含 `severity` 与 `details.finish_reason` |
| D-32 | **REV 39 条「代码有、文档无」**（planner 在 `API-CONTRACT.md:1130` 立此编号） | 历史：三方数字互不一致（planner 39/18、supervisor 20/46、captain 21/31）⇒ 指标未定义，曾统一记 `PENDING(canonical-script)` | **已结案（2026-10-23 04:4x）**：`scripts/check_route_parity.py` 定稿，退出码 0、7 条不变量全 true，`documented_total=111 / code_total=84 / matched=84 / only_in_code=0 / only_in_docs=27`（**2026-10-23 04:5x 现行**；旧的 43 已作废，见 §2.1.3 v7 台账） | 基线数字一律引该组；**旧值只作「变化原因」证据，不得再作断言**（§2.1.3 台账） | 归属：**planner**（改脚本口径）+ **coder**（实现推进）。 | `python3 scripts/check_route_parity.py` 退出码 0、7 条不变量 true、`only_in_docs=43`；与 §2.1.3 表逐档一致 |
| D-33 | **`§14.1` 自相矛盾**：正文新增了 `OUTPUT_TRUNCATED`（v1.15），但同一节末尾仍留着「**截断没有对应的 warning 码**：`OUTPUT_TRUNCATED` 已于 v1.6 删除」的旧注 | 2026-10-23 04:0x 阅读 `API-CONTRACT.md:1050-1060` 实测 | 读者按旧注实现 → 截断被判成错误（502），与 captain 三档裁定冲突 | **planner** | 删除/改写旧注，写明三档分工（空→502 empty_content；半截→502 partial_json；可解析→200 + OUTPUT_TRUNCATED） | `grep -n "已于 v1.6 删除" docs/API-CONTRACT.md` → 0 且 `grep -c OUTPUT_TRUNCATED` ≥2 |
| D-34 | **一格两条路由**（captain m01601 点名 `` `GET` \| `/jds` / `GET /jds/{id}` ``）——三方解析器分叉的直接原因之一 | 2026-10-23 04:3x 实跑基线 **0 命中**（planner 已在 `API-CONTRACT.md:1197` 立「一行一路由 / 方法单元格不得多方法合写」并改完表格）⇒ **已修复**，转为**常驻回归判据**（§2.1.2「路由表格格式纪律」） | 格式一旦回退，REV/FWD 立刻不可比，指标失效 | **planner**（改了没收口） | 回归时按 §2.1.2 片段复跑，命中必须 **0** | `python3` 片段见 §2.1.2 → `one_cell_two_routes = 0` |


| D-35 | **`is_current` 恒为 1，`end_date` 被静默清空**（`repos.py:686` 三目 `1 if isinstance(value, bool) ...` 把 `False` 也变 `1` → `create()` 认为至今在职并抹掉 `end_date`） | 实测：POST 带 `end_date=2024-06` → 响应与 DB 行均 `None/1`（`req_5984650051b74aea`）；真库 **18 行 18 行** `is_current=1` 且 `end_date IS NULL`；`PATCH` 正常（只有 create 路径受害） | **不报错、不告警、测试不红**，用户只在导出 PDF 时看到「每条经历都是至今」——静默改数据，比崩溃更难发现 补：captain 查明 18 行全是 `小象超市门店选址与订单量预测建模` 与其「（副本）」9+9、`source=authored`/`status=draft`/每行 3 变体/`build_selection=0` = **测试期反复 POST 的噪声**，处置改为**软归档（可 `--restore`）+ 归档前出 `data/exports/probe_rows_report.md` + 保留最早 1 行作回归夹具（标注「测试夹具」）**，不是用户真实条目 | **coder**（根因 + 往返测试 + 修复脚本）；修复脚本缺 dry-run/快照 → coder；护栏文案被删 → planner+coder | 根因已修（`repos.py:694 int(bool(value))`，04:5x 往返实测绿）；存量 18 行走 `scripts/repair_package_is_current.py`（默认 dry-run，来源限 `import_job.draft_json.entry.date_range`，反解不到不许猜） | `grep -rn "1 if isinstance(value, bool)" server/app/` → 0；PKG-08 往返绿；INT-17 dry-run 报 18 行 |
| D-36 | ✅**已消解**（captain 快照过期） | 活跃模板全部 `is_default=0`，导致 t8 首次 assemble 必 409（captain m01808 快照：6 个活跃模板全 0 默认） | 2026-10-23 04:0x supervisor 独立核查：`select is_default,count(*) from template where deleted_at is null group by 1` → **只有 `1\|1`**；`GET /api/v1/templates` 的 `resolved_default` **非 null**（`中文-单页-审`）；5 个同名「照片候选模板」已于 `04:01:29` 软删 ⇒ **captain 的 03:5x 快照已被清理动作消解** | 现无缺陷可修；保留 **CMP-28** 作常驻不变量（活跃模板恰 1 个默认；0 个 → 409 `NO_DEFAULT_TEMPLATE` 而非 500） | 不再派工；理由：缺陷记录保留作证据；**教训**：T-1「旧快照当现状」实例，报缺陷前必须现场重查 | `sqlite3 data/app.db "select is_default,count(*) from template where deleted_at is null group by 1"` → `1\|1` |
| D-37 | **`school_tier` 的「未识别」语义与 `preferred_tiers` 的「非硬门槛偏好」语义在契约里没写清**（captain m01877 点给 planner） | 未识别语义与偏好语义全靠实现者自行发明 | 要求 planner 在 `API-CONTRACT §6.1/§7` 与 `DATA-MODEL` 的 `school_tier` 说明中写死两条：① 未收录校名 → `"其他"` + `recognized:false` + warning，**不得**默认「普通本科」；② `preferred_tiers` 允许在 `hard_filter=false` 时非空（「优先但不设门槛」），且此时 `threshold` 必须以「不限」开头并含「偏好」 | planner | `grep -n '未识别\|recognized\|preferred_tiers' docs/API-CONTRACT.md docs/DATA-MODEL.md` 两处语义都在；ANL-09/ANL-10 可直接引用 | **✅ 已结案（2026-10-23 04:1x）**：`API-CONTRACT v1.18 §6.1` 四情形表 + `§7 preferred_tiers` 偏好表 + `DATA-MODEL v1.10 school_tier` 行已落；码表 37 错/40 警、未登记码 0；ANL-09/10 可直接引契约。
| D-38 | **`docs/DESIGN.md §12.4` 把 Chrome 临时页面的度量写成「真实体量实测」，读者会当成基线**（captain m01877） | 标题「真实体量实测（2026-10-23，Chrome headless 布局度量）」+ 表格数字无「估算」标记；实测对象是临时页面/精简样张，**不是最终 PDF** | 读者会把 Chrome 临时页面的数字当产品基线；叠加 uier 算错的分母，会把 **54mm** 的真实缺口误判成 **15mm**，进而做出「10pt 能塞进一页」的错误决策 | planner 改标题与表头为「**设计期估算**（Chrome 临时页面度量，非最终 PDF）」，并加一句「真实基线由 t8 首份 PDF 产生，届时以实测替换本表并标注命令+日期」 | planner | `grep -n '设计期估算' docs/DESIGN.md` ≥1，且 `grep -n '真实体量实测' docs/DESIGN.md` = 0。**追加（captain m01941）**：`§12.4` 那组 px 数字**必须删除或标注「已作废」**——它漏了「可用高度 = 页高 − 上 − 下」的减法，结论「10pt 可单页」不成立（真实缺口 ≈54mm）。宁可写「已作废，见 `ARCHITECTURE §7.5` 的原件密度参数」，也不要留一个算错的表；复验 `grep -n '已作废' docs/DESIGN.md` ≥1 且 `grep -nE '1178\.5\|1122\.5\|余 5\.6mm' docs/DESIGN.md` = 0 |
| D-39 | **captain 侧验收器 `data/eval/check_export_pdf.py` 的 `--right-margin` 默认 42.5pt 会把用户原件判红**（supervisor m01941 实测） | 直接 `--pdf data/imports/sample_zh.pdf --photo` → `overflow_count=63 / verdict FAIL`；原件真实右边距 **15.62pt**，填 `--right-margin 15.62` → `overflow_count=0 / verdict PASS`。默认值写死一个「常见 A4 边距」，遇到紧排原件必然假红 | 任何按默认参数引用该工具的人，都会把符合契约的紧排原件判成 FAIL（假红），并据此追错 coder；反过来也可能用它「证明」一个越界产物是 PASS | **captain（工具方）/supervisor（引用方）**：① 工具改为「不传 `--right-margin` 时从 PDF 内实测字块右边界推导」，或在检测到 `overflow_count>0 且 min(x1)` 与默认边距矛盾时**报「参数可疑」而不是 FAIL**；② 清单侧我已把「必须显式传实际右边距」写进 CMP-29 调用陷阱，任何引用该工具的地方都要带实际值 | captain | `$PY data/eval/check_export_pdf.py --pdf data/imports/sample_zh.pdf --photo` 在**不传**前提下达 `verdict=PASS`（或明确输出「参数可疑」），且 `--right-margin 15.62` 时仍 PASS |
| D-40 | **`docs/API-CONTRACT.md:1160` 的 `IMPORT_DRAFT_PRUNED` 行比同表多一列**（captain m01987 点出同类，supervisor 04:12 实测确认） | 该表 21 行 3 格（code / 出现处 / 含义），第 1160 行多出 `{count, pruned_ids[], max_keep, ttl_days}` 第 4 格；按列解析时其后所有行错位。注：captain 原报的 `DATA-MODEL.md:416` 粘连已被 planner 修复（04:12 复扫 0 命中） | 按列解析时其后所有行错位，FWD/REV 与字段比对会**连环错位且肉眼不可见**；同类形态还有「整表缺表头」与「空行后的续行块无表头」（planner 04:15 另报 `API-CONTRACT §14` 缺表头、`ARCHITECTURE §5.1` 4 行孤儿表，均已修） | **planner**：把第 4 格并入「含义」列（写成 `` `details{count, pruned_ids[], max_keep, ttl_days}` ``），或在表头补「details」列并把 21 行全部补齐——二选一，但**必须整表一致** | planner | `$PY` 跑 §2.1.4 脚本 → `mixed_nf_tables: 0` |
| D-41 | ✅**已修复（2026-10-23 04:17:29，04:18:24 复测 10/10 全绿）** 斜杠/并列形态曾丢层次：`仅限 985/211 院校` → `['985']`；`985 或 211 均可` → `hard_filter=false, []` | `server/app/services/jd_analysis.py` 门槛解析曾只取首个层次词（修复前 mtime 04:15:24 / 04:07:10） | 211 硕士被误判不达标（`211`→weak 而 `985`→strong） | **coder（已完成）** | 保留为回归判据，回退即重修 | ANL-11 十行用例 + 反向 `HARD_VERBS` 不含「优先」 + 并列集合包含 |
| D-42 | ✅**已修复（04:17:29，04:19:01 复测）** 门槛不匹配时 `gap_notes` 曾为空：`school_tier='其他'`/`211` + 门槛 985 → `verdict='weak'` 但 `gap_notes=[]` | `competitiveness()` 的 `gate_failed` 分支未写原因 | 用户只看到「弱」不知为何，申诉无门 | **coder（已完成）** | 回归判据：`gate_failed` 必写含层次的 note | ANL-12 三条断言（非空 / 含层次与门槛 / `unknown` 不得贬低） |
| D-43 | ✅**已修复（2026-10-23，planner v1.19）** `docs/ACCEPTANCE.md` 冻结说明写「AC-ANL-12 … 当前 KNOWN-FAIL」而条目行已写「已通过」；同文件两个结论 | 复验实测 `grep -n 'AC-ANL-12' docs/ACCEPTANCE.md \| grep -c 'KNOWN-FAIL'` → **0**（04:2x） | t11 对照时两处打架，无法判定以哪行为准 | **planner（已完成）**；并升级为通用规则 M6（见 §2.1.5） | 已按条目行修复，保留为回归判据 | `grep -n 'AC-ANL-12' docs/ACCEPTANCE.md | grep -c 'KNOWN-FAIL'` = 0 且条目行 `:268` 为「已通过，保留为回归判据」 |
| D-44 | ✅**已修复（planner v1.21）** 表头残留条目结论（M6 未彻底）：`ACCEPTANCE.md` v1.19 行含「`AC-ANL-12` … 已修复，保留为回归判据」，v1.18/v1.14 另有两行同类 | 复验 `grep -nE '^> 冻结' docs/ACCEPTANCE.md \| grep -cE 'AC-[A-Z]+-[0-9]+.*(已修复\|已通过\|KNOWN-FAIL)'` → **0**（04:5x，planner 一并清了 `:4/:5/:9`） | 表头与条目行可能给出不同口径，t11 对照会打架 | **planner（已完成）** | 保持上列 grep = 0；新增条目时表头只写编号 | 上列 grep = 0 且表头无结论词 |
| D-45 | **清理脚本把「留最新」当唯一规则，归档了有产出的来源行**（captain m02310） | 唯一活跃默认模板「中文-单页-审」来源行 `01a165188d92700783d126474f4875be` 于 04:22:27 被归档，`committed` 活跃数 **6 → 0**；不报错、不告警，只断溯源，而 IMP-17 级联删依赖该链 | **INT-21/22/23** + 契约 I14（planner 已落 `DATA-MODEL.md:559`、`API-CONTRACT` prune 段） | **captain（判据缺陷，不记 coder）**——三条件只写「留最新」，未写「产出优先」 | 归档前跑 INT-22 不交集 SQL；`committed` 活跃数 `BEFORE == AFTER`；同指纹组内归档 draft、保留 committed | `sqlite3 data/app.db "SELECT count(*) FROM import_job WHERE status='committed' AND deleted_at IS NOT NULL"` → 0 |
| D-46 | ✅**已修复（2026-10-23，coder commit 分支补写 static_text 与档案字段）** **commit 丢弃静态内容**：72 个 `template_block` 的 `static_text` 全空，`user_profile.{degree,major,grad_year,city}` 全 None、`skills_json=[]`；导出 PDF 只剩「示例大学」一行 + `SKILLS_EMPTY`（captain m02371） | 用户导入并 commit 后，GPA 3.56/4、86.53/100、CET4：562、CET6:508、7 门课程、3 行技能整句**全部消失**，且**不报错** | **IMP-18 / IMP-19 / CMP-31** | **coder**（`server/app/services/import_service.py` commit 分支） | 见 IMP-18/19 命令：`empty_static == 0`、五探针在 `template_block` 与 `draft_json` 双侧命中、四字段有值且有溯源 | `sqlite3 data/app.db "select count(*),sum(case when coalesce(static_text,'')='' then 1 else 0 end) from template_block"` → 第二列 0 |
| D-47 | ✅**已修复（coder 拆分 `--delete-drafts` + 快照回滚）** **破坏性脚本一次硬删 16 条 draft**：`prune_probe_data.py --delete` 挂在「硬删重复草稿」分支，超出批准的「软归档 2 行」（captain m02371） | 不可恢复地删掉 16 行导入草稿；执行者按命令跑、命令名未说明破坏性 | **INT-24 / INT-25** | **脚本设计（coder）**；「批准范围只有软归档」的**口径**归 captain | 脚本默认只做可恢复动作；`--delete*` 前打印「将删除 X 行（不可恢复）/ 将软删 Y 行（可恢复）」两类计数并留快照 md5；硬删拆到具名子命令 | 见 INT-24 判据；`grep -n '将删除\|将软删' scripts/*.py` ≥2 |
| D-48 | ⚠️**chrome 层已 PASS（2026-10-23 04:4x，captain 复验 `SAN ZHANG`/`B.M.`/`Available: Early July 2026`/`EDUCATION` 无 CJK）；正文层仍留判据（见 CMP-33/34/35/36 与 IMP-20）** **英文产物整篇未本地化**（不是漏翻一行）：`template` 唯一活跃模板 `lang='zh'`、`package_bullet_variant` **54 条全 `lang='zh'`**、库内**零英文变体**；实测 en 产物 CJK 片段 **12 段**（`到岗时间`/`年`/`月下旬`/`教育背景`/`项目经历`/`示例`/`小象超市…`/`全国大学生商业分析大赛`/`队长`/`把`/`条门店订单接入预测流程`/`试点门店备货周转提升`） | 英文简历里 section 标题、字段标签、卡片正文、姓名形态全是中文/中文式（`San Zhang` 而非 `SAN ZHANG`）；对外投递直接暴露机器拼接痕迹 | **判据 D-48 三层**（见下） | **coder**（i18n 未覆盖 chrome 与 profile 派生字段）+ **planner**（`LANG_FALLBACK` 契约） | ① **chrome 区 CJK = 0（P0）**：section 标题/字段标签（`到岗时间`→`Available`）/日期格式/姓名（`SAN ZHANG`）/`school_en`/学历专业——**这些是我们生成的文字，白名单为空**；② **正文允许中文机构/项目名（P1）**，但必须伴随 `LANG_FALLBACK{entry_count,bullet_count,sample}` + 导出页可见提示「以下条目沿用中文原文」；③ **反向防伪（P0）**：`LANG_FALLBACK` 存在 ⇔ 正文 CJK 字符数 > 0，**只成立一边 = FAIL** | 抽 en 产物：chrome 区（首 4 行 + section 标题行）CJK 断言为 0；正文 CJK>0 时 `LANG_FALLBACK` 必须在；`LANG_FALLBACK` 在而正文 CJK=0 同样 FAIL |
| D-49 | ✅**已闭环（planner v1.31–v1.32 拆行；captain 04:41 复核 48/48；supervisor 04:40:31 实测 行=码=去重=48、文件 mtime 04:40:14）** **`§14.1` 表头计数口径与表体不一致**（原行数 45 / 值数 48；定版：拆行、不改表头） | `docs/API-CONTRACT.md:1323` 是**一格四码**的合并行（`NAMING_SANITIZED` / `NAMING_TRUNCATED` / `NO_VARIABLE` / `NAMING_COLLISION_SUFFIXED`，第三列写「见 §9.4.1」），而 `:1275` 表头声明「一行一条码、无合并折算」⇒ 45 行实为 **48 个码**（44 行各 1 + 1 行 4）。**处置定性：这是「命令盲区」型缺陷，不是粗心**——按首列取码的正则每行只吐**首个**匹配，任何「一格多值」的表用它取数都会**静默少数**，两边都没数对正是这个原因 | **captain m02496 定版：拆 `:1323` 成 4 行、表头改回 48**，使「一行一条码」成为**机器可验的不变量**；保留合并行则只能靠人记得「45 行里有 1 行按 4 码算」，t11 跑机器不跑记忆 | t11 的机械计数判据（行数/码数/表头）三方不可能同时自洽，终验时必然红一条；且「一格多值」会让后续所有按列解析的比对**静默少数** | **planner** | **复验实测（supervisor，04:40:31）**：`行数=48 码数=48 去重=48 相等=True`，`:1277` 表头已为「共 48 条 / 一行一条码、无折算」，`:1325` 起四行独立 ⇒ 本条关闭。回归判据保留：① 行数 == 48；② `行数 == 去重码数`（**单元格 split 展开**取码，禁用首匹配式）；③ 表头 48 且口径「一行一条码、无折算」 |
| D-50 | `fetch_client.py` 自建 `httpx.Client` 却无 `finally` 关闭（**假报**） | `server/app/adapters/fetch_client.py:272-424`；构造 `:306-307`；关闭 `:422-424` | 无（代码本就正确；若以「已修复」入账会让 t11 缺陷账虚增一条） | **supervisor**（我只读构造行、没读函数尾部 → 立 T-13） | **❌ 不成立**：`owns_client = client is None`（`:306`）守卫正确，`finally: if owns_client: http.close()`（`:422-424`）覆盖异常路径；`llm_client.py:236/:528` 均为 `with httpx.Client(...)`，全仓无裸构造 | `sed -n '272,424p' server/app/adapters/fetch_client.py | tail -5` 应见 `finally:` + `http.close()`；`grep -rn 'httpx.Client(' server/app/ --include=*.py` 每条都在 `with` 或 `finally` 覆盖内 |
| D-51 | **`LANG_FALLBACK.details.entries` 是 6 个字符串，契约 v1.33 要求对象 `{entry_key,title,lines:[{text,chars}]}`；且缺 `meta.lang_fallback_lines`** | 实测 04:52:17 产物：`entries=['教育背景', …]`（str 列表）、无 `meta` 键；契约 `API-CONTRACT` v1.33 已定版对象结构 | t11 无法按条目定位回退行、两处计数（`meta.lang_fallback_lines` 与 `sum(len(lines))`）无法互校 | **待新产物验证（不记 coder）**——04:52 产物早于 v1.33 定稿 | ① `entries` 每条是 dict 且含 `entry_key`/`title`/`lines[]`；② `len(entries) == entry_count`；③ `meta.lang_fallback_lines == sum(len(e['lines']))` 两处口径一致 | 重导出后 `python3 -c "json…; assert all(isinstance(e,dict) …)"` + 两处计数相等 |
| D-52 | **契约已禁止的 `education_line` 仍在生成与消费（6 处）** | `API-CONTRACT.md §8.6.1`（v1.33）禁止该字段；`grep -rn education_line server/app --include=*.py` = 6（`compose.py:386` 生成、`:669` 消费；`render.py:196/283/320`、`export_service.py:403` 消费） | 页眉第二行出现 `本科 | 管理科学（商业数据分析） | 2028`（en 同病），与 CMP-40 判据二直接冲突 | 用户可见：简历页眉重复学历/专业/届别，占版面且与教育段重复 | **coder**：生成端与消费端一并清零；`grep == 0` 且 CMP-40 判据二为 0 命中 | `grep -rn education_line server/app --include=*.py` == 0；重导后页眉 3 行内无学历/专业词 |
| D-53 | **页面走查方法本身引入假象**（`--virtual-time-budget` + `--screenshot`） | captain m03206：虚拟时间会冻住/越过真实加载，据此得出「3 页正常 / 2 页空白」是错的；改用 CDP 真实等待后真相是「**7 页全死**」（CSP 拦掉内联启动脚本） | 判据工具自身制造假象，会把「全死」误报成「部分正常」，直接误导归因方向 | **captain**（方法）+ **supervisor**（引用了该结论而未复现） | 页面类判据只认「CDP + 真实等待 + `innerText` + CSP 违规数」，禁用 `--virtual-time-budget` 截图；见 T-15 | `scripts/check_pages_headless.py` 输出含 `innerText_len` 与 `csp_violations` 两列，且不得使用 `--virtual-time-budget` |
| D-54 | **`prune_builds.py --apply` 不可逆硬删构建**（指令与表结构冲突后静默降级） | captain m03422：指令是「只软归档」，但 `resume_build` **无归档列**（`pragma_table_info` = id/name/template_id/jd_id/company_profile_id/position/company/lang/status/naming_pattern/naming_overrides_json/field_values_json/sections_order_json/warnings_json/est_pages/created_at/updated_at，**无 `archived_at`**）⇒ 实际执行成**物理删除**：`resume_build` 43 → 12（删 31），连带 `build_artifact` 29 行、`build_selection` 79 行；两次 apply 前均有快照 `data/runtime/app.db.pre_prune_builds_20261023-075651`（2514944 B，07:56:51）。现状（08:0x 复算）：`resume_build 12 / build_artifact 22 / build_selection 46`，悬空行 0/0 | **已发生的不可逆删除**：31 构建行 + 29 产物行 + 79 选题行；处置合格**不改变**事实严重等级（T-12 两栏账：事实栏不因处置栏合格而降低） | **captain 为主**（下了一条物理上做不到的指令）+ **coder 半笔**（做不了时未回报，静默降级为硬删，且 `--ignore-name` 第二轮不在批准范围） | 新增归档语义见 **CMP-50**；快照保留，恢复一律走用户点头 | `pragma_table_info('resume_build')` 含 `archived_at`；`prune_builds.py` 默认不产生 `DELETE`（见 CMP-50 四条） |

> D-03/D-04/D-07 已由 captain 裁定（见「建议裁定」列中的**已裁定**字样），文档改口由 planner 执行；D-13/D-14 已落稿，D-12 待 planner 在 §10.4 补齐连接级可重试清单；**D-15（布局漂移）、D-16（`app_port` 格式）、D-17（consent 文案误报校名）、D-18（`skills_json`/`trim_courses` 契约缺口）、D-19（`SENT-BUT-UNUSED`：校名无人消费）、D-20..D-25（IMPORT lane 2026-10-23 03:30 实测：上传状态码 / severity 枚举 / commit 409 缺 reason / 照片自动 applied + 无 PHOTO_DETECTED / 产物 stale / 草稿契约缺字段）为 2026-10-23 实测或用户裁决新增**；**D-18 已于 2026-10-23 03:17 逐项实测解锁**（`DATA-MODEL.md:68/§1.1:80`、`ARCHITECTURE.md:514 §7.6`+`:545 ADR-19`、`ACCEPTANCE.md:199-202` AC-SKILL-01..04、`API-CONTRACT §14.1` `COURSES_TRIMMED`），`CMP-21..25` 回到可验状态（仅 CMP-22 反向基线段仍 `PENDING(no-artifact)`）；**D-08/D-09 已由 captain 关闭**。D-01/D-02/D-05/D-06/D-10/D-11 仍为未闭环项，终验前必须清零或标 `resolved`。

---

## 3. 追责规则

### 3.1 判定流程（五步，任何缺陷都走这条）

1. **复现**：用清单里的命令或最小脚本复现一次，记录命令 + 输出摘要（不许只说「我看到」）。
2. **定位首个偏离点**：从「契约/设计」→「实现」→「交互」→「验收执行」的顺序找**第一处**与规格不符的产出。
3. **归类产出**：文档/任务卡（planner/captain）· 后端（coder）· 前端（uier）· 检验（supervisor）。
4. **首次偏离原则定归属**：谁先把产出做成偏离规格的形态，谁主责；下游若无合理发现手段（例如契约未定义），不判下游。两方都偏离 → 记**主责 + 连带**，写成两条意见，不合并成一条模糊意见。
5. **出修改意见**：按 §3.4 模板，含最小修复与复验命令。**不接受的写法**：无证据、无复验命令、要求「重写整个模块」、顺手改到别的 lane。

### 3.2 归属判据表

| 归属 | 判据（命中任一条即归他） | 典型证据 | 反例（**不要**误判给他） |
|---|---|---|---|
| **planner** | ① `docs/` 内部两处口径冲突；② 验收条目无法被任何命令判定；③ 契约缺字段/缺错误码，导致前后端必须猜；④ 文档与实测环境矛盾（如声称某库可用但不可用）；⑤ 任务卡与规格冲突（任务卡归 captain，口径归 planner） | `grep` 出两处不同 code；AC 条目写「体验良好」 | 实现没按文档写（那是 coder）；文档写对了但测试没写（那是 coder） |
| **coder** | ① 端点/字段/状态码/错误码与 API-CONTRACT 不符；② 存在绕过 consent 或放宽 naming/gate 的代码路径；③ 日志/payload/DB 含正文或 PII；④ `[auto]` 条目无对应测试函数；⑤ 运行时 pip/npm 安装、引入禁用引擎；⑥ 把 `data/**` 或整包喂给出网请求；⑦ `fetch_client` 越界（非 GET / URL 或 body 带用户字段 / 白名单外 / 用户关闭后仍发，BLK-9）；⑧ 照片字节进 payload，或照片渲染位置尺寸不符（非右上角 89.3×89.3pt / 距顶 3.8pt） | 抓包 body 有指纹；`pytest -k ac_xxx` 收集到 0 项 | 前端用错字段（uier）；文档本身没定义（planner） |
| **uier** | ① 用 `innerHTML` 拼接用户可控文本；② 任何 CDN/外链/远程字体；③ Consent 的 `excluded`/`redactions` 折叠或可跳过；④ 硬编码身份/示例数据进 `server/app/`；⑤ 直出 `JSON.stringify(details)`；⑥ 使用契约里不存在的字段；⑦ 颜色是唯一信息载体、对比度 <4.5:1；⑧ 导出页「包含照片」开关默认关；无照片时空出照片位导致标题/正文错位 | `grep -rn innerHTML web/src`；DOM 断言失败 | 后端没返回该字段（coder）；契约没定义该字段（planner） |
| **supervisor** | ① 打勾项无证据或证据不可复现；② 未复核就 PASS、P0 漏检；③ 自行放宽/加严判定口径且未登记；④ 归属判错（把文档矛盾记成实现 bug）；⑤ 照抄 coder 自测结果当独立证据；⑥ 把「SHA-256 指纹」误判成 key 片段回显（见 INT-12 / 例 13） | 证据目录里没有该 AC 的产物；复跑命令输出与记录不符 | 缺陷在上游产出（planner/coder/uier）；规格本身没覆盖的**新**需求（captain 扩范围） |

> **captain 自产脚本**（`scripts/set-api-key.command` 等本地运维脚本）不在上表四角色判据内：脚本自身回显 key 片段 → 归 **captain**（BLK-3 级）；但 `server/app/` 或前端把 key 回显 → 仍判 coder/uier。**SHA-256 指纹（前 8 位）不算回显**。

> **假 FAIL 的归属（captain 2026-10-23 认可并推广；详见 §0.3.1）**：判据错要能追到**判据作者**。凡由「旧产物（T-1）/ 旧进程（T-2）/ 缺要素夹具（T-3）/ 未归一化坐标（T-6）」造成的 FAIL，一律归 **判据方（supervisor/验证者）或流程方（captain/产物生成方）**，不记实现方；反过来，实现方也不得拿「可能是判据问题」当挡箭牌——先按 T-1..T-6 逐项排除，排除不了才算实现缺陷。

### 3.3 判据示例（13 条，可直接照此写法给意见）

| # | 现象 | 证据 | 归属 | 理由 |
|---|---|---|---|---|
| 例 1 | `GET /settings` 返回 `key_last4:"BEEF"` | `curl -s $B/settings` | coder | 明确违反 AC-PRIV-06；planner 文档写得正确 |
| 例 2 | 参数化命名用例只跑了 12 条 | `pytest -k name_02 --collect-only \| tail -1` | coder | `[auto]` 条目要求 17 案；测试缺失 |
| 例 3 | 前端渲染 `data.key_last4`（后端已按契约返回 `key_set`） | `grep -n key_last4 web/src` | uier | 契约里无此字段 → 杜撰 |
| 例 4 | 文档一处 `NAMING_MISSING_VARIABLE`、一处 `NAMING_MISSING_VAR` | `grep -rn` | planner | 文档内部冲突（D-01） |
| 例 5 | `POST /llm/complete` 带 `{payload:{...}}` 也能发 | `curl` 428 断言失败 | coder | 结构性绕过 consent（BLK-4） |
| 例 6 | 清单条目 PASS 但 `tests/acceptance/test_ac_pdf_02.py` 不存在 | `ls tests/acceptance` | **supervisor** | 无证据放行，违反 §0.1 |
| 例 7 | 中文 PDF 提取 `"高"` 为 `U+2FBC` | CMP-06 命令 | coder | 未锁 Chrome 字体栈（KI-02）；文档已写清 |
| 例 8 | 导出 `-示例大学.pdf`（缺 `name_zh` 时只 warning） | CMP-15 命令 | coder | 契约明写 422；文档无歧义 |
| 例 9 | 契约 `warnings` 是字符串数组，前端按对象渲染崩 | X-F4 / X-A4 | planner | 契约自相矛盾（D-10）→ 前端无处可依 |
| 例 10 | `fetch_client` 把 `school=示例大学` 拼进抓取 URL query | 抓包请求行 / `grep -n "school" server/app/adapters/fetch_client.py` | **coder**（BLK-9） | D-07 已裁定「抓取合法、但下行零用户字段」；文档已写清 → 实现违规 |
| 例 11 | 导出 PDF 照片贴到左上角、或渲染成 120×120pt | CMP-20 的图片边界框断言 | **coder** | 已冻结右上角 89.3×89.3pt、距顶 3.8pt，无歧义 |
| 例 12 | `compileall` 全绿，但 `server/server.py` 启动即 `AttributeError: 'PosixPath' object has no attribute 'strip'`（`server/app/db.py:40`） | INT-11 子进程启动输出 | **coder** | 函数声明收 `str` 而实参是 `Path`；**编译通过不代表可运行**，静态检查不能替代启动断言 |
| 例 13 | 密钥脚本打印 `指纹 82be8a4d`，被误判成「回显 key 片段」 | `INT-12` ② + `shasum -a 256` 出处 | **supervisor**（误判） | 指纹不可逆、不可鉴权、不含 key 字符 → 不算回显；误杀合法实现属判据用错 |

> 例 6 是 supervisor 自检（无证据不得放行）；例 10 与旧版相反——**已授权的抓取需求不再算违规**，但「下行零用户字段」仍是硬线；例 11 说明尺寸/位置这类冻结数字必须逐字核对，不接受「大致右上角」。

### 3.4 修改意见模板

```
【缺陷单】RV-<YYYYMMDD>-<序号>
1. 问题（一句话，期望 vs 实际）：
2. 证据（命令 + 输出片段 + file:line + 证据文件路径）：
3. 归属（planner | coder | uier | supervisor）+ 命中的 §3.2 判据编号：
4. 影响（lane / AC ID / 是否 BLOCKER）：
5. 最小修复（最小改动 + 具体落点文件 + 建议改法）：
6. 复验命令（可整段粘贴，含期望输出）：
7. 截止与回退（何时未修则降级/换方案）：
```

**合格范例**

```
【缺陷单】RV-20261023-003
1. 问题：导出缺 {school} 时只产生 warning 并落盘 `数据分析实习生-张三-.pdf`，期望 422 且不落任何文件。
2. 证据：
   - 命令：`curl -s -X POST $B/builds/$bid/export -d '{"format":"pdf"}' -w '\n%{http_code}\n'`
   - 输出：HTTP 202，job succeeded，artifact.filename="数据分析实习生-张三-.pdf"
   - 证据：tests/.tmp/evidence/20261023/AC-NAME-04.log
3. 归属：coder（§3.2 coder ②「放宽 naming/gate」）
4. 影响：compose / AC-NAME-04 (P0) → BLK-6
5. 最小修复：`server/app/services/naming.py::resolve` 在 `valid=False` 时抛 `ApiError("NAMING_MISSING_VAR", 422, details={missing_vars,pattern})`；
   `server/app/api/exports.py` 在入 job 前先 `naming.validate()`，失败直接 422，不创建 artifact 记录、不落盘。
6. 复验命令：
   `$PY -m pytest tests/acceptance -q -k "name_03 or name_04"` → `2 passed`
   `find data/exports -name '*.pdf' | grep -E '^-|--|undefined'` → 零输出
7. 截止与回退：当日未修 → compose lane 整体 needs_revision，t11 不通过。
```

**不合格写法（会被打回）**：「命名模块有 bug，请优化一下」——无证据、无归属、无复验命令、无可执行修复。

### 3.5 升级与复裁

- **任务卡与规格冲突**（如 D-07）→ 立即上报 captain，抄送 planner 出书面裁定；**实现者不得自行选边**（选边即 coder 主责）。
- **文档之间冲突** → planner 24 h 内定稿并在 `API-CONTRACT.md` 变更记录加一行；未定稿则相关 AC 记 `BLOCKED-BY-DOC`，不算 lane 的失败，但**计入交付阻塞**。
- **归属有争议** → captain 裁定；supervisor 不得单方改判定口径，只能提交证据与判据条目。
- **口径变更** → 只能改 `ACCEPTANCE.md`（planner），且必须同步本清单对应行与复验命令。

### 3.6 supervisor 自身追责（写进来是为了可被追责）

- 同一 lane 出现 **2 次漏检**（终验通过后被 captain/coder 发现 P0 缺陷）→ 该 lane 复核作废，重跑 §4 最小可判集；第 3 次 → captain 换人复核。
- 任一条目打勾但 `$EV/` 里没有证据 → 该条目回退为 `FAIL`，并记 supervisor 缺陷一条（RV-…-S）。
- 归属判错（把 planner 文档矛盾记成 coder 实现 bug）→ 意见单作废重出，且在日报里更正。
- 本清单里出现**不可执行**的命令（跑不通/需要不存在的工具）→ 视为 supervisor 的清单缺陷，必须当日修。

---

## 4. 终验执行顺序（runbook）

**A. 前置闸（10 分钟，任一红即停）**
`CORE-09`（.gitignore/未污染 git）→ `BLK-1..10` 扫描（X-C1/C2/**C6**、CORE-11、X-F1/F6/**F8/F9**、CMP-06/13/**20**）→ `CORE-01/02/03`。

**B. 最小可判集（30 分钟，给出 PASS/FAIL 初判）**
0. **`INT-11` 启动硬门（t10 第一条）**：子进程起 `server/server.py` → 15s 内 `/api/v1/health` 200 → `app_port` **JSON 五字段**且三值相等（`INT-13`：实际监听 == `health.data.port` == `app_port.port`，用**非默认端口**跑）→ `terminate()` 后端口可立即 bind；再占 8765 验证顺延。**起不来或端口撒谎，后面全部无意义，直接 FAIL 并停。** 启动后立刻跑 **`INT-14`**（只读 GET 全 200 + 可 JSON 解析 + 无 `b'`）。
1. `INT-09` 全量 pytest（先看有没有失败，再看有没有缺用例）。
2. `CMP-06` 中文 PDF 字符断言 + `CMP-13` 命名 17 案 + `X-F3` 抓包哈希。
3. `X-B2` 数据模型列漂移 + `X-A2` 错误码覆盖。
4. `INT-02` E2E-01 端到端一次。
5. `CORE-19`/`CORE-20`/`CORE-21`/`CORE-23`/`CORE-24`/`CORE-25` LLM 加固六项（重试不误报、json 前置校验零出网零重试、截断与坏响应二分、非法 JSON 降级、身份自检拦截、关 AI 仍出 PDF）。
6. `CMP-20` 照片渲染四方（尺寸/位置/无照片不错位/中英两版）+ `X-F9` 字段级上云边界三条断言 + `X-C6` 下行零用户字段。

**C. 全量逐条（按 lane 顺序）**
core → import → package → analysis → compose → ui → skill → 集成；每条在 `ACCEPTANCE-RUN.md` 记行，证据存 `$EV/`。

**D. 结论模板**

```markdown
## 终验结论（<日期>）
- P0：__/__ PASS，FAIL 列表：…
- P1：__/__ PASS，KNOWN-FAIL：__ 项（≤2）
- BLOCKER：无 / 有（BLK-__）
- 未闭环文档缺陷：D-__（数量）
- lane 判定：core PASS / import PASS / … / skill PASS / 集成 PASS
- 总判定：PASS / FAIL
- 主责缺陷：RV-…（归属）
```

---

## 5. 缺陷台账模板（随终验一起交付）

| 缺陷 ID | 现象 | 归属 | 严重度 | 关联 AC | 最小修复 | 复验命令 | 状态 |
|---|---|---|---|---|---|---|---|
| RV-<date>-001 | | planner/coder/uier/supervisor | blocker/high/medium/low | | | | open/fixed/rejected |

> 台账里**每条 open 的 blocker 都必须在结论里出现**，不允许「已在沟通中」当作关闭。

### A.1 t16 退出条件一次性验收脚本（captain m03404 批准后跑一次出结论）

> 只读：不改库、不写文件、不出网。在 `resume-warehouse/` 下执行；退出码 0 = 六段全 PASS。
> **实跑记录（supervisor，2026-10-23 09:04:32，真实退出码 0）**：六段全 PASS。时点链：`scripts/recompute_jd_links.py` 09:01:25 → apply 报告 09:01:33 → dry-run 报告 09:01:38（均晚于脚本，INT-26 成立）；apply 快照 `data/runtime/app.db.pre_links_20261023-090133`。两份报告 `changed: 0` 且 `checked_against` 写明查过 `skills_json+packages+profile`，`command` 取自 `sys.argv`。
```text
[PASS] C1a — MANUAL=['AC-JD-05','AC-LOC-07','AC-PDF-20']（集合判等）
[PASS] C1b — NEGATIVE_EVIDENCE.md 覆盖 AC-UI-05/06/07/09 且含失败输出（11 行）
[INFO] C2a — jd_requirement.skill（pragma 存在=True）；matched=True；evidence=True
[PASS] C2b — matched 非空 1/6 条
[PASS] C2c — SQL/Python 条目引回 skills_json 且逐字可查
[PASS] C3 — Rust → missing/空；SQL/Python → 命中且 source=skills_json
[PASS] C4-neg1 谎报变化 — 按预期判红（before==after）
[PASS] C4-neg2 缺运行账 — 按预期判红（缺 command）
[PASS] C4 — apply/dry-run 最新两份：outbound_calls=0、运行账齐、before≠after、expected_but_unchanged 在、均晚于脚本
== 6 段 / PASS 6 / FAIL 0   退出码 0
```
> 历史记录（保留作证据）：2026-10-23 08:48:59 首次实跑退出码 1（C1b/C4 红），根因见 **T-19**（入册 fence ≠ 实跑脚本，含 `no such column: text`）。

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""t16 退出条件一次性验收（只读：不改库、不写文件、不出网）。

用法（在 resume-warehouse/ 下）：
    .venv/bin/python docs/accept_t16.py

退出码：0 = 六段全 PASS；1 = 至少一段 FAIL/ERROR。
设计纪律：每段独立 try/except，任一段异常只记该段 ERROR，**不中断其余段落**
（判据脚本中途崩 = 判据自身缺陷，见 X-A7/X-A10）。
"""
import glob
import json
import os
import sqlite3
import sys

ROOT = os.getcwd()
DB = os.path.join(ROOT, "data", "app.db")
ALLOWED_MANUAL = {"AC-LOC-07", "AC-PDF-20", "AC-JD-05"}
UI_IDS = ["AC-UI-05", "AC-UI-06", "AC-UI-07", "AC-UI-09"]
results = []


def ok(label, msg):
    results.append((label, True))
    print(f"[PASS] {label} — {msg}")


def bad(label, msg):
    results.append((label, False))
    print(f"[FAIL] {label} — {msg}")


def info(label, msg):
    print(f"[INFO] {label} — {msg}")


def cols(con, table):
    return [r[1] for r in con.execute(f"pragma table_info({table})")]


def con_ro():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def c1a():
    txt = open("tests/acceptance/AC_INDEX.md", encoding="utf-8").read()
    manual = sorted(set(__import__("re").findall(r"\|\s*`?(AC-[A-Z]+-\d+)`?\s*\|[^|]*\|\s*MANUAL\s*\|", txt)))
    if not manual:
        manual = sorted(set(__import__("re").findall(r"(AC-[A-Z]+-\d+)[^\n]*MANUAL", txt)))
    sub = set(manual) <= ALLOWED_MANUAL
    if sub and len(manual) == 3:
        ok("C1a", f"MANUAL={manual}（集合判等通过）")
    else:
        bad("C1a", f"MANUAL={manual}；越界={sorted(set(manual)-ALLOWED_MANUAL)}；数量={len(manual)}（要求 ⊆ {sorted(ALLOWED_MANUAL)} 且 == 3）")


def c1b():
    p = "tests/acceptance/NEGATIVE_EVIDENCE.md"
    if not os.path.exists(p):
        bad("C1b", f"{p} 不存在 ⇒ 四条 UI 用例「负向会红」无失败输出留证")
        return
    body = open(p, encoding="utf-8").read()
    missing = [i for i in UI_IDS if i not in body]
    lines = [l for l in body.splitlines() if l.strip() and not l.strip().startswith("#")]
    has_fail = any(("FAIL" in l) or ("AssertionError" in l) or ("失败" in l) for l in lines)
    if missing or not has_fail:
        bad("C1b", f"缺 {missing}；含失败记录={has_fail}（每条须含：命令 + 期望失败的断言 + 实际失败输出 ≥1 行原文）")
    else:
        ok("C1b", f"{p} 覆盖 {UI_IDS} 且含失败输出（{sum(1 for l in lines if 'FAIL' in l or 'AssertionError' in l)} 行）")


def jd_rows(con):
    rc = cols(con, "jd_requirement")
    info("C2a", f"用到 jd_requirement.{'skill'}（pragma 存在={'skill' in rc}）；"
                f"matched={'matched_package_ids_json' in rc}；evidence={'matched_evidence_json' in rc}")
    q = ("select id, skill, candidate_status, matched_package_ids_json, matched_evidence_json "
         "from jd_requirement order by rowid")
    return list(con.execute(q))


def c2b(rows):
    nonempty = []
    for rid, skill, st, mid, ev in rows:
        try:
            ids = json.loads(mid or "[]")
        except Exception:
            ids = []
        if ids:
            nonempty.append((rid, skill, len(ids)))
    if nonempty:
        ok("C2b", f"matched 非空 {len(nonempty)}/{len(rows)} 条：{nonempty[:3]}")
    else:
        bad("C2b", f"matched 非空 0/{len(rows)} 条 ⇒ 用户仍会看到「未体现」类结论")


def c2c(con, rows):
    skills = []
    try:
        raw = con.execute("select skills_json from user_profile limit 1").fetchone()
        skills = [str(x.get("line", "")) for x in json.loads(raw[0] or "[]")] if raw else []
    except Exception as e:
        bad("C2c", f"读 skills_json 失败：{e}")
        return
    hit, bad_ev = [], []
    for rid, skill, st, mid, ev in rows:
        if not (skill and ("SQL" in skill or "Python" in skill)):
            continue
        try:
            arr = json.loads(ev or "[]")
        except Exception:
            arr = []
        quoted = [a for a in arr if isinstance(a, dict) and a.get("source") == "skills_json" and a.get("quote")]
        good = [a for a in quoted if any(a["quote"] in line for line in skills)]
        if good:
            hit.append((rid, skill, good[0]["quote"][:24]))
        else:
            bad_ev.append((rid, skill, st, [a.get("quote", "")[:20] for a in quoted]))
    if hit and not bad_ev:
        ok("C2c", f"SQL/Python 条目引回 skills_json 且逐字可查：{hit}")
    else:
        bad("C2c", f"命中={hit}；引不回/缺 quote 的条目={bad_ev}")


def c3(rows):
    """C3 纯函数注入：证明「匹配逻辑不讨好」，零写库（captain m03474 裁定）。

    不依赖库里是否存在 Rust 条目——补假 JD 要写用户真库，会污染数据且出现在
    「已保存岗位」列表里。故改为直接喂本地函数，并带正向对照（防「永远返回空」）。
    """
    sys.path.insert(0, os.path.join(ROOT, "server"))
    from app.services.jd_analysis import link_requirements  # noqa: E402

    profile = {"skills": [{"line": "数据分析类：掌握Python、R、SQL等编程语言，可独立进行数据清洗、统计分析与可视化处理"}],
               "degree": "管理科学（商业数据分析） 本科", "major": "管理科学"}
    packages = [{"id": "pkg-a", "title": "赛车类游戏版本AB测试对照数据分析",
                 "summary": "用 SQL 与 Python 做版本 AB 测试的对照分析，输出显著性结论",
                 "tech_stack": ["SQL", "Python"], "bullets": ["负责 AB 测试实验设计与显著性检验"]}]

    neg = {"skill": "熟悉 Rust 后端开发", "candidate_status": "missing",
           "matched_package_ids": [], "matched_evidence": []}
    pos = {"skill": "熟练掌握 SQL、Python", "candidate_status": "missing",
           "matched_package_ids": [], "matched_evidence": []}
    link_requirements([neg, pos], packages, profile=profile)

    problems = []
    if neg.get("matched_package_ids") or neg.get("matched_evidence"):
        problems.append(f"Rust 被误命中：{neg.get('matched_package_ids')}/{neg.get('matched_evidence')}")
    if neg.get("candidate_status") != "missing":
        problems.append(f"Rust 状态被讨好式改写为 {neg.get('candidate_status')}")
    ev = pos.get("matched_evidence") or []
    if not ev:
        problems.append("正向对照未命中（可能函数永远返回空 ⇒ 本用例假绿）")
    elif not any(isinstance(e, dict) and e.get("source") == "skills_json" and e.get("quote")
                 for e in ev):
        problems.append(f"正向对照未引回 skills_json：{[e.get('source') for e in ev if isinstance(e, dict)]}")
    if problems:
        bad("C3", "；".join(problems))
    else:
        ok("C3", "Rust → missing/空（不讨好）；SQL/Python → 命中且 source=skills_json（正向对照成立）")


def _validate_report(rep, path, script_mtime, *, check_mtime=True):
    """单份报告的判据（captain m03510/m03525 定版）。返回 problems 列表。"""
    probs = []
    mode = rep.get("mode")
    if mode not in ("dry-run", "apply"):
        probs.append(f"mode={mode!r}（只允许 dry-run/apply）")
    if rep.get("outbound_calls") != 0:
        probs.append(f"outbound_calls={rep.get('outbound_calls')!r}（要求 0）")
    if "expected_but_unchanged" not in rep:
        probs.append("缺 expected_but_unchanged 键（缺键 = FAIL，不许当空数组）")
    if not str(rep.get("checked_against") or "").strip():
        probs.append("缺 checked_against（没写查过哪些源）")
    cmd = rep.get("command") or (rep.get("run") or {}).get("command")
    if not str(cmd or "").strip():
        probs.append("缺运行账 command（产生它的命令；缺运行账 = FAIL，不是格式问题）")
    if mode == "apply":
        snap = rep.get("snapshot") or {}
        if not (snap.get("path") and len(str(snap.get("md5") or "")) == 32):
            probs.append("apply 缺快照 path + md5(32 hex)")
    changed = []
    for jd in rep.get("jds") or []:
        for r in jd.get("requirements") or []:
            if r.get("changed") is True:
                changed.append(r)
    for r in changed:
        b, a = r.get("before"), r.get("after")
        if not isinstance(b, dict) or not isinstance(a, dict):
            probs.append(f"changed 行缺 before/after（{r.get('skill')!r}）")
        elif b == a:
            probs.append(f"changed 行 before==after（谎报变化：{r.get('skill')!r}）")
    if not changed and not rep.get("expected_but_unchanged") and not rep.get("checked_against"):
        probs.append("changed 为空且无 checked_against/expected_but_unchanged（无法证明「查过」）")
    if check_mtime and os.path.getmtime(path) < script_mtime:
        probs.append("报告早于 scripts/recompute_jd_links.py（INT-26）")
    return probs


def c4():
    """C4 重算报告：**每模式最新一份**判 INT-26；历史报告允许存在。

    反造假（T-20 同族）：changed 可为空（真实重算本来可能 0 变化），但必须给
    checked_against + expected_but_unchanged；每份必须带运行账（command + mode +
    apply 的快照 path/md5）。另跑两个负向自检：谎报变化、缺运行账 → 必须被判红。
    """
    script = "scripts/recompute_jd_links.py"
    if not os.path.exists(script):
        bad("C4", f"缺 {script}")
        return
    script_mtime = os.path.getmtime(script)
    latest, problems, seen = {}, [], []
    for p in sorted(glob.glob("data/exports/relink_report_*.json")):
        try:
            rep = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            problems.append(f"{os.path.basename(p)}: 不是合法 JSON（{e}）")
            continue
        mode = rep.get("mode")
        if mode not in latest or os.path.getmtime(p) > os.path.getmtime(latest[mode]):
            latest[mode] = p
    if set(latest) != {"dry-run", "apply"}:
        problems.append(f"模式不全：最新仅有 {sorted(latest)}，dry-run 与 apply 各要一份（历史文件允许保留）")
    for mode, p in sorted(latest.items()):
        rep = json.load(open(p, encoding="utf-8"))
        seen.append(f"{os.path.basename(p)}({mode}, changed={sum(1 for jd in rep.get('jds') or [] for r in jd.get('requirements') or [] if r.get('changed'))})")
        problems += [f"{os.path.basename(p)}: {x}" for x in _validate_report(rep, p, script_mtime)]

    # 负向自检 1：谎报变化（changed=true 但 before==after）必须红
    fake_changed = {"mode": "dry-run", "outbound_calls": 0, "checked_against": "skills_json",
                    "command": "python scripts/recompute_jd_links.py --report x --json",
                    "expected_but_unchanged": [],
                    "jds": [{"jd_id": "x", "requirements": [
                        {"id": "r", "skill": "s", "changed": True,
                         "before": {"status": "missing"}, "after": {"status": "missing"}}]}]}
    neg1 = _validate_report(fake_changed, __file__, script_mtime, check_mtime=False)
    # 负向自检 2：缺运行账必须红
    fake_norun = {"mode": "apply", "outbound_calls": 0, "checked_against": "skills_json",
                  "expected_but_unchanged": [], "jds": []}
    neg2 = _validate_report(fake_norun, __file__, script_mtime, check_mtime=False)
    for label, probs, want in (("C4-neg1 谎报变化", neg1, "before==after"),
                               ("C4-neg2 缺运行账", neg2, "运行账")):
        if any(want in x for x in probs):
            print(f"[PASS] {label} — 负向自检按预期判红：{probs[0]}")
        else:
            problems.append(f"{label} 自检失败：伪造样本未被判红（{probs}）")

    if problems:
        bad("C4", "；".join(problems[:6]) + (f"（共 {len(problems)} 项）" if len(problems) > 6 else ""))
    else:
        ok("C4", f"{seen}：outbound_calls=0、运行账齐、changed 行 before≠after、expected_but_unchanged 键在、两模式最新均晚于脚本")


def main():
    print(f"# accept_t16 @ {os.path.basename(ROOT)}  db={DB}  exists={os.path.exists(DB)}")
    for name, fn in (("C1a", c1a), ("C1b", c1b)):
        try:
            fn()
        except Exception as e:
            bad(name, f"ERROR {type(e).__name__}: {e}")
    try:
        con = con_ro()
        rows = jd_rows(con)
        for name, fn in (("C2b", lambda: c2b(rows)), ("C2c", lambda: c2c(con, rows)), ("C3", lambda: c3(rows))):
            try:
                fn()
            except Exception as e:
                bad(name, f"ERROR {type(e).__name__}: {e}")
    except Exception as e:
        bad("C2a", f"ERROR {type(e).__name__}: {e}")
    try:
        c4()
    except Exception as e:
        bad("C4", f"ERROR {type(e).__name__}: {e}")
    failed = [l for l, p in results if not p]
    print(f"\n== 汇总：{len(results)} 段，PASS {len(results)-len(failed)}，FAIL/ERROR {len(failed)} {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
```

**六段判据与脚本输出的对应**（C1a/C1b/C2b/C2c/C3/C4；C2a 为列名自检 INFO，不参与通过判定）：C1a = `MANUAL ⊆ {AC-LOC-07, AC-PDF-20, AC-JD-05} 且数量 == 3`（**判集合，不判数量**——只判数量时「把该留的换掉、数量仍是 3」会假绿）；C1b = 四条 UI 用例的负向证据（`tests/acceptance/NEGATIVE_EVIDENCE.md` 含 AC-UI-05/06/07/09 且含失败记录）；C2b/C2c = 持久 `jd_requirement` 非空 ≥1、`SQL|Python` 条目的 **`matched_evidence[].source == "skills_json"`**（证据来自哪）且带 `quote`——注意它与 **`candidate_status_source`**（谁下的判断，取值 `llm`/`local_override`/`manual`）是**两个正交维度**，不可混写；C3 = `Rust` 稳定 `missing`；C4 = 重算报告（**captain m03525 定版**）：**历史报告允许保留**（`data/exports/` 或归档目录），**只对「每个 mode 的最新一份」判 INT-26**（mtime ≥ `scripts/recompute_jd_links.py`）——若对每个文件都判，脚本每改一次全部历史报告都会变红，等于逼人删历史；① **按 mode 分组取最新一份**判 INT-26——历史报告允许留在 `data/exports/` 或归档目录，否则脚本每改一次所有历史都变红、逼人删历史；② `changed: []` **允许通过**，但必须同时给 `checked_against` + `expected_but_unchanged`（真实重算本来可能 0 变化，要求「必须有变化行」会逼人造报告）；③ **每份必须带运行账**：`command` + `mode` + apply 的 `snapshot{path, md5}`，缺运行账 = **FAIL**，不是格式问题；④ `outbound_calls == 0`；⑤ `changed == true` 的行必须 `before ≠ after`（相等 = 谎报变化）；⑥ 两条**反向自检必须真跑**：`changed=1` 但 `before==after` → 判红、无运行账 → 判红。

> **为什么加 ①③④**：T-16（把空转当收敛）、T-19（入册 fence ≠ 实跑脚本）、**T-20「判据要什么，就会有人造什么」**是同一族——captain 抓到 `relink_report_ebu_demo_*` 里有 `missing→partial`，而同期真实报告 `changed: 0`（该文件已移 `data/runtime/superseded_reports/`）。判据不改，下次就是「改到门满意为止」。
