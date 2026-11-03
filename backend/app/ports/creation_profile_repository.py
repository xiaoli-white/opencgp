from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.creation_profile import CreationProfile


@runtime_checkable
class CreationProfileRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def create(self, profile: CreationProfile) -> CreationProfile:
        ...

    def get(self, profile_id: str, tenant_id: str | None = None) -> CreationProfile | None:
        ...

    def list_visible(self, tenant_id: str, user_id: str) -> list[CreationProfile]:
        ...

    def update(
        self,
        profile_id: str,
        name: str | None = None,
        genre: str | None = None,
        tone: str | None = None,
        audience: str | None = None,
        pov: str | None = None,
        citation_policy: str | None = None,
        target_words: int | None = None,
        is_shared: bool | None = None,
    ) -> CreationProfile | None:
        ...

    def delete(self, profile_id: str, tenant_id: str | None = None) -> bool:
        ...
