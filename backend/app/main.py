"""FastAPI 应用入口。

提供健康检查端点 ``/health``、LLM 生成端点与 RAG 知识库端点，
并装配 Port/Adapter 容器。
启动方式（M0 单机）：:

    cd backend
    uvicorn app.main:app --port 8000
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.container import get_container
from app.models.citation import Citation
from app.models.blueprint import CourseBlueprint, GlossaryTerm
from app.models.course import Course, Lesson
from app.models.mode import GenerationMode
from app.models.thread import LessonThreadView
from app.services.errors import (
    BlueprintNotFoundError,
    BlueprintParseError,
    EmptyLLMResponseError,
    LessonContentEmptyError,
    LessonNotFoundError,
    MessageNotFoundError,
    NoEvidenceError,
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
) -> dict[str, Any]:
    data = await file.read()
    filename = file.filename or "upload.bin"
    try:
        result = await container.ingest().ingest_bytes(
            data, filename, source_name=source_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.model_dump()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    source_ids: list[str] | None = None


@app.post("/api/v1/kb/search")
async def kb_search(req: SearchRequest) -> dict[str, Any]:
    citations: list[Citation] = await container.ingest().search(
        req.query, top_k=req.top_k, source_ids=req.source_ids
    )
    return {
        "query": req.query,
        "top_k": req.top_k,
        "count": len(citations),
        "citations": [citation.model_dump() for citation in citations],
    }


@app.delete("/api/v1/kb/sources/{source_id}")
async def kb_delete_source(source_id: str) -> dict[str, Any]:
    removed = await container.ingest().delete_source(source_id)
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


class LessonRevertRequest(BaseModel):
    version: int = Field(ge=1)
    note: str = ""


class LessonAskRequest(BaseModel):
    question: str = Field(min_length=1)
    selection: str | None = None


class LessonAmendRequest(BaseModel):
    instruction: str = Field(min_length=1)
    target: str | None = None
    mode: GenerationMode = GenerationMode.strict


class LessonDrilldownRequest(BaseModel):
    message_id: str | None = None
    question: str | None = None


def _require_course(course_id: str) -> Course:
    course = container.course_repository().get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"课程不存在: {course_id}")
    return course


def _require_lesson(lesson_id: str) -> Lesson:
    lesson = container.course_repository().get_lesson(lesson_id)
    if lesson is None:
        raise HTTPException(status_code=404, detail=f"讲次不存在: {lesson_id}")
    return lesson


@app.post("/api/v1/courses", status_code=201)
def create_course(req: CourseCreateRequest) -> dict[str, Any]:
    course = container.course_repository().create_course(
        title=req.title,
        subtitle=req.subtitle,
        audience=req.audience,
        difficulty=req.difficulty,
        language=req.language,
    )
    return course.model_dump()


@app.get("/api/v1/courses")
def list_courses() -> dict[str, Any]:
    courses = container.course_repository().list_courses()
    return {"count": len(courses), "courses": [course.model_dump() for course in courses]}


@app.get("/api/v1/courses/{course_id}")
def get_course(course_id: str) -> dict[str, Any]:
    course = _require_course(course_id)
    lessons = container.course_repository().list_lessons(course_id)
    return {
        "course": course.model_dump(),
        "lesson_count": len(lessons),
        "lessons": [lesson.model_dump() for lesson in lessons],
        "progress": container.blueprint().progress(course_id),
    }


@app.post("/api/v1/courses/{course_id}/lessons", status_code=201)
def create_lesson(course_id: str, req: LessonCreateRequest) -> dict[str, Any]:
    _require_course(course_id)
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
def list_lessons(course_id: str) -> dict[str, Any]:
    _require_course(course_id)
    lessons = container.course_repository().list_lessons(course_id)
    return {
        "course_id": course_id,
        "count": len(lessons),
        "lessons": [lesson.model_dump() for lesson in lessons],
    }


@app.get("/api/v1/lessons/{lesson_id}")
def get_lesson(lesson_id: str) -> dict[str, Any]:
    lesson = _require_lesson(lesson_id)
    return lesson.model_dump()


@app.post("/api/v1/lessons/{lesson_id}/generate")
async def generate_lesson(
    lesson_id: str, req: LessonGenerateRequest | None = None
) -> dict[str, Any]:
    payload = req or LessonGenerateRequest()
    try:
        result = await container.generation().generate_lesson(
            lesson_id,
            topic=payload.topic,
            top_k=payload.top_k,
            note=payload.note,
            source_ids=payload.source_ids,
            mode=payload.mode.value,
        )
    except LessonNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"讲次不存在: {lesson_id}") from exc
    return result.model_dump()


@app.get("/api/v1/lessons/{lesson_id}/versions")
def list_lesson_versions(lesson_id: str) -> dict[str, Any]:
    lesson = _require_lesson(lesson_id)
    versions = container.course_repository().list_versions(lesson_id)
    return {
        "lesson_id": lesson_id,
        "current_version": lesson.current_version,
        "count": len(versions),
        "versions": [version.model_dump() for version in versions],
    }


@app.post("/api/v1/lessons/{lesson_id}/revert")
def revert_lesson(lesson_id: str, req: LessonRevertRequest) -> dict[str, Any]:
    _require_lesson(lesson_id)
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
async def ask_lesson(lesson_id: str, req: LessonAskRequest) -> dict[str, Any]:
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
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
async def amend_lesson(lesson_id: str, req: LessonAmendRequest) -> dict[str, Any]:
    instruction = req.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="修改指令不能为空")
    try:
        result = await container.conversation().amend(
            lesson_id, instruction, target=req.target, mode=req.mode.value
        )
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
    lesson_id: str, req: LessonDrilldownRequest | None = None
) -> dict[str, Any]:
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
    lesson_id: str, limit: int | None = Query(default=None, ge=1, le=200)
) -> dict[str, Any]:
    _require_lesson(lesson_id)
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
def get_thread(thread_id: str, limit: int | None = Query(default=None, ge=1, le=200)) -> dict[str, Any]:
    conversations = container.conversation_repository()
    thread = conversations.get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=f"对话线不存在: {thread_id}")
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
def get_course_blueprint(course_id: str) -> dict[str, Any]:
    _require_course(course_id)
    blueprint = container.blueprint().get_blueprint(course_id)
    return {
        "exists": blueprint is not None,
        "blueprint": blueprint.model_dump() if blueprint else None,
    }


@app.post("/api/v1/courses/{course_id}/blueprint/generate")
async def generate_course_blueprint(
    course_id: str, req: BlueprintGenerateRequest | None = None
) -> dict[str, Any]:
    payload = req or BlueprintGenerateRequest()
    _require_course(course_id)
    try:
        blueprint = await container.blueprint().generate(
            course_id,
            mode=payload.mode.value,
            top_k=payload.top_k,
            source_ids=payload.source_ids,
            focus=payload.focus,
        )
    except NoEvidenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BlueprintParseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except BlueprintNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return blueprint.model_dump()


@app.put("/api/v1/courses/{course_id}/blueprint")
def save_course_blueprint(course_id: str, req: BlueprintSaveRequest) -> dict[str, Any]:
    _require_course(course_id)
    try:
        saved = container.blueprint().save_blueprint(course_id, req.blueprint)
    except BlueprintNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return saved.model_dump()


@app.post("/api/v1/courses/{course_id}/blueprint/apply")
def apply_course_blueprint(course_id: str) -> dict[str, Any]:
    _require_course(course_id)
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
def get_course_glossary(course_id: str) -> dict[str, Any]:
    _require_course(course_id)
    blueprint = container.blueprint().get_blueprint(course_id)
    return _glossary_payload(course_id, blueprint)


@app.put("/api/v1/courses/{course_id}/glossary")
def update_course_glossary(course_id: str, req: GlossaryUpdateRequest) -> dict[str, Any]:
    _require_course(course_id)
    try:
        blueprint = container.blueprint().set_glossary(course_id, req.terms)
    except BlueprintNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _glossary_payload(course_id, blueprint)


@app.get("/api/v1/courses/{course_id}/progress")
def get_course_progress(course_id: str) -> dict[str, Any]:
    _require_course(course_id)
    return container.blueprint().progress(course_id)


@app.post("/api/v1/lessons/{lesson_id}/review")
def review_lesson(lesson_id: str, req: LessonReviewRequest) -> dict[str, Any]:
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
def list_lesson_reviews(lesson_id: str) -> dict[str, Any]:
    _require_lesson(lesson_id)
    reviews = container.blueprint().list_reviews(lesson_id)
    return {
        "lesson_id": lesson_id,
        "count": len(reviews),
        "reviews": [review.model_dump() for review in reviews],
    }
