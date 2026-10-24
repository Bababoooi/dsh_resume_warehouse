/**
 * 后端 API 客户端（同源，无任何外部依赖）。
 *
 * 约定（与 docs/API-CONTRACT.md 一致）：
 * - 成功统一信封 `{ok:true, data, request_id}`，这里直接把 `data` 交给调用方；
 * - 失败统一信封 `{ok:false, error:{code,message,details,hint}, request_id}`，
 *   这里抛 `ApiError`，带 `code/message/details/hint/status`，页面用 `describeError` 渲染；
 * - 不做任何重试/降级：隐私与 consent 的语义在前端必须保持「用户点一次=发一次」。
 */

export class ApiError extends Error {
  constructor(error, status) {
    super(error?.message || "请求失败");
    this.name = "ApiError";
    this.code = error?.code || "NETWORK";
    this.details = error?.details || null;
    this.hint = error?.hint || "";
    this.status = status || 0;
  }
}

function parseJson(text) {
  try {
    return JSON.parse(text);
  } catch (err) {
    return null;
  }
}

async function request(method, path, { body, raw, headers, signal } = {}) {
  const init = { method, headers: { Accept: "application/json", ...(headers || {}) } };
  if (signal) init.signal = signal;
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new ApiError({ code: "ABORTED", message: "请求已取消", hint: "" }, 0);
    }
    throw new ApiError({ code: "NETWORK", message: "连不上本地后端", hint: "请确认服务还在运行（data/runtime/app_port 里有端口）" }, 0);
  }
  if (raw && response.ok) return response;
  const text = await response.text();
  const payload = parseJson(text);
  if (!response.ok || !payload || payload.ok === false) {
    throw new ApiError(payload?.error || { code: `HTTP_${response.status}`, message: text.slice(0, 200) }, response.status);
  }
  return payload.data;
}

export const api = {
  get: (path, opts) => request("GET", path, opts),
  post: (path, body) => request("POST", path, { body }),
  put: (path, body) => request("PUT", path, { body }),
  patch: (path, body) => request("PATCH", path, { body }),
  del: (path) => request("DELETE", path),
  upload: (path, formData) => request("POST", path, { body: formData }),
  download: (path) => request("GET", path, { raw: true }),

  // ---- 具体资源（页面只调这些，避免各页自己拼 URL） ----------------------
  health: () => api.get("/api/v1/health"),
  env: () => api.get("/api/v1/env"),
  profile: () => api.get("/api/v1/profile"),
  saveProfile: (patch) => api.put("/api/v1/profile", patch),
  // 教育段补充行（GPA / 主修课程）：只读写默认模板教育段的那一个 static_text
  educationFacts: () => api.get("/api/v1/profile/education-facts"),
  saveEducationFacts: (lines) => api.put("/api/v1/profile/education-facts", { lines }),
  settings: () => api.get("/api/v1/settings"),
  saveSettings: (patch) => api.put("/api/v1/settings", patch),

  packages: (query = "") => api.get(`/api/v1/packages${query}`),
  package: (id) => api.get(`/api/v1/packages/${id}?include=variants`),
  packageStats: () => api.get("/api/v1/packages/stats"),
  draftPackage: (text) => api.post("/api/v1/packages/draft", { text }),
  createPackage: (payload) => api.post("/api/v1/packages", payload),
  patchPackage: (id, payload) => api.patch(`/api/v1/packages/${id}`, payload),
  deletePackage: (id) => api.del(`/api/v1/packages/${id}`),
  addVariant: (packageId, payload) => api.post(`/api/v1/packages/${packageId}/variants`, payload),

  imports: () => api.get("/api/v1/imports"),
  importFile: (file) => {
    const form = new FormData();
    form.append("file", file);
    return api.upload("/api/v1/imports", form);
  },
  importText: (text) => api.post("/api/v1/imports", { text }),
  importDraft: (id) => api.get(`/api/v1/imports/${id}/draft`),
  commitImport: (id, payload) => api.post(`/api/v1/imports/${id}/commit`, payload),

  templates: (lang) => api.get(`/api/v1/templates${lang ? `?lang=${lang}` : ""}`),
  defaultTemplate: (lang) => api.get(`/api/v1/templates/default?lang=${lang}`),
  setDefaultTemplate: (id) => api.post(`/api/v1/templates/${id}/default`),

  jds: () => api.get("/api/v1/jds"),
  createJd: (payload) => api.post("/api/v1/jds", payload),
  jd: (id) => api.get(`/api/v1/jds/${id}`),
  analyzeJd: (id, payload) => api.post(`/api/v1/jds/${id}/analyze`, payload),
  matchJd: (id) => api.post(`/api/v1/jds/${id}/match`),

  builds: () => api.get("/api/v1/builds"),
  createBuild: (payload) => api.post("/api/v1/builds", payload),
  build: (id) => api.get(`/api/v1/builds/${id}?include=selections,artifacts`),
  setSelections: (id, items) => api.put(`/api/v1/builds/${id}/selections`, { items }),
  assemble: (id) => api.post(`/api/v1/builds/${id}/assemble`),
  exportBuild: (id, payload) => api.post(`/api/v1/builds/${id}/export`, payload),

  jobs: () => api.get("/api/v1/jobs"),
  job: (id) => api.get(`/api/v1/jobs/${id}`),

  // opts.signal：命名预览在连续输入时会被新请求取消（builds/profile 的 300ms 防抖）
  validateNaming: (payload, opts = {}) => request("POST", "/api/v1/naming/validate", { body: payload, signal: opts.signal }),
  preview: (payload) => api.post("/api/v1/llm/preview", payload),
  complete: (previewId, sha) => api.post("/api/v1/llm/complete", { preview_id: previewId, expected_payload_sha256: sha }),
  llmStatus: () => api.get("/api/v1/llm/status"),
};

/** job 是否已经到终态（终态之后不该再轮询） */
export function isJobDone(job) {
  return Boolean(job) && ["succeeded", "failed", "interrupted", "cancelled"].includes(job.status);
}

/**
 * 轮询 job 直到终态（页面用它做「导出中…」）。
 *
 * 为什么要退避：导出/分析动辄几十秒，固定 700ms 会把本地服务打满无谓请求，
 * 也不利于用户在长任务里看清「还在跑」。起步 900ms，按 factor 退到 maxInterval。
 *
 * 轮询期间网络抖一下**不立刻判死**：连续 transientRetries 次失败才抛，
 * 因为「本地服务短暂过载」不该等价于「导出失败了」。
 *
 * @param {string} jobId
 * @param {object} [opts]
 * @param {number} [opts.interval=900] 首次间隔（800–1200ms 区间）
 * @param {number} [opts.maxInterval=4000] 退避上限
 * @param {number} [opts.factor=1.4] 退避系数
 * @param {number} [opts.timeout=300000] 总超时；超时抛 JOB_TIMEOUT
 * @param {number} [opts.transientRetries=4] 连续网络错误容忍次数
 * @param {Function} [opts.onTick] (job, {elapsedMs, attempt}) 每次拿到状态时回调
 * @param {Function} [opts.shouldStop] () => boolean，返回 true 时提前结束（例如页面已卸载）
 * @returns {Promise<object>} 终态 job
 */
export async function waitJob(
  jobId,
  { interval = 900, maxInterval = 4000, factor = 1.4, timeout = 300000, transientRetries = 4, onTick, shouldStop } = {},
) {
  const started = Date.now();
  let delay = Math.max(300, Number(interval) || 900);
  let attempt = 0;
  let failures = 0;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  for (;;) {
    attempt += 1;
    let job;
    try {
      job = await api.job(jobId);
      failures = 0;
    } catch (err) {
      failures += 1;
      if (failures > transientRetries) throw err;
      await sleep(delay);
      delay = Math.min(maxInterval, Math.ceil(delay * factor));
      continue;
    }

    if (typeof onTick === "function") onTick(job, { elapsedMs: Date.now() - started, attempt });
    if (isJobDone(job)) return job;
    if (typeof shouldStop === "function" && shouldStop()) return job;

    if (Date.now() - started > timeout) {
      throw new ApiError(
        {
          code: "JOB_TIMEOUT",
          message: `等了 ${Math.round((Date.now() - started) / 1000)} 秒还没完成`,
          hint: "任务可能还在服务端跑：可以稍后到「任务」页看结果，或重新发起一次。",
          details: { job_id: jobId },
        },
        0,
      );
    }

    await sleep(delay);
    delay = Math.min(maxInterval, Math.ceil(delay * factor));
  }
}

/** 列表响应统一是 `{items, next_cursor, total_estimate}`。 */
export function itemsOf(data) {
  return (data && Array.isArray(data.items) && data.items) || [];
}
