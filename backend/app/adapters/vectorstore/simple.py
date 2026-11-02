from __future__ import annotations

import asyncio
import json
import math
import sqlite3
import threading
import time
from pathlib import Path
from typing import Sequence

from app.models.chunk import Chunk
from app.models.citation import Citation
from app.ports.embedding import EmbeddingProvider
from app.ports.vectorstore import VectorStore
from app.services.textproc import coverage, index_tokens, make_snippet, query_terms

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS sources (
        source_id TEXT PRIMARY KEY,
        source_name TEXT NOT NULL,
        chunk_count INTEGER NOT NULL DEFAULT 0,
        char_count INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL
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
        created_at REAL NOT NULL
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
    ) -> None:
        self.root = Path(path)
        self.db_path = self.root / db_name
        self.embedder = embedder
        self.keyword_weight = keyword_weight
        self.min_relative_score = min_relative_score
        self.min_relative_coverage = min_relative_coverage
        self.max_scan_rows = max_scan_rows
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
                conn.commit()
                self._conn = conn
            return self._conn

    async def add_chunks(self, source_id: str, chunks: Sequence[Chunk]) -> int:
        items = list(chunks)
        if not items:
            return 0
        embeddings = await self.embedder.embed([chunk.text for chunk in items]) if self.embedder else None
        return await asyncio.to_thread(self._write_chunks, source_id, items, embeddings)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        source_ids: Sequence[str] | None = None,
    ) -> list[Citation]:
        if not query or not query.strip() or top_k <= 0:
            return []
        scope = [sid for sid in (source_ids or []) if sid]
        query_vector = None
        if self.embedder is not None:
            vectors = await self.embedder.embed([query])
            query_vector = vectors[0] if vectors else None
        return await asyncio.to_thread(
            self._search_sync, query.strip(), top_k, scope or None, query_vector
        )

    async def delete_by_source(self, source_id: str) -> int:
        return await asyncio.to_thread(self._delete_sync, source_id)

    def healthcheck(self) -> bool:
        try:
            conn = self._connection()
            conn.execute("SELECT count(*) FROM chunks").fetchone()
            conn.execute(
                "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? LIMIT 1", ("probe",)
            ).fetchall()
        except Exception:
            return False
        if self.embedder is not None:
            return bool(self.embedder.healthcheck())
        return True

    def _write_chunks(
        self,
        source_id: str,
        chunks: list[Chunk],
        embeddings: list[list[float]] | None,
    ) -> int:
        conn = self._connection()
        now = time.time()
        char_count = sum(len(chunk.text) for chunk in chunks)
        with self._lock, conn:
            self._delete_locked(conn, source_id)
            for position, chunk in enumerate(chunks):
                chunk_id = chunk.chunk_id
                vector = embeddings[position] if embeddings and position < len(embeddings) else None
                conn.execute(
                    """
                    INSERT OR REPLACE INTO chunks
                    (id, source_id, source_name, chunk_index, text, start_offset,
                     end_offset, meta, embedding, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                (source_id, source_name, chunk_count, char_count, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source_id, chunks[0].source_name, len(chunks), char_count, now),
            )
        return len(chunks)

    def _delete_sync(self, source_id: str) -> int:
        conn = self._connection()
        with self._lock, conn:
            return self._delete_locked(conn, source_id)

    def _delete_locked(self, conn: sqlite3.Connection, source_id: str) -> int:
        row = conn.execute(
            "SELECT count(*) FROM chunks WHERE source_id = ?", (source_id,)
        ).fetchone()
        removed = int(row[0]) if row else 0
        conn.execute("DELETE FROM chunks_fts WHERE source_id = ?", (source_id,))
        conn.execute("DELETE FROM chunks WHERE source_id = ?", (source_id,))
        conn.execute("DELETE FROM sources WHERE source_id = ?", (source_id,))
        return removed

    def _search_sync(
        self,
        query: str,
        top_k: int,
        source_ids: Sequence[str] | None,
        query_vector: Sequence[float] | None,
    ) -> list[Citation]:
        conn = self._connection()
        terms = query_terms(query)
        limit = max(top_k * 4, 20)
        keyword_scores = self._keyword_scores(conn, terms, limit, source_ids)
        if not keyword_scores:
            keyword_scores = self._like_scores(conn, query, limit, source_ids)
        keyword_norm = _normalize(keyword_scores)
        if query_vector is None:
            scores = keyword_norm
        else:
            vector_scores = self._vector_scores(conn, query_vector, limit, source_ids)
            scores = self._blend(keyword_norm, _normalize(vector_scores))
        ranked, covs = self._rank(conn, scores, terms)
        return self._build_citations(
            conn, self._select(ranked, covs, top_k), terms
        )

    def _rank(
        self,
        conn: sqlite3.Connection,
        scores: dict[str, float],
        terms: Sequence[str],
    ) -> tuple[list[tuple[str, float]], dict[str, float]]:
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        texts = self._texts(conn, [chunk_id for chunk_id, _ in ranked])
        covs = {
            chunk_id: coverage(terms, texts.get(chunk_id, ""))
            for chunk_id, _ in ranked
        }
        return ranked, covs

    def _select(
        self,
        ranked: Sequence[tuple[str, float]],
        covs: dict[str, float],
        top_k: int,
    ) -> list[tuple[str, float]]:
        if not ranked:
            return []
        best_score = ranked[0][1]
        best_cov = max(covs.values()) if covs else 0.0
        kept: list[tuple[str, float]] = [ranked[0]]
        for chunk_id, score in ranked[1:]:
            if len(kept) >= top_k:
                break
            if best_score > 0 and score < best_score * self.min_relative_score:
                continue
            if best_cov > 0 and covs.get(chunk_id, 0.0) < best_cov * self.min_relative_coverage:
                continue
            kept.append((chunk_id, score))
        return kept

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
        scores: dict[str, float] = {}
        for row in rows:
            chunk_id = row["chunk_id"]
            body = texts.get(chunk_id, "")
            raw = max(-float(row["rank"]), 0.0)
            scores[chunk_id] = raw * (0.5 + 0.5 * coverage(terms, body))
        return scores

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
        return {row["id"]: 1.0 / (1.0 + math.log1p(len(row["text"]))) for row in rows}

    def _vector_scores(
        self,
        conn: sqlite3.Connection,
        query_vector: Sequence[float],
        limit: int,
        source_ids: Sequence[str] | None,
    ) -> dict[str, float]:
        sql = "SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL"
        params: list[object] = []
        if source_ids:
            sql += f" AND source_id IN ({','.join('?' for _ in source_ids)})"
            params.extend(source_ids)
        sql += " LIMIT ?"
        params.append(self.max_scan_rows)
        try:
            rows = conn.execute(sql, params).fetchall()
        except sqlite3.Error:
            return {}
        scored: dict[str, float] = {}
        for row in rows:
            try:
                vector = json.loads(row["embedding"])
            except (TypeError, ValueError):
                continue
            scored[row["id"]] = _cosine(query_vector, vector)
        top = sorted(scored.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        return dict(top)

    def _blend(
        self, keyword_scores: dict[str, float], vector_scores: dict[str, float]
    ) -> dict[str, float]:
        keyword_norm = _normalize(keyword_scores)
        vector_norm = _normalize(vector_scores)
        weight = self.keyword_weight
        merged: dict[str, float] = {}
        for chunk_id in set(keyword_norm) | set(vector_norm):
            merged[chunk_id] = weight * keyword_norm.get(chunk_id, 0.0) + (
                1.0 - weight
            ) * vector_norm.get(chunk_id, 0.0)
        return merged

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
                )
            )
        return citations


def _load_meta(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    top = max(scores.values())
    if top <= 0:
        return {key: 0.0 for key in scores}
    return {key: value / top for key, value in scores.items()}


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
