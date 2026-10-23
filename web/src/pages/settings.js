/** 设置：模型路由、key 状态（永不回显）、脱敏开关、联网开关、自检。 */

import { h } from "../components/dom.js";
import { page } from "../components/layout.js";
import { button, callout, card, input, kv, select, statusDot, toggle } from "../components/primitives.js";
import { api } from "../api.js";
import { describeError, errorText } from "../components/errors.js";

export function render() {
  const host = h("div", { class: "stack" });
  const statusHost = h("div", null);

  async function load() {
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
      const flags = {
        autoRedact: Boolean(settings.auto_redact && settings.auto_redact.length),
        allowFetch: settings.allow_web_fetch !== false,
      };
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
            h("div", { class: "row" }, keyField, button({ label: "保存 key", onClick: (ev) => saveKey(ev.currentTarget, keyField.value) })),
            h("div", { class: "row" }, statusDot({ level: settings.key_set ? "ok" : "warn", label: settings.key_set ? "API key 已配置（仅存本机 .env，600 权限）" : "还没有 API key" })),
            h("div", { class: "row" }, button({ label: "测试连接", onClick: (ev) => testProvider(ev.currentTarget) })),
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
          button({
            label: "保存设置",
            variant: "primary",
            onClick: async (ev) => {
              ev.currentTarget.disabled = true;
              try {
                await api.saveSettings({
                  provider: provider.value,
                  model: modelChat.value,
                  model_analysis: modelAnalysis.value,
                  base_url: baseUrl.value,
                  auto_redact: flags.autoRedact ? ["phone", "email", "id", "name"] : ["name"],
                  allow_web_fetch: flags.allowFetch,
                });
                statusHost.replaceChildren(callout({ tone: "success", title: "设置已保存", body: "写入 .env（600）与本地设置表。" }));
                await load();
              } catch (err) {
                statusHost.replaceChildren(callout({ tone: "danger", title: "保存失败", body: errorText(err) }));
              } finally {
                ev.currentTarget.disabled = false;
              }
            },
          }),
          llm ? statusDot({ level: llm.ready ? "ok" : "warn", label: `LLM ${llm.ready ? "就绪" : "未就绪"} · ${llm.model || ""}` }) : null,
        ),
      );
    } catch (err) {
      host.replaceChildren(callout({ tone: "danger", title: "读不到设置", body: errorText(err) }));
    }
  }

  async function saveKey(node, value) {
    if (!String(value || "").trim()) return;
    node.disabled = true;
    try {
      await api.post("/api/v1/settings/api-key", { api_key: String(value).trim() });
      statusHost.replaceChildren(callout({ tone: "success", title: "key 已保存", body: "只写给本机 .env（权限 600），界面不再显示任何片段。" }));
      await load();
    } catch (err) {
      statusHost.replaceChildren(callout({ tone: "danger", title: "保存 key 失败", body: errorText(err) }));
    } finally {
      node.disabled = false;
    }
  }

  async function testProvider(node) {
    node.disabled = true;
    statusHost.replaceChildren(callout({ tone: "info", title: "正在测试连接（5 秒超时）…", body: "" }));
    try {
      const result = await api.post("/api/v1/settings/provider/test", {});
      statusHost.replaceChildren(
        callout({
          tone: result.reachable ? "success" : "danger",
          title: result.reachable ? "连接正常" : "连不上",
          body: kv([
            ["可达", result.reachable ? "是" : "否"],
            ["HTTP", String(result.http_status ?? "—")],
            ["延迟", `${result.latency_ms ?? "—"} ms`],
            ["模型", (result.models || []).join("、") || "—"],
            ["错误码", result.error_code || "—"],
          ]),
        }),
      );
    } catch (err) {
      statusHost.replaceChildren(callout({ tone: "danger", title: "测试失败", body: errorText(err) }));
    } finally {
      node.disabled = false;
    }
  }

  queueMicrotask(load);

  return page({
    title: "设置",
    desc: "唯一的上云出口是模型 API；这里决定它怎么走、发什么。",
    body: h("div", { class: "stack" }, statusHost, host),
  });
}

export default render;
