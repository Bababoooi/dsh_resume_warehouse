/**
 * import-review.js — 简历导入与模板拆解（校验左预览 / 右结构树）
 * 警告码见 docs/API-CONTRACT.md §14.1；置信度阈值 ≥0.8 高 / 0.6–0.8 中 / <0.6 低。
 */

import { h, cx } from "./dom.js";
import { icon } from "./icons.js";
import {
  badge,
  button,
  callout,
  chip,
  confidence,
  emptyState,
  iconButton,
  section,
} from "./primitives.js";

const STEPS = ["选择文件", "解析内容", "校对结构", "确认入库"];

/** 导入四步进度（当前位置 1-based） */
export function importSteps(p = {}) {
  const current = p.current || 1;
  return h(
    "div",
    { class: "import-steps", role: "list", "aria-label": `导入进度：第 ${current} 步，共 4 步` },
    STEPS.map((label, i) => {
      const n = i + 1;
      const state = n < current ? "is-done" : n === current ? "is-current" : "";
      return [
        i > 0 ? h("i", { class: "import-step__line", "aria-hidden": "true" }) : null,
        h(
          "span",
          {
            class: cx("import-step", state),
            role: "listitem",
            "aria-current": n === current ? "step" : null,
          },
          h("span", { class: "import-step__num", "aria-hidden": "true" }, n < current ? "✓" : String(n)),
          label,
        ),
      ];
    }),
  );
}

/**
 * 原文预览舞台（左 60%）：真实实现由服务端渲染 PDF 页图；
 * 这里给出结构性占位，保证在无后端时也能评审版式。
 * @param {{pages?:number, activePage?:number, highlight?:string, note?:string}} p
 */
export function pdfPreview(p = {}) {
  const pages = p.pages || 1;
  return h(
    "div",
    { class: "pdf-frame" },
    h(
      "div",
      { class: "pdf-page", "aria-label": `简历原文第 ${p.activePage || 1} 页` },
      h("div", { class: "pdf-page__line", style: { width: "38%", height: "12px" } }),
      h("div", { class: "pdf-page__line", style: { width: "62%" } }),
      h("div", { class: "pdf-page__line" }),
      h("div", { class: "pdf-page__line" }),
      h("div", { class: "pdf-page__line pdf-page__line--sm" }),
      h("div", { style: { height: "10px" } }),
      h("div", { class: "pdf-page__line", style: { width: "34%", height: "9px" } }),
      h("div", { class: "pdf-page__line" }),
      h("div", { class: "pdf-page__line pdf-page__highlight", title: p.highlight || "" }),
      h("div", { class: "pdf-page__line" }),
      h("div", { class: "pdf-page__line pdf-page__line--sm" }),
    ),
    pages > 1
      ? h(
          "div",
          { class: "pdf-thumbs", role: "tablist", "aria-label": "页面" },
          Array.from({ length: pages }, (_, i) =>
            h(
              "button",
              {
                class: cx("pdf-thumb", (p.activePage || 1) === i + 1 ? "is-active" : ""),
                type: "button",
                role: "tab",
                "aria-selected": (p.activePage || 1) === i + 1 ? "true" : "false",
                onClick: p.onPage ? () => p.onPage(i + 1) : null,
              },
              `第 ${i + 1} 页`,
            ),
          ),
        )
      : null,
    p.note ? h("p", { class: "small muted" }, p.note) : null,
  );
}

const BLOCK_ICONS = {
  header: "user",
  section: "layers",
  entry: "file",
  bullet: "arrow-right",
  text: "file",
};

const BLOCK_LABELS = {
  header: "头部",
  section: "章节",
  entry: "条目",
  bullet: "要点",
  text: "文本",
};

/**
 * 结构树（右 40%）。每行必须能键盘上移/下移（拖拽之外的第二条路径）。
 * @param {{
 *  blocks:Array<{id:string,type:string,title:string,slots?:number,confidence?:number}>,
 *  activeId?:string,
 *  onSelect?:(id:string)=>void,
 *  onMove?:(id:string, dir:-1|1)=>void
 * }} p
 */
export function blockTree(p = {}) {
  const blocks = p.blocks || [];
  if (!blocks.length) {
    return emptyState({
      icon: "layers",
      title: "还没解析出结构",
      desc: "上传简历后，这里会列出识别到的章节、条目与要点，可逐块调整顺序与归属。",
    });
  }

  return h(
    "div",
    { class: "block-tree", role: "tree", "aria-label": "简历结构" },
    blocks.map((b, i) =>
      h(
        "div",
        {
          class: cx("block-row", p.activeId === b.id ? "is-active" : ""),
          role: "treeitem",
          tabindex: p.activeId === b.id ? "0" : "-1",
          "aria-level": "1",
          "aria-selected": p.activeId === b.id ? "true" : "false",
          onClick: p.onSelect ? () => p.onSelect(b.id) : null,
          onKeydown: (ev) => {
            if (ev.key === "Enter" && p.onSelect) p.onSelect(b.id);
          },
        },
        h("span", { class: "block-row__handle", title: "拖拽排序，或用右侧上下按钮" }, icon("grip", { size: 14 })),
        h("span", { class: "block-row__type", title: BLOCK_LABELS[b.type] || b.type }, icon(BLOCK_ICONS[b.type] || "file", { size: 14 })),
        h(
          "span",
          { class: "stack", style: { minWidth: 0 } },
          h("span", { class: "block-row__title" }, b.title || "未命名区块"),
          h(
            "span",
            { class: "block-row__slots" },
            `${BLOCK_LABELS[b.type] || b.type}`,
            b.slots ? ` · ${b.slots} 个槽位` : "",
          ),
        ),
        typeof b.confidence === "number" ? confidence({ value: b.confidence }) : null,
        h(
          "span",
          { class: "block-row__moves" },
          iconButton({ icon: "arrow-up", label: `上移「${b.title}」`, size: "sm", disabled: i === 0, onClick: () => p.onMove && p.onMove(b.id, -1) }),
          iconButton({ icon: "arrow-down", label: `下移「${b.title}」`, size: "sm", disabled: i === blocks.length - 1, onClick: () => p.onMove && p.onMove(b.id, 1) }),
        ),
      ),
    ),
  );
}

/**
 * 解析警告集中区。
 * 硬要求：CID_GLYPH_MISSING 必须显示具体数字（例：16 处），不得笼统说「部分缺字」。
 * @param {{warnings:Array<{code:string,count?:number,blocks?:string[],message?:string}>, onOpenSettings?:Function}} p
 */
export function importWarnings(p = {}) {
  const list = p.warnings || [];
  if (!list.length) return null;

  return h(
    "div",
    { class: "stack" },
    list.map((w) => {
      switch (w.code) {
        case "CID_GLYPH_MISSING":
          return callout({
            tone: "info",
            icon: "info",
            title: `原文有 ${w.count ?? 0} 处 bullet 标记无法按字符提取（已识别为符号，不影响入库）`,
            body: `这些位置在 PDF 里是字形索引（cid），不是文字。系统已按 bullet 前缀处理并剥离正文，不会当作缺字报错；如原文含正文乱码，请检查第 ${(w.blocks || []).join("、") || "相关"} 块。`,
          });
        case "PHOTO_DETECTED":
          return callout({
            tone: "warn",
            icon: "alert-triangle",
            title: "检测到证件照",
            body: "照片默认不进入模板与导出。若这份简历需要照片位，请在「个人资料」里单独添加，并确认导出语言对应的模板是否启用照片。",
            actions: p.onOpenProfile ? [button({ label: "去个人资料", size: "sm", variant: "ghost", onClick: p.onOpenProfile })] : null,
          });
        case "LOW_CONFIDENCE_BLOCKS":
          return callout({
            tone: "warn",
            icon: "alert-triangle",
            title: `${w.count ?? (w.blocks || []).length} 个区块识别置信度偏低`,
            body: "低置信度区块已用红色标出，请逐块确认标题与槽位归属；未确认前不会写入模板库。",
            actions: (w.blocks || []).slice(0, 4).map((b) => chip({ label: b })),
          });
        case "TEMPLATE_INVALID":
          return callout({
            tone: "danger",
            title: "模板结构不完整",
            body: w.message || "缺少必需槽位，无法保存为可复用模板。",
          });
        default:
          return callout({
            tone: "info",
            title: w.code,
            body: w.message || "解析过程中出现提示，请确认是否影响使用。",
          });
      }
    }),
  );
}

/**
 * 模板卡（模板库三 tab 之一：中文 / 英文 / 草稿）
 * @param {{item:{id:string,name:string,lang:"zh"|"en",updated_at?:string,blocks?:number,
 *                is_default?:boolean,status?:string, source?:string},
 *          active?:boolean, onOpen?:Function, onUse?:Function, onSetDefault?:Function}} p
 */
export function templateCard(p = {}) {
  const it = p.item || {};
  return h(
    "article",
    {
      class: cx("pkg-card", p.active ? "is-active" : ""),
      tabindex: "0",
      onClick: p.onOpen ? () => p.onOpen(it.id) : null,
      onKeydown: p.onOpen
        ? (ev) => {
            if (ev.key === "Enter") p.onOpen(it.id);
          }
        : null,
    },
    h(
      "div",
      { class: "pkg-card__top" },
      h(
        "div",
        { class: "grow stack" },
        h("h3", { class: "pkg-card__title" }, it.name || "未命名模板"),
        h("div", { class: "pkg-card__org" }, it.source || (it.lang === "en" ? "英文模板" : "中文模板")),
      ),
      it.is_default ? badge({ text: "默认", tone: "accent" }) : null,
    ),
    h(
      "div",
      { class: "pkg-card__meta" },
      badge({ text: it.lang === "en" ? "English" : "中文", tone: it.lang === "en" ? "info" : "neutral" }),
      badge({ text: it.status === "draft" ? "草稿" : "可用", tone: it.status === "draft" ? "warn" : "success" }),
      h("span", { class: "pkg-card__time" }, it.updated_at ? `更新于 ${it.updated_at}` : ""),
    ),
    h(
      "div",
      { class: "pkg-card__foot" },
      h("span", { class: "pkg-card__count" }, `${it.blocks ?? 0} 个区块`),
      h("span", { class: "grow" }),
      p.onUse ? button({ label: "用于组装", size: "sm", variant: "ghost", onClick: (ev) => { ev.stopPropagation(); p.onUse(it.id); } }) : null,
      p.onSetDefault ? button({ label: "设为默认", size: "sm", variant: "quiet", onClick: (ev) => { ev.stopPropagation(); p.onSetDefault(it.id); } }) : null,
    ),
  );
}

/** 模板库空态 */
export function templateEmpty(p = {}) {
  return emptyState({
    icon: "template",
    title: "还没有模板",
    desc: "导入一份现有简历即可拆解为可重组模板；也可以从内置版式开始，再按自己的偏好调整章节顺序。",
    actions: [
      button({ label: "导入现有简历", variant: "primary", icon: "upload", onClick: p.onImport }),
      button({ label: "查看内置版式", icon: "template", onClick: p.onBuiltin }),
    ],
  });
}

/** 槽位编辑行（结构树选中块后展开） */
export function slotRow(p = {}) {
  return h(
    "div",
    { class: "slot-row" },
    h("span", { class: "mono small muted" }, p.key),
    h("span", { class: "small" }, p.value || "（空）"),
    badge({ text: p.required ? "必需" : "可选", tone: p.required ? "warn" : "neutral" }),
    p.onEdit ? iconButton({ icon: "edit", label: `编辑槽位 ${p.key}`, size: "sm", onClick: p.onEdit }) : null,
  );
}

/** 校对页的整体骨架（左预览 / 右结构树） */
export function reviewLayout(p = {}) {
  return h(
    "div",
    { class: "split--review" },
    section({ title: "原文预览", desc: "点击右侧区块可高亮对应位置", body: p.preview }),
    section({
      title: "结构树",
      desc: "确认标题、顺序与槽位归属",
      actions: p.treeActions ? p.treeActions : null,
      body: p.tree,
    }),
  );
}

/* ============================================================================
   校对页增强（v1.1）：草稿横幅 / 章节-条目-要点三级树 / 数字高亮 / 异常区 / 底部动作
   硬要求（captain 2026-10-23）：
   1. 左原件预览 + 右结构化树（section → entry → bullet），改动只落 ImportJob.draft_json，
      点「确认入库」才 commit；页面必须明示「这是草稿，未入库」。
   2. 每个 block 可改名 / 合并 / 拆分 / 拖入其它 section / 删除。
   3. bullet 里的数字（含百分号、区间、倍数）必须视觉高亮，让用户一眼核对「数字有没有被吞」。
   4. 异常（(cid:127)、U+FFFD、缺 section、bullet 为 0）必须显性告警，不许静默通过。
   ========================================================================== */

/** 章节类型 → 中文名与图标（与 TemplateBlock / ImportJob 的 section 类型对齐） */
export const SECTION_META = {
  education: { label: "教育背景", icon: "template" },
  experience: { label: "实习经历", icon: "warehouse" },
  project: { label: "项目经历", icon: "layers" },
  campus: { label: "校园活动", icon: "user" },
  skills: { label: "职业技能", icon: "sparkles" },
  summary: { label: "个人简介", icon: "file" },
  other: { label: "其它", icon: "file" },
};

const NUMBER_RE = /\d+(?:[.,]\d+)*(?:\s*(?:%|％|‰|倍|万|亿|k|K|ms|s|分钟|小时|天|周|月|年|页|人|条|个|次|项|所|篇|字))?/g;

/**
 * 把一个字符串拆成「普通文本 / 数字片段」两类，用于数字高亮。
 * 纯函数，不碰 DOM；返回 [{text:string, num?:boolean}]
 */
export function splitNumbers(text) {
  const src = String(text == null ? "" : text);
  const out = [];
  let last = 0;
  for (const m of src.matchAll(NUMBER_RE)) {
    if (m.index > last) out.push({ text: src.slice(last, m.index) });
    out.push({ text: m[0], num: true });
    last = m.index + m[0].length;
  }
  if (last < src.length) out.push({ text: src.slice(last) });
  return out;
}

/** 统计一段文本里的数字片段数（用于「这条 bullet 有 4 个数字」提示） */
export function countNumbers(text) {
  return splitNumbers(text).filter((p) => p.num).length;
}

/** 数字高亮渲染：返回节点数组，可直接作为 h() 的 children */
export function highlightNumbers(text, opts = {}) {
  return splitNumbers(text).map((p) =>
    p.num ? h("mark", { class: "num" }, p.text) : p.text,
  );
}

/**
 * 草稿横幅：明确「未入库 + 自动保存时间 + 放弃草稿」
 * @param {{savedAt?:string, dirty?:boolean, onDiscard?:Function, onPreview?:Function}} p
 */
export function draftBanner(p = {}) {
  return h(
    "div",
    { class: cx("draft-banner", p.dirty ? "is-dirty" : ""), role: "status" },
    h("span", { class: "draft-banner__icon" }, icon("edit", { size: 14 })),
    h(
      "span",
      { class: "draft-banner__main" },
      h("b", null, "这是草稿，还没有入库。"),
      h(
        "span",
        { class: "draft-banner__sub" },
        p.savedAt ? `改动已自动保存在本机（${p.savedAt}）` : "改动只保存在本机，不会上传",
        " · 点「确认入库」后才写入经历库与模板库",
      ),
    ),
    h(
      "span",
      { class: "draft-banner__actions" },
      p.onPreview
        ? button({ label: "预览将生成的模板", size: "sm", variant: "quiet", onClick: p.onPreview })
        : null,
      p.onDiscard
        ? button({ label: "放弃草稿", size: "sm", variant: "ghost", onClick: p.onDiscard })
        : null,
    ),
  );
}

/**
 * 单条 bullet 行：数字高亮 + 数字计数 + 置信度 + 行内动作（编辑/拆分/删除/移动）
 * @param {{id:string, text:string, confidence?:number, active?:boolean,
 *          onSelect?:Function, onEdit?:Function, onSplit?:Function, onDelete?:Function,
 *          onMove?:Function, showActions?:boolean}} p
 */
export function bulletRow(p = {}) {
  const n = countNumbers(p.text);
  return h(
    "div",
    {
      class: cx("tree-bullet", p.active ? "is-active" : ""),
      role: "treeitem",
      "aria-level": "3",
      tabindex: p.active ? "0" : "-1",
      "aria-selected": p.active ? "true" : "false",
      onClick: p.onSelect ? () => p.onSelect(p.id) : null,
      onKeydown: p.onSelect
        ? (ev) => {
            if (ev.key === "Enter") p.onSelect(p.id);
          }
        : null,
    },
    h("span", { class: "tree-bullet__handle", "aria-hidden": "true" }, icon("grip", { size: 12 })),
    h("span", { class: "tree-bullet__text" }, highlightNumbers(p.text || "")),
    h(
      "span",
      { class: "tree-bullet__meta", title: `这条要点里有 ${n} 个数字，导出时会逐字保留` },
      h("i", { class: cx("num-dot", n ? "is-ok" : "is-risk"), "aria-hidden": "true" }),
      `${n} 个数字`,
      typeof p.confidence === "number" ? confidence({ value: p.confidence }) : null,
    ),
    p.showActions === false
      ? null
      : h(
          "span",
          { class: "tree-bullet__actions" },
          iconButton({ icon: "edit", label: `编辑要点：${(p.text || "").slice(0, 12)}…`, size: "sm", onClick: p.onEdit }),
          iconButton({ icon: "split", label: "拆成两条要点", size: "sm", onClick: p.onSplit }),
          iconButton({ icon: "arrow-up", label: "上移这条要点", size: "sm", onClick: () => p.onMove && p.onMove(p.id, -1) }),
          iconButton({ icon: "arrow-down", label: "下移这条要点", size: "sm", onClick: () => p.onMove && p.onMove(p.id, 1) }),
          iconButton({ icon: "trash", label: "删除这条要点", size: "sm", onClick: p.onDelete }),
        ),
  );
}

/**
 * entry 行（公司/项目名 + 日期 + 角色 + bullet 数），可改名/拆分/删除/移动到其它 section
 * @param {{entry:{id:string,title:string,org?:string,role?:string,date?:string,
 *                 bullets:Array<{id:string,text:string,confidence?:number}>, confidence?:number},
 *          activeId?:string, onSelect?:Function, onRename?:Function, onSplit?:Function,
 *          onDelete?:Function, onMoveTo?:Function, onMove?:Function}} p
 */
export function entryNode(p = {}) {
  const e = p.entry || {};
  const bullets = e.bullets || [];
  return h(
    "div",
    { class: "tree-entry", role: "group" },
    h(
      "div",
      {
        class: cx("tree-entry__head", e.id === p.activeId ? "is-active" : ""),
        role: "treeitem",
        "aria-level": "2",
        tabindex: "0",
        onClick: p.onSelect ? () => p.onSelect(e.id) : null,
        onKeydown: p.onSelect
          ? (ev) => {
              if (ev.key === "Enter") p.onSelect(e.id);
            }
          : null,
      },
      h("span", { class: "tree-entry__handle", title: "拖到其它章节可改归属；也可用「移动到…」按钮" }, icon("grip", { size: 13 })),
      h(
        "span",
        { class: "tree-entry__main" },
        h("span", { class: "tree-entry__title" }, e.title || "未命名条目"),
        h(
          "span",
          { class: "tree-entry__meta" },
          e.org ? h("span", null, e.org) : null,
          e.role ? h("span", null, ` · ${e.role}`) : null,
          e.date ? h("span", { class: "mono" }, ` · ${e.date}`) : null,
          h("span", null, ` · ${bullets.length} 条要点`),
        ),
      ),
      typeof e.confidence === "number" ? confidence({ value: e.confidence }) : null,
      h(
        "span",
        { class: "tree-entry__actions" },
        iconButton({ icon: "edit", label: `重命名条目：${e.title || ""}`, size: "sm", onClick: p.onRename }),
        p.onMoveTo
          ? iconButton({ icon: "folder", label: `把「${e.title || "该条目"}」移动到其它章节`, size: "sm", onClick: p.onMoveTo })
          : null,
        iconButton({ icon: "split", label: "把这条经历拆成两条", size: "sm", onClick: p.onSplit }),
        iconButton({ icon: "arrow-up", label: "上移这条经历", size: "sm", onClick: () => p.onMove && p.onMove(e.id, -1) }),
        iconButton({ icon: "arrow-down", label: "下移这条经历", size: "sm", onClick: () => p.onMove && p.onMove(e.id, 1) }),
        iconButton({ icon: "trash", label: `删除条目：${e.title || ""}`, size: "sm", onClick: p.onDelete }),
      ),
    ),
    bullets.length
      ? h(
          "div",
          { class: "tree-entry__bullets", role: "group", "aria-label": `${e.title || "条目"}的要点` },
          bullets.map((b) =>
            bulletRow({
              id: b.id,
              text: b.text,
              confidence: b.confidence,
              active: p.activeId === b.id,
              onSelect: p.onSelect,
              onEdit: p.onEditBullet,
              onSplit: p.onSplitBullet,
              onDelete: p.onDeleteBullet,
              onMove: p.onMoveBullet,
            }),
          ),
        )
      : h(
          "div",
          { class: "tree-entry__empty" },
          h("span", { class: "small" }, "这条经历没有识别到要点（解析异常？）"),
          button({ label: "手动加一条", size: "sm", variant: "quiet", icon: "plus", onClick: p.onAddBullet }),
        ),
  );
}

/**
 * section 节点（教育背景 / 实习经历 / 项目经历 / 校园活动 / 职业技能）
 * @param {{section:{id:string,type:string,title?:string,entries?:Array<any>,bullets?:Array<any>,confidence?:number},
 *          collapsed?:boolean, activeId?:string, onToggle?:Function, onRename?:Function,
 *          onMerge?:Function, onDelete?:Function, onAddEntry?:Function, onMove?:Function,
 *          entryProps?:object}} p
 */
export function sectionNode(p = {}) {
  const s = p.section || {};
  const meta = SECTION_META[s.type] || SECTION_META.other;
  const entries = s.entries || [];
  const loose = s.bullets || [];
  const bulletCount = entries.reduce((n, e) => n + (e.bullets ? e.bullets.length : 0), loose.length);
  const collapsed = !!p.collapsed;

  return h(
    "section",
    { class: cx("tree-section", collapsed ? "is-collapsed" : ""), "aria-label": s.title || meta.label },
    h(
      "header",
      { class: "tree-section__head", role: "treeitem", "aria-level": "1", "aria-expanded": collapsed ? "false" : "true", tabindex: "0" },
      iconButton({ icon: collapsed ? "chevron-right" : "chevron-down", label: collapsed ? "展开本章节" : "收起本章节", size: "sm", onClick: p.onToggle }),
      h("span", { class: "tree-section__icon" }, icon(meta.icon, { size: 15 })),
      h("span", { class: "tree-section__title" }, s.title || meta.label),
      badge({ text: `${entries.length} 条 · ${bulletCount} 点`, tone: "neutral" }),
      typeof s.confidence === "number" ? confidence({ value: s.confidence }) : null,
      h("span", { class: "grow" }),
      h(
        "span",
        { class: "tree-section__actions" },
        iconButton({ icon: "edit", label: `重命名章节：${s.title || meta.label}`, size: "sm", onClick: p.onRename }),
        p.onMerge ? iconButton({ icon: "merge", label: "合并到其它章节", size: "sm", onClick: p.onMerge }) : null,
        p.onAddEntry ? iconButton({ icon: "plus", label: `在「${s.title || meta.label}」里加一条`, size: "sm", onClick: p.onAddEntry }) : null,
        p.onDelete ? iconButton({ icon: "trash", label: `删除章节：${s.title || meta.label}`, size: "sm", onClick: p.onDelete }) : null,
      ),
    ),
    collapsed
      ? null
      : h(
          "div",
          { class: "tree-section__body" },
          entries.length
            ? entries.map((e) =>
                entryNode({
                  entry: e,
                  activeId: p.activeId,
                  onSelect: p.entryProps && p.entryProps.onSelect,
                  onRename: p.entryProps && p.entryProps.onRename,
                  onSplit: p.entryProps && p.entryProps.onSplit,
                  onDelete: p.entryProps && p.entryProps.onDelete,
                  onMoveTo: p.entryProps && p.entryProps.onMoveTo,
                  onMove: p.entryProps && p.entryProps.onMove,
                  onEditBullet: p.entryProps && p.entryProps.onEditBullet,
                  onSplitBullet: p.entryProps && p.entryProps.onSplitBullet,
                  onDeleteBullet: p.entryProps && p.entryProps.onDeleteBullet,
                  onMoveBullet: p.entryProps && p.entryProps.onMoveBullet,
                  onAddBullet: p.entryProps && p.entryProps.onAddBullet,
                }),
              )
            : loose.length
              ? loose.map((b) =>
                  bulletRow({
                    id: b.id,
                    text: b.text,
                    confidence: b.confidence,
                    active: p.activeId === b.id,
                    onSelect: p.entryProps && p.entryProps.onSelect,
                  }),
                )
              : h("div", { class: "tree-section__empty" }, "本章节没有识别到内容 —— 可手动新增，或从其它章节拖入。"),
        ),
  );
}

/**
 * 结构树（三级）容器
 * @param {{sections:Array<any>, activeId?:string, collapsedIds?:string[], onToggleSection?:Function,
 *          sectionProps?:object, entryProps?:object}} p
 */
export function structureTree(p = {}) {
  const sections = p.sections || [];
  if (!sections.length) {
    return emptyState({
      icon: "layers",
      title: "还没解析出章节",
      desc: "换一份文件重试，或手动新建章节后再入库。若原文件是扫描件，先做 OCR 会明显提高识别率。",
    });
  }
  return h(
    "div",
    { class: "block-tree block-tree--nested", role: "tree", "aria-label": "简历结构：章节 / 条目 / 要点" },
    sections.map((s) =>
      sectionNode({
        section: s,
        collapsed: (p.collapsedIds || []).includes(s.id),
        activeId: p.activeId,
        onToggle: () => p.onToggleSection && p.onToggleSection(s.id),
        ...(p.sectionProps || {}),
        entryProps: p.entryProps,
      }),
    ),
  );
}

/**
 * 异常提示区：不许静默通过。
 * @param {{items:Array<{code:string,count?:number,detail?:string,block?:string,tone?:string,
 *                       fixLabel?:string,onFix?:Function}>, onJumpTo?:Function}} p
 */
export function importAnomalies(p = {}) {
  const items = p.items || [];
  if (!items.length) {
    return callout({
      tone: "success",
      icon: "check-circle",
      title: "没有发现解析异常",
      body: "章节、条目与数字都齐。可以逐块复核后入库。",
    });
  }
  return h(
    "div",
    { class: "anomaly-list", role: "list", "aria-label": "解析异常" },
    items.map((it) => {
      const tone = it.tone || "warn";
      const text =
        it.code === "REPLACEMENT_CHAR"
          ? `有 ${it.count ?? 0} 个乱码字符（U+FFFD），说明原文字形缺失`
          : it.code === "CID_UNMAPPED"
            ? `有 ${it.count ?? 0} 处 (cid:127) 类字形索引未能映射为文字`
            : it.code === "NO_SECTION"
              ? "没有识别到任何章节"
              : it.code === "EMPTY_BULLETS"
                ? `${it.count ?? 0} 个条目没有要点`
                : it.code === "NUMBER_LOST"
                  ? `有 ${it.count ?? 0} 条要点疑似丢失数字（原文有数字，解析结果没有）`
                  : it.detail || it.code;
      return h(
        "div",
        { class: cx("anomaly", `anomaly--${tone}`), role: "listitem" },
        icon(tone === "danger" ? "alert-circle" : "alert-triangle", { size: 15 }),
        h(
          "span",
          { class: "anomaly__main" },
          h("span", { class: "anomaly__title" }, text),
          it.detail && it.code !== "REPLACEMENT_CHAR" && it.code !== "NUMBER_LOST"
            ? h("span", { class: "anomaly__detail" }, it.detail)
            : null,
          it.block ? h("span", { class: "anomaly__where mono" }, `位置：${it.block}`) : null,
        ),
        it.fixLabel && it.onFix
          ? button({ label: it.fixLabel, size: "sm", variant: "ghost", onClick: it.onFix })
          : it.block && p.onJumpTo
            ? button({ label: "定位", size: "sm", variant: "ghost", onClick: () => p.onJumpTo(it.block) })
            : null,
      );
    }),
  );
}

/**
 * 校对统计条：章节数 / 条目数 / 要点数 / 数字总数 / 待确认数
 * @param {{sections:number, entries:number, bullets:number, numbers:number, lowConfidence?:number, pages?:number}} p
 */
export function reviewSummary(p = {}) {
  const cells = [
    { k: "章节", v: p.sections ?? 0 },
    { k: "条目", v: p.entries ?? 0 },
    { k: "要点", v: p.bullets ?? 0 },
    { k: "数字", v: p.numbers ?? 0, tone: "accent" },
    { k: "待确认", v: p.lowConfidence ?? 0, tone: (p.lowConfidence || 0) > 0 ? "warn" : "success" },
  ];
  return h(
    "div",
    { class: "review-summary", role: "list", "aria-label": "解析结果统计" },
    cells.map((c) =>
      h(
        "span",
        { class: cx("review-summary__cell", c.tone ? `is-${c.tone}` : ""), role: "listitem" },
        h("b", null, String(c.v)),
        h("span", null, c.k),
      ),
    ),
  );
}

/**
 * 底部动作条：确认入库（主）/ 放弃（次，二次确认）
 * @param {{canCommit?:boolean, blockedReason?:string, committing?:boolean,
 *          onCommit?:Function, onDiscard?:Function, onSaveDraft?:Function}} p
 */
export function reviewFooter(p = {}) {
  return h(
    "div",
    { class: "review-foot" },
    h(
      "span",
      { class: "review-foot__note" },
      p.canCommit === false
        ? [
            h("i", { class: "status-dot status-dot--warn", "aria-hidden": "true" }),
            p.blockedReason || "还有需要确认的区块，处理完才能入库。",
          ]
        : [
            h("i", { class: "status-dot status-dot--ok", "aria-hidden": "true" }),
            "入库后可在经历库与模板库里继续编辑；原文件会保留在 data/imports。",
          ],
    ),
    h(
      "span",
      { class: "review-foot__actions" },
      p.onSaveDraft ? button({ label: "仅保存草稿", onClick: p.onSaveDraft }) : null,
      p.onDiscard ? button({ label: "放弃", variant: "ghost", onClick: p.onDiscard }) : null,
      button({
        label: p.committing ? "正在入库…" : "确认入库",
        variant: "primary",
        icon: "check",
        loading: p.committing,
        disabled: p.canCommit === false,
        onClick: p.onCommit,
      }),
    ),
  );
}
