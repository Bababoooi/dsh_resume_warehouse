#!/usr/bin/env python3
"""路由一致性（文档 ↔ 实现）的**唯一权威实现**（captain m01767 §二）。

此前 planner / supervisor / lead 各写一份解析脚本，得出 39/18、20/46、21/31 三组不同
数字——根因不是谁解析错了，而是**这个指标没有定义**。本脚本把定义写死在这里：

归一化规则（改规则 = 改这个函数，别在别处另写一份）
------------------------------------------------
1. 方法一律大写，只认 ``GET/POST/PUT/PATCH/DELETE``（其它（HEAD/OPTIONS）不参与比对）。
2. 路径参数统一成 ``*``：``{id}`` / ``<id>`` / ``<string:slug>`` / ``{id:uuid}`` → ``*``。
3. ``Blueprint(url_prefix=...)`` 自动拼接；代码里省略前缀时按 ``/api/v1`` 拼。
4. 尾斜杠忽略（``/packages/`` 与 ``/packages`` 等价）。
5. **不展开子资源**：``/packages/{id}/variants`` 就是一条路由，不会因为 ``/packages``
   存在而被折叠或展开。
6. 查询串（``?q=``）不参与路径比对。
7. **说明性路径不计入**：含 ``..`` 的示例（如目录穿越演示里的
   ``/api/v1/files/../../.env``）不是路由，直接跳过——否则它会被当成一条
   「文档有、代码没有」的缺口，制造假红。

支持的两侧格式
--------------
口径（唯一权威定义，别再各写一份）
----------------------------------
* ``documented_total`` / ``code_total`` = 两侧 **unique (method, normalized_path) 条数**。
  同一路由在正文里被提及多次只算 1 条，次数记在每行的 ``mentions`` 字段里——把「提到
  几次」混进「缺几条路由」正是这个指标过去永远吵不清的原因。
* ``only_in_code`` = **代码有、文档无**（项目里的老叫法是 REV）。
* ``only_in_docs`` = **文档有、代码无**（老叫法 FWD）。
* ``matched`` = 两侧都有的条数。
* 旧键 ``rev`` / ``fwd`` **已废弃且不再输出**——它们曾被用来表示「文档侧/代码侧总数」，
  与项目里 REV=代码多、FWD=文档多的既有含义**正好相反**，读到的人都以为是缺口数。
* 不变量（必须恒成立，否则退出码 2）：
  ``matched + only_in_code == code_total``、
  ``matched + only_in_docs == documented_total``、两组差集互不相交、每侧都已去重。

文档（``docs/API-CONTRACT.md``）：
  * 两栏表格 ``| `GET` | `/packages` | 说明 |``
  * 三栏及更宽表格（同上，后续单元格当说明）
  * 内联 `` `GET /api/v1/packages` ``（也会抓 ``GET /packages`` 形态）
代码（``server/app/api/*.py``）：
  * ``@bp.get("/x")`` / ``@bp.post`` / ``@bp.put`` / ``@bp.patch`` / ``@bp.delete``
  * ``@bp.route("/x", methods=["GET", "POST"])``（多方法装饰器，展开成多条）
  * ``@app.route``（同一模块内出现时也认）

脏格式策略：**不猜**。一格塞两条路由（``| `GET` | `/jds` / `GET /jds/{id}` |``）这类
情况记进 ``warnings`` 并在 stderr 打印行号，让文档去改，而不是让脚本装作没看见。

用法::

    python3 scripts/check_route_parity.py                 # 输出 JSON
    python3 scripts/check_route_parity.py --self-test     # 自检（内置脏样本）
    python3 scripts/check_route_parity.py --strict        # 仅文档多出的路由 → 退出码 1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS = PROJECT_ROOT / "docs" / "API-CONTRACT.md"
API_DIR = PROJECT_ROOT / "server" / "app" / "api"

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
DEFAULT_PREFIX = "/api/v1"

_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_METHOD_CELL_RE = re.compile(r"^`?\s*(GET|POST|PUT|PATCH|DELETE)\s*`?$")
_PATH_CELL_RE = re.compile(r"^`?(/[A-Za-z0-9_\-{}/<>:*]*)`?$")
# 路径段字符集故意**不含** ``.``、``"``、``'``：
#   * 不含 ``.`` → 不会把「`GET /api/v1/settings` 的 `app_port`」粘成
#     ``/api/v1/settings.app_port``；也天然挡住 ``../.env`` 这类示例（规则 7）
#   * 不含引号 → 不会把 ``PUT /api/v1/profile/photo"`` 的右引号吃进路径
_SEG = r"A-Za-z0-9_\-{}/<>:*"
_INLINE_RE = re.compile(
    r"(?<![\w/])(GET|POST|PUT|PATCH|DELETE)\s+`?(/api/v1/[" + _SEG + r"]*|/[" + _SEG + r"]+[" + _SEG + r"/])"
)
_PARAM_RE = re.compile(r"(\{[^}/]*\}|<[^>/]*>)")


def normalize_path(path: str, *, prefix: str | None = DEFAULT_PREFIX) -> str:
    """按本文件顶部的规则归一化：参数 → ``*``、去查询串、去尾斜杠、补前缀。"""
    raw = (path or "").strip().strip("`").split("?", 1)[0].strip()
    if not raw.startswith("/"):
        raw = "/" + raw
    if prefix and not raw.startswith("/api/"):
        # 文档与代码都可能省略 /api/v1（§17 的实现档位说明里就这样写）
        raw = prefix + raw
    raw = _PARAM_RE.sub("*", raw)
    raw = re.sub(r"/{2,}", "/", raw)
    if len(raw) > 1:
        raw = raw.rstrip("/")
    return raw or "/"


_ILLUSTRATIVE_RE = re.compile(r"(^\.\.$|\.\./|/\.\.|^\.)")


def _is_illustrative(path: str) -> bool:
    """``..``/``.`` 之类的示例路径不是路由（规则 7）。"""
    return bool(_ILLUSTRATIVE_RE.search(path)) or ".." in path


def _warn(warnings: list[dict[str, Any]], code: str, file: str, line: int, detail: str) -> None:
    warnings.append({"code": code, "source_file": file, "line": line, "detail": detail})
    print(f"[warn] {code} {file}:{line} {detail}", file=sys.stderr)


def parse_docs(text: str, *, source: str = "docs/API-CONTRACT.md",
               prefix: str = DEFAULT_PREFIX) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """解析文档里的路由声明。返回 (routes, warnings)。"""
    routes: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        row = _TABLE_ROW_RE.match(line)
        if row and "---" not in line:
            cells = [cell.strip() for cell in row.group(1).split("|")]
            if len(cells) >= 2 and _METHOD_CELL_RE.match(cells[0]):
                method = _METHOD_CELL_RE.match(cells[0]).group(1)  # type: ignore[union-attr]
                path_cell = cells[1]
                # 一格可能塞多条：`/jds` / `GET /jds/{id}`（§393 的真实脏格式）
                pieces = [p.strip() for p in re.split(r"\s+/\s+|\s{2,}", path_cell) if p.strip()]
                if len(pieces) > 1:
                    _warn(
                        warnings,
                        "MULTI_ROUTE_PER_CELL",
                        source,
                        lineno,
                        f"一格塞了多条路由：{path_cell!r}（请拆成多行）",
                    )
                for piece in pieces:
                    piece_method = method
                    inline = re.match(
                        r"`?\s*(GET|POST|PUT|PATCH|DELETE)\s+`?(/[^\s`]*)", piece
                    )
                    if inline:
                        piece_method, piece = inline.group(1), inline.group(2)
                    match = _PATH_CELL_RE.match(piece)
                    if match and _is_illustrative(match.group(1)):
                        continue
                    if match:
                        routes.append(
                            {
                                "method": piece_method,
                                "path": normalize_path(match.group(1), prefix=prefix),
                                "source_file": source,
                                "line": lineno,
                                "style": "table",
                            }
                        )
                continue
        for match in _INLINE_RE.finditer(line):
            method, path = match.group(1), match.group(2)
            if not path or path in ("/",) or _is_illustrative(path):
                continue
            routes.append(
                {
                    "method": method,
                    "path": normalize_path(path, prefix=prefix),
                    "source_file": source,
                    "line": lineno,
                    "style": "inline",
                }
            )
    return routes, warnings


_BLUEPRINT_RE = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*Blueprint\(\s*['\"][^'\"]+['\"](?P<rest>.*)$"
)
_PREFIX_RE = re.compile(r"url_prefix\s*=\s*['\"]([^'\"]+)['\"]")
_DECORATOR_RE = re.compile(r"^\s*@(?P<obj>[A-Za-z_][A-Za-z0-9_]*)\.(?P<kind>get|post|put|patch|delete|route)\(\s*(?P<args>.*)$")
_STR_RE = re.compile(r"['\"](/[^'\"]*)['\"]")
_METHODS_KW_RE = re.compile(r"methods\s*=\s*\[([^\]]*)\]")


def parse_api_module(text: str, *, source: str, prefix: str = DEFAULT_PREFIX,
                     app_prefix: str = "") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """解析一个 ``app/api/*.py`` 模块里的路由装饰器。"""
    routes: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    blueprints: dict[str, str] = {}
    for lineno, line in enumerate(text.splitlines(), start=1):
        bp = _BLUEPRINT_RE.match(line)
        if bp:
            found = _PREFIX_RE.search(bp.group("rest"))
            blueprints[bp.group("name")] = found.group(1) if found else ""
            continue
        deco = _DECORATOR_RE.match(line)
        if not deco:
            continue
        obj, kind, args = deco.group("obj"), deco.group("kind"), deco.group("args")
        strings = _STR_RE.findall(args)
        if not strings:
            continue
        path = strings[0]
        if kind == "route":
            methods_kw = _METHODS_KW_RE.search(args)
            methods = (
                [m.strip().strip("'\"").upper() for m in methods_kw.group(1).split(",") if m.strip()]
                if methods_kw
                else ["GET"]
            )
            methods = [m for m in methods if m in METHODS]
            if not methods:
                _warn(warnings, "ROUTE_WITHOUT_METHOD", source, lineno, f"未识别 methods：{args.strip()}")
                continue
        else:
            methods = [kind.upper()]
        module_prefix = blueprints.get(obj, "")
        full_prefix = (module_prefix or prefix) if obj not in blueprints else module_prefix
        if not full_prefix and obj in blueprints:
            full_prefix = prefix
        for method in methods:
            routes.append(
                {
                    "method": method,
                    "path": normalize_path(path, prefix=full_prefix or prefix),
                    "source_file": source,
                    "line": lineno,
                    "style": "code",
                }
            )
    return routes, warnings


def aggregate(occurrences: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """把「按行收集」的原始命中折叠成 unique (method, path) 一行。

    这是本脚本存在的理由：``rev`` 曾经把「文档里提到几次」当「缺几条路由」，
    于是同一路由被列 2 遍、3 遍，数字永远吵不清。折叠后每行带 ``mentions`` 计数。
    """
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in occurrences:
        key = (item["method"], item["path"])
        entry = grouped.get(key)
        if entry is None:
            grouped[key] = {
                "method": item["method"],
                "path": item["path"],
                "source_file": item.get("source_file", ""),
                "line": item.get("line", 0),
                "mentions": 1,
                "styles": sorted({item.get("style", "")} - {""}),
            }
        else:
            entry["mentions"] += 1
            if item.get("style") and item["style"] not in entry["styles"]:
                entry["styles"] = sorted({*entry["styles"], item["style"]})
    return sorted(grouped.values(), key=lambda row: (row["path"], row["method"]))


def collect(docs_path: Path = DOCS, api_dir: Path = API_DIR) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    doc_hits: list[dict[str, Any]] = []
    code_hits: list[dict[str, Any]] = []

    doc_text = docs_path.read_text(encoding="utf-8") if docs_path.exists() else ""
    doc_source = str(docs_path.relative_to(PROJECT_ROOT)) if docs_path.is_absolute() else str(docs_path)
    doc_routes, doc_warnings = parse_docs(doc_text, source=doc_source)
    doc_hits.extend(doc_routes)
    warnings.extend(doc_warnings)

    for module in sorted(api_dir.glob("*.py")):
        text = module.read_text(encoding="utf-8")
        source = str(module.relative_to(PROJECT_ROOT)) if module.is_absolute() else str(module)
        routes, module_warnings = parse_api_module(text, source=source)
        code_hits.extend(routes)
        warnings.extend(module_warnings)

    rev = aggregate(doc_hits)
    fwd = aggregate(code_hits)
    rev_keys = {(item["method"], item["path"]) for item in rev}
    fwd_keys = {(item["method"], item["path"]) for item in fwd}
    matched_keys = rev_keys & fwd_keys
    only_docs = sorted(rev_keys - fwd_keys)
    only_code = sorted(fwd_keys - rev_keys)

    def pairs(keys: Iterable[tuple[str, str]]) -> list[dict[str, Any]]:
        return [{"method": method, "path": path} for method, path in sorted(keys, key=lambda k: (k[1], k[0]))]

    count_values = {
        # 两侧 unique 条数（不是缺口数）
        "documented_total": len(rev),
        "code_total": len(fwd),
        "matched": len(matched_keys),
        # 缺口：这两个才是判据
        "only_in_code": len(only_code),   # 代码有、文档无（老叫法 REV）
        "only_in_docs": len(only_docs),   # 文档有、代码无（老叫法 FWD）
        # 只作参考，不进判据
        "mentions": sum(item["mentions"] for item in rev) + sum(item["mentions"] for item in fwd),
    }

    # 不变量：数学关系不成立就说明解析器坏了，宁可退出码非 0 也不许打印一个「看着精确」的数字。
    invariants = {
        "matched_plus_only_in_docs_equals_documented_total": len(matched_keys) + len(only_docs) == len(rev_keys),
        "matched_plus_only_in_code_equals_code_total": len(matched_keys) + len(only_code) == len(fwd_keys),
        "rev_and_only_in_code_are_disjoint": not (rev_keys & set(only_code)),
        "fwd_and_only_in_docs_are_disjoint": not (fwd_keys & set(only_docs)),
        "only_lists_are_disjoint": not (set(only_docs) & set(only_code)),
        "every_documented_route_is_unique": len(rev_keys) == len(rev),
        "every_code_route_is_unique": len(fwd_keys) == len(fwd),
    }
    return {
        # 两份清单也改中性名字：documented=文档侧、code=代码侧（旧名 rev/fwd 已废弃）
        "documented": rev,
        "code": fwd,
        "counts": count_values,
        "only_in_docs": pairs(only_docs),
        "only_in_code": pairs(only_code),
        "invariants": invariants,
        "invariants_ok": all(invariants.values()),
        "warnings": sorted(warnings, key=lambda item: (item["source_file"], item["line"], item["code"])),
    }


# ---------------------------------------------------------------- self-test
SELF_TEST_DOC = """\
| 方法 | 路径 | 说明 |
| `GET` | `/packages` | 列表 |
| `POST` | `/packages` | 新建 |
| `GET` | `/packages/{id}` | 详情 |
| `GET` | `/jds` / `GET /jds/{id}` | 脏格式：一格两条 |
内联写法：`GET /api/v1/naming/template` 与 `DELETE /api/v1/packages/{id}/variants/{vid}`
"""

# 专门抓本次 bug 的最小样本：同一路由在文档里出现 3 次 + 代码侧 <x> 与文档 {x} 对应
SELF_TEST_DUP_DOC = """\
| `GET` | `/packages/{id}` | 详情 |
说明里又提了一次 `GET /api/v1/packages/{id}`，再提一次 `GET /api/v1/packages/{id}`。|
"""

SELF_TEST_DUP_MODULE = """\
from flask import Blueprint

bp = Blueprint("demo", __name__)


@bp.get("/api/v1/packages/<package_id>")
def detail(package_id):
    ...
"""

SELF_TEST_MODULE = """\
from flask import Blueprint

bp = Blueprint("demo", __name__)
tpl = Blueprint("tpl", __name__, url_prefix="/api/v1/templates")


@bp.get("/api/v1/packages")
def a():
    ...


@bp.route("/api/v1/packages/<package_id>", methods=["GET", "PATCH"])
def b(package_id):
    ...


@tpl.delete("/{template_id}/")
def c(template_id):
    ...
"""


def self_test() -> int:
    failures: list[str] = []
    routes, warnings = parse_docs(SELF_TEST_DOC, source="self-doc.md")
    doc_keys = {(r["method"], r["path"]) for r in routes}
    expected_doc = {
        ("GET", "/api/v1/packages"),
        ("POST", "/api/v1/packages"),
        ("GET", "/api/v1/packages/*"),
        ("GET", "/api/v1/jds"),
        ("GET", "/api/v1/jds/*"),
        ("GET", "/api/v1/naming/template"),
        ("DELETE", "/api/v1/packages/*/variants/*"),
    }
    if doc_keys != expected_doc:
        failures.append(f"文档解析：期望 {sorted(expected_doc)}，实际 {sorted(doc_keys)}")
    if not any(w["code"] == "MULTI_ROUTE_PER_CELL" and w["line"] == 5 for w in warnings):
        failures.append(f"脏格式未报 warning（期望 line=5）：{warnings}")

    code_routes, _ = parse_api_module(SELF_TEST_MODULE, source="self-module.py")
    code_keys = {(r["method"], r["path"]) for r in code_routes}
    expected_code = {
        ("GET", "/api/v1/packages"),
        ("GET", "/api/v1/packages/*"),
        ("PATCH", "/api/v1/packages/*"),
        ("DELETE", "/api/v1/templates/*"),
    }
    if code_keys != expected_code:
        failures.append(f"代码解析：期望 {sorted(expected_code)}，实际 {sorted(code_keys)}")

    # 归一化单测（参数三种写法 + 尾斜杠 + 查询串）
    for raw in ("/packages/{id}", "/packages/<id>", "/packages/<string:id>", "/api/v1/packages/{id}/"):
        if normalize_path(raw) != "/api/v1/packages/*":
            failures.append(f"normalize_path({raw!r}) = {normalize_path(raw)!r}")

    # -- 去重（本次 bug 的回归样本）：3 次提及 → 1 条路由、mentions==3，且与代码侧对上
    dup_doc, _ = parse_docs(SELF_TEST_DUP_DOC, source="dup-doc.md")
    dup_code, _ = parse_api_module(SELF_TEST_DUP_MODULE, source="dup-module.py")
    rev = aggregate(dup_doc)
    fwd = aggregate(dup_code)
    rev_keys = {(item["method"], item["path"]) for item in rev}
    fwd_keys = {(item["method"], item["path"]) for item in fwd}
    if len(rev) != 1:
        failures.append(f"去重失败：3 次提及应收敛成 1 条 unique 路由，实际 {len(rev)} 条：{rev}")
    if rev and rev[0]["mentions"] != 3:
        failures.append(f"mentions 计数错误：期望 3，实际 {rev[0]['mentions'] if rev else 0}")
    if rev_keys != {("GET", "/api/v1/packages/*")}:
        failures.append(f"文档侧归一化错误：{rev_keys}")
    if fwd_keys != {("GET", "/api/v1/packages/*")}:
        failures.append(f"代码侧归一化错误（<x> 应与 {{x}} 等价）：{fwd_keys}")
    if rev_keys & fwd_keys != {("GET", "/api/v1/packages/*")}:
        failures.append(f"两侧应完全匹配：rev={rev_keys} fwd={fwd_keys}")

    # -- 不变量：直接对真实仓库跑一遍，任何一条数学关系不成立都算失败
    real = collect()
    if not real["invariants_ok"]:
        failures.append(f"不变量不成立：{ {k: v for k, v in real['invariants'].items() if not v} }")
    counts = real["counts"]
    deprecated_keys = {"rev", "fwd"}
    leaked = sorted(deprecated_keys & set(real))
    if leaked:
        failures.append(f"输出里还有废弃键 {leaked}（它们的含义与项目习惯相反，禁止回归）")
    leaked_counts = sorted(deprecated_keys & set(counts))
    if leaked_counts:
        failures.append(f"counts 里还有废弃键 {leaked_counts}")
    for required in ("documented_total", "code_total", "matched", "only_in_code", "only_in_docs"):
        if required not in counts:
            failures.append(f"counts 缺少必需键 {required}")

    if counts["matched"] != counts["code_total"]:
        failures.append(
            "代码侧有未登记在文档里的路由："
            f"{counts['code_total'] - counts['matched']} 条 → {real['only_in_code']}"
        )

    if failures:
        print("self-test 失败：", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print(
        "self-test 通过：样本 文档 {doc}/代码 {code} 条；去重样本 mentions=3→1 条；"
        "真实仓库 documented_total={rev} code_total={fwd} matched={matched}"
        " only_in_code={oc} only_in_docs={od}；脏格式已报警".format(
            doc=len(doc_keys),
            code=len(code_keys),
            rev=counts["documented_total"],
            fwd=counts["code_total"],
            matched=counts["matched"],
            od=counts["only_in_docs"],
            oc=counts["only_in_code"],
        )
    )
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文档 ↔ 实现 路由一致性（唯一权威实现）")
    parser.add_argument("--docs", default=str(DOCS), help="契约文档路径")
    parser.add_argument("--api-dir", default=str(API_DIR), help="api 蓝图目录")
    parser.add_argument("--self-test", action="store_true", help="跑内置样本自检")
    parser.add_argument("--strict", action="store_true", help="文档有、代码没有的路由 → 退出码 1")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.self_test:
        return self_test()

    result = collect(Path(args.docs), Path(args.api_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))

    # 断言而非「跑通就行」：数学关系不成立 = 解析器坏了，宁可非 0 退出也不许给出精确数字
    broken = {name: value for name, value in result["invariants"].items() if not value}
    if broken:
        print(f"[ERROR] 不变量不成立：{broken}", file=sys.stderr)
        print(
            f"        counts={result['counts']}"
            f" only_in_code={len(result['only_in_code'])}",
            file=sys.stderr,
        )
        return 2
    if args.strict and result["only_in_docs"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
