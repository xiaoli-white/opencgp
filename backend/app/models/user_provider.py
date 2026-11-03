from __future__ import annotations

from pydantic import BaseModel, Field

USER_PROVIDER_PREFIX = "uprovider_"
SCOPE_USER = "user"
SCOPE_SERVER = "server"


class UserProvider(BaseModel):
    id: str
    user_id: str
    name: str = ""
    kind: str = "openai_compat"
    base_url: str = ""
    api_key_cipher: str = ""
    models: list[str] = Field(default_factory=list)
    enabled: bool = True
    is_default: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0
