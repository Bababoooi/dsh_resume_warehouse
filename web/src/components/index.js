/**
 * index.js — 展示组件统一出口
 *
 * 使用约定：
 *  - 全部组件是纯展示组件：只接收 props 与回调，不 fetch、不 import api 层、不读全局状态。
 *  - 用户内容只经 Text 节点写入（dom.js 禁止 innerHTML）。
 *  - 需要页面层做的事：调接口、持有 state、决定弹层开关。
 */

export * from "./dom.js";
export * from "./icons.js";
export * from "./primitives.js";
export * from "./layout.js";
export * from "./errors.js";
export * from "./package-card.js";
export * from "./import-review.js";
export * from "./jd-panel.js";
export * from "./build-parts.js";
export * from "./consent-modal.js";
export * from "./job-toast.js";
export * from "./profile-form.js";
