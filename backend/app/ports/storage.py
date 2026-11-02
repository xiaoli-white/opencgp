"""对象存储抽象端口（StorageBackend）。

统一文件/对象存储接口，用于存放课程资产（配图、代码、封面、导出产物等）。
M0 内置本地文件实现（``local``），生产可切换 S3 兼容 / rustfs / OSS 等，
同一端口、只改配置。

约定：
- ``key`` 为受控的相对路径风格对象键，例如 ``course/1/assets/cover.png``。
- 实现必须拒绝 ``..`` 等路径穿越，key 不允许是绝对路径。
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """通用对象存储端口。"""

    def put(self, key: str, data: bytes, content_type: Optional[str] = None) -> str:
        """写入对象，返回最终对象键。"""
        ...

    def get(self, key: str) -> bytes:
        """读取对象，不存在时抛 :class:`FileNotFoundError`。"""
        ...

    def delete(self, key: str) -> None:
        """删除对象（不存在则静默成功）。"""
        ...

    def exists(self, key: str) -> bool:
        """判断对象是否存在。"""
        ...

    def healthcheck(self) -> bool:
        """探活：能否对后端执行一次最小读写。"""
        ...
