from __future__ import annotations

import time
from typing import Any

from app.models.auth import DELETED_EMAIL_MARKER, USER_STATUS_ACTIVE, User
from app.ports.conversation_repository import ConversationRepository
from app.ports.series_repository import SeriesRepository
from app.ports.lock_repository import LockRepository
from app.ports.piece_repository import PieceRepository
from app.ports.provider_settings_repository import ProviderSettingsRepository
from app.ports.user_provider_repository import UserProviderRepository
from app.services.auth import AuthService
from app.services.errors import (
    AuthRequiredError,
    UserDeleteForbiddenError,
    UserHasWorksError,
)


class AccountAdminService:
    def __init__(
        self,
        auth: AuthService,
        user_providers: UserProviderRepository,
        provider_settings: ProviderSettingsRepository,
        locks: LockRepository,
        conversations: ConversationRepository | None = None,
        series: SeriesRepository | None = None,
        pieces: PieceRepository | None = None,
    ) -> None:
        self.auth = auth
        self.user_providers = user_providers
        self.provider_settings = provider_settings
        self.locks = locks
        self.conversations = conversations
        self.series = series
        self.pieces = pieces

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

    def count_works(self, user_id: str) -> int:
        total = 0
        if self.series is not None:
            total += int(self.series.count_by_user(user_id))
        if self.pieces is not None:
            total += int(self.pieces.count_by_user(user_id))
        return total

    def delete_user(
        self,
        actor_id: str,
        user_id: str,
        transfer_to_user_id: str = "",
        force: bool = False,
    ) -> dict[str, Any]:
        if user_id and user_id == actor_id:
            raise UserDeleteForbiddenError("you cannot delete your own account")
        user = self.auth.get_user(user_id)
        if user is None:
            raise AuthRequiredError("user not found")
        if float(user.deleted_at or 0) > 0:
            raise AuthRequiredError("the user has been deleted")
        target = self._resolve_target(user_id, (transfer_to_user_id or "").strip())
        works = self.count_works(user_id)
        if target is None and works > 0:
            raise UserHasWorksError(
                f"this user still owns {works} works; specify transfer_to_user_id"
            )
        memberships = self.auth.repository.list_memberships(user_id)
        personal_tenants: list[str] = []
        forced_tenants: list[str] = []
        for membership in memberships:
            if membership.role != "owner":
                continue
            if self.auth.repository.count_owners(membership.tenant_id) > 1:
                continue
            tenant = self.auth.repository.get_tenant(membership.tenant_id)
            if tenant is None:
                continue
            if tenant.kind == "personal":
                personal_tenants.append(tenant.id)
                continue
            if force and not tenant.is_system():
                forced_tenants.append(tenant.id)
                continue
            raise UserDeleteForbiddenError("you cannot delete the last owner of a tenant")
        moved_series = 0
        moved_pieces = 0
        moved_providers = 0
        if target is not None:
            if self.series is not None:
                moved_series = self.series.transfer_by_user(user_id, target.id)
            if self.pieces is not None:
                moved_pieces = self.pieces.transfer_by_user(user_id, target.id)
            moved_providers = self.user_providers.reassign_user(user_id, target.id)
            self._transfer_settings(user_id, target.id)
            for tenant_id in personal_tenants:
                self._handover_tenant(tenant_id, target.id)
        for tenant_id in forced_tenants:
            self.auth.repository.delete_tenant(tenant_id)
        if target is None:
            for tenant_id in personal_tenants:
                self.auth.repository.delete_tenant(tenant_id)
        removed_memberships = self.auth.repository.delete_memberships_by_user(user_id)
        if target is None:
            removed_providers = self.user_providers.delete_all_for_user(user_id)
            self.provider_settings.delete(user_id)
        else:
            removed_providers = moved_providers
        removed_locks = self.locks.delete_by_user(user_id)
        now = time.time()
        self.auth.repository.soft_delete_user(
            user_id, _deleted_email(user.email, now), now
        )
        return {
            "user_id": user_id,
            "email": user.email,
            "deleted": {
                "soft": True,
                "memberships": removed_memberships,
                "user_providers": removed_providers,
                "locks": removed_locks,
                "personal_tenants": len(personal_tenants) + len(forced_tenants),
                "transferred": {
                    "to_user_id": target.id if target else "",
                    "series": moved_series,
                    "pieces": moved_pieces,
                },
            },
        }

    def restore_user(self, user_id: str) -> dict[str, Any]:
        user = self.auth.get_user(user_id)
        if user is None:
            raise AuthRequiredError("user not found")
        restored_email = _restored_email(user.email)
        taken = self.auth.repository.get_user_by_email(restored_email)
        if taken is not None and taken.id != user_id:
            restored_email = user.email
            note = "email already taken; keeping the email suffix from when the account was disabled"
        else:
            note = ""
        updated = self.auth.repository.restore_user(user_id, restored_email)
        if updated is None:
            raise AuthRequiredError("user not found")
        return {
            "user": updated,
            "email_restored": restored_email == _restored_email(user.email),
            "note": note,
            "status": updated.status or USER_STATUS_ACTIVE,
        }

    def _resolve_target(self, user_id: str, transfer_to_user_id: str) -> User | None:
        if not transfer_to_user_id:
            return None
        if transfer_to_user_id == user_id:
            raise UserDeleteForbiddenError("works cannot be transferred to the deleted user itself")
        target = self.auth.get_user(transfer_to_user_id)
        if target is None or float(target.deleted_at or 0) > 0:
            raise UserDeleteForbiddenError("target user not found")
        return target

    def _handover_tenant(self, tenant_id: str, target_user_id: str) -> None:
        if self.auth.repository.get_membership(tenant_id, target_user_id) is None:
            self.auth.repository.add_membership(tenant_id, target_user_id, "owner")
        else:
            self.auth.repository.update_membership_role(
                tenant_id, target_user_id, "owner"
            )
        self.auth.repository.update_tenant(tenant_id, owner_user_id=target_user_id)

    def _transfer_settings(self, user_id: str, target_user_id: str) -> None:
        source = self.provider_settings.get(user_id)
        if source is None:
            return
        if self.provider_settings.get(target_user_id) is None:
            self.provider_settings.save(
                source.model_copy(update={"user_id": target_user_id})
            )
        self.provider_settings.delete(user_id)


def _deleted_email(email: str, now: float) -> str:
    base = (email or "").split(DELETED_EMAIL_MARKER, 1)[0]
    return f"{base}{DELETED_EMAIL_MARKER}{int(now)}"


def _restored_email(email: str) -> str:
    return (email or "").split(DELETED_EMAIL_MARKER, 1)[0]
