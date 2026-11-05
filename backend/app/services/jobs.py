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
    KIND_LESSON_GENERATE,
    KIND_LONGFORM_CREATE,
    KIND_LONGFORM_GENERATE,
    KIND_LONGFORM_REWRITE,
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
    longform: Any = None
    generation: Any = None
    blueprint: Any = None
    quota: Any = None
    llm_for: Callable[[str], Any] | None = None
    embedding_for: Callable[[str, str, str], Any] | None = None
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
            KIND_LONGFORM_CREATE: self._run_longform_create,
            KIND_LONGFORM_GENERATE: self._run_longform_generate,
            KIND_LONGFORM_REWRITE: self._run_longform_rewrite,
            KIND_LESSON_GENERATE: self._run_lesson_generate,
            KIND_BLUEPRINT_GENERATE: self._run_blueprint_generate,
            KIND_KB_EMBED_BACKFILL: self._run_kb_embed_backfill,
        }

    def submit(self, kind: str, payload: dict[str, Any], ctx: JobContext) -> Job:
        resolved = (kind or "").strip().lower()
        if resolved not in JOB_KINDS or resolved not in self.runners:
            raise UnsupportedJobKindError(
                f"不支持的任务类型: {kind!r}，可选: {', '.join(JOB_KINDS)}"
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
                    job.id, "failed", error=f"队列不可用: {exc}"
                )
                raise QueueUnavailableError(f"任务队列不可用: {exc}") from exc
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
            raise JobNotTerminalError("任务尚未结束，无法删除")
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
            print(f"[jobs] 事件发布失败 {job_id}: {exc!r}")

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
                    print(f"[jobs] 注入任务仓库到队列失败: {exc!r}")
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
            self._set_status(job_id, STATUS_CANCELED, None, "已取消")
            return
        self._set_status(job_id, STATUS_RUNNING)
        context = JobContext(
            tenant_id=job.tenant_id,
            user_id=job.user_id,
            job_id=job_id,
            llm=self._llm(job.user_id),
            progress_reporter=lambda value: self._set_progress(job_id, value),
            cancel_checker=lambda: self.repository.has_cancel_request(job_id),
        )
        context.report(STAGE_START)
        runner = self.runners.get(job.kind)
        if runner is None:
            self._set_status(
                job_id, STATUS_FAILED, None, f"不支持的任务类型: {job.kind}"
            )
            return
        try:
            result = await runner(job, job.payload, context)
        except JobCanceled:
            self._set_status(job_id, STATUS_CANCELED, None, "已取消")
            return
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            message = str(exc)[:ERROR_MAX_CHARS] or type(exc).__name__
            self._set_status(job_id, STATUS_FAILED, None, message)
            raise JobFailure(message) from exc
        if self.repository.has_cancel_request(job_id):
            self._set_status(job_id, STATUS_CANCELED, result, "已取消")
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
        ctx.report(0.2)
        run = await self.research.run(
            payload.get("topic", ""),
            depth=int(payload.get("depth") or 1),
            top_k=payload.get("top_k"),
            source_ids=payload.get("source_ids"),
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            llm=ctx.llm,
        )
        ctx.report(0.9)
        ctx.ensure_active()
        return {
            "research_id": run.id,
            "topic": run.topic,
            "status": run.status,
            "summary": run.brief.summary[:400],
            "findings": len(run.brief.findings),
            "citations": len(run.citations),
        }

    async def _run_longform_create(
        self, job: Job, payload: dict[str, Any], ctx: JobContext
    ) -> dict[str, Any]:
        ctx.ensure_active()
        ctx.report(0.2)
        from app.models.longform import LongformProfile

        profile_raw = payload.get("profile") or {}
        profile = (
            profile_raw
            if isinstance(profile_raw, LongformProfile)
            else LongformProfile(**profile_raw)
        )
        longform = await self.longform.create(
            payload.get("title", ""),
            profile=profile,
            target_words=int(payload.get("target_words") or 3000),
            mode=payload.get("mode") or self.default_mode,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
            llm=ctx.llm,
        )
        ctx.report(0.9)
        return {
            "longform_id": longform.id,
            "title": longform.title,
            "sections": len(longform.outline),
            "current_version": longform.current_version,
        }

    async def _run_longform_generate(
        self, job: Job, payload: dict[str, Any], ctx: JobContext
    ) -> dict[str, Any]:
        ctx.ensure_active()
        ctx.report(0.1)
        longform_id = str(payload.get("longform_id") or "").strip()
        if not longform_id:
            raise ValueError("缺少 longform_id")

        def on_progress(done: int, total: int) -> None:
            ctx.report(0.1 + 0.8 * (done / max(1, total)))
            ctx.ensure_active()

        longform = await self.longform.generate_all(
            longform_id,
            mode=payload.get("mode") or self.default_mode,
            top_k=payload.get("top_k"),
            tenant_id=ctx.tenant_id,
            llm=ctx.llm,
            on_progress=on_progress,
        )
        ctx.report(0.9)
        ctx.ensure_active()
        return {
            "longform_id": longform.id,
            "title": longform.title,
            "current_version": longform.current_version,
            "words": len(longform.content),
            "sections": len(longform.outline),
        }

    async def _run_longform_rewrite(
        self, job: Job, payload: dict[str, Any], ctx: JobContext
    ) -> dict[str, Any]:
        ctx.ensure_active()
        ctx.report(0.3)
        longform_id = str(payload.get("longform_id") or "").strip()
        if not longform_id:
            raise ValueError("缺少 longform_id")
        longform = await self.longform.rewrite(
            longform_id,
            str(payload.get("instruction") or "润色"),
            mode=payload.get("mode") or self.default_mode,
            expected_version=payload.get("expected_version"),
            llm=ctx.llm,
        )
        ctx.report(0.9)
        return {
            "longform_id": longform.id,
            "current_version": longform.current_version,
            "words": len(longform.content),
        }

    async def _run_lesson_generate(
        self, job: Job, payload: dict[str, Any], ctx: JobContext
    ) -> dict[str, Any]:
        ctx.ensure_active()
        ctx.report(0.2)
        lesson_id = str(payload.get("lesson_id") or "").strip()
        if not lesson_id:
            raise ValueError("缺少 lesson_id")
        result = await self.generation.generate_lesson(
            lesson_id,
            topic=payload.get("topic"),
            top_k=payload.get("top_k"),
            mode=payload.get("mode"),
            expected_version=payload.get("expected_version"),
            tenant_id=ctx.tenant_id,
            llm=ctx.llm,
        )
        ctx.report(0.9)
        return {
            "lesson_id": result.lesson_id,
            "version": result.version,
            "mode": result.mode,
            "grounded": result.grounded,
            "citations": len(result.citations),
            "words": len(result.content),
        }

    async def _run_blueprint_generate(
        self, job: Job, payload: dict[str, Any], ctx: JobContext
    ) -> dict[str, Any]:
        ctx.ensure_active()
        ctx.report(0.2)
        course_id = str(payload.get("course_id") or "").strip()
        if not course_id:
            raise ValueError("缺少 course_id")
        blueprint = await self.blueprint.generate(
            course_id,
            mode=payload.get("mode"),
            top_k=payload.get("top_k"),
            source_ids=payload.get("source_ids"),
            focus=str(payload.get("focus") or ""),
            tenant_id=ctx.tenant_id,
            llm=ctx.llm,
        )
        ctx.report(0.9)
        return {
            "course_id": blueprint.course_id,
            "version": blueprint.version,
            "stages": len(blueprint.learning_path),
            "nodes": len(blueprint.outline),
            "glossary": len(blueprint.glossary),
            "grounded": blueprint.grounded,
        }


def now() -> float:
    return time.time()
