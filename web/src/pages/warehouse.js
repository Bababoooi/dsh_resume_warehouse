/** 经历库：所有可复用的经历与表述变体（按 bullet_key 分组，标出「待核实」）。 */

import { h } from "../components/dom.js";
import { page } from "../components/layout.js";
import { button, callout, card, emptyState, input, stat, statusDot, tabs, toolbar } from "../components/primitives.js";
import { api, itemsOf } from "../api.js";
import { describeError, errorText } from "../components/errors.js";

const KIND_LABEL = { project: "项目", internship: "实习", education: "教育", award: "获奖", activity: "校园", custom: "其他" };
const TONE_LABEL = { original: "原文", impact: "结果导向", technical: "技术细节", leadership: "协作领导", concise: "精简", ats: "ATS" };

export function render() {
  const listHost = h("div", { class: "stack" });
  const statsHost = h("div", { class: "row row--wrap" });
  const search = input({ id: "wh-q", placeholder: "搜经历（支持中文，如：订单）" });
  let filter = "";

  async function load() {
    listHost.replaceChildren(callout({ tone: "info", title: "加载中…", body: "读取本机仓库" }));
    try {
      const query = new URLSearchParams({ limit: "50", include_variants: "1" });
      if (search.value) query.set("q", String(search.value));
      if (filter) query.set("status", filter);
      const data = await api.packages(`?${query.toString()}`);
      const items = itemsOf(data);
      renderStats(items);
      listHost.replaceChildren(items.length ? h("div", { class: "stack" }, items.map(packageCard)) : emptyState({ title: "仓库还是空的", desc: "先去工作台讲一段经历，或从「模板」页导入现有简历。" }));
    } catch (err) {
      listHost.replaceChildren(callout({ tone: "danger", title: "读不到经历库", body: errorText(err) }));
    }
  }

  function renderStats(items) {
    const variants = items.reduce((sum, item) => sum + ((item.variants || []).length), 0);
    const unverified = items.filter((item) => item.status !== "ready").length;
    statsHost.replaceChildren(
      stat({ label: "经历", value: items.length }),
      stat({ label: "表述变体", value: variants }),
      stat({ label: "待核实", value: unverified }),
      stat({ label: "可复用", value: items.filter((item) => item.status === "ready").length }),
    );
  }

  function packageCard(item) {
    const variants = item.variants || [];
    const groups = new Map();
    for (const variant of variants) {
      const key = variant.bullet_key || "b1";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(variant);
    }

    const statusNode =
      item.status === "ready"
        ? statusDot({ level: "ok", label: "可复用" })
        : statusDot({ level: "warn", label: "待核实" });

    return card({
      title: h("span", null, item.title, " ", h("span", { class: "small muted" }, ` ${KIND_LABEL[item.kind] || item.kind}`)),
      desc: [item.org, item.role, item.start_date || item.end_date ? `${item.start_date || "?"} - ${item.is_current ? "至今" : item.end_date || "?"}` : ""]
        .filter(Boolean)
        .join(" · "),
      actions: h("span", { class: "row" }, statusNode),
      body: h(
        "div",
        { class: "stack" },
        groups.size
          ? Array.from(groups.entries()).map(([bulletKey, rows]) =>
              h(
                "div",
                { class: "stack", style: { gap: "4px" } },
                h("div", { class: "small muted" }, bulletKey),
                rows.map((variant) =>
                  h(
                    "div",
                    { class: "row", style: { gap: "8px", alignItems: "flex-start" } },
                    h("span", { class: "chip chip--sm" }, TONE_LABEL[variant.tone] || variant.tone),
                    h("span", { style: { flex: "1" } }, variant.text),
                    h("span", { class: "small muted" }, `${variant.char_len || String(variant.text || "").length} 字`),
                    variant.verified ? statusDot({ level: "ok", label: "已核实" }) : verifyButton(item.id, variant),
                  ),
                ),
              ),
            )
          : h("div", { class: "small muted" }, "这条还没有要点——去工作台补几句。"),
        h(
          "div",
          { class: "row" },
          statusDot({
            level: item.status === "ready" ? "ok" : "idle",
            label: item.status === "ready" ? "可直接用于组装" : "核实至少一条要点后才能用于组装",
          }),
        ),
      ),
    });
  }

  function verifyButton(packageId, variant) {
    return button({
      label: "标记核实",
      size: "sm",
      variant: "ghost",
      onClick: async (ev) => {
        const node = ev.currentTarget;
        node.disabled = true;
        try {
          await api.patch(`/api/v1/packages/${packageId}/variants/${variant.id}`, { verified: true });
          await load();
        } catch (err) {
          node.disabled = false;
          alert(errorText(err));
        }
      },
    });
  }

  const searchButton = button({ label: "搜索", onClick: load });
  search.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") load();
  });

  const statusTabs = tabs({
    label: "状态筛选",
    value: "",
    items: [
      { id: "", label: "全部" },
      { id: "draft", label: "待核实" },
      { id: "ready", label: "可复用" },
      { id: "archived", label: "已归档" },
    ],
    onChange: (id) => {
      filter = id;
      load();
    },
  });

  queueMicrotask(load);

  return page({
    title: "经历库",
    desc: "每条经历配多条表述变体，组装时按岗位挑最合适的那条。",
    actions: h("span", { class: "row" }, search, searchButton),
    body: h("div", { class: "stack" }, toolbar({ children: statusTabs }), statsHost, listHost),
  });
}

export default render;
