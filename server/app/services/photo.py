"""内嵌照片抽取（用户要求：中英两版简历都保留照片）。

判定口径（captain m00133）：单张、近方形、原图短边 ≥200px 视为证件照。
落盘口径：``data/profile/photo_<hash>.png``，走内容寻址去重；照片字节**永不进 LLM payload**，
只在本机渲染阶段读取。
"""

from __future__ import annotations

import io
from typing import Any, Iterable, Mapping

from .extract import ExtractedDoc, ExtractedImage

#: 证件照最小短边（像素）
MIN_SIDE = 200
#: 近方形判定：宽高比落在 [1/1.45, 1.45]
ASPECT_RANGE = (1 / 1.45, 1.45)


def _as_photo(img: ExtractedImage) -> bool:
    width, height = img.src_width or 0, img.src_height or 0
    if min(width, height) < MIN_SIDE:
        return False
    ratio = width / height if height else 0
    return ASPECT_RANGE[0] <= ratio <= ASPECT_RANGE[1]


def pick_photo(doc: ExtractedDoc) -> ExtractedImage | None:
    candidates: Iterable[ExtractedImage] = [img for img in doc.images if _as_photo(img)]
    ordered = sorted(candidates, key=lambda img: (img.src_width * img.src_height, -img.page), reverse=True)
    return ordered[0] if ordered else None


def _raw_mode(data: bytes, width: int, height: int, colorspace: str, bits: int) -> str | None:
    """裸像素流（``/FlateDecode``）按长度 + 色彩空间推断 PIL mode；推不出就放弃。"""
    if bits != 8 or width <= 0 or height <= 0:
        return None
    pixels = width * height
    space = (colorspace or "").upper()
    if "CMYK" in space and len(data) >= pixels * 4:
        return "CMYK"
    if "GRAY" in space and len(data) >= pixels:
        return "L"
    if len(data) == pixels * 3:
        return "RGB"
    if len(data) == pixels:
        return "L"
    if len(data) == pixels * 4:
        # 没有色彩空间声明的 4 通道图，通常是 RGBA（预乘 alpha 与 CMYK 都无法可靠区分）
        return "RGBA"
    return None


def to_png(
    data: bytes,
    *,
    width: int = 0,
    height: int = 0,
    colorspace: str = "",
    bits: int = 8,
) -> tuple[bytes, int, int] | None:
    """转 PNG（保证导出端只处理一种格式）。

    两条解码路径（实证：Word/WPS 导出的 PDF 会把内嵌 PNG 展成 ``/FlateDecode`` 裸像素，
    流里没有 PNG 容器头，直接喂 PIL 只会得到 UnidentifiedImageError）：

    1. 有容器头（JPEG / PNG / JPX）→ 交给 Pillow；
    2. 裸像素 → 用 ``srcsize`` + ``bits`` + ``colorspace`` 重建位图。

    两条都失败才返回 None，由调用方降级为「无法解码」的显式提示。
    """
    try:
        from PIL import Image  # type: ignore
    except Exception:  # noqa: BLE001 - Pillow 缺失
        return None

    try:
        with Image.open(io.BytesIO(data)) as handle:
            frame = handle.convert("RGB")
            buffer = io.BytesIO()
            frame.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue(), frame.width, frame.height
    except Exception:  # noqa: BLE001 - 继续尝试裸像素路径
        pass

    mode = _raw_mode(data, width, height, colorspace, bits)
    if mode is None:
        return None
    try:
        frame = Image.frombytes(mode, (width, height), data[: len(data)])
        if frame.mode not in ("RGB", "L"):
            frame = frame.convert("RGB")
        buffer = io.BytesIO()
        frame.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue(), frame.width, frame.height
    except Exception:  # noqa: BLE001 - 裸像素重建也失败
        return None


def payload(
    doc: ExtractedDoc,
    *,
    file_rel: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    """``ImportJob.extracted_photo_json``：没有照片时也返回结构（available=false）。"""
    photo = pick_photo(doc)
    if photo is None:
        return {
            "available": False,
            "detected": False,
            "unreadable": False,
            "source": "none",
            "file": None,
            "width": None,
            "height": None,
            "rendered": None,
            "probable_kind": None,
            "applied": False,
            "note": "未检测到符合证件照判据（近方形、短边≥200px）的内嵌图片",
        }
    rendered = {
        "page": photo.page,
        "w_pt": round(photo.width, 2),
        "h_pt": round(photo.height, 2),
        "x0_pt": round(photo.x0, 2),
        # 距物理页顶：pdfplumber 的 top 相对 MediaBox 顶，必须加回 mediabox 底边偏移，
        # 否则下边不为 0 的 PDF（本项目的真实样张就是 [0, 7.83, 595.5, 850.08]）会整体偏 7.83pt。
        "top_offset_pt": round(photo.top_from_page, 2),
        "mediabox_bottom_pt": round(photo.mediabox_bottom, 2),
        # 距页右的**边距**（不是 x0；x0 是照片左边绝对坐标，两者曾被混用过）
        "right_gap_pt": round(max(0.0, photo.page_width - (photo.x0 + photo.width)), 2) if photo.page_width else None,
    }
    return {
        # 判据：available=true 必须意味着「用户能点开这个附件」；只检测到但没落盘时 available=false
        "available": bool(file_rel),
        "detected": True,
        "unreadable": False,
        "source": "embedded",
        "file": file_rel,
        "width": width or photo.src_width,
        "height": height or photo.src_height,
        "rendered": rendered,
        "probable_kind": "id_photo",
        # D-23：导入只把照片作为**候选**返回，绝不自动写 user_profile.photo_path。
        # 用户显式确认（PUT /api/v1/profile/photo {attachment_id}）之后才 applied=True。
        "applied": False,
        "confirmed": False,
        "note": "检测到内嵌证件照，作为候选返回；确认后才会用于简历。照片永不发送给任何 LLM",
    }


def save(
    doc: ExtractedDoc, storage: Any, *, original_name: str = "resume-photo"
) -> tuple[dict[str, Any], Mapping[str, Any] | None, list[dict[str, Any]]]:
    """抽图 → PNG → 内容寻址落盘，返回 ``(extracted_photo, stored_record, warnings)``。

    解码失败时**必须**同时：``available=false`` + ``unreadable=true`` + ``PHOTO_DECODE_FAILED``
    warning。否则 UI 会拿到一个「说有照片、却点不开」的自相矛盾状态（captain m01420 缺陷 B）。
    """
    photo = pick_photo(doc)
    if photo is None:
        return payload(doc), None, []
    converted = to_png(
        photo.data,
        width=photo.src_width,
        height=photo.src_height,
        colorspace=photo.colorspace,
        bits=photo.bits,
    )
    if converted is None:
        unreadable = payload(doc)
        unreadable.update(
            {
                "available": False,
                "detected": True,
                "unreadable": True,
                "file": None,
                "applied": False,
                "confirmed": False,
                "note": "检测到证件照但无法解码，已跳过；可手动上传照片",
            }
        )
        warning = {
            "code": "PHOTO_DECODE_FAILED",
            "count": 1,
            "severity": "warn",
            "message": "检测到证件照但无法解码，已跳过，可手动上传照片",
            "details": {
                "src_width": photo.src_width,
                "src_height": photo.src_height,
                "bytes": len(photo.data or b""),
                "bits": photo.bits,
                "colorspace": photo.colorspace,
            },
        }
        return unreadable, None, [warning]
    png, width, height = converted
    stored = storage.save_attachment(png, original_name=f"{original_name}.png", kind="photo", privacy="private")
    rel_path = str(stored.path.relative_to(storage.paths.root)).replace("\\", "/")
    return payload(doc, file_rel=rel_path, width=width, height=height), stored, []
