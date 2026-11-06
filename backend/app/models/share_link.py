from __future__ import annotations

from pydantic import BaseModel

RESOURCE_TYPES = ("series", "piece")


class ShareLink(BaseModel):
    id: str
    tenant_id: str = ""
    resource_type: str = ""
    resource_id: str = ""
    token: str = ""
    expires_at: float = 0.0
    revoked: bool = False
    view_count: int = 0
    created_by: str = ""
    created_at: float = 0.0
