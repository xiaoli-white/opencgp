from __future__ import annotations

import time
from typing import Any, Mapping

from app.models.media import MediaAsset
from app.ports.database import Database
from app.ports.media_repository import MediaRepository

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS media_assets (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        user_id TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL DEFAULT 'uploaded',
        prompt TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT 'upload',
        object_key TEXT NOT NULL DEFAULT '',
        content_type TEXT NOT NULL DEFAULT 'image/png',
        bytes INTEGER NOT NULL DEFAULT 0,
        width INTEGER NOT NULL DEFAULT 0,
        height INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_media_assets_tenant ON media_assets(tenant_id, created_at)",
)


class DatabaseMediaRepository(MediaRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        self._schema_ready = True

    def create(self, asset: MediaAsset) -> MediaAsset:
        self.ensure_schema()
        item = asset.model_copy(update={"created_at": asset.created_at or time.time()})
        self.database.execute(
            "INSERT INTO media_assets (id, tenant_id, user_id, kind, prompt, source,"
            " object_key, content_type, bytes, width, height, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id,
                item.tenant_id,
                item.user_id,
                item.kind,
                item.prompt,
                item.source,
                item.object_key,
                item.content_type,
                int(item.bytes),
                int(item.width),
                int(item.height),
                item.created_at,
            ),
        )
        return item

    def get(self, asset_id: str, tenant_id: str | None = None) -> MediaAsset | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM media_assets WHERE id = ?", (asset_id,)
        )
        if row is None:
            return None
        item = _to_asset(row)
        if tenant_id and item.tenant_id and item.tenant_id != tenant_id:
            return None
        return item

    def list_assets(
        self, tenant_id: str, kind: str | None = None, limit: int = 50
    ) -> list[MediaAsset]:
        self.ensure_schema()
        size = max(1, min(int(limit or 50), 200))
        if kind:
            rows = self.database.fetchall(
                "SELECT * FROM media_assets WHERE tenant_id = ? AND kind = ?"
                " ORDER BY created_at DESC LIMIT ?",
                (tenant_id, kind, size),
            )
        else:
            rows = self.database.fetchall(
                "SELECT * FROM media_assets WHERE tenant_id = ?"
                " ORDER BY created_at DESC LIMIT ?",
                (tenant_id, size),
            )
        return [_to_asset(row) for row in rows]

    def delete(self, asset_id: str, tenant_id: str | None = None) -> bool:
        self.ensure_schema()
        if self.get(asset_id, tenant_id) is None:
            return False
        self.database.execute("DELETE FROM media_assets WHERE id = ?", (asset_id,))
        return True


def _to_asset(row: Mapping[str, Any]) -> MediaAsset:
    return MediaAsset(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"] or ""),
        user_id=str(row["user_id"] or ""),
        kind=str(row["kind"] or "uploaded"),
        prompt=str(row["prompt"] or ""),
        source=str(row["source"] or "upload"),
        object_key=str(row["object_key"] or ""),
        content_type=str(row["content_type"] or "image/png"),
        bytes=int(row["bytes"] or 0),
        width=int(row["width"] or 0),
        height=int(row["height"] or 0),
        created_at=float(row["created_at"] or 0.0),
    )
