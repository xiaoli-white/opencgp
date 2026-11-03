from __future__ import annotations

import time
import uuid
from typing import Any, Mapping

from app.models.creation_profile import CreationProfile
from app.ports.creation_profile_repository import CreationProfileRepository
from app.ports.database import Database

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS creation_profiles (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        user_id TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL DEFAULT '',
        genre TEXT NOT NULL DEFAULT 'article',
        tone TEXT NOT NULL DEFAULT '',
        audience TEXT NOT NULL DEFAULT '',
        pov TEXT NOT NULL DEFAULT '',
        citation_policy TEXT NOT NULL DEFAULT 'optional',
        target_words INTEGER NOT NULL DEFAULT 3000,
        is_shared INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_creation_profiles_tenant ON creation_profiles(tenant_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_creation_profiles_user ON creation_profiles(user_id)",
)


class DatabaseCreationProfileRepository(CreationProfileRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        self._schema_ready = True

    def create(self, profile: CreationProfile) -> CreationProfile:
        self.ensure_schema()
        now = time.time()
        item = profile.model_copy(
            update={
                "id": profile.id or f"profile_{uuid.uuid4().hex[:16]}",
                "created_at": profile.created_at or now,
                "updated_at": now,
            }
        )
        self.database.execute(
            "INSERT INTO creation_profiles (id, tenant_id, user_id, name, genre, tone,"
            " audience, pov, citation_policy, target_words, is_shared, created_at,"
            " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                item.id,
                item.tenant_id,
                item.user_id,
                item.name,
                item.genre,
                item.tone,
                item.audience,
                item.pov,
                item.citation_policy,
                int(item.target_words),
                1 if item.is_shared else 0,
                item.created_at,
                item.updated_at,
            ),
        )
        return item

    def get(
        self, profile_id: str, tenant_id: str | None = None
    ) -> CreationProfile | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM creation_profiles WHERE id = ?", (profile_id,)
        )
        if row is None:
            return None
        item = _to_profile(row)
        if tenant_id and item.tenant_id and item.tenant_id != tenant_id:
            return None
        return item

    def list_visible(self, tenant_id: str, user_id: str) -> list[CreationProfile]:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT * FROM creation_profiles WHERE tenant_id = ?"
            " AND (user_id = ? OR is_shared = 1) ORDER BY updated_at DESC",
            (tenant_id, user_id),
        )
        return [_to_profile(row) for row in rows]

    def update(
        self,
        profile_id: str,
        name: str | None = None,
        genre: str | None = None,
        tone: str | None = None,
        audience: str | None = None,
        pov: str | None = None,
        citation_policy: str | None = None,
        target_words: int | None = None,
        is_shared: bool | None = None,
    ) -> CreationProfile | None:
        self.ensure_schema()
        current = self.get(profile_id)
        if current is None:
            return None
        self.database.execute(
            "UPDATE creation_profiles SET name = ?, genre = ?, tone = ?, audience = ?,"
            " pov = ?, citation_policy = ?, target_words = ?, is_shared = ?,"
            " updated_at = ? WHERE id = ?",
            (
                current.name if name is None else name,
                current.genre if genre is None else genre,
                current.tone if tone is None else tone,
                current.audience if audience is None else audience,
                current.pov if pov is None else pov,
                current.citation_policy
                if citation_policy is None
                else citation_policy,
                int(current.target_words if target_words is None else target_words),
                1
                if (current.is_shared if is_shared is None else is_shared)
                else 0,
                time.time(),
                profile_id,
            ),
        )
        return self.get(profile_id)

    def delete(self, profile_id: str, tenant_id: str | None = None) -> bool:
        self.ensure_schema()
        if self.get(profile_id, tenant_id) is None:
            return False
        self.database.execute(
            "DELETE FROM creation_profiles WHERE id = ?", (profile_id,)
        )
        return True


def _to_profile(row: Mapping[str, Any]) -> CreationProfile:
    return CreationProfile(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"] or ""),
        user_id=str(row["user_id"] or ""),
        name=str(row["name"] or ""),
        genre=str(row["genre"] or "article"),
        tone=str(row["tone"] or ""),
        audience=str(row["audience"] or ""),
        pov=str(row["pov"] or ""),
        citation_policy=str(row["citation_policy"] or "optional"),
        target_words=int(row["target_words"] or 3000),
        is_shared=bool(row["is_shared"]),
        created_at=float(row["created_at"] or 0.0),
        updated_at=float(row["updated_at"] or 0.0),
    )
