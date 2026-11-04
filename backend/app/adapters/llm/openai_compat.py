from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from app.ports.llm import LLMProvider
from app.services.errors import ProviderCallError


class OpenAICompatLLM(LLMProvider):
    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        timeout: float = 60.0,
        temperature: float | None = None,
        max_tokens: int | None = None,
        extra_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key
        self.model = model or "gpt-3.5-turbo"
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_body = dict(extra_body or {})
        self.extra_headers = dict(extra_headers or {})

    def _apply_defaults(self, payload: dict[str, Any]) -> dict[str, Any]:
        for key, value in self.extra_body.items():
            payload.setdefault(key, value)
        if self.temperature is not None and "temperature" not in payload:
            payload["temperature"] = float(self.temperature)
        if self.max_tokens and self.max_tokens > 0 and "max_tokens" not in payload:
            payload["max_tokens"] = int(self.max_tokens)
        return payload

    def _endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        for key, value in self.extra_headers.items():
            if str(key).strip():
                headers[str(key)] = str(value)
        return headers

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
        payload = self._apply_defaults(payload)
        payload.update(kwargs)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    self._endpoint(), headers=self._headers(), json=payload
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise ProviderCallError(_describe(exc)) from exc
        except (KeyError, IndexError, ValueError) as exc:
            raise ProviderCallError(f"响应结构异常: {exc!r}") from exc
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderCallError(f"响应缺少正文: {exc!r}") from exc

    async def stream_complete(
        self, prompt: str, **kwargs: Any
    ) -> AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": kwargs.pop("model", self.model),
            "messages": self._messages(prompt, kwargs),
            "stream": True,
        }
        payload.update(kwargs)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", self._endpoint(), headers=self._headers(), json=payload
                ) as resp:
                    if resp.status_code >= 400:
                        raise ProviderCallError(f"HTTP {resp.status_code}")
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
        except httpx.HTTPError as exc:
            raise ProviderCallError(_describe(exc)) from exc

    def healthcheck(self) -> bool:
        return bool(self.api_key and self.base_url)


def _describe(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        body = ""
        try:
            body = (exc.response.text or "").strip()
        except Exception:
            body = ""
        return f"HTTP {exc.response.status_code} {body or exc.response.reason_phrase}"
    if isinstance(exc, httpx.TimeoutException):
        return f"请求超时 {exc}"
    return f"{type(exc).__name__}: {exc}"
