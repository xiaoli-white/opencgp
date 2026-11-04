from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.exec import ExecResult


@runtime_checkable
class Executor(Protocol):
    name: str
    isolated: bool

    def available(self) -> bool: ...

    def run(
        self, language: str, code: str, stdin: str = "", timeout: int | None = None
    ) -> ExecResult: ...
