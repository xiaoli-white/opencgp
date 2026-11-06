"""FastAPI application entry point.

Exposes ``/health``, the generation endpoints and the RAG knowledge base,
and wires the port/adapter container.

Start locally::

    cd backend
    uvicorn app.main:app --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Any, Literal
from urllib.parse import quote

import psycopg
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

try:
    from psycopg_pool import PoolTimeout as _PsycopgPoolTimeout
except Exception:
    _PsycopgPoolTimeout = None

from app.config import get_settings
from app.container import get_container
from app.models.auth import (
    ALL_ACTIONS,
    CREATABLE_TENANT_KINDS,
    DEFAULT_TENANT_ID,
    USER_STATUSES,
    AuthContext,
)
from app.models.citation import Citation
from app.models.blueprint import SeriesBlueprint, GlossaryTerm
from app.models.series import Series, Unit
from app.models.export import (
    EXPORT_FORMATS,
    EXPORT_SOURCE_TYPES,
    EXPORT_THEMES,
    FORMAT_CONTENT_TYPES,
    FORMAT_EXTENSIONS,
    FORMAT_LABELS,
    FORMAT_MARKDOWN,
    SOURCE_SERIES,
    THEME_LIGHT,
)
from app.models.exec import LANGUAGES, ExecResult
from app.models.mode import GenerationMode
from app.models.thread import UnitThreadView
from app.models.piece import PieceProfile
from app.models.research import ResearchRun
from app.models.job import (
    JOB_KINDS,
    JOB_STATUSES,
    KIND_KB_EMBED_BACKFILL,
    KIND_PIECE_VIDEO,
    Job,
)
from app.models.factcheck import FactCheckReport
from app.services.jobs import JobContext
from app.services.retrieval_providers import retrieval_request_cache
from app.services.codecheck import CodeCheckService
from app.services.media import detect_image_type
from app.services.metrics import CONTENT_TYPE as METRICS_CONTENT_TYPE
from app.services.metrics import get_metrics
from app.services.textproc import line_diff
from app.services.validators import ValidatorRunner
from app.services.assets import DEFAULT_STYLE, AssetMaterializer
from app.services.errors import (
    ShareExpiredError,
    ShareNotFoundError,
    ShareRateLimitedError,
    ShareRevokedError,
    ExecLanguageError,
    ExecUnavailableError,
    ImageGenerationError,
    ImageGenerationUnavailableError,
    MediaAssetNotFoundError,
    MediaInvalidError,
    ExportFormatError,
    ExportSourceNotFoundError,
    ExportUnavailableError,
    AccountNotActiveError,
    AvatarInvalidError,
    AuthRequiredError,
    BlueprintNotFoundError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    MembershipNotFoundError,
    PermissionDeniedError,
    TenantNotFoundError,
    BlueprintParseError,
    EmptyLLMResponseError,
    UnitContentEmptyError,
    UnitNotFoundError,
    MessageNotFoundError,
    NoEvidenceError,
    QuotaExceededError,
    VersionConflictError,
    UnitLockedError,
    UnitLockLostError,
    LockTokenMismatchError,
    RoleNotFoundError,
    RoleInUseError,
    BuiltinRoleError,
    DefaultProviderError,
    ProviderDisabledError,
    ProviderInUseError,
    ProviderNotFoundError,
    ResearchNotFoundError,
    ResearchParseError,
    PieceNotFoundError,
    PieceSectionNotFoundError,
    JobNotFoundError,
    TenantInUseError,
    TenantKindError,
    TenantSystemError,
    UnsupportedJobKindError,
    JobNotTerminalError,
    UserDeleteForbiddenError,
    UserHasWorksError,
    CreationProfileNotFoundError,
    ProfileNotFoundError,
    BuiltinProfileError,
    ProfileInUseError,
    ProfileInvalidError,
    SourceNotFoundError,
    ThreadNotFoundError,
    ProviderCallError,
    QueueUnavailableError,
)

settings = get_settings()
container = get_container()
logger = logging.getLogger(__name__)


def _db_unavailable(exc: BaseException) -> bool:
    kinds: list[type[BaseException]] = [
        psycopg.OperationalError,
        psycopg.InterfaceError,
    ]
    if _PsycopgPoolTimeout is not None:
        kinds.append(_PsycopgPoolTimeout)
    if isinstance(exc, tuple(kinds)):
        return True
    if isinstance(exc, sqlite3.OperationalError):
        message = str(exc).lower()
        return "unable to open" in message or "database is locked" in message
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        container.auth_repository().ensure_schema()
    except Exception as exc:  # noqa: BLE001
        print(f"[auth] failed to initialise base tables: {exc!r}")
    try:
        container.profiles().ensure_builtin()
    except Exception as exc:  # noqa: BLE001
        print(f"[profiles] failed to seed built-in presets: {exc!r}")
    service = container.job_service()
    try:
        service.recover_stale()
    except Exception as exc:  # noqa: BLE001
        print(f"[jobs] failed to recover leftover jobs: {exc!r}")
    try:
        service.start()
    except Exception as exc:  # noqa: BLE001
        print(f"[jobs] failed to start the queue: {exc!r}")
    yield
    try:
        await service.aclose()
    except Exception as exc:  # noqa: BLE001
        print(f"[jobs] failed to shut down the queue: {exc!r}")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="OpenCGP · conversation-driven content generation where every piece stays a living document",
    lifespan=lifespan,
)

def _route_label(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return str(path) if path else "unmatched"


@app.middleware("http")
async def retrieval_cache_middleware(request: Request, call_next):
    with retrieval_request_cache():
        return await call_next(request)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001
        get_metrics().inc_request(request.method, _route_label(request), 500)
        raise
    elapsed = time.perf_counter() - started
    route = _route_label(request)
    get_metrics().inc_request(request.method, route, response.status_code)
    get_metrics().observe_duration(route, elapsed)
    return response


@app.exception_handler(ProviderCallError)
async def provider_call_error_handler(
    request: Request, exc: ProviderCallError
) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if _db_unavailable(exc):
        logger.error(
            "database unavailable on %s %s",
            request.method,
            request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=503,
            content={"detail": "database unavailable, please retry shortly"},
        )
    logger.error(
        "unhandled exception on %s %s",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)



class RegisterRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)
    display_name: str = ""


class LoginRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    kind: str = "personal"


class TenantRenameRequest(BaseModel):
    name: str = Field(min_length=1)


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class UserReviewRequest(BaseModel):
    reason: str = ""


class MemberAddRequest(BaseModel):
    email: str = Field(min_length=3)
    role: str = "viewer"


class MemberRoleRequest(BaseModel):
    role: str = Field(min_length=1)


def get_auth_context(
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> AuthContext:
    service = container.auth_service()
    if service.mode != "required":
        return service.local_context()
    token = ""
    if authorization:
        scheme, _, value = authorization.partition(" ")
        token = value.strip() if scheme.lower() == "bearer" else authorization.strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing access token")
    try:
        return service.resolve(token, x_tenant_id)
    except AuthRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AccountNotActiveError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except MembershipNotFoundError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _enforce(ctx: AuthContext, action: str) -> AuthContext:
    try:
        return container.auth_service().require(ctx, action)
    except AuthRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def require_read(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    return _enforce(ctx, "read")


def require_write(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
    return _enforce(ctx, "write")


def _tenant_of(ctx: AuthContext) -> str:
    if ctx is None or ctx.tenant is None:
        return DEFAULT_TENANT_ID
    return ctx.tenant.id or DEFAULT_TENANT_ID


def _is_privileged(ctx: AuthContext) -> bool:
    if not container.auth_service().can(ctx, "manage_members"):
        return False
    return (ctx.scope or "all") == "all"


def _charge(ctx: AuthContext, kind: str, units: int = 1, ref_id: str = "") -> None:
    try:
        container.quota_service().check_and_record(
            _tenant_of(ctx), ctx.user.id, kind, units, ref_id
        )
    except QuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


def _guard_lock(unit_id: str, ctx: AuthContext) -> None:
    try:
        container.lock_service().guard(unit_id, ctx.user.id)
    except UnitLockedError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"this unit is being edited by {exc.name}, coordinate or take over first",
        ) from exc


def _conflict(exc: VersionConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": "version conflict: the content was updated by someone else",
            "expected_version": exc.expected,
            "current_version": exc.current,
        },
    )


@app.get("/")
def root() -> dict:
    """Root path: return a navigation hint."""
    return {
        "app": settings.app_name,
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
    }


_PROBE_TTL_SECONDS = 60.0
_PROBE_WAIT_SECONDS = 0.10
_probe_cache: dict[str, dict[str, Any]] = {}
_probe_refreshing: set[str] = set()


def _probe_cached(key: str) -> dict[str, Any] | None:
    entry = _probe_cache.get(key)
    if not entry:
        return None
    return dict(entry.get("value") or {})


def _probe_is_fresh(key: str, now: float) -> bool:
    entry = _probe_cache.get(key)
    return bool(entry and now - float(entry.get("at") or 0.0) < _PROBE_TTL_SECONDS)


def _probe_store(key: str, value: dict[str, Any]) -> None:
    _probe_cache[key] = {"at": time.time(), "value": dict(value)}


async def _probe_refresh(key: str, factory) -> None:
    try:
        value = await factory()
        if not isinstance(value, dict):
            value = {"ok": bool(value)}
        _probe_store(key, value)
    except Exception as exc:  # noqa: BLE001
        _probe_store(key, {"ok": False, "error": str(exc)})
    finally:
        _probe_refreshing.discard(key)


async def _probe_with_cache(key: str, factory) -> dict[str, Any]:
    now = time.time()
    if _probe_is_fresh(key, now):
        value = _probe_cached(key) or {"ok": False}
        value["probe"] = "cache"
        return value
    if key in _probe_refreshing:
        value = _probe_cached(key)
        if value is not None:
            value["probe"] = "stale"
            return value
        return {"ok": False, "error": "probe in progress", "probe": "stale"}
    _probe_refreshing.add(key)
    try:
        value = await asyncio.wait_for(factory(), timeout=_PROBE_WAIT_SECONDS)
    except asyncio.TimeoutError:
        asyncio.create_task(_probe_refresh(key, factory))
        cached = _probe_cached(key)
        if cached is not None:
            cached["probe"] = "stale"
            return cached
        return {"ok": False, "error": "probe timeout", "probe": "stale"}
    except Exception as exc:  # noqa: BLE001
        _probe_refreshing.discard(key)
        value = {"ok": False, "error": str(exc)}
        _probe_store(key, value)
        value = dict(value)
        value["probe"] = "live"
        return value
    _probe_refreshing.discard(key)
    if not isinstance(value, dict):
        value = {"ok": bool(value)}
    _probe_store(key, value)
    value = dict(value)
    value["probe"] = "live"
    return value


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check: report the application state and every adapter probe.

    A failing adapter probe never causes a 500; it is reported as ``degraded`` so
    orchestrators (Docker Compose, Kubernetes) can use it as a probe.
    """
    adapters: dict[str, Any] = {}
    for name in ("database", "storage", "llm", "vectorstore", "exporter", "parser", "notifier"):
        try:
            obj = getattr(container, name)()
            ok = bool(obj.healthcheck())
        except Exception as exc:  # noqa: BLE001 - a probe must swallow every exception
            adapters[name] = {"ok": False, "error": str(exc)}
        else:
            adapters[name] = {"ok": ok}
    try:
        adapters["notifier"]["backend"] = (settings.notify.backend or "none").strip().lower()
        adapters["notifier"]["optional"] = True
    except Exception:
        pass
    try:
        adapters["database"]["backend"] = (settings.database.backend or "sqlite").strip().lower()
    except Exception:
        pass
    try:
        adapters["storage"]["backend"] = (settings.storage.backend or "local").strip().lower()
        adapters["storage"]["bucket"] = settings.storage.bucket
        error = getattr(container.storage(), "last_error", "")
        if error:
            adapters["storage"]["error"] = error
    except Exception:
        pass
    try:
        adapters["vectorstore"]["backend"] = (
            settings.vectorstore.backend or "simple"
        ).strip().lower()
        warning = getattr(container.vectorstore(), "last_warning", "")
        if warning:
            adapters["vectorstore"]["warning"] = warning
    except Exception:
        pass

    all_ok = all(
        v["ok"] for name, v in adapters.items() if not v.get("optional") or name == "database"
    )
    try:
        searcher = container.web_search()
        adapters["websearch"] = {
            "ok": bool(searcher.healthcheck()),
            "backend": getattr(searcher, "name", ""),
            "fetch": bool(getattr(searcher, "fetch_enabled", False)),
            "optional": True,
        }
    except Exception as exc:  # noqa: BLE001
        adapters["websearch"] = {"ok": False, "error": str(exc), "optional": True}
    try:
        imagegen = container.image_provider()
        adapters["imagegen"] = {
            "ok": bool(imagegen.healthcheck()),
            "backend": getattr(imagegen, "name", ""),
            "optional": True,
        }
    except Exception as exc:  # noqa: BLE001
        adapters["imagegen"] = {"ok": False, "error": str(exc), "optional": True}
    probe_jobs: list[tuple[str, Any]] = []
    embedding_backend = (settings.embedding.backend or "none").strip().lower()
    try:
        embedder = container.embedder()
        embedding_info: dict[str, Any] = {
            "ok": True if embedder is None else bool(embedder.healthcheck()),
            "backend": embedding_backend,
            "model": getattr(embedder, "model", "") or (settings.embedding.model if embedder is None else ""),
            "dim": int(getattr(embedder, "dim", 0) or 0),
            "optional": True,
        }
        if embedding_backend in ("openai", "openai_compat") and embedder is not None:
            key = "embedding:%s:%s:%s:%s" % (
                embedding_backend,
                getattr(embedder, "base_url", ""),
                getattr(embedder, "model", ""),
                getattr(embedder, "dim", 0),
            )

            async def _embedding_factory(adapter=embedder) -> dict[str, Any]:
                result = await adapter.probe()
                result["backend"] = embedding_backend
                result["model"] = getattr(adapter, "model", "")
                result["dim"] = int(result.get("dim") or 0)
                return result

            probe_jobs.append(("embedding", _probe_with_cache(key, _embedding_factory)))
        else:
            embedding_info["probe"] = "config"
        adapters["embedding"] = embedding_info
    except Exception as exc:  # noqa: BLE001
        adapters["embedding"] = {
            "ok": False,
            "error": str(exc),
            "backend": embedding_backend,
            "optional": True,
            "probe": "stale",
        }
    rerank_backend = (settings.rerank.backend or "none").strip().lower()
    try:
        reranker = container.reranker("")
        rerank_model = str(
            getattr(reranker, "model", "") or settings.rerank.model or ""
        )
        rerank_info: dict[str, Any] = {
            "ok": False,
            "backend": rerank_backend,
            "model": rerank_model,
            "optional": True,
            "probe": "stale",
        }
        remote_backends = {
            "cohere",
            "jina",
            "siliconflow",
            "zhipu",
            "tei",
            "generic",
            "http",
        }
        if rerank_backend in remote_backends:
            key = "rerank:%s:%s:%s" % (
                rerank_backend,
                getattr(reranker, "base_url", ""),
                rerank_model,
            )

            async def _rerank_factory(adapter=reranker) -> dict[str, Any]:
                result = await adapter.probe()
                result["backend"] = rerank_backend
                result["model"] = str(
                    getattr(adapter, "model", "") or rerank_model
                )
                return result

            probe_jobs.append(("rerank", _probe_with_cache(key, _rerank_factory)))
        else:
            rerank_info["ok"] = bool(reranker.healthcheck())
            rerank_info["probe"] = "config"
        adapters["rerank"] = rerank_info
    except Exception as exc:  # noqa: BLE001
        adapters["rerank"] = {
            "ok": False,
            "error": str(exc),
            "backend": rerank_backend,
            "optional": True,
            "probe": "stale",
        }
    if probe_jobs:
        try:
            probe_values = await asyncio.wait_for(
                asyncio.gather(
                    *(job for _, job in probe_jobs), return_exceptions=True
                ),
                timeout=0.25,
            )
        except asyncio.TimeoutError:
            probe_values = [None for _ in probe_jobs]
        for (name, _), value in zip(probe_jobs, probe_values):
            if isinstance(value, Exception):
                adapters[name] = {
                    "ok": False,
                    "error": str(value),
                    "backend": (
                        embedding_backend if name == "embedding" else rerank_backend
                    ),
                    "optional": True,
                    "probe": "stale",
                }
            elif isinstance(value, dict):
                merged = dict(adapters.get(name) or {})
                merged.update(value)
                merged.setdefault("probe", "live")
                merged["optional"] = True
                adapters[name] = merged
    queue_info: dict[str, Any] = {"backend": "unknown", "ok": False}
    jobs_info: dict[str, int] = {"queued": 0, "running": 0}
    try:
        queue = container.job_queue()
        queue_info = {
            "backend": getattr(queue, "name", "unknown"),
            "ok": bool(queue.healthcheck()) if hasattr(queue, "healthcheck") else True,
        }
        stats = queue.stats() if hasattr(queue, "stats") else {}
        queue_info["pending"] = int(stats.get("pending") or 0)
        queue_info["concurrency"] = int(stats.get("concurrency") or 0)
    except Exception as exc:  # noqa: BLE001
        queue_info = {"backend": "unknown", "ok": False, "error": str(exc)}
    try:
        counts = container.job_service().counts()
        jobs_info = {
            "queued": int(counts.get("queued") or 0),
            "running": int(counts.get("running") or 0),
        }
    except Exception as exc:  # noqa: BLE001
        jobs_info = {"queued": 0, "running": 0, "error": str(exc)}
    return {
        "status": "ok" if all_ok else "degraded",
        "app": settings.app_name,
        "env": settings.env,
        "adapters": adapters,
        "queue": queue_info,
        "jobs": jobs_info,
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


@app.post("/api/v1/kb/upload")
async def kb_upload(
    file: UploadFile = File(...),
    source_name: str | None = Form(default=None),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    data = await file.read()
    filename = file.filename or "upload.bin"
    _charge(ctx, "upload", 1, ref_id=filename)
    _charge(ctx, "storage", len(data), ref_id=filename)
    embedding = container.retrieval_providers().resolve_embedding(
        _tenant_of(ctx), ctx.user.id
    )
    try:
        result = await container.ingest().ingest_bytes(
            data,
            filename,
            source_name=source_name,
            tenant_id=_tenant_of(ctx),
            embedder=embedding.adapter,
            embedding_provider_id=embedding.provider_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    payload = result.model_dump()
    payload["object_key"] = container.ingest().last_object_key
    return payload


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    source_ids: list[str] | None = None


@app.post("/api/v1/kb/search")
async def kb_search(
    req: SearchRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    tenant_id = _tenant_of(ctx)
    user_id = ctx.user.id
    service = container.retrieval_providers()
    retrieval_ctx = service.resolve_context(tenant_id, user_id)
    embedding = retrieval_ctx.embedding
    rerank = retrieval_ctx.rerank
    weights = retrieval_ctx.weights
    store = container.vectorstore()
    rerank_enabled = rerank.enabled
    candidate_k = (
        min(50, max(req.top_k, int(weights.top_n)))
        if rerank_enabled
        else req.top_k
    )
    citations, search_meta = await retrieval_ctx.search(
        store,
        req.query,
        top_k=candidate_k,
        source_ids=req.source_ids,
        tenant_id=tenant_id,
    )
    warnings = list(search_meta.get("warnings") or [])
    if embedding.error and "embedding_provider_failed" not in warnings:
        warnings.append("embedding_provider_failed")
    if (
        embedding.adapter is not None
        and int(embedding.dim or 0) <= 0
        and "embedding_dim_unknown" not in warnings
    ):
        warnings.append("embedding_dim_unknown")
    stats = await store.embedding_status(
        tenant_id, embedding.model, embedding.dim, provider_id=embedding.provider_id
    )
    total = int(stats.get("chunks_total") or 0)
    embedded = int(stats.get("chunks_embedded") or 0)
    coverage = round(embedded / total, 6) if total > 0 else 0.0
    if embedding.adapter is not None and embedded <= 0:
        if "no_vectors_for_model" not in warnings:
            warnings.append("no_vectors_for_model")
    if rerank_enabled and citations:
        try:
            docs = [citation.text for citation in citations]
            scores = await rerank.adapter.rerank(req.query, docs, int(weights.top_n))
        except Exception as exc:  # noqa: BLE001
            print(f"[search] rerank failed, skipping reordering: {exc!r}")
            scores = []
            if "rerank_failed" not in warnings:
                warnings.append("rerank_failed")
        if len(scores) == len(citations):
            weight = min(1.0, max(0.0, float(weights.rerank)))
            for citation, score in zip(citations, scores):
                final_score = (
                    (1.0 - weight) * citation.score + weight * float(score)
                )
                citation.rerank_score = round(float(score), 6)
                citation.rerank_model = rerank.model or None
                citation.score = round(float(final_score), 6)
            citations.sort(key=lambda item: item.score, reverse=True)
    citations = citations[: req.top_k]
    retrieval = {
        "embedding": {
            "provider_id": embedding.provider_id,
            "model": embedding.model,
            "dim": embedding.dim,
            "backend": embedding.backend,
            "source": embedding.source,
            "coverage": coverage,
            "chunks_total": total,
            "chunks_embedded": embedded,
            "vector_rows": int(search_meta.get("vector_rows") or 0),
            "skipped_mismatch": int(search_meta.get("skipped_mismatch") or 0),
            "excluded_other_models": int(
                search_meta.get("excluded_other_models") or 0
            ),
            "mode": search_meta.get("mode") or "keyword",
        },
        "rerank": {
            "provider_id": rerank.provider_id,
            "model": rerank.model,
            "backend": rerank.backend,
            "source": rerank.source,
            "enabled": rerank_enabled,
        },
        "weights": {
            "vector": weights.vector,
            "rerank": weights.rerank,
            "top_n": weights.top_n,
        },
        "skipped_mismatch": int(search_meta.get("skipped_mismatch") or 0),
        "source": service.effective_settings(tenant_id, user_id).get("source", "env"),
        "sources": {
            "embedding": embedding.source,
            "rerank": rerank.source,
            "vector_weight": weights.sources.get("vector", "env"),
            "rerank_weight": weights.sources.get("rerank", "env"),
            "rerank_top_n": weights.sources.get("top_n", "env"),
        },
        "warnings": warnings,
    }
    return {
        "query": req.query,
        "top_k": req.top_k,
        "count": len(citations),
        "citations": [citation.model_dump() for citation in citations],
        "retrieval": retrieval,
        "warnings": warnings,
    }


class RetrievalProviderCreateRequest(BaseModel):
    kind: str = Field(min_length=1)
    name: str = Field(min_length=1)
    backend: str = Field(min_length=1)
    base_url: str = ""
    model: str = ""
    dim: int = 0
    api_key: str | None = None
    is_default: bool = False
    enabled: bool = True
    scope: str = "user"
    meta: dict[str, Any] = Field(default_factory=dict)


class RetrievalProviderPatchRequest(BaseModel):
    kind: str | None = None
    backend: str | None = None
    name: str | None = None
    base_url: str | None = None
    model: str | None = None
    dim: int | None = None
    api_key: str | None = None
    enabled: bool | None = None
    is_default: bool | None = None
    meta: dict[str, Any] | None = None


class RetrievalSettingsRequest(BaseModel):
    scope: str = "user"
    embedding_provider_id: str | None = None
    rerank_provider_id: str | None = None
    vector_weight: float | None = None
    rerank_weight: float | None = None
    rerank_top_n: int | None = None


def _can_manage_server(ctx: AuthContext) -> bool:
    try:
        return bool(container.auth_service().can(ctx, "manage_server"))
    except Exception:  # noqa: BLE001
        return False


@app.get("/api/v1/settings/retrieval/providers")
async def retrieval_providers_list(
    kind: str = Query(default=""),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    resolved_kind = (kind or "").strip().lower()
    if resolved_kind and resolved_kind not in ("embedding", "rerank"):
        raise HTTPException(status_code=400, detail="kind must be embedding or rerank")
    return container.retrieval_providers().list_payload(
        _tenant_of(ctx), ctx.user.id, resolved_kind
    )


@app.post("/api/v1/settings/retrieval/providers", status_code=201)
async def retrieval_providers_create(
    req: RetrievalProviderCreateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    service = container.retrieval_providers()
    try:
        record = service.create(
            tenant_id=_tenant_of(ctx),
            user_id=ctx.user.id,
            kind=req.kind,
            name=req.name,
            backend=req.backend,
            base_url=req.base_url,
            model=req.model,
            dim=req.dim,
            api_key=req.api_key or "",
            is_default=req.is_default,
            enabled=req.enabled,
            scope=req.scope,
            meta=req.meta,
            can_manage_server=_can_manage_server(ctx),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    dim_source = "configured"
    if record.kind == "embedding" and record.dim <= 0:
        probed = await service.probe_dim(record)
        if probed:
            record.dim = probed
            record.version = int(record.version or 1) + 1
            meta = dict(record.meta or {})
            meta.pop("needs_probe", None)
            meta["dim_source"] = "probe"
            record.meta = meta
            service.repository.save_provider(record)
            dim_source = "probe"
        else:
            record.enabled = False
            service.repository.save_provider(record)
            dim_source = "unknown"
    payload = service.payload(record)
    payload["dim_source"] = dim_source
    return payload


@app.patch("/api/v1/settings/retrieval/providers/{provider_id}")
async def retrieval_providers_patch(
    provider_id: str,
    req: RetrievalProviderPatchRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    service = container.retrieval_providers()
    changes = req.model_dump(exclude_unset=True)
    try:
        record = service.update(
            tenant_id=_tenant_of(ctx),
            user_id=ctx.user.id,
            provider_id=provider_id,
            changes=changes,
            can_manage_server=_can_manage_server(ctx),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    return service.payload(record)


@app.delete("/api/v1/settings/retrieval/providers/{provider_id}")
async def retrieval_providers_delete(
    provider_id: str,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    service = container.retrieval_providers()
    try:
        deleted = service.delete(
            _tenant_of(ctx),
            ctx.user.id,
            provider_id,
            can_manage_server=_can_manage_server(ctx),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"id": provider_id, "deleted": bool(deleted)}


@app.post("/api/v1/settings/retrieval/providers/{provider_id}/test")
async def retrieval_providers_test(
    provider_id: str,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    service = container.retrieval_providers()
    try:
        return await service.test_provider(
            _tenant_of(ctx), ctx.user.id, provider_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/settings/retrieval/settings")
async def retrieval_settings_get(
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    return container.retrieval_providers().effective_settings(
        _tenant_of(ctx), ctx.user.id
    )


@app.put("/api/v1/settings/retrieval/settings")
async def retrieval_settings_put(
    req: RetrievalSettingsRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    changes = req.model_dump(exclude_unset=True)
    changes.pop("scope", None)
    try:
        return container.retrieval_providers().update_settings(
            tenant_id=_tenant_of(ctx),
            user_id=ctx.user.id,
            scope=req.scope,
            changes=changes,
            can_manage_server=_can_manage_server(ctx),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/v1/settings/retrieval/settings")
async def retrieval_settings_delete(
    scope: str = Query(default="user"),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    try:
        return container.retrieval_providers().clear_settings(
            _tenant_of(ctx), ctx.user.id, scope, _can_manage_server(ctx)
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class EmbeddingBackfillRequest(BaseModel):
    source_id: str | None = None
    provider_id: str | None = None


def _embedding_identity() -> tuple[str, int]:
    cfg = settings.embedding
    embedder = container.embedder()
    model = str(getattr(embedder, "model", "") or cfg.model or "")
    dim = int(getattr(embedder, "dim", 0) or cfg.dim or 0)
    return model, dim


@app.post("/api/v1/kb/embeddings/backfill")
async def kb_embeddings_backfill(
    req: EmbeddingBackfillRequest | None = None,
    sync: bool = Query(default=False),
    ctx: AuthContext = Depends(get_auth_context),
) -> Any:
    _enforce(ctx, "write")
    cfg = settings.embedding
    store = container.vectorstore()
    tenant_id = _tenant_of(ctx)
    source_id = (req.source_id if req else None) or ""
    requested_provider = (req.provider_id if req else None) or ""
    embedding = container.retrieval_providers().resolve_embedding(
        tenant_id, ctx.user.id, requested_provider
    )
    if requested_provider and embedding.adapter is None:
        raise HTTPException(
            status_code=404, detail=embedding.error or "provider not found"
        )
    embedder = embedding.adapter
    model = embedding.model
    dim = embedding.dim
    provider_id = embedding.provider_id
    stats = await store.embedding_status(
        tenant_id, model, dim, provider_id=provider_id
    )
    stale = stats.get("stale") or {"chunks": 0, "bytes": 0}
    if not sync:
        job = container.job_service().submit(
            KIND_KB_EMBED_BACKFILL,
            {
                "source_id": source_id,
                "batch": max(1, int(cfg.batch)),
                "provider_id": provider_id,
            },
            JobContext(tenant_id=tenant_id, user_id=ctx.user.id),
        )
        return JSONResponse(
            status_code=201,
            content={
                "job_id": job.id,
                "queued": True,
                "provider_id": provider_id,
                "stale": stale,
            },
        )
    chunks = await store.list_chunks(tenant_id, source_id)
    if len(chunks) > 2000:
        raise HTTPException(
            status_code=429,
            detail="more than 2000 chunks; use the async backfill instead (drop sync=true)",
        )
    if embedder is None:
        return {
            "embedded": 0,
            "skipped": 0,
            "failed": 0,
            "provider_id": provider_id,
            "model": model,
            "dim": dim,
            "elapsed_ms": 0,
            "stale": stale,
        }
    from app.services.embedding_backfill import backfill_embeddings

    started = time.perf_counter()
    result = await backfill_embeddings(
        store=store,
        embedder=embedder,
        tenant_id=tenant_id,
        source_id=source_id,
        batch_size=max(1, int(cfg.batch)),
        provider_id=provider_id,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "embedded": int(result.get("embedded") or 0),
        "skipped": int(result.get("skipped") or 0),
        "failed": int(result.get("failed") or 0),
        "provider_id": provider_id,
        "model": model,
        "dim": dim,
        "elapsed_ms": elapsed_ms,
        "stale": stale,
    }


@app.get("/api/v1/kb/embeddings/status")
async def kb_embeddings_status(
    provider_id: str = Query(default=""),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    store = container.vectorstore()
    embedding = container.retrieval_providers().resolve_embedding(
        _tenant_of(ctx), ctx.user.id, (provider_id or "").strip()
    )
    if provider_id and embedding.adapter is None:
        raise HTTPException(
            status_code=404, detail=embedding.error or "provider not found"
        )
    model = embedding.model
    dim = embedding.dim
    target_provider = embedding.provider_id
    counts = await store.embedding_status(
        _tenant_of(ctx), model, dim, provider_id=target_provider
    )
    total = int(counts.get("chunks_total") or 0)
    embedded = int(counts.get("chunks_embedded") or 0)
    coverage = round(embedded / total, 6) if total > 0 else 0.0
    return {
        "provider_id": target_provider,
        "provider_name": (
            embedding.provider.name if embedding.provider is not None else ""
        ),
        "backend": embedding.backend,
        "current_backend": embedding.backend,
        "source": embedding.source,
        "model": model,
        "dim": dim,
        "chunks_total": total,
        "chunks_embedded": embedded,
        "coverage": coverage,
        "models": list(counts.get("models") or []),
        "stale": dict(counts.get("stale") or {"chunks": 0, "bytes": 0}),
        "note": (
            "stale counts vectors that do not match the current provider, model and dimension;"
            "coverage only counts vectors that match exactly."
        ),
    }


@app.post("/api/v1/kb/embeddings/purge")
async def kb_embeddings_purge(
    provider_id: str = Query(default=""),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    store = container.vectorstore()
    embedding = container.retrieval_providers().resolve_embedding(
        _tenant_of(ctx), ctx.user.id, (provider_id or "").strip()
    )
    if provider_id and embedding.adapter is None:
        raise HTTPException(
            status_code=404, detail=embedding.error or "provider not found"
        )
    return await store.purge_stale_embeddings(
        _tenant_of(ctx),
        embedding.model,
        embedding.dim,
        provider_id=embedding.provider_id,
    )


@app.get("/api/v1/kb/sources")
async def kb_list_sources(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    items = await container.ingest().list_sources(_tenant_of(ctx))
    return {"count": len(items), "sources": items}


class SourceRenameRequest(BaseModel):
    source_name: str = Field(min_length=1)


@app.patch("/api/v1/kb/sources/{source_id}")
async def kb_rename_source(
    source_id: str,
    req: SourceRenameRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    renamed = await container.ingest().rename_source(
        source_id, req.source_name.strip(), _tenant_of(ctx)
    )
    if not renamed:
        raise HTTPException(status_code=404, detail=f"source not found: {source_id}")
    return {"source_id": source_id, "source_name": req.source_name.strip()}


@app.delete("/api/v1/kb/sources/{source_id}")
async def kb_delete_source(
    source_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    removed = await container.ingest().delete_source(source_id, tenant_id=_tenant_of(ctx))
    return {"source_id": source_id, "deleted_chunks": removed}


class SeriesCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    subtitle: str = ""
    audience: str = ""
    difficulty: str = "intermediate"
    language: str = "zh"
    profile_id: str = ""


class UnitCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    order_index: int | None = Field(default=None, ge=1)
    learning_objectives: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    content: str = ""
    note: str = "create"


class UnitGenerateRequest(BaseModel):
    topic: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    note: str = ""
    source_ids: list[str] | None = None
    mode: GenerationMode = GenerationMode.strict
    expected_version: int | None = None


class UnitRevertRequest(BaseModel):
    version: int = Field(ge=1)
    note: str = ""
    expected_version: int | None = None


class UnitAskRequest(BaseModel):
    question: str = Field(min_length=1)
    selection: str | None = None


class UnitAmendRequest(BaseModel):
    instruction: str = Field(min_length=1)
    target: str | None = None
    mode: GenerationMode = GenerationMode.strict
    expected_version: int | None = None


class UnitDrilldownRequest(BaseModel):
    message_id: str | None = None
    question: str | None = None


class UnitFactCheckRequest(BaseModel):
    top_k: int | None = Field(default=None, ge=1, le=10)
    claims: list[str] | None = None


def _require_series(
    series_id: str, ctx: AuthContext | None = None, level: str = "read"
) -> Series:
    tenant_id = _tenant_of(ctx) if ctx is not None else None
    series = container.series_repository().get_series(series_id, tenant_id)
    if series is None:
        raise HTTPException(status_code=404, detail=f"series not found: {series_id}")
    if ctx is not None and not container.auth_service().can_access_series(ctx, series_id, level):
        raise HTTPException(status_code=404, detail=f"series not found: {series_id}")
    return series


def _version_summary(version: Any, extra: dict[str, Any], include_content: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": version.id,
        "version": version.version,
        "note": version.note,
        "mode": version.mode,
        "created_at": version.created_at,
        "content_length": len(version.content or ""),
        **extra,
    }
    if hasattr(version, "unit_id"):
        payload["unit_id"] = version.unit_id
    if hasattr(version, "piece_id"):
        payload["piece_id"] = version.piece_id
    if include_content:
        payload["content"] = version.content
    return payload


def _version_diff(
    owner_id: str, from_version: int, to_version: int, loader: Any
) -> dict[str, Any]:
    before = loader(int(from_version))
    after = loader(int(to_version))
    for value, label in ((before, from_version), (after, to_version)):
        if value is None:
            raise HTTPException(status_code=404, detail=f"version not found: {label}")
    result = line_diff(before.content, after.content)
    return {
        "owner_id": owner_id,
        "from": int(from_version),
        "to": int(to_version),
        "added_chars": result["added_chars"],
        "removed_chars": result["removed_chars"],
        "hunks": result["hunks"],
    }


def _require_unit(
    unit_id: str, ctx: AuthContext | None = None, level: str = "read"
) -> Unit:
    unit = container.series_repository().get_unit(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail=f"unit not found: {unit_id}")
    if ctx is not None:
        _require_series(unit.series_id, ctx, level)
    return unit


def _series_spec(series: Series | None) -> Any:
    try:
        return container.profiles().resolve_for_series(series)
    except Exception:
        return None


def _piece_spec(piece: Any) -> Any:
    try:
        return container.profiles().resolve_for_piece(piece)
    except Exception:
        return None


async def _validation_report(spec: Any, content: str, extra: dict[str, Any]) -> Any:
    if spec is None or not content:
        return None
    try:
        return await container.validators().run(spec, content, extra)
    except Exception:
        return None


@app.post("/api/v1/series", status_code=201)
def create_series(
    req: SeriesCreateRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    series = container.series_repository().create_series(
        title=req.title,
        subtitle=req.subtitle,
        audience=req.audience,
        difficulty=req.difficulty,
        language=req.language,
        tenant_id=_tenant_of(ctx),
        user_id=ctx.user.id,
        profile_id=req.profile_id,
    )
    return series.model_dump()


@app.get("/api/v1/series")
def list_series(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    series = container.series_repository().list_series(_tenant_of(ctx))
    visible = container.auth_service().visible_series_ids(ctx)
    if visible is not None:
        series = [series for series in series if series.id in visible]
    return {"count": len(series), "series": [series.model_dump() for series in series]}


@app.get("/api/v1/series/{series_id}")
def get_series(
    series_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    series = _require_series(series_id, ctx)
    units = container.series_repository().list_units(series_id)
    return {
        "series": series.model_dump(),
        "unit_count": len(units),
        "units": [unit.model_dump() for unit in units],
        "progress": container.blueprint().progress(series_id),
    }


@app.post("/api/v1/series/{series_id}/units", status_code=201)
def create_unit(
    series_id: str,
    req: UnitCreateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_series(series_id, ctx, "write")
    repository = container.series_repository()
    unit = repository.create_unit(
        series_id=series_id,
        title=req.title,
        order_index=req.order_index,
        learning_objectives=req.learning_objectives,
        prerequisites=req.prerequisites,
    )
    version = 0
    if req.content.strip():
        applied = repository.append_version(
            unit.id,
            content=req.content,
            citations=[],
            note=req.note,
            status="draft",
        )
        if applied is not None:
            unit, record = applied
            version = record.version
    return {"unit": unit.model_dump(), "version": version}


@app.get("/api/v1/series/{series_id}/units")
def list_units(
    series_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_series(series_id, ctx)
    units = container.series_repository().list_units(series_id)
    return {
        "series_id": series_id,
        "count": len(units),
        "units": [unit.model_dump() for unit in units],
    }


@app.get("/api/v1/units/{unit_id}")
def get_unit(
    unit_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    unit = _require_unit(unit_id, ctx)
    return unit.model_dump()


def _asset_materializer(spec: Any = None, *, auto_images: bool | None = None,
                        max_images: int | None = None, style: str | None = None):
    """Illustration pipeline used by every content generation entry point.

    Per-profile ``assets`` settings override the global defaults; explicit
    arguments win only when the profile does not define that field. Returns
    ``None`` when the image provider is not configured, in which case the
    generator simply strips any marker the model produced.
    """
    media = container.media_service()
    provider = media.provider()
    if provider is None or getattr(provider, "is_placeholder", False):
        return None
    profile_assets = getattr(spec, "assets", None) if spec is not None else None
    profile_auto = getattr(profile_assets, "auto_images", None)
    profile_max = getattr(profile_assets, "max_images", None)
    profile_style = (getattr(profile_assets, "style", "") or "").strip()
    resolved_auto = (
        auto_images
        if auto_images is not None
        else (
            profile_auto
            if profile_auto is not None
            else getattr(settings.generation, "assets_auto_images", True)
        )
    )
    resolved_max = (
        max_images
        if max_images is not None
        else (
            profile_max
            if profile_max is not None
            else getattr(settings.generation, "assets_max_images", 3)
        )
    )
    resolved_style = style if style is not None else (profile_style or DEFAULT_STYLE)
    return AssetMaterializer(
        media,
        enabled=bool(resolved_auto),
        max_images=int(resolved_max),
        style=resolved_style,
    )


@app.post("/api/v1/units/{unit_id}/generate")
async def generate_unit(
    unit_id: str,
    req: UnitGenerateRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    unit = _require_unit(unit_id, ctx, "write")
    _guard_lock(unit_id, ctx)
    payload = req or UnitGenerateRequest()
    _charge(ctx, "generate", 1, ref_id=unit_id)
    try:
        result = await container.generation().generate_unit(
            unit_id,
            topic=payload.topic,
            top_k=payload.top_k,
            note=payload.note,
            source_ids=payload.source_ids,
            mode=payload.mode.value,
            expected_version=payload.expected_version,
            tenant_id=_tenant_of(ctx),
            llm=container.llm_for(ctx.user.id),
            spec=_series_spec(container.series_repository().get_series(unit.series_id)),
            retrieval=container.retrieval_context(_tenant_of(ctx), ctx.user.id),
            ctx=ctx,
            assets=_asset_materializer(
                _series_spec(container.series_repository().get_series(unit.series_id))
            ),
        )
    except UnitNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unit not found: {unit_id}") from exc
    except VersionConflictError as exc:
        return _conflict(exc)
    return result.model_dump()


class UnitValidateRequest(BaseModel):
    profile_id: str = ""
    validators: list[str] | None = None


@app.post("/api/v1/units/{unit_id}/validate")
async def validate_unit(
    unit_id: str,
    req: UnitValidateRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    unit = _require_unit(unit_id, ctx)
    payload = req or UnitValidateRequest()
    series = container.series_repository().get_series(unit.series_id)
    spec = _series_spec(series)
    if payload.profile_id:
        resolved = container.profiles().resolve(payload.profile_id)
        if resolved is not None:
            spec = resolved
    if spec is None:
        raise HTTPException(status_code=404, detail="no usable creation profile found")
    if payload.validators:
        names = [item.strip().lower() for item in payload.validators if item and item.strip()]
        spec = spec.model_copy(
            update={"validation": spec.validation.model_copy(update={"validators": names})}
        )
    report = await container.validators().run(
        spec,
        unit.content or "",
        {
            "unit_id": unit.id,
            "series_id": unit.series_id,
            "title": unit.title,
            "setting_book": spec.assets.setting_book,
        },
    )
    return {
        "unit_id": unit_id,
        "profile_id": (series.profile_id if series else "") or "",
        "length": len(unit.content or ""),
        **report.model_dump(),
    }


@app.post("/api/v1/units/{unit_id}/factcheck")
async def factcheck_unit(
    unit_id: str,
    req: UnitFactCheckRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    unit = _require_unit(unit_id, ctx)
    payload = req or UnitFactCheckRequest()
    service = container.factcheck()
    explicit = [item.strip() for item in (payload.claims or []) if item and item.strip()]
    claims = explicit or service.extract_claims(unit.content or "")
    retrieval_ctx = container.retrieval_context(_tenant_of(ctx), ctx.user.id)
    results = await service.check(
        claims,
        top_k=payload.top_k,
        tenant_id=_tenant_of(ctx),
        llm=container.llm_for(ctx.user.id),
        retrieval=retrieval_ctx,
    )
    return FactCheckReport.build(
        results, unit_id, retrieval=retrieval_ctx.summary()
    ).model_dump()


@app.get("/api/v1/units/{unit_id}/versions/diff")
def diff_unit_versions(
    unit_id: str,
    from_version: int = Query(alias="from", ge=1),
    to_version: int = Query(alias="to", ge=1),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_unit(unit_id, ctx)
    repository = container.series_repository()
    return _version_diff(
        unit_id,
        from_version,
        to_version,
        lambda item: repository.get_version(unit_id, item),
    )


@app.get("/api/v1/units/{unit_id}/versions/{version}")
def get_unit_version(
    unit_id: str,
    version: int,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_unit(unit_id, ctx)
    record = container.series_repository().get_version(unit_id, version)
    if record is None:
        raise HTTPException(status_code=404, detail=f"version not found: {version}")
    return {"unit_id": unit_id, "version": record.model_dump()}


@app.get("/api/v1/units/{unit_id}/versions")
def list_unit_versions(
    unit_id: str,
    include_content: bool = Query(default=False),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    unit = _require_unit(unit_id, ctx)
    versions = container.series_repository().list_versions(unit_id)
    return {
        "unit_id": unit_id,
        "current_version": unit.current_version,
        "count": len(versions),
        "versions": [
            _version_summary(
                version,
                {
                    "citations": [citation.model_dump() for citation in version.citations],
                    "citation_count": len(version.citations),
                },
                include_content,
            )
            for version in versions
        ],
    }


@app.post("/api/v1/units/{unit_id}/revert")
def revert_unit(
    unit_id: str,
    req: UnitRevertRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    unit_now = _require_unit(unit_id, ctx, "write")
    _guard_lock(unit_id, ctx)
    if req.expected_version is not None and int(req.expected_version) != unit_now.current_version:
        return _conflict(
            VersionConflictError(int(req.expected_version), unit_now.current_version)
        )
    repository = container.series_repository()
    if repository.get_version(unit_id, req.version) is None:
        raise HTTPException(
            status_code=404, detail=f"version not found: {unit_id} v{req.version}"
        )
    applied = repository.revert_to_version(unit_id, req.version, note=req.note)
    if applied is None:
        raise HTTPException(status_code=404, detail=f"version not found: {unit_id} v{req.version}")
    unit, record = applied
    return {
        "unit": unit.model_dump(),
        "version": record.version,
        "reverted_from": req.version,
        "note": record.note,
    }


@app.post("/api/v1/units/{unit_id}/ask")
async def ask_unit(
    unit_id: str, req: UnitAskRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_unit(unit_id, ctx, "write")
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    _charge(ctx, "ask", 1, ref_id=unit_id)
    selection = (req.selection or "").strip() or None
    try:
        result = await container.conversation().ask(
            unit_id,
            question,
            selection=selection,
            llm=container.llm_for(ctx.user.id),
        )
    except UnitNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unit not found: {unit_id}") from exc
    except EmptyLLMResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result.model_dump()


@app.post("/api/v1/units/{unit_id}/amend")
async def amend_unit(
    unit_id: str,
    req: UnitAmendRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_unit(unit_id, ctx, "write")
    instruction = req.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction must not be empty")
    _guard_lock(unit_id, ctx)
    _charge(ctx, "amend", 1, ref_id=unit_id)
    try:
        result = await container.conversation().amend(
            unit_id,
            instruction,
            target=req.target,
            mode=req.mode.value,
            expected_version=req.expected_version,
            llm=container.llm_for(ctx.user.id),
        )
    except VersionConflictError as exc:
        return _conflict(exc)
    except UnitNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unit not found: {unit_id}") from exc
    except UnitContentEmptyError as exc:
        raise HTTPException(
            status_code=400, detail=f"this unit has no text yet, cannot patch it: {unit_id}"
        ) from exc
    except EmptyLLMResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result.model_dump()


@app.post("/api/v1/units/{unit_id}/drilldown")
async def drilldown_unit(
    unit_id: str,
    req: UnitDrilldownRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_unit(unit_id, ctx, "write")
    payload = req or UnitDrilldownRequest()
    try:
        result = await container.conversation().drilldown(
            unit_id,
            message_id=payload.message_id,
            question=payload.question,
            llm=container.llm_for(ctx.user.id),
        )
    except UnitNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unit not found: {unit_id}") from exc
    except MessageNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=(
                "no follow-up answer to keep; call ask first or pass a valid message_id: "
                f"{payload.message_id or payload.question or unit_id}"
            ),
        ) from exc
    return result.model_dump()


@app.get("/api/v1/units/{unit_id}/thread")
def get_unit_thread(
    unit_id: str,
    limit: int | None = Query(default=None, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_unit(unit_id, ctx)
    conversations = container.conversation_repository()
    thread = conversations.get_unit_thread(unit_id)
    if thread is None:
        empty = UnitThreadView(
            unit_id=unit_id, thread_id="", title="", message_count=0, messages=[]
        )
        return empty.model_dump()
    messages = conversations.list_messages(thread.id, limit=limit)
    view = UnitThreadView(
        unit_id=unit_id,
        thread_id=thread.id,
        title=thread.title,
        message_count=conversations.count_messages(thread.id),
        messages=messages,
    )
    payload = view.model_dump()
    payload["series_id"] = thread.series_id
    payload["returned_count"] = len(messages)
    payload["created_at"] = thread.created_at
    payload["updated_at"] = thread.updated_at
    return payload


@app.get("/api/v1/threads/{thread_id}")
def get_thread(
    thread_id: str,
    limit: int | None = Query(default=None, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    conversations = container.conversation_repository()
    thread = conversations.get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=f"conversation not found: {thread_id}")
    _require_series(thread.series_id, ctx)
    messages = conversations.list_messages(thread.id, limit=limit)
    return {
        "thread": thread.model_dump(),
        "message_count": conversations.count_messages(thread.id),
        "returned_count": len(messages),
        "messages": [message.model_dump() for message in messages],
    }


@app.get("/api/v1/threads")
def list_threads(
    limit: int = Query(default=100, ge=1, le=500),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    series = container.series_repository().list_series(_tenant_of(ctx))
    visible = container.auth_service().visible_series_ids(ctx)
    series_ids = [series.id for series in series]
    if visible is not None:
        allowed = set(visible)
        series_ids = [series_id for series_id in series_ids if series_id in allowed]
    conversations = container.conversation_repository()
    threads = conversations.list_threads(series_ids, limit)
    payload = []
    for thread in threads:
        item = thread.model_dump()
        item["message_count"] = conversations.count_messages(thread.id)
        payload.append(item)
    return {"count": len(payload), "threads": payload}


class ThreadRenameRequest(BaseModel):
    title: str = Field(min_length=1)


def _require_thread(thread_id: str, ctx: AuthContext, level: str = "read"):
    thread = container.conversation_repository().get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=f"conversation not found: {thread_id}")
    if thread.series_id:
        _require_series(thread.series_id, ctx, level)
    return thread


@app.patch("/api/v1/threads/{thread_id}")
def rename_thread(
    thread_id: str,
    req: ThreadRenameRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_thread(thread_id, ctx, "write")
    updated = container.conversation_repository().update_thread_title(
        thread_id, req.title
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"conversation not found: {thread_id}")
    return {"thread": updated.model_dump()}


@app.delete("/api/v1/threads/{thread_id}")
def delete_thread(
    thread_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_thread(thread_id, ctx, "write")
    removed = container.conversation_repository().delete_thread(thread_id)
    return {"ok": True, "thread_id": thread_id, "deleted_messages": removed}


class BlueprintGenerateRequest(BaseModel):
    mode: GenerationMode = GenerationMode.strict
    top_k: int | None = Field(default=None, ge=1, le=20)
    source_ids: list[str] | None = None
    focus: str = ""


class BlueprintSaveRequest(BaseModel):
    blueprint: SeriesBlueprint
    expected_version: int | None = None


class GlossaryUpdateRequest(BaseModel):
    terms: list[GlossaryTerm] = Field(default_factory=list)


class UnitReviewRequest(BaseModel):
    action: Literal["approve", "request_revision"]
    note: str = ""


def _glossary_payload(series_id: str, blueprint: SeriesBlueprint | None) -> dict[str, Any]:
    terms = blueprint.glossary if blueprint else []
    return {
        "series_id": series_id,
        "count": len(terms),
        "glossary": [term.model_dump() for term in terms],
    }


@app.get("/api/v1/series/{series_id}/blueprint")
def get_series_blueprint(
    series_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_series(series_id, ctx)
    blueprint = container.blueprint().get_blueprint(series_id)
    return {
        "exists": blueprint is not None,
        "blueprint": blueprint.model_dump() if blueprint else None,
    }


@app.post("/api/v1/series/{series_id}/blueprint/generate")
async def generate_series_blueprint(
    series_id: str,
    req: BlueprintGenerateRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    payload = req or BlueprintGenerateRequest()
    series = _require_series(series_id, ctx, "write")
    _charge(ctx, "blueprint", 1, ref_id=series_id)
    try:
        blueprint = await container.blueprint().generate(
            series_id,
            mode=payload.mode.value,
            top_k=payload.top_k,
            source_ids=payload.source_ids,
            focus=payload.focus,
            tenant_id=_tenant_of(ctx),
            llm=container.llm_for(ctx.user.id),
            spec=_series_spec(series),
            retrieval=container.retrieval_context(_tenant_of(ctx), ctx.user.id),
        )
    except NoEvidenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BlueprintParseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except BlueprintNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return blueprint.model_dump()


@app.put("/api/v1/series/{series_id}/blueprint")
def save_series_blueprint(
    series_id: str,
    req: BlueprintSaveRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_series(series_id, ctx, "write")
    try:
        saved = container.blueprint().save_blueprint(
            series_id, req.blueprint, expected_version=req.expected_version
        )
    except BlueprintNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VersionConflictError as exc:
        return _conflict(exc)
    return saved.model_dump()


@app.post("/api/v1/series/{series_id}/blueprint/apply")
def apply_series_blueprint(
    series_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_series(series_id, ctx, "write")
    try:
        blueprint, created = container.blueprint().apply(series_id)
    except BlueprintNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "created_units": [unit.model_dump() for unit in created],
        "blueprint": blueprint.model_dump(),
        "created_count": len(created),
    }


@app.get("/api/v1/series/{series_id}/glossary")
def get_series_glossary(
    series_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_series(series_id, ctx)
    blueprint = container.blueprint().get_blueprint(series_id)
    return _glossary_payload(series_id, blueprint)


@app.put("/api/v1/series/{series_id}/glossary")
def update_series_glossary(
    series_id: str,
    req: GlossaryUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_series(series_id, ctx, "write")
    try:
        blueprint = container.blueprint().set_glossary(series_id, req.terms)
    except BlueprintNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _glossary_payload(series_id, blueprint)


@app.get("/api/v1/series/{series_id}/progress")
def get_series_progress(
    series_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_series(series_id, ctx)
    return container.blueprint().progress(series_id)


@app.post("/api/v1/units/{unit_id}/review")
def review_unit(
    unit_id: str,
    req: UnitReviewRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "review")
    _require_unit(unit_id, ctx)
    _guard_lock(unit_id, ctx)
    try:
        unit, review = container.blueprint().review_unit(
            unit_id, req.action, note=req.note
        )
    except UnitNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unit not found: {unit_id}") from exc
    except UnitContentEmptyError as exc:
        raise HTTPException(
            status_code=400, detail=f"this unit has no text yet, cannot approve it: {unit_id}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    progress = container.blueprint().progress(unit.series_id)
    return {
        "unit": unit.model_dump(),
        "review": review.model_dump(),
        "series_progress": progress,
    }


@app.get("/api/v1/units/{unit_id}/reviews")
def list_unit_reviews(
    unit_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_unit(unit_id, ctx)
    reviews = container.blueprint().list_reviews(unit_id)
    return {
        "unit_id": unit_id,
        "count": len(reviews),
        "reviews": [review.model_dump() for review in reviews],
    }


def _auth_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AccountNotActiveError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, EmailAlreadyRegisteredError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, InvalidCredentialsError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, AuthRequiredError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, PermissionDeniedError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, MembershipNotFoundError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, TenantSystemError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, TenantInUseError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, TenantNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@app.post("/api/v1/auth/register", status_code=201)
def auth_register(req: RegisterRequest) -> dict[str, Any]:
    service = container.auth_service()
    try:
        user, token = service.register(req.email, req.password, req.display_name)
    except AccountNotActiveError as exc:
        raise _auth_error(exc) from exc
    except (EmailAlreadyRegisteredError, ValueError) as exc:
        raise _auth_error(exc) from exc
    if not token:
        container.notifications().registration_pending(user)
        container.notifications().registration_received(user)
        return {
            "pending": True,
            "message": "registration submitted, waiting for admin approval",
            "user": service.user_payload(user, service.role_in_system(user.id)),
        }
    return {
        "pending": False,
        "token": token,
        "user": service.user_payload(user, service.role_in_system(user.id)),
        "tenants": service.tenants_payload(user),
    }


@app.post("/api/v1/auth/login")
def auth_login(req: LoginRequest) -> dict[str, Any]:
    service = container.auth_service()
    try:
        user, token = service.login(req.email, req.password)
    except (AccountNotActiveError, InvalidCredentialsError) as exc:
        raise _auth_error(exc) from exc
    return {
        "token": token,
        "user": service.user_payload(user, service.role_in_system(user.id)),
        "tenants": service.tenants_payload(user),
    }


@app.get("/api/v1/auth/me")
def auth_me(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    service = container.auth_service()
    return {
        "user": service.user_payload(ctx.user, ctx.role_key or ctx.role),
        "tenant": service.tenant_payload(ctx.tenant),
        "role": ctx.role_key or ctx.role,
        "role_key": ctx.role_key or ctx.role,
        "role_name": ctx.role_name,
        "actions": sorted(ctx.actions),
        "can": {action: service.can(ctx, action) for action in ALL_ACTIONS},
        "scope": ctx.scope,
        "avatar_url": ctx.user.avatar_url(),
        "tenants": service.tenants_payload(ctx.user),
        "auth_mode": service.mode,
        "require_approval": service.require_approval,
    }


@app.patch("/api/v1/auth/me")
def auth_update_me(
    req: ProfileUpdateRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    service = container.auth_service()
    try:
        user = service.update_profile(
            ctx.user.id, display_name=req.display_name, email=req.email
        )
    except (EmailAlreadyRegisteredError, InvalidCredentialsError) as exc:
        raise _auth_error(exc) from exc
    except (AuthRequiredError, ValueError) as exc:
        raise _auth_error(exc) from exc
    return {
        "user": service.user_payload(user, ctx.role_key or ctx.role),
        "tenants": service.tenants_payload(user),
    }


@app.post("/api/v1/auth/password")
def auth_change_password(
    req: PasswordChangeRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    service = container.auth_service()
    try:
        service.change_password(ctx.user.id, req.current_password, req.new_password)
    except (InvalidCredentialsError, ValueError) as exc:
        raise _auth_error(exc) from exc
    return {"ok": True}


def _avatar_extension(filename: str, content_type: str) -> str:
    allowed = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
    suffix = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if suffix in allowed:
        return suffix
    mapping = {value: key for key, value in allowed.items()}
    guess = mapping.get((content_type or "").split(";")[0].strip().lower(), "")
    if not guess:
        raise AvatarInvalidError("avatar must be png, jpg, jpeg or webp")
    return guess


AVATAR_MAX_BYTES = 2 * 1024 * 1024


@app.put("/api/v1/auth/avatar")
async def auth_upload_avatar(
    file: UploadFile = File(...), ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="avatar file is empty")
    if len(data) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=400, detail="avatar must not exceed 2MB")
    try:
        ext = _avatar_extension(file.filename or "", file.content_type or "")
    except AvatarInvalidError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    key = f"avatars/{ctx.user.id}.{ext}"
    try:
        container.storage().put(key, data, content_type=(file.content_type or ""))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"failed to store the avatar: {exc}") from exc
    service = container.auth_service()
    try:
        service.set_avatar_key(ctx.user.id, key)
    except AuthRequiredError as exc:
        raise _auth_error(exc) from exc
    return {"ok": True, "avatar_url": f"/api/v1/users/{ctx.user.id}/avatar"}


AVATAR_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


@app.get("/api/v1/users/{user_id}/avatar")
def get_user_avatar(user_id: str) -> Any:
    service = container.auth_service()
    user = service.get_user(user_id)
    if user is None or not user.avatar_key:
        raise HTTPException(status_code=404, detail="avatar not found")
    try:
        data = container.storage().get(user.avatar_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="avatar not found") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=f"failed to read the avatar: {exc}") from exc
    ext = user.avatar_key.rsplit(".", 1)[-1].lower()
    return StreamingResponse(
        iter([data]),
        media_type=AVATAR_CONTENT_TYPES.get(ext, "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=300"},
    )


def _admin_user_payload(user: Any) -> dict[str, Any]:
    service = container.auth_service()
    return service.user_payload(user, service.role_in_system(user.id))


@app.get("/api/v1/admin/users")
def admin_list_users(
    status: str = Query(default=""),
    q: str = Query(default=""),
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "manage_server")
    wanted = (status or "").strip().lower()
    if wanted and wanted not in USER_STATUSES:
        raise HTTPException(status_code=400, detail=f"unknown status: {wanted}")
    users = container.auth_service().list_users(
        wanted, limit, q, include_deleted=include_deleted
    )
    payload = [_admin_user_payload(user) for user in users]
    return {"count": len(payload), "users": payload}


@app.post("/api/v1/admin/users/{user_id}/approve")
def admin_approve_user(
    user_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "manage_server")
    service = container.auth_service()
    try:
        user = service.approve_user(user_id)
    except AuthRequiredError as exc:
        raise _auth_error(exc) from exc
    membership = service.ensure_system_membership(user.id)
    container.notifications().registration_approved(user)
    return {
        "user": _admin_user_payload(user),
        "status": user.status,
        "system_membership": membership.model_dump() if membership else None,
    }


@app.post("/api/v1/admin/users/{user_id}/reject")
def admin_reject_user(
    user_id: str,
    req: UserReviewRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "manage_server")
    service = container.auth_service()
    try:
        user = service.reject_user(user_id)
    except AuthRequiredError as exc:
        raise _auth_error(exc) from exc
    reason = req.reason if req is not None else ""
    container.notifications().registration_rejected(user, reason)
    return {
        "user": _admin_user_payload(user),
        "status": user.status,
        "reason": reason,
    }


class AdminUserUpdateRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    status: str | None = None
    role: str | None = None


class PasswordResetRequest(BaseModel):
    new_password: str = Field(min_length=1)


@app.patch("/api/v1/admin/users/{user_id}")
def admin_update_user(
    user_id: str,
    req: AdminUserUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "manage_server")
    try:
        user = container.account_admin().update_user(
            user_id,
            display_name=req.display_name,
            email=req.email,
            status=req.status,
            role=req.role,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AuthRequiredError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": _admin_user_payload(user)}


class AdminUserDeleteRequest(BaseModel):
    transfer_to_user_id: str | None = None
    force: bool = False


@app.delete("/api/v1/admin/users/{user_id}")
def admin_delete_user(
    user_id: str,
    req: AdminUserDeleteRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "manage_server")
    payload = req or AdminUserDeleteRequest()
    try:
        result = container.account_admin().delete_user(
            ctx.user.id,
            user_id,
            transfer_to_user_id=payload.transfer_to_user_id or "",
            force=bool(payload.force),
        )
    except UserHasWorksError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UserDeleteForbiddenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AuthRequiredError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, **result}


@app.post("/api/v1/admin/users/{user_id}/restore")
def admin_restore_user(
    user_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "manage_server")
    try:
        result = container.account_admin().restore_user(user_id)
    except AuthRequiredError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {**result, "user": _admin_user_payload(result["user"])}


@app.post("/api/v1/admin/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: str,
    req: PasswordResetRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "manage_server")
    try:
        container.account_admin().reset_password(user_id, req.new_password)
        reset_user = container.auth_repository().get_user(user_id)
        if reset_user is not None:
            container.notifications().password_reset(reset_user, req.new_password)
    except AuthRequiredError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/v1/auth/logout")
def auth_logout() -> dict[str, Any]:
    return {"ok": True}


@app.get("/api/v1/tenants")
def list_tenants(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    tenants = container.auth_service().list_tenants(ctx.user)
    return {"count": len(tenants), "tenants": tenants}


@app.post("/api/v1/tenants", status_code=201)
def create_tenant(
    req: TenantCreateRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    service = container.auth_service()
    try:
        tenant, role = service.create_tenant(ctx.user, req.name, req.kind)
    except (ValueError, TenantKindError) as exc:
        raise _auth_error(exc) from exc
    return {"tenant": service.tenant_payload(tenant), "role": role}


@app.patch("/api/v1/tenants/{tenant_id}")
def rename_tenant(
    tenant_id: str,
    req: TenantRenameRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    service = container.auth_service()
    try:
        if service.mode == "required":
            scoped = service.context_for_tenant(ctx.user, tenant_id)
            if "owner" not in (scoped.role_key, scoped.role):
                raise PermissionDeniedError("only the space owner can change this space")
        tenant = service.rename_tenant(tenant_id, req.name)
    except (PermissionDeniedError, MembershipNotFoundError, TenantNotFoundError) as exc:
        raise _auth_error(exc) from exc
    except ValueError as exc:
        raise _auth_error(exc) from exc
    return service.tenant_payload(tenant)


@app.delete("/api/v1/tenants/{tenant_id}")
def delete_tenant(
    tenant_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    service = container.auth_service()
    try:
        target = service.get_tenant(tenant_id)
        if target is None:
            raise TenantNotFoundError("space not found")
        if target.kind == "system" or target.id == DEFAULT_TENANT_ID:
            raise TenantSystemError("the system space cannot be deleted")
        if service.mode == "required":
            scoped = service.context_for_tenant(ctx.user, tenant_id)
            if "owner" not in (scoped.role_key, scoped.role):
                raise PermissionDeniedError("only the space owner can delete this space")
        series = container.series_repository().list_series(tenant_id)
        if series:
            raise TenantInUseError("this space still holds series and cannot be deleted")
        service.delete_tenant(tenant_id)
    except (
        PermissionDeniedError,
        MembershipNotFoundError,
        TenantNotFoundError,
        TenantSystemError,
        TenantInUseError,
    ) as exc:
        raise _auth_error(exc) from exc
    return {"ok": True}


class TenantTransferRequest(BaseModel):
    user_id: str = Field(min_length=1)


@app.post("/api/v1/tenants/{tenant_id}/transfer")
def transfer_tenant(
    tenant_id: str,
    req: TenantTransferRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    service = container.auth_service()
    try:
        tenant = service.transfer_tenant(tenant_id, ctx.user.id, req.user_id)
    except (
        PermissionDeniedError,
        MembershipNotFoundError,
        TenantNotFoundError,
        TenantSystemError,
        ValueError,
    ) as exc:
        raise _auth_error(exc) from exc
    members = service.list_members(tenant_id)
    return {
        "ok": True,
        "tenant": service.tenant_payload(tenant),
        "owner_user_id": tenant.owner_user_id,
        "members": [member.model_dump() for member in members],
    }


def _require_tenant_action(ctx: AuthContext, tenant_id: str, action: str) -> str:
    service = container.auth_service()
    if service.mode != "required":
        return ctx.role_key or ctx.role
    try:
        scoped = service.context_for_tenant(ctx.user, tenant_id)
        service.require(scoped, action)
    except (MembershipNotFoundError, PermissionDeniedError, TenantNotFoundError) as exc:
        raise _auth_error(exc) from exc
    return scoped.role_key


@app.get("/api/v1/tenants/{tenant_id}/members")
def list_tenant_members(
    tenant_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _require_tenant_action(ctx, tenant_id, "read")
    try:
        members = container.auth_service().list_members(tenant_id)
    except TenantNotFoundError as exc:
        raise _auth_error(exc) from exc
    return {"count": len(members), "members": [member.model_dump() for member in members]}


@app.post("/api/v1/tenants/{tenant_id}/members", status_code=201)
def add_tenant_member(
    tenant_id: str,
    req: MemberAddRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _require_tenant_action(ctx, tenant_id, "manage_members")
    try:
        member = container.auth_service().add_member(tenant_id, req.email, req.role)
    except (MembershipNotFoundError, PermissionDeniedError, TenantNotFoundError, ValueError) as exc:
        raise _auth_error(exc) from exc
    return member.model_dump()


@app.patch("/api/v1/tenants/{tenant_id}/members/{user_id}")
def update_tenant_member(
    tenant_id: str,
    user_id: str,
    req: MemberRoleRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _require_tenant_action(ctx, tenant_id, "manage_members")
    try:
        member = container.auth_service().update_member_role(tenant_id, user_id, req.role)
    except (MembershipNotFoundError, PermissionDeniedError, TenantNotFoundError, ValueError) as exc:
        raise _auth_error(exc) from exc
    return member.model_dump()


@app.delete("/api/v1/tenants/{tenant_id}/members/{user_id}")
def remove_tenant_member(
    tenant_id: str, user_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _require_tenant_action(ctx, tenant_id, "manage_members")
    try:
        container.auth_service().remove_member(tenant_id, user_id)
    except (MembershipNotFoundError, PermissionDeniedError, TenantNotFoundError) as exc:
        raise _auth_error(exc) from exc
    return {"ok": True}


class UnitLockRequest(BaseModel):
    force: bool = False


class UnitHeartbeatRequest(BaseModel):
    token: str = Field(min_length=1)


class QuotaUpdateRequest(BaseModel):
    monthly_generations: int = Field(ge=-1)
    monthly_uploads: int = Field(ge=-1)
    storage_bytes: int = Field(ge=-1)


class ProviderSettingsRequest(BaseModel):
    provider_id: str | None = None
    backend: str = ""
    base_url: str = ""
    model: str = ""
    api_key: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=0, le=200000)
    extra_body: dict[str, Any] | None = None
    extra_headers: dict[str, str] | None = None
    disable_reasoning: bool | None = None


class ProviderCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    kind: Literal["openai_compat", "dummy"] = "openai_compat"
    base_url: str = ""
    api_key: str | None = None
    models: list[str] = Field(default_factory=list)
    enabled: bool = True
    is_default: bool = False


class ProviderUpdateRequest(BaseModel):
    name: str | None = None
    kind: Literal["openai_compat", "dummy"] | None = None
    base_url: str | None = None
    api_key: str | None = None
    models: list[str] | None = None
    enabled: bool | None = None
    is_default: bool | None = None


class ProviderTestRequest(BaseModel):
    model: str = ""


class UserProviderCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    kind: Literal["openai_compat", "dummy"] = "openai_compat"
    base_url: str = ""
    api_key: str | None = None
    models: list[str] = Field(default_factory=list)
    enabled: bool = True
    is_default: bool = False


class UserProviderUpdateRequest(BaseModel):
    name: str | None = None
    kind: Literal["openai_compat", "dummy"] | None = None
    base_url: str | None = None
    api_key: str | None = None
    models: list[str] | None = None
    enabled: bool | None = None
    is_default: bool | None = None


def _quota_payload(tenant_id: str) -> dict[str, Any]:
    service = container.quota_service()
    usage = service.usage(tenant_id)
    return {
        "tenant_id": tenant_id,
        "period": usage.period,
        "limits": service.limits(tenant_id).model_dump(),
        "usage": usage.model_dump(),
        "remaining": service.remaining(tenant_id),
        "unlimited": service.unlimited(tenant_id),
    }


@app.get("/api/v1/quotas/history")
def get_quota_history(
    days: int = Query(default=30, ge=1, le=90),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    tenant_id = _tenant_of(ctx)
    payload = container.quota_service().history(tenant_id, days)
    return {"tenant_id": tenant_id, **payload}


@app.get("/api/v1/quotas")
def get_quota(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    return _quota_payload(_tenant_of(ctx))


@app.put("/api/v1/quotas")
def update_quota(
    req: QuotaUpdateRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    ctx = _enforce(ctx, "manage_quota")
    tenant_id = _tenant_of(ctx)
    container.quota_service().set_limits(
        tenant_id,
        req.monthly_generations,
        req.monthly_uploads,
        req.storage_bytes,
    )
    return _quota_payload(tenant_id)


@app.get("/api/v1/units/{unit_id}/lock")
def get_unit_lock(
    unit_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_unit(unit_id, ctx)
    lock = container.lock_service().get(unit_id)
    return {"lock": lock.model_dump() if lock else None}


@app.post("/api/v1/units/{unit_id}/lock")
def acquire_unit_lock(
    unit_id: str,
    req: UnitLockRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> Any:
    _enforce(ctx, "write")
    _require_unit(unit_id, ctx, "write")
    payload = req or UnitLockRequest()
    if payload.force and not _is_privileged(ctx):
        raise HTTPException(status_code=403, detail="only an admin or the owner can force-take the edit lock")
    try:
        lock = container.lock_service().acquire(
            unit_id,
            _tenant_of(ctx),
            ctx.user.id,
            ctx.user.display_name or ctx.user.email,
            force=payload.force,
        )
    except UnitLockedError as exc:
        current = exc.lock
        return JSONResponse(
            status_code=409,
            content={
                "detail": f"this unit is being edited by {exc.name}",
                "lock": current.model_dump() if hasattr(current, "model_dump") else None,
            },
        )
    return {"acquired": True, "lock": lock.model_dump()}


@app.post("/api/v1/units/{unit_id}/lock/heartbeat")
def heartbeat_unit_lock(
    unit_id: str,
    req: UnitHeartbeatRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_unit(unit_id, ctx, "write")
    try:
        lock = container.lock_service().heartbeat(unit_id, req.token)
    except UnitLockLostError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"lock": lock.model_dump()}


@app.delete("/api/v1/units/{unit_id}/lock")
def release_unit_lock(
    unit_id: str,
    token: str = Query(default=""),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_unit(unit_id, ctx, "write")
    try:
        container.lock_service().release(unit_id, token)
    except LockTokenMismatchError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": True}


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    actions: list[str] = Field(default_factory=list)
    scope: Literal["all", "assigned"] = "all"


class RoleUpdateRequest(BaseModel):
    name: str | None = None
    actions: list[str] | None = None
    scope: Literal["all", "assigned"] | None = None


class GrantItem(BaseModel):
    user_id: str = Field(min_length=1)
    level: Literal["read", "write"] = "read"


class GrantReplaceRequest(BaseModel):
    grants: list[GrantItem] = Field(default_factory=list)


def _role_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RoleNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, RoleInUseError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, BuiltinRoleError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, TenantNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _role_payload(role) -> dict[str, Any]:
    return {
        "id": role.id,
        "key": role.key,
        "name": role.name or role.key,
        "actions": list(role.actions),
        "scope": role.scope,
        "builtin": role.builtin,
    }


def _grants_payload(series_id: str, grants) -> dict[str, Any]:
    return {
        "series_id": series_id,
        "count": len(grants),
        "grants": [
            {
                "user_id": grant.user_id,
                "user_email": grant.user_email,
                "user_display_name": grant.user_display_name,
                "level": grant.level,
            }
            for grant in grants
        ],
    }


@app.get("/api/v1/roles")
def list_roles(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    try:
        roles = container.auth_service().list_roles(_tenant_of(ctx))
    except TenantNotFoundError as exc:
        raise _role_error(exc) from exc
    return {"count": len(roles), "roles": roles}


@app.post("/api/v1/roles", status_code=201)
def create_role(
    req: RoleCreateRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "manage_members")
    try:
        role = container.auth_service().create_role(
            _tenant_of(ctx), req.name, req.actions, req.scope
        )
    except (TenantNotFoundError, ValueError) as exc:
        raise _role_error(exc) from exc
    return _role_payload(role)


@app.patch("/api/v1/roles/{role_id}")
def update_role(
    role_id: str,
    req: RoleUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "manage_members")
    try:
        role = container.auth_service().update_role(
            _tenant_of(ctx), role_id, req.name, req.actions, req.scope
        )
    except (RoleNotFoundError, BuiltinRoleError, ValueError) as exc:
        raise _role_error(exc) from exc
    return _role_payload(role)


@app.delete("/api/v1/roles/{role_id}")
def delete_role(
    role_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "manage_members")
    try:
        container.auth_service().delete_role(_tenant_of(ctx), role_id)
    except (RoleNotFoundError, RoleInUseError, BuiltinRoleError) as exc:
        raise _role_error(exc) from exc
    return {"ok": True}


@app.get("/api/v1/series/{series_id}/grants")
def list_series_grants(
    series_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    service = container.auth_service()
    manage = service.can(ctx, "manage_members")
    if not manage:
        _enforce(ctx, "write")
    _require_series(series_id, ctx, "read" if manage else "write")
    grants = service.list_grants(_tenant_of(ctx), series_id)
    return _grants_payload(series_id, grants)


@app.put("/api/v1/series/{series_id}/grants")
def replace_series_grants(
    series_id: str,
    req: GrantReplaceRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "manage_members")
    _require_series(series_id, ctx)
    try:
        grants = container.auth_service().replace_grants(
            _tenant_of(ctx),
            series_id,
            [(item.user_id, item.level) for item in req.grants],
        )
    except (MembershipNotFoundError, ValueError) as exc:
        raise _role_error(exc) from exc
    return _grants_payload(series_id, grants)


@app.get("/api/v1/me/capabilities")
def my_capabilities(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    return container.auth_service().capabilities(ctx)


@app.get("/api/v1/settings/provider")
def get_provider_settings(
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    return container.provider_settings().get_effective(ctx.user.id)


@app.put("/api/v1/settings/provider")
def update_provider_settings(
    req: ProviderSettingsRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    extra_body = dict(req.extra_body or {}) if req.extra_body is not None else None
    if req.disable_reasoning is not None:
        extra_body = dict(extra_body or {})
        if req.disable_reasoning:
            extra_body["thinking"] = {"type": "disabled"}
        else:
            extra_body.pop("thinking", None)
    try:
        return container.provider_settings().save(
            ctx.user.id,
            req.backend,
            req.base_url,
            req.model,
            req.api_key,
            req.temperature,
            req.max_tokens,
            req.provider_id,
            extra_body,
            req.extra_headers,
        )
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/v1/settings/provider")
def reset_provider_settings(
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    return container.provider_settings().reset(ctx.user.id)


@app.post("/api/v1/settings/provider/test")
async def test_provider_settings(
    req: ProviderTestRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    provider = container.llm_for(ctx.user.id)
    selected = (req.model if req is not None else "").strip()
    model = selected or getattr(provider, "model", "")
    started = time.perf_counter()
    detail = ""
    ok = True
    try:
        await asyncio.wait_for(provider.complete("ping", max_tokens=8), timeout=15)
    except asyncio.TimeoutError:
        ok = False
        detail = "request timed out (15s)"
    except Exception as exc:
        ok = False
        detail = f"{type(exc).__name__}: {exc}"
    return {
        "ok": ok,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "provider": type(provider).__name__,
        "model": model,
        "detail": detail,
    }


@app.get("/api/v1/settings/providers")
def list_user_providers(
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    return container.user_providers().list_payload(ctx.user.id)


@app.post("/api/v1/settings/providers")
def create_user_provider(
    req: UserProviderCreateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    service = container.user_providers()
    try:
        provider = service.create(
            ctx.user.id,
            req.name,
            req.kind,
            req.base_url,
            req.api_key,
            req.models,
            req.enabled,
            req.is_default,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.payload(provider)


@app.patch("/api/v1/settings/providers/{provider_id}")
def update_user_provider(
    provider_id: str,
    req: UserProviderUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    service = container.user_providers()
    try:
        provider = service.update(
            ctx.user.id,
            provider_id,
            req.name,
            req.kind,
            req.base_url,
            req.api_key,
            req.models,
            req.enabled,
            req.is_default,
        )
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return service.payload(provider)


@app.delete("/api/v1/settings/providers/{provider_id}")
def delete_user_provider(
    provider_id: str,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    service = container.user_providers()
    try:
        service.delete(ctx.user.id, provider_id)
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DefaultProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    settings_service = container.provider_settings()
    settings_service.clear_reference(ctx.user.id, provider_id)
    payload = settings_service.get_effective(ctx.user.id)
    return {
        "ok": True,
        "active_provider_id": payload["active_provider_id"],
        "active_scope": payload["active_scope"],
    }


@app.post("/api/v1/settings/providers/{provider_id}/test")
async def test_user_provider(
    provider_id: str,
    req: ProviderTestRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    service = container.user_providers()
    selected = (req.model if req is not None else "").strip()
    try:
        provider = service.build(ctx.user.id, provider_id, selected)
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProviderDisabledError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    model = selected or getattr(provider, "model", "")
    started = time.perf_counter()
    detail = ""
    ok = True
    try:
        await asyncio.wait_for(provider.complete("ping", max_tokens=8), timeout=15)
    except asyncio.TimeoutError:
        ok = False
        detail = "request timed out (15s)"
    except Exception as exc:
        ok = False
        detail = f"{type(exc).__name__}: {exc}"
    return {
        "ok": ok,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "provider": type(provider).__name__,
        "model": model,
        "detail": detail,
    }


class ProviderShareItem(BaseModel):
    user_id: str = Field(min_length=1)
    level: Literal["use", "manage"] = "use"


class ProviderShareReplaceRequest(BaseModel):
    shares: list[ProviderShareItem] = Field(default_factory=list)


def _provider_shares_payload(provider_id: str, shares) -> dict[str, Any]:
    return {
        "provider_id": provider_id,
        "count": len(shares),
        "shares": [
            {
                "user_id": share.user_id,
                "user_email": share.user_email,
                "user_display_name": share.user_display_name,
                "level": share.level,
            }
            for share in shares
        ],
    }


@app.get("/api/v1/settings/providers/{provider_id}/shares")
def list_provider_shares(
    provider_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    service = container.user_providers()
    own = service.get(ctx.user.id, provider_id)
    if own is None and not service.can_manage_shared(provider_id, ctx.user.id):
        raise HTTPException(status_code=404, detail="personal channel not found")
    return _provider_shares_payload(provider_id, service.list_shares(provider_id))


@app.put("/api/v1/settings/providers/{provider_id}/shares")
def replace_provider_shares(
    provider_id: str,
    req: ProviderShareReplaceRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    service = container.user_providers()
    try:
        shares = service.replace_shares(
            ctx.user.id,
            provider_id,
            [(item.user_id, item.level) for item in req.shares],
        )
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _provider_shares_payload(provider_id, shares)


def _provider_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProviderNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(
        exc, (ProviderDisabledError, DefaultProviderError, ValueError)
    ):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@app.get("/api/v1/admin/providers")
def list_server_providers(
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "manage_server")
    service = container.provider_catalog()
    providers = [service.payload(item) for item in service.list()]
    return {"count": len(providers), "providers": providers}


@app.post("/api/v1/admin/providers")
def create_server_provider(
    req: ProviderCreateRequest, ctx: AuthContext = Depends(get_auth_context)
) -> Any:
    _enforce(ctx, "manage_server")
    service = container.provider_catalog()
    try:
        provider = service.create(
            req.name,
            req.kind,
            req.base_url,
            req.api_key,
            req.models,
            req.enabled,
            req.is_default,
        )
    except ValueError as exc:
        raise _provider_error(exc) from exc
    return service.payload(provider)


@app.patch("/api/v1/admin/providers/{provider_id}")
def update_server_provider(
    provider_id: str,
    req: ProviderUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> Any:
    _enforce(ctx, "manage_server")
    service = container.provider_catalog()
    try:
        provider = service.update(
            provider_id,
            req.name,
            req.kind,
            req.base_url,
            req.api_key,
            req.models,
            req.enabled,
            req.is_default,
        )
    except (ProviderNotFoundError, ValueError) as exc:
        raise _provider_error(exc) from exc
    return service.payload(provider)


@app.delete("/api/v1/admin/providers/{provider_id}")
def delete_server_provider(
    provider_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "manage_server")
    service = container.provider_catalog()
    references = container.provider_settings_repository().count_by_provider(provider_id)
    try:
        service.delete(provider_id, references)
    except ProviderInUseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DefaultProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@app.post("/api/v1/admin/providers/{provider_id}/test")
async def test_server_provider(
    provider_id: str,
    req: ProviderTestRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "manage_server")
    service = container.provider_catalog()
    provider = service.get(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider not found")
    selected = (req.model if req is not None else "").strip()
    model = service.resolve_model(provider, selected)
    llm = service.build_provider(provider, model)
    started = time.perf_counter()
    detail = ""
    ok = True
    try:
        await asyncio.wait_for(llm.complete("ping", max_tokens=8), timeout=15)
    except asyncio.TimeoutError:
        ok = False
        detail = "request timed out (15s)"
    except Exception as exc:
        ok = False
        detail = f"{type(exc).__name__}: {exc}"
    return {
        "ok": ok,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "provider": provider.name,
        "kind": provider.kind,
        "model": model,
        "detail": detail,
    }


class ResearchCreateRequest(BaseModel):
    topic: str = Field(min_length=1)
    depth: int = Field(default=2, ge=1, le=3)
    top_k: int = Field(default=6, ge=1, le=20)
    source_ids: list[str] = Field(default_factory=list)


class ResearchBlueprintRequest(BaseModel):
    series_id: str = ""
    create_series: bool = False
    series_title: str = ""
    mode: str = "loose"


class PieceCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    genre: str | None = None
    tone: str | None = None
    audience: str | None = None
    pov: str | None = None
    citation_policy: str | None = None
    target_words: int | None = Field(default=None, ge=200, le=50000)
    mode: str = "loose"
    profile_id: str = ""


class PieceSectionRequest(BaseModel):
    mode: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


class PieceGenerateRequest(BaseModel):
    mode: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    expected_version: int | None = None


class PieceRewriteRequest(BaseModel):
    instruction: str = Field(min_length=1)
    mode: str | None = None
    expected_version: int | None = None


class PieceRevertRequest(BaseModel):
    version: int = Field(ge=1)


class PieceVideoRequest(BaseModel):
    title: str = ""
    bullets: list[str] | None = None
    image_urls: list[str] | None = None


def _research_payload(run: ResearchRun) -> dict[str, Any]:
    return run.model_dump()


@app.post("/api/v1/research", status_code=201)
async def create_research(
    req: ResearchCreateRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _charge(ctx, "research", 1, ref_id=req.topic[:40])
    try:
        run = await container.research().run(
            req.topic,
            depth=req.depth,
            top_k=req.top_k,
            source_ids=req.source_ids,
            tenant_id=_tenant_of(ctx),
            user_id=ctx.user.id,
            llm=container.llm_for(ctx.user.id),
            retrieval=container.retrieval_context(_tenant_of(ctx), ctx.user.id),
        )
    except ResearchParseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _research_payload(run)


@app.get("/api/v1/research")
def list_research(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    runs = container.research().list(_tenant_of(ctx), 50)
    return {"count": len(runs), "runs": [_research_payload(run) for run in runs]}


@app.get("/api/v1/research/{run_id}")
def get_research(run_id: str, ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    run = container.research().get(run_id, _tenant_of(ctx))
    if run is None:
        raise HTTPException(status_code=404, detail=f"research run not found: {run_id}")
    return _research_payload(run)


class ResearchRenameRequest(BaseModel):
    topic: str = Field(min_length=1)


@app.patch("/api/v1/research/{run_id}")
def rename_research(
    run_id: str,
    req: ResearchRenameRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    try:
        run = container.research().rename(run_id, req.topic, _tenant_of(ctx))
    except ResearchNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _research_payload(run)


@app.delete("/api/v1/research/{run_id}")
def delete_research(
    run_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    removed = container.research().delete(run_id, _tenant_of(ctx))
    if not removed:
        raise HTTPException(status_code=404, detail=f"research run not found: {run_id}")
    return {"ok": True}


@app.post("/api/v1/research/{run_id}/blueprint")
async def research_to_blueprint(
    run_id: str,
    req: ResearchBlueprintRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    payload = req or ResearchBlueprintRequest()
    run = container.research().get(run_id, _tenant_of(ctx))
    if run is None:
        raise HTTPException(status_code=404, detail=f"research run not found: {run_id}")
    series_id = (payload.series_id or "").strip()
    if series_id:
        _require_series(series_id, ctx, "write")
    elif payload.create_series:
        series = container.series_repository().create_series(
            title=(payload.series_title or run.topic).strip(),
            subtitle=run.brief.summary[:200],
            tenant_id=_tenant_of(ctx),
            user_id=ctx.user.id,
        )
        series_id = series.id
    else:
        raise HTTPException(status_code=400, detail="provide series_id or set create_series=true")
    _charge(ctx, "blueprint", 1, ref_id=series_id)
    focus = " ".join(
        [run.topic, run.brief.summary]
        + [finding.title for finding in run.brief.findings[:6]]
    ).strip()
    try:
        blueprint = await container.blueprint().generate(
            series_id,
            mode=payload.mode or "loose",
            focus=focus,
            tenant_id=_tenant_of(ctx),
            llm=container.llm_for(ctx.user.id),
            retrieval=container.retrieval_context(_tenant_of(ctx), ctx.user.id),
        )
    except NoEvidenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BlueprintParseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (BlueprintNotFoundError, ResearchNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "research_id": run.id,
        "series_id": series_id,
        "blueprint": blueprint.model_dump(),
    }


def _require_piece(piece_id: str, ctx: AuthContext, level: str = "read"):
    piece = container.piece().get(piece_id, _tenant_of(ctx))
    service = container.auth_service()
    if piece is None or not service.can_access_piece(ctx, piece_id, "read"):
        raise HTTPException(status_code=404, detail=f"standalone piece not found: {piece_id}")
    if level == "write" and not service.can_access_piece(
        ctx, piece_id, "write"
    ):
        raise HTTPException(status_code=403, detail="missing edit permission for this standalone piece")
    return piece


@app.post("/api/v1/pieces", status_code=201)
async def create_piece(
    req: PieceCreateRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _charge(ctx, "piece", 1, ref_id=req.title[:40])
    template = None
    work_spec = None
    if req.profile_id:
        try:
            work_spec = container.profiles().get_spec(ctx, req.profile_id)
        except ProfileNotFoundError:
            work_spec = None
        except (PermissionDeniedError, BuiltinProfileError):
            work_spec = None
        if work_spec is None:
            try:
                template = container.creation_profiles().get(
                    req.profile_id, _tenant_of(ctx)
                )
            except CreationProfileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
    genre = req.genre or (template.genre if template else "article")
    citation_policy = req.citation_policy or (
        work_spec.grounding.citation_policy
        if work_spec is not None
        else (template.citation_policy if template else "optional")
    )
    tone = (
        req.tone
        if req.tone is not None
        else (
            work_spec.voice.tone
            if work_spec is not None
            else (template.tone if template else "")
        )
    )
    audience = (
        req.audience
        if req.audience is not None
        else (template.audience if template else "")
    )
    pov = (
        req.pov
        if req.pov is not None
        else (
            work_spec.voice.pov
            if work_spec is not None
            else (template.pov if template else "")
        )
    )
    target_words = req.target_words or (
        work_spec.unit.default_words
        if work_spec is not None
        else (template.target_words if template else 3000)
    )
    profile = PieceProfile(
        genre=genre,
        tone=tone,
        audience=audience,
        pov=pov,
        citation_policy=citation_policy,
        unit_name=work_spec.unit.name if work_spec is not None else "section",
    )
    piece = await container.piece().create(
        req.title,
        profile=profile,
        target_words=target_words,
        mode=req.mode,
        tenant_id=_tenant_of(ctx),
        user_id=ctx.user.id,
        llm=container.llm_for(ctx.user.id),
        profile_id=req.profile_id,
        spec=work_spec,
        retrieval=container.retrieval_context(_tenant_of(ctx), ctx.user.id),
    )
    return piece.model_dump()


@app.get("/api/v1/pieces")
def list_pieces(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    items = container.piece().list(_tenant_of(ctx), 50)
    visible = container.auth_service().visible_piece_ids(
        ctx, [item.id for item in items]
    )
    if visible is not None:
        allowed = set(visible)
        items = [item for item in items if item.id in allowed]
    return {"count": len(items), "pieces": [item.model_dump() for item in items]}


@app.get("/api/v1/pieces/{piece_id}")
def get_piece(
    piece_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    return _require_piece(piece_id, ctx).model_dump()


@app.post("/api/v1/pieces/{piece_id}/sections/{section_id}/generate")
async def generate_piece_section(
    piece_id: str,
    section_id: str,
    req: PieceSectionRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    piece = _require_piece(piece_id, ctx, "write")
    payload = req or PieceSectionRequest()
    spec = _piece_spec(piece)
    _charge(ctx, "piece", 1, ref_id=piece_id)
    try:
        section, piece = await container.piece().generate_section(
            piece_id,
            section_id,
            mode=payload.mode,
            top_k=payload.top_k,
            tenant_id=_tenant_of(ctx),
            llm=container.llm_for(ctx.user.id),
            retrieval=container.retrieval_context(_tenant_of(ctx), ctx.user.id),
            spec=spec,
            ctx=ctx,
            assets=_asset_materializer(spec),
        )
    except PieceSectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"section not found: {exc}") from exc
    except PieceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    report = await _validation_report(
        _piece_spec(piece),
        piece.content,
        {"piece_id": piece_id, "section_id": section.id, "title": piece.title},
    )
    return {
        "section_id": section.id,
        "content": section.content,
        "piece": piece.model_dump(),
        "validation": report.model_dump() if report else None,
    }


@app.post("/api/v1/pieces/{piece_id}/generate")
async def generate_piece(
    piece_id: str,
    req: PieceGenerateRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    piece = _require_piece(piece_id, ctx, "write")
    payload = req or PieceGenerateRequest()
    if payload.expected_version is not None and int(payload.expected_version) != piece.current_version:
        return _conflict(VersionConflictError(int(payload.expected_version), piece.current_version))
    _charge(ctx, "piece", 1, ref_id=piece_id)
    spec = _piece_spec(piece)
    updated = await container.piece().generate_all(
        piece_id,
        mode=payload.mode,
        top_k=payload.top_k,
        tenant_id=_tenant_of(ctx),
        llm=container.llm_for(ctx.user.id),
        retrieval=container.retrieval_context(_tenant_of(ctx), ctx.user.id),
        spec=spec,
        ctx=ctx,
        assets=_asset_materializer(spec),
    )
    report = await _validation_report(
        _piece_spec(updated),
        updated.content,
        {"piece_id": piece_id, "title": updated.title},
    )
    return {**updated.model_dump(), "validation": report.model_dump() if report else None}


@app.post("/api/v1/pieces/{piece_id}/video", status_code=202)
async def generate_piece_video(
    piece_id: str,
    request: Request,
    req: PieceVideoRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    piece = _require_piece(piece_id, ctx, "write")
    payload = req or PieceVideoRequest()
    service = container.video_service()
    try:
        ok, reason = service.available()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"video generation is unavailable: {type(exc).__name__}: {exc}",
        ) from exc
    if not ok:
        raise HTTPException(status_code=503, detail=reason)

    title = (payload.title or piece.title or "").strip()
    bullets = payload.bullets
    if bullets is None:
        bullets = [
            f"{item.title}: {item.summary}" if item.summary else item.title
            for item in piece.outline
        ]
    image_urls = payload.image_urls
    if image_urls is None:
        image_urls = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", piece.content or "")
    base_url = str(request.base_url).rstrip("/")
    resolved_images = [
        item if item.startswith(("http://", "https://")) else f"{base_url}{item}"
        for item in image_urls
        if item
    ]
    try:
        job = container.job_service().submit(
            KIND_PIECE_VIDEO,
            {
                "piece_id": piece_id,
                "title": title,
                "bullets": list(bullets or []),
                "image_urls": resolved_images,
            },
            _job_ctx(ctx),
        )
    except QuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except QueueUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except UnsupportedJobKindError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "job_id": job.id,
        "kind": job.kind,
        "status": job.status,
        "events": f"/api/v1/jobs/{job.id}/events",
    }


@app.post("/api/v1/pieces/{piece_id}/rewrite")
async def rewrite_piece(
    piece_id: str,
    req: PieceRewriteRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_piece(piece_id, ctx, "write")
    _charge(ctx, "piece", 1, ref_id=piece_id)
    try:
        updated = await container.piece().rewrite(
            piece_id,
            req.instruction,
            mode=req.mode,
            expected_version=req.expected_version,
            llm=container.llm_for(ctx.user.id),
            spec=_piece_spec(container.piece().get(piece_id)),
        )
    except VersionConflictError as exc:
        return _conflict(exc)
    except PieceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    report = await _validation_report(
        _piece_spec(updated),
        updated.content,
        {"piece_id": piece_id, "title": updated.title},
    )
    return {**updated.model_dump(), "validation": report.model_dump() if report else None}


@app.get("/api/v1/pieces/{piece_id}/versions/diff")
def diff_piece_versions(
    piece_id: str,
    from_version: int = Query(alias="from", ge=1),
    to_version: int = Query(alias="to", ge=1),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_piece(piece_id, ctx)
    return _version_diff(
        piece_id,
        from_version,
        to_version,
        lambda item: container.piece().get_version(piece_id, item),
    )


@app.get("/api/v1/pieces/{piece_id}/versions/{version}")
def get_piece_version(
    piece_id: str,
    version: int,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_piece(piece_id, ctx)
    record = container.piece().get_version(piece_id, version)
    if record is None:
        raise HTTPException(status_code=404, detail=f"version not found: {version}")
    return {
        "piece_id": piece_id,
        "version": {
            "id": record.id,
            "piece_id": record.piece_id,
            "version": record.version,
            "content": record.content,
            "outline": [item.model_dump() for item in record.outline],
            "citations": [item.model_dump() for item in record.citations],
            "mode": record.mode,
            "note": record.note,
            "created_at": record.created_at,
        },
    }


@app.get("/api/v1/pieces/{piece_id}/versions")
def list_piece_versions(
    piece_id: str,
    include_content: bool = Query(default=False),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_piece(piece_id, ctx)
    versions = container.piece().list_versions(piece_id)
    return {
        "count": len(versions),
        "versions": [
            _version_summary(
                item, {"sections": len(item.outline)}, include_content
            )
            for item in versions
        ],
    }


@app.post("/api/v1/pieces/{piece_id}/revert")
def revert_piece(
    piece_id: str,
    req: PieceRevertRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_piece(piece_id, ctx, "write")
    try:
        piece, version = container.piece().revert(piece_id, req.version)
    except PieceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"piece": piece.model_dump(), "version": version.version}


def _piece_grants_payload(piece_id: str, grants) -> dict[str, Any]:
    return {
        "piece_id": piece_id,
        "count": len(grants),
        "grants": [
            {
                "user_id": grant.user_id,
                "user_email": grant.user_email,
                "user_display_name": grant.user_display_name,
                "level": grant.level,
            }
            for grant in grants
        ],
    }


class PieceGrantItem(BaseModel):
    user_id: str = Field(min_length=1)
    level: Literal["read", "write"] = "read"


class PieceGrantReplaceRequest(BaseModel):
    grants: list[PieceGrantItem] = Field(default_factory=list)


@app.get("/api/v1/pieces/{piece_id}/grants")
def list_piece_grants(
    piece_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    service = container.auth_service()
    manage = service.can(ctx, "manage_members")
    if not manage:
        _enforce(ctx, "write")
    _require_piece(piece_id, ctx, "read" if manage else "write")
    grants = service.list_piece_grants(_tenant_of(ctx), piece_id)
    return _piece_grants_payload(piece_id, grants)


@app.put("/api/v1/pieces/{piece_id}/grants")
def replace_piece_grants(
    piece_id: str,
    req: PieceGrantReplaceRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "manage_members")
    _require_piece(piece_id, ctx)
    try:
        grants = container.auth_service().replace_piece_grants(
            _tenant_of(ctx),
            piece_id,
            [(item.user_id, item.level) for item in req.grants],
        )
    except (MembershipNotFoundError, ValueError) as exc:
        raise _role_error(exc) from exc
    return _piece_grants_payload(piece_id, grants)


@app.delete("/api/v1/pieces/{piece_id}")
def delete_piece(
    piece_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_piece(piece_id, ctx, "write")
    if not container.piece().delete(piece_id, _tenant_of(ctx)):
        raise HTTPException(status_code=404, detail=f"standalone piece not found: {piece_id}")
    return {"ok": True}


class JobSubmitRequest(BaseModel):
    kind: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


def _job_payload(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "kind": job.kind,
        "status": job.status,
        "progress": round(float(job.progress or 0.0), 4),
        "error": job.error,
        "result": job.result,
        "payload": job.payload,
        "tenant_id": job.tenant_id,
        "user_id": job.user_id,
        "attempts": job.attempts,
        "cancel_requested": job.cancel_requested,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def _job_ctx(ctx: AuthContext) -> JobContext:
    return JobContext(tenant_id=_tenant_of(ctx), user_id=ctx.user.id)


@app.get("/api/v1/jobs/kinds")
def list_job_kinds(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    return {"count": len(JOB_KINDS), "kinds": list(JOB_KINDS), "statuses": list(JOB_STATUSES)}


@app.post("/api/v1/jobs", status_code=201)
def submit_job(
    req: JobSubmitRequest, ctx: AuthContext = Depends(require_write)
) -> dict[str, Any]:
    try:
        job = container.job_service().submit(req.kind, req.payload, _job_ctx(ctx))
    except UnsupportedJobKindError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except QuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except QueueUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _job_payload(job)


@app.get("/api/v1/jobs")
def list_jobs(
    status: str | None = None,
    kind: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    jobs = container.job_service().list(_tenant_of(ctx), status, kind, limit)
    return {"count": len(jobs), "jobs": [_job_payload(job) for job in jobs]}


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str, ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    job = container.job_service().get(job_id, _tenant_of(ctx))
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return _job_payload(job)


@app.post("/api/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: str, ctx: AuthContext = Depends(require_write)) -> dict[str, Any]:
    try:
        job = container.job_service().cancel(job_id, _tenant_of(ctx))
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"job not found: {exc}") from exc
    return _job_payload(job)


@app.delete("/api/v1/jobs/{job_id}")
def delete_job(job_id: str, ctx: AuthContext = Depends(require_write)) -> dict[str, Any]:
    try:
        job = container.job_service().delete(job_id, _tenant_of(ctx))
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"job not found: {exc}") from exc
    except JobNotTerminalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "job_id": job.id, "status": job.status}


@app.get("/api/v1/jobs/{job_id}/events")
async def job_events(
    job_id: str, request: Request, ctx: AuthContext = Depends(get_auth_context)
) -> StreamingResponse:
    _enforce(ctx, "read")
    tenant_id = _tenant_of(ctx)
    service = container.job_service()
    job = service.get(job_id, tenant_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    jobs_settings = settings.jobs
    interval = float(jobs_settings.sse_interval or 0.6)
    max_seconds = float(jobs_settings.sse_max_seconds or 600.0)
    ping_seconds = float(jobs_settings.sse_ping_seconds or 15.0)
    use_bus = (jobs_settings.queue_backend or "local").strip().lower() == "redis"
    bus = container.job_events() if use_bus else None

    def frame_of(payload: dict[str, Any]) -> str:
        return "event: status\n" + "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"

    async def bus_stream():
        snapshot = service.snapshot(job_id)
        if snapshot is not None:
            yield frame_of(snapshot)
            if snapshot["status"] in ("succeeded", "failed", "canceled"):
                return
        deadline = time.time() + max_seconds
        last_ping = time.time()
        try:
            async for message in bus.subscribe(job_id):
                if await request.is_disconnected():
                    return
                if not message:
                    if time.time() - last_ping >= ping_seconds:
                        last_ping = time.time()
                        yield ": ping\n\n"
                    if time.time() >= deadline:
                        return
                    continue
                payload = {
                    "id": message.get("id") or job_id,
                    "kind": message.get("kind") or "",
                    "status": message.get("status") or "running",
                    "progress": round(float(message.get("progress") or 0.0), 4),
                    "error": message.get("error"),
                    "result": message.get("result"),
                }
                last_ping = time.time()
                yield frame_of(payload)
                if payload["status"] in ("succeeded", "failed", "canceled"):
                    return
                if time.time() >= deadline:
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[jobs] failed to subscribe to {job_id}: {exc!r}")
            snapshot = service.snapshot(job_id)
            if snapshot is not None:
                yield frame_of(snapshot)
        finally:
            try:
                await bus.aclose()
            except Exception:
                pass

    async def event_stream():
        deadline = time.time() + max_seconds
        last_signature: tuple[Any, ...] | None = None
        while True:
            if await request.is_disconnected():
                break
            current = service.get(job_id, tenant_id)
            if current is None:
                payload = {"id": job_id, "status": "failed", "progress": 0, "error": "job not found", "result": None}
                yield "event: status\n" + "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
                break
            frame = {
                "id": current.id,
                "kind": current.kind,
                "status": current.status,
                "progress": round(float(current.progress or 0.0), 4),
                "error": current.error,
                "result": current.result,
            }
            signature = (frame["status"], frame["progress"], frame["error"])
            if signature != last_signature:
                last_signature = signature
                yield "event: status\n" + "data: " + json.dumps(frame, ensure_ascii=False) + "\n\n"
            if current.status in ("succeeded", "failed", "canceled"):
                break
            if time.time() >= deadline:
                break
            await asyncio.sleep(interval)

    stream = bus_stream() if use_bus else event_stream()
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/v1/storage/info")
def storage_info(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    storage_settings = settings.storage
    info: dict[str, Any] = {
        "backend": (storage_settings.backend or "local").strip().lower(),
        "bucket": storage_settings.bucket,
        "endpoint": storage_settings.endpoint,
        "prefix": storage_settings.prefix,
        "objects": 0,
    }
    try:
        backend = container.storage()
    except Exception as exc:
        info["error"] = str(exc)
        return info
    if info["backend"] in ("s3", "rustfs"):
        tenant_prefix = "/".join(
            part
            for part in (
                storage_settings.prefix.strip("/"),
                _tenant_of(ctx) or "tenant_default",
            )
            if part
        ) + "/"
        try:
            backend.ensure_bucket()
            info["objects"] = int(backend.count_objects(tenant_prefix))
            info["prefix"] = tenant_prefix
            info["ok"] = True
        except Exception as exc:
            info["error"] = str(exc)
    else:
        try:
            info["ok"] = bool(backend.healthcheck())
        except Exception as exc:
            info["error"] = str(exc)
    return info


class SeriesUpdateRequest(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    audience: str | None = None
    difficulty: str | None = None
    language: str | None = None
    profile_id: str | None = None


@app.patch("/api/v1/series/{series_id}")
def update_series(
    series_id: str,
    req: SeriesUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_series(series_id, ctx, "write")
    series = container.series_repository().update_series(
        series_id,
        title=req.title,
        subtitle=req.subtitle,
        audience=req.audience,
        difficulty=req.difficulty,
        language=req.language,
        profile_id=req.profile_id,
    )
    if series is None:
        raise HTTPException(status_code=404, detail=f"series not found: {series_id}")
    return series.model_dump()


@app.delete("/api/v1/series/{series_id}")
def delete_series(
    series_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_series(series_id, ctx, "write")
    deleted = container.series_repository().delete_series(series_id, _tenant_of(ctx))
    if deleted is None:
        raise HTTPException(status_code=404, detail=f"series not found: {series_id}")
    return {"series_id": series_id, "deleted": deleted}


class UnitUpdateRequest(BaseModel):
    title: str | None = None
    learning_objectives: list[str] | None = None
    prerequisites: list[str] | None = None
    order_index: int | None = None
    status: str | None = None
    content: str | None = None


@app.patch("/api/v1/units/{unit_id}")
def update_unit(
    unit_id: str,
    req: UnitUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_unit(unit_id, ctx, "write")
    unit = container.series_repository().update_unit(
        unit_id,
        title=req.title,
        learning_objectives=req.learning_objectives,
        prerequisites=req.prerequisites,
        status=req.status,
        order_index=req.order_index,
        content=req.content,
    )
    if unit is None:
        raise HTTPException(status_code=404, detail=f"unit not found: {unit_id}")
    return unit.model_dump()


@app.delete("/api/v1/units/{unit_id}")
def delete_unit(
    unit_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_unit(unit_id, ctx, "write")
    deleted = container.series_repository().delete_unit(unit_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail=f"unit not found: {unit_id}")
    return {
        "unit_id": unit_id,
        "deleted_versions": deleted["deleted_versions"],
        "deleted_threads": deleted["deleted_threads"],
    }


class UnitReorderRequest(BaseModel):
    unit_ids: list[str] = Field(default_factory=list)


@app.post("/api/v1/series/{series_id}/units/reorder")
def reorder_units(
    series_id: str,
    req: UnitReorderRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_series(series_id, ctx, "write")
    repository = container.series_repository()
    known = {unit.id for unit in repository.list_units(series_id)}
    unknown = [item for item in req.unit_ids if item not in known]
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"units do not belong to this series: {', '.join(unknown[:3])}"
        )
    units = repository.reorder_units(series_id, req.unit_ids)
    return {
        "series_id": series_id,
        "count": len(units),
        "units": [unit.model_dump() for unit in units],
    }


class PieceUpdateRequest(BaseModel):
    title: str | None = None
    profile: dict[str, Any] | None = None
    target_words: int | None = Field(default=None, ge=200, le=50000)
    profile_id: str | None = None


@app.patch("/api/v1/pieces/{piece_id}")
def update_piece(
    piece_id: str,
    req: PieceUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_piece(piece_id, ctx, "write")
    try:
        updated = container.piece().update_meta(
            piece_id,
            title=req.title,
            profile=req.profile,
            target_words=req.target_words,
            profile_id=req.profile_id,
        )
    except PieceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return updated.model_dump()


class PieceContentRequest(BaseModel):
    content: str = ""
    note: str | None = None
    expected_version: int | None = None


@app.post("/api/v1/pieces/{piece_id}/content")
def save_piece_content(
    piece_id: str,
    req: PieceContentRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_piece(piece_id, ctx, "write")
    try:
        piece, version = container.piece().save_content(
            piece_id,
            req.content,
            note=req.note,
            expected_version=req.expected_version,
        )
    except VersionConflictError as exc:
        return _conflict(exc)
    except PieceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "piece": piece.model_dump(),
        "version": version.version,
        "note": version.note,
        "mode": version.mode,
    }


class PieceSectionCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    summary: str = ""
    target_words: int = Field(default=0, ge=0, le=1200)
    after_id: str | None = None


class PieceSectionUpdateRequest(BaseModel):
    title: str | None = None
    summary: str | None = None
    target_words: int | None = Field(default=None, ge=0, le=1200)
    content: str | None = None


class PieceSectionReorderRequest(BaseModel):
    section_ids: list[str] = Field(default_factory=list)


@app.post("/api/v1/pieces/{piece_id}/sections/reorder")
def reorder_piece_sections(
    piece_id: str,
    req: PieceSectionReorderRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_piece(piece_id, ctx, "write")
    try:
        updated = container.piece().reorder_sections(piece_id, req.section_ids)
    except PieceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return updated.model_dump()


@app.post("/api/v1/pieces/{piece_id}/sections", status_code=201)
def add_piece_section(
    piece_id: str,
    req: PieceSectionCreateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_piece(piece_id, ctx, "write")
    try:
        section, piece = container.piece().add_section(
            piece_id,
            req.title,
            summary=req.summary,
            target_words=req.target_words,
            after_id=req.after_id,
        )
    except PieceSectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"section not found: {exc}") from exc
    except PieceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"section": section.model_dump(), "piece": piece.model_dump()}


@app.patch("/api/v1/pieces/{piece_id}/sections/{section_id}")
def update_piece_section(
    piece_id: str,
    section_id: str,
    req: PieceSectionUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_piece(piece_id, ctx, "write")
    try:
        updated = container.piece().update_section(
            piece_id,
            section_id,
            title=req.title,
            summary=req.summary,
            target_words=req.target_words,
            content=req.content,
        )
    except PieceSectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"section not found: {exc}") from exc
    except PieceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return updated.model_dump()


@app.delete("/api/v1/pieces/{piece_id}/sections/{section_id}")
def delete_piece_section(
    piece_id: str,
    section_id: str,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_piece(piece_id, ctx, "write")
    try:
        updated = container.piece().delete_section(piece_id, section_id)
    except PieceSectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"section not found: {exc}") from exc
    except PieceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return updated.model_dump()


class CreationProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    genre: str = "article"
    tone: str = ""
    audience: str = ""
    pov: str = ""
    citation_policy: str = "optional"
    target_words: int = Field(default=3000, ge=200, le=50000)
    is_shared: bool = False


class CreationProfileUpdateRequest(BaseModel):
    name: str | None = None
    genre: str | None = None
    tone: str | None = None
    audience: str | None = None
    pov: str | None = None
    citation_policy: str | None = None
    target_words: int | None = Field(default=None, ge=200, le=50000)
    is_shared: bool | None = None


@app.get("/api/v1/creation-profiles")
def list_creation_profiles(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    items = container.creation_profiles().list(_tenant_of(ctx), ctx.user.id)
    return {"count": len(items), "profiles": items}


@app.post("/api/v1/creation-profiles", status_code=201)
def create_creation_profile(
    req: CreationProfileCreateRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    try:
        item = container.creation_profiles().create(
            _tenant_of(ctx),
            ctx.user.id,
            name=req.name,
            genre=req.genre,
            tone=req.tone,
            audience=req.audience,
            pov=req.pov,
            citation_policy=req.citation_policy,
            target_words=req.target_words,
            is_shared=req.is_shared,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return container.creation_profiles().payload(item, ctx.user.id)


@app.patch("/api/v1/creation-profiles/{profile_id}")
def update_creation_profile(
    profile_id: str,
    req: CreationProfileUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    try:
        item = container.creation_profiles().update(
            profile_id,
            _tenant_of(ctx),
            ctx.user.id,
            name=req.name,
            genre=req.genre,
            tone=req.tone,
            audience=req.audience,
            pov=req.pov,
            citation_policy=req.citation_policy,
            target_words=req.target_words,
            is_shared=req.is_shared,
        )
    except CreationProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return container.creation_profiles().payload(item, ctx.user.id)


@app.delete("/api/v1/creation-profiles/{profile_id}")
def delete_creation_profile(
    profile_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    try:
        removed = container.creation_profiles().delete(
            profile_id, _tenant_of(ctx), ctx.user.id
        )
    except CreationProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"ok": bool(removed), "profile_id": profile_id}


class ProfileCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    spec: dict[str, Any] | None = None
    is_shared: bool = False
    scope: str = "user"


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    spec: dict[str, Any] | None = None
    is_shared: bool | None = None


class ProfileDuplicateRequest(BaseModel):
    name: str | None = None


class ProfileValidateRequest(BaseModel):
    spec: dict[str, Any] | None = None


class ProfilePreviewRequest(BaseModel):
    sample: dict[str, Any] | None = None


class ProfileImportRequest(BaseModel):
    data: dict[str, Any]
    name: str | None = None
    scope: str = "user"


class ProfileSampleRequest(BaseModel):
    topic: str | None = None
    chars: int = 300


class ProfileShareItem(BaseModel):
    user_id: str = Field(min_length=1)
    level: str = "read"


class ProfileShareReplaceRequest(BaseModel):
    shares: list[ProfileShareItem] = Field(default_factory=list)


def _profile_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProfileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ProfileInvalidError):
        errors = getattr(exc, "errors", None) or []
        if errors:
            return HTTPException(
                status_code=400,
                detail={"message": str(exc), "errors": errors},
            )
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, (BuiltinProfileError, ValueError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ProfileInUseError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, PermissionDeniedError):
        return HTTPException(status_code=403, detail=str(exc))
    raise exc


def _privileged_members(ctx: AuthContext) -> bool:
    return container.auth_service().can(ctx, "manage_members")


@app.get("/api/v1/profiles")
def list_work_profiles(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    items = container.profiles().list(ctx)
    return {"count": len(items), "profiles": items}


@app.post("/api/v1/profiles", status_code=201)
def create_work_profile(
    req: ProfileCreateRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    try:
        return container.profiles().create(
            ctx,
            name=req.name,
            spec=req.spec,
            is_shared=req.is_shared,
            description=req.description,
            scope=req.scope,
        )
    except Exception as exc:
        raise _profile_error(exc) from exc


@app.post("/api/v1/profiles/import", status_code=201)
def import_work_profile(
    req: ProfileImportRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    try:
        return container.profiles().import_profile(
            ctx, req.data, name=req.name, scope=req.scope
        )
    except Exception as exc:
        raise _profile_error(exc) from exc


@app.post("/api/v1/profiles/validate")
def validate_work_profile(
    req: ProfileValidateRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    return container.profiles().validate(req.spec)


@app.get("/api/v1/profiles/{profile_id}")
def get_work_profile(
    profile_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    try:
        return container.profiles().get(ctx, profile_id)
    except Exception as exc:
        raise _profile_error(exc) from exc


@app.patch("/api/v1/profiles/{profile_id}")
def update_work_profile(
    profile_id: str,
    req: ProfileUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    try:
        return container.profiles().update(
            ctx,
            profile_id,
            name=req.name,
            spec=req.spec,
            is_shared=req.is_shared,
            description=req.description,
        )
    except Exception as exc:
        raise _profile_error(exc) from exc


@app.delete("/api/v1/profiles/{profile_id}")
def delete_work_profile(
    profile_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    try:
        return container.profiles().delete(ctx, profile_id)
    except Exception as exc:
        raise _profile_error(exc) from exc


@app.post("/api/v1/profiles/{profile_id}/duplicate", status_code=201)
def duplicate_work_profile(
    profile_id: str,
    req: ProfileDuplicateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    try:
        return container.profiles().duplicate(ctx, profile_id, name=req.name)
    except Exception as exc:
        raise _profile_error(exc) from exc


@app.get("/api/v1/profiles/{profile_id}/export")
def export_work_profile(
    profile_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> JSONResponse:
    _enforce(ctx, "read")
    try:
        payload = container.profiles().export_payload(ctx, profile_id)
    except Exception as exc:
        raise _profile_error(exc) from exc
    filename = f"{payload.get('name') or profile_id}.profile.json"
    encoded = quote(filename)
    disposition = f'attachment; filename="{encoded}"'
    if encoded != filename:
        disposition += f"; filename*=UTF-8''{encoded}"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": disposition},
    )


@app.post("/api/v1/profiles/{profile_id}/sample")
async def sample_work_profile(
    profile_id: str,
    req: ProfileSampleRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    try:
        profile, prompt, target = container.profiles().sample_prompt(
            ctx, profile_id, topic=req.topic, chars=req.chars
        )
    except Exception as exc:
        raise _profile_error(exc) from exc
    provider = container.llm_for(ctx.user.id)
    model = str(getattr(provider, "model", "") or "")
    started = time.perf_counter()
    try:
        raw = await asyncio.wait_for(
            provider.complete(prompt, max_tokens=max(256, target * 3)),
            timeout=120,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="sample timed out (120s)") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"sample generation failed: {type(exc).__name__}: {exc}"
        ) from exc
    text = container.profiles().finalize_sample(profile, raw, target)
    if not text:
        raise HTTPException(status_code=502, detail="sample generation failed: the model returned nothing")
    sample_spec = profile.spec.model_copy(deep=True)
    skipped: list[str] = []
    remaining = []
    for name in sample_spec.validation.validators:
        if str(name).strip().lower() == "length":
            skipped.append("length")
            continue
        remaining.append(name)
    sample_spec.validation.validators = remaining
    report = await container.validators().run(sample_spec, text)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    char_count = len(re.sub(r"\s+", "", text))
    return {
        "text": text,
        "chars": char_count,
        "target_chars": target,
        "model": model,
        "elapsed_ms": elapsed_ms,
        "skipped": skipped,
        "validation": report.model_dump(),
    }


@app.post("/api/v1/profiles/{profile_id}/preview")
def preview_work_profile(
    profile_id: str,
    req: ProfilePreviewRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    try:
        return container.profiles().preview(ctx, profile_id, sample=req.sample)
    except Exception as exc:
        raise _profile_error(exc) from exc


def _profile_shares_payload(profile_id: str, shares: list[Any]) -> dict[str, Any]:
    payload = container.profiles().share_payload(shares)
    return {"profile_id": profile_id, "count": len(payload), "shares": payload}


@app.get("/api/v1/profiles/{profile_id}/shares")
def list_profile_shares(
    profile_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    try:
        shares = container.profiles().list_shares(
            ctx, profile_id, privileged=_privileged_members(ctx)
        )
    except Exception as exc:
        raise _profile_error(exc) from exc
    return _profile_shares_payload(profile_id, shares)


@app.put("/api/v1/profiles/{profile_id}/shares")
def replace_profile_shares(
    profile_id: str,
    req: ProfileShareReplaceRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    try:
        shares = container.profiles().replace_shares(
            ctx,
            profile_id,
            [(item.user_id, item.level) for item in req.shares],
            privileged=_privileged_members(ctx),
        )
    except Exception as exc:
        raise _profile_error(exc) from exc
    return _profile_shares_payload(profile_id, shares)


@app.get("/api/v1/export/formats")
def export_formats(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    exporter = container.exporter()
    availability = {}
    if hasattr(exporter, "available_formats"):
        try:
            availability = dict(exporter.available_formats())
        except Exception:
            availability = {}
    return {
        "formats": [
            {
                "id": fmt,
                "label": FORMAT_LABELS[fmt],
                "available": bool(availability.get(fmt, True)),
            }
            for fmt in EXPORT_FORMATS
        ]
    }


@app.get("/api/v1/export/{source_type}/{source_id}")
def export_document(
    source_type: str,
    source_id: str,
    fmt: str = Query(FORMAT_MARKDOWN, alias="format"),
    theme: str = Query(THEME_LIGHT),
    include_citations: bool = Query(True),
    ctx: AuthContext = Depends(get_auth_context),
) -> StreamingResponse:
    _enforce(ctx, "write")
    if source_type not in EXPORT_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported export source: {source_type} (supported: {', '.join(EXPORT_SOURCE_TYPES)})",
        )
    fmt = (fmt or "").strip().lower()
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported export format: {fmt} (supported: {', '.join(EXPORT_FORMATS)})",
        )
    theme = (theme or THEME_LIGHT).strip().lower()
    if theme not in EXPORT_THEMES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported theme: {theme} (supported: {', '.join(EXPORT_THEMES)})",
        )
    if source_type == SOURCE_SERIES:
        _require_series(source_id, ctx, "write")
    else:
        _require_piece(source_id, ctx, "write")
    try:
        document = container.export_service().build_document(
            source_type,
            source_id,
            _tenant_of(ctx),
            include_citations=include_citations,
        )
        payload = container.exporter().export(
            document,
            fmt,
            theme=theme,
            include_citations=include_citations,
        )
    except ExportSourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExportFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExportUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    extension = FORMAT_EXTENSIONS[fmt]
    filename = f"{document.title or source_id}.{extension}"
    disposition = (
        f"attachment; filename=\"export.{extension}\"; "
        f"filename*=UTF-8''{quote(filename)}"
    )
    print(
        f"[export] title={document.title} source={source_type}:{source_id} "
        f"format={fmt} theme={theme} bytes={len(payload)}",
        flush=True,
    )
    return StreamingResponse(
        iter([payload]),
        media_type=FORMAT_CONTENT_TYPES[fmt],
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(len(payload)),
        },
    )


class MediaGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    size: str = "1024x1024"
    n: int = Field(default=1, ge=1, le=4)


MEDIA_CACHE_CONTROL = "private, max-age=600"


def _media_ctx(
    authorization: str | None,
    x_tenant_id: str | None,
    token: str | None,
) -> AuthContext:
    service = container.auth_service()
    if service.mode != "required":
        return service.local_context()
    raw = ""
    if authorization:
        scheme, _, value = authorization.partition(" ")
        raw = value.strip() if scheme.lower() == "bearer" else authorization.strip()
    if not raw and token:
        raw = token.strip()
    if not raw:
        raise HTTPException(status_code=401, detail="missing access token")
    try:
        return service.resolve(raw, x_tenant_id)
    except AuthRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AccountNotActiveError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except MembershipNotFoundError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/media")
def list_media(
    kind: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    assets = container.media_service().list_assets(ctx, kind=kind, limit=limit)
    return {"count": len(assets), "assets": [item.payload() for item in assets]}


@app.get("/api/v1/media/{asset_id}")
def get_media(
    asset_id: str,
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> StreamingResponse:
    ctx = _media_ctx(authorization, x_tenant_id, token)
    _enforce(ctx, "read")
    service = container.media_service()
    try:
        asset = service.get_asset(ctx, asset_id)
        data = service.read_bytes(asset)
    except MediaAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(
        iter([data]),
        media_type=asset.content_type or "application/octet-stream",
        headers={
            "Cache-Control": MEDIA_CACHE_CONTROL,
            "Content-Length": str(len(data)),
        },
    )


@app.post("/api/v1/media/upload")
async def upload_media(
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="image file is empty")
    try:
        content_type, _ = detect_image_type(file.filename or "", file.content_type or "")
    except MediaInvalidError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    max_bytes = container.media_service().max_bytes
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"image must not exceed {max_bytes // (1024 * 1024)}MB",
        )
    _charge(ctx, "upload")
    _charge(ctx, "storage", len(data))
    try:
        asset = container.media_service().save_bytes(
            ctx, data, content_type, "uploaded"
        )
    except MediaInvalidError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asset.payload()


@app.post("/api/v1/media/generate")
async def generate_media(
    req: MediaGenerateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    service = container.media_service()
    provider = service.provider()
    if provider is None or getattr(provider, "is_placeholder", False):
        raise HTTPException(status_code=503, detail="image generation is not configured")
    _charge(ctx, "image")
    try:
        assets = await service.generate(ctx, req.prompt, req.size, req.n)
    except ImageGenerationUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ImageGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except MediaInvalidError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    print(
        f"[media] generate prompt={req.prompt[:60]!r} assets={len(assets)} "
        f"provider={getattr(provider, 'name', '')}",
        flush=True,
    )
    return {
        "count": len(assets),
        "assets": [item.payload() for item in assets],
        "provider": getattr(provider, "name", ""),
    }


@app.delete("/api/v1/media/{asset_id}")
def delete_media(
    asset_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    try:
        container.media_service().delete_asset(ctx, asset_id)
    except MediaAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


class ExecRequest(BaseModel):
    language: str
    code: str
    stdin: str = ""
    timeout: int | None = Field(default=None, ge=1, le=60)


class CodeCheckRequest(BaseModel):
    language: str | None = None


def _exec_result_label(result: ExecResult) -> str:
    if result.timed_out:
        return "timeout"
    return "ok" if int(result.exit_code) == 0 else "error"


@app.get("/api/v1/exec/backends")
def exec_backends(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    backends = container.executor_backends()
    return {
        "backends": backends,
        "selected": getattr(container.executor(), "name", "none"),
        "languages": sorted(LANGUAGES.keys()),
    }


@app.post("/api/v1/exec")
def exec_code(
    req: ExecRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    ctx = _enforce(ctx, "write")
    language = (req.language or "").strip().lower()
    if language not in LANGUAGES:
        raise HTTPException(status_code=400, detail=f"unsupported language: {req.language}")
    executor = container.executor()
    if not executor.available():
        raise HTTPException(status_code=503, detail="code execution backend is not configured")
    _charge(ctx, "exec", 1, ref_id=language)
    try:
        result = executor.run(language, req.code, req.stdin, req.timeout)
    except ExecLanguageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExecUnavailableError as exc:
        raise HTTPException(status_code=503, detail="code execution backend is not configured") from exc
    get_metrics().inc_exec(result.backend, _exec_result_label(result))
    return result.model_dump()


@app.post("/api/v1/units/{unit_id}/code-check")
def unit_code_check(
    unit_id: str,
    req: CodeCheckRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    ctx = _enforce(ctx, "write")
    unit = _require_unit(unit_id, ctx, "write")
    executor = container.executor()
    if not executor.available():
        raise HTTPException(status_code=503, detail="code execution backend is not configured")
    service = CodeCheckService(executor)
    payload = service.check(unit.content or "", (req or CodeCheckRequest()).language)
    for block in payload["blocks"]:
        if block.get("exit_code") is None:
            continue
        label = "timeout" if block.get("timed_out") else (
            "ok" if block.get("ok") else "error"
        )
        get_metrics().inc_exec(getattr(executor, "name", ""), label)
    return {"unit_id": unit_id, **payload}


def _metrics_snapshot_sync() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "jobs_total": [],
        "jobs_active": 0,
        "queue_backlog": 0,
        "adapter_up": [],
        "quota_usage": [],
        "info": {"version": app.version, "env": settings.env},
    }
    try:
        jobs = container.job_repository().list(limit=2000)
        grouped: dict[tuple[str, str], int] = {}
        for job in jobs:
            key = (str(job.kind), str(job.status))
            grouped[key] = grouped.get(key, 0) + 1
        snapshot["jobs_total"] = [
            {"kind": kind, "status": status, "count": count}
            for (kind, status), count in sorted(grouped.items())
        ]
    except Exception as exc:  # noqa: BLE001
        print(f"[metrics] failed to count jobs: {exc!r}")
    try:
        counts = container.job_service().counts()
        snapshot["jobs_active"] = int(counts.get("queued") or 0) + int(
            counts.get("running") or 0
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[metrics] failed to count active jobs: {exc!r}")
    try:
        stats = container.job_queue().stats()
        snapshot["queue_backlog"] = int(stats.get("pending") or 0)
    except Exception as exc:  # noqa: BLE001
        print(f"[metrics] failed to read queue stats: {exc!r}")
    try:
        payload = {"adapters": {}}
        for name in (
            "database",
            "storage",
            "llm",
            "vectorstore",
            "exporter",
            "parser",
            "notifier",
        ):
            try:
                payload["adapters"][name] = {
                    "ok": bool(getattr(container, name)().healthcheck())
                }
            except Exception as exc:  # noqa: BLE001
                payload["adapters"][name] = {"ok": False, "error": str(exc)}
        snapshot["adapter_up"] = [
            {"name": name, "up": bool(info.get("ok"))}
            for name, info in (payload.get("adapters") or {}).items()
        ]
    except Exception as exc:  # noqa: BLE001
        print(f"[metrics] adapter probe failed: {exc!r}")
    try:
        usage = container.quota_service().usage_by_kind(DEFAULT_TENANT_ID)
        snapshot["quota_usage"] = [
            {"kind": kind, "value": int(value)}
            for kind, value in sorted(usage.items())
        ]
    except Exception as exc:  # noqa: BLE001
        print(f"[metrics] failed to read quota stats: {exc!r}")
    return snapshot


@app.get("/metrics")
def metrics_endpoint() -> PlainTextResponse:
    return PlainTextResponse(
        get_metrics().render(_metrics_snapshot()), media_type=METRICS_CONTENT_TYPE
    )


class ShareCreateRequest(BaseModel):
    resource_type: Literal["series", "piece"]
    resource_id: str = Field(min_length=1)
    expires_in_days: int = Field(default=7, ge=0, le=365)


class NotifyTestRequest(BaseModel):
    to: str = Field(min_length=3)


@app.post("/api/v1/share-links", status_code=201)
def create_share_link(
    req: ShareCreateRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    if req.resource_type == "series":
        _require_series(req.resource_id, ctx, "write")
    else:
        _require_piece(req.resource_id, ctx, "write")
    try:
        return container.shares().create(
            _tenant_of(ctx),
            ctx.user.id,
            req.resource_type,
            req.resource_id,
            req.expires_in_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/share-links")
def list_share_links(
    resource_type: str = Query(default=""),
    resource_id: str = Query(default=""),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    links = container.shares().list(_tenant_of(ctx), resource_type, resource_id)
    return {"count": len(links), "links": links}


@app.delete("/api/v1/share-links/{link_id}")
def delete_share_link(
    link_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    try:
        container.shares().revoke(_tenant_of(ctx), link_id)
    except ShareNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}


@app.get("/api/v1/public/shares/{token}")
def public_share(token: str, request: Request) -> dict[str, Any]:
    client_ip = request.client.host if request.client else ""
    try:
        return container.shares().resolve_public(token, client_ip)
    except ShareNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ShareRevokedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ShareExpiredError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except ShareRateLimitedError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@app.post("/api/v1/admin/notify/test")
def notify_test(
    req: NotifyTestRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "manage_server")
    return container.notifications().send_test(req.to)
