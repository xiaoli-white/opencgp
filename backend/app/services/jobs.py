from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.models.job import (
    ERROR_MAX_CHARS,
    JOB_KINDS,
    KIND_BLUEPRINT_GENERATE,
    KIND_KB_EMBED_BACKFILL,
    KIND_UNIT_GENERATE,
    KIND_PIECE_CREATE,
    KIND_PIECE_GENERATE,
    KIND_PIECE_REWRITE,
    KIND_PIECE_VIDEO,
    KIND_RESEARCH,
    QUOTA_KIND_BY_JOB_KIND,
    STATUS_CANCELED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    Job,
    is_terminal,
)
from app.services.errors import (
    QueueUnavailableError,
    JobNotFoundError,
    JobNotTerminalError,
    UnsupportedJobKindError,
)

STAGE_START = 0.05
STAGE_DONE = 0.95


@dataclass
class JobContext:
    tenant_id: str = ""
    user_id: str = ""
    job_id: str = ""
    llm: Any = None
    retrieval: Any = None
    progress_reporter: Callable[[float], None] | None = None
    cancel_checker: Callable[[], bool] | None = None

    def report(self, value: float) -> None:
        if self.progress_reporter is not None:
            self.progress_reporter(value)

    def canceled(self) -> bool:
        return bool(self.cancel_checker()) if self.cancel_checker is not None else False

    def ensure_active(self) -> None:
        if self.canceled():
            raise JobCanceled()


class JobCanceled(Exception):
    pass


class JobFailure(RuntimeError):
    pass


@dataclass
class JobService:
    repository: Any
    queue: Any = None
    research: Any = None
    piece: Any = None
    generation: Any = None
    blueprint: Any = None
    video: Any = None
    quota: Any = None
    llm_for: Callable[[str], Any] | None = None
    embedding_for: Callable[[str, str, str], Any] | None = None
    retrieval_for: Callable[[str, str], Any] | None = None
    events: Any = None
    vectorstore: Any = None
    embedder: Any = None
    embedding_batch: int = 32
    default_top_k: int = 6
    default_mode: str = "loose"
    runners: dict[str, Callable[[Job, dict[str, Any], JobContext], Awaitable[dict[str, Any]]]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        self.runners = {
            KIND_RESEARCH: self._run_research,
            KIND_PIECE_CREATE: self._run_piece_create,
            KIND_PIECE_GENERATE: self._run_piece_generate,
            KIND_PIECE_REWRITE: self._run_piece_rewrite,
            KIND_PIECE_VIDEO: self._run_piece_video,
            KIND_UNIT_GENERATE: self._run_unit_generate,
            KIND_BLUEPRINT_GENERATE: self._run_blueprint_generate,
            KIND_KB_EMBED_BACKFILL: self._run_kb_embed_backfill,
        }

    def submit(self, kind: str, payload: dict[str, Any], ctx: JobContext) -> Job:
        resolved = (kind or "").strip().lower()
        if resolved not in JOB_KINDS or resolved not in self.runners:
            raise UnsupportedJobKindError(
                f"unsupported job kind: {kind!r}; valid kinds: {', '.join(JOB_KINDS)}"
            )
        body = dict(payload or {})
        quota_kind = QUOTA_KIND_BY_JOB_KIND.get(resolved, "generate")
        if self.quota is not None and resolved != KIND_KB_EMBED_BACKFILL:
            self.quota.check_and_record(
                ctx.tenant_id, ctx.user_id, quota_kind, 1, resolved
            )
        job = Job.create(
            kind=resolved,
            payload=body,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
        )
        self.repository.create(job)
        if self.queue is not None:
            try:
                self.queue.enqueue(job.id)
            except Exception as exc:
                self.repository.update_status(
                    job.id, "failed", error=f"queue unavailable: {exc}"
                )
                raise QueueUnavailableError(f"job queue is unavailable: {exc}") from exc
        return job

    def get(self, job_id: str, tenant_id: str | None = None) -> Job | None:
        job = self.repository.get(job_id)
        if job is None:
            return None
        if tenant_id and job.tenant_id and job.tenant_id != tenant_id:
            return None
        return job

    def require(self, job_id: str, tenant_id: str | None = None) -> Job:
        job = self.get(job_id, tenant_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def list(
        self,
        tenant_id: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 20,
    ) -> list[Job]:
        return self.repository.list(tenant_id, status, kind, limit)

    def cancel(self, job_id: str, tenant_id: str | None = None) -> Job:
        job = self.require(job_id, tenant_id)
        if is_terminal(job.status):
            return job
        updated = self.repository.request_cancel(job.id)
        self._publish(job.id)
        return updated or job

    def counts(self, tenant_id: str | None = None) -> dict[str, int]:
        return self.repository.counts(tenant_id)

    def delete(self, job_id: str, tenant_id: str | None = None) -> Job:
        job = self.require(job_id, tenant_id)
        if not is_terminal(job.status):
            raise JobNotTerminalError("the job has not finished yet and cannot be deleted")
        self.repository.delete(job.id)
        return job

    def recover_stale(self) -> int:
        return int(self.repository.recover_stale())

    def _publish(self, job_id: str) -> None:
        if self.events is None:
            return
        try:
            job = self.repository.get(job_id)
            if job is None:
                return
            self.events.publish(
                job_id,
                {
                    "id": job.id,
                    "kind": job.kind,
                    "status": job.status,
                    "progress": round(float(job.progress or 0.0), 4),
                    "error": job.error,
                    "result": job.result,
                },
            )
        except Exception as exc:
            print(f"[jobs] failed to publish the event for {job_id}: {exc!r}")

    def _set_status(self, job_id: str, status: str, result=None, error: str = "") -> None:
        self.repository.update_status(job_id, status, result, error)
        self._publish(job_id)

    def _set_progress(self, job_id: str, value: float) -> None:
        self.repository.update_progress(job_id, value)
        self._publish(job_id)

    def snapshot(self, job_id: str) -> dict[str, Any] | None:
        job = self.repository.get(job_id)
        if job is None:
            return None
        return {
            "id": job.id,
            "kind": job.kind,
            "status": job.status,
            "progress": round(float(job.progress or 0.0), 4),
            "error": job.error,
            "result": job.result,
        }

    def start(self) -> None:
        if self.queue is not None:
            setter = getattr(self.queue, "set_job_repository", None)
            if callable(setter):
                try:
                    setter(self.repository)
                except Exception as exc:
                    print(f"[jobs] failed to inject the job repository into the queue: {exc!r}")
            self.queue.start(self.handle)

    async def aclose(self) -> None:
        if self.queue is not None:
            await self.queue.aclose()

    async def handle(self, job_id: str) -> None:
        job = self.repository.get(job_id)
        if job is None:
            return
        if job.status in (STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELED):
            return
        if self.repository.has_cancel_request(job_id):
            self._set_status(job_id, STATUS_CANCELED, None, "Canceled")
            return
        self._set_status(job_id, STATUS_RUNNING)
        retrieval = None
        if self.retrieval_for is not None:
            try:
                retrieval = self.retrieval_for(job.tenant_id, job.user_id)
            except Exception as exc:  # noqa: BLE001
                print(f"[jobs] failed to resolve the retrieval configuration; falling back to environment defaults: {exc!r}")
        context = JobContext(
            tenant_id=job.tenant_id,
            user_id=job.user_id,
            job_id=job_id,
            llm=self._llm(job.user_id),
            retrieval=retrieval,
            progress_reporter=lambda value: self._set_progress(job_id, value),
            cancel_checker=lambda: self.repository.has_cancel_request(job_id),
        )
        context.report(STAGE_START)
        runner = self.runners.get(job.kind)
        if runner is None:
            self._set_status(
                job_id, STATUS_FAILED, None, f"unsupported job kind: {job.kind}"
            )
            return
        try:
            result = await runner(job, job.payload, context)
        except JobCanceled:
            self._set_status(job_id, STATUS_CANCELED, None, "Canceled")
            return
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            message = str(exc)[:ERROR_MAX_CHARS] or type(exc).__name__
            self._set_status(job_id, STATUS_FAILED, None, message)
            raise JobFailure(message) from exc
        if self.repository.has_cancel_request(job_id):
            self._set_status(job_id, STATUS_CANCELED, result, "Canceled")
            return
        context.report(STAGE_DONE)
        self._set_status(job_id, STATUS_SUCCEEDED, result, "")

    def _llm(self, user_id: str) -> Any:
        if self.llm_for is None:
            return None
        try:
            return self.llm_for(user_id)
        except Exception:  # noqa: BLE001
            return None

    async def _run_kb_embed_backfill(
        self, job: Job, payload: dict[str, Any], ctx: JobContext
    ) -> dict[str, Any]:
        from app.services.embedding_backfill import backfill_embeddings

        ctx.ensure_active()
        provider_id = str(payload.get("provider_id") or "")
        embedder = self.embedder
        if self.embedding_for is not None:
            try:
                resolved = self.embedding_for(
                    ctx.tenant_id, ctx.user_id, provider_id
                )
                embedder = getattr(resolved, "adapter", None)
                provider_id = str(
                    getattr(resolved, "provider_id", "") or provider_id
                )
            except Exception:
                embedder = self.embedder
        if embedder is None or self.vectorstore is None:
            return {"embedded": 0, "failed": 0, "skipped": 0}
        batch = max(1, int(payload.get("batch") or self.embedding_batch or 32))

        def report(value: float) -> None:
            ctx.ensure_active()
            ctx.report(min(0.95, 0.05 + 0.9 * max(0.0, min(1.0, float(value)))))

        result = await backfill_embeddings(
            store=self.vectorstore,
            embedder=embedder,
            tenant_id=ctx.tenant_id,
            source_id=str(payload.get("source_id") or ""),
            batch_size=batch,
            progress=report,
            provider_id=provider_id,
        )
        ctx.ensure_active()
        return {
            "embedded": int(result.get("embedded") or 0),
            "failed": int(result.get("failed") or 0),
            "skipped": int(result.get("skipped") or 0),
            "provider_id": provider_id,
        }

    async def _run_research(
        self, job: Job, payload: dict[str, Any], ctx: JobContext
    ) -> dict[str, Any]:
        ctx.ensure_active()
        stages: list[dict[str, Any]] = []
        last_progress = max(float(job.progress or 0.0), STAGE_START)

        def on_progress(stage: str, value: float) -> None:
            nonlocal last_progress
            resolved = max(0.0, min(float(value), 1.0))
            if resolved < last_progress:
                resolved = last_progress
            stages.append({"stage": stage, "at": round(time.time(), 4)})
            if resolved > last_progress:
                last_progress = resolved
                ctx.report(resolved)

        run = await self.research.run(
            payload.get("topic", ""),
            depth=int(payload.get("depth") or 1),
            top_k=payload.get("top_k"),
            source_ids=payload.get("source_ids"),
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            llm=ctx.llm,
            retrieval=ctx.retrieval,
            on_progress=on_progress,
        )
        ctx.report(max(last_progress, 0.9))
        ctx.ensure_active()
        return {
            "research_id": run.id,
            "topic": run.topic,
            "status": run.status,
            "summary": run.brief.summary[:400],
            "findings": len(run.brief.findings),
            "citations": len(run.citations),
            "warnings": list(run.warnings),
            "retrieval": dict(run.retrieval),
            "stage": stages[-1]["stage"] if stages else "",
            "stages": stages,
        }

    async def _run_piece_create(
        self, job: Job, payload: dict[str, Any], ctx: JobContext
    ) -> dict[str, Any]:
        ctx.ensure_active()
        ctx.report(0.2)
        from app.models.piece import PieceProfile

        profile_raw = payload.get("profile") or {}
        profile = (
            profile_raw
            if isinstance(profile_raw, PieceProfile)
            else PieceProfile(**profile_raw)
        )
        piece = await self.piece.create(
            payload.get("title", ""),
            profile=profile,
            target_words=int(payload.get("target_words") or 3000),
            mode=payload.get("mode") or self.default_mode,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            llm=ctx.llm,
            retrieval=ctx.retrieval,
        )
        ctx.report(0.9)
        return {
            "piece_id": piece.id,
            "title": piece.title,
            "sections": len(piece.outline),
            "current_version": piece.current_version,
            "warnings": list(piece.warnings),
            "retrieval": dict(piece.retrieval),
        }

    async def _run_piece_generate(
        self, job: Job, payload: dict[str, Any], ctx: JobContext
    ) -> dict[str, Any]:
        ctx.ensure_active()
        ctx.report(0.1)
        piece_id = str(payload.get("piece_id") or "").strip()
        if not piece_id:
            raise ValueError("missing piece_id")

        def on_progress(done: int, total: int) -> None:
            ctx.report(0.1 + 0.8 * (done / max(1, total)))
            ctx.ensure_active()

        piece = await self.piece.generate_all(
            piece_id,
            mode=payload.get("mode") or self.default_mode,
            top_k=payload.get("top_k"),
            tenant_id=ctx.tenant_id,
            llm=ctx.llm,
            on_progress=on_progress,
            retrieval=ctx.retrieval,
        )
        ctx.report(0.9)
        ctx.ensure_active()
        return {
            "piece_id": piece.id,
            "title": piece.title,
            "current_version": piece.current_version,
            "words": len(piece.content),
            "sections": len(piece.outline),
            "warnings": list(piece.warnings),
            "retrieval": dict(piece.retrieval),
        }

    async def _run_piece_rewrite(
        self, job: Job, payload: dict[str, Any], ctx: JobContext
    ) -> dict[str, Any]:
        ctx.ensure_active()
        ctx.report(0.3)
        piece_id = str(payload.get("piece_id") or "").strip()
        if not piece_id:
            raise ValueError("missing piece_id")
        piece = await self.piece.rewrite(
            piece_id,
            str(payload.get("instruction") or "polish"),
            mode=payload.get("mode") or self.default_mode,
            expected_version=payload.get("expected_version"),
            llm=ctx.llm,
        )
        ctx.report(0.9)
        return {
            "piece_id": piece.id,
            "current_version": piece.current_version,
            "words": len(piece.content),
        }

    async def _run_piece_video(
        self, job: Job, payload: dict[str, Any], ctx: JobContext
    ) -> dict[str, Any]:
        ctx.ensure_active()
        ctx.report(0.05)
        if self.video is None:
            raise ValueError("video generation service is not configured")
        piece_id = str(payload.get("piece_id") or "").strip()
        if not piece_id:
            raise ValueError("missing piece_id")

        piece = None
        if self.piece is not None:
            getter = getattr(self.piece, "get", None)
            if callable(getter):
                piece = getter(piece_id, ctx.tenant_id or None)
        title = str(payload.get("title") or (getattr(piece, "title", "") if piece else "")).strip()
        bullets = payload.get("bullets")
        if not bullets and piece is not None:
            bullets = [
                f"{item.title}: {item.summary}" if item.summary else item.title
                for item in piece.outline
            ]
        image_urls = payload.get("image_urls") or []
        if not image_urls and piece is not None:
            import re

            image_urls = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", piece.content or "")

        from app.models.auth import (
            DEFAULT_TENANT_ID,
            DEFAULT_USER_ID,
            AuthContext,
            Tenant,
            User,
        )

        tenant_id = ctx.tenant_id or DEFAULT_TENANT_ID
        user_id = ctx.user_id or DEFAULT_USER_ID
        media_ctx = AuthContext(
            user=User(id=user_id, email="", display_name=""),
            tenant=Tenant(id=tenant_id, name=tenant_id),
        )

        def on_progress(value: float) -> None:
            ctx.ensure_active()
            ctx.report(0.05 + 0.9 * max(0.0, min(float(value), 1.0)))

        asset = await self.video.generate(
            media_ctx,
            title=title,
            bullets=list(bullets or []),
            image_urls=list(image_urls or []),
            on_progress=on_progress,
        )
        ctx.report(0.98)
        ctx.ensure_active()
        return {
            "piece_id": piece_id,
            "asset": asset.payload(),
            "asset_id": asset.id,
            "url": asset.url(),
            "content_type": asset.content_type,
            "bytes": int(asset.bytes),
        }

    async def _run_unit_generate(
        self, job: Job, payload: dict[str, Any], ctx: JobContext
    ) -> dict[str, Any]:
        ctx.ensure_active()
        ctx.report(0.2)
        unit_id = str(payload.get("unit_id") or "").strip()
        if not unit_id:
            raise ValueError("missing unit_id")
        result = await self.generation.generate_unit(
            unit_id,
            topic=payload.get("topic"),
            top_k=payload.get("top_k"),
            mode=payload.get("mode"),
            expected_version=payload.get("expected_version"),
            tenant_id=ctx.tenant_id,
            llm=ctx.llm,
            retrieval=ctx.retrieval,
        )
        ctx.report(0.9)
        return {
            "unit_id": result.unit_id,
            "version": result.version,
            "mode": result.mode,
            "grounded": result.grounded,
            "citations": len(result.citations),
            "words": len(result.content),
            "warnings": list(result.warnings),
            "retrieval": dict(result.retrieval),
        }

    async def _run_blueprint_generate(
        self, job: Job, payload: dict[str, Any], ctx: JobContext
    ) -> dict[str, Any]:
        ctx.ensure_active()
        ctx.report(0.2)
        series_id = str(payload.get("series_id") or "").strip()
        if not series_id:
            raise ValueError("missing series_id")
        blueprint = await self.blueprint.generate(
            series_id,
            mode=payload.get("mode"),
            top_k=payload.get("top_k"),
            source_ids=payload.get("source_ids"),
            focus=str(payload.get("focus") or ""),
            tenant_id=ctx.tenant_id,
            llm=ctx.llm,
            retrieval=ctx.retrieval,
        )
        ctx.report(0.9)
        return {
            "series_id": blueprint.series_id,
            "version": blueprint.version,
            "stages": len(blueprint.learning_path),
            "nodes": len(blueprint.outline),
            "glossary": len(blueprint.glossary),
            "grounded": blueprint.grounded,
            "warnings": list(blueprint.warnings),
            "retrieval": dict(blueprint.retrieval),
        }


def now() -> float:
    return time.time()
