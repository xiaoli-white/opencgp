from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.blueprint import SeriesBlueprint, UnitReview


@runtime_checkable
class BlueprintRepository(Protocol):
    def get_blueprint(self, series_id: str) -> SeriesBlueprint | None:
        ...

    def save_blueprint(self, blueprint: SeriesBlueprint) -> SeriesBlueprint:
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
