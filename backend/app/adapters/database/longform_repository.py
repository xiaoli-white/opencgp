from __future__ import annotations

import json
import time
import uuid
from typing import Any, Mapping, Sequence

from app.models.citation import Citation
from app.models.longform import Longform, LongformVersion, OutlineSection
from app.ports.database import Database
from app.ports.longform_repository import LongformRepository

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS longforms (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        user_id TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL,
        profile_json TEXT NOT NULL DEFAULT '{}',
        outline_json TEXT NOT NULL DEFAULT '[]',
        content TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'draft',
        current_version INTEGER NOT NULL DEFAULT 0,
        target_words INTEGER NOT NULL DEFAULT 3000,
        last_mode TEXT NOT NULL DEFAULT '',
        citations_json TEXT NOT NULL DEFAULT '[]',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS longform_versions (
        id TEXT PRIMARY KEY,
        longform_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        content TEXT NOT NULL DEFAULT '',
        outline_json TEXT NOT NULL DEFAULT '[]',
        citations_json TEXT NOT NULL DEFAULT '[]',
        note TEXT NOT NULL DEFAULT '',
        mode TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_longforms_tenant ON longforms(tenant_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_longform_versions ON longform_versions(longform_id, version)",
)

COLUMN_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("longforms", "profile_id", "TEXT NOT NULL DEFAULT ''"),
)


class DatabaseLongformRepository(LongformRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        for table, column, ddl in COLUMN_MIGRATIONS:
            columns = {
                str(row["name"])
                for row in self.database.fetchall(f"PRAGMA table_info({table})")
            }
            if column not in columns:
                self.database.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        self._schema_ready = True

    def create(self, longform: Longform) -> Longform:
        self.ensure_schema()
        now = time.time()
        created = longform.created_at or now
        self.database.execute(
            """
            INSERT INTO longforms
                (id, tenant_id, user_id, title, profile_json, outline_json, content,
                 status, current_version, target_words, last_mode, citations_json,
                 profile_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                longform.id,
                longform.tenant_id,
                longform.user_id,
                longform.title,
                json.dumps(longform.profile.model_dump(), ensure_ascii=False),
                _dump_outline(longform.outline),
                longform.content,
                longform.status,
                int(longform.current_version),
                int(longform.target_words),
                longform.last_mode,
                _dump_citations(longform.citations),
                longform.profile_id,
                created,
                now,
            ),
        )
        return longform.model_copy(update={"created_at": created, "updated_at": now})

    def get(self, longform_id: str, tenant_id: str | None = None) -> Longform | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM longforms WHERE id = ?", (longform_id,)
        )
        if row is None:
            return None
        if tenant_id is not None and str(row["tenant_id"] or "") != (tenant_id or ""):
            return None
        return _row_to_longform(row)

    def list(self, tenant_id: str | None = None, limit: int = 50) -> list[Longform]:
        self.ensure_schema()
        if tenant_id is None:
            rows = self.database.fetchall(
                "SELECT * FROM longforms ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            )
        else:
            rows = self.database.fetchall(
                "SELECT * FROM longforms WHERE tenant_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (tenant_id or "", int(limit)),
            )
        return [_row_to_longform(row) for row in rows]

    def update(
        self,
        longform_id: str,
        outline: Sequence[OutlineSection] | None = None,
        content: str | None = None,
        status: str | None = None,
        last_mode: str | None = None,
        citations: Sequence[Citation] | None = None,
        title: str | None = None,
        profile: dict[str, Any] | None = None,
        target_words: int | None = None,
        profile_id: str | None = None,
    ) -> Longform | None:
        self.ensure_schema()
        current = self.get(longform_id)
        if current is None:
            return None
        sets = ["updated_at = ?"]
        params: list[Any] = [time.time()]
        if outline is not None:
            sets.append("outline_json = ?")
            params.append(_dump_outline(outline))
        if content is not None:
            sets.append("content = ?")
            params.append(content)
        if status is not None:
            sets.append("status = ?")
            params.append(status)
        if last_mode is not None:
            sets.append("last_mode = ?")
            params.append(last_mode)
        if citations is not None:
            sets.append("citations_json = ?")
            params.append(_dump_citations(citations))
        if title is not None:
            sets.append("title = ?")
            params.append(title)
        if profile is not None:
            sets.append("profile_json = ?")
            params.append(json.dumps(dict(profile), ensure_ascii=False))
        if target_words is not None:
            sets.append("target_words = ?")
            params.append(int(target_words))
        if profile_id is not None:
            sets.append("profile_id = ?")
            params.append(profile_id)
        params.append(longform_id)
        self.database.execute(
            f"UPDATE longforms SET {', '.join(sets)} WHERE id = ?", tuple(params)
        )
        return self.get(longform_id)

    def append_version(
        self,
        longform_id: str,
        content: str,
        outline: Sequence[OutlineSection] | None = None,
        citations: Sequence[Citation] | None = None,
        note: str = "",
        mode: str = "",
    ) -> tuple[Longform, LongformVersion] | None:
        self.ensure_schema()
        current = self.get(longform_id)
        if current is None:
            return None
        version = int(current.current_version) + 1
        next_outline = list(outline) if outline is not None else list(current.outline)
        next_citations = list(citations) if citations is not None else list(current.citations)
        now = time.time()
        record = LongformVersion(
            id=f"lfver_{uuid.uuid4().hex[:16]}",
            longform_id=longform_id,
            version=version,
            content=content,
            outline=next_outline,
            citations=next_citations,
            note=note,
            mode=mode,
            created_at=now,
        )
        self.database.execute(
            """
            INSERT INTO longform_versions
                (id, longform_id, version, content, outline_json, citations_json,
                 note, mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                longform_id,
                version,
                content,
                _dump_outline(next_outline),
                _dump_citations(next_citations),
                note,
                mode,
                now,
            ),
        )
        self.database.execute(
            """
            UPDATE longforms SET content = ?, outline_json = ?, citations_json = ?,
                status = ?, current_version = ?, last_mode = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                content,
                _dump_outline(next_outline),
                _dump_citations(next_citations),
                "completed" if content.strip() else current.status,
                version,
                mode or current.last_mode,
                now,
                longform_id,
            ),
        )
        updated = self.get(longform_id)
        if updated is None:
            return None
        return updated, record

    def list_versions(self, longform_id: str) -> list[LongformVersion]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM longform_versions WHERE longform_id = ? ORDER BY version",
            (longform_id,),
        )
        return [_row_to_version(row) for row in rows]

    def get_version(self, longform_id: str, version: int) -> LongformVersion | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM longform_versions WHERE longform_id = ? AND version = ?",
            (longform_id, int(version)),
        )
        return _row_to_version(row) if row is not None else None

    def count_by_user(self, user_id: str) -> int:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT COUNT(1) AS n FROM longforms WHERE user_id = ? AND user_id <> ''",
            (user_id,),
        )
        return int(row["n"]) if row else 0

    def transfer_by_user(
        self, user_id: str, target_user_id: str, tenant_ids: Sequence[str] = ()
    ) -> int:
        self.ensure_schema()
        scoped = [str(item) for item in tenant_ids if item]
        if scoped:
            placeholders = ", ".join("?" for _ in scoped)
            row = self.database.fetchone(
                f"SELECT COUNT(1) AS n FROM longforms WHERE user_id = ?"
                f" AND tenant_id IN ({placeholders})",
                (user_id, *scoped),
            )
            total = int(row["n"]) if row else 0
            self.database.execute(
                f"UPDATE longforms SET user_id = ?, updated_at = ? WHERE user_id = ?"
                f" AND tenant_id IN ({placeholders})",
                (target_user_id, time.time(), user_id, *scoped),
            )
            return total
        row = self.database.fetchone(
            "SELECT COUNT(1) AS n FROM longforms WHERE user_id = ?", (user_id,)
        )
        total = int(row["n"]) if row else 0
        self.database.execute(
            "UPDATE longforms SET user_id = ?, updated_at = ? WHERE user_id = ?",
            (target_user_id, time.time(), user_id),
        )
        return total

    def delete(self, longform_id: str, tenant_id: str | None = None) -> bool:
        self.ensure_schema()
        if self.get(longform_id, tenant_id) is None:
            return False
        self.database.execute(
            "DELETE FROM longform_versions WHERE longform_id = ?", (longform_id,)
        )
        self.database.execute("DELETE FROM longforms WHERE id = ?", (longform_id,))
        return True


def _dump_outline(outline: Sequence[OutlineSection]) -> str:
    return json.dumps(
        [section.model_dump() for section in outline], ensure_ascii=False
    )


def _dump_citations(citations: Sequence[Citation]) -> str:
    return json.dumps(
        [citation.model_dump() for citation in citations], ensure_ascii=False
    )


def _load_json(raw: Any, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except (TypeError, ValueError):
        return fallback


def _row_to_longform(row: Mapping[str, Any]) -> Longform:
    profile = _load_json(row["profile_json"], {})
    outline = _load_json(row["outline_json"], [])
    citations = _load_json(row["citations_json"], [])
    return Longform(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"] or ""),
        user_id=str(row["user_id"] or ""),
        title=str(row["title"] or ""),
        profile=profile if isinstance(profile, dict) else {},
        outline=[section for section in outline if isinstance(section, dict)]
        if isinstance(outline, list)
        else [],
        content=str(row["content"] or ""),
        status=str(row["status"] or ""),
        current_version=int(row["current_version"] or 0),
        target_words=int(row["target_words"] or 0),
        last_mode=str(row["last_mode"] or ""),
        citations=[item for item in citations if isinstance(item, dict)]
        if isinstance(citations, list)
        else [],
        profile_id=str(row["profile_id"] or ""),
        created_at=float(row["created_at"] or 0.0),
        updated_at=float(row["updated_at"] or 0.0),
    )


def _row_to_version(row: Mapping[str, Any]) -> LongformVersion:
    outline = _load_json(row["outline_json"], [])
    citations = _load_json(row["citations_json"], [])
    return LongformVersion(
        id=str(row["id"]),
        longform_id=str(row["longform_id"]),
        version=int(row["version"] or 0),
        content=str(row["content"] or ""),
        outline=[section for section in outline if isinstance(section, dict)]
        if isinstance(outline, list)
        else [],
        citations=[item for item in citations if isinstance(item, dict)]
        if isinstance(citations, list)
        else [],
        note=str(row["note"] or ""),
        mode=str(row["mode"] or ""),
        created_at=float(row["created_at"] or 0.0),
    )
