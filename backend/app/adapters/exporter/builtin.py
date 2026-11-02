"""导出引擎占位实现（builtin，M0 未实现）。

实现 :class:`app.ports.exporter.Exporter` 端口。当前为占位：可正常构造，
调用 ``export`` 时抛出 :class:`NotImplementedError`。后续接 pandoc / weasyprint，
输出 Markdown / HTML / EPUB / PDF（PDF 含中文字体内嵌）。
"""

from __future__ import annotations

from typing import Any

from app.ports.exporter import Exporter


class BuiltinExporter(Exporter):
    """内置导出引擎占位实现。"""

    def export(self, content: dict[str, Any], fmt: str, **kwargs: Any) -> bytes:
        raise NotImplementedError("Exporter adapter 尚未在 M0 Sprint 0 实现")

    def healthcheck(self) -> bool:
        return False
