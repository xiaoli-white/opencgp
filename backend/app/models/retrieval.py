from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

PROVIDER_KIND_EMBEDDING = "embedding"
PROVIDER_KIND_RERANK = "rerank"
PROVIDER_KINDS = (PROVIDER_KIND_EMBEDDING, PROVIDER_KIND_RERANK)

PROVIDER_SCOPE_USER = "user"
PROVIDER_SCOPE_TENANT = "tenant"
PROVIDER_SCOPE_GLOBAL = "global"
PROVIDER_SCOPES = (
    PROVIDER_SCOPE_USER,
    PROVIDER_SCOPE_TENANT,
    PROVIDER_SCOPE_GLOBAL,
)

SETTING_SCOPE_USER = "user"
SETTING_SCOPE_TENANT = "tenant"
SETTING_SCOPES = (SETTING_SCOPE_USER, SETTING_SCOPE_TENANT)

SOURCE_USER = "user"
SOURCE_TENANT = "tenant"
SOURCE_GLOBAL = "global"
SOURCE_ENV = "env"


class RetrievalProvider(BaseModel):
    id: str
    tenant_id: str | None = ""
    user_id: str | None = ""
    kind: str = PROVIDER_KIND_EMBEDDING
    name: str = ""
    backend: str = ""
    base_url: str = ""
    model: str = ""
    dim: int = 0
    api_key_cipher: str = ""
    enabled: bool = True
    is_default: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    created_at: int = 0
    updated_at: int = 0

    def scope(self) -> str:
        if self.tenant_id is None:
            return PROVIDER_SCOPE_GLOBAL
        return PROVIDER_SCOPE_USER if (self.user_id or "") else PROVIDER_SCOPE_TENANT


class RetrievalSetting(BaseModel):
    tenant_id: str
    user_id: str = ""
    scope: str = SETTING_SCOPE_USER
    embedding_provider_id: str | None = None
    rerank_provider_id: str | None = None
    vector_weight: float | None = None
    rerank_weight: float | None = None
    rerank_top_n: int | None = None
    updated_at: int = 0


__all__ = [
    "PROVIDER_KINDS",
    "PROVIDER_KIND_EMBEDDING",
    "PROVIDER_KIND_RERANK",
    "PROVIDER_SCOPES",
    "PROVIDER_SCOPE_GLOBAL",
    "PROVIDER_SCOPE_TENANT",
    "PROVIDER_SCOPE_USER",
    "RetrievalProvider",
    "RetrievalSetting",
    "SETTING_SCOPES",
    "SETTING_SCOPE_TENANT",
    "SETTING_SCOPE_USER",
    "SOURCE_ENV",
    "SOURCE_GLOBAL",
    "SOURCE_TENANT",
    "SOURCE_USER",
]
