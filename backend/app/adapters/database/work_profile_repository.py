from __future__ import annotations

import json
import time
import uuid
from typing import Any, Mapping, Sequence

from app.models.work_profile import (
    ProfileShare,
    ProfileSpec,
    WorkProfile,
    normalize_spec,
)
from app.ports.database import Database
from app.ports.work_profile_repository import WorkProfileRepository

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS work_profiles (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        owner_user_id TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        spec_json TEXT NOT NULL DEFAULT '{}',
        is_builtin INTEGER NOT NULL DEFAULT 0,
        is_shared INTEGER NOT NULL DEFAULT 0,
        version INTEGER NOT NULL DEFAULT 1,
        created_at REAL NOT NULL DEFAULT 0,
        updated_at REAL NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_work_profiles_tenant ON work_profiles(tenant_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_work_profiles_owner ON work_profiles(owner_user_id)",
    """
    CREATE TABLE IF NOT EXISTS profile_shares (
        id TEXT PRIMARY KEY,
        profile_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        level TEXT NOT NULL DEFAULT 'read',
        created_at REAL NOT NULL DEFAULT 0,
        UNIQUE (profile_id, user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_profile_shares_user ON profile_shares(user_id)",
)

SELECT_PROFILE = (
    "SELECT p.*, u.display_name AS owner_name FROM work_profiles p"
    " LEFT JOIN users u ON u.id = p.owner_user_id"
)


def _load_spec(raw: Any) -> ProfileSpec:
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        parsed = {}
    spec, _errors, _warnings = normalize_spec(parsed if isinstance(parsed, dict) else {})
    return spec


def _to_profile(row: Mapping[str, Any]) -> WorkProfile:
    keys = set(row.keys())
    spec = _load_spec(row["spec_json"])
    return WorkProfile(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"] or ""),
        owner_user_id=str(row["owner_user_id"] or ""),
        name=str(row["name"] or ""),
        description=str(row["description"] or ""),
        spec=spec,
        is_builtin=bool(row["is_builtin"]),
        is_shared=bool(row["is_shared"]),
        version=int(row["version"] or 0),
        created_at=float(row["created_at"] or 0.0),
        updated_at=float(row["updated_at"] or 0.0),
        owner_name=str(row["owner_name"] or "") if "owner_name" in keys else "",
    )


def _to_share(row: Mapping[str, Any]) -> ProfileShare:
    keys = set(row.keys())
    return ProfileShare(
        id=str(row["id"]),
        profile_id=str(row["profile_id"]),
        user_id=str(row["user_id"]),
        level=str(row["level"] or "read"),
        created_at=float(row["created_at"] or 0.0),
        user_email=str(row["user_email"] or "") if "user_email" in keys else "",
        user_display_name=(
            str(row["user_display_name"] or "") if "user_display_name" in keys else ""
        ),
    )


class DatabaseWorkProfileRepository(WorkProfileRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        self._schema_ready = True

    def create(self, profile: WorkProfile) -> WorkProfile:
        self.ensure_schema()
        now = time.time()
        item = profile.model_copy(
            update={
                "id": profile.id or f"profile_{uuid.uuid4().hex[:16]}",
                "created_at": profile.created_at or now,
                "updated_at": now,
                "version": max(1, int(profile.version or 1)),
            }
        )
        self.database.execute(
            "INSERT INTO work_profiles (id, tenant_id, owner_user_id, name, description,"
            " spec_json, is_builtin, is_shared, version, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id,
                item.tenant_id,
                item.owner_user_id,
                item.name,
                item.description,
                json.dumps(item.spec.model_dump(), ensure_ascii=False),
                1 if item.is_builtin else 0,
                1 if item.is_shared else 0,
                int(item.version),
                item.created_at,
                item.updated_at,
            ),
        )
        created = self.get(item.id)
        return created or item

    def get(self, profile_id: str) -> WorkProfile | None:
        self.ensure_schema()
        row = self.database.fetchone(
            f"{SELECT_PROFILE} WHERE p.id = ?", (profile_id,)
        )
        if row is None:
            return None
        return _to_profile(row)

    def list_visible(self, tenant_id: str, user_id: str) -> list[WorkProfile]:
        self.ensure_schema()
        rows = self.database.fetchall(
            f"{SELECT_PROFILE} WHERE p.is_builtin = 1"
            " OR (p.tenant_id = ? AND (p.owner_user_id = ? OR p.is_shared = 1))"
            " OR p.id IN (SELECT profile_id FROM profile_shares WHERE user_id = ?)"
            " ORDER BY p.is_builtin DESC, p.updated_at DESC",
            (tenant_id, user_id, user_id),
        )
        return [_to_profile(row) for row in rows]

    def list_builtin(self) -> list[WorkProfile]:
        self.ensure_schema()
        rows = self.database.fetchall(
            f"{SELECT_PROFILE} WHERE p.is_builtin = 1 ORDER BY p.created_at ASC"
        )
        return [_to_profile(row) for row in rows]

    def update(
        self,
        profile_id: str,
        name: str | None = None,
        description: str | None = None,
        spec: ProfileSpec | None = None,
        is_shared: bool | None = None,
        bump_version: bool = True,
    ) -> WorkProfile | None:
        self.ensure_schema()
        current = self.get(profile_id)
        if current is None:
            return None
        spec_payload = (
            json.dumps(spec.model_dump(), ensure_ascii=False)
            if spec is not None
            else json.dumps(current.spec.model_dump(), ensure_ascii=False)
        )
        version = current.version + 1 if bump_version else current.version
        self.database.execute(
            "UPDATE work_profiles SET name = ?, description = ?, spec_json = ?,"
            " is_shared = ?, version = ?, updated_at = ? WHERE id = ?",
            (
                current.name if name is None else name,
                current.description if description is None else description,
                spec_payload,
                1 if (current.is_shared if is_shared is None else is_shared) else 0,
                int(version),
                time.time(),
                profile_id,
            ),
        )
        return self.get(profile_id)

    def delete(self, profile_id: str) -> bool:
        self.ensure_schema()
        if self.get(profile_id) is None:
            return False
        self.database.execute("DELETE FROM profile_shares WHERE profile_id = ?", (profile_id,))
        self.database.execute("DELETE FROM work_profiles WHERE id = ?", (profile_id,))
        return True

    def count_usage(self, profile_id: str) -> int:
        self.ensure_schema()
        total = 0
        for table in ("courses", "longforms"):
            if not self._table_exists(table):
                continue
            row = self.database.fetchone(
                f"SELECT COUNT(*) AS total FROM {table} WHERE profile_id = ?",
                (profile_id,),
            )
            if row is not None:
                total += int(row["total"] or 0)
        return total

    def list_shares(self, profile_id: str) -> list[ProfileShare]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT s.*, u.email AS user_email, u.display_name AS user_display_name"
            " FROM profile_shares s LEFT JOIN users u ON u.id = s.user_id"
            " WHERE s.profile_id = ? ORDER BY s.created_at ASC",
            (profile_id,),
        )
        return [_to_share(row) for row in rows]

    def get_share(self, profile_id: str, user_id: str) -> ProfileShare | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT s.*, u.email AS user_email, u.display_name AS user_display_name"
            " FROM profile_shares s LEFT JOIN users u ON u.id = s.user_id"
            " WHERE s.profile_id = ? AND s.user_id = ?",
            (profile_id, user_id),
        )
        if row is None:
            return None
        return _to_share(row)

    def replace_shares(
        self, profile_id: str, items: Sequence[tuple[str, str]]
    ) -> list[ProfileShare]:
        self.ensure_schema()
        self.database.execute("DELETE FROM profile_shares WHERE profile_id = ?", (profile_id,))
        now = time.time()
        seen: set[str] = set()
        for user_id, level in items:
            if not user_id or user_id in seen:
                continue
            seen.add(user_id)
            self.database.execute(
                "INSERT INTO profile_shares (id, profile_id, user_id, level, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (f"pshare_{uuid.uuid4().hex[:16]}", profile_id, user_id, level, now),
            )
        return self.list_shares(profile_id)

    def _table_exists(self, table: str) -> bool:
        row = self.database.fetchone(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        )
        return row is not None
