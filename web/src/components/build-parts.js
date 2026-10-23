/**
 * build-parts.js — 组装与导出预览（三栏：选择器 / 预览 / 导出）
 *
 * 本文件承载两条硬需求的视觉实装：
 *  A. 简历语言切换（中文 / English）+ 模板选择（中文模板 / 英文模板），
 *     切换时实时列出「该语言缺失的字段」；
 *  B. 导出前的最终文件名预览（{position}-{name}-{school}），缺变量时必须红字报错，
 *     不生成残缺文件名；
 *  C. 「包含照片」开关（默认开启）+ 照片缩略图与来源标签。
 *
 * 组件不发请求：命名结果由页面层调用 POST /api/v1/naming/validate 后传入。
 */

import { h, cx } from "./dom.js";
import { icon } from "./icons.js";
import {
  badge,
  button,
  callout,
  chip,
  emptyState,
  iconButton,
  section,
  segmented,
  toggle,
} from "./primitives.js";

export const LANG_LABELS = { zh: "中文", en: "English" };

/** 个人资料字段 → 中文标签（用于「该语言缺失字段」提示） */
export const PROFILE_FIELD_LABELS = {
  name_zh: "姓名（中文）",
  name_en: "姓名（英文）",
  school_zh: "学校（中文）",
  school_en: "学校（英文）",
  degree: "学历",
  major: "专业",
  grad_year: "毕业年份",
  phone: "手机号",
  email: "邮箱",
  city: "城市",
  available_date: "可到岗时间",
  photo: "照片",
};

/**
 * 简历语言切换 + 该语言缺失字段的实时提示。
 * @param {{
 *  value:"zh"|"en",
 *  onChange?:(lang:"zh"|"en")=>void,
 *  missing?:{zh:string[], en:string[]},
 *  onGoProfile?:Function
 * }} p
 */
export function languageSwitch(p = {}) {
  const lang = p.value || "zh";
  const missing = (p.missing && p.missing[lang]) || [];
  const disabled = Boolean(p.missing && p.missing[lang === "zh" ? "en" : "zh"] === undefined);

  return h(
    "div",
    { class: "stack" },
    h(
      "div",
      { class: "row", style: { justifyContent: "space-between", gap: "var(--sp-4)" } },
      h(
        "div",
        { class: "ui-field__label", style: { margin: "0" } },
        "简历语言",
        h("span", { class: "ui-field__note" }, "决定姓名/学校取哪一列，以及用哪套模板"),
      ),
      segmented({
        label: "简历语言",
        value: lang,
        options: [
          { value: "zh", label: "中文", badge: "中文模板" },
          { value: "en", label: "English", badge: "English 模板" },
        ],
        onChange: p.onChange,
      }),
    ),
    missing.length
      ? callout({
          tone: "warn",
          icon: "alert-triangle",
          title: `${LANG_LABELS[lang]} 模板缺少 ${missing.length} 个字段`,
          body: h(
            "span",
            { class: "stack", style: { gap: "var(--sp-2)" } },
            h(
              "span",
              { class: "ui-chip-set" },
              missing.map((f) => chip({ label: PROFILE_FIELD_LABELS[f] || f, tone: "warn" })),
            ),
            h(
              "span",
              null,
              lang === "en"
                ? "英文模板不会回退到中文字段：请补全英文姓名与学校，否则导出会被拒绝。"
                : "中文模板使用中文字段：请补全中文姓名与学校，否则导出会被拒绝。",
            ),
          ),
          actions: p.onGoProfile
            ? [button({ label: "去个人资料补齐", size: "sm", variant: "ghost", iconRight: "arrow-right", onClick: p.onGoProfile })]
            : null,
        })
      : h(
          "div",
          { class: "naming__warn naming__warn--success" },
          icon("check-circle", { size: 13 }),
          `${LANG_LABELS[lang]} 模板所需字段齐全`,
        ),
    disabled ? null : null,
  );
}

/**
 * 模板选择（只列与当前语言匹配的模板，空则给出创建入口）
 * @param {{value?:string, options:Array<{value:string,label:string,lang:"zh"|"en",is_default?:boolean}>,
 *          onChange?:(id:string)=>void, onManage?:Function}} p
 */
/**
 * 版式宽松度（导出页右栏）。
 * - original：复刻用户原件 PDF 的页边距（上 8.3 / 下 16.4 / 左 14.8 / 右 15.6 pt，契约 §7.5.1），
 *   目标「单页 + 正文 ≥10pt」——这是默认值，也是唯一能保证真实体量压进一页的档位。
 * - relaxed：上下 16mm / 左右 15mm，观感舒展但**允许排到第 2 页**，给内容少的人用。
 * 纯展示：值由页面层从 `ResumeBuild.density` 读，切换只回调。
 * @param {{value?:string, onChange?:Function, pages?:number, note?:string}} p
 */
export const DENSITY_OPTIONS = [
  {
    value: "original",
    label: "紧凑（与原简历一致，单页）",
    hint: "页边距按你原来那份 PDF 来（上 8.3pt、左右 15pt 级），一页放得下。",
  },
  {
    value: "relaxed",
    label: "宽松（可能两页）",
    hint: "上下 16mm、左右 15mm，看着舒展；内容多时会排到第 2 页。",
  },
];

export function densitySelect(p = {}) {
  const value = p.value || "original";
  const current = DENSITY_OPTIONS.find((o) => o.value === value) || DENSITY_OPTIONS[0];
  return h(
    "div",
    { class: "stack", style: { gap: "var(--sp-2)" } },
    h(
      "div",
      { class: "row", style: { justifyContent: "space-between" } },
      h("div", { class: "ui-field__label", style: { margin: "0" } }, "版式松紧"),
      p.pages ? h("span", { class: "small muted mono" }, `预计 ${p.pages} 页`) : null,
    ),
    h(
      "div",
      { class: "ui-seg ui-seg--block", role: "radiogroup", "aria-label": "版式宽松度" },
      DENSITY_OPTIONS.map((o) =>
        h(
          "button",
          {
            type: "button",
            class: "ui-seg__opt",
            role: "radio",
            "aria-checked": o.value === value ? "true" : "false",
            onClick: p.onChange ? () => p.onChange(o.value) : null,
          },
          o.label,
        ),
      ),
    ),
    h("p", { class: "density-note" }, p.note || current.hint),
  );
}

export function templateSelect(p = {}) {
  const options = p.options || [];
  const current = options.find((o) => o.value === p.value);
  return h(
    "div",
    { class: "stack", style: { gap: "var(--sp-3)" } },
    h(
      "div",
      { class: "row", style: { justifyContent: "space-between" } },
      h("div", { class: "ui-field__label", style: { margin: "0" } }, "模板"),
      p.onManage ? button({ label: "管理模板", size: "sm", variant: "quiet", onClick: p.onManage }) : null,
    ),
    options.length
      ? h(
          "div",
          { class: "row", style: { gap: "var(--sp-3)" } },
          h(
            "select",
            {
              class: "ui-select",
              "aria-label": "选择模板",
              onChange: p.onChange ? (ev) => p.onChange(ev.target.value) : null,
            },
            options.map((o) =>
              h("option", { value: o.value, selected: String(o.value) === String(p.value) ? true : null }, o.label),
            ),
          ),
          current && current.is_default ? badge({ text: "默认", tone: "accent" }) : null,
        )
      : h(
          "div",
          { class: "small muted" },
          "该语言还没有可用模板。可以先导入一份现有简历，或在模板页从内置版式创建。",
        ),
    current
      ? h("div", { class: "small muted" }, `将使用「${current.label}」的章节顺序与字号；缺失槽位会以占位符标出。`)
      : null,
  );
}

/**
 * 三栏布局中的左侧选择器
 * @param {{groups:Array<{key:string,title:string,count?:number,items:Array}>,
 *          selected:string[], onToggle:(key:string)=>void, onMove?:(key:string,dir:-1|1)=>void,
 *          summary?:Node, onSelectAll?:Function, onClear?:Function}} p
 */
export function pickerLeft(p = {}) {
  const groups = p.groups || [];
  return h(
    "div",
    { class: "build-side build-side--left" },
    h(
      "div",
      { class: "row", style: { justifyContent: "space-between", alignItems: "baseline" } },
      h("h2", { class: "ui-section__title" }, "选择内容"),
      h(
        "span",
        { class: "row", style: { gap: "var(--sp-2)" } },
        p.onSelectAll ? button({ label: "全选", size: "sm", variant: "quiet", onClick: p.onSelectAll }) : null,
        p.onClear ? button({ label: "清空", size: "sm", variant: "quiet", onClick: p.onClear }) : null,
      ),
    ),
    p.summary || null,
    groups.length
      ? groups.map((g) =>
          h(
            "div",
            { class: "pick-group" },
            h(
              "div",
              { class: "pick-group__head" },
              g.title,
              h("span", { class: "pick-group__count" }, `${(g.items || []).filter((i) => p.selected.includes(i.key)).length}/${(g.items || []).length}`),
            ),
            (g.items || []).map((it) =>
              pickRow({
                item: it,
                checked: p.selected.includes(it.key),
                onToggle: p.onToggle,
                onMove: p.onMove,
              }),
            ),
          ),
        )
      : emptyState({
          icon: "warehouse",
          title: "没有可用的经历",
          desc: "先在经历库录入或导入一段经历，再回来组装。",
        }),
  );
}

/**
 * 单条可选经历（含子级变体勾选 + 键盘上下移动）
 * @param {{item:{key:string,title:string,org?:string,meta?:string,
 *                sub?:Array<{key:string,label:string,checked?:boolean}>},
 *          checked:boolean, onToggle?:Function, onMove?:Function}} p
 */
export function pickRow(p = {}) {
  const it = p.item || {};
  return h(
    "div",
    { class: cx("pick-row", p.checked ? "is-on" : "") },
    h("input", {
      type: "checkbox",
      checked: Boolean(p.checked),
      "aria-label": `选择「${it.title || it.key}」`,
      style: { marginTop: "2px", accentColor: "var(--c-primary-solid)" },
      onChange: p.onToggle ? () => p.onToggle(it.key) : null,
    }),
    h(
      "span",
      { class: "pick-row__main" },
      h("span", { class: "pick-row__title" }, it.title || it.key),
      h(
        "span",
        { class: "pick-row__meta" },
        it.org || "",
        it.meta ? h("span", null, `· ${it.meta}`) : null,
      ),
    ),
    p.onMove
      ? h(
          "span",
          { class: "pick-row__moves" },
          iconButton({ icon: "arrow-up", label: `上移「${it.title}」`, size: "sm", onClick: () => p.onMove(it.key, -1) }),
          iconButton({ icon: "arrow-down", label: `下移「${it.title}」`, size: "sm", onClick: () => p.onMove(it.key, 1) }),
        )
      : null,
  );
}

/**
 * 实时统计（已选包 / 变体 / 预估页数），超出页数上限变红
 * @param {{packages:number, variants:number, chars?:number, estPages?:number,
 *          pageLimit?:number, over?:boolean}} p
 */
export function selectSummary(p = {}) {
  return h(
    "div",
    { class: cx("select-summary", p.over ? "is-over" : "") },
    h("span", null, "已选 ", h("strong", null, String(p.packages ?? 0)), " 条经历"),
    h("span", null, h("strong", null, String(p.variants ?? 0)), " 条表述"),
    typeof p.estPages === "number"
      ? h(
          "span",
          null,
          "预估 ",
          h("strong", null, String(p.estPages)),
          ` 页 / 上限 ${p.pageLimit ?? 2}`,
        )
      : null,
    p.over ? h("span", null, "超出页数，导出前请删减") : null,
  );
}

/**
 * 命名模板：输入 + 最终文件名预览 + 变量来源 + 警告/错误。
 * 缺变量时必须显式报错（不允许产出带空段的残缺文件名）。
 * @param {{
 *  value:string,
 *  onChange?:(v:string)=>void,
 *  result?:{valid:boolean, filename?:string, resolved?:string,
 *           variables?:Array<{name:string,value?:string,source?:string}>,
 *           warnings?:Array<{code:string,message:string}>,
 *           errors?:Array<{code:string,vars?:object,message:string}>},
 *  pending?:boolean,
 *  onGoProfile?:Function,
 *  onReset?:Function,
 *  defaultTemplate?:string
 * }} p
 */
export function namingPreview(p = {}) {
  const res = p.result || null;
  const valid = res ? res.valid : true;
  const errors = (res && res.errors) || [];
  const warnings = (res && res.warnings) || [];
  const hasMissingVar = errors.some((e) => e.code === "NAMING_MISSING_VAR");

  return h(
    "div",
    { class: "naming" },
    h(
      "div",
      { class: "row", style: { justifyContent: "space-between", alignItems: "baseline" } },
      h("div", { class: "ui-field__label", style: { margin: "0" } }, "文件命名"),
      p.onReset ? button({ label: "恢复默认", size: "sm", variant: "quiet", onClick: p.onReset }) : null,
    ),
    h("input", {
      class: "ui-input ui-input--mono",
      value: p.value ?? "",
      "aria-label": "文件命名模板",
      "aria-invalid": valid ? null : "true",
      placeholder: "{position}-{name}-{school}",
      onInput: p.onChange ? (ev) => p.onChange(ev.target.value) : null,
    }),
    h(
      "div",
      { class: cx("naming__filename", valid ? "" : "is-invalid") },
      h("span", { class: "naming__filename-label" }, "本次文件名"),
      res && res.filename ? res.filename : valid ? "（待生成）" : "（命名无效，不会导出）",
      p.pending ? h("span", { class: "ui-spinner" }) : null,
    ),
    res && res.variables && res.variables.length
      ? h(
          "div",
          { class: "naming__chips" },
          res.variables.map((v) =>
            chip({
              label: v.value ? `${v.name} = ${v.value}` : `${v.name} = 空`,
              tone: v.value ? "neutral" : "warn",
              mono: true,
            }),
          ),
        )
      : null,
    errors.length
      ? h(
          "div",
          { class: "naming__err", role: "alert" },
          icon("alert-circle", { size: 14 }),
          h(
            "span",
            { class: "stack", style: { gap: "var(--sp-2)" } },
            errors.map((e) => h("span", null, e.message || e.code)),
            hasMissingVar && p.onGoProfile
              ? h(
                  "span",
                  { class: "naming__err-actions" },
                  button({ label: "去个人资料补齐字段", size: "sm", variant: "primary", onClick: p.onGoProfile }),
                )
              : null,
          ),
        )
      : null,
    !errors.length && warnings.length
      ? h(
          "div",
          { class: "stack", style: { gap: "var(--sp-2)" } },
          warnings.map((w) =>
            h(
              "div",
              { class: "naming__warn naming__warn--warn" },
              icon("alert-triangle", { size: 12 }),
              w.message || w.code,
            ),
          ),
        )
      : null,
    res && res.variables && res.variables.length
      ? h(
          "details",
          { class: "naming__vars ui-details" },
          h("summary", null, "变量取值与来源"),
          h(
            "div",
            { class: "ui-details__body" },
            res.variables.map((v) =>
              h(
                "div",
                { class: "naming__var-row" },
                h("code", null, `{${v.name}}`),
                h("span", null, v.value || "—"),
                h("span", { class: "muted" }, v.source ? `来自 ${v.source}` : ""),
              ),
            ),
          ),
        )
      : null,
    h("p", { class: "small muted" }, "默认模板 {position}-{name}-{school}；{name} 与 {school} 会按简历语言取对应列。"),
  );
}

/**
 * 「包含照片」开关 + 缩略图 + 来源标签。
 * 规则：默认开启；无照片时置灰但**不阻断**导出，并给出可继续的提示。
 * @param {{
 *  include:boolean, onChange?:(v:boolean)=>void,
 *  photo?:{url?:string, source?:"imported"|"manual", width?:number, height?:number, updated_at?:string},
 *  onManage?:Function
 * }} p
 */
export function photoToggle(p = {}) {
  const photo = p.photo || null;
  const hasPhoto = Boolean(photo && photo.url);
  const sourceLabel = photo && photo.source === "imported" ? "导入自简历" : "手动上传";
  const tooSmall = photo && photo.width && photo.width < 400;

  return h(
    "div",
    { class: "stack", style: { gap: "var(--sp-3)" } },
    h(
      "div",
      { class: "row", style: { justifyContent: "space-between", alignItems: "center", gap: "var(--sp-4)" } },
      h(
        "div",
        { class: "ui-field__label", style: { margin: "0" } },
        "包含照片",
        h("span", { class: "ui-field__note" }, "中文与英文模板都支持右上角照片位"),
      ),
      h("input", {
        type: "checkbox",
        role: "switch",
        checked: hasPhoto ? Boolean(p.include) : false,
        disabled: !hasPhoto,
        "aria-label": "包含照片",
        style: { width: "34px", height: "20px", accentColor: "var(--c-primary-solid)" },
        onChange: p.onChange ? (ev) => p.onChange(ev.target.checked) : null,
      }),
    ),
    h(
      "div",
      { class: "photo-pick" + (hasPhoto ? "" : " is-empty") },
      h(
        "span",
        { class: "photo-pick__thumb", "aria-hidden": "true" },
        hasPhoto ? h("img", { src: photo.url, alt: "" }) : icon("user", { size: 18 }),
      ),
      h(
        "span",
        { class: "stack grow", style: { gap: "2px" } },
        h("span", { class: "small" }, hasPhoto ? "将使用这张照片" : "还没有照片"),
        h(
          "span",
          { class: "small muted" },
          hasPhoto
            ? `${sourceLabel}${photo.width ? ` · ${photo.width}×${photo.height}` : ""}`
            : "未设置照片，将导出无照片版本 —— 不影响继续导出",
        ),
        tooSmall ? h("span", { class: "small", style: { color: "var(--c-warn)" } }, "分辨率偏低，建议 ≥ 400×400") : null,
      ),
      p.onManage
        ? button({ label: hasPhoto ? "更换" : "去上传", size: "sm", variant: "ghost", onClick: p.onManage })
        : null,
    ),
  );
}

/**
 * 导出面板（右侧 380）
 * @param {{
 *  naming:Node, photo:Node, pageLimit?:number,
 *  canExport:boolean, exportError?:string,
 *  onExport?:Function, onPreview?:Function,
 *  engine?:{label:string, ready:boolean, hint?:string},
 *  warnings?:Array<{code:string,message:string}>
 * }} p
 */
export function exportBox(p = {}) {
  return h(
    "div",
    { class: "export-box" },
    p.naming,
    h("div", { class: "hr" }),
    p.photo,
    p.warnings && p.warnings.length
      ? h(
          "div",
          { class: "stack", style: { gap: "var(--sp-2)" } },
          p.warnings.map((w) =>
            h("div", { class: "naming__warn naming__warn--warn" }, icon("alert-triangle", { size: 12 }), w.message || w.code),
          ),
        )
      : null,
    p.engine && !p.engine.ready
      ? callout({
          tone: "warn",
          title: "PDF 引擎不可用",
          body: p.engine.hint || "导出前请先修复字体或渲染引擎；也可以先导出 DOCX。",
          actions: p.onPreview ? [button({ label: "查看诊断", size: "sm", variant: "ghost", onClick: p.onPreview })] : null,
        })
      : null,
    p.exportError
      ? callout({ tone: "danger", title: "无法导出", body: p.exportError })
      : null,
    h(
      "div",
      { class: "export-box__foot" },
      button({
        label: p.engine && !p.engine.ready ? "导出 PDF（不可用）" : "导出 PDF",
        variant: "primary",
        size: "lg",
        block: true,
        icon: "download",
        disabled: !p.canExport,
        onClick: p.onExport,
      }),
      button({ label: "仅预览（不导出）", variant: "ghost", block: true, onClick: p.onPreview }),
      h(
        "div",
        { class: "export-box__hint" },
        p.engine && p.engine.ready
          ? `引擎：${p.engine.label} · 导出前会再弹一次「将发送字段清单」`
          : "导出只写本地目录，不会上传任何文件",
      ),
    ),
  );
}

/**
 * 纸张预览舞台（无后端时也能看版式）
 * 照片位：右上角 89.3×89.3pt 正方形（≈31.5mm），距页面顶边 3.8pt，
 * 与姓名/联系方式并排，姓名区在左。
 * @param {{lang?:"zh"|"en", name?:string, headline?:string, contact?:string[],
 *          includePhoto?:boolean, photoUrl?:string, sections?:Array<{title:string,lines:string[]}>}} p
 */
export function paperMock(p = {}) {
  const lang = p.lang || "zh";
  return h(
    "div",
    { class: cx("doc", lang === "en" ? "doc--en" : "") },
    h(
      "header",
      { class: "doc__header" },
      h(
        "div",
        { class: "doc__header-main" },
        h("h1", { class: "doc__name" }, p.name || (lang === "en" ? "YOUR NAME" : "你的姓名")),
        p.headline ? h("div", { class: "doc__headline" }, p.headline) : null,
        h(
          "div",
          { class: "doc__contact" },
          (p.contact || []).map((c) => h("span", { class: "doc__contact-item" }, c)),
        ),
      ),
      p.includePhoto
        ? p.photoUrl
          ? h("img", { class: "doc__photo", src: p.photoUrl, alt: "证件照" })
          : h("div", { class: "doc__photo doc__photo--ph" }, "照片")
        : null,
    ),
    (p.sections || []).map((s) =>
      h(
        "section",
        { class: "doc__section" },
        h("h2", { class: "doc__section-title" }, s.title),
        (s.lines || []).map((line) =>
          h("p", { class: "doc__bullet" }, line),
        ),
      ),
    ),
    h(
      "footer",
      { class: "doc__footer" },
      h("span", null, p.footerLeft || "本地生成 · 未上传"),
      h("span", null, "1 / 1"),
    ),
  );
}

/**
 * 中间预览区（优先 iframe 渲染服务端预览；无后端时用 paperMock）
 * @param {{lang?:"zh"|"en", templateName?:string, iframeUrl?:string,
 *          pageInfo?:string, onReload?:Function, fallback?:Node}} p
 */
export function buildPreview(p = {}) {
  return h(
    "div",
    { class: "build-preview" },
    h(
      "div",
      { class: "build-preview__bar" },
      badge({ text: p.lang === "en" ? "English" : "中文", tone: p.lang === "en" ? "info" : "neutral" }),
      h("span", null, p.templateName || "未选择模板"),
      h("span", { class: "grow" }),
      p.pageInfo ? h("span", { class: "small muted" }, p.pageInfo) : null,
      p.onReload ? iconButton({ icon: "refresh", label: "重新渲染预览", size: "sm", onClick: p.onReload }) : null,
    ),
    h(
      "div",
      { class: "build-preview__stage" },
      p.iframeUrl
        ? h("iframe", {
            class: "build-preview__frame",
            src: p.iframeUrl,
            title: "简历预览",
            loading: "lazy",
            sandbox: "allow-same-origin",
          })
        : p.fallback || paperMock({ lang: p.lang }),
    ),
    h(
      "div",
      { class: "build-preview__bar" },
      icon("info", { size: 13, cls: "muted" }),
      h("span", { class: "small muted" }, "预览与 PDF 使用同一套模板；照片位固定在右上角 89.3×89.3pt。"),
    ),
  );
}

/** 三栏组装布局 */
export function buildLayout(p = {}) {
  return h(
    "div",
    { class: "split--build" },
    p.left,
    p.center,
    h("div", { class: "build-side build-side--right" }, p.right),
  );
}

/** 页数超限提示（MISSING_SLOTS / PAGE_OVERFLOW 的 UI 呈现） */
export function buildWarnings(p = {}) {
  const list = p.warnings || [];
  if (!list.length) return null;
  return h(
    "div",
    { class: "stack", style: { gap: "var(--sp-3)" } },
    list.map((w) => {
      if (w.code === "PAGE_OVERFLOW") {
        return callout({
          tone: "warn",
          title: `内容超出 ${w.vars && w.vars.limit ? w.vars.limit : 2} 页上限`,
          body: "删掉低优先级条目，或把多条变体精简为一条；也可以切换到紧凑版式。",
        });
      }
      if (w.code === "MISSING_SLOTS_RENDERED") {
        return callout({
          tone: "warn",
          title: "有槽位没有内容，已用占位符渲染",
          body: "占位符在 PDF 里可见。导出前请补齐，或确认这个槽位是可选的。",
        });
      }
      if (w.code === "PROFILE_INCOMPLETE") {
        return callout({
          tone: "warn",
          title: "个人资料不完整",
          body: "联系方式或教育信息缺失，会让简历显得不完整。",
          actions: p.onGoProfile ? [button({ label: "去补齐", size: "sm", variant: "ghost", onClick: p.onGoProfile })] : null,
        });
      }
      return callout({ tone: "info", title: w.code, body: w.message || "" });
    }),
  );
}

export { section, toggle };

/* ───────────────────────────── 技能原文行 / 主修课程 / 荣誉 ───────────────────────────── */

/**
 * 技能是**整句原文**，不拆 tag。用户裁决：拆成 tag 会失去简历的规整感。
 * 匹配提示只加在整行旁边（「命中 JD：Python」），不改变文字。
 * @param {{index:number,text:string,matches?:string[],include?:boolean,
 *          onToggle?:(index:number)=>void,onMove?:(from:number,to:number)=>void}} p
 */
export function skillLine(p = {}) {
  const index = typeof p.index === "number" ? p.index : 0;
  const matches = p.matches || [];
  const include = p.include !== false;
  const hasMatch = matches.length > 0;
  return h(
    "div",
    { class: cx("skill-line", include ? "" : "is-off", hasMatch ? "is-hit" : "") },
    h(
      "span",
      { class: "skill-line__handle", "aria-hidden": "true" },
      icon("grip", { size: 13 }),
    ),
    h(
      "span",
      { class: "skill-line__main" },
      h("span", { class: "skill-line__text" }, p.text || ""),
      hasMatch
        ? h(
            "span",
            { class: "skill-line__match" },
            matches.map((m) => badge({ text: `命中 JD：${m}`, tone: "accent" })),
          )
        : null,
    ),
    h(
      "span",
      { class: "skill-line__actions" },
      p.onToggle
        ? button({
            label: include ? "不放进这份简历" : "放回这份简历",
            variant: "quiet",
            size: "sm",
            onClick: () => p.onToggle(index),
          })
        : null,
      p.onMove
        ? iconButton({
            icon: "arrow-up",
            label: `上移第 ${index + 1} 行`,
            size: "sm",
            onClick: () => p.onMove(index, index - 1),
            disabled: index === 0,
          })
        : null,
      p.onMove
        ? iconButton({
            icon: "arrow-down",
            label: `下移第 ${index + 1} 行`,
            size: "sm",
            onClick: () => p.onMove(index, index + 1),
            disabled: index === (p.total || 1) - 1,
          })
        : null,
    ),
  );
}

/**
 * 技能整行列表。默认原序；「按相关度排序」是一次性的视觉重排，随时可还原。
 * @param {{lines:Array<{text:string,matches?:string[],include?:boolean}>,
 *          sorted?:boolean,onToggleSort?:()=>void,
 *          onToggle?:(i:number)=>void,onMove?:(a:number,b:number)=>void}} p
 */
export function skillLines(p = {}) {
  const lines = p.lines || [];
  const sorted = !!p.sorted;
  return h(
    "div",
    { class: "skill-lines" },
    h(
      "div",
      { class: "skill-lines__head" },
      h(
        "span",
        { class: "small muted" },
        "技能按原文逐行保留，不拆成标签；匹配提示只做标记，不改文字。",
      ),
      h("span", { class: "grow" }),
      sorted ? badge({ text: "已按相关度排序", tone: "accent" }) : null,
      p.onToggleSort
        ? button({
            label: sorted ? "还原原顺序" : "按相关度排序",
            variant: "quiet",
            size: "sm",
            icon: sorted ? "refresh" : "arrow-down",
            onClick: p.onToggleSort,
          })
        : null,
    ),
    lines.map((line, i) =>
      skillLine({
        index: i,
        total: lines.length,
        text: line.text,
        matches: line.matches,
        include: line.include,
        onToggle: p.onToggle,
        onMove: p.onMove,
      }),
    ),
  );
}

/**
 * 主修课程：默认全部保留；「按 JD 裁剪」默认关闭，打开前先展示将裁掉哪几门。
 * @param {{total:number,courses?:string[],cut?:string[],enabled:boolean,
 *          onToggle?:(next:boolean)=>void,onConfirmCut?:(courses:string[])=>void,
 *          onBack?:()=>void,confirming?:boolean}} p
 */
export function courseTrim(p = {}) {
  const total = p.total || 0;
  const cut = p.cut || [];
  const courses = p.courses || [];
  const confirming = !!p.confirming;
  return h(
    "div",
    { class: cx("course-trim", p.enabled ? "is-on" : "") },
    h(
      "div",
      { class: "course-trim__row" },
      h(
        "span",
        { class: "course-trim__main" },
        h("span", { class: "course-trim__title" }, `主修课程 · ${total} 门`),
        h(
          "span",
          { class: "course-trim__sub small muted" },
          p.enabled
            ? `将裁掉 ${cut.length} 门（${cut.join("、") || "无"}），其余保留`
            : "默认全部保留，不按 JD 删课。",
        ),
      ),
      toggle({
        checked: !!p.enabled,
        label: "按 JD 裁剪主修课程",
        onChange: p.onToggle,
      }),
    ),
    confirming
      ? h(
          "div",
          { class: "course-trim__confirm", role: "group", "aria-label": "确认裁剪课程" },
          h("span", { class: "course-trim__confirm-title" }, "这次会裁掉这几门："),
          h(
            "span",
            { class: "ui-chip-set" },
            cut.length
              ? cut.map((c) => chip({ label: c, tone: "warn" }))
              : h("span", { class: "small muted" }, "当前没有课程会被裁掉。"),
          ),
          h("span", { class: "small muted" }, `保留 ${total - cut.length} / ${total} 门。`),
          h(
            "span",
            { class: "course-trim__confirm-actions" },
            button({ label: "取消", variant: "ghost", size: "sm", onClick: p.onBack }),
            button({
              label: "确认裁剪",
              variant: "primary",
              size: "sm",
              onClick: () => p.onConfirmCut && p.onConfirmCut(cut),
            }),
          ),
        )
      : null,
    !p.enabled && courses.length
      ? h(
          "div",
          { class: "course-trim__all small muted" },
          `全部保留：${courses.join("、")}`,
        )
      : null,
  );
}

/**
 * 荣誉：不单独成节，挂在「校园活动」下作为可选要点（默认显示）。
 * @param {{visible:boolean,count?:number,onChange?:(next:boolean)=>void}} p
 */
export function honorToggle(p = {}) {
  const visible = p.visible !== false;
  return h(
    "div",
    { class: "honor-row" },
    h(
      "span",
      { class: "honor-row__main" },
      h("span", { class: "honor-row__title" }, "荣誉与奖项"),
      h(
        "span",
        { class: "honor-row__sub small muted" },
        visible
          ? "作为「校园活动」下的一条要点显示，不单独成节。"
          : "已隐藏；经历库里的记录不会删除，随时可以再显示。",
      ),
    ),
    toggle({ checked: visible, label: "显示荣誉要点", onChange: p.onChange }),
  );
}

