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

async function request(method, path, { body, raw, headers } = {}) {
  const init = { method, headers: { Accept: "application/json", ...(headers || {}) } };
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
  get: (path) => request("GET", path),
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

  validateNaming: (payload) => api.post("/api/v1/naming/validate", payload),
  preview: (payload) => api.post("/api/v1/llm/preview", payload),
  complete: (previewId, sha) => api.post("/api/v1/llm/complete", { preview_id: previewId, expected_payload_sha256: sha }),
  llmStatus: () => api.get("/api/v1/llm/status"),
};

/** 轮询 job 直到终态（页面用它做「导出中…」）。 */
export async function waitJob(jobId, { interval = 700, timeout = 180000 } = {}) {
  const started = Date.now();
  for (;;) {
    const job = await api.job(jobId);
    if (job.status === "succeeded" || job.status === "failed" || job.status === "interrupted") return job;
    if (Date.now() - started > timeout) return job;
    await new Promise((resolve) => setTimeout(resolve, interval));
  }
}

/** 列表响应统一是 `{items, next_cursor, total_estimate}`。 */
export function itemsOf(data) {
  return (data && Array.isArray(data.items) && data.items) || [];
}
