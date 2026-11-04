from __future__ import annotations

import json

import time
from typing import Any, Mapping

from app.models.provider_setting import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    ProviderSetting,
)
from app.ports.database import Database
from app.ports.provider_settings_repository import ProviderSettingsRepository

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS user_provider_settings (
        user_id TEXT PRIMARY KEY,
        provider_id TEXT NOT NULL DEFAULT '',
        backend TEXT NOT NULL DEFAULT '',
        base_url TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT '',
        api_key_cipher TEXT NOT NULL DEFAULT '',
        temperature REAL NOT NULL DEFAULT 0.7,
        max_tokens INTEGER NOT NULL DEFAULT 0,
        extra_body_json TEXT NOT NULL DEFAULT '{}',
        extra_headers_json TEXT NOT NULL DEFAULT '{}',
        updated_at REAL NOT NULL DEFAULT 0
    )
    """,
)

COLUMN_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("user_provider_settings", "provider_id", "TEXT NOT NULL DEFAULT ''"),
)


def _load_json(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _dump_json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _to_setting(row: Mapping[str, Any]) -> ProviderSetting:
    data = dict(row)
    return ProviderSetting(
        user_id=data["user_id"],
        provider_id=data["provider_id"] or "",
        backend=data["backend"] or "",
        base_url=data["base_url"] or "",
        model=data["model"] or "",
        api_key_cipher=data["api_key_cipher"] or "",
        temperature=float(data["temperature"] or DEFAULT_TEMPERATURE),
        max_tokens=int(data["max_tokens"] or DEFAULT_MAX_TOKENS),
        extra_body=_load_json(data.get("extra_body_json")),
        extra_headers={
            str(key): str(value)
            for key, value in _load_json(data.get("extra_headers_json")).items()
        },
        updated_at=float(data["updated_at"] or 0.0),
    )


class DatabaseProviderSettingsRepository(ProviderSettingsRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    MIGRATIONS = (
        ("user_provider_settings", "extra_body_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("user_provider_settings", "extra_headers_json", "TEXT NOT NULL DEFAULT '{}'"),
    )

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
            if not columns:
                continue
            if column not in columns:
                self.database.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        for table, column, ddl in self.MIGRATIONS:
            columns = {
                str(row["name"])
                for row in self.database.fetchall(f"PRAGMA table_info({table})")
            }
            if column not in columns:
                self.database.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        self._schema_ready = True

    def get(self, user_id: str) -> ProviderSetting | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM user_provider_settings WHERE user_id = ?", (user_id,)
        )
        return _to_setting(row) if row is not None else None

    def save(self, setting: ProviderSetting) -> ProviderSetting:
        self.ensure_schema()
        payload = setting.model_copy(
            update={"updated_at": setting.updated_at or time.time()}
        )
        self.database.execute(
            """
            INSERT INTO user_provider_settings
                (user_id, provider_id, backend, base_url, model, api_key_cipher,
                 temperature, max_tokens, extra_body_json, extra_headers_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                provider_id = excluded.provider_id,
                backend = excluded.backend,
                base_url = excluded.base_url,
                model = excluded.model,
                api_key_cipher = excluded.api_key_cipher,
                temperature = excluded.temperature,
                max_tokens = excluded.max_tokens,
                extra_body_json = excluded.extra_body_json,
                extra_headers_json = excluded.extra_headers_json,
                updated_at = excluded.updated_at
            """,
            (
                payload.user_id,
                payload.provider_id,
                payload.backend,
                payload.base_url,
                payload.model,
                payload.api_key_cipher,
                payload.temperature,
                payload.max_tokens,
                _dump_json(payload.extra_body),
                _dump_json(payload.extra_headers),
                payload.updated_at,
            ),
        )
        return payload

    def delete(self, user_id: str) -> None:
        self.ensure_schema()
        self.database.execute(
            "DELETE FROM user_provider_settings WHERE user_id = ?", (user_id,)
        )

    def clear_provider_reference(self, user_id: str, provider_id: str) -> None:
        self.ensure_schema()
        if not provider_id:
            return
        self.database.execute(
            """
            UPDATE user_provider_settings
            SET provider_id = '', updated_at = ?
            WHERE user_id = ? AND provider_id = ?
            """,
            (time.time(), user_id, provider_id),
        )

    def count_by_provider(self, provider_id: str) -> int:
        self.ensure_schema()
        if not provider_id:
            return 0
        row = self.database.fetchone(
            "SELECT COUNT(*) AS n FROM user_provider_settings WHERE provider_id = ?",
            (provider_id,),
        )
        return int(row["n"]) if row is not None else 0
