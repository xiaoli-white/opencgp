from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_TENANT_ID = "tenant_default"
DEFAULT_USER_ID = "user_local"
DEFAULT_USER_EMAIL = "local@studio"

ROLES = ("owner", "admin", "editor", "viewer")
ALL_ACTIONS = ("read", "write", "review", "manage_members", "manage_quota")
SCOPE_ALL = "all"
SCOPE_ASSIGNED = "assigned"
SCOPES = (SCOPE_ALL, SCOPE_ASSIGNED)


class User(BaseModel):
    id: str
    email: str
    display_name: str = ""
    created_at: float = 0.0
    last_login_at: float = 0.0


class Tenant(BaseModel):
    id: str
    name: str
    slug: str = ""
    plan: str = "free"
    created_at: float = 0.0


class Membership(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    role: str = "viewer"
    created_at: float = 0.0
    user_email: str = ""
    user_display_name: str = ""


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
