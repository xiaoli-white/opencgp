from __future__ import annotations

import json

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
from app.models.user_provider import (
    SCOPE_SERVER,
    SCOPE_SHARED,
    SCOPE_USER,
    ProviderShare,
    UserProvider,
)
from app.ports.llm import LLMProvider
from app.ports.provider_settings_repository import ProviderSettingsRepository
from app.services.crypto import decrypt_text, encrypt_text, mask_secret
from app.services.errors import ProviderDisabledError, ProviderNotFoundError
from app.services.provider_catalog import ProviderCatalogService
from app.services.user_providers import UserProviderService

ProviderFactory = Callable[..., LLMProvider]


@dataclass
class ResolvedProvider:
    source: str = SETTING_SOURCE_SERVER
    scope: str = SCOPE_SERVER
    provider_id: str = ""
    provider_name: str = ""
    kind: str = ""
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    models: list[str] = field(default_factory=list)
    extra_body: dict[str, Any] = field(default_factory=dict)
    extra_headers: dict[str, str] = field(default_factory=dict)
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
        user_providers: UserProviderService | None = None,
        user_names: Callable[[str], Any] | None = None,
    ) -> None:
        self.repository = repository
        self.server = server
        self.secret = secret or ""
        self._provider_factory = provider_factory
        self._default_provider = default_provider
        self._user_names = user_names
        self.catalog = catalog or ProviderCatalogService(
            repository=None,
            server=server,
            secret=self.secret,
        )
        self.user_providers = user_providers or UserProviderService(
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

    def _personal(self, user_id: str, provider_id: str) -> UserProvider | None:
        try:
            return self.user_providers.get(user_id, provider_id)
        except ProviderNotFoundError:
            return None

    def _shared(
        self, user_id: str, provider_id: str
    ) -> tuple[UserProvider, ProviderShare] | None:
        share = self.user_providers.share_for(provider_id, user_id)
        if share is None:
            return None
        provider = self.user_providers.get_any(provider_id)
        if provider is None or provider.user_id == user_id:
            return None
        return provider, share

    def _owner_name(self, owner_user_id: str) -> str:
        if not owner_user_id:
            return ""
        if self._user_names is None:
            return owner_user_id
        try:
            user = self._user_names(owner_user_id)
        except Exception:
            return owner_user_id
        if user is None:
            return owner_user_id
        return getattr(user, "display_name", "") or getattr(user, "email", "")

    def _from_shared(
        self,
        provider: UserProvider,
        share: ProviderShare,
        setting: ProviderSetting | None,
        user_key: str,
        temperature: float,
        max_tokens: int,
    ) -> ResolvedProvider:
        models = list(provider.models)
        model = (setting.model if setting else "") or (
            models[0] if models else self.server.model
        )
        return ResolvedProvider(
            source=SETTING_SOURCE_USER,
            scope=SCOPE_SHARED,
            provider_id=provider.id,
            provider_name=provider.name,
            kind=provider.kind,
            base_url=provider.base_url or self.server.base_url,
            model=model,
            api_key=user_key or self.user_providers.api_key(provider),
            temperature=temperature,
            max_tokens=max_tokens,
            models=models,
            updated_at=max(
                provider.updated_at, setting.updated_at if setting else 0.0
            ),
        )

    def _from_personal(
        self,
        provider: UserProvider,
        setting: ProviderSetting | None,
        user_key: str,
        temperature: float,
        max_tokens: int,
    ) -> ResolvedProvider:
        models = list(provider.models)
        model = (setting.model if setting else "") or (
            models[0] if models else self.server.model
        )
        return ResolvedProvider(
            source=SETTING_SOURCE_USER,
            scope=SCOPE_USER,
            provider_id=provider.id,
            provider_name=provider.name,
            kind=provider.kind,
            base_url=provider.base_url or self.server.base_url,
            model=model,
            api_key=user_key or self.user_providers.api_key(provider),
            temperature=temperature,
            max_tokens=max_tokens,
            models=models,
            updated_at=max(
                provider.updated_at, setting.updated_at if setting else 0.0
            ),
        )

    def _from_server(
        self,
        provider: Any,
        setting: ProviderSetting | None,
        user_key: str,
        temperature: float,
        max_tokens: int,
    ) -> ResolvedProvider:
        models = list(provider.models)
        model = (setting.model if setting else "") or (
            models[0] if models else self.server.model
        )
        return ResolvedProvider(
            source=SETTING_SOURCE_USER if user_key else SETTING_SOURCE_SERVER,
            scope=SCOPE_SERVER,
            provider_id=provider.id,
            provider_name=provider.name,
            kind=provider.kind,
            base_url=provider.base_url or self.server.base_url,
            model=model,
            api_key=user_key or self.catalog.api_key(provider),
            temperature=temperature,
            max_tokens=max_tokens,
            models=models,
            updated_at=max(
                provider.updated_at, setting.updated_at if setting else 0.0
            ),
        )

    def resolve(self, user_id: str) -> ResolvedProvider:
        setting = self._setting(user_id)
        resolved = self._resolve_core(user_id)
        if setting is not None:
            resolved.extra_body = dict(setting.extra_body or {})
            resolved.extra_headers = dict(setting.extra_headers or {})
        return resolved

    def _resolve_core(self, user_id: str) -> ResolvedProvider:
        setting = self._setting(user_id)
        user_key = self._user_key(setting)
        temperature = setting.temperature if setting else DEFAULT_TEMPERATURE
        max_tokens = setting.max_tokens if setting else DEFAULT_MAX_TOKENS
        provider_id = (setting.provider_id if setting else "") or ""
        if provider_id:
            personal = self._personal(user_id, provider_id)
            if personal is not None and personal.enabled:
                return self._from_personal(
                    personal, setting, user_key, temperature, max_tokens
                )
            shared = self._shared(user_id, provider_id)
            if shared is not None and shared[0].enabled:
                return self._from_shared(
                    shared[0], shared[1], setting, user_key, temperature, max_tokens
                )
            server_provider = self.catalog.get(provider_id)
            if server_provider is not None and server_provider.enabled:
                return self._from_server(
                    server_provider, setting, user_key, temperature, max_tokens
                )
        personal_default = self.user_providers.default(user_id)
        if personal_default is not None and personal_default.enabled:
            return self._from_personal(
                personal_default, setting, user_key, temperature, max_tokens
            )
        if setting is not None and setting.backend and user_key:
            return ResolvedProvider(
                source=SETTING_SOURCE_USER,
                scope=SCOPE_USER,
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
                scope=SCOPE_SERVER,
                provider_id=default.id,
                provider_name=default.name,
                kind=default.kind,
                base_url=default.base_url or self.server.base_url,
                model=chosen,
                api_key=self.catalog.api_key(default),
                temperature=temperature,
                max_tokens=max_tokens,
                models=models,
                updated_at=max(
                    default.updated_at, setting.updated_at if setting else 0.0
                ),
            )
        return ResolvedProvider(
            source=SETTING_SOURCE_SERVER,
            scope=SCOPE_SERVER,
            kind=self.server.backend,
            base_url=self.server.base_url,
            model=(setting.model if setting else "") or self.server.model,
            api_key="",
            temperature=temperature,
            max_tokens=max_tokens,
            models=[self.server.model] if self.server.model else [],
            updated_at=setting.updated_at if setting else 0.0,
        )

    def options(self, user_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for provider in self.user_providers.list(user_id):
            if not provider.enabled:
                continue
            items.append(self.user_providers.option(provider))
        for provider, share in self.user_providers.shared_with_me(user_id):
            items.append(
                self.user_providers.shared_option(
                    provider, share, self._owner_name(provider.user_id)
                )
            )
        for provider in self.catalog.list():
            if not provider.enabled:
                continue
            option = self.catalog.option(provider)
            option["scope"] = SCOPE_SERVER
            items.append(option)
        return items

    def get_effective(self, user_id: str) -> dict[str, Any]:
        resolved = self.resolve(user_id)
        return {
            "source": resolved.source,
            "provider_id": resolved.provider_id,
            "provider_name": resolved.provider_name,
            "active_provider_id": resolved.provider_id,
            "active_scope": resolved.scope,
            "scope": resolved.scope,
            "backend": resolved.kind,
            "base_url": resolved.base_url,
            "model": resolved.model,
            "models": list(resolved.models),
            "temperature": resolved.temperature,
            "max_tokens": resolved.max_tokens,
            "has_key": resolved.has_key,
            "api_key_masked": mask_secret(resolved.api_key),
            "extra_body": dict(resolved.extra_body),
            "extra_headers": dict(resolved.extra_headers),
            "updated_at": resolved.updated_at,
            "providers": self.options(user_id),
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
        extra_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
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
            personal = self._personal(user_id, target)
            if personal is not None:
                if not personal.enabled:
                    raise ProviderDisabledError("指定的通道已被禁用")
                next_provider_id = personal.id
                next_backend = ""
                next_base_url = ""
            elif self.user_providers.can_use_shared(target, user_id):
                shared = self.user_providers.get_any(target)
                if shared is None:
                    raise ProviderNotFoundError("指定的 provider 不存在")
                if not shared.enabled:
                    raise ProviderDisabledError("指定的通道已被禁用")
                next_provider_id = shared.id
                next_backend = ""
                next_base_url = ""
            else:
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
            extra_body=(
                dict(extra_body)
                if extra_body is not None
                else (dict(existing.extra_body) if existing else {})
            ),
            extra_headers=(
                {str(k): str(v) for k, v in (extra_headers or {}).items()}
                if extra_headers is not None
                else (dict(existing.extra_headers) if existing else {})
            ),
            updated_at=time.time(),
        )
        self.repository.save(setting)
        return self.get_effective(user_id)

    def reset(self, user_id: str) -> dict[str, Any]:
        self.repository.delete(user_id)
        return self.get_effective(user_id)

    def clear_reference(self, user_id: str, provider_id: str) -> None:
        self.repository.clear_provider_reference(user_id, provider_id)

    def cache_key(self, user_id: str) -> tuple[Any, ...]:
        resolved = self.resolve(user_id)
        digest = hashlib.sha256(resolved.api_key.encode("utf-8")).hexdigest()
        return (
            resolved.scope,
            resolved.source,
            resolved.provider_id,
            resolved.kind,
            resolved.base_url,
            resolved.model,
            digest,
            resolved.temperature,
            resolved.max_tokens,
            json.dumps(resolved.extra_body, sort_keys=True, ensure_ascii=False),
            json.dumps(resolved.extra_headers, sort_keys=True, ensure_ascii=False),
            resolved.updated_at,
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
            extra_body=resolved.extra_body,
            extra_headers=resolved.extra_headers,
        )
