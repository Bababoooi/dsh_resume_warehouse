# captain 侧验收工具（只读）

三个独立检查器，供 captain / t11 独立复核使用。**只读**：不写库、不改产物、不联网。

| 工具 | 判什么 | 典型用法 |
|---|---|---|
| `check_import_draft.py` | 导入草稿结构/数字/特殊字符/退化痕迹 | `python3 scripts/eval/check_import_draft.py` |
| `check_export_pdf.py` | 页数、最小字号、照片几何、横向溢出、身份回填 | `python3 scripts/eval/check_export_pdf.py --pdf <pdf> --expect-pages 1 --min-size 10.0 --photo --right-margin 15.62` |
| `check_lang_export.py` | 中英产物语言层：chrome CJK、半翻译、`LANG_FALLBACK` 对账 | `python3 scripts/eval/check_lang_export.py --pdf <pdf> --build <build_id>` |

退出码：`0` 通过 / `1` 有 FAIL / `2` 无法判定（缺文件、缺基准）。

## 基准文件与隐私

`check_import_draft.py` 的人工基准是 `data/eval/expected_zh_v10.json`，内含用户真实姓名与联系方式，
**因此放在 `data/`（已 gitignore），不进仓库**。基准缺失时工具报 `SKIP(no-local-fixture)` 而不是假通过。

判据全部文件驱动：条目数、数字串一律 `len()` 取，**不得在代码里硬编码条数**（上游文件改动会让硬编码判据变成假红或假绿）。

## 量法的自我约束

- 字号/行距/照片位置**从产物 PDF 字符属性量**，不读 `render.py` 常量或 `print.css` 变量（读常量等于改常量即改通过）。
- 设计期 DOM 估算是估算，**不得作 PASS/FAIL 依据**；产物出现后以产物为准。
- 任何「现状是 X」的结论须附时点（产物 mtime / 代码 mtime / 进程 started_at），三者须单调。

## 页面巡检：`scripts/check_pages_headless.py`

接口全绿、模块全 200、`node --check` 全过，页面照样能整站白屏——2026-10-23 连栽两次：
先是 CSP（`script-src 'self'`）拦掉了内联启动脚本，后是 `boot.js` 的 import 多了一层 `src/`
（解析成 `/src/src/components/*.js` 全部 404）。两次都是「页面打不开、API 全 200」，
所以页面必须有**行为级**判据，而且判据不能是截图字节数（受缓存/时序影响，会产生假红假绿）。

```bash
.venv/bin/python scripts/check_pages_headless.py            # 七个路由逐个查
.venv/bin/python scripts/check_pages_headless.py --route builds
.venv/bin/python scripts/check_pages_headless.py --json      # 机器可读
```

做法：起 Chrome（`--remote-debugging-port` + `--remote-allow-origins=*`）→ `Page.navigate`
→ **真实 sleep**（默认 2s，不用 `--virtual-time-budget`，它会冻住时间导致假空白）→
`Runtime.evaluate` 读 `#view.innerText` 与标题，同时收 `Log.entryAdded` / `Runtime.exceptionThrown`。

判据（任一不满足即 FAIL，退出码 1）：

| 列 | 含义 | 通过线 |
|---|---|---|
| 正文字符 | `#view` 的 `innerText` 长度 | ≥ 120 |
| CSP | `Log.entryAdded` 且 `source=security`（安全策略拦了东西） | 0 |
| 网络 | `source=network`（404/500，路径或接口写错） | 0，且打印 URL |
| 异常 | `Runtime.exceptionThrown` | 0 |
| 标题 | 该页 `page({title})` 的实际标题 | 必须出现 |

「CSP」与「网络」分列是硬要求：把 404 当 CSP 违规归因，会让人分不清是安全策略拦的还是路径写错了。

静态护栏在 `tests/test_web_boot.py`：`index.html` 不许有内联脚本（CSP 不给 `unsafe-inline`）、
`boot.js` 不许出现 `./src/` 前缀、`boot.js` 的每个相对 import 必须落到真实文件、
`<link rel="icon">` 不许指向不存在的文件。
