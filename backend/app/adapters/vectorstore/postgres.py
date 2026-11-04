from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any, Sequence

from app.models.auth import DEFAULT_TENANT_ID
from app.models.chunk import Chunk
from app.models.citation import Citation
from app.ports.database import Database
from app.ports.vectorstore import VectorStore
from app.services.scoring import (
    LIKE_MATCH_SCORE,
    matched_terms,
    rank_with_coverage,
    select_top,
    term_score,
)
from app.services.textproc import make_snippet, query_terms

MAX_QUERY_TERMS = 12

_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS vs_sources (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        source_name TEXT NOT NULL DEFAULT '',
        chunk_count INTEGER NOT NULL DEFAULT 0,
        char_count INTEGER NOT NULL DEFAULT 0,
        object_key TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL DEFAULT 0,
        meta_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS vs_chunks (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT '',
        chunk_index INTEGER NOT NULL DEFAULT 0,
        text TEXT NOT NULL DEFAULT '',
        text_lower TEXT NOT NULL DEFAULT '',
        object_key TEXT NOT NULL DEFAULT '',
        meta_json TEXT NOT NULL DEFAULT '{}',
        start_offset INTEGER NOT NULL DEFAULT 0,
        end_offset INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_vs_chunks_tenant ON vs_chunks(tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_vs_chunks_source ON vs_chunks(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_vs_sources_tenant ON vs_sources(tenant_id)",
)

_TRGM_EXTENSION = "CREATE EXTENSION IF NOT EXISTS pg_trgm"
_TRGM_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_vs_chunks_trgm"
    " ON vs_chunks USING gin (text_lower gin_trgm_ops)"
)


class PostgresVectorStore(VectorStore):
    name = "postgres"

    def __init__(
        self,
        database: Database,
        keyword_weight: float = 0.65,
        min_relative_score: float = 0.2,
        min_relative_coverage: float = 0.5,
        max_scan_rows: int = 400,
    ) -> None:
        self.db = database
        self.keyword_weight = keyword_weight
        self.min_relative_score = min_relative_score
        self.min_relative_coverage = min_relative_coverage
        self.max_scan_rows = max(1, int(max_scan_rows))
        self.last_warning = ""
        self.trigram_index = False
        self._schema_lock = threading.Lock()
        self._schema_ready = False

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            for statement in _SCHEMA:
                self.db.execute(statement)
            try:
                self.db.execute(_TRGM_EXTENSION)
                self.db.execute(_TRGM_INDEX)
                self.trigram_index = True
            except Exception as exc:  # noqa: BLE001
                self.trigram_index = False
                self.last_warning = f"pg_trgm 不可用，退回 LIKE 全扫: {exc!r}"[:200]
            self._schema_ready = True

    async def add_chunks(
        self,
        source_id: str,
        chunks: Sequence[Chunk],
        tenant_id: str = "",
    ) -> int:
        items = list(chunks)
        if not items:
            return 0
        return await asyncio.to_thread(self._write_sync, source_id, items, tenant_id)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        source_ids: Sequence[str] | None = None,
        tenant_id: str = "",
        min_score: float | None = None,
    ) -> list[Citation]:
        if not query or not query.strip() or top_k <= 0:
            return []
        scope = [sid for sid in (source_ids or []) if sid]
        return await asyncio.to_thread(
            self._search_sync,
            query.strip(),
            top_k,
            scope or None,
            tenant_id,
            min_score,
        )

    async def delete_by_source(self, source_id: str, tenant_id: str = "") -> int:
        return await asyncio.to_thread(self._delete_sync, source_id, tenant_id)

    async def list_sources(self, tenant_id: str = "") -> list[dict]:
        return await asyncio.to_thread(self._list_sources_sync, tenant_id)

    async def rename_source(
        self, source_id: str, source_name: str, tenant_id: str = ""
    ) -> bool:
        return await asyncio.to_thread(
            self._rename_sync, source_id, source_name, tenant_id
        )

    def healthcheck(self) -> bool:
        try:
            self._ensure_schema()
            self.db.fetchone("SELECT count(*) AS total FROM vs_chunks")
        except Exception:  # noqa: BLE001
            return False
        return bool(self.db.healthcheck())

    def _write_sync(
        self, source_id: str, chunks: list[Chunk], tenant_id: str
    ) -> int:
        self._ensure_schema()
        scope = _tenant_scope(tenant_id)
        now = time.time()
        object_key = str(chunks[0].meta.get("object_key") or "")
        self._delete_sync(source_id, scope, guarded=True)
        for chunk in chunks:
            self.db.execute(
                "INSERT INTO vs_chunks (id, source_id, tenant_id, chunk_index, text,"
                " text_lower, object_key, meta_json, start_offset, end_offset, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk.chunk_id,
                    source_id,
                    scope,
                    chunk.chunk_index,
                    chunk.text,
                    chunk.text.lower(),
                    object_key,
                    json.dumps(chunk.meta, ensure_ascii=False),
                    chunk.start,
                    chunk.end,
                    now,
                ),
            )
        self.db.execute(
            "INSERT INTO vs_sources (id, tenant_id, source_name, chunk_count,"
            " char_count, object_key, created_at, meta_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                source_id,
                scope,
                chunks[0].source_name,
                len(chunks),
                sum(len(chunk.text) for chunk in chunks),
                object_key,
                now,
                json.dumps(
                    {"meta": chunks[0].meta, "object_key": object_key},
                    ensure_ascii=False,
                ),
            ),
        )
        return len(chunks)

    def _delete_sync(
        self, source_id: str, tenant_id: str = "", guarded: bool = False
    ) -> int:
        if not guarded:
            self._ensure_schema()
        clause, params = _tenant_filter_plain(tenant_id)
        row = self.db.fetchone(
            f"SELECT count(*) AS total FROM vs_chunks WHERE source_id = ?{clause}",
            [source_id, *params],
        )
        removed = int((row or {}).get("total") or 0)
        self.db.execute(
            f"DELETE FROM vs_chunks WHERE source_id = ?{clause}", [source_id, *params]
        )
        self.db.execute(
            f"DELETE FROM vs_sources WHERE id = ?{clause}", [source_id, *params]
        )
        return removed

    def _list_sources_sync(self, tenant_id: str = "") -> list[dict]:
        self._ensure_schema()
        clause, params = _tenant_filter_plain(tenant_id)
        rows = self.db.fetchall(
            "SELECT id, source_name, chunk_count, char_count, tenant_id, created_at,"
            f" object_key FROM vs_sources WHERE 1 = 1{clause} ORDER BY created_at DESC",
            list(params),
        )
        return [
            {
                "source_id": str(row.get("id") or ""),
                "source_name": str(row.get("source_name") or ""),
                "chunk_count": int(row.get("chunk_count") or 0),
                "char_count": int(row.get("char_count") or 0),
                "tenant_id": str(row.get("tenant_id") or ""),
                "created_at": float(row.get("created_at") or 0.0),
                "object_key": str(row.get("object_key") or ""),
            }
            for row in rows
        ]

    def _rename_sync(
        self, source_id: str, source_name: str, tenant_id: str = ""
    ) -> bool:
        name = (source_name or "").strip()
        if not name:
            return False
        self._ensure_schema()
        clause, params = _tenant_filter_plain(tenant_id)
        row = self.db.fetchone(
            f"SELECT id FROM vs_sources WHERE id = ?{clause}", [source_id, *params]
        )
        if row is None:
            return False
        self.db.execute(
            "UPDATE vs_sources SET source_name = ? WHERE id = ?", (name, source_id)
        )
        return True

    def _search_sync(
        self,
        query: str,
        top_k: int,
        source_ids: Sequence[str] | None,
        tenant_id: str,
        min_score: float | None,
    ) -> list[Citation]:
        self._ensure_schema()
        terms = query_terms(query)[:MAX_QUERY_TERMS]
        limit = max(top_k * 8, 40)
        rows = self._candidates(terms, limit, source_ids, tenant_id)
        like_only = False
        if not rows and query:
            rows = self._like_candidates(query, limit, source_ids, tenant_id)
            like_only = True
        if not rows:
            return []
        scores: dict[str, float] = {}
        texts: dict[str, str] = {}
        by_id: dict[str, dict] = {}
        for row in rows:
            chunk_id = str(row.get("id") or "")
            if not chunk_id:
                continue
            text = str(row.get("text") or "")
            texts[chunk_id] = text
            by_id[chunk_id] = row
            if like_only:
                scores[chunk_id] = LIKE_MATCH_SCORE
                continue
            raw = float(matched_terms(terms, text))
            scores[chunk_id] = term_score(
                terms, text, str(row.get("source_name") or ""), raw
            )
        ranked, covs = rank_with_coverage(scores, texts, terms)
        selected = select_top(
            ranked, covs, top_k, self.min_relative_score, self.min_relative_coverage
        )
        citations: list[Citation] = []
        for chunk_id, score in selected:
            row = by_id.get(chunk_id)
            if row is None:
                continue
            citations.append(
                Citation(
                    source_id=str(row.get("source_id") or ""),
                    source_name=str(row.get("source_name") or ""),
                    chunk_id=chunk_id,
                    chunk_index=int(row.get("chunk_index") or 0),
                    text=texts.get(chunk_id, ""),
                    snippet=make_snippet(texts.get(chunk_id, ""), terms),
                    score=round(float(score), 6),
                    start=int(row.get("start_offset") or 0),
                    end=int(row.get("end_offset") or 0),
                    meta=_load_meta(row.get("meta_json")),
                )
            )
        if min_score is not None:
            threshold = float(min_score)
            citations = [item for item in citations if item.score >= threshold]
        return citations

    def _candidates(
        self,
        terms: Sequence[str],
        limit: int,
        source_ids: Sequence[str] | None,
        tenant_id: str,
    ) -> list[dict]:
        if not terms:
            return []
        clause, params = _tenant_filter(tenant_id)
        conditions = " OR ".join("c.text_lower LIKE ?" for _ in terms)
        sql = (
            "SELECT c.id, c.source_id, c.chunk_index, c.text, c.start_offset,"
            " c.end_offset, c.meta_json, s.source_name"
            " FROM vs_chunks c LEFT JOIN vs_sources s ON s.id = c.source_id"
            f" WHERE 1 = 1{clause} AND ({conditions})"
        )
        values: list[Any] = [*params, *(f"%{term.lower()}%" for term in terms)]
        if source_ids:
            sql += f" AND c.source_id IN ({','.join('?' for _ in source_ids)})"
            values.extend(source_ids)
        sql += " LIMIT ?"
        values.append(self.max_scan_rows)
        try:
            return list(self.db.fetchall(sql, values))
        except Exception:  # noqa: BLE001
            return []

    def _like_candidates(
        self,
        query: str,
        limit: int,
        source_ids: Sequence[str] | None,
        tenant_id: str,
    ) -> list[dict]:
        clause, params = _tenant_filter(tenant_id)
        sql = (
            "SELECT c.id, c.source_id, c.chunk_index, c.text, c.start_offset,"
            " c.end_offset, c.meta_json, s.source_name"
            " FROM vs_chunks c LEFT JOIN vs_sources s ON s.id = c.source_id"
            f" WHERE 1 = 1{clause} AND c.text_lower LIKE ?"
        )
        values: list[Any] = [*params, f"%{query.lower()}%"]
        if source_ids:
            sql += f" AND c.source_id IN ({','.join('?' for _ in source_ids)})"
            values.extend(source_ids)
        sql += " LIMIT ?"
        values.append(limit)
        try:
            return list(self.db.fetchall(sql, values))
        except Exception:  # noqa: BLE001
            return []


def _tenant_scope(tenant_id: str) -> str:
    value = (tenant_id or "").strip()
    return value or DEFAULT_TENANT_ID


def _tenant_filter(tenant_id: str) -> tuple[str, list[Any]]:
    scope = _tenant_scope(tenant_id)
    if scope == DEFAULT_TENANT_ID:
        return " AND (c.tenant_id = ? OR c.tenant_id = '')", [DEFAULT_TENANT_ID]
    return " AND c.tenant_id = ?", [scope]


def _tenant_filter_plain(tenant_id: str) -> tuple[str, list[Any]]:
    scope = _tenant_scope(tenant_id)
    if scope == DEFAULT_TENANT_ID:
        return " AND (tenant_id = ? OR tenant_id = '')", [DEFAULT_TENANT_ID]
    return " AND tenant_id = ?", [scope]


def _load_meta(value: Any) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}
