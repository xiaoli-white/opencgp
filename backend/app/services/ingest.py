from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Sequence

from app.models.chunk import Chunk
from app.models.citation import Citation
from app.models.ingest import IngestResult
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
    ) -> None:
        self.vectorstore = vectorstore
        self.parser = parser
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_file_mb = max_file_mb

    async def ingest_bytes(
        self,
        data: bytes,
        filename: str,
        source_name: str | None = None,
        source_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> IngestResult:
        if not data:
            raise ValueError("上传文件为空")
        limit = self.max_file_mb * 1024 * 1024
        if len(data) > limit:
            raise ValueError(f"文件超过 {self.max_file_mb}MB 上限")
        if not self.parser.supports(filename):
            raise ValueError(f"不支持的文档类型: {Path(filename).suffix or filename!r}")
        parsed = self.parser.parse(data, filename)
        digest = hashlib.sha256(data).hexdigest()
        merged_meta = {"filename": filename, "sha256": digest, **parsed.meta, **(meta or {})}
        return await self.ingest_text(
            parsed.text,
            source_name=source_name or parsed.source_name,
            source_id=source_id or _source_id(digest),
            meta={**merged_meta, "parser": parsed.parser},
        )

    async def ingest_text(
        self,
        text: str,
        source_name: str,
        source_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> IngestResult:
        normalized = normalize_text(text)
        if not normalized:
            raise ValueError("文档解析后无有效文本")
        resolved_id = source_id or _source_id(hashlib.sha256(normalized.encode()).hexdigest())
        chunks = self._build_chunks(normalized, resolved_id, source_name, meta or {})
        if not chunks:
            raise ValueError("文档分块结果为空")
        await self.vectorstore.add_chunks(resolved_id, chunks)
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

    async def search(
        self,
        query: str,
        top_k: int = 5,
        source_ids: Sequence[str] | None = None,
    ) -> list[Citation]:
        return await self.vectorstore.search(query, top_k=top_k, source_ids=source_ids)

    async def delete_source(self, source_id: str) -> int:
        return await self.vectorstore.delete_by_source(source_id)

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
            if key in {"filename", "parser", "pages", "sha256"}
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
