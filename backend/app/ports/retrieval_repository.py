from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.retrieval import RetrievalProvider, RetrievalSetting


@runtime_checkable
class RetrievalRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def list_providers(
        self, tenant_id: str, user_id: str, kind: str = ""
    ) -> list[RetrievalProvider]:
        ...

    def get_provider(
        self, tenant_id: str, user_id: str, provider_id: str
    ) -> RetrievalProvider | None:
        ...

    def get_provider_any(self, provider_id: str) -> RetrievalProvider | None:
        ...

    def find_default(
        self, tenant_id: str, user_id: str, kind: str
    ) -> RetrievalProvider | None:
        ...

    def save_provider(self, provider: RetrievalProvider) -> RetrievalProvider:
        ...

    def delete_provider(
        self, tenant_id: str, user_id: str, provider_id: str
    ) -> bool:
        ...

    def clear_defaults(
        self, tenant_id: str | None, user_id: str, kind: str, keep_id: str = ""
    ) -> None:
        ...

    def get_setting(
        self, tenant_id: str, user_id: str, scope: str
    ) -> RetrievalSetting | None:
        ...

    def save_setting(self, setting: RetrievalSetting) -> RetrievalSetting:
        ...


__all__ = ["RetrievalRepository"]
