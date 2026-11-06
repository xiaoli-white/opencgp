from __future__ import annotations

import json
import time
from typing import Any, Mapping

from app.models.retrieval import RetrievalProvider, RetrievalSetting
from app.ports.database import Database
from app.ports.retrieval_repository import RetrievalRepository

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS retrieval_providers (
        id TEXT PRIMARY KEY,
        tenant_id TEXT,
        user_id TEXT,
        kind TEXT NOT NULL DEFAULT 'embedding',
        name TEXT NOT NULL DEFAULT '',
        backend TEXT NOT NULL DEFAULT '',
        base_url TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT '',
        dim INTEGER NOT NULL DEFAULT 0,
        api_key TEXT NOT NULL DEFAULT '',
        enabled INTEGER NOT NULL DEFAULT 1,
        is_default INTEGER NOT NULL DEFAULT 0,
        meta TEXT NOT NULL DEFAULT '{}',
        version INTEGER NOT NULL DEFAULT 1,
        created_at INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_retrieval_providers_scope"
    " ON retrieval_providers(tenant_id, user_id, kind, is_default)",
    "CREATE INDEX IF NOT EXISTS idx_retrieval_providers_kind"
    " ON retrieval_providers(kind)",
    """
    CREATE TABLE IF NOT EXISTS retrieval_settings (
        tenant_id TEXT NOT NULL DEFAULT '',
        user_id TEXT NOT NULL DEFAULT '',
        scope TEXT NOT NULL DEFAULT 'user',
        embedding_provider_id TEXT,
        rerank_provider_id TEXT,
        vector_weight REAL,
        rerank_weight REAL,
        rerank_top_n INTEGER,
        updated_at INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (tenant_id, scope, user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_retrieval_settings_scope"
    " ON retrieval_settings(tenant_id, scope)",
)


def _json_obj(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_provider(row: Mapping[str, Any]) -> RetrievalProvider:
    return RetrievalProvider(
        id=str(row["id"]),
        tenant_id=row.get("tenant_id"),
        user_id=row.get("user_id"),
        kind=str(row.get("kind") or "embedding"),
        name=str(row.get("name") or ""),
        backend=str(row.get("backend") or ""),
        base_url=str(row.get("base_url") or ""),
        model=str(row.get("model") or ""),
        dim=int(row.get("dim") or 0),
        api_key_cipher=str(row.get("api_key") or ""),
        enabled=bool(row.get("enabled")),
        is_default=bool(row.get("is_default")),
        meta=_json_obj(row.get("meta")),
        version=int(row.get("version") or 1),
        created_at=int(row.get("created_at") or 0),
        updated_at=int(row.get("updated_at") or 0),
    )


def _to_setting(row: Mapping[str, Any]) -> RetrievalSetting:
    return RetrievalSetting(
        tenant_id=str(row.get("tenant_id") or ""),
        user_id=str(row.get("user_id") or ""),
        scope=str(row.get("scope") or "user"),
        embedding_provider_id=row.get("embedding_provider_id"),
        rerank_provider_id=row.get("rerank_provider_id"),
        vector_weight=(
            float(row["vector_weight"])
            if row.get("vector_weight") is not None
            else None
        ),
        rerank_weight=(
            float(row["rerank_weight"])
            if row.get("rerank_weight") is not None
            else None
        ),
        rerank_top_n=(
            int(row["rerank_top_n"]) if row.get("rerank_top_n") is not None else None
        ),
        updated_at=int(row.get("updated_at") or 0),
    )


class DatabaseRetrievalRepository(RetrievalRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        self._schema_ready = True

    def list_providers(
        self, tenant_id: str, user_id: str, kind: str = ""
    ) -> list[RetrievalProvider]:
        self.ensure_schema()
        sql = (
            "SELECT * FROM retrieval_providers WHERE"
            " ((tenant_id = ? AND (user_id = ? OR user_id = '' OR user_id IS NULL))"
            " OR tenant_id IS NULL)"
        )
        params: list[Any] = [tenant_id, user_id]
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        sql += " ORDER BY created_at ASC, id ASC"
        rows = self.database.fetchall(sql, params)
        return [_to_provider(row) for row in rows]

    def get_provider(
        self, tenant_id: str, user_id: str, provider_id: str
    ) -> RetrievalProvider | None:
        self.ensure_schema()
        if not provider_id:
            return None
        row = self.database.fetchone(
            "SELECT * FROM retrieval_providers WHERE id = ? AND"
            " ((tenant_id = ? AND (user_id = ? OR user_id = '' OR user_id IS NULL))"
            " OR tenant_id IS NULL)",
            (provider_id, tenant_id, user_id),
        )
        return _to_provider(row) if row is not None else None

    def get_provider_any(self, provider_id: str) -> RetrievalProvider | None:
        self.ensure_schema()
        if not provider_id:
            return None
        row = self.database.fetchone(
            "SELECT * FROM retrieval_providers WHERE id = ?", (provider_id,)
        )
        return _to_provider(row) if row is not None else None

    def find_default(
        self, tenant_id: str, user_id: str, kind: str
    ) -> RetrievalProvider | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM retrieval_providers WHERE kind = ? AND enabled = 1"
            " AND is_default = 1 AND ("
            " (tenant_id = ? AND user_id = ?)"
            " OR (tenant_id = ? AND (user_id = '' OR user_id IS NULL))"
            " OR tenant_id IS NULL)"
            " ORDER BY CASE WHEN tenant_id = ? AND user_id = ? THEN 0"
            " WHEN tenant_id = ? THEN 1 ELSE 2 END, created_at ASC LIMIT 1",
            (kind, tenant_id, user_id, tenant_id, tenant_id, user_id, tenant_id),
        )
        return _to_provider(row) if row is not None else None

    def save_provider(self, provider: RetrievalProvider) -> RetrievalProvider:
        self.ensure_schema()
        if provider.is_default:
            self.clear_defaults(
                provider.tenant_id, provider.user_id or "", provider.kind, provider.id
            )
        self.database.execute(
            """
            INSERT INTO retrieval_providers
                (id, tenant_id, user_id, kind, name, backend, base_url, model, dim,
                 api_key, enabled, is_default, meta, version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                tenant_id = excluded.tenant_id,
                user_id = excluded.user_id,
                kind = excluded.kind,
                name = excluded.name,
                backend = excluded.backend,
                base_url = excluded.base_url,
                model = excluded.model,
                dim = excluded.dim,
                api_key = excluded.api_key,
                enabled = excluded.enabled,
                is_default = excluded.is_default,
                meta = excluded.meta,
                version = excluded.version,
                updated_at = excluded.updated_at
            """,
            (
                provider.id,
                provider.tenant_id,
                provider.user_id or "",
                provider.kind,
                provider.name,
                provider.backend,
                provider.base_url,
                provider.model,
                int(provider.dim),
                provider.api_key_cipher,
                1 if provider.enabled else 0,
                1 if provider.is_default else 0,
                json.dumps(provider.meta or {}, ensure_ascii=False),
                int(provider.version or 1),
                int(provider.created_at or 0),
                int(provider.updated_at or 0),
            ),
        )
        return self.get_provider_any(provider.id) or provider

    def delete_provider(
        self, tenant_id: str, user_id: str, provider_id: str
    ) -> bool:
        self.ensure_schema()
        existing = self.get_provider(tenant_id, user_id, provider_id)
        if existing is None:
            return False
        self.database.execute(
            "DELETE FROM retrieval_providers WHERE id = ?", (provider_id,)
        )
        self.database.execute(
            "UPDATE retrieval_settings SET embedding_provider_id = NULL"
            " WHERE embedding_provider_id = ?",
            (provider_id,),
        )
        self.database.execute(
            "UPDATE retrieval_settings SET rerank_provider_id = NULL"
            " WHERE rerank_provider_id = ?",
            (provider_id,),
        )
        return True

    def clear_defaults(
        self, tenant_id: str | None, user_id: str, kind: str, keep_id: str = ""
    ) -> None:
        self.ensure_schema()
        if tenant_id is None:
            self.database.execute(
                "UPDATE retrieval_providers SET is_default = 0"
                " WHERE tenant_id IS NULL AND kind = ? AND id <> ?",
                (kind, keep_id),
            )
            return
        if user_id:
            self.database.execute(
                "UPDATE retrieval_providers SET is_default = 0"
                " WHERE tenant_id = ? AND user_id = ? AND kind = ? AND id <> ?",
                (tenant_id, user_id, kind, keep_id),
            )
            return
        self.database.execute(
            "UPDATE retrieval_providers SET is_default = 0"
            " WHERE tenant_id = ? AND (user_id = '' OR user_id IS NULL)"
            " AND kind = ? AND id <> ?",
            (tenant_id, kind, keep_id),
        )

    def get_setting(
        self, tenant_id: str, user_id: str, scope: str
    ) -> RetrievalSetting | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM retrieval_settings"
            " WHERE tenant_id = ? AND scope = ? AND user_id = ?",
            (tenant_id, scope, user_id),
        )
        return _to_setting(row) if row is not None else None

    def delete_setting(self, tenant_id: str, user_id: str, scope: str) -> bool:
        self.ensure_schema()
        cur = self.database.execute(
            "DELETE FROM retrieval_settings"
            " WHERE tenant_id = ? AND scope = ? AND user_id = ?",
            (tenant_id, scope, user_id or ""),
        )
        return bool(getattr(cur, "rowcount", 0))

    def save_setting(self, setting: RetrievalSetting) -> RetrievalSetting:
        self.ensure_schema()
        now = int(setting.updated_at or time.time())
        self.database.execute(
            """
            INSERT INTO retrieval_settings
                (tenant_id, user_id, scope, embedding_provider_id,
                 rerank_provider_id, vector_weight, rerank_weight, rerank_top_n,
                 updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, scope, user_id) DO UPDATE SET
                embedding_provider_id = excluded.embedding_provider_id,
                rerank_provider_id = excluded.rerank_provider_id,
                vector_weight = excluded.vector_weight,
                rerank_weight = excluded.rerank_weight,
                rerank_top_n = excluded.rerank_top_n,
                updated_at = excluded.updated_at
            """,
            (
                setting.tenant_id,
                setting.user_id or "",
                setting.scope,
                setting.embedding_provider_id,
                setting.rerank_provider_id,
                setting.vector_weight,
                setting.rerank_weight,
                setting.rerank_top_n,
                now,
            ),
        )
        stored = self.get_setting(
            setting.tenant_id, setting.user_id or "", setting.scope
        )
        return stored or setting


__all__ = ["DatabaseRetrievalRepository", "SCHEMA"]
