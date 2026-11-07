"""Runtime overrides for settings that operators want to tune without a restart.

Only an explicit allow-list can be overridden, so this cannot be used to change
credentials or provider choices. Values are stored in the application database
and applied to the in-memory settings object at startup and on every update.
"""

from __future__ import annotations

import time
from typing import Any

from app.ports.database import Database

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS runtime_config ("
    " key TEXT PRIMARY KEY,"
    " value TEXT NOT NULL,"
    " updated_at REAL NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_runtime_config_updated"
    " ON runtime_config(updated_at)",
]


# Every overridable knob: key -> (settings group, attribute, kind, minimum).
# The group names match the attribute names on the Settings object.
#
# `generation.timeout` is deliberately not listed: GenerationConfig has no such
# attribute and no generation-level deadline exists in the current code (LLM
# calls are bounded by llm.timeout, retrieval by the embedding/rerank timeouts).
# Exposing a knob that nothing reads would be a lie, so it stays env-only until
# a real generation deadline is implemented.
OVERRIDABLE: dict[str, tuple[str, str, str, float]] = {
    "llm.timeout": ("llm", "timeout", "float", 1.0),
    "image.timeout": ("image", "timeout", "float", 1.0),
    "video.timeout": ("video", "timeout", "float", 1.0),
    "websearch.timeout": ("websearch", "timeout", "float", 1.0),
    "websearch.fetch_timeout": ("websearch", "fetch_timeout", "float", 1.0),
    "embedding.timeout": ("embedding", "timeout", "float", 1.0),
    "rerank.timeout": ("rerank", "timeout", "float", 1.0),
}

MAXIMUM = 86_400


class RuntimeConfigService:
    def __init__(self, database: Database) -> None:
        self.database = database
        # Environment-backed values captured before any override is applied.
        # Kept so "default" keeps meaning "what deploy-time config said", even
        # though the live settings object is mutated in place.
        self._defaults: dict[str, float | None] = {}
        self._defaults_captured = False

    def ensure_schema(self) -> None:
        for statement in SCHEMA:
            self.database.execute(statement)

    # -- defaults ----------------------------------------------------------

    def capture_defaults(self, settings: Any) -> None:
        """Remember the env-backed values before overrides are applied."""
        if self._defaults_captured:
            return
        for key, (group, attribute, _, _) in OVERRIDABLE.items():
            target = getattr(settings, group, None)
            value = getattr(target, attribute, None) if target is not None else None
            self._defaults[key] = value
        self._defaults_captured = True

    def _default_for(self, key: str, settings: Any) -> float | None:
        if not self._defaults_captured:
            self.capture_defaults(settings)
        return self._defaults.get(key)

    # -- persistence -------------------------------------------------------

    def load(self) -> dict[str, Any]:
        self.ensure_schema()
        rows = self.database.fetchall("SELECT key, value FROM runtime_config")
        result: dict[str, Any] = {}
        for row in rows or []:
            record = dict(row)
            key = record.get("key")
            if key in OVERRIDABLE:
                try:
                    result[key] = self._coerce(key, record.get("value"))
                except ValueError:
                    continue
        return result

    def save(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Validate the whole batch first, then persist it, then reload."""
        self.ensure_schema()
        prepared: list[tuple[str, str | None]] = []
        for key, raw in changes.items():
            if key not in OVERRIDABLE:
                raise ValueError(f"setting is not overridable: {key}")
            if raw is None:
                prepared.append((key, None))
                continue
            value = self._coerce(key, raw)
            prepared.append((key, str(value)))
        now = time.time()
        for key, value in prepared:
            if value is None:
                self.database.execute(
                    "DELETE FROM runtime_config WHERE key = ?", (key,)
                )
            else:
                self.database.execute(
                    "INSERT INTO runtime_config (key, value, updated_at)"
                    " VALUES (?, ?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET"
                    " value = excluded.value, updated_at = excluded.updated_at",
                    (key, value, now),
                )
        return self.load()

    def _coerce(self, key: str, raw: Any) -> float:
        _, _, kind, minimum = OVERRIDABLE[key]
        if kind == "float":
            try:
                value = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be a number") from exc
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError(f"{key} must be a finite number")
            if value < minimum:
                raise ValueError(f"{key} must be at least {minimum:g} seconds")
            if value > MAXIMUM:
                raise ValueError(f"{key} must be at most {MAXIMUM} seconds")
            return value
        raise ValueError(f"unsupported kind for {key}")

    # -- applying overrides ------------------------------------------------

    def apply(self, settings: Any) -> dict[str, Any]:
        """Copy stored overrides onto the settings object, in place."""
        self.capture_defaults(settings)
        # Reset every allow-listed knob to its env-backed default first, so a
        # deleted override actually falls back instead of keeping the stale
        # in-memory value.
        for key, (group, attribute, _, _) in OVERRIDABLE.items():
            target = getattr(settings, group, None)
            default = self._defaults.get(key)
            if target is not None and default is not None and hasattr(target, attribute):
                setattr(target, attribute, default)
        applied = self.load()
        for key, value in applied.items():
            group, attribute, _, _ = OVERRIDABLE[key]
            target = getattr(settings, group, None)
            if target is None:
                continue
            if hasattr(target, attribute):
                setattr(target, attribute, value)
        return applied

    def snapshot(self, settings: Any) -> dict[str, Any]:
        """Current effective values plus which ones are overridden."""
        self.capture_defaults(settings)
        overrides = self.load()
        items = []
        for key, (group, attribute, _, minimum) in OVERRIDABLE.items():
            target = getattr(settings, group, None)
            current = getattr(target, attribute, None) if target else None
            default = self._default_for(key, settings)
            override = overrides.get(key)
            items.append(
                {
                    "key": key,
                    "default": default,
                    "value": override if override is not None else current,
                    "overridden": override is not None,
                    "minimum": minimum,
                    "maximum": MAXIMUM,
                }
            )
        return {"items": items, "overrides": overrides}
