"""Object storage abstract port (StorageBackend).

Unified file/object storage interface used to store course assets (images, code,
covers, export artifacts, etc.). M0 ships a built-in local-file implementation
(``local``); production can switch to S3-compatible storage / rustfs / OSS, etc.
through the same port by changing configuration only.

Conventions:
- ``key`` is a controlled relative-path-style object key, e.g. ``series/1/assets/cover.png``.
- Implementations must reject path traversal such as ``..``; keys must not be absolute paths.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Generic object storage port."""

    def put(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        """Write an object and return the final object key."""
        ...

    def get(self, key: str) -> bytes:
        """Read an object; raise :class:`FileNotFoundError` when it does not exist."""
        ...

    def delete(self, key: str) -> None:
        """Delete an object (succeeds silently when it does not exist)."""
        ...

    def exists(self, key: str) -> bool:
        """Return whether the object exists."""
        ...

    def healthcheck(self) -> bool:
        """Health check: whether a minimal read/write against the backend succeeds."""
        ...
