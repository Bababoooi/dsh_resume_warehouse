# resume-warehouse · 本地简历仓库与定制生成器

> 把经历打包成可复用的「经历包」存进本地仓库，按目标岗位 JD 重新组装，导出中/英双语简历 PDF。
> **数据全部留在本机**；唯一出网动作是调用你自己配置的 LLM，且每次调用前都会先给你看「将发送哪些字段」。

A local-first resume warehouse: pack each experience into a reusable *package*, import an existing resume into a re-assemblable template, analyze a job description (including how much that employer cares about your school), then re-assemble a tailored resume and export it as a PDF — all data stays on your machine.

---

## 它解决什么问题

投简历时最痛的不是「没有经历」，而是**同一段经历要为不同岗位写不同版本**，还要手工对齐版面、核对字数、反复改文件名。这个工具把五步拆开：

| 步骤 | 你做什么 | 系统做什么 |
|---|---|---|
| 1. 录入 | 用一段话讲清楚一段经历 | 切成事实 + 多个语气/语言的**表述变体**，存成 Package |
| 2. 拆模板 | 导入现有简历（PDF/DOCX/Markdown/纯文本） | 拆成章节/条目/槽位，供后续重组 |
| 3. 看岗位 | 粘贴 JD 与公司名 | 提取技能要求、院校门槛（硬门槛还是偏好）、你的竞争力差距 |
| 4. 组装 | 选经历、选语言、选语气 | 按 JD 相关度排序，生成预览 |
| 5. 导出 | 指定文件名格式 | 渲染 A4 PDF，中文宋体 / 英文 Times，照片固定右上 89.28pt |

---

## 隐私模型（设计的第一原则）

- **不出本机**：SQLite 数据库、导入的简历原件、照片、导出的 PDF 全部在 `data/` 下，`data/` 与 `.env` 都在 `.gitignore` 里。
- **唯一的上行出口**：`server/app/adapters/llm_client.py`。所有上云请求必须经过它，且必须先创建 consent preview——界面明确列出「**不会发送**」（姓名、电话、邮箱、照片字节与哈希）与「**会发送**」（学校名、学历专业、经历文本、JD、公司名）。姓名强制脱敏且不可关闭。
- **下行另有独立出口**：`server/app/adapters/fetch_client.py`，只做 GET、只允许白名单主机、拒绝私有地址、最多 3 次跳转、可整体关闭；抓不到就降级为「只用你粘贴的 JD 文本」。
- **`provider=off` 是一等开关**：置为 `off` 后所有 LLM 端点直接 503，连已确认的预览也不会发出；导入、组装、导出、命名等本地能力**照常可用**（分析走本地启发式）。

> 校名是**故意**要发给模型的：它决定「这家公司卡不卡院校」。但发送必须换来可见结论——模型没消费校名会强制告警 `SCHOOL_SIGNAL_UNUSED`，而不是「发了但白付隐私成本」。

---

## 快速开始

```bash
cp .env.example .env && chmod 600 .env   # 填入 LLM_API_KEY

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

bash skills/resume-warehouse/start.sh     # 幂等：已在跑就不重复启动
open http://127.0.0.1:8765                # 端口占用会自动顺延，实际地址见 data/runtime/app_port
```

不想用命令行？macOS 上双击 `scripts/set-api-key.command`：安全提示粘贴 key（不回显、不进 shell 历史），写 `.env` 后 `chmod 600` 并打印指纹供你核对。

**前置条件**：Linux/macOS + Python 3.10+；中文 PDF 依赖系统里的 CJK 字体（macOS 自带 `Songti.ttc`）。缺字体时 `GET /api/v1/env` 会明确告警，不会静默出乱码。

---

## 目录结构

```
server/app/            Flask 应用：api/ 路由 · services/ 业务 · adapters/ 两个出网口 · repos/ 数据访问
server/app/schema.sql  SQLite 结构（含 FTS5 全文索引与版本化迁移）
web/                   零构建 ES modules 前端（index.html + src/pages + src/components + styles）
docs/                  契约与设计：API-CONTRACT / DATA-MODEL / ARCHITECTURE / ACCEPTANCE / DESIGN
docs/maintainers/      内部验收台账（REVIEW-CHECKLIST）与交付状态
scripts/               运维与校验脚本（preflight / run / prune / recompute / 各类 checker）
skills/                DSH Skill 包装（指针式，不复制正文，避免双源漂移）
tests/                 pytest；server/tests/ 为 unittest 风格的单元测试
```

建议阅读顺序：`docs/ARCHITECTURE.md`（选型与被否方案）→ `docs/API-CONTRACT.md`（端点、错误码、警告码）→ `docs/DATA-MODEL.md`（不变量）→ `docs/ACCEPTANCE.md`（可测条款）。

---

## 自检

```bash
PYTHONPATH=server python3 -m unittest discover -s server/tests   # 单元测试
python3 -m pytest tests -q                                       # 端到端 + 验收
python3 scripts/preflight.py                                     # 环境体检（字体 / 端口 / key 权限）
python3 scripts/check_route_parity.py                            # 文档路由 ↔ 代码路由双向对账
python3 scripts/eval/check_export_pdf.py --pdf <file> --photo     # 独立校验导出 PDF 的几何与字号
```

`scripts/eval/` 下的检查器**独立于被测实现**：只读产物、退出码 0/1/2、不 import 被测代码——避免「改常量就等于改通过」。

---

## 已知限制（诚实清单）

- **不会编造经历**：变体只在已有事实上改措辞。判定为 `satisfied` 必须有可核对证据（`matched_evidence`），没证据会降级 `partial` 并告警 `STATUS_WITHOUT_EVIDENCE`。
- **英文版依赖英文变体覆盖度**：缺英文变体的条目会诚实回退中文并给 `LANG_FALLBACK` 逐条清单，不会假装成英文。
- **单页优先但不裁内容**：字号阶梯 11.0 → 10.5 → 10.0（9.5 仅紧急档），靠版式效率而非缩字；装不下允许第二页并告警。
- 不配 LLM key 时，「分析」能力退化为本地启发式；全站仍可本地使用。

---

## 参与贡献

欢迎 issue 与 PR。改行为前请先读 `docs/API-CONTRACT.md` 与 `docs/DATA-MODEL.md`：本项目**把契约当验收依据**，改行为必须同步改文档与 `docs/ACCEPTANCE.md` 条款，否则会被拒收。

## 许可证

MIT，见 [LICENSE](LICENSE)。
