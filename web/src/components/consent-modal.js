/**
 * consent-modal.js — 「将发送字段清单」隐私确认弹层（不可绕过）
 *
 * 硬要求（见 docs/DESIGN-BRIEF.md · ConsentModal）：
 *  1. 每次调用 LLM 前必须出现；没有「不再提示」。
 *  2. 字段逐条列出：中文标签 + 字符数 + 估算 token；可折叠分组之外的主视野能看到
 *     「未被发送的内容」（excluded.note / skipped）与「已脱敏的位置」（redactions）。
 *  3. Esc 或点击遮罩 = 取消；Enter **不得**等同于确认。
 *  4. 过期（expires_at 已过）时把确认按钮换成「重新生成预览」。
 *  5. 发送失败时不关闭弹层，在底部显示错误条。
 *  6. 确认按钮文案带 provider / model / 估算 token 数。
 *  7. 不显示 API Key 片段、不显示完整 payload（折进 <details>，且由后端脱敏后给出）。
 */

import { h, cx, trapFocus, escToClose } from "./dom.js";
import { icon } from "./icons.js";
import { badge, button, callout, kv } from "./primitives.js";

/** 字段类型中文名（API-CONTRACT §10.2 fields[].kind） */
export const KIND_LABELS = {
  resume_fragment: "简历片段",
  system_prompt: "系统指令",
  user_instruction: "你的附加要求",
  jd_text: "JD 原文",
  company_note: "公司备注",
};

/**
 * 本次调用的用途（决定「这次到底在做什么」的文案）。
 * 模型名不在这里：它必须来自 `POST /consent/preview` 的 `model` 字段，
 * 因为同一服务商对不同用途会用不同模型（例如 JD 分析用 reasoner、改写用 chat）。
 */
export const PURPOSE_LABELS = {
  jd_analyze: "JD 与公司分析",
  company_profile: "公司招聘偏好分析",
  resume_assemble: "简历改写（组装）",
  resume_polish: "简历措辞润色",
  import_fallback: "导入解析兜底",
};

/** 用途兜底：拿不到 purpose 就说泛称，不编造具体环节 */
export function purposeLabel(purpose) {
  if (!purpose) return "定制简历生成";
  return PURPOSE_LABELS[purpose] || purpose;
}

/** 模型名是否可用（拿不到时宁可说不知道，也不显示默认值） */
export function hasModel(d) {
  return Boolean(d && typeof d.model === "string" && d.model.trim());
}

const KIND_TONES = {
  resume_fragment: "neutral",
  system_prompt: "info",
  user_instruction: "accent",
  jd_text: "warn",
  company_note: "neutral",
};

const SOURCE_LABELS = {
  package: "经历库",
  variant: "表述变体",
  profile: "个人资料",
  jd: "目标职位",
  company: "公司信息",
  setting: "设置",
  user: "手动输入",
  system: "系统",
};

function fmt(n) {
  if (typeof n !== "number" || Number.isNaN(n)) return "—";
  return n.toLocaleString("zh-CN");
}

/**
 * 单个字段行
 * @param {{field:{path:string,label:string,kind:string,source?:string,source_id?:string,
 *                  package_title?:string,chars?:number,est_tokens?:number,
 *                  included?:boolean,redacted?:boolean}}} p
 */
export function consentFieldRow(p = {}) {
  const f = p.field || {};
  const excluded = f.included === false;
  return h(
    "div",
    { class: cx("modal__field", excluded ? "is-excluded" : "") },
    h(
      "span",
      { class: "modal__field-kind" },
      badge({ text: KIND_LABELS[f.kind] || f.kind || "字段", tone: KIND_TONES[f.kind] || "neutral" }),
    ),
    h(
      "span",
      { class: "modal__field-main" },
      h("span", { class: "modal__field-label" }, f.label || f.path),
      h(
        "span",
        { class: "modal__field-meta mono" },
        f.path,
        f.package_title ? ` · ${f.package_title}` : "",
        f.source ? ` · ${SOURCE_LABELS[f.source] || f.source}` : "",
      ),
    ),
    h(
      "span",
      { class: "modal__field-stat" },
      f.redacted ? badge({ text: "已脱敏", tone: "warn" }) : null,
      excluded ? badge({ text: "不发送", tone: "neutral" }) : null,
      h("span", { class: "mono small" }, `${fmt(f.chars)} 字`),
      h("span", { class: "mono small muted" }, `≈${fmt(f.est_tokens)} tok`),
    ),
  );
}

/**
 * 隐私确认弹层
 * @param {{
 *  data:{
 *    preview_id:string, purpose?:string, provider:string, model:string,
 *    endpoint_host?:string, expires_at?:string, total_chars?:number, est_tokens?:number,
 *    payload_sha256?:string, payload?:string,
 *    fields?:Array, excluded?:{packages_total?:number,packages_selected?:number,
 *      variants_total?:number,variants_selected?:number,skipped?:Array<string>,note?:string},
 *    redactions?:Array<{path:string,match?:string,value_preview?:string,replacement?:string,count?:number}>,
 *    warnings?:Array<{code:string,message:string}>
 *  },
 *  expired?:boolean, sending?:boolean, error?:string,
 *  onConfirm?:Function, onCancel?:Function, onRegenerate?:Function
 * }} p
 */
export function consentModal(p = {}) {
  const d = p.data || {};
  const fields = (d.fields || []).filter((f) => f.included !== false);
  const excludedFields = (d.fields || []).filter((f) => f.included === false);
  const ex = d.excluded || {};
  const redactions = d.redactions || [];
  const skipped = ex.skipped || [];
  const expired = Boolean(p.expired);

  const body = h(
    "div",
    { class: "modal__body" },

    // 顶部：这次要发到哪儿、为什么
    h(
      "div",
      { class: "modal__meta" },
      kv({
        rows: [
          ["服务商", d.provider || "—"],
          ["模型", hasModel(d) ? d.model : "模型未知（将不发送）"],
          ["接口地址", d.endpoint_host || "—"],
          ["本次用途", purposeLabel(d.purpose)],
          ["合计", `${fmt(d.total_chars)} 字 · ≈${fmt(d.est_tokens)} tokens`],
        ],
      }),
      d.payload_sha256
        ? h(
            "div",
            { class: "copy-text" },
            icon("lock", { size: 12 }),
            h("span", { class: "mono" }, `指纹 ${String(d.payload_sha256).slice(0, 16)}…`),
            h("span", { class: "small muted" }, "确认发送前可用它核对内容未被改动"),
          )
        : null,
    ),

    hasModel(d)
      ? null
      : callout({
          tone: "danger",
          icon: "alert-triangle",
          title: "没有拿到本次的模型名，这次不允许发送",
          body: "可能是配置读取失败或服务商切换后没刷新。写错模型等于在隐私声明里说错话，所以这里直接停住 —— 请到设置页确认服务商与模型后，点「重新生成预览」。",
        }),

    callout({
      tone: "info",
      icon: "shield",
      title: "只有下面这些字段会离开本机",
      body: h(
        "span",
        null,
        "其余数据（照片、完整经历库、未选中的变体、附件）全部留在本地。发送内容不含密钥，脱敏项已就地替换。",
      ),
    }),

    // 发送字段
    h(
      "div",
      { class: "modal__section" },
      h(
        "div",
        { class: "modal__section-head" },
        h("h3", { class: "modal__section-title" }, `将要发送（${fields.length} 项）`),
        h("span", { class: "small muted" }, "按字符数与估算 token 排序"),
      ),
      h(
        "div",
        { class: "modal__fields" },
        fields.length
          ? fields.map((f) => consentFieldRow({ field: f }))
          : h("div", { class: "small muted" }, "没有可发送的字段。"),
      ),
    ),

    // 未发送（主视野可见，不折叠）
    h(
      "div",
      { class: "modal__excluded" },
      h(
        "div",
        { class: "modal__excluded-head" },
        icon("shield", { size: 14 }),
        h("strong", null, "不会发送"),
      ),
      h(
        "div",
        { class: "modal__excluded-grid" },
        h("span", null, `经历 ${ex.packages_selected ?? 0} / ${ex.packages_total ?? 0} 条被选中`),
        h("span", null, `表述 ${ex.variants_selected ?? 0} / ${ex.variants_total ?? 0} 条被选中`),
      ),
      skipped.length
        ? h(
            "div",
            { class: "modal__excluded-list" },
            h("span", { class: "small muted" }, "被跳过的："),
            skipped.map((s) => h("span", { class: "modal__excluded-item" }, s)),
          )
        : null,
      excludedFields.length
        ? h(
            "div",
            { class: "modal__excluded-list" },
            h("span", { class: "small muted" }, "标记为不发送的字段："),
            excludedFields.map((f) => h("span", { class: "modal__excluded-item mono" }, f.path)),
          )
        : null,
      ex.note ? h("p", { class: "modal__excluded-note" }, ex.note) : null,
    ),

    // 脱敏
    redactions.length
      ? h(
          "div",
          { class: "modal__redactions" },
          h(
            "div",
            { class: "modal__redactions-head" },
            icon("alert-triangle", { size: 14 }),
            h("strong", null, `已脱敏 ${redactions.length} 处`),
            h("span", { class: "small muted" }, "这些内容在发送前已替换，不会出现在请求里"),
          ),
          redactions.map((r) =>
            h(
              "div",
              { class: "modal__redaction-row" },
              h("span", { class: "mono small" }, r.path),
              r.match ? h("span", { class: "small" }, r.match) : null,
              h("span", { class: "mono small" }, r.value_preview || "••••"),
              h("span", { class: "small muted" }, `→ ${r.replacement || "[REDACTED]"}`),
              typeof r.count === "number" && r.count > 1 ? h("span", { class: "small muted" }, `×${r.count}`) : null,
            ),
          ),
        )
      : null,

    // 警告
    d.warnings && d.warnings.length
      ? h(
          "div",
          { class: "stack" },
          d.warnings.map((w) =>
            h(
              "div",
              { class: "naming__warn naming__warn--warn" },
              icon("alert-triangle", { size: 12 }),
              w.message || w.code,
            ),
          ),
        )
      : null,

    // 完整 payload（折叠）
    d.payload
      ? h(
          "details",
          { class: "modal__payload ui-details" },
          h("summary", null, "查看将要发送的完整文本（只读）"),
          h("pre", { class: "mono" }, d.payload),
        )
      : null,
  );

  const footer = h(
    "div",
    { class: "modal__foot" },
    p.error ? h("div", { class: "modal__error", role: "alert" }, icon("alert-circle", { size: 14 }), p.error) : null,
    h(
      "div",
      { class: "modal__foot-actions" },
      button({
        label: "取消（不发送）",
        variant: "ghost",
        onClick: p.onCancel,
        kbd: "Esc",
      }),
      expired
        ? button({
            label: "预览已过期 · 重新生成",
            variant: "primary",
            icon: "refresh",
            onClick: p.onRegenerate,
          })
        : button({
            label: hasModel(d) ? `确认发送 · ≈${fmt(d.est_tokens)} tokens` : "模型未知 · 暂不能发送",
            variant: "primary",
            icon: hasModel(d) ? "check" : "alert-triangle",
            disabled: !hasModel(d),
            loading: Boolean(p.sending),
            onClick: p.onConfirm,
          }),
    ),
    h(
      "div",
      { class: "modal__foot-hint" },
      expired
        ? "预览超过有效期，字段可能已变化，请重新生成后再确认。"
        : hasModel(d)
          ? `发送到 ${d.provider || "—"} / ${d.model}；按 Enter 不会发送，必须点这个按钮。`
          : "模型名未知，本次不能发送；按 Enter 也不会发送。",
    ),
  );

  const layer = h(
    "div",
    {
      class: "modal-layer",
      role: "presentation",
      onMouseDown: (ev) => {
        if (ev.target === layer && p.onCancel) p.onCancel();
      },
    },
    h(
      "div",
      {
        class: cx("modal", expired ? "is-expired" : ""),
        role: "dialog",
        "aria-modal": "true",
        "aria-labelledby": "consent-title",
        onKeyDown: (ev) => {
          // Enter 永远不触发确认：焦点在按钮上也要显式点击
          if (ev.key === "Enter" && !ev.target.closest("button[data-allow-enter]")) ev.preventDefault();
        },
      },
      h(
        "div",
        { class: "modal__head" },
        h(
          "div",
          { class: "row", style: { gap: "var(--sp-4)", alignItems: "flex-start" } },
          h("span", { class: "modal__head-icon" }, icon("shield", { size: 18 })),
          h(
            "div",
            { class: "stack", style: { gap: "2px" } },
            h("h2", { class: "modal__title", id: "consent-title" }, "将发送字段清单"),
            h(
              "p",
              { class: "modal__subtitle" },
              "这是唯一一次会联网的操作。确认后才会把下列字段发给所选模型；取消则完全留在本地。",
            ),
          ),
        ),
        button({ label: "取消", variant: "quiet", size: "sm", icon: "x", onClick: p.onCancel, ariaLabel: "关闭并取消发送" }),
      ),
      body,
      footer,
    ),
  );

  // 焦点管理：打开即聚焦对话框，Esc 取消，Tab 循环
  requestAnimationFrame(() => {
    const dialog = layer.querySelector(".modal");
    if (!dialog) return;
    dialog.setAttribute("tabindex", "-1");
    dialog.focus();
    trapFocus(dialog, { onEscape: p.onCancel });
    // 焦点若被用户点到弹层外（例如误点滚动条），trapFocus 收不到 Esc；这一层兜底
    escToClose(layer, p.onCancel);
    layer._dialog = dialog;
  });

  return layer;
}
