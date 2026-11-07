from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.models.blueprint import SeriesBlueprint, UnitReview


@runtime_checkable
class BlueprintRepository(Protocol):
    def get_blueprint(self, series_id: str) -> SeriesBlueprint | None:
        ...

    def save_blueprint(
        self,
        blueprint: SeriesBlueprint,
        *,
        author: str | None = None,
        change_source: str | None = None,
        note: str = "",
    ) -> SeriesBlueprint:
        ...

    def list_blueprint_versions(self, series_id: str) -> list[dict[str, Any]]:
        ...

    def get_blueprint_version(
        self, series_id: str, version: int
    ) -> SeriesBlueprint | None:
        ...

    def add_review(
        self,
        unit_id: str,
        action: str,
        note: str = "",
        version: int = 0,
        status: str = "",
    ) -> UnitReview:
        ...

    def list_reviews(self, unit_id: str) -> list[UnitReview]:
        ...

    def latest_review(self, unit_id: str) -> UnitReview | None:
        ...
