"""Document parsing abstract port (DocumentParser).

Parses uploaded raw byte streams into plain text for chunking and indexing. The M0
built-in implementation supports pdf / docx / md / txt; OCR, table, web-page and
other parsers can be added later by adding adapters only, without changing business code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ParsedDocument:
    source_name: str
    text: str
    parser: str
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class DocumentParser(Protocol):
    """Generic document parsing port."""

    def supports(self, filename: str) -> bool:
        """Return whether the filename is supported (by extension)."""
        ...

    def parse(self, data: bytes, filename: str) -> ParsedDocument:
        """Parse the raw byte stream into plain text; raise ``ValueError`` on failure."""
        ...

    def healthcheck(self) -> bool:
        """Health check: whether the parser dependencies are available."""
        ...
