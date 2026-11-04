from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 0
SETTING_SOURCE_USER = "user"
SETTING_SOURCE_SERVER = "server"


class ProviderSetting(BaseModel):
    user_id: str
    provider_id: str = ""
    backend: str = ""
    base_url: str = ""
    model: str = ""
    api_key_cipher: str = ""
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    extra_body: dict[str, Any] = Field(default_factory=dict)
    extra_headers: dict[str, str] = Field(default_factory=dict)
    updated_at: float = 0.0
