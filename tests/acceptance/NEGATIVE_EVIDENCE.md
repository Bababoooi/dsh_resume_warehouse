# 负向验证记录（AC-UI-05 / 06 / 07 / 09）

**这份文件为什么存在**：`tests/acceptance/test_ac_ui_browser.py` 的四条 AC 是 CDP 真浏览器断言。
「断言能过」不等于「断言能红」——一个永远为真的断言也是绿的。所以这里逐条记录
**人为把产品改坏之后、对应用例真的 FAIL** 的执行输出。

- **不是手抄**：下面四段都是真跑出来的。手法是「备份源文件 → 打一个最小的产品侧补丁 → 只跑该用例 → 存日志 → 还原 → `md5` 校验还原一致」。
- **执行时点**：2026-10-23T08:54:14+0800（本机，Chrome + CDP，临时 `DATA_DIR`，不碰真实 `data/app.db`）。
- **当次 pytest 汇总行（还原后正向复跑）**：`4 passed, 1 deselected in 28.06s`
- **选例命令要用小写 `-k`**：`-k AC-UI-05` 选不到任何用例（pytest 的 `-k` 区分大小写，函数名是 `test_ac_ui_05_…`）；下面统一用 `-k ac_ui_05` 这种写法。
- 四段的补丁都只改 `web/src/` 下的前端资源，**没有改测试**；每条跑完都 `md5` 核对了还原后的文件与改坏前一致。

---

### AC-UI-05 命名实时预览（清空岗位名 → 红字 + 「去个人资料」深链）

- 命令：`.venv/bin/python -m pytest tests/acceptance/test_ac_ui_browser.py -q -k ac_ui_05`
- 负向手法：`web/src/pages/builds.js` 里把红字标题 `"文件名还不能生成"` 改成 `"文件名待生成"`（模拟「缺字段时不给红字说明」这一真实退化）。
- 期望：用例 FAIL，失败信息指到「文件名还不能生成」这句判据。
- 实际输出：
  ```
  >       assert "文件名还不能生成" in text, text[:400]
  FAILED tests/acceptance/test_ac_ui_browser.py::test_ac_ui_05_naming_error_links_to_profile
  1 failed, 4 deselected in 6.42s
  ```

### AC-UI-06 任务中断提示（服务重启 → 「已中断」而不是一直转圈）

- 命令：`.venv/bin/python -m pytest tests/acceptance/test_ac_ui_browser.py -q -k ac_ui_06`
- 负向手法：`web/src/pages/builds.js` 的导出分支里，在 `if (!done || done.status !== "succeeded") {` 之后立刻 `return`（模拟「中断分支没处理」——用户看到的是永远停在「正在渲染 PDF…」）。
- 期望：用例 FAIL，且两条判据都红（既没有「任务已中断」，也没有收尾）。
- 实际输出：
  ```
  E       assert '任务已中断' in '组装\n\n挑模板、挑经历，点导出。文件名按「岗位-姓名-学校」。\n\n这次投什么\n中文\nEnglish\nUI 模板（默认）\n不关联岗位\n包含照片\n文件名：后端实习生-张三-示例大学.pdf\n…正在渲染 PDF…\n本机 reportlab，不联网。\nnullnullnull\n…'
  FAILED tests/acceptance/test_ac_ui_browser.py::test_ac_ui_06_interrupted_job_shows_chinese_notice
  1 failed, 4 deselected in 6.53s
  ```

### AC-UI-07 1280 无横向滚动 / 1440 三栏

- 命令：`.venv/bin/python -m pytest tests/acceptance/test_ac_ui_browser.py -q -k ac_ui_07`
- 负向手法：`web/src/styles/layout.css` 把 `.split--build` 的列宽从 `var(--w-side-left) minmax(0,1fr) var(--w-side-right)` 改成写死 `360px 560px 560px`（模拟「有人把三栏宽度写死」）。
- 期望：用例 FAIL。
- 实际输出：
  ```
  E           AssertionError: 1280px 宽下三栏内容被裁切：容器内容宽 1504px > 可视宽 1072px（窗口 1280px）
  E           assert 1504 <= (1072 + 1)
  FAILED tests/acceptance/test_ac_ui_browser.py::test_ac_ui_07_no_horizontal_scroll_at_1280
  1 failed, 4 deselected in 7.50s
  ```
- **这条负向验证暴露过用例自身的盲点，已顺手补掉**：第一版只断言
  `document.scrollingElement.scrollWidth - window.innerWidth <= 1`。三栏写死固定像素时，外层容器
  `overflow: hidden` 会把右栏**裁掉**而不是产生文档级滚动，于是文档 overflow 仍是 0、用例照样绿
  （我第一次跑这个补丁就是 `1 passed`）。补的断言是「三栏容器自身 `scrollWidth <= clientWidth + 1`」
  ——上表这行就是补完之后跑出来的。盲点没补之前，这条 AC 只能抓到「页面整体撑宽」，抓不到「右栏被切」。

### AC-UI-09 错误码渲染成人话 + 下一步（不许把 JSON 糊脸上）

- 命令：`.venv/bin/python -m pytest tests/acceptance/test_ac_ui_browser.py -q -k ac_ui_09`
- 负向手法：`web/src/components/errors.js` 的 `errorText()` 直接 `return JSON.stringify(err)`（模拟「把错误对象原样印到界面上」）。
- 期望：用例 FAIL，失败信息含「没有渲染对应人话」与原始 JSON 片段。
- 实际输出：
  ```
  E           AssertionError: NOT_FOUND 没有渲染对应人话（期望「找不到这条数据」）：'经历库\n\n…\n读不到经历库\n{"name":"ApiError","code":"NOT_FOUND","details":{"secret":"raw"},"hint":"","status":400}'
  FAILED tests/acceptance/test_ac_ui_browser.py::test_ac_ui_09_error_codes_render_chinese_next_steps
  1 failed, 4 deselected in 2.93s
  ```

---

## 复现方式（想自己再跑一遍的话）

四段都是同一个套路，举例（AC-UI-09）：

```bash
cd resume-warehouse
cp web/src/components/errors.js /tmp/errors.js.bak        # 1. 备份
python3 - <<'PY'                                          # 2. 打补丁（见上「负向手法」）
import pathlib
p = pathlib.Path("web/src/components/errors.js"); s = p.read_text()
p.write_text(s.replace('return `${parts.join("：")}（错误码 ${d.code}）`;', 'return JSON.stringify(err);'))
PY
.venv/bin/python -m pytest tests/acceptance/test_ac_ui_browser.py -q -k ac_ui_09   # 3. 应该红
cp /tmp/errors.js.bak web/src/components/errors.js        # 4. 还原
md5 -q web/src/components/errors.js                       # 5. 核对与备份一致
```

四条的正向基线（还原后）：`4 passed, 1 deselected in 28.06s`。
