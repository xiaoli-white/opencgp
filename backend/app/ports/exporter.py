"""导出引擎抽象端口（Exporter）。

把课程内容导出为目标格式（Markdown / HTML / EPUB / PDF 等）。
设计目标：导出格式可插件化（新增格式 = 新增一个实现，不改现有代码）。
M0 内置实现先占位，后续接 pandoc / weasyprint（PDF 含中文字体内嵌）。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Exporter(Protocol):
    """通用导出端口。"""

    def export(self, content: dict[str, Any], fmt: str, **kwargs: Any) -> bytes:
        """将课程内容导出为指定格式（``fmt``），返回二进制产物。"""
        ...

    def healthcheck(self) -> bool:
        """探活：底层渲染引擎（如 pandoc/weasyprint）是否可用。"""
        ...

    def available_formats(self) -> dict[str, bool]:
        """返回各导出格式的可用性（``{fmt: bool}``）。"""
        ...
