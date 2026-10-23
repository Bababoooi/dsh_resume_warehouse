---
name: resume-warehouse
description: 本地简历仓库与定制生成器（resume-warehouse）。把项目/实习经历打包成可复用的 Package 存入本机 Warehouse，导入现有简历拆成可重组模板，按 JD + 公司名分析岗位要求与招聘偏好，再按需组装成中/英定制简历并导出 PDF（文件名按用户指定模板）。全部数据留在本机，唯一上云出口是可切换的 LLM API（默认 DeepSeek），且每次调用前必须先把「将发送字段清单」返回给用户确认。当用户说「把这段经历存进简历库 / 导入我的简历 / 分析这个 JD / 按这个岗位出一份简历 / 导出 PDF 简历」时使用。
---

# resume-warehouse

本地优先的简历仓库 + 定制生成器。它是一个**本机 HTTP 服务**（Flask，只监听 `127.0.0.1`）+ 一个可选的网页界面。
你（模型）不需要读源码：按本文件的端点与流程调用即可完成 **录入 → 导入 → 分析 → 组装 → 导出**。

## 0. 先决条件与启动（每次会话开头做一次）

```bash
# 一键启动（幂等：首次会自动建 .venv 并装依赖，然后起服务）
bash <REPO>/skills/resume-warehouse/start.sh

# 启动后脚本会打印形如：
#   URL=http://127.0.0.1:8765
#   PORT_FILE=<REPO>/data/runtime/app_port
```

- **端口不是固定的 8765**：被占用会自动顺延。真实端口写在 `data/runtime/app_port`（JSON：`port/host/url/pid/started_at`）。
  读它的方式：`PORT=$(python3 -c "import json;print(json.load(open('<REPO>/data/runtime/app_port'))['port'])")`
- 检查是否已在跑：`curl -s http://127.0.0.1:$PORT/api/v1/health`
- 停止：`bash <REPO>/skills/resume-warehouse/stop.sh`
- 冒烟体检：`curl -s http://127.0.0.1:$PORT/api/v1/env`（缺依赖/缺字体会在 `warnings` 里说明）

`<REPO>` 是用户克隆 `resume-warehouse` 的目录（含 `server/`、`scripts/`、`skills/`）。

## 1. 通用约定（所有调用都遵守）

响应信封：

```json
{"ok": true,  "data": {...}, "request_id": "req_..."}
{"ok": false, "error": {"code": "VALIDATION_ERROR", "message": "…", "details": {...}, "hint": "…"}, "request_id": "req_..."}
```

- 列表信封：`{"items": [...], "next_cursor": null, "total_estimate": 12, "limit": 50, "offset": 0}`
- 写操作成功：`201` + `Location`（创建）、`204`/`200`（删除/更新）、`202` + `{"job_id": "..."}`（长任务）
- 长任务轮询：`GET /api/v1/jobs/{job_id}` → `status ∈ queued|running|succeeded|failed|interrupted`；
  成功时读 `result_json`，失败时读 `error_json`（结构与上面的 `error` 相同）。
- 常见错误码：`VALIDATION_ERROR`(422)、`NOT_FOUND`(404)、`CONFLICT`(409)、`PATH_ESCAPE`(400)、
  `FILE_IN_USE`(409)、`NO_DEFAULT_TEMPLATE`(409)、`IMPORT_NO_TEXT_LAYER`(422)、`NAMING_*`(422)、
  `LLM_CONSENT_REQUIRED`(428)、`LLM_CONSENT_EXPIRED`(410)、`LLM_CONSENT_MISMATCH`(409)、
  `LLM_UNREACHABLE`(503)、`LLM_TIMEOUT`(504)、`LLM_TRUNCATED`(502)、`LLM_JSON_MODE_PRECONDITION`(422)、
  `EGRESS_BLOCKED`(403)、`FONT_UNAVAILABLE`(500)。
- 响应里的 `warnings[]` 是**给人看的诚实提示**（如 `PAGE_FIT_DOWNGRADED` 降档、`LANG_FALLBACK` 英文版沿用中文正文、
  `SOURCE_CONFLICT` 中英简历数字不一致、`PACKAGE_MISSING` 某段本次无内容）。**要把 warnings 转述给用户**，不要吞掉。

## 2. 五个能力（按需组合，不必每次全做）

### 2.1 档案（身份与命名的唯一来源）

```bash
curl -s http://127.0.0.1:$PORT/api/v1/profile            # 读：含 completeness / missing
curl -s -X PUT http://127.0.0.1:$PORT/api/v1/profile \
  -H 'Content-Type: application/json' \
  -d '{"name_zh":"张三","name_en":"San Zhang","school_zh":"示例大学","school_en":"Example University",
       "degree":"本科","major":"管理科学","grad_year":2028,"phone":"13800138000",
       "email":"zhangsan@example.com","city":"武汉","available_note":"2027年1月下旬",
       "school_tier":"985"}'
# 照片：上传（multipart，≤5MB，png/jpg）→ 确认（PUT，按 attachment_id 或 sha256）
curl -s -X POST http://127.0.0.1:$PORT/api/v1/profile/photo -F "file=@/path/photo.png"
curl -s -X PUT  http://127.0.0.1:$PORT/api/v1/profile/photo -H 'Content-Type: application/json' -d '{"attachment_id":"att_..."}'
```

- `name_zh` 是必填（首次写档案时）；`PUT` 是**部分更新**，显式 `null` 表示清空。
- `school_tier` 只接受 `C9/985/211/双一流/普通本科/海外/其他`；不填也能用，但竞争力判断只能推断并会告警。
- 英文版会读 `extra.degree_en / major_en / city_en / available_note_en`；缺了会**省略该行**并告警，不会把中文写进英文简历。

### 2.2 导入现有简历 → 可重组模板（+ 顺带拆成经历包）

```bash
# 上传并解析（pdf/docx/md/html/txt 或直接粘贴文本）；返回 201 + job_id + 内联 draft（不自动入库任何模板）
curl -s -X POST http://127.0.0.1:$PORT/api/v1/imports -F "file=@/path/resume.pdf"
# 粘贴文本：
curl -s -X POST http://127.0.0.1:$PORT/api/v1/imports -H 'Content-Type: application/json' \
  -d '{"text":"教育背景\n…","filename":"pasted.txt"}'

curl -s http://127.0.0.1:$PORT/api/v1/imports/$IMPORT_ID/draft     # 看 blocks[]（section→entry→bullet）
curl -s -X PUT http://127.0.0.1:$PORT/api/v1/imports/$IMPORT_ID/draft \
  -H 'Content-Type: application/json' -d '{"draft": {...修改后的 draft...}}'
curl -s -X POST http://127.0.0.1:$PORT/api/v1/imports/$IMPORT_ID/export-draft   # 落 data/exports/import_draft_*.{json,md}

# 确认后落成模板（并可选：每条经历也落成 Package）
curl -s -X POST http://127.0.0.1:$PORT/api/v1/imports/$IMPORT_ID/commit \
  -H 'Content-Type: application/json' \
  -d '{"template_name":"中文-单页","lang":"zh","page_limit":1,"set_default":true,
       "also_create_packages":true,"apply_identity":true}'
```

- `draft.blocks[]` 里 `block_type ∈ header/section/entry/skills/awards/summary`，条目正文在 `entry.bullets` 与 `entry.facts`。
- 解析质量字段：`stats{pages,chars,cid_missing}`、`warnings[]`、`needs_llm_fallback`（**为 true 时先问用户**，不要擅自把简历发给 LLM）。
- 照片只作为**候选**返回（`extracted_photo`），必须用户确认才写进档案（避免误用）。
- `also_create_packages=true`：每条实习/项目/校园条目 → 一个 Package，原始句子 → `tone=original`、`verified=true` 的变体；同一份导入重复执行是幂等的。
- 模板：`GET /api/v1/templates`、`GET /api/v1/templates/default?lang=zh`、`POST /api/v1/templates/{id}/default`。
  没有默认模板时组装会返回 `409 NO_DEFAULT_TEMPLATE`（**不许自行挑一个**，要让用户选或先设默认）。

### 2.3 对话式打包经历 → Package（核心仓库）

```bash
# 一段自然语言 → 结构化草稿（纯本地、零出网；返回 questions[] 告诉你还缺什么）
curl -s -X POST http://127.0.0.1:$PORT/api/v1/packages/draft -H 'Content-Type: application/json' \
  -d '{"text":"2026年7-10月在杭州拓端数据科技做数据处理实习生，负责合肥空气质量数据治理，把日处理时间从8小时降到24分钟","kind":"internship"}'

# 落库（带变体）
curl -s -X POST http://127.0.0.1:$PORT/api/v1/packages -H 'Content-Type: application/json' \
  -d '{"title":"杭州拓端数据科技有限公司","kind":"internship","org":"杭州拓端数据科技有限公司",
       "role":"数据处理实习生","start_date":"2026-07","end_date":"2026-10","is_current":false,
       "tech_stack":["Python","SQL"],"tags":["数据清洗"],
       "variants":[{"bullet_key":"b1","tone":"impact","lang":"zh","text":"…","verified":true}]}'

curl -s "http://127.0.0.1:$PORT/api/v1/packages?q=订单&status=ready"   # 中文全文检索（FTS5）
curl -s http://127.0.0.1:$PORT/api/v1/packages/$PKG_ID?include=variants
curl -s http://127.0.0.1:$PORT/api/v1/packages/stats                   # 库健康度：包/变体/待核实/模板
```

- `kind ∈ project/internship/education/award/activity/custom`；`status ∈ draft/ready/archived`。
- **`status=ready` 的前置条件**：该包至少有一条 `verified=true` 的变体，否则 `409`（`details.reason="PACKAGE_NEEDS_VERIFIED_VARIANT"`、`details.unverified=[...]`）。
- `is_current=true` 时不能给 `end_date`（422）。
- 变体：`tone ∈ impact/technical/leadership/concise/ats/original`，`lang ∈ zh/en`，
  唯一键 `(package_id, bullet_key, tone, lang)`，重复插入返回 `409`（用 `PUT` 改现有那条）。
- 删除是软删（`deleted_at`），`POST /api/v1/packages/{id}/restore` 可恢复；`archived` 默认不出现在列表里。

### 2.4 JD 与公司偏好分析

```bash
# 建 JD（raw_text 就是用户粘贴的 JD 全文）
curl -s -X POST http://127.0.0.1:$PORT/api/v1/jds -H 'Content-Type: application/json' \
  -d '{"title":"数据分析实习生（增长方向）","company_name":"星链数科（杭州）有限公司","raw_text":"…JD 全文…","lang":"zh"}'

# 分析：method=heuristic 纯本地；auto/llm 需要先做 consent preview（见 §3）
curl -s -X POST http://127.0.0.1:$PORT/api/v1/jds/$JD_ID/analyze -H 'Content-Type: application/json' \
  -d '{"method":"heuristic"}'                      # → 202 job_id；auto 且 LLM 就绪却没 preview → 428
curl -s http://127.0.0.1:$PORT/api/v1/jds/$JD_ID                  # 含 competitiveness
curl -s http://127.0.0.1:$PORT/api/v1/jds/$JD_ID/requirements
curl -s -X PATCH http://127.0.0.1:$PORT/api/v1/requirements/$REQ_ID -H 'Content-Type: application/json' \
  -d '{"priority":"must"}'                          # 人工修正后 source=manual
curl -s -X POST http://127.0.0.1:$PORT/api/v1/jds/$JD_ID/match -H 'Content-Type: application/json' \
  -d '{"package_ids":["'$PKG_ID'"]}'                # 纯本地打分：score/hits/gaps/coverage

# 公司偏好（可联网抓公开页；默认开机，可按次关闭）
curl -s -X POST http://127.0.0.1:$PORT/api/v1/company-profiles/analyze -H 'Content-Type: application/json' \
  -d '{"company_name":"星链数科（杭州）有限公司","jd_id":"'$JD_ID'","allow_fetch":true,"method":"heuristic"}'
curl -s -X POST http://127.0.0.1:$PORT/api/v1/fetch/public-page -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/jobs"}'
```

- `competitiveness{school_tier, school_signal, degree_fit, major_fit, experience_fit, verdict, gap_notes[]}` 与
  `requirements[].candidate_status ∈ satisfied/partial/missing` 是「校名参与判断」的落点；`heuristic` 路径也必须给。
- `school_preference{threshold, preferred_tiers, hard_filter, evidence, confidence}`：**「985/211 优先」是偏好不是门槛**
  （`hard_filter=false`），「仅限 985/211」才是门槛（`hard_filter=true`）。JD 没提院校时 `threshold="不限"`、`evidence` 说明依据。
- 抓取是**下行只读**：只 GET 公开页、域名白名单、拒绝私有地址、≤3 跳、15s 超时、24h 缓存；
  `allow_web_fetch=false` → `403 EGRESS_BLOCKED`（`reason="fetch_disabled"`）。抓不到就降级为「只用用户粘贴的 JD」。

### 2.5 组装 + 导出 PDF

```bash
# 1) 建 build（不填 position/company 时从 JD 继承；naming_pattern 决定文件名）
curl -s -X POST http://127.0.0.1:$PORT/api/v1/builds -H 'Content-Type: application/json' \
  -d '{"name":"星链数科-数据分析实习","template_id":"'$TPL_ID'","jd_id":"'$JD_ID'",
       "position":"数据分析实习生","company":"星链数科（杭州）有限公司","lang":"zh"}'

# 2) 选包（整体替换；非 ready 的包 → 409）
curl -s -X PUT http://127.0.0.1:$PORT/api/v1/builds/$BUILD_ID/selections \
  -H 'Content-Type: application/json' -d '{"items":[{"package_id":"'$PKG_ID'","order_index":0}]}'

# 3) 预览（先看内容，不落文件）
curl -s http://127.0.0.1:$PORT/api/v1/builds/$BUILD_ID/preview            # JSON
curl -s "http://127.0.0.1:$PORT/api/v1/builds/$BUILD_ID/preview?format=html"

# 4) 导出（长任务）
curl -s -X POST http://127.0.0.1:$PORT/api/v1/builds/$BUILD_ID/export \
  -H 'Content-Type: application/json' -d '{"format":"pdf","verify_text":true,"density":"original"}'
curl -s http://127.0.0.1:$PORT/api/v1/jobs/$JOB_ID      # result_json.artifacts[0] → filename/rel_path/bytes/text_verified
curl -s -o out.pdf http://127.0.0.1:$PORT/api/v1/artifacts/$ARTIFACT_ID/download
```

- `format ∈ pdf/docx/html/md`；`density ∈ original(默认，边距最紧、单页能力最强) / relaxed`。
- 命名模板：默认 `{position}-{name}-{school}`。可用变量 `{name}{school}{position}{company}{date}{version}{lang}`，
  变量缺失是**硬错误**（`422 NAMING_MISSING_VAR`，不落任何文件）——缺字段就回 §2.1 补档案，别改模板。
- 版式：中文 reportlab + 系统宋体，正文首档 11pt（装不下才降到 10.5/10/9.5 并发 `PAGE_FIT_DOWNGRADED`）；
  照片画在右上角 89.28×89.28pt（无照片不影响其它元素位置）。
- 导出后 `text_verified=true` 表示「PDF 文本层与内容逐段一致」；为 false 会带 `TEXT_LAYER_MISMATCH`（字体缺字形），此时应换 `lang`/字体或降级 `docx`。

## 3. LLM 使用规则（唯一上云出口，必须先给字段清单）

只有这 5 个 purpose 会调用 LLM：`jd_analyze`、`company_profile`、`build_suggest`、`bullets_generate`、`summary_polish`。
它们共用一套两步协议：

```bash
# ① 预览：只传 ID，不传文本。响应 payload 就是「逐字将发送的请求体」
curl -s -X POST http://127.0.0.1:$PORT/api/v1/llm/preview -H 'Content-Type: application/json' -d '{
  "purpose":"bullets_generate",
  "selections":{"package_ids":["'$PKG_ID'"],"tones":["impact"],"lang":"en"},
  "options":{"auto_redact":true}
}'
# → data.preview_id / data.payload / data.fields[]（字段名+字数+是否脱敏）/ data.excluded / data.redactions / data.expires_at(10 分钟)

# ② 用户在后端确认后（或用户在 UI 点「同意发送」），带 preview_id + payload_sha256 提交
curl -s -X POST http://127.0.0.1:$PORT/api/v1/llm/complete -H 'Content-Type: application/json' \
  -d '{"preview_id":"'$PREVIEW_ID'","expected_payload_sha256":"'$SHA'"}'
```

**把 `fields[]` 与 `excluded` 转述给用户，等他明确同意再调 `complete`。** 不要跳过预览直接调业务端点——
`/jds/{id}/analyze`（method=auto/llm）、`/company-profiles/analyze`、`/packages/{id}/variants/generate`
在没有有效 `preview_id` 时一律 `428 LLM_CONSENT_REQUIRED`。

隐私边界（由服务端强制执行，不可绕过）：

| 内容 | 是否上云 |
|---|---|
| 姓名 | **永不**（固定替换为 `[NAME]`，用户关不掉） |
| 电话 / 邮箱 | 默认脱敏为 `[PHONE]/[EMAIL]`；用户可在设置里关，但仍会被本机身份校验拦住 |
| 照片字节与哈希 | **永不** |
| 原始简历文件 `data/imports/**` | **永不**（只有用户显式选中的条目文本会进 payload） |
| 学校名 / 学历 / 专业 / 届别 / 城市 / 到岗时间 | 按真实值发送（竞争力判断需要） |
| 经历与项目文本、JD、公司名、岗位名、备注 | 按真实值发送 |

- `bullets_generate` 生成英文变体：`selections.lang="en"`（源事实可以仍是中文，模型负责输出英文）；
  结果**不会自动入库**，job 的 `result_json.variants[]` 是草稿，用户确认后再 `POST /packages/{id}/variants`。
- `GET /api/v1/llm/egress-log` 可审计「发过哪些字段」（只记字段名与字节数，不记内容）。
- 模型路由：`LLM_MODEL`=对话/改写/摘要；`LLM_MODEL_ANALYSIS`=JD/公司/匹配/组装策略。不要在业务代码里写模型名。

## 4. 两种驱动模式

1. **网页界面（默认）**：浏览器打开 `http://127.0.0.1:$PORT/`。五个页面（仓库 / 导入 / JD / 组装 / 设置）都走同一套 API；
   ConsentModal 就是 §3 的 `preview` 前置。
2. **HTTP / CLI（无界面）**：用上面的 `curl` 直接驱动，适合脚本化批量出简历。导出产物落 `data/exports/`，
   文件名即命名模板结果；同名已存在时加 `-2/-3` 后缀（`overwrite=true` 才覆盖）。

## 5. 故障排查（按症状查）

| 症状 | 原因 / 处理 |
|---|---|
| 连不上 | 先看 `data/runtime/app_port`；端口被占用会自动顺延。启动失败看 `data/logs/app.log` |
| `502/503 LLM_*` | `curl /api/v1/llm/status`；`python3 scripts/llm_probe.py` 自检（不打印 key）。网络抖动会自动重试 |
| `422 LLM_JSON_MODE_PRECONDITION` | 提示词缺 `json` 字样（本地拦截、零出网）：说明是模板 bug，不是网络问题 |
| `502 LLM_TRUNCATED` | 模型把 token 花在推理/输出被截断：提高 `max_tokens_analysis`（≥2048）或缩短输入 |
| `428 LLM_CONSENT_REQUIRED` | 少了 §3 的 preview；先做预览并把字段清单给用户看 |
| `409 NO_DEFAULT_TEMPLATE` | 没有默认模板：`POST /templates/{id}/default` 或让用户选 |
| `422 NAMING_MISSING_VAR` | 文件名变量缺值（多为档案缺 `name/school` 或 build 缺 `position`）。补档案，别改模板 |
| `500 FONT_UNAVAILABLE` | 系统缺宋体（`/System/Library/Fonts/Supplemental/Songti.ttc`）；`/api/v1/env` 的 `fonts` 段会给出链路 |
| `text_verified=false` | 文本层与内容不一致：换 `lang`、或 `format=docx` 兜底；warning 里会列出缺的段落 |
| `409 FILE_IN_USE` | 文件被档案照片/构建产物/导入草稿引用：先解绑再删 |
| 数据看着不对 | `GET /api/v1/packages/stats`、`GET /api/v1/imports`、`GET /api/v1/templates`；真库改前先 `GET /api/v1/settings/export-all` 备份 |

## 6. 数据目录（全部本地，`DATA_DIR` 默认 `./data`）

```
data/
  app.db              SQLite（WAL）：档案/包/变体/模板/导入/JD/公司/构建/产物/任务/LLM 预览与审计
  files/              附件（内容寻址 sha256）：照片、证据
  imports/            用户上传的原始简历（**永不发给 LLM，永不进 payload**）
  exports/            导出产物（PDF/HTML/MD）与报告；备份 zip 也落这里
  profile/            确认后的档案照片
  runtime/app_port    真实端口与进程信息（JSON）
  logs/               app.log（滚动；key 自动脱敏为 sk-***）
  backups/            脚本级快照（如迁移/修复前）
```

- `.env`（600 权限）是唯一的密钥位置：`LLM_PROVIDER / LLM_BASE_URL / LLM_MODEL / LLM_MODEL_ANALYSIS /
  LLM_API_KEY / LLM_TIMEOUT_SECONDS / LLM_MAX_RETRIES / APP_PORT / DATA_DIR`。**不要把 key 写进代码、日志或对话。**
- 迁移是自动的（`schema_version` 记录在 `app_setting`）；升级后 `GET /api/v1/health` 的 `db.schema_version` 应该变大。

## 7. 安装 / 卸载

```bash
# 方式 A：注册到 DSH 技能目录（推荐，全局可用）
cp -R <REPO>/skills/resume-warehouse ~/.dsh/skills/        # DSH_HOME 默认 ~/.dsh
# 方式 B：用 DSH 的 skill 管理工具
#   skill_manage(action="create", name="resume-warehouse", description="…", body="<本文件内容>")
# 方式 C：只在当前仓库用（不改任何全局配置）——直接按本文件调用 API 即可
```

卸载：删掉复制过去的目录 + `bash <REPO>/skills/resume-warehouse/stop.sh`。**不要**删 `data/`，那是用户数据。

## 8. 一条完整的最小链路（复制即可跑，不需要任何外部文件）

空仓库也能跑通：先建档案 → 粘贴一段简历文本导入并 commit（同时得到模板 + 经历包）→ 组装 → 导出 PDF。

```bash
bash <REPO>/skills/resume-warehouse/start.sh
PORT=$(python3 -c "import json;print(json.load(open('<REPO>/data/runtime/app_port'))['port'])")
B=http://127.0.0.1:$PORT/api/v1

# 1) 档案（命名的唯一来源；缺 name/school 会在导出时 422 NAMING_MISSING_VAR）
curl -s -X PUT $B/profile -H 'Content-Type: application/json' -d '{
  "name_zh":"张三","school_zh":"示例大学","degree":"本科","major":"管理科学（商业数据分析）",
  "grad_year":2028,"city":"武汉","available_note":"2027年1月下旬"}'

# 2) 粘贴文本导入 → 同时落模板与经历包（also_create_packages）
IMPORT=$(curl -s -X POST $B/imports -H 'Content-Type: application/json' -d '{
  "filename":"pasted.txt","lang":"zh","text":"教育背景\n2024.9-2028.6 示例大学 管理科学（商业数据分析） 本科\n\n项目经历\n门店选址与订单量预测 队长 2026.03 - 2026.04\n· 把 6527 条订单接入预测流程，备货周转提升 39.3%。"}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['import_id'])")

curl -s -X POST $B/imports/$IMPORT/commit -H 'Content-Type: application/json' \
  -d '{"template_name":"我的模板","lang":"zh","set_default":true,"also_create_packages":true}' \
  | python3 -c "import json,sys;d=json.load(sys.stdin)['data'];print('template',d['template_id'],'packages',d.get('packages_created'))"

TPL=$(curl -s "$B/templates/default?lang=zh" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['id'])")

# 3) 组装（选中的包必须 status=ready；导入派生的包已就绪）
BUILD=$(curl -s -X POST $B/builds -H 'Content-Type: application/json' \
  -d "{\"name\":\"demo\",\"template_id\":\"$TPL\",\"position\":\"数据分析实习生\",\"lang\":\"zh\"}" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['id'])")
PKGS_JSON=$(curl -s "$B/packages?status=ready&limit=50" \
  | python3 -c 'import json,sys;print(json.dumps([{"package_id":p["id"]} for p in json.load(sys.stdin)["data"]["items"]]))')
curl -s -X PUT $B/builds/$BUILD/selections -H 'Content-Type: application/json' -d "{\"items\":$PKGS_JSON}"

# 4) 导出（202 + 轮询）
JOB=$(curl -s -X POST $B/builds/$BUILD/export -H 'Content-Type: application/json' -d '{"format":"pdf"}' \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['job_id'])")
sleep 4
curl -s $B/jobs/$JOB | python3 -m json.tool | head -40   # result_json.artifacts[0].filename → 落 data/exports/
```

排错要点：`409 NO_DEFAULT_TEMPLATE` = 还没 commit 过模板（先做第 2 步，别自己挑一个）；
`422 NAMING_MISSING_VAR` = 档案缺 `name/school` 或 build 缺 `position`。
