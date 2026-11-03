from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.config import LLMConfig
from app.models.provider_catalog import (
    PROVIDER_KIND_DUMMY,
    SERVER_MAX_TOKENS,
    SERVER_TEMPERATURE,
)
from app.models.provider_setting import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    SETTING_SOURCE_SERVER,
    SETTING_SOURCE_USER,
    ProviderSetting,
)
from app.ports.llm import LLMProvider
from app.ports.provider_settings_repository import ProviderSettingsRepository
from app.services.crypto import decrypt_text, encrypt_text, mask_secret
from app.services.errors import ProviderDisabledError, ProviderNotFoundError
from app.services.provider_catalog import ProviderCatalogService

ProviderFactory = Callable[..., LLMProvider]


@dataclass
class ResolvedProvider:
    source: str = SETTING_SOURCE_SERVER
    provider_id: str = ""
    provider_name: str = ""
    kind: str = ""
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    models: list[str] = field(default_factory=list)
    updated_at: float = 0.0

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


class ProviderSettingsService:
    def __init__(
        self,
        repository: ProviderSettingsRepository,
        server: LLMConfig,
        secret: str = "",
        provider_factory: ProviderFactory | None = None,
        default_provider: Callable[[], LLMProvider] | None = None,
        catalog: ProviderCatalogService | None = None,
    ) -> None:
        self.repository = repository
        self.server = server
        self.secret = secret or ""
        self._provider_factory = provider_factory
        self._default_provider = default_provider
        self.catalog = catalog or ProviderCatalogService(
            repository=None,
            server=server,
            secret=self.secret,
        )

    def _factory(self, **kwargs: Any) -> LLMProvider:
        if self._provider_factory is None:
            from app.adapters.llm.openai_compat import OpenAICompatLLM

            return OpenAICompatLLM(**kwargs)
        return self._provider_factory(**kwargs)

    def _default(self) -> LLMProvider:
        if self._default_provider is None:
            from app.adapters.llm.dummy import DummyProvider

            return DummyProvider()
        return self._default_provider()

    def _setting(self, user_id: str) -> ProviderSetting | None:
        return self.repository.get(user_id)

    def _user_key(self, setting: ProviderSetting | None) -> str:
        if setting is None or not setting.api_key_cipher:
            return ""
        return decrypt_text(setting.api_key_cipher, self.secret)

    def _server_payload(self) -> dict[str, Any]:
        summary = self.catalog.summary()
        summary.setdefault("backend", summary.get("kind", self.server.backend))
        summary.setdefault("model", self.server.model)
        summary["has_key"] = bool(summary.get("has_key") or self.server.api_key)
        return summary

    def resolve(self, user_id: str) -> ResolvedProvider:
        setting = self._setting(user_id)
        user_key = self._user_key(setting)
        temperature = setting.temperature if setting else DEFAULT_TEMPERATURE
        max_tokens = setting.max_tokens if setting else DEFAULT_MAX_TOKENS
        provider_id = (setting.provider_id if setting else "") or ""
        provider = self.catalog.get(provider_id) if provider_id else None
        if provider is not None and provider.enabled:
            key = user_key or self.catalog.api_key(provider)
            models = list(provider.models)
            model = (setting.model if setting else "") or (
                models[0] if models else self.server.model
            )
            return ResolvedProvider(
                source=SETTING_SOURCE_USER,
                provider_id=provider.id,
                provider_name=provider.name,
                kind=provider.kind,
                base_url=provider.base_url or self.server.base_url,
                model=model,
                api_key=key,
                temperature=temperature,
                max_tokens=max_tokens,
                models=models,
                updated_at=setting.updated_at if setting else 0.0,
            )
        if setting is not None and setting.backend and user_key:
            return ResolvedProvider(
                source=SETTING_SOURCE_USER,
                provider_id="",
                provider_name="",
                kind=setting.backend,
                base_url=setting.base_url or self.server.base_url,
                model=setting.model or self.server.model,
                api_key=user_key,
                temperature=temperature,
                max_tokens=max_tokens,
                models=[setting.model] if setting.model else [],
                updated_at=setting.updated_at,
            )
        default = self.catalog.default()
        if default is not None:
            models = list(default.models)
            chosen = (setting.model if setting else "") or (
                models[0] if models else self.server.model
            )
            return ResolvedProvider(
                source=SETTING_SOURCE_SERVER,
                provider_id=default.id,
                provider_name=default.name,
                kind=default.kind,
                base_url=default.base_url or self.server.base_url,
                model=chosen,
                api_key=self.catalog.api_key(default),
                temperature=temperature,
                max_tokens=max_tokens,
                models=models,
                updated_at=setting.updated_at if setting else 0.0,
            )
        return ResolvedProvider(
            source=SETTING_SOURCE_SERVER,
            kind=self.server.backend,
            base_url=self.server.base_url,
            model=(setting.model if setting else "") or self.server.model,
            api_key="",
            temperature=temperature,
            max_tokens=max_tokens,
            models=[self.server.model] if self.server.model else [],
            updated_at=setting.updated_at if setting else 0.0,
        )

    def get_effective(self, user_id: str) -> dict[str, Any]:
        resolved = self.resolve(user_id)
        return {
            "source": resolved.source,
            "provider_id": resolved.provider_id,
            "provider_name": resolved.provider_name,
            "backend": resolved.kind,
            "base_url": resolved.base_url,
            "model": resolved.model,
            "models": list(resolved.models),
            "temperature": resolved.temperature,
            "max_tokens": resolved.max_tokens,
            "has_key": resolved.has_key,
            "api_key_masked": mask_secret(resolved.api_key),
            "updated_at": resolved.updated_at,
            "providers": self.catalog.options(),
            "server": self._server_payload(),
        }

    def save(
        self,
        user_id: str,
        backend: str = "",
        base_url: str = "",
        model: str = "",
        api_key: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        provider_id: str | None = None,
    ) -> dict[str, Any]:
        existing = self._setting(user_id)
        cipher = existing.api_key_cipher if existing is not None else ""
        raw_key = (api_key or "").strip()
        if raw_key:
            cipher = encrypt_text(raw_key, self.secret)
        target = (provider_id or "").strip()
        next_backend = (backend or "").strip()
        next_base_url = (base_url or "").strip()
        next_model = (model or "").strip()
        next_provider_id = existing.provider_id if existing is not None else ""
        if target:
            provider = self.catalog.get(target)
            if provider is None:
                raise ProviderNotFoundError("指定的 provider 不存在")
            if not provider.enabled:
                raise ProviderDisabledError("指定的 provider 已被禁用")
            next_provider_id = provider.id
            next_backend = ""
            next_base_url = ""
        elif next_backend:
            next_provider_id = ""
        setting = ProviderSetting(
            user_id=user_id,
            provider_id=next_provider_id,
            backend=next_backend,
            base_url=next_base_url,
            model=next_model,
            api_key_cipher=cipher,
            temperature=(
                float(temperature)
                if temperature is not None
                else (existing.temperature if existing else DEFAULT_TEMPERATURE)
            ),
            max_tokens=(
                int(max_tokens)
                if max_tokens is not None
                else (existing.max_tokens if existing else DEFAULT_MAX_TOKENS)
            ),
            updated_at=time.time(),
        )
        self.repository.save(setting)
        return self.get_effective(user_id)

    def reset(self, user_id: str) -> dict[str, Any]:
        self.repository.delete(user_id)
        return self.get_effective(user_id)

    def cache_key(self, user_id: str) -> tuple[Any, ...]:
        resolved = self.resolve(user_id)
        digest = hashlib.sha256(resolved.api_key.encode("utf-8")).hexdigest()
        return (
            resolved.source,
            resolved.provider_id,
            resolved.kind,
            resolved.base_url,
            resolved.model,
            digest,
            resolved.temperature,
            resolved.max_tokens,
        )

    def build_provider(self, user_id: str) -> LLMProvider:
        resolved = self.resolve(user_id)
        if resolved.kind == PROVIDER_KIND_DUMMY:
            return self._default()
        if not resolved.has_key:
            return self._default()
        return self._factory(
            base_url=resolved.base_url or self.server.base_url,
            api_key=resolved.api_key,
            model=resolved.model or self.server.model,
            temperature=(
                resolved.temperature
                if resolved.temperature is not None
                else SERVER_TEMPERATURE
            ),
            max_tokens=resolved.max_tokens or SERVER_MAX_TOKENS,
        )
