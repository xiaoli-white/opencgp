from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from app.models.work_profile import ProfileShare, ProfileSpec, WorkProfile


@runtime_checkable
class WorkProfileRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def create(self, profile: WorkProfile) -> WorkProfile:
        ...

    def get(self, profile_id: str) -> WorkProfile | None:
        ...

    def list_visible(self, tenant_id: str, user_id: str) -> list[WorkProfile]:
        ...

    def list_builtin(self) -> list[WorkProfile]:
        ...

    def update(
        self,
        profile_id: str,
        name: str | None = None,
        description: str | None = None,
        spec: ProfileSpec | None = None,
        is_shared: bool | None = None,
        bump_version: bool = True,
    ) -> WorkProfile | None:
        ...

    def delete(self, profile_id: str) -> bool:
        ...

    def count_usage(self, profile_id: str) -> int:
        ...

    def list_shares(self, profile_id: str) -> list[ProfileShare]:
        ...

    def get_share(self, profile_id: str, user_id: str) -> ProfileShare | None:
        ...

    def replace_shares(
        self, profile_id: str, items: Sequence[tuple[str, str]]
    ) -> list[ProfileShare]:
        ...
