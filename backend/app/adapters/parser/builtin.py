from __future__ import annotations

from io import BytesIO
from importlib.util import find_spec
from pathlib import Path

from app.ports.parser import DocumentParser, ParsedDocument

PLAIN_SUFFIXES = {".txt", ".text", ".md", ".markdown", ".log", ".csv"}
SUPPORTED_SUFFIXES = PLAIN_SUFFIXES | {".pdf", ".docx"}


class BuiltinDocumentParser(DocumentParser):
    def supports(self, filename: str) -> bool:
        return Path(filename).suffix.lower() in SUPPORTED_SUFFIXES

    def parse(self, data: bytes, filename: str) -> ParsedDocument:
        suffix = Path(filename).suffix.lower()
        if suffix == ".pdf":
            return self._parse_pdf(data, filename)
        if suffix == ".docx":
            return self._parse_docx(data, filename)
        if suffix in PLAIN_SUFFIXES:
            return self._parse_plain(data, filename)
        raise ValueError(f"不支持的文档类型: {suffix or filename!r}")

    def _parse_plain(self, data: bytes, filename: str) -> ParsedDocument:
        text = _decode(data)
        if not text.strip():
            raise ValueError("文档内容为空")
        return ParsedDocument(
            source_name=filename,
            text=text,
            parser="builtin.plain",
            meta={"bytes": len(data)},
        )

    def _parse_pdf(self, data: bytes, filename: str) -> ParsedDocument:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("缺少 pypdf 依赖，无法解析 PDF") from exc

        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise ValueError("PDF 已加密，无法解析") from exc
        pages: list[str] = []
        for page in reader.pages:
            pages.append((page.extract_text() or "").strip())
        text = "\n\n".join(part for part in pages if part)
        if not text.strip():
            raise ValueError("PDF 未提取到文本（可能是扫描件，需 OCR）")
        return ParsedDocument(
            source_name=filename,
            text=text,
            parser="builtin.pypdf",
            meta={"pages": len(reader.pages), "bytes": len(data)},
        )

    def _parse_docx(self, data: bytes, filename: str) -> ParsedDocument:
        try:
            import docx
        except ImportError as exc:
            raise ValueError("缺少 python-docx 依赖，无法解析 DOCX") from exc

        document = docx.Document(BytesIO(data))
        blocks: list[str] = []
        for paragraph in document.paragraphs:
            body = paragraph.text.strip()
            if body:
                blocks.append(body)
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                line = " | ".join(cell for cell in cells if cell)
                if line:
                    blocks.append(line)
        text = "\n".join(blocks)
        if not text.strip():
            raise ValueError("DOCX 未提取到文本")
        return ParsedDocument(
            source_name=filename,
            text=text,
            parser="builtin.python-docx",
            meta={"blocks": len(blocks), "bytes": len(data)},
        )

    def healthcheck(self) -> bool:
        return all(
            find_spec(name) is not None for name in ("pypdf", "docx")
        )


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
