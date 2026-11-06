"""Remotion renderer adapter.

The adapter deliberately knows only the repository template contract:

    node <project>/render.mjs --out <tmp.mp4> --props <json-file>

Anything else (composition ids, assets, fonts) stays inside the template.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from app.services.errors import VideoRenderError, VideoUnavailableError

REPO_ROOT = Path(__file__).resolve().parents[4]
STDERR_TAIL = 1200


class RemotionRenderer:
    name = "remotion"

    def __init__(
        self,
        node_bin: str = "node",
        project: str = "tools/remotion",
        timeout: float = 300.0,
    ) -> None:
        self.node_bin = (node_bin or "node").strip()
        self.project = (project or "tools/remotion").strip()
        self.timeout = max(1.0, float(timeout or 300.0))

    def project_path(self) -> Path:
        candidate = Path(self.project).expanduser()
        if candidate.is_absolute():
            return candidate
        for base in (Path.cwd(), Path.cwd().parent, REPO_ROOT):
            resolved = (base / candidate).resolve()
            if resolved.is_dir():
                return resolved
        return (REPO_ROOT / candidate).resolve()

    def _resolved_node(self) -> str:
        node = self.node_bin
        if os.path.sep in node or node.startswith("."):
            path = Path(node).expanduser()
            return str(path) if path.is_file() else ""
        return shutil.which(node) or ""

    def check(self) -> tuple[bool, str]:
        node = self._resolved_node()
        if not node:
            return (
                False,
                f"video generation is unavailable: node binary not found ({self.node_bin!r}); "
                "set OPENCGP_VIDEO_NODE_BIN to a valid Node.js executable",
            )
        project = self.project_path()
        if not project.is_dir():
            return (
                False,
                f"video generation is unavailable: Remotion project not found at {project}; "
                "set OPENCGP_VIDEO_PROJECT or install tools/remotion",
            )
        render_script = project / "render.mjs"
        if not render_script.is_file():
            return (
                False,
                f"video generation is unavailable: render.mjs not found in {project}; "
                "the Remotion template is incomplete",
            )
        return True, ""

    async def render(
        self,
        props: dict[str, Any],
        out_path: str,
        on_progress: Callable[[float], None] | None = None,
    ) -> str:
        ok, reason = self.check()
        if not ok:
            raise VideoUnavailableError(reason)
        project = self.project_path()
        render_script = project / "render.mjs"
        node = self._resolved_node()
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)

        props_handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", prefix="opencgp-video-", delete=False, encoding="utf-8"
        )
        try:
            json.dump(props, props_handle, ensure_ascii=False)
            props_handle.flush()
            props_path = props_handle.name
        finally:
            props_handle.close()

        command = [
            node,
            str(render_script),
            "--out",
            str(target),
            "--props",
            props_path,
        ]
        if on_progress is not None:
            on_progress(0.15)
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(project),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.timeout
                )
            except asyncio.TimeoutError as exc:
                process.kill()
                await process.wait()
                raise VideoRenderError(
                    f"Remotion render timed out after {self.timeout:.0f}s"
                ) from exc
        except FileNotFoundError as exc:
            raise VideoUnavailableError(
                f"video generation is unavailable: cannot execute node ({node!r})"
            ) from exc
        finally:
            try:
                Path(props_path).unlink(missing_ok=True)
            except OSError:
                pass

        if process.returncode != 0:
            detail = (stderr or stdout or b"").decode("utf-8", errors="replace").strip()
            raise VideoRenderError(
                f"Remotion render failed (exit {process.returncode}): {detail[-STDERR_TAIL:]}"
            )
        if not target.is_file() or target.stat().st_size == 0:
            raise VideoRenderError("Remotion render finished without producing an mp4 file")
        if on_progress is not None:
            on_progress(0.85)
        return str(target)
