from __future__ import annotations

import time
from typing import Any, Callable

from app.config import LLMConfig
from app.models.provider_catalog import (
    PROVIDER_KIND_DUMMY,
    PROVIDER_KIND_OPENAI,
    PROVIDER_KINDS,
    SERVER_MAX_TOKENS,
    SERVER_TEMPERATURE,
)
from app.models.user_provider import (
    SCOPE_SHARED,
    SCOPE_USER,
    SHARE_LEVEL_MANAGE,
    SHARE_LEVEL_USE,
    SHARE_LEVELS,
    USER_PROVIDER_PREFIX,
    ProviderShare,
    UserProvider,
)
from app.ports.llm import LLMProvider
from app.ports.user_provider_repository import UserProviderRepository
from app.services.crypto import decrypt_text, encrypt_text, mask_secret
from app.services.errors import (
    DefaultProviderError,
    ProviderDisabledError,
    ProviderNotFoundError,
)

ProviderFactory = Callable[..., LLMProvider]


class UserProviderService:
    def __init__(
        self,
        repository: UserProviderRepository,
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

    def api_key(self, provider: UserProvider | None) -> str:
        if provider is None or not provider.api_key_cipher:
            return ""
        return decrypt_text(provider.api_key_cipher, self.secret)

    def list(self, user_id: str) -> list[UserProvider]:
        self.repository.ensure_schema()
        return self.repository.list_providers(user_id)

    def get(self, user_id: str, provider_id: str) -> UserProvider | None:
        if not provider_id:
            return None
        self.repository.ensure_schema()
        return self.repository.get_provider(user_id, provider_id)

    def require(self, user_id: str, provider_id: str) -> UserProvider:
        provider = self.get(user_id, provider_id)
        if provider is None:
            raise ProviderNotFoundError("个人通道不存在")
        return provider

    def default(self, user_id: str) -> UserProvider | None:
        for provider in self.list(user_id):
            if provider.is_default:
                return provider
        return None

    def get_any(self, provider_id: str) -> UserProvider | None:
        if not provider_id:
            return None
        self.repository.ensure_schema()
        return self.repository.get_provider_any(provider_id)

    def share_level(self, provider_id: str, user_id: str) -> str:
        if not provider_id or not user_id:
            return ""
        self.repository.ensure_schema()
        share = self.repository.get_share(provider_id, user_id)
        return share.level if share is not None else ""

    def can_use_shared(self, provider_id: str, user_id: str) -> bool:
        return self.share_level(provider_id, user_id) in SHARE_LEVELS

    def can_manage_shared(self, provider_id: str, user_id: str) -> bool:
        return self.share_level(provider_id, user_id) == SHARE_LEVEL_MANAGE

    def share_for(self, provider_id: str, user_id: str) -> ProviderShare | None:
        if not provider_id or not user_id:
            return None
        self.repository.ensure_schema()
        return self.repository.get_share(provider_id, user_id)

    def list_shares(self, provider_id: str) -> list[ProviderShare]:
        self.repository.ensure_schema()
        return self.repository.list_shares(provider_id)

    def shared_with_me(self, user_id: str) -> list[tuple[UserProvider, ProviderShare]]:
        self.repository.ensure_schema()
        items: list[tuple[UserProvider, ProviderShare]] = []
        for share in self.repository.list_shared_with(user_id):
            provider = self.repository.get_provider_any(share.provider_id)
            if provider is None or not provider.enabled:
                continue
            if provider.user_id == user_id:
                continue
            items.append((provider, share))
        return items

    def resolve_usable(
        self, user_id: str, provider_id: str
    ) -> tuple[UserProvider, str] | None:
        own = self.get(user_id, provider_id)
        if own is not None:
            return own, SCOPE_USER
        if not self.can_use_shared(provider_id, user_id):
            return None
        shared = self.get_any(provider_id)
        if shared is None:
            return None
        return shared, SCOPE_SHARED

    def replace_shares(
        self, owner_user_id: str, provider_id: str, shares: list[tuple[str, str]]
    ) -> list[ProviderShare]:
        current = self.require(owner_user_id, provider_id)
        cleaned: list[tuple[str, str]] = []
        seen: set[str] = set()
        for user_id, level in shares:
            target = (user_id or "").strip()
            if not target or target in seen or target == owner_user_id:
                continue
            seen.add(target)
            cleaned.append(
                (target, SHARE_LEVEL_MANAGE if level == SHARE_LEVEL_MANAGE else SHARE_LEVEL_USE)
            )
        return self.repository.replace_shares(
            current.id, owner_user_id, cleaned
        )

    def shared_option(
        self, provider: UserProvider, share: ProviderShare, owner_name: str = ""
    ) -> dict[str, Any]:
        key = self.api_key(provider)
        return {
            "id": provider.id,
            "name": provider.name,
            "kind": provider.kind,
            "models": list(provider.models),
            "has_key": bool(key),
            "is_default": False,
            "enabled": provider.enabled,
            "scope": SCOPE_SHARED,
            "shared_level": share.level,
            "can_manage": share.level == SHARE_LEVEL_MANAGE,
            "owner_user_id": provider.user_id,
            "owner_name": owner_name,
        }

    def payload(self, provider: UserProvider) -> dict[str, Any]:
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

    def option(self, provider: UserProvider) -> dict[str, Any]:
        key = self.api_key(provider)
        return {
            "id": provider.id,
            "name": provider.name,
            "kind": provider.kind,
            "models": list(provider.models),
            "has_key": bool(key),
            "is_default": provider.is_default,
            "enabled": provider.enabled,
            "scope": "user",
        }

    def list_payload(self, user_id: str) -> dict[str, Any]:
        items = [self.payload(item) for item in self.list(user_id)]
        return {"count": len(items), "providers": items}

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
        user_id: str,
        name: str,
        kind: str,
        base_url: str = "",
        api_key: str | None = None,
        models: list[str] | None = None,
        enabled: bool = True,
        is_default: bool = False,
    ) -> UserProvider:
        self.repository.ensure_schema()
        label = (name or "").strip()
        if not label:
            raise ValueError("通道名称不能为空")
        now = time.time()
        record = UserProvider(
            id=(
                f"{USER_PROVIDER_PREFIX}{int(now * 1000)}"
                f"_{time.perf_counter_ns() % 100000}"
            ),
            user_id=user_id,
            name=label,
            kind=self._normalize_kind(kind or PROVIDER_KIND_OPENAI),
            base_url=(base_url or "").strip(),
            api_key_cipher=(
                encrypt_text((api_key or "").strip(), self.secret)
                if (api_key or "").strip()
                else ""
            ),
            models=self._normalize_models(models),
            enabled=bool(enabled),
            is_default=bool(is_default),
            created_at=now,
            updated_at=now,
        )
        return self.repository.save_provider(record)

    def update(
        self,
        user_id: str,
        provider_id: str,
        name: str | None = None,
        kind: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        models: list[str] | None = None,
        enabled: bool | None = None,
        is_default: bool | None = None,
    ) -> UserProvider:
        current = self.get(user_id, provider_id)
        if current is None:
            shared = self.get_any(provider_id)
            if shared is None or not self.can_manage_shared(provider_id, user_id):
                raise ProviderNotFoundError("个人通道不存在")
            current = shared
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

    def delete(self, user_id: str, provider_id: str) -> None:
        current = self.require(user_id, provider_id)
        if current.is_default:
            raise DefaultProviderError("个人默认通道不可删除，请先切换默认通道")
        self.repository.delete_shares(current.id)
        self.repository.delete_provider(user_id, provider_id)

    def resolve_model(self, provider: UserProvider, model: str = "") -> str:
        target = (model or "").strip()
        if target:
            return target
        if provider.models:
            return provider.models[0]
        return self.server.model

    def build(
        self,
        user_id: str,
        provider_id: str,
        model: str = "",
        api_key: str = "",
    ) -> LLMProvider:
        resolved = self.resolve_usable(user_id, provider_id)
        if resolved is None:
            raise ProviderNotFoundError("个人通道不存在")
        provider = resolved[0]
        if not provider.enabled:
            raise ProviderDisabledError("该个人通道已被禁用")
        if provider.kind == PROVIDER_KIND_DUMMY:
            return self._dummy()
        key = api_key or self.api_key(provider)
        return self._factory(
            base_url=provider.base_url or self.server.base_url,
            api_key=key,
            model=self.resolve_model(provider, model),
            temperature=SERVER_TEMPERATURE,
            max_tokens=SERVER_MAX_TOKENS,
        )
