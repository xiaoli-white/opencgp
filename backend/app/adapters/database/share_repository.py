from __future__ import annotations

import time
import uuid
from typing import Any, Mapping

from app.models.share_link import ShareLink
from app.ports.database import Database
from app.ports.share_repository import ShareRepository

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS share_links (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        resource_type TEXT NOT NULL DEFAULT '',
        resource_id TEXT NOT NULL DEFAULT '',
        token TEXT NOT NULL UNIQUE,
        expires_at REAL NOT NULL DEFAULT 0,
        revoked INTEGER NOT NULL DEFAULT 0,
        view_count INTEGER NOT NULL DEFAULT 0,
        created_by TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_share_links_resource ON share_links(resource_type, resource_id)",
    "CREATE INDEX IF NOT EXISTS idx_share_links_tenant ON share_links(tenant_id, created_at)",
)


class DatabaseShareRepository(ShareRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._ready = False

    def ensure_schema(self) -> None:
        if self._ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        self._ready = True

    def create(self, link: ShareLink) -> ShareLink:
        self.ensure_schema()
        record = link.model_copy(
            update={
                "id": link.id or f"share_{uuid.uuid4().hex[:16]}",
                "created_at": link.created_at or time.time(),
            }
        )
        self.database.execute(
            "INSERT INTO share_links (id, tenant_id, resource_type, resource_id, token,"
            " expires_at, revoked, view_count, created_by, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.tenant_id,
                record.resource_type,
                record.resource_id,
                record.token,
                record.expires_at,
                int(record.revoked),
                record.view_count,
                record.created_by,
                record.created_at,
            ),
        )
        return record

    def get(self, link_id: str) -> ShareLink | None:
        self.ensure_schema()
        row = self.database.fetchone("SELECT * FROM share_links WHERE id = ?", (link_id,))
        return _to_link(row) if row else None

    def get_by_token(self, token: str) -> ShareLink | None:
        self.ensure_schema()
        row = self.database.fetchone("SELECT * FROM share_links WHERE token = ?", (token,))
        return _to_link(row) if row else None

    def list(
        self, tenant_id: str, resource_type: str = "", resource_id: str = ""
    ) -> list[ShareLink]:
        self.ensure_schema()
        sql = "SELECT * FROM share_links WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]
        if resource_type:
            sql += " AND resource_type = ?"
            params.append(resource_type)
        if resource_id:
            sql += " AND resource_id = ?"
            params.append(resource_id)
        sql += " ORDER BY created_at DESC"
        return [_to_link(row) for row in self.database.fetchall(sql, tuple(params))]

    def revoke(self, link_id: str, tenant_id: str) -> bool:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT id FROM share_links WHERE id = ? AND tenant_id = ?",
            (link_id, tenant_id),
        )
        if row is None:
            return False
        self.database.execute("UPDATE share_links SET revoked = 1 WHERE id = ?", (link_id,))
        return True

    def count_views(self, token: str) -> None:
        self.ensure_schema()
        self.database.execute(
            "UPDATE share_links SET view_count = view_count + 1 WHERE token = ?", (token,)
        )

    def healthcheck(self) -> bool:
        try:
            self.ensure_schema()
            return True
        except Exception:
            return False


def _to_link(row: Mapping[str, Any]) -> ShareLink:
    data = dict(row)
    return ShareLink(
        id=str(data["id"]),
        tenant_id=str(data.get("tenant_id") or ""),
        resource_type=str(data.get("resource_type") or ""),
        resource_id=str(data.get("resource_id") or ""),
        token=str(data.get("token") or ""),
        expires_at=float(data.get("expires_at") or 0.0),
        revoked=bool(data.get("revoked")),
        view_count=int(data.get("view_count") or 0),
        created_by=str(data.get("created_by") or ""),
        created_at=float(data.get("created_at") or 0.0),
    )
