# DESIGN — 界面系统与六屏交互规范

> 状态：**v1.0 冻结**（2026-10-23）· owner: uier（UI/UX lane）
> 上游输入：`docs/DESIGN-BRIEF.md`（界面结构与交互契约）、`docs/API-CONTRACT.md`（数据形态、错误码、命名与 Consent 结构）、`docs/ARCHITECTURE.md` §7.3（前端约束：零构建、零外链、ES modules）。
> 本文是**实现规范**：凡是本文与代码不一致，以本文为准并修代码；凡是本文与 `API-CONTRACT.md` 的字段/错误码不一致，以 `API-CONTRACT.md` 为准并修本文。
> 配套可评审产物：`web/preview.html`（零 JS 静态设计预览，断网双击可开，含六屏、ConsentModal、A4 样张、状态对照、深色对照）。

---

## 0. 交付物地图

| 路径 | 内容 | 谁消费 |
| --- | --- | --- |
| `web/src/styles/tokens.css` | 唯一 token 来源（颜色/字体/字号/间距/圆角/阴影/动效/尺寸/z-index/焦点环） | 所有样式 |
| `web/src/styles/base.css` | 复位、CJK 排版基线、标题层级、焦点环、`.sr-only`/`.skip-link`、滚动条、工具类 | 全局 |
| `web/src/styles/layout.css` | `.app` 外壳、状态条、侧栏、顶栏、页面栅格、抽屉、响应式 | 页面骨架 |
| `web/src/styles/components.css` | 组件层（按钮/表单/徽标/卡片/表格/弹层/Toast/照片/命名/构建） | 组件 |
| `web/src/styles/print.css` | A4 导出稿版式（`.doc`）与 `@media print` | 导出预览与打印 |
| `web/src/components/*.js` | 纯展示组件（输入 props、输出 DOM，不发请求、不 import api 层） | 页面层 |
| `web/index.html` | 应用外壳（状态条 + 侧栏 + 顶栏 + 路由挂载点） | 运行时 |
| `web/preview.html` | 静态设计预览（评审用，零 JS） | 评审 / 验收 |

组件清单（`web/src/components/`）：`dom.js`、`icons.js`、`primitives.js`、`layout.js`、`package-card.js`、`import-review.js`、`jd-panel.js`、`build-parts.js`、`consent-modal.js`、`job-toast.js`、`profile-form.js`、`errors.js`、`index.js`（统一 re-export）。

---

## 1. 设计原则

1. **本地感必须一直可见。** 状态条常驻「本地 · 当前地址」；任何出网动作前必停一次（ConsentModal）。界面不假装成网页服务，它是「我电脑上的一个工具」。
2. **先看结论，再看证据。** 每屏第一眼给结论（命中率、缺几个字段、几个待核实、文件名叫什么），细节折叠在其下。
3. **颜色不是唯一信息载体。** 所有状态同时给文字：`● 已核实` / `● 待核实`、`必须/优先/加分`、置信度数字 + 高/中/低。
4. **错误要能走下去。** 每条错误 = 发生了什么 + 还能做什么 + 一个动作按钮；不打印 JSON、不显示堆栈、不暴露密钥。
5. **中文优先的排版。** 以 `-apple-system` + `PingFang SC` 起手，行高 ≥1.5，中英混排不错行，标点避头尾。
6. **零外部资源。** 无 CDN、无远程字体、无追踪；断网、`file://` 双击也能完整评审。
7. **不硬编码身份。** 姓名/学校只能来自 UserProfile；前端不得出现任何真实姓名或学校字面量，也不用 8765 之类端口字面量。

---

## 2. 信息架构

### 2.1 页面树

```
全局外壳（常驻）
├─ 状态条（34px）：本地地址 · AI 状态 · 中文字体状态 · 最近导出 · 主题切换
├─ 左侧导航（208px，可折叠 56px）
│  ├─ 工作  工作台 / 经历库 / 模板 / 目标职位 / 组装导出
│  └─ 本地数据  个人资料 / 设置
└─ 顶栏（44px）：面包屑 + 页面级动作（搜索 ⌘K / 新建）

一级页面（7 个路由，hash 路由）
├─ #/workbench   工作台：今天要做什么（3 个主动作 + 最近构建 + 库健康度）
├─ #/warehouse   经历库：Package 卡片 + 560px 右抽屉（变体编辑）
├─ #/templates   模板：列表 / 导入四步 / 区块-槽位校对
├─ #/jobs        目标职位：JD 列表 + 需求矩阵 + 公司偏好
├─ #/builds      组装导出：三栏（选择 / A4 预览 / 语言·模板·命名·照片·导出）
├─ #/profile     个人资料：UserProfile 单例（身份与命名的唯一来源）
└─ #/settings    设置：模型（DeepSeek / 关闭）、隐私红线、数据位置

全局浮层
├─ ConsentModal  出网前「将发送字段清单」（不可绕过、无「不再提示」）
└─ JobToast      右下角长任务（导出/分析/导入）进度与结果
```

### 2.2 尺寸基线

| 元素 | 尺寸 | token |
| --- | --- | --- |
| 状态条高 | 34px | `--h-status` |
| 顶栏高 | 44px | `--h-topbar` |
| 侧栏宽 / 折叠宽 | 208 / 56px | `--w-nav` / `--w-nav-collapsed` |
| 内容最大宽 | 1400px | `--w-page-max` |
| 控件高（sm/基准/lg） | 26 / 32 / 38px | `--h-control-sm` / `--h-control` / `--h-control-lg` |
| 右抽屉 | 560px | `--w-drawer` |
| 构建页左右栏 | 260 / 380px | `--w-side-left` / `--w-side-right` |
| Jobs 左列表 | 320px | `--w-side-jobs` |
| 模态 | 720px，最高 80vh | `--w-modal` |

### 2.3 导航分组与计数

- 「工作」组 5 项，顺序固定：工作台 → 经历库 → 模板 → 目标职位 → 组装导出。
- 「本地数据」组在底部：个人资料 → 设置。用视觉分组（组标签 + 上间距）而不是分割线，减少线条噪音。
- 计数只出现在 经历库（Package 数）、模板（模板数）、目标职位（未分析 JD 数）。计数为 0 时不显示，避免「0」噪音。
- 当前项：左侧 3px 主色竖条 + 文字提亮（`aria-current="page"`）。折叠态只留图标，`title` + `aria-label` 保留全名。

### 2.4 路由与状态保持

- hash 路由（`#/builds/new` 等），刷新可回到同一屏。
- 页面级过滤/选中的临时态放内存；`localStorage` 只存两件事：`rw-theme`（主题）与 `rw-status`（上次状态条快照）。**不缓存任何简历内容。**
- 页面切换不重新请求全局资源；状态条由 `rw:status` 事件更新。

---

## 3. 设计 token

### 3.1 颜色：一份深色定义

所有颜色在 `tokens.css` 用 **`light-dark(浅色, 深色)` 成对声明**，`:root { color-scheme: light dark }` 让浏览器按系统偏好取值；显式主题用 `[data-theme="light"|"dark"]`；局部对照用 `.theme-dark` / `.theme-light`。

> 这样做的好处：**深色值只有一份**，不存在「两套变量不同步、深色下漏改一处」的经典 bug。组件 CSS 只允许 `var(--…)`，禁止字面色值（唯一例外见 §3.6）。

| 分组 | token | 用途 |
| --- | --- | --- |
| 背景 | `--c-bg` `--c-bg-sunken` `--c-surface` `--c-surface-2` `--c-surface-3` `--c-surface-hover` | 页面 / 凹陷区 / 卡片 / 次级面 / 三级面 / hover |
| 描边 | `--c-border` `--c-border-strong` `--c-border-input` | 分隔线 / 强调边 / 表单边 |
| 文字 | `--c-text` `--c-text-2` `--c-text-3` `--c-text-inv` `--c-text-link` | 正文 / 次文 / 三级文（元信息）/ 反色 / 链接 |
| 主色 | `--c-primary` `--c-primary-solid` `-hover` `-active` `--c-on-primary` `--c-primary-soft` `--c-primary-soft-border` | 文字型主色 / 实心按钮 / 交互态 / 软底 / 软底边 |
| 成功 | `--c-success` `--c-success-soft` `--c-success-border` | 已核实、齐全、已连接 |
| 警告 | `--c-warn` `--c-warn-soft` `--c-warn-border` | 待确认、缺字段、已脱敏提示 |
| 危险 | `--c-danger` `--c-danger-soft` `--c-danger-border` | 错误、导出阻断、删除 |
| 信息 | `--c-info` `--c-info-soft` `--c-info-border` | 说明性 callout、系统指令来源 |
| 中性 | `--c-neutral-soft` `--c-neutral-border` | 中性徽标 |
| 交互辅助 | `--c-focus` `--c-overlay` `--c-selection` `--c-scrollbar` | 焦点环 / 遮罩 / 选中文本 / 细滚动条 |

对比度：正文与背景、按钮文字与按钮底色、徽标文字与其软底，全部 ≥4.5:1（浅深两套都验过）；纯装饰描边允许 ≥3:1。

### 3.2 排版

| 角色 | 字体栈 | 说明 |
| --- | --- | --- |
| 界面 | `--font-sans`：`-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Source Han Sans SC", "Noto Sans CJK SC", "Microsoft YaHei", "Segoe UI", Roboto, …` | 中文优先；不引外链字体 |
| 文档（中文导出稿） | `--font-doc`：`"Songti SC", "Source Han Serif SC", "Noto Serif CJK SC", "STSong", SimSun, Georgia, "Times New Roman", serif` | 与 reportlab 的宋体渲染对齐 |
| 文档（英文导出稿） | `--font-doc-en`：`Georgia, "Times New Roman", Cambria, "Songti SC", …` | 英文简历偏 Times 系；中文回退保证混排不断字 |
| 等宽 | `--font-mono`：`ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, …` | 文件路径、错误码、token 数、指纹 |

字号阶梯（`--fs-*`，px）：`11 12 13 14 15 16 20 24 30 38`。实际用法：

- `38` 只在预览页 hero；应用内最大 `30`（页面标题），其下 `24`（区块主标题）、`20`（卡片标题）、`16`（重点正文）、`14`（正文基准）、`13`（控件与表格）、`12`（元信息）、`11`（最小：徽标、计数、错误码，不用于长文本）。
- 字重：`400/500/600/700`；中文标题用 600，避免 700 在苹方上过粗。
- 字距：`--tracking-cjk: 0.01em` 仅用于标题；正文 `0`。

行高：`--lh-tight 1.3`（数字与大标题）、`--lh-snug 1.45`（控件）、**`--lh-body 1.65`（客户界面正文，契约下限 1.5）**、`--lh-loose 1.85`（阅读型说明）。

> 注意区分：这两组行高是**屏幕界面**的；A4 纸面正文行距比是另一套常量（`--doc-lh: 1.15`，契约 `leading_ratio`），见 §12.4。不要拿 1.65 去套纸张，也不要拿 1.15 去套界面。

**中英混排规则（写进 `base.css`，全站继承）**

- `line-break: normal`（不滥用 `strict` 造成中文标点稀疏）、`overflow-wrap: break-word`（兜住超长 URL/代码）、正文 `text-wrap: pretty`。
- 中文标点避头尾：`hanging-punctuation: first allow-end`（Safari/新 Chrome 生效，其它浏览器降级不影响可读性）。
- 数字与英文单词：`font-variant-numeric: tabular-nums`（表格、字数、token、百分比对齐）；英文不退化成中文字体，靠字体栈顺序保证。
- 中英文之间不加空格字符（由系统字体与标点自然处理），**不做**用 `letter-spacing` 硬撑的伪对齐。
- 禁断行位置：`.mono`、文件名、`<code>` 用 `white-space: nowrap` + 容器 `overflow-wrap: anywhere` 兜底。

### 3.3 间距 / 圆角 / 阴影 / 动效

- 间距 4px 基准：`--sp-1..13` = 2/4/6/8/10/12/16/20/24/32/40/48/64。页面内边距 `--sp-8`（20px），区块间距 `--sp-10`（32px），卡片内边距 `--sp-7`（16px）。
- 圆角：`--r-xs 4`（徽标）/ `--r-sm 6`（控件）/ `--r-md 8`（输入、按钮）/ `--r-lg 12`（卡片）/ `--r-xl 16`（抽屉、弹层）/ `--r-pill`（开关、chip）。
- 阴影三级：`--sh-1`（卡片浮起）/ `--sh-2`（抽屉、Toast）/ `--sh-3`（模态）；`--sh-paper` 专给 A4 纸张。
- 动效：`--dur-1 120ms`（hover/焦点）、`--dur-2 180ms`（抽屉、Toast 入）、`--dur-3 260ms`（模态）；统一 `--ease cubic-bezier(.2,0,0,1)`。`prefers-reduced-motion: reduce` 时全部降为 0ms 且不位移。

### 3.4 层级与焦点

- `--z-nav 10` / `--z-topbar 20` / `--z-drawer 40` / `--z-toast 60` / `--z-modal 80`。ConsentModal 永远在 Toast 之上（发送确认优先于进度）。
- 焦点环双层：`--ring: 0 0 0 2px var(--c-surface), 0 0 0 4px var(--c-focus)`，保证在卡片、软底、深色上都可见；只在 `:focus-visible` 生效，鼠标点击不出现。

### 3.5 深色模式规则

- 组件不写 `@media (prefers-color-scheme)`，只消费 token；主题切换靠 `data-theme`。
- **唯一例外**：`print.css` 里的 `.doc` 固定 `color-scheme: light` + 字面墨色（如 `#17171a`）。理由：纸张必须模拟真实导出物，深色下预览纸张变暗会误判排版与灰阶。该文件顶部有注释说明，是唯一允许字面色值的样式文件。
- 主题切换按钮在状态条最右，图标 + `title`；切换写 `localStorage.rw-theme`。

### 3.6 打印

`@media print`：隐藏状态条、侧栏、顶栏、抽屉、Toast、模态、`.no-print`；`.doc` 去阴影、去缩放，`@page { size: A4; margin: 16mm 15mm }`（与 `.doc` 内边距一致），保证「打印预览 = 导出 PDF」。

---

## 4. 布局系统

### 4.1 应用外壳

```
┌───────────────────────────────────────────────────────────────┐
│ 状态条 34px  ●本地 127.0.0.1:PORT   ●DeepSeek 已就绪  ●字体  │
├──────────┬────────────────────────────────────────────────────┤
│ 侧栏     │ 顶栏 44px  面包屑 ·················  ⌘K 搜索  动作 │
│ 208/56px ├────────────────────────────────────────────────────┤
│          │ 主滚动区  .main__scroll                             │
│  工作    │  .page（最大 1400，可 --wide/--narrow）             │
│  本地数据│                                                     │
└──────────┴────────────────────────────────────────────────────┘
```

- 只有 `.main__scroll` 滚动，侧栏与顶栏不动；页面标题随内容滚动（不做 sticky 大标题，减少占位）。
- `.page` 三档宽度：默认 1400 上限、`--wide`（列表/三栏，铺满）、`--narrow`（表单/设置，`68ch` 阅读宽）。

### 4.2 常用栅格

| 类 | 布局 | 用在哪 |
| --- | --- | --- |
| `.grid--dashboard` | 3 卡 + 左右两栏（1.4fr / 1fr） | 工作台 |
| `.split--drawer` | `minmax(0,1fr) var(--w-drawer)` | 经历库、模板详情 |
| `.split--review` | `1.5fr 360px` | 导入校对（PDF 原文 / 结构树） |
| `.split--jobs` | `var(--w-side-jobs) 1fr` | 目标职位 |
| `.split--build` | `var(--w-side-left) 1fr var(--w-side-right)` | 组装导出 |
| `.profile-layout` | `1fr 340px` | 个人资料（表单 / 命名·照片侧栏） |

### 4.3 响应式断点

| 宽度 | 行为 |
| --- | --- |
| ≥1440 | 三栏完整（构建页 260/1fr/380），侧栏展开 |
| 1360–1439 | 构建页右栏 340，卡片最小宽降到 240 |
| 1180–1359 | 侧栏默认折叠为 56；三栏仍在，预览区可横向滚动 |
| 1024–1179 | 构建页折叠为「预览 + 右栏抽屉」，Jobs 左列表变顶部横向 |
| <1024 | 显示 `.desktop-notice`：「这个工具按桌面宽度设计，建议 ≥1280 宽使用」，不做移动端适配 |

验收：**1280×800 无横向滚动**，**1440+ 三栏并排**（AC-UI-07）。

### 4.4 抽屉

- 右抽屉 560px，`--z-drawer`，遮罩 `--c-overlay`，`slide-in` 180ms。
- 结构：`.drawer__head`（标题 + 元信息 + 关闭）、`.drawer__body`（滚动）、`.drawer__foot`（动作，sticky 底部）。
- 打开时焦点移入抽屉，`Esc` 关闭，关闭后焦点回到触发卡片；抽屉内 `Tab` 循环（`trapFocus`）。

---

## 5. 组件库

### 5.1 纯展示约束（硬）

- 组件只做三件事：收 props → 返回 DOM 节点 → 调回调（`onXxx`）。**不发请求、不 import `api` 层、不读写全局状态。**
- 所有文本通过 `document.createTextNode` 进入 DOM；`dom.js` 的 `h()` 对 `innerHTML`/`outerHTML`/`srcdoc`/`html` 四个 prop **直接抛错**，从机制上满足 AC-UI-04。
- 用户内容（姓名、学校、经历、JD、公司名）只能出现在文本节点与 `title`/`aria-label` 属性值里；绝不拼进选择器或模板字符串再交给 `h()` 的 tag 参数。
- 每个交互元素要么原生可聚焦（`button`/`input`/`a`），要么显式 `tabindex="0"` + `role` + 键盘处理（见 §14）。

### 5.2 基础件（`primitives.js`）

| 组件 | 关键 props | 说明 |
| --- | --- | --- |
| `button` | `label variant size icon iconRight kbd block disabled loading type onClick` | `variant`: primary / secondary / ghost / quiet / danger / danger-ghost；`loading` 时禁用并保留宽高 |
| `iconButton` | `icon label onClick` | 必须有 `aria-label` |
| `badge` | `text tone dot` | tone: success / warn / danger / info / accent / neutral / outline |
| `chip` / `chipSet` | `label tone mono onClick onRemove disabled` | 可点 chip 渲染为 `button`；可删带 `×`（`aria-label="移除 …"`） |
| `field` | `label control required note hint error id full` | `error` 时 `aria-invalid` + `role="alert"` 文本；`hint` 是常态说明，`error` 是阻断说明 |
| `input` / `textarea` / `select` / `checkbox` / `toggle` / `segmented` / `filePicker` | 原生属性 + `onChange` | `segmented` 是 `role="radiogroup"` + 左右方向键 |
| `callout` | `tone title body actions icon` | 屏内说明；`banner` 是同结构的通栏版 |
| `emptyState` | `icon title body actions` | 「为什么空 + 怎么开始」，两个动作以内 |
| `skeleton` / `spinner` / `loadingText` / `progress` | `lines` / `value label meta` | 骨架只用于首屏结构，不用于「正在分析」 |
| `card` / `section` / `stat` / `toolbar` / `tabs` | — | `tabs` 键盘 ←/→，`role="tablist"` |
| `statusDot` | `level text` | **点 + 文案双通道**（颜色不是唯一载体） |
| `confidence` | `value` | ≥0.8 高（绿）/ 0.6–0.8 中（黄）/ <0.6 低（红），同时输出数字 |
| `kv` / `copyText` / `charCount` | — | 字数计数 `n 字`；复制按钮给「已复制」2s 反馈 |
| `modal` | `title icon meta body footer error wide expired onClose` | 返回 `.modal-layer`；**不把 Enter 当确认** |

### 5.3 领域组件

| 文件 | 导出 | 用途 |
| --- | --- | --- |
| `layout.js` | `NAV_ITEMS statusBar sideNav topBar page appShell drawer` | 外壳骨架 |
| `package-card.js` | `TONE_LABELS KIND_LABELS packageCard packageCardSkeleton packageEmpty bulletGroup variantCard bulletsEmpty` | 经历卡、按 `bullet_key` 分组的变体列 |
| `import-review.js` | `SECTION_META importSteps pdfPreview draftBanner reviewSummary structureTree sectionNode entryNode bulletRow importAnomalies reviewFooter templateCard templateEmpty slotRow reviewLayout` | 导入四步、草稿横幅、三级结构树（章节→条目→要点）、异常告警（含 CID 具体数字）、入库/放弃底栏 |
| `jd-panel.js` | `PRIORITY_LABELS jobListItem weightBar coverageRing requirementTable coverageChips companyProfile jobEmpty jobsLayout analysisSummary` | 需求矩阵、覆盖率、公司偏好 |
| `build-parts.js` | `LANG_LABELS PROFILE_FIELD_LABELS languageSwitch templateSelect pickerLeft pickRow selectSummary namingPreview photoToggle skillLine skillLines courseTrim honorToggle exportBox paperMock buildPreview buildLayout buildWarnings` | 组装导出三栏全部零件；技能整行原文 + 行级命中标记 + 课程裁剪 + 荣誉开关 |
| `consent-modal.js` | `KIND_LABELS consentFieldRow consentModal` | 出网前字段清单 |
| `job-toast.js` | `JOB_KIND_LABELS jobToast toastLayer` | 后台任务 |
| `profile-form.js` | `FIELDS MISSING_SCHOOL_MSG profileForm photoField profileNamingPreview completenessMeter` | 个人资料与照片 |
| `errors.js` | `ERROR_COPY describeError errorView` | 错误码 → 可读文案 + 动作 |

---

## 6. 六个主界面

每屏固定交代：目的 / 布局 / 交互流程 / 空态 / 加载态 / 错误态 / 键盘。截图见 `web/preview.html` 对应屏。

### 6.1 对话式录入工作台 `#/workbench`

**目的**：5 秒内知道下一步做什么；首次使用不留白屏。

**布局**：`.grid--dashboard` —— 上方三张等宽主动作卡；下方左「最近构建」（1.4fr）+ 右「库健康度」（1fr）。

**交互流程**
1. 三张卡是并列入口，不分主次：**讲一段经历**（打开对话面板，边聊边落成 Package 草稿）/ **导入现有简历**（选文件 → 进 §6.3 四步）/ **按 JD 组装**（跳 §6.4 或直接 §6.5）。
2. 「最近构建」每行：文件名（命中命名结果，`mono`）· 时间 · 状态徽标（`已导出` / `草稿` / `命名缺字段`）。点行 → 打开该构建；行尾「重新导出」直接走导出。
3. 「库健康度」四个可点数字：经历 12 条 / 表述变体 41 条 / 待核实 6 条 / 模板 3 套。点任一项跳到对应页并带好筛选。
4. 缺个人资料时，顶部出现 `ui-callout--warn`「还没填个人资料，导出会因缺少姓名/学校失败」+「去填写」。工作台本身**不**自动触发任何 LLM 调用。

**空态**：库为空时，主区换成 `.ui-empty`「还没有经历，先把一件事讲清楚」+ 两个动作（对话录入 / 导入简历），三张动作卡保留在下（学习成本）。

**加载态**：首屏用骨架（3 卡 + 3 行 + 4 数字），≤300ms 内到达则不闪骨架（延迟出现）。

**错误态**：最近构建接口失败 → 该卡内 `.ui-callout--danger` + 「重试」，不影响其它卡；状态条 AI 红点 → 「调用失败」可点进设置。

**键盘**：`⌘K` 全局搜索、`⌘S` 保存当前页、`1/2/3` 聚焦三张卡、`Enter` 进入、`J/K` 在最近构建列表上下移动。

### 6.2 Package 仓库 `#/warehouse`

**目的**：把经历当「弹药」管理：一包一条经历，包内按要点分组多种表述。

**布局**：`.split--drawer` —— 左 `.pkg-grid`（自动填充，最小 268px），右 560px `.drawer`。

**卡片内容**：标题（岗位/项目名）· 公司/组织 + 角色 · 时间区间 · `kind` 徽标（实习/项目/校园）· 已核实变体数（`● 已核实 3`）· 标签 chips · 「4 事实 · 7 变体」· 最近更新。示例包带 `is-sample` 虚线边框 + 「示例」角标。

**抽屉（详情）**：`bulletGroup` 按 `bullet_key` 分组，每组显示事实（fact）与变体横滑列（264px/张）：变体卡 = 语气徽标（结果导向/技术细节/协作领导/精简/ATS 关键词）+ 正文（可编辑 `textarea`）+ 字数 + `● 已核实/待核实` + 复制。抽屉底部：保存 / 标记已核实 / 删除。

**交互流程**
1. 点卡片 → 抽屉打开，选中卡 `is-selected`（左侧 2px 主色条）。
2. 批量选择：卡片原生 checkbox，选中后顶部出现 `.ui-toolbar`「已选 3 · 合并到新包 / 删除」。
3. 变体编辑：失焦或 `⌘S` 保存，字数实时；标记已核实需显式点击（不因编辑自动变绿）。
4. 删除：二次确认（说明「该包被 2 个构建引用，删除后构建会显示缺失槽位」）。

**空态**：`.ui-empty` + 「讲一段经历 / 导入简历」两动作 + 一行说明「示例包只是让你看看长什么样，可随时删」。

**加载态**：抽屉先骨架（标题 + 3 组变体骨架），列表保持现状不闪。

**错误态**：`CONFLICT`（该经历已被改动）→ 抽屉顶部黄条「这条经历刚被改过，请刷新后重试」+「刷新」；`404` → 关闭抽屉 + Toast「这条经历已被删除」。

**键盘**：卡片 `Tab` 聚焦、`Enter` 打开、`Space` 勾选；抽屉内 `Esc` 关闭并把焦点还给原卡片；变体列 `←/→` 横向滚动；变体卡 `⌘Enter` 保存。

### 6.3 简历导入与模板拆解 `#/templates`（导入 + 校对）

**目的**：把已有的 PDF/DOCX 简历拆成「章节 → 条目 → 要点」三级结构，**先让用户逐块确认拆得对不对，再入库**。这一页是整条链路唯一的人工关口，做不好后面全错。

**四步**：① 选择文件 → ② 解析内容 → ③ 校对结构 → ④ 确认入库。`.import-steps` 常驻，当前步高亮，已完成步可点回退（`title` 里写明「回退不会丢草稿」）。

**草稿横幅（`.draft-banner`，页面顶部常驻）**

> **这是草稿，还没有入库。**
> 改动已自动保存在本机（09:41）· 点「确认入库」后才写入经历库与模板库

- 右侧两个动作：「预览将生成的模板」「放弃草稿」。
- 卸载/离开页面不写库；`ImportJob.draft_json` 是唯一写入目标（DATA-MODEL `ImportJob`）。
- 有未保存改动时离开 → `beforeunload` 确认；已自动保存时提示「草稿已自动保存」，不弹窗。

**校对布局**：`.split--review`（左 PDF 原文 1fr / 右结构树 470px；1280 宽下退化为上下堆叠）。

- **左**：`.pdf-frame` 逐页渲染原文（服务端出图），页脚一行「第 1 页 / 共 1 页 · 21 段 · 逐字保留原文」，右上「缩小/放大」。点右侧任一块，左侧对应段落高亮（滚动到视口内）。
- **右**：异常区（`.anomaly-list`）在上，结构树（`.block-tree--nested`）在下。
- **底栏 `.review-foot`（sticky）**：左侧状态（「还有 2 处需要确认（1 段乱码字符、1 条低置信度要点）；处理完才能入库。」），右侧 **「放弃」（ghost，二次确认）** + **「确认入库」（primary）**。页头只留一个安静的「取消导入」，避免同一动作出现两次。

**结构树：三级，可编辑，全部只改草稿**

```
章节 section（教育背景 / 实习经历 / 项目经历 / 校园活动 / 职业技能）
└─ 条目 entry（公司或项目名 · 日期 · 角色）
   └─ 要点 bullet（一行一条，逐字保留原文）
```

- 章节头：折叠箭头 · 图标 · 名称 · 「N 条 · M 点」· 置信度 · 动作（**改名 / 合并到其它章节 / 加一条 / 删除**）。
- 条目头：把手 · 标题 · 日期/角色 · 置信度 · 动作（**改名 / 移到其它章节 / 拆分 / 删除**）。
- 要点行：把手 · 原文 · 「N 个数字」+ 置信度 · 动作（**编辑 / 拆成两条 / 删除**）。
- 动作按钮默认 `opacity:0`，`:hover`/`:focus-within` 显示；`@media (hover:none)` 常显；**每行必须有键盘等价操作**（`⌘↑/⌘↓` 调序，`Delete` 删除并二次确认，`⌘D` 拆分为两条）。
- 合并/移动：选目标章节后二次确认，提示「章节里的 3 条要点将一起移动，可撤销」。
- 所有改动只写草稿；「确认入库」是唯一 commit 入口。

**数字高亮（`.tree-bullet__text mark.num`）**

解析逐字保留数字，UI 把数字/百分比/量词全部标成 `.num`（主色软底 + 等宽数字），行尾给「N 个数字」计数。目的：一眼核对「数字有没有被吞」。数字数量与原文不一致时该行标 `.num-dot.is-risk` 并在异常区出一行 `NUMBER_LOST`。

**技能区 = 整行原文（用户裁决，硬）**

职业技能章节体不使用 `.ui-chip`、不做标签云、不用竖线分隔，逐行排原文：

```
数据分析类：掌握Python、R、SQL等编程语言，可独立进行数据清洗、统计分析与可视化处理
基础办公类：掌握Excel的数据透视表、VLOOKUP函数等常用工具，可以快速上手工作
AI开发类：可以借助AI Agent对重复性数据挖掘工作进行自动化，提升处理效率
```

- 行内组件是 `.skill-line`（把手 + 原文 + 可选行级匹配徽章），**文字一个字符都不改**。
- 章节头写「0 条 · 3 行」而不是「3 条」——技能不是 entry。
- 理由（写进代码注释，防止后人"优化"）：拆成 tag 会失去简历的规整感，HR 看到一堆孤立标签反而不清楚候选人具体会什么。

**荣誉：不单独成节**

荣誉/奖项挂在「校园活动」下作为**可选要点**，默认显示；行下面是 `.honor-row` 开关「显示荣誉要点」。关掉只是隐藏（经历库里的记录不删除），**不新增 section**。

**异常告警（`.anomaly-list`，不许静默通过）**

| 码 | 触发 | 文案骨架 | 动作 |
| --- | --- | --- | --- |
| `CID_UNMAPPED` | PDF 里 `(cid:127)` 等字形索引 | 「有 N 处 bullet 标记在 PDF 里是字形索引，不是文字，已按项目符号处理并剥离正文」 | 定位 / 了解详情 |
| `REPLACEMENT_CHAR` | 文本含 U+FFFD | 「有 N 个乱码字符，说明原文字形缺失；不改也能入库，但导出会带方框」 | 定位 |
| `LOW_CONFIDENCE` | 块置信度 <0.6 | 「有 N 个区块低于 0.6，建议手核」 | 定位（逐个跳） |
| `NO_SECTION` | 0 条且 0 点的章节 | 「『校园活动』没有识别到任何条目」 | 删除本章节 / 手动新增 |
| `EMPTY_BULLETS` | 条目存在但 0 bullet | 「条目里没有要点，导出后会只剩标题」 | 加一条 |
| `NUMBER_LOST` | 数字数量与原文不符 | 「这一行少 N 个数字」 | 定位 |

- 异常区永远在结构树上方，主视野可见，不折进 `<details>`。
- 全部清空后区块换成成功态「没有发现异常，可以入库」，而不是消失。
- 置信度用 `● 0.94 高` 三通道（点 + 文字 + 数字），`conf--hi ≥0.8` / `conf--mid 0.6–0.8` / `conf--lo <0.6`。

**交互流程**

1. 拖拽或点选文件（`pdf/docx/md/txt/html`）；拖拽区同时支持 `Enter`/`Space` 打开文件选择。
2. 解析中：`.ui-progress` + 「正在解析第 3/12 页」，可取消；解析在后台任务里跑（§8）。
3. 校对：改 section/entry 名、合并、拆分、换章节、删除，全部即时写草稿并显示「草稿已自动保存 09:41」。
4. 「确认入库」：名字冲突 → 黄条「已有同名模板，将保存为『…（2）』」；仍有 `REPLACEMENT_CHAR` / `NUMBER_LOST` → 阻断并高亮对应块；只有 `LOW_CONFIDENCE` 时允许带着入库，但要点确认「还有 1 条低置信度要点也会入库」。

**空态**：未上传时右侧是「还没解析出结构」空态，左栏虚线投放区 + 支持格式；从库进模板 tab 且无模板时提示「先用示例模板起个头」。

**加载态**：解析时左侧骨架页 + 右侧灰条；解析失败保留已识别部分，可「仅保存已识别区块」。

**错误态**：`IMPORT_ENCRYPTED` / `IMPORT_PARSE_FAILED` / `IMPORT_TOO_LARGE` 等按错误码给中文解释 + 「换一个文件」；拒绝时不整份丢弃。

**键盘**：进入结构树 `↑/↓` 移动、`→` 展开、`⌘↑/⌘↓` 调序、`Enter` 选中、`F2` 改名、`Delete` 删除、`⌘D` 拆分、`Esc` 退出导入并提示「草稿已自动保存」。

### 6.4 目标职位与公司分析 `#/jobs`

**目的**：把 JD 变成一张「要求矩阵」，明确「必须/优先/加分」与「我覆盖了多少」。

**布局**：`.split--jobs` —— 左 320px JD 列表（搜索 + 高亮项 + 「粘贴新 JD」虚线按钮），右详情。

**右栏结构**：标题 + 公司 + 「互联网 · 电商 · JD 1,842 字 · 分析于 09:22」→ 覆盖率环（`68%`，conic-gradient + 中心数字 + `role="img"` `aria-label`）→ 「必须项覆盖 5/7 · 优先 2/3」→ 缺口摘要「缺口集中在『SQL 窗口函数』与『A/B 实验设计』」+「去经历库补事实」→ 公司偏好卡（仅来自 JD 文本，标注「只引用 JD 原文，不做推测」）→ 需求矩阵表 → 分析来源折叠。

**需求矩阵列**：技能/要求 · 类别 · 优先级（`必须/优先/加分` 文字徽标）· 权重（进度条 **+ 百分比数字**）· 命中经历（`0 条/2 条` 或 `● 已覆盖 / ○ 缺口`）。表头支持按优先级过滤。

**交互流程**
1. 粘贴 JD → 「分析」→ **弹 ConsentModal**（发送 JD 原文 + 公司名 + 已选经历片段）→ 确认后跑任务。
2. 分析中：右栏骨架 + Toast 进度；已完成部分（公司名、字数）先显示。
3. 点矩阵行 → 高亮左列表对应经历或跳转经历库该包；缺口行给「补一条事实」入口。
4. 重新分析：覆盖旧结果前二次确认「已有分析结果，重新分析会替换」。

**空态**：无 JD 时右栏空态「粘贴第一份 JD」+ 说明「只会发送 JD 文本与公司名，不会发送你的完整经历库」。

**错误态**：`JD_TOO_SHORT` → 内联提示「JD 太短，至少 40 字」；`LLM_*` → 保留旧结果 + 顶部错误条；公司信息缺失 → 明确写「信息不足，不做推测」，禁止编造。

**键盘**：`J/K` 列表上下、`Enter` 打开、`Tab` 进矩阵、`⌘Enter` 重新分析。

### 6.5 组装与导出预览 `#/builds`

**目的**：选经历 → 看 A4 真实排版 → 选语言与模板 → 确认文件名与照片 → 导出。

**布局**：`.split--build` 三栏 260 / 1fr / 380。

- **左（选择）**：`pick-group`（实习 / 项目 / 校园），每组可「全选/全不选」；`pick-row` = 勾选框 + 标题 + 时间 + 变体数 + 上移/下移；底部 `select-summary` 固定：「已选 3 段经历 · 5 个变体」+「预计 1/2 页」（超页数变红 `is-over`）。
- **中（预览）**：`.build-preview` 顶条「中文模板 · 单页 · A4 · 第 1/1 页」+ 刷新；下方 `paperMock` 渲染真实 `.doc`（210×297mm），按语言切中/英版式，照片在右上 89.3×89.3pt。
- **右（输出配置）**：语言 → 模板 → 文件名 → 照片 → 导出。

**交互流程（含两条新增硬需求）**

1. **简历语言**（`.ui-seg`：中文 / English）。切换立即：
   - 预览重渲染为该语言版式；
   - 下方显示该语言模板所需字段的缺失清单（`name_en`、`school_en`…），齐全时显示绿字「中文 模板所需字段齐全」；
   - 有缺失 → 黄条「English 模板缺少 2 个字段：姓名（英文）、学校（英文）」+ chip 列表 +「去个人资料补齐」；**不自动回退到中文字段**，导出按钮直接禁用并说明「补齐后才能导出英文版」。
2. **模板选择**：`templateSelect` 只列与当前语言匹配的模板（中文模板 / 英文模板），右侧「管理模板」跳 §6.3。切换模板立刻重排预览，章节顺序在预览里可见。
3. **文件名**：`namingPreview` 输入 `{position}-{name}-{school}`（默认值来自 `AppSetting.naming_template`，用户可改）。**前端不拼文件名**：每次输入（300ms 防抖）调 `POST /api/v1/naming/validate`，把返回的 `filename` 原样显示在「本次文件名」。缺失变量 → 输入框 `aria-invalid` + 文件名位置显示「（命名无效，不会导出）」+ 红字「导出将因缺少学校而失败：请填写中文或英文学校名。」+「去个人资料补齐」深链。警告（`NAMING_SANITIZED` 等）用黄 chip 说明「文件名里的 `/` 会被替换为 `-`」。
4. **包含照片**（`photoToggle`，**默认开启**）：右侧缩略图 + 来源标签（`导入自简历` / `手动上传`）+「更换」。关闭时预览立刻去掉照片且版式不塌陷（`.doc--no-photo` 让姓名区右补）；**无照片时开关置灰但可继续**，提示「未设置照片，将导出无照片版本 —— 不影响继续导出」。
5. **技能与课程**（用户裁决，影响成品观感）：
   - **技能整行原文**：右栏「技能与课程」用 `.skill-lines` 逐行渲染原文，不拆 tag、不用竖线；命中 JD 时在该行下方加 `命中 JD：Python` 行级徽章（`.skill-line.is-hit`），**文字一个字都不改**。
   - **整行排序 + 一键还原**：默认保持原序；「按相关度排序」只移动整行，按钮变「还原原序」，排序状态用徽章明示，随时可逆。
   - **主修课程默认全留**（7 门）：`courseTrim` 开关「按 JD 裁剪主修课程」**默认关闭**；打开只进入「确认」态（`.course-trim__confirm`），列清「将裁掉 2 门：抽样调查、计量经济学；保留 5/7 门」，确认后才写进这份简历，**不静默裁**。经历库里的原始课程不受影响。
   - 被排除的技能行用 `.skill-line.is-off`（删除线 + 降低不透明度），文字仍原文。
6. **导出**：`exportBox` 主按钮「导出 PDF」→ 若本次调用需要 LLM（如润色）先弹 ConsentModal；否则直接 202 + JobToast。按钮下方常驻引擎信息「渲染引擎：reportlab 4.5.1 · 中文字体：Songti SC」。

**空态**：没有可选经历 → 左栏空态「先往库里放一段经历」；有经历但未选 → 预览区占位 + 「从左侧选择经历」。

**加载态**：预览首次渲染骨架（纸张轮廓 + 灰色行）；导出中按钮 `is-loading` + Toast 进度，页面其余仍可操作（但锁定本次选择）。

**错误态**：`PAGE_OVERFLOW` → 左栏摘要红字「预计 2 页，超过单页设置」+「精简变体 / 允许 2 页」；`MISSING_SLOTS_RENDERED` → 预览内橙色虚线占位块 + 顶部提示；`RENDER_FAILED` / `FONT_UNAVAILABLE` → 见 §8 与 `errors.js` 文案；命名错误 → 见上，且导出按钮禁用。

**键盘**：`Tab` 顺序 左栏选择 → 预览工具条 → 右栏（语言 → 模板 → 文件名 → 照片 → 导出）；`↑/↓` 在 `pick-row` 间移动，`Space` 勾选，`⌘↑/⌘↓` 调序；`⌘S` 保存构建；`Enter` 在文件名输入框内不提交、不导出。

### 6.6 个人资料与设置 `#/profile` · `#/settings`

**目的**：`UserProfile` 是身份与文件命名的**唯一来源**（ARCHITECTURE §4.4），这一页要让人一眼看出「改这里 = 改所有导出」。

**布局**：`.profile-layout` 左表单（1fr）+ 右 340px 侧栏（命名预览 + 照片 + 完整度）。

**表单分组**：身份（姓名中文* / 姓名英文 / 学历 / 专业）、教育（学校中文* / 学校英文 / 毕业年份）、联系方式（手机 / 邮箱 / 城市 / 到岗时间）。字段旁常驻说明：「导出中文简历时 `{name}` 取这一列」「导出英文简历时不会回退用中文校名」。

**侧栏 · 导出文件名预览**（与表单实时联动）：显示 `本次文件名`、`模板 {position}-{name}-{school}`、`✓ 命名所需字段齐全` / 缺字段红字。**缺 `school_zh` 时整卡标红 `is-blocked`**，文案固定为「**导出将因缺少学校而失败**」，并给出「去填写学校」的聚焦动作。

**照片（`photoField`）**
- 1:1 裁切框（112px 显示区，右上角 `1:1` 角标），最终渲染 **89.3×89.3pt（≈31.5mm）**、页面**右上角**、距页顶 **3.8pt**；裁切框只做方形取景提示，真正裁切在导出渲染时按 `object-fit: cover; object-position: center 20%`（避免把头顶切掉）。
- 三种状态：无照片（拖放区 + 「JPG / PNG，建议 ≥400×400」）/ 手动上传（缩略图 + 「替换」「移除」）/ 从导入件提取（显示导入候选缩略图 + 「改回这张」）。
- 交互：拖放或点选；**前端只本地预览**（`URL.createObjectURL`），上传交后端；替换前二次确认「替换后原照片会被删除」；移除后若有导入候选，回到「使用导入件里的这张」。
- 校验：非 jpg/png → 内联错误；<400×400 → 黄字「分辨率偏低，打印可能发虚」但不阻断。

**设置页**
- 模型：**两张卡 + 一个总开关** —— `DeepSeek`（默认，展示模型名与连接状态）/「高级：自定义 OpenAI 兼容地址」（折叠，展开才出现 Base URL 与模型名）；第三档 `关闭 LLM（完全不上云）`。**不出现本地模型 / Ollama 入口，也不做「检测本机模型」的提示。**
- API Key：掩码显示（`sk-••••••••`），永不显示片段，永不回填完整值；「测试连接」按钮给成功/失败一行结果。
- 隐私红线三条（只读）：`data/** 永不作为 LLM 输入`、`每次出网前必须确认字段清单`、`照片与联系方式默认不发送`。
- 数据位置：`data/` 目录路径 + 「打开目录」；备份/导出留待 v2。

**空态/加载/错误**：首次进入无 profile → 表单空 + 侧栏「填写姓名与学校后才能导出」；保存中按钮 `is-loading`；保存失败 → 顶部错误条 + 不清空已填内容；`LLM_AUTH` → 「密钥可能已过期或填错，请到设置页更新后重试」，**不建议换服务商**。

**键盘**：`⌘S` 保存；`Tab` 顺序 身份 → 教育 → 联系方式 → 照片 → 侧栏；照片拖放区 `Enter`/`Space` 打开文件选择；表单错误时焦点移到第一个出错字段并朗读错误（`role="alert"`）。

---

## 7. 隐私确认弹层 ConsentModal

**不可绕过**：任何进入 LLM 的请求，前端必须先拿到 `POST /api/v1/llm/preview` 的 `preview_id`，弹层确认后才用同一 `preview_id` 发起调用；没有「不再提示」，没有 `localStorage` 记忆勾选。

**结构**（720px，最高 80vh，头尾固定、中部滚动）：

1. 头：盾牌图标 + 「将发送字段清单」+ 一行 meta：`DeepSeek · deepseek-chat` / `api.deepseek.com` / 用途（如「定制简历生成」）/ `2,148 字 · ≈1,043 tokens` / 指纹 `8f3c1a52…`。
2. 说明 callout：「只有下面这些字段会离开本机」，并明确「其余数据（照片、完整经历库、未选中的变体、附件）全部留在本地」。
3. 字段列表 `fields[]`：每行 = 类型徽标（简历片段/系统指令/你的附加要求/JD 原文/公司备注）+ 中文标签 + `path` + 包名 + 来源 + 字数 + `≈tokens`；已脱敏行加 `已脱敏` 徽标。
4. **不会发送**（`.modal__excluded`，绿框、主视野、默认展开）：经历 `3/12` 条被选中、表述 `5/41` 条被选中、被跳过的条目名、`profile.photo_path`/`profile.phone` 等未发送字段，最后一行 note 说明「照片与手机号不会随本次请求发送；联系方式只在最终 PDF 里本地生成」。
5. **已脱敏**（`.modal__redactions`，黄底）：`value_preview → replacement ×count`，例如 `138****0000 → [PHONE]`、`陈** → [NAME] ×2`。
6. 折叠 payload（`<details>`）：等宽 `pre`，由后端脱敏后给出；默认收起。
7. 底部：左「按 Enter 不会发送」；右 `取消`（= Esc）+ `确认发送 · DeepSeek/deepseek-chat · ≈1,043 tokens`（主按钮文案自带服务商与 token 数）。

**状态**
- 过期（`expires_at` 过）：确认按钮替换为「预览已过期 · 重新生成」，点击重新 preview。
- 发送中：确认按钮 `is-loading`，不可重复点。
- 发送失败：**弹层不关**，底部红色错误条 + 错误码 + 动作（`LLM_AUTH` → 打开设置；`LLM_RATE_LIMITED` → 稍后重试）。

**键盘**：打开后焦点落在对话框（`role="dialog" aria-modal="true"`），`Tab` 在弹层内循环；`Esc` 或点遮罩 = 取消；**`Enter` 被显式拦截**（除带 `data-allow-enter` 的控件），从机制上避免「手一抖把简历发出去」。

---

## 8. 后台任务 JobToast

- 位置：右下角 `--z-toast`，最多 3 条，超出显示「还有 N 个任务在进行」。
- 每个任务卡片：类型图标 + 标题（`导出 PDF` / `分析 JD` / `导入简历`）+ 状态（`排队中` / `进行中 · 正在渲染第 1 页` / `已导出` / `失败` / `已中断`）+ 进度条 + 动作。
- `succeeded`：列出产物（文件名 + 大小 + `文本校验通过`），每个给下载。
- `failed`：`describeError` 的标题 + 一句原因 + 动作（查看诊断 / 重试）。
- `interrupted`（服务重启）：文案固定「服务重启导致任务中断，没有产生文件。」+「重新执行」——**不假装成功、不留下半份文件**。
- `cancelled`：直接收起，2s 后消失。
- 键盘：Toast 容器 `aria-live="polite"`；可聚焦到卡片内按钮；`Esc` 只收起已完成/失败的卡片，不打断进行中任务（避免误取消失）。

---

## 9. 简历语言切换

- 语言集合：`zh`（中文·中文模板）/ `en`（English·English 模板）。语言决定三件事：**版式**（`--font-doc` vs `--font-doc-en`、`text-align: justify` vs `left`、bullet 用「·」vs「•」）、**模板候选**（只列该语言模板）、**命名变量取值**（`{name}`→`name_zh|name_en`，`{school}`→`school_zh|school_en`）。
- **字段缺失提示**：切换后立刻计算该语言所需字段（`FIELDS` 子集），缺失项以 chip 列出并标「去个人资料补齐」。缺失不静默降级：**不**回退中文字段到英文模板，导出按钮禁用并说明原因。
- 缺字段不阻断预览：预览仍渲染（缺的位置留空或占位），让用户看见差别。
- 语言是构建的属性（`ResumeBuild.language`），切换会清空「已选变体中该语言不存在的项」并提示「2 个变体没有英文版本，已自动取消勾选」。

---

## 10. 文件名预览（命名）

- 默认模板 `{position}-{name}-{school}`，`{position}` 来自本次构建的岗位名，`{name}`/`{school}` 来自 UserProfile，按语言取值。
- **前端绝不自己拼**：显示的一切都来自 `POST /api/v1/naming/validate` 的 `data.filename`（该接口恒 200，合法与否看 `valid`）。
- 状态机：`pending`（防抖中，显示上一次结果 + 轻微 `aria-busy`）→ `valid`（等宽文件名 + 绿色「命名所需的个人信息齐全」）→ `invalid`（文件名位置显示「（命名无效，不会导出）」，红字错误 + 深链）。
- 错误码 → 文案：`NAMING_MISSING_VAR`（缺 `school` 等具体变量名）/ `NAMING_UNKNOWN_VAR` / `NAMING_EMPTY` / `NAMING_TOO_LONG`（超 120 字节）/ `NAMING_SYNTAX`（未闭合的 `{`）/ `NAMING_INVALID_CHARS`。警告码：`NAMING_SANITIZED` / `NAMING_TRUNCATED` / `EMOJI_STRIPPED` / `NO_VARIABLE` / `NAMING_COLLISION_SUFFIXED`，用黄 chip 显示，不阻断。
- 变量来源折叠区（`变量取值与来源`）：逐条 `{position} = 数据分析实习生`、`{name} = 陈思远（个人资料·中文）`，让用户能追溯到哪来的。
- 导出时后端用同一套校验；前端禁用导出只是提前拦截，不替代服务端校验。

---

## 11. 照片规范

| 项 | 规格 |
| --- | --- |
| 渲染尺寸 | **89.3 × 89.3 pt**（≈31.5mm 见方），正方形，等比裁切 `object-fit: cover` |
| 位置 | 页面**右上角**；距页顶 **3.8pt**；照片左边 x0 = **497.1pt**；距页面右缘 **9.1pt**（真实右边距） |
| 几何来源 | 原始 PDF 内容流反算（MediaBox `[0, 7.83, 595.5, 850.08]`，页面流 0.24 缩放 + Y 翻转 + 平移到页顶）：照片框 89.28 × 89.28pt、x0 497.08pt、距页顶 3.82pt、距页右 9.13pt；实现 token `--doc-photo-size: 89.28pt` / `--doc-photo-top: 3.82pt` / `--doc-photo-right: 9.13pt`。**注意 `98.42 = 595.5 − 497.08` 是「照片左边到页右缘」的距离，不是右边距**，不能当 `right` 偏移用 |
| 与文字关系 | 姓名区在左，照片独立在右，姓名/联系方式最多占 `页宽 - 照片宽 - 间距`；`.doc--no-photo` 时姓名区自动补回整宽 |
| 来源 | `手动上传`（在个人资料页）或 `导入自简历`（导入时检测到证件照） |
| 格式/尺寸 | jpg / png；建议 ≥400×400；<400 给黄字提醒但不阻断 |
| 发送策略 | **照片永不上传 LLM**（`profile.photo_path` 在 excluded 列表里），只在本地渲染进 PDF |
| 无照片 | 导出照常进行，版式不留空（`.doc--no-photo`），导出页开关置灰 + 说明；不阻断导出 |

预览页 `#paper` 与构建页预览都用同一份 `.doc` 结构，保证「预览即导出」。

---

## 12. A4 导出稿排版（`.doc`）

- 纸张：210×297mm；`@page { size: A4; margin: 0 }` —— **页边距不交给 `@page`**，全部由 `.doc` 的四边内边距承担（`--doc-pad-t/r/b/l`），因为原件的四边页边距不等且上边只有 8.3pt 级，`@page` 只能给对称值。屏幕与打印因此共用同一套版心。
- 版式密度两档（详见 §12.4）：`original`（默认，复刻原件页边距）与 `relaxed`（上下 16mm / 左右 15mm，允许 2 页）；导出页右栏「版式宽松度」可切。
- 正文默认 **11pt / 行距比 1.15**（契约 `--doc-body` / `--doc-leading`，对应原件实测 11pt、行距 12pt≈1.09×，留 5% 余量）/ 中文 `text-align: justify` + `text-justify: inter-ideograph`；装不下才按 §12.4 的阶梯降档（10.5 → 10.0 → 9.5 紧急档）。**行距比全档恒定 1.15**：不允许用放大行距的方式撑开版式。
- 中文版：宋体栈 `--font-doc`；章节标题 12pt 加粗 + 前置圆点 + 字距 `0.01em`；**条目头必须单行**：`org · role …… 日期` 同行基线对齐，日期列宽取版心 12%–22%（67.8–124.3pt），只有日期串超长才允许 role 换行；bullet 用「·」并悬挂缩进；技能行逐行整句（见 §12.1），不加分隔符。
- 英文版：`.doc--en` 用 `--font-doc-en`（Georgia/Times），左对齐不强行两端对齐；bullet 用「•」；`Education / Experience / Projects / Skills`。
- 页脚：一行小字（8pt，次级墨色）「保证所有信息真实，任何夸张的措辞都可追溯」；英文版用对应英文。
- 占位符 `.doc__ph`：橙色虚线框，仅用于「缺槽位」的预览态，导出时不允许出现（服务端 `MISSING_SLOTS_RENDERED` 会警告）。
- 打印：`print.css` 的 `@media print` 保证「浏览器打印 = 导出的 PDF」（打印时保留 `.doc` 四边内边距，`@page` margin 已为 0，不会叠加）。

### 12.1 技能区：整句原文逐行

- 技能**不是**标签集合，是若干整句。`.doc__skill-line` 逐行输出，行高 1.55、中文两端对齐（`inter-ideograph`）、`overflow-wrap: break-word`，不加 bullet 符号、不用 `|` 分隔。
- 典型形态（用户真实简历）：

  ```
  数据分析类：掌握Python、R、SQL等编程语言，可独立进行数据清洗、统计分析与可视化处理
  基础办公类：掌握Excel的数据透视表、VLOOKUP函数等常用工具，可以快速上手工作
  AI开发类：可以借助AI Agent对重复性数据挖掘工作进行自动化，提升处理效率
  ```

- 英文模板同构，行首类别名可译（`Data analysis: …`），但**不做词表替换**（不把 Python 换成 "Python programming"）。
- 验收口径：生成的 PDF 里技能区文本与源行**逐字相等**（含中文冒号「：」、顿号、句末无句号）。任何 UI 设计都不能让这份数据在渲染前被改写。

### 12.2 主修课程

- 默认**全部保留**（用户简历为 7 门），以一行「主修：数理统计、回归分析、机器学习导论、…」呈现。
- 「按 JD 裁剪」是**默认关闭**的可选项；用户在组装页显式打开并确认后才裁剪，裁剪结果只作用于本次构建。
- 裁剪后行尾不加「等」字（避免暗示还有未列出的课），文案改为「主修（按 JD 精简）：…」。

### 12.3 荣誉

- **不单独成节**。荣誉作为「校园活动」章节下的一条要点，默认显示。
- 用户可关掉（`.honor-row` 开关），关掉后该行不渲染、章节仍在；不产生新 section、不改章节顺序。
- 分类上不新增「竞赛」类目：竞赛/奖项一律归「项目经历」或「校园活动」（如「小象超市」这类项目归**项目经历**）。

---

### 12.4 版式密度：原件密度（默认）与宽松密度

**为什么有两档**：用户原件 `data/imports/**/*.pdf` 是一张**几乎用满整页**的 A4 —— 实测内容高度 817.6pt / 页面 842pt（288.4mm 占 297mm），四边页边距分别是 **左 14.83pt、右 15.62pt、上 8.26pt、下 16.38pt**（契约取整为 14.8 / 15.6 / 8.3 / 16.4），正文最小 10pt。也就是说它靠「5pt 级窄边距 + 10pt 正文」装进一页。设计稿若用 15mm/16mm 的常规边距，同一份内容会被挤到 319mm 高，必然掉第二页 —— 所以**默认必须复刻原件密度**，而不是套一个「好看的通用边距」。

| 密度 | `.doc` 四边内边距 | 目标 | 用在哪 |
| --- | --- | --- | --- |
| `original`（**默认**） | 上 8.3pt / 下 16.4pt / 左 14.8pt / 右 15.6pt | 单页 + 正文中位字号 ≥10.5pt | 所有导出的默认值；用户不改就是它 |
| `relaxed` | 上 16mm / 下 16mm / 左 15mm / 右 15mm | 观感更舒展，**允许排到第 2 页** | 内容少（1–2 段经历）的人，或明确不在意页数时 |

- 实现：`print.css` 用 `.doc--density-original` / `.doc--density-relaxed` 两个类切换；`@page { margin: 0 }`，页边距全部由 `.doc` 的四边内边距承担 —— 因为原件的左右上三边是 5pt / 2.9pt 级且四边不等，`@page` 只能给一套对称值，表达不了原件版式。
- 切换位置：**导出页右栏「版式松紧」**（`densitySelect`，默认 `original`）。两个选项用直白文案：**「紧凑（与原简历一致，单页）」**与**「宽松（可能两页）」** —— 不把 `original/relaxed` 这类术语暴露给用户。切换即重算「预计 N 页」，个人资料页不放这个开关（它不是身份信息）。
- 照片**不随密度变化**：89.28pt、距顶 3.82pt、距右缘 9.13pt 永远不动。原件里照片顶边（3.82pt）比上边距（8.26pt）还高，这是原件本来的样子，不要为了对称去挪。

**字号阶梯**（与密度解耦，命中即用）：

1. 默认 `11.0pt / 1.15`（契约首档）；装不下 → `.doc--compact` `10.5 / 1.15` → `.doc--tight` `10.0 / 1.15` → 紧急档 `.doc--dense` `9.5 / 1.15`。
2. **行距比四档恒定 1.15**（契约 `leading_ratio`，允许区间 [1.10, 1.25]）：降档只降字号，不放大行距——放大行距等于用空白换行数，正是「9.5pt + 1.45 行距」那次版式事故的成因。
3. **9.5pt 是紧急档**：只有前三档都装不下才允许，且必须带 `PAGE_FIT_DOWNGRADED(from_pt/to_pt)` 与失败原因；单独出现 9.5pt 无降档链 = 规格违规。
4. 每次降档必须发 `PAGE_FIT_DOWNGRADED`（`from_pt/to_pt/used_height_pt/available_height_pt`），前端可见，**不许静默降档**。
5. 仍超出就排第二页 + `PAGE_OVERFLOW_TWO_PAGES` 并提示精简要点；**不许为了塞进一页而删要点**（条目数/要点数要与 `build.selections.variant_ids` 对上）。

**证据等级（重要）**：§12.4.1 的所有 px 都是**设计期估算** —— 在浏览器里量 `.doc` 的 DOM（2026-10-23 05:05，命令在该节），不是 PDF 量出来的。真实基线以 **`data/eval/check_export_pdf.py` 对 t8 首份 PDF 的度量**为准（页数 / 字号中位数 / 相邻行基线差 / 照片 w·h·x0·距顶·距右 / 溢出字符数）。边距与字号常量取自 `docs/ARCHITECTURE.md` §7.5.1（v1.17 冻结：`original` 边距 8.3/16.4/14.8/15.6pt、首档 11.0pt/1.15、紧急档 9.5pt）——**实现与契约一致，不存在待同步的口径差**。

#### 12.4.1 设计期估算（2026-10-23 05:05 重测，可复跑）

**证据等级：设计期估算（DOM 度量），不是基线。** 真实基线由 t8 首份 PDF + `data/eval/check_export_pdf.py` 产生（页数 / 字号中位数 / 相邻行基线差 / 溢出字符数）。

样本：`web/preview.html` 的 `#paper` 中文样张（按真实拆解体量生成的虚构内容）：**1,289 字 / 5 章节 / 6 条目 / 11 条要点 / 2 段整段文字 / 47 个数字**。页高 1123px（297mm @96dpi）。

| 档位 | 正文 / 行距比 | 内容高度 | 可用高度（页高 − 上边距 − 下边距） | 结论 |
| --- | --- | --- | --- | --- |
| **默认** | **11.0pt / 1.15** | 902px | 1090px | 余 **188px ≈ 50mm**，单页宽松成立；条目头 6/6 均为 1 行 |
| `.doc--compact` | 10.5pt / 1.15 | 875px | 1090px | 余 215px ≈ 57mm（本样本用不到） |
| `.doc--tight` | 10.0pt / 1.15 | 847px | 1090px | 余 243px ≈ 64mm |
| `.doc--dense`（紧急） | 9.5pt / 1.15 | 804px | 1090px | 余 286px ≈ 76mm |
| `relaxed` + 11pt | 11.0pt / 1.15 | 977px | 1002px | 余 25px ≈ 6.6mm，本样本在宽松档也能单页 |

口径：`overflow = content_height − (page_height − padding_top − padding_bottom)`；内容高度从 `.doc` **内容盒顶边**起算（`bbox.top + paddingTop`），**不能再把 `padding-bottom` 加进内容高度**。

> 为什么现在余量这么大：上一版是 10.5pt / **1.62** 行距比，同样内容吃到 1058px；改回 11pt / **1.15** 后，字更大而垂直占用反而降到 902px —— 行距比才是主因，不是字号。这也说明「9.5pt + 1.45」既更小又更挤，属于版式效率问题，不是内容问题。

复现命令（`$PWD` = `resume-warehouse/web`；三个坑都写在注释里）：

```bash
cd resume-warehouse/web
python3 - <<'PY'
import re, pathlib
h = pathlib.Path('preview.html').read_text()
seg = h[h.find('id="paper"'):]                            # 只取 A4 样张那一段
i = seg.find('<div class="doc'); d, q = 0, i
while True:                                               # 按 <div> 深度配平取整块
    m = re.compile(r'<(/?)div\b[^>]*>').search(seg, q)     # 坑 1：正则要吃掉 ">"，
    d += -1 if m.group(1) == '/' else 1; q = m.end()       # 否则切片尾部残缺、浏览器补空 div → 量到 0
    if d == 0: break
doc = re.sub(r'\s*style="[^"]*"', '', seg[i:q], count=1)   # 去掉 .pv-paper 的 scale
HEAD = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<link rel="stylesheet" href="src/styles/tokens.css">'
        '<link rel="stylesheet" href="src/styles/base.css">'
        '<link rel="stylesheet" href="src/styles/print.css"></head>'
        '<body><div class="paper-stage">')
TAIL = ('</div><script>window.addEventListener("load",function(){'
        'var d=document.querySelector(".doc"),cs=getComputedStyle(d),b=d.getBoundingClientRect();'
        'var kids=Array.prototype.filter.call(d.children,function(k){return k.getBoundingClientRect().height>0});'
        'var last=kids[kids.length-1],padT=parseFloat(cs.paddingTop),padB=parseFloat(cs.paddingBottom);'
        'var contentH=last.getBoundingClientRect().bottom-(b.top+padT),avail=b.height-padT-padB;'
        'var fs=parseFloat(cs.fontSize),lh=parseFloat(cs.lineHeight);'
        'var heads=d.querySelectorAll(".doc__entry-head");'
        'var over=Array.prototype.filter.call(heads,function(e){return e.getBoundingClientRect().height>1.6*lh}).length;'
        'document.title=JSON.stringify({page:Math.round(b.height),contentH:Math.round(contentH),'
        'avail:Math.round(avail),over:Math.round(contentH-avail),fs:fs,lh:lh,headOverflow:over})'
        '});</script></body></html>')
for name, var in {'full': doc,
                  'compact': doc.replace('doc--density-original', 'doc--density-original doc--compact', 1),
                  'tight': doc.replace('doc--density-original', 'doc--density-original doc--tight', 1),
                  'dense': doc.replace('doc--density-original', 'doc--density-original doc--dense', 1),
                  'relaxed': doc.replace('doc--density-original', 'doc--density-relaxed', 1)}.items():
    pathlib.Path(f'a4-{name}.html').write_text(HEAD + var + TAIL)
PY
for v in full compact tight dense relaxed; do printf "%-9s " "$v"
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --no-sandbox \
    --disable-gpu --disable-crash-reporter --disable-breakpad --virtual-time-budget=3000 \
    --dump-dom --user-data-dir=/tmp/rw-chrome-a4 "file://$PWD/a4-$v.html" | grep -o '<title>[^<]*'
done
rm -f a4-*.html
```

2026-10-23 05:05 本机输出：

```
full     {"page":1123,"contentH":902,"avail":1090,"over":-187,"fs":14.6667,"lh":16.8667,"headOverflow":0}
compact  {"page":1123,"contentH":875,"avail":1090,"over":-215,"fs":14,"lh":16.1,"headOverflow":0}
tight    {"page":1123,"contentH":847,"avail":1090,"over":-243,"fs":13.3333,"lh":15.3333,"headOverflow":0}
dense    {"page":1123,"contentH":804,"avail":1090,"over":-286,"fs":12.6667,"lh":14.5667,"headOverflow":0}
relaxed  {"page":1123,"contentH":977,"avail":1002,"over":-24,"fs":14.6667,"lh":16.8667,"headOverflow":0}
```

> 坑 2：量内容高度时起点是 `.doc` 的**内容盒顶边**，可用高度是 `页高 − paddingTop − paddingBottom`；两者都按内容盒算才对得上。
> 坑 3：Chrome 必须带 `--no-sandbox` 与 `--user-data-dir`，否则在本机会在 crashpad 处失败且**不产出任何输出**，看起来像「量不到数」。

同批实测的两项几何与排版结论（**设计期估算**；照片几何真值来自 PDF 内容流反解）：

- 照片：DOM 里 100% 缩放时距页顶 3.81pt、距页右缘 9.13pt、89.28pt 见方；`.doc__header` 右侧留白 8pt 呼吸位，姓名区与照片不重叠（`headerOverlapsPhoto=false`）。
- 英文：`.doc--en` 同体量 47 行、0 个元素横向溢出；36 字符长词 `SupportVectorMachineHyperparameters` 在 `overflow-wrap: break-word` 下整词换行。

## 13. 文案规范

- 语气：**平实、具体、可执行**。不卖萌、不用感叹号、不写「赋能/闭环」。
- 按钮：动词开头（`导出 PDF`、`去个人资料补齐`、`重新执行`），不用「确定/取消」当唯一信息（确认按钮要带对象：「保存资料」「导出 PDF」）。
- 错误三段式：**发生了什么** → **还能做什么** → **一个动作**。例：
  - 「PDF 渲染失败」/「已保留中间文件供排查；这次没有产生可下载的 PDF。」/「查看诊断 · 重试」。
  - 「密钥被拒绝」/「密钥可能已过期或填错，请到设置页更新后重试。」/「打开设置」。
- 禁止：出现 Ollama/本地模型引导、API Key 片段、原始 JSON、英文堆栈、真实姓名或学校字面量、「8765」端口字面量。
- 数字统一 `toLocaleString('zh-CN')`；单位用中文（`1,043 tokens`、`89.3pt`、`2,148 字`）。

---

## 14. 无障碍与键盘

- **对比度**：正文/按钮/徽标 ≥4.5:1；装饰描边 ≥3:1；深浅两套都验。
- **非颜色唯一**：所有状态点旁边有文字（`● 已核实`、`必须`、`68%`、置信度数字）。
- **焦点**：`:focus-visible` 双层环，深色下同样可见；`skip-link` 跳主内容；抽屉/模态打开时 `trapFocus`，关闭后焦点回到触发器。
- **语义**：页面 `<h1>` 唯一；导航 `aria-current="page"`；`tabs` 用 `role=tablist/tab/tabpanel` + ←/→；`segmented` 用 `role=radiogroup` + ←/→；错误 `role="alert"`，Toast 容器 `aria-live="polite"`。
- **快捷键**（全局）：`⌘K` 搜索、`⌘S` 保存当前页、`Esc` 关闭最上层浮层、`J/K` 列表上下、`Enter` 打开、`Space` 勾选。快捷键提示用 `kbd` 元素显示在按钮右侧，且**不阻断**原生输入框。
- **拖拽替代**：所有拖拽操作（区块排序、变体排序）必须有「上移/下移」按钮；拖拽把手带 `aria-label="拖动调整顺序：{名称}，也可用上移/下移按钮"`。
- **动效**：`prefers-reduced-motion` 下 0ms 且不位移；自动播放类动效一律无。
- **表单**：每个控件有 `label`；`aria-describedby` 关联 hint/error；必填标 `*` 且 `required`/`aria-required`。

---

## 15. 离线与零构建约束

- **零构建**：无 `node_modules`、无打包器；`index.html` 用原生 `<script type="module">` + 相对路径 import；组件可用 `file://` 或静态目录直接加载。
- **零外部资源**：没有 CDN、远程字体、追踪脚本；图标是内联 SVG（`icons.js` / `preview.html` 的 `<symbol>` 表）。
- **风格分层**：`tokens → base → layout → components → print`，顺序固定；页面层（`web/src/pages/**`）只允许写页面级布局胶水，不得新增字面色值与重复组件样式。
- **API**：同源相对路径（`/api/v1/...`），端口由启动脚本决定；前端不出现端口字面量，状态条地址取 `location.host` 或后端下发的 `localUrl`。
- **预览页**：`web/preview.html` 零 JS，可直接双击打开评审；它是设计契约的可视化附件，不参与运行时。

---

## 16. 页面实现交接（给页面层）

| 页面 | 主要组件 | 必须实现的事件/状态 | 禁止 |
| --- | --- | --- | --- |
| `workbench` | `layout.page statusBar` + `card/action` + `mini-list` + `stat` | 三入口跳转、最近构建行点击、健康度筛选跳转 | 自动触发 LLM |
| `warehouse` | `packageCard*` `bulletGroup` `variantCard` `drawer` | 选中/批量、抽屉开关焦点管理、变体保存与核实 | 直接改 DOM 文本拼用户内容 |
| `templates` | `importSteps pdfPreview blockTree importWarnings slotRow` | 四步状态机、双向高亮、置信度排序、冲突与缺槽位处理 | 把 CID 字形当缺字报错 |
| `jobs` | `jobListItem coverageRing weightBar requirementTable coverageChips companyProfile` | 分析→Consent→任务、缺口跳转、重新分析确认 | 编造公司信息 |
| `builds` | `languageSwitch templateSelect pickerLeft selectSummary namingPreview photoToggle exportBox paperMock buildPreview` | 语言→缺失字段→禁用导出、命名 validate 防抖、照片开关、导出前 Consent | 前端拼文件名、硬编码姓名/端口 |
| `profile` | `profileForm photoField profileNamingPreview completenessMeter` | 实时命名联动、缺学校整卡标红、照片三态与二次确认 | 在本地保存照片以外的二进制到前端存储 |
| `settings` | `field segmented toggle callout` | provider 两档 + 关闭、密钥掩码、测试连接 | 出现 Ollama/本地模型/密钥片段 |

页面层只允许 `import` 组件与 `api`/`state`；组件层不得反向 `import` 页面层。

---

## 17. 验收映射

| 验收项 | 本文位置 | 落实点 |
| --- | --- | --- |
| AC-UI-01 断网全页面可加载无外链 | §15 | 零外部资源、内联 SVG、系统字体 |
| AC-UI-02 零构建无 node_modules | §15 | 原生 ES modules，`index.html` 直接 import |
| AC-UI-03 Consent 必现/Esc 取消/Enter 不发送/excluded+redactions 主视野/过期换按钮 | §7 | `consent-modal.js` + 预览页 `#consent` |
| AC-UI-04 禁 innerHTML 注入 | §5.1 | `dom.js` `FORBIDDEN_PROPS` 抛错，文本只走 Text 节点 |
| AC-UI-05 导出对话框实时命名 + 缺变量红字 + 深链 + 默认模板 | §10、§6.5 | `namingPreview` + `profileNamingPreview` |
| AC-UI-06 JobToast 进度/可取消/重启变中断 | §8 | `job-toast.js` |
| AC-UI-07 1280×800 无横向滚动、1440+ 三栏 | §4.3 | 断点与 `.split--build` |
| AC-UI-08 字体/引擎不可用顶部红条且禁用 PDF | §13、§8 | 状态条 + `FONT_UNAVAILABLE` 文案 |
| AC-UI-09 错误按 code 分支 + hint，不原样 JSON | §13 | `errors.js` |
| AC-NAME-07 前端不硬编码姓名/学校 | §1.7、§15 | 全部示例数据用「陈思远 / 示例大学」，运行时只吃 UserProfile |
| 用户裁决·技能不拆 tag | §6.3、§12.1 | `skillLines` 逐行原文；无 chip / 无竖线；PDF 文本与源行逐字相等 |
| 用户裁决·荣誉不单独成节 | §6.3、§12.3 | `.honor-row` 开关，挂在校园活动下作为可选要点 |
| 用户裁决·主修课程默认全留 | §6.5、§12.2 | `courseTrim` 默认关闭；打开先列裁掉哪几门再确认 |
| 用户裁决·不新增「竞赛」分类 | §6.3、§12.3 | 分类固定 6 类，竞赛归项目/校园 |
| 前端不拼 API base URL | §15 | 一律同源 `/api/v1/**`；前端产物 grep 无 `8765` / `localhost:` |

---

## 18. 已知限制与后续

1. `light-dark()` 需要 Chrome/Safari ≥17.5；旧浏览器会退回浅色（可接受，不引 polyfill）。
2. `hanging-punctuation` 仅 Safari/新 Chrome 生效，其它浏览器标点不悬挂但不断行。
3. 预览页是**静态** mock：真实交互以组件层为准；预览页不加载 `src/pages/**`，避免与页面 lane 耦合。
4. 打印路径依赖浏览器对 `@page` 的支持；最终交付以服务端 reportlab 渲染为准（`docs/ARCHITECTURE.md` §7.5）。
5. 移动端不做适配，<1024 显示桌面宽度提示。
6. 组件层未写单元测试（零构建约束下不引测试框架）；行为由 `docs/ACCEPTANCE.md` 的 UI 组条目人工/脚本验收。

---

*本文与 `web/preview.html` 同步维护：改视觉先改 token，再改组件，最后同步预览页；三者不一致视为缺陷。*

---

## 19. 实装对照（设计稿 ↔ 组件/CSS）

组件层 13 个文件全部在 `web/src/components/`（纯展示、零依赖、ES module）。下表逐节对账，**"设计了但没实装"单列在 §19.2**——这是诚实账，页面层（`web/src/pages/**`）不在本次 t3 范围。

### 19.1 逐节对账

| 设计章节 | 落点（组件 / CSS） | 状态 |
| --- | --- | --- |
| §1 设计原则 | `tokens.css` + `base.css` + 全组件约定 | 已实装（样式层） |
| §2 信息架构 | `web/index.html`（`ROUTES` + hash 路由）、`layout.js` `NAV_ITEMS` | 外壳已实装；页面装配未实装 |
| §3 设计 token | `tokens.css`（`light-dark()` 单份深色定义） | 已实装 |
| §4 布局系统 | `layout.css`（外壳、6 种栅格、断点、抽屉） | 已实装 |
| §5 组件库 | `primitives.js` + 12 个领域组件 | 已实装 |
| §6.1 工作台 | `.action-card` / `.stat` / `.mini-list` / `ui-empty` | 样式已实装；页面编排未实装 |
| §6.2 Package 仓库 | `package-card.js`（`packageCard`/`bulletGroup`/`variantCard`）+ `.pkg-grid` + `.drawer` | 已实装 |
| §6.3 导入与校对 | `import-review.js`（`importSteps`/`pdfPreview`/`structureTree`/`tree-fact`/`importAnomalies`/`reviewFooter`） | 已实装（含 3 级树与整段文字） |
| §6.4 目标职位 | `jd-panel.js`（`requirementTable`/`coverageRing`/`weightBar`/`companyProfile`） | 已实装 |
| §6.5 组装与导出 | `build-parts.js`（`languageSwitch`/`templateSelect`/`pickerLeft`/`namingPreview`/`photoToggle`/`exportBox`/`paperMock`/`buildPreview`） | 已实装 |
| §6.6 个人资料与设置 | `profile-form.js`（`profileForm`/`photoField`/`profileNamingPreview`/`completenessMeter`） | 已实装 |
| §7 ConsentModal | `consent-modal.js` + `.modal*` | 已实装 |
| §8 JobToast | `job-toast.js`（`jobToast`/`toastLayer`）+ `.toast*` | 已实装 |
| §9 简历语言切换 | `build-parts.languageSwitch` + `.ui-seg` | 已实装 |
| §10 文件名预览 | `build-parts.namingPreview` + `profileNamingPreview` + `.naming*` | 已实装 |
| §11 照片规范 | `profile-form.photoField` / `build-parts.photoToggle` / `print.css` `.doc__photo` | 已实装 |
| §12 A4 导出稿 | `print.css`（含 §12.4 实测档位） | 已实装 |
| §13 文案规范 | `errors.js`（`describeError`/`errorView`）+ 组件内文案 | 已实装（页面级空态文案未实装） |
| §14 无障碍与键盘 | `dom.trapFocus`/`focusFirst`、组件 `aria-*`、`index.html` 全局 ⌘K/⌘S | 组件级已实装；页面内快捷键未实装 |
| §15 离线与零构建 | 13 个 ES module，无依赖、无构建、无外链 | 已实装 |
| §16 页面交接表 | 本文档 | 文档（n/a） |
| §17 验收映射 | 本文档 + `web/preview.html` 静态走查 | 文档（n/a） |
| §18 已知限制 | 本文档 | 文档（n/a） |

### 19.2 设计了但没实装（文件 + lane + 依赖）

t3 只做到「组件 + CSS + 静态预览」，页面装配属于别的 lane。下表每项点名**要动的文件**、**归谁**、**卡在什么依赖上** —— 这些不是缺陷，是还没轮到的工作。

| 项 | 设计在哪 | 要动的文件 | 负责 lane | 依赖 |
| --- | --- | --- | --- | --- |
| 六个页面的组装（数据绑定、store 订阅、路由） | §2、§6 | `web/src/pages/{workbench,warehouse,templates,jobs,build,profile,settings}.js` | **t8**（构建/导出页）+ **t9**（仓库/模板/JD）+ **t10**（工作台/设置） | `web/src/api/*.js`（coder）+ `web/src/state.js` |
| PDF 原文页图渲染 | §6.3 左栏 | `web/src/pages/templates.js` | **t9** | `GET /api/v1/imports/{id}/pages/{n}`（server，coder） |
| 图片裁切算法与上传进度 | §11 | `web/src/pages/profile.js` | **t10** | `POST /api/v1/profile/photo`（server）+ 组件已就位的 `.photo-field` 裁切框 |
| HTML5 拖拽移动 block | §6.3 | `web/src/pages/templates.js` | **t9** | `PATCH /api/v1/imports/{id}/draft`；组件已提供上移/下移/换章节的键盘等价操作 |
| JobToast 轮询 / SSE / 重启恢复 | §8 | `web/src/pages/*.js` + `web/src/state.js` | **t8** | `GET /api/v1/jobs/{id}`（server）；组件已处理 `queued/running/succeeded/failed/interrupted` 五态 |
| 语言缺失提示的真实数据 | §9 | `web/src/pages/build.js` | **t8** | `profile.missing` + 模板 `required_fields`（`POST /api/v1/builds/{id}/assemble` 的 `missing_slots`） |
| 多页预览（>1 页分页与缩略图） | §6.5、§12 | `web/src/pages/build.js` | **t8** | `GET /api/v1/builds/{id}/preview?page=n`（server） |
| 一键打印入口 | §12 | `web/src/pages/build.js` | **t8** | 无（`@media print` 规则已就绪，只差一个 `window.print()` 按钮 + 打印前隐藏 chrome） |
| 骨架 → 真实数据过渡 | §6 | `web/src/pages/*.js` | **t8/t9/t10** | 无（`.ui-skel` 与 `skeleton()` 已在组件层，缺编排） |
| 版式松紧切换的持久化 | §12.4 | `web/src/pages/build.js` | **t8** | `PATCH /api/v1/builds/{id}` 存 `density`；组件 `densitySelect` 已就绪，默认 `original` |

### 19.3 本轮（真实数据化）的改动清单

- `preview.html` 的 03 导入校对屏：教育段改为**整段文字**（`.tree-fact` + 「整段 1/2」「N 个数字·不拆 bullet」），章节数 5 / 条目 6 / 要点 11 / 数字 47 与真实拆解体量一致；项目经历 3 条。
- `preview.html` 的 05 组装导出屏：左栏项目经历 3 条改为**可滚动列表**（`.pick-scroll`），每行带匹配分（`.pick-row__match`）与变体数；右栏技能 3 行整句原文 + 命中徽章 + 课程裁剪。
- `print.css`：新增 `.doc__fact`（整段文字，行首无「·」、可与 bullet 区分）、`.doc--dense`、`.doc mark.num` 归零、`@page` 与 `.doc` 内边距对齐。
- `components.css`：新增 `.tree-entry__facts` / `.tree-fact` / `.tree-entry__fact-note` / `.pick-scroll` / `.pick-row__match` / `.pick-row__count` / `.pick-hint`。
- **异常区按真实草稿的 `quality` 重写**：真实拆解是 `cid_residual:0`、`replacement_chars:0`、`images:1`，所以第 03 屏不再出现「16 处 bullet 提取不到」这类演示性告警，改为两条真实存在的提醒 ——「检测到 1 张照片（266×266 px），已剥离为独立文件」与「3 条要点置信度低于 0.8（0.72 / 0.74 / 0.66）」。两者都**不阻断入库**，因此「确认入库」是**可点的主按钮**（只有 U+FFFD 无法修复、数字丢失、缺 section 这类才置灰）。

---
- **版式密度落地（2026-10-23 晚，与 ARCHITECTURE §7.5.1 v1.15 对齐后）**：`print.css` 改为 `@page { margin: 0 }` + `.doc` 四边内边距承担页边距；`original` 档常量为 **上 8.3pt / 下 16.4pt / 左 14.8pt / 右 15.6pt**（唯一一份，写在 `.doc` 上），`.doc--density-original` 只作标记不重复数值；`relaxed` 档为上下 16mm / 左右 15mm；`.doc--compact` / `.doc--dense` 不再改内边距（字号与密度解耦）。照片三值 89.28pt / 3.82pt / 9.13pt 不随密度变。
- **导出页新增「版式松紧」**：组件 `densitySelect`（`build-parts.js`，`.ui-seg--block` 两档 + 「预计 N 页」+ `.density-note`），选项文案是「紧凑（与原简历一致，单页）」/「宽松（可能两页）」，不暴露 `original/relaxed` 术语；`.ui-seg--block .ui-seg__opt` 允许折行（380px 侧栏里中文长标签必须能两行）。
- **字号阶梯改回契约 v1.17**：默认由 `10.5pt / 1.62` 改为 **`11pt / 行距比 1.15`**，新增 `.doc--tight`（10pt）补齐四档，`.doc--dense` 改 `9.5pt / 1.15`（行距比不再随档位变）；`--doc-fs`/`--doc-lh` 注释指明对应契约 `--doc-body`/`--doc-leading`，`preview.html` 的「版式规格」注释同步为新口径（11pt/1.15、余 50mm、宽松档上下 16mm/左右 15mm）。
- **条目头改单行 flex**：`.doc__entry-head` 由 `grid` 改为 `display:flex; align-items:baseline; gap:8pt`，标题 `flex:1 1 auto` + `white-space:nowrap; text-overflow:ellipsis`，日期列 `flex:0 1 auto; min-width:12%; max-width:22%`（即契约「日期列占版心 12%–22%」的百分比写法，不再引入第二份绝对常量）。实测 6 个条目头全部 1 行（`headOverflow: 0`）。
- **正文族字号全部由 `--doc-fs` 派生**：`.doc__bullet` / `.doc__fact` / `.doc__entry-title` / `.doc__entry-org` 直接 `var(--doc-fs)`；`.doc__headline` `×0.94`、`.doc__contact` / `.doc__entry-sub` `×0.86`、`.doc__tags` `×0.9`。改这一处即改全篇，**杜绝第二种字号阶梯**（DESIGN-BRIEF.md:186 禁止项）。
- **预览页纸张缩放改用固定像素 + `transform`**：构建页中栏 `.pv-frame .build-preview__frame{width:373px;height:528px;overflow:hidden}` + `.doc{width:794px!important;transform:scale(.47);transform-origin:top left}`。原因：`zoom` 在 Chrome 会重算布局宽度，导致正文画出白底、右侧被裁；`transform` 不参与布局则必须由外层给定缩放后的尺寸。仅影响 `preview.html`，不影响 `print.css`。
