# awesome-dsh-plugin 目录条目（提 PR 用）

## 真实提交格式（2026-10 版）

目录数据在 awesome-dsh-plugin 仓库的 `data/plugins/`，**一个插件一个 YAML 文件**，README 由脚本生成——
**不要手改 README**。PR 只需要新增一个文件。

- 文件路径：`data/plugins/Bababoooi__dsh_resume_warehouse--plugins-resume-warehouse.yml`
- 内容（同 `docs/marketplace/entry.yml`）：

```yaml
url: https://github.com/Bababoooi/dsh_resume_warehouse/tree/main/plugins/resume-warehouse
name: Bababoooi/dsh_resume_warehouse#resume-warehouse
category: tools
description:
  en: 'Local-first resume warehouse for DeepSeek Harness: package your work into reusable bullets, import an existing resume into a template, analyse a job description (including the school-tier preference it implies), assemble a tailored Chinese or English resume and export a PDF named position-name-school — the bundled tool starts, stops and health-checks the local app, and nothing leaves the machine except the LLM calls you confirm.'
  zh: '本地优先的简历仓库：把经历打包成可复用的表述、把现有简历拆成模板、分析岗位 JD（含其隐含的院校层次偏好）、组装中英双语定制简历并导出「岗位-姓名-学校」命名的 PDF；自带工具负责启动/停止本机应用并读取健康状态，除你确认过的 LLM 调用外数据不出本机。'
```

## 提交前置（缺一不可）

| 项 | 状态 | 备注 |
|---|---|---|
| repo 的 `package.json` 声明 `dsh.bundle` | ✅ | 在 `plugins/resume-warehouse/package.json`（CI 只认 root 或 `packages/`·`plugins/`·`apps/` 子包，所以不能叫 `plugin/`） |
| 仓库有真实可用代码 | ✅ | Python 后端 + 13 条契约测试 |
| 仓库创建满 **1 天** | ⏳ | CI 自动检查；本项目 repo 创建于 2026-10-23T07:35:49Z，**2026-10-24T07:36Z 之后才可提交** |
| 仓库有 `dsh-plugin` topic | ✅ | 已加 |
| 描述属实、无营销词 | ✅ | 与 `index.js` 的工具名/四个动作一致 |
| npm 包 `repository` 指回本仓库 | ✅ | `dsh-plugin-resume-warehouse@0.1.1`，`repository.directory = plugins/resume-warehouse` |

## 提交流程

1. fork `awesome-dsh-plugin/awesome-dsh-plugin`
2. 新增上面那一个 YAML 文件（`data/plugins/…`）
3. 提 PR，标题形如 `Add: Bababoooi/dsh_resume_warehouse`
4. CI 会依次查：条目数 ≤3 → `dsh.bundle` → 仓库年龄 → awesome-lint 与站点构建
5. 合并后站点与 `plugins.json` 自动重建，dsh-market 里可搜到

一个 PR 最多 3 条；只改自己那一条，别动别人的 YAML。
