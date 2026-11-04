from __future__ import annotations

from typing import Any, Protocol, Sequence, runtime_checkable

from app.models.citation import Citation
from app.models.longform import Longform, LongformVersion, OutlineSection


@runtime_checkable
class LongformRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def create(self, longform: Longform) -> Longform:
        ...

    def get(self, longform_id: str, tenant_id: str | None = None) -> Longform | None:
        ...

    def list(self, tenant_id: str | None = None, limit: int = 50) -> list[Longform]:
        ...

    def update(
        self,
        longform_id: str,
        outline: Sequence[OutlineSection] | None = None,
        content: str | None = None,
        status: str | None = None,
        last_mode: str | None = None,
        citations: Sequence[Citation] | None = None,
        title: str | None = None,
        profile: dict[str, Any] | None = None,
        target_words: int | None = None,
    ) -> Longform | None:
        ...

    def append_version(
        self,
        longform_id: str,
        content: str,
        outline: Sequence[OutlineSection] | None = None,
        citations: Sequence[Citation] | None = None,
        note: str = "",
        mode: str = "",
    ) -> tuple[Longform, LongformVersion] | None:
        ...

    def list_versions(self, longform_id: str) -> list[LongformVersion]:
        ...

    def get_version(self, longform_id: str, version: int) -> LongformVersion | None:
        ...

    def count_by_user(self, user_id: str) -> int:
        ...

    def transfer_by_user(
        self, user_id: str, target_user_id: str, tenant_ids: Sequence[str] = ()
    ) -> int:
        ...

    def delete(self, longform_id: str, tenant_id: str | None = None) -> bool:
        ...
