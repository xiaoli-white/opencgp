from __future__ import annotations

import asyncio
import heapq
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Sequence

from app.models.auth import DEFAULT_TENANT_ID
from app.models.chunk import Chunk
from app.models.citation import Citation
from app.ports.embedding import EmbeddingProvider
from app.ports.vectorstore import VectorStore
from app.services.scoring import (
    LIKE_MATCH_SCORE,
    rank_with_coverage,
    select_top,
    term_score,
)
from app.services.textproc import index_tokens, make_snippet, query_terms
from app.services.vector_math import pack_vector, packed_cosine

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS sources (
        source_id TEXT PRIMARY KEY,
        source_name TEXT NOT NULL,
        chunk_count INTEGER NOT NULL DEFAULT 0,
        char_count INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL,
        source_name TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        text TEXT NOT NULL,
        start_offset INTEGER NOT NULL,
        end_offset INTEGER NOT NULL,
        meta TEXT NOT NULL DEFAULT '{}',
        embedding TEXT,
        created_at REAL NOT NULL,
        tenant_id TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_id)",
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
        tokens,
        source_id UNINDEXED,
        chunk_id UNINDEXED,
        tokenize='unicode61'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunk_embeddings (
        chunk_id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL DEFAULT '',
        tenant_id TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT '',
        dim INTEGER NOT NULL DEFAULT 0,
        vec BLOB,
        updated_at INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_tenant ON chunk_embeddings(tenant_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_updated ON chunk_embeddings(updated_at)",
)


_COLUMN_MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("sources", "tenant_id", "TEXT NOT NULL DEFAULT ''"),
    ("chunks", "tenant_id", "TEXT NOT NULL DEFAULT ''"),
    ("sources", "object_key", "TEXT NOT NULL DEFAULT ''"),
)


class SimpleVectorStore(VectorStore):
    def __init__(
        self,
        path: str = "data/vectorstore",
        db_name: str = "chunks.db",
        embedder: EmbeddingProvider | None = None,
        keyword_weight: float = 0.65,
        min_relative_score: float = 0.2,
        min_relative_coverage: float = 0.5,
        max_scan_rows: int = 20000,
        vector_weight: float = 0.55,
        max_vector_rows: int = 20000,
    ) -> None:
        self.root = Path(path)
        self.db_path = self.root / db_name
        self.embedder = embedder
        self.keyword_weight = keyword_weight
        self.min_relative_score = min_relative_score
        self.min_relative_coverage = min_relative_coverage
        self.max_scan_rows = max_scan_rows
        self.vector_weight = min(1.0, max(0.0, float(vector_weight)))
        self.max_vector_rows = max(1, int(max_vector_rows))
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    def _connection(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                self.root.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                for statement in _SCHEMA:
                    conn.execute(statement)
                for table, column, ddl in _COLUMN_MIGRATIONS:
                    if not _has_column(conn, table, column):
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON chunks(tenant_id)"
                )
                conn.commit()
                self._conn = conn
            return self._conn

    async def add_chunks(
        self,
        source_id: str,
        chunks: Sequence[Chunk],
        tenant_id: str = "",
    ) -> int:
        items = list(chunks)
        if not items:
            return 0
        return await asyncio.to_thread(
            self._write_chunks, source_id, items, None, tenant_id
        )

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
            query_vector,
            tenant_id,
            min_score,
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

    async def embedding_status(self, tenant_id: str = "") -> dict:
        return await asyncio.to_thread(self._embedding_status_sync, tenant_id)

    def _upsert_embeddings_sync(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        conn = self._connection()
        now = int(time.time())
        written = 0
        with self._lock, conn:
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
                conn.execute(
                    "INSERT OR REPLACE INTO chunk_embeddings"
                    " (chunk_id, source_id, tenant_id, model, dim, vec, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        chunk_id,
                        str(row.get("source_id") or ""),
                        _tenant_scope(str(row.get("tenant_id") or "")),
                        str(row.get("model") or ""),
                        dim,
                        blob,
                        int(row.get("updated_at") or now),
                    ),
                )
                written += 1
        return written

    def _search_vector_sync(
        self,
        tenant_id: str,
        query_vec: Sequence[float],
        limit: int,
        source_ids: Sequence[str] | None,
    ) -> list[tuple[str, float]]:
        conn = self._connection()
        clause, params = _tenant_filter_plain(tenant_id)
        sql = "SELECT chunk_id, vec FROM chunk_embeddings WHERE vec IS NOT NULL"
        sql += clause
        values: list[object] = [*params]
        if self.embedder is not None:
            sql += " AND model = ? AND dim = ?"
            values.extend([self.embedder.model, int(self.embedder.dim)])
        if source_ids:
            sql += f" AND source_id IN ({','.join('?' for _ in source_ids)})"
            values.extend(source_ids)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        values.append(self.max_vector_rows)
        best: list[tuple[float, str]] = []
        cap = max(1, int(limit))
        try:
            cursor = conn.execute(sql, values)
        except sqlite3.Error:
            return []
        for row in cursor:
            score = packed_cosine(query_vec, row["vec"])
            chunk_id = str(row["chunk_id"])
            if len(best) < cap:
                heapq.heappush(best, (score, chunk_id))
            elif score > best[0][0]:
                heapq.heapreplace(best, (score, chunk_id))
        return [
            (chunk_id, float(score))
            for score, chunk_id in sorted(best, key=lambda item: item[0], reverse=True)
        ]

    def _list_chunks_sync(
        self, tenant_id: str = "", source_id: str = ""
    ) -> list[dict]:
        conn = self._connection()
        clause, params = _tenant_filter_plain(tenant_id)
        sql = "SELECT id, source_id, tenant_id, text FROM chunks WHERE 1 = 1" + clause
        values: list[object] = [*params]
        if source_id:
            sql += " AND source_id = ?"
            values.append(source_id)
        sql += " ORDER BY created_at, chunk_index"
        rows = conn.execute(sql, values).fetchall()
        return [
            {
                "chunk_id": str(row["id"]),
                "source_id": str(row["source_id"] or ""),
                "tenant_id": str(row["tenant_id"] or ""),
                "text": str(row["text"] or ""),
            }
            for row in rows
        ]

    def _embedded_index_sync(
        self, tenant_id: str = "", source_id: str = ""
    ) -> dict[str, tuple[str, int]]:
        conn = self._connection()
        clause, params = _tenant_filter_plain(tenant_id)
        sql = "SELECT chunk_id, model, dim FROM chunk_embeddings WHERE 1 = 1" + clause
        values: list[object] = [*params]
        if source_id:
            sql += " AND source_id = ?"
            values.append(source_id)
        rows = conn.execute(sql, values).fetchall()
        return {
            str(row["chunk_id"]): (str(row["model"] or ""), int(row["dim"] or 0))
            for row in rows
        }

    def _embedding_status_sync(self, tenant_id: str = "") -> dict:
        conn = self._connection()
        clause, params = _tenant_filter_plain(tenant_id)
        total_row = conn.execute(
            "SELECT count(*) FROM chunks WHERE 1 = 1" + clause, list(params)
        ).fetchone()
        embedded_row = conn.execute(
            "SELECT count(*) FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id"
            " WHERE 1 = 1" + clause.replace("tenant_id", "c.tenant_id"),
            list(params),
        ).fetchone()
        return {
            "chunks_total": int(total_row[0]) if total_row else 0,
            "chunks_embedded": int(embedded_row[0]) if embedded_row else 0,
        }

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
            conn = self._connection()
            conn.execute("SELECT count(*) FROM chunks").fetchone()
            conn.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? LIMIT 1", ("probe",)
            ).fetchall()
        except Exception:
            return False
        return True

    def _write_chunks(
        self,
        source_id: str,
        chunks: list[Chunk],
        embeddings: list[list[float]] | None,
        tenant_id: str = "",
    ) -> int:
        conn = self._connection()
        now = time.time()
        char_count = sum(len(chunk.text) for chunk in chunks)
        scope = _tenant_scope(tenant_id)
        with self._lock, conn:
            self._delete_locked(conn, source_id, scope)
            for position, chunk in enumerate(chunks):
                chunk_id = chunk.chunk_id
                vector = embeddings[position] if embeddings and position < len(embeddings) else None
                conn.execute(
                    """
                    INSERT OR REPLACE INTO chunks
                    (id, source_id, source_name, chunk_index, text, start_offset,
                     end_offset, meta, embedding, created_at, tenant_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        source_id,
                        chunk.source_name,
                        chunk.chunk_index,
                        chunk.text,
                        chunk.start,
                        chunk.end,
                        json.dumps(chunk.meta, ensure_ascii=False),
                        json.dumps(vector) if vector is not None else None,
                        now,
                        scope,
                    ),
                )
                tokens = index_tokens(chunk.text)
                if tokens:
                    conn.execute(
                        "INSERT INTO chunks_fts(tokens, source_id, chunk_id) VALUES (?, ?, ?)",
                        (tokens, source_id, chunk_id),
                    )
            conn.execute(
                """
                INSERT OR REPLACE INTO sources
                (source_id, source_name, chunk_count, char_count, created_at, tenant_id, object_key)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    chunks[0].source_name,
                    len(chunks),
                    char_count,
                    now,
                    scope,
                    str(chunks[0].meta.get("object_key") or ""),
                ),
            )
        return len(chunks)

    def _delete_sync(self, source_id: str, tenant_id: str = "") -> int:
        conn = self._connection()
        scope = _tenant_scope(tenant_id)
        with self._lock, conn:
            return self._delete_locked(conn, source_id, scope)

    def _list_sources_sync(self, tenant_id: str = "") -> list[dict]:
        conn = self._connection()
        clause, params = _tenant_filter(tenant_id)
        rows = conn.execute(
            "SELECT source_id, source_name, chunk_count, char_count, tenant_id,"
            f" created_at, object_key FROM sources WHERE 1 = 1{clause}"
            " ORDER BY created_at DESC",
            list(params),
        ).fetchall()
        return [
            {
                "source_id": str(row[0]),
                "source_name": str(row[1] or ""),
                "chunk_count": int(row[2] or 0),
                "char_count": int(row[3] or 0),
                "tenant_id": str(row[4] or ""),
                "created_at": float(row[5] or 0.0),
                "object_key": str(row[6] or ""),
            }
            for row in rows
        ]

    def _rename_sync(
        self, source_id: str, source_name: str, tenant_id: str = ""
    ) -> bool:
        name = (source_name or "").strip()
        if not name:
            return False
        conn = self._connection()
        clause, params = _tenant_filter(tenant_id)
        with self._lock, conn:
            row = conn.execute(
                f"SELECT source_id FROM sources WHERE source_id = ?{clause}",
                [source_id, *params],
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE sources SET source_name = ? WHERE source_id = ?",
                (name, source_id),
            )
            conn.execute(
                "UPDATE chunks SET source_name = ? WHERE source_id = ?",
                (name, source_id),
            )
        return True

    def _delete_locked(
        self, conn: sqlite3.Connection, source_id: str, tenant_id: str = ""
    ) -> int:
        clause, params = _tenant_filter(tenant_id)
        row = conn.execute(
            f"SELECT count(*) FROM chunks WHERE source_id = ?{clause}",
            [source_id, *params],
        ).fetchone()
        removed = int(row[0]) if row else 0
        conn.execute("DELETE FROM chunks_fts WHERE source_id = ?", (source_id,))
        conn.execute("DELETE FROM chunk_embeddings WHERE source_id = ?", (source_id,))
        conn.execute(
            f"DELETE FROM chunks WHERE source_id = ?{clause}", [source_id, *params]
        )
        conn.execute(
            f"DELETE FROM sources WHERE source_id = ?{clause}", [source_id, *params]
        )
        return removed

    def _search_sync(
        self,
        query: str,
        top_k: int,
        source_ids: Sequence[str] | None,
        query_vector: Sequence[float] | None,
        tenant_id: str = "",
        min_score: float | None = None,
    ) -> list[Citation]:
        conn = self._connection()
        terms = query_terms(query)
        keyword_limit = (
            max(top_k * 4, 20) if query_vector is None else max(top_k * 3, 1)
        )
        keyword_scores = self._keyword_scores(conn, terms, keyword_limit, source_ids)
        if not keyword_scores:
            keyword_scores = self._like_scores(conn, query, keyword_limit, source_ids)
        if query_vector is None:
            return self._finish_keyword(
                conn, query, terms, keyword_scores, top_k, tenant_id, min_score
            )
        vector_scores = self._search_vector_sync(
            tenant_id, query_vector, max(top_k * 3, 1), source_ids
        )
        if not vector_scores:
            return self._finish_keyword(
                conn, query, terms, keyword_scores, top_k, tenant_id, min_score
            )
        return self._finish_hybrid(
            conn,
            terms,
            keyword_scores,
            dict(vector_scores),
            top_k,
            tenant_id,
            min_score,
        )

    def _finish_keyword(
        self,
        conn: sqlite3.Connection,
        query: str,
        terms: Sequence[str],
        keyword_scores: dict[str, float],
        top_k: int,
        tenant_id: str,
        min_score: float | None,
    ) -> list[Citation]:
        scores = self._scope_scores(conn, keyword_scores, tenant_id)
        texts = self._texts(conn, list(scores))
        ranked, covs = rank_with_coverage(scores, texts, terms)
        selected = select_top(
            ranked, covs, top_k, self.min_relative_score, self.min_relative_coverage
        )
        citations = self._build_citations(conn, selected, terms)
        if min_score is not None:
            threshold = float(min_score)
            citations = [item for item in citations if item.score >= threshold]
        return citations

    def _finish_hybrid(
        self,
        conn: sqlite3.Connection,
        terms: Sequence[str],
        keyword_scores: dict[str, float],
        vector_scores: dict[str, float],
        top_k: int,
        tenant_id: str,
        min_score: float | None,
    ) -> list[Citation]:
        keyword_scores = self._scope_scores(conn, keyword_scores, tenant_id)
        best_keyword = max(keyword_scores.values()) if keyword_scores else 0.0
        weight = self.vector_weight
        merged: dict[str, float] = {}
        for chunk_id in set(keyword_scores) | set(vector_scores):
            keyword = keyword_scores.get(chunk_id, 0.0)
            keyword_norm = keyword / best_keyword if best_keyword > 0 else 0.0
            vector_norm = (max(-1.0, min(1.0, vector_scores.get(chunk_id, 0.0))) + 1.0) / 2.0
            merged[chunk_id] = (1.0 - weight) * keyword_norm + weight * vector_norm
        ranked = sorted(merged.items(), key=lambda item: item[1], reverse=True)[:top_k]
        citations = self._build_citations(
            conn, ranked, terms, keyword_scores, vector_scores
        )
        if min_score is not None:
            threshold = float(min_score)
            citations = [item for item in citations if item.score >= threshold]
        return citations

    def _scope_scores(
        self,
        conn: sqlite3.Connection,
        scores: dict[str, float],
        tenant_id: str,
    ) -> dict[str, float]:
        if not scores:
            return {}
        clause, params = _tenant_filter(tenant_id)
        ids = list(scores)
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"SELECT id FROM chunks WHERE id IN ({placeholders}){clause}",
            [*ids, *params],
        ).fetchall()
        allowed = {row["id"] for row in rows}
        return {key: value for key, value in scores.items() if key in allowed}

    def _keyword_scores(
        self,
        conn: sqlite3.Connection,
        terms: Sequence[str],
        limit: int,
        source_ids: Sequence[str] | None,
    ) -> dict[str, float]:
        if not terms:
            return {}
        match = " OR ".join(f'"{term}"' for term in terms)
        sql = "SELECT chunk_id, bm25(chunks_fts) AS rank FROM chunks_fts WHERE chunks_fts MATCH ?"
        params: list[object] = [match]
        if source_ids:
            sql += f" AND source_id IN ({','.join('?' for _ in source_ids)})"
            params.extend(source_ids)
        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.Error:
            return {}
        texts = self._texts(conn, [row["chunk_id"] for row in rows])
        names = self._source_names(conn, [row["chunk_id"] for row in rows])
        scores: dict[str, float] = {}
        for row in rows:
            chunk_id = row["chunk_id"]
            body = texts.get(chunk_id, "")
            raw = max(-float(row["rank"]), 0.0)
            scores[chunk_id] = term_score(
                terms, body, names.get(chunk_id, ""), raw
            )
        return scores

    def _source_names(
        self, conn: sqlite3.Connection, chunk_ids: Sequence[str]
    ) -> dict[str, str]:
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        sql = (
            "SELECT c.id AS chunk_id, s.source_name AS source_name FROM chunks c"
            " LEFT JOIN sources s ON s.id = c.source_id"
            f" WHERE c.id IN ({placeholders})"
        )
        try:
            rows = conn.execute(sql, list(chunk_ids)).fetchall()
        except sqlite3.Error:
            return {}
        return {
            str(row["chunk_id"]): str(row["source_name"] or "")
            for row in rows
        }

    def _like_scores(
        self,
        conn: sqlite3.Connection,
        query: str,
        limit: int,
        source_ids: Sequence[str] | None,
    ) -> dict[str, float]:
        pattern = f"%{query}%"
        sql = "SELECT id, text FROM chunks WHERE text LIKE ?"
        params: list[object] = [pattern]
        if source_ids:
            sql += f" AND source_id IN ({','.join('?' for _ in source_ids)})"
            params.extend(source_ids)
        sql += " ORDER BY length(text) LIMIT ?"
        params.append(limit)
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.Error:
            return {}
        return {row["id"]: LIKE_MATCH_SCORE for row in rows}

    def _texts(
        self, conn: sqlite3.Connection, chunk_ids: Sequence[str]
    ) -> dict[str, str]:
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        rows = conn.execute(
            f"SELECT id, text FROM chunks WHERE id IN ({placeholders})",
            list(chunk_ids),
        ).fetchall()
        return {row["id"]: row["text"] for row in rows}

    def _build_citations(
        self,
        conn: sqlite3.Connection,
        ranked: Sequence[tuple[str, float]],
        terms: Sequence[str],
        keyword_scores: dict[str, float] | None = None,
        vector_scores: dict[str, float] | None = None,
    ) -> list[Citation]:
        if not ranked:
            return []
        ids = [chunk_id for chunk_id, _ in ranked]
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"SELECT * FROM chunks WHERE id IN ({placeholders})", ids
        ).fetchall()
        by_id = {row["id"]: row for row in rows}
        citations: list[Citation] = []
        for chunk_id, score in ranked:
            row = by_id.get(chunk_id)
            if row is None:
                continue
            citations.append(
                Citation(
                    source_id=row["source_id"],
                    source_name=row["source_name"],
                    chunk_id=chunk_id,
                    chunk_index=int(row["chunk_index"]),
                    text=row["text"],
                    snippet=make_snippet(row["text"], terms),
                    score=round(float(score), 6),
                    start=int(row["start_offset"]),
                    end=int(row["end_offset"]),
                    meta=_load_meta(row["meta"]),
                    keyword_score=(
                        round(float(keyword_scores.get(chunk_id, 0.0)), 6)
                        if keyword_scores is not None
                        else None
                    ),
                    vector_score=(
                        round(float(vector_scores.get(chunk_id, 0.0)), 6)
                        if vector_scores is not None
                        else None
                    ),
                )
            )
        return citations


def _tenant_scope(tenant_id: str) -> str:
    value = (tenant_id or "").strip()
    return value or DEFAULT_TENANT_ID


def _tenant_filter(tenant_id: str) -> tuple[str, list[object]]:
    scope = _tenant_scope(tenant_id)
    if scope == DEFAULT_TENANT_ID:
        return " AND (tenant_id = ? OR tenant_id = '')", [DEFAULT_TENANT_ID]
    return " AND tenant_id = ?", [scope]


def _tenant_filter_plain(tenant_id: str) -> tuple[str, list[object]]:
    return _tenant_filter(tenant_id)


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error:
        return False
    return any(row["name"] == column for row in rows)


def _load_meta(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}
