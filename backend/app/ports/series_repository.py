"""Course document persistence port (SeriesRepository).

Repository interface for courses / chapters / chapter versions. Business code
(services, API) depends only on this protocol; the concrete SQL dialect and
driver are implemented by the adapter and assembled by the container from config.

Conventions:
- Version numbers start at 1 and increase monotonically, unique within one ``unit_id``.
- Every content change (generation, rollback) must append a new ``UnitVersion``;
  history is never overwritten.
- Rollback does not delete history; it appends a new version with the target
  version's content (similar to git revert).
- Each version records the generation mode ``mode`` (``strict`` for strictly cited
  content / ``loose`` for free-form LLM writing / empty string for a manual draft);
  ``units.last_mode`` follows the most recent generation mode.
- Return ``None`` when an entity is not found; the caller decides the error semantics.
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence, runtime_checkable

from app.models.citation import Citation
from app.models.series import Series, Unit, UnitVersion


@runtime_checkable
class SeriesRepository(Protocol):
    def create_series(
        self,
        title: str,
        subtitle: str = "",
        audience: str = "",
        difficulty: str = "intermediate",
        language: str = "zh",
        tenant_id: str = "",
        user_id: str = "",
        brief: str = "",
    ) -> Series:
        ...

    def get_series(self, series_id: str, tenant_id: str | None = None) -> Series | None:
        ...

    def list_series(self, tenant_id: str | None = None) -> list[Series]:
        ...

    def update_series(
        self,
        series_id: str,
        title: str | None = None,
        subtitle: str | None = None,
        audience: str | None = None,
        difficulty: str | None = None,
        language: str | None = None,
        profile_id: str | None = None,
        brief: str | None = None,
    ) -> Series | None:
        ...

    def delete_series(
        self, series_id: str, tenant_id: str | None = None
    ) -> dict[str, Any] | None:
        ...

    def count_by_user(self, user_id: str) -> int:
        ...

    def transfer_by_user(
        self, user_id: str, target_user_id: str, tenant_ids: Sequence[str] = ()
    ) -> int:
        ...

    def create_unit(
        self,
        series_id: str,
        title: str,
        order_index: int | None = None,
        learning_objectives: Sequence[str] | None = None,
        prerequisites: Sequence[str] | None = None,
        content: str = "",
        status: str = "draft",
    ) -> Unit:
        ...

    def get_unit(self, unit_id: str) -> Unit | None:
        ...

    def list_units(self, series_id: str) -> list[Unit]:
        ...

    def update_unit(
        self,
        unit_id: str,
        title: str | None = None,
        learning_objectives: Sequence[str] | None = None,
        prerequisites: Sequence[str] | None = None,
        status: str | None = None,
        order_index: int | None = None,
        content: str | None = None,
    ) -> Unit | None:
        ...

    def delete_unit(self, unit_id: str) -> dict[str, int] | None:
        ...

    def reorder_units(
        self, series_id: str, unit_ids: Sequence[str]
    ) -> list[Unit]:
        ...

    def append_version(
        self,
        unit_id: str,
        content: str,
        citations: Sequence[Citation] | None = None,
        note: str = "",
        status: str | None = None,
        mode: str = "",
    ) -> tuple[Unit, UnitVersion] | None:
        ...

    def list_versions(self, unit_id: str) -> list[UnitVersion]:
        ...

    def get_version(self, unit_id: str, version: int) -> UnitVersion | None:
        ...

    def revert_to_version(
        self, unit_id: str, version: int, note: str = ""
    ) -> tuple[Unit, UnitVersion] | None:
        ...
