"""本地文件存储：内容寻址附件、导出写盘、路径越界断言、备份导出。

磁盘布局（ARCHITECTURE §3.1）::

    data/
      app.db            SQLite（WAL）
      files/<xx>/<sha256>.<ext>      其余附件（照片、证据、导出快照）
      imports/<sha256>.<ext>         用户上传的原始简历（隐私级：永不进 LLM）
      exports/<build 文件名>          导出产物（PDF/DOCX）
      logs/                          运行日志
      tmp/                           原子写临时文件

为什么内容寻址：同名文件天然去重、上传文件名不参与磁盘命名（防路径注入与
中文名编码问题），原始文件名只存 ``attachment.original_name``。
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Iterator, Mapping, Sequence

from .. import config as config_mod
from .. import db as db_mod
from ..errors import ApiError

#: 扩展名白名单（上传）
ALLOWED_UPLOAD_EXTS: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "md": "text/markdown",
    "txt": "text/plain",
    "html": "text/html",
}

#: magic bytes 双判定（扩展名说 PDF 但内容不是 → 拒绝）
MAGIC_PREFIXES: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF",),
    "docx": (b"PK\x03\x04",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
}

#: 上传大小上限
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_PHOTO_BYTES = 5 * 1024 * 1024

_SAFE_EXT_RE = re.compile(r"^[a-z0-9]{1,10}$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_ext(filename: str) -> str:
    ext = Path(filename or "").suffix.lower().lstrip(".")
    return ext if _SAFE_EXT_RE.match(ext or "") else ""


def guess_mime(ext: str) -> str:
    return ALLOWED_UPLOAD_EXTS.get(ext) or mimetypes.guess_type(f"x.{ext}")[0] or "application/octet-stream"


def validate_upload(filename: str, data: bytes, *, allowed: Sequence[str] | None = None) -> tuple[str, str]:
    """扩展名 + magic bytes 双判定，返回 (ext, mime)。不合法抛 415/413。"""
    ext = normalize_ext(filename)
    allowed_set = set(allowed or ALLOWED_UPLOAD_EXTS.keys())
    if ext not in allowed_set:
        raise ApiError(
            "UNSUPPORTED_MEDIA_TYPE",
            f"不支持的文件类型 .{ext or '?'}",
            details={"allowed": sorted(allowed_set)},
            hint="支持 PDF / DOCX / MD / TXT / HTML / PNG / JPG",
        )
    if not data:
        raise ApiError("PAYLOAD_TOO_LARGE", "文件为空", details={"bytes": 0})
    prefixes = MAGIC_PREFIXES.get(ext)
    if prefixes and not any(data.startswith(prefix) for prefix in prefixes):
        raise ApiError(
            "UNSUPPORTED_MEDIA_TYPE",
            f"文件内容与扩展名 .{ext} 不匹配",
            details={"ext": ext},
            hint="请确认文件未被改扩展名或损坏",
        )
    return ext, guess_mime(ext)


@dataclass
class StoredFile:
    attachment_id: str
    sha256: str
    path: Path
    bytes: int
    ext: str
    mime: str
    original_name: str
    kind: str
    privacy: str
    deduplicated: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.attachment_id,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "ext": self.ext,
            "mime": self.mime,
            "original_name": self.original_name,
            "kind": self.kind,
            "privacy": self.privacy,
            "deduplicated": self.deduplicated,
        }


class Storage:
    """所有落盘动作的唯一入口（便于统一断言路径与原子写）。"""

    def __init__(self, conn: sqlite3.Connection | None = None, paths: db_mod.Paths | None = None) -> None:
        self.paths = paths or db_mod.get_paths()
        self._conn = conn

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn or db_mod.get_conn()

    # -- 路径 ------------------------------------------------------------------
    def attachment_path(self, sha256: str, ext: str, kind: str) -> Path:
        """按 kind 决定目录：

        * ``resume_source``（用户原始简历）→ ``data/imports/<sha>.<ext>``
        * ``photo``（证件照）→ ``data/profile/photo_<sha>.<ext>``（与 docs 一致，便于 t8 渲染取用）
        * 其余 → ``data/files/<sha[:2]>/<sha>.<ext>``
        """
        ext = normalize_ext(f"x.{ext}") or "bin"
        if kind == "resume_source":
            return self.paths.imports / f"{sha256}.{ext}"
        if kind == "photo":
            profile_dir = self.paths.root / "profile"
            profile_dir.mkdir(parents=True, exist_ok=True)
            return profile_dir / f"photo_{sha256[:16]}.{ext}"
        return self.paths.files / sha256[:2] / f"{sha256}.{ext}"

    def locate_attachment(self, row: dict[str, Any]) -> Path:
        path = self.attachment_path(str(row["sha256"]), str(row["ext"]), str(row["kind"]))
        return self.paths.assert_within(path)

    def export_dir(self) -> Path:
        return self.paths.assert_within(self.paths.exports)

    # -- 上传 ------------------------------------------------------------------
    def save_attachment(
        self,
        data: bytes,
        *,
        original_name: str,
        kind: str = "evidence",
        privacy: str = "private",
        allowed_exts: Sequence[str] | None = None,
        max_bytes: int | None = None,
    ) -> StoredFile:
        limit = max_bytes or (MAX_PHOTO_BYTES if kind == "photo" else MAX_UPLOAD_BYTES)
        if len(data) > limit:
            raise ApiError(
                "PAYLOAD_TOO_LARGE",
                f"文件超过 {limit // (1024 * 1024)}MB 上限",
                details={"bytes": len(data), "limit": limit},
            )
        ext, mime = validate_upload(original_name, data, allowed=allowed_exts)
        digest = sha256_bytes(data)
        target = self.paths.assert_within(self.attachment_path(digest, ext, kind))

        existing = self.conn.execute(
            "SELECT * FROM attachment WHERE sha256 = ?", (digest,)
        ).fetchone()
        if existing is not None:
            row = dict(existing)
            path = self.paths.assert_within(self.attachment_path(digest, row["ext"], row["kind"]))
            if not path.exists():
                self._atomic_write(path, data)
            return StoredFile(
                attachment_id=row["id"],
                sha256=digest,
                path=path,
                bytes=int(row["bytes"]),
                ext=row["ext"],
                mime=row["mime"],
                original_name=row["original_name"],
                kind=row["kind"],
                privacy=row["privacy"],
                deduplicated=True,
            )

        self._atomic_write(target, data)
        attachment_id = db_mod.new_id()
        now = db_mod.utcnow_iso()
        with db_mod.transaction(self.conn) as conn:
            conn.execute(
                "INSERT INTO attachment(id, sha256, original_name, ext, mime, bytes, kind, privacy, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (attachment_id, digest, original_name, ext, mime, len(data), kind, privacy, now),
            )
        return StoredFile(
            attachment_id=attachment_id,
            sha256=digest,
            path=target,
            bytes=len(data),
            ext=ext,
            mime=mime,
            original_name=original_name,
            kind=kind,
            privacy=privacy,
            deduplicated=False,
        )

    def _atomic_write(self, target: Path, data: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.paths.tmp), prefix="up_")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, target)
        except OSError as exc:  # pragma: no cover - 磁盘满/权限问题
            Path(tmp_name).unlink(missing_ok=True)
            raise ApiError("STORAGE_ERROR", "写入附件失败", details={"reason": str(exc)}) from exc

    # -- 读取 ------------------------------------------------------------------
    def get_attachment(self, attachment_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM attachment WHERE id = ?", (attachment_id,)).fetchone()
        if row is None:
            raise ApiError("NOT_FOUND", "附件不存在", details={"resource": "attachment", "id": attachment_id})
        return dict(row)

    def open_attachment(self, attachment_id: str) -> tuple[Path, dict[str, Any]]:
        row = self.get_attachment(attachment_id)
        path = self.locate_attachment(row)
        if not path.exists():
            raise ApiError("NOT_FOUND", "附件文件已丢失", details={"resource": "attachment", "id": attachment_id})
        return path, row

    #: 引用检查覆盖的表 → 人话标签（captain m01767：一次误删 = 简历照片永久消失）
    def attachment_references(self, attachment_id: str) -> list[str]:
        """列出「谁在用这个附件」，返回人话标签（不是表名）。

        覆盖三类真实引用：
        * ``user_profile.photo_path`` / ``extra.photo_attachment_id``：个人资料照片；
        * ``build_artifact``：已导出的简历文件；
        * ``import_job.draft_json.extracted_photo``：导入草稿里的照片候选。
        另外同内容（sha256）的其它附件行也算「内容仍被引用」，删文件会连坐。
        """
        row = self.get_attachment(attachment_id)
        labels: list[str] = []
        conn = self.conn

        profile = conn.execute("SELECT photo_path, extra_json FROM user_profile WHERE id = 'me'").fetchone()
        if profile is not None:
            extra = db_mod.loads_json(profile["extra_json"], {})
            if extra.get("photo_attachment_id") == attachment_id:
                labels.append("个人资料照片")
            elif profile["photo_path"] and self._same_content(profile["photo_path"], row):
                labels.append("个人资料照片")

        for (rel_path,) in conn.execute("SELECT rel_path FROM build_artifact").fetchall():
            if rel_path and self._same_content(rel_path, row):
                labels.append(f"构建产物：{Path(rel_path).name}")

        placeholders = None
        for (draft_json,) in conn.execute("SELECT draft_json FROM import_job").fetchall():
            if not draft_json:
                continue
            draft = db_mod.loads_json(draft_json, {}) or {}
            candidate = draft.get("extracted_photo") or {}
            if candidate.get("attachment_id") == attachment_id or (
                candidate.get("file") and self._same_content(candidate["file"], row)
            ):
                labels.append("导入草稿里的照片候选")
                break
        del placeholders

        others = conn.execute(
            "SELECT COUNT(*) FROM attachment WHERE sha256 = ? AND id <> ?",
            (row["sha256"], attachment_id),
        ).fetchone()[0]
        if others:
            labels.append(f"另有 {others} 个附件行共用同一份内容（sha256 相同）")
        return labels

    def _same_content(self, rel_path: str, row: Mapping[str, Any]) -> bool:
        """rel_path 指向的文件是不是这一行的内容（按内容寻址命名或 sha 比对）。"""
        rel = str(rel_path).replace("\\", "/")
        if Path(rel).name == self.attachment_path(row["sha256"], row["ext"], row["kind"]).name:
            return True
        try:
            path = self.paths.assert_within(self.paths.root / rel)
        except ApiError:
            return False
        if not path.exists():
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]

    def delete_attachment(self, attachment_id: str, *, remove_file: bool = False) -> bool:
        """删除附件行（可选删文件）。

        顺序（captain m01767 要求）：**先查引用 → 再删行 → 最后 unlink**。
        反过来的话中途抛异常会留下「行没了、文件还在」的孤儿；更糟的是先 unlink
        再发现被引用，照片就永久没了（内容寻址没有副本）。
        被引用时抛 409 ``FILE_IN_USE``，且**不提供 force** —— 这个仓库没有需要绕过
        守卫的场景，正确做法是先去个人资料页解除绑定。
        """
        row = self.get_attachment(attachment_id)
        references = self.attachment_references(attachment_id)
        if references:
            raise ApiError(
                "FILE_IN_USE",
                "该文件仍被引用，不能删除",
                details={"attachment_id": attachment_id, "referenced_by": references},
                hint="请先在个人资料页解除绑定（DELETE /api/v1/profile/photo），或先删除引用它的构建产物",
            )
        with db_mod.transaction(self.conn) as conn:
            conn.execute("DELETE FROM attachment WHERE id = ?", (attachment_id,))
        if remove_file:
            self.locate_attachment(row).unlink(missing_ok=True)
        return True

    # -- 导出 ------------------------------------------------------------------
    def export_listing(self) -> list[str]:
        return sorted(p.name for p in self.export_dir().iterdir() if p.is_file())

    def write_export(self, filename: str, data: bytes, *, overwrite: bool = False) -> tuple[Path, str, list[str]]:
        """写导出产物，返回 (绝对路径, 相对 data/exports 的路径, warnings)。

        同名冲突默认追加 ``-2``/``-3``（契约 §9.5），``overwrite=True`` 才覆盖。
        """
        warnings: list[str] = []
        directory = self.export_dir()
        target = self.paths.assert_within(directory / Path(filename).name)
        if target.exists() and not overwrite:
            stem, suffix = target.stem, target.suffix
            index = 2
            while True:
                candidate = self.paths.assert_within(directory / f"{stem}-{index}{suffix}")
                if not candidate.exists():
                    target = candidate
                    break
                index += 1
            warnings.append(f"NAMING_COLLISION_SUFFIXED:{target.name}")
        self._atomic_write(target, data)
        rel = str(target.relative_to(self.paths.root))
        return target, rel, warnings

    def resolve_export_rel(self, rel_path: str) -> Path:
        """把 DB 里的相对路径解析回绝对路径（越界 → PATH_ESCAPE）。"""
        candidate = self.paths.root / rel_path
        return self.paths.assert_within(candidate)

    # -- 备份 ------------------------------------------------------------------
    def export_all_zip(self, dest: Path) -> Path:
        """把 db + files + exports 打包（**不含 .env**，也不含 imports 原件？见下）。

        ``imports/`` 属于用户原始简历：包含在内，因为这是本地备份，不涉及出网；
        但 .env / LLM_API_KEY 绝不打进 zip。
        """
        dest = self.paths.assert_within(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.paths.tmp), prefix="zip_", suffix=".zip")
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
                db_copy = self.paths.tmp / "backup_app.db"
                self._backup_db(db_copy)
                bundle.write(db_copy, "app.db")
                db_copy.unlink(missing_ok=True)
                for folder, arc_root in (
                    (self.paths.files, "files"),
                    (self.paths.exports, "exports"),
                    (self.paths.imports, "imports"),
                ):
                    if not folder.exists():
                        continue
                    for path in sorted(folder.rglob("*")):
                        if path.is_file():
                            bundle.write(path, f"{arc_root}/{path.relative_to(folder).as_posix()}")
                bundle.writestr(
                    "manifest.json",
                    db_mod.dumps_json(
                        {
                            "created_at": db_mod.utcnow_iso(),
                            "app_version": config_mod.APP_VERSION,
                            "excludes": [".env", "logs/", "tmp/"],
                        }
                    ),
                )
            os.replace(tmp_path, dest)
        except OSError as exc:  # pragma: no cover
            tmp_path.unlink(missing_ok=True)
            raise ApiError("STORAGE_ERROR", "打包备份失败", details={"reason": str(exc)}) from exc
        return dest

    def _backup_db(self, dest: Path) -> None:
        target = sqlite3.connect(str(dest))
        try:
            self.conn.backup(target)
        finally:
            target.close()
