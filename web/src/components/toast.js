/**
 * toast.js — 全局轻量通知层（右下角堆叠、逐条可关、Esc 关最上面一条）
 *
 * 定位：纯展示层。不发起请求、不读写 localStorage、不 import api 层；
 * 调用方只传文案与回调。真实的「四态」由 feedback.js / pages 驱动。
 *
 * 可访问性：
 *  - 容器角色 role="region" aria-label="通知"，但**不在容器上**设 aria-live，
 *    而是每条通知自带 role="status"（polite）/ role="alert"（assertive），
 *    避免一次读屏把整层历史重新播报。
 *  - 每条通知都有可聚焦的关闭按钮（iconButton），Tab 可达。
 *  - Esc 关闭最上面一条；关闭后焦点回到打开前的元素（若仍在文档中）。
 *  - 自动消失的通知在 hover / focus 时暂停，移开后续计。
 *  - 动画：全部走 CSS 过渡，prefers-reduced-motion 由 base.css 统一降级。
 */

import { h, cx, clear } from "./dom.js";
import { icon } from "./icons.js";
import { iconButton, button } from "./primitives.js";

const MAX_VISIBLE = 3;

/** 音调 → 视觉/语义映射。is-succeeded / is-failed / is-interrupted 复用 components.css 既有状态样式 */
export const TOAST_TONES = {
  info: { className: "", role: "status", icon: "info", timeout: 5000 },
  success: { className: "is-succeeded", role: "status", icon: "check-circle", timeout: 4500 },
  warn: { className: "is-interrupted", role: "status", icon: "alert-triangle", timeout: 9000 },
  danger: { className: "is-failed", role: "alert", icon: "alert-circle", timeout: 0 },
};

/** 当前挂着的通知（按出现顺序，用于 Esc 关最上面一条） */
const live = [];
let seq = 0;
let escBound = false;
let lastFocus = null;

/** 找到（必要时创建）通知层容器 */
function layer() {
  let host = document.getElementById("toast-root");
  if (!host) {
    host = h("div#toast-root");
    document.body.appendChild(host);
  }
  let box = host.querySelector(".toast-layer");
  if (!box) {
    box = h("div.toast-layer", { role: "region", "aria-label": "通知" });
    host.appendChild(box);
  }
  return box;
}

function bindEsc() {
  if (escBound) return;
  escBound = true;
  document.addEventListener("keydown", onEsc);
}

function unbindEscIfIdle() {
  if (!escBound || live.length) return;
  escBound = false;
  document.removeEventListener("keydown", onEsc);
}

function onEsc(ev) {
  if (ev.key !== "Escape" || !live.length) return;
  // 弹层自己先处理 Esc（trapFocus / escToClose）；只有没有弹层时才轮到通知层
  if (ev.defaultPrevented) return;
  if (document.querySelector(".modal-layer, .drawer-layer")) return;
  ev.preventDefault();
  dismissToast(live[live.length - 1].id);
}

/**
 * 弹出一条通知。
 * @param {object} p
 * @param {"info"|"success"|"warn"|"danger"} [p.tone="info"]
 * @param {string} p.title 一句话结果（读屏主要读它）
 * @param {string} [p.message] 补充说明（发生了什么 / 下一步）
 * @param {HTMLElement|null} [p.actions] 操作区（重试、查看详情、下载…）
 * @param {number} [p.timeout] 毫秒；0 = 不自动消失（默认按 tone）
 * @param {Function} [p.onClose] 关闭回调
 * @param {boolean} [p.closable=true] 是否显示关闭按钮
 * @returns {{id:string, node:HTMLElement, dismiss:Function}}
 */
export function toast(p = {}) {
  const tone = TOAST_TONES[p.tone] ? p.tone : "info";
  const conf = TOAST_TONES[tone];
  const id = p.id || `toast-${++seq}`;
  const box = layer();

  // 同 id 重复弹出：先撤掉旧的，避免双份
  const dup = live.find((t) => t.id === id);
  if (dup) dismissToast(id);

  // 超出上限：最旧的先走（layout 稳定：固定右下角向上堆叠，条目进出不影响主内容）
  while (live.length >= MAX_VISIBLE) dismissToast(live[0].id);

  lastFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;

  const closeBtn = p.closable === false
    ? null
    : iconButton({
        icon: "x",
        label: "关闭通知",
        size: "sm",
        variant: "quiet",
        onClick: () => dismissToast(id),
      });

  const node = h(
    "div",
    {
      class: cx("toast", conf.className),
      role: conf.role,
      "aria-live": tone === "danger" ? "assertive" : "polite",
      "aria-atomic": "true",
      dataset: { toastId: id, tone },
    },
    h(
      "div.toast__head",
      null,
      h("span.toast__icon", { "aria-hidden": "true" }, icon(conf.icon, { size: 16 })),
      h(
        "div",
        { class: "stack", style: { gap: "2px", flex: "1 1 auto", minWidth: "0" } },
        h("div.toast__title", null, p.title || ""),
        p.message ? h("div.toast__stage", null, p.message) : null,
      ),
      closeBtn,
    ),
    p.actions ? h("div.toast__foot", null, p.actions) : null,
  );

  const entry = {
    id,
    node,
    timer: 0,
    remaining: p.timeout === undefined ? conf.timeout : Number(p.timeout) || 0,
    onClose: p.onClose,
  };
  live.push(entry);
  box.appendChild(node);
  bindEsc();

  const arm = () => {
    if (!entry.remaining) return;
    entry.timer = window.setTimeout(() => dismissToast(id), entry.remaining);
  };
  const pause = () => {
    if (!entry.timer) return;
    window.clearTimeout(entry.timer);
    entry.timer = 0;
  };

  node.addEventListener("pointerenter", pause);
  node.addEventListener("pointerleave", () => {
    if (!entry.timer) arm();
  });
  node.addEventListener("focusin", pause);
  node.addEventListener("focusout", (ev) => {
    if (!node.contains(ev.relatedTarget)) {
      if (!entry.timer) arm();
    }
  });

  arm();

  return {
    id,
    node,
    dismiss: () => dismissToast(id),
    pause,
    resume: () => {
      if (!entry.timer) arm();
    },
  };
}

/** 关闭一条通知（带淡出；元素脱离后才真正移除） */
export function dismissToast(id) {
  const idx = live.findIndex((t) => t.id === id);
  if (idx === -1) return false;
  const [entry] = live.splice(idx, 1);
  if (entry.timer) window.clearTimeout(entry.timer);

  const finish = () => {
    entry.node.remove();
    unbindEscIfIdle();
    if (live.length === 0 && lastFocus && lastFocus.isConnected) {
      // 只在整层清空时归还焦点，避免多通知互抢
      try {
        lastFocus.focus({ preventScroll: true });
      } catch {
        /* 忽略：元素可能已不可聚焦 */
      }
    }
    if (typeof entry.onClose === "function") entry.onClose();
  };

  // 退场：优先等 uiverse.css 的 animationend（ux-is-leaving），300ms 兜底。
  // reduced-motion 下 base.css 把动画压到 0.01ms，animationend 几乎立刻到达，不会卡住。
  entry.node.style.pointerEvents = "none";
  entry.node.classList.add("ux-is-leaving");
  entry.node.style.transition = "opacity var(--dur-2) var(--ease), transform var(--dur-2) var(--ease)";
  entry.node.style.opacity = "0";
  entry.node.style.transform = "translateY(4px)";
  let done = false;
  let timer = 0;
  const once = () => {
    if (done) return;
    done = true;
    window.clearTimeout(timer);
    entry.node.removeEventListener("animationend", once);
    finish();
  };
  entry.node.addEventListener("animationend", once, { once: true });
  timer = window.setTimeout(once, 300);
  return true;
}

/** 关掉全部通知 */
export function clearToasts() {
  for (const entry of live.slice()) dismissToast(entry.id);
}

/** 便捷函数 */
export function toastSuccess(title, opts = {}) {
  return toast({ tone: "success", title, ...opts });
}

export function toastInfo(title, opts = {}) {
  return toast({ tone: "info", title, ...opts });
}

export function toastWarn(title, opts = {}) {
  return toast({ tone: "warn", title, ...opts });
}

/** 错误通知：默认常驻（0 = 不自动消失），由用户自己关掉 */
export function toastError(title, opts = {}) {
  return toast({ tone: "danger", title, timeout: 0, ...opts });
}

/** 失败通知 + 重试按钮（「是否可重试」的可见表达） */
export function toastRetry(title, { message, onRetry, retryLabel = "重试", onClose } = {}) {
  let handle = null;
  const actions = onRetry
    ? h(
        "div.row",
        { style: { gap: "var(--sp-3)", justifyContent: "flex-end", width: "100%" } },
        button({
          label: retryLabel,
          variant: "primary",
          size: "sm",
          icon: "refresh",
          onClick: () => {
            if (handle) handle.dismiss();
            onRetry();
          },
        }),
      )
    : null;
  handle = toastError(title, { message, actions, onClose });
  return handle;
}

/**
 * 供页面用的「结果播报」：把成功/失败同时落到 toast 与（可选的）内联状态区。
 * 这里只做通知；内联区由 feedback.js 的 feedbackRegion 负责。
 */
export function announce({ tone = "success", title, message, timeout, onClose } = {}) {
  return toast({ tone, title, message, timeout, onClose });
}

/** 测试/清理用：清空层里的残留节点 */
export function resetToastLayer() {
  clearToasts();
  const host = document.getElementById("toast-root");
  if (host) clear(host);
}
