from __future__ import annotations

import json
import time
import uuid
from typing import Any, Mapping

from app.models.blueprint import CourseBlueprint, LessonReview
from app.ports.blueprint_repository import BlueprintRepository
from app.ports.database import Database

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS course_blueprints (
        course_id TEXT PRIMARY KEY,
        version INTEGER NOT NULL DEFAULT 0,
        payload_json TEXT NOT NULL DEFAULT '{}',
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lesson_reviews (
        id TEXT PRIMARY KEY,
        lesson_id TEXT NOT NULL,
        action TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        version INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_lesson_reviews_lesson ON lesson_reviews(lesson_id, created_at)",
)


class DatabaseBlueprintRepository(BlueprintRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        self._schema_ready = True

    def get_blueprint(self, course_id: str) -> CourseBlueprint | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM course_blueprints WHERE course_id = ?", (course_id,)
        )
        if row is None:
            return None
        payload = _load_payload(row["payload_json"])
        payload["course_id"] = str(row["course_id"])
        payload["version"] = int(row["version"])
        payload["updated_at"] = float(row["updated_at"])
        return CourseBlueprint(**payload)

    def save_blueprint(self, blueprint: CourseBlueprint) -> CourseBlueprint:
        self.ensure_schema()
        existing = self.database.fetchone(
            "SELECT version FROM course_blueprints WHERE course_id = ?",
            (blueprint.course_id,),
        )
        next_version = (int(existing["version"]) + 1) if existing else 1
        now = time.time()
        saved = blueprint.model_copy(
            update={"version": next_version, "updated_at": now}
        )
        self.database.execute(
            "INSERT INTO course_blueprints (course_id, version, payload_json, updated_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(course_id) DO UPDATE SET version = excluded.version,"
            " payload_json = excluded.payload_json, updated_at = excluded.updated_at",
            (
                saved.course_id,
                saved.version,
                _dump_payload(saved),
                saved.updated_at,
            ),
        )
        return saved

    def add_review(
        self,
        lesson_id: str,
        action: str,
        note: str = "",
        version: int = 0,
        status: str = "",
    ) -> LessonReview:
        self.ensure_schema()
        review = LessonReview(
            id=_new_id(),
            lesson_id=lesson_id,
            action=action,
            note=note,
            version=version,
            status=status,
            created_at=time.time(),
        )
        self.database.execute(
            "INSERT INTO lesson_reviews (id, lesson_id, action, note, version, status,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                review.id,
                review.lesson_id,
                review.action,
                review.note,
                review.version,
                review.status,
                review.created_at,
            ),
        )
        return review

    def list_reviews(self, lesson_id: str) -> list[LessonReview]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM lesson_reviews WHERE lesson_id = ? ORDER BY created_at DESC",
            (lesson_id,),
        )
        return [_to_review(row) for row in rows]

    def latest_review(self, lesson_id: str) -> LessonReview | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM lesson_reviews WHERE lesson_id = ?"
            " ORDER BY created_at DESC LIMIT 1",
            (lesson_id,),
        )
        return _to_review(row) if row else None


def _new_id() -> str:
    return str(uuid.uuid4())


def _dump_payload(blueprint: CourseBlueprint) -> str:
    payload = blueprint.model_dump()
    payload.pop("version", None)
    payload.pop("updated_at", None)
    return json.dumps(payload, ensure_ascii=False)


def _load_payload(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _to_review(row: Mapping[str, Any]) -> LessonReview:
    return LessonReview(
        id=str(row["id"]),
        lesson_id=str(row["lesson_id"]),
        action=str(row["action"]),
        note=str(row["note"] or ""),
        version=int(row["version"]),
        status=str(row["status"] or ""),
        created_at=float(row["created_at"]),
    )
