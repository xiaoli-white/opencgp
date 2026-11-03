from __future__ import annotations

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
        backend TEXT NOT NULL DEFAULT '',
        base_url TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT '',
        api_key_cipher TEXT NOT NULL DEFAULT '',
        temperature REAL NOT NULL DEFAULT 0.7,
        max_tokens INTEGER NOT NULL DEFAULT 0,
        updated_at REAL NOT NULL DEFAULT 0
    )
    """,
)


def _to_setting(row: Mapping[str, Any]) -> ProviderSetting:
    return ProviderSetting(
        user_id=row["user_id"],
        backend=row["backend"] or "",
        base_url=row["base_url"] or "",
        model=row["model"] or "",
        api_key_cipher=row["api_key_cipher"] or "",
        temperature=float(row["temperature"] or DEFAULT_TEMPERATURE),
        max_tokens=int(row["max_tokens"] or DEFAULT_MAX_TOKENS),
        updated_at=float(row["updated_at"] or 0.0),
    )


class DatabaseProviderSettingsRepository(ProviderSettingsRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
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
                (user_id, backend, base_url, model, api_key_cipher,
                 temperature, max_tokens, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                backend = excluded.backend,
                base_url = excluded.base_url,
                model = excluded.model,
                api_key_cipher = excluded.api_key_cipher,
                temperature = excluded.temperature,
                max_tokens = excluded.max_tokens,
                updated_at = excluded.updated_at
            """,
            (
                payload.user_id,
                payload.backend,
                payload.base_url,
                payload.model,
                payload.api_key_cipher,
                payload.temperature,
                payload.max_tokens,
                payload.updated_at,
            ),
        )
        return payload

    def delete(self, user_id: str) -> None:
        self.ensure_schema()
        self.database.execute(
            "DELETE FROM user_provider_settings WHERE user_id = ?", (user_id,)
        )
