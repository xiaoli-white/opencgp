"""Database implementation of the course document repository (based on the Database port).

Depends only on :class:`app.ports.database.Database`, so SQLite (M0 default) and
PostgreSQL (production) share the same implementation; switching only changes config.

Storage conventions: structured fields are stored as JSON text
(``learning_objectives`` / ``prerequisites`` / ``citations_json``), so switching
databases needs no JSONB migration.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Mapping, Sequence

from app.models.auth import DEFAULT_TENANT_ID
from app.models.citation import Citation
from app.models.series import Series, Unit, UnitVersion
from app.ports.series_repository import SeriesRepository
from app.ports.database import Database

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS series (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        subtitle TEXT NOT NULL DEFAULT '',
        brief TEXT NOT NULL DEFAULT '',
        audience TEXT NOT NULL DEFAULT '',
        difficulty TEXT NOT NULL DEFAULT 'intermediate',
        language TEXT NOT NULL DEFAULT 'zh',
        tenant_id TEXT NOT NULL DEFAULT '',
        user_id TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS units (
        id TEXT PRIMARY KEY,
        series_id TEXT NOT NULL,
        order_index INTEGER NOT NULL DEFAULT 0,
        title TEXT NOT NULL,
        learning_objectives TEXT NOT NULL DEFAULT '[]',
        prerequisites TEXT NOT NULL DEFAULT '[]',
        content TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'draft',
        current_version INTEGER NOT NULL DEFAULT 0,
        last_mode TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_units_series ON units(series_id, order_index)",
    """
    CREATE TABLE IF NOT EXISTS unit_versions (
        id TEXT PRIMARY KEY,
        unit_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        content TEXT NOT NULL DEFAULT '',
        citations_json TEXT NOT NULL DEFAULT '[]',
        mode TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        UNIQUE (unit_id, version)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_unit_versions_unit ON unit_versions(unit_id, version)",
)

COLUMN_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("series", "brief", "TEXT NOT NULL DEFAULT ''"),
    ("series", "tenant_id", "TEXT NOT NULL DEFAULT ''"),
    ("series", "user_id", "TEXT NOT NULL DEFAULT ''"),
    ("series", "profile_id", "TEXT NOT NULL DEFAULT ''"),
    ("units", "last_mode", "TEXT NOT NULL DEFAULT ''"),
    ("unit_versions", "mode", "TEXT NOT NULL DEFAULT ''"),
)


class DatabaseSeriesRepository(SeriesRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        for table, column, ddl in COLUMN_MIGRATIONS:
            columns = {
                str(row["name"])
                for row in self.database.fetchall(f"PRAGMA table_info({table})")
            }
            if column not in columns:
                self.database.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        self._schema_ready = True

    def create_series(
        self,
        title: str,
        subtitle: str = "",
        audience: str = "",
        difficulty: str = "intermediate",
        language: str = "zh",
        tenant_id: str = "",
        user_id: str = "",
        profile_id: str = "",
        brief: str = "",
    ) -> Series:
        self.ensure_schema()
        now = time.time()
        series = Series(
            id=_new_id(),
            title=title,
            subtitle=subtitle,
            brief=brief or "",
            audience=audience,
            difficulty=difficulty,
            language=language,
            user_id=user_id or "",
            profile_id=profile_id or "",
            created_at=now,
            updated_at=now,
        )
        self.database.execute(
            "INSERT INTO series (id, title, subtitle, brief, audience, difficulty, language,"
            " tenant_id, user_id, profile_id, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                series.id,
                series.title,
                series.subtitle,
                series.brief,
                series.audience,
                series.difficulty,
                series.language,
                tenant_id or "",
                user_id or "",
                series.profile_id,
                series.created_at,
                series.updated_at,
            ),
        )
        return series

    def get_series(self, series_id: str, tenant_id: str | None = None) -> Series | None:
        self.ensure_schema()
        if tenant_id is None:
            row = self.database.fetchone(
                "SELECT * FROM series WHERE id = ?", (series_id,)
            )
        else:
            row = self.database.fetchone(
                "SELECT * FROM series WHERE id = ? AND"
                " (CASE WHEN tenant_id = '' THEN ? ELSE tenant_id END) = ?",
                (series_id, DEFAULT_TENANT_ID, _tenant(tenant_id)),
            )
        return _to_series(row) if row else None

    def list_series(self, tenant_id: str | None = None) -> list[Series]:
        self.ensure_schema()
        if tenant_id is None:
            rows = self.database.fetchall("SELECT * FROM series ORDER BY created_at ASC")
        else:
            rows = self.database.fetchall(
                "SELECT * FROM series WHERE"
                " (CASE WHEN tenant_id = '' THEN ? ELSE tenant_id END) = ?"
                " ORDER BY created_at ASC",
                (DEFAULT_TENANT_ID, _tenant(tenant_id)),
            )
        return [_to_series(row) for row in rows]

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
        self.ensure_schema()
        series = self.get_series(series_id)
        if series is None:
            return None
        assignments: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("title", title),
            ("subtitle", subtitle),
            ("brief", brief),
            ("audience", audience),
            ("difficulty", difficulty),
            ("language", language),
            ("profile_id", profile_id),
        ):
            if value is not None:
                assignments.append(f"{column} = ?")
                params.append(value)
        if not assignments:
            return series
        assignments.append("updated_at = ?")
        params.append(time.time())
        params.append(series_id)
        self.database.execute(
            f"UPDATE series SET {', '.join(assignments)} WHERE id = ?", tuple(params)
        )
        return self.get_series(series_id)

    def delete_series(
        self, series_id: str, tenant_id: str | None = None
    ) -> dict[str, Any] | None:
        self.ensure_schema()
        if self.get_series(series_id, tenant_id) is None:
            return None
        unit_ids = [
            str(row["id"])
            for row in self.database.fetchall(
                "SELECT id FROM units WHERE series_id = ?", (series_id,)
            )
        ]
        versions = 0
        for unit_id in unit_ids:
            row = self.database.fetchone(
                "SELECT COUNT(*) AS n FROM unit_versions WHERE unit_id = ?",
                (unit_id,),
            )
            versions += int(row["n"] or 0) if row else 0
            self.database.execute(
                "DELETE FROM unit_versions WHERE unit_id = ?", (unit_id,)
            )
        threads = 0
        if self._table_exists("threads"):
            thread_ids: set[str] = set()
            for row in self.database.fetchall(
                "SELECT id FROM threads WHERE series_id = ?", (series_id,)
            ):
                thread_ids.add(str(row["id"]))
            for unit_id in unit_ids:
                for row in self.database.fetchall(
                    "SELECT id FROM threads WHERE unit_id = ?", (unit_id,)
                ):
                    thread_ids.add(str(row["id"]))
            for thread_id in thread_ids:
                if self._table_exists("messages"):
                    self.database.execute(
                        "DELETE FROM messages WHERE thread_id = ?", (thread_id,)
                    )
                self.database.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
            threads = len(thread_ids)
        if self._table_exists("unit_locks"):
            for unit_id in unit_ids:
                self.database.execute(
                    "DELETE FROM unit_locks WHERE unit_id = ?", (unit_id,)
                )
        blueprint = False
        if self._table_exists("series_blueprints"):
            row = self.database.fetchone(
                "SELECT series_id FROM series_blueprints WHERE series_id = ?",
                (series_id,),
            )
            blueprint = row is not None
            self.database.execute(
                "DELETE FROM series_blueprints WHERE series_id = ?", (series_id,)
            )
        if self._table_exists("series_grants"):
            self.database.execute(
                "DELETE FROM series_grants WHERE series_id = ?", (series_id,)
            )
        self.database.execute("DELETE FROM units WHERE series_id = ?", (series_id,))
        self.database.execute("DELETE FROM series WHERE id = ?", (series_id,))
        return {
            "units": len(unit_ids),
            "versions": versions,
            "threads": threads,
            "blueprint": blueprint,
        }

    def _table_exists(self, table: str) -> bool:
        try:
            row = self.database.fetchone(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            )
        except Exception:  # noqa: BLE001
            return True
        return row is not None

    def count_by_user(self, user_id: str) -> int:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT COUNT(1) AS n FROM series WHERE user_id = ? AND user_id <> ''",
            (user_id,),
        )
        return int(row["n"]) if row else 0

    def transfer_by_user(
        self, user_id: str, target_user_id: str, tenant_ids: Sequence[str] = ()
    ) -> int:
        self.ensure_schema()
        scoped = [str(item) for item in tenant_ids if item]
        if scoped:
            placeholders = ", ".join("?" for _ in scoped)
            row = self.database.fetchone(
                f"SELECT COUNT(1) AS n FROM series WHERE user_id = ?"
                f" AND tenant_id IN ({placeholders})",
                (user_id, *scoped),
            )
            total = int(row["n"]) if row else 0
            self.database.execute(
                f"UPDATE series SET user_id = ?, updated_at = ? WHERE user_id = ?"
                f" AND tenant_id IN ({placeholders})",
                (target_user_id, time.time(), user_id, *scoped),
            )
            return total
        row = self.database.fetchone(
            "SELECT COUNT(1) AS n FROM series WHERE user_id = ?", (user_id,)
        )
        total = int(row["n"]) if row else 0
        self.database.execute(
            "UPDATE series SET user_id = ?, updated_at = ? WHERE user_id = ?",
            (target_user_id, time.time(), user_id),
        )
        return total

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
        self.ensure_schema()
        now = time.time()
        resolved_index = order_index if order_index is not None else self._next_order_index(series_id)
        unit = Unit(
            id=_new_id(),
            series_id=series_id,
            order_index=resolved_index,
            title=title,
            learning_objectives=list(learning_objectives or []),
            prerequisites=list(prerequisites or []),
            content=content,
            status=status,
            current_version=0,
            created_at=now,
            updated_at=now,
        )
        self.database.execute(
            "INSERT INTO units (id, series_id, order_index, title, learning_objectives,"
            " prerequisites, content, status, current_version, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                unit.id,
                unit.series_id,
                unit.order_index,
                unit.title,
                _dump_list(unit.learning_objectives),
                _dump_list(unit.prerequisites),
                unit.content,
                unit.status,
                unit.current_version,
                unit.created_at,
                unit.updated_at,
            ),
        )
        return unit

    def get_unit(self, unit_id: str) -> Unit | None:
        self.ensure_schema()
        row = self.database.fetchone("SELECT * FROM units WHERE id = ?", (unit_id,))
        return _to_unit(row) if row else None

    def list_units(self, series_id: str) -> list[Unit]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM units WHERE series_id = ? ORDER BY order_index ASC, created_at ASC",
            (series_id,),
        )
        return [_to_unit(row) for row in rows]

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
        self.ensure_schema()
        unit = self.get_unit(unit_id)
        if unit is None:
            return None
        assignments: list[str] = []
        params: list[Any] = []
        if title is not None:
            assignments.append("title = ?")
            params.append(title)
        if learning_objectives is not None:
            assignments.append("learning_objectives = ?")
            params.append(_dump_list(learning_objectives))
        if prerequisites is not None:
            assignments.append("prerequisites = ?")
            params.append(_dump_list(prerequisites))
        if status is not None:
            assignments.append("status = ?")
            params.append(status)
        if order_index is not None:
            assignments.append("order_index = ?")
            params.append(int(order_index))
        if content is not None:
            assignments.append("content = ?")
            params.append(content)
        if not assignments:
            return unit
        assignments.append("updated_at = ?")
        params.append(time.time())
        params.append(unit_id)
        self.database.execute(
            f"UPDATE units SET {', '.join(assignments)} WHERE id = ?", tuple(params)
        )
        return self.get_unit(unit_id)

    def delete_unit(self, unit_id: str) -> dict[str, int] | None:
        self.ensure_schema()
        if self.get_unit(unit_id) is None:
            return None
        row = self.database.fetchone(
            "SELECT COUNT(*) AS n FROM unit_versions WHERE unit_id = ?",
            (unit_id,),
        )
        deleted_versions = int(row["n"] or 0) if row else 0
        self.database.execute(
            "DELETE FROM unit_versions WHERE unit_id = ?", (unit_id,)
        )
        thread_ids: set[str] = set()
        if self._table_exists("threads"):
            for row in self.database.fetchall(
                "SELECT id FROM threads WHERE unit_id = ?", (unit_id,)
            ):
                thread_ids.add(str(row["id"]))
            for thread_id in thread_ids:
                if self._table_exists("messages"):
                    self.database.execute(
                        "DELETE FROM messages WHERE thread_id = ?", (thread_id,)
                    )
                self.database.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
        if self._table_exists("unit_locks"):
            self.database.execute(
                "DELETE FROM unit_locks WHERE unit_id = ?", (unit_id,)
            )
        self.database.execute("DELETE FROM units WHERE id = ?", (unit_id,))
        return {"deleted_versions": deleted_versions, "deleted_threads": len(thread_ids)}

    def reorder_units(
        self, series_id: str, unit_ids: Sequence[str]
    ) -> list[Unit]:
        self.ensure_schema()
        existing = self.list_units(series_id)
        by_id = {unit.id: unit for unit in existing}
        ordered: list[Unit] = []
        seen: set[str] = set()
        for unit_id in unit_ids:
            unit = by_id.get(str(unit_id))
            if unit is None or unit.id in seen:
                continue
            seen.add(unit.id)
            ordered.append(unit)
        ordered.extend(unit for unit in existing if unit.id not in seen)
        now = time.time()
        for index, unit in enumerate(ordered, start=1):
            self.database.execute(
                "UPDATE units SET order_index = ?, updated_at = ? WHERE id = ?",
                (index, now, unit.id),
            )
        return self.list_units(series_id)

    def append_version(
        self,
        unit_id: str,
        content: str,
        citations: Sequence[Citation] | None = None,
        note: str = "",
        status: str | None = None,
        mode: str = "",
    ) -> tuple[Unit, UnitVersion] | None:
        self.ensure_schema()
        unit = self.get_unit(unit_id)
        if unit is None:
            return None
        version = unit.current_version + 1
        now = time.time()
        record = UnitVersion(
            id=_new_id(),
            unit_id=unit_id,
            version=version,
            content=content,
            citations=list(citations or []),
            mode=mode,
            note=note,
            created_at=now,
        )
        self.database.execute(
            "INSERT INTO unit_versions (id, unit_id, version, content, citations_json,"
            " mode, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.unit_id,
                record.version,
                record.content,
                _dump_list([citation.model_dump() for citation in record.citations]),
                record.mode,
                record.note,
                record.created_at,
            ),
        )
        self.database.execute(
            "UPDATE units SET content = ?, current_version = ?, status = ?, last_mode = ?,"
            " updated_at = ? WHERE id = ?",
            (
                content,
                version,
                status or unit.status,
                mode or unit.last_mode,
                now,
                unit_id,
            ),
        )
        updated = self.get_unit(unit_id)
        assert updated is not None
        return updated, record

    def list_versions(self, unit_id: str) -> list[UnitVersion]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM unit_versions WHERE unit_id = ? ORDER BY version DESC",
            (unit_id,),
        )
        return [_to_version(row) for row in rows]

    def get_version(self, unit_id: str, version: int) -> UnitVersion | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM unit_versions WHERE unit_id = ? AND version = ?",
            (unit_id, version),
        )
        return _to_version(row) if row else None

    def revert_to_version(
        self, unit_id: str, version: int, note: str = ""
    ) -> tuple[Unit, UnitVersion] | None:
        target = self.get_version(unit_id, version)
        if target is None:
            return None
        resolved_note = note or f"revert to v{version}"
        return self.append_version(
            unit_id,
            content=target.content,
            citations=target.citations,
            note=resolved_note,
            status="reverted",
            mode=target.mode,
        )

    def _next_order_index(self, series_id: str) -> int:
        row = self.database.fetchone(
            "SELECT MAX(order_index) AS max_index FROM units WHERE series_id = ?",
            (series_id,),
        )
        if not row or row["max_index"] is None:
            return 1
        return int(row["max_index"]) + 1


def _new_id() -> str:
    return str(uuid.uuid4())


def _dump_list(values: Sequence[Any]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _load_list(raw: Any) -> list[Any]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _to_series(row: Mapping[str, Any]) -> Series:
    keys = set(row.keys())
    return Series(
        id=str(row["id"]),
        title=str(row["title"]),
        subtitle=str(row["subtitle"] or ""),
        brief=str(row["brief"] or "") if "brief" in keys else "",
        audience=str(row["audience"] or ""),
        difficulty=str(row["difficulty"] or "intermediate"),
        language=str(row["language"] or "zh"),
        user_id=str(row["user_id"] or "") if "user_id" in keys else "",
        profile_id=str(row["profile_id"] or "") if "profile_id" in keys else "",
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _to_unit(row: Mapping[str, Any]) -> Unit:
    return Unit(
        id=str(row["id"]),
        series_id=str(row["series_id"]),
        order_index=int(row["order_index"]),
        title=str(row["title"]),
        learning_objectives=[str(item) for item in _load_list(row["learning_objectives"])],
        prerequisites=[str(item) for item in _load_list(row["prerequisites"])],
        content=str(row["content"] or ""),
        status=str(row["status"] or "draft"),
        current_version=int(row["current_version"]),
        last_mode=str(row.get("last_mode") or ""),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )


def _to_version(row: Mapping[str, Any]) -> UnitVersion:
    citations = [Citation(**item) for item in _load_list(row["citations_json"])]
    return UnitVersion(
        id=str(row["id"]),
        unit_id=str(row["unit_id"]),
        version=int(row["version"]),
        content=str(row["content"] or ""),
        citations=citations,
        mode=str(row.get("mode") or ""),
        note=str(row["note"] or ""),
        created_at=float(row["created_at"]),
    )


def _tenant(tenant_id: str) -> str:
    value = (tenant_id or "").strip()
    return value or DEFAULT_TENANT_ID
