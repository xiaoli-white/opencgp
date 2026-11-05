from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Sequence

DEFAULT_LSH_BITS = 12
_CACHE_LIMIT = 16
_MASK64 = (1 << 64) - 1
_GOLDEN = 0x9E3779B97F4A7C15


class _SplitMix64:
    def __init__(self, seed: int) -> None:
        self.state = seed & _MASK64

    def next(self) -> int:
        self.state = (self.state + _GOLDEN) & _MASK64
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & _MASK64
        return (value ^ (value >> 31)) & _MASK64


def model_seed(model: str) -> int:
    digest = hashlib.md5((model or "").encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") & 0xFFFFFFFF


def _build_planes(seed: int, dim: int, bits: int) -> tuple[tuple[float, ...], ...]:
    rng = _SplitMix64(seed ^ ((dim & 0xFFFFFFFF) << 32) ^ (bits & 0xFFFFFFFF))
    planes: list[tuple[float, ...]] = []
    for _ in range(bits):
        planes.append(tuple(1.0 if rng.next() & 1 else -1.0 for _ in range(dim)))
    return tuple(planes)


_PLANES: OrderedDict[tuple[int, int, int], tuple[tuple[float, ...], ...]] = OrderedDict()
_PLANES_LOCK = threading.Lock()


def hyperplanes(model: str, dim: int, bits: int = DEFAULT_LSH_BITS) -> tuple[tuple[float, ...], ...]:
    dimension = max(1, int(dim))
    width = max(1, min(32, int(bits)))
    key = (model_seed(model), dimension, width)
    with _PLANES_LOCK:
        planes = _PLANES.get(key)
        if planes is not None:
            _PLANES.move_to_end(key)
            return planes
        planes = _build_planes(key[0], dimension, width)
        _PLANES[key] = planes
        while len(_PLANES) > _CACHE_LIMIT:
            _PLANES.popitem(last=False)
        return planes


def project_bucket(
    model: str, vector: Sequence[float], bits: int = DEFAULT_LSH_BITS
) -> int:
    if not vector:
        return 0
    width = max(1, min(32, int(bits)))
    planes = hyperplanes(model, len(vector), width)
    bucket = 0
    for index, plane in enumerate(planes):
        total = 0.0
        for value, sign in zip(vector, plane):
            total += value * sign
        if total > 0.0:
            bucket |= 1 << index
    return bucket


def neighbor_buckets(bucket: int, bits: int = DEFAULT_LSH_BITS) -> tuple[int, ...]:
    width = max(1, min(32, int(bits)))
    mask = (1 << width) - 1
    base = int(bucket) & mask
    values = [base]
    for index in range(width):
        values.append(base ^ (1 << index))
    return tuple(values)


__all__ = [
    "DEFAULT_LSH_BITS",
    "hyperplanes",
    "model_seed",
    "neighbor_buckets",
    "project_bucket",
]
