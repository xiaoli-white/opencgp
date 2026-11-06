from __future__ import annotations

import uuid

from app.models.auth import DEFAULT_TENANT_ID, AuthContext
from app.models.media import (
    IMAGE_CONTENT_TYPES,
    IMAGE_EXTENSIONS,
    MEDIA_EXTENSIONS,
    MEDIA_KIND_GENERATED,
    MEDIA_KIND_UPLOADED,
    MediaAsset,
    SOURCE_UPLOAD,
)
from app.ports.image_provider import ImageProvider
from app.ports.media_repository import MediaRepository
from app.ports.storage import StorageBackend
from app.services.errors import (
    ImageGenerationUnavailableError,
    MediaAssetNotFoundError,
    MediaInvalidError,
)

DEFAULT_MAX_BYTES = 8 * 1024 * 1024
MAX_BATCH = 4


def _tenant_of(ctx: AuthContext) -> str:
    if ctx is None or ctx.tenant is None:
        return DEFAULT_TENANT_ID
    return ctx.tenant.id or DEFAULT_TENANT_ID


def _dimensions(data: bytes) -> tuple[int, int]:
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            return int(image.width), int(image.height)
    except Exception:  # noqa: BLE001
        return 0, 0


def _sniff_content_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "video/mp4"
    return ""


def detect_image_type(filename: str, content_type: str) -> tuple[str, str]:
    name = (filename or "").strip()
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix in IMAGE_CONTENT_TYPES:
        return IMAGE_CONTENT_TYPES[suffix], IMAGE_EXTENSIONS[IMAGE_CONTENT_TYPES[suffix]]
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime in IMAGE_EXTENSIONS:
        return mime, IMAGE_EXTENSIONS[mime]
    raise MediaInvalidError("images support only png/jpg/jpeg/webp")


class MediaService:
    def __init__(
        self,
        repository: MediaRepository,
        storage: StorageBackend,
        image_provider: ImageProvider | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.image_provider = image_provider
        self.max_bytes = int(max_bytes or DEFAULT_MAX_BYTES)

    def save_bytes(
        self,
        ctx: AuthContext,
        data: bytes,
        content_type: str,
        kind: str,
        prompt: str = "",
        source: str = SOURCE_UPLOAD,
    ) -> MediaAsset:
        if not data:
            raise MediaInvalidError("media content is empty")
        if len(data) > self.max_bytes:
            raise MediaInvalidError(
                f"media must not exceed {self.max_bytes // (1024 * 1024)}MB"
            )
        mime = (content_type or "").split(";")[0].strip().lower()
        extension = MEDIA_EXTENSIONS.get(mime, "")
        if not extension:
            sniffed = _sniff_content_type(data)
            if not sniffed:
                raise MediaInvalidError("unsupported media type; expected png/jpg/jpeg/webp/mp4")
            mime, extension = sniffed, MEDIA_EXTENSIONS[sniffed]
        tenant_id = _tenant_of(ctx)
        user_id = ctx.user.id if ctx is not None and ctx.user is not None else ""
        asset_id = f"media_{uuid.uuid4().hex[:16]}"
        object_key = f"media/{tenant_id}/{user_id}/{asset_id}.{extension}"
        try:
            self.storage.put(object_key, data, content_type=mime)
        except Exception as exc:  # noqa: BLE001
            raise MediaInvalidError(f"failed to save the media: {exc}") from exc
        width, height = _dimensions(data)
        asset = MediaAsset(
            id=asset_id,
            tenant_id=tenant_id,
            user_id=user_id,
            kind=kind or MEDIA_KIND_UPLOADED,
            prompt=prompt or "",
            source=source or SOURCE_UPLOAD,
            object_key=object_key,
            content_type=mime,
            bytes=len(data),
            width=width,
            height=height,
        )
        return self.repository.create(asset)

    def list_assets(
        self, ctx: AuthContext, kind: str | None = None, limit: int = 50
    ) -> list[MediaAsset]:
        return self.repository.list_assets(_tenant_of(ctx), kind=kind, limit=limit)

    def get_asset(self, ctx: AuthContext, asset_id: str) -> MediaAsset:
        asset = self.repository.get(asset_id, _tenant_of(ctx))
        if asset is None:
            raise MediaAssetNotFoundError("image not found")
        return asset

    def delete_asset(self, ctx: AuthContext, asset_id: str) -> bool:
        asset = self.get_asset(ctx, asset_id)
        removed = self.repository.delete(asset.id, _tenant_of(ctx))
        if removed and asset.object_key:
            try:
                self.storage.delete(asset.object_key)
            except Exception:  # noqa: BLE001
                pass
        return removed

    def read_bytes(self, asset: MediaAsset) -> bytes:
        try:
            return self.storage.get(asset.object_key)
        except FileNotFoundError as exc:
            raise MediaAssetNotFoundError("media not found") from exc
        except Exception as exc:  # noqa: BLE001
            raise MediaAssetNotFoundError(f"failed to read the media: {exc}") from exc

    def provider(self) -> ImageProvider | None:
        return self.image_provider

    async def generate(
        self,
        ctx: AuthContext,
        prompt: str,
        size: str = "1024x1024",
        n: int = 1,
    ) -> list[MediaAsset]:
        text = (prompt or "").strip()
        if not text:
            raise MediaInvalidError("prompt must not be empty")
        provider = self.image_provider
        if provider is None or getattr(provider, "is_placeholder", False):
            raise ImageGenerationUnavailableError("image generation service is not configured")
        count = max(1, min(int(n or 1), MAX_BATCH))
        images = await provider.generate(text, size=size or "1024x1024", n=count)
        assets: list[MediaAsset] = []
        for data in images:
            assets.append(
                self.save_bytes(
                    ctx,
                    data,
                    _sniff_content_type(data) or "image/png",
                    MEDIA_KIND_GENERATED,
                    prompt=text,
                    source=getattr(provider, "name", ""),
                )
            )
        return assets
