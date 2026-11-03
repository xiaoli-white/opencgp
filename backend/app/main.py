"""FastAPI 应用入口。

提供健康检查端点 ``/health``、LLM 生成端点与 RAG 知识库端点，
并装配 Port/Adapter 容器。
启动方式（M0 单机）：:

    cd backend
    uvicorn app.main:app --port 8000
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.container import get_container
from app.models.auth import DEFAULT_TENANT_ID, AuthContext
from app.models.citation import Citation
from app.models.blueprint import CourseBlueprint, GlossaryTerm
from app.models.course import Course, Lesson
from app.models.mode import GenerationMode
from app.models.thread import LessonThreadView
from app.services.errors import (
    AuthRequiredError,
    BlueprintNotFoundError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    MembershipNotFoundError,
    PermissionDeniedError,
    TenantNotFoundError,
    BlueprintParseError,
    EmptyLLMResponseError,
    LessonContentEmptyError,
    LessonNotFoundError,
    MessageNotFoundError,
    NoEvidenceError,
    QuotaExceededError,
    VersionConflictError,
    LessonLockedError,
    LessonLockLostError,
    LockTokenMismatchError,
    RoleNotFoundError,
    RoleInUseError,
    BuiltinRoleError,
)

settings = get_settings()
container = get_container()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI 课程工作室 · 以对话为中心、以课程为活文档的创作工作台",
)

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
        raise HTTPException(status_code=401, detail="缺少访问令牌")
    try:
        return service.resolve(token, x_tenant_id)
    except AuthRequiredError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
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


def _guard_lock(lesson_id: str, ctx: AuthContext) -> None:
    try:
        container.lock_service().guard(lesson_id, ctx.user.id)
    except LessonLockedError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"该讲正被 {exc.name} 编辑，请先协商或接管",
        ) from exc


def _conflict(exc: VersionConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": "版本冲突：内容已被他人更新",
            "expected_version": exc.expected,
            "current_version": exc.current,
        },
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
    for name in ("database", "storage", "llm", "vectorstore", "exporter", "parser"):
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
    try:
        result = await container.ingest().ingest_bytes(
            data,
            filename,
            source_name=source_name,
            tenant_id=_tenant_of(ctx),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    source_ids: list[str] | None = None


@app.post("/api/v1/kb/search")
async def kb_search(
    req: SearchRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    citations: list[Citation] = await container.ingest().search(
        req.query,
        top_k=req.top_k,
        source_ids=req.source_ids,
        tenant_id=_tenant_of(ctx),
    )
    return {
        "query": req.query,
        "top_k": req.top_k,
        "count": len(citations),
        "citations": [citation.model_dump() for citation in citations],
    }


@app.delete("/api/v1/kb/sources/{source_id}")
async def kb_delete_source(
    source_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    removed = await container.ingest().delete_source(source_id, tenant_id=_tenant_of(ctx))
    return {"source_id": source_id, "deleted_chunks": removed}


class CourseCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    subtitle: str = ""
    audience: str = ""
    difficulty: str = "intermediate"
    language: str = "zh"


class LessonCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    order_index: int | None = Field(default=None, ge=1)
    learning_objectives: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    content: str = ""
    note: str = "create"


class LessonGenerateRequest(BaseModel):
    topic: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)
    note: str = ""
    source_ids: list[str] | None = None
    mode: GenerationMode = GenerationMode.strict
    expected_version: int | None = None


class LessonRevertRequest(BaseModel):
    version: int = Field(ge=1)
    note: str = ""
    expected_version: int | None = None


class LessonAskRequest(BaseModel):
    question: str = Field(min_length=1)
    selection: str | None = None


class LessonAmendRequest(BaseModel):
    instruction: str = Field(min_length=1)
    target: str | None = None
    mode: GenerationMode = GenerationMode.strict
    expected_version: int | None = None


class LessonDrilldownRequest(BaseModel):
    message_id: str | None = None
    question: str | None = None


def _require_course(
    course_id: str, ctx: AuthContext | None = None, level: str = "read"
) -> Course:
    tenant_id = _tenant_of(ctx) if ctx is not None else None
    course = container.course_repository().get_course(course_id, tenant_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"课程不存在: {course_id}")
    if ctx is not None and not container.auth_service().can_access_course(ctx, course_id, level):
        raise HTTPException(status_code=404, detail=f"课程不存在: {course_id}")
    return course


def _require_lesson(
    lesson_id: str, ctx: AuthContext | None = None, level: str = "read"
) -> Lesson:
    lesson = container.course_repository().get_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail=f"讲次不存在: {lesson_id}")
    if ctx is not None:
        _require_course(lesson.course_id, ctx, level)
    return lesson


@app.post("/api/v1/courses", status_code=201)
def create_course(
    req: CourseCreateRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    course = container.course_repository().create_course(
        title=req.title,
        subtitle=req.subtitle,
        audience=req.audience,
        difficulty=req.difficulty,
        language=req.language,
        tenant_id=_tenant_of(ctx),
    )
    return course.model_dump()


@app.get("/api/v1/courses")
def list_courses(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    _enforce(ctx, "read")
    courses = container.course_repository().list_courses(_tenant_of(ctx))
    visible = container.auth_service().visible_course_ids(ctx)
    if visible is not None:
        courses = [course for course in courses if course.id in visible]
    return {"count": len(courses), "courses": [course.model_dump() for course in courses]}


@app.get("/api/v1/courses/{course_id}")
def get_course(
    course_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    course = _require_course(course_id, ctx)
    lessons = container.course_repository().list_lessons(course_id)
    return {
        "course": course.model_dump(),
        "lesson_count": len(lessons),
        "lessons": [lesson.model_dump() for lesson in lessons],
        "progress": container.blueprint().progress(course_id),
    }


@app.post("/api/v1/courses/{course_id}/lessons", status_code=201)
def create_lesson(
    course_id: str,
    req: LessonCreateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_course(course_id, ctx, "write")
    repository = container.course_repository()
    lesson = repository.create_lesson(
        course_id=course_id,
        title=req.title,
        order_index=req.order_index,
        learning_objectives=req.learning_objectives,
        prerequisites=req.prerequisites,
    )
    version = 0
    if req.content.strip():
        applied = repository.append_version(
            lesson.id,
            content=req.content,
            citations=[],
            note=req.note,
            status="draft",
        )
        if applied is not None:
            lesson, record = applied
            version = record.version
    return {"lesson": lesson.model_dump(), "version": version}


@app.get("/api/v1/courses/{course_id}/lessons")
def list_lessons(
    course_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_course(course_id, ctx)
    lessons = container.course_repository().list_lessons(course_id)
    return {
        "course_id": course_id,
        "count": len(lessons),
        "lessons": [lesson.model_dump() for lesson in lessons],
    }


@app.get("/api/v1/lessons/{lesson_id}")
def get_lesson(
    lesson_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    lesson = _require_lesson(lesson_id, ctx)
    return lesson.model_dump()


@app.post("/api/v1/lessons/{lesson_id}/generate")
async def generate_lesson(
    lesson_id: str,
    req: LessonGenerateRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_lesson(lesson_id, ctx, "write")
    _guard_lock(lesson_id, ctx)
    payload = req or LessonGenerateRequest()
    _charge(ctx, "generate", 1, ref_id=lesson_id)
    try:
        result = await container.generation().generate_lesson(
            lesson_id,
            topic=payload.topic,
            top_k=payload.top_k,
            note=payload.note,
            source_ids=payload.source_ids,
            mode=payload.mode.value,
            expected_version=payload.expected_version,
            tenant_id=_tenant_of(ctx),
        )
    except LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"讲次不存在: {lesson_id}") from exc
    except VersionConflictError as exc:
        return _conflict(exc)
    return result.model_dump()


@app.get("/api/v1/lessons/{lesson_id}/versions")
def list_lesson_versions(
    lesson_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    lesson = _require_lesson(lesson_id, ctx)
    versions = container.course_repository().list_versions(lesson_id)
    return {
        "lesson_id": lesson_id,
        "current_version": lesson.current_version,
        "count": len(versions),
        "versions": [version.model_dump() for version in versions],
    }


@app.post("/api/v1/lessons/{lesson_id}/revert")
def revert_lesson(
    lesson_id: str,
    req: LessonRevertRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    lesson_now = _require_lesson(lesson_id, ctx, "write")
    _guard_lock(lesson_id, ctx)
    if req.expected_version is not None and int(req.expected_version) != lesson_now.current_version:
        return _conflict(
            VersionConflictError(int(req.expected_version), lesson_now.current_version)
        )
    repository = container.course_repository()
    if repository.get_version(lesson_id, req.version) is None:
        raise HTTPException(
            status_code=404, detail=f"版本不存在: {lesson_id} v{req.version}"
        )
    applied = repository.revert_to_version(lesson_id, req.version, note=req.note)
    if applied is None:
        raise HTTPException(status_code=404, detail=f"版本不存在: {lesson_id} v{req.version}")
    lesson, record = applied
    return {
        "lesson": lesson.model_dump(),
        "version": record.version,
        "reverted_from": req.version,
        "note": record.note,
    }


@app.post("/api/v1/lessons/{lesson_id}/ask")
async def ask_lesson(
    lesson_id: str, req: LessonAskRequest, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_lesson(lesson_id, ctx, "write")
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
    _charge(ctx, "ask", 1, ref_id=lesson_id)
    selection = (req.selection or "").strip() or None
    try:
        result = await container.conversation().ask(
            lesson_id, question, selection=selection
        )
    except LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"讲次不存在: {lesson_id}") from exc
    except EmptyLLMResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result.model_dump()


@app.post("/api/v1/lessons/{lesson_id}/amend")
async def amend_lesson(
    lesson_id: str,
    req: LessonAmendRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_lesson(lesson_id, ctx, "write")
    instruction = req.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="修改指令不能为空")
    _guard_lock(lesson_id, ctx)
    _charge(ctx, "amend", 1, ref_id=lesson_id)
    try:
        result = await container.conversation().amend(
            lesson_id,
            instruction,
            target=req.target,
            mode=req.mode.value,
            expected_version=req.expected_version,
        )
    except VersionConflictError as exc:
        return _conflict(exc)
    except LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"讲次不存在: {lesson_id}") from exc
    except LessonContentEmptyError as exc:
        raise HTTPException(
            status_code=400, detail=f"该讲尚无正文，无法局部修改: {lesson_id}"
        ) from exc
    except EmptyLLMResponseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return result.model_dump()


@app.post("/api/v1/lessons/{lesson_id}/drilldown")
async def drilldown_lesson(
    lesson_id: str,
    req: LessonDrilldownRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_lesson(lesson_id, ctx, "write")
    payload = req or LessonDrilldownRequest()
    try:
        result = await container.conversation().drilldown(
            lesson_id, message_id=payload.message_id, question=payload.question
        )
    except LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"讲次不存在: {lesson_id}") from exc
    except MessageNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=(
                "未找到可沉淀的追问回答，请先调用 ask 或指定有效的 message_id: "
                f"{payload.message_id or payload.question or lesson_id}"
            ),
        ) from exc
    return result.model_dump()


@app.get("/api/v1/lessons/{lesson_id}/thread")
def get_lesson_thread(
    lesson_id: str,
    limit: int | None = Query(default=None, ge=1, le=200),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_lesson(lesson_id, ctx)
    conversations = container.conversation_repository()
    thread = conversations.get_lesson_thread(lesson_id)
    if thread is None:
        empty = LessonThreadView(
            lesson_id=lesson_id, thread_id="", title="", message_count=0, messages=[]
        )
        return empty.model_dump()
    messages = conversations.list_messages(thread.id, limit=limit)
    view = LessonThreadView(
        lesson_id=lesson_id,
        thread_id=thread.id,
        title=thread.title,
        message_count=conversations.count_messages(thread.id),
        messages=messages,
    )
    payload = view.model_dump()
    payload["course_id"] = thread.course_id
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
        raise HTTPException(status_code=404, detail=f"对话线不存在: {thread_id}")
    _require_course(thread.course_id, ctx)
    messages = conversations.list_messages(thread.id, limit=limit)
    return {
        "thread": thread.model_dump(),
        "message_count": conversations.count_messages(thread.id),
        "returned_count": len(messages),
        "messages": [message.model_dump() for message in messages],
    }


class BlueprintGenerateRequest(BaseModel):
    mode: GenerationMode = GenerationMode.strict
    top_k: int | None = Field(default=None, ge=1, le=20)
    source_ids: list[str] | None = None
    focus: str = ""


class BlueprintSaveRequest(BaseModel):
    blueprint: CourseBlueprint
    expected_version: int | None = None


class GlossaryUpdateRequest(BaseModel):
    terms: list[GlossaryTerm] = Field(default_factory=list)


class LessonReviewRequest(BaseModel):
    action: Literal["approve", "request_revision"]
    note: str = ""


def _glossary_payload(course_id: str, blueprint: CourseBlueprint | None) -> dict[str, Any]:
    terms = blueprint.glossary if blueprint else []
    return {
        "course_id": course_id,
        "count": len(terms),
        "glossary": [term.model_dump() for term in terms],
    }


@app.get("/api/v1/courses/{course_id}/blueprint")
def get_course_blueprint(
    course_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_course(course_id, ctx)
    blueprint = container.blueprint().get_blueprint(course_id)
    return {
        "exists": blueprint is not None,
        "blueprint": blueprint.model_dump() if blueprint else None,
    }


@app.post("/api/v1/courses/{course_id}/blueprint/generate")
async def generate_course_blueprint(
    course_id: str,
    req: BlueprintGenerateRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    payload = req or BlueprintGenerateRequest()
    _require_course(course_id, ctx, "write")
    _charge(ctx, "blueprint", 1, ref_id=course_id)
    try:
        blueprint = await container.blueprint().generate(
            course_id,
            mode=payload.mode.value,
            top_k=payload.top_k,
            source_ids=payload.source_ids,
            focus=payload.focus,
            tenant_id=_tenant_of(ctx),
        )
    except NoEvidenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BlueprintParseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except BlueprintNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return blueprint.model_dump()


@app.put("/api/v1/courses/{course_id}/blueprint")
def save_course_blueprint(
    course_id: str,
    req: BlueprintSaveRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_course(course_id, ctx, "write")
    try:
        saved = container.blueprint().save_blueprint(
            course_id, req.blueprint, expected_version=req.expected_version
        )
    except BlueprintNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except VersionConflictError as exc:
        return _conflict(exc)
    return saved.model_dump()


@app.post("/api/v1/courses/{course_id}/blueprint/apply")
def apply_course_blueprint(
    course_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_course(course_id, ctx, "write")
    try:
        blueprint, created = container.blueprint().apply(course_id)
    except BlueprintNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "created_lessons": [lesson.model_dump() for lesson in created],
        "blueprint": blueprint.model_dump(),
        "created_count": len(created),
    }


@app.get("/api/v1/courses/{course_id}/glossary")
def get_course_glossary(
    course_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_course(course_id, ctx)
    blueprint = container.blueprint().get_blueprint(course_id)
    return _glossary_payload(course_id, blueprint)


@app.put("/api/v1/courses/{course_id}/glossary")
def update_course_glossary(
    course_id: str,
    req: GlossaryUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_course(course_id, ctx, "write")
    try:
        blueprint = container.blueprint().set_glossary(course_id, req.terms)
    except BlueprintNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _glossary_payload(course_id, blueprint)


@app.get("/api/v1/courses/{course_id}/progress")
def get_course_progress(
    course_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_course(course_id, ctx)
    return container.blueprint().progress(course_id)


@app.post("/api/v1/lessons/{lesson_id}/review")
def review_lesson(
    lesson_id: str,
    req: LessonReviewRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "review")
    _require_lesson(lesson_id, ctx)
    _guard_lock(lesson_id, ctx)
    try:
        lesson, review = container.blueprint().review_lesson(
            lesson_id, req.action, note=req.note
        )
    except LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"讲次不存在: {lesson_id}") from exc
    except LessonContentEmptyError as exc:
        raise HTTPException(
            status_code=400, detail=f"该讲尚无正文，无法通过审核: {lesson_id}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    progress = container.blueprint().progress(lesson.course_id)
    return {
        "lesson": lesson.model_dump(),
        "review": review.model_dump(),
        "course_progress": progress,
    }


@app.get("/api/v1/lessons/{lesson_id}/reviews")
def list_lesson_reviews(
    lesson_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_lesson(lesson_id, ctx)
    reviews = container.blueprint().list_reviews(lesson_id)
    return {
        "lesson_id": lesson_id,
        "count": len(reviews),
        "reviews": [review.model_dump() for review in reviews],
    }


def _auth_error(exc: Exception) -> HTTPException:
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
    if isinstance(exc, TenantNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@app.post("/api/v1/auth/register", status_code=201)
def auth_register(req: RegisterRequest) -> dict[str, Any]:
    service = container.auth_service()
    try:
        user, token = service.register(req.email, req.password, req.display_name)
    except (EmailAlreadyRegisteredError, ValueError) as exc:
        raise _auth_error(exc) from exc
    return {"token": token, "user": user.model_dump(), "tenants": service.tenants_payload(user)}


@app.post("/api/v1/auth/login")
def auth_login(req: LoginRequest) -> dict[str, Any]:
    service = container.auth_service()
    try:
        user, token = service.login(req.email, req.password)
    except InvalidCredentialsError as exc:
        raise _auth_error(exc) from exc
    return {"token": token, "user": user.model_dump(), "tenants": service.tenants_payload(user)}


@app.get("/api/v1/auth/me")
def auth_me(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    service = container.auth_service()
    return {
        "user": ctx.user.model_dump(),
        "tenant": ctx.tenant.model_dump(),
        "role": ctx.role_key or ctx.role,
        "role_key": ctx.role_key or ctx.role,
        "role_name": ctx.role_name,
        "actions": sorted(ctx.actions),
        "scope": ctx.scope,
        "tenants": service.tenants_payload(ctx.user),
        "auth_mode": service.mode,
    }


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
        tenant, role = service.create_tenant(ctx.user, req.name)
    except ValueError as exc:
        raise _auth_error(exc) from exc
    return {"tenant": tenant.model_dump(), "role": role}


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


class LessonLockRequest(BaseModel):
    force: bool = False


class LessonHeartbeatRequest(BaseModel):
    token: str = Field(min_length=1)


class QuotaUpdateRequest(BaseModel):
    monthly_generations: int = Field(ge=0)
    monthly_uploads: int = Field(ge=0)
    storage_bytes: int = Field(ge=0)


def _quota_payload(tenant_id: str) -> dict[str, Any]:
    service = container.quota_service()
    usage = service.usage(tenant_id)
    return {
        "tenant_id": tenant_id,
        "period": usage.period,
        "limits": service.limits(tenant_id).model_dump(),
        "usage": usage.model_dump(),
        "remaining": service.remaining(tenant_id),
    }


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


@app.get("/api/v1/lessons/{lesson_id}/lock")
def get_lesson_lock(
    lesson_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    _enforce(ctx, "read")
    _require_lesson(lesson_id, ctx)
    lock = container.lock_service().get(lesson_id)
    return {"lock": lock.model_dump() if lock else None}


@app.post("/api/v1/lessons/{lesson_id}/lock")
def acquire_lesson_lock(
    lesson_id: str,
    req: LessonLockRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
) -> Any:
    _enforce(ctx, "write")
    _require_lesson(lesson_id, ctx, "write")
    payload = req or LessonLockRequest()
    if payload.force and not _is_privileged(ctx):
        raise HTTPException(status_code=403, detail="仅管理员或所有者可强制接管编辑锁")
    try:
        lock = container.lock_service().acquire(
            lesson_id,
            _tenant_of(ctx),
            ctx.user.id,
            ctx.user.display_name or ctx.user.email,
            force=payload.force,
        )
    except LessonLockedError as exc:
        current = exc.lock
        return JSONResponse(
            status_code=409,
            content={
                "detail": f"该讲正被 {exc.name} 编辑",
                "lock": current.model_dump() if hasattr(current, "model_dump") else None,
            },
        )
    return {"acquired": True, "lock": lock.model_dump()}


@app.post("/api/v1/lessons/{lesson_id}/lock/heartbeat")
def heartbeat_lesson_lock(
    lesson_id: str,
    req: LessonHeartbeatRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_lesson(lesson_id, ctx, "write")
    try:
        lock = container.lock_service().heartbeat(lesson_id, req.token)
    except LessonLockLostError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"lock": lock.model_dump()}


@app.delete("/api/v1/lessons/{lesson_id}/lock")
def release_lesson_lock(
    lesson_id: str,
    token: str = Query(default=""),
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "write")
    _require_lesson(lesson_id, ctx, "write")
    try:
        container.lock_service().release(lesson_id, token)
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


def _grants_payload(course_id: str, grants) -> dict[str, Any]:
    return {
        "course_id": course_id,
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


@app.get("/api/v1/courses/{course_id}/grants")
def list_course_grants(
    course_id: str, ctx: AuthContext = Depends(get_auth_context)
) -> dict[str, Any]:
    service = container.auth_service()
    manage = service.can(ctx, "manage_members")
    if not manage:
        _enforce(ctx, "write")
    _require_course(course_id, ctx, "read" if manage else "write")
    grants = service.list_grants(_tenant_of(ctx), course_id)
    return _grants_payload(course_id, grants)


@app.put("/api/v1/courses/{course_id}/grants")
def replace_course_grants(
    course_id: str,
    req: GrantReplaceRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _enforce(ctx, "manage_members")
    _require_course(course_id, ctx)
    try:
        grants = container.auth_service().replace_grants(
            _tenant_of(ctx),
            course_id,
            [(item.user_id, item.level) for item in req.grants],
        )
    except (MembershipNotFoundError, ValueError) as exc:
        raise _role_error(exc) from exc
    return _grants_payload(course_id, grants)


@app.get("/api/v1/me/capabilities")
def my_capabilities(ctx: AuthContext = Depends(get_auth_context)) -> dict[str, Any]:
    return container.auth_service().capabilities(ctx)
