"""数据库抽象端口（Database）。

定义持久化层的统一接口。业务代码只依赖本协议、不依赖具体驱动，
从而可在 SQLite（M0 内置默认）与 PostgreSQL/pgvector（生产）之间无缝切换，
无需改动任何业务代码。

约定：
- 查询结果以 ``dict`` 表示一行（列名 → 值）。
- 连接为惰性：首次使用前调用 ``connect()``，用毕调用 ``close()``；
  实现必须保证 ``connect`` / ``close`` 幂等。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, Sequence, runtime_checkable


@runtime_checkable
class Database(Protocol):
    """通用关系数据库端口。"""

    def connect(self) -> None:
        """建立连接（幂等）。"""
        ...

    def close(self) -> None:
        """关闭连接并释放资源（幂等）。"""
        ...

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        """执行写语句（INSERT/UPDATE/DELETE/DDL）并提交事务。"""
        ...

    def fetchone(
        self, sql: str, params: Sequence[Any] = ()
    ) -> Optional[Mapping[str, Any]]:
        """查询单行，无结果返回 ``None``。"""
        ...

    def fetchall(
        self, sql: str, params: Sequence[Any] = ()
    ) -> list[Mapping[str, Any]]:
        """查询多行，返回行列表。"""
        ...

    def healthcheck(self) -> bool:
        """探活：能否成功执行一次最小查询。"""
        ...
