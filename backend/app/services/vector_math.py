from __future__ import annotations

import array
import math
import struct
import threading
from collections import OrderedDict
from typing import Sequence


class VectorCache:
    def __init__(self, capacity: int = 20000) -> None:
        self.capacity = max(1, int(capacity))
        self._items: OrderedDict[str, Sequence[float]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Sequence[float] | None:
        with self._lock:
            value = self._items.get(key)
            if value is None:
                return None
            self._items.move_to_end(key)
            return value

    def put(self, key: str, value: Sequence[float]) -> None:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


_VECTOR_CACHE = VectorCache(20000)


def vector_cache() -> VectorCache:
    return _VECTOR_CACHE


def clear_vector_cache() -> None:
    _VECTOR_CACHE.clear()


def cache_key(chunk_id: str, model: str, dim: int) -> str:
    return f"{chunk_id}:{model}:{int(dim)}"


def clear_vector_cache_entry(chunk_id: str, model: str, dim: int) -> None:
    _VECTOR_CACHE.delete(cache_key(chunk_id, model, dim))


def pack_vector(vec: Sequence[float]) -> bytes:
    values = [float(item) for item in vec]
    return struct.pack(f"<{len(values)}f", *values)


def unpack_vector(blob: object) -> tuple[float, ...]:
    if blob is None:
        return ()
    if isinstance(blob, memoryview):
        blob = blob.tobytes()
    if isinstance(blob, bytearray):
        blob = bytes(blob)
    if isinstance(blob, bytes):
        count = len(blob) // 4
        if count <= 0:
            return ()
        return struct.unpack(f"<{count}f", blob[: count * 4])
    try:
        return tuple(float(item) for item in blob)  # type: ignore[arg-type]
    except TypeError:
        return ()


def cosine(query: Sequence[float], vec: Sequence[float]) -> float:
    if not query or not vec or len(query) != len(vec):
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(query, vec):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


def packed_cosine(query: Sequence[float], blob: object) -> float:
    return cosine(query, unpack_vector(blob))


def cached_vector(key: str, blob: object) -> Sequence[float]:
    value = _VECTOR_CACHE.get(key)
    if value is None:
        unpacked = unpack_vector(blob)
        if unpacked:
            value = array.array("f", unpacked)
            _VECTOR_CACHE.put(key, value)
        else:
            value = ()
    return value


def cached_cosine(key: str, query: Sequence[float], blob: object) -> float:
    return cosine(query, cached_vector(key, blob))


__all__ = [
    "VectorCache",
    "cache_key",
    "cached_cosine",
    "clear_vector_cache_entry",
    "cached_vector",
    "clear_vector_cache",
    "cosine",
    "pack_vector",
    "packed_cosine",
    "unpack_vector",
    "vector_cache",
]
