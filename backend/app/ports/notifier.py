from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Notifier(Protocol):
    name: str

    def available(self) -> bool: ...

    def send(self, to: str, subject: str, body: str, html: str | None = None) -> bool: ...

    def healthcheck(self) -> bool: ...
