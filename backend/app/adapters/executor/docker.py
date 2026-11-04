from __future__ import annotations

import secrets
import subprocess
import time

from app.models.exec import LANGUAGES, RUN_SPECS, ExecResult
from app.services.errors import ExecLanguageError, ExecUnavailableError

CONTAINER_PREFIX = "opencgp-exec-"
DEFAULT_MEMORY = "256m"
PIDS_LIMIT = "64"
CPUS = "0.5"
TMPFS_SIZE = "16m"
DEFAULT_IMAGES: dict[str, str] = {lang: spec[0] for lang, spec in RUN_SPECS.items()}


def _decode(raw: bytes, limit: int) -> tuple[str, bool]:
    truncated = len(raw) > limit
    if truncated:
        raw = raw[:limit]
    return raw.decode("utf-8", errors="replace"), truncated


class DockerExecutor:
    name = "docker"
    isolated = True

    def __init__(
        self,
        images: dict[str, str] | None = None,
        max_bytes: int = 65536,
        default_timeout: int = 10,
        docker_bin: str = "docker",
    ) -> None:
        self.images = dict(images or DEFAULT_IMAGES)
        self.max_bytes = int(max_bytes)
        self.default_timeout = int(default_timeout)
        self.docker_bin = docker_bin
        self.last_error = ""

    def images_for(self, language: str) -> list[str]:
        image = self.images.get(language)
        return [image] if image else []

    def _docker(self, args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.docker_bin, *args],
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def available(self) -> bool:
        try:
            version = self._docker(["version", "--format", "{{.Server.Version}}"])
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"docker 不可用: {exc!r}"
            return False
        if version.returncode != 0:
            self.last_error = version.stderr.decode("utf-8", errors="replace")[:300]
            return False
        missing: list[str] = []
        for image in sorted(set(self.images.values())):
            try:
                probe = self._docker(["image", "inspect", image], timeout=10.0)
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"镜像探测失败: {exc!r}"
                return False
            if probe.returncode != 0:
                missing.append(image)
        if len(missing) == len(set(self.images.values())):
            self.last_error = (
                "缺少执行镜像，请先拉取: "
                + ", ".join(sorted(set(self.images.values())))
            )
            return False
        self.last_error = ""
        return True

    def missing_images(self) -> list[str]:
        missing: list[str] = []
        for image in sorted(set(self.images.values())):
            try:
                probe = self._docker(["image", "inspect", image], timeout=10.0)
            except Exception:  # noqa: BLE001
                missing.append(image)
                continue
            if probe.returncode != 0:
                missing.append(image)
        return missing

    def _image_ready(self, image: str) -> bool:
        try:
            probe = self._docker(["image", "inspect", image], timeout=10.0)
        except Exception:  # noqa: BLE001
            return False
        return probe.returncode == 0

    def run(
        self, language: str, code: str, stdin: str = "", timeout: int | None = None
    ) -> ExecResult:
        resolved = (language or "").strip().lower()
        if resolved not in LANGUAGES:
            raise ExecLanguageError(f"不支持的代码语言: {language!r}")
        image, command = RUN_SPECS[resolved]
        image = self.images.get(resolved, image)
        if not self._image_ready(image):
            self.last_error = f"缺少执行镜像: {image}"
            raise ExecUnavailableError(f"缺少执行镜像 {image}，请先执行 docker pull")
        limit = int(timeout or self.default_timeout)
        container_name = CONTAINER_PREFIX + secrets.token_hex(6)
        args = [
            "run",
            "--rm",
            "-i",
            "--pull",
            "never",
            "--name",
            container_name,
            "--network",
            "none",
            "--memory",
            DEFAULT_MEMORY,
            "--memory-swap",
            DEFAULT_MEMORY,
            "--pids-limit",
            PIDS_LIMIT,
            "--cpus",
            CPUS,
            "--read-only",
            "--tmpfs",
            f"/tmp:size={TMPFS_SIZE}",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "65534:65534",
            image,
            *command,
        ]
        payload = code
        started = time.monotonic()
        timed_out = False
        try:
            process = subprocess.Popen(
                [self.docker_bin, *args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
            raise ExecUnavailableError(f"代码执行后端不可用: {exc}") from exc
        try:
            out, err = process.communicate(
                input=payload.encode("utf-8"), timeout=limit
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                self._docker(["kill", container_name], timeout=10.0)
            except Exception:  # noqa: BLE001
                pass
            try:
                out, err = process.communicate(timeout=5)
            except Exception:  # noqa: BLE001
                process.kill()
                out, err = b"", b""
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout, out_truncated = _decode(out or b"", self.max_bytes)
        stderr, err_truncated = _decode(err or b"", self.max_bytes)
        exit_code = process.returncode if process.returncode is not None else -1
        if timed_out:
            stderr = (stderr + f"\n执行超时（{limit}s），已终止容器").strip()
            exit_code = 124
        return ExecResult(
            language=resolved,
            backend=self.name,
            stdout=stdout,
            stderr=stderr,
            exit_code=int(exit_code),
            duration_ms=duration_ms,
            timed_out=timed_out,
            truncated=out_truncated or err_truncated,
        )
