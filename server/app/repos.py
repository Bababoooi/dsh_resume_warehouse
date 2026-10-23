"""各实体的 Repository / CRUD（DATA-MODEL 的唯一写库入口）。

约定：
* 所有写操作走 :func:`db.transaction`（BEGIN IMMEDIATE），失败自动回滚；
* 业务不变量（I1/I2 等）在这里落成显式检查，抛契约错误码；
* JSON 列统一在 repository 边界内完成序列化/反序列化，上层只看到 Python 对象。
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any, Iterable, Mapping, Sequence

from . import db as db_mod
from . import models
from .errors import ApiError

# --------------------------------------------------------------------------------------
# 工具
# --------------------------------------------------------------------------------------

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[+#._-][A-Za-z0-9]+)*")


def cjk_bigrams(text: str) -> list[str]:
    """把中文连续串切成 bigram（unicode61 不切中文，检索靠 bigram 命中）。"""
    grams: list[str] = []
    for run in _CJK_RE.findall(text or ""):
        if len(run) == 1:
            grams.append(run)
            continue
        grams.extend(run[i : i + 2] for i in range(len(run) - 1))
    return grams


def tokenize_for_index(text: str) -> str:
    tokens = cjk_bigrams(text) + [t.lower() for t in _TOKEN_RE.findall(text or "")]
    return " ".join(dict.fromkeys(tokens))


def build_fts_query(query: str) -> str:
    """用户输入 → FTS5 MATCH 表达式（OR 语义，前缀匹配英文，bigram 匹配中文）。"""
    query = (query or "").strip()
    if not query:
        return ""
    clauses: list[str] = []
    for gram in cjk_bigrams(query):
        clauses.append(f'"{gram}"')
    for token in _TOKEN_RE.findall(query):
        clauses.append(f'"{token.lower()}"*')
    if not clauses:
        safe = query.replace('"', " ")
        clauses.append(f'"{safe}"')
    return " OR ".join(dict.fromkeys(clauses))


# --------------------------------------------------------------------------------------
# UserProfile（单例）
# --------------------------------------------------------------------------------------

PROFILE_FIELDS: tuple[str, ...] = (
    "name_zh",
    "name_en",
    "school_zh",
    "school_en",
    "degree",
    "major",
    "grad_year",
    "phone",
    "email",
    "city",
    "available_date",
    "available_note",
    "photo_path",
    "school_tier",
)

#: 完整度计算用的关键字段（photo/available_note 不计入）
COMPLETENESS_FIELDS: tuple[str, ...] = (
    "name_zh",
    "school_zh",
    "degree",
    "major",
    "grad_year",
    "phone",
    "email",
    "city",
)


class ProfileRepo:
    TABLE = "user_profile"

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or db_mod.get_conn()

    def _decode(self, row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any]:
        if row is None:
            return self._empty()
        data = dict(row)
        data["links"] = db_mod.loads_json(data.pop("links_json", "[]"), [])
        data["extra"] = db_mod.loads_json(data.pop("extra_json", "{}"), {})
        data["skills"] = db_mod.loads_json(data.pop("skills_json", "[]"), [])
        return data

    @staticmethod
    def _empty() -> dict[str, Any]:
        data: dict[str, Any] = {field: None for field in PROFILE_FIELDS}
        data.update({"id": "me", "links": [], "extra": {}, "skills": [], "created_at": None, "updated_at": None})
        return data

    def get(self) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM user_profile WHERE id = 'me'").fetchone()
        return self._decode(row)

    def exists(self) -> bool:
        return self.conn.execute("SELECT 1 FROM user_profile WHERE id='me'").fetchone() is not None

    def upsert(self, patch: Mapping[str, Any]) -> dict[str, Any]:
        """部分更新：``None`` 表示清空（name_zh 除外），未提供的键保持原值。"""
        current = self.get()
        now = db_mod.utcnow_iso()
        payload: dict[str, Any] = {}
        for key, value in patch.items():
            if key in ("links", "extra", "skills"):
                column = {"links": "links_json", "extra": "extra_json", "skills": "skills_json"}[key]
                payload[column] = db_mod.dumps_json(value if value is not None else ({} if key == "extra" else []))
            elif key in PROFILE_FIELDS:
                payload[key] = value
        if "name_zh" in payload and not payload["name_zh"]:
            raise ApiError(
                "VALIDATION_ERROR",
                "姓名不能为空",
                details={"fields": [{"field": "name_zh", "rule": "required", "message": "姓名不能清空"}]},
            )
        # 到岗时间有「结构化日期 / 中文原文 / 英文表述」三处可能来源：
        # 用户在界面上改的是 `available_note`（中文真值），这里顺手把它同步进
        # `extra.available_note_zh`，否则 LLM 侧仍会读到导入时的旧原文（改了没效果）。
        if "available_note" in payload:
            base = (
                db_mod.loads_json(payload["extra_json"], {})
                if "extra_json" in payload
                else dict(current.get("extra") or {})
            )
            note = payload["available_note"]
            if note:
                base["available_note_zh"] = note
            else:
                base.pop("available_note_zh", None)
            payload["extra_json"] = db_mod.dumps_json(base)

        payload["updated_at"] = now
        if not self.exists():
            if "name_zh" not in payload or not payload["name_zh"]:
                raise ApiError(
                    "VALIDATION_ERROR",
                    "首次填写资料必须提供姓名",
                    details={"fields": [{"field": "name_zh", "rule": "required", "message": "请先填写姓名"}]},
                )
            payload.update({"id": "me", "created_at": now})
            payload.setdefault("links_json", "[]")
            payload.setdefault("extra_json", "{}")
            payload.setdefault("skills_json", "[]")
            cols = list(payload)
            with db_mod.transaction(self.conn) as conn:
                conn.execute(
                    f"INSERT INTO user_profile ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                    [payload[c] for c in cols],
                )
        else:
            assignments = ", ".join(f"{col} = ?" for col in payload)
            with db_mod.transaction(self.conn) as conn:
                conn.execute(
                    f"UPDATE user_profile SET {assignments} WHERE id = 'me'",
                    [*payload.values()],
                )
        return self.get()

    def completeness(self, profile: Mapping[str, Any] | None = None) -> dict[str, Any]:
        profile = profile or self.get()
        missing = [field for field in COMPLETENESS_FIELDS if not profile.get(field)]
        total = len(COMPLETENESS_FIELDS)
        return {
            "completeness": round((total - len(missing)) / total, 2),
            "missing": missing,
        }

    def public_view(self) -> dict[str, Any]:
        """对外 GET /profile 的返回体（含 completeness/missing，不含内部列）。"""
        profile = self.get()
        view = {field: profile.get(field) for field in PROFILE_FIELDS}
        view.update(
            {
                "id": "me",
                "links": profile.get("links") or [],
                "extra": profile.get("extra") or {},
                "skills": profile.get("skills") or [],
                "created_at": profile.get("created_at"),
                "updated_at": profile.get("updated_at"),
            }
        )
        view.update(self.completeness(profile))
        return view

    def llm_brief(self) -> dict[str, Any]:
        """给 LLM 用的最小档案（用户 m00265 定稿的边界）。

        **永不含**姓名 / 电话 / 邮箱 / 照片；学校名按真实值上行（院校层次、
        校招节奏、届别推断都需要它，用户明确要求保留）。
        """
        profile = self.get()
        extra = profile.get("extra") or {}
        brief: dict[str, Any] = {
            "school": profile.get("school_zh") or profile.get("school_en") or "",
            "degree": profile.get("degree") or "",
            "major": profile.get("major") or "",
            "grad_year": profile.get("grad_year") or "",
            "city": profile.get("city") or "",
            # 到岗时间：结构化日期优先，没有就用用户写下的原文（「2027年1月下旬」）。
            # 空着不上行，模型只能猜；有原文就该按原文发。
            "available_date": (
                profile.get("available_date")
                or extra.get("available_note_zh")
                or profile.get("available_note")
                or ""
            ),
        }
        tier = profile.get("school_tier") or extra.get("school_tier")
        if isinstance(tier, str) and tier.strip():
            # 只接受人工填写的固定枚举，不让模型猜（如「985」「双一流」「QS100」）
            brief["school_tier"] = tier.strip()
        # 技能行整句上行：模型据此判断「会不会 SQL/Python」。早前只发六项，
        # 结果模型写「档案未列出 SQL/Python 技能」——用户被自己的系统判成没技能。
        skills = [
            {
                "line": str(row.get("line") or "").strip(),
                "category": str(row.get("category") or "").strip(),
            }
            for row in (profile.get("skills") or [])
            if str(row.get("line") or "").strip()
        ]
        if skills:
            brief["skills"] = skills
        return brief


# --------------------------------------------------------------------------------------
# Attachment / Job / Settings 等支撑表
# --------------------------------------------------------------------------------------


class AttachmentRepo:
    TABLE = "attachment"

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or db_mod.get_conn()

    def get(self, attachment_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM attachment WHERE id = ?", (attachment_id,)).fetchone()
        return dict(row) if row else None

    def get_by_sha(self, sha256: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM attachment WHERE sha256 = ?", (sha256,)).fetchone()
        return dict(row) if row else None

    def list(self, *, kind: str | None = None, privacy: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        params: list[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if privacy:
            clauses.append("privacy = ?")
            params.append(privacy)
        params.append(limit)
        rows = self.conn.execute(
            f"SELECT * FROM attachment WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]


class JobRepo:
    TABLE = "job"

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or db_mod.get_conn()

    def create(self, kind: str, *, message: str | None = None) -> str:
        job_id = db_mod.new_id()
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "INSERT INTO job(id, kind, status, progress, message, created_at) VALUES (?, ?, 'queued', 0, ?, ?)",
                (job_id, kind, message, db_mod.utcnow_iso()),
            )
        return job_id

    def get(self, job_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise ApiError("NOT_FOUND", "任务不存在", details={"resource": "job", "id": job_id})
        data = dict(row)
        data["result_json"] = db_mod.loads_json(data.get("result_json"), None)
        data["error_json"] = db_mod.loads_json(data.get("error_json"), None)
        return data

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        result: Any | None = None,
        error: Any | None = None,
    ) -> None:
        sets: list[str] = []
        params: list[Any] = []
        if status is not None:
            sets.append("status = ?")
            params.append(status)
            if status in ("succeeded", "failed", "interrupted"):
                sets.append("finished_at = ?")
                params.append(db_mod.utcnow_iso())
        if progress is not None:
            sets.append("progress = ?")
            params.append(max(0, min(100, progress)))
        if message is not None:
            sets.append("message = ?")
            params.append(message)
        if result is not None:
            sets.append("result_json = ?")
            params.append(db_mod.dumps_json(result))
        if error is not None:
            sets.append("error_json = ?")
            params.append(db_mod.dumps_json(error))
        if not sets:
            return
        params.append(job_id)
        with db_mod.transaction(self.conn) as conn:
            conn.execute(f"UPDATE job SET {', '.join(sets)} WHERE id = ?", params)

    def list(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        params.append(limit)
        rows = self.conn.execute(
            f"SELECT * FROM job WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?", params
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_interrupted(self) -> int:
        """进程启动时调用：把残留的 running/queued 任务标为 interrupted（ARCHITECTURE §6）。"""
        with db_mod.transaction(self.conn) as conn:
            cur = conn.execute(
                "UPDATE job SET status='interrupted', finished_at=?, message=COALESCE(message,'进程重启导致中断')"
                " WHERE status IN ('queued','running')",
                (db_mod.utcnow_iso(),),
            )
        return cur.rowcount


class SettingsRepo:
    """app_setting 的读写（值是 JSON 文本；这里做类型化访问）。"""

    DEFAULTS: dict[str, Any] = {
        "naming_template": "{position}-{name}-{school}",
        "default_engine": "auto",
        "verify_text": True,
        "page_limit": 1,
        "theme": "light",
        "auto_redact": ["phone", "email", "id", "name"],
        "last_template_id": None,
    }

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or db_mod.get_conn()

    def get_raw(self, key: str) -> Any:
        row = self.conn.execute("SELECT value FROM app_setting WHERE key = ?", (key,)).fetchone()
        if row is None:
            return self.DEFAULTS.get(key)
        return db_mod.loads_json(row[0], self.DEFAULTS.get(key))

    def get(self, key: str, default: Any = None) -> Any:
        value = self.get_raw(key)
        return default if value is None else value

    def set(self, key: str, value: Any) -> None:
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "INSERT INTO app_setting(key, value, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, db_mod.dumps_json(value), db_mod.utcnow_iso()),
            )

    def all(self) -> dict[str, Any]:
        result = dict(self.DEFAULTS)
        for row in self.conn.execute("SELECT key, value FROM app_setting"):
            result[row[0]] = db_mod.loads_json(row[1], result.get(row[0]))
        return result

    def schema_version(self) -> int:
        row = self.conn.execute("SELECT MAX(version) FROM schema_migration").fetchone()
        return int(row[0]) if row and row[0] is not None else 0


# --------------------------------------------------------------------------------------
# Package + Variant
# --------------------------------------------------------------------------------------


class PackageRepo:
    TABLE = "package"
    COLUMNS: tuple[str, ...] = (
        "title",
        "kind",
        "org",
        "role",
        "start_date",
        "end_date",
        "is_current",
        "location",
        "summary",
        "tech_stack_json",
        "tags_json",
        "outcomes_json",
        "evidence_json",
        "status",
        "source",
        "content_hash",
        # v8：导入派生包的溯源两列（DATA-MODEL v1.12 的幂等键；schema 之前漏建，契约里
        # 的 UNIQUE(source_import_job_id, source_entry_temp_id) 一直无处落地）
        "source_import_job_id",
        "source_entry_temp_id",
    )
    JSON_COLUMNS: tuple[str, ...] = ("tech_stack_json", "tags_json", "outcomes_json", "evidence_json")

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or db_mod.get_conn()

    # -- 读 --------------------------------------------------------------------
    def _decode(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        data["tech_stack"] = db_mod.loads_json(data.pop("tech_stack_json", "[]"), [])
        data["tags"] = db_mod.loads_json(data.pop("tags_json", "[]"), [])
        data["outcomes"] = db_mod.loads_json(data.pop("outcomes_json", "[]"), [])
        data["evidence"] = db_mod.loads_json(data.pop("evidence_json", "[]"), [])
        data["is_current"] = bool(data.get("is_current"))
        return data

    def get(self, package_id: str, *, with_variants: bool = True) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM package WHERE id = ? AND deleted_at IS NULL", (package_id,)
        ).fetchone()
        data = self._decode(row)
        if data and with_variants:
            data["variants"] = self.list_variants(package_id)
        return data

    def require(self, package_id: str) -> dict[str, Any]:
        data = self.get(package_id)
        if data is None:
            raise ApiError("NOT_FOUND", "经历包不存在", details={"resource": "package", "id": package_id})
        return data

    def list(
        self,
        *,
        kind: str | None = None,
        status: str | None = None,
        q: str | None = None,
        tag: str | None = None,
        org: str | None = None,
        limit: int = 100,
        offset: int = 0,
        include_variants: bool = True,
    ) -> dict[str, Any]:
        clauses = ["deleted_at IS NULL"]
        params: list[Any] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if status:
            clauses.append("status = ?")
            params.append(status)
        else:
            # 归档（PKG-07）不等于删除：默认列表不返回，显式 status=archived 才看得到
            clauses.append("status != 'archived'")
        if tag:
            clauses.append("EXISTS (SELECT 1 FROM json_each(package.tags_json) WHERE json_each.value = ?)")
            params.append(tag)
        if org:
            clauses.append("org LIKE ? ESCAPE '\\'")
            params.append(f"%{db_mod.like_escape(org)}%")
        if q:
            ids = self.search_ids(q, limit=200)
            if not ids:
                return {"items": [], "total_estimate": 0}
            placeholders = ", ".join("?" for _ in ids)
            clauses.append(f"id IN ({placeholders})")
            params.extend(ids)
        total = self.conn.execute(
            f"SELECT COUNT(*) FROM package WHERE {' AND '.join(clauses)}", params
        ).fetchone()[0]
        params.extend([limit, offset])
        rows = self.conn.execute(
            f"SELECT * FROM package WHERE {' AND '.join(clauses)} ORDER BY COALESCE(end_date, start_date, '') DESC, created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        items = []
        for row in rows:
            item = self._decode(row)
            assert item is not None
            if include_variants:
                item["variants"] = self.list_variants(item["id"])
            items.append(item)
        return {"items": items, "total_estimate": int(total)}

    def search_ids(self, query: str, *, limit: int = 100) -> list[str]:
        match = build_fts_query(query)
        if not match:
            return []
        try:
            rows = self.conn.execute(
                "SELECT package_id FROM package_fts WHERE package_fts MATCH ? ORDER BY rank LIMIT ?",
                (match, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [row[0] for row in rows]

    def list_variants(self, package_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM package_bullet_variant WHERE package_id = ? ORDER BY bullet_key, tone, lang",
            (package_id,),
        ).fetchall()
        variants = []
        for row in rows:
            data = dict(row)
            data["keywords"] = db_mod.loads_json(data.pop("keywords_json", "[]"), [])
            data["metrics"] = db_mod.loads_json(data.pop("metrics_json", "[]"), [])
            data["verified"] = bool(data.get("verified"))
            data["llm_generated"] = bool(data.get("llm_generated"))
            variants.append(data)
        return variants

    # -- 写 --------------------------------------------------------------------
    def create(self, data: Mapping[str, Any]) -> str:
        payload = self._encode(data)
        package_id = db_mod.new_id()
        now = db_mod.utcnow_iso()
        payload.update({"id": package_id, "created_at": now, "updated_at": now})
        if payload.get("is_current"):
            payload["end_date"] = None
        cols = list(payload)
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                f"INSERT INTO package ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                [payload[c] for c in cols],
            )
        self.reindex(package_id)
        return package_id

    def update(self, package_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        current = self.require(package_id)
        payload = self._encode(data)
        if payload.get("is_current") and (payload.get("end_date") or current.get("end_date")):
            # is_current=1 时不允许有结束时间（DATA-MODEL 约束）
            payload["end_date"] = None
        if payload.get("status") == "ready":
            self._assert_ready(package_id)
        payload["updated_at"] = db_mod.utcnow_iso()
        assignments = ", ".join(f"{col} = ?" for col in payload)
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                f"UPDATE package SET {assignments} WHERE id = ?",
                [*payload.values(), package_id],
            )
        self.reindex(package_id)
        return self.require(package_id)

    def unverified_bullets(self, package_id: str) -> list[str]:
        """返回尚未核实（且没有任何已核实变体）的 bullet_key，供 ready 校验与 UI 提示。"""
        rows = self.conn.execute(
            "SELECT bullet_key, MAX(verified) AS verified FROM package_bullet_variant"
            " WHERE package_id = ? GROUP BY bullet_key ORDER BY bullet_key",
            (package_id,),
        ).fetchall()
        return [str(row[0]) for row in rows if not int(row[1] or 0)]

    def _assert_ready(self, package_id: str) -> None:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM package_bullet_variant WHERE package_id = ? AND verified = 1",
            (package_id,),
        ).fetchone()
        if not row or int(row[0]) == 0:
            raise ApiError(
                "CONFLICT",
                "标记为 ready 前至少需要 1 条已核实的 bullet",
                details={
                    "package_id": package_id,
                    "rule": "I1",
                    "reason": "PACKAGE_NEEDS_VERIFIED_VARIANT",
                    "unverified": self.unverified_bullets(package_id),
                },
                hint="先在变体列表勾选「已核实」，或先补写一条真实经历",
            )

    def delete(self, package_id: str) -> bool:
        with db_mod.transaction(self.conn) as conn:
            cur = conn.execute(
                "UPDATE package SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (db_mod.utcnow_iso(), db_mod.utcnow_iso(), package_id),
            )
            conn.execute("DELETE FROM package_fts WHERE package_id = ?", (package_id,))
        return cur.rowcount > 0

    def restore(self, package_id: str) -> dict[str, Any]:
        """撤销软删除（PKG-01）。已不存在的 id 走 404。"""
        row = self.conn.execute("SELECT id FROM package WHERE id = ?", (package_id,)).fetchone()
        if row is None:
            raise ApiError("NOT_FOUND", "经历包不存在", details={"resource": "package", "id": package_id})
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "UPDATE package SET deleted_at = NULL, updated_at = ? WHERE id = ?",
                (db_mod.utcnow_iso(), package_id),
            )
        self.reindex(package_id)
        return self.require(package_id)

    def duplicate(self, package_id: str, *, title_suffix: str = "（副本）") -> str:
        """复制为新草稿：变体一起带走但一律置为待核实，避免「复制即已核实」。"""
        source = self.require(package_id)
        payload: dict[str, Any] = {}
        for column in self.COLUMNS:
            if column in ("status", "content_hash"):
                continue
            if column in self.JSON_COLUMNS:
                payload[column.removesuffix("_json")] = source.get(column.removesuffix("_json"))
            else:
                payload[column] = source.get(column)
        payload["title"] = f"{source['title']}{title_suffix}"
        payload["status"] = "draft"
        payload["source"] = "authored"
        new_id = self.create(payload)
        for variant in source.get("variants") or []:
            self.add_variant(
                new_id,
                {
                    "bullet_key": variant["bullet_key"],
                    "tone": variant["tone"],
                    "lang": variant["lang"],
                    "text": variant["text"],
                    "keywords": variant.get("keywords") or [],
                    "metrics": variant.get("metrics") or [],
                    "verified": False,
                    "llm_generated": variant.get("llm_generated"),
                },
                conflict="update",
            )
        return new_id

    def stats(self) -> dict[str, int]:
        """库健康度（工作台「经历 N 条 / 变体 M 条 / 待核实 K 条 / 模板 L 套」）。"""
        def scalar(sql: str, params: Sequence[Any] = ()) -> int:
            row = self.conn.execute(sql, params).fetchone()
            return int(row[0] or 0) if row else 0

        return {
            "packages": scalar("SELECT COUNT(*) FROM package WHERE deleted_at IS NULL"),
            "variants": scalar(
                "SELECT COUNT(*) FROM package_bullet_variant v JOIN package p ON p.id = v.package_id"
                " WHERE p.deleted_at IS NULL"
            ),
            # 口径与 unverified_bullets() 一致：同一 bullet_key 只要有一条已核实就算核实过
            "unverified": scalar(
                "SELECT COUNT(*) FROM ("
                " SELECT v.package_id, v.bullet_key FROM package_bullet_variant v"
                " JOIN package p ON p.id = v.package_id WHERE p.deleted_at IS NULL"
                " GROUP BY v.package_id, v.bullet_key HAVING MAX(v.verified) = 0)"
            ),
            "ready": scalar("SELECT COUNT(*) FROM package WHERE deleted_at IS NULL AND status = 'ready'"),
            "templates": scalar("SELECT COUNT(*) FROM template WHERE deleted_at IS NULL"),
        }

    def _encode(self, data: Mapping[str, Any]) -> dict[str, Any]:
        mapping = {
            "tech_stack": "tech_stack_json",
            "tags": "tags_json",
            "outcomes": "outcomes_json",
            "evidence": "evidence_json",
        }
        payload: dict[str, Any] = {}
        for key, value in data.items():
            if key in mapping:
                payload[mapping[key]] = db_mod.dumps_json(value or [])
            elif key in self.COLUMNS:
                if key == "is_current":
                    # 三目写错过一次：``1 if isinstance(value, bool) ...`` 会把 False 也变成 1，
                    # 接着 create() 认为「至今在职」并把用户填的 end_date 抹成 NULL
                    # （真库 18 行全部 is_current=1 / end_date=NULL 就是它造成的）。
                    # 唯一正确写法是如实转换：True→1、False→0、None→0。
                    payload[key] = int(bool(value))
                else:
                    payload[key] = value
        return payload

    # -- 变体 ------------------------------------------------------------------
    def add_variant(
        self,
        package_id: str,
        data: Mapping[str, Any],
        *,
        conflict: str = "error",
    ) -> dict[str, Any]:
        """新建变体。

        ``conflict="error"``（HTTP POST 的默认语义）：``UNIQUE(package_id, bullet_key, tone, lang)``
        命中即 409，绝不静默覆盖用户已经核实过的表述；``conflict="update"`` 供复制/导入等内部路径使用。
        """
        self.require(package_id)
        text = str(data.get("text") or "").strip()
        existing = self.conn.execute(
            "SELECT * FROM package_bullet_variant WHERE package_id=? AND bullet_key=? AND tone=? AND lang=?",
            (package_id, data.get("bullet_key"), data.get("tone"), data.get("lang")),
        ).fetchone()
        if existing and conflict == "error":
            raise ApiError(
                "CONFLICT",
                "该要点在这一语气/语言下已有变体，请直接编辑它",
                details={
                    "package_id": package_id,
                    "bullet_key": data.get("bullet_key"),
                    "tone": data.get("tone"),
                    "lang": data.get("lang"),
                    "existing_variant_id": existing["id"],
                },
                hint="用 PUT /packages/{id}/variants/{vid} 修改现有变体",
            )
        now = db_mod.utcnow_iso()
        # 来源必须落库（AC-PKG-14）：LLM 改写的与导入照录的可信度不同，
        # 只靠 llm_generated 0/1 区分不了「手工补写」与「导入原文」。
        origin = data.get("source")
        if origin not in ("imported_verbatim", "llm_rewrite", "manual"):
            origin = "llm_rewrite" if data.get("llm_generated") else "imported_verbatim"
        values = {
            "keywords_json": db_mod.dumps_json(data.get("keywords") or []),
            "metrics_json": db_mod.dumps_json(data.get("metrics") or []),
            "char_len": len(text),
            "verified": 1 if data.get("verified") else 0,
            "quality_score": data.get("quality_score"),
            "llm_generated": 1 if data.get("llm_generated") else 0,
            "source": origin,
            "text": text,
            "updated_at": now,
        }
        if existing:
            variant_id = existing["id"]
            assignments = ", ".join(f"{col} = ?" for col in values)
            with db_mod.transaction(self.conn) as conn:
                conn.execute(
                    f"UPDATE package_bullet_variant SET {assignments} WHERE id = ?",
                    [*values.values(), variant_id],
                )
        else:
            variant_id = db_mod.new_id()
            values.update(
                {
                    "id": variant_id,
                    "package_id": package_id,
                    "bullet_key": data.get("bullet_key"),
                    "tone": data.get("tone"),
                    "lang": data.get("lang"),
                    "created_at": now,
                }
            )
            cols = list(values)
            with db_mod.transaction(self.conn) as conn:
                conn.execute(
                    f"INSERT INTO package_bullet_variant ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                    [values[c] for c in cols],
                )
        self.reindex(package_id)
        row = self.conn.execute("SELECT * FROM package_bullet_variant WHERE id = ?", (variant_id,)).fetchone()
        return self._decode_variant(row)

    def _decode_variant(self, row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            raise ApiError("NOT_FOUND", "bullet 变体不存在")
        data = dict(row)
        data["keywords"] = db_mod.loads_json(data.pop("keywords_json", "[]"), [])
        data["metrics"] = db_mod.loads_json(data.pop("metrics_json", "[]"), [])
        data["verified"] = bool(data.get("verified"))
        data["llm_generated"] = bool(data.get("llm_generated"))
        return data

    def get_variant(self, variant_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM package_bullet_variant WHERE id = ?", (variant_id,)).fetchone()
        if row is None:
            raise ApiError("NOT_FOUND", "bullet 变体不存在", details={"resource": "variant", "id": variant_id})
        return self._decode_variant(row)

    def update_variant(self, variant_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        current = self.get_variant(variant_id)
        values: dict[str, Any] = {}
        if "text" in data and data["text"] is not None:
            text = str(data["text"]).strip()
            values["text"] = text
            values["char_len"] = len(text)
        for key in ("tone", "lang", "quality_score"):
            if key in data:
                values[key] = data[key]
        if "keywords" in data and data["keywords"] is not None:
            values["keywords_json"] = db_mod.dumps_json(data["keywords"])
        if "metrics" in data and data["metrics"] is not None:
            values["metrics_json"] = db_mod.dumps_json(data["metrics"])
        if "verified" in data and data["verified"] is not None:
            values["verified"] = 1 if data["verified"] else 0
        if not values:
            return current
        values["updated_at"] = db_mod.utcnow_iso()
        assignments = ", ".join(f"{col} = ?" for col in values)
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                f"UPDATE package_bullet_variant SET {assignments} WHERE id = ?",
                [*values.values(), variant_id],
            )
        self.reindex(current["package_id"])
        return self.get_variant(variant_id)

    def delete_variant(self, variant_id: str) -> bool:
        current = self.get_variant(variant_id)
        with db_mod.transaction(self.conn) as conn:
            cur = conn.execute("DELETE FROM package_bullet_variant WHERE id = ?", (variant_id,))
        self.reindex(current["package_id"])
        return cur.rowcount > 0

    def variant_ids_for(self, package_id: str, *, lang: str | None = None, verified_only: bool = False) -> list[str]:
        clauses = ["package_id = ?"]
        params: list[Any] = [package_id]
        if lang:
            clauses.append("lang = ?")
            params.append(lang)
        if verified_only:
            clauses.append("verified = 1")
        rows = self.conn.execute(
            f"SELECT id FROM package_bullet_variant WHERE {' AND '.join(clauses)}", params
        ).fetchall()
        return [row[0] for row in rows]

    # -- 检索索引 --------------------------------------------------------------
    def reindex(self, package_id: str) -> None:
        package = self._decode(
            self.conn.execute("SELECT * FROM package WHERE id = ?", (package_id,)).fetchone()
        )
        with db_mod.transaction(self.conn) as conn:
            conn.execute("DELETE FROM package_fts WHERE package_id = ?", (package_id,))
            if package is None or package.get("deleted_at"):
                return
            variants = self.conn.execute(
                "SELECT text FROM package_bullet_variant WHERE package_id = ?", (package_id,)
            ).fetchall()
            body = " ".join(str(row[0]) for row in variants)
            conn.execute(
                "INSERT INTO package_fts(package_id, package_title, org, role, variant_text, tags_text)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    package_id,
                    tokenize_for_index(str(package.get("title") or "")),
                    tokenize_for_index(str(package.get("org") or "")),
                    tokenize_for_index(str(package.get("role") or "")),
                    tokenize_for_index(body),
                    tokenize_for_index(" ".join(package.get("tags") or [])),
                ),
            )

    def rebuild_index(self) -> int:
        rows = self.conn.execute("SELECT id FROM package WHERE deleted_at IS NULL").fetchall()
        for row in rows:
            self.reindex(row[0])
        return len(rows)


# --------------------------------------------------------------------------------------
# Template / Block / Slot
# --------------------------------------------------------------------------------------


class TemplateRepo:
    TABLE = "template"
    COLUMNS: tuple[str, ...] = (
        "name",
        "source_kind",
        "source_file_id",
        "lang",
        "page_limit",
        "layout_json",
        "is_default",
        "target_role_family",
    )

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or db_mod.get_conn()

    def _decode(self, row: sqlite3.Row | None, *, with_blocks: bool = False) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        data["layout"] = db_mod.loads_json(data.pop("layout_json", "{}"), {})
        data["is_default"] = bool(data.get("is_default"))
        if with_blocks:
            data["blocks"] = self.list_blocks(data["id"])
        return data

    def list(self, *, limit: int = 100, lang: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM template WHERE deleted_at IS NULL"
        params: list[Any] = []
        if lang:
            sql += " AND lang = ?"
            params.append(lang)
        sql += " ORDER BY is_default DESC, updated_at DESC, created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._decode(row) for row in rows]  # type: ignore[misc]

    def get(self, template_id: str, *, with_blocks: bool = True) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM template WHERE id = ? AND deleted_at IS NULL", (template_id,)
        ).fetchone()
        return self._decode(row, with_blocks=with_blocks)

    def require(self, template_id: str) -> dict[str, Any]:
        data = self.get(template_id)
        if data is None:
            raise ApiError("NOT_FOUND", "模板不存在", details={"resource": "template", "id": template_id})
        return data

    def default(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM template WHERE is_default = 1 AND deleted_at IS NULL"
        ).fetchone()
        return self._decode(row, with_blocks=True)

    def has_default(self, lang: str | None = None) -> bool:
        sql = "SELECT 1 FROM template WHERE is_default = 1 AND deleted_at IS NULL"
        params: list[Any] = []
        if lang:
            sql += " AND lang = ?"
            params.append(lang)
        return self.conn.execute(sql + " LIMIT 1", params).fetchone() is not None

    def resolved_default(self, lang: str | None = None) -> dict[str, Any] | None:
        """t8 永远有确定的模板可用（captain P1 规则 B）。

        优先 ``is_default=1``；没有就按 ``updated_at DESC`` 兜底（同 lang 优先），
        再不济退回任意语言的最近一条。绝不返回「第一条」这种不确定结果。
        """
        candidates: list[Mapping[str, Any]] = []
        if lang:
            row = self.conn.execute(
                "SELECT * FROM template WHERE is_default = 1 AND deleted_at IS NULL AND lang = ?",
                (lang,),
            ).fetchone()
            if row is not None:
                candidates.append(row)
        if not candidates:
            row = self.conn.execute(
                "SELECT * FROM template WHERE is_default = 1 AND deleted_at IS NULL"
                " ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            if row is not None:
                candidates.append(row)
        if not candidates:
            sql = "SELECT * FROM template WHERE deleted_at IS NULL"
            params: list[Any] = []
            if lang:
                sql += " AND lang = ?"
                params.append(lang)
            sql += " ORDER BY updated_at DESC, created_at DESC LIMIT 1"
            row = self.conn.execute(sql, params).fetchone()
            if row is not None:
                candidates.append(row)
        return self._decode(candidates[0], with_blocks=False) if candidates else None

    def create(self, data: Mapping[str, Any]) -> str:
        template_id = db_mod.new_id()
        now = db_mod.utcnow_iso()
        payload = {
            "id": template_id,
            "name": data["name"],
            "source_kind": data.get("source_kind") or "builtin",
            "source_file_id": data.get("source_file_id"),
            "lang": data.get("lang") or "zh",
            "page_limit": int(data.get("page_limit") or 1),
            "layout_json": db_mod.dumps_json(data.get("layout") or {}),
            "is_default": 1 if data.get("is_default") else 0,
            "target_role_family": data.get("target_role_family"),
            "created_at": now,
            "updated_at": now,
        }
        with db_mod.transaction(self.conn) as conn:
            if payload["is_default"]:
                conn.execute("UPDATE template SET is_default = 0 WHERE is_default = 1")
            else:
                # captain P1 规则 A：全局还没有 default 时，第一个模板自动成为 default，
                # 免得 t8「用户没选模板」时没有确定答案。
                # 注意 is_default 是**全局唯一**（DATA-MODEL I2 + 部分唯一索引），
                # 所以这里只判全局；跨语言的兜底交给 resolved_default(lang=...)。
                existing = conn.execute(
                    "SELECT 1 FROM template WHERE is_default = 1 AND deleted_at IS NULL LIMIT 1"
                ).fetchone()
                if existing is None:
                    payload["is_default"] = 1
            conn.execute(
                f"INSERT INTO template ({', '.join(payload)}) VALUES ({', '.join('?' for _ in payload)})",
                list(payload.values()),
            )
        return template_id

    def set_default(self, template_id: str) -> dict[str, Any]:
        """显式把某个模板设为默认（``is_default`` 全局唯一，先清后置）。"""
        self.require(template_id)
        now = db_mod.utcnow_iso()
        with db_mod.transaction(self.conn) as conn:
            conn.execute("UPDATE template SET is_default = 0 WHERE is_default = 1")
            conn.execute(
                "UPDATE template SET is_default = 1, updated_at = ? WHERE id = ?", (now, template_id)
            )
        return self.require(template_id)

    def require_default(self, lang: str | None = None) -> dict[str, Any]:
        """组装前置：必须**显式**设过默认模板，否则 409 ``NO_DEFAULT_TEMPLATE``。

        绝不静默取「最新一条」——那会让用户以为自己选了模板，实际渲染的是别人的。
        错误里给出 ``candidates[]``，前端可直接让用户点选后 ``POST /templates/{id}/default``。
        """
        explicit = self.default()
        if explicit is not None and (lang is None or explicit["lang"] == lang or explicit["lang"] == "mixed"):
            return explicit
        rows = self.list(limit=50, lang=lang)
        candidates = [
            {"id": row["id"], "name": row["name"], "lang": row["lang"], "updated_at": row["updated_at"]}
            for row in rows
        ]
        raise ApiError(
            "NO_DEFAULT_TEMPLATE",
            "还没有指定默认模板，无法组装简历",
            details={"candidates": candidates, "lang": lang, "count": len(candidates)},
            hint=(
                "先 POST /api/v1/templates/{id}/default 指定一个默认模板"
                if candidates
                else "先导入一份简历生成模板（POST /api/v1/imports → commit）"
            ),
        )

    def update(self, template_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        self.require(template_id)
        payload: dict[str, Any] = {}
        for key in ("name", "lang", "page_limit", "target_role_family", "source_kind", "source_file_id"):
            if key in data:
                payload[key] = data[key]
        if "layout" in data:
            payload["layout_json"] = db_mod.dumps_json(data["layout"] or {})
        if "is_default" in data and data["is_default"] is not None:
            payload["is_default"] = 1 if data["is_default"] else 0
        payload["updated_at"] = db_mod.utcnow_iso()
        with db_mod.transaction(self.conn) as conn:
            if payload.get("is_default"):
                conn.execute("UPDATE template SET is_default = 0 WHERE is_default = 1 AND id <> ?", (template_id,))
            assignments = ", ".join(f"{col} = ?" for col in payload)
            conn.execute(
                f"UPDATE template SET {assignments} WHERE id = ?", [*payload.values(), template_id]
            )
        return self.require(template_id)

    def delete(self, template_id: str) -> bool:
        with db_mod.transaction(self.conn) as conn:
            cur = conn.execute(
                "UPDATE template SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (db_mod.utcnow_iso(), db_mod.utcnow_iso(), template_id),
            )
        return cur.rowcount > 0

    # -- blocks ----------------------------------------------------------------
    def list_blocks(self, template_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM template_block WHERE template_id = ? ORDER BY parent_block_id IS NOT NULL, order_index",
            (template_id,),
        ).fetchall()
        blocks = []
        for row in rows:
            block = dict(row)
            block["style"] = db_mod.loads_json(block.pop("style_json", "{}"), {})
            block["page_break_before"] = bool(block.get("page_break_before"))
            block["repeat_per_package"] = bool(block.get("repeat_per_package"))
            block["slots"] = self.list_slots(block["id"])
            blocks.append(block)
        return blocks

    def add_block(self, template_id: str, data: Mapping[str, Any]) -> str:
        self.require(template_id)
        block_id = db_mod.new_id()
        now = db_mod.utcnow_iso()
        payload = {
            "id": block_id,
            "template_id": template_id,
            "parent_block_id": data.get("parent_block_id"),
            "order_index": int(data.get("order_index") or 0),
            "block_type": data["block_type"],
            "heading": data.get("heading"),
            "bound_package_kind": data.get("bound_package_kind"),
            "style_json": db_mod.dumps_json(data.get("style") or {}),
            "page_break_before": 1 if data.get("page_break_before") else 0,
            "max_bullets": data.get("max_bullets"),
            "static_text": data.get("static_text"),
            "repeat_per_package": 1 if data.get("repeat_per_package", True) else 0,
            "created_at": now,
            "updated_at": now,
        }
        try:
            with db_mod.transaction(self.conn) as conn:
                conn.execute(
                    f"INSERT INTO template_block ({', '.join(payload)}) VALUES ({', '.join('?' for _ in payload)})",
                    list(payload.values()),
                )
        except sqlite3.IntegrityError as exc:
            raise ApiError(
                "TEMPLATE_INVALID",
                "同一父块下的 order_index 不能重复",
                details={"reason": str(exc), "template_id": template_id},
            ) from None
        return block_id

    def delete_block(self, block_id: str) -> bool:
        with db_mod.transaction(self.conn) as conn:
            cur = conn.execute("DELETE FROM template_block WHERE id = ?", (block_id,))
        return cur.rowcount > 0

    # -- slots -----------------------------------------------------------------
    def list_slots(self, block_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM slot WHERE block_id = ? ORDER BY slot_key", (block_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def reorder_block(self, block_id: str, order_index: int) -> bool:
        """只改 ``order_index``（模板拖拽排序用），不碰内容/父子关系。"""
        with db_mod.transaction(self.conn) as conn:
            cur = conn.execute(
                "UPDATE template_block SET order_index = ?, updated_at = ? WHERE id = ?",
                (int(order_index), db_mod.utcnow_iso(), block_id),
            )
        return cur.rowcount > 0

    def add_slot(self, block_id: str, data: Mapping[str, Any]) -> str:
        slot_id = db_mod.new_id()
        now = db_mod.utcnow_iso()
        payload = {
            "id": slot_id,
            "block_id": block_id,
            "slot_key": data["slot_key"],
            "slot_type": data["slot_type"],
            "required": 1 if data.get("required") else 0,
            "bound_field": data.get("bound_field"),
            "default_value": data.get("default_value"),
            "max_chars": data.get("max_chars"),
            "pattern": data.get("pattern"),
            "list_source": data.get("list_source"),
            "created_at": now,
            "updated_at": now,
        }
        try:
            with db_mod.transaction(self.conn) as conn:
                conn.execute(
                    f"INSERT INTO slot ({', '.join(payload)}) VALUES ({', '.join('?' for _ in payload)})",
                    list(payload.values()),
                )
        except sqlite3.IntegrityError as exc:
            raise ApiError(
                "TEMPLATE_INVALID",
                "同一个块内的 slot_key 不能重复",
                details={"reason": str(exc), "block_id": block_id},
            ) from None
        return slot_id

    def missing_required_slots(self, template_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT s.id, s.slot_key, s.slot_type, s.bound_field, b.id AS block_id, b.heading"
            " FROM slot s JOIN template_block b ON b.id = s.block_id"
            " WHERE b.template_id = ? AND s.required = 1 AND s.bound_field IS NULL AND s.default_value IS NULL",
            (template_id,),
        ).fetchall()
        return [dict(row) for row in rows]


# --------------------------------------------------------------------------------------
# JD / Company
# --------------------------------------------------------------------------------------


class JdRepo:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or db_mod.get_conn()

    def create(self, data: Mapping[str, Any]) -> str:
        jd_id = db_mod.new_id()
        now = db_mod.utcnow_iso()
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "INSERT INTO job_description(id, title, company_name, raw_text, attachment_id, source_url, lang,"
                " analysis_status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'none', ?, ?)",
                (
                    jd_id,
                    data.get("title"),
                    data.get("company_name"),
                    data["raw_text"],
                    data.get("attachment_id"),
                    data.get("source_url"),
                    data.get("lang") or "zh",
                    now,
                    now,
                ),
            )
        return jd_id

    def get(self, jd_id: str, *, with_requirements: bool = True) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM job_description WHERE id = ?", (jd_id,)).fetchone()
        if row is None:
            raise ApiError("NOT_FOUND", "JD 不存在", details={"resource": "jd", "id": jd_id})
        data = dict(row)
        data["competitiveness"] = db_mod.loads_json(data.pop("competitiveness_json", "{}"), {})
        if with_requirements:
            data["requirements"] = self.list_requirements(jd_id)
        return data

    def list(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM job_description ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def set_competitiveness(self, jd_id: str, payload: Mapping[str, Any]) -> None:
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "UPDATE job_description SET competitiveness_json = ?, updated_at = ? WHERE id = ?",
                (db_mod.dumps_json(payload or {}), db_mod.utcnow_iso(), jd_id),
            )

    def update_requirement(self, requirement_id: str, patch: Mapping[str, Any]) -> dict[str, Any]:
        """人工改需求：``source`` 一律置 ``manual``（ANL-04：人工修改必须影响后续打分）。"""
        row = self.conn.execute(
            "SELECT * FROM jd_requirement WHERE id = ?", (requirement_id,)
        ).fetchone()
        if row is None:
            raise ApiError(
                "NOT_FOUND", "需求条目不存在", details={"resource": "requirement", "id": requirement_id}
            )
        sets = ["source = 'manual'", "updated_at = ?"]
        params: list[Any] = [db_mod.utcnow_iso()]
        for key in ("skill", "category", "priority", "weight", "evidence_hint", "raw_quote"):
            if key not in patch:
                continue
            value = patch[key]
            if key == "weight" and value is not None:
                value = float(value)
            if key == "skill" and value is not None:
                value = str(value)[:80]
            sets.append(f"{key} = ?")
            params.append(value)
        if "candidate_status" in patch and patch["candidate_status"] is not None:
            sets.append("candidate_status = ?")
            params.append(patch["candidate_status"])
            sets.append("candidate_status_source = 'manual'")
        if patch.get("candidate_status_source") == "auto":
            # 撤销人工标记：值保留，但来源变回自动，下一次重算就会覆盖它。
            sets.append("candidate_status_source = 'llm'")
        params.append(requirement_id)
        with db_mod.transaction(self.conn) as conn:
            conn.execute(f"UPDATE jd_requirement SET {', '.join(sets)} WHERE id = ?", params)
        updated = self.conn.execute("SELECT * FROM jd_requirement WHERE id = ?", (requirement_id,)).fetchone()
        data = dict(updated)
        data["matched_package_ids"] = db_mod.loads_json(data.pop("matched_package_ids_json", "[]"), [])
        data["matched_evidence"] = db_mod.loads_json(data.pop("matched_evidence_json", "[]"), [])
        return data

    def set_local_link(
        self,
        requirement_id: str,
        *,
        candidate_status: str | None = None,
        candidate_status_source: str | None = None,
        matched_package_ids: Iterable[str] | None = None,
        matched_evidence: Iterable[Mapping[str, Any]] | None = None,
        evidence_hint: str | None = None,
        raw_quote: str | None = None,
    ) -> dict[str, Any]:
        """写回**本地匹配**结论（不是人工编辑）。

        与 :meth:`update_requirement` 的区别很重要：那条路会把 ``source`` 置成
        ``manual``（人工改需求要影响打分），而重算历史结论时 ``source`` 应保持
        原样（llm/heuristic）——否则台账上会凭空多出「人工改过」的记录。
        """
        sets = ["updated_at = ?"]
        params: list[Any] = [db_mod.utcnow_iso()]
        if candidate_status is not None:
            sets.append("candidate_status = ?")
            params.append(candidate_status)
        if candidate_status_source is not None:
            sets.append("candidate_status_source = ?")
            params.append(candidate_status_source)
        if matched_package_ids is not None:
            sets.append("matched_package_ids_json = ?")
            params.append(db_mod.dumps_json(list(matched_package_ids)))
        if matched_evidence is not None:
            sets.append("matched_evidence_json = ?")
            params.append(db_mod.dumps_json([dict(item) for item in matched_evidence]))
        if evidence_hint is not None:
            sets.append("evidence_hint = ?")
            params.append(str(evidence_hint)[:200])
        if raw_quote is not None:
            sets.append("raw_quote = ?")
            params.append(str(raw_quote)[:500])
        params.append(requirement_id)
        with db_mod.transaction(self.conn) as conn:
            conn.execute(f"UPDATE jd_requirement SET {', '.join(sets)} WHERE id = ?", params)
        row = self.conn.execute("SELECT * FROM jd_requirement WHERE id = ?", (requirement_id,)).fetchone()
        data = dict(row) if row else {}
        if "matched_package_ids_json" in data:
            data["matched_package_ids"] = db_mod.loads_json(data.pop("matched_package_ids_json"), [])
        return data

    def delete_requirement(self, requirement_id: str) -> str:
        row = self.conn.execute(
            "SELECT jd_id FROM jd_requirement WHERE id = ?", (requirement_id,)
        ).fetchone()
        if row is None:
            raise ApiError(
                "NOT_FOUND", "需求条目不存在", details={"resource": "requirement", "id": requirement_id}
            )
        with db_mod.transaction(self.conn) as conn:
            conn.execute("DELETE FROM jd_requirement WHERE id = ?", (requirement_id,))
        return str(row["jd_id"])

    def update_status(self, jd_id: str, status: str, method: str | None = None) -> None:
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "UPDATE job_description SET analysis_status = ?, analysis_method = COALESCE(?, analysis_method), updated_at = ? WHERE id = ?",
                (status, method, db_mod.utcnow_iso(), jd_id),
            )

    def list_requirements(self, jd_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM jd_requirement WHERE jd_id = ? ORDER BY CASE priority WHEN 'must' THEN 0 WHEN 'should' THEN 1 ELSE 2 END, skill",
            (jd_id,),
        ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["matched_package_ids"] = db_mod.loads_json(data.pop("matched_package_ids_json", "[]"), [])
            data["matched_evidence"] = db_mod.loads_json(data.pop("matched_evidence_json", "[]"), [])
            data.setdefault("candidate_status", None)
            result.append(data)
        return result

    def replace_requirements(self, jd_id: str, requirements: Iterable[Mapping[str, Any]], *, method: str) -> int:
        """原子替换某 JD 的全部要求（幂等：先清后插，避免 UNIQUE 冲突）。"""
        now = db_mod.utcnow_iso()
        count = 0
        # 人工改判要压过重算（§6.2.5 / I23）：先按 (skill, category) 记住 manual 行，
        # 重算结果写到同一 key 时必须保留人工的 candidate_status。撤销只能显式给
        # `candidate_status_source="auto"`（那条 PATCH 会把它变回非 manual，下次重算才生效）。
        manual_rows: dict[tuple[str, str], tuple[str, str]] = {}
        for row in self.conn.execute(
            "SELECT lower(skill) AS k, category, candidate_status, candidate_status_source"
            " FROM jd_requirement WHERE jd_id = ? AND candidate_status_source = 'manual'",
            (jd_id,),
        ):
            manual_rows[(row["k"], row["category"])] = (row["candidate_status"], "manual")

        with db_mod.transaction(self.conn) as conn:
            conn.execute("DELETE FROM jd_requirement WHERE jd_id = ?", (jd_id,))
            for req in requirements:
                conn.execute(
                    "INSERT OR REPLACE INTO jd_requirement(id, jd_id, skill, category, priority, weight,"
                    " evidence_hint, raw_quote, source, matched_package_ids_json, candidate_status,"
                    " candidate_status_source, matched_evidence_json, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        db_mod.new_id(),
                        jd_id,
                        str(req.get("skill"))[:80],
                        req.get("category") or "hard",
                        req.get("priority") or "should",
                        float(req.get("weight") if req.get("weight") is not None else 0.5),
                        (str(req.get("evidence_hint"))[:200] if req.get("evidence_hint") else None),
                        (str(req.get("raw_quote"))[:300] if req.get("raw_quote") else None),
                        req.get("source") or method,
                        db_mod.dumps_json(req.get("matched_package_ids") or []),
                        manual_rows.get(
                            (str(req.get("skill") or "").lower(), str(req.get("category") or "hard")),
                            (
                                req.get("candidate_status"),
                                req.get("candidate_status_source") or req.get("source") or method,
                            ),
                        )[0],
                        manual_rows.get(
                            (str(req.get("skill") or "").lower(), str(req.get("category") or "hard")),
                            (
                                req.get("candidate_status"),
                                req.get("candidate_status_source") or req.get("source") or method,
                            ),
                        )[1],
                        db_mod.dumps_json([dict(item) for item in (req.get("matched_evidence") or [])]),
                        now,
                        now,
                    ),
                )
                count += 1
            conn.execute(
                "UPDATE job_description SET analysis_status='done', analysis_method=?, updated_at=? WHERE id=?",
                (method, now, jd_id),
            )
        return count


class CompanyRepo:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or db_mod.get_conn()

    JSON_COLUMNS = (
        "culture_signals_json",
        "hiring_preferences_json",
        "interview_focus_json",
        "keywords_json",
        "sources_json",
        "school_preference_json",
    )

    def _decode(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        data["culture_signals"] = db_mod.loads_json(data.pop("culture_signals_json", "[]"), [])
        data["hiring_preferences"] = db_mod.loads_json(data.pop("hiring_preferences_json", "[]"), [])
        data["interview_focus"] = db_mod.loads_json(data.pop("interview_focus_json", "[]"), [])
        data["keywords"] = db_mod.loads_json(data.pop("keywords_json", "[]"), [])
        data["sources"] = db_mod.loads_json(data.pop("sources_json", "[]"), [])
        data["school_preference"] = db_mod.loads_json(data.pop("school_preference_json", "{}"), {})
        return data

    def get(self, company_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM company_profile WHERE id = ?", (company_id,)).fetchone()
        data = self._decode(row)
        if data is None:
            raise ApiError("NOT_FOUND", "公司档案不存在", details={"resource": "company_profile", "id": company_id})
        return data

    def list(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM company_profile ORDER BY updated_at DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
        return [self._decode(row) or {} for row in rows]

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM company_profile").fetchone()
        return int(row[0]) if row else 0

    def delete(self, company_id: str) -> None:
        self.get(company_id)  # 不存在 → 404
        with db_mod.transaction(self.conn) as conn:
            conn.execute("DELETE FROM company_profile WHERE id = ?", (company_id,))

    def find_by_name(self, company_name: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM company_profile WHERE company_name = ?", (company_name.strip(),)
        ).fetchone()
        return self._decode(row)

    def upsert(self, company_name: str, data: Mapping[str, Any], *, method: str = "manual") -> dict[str, Any]:
        existing = self.find_by_name(company_name)
        now = db_mod.utcnow_iso()
        payload: dict[str, Any] = {
            "company_name": company_name.strip(),
            "industry": data.get("industry"),
            "company_stage": data.get("company_stage"),
            "size_hint": data.get("size_hint"),
            "culture_signals_json": db_mod.dumps_json(data.get("culture_signals") or []),
            "hiring_preferences_json": db_mod.dumps_json(data.get("hiring_preferences") or []),
            "interview_focus_json": db_mod.dumps_json(data.get("interview_focus") or []),
            "tone": data.get("tone"),
            "keywords_json": db_mod.dumps_json(data.get("keywords") or []),
            "sources_json": db_mod.dumps_json(data.get("sources") or []),
            "school_preference_json": db_mod.dumps_json(data.get("school_preference") or {}),
            "website": data.get("website"),
            "confidence": data.get("confidence"),
            "method": data.get("method") or method,
            "last_analyzed_at": now,
            "expires_at": data.get("expires_at"),
            "updated_at": now,
        }
        if existing:
            assignments = ", ".join(f"{col} = ?" for col in payload)
            with db_mod.transaction(self.conn) as conn:
                conn.execute(
                    f"UPDATE company_profile SET {assignments} WHERE id = ?",
                    [*payload.values(), existing["id"]],
                )
            return self.get(existing["id"])
        company_id = db_mod.new_id()
        payload.update({"id": company_id, "created_at": now})
        cols = list(payload)
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                f"INSERT INTO company_profile ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                [payload[c] for c in cols],
            )
        return self.get(company_id)

    def patch(self, company_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        current = self.get(company_id)
        payload: dict[str, Any] = {"updated_at": db_mod.utcnow_iso()}
        for key in ("industry", "company_stage", "size_hint", "tone", "confidence", "method", "website"):
            if key in data:
                payload[key] = data[key]
        for key in ("culture_signals", "hiring_preferences", "interview_focus", "keywords"):
            if key in data and data[key] is not None:
                payload[f"{key}_json"] = db_mod.dumps_json(data[key])
        if "school_preference" in data and data["school_preference"] is not None:
            payload["school_preference_json"] = db_mod.dumps_json(data["school_preference"])
        assignments = ", ".join(f"{col} = ?" for col in payload)
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                f"UPDATE company_profile SET {assignments} WHERE id = ?",
                [*payload.values(), company_id],
            )
        return self.get(company_id)


# --------------------------------------------------------------------------------------
# Build / Selection / Artifact
# --------------------------------------------------------------------------------------


class BuildRepo:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or db_mod.get_conn()

    JSON_COLUMNS = ("naming_overrides_json", "field_values_json", "sections_order_json", "warnings_json")

    def _decode(self, row: sqlite3.Row | None, *, with_selections: bool = False) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        data["naming_overrides"] = db_mod.loads_json(data.pop("naming_overrides_json", "{}"), {})
        data["field_values"] = db_mod.loads_json(data.pop("field_values_json", "{}"), {})
        data["sections_order"] = db_mod.loads_json(data.pop("sections_order_json", "[]"), [])
        data["warnings"] = db_mod.loads_json(data.pop("warnings_json", "[]"), [])
        if with_selections:
            data["selections"] = self.list_selections(data["id"])
            data["artifacts"] = self.list_artifacts(data["id"])
        return data

    def create(self, data: Mapping[str, Any]) -> str:
        build_id = db_mod.new_id()
        now = db_mod.utcnow_iso()
        payload = {
            "id": build_id,
            "name": data["name"],
            "template_id": data["template_id"],
            "jd_id": data.get("jd_id"),
            "company_profile_id": data.get("company_profile_id"),
            "position": data.get("position"),
            "company": data.get("company"),
            "lang": data.get("lang") or "zh",
            "status": "draft",
            "naming_pattern": data.get("naming_pattern") or "{position}-{name}-{school}",
            "naming_overrides_json": db_mod.dumps_json(data.get("naming_overrides") or {}),
            "field_values_json": db_mod.dumps_json(data.get("field_values") or {}),
            "sections_order_json": db_mod.dumps_json(data.get("sections_order") or []),
            "warnings_json": "[]",
            "created_at": now,
            "updated_at": now,
        }
        cols = list(payload)
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                f"INSERT INTO resume_build ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                [payload[c] for c in cols],
            )
        return build_id

    def get(self, build_id: str, *, with_selections: bool = True) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM resume_build WHERE id = ?", (build_id,)).fetchone()
        data = self._decode(row, with_selections=with_selections)
        if data is None:
            raise ApiError("NOT_FOUND", "简历构建不存在", details={"resource": "build", "id": build_id})
        return data

    def list(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
        template_id: str | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        """默认只看未归档的构建。

        「归档」是一条用户可见的语义：导出记录积多了要能从列表里收起来，但历史本身
        不许消失（对应 schema v12 的 ``archived_at``）。真删得走脚本的 ``--hard-delete``。
        """
        sql = "SELECT * FROM resume_build"
        clauses: list[str] = []
        params: list[Any] = []
        if not include_archived:
            clauses.append("archived_at IS NULL")
        if status:
            clauses.append("status = ?")
            params.append(status)
        if template_id:
            clauses.append("template_id = ?")
            params.append(template_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [self._decode(row) for row in rows]  # type: ignore[misc]

    def set_archived(self, build_id: str, *, archived: bool = True) -> dict[str, Any]:
        """归档 / 取消归档一条构建；返回更新后的行（不存在则 404）。"""
        build = self.get(build_id, with_selections=False)
        if build is None:
            raise ApiError("NOT_FOUND", "构建不存在", details={"build_id": build_id})
        stamp = db_mod.utcnow_iso() if archived else None
        with db_mod.transaction(self.conn):
            self.conn.execute(
                "UPDATE resume_build SET archived_at = ?, updated_at = ? WHERE id = ?",
                (stamp, db_mod.utcnow_iso(), build_id),
            )
        return self.get(build_id, with_selections=False) or {}

    def update(self, build_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        self.get(build_id, with_selections=False)
        payload: dict[str, Any] = {"updated_at": db_mod.utcnow_iso()}
        for key in ("name", "template_id", "jd_id", "company_profile_id", "position", "company", "lang", "status", "naming_pattern", "est_pages"):
            if key in data:
                payload[key] = data[key]
        for key, column in (
            ("naming_overrides", "naming_overrides_json"),
            ("field_values", "field_values_json"),
            ("sections_order", "sections_order_json"),
            ("warnings", "warnings_json"),
        ):
            if key in data and data[key] is not None:
                payload[column] = db_mod.dumps_json(data[key])
        assignments = ", ".join(f"{col} = ?" for col in payload)
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                f"UPDATE resume_build SET {assignments} WHERE id = ?", [*payload.values(), build_id]
            )
        return self.get(build_id)

    def delete(self, build_id: str) -> bool:
        with db_mod.transaction(self.conn) as conn:
            cur = conn.execute("DELETE FROM resume_build WHERE id = ?", (build_id,))
        return cur.rowcount > 0

    # -- selections ------------------------------------------------------------
    def list_selections(self, build_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM build_selection WHERE build_id = ? ORDER BY order_index", (build_id,)
        ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["variant_ids"] = db_mod.loads_json(data.pop("variant_ids_json", "[]"), [])
            data["overrides"] = db_mod.loads_json(data.pop("overrides_json", "{}"), {})
            data["snapshot"] = db_mod.loads_json(data.pop("snapshot_json", "{}"), {})
            result.append(data)
        return result

    def add_selection(self, build_id: str, data: Mapping[str, Any]) -> str:
        self.get(build_id, with_selections=False)
        selection_id = db_mod.new_id()
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "INSERT INTO build_selection(id, build_id, package_id, variant_ids_json, order_index, overrides_json, snapshot_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(build_id, package_id) DO UPDATE SET"
                " variant_ids_json=excluded.variant_ids_json, order_index=excluded.order_index,"
                " overrides_json=excluded.overrides_json, snapshot_json=excluded.snapshot_json",
                (
                    selection_id,
                    build_id,
                    data["package_id"],
                    db_mod.dumps_json(data.get("variant_ids") or []),
                    int(data.get("order_index") or 0),
                    db_mod.dumps_json(data.get("overrides") or {}),
                    db_mod.dumps_json(data.get("snapshot") or {}),
                    db_mod.utcnow_iso(),
                ),
            )
        return selection_id

    def update_selection_snapshot(self, build_id: str, package_id: str, snapshot: Mapping[str, Any]) -> None:
        """把「这条经历本次渲染成什么」存进 build_selection.snapshot_json（可追溯）。"""
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "UPDATE build_selection SET snapshot_json = ? WHERE build_id = ? AND package_id = ?",
                (db_mod.dumps_json(dict(snapshot)), build_id, package_id),
            )

    def clear_selections(self, build_id: str) -> None:
        with db_mod.transaction(self.conn) as conn:
            conn.execute("DELETE FROM build_selection WHERE build_id = ?", (build_id,))

    # -- artifacts -------------------------------------------------------------
    def add_artifact(self, build_id: str, data: Mapping[str, Any]) -> str:
        artifact_id = db_mod.new_id()
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "INSERT INTO build_artifact(id, build_id, format, engine, filename, rel_path, bytes, sha256,"
                " text_verified, text_diff_json, warnings_json, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact_id,
                    build_id,
                    data["format"],
                    data["engine"],
                    data["filename"],
                    data["rel_path"],
                    int(data["bytes"]),
                    data["sha256"],
                    None if data.get("text_verified") is None else (1 if data.get("text_verified") else 0),
                    db_mod.dumps_json(data.get("text_diff") or []),
                    db_mod.dumps_json(data.get("warnings") or []),
                    db_mod.utcnow_iso(),
                ),
            )
        return artifact_id

    def list_artifacts(self, build_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM build_artifact WHERE build_id = ? ORDER BY created_at DESC", (build_id,)
        ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["text_diff"] = db_mod.loads_json(data.pop("text_diff_json", "[]"), [])
            data["warnings"] = db_mod.loads_json(data.pop("warnings_json", "[]"), [])
            result.append(data)
        return result

    def get_artifact(self, artifact_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM build_artifact WHERE id = ?", (artifact_id,)).fetchone()
        if row is None:
            raise ApiError("NOT_FOUND", "导出产物不存在", details={"resource": "artifact", "id": artifact_id})
        data = dict(row)
        data["text_diff"] = db_mod.loads_json(data.pop("text_diff_json", "[]"), [])
        data["warnings"] = db_mod.loads_json(data.pop("warnings_json", "[]"), [])
        return data


# --------------------------------------------------------------------------------------
# ImportJob
# --------------------------------------------------------------------------------------


class ImportRepo:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or db_mod.get_conn()

    def create(self, attachment_id: str, parser: str) -> str:
        import_id = db_mod.new_id()
        now = db_mod.utcnow_iso()
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "INSERT INTO import_job(id, attachment_id, status, parser, created_at, updated_at)"
                " VALUES (?, ?, 'queued', ?, ?, ?)",
                (import_id, attachment_id, parser, now, now),
            )
        return import_id

    def list(
        self,
        *,
        status: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM import_job"
        clauses: list[str] = []
        params: list[Any] = []
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    OPEN_STATUSES: tuple[str, ...] = ("queued", "parsing", "draft")

    def find_open_by_source_sha(self, sha256: str) -> str | None:
        """同一份源文件（内容寻址 sha256）已有未提交草稿 → 直接复用，避免重复存 PII。"""
        if not sha256:
            return None
        placeholders = ", ".join("?" for _ in self.OPEN_STATUSES)
        row = self.conn.execute(
            "SELECT j.id FROM import_job j JOIN attachment a ON a.id = j.attachment_id"
            f" WHERE a.sha256 = ? AND j.status IN ({placeholders})"
            " ORDER BY j.created_at DESC LIMIT 1",
            (sha256, *self.OPEN_STATUSES),
        ).fetchone()
        return str(row[0]) if row is not None else None

    def prune_drafts(
        self, *, max_keep: int = 20, ttl_days: int = 7, keep: Iterable[str] = ()
    ) -> list[str]:
        """清理未提交草稿：超过 ``max_keep`` 的最新保留，其余删除；另删超过 ``ttl_days`` 的。

        返回被删的 import_id 列表（调用方据此给一条 ``IMPORT_DRAFT_PRUNED`` 提示）。
        """
        placeholders = ", ".join("?" for _ in self.OPEN_STATUSES)
        rows = self.conn.execute(
            f"SELECT id, created_at FROM import_job WHERE status IN ({placeholders})"
            " ORDER BY created_at DESC, id DESC",  # created_at 只到秒，用时间有序 id 兜底稳定
            self.OPEN_STATUSES,
        ).fetchall()
        protected = set(keep)
        if not rows:
            return []
        cutoff = None
        if ttl_days > 0:
            cutoff = db_mod.parse_iso(db_mod.utcnow_iso())
        stale: list[str] = []
        kept = 0
        for row in rows:
            if str(row["id"]) in protected:
                kept += 1
                continue
            too_many = kept >= max_keep
            too_old = False
            if cutoff is not None and row["created_at"]:
                try:
                    too_old = (cutoff - db_mod.parse_iso(str(row["created_at"]))).days >= ttl_days
                except (TypeError, ValueError):
                    too_old = False
            if too_many or too_old:
                stale.append(str(row["id"]))
            else:
                kept += 1
        if not stale:
            return []
        chunk = ", ".join("?" for _ in stale)
        with db_mod.transaction(self.conn) as conn:
            conn.execute(f"DELETE FROM import_job WHERE id IN ({chunk})", stale)
        return stale

    def soft_delete(self, import_id: str) -> dict[str, Any]:
        """软删（可 restore）：用户随时能删掉导入历史，但不物理销毁真实简历副本。"""
        self.get(import_id)
        now = db_mod.utcnow_iso()
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "UPDATE import_job SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                (now, now, import_id),
            )
            # 连带软删派生包，**用同一个时间戳**标记这一批：恢复时据此精确复原，
            # 不会把用户自己删掉的包顺手复活。老数据（v8 之前无 source_import_job_id）
            # 只能靠 tags 兜底，留给 cascade 辅助函数处理。
            rows = conn.execute(
                "UPDATE package SET deleted_at = ?, updated_at = ? "
                "WHERE source_import_job_id = ? AND deleted_at IS NULL RETURNING id",
                (now, now, import_id),
            ).fetchall()
        row = self.get(import_id)
        # 把本次连带软删的包 id 一并交给调用方：删除接口要如实回报删了几条，
        # 而列表查询已经看不到它们了（不能靠「再查一次」来数）。
        row["cascaded_package_ids"] = [str(item[0]) for item in rows]
        return row

    def restore(self, import_id: str) -> dict[str, Any]:
        """恢复导入历史：连同本次删除批次连带软删的派生包一起复原。

        只复原 ``deleted_at`` 等于本次导入行删除时间戳的包——用户手动删掉的
        （时间戳不同）不会被顺手复活，删除与恢复因此是对称的。
        """
        row = self.get(import_id)
        batch = row.get("deleted_at")
        with db_mod.transaction(self.conn) as conn:
            if batch:
                conn.execute(
                    "UPDATE package SET deleted_at = NULL, updated_at = ? "
                    "WHERE source_import_job_id = ? AND deleted_at = ?",
                    (db_mod.utcnow_iso(), import_id, batch),
                )
            conn.execute(
                "UPDATE import_job SET deleted_at = NULL, updated_at = ? WHERE id = ?",
                (db_mod.utcnow_iso(), import_id),
            )
        return self.get(import_id)

    def get(self, import_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM import_job WHERE id = ?", (import_id,)).fetchone()
        if row is None:
            raise ApiError("NOT_FOUND", "导入任务不存在", details={"resource": "import", "id": import_id})
        data = dict(row)
        data["draft"] = db_mod.loads_json(data.pop("draft_json", "{}"), {})
        data["stats"] = db_mod.loads_json(data.pop("stats_json", "{}"), {})
        data["warnings"] = db_mod.loads_json(data.pop("warnings_json", "[]"), [])
        return data

    def update(
        self,
        import_id: str,
        *,
        status: str | None = None,
        draft: Any | None = None,
        stats: Any | None = None,
        warnings: Any | None = None,
        template_id: str | None = None,
    ) -> None:
        sets = ["updated_at = ?"]
        params: list[Any] = [db_mod.utcnow_iso()]
        if status is not None:
            sets.append("status = ?")
            params.append(status)
        if draft is not None:
            sets.append("draft_json = ?")
            params.append(db_mod.dumps_json(draft))
        if stats is not None:
            sets.append("stats_json = ?")
            params.append(db_mod.dumps_json(stats))
        if warnings is not None:
            sets.append("warnings_json = ?")
            params.append(db_mod.dumps_json(warnings))
        if template_id is not None:
            sets.append("result_template_id = ?")
            params.append(template_id)
        params.append(import_id)
        with db_mod.transaction(self.conn) as conn:
            conn.execute(f"UPDATE import_job SET {', '.join(sets)} WHERE id = ?", params)


# --------------------------------------------------------------------------------------
# LLM 预览（consent 状态机）与调用审计
# --------------------------------------------------------------------------------------


class PreviewRepo:
    """I5：pending → consumed/expired/rejected 不可逆；用条件 UPDATE 判竞态。"""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or db_mod.get_conn()

    def create(self, data: Mapping[str, Any]) -> str:
        preview_id = db_mod.new_id()
        now = db_mod.utcnow_iso()
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "INSERT INTO llm_preview(id, purpose, provider, model, endpoint_host, payload_json,"
                " payload_sha256, field_manifest_json, est_tokens, redactions_json, status, expires_at, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
                (
                    preview_id,
                    data["purpose"],
                    data["provider"],
                    data["model"],
                    data["endpoint_host"],
                    db_mod.dumps_json(data["payload"]),
                    data["payload_sha256"],
                    db_mod.dumps_json(data["fields"]),
                    int(data.get("est_tokens") or 0),
                    db_mod.dumps_json(data.get("redactions") or []),
                    data["expires_at"],
                    now,
                ),
            )
        return preview_id

    def get(self, preview_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM llm_preview WHERE id = ?", (preview_id,)).fetchone()
        if row is None:
            raise ApiError("NOT_FOUND", "预览不存在", details={"resource": "llm_preview", "id": preview_id})
        data = dict(row)
        data["payload"] = db_mod.loads_json(data.pop("payload_json", "{}"), {})
        data["fields"] = db_mod.loads_json(data.pop("field_manifest_json", "[]"), [])
        data["redactions"] = db_mod.loads_json(data.pop("redactions_json", "[]"), [])
        return data

    def consume(self, preview_id: str) -> bool:
        """原子消费：只有 pending 能被置为 consumed；返回是否抢到。"""
        with db_mod.transaction(self.conn) as conn:
            cur = conn.execute(
                "UPDATE llm_preview SET status='consumed', consumed_at=? WHERE id=? AND status='pending'",
                (db_mod.utcnow_iso(), preview_id),
            )
        return cur.rowcount == 1

    def reject(self, preview_id: str) -> bool:
        with db_mod.transaction(self.conn) as conn:
            cur = conn.execute(
                "UPDATE llm_preview SET status='rejected' WHERE id=? AND status='pending'", (preview_id,)
            )
        return cur.rowcount == 1

    def expire_stale(self, now_iso: str | None = None) -> int:
        with db_mod.transaction(self.conn) as conn:
            cur = conn.execute(
                "UPDATE llm_preview SET status='expired' WHERE status='pending' AND expires_at < ?",
                (now_iso or db_mod.utcnow_iso(),),
            )
        return cur.rowcount


class LlmLogRepo:
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or db_mod.get_conn()

    def append(
        self,
        *,
        preview_id: str | None,
        provider: str,
        model: str,
        endpoint_host: str,
        field_names: Sequence[str],
        payload_bytes: int,
        est_tokens: int,
        http_status: int | None,
        latency_ms: int | None,
        ok: bool,
        error_code: str | None = None,
        purpose: str | None = None,
    ) -> str:
        log_id = db_mod.new_id()
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "INSERT INTO llm_call_log(id, preview_id, provider, model, endpoint_host, field_names_json,"
                " payload_bytes, est_tokens, http_status, latency_ms, ok, error_code, purpose, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    log_id,
                    preview_id,
                    provider,
                    model,
                    endpoint_host,
                    db_mod.dumps_json(list(field_names)),
                    payload_bytes,
                    est_tokens,
                    http_status,
                    latency_ms,
                    1 if ok else 0,
                    error_code,
                    purpose,
                    db_mod.utcnow_iso(),
                ),
            )
        return log_id

    def purposes(self) -> list[dict[str, Any]]:
        """按 purpose 汇总调用次数（给「分析档是否真走 reasoner」这类问题取证）。"""
        rows = self.conn.execute(
            "SELECT purpose, model, COUNT(*) AS calls FROM llm_call_log"
            " GROUP BY purpose, model ORDER BY calls DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def list(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM llm_call_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["field_names"] = db_mod.loads_json(data.pop("field_names_json", "[]"), [])
            result.append(data)
        return result
