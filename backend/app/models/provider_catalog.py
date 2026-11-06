from __future__ import annotations

from pydantic import BaseModel, Field

PROVIDER_KIND_OPENAI = "openai_compat"
PROVIDER_KIND_DUMMY = "dummy"
PROVIDER_KINDS = (PROVIDER_KIND_OPENAI, PROVIDER_KIND_DUMMY)

SERVER_TEMPERATURE = 0.7
SERVER_MAX_TOKENS = 2048
DEFAULT_PROVIDER_NAME = "Server default"
DEFAULT_PROVIDER_ID = "provider_server_default"


class ServerProvider(BaseModel):
    id: str
    name: str = ""
    kind: str = PROVIDER_KIND_OPENAI
    base_url: str = ""
    api_key_cipher: str = ""
    models: list[str] = Field(default_factory=list)
    enabled: bool = True
    is_default: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0
