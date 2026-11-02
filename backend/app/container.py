"""依赖注入容器（极简版）。

根据 ``Settings`` 选择 adapter 并装配，业务代码只依赖端口、不 import 具体实现。
后续可替换为更完整的 DI 框架（如 dependency-injector），调用方式不变。

用法：:

    from app.container import get_container
    db = get_container().database()
"""

from __future__ import annotations

from typing import Any, Callable

from app.config import Settings, get_settings
from app.ports.database import Database
from app.ports.embedding import EmbeddingProvider
from app.ports.exporter import Exporter
from app.ports.llm import LLMProvider
from app.ports.parser import DocumentParser
from app.ports.storage import StorageBackend
from app.ports.vectorstore import VectorStore
from app.services.ingest import IngestService


class Container:
    """按配置装配并缓存各端口实例的单例容器。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._instances: dict[str, Any] = {}

    def _get_or_build(self, key: str, builder: Callable[[], Any]) -> Any:
        if key not in self._instances:
            self._instances[key] = builder()
        return self._instances[key]

    def database(self) -> Database:
        def build() -> Database:
            backend = self.settings.database.backend
            if backend == "sqlite":
                from app.adapters.database.sqlite import SQLiteDatabase

                return SQLiteDatabase(path=self.settings.database.path)
            raise ValueError(f"不支持的 database backend: {backend!r}")

        return self._get_or_build("database", build)

    def storage(self) -> StorageBackend:
        def build() -> StorageBackend:
            backend = self.settings.storage.backend
            if backend == "local":
                from app.adapters.storage.local import LocalStorageBackend

                return LocalStorageBackend(root=self.settings.storage.root)
            raise ValueError(f"不支持的 storage backend: {backend!r}")

        return self._get_or_build("storage", build)

    def llm(self) -> LLMProvider:
        def build() -> LLMProvider:
            backend = self.settings.llm.backend
            if backend == "dummy":
                from app.adapters.llm.dummy import DummyProvider

                return DummyProvider()
            if backend == "openai_compat":
                if not self.settings.llm.api_key:
                    from app.adapters.llm.dummy import DummyProvider

                    return DummyProvider()
                from app.adapters.llm.openai_compat import OpenAICompatLLM

                return OpenAICompatLLM(
                    base_url=self.settings.llm.base_url,
                    api_key=self.settings.llm.api_key,
                    model=self.settings.llm.model,
                )
            raise ValueError(f"不支持的 llm backend: {backend!r}")

        return self._get_or_build("llm", build)

    def parser(self) -> DocumentParser:
        def build() -> DocumentParser:
            backend = self.settings.parser.backend
            if backend == "builtin":
                from app.adapters.parser.builtin import BuiltinDocumentParser

                return BuiltinDocumentParser()
            raise ValueError(f"不支持的 parser backend: {backend!r}")

        return self._get_or_build("parser", build)

    def embedder(self) -> EmbeddingProvider | None:
        def build() -> EmbeddingProvider | None:
            backend = self.settings.embedding.backend
            if backend in ("", "none"):
                return None
            raise ValueError(f"不支持的 embedding backend: {backend!r}")

        return self._get_or_build("embedder", build)

    def vectorstore(self) -> VectorStore:
        def build() -> VectorStore:
            backend = self.settings.vectorstore.backend
            if backend == "simple":
                from app.adapters.vectorstore.simple import SimpleVectorStore

                return SimpleVectorStore(
                    path=self.settings.vectorstore.path,
                    embedder=self.embedder(),
                )
            raise ValueError(f"不支持的 vectorstore backend: {backend!r}")

        return self._get_or_build("vectorstore", build)

    def ingest(self) -> IngestService:
        def build() -> IngestService:
            return IngestService(
                vectorstore=self.vectorstore(),
                parser=self.parser(),
                chunk_size=self.settings.ingest.chunk_size,
                chunk_overlap=self.settings.ingest.chunk_overlap,
                max_file_mb=self.settings.ingest.max_file_mb,
            )

        return self._get_or_build("ingest", build)

    def exporter(self) -> Exporter:
        def build() -> Exporter:
            backend = self.settings.exporter.backend
            if backend == "builtin":
                from app.adapters.exporter.builtin import BuiltinExporter

                return BuiltinExporter()
            raise ValueError(f"不支持的 exporter backend: {backend!r}")

        return self._get_or_build("exporter", build)


_default_container: Container | None = None


def get_container() -> Container:
    """返回进程级默认容器单例。"""
    global _default_container
    if _default_container is None:
        _default_container = Container()
    return _default_container
