"""Video generation service: structured input -> Remotion render -> media asset."""

from __future__ import annotations

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
    ) -> None:
        self.media = media
        self.public_base_url = (public_base_url or "").rstrip("/")
        self.renderer = renderer
        self.backend = (backend or "none").strip().lower()
        self.max_images = max(0, int(max_images))

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

        # Keep the JSON shape aligned with tools/remotion/render.mjs.
        props: dict[str, Any] = {
            "title": resolved_title,
            "points": resolved_bullets,
            "images": resolved_images,
            "brand": "OpenCGP",
            "durationInFrames": 300,
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
