/**
 * 岗位：粘 JD → 分析（离线启发式 / 可选 AI，AI 前必须先看「将发送字段清单」）→ 需求与竞争力。
 *
 * 隐私硬线：调用 LLM 的唯一入口是 consent 预览。用户在这里看到的清单就是逐字要发送的内容；
 * 不点确认，一条字节都不会离开本机。
 */

import { h } from "../components/dom.js";
import { page } from "../components/layout.js";
import { button, callout, card, checkbox, emptyState, input, skeleton, statusDot, textarea } from "../components/primitives.js";
import { api, itemsOf } from "../api.js";
import { describeError, errorText } from "../components/errors.js";
import { createAction, feedbackRegion } from "../components/feedback.js";
import { forgetJob, jobProgress, listRememberedJobs, peekJob, recallJob, trackJob } from "../components/progress.js";
import { toastWarn } from "../components/toast.js";

const VERDICT_LABEL = { strong: "占优", medium: "势均", weak: "偏弱" };

export function render() {
  const listHost = h("div", { class: "stack" });
  const detailHost = h("div", { class: "stack" });
  const consentHost = h("div", null);
  // 反馈区：保存/分析/失败说明统一落这里（aria-live 播报，可关闭，带重试）
  const fb = feedbackRegion({ label: "岗位与分析状态" });

  function skeletonRows(count = 4) {
    const rows = h("div.ux-skel-rows", { "aria-hidden": "true" });
    for (let i = 0; i < count; i += 1) rows.appendChild(skeleton({ title: true, lines: 2 }));
    const slot = h("div.ux-skel-slot", { "aria-hidden": "true" }, rows);
    slot.style.setProperty("--ux-skel-h", "64px");
    return slot;
  }

  const title = input({ id: "jd-title", placeholder: "岗位名，如：数据分析实习生" });
  const company = input({ id: "jd-company", placeholder: "公司名，如：星链数科（杭州）有限公司" });
  const text = textarea({ id: "jd-text", rows: 8, placeholder: "把 JD 原文粘进来（责任、要求、加分项都算）" });
  const llmChoice = { on: false };
  const useLlm = checkbox({
    label: "用 DeepSeek 分析（会先给你看将发送的字段清单）",
    checked: false,
    onChange: (checked) => {
      llmChoice.on = checked;
    },
  });

  async function loadList() {
    const first = !listHost.dataset.loaded;
    listHost.setAttribute("aria-busy", "true");
    if (first) listHost.replaceChildren(skeletonRows(4));
    try {
      const data = await api.jds();
      const items = itemsOf(data);
      listHost.replaceChildren(
        items.length
          ? h("div", { class: "stack" }, items.map((jd) => jdRow(jd)))
          : emptyState({
              title: "还没有岗位",
              desc: "把想投的 JD 粘进来，先看清它到底要什么。",
              actions: h("a", { class: "ui-btn ui-btn--secondary", href: "#/builds" }, "看看组装页要什么"),
            }),
      );
      listHost.dataset.loaded = "1";
      listHost.setAttribute("aria-busy", "false");
    } catch (err) {
      listHost.setAttribute("aria-busy", "false");
      if (!listHost.dataset.loaded) listHost.replaceChildren();
      fb.error(err, { onRetry: () => loadList(), retryable: true, hint: "本机后端可能没起来；点「重试」再读一次。" });
    }
  }

  function jdRow(jd) {
    return card({
      title: jd.title,
      desc: [jd.company_name, jd.analysis_method ? `分析方式：${jd.analysis_method === "llm" ? "AI" : "本地"}` : "未分析"].filter(Boolean).join(" · "),
      actions: statusDot({ level: jd.analysis_status === "done" ? "ok" : "idle", label: jd.analysis_status === "done" ? "已分析" : "待分析" }),
      body: h("div", { class: "row" }, button({ label: "看需求与竞争力", onClick: () => showDetail(jd.id) })),
    });
  }

  async function showDetail(id) {
    detailHost.replaceChildren(callout({ tone: "info", title: "读取中…", body: "本机数据" }));
    try {
      const jd = await api.jd(id);
      const reqs = jd.requirements || [];
      const comp = jd.competitiveness || {};
      detailHost.replaceChildren(
        card({
          title: jd.title,
          desc: jd.company_name || "",
          body: h(
            "div",
            { class: "stack" },
            comp.verdict
              ? callout({
                  tone: comp.verdict === "weak" ? "warn" : "info",
                  title: `竞争力：${VERDICT_LABEL[comp.verdict] || comp.verdict}`,
                  body: h(
                    "div",
                    { class: "stack", style: { gap: "4px" } },
                    h("div", null, comp.school_signal || ""),
                    h("div", { class: "small muted" }, `学历匹配 ${comp.degree_fit || "?"} · 专业匹配 ${comp.major_fit || "?"} · 经历匹配 ${comp.experience_fit || "?"}`),
                    (comp.gap_notes || []).length ? h("ul", null, comp.gap_notes.map((note) => h("li", null, note))) : null,
                  ),
                })
              : null,
            reqs.length
              ? h(
                  "div",
                  { class: "stack" },
                  reqs.map((req) => {
                    const ev = Array.isArray(req.matched_evidence) ? req.matched_evidence : [];
                    const bits = [];
                    for (const item of ev.filter((e) => e && !e.derived && e.quote).slice(0, 2)) {
                      bits.push(h("span", { class: "chip chip--sm" }, `原文：${String(item.quote).slice(0, 30)}`));
                    }
                    // 推算 ≠ 原文命中：本地确定性规则（校名→层次、届别≥要求年份）也
                    // 算证据，但必须逐条标明，否则用户会把「推算」当成简历里的原话。
                    for (const item of ev.filter((e) => e && e.derived).slice(0, 2)) {
                      bits.push(
                        h("span", { class: "chip chip--sm" }, `推算：${String(item.rule || item.quote || "").slice(0, 44)}`),
                      );
                    }
                    if (!ev.length && (req.candidate_status === "satisfied" || req.candidate_status === "partial")) {
                      bits.push(h("span", { class: "chip chip--sm" }, "无依据：仅模型判断，请人工确认"));
                    }
                    return h(
                      "div",
                      { class: "stack", style: { gap: "2px" } },
                      h(
                        "div",
                        { class: "row", style: { gap: "8px", alignItems: "baseline" } },
                        h("span", { class: "chip chip--sm" }, req.priority),
                        h("span", { style: { flex: "1" } }, req.skill),
                        h("span", { class: "small muted" }, req.category),
                        statusDot({
                          level: req.candidate_status === "satisfied" ? "ok" : req.candidate_status === "partial" ? "warn" : "idle",
                          label: { satisfied: "已满足", partial: "部分", missing: "缺失" }[req.candidate_status] || "未评估",
                        }),
                      ),
                      h("div", { class: "row", style: { gap: "6px", paddingLeft: "8px", flexWrap: "wrap" } }, ...bits),
                    );
                  }),
                )
              : h("div", { class: "small muted" }, "还没有拆出需求条目。"),
          ),
        }),
      );
    } catch (err) {
      detailHost.replaceChildren(callout({ tone: "danger", title: "读取失败", body: errorText(err) }));
    }
  }

  async function createJd() {
    if (!String(text.value || "").trim()) {
      // 空 JD：warn + 聚焦到输入框，不静默、不清空已填内容
      toastWarn("先粘一段 JD", { message: "至少要有一段岗位描述才能分析。" });
      fb.error(
        { code: "VALIDATION_ERROR", message: "JD 正文是空的。" },
        { retryable: false, hint: "把岗位描述粘到「新增岗位」的文本框里，再点「保存并分析」。" },
      );
      try {
        text.focus({ preventScroll: true });
        text.scrollIntoView({ block: "center" });
      } catch {
        /* 忽略 */
      }
      return { ok: false, skipped: true };
    }
    fb.pending("正在保存岗位", "写本机数据库，然后开始分析。");
    const jd = await api.createJd({
      title: String(title.value || "").trim() || "未命名岗位",
      company_name: String(company.value || "").trim() || null,
      raw_text: String(text.value),
    });
    await loadList();
    await analyze(jd.id);
    return jd;
  }

  /** LLM 路径：先预览字段清单，用户确认后才真正发送。 */
  async function analyze(id) {
    try {
      if (!llmChoice.on) {
        const job = await api.analyzeJd(id, { method: "heuristic" });
        await trackAnalyze(job, { jdId: id, label: "本地启发式分析" });
        return;
      }
      fb.pending("正在生成「将发送字段清单」", "这一步只有本机，不会发送任何内容。");
      const preview = await api.preview({ purpose: "jd_analyze", selections: { jd_id: id, include_summary: true } });
      showConsent(preview, id);
      fb.idle();
    } catch (err) {
      fb.error(err, {
        retryable: true,
        onRetry: () => analyze(id),
        hint: "预览没生成出来；重试会再请求一次清单，此时仍不会发送任何内容。",
      });
    }
  }

  /** 轮询一个分析任务：进度 + 阶段文案，失败给人话（不弹 JSON） */
  function trackAnalyze(job, opts = {}) {
    const jdId = opts.jdId;
    const label = opts.label || "分析";
    const jobId = (job && (job.job_id || job.id)) || "";
    const scope = `jobs:analyze:${jdId}`;
    if (!jobId) {
      fb.error({ code: "INTERNAL", message: "后端没有返回 job_id，无法跟踪这次分析。" }, {
        retryable: true,
        onRetry: () => analyze(jdId),
        hint: "可能后端版本较旧；重试一次，或重启本地服务。",
      });
      return Promise.resolve({ ok: false });
    }
    const panel = jobProgress({ kind: "jd_analyze", label, startedAt: Date.now() });
    detailHost.replaceChildren(panel.node);
    fb.pending(`${label}进行中`, "可以离开这一页，任务会继续；回来会自动接上。");
    return new Promise((resolve) => {
      trackJob({
        jobId,
        scope,
        kind: "jd_analyze",
        label,
        onUpdate: (j, meta) => panel.update(j, meta && meta.elapsedMs),
        onDone: async (done) => {
          if (done && done.status === "succeeded") {
            panel.done(done);
            fb.success({ title: "分析完成", body: "需求与竞争力已刷新。" });
            await loadList();
            await showDetail(jdId);
            resolve({ ok: true });
            return;
          }
          const failure =
            (done && done.error_json) || {
              code: done && done.status === "interrupted" ? "JOB_INTERRUPTED" : "INTERNAL",
              message: (done && done.message) || "",
            };
          detailHost.replaceChildren();
          fb.error(failure, {
            retryable: true,
            onRetry: () => analyze(jdId),
            hint: "这次分析没有留下半成品；重新分析一次即可，AI 路径会重新生成字段清单。",
          });
          resolve({ ok: false });
        },
        onError: (err) => {
          detailHost.replaceChildren();
          fb.error(err, { retryable: true, onRetry: () => analyze(jdId) });
          resolve({ ok: false });
        },
        alive: () => detailHost.isConnected,
      });
    });
  }

  /** 切页回来：如果服务端还有这个岗位的分析在跑，把轮询接上 */
  async function resumeAnalyze(jdId) {
    const scope = `jobs:analyze:${jdId}`;
    const rec = recallJob(scope);
    if (!rec) return;
    const current = await peekJob(rec.jobId);
    if (!current) {
      forgetJob(scope);
      return;
    }
    if (["succeeded", "failed", "interrupted", "cancelled"].includes(current.status)) {
      forgetJob(scope);
      return;
    }
    // 还在跑：直接接管（提示一句，不重复播报每次轮询）
    const panel = jobProgress({ kind: "jd_analyze", label: rec.label || "岗位分析", startedAt: rec.startedAt, showHint: true });
    detailHost.replaceChildren(panel.node);
    fb.pending("上一次分析还在继续", `已经接上后台任务（已跑 ${Math.max(1, Math.round((Date.now() - (rec.startedAt || Date.now())) / 1000))} 秒）。`);
    trackJob({
      jobId: rec.jobId,
      scope,
      kind: "jd_analyze",
      label: rec.label || "岗位分析",
      startedAt: rec.startedAt,
      onUpdate: (j, meta) => panel.update(j, meta && meta.elapsedMs),
      onDone: async (done) => {
        if (done && done.status === "succeeded") {
          panel.done(done);
          fb.success({ title: "上次的分析完成了", body: "需求与竞争力已刷新。" });
          await loadList();
          await showDetail(jdId);
        } else {
          detailHost.replaceChildren();
          fb.error((done && done.error_json) || { code: "INTERNAL", message: (done && done.message) || "" }, {
            retryable: true,
            onRetry: () => analyze(jdId),
          });
        }
      },
      onError: (err) => {
        detailHost.replaceChildren();
        fb.error(err, { retryable: true, onRetry: () => analyze(jdId) });
      },
      alive: () => detailHost.isConnected,
    });
  }

  /** 用户点了「确认发送并分析」：真正的上云动作，只在 consent 确认后执行一次 */
  async function sendConfirmed(preview, jdId, action) {
    const res = await action.run(async () => {
      const job = await api.analyzeJd(jdId, {
        method: "llm",
        preview_id: preview.preview_id,
        expected_payload_sha256: preview.payload_sha256,
      });
      consentHost.replaceChildren();
      await trackAnalyze(job, { jdId, label: "AI 分析" });
      return job;
    });
    if (res.skipped || res.ok) return;
    // 发送失败不给「自动重发」：consent 预览是一次性的，重试必须重新生成清单（UX-FEEDBACK-PLAN §6 R9）
    fb.error(res.error, {
      retryable: false,
      actionLabel: "重新生成清单",
      onAction: () => analyze(jdId),
      hint: "这次没有发送成功。发送清单是一次性的，要再发一次得重新生成清单并重新确认。",
    });
  }

  function showConsent(preview, jdId) {
    const confirmAction = createAction({ label: "确认发送并分析", variant: "primary" });
    confirmAction.node.addEventListener("click", () => sendConfirmed(preview, jdId, confirmAction));
    const fields = preview.fields || [];
    const excluded = preview.excluded || {};
    const redactions = preview.redactions || [];
    const warnings = preview.warnings || [];
    consentHost.replaceChildren(
      card({
        title: "将发送到 DeepSeek 的字段（逐字）",
        desc: `共 ${preview.total_chars || 0} 字 · 约 ${preview.est_tokens || 0} tokens · 目标 ${preview.endpoint_host} · 过期 ${preview.expires_at || ""}`,
        body: h(
          "div",
          { class: "stack" },
          h(
            "table",
            { class: "table" },
            h("thead", null, h("tr", null, ["字段", "来源", "字数", "脱敏", "发送"].map((label) => h("th", null, label)))),
            h(
              "tbody",
              null,
              fields.map((f) =>
                h(
                  "tr",
                  null,
                  h("td", null, f.label || f.path),
                  h("td", null, `${f.source}${f.source_id ? ` · ${String(f.source_id).slice(0, 8)}` : ""}`),
                  h("td", null, String(f.chars ?? "")),
                  h("td", null, f.redacted ? "是" : "—"),
                  h("td", null, f.included ? "✓" : "—"),
                ),
              ),
            ),
          ),
          excluded.note ? callout({ tone: "info", title: "不发送的内容", body: excluded.note }) : null,
          (excluded.structural_exclusions || []).length
            ? h("div", { class: "small muted" }, `结构上排除：${(excluded.structural_exclusions || []).join("、")}`)
            : null,
          redactions.length
            ? h("div", { class: "small" }, `脱敏 ${redactions.length} 处：${redactions.map((r) => `${r.path}→${r.replacement}`).join("；")}`)
            : null,
          warnings.length ? callout({ tone: "warn", title: "提示", body: h("ul", null, warnings.map((w) => h("li", null, `${w.code}：${w.message || ""}`))) }) : null,
          h(
            "details",
            null,
            h("summary", { class: "small muted" }, "展开逐字 payload"),
            h("pre", { class: "code-block" }, JSON.stringify(preview.payload, null, 2)),
          ),
          h(
            "div",
            { class: "row" },
            confirmAction.node,
            button({ label: "不发送", variant: "ghost", onClick: () => consentHost.replaceChildren() }),
          ),
        ),
      }),
    );
  }


  const saveAnalyzeAction = createAction({
    label: "保存并分析",
    variant: "primary",
    icon: "sparkles",
    onClick: () =>
      createJd().catch((err) => {
        fb.error(err, {
          retryable: true,
          onRetry: () => createJd(),
          hint: "JD 正文还在输入框里；重试会再存一条岗位记录，若已建成就先在列表里删掉旧的。",
        });
        throw err;
      }),
  });

  queueMicrotask(loadList);
  queueMicrotask(async () => {
    // 切页回来续上：只接管「还在跑」的分析任务
    const scopes = new Set();
    for (const rec of listRememberedJobs()) {
      if (String(rec.scope || "").startsWith("jobs:analyze:")) scopes.add(rec.scope);
    }
    for (const scope of scopes) {
      const jdId = scope.slice("jobs:analyze:".length);
      if (jdId) await resumeAnalyze(jdId);
    }
  });

  return page({
    title: "岗位",
    desc: "粘 JD → 看清技能需求、院校门槛与你的竞争力差距。",
    actions: saveAnalyzeAction.node,
    body: h(
      "div",
      { class: "stack" },
      card({
        title: "新增岗位",
        body: h("div", { class: "stack" }, h("div", { class: "row" }, title, company), text, useLlm),
      }),
      consentHost,
      fb.node,
      detailHost,
      card({ title: "已保存的岗位", body: listHost }),
    ),
  });
}

export default render;
