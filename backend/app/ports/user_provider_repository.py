from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from app.models.user_provider import ProviderShare, UserProvider


@runtime_checkable
class UserProviderRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def list_providers(self, user_id: str) -> list[UserProvider]:
        ...

    def get_provider(self, user_id: str, provider_id: str) -> UserProvider | None:
        ...

    def get_provider_any(self, provider_id: str) -> UserProvider | None:
        ...

    def save_provider(self, provider: UserProvider) -> UserProvider:
        ...

    def delete_provider(self, user_id: str, provider_id: str) -> bool:
        ...

    def clear_default(self, user_id: str, keep_id: str = "") -> None:
        ...

    def count_by_user(self, user_id: str) -> int:
        ...

    def list_shares(self, provider_id: str) -> list[ProviderShare]:
        ...

    def get_share(self, provider_id: str, user_id: str) -> ProviderShare | None:
        ...

    def list_shared_with(self, user_id: str) -> list[ProviderShare]:
        ...

    def replace_shares(
        self, provider_id: str, owner_user_id: str, shares: Sequence[tuple[str, str]]
    ) -> list[ProviderShare]:
        ...

    def delete_shares(self, provider_id: str) -> bool:
        ...
