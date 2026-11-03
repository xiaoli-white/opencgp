from __future__ import annotations

from pydantic import BaseModel


class CreationProfile(BaseModel):
    id: str
    tenant_id: str = ""
    user_id: str = ""
    name: str = ""
    genre: str = "article"
    tone: str = ""
    audience: str = ""
    pov: str = ""
    citation_policy: str = "optional"
    target_words: int = 3000
    is_shared: bool = False
    created_at: float = 0.0
    updated_at: float = 0.0
