/**
 * feedback.js — 交互反馈的四态契约（idle → pending → success → error）
 *
 * 这个模块只解决「一次会等服务器的动作该怎么表现」：
 *   1. pending：按钮进入 loading、禁用、文案改成进行时（防止重复提交）；
 *   2. success：内联或 toast 给结果，且可关闭；
 *   3. error：说清「发生了什么 + 下一步 + 是否可重试」；
 *   4. 乐观更新失败要能回滚（optimistic / inlineError）。
 *
 * 约束：纯展示层，不发起请求、不 import api 层、不读写 localStorage。
 */

import { h, cx, clear } from "./dom.js";
import { icon } from "./icons.js";
import { badge, button, callout, iconButton, spinner } from "./primitives.js";
import { describeError } from "./errors.js";

/** 四态枚举（页面里用常量，避免拼写漂移） */
export const PHASE = { idle: "idle", pending: "pending", success: "success", error: "error" };

/**
 * 哪些错误值得让用户点「重试」。
 * 依据：网络抖动、服务端内部错误、上游模型暂时失败、渲染引擎偶发失败——
 * 这些重试有意义；参数类错误（命名缺失、不支持的格式、未配置、未授权）重试也不会变好。
 */
export const RETRYABLE_CODES = new Set([
  "NETWORK",
  "HTTP_5XX",
  "INTERNAL",
  "LLM_TIMEOUT",
  "LLM_RATE_LIMIT",
  "LLM_UPSTREAM",
  "LLM_BAD_RESPONSE",
  "JOB_INTERRUPTED",
  "RENDER_FAILED",
  "EXPORT_FAILED",
  "PDF_ENGINE_MISSING",
  "FONT_UNAVAILABLE",
  "FILE_IN_USE",
  "CONFLICT",
]);

/** 明确「重试也不会变好」的错误码（用于文案，不让用户白点） */
export const NON_RETRYABLE_CODES = new Set([
  "VALIDATION_ERROR",
  "NAMING_POSITION_MISSING",
  "NAMING_NAME_MISSING",
  "NAMING_SCHOOL_MISSING",
  "NAMING_INVALID",
  "IMPORT_UNSUPPORTED",
  "IMPORT_FILE_TOO_LARGE",
  "IMPORT_PARSE_FAILED",
  "IMPORT_EMPTY",
  "LLM_NOT_CONFIGURED",
  "LLM_AUTH",
  "NO_DEFAULT_TEMPLATE",
  "TEMPLATE_INVALID",
  "MISSING_SLOTS",
  "EMPTY_SELECTION",
  "PROFILE_INCOMPLETE",
  "PAGE_OVERFLOW",
  "CONSENT_EXPIRED",
  "NOT_FOUND",
  "BAD_REQUEST",
]);

/** 显示/隐藏：用 style.display，不用 hidden 属性。
 *  hidden 属性靠 UA 的 [hidden]{display:none}，而 .ui-btn/.ui-spinner/.badge 这些类自带
 *  author 级 display（inline-flex/inline-block），会压过 UA 规则 —— 之前星标和「重试」按钮
 *  因此在该隐藏时仍然画出来（用户把星标误读成关闭叉号）。 */
function setShown(node, shown) {
  if (!node) return;
  node.hidden = !shown;
  node.style.display = shown ? "" : "none";
}

/** 某个错误是否值得重试 */
export function isRetryable(err) {
  const code = err && err.code ? String(err.code) : "";
  if (RETRYABLE_CODES.has(code)) return true;
  if (NON_RETRYABLE_CODES.has(code)) return false;
  const status = err && Number(err.status);
  if (status >= 500 || status === 429 || status === 408) return true;
  // 未识别的错误：默认给一次重试机会（有按钮比没按钮好，用户至少能自己判断）
  if (!code || code === "UNKNOWN") return true;
  return false;
}

/**
 * 四态行动按钮。
 *
 * @param {object} p
 * @param {string} p.label 空闲文案
 * @param {string} [p.pendingLabel] 进行时文案（默认「处理中…」）
 * @param {string} [p.successLabel] 成功短暂文案（默认回到 label）
 * @param {Function} [p.onClick] 若提供，点击自动走 run()（带防重入）
 * @param {Function} [p.run] 需要自定义时由页面调用 action.run(executor)
 * @returns {{node:HTMLButtonElement, run:Function, reset:Function, state:string, setDisabled:Function}}
 */
export function createAction(p = {}) {
  let label = p.label || "";
  const pendingLabel = p.pendingLabel || "处理中…";
  const successLabel = p.successLabel || label;

  const labelNode = h("span", { class: "ui-btn__label" }, label);
  const spinNode = spinner();
  const spinSlot = h(
    "span",
    {
      class: "ui-action__spin",
      "aria-hidden": "true",
      style: {
        // 用 display 控制显隐：inline-flex 写在 style 上会压过 UA 的 [hidden]{display:none}，
        // 之前正是靠 hidden 属性隐藏，结果 idle 态也把星标画了出来（用户误读成关闭叉号）。
        display: "none",
        alignItems: "center",
        justifyContent: "center",
        width: "14px",
        height: "14px",
        flex: "0 0 auto",
      },
    },
    spinNode,
  );
  // pending 时才让出 14px 槽位；idle 不占位（不留空白缺口），宽度由 createAction 里量好的 min-width 兜住
  spinSlot.style.display = "none";

  const iconNode = p.icon ? icon(p.icon, { size: p.size === "sm" ? 14 : 15, cls: "ui-btn__icon" }) : null;

  const node = h(
    "button",
    {
      // 必须显式给出 variant 类：.ui-btn 裸类是透明底/透明边（靠 --btn-* 变量），
      // 缺 ui-btn--secondary 时会渲染成「只有文字、没有按钮外观」，与 primitives.button 的默认值保持一致。
      class: cx("ui-btn", `ui-btn--${p.variant || "secondary"}`, p.size ? `ui-btn--${p.size}` : "", p.block ? "ui-btn--block" : ""),
      type: p.type || "button",
      title: p.title,
      "aria-label": p.ariaLabel,
      "aria-busy": "false",
      disabled: Boolean(p.disabled),
      dataset: { phase: PHASE.idle },
    },
    spinSlot,
    iconNode,
    labelNode,
    p.iconRight ? icon(p.iconRight, { size: 14, cls: "ui-btn__icon" }) : null,
  );

  let externalDisabled = Boolean(p.disabled);

  // 预留宽度：让「空闲文案」和「进行时文案」都放得下，状态切换时按钮不会抽动。
  // 设计稿 D6 担心「改文案会让宽度跳」，但用户明确要求进行时有文案——预留宽度后两者可兼得。
  // 在插入页面之前离屏量一次，量不到就退回原行为（不预留）。
  (() => {
    try {
      if (!document.body) return;
      node.style.position = "absolute";
      node.style.visibility = "hidden";
      node.style.pointerEvents = "none";
      node.style.minWidth = "0";
      document.body.appendChild(node);
      const idleWidth = node.getBoundingClientRect().width;
      labelNode.textContent = pendingLabel;
      const pendingWidth = node.getBoundingClientRect().width;
      const successWidth = successLabel === label ? 0 : (() => {
        labelNode.textContent = successLabel;
        return node.getBoundingClientRect().width;
      })();
      labelNode.textContent = label;
      node.remove();
      node.style.position = "";
      node.style.visibility = "";
      node.style.pointerEvents = "";
      const reserve = Math.ceil(Math.max(idleWidth, pendingWidth, successWidth));
      if (reserve > 0) node.style.minWidth = `${reserve}px`;
    } catch (_error) {
      // 量不到（例如被 CSP/布局限制）就不预留，退化为「文案变化自然撑宽」
      node.style.minWidth = "";
    }
  })();

  const api = {
    node,
    state: PHASE.idle,
    /** 外部禁用（例如前置条件不满足）时用；pending 期间不接受解除 */
    setDisabled(flag) {
      externalDisabled = Boolean(flag);
      if (api.state === PHASE.pending) return;
      node.disabled = externalDisabled;
    },
  };

  function paint(state, text) {
    api.state = state;
    // 双写：data-state 是规范名（UX-FEEDBACK-PLAN §7 D1），data-phase 是 uiverse.css 的历史选择器
    node.dataset.state = state;
    node.dataset.phase = state;
    node.setAttribute("aria-busy", state === PHASE.pending ? "true" : "false");
    // 文案随状态切换（宽度已在 createAction 里预留，所以不会抽动）。
    // 注意：不要在这里清 min-width —— 一清就会在退出 pending 时再跳一次。
    if (text !== undefined) labelNode.textContent = text;
    const pending = state === PHASE.pending;
    // 无图标：idle 完全不留前置符号（display:none），pending 才显示 14px 星标；
    // 有图标：idle 显示自己的图标，pending 把图标换成星标（宽度由 min-width 预留）。
    spinSlot.style.display = pending ? "inline-flex" : "none";
    if (iconNode) setShown(iconNode, !pending);
    // pending 期间用 aria-disabled + CSS pointer-events:none 挡重复提交，**不**用原生 disabled：
    // 原生 disabled 会让按钮丢焦点，键盘用户被弹回页面顶部（UX-FEEDBACK-PLAN §7 D5 / UI-REFRESH §3.1 缺口①）。
    // 重复点击由 run() 里的 L1 同步守卫兜住，回车提交同样走 click。
    // 原生 disabled 只留给「结构性不可用」（缺中文字体、没有模板）。
    const inert = state === PHASE.pending;
    node.disabled = externalDisabled;
    node.setAttribute("aria-disabled", inert || externalDisabled ? "true" : "false");
    if (state === PHASE.pending) node.setAttribute("aria-label", `${labelNode.textContent}（进行中）`);
    else node.removeAttribute("aria-label");
  }

  /**
   * 执行一次动作。pending 期间重复调用直接丢弃（不产生第二个请求）。
   * @returns {Promise<{ok:boolean, value?:any, error?:any, skipped?:boolean}>}
   */
  async function run(executor, opts = {}) {
    if (api.state === PHASE.pending) return { ok: false, skipped: true };
    if (typeof executor !== "function") return { ok: false, skipped: true };

    paint(PHASE.pending, opts.pendingLabel || pendingLabel);
    let value;
    try {
      value = await executor();
    } catch (error) {
      paint(PHASE.error, opts.errorLabel || label);
      if (typeof opts.onError === "function") opts.onError(error);
      return { ok: false, error };
    }
    paint(PHASE.success, opts.successLabel || successLabel);
    // 成功文案停留一会儿再回到空闲，给用户一个「确实发生了」的确认
    const hold = opts.holdMs === undefined ? 1200 : Number(opts.holdMs) || 0;
    if (hold > 0) {
      window.setTimeout(() => {
        if (api.state === PHASE.success) paint(PHASE.idle, label);
      }, hold);
    } else {
      paint(PHASE.idle, label);
    }
    if (typeof opts.onSuccess === "function") opts.onSuccess(value);
    return { ok: true, value };
  }

  api.run = run;
  /** 改空闲文案（例如「导出 PDF」→「导出 PDF（缺中文字体）」），不影响 pending/success 文案 */
  api.setLabel = (text) => {
    label = String(text === undefined ? p.label || "" : text);
    if (api.state === PHASE.idle) paint(PHASE.idle, label);
  };
  api.reset = () => paint(PHASE.idle, label);
  paint(PHASE.idle, label);

  if (typeof p.onClick === "function") {
    node.addEventListener("click", () => {
      run(() => p.onClick());
    });
  }

  return api;
}

/**
 * 内联反馈区：一个带 aria-live 的容器，页面把它放在动作用户视线自然落点。
 * 空着的时候不占高度；有内容时由调用方决定位置（建议放在按钮上方或列表头部）。
 *
 * @param {object} p
 * @param {"polite"|"assertive"} [p.live="polite"]
 * @param {string} [p.label] aria-label（给读屏的区块名）
 */
export function feedbackRegion(p = {}) {
  const ariaLabel = p.label || "操作状态";
  const layerStyle = {
    gridArea: "1 / 1",
    minWidth: "0",
    opacity: "0",
    visibility: "hidden",
    transition: "opacity var(--dur-2) var(--ease), visibility 0s linear var(--dur-2)",
  };
  const showStyle = {
    ...layerStyle,
    opacity: "1",
    visibility: "visible",
    transition: "opacity var(--dur-2) var(--ease), visibility 0s",
  };

  function makeLayer(name, children) {
    return h(
      "div",
      {
        class: `ux-feedback__${name}`,
        dataset: { uxLayer: name },
        style: { ...layerStyle },
        "aria-hidden": "true",
      },
      children,
    );
  }

  // ---- pending ----
  const pendingTitle = h("div", { class: "ui-callout__title" }, "正在处理…");
  const pendingBody = h("div", { class: "ui-callout__body", style: { margin: "0" } }, null);
  const pendingLayer = makeLayer(
    "pending",
    h(
      "div",
      { class: "ui-callout ui-callout--info", role: "status" },
      icon("clock", { size: 16, cls: "ui-callout__icon" }),
      h("div", { class: "ui-callout__main" }, pendingTitle, pendingBody),
      spinner({ size: 14 }),
    ),
  );

  // ---- success（凭证 + 可关闭）----
  const successTitle = h("div", { class: "ui-callout__title" }, "完成");
  const successBody = h("div", { class: "ui-callout__body", style: { margin: "0" } }, null);
  const successActions = h("div", { class: "ui-callout__actions" }, null);
  const successClose = iconButton({
    icon: "x",
    label: "关闭这条结果",
    size: "sm",
    variant: "quiet",
    onClick: () => {
      idle({ silent: true });
      if (typeof handlers.onClose === "function") handlers.onClose();
    },
  });
  const successLayer = makeLayer(
    "success",
    h(
      "div",
      { class: "ui-callout ui-callout--success", role: "status" },
      icon("check-circle", { size: 16, cls: "ui-callout__icon" }),
      h("div", { class: "ui-callout__main" }, successTitle, successBody, successActions),
      successClose,
    ),
  );

  // ---- error（三段式：发生了什么 / 下一步 / 能不能重试）----
  const errTitle = h("div", { class: "ui-callout__title" }, "失败了");
  const errWhatText = h("span", null, "");
  const errNextText = h("span", null, "");
  const errRetryNoteStrong = h("strong", null, "可以重试。");
  const errRetryNoteText = h("span", null, "");
  const errCodeBadge = badge({ text: "错误码", tone: "danger" });
  const errRetryLabel = h("span", { class: "ui-btn__label" }, "重试");
  let retryHandler = null;
  const errRetryBtn = h(
    "button",
    {
      class: "ui-btn ui-btn--primary ui-btn--sm",
      type: "button",
      hidden: true,
      onClick: () => {
        if (handlers.retry && typeof retryHandler === "function") retryHandler();
      },
    },
    icon("refresh", { size: 14, cls: "ui-btn__icon" }),
    errRetryLabel,
  );
  const errActionLabel = h("span", { class: "ui-btn__label" }, "去处理");
  let actionHandler = null;
  const errActionBtn = h(
    "button",
    {
      class: "ui-btn ui-btn--secondary ui-btn--sm",
      type: "button",
      hidden: true,
      onClick: () => {
        if (typeof actionHandler === "function") actionHandler();
      },
    },
    icon("arrow-right", { size: 14, cls: "ui-btn__icon" }),
    errActionLabel,
  );
  const errClose = iconButton({
    icon: "x",
    label: "关闭这条错误",
    size: "sm",
    variant: "quiet",
    onClick: () => {
      idle({ silent: true });
      if (typeof handlers.onClose === "function") handlers.onClose();
    },
  });
  const errorLayer = makeLayer(
    "error",
    h(
      "div",
      { class: "ui-callout ui-callout--danger", role: "alert" },
      icon("alert-circle", { size: 16, cls: "ui-callout__icon" }),
      h(
        "div",
        { class: "ui-callout__main" },
        errTitle,
        h(
          "div",
          { class: "ui-callout__body", style: { margin: "0" } },
          h("p", { style: { margin: "0" } }, errWhatText),
          h("p", { style: { margin: "var(--sp-2) 0 0" } }, h("strong", null, "下一步："), errNextText),
          h(
            "p",
            { style: { margin: "var(--sp-2) 0 0", color: "var(--c-text-2)" } },
            errRetryNoteStrong,
            errRetryNoteText,
          ),
          h(
            "div",
            { class: "row", style: { gap: "var(--sp-3)", flexWrap: "wrap", alignItems: "center", marginTop: "var(--sp-3)" } },
            errCodeBadge,
            errRetryBtn,
            errActionBtn,
          ),
        ),
      ),
      errClose,
    ),
  );

  const idleLayer = makeLayer("idle", null);

  // 唯一的播报通道：读屏只在「状态变了」时听到一句话（R5）
  const live = h("span", {
    class: "sr-only",
    "data-ux-live": "true",
    "aria-live": "polite",
    "aria-atomic": "true",
  });
  let lastAnnounce = "";

  const layers = { idle: idleLayer, pending: pendingLayer, success: successLayer, error: errorLayer };

  // D3（F17）：反馈区做成「锚定覆盖层」——外层锚点高度恒为 0，不参与文档流，
  // 四态都在这里换内容，所以下方任何元素的 getBoundingClientRect().top 都不动。
  // 区域本身绝对定位并自带轻投影，出现/消失只走 opacity + translateY。
  const node = h(
    "div.ux-feedback",
    {
      "data-region": "feedback",
      "data-phase": "idle",
      "data-state": "idle",
      "aria-live": "polite",
      "aria-atomic": "true",
      "aria-busy": "false",
      "aria-label": ariaLabel,
      role: "group",
      style: {
        position: "absolute",
        top: "0",
        insetInlineStart: "0",
        width: "100%",
        maxWidth: "460px",
        zIndex: "6",
        display: "grid",
        minWidth: "0",
        borderRadius: "var(--r-md)",
        boxShadow: "var(--sh-3)",
        background: "var(--c-surface)",
        opacity: "0",
        visibility: "hidden",
        transform: "translateY(-4px)",
        pointerEvents: "none",
        ...(p.style || {}),
      },
    },
    idleLayer,
    pendingLayer,
    successLayer,
    errorLayer,
    live,
  );

  // 锚点：唯一插入页面的节点。height:0 → 无论四态怎么切，占位高度都是 0。
  const anchor = h(
    "div",
    {
      class: "ux-feedback-anchor",
      "data-ux-feedback-anchor": "true",
      style: { position: "relative", height: "0", minHeight: "0", display: "block", zIndex: "5" },
    },
    node,
  );

  const handlers = { onClose: undefined, retry: false };

  function announce(text) {
    if (!text || text === lastAnnounce) return;
    lastAnnounce = text;
    // 先清空再写入，保证同一句话连续两次也能被读屏播报
    live.textContent = "";
    window.setTimeout(() => {
      live.textContent = text;
    }, 20);
  }

  function setState(state) {
    const active = layers[state] ? state : "idle";
    node.dataset.state = active;
    node.dataset.phase = active;
    node.setAttribute("aria-busy", active === "pending" ? "true" : "false");
    // 任何状态都不改 display（改了才是 153px 跳动的根源）：只切透明度与位移。
    // prefers-reduced-motion 直接关掉过渡，避免「空间感」动画在无动画偏好下仍然发生。
    const shown = active !== "idle";
    const reduce = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    node.style.display = "grid";
    node.style.opacity = shown ? "1" : "0";
    node.style.visibility = shown ? "visible" : "hidden";
    node.style.transform = shown ? "translateY(0)" : "translateY(-4px)";
    node.style.pointerEvents = shown ? "auto" : "none";
    node.style.transition = reduce
      ? "none"
      : `opacity var(--dur-2) var(--ease), transform var(--dur-2) var(--ease), visibility 0s linear ${shown ? "0s" : "var(--dur-2)"}`;
    for (const [name, el] of Object.entries(layers)) {
      const on = name === active;
      Object.assign(el.style, on ? showStyle : layerStyle);
      el.setAttribute("aria-hidden", on ? "false" : "true");
      el.inert = !on;
    }
    return active;
  }

  /** idle：区域归零（:empty 不适用，因为四块是预渲染的，用 display:none 收起来） */
  function idle(opts = {}) {
    setState("idle");
    if (!opts.silent) announce("");
    return node;
  }

  function pending(title, detail) {
    pendingTitle.textContent = title || "正在处理…";
    pendingBody.textContent = detail || "";
    setShown(pendingBody, Boolean(detail));
    setState("pending");
    announce(`${title || "正在处理"}${detail ? `。${detail}` : ""}`);
    return node;
  }

  function success(p2 = {}) {
    successTitle.textContent = p2.title || "完成";
    clear(successBody);
    if (p2.body) {
      // 调用点大多传字符串（builds/jobs/profile/settings/templates/workbench 共 10 处），
      // 直接 appendChild 会抛 TypeError: parameter 1 is not of type 'Node' ——
      // 用户看到的是「组装成功却红条报失败」。这里统一兜底。
      successBody.appendChild(
        p2.body instanceof Node ? p2.body : document.createTextNode(String(p2.body)),
      );
    }
    setShown(successBody, Boolean(p2.body));
    clear(successActions);
    for (const action of p2.actions || []) if (action) successActions.appendChild(action);
    setShown(successActions, Boolean(p2.actions && p2.actions.length));
    setShown(successClose, p2.closable !== false);
    setState("success");
    announce(`${p2.title || "完成"}${p2.announce ? `。${p2.announce}` : ""}`);
    return node;
  }

  function error(err, opts = {}) {
    const copy = describeError(err);
    const retryable = opts.retryable === undefined ? isRetryable(err) : Boolean(opts.retryable);
    const detail =
      err && err.message && err.message !== copy.title && err.message !== copy.body ? String(err.message) : "";
    errTitle.textContent = copy.title || "失败了";
    errWhatText.textContent = copy.body || detail || "服务端返回了错误，但没给出具体原因。";
    errNextText.textContent =
      opts.hint || copy.hint || (retryable ? "稍等几秒后点「重试」。" : "先处理上面的原因，再回来继续。");
    errRetryNoteStrong.textContent = retryable ? "可以重试。" : "重试不会解决问题。";
    errRetryNoteText.textContent = retryable
      ? opts.retryNote || "这次失败是暂时的，再点一次通常就能过去。"
      : "这是参数/配置类问题，需要先改上面的内容。";
    errCodeBadge.textContent = `技术细节：${(err && err.code) || "UNKNOWN"}`;
    setShown(errCodeBadge, Boolean(err && err.code));
    retryHandler = typeof opts.onRetry === "function" ? opts.onRetry : null;
    errRetryLabel.textContent = opts.retryLabel || "重试";
    setShown(errRetryBtn, Boolean(retryable && retryHandler));
    actionHandler = typeof opts.onAction === "function" ? opts.onAction : null;
    errActionLabel.textContent =
      opts.actionLabel ||
      (copy.action === "settings" ? "去设置页" : copy.action === "profile" ? "去补全资料" : "去处理");
    setShown(errActionBtn, Boolean(actionHandler));
    setState("error");
    announce(`${copy.title || "失败了"}。下一步：${errNextText.textContent}。${errRetryNoteStrong.textContent}`);
    return node;
  }

  // 对外只暴露锚点：页面 `stack` 里插 fb.node，高度恒为 0；
  // 需要拿区域本体的验收脚本仍可用 `.ux-feedback` / `[data-region="feedback"]` 定位。
  return { node: anchor, region: node, idle, pending, success, error, set: null, announce };
}

/** 别名：文档与验收脚本里两种叫法都出现过 */
export const feedback = feedbackRegion;

export function inlineError(message, opts = {}) {
  const node = h(
    "div",
    {
      class: "small",
      role: "status",
      "aria-live": "polite",
      style: { color: "var(--c-danger)", display: "flex", gap: "var(--sp-2)", alignItems: "center" },
    },
    icon("alert-circle", { size: 12 }),
    h("span", null, message),
  );
  if (opts.onDismiss) {
    node.appendChild(
      iconButton({ icon: "x", label: "关闭这条说明", size: "sm", variant: "quiet", onClick: opts.onDismiss }),
    );
  }
  return node;
}

/**
 * 防重复提交的门闩（非按钮场景：表单回车、快捷键、拖拽触发…）。
 * 同一时刻只放行一个执行体。
 */
export function submitGuard() {
  let busy = false;
  const gate = async (fn) => {
    if (busy) return { ok: false, skipped: true };
    busy = true;
    try {
      return { ok: true, value: await fn() };
    } catch (error) {
      return { ok: false, error };
    } finally {
      busy = false;
    }
  };
  gate.isBusy = () => busy;
  return gate;
}

/**
 * 乐观更新：先本地生效，请求失败则回滚。
 * @param {object} p
 * @param {Function} p.apply 本地先改（同步）
 * @param {Function} p.commit 真正发请求（返回 Promise）
 * @param {Function} p.revert 失败时回滚（同步）
 * @param {Function} [p.onError] 失败回调，拿到 err；页面在这里给出该元素附近的错误说明
 */
export async function optimistic(p = {}) {
  const { apply, commit, revert, onError } = p;
  if (typeof apply === "function") apply();
  try {
    const value = await commit();
    return { ok: true, value };
  } catch (error) {
    if (typeof revert === "function") revert();
    if (typeof onError === "function") onError(error);
    return { ok: false, error };
  }
}

/** 阶段文案：耗时显示（长任务用，避免用户怀疑卡死） */
export function elapsedText(startMs, nowMs = Date.now()) {
  const ms = Math.max(0, nowMs - startMs);
  if (ms < 1000) return "已用时 <1s";
  const s = ms / 1000;
  if (s < 60) return `已用时 ${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  return `已用时 ${m}m${String(Math.round(s % 60)).padStart(2, "0")}s`;
}
