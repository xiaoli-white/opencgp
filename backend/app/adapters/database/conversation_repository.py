"""Database implementation of the conversation-thread repository (based on the Database port).

Depends only on :class:`app.ports.database.Database`, so SQLite (M0 default) and
PostgreSQL (production) share the same implementation; switching only changes config.

Storage conventions:
- A partial unique index on ``threads.unit_id`` guarantees one chapter-level thread
  per chapter (idempotent thread creation).
- Messages are append-only; ``_next_timestamp`` keeps ``created_at`` strictly
  increasing within a thread, so user/assistant messages from the same second do
  not jitter in ordering.
- ``citations_json`` is stored as JSON text, so switching databases needs no JSONB migration.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Mapping, Sequence

from app.models.citation import Citation
from app.models.thread import Message, Thread
from app.ports.conversation_repository import ConversationRepository
from app.ports.database import Database

MESSAGE_ROLES = ("user", "assistant", "system")

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS threads (
        id TEXT PRIMARY KEY,
        series_id TEXT NOT NULL DEFAULT '',
        unit_id TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_threads_unit_unique
    ON threads(unit_id) WHERE unit_id <> ''
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        thread_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        citations_json TEXT NOT NULL DEFAULT '[]',
        created_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, created_at)",
)


class DatabaseConversationRepository(ConversationRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        self._schema_ready = True

    def get_or_create_unit_thread(
        self, unit_id: str, series_id: str = "", title: str = ""
    ) -> Thread:
        self.ensure_schema()
        existing = self.get_unit_thread(unit_id)
        if existing is not None:
            return existing
        now = time.time()
        thread = Thread(
            id=_new_id(),
            series_id=series_id,
            unit_id=unit_id,
            title=title,
            created_at=now,
            updated_at=now,
        )
        try:
            self.database.execute(
                "INSERT INTO threads (id, series_id, unit_id, title, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    thread.id,
                    thread.series_id,
                    thread.unit_id,
                    thread.title,
                    thread.created_at,
                    thread.updated_at,
                ),
            )
        except Exception:
            raced = self.get_unit_thread(unit_id)
            if raced is None:
                raise
            return raced
        return thread

    def get_thread(self, thread_id: str) -> Thread | None:
        self.ensure_schema()
        row = self.database.fetchone("SELECT * FROM threads WHERE id = ?", (thread_id,))
        return _to_thread(row) if row else None

    def get_unit_thread(self, unit_id: str) -> Thread | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM threads WHERE unit_id = ? ORDER BY created_at ASC LIMIT 1",
            (unit_id,),
        )
        return _to_thread(row) if row else None

    def list_unit_threads(self, unit_id: str) -> list[Thread]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM threads WHERE unit_id = ? ORDER BY created_at ASC",
            (unit_id,),
        )
        return [_to_thread(row) for row in rows]

    def append_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        citations: Sequence[Citation] | None = None,
    ) -> Message:
        self.ensure_schema()
        resolved_role = role if role in MESSAGE_ROLES else "user"
        created_at = self._next_timestamp(thread_id)
        message = Message(
            id=_new_id(),
            thread_id=thread_id,
            role=resolved_role,
            content=content,
            citations=list(citations or []),
            created_at=created_at,
        )
        self.database.execute(
            "INSERT INTO messages (id, thread_id, role, content, citations_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                message.id,
                message.thread_id,
                message.role,
                message.content,
                _dump_list([citation.model_dump() for citation in message.citations]),
                message.created_at,
            ),
        )
        self.database.execute(
            "UPDATE threads SET updated_at = ? WHERE id = ?", (created_at, thread_id)
        )
        return message

    def get_message(self, message_id: str) -> Message | None:
        self.ensure_schema()
        row = self.database.fetchone("SELECT * FROM messages WHERE id = ?", (message_id,))
        return _to_message(row) if row else None

    def list_messages(self, thread_id: str, limit: int | None = None) -> list[Message]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM messages WHERE thread_id = ? ORDER BY created_at ASC",
            (thread_id,),
        )
        messages = [_to_message(row) for row in rows]
        if limit is not None and limit > 0 and len(messages) > limit:
            return messages[-limit:]
        return messages

    def count_messages(self, thread_id: str) -> int:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT COUNT(*) AS total FROM messages WHERE thread_id = ?", (thread_id,)
        )
        if not row or row["total"] is None:
            return 0
        return int(row["total"])

    def list_threads(
        self, series_ids: Sequence[str] | None = None, limit: int = 200
    ) -> list[Thread]:
        self.ensure_schema()
        clauses = ["1 = 1"]
        params: list[Any] = []
        if series_ids is not None:
            scoped = [str(item) for item in series_ids if item]
            if not scoped:
                return []
            placeholders = ", ".join("?" for _ in scoped)
            clauses.append(f"series_id IN ({placeholders})")
            params.extend(scoped)
        params.append(max(1, int(limit)))
        rows = self.database.fetchall(
            f"SELECT * FROM threads WHERE {' AND '.join(clauses)}"
            " ORDER BY updated_at DESC LIMIT ?",
            tuple(params),
        )
        return [_to_thread(row) for row in rows]

    def update_thread_title(self, thread_id: str, title: str) -> Thread | None:
        self.ensure_schema()
        current = self.get_thread(thread_id)
        if current is None:
            return None
        self.database.execute(
            "UPDATE threads SET title = ?, updated_at = ? WHERE id = ?",
            ((title or "").strip(), time.time(), thread_id),
        )
        return self.get_thread(thread_id)

    def delete_thread(self, thread_id: str) -> int:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT COUNT(*) AS total FROM messages WHERE thread_id = ?", (thread_id,)
        )
        removed = int(row["total"]) if row and row["total"] is not None else 0
        self.database.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
        self.database.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
        return removed

    def _next_timestamp(self, thread_id: str) -> float:
        now = time.time()
        row = self.database.fetchone(
            "SELECT MAX(created_at) AS last_at FROM messages WHERE thread_id = ?",
            (thread_id,),
        )
        if not row or row["last_at"] is None:
            return now
        return max(now, float(row["last_at"]) + 1e-6)


def _new_id() -> str:
    return str(uuid.uuid4())


def _dump_list(values: Sequence[Any]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _load_list(raw: Any) -> list[Any]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _to_thread(row: Mapping[str, Any]) -> Thread:
    return Thread(
        id=str(row["id"]),
        series_id=str(row["series_id"] or ""),
        unit_id=str(row["unit_id"] or ""),
        title=str(row["title"] or ""),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _to_message(row: Mapping[str, Any]) -> Message:
    citations = [Citation(**item) for item in _load_list(row["citations_json"])]
    return Message(
        id=str(row["id"]),
        thread_id=str(row["thread_id"]),
        role=str(row["role"]),
        content=str(row["content"] or ""),
        citations=citations,
        created_at=float(row["created_at"]),
    )
