"""模板结构维护端点（契约 §17.2 标 P1 的两条）。

契约把模板写侧大规模推迟到 P2（"模板结构的首次生成走导入校对"，见 API-CONTRACT
§17.2.1），但这两条是 P1 且 t10 前置：

* ``POST /templates/{id}/blocks/reorder``：**只**改 ``order_index``（不动内容、不动
  ``parent_block_id``）——用户拖一下章节顺序不该被当成一次"结构重写"。
* ``POST /templates/{id}/validate``：**只读**体检，恒 200。它的价值是让用户在导出
  之前看到"这个模板缺 header / 有块没槽位 / 必填槽位没值"，而不是等到 PDF 出来才发现
  某段是空的。

两条端点都不写库以外的副作用（validate 连一行 UPDATE 都没有，用只读连接跑）。
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, request

from ..errors import ApiError, bad_request, not_found
from ..repos import TemplateRepo
from .common import ok, raw_body

bp = Blueprint("templates_ops", __name__)

#: 重排时相邻块之间的序号步长（留空位给以后插块，不必整体重编）
ORDER_STEP = 10

#: 允许的每页页数（单页 / 双页），与 schema 的 CHECK 同源
PAGE_LIMITS = (1, 2)


def _require(template_id: str) -> dict[str, Any]:
    row = TemplateRepo().get(template_id)
    if row is None:
        raise not_found("模板不存在", details={"resource": "template", "id": template_id})
    return row


def _requested_order(body: dict[str, Any]) -> list[str]:
    """取请求里的块 id 顺序。

    契约 §17.2 写的是 ``{"moves":[{"id","parent_block_id","order_index"}]}``，
    captain 定的实现口径是更简单的 ``{"block_ids":[...]}``（按数组顺序重写）。两种都收，
    免得前端按文档写却被拒。
    """
    block_ids = body.get("block_ids")
    if isinstance(block_ids, list):
        return [str(item) for item in block_ids]
    moves = body.get("moves")
    if isinstance(moves, list):
        pairs = [m for m in moves if isinstance(m, dict) and m.get("id") is not None]
        pairs.sort(key=lambda m: int(m.get("order_index") or 0))
        return [str(m["id"]) for m in pairs]
    raise bad_request(
        "缺少 block_ids",
        details={"field": "block_ids", "hint": 'body 形如 {"block_ids": ["tb2","tb1"]} 或 {"moves": [...]}'},
    )


@bp.post("/templates/<template_id>/blocks/reorder")
def reorder_blocks(template_id: str):
    """按给定数组顺序重写 ``order_index``（10, 20, 30…），其余列一律不动。"""
    _require(template_id)
    body = raw_body()
    order = _requested_order(body)
    repo = TemplateRepo()
    blocks = repo.list_blocks(template_id)
    known = {str(block["id"]): block for block in blocks}

    unknown = [block_id for block_id in order if block_id not in known]
    missing = [block_id for block_id in known if block_id not in set(order)]
    if unknown or missing:
        # 不猜"没给的块放哪"：少给/多给一律拒绝，避免静默把某块挪到末尾
        raise ApiError(
            "VALIDATION_ERROR",
            "block_ids 必须恰好是该模板的全部 block（不多不少）",
            details={
                "reason": "BLOCK_IDS_MISMATCH",
                "template_id": template_id,
                "unknown": unknown,
                "missing": missing,
                "expected_count": len(known),
                "given_count": len(order),
                "fields": [
                    {
                        "field": "block_ids",
                        "rule": "blocks_of_template",
                        "message": "block_ids 必须恰好是该模板的全部 block（不多不少）",
                    }
                ],
            },
            hint="请把该模板的全部 block id 按期望顺序一次性提交",
        )

    # 按父级分组：order_index 只在同一层级内有意义（21、31 是 20、30 的子块），
    # 所以每一组各自按「在请求数组里出现的先后」编号，不会把子块顶到别的段里。
    groups: dict[str, list[str]] = {}
    for block_id in order:
        groups.setdefault(_group_key(known[block_id]), []).append(block_id)
    for siblings in groups.values():
        for index, block_id in enumerate(siblings):
            repo.reorder_block(block_id, (index + 1) * ORDER_STEP)
    return ok({"blocks": repo.list_blocks(template_id), "order": order})


def _group_key(block: dict[str, Any]) -> str:
    return str(block.get("parent_block_id") or "")


@bp.post("/templates/<template_id>/validate")
def validate_template(template_id: str):
    """结构体检：**只读**，恒 200，把问题列成 ``issues[]`` 交给前端逐条修。"""
    row = _require(template_id)
    blocks = TemplateRepo().list_blocks(template_id)
    issues: list[dict[str, Any]] = []

    if not blocks:
        issues.append(
            {
                "code": "TEMPLATE_EMPTY",
                "block_id": None,
                "message": "模板里一个 block 都没有，导出会得到空简历",
            }
        )

    page_limit = row.get("page_limit")
    if page_limit not in PAGE_LIMITS:
        issues.append(
            {
                "code": "PAGE_LIMIT_INVALID",
                "block_id": None,
                "message": f"page_limit={page_limit!r}，只能是 {list(PAGE_LIMITS)}",
            }
        )

    headers = [block for block in blocks if block.get("block_type") == "header"]
    if blocks and not headers:
        issues.append(
            {
                "code": "NO_HEADER",
                "block_id": None,
                "message": "缺少 header 块：姓名/联系方式无处安放",
            }
        )

    parents_with_children = {_group_key(block) for block in blocks if block.get("parent_block_id")}
    seen_orders: dict[tuple[str, int], str] = {}
    for block in blocks:
        block_id = str(block["id"])
        heading = block.get("heading") or block.get("block_type")
        slots = block.get("slots") or []
        has_children = block_id in parents_with_children
        has_static = bool(str(block.get("static_text") or "").strip())
        if not slots and not has_children and not has_static:
            issues.append(
                {
                    "code": "BLOCK_WITHOUT_SLOTS",
                    "block_id": block_id,
                    "message": f"「{heading}」没有任何槽位，渲染时不会有内容",
                }
            )
        for slot in slots:
            if not int(slot.get("required") or 0):
                continue
            if slot.get("bound_field") or slot.get("default_value"):
                continue
            issues.append(
                {
                    "code": "SLOT_MISSING_VALUE",
                    "block_id": block_id,
                    "message": f"必填槽位「{slot.get('slot_key')}」既没绑定字段也没默认值",
                }
            )
        key = (_group_key(block), int(block.get("order_index") or 0))
        if key in seen_orders:
            issues.append(
                {
                    "code": "DUPLICATE_ORDER_INDEX",
                    "block_id": block_id,
                    "message": (
                        f"同一层级里 order_index={key[1]} 重复（与 {seen_orders[key]} 冲突），"
                        "渲染顺序不确定"
                    ),
                }
            )
        else:
            seen_orders[key] = block_id

    return ok(
        {
            "ok": not issues,
            "valid": not issues,
            "template_id": template_id,
            "checked": len(blocks),
            "issues": issues,
        }
    )


#: 供 ``api/__init__.py`` 统一注册
templates_ops_bp = bp
