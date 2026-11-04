from __future__ import annotations

import time
import uuid
from typing import Any, Mapping

from app.models.quota import (
    DEFAULT_MONTHLY_GENERATIONS,
    DEFAULT_MONTHLY_UPLOADS,
    DEFAULT_STORAGE_BYTES,
    LessonLock,
    QuotaLimits,
    QuotaUsage,
)
from app.ports.database import Database
from app.ports.lock_repository import LockRepository
from app.ports.quota_repository import QuotaRepository

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS tenant_quotas (
        tenant_id TEXT PRIMARY KEY,
        monthly_generations INTEGER NOT NULL DEFAULT 200,
        monthly_uploads INTEGER NOT NULL DEFAULT 100,
        storage_bytes INTEGER NOT NULL DEFAULT 104857600,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS usage_events (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        user_id TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL,
        units INTEGER NOT NULL DEFAULT 1,
        ref_id TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_usage_events_tenant ON usage_events(tenant_id, created_at)",
    """
    CREATE TABLE IF NOT EXISTS lesson_locks (
        lesson_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        user_id TEXT NOT NULL DEFAULT '',
        user_name TEXT NOT NULL DEFAULT '',
        token TEXT NOT NULL DEFAULT '',
        heartbeat_at REAL NOT NULL DEFAULT 0,
        expires_at REAL NOT NULL DEFAULT 0
    )
    """,
)


class DatabaseQuotaRepository(QuotaRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        self._schema_ready = True

    def get_limits(self, tenant_id: str) -> QuotaLimits:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM tenant_quotas WHERE tenant_id = ?", (tenant_id,)
        )
        if row is None:
            limits = QuotaLimits(
                monthly_generations=DEFAULT_MONTHLY_GENERATIONS,
                monthly_uploads=DEFAULT_MONTHLY_UPLOADS,
                storage_bytes=DEFAULT_STORAGE_BYTES,
            )
            self.save_limits(tenant_id, limits)
            return limits
        return _limits_from_row(row)

    def save_limits(self, tenant_id: str, limits: QuotaLimits) -> QuotaLimits:
        self.ensure_schema()
        now = time.time()
        self.database.execute(
            "INSERT INTO tenant_quotas (tenant_id, monthly_generations, monthly_uploads,"
            " storage_bytes, updated_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(tenant_id) DO UPDATE SET"
            " monthly_generations = excluded.monthly_generations,"
            " monthly_uploads = excluded.monthly_uploads,"
            " storage_bytes = excluded.storage_bytes,"
            " updated_at = excluded.updated_at",
            (
                tenant_id,
                int(limits.monthly_generations),
                int(limits.monthly_uploads),
                int(limits.storage_bytes),
                now,
            ),
        )
        return limits

    def usage(self, tenant_id: str, period_start: float) -> QuotaUsage:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT kind, SUM(units) AS units FROM usage_events"
            " WHERE tenant_id = ? AND created_at >= ? GROUP BY kind",
            (tenant_id, period_start),
        )
        period = _sum_kinds(rows)
        storage_rows = self.database.fetchall(
            "SELECT kind, SUM(units) AS units FROM usage_events"
            " WHERE tenant_id = ? AND kind = 'storage' GROUP BY kind",
            (tenant_id,),
        )
        storage = _sum_kinds(storage_rows)
        return QuotaUsage(
            period=time.strftime("%Y-%m", time.localtime(period_start)),
            generations=period["generate"]
            + period["amend"]
            + period["ask"]
            + period["blueprint"]
            + period["image"],
            uploads=period["upload"],
            storage_bytes=storage["storage"],
        )

    def record(
        self,
        tenant_id: str,
        user_id: str,
        kind: str,
        units: int = 1,
        ref_id: str = "",
    ) -> None:
        self.ensure_schema()
        self.database.execute(
            "INSERT INTO usage_events (id, tenant_id, user_id, kind, units, ref_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                uuid.uuid4().hex,
                tenant_id,
                user_id or "",
                kind,
                int(units),
                ref_id or "",
                time.time(),
            ),
        )


class DatabaseLockRepository(LockRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        self._schema_ready = True

    def get_lock(self, lesson_id: str) -> LessonLock | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM lesson_locks WHERE lesson_id = ?", (lesson_id,)
        )
        if row is None:
            return None
        return LessonLock(
            lesson_id=str(row["lesson_id"]),
            tenant_id=str(row["tenant_id"] or ""),
            user_id=str(row["user_id"] or ""),
            user_name=str(row["user_name"] or ""),
            token=str(row["token"] or ""),
            heartbeat_at=float(row["heartbeat_at"] or 0),
            expires_at=float(row["expires_at"] or 0),
        )

    def save_lock(self, lock: LessonLock) -> LessonLock:
        self.ensure_schema()
        self.database.execute(
            "INSERT INTO lesson_locks (lesson_id, tenant_id, user_id, user_name, token,"
            " heartbeat_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(lesson_id) DO UPDATE SET"
            " tenant_id = excluded.tenant_id, user_id = excluded.user_id,"
            " user_name = excluded.user_name, token = excluded.token,"
            " heartbeat_at = excluded.heartbeat_at, expires_at = excluded.expires_at",
            (
                lock.lesson_id,
                lock.tenant_id,
                lock.user_id,
                lock.user_name,
                lock.token,
                lock.heartbeat_at,
                lock.expires_at,
            ),
        )
        return lock

    def delete_lock(self, lesson_id: str) -> None:
        self.ensure_schema()
        self.database.execute(
            "DELETE FROM lesson_locks WHERE lesson_id = ?", (lesson_id,)
        )

    def delete_by_user(self, user_id: str) -> int:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT COUNT(*) AS total FROM lesson_locks WHERE user_id = ?", (user_id,)
        )
        removed = int(row["total"]) if row and row["total"] is not None else 0
        self.database.execute("DELETE FROM lesson_locks WHERE user_id = ?", (user_id,))
        return removed


def _limits_from_row(row: Mapping[str, Any]) -> QuotaLimits:
    return QuotaLimits(
        monthly_generations=int(row["monthly_generations"]),
        monthly_uploads=int(row["monthly_uploads"]),
        storage_bytes=int(row["storage_bytes"]),
    )


def _sum_kinds(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {"generate": 0, "amend": 0, "ask": 0, "blueprint": 0, "image": 0, "upload": 0, "storage": 0}
    for row in rows:
        kind = str(row["kind"])
        totals[kind] = totals.get(kind, 0) + int(row["units"] or 0)
    return totals
