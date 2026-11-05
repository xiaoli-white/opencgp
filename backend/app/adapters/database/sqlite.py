"""SQLite 数据库实现（builtin，M0 默认）。

实现 :class:`app.ports.database.Database` 端口，基于标准库 ``sqlite3``。
生产环境可将配置 ``COURSE_STUDIO_DATABASE_BACKEND`` 切为 ``postgres``
（配合 psycopg2/asyncpg 实现同一端口），业务代码零改动。

连接允许跨线程复用（``check_same_thread=False``）并用可重入锁串行化访问：
同步端点跑在线程池、异步端点跑在事件循环线程，二者会共用同一实例。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from app.ports.database import Database


class SQLiteDatabase(Database):
    """基于 SQLite 文件的数据库实现。"""

    def __init__(self, path: str = "data/opencgp.db") -> None:
        self.path = Path(path)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    def connect(self) -> None:
        with self._lock:
            if self._conn is not None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._conn = conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        with self._lock:
            conn = self._ensure_conn()
            conn.execute(sql, tuple(params))
            conn.commit()

    def fetchone(
        self, sql: str, params: Sequence[Any] = ()
    ) -> Optional[Mapping[str, Any]]:
        with self._lock:
            conn = self._ensure_conn()
            row = conn.execute(sql, tuple(params)).fetchone()
            return dict(row) if row is not None else None

    def fetchall(
        self, sql: str, params: Sequence[Any] = ()
    ) -> list[Mapping[str, Any]]:
        with self._lock:
            conn = self._ensure_conn()
            rows = conn.execute(sql, tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def healthcheck(self) -> bool:
        try:
            with self._lock:
                conn = self._ensure_conn()
                conn.execute("SELECT 1").fetchone()
                return True
        except Exception:  # noqa: BLE001
            return False
