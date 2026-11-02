"""文档解析抽象端口（DocumentParser）。

把上传的原始字节流解析为纯文本，供分块与索引使用。M0 内置实现支持
pdf / docx / md / txt，后续可加 OCR、表格、网页等解析器，只增 adapter 不改业务。
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
    """通用文档解析端口。"""

    def supports(self, filename: str) -> bool:
        """判断是否支持该文件名（按扩展名）。"""
        ...

    def parse(self, data: bytes, filename: str) -> ParsedDocument:
        """解析原始字节流为纯文本，失败时抛 ``ValueError``。"""
        ...

    def healthcheck(self) -> bool:
        """探活：解析器依赖是否可用。"""
        ...
