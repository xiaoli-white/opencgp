from __future__ import annotations

import time
from typing import Any, Callable

from app.config import LLMConfig
from app.models.provider_catalog import (
    DEFAULT_PROVIDER_ID,
    DEFAULT_PROVIDER_NAME,
    PROVIDER_KIND_DUMMY,
    PROVIDER_KIND_OPENAI,
    PROVIDER_KINDS,
    SERVER_MAX_TOKENS,
    SERVER_TEMPERATURE,
    ServerProvider,
)
from app.ports.llm import LLMProvider
from app.ports.provider_catalog_repository import ProviderCatalogRepository
from app.services.crypto import decrypt_text, encrypt_text, mask_secret
from app.services.errors import (
    DefaultProviderError,
    ProviderInUseError,
    ProviderNotFoundError,
)

ProviderFactory = Callable[..., LLMProvider]


class ProviderCatalogService:
    def __init__(
        self,
        repository: ProviderCatalogRepository,
        server: LLMConfig,
        secret: str = "",
        provider_factory: ProviderFactory | None = None,
        default_provider: Callable[[], LLMProvider] | None = None,
    ) -> None:
        self.repository = repository
        self.server = server
        self.secret = secret or ""
        self._provider_factory = provider_factory
        self._default_provider = default_provider
        self._seeded = False

    def _factory(self, **kwargs: Any) -> LLMProvider:
        if self._provider_factory is None:
            from app.adapters.llm.openai_compat import OpenAICompatLLM

            return OpenAICompatLLM(**kwargs)
        return self._provider_factory(**kwargs)

    def _dummy(self) -> LLMProvider:
        if self._default_provider is None:
            from app.adapters.llm.dummy import DummyProvider

            return DummyProvider()
        return self._default_provider()

    def ensure_seed(self) -> None:
        if self._seeded:
            return
        self.repository.ensure_schema()
        if self.repository.count() == 0:
            self.repository.save_provider(self._seed_record())
        self._seeded = True

    def _seed_record(self) -> ServerProvider:
        kind = self.server.backend if self.server.backend in PROVIDER_KINDS else ""
        if kind in ("", PROVIDER_KIND_OPENAI) and not self.server.api_key:
            kind = PROVIDER_KIND_DUMMY
        if not kind:
            kind = PROVIDER_KIND_OPENAI
        models = [self.server.model] if self.server.model else []
        return ServerProvider(
            id=DEFAULT_PROVIDER_ID,
            name=DEFAULT_PROVIDER_NAME,
            kind=kind,
            base_url=self.server.base_url,
            api_key_cipher=(
                encrypt_text(self.server.api_key, self.secret)
                if self.server.api_key
                else ""
            ),
            models=models,
            enabled=True,
            is_default=True,
            created_at=time.time(),
            updated_at=time.time(),
        )

    def api_key(self, provider: ServerProvider | None) -> str:
        if provider is None or not provider.api_key_cipher:
            return ""
        return decrypt_text(provider.api_key_cipher, self.secret)

    def list(self) -> list[ServerProvider]:
        self.ensure_seed()
        return self.repository.list_providers()

    def get(self, provider_id: str) -> ServerProvider | None:
        if not provider_id:
            return None
        self.ensure_seed()
        return self.repository.get_provider(provider_id)

    def default(self) -> ServerProvider | None:
        for provider in self.list():
            if provider.is_default:
                return provider
        items = self.list()
        return items[0] if items else None

    def payload(self, provider: ServerProvider) -> dict[str, Any]:
        key = self.api_key(provider)
        return {
            "id": provider.id,
            "name": provider.name,
            "kind": provider.kind,
            "base_url": provider.base_url,
            "models": list(provider.models),
            "enabled": provider.enabled,
            "is_default": provider.is_default,
            "has_key": bool(key),
            "api_key_masked": mask_secret(key),
            "updated_at": provider.updated_at,
        }

    def option(self, provider: ServerProvider) -> dict[str, Any]:
        key = self.api_key(provider)
        return {
            "id": provider.id,
            "name": provider.name,
            "kind": provider.kind,
            "models": list(provider.models),
            "has_key": bool(key),
            "is_default": provider.is_default,
            "enabled": provider.enabled,
        }

    def options(self) -> list[dict[str, Any]]:
        return [self.option(item) for item in self.list() if item.enabled]

    def summary(self) -> dict[str, Any]:
        provider = self.default()
        if provider is None:
            return {
                "id": "",
                "name": "",
                "kind": self.server.backend,
                "base_url": self.server.base_url,
                "models": [self.server.model] if self.server.model else [],
                "has_key": bool(self.server.api_key),
            }
        return {
            "id": provider.id,
            "name": provider.name,
            "kind": provider.kind,
            "base_url": provider.base_url,
            "models": list(provider.models),
            "has_key": bool(self.api_key(provider)),
        }

    def _normalize_kind(self, kind: str) -> str:
        value = (kind or "").strip()
        if value not in PROVIDER_KINDS:
            raise ValueError("kind 仅支持 openai_compat 或 dummy")
        return value

    def _normalize_models(self, models: list[str] | None) -> list[str]:
        seen: list[str] = []
        for item in models or []:
            text = str(item).strip()
            if text and text not in seen:
                seen.append(text)
        return seen

    def create(
        self,
        name: str,
        kind: str,
        base_url: str = "",
        api_key: str | None = None,
        models: list[str] | None = None,
        enabled: bool = True,
        is_default: bool = False,
    ) -> ServerProvider:
        self.ensure_seed()
        label = (name or "").strip()
        if not label:
            raise ValueError("provider 名称不能为空")
        record = ServerProvider(
            id=f"provider_{int(time.time() * 1000)}_{time.perf_counter_ns() % 100000}",
            name=label,
            kind=self._normalize_kind(kind),
            base_url=(base_url or "").strip(),
            api_key_cipher=(
                encrypt_text((api_key or "").strip(), self.secret)
                if (api_key or "").strip()
                else ""
            ),
            models=self._normalize_models(models),
            enabled=bool(enabled),
            is_default=bool(is_default),
            created_at=time.time(),
            updated_at=time.time(),
        )
        return self.repository.save_provider(record)

    def update(
        self,
        provider_id: str,
        name: str | None = None,
        kind: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        models: list[str] | None = None,
        enabled: bool | None = None,
        is_default: bool | None = None,
    ) -> ServerProvider:
        current = self.get(provider_id)
        if current is None:
            raise ProviderNotFoundError("provider 不存在")
        cipher = current.api_key_cipher
        raw_key = (api_key or "").strip()
        if raw_key:
            cipher = encrypt_text(raw_key, self.secret)
        record = current.model_copy(
            update={
                "name": (name or "").strip() or current.name,
                "kind": self._normalize_kind(kind) if kind else current.kind,
                "base_url": (
                    (base_url or "").strip() if base_url is not None else current.base_url
                ),
                "api_key_cipher": cipher,
                "models": (
                    self._normalize_models(models)
                    if models is not None
                    else list(current.models)
                ),
                "enabled": current.enabled if enabled is None else bool(enabled),
                "is_default": (
                    current.is_default if is_default is None else bool(is_default)
                ),
                "updated_at": time.time(),
            }
        )
        return self.repository.save_provider(record)

    def delete(self, provider_id: str, references: int = 0) -> None:
        current = self.get(provider_id)
        if current is None:
            raise ProviderNotFoundError("provider 不存在")
        if current.is_default:
            raise DefaultProviderError("默认 provider 不可删除，请先切换默认 provider")
        if references > 0:
            raise ProviderInUseError(
                f"该 provider 仍被 {references} 个用户设置引用，请先让用户切换 provider"
            )
        self.repository.delete_provider(provider_id)

    def build_provider(
        self, provider: ServerProvider, model: str = "", api_key: str = ""
    ) -> LLMProvider:
        if provider.kind == PROVIDER_KIND_DUMMY:
            return self._dummy()
        key = api_key or self.api_key(provider)
        return self._factory(
            base_url=provider.base_url or self.server.base_url,
            api_key=key,
            model=model or (provider.models[0] if provider.models else self.server.model),
            temperature=SERVER_TEMPERATURE,
            max_tokens=SERVER_MAX_TOKENS,
        )

    def resolve_model(self, provider: ServerProvider, model: str = "") -> str:
        target = (model or "").strip()
        if target:
            return target
        return provider.models[0] if provider.models else self.server.model

    def fingerprint(self, provider: ServerProvider) -> tuple[Any, ...]:
        return (
            provider.id,
            provider.kind,
            provider.base_url,
            tuple(provider.models),
            provider.updated_at,
            bool(provider.api_key_cipher),
        )
