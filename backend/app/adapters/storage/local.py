"""Local-file object storage implementation (builtin, M0 default).

Implements the :class:`app.ports.storage.StorageBackend` port and writes to a local
directory. Production can switch to ``s3`` / ``rustfs``, etc. (same port, config only).

Security convention: ``key`` may only be a controlled relative path; path traversal is rejected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.ports.storage import StorageBackend


class LocalStorageBackend(StorageBackend):
    """Object storage implementation backed by the local filesystem."""

    def __init__(self, root: str = "data/storage") -> None:
        self.root = Path(root)

    def _resolve(self, key: str) -> Path:
        key = key.replace("\\", "/").lstrip("/")
        candidate = (self.root / key).resolve()
        root_resolved = self.root.resolve()
        if candidate != root_resolved and root_resolved not in candidate.parents:
            raise ValueError(f"invalid object key (path traversal): {key!r}")
        return candidate

    def put(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.is_file():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def healthcheck(self) -> bool:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe = self.root / ".healthcheck"
            probe.write_bytes(b"ok")
            probe.unlink()
            return True
        except Exception:  # noqa: BLE001
            return False
