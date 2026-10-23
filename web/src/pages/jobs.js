/**
 * 岗位：粘 JD → 分析（离线启发式 / 可选 AI，AI 前必须先看「将发送字段清单」）→ 需求与竞争力。
 *
 * 隐私硬线：调用 LLM 的唯一入口是 consent 预览。用户在这里看到的清单就是逐字要发送的内容；
 * 不点确认，一条字节都不会离开本机。
 */

import { h } from "../components/dom.js";
import { page } from "../components/layout.js";
import { button, callout, card, checkbox, emptyState, input, statusDot, textarea } from "../components/primitives.js";
import { api, itemsOf, waitJob } from "../api.js";
import { describeError, errorText } from "../components/errors.js";

const VERDICT_LABEL = { strong: "占优", medium: "势均", weak: "偏弱" };

export function render() {
  const listHost = h("div", { class: "stack" });
  const detailHost = h("div", { class: "stack" });
  const consentHost = h("div", null);

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
    try {
      const data = await api.jds();
      const items = itemsOf(data);
      listHost.replaceChildren(
        items.length
          ? h("div", { class: "stack" }, items.map((jd) => jdRow(jd)))
          : emptyState({ title: "还没有岗位", desc: "把想投的 JD 粘进来，先看清它到底要什么。" }),
      );
    } catch (err) {
      listHost.replaceChildren(callout({ tone: "danger", title: "读不到岗位", body: errorText(err) }));
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
      detailHost.replaceChildren(callout({ tone: "warn", title: "先粘 JD", body: "至少要有一段岗位描述。" }));
      return;
    }
    try {
      const jd = await api.createJd({
        title: String(title.value || "").trim() || "未命名岗位",
        company_name: String(company.value || "").trim() || null,
        raw_text: String(text.value),
      });
      await loadList();
      await analyze(jd.id);
    } catch (err) {
      detailHost.replaceChildren(callout({ tone: "danger", title: "保存失败", body: errorText(err) }));
    }
  }

  /** LLM 路径：先预览字段清单，用户确认后才真正发送。 */
  async function analyze(id) {
    try {
      if (!llmChoice.on) {
        const job = await api.analyzeJd(id, { method: "heuristic" });
        await pollJob(job, id, "本地启发式分析（没走网络）");
        return;
      }
      detailHost.prepend(callout({ tone: "info", title: "正在生成「将发送字段清单」…", body: "这一步不会发送任何内容" }));
      const preview = await api.preview({ purpose: "jd_analyze", selections: { jd_id: id, include_summary: true } });
      showConsent(preview, id);
    } catch (err) {
      detailHost.replaceChildren(callout({ tone: "danger", title: "分析没开始", body: errorText(err) }));
    }
  }

  function showConsent(preview, jdId) {
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
            button({
              label: "确认发送并分析",
              variant: "primary",
              onClick: async (ev) => {
                ev.currentTarget.disabled = true;
                consentHost.replaceChildren(callout({ tone: "info", title: "已发送，等待模型返回…", body: "失败会自动降级为本地启发式。" }));
                try {
                  const job = await api.analyzeJd(jdId, { method: "llm", preview_id: preview.preview_id, expected_payload_sha256: preview.payload_sha256 });
                  await pollJob(job, jdId, "AI 分析");
                } catch (err) {
                  detailHost.replaceChildren(callout({ tone: "warn", title: "AI 分析没成功", body: errorText(err), actions: h("div", { class: "row" }, button({ label: "改用本地分析", onClick: () => api.analyzeJd(jdId, { method: "heuristic" }).then(() => showDetail(jdId)) })) }));
                }
              },
            }),
            button({ label: "不发送", variant: "ghost", onClick: () => consentHost.replaceChildren() }),
          ),
        ),
      }),
    );
  }

  async function pollJob(job, jdId, label) {
    const jobId = (job && (job.job_id || job.id)) || "";
    detailHost.replaceChildren(callout({ tone: "info", title: `${label}进行中…`, body: "完成后自动刷新。" }));
    const done = jobId ? await waitJob(jobId) : job;
    if (done && done.status === "failed") {
      detailHost.replaceChildren(callout({ tone: "danger", title: "分析失败", body: JSON.stringify(done.error_json || {}, null, 2) }));
      return;
    }
    await loadList();
    await showDetail(jdId);
  }

  queueMicrotask(loadList);

  return page({
    title: "岗位",
    desc: "粘 JD → 看清技能需求、院校门槛与你的竞争力差距。",
    actions: button({ label: "保存并分析", variant: "primary", icon: "sparkles", onClick: createJd }),
    body: h(
      "div",
      { class: "stack" },
      card({
        title: "新增岗位",
        body: h("div", { class: "stack" }, h("div", { class: "row" }, title, company), text, useLlm),
      }),
      consentHost,
      detailHost,
      card({ title: "已保存的岗位", body: listHost }),
    ),
  });
}

export default render;
