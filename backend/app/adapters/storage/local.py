"""本地文件对象存储实现（builtin，M0 默认）。

实现 :class:`app.ports.storage.StorageBackend` 端口，落盘到本地目录。
生产可切 ``s3`` / ``rustfs`` 等（同一端口、只改配置）。

安全约定：``key`` 仅允许受控相对路径，拒绝路径穿越。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.ports.storage import StorageBackend


class LocalStorageBackend(StorageBackend):
    """基于本地文件系统的对象存储实现。"""

    def __init__(self, root: str = "data/storage") -> None:
        self.root = Path(root)

    def _resolve(self, key: str) -> Path:
        key = key.replace("\\", "/").lstrip("/")
        candidate = (self.root / key).resolve()
        root_resolved = self.root.resolve()
        if candidate != root_resolved and root_resolved not in candidate.parents:
            raise ValueError(f"非法的对象键（路径穿越）: {key!r}")
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
