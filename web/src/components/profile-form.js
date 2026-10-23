/**
 * profile-form.js — 个人资料（UserProfile 单例）
 *
 * 职责边界：本组件只渲染与收集输入，不发请求；username/school 等身份信息
 * 一律来自 UserProfile（ARCHITECTURE §4.4），前端**不允许**硬编码任何姓名/学校。
 *
 * 照片：预览区是固定 1:1 方形裁切框（导出后渲染为右上角 89.3×89.3pt ≈ 31.5mm），
 * 支持拖放与点选；替换要二次确认；移除后回落到「导入自简历」候选。
 */

import { h, cx } from "./dom.js";
import { icon } from "./icons.js";
import { badge, button, callout, chip, field, input, progress, section, select } from "./primitives.js";
import { PROFILE_FIELD_LABELS } from "./build-parts.js";

/** 表单字段定义（顺序即视觉顺序） */
const FIELDS = [
  { key: "name_zh", label: "姓名（中文）", placeholder: "与身份证一致", required: true, group: "身份" },
  { key: "name_en", label: "姓名（英文）", placeholder: "拼音或英文名，英文模板使用", required: true, group: "身份" },
  { key: "school_zh", label: "学校（中文）", placeholder: "全称，导出命名会用到", required: true, group: "教育" },
  { key: "school_en", label: "学校（英文）", placeholder: "English name，英文模板使用", required: true, group: "教育" },
  { key: "degree", label: "学历", placeholder: "本科 / 硕士 / 博士", group: "教育" },
  { key: "major", label: "专业", placeholder: "专业全称", group: "教育" },
  { key: "grad_year", label: "毕业年份", placeholder: "2026", group: "教育", inputmode: "numeric" },
  { key: "phone", label: "手机号", placeholder: "13800000000", group: "联系" },
  { key: "email", label: "邮箱", placeholder: "you@example.com", group: "联系", type: "email" },
  { key: "city", label: "城市", placeholder: "现居城市", group: "联系" },
  // 中文原文是真值（渲染页眉第三行）；英文表述写 extra，留空回退中文值
  { key: "available_note", label: "到岗时间（中文）", placeholder: "如：2027年1月下旬", group: "联系" },
  { key: "available_note_en", label: "到岗时间（英文，可选）", placeholder: "Late January 2027", group: "联系" },
];

/** 学校缺失时的硬提示文案（需求原文，不要改写） */
export const MISSING_SCHOOL_MSG = "导出将因缺少学校而失败";

/**
 * 个人资料主表单
 * @param {{
 *  value:Record<string,string>, onChange?:(key:string,val:string)=>void,
 *  errors?:Record<string,string>, dirty?:boolean, saving?:boolean,
 *  savedAt?:string, onSave?:Function, onReset?:Function,
 *  photo?:Node, completeness?:{value:number,missing:string[]}, naming?:Node
 * }} p
 */
export function profileForm(p = {}) {
  const v = p.value || {};
  const groups = [
    { title: "身份", keys: ["name_zh", "name_en"] },
    { title: "教育", keys: ["school_zh", "school_en", "degree", "major", "grad_year"] },
    { title: "联系方式", keys: ["phone", "email", "city", "available_note", "available_note_en"] },
  ];

  return h(
    "div",
    { class: "profile-layout" },
    h(
      "div",
      { class: "stack", style: { gap: "var(--sp-7)" } },

      callout({
        tone: "info",
        icon: "user",
        title: "这里的字段是简历与文件命名的唯一来源",
        body: "改这里，导出页的姓名、学校与文件名会立刻跟着变；简历正文不会硬编码任何身份信息。",
      }),

      groups.map((g) =>
        section({
          title: g.title,
          body: h(
            "div",
            { class: "profile-form__grid" },
            g.keys.map((key) => {
              const def = FIELDS.find((f) => f.key === key) || { key, label: key };
              const missing = key === "school_zh" && !v.school_zh;
              return field({
                id: `profile-${key}`,
                label: def.label,
                required: def.required,
                full: key === "available_note" ? false : undefined,
                error: p.errors && p.errors[key] ? p.errors[key] : null,
                hint: missing ? h("span", { style: { color: "var(--c-danger)" } }, MISSING_SCHOOL_MSG) : null,
                control: input({
                  id: `profile-${key}`,
                  value: v[key] ?? "",
                  placeholder: def.placeholder,
                  type: def.type || "text",
                  inputmode: def.inputmode,
                  invalid: Boolean(p.errors && p.errors[key]) || missing,
                  onInput: p.onChange ? (val) => p.onChange(key, val) : null,
                }),
              });
            }),
          ),
        }),
      ),

      section({
        title: "照片",
        desc: "会渲染在简历右上角；中文与英文模板都支持。",
        body: p.photo || null,
      }),

      h(
        "div",
        { class: "row", style: { gap: "var(--sp-4)", alignItems: "center" } },
        button({
          label: p.saving ? "保存中…" : "保存个人资料",
          variant: "primary",
          icon: "check",
          loading: Boolean(p.saving),
          disabled: p.dirty === false,
          onClick: p.onSave,
        }),
        p.dirty
          ? h("span", { class: "small muted" }, "有未保存的修改")
          : p.savedAt
            ? h("span", { class: "small muted" }, `已保存 · ${p.savedAt}`)
            : null,
        h("span", { class: "grow" }),
        p.onReset ? button({ label: "撤销修改", variant: "quiet", size: "sm", onClick: p.onReset }) : null,
      ),
    ),

    h("div", { class: "profile-side" }, p.naming || null, p.completeness || completenessMeter(p.completeness)),
  );
}

/**
 * 照片区：1:1 裁切框预览 + 拖放 / 点选 + 替换二次确认 + 移除后回落导入候选
 * @param {{
 *  photo?:{url:string, source?:"imported"|"manual", width?:number, height?:number, bytes?:number},
 *  importedPhoto?:{url:string,width?:number,height?:number}|null,
 *  confirmReplace?:boolean, uploading?:boolean, error?:string,
 *  onPick?:Function, onReplace?:Function, onConfirmReplace?:Function,
 *  onCancelReplace?:Function, onRemove?:Function, onUseImported?:Function,
 *  onDropFile?:(file:File)=>void, onSelectFile?:(file:File)=>void
 * }} p
 */
export function photoField(p = {}) {
  const photo = p.photo || null;
  const has = Boolean(photo && photo.url);
  const imported = p.importedPhoto || null;
  const tooSmall = photo && photo.width && photo.width < 400;
  const sourceLabel = photo && photo.source === "imported" ? "导入自简历" : "手动上传";

  const zone = h(
    "div",
    {
      class: cx("photo-field__drop", has ? "has-photo" : ""),
      tabindex: "0",
      role: "button",
      "aria-label": has ? "替换照片（拖入或按回车选择文件）" : "上传照片（拖入或按回车选择文件）",
      onClick: () => {
        if (has) p.onReplace && p.onReplace();
        else p.onPick && p.onPick();
      },
      onKeyDown: (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          if (has) p.onReplace && p.onReplace();
          else p.onPick && p.onPick();
        }
      },
      onDragOver: (ev) => {
        ev.preventDefault();
        ev.currentTarget.classList.add("is-dragover");
      },
      onDragLeave: (ev) => ev.currentTarget.classList.remove("is-dragover"),
      onDrop: (ev) => {
        ev.preventDefault();
        ev.currentTarget.classList.remove("is-dragover");
        const file = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
        if (!file) return;
        if (has && p.onReplace) p.onReplace(file);
        else if (p.onDropFile) p.onDropFile(file);
      },
    },
    h(
      "div",
      { class: "photo-field__frame" },
      has
        ? h("img", { src: photo.url, alt: "证件照预览（方形裁切）", class: "photo-field__img" })
        : h(
            "div",
            { class: "photo-field__placeholder" },
            icon("upload", { size: 20 }),
            h("span", null, "拖入或点击选择"),
            h("span", { class: "small muted" }, "JPG / PNG"),
          ),
      h("span", { class: "photo-field__crop-hint" }, "1:1"),
    ),
    h(
      "div",
      { class: "stack", style: { gap: "var(--sp-2)" } },
      h(
        "div",
        { class: "badge-row" },
        has ? badge({ text: sourceLabel, tone: photo.source === "imported" ? "info" : "accent" }) : badge({ text: "未设置" }),
        has && photo.width ? badge({ text: `${photo.width}×${photo.height}` }) : null,
        tooSmall ? badge({ text: "建议 ≥400×400", tone: "warn" }) : null,
      ),
      h(
        "div",
        { class: "small muted" },
        has ? "导出时固定为右上角 89.3×89.3pt（≈31.5mm）正方形，按中心裁切。" : "上传后会在导出时渲染成 89.3×89.3pt 正方形。",
      ),
      !has && imported
        ? h(
            "div",
            { class: "photo-field__imported" },
            icon("file", { size: 13 }),
            h("span", { class: "small" }, "检测到简历里带照片"),
            h("img", { src: imported.url, alt: "", class: "photo-field__mini" }),
            button({
              label: "使用这张",
              size: "sm",
              variant: "ghost",
              onClick: p.onUseImported,
            }),
          )
        : null,
    ),
  );

  return h(
    "div",
    { class: "photo-field" },
    zone,
    h(
      "div",
      { class: "photo-field__actions" },
      button({
        label: has ? "替换照片" : "上传照片",
        icon: "upload",
        size: "sm",
        variant: has ? "secondary" : "primary",
        loading: Boolean(p.uploading),
        onClick: has ? () => p.onReplace && p.onReplace() : () => p.onPick && p.onPick(),
      }),
      has ? button({ label: "移除", icon: "trash", size: "sm", variant: "danger-ghost", onClick: p.onRemove }) : null,
      imported && has
        ? button({ label: "改回导入的", size: "sm", variant: "quiet", onClick: p.onUseImported })
        : null,
      h(
        "label",
        { class: "ui-btn ui-btn--quiet ui-btn--sm", style: { cursor: "pointer" } },
        icon("folder", { size: 14 }),
        h("span", null, "选择文件"),
        h("input", {
          type: "file",
          accept: "image/jpeg,image/png",
          class: "sr-only",
          onChange: (ev) => {
            const f = ev.target.files && ev.target.files[0];
            if (f && p.onSelectFile) p.onSelectFile(f);
            ev.target.value = "";
          },
        }),
      ),
    ),

    // 替换前的二次确认（内联，不打断输入）
    p.confirmReplace
      ? h(
          "div",
          { class: "photo-field__confirm", role: "alertdialog", "aria-label": "确认替换照片" },
          icon("alert-triangle", { size: 14 }),
          h(
            "span",
            { class: "stack", style: { gap: "2px" } },
            h("span", null, "替换会覆盖当前照片，原图不保留。"),
            h("span", { class: "small muted" }, "已保存的简历不回收照片，可随时改回。"),
          ),
          h(
            "span",
            { class: "row", style: { gap: "var(--sp-2)" } },
            button({ label: "取消", size: "sm", variant: "quiet", onClick: p.onCancelReplace }),
            button({ label: "确认替换", size: "sm", variant: "danger", onClick: p.onConfirmReplace }),
          ),
        )
      : null,

    p.uploading ? progress({ label: "上传中", value: null }) : null,
    p.error ? h("div", { class: "ui-field__error" }, icon("alert-circle", { size: 13 }), p.error) : null,
    h(
      "p",
      { class: "small muted" },
      "支持 JPG / PNG，建议 ≥400×400（小于 400 会偏糊）。照片只存在本地目录，不会进入任何 LLM 请求。",
    ),
  );
}

/**
 * 右侧：命名实时预览（与导出页同一套 {position}-{name}-{school}）
 * @param {{
 *  template?:string, position?:string,
 *  result?:{valid:boolean,filename?:string,errors?:Array<{code:string,message:string}>,warnings?:Array},
 *  lang?:"zh"|"en", missingSchool?:boolean, pending?:boolean,
 *  onGoBuild?:Function
 * }} p
 */
export function profileNamingPreview(p = {}) {
  const template = p.template || "{position}-{name}-{school}";
  const errors = (p.result && p.result.errors) || [];
  const blocked = Boolean(p.missingSchool) || errors.some((e) => e.code === "NAMING_MISSING_VAR");
  const filename = p.result && p.result.filename;

  return h(
    "div",
    { class: cx("profile-side__card", blocked ? "is-blocked" : "") },
    h(
      "div",
      { class: "row", style: { justifyContent: "space-between", alignItems: "baseline" } },
      h("h3", { class: "ui-section__title", style: { margin: "0" } }, "导出文件名预览"),
      badge({ text: p.lang === "en" ? "English" : "中文", tone: p.lang === "en" ? "info" : "neutral" }),
    ),
    h(
      "div",
      { class: cx("naming__filename", blocked || !filename ? "is-invalid" : "") },
      h("span", { class: "naming__filename-label" }, "本次文件名"),
      p.pending ? h("span", { class: "ui-spinner" }) : filename || "（待生成）",
    ),
    h("div", { class: "small muted" }, `模板 ${template}`),
    blocked
      ? h(
          "div",
          { class: "naming__err", role: "alert" },
          icon("alert-circle", { size: 14 }),
          h(
            "span",
            { class: "stack", style: { gap: "var(--sp-2)" } },
            h("strong", null, MISSING_SCHOOL_MSG),
            h("span", { class: "small" }, "补上学校（中文或英文，按简历语言）即可解除。"),
            p.onGoBuild
              ? h("span", null, button({ label: "去组装页看看", size: "sm", variant: "ghost", onClick: p.onGoBuild }))
              : null,
          ),
        )
      : null,
    !blocked && errors.length
      ? h(
          "div",
          { class: "naming__err", role: "alert" },
          icon("alert-circle", { size: 14 }),
          h("span", { class: "stack", style: { gap: "2px" } }, errors.map((e) => h("span", null, e.message || e.code))),
        )
      : null,
    !blocked && !errors.length
      ? h("div", { class: "naming__warn naming__warn--success" }, icon("check-circle", { size: 12 }), "命名所需字段齐全")
      : null,
    h(
      "p",
      { class: "small muted" },
      "{name} 取中文姓名或英文姓名（跟随简历语言）；{school} 同理。缺字段时报错，不会生成残缺文件名。",
    ),
  );
}

/**
 * 完整度（completeness 0–1 + missing 字段）
 * @param {{value?:number, missing?:string[]}} p
 */
export function completenessMeter(p = {}) {
  const v = Math.max(0, Math.min(1, Number(p.value) || 0));
  const missing = p.missing || [];
  return h(
    "div",
    { class: "completeness" },
    h("div", { class: "row", style: { justifyContent: "space-between" } },
      h("span", { class: "small" }, "资料完整度"),
      h("span", { class: "mono small" }, `${Math.round(v * 100)}%`),
    ),
    progress({ value: Math.round(v * 100), label: "资料完整度" }),
    missing.length
      ? h(
          "div",
          { class: "stack", style: { gap: "var(--sp-2)" } },
          h("span", { class: "small muted" }, "还缺："),
          h(
            "div",
            { class: "ui-chip-set" },
            missing.map((m) => chip({ label: PROFILE_FIELD_LABELS[m] || m, tone: "warn", mono: true })),
          ),
        )
      : h("span", { class: "small muted" }, "关键字段都齐了。"),
  );
}

export { select };
