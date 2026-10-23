/** 模板：导入现有简历 → 拆成可重组的槽位；设为默认模板。 */

import { h } from "../components/dom.js";
import { page } from "../components/layout.js";
import { button, callout, card, emptyState, filePicker, statusDot, tabs, textarea } from "../components/primitives.js";
import { api, itemsOf } from "../api.js";
import { describeError, errorText } from "../components/errors.js";

export function render() {
  const draftHost = h("div", { class: "stack" });
  const listHost = h("div", { class: "stack" });
  const statusHost = h("div", null);
  let lang = "zh";

  const paste = textarea({ id: "tpl-paste", rows: 6, placeholder: "也可以直接粘贴简历全文（纯文本/Markdown 都行）" });

  async function loadTemplates() {
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
              items.map((item) =>
                card({
                  title: item.name,
                  desc: `${item.lang === "en" ? "英文" : "中文"} · ${item.page_limit} 页 · ${item.source_kind}`,
                  actions: h(
                    "span",
                    { class: "row" },
                    item.is_default ? statusDot({ level: "ok", label: "默认" }) : button({ label: "设为默认", size: "sm", onClick: () => setDefault(item.id) }),
                  ),
                  body: h("div", { class: "small muted" }, `更新于 ${item.updated_at || ""}`),
                }),
              ),
            )
          : emptyState({ title: "还没有模板", desc: "导入一份现有简历，或直接粘贴全文。" }),
      );
    } catch (err) {
      listHost.replaceChildren(callout({ tone: "danger", title: "读不到模板", body: errorText(err) }));
    }
  }

  async function setDefault(id) {
    try {
      await api.setDefaultTemplate(id);
      await loadTemplates();
    } catch (err) {
      alert(errorText(err));
    }
  }

  async function handleFile(file) {
    statusHost.replaceChildren(callout({ tone: "info", title: `正在解析 ${file.name}…`, body: "全部在本机完成，不上传任何服务器。" }));
    try {
      const data = await api.importFile(file);
      showDraft(data);
    } catch (err) {
      statusHost.replaceChildren(callout({ tone: err.code === "IMPORT_NO_TEXT_LAYER" ? "warn" : "danger", title: "这份文件没法解析", body: errorText(err) }));
    }
  }

  async function handlePaste() {
    const text = String(paste.value || "").trim();
    if (!text) return;
    statusHost.replaceChildren(callout({ tone: "info", title: "正在解析粘贴内容…", body: "本机规则解析。" }));
    try {
      showDraft(await api.importText(text));
    } catch (err) {
      statusHost.replaceChildren(callout({ tone: "danger", title: "解析失败", body: errorText(err) }));
    }
  }

  function showDraft(data) {
    const blocks = data.blocks || [];
    const warnings = data.warnings || [];
    const photo = data.extracted_photo || {};
    const commitButton = button({
      label: "确认为模板",
      variant: "primary",
      icon: "check",
      onClick: async () => {
        commitButton.disabled = true;
        try {
          const result = await api.commitImport(data.import_id, {
            template_name: `${data.lang === "en" ? "英文" : "中文"}-导入-${new Date().toISOString().slice(5, 10)}`,
            lang: data.lang || lang,
            set_default: true,
            also_create_packages: true,
            apply_photo: false,
          });
          statusHost.replaceChildren(
            callout({
              tone: "success",
              title: "模板已保存",
              body: `新建 ${result.blocks_created} 个块；派生经历包 ${(result.packages_created || []).length} 条。照片候选未自动套用，可在「个人资料」确认。`,
            }),
          );
          draftHost.replaceChildren();
          await loadTemplates();
        } catch (err) {
          commitButton.disabled = false;
          statusHost.replaceChildren(callout({ tone: "danger", title: "确认失败", body: errorText(err) }));
        }
      },
    });

    draftHost.replaceChildren(
      card({
        title: `解析出 ${blocks.length} 个块`,
        desc: `${data.parser || "?"} · ${data.stats ? `${data.stats.pages || 1} 页 / ${data.stats.chars || 0} 字` : ""}${photo.available ? " · 检测到照片候选" : ""}`,
        actions: commitButton,
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
      statusHost,
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
