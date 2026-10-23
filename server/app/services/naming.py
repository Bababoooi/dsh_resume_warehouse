"""导出文件名模板：解析、变量替换、净化、长度与冲突处理（API-CONTRACT §9 的唯一实现）。

纯函数：不读库、不读环境变量，所有上下文由调用方传入（便于单元测试与
``POST /naming/validate`` 恒 200 的语义）。

语法：``{var}`` 或 ``{var:%Y%m%d}``；``{{`` / ``}}`` 为字面大括号；
变量名 ``[a-z][a-z0-9_]*``；未知变量 → ``NAMING_UNKNOWN_VAR``。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

_EMOJI_RANGES = (
    (0x1F300, 0x1FAFF),
    (0x1F000, 0x1F2FF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0xFE00, 0xFE0F),
    (0x1F1E6, 0x1F1FF),
)

_ILLEGAL_CHARS = set('\\/:*?"<>|')
#: 变量合法名
VAR_RE = re.compile(r"^[a-z][a-z0-9_]*$")
#: 允许的日期格式（``strftime`` 指令白名单，避免任意指令如 %n 注入）
DATE_TOKENS = ("%Y", "%m", "%d", "%H", "%M", "%S", "%j", "%W")
MAX_STEM_CHARS = 120
MAX_UTF8_BYTES = 200
WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

#: 内置变量（顺序即展示顺序）
KNOWN_VARS: tuple[str, ...] = ("name", "school", "position", "company", "date", "version", "lang")


@dataclass
class NamingVariable:
    name: str
    value: str
    source: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "value": self.value, "source": self.source}


@dataclass
class NamingIssue:
    code: str
    message: str
    field: str = "pattern"

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "field": self.field}


@dataclass
class NamingWarning:
    code: str
    message: str
    field: str = "pattern"

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "field": self.field}


@dataclass
class NamingResult:
    valid: bool
    resolved: str
    filename: str
    variables: list[NamingVariable] = field(default_factory=list)
    warnings: list[NamingWarning] = field(default_factory=list)
    errors: list[NamingIssue] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "resolved": self.resolved,
            "filename": self.filename,
            "variables": [v.as_dict() for v in self.variables],
            "warnings": [w.as_dict() for w in self.warnings],
            "errors": [e.as_dict() for e in self.errors],
        }


# --------------------------------------------------------------------------------------
# 词法解析
# --------------------------------------------------------------------------------------


@dataclass
class _Token:
    kind: str  # "literal" | "var"
    text: str
    name: str = ""
    fmt: str | None = None


def tokenize(pattern: str) -> tuple[list[_Token], list[NamingIssue]]:
    """手写扫描器：正确处理 ``{{`` / ``}}`` 转义与未闭合大括号。"""
    tokens: list[_Token] = []
    issues: list[NamingIssue] = []
    buf: list[str] = []
    i = 0
    length = len(pattern)
    while i < length:
        char = pattern[i]
        if char == "{":
            if i + 1 < length and pattern[i + 1] == "{":
                buf.append("{")
                i += 2
                continue
            end = pattern.find("}", i + 1)
            if end == -1:
                issues.append(NamingIssue("NAMING_SYNTAX", "命名模板存在未闭合的 '{'", "pattern"))
                i = length
                break
            if buf:
                tokens.append(_Token("literal", "".join(buf)))
                buf = []
            inner = pattern[i + 1 : end].strip()
            if not inner:
                issues.append(NamingIssue("NAMING_SYNTAX", "命名模板存在空变量 '{}'", "pattern"))
                i = end + 1
                continue
            name, _, fmt = inner.partition(":")
            name = name.strip()
            fmt = fmt.strip() or None
            if not VAR_RE.match(name):
                issues.append(
                    NamingIssue("NAMING_SYNTAX", f"变量名不合法：{{{inner}}}（需 ^[a-z][a-z0-9_]*$）", "pattern")
                )
                i = end + 1
                continue
            tokens.append(_Token("var", inner, name=name, fmt=fmt))
            i = end + 1
            continue
        if char == "}":
            if i + 1 < length and pattern[i + 1] == "}":
                buf.append("}")
                i += 2
                continue
            issues.append(NamingIssue("NAMING_SYNTAX", "命名模板存在多余的 '}'（字面大括号请写 '}}'）", "pattern"))
            i += 1
            continue
        buf.append(char)
        i += 1
    if buf:
        tokens.append(_Token("literal", "".join(buf)))
    return tokens, issues


def _valid_date_format(fmt: str) -> bool:
    """只允许白名单指令 + 普通字符/分隔符。"""
    if not fmt:
        return False
    remainder = fmt
    for token in DATE_TOKENS:
        remainder = remainder.replace(token, "")
    return "%" not in remainder


def _format_date(fmt: str | None, now: datetime) -> str:
    if not fmt:
        return now.strftime("%Y%m%d")
    return now.strftime(fmt)


# --------------------------------------------------------------------------------------
# 变量解析
# --------------------------------------------------------------------------------------


def build_variables(
    *,
    lang: str,
    profile: Mapping[str, Any] | None,
    position: str | None = None,
    company: str | None = None,
    overrides: Mapping[str, str] | None = None,
    date_value: str | None = None,
    version: str | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, NamingVariable], list[NamingWarning]]:
    """按契约的优先级解析 7 个内置变量；空串视为「未提供」。"""
    profile = profile or {}
    overrides = overrides or {}
    warnings: list[NamingWarning] = []
    resolved: dict[str, NamingVariable] = {}
    is_zh = lang != "en"

    def pick(lang_value: Any, en_value: Any) -> Any:
        return lang_value if is_zh else (en_value or lang_value)

    candidates: dict[str, tuple[Any, str]] = {
        "name": (pick(profile.get("name_zh"), profile.get("name_en")), "profile.name_zh"),
        "school": (pick(profile.get("school_zh"), profile.get("school_en")), "profile.school_zh"),
        "position": (position, "build.position"),
        "company": (company, "jd.company_name"),
    }
    for key, (value, source) in candidates.items():
        override = overrides.get(key)
        if override is not None and str(override).strip() != "":
            resolved[key] = NamingVariable(key, str(override), "override")
        elif value is not None and str(value).strip() != "":
            resolved[key] = NamingVariable(key, str(value), source)

    stamp = now or datetime.now().astimezone()
    resolved["date"] = NamingVariable("date", date_value or _format_date("%Y%m%d", stamp), "export_time")
    resolved["version"] = NamingVariable("version", (version or overrides.get("version") or "v1"), "override")
    resolved["lang"] = NamingVariable("lang", "en" if not is_zh else "zh", "build.lang")
    return resolved, warnings


# --------------------------------------------------------------------------------------
# 净化
# --------------------------------------------------------------------------------------


def _strip_emoji(text: str) -> tuple[str, bool]:
    out: list[str] = []
    touched = False
    for char in text:
        code = ord(char)
        if char == "\u200d" or char == "\u20e3":
            touched = True
            continue
        if any(low <= code <= high for low, high in _EMOJI_RANGES):
            touched = True
            continue
        out.append(char)
    return "".join(out), touched


def sanitize_stem(stem: str) -> tuple[str, list[NamingWarning]]:
    """契约 §9.3 的 8 步净化。返回 (净化后文本, warnings)。"""
    warnings: list[NamingWarning] = []
    text = unicodedata.normalize("NFC", stem)

    text, emoji_stripped = _strip_emoji(text)
    if emoji_stripped:
        warnings.append(NamingWarning("EMOJI_STRIPPED", "文件名中的表情符号已移除"))

    # 控制字符
    cleaned_chars = []
    invalid_hit = False
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("C"):
            invalid_hit = True
            continue
        if char in _ILLEGAL_CHARS:
            invalid_hit = True
            cleaned_chars.append("-")
            continue
        cleaned_chars.append(char)
    text = "".join(cleaned_chars)
    if invalid_hit:
        warnings.append(
            NamingWarning("NAMING_INVALID_CHARS", "文件名包含 \\ / : * ? \" < > | 或控制字符，已替换为 '-'")
        )

    # 折叠连字符/空白：连续 - 与空格统一成单个 '-'
    text = re.sub(r"[\s\u3000]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)

    # 去首尾的空白与 . - _
    text = text.strip(" .-_")

    # 路径穿越与 Windows 特殊名
    text = text.replace("..", "-").replace("._", "-")
    if text.upper() in WINDOWS_RESERVED:
        text = f"_{text}"

    if text and text != stem:
        warnings.append(NamingWarning("NAMING_SANITIZED", "文件名已按跨平台规则净化"))
    return text, warnings


def _truncate(text: str) -> tuple[str, bool]:
    truncated = False
    if len(text) > MAX_STEM_CHARS:
        text = text[:MAX_STEM_CHARS]
        truncated = True
    while len(text.encode("utf-8")) > MAX_UTF8_BYTES and text:
        text = text[:-1]
        truncated = True
    return text.rstrip(" .-_"), truncated


# --------------------------------------------------------------------------------------
# 顶层入口
# --------------------------------------------------------------------------------------


def resolve_filename(
    pattern: str,
    *,
    lang: str = "zh",
    profile: Mapping[str, Any] | None = None,
    position: str | None = None,
    company: str | None = None,
    overrides: Mapping[str, str] | None = None,
    date_value: str | None = None,
    version: str | None = None,
    extension: str = "pdf",
    now: datetime | None = None,
    exists: Sequence[str] | None = None,
) -> NamingResult:
    """解析模板 → 变量替换 → 净化 → 长度校验 → 冲突后缀。

    ``exists`` 传入同目录已存在的文件名（含扩展名）时，若冲突则追加 ``-2``/``-3``。
    任何 ``errors`` 非空时调用方**不得**落盘（契约 §9.5）。
    """
    errors: list[NamingIssue] = []
    warnings: list[NamingWarning] = []

    if not pattern or not pattern.strip():
        return NamingResult(
            valid=False,
            resolved="",
            filename="",
            errors=[NamingIssue("NAMING_EMPTY", "命名模板不能为空")],
        )

    tokens, syntax_errors = tokenize(pattern)
    errors.extend(syntax_errors)

    if not any(token.kind == "var" for token in tokens) and not errors:
        warnings.append(
            NamingWarning("NO_VARIABLE", "命名模板不含任何变量，导出多个文件时可能重名")
        )

    variables, var_warnings = build_variables(
        lang=lang,
        profile=profile,
        position=position,
        company=company,
        overrides=overrides,
        date_value=date_value,
        version=version,
        now=now,
    )
    warnings.extend(var_warnings)

    used: list[NamingVariable] = []
    parts: list[str] = []
    stamp = now or datetime.now().astimezone()
    for token in tokens:
        if token.kind == "literal":
            parts.append(token.text)
            continue
        if token.name not in KNOWN_VARS:
            errors.append(
                NamingIssue(
                    "NAMING_UNKNOWN_VAR",
                    f"未知变量 {{{token.name}}}；可用变量：{'、'.join(KNOWN_VARS)}",
                    f"pattern.{token.name}",
                )
            )
            continue
        variable = variables.get(token.name)
        if variable is None or not variable.value:
            errors.append(
                NamingIssue(
                    "NAMING_MISSING_VAR",
                    f"变量 {{{token.name}}} 没有可用的值，请先补全个人资料或岗位信息",
                    token.name,
                )
            )
            continue
        value = variable.value
        if token.name == "date" and token.fmt:
            if not _valid_date_format(token.fmt):
                errors.append(
                    NamingIssue(
                        "NAMING_SYNTAX",
                        f"日期格式 {{{token.name}:{token.fmt}}} 不合法（仅支持 %Y %m %d %H %M %S）",
                        "pattern.date",
                    )
                )
                continue
            value = _format_date(token.fmt, stamp)
        used.append(variable)
        parts.append(value)

    resolved = "".join(parts)
    if not errors and not resolved.strip():
        errors.append(NamingIssue("NAMING_EMPTY", "命名模板替换后为空"))

    stem, sanitize_warnings = sanitize_stem(resolved)
    warnings.extend(sanitize_warnings)

    stem, truncated = _truncate(stem)
    if truncated:
        warnings.append(
            NamingWarning("NAMING_TRUNCATED", f"文件名超过 {MAX_STEM_CHARS} 字符或 {MAX_UTF8_BYTES} 字节，已截断")
        )
    if not stem and not errors:
        errors.append(NamingIssue("NAMING_EMPTY", "净化后文件名为空，请检查模板中的变量名"))

    ext = extension.lstrip(".").lower() or "pdf"
    filename = f"{stem}.{ext}" if stem else ""

    # 冲突后缀：只在真正导出时使用（validate 传入 exists 即可预览）
    if stem and exists:
        taken = {name.lower() for name in exists}
        if filename.lower() in taken:
            index = 2
            while f"{stem}-{index}.{ext}".lower() in taken:
                index += 1
            filename = f"{stem}-{index}.{ext}"
            warnings.append(
                NamingWarning("NAMING_COLLISION_SUFFIXED", f"同名文件已存在，已改用 {filename}")
            )

    # 契约 §9.3：不合法时 ``resolved``/``filename`` 都是 null（§17.7 实测口径为 ""），
    # 绝不能回一个「看起来像真的」残缺文件名——前端会拿它当预览、用户会以为能导出。
    valid = not errors
    return NamingResult(
        valid=valid,
        resolved=resolved if valid else "",
        filename=filename if valid else "",
        variables=used,
        warnings=warnings,
        errors=errors,
    )


def pattern_errors(pattern: str) -> list[NamingIssue]:
    """只校验「模板本身」是否合法（语法 + 未知变量），不校验变量值是否齐。

    用途：``PATCH /builds/{id}`` 写入 naming_pattern 时先拦非法模板（AC-NAME-03），
    避免把不可解析的模板落库、等到导出才炸。
    """
    if not pattern:
        return []
    tokens, issues = tokenize(pattern)
    errors = list(issues)
    for token in tokens:
        if token.kind == "var" and token.name not in KNOWN_VARS:
            errors.append(
                NamingIssue("NAMING_UNKNOWN_VAR", f"未知变量 {{{token.name}}}（可用：{'、'.join(KNOWN_VARS)}）", "naming_pattern")
            )
    return errors


def raise_pattern_errors(pattern: str) -> None:
    """非法模板直接 422（不落库）。"""
    errors = pattern_errors(pattern)
    if not errors:
        return
    from ..errors import ApiError

    first = errors[0]
    raise ApiError(
        first.code,
        first.message,
        details={"field": "naming_pattern", "errors": [issue.as_dict() for issue in errors]},
        hint="可用变量：" + "、".join("{" + name + "}" for name in KNOWN_VARS),
    )


def raise_on_errors(result: NamingResult) -> None:
    """导出链路用：第一条 error 直接转成 422 ApiError。"""
    if not result.errors:
        return
    from ..errors import ApiError

    first = result.errors[0]
    hints = {
        "NAMING_MISSING_VAR": "去「个人资料」补全姓名/学校，或在导出页把命名模板改成不含该变量的形式",
        "NAMING_UNKNOWN_VAR": "命名模板只支持 {name}{school}{position}{company}{date}{version}{lang}",
        "NAMING_SYNTAX": "检查命名模板的大括号是否闭合、变量名是否合法",
        "NAMING_EMPTY": "模板解析后为空，请至少保留一个变量或文字",
        "NAMING_TOO_LONG": "缩短命名模板或变量值",
    }
    raise ApiError(
        first.code,
        first.message,
        details={
            "field": first.field,
            "errors": [issue.as_dict() for issue in result.errors],
            "warnings": [warning.as_dict() for warning in result.warnings],
        },
        hint=hints.get(first.code),
    )
