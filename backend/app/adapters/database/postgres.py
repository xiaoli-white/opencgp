from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Optional, Sequence

import psycopg
from psycopg.rows import dict_row

from app.adapters.database.sql_dialect import DialectTranslationError, translate
from app.ports.database import Database

DEFAULT_POOL_SIZE = 8
_CONNECT_TIMEOUT = 10
_IGNORABLE_SQLSTATES = frozenset({"42P07", "42710", "42701", "42P16"})
_PRIMARY_KEY_SQL = (
    "SELECT a.attname AS name FROM pg_index i"
    " JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)"
    " WHERE i.indrelid = to_regclass(%s) AND i.indisprimary"
    " ORDER BY array_position(i.indkey, a.attnum)"
)


class PostgresDatabase(Database):
    def __init__(
        self,
        dsn: str = "",
        pool_size: int = DEFAULT_POOL_SIZE,
    ) -> None:
        self.dsn = dsn
        self.pool_size = max(1, int(pool_size or DEFAULT_POOL_SIZE))
        self._pool: list[psycopg.Connection[Any]] = []
        self._lock = threading.Lock()
        self._semaphore = threading.BoundedSemaphore(self.pool_size)
        self._closed = False
        self._pk_cache: dict[str, tuple[str, ...]] = {}

    def _open(self) -> psycopg.Connection[Any]:
        if not self.dsn:
            raise RuntimeError("未配置 COURSE_STUDIO_DATABASE_DSN")
        return psycopg.connect(
            self.dsn,
            autocommit=True,
            row_factory=dict_row,
            connect_timeout=_CONNECT_TIMEOUT,
            application_name="opencgp",
        )

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        if self._closed:
            raise RuntimeError("数据库连接池已关闭")
        self._semaphore.acquire()
        connection: Optional[psycopg.Connection[Any]] = None
        broken = False
        try:
            with self._lock:
                if self._pool:
                    connection = self._pool.pop()
            if connection is None:
                connection = self._open()
            yield connection
        except psycopg.OperationalError:
            broken = True
            raise
        finally:
            if connection is None:
                self._semaphore.release()
                return
            if connection.closed:
                broken = True
            if broken or self._closed:
                try:
                    connection.close()
                except Exception:  # noqa: BLE001
                    pass
                self._semaphore.release()
            else:
                with self._lock:
                    self._pool.append(connection)
                self._semaphore.release()

    def connect(self) -> None:
        if self._closed:
            self._closed = False
        with self._connection() as connection:
            connection.execute("SELECT 1")

    def close(self) -> None:
        with self._lock:
            self._closed = True
            pool, self._pool = self._pool, []
        for connection in pool:
            try:
                connection.close()
            except Exception:  # noqa: BLE001
                pass

    def _primary_key(self, table: str) -> tuple[str, ...]:
        cached = self._pk_cache.get(table)
        if cached is not None:
            return cached
        try:
            with self._connection() as connection:
                rows = connection.execute(_PRIMARY_KEY_SQL, (table,)).fetchall()
            columns = tuple(str(row["name"]) for row in rows)
        except Exception:  # noqa: BLE001
            columns = ()
        self._pk_cache[table] = columns
        return columns

    def _prepare(self, sql: str, params: Sequence[Any]) -> str:
        return translate(sql, params, pk_lookup=self._primary_key)

    def _is_ignorable(self, exc: Exception) -> bool:
        code = getattr(exc, "sqlstate", None) or getattr(exc, "pgcode", None)
        return str(code) in _IGNORABLE_SQLSTATES

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        statement = self._prepare(sql, params)
        try:
            with self._connection() as connection:
                connection.execute(statement, tuple(params) if params else None)
        except psycopg.Error as exc:
            if self._is_ignorable(exc):
                return
            raise

    def fetchone(
        self, sql: str, params: Sequence[Any] = ()
    ) -> Optional[Mapping[str, Any]]:
        statement = self._prepare(sql, params)
        with self._connection() as connection:
            row = connection.execute(
                statement, tuple(params) if params else None
            ).fetchone()
        return dict(row) if row is not None else None

    def fetchall(
        self, sql: str, params: Sequence[Any] = ()
    ) -> list[Mapping[str, Any]]:
        statement = self._prepare(sql, params)
        with self._connection() as connection:
            rows = connection.execute(
                statement, tuple(params) if params else None
            ).fetchall()
        return [dict(row) for row in rows]

    def healthcheck(self) -> bool:
        try:
            with self._connection() as connection:
                connection.execute("SELECT 1").fetchone()
            return True
        except Exception:  # noqa: BLE001
            return False


__all__ = ["PostgresDatabase", "DialectTranslationError"]
