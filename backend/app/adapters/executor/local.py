from __future__ import annotations

import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time

from app.models.exec import LANGUAGES, ExecResult
from app.services.errors import ExecLanguageError, ExecUnavailableError

CPU_SECONDS = 10
ADDRESS_SPACE = 256 * 1024 * 1024
FILE_SIZE = 16 * 1024 * 1024
OPEN_FILES = 64


def _limit() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 2))
    resource.setrlimit(resource.RLIMIT_AS, (ADDRESS_SPACE, ADDRESS_SPACE))
    resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_SIZE, FILE_SIZE))
    resource.setrlimit(resource.RLIMIT_NOFILE, (OPEN_FILES, OPEN_FILES))


def _decode(raw: bytes, limit: int) -> tuple[str, bool]:
    truncated = len(raw) > limit
    if truncated:
        raw = raw[:limit]
    return raw.decode("utf-8", errors="replace"), truncated


class LocalExecutor:
    name = "local"
    isolated = False

    def __init__(self, max_bytes: int = 65536, default_timeout: int = 10) -> None:
        self.max_bytes = int(max_bytes)
        self.default_timeout = int(default_timeout)
        self.last_error = ""

    def _command(self, language: str) -> list[str]:
        if language == "python":
            return [sys.executable or "python3", "-"]
        if language == "node":
            binary = shutil.which("node")
            if not binary:
                raise ExecLanguageError("本机未安装 node 运行时")
            return [binary, "-"]
        if language == "bash":
            binary = shutil.which("bash")
            if not binary:
                raise ExecLanguageError("本机未安装 bash 运行时")
            return [binary, "-s"]
        raise ExecLanguageError(f"不支持的代码语言: {language!r}")

    def images_for(self, language: str) -> list[str]:
        return ["system-runtime"]

    def available(self) -> bool:
        return sys.executable is not None or shutil.which("python3") is not None

    def run(
        self, language: str, code: str, stdin: str = "", timeout: int | None = None
    ) -> ExecResult:
        resolved = (language or "").strip().lower()
        if resolved not in LANGUAGES:
            raise ExecLanguageError(f"不支持的代码语言: {language!r}")
        command = self._command(resolved)
        limit = int(timeout or self.default_timeout)
        workdir = tempfile.mkdtemp(prefix="opencgp-exec-")
        started = time.monotonic()
        timed_out = False
        out = b""
        err = b""
        exit_code = -1
        try:
            completed = subprocess.run(
                command,
                input=code.encode("utf-8"),
                capture_output=True,
                cwd=workdir,
                timeout=limit,
                preexec_fn=_limit,
                env={
                    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
                    "HOME": workdir,
                    "TMPDIR": workdir,
                    "LANG": "C.UTF-8",
                    "PYTHONIOENCODING": "utf-8",
                },
                check=False,
            )
            out, err = completed.stdout, completed.stderr
            exit_code = int(completed.returncode)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            out = exc.stdout or b""
            err = exc.stderr or b""
            exit_code = 124
        except ExecLanguageError:
            shutil.rmtree(workdir, ignore_errors=True)
            raise
        except Exception as exc:  # noqa: BLE001
            shutil.rmtree(workdir, ignore_errors=True)
            self.last_error = str(exc)
            raise ExecUnavailableError(f"代码执行失败: {exc}") from exc
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout, out_truncated = _decode(out or b"", self.max_bytes)
        stderr, err_truncated = _decode(err or b"", self.max_bytes)
        if timed_out:
            stderr = (stderr + f"\n执行超时（{limit}s），已终止进程").strip()
        return ExecResult(
            language=resolved,
            backend=self.name,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            timed_out=timed_out,
            truncated=out_truncated or err_truncated,
        )
