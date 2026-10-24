# UI-REFRESH — 简约交互反馈改造（v1.0）

> owner: uier ｜ 状态: 待 coder 落地 ｜ 2026-10-24
> 配套产物：`web/src/styles/uiverse.css`（636 行，只含样式）
> 本文件只描述**要改成什么、落到哪个选择器/哪一行代码**，不含「建议优化」类表述。
> 每个动作都给了：四态文案、DOM/属性契约、CSS 类名、JS 改动点、可执行验收断言。

---

## 0. 怎么用这份文档

| 角色 | 读哪几节 |
| --- | --- |
| planner | §2 选型（判断范围）、§4 规格表（拆任务）、§5.1 清单（排期与依赖） |
| coder | §3 规范（**实现契约，先读**）、§4 规格表（逐行对照）、§5.1 清单（逐条打勾）、§5.2 接线片段（可复制） |
| 验收 | §5.3 断言（可执行命令）、§7 自查记录 |

**一句话总纲**：`web/src/components/feedback.js`、`toast.js`、`progress.js` 已经把四态契约、通知、长任务进度做成了模块（§5.1 A 段列出已交付接口与仍缺的一处导出）；**CSS 层由 `uiverse.css` 接管这些模块写出的状态属性** —— `.ui-btn[data-phase]`、`[data-region="feedback"]`、`.toast[data-tone]`、`[data-role="job-progress"]`，所以样式不改任何一行 JS 就生效；剩下的事是把 7 个页面接到这批模块上，并消灭 `alert()`、`node.disabled = true`、「加载中…」callout 这三类旧反馈。

---

## 1. 硬约束与自证方式

| # | 约束 | 本次如何满足 | 自证命令 |
| --- | --- | --- | --- |
| 1 | CSP `script-src 'self'`，禁内联脚本/外链 CDN/`new Function` | `uiverse.css` 不含任何 JS；需要 JS 的部分全部写成 ES module 需求（§5.1），放 `web/src/components/` | `grep -n "<script" web/src/styles/uiverse.css` → 0 |
| 2 | 完全离线 | 零 `@import`、零资源引用函数、零字体、零图标字体；星标/勾/关闭字形全部 `border`+`clip-path` 现画 | §7 自查脚本输出 |
| 3 | `dom.js` 禁 innerHTML | §5.2 的接线片段全部用 `h()`/`textContent`/`append`，无一行 innerHTML | §5.3 断言 3 |
| 4 | 颜色/间距只用 `tokens.css` | 全文 0 个字面色值（无 hex、无 rgb/hsl、无 white/black）；新增仅 5 个 `--ux-*` 语义变量，其值全部引用 token | §7：`re.findall(r'#[0-9a-fA-F]{3,8}')` → `[]` |
| 5 | `print.css` / 照片几何（52pt 方块、距顶 8.3、距右 15.62）不得被影响 | 新文件**不含任何纸张相关选择器**（`.doc`、`.doc__*`、`.paper-stage*`）也**不含打印分页声明**；`uiverse.css` 在 `print.css` 之前加载，打印规则仍由 `print.css` 全权覆盖 | `grep -cE "\.doc|paper-stage|@page" uiverse.css` → 0 |
| 6 | 深浅色都要能看 | 所有颜色走 token，token 用 `light-dark()` 成对声明 ⇒ 两套主题自动成立，**本文件没有一条 `[data-theme]` 分支**；对比度由 DESIGN §3 的 token 基线保证 | §5.3 断言 6 |

---

## 2. 选型清单（8 个 uiverse 页面 → 7 组组件）

### 2.1 取材说明（诚实版，请勿略过）

uiverse 的组件代码面板是 **JS 客户端渲染**：服务端下发的 HTML 不含 CSS 源码（页面里只有作者写的英文设计描述 + tags + 一个 4.5KB 的风控壳），直连其 API 返回 403/404。因此本方案的做法是：

1. 逐个打开原始页面，读取作者对该组件的**公开设计描述与 tags**（下表「取自」列即原文要点）；
2. 用本项目 tokens 重写成纯 CSS（不是逐字复制原代码，也不下载任何资源）；
3. 保留原始链接以便复核。uiverse 页面底部声明其内容整体以 MIT 发布，视觉思路借鉴无授权负担。

**改造原则（对所有组件生效）**：uiverse 上偏「重」的部分（多层硬阴影、3D 抬升、霓虹发光、圆形 morph、parchment/ember 双色循环）一律降级为「**低饱和 + 1px 位移/1 条描边/1 次淡入**」，因为本项目的排版基准是 A4 纸张预览，任何高对比装饰都会在纸张旁边抢注意力。

### 2.2 清单表

| # | 组件 | 来源（uiverse 原始页面） | 取自原文的视觉要点 | 为什么选它 | 落到哪 |
| --- | --- | --- | --- | --- | --- |
| C1 | **Minimal 按钮** | [iamriishav/old-liger-56](https://uiverse.io/iamriishav/old-liger-56) | `rounded`/`text`/`shadow`/`white`/**`minimal`**/`hover` | 白底 + 小圆角 + 一层柔和阴影 + 悬停才浮起；和本项目「低饱和、无边框感」的按钮完全同族，改造成本最低 | 全 7 页的 `.ui-btn`；重点 工作台「开始拆解」、拼装「导出 PDF」、设置「保存设置」、资料「保存」 |
| C2 | **按压物理** | [00Kubi/wise-catfish-3](https://uiverse.io/00Kubi/wise-catfish-3) | `rounded`/`shadow`/`3D`/**`press`** | 它的 `press` 手感（按下瞬间压低）是本次「点击反馈」的核心，但它的 3D 抬升+蓝色要丢掉，只保留「下沉 1px」 | 同上（并入 C1 的 `:active`） |
| C3 | **下划线输入** | [Satwinder04/quick-cheetah-45](https://uiverse.io/Satwinder04/quick-cheetah-45) | `input`/`placeholder`/`gray`/**`minimal`**/**`underline`** | 无框、灰占位、焦点只出现一条下划线；正是「边框不抢戏、焦点要明确」的解法 | 焦点态：`#wb-text`、`#jd-text`、`#tpl-paste`、`#st-key`、`#bd-position`、资料 13 个 `#pf-*` |
| C4 | **灰圆开关** | [KareemTolan/tasty-snail-21](https://uiverse.io/KareemTolan/tasty-snail-21) | `switch`/`grey`/`round`/**`minimal`**/`toggle`/`inactive`（1.4K 赞） | 灰轨 + 圆钮、无描边；轨道色正好映射 `--c-border-strong` ↔ `--c-primary-solid`，不需要新色 | 设置「自动脱敏电话/邮箱」「允许抓取公司公开页面」；拼装「包含照片」 |
| C5 | **两段式复选框** | [uiverse-astronaut/itchy-fireant-31](https://uiverse.io/uiverse-astronaut/itchy-fireant-31) | pill-square **morph** + 「fill 完成后 tick 才 scale-in」的 `kinetic` 两段节奏 | 把「填充」和「打勾」拆成两拍，是本次要的**成功反馈**最小样本；比单纯换色有「确认感」 | 拼装选经历条目、招聘「用 DeepSeek 分析」、模板语言/勾选项、经历库筛选 |
| C6 | **行内 pending 星标** | [uiverse-astronaut/ordinary-bobcat-90](https://uiverse.io/uiverse-astronaut/ordinary-bobcat-90) | 四角星 spark 旋转 + 旁边小号标签（`loader`/`spinner`/`editorial`） | 4 角星比圆环「轻」，适合按钮内 14px 的 pending；配 micro 标签满足「颜色不单独表意」 | 所有 `data-phase="pending"` 的按钮、设置「测试连接」、模板「解析粘贴内容」 |
| C7 | **整页 loader / 骨架** | [elijahgummer/sharp-squid-77](https://uiverse.io/elijahgummer/sharp-squid-77) | 旋转星/圆环（`star`/`circle`/`rotating`/`waiting`） | 页面级「整块在加载」只需要一个安静的单体动效；本项目骨架已有 `.ui-skel`，借它的星形做首屏 loader | 经历库首屏、招聘列表、拼装侧栏、资料/设置首屏 |
| C8 | **确认 Toast** | [uiverse-astronaut/great-turtle-50](https://uiverse.io/uiverse-astronaut/great-turtle-50) | 圆形 check 领起 + 标题/描述两级字 + **ghost 关闭字形** + 柔和多层阴影 + **发丝边框** | 「任务收尾」这件事故意要比 callout 更安静：发丝边框 + 圆勾，不抢焦点；ghost 关闭字形去掉图片/字体依赖 | `job-toast.js` 全部任务卡；以及 工作台保存 / 资料保存 / 设置保存 / 拼装导出 的成功收尾 |

> 采用 uiverse 的「只挑视觉语汇、不搬 CSS」策略还有一个硬理由：uiverse 的组件普遍用**字面色值**（如 `#0c1320`、`#c7b294`）与**多层 box-shadow**，直接搬进来会同时违反本文档 §1 的第 4、6 条约束。

### 2.3 逐组件改造点（从 → 到）

**C1+C2 按钮**（`uiverse.css` §1）
| 原组件 | 本项目改造 |
| --- | --- |
| 白底 + 常驻阴影 | 默认无阴影；`:hover` 才加 `--sh-1`（`--primary/--secondary/--danger` 三个实心变体） |
| `3D` 抬升（translateY(-2px) + 大阴影） | `:active` 下沉 `translateY(1px)`（`--ux-press-y`）+ 阴影归零；时长 `--ux-dur-tap: 100ms` |
| 固定蓝色 | 无新增色；四态色全部给 `--c-success*` / `--c-danger*` |
| 无状态 | `[data-phase]` 四态（属性名取自已实装的 `createAction()`）：`pending`（星标 + 「处理中…」文案 + `cursor:progress`；CSS **覆盖 `disabled` 的 0.45 透明度**，否则按钮看起来像坏了）、`success`（绿边+浅底，1200ms 后由 JS 回 idle）、`error`（红边 + 一次 2px 抖动 `ux-shake`）。旧写法 `[data-state]` / `.is-loading` 同样生效 |

**C3 输入**（`uiverse.css` §3）
| 原组件 | 本项目改造 |
| --- | --- |
| 完全无边框、只一条下划线 | **保留原有 1px 边框**（不破既有表单观感），`:focus-visible` 时叠加 `inset 0 -2px 0 var(--c-primary)` 内嵌下划线 —— inset 阴影不参与布局，**零位移** |
| 焦点色唯一变化 | 非法态焦点同时给 `3px --c-danger-soft` 外环 + 红色内下划线，红+形双通道 |
| 无只读处理 | `[readonly]:hover` 不加深边框，避免暗示可编辑 |

**C4 开关**（`uiverse.css` §4）
| 原组件 | 本项目改造 |
| --- | --- |
| 灰色双态 | 轨色 `--c-border-strong` → `--c-primary-solid`（沿用既有基类，只补 hover 轨色） |
| 圆钮平移 | 加 `:active` 时拇指 `width 16→18px` 拉长（checked 时 `translateX` 由 14→12 补偿，**不越轨**） |
| — | `[aria-disabled="true"]` 时 hover 不换色（既有 opacity .5 保留） |

**C5 复选框**（`uiverse.css` §5）
| 原组件 | 本项目改造 |
| --- | --- |
| 圆形 → 圆角方形 morph | **拒绝**：本项目 `.ui-check` 同时承载 radio，圆形语义会撞车。保留 4px 方形，只取节奏 |
| fill 完成 → tick scale-in | `input:checked::after` 加 `ux-tick-in 160ms var(--ease) 60ms both`：先填色，60ms 后勾从 `scale(0.35)/opacity 0` 弹出 |
| 无按压反馈 | `:active` 时 `scale(0.9)`，100ms 回弹 |

**C6 星标**（`uiverse.css` §2）
| 原组件 | 本项目改造 |
| --- | --- |
| 图片/SVG 星 + parchment↔ember 双色循环 | `clip-path: polygon(...)` 八点现画四角星；**直接覆盖 `.ui-spinner`** —— 于是 `createAction` 的按钮槽位、`jobProgress`、`loadingText`、toast 里的所有转圈一次全变星标，JS 零改动；配色降级为「`currentColor` + opacity 0.55 呼吸」（`ux-spin` + `ux-spin-breathe`） |
| 固定尺寸 | 保留既有 14px（正是 `createAction` 预留的槽位宽度）；`.ux-spin` 另给 `--sm 11px` / `--lg 22px` / `--muted`（`--c-text-3`）三档；需要传统圆环时用 `.ui-spinner--ring` 逃生舱 |
| 只旋转无文字 | 配 `.ux-pending`（星+文字）与 `.ux-pending__label`（11px 小字，`letter-spacing .04em`） |

**C7 整页 loader / 骨架**（`uiverse.css` §7）
| 原组件 | 本项目改造 |
| --- | --- |
| 旋转星作为独立 loading 块 | 复用 `.ux-spin--lg`；首屏用**骨架**而不是 loading 块 |
| — | `.ui-skel::after` 的 `rgba()` 字面流光改为 `linear-gradient(90deg, transparent, var(--c-surface-hover), transparent)`：暗色下自动正确，且不再需要 `light-dark()` 补丁 |
| — | 新增 `.ux-skel-pulse`（不扫光，只呼吸，1.6s）、`.ux-skel-slot`（`min-height: var(--ux-skel-h)` 零跳动槽位）、`.ux-skel-rows`（行距 `--sp-4` 与真实列表一致） |

**C8 Toast**（`uiverse.css` §9；挂载点是 `components/toast.js` 生成的 DOM）

| 原组件 | 本项目改造 |
| --- | --- |
| 墨色面板 + 羊皮纸圆勾 | 面板保持 `--c-surface`；「圆勾」包住**既有** `.toast__icon`（22px 圆、`--c-success-border` 边、`--c-success-soft` 底），不改 `toast.js` 生成的结构 |
| tone 区分 | 不新造形状，改用左侧 3px 竖条：`.toast[data-tone="success|warn|danger|info"]`（成功/警告/失败/中性各一色，全部 token） |
| ghost 关闭字形 | 落在既有 `iconButton` 上：`.toast__head > .ui-btn` 22px、无边框、hover 才出 `--c-surface-hover` 底；字形仍由 `icons.js` 提供，不新增图标 |
| 柔和多层阴影 + 发丝边框 | `box-shadow: var(--sh-3), inset 0 1px 0 var(--c-surface-2)`；边框保持 `--c-border-strong` |
| 离场 | **已实装**：`dismissToast()` 加 `.is-leaving` + 内联 transition，160ms 后移除；CSS 侧补 `.toast.is-leaving` 兜底（内联被清掉也能淡出） |

---

## 3. 交互反馈规范（实现契约）

### 3.1 四态模型（契约已实装在 `web/src/components/feedback.js`）

**状态机**（每个「一次动作」一个实例，不复用）：

```
idle ──(用户触发, 同步置位)──► pending ──(2xx)──► success ──(holdMs 1200ms)──► idle
                                  └──(非 2xx)──► error ──(用户再点即可重来)──► pending
```

- **idle**：动作可用的默认态（`data-phase="idle"`，标签是动词原文案）。
- **pending**：请求已发出、结果未知。`createAction().run()` 在**第一个 `await` 之前**就 `paint(PHASE.pending)` —— 这就是同步闸，双击的第二下在微任务里到达时已被 `api.state === PHASE.pending` 丢掉。
- **success**：服务端已确认（**不是**「请求发出去了」）。标签换成 `successLabel`，`holdMs` 默认 1200ms 后自动回 idle。
- **error**：标签回原文案、按钮恢复可点；错误正文由页面用 `feedbackRegion().error(err, { onRetry, onAction })` 呈现。**错误展示不自动消失**，只有用户关闭或重试。

**已交付的四个接口**（页面直接 import，不要再自己写一套）：

| 接口 | 作用 | 关键行为 |
| --- | --- | --- |
| `createAction({ label, pendingLabel, successLabel, onClick })` → `{ node, run, reset, setDisabled, state }` | 四态行动按钮 | 内部已有重入判断；pending 时 `data-phase` + `.is-pending` + `aria-busy="true"` + 预留 14px 星标槽位（切态不顶宽） |
| `feedbackRegion({ label, live })` → `{ node, idle, pending, success, error, set }` | 内联反馈区 | `aria-live="polite"`、`aria-atomic="true"`；`success` 可关闭；`error` 自带 `describeError` 三段式 + 可重试判定（`isRetryable`）+ 错误码 badge |
| `inlineError(message, { onDismiss })` | 贴着元素的一行错 | `role="status"` + `aria-live="polite"`，用于乐观更新回滚（不抢全局反馈区） |
| `submitGuard()` / `optimistic({ apply, commit, revert, onError })` | 非按钮入口的闸 / 乐观更新 | `submitGuard().isBusy()` 供快捷键、回车、拖拽复用；`optimistic` 失败自动 `revert()` |

**页面侧的 DOM 契约**（CSS 已按此挂载，见 `uiverse.css` §1、§6）：

```html
<!-- 行动按钮 -->
<button class="ui-btn ui-btn--primary" data-phase="idle" aria-busy="false">
  <span class="ui-action__spin" aria-hidden="true" hidden><span class="ui-spinner"></span></span>
  <span class="ui-btn__label">导出 PDF</span>
</button>

<!-- 反馈区（放在动作旁边、视线自然落点；空着时不占高度） -->
<div data-region="feedback" aria-live="polite" aria-atomic="true" aria-busy="false" aria-label="操作状态"></div>
```

四条铁律：
1. **状态只改属性**（`data-phase` / `aria-busy` / 标签文本），不重建按钮；标签文案变化由 `createAction` 统一处理，页面不要自己 `textContent = "保存中…"`。
2. 反馈区**一次只放一块**（`feedbackRegion` 内部 `clear()` + append）；`pending` 块在 `aria-busy="true"` 期间用虚线段（`uiverse.css` §6）与转圈星标双重表达「还没有结果」。
3. 播报只走一个地方：`feedbackRegion` 的 `aria-live` 容器 + `.ui-field__error` 的 `role="alert"`；不要给视觉块再加 `role="alert"`（会双播）。
4. `inlineError` 只用于「该元素附近」，且必须配 `onDismiss`（可关掉），否则错误会永久挂在行上。

**已知缺口（必须补，否则四态不完整）**：

| 缺口 | 现状 | 修法 |
| --- | --- | --- |
| 焦点丢失 | `createAction.paint()` 在 pending 时 `node.disabled = true`，浏览器会把焦点丢到 `<body>` | 改成 `node.setAttribute("aria-disabled", "true")` + `pointer-events:none`（CSS 已就绪：`.ui-btn[data-phase="pending"]`）；若保留 `disabled`，必须在 `paint()` 里记 `document.activeElement` 并在回 idle 时还原（见 §5.1 B8） |
| 四态之间的高度跳动 | `feedbackRegion` 是替换式渲染，pending 块与 error 块高度不同 → 区域高度跳一下 | ① 入场动画已缓解（`uiverse.css` §6）；② 若要真正零跳动，按**附录 A** 把四个块预渲染并用 `data-phase` 叠放 |
| `progress.js` 未导出 | `components/index.js` 只 `export * from "./toast.js"`、`"./feedback.js"`，漏了 `"./progress.js"` | 补一行导出（否则页面只能深路径 import） |

### 3.2 防重复提交（三层，缺一层就会漏）

| 层 | 做法 | 为什么必须有 |
| --- | --- | --- |
| L1 同步闸 | **已实装**在 `createAction.run()` 首行：`if (api.state === PHASE.pending) return { ok:false, skipped:true }`，位于第一个 `await` 之前；非按钮入口（回车/⌘S/拖拽）用 `submitGuard()` 的 `gate()` | 双击的第二下在微任务里到达，只有同步闸能挡住 |
| L2 属性闸 | 同帧设 `data-phase="pending"` + `aria-busy="true"`（`createAction` 已实装）。**建议**用 `aria-disabled="true"` 而非 `disabled`；CSS 侧 `.ui-btn:is([data-phase="pending"], [data-state="pending"], .is-pending)` 已同时覆盖两种写法 | `disabled` 会让浏览器把焦点丢到 `<body>`，键盘用户失位。当前代码用的是 `disabled`，所以 CSS 额外把 pending 时的透明度补回 1（否则按钮像坏了），焦点回位仍需 JS（§5.1 B8） |
| L3 容器闸 | 表单/卡片外层 `.ux-busy[aria-busy="true"]`，CSS 把内部控件 `pointer-events:none` + 降透明度 | 兜住「Enter 键提交」「第二个按钮」这类 L2 覆盖不到的路 |

例外（允许用原生 `disabled`，因为属于**结构性不可用**而非在途）：
- 拼装页「导出 PDF（缺中文字体）」—— 必须 `disabled` + `title` 说明原因 + 旁边给「重新检测字体」动作；
- 模板「保存补充行」在无模板时禁用（既有行为）。

> 现状违规清单（必须改）：`workbench.js:saveButton`、`pages/templates.js:commitButton`、`pages/builds.js:exportPdf(node)`、`pages/profile.js:saveButton`、`pages/settings.js:saveKey/testProvider/保存设置` 全部用 `node.disabled = true`，会把焦点踢走；且都是**先 `disabled` 再 `await`**（顺序对，但缺 L1 同步闸，双击仍可能进两次——`disabled` 属性在事件派发后才生效）。

### 3.3 乐观更新与回滚

判据：**幂等 + 可逆 + 本地视觉可表达** 三者同时成立才乐观；否则必须等确认。

| 动作 | 乐观？ | 视觉 | 回滚 |
| --- | --- | --- | --- |
| 经历库「标记核实」（`PATCH …/variants/:id {verified:true}`，幂等） | ✅ | 立刻把按钮换成 `.statusDot({level:"ok",label:"已核实"})`，整行加 `.ux-row.is-optimistic`（`opacity .65` + 1px 虚线描边 `--c-border-strong`） | 失败：移除 optimistic + 整行 `.ux-row[data-state="error"]`（`ux-rollback` 闪红 `--ux-dur-flash` 1200ms）+ 原地 inline 错误 + 播报「核实失败：…」 |
| 模板「设为默认」 | ✅ | 立刻把「默认」点移到该卡；原默认卡回到「设为默认」按钮 | 失败：同上，并把默认点移回原卡 |
| 设置里两个开关（自动脱敏 / 允许抓取） | ✅（本地 flag） | 开关立即切换（开关自身就是反馈）；按钮旁出 `.ux-pending__label`「有未保存的改动」 | 无需回滚（未落盘），保存失败时保留脏标记 |
| 保存资料 / 保存设置 / 保存 key | ❌ | — | 必须等服务端 2xx 才 success（涉及 `.env` 600 与文件名契约） |
| 导出 PDF / 组装 / 分析 JD / 导入解析 | ❌ | — | 长任务，走 JobToast 五态，禁止乐观 |

**乐观更新时序**：`点击 → 同步置 optimistic（0ms）→ await → 2xx：去掉 optimistic（保留结果）／非 2xx：回滚 + error`。
**可访问性**：optimistic 只是视觉，`aria-busy="true"` 必须同时挂在行上；回滚时 `.sr-only` 播报失败原因（不能只靠闪红）。

### 3.4 焦点与键盘

| 场景 | 规则 |
| --- | --- |
| 焦点环 | 统一 `--ring`（`0 0 0 2px --c-surface, 0 0 0 4px --c-focus`）；新增交互元素（ghost 关闭（`.toast__head > .ui-btn`）、反馈区里的 `<a>/<button>`、`.ui-file`）已补 `:focus-visible` |
| 在途期间 | 焦点**留在触发按钮**（这是用 `aria-disabled` 而非 `disabled` 的原因）；`aria-busy="true"` 让读屏知道「别急着再按」 |
| 反馈出现 | **不抢焦点**（aria-live 负责播报）。只有字段级校验失败才 `focus()` 该字段 |
| 成功后 | 若触发了节点替换（如「确认为模板」清空草稿），焦点移到该流程的稳定容器（模板语言 tabs 或列表首项），不能落到 `<body>` |
| Enter | 表单内 `keydown` 必须判 `ev.isComposing === false && ev.key === "Enter"` 才提交（中文输入法选词回车不得触发保存）；Consent 弹层继续按 DESIGN §7 拦截 Enter（除 `[data-allow-enter]`） |
| Esc | 只关最上层：Toast（仅已完成/失败卡）→ 弹层 → 无。**不得**中断进行中的导出/组装 |
| ⌘S / Ctrl+S | `preventDefault` 后触发当前页主保存动作；若该动作在 pending，则播报「正在保存…」而不发第二次请求（走 L1 同步闸） |
| Tab 序 | 骨架块 `aria-hidden="true"` + 内部无 tabindex，不得进入 Tab 序；`[data-region="feedback"]` 隐藏态孩子 `visibility:hidden` 天然不可聚焦 |

### 3.5 aria-live 播报矩阵

| 位置 | role / aria-live | 播报内容 | 频率 |
| --- | --- | --- | --- |
| `[data-region="feedback"]`（页面内一次动作的反馈区） | `role="status"` + `aria-live="polite"` | 状态切换时写一行：「正在校验文件名…」「已保存，文件名已同步」 | 每次状态变化 1 次 |
| error 块内的文案 | 无 role（纯视觉） | 由上面那行统一播报 | — |
| 字段级错误 `.ui-field__error` | `role="alert"`（既有，保持） | 字段错误原文 | 出现时 1 次 |
| `job-toast.js` 任务卡 | `role="status"/"alert"`，failed 用 `aria-live="assertive"`（既有） | 状态五态 | 状态变化时 |
| JobToast 轮询进度条 | **不播报**（`aria-hidden="true"` 于数值，容器 `aria-busy="true"`） | — | 禁止每次轮询刷屏 |
| 骨架区 | `aria-busy="true"` + `aria-label`「正在载入经历库」 | 完成时 `aria-busy="false"` | 2 次 |
| 乐观更新 | 行 `aria-busy="true"` | 回滚时播报失败 | 2 次 |

> 与 DESIGN §7 的分工：Consent 弹层的错误条仍用 `role="alert"`；本节的 polite 仅针对**页面内四态反馈区**。理由：这些动作都由用户刚刚触发，polite 不会被打断，而 assertive 会在读屏念一半时插话。

### 3.6 `prefers-reduced-motion` 降级表

| 动效 | 正常 | 降级后（`uiverse.css` §12） |
| --- | --- | --- |
| `.ux-spin` 旋转 + 呼吸 | 1.1s 无限 / 2.2s 呼吸 | `animation:none`：星标变静态图形，**文字「进行中」仍在其旁**（状态不丢） |
| `.ux-skel` 流光扫过 | 1.4s 无限 | 停扫，保留 `--c-surface-3` 静态块 |
| `.ux-skel-pulse` 呼吸 | 1.6s 无限 | `animation:none`，保持 100% 不透明 |
| 复选框勾入场 | 160ms + 60ms 延迟 | 直接出现在终态（无过渡） |
| 按钮 error 抖动 | 2px × 2 来回 / 260ms | 不抖，只保留红边 + 文案 |
| Toast 离场 | 下移 6px + 淡出 / 160ms | 直接消失 |
| 按钮按压下沉 | `translateY(1px)` / 100ms | **不位移**（DESIGN §14 要求） |
| 开关拇指拉长 | 16→18px | 不拉长（checked 保持 `translateX(14px)`） |

`base.css` 已全局把 duration 压到 0.01ms，但**不处理 transform 位移**，所以 §12 的降级块必须存在（已用与按压规则完全相同的选择器，避免优先级被吃掉）。

### 3.7 骨架屏与零布局跳动

四条规则，违反任意一条就会出现「闪一下再跳一下」：

1. **槽位定高**：骨架容器 `class="ux-skel-slot"` 并内联 `style="--ux-skel-h: <实测px>"`，`min-height` 保证换成真内容后高度不变。
2. **延迟 300ms 才显示骨架**：请求 <300ms 直接出内容（本地 SQLite 大多如此），否则先显示骨架。避免「骨架闪 80ms」比不显示更糟。
3. **同层叠放**：骨架与真内容放同一 grid 单元（`grid-area: 1/1`），或先插真内容再移除骨架；**禁止**「先清空 → 再渲染」造成两帧空白。
4. **行距对齐**：骨架行距必须与真实列表一致（`--sp-4`，见 `.ux-skel-rows`），否则行数差会引起二次跳动。

各页首屏槽位（起始值，落地时用 DevTools 实测替换，CSS 只要求 `min-height` 等于实测）：

| 页面 | 骨架结构 | 起始 `--ux-skel-h` |
| --- | --- | --- |
| 经历库 `warehouse.js:load()` | stat 行 4 格（`.ui-card` 高 56）+ 3 张 package 卡 | `56px`；每卡 `148px` |
| 招聘 `jobs.js` 列表 | 4 行 JD 摘要 | 每行 `64px` |
| 拼装 `builds.js` 侧栏 | naming 卡 1 块 + 预览 1 块 | `96px` / `420px` |
| 模板 `templates.js` | 2 张模板卡 | 每张 `120px` |
| 资料 / 设置 | 表单 6 行（label 18 + gap 6 + 控件 32 + gap 16） | 每行 `72px` |

### 3.8 状态表达与文案

- **颜色不单独表意**（DESIGN §1）：pending 必有星标+文字，success 必有勾+「已…」，error 必有 `--c-danger` + 错误三段式（发生什么 / 为什么 / 一个动作）。
- 按钮文案动词开头，在途不改文案（**不要**「保存中…」替换标签，靠星标 + `aria-busy` 表达；改文案会让按钮宽度跳动）。
- 错误文案禁止 JSON/堆栈/key 片段（DESIGN §13）；技术细节只允许折叠在「技术细节：CODE」一行（既有 `builds.js` 已是此形态）。

---

## 4. 页面 × 动作 → 反馈规格表

> 「位置」列给的是现有代码锚点（文件 + 函数名/选择器），coder 照着改即可。
> 四态文案是**可直接抄进代码**的最终中文，不需要再润色。

### 4.1 工作台 `web/src/pages/workbench.js`

| # | 动作 / 位置 | idle | pending | success | error | 防重复 & 焦点 |
| --- | --- | --- | --- | --- | --- | --- |
| W1 | 「开始拆解」`workbench.js:151`（`draft()`） | 空态卡 + 按钮 | 按钮 `data-phase="pending"` + 星标；结果区 `[data-region="feedback"]` 转 pending：**「正在本地拆解…」/「不会发送给任何模型。」** | `[data-region="feedback"]` 转 success：草稿卡（要点数、问题数）；播报「拆解出 N 条要点」 | danger：**「拆解失败」** + `errorText(err)` + 动作「再试一次」（`button--ghost` 重调 `draft()`） | L1 同步闸；**保留上一次草稿**（现状会 `replaceChildren` 清空，必须改成四态） |
| W2 | 「保存为经历（N 条要点）」`workbench.js:56` | 按钮可用 | 按钮 pending + 星标；草稿区 `[data-region="feedback"]` pending「正在存进经历库…」 | 按钮 `data-state="success"` 1.2s → idle；`[data-region="feedback"]` success「**已存进经历库**」+ 次动作「去经历库看看」+ 圆勾（`.toast.is-succeeded .toast__icon`） 圆勾可选 | danger「**保存失败**」+ `errorText` + 「重试保存」；**草稿不得被清掉** | L1+L2；成功后在按钮上播报一次，然后焦点仍在按钮，由用户决定是否跳转 |
| W3 | 空文本点「开始拆解」 | — | **不进 pending** | — | 立即 warn「**先把经历写下来**」/「哪怕两句话也行——时间、单位、你做了什么。」+ `focus()` `#wb-text` | 不联网、不计时；焦点直接落到输入框 |

### 4.2 经历库 `web/src/pages/warehouse.js`

| # | 动作 / 位置 | idle | pending | success | error | 防重复 & 焦点 |
| --- | --- | --- | --- | --- | --- | --- |
| H1 | 首次进入 `load()` | — | **骨架**（stat 行 + 3 卡，`.ux-skel-slot` + `.ux-skel-rows`），区域 `aria-busy="true"`；**不再**用「加载中…」callout | stat 4 格 + 卡片列表；`aria-busy="false"` | danger「**读不到经历库**」+ `errorText` + 「重试」按钮 | 骨架 300ms 延迟；`aria-hidden="true"` |
| H2 | 「搜索」`warehouse.js:117` / `#wh-q` Enter | 列表 | 区域 `aria-busy="true"` + `.ux-pending`（星 +「搜索中…」）；**保留旧列表**（不闪骨架） | 新列表；0 结果 → `emptyState`「**没有匹配的经历**」+ 动作「清空搜索」（清空 `#wh-q` 并重载，焦点回输入框） | danger「**搜索失败**」+ 「重试」 | 300ms 防抖（`Enter` 立即）；L1 闸 |
| H3 | tabs 状态筛选 `warehouse.js:126` | 当前 tab `aria-selected="true"` | 同上 H2 | 同上 | 同上 | tab 键盘 ←/→（DESIGN §14）；切换不动焦点 |
| H4 | 「标记核实」`warehouse.js:99`（`verifyButton`） | ghost 按钮 | **乐观**：立即换成 `.statusDot({level:"ok",label:"已核实"})`，行加 `.ux-row.is-optimistic`，行 `aria-busy="true"` | 去掉 optimistic（行保持 100% 不透明） | 回滚：行 `.ux-row[data-state="error"]` 闪红 1200ms + 行内 inline danger「**核实失败**：{msg}」+ 播报；**替换现在的 `alert()`（`warehouse.js:111`）** | 行级 L1；不重载整页（现状 `await load()` 会整表闪烁） |
| H5 | 列表为空 | `emptyState`「**经历库还是空的**」+ 动作「去工作台拆一条」(`#/workbench`) | — | — | — | 空态也可 Tab 到动作按钮 |

### 4.3 模板 `web/src/pages/templates.js`

| # | 动作 / 位置 | idle | pending | success | error | 防重复 & 焦点 |
| --- | --- | --- | --- | --- | --- | --- |
| T1 | 选择文件 `templates.js:169`（`.ui-file`） | 虚线框 `选择文件` | `.ui-file` 获得 `aria-busy`；pending「**正在本机解析 {file.name}…**」/「全部在本机完成，不上传任何服务器。」+ 星标 | 进入校对区 `showDraft()`；播报「解析完成，请校对」 | `IMPORT_NO_TEXT_LAYER` → warn「**这份 PDF 没有文字层**」+ 动作「改用粘贴」→ 聚焦 `#tpl-paste`；其他 → danger「**解析失败**」+ `errorText` + 「换一个文件」 | 解析中禁止再选文件（`.ux-busy`）；完成后焦点移到校对区第一个可编辑项 |
| T2 | 「解析粘贴内容」`templates.js:171`（`handlePaste`） | 按钮可用 | 星标 + 「正在解析粘贴内容…」 | 校对区 | **空文本现在静默 `return`，必须改**：warn「**先粘点内容进来**」+ `focus()` `#tpl-paste`；其他错误 danger + 「重试」 | L1 闸 |
| T3 | 「确认为模板」`templates.js:82`（`commitButton`） | 按钮可用 | 按钮 pending + 星标；「正在保存模板…」 | success「**模板已保存**」；清空草稿；焦点移到「语言」tabs；列表重载（用 H1 骨架，不用 callout） | danger「**确认失败**」+ `errorText` + 「重试」（保留草稿） | L1+L2；**成功后才清空**，失败绝不清 |
| T4 | 「设为默认」`templates.js:35`（`setDefault`） | ghost sm 按钮 | **乐观**：默认点立即移到该卡 | 原默认卡恢复按钮 | 回滚 + inline danger「**设为默认失败**：{msg}」；**替换 `alert()`（`templates.js:53`）** | 同 H4 |
| T5 | 语言 tabs `templates.js:151` | `aria-selected` | — | 立即切换语言（纯本地） | — | ←/→ 键盘 |

### 4.4 招聘分析 `web/src/pages/jobs.js`

| # | 动作 / 位置 | idle | pending | success | error | 防重复 & 焦点 |
| --- | --- | --- | --- | --- | --- | --- |
| J1 | 「保存并分析」`jobs.js:250`（`createJd`） | 按钮可用 | 按钮 pending + 星标 | 进 `analyze()` 流程 | warn「**先粘 JD**」（现状已有）→ 保留并 `focus()` `#jd-text`；其他 danger + 「重试」 | L1 闸 |
| J2 | 本地分析 `heuristic` | — | 详情区 `[data-region="feedback"]` pending「**正在本地分析…**」+ 细进度条（indeterminate） | 详情渲染（需求/竞争力/院校信号） | danger「**分析失败**」+ `errorText` + 「重试」 | 轮询期间区域 `aria-busy="true"`，**不逐次播报** |
| J3 | LLM 路径 → 字段清单 `api.preview` | — | info「**正在生成将发送字段清单…**」+ 星标 | Consent 弹层（DESIGN §7：四段结构 + payload `<details>`） | danger「**字段清单生成失败**」+ `errorText` + 「改用本地分析」 | 弹层打开后焦点入 dialog（既有 `trapFocus`） |
| J4 | 弹层「确认发送并分析」`jobs.js:212` | 按钮可用 | 按钮 pending + `aria-busy`（`is-loading` 既有），**不可重复点**；「已发送，等待模型返回…」 | 弹层关闭 → 详情区 pending → success | 弹层**不关**，底部红条 + 错误码 + 动作（`LLM_AUTH`→「打开设置」`#/settings`；其他→「改用本地分析」） | DESIGN §7；Esc=取消；Enter 拦截 |
| J5 | Consent 过期 | — | — | — | 按钮替换为「**预览已过期 · 重新生成**」（DESIGN §7） | 点它重新 `api.preview` |
| J6 | 长任务轮询 `pollJob` | — | `[data-region="feedback"]` pending：`{JOB_KIND_LABELS}进行中…` + 「**可以离开这一页，任务会继续**」+ `.ui-progress__bar--indeterminate` | 列表 + 详情刷新 | danger「**分析失败**」+ `describeError` 三段 + 「改用本地分析」 | 容器 `aria-busy`；进度条 `aria-hidden` |
| J7 | 列表首屏 | 骨架 4 行 | 骨架 | JD 卡片 + `statusDot` 已分析/待分析 | danger「**读不到岗位列表**」+「重试」 | — |

### 4.5 拼装 `web/src/pages/builds.js`

| # | 动作 / 位置 | idle | pending | success | error | 防重复 & 焦点 |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | 命名输入 `#bd-position` / `#bd-company`（`refreshNaming`） | 上次校验结果（callout info「文件名：X」） | `namingHost` `aria-busy="true"` + `.ux-pending__label`「校验中…」；**保留上次结果**（DESIGN §10） | 新结果（绿色 valid / 红色 invalid + 「去个人资料」深链，既有） | 命名校验失败 danger「**命名校验失败**」+ 「重试」 | **300ms 防抖（现状每次输入都请求）**；`AbortController` 丢弃过期响应（防止慢响应覆盖新结果） |
| B2 | 「组装预览」`builds.js:342`（`assemble()`） | 按钮可用 | 按钮 pending + 星标；预览区 `.ux-skel-slot`（`--ux-skel-h:420px`） | 预览 + 「重新组装」ghost | 命名不完整 → danger「**先补全再组装**」（既有文案保留）；其他 → danger「**组装失败**」+ `errorText` + 「重试」 | L1+L2；失败后焦点回「组装预览」 |
| B3 | 「导出 PDF」`builds.js:228`（`exportPdf`） | primary + download 图标 | 按钮 pending + 星标；状态区 **info「正在渲染 PDF…」+ 不定量进度条**；页面顶部提示可离开（JobToast 接管） | 圆勾（`.toast.is-succeeded .toast__icon`）（圆勾）+ callout success「**已导出：{filename}**」+ 体积/文本层校验 + 「下载」primary；播报一次 | danger「**导出失败**」+ `describeError`（`copy.title/body/hint`）+ 「技术细节：{code}」折叠 + 「重试」；**不弹 JSON** | L1+L2；`finally` 里清 `data-state`；失败焦点回导出按钮 |
| B4 | 缺中文字体（`probeFonts`） | banner「这台机器没有找到中文字体（宋体）…」（既有） | — | — | 按钮 `disabled` + 文案「导出 PDF（缺中文字体）」+ `title="装好中文字体后再导出；点右侧按钮重新检测"` + 相邻「**重新检测字体**」ghost 按钮（新增） | 结构性不可用允许 `disabled`；焦点可由「重新检测字体」承接 |
| B5 | 照片开关 `photoToggle` `builds.js:42` | 开关 | — | 立即切换（本地 flag） | — | 切换后触发 B1 重新校验 |

### 4.6 个人资料 `web/src/pages/profile.js`

| # | 动作 / 位置 | idle | pending | success | error | 防重复 & 焦点 |
| --- | --- | --- | --- | --- | --- | --- |
| P1 | 任意字段 input（13 个 `#pf-*`） | 文件名预览卡（既有 `kv`） | `namingHost` `aria-busy` + 「校验中…」，保留上次 | 新预览 | danger「**文件名预览失败**」+「重试」 | 300ms 防抖（现状 `queueMicrotask` 每次输入必发） |
| P2 | 「保存」`profile.js:135`（`saveButton`） | primary | 按钮 pending + 星标 | 顶部 success「**已保存**」/「文件名已同步更新。」（2.4s 收起）+ 元信息刷新 + 播报 | danger「**保存失败**」+ `errorText`；然后把焦点移到第一个 `aria-invalid="true"` 字段 | L1+L2；成功后焦点留在按钮 |
| P3 | 「保存补充行」`profile.js:85` | secondary sm（无模板时 `disabled`，既有） | 星标 + 「正在写入教育段…」 | success「**教育段已更新**」+ 快照路径/md5（既有）；复制按钮 `data-state="success"` 1.2s 显示「已复制」 | danger「**写入失败**」+ `errorText` + 「重试」 | L1；复制用 `.ui-btn[data-state="success"]`（已由 CSS 覆盖） |
| P4 | 缺 N 项提示 `statusHost` | warn「还缺 N 项」（既有） | — | 齐全 → success「资料齐全」（既有） | — | 不阻断保存 |
| P5 | 照片未设置 | `statusDot`「未设置照片」（既有） | — | — | — | — |

### 4.7 设置 `web/src/pages/settings.js`

| # | 动作 / 位置 | idle | pending | success | error | 防重复 & 焦点 |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | 「保存 key」`settings.js:57`（`saveKey`） | 按钮可用 | 星标 + 「正在写入 .env（600）…」 | success「**key 已保存**」/「写入 .env（600），不回显。」+ 输入框清空 | **空值现在静默 `return`，必须改**：warn「**先把 key 粘进来**」+ `focus()` `#st-key`；其他 danger「**保存 key 失败**」+ `errorText` + 「重试」 | L1+L2 |
| S2 | 「测试连接」`settings.js:59`（`testProvider`） | 按钮可用 | 星标 + 「**正在测试连接（5 秒超时）…**」+ 细进度条；按钮 `aria-disabled` | success + `kv` 表（可达 / HTTP / 延迟 / 模型） | danger「**连不上**」+ `describeError` + 动作「**检查 base_url**」→ `focus()` `#st-base` | L1；5s 由 `api` 超时兜底，超时要落成 `LLM_TIMEOUT` 文案而不是裸错误 |
| S3 | 「保存设置」`settings.js:88` | primary | 星标 + 「正在写入设置…」 | success「**设置已保存**」/「写入 .env（600）与本地设置表。」+ 重载设置 | danger「**保存失败**」+ `errorText` + 「重试」 | L1+L2；`finally` 清态 |
| S4 | 两个开关 `settings.js:35/42` | 开/关 | — | 立即切换 + 按钮旁 `.ux-pending__label`「有未保存的改动」 | — | 本地 flag；不需回滚 |
| S5 | 首屏 `load()` | 骨架 6 行 | 骨架 | 表单填值 | danger「**读不到设置**」+「重试」 | `Promise.all` 里 `llmStatus()` 的 catch 保持（既有），只有 `settings()` 失败才算 error |

### 4.8 全局（跨页）

| # | 动作 | 规格 |
| --- | --- | --- |
| G1 | 任务卡出现（`job-toast.js`） | `role="status"` + `polite`；succeeded 用 圆勾（`.toast.is-succeeded .toast__icon`），failed 用 失败红圆（`.toast.is-failed .toast__icon`）；关闭按钮换 ghost 关闭（`.toast__head > .ui-btn`）；离场 `.toast.is-leaving` + `animationend` 移除 |
| G2 | 任务卡上限 3 条 | 超出显示「还有 N 个任务在进行」（既有） |
| G3 | 失败任务卡 | `role="alert" aria-live="assertive"`（**保留既有例外**：后台任务失败是用户没盯着的，必须打断） |
| G4 | `cancelled` 卡 | 2s 后自动移除（DESIGN §8） |
| G5 | ⌘S / Ctrl+S | 触发当前页主保存动作；pending 中只播报「正在保存…」 |
| G6 | 主题切换 | 无 JS 需求：所有新样式走 token，`[data-theme]` 切换自动生效 |

---

## 5. 落地清单

### 5.1 coder 逐条勾选（按依赖排序）

**A. 接线（已交付 2/3，剩 1 处导出 + 1 行 link）**
- [x] A0 **已交付** `web/src/components/feedback.js`（422 行）：`createAction` / `feedbackRegion` / `inlineError` / `submitGuard` / `optimistic` / `elapsedText` / `PHASE` / `isRetryable`
- [x] A0 **已交付** `web/src/components/toast.js`（269 行）：`toast` 五调（info/success/warn/danger）+ `data-tone` / `is-leaving` / Esc 关闭 / hover 暂停计时 / 焦点归还
- [x] A0 **已交付** `web/src/components/progress.js`（324 行）：`jobProgress()` + 断点记忆轮询（`data-role="job-progress"`、`data-state=running|done|failed`）
- [ ] A1 `web/index.html`：在 `components.css` 之后、`print.css` **之前**插入
      `<link rel="stylesheet" href="./src/styles/uiverse.css" />`
      （顺序是硬约束：晚于 components 才能覆盖状态，早于 print 才不影响打印）
- [ ] A2 `web/src/components/index.js`：补 `export * from "./progress.js";`（当前漏了，页面只能深路径 import）
- [ ] A3 `web/src/components/primitives.js`：`button()` 目前**没有** `state` 参数（状态在 `createAction` 里）。不要再加第二套四态，改为在文档/代码注释里指明「需要四态请用 `createAction`」，避免两套 API 并存
**B. 逐页改反馈（1.5 天）**
- [ ] B1 `pages/workbench.js`：`draft()` 改四态、保留旧草稿；`saveButton` 换成 `createAction()`（四态 + 自带闸）；空文本 `focus()` `#wb-text`（W1–W3）
- [ ] B2 `pages/warehouse.js`：首屏骨架（H1）；搜索保留旧列表 + `aria-busy`（H2）；`verifyButton` 乐观更新 + 回滚，删 `alert()`（`warehouse.js:111`，H4）；空态动作（H5）
- [ ] B3 `pages/templates.js`：`handlePaste` 空值 warn + 聚焦（T2）；`commitButton` 四态 + 成功后焦点搬移（T3）；`setDefault` 乐观 + 删 `alert()`（`templates.js:53`，T4）
- [ ] B4 `pages/jobs.js`：J1 空 JD 聚焦；J4 弹层内按钮 `aria-disabled` + L1；J6 轮询 `aria-busy` + `aria-hidden` 进度；J2/J6 用四态（J1–J7）
- [ ] B5 `pages/builds.js`：`refreshNaming` 300ms 防抖 + `AbortController`（B1）；`assemble` 四态（B2）；`exportPdf` 四态 + 失败不弹 JSON（B3）；字体 banner 加「重新检测字体」（B4）
- [ ] B6 `pages/profile.js`：`refreshNaming` 防抖（P1）；`saveButton` 四态 + 首个 invalid 聚焦（P2）；「保存补充行」四态（P3）
- [ ] B7 `pages/settings.js`：`saveKey` 空值 warn + 聚焦（S1）；`testProvider` 四态（S2）；「保存设置」四态（S3）；脏标记（S4）；首屏骨架（S5）
- [ ] B8 `components/feedback.js`：`paint()` 在 pending 时用 `node.disabled = true`（焦点掉到 `<body>`）。二选一：① 改成 `aria-disabled` + CSS 已就绪；② 保留 `disabled` 但在 `paint()` 里记住 `document.activeElement`，回 idle 时 `focus({preventScroll:true})` 还原

**C. 收尾（0.5 天）**
- [ ] C1 两套通知收敛：`components/job-toast.js`（旧，`is-<status>`）与 `toast.js`（新，`[data-tone]`）并存会让 `#toast-root` 出现两种 DOM。`uiverse.css` §9 已同时覆盖两种写法，迁移时只需保证 failed 仍是 `role="alert"` + `aria-live="assertive"`（G1–G4）
- [ ] C2 `web/src/boot.js`：⌘S / Esc 全局键（G5）；`ev.isComposing` 守卫
- [ ] C3 `docs/DESIGN.md` §0 把样式层顺序更新为 `tokens → base → layout → components → uiverse → print`（本次不改，登记给下一个改 DESIGN 的人）

### 5.2 接线片段（用已交付模块，不重写一套）

页面接一个四态按钮 + 反馈区（工作台「保存为经历」为例）：

```js
import { createAction, feedbackRegion } from "../components/feedback.js";
import { errorText } from "../components/errors.js";

const fb = feedbackRegion({ label: "保存经历状态" });
const save = createAction({
  label: `保存为经历（${bullets.length} 条要点）`,
  pendingLabel: "正在存进经历库…",
  successLabel: "已存进经历库",
  icon: "save",
  variant: "primary",
});

// A. 点按钮触发（createAction 内部已有重入闸 paint(pending) 在 await 之前）
save.node.addEventListener("click", () => {
  save.run(
    () => api.createPackage({ ... }),
    {
      onSuccess: () => fb.success({
        title: "已存进经历库",
        body: "下次组装简历时可以直接引用这条经历。",
        actions: [button({ label: "去经历库看看", onClick: () => { location.hash = "#/warehouse"; } })],
      }),
      onError: (err) => fb.error(err, {
        onRetry: () => save.node.click(),
        onAction: () => { location.hash = "#/profile"; },
      }),
    },
  );
});

// B. 非按钮入口（回车 / ⌘S / 拖拽）用同一个闸
const gate = submitGuard();
form.addEventListener("keydown", (ev) => {
  if (ev.key !== "Enter" || ev.isComposing) return;   // 中文输入法选词回车不算提交
  ev.preventDefault();
  gate(() => save.run(() => api.createPackage({ ... })));
});

// C. 乐观更新（经历库「标记核实」）
optimistic({
  apply: () => { row.classList.add("is-optimistic"); row.setAttribute("aria-busy", "true"); },
  commit: () => api.patch(`/api/v1/packages/${pkgId}/variants/${variantId}`, { verified: true }),
  revert: () => {
    row.classList.remove("is-optimistic");
    row.dataset.state = "error";                       // CSS: 闪红 1.2s
    row.replaceChildren(inlineError(`核实失败：${errorText(err)}`, { onDismiss }));
    window.setTimeout(() => { delete row.dataset.state; }, 1200);
  },
  onError: (err) => fb.error(err),
});
```

长任务（导出 PDF / 分析 JD）：

```js
import { jobProgress } from "../components/progress.js";   // A2 补导出后可从 index.js 取

const prog = jobProgress({ kind: "export" });
statusHost.replaceChildren(prog.node);
const done = await waitJob(jobId);
if (done.status === "succeeded") prog.done(done); else prog.fail(done.error_json);
```

全部用 DOM API / `h()`；`dom.js` 的 `innerHTML` 禁令不受影响。
### 5.3 验收断言（可执行）

```bash
cd resume-warehouse

# 1. 样式表接线与顺序（uiverse 必须在 print 之前）
grep -n "styles/" web/index.html | grep -nE "components|uiverse|print"

# 2. 新 CSS 的离线/纯净自证（应分别输出 0 0 0 0 0）
grep -c "http" web/src/styles/uiverse.css
grep -c "@import" web/src/styles/uiverse.css
grep -c "url(" web/src/styles/uiverse.css
grep -c "!important" web/src/styles/uiverse.css       # 预算 3，实际 0
grep -cE "#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(" web/src/styles/uiverse.css

# 3. 纸张隔离（应输出 0）
grep -cE "\.doc\b|\.doc__|paper-stage|@page" web/src/styles/uiverse.css

# 4. innerHTML 仍为 0（dom.js 的禁令没被绕过）
grep -rn "innerHTML" web/src --include=*.js | wc -l   # 只允许 dom.js 的 FORBIDDEN_PROPS 名单里出现

# 5. 上一轮 alert() 全部清零
grep -rn "alert(" web/src/pages/*.js                    # 期望 0 行

# 6. 防重复：连点两次「保存」在服务端只产生 1 次写请求
#    打开 DevTools Network 过滤 POST，或看 server 日志中同一毫秒前后的请求数

# 7. 在途焦点不丢：pending 期间执行
document.activeElement === document.querySelector("#st-key") // 期望 true
```

```js
// 8. 状态切换不重建按钮（四态不丢焦点、不顶宽）
const btn = document.querySelector(".ui-btn[data-phase]");
const before = btn.getBoundingClientRect();
btn.click();                                  // 进 pending
const during = btn.getBoundingClientRect();
Math.abs(during.width - before.width) <= 1;   // 期望 true（createAction 预留 14px 星标槽位）
getComputedStyle(btn).opacity;                // 期望 "1"（不是 disabled 的 0.45）
document.activeElement === btn;               // 期望 true（B8 修好后）

// 9. 降级：DevTools → Rendering → Emulate prefers-reduced-motion: reduce
//    断言：.ui-spinner / .ux-spin 的 getAnimations() 为空；按钮 click 前后 transform 均为 none

// 10. 深浅色：切换 [data-theme="dark"] 后，.toast / [data-region="feedback"] .ui-callout / .ux-spin
//     的 DevTools 对比度读数 ≥ 4.5:1（正文与按钮文字，DESIGN §3）

// 11. 打印：Cmd+P 预览只含纸张；.doc 宽度仍为 210mm，照片方块 52pt 与偏移未变
```

---

## 6. 与 DESIGN.md 的关系与差异登记

本文件不推翻 DESIGN.md，只补它的「交互反馈」缺口。以下 5 处需要 DESIGN 侧确认（本次按边界未改 DESIGN.md）：

| # | DESIGN.md 现状 | 本次做法 | 建议 |
| --- | --- | --- | --- |
| D1 | §0 样式分层固定为 `tokens→base→layout→components→print` | 新增第 5 层 `uiverse.css` | 更新 §0 为 `…→components→uiverse→print`，并注明「uiverse 层只允许写状态与动效，不得写布局」 |
| D2 | §14 只说「:focus-visible 双层环」 | **在途禁用**建议 `aria-disabled` 而非 `disabled`（防焦点丢失）；已实装的 `createAction` 目前仍用 `disabled`，CSS 已把它在 pending 时的透明度补回 1（否则按钮看起来像坏了） | 补一条规则：「在途禁用优先 aria-disabled；disabled 只用于结构性不可用」，并让 `createAction.paint()` 对齐 |
| D3 | §19.2 把骨架列为「设计了但没实装」 | 本次给出 `.ux-skel-slot`/`--ux-skel-h`/延迟 300ms 的落地方案 | 实装后从 §19.2 删去该条 |
| D4 | uiverse 复选框是圆形 morph | **拒绝改形状**（`.ui-check` 同时是 radio 的容器），只取两段节奏 | 无需改文档，登记设计决策 |
| D5 | §7 错误统一 `role="alert"` | 页面内四态反馈区用 `polite`；`alert` 保留给字段错误、Consent、后台任务 | §14 补「polite/assertive 分工表」（本文件 §3.5 可直接搬） |

---

## 7. 自查记录（2026-10-24，本机执行）

```
$ python3 自查脚本 → web/src/styles/uiverse.css
{'http://': 0, 'https://': 0, '@import': 0, 'url(': 0, '!important': 0}
hex/rgb/hsl 字面色值: []          白/黑字面量: []
.doc / .doc__ / paper-stage / @page 选择器: 0
大括号: 平衡（结构校验通过，无空选择器）
```

- **与已实装代码对齐**：`uiverse.css` v1.1 的挂载点全部取自 `feedback.js` / `toast.js` / `progress.js` 里的真实类名与属性（`data-phase`、`data-region="feedback"`、`data-tone`、`data-role="job-progress"`、`.ui-action__spin`、`.ui-spinner`），不是自造命名。
- **不需要改 JS 就能生效的部分**：按钮按压/悬停、pending 星标（全局替换 `.ui-spinner`）、success/error 着色与抖动、输入焦点下划线、开关按压、复选框两段勾、反馈区入场、toast 圆勾与 ghost 关闭、进度条状态色、骨架 token 化。
- **必须改 JS 的部分**：§5.1 A1（link）、A2（index.js 导出）、B1–B7（7 页接线）、B8（焦点回位）、C1–C2（全局键）。
- 只改了两个文件：`docs/UI-REFRESH.md`（本文件）、`web/src/styles/uiverse.css`。
- **未改动**：任何 `.js`、`web/index.html`、`web/src/styles/print.css`、`server/**`；未 `git commit`、未 `push`。

---

## 附录 A：四态零跳动的升级路径（可选，接 B 段时再决定）

现状 `feedbackRegion()` 是「清空 + 塞一块」，不同状态块高度不同 → 区域会跳一下。若要做到**四态之间零布局跳动且不丢焦点**：

1. 预渲染四个块（内容在状态切换前就位），用同一格叠放：

```js
const wrap = h("div.ux-feedback", { "data-phase": "idle", role: "status", "aria-live": "polite" },
  h("div.ux-feedback__idle", null, idleEl),
  h("div.ux-feedback__pending", null, pendingEl),
  h("div.ux-feedback__success", null, successEl),
  h("div.ux-feedback__error", null, errorEl));
```

2. 配套 CSS（把下面这段贴进 `uiverse.css` §6 末尾即可，纯样式、无逻辑）：

```css
.ux-feedback { display: grid; min-width: 0; }
.ux-feedback[data-phase="idle"] { display: none; }
.ux-feedback > [class^="ux-feedback__"] {
  grid-area: 1 / 1;
  min-width: 0;
  opacity: 0;
  visibility: hidden;
  transition: opacity var(--dur-2) var(--ease), visibility 0s linear var(--dur-2);
}
.ux-feedback[data-phase="idle"] > .ux-feedback__idle,
.ux-feedback[data-phase="pending"] > .ux-feedback__pending,
.ux-feedback[data-phase="success"] > .ux-feedback__success,
.ux-feedback[data-phase="error"] > .ux-feedback__error {
  opacity: 1;
  visibility: visible;
  transition: opacity var(--dur-2) var(--ease), visibility 0s;
}
```

3. 收益：四块同格叠放 ⇒ 容器高度取最大值 ⇒ 状态切换零跳动；`visibility:hidden` 的块不进 Tab 序与读屏；切换不重建节点 ⇒ 不丢焦点、不重播入场。
4. 代价：`idle` 时四块内容仍需存在于 DOM（多几十个节点/页），且 `feedbackRegion` 的 `success()` 可关闭语义要改成「切回 idle」。
