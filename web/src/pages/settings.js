/** 设置：模型路由、key 状态（永不回显）、脱敏开关、联网开关、自检。 */

import { h } from "../components/dom.js";
import { page } from "../components/layout.js";
import { button, callout, card, input, kv, select, skeleton, statusDot, toggle } from "../components/primitives.js";
import { api } from "../api.js";
import { describeError, errorText } from "../components/errors.js";
import { createAction, feedbackRegion } from "../components/feedback.js";
import { toastWarn } from "../components/toast.js";

export function render() {
  const host = h("div", { class: "stack" });
  const statusHost = h("div", null);
  // 反馈区：保存 key / 测试连接 / 保存设置 的四态与失败说明
  const fb = feedbackRegion({ label: "设置保存状态" });

  const flagsRef = { autoRedact: false, allowFetch: true };
  /** 三个动作按钮在 render 作用域里只建一次：切语言/重载不会堆叠监听 */
  const saveKeyAction = createAction({
    label: "保存 key",
    onClick: () => {
      const field = document.getElementById("st-key");
      return saveKey(field ? field.value : "").catch((err) => {
        fb.error(err, {
          retryable: true,
          onRetry: () => saveKeyAction.run(() => saveKey(document.getElementById("st-key")?.value || "")),
          hint: "key 没有被写坏；重新粘一次再保存。",
        });
        throw err;
      });
    },
  });
  const testAction = createAction({ label: "测试连接", onClick: () => testProvider() });
  const saveSettingsAction = createAction({
    label: "保存设置",
    variant: "primary",
    onClick: () =>
      saveSettings().catch((err) => {
        fb.error(err, {
          retryable: true,
          onRetry: () => saveSettings(),
          hint: "表单内容还在；改完再点一次保存。",
        });
        throw err;
      }),
  });

  async function load() {
    if (!host.dataset.loaded) {
      const slot = h("div.ux-skel-slot", { "aria-hidden": "true" }, skeleton({ title: true, lines: 5 }));
      slot.style.setProperty("--ux-skel-h", "360px");
      host.replaceChildren(slot);
    }
    try {
      const [settings, llm] = await Promise.all([api.settings(), api.llmStatus().catch(() => null)]);
      const provider = select({
        id: "st-provider",
        value: settings.provider,
        options: [
          { value: "deepseek", label: "DeepSeek" },
          { value: "openai_compatible", label: "OpenAI 兼容" },
          { value: "off", label: "关闭（只用本地能力）" },
        ],
      });
      const modelChat = input({ id: "st-model", value: settings.model || "" });
      const modelAnalysis = input({ id: "st-model-analysis", value: settings.model_analysis || "" });
      const baseUrl = input({ id: "st-base", value: settings.base_url || "" });
      const keyField = input({ id: "st-key", type: "password", placeholder: settings.key_set ? "已保存（不回显，留空表示不改）" : "sk-…" });
      flagsRef.autoRedact = Boolean(settings.auto_redact && settings.auto_redact.length);
      flagsRef.allowFetch = settings.allow_web_fetch !== false;
      const flags = flagsRef;
      const autoRedact = toggle({
        checked: flags.autoRedact,
        label: "自动脱敏电话/邮箱",
        onChange: (on) => {
          flags.autoRedact = on;
        },
      });
      const allowFetch = toggle({
        checked: flags.allowFetch,
        label: "允许抓取公司公开页面（只读、可关）",
        onChange: (on) => {
          flags.allowFetch = on;
        },
      });

      host.replaceChildren(
        card({
          title: "模型路由",
          desc: "对话/改写走 CHAT 模型，JD 解析、公司偏好、匹配与组装策略走 ANALYSIS 模型。",
          body: h(
            "div",
            { class: "stack" },
            h("div", { class: "row" }, provider, baseUrl),
            h("div", { class: "row" }, modelChat, modelAnalysis),
            h("div", { class: "row" }, keyField, saveKeyAction.node),
            h("div", { class: "row" }, statusDot({ level: settings.key_set ? "ok" : "warn", label: settings.key_set ? "API key 已配置（仅存本机 .env，600 权限）" : "还没有 API key" })),
            h("div", { class: "row" }, testAction.node),
          ),
        }),
        card({
          title: "隐私",
          desc: "姓名永远脱敏；电话/邮箱默认脱敏，关掉后本机身份校验仍会拦住它们。",
          body: h(
            "div",
            { class: "stack" },
            autoRedact,
            allowFetch,
            h("div", { class: "small muted" }, "照片与原始简历文件永不进入模型请求；每次调用前都会先给你看字段清单。"),
          ),
        }),
        card({
          title: "本地状态",
          body: kv([
            ["数据目录", settings.data_root || "—"],
            ["端口", String(settings.app_port || "")],
            ["对话模型", settings.model || "—"],
            ["分析模型", settings.model_analysis || "—"],
            ["LLM 就绪", settings.ready ? "是" : `否${settings.not_ready_reason ? `（${settings.not_ready_reason}）` : ""}`],
            ["允许出网主机", (settings.allowed_hosts || []).join("、")],
            ["上次自检", settings.llm_last_check_at || "—"],
          ]),
        }),
        h(
          "div",
          { class: "row" },
          saveSettingsAction.node,
          llm ? statusDot({ level: llm.ready ? "ok" : "warn", label: `LLM ${llm.ready ? "就绪" : "未就绪"} · ${llm.model || ""}` }) : null,
        ),
      );
    } catch (err) {
      host.replaceChildren(callout({ tone: "danger", title: "读不到设置", body: errorText(err) }));
    }
  }

  async function saveKey(value) {
    if (!String(value || "").trim()) {
      // 空 key 不许静默 return（B7）
      toastWarn("还没填 key", { message: "把 API key 填进左边的密码框，再点「保存 key」。" });
      fb.error(
        { code: "VALIDATION_ERROR", message: "API key 是空的。" },
        { retryable: false, hint: "把 key 粘到「模型路由」卡片里的密码框，再点「保存 key」。已保存过的 key 不回显，留空表示不改。" },
      );
      try {
        const field = document.getElementById("st-key");
        if (field) field.focus({ preventScroll: true });
      } catch {
        /* 忽略 */
      }
      return { ok: false, skipped: true };
    }
    fb.pending("正在保存 key", "只写给本机 .env（权限 600）。");
    await api.post("/api/v1/settings/api-key", { api_key: String(value).trim() });
    fb.success({ title: "key 已保存", body: "只写给本机 .env（权限 600），界面不再显示任何片段。", announce: "密钥已保存" });
    await load();
    return { ok: true };
  }

  async function testProvider() {
    fb.pending("正在测试连接", "5 秒超时；失败不影响已保存的设置。");
    const result = await api.post("/api/v1/settings/provider/test", {});
    if (result.reachable) {
      fb.success({
        title: "连接正常",
        body: `HTTP ${result.http_status ?? "—"} · ${result.latency_ms ?? "—"} ms · 模型 ${(result.models || []).join("、") || "—"}`,
        announce: "连接正常",
      });
      return result;
    }
    fb.error(
      { code: result.error_code || "LLM_UPSTREAM", message: `连不上模型服务（HTTP ${result.http_status ?? "—"}）。` },
      {
        retryable: true,
        onRetry: () => testAction.run(runTest),
        hint: "检查 base_url 与 key 是否匹配；改完点「保存 key」再测一次。",
      },
    );
    return result;
  }

  async function runTest() {
    return testProvider();
  }

  async function saveSettings() {
    fb.pending("正在保存设置", "写 .env（600）与本地设置表。");
    const provider = document.getElementById("st-provider");
    const baseUrl = document.getElementById("st-base");
    const modelChat = document.getElementById("st-model");
    const modelAnalysis = document.getElementById("st-model-analysis");
    await api.saveSettings({
      provider: provider ? provider.value : undefined,
      model: modelChat ? modelChat.value : undefined,
      model_analysis: modelAnalysis ? modelAnalysis.value : undefined,
      base_url: baseUrl ? baseUrl.value : undefined,
      auto_redact: flagsRef.autoRedact ? ["phone", "email", "id", "name"] : ["name"],
      allow_web_fetch: flagsRef.allowFetch,
    });
    fb.success({ title: "设置已保存", body: "写入 .env（600）与本地设置表；顶栏的 AI 状态会立刻重新检查。", announce: "设置已保存" });
    // 保存后让顶栏重新探测（痛点 ④：保存了却还是「未就绪」）
    window.dispatchEvent(new CustomEvent("rw:status", { detail: { ai: "checking" } }));
    await load();
    if (typeof window.__rw?.probeStatus === "function") window.__rw.probeStatus();
    return { ok: true };
  }

  queueMicrotask(load);

  return page({
    title: "设置",
    desc: "唯一的上云出口是模型 API；这里决定它怎么走、发什么。",
    body: h("div", { class: "stack" }, fb.node, statusHost, host),
  });
}

export default render;
