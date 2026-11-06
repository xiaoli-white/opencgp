from __future__ import annotations

import json
import time
import uuid
from typing import Any, Mapping

from app.models.blueprint import SeriesBlueprint, UnitReview
from app.ports.blueprint_repository import BlueprintRepository
from app.ports.database import Database

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS series_blueprints (
        series_id TEXT PRIMARY KEY,
        version INTEGER NOT NULL DEFAULT 0,
        payload_json TEXT NOT NULL DEFAULT '{}',
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS unit_reviews (
        id TEXT PRIMARY KEY,
        unit_id TEXT NOT NULL,
        action TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        version INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_unit_reviews_unit ON unit_reviews(unit_id, created_at)",
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

    def get_blueprint(self, series_id: str) -> SeriesBlueprint | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM series_blueprints WHERE series_id = ?", (series_id,)
        )
        if row is None:
            return None
        payload = _load_payload(row["payload_json"])
        payload["series_id"] = str(row["series_id"])
        payload["version"] = int(row["version"])
        payload["updated_at"] = float(row["updated_at"])
        return SeriesBlueprint(**payload)

    def save_blueprint(self, blueprint: SeriesBlueprint) -> SeriesBlueprint:
        self.ensure_schema()
        existing = self.database.fetchone(
            "SELECT version FROM series_blueprints WHERE series_id = ?",
            (blueprint.series_id,),
        )
        next_version = (int(existing["version"]) + 1) if existing else 1
        now = time.time()
        saved = blueprint.model_copy(
            update={"version": next_version, "updated_at": now}
        )
        self.database.execute(
            "INSERT INTO series_blueprints (series_id, version, payload_json, updated_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(series_id) DO UPDATE SET version = excluded.version,"
            " payload_json = excluded.payload_json, updated_at = excluded.updated_at",
            (
                saved.series_id,
                saved.version,
                _dump_payload(saved),
                saved.updated_at,
            ),
        )
        return saved

    def add_review(
        self,
        unit_id: str,
        action: str,
        note: str = "",
        version: int = 0,
        status: str = "",
    ) -> UnitReview:
        self.ensure_schema()
        review = UnitReview(
            id=_new_id(),
            unit_id=unit_id,
            action=action,
            note=note,
            version=version,
            status=status,
            created_at=time.time(),
        )
        self.database.execute(
            "INSERT INTO unit_reviews (id, unit_id, action, note, version, status,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                review.id,
                review.unit_id,
                review.action,
                review.note,
                review.version,
                review.status,
                review.created_at,
            ),
        )
        return review

    def list_reviews(self, unit_id: str) -> list[UnitReview]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM unit_reviews WHERE unit_id = ? ORDER BY created_at DESC",
            (unit_id,),
        )
        return [_to_review(row) for row in rows]

    def latest_review(self, unit_id: str) -> UnitReview | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM unit_reviews WHERE unit_id = ?"
            " ORDER BY created_at DESC LIMIT 1",
            (unit_id,),
        )
        return _to_review(row) if row else None


def _new_id() -> str:
    return str(uuid.uuid4())


def _dump_payload(blueprint: SeriesBlueprint) -> str:
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


def _to_review(row: Mapping[str, Any]) -> UnitReview:
    return UnitReview(
        id=str(row["id"]),
        unit_id=str(row["unit_id"]),
        action=str(row["action"]),
        note=str(row["note"] or ""),
        version=int(row["version"]),
        status=str(row["status"] or ""),
        created_at=float(row["created_at"]),
    )
