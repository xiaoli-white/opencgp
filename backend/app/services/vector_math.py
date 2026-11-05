from __future__ import annotations

import math
import struct
from typing import Sequence


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


def packed_cosine(query: Sequence[float], blob: object) -> float:
    vec = unpack_vector(blob)
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
