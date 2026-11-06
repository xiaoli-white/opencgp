from __future__ import annotations

import base64
from typing import Any

import httpx

from app.ports.image_provider import ImageProvider
from app.services.errors import (
    ImageGenerationError,
    ImageGenerationUnavailableError,
)

ERROR_LIMIT = 300


class OpenAIImageProvider(ImageProvider):
    name = "openai_images"
    is_placeholder = False

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "gpt-image-1",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or "gpt-image-1"
        self.timeout = float(timeout)

    def _endpoint(self) -> str:
        base = self.base_url or "https://api.openai.com/v1"
        return f"{base}/images/generations"

    def healthcheck(self) -> bool:
        return bool(self.base_url and self.api_key)

    async def _download(self, url: str, headers: dict[str, str]) -> bytes:
        """Fetch a generated image that came back as a URL instead of base64."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.content
        except Exception as exc:  # noqa: BLE001
            raise ImageGenerationError(
                f"failed to download the generated image: {type(exc).__name__}"
            ) from exc

    async def generate(
        self, prompt: str, size: str = "1024x1024", n: int = 1
    ) -> list[bytes]:
        if not self.api_key:
            raise ImageGenerationUnavailableError("image generation service is not configured")
        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": size or "1024x1024",
            "n": max(1, int(n or 1)),
            "response_format": "b64_json",
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self._endpoint(), json=payload, headers=headers)
        except Exception as exc:  # noqa: BLE001
            raise ImageGenerationError(str(exc)[:ERROR_LIMIT]) from exc
        if resp.status_code >= 400:
            raise ImageGenerationError(
                f"image generation failed {resp.status_code}: {resp.text[:ERROR_LIMIT]}"
            )
        try:
            body: Any = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise ImageGenerationError(
                f"image generation returned non-JSON: {resp.text[:ERROR_LIMIT]}"
            ) from exc
        images: list[bytes] = []
        for item in (body or {}).get("data") or []:
            item = item or {}
            encoded = item.get("b64_json")
            if encoded:
                try:
                    images.append(base64.b64decode(encoded))
                except Exception as exc:  # noqa: BLE001
                    raise ImageGenerationError("failed to decode the image data") from exc
                continue
            # Several providers ignore response_format=b64_json and return a URL.
            remote_url = item.get("url")
            if remote_url:
                images.append(await self._download(remote_url, headers))
        if not images:
            raise ImageGenerationError("image generation returned an empty result")
        return images
