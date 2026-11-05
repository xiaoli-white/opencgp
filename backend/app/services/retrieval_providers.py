from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from app.config import Settings
from app.models.retrieval import (
    PROVIDER_KINDS,
    PROVIDER_KIND_EMBEDDING,
    PROVIDER_KIND_RERANK,
    PROVIDER_SCOPES,
    PROVIDER_SCOPE_GLOBAL,
    PROVIDER_SCOPE_TENANT,
    PROVIDER_SCOPE_USER,
    SOURCE_ENV,
    SOURCE_GLOBAL,
    SOURCE_TENANT,
    SOURCE_USER,
    RetrievalProvider,
    RetrievalSetting,
    SETTING_SCOPES,
    SETTING_SCOPE_TENANT,
    SETTING_SCOPE_USER,
)
from app.ports.retrieval_repository import RetrievalRepository
from app.services.crypto import decrypt_text, encrypt_text
from app.services.vector_math import cosine

EMBEDDING_BACKENDS = ("openai", "openai_compat", "hash")
RERANK_BACKENDS = (
    "llm",
    "cohere",
    "jina",
    "siliconflow",
    "zhipu",
    "tei",
    "generic",
    "http",
)

RERANK_PRESETS: dict[str, dict[str, str]] = {
    "cohere": {
        "format": "cohere",
        "base_url": "https://api.cohere.com/v1/rerank",
        "model": "rerank-v3.5",
    },
    "jina": {
        "format": "cohere",
        "base_url": "https://api.jina.ai/v1/rerank",
        "model": "jina-reranker-v2-base-multilingual",
    },
    "siliconflow": {
        "format": "cohere",
        "base_url": "https://api.siliconflow.cn/v1/rerank",
        "model": "BAAI/bge-reranker-v2-m3",
    },
    "zhipu": {
        "format": "cohere",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/rerank",
        "model": "rerank",
    },
    "tei": {
        "format": "tei",
        "base_url": "http://127.0.0.1:8080/rerank",
        "model": "BAAI/bge-reranker-v2-m3",
    },
    "generic": {"format": "generic", "base_url": "", "model": ""},
    "http": {"format": "generic", "base_url": "", "model": ""},
}


@dataclass
class ResolvedEmbedding:
    provider_id: str = "legacy"
    model: str = ""
    dim: int = 0
    backend: str = "none"
    source: str = SOURCE_ENV
    adapter: Any = None
    provider: RetrievalProvider | None = None
    error: str = ""


@dataclass
class ResolvedRerank:
    provider_id: str = ""
    model: str = ""
    backend: str = "none"
    source: str = SOURCE_ENV
    adapter: Any = None
    provider: RetrievalProvider | None = None
    error: str = ""

    @property
    def enabled(self) -> bool:
        return self.adapter is not None and self.backend != "none"


@dataclass
class ResolvedWeights:
    vector: float = 0.55
    rerank: float = 0.5
    top_n: int = 12
    source: str = SOURCE_ENV
    sources: dict[str, str] = field(default_factory=dict)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _source_of(provider: RetrievalProvider) -> str:
    scope = provider.scope()
    if scope == PROVIDER_SCOPE_USER:
        return SOURCE_USER
    if scope == PROVIDER_SCOPE_TENANT:
        return SOURCE_TENANT
    return SOURCE_GLOBAL


class RetrievalProviderService:
    def __init__(
        self,
        repository: RetrievalRepository,
        settings: Settings,
        secret: str = "",
        env_embedder: Callable[[], Any] | None = None,
        env_reranker: Callable[[str], Any] | None = None,
        llm_for: Callable[[str], Any] | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.secret = secret or ""
        self._env_embedder = env_embedder
        self._env_reranker = env_reranker
        self._llm_for = llm_for

    def api_key(self, provider: RetrievalProvider | None) -> str:
        if provider is None or not provider.api_key_cipher:
            return ""
        return decrypt_text(provider.api_key_cipher, self.secret)

    def payload(self, provider: RetrievalProvider) -> dict[str, Any]:
        return {
            "id": provider.id,
            "tenant_id": provider.tenant_id,
            "user_id": provider.user_id or "",
            "scope": provider.scope(),
            "kind": provider.kind,
            "name": provider.name,
            "backend": provider.backend,
            "base_url": provider.base_url,
            "model": provider.model,
            "dim": provider.dim,
            "enabled": provider.enabled,
            "is_default": provider.is_default,
            "has_key": bool(provider.api_key_cipher),
            "meta": dict(provider.meta or {}),
            "version": provider.version,
            "created_at": provider.created_at,
            "updated_at": provider.updated_at,
        }

    def list_payload(
        self, tenant_id: str, user_id: str, kind: str = ""
    ) -> dict[str, Any]:
        items = [
            self.payload(item)
            for item in self.repository.list_providers(tenant_id, user_id, kind)
        ]
        return {"count": len(items), "providers": items}

    def get_visible(
        self, tenant_id: str, user_id: str, provider_id: str, kind: str = ""
    ) -> RetrievalProvider:
        record = self.repository.get_provider(tenant_id, user_id, provider_id)
        if record is None:
            raise ValueError("provider 不存在")
        if kind and record.kind != kind:
            raise ValueError("provider 类型不匹配")
        return record

    def _normalize_backend(self, kind: str, backend: str) -> str:
        value = (backend or "").strip().lower()
        allowed = EMBEDDING_BACKENDS if kind == PROVIDER_KIND_EMBEDDING else RERANK_BACKENDS
        if value not in allowed:
            raise ValueError(f"不支持的 backend: {value or 'empty'}")
        return value

    def _scope_fields(
        self, scope: str, tenant_id: str, user_id: str
    ) -> tuple[str | None, str]:
        value = (scope or PROVIDER_SCOPE_USER).strip().lower()
        if value not in PROVIDER_SCOPES:
            raise ValueError("scope 仅支持 user / tenant / global")
        if value == PROVIDER_SCOPE_GLOBAL:
            return None, ""
        if value == PROVIDER_SCOPE_TENANT:
            return tenant_id, ""
        return tenant_id, user_id

    def create(
        self,
        tenant_id: str,
        user_id: str,
        kind: str,
        name: str,
        backend: str,
        base_url: str = "",
        model: str = "",
        dim: int = 0,
        api_key: str = "",
        is_default: bool = False,
        enabled: bool = True,
        scope: str = PROVIDER_SCOPE_USER,
        meta: dict[str, Any] | None = None,
        can_manage_server: bool = False,
    ) -> RetrievalProvider:
        self.repository.ensure_schema()
        resolved_kind = (kind or "").strip().lower()
        if resolved_kind not in PROVIDER_KINDS:
            raise ValueError("kind 仅支持 embedding / rerank")
        label = (name or "").strip()
        if not label:
            raise ValueError("name 不能为空")
        resolved_backend = self._normalize_backend(resolved_kind, backend)
        resolved_scope = (scope or PROVIDER_SCOPE_USER).strip().lower()
        if resolved_scope in (PROVIDER_SCOPE_TENANT, PROVIDER_SCOPE_GLOBAL) and not can_manage_server:
            raise PermissionError("scope 需要 manage_server")
        row_tenant, row_user = self._scope_fields(resolved_scope, tenant_id, user_id)
        resolved_model = (model or "").strip()
        resolved_dim = int(dim or 0)
        resolved_url = (base_url or "").strip()
        if resolved_kind == PROVIDER_KIND_EMBEDDING:
            if resolved_backend in ("openai", "openai_compat"):
                if not resolved_url:
                    raise ValueError("openai 兼容 embedding 需要 base_url")
                if not resolved_model:
                    raise ValueError("embedding 需要 model")
                if resolved_dim <= 0:
                    raise ValueError("embedding 需要 dim")
            else:
                resolved_model = resolved_model or "hash"
                if resolved_dim <= 0:
                    raise ValueError("embedding 需要 dim")
        else:
            if not resolved_model:
                preset = RERANK_PRESETS.get(resolved_backend) or {}
                resolved_model = str(preset.get("model") or "")
            if not resolved_url:
                preset = RERANK_PRESETS.get(resolved_backend) or {}
                resolved_url = str(preset.get("base_url") or "")
            if resolved_backend not in ("llm",) and not resolved_url:
                raise ValueError("rerank 需要 base_url")
        now = int(time.time())
        record = RetrievalProvider(
            id=f"rp_{uuid.uuid4().hex[:16]}",
            tenant_id=row_tenant,
            user_id=row_user,
            kind=resolved_kind,
            name=label,
            backend=resolved_backend,
            base_url=resolved_url,
            model=resolved_model,
            dim=resolved_dim,
            api_key_cipher=(
                encrypt_text((api_key or "").strip(), self.secret)
                if (api_key or "").strip()
                else ""
            ),
            enabled=bool(enabled),
            is_default=bool(is_default),
            meta=dict(meta or {}),
            version=1,
            created_at=now,
            updated_at=now,
        )
        return self.repository.save_provider(record)

    def update(
        self,
        tenant_id: str,
        user_id: str,
        provider_id: str,
        changes: dict[str, Any],
        can_manage_server: bool = False,
    ) -> RetrievalProvider:
        record = self.get_visible(tenant_id, user_id, provider_id)
        scope = record.scope()
        if scope in (PROVIDER_SCOPE_TENANT, PROVIDER_SCOPE_GLOBAL) and not can_manage_server:
            raise PermissionError("scope 需要 manage_server")
        if "name" in changes and changes.get("name") is not None:
            label = str(changes.get("name") or "").strip()
            if not label:
                raise ValueError("name 不能为空")
            record.name = label
        if "base_url" in changes and changes.get("base_url") is not None:
            record.base_url = str(changes.get("base_url") or "").strip()
        if "model" in changes and changes.get("model") is not None:
            record.model = str(changes.get("model") or "").strip()
        if "dim" in changes and changes.get("dim") is not None:
            record.dim = int(changes.get("dim") or 0)
        if "api_key" in changes and changes.get("api_key") is not None:
            raw = str(changes.get("api_key") or "").strip()
            record.api_key_cipher = encrypt_text(raw, self.secret) if raw else ""
        if "enabled" in changes and changes.get("enabled") is not None:
            record.enabled = bool(changes.get("enabled"))
        if "is_default" in changes and changes.get("is_default") is not None:
            record.is_default = bool(changes.get("is_default"))
        if "meta" in changes and changes.get("meta") is not None:
            meta = changes.get("meta")
            record.meta = dict(meta) if isinstance(meta, dict) else {}
        if record.kind == PROVIDER_KIND_EMBEDDING and record.dim <= 0:
            raise ValueError("embedding 需要 dim")
        record.version = int(record.version or 1) + 1
        record.updated_at = int(time.time())
        return self.repository.save_provider(record)

    def delete(
        self,
        tenant_id: str,
        user_id: str,
        provider_id: str,
        can_manage_server: bool = False,
    ) -> bool:
        record = self.get_visible(tenant_id, user_id, provider_id)
        if (
            record.scope() in (PROVIDER_SCOPE_TENANT, PROVIDER_SCOPE_GLOBAL)
            and not can_manage_server
        ):
            raise PermissionError("scope 需要 manage_server")
        return self.repository.delete_provider(tenant_id, user_id, provider_id)

    def _setting_provider(
        self,
        tenant_id: str,
        user_id: str,
        provider_id: str | None,
        kind: str,
    ) -> tuple[RetrievalProvider | None, str]:
        if not provider_id:
            return None, ""
        record = self.repository.get_provider(tenant_id, user_id, str(provider_id))
        if record is None or not record.enabled or record.kind != kind:
            return None, ""
        return record, _source_of(record)

    def _select_provider(
        self, tenant_id: str, user_id: str, kind: str, explicit_provider_id: str = ""
    ) -> tuple[RetrievalProvider | None, str, str]:
        if explicit_provider_id:
            if explicit_provider_id == "legacy":
                return None, SOURCE_ENV, ""
            record = self.repository.get_provider(tenant_id, user_id, explicit_provider_id)
            if record is None:
                raise ValueError("provider 不存在")
            if not record.enabled or record.kind != kind:
                raise ValueError("provider 不可用")
            return record, _source_of(record), ""
        user_setting = self.repository.get_setting(
            tenant_id, user_id, SETTING_SCOPE_USER
        )
        if user_setting is not None:
            field = (
                user_setting.embedding_provider_id
                if kind == PROVIDER_KIND_EMBEDDING
                else user_setting.rerank_provider_id
            )
            record, source = self._setting_provider(tenant_id, user_id, field, kind)
            if record is not None:
                return record, source, ""
        providers = self.repository.list_providers(tenant_id, user_id, kind)
        for provider in providers:
            if (
                provider.scope() == PROVIDER_SCOPE_USER
                and provider.enabled
                and provider.is_default
            ):
                return provider, SOURCE_USER, ""
        tenant_setting = self.repository.get_setting(
            tenant_id, "", SETTING_SCOPE_TENANT
        )
        if tenant_setting is not None:
            field = (
                tenant_setting.embedding_provider_id
                if kind == PROVIDER_KIND_EMBEDDING
                else tenant_setting.rerank_provider_id
            )
            record, source = self._setting_provider(tenant_id, user_id, field, kind)
            if record is not None:
                return record, source, ""
        for provider in providers:
            if (
                provider.scope() == PROVIDER_SCOPE_TENANT
                and provider.enabled
                and provider.is_default
            ):
                return provider, SOURCE_TENANT, ""
        for provider in providers:
            if (
                provider.scope() == PROVIDER_SCOPE_GLOBAL
                and provider.enabled
                and provider.is_default
            ):
                return provider, SOURCE_GLOBAL, ""
        return None, "", ""

    def _build_embedding(self, record: RetrievalProvider) -> Any:
        backend = (record.backend or "").strip().lower()
        if backend in ("openai", "openai_compat"):
            from app.adapters.embedding.openai_embedding import OpenAIEmbedding

            adapter = OpenAIEmbedding(
                base_url=record.base_url,
                api_key=self.api_key(record),
                model=record.model,
                dim=record.dim,
                batch=self.settings.embedding.batch,
                timeout=self.settings.embedding.timeout,
                query_prefix=self.settings.embedding.query_prefix,
            )
        elif backend == "hash":
            from app.adapters.embedding.hash_embedding import HashEmbedding

            adapter = HashEmbedding(
                dim=record.dim,
                query_prefix=self.settings.embedding.query_prefix,
                model=record.model or "hash",
            )
        else:
            raise ValueError(f"不支持的 embedding backend: {backend}")
        setattr(adapter, "provider_id", record.id)
        return adapter

    def _build_rerank(self, record: RetrievalProvider, user_id: str) -> Any:
        backend = (record.backend or "").strip().lower()
        if backend == "llm":
            from app.adapters.rerank.llm_rerank import LLMReranker

            provider = self._llm_for(user_id) if self._llm_for is not None else None
            adapter = LLMReranker(
                llm=provider,
                timeout=self.settings.rerank.timeout,
                batch_size=min(12, max(1, int(self.settings.rerank.top_n or 12))),
                max_doc_chars=self.settings.rerank.chars,
            )
        else:
            from app.adapters.rerank.remote_rerank import RemoteRerank

            preset = RERANK_PRESETS.get(backend) or {
                "format": "generic",
                "base_url": "",
                "model": "",
            }
            adapter = RemoteRerank(
                format=preset["format"],
                base_url=record.base_url or preset["base_url"],
                model=record.model or preset["model"],
                api_key=self.api_key(record),
                timeout=self.settings.rerank.timeout,
                retries=self.settings.rerank.retries,
                batch=min(100, max(1, int(self.settings.rerank.batch or 100))),
                chars=self.settings.rerank.chars,
                normalize=self.settings.rerank.normalize,
                raw_scores=self.settings.rerank.raw_scores,
            )
        setattr(adapter, "provider_id", record.id)
        setattr(adapter, "backend", backend)
        setattr(adapter, "model", record.model)
        return adapter

    def resolve_embedding(
        self,
        tenant_id: str,
        user_id: str,
        provider_id: str = "",
    ) -> ResolvedEmbedding:
        try:
            record, source, _ = self._select_provider(
                tenant_id, user_id, PROVIDER_KIND_EMBEDDING, provider_id
            )
        except ValueError as exc:
            return ResolvedEmbedding(
                provider_id=provider_id, source=SOURCE_ENV, error=str(exc)
            )
        if record is None:
            adapter = self._env_embedder() if self._env_embedder is not None else None
            model = str(
                getattr(adapter, "model", "") or self.settings.embedding.model or ""
            )
            dim = int(getattr(adapter, "dim", 0) or self.settings.embedding.dim or 0)
            return ResolvedEmbedding(
                provider_id=str(getattr(adapter, "provider_id", "legacy") or "legacy"),
                model=model,
                dim=dim,
                backend=(self.settings.embedding.backend or "none").strip().lower(),
                source=SOURCE_ENV,
                adapter=adapter,
            )
        try:
            adapter = self._build_embedding(record)
        except Exception as exc:
            return ResolvedEmbedding(
                provider_id=record.id,
                model=record.model,
                dim=record.dim,
                backend=record.backend,
                source=source,
                provider=record,
                error=str(exc),
            )
        return ResolvedEmbedding(
            provider_id=record.id,
            model=record.model,
            dim=record.dim,
            backend=record.backend,
            source=source,
            adapter=adapter,
            provider=record,
        )

    def resolve_rerank(
        self,
        tenant_id: str,
        user_id: str,
        provider_id: str = "",
    ) -> ResolvedRerank:
        try:
            record, source, _ = self._select_provider(
                tenant_id, user_id, PROVIDER_KIND_RERANK, provider_id
            )
        except ValueError as exc:
            return ResolvedRerank(
                provider_id=provider_id, source=SOURCE_ENV, error=str(exc)
            )
        if record is None:
            adapter = (
                self._env_reranker(user_id) if self._env_reranker is not None else None
            )
            backend = (self.settings.rerank.backend or "none").strip().lower()
            if adapter is None or backend == "none":
                return ResolvedRerank(
                    backend=backend,
                    source=SOURCE_ENV,
                    adapter=None,
                )
            return ResolvedRerank(
                provider_id=str(getattr(adapter, "provider_id", "legacy") or "legacy"),
                model=str(
                    getattr(adapter, "model", "") or self.settings.rerank.model or ""
                ),
                backend=backend,
                source=SOURCE_ENV,
                adapter=adapter,
            )
        try:
            adapter = self._build_rerank(record, user_id)
        except Exception as exc:
            return ResolvedRerank(
                provider_id=record.id,
                model=record.model,
                backend=record.backend,
                source=source,
                provider=record,
                error=str(exc),
            )
        return ResolvedRerank(
            provider_id=record.id,
            model=record.model,
            backend=record.backend,
            source=source,
            adapter=adapter,
            provider=record,
        )

    def resolve_weights(self, tenant_id: str, user_id: str) -> ResolvedWeights:
        user_setting = self.repository.get_setting(
            tenant_id, user_id, SETTING_SCOPE_USER
        )
        tenant_setting = self.repository.get_setting(
            tenant_id, "", SETTING_SCOPE_TENANT
        )
        sources: dict[str, str] = {}

        def pick(field: str, default: Any) -> Any:
            if user_setting is not None:
                value = getattr(user_setting, field)
                if value is not None:
                    sources[field] = SOURCE_USER
                    return value
            if tenant_setting is not None:
                value = getattr(tenant_setting, field)
                if value is not None:
                    sources[field] = SOURCE_TENANT
                    return value
            sources[field] = SOURCE_ENV
            return default

        vector_value = _clamp(
            float(pick("vector_weight", self.settings.vectorstore.vector_weight))
        )
        rerank_value = _clamp(
            float(pick("rerank_weight", self.settings.rerank.weight))
        )
        top_n_value = max(
            1, int(pick("rerank_top_n", self.settings.rerank.top_n))
        )
        overall = SOURCE_ENV
        if SOURCE_USER in sources.values():
            overall = SOURCE_USER
        elif SOURCE_TENANT in sources.values():
            overall = SOURCE_TENANT
        return ResolvedWeights(
            vector=vector_value,
            rerank=rerank_value,
            top_n=top_n_value,
            source=overall,
            sources={
                "vector": sources.get("vector_weight", SOURCE_ENV),
                "rerank": sources.get("rerank_weight", SOURCE_ENV),
                "top_n": sources.get("rerank_top_n", SOURCE_ENV),
            },
        )

    def _overall_source(
        self,
        embedding: ResolvedEmbedding,
        rerank: ResolvedRerank,
        weights: ResolvedWeights,
    ) -> str:
        if embedding.source in (SOURCE_USER, SOURCE_TENANT):
            return embedding.source
        if rerank.source in (SOURCE_USER, SOURCE_TENANT):
            return rerank.source
        values = [
            weights.sources.get("vector", SOURCE_ENV),
            weights.sources.get("rerank", SOURCE_ENV),
            weights.sources.get("top_n", SOURCE_ENV),
        ]
        if SOURCE_USER in values:
            return SOURCE_USER
        if SOURCE_TENANT in values:
            return SOURCE_TENANT
        return SOURCE_ENV

    def effective_settings(
        self, tenant_id: str, user_id: str
    ) -> dict[str, Any]:
        embedding = self.resolve_embedding(tenant_id, user_id)
        rerank = self.resolve_rerank(tenant_id, user_id)
        weights = self.resolve_weights(tenant_id, user_id)
        source = self._overall_source(embedding, rerank, weights)
        embedding_payload = {
            "provider_id": embedding.provider_id,
            "model": embedding.model,
            "dim": embedding.dim,
            "backend": embedding.backend,
            "source": embedding.source,
            "enabled": embedding.adapter is not None,
            "has_key": bool(
                embedding.provider is not None and embedding.provider.api_key_cipher
            ),
        }
        if embedding.error:
            embedding_payload["error"] = embedding.error
        rerank_payload = {
            "provider_id": rerank.provider_id,
            "model": rerank.model,
            "backend": rerank.backend,
            "source": rerank.source,
            "enabled": rerank.enabled,
            "has_key": bool(
                rerank.provider is not None and rerank.provider.api_key_cipher
            ),
        }
        if rerank.error:
            rerank_payload["error"] = rerank.error
        return {
            "embedding": embedding_payload,
            "rerank": rerank_payload,
            "weights": {
                "vector": weights.vector,
                "rerank": weights.rerank,
                "top_n": weights.top_n,
                "sources": dict(weights.sources),
            },
            "source": source,
            "sources": {
                "embedding": embedding.source,
                "rerank": rerank.source,
                "vector_weight": weights.sources.get("vector", SOURCE_ENV),
                "rerank_weight": weights.sources.get("rerank", SOURCE_ENV),
                "rerank_top_n": weights.sources.get("top_n", SOURCE_ENV),
            },
            "embedding_provider_id": embedding.provider_id,
            "rerank_provider_id": rerank.provider_id,
            "vector_weight": weights.vector,
            "rerank_weight": weights.rerank,
            "rerank_top_n": weights.top_n,
        }

    def update_settings(
        self,
        tenant_id: str,
        user_id: str,
        scope: str,
        changes: dict[str, Any],
        can_manage_server: bool = False,
    ) -> dict[str, Any]:
        resolved_scope = (scope or SETTING_SCOPE_USER).strip().lower()
        if resolved_scope not in SETTING_SCOPES:
            raise ValueError("scope 仅支持 user / tenant")
        if resolved_scope == SETTING_SCOPE_TENANT and not can_manage_server:
            raise PermissionError("scope=tenant 需要 manage_server")
        row_user = user_id if resolved_scope == SETTING_SCOPE_USER else ""
        current = self.repository.get_setting(tenant_id, row_user, resolved_scope)
        setting = current or RetrievalSetting(
            tenant_id=tenant_id,
            user_id=row_user,
            scope=resolved_scope,
        )
        if "embedding_provider_id" in changes:
            value = changes.get("embedding_provider_id")
            if value:
                record = self.repository.get_provider(tenant_id, user_id, str(value))
                if record is None or record.kind != PROVIDER_KIND_EMBEDDING:
                    raise ValueError("embedding provider 不存在")
                setting.embedding_provider_id = record.id
            else:
                setting.embedding_provider_id = None
        if "rerank_provider_id" in changes:
            value = changes.get("rerank_provider_id")
            if value:
                record = self.repository.get_provider(tenant_id, user_id, str(value))
                if record is None or record.kind != PROVIDER_KIND_RERANK:
                    raise ValueError("rerank provider 不存在")
                setting.rerank_provider_id = record.id
            else:
                setting.rerank_provider_id = None
        if "vector_weight" in changes:
            value = changes.get("vector_weight")
            if value is None:
                setting.vector_weight = None
            else:
                setting.vector_weight = _clamp(float(value))
        if "rerank_weight" in changes:
            value = changes.get("rerank_weight")
            if value is None:
                setting.rerank_weight = None
            else:
                setting.rerank_weight = _clamp(float(value))
        if "rerank_top_n" in changes:
            value = changes.get("rerank_top_n")
            if value is None:
                setting.rerank_top_n = None
            else:
                setting.rerank_top_n = max(1, int(value))
        setting.updated_at = int(time.time())
        self.repository.save_setting(setting)
        return self.effective_settings(tenant_id, user_id)

    async def test_provider(
        self, tenant_id: str, user_id: str, provider_id: str
    ) -> dict[str, Any]:
        record = self.get_visible(tenant_id, user_id, provider_id)
        started = time.perf_counter()
        if record.kind == PROVIDER_KIND_EMBEDDING:
            try:
                adapter = self._build_embedding(record)
                timeout = max(3.0, min(30.0, float(self.settings.embedding.timeout)))
                vectors = await asyncio.wait_for(adapter.embed(["ping"]), timeout=timeout)
                latency_ms = int((time.perf_counter() - started) * 1000)
                if not vectors or not vectors[0]:
                    return {
                        "ok": False,
                        "latency_ms": latency_ms,
                        "error": "空向量",
                    }
                dim = len(vectors[0])
                score = cosine(vectors[0], vectors[0])
                result = {
                    "ok": dim == record.dim,
                    "latency_ms": latency_ms,
                    "dim": dim,
                    "expected_dim": record.dim,
                    "sample_score": round(float(score), 6),
                }
                if dim != record.dim:
                    result["error"] = (
                        f"维度不匹配: 期望 {record.dim}，实际 {dim}"
                    )
                return result
            except Exception as exc:
                return {
                    "ok": False,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "error": str(exc)[:300] or exc.__class__.__name__,
                }
        try:
            adapter = self._build_rerank(record, user_id)
            timeout = max(3.0, min(30.0, float(self.settings.rerank.timeout)))
            scores = await asyncio.wait_for(
                adapter.rerank("ping", ["ping", "pong"], 2), timeout=timeout
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            if len(scores) != 2:
                return {
                    "ok": False,
                    "latency_ms": latency_ms,
                    "error": f"rerank 返回条数异常: {len(scores)}",
                }
            return {
                "ok": True,
                "latency_ms": latency_ms,
                "sample_score": round(float(scores[0]), 6),
            }
        except Exception as exc:
            return {
                "ok": False,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "error": str(exc)[:300] or exc.__class__.__name__,
            }


__all__ = [
    "EMBEDDING_BACKENDS",
    "RERANK_BACKENDS",
    "RERANK_PRESETS",
    "ResolvedEmbedding",
    "ResolvedRerank",
    "ResolvedWeights",
    "RetrievalProviderService",
]
