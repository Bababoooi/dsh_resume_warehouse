# UX-FEEDBACK-PLAN — 交互契约与验收口径（v1.0）

> owner: planner ｜ 状态: 待 coder 落地 ｜ 观测时点 **2026-10-24T16:36:13+08:00**
> 配套：`docs/UI-REFRESH.md`（uier，视觉/选型/文案）+ `web/src/styles/uiverse.css`（只样式）。**两者在 16:40 仍被 uier 修改，本文件只引用其章节号与选择器名，不复制行数/行号。**
> 本文件只做三件事：**① 把「用户点了要等服务器」的动作穷举成表；② 每个动作钉死四态；③ 给出可测的验收口径**。不含视觉决策（归 uier）、不含实现代码（归 coder）。

---

## 0. 怎么用这份文档

| 角色 | 读哪几节 | 只读这一节的话 |
| --- | --- | --- |
| coder | §2 动作清单（别漏动作）→ §3 四态表（逐行照做）→ §4 轮询（长任务）→ §7 仲裁表（**先看，否则会和已落地的 feedback.js 打架**） | §7 仲裁表 |
| uier | §3 四态表（找 uier 未覆盖的动作）→ §7 差异登记 | §7 |
| 验收 / supervisor | §6 验收清单（28 条，AUTO 18 / MANUAL 10） | §6 |

**与其它文档的分工（不要重复写进别处）**

| 文档 | 回答什么 | 本文件如何对待 |
| --- | --- | --- |
| `docs/DESIGN.md` §7/§8/§10/§13/§14 | 组件视觉、Consent 弹层、JobToast 形态、文案三段式、无障碍基线 | 引用，不推翻；冲突见 §7 D5/D6 |
| `docs/UI-REFRESH.md`（uier） | 选型、CSS 钩子、DOM 契约、**逐动作四态文案** | **文案以它 §4 为唯一真源**，本文件只补它未覆盖的动作与跨页规则，编号 `U-W1/H4/B3…` |
| `docs/ACCEPTANCE.md` §10（351-359 行） | AC-UI-01..09 的既有条目 | 本文件 §6 新增 AC-UXF-01..28，必须回写该表（§6.3） |
| `docs/REVIEW-CHECKLIST.md` §1.6（1671 行起） | UI-01..UI-14 的 grep 判据 | 引用；**其中 UI-04/UI-14 的路径已漂移**（§7 D9） |

**观测时点与变动声明（重要）**：本文所有「现状/行号」结论取于 2026-10-24T16:36:13。同期仓库正在被我方协作改动（`git status`：`M api.js / boot.js / dom.js / components/index.js / layout.js / primitives.js / consent-modal.js`，`?? feedback.js / progress.js / toast.js / uiverse.css / docs/UI-REFRESH.md`），**7 个页面文件的 mtime 仍是 10-23**，即页面接线尚未发生。行号若与当前不符，以 `grep -n` 重测为准，不要照抄行号改代码。

---

## 1. 设施现状：可复用 / 待接线 / 待新增

### 1.1 已落地但页面还没用（coder 必须基于这些写，不要另起一套）

| 能力 | 位置 | 契约相关要点 |
| --- | --- | --- |
| `waitJob(jobId, opts)` 退避轮询 | `web/src/api.js:143-146` | `interval=900, maxInterval=4000, factor=1.4, timeout=300000, transientRetries=4, onTick, shouldStop`；超时**抛** `JOB_TIMEOUT`（:171-181）；`sleep` 用 `setTimeout`（:151） |
| `isJobDone(job)` | `web/src/api.js:119-121` | 终态含 `cancelled` |
| `createAction(p)` | `web/src/components/feedback.js:90-200` | `dataset:{phase}`、`.is-pending`、pending 防重入返回 `{ok:false,skipped:true}`、success hold 1200ms —— **与 uier 契约不符，见 §7 D1** |
| `feedbackRegion(p)` | `feedback.js:210-346` | 方法 `idle/pending/success/error/set`；error 自带三段式骨架；**DOM 形态不符 uier §3.1，见 §7 D2** |
| `isRetryable(err)` | `feedback.js:68-77` | 未识别码默认 `true`（这正是 §7 D8 会误报「可重试」的机制） |
| `inlineError` / `submitGuard` / `optimistic` / `elapsedText` | `feedback.js:352/376/401/415` | 可直接复用 |
| `toast*` / `announce` | `web/src/components/toast.js:216-262` | `MAX_VISIBLE=4`（:21）与 DESIGN §8「最多 3」冲突 → §7 D3 |
| `jobProgress` / `trackJob` / `resumeJob` / `peekJob` | `web/src/components/progress.js:123/246/293/317` | 记忆键 `rw-active-jobs`（:19），只存 `{jobId,kind,label,startedAt}`（:68-79），**不存用户内容** |
| `button({loading})` | `web/src/components/primitives.js:32-...` | 现成 spinner 能力，7 页一次没用过 |
| `progress()` / `skeleton()` / `emptyState({actions})` / `loadingText()` | `primitives.js:442/421/409/437` | `emptyState` 支持 actions，7 页零使用（痛点 5） |
| `errorView(err,{onAction})` | `web/src/components/errors.js:152-187` | 7 页零使用，只用 `errorText` |

### 1.2 页面层现状（5 个痛点的确证位置）

| 痛点 | 证据 |
| --- | --- |
| ① 导出只在结束时 toast，中间无进度 | `pages/builds.js:247` 发 `exportBuild` → `:248 waitJob` → 中途只有一条静态 callout「正在渲染 PDF…」（:244）；无 job 轮询 UI、无 `progress` |
| ② 提交期间不禁用，可重复点 | 完全无闸：`workbench.js` 的拆解按钮（`draft()`, `:32-45`）、`jobs.js:135 createJd`、`builds.js:184 assemble`、`settings.js:133 testProvider`；有闸但用 `disabled`：`workbench.js:61`、`templates.js:87`、`profile.js:139`、`settings.js:127/94`（`disabled` 而非 `aria-disabled`，会丢焦点，§7 D5） |
| ③ 无乐观更新、失败无回滚 | `warehouse.js:107` patch 后 `await load()` 整表重载，失败 `alert(errorText(err))`（:111）；`templates.js:50` 设为默认后全量重渲，失败 `alert`（:53）；`settings.js` 开关只改本地 flag，无脏标记 |
| ④ 顶栏状态无刷新 | `boot.js:254 probeStatus()` 仅启动调一次；`rw:status` 监听存在（:217-223）但 7 页零派发；改完 key 顶栏仍是「AI 未检查」 |
| ⑤ 空列表只有一句文字 | `warehouse.js:27`、`jobs.js:40`、`builds.js:119` 的 `emptyState` 均未传 `actions`；`templates.js` 空态同样 |

### 1.3 待新增（前端没有，后端有）

| 动作 | 后端已有 | 前端缺 |
| --- | --- | --- |
| 经历包归档 / 恢复 / 删除 | `PATCH /packages/{id}`（`status:"archived"`）、`POST /packages/{id}/restore`（`packages.py:150`）、`DELETE`（:142，204） | 无按钮、无 `api.restorePackage`；仅 `warehouse.js:129` 有「已归档」tab |
| 生成措辞变体 | `POST /packages/{id}/variants/generate`（`packages.py:259`，需 `preview_id`，202 job） | 无 UI、无 `api.generateVariants` |
| 照片上传 / 替换 / 移除 | `POST/PUT/DELETE /profile/photo`（`profile.py:71/100/130`；DELETE 返回 200 + `previous_attachment_id` 可撤销） | `profile.js:127 photoToggle` 只有一个 `statusDot`；完整四态设计只在死代码 `components/profile-form.js:photoField` |
| 拼装产物归档 | `PATCH /builds/{id}` `{"archived":true}`（`builds.py:111-112`，AC-BUILD-16） | 无 UI |
| 顶栏状态刷新 | `GET /llm/status` + `GET /env` | 无重探时机 |

> 注意：**packages 的「归档」是 `status="archived"`，builds 的「归档」是 `archived_at`**，两套机制不能混用（`repos.py:515-516` vs `builds.py:132-134`）。

---

## 2. 动作清单（33 条，"用户点了要等服务器"：A01–A32 + 回退动作 A16b）

列含义：**幂等** = 重复请求是否安全（决定能否乐观、能否重试）；**文案来源** = `U-*` 指 `docs/UI-REFRESH.md` §4 的现成文案，"本文" 指本文件 §3 新写。

### 2.1 工作台 `web/src/pages/workbench.js`

| # | 元素 | 触发 | 接口 | 预期反馈 | 幂等 | 文案来源 |
| --- | --- | --- | --- | --- | --- | --- |
| A01 | 「开始拆解」(`:151` actions) | click | `POST /packages/draft`（本地规则，零出网）(`:40`) | 结果区四态 + 保留上次草稿；**不得清空用户输入** | ✅ 只读式 | U-W1 |
| A02 | 「保存为经历」(`saveButton:56`) | click | `POST /packages` (`:63`) | 按钮 pending→success 1.2s；success 带「去经历库」次动作 | ❌ 非幂等（会建重复包）→ 必须 L1 同步闸 | U-W2 |

### 2.2 经历库 `web/src/pages/warehouse.js`

| # | 元素 | 触发 | 接口 | 预期反馈 | 幂等 | 文案来源 |
| --- | --- | --- | --- | --- | --- | --- |
| A03 | 首屏 / tabs / 搜索 | mount、tab click、Enter | `GET /packages` (`:24`) | 骨架 300ms 延迟；切 tab/搜索**保留旧列表** + `aria-busy` | ✅ | U-H1/H2/H3 |
| A04 | 「标记核实」(`verifyButton:99`) | click | `PATCH /packages/{id}/variants/{vid}` (`:107`) | **乐观**：立即 `.statusDot(ok)` + 行 `.is-optimistic`；失败回滚 + 行内错误 | ✅ 幂等 → 允许乐观 | U-H4 |
| A05 | 「归档」**新增** | click | `PATCH /packages/{id}` `{status:"archived"}` | 行淡出 + toast「已归档，可在「已归档」里恢复」+ 撤销 | ✅ | 本文 §3.3 |
| A06 | 「恢复」**新增** | click（archived tab 内） | `POST /packages/{id}/restore` | toast「已恢复到「可复用」」+ 从 archived 列表移除 | ✅ | 本文 |
| A07 | 「删除」**新增** | click → `role="alertdialog"` 二次确认 | `DELETE /packages/{id}` (204) | toast danger 常驻 +「撤销」8s（调 restore，软删可逆） | ⚠️ 软删 → 可撤销 | 本文 |

### 2.3 模板 `web/src/pages/templates.js`

| # | 元素 | 触发 | 接口 | 预期反馈 | 幂等 | 文案来源 |
| --- | --- | --- | --- | --- | --- | --- |
| A08 | 选择/拖入文件 (`.ui-file`) | change/drop | `POST /imports` (`:60`) | 「正在本机解析 {file.name}…」+ 不定量进度；扫描件走 warn + 「改用粘贴」 | ⚠️ 每次产生一条 import（重复=垃圾行）→ L1 | U-T1 |
| A09 | 「解析粘贴内容」(`:171`) | click | `POST /imports` (`:72`) | 空值→warn + `focus(#tpl-paste)`（现状静默 return） | ⚠️ 同上 | U-T2 |
| A10 | 「确认为模板」(`:82`) | click | `POST /imports/{id}/commit` (`:89`) | 成功后**才**清草稿；列表用骨架刷新；焦点移到语言 tabs | ❌ 非幂等 | U-T3 |
| A11 | 「设为默认」(`:35`) | click | `POST /templates/{id}/default` (`:50`) | **乐观**：默认点立即迁移；失败回滚 | ✅ | U-T4 |

### 2.4 招聘分析 `web/src/pages/jobs.js`

| # | 元素 | 触发 | 接口 | 预期反馈 | 幂等 | 文案来源 |
| --- | --- | --- | --- | --- | --- | --- |
| A12 | 首屏列表 | mount | `GET /jds` (`:35`) | 骨架 4 行 | ✅ | U-J7 |
| A13 | 列表项点击 | click | `GET /jds/{id}` (`:59`) | 详情区 `aria-busy` + 保留旧详情 | ✅ | U-J2 附 |
| A14 | 「保存并分析」(`:250`) | click | `POST /jds` (`:135`) | 按钮 pending → 自动接 A15/A16；空 JD → warn + `focus(#jd-text)` | ❌ 非幂等 | U-J1 |
| A15 | 本地分析 | 由 A14 或「本地分析」触发 | `POST /jds/{id}/analyze` `{method:"heuristic"}` (`:151`) → **202 job** | 详情区 pending + 进度条；**不逐次播报** | ⚠️ 每次一个新 job | U-J2 |
| A16 | AI 分析（consent） | click「AI 分析」 | `POST /llm/preview` (`:156`) → 弹层 → `POST /jds/{id}/analyze` `{method:"llm",preview_id,expected_payload_sha256}` (`:219`) → **202 job** | 预览表 → 弹层自动 pending → 状态区 pending；失败**弹层不关**，底部红条 + 动作 | ❌ consent 一次性消耗 | U-J3/J4/J5 |
| A16b | 「改用本地分析」（失败回退，`:222`） | click | `POST /jds/{id}/analyze` heuristic | **当前 bug：调了 analyzeJd 却不轮询，结果丢失** → 必须接回 A15 的轮询链 | ⚠️ | 本文 §3.5 |

### 2.5 拼装 `web/src/pages/builds.js`

| # | 元素 | 触发 | 接口 | 预期反馈 | 幂等 | 文案来源 |
| --- | --- | --- | --- | --- | --- | --- |
| A17 | 进入页三栏载入 | mount | `GET /templates`(`:59`)、`GET /jds`(`:84`，失败可静默)、`GET /packages`(`:96`)、`GET /env`(`:302`) | 各栏独立骨架；**packages 失败必须可见**（否则「经历库是空的」是假象） | ✅ | U-B1 附 |
| A18 | 命名输入 `#bd-position`/`#bd-company` | input | `GET /profile` + `POST /naming/validate` (`:128/:129`) | **300ms 防抖 + AbortController**；pending 保留上次结果 + `aria-busy`（不遮罩） | ✅ | U-B1 |
| A19 | 「组装预览」(`:342`) | click | `POST /builds`(`:173`，仅首次) → `PUT /builds/{id}/selections`(`:183`) → `POST /builds/{id}/assemble`(`:184`) | 按钮 pending + 预览区骨架；失败焦点回按钮 | ❌ createBuild 非幂等 | U-B2 |
| A20 | 「导出 PDF」(`:228`) | click | `POST /builds/{id}/export` (`:247`) → **202 job** → `waitJob` (`:248`) | 按钮 pending + 「正在渲染 PDF…」+ 进度条 + **可离开本页**；成功带文件名/体积/校验 | ⚠️ 每次新 job（overwrite 语义） | U-B3 |
| A21 | 字体探测 | mount / 「重新检测字体」 | `GET /env` (`:302`) | banner + 顶栏 `font` 状态 + 导出按钮 `disabled`（**unique 合法 disabled**） | ✅ | U-B4 |

### 2.6 经历库·变体（`warehouse.js` 承载，待新增）

| # | 元素 | 触发 | 接口 | 预期反馈 | 幂等 | 文案来源 |
| --- | --- | --- | --- | --- | --- | --- |
| A22 | 「生成 3 条新表述」**新增** | click → 字段清单弹层 | `POST /llm/preview` `purpose:"bullets_generate"` → `POST /packages/{id}/variants/generate` → **202 job** | 变体卡插到包内，标「未核实」；consent 语义同 A16 | ❌ | 本文 §3.7 |
| A23 | 「新增一条表述」/「删除变体」**新增** | click | `POST /packages/{id}/variants` / `DELETE …/variants/{vid}` | 行内四态（不整页重载） | ⚠️ 新建非幂等 | 本文 |

### 2.7 个人资料 `web/src/pages/profile.js`

| # | 元素 | 触发 | 接口 | 预期反馈 | 幂等 | 文案来源 |
| --- | --- | --- | --- | --- | --- | --- |
| A24 | 「保存」(`:135`) | click | `PUT /profile` (`:155`) | 顶部 success「已保存 / 文件名已同步更新」2.4s；失败聚焦首个 invalid | ✅ 幂等（PUT 全量 patch） | U-P2 |
| A25 | 「保存补充行」(`:85`) | click | `PUT /profile/education-facts` (`:93`) | 显示快照 path/md5（既有）+ 复制按钮 success 1.2s | ✅ | U-P3 |
| A26 | 上传 / 替换照片 **新增** | 拖放、回车、选文件；替换前 `alertdialog` | `POST /profile/photo`（上传）/ `PUT`（`{attachment_id}` 或 `{sha256}` 确认导入候选） | 上传中 `progress{value:null}`；成功「已更新 WxH」+「撤销」 | ❌ 上传非幂等；PUT 幂等 | 本文 §3.8 |
| A27 | 「移除照片」**新增** | click → `alertdialog` | `DELETE /profile/photo`（**200**，回 `previous_attachment_id`） | 「已移除」+「撤销」（用同 attachment_id 再 PUT） | ⚠️ 可逆 | 本文 |
| A28 | 「保存 key」(`:57`) | click | `POST /settings/api-key` (`:123`) | 空值→warn + `focus(#st-key)`（现状静默 return）；成功后**自动接 A29 并调用 `__rw.probeStatus()`**（见 A32） | ⚠️ 覆盖写 | U-S1 |
| A29 | 「测试连接」(`:59`) | click | `POST /settings/provider/test` (`:137`) | 5s 超时文案 + kv 结果；成功后调用 `__rw.probeStatus()` 让顶栏变 ok | ✅ | U-S2 |
| A30 | 「保存设置」(`:88`) | click | `PUT /settings` (`:94`) | success + 重载；失败清 pending 保留脏标记 | ✅ | U-S3 |
| A31 | 两个开关（自动脱敏 / 允许抓取） | change | 仅本地 flag，保存时随 A30 提交 | **乐观**：立即切换 + 「有未保存的改动」脏标记 | ✅ 本地 | U-S4 |
| A32 | 顶栏 AI / 字体状态 | 系统动作（无点击，`ai` 可点击跳设置） | `GET /llm/status` + `GET /env`（`boot.js:229-254`） | 现状：仅启动探一次 → **重探的单一入口＝boot 新增暴露 `window.__rw.probeStatus()`**；触发点：A21/A28/A29/A30 成功后、每次 `navigate()` 后（节流 5s） | ✅ | 本文 §3.8 |

**合计 33 条动作**（编号 A01–A32 共 32 条 + 回退动作 A16b）。其中后端已有、前端待新增按钮/方法的有 **7 条**（A05 A06 A07 A22 A23 A26 A27），改造现有交互的有 **26 条**。

---

## 3. 四态契约

### 3.1 全局规则（R1–R16，优先级高于任何单页实现）

| # | 规则 | 为什么（反面实例） |
| --- | --- | --- |
| R1 | 所有服务器动作必须有显式状态机；`callout` 静态替换**不算**四态 | 现状 7 页全是 `replaceChildren(callout(...))`，切态即丢焦点、重播报 |
| R2 | **pending 在第一个 `await` 之前同步置位**（L1 同步闸 `if (node.dataset.state==="pending") return;`） | `disabled` 要等事件派发后才生效，双击第二下仍会进 handler |
| R3 | 在途禁用用 `aria-disabled="true"` + `pointer-events:none`，**不用 `disabled`**（会丢焦点到 `<body>`）；`disabled` 只留给**结构性不可用**（缺中文字体、无默认模板的补充行） | uier §3.2 L2；`workbench:61` 等 5 处现状都是 `disabled` |
| R4 | **按钮 DOM 文案在途不变**（CSS 让文字透明 + 星标居中）；「文案变化」发生在反馈区与 sr-only 播报 | 改文案会让按钮宽度跳动（uier §3.8）；本文原拟「保存中…」方案按 uier 裁决作废 |
| R5 | 四态 DOM 只改 `data-state`，四个孩子预渲染，唯一播报通道是 `.sr-only[data-ux-live]`（uier §3.1 四条铁律） | 现 `feedbackRegion` 每次 `clear()` 重建，会双重播报并丢焦点 |
| R6 | **success 必须有凭证**：文件名 / 条数 / WxH / 快照 md5 / 「已保存 HH:mm:ss」；禁止只说「成功」 | 现状 `workbench.js:76`「已存进经历库」无标题无跳转 |
| R7 | **error 三段式固定**：发生了什么（`describeError().title` + body）→ 下一步（可执行动作/hint）→ 能否重试（`可以重试。`/`重试不会解决问题。`）；**error 常驻不自动消失** | `warehouse.js:111`、`templates.js:53` 用 `alert()`；`jobs.js:238` 直接把 `error_json` JSON 糊脸（AC-UI-09 违规） |
| R8 | 可重试与否只信 `isRetryable(err)`（`feedback.js:68`），页面不得自己写 if/else | 现状各页各写各的 |
| R9 | **consent 类动作永不自动重试/自动续跑**：`api.js:8` 明写「用户点一次=发一次」；`CONSENT_EXPIRED` 的动作是「重新生成字段清单」而不是重试 | 自动重试会把同一份脱敏 payload 再发一次，语义与审计都对不上 |
| R10 | 失败**不得清空用户输入**、不得把列表整块换成错误 | `workbench.draft()` 现状 `replaceChildren` 会清掉上次草稿 |
| R11 | 禁止 `alert()` / `confirm()`；破坏性动作（删除、替换照片、移除照片）用内联 `role="alertdialog"`；可逆的给「撤销」 | `profile-form.js:176-182` 已有合规样板可抄 |
| R12 | 每个反馈模块必须声明**成功提示位置**：页内动作 → 就近 `.ux-feedback`；跨页长任务 → toast/JobToast；列表项 → 行内 | 三条并存时必须选一条，否则同一事件播两遍 |
| R13 | **202 一到就进 pending**，不得等第一次轮询返回 | `builds.js:248` 现状是先插入静态 callout，与 job 状态无联动 |
| R14 | 不可取消就不画取消按钮（后端无 cancel 端点） | `progress.js:8-11` 已按此写；`jobrun.py:77` 的 `cancel_futures` 只用于进程退出 |
| R15 | 页面卸载**不取消**服务端任务，只 `trackJob.stop()`；回来后 `peekJob` 未终态才 `resumeJob` | 现状切页即丢（痛点 ①） |
| R16 | 文案禁词：原始 JSON、`ok:false`、端口号字面量、`[object Object]`、无中文说明的英文 code；技术细节只允许折叠成「技术细节：{code}」一行 | DESIGN §13；`jobs.js:238` 与 `builds.js` 已合规可对照 |

### 3.2 工作台（2 条）

| # | 动作 | idle | pending（视觉 / 按钮 / 重复点击） | success（位置 + 文案） | error（三段式 / 可重试） |
| --- | --- | --- | --- | --- | --- |
| A01 | 本地拆解 | 空态卡「开始拆解」可用 | 按钮 `data-state=pending` + 星标；结果区 `.ux-feedback[data-state=pending]`「正在本地拆解…／不会发送给任何模型。」；**不可重复点击**（L1）；**保留上次草稿** | 结果区 success：草稿卡（要点 N / 问题 M）；播报「拆解出 N 条要点」 | 「拆解失败」+ 为什么（`errorText`）+ 「再试一次」（ghost，重调 draft）；✅ 可重试 |
| A02 | 存进经历库 | 按钮可用 | 按钮 pending + 星标；草稿区 pending「正在存进经历库…」；**不可重复**（L1+L2，非幂等） | 按钮 success 1.2s → idle；反馈区「已存进经历库：{title}」+ 次动作「去经历库看看」；**草稿保留直到用户离开** | 「保存失败」+ 原因 + 「重试保存」；⚠️ 仅 `isRetryable` 为真时给重试（NETWORK/5xx），校验错只给「检查哪一项」 |

### 3.3 经历库（A03–A07，5 条）

| # | 动作 | idle | pending | success | error |
| --- | --- | --- | --- | --- | --- |
| A03 | 列表/筛选/搜索 | 列表（或空态 + 动作） | 骨架槽 `.ux-skel-slot`（300ms 延迟）+ 区域 `aria-busy=true`；切 tab/搜索**保留旧列表** + 细进度条，**不闪骨架** | 新列表；0 结果 → `emptyState`「没有匹配的经历」+ 动作「清空搜索」并 `focus(#wh-q)` | 「读不到经历库/搜索失败」+ 原因 + 「重试」；✅ |
| A04 | 标记核实 | ghost「标记核实」 | **乐观**：立刻 `.statusDot({level:"ok"})` + 行 `.is-optimistic` + `aria-busy`；可再点（幂等）但同帧只发一次 | 去掉 optimistic（**不整页重载**） | 回滚 optimistic + 行 `.ux-row[data-state=error]` 闪红 1200ms + 行内「核实失败：{msg}」+ 播报；✅ 可重试 |
| A05 | 归档 | 「归档」 | 按钮 pending + 星标；行降透明度；不可重复 | toast info「已归档，可在「已归档」里恢复」+ 行淡出 + 「撤销」 | 「归档失败」+ 原因 + 「重试」；✅ |
| A06 | 恢复 | archived tab 内「恢复」 | 按钮 pending；行 `aria-busy` | toast success「已恢复到「可复用」」+ 行移出 archived 列表 | 「恢复失败」+ 原因 + 「重试」；✅ |
| A07 | 删除 | 「删除」→ `alertdialog`「删除后 8 秒内可撤销；行与变体都还在本机。」 | 确认后按钮 pending「正在删除…」；不可重复 | toast danger **常驻**「已删除：{title}」+ 「撤销」按钮（8s 内可点，调 restore） | 「删除失败」+ 原因 + 「重试」；⚠️ 204 无 body，失败几乎只能是网络/权限 |

### 3.4 模板（A08–A11，4 条）

| # | 动作 | idle | pending | success | error |
| --- | --- | --- | --- | --- | --- |
| A08 | 文件解析 | `.ui-file` 虚线框「选择文件」 | `aria-busy` + 「正在本机解析 {name}…／全部在本机完成，不上传任何服务器。」+ 不定量进度；解析中**禁止再选文件** | 进校对区；播报「解析完成，请校对」；焦点移到校对区首个可编辑项 | 扫描件（`IMPORT_NO_TEXT_LAYER`）→ **warn**「这份 PDF 没有文字层」+ 动作「改用粘贴」（**不可重试**）；其他 → danger「解析失败」+ 「换一个文件」 |
| A09 | 粘贴解析 | 「解析粘贴内容」 | 星标 + 「正在解析粘贴内容…」；不可重复 | 校对区 | 空文本 → warn「先粘点内容进来」+ `focus(#tpl-paste)`（现状静默 return，必须改）；其他 danger + 重试 |
| A10 | 确认为模板 | 「确认为模板」 | 按钮 pending + 星标；「正在保存模板…」；不可重复（非幂等） | 「模板已保存」+ **成功后才清草稿** + 焦点移到语言 tabs + 列表骨架刷新 | 「确认失败」+ 原因 + 「重试」；**草稿绝不清空** |
| A11 | 设为默认 | ghost「设为默认」 | **乐观**：默认点立刻迁移 | 保持（原默认卡回按钮） | 回滚默认点 + inline danger「设为默认失败：{msg}」；✅ |

### 3.5 招聘分析（A12–A16b，6 条）

| # | 动作 | idle | pending | success | error |
| --- | --- | --- | --- | --- | --- |
| A12 | 列表首屏 | 骨架 4 行 | 骨架（`aria-hidden` + 区域 `aria-busy`） | JD 卡 + 状态点 | 「读不到岗位列表」+ 「重试」；✅ |
| A13 | 详情载入 | 空 / 上次详情 | 详情区 `aria-busy` + 细进度条，**不清空旧详情** | 详情渲染 | 「读不到这个岗位」+ 「重试」；✅ |
| A14 | 保存 JD | 「保存并分析」 | 按钮 pending + 星标；空 JD → warn + `focus(#jd-text)`（**不进 pending**） | 进分析流程（不单独 toast，避免两次播报） | 「保存失败」+ 原因 + 「重试」；⚠️ 重试可能产生重复 JD → 提示「上次可能已保存，先刷新列表」 |
| A15 | 本地分析 | 「本地分析」 | 详情区 pending「正在本地分析…」+ 不定量进度条；容器 `aria-busy`；**进度不逐次播报** | 详情刷新（需求/竞争力/院校信号）+ 顶部「分析完成」 | 「分析失败」+ `describeError` 三段 + 「重试」；✅ |
| A16 | AI 分析（含 consent） | 「AI 分析」→ 字段清单弹层 → 确认 | 弹层按钮 pending（`aria-disabled`，不可重复点）→ 关层后状态区「已发送，等待模型返回…／可以离开这一页」+ 进度条 | 同 A15 + 「本次上云字段：N 项，已脱敏 M 项」凭证 | **弹层不关**：底部红条 + 错误码 + 动作（`LLM_AUTH`→「打开设置」；超时/限流→「重试」；其余→「改用本地分析」）；⚠️ 仅 `isRetryable` 且 **需重新生成 preview** 才可重试（R9） |
| A16b | 改用本地分析 | 「改用本地分析」 | 立刻转 A15 pending | 同 A15 | 同 A15；**必须走 waitJob 轮询**（当前 `:222` 调了不轮询＝结果丢失） |

### 3.6 拼装（A17–A21，5 条）

| # | 动作 | idle | pending | success | error |
| --- | --- | --- | --- | --- | --- |
| A17 | 三栏载入 | 三栏骨架 | 每栏 `.ux-skel-slot` + `aria-busy` | 三栏内容 | 模板/经历库栏 → danger「读不到模板/经历库」+ 重试；**岗位栏失败可静默**（非必需，但须在左栏提示「岗位可稍后选」） |
| A18 | 命名校验 | 上次结果（info「文件名：X」） | `namingHost aria-busy` + 「校验中…」，**保留上次结果**（DESIGN §10）；300ms 防抖 + `AbortController` 丢弃过期响应 | 新结果（valid 绿 / invalid 红 + 「去个人资料」深链） | 「命名校验失败」+ 「重试」；✅ |
| A19 | 组装预览 | 「组装预览」 | 按钮 pending + 星标；预览区骨架 `--ux-skel-h:420px`；不可重复 | 预览 sections + `est_pages` + 「重新组装」ghost | 命名不全 → danger「先补全再组装」+ 去 profile 深链（不可重试）；其他 → 「组装失败」+ 重试；焦点回按钮 |
| A20 | 导出 PDF | 「导出 PDF」primary | 按钮 pending + 星标；状态区「正在渲染 PDF…」+ **不定量**进度条（后端只有 20/100 两个报告点，见 §4 P4）；「可以离开这一页，任务会继续」 | `.ux-toast-mark` + 「已导出：{filename}」+ 体积/`text_verified` 徽标 + 「下载」primary + 播报一次 | 「导出失败」+ `describeError` 三段 + 「技术细节：{code}」折叠 + 「重试」；**不弹 JSON**；1 retry 语义=`新 job` |
| A21 | 字体探测 | banner（既有）或静默 | （无需 pending，快请求）保留上次 | 顶栏 `font` 状态更新 | banner「没找到中文字体」+「重新检测字体」；导出按钮 `disabled`（结构性，R3 例外） |

### 3.7 变体（A22–A23，2 条）

| # | 动作 | idle | pending | success | error |
| --- | --- | --- | --- | --- | --- |
| A22 | 生成变体 | 「生成 3 条新表述」→ 字段清单弹层 | 弹层按钮 pending；关层后包内 pending 条「正在生成…」+ 进度条；**不可重复**（consent 一次性） | 变体卡插入包内，标「未核实」+ 计数「+3」；播报「已生成 3 条，均未核实」 | 弹层内红条（`LLM_NOT_CONFIGURED` → 「打开设置」；`CONSENT_EXPIRED` → 「重新生成字段清单」；其他 → 「改用本地分析/手写」）；⚠️ 不自动重试 |
| A23 | 增删变体 | 「新增一条表述」/ 行内「删除」 | 行内 `aria-busy` + 按钮 pending | 行内成功（新增行聚焦；删除行淡出）+ 不整页重载 | 「保存失败/删除失败」+ 行内重试；✅ |

### 3.8 个人资料 + 设置（A24–A32，9 条）

| # | 动作 | idle | pending | success | error |
| --- | --- | --- | --- | --- | --- |
| A24 | 保存资料 | 「保存」primary | 按钮 pending + 星标；表单 `.ux-busy[aria-busy]`；不可重复 | 顶部「已保存 HH:mm:ss／文件名已同步更新」2.4s + 元信息刷新 + 播报 | 「保存失败」+ 原因 + 焦点移到首个 `aria-invalid` 字段；⚠️ 校验错不可重试 |
| A25 | 保存补充行 | 「保存补充行」secondary sm（无模板时 `disabled`，结构性） | 星标 + 「正在写入教育段…」 | 「教育段已更新」+ 快照 path/md5 + 复制按钮 success 1.2s | 「写入失败」+ 原因 + 「重试」；✅ |
| A26 | 上传/替换照片 | 「上传照片」/「替换照片」（替换先 `alertdialog`：「替换会覆盖当前照片，原图不保留。」） | 拖放区 `aria-busy` + `progress{value:null}`「上传中」；不可重复 | 缩略图 + 「已更新 {W}×{H}」+「撤销」+ 说明「照片只存本地，不进入任何 LLM 请求」 | 「照片没能保存」+ 原因（超大/格式）+ 「换一张」；✅ 可重试 |
| A27 | 移除照片 | 「移除照片」→ `alertdialog` | 按钮 pending | 「已移除」+「撤销」（用 `previous_attachment_id` 再 PUT） | 「移除失败」+ 原因 + 「重试」；✅ |
| A28 | 保存 key | 「保存 key」 | 星标 + 「正在写入 .env（600）…」；不可重复 | 「key 已保存（设置 600，不回显）」+ 输入框清空 + **自动接 A29** + **调用 `__rw.probeStatus()`** | 空值 → warn「先把 key 粘进来」+ `focus(#st-key)`；其他 danger + 原因 + 「重试」 |
| A29 | 测试连接 | 「测试连接」 | 星标「正在测试连接（5 秒超时）…」+ 细进度条 | kv 面板（可达/HTTP/延迟/模型）+ **调用 `__rw.probeStatus()`** 让顶栏 `ai=ok` | 「连不上」+ `describeError` + 动作「检查 base_url」→ `focus(#st-base)`；`LLM_TIMEOUT` ✅ 可重试 |
| A30 | 保存设置 | 「保存设置」primary | 星标「正在写入设置…」+ 表单 `aria-busy` | 「设置已保存」+ 重载 + 调用 `__rw.probeStatus()`（脱敏开关会改变 AI 状态） | 「保存失败」+ 原因 + 「重试」；失败保留脏标记 |
| A31 | 两个开关 | 开/关 | **乐观**立即切换 + 旁注「有未保存的改动」（`.ux-pending__label`） | 随 A30 落盘后脏标记消失 | 不回滚（未落盘）；A30 失败时脏标记保留 |
| A32 | 顶栏状态 | `AI 未检查`/`字体未检查`（`idle`） | 重探中：**保留上次文案** + `title="正在检查…"` + 顶部细进度条（不得闪白） | `DeepSeek 已就绪` / `模型未配置` / `调用失败`；`ok/warn/bad` 三档 + 点击跳设置 | 探测失败 → `bad`「调用失败」+ 点击去设置；✅ 下次导航自动重探（`navigate()` 后节流 5s 调 `__rw.probeStatus()`） |

**四态表覆盖：7 个页面（workbench / warehouse / templates / jobs / builds / profile / settings）+ 1 个跨页系统动作（A32）。**

---

## 4. 轮询与长任务

适用：A15 / A16 / A20 / A22（后端 `jobrun.submit` → 202）。后端事实：`GET /jobs/{id}` 返回 `{id,kind,status,progress,message,result_json,error_json,created_at,finished_at}`（`server/app/api/jobs.py:17-28`）；`status ∈ queued|running|succeeded|failed|interrupted|cancelled`；进度报告点**稀疏**（`jobrun.py` 起手 5；`builds.py:386` 20「组装内容」、`:397` 100「导出完成」；`companies.py` 有 20/55；`packages.py` 30）——**没有平滑百分比可承诺**。

| # | 规则 | 取值 / 落点 |
| --- | --- | --- |
| P1 | 202 到手立刻 pending 并挂进度条 | `builds.js:247` 之后；`jobs.js:236` 之前 |
| P2 | 轮询一律走 `waitJob`，不自己写循环 | `api.js:143-146`；显式传 `timeout:300000`（导出）、`onTick`、`shouldStop` |
| P3 | 间隔退避 | 900ms → ×1.4 → 上限 4000ms（`api.js` 默认值是契约值，页面不要改） |
| P4 | 进度语义 | `progress` 有值且 `0<v<100` → 显示 `role="progressbar"` + `aria-valuenow`，**同时**始终显示 `job.message`（阶段文案）；`progress==null` 或 0/100 之间跳变 → 用 indeterminate 条 + 阶段文案；**禁止 JS 插值伪造平滑**（会掩盖真实阶段） |
| P5 | 超时 | `waitJob` 在 300s 抛 `JOB_TIMEOUT`（`api.js:171-181`）→ UI 必须三件事：「任务可能还在服务端跑」+「回本页重新导出」（**不是**「任务页」，见 §7 D7）+ 「重试」 |
| P6 | 轮询期间网络抖动 | `transientRetries=4` 内静默重试（不打扰用户）；耗尽后按 `NETWORK`/`HTTP_5XX` 走错误态 + 重试 |
| P7 | 失败 | `describeError(job.error_json)` 结构化渲染；**禁止** `JSON.stringify`（`jobs.js:238` 现状违规） |
| P8 | interrupted | 固定文案「服务重启导致任务中断，没有产生文件。」（errors.js `JOB_INTERRUPTED`）+ 「重新执行」；⚠️ 这是唯一允许「一键重跑」的失败（无副作用） |
| P9 | 切页恢复 | scope 命名：`builds:export:<buildId>`、`jobs:analyze:<jdId>`、`packages:generate:<packageId>`；mount 时 `peekJob(scope)` 未终态才 `resumeJob(scope,{alive})`；unmount 只 `trackJob.stop()`（R15） | `progress.js:246/293/317` |
| P10 | 恢复时的播报 | 回来只播报**一次**：「导出还在继续（已 12 秒）」，之后轮询不播报（uier §3.5 禁止逐次刷屏） |
| P11 | 并发 | 同一 scope 只允许一个在跑：新任务先 `forgetJob(scope)` 再 `trackJob`；不同 scope 并行（后端 `ThreadPoolExecutor(max_workers=2)`，同页最多 2 个长任务） |
| P12 | 结果落地 | succeeded 后**局部刷新**（列表 prepend/替换对应行），不整页 reload、不滚回顶部 |
| P13 | 页内可离开提示 | 长任务 pending 区必须有一行「可以离开这一页，任务会继续」；这是「切页恢复」能被用户信任的前提 |
| P14 | 结构化断言 | `grep -n setInterval web/src` 必须 0 命中（REVIEW-CHECKLIST UI-06 判据）；轮询只允许 `setTimeout` 递归（`api.js:151 sleep`） |

---

## 5. 可访问性与降级

| # | 要求 | 落点 / 现状 |
| --- | --- | --- |
| E1 | **播报矩阵以 uier §3.5 为准**：`.ux-feedback` polite 一行；字段错误 `role=alert`；JobToast failed = assertive（唯一例外）；进度数值不播报 | 本文件不重复定义，避免两套 |
| E2 | `aria-live` 容器必须**常驻且不整块替换**；`feedbackRegion` 现在 `clear()` 重建，违反此项 | `feedback.js:218-230` → §7 D2 |
| E3 | pending 同帧设 `aria-busy`，结束后移除；容器级（表单/卡片）也要挂 `.ux-busy` | uier §3.2 L3 |
| E4 | 焦点：在途留在触发按钮（R3 的原因）；成功后若节点替换，焦点移到流程稳定容器（tabs/列表首项）；反馈出现**不抢焦点** | `layout.js:230-249 drawer` 无 Esc、无 focus trap → 顺带修（DESIGN §14 有 `trapFocus` 可复用，`dom.js:182`） |
| E5 | 键盘：Enter 提交须判 `ev.isComposing===false`（中文选词回车不得提交）；Esc 只关最上层（toast → 弹层 → 无），**不得中断导出**；Tab 序排除骨架（`aria-hidden`） | uier §3.4 |
| E6 | `:focus-visible` 已存在（`base.css:181-182`）；新增控件必须落进 uier §11 的焦点环；**注意** uiverse 的焦点环只覆盖 `.ux-feedback :is(.ux-close,.ui-btn)`，页面级控件仍需自身 `:focus-visible` | `uiverse.css:593` |
| E7 | `prefers-reduced-motion`：星标停转但**保留文字**、按压不位移、toast 直接消失 | `base.css:257` 全局 + `uiverse.css:597-636` |
| E8 | 骨架块 `aria-hidden="true"` + 无 tabindex；`aria-busy="true"` 挂在**被加载的区域**，不是骨架本身 | uier §3.7 |
| E9 | 颜色不单独表意：pending 必有星标 + 文字，success 必有勾 + 「已…」，error 必有红 + 三段式 | 顶栏已合规（`layout.js:23` 注释） |
| E10 | 断网/后端挂了：`NETWORK`（`api.js:42`）→ 「连不上本地后端」+ 提示端口位置 + 「重试」；**页面不得白屏**（`boot.js:136-186` 的占位不要退化成空白） | AC-UI-01 现有手工项 |
| E11 | 无 key / 模型未配置：顶栏 `warn`「模型未配置」点击跳设置；页面上的 LLM 动作给 `LLM_NOT_CONFIGURED` + 「打开设置」深链（`errors.js` 的 `action:"settings"`） | `boot.js:229-254` |
| E12 | 降级不丢状态：reduced-motion 下所有 pending 仍必须有**文字**说明在做什么；纯动画表达状态一律不合规 | uier §3.6 |

---

## 6. 验收口径（28 条：AUTO 18 / MANUAL 10）

### 6.1 怎么跑

```bash
cd "/Users/zhong/Desktop/校外项目/DSH Project/resume-warehouse"

# 静态类（F01–F08）
pytest tests/test_web.py -q                    # 既有：路由模块/无外链/无 innerHTML
python tests/acceptance/make_index.py --check  # 账本自校验（新增 AC 后必须 0 未覆盖）

# 浏览器类（F09–F18）：复用既有 CDP harness
pytest tests/acceptance/test_ac_ui_browser.py -q -k "ac_ui or ac_uxf"
# 无 Chrome / 无 websocket-client 时会 skip（不判红），所以 CI 上要单独跑一轮并看 skip 数=0
```

harness 能力（`tests/acceptance/test_ac_ui_browser.py`）：真服务 + headless Chrome + `Page.addScriptToEvaluateOnNewDocument` 注入 fetch 桩（表项 `{match,status,body,method}`，URL 子串先匹配先赢），`_navigate(site, route, stubs, settle=1.6)` 返回 `#view.innerText`，`_eval(site, expr)` 取值。**当前桩唯一缺口是「命中计数」**：F13（连点只发一次）需要桩表项加 `hits`（或一个全局计数器）；其余判据都能用现有能力表达——F12 用「恒回 503」桩即可耗尽 `transientRetries`，F14 用 `_navigate` 重装同一张桩表即可（无需 `seq`/`delayMs`）。

### 6.2 清单

| ID | 级 | 通道 | 怎么点（前置 / 桩） | 看什么 | 算过 | 算不过 |
| --- | --- | --- | --- | --- | --- | --- |
| **F01** | P0 | AUTO/静态 | `grep -rn "alert(" web/src/pages/*.js` | 输出行数 | **0** | ≥1 行（warehouse:111、templates:53 必须先清掉） |
| **F02** | P0 | AUTO/静态 | `grep -n "styles/" web/index.html` | 样式表顺序 | `uiverse.css` 存在且**在 components.css 之后、print.css 之前** | 缺失，或顺序错（打印规则会被覆盖） |
| **F03** | P0 | AUTO/静态 | `grep -l "components/feedback.js" web/src/pages/*.js \| wc -l` | 命中页数 | **7** | ≤6（有页面还在用裸 callout） |
| **F04** | P0 | AUTO/静态 | `grep -rn "setInterval" web/src` ；`grep -c waitJob web/src/pages/*.js` | 行数 | `setInterval` **0**；至少 builds/jobs 两页用 `waitJob` | 出现 setInterval，或页面自己写轮询循环 |
| **F05** | P0 | AUTO/静态 | `grep -c "ux-feedback\|data-ux-live" web/src/components/feedback.js` | 命中数 | **≥2**（DOM 契约与 uier §3.1 同名） | 仍只有 `data-region="feedback"` 自创属性 |
| **F06** | P0 | AUTO/静态 | `python -c` 比对 `server/app/errors.py` 的 code 集合 vs `errors.js` keys vs `feedback.js` 两张码表 | 差集 | `IMPORT_NO_TEXT_LAYER` 出现在两处前端表里（文案 + NON_RETRYABLE） | 差集非空（扫描件 PDF 会出现「可重试」的错误文案） |
| **F07** | P0 | AUTO/静态 | `grep -rn "JSON.stringify" web/src/pages/*.js` | 命中行 | 仅允许 `jobs.js:207`（`<details>` 里的 payload 预览，DESIGN §7 允许） | 出现 `error_json`/`err` 的 stringify（AC-UI-09 回退） |
| **F08** | P1 | AUTO/静态 | `grep -rn "disabled = true" web/src/pages/*.js`（运行时赋值；不含渲染期属性） | 命中行数 | **0**；结构性禁用只允许作为渲染参数出现（`builds.js` 字体缺失、`profile.js` 无模板的补充行） | ≥1（仍在用在途运行时 `disabled`，会丢焦点） |
| **F09** | P0 | AUTO/浏览器 | stub `POST /builds/*/export`→202 `{job_id:"j1"}`；`GET /jobs/j1`→`running,progress:20,message:"组装内容"`；进 `#/builds` 点导出 | 导出按钮 + 状态区 | 按钮 `data-state="pending"`；`.ux-feedback[data-state="pending"]` 存在；`role="progressbar"` 存在；`#view` 含「组装内容」 | 按钮仍可用 / 无进度条 / 仍只有静态 callout |
| **F10** | P0 | AUTO/浏览器 | 同上，`GET /jobs/j1`→`succeeded` + `result_json.artifacts[0]={filename:"数据分析实习生-张三-某某大学.pdf",bytes:123456,text_verified:true}` | 成功区 | `#view` 含该文件名；`a[href*="/api/v1/artifacts/"]` 存在；`data-state="success"` 出现 | 无文件名 / 无下载链接 / 只有「成功」二字 |
| **F11** | P0 | AUTO/浏览器 | `GET /jobs/j1`→`failed`，`error_json={code:"EXPORT_FAILED",message:"…"}` | 错误区文案 | 含中文标题 + 「下一步」+ 「技术细节」；**不含** `"code":`、`"details"`、`ok:false` 原文 | 出现 JSON 原文（AC-UI-09 扩展判据） |
| **F12** | P0 | AUTO/浏览器 | `GET /jobs/j1`→503 ×5（耗尽 `transientRetries`） | 错误区 | 出现网络/5xx 类文案 + 「重试」按钮 | 静默挂死 / 白屏 / 只转圈不结束 |
| **F13** | P0 | AUTO/浏览器(需 `hits`) | 桩记录请求次数；`_eval` 连点导出按钮 3 次（同一 tick 内） | 桩计数 | `POST /export` 次数 **==1** | ≥2（L1 同步闸缺失） |
| **F14** | P1 | AUTO/浏览器 | 导出 running → `_navigate("#/warehouse")` → `_navigate("#/builds")`（同 session，桩表重装同内容） | 回页后状态 | 出现「正在渲染」+ 进度条 + 「可以离开这一页」 | 回页后按钮恢复 idle、任务状态丢失 |
| **F15** | P1 | AUTO/浏览器 | stub `GET /packages`→`{items:[]}`；依次进 `#/warehouse`、`#/jobs`、`#/builds`（三处空态） | 空态块 | 三处 `.empty-state` 内都有可点的 action（如 `a[href="#/workbench"]`） | 任一处只有一句文字（痛点 ⑤ 未修） |
| **F16** | P1 | AUTO/浏览器 | `#/settings`；stub `POST /settings/api-key`→200、`GET /llm/status`→`{ready:true}`；点保存 key，等 2s（或离开再导航回来） | 顶栏 `AI` 项 | 顶栏文案变「DeepSeek 已就绪」 | 顶栏仍「AI 未检查」（痛点 ④ 未修） |
| **F17** | P1 | AUTO/浏览器(`_eval`) | 任一页有 `.ux-feedback` 时量高度：idle vs error | `getBoundingClientRect().height` | 两值相等（零跳动，uier 断言 8） | 差值 >1px |
| **F18** | P0 | AUTO/浏览器 | `GET /jobs/j1`→`interrupted` | 错误区 | 「任务已中断」+ 「重新执行」按钮（AC-UI-06 扩展） | 只有文案无动作 / 仍显示「正在渲染」 |
| **F19** | P1 | MANUAL | 真机点任意按钮，慢速看 | 星标/按压/无闪白 | 星标 14px 不刺眼；按压 1px 下沉；pending 文字不抖动（宽度不变） | 按钮宽度跳变 / 星标抢注意力 / 双闪 |
| **F20** | P1 | MANUAL | 连触发 5 个长任务，看右下角 | toast 区 | 最多 3 条 + 「还有 N 个」；不遮挡主按钮与 A4 预览；danger 常驻 | 超过 3 条 / 遮挡导出按钮 / 危险提示自动消失 |
| **F21** | P0 | MANUAL | DevTools 对比度读数，浅色 + `[data-theme="dark"]` | 正文/按钮/错误文案 | ≥4.5:1（DESIGN §3） | 任一 <4.5 |
| **F22** | P0 | MANUAL | 纯键盘走完 A01→A02、A14→A16、A20 | Tab/Enter/Esc/焦点 | Tab 序合理；Enter 提交；**中文输入法选词回车不提交**；Esc 关最上层；焦点不回 `<body>` | 焦点丢失 / Esc 中断导出 / 输入法回车误提交 |
| **F23** | P1 | MANUAL | VoiceOver 走 A20 导出 + A04 核实 | 播报次数 | pending/success/error 各播报 1 次；轮询不刷屏 | 重复播报 / 只播颜色变化 / 进度条每次 tick 都念 |
| **F24** | P1 | MANUAL | 系统开「减少动态效果」 | 星标/骨架/toast 离场/按压 | 全部静态但**文字仍在**；无位移 | 只剩动画没有文字，或仍在位移 |
| **F25** | P0 | MANUAL | 停掉后端（或断网）后点任意动作 | 错误提示 | 「连不上本地后端」+ 端口提示 + 「重试」；不白屏 | 白屏 / `[object Object]` / 卡死无限转圈 |
| **F26** | P0 | MANUAL | 真 Chrome 引擎导出一份真实 PDF（8–12s） | 进度与恢复 | 进度条一直在动（阶段文案变化）；切到别的页再回来状态还在；完成后文件名/体积正确 | 中途无反馈 / 回来状态丢 |
| **F27** | P1 | MANUAL | 上传 4000×3000 照片 → 替换（确认弹窗）→ 移除 → 撤销 | 照片区四态 | 上传中有进度；替换有二次确认；移除后有「撤销」且真能恢复 | 无确认就覆盖；移除后无法撤销 |
| **F28** | P1 | MANUAL | 1280×800 + 200% 缩放，触发最长错误文案（`NAMING_MISSING_VAR` + 长 hint） | 布局 | 不横向滚动、不撑破卡片、错误码不折成乱码 | 溢出 / 截断 / 按钮被挤出 |

### 6.3 新增 AC 的落账要求（不做这步就等于没验收）

1. 每条 `AC-UXF-01..28` 必须回写 `docs/ACCEPTANCE.md` §10（当前表在 **351-359 行**），带 P0/P1 与验证列（AUTO 写 pytest 节点 id；MANUAL 写手工步骤）。
2. 每条 AUTO 必须同时有 `@check("AC-UXF-xx")` 紧贴 `def` 上一行（`tests/acceptance/test_ac_ui_browser.py`）或静态断言落在 `tests/test_web.py`；每条 MANUAL 必须进 `tests/acceptance/manual.py` 的 `MANUAL` dict。否则 `make_index.py --check` 会报未覆盖。
3. **当前账本基线**：160 条 / 已执行 157 / MANUAL 3（`AC-LOC-07`、`AC-PDF-20`、`AC-JD-05`）/ 未覆盖 0。新增 28 条后**自校验分母必须跟着变且未覆盖仍为 0**——具体数字以实际跑出来的为准，不要照抄本行估算。
4. 新增的 AUTO 项至少挑 3 条（建议 F09、F11、F13）做「改源码→用例 FAIL→md5 还原」的红证，登记进 `tests/acceptance/NEGATIVE_EVIDENCE.md`（既有 4 条的格式）。
5. `-k` 必须小写（既有约定：`-k ac_ui_05`）。

---

## 7. 仲裁表：uier 契约 ↔ 现存实现 ↔ 本文件口径（coder 先读这节）

> 下面每条都已在 16:30–16:36 之间实测过文件行号。**冲突一律以此表裁决**，不要按「看起来更顺手」的那一套写。

| # | 冲突 | 现状证据 | 裁决 |
| --- | --- | --- | --- |
| **D1** | `feedback.js` 的 `createAction` 用 `dataset:{phase}` + `.is-pending`，uier CSS 只认 `[data-state="pending"]`（`uiverse.css:76-80`） | `feedback.js:127/150` | **以 uier 为准**：`data-state` 单属性；`phase` 删除；`is-pending` 只允许作为 CSS 的 legacy 兼容选择器存在，JS 不再写它 |
| **D2** | `feedbackRegion` 用 `aria-live` + `clear()` 重建 callout，uier §3.1 要求「四子节点预渲染 + 只改 `data-state` + 唯一播报走 `.sr-only[data-ux-live]`」 | `feedback.js:210-346`（`set()` 内 `clear(node)`） | **重写 DOM 形态**，函数名保留 `feedbackRegion`（减少页面改动），并导出 `feedback()` 作为 uier §5.2 的别名；`aria-live` 留在容器，但**播报文本只经 `.sr-only[data-ux-live]`** |
| **D3** | toast 容量：DESIGN §8 与 uier G2 说「最多 3」，`toast.js` 是 `MAX_VISIBLE=4` | `toast.js:21` | **取 3**（改 `MAX_VISIBLE`），第 4 个折叠进「还有 N 个任务在进行」 |
| **D4** | toast 离场：uier 要 `.toast.ux-is-leaving` + `animationend`；`toast.js` 用 `.is-leaving` + 内联 transition 160ms | `toast.js:202` vs `uiverse.css:551` | **以 uier 为准**：class 改 `ux-is-leaving`，用 `animationend` 移除节点，另加 300ms 兜底定时器（动画被 reduce-motion 干掉时仍能移除） |
| **D5** | 在途禁用：任务原话「提交期间按钮不禁用」；uier §3.2 明确**不许用 `disabled`**（丢焦点） | 5 处 `node.disabled = true` | **语义双向满足**：目标是「不可重复提交」，手段是 `aria-disabled` + `pointer-events:none` + L1 同步闸；`disabled` 仅用于结构性不可用（导出缺字体、无模板补充行） |
| **D6** | 按钮文案：任务要求四态写「按钮文案变化」；uier §3.8 要求**在途不改文案**（宽度跳动） | uier §3.8 | **按 uier**：DOM 文案不变，pending 由 CSS 让文字透明 + 星标表达；「文案变化」落在反馈区与播报。例外：语义永久改变时允许改（如「设为默认」成功后按钮变「✓ 默认」） |
| **D7** | `JOB_TIMEOUT` 的 hint 指向「任务」页，但 7 个路由里没有任务页（`jobs` 是岗位页） | `api.js:176`；`boot.js:15-23` | 改 hint：「任务可能还在服务端跑：**回到本页重新导出**，或稍后重试。」（**不要新增第 8 个路由**，超出本次边界） |
| **D8** | 错误码词表三方不一致：后端 `IMPORT_NO_TEXT_LAYER`（`server/app/errors.py:34`、`import_service.py:99`）；`errors.js:42` 写 `IMPORT_NO_TEXT`；`feedback.js:50-53` 写 `IMPORT_UNSUPPORTED/IMPORT_FILE_TOO_LARGE/IMPORT_PARSE_FAILED/IMPORT_EMPTY` | 实测三处 | 以后端码为准：`errors.js` 增加 `IMPORT_NO_TEXT_LAYER` 条目（保留 `IMPORT_NO_TEXT` 作别名）；`replaceAll` 到 `NON_RETRYABLE_CODES`；`templates.js:63` 的分支改为判后端码 |
| **D9** | REVIEW-CHECKLIST §1.6 的 UI-04/UI-14 判据 grep 的路径已不存在 | `web/src/modules/consent.js`、`web/src/modules/views/*.js` | 本文件不改那份 checklist；**验收时用现路径** `web/src/components/consent-modal.js`、`web/src/pages/*.js`，并在 §6 判据里避免照抄旧路径（否则假红） |
| **D10** | 两套长任务 UI：死代码 `job-toast.js`（uier C1 要改它）vs 新的 `progress.js` + `toast.js`（页面未来实际会用） | `grep jobToast web/src/pages` → 0；`components/index.js:20-22` 三个都转口 | **只接 `progress.trackJob` + `toast.js` 任务卡**；`job-toast.js` 不再被任何页面引用（留作参考或由 coder 单独决定删除），严禁同一页面两套并存 |
| **D11** | `api.js` 缺 4 个方法（`restorePackage` / `generateVariants` / 照片上传 / 照片删除+确认）；页面若自己 `api.post("/api/v1/...")` 会破坏「页面只调 api 对象」纪律 | `api.js:62-116` 方法表 | 先补方法再改页面；照片三件套命名建议 `uploadPhoto(file)` / `confirmPhoto({attachment_id｜sha256})` / `removePhoto()` |
| **D12** | `feedback.js` 的 error 渲染已自带三段式；页面若继续 `"失败：" + errorText(err)` 会双层文案 | `feedback.js` error 分支 vs `errors.js:140` | 结构化渲染一律传 `err` 给 `feedbackRegion.error(err, …)`；`errorText` 只用于**纯文本**场景（折叠的「技术细节」、console、复制给开发者） |
| **D13** | `components/index.js` 现在只转口了新模块 `toast.js`(:21) 与 `feedback.js`(:22)，**`progress.js` 未导出** | `index.js` 共 24 行 | 页面**按模块直引**（现状 7 页都是直引 `../components/xxx.js`），不要改成从 index 取；`progress.js` 由 coder 决定是否补一行 `export *`（补了也不改页面写法） |

---

## 8. 落地顺序与 3 处最容易做歪

### 8.1 顺序（每步可独立验收）

1. **接线底座**：`index.html` 引 `uiverse.css`（A1）→ `feedback.js` 按 §7 D1/D2 重写 → `primitives.button` 加 `state`（uier A3）→ `toast.js` 容量/离场（§7 D3/D4）。验收 F02/F05/F17。
2. **错误码与文案**：§7 D8 词表统一 + `errorText` 复用边界（D12）。验收 F06/F07。
3. **防重复与四态**：按 §3 表逐页改（先 workbench → templates → profile → settings，再 jobs → builds，最后 warehouse 的乐观更新）。每页改完跑 F01/F08；空态带动作（痛点 ⑤）与本次改动一起做，验收 F15。
4. **长任务**：`builds.exportPdf` 接 `progress.trackJob`（A20）→ `jobs.pollJob`（A15/A16）→ 变体（A22）。验收 F09–F14/F18。
5. **新增动作**：归档/恢复/删除（A05–A07）→ 照片（A26/A27）→ 生成变体（A22）→ 顶栏重探（A32）。验收 F15/F16/F27。
6. **终检**：F19–F28 手工过一遍 + `make_index --check` + `NEGATIVE_EVIDENCE` 补 3 条红证。

### 8.2 最容易被 coder 做歪的 3 处

1. **`feedbackRegion` 的「重建式」写法会被保留下来**。它现在每次 `set()` 都 `clear()` + 重建，看起来能跑、文案也对，但正是「会丢焦点 + 双重播报 + 四态跳动」的根因（F17 会红、F22/F23 手工立刻异常）。改的时候不是加参数，而是换 DOM 形态：四子节点预渲染 + `data-state` + `.sr-only[data-ux-live]` 单通道。
2. **把「不可重复点击」写成 `disabled`**（最省事也最错）。任务原话是「提交期间按钮不禁用」的痛点，直觉答案就是 `disabled`；但 `disabled` 会把焦点踢到 `<body>`，键盘用户在长任务期间彻底失位，还会让 F08/F22 直接红。正确解是 L1 同步闸 + `aria-disabled` + `pointer-events:none`，`disabled` 只留给「结构性不可用」。
3. **长任务用「假进度」糊过去**。后端只有 5 → 20 → 100 三个报告点（`jobrun.py` + `builds.py:386/397`），coder 很容易写一个 `setInterval` 插值让它「看起来在动」——这既违反 F04（setInterval 零命中），又会在真实 20% 卡住 8 秒时骗用户。正确解：阶段文案（`job.message`）+ indeterminate 条 + 「可以离开这一页」，进度值只在后端给值时显示。

---

## 9. 未验证 / 待确认（诚实登记）

| # | 项 | 状态 |
| --- | --- | --- |
| Q1 | 7 个页面是否会在本次改动中被重写到 `web/src/modules/*`（旧 checklist 的路径） | 未定；以 `web/src/pages/` 为准 |
| Q2 | `server/app/api/builds.py` 的 `report(20,"组装内容")` 之后到 100 之间是否还有其他报告点 | 已 grep 未见；若 coder 加报告点，§4 P4 的「不定量」可升级为定量（需同步改 F09 断言） |
| Q3 | `docs/UI-REFRESH.md`（16:40:44 实测 52985B）与 `uiverse.css`（16:40:05 实测 21818B）仍在被 uier 修改，行数已比 16:36 时增加 | 文案与选择器以其最终版为准；本文件 §3 只引用编号不复制长句、§7 只引用选择器名不引用行号，降低漂移风险 |
| Q4 | 新增 28 条 AC 后 `make_index.py --check` 的精确分母 | 未跑；落地时必须实跑并登记，禁止照抄估算 |
