from __future__ import annotations

from pydantic import BaseModel

LANGUAGES: dict[str, str] = {"python": "python", "node": "node", "bash": "bash"}

RUN_SPECS: dict[str, tuple[str, list[str]]] = {
    "python": ("python:3.12-slim", ["python", "-"]),
    "node": ("node:20-slim", ["node", "-"]),
    "bash": ("python:3.12-slim", ["bash", "-s"]),
}


class ExecResult(BaseModel):
    language: str
    backend: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: int = 0
    timed_out: bool = False
    truncated: bool = False
