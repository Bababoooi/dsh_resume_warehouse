"""无法自动判定的验收条款：逐条写清「为什么必须人眼/手做」，交给 t10 终验的人照着做。

账本（``make_index.py``）把这里的条目计为 **MANUAL**，而不是「未覆盖」——
两者的区别是责任：未覆盖 = 没人管；MANUAL = 已认领，且附了可执行的验证步骤。
"""

from __future__ import annotations

from typing import Final

MANUAL: Final[dict[str, str]] = {
    "AC-LOC-07": "需要真实点一次「清空数据」并在输入框里手打 DELETE，再重启服务确认 schema 自动重建。自动化会在真库上删数据，不能跑；请在 data/ 备份后手动验证，命令：`cp -r data data.bak && .venv/bin/python scripts/preflight.py`（重启后查 /api/v1/health 的 db.schema_version）。",
    "AC-PDF-20": "打印版式一致性只能在浏览器打印预览里看：Chrome 打开预览页 → ⌘P → 选 A4、边距选「默认」→ 对比导出的 PDF 首页边距（左右 42.5pt / 上下 45.35pt）。",
    "AC-JD-05": "CompanyProfile 的手填/LLM 建议属于交互流程：需要人在 #/jobs 页填一次 culture_tags/hiring_signals/source_urls，再点「让 AI 建议」看是否合并进同一份档案（接口侧已有 PATCH/analyze 自动断言兜底）。",
}
