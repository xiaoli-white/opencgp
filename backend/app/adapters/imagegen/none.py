from __future__ import annotations

from app.ports.image_provider import ImageProvider
from app.services.errors import ImageGenerationUnavailableError


class NullImageProvider(ImageProvider):
    name = "none"
    is_placeholder = True

    async def generate(
        self, prompt: str, size: str = "1024x1024", n: int = 1
    ) -> list[bytes]:
        raise ImageGenerationUnavailableError("image generation service is not configured")

    def healthcheck(self) -> bool:
        return False
