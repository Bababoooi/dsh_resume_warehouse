/**
 * progress.js — 长任务（导出 / 分析）的进度视图与断点续poll
 *
 * 为什么在 components/ 里：任务条和「加载中…」一样是展示层的一块；
 * 但它是本目录里**唯一**允许触达 api 层与 sessionStorage 的模块，
 * 因为「切页再回来还能接着看进度」必须由它记住 job_id。其余组件保持纯展示。
 *
 * 后端契约（server/app/api/jobs.py::_view）：
 *   {id, kind, status, progress(0-100), message, result_json, error_json, created_at, finished_at}
 *   status ∈ queued / running / succeeded / failed / interrupted / cancelled
 * 后端没有取消接口，所以这里不提供「取消」按钮（不画不能点的东西）。
 */

import { h } from "./dom.js";
import { elapsedText } from "./feedback.js";
import { api, waitJob } from "../api.js";

/** 记住哪些 scope 有在跑的任务 */
const STORE_KEY = "rw-active-jobs";

/** 服务端任务终结态（workflow/jobs.py） */
const TERMINAL = ["succeeded", "failed", "interrupted", "cancelled"];

export const JOB_KIND_LABEL = {
  build_export: "PDF 导出",
  jd_analyze: "岗位分析",
  company_analyze: "公司偏好分析",
  bullets_generate: "Bullet 生成",
};

const JOB_STATUS_LABEL = {
  queued: "排队等待开始",
  running: "正在处理",
  succeeded: "已完成",
  failed: "失败",
  interrupted: "被中断",
  cancelled: "已取消",
};

function storage() {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function readAll() {
  const ss = storage();
  if (!ss) return {};
  try {
    const raw = ss.getItem(STORE_KEY);
    const data = raw ? JSON.parse(raw) : {};
    return data && typeof data === "object" ? data : {};
  } catch {
    return {};
  }
}

function writeAll(data) {
  const ss = storage();
  if (!ss) return;
  try {
    ss.setItem(STORE_KEY, JSON.stringify(data));
  } catch {
    /* 存不下就算了：进度会丢，但页面功能不受影响 */
  }
}

/** 记下一个还在跑的 job（scope 例："builds:export"、"jobs:analyze:<jdId>"） */
/** 同上：.ui-spinner 自带 author 级 display，hidden 属性压不住它 */
function setShown(node, shown) {
  if (!node) return;
  node.hidden = !shown;
  node.style.display = shown ? "" : "none";
}

export function rememberJob(scope, rec = {}) {
  if (!scope || !rec.jobId) return;
  const all = readAll();
  all[scope] = {
    jobId: String(rec.jobId),
    kind: rec.kind || "",
    label: rec.label || "",
    startedAt: Number(rec.startedAt) || Date.now(),
  };
  writeAll(all);
}

/** 取出 scope 上记住的 job（没有就 null） */
export function recallJob(scope) {
  if (!scope) return null;
  const rec = readAll()[scope];
  if (!rec || !rec.jobId) return null;
  return rec;
}

/** 任务收尾后清掉，避免下次进页面误报「还在跑」 */
export function forgetJob(scope) {
  if (!scope) return null;
  const all = readAll();
  const rec = all[scope] || null;
  if (rec) {
    delete all[scope];
    writeAll(all);
  }
  return rec;
}

/** 当前记住的所有任务（设置页/任务页做「还在跑」提示时可用） */
export function listRememberedJobs() {
  return Object.entries(readAll()).map(([scope, rec]) => ({ scope, ...rec }));
}

function stageTextFor(kind, status, message) {
  const kindLabel = JOB_KIND_LABEL[kind] || "任务";
  if (message && String(message).trim()) {
    // 后端在关键节点会报具体阶段（「组装内容」「等待模型返回公司画像」），优先用它
    return `${kindLabel}：${message}`;
  }
  return `${kindLabel}：${JOB_STATUS_LABEL[status] || "处理中"}`;
}

/**
 * 进度视图。
 *
 * @param {object} p
 * @param {string} [p.kind] job kind（决定「PDF 导出 / 岗位分析」这类文案）
 * @param {string} [p.label] 覆盖显示名
 * @param {boolean} [p.showHint=true] 是否显示「切页也能接上」的说明
 * @returns {{node:HTMLElement, update:Function, done:Function, fail:Function, reset:Function, setText:Function}}
 */
export function jobProgress(p = {}) {
  const kindLabel = p.label || JOB_KIND_LABEL[p.kind] || "任务";
  const startedAt = { value: Number(p.startedAt) || Date.now() };
  let lastStage = "";

  const spinnerNode = h("span", { class: "ui-spinner", "aria-hidden": "true" });
  const stageNode = h("span", {
    "aria-live": "polite",
    "aria-atomic": "true",
    style: { fontSize: "var(--fs-12)", color: "var(--c-text)" },
  }, `${kindLabel}：准备中…`);
  const elapsedNode = h("span", {
    class: "small muted",
    style: { marginLeft: "auto", fontVariantNumeric: "tabular-nums" },
  }, "已用时 <1s");

  const barNode = h("div", {
    class: "ui-progress__bar ui-progress__bar--indeterminate",
    style: null,
  });
  const track = h(
    "div.ui-progress__track",
    { role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-label": `${kindLabel}进度` },
    barNode,
  );

  const hintNode = p.showHint === false
    ? null
    : h("div.small.muted", null, "任务在服务端继续跑，切到别的页面再回来会自动接上。");

  const node = h(
    "div",
    {
      class: "stack",
      style: { gap: "var(--sp-3)" },
      role: "group",
      "aria-label": `${kindLabel}进度`,
      // data-state / aria-busy 必须从第一帧就存在：验收是在「进度面板出现」时读的，
      // 等到 update() 才写会读到 undefined。
      dataset: { role: "job-progress", kind: p.kind || "", state: "running" },
      "aria-busy": "true",
    },
    h("div.row", { style: { gap: "var(--sp-3)", alignItems: "center" } }, spinnerNode, stageNode, elapsedNode),
    h("div.ui-progress", null, track),
    hintNode,
  );

  function setText(text) {
    if (text === lastStage) return; // 同文案重复写入会让读屏反复播报
    lastStage = text;
    stageNode.textContent = text;
  }

  function paintProgress(value) {
    const indeterminate = value === null || value === undefined || Number.isNaN(Number(value));
    barNode.classList.toggle("ui-progress__bar--indeterminate", indeterminate);
    if (indeterminate) {
      barNode.style.width = "";
      track.removeAttribute("aria-valuenow");
    } else {
      const v = Math.max(0, Math.min(100, Math.round(Number(value))));
      barNode.style.width = `${v}%`;
      track.setAttribute("aria-valuenow", String(v));
    }
  }

  function update(job, elapsedMs) {
    if (!job) return node;
    elapsedNode.textContent = elapsedText(startedAt.value, Date.now());
    setText(stageTextFor(p.kind, job.status, job.message));
    if (job.status === "succeeded") paintProgress(100);
    else paintProgress(job.progress);
    return node;
  }

  function done(job) {
    setShown(spinnerNode, false);
    paintProgress(100);
    setText(`${kindLabel}：${job && job.status === "failed" ? "已结束（失败）" : "已完成"}`);
    elapsedNode.textContent = elapsedText(startedAt.value, Date.now());
    if (hintNode) hintNode.textContent = "可以关闭这条进度了。";
    node.dataset.state = "done";
    node.setAttribute("aria-busy", "false");
    return node;
  }

  function fail(err) {
    setShown(spinnerNode, false);
    paintProgress(0);
    setText(`${kindLabel}：中断了`);
    if (hintNode) hintNode.textContent = (err && err.message) || "服务端返回失败，详情见下方。";
    node.dataset.state = "failed";
    node.setAttribute("aria-busy", "false");
    return node;
  }

  function reset(startedAtMs) {
    startedAt.value = Number(startedAtMs) || Date.now();
    setShown(spinnerNode, true);
    setText(`${kindLabel}：准备中…`);
    paintProgress(null);
    node.dataset.state = "running";
    node.setAttribute("aria-busy", "true");
    elapsedNode.textContent = "已用时 <1s";
    return node;
  }

  return { node, update, done, fail, reset, setText };
}

/**
 * 起一轮轮询（带断点记忆）。
 *
 * 与 waitJob 的分工：waitJob 只负责「问后端要状态」，这里负责
 * 「记住 job_id / 页面走了就别再改 DOM / 结束后清掉记忆」。
 *
 * @param {object} p
 * @param {string} p.jobId
 * @param {string} [p.scope] sessionStorage 的键（同一动作固定一个）
 * @param {string} [p.kind]
 * @param {string} [p.label]
 * @param {number} [p.startedAt]
 * @param {number} [p.timeout]
 * @param {Function} [p.onUpdate] (job, meta) 每次拿到状态
 * @param {Function} [p.onDone] (job)
 * @param {Function} [p.onError] (err)
 * @param {Function} [p.alive] () => boolean；返回 false 时停止轮询（页面已卸载）
 * @returns {{promise:Promise<object>, jobId:string, stop:Function}}
 */
export function trackJob(p = {}) {
  const startedAt = Number(p.startedAt) || Date.now();
  if (p.scope && p.jobId) {
    rememberJob(p.scope, { jobId: p.jobId, kind: p.kind, label: p.label, startedAt });
  }

  let stopped = false;
  const alive = typeof p.alive === "function" ? p.alive : () => true;

  const promise = waitJob(p.jobId, {
    timeout: p.timeout,
    onTick: (job, meta) => {
      if (stopped || !alive()) return;
      if (typeof p.onUpdate === "function") p.onUpdate(job, meta, startedAt);
    },
    shouldStop: () => stopped || !alive(),
  })
    .then((job) => {
      // 只有任务真的终结了才清除 sessionStorage 记录。
      // 页面被切走时 waitJob 会因为 shouldStop() 提前返回当前 job —— 那种情况下
      // 任务还在服务端跑，必须把 job_id 留着，用户切回来才能续上轮询。
      const finished = job && TERMINAL.includes(job.status);
      if (!finished) return job;
      if (p.scope) forgetJob(p.scope);
      if (!stopped && alive() && typeof p.onDone === "function") p.onDone(job);
      return job;
    })
    .catch((err) => {
      // 网络抖动 / 轮询超时：任务可能还在服务端，保留记录以便下次进来续上；
      // 4xx 之类的确定性失败则清掉，免得每次进页面都白轮询一次。
      const transient =
        !err || err.code === "NETWORK" || err.code === "JOB_TIMEOUT" || Number(err.status) >= 500;
      if (p.scope && !transient) forgetJob(p.scope);
      if (!stopped && alive() && typeof p.onError === "function") p.onError(err);
      throw err;
    });

  // 页面忘记 catch 时不要让全局 unhandledrejection 把整页换成错误页
  promise.catch(() => {});

  return {
    promise,
    jobId: p.jobId,
    stop() {
      stopped = true;
    },
  };
}

/**
 * 进页面时恢复上次没跑完的任务。
 *
 * @param {string} scope
 * @param {object} handlers {onTick, onDone, onError, alive, timeout}
 * @returns {null|{jobId, kind, label, startedAt, promise, stop}}
 */
export function resumeJob(scope, handlers = {}) {
  const rec = recallJob(scope);
  if (!rec) return null;
  const ctl = trackJob({
    scope,
    jobId: rec.jobId,
    kind: rec.kind,
    label: rec.label,
    startedAt: rec.startedAt,
    timeout: handlers.timeout,
    onUpdate: handlers.onTick,
    onDone: handlers.onDone,
    onError: handlers.onError,
    alive: handlers.alive,
  });
  return { ...rec, promise: ctl.promise, stop: ctl.stop };
}

/** 清掉一个 scope 的记忆（成功/失败收尾时用，或用户主动放弃） */
export function dropJob(scope) {
  return forgetJob(scope);
}

/** 直接查一次 job 状态（恢复时先确认它还没结束，避免白画一个进度条） */
export async function peekJob(jobId) {
  if (!jobId) return null;
  try {
    return await api.job(jobId);
  } catch {
    return null;
  }
}
