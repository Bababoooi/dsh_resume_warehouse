/**
 * errors.js — 错误码 → 人话（AC-UI-09：按 error.code 分支，绝不把 JSON 原样丢给用户）
 *
 * 码表与 docs/API-CONTRACT.md §14 对齐；未知码回退到「服务端返回了未分类错误」，
 * 同时保留原码作为「技术细节」供排查，而不是当正文。
 */

import { h } from "./dom.js";
import { icon } from "./icons.js";
import { callout } from "./primitives.js";

/** code → {title, body?, hint?, action?} */
export const ERROR_COPY = {
  VALIDATION_ERROR: {
    title: "提交的内容有问题",
    hint: "检查标红的字段后重试；错误项已在表单里标出。",
  },
  BAD_REQUEST: { title: "请求格式不对", hint: "这通常是前端 bug，请刷新页面重试。" },
  NOT_FOUND: { title: "找不到这条数据", hint: "可能已被删除；返回列表刷新一下。" },
  CONFLICT: { title: "数据已被改动", hint: "刷新后重新操作，避免覆盖别人的修改。" },
  INTERNAL: { title: "本地服务出错了", hint: "看一下终端里的 traceback，或重启服务。" },

  NAMING_UNKNOWN_VAR: {
    title: "命名模板里有不认识的变量",
    hint: "可用变量：{position} {company} {name} {school} {date} {version} {lang}。",
  },
  NAMING_MISSING_VAR: {
    title: "缺少命名需要的字段",
    hint: "去「个人资料」补齐姓名/学校；缺字段时不会生成残缺文件名。",
    action: "profile",
  },
  NAMING_EMPTY: { title: "命名模板是空的", hint: "恢复默认 {position}-{name}-{school}。" },
  NAMING_TOO_LONG: { title: "文件名太长", hint: "精简模板，保留 120 字符以内。" },
  NAMING_SYNTAX: { title: "模板语法有问题", hint: "大括号要成对出现，例如 {name}。" },
  NAMING_INVALID_CHARS: {
    title: "文件名含不允许的字符",
    hint: "不能出现 / \\ : * ? \" < > | 这些字符；中文与空格是允许的。",
  },

  IMPORT_UNSUPPORTED: { title: "不支持这个文件类型", hint: "目前支持 PDF 与 DOCX。" },
  IMPORT_TOO_LARGE: { title: "文件太大", hint: "单份简历建议 10MB 以内。" },
  IMPORT_NO_TEXT: {
    title: "这份 PDF 里没有可提取的文字",
    hint: "扫描件需要先 OCR；可以换一份可复制文字的版本。",
  },
  IMPORT_PARSE_FAILED: { title: "解析失败", hint: "换一份文件，或把简历转成 DOCX 再试。" },
  TEMPLATE_INVALID: { title: "模板结构不合法", hint: "回到模板页修好槽位再组装。" },
  MISSING_SLOTS: { title: "模板有槽位没有内容", hint: "补齐内容，或确认该槽位可留空。" },
  EMPTY_SELECTION: { title: "还没选任何经历", hint: "左栏至少勾选一条经历。" },

  LLM_NOT_CONFIGURED: {
    title: "还没配置模型",
    hint: "去设置页确认已填入 DeepSeek API Key。",
    action: "settings",
  },
  LLM_AUTH: {
    title: "密钥被拒绝",
    hint: "密钥可能已过期或填错，请到设置页更新后重试。",
    action: "settings",
  },
  LLM_RATE_LIMIT: { title: "请求太频繁", hint: "等一分钟再试，或减少一次发送的字段。" },
  LLM_TIMEOUT: { title: "模型响应超时", hint: "重试；若经常超时，改用本地模型或缩短 JD 文本。" },
  LLM_UPSTREAM: { title: "上游服务出错", hint: "稍后重试；不影响本地已保存的内容。" },
  LLM_BAD_RESPONSE: {
    title: "模型返回的内容无法解析",
    hint: "重试一次；仍失败可换模型，或在附加要求里指定输出格式。",
  },
  LLM_CONTENT_REJECTED: {
    title: "这次请求被服务商拒绝",
    hint: "可逐个取消勾选字段后重试，或先在本地删掉可疑内容。",
  },
  CONSENT_EXPIRED: { title: "发送预览已过期", hint: "重新生成字段清单后再确认。" },
  LLM_CONSENT_REQUIRED: {
    title: "这次要先把「将发送的字段」给你过目",
    hint: "在发送预览里确认字段清单后再点确认；未经确认不会联网。",
  },
  LLM_DISABLED: {
    title: "模型通道已关闭",
    hint: "在设置里选一个模型服务并填好密钥；关掉时所有本地功能照常可用。",
    action: "settings",
  },
  JOB_INTERRUPTED: {
    title: "任务已中断（服务重启过）",
    hint: "重新点一次即可；已保存的内容不会丢。",
  },
  NO_DEFAULT_TEMPLATE: {
    title: "还没有可用的模板",
    hint: "去「模板」页导入一份简历，或把某个模板设为默认。",
  },
  FILE_IN_USE: {
    title: "这个文件还有地方在用",
    hint: "先在引用它的地方解除绑定（例如个人资料照片），再删除。",
  },

  RENDER_FAILED: { title: "PDF 渲染失败", hint: "可先导出 DOCX；或查看诊断里的引擎报错。" },
  FONT_UNAVAILABLE: {
    title: "找不到中文字体",
    hint: "导出会回退到 Chrome 引擎；仍然失败请检查系统是否安装 Songti / STHeiti。",
  },
  PDF_ENGINE_MISSING: { title: "PDF 引擎不可用", hint: "在设置里查看诊断，或先导出 DOCX。" },
  EXPORT_FAILED: { title: "导出失败", hint: "文件没有写出。重试，或换一个输出目录。" },
  PAGE_OVERFLOW: { title: "内容超出页数上限", hint: "删减条目或改用紧凑版式。" },
  PROFILE_INCOMPLETE: { title: "个人资料不完整", hint: "补齐联系方式与教育信息。", action: "profile" },
  JOB_CANCELLED: { title: "任务已取消", hint: "没有写入任何文件。" },
};

/**
 * 把 error 对象归一成 {code, title, body, hint, action}
 * @param {{code?:string, message?:string, vars?:object, hint?:string}} err
 */
export function describeError(err) {
  const code = (err && err.code) || "INTERNAL";
  const copy = ERROR_COPY[code];
  if (copy) {
    return {
      code,
      title: copy.title,
      body: err && err.message ? err.message : "",
      hint: (err && err.hint) || copy.hint || "",
      action: copy.action || null,
      known: true,
    };
  }
  return {
    code,
    title: "出现了未分类的错误",
    body: (err && err.message) || "",
    hint: "把下面这行技术细节发给开发者即可定位。",
    action: null,
    known: false,
  };
}

/**
 * 把 error 对象压成一句人话（给 `callout({body})` 这类只收文本的位置用）。
 *
 * 为什么需要它：`describeError()` 返回的是对象，直接塞进 `body` 会被字符串化成
 * 「[object Object]」——用户看到一团乱码，等于没有提示（AC-UI-09 的红）。
 */
export function errorText(err) {
  const d = describeError(err);
  const parts = [d.title];
  if (d.body && d.body !== d.title) parts.push(d.body);
  if (d.hint) parts.push(d.hint);
  return `${parts.join("：")}（错误码 ${d.code}）`;
}

/**
 * 渲染错误块（含可选「去设置 / 去个人资料」深链）
 * @param {{error:object, onAction?:(target:"settings"|"profile")=>void, compact?:boolean}} p
 */
export function errorView(p = {}) {
  const d = describeError(p.error);
  const actions = [];
  if (d.action && p.onAction) {
    actions.push(
      h(
        "button",
        {
          class: "ui-btn ui-btn--ghost ui-btn--sm",
          type: "button",
          onClick: () => p.onAction(d.action),
        },
        d.action === "settings" ? "去设置模型" : "去个人资料",
      ),
    );
  }
  return callout({
    tone: "danger",
    icon: "alert-circle",
    title: d.title,
    body: h(
      "span",
      { class: "stack", style: { gap: "var(--sp-2)" } },
      d.body ? h("span", null, d.body) : null,
      d.hint ? h("span", { class: "small muted" }, d.hint) : null,
      h(
        "span",
        { class: "err-code mono small" },
        icon("info", { size: 11 }),
        d.code,
      ),
    ),
    actions: actions.length ? actions : null,
    compact: p.compact,
  });
}
