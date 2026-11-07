from __future__ import annotations

import json
import time
import uuid
from typing import Any, Mapping, Sequence

from app.models.citation import Citation
from app.models.piece import Piece, PieceVersion, OutlineSection
from app.ports.database import Database
from app.ports.piece_repository import PieceRepository

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS pieces (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        user_id TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL,
        brief TEXT NOT NULL DEFAULT '',
        profile_json TEXT NOT NULL DEFAULT '{}',
        outline_json TEXT NOT NULL DEFAULT '[]',
        content TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'draft',
        current_version INTEGER NOT NULL DEFAULT 0,
        target_words INTEGER NOT NULL DEFAULT 3000,
        last_mode TEXT NOT NULL DEFAULT '',
        grounded INTEGER NOT NULL DEFAULT 0,
        gate_json TEXT NOT NULL DEFAULT '{}',
        citations_json TEXT NOT NULL DEFAULT '[]',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS piece_versions (
        id TEXT PRIMARY KEY,
        piece_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        content TEXT NOT NULL DEFAULT '',
        outline_json TEXT NOT NULL DEFAULT '[]',
        citations_json TEXT NOT NULL DEFAULT '[]',
        note TEXT NOT NULL DEFAULT '',
        mode TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pieces_tenant ON pieces(tenant_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_piece_versions ON piece_versions(piece_id, version)",
)

COLUMN_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("pieces", "brief", "TEXT NOT NULL DEFAULT ''"),
    ("pieces", "profile_id", "TEXT NOT NULL DEFAULT ''"),
    ("pieces", "grounded", "INTEGER NOT NULL DEFAULT 0"),
    ("pieces", "gate_json", "TEXT NOT NULL DEFAULT '{}'"),
)


class DatabasePieceRepository(PieceRepository):
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

    def create(self, piece: Piece) -> Piece:
        self.ensure_schema()
        now = time.time()
        created = piece.created_at or now
        self.database.execute(
            """
            INSERT INTO pieces
                (id, tenant_id, user_id, title, brief, profile_json, outline_json, content,
                 status, current_version, target_words, last_mode, grounded, gate_json,
                 citations_json, profile_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                piece.id,
                piece.tenant_id,
                piece.user_id,
                piece.title,
                piece.brief,
                json.dumps(piece.profile.model_dump(), ensure_ascii=False),
                _dump_outline(piece.outline),
                piece.content,
                piece.status,
                int(piece.current_version),
                int(piece.target_words),
                piece.last_mode,
                1 if piece.grounded else 0,
                json.dumps(piece.gate or {}, ensure_ascii=False),
                _dump_citations(piece.citations),
                piece.profile_id,
                created,
                now,
            ),
        )
        return piece.model_copy(update={"created_at": created, "updated_at": now})

    def get(self, piece_id: str, tenant_id: str | None = None) -> Piece | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM pieces WHERE id = ?", (piece_id,)
        )
        if row is None:
            return None
        if tenant_id is not None and str(row["tenant_id"] or "") != (tenant_id or ""):
            return None
        return _row_to_piece(row)

    def list(self, tenant_id: str | None = None, limit: int = 50) -> list[Piece]:
        self.ensure_schema()
        if tenant_id is None:
            rows = self.database.fetchall(
                "SELECT * FROM pieces ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            )
        else:
            rows = self.database.fetchall(
                "SELECT * FROM pieces WHERE tenant_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (tenant_id or "", int(limit)),
            )
        return [_row_to_piece(row) for row in rows]

    def update(
        self,
        piece_id: str,
        outline: Sequence[OutlineSection] | None = None,
        content: str | None = None,
        status: str | None = None,
        last_mode: str | None = None,
        citations: Sequence[Citation] | None = None,
        title: str | None = None,
        profile: dict[str, Any] | None = None,
        target_words: int | None = None,
        profile_id: str | None = None,
        brief: str | None = None,
    ) -> Piece | None:
        self.ensure_schema()
        current = self.get(piece_id)
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
        if brief is not None:
            sets.append("brief = ?")
            params.append(brief)
        params.append(piece_id)
        self.database.execute(
            f"UPDATE pieces SET {', '.join(sets)} WHERE id = ?", tuple(params)
        )
        return self.get(piece_id)

    def append_version(
        self,
        piece_id: str,
        content: str,
        outline: Sequence[OutlineSection] | None = None,
        citations: Sequence[Citation] | None = None,
        note: str = "",
        mode: str = "",
        grounded: bool | None = None,
        gate: dict[str, Any] | None = None,
    ) -> tuple[Piece, PieceVersion] | None:
        self.ensure_schema()
        current = self.get(piece_id)
        if current is None:
            return None
        version = int(current.current_version) + 1
        next_outline = list(outline) if outline is not None else list(current.outline)
        next_citations = list(citations) if citations is not None else list(current.citations)
        now = time.time()
        record = PieceVersion(
            id=f"pcver_{uuid.uuid4().hex[:16]}",
            piece_id=piece_id,
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
            INSERT INTO piece_versions
                (id, piece_id, version, content, outline_json, citations_json,
                 note, mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                piece_id,
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
            UPDATE pieces SET content = ?, outline_json = ?, citations_json = ?,
                status = ?, current_version = ?, last_mode = ?, grounded = ?,
                gate_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                content,
                _dump_outline(next_outline),
                _dump_citations(next_citations),
                "completed" if content.strip() else current.status,
                version,
                mode or current.last_mode,
                (1 if grounded else 0)
                if grounded is not None
                else (1 if current.grounded else 0),
                json.dumps(gate, ensure_ascii=False)
                if gate is not None
                else json.dumps(current.gate or {}, ensure_ascii=False),
                now,
                piece_id,
            ),
        )
        updated = self.get(piece_id)
        if updated is None:
            return None
        return updated, record

    def list_versions(self, piece_id: str) -> list[PieceVersion]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM piece_versions WHERE piece_id = ? ORDER BY version",
            (piece_id,),
        )
        return [_row_to_version(row) for row in rows]

    def get_version(self, piece_id: str, version: int) -> PieceVersion | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM piece_versions WHERE piece_id = ? AND version = ?",
            (piece_id, int(version)),
        )
        return _row_to_version(row) if row is not None else None

    def count_by_user(self, user_id: str) -> int:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT COUNT(1) AS n FROM pieces WHERE user_id = ? AND user_id <> ''",
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
                f"SELECT COUNT(1) AS n FROM pieces WHERE user_id = ?"
                f" AND tenant_id IN ({placeholders})",
                (user_id, *scoped),
            )
            total = int(row["n"]) if row else 0
            self.database.execute(
                f"UPDATE pieces SET user_id = ?, updated_at = ? WHERE user_id = ?"
                f" AND tenant_id IN ({placeholders})",
                (target_user_id, time.time(), user_id, *scoped),
            )
            return total
        row = self.database.fetchone(
            "SELECT COUNT(1) AS n FROM pieces WHERE user_id = ?", (user_id,)
        )
        total = int(row["n"]) if row else 0
        self.database.execute(
            "UPDATE pieces SET user_id = ?, updated_at = ? WHERE user_id = ?",
            (target_user_id, time.time(), user_id),
        )
        return total

    def delete(self, piece_id: str, tenant_id: str | None = None) -> bool:
        self.ensure_schema()
        if self.get(piece_id, tenant_id) is None:
            return False
        self.database.execute(
            "DELETE FROM piece_versions WHERE piece_id = ?", (piece_id,)
        )
        self.database.execute("DELETE FROM pieces WHERE id = ?", (piece_id,))
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


def _row_to_piece(row: Mapping[str, Any]) -> Piece:
    profile = _load_json(row["profile_json"], {})
    outline = _load_json(row["outline_json"], [])
    citations = _load_json(row["citations_json"], [])
    return Piece(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"] or ""),
        user_id=str(row["user_id"] or ""),
        title=str(row["title"] or ""),
        brief=str(row["brief"] or "") if "brief" in row.keys() else "",
        profile=profile if isinstance(profile, dict) else {},
        outline=[section for section in outline if isinstance(section, dict)]
        if isinstance(outline, list)
        else [],
        content=str(row["content"] or ""),
        status=str(row["status"] or ""),
        current_version=int(row["current_version"] or 0),
        target_words=int(row["target_words"] or 0),
        last_mode=str(row["last_mode"] or ""),
        grounded=bool(row["grounded"]) if "grounded" in row.keys() else False,
        gate=_load_json(row["gate_json"], {})
        if "gate_json" in row.keys()
        else {},
        citations=[item for item in citations if isinstance(item, dict)]
        if isinstance(citations, list)
        else [],
        profile_id=str(row["profile_id"] or ""),
        created_at=float(row["created_at"] or 0.0),
        updated_at=float(row["updated_at"] or 0.0),
    )


def _row_to_version(row: Mapping[str, Any]) -> PieceVersion:
    outline = _load_json(row["outline_json"], [])
    citations = _load_json(row["citations_json"], [])
    return PieceVersion(
        id=str(row["id"]),
        piece_id=str(row["piece_id"]),
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
