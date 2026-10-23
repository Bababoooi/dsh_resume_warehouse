"""「将发送字段清单」与一次性授权（consent）——隐私红线的执行点。

流程（API-CONTRACT §10）：
1. ``POST /llm/preview``：按用户**显式选中的 ID** 取数据，脱敏，组装请求体，
   逐字段生成清单（字段名 + 字数 + 是否含 PII），落 ``llm_preview``，状态 ``pending``；
2. ``POST /llm/complete``：校验 payload sha256 与状态后**原子**消费（一次性），
   才真正发起网络请求；
3. ``POST /llm/previews/{id}/reject``：放弃发送。

硬红线：
* 只接受 ID，不接受正文；``data/imports/**`` 的文件内容永不进入 payload；
* 档案里的 ``phone`` / ``email`` / ``photo_path`` 结构上排除（不只是脱敏）；
* 审计表 ``llm_call_log`` 只记录字段名与大小，不记录任何正文。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

from .. import config as config_mod
from .. import db as db_mod
from ..adapters import llm_client, providers
from ..errors import ApiError
from ..repos import (
    AttachmentRepo,
    CompanyRepo,
    JdRepo,
    LlmLogRepo,
    PackageRepo,
    PreviewRepo,
    ProfileRepo,
    SettingsRepo,
)
from . import prompts
from .privacy import assert_no_identity

log = logging.getLogger("app.consent")

#: 预览有效期（契约：created + 600s）
PREVIEW_TTL_SECONDS = 600
#: 提示词接近上限的提醒阈值（字符）
PROMPT_NEAR_LIMIT_CHARS = 24000
#: JD 分析时自动带上的仓库经历条数上限（captain 2026-10-23：按与 JD 技能词的重合度取前 N）
WAREHOUSE_MAX_PACKAGES = 12
#: 仓库经历段落的总字符上限
WAREHOUSE_MAX_CHARS = 6000

REDACTION_PATTERNS: dict[str, tuple[re.Pattern[str], str]] = {
    "phone": (re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)"), "[PHONE]"),
    "email": (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "[EMAIL]"),
    "id": (re.compile(r"(?<![\dXx])(?:\d{17}[\dXx]|\d{15})(?![\dXx])"), "[ID]"),
}

#: 动态脱敏：用档案真值在运行时构造正则（纵深防御——即使经历文本里自己写了真名也拦下）
#: 学校名**不脱敏**（用户 m00265：校名有分析价值，按真实值上云）
REDACT_NAME = "[NAME]"

DEFAULT_REDACT_KINDS: tuple[str, ...] = ("phone", "email", "id", "name")

#: 强制脱敏类别：不可被用户开关关闭（姓名恒脱敏，用户明确「永不上云」）
FORCED_REDACT_KINDS: tuple[str, ...] = ("name",)


def build_dynamic_patterns(profile: Mapping[str, Any]) -> dict[str, tuple[re.Pattern[str], str]]:
    """按档案真值构造姓名正则（re.escape，避免把正则元字符当语法）。"""

    patterns: dict[str, tuple[re.Pattern[str], str]] = {}
    names = [profile.get("name_zh"), profile.get("name_en")]
    name_values = [value.strip() for value in names if isinstance(value, str) and len(value.strip()) >= 2]
    if name_values:
        alternation = "|".join(re.escape(value) for value in sorted(set(name_values), key=len, reverse=True))
        patterns["name"] = (re.compile(alternation), REDACT_NAME)
    return patterns


def _mask(value: str) -> str:
    """value_preview：中间打码（178****0929），永远不返回完整值。"""
    if len(value) <= 4:
        return "*" * len(value)
    if len(value) <= 8:
        return value[:1] + "*" * (len(value) - 2) + value[-1:]
    return value[:3] + "*" * (len(value) - 7) + value[-4:]


class Redactor:
    """按开关做正则替换，并记录 redactions（供 UI 展示并核对）。"""

    def __init__(
        self,
        kinds: list[str],
        patterns: Mapping[str, tuple[re.Pattern[str], str]] | None = None,
    ) -> None:
        self.patterns: dict[str, tuple[re.Pattern[str], str]] = dict(REDACTION_PATTERNS)
        self.patterns.update(patterns or {})
        self.kinds = [kind for kind in dict.fromkeys(kinds) if kind in self.patterns]
        self.records: list[dict[str, Any]] = []

    def apply(self, text: str, *, path: str) -> str:
        if not text or not self.kinds:
            return text
        result = text
        for kind in self.kinds:
            pattern, replacement = self.patterns[kind]
            matches = pattern.findall(result)
            if not matches:
                continue
            result = pattern.sub(replacement, result)
            unique = list(dict.fromkeys(matches))
            for match in unique:
                self.records.append(
                    {
                        "path": path,
                        "match": kind,
                        "value_preview": _mask(match),
                        "replacement": replacement,
                        "count": matches.count(match),
                    }
                )
        return result


def canonical_payload_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def payload_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()


def est_tokens(chars: int) -> int:
    """粗估：中文约 1 token/字，英文约 4 字符/token；取折中 1.6 字符/token。"""
    return max(1, int(chars / 1.6)) if chars else 0


def _norm(text: object) -> str:
    """匹配用归一化（全角转半角、小写、只留字母数字与汉字）。"""
    raw = unicodedata.normalize("NFKC", str(text or ""))
    return "".join(ch for ch in raw.lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def _jd_tokens(text: str, *, limit: int = 160) -> list[str]:
    """JD 里的技能/业务词（用于给仓库经历排序，本地确定性、不发网络）。"""
    words = re.findall(r"[A-Za-z]{2,}|[\u4e00-\u9fff]{2,4}", str(text or ""))
    out: list[str] = []
    for word in words:
        needle = _norm(word)
        if len(needle) >= 2 and needle not in out:
            out.append(needle)
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------------------
# schema 校验（降级链的最后一环）
# --------------------------------------------------------------------------------------


def _validator_for(purpose: str) -> Callable[[Any], Any]:
    def validate(obj: Any) -> Any:
        if not isinstance(obj, Mapping):
            raise ValueError("顶层必须是 JSON 对象")
        if purpose == "jd_analyze":
            requirements = obj.get("requirements")
            if not isinstance(requirements, list) or not requirements:
                raise ValueError("缺少非空的 requirements 数组")
            for req in requirements:
                if not isinstance(req, Mapping) or not req.get("skill"):
                    raise ValueError("requirements[].skill 缺失")
        elif purpose == "company_profile":
            if "company_name" not in obj:
                raise ValueError("缺少 company_name")
        elif purpose == "build_suggest":
            if not isinstance(obj.get("selected"), list):
                raise ValueError("缺少 selected 数组")
        elif purpose == "bullets_generate":
            if not isinstance(obj.get("variants"), list):
                raise ValueError("缺少 variants 数组")
        return obj

    return validate


# --------------------------------------------------------------------------------------
# 服务
# --------------------------------------------------------------------------------------


class ConsentService:
    def __init__(
        self,
        *,
        conn=None,
        cfg: config_mod.Config | None = None,
        client: llm_client.LlmClient | None = None,
    ) -> None:
        self.cfg = cfg or config_mod.get_config()
        self.conn = conn or db_mod.get_conn()
        self.client = client or llm_client.LlmClient(self.cfg)
        self.packages = PackageRepo(self.conn)
        self.profile = ProfileRepo(self.conn)
        self.jds = JdRepo(self.conn)
        self.companies = CompanyRepo(self.conn)
        self.previews = PreviewRepo(self.conn)
        self.logs = LlmLogRepo(self.conn)
        self.settings = SettingsRepo(self.conn)
        self.attachments = AttachmentRepo(self.conn)
        #: 本次预览带上来的仓库经历统计（JD 分析用），由 ``_collect`` 写入
        self.warehouse_stats: dict[str, Any] = {}

    # -- 预览 ------------------------------------------------------------------
    def build_preview(self, request: Mapping[str, Any]) -> dict[str, Any]:
        purpose = request["purpose"]
        spec = providers.spec_for(purpose)
        route = providers.resolve_route(
            purpose,
            self.cfg,
            provider_override=request.get("provider_override"),
            temperature=(request.get("options") or {}).get("temperature"),
            max_tokens=(request.get("options") or {}).get("max_tokens"),
        )
        self.client.ensure_ready(route.provider)

        selections = request.get("selections") or {}
        options = request.get("options") or {}
        self.warehouse_stats = {}
        redact_kinds = self._redact_kinds(options.get("auto_redact"))
        profile = self.profile.get()
        redactor = Redactor(redact_kinds, build_dynamic_patterns(profile))

        context, manifest, excluded, warnings = self._collect(selections, purpose, redactor, profile)

        system_text = redactor.apply(prompts.system_prompt(purpose), path=f"messages[0].content")
        user_text = prompts.render_user_content(purpose, context)
        user_text = redactor.apply(user_text, path="messages[1].content")

        payload: dict[str, Any] = {
            "model": route.model,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            "temperature": route.temperature,
            "max_tokens": route.max_tokens,
            "stream": False,
        }
        if spec.json_mode:
            payload["response_format"] = {"type": "json_object"}

        fields = self._manifest(system_text, user_text, manifest)
        total_chars = len(system_text) + len(user_text)
        if total_chars > PROMPT_NEAR_LIMIT_CHARS:
            warnings.append(
                {
                    "code": "PROMPT_NEAR_LIMIT",
                    "message": f"本次将发送 {total_chars} 字符，接近单次上限，建议减少选中的经历包",
                }
            )
        # 出站前最后一道身份断言：姓名/电话/邮箱/照片哈希若仍留在 payload 中 → 500（零出网）；
        # 学校名允许且必须保留真实值（竞争力判断依据，用户 2026-10-23 定稿）。
        assert_no_identity(
            canonical_payload_bytes(payload).decode("utf-8", "ignore"),
            profile,
            self._photo_hashes(),
        )
        digest = payload_sha256(payload)
        created = datetime.now().astimezone()
        expires = created + timedelta(seconds=PREVIEW_TTL_SECONDS)

        preview_id = self.previews.create(
            {
                "purpose": purpose,
                "provider": route.provider,
                "model": route.model,
                "endpoint_host": route.endpoint_host,
                "payload": payload,
                "payload_sha256": digest,
                "fields": fields,
                "est_tokens": est_tokens(total_chars),
                "redactions": redactor.records,
                "expires_at": db_mod.to_iso(expires),
            }
        )
        log.info(
            "consent preview 建立 purpose=%s preview=%s chars=%s fields=%s redactions=%s",
            purpose,
            preview_id,
            total_chars,
            len(fields),
            len(redactor.records),
        )
        return {
            "preview_id": preview_id,
            "purpose": purpose,
            "provider": route.provider,
            "model": route.model,
            "endpoint_host": route.endpoint_host,
            "expires_at": db_mod.to_iso(expires),
            "payload": payload,
            "payload_sha256": digest,
            "total_chars": total_chars,
            "est_tokens": est_tokens(total_chars),
            "fields": fields,
            "excluded": excluded,
            "context": dict(self.warehouse_stats),
            "redactions": redactor.records,
            "warnings": warnings,
        }

    def _warehouse_context(
        self,
        redactor: Redactor,
        jd_id: str | None,
        manifest: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
        """JD 分析时自动带上仓库里**已就绪**的经历要点（只发要点文本，不发 tokens/id）。

        没有这一段，模型只能看见档案，于是会写「档案未体现 A/B 测试经验」——
        而用户仓库里就有这么一个项目。按与 JD 技能词的重合度取前 N 条，
        总字符封顶；超出的部分降级为 warning，绝不静默丢弃。
        """
        jd_text = ""
        if jd_id:
            jd = self.jds.get(jd_id)
            jd_text = str(jd.get("raw_text") or "")
        jd_tokens = _jd_tokens(jd_text)

        rows = self.conn.execute(
            "SELECT id, title, kind, org, role, start_date, end_date, is_current FROM package "
            "WHERE deleted_at IS NULL AND status = 'ready' ORDER BY updated_at DESC"
        ).fetchall()

        candidates: list[tuple[int, dict[str, Any], list[str], str]] = []
        for row in rows:
            variants = [v for v in self.packages.list_variants(row["id"]) if str(v.get("text") or "").strip()]
            if not variants:
                continue
            bullets = [str(v["text"]).strip() for v in variants]
            blob = " ".join([str(row["title"] or ""), str(row["org"] or ""), str(row["role"] or ""), *bullets])
            norm_blob = _norm(blob)
            score = sum(1 for token in jd_tokens if token in norm_blob)
            period = " - ".join(
                filter(None, [str(row["start_date"] or ""), str(row["end_date"] or ("至今" if row["is_current"] else ""))])
            )
            entry = {
                "title": row["title"],
                "kind": row["kind"],
                "org": row["org"] or "",
                "role": row["role"] or "",
                "period": period,
                "bullets": bullets,
            }
            candidates.append((score, entry, bullets, str(row["id"])))

        candidates.sort(key=lambda item: -item[0])

        included: list[dict[str, Any]] = []
        chars = 0
        skipped = 0
        for score, entry, _bullets, package_id in candidates:
            if len(included) >= WAREHOUSE_MAX_PACKAGES:
                skipped += 1
                continue
            cost = len(json.dumps(entry, ensure_ascii=False))
            if chars + cost > WAREHOUSE_MAX_CHARS:
                skipped += 1
                continue
            chars += cost
            redacted = self._redact_entry(entry, redactor)
            included.append(redacted)
            # source 必须是 "packages"、source_id 必须是包 id：字段清单要能反查到
            # 「这一行来自哪个经历包」，用户在确认弹窗里点得回原经历（AC-ANL-13）。
            manifest.append(
                self._field(
                    f"package:{package_id}",
                    f"经历要点：{entry['title']}",
                    "package",
                    "packages",
                    package_id,
                    entry,
                    "messages[1].content",
                )
            )

        warnings: list[dict[str, Any]] = []
        if skipped:
            warnings.append(
                {
                    "code": "PACKAGES_TRUNCATED",
                    "severity": "info",
                    "message": f"仓库经历较多，本次只带了 {len(included)} 条（另有 {skipped} 条未带）",
                    "details": {"included": len(included), "skipped": skipped},
                }
            )
        stats = {"packages_included": len(included), "chars": chars}
        return included, stats, warnings

    def _photo_hashes(self) -> list[str]:
        """私有照片的 sha256：照片字节结构性排除，指纹也不许出现在 payload 里。"""
        rows = self.conn.execute(
            "SELECT sha256 FROM attachment WHERE kind='photo' AND sha256 IS NOT NULL"
        ).fetchall()
        return [str(row["sha256"]) for row in rows]

    def _redact_kinds(self, auto_redact: bool | None) -> list[str]:
        """计算本次生效的脱敏类别。

        ``name`` / ``school`` 是**强制类别**（用户拍板「永不外发」），无论
        ``auto_redact`` 传 True/False/未给都恒生效；可关的只有用户自己的
        phone / email / id。
        """
        if auto_redact is True:
            kinds = list(DEFAULT_REDACT_KINDS)
        elif auto_redact is False:
            kinds = []
        else:
            configured = self.settings.get("auto_redact", list(DEFAULT_REDACT_KINDS))
            kinds = [kind for kind in configured if isinstance(kind, str)] if isinstance(configured, list) else list(DEFAULT_REDACT_KINDS)
        for forced in FORCED_REDACT_KINDS:
            if forced not in kinds:
                kinds.append(forced)
        return kinds

    def _collect(
        self,
        selections: Mapping[str, Any],
        purpose: str,
        redactor: Redactor,
        profile: Mapping[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, str]]]:
        """按 ID 取数并生成 (context, manifest 片段, excluded, warnings)。"""
        warnings: list[dict[str, str]] = []
        manifest: list[dict[str, Any]] = []
        context: dict[str, Any] = {}

        if not profile.get("name_zh"):
            warnings.append({"code": "PROFILE_INCOMPLETE", "message": "个人资料尚未填写，将只发送已选经历"})

        # 所有调用点都带「候选人档案」段：jd_analyze 要用校名判断竞争力，company_profile
        # 要推理院校偏好，build_suggest 要按院校信号选包。该段只含
        # {school, degree, major, grad_year, city, available_date}，姓名/电话/邮箱/照片结构上不在内。
        include_profile = purpose in (
            "jd_analyze", "bullets_generate", "build_suggest", "summary_polish", "company_profile"
        )
        if include_profile:
            brief = self.profile.llm_brief()
            manifest.append(self._field("profile", "个人档案摘要", "profile", "user_profile", "me", brief, "messages[1].content"))
            # 七项一律给出（未知写 null）：模型要能区分「没填」与「没有这个字段」。
            # 早前用 `if v` 过滤，available_date 为空时整个键消失，模型只能猜。
            context["候选人档案"] = {k: (v if v not in ("", None) else None) for k, v in brief.items()}

        package_ids: list[str] = list(dict.fromkeys(selections.get("package_ids") or []))
        variant_ids: list[str] = list(dict.fromkeys(selections.get("variant_ids") or []))
        # bullets_generate 的精细选择：只送指定的事实条目与语气，其余不读（AC-PRIV-01/02）
        wanted_keys = {str(k) for k in (selections.get("bullet_keys") or []) if str(k or "").strip()}
        wanted_tones = {str(t) for t in (selections.get("tones") or []) if str(t or "").strip()}
        wanted_lang = str(selections.get("lang") or "").strip() or None
        packages = []
        skipped_unselected = 0
        total_packages = int(self.conn.execute("SELECT COUNT(*) FROM package WHERE deleted_at IS NULL").fetchone()[0])
        total_variants = int(self.conn.execute("SELECT COUNT(*) FROM package_bullet_variant").fetchone()[0])
        selected_variants = 0

        for package_id in package_ids:
            package = self.packages.get(package_id)
            if package is None:
                warnings.append(
                    {"code": "PACKAGE_SKIPPED", "message": f"经历包 {package_id} 不存在（可能已删除），已跳过"}
                )
                continue
            packages.append(package)

        if not packages and purpose in ("jd_analyze", "company_profile"):
            pass  # 这两个 purpose 不依赖经历包

        # 组装经历文本（只含显式选中字段）
        entries: list[dict[str, Any]] = []
        for package in packages:
            entry: dict[str, Any] = {
                "title": package.get("title"),
                "kind": package.get("kind"),
                "org": package.get("org") or "",
                "role": package.get("role") or "",
                "period": " - ".join(filter(None, [package.get("start_date"), package.get("end_date") or ("至今" if package.get("is_current") else "")])),
                "summary": package.get("summary") or "",
                "tech_stack": package.get("tech_stack") or [],
                "outcomes": package.get("outcomes") or [],
            }
            manifest.extend(
                self._package_fields(package, entry_path=f"messages[1].content#package:{package.get('id')}")
            )
            variants = self.packages.list_variants(package["id"])
            if variant_ids:
                chosen = [v for v in variants if v["id"] in variant_ids]
            elif purpose == "bullets_generate":
                # 改写时优先拿「已核实」的事实；没有已核实事实才退回全部（并在 warnings 里说明）
                verified_only = [v for v in variants if v.get("verified")]
                if not verified_only:
                    warnings.append(
                        {
                            "code": "PACKAGE_NOT_READY",
                            "message": f"经历包《{package.get('title')}》没有已核实的事实，改写结果需人工逐条核对",
                        }
                    )
                chosen = verified_only or variants
            else:
                chosen = list(variants)
            if wanted_keys:
                chosen = [v for v in chosen if str(v.get("bullet_key") or "") in wanted_keys]
            if wanted_tones:
                chosen = [v for v in chosen if str(v.get("tone") or "") in wanted_tones]
            if wanted_lang:
                same_lang = [v for v in chosen if str(v.get("lang") or "") == wanted_lang]
                if same_lang or purpose != "bullets_generate":
                    chosen = same_lang
                # 英文变体生成：目标语言是**产出**语言，源事实通常只有中文。
                # 这时不能把 source 也过滤空，否则送给模型的是空上下文（模型只能编）。
                # 保留中文源句，并在「改写要求.输出语言」里明确要求输出英文。
            entry["bullets"] = [v["text"] for v in chosen]
            selected_variants += len(chosen)
            for variant in chosen:
                manifest.append(
                    self._field(
                        f"variant:{variant['id']}",
                        f"bullet（{variant.get('tone')}/{variant.get('lang')}）",
                        "variant",
                        variant["id"],
                        variant["id"],
                        variant["text"],
                        "messages[1].content",
                    )
                )
            redacted_entry = self._redact_entry(entry, redactor)
            entries.append(redacted_entry)
            skipped_unselected += max(0, len(variants) - len(chosen))

        if entries:
            context["已选经历"] = entries

        if purpose == "bullets_generate" and (wanted_tones or wanted_lang or wanted_keys):
            # 明确告诉模型这次要产出哪几种语气 —— 否则它会按自己的喜好编造变体
            target: dict[str, Any] = {}
            if wanted_tones:
                target["目标语气"] = sorted(wanted_tones)
            if wanted_lang:
                target["语言"] = wanted_lang
                target["输出语言"] = (
                    "英文（English only，不得夹杂中文；专有名词与技术缩写可保留原文）"
                    if wanted_lang == "en"
                    else "中文（简体，保留技术缩写原文）"
                )
            if wanted_keys:
                target["对应事实"] = sorted(wanted_keys)
            context["改写要求"] = target

        jd_id = selections.get("jd_id")
        if jd_id:
            jd = self.jds.get(jd_id)
            jd_text = redactor.apply(str(jd.get("raw_text") or ""), path=f"jd:{jd_id}")
            manifest.append(self._field(f"jd:{jd_id}", "JD 原文", "jd_text", jd_id, jd_id, jd_text, "messages[1].content"))
            context["岗位描述"] = {
                "title": jd.get("title") or "",
                "company": jd.get("company_name") or "",
                "text": jd_text,
            }

        # JD 分析必须看见仓库里已有的经历：否则模型只能凭档案说「没有 A/B 测试经验」，
        # 而用户仓库里就有这个项目（captain 2026-10-23 P0）。
        if purpose == "jd_analyze":
            entries, stats, wh_warnings = self._warehouse_context(redactor, jd_id, manifest)
            if entries:
                context["仓库经历"] = entries
            self.warehouse_stats = stats
            warnings.extend(wh_warnings)

        company_id = selections.get("company_profile_id")
        if company_id:
            company = self.companies.get(company_id)
            note = {
                "company_name": company.get("company_name"),
                "industry": company.get("industry"),
                "tone": company.get("tone"),
                "hiring_preferences": company.get("hiring_preferences") or [],
                "interview_focus": company.get("interview_focus") or [],
            }
            manifest.append(
                self._field(f"company:{company_id}", "公司档案", "company_note", company_id, company_id, note, "messages[1].content")
            )
            context["公司档案"] = {k: v for k, v in note.items() if v}

        instruction = selections.get("extra_instruction")
        if instruction:
            context["补充要求"] = redactor.apply(str(instruction), path="extra_instruction")
            manifest.append(
                self._field("extra_instruction", "用户补充要求", "user_instruction", "selections", "extra_instruction", instruction, "messages[1].content")
            )

        excluded = {
            "packages_total": total_packages,
            "packages_selected": len(packages),
            "variants_total": total_variants,
            "variants_selected": selected_variants,
            "skipped": [
                {"kind": "package", "reason": "not_selected", "count": max(0, total_packages - len(packages))},
                {"kind": "variant", "reason": "not_selected", "count": max(0, total_variants - selected_variants)},
                {"kind": "attachment", "reason": "local_only", "count": self._private_attachment_count()},
                {"kind": "profile_field", "reason": "pii_structural_exclusion", "count": 3},
                {"kind": "profile_field", "reason": "placeholder_substitution", "count": 1},
            ],
            "structural_exclusions": ["profile.phone", "profile.email", "profile.photo_path"],
            "placeholder_substitutions": {
                "profile.name_zh": REDACT_NAME,
                "note": "姓名恒脱敏（强制类别，不可关闭）；学校名按真实值发送（用户定稿：有分析价值）",
            },
            "note": (
                "原始简历文件（data/imports）与照片永不发送；姓名固定脱敏为 [NAME]（不可关闭）；"
                "学校名按真实值发送；电话、邮箱默认脱敏为 [PHONE]/[EMAIL]，可在设置里关闭脱敏，"
                "但本机身份校验仍会拦截，实际不会发送；被跳过的经历包不会被读取。"
            ),
        }
        return context, manifest, excluded, warnings

    def _private_attachment_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM attachment WHERE privacy = 'private'").fetchone()
        return int(row[0]) if row else 0

    def _redact_entry(self, entry: Mapping[str, Any], redactor: Redactor) -> dict[str, Any]:
        redacted: dict[str, Any] = {}
        for key, value in entry.items():
            if isinstance(value, str):
                redacted[key] = redactor.apply(value, path=f"messages[1].content#{key}")
            elif isinstance(value, list):
                redacted[key] = [
                    redactor.apply(item, path=f"messages[1].content#{key}[]") if isinstance(item, str) else item
                    for item in value
                ]
            else:
                redacted[key] = value
        return redacted

    def _package_fields(self, package: Mapping[str, Any], *, entry_path: str) -> list[dict[str, Any]]:
        fields = []
        for key, label in (
            ("title", "经历标题"),
            ("org", "组织"),
            ("role", "角色"),
            ("start_date", "开始时间"),
            ("end_date", "结束时间"),
            ("summary", "概述"),
        ):
            value = package.get(key)
            if value:
                fields.append(self._field(f"{entry_path}.{key}", label, "package", package["id"], package["id"], value, "messages[1].content"))
        for key, label in (("tech_stack", "技术栈"), ("outcomes", "成果")):
            values = package.get(key) or []
            if values:
                fields.append(
                    self._field(f"{entry_path}.{key}", label, "package", package["id"], package["id"], " / ".join(map(str, values)), "messages[1].content")
                )
        return fields

    @staticmethod
    def _field(path: str, label: str, kind: str, source_id: str, id_value: str, value: Any, container: str) -> dict[str, Any]:
        chars = len(value) if isinstance(value, str) else len(json.dumps(value, ensure_ascii=False))
        return {
            "path": path,
            "label": label,
            "kind": kind,
            "source": source_id,
            "source_id": id_value,
            "chars": chars,
            "est_tokens": est_tokens(chars),
            "included": True,
            "redacted": isinstance(value, str) and ("[PHONE]" in value or "[EMAIL]" in value or "[ID]" in value),
        }

    def _manifest(self, system_text: str, user_text: str, collected: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fields = [
            {
                "path": "messages[0].content",
                "label": "系统提示词（固定模板）",
                "kind": "system_prompt",
                "source": "template",
                "source_id": "prompts.py",
                "chars": len(system_text),
                "est_tokens": est_tokens(len(system_text)),
                "included": True,
                "redacted": False,
            },
            {
                "path": "messages[1].content",
                "label": "用户消息（已选数据 + 指令）",
                "kind": "user_instruction",
                "source": "composed",
                "source_id": "consent",
                "chars": len(user_text),
                "est_tokens": est_tokens(len(user_text)),
                "included": True,
                "redacted": bool(re.search(r"\[(PHONE|EMAIL|ID)\]", user_text)),
            },
        ]
        return fields + collected

    # -- 状态流转 --------------------------------------------------------------
    def get_preview(self, preview_id: str) -> dict[str, Any]:
        preview = self.previews.get(preview_id)
        return {
            "preview_id": preview["id"],
            "purpose": preview["purpose"],
            "provider": preview["provider"],
            "model": preview["model"],
            "endpoint_host": preview["endpoint_host"],
            "status": preview["status"],
            "expires_at": preview["expires_at"],
            "seconds_left": db_mod.seconds_left(preview["expires_at"]),
            "payload": preview["payload"],
            "payload_sha256": preview["payload_sha256"],
            "fields": preview["fields"],
            "redactions": preview["redactions"],
            "est_tokens": preview["est_tokens"],
            "created_at": preview["created_at"],
        }

    def reject(self, preview_id: str) -> dict[str, Any]:
        preview = self.previews.get(preview_id)
        if preview["status"] != "pending":
            raise ApiError(
                "LLM_CONSENT_MISMATCH",
                "该预览已不处于待确认状态",
                details={"status": preview["status"]},
            )
        self.previews.reject(preview_id)
        return {"preview_id": preview_id, "status": "rejected"}

    def complete(self, preview_id: str, expected_sha256: str) -> dict[str, Any]:
        # provider=off 是「完全不上云」的硬开关：即使预览已经确认过也不许发（AC-LLM-03）
        if str(self.cfg.llm_provider or "").lower() == "off":
            raise ApiError(
                "LLM_DISABLED",
                "已在设置里关闭 LLM（不使用 AI 模式），本次不会发送任何数据",
                hint="需要 AI 改写时，在设置页打开 provider",
            )
        preview = self.previews.get(preview_id)
        if preview["status"] == "expired" or db_mod.seconds_left(preview["expires_at"]) <= 0:
            self.previews.expire_stale()
            raise ApiError(
                "LLM_CONSENT_EXPIRED",
                "预览已过期，请重新预览",
                details={"expires_at": preview["expires_at"]},
            )
        if preview["status"] != "pending":
            raise ApiError(
                "LLM_CONSENT_MISMATCH",
                "该预览已被使用或已放弃，请重新预览",
                details={"status": preview["status"]},
            )
        if preview["payload_sha256"] != expected_sha256:
            raise ApiError(
                "LLM_CONSENT_MISMATCH",
                "确认的发送内容与预览不一致（可能被篡改），已拒绝发送",
                details={"expected": expected_sha256[:12] + "…", "actual": preview["payload_sha256"][:12] + "…"},
            )
        payload = preview["payload"]
        purpose = preview["purpose"]
        # 契约 v1.4：canonical_payload_bytes 之后、httpx.post 之前的最后断言。
        # 命中即 500，宁可失败也绝不把姓名/电话/邮箱/照片发出去（此时零出网）；
        # 学校名允许且必须保留真实值（竞争力判断依据）。
        assert_no_identity(
            canonical_payload_bytes(payload).decode("utf-8", "ignore"),
            self.profile.get(),
            self._photo_hashes(),
        )
        started = db_mod.utcnow_iso()
        try:
            result = self.client.chat(
                payload,
                purpose=purpose,
                provider=preview["provider"],
                model=preview["model"],
                validator=_validator_for(purpose),
            )
        except ApiError as exc:
            # 契约 §10.4：只有「拿到 HTTP 响应」才把 preview 置 consumed；
            # 连接级失败（请求体根本没发出去）与本地前置校验（零出网）都保持 pending，
            # 用户可以原样再点一次「发送」，不会被误判为 LLM_CONSENT_MISMATCH。
            got_response = bool(exc.details.get("http_status")) or exc.code in (
                "LLM_TRUNCATED",
                "LLM_BAD_RESPONSE",
            )
            if got_response:
                self.previews.consume(preview_id)
            self._log_call(preview, payload, ok=False, http_status=exc.details.get("http_status"), error_code=exc.code)
            log.warning("LLM 调用失败 purpose=%s preview=%s code=%s consumed=%s", purpose, preview_id, exc.code, got_response)
            raise
        if not self.previews.consume(preview_id):
            # 数据已经发出，不吞掉结果；只记录竞态（理论上不可能同时 complete 同一 preview）
            log.warning("preview 消费竞态 preview=%s（结果仍返回）", preview_id)
        self._log_call(preview, payload, ok=True, http_status=result.http_status, error_code=None, latency_ms=result.latency_ms, result=result)

        response = {
            "preview_id": preview_id,
            "raw_text": result.raw_text,
            "parsed": result.parsed,
            "usage": result.usage,
            "provider": result.provider,
            "model": result.model,
            "latency_ms": result.latency_ms,
            "finish_reason": result.finish_reason,
            "warnings": result.warnings,
            "started_at": started,
        }
        return response

    def _log_call(
        self,
        preview: Mapping[str, Any],
        payload: Mapping[str, Any],
        *,
        ok: bool,
        http_status: Any,
        error_code: str | None,
        latency_ms: int | None = None,
        result: llm_client.LlmResult | None = None,
    ) -> None:
        field_names = [str(field.get("path")) for field in preview.get("fields") or []]
        size = len(canonical_payload_bytes(payload))
        self.logs.append(
            preview_id=str(preview["id"]),
            provider=str(preview["provider"]),
            model=str(preview["model"]),
            endpoint_host=str(preview["endpoint_host"]),
            # v8：日志记 purpose，事后可证「分析档走 LLM_MODEL_ANALYSIS、对话档走 LLM_MODEL」，
            # 不必依赖 preview 行是否还存在（preview 会被清理/过期）。
            purpose=str(preview.get("purpose") or "") or None,
            field_names=field_names,
            payload_bytes=size,
            est_tokens=int(preview.get("est_tokens") or 0),
            http_status=int(http_status) if isinstance(http_status, int) else None,
            latency_ms=latency_ms,
            ok=ok,
            error_code=error_code,
        )


def get_service(conn=None) -> ConsentService:
    return ConsentService(conn=conn)
