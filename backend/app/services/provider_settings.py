from __future__ import annotations

import hashlib
import time
from typing import Any, Callable

from app.config import LLMConfig
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

ProviderFactory = Callable[..., LLMProvider]


class ProviderSettingsService:
    def __init__(
        self,
        repository: ProviderSettingsRepository,
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

    def _default(self) -> LLMProvider:
        if self._default_provider is None:
            from app.adapters.llm.dummy import DummyProvider

            return DummyProvider()
        return self._default_provider()

    def _setting(self, user_id: str) -> ProviderSetting | None:
        return self.repository.get(user_id)

    def _api_key(self, setting: ProviderSetting | None) -> str:
        if setting is None or not setting.api_key_cipher:
            return ""
        return decrypt_text(setting.api_key_cipher, self.secret)

    def _server_payload(self) -> dict[str, Any]:
        return {
            "backend": self.server.backend,
            "base_url": self.server.base_url,
            "model": self.server.model,
            "has_key": bool(self.server.api_key),
        }

    def get_effective(self, user_id: str) -> dict[str, Any]:
        setting = self._setting(user_id)
        key = self._api_key(setting)
        source = (
            SETTING_SOURCE_USER
            if setting is not None and setting.backend and key
            else SETTING_SOURCE_SERVER
        )
        if source == SETTING_SOURCE_USER:
            payload = {
                "backend": setting.backend,
                "base_url": setting.base_url or self.server.base_url,
                "model": setting.model or self.server.model,
                "temperature": setting.temperature,
                "max_tokens": setting.max_tokens,
                "has_key": True,
                "api_key_masked": mask_secret(key),
                "updated_at": setting.updated_at,
            }
        else:
            payload = {
                "backend": self.server.backend,
                "base_url": self.server.base_url,
                "model": self.server.model,
                "temperature": setting.temperature if setting else DEFAULT_TEMPERATURE,
                "max_tokens": setting.max_tokens if setting else DEFAULT_MAX_TOKENS,
                "has_key": False,
                "api_key_masked": "",
                "updated_at": setting.updated_at if setting else 0.0,
            }
        payload["source"] = source
        payload["server"] = self._server_payload()
        return payload

    def save(
        self,
        user_id: str,
        backend: str,
        base_url: str,
        model: str,
        api_key: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        existing = self._setting(user_id)
        cipher = existing.api_key_cipher if existing is not None else ""
        raw_key = (api_key or "").strip()
        if raw_key:
            cipher = encrypt_text(raw_key, self.secret)
        setting = ProviderSetting(
            user_id=user_id,
            backend=(backend or "").strip(),
            base_url=(base_url or "").strip(),
            model=(model or "").strip(),
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
        setting = self._setting(user_id)
        key = self._api_key(setting)
        if setting is not None and setting.backend and key:
            digest = hashlib.sha256(
                f"{setting.backend}|{setting.base_url}|{setting.model}|{key}".encode(
                    "utf-8"
                )
            ).hexdigest()
            return (
                SETTING_SOURCE_USER,
                setting.backend,
                setting.base_url,
                setting.model,
                digest,
                setting.temperature,
                setting.max_tokens,
            )
        digest = hashlib.sha256(
            f"{self.server.backend}|{self.server.base_url}|{self.server.model}|"
            f"{self.server.api_key}".encode("utf-8")
        ).hexdigest()
        return (
            SETTING_SOURCE_SERVER,
            self.server.backend,
            self.server.base_url,
            self.server.model,
            digest,
        )

    def build_provider(self, user_id: str) -> LLMProvider:
        setting = self._setting(user_id)
        key = self._api_key(setting)
        if setting is not None and setting.backend and key:
            return self._factory(
                base_url=setting.base_url or self.server.base_url,
                api_key=key,
                model=setting.model or self.server.model,
                temperature=setting.temperature,
                max_tokens=setting.max_tokens,
            )
        return self._default()
