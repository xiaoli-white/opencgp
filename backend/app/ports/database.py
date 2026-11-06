"""Database abstract port (Database).

Defines the unified interface of the persistence layer. Business code depends only
on this protocol, not on a specific driver, so the backend can switch seamlessly
between SQLite (built-in default for M0) and PostgreSQL/pgvector (production)
without changing any business code.

Conventions:
- A query result represents one row as a ``dict`` (column name -> value).
- Connections are lazy: call ``connect()`` before first use and ``close()`` after;
  implementations must keep ``connect`` / ``close`` idempotent.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable


@runtime_checkable
class Database(Protocol):
    """Generic relational database port."""

    def connect(self) -> None:
        """Open a connection (idempotent)."""
        ...

    def close(self) -> None:
        """Close the connection and release resources (idempotent)."""
        ...

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        """Execute a write statement (INSERT/UPDATE/DELETE/DDL) and commit the transaction."""
        ...

    def fetchone(
        self, sql: str, params: Sequence[Any] = ()
    ) -> Optional[Mapping[str, Any]]:
        """Fetch a single row; return ``None`` when there is no result."""
        ...

    def fetchall(
        self, sql: str, params: Sequence[Any] = ()
    ) -> list[Mapping[str, Any]]:
        """Fetch multiple rows and return a list of rows."""
        ...

    def healthcheck(self) -> bool:
        """Health check: whether a minimal query executes successfully."""
        ...
