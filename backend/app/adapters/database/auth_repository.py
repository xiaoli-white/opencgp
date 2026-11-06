from __future__ import annotations

import json
import time
import uuid
from typing import Any, Mapping, Sequence

from app.models.auth import (
    DEFAULT_TENANT_ID,
    SeriesGrant,
    PieceGrant,
    Membership,
    Role,
    Tenant,
    User,
    avatar_url_for,
)
from app.ports.auth_repository import AuthRepository
from app.ports.database import Database

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS tenants (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        plan TEXT NOT NULL DEFAULT 'free',
        kind TEXT NOT NULL DEFAULT 'team',
        owner_user_id TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL DEFAULT '',
        password_hash TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active',
        avatar_key TEXT NOT NULL DEFAULT '',
        deleted_at REAL NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        last_login_at REAL NOT NULL DEFAULT 0,
        updated_at REAL NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memberships (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'viewer',
        created_at REAL NOT NULL,
        UNIQUE (tenant_id, user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_memberships_tenant ON memberships(tenant_id)",
    """
    CREATE TABLE IF NOT EXISTS tenant_roles (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        key TEXT NOT NULL,
        name TEXT NOT NULL DEFAULT '',
        actions_json TEXT NOT NULL DEFAULT '[]',
        scope TEXT NOT NULL DEFAULT 'all',
        builtin INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        UNIQUE (tenant_id, key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_tenant_roles_tenant ON tenant_roles(tenant_id)",
    """
    CREATE TABLE IF NOT EXISTS series_grants (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        series_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        level TEXT NOT NULL DEFAULT 'read',
        created_at REAL NOT NULL,
        UNIQUE (series_id, user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_series_grants_series ON series_grants(series_id)",
    "CREATE INDEX IF NOT EXISTS idx_series_grants_user ON series_grants(tenant_id, user_id)",
    """
    CREATE TABLE IF NOT EXISTS piece_grants (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        piece_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        level TEXT NOT NULL DEFAULT 'read',
        created_at REAL NOT NULL,
        UNIQUE (piece_id, user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_piece_grants_lf ON piece_grants(piece_id)",
    "CREATE INDEX IF NOT EXISTS idx_piece_grants_user ON piece_grants(tenant_id, user_id)",
)

COLUMN_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("series", "tenant_id", "TEXT NOT NULL DEFAULT ''"),
    ("users", "status", "TEXT NOT NULL DEFAULT 'active'"),
    ("users", "avatar_key", "TEXT NOT NULL DEFAULT ''"),
    ("users", "updated_at", "REAL NOT NULL DEFAULT 0"),
    ("users", "deleted_at", "REAL NOT NULL DEFAULT 0"),
    ("tenants", "kind", "TEXT NOT NULL DEFAULT 'team'"),
    ("tenants", "owner_user_id", "TEXT NOT NULL DEFAULT ''"),
)


class DatabaseAuthRepository(AuthRepository):
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
            if not columns:
                continue
            if column not in columns:
                self.database.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        self.database.execute(
            "UPDATE tenants SET kind = 'system' WHERE id = ? AND kind != 'system'",
            (DEFAULT_TENANT_ID,),
        )
        self.database.execute(
            "UPDATE users SET updated_at = created_at WHERE updated_at = 0"
        )
        self._schema_ready = True

    def create_user(
        self,
        email: str,
        password_hash: str,
        display_name: str = "",
        user_id: str = "",
        status: str = "active",
    ) -> User:
        self.ensure_schema()
        now = time.time()
        user = User(
            id=user_id or _new_id("user"),
            email=email.strip().lower(),
            display_name=display_name or email.split("@")[0],
            status=status or "active",
            created_at=now,
            last_login_at=0.0,
            updated_at=now,
        )
        self.database.execute(
            "INSERT INTO users (id, email, display_name, password_hash, status,"
            " avatar_key, created_at, last_login_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user.id,
                user.email,
                user.display_name,
                password_hash,
                user.status,
                "",
                now,
                0.0,
                now,
            ),
        )
        return user

    def update_user(
        self,
        user_id: str,
        display_name: str | None = None,
        email: str | None = None,
        avatar_key: str | None = None,
        status: str | None = None,
    ) -> User | None:
        self.ensure_schema()
        current = self.get_user(user_id)
        if current is None:
            return None
        self.database.execute(
            "UPDATE users SET display_name = ?, email = ?, avatar_key = ?, status = ?,"
            " updated_at = ? WHERE id = ?",
            (
                current.display_name if display_name is None else display_name,
                current.email if email is None else email.strip().lower(),
                current.avatar_key if avatar_key is None else avatar_key,
                current.status if status is None else status,
                time.time(),
                user_id,
            ),
        )
        return self.get_user(user_id)

    def update_password_hash(self, user_id: str, password_hash: str) -> bool:
        self.ensure_schema()
        if self.get_user(user_id) is None:
            return False
        self.database.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (password_hash, time.time(), user_id),
        )
        return True

    def list_users(
        self,
        status: str = "",
        limit: int = 50,
        q: str = "",
        include_deleted: bool = False,
    ) -> list[User]:
        self.ensure_schema()
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        elif not include_deleted:
            clauses.append("status <> 'disabled' AND deleted_at = 0")
        keyword = (q or "").strip().lower()
        if keyword:
            clauses.append("(lower(email) LIKE ? OR lower(display_name) LIKE ?)")
            like = f"%{keyword}%"
            params.extend([like, like])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, int(limit)))
        rows = self.database.fetchall(
            f"SELECT * FROM users{where} ORDER BY created_at DESC LIMIT ?",
            tuple(params),
        )
        return [_to_user(row) for row in rows]

    def delete_user(self, user_id: str) -> bool:
        self.ensure_schema()
        if self.get_user(user_id) is None:
            return False
        self.database.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return True

    def soft_delete_user(
        self, user_id: str, email: str, deleted_at: float
    ) -> bool:
        self.ensure_schema()
        if self.get_user(user_id) is None:
            return False
        self.database.execute(
            "UPDATE users SET email = ?, status = 'disabled', deleted_at = ?,"
            " updated_at = ? WHERE id = ?",
            (email.strip().lower(), float(deleted_at), float(deleted_at), user_id),
        )
        return True

    def restore_user(self, user_id: str, email: str) -> User | None:
        self.ensure_schema()
        if self.get_user(user_id) is None:
            return None
        self.database.execute(
            "UPDATE users SET email = ?, status = 'active', deleted_at = 0,"
            " updated_at = ? WHERE id = ?",
            (email.strip().lower(), time.time(), user_id),
        )
        return self.get_user(user_id)

    def delete_memberships_by_user(self, user_id: str) -> int:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT COUNT(*) AS total FROM memberships WHERE user_id = ?", (user_id,)
        )
        removed = int(rows[0]["total"]) if rows and rows[0]["total"] is not None else 0
        self.database.execute("DELETE FROM memberships WHERE user_id = ?", (user_id,))
        self.database.execute("DELETE FROM series_grants WHERE user_id = ?", (user_id,))
        self.database.execute(
            "DELETE FROM piece_grants WHERE user_id = ?", (user_id,)
        )
        return removed

    def count_users(self, exclude_ids: Sequence[str] = ()) -> int:
        self.ensure_schema()
        excluded = [str(item) for item in exclude_ids if item]
        if not excluded:
            row = self.database.fetchone(
                "SELECT COUNT(1) AS n FROM users WHERE status <> 'disabled'"
            )
            return int(row["n"]) if row else 0
        placeholders = ", ".join("?" for _ in excluded)
        row = self.database.fetchone(
            f"SELECT COUNT(1) AS n FROM users"
            f" WHERE status <> 'disabled' AND id NOT IN ({placeholders})",
            tuple(excluded),
        )
        return int(row["n"]) if row else 0

    def get_user(self, user_id: str) -> User | None:
        self.ensure_schema()
        row = self.database.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        return _to_user(row) if row else None

    def get_user_by_email(self, email: str) -> User | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        )
        return _to_user(row) if row else None

    def get_user_by_email_any(self, email: str) -> User | None:
        self.ensure_schema()
        address = (email or "").strip().lower()
        row = self.database.fetchone(
            "SELECT * FROM users WHERE email = ? OR email LIKE ? LIMIT 1",
            (address, f"{address}__deleted__%"),
        )
        return _to_user(row) if row else None

    def get_password_hash(self, user_id: str) -> str:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        )
        return str(row["password_hash"]) if row else ""

    def touch_login(self, user_id: str) -> None:
        self.ensure_schema()
        self.database.execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?", (time.time(), user_id)
        )

    def create_tenant(
        self,
        name: str,
        slug: str,
        plan: str = "free",
        tenant_id: str = "",
        kind: str = "team",
        owner_user_id: str = "",
    ) -> Tenant:
        self.ensure_schema()
        now = time.time()
        tenant = Tenant(
            id=tenant_id or _new_id("tenant"),
            name=name.strip(),
            slug=slug,
            plan=plan,
            kind=kind or "team",
            owner_user_id=owner_user_id,
            created_at=now,
        )
        self.database.execute(
            "INSERT INTO tenants (id, name, slug, plan, kind, owner_user_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                tenant.id,
                tenant.name,
                tenant.slug,
                tenant.plan,
                tenant.kind,
                tenant.owner_user_id,
                now,
            ),
        )
        return tenant

    def update_tenant(
        self,
        tenant_id: str,
        name: str | None = None,
        kind: str | None = None,
        owner_user_id: str | None = None,
    ) -> Tenant | None:
        self.ensure_schema()
        current = self.get_tenant(tenant_id)
        if current is None:
            return None
        self.database.execute(
            "UPDATE tenants SET name = ?, kind = ?, owner_user_id = ? WHERE id = ?",
            (
                current.name if name is None else name.strip(),
                current.kind if kind is None else kind,
                current.owner_user_id if owner_user_id is None else owner_user_id,
                tenant_id,
            ),
        )
        return self.get_tenant(tenant_id)

    def delete_tenant(self, tenant_id: str) -> bool:
        self.ensure_schema()
        if self.get_tenant(tenant_id) is None:
            return False
        self.database.execute(
            "DELETE FROM memberships WHERE tenant_id = ?", (tenant_id,)
        )
        self.database.execute("DELETE FROM tenants WHERE id = ?", (tenant_id,))
        return True

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        self.ensure_schema()
        row = self.database.fetchone("SELECT * FROM tenants WHERE id = ?", (tenant_id,))
        return _to_tenant(row) if row else None

    def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        self.ensure_schema()
        row = self.database.fetchone("SELECT * FROM tenants WHERE slug = ?", (slug,))
        return _to_tenant(row) if row else None

    def list_tenants(self) -> list[Tenant]:
        self.ensure_schema()
        rows = self.database.fetchall("SELECT * FROM tenants ORDER BY created_at ASC")
        return [_to_tenant(row) for row in rows]

    def add_membership(self, tenant_id: str, user_id: str, role: str) -> Membership:
        self.ensure_schema()
        now = time.time()
        record = Membership(
            id=_new_id("membership"),
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            created_at=now,
        )
        self.database.execute(
            "INSERT INTO memberships (id, tenant_id, user_id, role, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (record.id, tenant_id, user_id, role, now),
        )
        return record

    def get_membership(self, tenant_id: str, user_id: str) -> Membership | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT m.*, u.email AS user_email, u.display_name AS user_display_name, u.avatar_key AS user_avatar_key"
            " FROM memberships m LEFT JOIN users u ON u.id = m.user_id"
            " WHERE m.tenant_id = ? AND m.user_id = ?",
            (tenant_id, user_id),
        )
        return _to_membership(row) if row else None

    def list_memberships(self, user_id: str) -> list[Membership]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT m.*, u.email AS user_email, u.display_name AS user_display_name, u.avatar_key AS user_avatar_key"
            " FROM memberships m LEFT JOIN users u ON u.id = m.user_id"
            " WHERE m.user_id = ? ORDER BY m.created_at ASC",
            (user_id,),
        )
        return [_to_membership(row) for row in rows]

    def list_members(self, tenant_id: str) -> list[Membership]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT m.*, u.email AS user_email, u.display_name AS user_display_name, u.avatar_key AS user_avatar_key"
            " FROM memberships m LEFT JOIN users u ON u.id = m.user_id"
            " WHERE m.tenant_id = ? ORDER BY m.created_at ASC",
            (tenant_id,),
        )
        return [_to_membership(row) for row in rows]

    def update_membership_role(
        self, tenant_id: str, user_id: str, role: str
    ) -> Membership | None:
        self.ensure_schema()
        membership = self.get_membership(tenant_id, user_id)
        if membership is None:
            return None
        self.database.execute(
            "UPDATE memberships SET role = ? WHERE tenant_id = ? AND user_id = ?",
            (role, tenant_id, user_id),
        )
        return self.get_membership(tenant_id, user_id)

    def remove_membership(self, tenant_id: str, user_id: str) -> bool:
        self.ensure_schema()
        membership = self.get_membership(tenant_id, user_id)
        if membership is None:
            return False
        self.database.execute(
            "DELETE FROM memberships WHERE tenant_id = ? AND user_id = ?",
            (tenant_id, user_id),
        )
        return True

    def count_members(self, tenant_id: str) -> int:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT COUNT(1) AS n FROM memberships WHERE tenant_id = ?", (tenant_id,)
        )
        return int(row["n"]) if row else 0

    def count_owners(self, tenant_id: str) -> int:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT COUNT(1) AS n FROM memberships WHERE tenant_id = ? AND role = 'owner'",
            (tenant_id,),
        )
        return int(row["n"]) if row else 0

    def create_role(
        self,
        tenant_id: str,
        key: str,
        name: str,
        actions: Sequence[str],
        scope: str = "all",
        builtin: bool = False,
    ) -> Role:
        self.ensure_schema()
        record = Role(
            id=_new_id("role"),
            tenant_id=tenant_id,
            key=key,
            name=name or key,
            actions=[str(item) for item in actions],
            scope=scope,
            builtin=builtin,
            created_at=time.time(),
        )
        self.database.execute(
            "INSERT INTO tenant_roles (id, tenant_id, key, name, actions_json, scope,"
            " builtin, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                tenant_id,
                record.key,
                record.name,
                json.dumps(record.actions),
                record.scope,
                1 if builtin else 0,
                record.created_at,
            ),
        )
        return record

    def get_role(self, tenant_id: str, key: str) -> Role | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM tenant_roles WHERE tenant_id = ? AND key = ?",
            (tenant_id, key),
        )
        return _to_role(row) if row else None

    def get_role_by_id(self, role_id: str) -> Role | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM tenant_roles WHERE id = ?", (role_id,)
        )
        return _to_role(row) if row else None

    def list_roles(self, tenant_id: str) -> list[Role]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM tenant_roles WHERE tenant_id = ? ORDER BY created_at ASC",
            (tenant_id,),
        )
        return [_to_role(row) for row in rows]

    def update_role(
        self,
        role_id: str,
        name: str | None = None,
        actions: Sequence[str] | None = None,
        scope: str | None = None,
    ) -> Role | None:
        self.ensure_schema()
        current = self.get_role_by_id(role_id)
        if current is None:
            return None
        next_name = current.name if name is None else name
        next_actions = current.actions if actions is None else [str(i) for i in actions]
        next_scope = current.scope if scope is None else scope
        self.database.execute(
            "UPDATE tenant_roles SET name = ?, actions_json = ?, scope = ? WHERE id = ?",
            (next_name, json.dumps(next_actions), next_scope, role_id),
        )
        return self.get_role_by_id(role_id)

    def delete_role(self, role_id: str) -> bool:
        self.ensure_schema()
        current = self.get_role_by_id(role_id)
        if current is None:
            return False
        self.database.execute("DELETE FROM tenant_roles WHERE id = ?", (role_id,))
        return True

    def count_role_members(self, tenant_id: str, key: str) -> int:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT COUNT(1) AS n FROM memberships WHERE tenant_id = ? AND role = ?",
            (tenant_id, key),
        )
        return int(row["n"]) if row else 0

    def list_grants(self, series_id: str) -> list[SeriesGrant]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT g.*, u.email AS user_email, u.display_name AS user_display_name, u.avatar_key AS user_avatar_key"
            " FROM series_grants g LEFT JOIN users u ON u.id = g.user_id"
            " WHERE g.series_id = ? ORDER BY g.created_at ASC",
            (series_id,),
        )
        return [_to_grant(row) for row in rows]

    def get_grant(self, series_id: str, user_id: str) -> SeriesGrant | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT g.*, u.email AS user_email, u.display_name AS user_display_name, u.avatar_key AS user_avatar_key"
            " FROM series_grants g LEFT JOIN users u ON u.id = g.user_id"
            " WHERE g.series_id = ? AND g.user_id = ?",
            (series_id, user_id),
        )
        return _to_grant(row) if row else None

    def list_user_grants(self, tenant_id: str, user_id: str) -> list[SeriesGrant]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM series_grants WHERE tenant_id = ? AND user_id = ?",
            (tenant_id, user_id),
        )
        return [_to_grant(row) for row in rows]

    def replace_grants(
        self, tenant_id: str, series_id: str, grants: Sequence[tuple[str, str]]
    ) -> list[SeriesGrant]:
        self.ensure_schema()
        self.database.execute(
            "DELETE FROM series_grants WHERE series_id = ?", (series_id,)
        )
        now = time.time()
        for user_id, level in grants:
            self.database.execute(
                "INSERT INTO series_grants (id, tenant_id, series_id, user_id, level,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (_new_id("grant"), tenant_id, series_id, user_id, level, now),
            )
        return self.list_grants(series_id)

    def list_piece_grants(self, piece_id: str) -> list[PieceGrant]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT g.*, u.email AS user_email, u.display_name AS user_display_name"
            " FROM piece_grants g LEFT JOIN users u ON u.id = g.user_id"
            " WHERE g.piece_id = ? ORDER BY g.created_at ASC",
            (piece_id,),
        )
        return [_to_piece_grant(row) for row in rows]

    def get_piece_grant(
        self, piece_id: str, user_id: str
    ) -> PieceGrant | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT g.*, u.email AS user_email, u.display_name AS user_display_name"
            " FROM piece_grants g LEFT JOIN users u ON u.id = g.user_id"
            " WHERE g.piece_id = ? AND g.user_id = ?",
            (piece_id, user_id),
        )
        return _to_piece_grant(row) if row else None

    def list_user_piece_grants(
        self, tenant_id: str, user_id: str
    ) -> list[PieceGrant]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM piece_grants WHERE tenant_id = ? AND user_id = ?",
            (tenant_id, user_id),
        )
        return [_to_piece_grant(row) for row in rows]

    def replace_piece_grants(
        self, tenant_id: str, piece_id: str, grants: Sequence[tuple[str, str]]
    ) -> list[PieceGrant]:
        self.ensure_schema()
        self.database.execute(
            "DELETE FROM piece_grants WHERE piece_id = ?", (piece_id,)
        )
        now = time.time()
        for user_id, level in grants:
            self.database.execute(
                "INSERT INTO piece_grants (id, tenant_id, piece_id, user_id,"
                " level, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    _new_id("lfgrant"),
                    tenant_id,
                    piece_id,
                    user_id,
                    level,
                    now,
                ),
            )
        return self.list_piece_grants(piece_id)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _to_role(row: Mapping[str, Any]) -> Role:
    try:
        actions = json.loads(str(row["actions_json"] or "[]"))
    except (ValueError, TypeError):
        actions = []
    if not isinstance(actions, list):
        actions = []
    return Role(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        key=str(row["key"]),
        name=str(row["name"] or ""),
        actions=[str(item) for item in actions],
        scope=str(row["scope"] or "all"),
        builtin=bool(int(row["builtin"] or 0)),
        created_at=float(row["created_at"] or 0.0),
    )


def _to_grant(row: Mapping[str, Any]) -> SeriesGrant:
    keys = set(row.keys())
    return SeriesGrant(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        series_id=str(row["series_id"]),
        user_id=str(row["user_id"]),
        level=str(row["level"] or "read"),
        created_at=float(row["created_at"] or 0.0),
        user_email=str(row["user_email"] or "") if "user_email" in keys else "",
        user_display_name=(
            str(row["user_display_name"] or "") if "user_display_name" in keys else ""
        ),
    )


def _to_piece_grant(row: Mapping[str, Any]) -> PieceGrant:
    keys = set(row.keys())
    return PieceGrant(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        piece_id=str(row["piece_id"]),
        user_id=str(row["user_id"]),
        level=str(row["level"] or "read"),
        created_at=float(row["created_at"] or 0.0),
        user_email=str(row["user_email"] or "") if "user_email" in keys else "",
        user_display_name=(
            str(row["user_display_name"] or "") if "user_display_name" in keys else ""
        ),
    )


def _to_user(row: Mapping[str, Any]) -> User:
    keys = set(row.keys())
    return User(
        id=str(row["id"]),
        email=str(row["email"]),
        display_name=str(row["display_name"] or ""),
        status=str(row["status"] or "active") if "status" in keys else "active",
        avatar_key=str(row["avatar_key"] or "") if "avatar_key" in keys else "",
        deleted_at=float(row["deleted_at"] or 0) if "deleted_at" in keys else 0.0,
        created_at=float(row["created_at"] or 0.0),
        last_login_at=float(row["last_login_at"] or 0.0),
        updated_at=float(row["updated_at"] or 0.0) if "updated_at" in keys else 0.0,
    )


def _to_tenant(row: Mapping[str, Any]) -> Tenant:
    keys = set(row.keys())
    return Tenant(
        id=str(row["id"]),
        name=str(row["name"]),
        slug=str(row["slug"] or ""),
        plan=str(row["plan"] or "free"),
        kind=str(row["kind"] or "team") if "kind" in keys else "team",
        owner_user_id=(
            str(row["owner_user_id"] or "") if "owner_user_id" in keys else ""
        ),
        created_at=float(row["created_at"] or 0.0),
    )


def _to_membership(row: Mapping[str, Any]) -> Membership:
    keys = set(row.keys())
    avatar_key = str(row["user_avatar_key"] or "") if "user_avatar_key" in keys else ""
    user_id = str(row["user_id"])
    return Membership(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        user_id=user_id,
        role=str(row["role"] or "viewer"),
        created_at=float(row["created_at"] or 0.0),
        user_email=str(row["user_email"] or "") if "user_email" in keys else "",
        user_display_name=(
            str(row["user_display_name"] or "") if "user_display_name" in keys else ""
        ),
        avatar_url=avatar_url_for(user_id, avatar_key),
    )
