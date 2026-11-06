"""SQLite database implementation (builtin, M0 default).

Implements the :class:`app.ports.database.Database` port on top of the standard
library ``sqlite3``. In production, set ``COURSE_STUDIO_DATABASE_BACKEND`` to
``postgres`` (backed by psycopg2/asyncpg implementing the same port) with zero
changes to business code.

Connections may be reused across threads (``check_same_thread=False``) and access
is serialized with a reentrant lock: synchronous endpoints run in the thread pool
while asynchronous endpoints run on the event-loop thread, and both share the same instance.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from app.ports.database import Database


class SQLiteDatabase(Database):
    """Database implementation backed by a SQLite file."""

    def __init__(self, path: str = "data/opencgp.db") -> None:
        self.path = Path(path)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    def connect(self) -> None:
        with self._lock:
            if self._conn is not None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._conn = conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        with self._lock:
            conn = self._ensure_conn()
            conn.execute(sql, tuple(params))
            conn.commit()

    def fetchone(
        self, sql: str, params: Sequence[Any] = ()
    ) -> Optional[Mapping[str, Any]]:
        with self._lock:
            conn = self._ensure_conn()
            row = conn.execute(sql, tuple(params)).fetchone()
            return dict(row) if row is not None else None

    def fetchall(
        self, sql: str, params: Sequence[Any] = ()
    ) -> list[Mapping[str, Any]]:
        with self._lock:
            conn = self._ensure_conn()
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def healthcheck(self) -> bool:
        try:
            with self._lock:
                conn = self._ensure_conn()
                conn.execute("SELECT 1").fetchone()
                return True
        except Exception:  # noqa: BLE001
            return False
