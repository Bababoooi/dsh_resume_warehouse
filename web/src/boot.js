/**
 * 应用启动脚本（外部文件）。
 *
 * 为什么必须放在外部文件：`GET /` 的 CSP 是 `script-src 'self'`，内联
 * `<script type="module">` 会被浏览器直接拦掉（Log: Executing inline script violates
 * CSP）——后果不是报错，而是「整站只剩静态外壳与骨架」，所有路由全白。
 * 不要为了省事把这段搬回 index.html，也不要给 CSP 加 unsafe-inline。
 */

import { statusBar, sideNav, topBar, page } from "./components/layout.js";
import { h, replace } from "./components/dom.js";
import { callout, button } from "./components/primitives.js";
import { icon } from "./components/icons.js";
import { toast } from "./components/toast.js";

const ROUTES = {
  workbench: { label: "工作台", crumb: "对话式录入工作台", desc: "把一段经历讲清楚，剩下的交给仓库" },
  warehouse: { label: "经历库", crumb: "Package 仓库", desc: "所有可复用的经历与表述变体" },
  templates: { label: "模板", crumb: "简历导入与模板拆解", desc: "导入现有简历，拆成可重组的槽位" },
  jobs: { label: "目标职位", crumb: "JD 与公司分析", desc: "看清岗位要什么，再决定写什么" },
  builds: { label: "组装导出", crumb: "组装与导出预览", desc: "选经历、选语言、导出 PDF" },
  profile: { label: "个人资料", crumb: "个人资料与设置", desc: "姓名、学校与照片的唯一来源" },
  settings: { label: "设置", crumb: "设置", desc: "模型、隐私与本地路径" },
};

/* ---------------- 主题 ---------------- */
const THEME_KEY = "rw-theme";
const AI_LABELS = { ok: "DeepSeek 已就绪", warn: "模型未配置", bad: "调用失败", idle: "AI 未检查", checking: "正在检查 AI…" };
const FONT_LABELS = { ok: "中文字体可用", warn: "字体待确认", bad: "缺中文字体", idle: "字体未检查", checking: "正在检查字体…" };

const states = () => {
  const s = { ai: "idle", font: "idle", lastExport: null, url: null };
  try {
    const cached = localStorage.getItem("rw-status");
    if (cached) Object.assign(s, JSON.parse(cached));
  } catch (_) {}
  return s;
};

let appStatus = states();
let navCollapsed = false;

function applyTheme(mode) {
  const root = document.documentElement;
  if (!mode || mode === "auto") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", mode);
  try {
    localStorage.setItem(THEME_KEY, mode || "auto");
  } catch (_) {}
}

function currentTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || "auto";
  } catch (_) {
    return "auto";
  }
}

const storedTheme = currentTheme();
applyTheme(storedTheme);

/* ---------------- 引擎 ---------------- */
let activeRoute = (location.hash.replace(/^#\/?/, "") || "workbench").split("/")[0];
if (!ROUTES[activeRoute]) activeRoute = "workbench";

function renderChrome() {
  replace(
    document.getElementById("statusbar"),
    statusBar({
      localUrl: appStatus.url || (typeof location !== "undefined" ? location.host : "本地服务"),
      ai: {
        level: appStatus.ai,
        label: AI_LABELS[appStatus.ai] || "AI 状态未知",
        title: "AI 仅在你确认后联网，发送字段逐项可见",
        onClick: () => navigate("settings"),
        onRetry: () => probeStatus({ retry: true }),
      },
      font: {
        level: appStatus.font,
        label: FONT_LABELS[appStatus.font] || "字体状态未知",
        onRetry: () => probeStatus({ retry: true }),
      },
      lastExport: appStatus.lastExport,
      theme: currentTheme(),
      onThemeToggle: () => {
        const next = currentTheme() === "dark" ? "light" : "dark";
        applyTheme(next);
        renderChrome();
      },
    }),
  );

  replace(
    document.getElementById("sidenav"),
    sideNav({
      active: activeRoute,
      collapsed: navCollapsed,
      onNavigate: (key) => navigate(key),
      onToggle: () => {
        navCollapsed = !navCollapsed;
        renderChrome();
      },
      counts: { warehouse: appStatus.packages, templates: appStatus.templates, jobs: appStatus.jobs },
    }),
  );

  replace(
    document.getElementById("topbar"),
    topBar({
      crumbs: [
        { label: "简历仓库", href: "#/workbench" },
        { label: ROUTES[activeRoute].crumb, current: true },
      ],
      actions: [
        button({
          label: "搜索",
          icon: "search",
          size: "sm",
          variant: "quiet",
          kbd: "⌘K",
          onClick: () => document.dispatchEvent(new CustomEvent("rw:search")),
        }),
        button({
          label: "设计预览",
          icon: "eye",
          size: "sm",
          variant: "ghost",
          onClick: () => window.open("./preview.html", "_blank", "noopener"),
        }),
      ],
    }),
  );
}

/* ---------------- 页面装载 ----------------
   页面层（web/src/pages/**）由另一条 lane 实装。存在即挂载；
   不存在时给出诚实的占位，而不是白屏。 */
async function mountPage(key) {
  const host = document.getElementById("view");
  try {
    const mod = await import(`./pages/${key}.js`);
    const factory = mod.render || mod.default;
    if (typeof factory === "function") {
      replace(host, factory());
      return;
    }
    throw new Error("页面模块没有导出 render()");
  } catch (err) {
    replace(
      host,
      page({
        title: ROUTES[key].crumb,
        desc: ROUTES[key].desc,
        body: h(
          "div",
          { class: "stack", style: { gap: "var(--sp-6)" } },
          callout({
            tone: "info",
            icon: "info",
            title: "界面框架已就绪，页面内容尚未接入",
            body: h(
              "span",
              null,
              "导航、状态条、组件库与设计 token 都已生效；这一屏的具体内容由页面层（web/src/pages/",
              key,
              ".js）挂载。想看完整界面效果，请打开设计预览页。",
            ),
          }),
          h(
            "div",
            { class: "row", style: { gap: "var(--sp-4)" } },
            button({
              label: "打开设计预览（6 屏 + 弹层 + A4 样张）",
              variant: "primary",
              icon: "eye",
              onClick: () => window.open("./preview.html", "_blank", "noopener"),
            }),
          ),
          h(
            "p",
            { class: "small muted mono" },
            String(err && err.message ? err.message : err),
          ),
        ),
      }),
    );
  }
}

function navigate(key) {
  if (!ROUTES[key]) key = "workbench";
  activeRoute = key;
  if (location.hash !== `#/${key}`) history.replaceState(null, "", `#/${key}`);
  renderChrome();
  mountPage(key);
  document.getElementById("view").focus({ preventScroll: true });
  document.dispatchEvent(new CustomEvent("rw:navigate", { detail: { route: key } }));
}

window.addEventListener("hashchange", () => {
  const key = (location.hash.replace(/^#\/?/, "") || "workbench").split("/")[0];
  if (key !== activeRoute) navigate(key);
});

/* ---------------- 全局快捷键 ---------------- */
document.addEventListener("keydown", (ev) => {
  // 中文输入法组字期间的按键不是命令（Enter/⌘S 都不该触发提交）
  if (ev.isComposing || ev.keyCode === 229) return;
  const meta = ev.metaKey || ev.ctrlKey;
  if (meta && ev.key.toLowerCase() === "k") {
    ev.preventDefault();
    document.dispatchEvent(new CustomEvent("rw:search"));
  } else if (meta && ev.key.toLowerCase() === "s") {
    ev.preventDefault();
    document.dispatchEvent(new CustomEvent("rw:save"));
  }
});

/* ---------------- 状态条更新入口 ----------------
   页面层通过 window.dispatchEvent(new CustomEvent("rw:status", {detail:{ai:"warn"}})) 更新。 */
window.addEventListener("rw:status", (ev) => {
  appStatus = Object.assign({}, appStatus, ev.detail || {});
  try {
    localStorage.setItem("rw-status", JSON.stringify(appStatus));
  } catch (_) {}
  renderChrome();
});

renderChrome();

/* 启动即探一次真实状态：状态条此前永远停在 idle，因为没有任何地方派发 rw:status。
   两个端点都是本机自检（不发任何用户数据），失败也只影响一颗指示灯。
   retry=true 用于用户点击状态条上的刷新：先置 checking 给即时反馈，失败再补一条可重试的提示。 */
async function probeStatus({ retry = false } = {}) {
  if (retry) {
    window.dispatchEvent(new CustomEvent("rw:status", { detail: { ai: "checking", font: "checking" } }));
  }
  const out = {};

  // 本地服务可能在启动/重启：4 秒还没回就当失败，不然状态条会一直停在「未检查」
  const signal = (() => {
    try {
      return typeof AbortSignal !== "undefined" && AbortSignal.timeout ? AbortSignal.timeout(4000) : undefined;
    } catch {
      return undefined;
    }
  })();

  try {
    const resp = await fetch("/api/v1/llm/status", signal ? { signal } : undefined);
    const body = await resp.json();
    const data = (body && body.data) || {};
    if (data.ready === true) out.ai = "ok";
    else if (data.key_set === false || data.configured === false) out.ai = "warn";
    else out.ai = "bad";
  } catch (_) {
    out.ai = "bad";
  }
  try {
    const resp = await fetch("/api/v1/env", signal ? { signal } : undefined);
    const body = await resp.json();
    const fonts = (body && body.data && body.data.fonts) || {};
    const name = (fonts.primary && (fonts.primary.name || fonts.primary)) || "";
    if (fonts.ok === true && /^STSongti|Songti/i.test(String(name))) out.font = "ok";
    else if (fonts.ok === true) out.font = "warn";
    else out.font = "bad";
  } catch (_) {
    out.font = "bad";
  }

  window.dispatchEvent(new CustomEvent("rw:status", { detail: out }));

  if (retry && out.ai === "bad" && out.font === "bad") {
    toast({
      tone: "warn",
      title: "还是连不上本地服务",
      message: "两个自检端点都没响应。如果刚重启过，等两秒再点状态条上的刷新。",
      timeout: 6000,
    });
  } else if (retry && (out.ai === "bad" || out.font === "bad")) {
    const failing = [out.ai === "bad" ? "AI 状态" : "", out.font === "bad" ? "中文字体" : ""].filter(Boolean).join("、");
    toast({
      tone: "warn",
      title: `${failing}检查未通过`,
      message: out.ai === "bad" ? "看看设置页里的服务商与模型；只想用本地能力可以先不管。" : "导出 PDF 会失败：装宋体或改用渲染引擎。",
      timeout: 6000,
    });
  }
  return out;
}
probeStatus();

/* ---------------- 兜底：任何页面崩溃都必须看得见 ----------------
   页面在 queueMicrotask / await 里抛的异常，以前会静默留白（外壳还在、正文空），
   比报错更难排查。这里统一转成可见的错误条，并带上错误码。 */
function showFatal(kind, err) {
  const view = document.getElementById("view");
  if (!view) return;
  const raw = (err && (err.stack || err.message)) || String(err || "未知错误");
  const code = (err && err.code) || "PAGE_ERROR";
  view.prepend(
    callout({
      tone: "danger",
      title: `这一页出错了（${kind}）`,
      body: h("span", null, `错误码 ${code}：${String(raw).split("\n")[0]}`),
    }),
  );
}

window.addEventListener("error", (ev) => showFatal("脚本错误", ev.error || ev.message));
window.addEventListener("unhandledrejection", (ev) => showFatal("未捕获的异步异常", ev.reason));

mountPage(activeRoute);

// 暴露给页面层的极小工具（不作为业务 API）
window.__rw = {
  navigate,
  refreshStatus: () => renderChrome(),
  probeStatus: () => probeStatus({ retry: true }),
  icon,
};
    
