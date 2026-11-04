from __future__ import annotations

from app.models.exec import ExecResult
from app.services.errors import ExecUnavailableError


class NullExecutor:
    name = "none"
    isolated = False
    last_error = "未配置代码执行后端"

    def available(self) -> bool:
        return False

    def images_for(self, language: str) -> list[str]:
        return []

    def run(
        self, language: str, code: str, stdin: str = "", timeout: int | None = None
    ) -> ExecResult:
        raise ExecUnavailableError("未配置代码执行后端")
