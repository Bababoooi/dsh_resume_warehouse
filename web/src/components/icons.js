/**
 * icons.js — 内联 SVG 图标（零外部资源，AC-UI-01）
 * 统一 24×24 viewBox、1.6 描边、currentColor，跟随文字颜色与深浅色。
 */

import { svg } from "./dom.js";

const PATHS = {
  // 导航
  dashboard: "M3 9.5 12 3l9 6.5V21a1 1 0 0 1-1 1h-5v-7H10v7H4a1 1 0 0 1-1-1z",
  warehouse: "M21 8v13H3V8|M1 3h22v5H1z|M10 12h4",
  template: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z|M14 2v6h6|M8 13h8|M8 17h5",
  target: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20|M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10|M12 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2",
  layers: "M12 2 2 7l10 5 10-5z|M2 12l10 5 10-5|M2 17l10 5 10-5",
  settings:
    "M4 21v-7|M4 10V3|M12 21v-9|M12 8V3|M20 21v-5|M20 12V3|M1 14h6|M9 8h6|M17 16h6",
  chat: "M21 11.5a8.4 8.4 0 0 1-9 8.4 8.6 8.6 0 0 1-3.8-.9L3 21l1.9-5.2a8.4 8.4 0 0 1 9-11A8.4 8.4 0 0 1 21 11.5z",
  folder: "M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z",

  // 动作
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z|M21 21l-4.35-4.35",
  plus: "M12 5v14|M5 12h14",
  minus: "M5 12h14",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4|M7 10l5 5 5-5|M12 15V3",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4|M17 8l-5-5-5 5|M12 3v12",
  check: "M20 6 9 17l-5-5",
  x: "M18 6 6 18|M6 6l12 12",
  trash: "M3 6h18|M8 6V4h8v2|M19 6l-1 14H6L5 6|M10 11v5|M14 11v5",
  edit: "M12 20h9|M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z",
  copy: "M9 9h10v12H9z|M5 15V3h10",
  refresh:
    "M23 4v6h-6|M1 20v-6h6|M3.5 9a9 9 0 0 1 14.9-3.4L23 10|M20.5 15A9 9 0 0 1 5.6 18.4L1 14",
  external: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6|M15 3h6v6|M10 14 21 3",
  eye: "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z|M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  menu: "M3 12h18|M3 6h18|M3 18h18",
  grip: "M9 6h.01|M9 12h.01|M9 18h.01|M15 6h.01|M15 12h.01|M15 18h.01",

  // 方向
  "chevron-left": "M15 18l-6-6 6-6",
  "chevron-right": "M9 18l6-6-6-6",
  "split": "M12 4v6M12 14v6M4 12h4M16 12h4M9 7l3 3 3-3M9 17l3-3 3 3",
  "merge": "M7 4v5a3 3 0 0 0 3 3h4a3 3 0 0 1 3 3v5M17 4v5a3 3 0 0 1-3 3h-4a3 3 0 0 0-3 3v5",
  "chevron-down": "M6 9l6 6 6-6",
  "chevron-up": "M18 15l-6-6-6 6",
  "arrow-up": "M12 19V5|M5 12l7-7 7 7",
  "arrow-down": "M12 5v14|M19 12l-7 7-7-7",
  "arrow-right": "M5 12h14|M13 5l7 7-7 7",

  // 状态
  "alert-triangle":
    "M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z|M12 9v4|M12 17h.01",
  "alert-circle": "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20|M12 8v4|M12 16h.01",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20|M12 16v-4|M12 8h.01",
  clock: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20|M12 6v6l4 2",
  "cloud-off":
    "M22.6 16.4A5 5 0 0 0 18 8h-1.3A8 8 0 0 0 3 12c0 1.4.4 2.7 1 3.8|M1 1l22 22",
  "check-circle": "M22 11.1V12a10 10 0 1 1-5.9-9.1|M22 4 12 14.01l-3-3",

  // 领域
  lock: "M5 11h14v11H5z|M8 11V7a4 4 0 1 1 8 0v4",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  sparkles:
    "M12 3l1.8 4.6 4.6 1.8-4.6 1.8L12 15.8 10.2 11.2 5.6 9.4l4.6-1.8z|M19 15l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z",
  user: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2|M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z|M14 2v6h6",
  globe: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20|M2 12h20|M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20",
  languages: "M5 8l6 6|M4 14l6-6 2-3|M2 5h12|M7 2h1|M22 22l-5-10-5 10|M14 18h6",
};

/** 图标名列表（供预览页/demo 遍历） */
export const ICON_NAMES = Object.keys(PATHS);

/**
 * 生成图标元素。
 * @param {string} name PATHS 中的键
 * @param {{size?:number, cls?:string, strokeWidth?:number, filled?:boolean}} [opts]
 */
export function icon(name, opts = {}) {
  const d = PATHS[name];
  if (!d) {
    // 未知图标不阻断渲染：返回一个占位方框，便于开发期发现拼写错误
    const fallback = svg("M4 4h16v16H4z", opts);
    fallback.dataset.iconMissing = name;
    return fallback;
  }
  const el = svg(d, opts);
  el.dataset.icon = name;
  return el;
}

export default icon;
