from __future__ import annotations

import time
import uuid
from typing import Any, Mapping

from app.models.quota import (
    DEFAULT_MONTHLY_GENERATIONS,
    GENERATION_KINDS,
    DEFAULT_MONTHLY_UPLOADS,
    DEFAULT_STORAGE_BYTES,
    UnitLock,
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
    CREATE TABLE IF NOT EXISTS unit_locks (
        unit_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        user_id TEXT NOT NULL DEFAULT '',
        user_name TEXT NOT NULL DEFAULT '',
        token TEXT NOT NULL DEFAULT '',
        heartbeat_at REAL NOT NULL DEFAULT 0,
        expires_at REAL NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS edit_locks (
        resource_type TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT '',
        user_id TEXT NOT NULL DEFAULT '',
        user_name TEXT NOT NULL DEFAULT '',
        token TEXT NOT NULL DEFAULT '',
        heartbeat_at REAL NOT NULL DEFAULT 0,
        expires_at REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (resource_type, resource_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_edit_locks_expiry ON edit_locks(expires_at)",
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
            generations=sum(period[kind] for kind in GENERATION_KINDS if kind in period),
            uploads=period["upload"],
            storage_bytes=storage["storage"],
        )

    def usage_by_kind(self, tenant_id: str, period_start: float) -> dict[str, int]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT kind, SUM(units) AS units FROM usage_events"
            " WHERE tenant_id = ? AND created_at >= ? GROUP BY kind",
            (tenant_id, period_start),
        )
        return {str(row["kind"]): int(row["units"] or 0) for row in rows}

    def daily_usage(self, tenant_id: str, since: float) -> list[dict[str, Any]]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT date(created_at, 'unixepoch', '+8 hours') AS day, kind,"
            " SUM(units) AS units FROM usage_events"
            " WHERE tenant_id = ? AND created_at >= ? GROUP BY day, kind ORDER BY day",
            (tenant_id, float(since)),
        )
        return [
            {
                "date": str(row["day"]),
                "kind": str(row["kind"]),
                "units": int(row["units"] or 0),
            }
            for row in rows
        ]

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
    """Persistence for explicit human edit locks.

    Locks live in ``edit_locks`` and are keyed by (resource_type, resource_id).
    Acquisition is a single upsert with a conditional WHERE clause so two API
    processes can race without both believing they won.  The legacy
    ``unit_locks`` table is kept for upgrades and is copied into the new table
    on schema initialisation.
    """

    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        # Preserve active locks created by an older backend release.
        try:
            self.database.execute(
                "INSERT INTO edit_locks (resource_type, resource_id, tenant_id,"
                " user_id, user_name, token, heartbeat_at, expires_at)"
                " SELECT 'unit', unit_id, tenant_id, user_id, user_name, token,"
                " heartbeat_at, expires_at FROM unit_locks WHERE expires_at > ?"
                " ON CONFLICT(resource_type, resource_id) DO NOTHING",
                (time.time(),),
            )
        except Exception:  # noqa: BLE001 - best-effort data migration
            pass
        self._schema_ready = True

    # -- generic edit locks ------------------------------------------------

    def get_edit_lock(
        self, resource_type: str, resource_id: str
    ) -> dict[str, Any] | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM edit_locks WHERE resource_type = ? AND resource_id = ?",
            (resource_type, resource_id),
        )
        return dict(row) if row is not None else None

    def try_acquire_edit_lock(
        self,
        resource_type: str,
        resource_id: str,
        tenant_id: str,
        user_id: str,
        user_name: str,
        token: str,
        now: float,
        expires_at: float,
        force: bool = False,
    ) -> tuple[bool, dict[str, Any] | None]:
        self.ensure_schema()
        # Expired rows can be replaced by anyone; deleting first keeps the
        # upsert condition simple while the unique key still serialises races.
        self.database.execute(
            "DELETE FROM edit_locks WHERE resource_type = ? AND resource_id = ?"
            " AND expires_at <= ?",
            (resource_type, resource_id, float(now)),
        )
        self.database.execute(
            "INSERT INTO edit_locks (resource_type, resource_id, tenant_id,"
            " user_id, user_name, token, heartbeat_at, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(resource_type, resource_id) DO UPDATE SET"
            " tenant_id = excluded.tenant_id, user_id = excluded.user_id,"
            " user_name = excluded.user_name,"
            # Keep the token stable for a holder that re-acquires its own lock,
            # otherwise a double click breaks the release path.
            " token = CASE WHEN edit_locks.user_id = excluded.user_id"
            " THEN edit_locks.token ELSE excluded.token END,"
            " heartbeat_at = excluded.heartbeat_at, expires_at = excluded.expires_at"
            " WHERE edit_locks.user_id = excluded.user_id"
            " OR edit_locks.expires_at <= ? OR ? = 1",
            (
                resource_type,
                resource_id,
                tenant_id or "",
                user_id or "",
                user_name or "",
                token,
                float(now),
                float(expires_at),
                float(now),
                1 if force else 0,
            ),
        )
        row = self.database.fetchone(
            "SELECT * FROM edit_locks WHERE resource_type = ? AND resource_id = ?",
            (resource_type, resource_id),
        )
        if row is None:
            return False, None
        stored = dict(row)
        return stored.get("token") == token, stored

    def renew_edit_lock(
        self,
        resource_type: str,
        resource_id: str,
        token: str,
        now: float,
        expires_at: float,
    ) -> bool:
        self.ensure_schema()
        if not token:
            return False
        self.database.execute(
            "UPDATE edit_locks SET heartbeat_at = ?, expires_at = ?"
            " WHERE resource_type = ? AND resource_id = ? AND token = ?"
            " AND expires_at > ?",
            (
                float(now),
                float(expires_at),
                resource_type,
                resource_id,
                token,
                float(now),
            ),
        )
        row = self.database.fetchone(
            "SELECT token FROM edit_locks WHERE resource_type = ? AND resource_id = ?",
            (resource_type, resource_id),
        )
        return bool(row is not None and str(row["token"] or "") == token)

    def delete_edit_lock(
        self, resource_type: str, resource_id: str, token: str
    ) -> bool:
        self.ensure_schema()
        self.database.execute(
            "DELETE FROM edit_locks WHERE resource_type = ? AND resource_id = ?"
            " AND token = ?",
            (resource_type, resource_id, token or ""),
        )
        return (
            self.database.fetchone(
                "SELECT resource_id FROM edit_locks"
                " WHERE resource_type = ? AND resource_id = ?",
                (resource_type, resource_id),
            )
            is None
        )

    def delete_edit_lock_for_user(
        self, resource_type: str, resource_id: str, user_id: str
    ) -> int:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT COUNT(*) AS total FROM edit_locks"
            " WHERE resource_type = ? AND resource_id = ? AND user_id = ?",
            (resource_type, resource_id, user_id or ""),
        )
        removed = int(row["total"] or 0) if row is not None else 0
        if removed:
            self.database.execute(
                "DELETE FROM edit_locks WHERE resource_type = ?"
                " AND resource_id = ? AND user_id = ?",
                (resource_type, resource_id, user_id or ""),
            )
        return removed

    def delete_expired_edit_locks(
        self, resource_type: str, resource_id: str, now: float
    ) -> None:
        self.ensure_schema()
        self.database.execute(
            "DELETE FROM edit_locks WHERE resource_type = ? AND resource_id = ?"
            " AND expires_at <= ?",
            (resource_type, resource_id, float(now)),
        )

    # -- legacy unit-lock API ---------------------------------------------

    def get_lock(self, unit_id: str) -> UnitLock | None:
        row = self.get_edit_lock("unit", unit_id)
        if row is None:
            return None
        return UnitLock(
            unit_id=str(row["resource_id"]),
            tenant_id=str(row["tenant_id"] or ""),
            user_id=str(row["user_id"] or ""),
            user_name=str(row["user_name"] or ""),
            token=str(row["token"] or ""),
            heartbeat_at=float(row["heartbeat_at"] or 0),
            expires_at=float(row["expires_at"] or 0),
        )

    def save_lock(self, lock: UnitLock) -> UnitLock:
        self.ensure_schema()
        self.database.execute(
            "INSERT INTO edit_locks (resource_type, resource_id, tenant_id,"
            " user_id, user_name, token, heartbeat_at, expires_at)"
            " VALUES ('unit', ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(resource_type, resource_id) DO UPDATE SET"
            " tenant_id = excluded.tenant_id, user_id = excluded.user_id,"
            " user_name = excluded.user_name, token = excluded.token,"
            " heartbeat_at = excluded.heartbeat_at, expires_at = excluded.expires_at",
            (
                lock.unit_id,
                lock.tenant_id,
                lock.user_id,
                lock.user_name,
                lock.token,
                lock.heartbeat_at,
                lock.expires_at,
            ),
        )
        return lock

    def delete_lock(self, unit_id: str) -> None:
        self.ensure_schema()
        self.database.execute(
            "DELETE FROM edit_locks WHERE resource_type = 'unit' AND resource_id = ?",
            (unit_id,),
        )
        try:
            self.database.execute(
                "DELETE FROM unit_locks WHERE unit_id = ?", (unit_id,)
            )
        except Exception:  # noqa: BLE001 - legacy table may be absent
            pass

    def delete_by_user(self, user_id: str) -> int:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT COUNT(*) AS total FROM edit_locks WHERE user_id = ?", (user_id,)
        )
        removed = int(row["total"] or 0) if row is not None else 0
        self.database.execute(
            "DELETE FROM edit_locks WHERE user_id = ?", (user_id,)
        )
        try:
            self.database.execute("DELETE FROM unit_locks WHERE user_id = ?", (user_id,))
        except Exception:  # noqa: BLE001
            pass
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
