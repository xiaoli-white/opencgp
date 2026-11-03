from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.provider_setting import ProviderSetting


@runtime_checkable
class ProviderSettingsRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def get(self, user_id: str) -> ProviderSetting | None:
        ...

    def save(self, setting: ProviderSetting) -> ProviderSetting:
        ...

    def delete(self, user_id: str) -> None:
        ...

    def count_by_provider(self, provider_id: str) -> int:
        ...

    def clear_provider_reference(self, user_id: str, provider_id: str) -> None:
        ...
