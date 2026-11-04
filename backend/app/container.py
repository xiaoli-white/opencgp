"""依赖注入容器（极简版）。

根据 ``Settings`` 选择 adapter 并装配，业务代码只依赖端口、不 import 具体实现。
后续可替换为更完整的 DI 框架（如 dependency-injector），调用方式不变。

用法：:

    from app.container import get_container
    db = get_container().database()
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Callable

from app.config import Settings, get_settings
from app.ports.auth_repository import AuthRepository
from app.ports.conversation_repository import ConversationRepository
from app.ports.blueprint_repository import BlueprintRepository
from app.ports.course_repository import CourseRepository
from app.ports.database import Database
from app.ports.embedding import EmbeddingProvider
from app.ports.exporter import Exporter
from app.ports.llm import LLMProvider
from app.ports.lock_repository import LockRepository
from app.ports.parser import DocumentParser
from app.ports.provider_catalog_repository import ProviderCatalogRepository
from app.ports.provider_settings_repository import ProviderSettingsRepository
from app.ports.user_provider_repository import UserProviderRepository
from app.ports.quota_repository import QuotaRepository
from app.ports.storage import StorageBackend
from app.ports.vectorstore import VectorStore
from app.ports.web_search import WebSearchPort
from app.ports.image_provider import ImageProvider
from app.ports.media_repository import MediaRepository
from app.ports.executor import Executor
from app.ports.research_repository import ResearchRepository
from app.ports.longform_repository import LongformRepository
from app.ports.job_repository import JobRepository
from app.ports.job_queue import JobQueue
from app.ports.creation_profile_repository import CreationProfileRepository
from app.services.auth import AuthService
from app.services.conversation import ConversationService
from app.services.blueprint import BlueprintService
from app.services.generation import GenerationService
from app.services.factcheck import FactCheckService
from app.services.export import ExportService
from app.services.ingest import IngestService
from app.services.locks import LockService
from app.services.provider_catalog import ProviderCatalogService
from app.services.provider_settings import ProviderSettingsService
from app.services.quota import QuotaService
from app.services.user_providers import UserProviderService
from app.services.research import ResearchService
from app.services.longform import LongformService
from app.services.jobs import JobService
from app.services.creation_profiles import CreationProfileService
from app.services.accounts import AccountAdminService
from app.services.media import MediaService

PROVIDER_CACHE_SIZE = 64


class Container:
    """按配置装配并缓存各端口实例的单例容器。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._instances: dict[str, Any] = {}
        self._provider_cache: OrderedDict[tuple[Any, ...], LLMProvider] = OrderedDict()

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
            settings = self.settings.storage
            backend = (settings.backend or "local").strip().lower()
            if backend == "local":
                from app.adapters.storage.local import LocalStorageBackend

                return LocalStorageBackend(root=settings.root)
            if backend in ("s3", "rustfs"):
                from app.adapters.storage.s3 import S3StorageBackend

                return S3StorageBackend(
                    endpoint=settings.endpoint,
                    bucket=settings.bucket,
                    access_key=settings.access_key,
                    secret_key=settings.secret_key,
                    region=settings.region,
                    prefix=settings.prefix,
                    timeout=settings.timeout,
                )
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
                storage=self.storage(),
                storage_prefix=self.settings.storage.prefix,

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

                cfg = self.settings.exporter
                return BuiltinExporter(
                    font_regular=cfg.font_regular,
                    font_bold=cfg.font_bold,
                    pdf_margin_mm=cfg.pdf_margin_mm,
                )
            raise ValueError(f"不支持的 exporter backend: {backend!r}")

        return self._get_or_build("exporter", build)

    def export_service(self) -> ExportService:
        def build() -> ExportService:
            return ExportService(
                course_repository=self.course_repository(),
                longform_repository=self.longform_repository(),
                exporter=self.exporter(),
            )

        return self._get_or_build("export_service", build)

    def course_repository(self) -> CourseRepository:
        def build() -> CourseRepository:
            from app.adapters.database.course_repository import DatabaseCourseRepository

            return DatabaseCourseRepository(database=self.database())

        return self._get_or_build("course_repository", build)

    def generation(self) -> GenerationService:
        def build() -> GenerationService:
            return GenerationService(
                repository=self.course_repository(),
                vectorstore=self.vectorstore(),
                llm=self.llm(),
                default_top_k=self.settings.generation.top_k,
                evidence_char_limit=self.settings.generation.evidence_char_limit,
                max_evidence=self.settings.generation.max_evidence,
                default_mode=self.settings.generation.default_mode,
                min_score=self.settings.vectorstore.min_score,
                factcheck=self.factcheck(),
            )

        return self._get_or_build("generation", build)

    def factcheck(self) -> FactCheckService:
        def build() -> FactCheckService:
            return FactCheckService(
                vectorstore=self.vectorstore(),
                llm=self.llm(),
                repository=self.course_repository(),
            )

        return self._get_or_build("factcheck", build)

    def blueprint_repository(self) -> BlueprintRepository:
        def build() -> BlueprintRepository:
            from app.adapters.database.blueprint_repository import (
                DatabaseBlueprintRepository,
            )

            return DatabaseBlueprintRepository(database=self.database())

        return self._get_or_build("blueprint_repository", build)

    def blueprint(self) -> BlueprintService:
        def build() -> BlueprintService:
            settings = self.settings.blueprint
            default_mode = settings.default_mode or self.settings.generation.default_mode
            return BlueprintService(
                repository=self.blueprint_repository(),
                course_repository=self.course_repository(),
                vectorstore=self.vectorstore(),
                llm=self.llm(),
                default_top_k=settings.top_k,
                default_mode=default_mode,
                min_score=self.settings.vectorstore.min_score,
            )

        return self._get_or_build("blueprint", build)

    def auth_repository(self) -> AuthRepository:
        def build() -> AuthRepository:
            from app.adapters.database.auth_repository import DatabaseAuthRepository

            return DatabaseAuthRepository(database=self.database())

        return self._get_or_build("auth_repository", build)

    def auth_service(self) -> AuthService:
        def build() -> AuthService:
            settings = self.settings.auth
            return AuthService(
                repository=self.auth_repository(),
                secret=settings.secret,
                ttl_seconds=settings.token_ttl_hours * 3600,
                mode=settings.mode,
                require_approval=settings.require_approval,
            )

        return self._get_or_build("auth_service", build)

    def provider_settings_repository(self) -> ProviderSettingsRepository:
        def build() -> ProviderSettingsRepository:
            from app.adapters.database.provider_settings_repository import (
                DatabaseProviderSettingsRepository,
            )

            return DatabaseProviderSettingsRepository(database=self.database())

        return self._get_or_build("provider_settings_repository", build)

    def provider_catalog_repository(self) -> ProviderCatalogRepository:
        def build() -> ProviderCatalogRepository:
            from app.adapters.database.provider_catalog_repository import (
                DatabaseProviderCatalogRepository,
            )

            return DatabaseProviderCatalogRepository(database=self.database())

        return self._get_or_build("provider_catalog_repository", build)

    def provider_catalog(self) -> ProviderCatalogService:
        def build() -> ProviderCatalogService:
            return ProviderCatalogService(
                repository=self.provider_catalog_repository(),
                server=self.settings.llm,
                secret=self.settings.auth.secret,
            )

        return self._get_or_build("provider_catalog", build)

    def user_provider_repository(self) -> UserProviderRepository:
        def build() -> UserProviderRepository:
            from app.adapters.database.user_provider_repository import (
                DatabaseUserProviderRepository,
            )

            return DatabaseUserProviderRepository(database=self.database())

        return self._get_or_build("user_provider_repository", build)

    def user_providers(self) -> UserProviderService:
        def build() -> UserProviderService:
            return UserProviderService(
                repository=self.user_provider_repository(),
                server=self.settings.llm,
                secret=self.settings.auth.secret,
                default_provider=self.llm,
            )

        return self._get_or_build("user_providers", build)

    def provider_settings(self) -> ProviderSettingsService:
        def build() -> ProviderSettingsService:
            return ProviderSettingsService(
                repository=self.provider_settings_repository(),
                server=self.settings.llm,
                secret=self.settings.auth.secret,
                default_provider=self.llm,
                catalog=self.provider_catalog(),
                user_providers=self.user_providers(),
                user_names=self._lookup_user,
            )

        return self._get_or_build("provider_settings", build)

    def _lookup_user(self, user_id: str):
        try:
            return self.auth_service().get_user(user_id)
        except Exception:
            return None

    def llm_for(self, user_id: str) -> LLMProvider:
        service = self.provider_settings()
        cache_key = service.cache_key(user_id)
        cached = self._provider_cache.get(cache_key)
        if cached is not None:
            self._provider_cache.move_to_end(cache_key)
            return cached
        provider = service.build_provider(user_id)
        self._provider_cache[cache_key] = provider
        while len(self._provider_cache) > PROVIDER_CACHE_SIZE:
            self._provider_cache.popitem(last=False)
        return provider

    def quota_repository(self) -> QuotaRepository:
        def build() -> QuotaRepository:
            from app.adapters.database.quota_repository import DatabaseQuotaRepository

            return DatabaseQuotaRepository(database=self.database())

        return self._get_or_build("quota_repository", build)

    def quota_service(self) -> QuotaService:
        def build() -> QuotaService:
            return QuotaService(repository=self.quota_repository())

        return self._get_or_build("quota_service", build)

    def lock_repository(self) -> LockRepository:
        def build() -> LockRepository:
            from app.adapters.database.quota_repository import DatabaseLockRepository

            return DatabaseLockRepository(database=self.database())

        return self._get_or_build("lock_repository", build)

    def lock_service(self) -> LockService:
        def build() -> LockService:
            return LockService(
                repository=self.lock_repository(),
                ttl_seconds=self.settings.locks.ttl_seconds,
            )

        return self._get_or_build("lock_service", build)

    def web_search(self) -> WebSearchPort:
        def build() -> WebSearchPort:
            settings = self.settings.websearch
            backend = (settings.backend or "none").strip().lower()
            if backend in ("generic", "http_json", "generic_json"):
                from app.adapters.websearch.http_json import HttpJsonWebSearch

                return HttpJsonWebSearch(
                    url=settings.url,
                    api_key=settings.api_key,
                    result_path=settings.result_path,
                    method=settings.method,
                    timeout=settings.timeout,
                )
            from app.adapters.websearch.none import NullWebSearch

            return NullWebSearch()

        return self._get_or_build("web_search", build)

    def research_repository(self) -> ResearchRepository:
        def build() -> ResearchRepository:
            from app.adapters.database.research_repository import (
                DatabaseResearchRepository,
            )

            return DatabaseResearchRepository(database=self.database())

        return self._get_or_build("research_repository", build)

    def research(self) -> ResearchService:
        def build() -> ResearchService:
            return ResearchService(
                repository=self.research_repository(),
                vectorstore=self.vectorstore(),
                llm=self.llm(),
                web_search=self.web_search(),
                min_score=self.settings.vectorstore.min_score,
            )

        return self._get_or_build("research", build)

    def longform_repository(self) -> LongformRepository:
        def build() -> LongformRepository:
            from app.adapters.database.longform_repository import (
                DatabaseLongformRepository,
            )

            return DatabaseLongformRepository(database=self.database())

        return self._get_or_build("longform_repository", build)

    def longform(self) -> LongformService:
        def build() -> LongformService:
            return LongformService(
                repository=self.longform_repository(),
                vectorstore=self.vectorstore(),
                llm=self.llm(),
            )

        return self._get_or_build("longform", build)

    def job_repository(self) -> JobRepository:
        def build() -> JobRepository:
            from app.adapters.database.job_repository import DatabaseJobRepository

            return DatabaseJobRepository(database=self.database())

        return self._get_or_build("job_repository", build)

    def job_queue(self) -> JobQueue:
        def build() -> JobQueue:
            settings = self.settings.jobs
            backend = (settings.queue_backend or "local").strip().lower()
            if backend == "redis":
                try:
                    from app.adapters.queue.redis import build_redis_job_queue

                    return build_redis_job_queue(
                        url=settings.redis_url,
                        concurrency=settings.concurrency,
                        max_attempts=settings.max_attempts,
                        brpop_timeout=settings.brpop_timeout,
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"[queue] redis backend 不可用，回落 local: {exc!r}")
            from app.adapters.queue.local import LocalJobQueue

            return LocalJobQueue(concurrency=settings.concurrency)

        return self._get_or_build("job_queue", build)

    def job_events(self):
        def build():
            settings = self.settings.jobs
            backend = (settings.queue_backend or "local").strip().lower()
            if backend == "redis":
                try:
                    from app.adapters.queue.redis import build_redis_job_event_bus

                    return build_redis_job_event_bus(url=settings.redis_url)
                except Exception as exc:
                    print(f"[jobs] redis 事件总线不可用，回落本地: {exc!r}")
            from app.adapters.queue.local import NullJobEventBus

            return NullJobEventBus()

        return self._get_or_build("job_events", build)

    def job_service(self) -> JobService:
        def build() -> JobService:
            settings = self.settings.jobs
            return JobService(
                repository=self.job_repository(),
                queue=self.job_queue(),
                research=self.research(),
                longform=self.longform(),
                generation=self.generation(),
                blueprint=self.blueprint(),
                quota=self.quota_service(),
                llm_for=self.llm_for,
                events=self.job_events(),
                default_top_k=self.settings.generation.top_k,
                default_mode=self.settings.generation.default_mode,
            )

        return self._get_or_build("job_service", build)

    def creation_profile_repository(self) -> CreationProfileRepository:
        def build() -> CreationProfileRepository:
            from app.adapters.database.creation_profile_repository import (
                DatabaseCreationProfileRepository,
            )

            return DatabaseCreationProfileRepository(database=self.database())

        return self._get_or_build("creation_profile_repository", build)

    def creation_profiles(self) -> CreationProfileService:
        def build() -> CreationProfileService:
            return CreationProfileService(repository=self.creation_profile_repository())

        return self._get_or_build("creation_profiles", build)

    def account_admin(self) -> AccountAdminService:
        def build() -> AccountAdminService:
            return AccountAdminService(
                auth=self.auth_service(),
                user_providers=self.user_provider_repository(),
                provider_settings=self.provider_settings_repository(),
                locks=self.lock_repository(),
                conversations=self.conversation_repository(),
                courses=self.course_repository(),
                longforms=self.longform_repository(),
            )

        return self._get_or_build("account_admin", build)

    def image_provider(self) -> ImageProvider:
        def build() -> ImageProvider:
            settings = self.settings.image
            backend = (settings.backend or "none").strip().lower()
            if backend == "openai_images" and settings.api_key:
                from app.adapters.imagegen.openai_images import OpenAIImageProvider

                return OpenAIImageProvider(
                    base_url=settings.base_url,
                    api_key=settings.api_key,
                    model=settings.model,
                    timeout=settings.timeout,
                )
            from app.adapters.imagegen.none import NullImageProvider

            return NullImageProvider()

        return self._get_or_build("image_provider", build)

    def media_repository(self) -> MediaRepository:
        def build() -> MediaRepository:
            from app.adapters.database.media_repository import (
                DatabaseMediaRepository,
            )

            return DatabaseMediaRepository(database=self.database())

        return self._get_or_build("media_repository", build)

    def media_service(self) -> MediaService:
        def build() -> MediaService:
            return MediaService(
                repository=self.media_repository(),
                storage=self.storage(),
                image_provider=self.image_provider(),
                max_bytes=self.settings.image.max_bytes,
            )

        return self._get_or_build("media_service", build)

    def executor(self) -> Executor:
        def build() -> Executor:
            settings = self.settings.exec
            backend = (settings.backend or "docker").strip().lower()
            if backend == "docker":
                from app.adapters.executor.docker import DockerExecutor

                docker = DockerExecutor(
                    images=settings.images,
                    max_bytes=settings.max_bytes,
                    default_timeout=settings.timeout,
                )
                if docker.available():
                    return docker
                print(f"[exec] docker 后端不可用，回落 local: {docker.last_error}")
            if backend in ("docker", "local"):
                from app.adapters.executor.local import LocalExecutor

                local = LocalExecutor(
                    max_bytes=settings.max_bytes,
                    default_timeout=settings.timeout,
                )
                if local.available():
                    return local
                print("[exec] local 后端不可用，回落 none")
            from app.adapters.executor.null import NullExecutor

            return NullExecutor()

        return self._get_or_build("executor", build)

    def executor_backends(self) -> list[dict[str, Any]]:
        settings = self.settings.exec
        backends: list[dict[str, Any]] = []
        from app.adapters.executor.docker import DockerExecutor
        from app.adapters.executor.local import LocalExecutor
        from app.adapters.executor.null import NullExecutor

        docker = DockerExecutor(
            images=settings.images,
            max_bytes=settings.max_bytes,
            default_timeout=settings.timeout,
        )
        backends.append(
            {
                "id": "docker",
                "available": docker.available(),
                "isolated": True,
                "images": sorted(set(settings.images.values())),
                "missing_images": docker.missing_images(),
                "detail": docker.last_error,
            }
        )
        local = LocalExecutor(
            max_bytes=settings.max_bytes, default_timeout=settings.timeout
        )
        backends.append(
            {
                "id": "local",
                "available": local.available(),
                "isolated": False,
                "images": ["system-runtime"],
                "missing_images": [],
                "detail": "无网络隔离，仅适用于本地可信环境",
            }
        )
        null = NullExecutor()
        backends.append(
            {
                "id": "none",
                "available": null.available(),
                "isolated": False,
                "images": [],
                "missing_images": [],
                "detail": "未配置代码执行后端",
            }
        )
        return backends

    def code_check_service(self) -> Any:
        from app.services.codecheck import CodeCheckService

        def build() -> CodeCheckService:
            return CodeCheckService(self.executor())

        return self._get_or_build("code_check_service", build)

    def conversation_repository(self) -> ConversationRepository:
        def build() -> ConversationRepository:
            from app.adapters.database.conversation_repository import (
                DatabaseConversationRepository,
            )

            return DatabaseConversationRepository(database=self.database())

        return self._get_or_build("conversation_repository", build)

    def conversation(self) -> ConversationService:
        def build() -> ConversationService:
            settings = self.settings.conversation
            return ConversationService(
                repository=self.course_repository(),
                conversations=self.conversation_repository(),
                llm=self.llm(),
                history_limit=settings.history_limit,
                history_char_limit=settings.history_char_limit,
                content_char_limit=settings.content_char_limit,
                evidence_char_limit=settings.evidence_char_limit,
            )

        return self._get_or_build("conversation", build)


_default_container: Container | None = None


def get_container() -> Container:
    """返回进程级默认容器单例。"""
    global _default_container
    if _default_container is None:
        _default_container = Container()
    return _default_container
