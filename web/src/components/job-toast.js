/**
 * job-toast.js — 后台任务提示（右下角）
 *
 * 行为：进度 / 已取消 / 失败（带错误码人话）/ 「服务重启后变为已中断」。
 * 不做请求，状态由页面层轮询后传入；可取消（可选）。
 */

import { h, cx } from "./dom.js";
import { icon } from "./icons.js";
import { button, progress } from "./primitives.js";
import { describeError, errorText } from "./errors.js";

export const JOB_KIND_LABELS = {
  export: "导出 PDF",
  assemble: "组装简历",
  import: "解析简历",
  jd_analyze: "分析 JD",
  llm_polish: "定制表述",
  llm_company: "公司偏好分析",
};

const STATUS_LABELS = {
  queued: "排队中",
  running: "进行中",
  succeeded: "已完成",
  failed: "失败",
  interrupted: "已中断",
  cancelled: "已取消",
};

const STATUS_ICONS = {
  queued: "clock",
  running: "refresh",
  succeeded: "check-circle",
  failed: "alert-circle",
  interrupted: "alert-triangle",
  cancelled: "x",
};

/**
 * 单个任务提示条
 * @param {{
 *  job:{id:string, kind?:string, status?:"queued"|"running"|"succeeded"|"failed"|"interrupted"|"cancelled",
 *       progress?:number, message?:string, error?:{code:string,message?:string},
 *       artifacts?:Array<{filename:string,download_url?:string}>, created_at?:string},
 *  onCancel?:(id:string)=>void, onDismiss?:(id:string)=>void,
 *  onOpen?:(id:string)=>void, onRetry?:(id:string)=>void
 * }} p
 */
export function jobToast(p = {}) {
  const j = p.job || {};
  const status = j.status || "running";
  const kind = JOB_KIND_LABELS[j.kind] || j.kind || "任务";
  const terminal = ["succeeded", "failed", "interrupted", "cancelled"].includes(status);

  return h(
    "div",
    {
      class: cx("toast", `is-${status}`),
      role: status === "failed" ? "alert" : "status",
      "aria-live": status === "failed" ? "assertive" : "polite",
    },
    h(
      "div",
      { class: "toast__head" },
      h(
        "span",
        { class: "toast__icon" },
        icon(STATUS_ICONS[status] || "clock", {
          size: 15,
          cls: status === "running" ? "is-spinning" : "",
        }),
      ),
      h(
        "span",
        { class: "toast__main" },
        h("span", { class: "toast__title" }, kind),
        h("span", { class: "toast__status" }, STATUS_LABELS[status] || status,
          j.message ? h("span", { class: "toast__msg" }, ` · ${j.message}`) : null),
      ),
      terminal
        ? button({ label: "", variant: "quiet", size: "sm", icon: "x", ariaLabel: "关闭提示", onClick: p.onDismiss ? () => p.onDismiss(j.id) : null })
        : p.onCancel
          ? button({ label: "取消", variant: "quiet", size: "sm", onClick: () => p.onCancel(j.id) })
          : null,
    ),

    status === "running" || status === "queued"
      ? progress({ value: j.progress ?? null, label: status === "queued" ? "等待执行" : "处理中" })
      : null,

    status === "failed"
      ? h(
          "div",
          { class: "toast__error" },
          h("span", null, describeError(j.error).title),
          j.error && j.error.code ? h("span", { class: "mono small muted" }, j.error.code) : null,
          p.onRetry ? button({ label: "重试", size: "sm", variant: "ghost", onClick: () => p.onRetry(j.id) }) : null,
        )
      : null,

    status === "interrupted"
      ? h(
          "div",
          { class: "toast__error" },
          h("span", null, "服务重启导致任务中断，没有产生文件。"),
          p.onRetry ? button({ label: "重新执行", size: "sm", variant: "ghost", onClick: () => p.onRetry(j.id) }) : null,
        )
      : null,

    status === "succeeded" && j.artifacts && j.artifacts.length
      ? h(
          "div",
          { class: "toast__result" },
          j.artifacts.map((a) =>
            h(
              "a",
              {
                class: "toast__file",
                href: a.download_url || "#",
                download: a.filename || null,
              },
              icon("download", { size: 13 }),
              h("span", { class: "truncate" }, a.filename || "下载文件"),
            ),
          ),
          p.onOpen ? button({ label: "打开所在目录", size: "sm", variant: "quiet", onClick: () => p.onOpen(j.id) }) : null,
        )
      : null,
  );
}

/**
 * 右下角图层（最多显示 3 条，其余折叠为「还有 N 个任务」）
 * @param {{jobs:Array, onCancel?:Function, onDismiss?:Function, onOpen?:Function, onRetry?:Function}} p
 */
export function toastLayer(p = {}) {
  const jobs = p.jobs || [];
  if (!jobs.length) return null;
  const shown = jobs.slice(0, 3);
  const rest = jobs.length - shown.length;
  return h(
    "div",
    { class: "toast-layer", "aria-label": "后台任务" },
    shown.map((j) =>
      jobToast({ job: j, onCancel: p.onCancel, onDismiss: p.onDismiss, onOpen: p.onOpen, onRetry: p.onRetry }),
    ),
    rest > 0
      ? h(
          "div",
          { class: "toast toast--summary" },
          h("span", null, `还有 ${rest} 个任务在进行`),
        )
      : null,
  );
}
