/** 个人资料：文件名里出现的姓名/校名就是这里的两行；右侧实时显示导出名。 */

import { h } from "../components/dom.js";
import { page } from "../components/layout.js";
import { button, callout, card, emptyState, input, kv, skeleton, statusDot, textarea, toggle } from "../components/primitives.js";
import { api } from "../api.js";
import { errorText } from "../components/errors.js";
import { createAction, feedbackRegion } from "../components/feedback.js";

const FIELDS = [
  ["name_zh", "中文姓名", "决定中文简历的文件名"],
  ["name_en", "英文姓名", "决定英文简历的文件名（建议全大写）"],
  ["school_zh", "中文校名", "决定中文简历的文件名；缺失会直接挡住导出"],
  ["school_en", "英文校名", "决定英文简历的文件名"],
  ["degree", "学历", "本科 / 硕士 / 博士"],
  ["major", "专业", ""],
  ["grad_year", "毕业年份", "四位数"],
  ["phone", "手机号", "永不发送给模型"],
  ["email", "邮箱", "永不发送给模型"],
  ["city", "城市", ""],
  // 到岗时间：中文原文是真值（渲染页眉第三行），英文表述写 extra，留空则回退中文值
  ["available_note", "到岗时间（中文）", "简历页眉第三行用它，如：2027年1月下旬"],
  ["available_note_en", "到岗时间（英文，可选）", "英文模板用；留空则自动用上面的中文值", "extra"],
];

export function render() {
  const formHost = h("div", { class: "stack" });
  const namingHost = h("div", null);
  const statusHost = h("div", null);
  // 反馈区：保存结果、失败与「下一步」都落在这里（aria-live 播报，可关闭）
  const fb = feedbackRegion({ label: "个人资料保存状态" });
  const inputs = {};
  let profileExtra = {};

  // 命名实时预览的防抖句柄：以前每敲一个键就发一次请求（B6）
  let namingTimer = 0;
  let namingSeq = 0;

  function scheduleNaming(delay = 300) {
    window.clearTimeout(namingTimer);
    namingTimer = window.setTimeout(() => refreshNaming(), delay);
  }

  async function load() {
    if (!formHost.dataset.loaded) {
      const slot = h("div.ux-skel-slot", { "aria-hidden": "true" }, skeleton({ title: true, lines: 4 }));
      slot.style.setProperty("--ux-skel-h", "288px");
      formHost.replaceChildren(slot);
    }
    try {
      const profile = await api.profile();
      profileExtra = profile.extra || {};
      formHost.replaceChildren(
        ...FIELDS.map(([key, label, hint, scope]) => {
          const initial = scope === "extra" ? (profile.extra || {})[key] ?? "" : profile[key] ?? "";
          const field = input({ id: `pf-${key}`, value: initial, placeholder: hint || "" });
          inputs[key] = field;
          field.addEventListener("input", () => scheduleNaming(300));
          return h(
            "label",
            { class: "field" },
            h("span", { class: "field__label" }, label),
            field,
            hint ? h("span", { class: "field__hint small muted" }, hint) : null,
          );
        }),
        h("div", { class: "row" }, photoToggle(profile), saveButton()),
      );
      renderMeta(profile);
      await loadEducationFacts();
      await refreshNaming();
    } catch (err) {
      formHost.replaceChildren(callout({ tone: "danger", title: "读不到个人资料", body: errorText(err) }));
    }
  }

  const factsHost = h("div", { class: "stack" });

  /** 教育段补充（GPA / 主修课程）：只改默认模板里那两行，不碰模板其他部分。 */
  async function loadEducationFacts() {
    try {
      const data = await api.educationFacts();
      const box = textarea({
        id: "pf-education-facts",
        rows: 3,
        value: (data.lines || []).join("\n"),
        placeholder: "专业成绩：GPA 3.56/4 86.53/100 CET4：562 CET6:508",
      });
      factsHost.replaceChildren(
        card({
          title: "教育段补充（GPA / 主修课程）",
          desc: data.template_name
            ? `写在默认模板「${data.template_name}」的教育段里；一行一条，导出即用。`
            : "还没有模板——先导入一份简历，这里就能编辑了。",
          body: h(
            "div",
            { class: "stack" },
            box,
            h(
              "div",
              { class: "row" },
              button({
                label: "保存补充行",
                variant: "secondary",
                size: "sm",
                disabled: !data.template_id,
                onClick: async () => {
                  const lines = String(box.value || "").split("\n").map((x) => x.trim()).filter(Boolean);
                  try {
                    const saved = await api.saveEducationFacts(lines);
                    const snap = saved.snapshot || {};
                    factsHost.replaceChildren(
                      callout({
                        tone: "success",
                        title: "教育段已更新",
                        body: `共 ${saved.lines.length} 行；改前快照：${snap.path || "—"}（md5 ${String(snap.md5 || "").slice(0, 12)}…）。重新导出后生效。`,
                      }),
                      ...factsHost.children,
                    );
                  } catch (err) {
                    factsHost.replaceChildren(callout({ tone: "danger", title: "保存失败", body: errorText(err) }));
                  }
                },
              }),
              h("span", { class: "small muted" }, "清空后该段不再出现这两行"),
            ),
          ),
        }),
      );
    } catch (err) {
      factsHost.replaceChildren(callout({ tone: "warn", title: "读不到教育段补充行", body: errorText(err) }));
    }
  }

  function renderMeta(profile) {
    const missing = profile.missing || [];
    statusHost.replaceChildren(
      missing.length
        ? callout({ tone: "warn", title: `还差 ${missing.length} 项`, body: `缺：${missing.join("、")}。缺姓名或校名会直接导致导出失败（不产残缺文件名）。` })
        : callout({ tone: "success", title: "资料齐全", body: "姓名、校名、联系方式都在——导出时不会再问你要。" }),
    );
  }

  function photoToggle(profile) {
    return statusDot({
      level: profile.photo_path ? "ok" : "idle",
      label: profile.photo_path ? `照片已设置（${profile.photo_path}）` : "未设置照片",
    });
  }

  function saveButton() {
    const action = createAction({
      label: "保存",
      variant: "primary",
      onClick: () => saveProfile(),
    });
    return action.node;
  }

  async function saveProfile() {
    fb.pending("正在保存资料", "只写本机数据库；姓名与联系方式不会因此离开本机。");
    try {
      {
        {
          const patch = {};
          const extraPatch = { ...(profileExtra || {}) };
          for (const [key, , , scope] of FIELDS) {
            const value = String(inputs[key].value ?? "").trim();
            if (scope === "extra") {
              if (value) extraPatch[key] = value;
              else delete extraPatch[key];
              continue;
            }
            if (key === "grad_year") patch[key] = value ? Number(value) : null;
            else patch[key] = value || null;
          }
          // 只在真的有英文表述时整体回写 extra，避免把别的 extra 字段冲掉
          patch.extra = extraPatch;
          const saved = await api.saveProfile(patch);
          renderMeta(saved);
          const stamp = new Date().toLocaleTimeString("zh-CN", { hour12: false });
          fb.success({
            title: `已保存 · ${stamp}`,
            body: `姓名「${String(inputs.name_zh.value || "").trim() || "—"}」、校名「${String(inputs.school_zh.value || "").trim() || "—"}」已写入本机；导出文件名会立刻用新值。`,
            announce: "资料已保存",
          });
          await refreshNaming();
          return saved;
        }
      }
    } catch (err) {
      fb.error(err, {
        retryable: true,
        onRetry: () => saveProfile(),
        hint: "表单里的内容没被清掉；改完上面提示的字段再点一次保存即可。",
      });
      // 把焦点送到第一个被服务端拒绝的字段（字段名从 details/errors 里取）
      const firstBad = (err && err.details && (err.details.field || (Array.isArray(err.details.errors) && err.details.errors[0] && err.details.errors[0].field))) || "";
      const target = firstBad ? inputs[firstBad] : null;
      if (target && typeof target.focus === "function") {
        try {
          target.focus({ preventScroll: true });
          target.scrollIntoView({ block: "center" });
        } catch {
          /* 忽略 */
        }
      }
      throw err;
    }
  }

  async function refreshNaming() {
    try {
      const [zh, en] = await Promise.all([
        api.validateNaming({
          pattern: "{position}-{name}-{school}",
          lang: "zh",
          position: String(inputs.name_zh?.value ? "数据分析实习生" : "数据分析实习生"),
        }),
        api.validateNaming({ pattern: "{position}-{name}-{school}", lang: "en", position: "Data Analyst Intern" }),
      ]);
      namingHost.replaceChildren(
        card({
          title: "导出文件名预览",
          desc: "命名模板：{position}-{name}-{school}（姓名与校名来自上面的输入框）",
          body: kv([
            ["中文", zh.filename || errorsText(zh)],
            ["English", en.filename || errorsText(en)],
            [
              "来源",
              (zh.variables || [])
                .map((v) => `${v.name}=${v.value}（${v.source}）`)
                .join(" · ") || "—",
            ],
          ]),
        }),
      );
    } catch (err) {
      namingHost.replaceChildren(callout({ tone: "warn", title: "命名预览失败", body: errorText(err) }));
    }
  }

  function errorsText(result) {
    const errors = result.errors || [];
    if (!errors.length) return "—";
    return `不可用：${errors.map((e) => e.code).join("、")}`;
  }

  queueMicrotask(load);

  return page({
    title: "个人资料",
    desc: "这里填的姓名/校名会直接出现在导出文件名里；联系方式永不发送给模型。",
    body: h(
      "div",
      { class: "stack" },
      fb.node,
      statusHost,
      card({ title: "基本信息", body: formHost }),
      factsHost,
      namingHost,
    ),
  });
}

export default render;
