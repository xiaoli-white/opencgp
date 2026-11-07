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
    CREATE TABLE IF NOT EXISTS blueprint_versions (
        series_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        payload_json TEXT NOT NULL DEFAULT '{}',
        author TEXT NOT NULL DEFAULT '',
        change_source TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        PRIMARY KEY (series_id, version)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_blueprint_versions_series"
    " ON blueprint_versions(series_id, version DESC)",
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
    """
    CREATE TABLE IF NOT EXISTS blueprint_applications (
        series_id TEXT PRIMARY KEY,
        version INTEGER NOT NULL,
        applied_at REAL NOT NULL,
        author TEXT NOT NULL DEFAULT ''
    )
    """,
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

    def record_application(
        self, series_id: str, version: int, author: str = ""
    ) -> None:
        """Remember which blueprint version was last pushed into the units.

        The UI uses this to keep "apply" disabled until the blueprint changes
        again, so a no-op apply cannot be clicked repeatedly.
        """
        self.ensure_schema()
        self.database.execute(
            "INSERT INTO blueprint_applications (series_id, version, applied_at, author)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(series_id) DO UPDATE SET"
            " version = excluded.version, applied_at = excluded.applied_at,"
            " author = excluded.author",
            (series_id, int(version), time.time(), author or ""),
        )

    def get_application(self, series_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT series_id, version, applied_at, author"
            " FROM blueprint_applications WHERE series_id = ?",
            (series_id,),
        )
        return dict(row) if row is not None else None

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

    def save_blueprint(
        self,
        blueprint: SeriesBlueprint,
        *,
        author: str | None = None,
        change_source: str | None = None,
        note: str = "",
    ) -> SeriesBlueprint:
        """Persist a new blueprint version and keep the previous one.

        The ``series_blueprints`` row remains the fast "current" pointer.  The
        blueprint already used a monotonically increasing ``version`` counter;
        this method now also appends each version to ``blueprint_versions`` so
        older plans stay retrievable and can be restored.  No parallel history
        or second counter is introduced.
        """
        self.ensure_schema()
        existing = self.database.fetchone(
            "SELECT version, payload_json, updated_at FROM series_blueprints"
            " WHERE series_id = ?",
            (blueprint.series_id,),
        )
        now = time.time()
        if existing is not None:
            old_version = int(existing["version"])
            # Make the pre-upgrade current plan retrievable on the first save
            # after this feature ships (older databases have no history rows).
            self.database.execute(
                "INSERT INTO blueprint_versions (series_id, version, payload_json,"
                " author, change_source, note, created_at)"
                " SELECT ?, ?, ?, ?, ?, ?, ?"
                " WHERE NOT EXISTS (SELECT 1 FROM blueprint_versions"
                " WHERE series_id = ? AND version = ?)",
                (
                    blueprint.series_id,
                    old_version,
                    str(existing["payload_json"] or "{}"),
                    "",
                    "generated",
                    "snapshot before the next save",
                    float(existing["updated_at"] or now),
                    blueprint.series_id,
                    old_version,
                ),
            )
        next_version = (int(existing["version"]) + 1) if existing else 1
        saved = blueprint.model_copy(
            update={
                "version": next_version,
                "updated_at": now,
                **(
                    {"author": str(author or "")}
                    if author is not None
                    else {}
                ),
                **(
                    {"change_source": str(change_source or "")}
                    if change_source is not None
                    else {}
                ),
            }
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
        self.database.execute(
            "INSERT OR REPLACE INTO blueprint_versions (series_id, version,"
            " payload_json, author, change_source, note, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                saved.series_id,
                saved.version,
                _dump_payload(saved),
                str(saved.author or ""),
                str(saved.change_source or ""),
                str(note or ""),
                now,
            ),
        )
        return saved

    def list_blueprint_versions(self, series_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT version, payload_json, author, change_source, note, created_at"
            " FROM blueprint_versions WHERE series_id = ? ORDER BY version DESC",
            (series_id,),
        )
        versions: list[dict[str, Any]] = []
        for row in rows:
            payload = _load_payload(row["payload_json"])
            versions.append(
                {
                    "version": int(row["version"]),
                    "author": str(row["author"] or ""),
                    "change_source": str(row["change_source"] or ""),
                    "note": str(row["note"] or ""),
                    "created_at": float(row["created_at"] or 0.0),
                    "overview": str(payload.get("overview") or "")[:280],
                    "stage_count": len(payload.get("learning_path") or []),
                    "node_count": len(payload.get("outline") or []),
                    "glossary_count": len(payload.get("glossary") or []),
                    "mode": str(payload.get("mode") or ""),
                }
            )
        return versions

    def get_blueprint_version(
        self, series_id: str, version: int
    ) -> SeriesBlueprint | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM blueprint_versions WHERE series_id = ? AND version = ?",
            (series_id, int(version)),
        )
        if row is None:
            # Compatibility with rows written before blueprint_versions
            # existed: the current pointer may still be the only copy.
            current = self.database.fetchone(
                "SELECT * FROM series_blueprints WHERE series_id = ? AND version = ?",
                (series_id, int(version)),
            )
            if current is None:
                return None
            row = current
        payload = _load_payload(row["payload_json"])
        payload["series_id"] = str(row["series_id"])
        payload["version"] = int(row["version"])
        created = (
            float(row["created_at"])
            if "created_at" in row.keys()
            else float(row["updated_at"] or 0.0)
        )
        payload["updated_at"] = created
        return SeriesBlueprint(**payload)

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
