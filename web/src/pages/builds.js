/**
 * 组装：选模板 + 选经历 + 中英切换 + 命名实时预览 → 导出 PDF。
 *
 * 两个必须在界面上说清楚的事：
 * 1. 文件名来自 UserProfile（姓名/校名），缺一项就在这里挡住并说明原因，不产残缺文件；
 * 2. 语言切到英文但仓库里没有英文变体时，页面明示「以下条目沿用中文原文」（LANG_FALLBACK），不静默。
 */

import { h } from "../components/dom.js";
import { page } from "../components/layout.js";
import { banner, button, callout, card, checkbox, emptyState, input, select, skeleton, statusDot, textarea, toggle } from "../components/primitives.js";
import { api, itemsOf } from "../api.js";
import { describeError, errorText } from "../components/errors.js";
import { createAction, feedbackRegion } from "../components/feedback.js";
import { forgetJob, jobProgress, listRememberedJobs, peekJob, trackJob } from "../components/progress.js";
import { buildLayout } from "../components/build-parts.js";

const LANG_LABEL = { zh: "中文", en: "英文" };

export function render() {
  // env 的字体探测结果：不可用时导出必失败，必须提前说、并且把按钮禁掉
  // （AC-UI-08）。默认 null = 还没探到，按可用处理，避免首屏闪一下报错。
  const state = {
    fontBad: null,
    lang: "zh",
    templateId: "",
    jdId: "",
    position: "",
    company: "",
    includePhoto: true,
    selected: new Set(),
    buildId: "",
  };

  const host = h("div", { class: "stack" });
  const namingHost = h("div", null);
  const warningHost = h("div", { class: "stack" });
  const previewHost = h("div", { class: "stack" });
  previewHost.replaceChildren(
    emptyState({
      icon: "eye",
      title: "组装后在这里预览",
      desc: "左侧选好模板与经历，点「组装预览」。这里会给出文件名、段落清单与预计页数，再决定是否导出 PDF。",
    }),
  );

  const positionInput = input({ id: "bd-position", placeholder: "岗位名（决定文件名开头）" });
  const companyInput = input({ id: "bd-company", placeholder: "公司名（可不填）" });
  const templateSelect = select({ id: "bd-template", options: [] });
  const jdSelect = select({ id: "bd-jd", options: [{ value: "", label: "不关联岗位" }] });
  const photoToggle = toggle({ checked: true, label: "包含照片", onChange: (on) => { state.includePhoto = on; refreshNaming(); } });
  const langSwitch = select({
    id: "bd-lang",
    options: [
      { value: "zh", label: "中文" },
      { value: "en", label: "English" },
    ],
    value: "zh",
    onChange: (value) => {
      state.lang = value;
      loadTemplates();
      refreshNaming();
    },
  });

  // 反馈区：组装 / 导出的四态说明都落在这里（aria-live 播报，可关闭，可重试）
  const fb = feedbackRegion({ label: "组装与导出状态" });

  // 命名预览防抖：以前每敲一个键就发一次 /naming/validate（B5）
  let namingTimer = 0;
  let namingSeq = 0;
  let namingController = null;
  function scheduleNaming(delay = 300) {
    window.clearTimeout(namingTimer);
    namingTimer = window.setTimeout(() => {
      namingTimer = 0;
      refreshNaming();
    }, delay);
  }

  // 只有装配完成后才能导出：没组装过就点，明确说「先组装」
  const exportAction = createAction({
    label: "导出 PDF",
    variant: "primary",
    icon: "download",
    onClick: () => exportPdf(),
  });
  const assembleAction = createAction({
    label: "组装预览",
    variant: "primary",
    onClick: () => assemble(),
  });

  async function loadTemplates() {
    try {
      const data = await api.templates(state.lang);
      const items = itemsOf(data);
      templateSelect.replaceChildren(
        ...items.map((item) => h("option", { value: item.id }, `${item.name}${item.is_default ? "（默认）" : ""}`)),
      );
      if (!items.length) {
        warningHost.replaceChildren(callout({ tone: "warn", title: `${LANG_LABEL[state.lang]}还没有模板`, body: "去「模板」页导入一份，或把语言切回中文。" }));
        state.templateId = "";
        // 没有模板也要把「文件名能不能生成」算出来：用户可能同时缺姓名/学校，
        // 两件事必须都摆出来，不能因为缺模板就把另一个问题藏掉（AC-UI-05）。
        await refreshNaming();
        return;
      }
      const preferred = items.find((item) => item.is_default) || items[0];
      state.templateId = preferred.id;
      templateSelect.value = preferred.id;
      await Promise.all([loadPackages(), loadJds()]);
      await refreshNaming();
    } catch (err) {
      warningHost.replaceChildren(callout({ tone: "danger", title: "读不到模板", body: errorText(err) }));
    }
  }

  async function loadJds() {
    try {
      const items = itemsOf(await api.jds());
      jdSelect.replaceChildren(
        h("option", { value: "" }, "不关联岗位"),
        ...items.map((jd) => h("option", { value: jd.id }, `${jd.title}${jd.company_name ? ` · ${jd.company_name}` : ""}`)),
      );
    } catch {
      /* 岗位不是必须的，读不到就不填 */
    }
  }

  async function loadPackages() {
    if (!host.dataset.loaded) {
      const slot = h("div.ux-skel-slot", { "aria-hidden": "true" }, skeleton({ title: false, lines: 4 }));
      slot.style.setProperty("--ux-skel-h", "148px");
      host.replaceChildren(slot);
    }
    try {
      const items = itemsOf(await api.packages("?limit=100"));
      // 演示数据（tags 含 sample / 标题以【示例】开头）默认不选：它会让成品里出现
      // 用户没做过的经历。判据与后端 services/samples.py 一致，后端导出时还会再兜一道。
      const isSample = (item) =>
        String(item.title || "").trim().startsWith("【示例】") ||
        (Array.isArray(item.tags) ? item.tags : []).map((t) => String(t).toLowerCase()).includes("sample");
      state.selected = new Set(
        items.filter((item) => item.status === "ready" && !isSample(item)).map((item) => item.id),
      );
      const rows = items.length
        ? items.map((item) =>
            checkbox({
              label: `${item.title}${
                isSample(item) ? "（示例数据，默认不选）" : item.status === "ready" ? "" : "（待核实，组装时会被跳过）"
              }`,
              checked: state.selected.has(item.id),
              onChange: (on, node) => {
                if (on) state.selected.add(item.id);
                else state.selected.delete(item.id);
                refreshNaming();
              },
            }),
          )
        : [emptyState({ title: "经历库是空的", desc: "去工作台讲一段经历，或从「模板」页导入现有简历。" })];
      host.replaceChildren(h("div", { class: "stack" }, rows));
      host.dataset.loaded = "1";
    } catch (err) {
      host.replaceChildren(callout({ tone: "danger", title: "读不到经历库", body: errorText(err) }));
    }
  }

  async function refreshNaming() {
    // 新请求取消旧请求：连打时不排队、不闪回旧结果
    const seq = ++namingSeq;
    if (namingController) namingController.abort();
    namingController = new AbortController();
    const signal = namingController.signal;
    namingHost.setAttribute("aria-busy", "true");
    try {
      const profile = await api.profile();
      if (seq !== namingSeq) return { ok: false, stale: true, filename: "", errors: [] };
      const result = await api.validateNaming(
        {
          pattern: "{position}-{name}-{school}",
          lang: state.lang,
          position: String(positionInput.value || "").trim(),
          company: String(companyInput.value || "").trim(),
        },
        { signal },
      );
      if (seq !== namingSeq) return { ok: false, stale: true, filename: "", errors: [] };
      const filename = result.filename || "";
      const errors = result.errors || [];
      const warnings = result.warnings || [];
      const missing = profile.missing || [];
      namingHost.replaceChildren(
        callout({
          tone: errors.length ? "danger" : "info",
          title: errors.length ? "文件名还不能生成" : `文件名：${filename}`,
          body: h(
            "div",
            { class: "stack", style: { gap: "4px" } },
            errors.length
              ? h("ul", null, errors.map((err) => h("li", null, `${err.message}${err.field ? `（${err.field}）` : ""}`)))
              : h("div", { class: "small muted" }, "姓名与校名取自「个人资料」，改名会立刻反映在这里。"),
            missing.length ? h("div", { class: "small muted" }, `个人资料待补：${missing.join("、")}`) : null,
            // AC-UI-05：报错必须同时给出「下一步去哪儿」，不能只丢一句红字
            errors.length ? h("div", { class: "row" }, h("a", { class: "ui-btn ui-btn--ghost ui-btn--sm", href: "#/profile" }, "去个人资料")) : null,
            warnings.length ? h("div", { class: "small muted" }, warnings.map((w) => w.message).join("；")) : null,
          ),
        }),
      );
      namingHost.setAttribute("aria-busy", "false");
      return { ok: !errors.length, filename, errors };
    } catch (err) {
      namingHost.setAttribute("aria-busy", "false");
      // 被新输入取消的那次不算失败，也不许把旧错误糊上去
      if ((err && err.code === "ABORTED") || seq !== namingSeq) {
        return { ok: false, stale: true, filename: "", errors: [] };
      }
      namingHost.replaceChildren(callout({ tone: "danger", title: "命名校验失败", body: errorText(err) }));
      return { ok: false, filename: "", errors: [{ message: describeError(err) }] };
    }
  }

  async function assemble() {
    previewHost.replaceChildren();
    fb.pending("正在组装", "本机拼装模板与经历，不联网。");
    const naming = await refreshNaming();
    if (naming.stale) {
      fb.idle();
      return;
    }
    if (!naming.ok) {
      warningHost.replaceChildren(callout({ tone: "danger", title: "先补全再组装", body: "文件名不完整时不会生成简历——避免产出「-张三-.pdf」这种。" }));
      fb.error(
        { code: "PROFILE_INCOMPLETE", message: "姓名或校名还缺，文件名拼不出来。" },
        {
          retryable: false,
          actionLabel: "去个人资料",
          onAction: () => {
            location.hash = "#/profile";
          },
          hint: "补全姓名与校名后回来再组装；缺任意一项都不会生成残缺文件名。",
        },
      );
      return { ok: false };
    }
    try {
      if (!state.buildId) {
        const build = await api.createBuild({
          name: `${String(positionInput.value || "定制简历").trim()}-${state.lang}`,
          template_id: state.templateId,
          jd_id: String(jdSelect.value || "") || null,
          position: String(positionInput.value || "").trim() || null,
          company: String(companyInput.value || "").trim() || null,
          lang: state.lang,
        });
        state.buildId = build.id;
      }
      await api.setSelections(state.buildId, Array.from(state.selected).map((id) => ({ package_id: id })));
      const assembled = await api.assemble(state.buildId);
      renderAssembled(assembled);
      fb.success({
        title: "组装完成",
        body: `${(assembled.sections || []).length} 个段落 · 预计 ${assembled.est_pages || 1} 页。确认没问题后点「导出 PDF」。`,
        announce: "组装完成",
      });
      return { ok: true, value: assembled };
    } catch (err) {
      warningHost.replaceChildren(callout({ tone: "danger", title: "组装失败", body: errorText(err) }));
      fb.error(err, {
        retryable: true,
        onRetry: () => assemble(),
        hint: "选项都还在；重试会重新组装同一个 build，不会新建。",
      });
      throw err;
    }
  }

  function renderAssembled(assembled) {
    const sections = assembled.sections || [];
    const warnings = assembled.warnings || [];
    const comp = assembled.competitiveness_summary || {};
    const fallback = warnings.find((w) => w.code === "LANG_FALLBACK");
    const omitted = warnings.filter((w) => w.code === "PACKAGE_MISSING");
    warningHost.replaceChildren(
      fallback
        ? callout({
            tone: "warn",
            title: "部分条目沿用中文原文",
            body: `仓库里没有英文表述的条目共 ${fallback.details?.entry_count ?? "?"} 条、要点 ${fallback.details?.bullet_count ?? "?"} 条${fallback.details?.skills_fallback ? "（职业技能整块）" : ""}。要英文版就先去经历库补英文变体。`,
          })
        : null,
      omitted.length ? callout({ tone: "warn", title: "有段落没有内容，已省略", body: omitted.map((w) => w.details?.heading || w.details?.section || "某段").join("、") }) : null,
      warnings.filter((w) => !["LANG_FALLBACK", "PACKAGE_MISSING"].includes(w.code)).length
        ? callout({ tone: "info", title: "其他提示", body: h("ul", null, warnings.filter((w) => !["LANG_FALLBACK", "PACKAGE_MISSING"].includes(w.code)).map((w) => h("li", null, `${w.code}：${w.message || ""}`))) })
        : null,
    );
    previewHost.replaceChildren(
      card({
        title: "组装结果",
        desc: `${sections.length} 个段落 · 预计 ${assembled.est_pages || 1} 页${comp.verdict ? ` · 竞争力 ${comp.verdict}` : ""}`,
        body: h(
          "div",
          { class: "stack" },
          sections.map((section) =>
            h(
              "div",
              { class: "stack", style: { gap: "2px" } },
              h("strong", null, section.heading),
              h(
                "div",
                { class: "small muted" },
                (() => {
                  // 接口给的是计数（{"entries":1,"bullets":2,"skills":0}），不是数组；
                  // 早先按 .length 取，界面就变成「教育背景 / undefined 条」。
                  const count = (v) => (Array.isArray(v) ? v.length : Number(v) || 0);
                  const parts = [`${count(section.entries)} 条`];
                  if (count(section.skills)) parts.push(`${count(section.skills)} 行技能`);
                  return parts.join(" · ");
                })(),
              ),
            ),
          ),
          h(
            "div",
            { class: "row" },
            exportAction.node,
            button({ label: "重新组装", variant: "ghost", onClick: () => assembleAction.run(() => assemble()) }),
          ),
        ),
      }),
    );
  }

  function exportFailureCopy(failure, status) {
    const copy = describeError(failure);
    return h(
      "div",
      { class: "stack", style: { gap: "4px" } },
      h("div", null, copy.body || ""),
      h("div", { class: "small muted" }, copy.hint || ""),
      h("div", { class: "small muted" }, `技术细节：${(failure && failure.code) || status || "EXPORT_FAILED"}`),
    );
  }

  /** 任务结束后的统一呈现：成功给文件名+下载链接，失败给人话三段式 */
  function exportFinished(done, panel) {
    if (!done || done.status !== "succeeded") {
      const failure = (done && done.error_json) || {
        code: done && done.status === "interrupted" ? "JOB_INTERRUPTED" : "EXPORT_FAILED",
        message: (done && done.message) || "",
      };
      if (panel) panel.fail(failure);
      fb.error(failure, {
        retryable: failure.code !== "PAGE_OVERFLOW" && failure.code !== "FONT_UNAVAILABLE",
        onRetry: () => exportPdf(),
        hint:
          failure.code === "JOB_INTERRUPTED"
            ? "服务重启把任务打断了，重试会从头渲染一次。"
            : "重试会重新渲染同一个 build；不行就换模板或减少内容。",
      });
      return;
    }
    const result = done.result_json || {};
    const artifact = (result.artifacts || [])[0] || {};
    const warnings = artifact.warnings_json || result.warnings || [];
    if (panel) panel.done(done);
    const href = `/api/v1/artifacts/${artifact.id}/download`;
    fb.success({
      title: `已导出：${artifact.filename || ""}`,
      body: h(
        "div",
        { class: "stack", style: { gap: "4px" } },
        h("div", null, `${Math.round((artifact.bytes || 0) / 1024)} KB · 文本层校验 ${artifact.text_verified ? "通过" : "未通过"}`),
        warnings.length ? h("div", { class: "small muted" }, warnings.map((w) => w.code).join("、")) : null,
      ),
      actions: [h("a", { class: "ui-btn ui-btn--primary ui-btn--sm", href, target: "_blank", rel: "noopener" }, "下载 PDF")],
      announce: `导出完成：${artifact.filename || ""}`,
    });
  }

  async function exportPdf() {
    if (state.fontBad) {
      fb.error(
        { code: "FONT_UNAVAILABLE", message: "这台机器没有中文字体（宋体），渲染一定会失败。" },
        { retryable: false, hint: "装好宋体（/System/Library/Fonts/Supplemental/Songti.ttc）后刷新页面再导出。" },
      );
      return { ok: false };
    }
    if (!state.buildId) {
      fb.error(
        { code: "VALIDATION_ERROR", message: "还没有组装过，没有可导出的内容。" },
        { retryable: true, onRetry: () => exportPdf(), hint: "先点「组装预览」，确认段落无误后再导出。" },
      );
      return { ok: false };
    }
    const startedAt = Date.now();
    const scope = `builds:export:${state.buildId}`;
    const panel = jobProgress({ kind: "build_export", label: "导出 PDF", startedAt, showHint: true });
    warningHost.prepend(panel.node);
    fb.pending("正在渲染 PDF", "可以离开这一页，任务会在服务端继续；回来会自动接上。");
    try {
      const job = await api.exportBuild(state.buildId, { format: "pdf", verify_text: true, include_photo: state.includePhoto });
      const jobId = (job && (job.job_id || job.id)) || "";
      if (!jobId) {
        panel.fail({ code: "INTERNAL" });
        fb.error({ code: "INTERNAL", message: "后端没有返回 job_id，无法跟踪这次导出。" }, {
          retryable: true,
          onRetry: () => exportPdf(),
          hint: "可能后端版本较旧；重试一次，或重启本地服务。",
        });
        return { ok: false };
      }
      await new Promise((resolve) => {
        trackJob({
          jobId,
          scope,
          kind: "build_export",
          label: "导出 PDF",
          startedAt,
          onUpdate: (j, meta) => panel.update(j, meta && meta.elapsedMs),
          onDone: (done) => {
            exportFinished(done, panel);
            resolve();
          },
          onError: (err) => {
            panel.fail(err);
            fb.error(err, {
              retryable: true,
              onRetry: () => exportPdf(),
              hint: "引擎或服务可能刚重启；重试会重新渲染，不会产生两份文件。",
            });
            resolve();
          },
          alive: () => warningHost.isConnected,
        });
      });
      return { ok: true };
    } catch (err) {
      panel.fail(err);
      fb.error(err, {
        retryable: true,
        onRetry: () => exportPdf(),
        hint: "导出请求没发出去；重试一次即可，不会重复排队。",
      });
      throw err;
    }
  }

  /** 切页回来：如果这个截图（build）的导出还在服务端跑，把进度条接回去 */
  async function resumeExport() {
    let rec = null;
    for (const item of listRememberedJobs()) {
      if (String(item.scope || "").startsWith("builds:export:")) {
        rec = item;
        break;
      }
    }
    if (!rec) return;
    const current = await peekJob(rec.jobId);
    if (!current) {
      forgetJob(rec.scope);
      return;
    }
    if (["succeeded", "failed", "interrupted", "cancelled"].includes(current.status)) {
      forgetJob(rec.scope);
      return;
    }
    if (!state.buildId) state.buildId = rec.scope.slice("builds:export:".length);
    const panel = jobProgress({ kind: "build_export", label: rec.label || "导出 PDF", startedAt: rec.startedAt, showHint: true });
    warningHost.prepend(panel.node);
    const secs = Math.max(1, Math.round((Date.now() - (rec.startedAt || Date.now())) / 1000));
    fb.pending("上次的导出还在继续", `已跑 ${secs} 秒；进度条已经接回来，导出完成后会给你下载链接。`);
    trackJob({
      jobId: rec.jobId,
      scope: rec.scope,
      kind: "build_export",
      label: rec.label || "导出 PDF",
      startedAt: rec.startedAt,
      onUpdate: (j, meta) => panel.update(j, meta && meta.elapsedMs),
      onDone: (done) => exportFinished(done, panel),
      onError: (err) => {
        panel.fail(err);
        fb.error(err, { retryable: true, onRetry: () => exportPdf(), hint: "任务在服务端可能已经结束；重试会重新渲染。" });
      },
      alive: () => warningHost.isConnected,
    });
  }

  // 连续输入只发最后一次（300ms 防抖），并用 AbortController 取消在途请求
  positionInput.addEventListener("input", () => scheduleNaming(300));
  companyInput.addEventListener("input", () => scheduleNaming(300));

  // 字体自检：不可用时导出必然 FONT_UNAVAILABLE，与其让用户点了才报错，
  // 不如进来就红条说清楚，并把导出按钮禁掉（AC-UI-08）。
  async function probeFonts() {
    try {
      const env = await api.env();
      const fonts = (env && env.fonts) || {};
      state.fontBad = fonts.ok !== true;
      if (state.fontBad) {
        // 结构性不可用：导出按钮置灰（不是 pending 态，原生 disabled 正确）
        exportAction.setDisabled(true);
        exportAction.setLabel("导出 PDF（缺中文字体）");
        warningHost.prepend(
          banner({
            text: "这台机器没有找到中文字体（宋体），导出 PDF 会失败：请装 /System/Library/Fonts/Supplemental/Songti.ttc 或改设置里的 PDF 引擎。",
          }),
        );
      }
    } catch {
      /* 自检失败不影响主流程：真导出时后端还会再挡一次 */
    }
  }

  queueMicrotask(probeFonts);
  queueMicrotask(loadTemplates);
  // 切页回来接上还在跑的导出
  queueMicrotask(resumeExport);

  return page({
    title: "组装",
    desc: "挑模板、挑经历，点导出。文件名按「岗位-姓名-学校」。",
    // 三栏（AC-UI-07）：左=投递参数、中=经历选择与操作、右=预览。
    // 1180px 以下右侧自动撑满到下一行，1280 不出现横向滚动。
    body: buildLayout({
      left: card({
        title: "这次投什么",
        body: h(
          "div",
          { class: "stack" },
          h("div", { class: "row" }, positionInput, companyInput),
          h("div", { class: "row" }, langSwitch, templateSelect, jdSelect),
          h("div", { class: "row" }, photoToggle),
          namingHost,
        ),
      }),
      center: h(
        "div",
        { class: "stack" },
        warningHost,
        fb.node,
        card({ title: "用哪些经历", body: host }),
        h("div", { class: "row" }, assembleAction.node),
      ),
      right: h("div", { class: "stack" }, previewHost),
    }),
  });
}

export default render;
