"""简历文件 → 带版式信息的文本行（t5 导入引擎的抽取层）。

设计要点（实测自用户真实简历，见 docs/ARCHITECTURE §7.5 与 t5 记录）：

1. **逐字保真**：抽取阶段不润色、不归一、不改写。全角冒号、`PM₁`、`PM₂.₅`、
   `（R）`、`（Python）`、`AI&金融` 等必须原样保留（t5 硬指标 3/4）。
2. **版式信息保留**：每行带 ``x0``（左边界）、``size``（字号）、``bold``、``italic``、
   ``bullet``。解析层靠"字号/加粗/缩进/日期"判断 section 与 entry，而不是靠猜。
3. **`(cid:127)` 清洗**：英文样张里项目符号字形缺失，文本层是字面量 ``(cid:127)``。
   行首的它识别为 bullet 标记并剥离；行中出现的其它 ``(cid:N)`` 一并剥离并计数，
   输出不得残留 ``(cid:``（t5 硬指标 5）。
4. **双页不串栏**：按页序、页内自上而下产出；续行只能向上归属同一页的同一 entry。
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

#: 行首项目符号字形缺失（英文样张 16 处）
CID_RE = re.compile(r"\(cid:(\d+)\)")
#: 日期区间（中文/英文/斜杠/横线/至今）
#: 注意：裸四位数字**不算**日期。否则「示例数据科技7193a0 - 数据实习生 2026.07 - 2026.10」
#: 会被 DATE_SPAN_RE 先匹配到 `7193`，条目标题判定随之中止，整行被当成正文吞进 bullets。
#: 真的只有年份时写法是「2026 年」或「2026届」，带单位才认。
#: 分隔符后**必须**有月份数字：`4678 - ` 这种「四位数字 + 横线」不是日期。
#: （原写法 `\d{0,2}` 允许零位，导致「示例数据科技ac934678 - 数据实习生 2026.07 - 2026.10」
#: 先匹配到 `4678 -`，条目标题判定中止，整行被吞进 bullets——marker 决定解析结果。）
_DATE = (
    r"(?:\d{4}\s*[./\-]\s*\d{1,2}|\d{4}\s*年\s*\d{0,2}\s*月?|\d{1,2}/\d{4}|\d{4}\s*[年届])"
)
_PRESENT = r"(?:至今|现在|Present|Now)"
DATE_SPAN_RE = re.compile(rf"(?:{_DATE}\s*(?:[–—\-~至到]+\s*(?:{_DATE}|{_PRESENT}))?|{_DATE}|{_PRESENT})")
#: 列分隔（PDF 文本层里的对齐空格或制表符）
COLUMN_GAP_RE = re.compile(r"\s{2,}|\t")
#: 句末标点（用于把折行正文还原成句子）
SENTENCE_RE = re.compile(r"[^。！？!?]*[。！？!?]|[^。！？!?]+$")

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def is_cjk(char: str) -> bool:
    return bool(char) and bool(CJK_RE.match(char))


def join_fragments(left: str, right: str) -> str:
    """把 PDF 的折行接回去：中文直接拼，英文/数字之间补一个空格。"""
    if not left:
        return right
    if not right:
        return left
    tail, head = left[-1], right[0]
    if tail.isspace() or head.isspace():
        return left + right
    if is_cjk(tail) or is_cjk(head):
        return left + right
    if head in "，。、；：！？）」』】%,.;:!?)]}":
        return left + right
    if tail in "（「『【([{":
        return left + right
    return left + " " + right


@dataclass
class DocLine:
    """一个视觉行（PDF）或一个逻辑段落（DOCX/MD/TXT）。"""

    text: str
    page: int = 0
    top: float = 0.0
    x0: float = 0.0
    size: float = 0.0
    bold: bool = False
    italic: bool = False
    bullet: bool = False
    level: int = 0          # DOCX/MD 标题级别（1..6），0 表示非标题
    style: str = ""

    @property
    def stripped(self) -> str:
        return self.text.strip()

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "page": self.page,
            "x0": round(self.x0, 2),
            "size": round(self.size, 2),
            "bold": self.bold,
            "italic": self.italic,
            "bullet": self.bullet,
            "level": self.level,
        }


@dataclass
class ExtractedImage:
    page: int
    x0: float
    top: float
    width: float
    height: float
    src_width: int
    src_height: int
    data: bytes
    ext: str = "png"
    #: 该页 MediaBox 的底边偏移（多数 PDF 是 0，但扫描件/导出器常带 7.83 这类偏移）。
    #: pdfplumber 的 ``im["top"]`` 相对 MediaBox 顶，换算成「距物理页顶」必须加回这个偏移。
    mediabox_bottom: float = 0.0
    #: 该页 MediaBox 宽度（pt），用于算「距页右」这类边距，避免把绝对 x 当边距混用。
    page_width: float = 0.0
    #: 每通道位数与色彩空间（pdfplumber 的 ``bits`` / ``colorspace``）。
    #: Word/WPS 导出的 PDF 常把内嵌 PNG 写成 ``/FlateDecode`` 的**裸像素**，
    #: 没有 PNG 容器头，PIL 打不开；这时需要靠这两个值重建位图（见 services/photo.py）。
    bits: int = 8
    colorspace: str = ""

    @property
    def top_from_page(self) -> float:
        """距**物理页顶**的距离（pt）。恒 ≥ 0，可直接与设计稿的 3.8pt 比对。"""
        return self.top + self.mediabox_bottom

    def as_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "x0": round(self.x0, 2),
            "top": round(self.top, 2),
            "top_from_page": round(self.top_from_page, 2),
            "mediabox_bottom": round(self.mediabox_bottom, 2),
            "page_width": round(self.page_width, 2),
            "width": round(self.width, 2),
            "height": round(self.height, 2),
            "src_width": self.src_width,
            "src_height": self.src_height,
            "bits": self.bits,
            "colorspace": self.colorspace,
            "src_width": self.src_width,
            "src_height": self.src_height,
            "bytes": len(self.data),
            "ext": self.ext,
        }


@dataclass
class ExtractedDoc:
    parser: str
    pages: int
    lines: list[DocLine]
    images: list[ExtractedImage] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    cid_count: int = 0
    raw_text: str = ""
    lang: str = "zh"

    @property
    def text_chars(self) -> int:
        return sum(len(line.stripped) for line in self.lines)

    @property
    def words(self) -> int:
        return sum(len(line.stripped.split()) for line in self.lines)

    @property
    def nonempty_lines(self) -> int:
        return sum(1 for line in self.lines if line.stripped)

    def stats(self) -> dict[str, Any]:
        return {
            "pages": self.pages,
            "chars": self.text_chars,
            "words": self.words,
            "lines": self.nonempty_lines,
            "images": len(self.images),
            "cid_missing": self.cid_count,
        }


# --------------------------------------------------------------------------------------
# 文本清洗
# --------------------------------------------------------------------------------------

def clean_cid(lines: Iterable[DocLine]) -> tuple[list[DocLine], int]:
    """剥离 ``(cid:N)``：行首的算 bullet 标记，其余直接去掉；返回 (lines, 计数)。"""
    cleaned: list[DocLine] = []
    count = 0
    for line in lines:
        text = line.text
        matches = CID_RE.findall(text)
        if matches:
            count += len(matches)
            leading = True
            for match in CID_RE.finditer(text):
                prefix = text[: match.start()]
                if prefix.strip():
                    leading = False
                break
            # 行首的 (cid:127) 视为项目符号：删掉标记，标记 bullet
            text = CID_RE.sub(" ", text) if not leading else CID_RE.sub("", text, count=1)
            if leading:
                line.bullet = True
            text = text.replace("  ", " ")
        line.text = text
        cleaned.append(line)
    return cleaned, count


def detect_lang(lines: Sequence[DocLine]) -> str:
    cjk = latin = 0
    for line in lines:
        for char in line.stripped:
            if CJK_RE.match(char):
                cjk += 1
            elif char.isascii() and char.isalpha():
                latin += 1
    return "zh" if cjk >= max(1, latin // 2) else "en"


# --------------------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------------------

def _cluster_rows(chars: list[dict[str, Any]], tolerance: float = 2.0) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    for char in sorted(chars, key=lambda c: (round(c["top"], 1), c["x0"])):
        if rows and abs(char["top"] - rows[-1][0]["top"]) <= tolerance:
            rows[-1].append(char)
        else:
            rows.append([char])
    for row in rows:
        row.sort(key=lambda c: c["x0"])
    return rows


def _row_to_line(row: Sequence[dict[str, Any]], page_no: int) -> DocLine:
    size = sorted(char["size"] for char in row)[len(row) // 2]
    size = size or 10.0
    fonts = [char.get("fontname", "") for char in row]
    bold = sum(1 for font in fonts if "Bold" in font or font.endswith("-Bd")) > len(fonts) * 0.55
    italic = sum(1 for font in fonts if "Italic" in font or "Oblique" in font) > len(fonts) * 0.55
    parts: list[str] = []
    prev: dict[str, Any] | None = None
    for char in row:
        if prev is not None:
            gap = char["x0"] - prev["x1"]
            if gap > 2.5 * size:
                parts.append("\t")
            elif gap > 0.18 * size and not (parts and parts[-1].endswith(" ")):
                parts.append(" ")
        parts.append(char["text"])
        prev = char
    return DocLine(
        text="".join(parts).rstrip(),
        page=page_no,
        top=row[0]["top"],
        x0=row[0]["x0"],
        size=round(size, 2),
        bold=bold,
        italic=italic,
    )


def _read_pdf_pages(
    data: bytes,
    lines: list[DocLine],
    images: list[ExtractedImage],
    warnings: list[dict[str, Any]],
) -> int:
    """把 PDF 的文本行与内嵌图读进给定容器，返回页数。异常由调用方兜底。"""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = len(pdf.pages)
        for page_no, page in enumerate(pdf.pages):
            for row in _cluster_rows(page.chars):
                line = _row_to_line(row, page_no)
                if line.stripped:
                    lines.append(line)
            for image in page.images or []:
                stream = image.get("stream")
                if stream is None:
                    continue
                try:
                    blob = stream.get_data()
                except Exception:  # pragma: no cover - 极少见的编码异常
                    warnings.append(
                        {
                            "code": "IMAGE_DECODE_FAILED",
                            "count": 1,
                            "message": "内嵌图无法解码，已跳过（不影响文本导入）",
                            "severity": "info",
                        }
                    )
                    continue
                src_w, src_h = image.get("srcsize") or (0, 0)
                # pdfplumber 会把 MediaBox 归一化：原始 [0, b, w, h] 变成 (0, -b, w, h-2b)，
                # 因此「底边偏移」= -mediabox[1]（b=0 的常规 PDF 得到 0）。
                # im["top"] 是相对归一化后的页顶，加上这个偏移才是距物理页顶的真实距离。
                try:
                    mediabox_bottom = max(0.0, -float(page.mediabox[1]))
                    page_width = float(page.mediabox[2])
                except Exception:  # pragma: no cover - 没有 mediabox 的畸形 PDF
                    mediabox_bottom = 0.0
                    page_width = 0.0
                images.append(
                    ExtractedImage(
                        page=page_no + 1,
                        x0=float(image.get("x0") or 0.0),
                        top=float(image.get("top") or 0.0),
                        width=float(image.get("width") or 0.0),
                        height=float(image.get("height") or 0.0),
                        src_width=int(src_w or 0),
                        src_height=int(src_h or 0),
                        data=blob,
                        ext=_guess_ext(blob),
                        mediabox_bottom=mediabox_bottom,
                        page_width=page_width,
                        bits=int(image.get("bits") or 8),
                        colorspace=_colorspace_name(image.get("colorspace")),
                    )
                )
    return pages


def extract_pdf(data: bytes) -> ExtractedDoc:
    lines: list[DocLine] = []
    images: list[ExtractedImage] = []
    warnings: list[dict[str, Any]] = []
    pages = 0
    try:
        pages = _read_pdf_pages(data, lines, images, warnings)
    except Exception as exc:  # noqa: BLE001 - 损坏/加密 PDF 不能抛 500
        warnings.append(
            {
                "code": "PDF_UNREADABLE",
                "count": 1,
                "message": f"PDF 无法解析（{type(exc).__name__}），已按无文本层处理，可改用粘贴文本导入",
                "severity": "error",
            }
        )
        return ExtractedDoc(
            parser="pdf",
            pages=0,
            lines=[],
            images=[],
            warnings=warnings,
            cid_count=0,
            raw_text="",
        )

    lines, cid_count = clean_cid(lines)
    if cid_count:
        warnings.append(
            {
                "code": "CID_GLYPH_MISSING",
                "count": cid_count,
                "message": (
                    f"文本层有 {cid_count} 处内嵌字形缺失的项目符号（PDF cid 编码 U+007F），"
                    "已识别为 bullet 标记并从正文剥离，未当成缺字处理"
                ),
                "severity": "warn",
            }
        )
    doc = ExtractedDoc(
        parser="pdf",
        pages=pages,
        lines=lines,
        images=images,
        warnings=warnings,
        cid_count=cid_count,
        raw_text="\n".join(line.text for line in lines),
    )
    doc.lang = detect_lang(lines)
    return doc


def _colorspace_name(colorspace: Any) -> str:
    """pdfplumber 的 colorspace 是 ``[/'DeviceRGB]`` 这类混合列表，取可读名字。"""
    if not colorspace:
        return ""
    parts: list[str] = []
    values = colorspace if isinstance(colorspace, (list, tuple)) else [colorspace]
    for value in values:
        name = getattr(value, "name", None) or str(value)
        parts.append(str(name))
    return " ".join(part for part in parts if part)


def _guess_ext(blob: bytes) -> str:
    if blob.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "webp"
    return "bin"


# --------------------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------------------

_HEADING_STYLE_RE = re.compile(r"(?:heading|标题)\s*(\d+)", re.IGNORECASE)


def extract_docx(data: bytes) -> ExtractedDoc:
    import docx

    document = docx.Document(io.BytesIO(data))
    lines: list[DocLine] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.rstrip()
        if not text.strip():
            continue
        style = (paragraph.style.name if paragraph.style is not None else "") or ""
        level_match = _HEADING_STYLE_RE.search(style)
        level = int(level_match.group(1)) if level_match else ("Title" in style and 1 or 0)
        bullet = "List" in style or text.lstrip().startswith(("•", "·", "-", "▪"))
        runs = [run for run in paragraph.runs if run.text.strip()]
        bold = bool(runs) and all(run.bold for run in runs)
        italic = bool(runs) and all(run.italic for run in runs)
        cleaned = text.lstrip("•·▪- ").strip() if bullet else text.strip()
        lines.append(DocLine(text=cleaned, bold=bold, italic=italic, bullet=bullet, level=level, style=style))
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                lines.append(DocLine(text=" | ".join(cells), style="table"))

    warnings: list[dict[str, Any]] = []
    doc = ExtractedDoc(
        parser="docx",
        pages=1,
        lines=lines,
        warnings=warnings,
        raw_text="\n".join(line.text for line in lines),
    )
    doc.lang = detect_lang(lines)
    return doc


# --------------------------------------------------------------------------------------
# Markdown / TXT / HTML / 直接粘贴
# --------------------------------------------------------------------------------------

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_MD_LIST_RE = re.compile(r"^\s*(?:[-*+•·]|\d+[.)])\s+(.*)$")


def extract_markdown(data: bytes) -> ExtractedDoc:
    text = data.decode("utf-8", "replace")
    lines: list[DocLine] = []
    in_code = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line.strip():
            continue
        heading = _MD_HEADING_RE.match(line)
        if heading:
            lines.append(DocLine(text=heading.group(2).strip(), level=len(heading.group(1)), bold=True, style="heading"))
            continue
        item = _MD_LIST_RE.match(line)
        if item:
            lines.append(DocLine(text=item.group(1).strip(), bullet=True, style="list"))
            continue
        stripped = re.sub(r"\*\*(.+?)\*\*", r"\1", line.strip())
        stripped = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", stripped)
        stripped = re.sub(r"`([^`]+)`", r"\1", stripped)
        lines.append(DocLine(text=stripped, style="body"))
    doc = ExtractedDoc(
        parser="md",
        pages=1,
        lines=lines,
        raw_text="\n".join(line.text for line in lines),
    )
    doc.lang = detect_lang(lines)
    return doc


def extract_plaintext(data: bytes, parser: str = "txt") -> ExtractedDoc:
    text = data.decode("utf-8", "replace")
    lines: list[DocLine] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        bullet = line.lstrip().startswith(("•", "·", "-", "*", "▪", "◦"))
        cleaned = line.lstrip("•·-*▪◦ ").strip() if bullet else line.strip()
        lines.append(DocLine(text=cleaned, bullet=bullet, style="bullet" if bullet else "body"))
    doc = ExtractedDoc(
        parser=parser,
        pages=1,
        lines=lines,
        raw_text="\n".join(line.text for line in lines),
    )
    doc.lang = detect_lang(lines)
    return doc


def extract_html(data: bytes) -> ExtractedDoc:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data.decode("utf-8", "replace"), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    lines: list[DocLine] = []
    for element in soup.find_all(["h1", "h2", "h3", "h4", "li", "p", "td"]):
        text = element.get_text(" ", strip=True)
        if not text:
            continue
        name = element.name
        if name.startswith("h"):
            lines.append(DocLine(text=text, level=int(name[1]), bold=True, style="heading"))
        elif name == "li":
            lines.append(DocLine(text=text, bullet=True, style="list"))
        else:
            lines.append(DocLine(text=text, style=name))
    doc = ExtractedDoc(
        parser="html",
        pages=1,
        lines=lines,
        raw_text="\n".join(line.text for line in lines),
    )
    doc.lang = detect_lang(lines)
    return doc


# --------------------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------------------

PARSERS = {
    "pdf": extract_pdf,
    "docx": extract_docx,
    "md": extract_markdown,
    "txt": extract_plaintext,
    "html": extract_html,
}


def parser_for_name(filename: str) -> str:
    name = (filename or "").lower()
    for ext, parser in ((".pdf", "pdf"), (".docx", "docx"), (".md", "md"), (".markdown", "md"), (".txt", "txt"), (".html", "html"), (".htm", "html")):
        if name.endswith(ext):
            return parser
    return "txt"


def extract(data: bytes, parser: str) -> ExtractedDoc:
    if parser not in PARSERS:
        raise ValueError(f"不支持的解析器：{parser}")
    doc = PARSERS[parser](data)
    if not doc.lang:
        doc.lang = "zh"
    # 保真检查：出现替换字符属于硬失败信号（t5 硬指标 5）
    replacement = doc.raw_text.count("\ufffd")
    if replacement:
        doc.warnings.append(
            {
                "code": "TEXT_ENCODING_REPLACED",
                "count": replacement,
                "message": f"文本解码出现 {replacement} 个替换字符（U+FFFD），请检查源文件编码",
                "severity": "error",
            }
        )
    residual = doc.raw_text.count("(cid:")
    if residual:
        doc.warnings.append(
            {
                "code": "CID_GLYPH_RESIDUAL",
                "count": residual,
                "message": "仍有内嵌字形缺失标记残留，需人工确认（不要直接提交模板）",
                "severity": "error",
            }
        )
    return doc


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", text or "").strip()
