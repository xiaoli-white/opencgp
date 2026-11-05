from __future__ import annotations

import asyncio
import heapq
import json
import threading
import time
from typing import Any, Sequence

from app.models.auth import DEFAULT_TENANT_ID
from app.models.chunk import Chunk
from app.models.citation import Citation
from app.ports.database import Database
from app.ports.embedding import EmbeddingProvider
from app.ports.vectorstore import VectorStore
from app.services.scoring import (
    LIKE_MATCH_SCORE,
    matched_terms,
    rank_with_coverage,
    select_top,
    term_score,
)
from app.services.lsh import neighbor_buckets, project_bucket
from app.services.textproc import make_snippet, query_terms
from app.services.vector_math import (
    cache_key,
    cached_cosine,
    clear_vector_cache,
    clear_vector_cache_entry,
    pack_vector,
    unpack_vector,
)

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
    """
    CREATE TABLE IF NOT EXISTS chunk_embeddings (
        chunk_id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL DEFAULT '',
        tenant_id TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT '',
        dim INTEGER NOT NULL DEFAULT 0,
        vec BLOB,
        bucket INTEGER NOT NULL DEFAULT 0,
        updated_at INTEGER NOT NULL DEFAULT 0
    )
    """,
    "ALTER TABLE chunk_embeddings ADD COLUMN IF NOT EXISTS bucket INTEGER NOT NULL DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_tenant ON chunk_embeddings(tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_updated ON chunk_embeddings(updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_lsh ON chunk_embeddings(tenant_id, model, dim, bucket)",
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
        embedder: EmbeddingProvider | None = None,
        vector_weight: float = 0.55,
        max_vector_rows: int = 200000,
        lsh_bits: int = 12,
    ) -> None:
        self.db = database
        self.keyword_weight = keyword_weight
        self.min_relative_score = min_relative_score
        self.min_relative_coverage = min_relative_coverage
        self.max_scan_rows = max(1, int(max_scan_rows))
        self.embedder = embedder
        self.vector_weight = min(1.0, max(0.0, float(vector_weight)))
        self.max_vector_rows = max(1, int(max_vector_rows))
        self.lsh_bits = max(1, min(32, int(lsh_bits)))
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
        query_vector = None
        if self.embedder is not None:
            try:
                embed_query = getattr(self.embedder, "embed_query", None)
                if callable(embed_query):
                    vector = await embed_query(query.strip())
                else:
                    vectors = await self.embedder.embed([query.strip()])
                    vector = vectors[0] if vectors else None
                query_vector = list(vector) if vector else None
            except Exception as exc:
                print(f"[vectorstore] 查询向量化失败，降级为关键词检索: {exc!r}")
                query_vector = None
        return await asyncio.to_thread(
            self._search_sync,
            query.strip(),
            top_k,
            scope or None,
            tenant_id,
            min_score,
            query_vector,
        )

    async def search_vector(
        self, tenant_id: str, query_vec: Sequence[float], limit: int = 10
    ) -> list[tuple[str, float]]:
        if not query_vec or limit <= 0:
            return []
        return await asyncio.to_thread(
            self._search_vector_sync,
            tenant_id,
            [float(value) for value in query_vec],
            limit,
            None,
        )

    async def upsert_embeddings(self, rows: Sequence[dict]) -> int:
        return await asyncio.to_thread(self._upsert_embeddings_sync, list(rows))

    async def list_chunks(
        self, tenant_id: str = "", source_id: str = ""
    ) -> list[dict]:
        return await asyncio.to_thread(self._list_chunks_sync, tenant_id, source_id)

    async def embedded_index(
        self, tenant_id: str = "", source_id: str = ""
    ) -> dict[str, tuple[str, int]]:
        return await asyncio.to_thread(self._embedded_index_sync, tenant_id, source_id)

    async def embedding_status(
        self, tenant_id: str = "", model: str = "", dim: int = 0
    ) -> dict:
        return await asyncio.to_thread(
            self._embedding_status_sync, tenant_id, model, dim
        )

    async def purge_stale_embeddings(
        self, tenant_id: str, model: str, dim: int
    ) -> dict:
        return await asyncio.to_thread(
            self._purge_stale_embeddings_sync, tenant_id, model, dim
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
            "DELETE FROM chunk_embeddings WHERE source_id = ?", (source_id,)
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
        query_vector: Sequence[float] | None = None,
    ) -> list[Citation]:
        self._ensure_schema()
        terms = query_terms(query)[:MAX_QUERY_TERMS]
        rows = self._candidates(terms, max(top_k * 8, 40), source_ids, tenant_id)
        like_only = False
        if not rows and query:
            rows = self._like_candidates(query, max(top_k * 8, 40), source_ids, tenant_id)
            like_only = True
        if not rows:
            return []
        keyword_scores, texts, by_id = self._score_rows(rows, terms, like_only)
        if query_vector is None:
            return self._finish_keyword(
                top_k, terms, keyword_scores, texts, by_id, min_score
            )
        vector_scores = dict(
            self._search_vector_sync(
                tenant_id, query_vector, max(top_k * 3, 1), source_ids
            )
        )
        if not vector_scores:
            return self._finish_keyword(
                top_k, terms, keyword_scores, texts, by_id, min_score
            )
        missing = [cid for cid in vector_scores if cid not in by_id]
        if missing:
            for row in self._rows_by_ids(missing, tenant_id):
                cid = str(row.get("id") or "")
                if not cid:
                    continue
                by_id[cid] = row
                texts[cid] = str(row.get("text") or "")
        best_keyword = max(keyword_scores.values()) if keyword_scores else 0.0
        if keyword_scores:
            trimmed = sorted(
                keyword_scores.items(), key=lambda item: item[1], reverse=True
            )[: max(top_k * 3, 1)]
            keyword_scores = dict(trimmed)
        weight = self.vector_weight
        merged: dict[str, float] = {}
        for chunk_id in set(keyword_scores) | set(vector_scores):
            keyword = keyword_scores.get(chunk_id, 0.0)
            keyword_norm = keyword / best_keyword if best_keyword > 0 else 0.0
            vector_norm = (max(-1.0, min(1.0, vector_scores.get(chunk_id, 0.0))) + 1.0) / 2.0
            merged[chunk_id] = (1.0 - weight) * keyword_norm + weight * vector_norm
        ranked = sorted(merged.items(), key=lambda item: item[1], reverse=True)[:top_k]
        citations: list[Citation] = []
        for chunk_id, score in ranked:
            row = by_id.get(chunk_id)
            if row is None:
                continue
            text = texts.get(chunk_id, "")
            citations.append(
                Citation(
                    source_id=str(row.get("source_id") or ""),
                    source_name=str(row.get("source_name") or ""),
                    chunk_id=chunk_id,
                    chunk_index=int(row.get("chunk_index") or 0),
                    text=text,
                    snippet=make_snippet(text, terms),
                    score=round(float(score), 6),
                    start=int(row.get("start_offset") or 0),
                    end=int(row.get("end_offset") or 0),
                    meta=_load_meta(row.get("meta_json")),
                    keyword_score=round(float(keyword_scores.get(chunk_id, 0.0)), 6),
                    vector_score=round(float(vector_scores.get(chunk_id, 0.0)), 6),
                )
            )
        if min_score is not None:
            threshold = float(min_score)
            citations = [item for item in citations if item.score >= threshold]
        return citations

    def _score_rows(
        self,
        rows: Sequence[dict],
        terms: Sequence[str],
        like_only: bool,
    ) -> tuple[dict[str, float], dict[str, str], dict[str, dict]]:
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
        return scores, texts, by_id

    def _finish_keyword(
        self,
        top_k: int,
        terms: Sequence[str],
        scores: dict[str, float],
        texts: dict[str, str],
        by_id: dict[str, dict],
        min_score: float | None,
    ) -> list[Citation]:
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
                    keyword_score=round(float(scores.get(chunk_id, 0.0)), 6),
                )
            )
        if min_score is not None:
            threshold = float(min_score)
            citations = [item for item in citations if item.score >= threshold]
        return citations

    def _rows_by_ids(self, ids: Sequence[str], tenant_id: str) -> list[dict]:
        if not ids:
            return []
        self._ensure_schema()
        clause, params = _tenant_filter(tenant_id)
        placeholders = ",".join("?" for _ in ids)
        sql = (
            "SELECT c.id, c.source_id, c.chunk_index, c.text, c.start_offset,"
            " c.end_offset, c.meta_json, s.source_name"
            " FROM vs_chunks c LEFT JOIN vs_sources s ON s.id = c.source_id"
            f" WHERE c.id IN ({placeholders}){clause}"
        )
        try:
            return list(self.db.fetchall(sql, [*ids, *params]))
        except Exception:
            return []

    def _search_vector_sync(
        self,
        tenant_id: str,
        query_vec: Sequence[float],
        limit: int,
        source_ids: Sequence[str] | None,
    ) -> list[tuple[str, float]]:
        return self._search_vector_ranked(
            tenant_id, query_vec, limit, source_ids, use_lsh=True
        )

    def _search_vector_scan_sync(
        self,
        tenant_id: str,
        query_vec: Sequence[float],
        limit: int,
        source_ids: Sequence[str] | None,
    ) -> list[tuple[str, float]]:
        return self._search_vector_ranked(
            tenant_id, query_vec, limit, source_ids, use_lsh=False
        )

    def _search_vector_ranked(
        self,
        tenant_id: str,
        query_vec: Sequence[float],
        limit: int,
        source_ids: Sequence[str] | None,
        use_lsh: bool,
    ) -> list[tuple[str, float]]:
        self._ensure_schema()
        clause, params = _tenant_filter_plain(tenant_id)
        values: list[Any] = [*params]
        model = ""
        dim = 0
        filters = ""
        if self.embedder is not None:
            model = self.embedder.model
            dim = int(self.embedder.dim)
            filters += " AND model = ? AND dim = ?"
            values.extend([model, dim])
        if source_ids:
            filters += f" AND source_id IN ({','.join('?' for _ in source_ids)})"
            values.extend(source_ids)
        cap = max(1, int(limit))
        if use_lsh and model:
            buckets = neighbor_buckets(
                project_bucket(model, query_vec, self.lsh_bits), self.lsh_bits
            )
            placeholders = ",".join("?" for _ in buckets)
            sql = (
                "SELECT chunk_id, model, dim, vec FROM chunk_embeddings"
                " WHERE vec IS NOT NULL" + clause + filters
                + f" AND bucket IN ({placeholders}) LIMIT ?"
            )
            try:
                rows = list(self.db.fetchall(sql, [*values, *buckets, self.max_vector_rows]))
            except Exception:
                rows = []
            if len(rows) >= cap:
                return self._rank_vector_rows(rows, query_vec, cap)
        sql = (
            "SELECT chunk_id, model, dim, vec FROM chunk_embeddings"
            " WHERE vec IS NOT NULL" + clause + filters
            + " ORDER BY updated_at DESC LIMIT ?"
        )
        try:
            rows = list(self.db.fetchall(sql, [*values, self.max_vector_rows]))
        except Exception:
            return []
        return self._rank_vector_rows(rows, query_vec, cap)

    def _rank_vector_rows(
        self,
        rows: Sequence[dict],
        query_vec: Sequence[float],
        cap: int,
    ) -> list[tuple[str, float]]:
        best: list[tuple[float, str]] = []
        for row in rows:
            chunk_id = str(row.get("chunk_id") or "")
            if not chunk_id:
                continue
            key = cache_key(
                chunk_id,
                str(row.get("model") or ""),
                int(row.get("dim") or 0),
            )
            score = cached_cosine(key, query_vec, row.get("vec"))
            if len(best) < cap:
                heapq.heappush(best, (score, chunk_id))
            elif score > best[0][0]:
                heapq.heapreplace(best, (score, chunk_id))
        return [
            (chunk_id, float(score))
            for score, chunk_id in sorted(best, key=lambda item: item[0], reverse=True)
        ]

    def _upsert_embeddings_sync(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        self._ensure_schema()
        now = int(time.time())
        written = 0
        for row in rows:
            chunk_id = str(row.get("chunk_id") or "")
            if not chunk_id:
                continue
            vec = row.get("vec")
            if isinstance(vec, memoryview):
                blob = vec.tobytes()
            elif isinstance(vec, (bytes, bytearray)):
                blob = bytes(vec)
            else:
                blob = pack_vector(vec or [])
            dim = int(row.get("dim") or (len(blob) // 4))
            model = str(row.get("model") or "")
            bucket = project_bucket(model, unpack_vector(blob), self.lsh_bits)
            self.db.execute(
                "INSERT OR REPLACE INTO chunk_embeddings"
                " (chunk_id, source_id, tenant_id, model, dim, vec, bucket, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chunk_id,
                    str(row.get("source_id") or ""),
                    _tenant_scope(str(row.get("tenant_id") or "")),
                    model,
                    dim,
                    blob,
                    bucket,
                    int(row.get("updated_at") or now),
                ),
            )
            clear_vector_cache_entry(chunk_id, model, dim)
            written += 1
        return written

    def _list_chunks_sync(
        self, tenant_id: str = "", source_id: str = ""
    ) -> list[dict]:
        self._ensure_schema()
        clause, params = _tenant_filter(tenant_id)
        sql = (
            "SELECT c.id, c.source_id, c.tenant_id, c.text FROM vs_chunks c"
            f" WHERE 1 = 1{clause}"
        )
        values: list[Any] = [*params]
        if source_id:
            sql += " AND c.source_id = ?"
            values.append(source_id)
        sql += " ORDER BY c.created_at, c.chunk_index"
        try:
            rows = list(self.db.fetchall(sql, values))
        except Exception:
            return []
        return [
            {
                "chunk_id": str(row.get("id") or ""),
                "source_id": str(row.get("source_id") or ""),
                "tenant_id": str(row.get("tenant_id") or ""),
                "text": str(row.get("text") or ""),
            }
            for row in rows
        ]

    def _embedded_index_sync(
        self, tenant_id: str = "", source_id: str = ""
    ) -> dict[str, tuple[str, int]]:
        self._ensure_schema()
        clause, params = _tenant_filter_plain(tenant_id)
        sql = "SELECT chunk_id, model, dim FROM chunk_embeddings WHERE 1 = 1" + clause
        values: list[Any] = [*params]
        if source_id:
            sql += " AND source_id = ?"
            values.append(source_id)
        try:
            rows = list(self.db.fetchall(sql, values))
        except Exception:
            return {}
        return {
            str(row.get("chunk_id") or ""): (
                str(row.get("model") or ""),
                int(row.get("dim") or 0),
            )
            for row in rows
        }

    def _embedding_status_sync(
        self, tenant_id: str = "", model: str = "", dim: int = 0
    ) -> dict:
        self._ensure_schema()
        clause, params = _tenant_filter(tenant_id)
        embedding_clause = clause.replace("c.tenant_id", "e.tenant_id")
        try:
            total_row = self.db.fetchone(
                f"SELECT count(*) AS total FROM vs_chunks c WHERE 1 = 1{clause}",
                list(params),
            )
            embedded_row = self.db.fetchone(
                "SELECT count(*) AS total FROM chunk_embeddings e"
                " JOIN vs_chunks c ON c.id = e.chunk_id"
                " WHERE 1 = 1" + clause + " AND e.model = ? AND e.dim = ?",
                [*params, model, int(dim)],
            )
            group_rows = list(
                self.db.fetchall(
                    "SELECT e.model AS model, e.dim AS dim, count(*) AS chunks"
                    " FROM chunk_embeddings e WHERE 1 = 1" + embedding_clause
                    + " GROUP BY e.model, e.dim ORDER BY chunks DESC, e.model",
                    list(params),
                )
            )
            stale_row = self.db.fetchone(
                "SELECT count(*) AS chunks,"
                " COALESCE(SUM(COALESCE(LENGTH(e.vec), 0)), 0) AS bytes"
                " FROM chunk_embeddings e WHERE 1 = 1" + embedding_clause
                + " AND (e.model != ? OR e.dim != ?)",
                [*params, model, int(dim)],
            )
        except Exception:
            return {
                "chunks_total": 0,
                "chunks_embedded": 0,
                "models": [],
                "stale": {"chunks": 0, "bytes": 0},
            }
        return {
            "chunks_total": int((total_row or {}).get("total") or 0),
            "chunks_embedded": int((embedded_row or {}).get("total") or 0),
            "models": [
                {
                    "model": str(row.get("model") or ""),
                    "dim": int(row.get("dim") or 0),
                    "chunks": int(row.get("chunks") or 0),
                }
                for row in group_rows
            ],
            "stale": {
                "chunks": int((stale_row or {}).get("chunks") or 0),
                "bytes": int((stale_row or {}).get("bytes") or 0),
            },
        }

    def _purge_stale_embeddings_sync(
        self, tenant_id: str, model: str, dim: int
    ) -> dict:
        self._ensure_schema()
        clause, params = _tenant_filter(tenant_id)
        embedding_clause = clause.replace("c.tenant_id", "e.tenant_id")
        values = [*params, model, int(dim)]
        try:
            row = self.db.fetchone(
                "SELECT count(*) AS chunks,"
                " COALESCE(SUM(COALESCE(LENGTH(e.vec), 0)), 0) AS bytes"
                " FROM chunk_embeddings e WHERE 1 = 1" + embedding_clause
                + " AND (e.model != ? OR e.dim != ?)",
                values,
            )
        except Exception:
            row = None
        deleted = int((row or {}).get("chunks") or 0)
        freed = int((row or {}).get("bytes") or 0)
        self.db.execute(
            "DELETE FROM chunk_embeddings e WHERE 1 = 1" + embedding_clause
            + " AND (e.model != ? OR e.dim != ?)",
            values,
        )
        clear_vector_cache()
        return {"deleted": deleted, "freed_bytes": freed}

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
