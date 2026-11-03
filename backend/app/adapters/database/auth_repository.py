from __future__ import annotations

import json
import time
import uuid
from typing import Any, Mapping, Sequence

from app.models.auth import CourseGrant, Membership, Role, Tenant, User
from app.ports.auth_repository import AuthRepository
from app.ports.database import Database

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS tenants (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        slug TEXT NOT NULL UNIQUE,
        plan TEXT NOT NULL DEFAULT 'free',
        created_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        display_name TEXT NOT NULL DEFAULT '',
        password_hash TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        last_login_at REAL NOT NULL DEFAULT 0
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
    CREATE TABLE IF NOT EXISTS course_grants (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        course_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        level TEXT NOT NULL DEFAULT 'read',
        created_at REAL NOT NULL,
        UNIQUE (course_id, user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_course_grants_course ON course_grants(course_id)",
    "CREATE INDEX IF NOT EXISTS idx_course_grants_user ON course_grants(tenant_id, user_id)",
)

COLUMN_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("courses", "tenant_id", "TEXT NOT NULL DEFAULT ''"),
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
        self._schema_ready = True

    def create_user(
        self,
        email: str,
        password_hash: str,
        display_name: str = "",
        user_id: str = "",
    ) -> User:
        self.ensure_schema()
        now = time.time()
        user = User(
            id=user_id or _new_id("user"),
            email=email.strip().lower(),
            display_name=display_name or email.split("@")[0],
            created_at=now,
            last_login_at=0.0,
        )
        self.database.execute(
            "INSERT INTO users (id, email, display_name, password_hash, created_at,"
            " last_login_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user.id, user.email, user.display_name, password_hash, now, 0.0),
        )
        return user

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
        self, name: str, slug: str, plan: str = "free", tenant_id: str = ""
    ) -> Tenant:
        self.ensure_schema()
        now = time.time()
        tenant = Tenant(
            id=tenant_id or _new_id("tenant"),
            name=name.strip(),
            slug=slug,
            plan=plan,
            created_at=now,
        )
        self.database.execute(
            "INSERT INTO tenants (id, name, slug, plan, created_at) VALUES (?, ?, ?, ?, ?)",
            (tenant.id, tenant.name, tenant.slug, tenant.plan, now),
        )
        return tenant

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
            "SELECT m.*, u.email AS user_email, u.display_name AS user_display_name"
            " FROM memberships m LEFT JOIN users u ON u.id = m.user_id"
            " WHERE m.tenant_id = ? AND m.user_id = ?",
            (tenant_id, user_id),
        )
        return _to_membership(row) if row else None

    def list_memberships(self, user_id: str) -> list[Membership]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT m.*, u.email AS user_email, u.display_name AS user_display_name"
            " FROM memberships m LEFT JOIN users u ON u.id = m.user_id"
            " WHERE m.user_id = ? ORDER BY m.created_at ASC",
            (user_id,),
        )
        return [_to_membership(row) for row in rows]

    def list_members(self, tenant_id: str) -> list[Membership]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT m.*, u.email AS user_email, u.display_name AS user_display_name"
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

    def list_grants(self, course_id: str) -> list[CourseGrant]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT g.*, u.email AS user_email, u.display_name AS user_display_name"
            " FROM course_grants g LEFT JOIN users u ON u.id = g.user_id"
            " WHERE g.course_id = ? ORDER BY g.created_at ASC",
            (course_id,),
        )
        return [_to_grant(row) for row in rows]

    def get_grant(self, course_id: str, user_id: str) -> CourseGrant | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT g.*, u.email AS user_email, u.display_name AS user_display_name"
            " FROM course_grants g LEFT JOIN users u ON u.id = g.user_id"
            " WHERE g.course_id = ? AND g.user_id = ?",
            (course_id, user_id),
        )
        return _to_grant(row) if row else None

    def list_user_grants(self, tenant_id: str, user_id: str) -> list[CourseGrant]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM course_grants WHERE tenant_id = ? AND user_id = ?",
            (tenant_id, user_id),
        )
        return [_to_grant(row) for row in rows]

    def replace_grants(
        self, tenant_id: str, course_id: str, grants: Sequence[tuple[str, str]]
    ) -> list[CourseGrant]:
        self.ensure_schema()
        self.database.execute(
            "DELETE FROM course_grants WHERE course_id = ?", (course_id,)
        )
        now = time.time()
        for user_id, level in grants:
            self.database.execute(
                "INSERT INTO course_grants (id, tenant_id, course_id, user_id, level,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (_new_id("grant"), tenant_id, course_id, user_id, level, now),
            )
        return self.list_grants(course_id)


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


def _to_grant(row: Mapping[str, Any]) -> CourseGrant:
    keys = set(row.keys())
    return CourseGrant(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        course_id=str(row["course_id"]),
        user_id=str(row["user_id"]),
        level=str(row["level"] or "read"),
        created_at=float(row["created_at"] or 0.0),
        user_email=str(row["user_email"] or "") if "user_email" in keys else "",
        user_display_name=(
            str(row["user_display_name"] or "") if "user_display_name" in keys else ""
        ),
    )


def _to_user(row: Mapping[str, Any]) -> User:
    return User(
        id=str(row["id"]),
        email=str(row["email"]),
        display_name=str(row["display_name"] or ""),
        created_at=float(row["created_at"] or 0.0),
        last_login_at=float(row["last_login_at"] or 0.0),
    )


def _to_tenant(row: Mapping[str, Any]) -> Tenant:
    return Tenant(
        id=str(row["id"]),
        name=str(row["name"]),
        slug=str(row["slug"] or ""),
        plan=str(row["plan"] or "free"),
        created_at=float(row["created_at"] or 0.0),
    )


def _to_membership(row: Mapping[str, Any]) -> Membership:
    keys = set(row.keys())
    return Membership(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        user_id=str(row["user_id"]),
        role=str(row["role"] or "viewer"),
        created_at=float(row["created_at"] or 0.0),
        user_email=str(row["user_email"] or "") if "user_email" in keys else "",
        user_display_name=(
            str(row["user_display_name"] or "") if "user_display_name" in keys else ""
        ),
    )
