/** 模板：导入现有简历 → 拆成可重组的槽位；设为默认模板。 */

import { h } from "../components/dom.js";
import { page } from "../components/layout.js";
import { button, callout, card, emptyState, filePicker, skeleton, statusDot, tabs, textarea } from "../components/primitives.js";
import { api, itemsOf } from "../api.js";
import { createAction, feedbackRegion, inlineError } from "../components/feedback.js";
import { toastWarn } from "../components/toast.js";

export function render() {
  const draftHost = h("div", { class: "stack" });
  const listHost = h("div", { class: "stack" });
  const fb = feedbackRegion({ label: "模板导入状态" });
  let lang = "zh";
  let defaultId = "";
  /** id -> { host, action }：设为默认的乐观更新要能原地换标记 */
  const markers = new Map();

  function skeletonRows(count = 2) {
    const rows = h("div.ux-skel-rows", { "aria-hidden": "true" });
    for (let i = 0; i < count; i += 1) rows.appendChild(skeleton({ title: true, lines: 2 }));
    const slot = h("div.ux-skel-slot", { "aria-hidden": "true" }, rows);
    slot.style.setProperty("--ux-skel-h", "120px");
    return slot;
  }

  function paintDefault(targetId, optimistic = false) {
    for (const [id, entry] of markers) {
      if (id === targetId) {
        entry.host.replaceChildren(
          statusDot({ level: "ok", label: optimistic ? "设为默认中…" : "默认" }),
        );
      } else {
        entry.host.replaceChildren(entry.action.node);
        entry.action.reset();
      }
    }
  }

  const paste = textarea({ id: "tpl-paste", rows: 6, placeholder: "也可以直接粘贴简历全文（纯文本/Markdown 都行）" });

  async function loadTemplates() {
    const first = !listHost.dataset.loaded;
    listHost.setAttribute("aria-busy", "true");
    if (first) listHost.replaceChildren(skeletonRows(2));
    try {
      const data = await api.templates(lang);
      const items = itemsOf(data);
      const resolved = data.resolved_default;
      listHost.replaceChildren(
        items.length
          ? h(
              "div",
              { class: "stack" },
              resolved ? callout({ tone: "info", title: "当前默认模板", body: `${resolved.name}（${resolved.lang}）` }) : callout({ tone: "warn", title: "还没有默认模板", body: "导入一份简历并「确认为模板」后，它就会成为默认。" }),
              items.map((item) => {
                const markerHost = h("span", { class: "row", style: { gap: "6px", alignItems: "center" } });
                const action = createAction({ label: "设为默认", size: "sm" });
                action.node.addEventListener("click", () => setDefault(item.id, action));
                markers.set(item.id, { host: markerHost, action });
                if (item.is_default) {
                  defaultId = item.id;
                  markerHost.replaceChildren(statusDot({ level: "ok", label: "默认" }));
                } else {
                  markerHost.replaceChildren(action.node);
                }
                return card({
                  title: item.name,
                  desc: `${item.lang === "en" ? "英文" : "中文"} · ${item.page_limit} 页 · ${item.source_kind}`,
                  actions: h("span", { class: "row" }, markerHost),
                  body: h("div", { class: "small muted" }, `更新于 ${item.updated_at || ""}`),
                });
              }),
            )
          : emptyState({
              title: "还没有模板",
              desc: "导入一份现有简历，或直接粘贴全文。",
              actions: h("a", { class: "ui-btn ui-btn--secondary", href: "#/profile" }, "先去补个人资料"),
            }),
      );
      listHost.dataset.loaded = "1";
      listHost.setAttribute("aria-busy", "false");
      fb.idle();
    } catch (err) {
      listHost.setAttribute("aria-busy", "false");
      if (!listHost.dataset.loaded) listHost.replaceChildren();
      fb.error(err, { onRetry: () => loadTemplates(), retryable: true, hint: "本机后端可能没起来；点「重试」再读一次。" });
    }
  }

  /**
   * 设为默认：乐观更新（先把「默认」标记挪过来），失败回滚到原来那个。
   * 服务端幂等，重试不会造成两个默认模板。
   */
  async function setDefault(id, action) {
    const previous = defaultId;
    const res = await action.run(async () => {
      paintDefault(id, true);
      try {
        await api.setDefaultTemplate(id);
        defaultId = id;
        paintDefault(id, false);
        return true;
      } catch (error) {
        defaultId = previous;
        paintDefault(previous, false);
        throw error;
      }
    });
    if (res.skipped || res.ok) return;
    fb.error(res.error, {
      retryable: true,
      onRetry: () => setDefault(id, action),
      hint: "默认模板没换成功，列表已回滚；重试会再提交一次。",
    });
  }

  async function handleFile(file) {
    fb.pending(`正在解析 ${file.name}`, "全部在本机完成，不上传任何服务器。");
    try {
      const data = await api.importFile(file);
      showDraft(data);
      fb.success({
        title: "解析完成",
        body: `解析出 ${(data.blocks || []).length} 个块${data.parser ? ` · ${data.parser}` : ""}。确认无误后点「确认为模板」。`,
      });
    } catch (err) {
      fb.error(err, {
        retryable: err && err.code !== "IMPORT_NO_TEXT_LAYER",
        retryNote: err && err.code === "IMPORT_NO_TEXT_LAYER" ? "" : undefined,
        hint:
          err && err.code === "IMPORT_NO_TEXT_LAYER"
            ? "这份 PDF 没有文字层（多半是扫描件），换一份可选中的 PDF，或把正文粘贴到下面的输入框。"
            : "换一份文件，或改用下方「粘贴全文」。",
      });
    }
  }

  async function handlePaste() {
    const text = String(paste.value || "").trim();
    if (!text) {
      // 空粘贴不许静默 return（UI-REFRESH §3.2）
      toastWarn("还没有内容", { message: "把简历正文粘贴到下面的输入框，再点「解析粘贴内容」。" });
      fb.error(
        { code: "EMPTY_SELECTION", message: "粘贴框是空的。" },
        { retryable: false, hint: "先粘贴简历正文（纯文本或 Markdown 都行），再点解析。" },
      );
      try {
        paste.focus({ preventScroll: true });
        paste.scrollIntoView({ block: "nearest" });
      } catch {
        /* 忽略 */
      }
      return;
    }
    fb.pending("正在解析粘贴内容", "本机规则解析，不联网。");
    try {
      const data = await api.importText(text);
      showDraft(data);
      fb.success({
        title: "解析完成",
        body: `解析出 ${(data.blocks || []).length} 个块。确认无误后点「确认为模板」。`,
      });
    } catch (err) {
      fb.error(err, { retryable: true, hint: "内容可能是空行太多或格式不认识；精简后重试。" });
    }
  }

  function showDraft(data) {
    const blocks = data.blocks || [];
    const warnings = data.warnings || [];
    const photo = data.extracted_photo || {};
    const commitAction = createAction({
      label: "确认为模板",
      variant: "primary",
      icon: "check",
      onClick: () => commitDraft(data),
    });

    async function commitDraft(draft) {
      fb.pending("正在保存模板", "写本机数据库；会同时派生可复用的经历包。");
      try {
        const result = await api.commitImport(draft.import_id, {
          template_name: `${draft.lang === "en" ? "英文" : "中文"}-导入-${new Date().toISOString().slice(5, 10)}`,
          lang: draft.lang || lang,
          set_default: true,
          also_create_packages: true,
          apply_photo: false,
        });
        fb.success({
          title: "模板已保存",
          body: `新建 ${result.blocks_created} 个块；派生经历包 ${(result.packages_created || []).length} 条。照片候选未自动套用，可在「个人资料」确认。`,
        });
        draftHost.replaceChildren();
        await loadTemplates();
        return result;
      } catch (err) {
        // 解析结果还在草稿区，用户可以再点一次「确认为模板」（导入单幂等）
        fb.error(err, {
          retryable: true,
          onRetry: () => commitDraft(draft),
          hint: "草稿还在上面，可以直接重试；重复确认不会生成两份模板。",
        });
        throw err;
      }
    }

    draftHost.replaceChildren(
      card({
        title: `解析出 ${blocks.length} 个块`,
        desc: `${data.parser || "?"} · ${data.stats ? `${data.stats.pages || 1} 页 / ${data.stats.chars || 0} 字` : ""}${photo.available ? " · 检测到照片候选" : ""}`,
        actions: commitAction.node,
        body: h(
          "div",
          { class: "stack" },
          warnings.length
            ? callout({ tone: "warn", title: "解析提示", body: h("ul", null, warnings.map((w) => h("li", null, `${w.code}：${w.message || ""}${w.count ? `（${w.count}）` : ""}`))) })
            : null,
          h(
            "div",
            { class: "stack" },
            blocks.map((block) =>
              h(
                "div",
                { class: "row", style: { gap: "8px", alignItems: "baseline" } },
                h("span", { class: "chip chip--sm" }, block.block_type),
                h("strong", null, block.heading || "(无标题)"),
                h("span", { class: "small muted", style: { flex: "1" } }, (block.preview_text || "").slice(0, 80)),
                h("span", { class: "small muted" }, `槽位 ${(block.slots || []).length}`),
              ),
            ),
          ),
        ),
      }),
    );
  }

  queueMicrotask(loadTemplates);

  return page({
    title: "模板",
    desc: "导入一份现有简历，拆成可重组的槽位；确认后才成为可用模板。",
    actions: tabs({
      label: "语言",
      value: lang,
      items: [
        { id: "zh", label: "中文" },
        { id: "en", label: "English" },
      ],
      onChange: (id) => {
        lang = id;
        loadTemplates();
      },
    }),
    body: h(
      "div",
      { class: "stack" },
      fb.node,
      card({
        title: "导入简历",
        desc: "PDF / DOCX / Markdown / TXT 都行；扫描件没有文字层会明确告诉你。",
        body: h(
          "div",
          { class: "stack" },
          filePicker({ accept: ".pdf,.docx,.md,.txt,.markdown", onSelect: handleFile, label: "选择文件" }),
          paste,
          h("div", { class: "row" }, button({ label: "解析粘贴内容", onClick: handlePaste })),
        ),
      }),
      draftHost,
      card({ title: "已保存的模板", body: listHost }),
    ),
  });
}

export default render;
