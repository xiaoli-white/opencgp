from __future__ import annotations

from typing import Any

from app.ports.conversation_repository import ConversationRepository
from app.ports.lock_repository import LockRepository
from app.ports.provider_settings_repository import ProviderSettingsRepository
from app.ports.user_provider_repository import UserProviderRepository
from app.services.auth import AuthService
from app.services.errors import AuthRequiredError, UserDeleteForbiddenError


class AccountAdminService:
    def __init__(
        self,
        auth: AuthService,
        user_providers: UserProviderRepository,
        provider_settings: ProviderSettingsRepository,
        locks: LockRepository,
        conversations: ConversationRepository | None = None,
    ) -> None:
        self.auth = auth
        self.user_providers = user_providers
        self.provider_settings = provider_settings
        self.locks = locks
        self.conversations = conversations

    def update_user(
        self,
        user_id: str,
        display_name: str | None = None,
        email: str | None = None,
        status: str | None = None,
        role: str | None = None,
    ) -> Any:
        return self.auth.admin_update_user(
            user_id,
            display_name=display_name,
            email=email,
            status=status,
            role=role,
        )

    def reset_password(self, user_id: str, new_password: str) -> None:
        self.auth.set_password(user_id, new_password)

    def delete_user(self, actor_id: str, user_id: str) -> dict[str, Any]:
        if user_id and user_id == actor_id:
            raise UserDeleteForbiddenError("不能删除自己的账号")
        user = self.auth.get_user(user_id)
        if user is None:
            raise AuthRequiredError("用户不存在")
        memberships = self.auth.repository.list_memberships(user_id)
        dropped_tenants: list[str] = []
        for membership in memberships:
            if membership.role != "owner":
                continue
            if self.auth.repository.count_owners(membership.tenant_id) > 1:
                continue
            tenant = self.auth.repository.get_tenant(membership.tenant_id)
            if tenant is not None and tenant.kind == "personal":
                dropped_tenants.append(tenant.id)
                continue
            raise UserDeleteForbiddenError("不能删除租户里最后一个 owner")
        for tenant_id in dropped_tenants:
            self.auth.repository.delete_tenant(tenant_id)
        removed_memberships = self.auth.repository.delete_memberships_by_user(user_id)
        removed_providers = self.user_providers.delete_all_for_user(user_id)
        self.provider_settings.delete(user_id)
        removed_locks = self.locks.delete_by_user(user_id)
        self.auth.repository.delete_user(user_id)
        return {
            "user_id": user_id,
            "email": user.email,
            "deleted": {
                "memberships": removed_memberships,
                "user_providers": removed_providers,
                "locks": removed_locks,
                "personal_tenants": len(dropped_tenants),
            },
        }
