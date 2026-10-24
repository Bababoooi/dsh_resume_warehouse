/**
 * dom.js — 极简 DOM 构建工具（纯展示层的地基）
 *
 * 设计约束（对应 ACCEPTANCE AC-UI-04）：
 *  - 任何用户内容只能以 Text 节点进入 DOM：h() 只接受字符串/数字/Node，
 *    不接受 HTML 字符串，也**不支持** innerHTML / dangerouslySetInnerHTML。
 *  - 组件不发起请求、不读写 localStorage、不 import api 层。
 *  - 零依赖、零构建，直接由浏览器以 ES module 加载。
 */

const SVG_NS = "http://www.w3.org/2000/svg";

/** 禁止通过属性注入 HTML 的键（防御性：即使调用方误传也直接抛错） */
const FORBIDDEN_PROPS = new Set(["innerHTML", "outerHTML", "srcdoc", "html"]);

const BOOLEAN_ATTRS = new Set([
  "disabled",
  "checked",
  "readonly",
  "required",
  "multiple",
  "hidden",
  "open",
  "selected",
  "novalidate",
]);

/**
 * 创建元素。
 * @param {string} tag 标签名，可带类名简写："div.ui-card.is-active"
 * @param {object|null} props 属性；`on*` 绑定事件；`style` 可传对象；
 *                            `dataset` 传对象；其余按 attribute 处理
 * @param {...(Node|string|number|null|undefined|false|Array)} children
 * @returns {HTMLElement}
 */
export function h(tag, props, ...children) {
  const [name, ...classList] = String(tag).split(".");
  const node = document.createElement(name || "div");
  if (classList.length) node.className = classList.join(" ");

  if (props && typeof props === "object") {
    for (const [key, value] of Object.entries(props)) {
      if (value === null || value === undefined || value === false) continue;
      if (FORBIDDEN_PROPS.has(key)) {
        throw new Error(`dom.h: 禁止使用 ${key}（用户内容必须走 Text 节点）`);
      }
      if (key === "class" || key === "className") {
        node.className = [node.className, value].filter(Boolean).join(" ");
        continue;
      }
      if (key === "style" && typeof value === "object") {
        Object.assign(node.style, value);
        continue;
      }
      if (key === "dataset" && typeof value === "object") {
        for (const [dk, dv] of Object.entries(value)) {
          if (dv === null || dv === undefined) continue;
          node.dataset[dk] = String(dv);
        }
        continue;
      }
      if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2).toLowerCase(), value);
        continue;
      }
      if (key === "ref" && typeof value === "function") {
        value(node);
        continue;
      }
      if (BOOLEAN_ATTRS.has(key)) {
        node[key] = Boolean(value);
        if (!value) node.removeAttribute(key);
        else node.setAttribute(key, "");
        continue;
      }
      if (key === "value") {
        node.value = value;
        continue;
      }
      if (key === "text") {
        node.textContent = String(value);
        continue;
      }
      node.setAttribute(key, value === true ? "" : String(value));
    }
  }

  append(node, children);
  return node;
}

/** 批量追加子节点；递归展开数组，忽略 null/undefined/false */
export function append(parent, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false || child === true) {
      continue;
    }
    if (Array.isArray(child)) {
      append(parent, child);
      continue;
    }
    if (child instanceof Node) {
      parent.appendChild(child);
      continue;
    }
    parent.appendChild(document.createTextNode(String(child)));
  }
  return parent;
}

/** 文本片段（永不解释为 HTML） */
export function text(value) {
  return document.createTextNode(value === null || value === undefined ? "" : String(value));
}

/** 清空容器（比 innerHTML = "" 更明确，且不触发解析） */
export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

/** 用新内容替换容器内容（用于「加载态 → 数据态」切换） */
export function replace(node, ...children) {
  clear(node);
  append(node, children);
  return node;
}

/** 条件渲染：cond 为真时返回节点，否则返回 null（h() 会忽略） */
export function when(cond, factory) {
  return cond ? factory() : null;
}

/** 拼接类名，过滤假值 */
export function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}

/** 复数/计数文案：n 条 / 0 条 */
export function count(n, unit) {
  return `${Number(n) || 0} ${unit}`;
}

/**
 * SVG 图标容器（图标本身由 icons.js 提供路径数据）
 * @param {string} pathData 一条或多条 path 的 d 属性（用 "|" 分隔）
 */
export function svg(pathData, { size = 16, filled = false, strokeWidth = 1.6, cls = "" } = {}) {
  const el = document.createElementNS(SVG_NS, "svg");
  el.setAttribute("viewBox", "0 0 24 24");
  el.setAttribute("width", String(size));
  el.setAttribute("height", String(size));
  el.setAttribute("fill", filled ? "currentColor" : "none");
  el.setAttribute("stroke", filled ? "none" : "currentColor");
  el.setAttribute("stroke-width", String(strokeWidth));
  el.setAttribute("stroke-linecap", "round");
  el.setAttribute("stroke-linejoin", "round");
  el.setAttribute("aria-hidden", "true");
  el.setAttribute("focusable", "false");
  if (cls) el.setAttribute("class", cls);
  for (const d of String(pathData).split("|")) {
    if (!d.trim()) continue;
    const p = document.createElementNS(SVG_NS, "path");
    p.setAttribute("d", d.trim());
    el.appendChild(p);
  }
  return el;
}

/** 焦点可见性工具：把焦点移到容器内第一个可聚焦元素 */
export function focusFirst(container) {
  if (!container) return false;
  const target = container.querySelector(
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  );
  if (!target) return false;
  target.focus();
  return true;
}

/** 焦点陷阱（模态用）；返回解绑函数 */
export function trapFocus(container, { onEscape } = {}) {
  const selector =
    'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function onKeydown(event) {
    if (event.key === "Escape" && typeof onEscape === "function") {
      event.preventDefault();
      event.stopPropagation();
      onEscape();
      return;
    }
    if (event.key !== "Tab") return;
    const items = Array.from(container.querySelectorAll(selector)).filter(
      (node) => node.offsetParent !== null || node === document.activeElement,
    );
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  container.addEventListener("keydown", onKeydown);
  return () => container.removeEventListener("keydown", onKeydown);
}

/**
 * 让弹层/抽屉支持 Esc 关闭 —— 不依赖焦点是否落在弹层内部。
 *
 * 为什么需要：trapFocus 的 Esc 只在该容器内收到 keydown 时生效；用户点了别处、
 * 或焦点被移到容器外之后，Esc 就没反应了。这里在 document 上听，并且只关
 * 最上面一层（避免一次 Esc 关掉两层）。
 *
 * 与 trapFocus 共存：trapFocus 会 preventDefault + stopPropagation，所以它已经
 * 处理过的 Esc 不会再触发这里（事件到不了 document）。
 *
 * @param {HTMLElement} layer 弹层根节点（.modal-layer / .drawer-layer）
 * @param {Function} onClose 关闭回调
 * @returns {Function} 解绑函数
 */
export function escToClose(layer, onClose) {
  if (!layer || typeof onClose !== "function") return () => {};
  const stackSelector = ".modal-layer, .drawer-layer";

  function onKeydown(event) {
    if (!layer.isConnected) {
      document.removeEventListener("keydown", onKeydown);
      return;
    }
    if (event.key !== "Escape" || event.defaultPrevented) return;
    const stack = Array.from(document.querySelectorAll(stackSelector));
    if (stack.length && stack[stack.length - 1] !== layer) return;
    if (!stack.length) return;
    event.preventDefault();
    onClose();
  }

  document.addEventListener("keydown", onKeydown);
  return () => document.removeEventListener("keydown", onKeydown);
}
