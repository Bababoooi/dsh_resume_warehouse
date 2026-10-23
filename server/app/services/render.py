"""渲染：IR → PDF / HTML（中文版式按 ARCHITECTURE §7.5.1 冻结常量）。

为什么是 reportlab 手排版而不是模板引擎
--------------------------------------
用户原件是 1 页 A4、正文 10.5pt/1.62、页边距上下 8.3/16.4、左右 14.8/15.6、照片
89.28×89.28pt 距顶 3.82 距右 9.13。这些数字必须**可复现地**出现在导出 PDF 里，
而且要能在「装不下」时按 10.5 → 10.0 → 9.5 降档并如实报告，所以：

* 版式常量集中在 ``DENSITY`` / ``LADDER`` / ``PHOTO`` 三个字典里（唯一来源）；
* 降档判定用 ``Paragraph.wrap()`` **实测**高度，不估算（估算会在长行折行时失真）；
* 照片用 canvas 绝对坐标画（``x0 = PAGE_W - PHOTO.right - PHOTO.size``），
  不随字号降档缩放，也不参与 Flowable 排版（否则右下角会被版心裁掉）；
* 溢出算式以**可用高度**为分母：``PAGE_H - margin_top - margin_bottom``。

字体：宋体 ``Songti.ttc`` subfont 6（常规）/ 1（粗体），必须
``registerFontFamily`` + ``addMapping``，否则 ``<b>`` 会静默退化成常规字重。
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .. import errors
from ..errors import ApiError
from . import envcheck

# --------------------------------------------------------------------------
# 冻结常量（ARCHITECTURE §7.5.1，唯一来源；改这里等于改版式）
# --------------------------------------------------------------------------
PAGE_W = 595.5
PAGE_H = 842.25

DENSITY: dict[str, dict[str, float]] = {
    # 用户原件实测：上下 8.3 / 16.4，左右 14.8 / 15.6
    "original": {"top": 8.3, "bottom": 16.4, "left": 14.8, "right": 15.6},
    # 宽松档（15/16mm）：只在用户显式选 relaxed 时用，允许 2 页
    "relaxed": {"top": 45.35, "bottom": 45.35, "left": 42.5, "right": 45.35},
}

#: 字号阶梯 (body_pt, leading_ratio)；9.5pt 是硬下限，再小就不可读
#: 字号阶梯：首档 11.0pt 与用户原件一致（原件正文 11.0/12.0，行距 12.0 ≈ 1.09 倍）。
#: 行距固定 ``size × 1.15``——原实现用 1.62/1.50/1.45 的「更小字号 + 更大行距」，
#: 等于用更小的字占更多的地（实测 45 行 × 13.8pt 触到 9.5pt 下限）。
#: 装不下才逐档下降，每次降档都发 PAGE_FIT_DOWNGRADED。
LADDER: tuple[tuple[float, float], ...] = ((11.0, 1.15), (10.5, 1.15), (10.0, 1.15), (9.5, 1.15))
MIN_BODY_PT = 9.5

#: 照片几何：边长不再写死 89.28pt，而是**与标题区等高**（用户要求）。
#: 标题区 = 姓名行（22pt）+ 两行元信息（联系方式、到岗时间）；照片上沿与姓名上沿齐平、
#: 右沿与正文右缘齐平，看上去是「标题区里的一个方块」，而不是抢眼的贴纸。
PHOTO = {"size": 49.3, "top": 8.3, "right": 15.62}

NAME_LEADING = 26.0


def photo_box(body_pt: float = 11.0, leading_ratio: float = 1.15) -> dict[str, float]:
    """照片边长 = 标题区高度（姓名行 + 两行元信息），预览侧与渲染侧共用同一口径。"""
    return {"size": round(NAME_LEADING + 2 + body_pt * leading_ratio * 2, 2)}

FONT_NAME = "CV"
FONT_PATH = envcheck.SONGTI_PATH

#: 英文版用 Times（用户原件英文简历就是 Times 系）；中文版用宋体
FONT_BY_LANG: dict[str, tuple[str, str]] = {
    "zh": (FONT_NAME, f"{FONT_NAME}-Bold"),
    "en": ("Times-Roman", "Times-Bold"),
}


_CJK_RE = re.compile(r"[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]")


def fonts_for(lang: str) -> tuple[str, str]:
    return FONT_BY_LANG.get(lang, FONT_BY_LANG["zh"])


def has_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))
REGULAR_INDEX = envcheck.REGULAR_SUBFONT_INDEX
BOLD_INDEX = envcheck.BOLD_SUBFONT_INDEX

_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_fonts_registered = False


# --------------------------------------------------------------------------
# 字体
# --------------------------------------------------------------------------
def register_fonts() -> None:
    """注册宋体（幂等）。缺字体 → ``FONT_UNAVAILABLE``，绝不静默换字体。"""
    global _fonts_registered
    if _fonts_registered:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if not FONT_PATH.exists():
        raise ApiError(
            "FONT_UNAVAILABLE",
            f"缺少中文字体 {FONT_PATH}，无法生成中文 PDF",
            details={"path": str(FONT_PATH)},
            hint="macOS 自带宋体；若被删可从系统安装包里恢复，或改用 DOCX 导出",
        )
    try:
        pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_PATH), subfontIndex=REGULAR_INDEX))
        pdfmetrics.registerFont(TTFont(f"{FONT_NAME}-Bold", str(FONT_PATH), subfontIndex=BOLD_INDEX))
        pdfmetrics.registerFontFamily(
            FONT_NAME,
            normal=FONT_NAME,
            bold=f"{FONT_NAME}-Bold",
            italic=FONT_NAME,
            boldItalic=f"{FONT_NAME}-Bold",
        )
    except Exception as exc:  # pragma: no cover - 字体文件损坏才会到这
        raise ApiError(
            "FONT_UNAVAILABLE",
            "中文字体加载失败",
            details={"path": str(FONT_PATH), "type": type(exc).__name__},
            hint="检查 Songti.ttc 是否完整",
        ) from exc
    _fonts_registered = True


# --------------------------------------------------------------------------
# 文本净化
# --------------------------------------------------------------------------
def sanitize_text(text: str) -> tuple[str, int]:
    """NFC 归一 + 剥 emoji/控制字符（返回 ``(文本, 剥掉的字符数)``）。"""
    if not text:
        return "", 0
    normalized = unicodedata.normalize("NFC", str(text))
    stripped = _EMOJI_RE.sub("", normalized)
    stripped = _CONTROL_RE.sub("", stripped)
    removed = len(normalized) - len(stripped)
    return re.sub(r"[ \t]{2,}", " ", stripped).strip(), removed


def escape_xml(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


@dataclass
class RenderResult:
    """渲染结果：字节 + 实测几何 + warnings。"""

    data: bytes
    page_count: int
    body_pt: float
    leading: float
    used_height_pt: float
    available_height_pt: float
    warnings: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# HTML（预览用，无外部资源、无脚本）
# --------------------------------------------------------------------------
def render_html(ir: Mapping[str, Any]) -> str:
    """生成预览 HTML（自包含、CSP 友好；不引任何外部资源）。"""
    header = ir.get("header") or {}
    lang = str(ir.get("lang") or "zh")
    # 预览用首档版式（与 PDF 未降档时逐字一致）；降档只发生在 PDF 的装不下分支。
    body_pt, ratio = LADDER[0]
    leading = round(body_pt * ratio, 2)
    m = DENSITY["original"]
    NAME_PT = 22.0
    META_PT = 10.0
    HEADING_PT = 13.0
    HEADING_SPACE_BEFORE = 6
    HEADING_SPACE_AFTER = 2

    def esc(value: Any) -> str:
        text, _ = sanitize_text(str(value or ""))
        return escape_xml(text)

    parts: list[str] = [
        "<!doctype html><html lang=\"" + ("en" if lang == "en" else "zh-CN") + "\">",
        '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>简历预览</title>",
        "<style>",
        ":root{--ink:#1f2328;--muted:#5c6470;--rule:#d8dde5}",
        "*{box-sizing:border-box}",
        "body{margin:0;background:#eef1f5;font-family:'Songti SC','Source Han Serif SC',serif;color:var(--ink)}",
        # 版式常量唯一来源：HTML 预览与 PDF 都从 DENSITY/LADDER 派生，
        # 否则「预览 10.5/1.62、PDF 11.0/1.15」就是所见非所得。
        f".sheet{{width:{PAGE_W}pt;min-height:{PAGE_H}pt;margin:16px auto;background:#fff;"
        f"padding:{m['top']}pt {m['right']}pt {m['bottom']}pt {m['left']}pt;position:relative;"
        "box-shadow:0 2px 12px rgba(0,0,0,.12)}",
        f".photo{{position:absolute;top:{PHOTO['top']}pt;right:{PHOTO['right']}pt;"
        f"width:{PHOTO['size']}pt;height:{PHOTO['size']}pt;object-fit:cover;border-radius:2pt}}",
        f".name{{font-size:{NAME_PT}pt;font-weight:700;text-align:center;margin:0 0 2pt}}",
        f".meta{{font-size:{META_PT}pt;color:var(--muted);text-align:center;margin:0}}",
        f"h2{{font-size:{HEADING_PT}pt;font-weight:700;margin:{HEADING_SPACE_BEFORE}pt 0 {HEADING_SPACE_AFTER}pt;"
        "padding-bottom:1pt;border-bottom:.6pt solid var(--rule)}",
        ".entry{margin:0 0 4pt}",
        f".entry-head{{display:flex;justify-content:space-between;gap:8pt;font-size:{round(body_pt + 0.5, 2)}pt;font-weight:700}}",
        f".entry-sub{{font-size:{body_pt}pt;color:var(--muted)}}",
        "ul{margin:2pt 0 0;padding-left:16pt}",
        f"li{{font-size:{body_pt}pt;line-height:{leading}pt;margin:0 0 1pt}}",
        f".skills div{{font-size:{body_pt}pt;line-height:{leading}pt}}",
        "</style></head><body><article class=\"sheet\">",
    ]
    if header.get("photo_path"):
        parts.append(f'<img class="photo" src="/api/v1/files/profile-photo" alt="照片">')
    if header.get("name"):
        parts.append(f'<h1 class="name">{esc(header["name"])}</h1>')
    for key in ("contact_line",):
        if header.get(key):
            parts.append(f'<p class="meta">{esc(header[key])}</p>')
    if header.get("available"):
        _label = (header.get("labels") or {}).get("available", "到岗时间")
        _sep = ": " if any(c.isascii() and c.isalpha() for c in _label) else "："
        parts.append(f'<p class="meta">{_label}{_sep}{esc(header["available"])}</p>')

    for section in ir.get("sections") or []:
        parts.append(f'<section><h2>{esc(section.get("heading"))}</h2>')
        if section.get("kind") == "skills":
            parts.append('<div class="skills">')
            for line in section.get("skills") or []:
                parts.append(f"<div>{esc(line)}</div>")
            parts.append("</div></section>")
            continue
        for entry in section.get("entries") or []:
            parts.append('<div class="entry">')
            head = esc(entry.get("title"))
            date = esc(entry.get("date"))
            if head or date:
                parts.append(f'<div class="entry-head"><span>{head}</span><span>{date}</span></div>')
            sub_bits = [esc(entry.get("org")), esc(entry.get("role")), esc(entry.get("location"))]
            sub = " · ".join(bit for bit in sub_bits if bit)
            if sub:
                parts.append(f'<div class="entry-sub">{sub}</div>')
            if entry.get("facts"):
                parts.append('<div class="facts">')
                for line in entry.get("facts") or []:
                    parts.append(f'<p class="fact">{esc(line)}</p>')
                parts.append("</div>")
            if entry.get("bullets"):
                parts.append("<ul>")
                for line in entry.get("bullets") or []:
                    parts.append(f"<li>{esc(line)}</li>")
                parts.append("</ul>")
            parts.append("</div>")
        parts.append("</section>")
    parts.append("</article></body></html>")
    return "".join(parts)


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
def _styles(body_pt: float, leading_ratio: float, *, lang: str = "zh"):
    from reportlab.lib.styles import ParagraphStyle

    leading = round(body_pt * leading_ratio, 2)
    regular, bold = fonts_for(lang)
    # 行末悬挂标点预留：CJK 逐字断行时「、。，；：）」」可能被放在行尾边缘之外
    # （实测 9.5pt 档「、」越界 1.95pt）。正文段落统一在右侧留出半个字宽，
    # 末字标点落进这条预留带里，视觉上等同悬挂，且保证 x1 不越过版心右边界。
    hang = round(body_pt * 0.5, 2)
    common = {"fontName": regular, "wordWrap": "CJK", "rightIndent": hang}
    return {
        "name": ParagraphStyle("name", fontName=bold, fontSize=22, leading=24, alignment=1, wordWrap="CJK"),
        "meta": ParagraphStyle("meta", fontSize=10, leading=13, alignment=1, textColor="#333333", **common),
        "heading": ParagraphStyle(
            "heading", fontName=bold, fontSize=13, leading=15, spaceBefore=6, spaceAfter=2, wordWrap="CJK", rightIndent=hang
        ),
        "entry": ParagraphStyle("entry", fontName=bold, fontSize=body_pt + 0.5, leading=leading, spaceBefore=3, wordWrap="CJK", rightIndent=hang),
        "sub": ParagraphStyle("sub", fontSize=body_pt, leading=leading, textColor="#444444", **common),
        "bullet": ParagraphStyle(
            "bullet", fontSize=body_pt, leading=leading, leftIndent=10, firstLineIndent=-10, **common
        ),
        "skill": ParagraphStyle("skill", fontSize=body_pt, leading=leading, **common),
        "date": ParagraphStyle("date", fontSize=body_pt, leading=leading, alignment=2, **common),
    }


def _collect_warnings(ir: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """把 IR 里的文本过一遍净化，统计剥掉的 emoji。"""
    warnings = list(ir.get("warnings") or [])
    stripped_total = 0
    for section in ir.get("sections") or []:
        for entry in section.get("entries") or []:
            for key in ("title", "org", "role", "location", "date"):
                _, removed = sanitize_text(str(entry.get(key) or ""))
                stripped_total += removed
            for line in list(entry.get("bullets") or []) + list(entry.get("facts") or []):
                _, removed = sanitize_text(str(line))
                stripped_total += removed
        for line in section.get("skills") or []:
            _, removed = sanitize_text(str(line))
            stripped_total += removed
    header = ir.get("header") or {}
    for key in ("name", "contact_line", "available"):
        _, removed = sanitize_text(str(header.get(key) or ""))
        stripped_total += removed
    if stripped_total:
        warnings.append(
            {
                "code": "EMOJI_STRIPPED",
                "severity": "info",
                "message": f"正文里有 {stripped_total} 个 emoji/控制字符无法用宋体渲染，导出时已剥离",
                "details": {"count": stripped_total},
            }
        )
    return warnings, stripped_total


def _header_story(
    ir: Mapping[str, Any], body_pt: float, leading_ratio: float, *, lang: str = "zh"
) -> list[Any]:
    """页眉三件（姓名 / 联系方式 / 到岗时间）。

    单独抽出来只有一个理由：**照片边长要与标题区等高，必须量真实高度**——
    靠常量估会在中英切换时错位。
    """
    from reportlab.platypus import Paragraph, Spacer

    styles = _styles(body_pt, leading_ratio, lang=lang)
    styles_cjk = _styles(body_pt, leading_ratio, lang="zh")
    header = ir.get("header") or {}
    story: list[Any] = []

    def para(text: Any, style: str) -> Any:
        clean, _ = sanitize_text(str(text or ""))
        if not clean:
            return None
        key = styles_cjk if has_cjk(clean) else styles
        return Paragraph(escape_xml(clean), key[style])

    if header.get("name"):
        story.append(para(header["name"], "name"))
        story.append(Spacer(1, 2))
    for key in ("contact_line",):
        item = para(header.get(key), "meta")
        if item is not None:
            story.append(item)
    if header.get("available"):
        labels = header.get("labels") or {}
        label = labels.get("available", "到岗时间")
        sep = ": " if any(c.isascii() and c.isalpha() for c in label) else "："
        item = para(f"{label}{sep}{header['available']}", "meta")
        if item is not None:
            story.append(item)
    return story


def _build_story(
    ir: Mapping[str, Any],
    body_pt: float,
    leading_ratio: float,
    width: float,
    *,
    lang: str = "zh",
    gap: float = 0.0,
):
    from reportlab.lib.units import mm  # noqa: F401  (保持 reportlab 已导入)
    from reportlab.platypus import Paragraph, Spacer

    styles = _styles(body_pt, leading_ratio, lang=lang)
    styles_cjk = _styles(body_pt, leading_ratio, lang="zh")

    def pick(text: str, key: str):
        """含中文的段落用宋体，纯西文用当前语言字体（英文版才是 Times）。"""
        return styles_cjk[key] if has_cjk(text) else styles[key]
    story: list[Any] = _header_story(ir, body_pt, leading_ratio, lang=lang)

    def para(text: Any, style: str, **kwargs) -> Any:
        clean, _ = sanitize_text(str(text or ""))
        if not clean:
            return None
        return Paragraph(escape_xml(clean), pick(clean, style), **kwargs)

    for section in ir.get("sections") or []:
        if gap:
            story.append(Spacer(1, gap))
        heading = para(section.get("heading"), "heading")
        if heading is not None:
            story.append(heading)
        if section.get("kind") == "skills":
            for line in section.get("skills") or []:
                if gap:
                    story.append(Spacer(1, round(gap * 0.35, 2)))
                item = para(line, "skill")
                if item is not None:
                    story.append(item)
            continue
        for entry in section.get("entries") or []:
            if gap:
                story.append(Spacer(1, round(gap * 0.6, 2)))
            title = sanitize_text(str(entry.get("title") or ""))[0].strip()
            date = sanitize_text(str(entry.get("date") or ""))[0].strip()
            # 标题若已经就是单位名（导入的经历常见），不再重复一次
            sub_parts = []
            for key in ("org", "role", "location"):
                value = sanitize_text(str(entry.get(key) or ""))[0].strip()
                if not value or value in title or value in sub_parts:
                    continue
                sub_parts.append(value)
            if title or date:
                # 用户原件的经历是「公司 - 职位 …… 日期」同一行；
                # 副行另起会让每条经历多占 1–2 行（实测 33 行被撑到 45 行）。
                story.append(_entry_head(title, sub_parts, date, styles, styles_cjk, width, body_pt))
            for line in entry.get("bullets") or []:
                if gap:
                    story.append(Spacer(1, round(gap * 0.35, 2)))
                item = para(f"· {line}", "bullet")
                if item is not None:
                    story.append(item)
            # facts 是简历里的整段固定文本（GPA/CET/主修课程），行首不加 bullet 标记
            for line in entry.get("facts") or []:
                if gap:
                    story.append(Spacer(1, round(gap * 0.3, 2)))
                item = para(str(line), "bullet")
                if item is not None:
                    story.append(item)
    return story


def _entry_head(title: str, sub_parts: Sequence[str], date: str, styles, styles_cjk, width: float, body_pt: float):
    """条目标题行：``标题 · 单位 · 职位``（加粗标题 + 常规副信息）在左，日期贴右。

    用户原件的经历一律是「公司 - 职位 …… 日期」同一行；把单位/职位另起一行会让
    每条经历多占 1–2 行（实测把 33 行的正文撑到 45 行、触发 9.5pt 降档）。
    """
    from reportlab.platypus import Paragraph, Table, TableStyle

    plain = " · ".join(part for part in [title, *sub_parts] if part)
    left_style = styles_cjk["entry"] if has_cjk(plain) else styles["entry"]
    right_style = styles_cjk["date"] if has_cjk(date) else styles["date"]
    left_html = f"<b>{escape_xml(title)}</b>" if title else ""
    if sub_parts:
        tail = escape_xml(" · ".join(sub_parts))
        left_html = f"{left_html}　{tail}" if left_html else tail
    left = Paragraph(left_html or "", left_style)
    right = Paragraph(escape_xml(date), right_style) if date else Paragraph("", right_style)
    # 日期列按实际文字宽度给（12%–22% 版心），其余全部留给标题
    date_width = 0.02 * width
    if date:
        approx = 0.62 * body_pt * max(1, len(date))
        date_width = min(0.22 * width, max(0.12 * width, approx))
    table = Table([[left, right]], colWidths=[width - date_width, date_width])
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _measure(story: Sequence[Any], width: float, available: float) -> float:
    """用真实 wrap 逐段量高度（比估算可靠）。"""
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    probe = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    total = 0.0
    for flowable in story:
        space_before = float(getattr(flowable, "getSpaceBefore", lambda: 0)() or 0)
        space_after = float(getattr(flowable, "getSpaceAfter", lambda: 0)() or 0)
        _, height = flowable.wrap(width, available)
        total += space_before + height + space_after
    probe.save()
    return round(total, 2)


def render_pdf(
    ir: Mapping[str, Any],
    *,
    density: str = "original",
    photo_bytes: bytes | None = None,
) -> RenderResult:
    """渲染 PDF：单页优先，装不下按阶梯降档，仍不下就 2 页并如实报警。"""
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import SimpleDocTemplate

    lang = str(ir.get("lang") or "zh")
    register_fonts()  # 英文版也可能夹中文（项目名/公司名），宋体必须可用
    density = density if density in DENSITY else "original"
    margins = DENSITY[density]
    width = round(PAGE_W - margins["left"] - margins["right"], 2)
    available = round(PAGE_H - margins["top"] - margins["bottom"], 2)
    warnings, _ = _collect_warnings(ir)

    chosen: tuple[float, float] | None = None
    used = 0.0
    for body_pt, ratio in LADDER:
        story = _build_story(ir, body_pt, ratio, width, lang=lang)
        used = _measure(story, width, available)
        if used <= available:
            chosen = (body_pt, ratio)
            break
    overflow = 0.0
    if chosen is None:
        chosen = LADDER[-1]
        story = _build_story(ir, chosen[0], chosen[1], width, lang=lang)
        used = _measure(story, width, available)
        overflow = round(max(0.0, used - available), 2)
        warnings.append(
            {
                "code": "PAGE_OVERFLOW_TWO_PAGES",
                "severity": "warn",
                "message": f"内容超出单页 {overflow}pt，已排成两页（可用高度 {available}pt）",
                "details": {
                    "pages": 2,
                    "overflow_pt": overflow,
                    "available_height_pt": available,
                    "body_pt": chosen[0],
                    "suggestion": "删掉部分要点，或把「包含照片/课程」等可选内容关掉",
                },
            }
        )
    elif chosen != LADDER[0]:
        warnings.append(
            {
                "code": "PAGE_FIT_DOWNGRADED",
                "severity": "warn",
                "message": f"单页装不下原文（{LADDER[0][0]}pt），已降到 {chosen[0]}pt 保证一页",
                "details": {
                    "from_pt": LADDER[0][0],
                    "to_pt": chosen[0],
                    "used_height_pt": used,
                    "available_height_pt": available,
                    "reason": "single_page_fit",
                },
            }
        )

    # 纵向铺满，但要「自然」：先抬行距（视觉上更透气，符合原件的 1.1–1.2 倍习惯），
    # 剩余零头再分给章节/条目间距，且间距最多 12pt——再大就像在凑字数。
    # 每一步都用**真实分页**复核：_measure 求和只是估计，frame 边界会多吃几 pt，
    # 实测过「量着装得下、实际掉第二页」和「退回一半后底部又空 143pt」两个坑。
    base_story = _build_story(ir, chosen[0], chosen[1], width, lang=lang)
    base_used = _measure(base_story, width, available)
    slack = available - base_used
    ratio = chosen[1]
    if slack > 0:
        for candidate in (1.25, 1.22, 1.18):
            if base_used * candidate / chosen[1] <= available - 6:
                ratio = candidate
                break
    body_pt = chosen[0]
    leading_ratio = ratio

    def gaps(max_gap: float) -> list[float]:
        return [round(i * 2.0, 2) for i in range(0, int(max_gap / 2) + 1)]

    story = _build_story(ir, body_pt, leading_ratio, width, lang=lang)
    filled_gap = 0.0
    best = None
    for gap in gaps(16.0):
        candidate = _build_story(ir, body_pt, leading_ratio, width, lang=lang, gap=gap)
        if _measure(candidate, width, available) <= available:
            best = (candidate, gap)
        else:
            break
    if best:
        story, filled_gap = best
    used = _measure(story, width, available)
    overflow = round(max(0.0, used - available), 2)

    buf = io.BytesIO()
    # 照片：边长 == 标题区真实高度；上沿与姓名上沿齐平，右沿与正文右缘齐平。
    photo_size = round(
        _measure(_header_story(ir, chosen[0], chosen[1], lang=lang), width, available), 2
    )
    photo_top = float(margins["top"])
    photo_right = float(margins["right"])
    photo_path = (ir.get("header") or {}).get("photo_path")

    def draw_photo(canv, doc):  # noqa: ANN001 - reportlab 回调签名
        if not photo_path or photo_bytes is None:
            return
        x = PAGE_W - photo_right - photo_size
        y = PAGE_H - photo_top - photo_size
        canv.drawImage(
            ImageReader(io.BytesIO(photo_bytes)),
            x,
            y,
            width=photo_size,
            height=photo_size,
            preserveAspectRatio=True,
            anchor="c",
            mask="auto",
        )

    def build_with(gap_value: float) -> tuple[bytes, int]:
        """按给定章节间距渲染一次，返回 (pdf bytes, 页数)。

        ``_measure`` 求和高度只是估计——reportlab 真正分页时 frame 边界会多吃几 pt；
        所以「间距铺满」必须用**真实分页结果**复核，装出两页就退回半档、再退回 0。
        这就是中文版曾因铺满而掉到第 2 页的那个坑。
        """
        flowed = (
            _build_story(ir, body_pt, leading_ratio, width, lang=lang, gap=gap_value)
            if gap_value
            else _build_story(ir, body_pt, leading_ratio, width, lang=lang)
        )
        buffer = io.BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=(PAGE_W, PAGE_H),
            leftMargin=margins["left"],
            rightMargin=margins["right"],
            topMargin=margins["top"],
            bottomMargin=margins["bottom"],
            title=str((ir.get("header") or {}).get("name") or "简历"),
            author="Resume Warehouse",
            creator="Resume Warehouse (local)",
        )
        document.build(flowed, onFirstPage=draw_photo, onLaterPages=draw_photo)
        blob = buffer.getvalue()
        pages = blob.count(b"/Type /Page") - blob.count(b"/Type /Pages")
        return blob, max(1, pages)

    # 从「量出来的最大可行间距」往下按 2pt 退，直到真实分页 = 1 页。
    # 只退一半不够：实测 en 34pt 会掉页、退到 17pt 后底部又空出 143pt；
    # 逐步退到第一个真正装得下的值，才能又满又不掉页。
    attempts = [round(g, 2) for g in (filled_gap - i * 2 for i in range(0, 8)) if g >= 0]
    data, page_count = build_with(attempts[0])
    filled_gap = attempts[0]
    for candidate_gap in attempts[1:]:
        if page_count <= 1:
            break
        data, page_count = build_with(candidate_gap)
        filled_gap = candidate_gap
    if page_count > 1:
        # 行距抬过头了：退回原行距、间距归零，宁可有留白也不许掉页
        leading_ratio = chosen[1]
        filled_gap = 0.0
        data, page_count = build_with(0.0)
    return RenderResult(
        data=data,
        page_count=max(1, page_count),
        body_pt=body_pt,
        leading=round(body_pt * leading_ratio, 2),
        used_height_pt=used,
        available_height_pt=available,
        warnings=warnings,
        meta={
            "density": density,
            "layout": {
                "available_height_pt": available,
                "text_width_pt": width,
                "body_pt": body_pt,
                "leading": round(body_pt * leading_ratio, 2),
                "leading_ratio": leading_ratio,
                "margins": dict(margins),
                "photo": (
                    {"size": photo_size, "top": photo_top, "right": photo_right}
                    if photo_path
                    else None
                ),
                "section_gap_pt": filled_gap,
            },
        },
    )


def extract_pdf_text(data: bytes) -> str:
    """抽取 PDF 文本层（供 ``verify_text`` 逐字比对）。"""
    try:
        from pypdf import PdfReader
    except Exception:  # pragma: no cover - pypdf 必装
        raise errors.internal_error("pypdf 不可用，无法校验文本层")
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def compare_text(expected: Sequence[str], actual: str) -> dict[str, Any]:
    """逐条比对期望字符串是否出现在 PDF 文本层（忽略空白差异）。"""
    normalized = re.sub(r"\s+", "", actual or "")
    missing = [item for item in expected if re.sub(r"\s+", "", item) not in normalized]
    return {
        "ok": not missing,
        "expected_count": len(expected),
        "missing": missing[:20],
        "missing_count": len(missing),
    }
