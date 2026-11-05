from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Sequence

from app.models.chunk import Chunk
from app.models.citation import Citation
from app.models.ingest import IngestResult
from app.ports.embedding import EmbeddingPort
from app.ports.parser import DocumentParser
from app.ports.vectorstore import VectorStore
from app.services.chunking import chunk_texts
from app.services.textproc import normalize_text


class IngestService:
    def __init__(
        self,
        vectorstore: VectorStore,
        parser: DocumentParser,
        chunk_size: int = 800,
        chunk_overlap: int = 120,
        max_file_mb: int = 20,
        storage: Any = None,
        storage_prefix: str = "",
        embedder: EmbeddingPort | None = None,
    ) -> None:
        self.vectorstore = vectorstore
        self.parser = parser
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_file_mb = max_file_mb
        self.storage = storage
        self.storage_prefix = (storage_prefix or "").strip("/")
        self.embedder = embedder
        self.last_object_key = ""
        self.last_object_error = ""

    async def ingest_bytes(
        self,
        data: bytes,
        filename: str,
        source_name: str | None = None,
        source_id: str | None = None,
        meta: dict[str, Any] | None = None,
        tenant_id: str = "",
    ) -> IngestResult:
        if not data:
            raise ValueError("上传文件为空")
        limit = self.max_file_mb * 1024 * 1024
        if len(data) > limit:
            raise ValueError(f"文件超过 {self.max_file_mb}MB 上限")
        if not self.parser.supports(filename):
            raise ValueError(f"不支持的文档类型: {Path(filename).suffix or filename!r}")
        try:
            parsed = self.parser.parse(data, filename)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"文件解析失败: {exc}") from exc
        digest = hashlib.sha256(data).hexdigest()
        merged_meta = {"filename": filename, "sha256": digest, **parsed.meta, **(meta or {})}
        resolved_id = source_id or _source_id(digest)
        object_key = self._store_raw(data, filename, resolved_id, tenant_id)
        if object_key:
            merged_meta["object_key"] = object_key
        return await self.ingest_text(
            parsed.text,
            source_name=source_name or parsed.source_name,
            source_id=resolved_id,
            meta={**merged_meta, "parser": parsed.parser},
            tenant_id=tenant_id,
        )

    async def ingest_text(
        self,
        text: str,
        source_name: str,
        source_id: str | None = None,
        meta: dict[str, Any] | None = None,
        tenant_id: str = "",
    ) -> IngestResult:
        normalized = normalize_text(text)
        if not normalized:
            raise ValueError("文档解析后无有效文本")
        resolved_id = source_id or _source_id(hashlib.sha256(normalized.encode()).hexdigest())
        chunks = self._build_chunks(normalized, resolved_id, source_name, meta or {})
        if not chunks:
            raise ValueError("文档分块结果为空")
        await self.vectorstore.add_chunks(resolved_id, chunks, tenant_id=tenant_id)
        await self._embed_chunks(resolved_id, chunks, tenant_id)
        parser_name = str((meta or {}).get("parser", "unknown"))
        return IngestResult(
            source_id=resolved_id,
            source_name=source_name,
            parser=parser_name,
            chunk_count=len(chunks),
            char_count=len(normalized),
            meta={
                **(meta or {}),
                "chunk_size": self.chunk_size,
                "chunk_overlap": self.chunk_overlap,
                "ingested_at": time.time(),
            },
        )

    async def _embed_chunks(
        self, source_id: str, chunks: Sequence[Chunk], tenant_id: str
    ) -> None:
        if self.embedder is None or not chunks:
            return
        try:
            vectors = await self.embedder.embed([chunk.text for chunk in chunks])
        except Exception as exc:
            print(f"[ingest] 向量化失败，跳过 embedding: {exc!r}")
            return
        if len(vectors) != len(chunks):
            print(
                f"[ingest] 向量数量不匹配，跳过 embedding: {len(vectors)} != {len(chunks)}"
            )
            return
        rows = [
            {
                "chunk_id": chunk.chunk_id,
                "source_id": source_id,
                "tenant_id": tenant_id,
                "model": self.embedder.model,
                "dim": self.embedder.dim,
                "vec": vector,
            }
            for chunk, vector in zip(chunks, vectors)
        ]
        try:
            await self.vectorstore.upsert_embeddings(rows)
        except Exception as exc:
            print(f"[ingest] embedding 写入失败，已跳过: {exc!r}")

    def _store_raw(
        self, data: bytes, filename: str, source_id: str, tenant_id: str
    ) -> str:
        self.last_object_key = ""
        self.last_object_error = ""
        if self.storage is None:
            return ""
        key = self.object_key(tenant_id, source_id, filename)
        try:
            self.storage.put(key, data, content_type="application/octet-stream")
        except Exception as exc:
            self.last_object_error = repr(exc)
            print(f"[ingest] 原始文件写入对象存储失败: {exc!r}")
            return ""
        self.last_object_key = key
        return key

    def object_key(self, tenant_id: str, source_id: str, filename: str) -> str:
        tenant = (tenant_id or "tenant_default").strip() or "tenant_default"
        name = (filename or "upload.bin").strip().replace("/", "_") or "upload.bin"
        parts = [part for part in (self.storage_prefix, tenant, source_id, name) if part]
        return "/".join(parts)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        source_ids: Sequence[str] | None = None,
        tenant_id: str = "",
    ) -> list[Citation]:
        return await self.vectorstore.search(
            query, top_k=top_k, source_ids=source_ids, tenant_id=tenant_id
        )

    async def delete_source(self, source_id: str, tenant_id: str = "") -> int:
        return await self.vectorstore.delete_by_source(source_id, tenant_id=tenant_id)

    async def list_sources(self, tenant_id: str = "") -> list[dict]:
        return await self.vectorstore.list_sources(tenant_id)

    async def rename_source(
        self, source_id: str, source_name: str, tenant_id: str = ""
    ) -> bool:
        return await self.vectorstore.rename_source(source_id, source_name, tenant_id)

    def _build_chunks(
        self,
        text: str,
        source_id: str,
        source_name: str,
        meta: dict[str, Any],
    ) -> list[Chunk]:
        chunk_meta = {
            key: value
            for key, value in meta.items()
            if key in {"filename", "parser", "pages", "sha256", "object_key"}
        }
        chunks: list[Chunk] = []
        for index, (start, end, body) in enumerate(
            chunk_texts(text, self.chunk_size, self.chunk_overlap)
        ):
            chunks.append(
                Chunk(
                    source_id=source_id,
                    source_name=source_name,
                    chunk_index=index,
                    text=body,
                    start=start,
                    end=end,
                    meta={**chunk_meta, "char_count": len(body)},
                )
            )
        return chunks


def _source_id(digest: str) -> str:
    return f"src_{digest[:16]}"
