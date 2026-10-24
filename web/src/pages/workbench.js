/**
 * 工作台：把一段经历讲清楚，落成 Package 草稿。
 *
 * 全流程零出网：`POST /packages/draft` 是本地规则抽取（日期/机构/角色/指标/技术栈），
 * 不调用任何 LLM。想改写措辞要走 consent（字段清单先给用户看），不在这一屏偷偷发。
 */

import { h } from "../components/dom.js";
import { page } from "../components/layout.js";
import { button, callout, card, emptyState, kv, skeleton, textarea, input, select } from "../components/primitives.js";
import { api } from "../api.js";
import { createAction, feedbackRegion } from "../components/feedback.js";
import { toastWarn } from "../components/toast.js";

const KIND_OPTIONS = [
  { value: "", label: "自动判断" },
  { value: "internship", label: "实习" },
  { value: "project", label: "项目" },
  { value: "activity", label: "校园活动" },
  { value: "award", label: "获奖" },
];

export function render() {
  const result = h("div", { class: "stack" });
  const fb = feedbackRegion({ label: "拆解与保存状态" });
  const inputArea = textarea({
    id: "wb-text",
    rows: 10,
    placeholder: "例：2026.07-2026.10 在杭州拓端数据科技有限公司做数据处理实习生，独立负责 17 项逐日环境指标治理，交付数据完整率 99.7% 的数据集……",
  });
  const titleField = input({ id: "wb-title", placeholder: "标题（可不填，留空会自动截取）" });
  const kindField = select({ id: "wb-kind", options: KIND_OPTIONS, value: "" });

  async function draft() {
    const text = String(inputArea.value || "").trim();
    if (!text) {
      // 空文本不许静默：warn + 聚焦到文本框，已填内容一点不动（B1）
      toastWarn("先把经历写下来", { message: "哪怕两句话也行——时间、单位、你做了什么。" });
      fb.error(
        { code: "VALIDATION_ERROR", message: "经历正文是空的。" },
        { retryable: false, hint: "在下面的输入框写一段经历（时间 / 单位 / 你做了什么），再点「开始拆解」。" },
      );
      try {
        inputArea.focus({ preventScroll: true });
        inputArea.scrollIntoView({ block: "center" });
      } catch {
        /* 忽略 */
      }
      return { ok: false, skipped: true };
    }
    fb.pending("正在本地拆解", "纯本机规则抽取，不会发送给任何模型。");
    const slot = h("div.ux-skel-slot", { "aria-hidden": "true" }, skeleton({ title: true, lines: 4 }));
    slot.style.setProperty("--ux-skel-h", "220px");
    result.replaceChildren(slot);
    try {
      const data = await api.draftPackage(text);
      result.replaceChildren(renderDraft(data));
      fb.success({
        title: "拆解完成",
        body: `识别出 ${(data.bullets || []).length} 条要点、${(data.outcomes || []).length} 个量化结果。核对后再保存。`,
      });
      return data;
    } catch (err) {
      result.replaceChildren();
      fb.error(err, {
        retryable: true,
        onRetry: () => draft(),
        hint: "输入还在文本框里；重试会重新拆一遍，不会覆盖任何已保存的经历。",
      });
      throw err;
    }
  }

  /** 保存草稿：四态 + 成功后给去经历库的链接；失败保留拆解结果与用户输入 */
  async function saveDraft(data, pkg, bullets) {
    fb.pending("正在存进经历库", "写本机数据库。");
    try {
      const created = await api.createPackage({
        ...pkg,
        variants: bullets.map((b, index) => ({
          bullet_key: b.bullet_key || `b${index + 1}`,
          tone: "original",
          lang: data.lang || "zh",
          text: b.fact,
          verified: false,
        })),
      });
      fb.success({
        title: "已存进经历库",
        body: h(
          "div",
          { class: "stack" },
          h("div", null, `「${created.title}」共 ${bullets.length} 条要点，状态：${created.status === "ready" ? "可复用" : "草稿（要点未核实）"}`),
          h("div", { class: "small muted" }, "要点未核实时，组装页会跳过这条；去经历库点「标记核实」即可。"),
        ),
        actions: [h("a", { class: "ui-btn ui-btn--secondary ui-btn--sm", href: "#/warehouse" }, "去经历库看看")],
        announce: "已保存",
      });
      return created;
    } catch (err) {
      fb.error(err, {
        retryable: true,
        onRetry: () => saveDraft(data, pkg, bullets),
        hint: "拆解结果还在下面；重试会再存一次，若已建成请先在经历库删掉重复的那条。",
      });
      throw err;
    }
  }

  function renderDraft(data) {
    const pkg = data.package || {};
    const bullets = data.bullets || [];
    const questions = data.questions || [];
    const warnings = data.warnings || [];

    if (titleField.value && !pkg.title) pkg.title = titleField.value;
    if (kindField.value) pkg.kind = kindField.value;

    const saveAction = createAction({
      label: `保存为经历（${bullets.length} 条要点）`,
      variant: "primary",
      icon: "save",
      onClick: () => saveDraft(data, pkg, bullets),
    });

    return h(
      "div",
      { class: "stack" },
      card({
        title: "拆解结果",
        desc: "以下是本地规则抽取，请核对；不对就直接改文字重新拆。",
        body: h(
          "div",
          { class: "stack" },
          kv([
            ["标题", pkg.title || "—"],
            ["类型", pkg.kind || "—"],
            ["单位", pkg.org || "—"],
            ["角色", pkg.role || "—"],
            ["时间", pkg.is_current ? `${pkg.start_date || "?"} - 至今` : `${pkg.start_date || "?"} - ${pkg.end_date || "?"}`],
            ["技术栈", (pkg.tech_stack || []).join("、") || "未识别"],
            ["量化结果", (data.outcomes || []).map((o) => o.metric || o).join("；") || "未识别"],
          ]),
          warnings.length
            ? callout({
                tone: "warn",
                title: "有几处没识别出来",
                body: h("ul", null, warnings.map((w) => h("li", null, w.message || w.code))),
              })
            : null,
        ),
      }),
      card({
        title: `要点（${bullets.length}）`,
        body: h(
          "div",
          { class: "stack" },
          bullets.map((b, index) =>
            h(
              "div",
              { class: "stack", style: { gap: "2px" } },
              h("div", { class: "small muted" }, `#${index + 1}${b.has_metric ? " · 含量化" : ""}`),
              h("div", null, b.fact),
            ),
          ),
        ),
      }),
      questions.length
        ? card({
            title: "补两句话会更完整",
            body: h("ul", null, questions.map((q) => h("li", null, q.question || q))),
          })
        : null,
      h("div", { class: "row" }, saveButton),
    );
  }

  const draftAction = createAction({
    label: "开始拆解",
    variant: "primary",
    icon: "sparkles",
    onClick: () =>
      draft().catch((err) => {
        throw err;
      }),
  });

  return page({
    title: "工作台",
    desc: "把一段经历讲清楚，剩下的交给仓库。全部在本机完成。",
    actions: draftAction.node,
    body: h(
      "div",
      { class: "stack" },
      fb.node,
      card({
        title: "讲一段经历",
        desc: "时间、单位、你负责什么、做出了什么结果——写成一段话即可。",
        body: h(
          "div",
          { class: "stack" },
          inputArea,
          h("div", { class: "row" }, titleField, kindField),
        ),
      }),
      callout({
        tone: "info",
        title: "写清楚这四件事，后面组装就不用返工",
        body: h(
          "ul",
          { class: "plain-list small" },
          h("li", null, "时间与单位：例如「2026.07–2026.10 在杭州拓端数据科技有限公司」，实习与项目分开写。"),
          h("li", null, "你负责什么：写「我做了什么」，不要写「团队做了什么」。"),
          h("li", null, "结果要带数字：完整率 99.7%、覆盖 17 项指标、耗时从 8 小时降到 24 小时内。"),
          h("li", null, "用到的工具：SQL、Python、Excel 透视表——写清是「熟练」还是「用过」。"),
        ),
      }),
      result,
    ),
  });
}

export default render;
