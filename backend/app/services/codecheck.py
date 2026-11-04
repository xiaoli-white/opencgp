from __future__ import annotations

import re
from typing import Any

from app.ports.executor import Executor
from app.services.errors import ExecLanguageError, ExecUnavailableError

FENCE_PATTERN = re.compile(r"```([^\n`]*)\n(.*?)```", re.S)
LANGUAGE_ALIASES = {
    "python": "python",
    "py": "python",
    "python3": "python",
    "javascript": "node",
    "js": "node",
    "node": "node",
    "nodejs": "node",
    "bash": "bash",
    "sh": "bash",
    "shell": "bash",
}
DEFAULT_LANGUAGE = "python"
UNKNOWN_LANGUAGE = "unknown"
MAX_BLOCKS = 5
BLOCK_TIMEOUT = 8


def extract_blocks(content: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in FENCE_PATTERN.finditer(content or ""):
        tag = (match.group(1) or "").strip().lower()
        code = match.group(2) or ""
        if not code.strip():
            continue
        if not tag:
            language = DEFAULT_LANGUAGE
        else:
            language = LANGUAGE_ALIASES.get(tag, UNKNOWN_LANGUAGE)
        blocks.append({"language": language, "code": code})
    return blocks


class CodeCheckService:
    def __init__(
        self,
        executor: Executor,
        max_blocks: int = MAX_BLOCKS,
        timeout: int = BLOCK_TIMEOUT,
    ) -> None:
        self.executor = executor
        self.max_blocks = int(max_blocks)
        self.timeout = int(timeout)

    def check(self, content: str, language: str | None = None) -> dict[str, Any]:
        blocks = extract_blocks(content)
        if language:
            wanted = (language or "").strip().lower()
            blocks = [block for block in blocks if block["language"] == wanted]
        results: list[dict[str, Any]] = []
        executed = 0
        passed = 0
        failed = 0
        skipped = 0
        for index, block in enumerate(blocks):
            language = block["language"]
            if language == UNKNOWN_LANGUAGE:
                skipped += 1
                results.append(
                    {
                        "index": index,
                        "language": UNKNOWN_LANGUAGE,
                        "ok": False,
                        "stdout": "",
                        "stderr": "未识别的代码语言，已跳过",
                        "exit_code": None,
                        "duration_ms": 0,
                        "timed_out": False,
                    }
                )
                continue
            if executed >= self.max_blocks:
                skipped += 1
                continue
            executed += 1
            try:
                result = self.executor.run(
                    language, block["code"], timeout=self.timeout
                )
            except (ExecLanguageError, ExecUnavailableError) as exc:
                failed += 1
                results.append(
                    {
                        "index": index,
                        "language": language,
                        "ok": False,
                        "stdout": "",
                        "stderr": str(exc),
                        "exit_code": None,
                        "duration_ms": 0,
                        "timed_out": False,
                    }
                )
                continue
            except Exception as exc:  # noqa: BLE001
                failed += 1
                results.append(
                    {
                        "index": index,
                        "language": language,
                        "ok": False,
                        "stdout": "",
                        "stderr": f"执行异常: {exc}",
                        "exit_code": None,
                        "duration_ms": 0,
                        "timed_out": False,
                    }
                )
                continue
            ok = int(result.exit_code) == 0 and not result.timed_out
            if ok:
                passed += 1
            else:
                failed += 1
            results.append(
                {
                    "index": index,
                    "language": language,
                    "ok": ok,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": int(result.exit_code),
                    "duration_ms": int(result.duration_ms),
                    "timed_out": bool(result.timed_out),
                }
            )
        return {
            "blocks": results,
            "summary": {
                "total": len(results),
                "executed": executed,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "backend": getattr(self.executor, "name", ""),
            },
        }
