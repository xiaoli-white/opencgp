from __future__ import annotations

from typing import Any

from pydantic import BaseModel

MEDIA_KIND_GENERATED = "generated"
MEDIA_KIND_UPLOADED = "uploaded"
MEDIA_KIND_SEARCHED = "searched"
MEDIA_KINDS = (MEDIA_KIND_GENERATED, MEDIA_KIND_UPLOADED, MEDIA_KIND_SEARCHED)

SOURCE_UPLOAD = "upload"
SOURCE_URL = "url"

IMAGE_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

IMAGE_EXTENSIONS = {
    "image/png": "png",
    "image/jpg": "jpg",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

DEFAULT_IMAGE_SIZE = "1024x1024"


class MediaAsset(BaseModel):
    id: str
    tenant_id: str = ""
    user_id: str = ""
    kind: str = MEDIA_KIND_UPLOADED
    prompt: str = ""
    source: str = SOURCE_UPLOAD
    object_key: str = ""
    content_type: str = "image/png"
    bytes: int = 0
    width: int = 0
    height: int = 0
    created_at: float = 0.0

    def url(self) -> str:
        return f"/api/v1/media/{self.id}"

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "prompt": self.prompt,
            "source": self.source,
            "url": self.url(),
            "content_type": self.content_type,
            "bytes": int(self.bytes),
            "width": int(self.width),
            "height": int(self.height),
            "created_at": self.created_at,
        }
