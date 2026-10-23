# awesome-dsh-plugin 目录条目（提 PR 用）

`awesome-dsh-plugin` 的目录来自该仓库里的一条列表项，字段与 `https://awesome-dsh-plugin.com/plugins.json` 一致。
下面这行按现有表格风格写好，粘贴到 `tools` 分类的表格末尾即可。

| [dsh-plugin-resume-warehouse](https://github.com/Bababoooi/dsh_resume_warehouse) | 本地优先的简历仓库：经历打包成 Package、简历拆模板、JD 分析与院校层次偏好、中英双语组装、导出「岗位-姓名-学校」PDF；插件提供启动/停止本机应用并读健康的工具，数据不出本机。 | [Bababoooi](https://github.com/Bababoooi) |

提 PR 前的三条前置（缺一不可）：

1. npm 上已有 `dsh-plugin-resume-warehouse@0.1.0`（`plugin/` 目录 `npm publish --access public`）。
2. `package.json` 的 `repository` / `homepage` 与条目里的 `url` 指向同一个 GitHub 仓库（市场会做一致性校验）。
3. 仓库里有 `plugin/` 目录与可复现的 `npm test`（13 条契约测试，无需 Python、不联网）。

结构化的同一份数据在 `docs/marketplace/entry.json`，用于提交 PR 的机器可读附件或自查。
