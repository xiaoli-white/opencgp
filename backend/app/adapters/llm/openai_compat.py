from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from app.ports.llm import LLMProvider


class OpenAICompatLLM(LLMProvider):
    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key
        self.model = model or "gpt-3.5-turbo"
        self.timeout = timeout

    def _endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _messages(
        self, prompt: str, kwargs: dict[str, Any]
    ) -> list[dict[str, Any]]:
        messages = kwargs.pop("messages", None)
        if messages is None:
            return [{"role": "user", "content": prompt}]
        return messages

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        payload: dict[str, Any] = {
            "model": kwargs.pop("model", self.model),
            "messages": self._messages(prompt, kwargs),
            "stream": False,
        }
        payload.update(kwargs)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self._endpoint(), headers=self._headers(), json=payload
            )
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def stream_complete(
        self, prompt: str, **kwargs: Any
    ) -> AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": kwargs.pop("model", self.model),
            "messages": self._messages(prompt, kwargs),
            "stream": True,
        }
        payload.update(kwargs)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", self._endpoint(), headers=self._headers(), json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    token = delta.get("content")
                    if token:
                        yield token

    def healthcheck(self) -> bool:
        return bool(self.api_key and self.base_url)
