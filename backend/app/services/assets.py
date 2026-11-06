from __future__ import annotations

import re
from typing import Any

from app.models.auth import AuthContext

# The generation prompt asks the model to drop these markers where a visual helps:
#   [[image: a short scene description]]
PLACEHOLDER = re.compile(r"\[\[\s*(?:image|figure|img)\s*:\s*([^\]\n]{3,300}?)\s*\]\]", re.IGNORECASE)

DEFAULT_STYLE = (
    "editorial illustration, soft natural light, restrained palette, "
    "no text, no watermark, no logo"
)


class AssetMaterializer:
    """Turn ``[[image: ...]]`` markers in generated text into real media assets.

    The article stays the source of truth: each marker is replaced in place by a
    Markdown image pointing at the stored asset, so the body keeps its order and
    the image can still be swapped later from the media library.
    """

    def __init__(
        self,
        media: Any,
        enabled: bool = True,
        max_images: int = 3,
        size: str = "1024x1024",
        style: str = DEFAULT_STYLE,
    ) -> None:
        self.media = media
        self.enabled = bool(enabled)
        self.max_images = max(0, int(max_images))
        self.size = size or "1024x1024"
        self.style = (style or "").strip()

    def with_limit(self, remaining: int) -> "AssetMaterializer":
        """Return a copy capped to ``remaining`` images (used for a whole-piece budget)."""
        return AssetMaterializer(
            self.media,
            enabled=self.enabled,
            max_images=max(0, int(remaining)),
            size=self.size,
            style=self.style,
        )

    def has_placeholders(self, text: str) -> bool:
        return bool(text) and PLACEHOLDER.search(text) is not None

    def with_profile(self, spec: Any) -> "AssetMaterializer":
        """Return a copy with optional per-profile illustration settings applied."""
        profile_assets = getattr(spec, "assets", None) if spec is not None else None
        if profile_assets is None:
            return self
        auto_images = getattr(profile_assets, "auto_images", None)
        max_images = getattr(profile_assets, "max_images", None)
        raw_style = getattr(profile_assets, "style", "") or ""
        style = raw_style.strip()
        if auto_images is None and max_images is None and not style:
            return self
        return AssetMaterializer(
            self.media,
            enabled=self.enabled if auto_images is None else bool(auto_images),
            max_images=self.max_images if max_images is None else int(max_images),
            size=self.size,
            style=style or self.style,
        )

    def _prompt_for(self, description: str) -> str:
        description = description.strip()
        if self.style:
            return f"{description}. Style: {self.style}"
        return description

    async def materialize(
        self, ctx: AuthContext, text: str
    ) -> tuple[str, list[str], list[str]]:
        """Return (new_text, asset_ids, errors).

        Markers beyond ``max_images`` and any marker that fails to render are
        removed from the body so raw markers never leak into the article.
        """
        if not text:
            return text, [], []
        if not self.enabled or self.max_images == 0:
            return PLACEHOLDER.sub("", text).strip(), [], []

        matches = list(PLACEHOLDER.finditer(text))
        if not matches:
            return text, [], []

        pieces: list[str] = []
        asset_ids: list[str] = []
        errors: list[str] = []
        cursor = 0
        for index, match in enumerate(matches):
            pieces.append(text[cursor:match.start()])
            cursor = match.end()
            if index >= self.max_images:
                continue
            description = match.group(1).strip()
            alt = description[:80]
            try:
                assets = await self.media.generate(
                    ctx, self._prompt_for(description), size=self.size, n=1
                )
            except Exception as exc:  # noqa: BLE001 - a failed image must not fail the article
                errors.append(f"{type(exc).__name__}: {exc}"[:200])
                continue
            if not assets:
                errors.append("image provider returned no asset")
                continue
            asset = assets[0]
            asset_ids.append(asset.id)
            pieces.append(f"![{alt}](/api/v1/media/{asset.id})")
        pieces.append(text[cursor:])

        cleaned = PLACEHOLDER.sub("", "".join(pieces)).strip()
        return cleaned, asset_ids, errors
