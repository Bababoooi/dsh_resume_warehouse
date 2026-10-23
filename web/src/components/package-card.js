/**
 * package-card.js — 经历库（Package）卡片与变体列
 * 数据形状见 docs/DATA-MODEL.md Package / PackageBulletVariant。
 */

import { h, cx } from "./dom.js";
import { icon } from "./icons.js";
import { badge, button, charCount, chip, confidence, emptyState, iconButton } from "./primitives.js";

/** 变体语气 → 中文名（与后端 tone 枚举一致） */
export const TONE_LABELS = {
  impact: "结果导向",
  technical: "技术细节",
  leadership: "协作领导",
  concise: "精简",
  ats: "ATS 关键词",
};

/** 经历类型 */
export const KIND_LABELS = {
  internship: "实习",
  project: "项目",
  research: "科研",
  campus: "校园",
  other: "其他",
};

/**
 * Package 卡片
 * @param {{
 *  item:{id:string,title:string,org?:string,role?:string,kind?:string,summary?:string,
 *        bullets?:number,variants?:number,verified?:number,updated_at?:string,tags?:string[],
 *        is_sample?:boolean, archived?:boolean},
 *  active?:boolean, selected?:boolean, selectable?:boolean,
 *  onOpen?:Function, onToggleSelect?:Function
 * }} p
 */
export function packageCard(p = {}) {
  const it = p.item || {};
  const kind = KIND_LABELS[it.kind] || it.kind || "经历";

  const node = h(
    "article",
    {
      class: cx("pkg-card", p.active ? "is-active" : "", p.selected ? "is-selected" : "", it.is_sample ? "is-sample" : ""),
      tabindex: "0",
      "aria-label": `${it.title || "未命名经历"} 详情`,
      onClick: p.onOpen ? () => p.onOpen(it.id) : null,
      onKeydown: p.onOpen
        ? (ev) => {
            if (ev.key === "Enter" || ev.key === " ") {
              ev.preventDefault();
              p.onOpen(it.id);
            }
          }
        : null,
    },
    h(
      "div",
      { class: "pkg-card__top" },
      h(
        "div",
        { class: "grow stack" },
        h("h3", { class: "pkg-card__title" }, it.title || "未命名经历"),
        h(
          "div",
          { class: "pkg-card__org" },
          [it.org, it.role].filter(Boolean).join(" · ") || "未填写组织 / 角色",
        ),
      ),
      p.selectable
        ? h("input", {
            class: "pkg-card__check",
            type: "checkbox",
            checked: Boolean(p.selected),
            "aria-label": `选择 ${it.title || "这条经历"} 用于组装`,
            onClick: (ev) => ev.stopPropagation(),
            onChange: (ev) => {
              ev.stopPropagation();
              if (p.onToggleSelect) p.onToggleSelect(it.id);
            },
          })
        : null,
    ),
    h(
      "div",
      { class: "pkg-card__meta" },
      badge({ text: kind, tone: it.kind === "internship" ? "accent" : "neutral" }),
      it.verified ? badge({ text: `${it.verified} 条已核实`, tone: "success" }) : null,
      it.is_sample ? badge({ text: "示例数据", tone: "outline" }) : null,
      h("span", { class: "pkg-card__time" }, it.updated_at ? `更新于 ${it.updated_at}` : "尚未更新"),
    ),
    it.summary ? h("p", { class: "pkg-card__summary clamp-2" }, it.summary) : null,
    it.tags && it.tags.length
      ? h("div", { class: "ui-chip-set" }, it.tags.slice(0, 4).map((t) => chip({ label: t })))
      : null,
    h(
      "div",
      { class: "pkg-card__foot" },
      h("span", { class: "pkg-card__count" }, `${it.bullets ?? 0} 条事实`),
      h("span", { class: "pkg-card__count" }, `· ${it.variants ?? 0} 个变体`),
      h("span", { class: "grow" }),
      p.onOpen ? button({ label: "查看", size: "sm", variant: "ghost", iconRight: "chevron-right", onClick: (ev) => { ev.stopPropagation(); p.onOpen(it.id); } }) : null,
    ),
  );

  return node;
}

/** 卡片骨架（列表加载态） */
export function packageCardSkeleton() {
  return h(
    "div",
    { class: "ui-skel ui-skel--block", "aria-hidden": "true", style: { height: "150px" } },
  );
}

/** 经历库空态（引导到对话式录入） */
export function packageEmpty(p = {}) {
  return emptyState({
    icon: "warehouse",
    title: "经历库还是空的",
    desc: "去工作台用对话的方式，把一段实习或项目说清楚——系统会把它拆成可复用的事实条目（bullet）与多种表述变体。",
    actions: [
      button({ label: "去工作台录入", variant: "primary", icon: "chat", onClick: p.onCreate }),
      button({ label: "先导入现有简历", icon: "upload", onClick: p.onImport }),
    ],
  });
}

/**
 * 单个事实条目（bullet）下的变体列
 * @param {{
 *  groupKey:string, fact:string,
 *  variants:Array<{id:string, tone:string, text:string, verified?:boolean, chars?:number,
 *                  max_chars?:number, confidence?:number}>,
 *  onEdit?:(variantId:string, value:string)=>void,
 *  onVerify?:(variantId:string)=>void,
 *  onCopy?:(variantId:string)=>void
 * }} p
 */
export function bulletGroup(p = {}) {
  return h(
    "div",
    { class: "bullet-group" },
    h(
      "div",
      { class: "bullet-group__head" },
      h("span", { class: "bullet-group__key" }, p.groupKey),
      h("span", { class: "clamp-2" }, p.fact),
    ),
    h(
      "div",
      { class: "bullet-group__cols" },
      (p.variants || []).map((v) => variantCard(v, p)),
    ),
  );
}

function variantCard(v, p) {
  return h(
    "div",
    {
      class: cx("variant", v.verified ? "is-verified" : "is-unverified"),
      "aria-label": `${TONE_LABELS[v.tone] || v.tone} 变体`,
    },
    h(
      "div",
      { class: "variant__head" },
      badge({ text: TONE_LABELS[v.tone] || v.tone, tone: v.verified ? "success" : "neutral" }),
      v.verified ? badge({ text: "已核实", tone: "success", dot: true }) : badge({ text: "待核实", tone: "warn", dot: true }),
      typeof v.confidence === "number" ? confidence({ value: v.confidence }) : null,
    ),
    h("textarea", {
      class: "variant__text",
      rows: 3,
      value: v.text || "",
      "aria-label": `${TONE_LABELS[v.tone] || v.tone} 表述`,
      onInput: p.onEdit ? (ev) => p.onEdit(v.id, ev.target.value) : undefined,
    }),
    h(
      "div",
      { class: "variant__foot" },
      charCount({ value: v.text || "", max: v.max_chars || 180 }),
      !v.verified && p.onVerify ? button({ label: "标为已核实", size: "sm", variant: "ghost", onClick: () => p.onVerify(v.id) }) : null,
      p.onCopy ? iconButton({ icon: "copy", label: "复制这条表述", size: "sm", onClick: () => p.onCopy(v.id) }) : null,
    ),
  );
}

/** 变体区空态（只有事实、还没生成变体） */
export function bulletsEmpty(p = {}) {
  return emptyState({
    icon: "sparkles",
    title: "还没有表述变体",
    desc: "可以为同一条事实生成不同语气的写法（结果导向 / 技术细节 / 精简…），组装时按目标职位挑选。",
    actions: [button({ label: "生成变体", variant: "primary", icon: "sparkles", onClick: p.onGenerate })],
  });
}
