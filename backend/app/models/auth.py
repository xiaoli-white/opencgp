from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_TENANT_ID = "tenant_default"
DEFAULT_USER_ID = "user_local"
DEFAULT_USER_EMAIL = "local@studio"

USER_STATUS_ACTIVE = "active"
USER_STATUS_PENDING = "pending"
USER_STATUS_REJECTED = "rejected"
USER_STATUSES = (USER_STATUS_PENDING, USER_STATUS_ACTIVE, USER_STATUS_REJECTED)

TENANT_KIND_SYSTEM = "system"
TENANT_KIND_PERSONAL = "personal"
TENANT_KIND_TEAM = "team"
TENANT_KINDS = (TENANT_KIND_SYSTEM, TENANT_KIND_PERSONAL, TENANT_KIND_TEAM)
CREATABLE_TENANT_KINDS = (TENANT_KIND_PERSONAL, TENANT_KIND_TEAM)

ROLES = ("owner", "admin", "editor", "viewer")
ALL_ACTIONS = (
    "read",
    "write",
    "review",
    "manage_members",
    "manage_quota",
    "manage_server",
)
SCOPE_ALL = "all"
SCOPE_ASSIGNED = "assigned"
SCOPES = (SCOPE_ALL, SCOPE_ASSIGNED)


class User(BaseModel):
    id: str
    email: str
    display_name: str = ""
    status: str = USER_STATUS_ACTIVE
    avatar_key: str = ""
    created_at: float = 0.0
    last_login_at: float = 0.0
    updated_at: float = 0.0

    def avatar_url(self) -> str:
        return avatar_url_for(self.id, self.avatar_key)


class Tenant(BaseModel):
    id: str
    name: str
    slug: str = ""
    plan: str = "free"
    kind: str = TENANT_KIND_TEAM
    owner_user_id: str = ""
    member_count: int = 0
    created_at: float = 0.0

    def is_system(self) -> bool:
        return self.kind == TENANT_KIND_SYSTEM


class Membership(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    role: str = "viewer"
    created_at: float = 0.0
    user_email: str = ""
    user_display_name: str = ""
    avatar_url: str = ""


def avatar_url_for(user_id: str, avatar_key: str) -> str:
    if not avatar_key:
        return ""
    return f"/api/v1/users/{user_id}/avatar"


class Role(BaseModel):
    id: str = ""
    tenant_id: str = ""
    key: str = "viewer"
    name: str = ""
    actions: list[str] = Field(default_factory=list)
    scope: str = SCOPE_ALL
    builtin: bool = False
    created_at: float = 0.0


class CourseGrant(BaseModel):
    id: str = ""
    tenant_id: str = ""
    course_id: str = ""
    user_id: str = ""
    level: str = "read"
    created_at: float = 0.0
    user_email: str = ""
    user_display_name: str = ""


class LongformGrant(BaseModel):
    id: str = ""
    tenant_id: str = ""
    longform_id: str = ""
    user_id: str = ""
    level: str = "read"
    created_at: float = 0.0
    user_email: str = ""
    user_display_name: str = ""


class AuthContext(BaseModel):
    user: User
    tenant: Tenant
    role: str = "owner"
    role_key: str = "owner"
    role_name: str = ""
    actions: set[str] = Field(default_factory=lambda: set(ALL_ACTIONS))
    scope: str = SCOPE_ALL

    def can(self, action: str) -> bool:
        return action in self.actions

    def role_payload(self) -> dict:
        return {
            "key": self.role_key or self.role,
            "name": self.role_name or self.role_key or self.role,
            "actions": sorted(self.actions),
            "scope": self.scope or SCOPE_ALL,
        }
