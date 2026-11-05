from __future__ import annotations

import asyncio
from typing import Any, Sequence

import httpx


class OpenAIEmbedding:
    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "text-embedding-3-small",
        dim: int = 1024,
        batch: int = 32,
        timeout: float = 20.0,
        query_prefix: str = "",
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self.model = model or "text-embedding-3-small"
        self.dim = max(1, int(dim or 1024))
        self.batch = max(1, int(batch or 32))
        self.timeout = float(timeout or 20)
        self.query_prefix = query_prefix or ""

    def _endpoint(self) -> str:
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/embeddings"
        return f"{self.base_url}/v1/embeddings"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        items = [str(text or "") for text in texts]
        if not items:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(items), self.batch):
            chunk = items[start : start + self.batch]
            payload = {"model": self.model, "input": chunk}
            data = await self._post(payload)
            rows = data.get("data")
            if not isinstance(rows, list) or len(rows) != len(chunk):
                raise ValueError(f"embedding 响应条目数不匹配: {len(rows) if isinstance(rows, list) else 'invalid'}")
            ordered: list[tuple[int, list[float]]] = []
            for position, row in enumerate(rows):
                if not isinstance(row, dict):
                    raise ValueError("embedding 响应结构异常")
                index = int(row.get("index", position))
                vector = row.get("embedding")
                if not isinstance(vector, list) or not vector:
                    raise ValueError("embedding 向量为空")
                ordered.append((index, [float(value) for value in vector]))
            ordered.sort(key=lambda item: item[0])
            vectors.extend(vector for _, vector in ordered)
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed([f"{self.query_prefix}{text or ''}"])
        return vectors[0] if vectors else []

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self._endpoint(), headers=self._headers(), json=payload
                    )
                    response.raise_for_status()
                    data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("embedding 响应不是对象")
                return data
            except Exception as exc:
                last_error = exc
                if attempt >= 2:
                    break
                await asyncio.sleep(0.5 * (2**attempt))
        if last_error is None:
            raise RuntimeError("embedding 请求失败")
        raise last_error

    def healthcheck(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)
