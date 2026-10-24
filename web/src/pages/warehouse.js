/** 经历库：所有可复用的经历与表述变体（按 bullet_key 分组，标出「待核实」）。 */

import { h } from "../components/dom.js";
import { page } from "../components/layout.js";
import { button, callout, card, emptyState, input, skeleton, stat, statusDot, tabs, toolbar } from "../components/primitives.js";
import { api, itemsOf } from "../api.js";
import { createAction, feedbackRegion, inlineError, optimistic } from "../components/feedback.js";

const KIND_LABEL = { project: "项目", internship: "实习", education: "教育", award: "获奖", activity: "校园", custom: "其他" };
const TONE_LABEL = { original: "原文", impact: "结果导向", technical: "技术细节", leadership: "协作领导", concise: "精简", ats: "ATS" };

export function render() {
  const listHost = h("div", { class: "stack" });
  const statsHost = h("div", { class: "row row--wrap" });
  const search = input({ id: "wh-q", placeholder: "搜经历（支持中文，如：订单）" });
  let filter = "";

  // 反馈区：加载失败 / 乐观回滚说明都落在这里（aria-live 播报，可关闭，带重试）
  const fb = feedbackRegion({ label: "经历库状态" });

  /** 骨架：真实卡片高 148px，槽位固定高度 => 数据到达时列表不跳 */
  function skeletonRows(count = 3) {
    const rows = h("div.ux-skel-rows", { "aria-hidden": "true" });
    for (let i = 0; i < count; i += 1) rows.appendChild(skeleton({ title: true, lines: 3 }));
    const slot = h("div.ux-skel-slot", { "aria-hidden": "true" }, rows);
    slot.style.setProperty("--ux-skel-h", "148px");
    return slot;
  }

  async function load() {
    // 首屏用骨架屏占位；后续搜索/切筛选保留旧列表 + aria-busy，
    // 失败时不清掉用户正在看的内容（R10）
    const first = !listHost.dataset.loaded;
    listHost.setAttribute("aria-busy", "true");
    if (first) listHost.replaceChildren(skeletonRows(3));
    try {
      const query = new URLSearchParams({ limit: "50", include_variants: "1" });
      if (search.value) query.set("q", String(search.value));
      if (filter) query.set("status", filter);
      const data = await api.packages(`?${query.toString()}`);
      const items = itemsOf(data);
      renderStats(items);
      listHost.replaceChildren(
        items.length
          ? h("div", { class: "stack" }, items.map(packageCard))
          : emptyState({
              title: "仓库还是空的",
              desc: "先去工作台讲一段经历，或从「模板」页导入现有简历。",
              actions: h("a", { class: "ui-btn ui-btn--primary", href: "#/workbench" }, "去工作台"),
            }),
      );
      listHost.dataset.loaded = "1";
      listHost.setAttribute("aria-busy", "false");
      fb.idle();
      return { ok: true, count: items.length };
    } catch (err) {
      listHost.setAttribute("aria-busy", "false");
      if (first) listHost.replaceChildren();
      fb.error(err, { onRetry: () => load(), retryable: true, hint: "本机后端可能没起来；点「重试」再读一次。" });
      return { ok: false, error: err };
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
    // 行容器：乐观期间 .ux-row 半透明 + 虚线框；失败回滚时 data-state="error" 红闪一次（1.2s 后清）
    const row = h("div", { class: "row ux-row", style: { gap: "8px", alignItems: "center" } });
    const valueHost = h("span", { class: "row", style: { gap: "8px", alignItems: "center" } });
    const msgHost = h("span", { class: "row", style: { gap: "8px", alignItems: "center" } });
    const action = createAction({ label: "标记核实", size: "sm", variant: "ghost" });
    let previousState = "";

    async function run() {
      const res = await action.run(
        async () => {
          // ① 先本地生效（乐观）：立刻显示已核实，按钮隐去
          previousState = row.dataset.state || "";
          row.dataset.state = "optimistic";
          row.setAttribute("aria-busy", "true");
          msgHost.replaceChildren();
          valueHost.replaceChildren(statusDot({ level: "ok", label: "已核实" }));
          try {
            // ② 再发请求
            await api.patch(`/api/v1/packages/${packageId}/variants/${variant.id}`, { verified: true });
          } catch (error) {
            // ③ 失败回滚：把按钮放回去，行红闪一次
            valueHost.replaceChildren(action.node);
            row.dataset.state = "error";
            window.setTimeout(() => {
              if (row.dataset.state === "error") row.dataset.state = previousState;
            }, 1200);
            throw error;
          } finally {
            row.setAttribute("aria-busy", "false");
          }
        },
      );
      if (res.skipped || res.ok) return;
      // ④ 错误说明挂在**这一行旁边**，同时给反馈区一份（可重试）
      msgHost.replaceChildren(
        inlineError(`没核实成功：${(res.error && res.error.message) || "服务端拒绝了这次修改"}`, {
          onDismiss: () => msgHost.replaceChildren(),
        }),
      );
      fb.error(res.error, {
        retryable: true,
        onRetry: run,
        hint: "这条要点可能已被别的窗口改过；重试会重新提交一次，不会重复建条目。",
      });
    }

    action.node.addEventListener("click", run);
    valueHost.appendChild(action.node);
    row.append(valueHost, msgHost);
    return row;
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
    body: h("div", { class: "stack ux-busy" }, toolbar({ children: statusTabs }), statsHost, fb.node, listHost),
  });
}

export default render;
