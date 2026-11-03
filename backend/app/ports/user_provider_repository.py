from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.user_provider import UserProvider


@runtime_checkable
class UserProviderRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def list_providers(self, user_id: str) -> list[UserProvider]:
        ...

    def get_provider(self, user_id: str, provider_id: str) -> UserProvider | None:
        ...

    def save_provider(self, provider: UserProvider) -> UserProvider:
        ...

    def delete_provider(self, user_id: str, provider_id: str) -> bool:
        ...

    def clear_default(self, user_id: str, keep_id: str = "") -> None:
        ...

    def count_by_user(self, user_id: str) -> int:
        ...
