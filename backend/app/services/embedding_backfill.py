from __future__ import annotations

from typing import Any, Callable, Sequence


async def _embed_texts(
    embedder: Any, texts: Sequence[str]
) -> list[list[float] | None]:
    results: list[list[float] | None] = [None] * len(texts)
    try:
        vectors = await embedder.embed(list(texts))
        if len(vectors) == len(texts):
            return [list(vector) if vector else None for vector in vectors]
    except Exception:
        pass
    for index, text in enumerate(texts):
        try:
            vector = await embedder.embed([text])
            if vector:
                results[index] = list(vector[0])
        except Exception:
            results[index] = None
    return results


async def backfill_embeddings(
    store: Any,
    embedder: Any,
    tenant_id: str,
    source_id: str = "",
    batch_size: int = 32,
    progress: Callable[[float], None] | None = None,
) -> dict[str, int]:
    if embedder is None or store is None:
        return {"embedded": 0, "failed": 0, "skipped": 0}
    chunks = await store.list_chunks(tenant_id, source_id)
    existing = await store.embedded_index(tenant_id, source_id)
    todo: list[dict] = []
    skipped = 0
    model = str(getattr(embedder, "model", "") or "")
    dim = int(getattr(embedder, "dim", 0) or 0)
    for chunk in chunks:
        current = existing.get(str(chunk.get("chunk_id") or ""))
        if current and current[0] == model and int(current[1]) == dim:
            skipped += 1
            continue
        todo.append(chunk)
    embedded = 0
    failed = 0
    width = max(1, int(batch_size or 32))
    total = len(todo)
    for start in range(0, total, width):
        batch = todo[start : start + width]
        vectors = await _embed_texts(
            embedder, [str(item.get("text") or "") for item in batch]
        )
        rows: list[dict] = []
        for item, vector in zip(batch, vectors):
            chunk_id = str(item.get("chunk_id") or "")
            if vector is None or not chunk_id:
                failed += 1
                continue
            rows.append(
                {
                    "chunk_id": chunk_id,
                    "source_id": str(item.get("source_id") or ""),
                    "tenant_id": tenant_id,
                    "model": model,
                    "dim": dim,
                    "vec": vector,
                }
            )
        if rows:
            try:
                embedded += int(await store.upsert_embeddings(rows))
            except Exception:
                for row in rows:
                    try:
                        embedded += int(await store.upsert_embeddings([row]))
                    except Exception:
                        failed += 1
        if progress is not None:
            done = min(total, start + len(batch))
            progress(done / total if total else 1.0)
    return {"embedded": embedded, "failed": failed, "skipped": skipped}


__all__ = ["backfill_embeddings"]
