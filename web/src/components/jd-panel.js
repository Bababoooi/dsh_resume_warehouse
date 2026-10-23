/**
 * jd-panel.js — JD + 公司分析
 * 展示要求：需求矩阵（技能 / 类别 / 优先级 / 权重 / 命中包数）+ 覆盖率环 + 已覆盖/缺口 chips。
 * 权重与覆盖率同时给数字，不只给色块（对比度与色觉可达性）。
 */

import { h, cx } from "./dom.js";
import { icon } from "./icons.js";
import { badge, button, chip, emptyState, iconButton, section } from "./primitives.js";

export const PRIORITY_LABELS = { must: "必须", should: "优先", nice: "加分" };
const PRIORITY_TONES = { must: "danger", should: "warn", nice: "neutral" };

/**
 * 职位列表项（左栏 320）
 * @param {{item:{id:string,title:string,company?:string,status?:string,coverage?:number,
 *                created_at?:string,reqs?:number}, active?:boolean, onOpen?:Function}} p
 */
export function jobListItem(p = {}) {
  const it = p.item || {};
  return h(
    "button",
    {
      class: cx("pick-row", p.active ? "is-on" : ""),
      type: "button",
      "aria-current": p.active ? "true" : null,
      onClick: p.onOpen ? () => p.onOpen(it.id) : null,
    },
    h(
      "span",
      { class: "pick-row__main" },
      h("span", { class: "pick-row__title" }, it.title || "未命名职位"),
      h(
        "span",
        { class: "pick-row__meta" },
        it.company || "未填写公司",
        typeof it.coverage === "number" ? h("span", null, `覆盖 ${Math.round(it.coverage * 100)}%`) : null,
      ),
    ),
    typeof it.reqs === "number" ? h("span", { class: "pick-row__meta" }, String(it.reqs)) : null,
  );
}

/**
 * 权重条：宽度按 weight（0–1），同时显示百分比数字
 * @param {{value:number, label?:string}} p
 */
export function weightBar(p = {}) {
  const v = Math.max(0, Math.min(1, Number(p.value) || 0));
  return h(
    "span",
    { class: "weight", title: p.label || `权重 ${Math.round(v * 100)}%` },
    h("span", { class: "weight__track" }, h("span", { class: "weight__fill", style: { width: `${v * 100}%` } })),
    h("span", { class: "weight__val" }, `${Math.round(v * 100)}%`),
  );
}

/**
 * 覆盖率环：conic-gradient + 中心数字 + 文字标签
 * @param {{value:number, label?:string, sub?:string}} p
 */
export function coverageRing(p = {}) {
  const pct = Math.round(Math.max(0, Math.min(1, Number(p.value) || 0)) * 100);
  return h(
    "div",
    {
      class: "ring",
      role: "img",
      "aria-label": `${p.label || "覆盖率"} ${pct}%`,
      style: { "--ring-value": String(pct) },
    },
    h(
      "div",
      { class: "ring__inner" },
      h("span", { class: "ring__value" }, `${pct}%`),
      h("span", { class: "ring__label" }, p.label || "技能覆盖"),
      p.sub ? h("span", { class: "ring__label" }, p.sub) : null,
    ),
  );
}

/**
 * 需求矩阵
 * @param {{requirements:Array<{id?:string,skill:string,category?:string,
 *          priority:"must"|"should"|"nice",weight?:number,hits?:number,
 *          covered?:boolean,source?:string}>,
 *          onFilter?:(p:string)=>void}} p
 */
export function requirementTable(p = {}) {
  const rows = p.requirements || [];
  if (!rows.length) {
    return emptyState({
      icon: "target",
      title: "还没有解析出要求",
      desc: "贴上 JD 原文后，系统会抽取技能、经验年限与硬性条件，并标注必须 / 优先 / 加分。",
    });
  }

  return h(
    "table",
    { class: "req-table" },
    h(
      "thead",
      null,
      h(
        "tr",
        null,
        h("th", { scope: "col" }, "技能 / 要求"),
        h("th", { scope: "col" }, "类别"),
        h("th", { scope: "col" }, "优先级"),
        h("th", { scope: "col" }, "权重"),
        h("th", { scope: "col" }, "命中经历"),
      ),
    ),
    h(
      "tbody",
      null,
      rows.map((r) =>
        h(
          "tr",
          null,
          h(
            "td",
            null,
            h(
              "span",
              { class: "req-table__skill" },
              r.skill,
              r.covered ? badge({ text: "已覆盖", tone: "success" }) : badge({ text: "缺口", tone: "danger" }),
            ),
          ),
          h("td", null, h("span", { class: "small muted" }, r.category || "—")),
          h(
            "td",
            null,
            h(
              "button",
              {
                class: "ui-btn ui-btn--ghost ui-btn--sm",
                type: "button",
                style: { padding: "0" },
                onClick: p.onFilter ? () => p.onFilter(r.priority) : null,
              },
              badge({ text: PRIORITY_LABELS[r.priority] || r.priority, tone: PRIORITY_TONES[r.priority] || "neutral" }),
            ),
          ),
          h("td", null, weightBar({ value: r.weight ?? 0 })),
          h(
            "td",
            null,
            h("span", { class: "mono small" }, `${r.hits ?? 0}`),
            h("span", { class: "small muted" }, " 条"),
          ),
        ),
      ),
    ),
  );
}

/**
 * 已覆盖 / 缺口 chips
 * @param {{covered:string[], gaps:string[], max?:number}} p
 */
export function coverageChips(p = {}) {
  const covered = p.covered || [];
  const gaps = p.gaps || [];
  const max = p.max || 12;
  return h(
    "div",
    { class: "stack" },
    section({
      title: `已覆盖 ${covered.length}`,
      desc: "这些要求在经历库里有对应事实",
      body: h(
        "div",
        { class: "ui-chip-set" },
        covered.slice(0, max).map((s) => chip({ label: s, tone: "success" })),
        covered.length > max ? chip({ label: `+${covered.length - max}`, tone: "neutral" }) : null,
      ),
    }),
    section({
      title: `缺口 ${gaps.length}`,
      desc: "缺的这些不会伪造：要么补一段真实经历，要么在简历里弱化",
      body: h(
        "div",
        { class: "ui-chip-set" },
        gaps.slice(0, max).map((s) => chip({ label: s, tone: "danger" })),
        !gaps.length ? h("span", { class: "small muted" }, "没有缺口，可以放心投。") : null,
      ),
    }),
  );
}

/**
 * 公司招聘偏好（必须有来源标注，不允许编造）
 * @param {{company:{name:string,industry?:string,size?:string,hiring_style?:string,
 *                   notes?:string[],sources?:Array<{title:string,url?:string}>}}} p
 */
export function companyProfile(p = {}) {
  const c = p.company || {};
  const notes = c.notes || [];
  return h(
    "div",
    { class: "stack" },
    h(
      "div",
      { class: "badge-row" },
      badge({ text: c.name || "未填写公司", tone: "accent" }),
      c.industry ? badge({ text: c.industry }) : null,
      c.size ? badge({ text: c.size }) : null,
    ),
    notes.length
      ? h(
          "ul",
          { class: "mini-list", style: { listStyle: "none", padding: "0" } },
          notes.map((n) =>
            h(
              "li",
              { class: "mini-list__row" },
              icon("info", { size: 14, cls: "muted" }),
              h("span", { class: "mini-list__main" }, n),
            ),
          ),
        )
      : h("p", { class: "small muted" }, "还没有足够信息判断招聘偏好。可以补充公司名、行业或招聘页面文本后再分析。"),
    c.sources && c.sources.length
      ? h(
          "details",
          { class: "ui-details" },
          h("summary", null, `依据来源（${c.sources.length}）`),
          h(
            "div",
            { class: "ui-details__body" },
            c.sources.map((s) =>
              h(
                "div",
                { class: "mini-list__row" },
                icon("external", { size: 13, cls: "muted" }),
                h("span", { class: "mini-list__main small" }, s.title || s.url || "未命名来源"),
                s.url ? h("span", { class: "mini-list__meta" }, s.url) : null,
              ),
            ),
          ),
        )
      : null,
  );
}

/**
 * JD 分析空态 / 输入引导
 * @param {{onPaste?:Function, onAnalyze?:Function}} p
 */
export function jobEmpty(p = {}) {
  return emptyState({
    icon: "target",
    title: "还没有目标职位",
    desc: "把 JD 原文粘进来，填上公司名。分析会给出技能需求、优先级与权重，并指出经历库里的覆盖与缺口。",
    actions: [
      button({ label: "粘贴 JD 开始分析", variant: "primary", icon: "plus", onClick: p.onPaste }),
      button({ label: "从 Linked 职位页导入", icon: "globe", onClick: p.onImport }),
    ],
  });
}

/**
 * 分析页布局（左职位列表 / 右详情）
 * @param {{list:Node, detail:Node}} p
 */
export function jobsLayout(p = {}) {
  return h("div", { class: "split--jobs" }, p.list, p.detail);
}

/** 需求矩阵卡（带覆盖环的组合，供详情页复用） */
export function analysisSummary(p = {}) {
  return h(
    "div",
    { class: "grid grid--2" },
    h(
      "div",
      { class: "ui-card ui-card--pad" },
      h("div", { class: "row", style: { gap: "var(--sp-7)", alignItems: "center" } },
        coverageRing({ value: p.coverage || 0, label: "技能覆盖", sub: p.sub }),
        h(
          "div",
          { class: "stack grow" },
          h("div", { class: "small muted" }, "按权重加权后的覆盖率"),
          h("div", { class: "small" }, p.note || "覆盖只统计经历库中可引用的事实，不包含未经验证的内容。"),
          h("div", { class: "badge-row" },
            badge({ text: `必须 ${p.must ?? 0}`, tone: "danger" }),
            badge({ text: `优先 ${p.should ?? 0}`, tone: "warn" }),
            badge({ text: `加分 ${p.nice ?? 0}`, tone: "neutral" }),
          ),
        ),
      ),
    ),
    h(
      "div",
      { class: "ui-card ui-card--pad" },
      section({
        title: "建议下一步",
        body: h(
          "ol",
          { class: "prose small", style: { paddingLeft: "1.1em", margin: 0 } },
          h("li", null, "先补缺口里权重最高的两项——没把握的不要写进简历。"),
          h("li", null, "把命中经历的多条变体按 JD 关键词重排优先级。"),
          h("li", null, "选中文模板组装，导出前逐项检查命名与字段清单。"),
        ),
        actions: p.onBuild ? button({ label: "用这份 JD 组装", size: "sm", variant: "primary", onClick: p.onBuild }) : null,
      }),
    ),
  );
}

export { iconButton };
