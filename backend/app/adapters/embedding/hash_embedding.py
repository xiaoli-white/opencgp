from __future__ import annotations

import hashlib
import math
import re
from typing import Sequence

_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]+")
_ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")


class HashEmbedding:
    def __init__(
        self,
        dim: int = 256,
        query_prefix: str = "",
        model: str = "hash",
    ) -> None:
        self.dim = max(8, int(dim or 256))
        self.query_prefix = query_prefix or ""
        self.model = model or "hash"

    def _tokens(self, text: str) -> list[str]:
        tokens: list[str] = []
        lowered = text or ""
        for run in _CJK_RUN.findall(lowered):
            if len(run) == 1:
                tokens.append(run)
            else:
                tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
        for word in _ASCII_WORD.findall(lowered):
            if len(word) > 1:
                tokens.append(word.lower())
        return tokens

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in self._tokens(text):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], "big") % self.dim
            sign = 1.0 if digest[8] & 1 == 0 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(value * value for value in vec))
        if norm <= 0:
            return vec
        return [value / norm for value in vec]

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(str(text or "")) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(f"{self.query_prefix}{text or ''}")

    def healthcheck(self) -> bool:
        return True
