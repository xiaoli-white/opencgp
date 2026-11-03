from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.auth import Membership, Tenant, User


@runtime_checkable
class AuthRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def create_user(
        self,
        email: str,
        password_hash: str,
        display_name: str = "",
        user_id: str = "",
    ) -> User:
        ...

    def get_password_hash(self, user_id: str) -> str:
        ...

    def get_user(self, user_id: str) -> User | None:
        ...

    def get_user_by_email(self, email: str) -> User | None:
        ...

    def touch_login(self, user_id: str) -> None:
        ...

    def create_tenant(
        self, name: str, slug: str, plan: str = "free", tenant_id: str = ""
    ) -> Tenant:
        ...

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        ...

    def get_tenant_by_slug(self, slug: str) -> Tenant | None:
        ...

    def list_tenants(self) -> list[Tenant]:
        ...

    def add_membership(self, tenant_id: str, user_id: str, role: str) -> Membership:
        ...

    def get_membership(self, tenant_id: str, user_id: str) -> Membership | None:
        ...

    def list_memberships(self, user_id: str) -> list[Membership]:
        ...

    def list_members(self, tenant_id: str) -> list[Membership]:
        ...

    def update_membership_role(
        self, tenant_id: str, user_id: str, role: str
    ) -> Membership | None:
        ...

    def remove_membership(self, tenant_id: str, user_id: str) -> bool:
        ...

    def count_members(self, tenant_id: str) -> int:
        ...

    def count_owners(self, tenant_id: str) -> int:
        ...
