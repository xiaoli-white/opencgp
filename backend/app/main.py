"""FastAPI 应用入口。

提供健康检查端点 ``/health``，并装配 Port/Adapter 容器。
启动方式（M0 单机）：:

    cd backend
    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings
from app.container import get_container

settings = get_settings()
container = get_container()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI 课程工作室 · 以对话为中心、以课程为活文档的创作工作台",
)


@app.get("/")
def root() -> dict:
    """根路径：返回导航提示。"""
    return {
        "app": settings.app_name,
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    """健康检查：报告应用状态与各 adapter 探活结果。

    adapter 探活失败不会导致 500，而是以 ``degraded`` 状态如实返回，
    便于编排系统（如 Docker Compose / K8s）做探针判断。
    """
    adapters: dict[str, Any] = {}
    for name in ("database", "storage", "llm", "vectorstore", "exporter"):
        try:
            obj = getattr(container, name)()
            ok = bool(obj.healthcheck())
        except Exception as exc:  # noqa: BLE001 - 探活需兜住一切异常
            adapters[name] = {"ok": False, "error": str(exc)}
        else:
            adapters[name] = {"ok": ok}

    all_ok = all(v["ok"] for v in adapters.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "app": settings.app_name,
        "env": settings.env,
        "adapters": adapters,
    }


class GenerateRequest(BaseModel):
    prompt: str


@app.post("/api/v1/generate")
async def generate(req: GenerateRequest) -> dict[str, str]:
    provider = container.llm()
    text = await provider.complete(req.prompt)
    return {"text": text}


@app.post("/api/v1/generate/stream")
async def generate_stream(req: GenerateRequest) -> StreamingResponse:
    provider = container.llm()

    async def event_stream():
        async for token in provider.stream_complete(req.prompt):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
