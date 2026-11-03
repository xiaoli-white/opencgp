from __future__ import annotations

import json
import time
from typing import Any, Mapping

from app.models.provider_catalog import PROVIDER_KIND_OPENAI, ServerProvider
from app.ports.database import Database
from app.ports.provider_catalog_repository import ProviderCatalogRepository

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS server_providers (
        id TEXT PRIMARY KEY,
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
    CREATE INDEX IF NOT EXISTS idx_server_providers_default
        ON server_providers (is_default)
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


def _to_provider(row: Mapping[str, Any]) -> ServerProvider:
    return ServerProvider(
        id=row["id"],
        name=row["name"] or "",
        kind=row["kind"] or PROVIDER_KIND_OPENAI,
        base_url=row["base_url"] or "",
        api_key_cipher=row["api_key_cipher"] or "",
        models=_models(row["models_json"]),
        enabled=bool(row["enabled"]),
        is_default=bool(row["is_default"]),
        created_at=float(row["created_at"] or 0.0),
        updated_at=float(row["updated_at"] or 0.0),
    )


class DatabaseProviderCatalogRepository(ProviderCatalogRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        self._schema_ready = True

    def count(self) -> int:
        self.ensure_schema()
        row = self.database.fetchone("SELECT COUNT(*) AS n FROM server_providers")
        return int(row["n"]) if row is not None else 0

    def list_providers(self) -> list[ServerProvider]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM server_providers ORDER BY is_default DESC, created_at ASC"
        )
        return [_to_provider(row) for row in rows]

    def get_provider(self, provider_id: str) -> ServerProvider | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM server_providers WHERE id = ?", (provider_id,)
        )
        return _to_provider(row) if row is not None else None

    def save_provider(self, provider: ServerProvider) -> ServerProvider:
        self.ensure_schema()
        payload = provider.model_copy(
            update={"updated_at": provider.updated_at or time.time()}
        )
        if payload.is_default:
            self.clear_default(payload.id)
        self.database.execute(
            """
            INSERT INTO server_providers
                (id, name, kind, base_url, api_key_cipher, models_json,
                 enabled, is_default, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        return self.get_provider(payload.id) or payload

    def delete_provider(self, provider_id: str) -> bool:
        self.ensure_schema()
        existing = self.get_provider(provider_id)
        if existing is None:
            return False
        self.database.execute(
            "DELETE FROM server_providers WHERE id = ?", (provider_id,)
        )
        return True

    def clear_default(self, keep_id: str = "") -> None:
        self.ensure_schema()
        self.database.execute(
            "UPDATE server_providers SET is_default = 0 WHERE id <> ?", (keep_id,)
        )
