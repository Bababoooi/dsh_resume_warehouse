"""出站身份断言：姓名 / 电话 / 邮箱 / 照片 绝不允许出现在上行 payload 里。

用户 m00265 定稿的边界：
* ❌ 永不上云：姓名、电话、邮箱、照片
* ✅ 上云：学校名、学历、专业、届别、城市、到岗时间、经历与项目文本、JD、公司名、岗位名、备注

脱敏（``services/consent.py``）是主要手段；本模块是**兜底断言**——即使某天
脱敏开关被误关、动态正则没命中（例如姓名为单字被跳过构造），也会在真正
发起 HTTP 之前失败，绝不把身份信息发出去。宁可 500，也不外发。
注意：**不拦学校名**，否则会把合法输入判成违规。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from ..errors import ApiError

#: 姓名类字段（值必须从 payload 里消失）
_NAME_FIELDS: tuple[str, ...] = ("name_zh", "name_en")
#: 联系方式类字段（值必须从 payload 里消失）
_CONTACT_FIELDS: tuple[str, ...] = ("phone", "email")


def identity_terms(
    profile: Mapping[str, Any],
    photo_hashes: Iterable[str] = (),
) -> list[tuple[str, str]]:
    """返回 [(字段名, 真值)]；姓名/联系方式长度 <2 的忽略（单字匹配会误伤正文）。"""

    terms: list[tuple[str, str]] = []
    for field in _NAME_FIELDS + _CONTACT_FIELDS:
        value = profile.get(field)
        if isinstance(value, str) and len(value.strip()) >= 2:
            terms.append((field, value.strip()))
    for digest in photo_hashes:
        if isinstance(digest, str) and len(digest.strip()) >= 16:
            terms.append(("photo.sha256", digest.strip()))
    return terms


def assert_no_identity(
    text: str,
    profile: Mapping[str, Any],
    photo_hashes: Iterable[str] = (),
) -> None:
    """payload 文本里出现姓名/电话/邮箱/照片哈希即 500（fail-closed），不回显命中值。"""

    if not text:
        return
    hits: list[dict[str, str]] = []
    for field, value in identity_terms(profile, photo_hashes):
        if value and value in text:
            hits.append({"field": field, "action": "blocked"})
    if hits:
        raise ApiError(
            "INTERNAL",
            "已阻止发送：payload 中仍包含姓名、联系方式或照片指纹（脱敏链路缺陷）",
            details={"reason": "IDENTITY_PRESENT_IN_PAYLOAD", "hits": hits},
            hint="请反馈该问题；本次请求未发出，任何数据都没有离开本机",
        )


def redact_identity(text: str, profile: Mapping[str, Any]) -> tuple[str, int]:
    """把姓名替换为 ``[NAME]``，返回 (新文本, 替换次数)。用于非 payload 的出站文本。"""

    count = 0
    for field in _NAME_FIELDS:
        value = profile.get(field)
        if not isinstance(value, str) or len(value.strip()) < 2:
            continue
        pattern = re.compile(re.escape(value.strip()))
        text, hits = pattern.subn("[NAME]", text)
        count += hits
    return text, count
