"""Export engine abstract port (Exporter).

Exports course content to a target format (Markdown / HTML / EPUB / PDF, etc.).
Design goal: export formats are pluggable (a new format = a new implementation,
with no changes to existing code). The M0 built-in implementation is a placeholder;
pandoc / weasyprint will be wired in later (PDF with embedded CJK fonts).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Exporter(Protocol):
    """Generic export port."""

    def export(self, content: dict[str, Any], fmt: str, **kwargs: Any) -> bytes:
        """Export course content to the given format (``fmt``) and return the binary artifact."""
        ...

    def healthcheck(self) -> bool:
        """Health check: whether the underlying rendering engine (e.g. pandoc/weasyprint) is available."""
        ...

    def available_formats(self) -> dict[str, bool]:
        """Return the availability of each export format (``{fmt: bool}``)."""
        ...
