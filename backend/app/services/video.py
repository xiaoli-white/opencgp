"""Video generation service: structured input -> Remotion render -> media asset."""

from __future__ import annotations

import base64
import re

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Callable

from app.models.auth import AuthContext
from app.models.media import MEDIA_KIND_VIDEO, MediaAsset
from app.services.errors import VideoUnavailableError

MAX_BULLETS = 6
MAX_IMAGES = 6


class VideoService:
    """Render a short video and persist it in the media library."""

    def __init__(
        self,
        media: Any,
        renderer: Any = None,
        backend: str = "none",
        max_images: int = MAX_IMAGES,
        public_base_url: str = "",
        duration_frames: int = 300,
    ) -> None:
        self.media = media
        self.public_base_url = (public_base_url or "").rstrip("/")
        self.renderer = renderer
        self.backend = (backend or "none").strip().lower()
        self.max_images = max(0, int(max_images))
        self.duration_frames = max(30, int(duration_frames or 300))

    def available(self) -> tuple[bool, str]:
        if self.backend != "remotion":
            return (
                False,
                "video generation is unavailable: OPENCGP_VIDEO_BACKEND is 'none'; "
                "set it to 'remotion' and configure OPENCGP_VIDEO_PROJECT",
            )
        if self.renderer is None:
            return (
                False,
                "video generation is unavailable: the Remotion renderer is not configured",
            )
        checker = getattr(self.renderer, "check", None)
        if callable(checker):
            return checker()
        return True, ""


    async def _inline(self, ctx: AuthContext, url: str) -> str:
        """Inline a media asset so the headless browser needs no credentials.

        The renderer runs outside the API process and cannot send the auth
        header, so protected media URLs would 401. Assets that already point at
        a remote URL are left untouched.
        """
        match = re.search(r"/api/v1/media/([A-Za-z0-9_\-]+)", url or "")
        if not match or self.media is None:
            return url
        try:
            asset = self.media.get_asset(ctx, match.group(1))
            data = self.media.read_bytes(asset)
        except Exception:  # noqa: BLE001 - fall back to the raw url
            return url
        content_type = getattr(asset, "content_type", "") or "image/png"
        return f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"

    async def generate(
        self,
        ctx: AuthContext,
        title: str,
        bullets: list[str],
        image_urls: list[str],
        on_progress: Callable[[float], None] | None = None,
    ) -> MediaAsset:
        ok, reason = self.available()
        if not ok:
            raise VideoUnavailableError(reason)

        resolved_title = (title or "").strip()
        if not resolved_title:
            raise ValueError("video title must not be empty")
        resolved_bullets = [str(item).strip() for item in (bullets or []) if str(item).strip()]
        if not resolved_bullets:
            raise ValueError("video needs at least one bullet point")
        resolved_bullets = resolved_bullets[:MAX_BULLETS]
        base = (getattr(self, "public_base_url", "") or "").rstrip("/")
        resolved_images = []
        for item in image_urls or []:
            url = str(item).strip()
            if not url:
                continue
            # Relative media paths only work when the renderer can reach the API host.
            if url.startswith("/") and base:
                url = f"{base}{url}"
            resolved_images.append(url)
        if len(resolved_images) > self.max_images:
            resolved_images = resolved_images[: self.max_images]
        if self.media is not None:
            resolved_images = [
                await self._inline(ctx, url) for url in resolved_images
            ]

        # Keep the JSON shape aligned with tools/remotion/render.mjs.
        props: dict[str, Any] = {
            "title": resolved_title,
            "points": resolved_bullets,
            "images": resolved_images,
            "brand": "OpenCGP",
            "durationInFrames": max(30, int(getattr(self, "duration_frames", 300) or 300)),
            "fps": 30,
        }

        def report(value: float) -> None:
            if on_progress is not None:
                on_progress(max(0.0, min(float(value), 1.0)))

        report(0.05)
        with tempfile.TemporaryDirectory(prefix="opencgp-video-") as workdir:
            out_path = str(Path(workdir) / "render.mp4")
            await self.renderer.render(props, out_path, on_progress=report)
            data = Path(out_path).read_bytes()
            if not data:
                raise ValueError("the renderer produced an empty video file")
            report(0.9)
            asset = await asyncio.to_thread(
                self.media.save_bytes,
                ctx,
                data,
                "video/mp4",
                MEDIA_KIND_VIDEO,
                resolved_title[:200],
                "remotion",
            )
        report(0.98)
        return asset
