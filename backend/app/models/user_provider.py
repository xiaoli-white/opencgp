from __future__ import annotations

from pydantic import BaseModel, Field

USER_PROVIDER_PREFIX = "uprovider_"
SCOPE_USER = "user"
SCOPE_SERVER = "server"
SCOPE_SHARED = "shared"
SHARE_LEVEL_USE = "use"
SHARE_LEVEL_MANAGE = "manage"
SHARE_LEVELS = (SHARE_LEVEL_USE, SHARE_LEVEL_MANAGE)


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


class ProviderShare(BaseModel):
    id: str = ""
    provider_id: str = ""
    owner_user_id: str = ""
    user_id: str = ""
    level: str = SHARE_LEVEL_USE
    created_at: float = 0.0
    user_email: str = ""
    user_display_name: str = ""

    def can_use(self) -> bool:
        return self.level in SHARE_LEVELS

    def can_manage(self) -> bool:
        return self.level == SHARE_LEVEL_MANAGE
