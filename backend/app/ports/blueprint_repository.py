from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.blueprint import CourseBlueprint, LessonReview


@runtime_checkable
class BlueprintRepository(Protocol):
    def get_blueprint(self, course_id: str) -> CourseBlueprint | None:
        ...

    def save_blueprint(self, blueprint: CourseBlueprint) -> CourseBlueprint:
        ...

    def add_review(
        self,
        lesson_id: str,
        action: str,
        note: str = "",
        version: int = 0,
        status: str = "",
    ) -> LessonReview:
        ...

    def list_reviews(self, lesson_id: str) -> list[LessonReview]:
        ...

    def latest_review(self, lesson_id: str) -> LessonReview | None:
        ...
