/**
 * layout.js — 应用外壳（状态条 / 左导航 / 面包屑 / 页面容器 / 抽屉）
 * 与 layout.css 的结构一一对应；index.html 里是同一套静态标记。
 */

import { h, cx } from "./dom.js";
import { icon } from "./icons.js";
import { iconButton, statusDot } from "./primitives.js";

/** 导航项（顺序与 DESIGN.md §2 一致） */
export const NAV_ITEMS = [
  { id: "workbench", label: "工作台", icon: "dashboard", href: "#/workbench" },
  { id: "warehouse", label: "经历库", icon: "warehouse", href: "#/warehouse" },
  { id: "templates", label: "模板", icon: "template", href: "#/templates" },
  { id: "jobs", label: "目标职位", icon: "target", href: "#/jobs" },
  { id: "builds", label: "组装导出", icon: "layers", href: "#/builds" },
  { id: "profile", label: "个人资料", icon: "user", href: "#/profile" },
  { id: "settings", label: "设置", icon: "settings", href: "#/settings" },
];

/**
 * 顶层状态条：本地地址 / AI / 字体 / 最近导出。
 * 每个状态都是「点 + 文案」，且都带 title 说明（颜色不是唯一信息载体）。
 * @param {{
 *  localUrl?:string,
 *  ai?:{level:"ok"|"warn"|"bad"|"idle", label:string, title?:string, onClick?:Function},
 *  font?:{level:"ok"|"warn"|"bad"|"idle", label:string, title?:string},
 *  lastExport?:string,
 *  onThemeToggle?:Function,
 *  theme?: "auto"|"light"|"dark"
 * }} p
 */
export function statusBar(p = {}) {
  const ai = p.ai || { level: "idle", label: "AI 未检查" };
  const font = p.font || { level: "idle", label: "字体未检查" };

  const aiNode = ai.onClick
    ? h(
        "button",
        {
          class: "status-item status-item--btn",
          type: "button",
          title: ai.title || "查看 AI 配置",
          onClick: ai.onClick,
        },
        h("i", { class: `status-dot status-dot--${ai.level}` }),
        ai.label,
      )
    : h("span", { class: "status-item", title: ai.title }, h("i", { class: `status-dot status-dot--${ai.level}` }), ai.label);

  const themeLabel = p.theme === "dark" ? "深色" : p.theme === "light" ? "浅色" : "跟随系统";

  return h(
    "header",
    { class: "app__statusbar", role: "status" },
    h(
      "span",
      { class: "status-item", title: "本地运行：数据与文件都保存在这台机器上" },
      h("i", { class: "status-dot status-dot--ok" }),
      // 端口由启动脚本决定：前端只显示当前同源地址（location.host），不写死端口
      h("span", { class: "status-local" }, p.localUrl || (typeof location !== "undefined" ? location.host : "本地服务")),
      h("span", { class: "small" }, "本地"),
    ),
    h("i", { class: "status-sep", "aria-hidden": "true" }),
    h("span", { class: "status-item", title: "AI 仅在你确认后联网，发送字段逐项可见" }, aiNode),
    h("i", { class: "status-sep", "aria-hidden": "true" }),
    h("span", { class: "status-item", title: font.title || "中文 PDF 字体检测结果" }, h("i", { class: `status-dot status-dot--${font.level}` }), font.label),
    h(
      "span",
      { class: "app__statusbar__right" },
      p.lastExport
        ? h("span", { class: "status-item", title: "最近一次导出" }, "最近导出 ", h("span", { class: "mono small" }, p.lastExport))
        : null,
      p.onThemeToggle
        ? iconButton({
            icon: "eye",
            label: `切换主题（当前：${themeLabel}）`,
            size: "sm",
            onClick: p.onThemeToggle,
          })
        : null,
    ),
  );
}

/**
 * 左侧导航
 * @param {{items?:Array, active?:string, collapsed?:boolean,
 *          onToggle?:Function, onNavigate?:(id:string)=>void, counts?:Record<string,number>}} p
 */
export function sideNav(p = {}) {
  const items = p.items || NAV_ITEMS;
  const counts = p.counts || {};

  return h(
    "nav",
    { class: cx("sidenav", p.collapsed ? "sidenav--collapsed" : ""), "aria-label": "主导航" },
    h(
      "div",
      { class: "sidenav__brand" },
      h("span", { class: "sidenav__brand-mark", "aria-hidden": "true" }, "RW"),
      h(
        "span",
        { class: "sidenav__brand-text" },
        h("span", { class: "sidenav__brand-name" }, "简历仓库"),
        h("span", { class: "sidenav__brand-sub" }, "本地 · 离线优先"),
      ),
    ),
    h("div", { class: "sidenav__list" }, [
      h("div", { class: "sidenav__group-label" }, "工作"),
      items.slice(0, 5).map((it) => navItem(it, p.active, counts[it.id], p.onNavigate)),
      h("div", { class: "sidenav__group-label" }, "本地数据"),
      items.slice(5).map((it) => navItem(it, p.active, counts[it.id], p.onNavigate)),
    ]),
    h(
      "div",
      { class: "sidenav__footer" },
      p.onToggle
        ? h(
            "button",
            {
              class: "sidenav__collapse",
              type: "button",
              title: p.collapsed ? "展开导航" : "收起导航",
              "aria-expanded": p.collapsed ? "false" : "true",
              onClick: p.onToggle,
            },
            icon(p.collapsed ? "chevron-right" : "chevron-up", { size: 14 }),
            h("span", { class: "sidenav__label" }, p.collapsed ? "展开" : "收起"),
          )
        : null,
    ),
  );
}

function navItem(it, active, count, onNavigate) {
  const isActive = it.id === active;
  return h(
    "a",
    {
      class: cx("sidenav__item", isActive ? "is-active" : ""),
      href: it.href || `#/${it.id}`,
      "aria-current": isActive ? "page" : null,
      title: it.label,
      onClick: onNavigate
        ? (ev) => {
            ev.preventDefault();
            onNavigate(it.id);
          }
        : null,
    },
    icon(it.icon, { size: 16, cls: "sidenav__icon" }),
    h("span", { class: "sidenav__label" }, it.label),
    count !== undefined && count !== null ? h("span", { class: "sidenav__count" }, String(count)) : null,
  );
}

/**
 * 页面工具条（面包屑 + 右侧动作）
 * @param {{crumbs?:Array<{label:string, href?:string, current?:boolean}>, actions?:Node[]}} p
 */
export function topBar(p = {}) {
  const crumbs = p.crumbs || [];
  return h(
    "div",
    { class: "topbar" },
    h(
      "nav",
      { class: "topbar__crumbs", "aria-label": "面包屑" },
      crumbs.map((c, i) => [
        i > 0 ? h("span", { "aria-hidden": "true" }, "/") : null,
        h(
          c.current || !c.href ? "span" : "a",
          {
            class: cx("topbar__crumb", c.current ? "is-current" : ""),
            href: c.href,
            "aria-current": c.current ? "page" : null,
          },
          c.label,
        ),
      ]),
    ),
    p.actions ? h("div", { class: "topbar__right" }, p.actions) : null,
  );
}

/**
 * 页面容器：标题 / 说明 / 动作 / 主体
 * @param {{title:string, desc?:string, actions?:Node[], body?:Node|Node[],
 *          wide?:boolean, narrow?:boolean, badges?:Node[]}} p
 */
export function page(p = {}) {
  return h(
    "div",
    { class: cx("page", p.wide ? "page--wide" : "", p.narrow ? "page--narrow" : "") },
    p.title
      ? h(
          "div",
          { class: "page__head" },
          h(
            "div",
            { class: "page__head-text" },
            h("h1", { class: "page__title" }, p.title, p.badges || null),
            p.desc ? h("p", { class: "page__desc" }, p.desc) : null,
          ),
          p.actions ? h("div", { class: "page__actions" }, p.actions) : null,
        )
      : null,
    p.body,
  );
}

/**
 * 整体外壳：状态条 + 导航 + 主区
 * @param {{statusbar?:Node, nav?:Node, topbar?:Node, content?:Node}} p
 */
export function appShell(p = {}) {
  return h(
    "div",
    { class: "app" },
    p.statusbar,
    h("div", { class: "app__body" }, p.nav, h("div", { class: "main" }, p.topbar, h("div", { class: "main__scroll" }, p.content))),
  );
}

/**
 * 右侧抽屉（Package 详情 / JD 详情复用）
 * @param {{title:string, body:Node, footer?:Node, onClose?:Function, meta?:Node[], wide?:boolean}} p
 */
export function drawer(p = {}) {
  return h(
    "div",
    { class: "drawer-layer" },
    h("div", { class: "drawer-layer__scrim", onClick: p.onClose, "aria-hidden": "true" }),
    h(
      "aside",
      { class: "drawer", role: "dialog", "aria-modal": "false", "aria-label": p.title },
      h(
        "div",
        { class: "drawer__head" },
        h("h2", { class: "drawer__title" }, p.title),
        p.meta ? h("div", { class: "badge-row" }, p.meta) : null,
        iconButton({ icon: "x", label: "关闭详情", size: "sm", onClick: p.onClose }),
      ),
      h("div", { class: "drawer__body" }, p.body),
      p.footer ? h("div", { class: "drawer__foot" }, p.footer) : null,
    ),
  );
}
