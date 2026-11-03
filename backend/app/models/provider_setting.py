from __future__ import annotations

from pydantic import BaseModel

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
    updated_at: float = 0.0
