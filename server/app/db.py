"""SQLite 数据层：路径、连接、迁移、事务、ID 生成。

设计要点（ARCHITECTURE §3 / DATA-MODEL「实现约定」）：
* 每线程一个连接（``threading.local``），``check_same_thread=False``，WAL + busy_timeout=5000。
* 所有写操作走 ``BEGIN IMMEDIATE``（避免 SQLITE_BUSY 升级死锁），读操作自动提交。
* ``DATA_DIR`` 必须解析到项目 ``data/`` 目录内，否则启动即失败（防误写到项目外）。
* 迁移脚本 ``app/schema.sql`` 用 ``-- @version N`` 分段，按 schema_migration 表顺序补齐，幂等。
* ID 统一 UUIDv7（时间前缀 + 随机），TEXT 主键，便于按创建时间排序。
"""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from . import config as config_mod

# --------------------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------------------

#: data/ 下允许存在的子目录（首次启动自动创建）
DATA_SUBDIRS = ("files", "exports", "imports", "logs", "tmp", "profile", "runtime")


def project_root() -> Path:
    return config_mod.PROJECT_ROOT


def resolve_data_root(raw: str | os.PathLike[str] | None = None) -> Path:
    """解析 DATA_DIR 并断言其落在项目 data/ 内（接受 str 或 Path，勿假设类型）。"""
    text = os.fspath(raw) if raw is not None else os.environ.get("DATA_DIR") or "./data"
    text = str(text).strip() or "./data"
    candidate = Path(os.path.expanduser(text))
    if not candidate.is_absolute():
        candidate = config_mod.PROJECT_ROOT / candidate
    resolved = candidate.resolve()
    allowed = (config_mod.PROJECT_ROOT / "data").resolve()
    if not (resolved == allowed or resolved.is_relative_to(allowed)):
        raise RuntimeError(
            f"DATA_DIR 必须位于 {allowed} 之内，实际解析为 {resolved}（拒绝在项目外落盘）"
        )
    return resolved


class Paths:
    """一次解析、处处复用的一组本地路径。"""

    __slots__ = ("root", "db", "files", "exports", "imports", "logs", "tmp")

    def __init__(self, data_root: Path) -> None:
        self.root = data_root
        self.db = data_root / "app.db"
        self.files = data_root / "files"
        self.exports = data_root / "exports"
        self.imports = data_root / "imports"
        self.logs = data_root / "logs"
        self.tmp = data_root / "tmp"

    def ensure(self) -> "Paths":
        self.root.mkdir(parents=True, exist_ok=True)
        for sub in DATA_SUBDIRS:
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        return self

    def as_dict(self) -> dict[str, str]:
        return {
            "data_root": str(self.root),
            "db": str(self.db),
            "files": str(self.files),
            "exports": str(self.exports),
            "imports": str(self.imports),
            "logs": str(self.logs),
        }

    def assert_within(self, path: Path, *, base: Path | None = None) -> Path:
        """把任意路径解析后断言在 data/（或指定子目录）内，越界抛 ApiError(PATH_ESCAPE)。"""
        from .errors import ApiError

        base = (base or self.root).resolve()
        resolved = Path(path).expanduser()
        if not resolved.is_absolute():
            resolved = base / resolved
        resolved = resolved.resolve()
        if not (resolved == base or resolved.is_relative_to(base)):
            raise ApiError("PATH_ESCAPE", details={"base": str(base), "requested": str(resolved)})
        return resolved


_paths_lock = threading.Lock()
_paths: Paths | None = None


def get_paths(config: config_mod.Config | None = None) -> Paths:
    global _paths
    with _paths_lock:
        if _paths is None:
            cfg = config or config_mod.get_config()
            _paths = Paths(resolve_data_root(cfg.data_dir)).ensure()
        return _paths


def reset_paths_for_tests(data_root: str | os.PathLike[str] | None = None) -> Paths:
    """测试/脚本用：强制重新解析 data 根。

    **必须顺带刷新配置单例** —— ``config_mod`` 是进程级单例，改了 ``DATA_DIR`` 之后
    不重新 ``load_config()``，``get_config().data_dir`` 还是旧值，路径会指回真实
    ``data/``（2026-10-23 实测：一套测试把 91 条导入草稿写进了真实库）。
    """
    global _paths, _GENERATION
    with _paths_lock:
        _paths = None
        # 每个线程（含 jobrun 的 worker 线程）缓存了自己的连接；换了数据根之后
        # 旧连接还指着上一个库文件（可能是已删除的临时库）→ 用代数让它们自觉重连。
        _GENERATION += 1
        if data_root is not None:
            os.environ["DATA_DIR"] = str(data_root)
        config_mod.set_config(config_mod.load_config())
        cfg = config_mod.get_config()
        _paths = Paths(resolve_data_root(cfg.data_dir)).ensure()
        return _paths


# --------------------------------------------------------------------------------------
# 迁移脚本解析
# --------------------------------------------------------------------------------------

#: 允许 ``-- @version 7：说明文字`` 这种带注解的写法。
#: 早前只认「行尾即结束」，结果 ``-- @version 6：…`` 被静默跳过 ——
#: 迁移「看不见」比迁移报错危险得多，所以这里故意放宽并在测试里锁住。
_VERSION_RE = re.compile(r"^--\s*@version\s+(\d+)\b.*$", re.MULTILINE)


def load_migrations(schema_path: Path | None = None) -> list[tuple[int, str]]:
    """把 schema.sql 切成 [(version, sql), ...]，按 version 升序。"""
    path = schema_path or config_mod.SCHEMA_PATH
    sql_all = path.read_text(encoding="utf-8")
    matches = list(_VERSION_RE.finditer(sql_all))
    if not matches:
        raise RuntimeError(f"{path} 缺少 '-- @version N' 分段标记")
    segments: list[tuple[int, str]] = []
    for idx, match in enumerate(matches):
        version = int(match.group(1))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(sql_all)
        body = sql_all[start:end].strip()
        if body:
            segments.append((version, body))
    if len({v for v, _ in segments}) != len(segments):
        raise RuntimeError(f"{path} 存在重复的 @version 编号")
    return sorted(segments, key=lambda item: item[0])


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migration'"
    ).fetchone()
    if not exists:
        return set()
    return {int(row[0]) for row in conn.execute("SELECT version FROM schema_migration")}


def migrate(conn: sqlite3.Connection, *, schema_path: Path | None = None) -> list[int]:
    """补齐未应用的迁移段，返回本次新应用的版本号列表。"""
    applied = _applied_versions(conn)
    newly: list[int] = []
    for version, sql in load_migrations(schema_path):
        if version in applied:
            continue
        conn.executescript(f"BEGIN IMMEDIATE;\n{sql}\nCOMMIT;")
        conn.execute(
            "INSERT OR REPLACE INTO schema_migration(version, applied_at) VALUES (?, ?)",
            (version, utcnow_iso()),
        )
        conn.commit()
        newly.append(version)
    return newly


# --------------------------------------------------------------------------------------
# 连接管理
# --------------------------------------------------------------------------------------

_local = threading.local()

#: 数据根代数：``reset_paths_for_tests()`` 会 +1，各线程据此丢弃旧连接。
_GENERATION = 0


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(
        str(db_path),
        timeout=5.0,
        isolation_level=None,  # 自己控制事务边界
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def get_conn(config: config_mod.Config | None = None) -> sqlite3.Connection:
    """当前线程的连接（懒创建 + 自动迁移一次）。"""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        if getattr(_local, "generation", -1) == _GENERATION:
            return conn
        # 数据根换过了：本线程的旧连接指向旧库，必须丢弃
        try:
            conn.close()
        except sqlite3.Error:  # pragma: no cover - 关闭失败不影响新建
            pass
        _local.conn = None
    paths = get_paths(config)
    conn = _connect(paths.db)
    migrate(conn)
    _local.conn = conn
    _local.generation = _GENERATION
    return conn


def close_conn() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        finally:
            _local.conn = None


@contextmanager
def transaction(conn: sqlite3.Connection | None = None) -> Iterator[sqlite3.Connection]:
    """写事务：BEGIN IMMEDIATE ... COMMIT / ROLLBACK。支持嵌套（内层用 SAVEPOINT）。"""
    conn = conn or get_conn()
    depth = getattr(_local, "tx_depth", 0)
    savepoint = f"sp_{depth}"
    if depth == 0:
        conn.execute("BEGIN IMMEDIATE")
    else:
        conn.execute(f"SAVEPOINT {savepoint}")
    _local.tx_depth = depth + 1
    try:
        yield conn
    except BaseException:
        _local.tx_depth = depth
        if depth == 0:
            conn.execute("ROLLBACK")
        else:
            conn.execute(f"ROLLBACK TO {savepoint}")
            conn.execute(f"RELEASE {savepoint}")
        raise
    else:
        _local.tx_depth = depth
        if depth == 0:
            conn.execute("COMMIT")
        else:
            conn.execute(f"RELEASE {savepoint}")


@contextmanager
def reading(conn: sqlite3.Connection | None = None) -> Iterator[sqlite3.Connection]:
    yield conn or get_conn()


# --------------------------------------------------------------------------------------
# 通用工具
# --------------------------------------------------------------------------------------


def utcnow_iso() -> str:
    """本地时区 ISO-8601（带偏移）。DB 内所有时间列统一用这个格式。"""
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.astimezone()
    return value.replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def seconds_left(expires_at: str | None) -> int:
    dt = parse_iso(expires_at)
    if dt is None:
        return 0
    return max(0, int((dt - datetime.now().astimezone()).total_seconds()))


_seq_lock = threading.Lock()
_last_ms = 0
_seq = 0


def new_id(prefix: str = "") -> str:
    """UUIDv7 风格 ID：48bit 毫秒时间戳 + 版本位 + 随机，保证大致按时间递增。

    ``prefix`` 可选（如 ``att_``），DB 内统一裸 32 位 hex 更省空间；
    对外暴露的 ID 原样返回即可。
    """
    global _last_ms, _seq
    with _seq_lock:
        now_ms = int(time.time() * 1000)
        if now_ms <= _last_ms:
            _seq += 1
            now_ms = _last_ms
        else:
            _seq = 0
            _last_ms = now_ms
    ts = now_ms.to_bytes(6, "big")
    rand = secrets.token_bytes(10)
    raw = bytearray(ts + rand)
    # version 7 in the high nibble of byte 6, variant bits in byte 8
    raw[6] = (raw[6] & 0x0F) | 0x70
    raw[8] = (raw[8] & 0x3F) | 0x80
    return prefix + raw.hex()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def dumps_json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=False)


def loads_json(text: str | None, default: Any = None) -> Any:
    import json

    if text is None or text == "":
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def like_escape(term: str) -> str:
    """把用户输入转成 LIKE 模式（转义 % _ \\），配合 ESCAPE '\\'。"""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def build_json_column(row: Mapping[str, Any], column: str, default: Any) -> Any:
    """读取行内 TEXT 存 JSON 的列。"""
    raw = row.get(column, None)
    value = loads_json(raw, default)
    return default if value is None else value


# --------------------------------------------------------------------------------------
# 表驱动的 CRUD 基类
# --------------------------------------------------------------------------------------


class Repository:
    """极简 CRUD：子类声明 table / columns / json_columns。

    * ``columns`` 是除 id/created_at/updated_at 之外的可写列；
    * ``json_columns`` 中的列在读写时自动序列化/反序列化；
    * 不做隐式字段猜测（显式白名单，避免把未知字段写进库）。
    """

    table: str = ""
    columns: Sequence[str] = ()
    json_columns: Sequence[str] = ()
    #: JSON 列的读默认值（缺省 None；列表列应显式写 []）
    json_defaults: Mapping[str, Any] = {}
    soft_delete: bool = False
    id_prefix: str = ""

    # -- 基础 ----------------------------------------------------------------
    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or get_conn()

    def _encode(self, data: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in data.items():
            if key in self.json_columns:
                out[key] = value if isinstance(value, str) else dumps_json(value)
            elif isinstance(value, bool):
                out[key] = 1 if value else 0
            else:
                out[key] = value
        return out

    def _decode(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        for key in self.json_columns:
            if key in data:
                data[key] = loads_json(data[key], self.json_defaults.get(key))
        return data

    def _where_alive(self) -> str:
        return " AND deleted_at IS NULL" if self.soft_delete else ""

    def get(self, entity_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE id = ?{self._where_alive()}", (entity_id,)
        ).fetchone()
        return self._decode(row)

    def list_all(self, *, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            f"SELECT * FROM {self.table} WHERE 1=1{self._where_alive()} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [self._decode(row) for row in rows]  # type: ignore[misc]

    def count(self) -> int:
        row = self.conn.execute(
            f"SELECT COUNT(*) FROM {self.table} WHERE 1=1{self._where_alive()}"
        ).fetchone()
        return int(row[0]) if row else 0

    def insert(self, data: Mapping[str, Any], *, entity_id: str | None = None) -> str:
        entity_id = entity_id or new_id(self.id_prefix)
        now = utcnow_iso()
        payload = self._encode({k: v for k, v in data.items() if k in self.columns})
        payload["id"] = entity_id
        payload.setdefault("created_at", now)
        payload["updated_at"] = payload.get("updated_at") or now
        cols = list(payload.keys())
        placeholders = ", ".join("?" for _ in cols)
        with transaction(self.conn) as conn:
            conn.execute(
                f"INSERT INTO {self.table} ({', '.join(cols)}) VALUES ({placeholders})",
                [payload[c] for c in cols],
            )
        return entity_id

    def update(self, entity_id: str, data: Mapping[str, Any], *, touch: bool = True) -> bool:
        payload = self._encode({k: v for k, v in data.items() if k in self.columns})
        if touch:
            payload["updated_at"] = utcnow_iso()
        if not payload:
            return bool(self.get(entity_id))
        assignments = ", ".join(f"{col} = ?" for col in payload)
        with transaction(self.conn) as conn:
            cur = conn.execute(
                f"UPDATE {self.table} SET {assignments} WHERE id = ?",
                [*payload.values(), entity_id],
            )
        return cur.rowcount > 0

    def delete(self, entity_id: str) -> bool:
        with transaction(self.conn) as conn:
            if self.soft_delete:
                cur = conn.execute(
                    f"UPDATE {self.table} SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
                    (utcnow_iso(), utcnow_iso(), entity_id),
                )
            else:
                cur = conn.execute(f"DELETE FROM {self.table} WHERE id = ?", (entity_id,))
        return cur.rowcount > 0

    def exists(self, entity_id: str) -> bool:
        row = self.conn.execute(
            f"SELECT 1 FROM {self.table} WHERE id = ?{self._where_alive()}", (entity_id,)
        ).fetchone()
        return row is not None
