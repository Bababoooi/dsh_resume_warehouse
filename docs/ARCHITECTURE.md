# ARCHITECTURE — 简历打包与定制生成系统

> 状态：**冻结（FROZEN v1.18）**。v1.18 变更：§5.3 补 **`provider=off` 零出网硬保证**（含「已确认的 consent preview 也不得发送」，判据 `outbound_calls == 0` 双证），登记 T-5。
> 状态：**冻结（FROZEN v1.17）**。v1.17 变更：**§7.5.1 `original` 档常量改定**（ADR-22）——`leading_ratio` 1.45 → **1.15**、字号阶梯首档 10.5 → **11.0**（11.0/10.5/10.0/9.5，9.5 为紧急档）、新增**条目头单行 + 日期列 12%–22% 版心**与**可用高度核算算式**（≈778 pt < 817.65 pt ⇒ 单页成立）、反作弊下限改为「中位字号 ≥10.5 pt、行距比 ∈[1.10,1.25]」+「不得靠裁内容换字号」反向断言；ADR-21 补改定说明、新增 **ADR-22**。
> 状态：**冻结（FROZEN v1.16）**。v1.16 变更：§7.5.2 新增 **基线四要素**（运行实例 `pid`/`started_at`、`health.data.build.id`、最新 `server/**/*.py` mtime 与 `started_at` 的先后、`db.schema_version`），并写明「**源码 mtime 晚于进程启动时间 ⇒ 结论作废**」。
> 状态：**冻结（FROZEN v1.15）**。v1.15 变更：修复 **§5.1 尾部 4 行孤儿表**（`审计层/前端层/依赖层` 原为 2 格行却紧跟 4 列表之后、且无表头，渲染与按列解析均会错位）→ 补 `| 层 | 约束与证据位置 |` 表头与空行分隔；表列自检见 API-CONTRACT §16.0 M3（mismatch **0**）。
> 状态：**冻结（FROZEN v1.14）**。v1.14 变更：修复表格列数缺陷 2 处（§1.2 表头补「判定」列、ADR-21 行日期并入理由列，ADR 表为 3 列）；判据未改，列自检见 API-CONTRACT §16.0 M3（mismatch **0**）。
> 状态：**冻结（FROZEN v1.13）**。v1.13 变更：§7.5.1 由「单页版式常量」改为 **`density` 两档**（`original` 默认：边距 8.3/16.4/14.8/15.6 pt、可用高度 **817.65 pt**、版心 **564.9 pt**、正文 10.0 pt；`relaxed`：15/16 mm、751.5 pt，允许 2 页）+ **反作弊下限**（字号 ≥9.5pt、行距 ≥1.45、边距不小于 `original`）+ **ADR-21**（密度取自用户原件而非通用审美）；§7.5.2 证据等级纪律保留，并把「未减边距的溢出算法」列为反面示例。

> 状态：**冻结（FROZEN v1.1）**。本文是后续所有实现、联调、验收的唯一架构依据。
> 任何偏离本文的决定必须在 `docs/ARCHITECTURE.md` 的「决策记录」中追加一条并标注日期与理由。
> 撰写时间：2026-10-23。环境探测在同一台机器上实测完成（见 §1）。
> 修订记录：**v1.1（2026-10-23）** 按 captain 回归实测 **F1–F4** 更新 —— 新增 §5.5「上游调用约定」、§6 新增 D14 并收窄 D7、§9 新增 KI-11..KI-13、ADR-14。其余章节未改。
> 修订记录：**v1.2（2026-10-23）** 按 captain 决断 ①③④⑤ 与用户拍板更新 —— 出网改为**双通道**（§5.1 上行 `llm_client` / 下行 `fetch_client`）；上云边界按**宽路径 + 占位符脱敏**重写（§5.4：经历/JD/公司名可发，姓名/电话/邮箱/照片永不上云）；端口顺延并写 `data/runtime/app_port`（§3.1 / D3）；体检脚本移到 `scripts/preflight.py`（§3.2）；照片链路（§4.4 / §7.2）；新增 D15、KI-14 / KI-15、ADR-15 / ADR-16。
> 修订记录：**v1.11（2026-10-23）** §3.3 补 `app_port` **生命周期三条**（启动时判陈旧并覆盖 / 退出仅当 pid==自己才删 / preflight 用 `lsof` 核对实况，D-26）。
> 修订记录：**v1.10（2026-10-23）** §7.2 证件照几何补「距页面右缘 **9.13 pt**」并记两个陷阱（98.42 是照片左边到页右缘；pdfplumber `top` 未按 MediaBox 归一化）；§9 KI-14 同步。
> 修订记录：**v1.9（2026-10-23，D-19）** 新增 **ADR-20**「校名不是允许发送而是必须参与判断」；§5.4 增「校名必须被消费」硬要求（`competitiveness`/`school_preference`/`competitiveness_summary`）。
> 修订记录：**v1.8（2026-10-23）** §3.2 目录树改为**真实布局**（`server/app/**` + `web/` + `scripts/run.sh`，D-15 闭环）；新增 **§7.6 简历内容结构约束**（荣誉不单独成节 / 小象超市归 project / `trim_courses` 默认关且裁剪须进 warnings / 技能不拆 tag）；新增 **ADR-19**（技能展示层与索引层分离）；ADR-18 附注「文案属于契约」。
> 修订记录：**v1.7（2026-10-23）** 新增 **§3.3 `data/runtime/app_port` 契约（D-03 定版）**：格式冻结为 **JSON 五字段** `{port,host,url,pid,started_at}`（允许多键、不许少键）、**原子写入**（`app_port.tmp` + `os.replace`）、消费者一律 `json["port"]`、**禁止 `int(read())` 纯数字解析**（含反向 grep 判据与 url/port 自洽断言）；§3.1/§3.2/D3 同步。
> 修订记录：**v1.6（2026-10-23）** §3.2 增「`key` 回显红线（一处允许的例外）」——允许回显 SHA-256 前 8 位指纹作身份锚点，禁止任何 key 字符片段（含末四位）。
> 修订记录：**v1.5（2026-10-23）** 上云边界最终口径（用户 m00265）——**学校名改为真实上云**，撤销 `[SCHOOL]` 占位符，脱敏名单收敛为姓名/电话/邮箱/身份证号，照片结构上不可传；新增 **ADR-18**（保留 ADR-16 以展示决策演进）。
> 修订记录：**v1.4（2026-10-23）** 一致性收口（captain 裁定）：F4 行改 `LLM_TRUNCATED`(502)、F2 行错误码统一为 `LLM_JSON_MODE_PRECONDITION`、D10 槽位缺失分层、D11 去自造码、`text_verified` 字段名统一、§3.2 补 `设置API密钥.command` 与「不回显 key 任何片段」红线。
> 修订记录：**v1.3（2026-10-23）** 按用户决策「坚持 DeepSeek 路线」——**移除 Ollama**：provider 枚举收敛为 `deepseek | openai_compatible | off`，删 §5.3 的 ollama 预设行、重写 KI-05、新增 ADR-17；`off` 升为「完全不上云」一等开关。

---

## 0. 一句话定位

一个**纯本地、零构建、零新增运行时依赖**的单机 Web 应用：把项目/实习经历打包成可复用 Package 存入本地 Warehouse，导入既有简历拆成可重组的 Template/Slot，分析 JD 与公司偏好，再按需把选中的 Package 片段组装成定制简历导出 PDF/DOCX。**唯一出网点是可切换的 LLM 适配层，且每次出网前必须由 UI 展示将发送的字段清单。**

---

## 1. 环境实测（2026-10-23，本机 macOS arm64 / macOS 26.5.1）

这一节不是「听说」，全部为本次实际执行结果。后续实现不得假设与实测冲突的东西。

### 1.1 运行时与包

| 项 | 实测结果 | 结论 |
|---|---|---|
| Python | `/opt/anaconda3/bin/python3` = **3.13.9**（Anaconda，Clang 20.1.8） | 使用该解释器 |
| pip | 25.3 | 可用，但**不作为构建前提** |
| venv | `python3 -m venv --system-site-packages .venv` **成功**，venv 内可 `import flask, reportlab, pydantic, docx` | ✅ 锁定为 `.venv` 方案 |
| venv（无 `--system-site-packages`） | **失败**（`ModuleNotFoundError: flask`） | ⚠️ 禁止用裸 venv，见 §3.1 |
| Flask | **3.1.0 已装**（werkzeug 3.1.3，jinja2 3.1.6），`test_client` 返回 200，真实绑定 `127.0.0.1:8765` + GET/POST JSON 均通过 | ✅ 后端框架定为 Flask |
| fastapi / uvicorn / starlette / multipart / aiofiles | 全部 **缺失** | ❌ 不用（不赌网络安装） |
| openai SDK | **缺失** | ❌ 不用，直接 httpx 打 HTTP |
| httpx | 0.28.1 | ✅ LLM 适配层唯一 HTTP 客户端 |
| pydantic | 2.12.4 | ✅ 请求/响应模型与校验 |
| jinja2 | 3.1.6 | ✅ HTML 预览与导出模板 |
| reportlab | 4.5.1 | ✅ **PDF 主引擎** |
| pdfplumber | 0.11.9 / pypdf 6.9.2 / pdfminer 20251230 | ✅ 导入解析与文本校验 |
| python-docx | 1.2.0 | ✅ DOCX 导入 + DOCX 导出 |
| markdown 3.8 / bs4 4.13.3 / lxml 5.3.0 | 已装 | ✅ MD/HTML 导入 |
| SQLAlchemy 2.0.43 | 已装但**不使用** | 用 stdlib `sqlite3` + 薄 DAO，见 §4.2 |
| sqlite3 | 3.51.0；**FTS5 可用**、`json_extract`/`json_each` 可用、WAL 可用 | ✅ 单文件库 `data/app.db` |
| pytest 8.4.2 / ruff 0.12.0 | 已装 | ✅ 验收与静态检查可用，无需联网 |
| playwright | 缺失 | ❌ 不做浏览器自动化测试 |
| weasyprint | **导入即炸**：`OSError: cannot load library 'libpango-1.0-0'` | ❌ 永久排除 |
| Node / npm | v22.22.1 / 10.9.4；**pnpm 缺失** | ❌ 前端零构建（不引入 Node 工具链） |

### 1.2 字体与 PDF 引擎实测（最关键的一组）

| 路径 | 结果 | 判定 |
|---|---|---|
| reportlab `UnicodeCIDFont("STSong-Light")` | 能出 PDF，但 **U+00B7 `·` 丢字**（提取文本里消失） | ❌ 不作为默认（`·` 会丢） |
| reportlab + `Songti.ttc` `subfontIndex=6` | 注册为 `STSongti-SC-Regular`；`subfontIndex=1` → `STSongti-SC-Bold`。**提取文本与源文本逐字相等**（含 `· 「」《》 ①② ％ 全角数字 ±÷≠≤≥`；rarer 字 `龘鑫彧甯喆珺屾赟` 全部 covered） | ✅ **主路径** |
| reportlab + `Arial Unicode.ttf` | 可注册、中文正常 | ✅ 备用/回退字体 |
| reportlab + `Hiragino Sans GB.ttc` | `TTFError: postscript outlines are not supported`（CFF 轮廓不支持） | ❌ 排除 |
| reportlab 表格内 `<b>` | **不生效**（TableCell 字符串不解析标记） | ⚠️ 实现约束：表格单元格必须放 `Paragraph` 对象 |
| reportlab + emoji（🚀✅） | 提取为 `\x00`，视觉为空白/豆腐 | ⚠️ 导出前必须剥离并告警 |
| Chrome headless `--print-to-pdf` | **可用**（18912 B，中文正常）。但**必须**加 `--user-data-dir=<临时目录>`，否则 `Failed to create a unique user data directory for headless` | ✅ 视觉级回退路径 |
| Chrome 的 ToUnicode 坑 | 字体不同结果不同：`Songti SC`/`Hiragino Sans GB` → 提取出 **康熙部首**（`高`→U+2FBC、`工`→U+2F2F，`"高级工程师" in text == False`）；`STHeiti` / `Arial Unicode MS` → **逐字精确** | ⚠️ Chrome 路径必须锁定字体栈，且只算视觉回退 |
| `/opt/homebrew/bin/soffice --convert-to pdf` | **崩溃**：`libc++abi: terminating due to uncaught exception ... DeploymentException` / `Fatal exception: Signal 6`，无产物 | ❌ LibreOffice 转换永久排除 |
| 系统字体清单 | `Songti.ttc`（8 个 face）、`STHeiti Light/Medium.ttc`、`Hiragino Sans GB.ttc`、`Arial Unicode.ttf`；**无 `PingFang.ttc`** | 字体声明见 §7.2 |

### 1.3 网络与端口（仅用于判定降级，不构成依赖）

| 探测 | 结果 |
|---|---|
| pypi.org / files.pythonhosted.org / api.deepseek.com / registry.npmjs.org:443 | **当前可达**（0.2–0.3 s） |
| `127.0.0.1:11434`（Ollama） | **closed**；`ollama` 命令与 `/Applications/Ollama.app` 均不存在 |
| `127.0.0.1:8765` | **free**（本项目默认端口） |
| `127.0.0.1:8000` / `:8080` | closed（但不采用，避免与其他开发服务器撞车） |

> **结论：网络虽然可达，但架构一律按「不可达」设计。** 任何实现步骤都不得要求 `pip install`、`npm install`、下载模型或拉取 CDN。本机未安装 Ollama，且用户已明确**坚持 DeepSeek 路线**——**Ollama 不在支持范围**（不写适配、不做预检、不做验收）。provider 只有 `deepseek` / `openai_compatible` / `off` 三档。

### 1.4 由实测直接推导出的 5 条硬事实

1. **后端 = Flask 3.1.0 + werkzeug 开发服务器**（不是 FastAPI，也不是 `http.server` —— 因为 Flask 已装且实测可跑，而标准库方案要手写路由/JSON/multipart 边界，风险更高）。`http.server` 保留为 §7.1 的第三级降级。
2. **PDF 主引擎 = reportlab + Songti.ttc 子字体**（CID 字体会丢 `·`，Chrome 会污染 ToUnicode，soffice 会崩）。三选一里只有它同时满足「中文不缺字」和「文本可被 ATS/复制粘贴正确取出」。
3. **venv 必须 `--system-site-packages`**，否则零依赖承诺立刻破产。
4. **前端零构建**：Vanilla ES Modules + 手写 CSS，由 Flask 直接托管。Node 存在但不使用。
5. **`LLM_PROVIDER=off` 是一等状态**（完全不上云）：UI 与预检必须能表达「AI 未启用」并让全部本地功能照常可用，而不是报错崩溃。

---

## 2. 技术选型与理由（逐项决策，含被否方案）

| 层 | 选定 | 理由（为什么是它） | 被否方案与原因 |
|---|---|---|---|
| HTTP 服务 | **Flask 3.1.0**（`app.run(127.0.0.1, 8765, threaded=True)`） | 已装、实测跑通、路由/JSON/multipart/静态托管全都现成；开发服务器对单用户本地应用足够 | FastAPI+uvicorn：未装，需联网安装 → 违反 ④；`http.server`：要手写 URL 解析、chunked、multipart、静态 MIME、错误页，代码量与缺陷面都更大 |
| 静态检查/测试 | pytest + ruff（均已装） | 离线可用 | playwright：未装，且本地应用不强制浏览器 E2E |
| 持久化 | **stdlib `sqlite3`**（FTS5 + WAL） | 单文件、零进程、FTS5 实测可用、`json_each` 可查 JSON 数组；直接写 SQL 便于控制索引与触发器 | SQLAlchemy：多一层映射而本地单用户无收益；JSON 文件：并发与查询都退化 |
| 数据校验 | **pydantic 2.12.4** | 请求/响应契约即代码，可 `model_json_schema()` 反向生成契约文档；与 API-CONTRACT 单一来源 | 手写校验：错误码与文案会漂移 |
| HTML 预览 | **jinja2 + 手写 CSS**（autoescape 强制开） | 零构建、可离线、模板即报告 | React/Vite：需 npm 联网 + 构建产物管理，违反 ④；零收益 |
| PDF 主引擎 | **reportlab platypus**（TTF 嵌入 Songti.ttc） | 唯一同时满足「中文不缺字 + 提取文本精确 + 无外部依赖」的路径（§1.2） | WeasyPrint（坏）、CID STSong-Light（丢 `·`）、Chrome（ToUnicode 污染）、soffice（崩） |
| PDF 视觉回退 | **Chrome headless `--print-to-pdf`** + 固定字体栈 + 临时 `--user-data-dir` | reportlab 排版能力有限（复杂双栏/图形）时的逃生门；实测可出中文 PDF | 只作回退：文本提取可能被污染，**导出后必须跑文本一致性校验**，不通过则回退到 reportlab 结果并告警 |
| DOCX 导出 | **python-docx 直接生成**（不经 soffice） | soffice 崩（§1.2），直接写 OOXML 可控且离线 | `docx→pdf` 转换：不可用 |
| 导入解析 | pdfplumber（PDF 文本+坐标）/ python-docx / markdown / bs4 | 全已装；pdfplumber 带 `words` 坐标，可做「按行聚簇→块切分」的启发式模板还原 | OCR（无依赖，图片型 PDF 明确不支持并给出提示） |
| LLM 适配 | **httpx 0.28.1 + OpenAI 兼容 `/chat/completions`** | DeepSeek 与任意 OpenAI 兼容网关同协议，一套客户端 + 两个预设即可覆盖；不引入 SDK（**不做 Ollama**，用户决策，见 ADR-17） | openai SDK（未装且非必需）；每 provider 写一套客户端（协议分叉成本） |
| 前端 | **Vanilla ES Modules + CSS 变量** | 零构建、离线、单用户；界面复杂度（表单/列表/模态）远低于需要框架的阈值 | 见上 |

### 2.1 为什么不引入任何新的 pip 包（写死这一条）

`requirements.lock.txt` **只记录实测版本用于自检，不用于安装**。启动预检脚本逐一 `import` 并比对版本，缺任何一个就打印修复指引并退出（退出码 2），而不是尝试安装。唯一允许的"安装"动作是 `python3 -m venv --system-site-packages .venv`（纯本地，无网络）。

---

## 3. 进程模型与目录布局

### 3.1 启动链

```
./scripts/run.sh
 ├─ 1. 若 .venv 不存在 → /opt/anaconda3/bin/python3 -m venv --system-site-packages .venv
 ├─ 2. .venv/bin/python scripts/preflight.py      # 纯本地体检，不联网（脚本在 scripts/，见 §3.2）
 │      ├─ import + 版本比对（flask/reportlab/pydantic/jinja2/httpx/pdfplumber/pypdf/docx/markdown/bs4）
 │      ├─ 字体探测：Songti.ttc idx6/idx1 可注册、Arial Unicode.ttf 存在
 │      ├─ 路径探测：data/ data/files data/exports data/logs 可写
 │      ├─ 端口：默认 8765 → 被占用则**顺延到下一个空闲端口**（8766…8799），实际端口原子写入 `data/runtime/app_port`（**JSON 五字段**，格式冻结见 §3.3）
 │      ├─ .env 权限：存在时 chmod 600，权限过宽打 WARN
 │      └─ 输出 JSON 体检报告 → data/logs/preflight.json
 │      └─ 启动横幅打印**真实** http://127.0.0.1:<实际端口>（run.sh / DSH Skill / UI 一律读 `data/runtime/app_port` 的 `json["port"]`，禁止让用户猜端口）
 └─ 3. .venv/bin/python -m app.server --port <实际端口>   # 前台运行，Ctrl-C 退出
```

- **单进程**：Flask（threaded=True，8 线程）。SQLite 每线程一连接（`check_same_thread=False` + `threading.local()`），写操作串行化（`BEGIN IMMEDIATE`，`busy_timeout=5000`）。
- **唯一的子进程**：`render_pdf_chrome` 回退路径会 `subprocess.run` 拉起 Chrome，超时 60 s，工作目录在临时目录，产物拷回 `data/exports/`。主路径（reportlab）**无子进程**。
- **无守护进程、无后台队列、无定时任务**。长操作（导入解析、LLM 调用、批量导出）以 `job` 表 + 轮询表达（见 API-CONTRACT §8），进程重启即把 `running` 的 job 标为 `interrupted`。

### 3.2 目录布局（写入范围即此，不得越界）

```
resume-warehouse/
├── .env                        # 机密，chmod 600，永不被读取接口回显
├── .env.example                # 仅键名与占位值
├── requirements.lock.txt       # 版本清单（自检用，不安装）
├── 设置API密钥.command          # 可选双击入口：把 key 写入 .env（chmod 600）。**只允许回显 key_set=true 或不可逆指纹（SHA-256 前 8 位）**，**禁止输出 key 的任何字符片段（含末四位）**；首行必须 `cd "$(dirname "$0")"`。它不参与服务运行，run.sh 不依赖它
├── scripts/
│   ├── run.sh                 # 一键启动（§3.1）：preflight → 端口顺延 → 横幅 → 起服务
│   ├── preflight.py           # 启动体检：纯本地、不联网，可独立 `python scripts/preflight.py`
│   ├── bootstrap.sh           # 首次准备（venv --system-site-packages、目录、.env 权限）
│   ├── check_egress.py        # 出网闸门自检：静态扫描 + 白名单断言
│   └── llm_probe.py           # provider 连通性探测（供 /api/v1/settings/provider/test 调用）
├── server/                     # ← 后端根（cwd 在此或把 server/ 加进 sys.path；模块导入仍是 app.*）
│   ├── server.py               # 入口：`python -m app.server` / `python server.py`
│   ├── tests/                  # pytest：契约测试、渲染测试、离线闸门测试
│   ├── app/
│   │   ├── __init__.py         # create_app()
│   │   ├── server.py           # Flask 实例、蓝图注册、静态托管、错误处理器
│   │   ├── config.py             # .env 解析、路径常量、provider 预设、脱敏函数
│   │   ├── db.py                 # 连接池(线程局部)、迁移执行器、事务助手
│   │   ├── schema.sql            # DDL（对应 DATA-MODEL.md）
│   │   ├── models.py             # pydantic 请求/响应模型（契约唯一来源）
│   │   ├── errors.py             # ApiError + 错误码表 + 统一 JSON 错误响应
│   │   ├── repos.py              # 数据访问层（SQL 集中处，service 不直接写 SQL）
│   │   ├── api/                  # 一资源一蓝图
│   │   │   ├── health.py  candidate.py  packages.py  variants.py
│   │   │   ├── imports.py  templates.py  blocks.py  slots.py
│   │   │   ├── jd.py  companies.py  builds.py  exports.py
│   │   │   └── naming.py  settings.py  llm.py  files.py  jobs.py
│   │   ├── services/
│   │   │   ├── warehouse.py      # Package CRUD + FTS 检索 + 标签过滤
│   │   │   ├── importer.py       # PDF/DOCX/MD/HTML/TXT → blocks+slots 草稿
│   │   │   ├── jd_analyzer.py    # JD → requirements（LLM 或离线启发式）
│   │   │   ├── company_profiler.py # 公司名(+JD) → CompanyProfile（带 TTL 缓存）
│   │   │   ├── assembler.py      # 选包 → 槽位解析 → 中间文档 IR（dict）
│   │   │   ├── render_html.py    # IR → HTML（jinja2, autoescape）
│   │   │   ├── render_pdf.py     # IR → PDF（reportlab 主路径 + Chrome 回退）
│   │   │   ├── render_docx.py    # IR → DOCX
│   │   │   ├── fonts.py          # 字体注册与回退链（唯一注册点）
│   │   │   ├── naming.py         # 命名模板变量解析 + 文件名净化
│   │   │   ├── consent.py        # payload 构造/预览/哈希/一次性令牌
│   │   │   └── textcheck.py      # 导出后 PDF 文本一致性校验
│   │   └── adapters/
│   │       ├── llm_client.py     # ★ 上行唯一出口：唯一允许把用户数据发出去的模块
│   │       ├── fetch_client.py   # ↓ 下行唯一出口：只下载公司官网/招聘页公开文本，请求体恒空
│   │       ├── providers.py      # deepseek / openai_compatible 预设（+ off，无 ollama，见 ADR-17）
│   │       └── egress_guard.py   # host 白名单断言 + 出网审计日志
├── web/                        # ← 前端（零构建：原生 ES modules + CSS，无 node_modules）
│   ├── index.html              # 主界面外壳（5 页 IA）
│   ├── preview.html            # 简历预览/打印视图
│   └── src/
│       ├── components/         # layout.js / consent-modal.js / import-review.js / package-card.js …
│       └── styles/             # base.css / layout.css / components.css / print.css
├── data/                       # ← 全部用户数据只在这里
│   ├── app.db                  # SQLite（WAL）
│   ├── files/<sha2>/<sha256>.<ext>   # 导入原件与中间产物
│   ├── exports/<YYYY>/<build_id>/<filename>.pdf|.docx
│   ├── logs/app.log            # 应用日志（自动脱敏）
│   ├── logs/llm-egress.jsonl   # 出网审计（字段名清单，**不含正文**）
│   ├── logs/preflight.json
│   ├── profile/                # 证件照 photo_*.png（gitignored，永不进 payload）
│   └── runtime/
│       ├── app_port            # **JSON 五字段**：port/host/url/pid/started_at（D-03 定版，见 §3.3）
│       └── app_port.tmp        # 原子写入中转，os.replace 后即刻消失
├── docs/                       # 本目录（5 份规格）
├── skill/                      # 独立 DSH Skill：SKILL.md + cli.py + examples/
└── tests/                      # pytest：契约测试、渲染测试、离线闸门测试
```

**`key` 回显红线（一处允许的例外）**

- **允许**：回显 `key_set=true` 这类布尔事实；回显 key 的**不可逆指纹**（`SHA-256(key)` 前 8 位，例如 `指纹 82be8a4d`）—— 用户填过多把 key 时，这是他唯一能核对「这次填的是不是原来那把」的锚点。
- **禁止**：输出 key 的任何**字符片段**（含末四位、前缀 `sk-` 之后的部分）、完整长度之外的任何可逆信息、把 key 写进日志/`llm_call_log`/错误消息/HTTP 响应。
- 判定：指纹**不含 key 任何字符、不可逆、不能用于鉴权**，因此不违反「不回显 key」的本意；而「打码末四位」既泄露 16 bit 又不解决「是哪把 key」的问题，属**禁止**。
- 可复验：`grep -c '末尾四位' 设置API密钥.command` → **0**；`grep -c '指纹' 设置API密钥.command` → **≥1**；`grep -Ec 'sk-[A-Za-z0-9]{4,}' 设置API密钥.command` → **0**。

**路径禁令（可被验收检查）**
- 除 `data/` 与 `tests/.tmp/` 外不写任何文件；导出文件绝不写到 `~/Desktop`、`~/Downloads`，除非用户在请求里显式给出**绝对路径**且值为 `data/exports` 之外的目标（此时记录 `EXPORT_OUTSIDE_DATA` 警告到 export 响应）。
- 所有来自请求的路径参数先 `Path.resolve()` 再断言 `is_relative_to(DATA_ROOT)`，否则 `PATH_ESCAPE`(400)。
- 上传文件名不参与磁盘命名（用 SHA-256 命名），原名只存库。

---

### 3.3 `data/runtime/app_port` 契约（**D-03 定版，格式冻结**）

该文件是端口顺延后**唯一可信的端口来源**，`run.sh`、`scripts/stop.sh`、DSH Skill、启动横幅、UI 顶部、`/api/v1/health` 六处消费者共用。**冻结为 JSON，不是纯数字。**

```json
{"port": 8765, "host": "127.0.0.1", "url": "http://127.0.0.1:8765", "pid": 78756, "started_at": "2026-10-23T03:05:03+08:00"}
```

| 键 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `port` | int | ✅ | **唯一权威端口**，消费者只看它 |
| `host` | str | ✅ | 恒 `"127.0.0.1"`（只监听 loopback） |
| `url` | str | ✅ | 与 `port` 自洽：必须 `url.endswith(":" + str(port))` |
| `pid` | int | ✅ | 服务进程 pid，`scripts/stop.sh` 靠它精准 `kill`，避免误杀；排障锚点 |
| `started_at` | str | ✅ | ISO 8601 **带时区**，用于判断"这次跑的是不是刚才那个实例" |

- **允许多加键，不允许少键。** 少任一必填键 → 消费者（`run.sh`/Skill）报「端口文件损坏，请重跑 ./scripts/run.sh」，不得静默回落 8765。
- **写入必须原子**：先写 `data/runtime/app_port.tmp`，`flush` + `os.fsync`，再 `os.replace(tmp, app_port)`。直接 `open(...,"w")` 会让并发读者读到半截 JSON（`json.JSONDecodeError`）。
- **消费者的唯一解析方式**：`json.loads(...)["port"]`。**任何地方禁止 `int(open(...).read())` / `int(read().strip())` 当纯数字解析**——那是 D-16 实测出的假红来源（实现写 JSON、判据当数字）。
- **自洽校验**（服务启动时自检，失败打 WARN 并重写）：`json["host"] == "127.0.0.1"`、`json["url"].endswith(":"+str(json["port"]))`、`json["port"] == 实际 bind 端口`。
**生命周期规则（D-26 定版，v1.11 补）**——陈旧文件会让「用户按横幅 URL 打开就是白屏」，必须按下面三条处理：

| 时机 | 规则 |
|---|---|
| **启动时** | 读已有文件：若 `pid` **不存活**（`os.kill(pid,0)` 抛 `ProcessLookupError`）**或**该 `port` **不可连**（`socket.create_connection` 超时/拒绝）→ 判为**陈旧**，直接覆盖写入新值（原子写）。只有 pid 存活**且**端口可连时才算「已有实例在跑」 |
| **优雅退出时** | **仅当**文件中 `pid == 自己` 时删除 `app_port`。pid 不匹配说明文件已被新实例接管，删了会把正在跑的实例的入口抹掉 |
| **preflight 时** | 增加一条一致性检查：`app_port.port` 必须能被 `lsof -nP -iTCP:<port> -sTCP:LISTEN` 证实有进程在听；且 `app_port.pid` 必须出现在该 `lsof` 输出里。不一致 → 打 WARN 并在 `/env` 的 `warnings[]` 里暴露（不阻断启动） |

实测踩点（D-26）：8765 在监听，但 `app_port` 写着 `8899 / pid 62604`（进程已死、端口拒绝连接）——正是「pid 不存活但文件还在」的 stale 场景。

- **反向 grep 判据**（期望命中 0，作为 `INT-11`/`INT-13` 的配套检查；**入册前必须在当前代码上跑过并确认基线为 0**，否则清单自带假红）：

```bash
grep -rnE 'int\([^)]*(app_port|app_port_file|PORT_FILE|port_file)[^)]*(read|read_text)\(\)' --include='*.py' --include='*.sh' .   # 期望无输出（基线已实测为 0）
```

## 4. 数据与存储边界

### 4.1 三类落盘物

| 类别 | 位置 | 说明 |
|---|---|---|
| 结构化数据 | `data/app.db` | 13 张业务表 + 2 张审计/设置表（见 DATA-MODEL.md） |
| 二进制原件 | `data/files/` | 导入的 PDF/DOCX/MD/HTML 原文，按内容哈希去重 |
| 产物 | `data/exports/` | 导出 PDF/DOCX；同名冲突走 `-2`、`-3` 后缀，除非请求带 `overwrite=true` |

### 4.2 DB 约定

- `PRAGMA journal_mode=WAL; foreign_keys=ON; busy_timeout=5000; synchronous=NORMAL;`
- 迁移：`schema_migration(version INTEGER PRIMARY KEY, applied_at TEXT)`；`app/schema.sql` 中每条 DDL 以 `-- @version N` 分段，启动时顺序补齐（幂等）。
- 时间统一 `TEXT` ISO-8601（`YYYY-MM-DDTHH:MM:SS+08:00`）；ID 为 `TEXT` UUIDv7（可排序、无外部依赖，用 `uuid.uuid4().hex` + 时间前缀生成）。
- 列表字段用 `TEXT` JSON 数组（SQLite `json_each` 查询），**不用逗号分隔字符串**。
- 全文检索：`package_fts(variant_text, package_title, org, role, tags_text)` FTS5 虚表 + 3 个触发器同步（insert/update/delete）。中文无分词器 → 用 `unicode61` + 双字 bigram 预切分写入 `tags_text`/`search_blob`（实现细节留实现者，契约是 `GET /packages?q=` 能命中中文子串）。

### 4.3 备份与恢复（不做自动化，只提供操作）

`sqlite3 data/app.db ".backup data/backup/app-$(date +%Y%m%d).db"` 写进 README 提示即可。系统**不得**自动上传或自动同步任何数据。

### 4.4 UserProfile 是唯一身份源（单例，禁前端硬编码）

简历头部（姓名/学校/联系方式/照片）与**导出文件名**都只能从数据库里的 `user_profile`（单行，`id=1`）取值：

| 字段 | 用途 |
|---|---|
| `name_zh` / `name_en` | 简历标题行；命名模板 `{name}` 取 `name_zh`（回退 `name_en`） |
| `school_zh` / `school_en` | 教育背景区块默认值；命名模板 `{school}` 取 `school_zh`（回退 `school_en`） |
| `degree` / `major` / `grad_year` | 教育区块；`{version}` 与 `{date}` 不取自此 |
| `phone` / `email` / `city` / `available_date` | 联系行；**进 LLM 前必须脱敏**（见 §5.4） |
| `photo_path` | 指向 `data/profile/` 的证件照（文件名 `photo_<sha256>.<ext>`）；仅本地渲染，**永不进 payload** |
| `photo_source` | `manual`（用户上传/替换）/ `imported`（从导入简历内嵌图片抽取）/ `none` |

- 前端**不得**出现任何硬编码的人名/校名（示例数据也必须放 `data/` 或走接口）。验收：`grep -rn "张三\|示例大学" web/ server/app/` 无命中（AC-NAME-07）。
- 渲染层通过 `profile_context()` 注入 jinja2，模板写 `{{ profile.name_zh }}`，不写常量。
- `user_profile` 缺失时不得崩：简历头部留空 + `warnings=["PROFILE_INCOMPLETE"]`；但**导出文件名**若因此缺 `{name}`/`{school}`，必须直接 422 `NAMING_MISSING_VAR`（不得产出 `-示例大学.pdf` 这种残名）。

### 4.5 导出命名模板

- 默认值（存 `app_setting.naming_template`）：`{position}-{name}-{school}` → 例 `数据分析实习生-张三-示例大学.pdf`。
- 变量全集：`{company} {position} {date} {name} {school} {version} {lang}`；解析/净化/错误码的唯一定义在 `docs/API-CONTRACT.md` §9（`POST /api/v1/naming/validate` 是纯函数，恒 200，只回 `ok=false` + `NAMING_*` 码）。
- **缺变量即失败**：`{name}` 无值 → `NAMING_MISSING_VAR`，导出接口返回 422 且**不落任何文件**。这是硬约束，不是警告。
- 产物落 `data/exports/`；文件名经 8 步净化（见契约），且最终路径必须 `os.path.realpath()` 后仍以 `data/exports/` 开头（防穿越）。

### 4.6 `.gitignore` 是隐私边界的一部分（必须存在）

仓库根 `.gitignore` 至少包含：

```gitignore
data/
.venv/
.env
*.pyc
__pycache__/
.pytest_cache/
.ruff_cache/
data/app.db*
data/files/
data/exports/
data/imports/
data/logs/
```

理由：`data/imports/` 里已有**用户真实简历原件**（中文单页 + 英文双页含照片），属于个人隐私。这些文件既不能进 Git，也不能进 LLM 上下文（见 §5.4）。验收：`git check-ignore -v data/app.db .env` 均命中（AC-LOC-05）。

> ⚠️ **当前状态（2026-10-23）**：工作区**尚未 `git init`**，而 `resume-warehouse/.env`（含 `LLM_API_KEY`）与 `data/imports/*.pdf` 已存在于磁盘。因此顺序必须是：**先落 `.gitignore` → 再 `git init`/首次 `add`**。一旦误提交，`.env` 的 key 与简历原件就进入历史，`--amend` 也未必救得回来（还要 `filter-repo` + 立刻轮换 key）。这条是交付前的硬门，不是文档建议。

---

## 5. 离线边界（这是本项目的安全核心，必须可验证）

### 5.1 出网：上行与下行两个通道（构造性保证）

**「唯一上云出口」的准确含义是「唯一能把用户数据发出去的出口」，不是「全项目只有一处网络调用」。** 用户已授权默认允许抓取公司官网与招聘页（只取公开文本、不携带用户数据），因此网络按**方向**拆成两个互不重叠的通道：

| 通道 | 唯一模块 | 允许做什么 | 严禁做什么 |
|---|---|---|---|
| **上行（携带用户数据）** | `app/adapters/llm_client.py` | 向 `LLM_BASE_URL` 发送 consent 清单 `fields[]` 覆盖的片段 | 任何其他 host；任何未脱敏的姓名/电话/邮箱/照片（**学校名不在此列**，见 §5.4） |
| **下行（只取公开网页）** | `app/adapters/fetch_client.py` | `GET` 公司官网/招聘页，取 HTML → bs4 抽正文 | 携带**任何**用户数据（请求体恒空，URL 里也不放姓名/邮箱）；登录态与付费墙；跳到白名单外域名；访问内网地址 |

- **静态闸门（可执行）**：只有这两个模块允许 `import httpx`。`app/services/*`、`app/api/*` 一律不得 import 任何 HTTP 客户端。验收：`grep -rn "import httpx" app/` 的行必须全部落在 `adapters/llm_client.py` 或 `adapters/fetch_client.py`。**注意判定口径**：AC-PRIV-10 / supervisor BLK-1 约束的是「**非 `llm_client` 的上行外发**」（是否携带用户数据），不是「任何非 `llm_client` 的网络调用」——否则 t7 的抓取需求照做即违规。
- **上行运行层**：`egress_guard.assert_llm_allowed(url)` 每次请求前校验 scheme ∈ {http,https} 且 host == 当前 `LLM_BASE_URL` 主机名（自建网关即 `127.0.0.1`），否则 `EGRESS_BLOCKED`(403)。白名单由配置**自动推导**，不设手写域名变量。
- **下行运行层**：`fetch_guard.assert_fetch_allowed(url)` 三重校验 —— ① scheme ∈ {http,https}；② host 命中「目标公司官网域名」或内置招聘站表（`config.py`：`*.zhipin.com`、`*.lagou.com`、`*.liepin.com`、`*.51job.com`、`*.linkedin.com`、`jobs.bytedance.com` 等，可被设置关闭）；③ 解析出的 IP 不得为私有/回环/链路本地（防 SSRF）。跳转逐跳校验，超 3 跳放弃。
- **下行开关**：`app_setting.allow_web_fetch`（默认 **true**，用户可关）。关闭后抓取端点直接 `EGRESS_BLOCKED`(403) `details.reason="fetch_disabled"`，其余功能不受影响；抓取失败一律降级为「仅用用户粘贴的 JD 文本」（§6 D15）。

| 层 | 约束与证据位置 |
|---|---|
| 审计层（上行） | 每次出网写 `data/logs/llm-egress.jsonl`：`{ts, request_id, provider, host, path, model, field_names[], payload_bytes, est_tokens, preview_id, ok, http_status, latency_ms}`。**不记录任何正文内容**——只有字段名。 |
| 审计层（下行） | 每次抓取写 `data/logs/fetch-egress.jsonl`：`{ts, host, path, http_status, bytes, from_cache, ok, error}`。**请求体恒空 → 结构上不可能带出用户数据** |
| 前端层 | 页面不加载任何外部资源：无 CDN、无 Google Fonts、无远程图片、无 `<script src="http...">`。CSP 由 Flask 注入：`default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; font-src 'self'`。 |
| 依赖层 | 无自动更新、无遥测、无崩溃上报。零新依赖。 |

### 5.2 发送前明示（consent 协议，服务端强制）

这是「UI 明示字段清单」从口头承诺变成**机器可验证**的关键设计：

1. 前端调 `POST /api/v1/llm/preview`，body 说明 `purpose`（`jd_analyze` / `bullets_generate` / `company_profile` / `build_suggest`）与该用途**用户显式选中**的片段 ID 列表（`package_ids` / `variant_ids` / `jd_id` 等）。
2. 服务端 **只**用这些 ID 从库里取内容，构造 payload，落 `llm_preview` 表，返回：
   - `preview_id`、`payload`（**这就是将要发出的完整 JSON，逐字**）、`fields[]`（每个字段的 `path`/`label`/`chars`/`source`）、`est_tokens`、`redactions[]`、`expires_at`。
3. 前端必须把 `fields[]` 渲染成清单（勾选视图，不可编辑正文），用户点「确认发送」。
4. 前端调 `POST /api/v1/llm/complete`，**必须**携带 `preview_id`。服务端校验：存在 → 未过期（600 s）→ 未被用过 → 当前 payload 哈希 == 预览时哈希。任何一项失败：`LLM_CONSENT_REQUIRED`(428) / `LLM_CONSENT_EXPIRED`(410) / `LLM_CONSENT_MISMATCH`(409)。
5. **不存在**任何「跳过 preview 直接调 LLM」的旁路：`llm_client.send()` 的签名强制要求已消费的 preview 对象。**整包（package 全文）永不自动上传**：payload 只由显式选中的 variant 文本 + 结构化字段组成；`package.summary` 也必须被显式选中才进入 payload（preview 的 `fields[]` 会标出来源）。

### 5.3 Provider 预设与切换

**`.env` 只有一套 LLM 变量（provider 无关，切 provider 只改变量值，不改变量名）**。`resume-warehouse/.env`（`chmod 600`，必须被 `.gitignore` 忽略——见 §4.6）目前已按此命名落盘：

```dotenv
LLM_PROVIDER=deepseek              # deepseek | openai_compatible | off（不支持 ollama，见 ADR-17）
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat            # 常规任务：改写措辞/打包/短分析
LLM_MODEL_ANALYSIS=deepseek-chat   # 重推理：JD 需求分析、公司偏好、匹配打分（可指更贵的模型）
LLM_API_KEY=                       # 缺失时 key_set=false，LLM 端点返回 LLM_NOT_CONFIGURED
LLM_TIMEOUT_SECONDS=90
LLM_MAX_RETRIES=2                  # 单次调用内部重试上限（连接级与 HTTP 级共用此上限；实测需 2 次才能把 1/12 的握手失败率压到 0，见 §5.5 F1）
APP_PORT=8765
DATA_DIR=./data
```

| provider | `LLM_BASE_URL` | `LLM_MODEL` 默认 | key | 备注 |
|---|---|---|---|---|
| `deepseek`（默认） | `https://api.deepseek.com/v1` | `deepseek-chat` | `LLM_API_KEY` | OpenAI 兼容 |
| `openai_compatible` | 自定义（网关/vLLM/one-api） | 自定义 | `LLM_API_KEY` | `LLM_BASE_URL` 必填 |
| `off` | — | — | — | 全部 LLM 端点返回 `LLM_DISABLED`(503)，系统退化为纯手工/启发式模式 |

> **`provider=off` 是「零出网」硬保证（v1.17 补记，T-5）**：`off` 下 `complete()` **不得发出任何上游请求——包括用户已经确认过 consent preview 的那次调用**。
> 理由：consent 授权的是「把这些字段发给这个 provider」，而 `off` 的语义是「现在不发任何东西」；两者冲突时以 `off` 为准，**不能因为预览已确认就把请求放出去**（曾实测到 `complete()` 在 `off` 下仍发请求 → 已修为硬拦 503）。
> 判据：`provider=off` 时对 `/llm/preview` 之后紧跟 `/llm/complete`，要求 ① 两次都回 `LLM_DISABLED`(503)、② `llm_call_log` 零新增、③ `outbound_calls == 0`（`httpx` 计数器与 `llm-egress.jsonl` 双证）。

- 变量名固定为 `LLM_*` 一套：**不要**再引入 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` 这类按 provider 分裂的变量（切换 provider 会漏配，且 `key_set` 判定会歧义）。
- `LLM_MODEL_ANALYSIS` 缺失时回退 `LLM_MODEL`；`LLM_TIMEOUT_SECONDS` 是总预算，内部按 connect 5 s / read ≤ 总预算分配。
- `DATA_DIR` 只做解析与校验（必须解析到 `resume-warehouse/data/`），**不允许**指向项目外。

- 切换只改 `.env` 或 `PUT /api/v1/settings`（写入 `.env`，`chmod 600`）；`GET /api/v1/settings` **只返回** `provider/model/base_url/key_set:true|false/timeouts/allowed_hosts`，**绝不返回 key 的任何片段（连后 4 位都不给）**。
- 预检 `POST /api/v1/settings/provider/test`：对 base_url 发 `GET {base}/models`（OpenAI 兼容端点），5 s 超时，返回 `{reachable, http_status, model_list?, error_code?}`。**这一步本身不出网到第三方，只是到用户配置的 endpoint**，且不发任何简历内容。
- 密钥卫生：`config.redact()` 应用于日志 formatter 与所有异常消息；`httpx` 的 `headers` 在日志里替换为 `{'Authorization': '***'}`。启动时扫描日志里是否出现 `sk-` 前缀并打印 WARN（AC-PRIV-06/07 的自动化依据）。

### 5.4 `data/**` 永不作为 LLM 输入（红线，可机器验证）

**规则**：`data/imports/**`（用户原始简历 PDF/DOCX）、`data/files/**`（上传原件与照片）、`data/exports/**`（历史产物）、`data/app.db` 的任何整行/整文件内容，**一律不得进入任何出网请求体**。它们只能被**本地解析**成结构化记录，再由用户**显式选中**其中片段后发送。

用户已拍板按**宽路径**实施，并在 m00265 收窄了脱敏面：经历/项目文本、JD 文本、公司名与岗位名、用户备注、**学校名（真实值）**、学历/专业/届别/城市/到岗时间**可以**发到云端；只有**姓名、电话、邮箱、照片、身份证/学号永不上云**，替换为占位符后发送，**真实值只在本机渲染阶段回填**。每一项都会出现在 consent 清单的 `fields[]` 里。

> **撤销项**：`[SCHOOL]` 占位符已废除（原 v1.2 设计）。理由见 ADR-18。


**校名必须被消费（ADR-20）**：发送只是必要条件。`jd/analyze` 的响应必须含 `competitiveness{school_tier, school_signal, verdict, degree_fit, major_fit, experience_fit, gap_notes}`、`company/profile` 必须含 `school_preference{threshold, preferred_tiers, hard_filter, evidence, confidence}`、`builds/suggest` 与 `assemble` 必须含 `competitiveness_summary` 与 `school_signal_used`。只发送不判断 = 隐私成本付了、收益为零，属净损失。

**可发送（宽路径）**

| # | 来源 | 形态 | 约束 |
|---|---|---|---|
| 1 | 用户显式勾选的 `package_bullet_variant.text` / `package.summary` | 短文本（≤400 字/条） | 未勾选的不发；**必然带脱敏**（见下表） |
| 2 | 结构化字段：`position`、`company`、`lang`、`tone`、`jd.requirements` 摘要 | 标量/短列表 | 公司名与岗位名允许发送（用户明确要求分析公司偏好） |
| 3 | 用户粘贴的 JD 全文 | 文本 | 用户自愿输入，非从 `data/**` 抓取 |
| 4 | 下行抓到的公开页面正文（用户显式触发） | 文本 | 必须记 `source_url`；抓到后存 `data/files/`，**下次只读本地不再二次上云** |
| 5 | 用户备注（`notes`） | 短文本 | 同上，过脱敏 |

**永不上云（占位符脱敏，位置在 `services/llm_payload.py`，不在 UI）**

| 字段 | 占位符 | 说明 |
|---|---|---|
| `name_zh` / `name_en` | `[NAME]` | **正文里出现的姓名也要替换**（含 bullet 文本里的自称） |
| `phone` | `[PHONE]` | 含 `+86`、空格、短横线变体 |
| `email` | `[EMAIL]` | |
| 照片（`photo_path` / 任何二进制） | — | 结构上无字段可放，直接排除；`payload` 中**不得出现 base64 图像** |
| 身份证 / 学号（正则命中） | `[ID]` | |
| `data/imports/**` 原件、`data/exports/**` 产物、`data/app.db` 整行 | — | 一律不进 payload；只有被解析并**显式选中**的片段可发 |

**回填机制**：LLM 输出里会保留 `[NAME]` / `[PHONE]` / `[EMAIL]` / `[ID]` 占位符 → 入库时**原样保存**，只在 `render_html` / `render_pdf` / `render_docx` 生成最终产物时用 profile 真实值替换（同一函数也负责 ATS 文本层）。这样即使日志或产物被复制走，也不会出现姓名 + 联系方式的明文组合（校名可明文）。

**验证方式（三条，缺一不可）**
1. 单测：把含指纹串（`zhong_xudong`、手机号、邮箱）的素材灌入库 → 走 `preview` → 断言 `payload` JSON 中不含任何指纹（AC-PRIV-01）。
2. 结构：`llm_client.send()` 只接受 `ConsentGrant` 对象（含 `preview_id` + `payload_sha256`），无法直接传字符串；`llm_payload.build()` 的入参是 `variant_ids` 白名单，不是 `package_id`（避免「取整包」）。
3. 审计：`data/logs/llm-egress.jsonl` 只记 `field_names[]`，不记正文（AC-PRIV-07）。

> 结论：**「整份简历/整包上传」在本架构里没有代码路径**，不是靠自觉。任何一个新端点想直接吃 `package_id` 并出网，都会撞上 `llm_payload.build()` 的白名单签名。

---

### 5.5 上游调用约定（DeepSeek 实测，2026-10-23 —— 与本文原保守假设冲突处以实测为准）

以下四条来自 captain 的独立回归实测，**不是推测**；实现必须按这四条写，API 契约层同步见 `API-CONTRACT.md` §10.5。

| # | 实测事实 | 对实现的强制约束 |
|---|---|---|
| **F1** | 约 **1/12** 请求在 TLS 握手期失败：抛 `httpx.ConnectError`，内层 `[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1032)`，**没有 HTTP 状态码**；重试 2 次后 **12/12 成功**；强制 TLS 1.2 同样 12/12 成功 | 连接级异常按**瞬态**处理：自动重试，最多 `LLM_MAX_RETRIES`（默认 **2** → 共 3 次尝试；1 次不够，实测要 2 次才 12/12）。**握手期失败不消耗 preview 的一次性状态**（请求体根本没发出去），用户可原样重发。最终仍失败 → `LLM_UNREACHABLE`(503)，`details.kind="connect"`，**禁止**映射成 `LLM_NOT_CONFIGURED` 或 401 语义（§6 D7/D14） |
| **F2** | `response_format={"type":"json_object"}` 是**服务端硬性前置**：prompt 不含字面量 `json` 时返回 400 `Prompt must contain the word 'json' in some form to use 'response_format' of type 'json_object'`（`deepseek-chat` 与 `deepseek-reasoner` 表现一致） | `llm_prompt.build_messages()` 对每个 JSON 用途**强制注入**含字面量 `json` 的固定指令（如 `Respond with a single JSON object.`）；发送前本地断言，缺则**不发起请求**，直接 422 `LLM_JSON_MODE_PRECONDITION`（`details.reason="PROMPT_MISSING_JSON_LITERAL"`）。这是**本地前置校验失败，不是服务端错误**，绝不能把它当上游 4xx 去重试 |
| **F3** | `deepseek-reasoner` **支持** `json_object`：`max_tokens=512` → 200 + 合法 `{"ok":true}` | 原假设「reasoner 不支持 json 模式」**作废**；降级链（非法 JSON → 文本抽取 → schema 校验）保留，但理由改为「**模型可能返回非法 JSON**」。不得以「reasoner 不支持 json_object」为由关闭 `response_format` |
| **F4** | `deepseek-reasoner` 用 `max_tokens=16` → `finish_reason="length"`、`content=""`、`reasoning_content` 有内容、`completion_tokens_details.reasoning_tokens=16`（推理 token 与输出 token **共享同一预算**） | `finish_reason="length"` → **`LLM_TRUNCATED`**(502)，`details{reason:"empty_content"\|"partial_json", finish_reason, completion_tokens, max_tokens, reasoning_tokens?}`（与 API-CONTRACT §14 同源；captain 2026-10-23 裁定：截断是独立故障模式，不复用 `LLM_BAD_RESPONSE`）；空 `content` **永不入库**（不写 variant、不写 build、不写 JD 需求）；分析链路（JD 需求/公司偏好/匹配打分）`max_tokens` **≥ 2048**，生成链路 ≥ 900 |

**不做的事（避免过度设计）**
- **不默认强制 TLS 1.2**：强制 TLS 1.2 虽然也 12/12，但会永久放弃 TLS 1.3；重试已把失败率压到可忽略（0.083³ ≈ 0.06%）。保留 `LLM_TLS_MAX=1.2` 作为**故障期排障开关**（默认不设），改了要在设置页显示「已锁定 TLS 版本」。
- **不因为 F1 加长总超时**：握手失败是快失败（毫秒级），不需要更大 timeout。

---

## 6. 失败降级矩阵（每一行都要有实现与可观测信号）

| # | 失败条件 | 检测点 | 降级行为 | 用户可见信号 |
|---|---|---|---|---|
| D1 | `pip`/网络不可用 | 不检测（架构不依赖） | 启动照常 | 无 |
| D2 | Flask import 失败 | `preflight` | 启动中止，退出码 2，打印「修复指引：python3 -m venv --system-site-packages .venv」 | CLI 错误 |
| D3 | 端口 8765 被占 | 启动时 `scripts/preflight.py` | **顺延到下一个空闲端口**（8766→8799），实际端口**原子**写入 `data/runtime/app_port`（JSON 五字段，§3.3）；run.sh / DSH Skill / 启动横幅 / `/health` 统一读 `json["port"]` | 启动横幅打印**真实**地址 + UI 顶部显示实际端口。禁止静默失败、禁止让用户猜端口 |
| D4 | Songti.ttc 缺失/不可注册 | `services/fonts.py` 启动时探测 | 回退链：Songti.ttc → Arial Unicode.ttf → reportlab 内置 `Helvetica`（**纯英文可用，中文必然缺字→拒绝导出并报 `FONT_UNAVAILABLE`(500)**，绝不产出乱码 PDF） | 顶部黄条「中文字体缺失，PDF 导出已禁用」 |
| D5 | reportlab 渲染异常 | `render_pdf` try/except | 若 `chrome_fallback=true` → Chrome headless（临时 user-data-dir + 字体栈 `STHeiti, 'Arial Unicode MS'`）；Chrome 也失败 → `RENDER_FAILED`(500)，保留 HTML 预览可用 | 导出对话框显示失败原因与「改用 DOCX 导出」按钮 |
| D6 | Chrome 文本提取不一致 | `services/textcheck.py`（导出后必然执行） | 标记产物 `text_verified=false`，附 `warnings[]`；UI 显著提示「该 PDF 文本层可能影响 ATS 解析」 | 产物卡片红色角标 |
| D7 | LLM provider 未配 key / `provider=off` / **鉴权失败（401·403）** | `adapters/llm_client` + preflight | 全部 LLM 功能禁用；JD 分析走**离线启发式**（正则+词典抽技能词），变体生成走模板拼接；不阻塞任何本地功能。**鉴权失败不重试**（错的 key 重试也是错的） | 顶部灰条「AI 功能未启用：<原因>」+「去设置检查 Key」 |
| D8 | LLM 返回非 JSON / 缺字段 | schema 校验 | 重试 1 次（同一 payload、同一 preview）；再失败 `LLM_BAD_RESPONSE`(502)，保留原始文本到 `data/logs/app.log`（脱敏后）供排查 | 错误 toast + 「手动填写」入口 |
| D9 | 导入的 PDF 是扫描件（无文本层） | pdfplumber 提取字符数 < 20 | 中止导入并提示「图片型 PDF 无文本层，暂不支持 OCR」 | `IMPORT_NO_TEXT_LAYER`(422) |
| D10 | 模板槽位缺失 | `assembler` | **分层**：`required=1` 缺值 → 组装中止，422 `MISSING_SLOTS` + 定位到 block_id/slot_key；`required=0` 缺值 → **200**，渲染 `⟨slot_key⟩` 占位符 + `warnings[MISSING_SLOTS_RENDERED]`（占位符含槽位名，便于事后替换） | 预览页高亮缺失槽位；必填缺失时导出按钮禁用 |
| D11 | 命名模板非法或净化后为空 | `naming.validate` | 不导出；按具体原因返回 `NAMING_SYNTAX` / `NAMING_EMPTY` / `NAMING_UNKNOWN_VAR`(均 422)，**不得返回 §14 表外码**（旧稿的自造码已全部废除） | 输入框下方红字 |
| D12 | 磁盘满 / 权限错 | 写文件时 | `STORAGE_ERROR`(500)，不落半成品（写临时文件再 `os.replace` 原子替换） | 错误提示 |
| D13 | 进程崩溃于 job 中 | 启动时扫 `job` 表 | `running` → `interrupted`，允许用户重试 | 任务列表显示「已中断，可重试」 |
| D14 | **连接级异常**：TLS 握手失败（`httpx.ConnectError`）、`ReadError`、`RemoteProtocolError`、`ConnectTimeout`、DNS 失败（**没有 HTTP 状态码**，实测约 1/12 概率） | `llm_client` 异常分类（`NoHttpStatus` 分支） | 重试同一 payload，上限 `LLM_MAX_RETRIES`（默认 2）；**不消耗 preview 的一次性状态**；仍失败 → `LLM_UNREACHABLE`(503)，`details.kind="connect"` | 灰条「AI 服务暂时不可达，可重试」+「重试」按钮；本地功能不受影响 |
| D15 | **下行抓取失败**（无网络 / 403 / 超时 / 白名单外 / 用户关闭 `allow_web_fetch` / 正文过短像 SPA 空壳） | `adapters/fetch_client` | 最多 1 次重试；仍失败即**降级**为「仅用用户粘贴的 JD 文本」继续分析；`warnings` 记 `FETCH_UNAVAILABLE` + `reason`；**不阻塞** JD/公司分析主流程 | 提示「未能抓取公司页面，已改用你粘贴的 JD」+「允许抓取」开关入口 |

> **D7 与 D14 的边界（实测要求，不要合并）**：`401/403`（key 错、余额不足）→ D7，`LLM_UPSTREAM_ERROR`，`details.http_status` 有值，**不重试**，文案指向设置页；握手失败 / DNS / 连接被拒（`details.http_status=null`，`details.kind="connect"`）→ D14，`LLM_UNREACHABLE`，**可重试**，文案是「稍后重试」。两者在 `llm_call_log` 里用 `error_code` 区分，看板上不能都显示「不可达」。

---

## 7. 关键实现约束（写给实现者，都是踩过的坑）

### 7.1 后端

1. `create_app()` 内先 `init_db()` 再注册蓝图；所有蓝图前缀 `/api/v1`。
2. 统一错误处理：任何 `ApiError` → `{"ok":false,"error":{...}}` + 对应 HTTP 状态；未捕获异常 → `INTERNAL`(500) 且**响应体不含 traceback**，traceback 只进日志。
3. `jsonify` 全部 `ensure_ascii=False`（配置 `app.json.ensure_ascii = False`），否则中文在 UI 里变 `\uXXXX`，调试体验极差。
4. 上传：`MAX_CONTENT_LENGTH = 20 * 1024 * 1024`；只接受 `pdf/docx/md/txt/html`，按扩展名 + magic bytes 双判定（`%PDF`、`PK\x03\x04`）。
5. 绝不在请求线程里跑长任务：>2 s 的操作落 `job`，返回 `202 {job_id}`。
6. 第三级降级（若 Flask 真的不可用）：`app/server_fallback.py` 用 `http.server.ThreadingHTTPServer` 实现 `/healthz` + 只读列表。写进代码但默认不启用，仅 `RESUME_WAREHOUSE_BACKEND=stdlib` 时使用。

### 7.2 PDF/字体

```python
# services/fonts.py — 唯一字体注册点（实测可用的路径）
SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"
ARIAL_U = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
_FALLBACKS = [
    (SONGTI, 6, "STSongti-SC-Regular"), (SONGTI, 1, "STSongti-SC-Bold"),   # idx6=Regular, idx1=Bold（实测）
    (ARIAL_U, None, "ArialUnicode"),
]
```
- 必须 `pdfmetrics.registerFontFamily("CV", normal=..., bold=..., italic=..., boldItalic=...)` 并 `addMapping`，否则 `<b>` 静默失效。
- 表格单元格内的富文本必须包 `Paragraph`，否则 `<b>` 原样输出（实测）。
- 导出前文本净化：`unicodedata.normalize("NFC")`，emoji（`So` 类）→ 替换为 `""` 并写 `warnings[]`；控制字符剔除。
- A4、页边距 16–18 mm、正文 10.5 pt / 行距 15 pt、二级标题 12 pt 加粗（示例值，模板可覆盖）。
- **证件照（有照片时）**：右上角方块，**边长 == 标题区实测高度**（= 姓名行 26pt + 2pt + 两行元信息 `2 × body × leading`；11pt/1.15 时实测 **52.0pt**），上沿与**姓名上沿齐平**（`top = 上边距 8.3pt`）、右沿与**正文右缘齐平**（`right = 右边距 15.62pt`）。**不再写死 89.28pt**：用户 2026-10-23 要求「缩小一点、高度与标题高度一致」，写死常量会让中英切换后错位；历史值 89.28/3.82/9.13 仅用于量原始样张（KI-14），不用于我们自己的导出
  - **陷阱（v1.9 更正）**：曾把「页面右边距」写成 98 pt —— 98.42 其实是 `595.5 − 497.08`，即**照片左边到页右缘**的距离，与右边距不是一回事。真实右边距只有 **9.13 pt**（约 3.2 mm），照片几乎贴着页边。
  - **第二个陷阱**：`pdfplumber` 的 `im["top"]` **未按 MediaBox 归一化** —— 该样张 `/MediaBox` 下边为 `7.83`，所以 pdfplumber 报的 `-4.01` 与内容流算出的 `3.82` 矛盾；**以内容流（`cm` 矩阵 + MediaBox 原点）为准**，pdfplumber 值只能当参考。
  - 冻结值（验收引用）：`89.3 / 497.1 / 距顶 3.8 / 距右缘 9.13`（AC-PHOTO-01..02）。实测自中文样张：A4 595.5×842.2 pt，内嵌 266×266 JPEG 渲染在此方块，与姓名区并列、不重叠。
- 渲染：`preserveAspectRatio=True` 居中裁切；无照片时不得留空洞——姓名块扩到整行宽度，节距不变、页数不增（AC-PHOTO-01/02）。导出页「包含照片」开关默认**开启**。

### 7.3 前端

- 零构建：`<script type="module" src="/static/app.js">`，模块拆分 `api.js / state.js / views/*.js / consent.js`。
- 禁止 `innerHTML` 拼接用户内容（简历文本是用户可控的 XSS 载体）；统一 `textContent` 或经 `escapeHtml()`。预览 HTML 由服务端 jinja2 生成并 autoescape，前端只做 `iframe.srcdoc` 或直接跳转 `/preview/{build_id}`。
- 状态保持简单：`state.js` 里一个 `store`（对象 + `subscribe`），不引入框架。
- 所有 fetch 走 `api.js`，统一注入 `X-Request-Id`（`crypto.randomUUID()`）与错误 toast。

### 7.4 DSH Skill（`skill/`）

- `SKILL.md`：frontmatter `name: resume-warehouse`，description 说明「当用户要打包经历/导入简历/按 JD 定制简历/导出 PDF 时使用」。
- `cli.py`：薄封装，调用 `http://127.0.0.1:8765/api/v1/*`；服务未启动时打印 `run.sh` 指引（不自动启动服务）。
- Skill **不得**自己直连 LLM：所有 LLM 调用必须经过本应用（这样 consent 与审计仍然生效）。

### 7.5 中文 PDF 最终路径（结论已冻结，不再讨论）

captain 问的「PDF 出中文最终走哪条」——**已按本机实测定案**：

| 顺位 | 引擎 | 关键参数 | 实测结论 | 用在哪 |
|---|---|---|---|---|
| 1️⃣ 主 | **reportlab 4.5.1** | `TTFont("STSongti-SC-Regular", Songti.ttc, subfontIndex=6)`；Bold 用 `subfontIndex=1` | 提取文本与源文本**逐字相等**，全字符集（`·「」《》①②％±÷≠≤≥` + 罕字）全过 | 默认 `engine=auto` 首选；DOCX 同源数据 |
| 2️⃣ 备 | **Chrome headless** | `--headless=new --disable-gpu --no-sandbox --user-data-dir=<tmp> --no-pdf-header-footer --print-to-pdf=` | 能出中文 PDF；但字体栈必须是 `STHeiti / Arial Unicode MS`，用 Songti SC 时 ToUnicode 把汉字映射成**康熙部首** | reportlab 抛异常或版式过于复杂时回退；`engine=chrome` 可强制 |
| 3️⃣ 兜 | **DOCX**（python-docx） | — | 无 PDF 引擎也能交付，ATS 友好 | `engines.reportlab.ok=false && chrome.ok=false` 时 UI 默认切 DOCX |
| ❌ 弃 | **soffice** | `/opt/homebrew/bin/soffice` | **崩溃无产物**：`com::sun::star::deployment::DeploymentException` + `Signal 6` | 永久排除，不写重试逻辑 |
| ❌ 弃 | **weasyprint** | — | import 即 `OSError: cannot load library 'libpango-1.0-0'` | 永久排除 |
| ❌ 弃 | **`UnicodeCIDFont("STSong-Light")`** | — | 可出 PDF，但 `·`(U+00B7) 丢字 | 永久排除（这是最容易踩的「看起来能用」的坑） |

**双保险**：无论走 1️⃣ 还是 2️⃣，导出后都跑 `verify_text`（pdfplumber 抽取 → 去空白 → 与源文本比对）；差异率 >2% 时 `build_artifact.text_verified=0` + `warnings_json` 追加 `{code:"TEXT_LAYER_MISMATCH",count}`（字段名统一为 `text_verified`：1=通过 / 0=不通过 / NULL=未校验），UI 显示红色角标并建议改 DOCX。这样「字体映射悄悄坏掉」不会静默发布（ADR-09）。

---

### 7.5.1 版式密度 `density`（冻结；取自用户原件实测，D-38）

**结论先行**：通用模板常用的 15–20 mm 边距**不适配这份简历**。用户原件是 **5 mm 级**密度——同一份内容按通用边距排版会从 1 页变 2 页，对用户是可见退步。故默认 `density="original"`。

实测依据（`data/imports/sample_zh.pdf`，pdfplumber，2026-10-23 04:5x，**实测等级**）：

| 项 | 实测值 |
|---|---|
| 纸张 | 595.50 × 842.25 pt（A4） |
| 页边距 | 左 **14.83**、右 **15.62**、上 **8.26**、下 **16.38** pt |
| **正文内容高度** | **817.61 pt（288.4 mm）** |
| **版心宽** | **565.05 pt（199.3 mm）** |
| 正文最小字号 | **10.0 pt**（标题 11–22 pt） |
| 抽取字符数 | **1,748**（`extract_text()` 去换行；captain 报 1,707，方法差异，见 §7.5.2 证据等级） |

**两档密度（契约常量，唯一来源）**

| 参数 | `density="original"`（**默认**） | `density="relaxed"` |
|---|---|---|
| 上 / 下 / 左 / 右 边距 | **8.3 / 16.4 / 14.8 / 15.6 pt** | 16 / 16 / 15 / 15 mm（45.35 / 42.5 pt） |
| 可用高度 | **817.65 pt** | **751.5 pt** |
| 版心宽 | **564.9 pt** | **510.5 pt** |
| 目标 | **单页，正文 ≥ 10.0 pt** | 允许 2 页（发 `PAGE_OVERFLOW_TWO_PAGES`） |
| 字号阶梯（字/p 行距比） | **11.0/1.15** → 10.5/1.15 → 10.0/1.15 → 9.5/1.15（末档=紧急档，见规则 7） | 同左 |
| 行距比 `leading_ratio` | **1.15**（11 pt ⇒ ≈12.65 pt 行距；原件实测 12.0 pt / 11 pt ≈ 1.09，留 5% 余量） | 同左 |

规则：

1. **降档必须留痕**：每次降档发 `PAGE_FIT_DOWNGRADED`，`details{from_pt, to_pt, used_height_pt, available_height_pt, reason:"single_page_fit"}`；前端有可见提示。**不得静默降档**。
2. **三档都装不下** → 允许第 2 页 + `PAGE_OVERFLOW_TWO_PAGES{pages, overflow_pt, suggestion:"精简要点"}`；此时**不再降字号**。
3. **反作弊下限**（任何人「为了塞进一页」都不许越过）：正文**中位字号 ≥ 10.5 pt**、**行距比 ∈ [1.10, 1.25]**、边距不得小于 `original` 档（8.3/14.8 pt）。越线即为**规格违规**，不是「优化」。
   - 中位字号与行距比**都必须从产物 PDF 逐字符量出来**（pdfplumber `chars` 的 `size` 中位数、相邻行基线差中位数），不许读代码常量自证。
   - **两组必须同时成立**：*内容不减 + 字号达标 + 单页*。为让字号达标而裁条目数 / 删要点 ⇒ **FAIL**（条目数与 `build.selections` 的 `variant_ids` 总数逐条比对）。
4. **照片边长不随版式参数缩放**：它由标题区高度决定（`photo_box(body_pt, leading_ratio)` = `26 + 2 + body*ratio*2`），正文尺寸定了它自然就定；距顶 = 上边距、距右 = 右边距。**不得为凑版式单独改照片**。
5. 上述数值**只有这一处**（契约侧）。代码里出现第二份常量即视为漂移：`grep -rn "89.28\|817.6\|565.05" server/`。
6. **别用「内容高度直接减纸张高度」算溢出**——那会漏掉上下边距（uier 的 15 mm 结论就是这么少算了一个减法）。正确算式：`overflow = content_height − (page_height − margin_top − margin_bottom)`。

7. **首档必须是 11 pt：可用高度核算（这就是依据，不是拍脑袋）**
   ```
   available_height = 817.65 pt                    （original 档契约常量；pdfplumber 实测内容高 817.61，取整）
   正文行高          = 11.0 pt × 1.15               = 12.65 pt
   52 行正文（含条目头；条目头单行后每条目只占 1 行）= 52 × 12.65 = 657.8 pt
   章节间距（5 节 × 8 pt 上距 + 2 pt 下距 + 1pt 分隔线）≈ 120 pt
   ──────────────────────────────────────────────────
   合计 ≈ 777.8 pt  <  817.65 pt   ⇒  余量 ≈ 40 pt，单页成立、无需降档
   ```
   11 pt/1.15 在 `original` 档**装得下**。所以「9.5 pt + 1.45 行距」不是被内容逼出来的，是**版式效率低**：行距比原件多 33%，且条目头被拆成 2–3 行 ⇒ 正文行数从 33 涨到 45、垂直占用从 ≈396 pt 涨到 ≈621 pt。
   **降档只允许发生在装不下时**（规则 1），且每档都发 `PAGE_FIT_DOWNGRADED`。

8. **条目头必须条目内单行**：`org · role …… 日期` **同行渲染**，日期列宽度动态取 **12%–22% 版心**（`0.12 × 564.9 ≈ 67.8 pt` 到 `0.22 × 564.9 ≈ 124.3 pt`，按日期串实测宽度取，命中区间即可）；只有日期串超长时才允许 `role` 换行，**不得**把 `org`/`role`/日期各占一行。
   - 机器判据：任一条目头的渲染行高 > 1 行（纵向跨度 > 1.6 × 行高）⇒ 该条目记为超行；全文档超行条目数必须为 **0**（`density=relaxed` 同样适用）。
   - 这条是「33 行 vs 45 行」差距的主因：条目头从 2–3 行压回 1 行，正文行数才有机会回到原件量级。

9. **9.5 pt 是紧急档**：只有 11.0 → 10.5 → 10.0 三档都装不下才允许，且**必须同时**报 `PAGE_FIT_DOWNGRADED`（含 `from_pt/to_pt`）**与**降档原因码（`PAGE_OVERFLOW_TWO_PAGES` 或 `reason` 中写明三档均失败）。9.5 pt 单独出现而无降档链 ⇒ **规格违规**。

### 7.5.2 证据等级纪律（对他人测量值的引用）

`docs/` 内引用非本方实测的数字时，**必须标注证据等级**：

| 等级 | 含义 | 能否作 PASS/FAIL 依据 |
|---|---|---|
| **实测** | 本机命令产出、附命令与输出 | ✅ 可以 |
| **估算** | 设计期在浏览器里量的、或按经验推的 | ❌ 只能作方向参考 |
| **未验证** | 未跑过，只有推断 | ❌ 不得写进判据 |

具体：`docs/DESIGN.md §12.4` 那组 px 值是 uier 在 Chrome 临时页面量的**估算值**，且 `web/preview.html` 里的样张是精简版（复量只到 563–738 px）。**真实基线由 t8 首份 PDF 产生**——t8 之前任何基于 px 的断言都只能是「估算」，不得作为验收依据。

### 7.6 简历内容结构约束（用户裁决，2026-10-23）

四条裁决会反复被后人"优化"掉，写成硬约束：

1. **荣誉不单独成节**：留在「校园活动」下，作为**可选 bullet**（默认显示；投研究岗时可单独拎出到该节内），**不新增 section**。
2. **小象超市那条不分竞赛**：仍按 `项目经历` 归类（`bound_package_kind=project`），不因"看起来像竞赛"改分类。
3. **主修课程默认全留**：`trim_courses` 是**可选开关，默认 `false`**。开启时输出必须保留「主修课程：」前缀与**至少 3 门**课，且**裁剪前后条目数差异写进 build 的 `warnings[]`**（用户要能看出被裁了，见 AC-SKILL-04）。
4. **职业技能不拆 tag**：渲染管线只读 `skills_json[].line`（逐字原文），matcher 只读 `tokens`，**两者不得互相污染**。PDF/预览/HTML 里不得出现 ` | ` 分隔的 tag 块或标签云。细则见 DATA-MODEL §1.1，决策见 ADR-19。

**基线四要素（v1.16 增，任何「现状是 X」都必须同时给出）**：三方（captain / supervisor / 我）报基线时必须凑齐这四项，否则彼此看到的可能不是同一个运行实例。

| 要素 | 取法 | 为什么必须 |
|---|---|---|
| **运行实例** | `data/runtime/app_port` 的 `pid` + `started_at` | 同端口旧进程 vs 新进程会给出完全不同的结论（本项目已因此误判 `job_id`/`PHOTO_DETECTED`） |
| **代码版本** | `health.data.build.id`（形如 `b8c335e-dirty` / `src-<12位>`） | 唯一能回答「进程跑的到底是不是当前代码」（D-27） |
| **源码新鲜度** | `ls -ltT server/**/*.py \| head -3` 的最新 mtime，与上面 `started_at` 比对 | **若最新 mtime 晚于 `started_at`，结论一律作废**——你这台机器上正在改代码（本项目已发生 3 次「报缺陷时它已被修」） |
| **数据状态** | `health.data.db.schema_version` | 迁移会改行为；不是契约常量，但能区分「两份不同的库」 |

> 取数路径务必用 `health.data.*`（**不是**顶层，见 API-CONTRACT §2）。

## 8. 决策记录（ADR 摘要）

| ID | 决策 | 理由一句话 |
|---|---|---|
| ADR-01 | Flask 而非 FastAPI/stdlib | Flask 已装实测可跑；FastAPI 需联网；stdlib 手写成本高 |
| ADR-02 | 裸 `sqlite3` 而非 SQLAlchemy | 单用户本地应用，FTS5 触发器与 JSON 查询直接写 SQL 更短更可控 |
| ADR-03 | reportlab 主、Chrome 备、soffice/WeasyPrint 弃 | 只有 reportlab 同时满足中文不缺字 + 文本层精确（§1.2 实测） |
| ADR-04 | venv 必须带 `--system-site-packages` | 裸 venv 里 `import flask` 失败；零安装是硬前提 |
| ADR-05 | 前端 Vanilla，不建 Node 构建链 | pnpm 缺失、npm 需联网；界面复杂度不需要框架 |
| ADR-06 | consent 用「preview_id + payload 哈希 + 一次性 + 600 s」 | 把「UI 明示字段清单」变成服务端可强制的状态机，而不是一句 UI 说明 |
| ADR-07 | `off` 作为一等 provider | 离线可用是产品承诺；无 key 时应用必须完整可用（除 AI 增强） |
| ADR-08 | 中文全文检索用 bigram 预切分 + FTS5 unicode61 | 无中文分词器依赖，仍能子串命中 |
| ADR-09 | 导出后强制 textcheck | Chrome 的 ToUnicode 污染是真实风险（实测 `高`→U+2FBC），必须用抽取文本自证 |
| ADR-10 | 文件按 SHA-256 命名 | 避免路径穿越与同名覆盖，原件名只存库 |
| ADR-11 | UserProfile 单例 + 模板变量，禁前端硬编码 | 命名格式要可配置（`{position}-{name}-{school}`），身份数据只能有一个来源，否则改名要改代码 |
| ADR-12 | 命名模板缺变量 → 422 硬失败，不产出残缺名 | 残缺文件名（`-示例大学.pdf`）在投递时会直接暴露，且无法被用户察觉；宁可挡住导出 |
| ADR-13 | `data/**` 在类型层就进不了 payload | 靠 code review 守隐私不可持续；用「入参是 variant_ids 白名单」的签名让整包上传在结构上不可能（§5.4） |
| ADR-17 | **不支持 Ollama**：provider 枚举收敛为 `deepseek` / `openai_compatible` / `off` | 用户明确「坚持 DS 路线」；本机也未装 Ollama。保留一个无法验收的档位只会让 t11 终验产生歧义，也让 preflight / 设置页 / 错误码多出一整条死路径。需要完全离线时用 `off`（全部 LLM 端点 503 `LLM_DISABLED`），本地功能零损失 |
| ADR-15 | 出网拆成**上行 `llm_client` / 下行 `fetch_client`** 两个唯一模块，而不是把全部网络锁进一个模块 | 用户授权抓公开页，但抓取绝不能与「发送用户数据」共用一条代码路径；按方向拆分后隐私闸门可精确表述为「非 `llm_client` 的**携带用户数据**外发」，两侧都能静态检查。若强行单模块，要么违背用户需求，要么让闸门退化为人工判断 |
| ADR-16 | 上云用**宽路径 + 占位符脱敏**（姓名/电话/邮箱/学校名/照片 → `[NAME]`/`[PHONE]`/`[EMAIL]`/`[SCHOOL]`），而不是「只允许发送白名单字段」 | 用户明确要按宽路径；窄路径会让 JD 定制效果差。脱敏在 payload 构造层做、回填在渲染层做，是唯一能同时满足「效果」与「身份不入云」的结构；`data/**` 仍结构性不可进 payload（ADR-13） |
| ADR-14 | 连接级异常靠重试吸收（`LLM_MAX_RETRIES=2`），**不默认降 TLS 版本** | 强制 TLS 1.2 虽同样 12/12，但永久放弃 1.3；2 次重试把残余失败压到 ~0.06%（0.083³），且顺带覆盖 DNS/连接被拒/协议中断等同类瞬态 |
| ADR-18 | **学校名改为真实上云，撤销 `[SCHOOL]` 占位符**（覆盖 ADR-16 中「校名也脱敏」的部分；ADR-16 其余不删） | 用户 m00265 最终口径。校名有分析价值（院校层次、校招节奏、届别→应届身份推断），而标识风险低（同校同届人数多，单独不足以定位个人）；姓名 + 电话/邮箱才是真正的强标识，且对分析零增益。因此脱敏名单收敛为 `[NAME]`/`[PHONE]`/`[EMAIL]`/`[ID]` + 照片不可传。**ADR-16 保留**，用于展示决策演进：先宽路径含校名 → 收窄 → 再按分析价值 v.s. 标识风险重新划界 |
| ADR-19 | **职业技能不拆 tag：展示层逐行原文 + 隐式索引层**（用户裁决 2026-10-23） | 用户原话：「HR 看到一堆 tag 不知道具体情况，会莫名其妙」。简历是给人看的成品，tag/标签云破坏可读性与规整感；但 JD 匹配需要精确 token。解法：`skills_json[].line` 是唯一渲染源，`tokens` 是派生索引、永不渲染。**理由必须留着**：否则后人会重新提议 tag 化，并把它当成「更好的匹配」的进步 |
| ADR-20 | **校名不是「允许发送」而是「必须参与判断」** | 用户明确「校名是判定是否具有竞争力的核心判定依据之一」。院校层次是校招硬门槛的主要来源（卡 985/211/双一流），直接决定是否值得投、简历往哪个方向打。**反面教训**：v1.5 让校名进了 payload，但 `jd/analyze` 的 schema 只有 `{title, company_name, requirements[], keywords[], summary}`、`company/profile` 只推理招聘偏好、`build_suggest` 没有校名维度 → 隐私成本付了、分析收益为零，属**净损失**。故 `competitiveness`（含 `school_tier`/`school_signal`/`verdict`）与 `school_preference` 升为契约必需字段，并新增 `SCHOOL_SIGNAL_UNUSED` 警告兜住「发了但没用」的回退 |
| ADR-21 | **版式密度取自用户原件，而不是通用审美默认值** | ① 通用简历模板常用 15–20 mm 边距，但**该用户原件是 5 mm 级**（实测 8.3/16.4/14.8/15.6 pt）；② 若采用通用值，同一份内容会从 1 页变 2 页——**对用户是可见的退步**；③ 故默认 `density="original"`，`relaxed` 作为可选（允许 2 页并告警）；④ 边距（≥ `original`）、**行距比 ∈ [1.10, 1.25]**、**正文字号中位 ≥ 10.5 pt** 作为**反作弊下限**写入契约，防止为凑单页无限压缩。**v1.15 改定**：原 `leading_ratio=1.45` + 首档 10.5 pt 会让产物**比用户原件小一圈**（实测原件正文 11.0 pt / 行距 12.0 pt ≈ 1.09×，我们的产物 9.5 pt / 13.8 pt ≈ 1.45×）——「更小的字 + 更大的行距 = 更挤又更小」；现改为首档 **11.0 pt / `leading_ratio` 1.15**，并把「条目头条目内单行 + 日期列 12%–22% 版心」写进契约（这条是 33 行 vs 45 行差距的主因）。**保留 ADR-17、ADR-21 的历史口径不删**。**保留 ADR-17 的历史口径不删**，本条覆盖版式默认值。 2026-10-23（captain 实测原件后改定） |

---

_D-18 附注（同一条 ADR，不另开号）_：**ConsentModal 的字段清单文案属于契约的一部分，改口径必须同步改文案**——文案与实际发送清单不一致就是隐私声明造假（实测踩到：`server/app/services/consent.py` 的 note 曾写「姓名与学校名以占位符传输」，与 ADR-18 新口径自相矛盾）。判定：`redactions[]` 与文案同源生成，文案里出现的每个字段名都必须能在 `fields[]`/`redactions[]` 里找到对应项（验收 AC-PRIV-11）。
| ADR-22 | **字号下限不是「越小越能装」，版式效率优先于压缩** | ① 首版把 `leading_ratio` 设为 1.45、首档 10.5 pt，产物实测正文 9.5 pt / 行距 13.8 pt、45 行、垂直占用 621 pt；用户原件是 11.0 pt / 12.0 pt（≈1.09）、33 行、396 pt。② 同为 A4 单页，**小字 + 大行距 = 视觉更差且更占空间**：9.5 pt 下限被触发不是内容装不下，而是行距浪费 33% + 条目头拆成 2–3 行。③ 改为 11.0 pt / 1.15 后用可用高度算式核算 ≈778 pt < 817.65 pt，单页成立。④ 口径：**降档只能由「装不下」触发**，反作弊下限改为「中位字号 ≥10.5 pt、行距比 ∈[1.10,1.25]」，并加反向断言「不得靠裁内容换字号」。⑤ 教训：常量从「通用审美」取值必然偏离用户原件——**先量原件，再定常量**。 |


## 9. 已知问题清单（实现时必须带着这些前提写）

| 编号 | 已知问题（实测） | 对实现的要求 |
|---|---|---|
| KI-01 | 英文样张 `data/imports/sample_en.pdf` 抽取文本含 **16 处 `(cid:127)`**（Symbol 项目符号，ToUnicode 表缺失），全部紧邻 bullet 行首 | 视作列表标记：剥离正文、该行标 `list`；`warnings` 记 `CID_GLYPH_MISSING{count:16}`。**不得**当缺字报错、不得让 `(cid:127)` 字面量进 draft |
| KI-02 | Chrome + Songti SC/Hiragino 渲染后，抽取文本变康熙部首（`高`→U+2FBC、`工`→U+2F2F，`"高级工程师" in text == False`） | Chrome 回退时字体栈锁 `STHeiti, Arial Unicode MS`；导出后必跑 textcheck |
| KI-03 | `soffice --headless --convert-to pdf` 崩溃（`DeploymentException` / Signal 6），无产物 | 永久排除，不探测、不重试 |
| KI-04 | weasyprint `import` 即 `OSError: cannot load library 'libpango-1.0-0'` | 永久排除；不要写 `try: import weasyprint` 的兜底 |
| KI-05 | 本机 11434 关闭，`ollama` CLI 与 `/Applications/Ollama.app` 均不存在；且用户拍板**坚持 DeepSeek 路线**，不做本地模型 | 早期设计曾把 Ollama 列为 provider，会误导实现与验收；**明确不做**：`providers.py` 无 ollama 分支；provider 枚举仅 `deepseek`/`openai_compatible`/`off`；预检不探测 11434；UI 无「本地模型」入口；其警告码已从 API-CONTRACT §14.1 删除 |
| KI-06 | reportlab 表格单元格里的字符串**不解析** `<b>`；未 `registerFontFamily`+`addMapping` 时 `<b>` 静默失效 | 单元格内容一律包 `Paragraph`；字体家族注册集中在 `services/fonts.py` |
| KI-07 | emoji（🚀✅）在 reportlab 渲染后抽取为 `\x00`（视觉豆腐） | 导出前按 `unicodedata.category == "So"` 剥离 + `EMOJI_STRIPPED` 告警 |
| KI-08 | 本机**无 `PingFang.ttc`**；`Hiragino Sans GB.ttc` 是 PostScript 轮廓 → `TTFError: postscript outlines are not supported` | 字体链固定 Songti.ttc(6/1) → Arial Unicode.ttf → STHeiti；不要把 PingFang 写进首选 |
| KI-09 | macOS 无 `timeout` 命令 | 所有超时用 Python 侧（`httpx.Timeout`、`socket.settimeout`），脚本不调 GNU coreutils |
| KI-10 | 裸 `python -m venv .venv` **缺 flask**（`ModuleNotFoundError: No module named 'flask'`） | `run.sh` 与文档强制 `--system-site-packages`；preflight 校验 `flask` 可导入 |
| KI-11 | **TLS 抖包**：约 1/12 请求在握手期失败 —— `httpx.ConnectError` + `[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1032)`，无 HTTP 状态码；重试 2 次后 12/12 成功 | 按瞬态处理（D14）：`connect_retries=2` 独立预算；**不得**把它当成「服务不可用」直接禁用 AI 功能，也**不得**归为鉴权失败 |
| KI-12 | `response_format=json_object` 要求 prompt 含字面量 `json`，否则 400 `Prompt must contain the word 'json' in some form to use 'response_format' of type 'json_object'`（chat/reasoner 一致） | 所有 JSON 用途由 `llm_prompt.build_messages()` 注入含 `json` 的固定指令 + 本地前置断言；触发即 `PROMPT_MISSING_JSON_LITERAL`(**本地校验失败**，零出网) |
| KI-13 | `deepseek-reasoner` 在 `max_tokens` 过小时会把预算全烧在推理上：`max_tokens=16` → `finish_reason="length"`、`content=""`、`reasoning_tokens=16` | 空 `content` 永不入库；`LLM_BAD_RESPONSE` + `details.reason="empty_content"`；分析链路 `max_tokens ≥ 2048`。不自动重试（重试同样烧预算） |
| KI-14 | **中文样张 1 页 A4（595.5×842.2 pt）内嵌 1 张 266×266 JPEG，渲染在右上角 89.28×89.28 pt（x0=497.08，距顶 3.82 pt，**距页面右缘 9.13 pt**），与姓名区并列** | 导入时用 pdfplumber `page.images` / pypdf 抽内嵌图 → 落 `data/profile/` 作为**候选**照片（`photo_source=imported` 只在用户确认后写库）；渲染按 §7.2 的尺寸与位置 |
| KI-15 | 公司官网多为 SPA 或反爬：抓回的 HTML 正文可能 < 200 字符（导航/脚本壳） | 正文长度 < 200 字符视同抓取失败 → 按 D15 降级，不得拿空壳去喂 LLM 分析 |

> 这 15 条不是「将来可能」，是**本机已复现**。实现时如果发现自己在写绕过它们的兜底逻辑，先回来看这一节。

---

## 10. 文档与契约的权威顺序

出现冲突时按此顺序裁定，**不要自行发挥**：

1. `docs/API-CONTRACT.md` —— 端点/字段/错误码（前后端唯一联调契约）
2. `docs/DATA-MODEL.md` —— 表结构与不变量
3. `docs/ACCEPTANCE.md` —— 验收口径（判定「做完没有」只看这里）
4. `docs/ARCHITECTURE.md` —— 选型/边界/降级（本文）
5. `docs/DESIGN-BRIEF.md` —— 界面与交互

变更流程：任何字段/端点改动 → 先改 1 或 2 → 在 `API-CONTRACT.md` 的「契约变更记录」加一行 → 同步 3 的条目。禁止「代码先改、文档后补」。
