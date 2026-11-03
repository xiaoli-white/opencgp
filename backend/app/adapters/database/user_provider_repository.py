from __future__ import annotations

import json
import time
from typing import Any, Mapping

from app.models.user_provider import UserProvider
from app.ports.database import Database
from app.ports.user_provider_repository import UserProviderRepository

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS user_providers (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL DEFAULT 'openai_compat',
        base_url TEXT NOT NULL DEFAULT '',
        api_key_cipher TEXT NOT NULL DEFAULT '',
        models_json TEXT NOT NULL DEFAULT '[]',
        enabled INTEGER NOT NULL DEFAULT 1,
        is_default INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL DEFAULT 0,
        updated_at REAL NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_user_providers_user
        ON user_providers (user_id)
    """,
)


def _models(raw: Any) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _to_provider(row: Mapping[str, Any]) -> UserProvider:
    return UserProvider(
        id=row["id"],
        user_id=row["user_id"] or "",
        name=row["name"] or "",
        kind=row["kind"] or "openai_compat",
        base_url=row["base_url"] or "",
        api_key_cipher=row["api_key_cipher"] or "",
        models=_models(row["models_json"]),
        enabled=bool(row["enabled"]),
        is_default=bool(row["is_default"]),
        created_at=float(row["created_at"] or 0.0),
        updated_at=float(row["updated_at"] or 0.0),
    )


class DatabaseUserProviderRepository(UserProviderRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        self._schema_ready = True

    def list_providers(self, user_id: str) -> list[UserProvider]:
        self.ensure_schema()
        rows = self.database.fetchall(
            """
            SELECT * FROM user_providers
            WHERE user_id = ?
            ORDER BY is_default DESC, created_at ASC
            """,
            (user_id,),
        )
        return [_to_provider(row) for row in rows]

    def get_provider(self, user_id: str, provider_id: str) -> UserProvider | None:
        self.ensure_schema()
        if not provider_id:
            return None
        row = self.database.fetchone(
            "SELECT * FROM user_providers WHERE id = ? AND user_id = ?",
            (provider_id, user_id),
        )
        return _to_provider(row) if row is not None else None

    def save_provider(self, provider: UserProvider) -> UserProvider:
        self.ensure_schema()
        payload = provider.model_copy(
            update={"updated_at": provider.updated_at or time.time()}
        )
        if payload.is_default:
            self.clear_default(payload.user_id, payload.id)
        self.database.execute(
            """
            INSERT INTO user_providers
                (id, user_id, name, kind, base_url, api_key_cipher, models_json,
                 enabled, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                kind = excluded.kind,
                base_url = excluded.base_url,
                api_key_cipher = excluded.api_key_cipher,
                models_json = excluded.models_json,
                enabled = excluded.enabled,
                is_default = excluded.is_default,
                updated_at = excluded.updated_at
            """,
            (
                payload.id,
                payload.user_id,
                payload.name,
                payload.kind,
                payload.base_url,
                payload.api_key_cipher,
                json.dumps(list(payload.models), ensure_ascii=False),
                1 if payload.enabled else 0,
                1 if payload.is_default else 0,
                payload.created_at or payload.updated_at,
                payload.updated_at,
            ),
        )
        return self.get_provider(payload.user_id, payload.id) or payload

    def delete_provider(self, user_id: str, provider_id: str) -> bool:
        self.ensure_schema()
        existing = self.get_provider(user_id, provider_id)
        if existing is None:
            return False
        self.database.execute(
            "DELETE FROM user_providers WHERE id = ? AND user_id = ?",
            (provider_id, user_id),
        )
        return True

    def clear_default(self, user_id: str, keep_id: str = "") -> None:
        self.ensure_schema()
        self.database.execute(
            "UPDATE user_providers SET is_default = 0 WHERE user_id = ? AND id <> ?",
            (user_id, keep_id),
        )

    def count_by_user(self, user_id: str) -> int:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT COUNT(*) AS n FROM user_providers WHERE user_id = ?", (user_id,)
        )
        return int(row["n"]) if row is not None else 0
