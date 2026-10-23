/**
 * primitives.js — 基础展示组件
 *
 * 统一约定（DESIGN.md §4）：
 *  - 每个组件是纯函数：入参 props → 返回 DOM 节点；
 *  - 不发起请求、不读全局状态、不写 localStorage；
 *  - 交互只通过回调（onClick / onChange）交给页面层；
 *  - 所有用户可见文本一律走 Text 节点（h() 保证）。
 */

import { h, cx, trapFocus, focusFirst } from "./dom.js";
import { icon } from "./icons.js";

/* ---------------------------------------------------------------- 按钮 */

/**
 * @param {object} p
 * @param {string} p.label
 * @param {"primary"|"secondary"|"ghost"|"quiet"|"danger"|"danger-ghost"} [p.variant]
 * @param {"sm"|"md"|"lg"} [p.size]
 * @param {string} [p.icon] icons.js 中的图标名
 * @param {string} [p.iconRight]
 * @param {string} [p.kbd] 展示的快捷键提示（仅视觉，不绑键）
 * @param {boolean} [p.block]
 * @param {boolean} [p.disabled]
 * @param {boolean} [p.loading]
 * @param {"button"|"submit"} [p.type]
 * @param {string} [p.title]
 * @param {string} [p.ariaLabel]
 * @param {(ev:MouseEvent)=>void} [p.onClick]
 */
export function button(p = {}) {
  const {
    label,
    variant = "secondary",
    size,
    icon: iconName,
    iconRight,
    kbd,
    block,
    disabled,
    loading,
    type = "button",
    title,
    ariaLabel,
    onClick,
  } = p;

  const classes = [
    "ui-btn",
    variant === "secondary" ? "" : `ui-btn--${variant}`,
    size ? `ui-btn--${size}` : "",
    block ? "ui-btn--block" : "",
    loading ? "is-loading" : "",
  ];

  const node = h(
    "button",
    {
      class: cx(...classes),
      type,
      title,
      "aria-label": ariaLabel,
      "aria-busy": loading ? "true" : null,
      disabled: Boolean(disabled || loading),
      onClick,
    },
    iconName ? icon(iconName, { size: size === "sm" ? 14 : 15, cls: "ui-btn__icon" }) : null,
    label ? h("span", null, label) : null,
    iconRight ? icon(iconRight, { size: 14, cls: "ui-btn__icon" }) : null,
    kbd ? h("span", { class: "ui-btn__kbd" }, kbd) : null,
    loading ? h("span", { class: "ui-spinner" }) : null,
  );

  return node;
}

/** 纯图标按钮（必须有可读标签，用于 aria-label） */
export function iconButton(p = {}) {
  return h(
    "button",
    {
      class: cx("ui-btn", `ui-btn--${p.variant || "ghost"}`, p.size === "sm" ? "ui-btn--sm" : "", "ui-btn--icon"),
      type: "button",
      title: p.label,
      "aria-label": p.label,
      disabled: p.disabled,
      onClick: p.onClick,
    },
    icon(p.icon, { size: p.size === "sm" ? 14 : 16 }),
  );
}

/* ---------------------------------------------------------------- 徽标 / chip */

/**
 * @param {{text:string, tone?:string, dot?:boolean}} p
 * tone: neutral | success | warn | danger | info | accent | outline
 */
export function badge(p = {}) {
  return h(
    "span",
    { class: cx("ui-badge", p.tone && p.tone !== "neutral" ? `ui-badge--${p.tone}` : "") },
    p.dot ? h("i", { class: "ui-badge__dot" }) : null,
    p.text,
  );
}

/** 可点/可删的小标签 */
export function chip(p = {}) {
  const { label, tone, mono, onClick, onRemove, title, disabled } = p;
  const isButton = Boolean(onClick);
  const base = h(
    isButton ? "button" : "span",
    {
      class: cx("ui-chip", tone ? `ui-chip--${tone}` : "", onClick ? "ui-chip--btn" : ""),
      type: isButton ? "button" : null,
      title,
      "aria-disabled": disabled ? "true" : null,
      onClick: disabled ? null : onClick,
      style: mono ? { fontFamily: "var(--font-mono)", fontSize: "var(--fs-11)" } : null,
    },
    label,
    onRemove
      ? h(
          "span",
          {
            class: "ui-chip__x",
            role: "button",
            tabindex: "0",
            "aria-label": `移除 ${label}`,
            onClick: (ev) => {
              ev.stopPropagation();
              onRemove();
            },
            onKeydown: (ev) => {
              if (ev.key === "Enter" || ev.key === " ") {
                ev.preventDefault();
                ev.stopPropagation();
                onRemove();
              }
            },
          },
          icon("x", { size: 10 }),
        )
      : null,
  );
  return base;
}

export function chipSet(items = [], opts = {}) {
  return h(
    "div",
    { class: "ui-chip-set" },
    items.map((it) =>
      typeof it === "string"
        ? chip({ label: it, tone: opts.tone })
        : chip(it),
    ),
  );
}

/* ---------------------------------------------------------------- 表单 */

/** label + 控件 + 提示 + 错误 的容器 */
export function field(p = {}) {
  const { label, control, required, note, hint, error, id, full } = p;
  return h(
    "div",
    { class: cx("ui-field", full ? "ui-field--full" : "") },
    label
      ? h(
          "label",
          { class: "ui-field__label", for: id },
          label,
          required ? h("span", { class: "ui-field__req", "aria-hidden": "true" }, "*") : null,
          note ? h("span", { class: "ui-field__note" }, note) : null,
        )
      : null,
    control,
    hint ? h("div", { class: "ui-field__hint" }, hint) : null,
    error
      ? h(
          "div",
          { class: "ui-field__error", role: "alert" },
          icon("alert-circle", { size: 13 }),
          h("span", null, error),
        )
      : null,
  );
}

/**
 * 文本输入
 * @param {{id?:string, value?:string, placeholder?:string, type?:string,
 *          mono?:boolean, invalid?:boolean, disabled?:boolean, autocomplete?:string,
 *          onInput?:(v:string,ev:Event)=>void, describedBy?:string, maxLength?:number}} p
 */
export function input(p = {}) {
  return h("input", {
    class: cx("ui-input", p.mono ? "ui-input--mono" : "", p.lg ? "ui-input--lg" : ""),
    id: p.id,
    type: p.type || "text",
    value: p.value ?? "",
    placeholder: p.placeholder,
    inputmode: p.inputmode,
    autocomplete: p.autocomplete,
    "aria-invalid": p.invalid ? "true" : null,
    "aria-describedby": p.describedBy,
    disabled: p.disabled,
    maxlength: p.maxLength,
    onInput: p.onInput ? (ev) => p.onInput(ev.target.value, ev) : undefined,
  });
}

export function textarea(p = {}) {
  return h("textarea", {
    class: cx("ui-textarea", p.mono ? "ui-textarea--mono" : ""),
    id: p.id,
    rows: p.rows || 3,
    value: p.value ?? "",
    placeholder: p.placeholder,
    "aria-invalid": p.invalid ? "true" : null,
    "aria-describedby": p.describedBy,
    disabled: p.disabled,
    onInput: p.onInput ? (ev) => p.onInput(ev.target.value, ev) : undefined,
  });
}

/**
 * 下拉选择
 * @param {{id?:string, value?:string, options:Array<{value:string,label:string,disabled?:boolean}>,
 *          onChange?:(v:string,ev:Event)=>void, disabled?:boolean, invalid?:boolean}} p
 */
export function select(p = {}) {
  const node = h(
    "select",
    {
      class: "ui-select",
      id: p.id,
      "aria-invalid": p.invalid ? "true" : null,
      disabled: p.disabled,
      onChange: p.onChange ? (ev) => p.onChange(ev.target.value, ev) : undefined,
    },
    (p.options || []).map((o) =>
      h(
        "option",
        { value: o.value, selected: String(o.value) === String(p.value) ? true : null, disabled: o.disabled },
        o.label,
      ),
    ),
  );
  return node;
}

/** 复选框（label 可含说明） */
export function checkbox(p = {}) {
  return h(
    "label",
    { class: "ui-check" },
    h("input", {
      type: "checkbox",
      checked: Boolean(p.checked),
      disabled: p.disabled,
      onChange: p.onChange ? (ev) => p.onChange(ev.target.checked, ev) : undefined,
      name: p.name,
      value: p.value,
    }),
    h(
      "span",
      { class: "ui-check__text" },
      p.label,
      p.meta ? h("span", { class: "ui-check__meta" }, ` ${p.meta}`) : null,
    ),
  );
}

/** 开关（role=switch，视觉与状态都不只靠颜色） */
export function toggle(p = {}) {
  const btn = h(
    "button",
    {
      class: "ui-switch",
      type: "button",
      role: "switch",
      "aria-checked": p.checked ? "true" : "false",
      "aria-disabled": p.disabled ? "true" : null,
      onClick: p.onChange && !p.disabled ? () => p.onChange(!p.checked) : null,
    },
    h("span", { class: "ui-switch__track" }, h("span", { class: "ui-switch__thumb" })),
    p.label ? h("span", null, p.label) : null,
  );
  return btn;
}

/**
 * 分段控件
 * @param {{options:Array<{value:string,label:string,badge?:string,disabled?:boolean}>,
 *          value:string, onChange?:(v:string)=>void, block?:boolean, label?:string}} p
 */
export function segmented(p = {}) {
  const group = h(
    "div",
    {
      class: cx("ui-seg", p.block ? "ui-seg--block" : ""),
      role: "radiogroup",
      "aria-label": p.label,
    },
    (p.options || []).map((o) =>
      h(
        "button",
        {
          class: "ui-seg__opt",
          type: "button",
          role: "radio",
          "aria-checked": String(o.value) === String(p.value) ? "true" : "false",
          "aria-disabled": o.disabled ? "true" : null,
          disabled: o.disabled,
          onClick: o.disabled || !p.onChange ? null : () => p.onChange(o.value),
        },
        o.label,
        o.badge ? h("span", { class: "ui-seg__badge" }, o.badge) : null,
      ),
    ),
  );
  return group;
}

/** 文件选择区（纯展示：只把 File 交给回调，不上传） */
export function filePicker(p = {}) {
  const inputEl = h("input", {
    type: "file",
    accept: p.accept || ".pdf,.docx,.md,.txt",
    onChange: (ev) => {
      const file = ev.target.files && ev.target.files[0];
      if (file && p.onSelect) p.onSelect(file);
    },
  });

  const zone = h(
    "label",
    {
      class: "ui-file",
      onDragover: (ev) => {
        ev.preventDefault();
        zone.classList.add("is-dragover");
      },
      onDragleave: () => zone.classList.remove("is-dragover"),
      onDrop: (ev) => {
        ev.preventDefault();
        zone.classList.remove("is-dragover");
        const file = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
        if (file && p.onSelect) p.onSelect(file);
      },
    },
    inputEl,
    h("span", { class: "ui-file__icon" }, icon("upload", { size: 16 })),
    h(
      "span",
      { class: "stack" },
      h("strong", { class: "small" }, p.title || "选择文件，或拖到这里"),
      h(
        "span",
        { class: "small muted" },
        p.hint || "支持 PDF / DOCX / Markdown / 纯文本；文件只在本机解析，不会上传",
      ),
    ),
  );
  return zone;
}

/* ---------------------------------------------------------------- 提示 */

/**
 * 提示条
 * @param {{tone?:"info"|"warn"|"danger"|"success", title?:string, body?:string|Node,
 *          actions?:Node[], icon?:string}} p
 */
export function callout(p = {}) {
  const tone = p.tone || "info";
  const iconName =
    p.icon || { info: "info", warn: "alert-triangle", danger: "alert-circle", success: "check-circle" }[tone];
  return h(
    "div",
    { class: `ui-callout ui-callout--${tone}`, role: tone === "danger" ? "alert" : "status" },
    icon(iconName, { size: 16, cls: "ui-callout__icon" }),
    h(
      "div",
      { class: "ui-callout__main" },
      p.title ? h("div", { class: "ui-callout__title" }, p.title) : null,
      p.body ? h("div", { class: "ui-callout__body" }, p.body) : null,
      p.actions && p.actions.length ? h("div", { class: "ui-callout__actions" }, p.actions) : null,
    ),
  );
}

/** 页顶横幅（字体缺失 / AI 未配置 / 版本过期） */
export function banner(p = {}) {
  return h(
    "div",
    { class: "ui-banner", role: "status" },
    icon(p.icon || "alert-triangle", { size: 15 }),
    h("span", null, p.text),
    p.actions ? h("span", { class: "ui-banner__actions" }, p.actions) : null,
  );
}

/** 空态 */
export function emptyState(p = {}) {
  return h(
    "div",
    { class: "ui-empty" },
    h("div", { class: "ui-empty__icon" }, icon(p.icon || "folder", { size: 18 })),
    h("div", { class: "ui-empty__title" }, p.title || "这里还没有内容"),
    p.desc ? h("p", { class: "ui-empty__desc" }, p.desc) : null,
    p.actions && p.actions.length ? h("div", { class: "ui-empty__actions" }, p.actions) : null,
  );
}

/** 骨架屏 */
export function skeleton(p = {}) {
  const lines = p.lines ?? 3;
  return h(
    "div",
    { class: "ui-skel-stack", "aria-hidden": "true" },
    p.title ? h("div", { class: "ui-skel ui-skel--title" }) : null,
    Array.from({ length: lines }, (_, i) =>
      h("div", { class: "ui-skel ui-skel--line", style: { width: `${92 - i * 7}%` } }),
    ),
  );
}

export function spinner(p = {}) {
  return h("span", { class: "ui-spinner", "aria-hidden": "true", style: p.size ? { width: p.size, height: p.size } : null });
}

export function loadingText(label) {
  return h("span", { class: "ui-loading", role: "status" }, spinner(), label || "加载中…");
}

/** 进度条（value 为 0–100；null 表示不确定进度） */
export function progress(p = {}) {
  const value = p.value;
  const indeterminate = value === null || value === undefined;
  return h(
    "div",
    { class: "ui-progress" },
    h(
      "div",
      {
        class: "ui-progress__track",
        role: "progressbar",
        "aria-valuemin": "0",
        "aria-valuemax": "100",
        "aria-valuenow": indeterminate ? null : String(value),
        "aria-label": p.label || "进度",
      },
      h("div", {
        class: cx("ui-progress__bar", indeterminate ? "ui-progress__bar--indeterminate" : ""),
        style: indeterminate ? null : { width: `${Math.max(0, Math.min(100, value))}%` },
      }),
    ),
    p.meta ? h("div", { class: "ui-progress__meta" }, p.meta) : null,
  );
}

/* ---------------------------------------------------------------- 卡片 / 区块 */

export function card(p = {}) {
  return h(
    "section",
    { class: cx("ui-card", p.flush ? "ui-card--flush" : "") },
    p.title
      ? h(
          "div",
          { class: "ui-card__head" },
          h(
            "div",
            { class: "ui-card__head-text" },
            h("h2", { class: "ui-card__title" }, p.title),
            p.desc ? h("div", { class: "ui-card__desc" }, p.desc) : null,
          ),
          p.actions ? h("div", { class: "ui-card__actions" }, p.actions) : null,
        )
      : null,
    h("div", { class: "ui-card__body" }, p.body),
  );
}

export function section(p = {}) {
  return h(
    "div",
    { class: "ui-section" },
    h(
      "div",
      { class: "ui-section__head" },
      h("h2", { class: "ui-section__title" }, p.title),
      p.desc ? h("span", { class: "ui-section__desc" }, p.desc) : null,
      p.actions ? h("span", { class: "ui-section__actions" }, p.actions) : null,
    ),
    p.body,
  );
}

export function stat(p = {}) {
  return h(
    "div",
    { class: "stat" },
    h("span", { class: "stat__label" }, p.label, p.hint ? h("span", { class: "small muted" }, p.hint) : null),
    h(
      "span",
      { class: "stat__value" },
      p.value,
      p.unit ? h("small", null, p.unit) : null,
    ),
  );
}

/* ---------------------------------------------------------------- 工具条 / 标签页 */

export function toolbar(p = {}) {
  return h("div", { class: "ui-toolbar", role: "toolbar" }, p.children);
}

/**
 * 标签页（无路由依赖：onChange 交给页面）
 * @param {{items:Array<{id:string,label:string,count?:number}>, value:string,
 *          onChange?:(id:string)=>void, label?:string}} p
 */
export function tabs(p = {}) {
  return h(
    "div",
    { class: "ui-tabs", role: "tablist", "aria-label": p.label },
    (p.items || []).map((it) =>
      h(
        "button",
        {
          class: "ui-tab",
          type: "button",
          role: "tab",
          "aria-selected": String(it.id) === String(p.value) ? "true" : "false",
          onClick: p.onChange ? () => p.onChange(it.id) : null,
        },
        it.label,
        it.count !== undefined && it.count !== null ? h("span", { class: "ui-tab__count" }, String(it.count)) : null,
      ),
    ),
  );
}

/* ---------------------------------------------------------------- 状态点 / 置信度 */

/**
 * 状态点：颜色 + 文案双通道（不允许只靠颜色表达状态）
 * 结构与 layout.css 的 .status-item / .status-dot 对齐。
 * @param {{level:"ok"|"warn"|"bad"|"idle", label:string, title?:string}} p
 */
export function statusDot(p = {}) {
  return h(
    "span",
    { class: "status-item", title: p.title },
    h("i", { class: `status-dot status-dot--${p.level || "idle"}` }),
    p.label,
  );
}

/**
 * 置信度：>=0.8 hi / 0.6–0.8 mid / <0.6 lo（数字与文字都必须出现）
 * @param {{value:number}} p
 */
export function confidence(p = {}) {
  const v = Number(p.value);
  const level = v >= 0.8 ? "hi" : v >= 0.6 ? "mid" : "lo";
  const label = level === "hi" ? "高" : level === "mid" ? "中" : "低";
  return h(
    "span",
    { class: `conf conf--${level}`, title: `置信度 ${(v * 100).toFixed(0)}%` },
    h("i", { class: "conf__dot" }),
    `${label} ${(v * 100).toFixed(0)}%`,
  );
}

/* ---------------------------------------------------------------- 其他小件 */

/** 键值行 */
export function kv(rows = []) {
  return h(
    "div",
    { class: "kv" },
    rows.map(([k, v]) => [h("div", { class: "kv__k" }, k), h("div", { class: "kv__v" }, v)]),
  );
}

/** 可复制文本（只展示；复制动作由页面绑定，避免组件触碰剪贴板权限之外的逻辑） */
export function copyText(p = {}) {
  const value = p.value ?? "";
  return h(
    "span",
    { class: "copy-text", title: value },
    h("span", { class: "copy-text__value" }, value),
    p.onCopy
      ? h(
          "button",
          {
            class: "ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon",
            type: "button",
            "aria-label": "复制",
            onClick: () => p.onCopy(value),
          },
          icon("copy", { size: 12 }),
        )
      : null,
  );
}

/** 字符计数（超出上限变红并给出文字） */
export function charCount(p = {}) {
  const n = p.value ? String(p.value).length : 0;
  const over = p.max ? n > p.max : false;
  return h(
    "span",
    { class: cx("char-count", over ? "is-over" : "") },
    p.max ? `${n} / ${p.max}` : String(n),
    over ? "（超出）" : "",
  );
}

/* ---------------------------------------------------------------- 模态基础件 */

/**
 * 模态骨架：遮罩 + 容器 + 头/体/脚插槽。
 * 焦点陷阱与 Esc 由 trapFocus 提供；Enter 不作为默认确认动作（见 DESIGN.md §5.4）。
 * @param {{title:string, icon?:string, meta?:Node[], body:Node, footer:Node,
 *          wide?:boolean, expired?:boolean, onClose?:()=>void, labelledBy?:string}} p
 */
export function modal(p = {}) {
  const titleId = p.labelledBy || `modal-title-${Math.random().toString(36).slice(2, 8)}`;
  const dialog = h(
    "div",
    {
      class: cx("modal", p.wide ? "modal--wide" : "", p.expired ? "is-expired" : ""),
      role: "dialog",
      "aria-modal": "true",
      "aria-labelledby": titleId,
    },
    h(
      "div",
      { class: "modal__head" },
      h(
        "h2",
        { class: "modal__title", id: titleId },
        p.icon ? icon(p.icon, { size: 20, cls: "modal__title-icon" }) : null,
        p.title,
      ),
      p.meta && p.meta.length ? h("div", { class: "modal__meta" }, p.meta) : null,
    ),
    h("div", { class: "modal__body" }, p.body),
    p.error ? h("div", { class: "modal__error", role: "alert" }, icon("alert-circle", { size: 15 }), h("span", null, p.error)) : null,
    h("div", { class: "modal__foot" }, p.footer),
  );

  const layer = h(
    "div",
    { class: "modal-layer" },
    h("div", {
      class: "modal-layer__scrim",
      onClick: p.onClose || null,
      "aria-hidden": "true",
    }),
    dialog,
  );

  layer._dialog = dialog;
  return layer;
}

export { trapFocus, focusFirst };
