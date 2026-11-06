from __future__ import annotations

from enum import Enum


class GenerationMode(str, Enum):
    strict = "strict"
    loose = "loose"

    @classmethod
    def normalize(cls, value: str | None) -> "GenerationMode":
        raw = (value or "").strip().lower()
        if raw == cls.loose.value:
            return cls.loose
        return cls.strict


LOOSE_NOTICE = "⚠️ This article was written by an LLM and has not been verified against knowledge-base evidence"

LOOSE_BANNER = f"> {LOOSE_NOTICE}"


def with_loose_notice(content: str) -> str:
    body = "\n".join(
        line for line in content.splitlines() if LOOSE_NOTICE not in line
    ).strip()
    if not body:
        return LOOSE_BANNER
    return f"{LOOSE_BANNER}\n\n{body}"
