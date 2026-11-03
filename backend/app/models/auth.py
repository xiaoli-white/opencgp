from __future__ import annotations

from pydantic import BaseModel, Field

DEFAULT_TENANT_ID = "tenant_default"
DEFAULT_USER_ID = "user_local"
DEFAULT_USER_EMAIL = "local@studio"

ROLES = ("owner", "admin", "editor", "viewer")


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


class AuthContext(BaseModel):
    user: User
    tenant: Tenant
    role: str = "owner"
