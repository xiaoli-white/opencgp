from __future__ import annotations

import json
import re
import time
from typing import Any, Mapping, Sequence

from app.models.blueprint import (
    CourseBlueprint,
    GlossaryTerm,
    LearningStage,
    LessonReview,
    OutlineNode,
)
from app.models.course import Course, Lesson
from app.models.generation import Evidence
from app.models.mode import GenerationMode
from app.ports.blueprint_repository import BlueprintRepository
from app.ports.course_repository import CourseRepository
from app.ports.llm import LLMProvider
from app.ports.vectorstore import VectorStore
from app.services.errors import (
    BlueprintNotFoundError,
    BlueprintParseError,
    LessonContentEmptyError,
    LessonNotFoundError,
    NoEvidenceError,
)

NO_EVIDENCE_MESSAGE = (
    "知识库中未检索到与课程主题相关的证据，严格模式无法生成蓝图；请先上传资料或改用 loose 模式"
)
PLACEHOLDER_WARNING = "未配置 LLM key，蓝图为占位规划"
LOOSE_WARNING = "非严格模式：蓝图由大模型基于自身知识规划，未经知识库证据核实"
REVIEW_APPROVE = "approve"
REVIEW_REQUEST_REVISION = "request_revision"
NODE_PLANNED = "planned"
NODE_GENERATED = "generated"
NODE_APPROVED = "approved"
LESSON_NEEDS_REVISION = "needs_revision"

_STOPWORDS = {
    "一个", "我们", "你们", "他们", "这个", "那个", "可以", "需要", "使用", "进行",
    "以及", "因为", "所以", "但是", "如果", "就是", "不是", "没有", "如何", "什么",
    "内容", "部分", "以下", "上面", "下面", "时候", "问题", "方式", "情况", "通过",
}


class BlueprintService:
    def __init__(
        self,
        repository: BlueprintRepository,
        course_repository: CourseRepository,
        vectorstore: VectorStore,
        llm: LLMProvider,
        default_top_k: int = 6,
        default_mode: str = "strict",
        max_evidence: int = 6,
        evidence_char_limit: int = 400,
    ) -> None:
        self.repository = repository
        self.course_repository = course_repository
        self.vectorstore = vectorstore
        self.llm = llm
        self.default_top_k = default_top_k
        self.default_mode = GenerationMode.normalize(default_mode).value
        self.max_evidence = max_evidence
        self.evidence_char_limit = evidence_char_limit

    async def generate(
        self,
        course_id: str,
        mode: str | None = None,
        top_k: int | None = None,
        source_ids: Sequence[str] | None = None,
        focus: str = "",
    ) -> CourseBlueprint:
        course = self.course_repository.get_course(course_id)
        if course is None:
            raise BlueprintNotFoundError(f"课程不存在: {course_id}")
        resolved_mode = GenerationMode.normalize(mode or self.default_mode)
        resolved_top_k = max(1, min(int(top_k or self.default_top_k), 20))
        citations = await self.vectorstore.search(
            self._build_query(course, focus),
            top_k=resolved_top_k,
            source_ids=source_ids,
        )
        citations = citations[: self.max_evidence]
        evidence = [
            Evidence(marker=f"E{index}", citation=citation)
            for index, citation in enumerate(citations, start=1)
        ]
        if resolved_mode is GenerationMode.strict and not evidence:
            raise NoEvidenceError(NO_EVIDENCE_MESSAGE)

        provider_name = type(self.llm).__name__
        if getattr(self.llm, "is_placeholder", False):
            blueprint = self._placeholder_blueprint(
                course, evidence, resolved_mode, provider_name
            )
        else:
            payload = await self._request_payload(course, evidence, resolved_mode, focus)
            blueprint = self._blueprint_from_payload(
                course, payload, evidence, resolved_mode, provider_name
            )
        return self.repository.save_blueprint(blueprint)

    def get_blueprint(self, course_id: str) -> CourseBlueprint | None:
        return self.repository.get_blueprint(course_id)

    def save_blueprint(self, course_id: str, blueprint: CourseBlueprint) -> CourseBlueprint:
        blueprint = blueprint.model_copy(update={"course_id": course_id})
        return self.repository.save_blueprint(blueprint)

    def apply(self, course_id: str) -> tuple[CourseBlueprint, list[Lesson]]:
        blueprint = self.repository.get_blueprint(course_id)
        if blueprint is None:
            raise BlueprintNotFoundError(f"课程蓝图不存在: {course_id}")
        if self.course_repository.get_course(course_id) is None:
            raise BlueprintNotFoundError(f"课程不存在: {course_id}")

        created: list[Lesson] = []
        for position, node in enumerate(blueprint.outline, start=1):
            lesson: Lesson | None = None
            if node.lesson_id:
                lesson = self.course_repository.get_lesson(node.lesson_id)
            if lesson is None:
                lesson = self.course_repository.create_lesson(
                    course_id=course_id,
                    title=node.title,
                    order_index=position,
                    learning_objectives=node.objectives,
                    prerequisites=node.prerequisites,
                    status=NODE_PLANNED,
                )
                created.append(lesson)
                node.lesson_id = lesson.id
            node.status = self._node_status_for_lesson(lesson)
        saved = self.repository.save_blueprint(blueprint)
        return saved, created

    def set_glossary(
        self, course_id: str, terms: Sequence[GlossaryTerm]
    ) -> CourseBlueprint:
        blueprint = self.repository.get_blueprint(course_id)
        if blueprint is None:
            raise BlueprintNotFoundError(f"课程蓝图不存在: {course_id}")
        blueprint.glossary = [
            term if isinstance(term, GlossaryTerm) else GlossaryTerm(**term)
            for term in terms
        ]
        return self.repository.save_blueprint(blueprint)

    def sync_statuses(self, course_id: str) -> CourseBlueprint:
        blueprint = self.repository.get_blueprint(course_id)
        if blueprint is None:
            raise BlueprintNotFoundError(f"课程蓝图不存在: {course_id}")
        for node in blueprint.outline:
            if not node.lesson_id:
                continue
            lesson = self.course_repository.get_lesson(node.lesson_id)
            if lesson is None:
                node.lesson_id = None
                node.status = NODE_PLANNED
                continue
            node.status = self._node_status_for_lesson(lesson)
        return self.repository.save_blueprint(blueprint)

    def review_lesson(
        self, lesson_id: str, action: str, note: str = ""
    ) -> tuple[Lesson, LessonReview]:
        lesson = self.course_repository.get_lesson(lesson_id)
        if lesson is None:
            raise LessonNotFoundError(lesson_id)
        resolved = (action or "").strip().lower()
        if resolved == REVIEW_APPROVE:
            if not lesson.content.strip():
                raise LessonContentEmptyError(lesson_id)
            status = NODE_APPROVED
            action_value = REVIEW_APPROVE
        elif resolved in (REVIEW_REQUEST_REVISION, "request-revision", "revision"):
            status = LESSON_NEEDS_REVISION
            action_value = REVIEW_REQUEST_REVISION
        else:
            raise ValueError(f"不支持的审核动作: {action!r}")

        updated = self.course_repository.update_lesson(lesson_id, status=status)
        assert updated is not None
        review = self.repository.add_review(
            lesson_id=lesson_id,
            action=action_value,
            note=note,
            version=lesson.current_version,
            status=status,
        )
        self._sync_node_status(lesson.course_id, lesson_id, status)
        return updated, review

    def list_reviews(self, lesson_id: str) -> list[LessonReview]:
        return self.repository.list_reviews(lesson_id)

    def progress(self, course_id: str) -> dict[str, Any]:
        lessons = self.course_repository.list_lessons(course_id)
        by_status: dict[str, int] = {}
        for lesson in lessons:
            by_status[lesson.status] = by_status.get(lesson.status, 0) + 1
        approved = by_status.get(NODE_APPROVED, 0)
        pending_review = sum(
            1
            for lesson in lessons
            if lesson.status != NODE_APPROVED and lesson.content.strip()
        )
        next_lesson_id: str | None = None
        for lesson in lessons:
            if lesson.status != NODE_APPROVED:
                next_lesson_id = lesson.id
                break
        blueprint = self.repository.get_blueprint(course_id)
        return {
            "course_id": course_id,
            "total": len(lessons),
            "by_status": by_status,
            "approved": approved,
            "pending_review": pending_review,
            "next_lesson_id": next_lesson_id,
            "blueprint_ready": bool(blueprint and blueprint.outline),
            "blueprint_version": blueprint.version if blueprint else 0,
        }

    def _sync_node_status(self, course_id: str, lesson_id: str, lesson_status: str) -> None:
        blueprint = self.repository.get_blueprint(course_id)
        if blueprint is None:
            return
        node_status = (
            NODE_APPROVED if lesson_status == NODE_APPROVED else NODE_GENERATED
        )
        changed = False
        for node in blueprint.outline:
            if node.lesson_id == lesson_id:
                node.status = node_status
                changed = True
        if changed:
            self.repository.save_blueprint(blueprint)

    @staticmethod
    def _node_status_for_lesson(lesson: Lesson) -> str:
        if lesson.status == NODE_APPROVED:
            return NODE_APPROVED
        if lesson.content.strip():
            return NODE_GENERATED
        return NODE_PLANNED

    def _build_query(self, course: Course, focus: str) -> str:
        parts = [course.title, course.subtitle, course.audience, focus]
        return " ".join(part.strip() for part in parts if part and part.strip())

    async def _request_payload(
        self,
        course: Course,
        evidence: Sequence[Evidence],
        mode: GenerationMode,
        focus: str,
    ) -> dict[str, Any]:
        prompt = self._build_prompt(course, evidence, mode, focus)
        raw = await self.llm.complete(prompt)
        payload = _extract_json(raw)
        if payload is None:
            retry = (
                prompt
                + "\n\n## 重要提醒\n上一次输出不是合法 JSON，无法解析。"
                "只输出合法 JSON 对象，不要输出代码块围栏或任何解释文字。"
            )
            raw = await self.llm.complete(retry)
            payload = _extract_json(raw)
        if payload is None:
            raise BlueprintParseError("模型返回的课程蓝图不是合法 JSON，无法解析")
        return payload

    def _build_prompt(
        self,
        course: Course,
        evidence: Sequence[Evidence],
        mode: GenerationMode,
        focus: str,
    ) -> str:
        lines: list[str] = [
            "你是资深课程架构师，负责为一门课程设计可执行的教学蓝图。",
            "",
            "## 课程信息",
            f"- 标题：{course.title}",
            f"- 副标题：{course.subtitle or '（无）'}",
            f"- 目标读者：{course.audience or '（未指定）'}",
            f"- 难度：{course.difficulty}",
            f"- 语言：{course.language}",
            f"- 额外关注点：{focus.strip() or '（无）'}",
            "",
            "## 生成模式",
        ]
        if mode is GenerationMode.strict:
            lines.extend(
                [
                    "strict（严格模式）硬约束：",
                    "1. overview 与每个 outline 节点的 summary 只能依据下方「证据」中的内容撰写。",
                    "2. 使用证据的段落必须标注来源标记，格式为 [E1]，多条写作 [E1][E2]。",
                    "3. 证据未覆盖的部分必须显式写明「资料不足：<缺口说明>」，禁止用常识补全。",
                ]
            )
        else:
            lines.extend(
                [
                    "loose（非严格模式）要求：",
                    "1. 允许基于通用知识与教学经验自由规划，不要求逐条引用证据。",
                    "2. overview 首行必须写「⚠️ 本蓝图由大模型编写，未经知识库证据核实」。",
                    "3. 对不确定的时效性内容标注「建议核实」，不要伪装成已核实事实。",
                ]
            )
        lines.extend(["", "## 证据"])
        if evidence:
            for item in evidence:
                snippet = (item.citation.text or item.citation.snippet).strip()
                if len(snippet) > self.evidence_char_limit:
                    snippet = snippet[: self.evidence_char_limit] + "…"
                lines.append(
                    f"[{item.marker}] 来源：{item.citation.source_name}"
                    f"｜片段 #{item.citation.chunk_index}"
                )
                lines.append(snippet)
                lines.append("")
        else:
            lines.extend(["（本次未检索到知识库证据）", ""])
        lines.extend(
            [
                "## 输出 JSON 结构",
                "{",
                '  "overview": "课程整体说明",',
                '  "learning_path": [',
                '    {"id": "stage-1", "title": "阶段名", "goal": "阶段目标",'
                ' "node_ids": ["node-1"], "estimated_minutes": 60}',
                "  ],",
                '  "outline": [',
                '    {"id": "node-1", "stage_id": "stage-1", "title": "讲次标题",'
                ' "summary": "讲次说明", "objectives": ["学习目标"],'
                ' "prerequisites": ["前置知识"], "estimated_minutes": 30}',
                "  ],",
                '  "glossary": [',
                '    {"term": "术语", "definition": "定义", "aliases": ["别名"],'
                ' "node_ids": ["node-1"]}',
                "  ]",
                "}",
                "",
                "## 结构约束",
                "1. learning_path 输出 4-8 个 stage，按学习顺序排列，id 形如 stage-1。",
                "2. 每个 stage 下 2-5 个 outline 节点，全课共 8-20 个节点，id 形如 node-1。",
                "3. 每个 outline 节点的 stage_id 必须引用已定义的 stage id。",
                "4. glossary 输出 6-12 条术语，term 不重复，node_ids 引用 outline 节点 id。",
                "5. 每个节点的 objectives 输出 2-3 条，prerequisites 可为空数组。",
                "",
                "## 输出",
                "只输出一个 JSON 对象，不要输出 markdown 代码块围栏，不要输出任何解释文字。",
            ]
        )
        return "\n".join(lines)

    def _blueprint_from_payload(
        self,
        course: Course,
        payload: Mapping[str, Any],
        evidence: Sequence[Evidence],
        mode: GenerationMode,
        provider_name: str,
    ) -> CourseBlueprint:
        stages = _parse_stages(payload.get("learning_path") or payload.get("stages"))
        nodes = _parse_nodes(payload.get("outline") or payload.get("nodes"))
        if not nodes:
            raise BlueprintParseError("模型返回的课程蓝图缺少 outline 节点，无法使用")
        _assign_stages(stages, nodes)
        terms = _parse_terms(payload.get("glossary"))
        if not terms:
            terms = self._placeholder_terms(course, evidence, [node.id for node in nodes])

        grounded = mode is GenerationMode.strict and bool(evidence)
        overview = _as_str(payload.get("overview"))
        if mode is GenerationMode.loose and "未经知识库证据核实" not in overview:
            overview = f"⚠️ 本蓝图由大模型编写，未经知识库证据核实\n\n{overview}".strip()

        return CourseBlueprint(
            course_id=course.id,
            overview=overview,
            mode=mode.value,
            grounded=grounded,
            learning_path=stages,
            outline=nodes,
            glossary=terms,
            provider=provider_name,
            warning="" if grounded else (LOOSE_WARNING if mode is GenerationMode.loose else ""),
            updated_at=time.time(),
        )

    def _placeholder_blueprint(
        self,
        course: Course,
        evidence: Sequence[Evidence],
        mode: GenerationMode,
        provider_name: str,
    ) -> CourseBlueprint:
        title = course.title
        stage_specs: list[tuple[str, str, str, list[tuple[str, str]]]] = [
            (
                "stage-1",
                "入门与全景",
                f"建立对「{title}」的整体认知与术语基础",
                [
                    (f"{title}：问题域与价值", f"说明「{title}」要解决的问题、适用场景与不适用场景。"),
                    ("核心概念与术语地图", f"梳理「{title}」的关键概念及其相互关系。"),
                    ("学习路径与前置条件", "明确学习顺序、所需基础与自检方式。"),
                ],
            ),
            (
                "stage-2",
                "核心机制",
                f"理解「{title}」的关键机制与典型工作流",
                [
                    ("关键机制拆解", "拆解核心机制的输入、处理过程与输出。"),
                    ("典型工作流", "走通一条从准备到交付的完整工作流。"),
                    ("常见误区与边界", "识别误用场景、失效边界与排查思路。"),
                ],
            ),
            (
                "stage-3",
                "实践与进阶",
                "把知识落到可运行产物并规划进阶方向",
                [
                    ("动手实践：最小可运行样例", "完成一个最小可运行样例并验证结果。"),
                    ("工程化落地与协作", "讨论可维护性、协作方式与质量保障。"),
                    ("进阶延伸与自测", "给出延伸方向与自测清单。"),
                ],
            ),
        ]

        node_index = 0
        nodes: list[OutlineNode] = []
        stages: list[LearningStage] = []
        for stage_id, stage_title, stage_goal, node_specs in stage_specs:
            stage_node_ids: list[str] = []
            for node_title, node_summary in node_specs:
                node_index += 1
                node_id = f"node-{node_index}"
                stage_node_ids.append(node_id)
                summary = node_summary
                if evidence:
                    marker = evidence[(node_index - 1) % len(evidence)].marker
                    summary = f"{node_summary}（参考证据 [{marker}]）"
                else:
                    summary = f"{node_summary}（资料不足：知识库暂无对应证据）"
                nodes.append(
                    OutlineNode(
                        id=node_id,
                        stage_id=stage_id,
                        title=node_title,
                        summary=summary,
                        objectives=[
                            f"能用自己的话解释「{node_title}」",
                            f"能判断「{title}」中与该主题相关的常见问题",
                        ],
                        prerequisites=[]
                        if stage_id == "stage-1"
                        else ["上一阶段的核心概念"],
                        estimated_minutes=30,
                        status=NODE_PLANNED,
                    )
                )
            stages.append(
                LearningStage(
                    id=stage_id,
                    title=stage_title,
                    goal=stage_goal,
                    node_ids=stage_node_ids,
                    estimated_minutes=90,
                )
            )

        term_source = (
            f"占位蓝图基于课程元数据与 {len(evidence)} 条证据规划，"
            if evidence
            else "占位蓝图仅基于课程元数据规划，"
        )
        overview = (
            f"⚠️ 本蓝图由大模型编写，未经知识库证据核实\n\n"
            if mode is GenerationMode.loose
            else ""
        ) + (
            f"{term_source}覆盖「{title}」从入门到实践的 {len(stages)} 个阶段、"
            f"{len(nodes)} 个讲次。目标读者：{course.audience or '未指定'}；难度：{course.difficulty}。"
        )
        glossary = self._placeholder_terms(
            course, evidence, [node.id for node in nodes]
        )
        warning = PLACEHOLDER_WARNING
        if mode is GenerationMode.loose:
            warning = f"{PLACEHOLDER_WARNING}；{LOOSE_WARNING}"
        return CourseBlueprint(
            course_id=course.id,
            overview=overview,
            mode=mode.value,
            grounded=mode is GenerationMode.strict and bool(evidence),
            learning_path=stages,
            outline=nodes,
            glossary=glossary,
            provider=provider_name,
            warning=warning,
            updated_at=time.time(),
        )

    def _placeholder_terms(
        self, course: Course, evidence: Sequence[Evidence], node_ids: Sequence[str]
    ) -> list[GlossaryTerm]:
        counts: dict[str, int] = {}
        for item in evidence:
            text = item.citation.text or item.citation.snippet
            for term, count in _candidate_counts(text).items():
                counts[term] = counts.get(term, 0) + count
        selected = _select_terms(counts, 6)
        if len(selected) < 6:
            meta = " ".join([course.title, course.subtitle, course.audience])
            for term in _metadata_terms(meta):
                if term in selected:
                    continue
                selected.append(term)
                if len(selected) >= 6:
                    break
        for fallback in ("核心概念", "工作流程", "常见误区", "实践路径"):
            if len(selected) >= 6:
                break
            if fallback not in selected:
                selected.append(fallback)

        terms: list[GlossaryTerm] = []
        for position, term in enumerate(selected[:6]):
            sources = sorted(
                {
                    item.citation.source_name
                    for item in evidence
                    if term in (item.citation.text or item.citation.snippet)
                }
            )
            definition = f"占位释义：与「{course.title}」相关的关键概念，待补充资料后定稿。"
            if sources:
                definition = f"{definition}出现于：{'、'.join(sources[:2])}。"
            terms.append(
                GlossaryTerm(
                    term=term,
                    definition=definition,
                    aliases=[],
                    node_ids=[node_ids[position % len(node_ids)]] if node_ids else [],
                )
            )
        return terms


def _parse_stages(raw: Any) -> list[LearningStage]:
    if not isinstance(raw, list):
        return []
    stages: list[LearningStage] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            continue
        stage_id = _as_str(item.get("id")) or f"stage-{index}"
        stages.append(
            LearningStage(
                id=stage_id,
                title=_as_str(item.get("title")) or f"阶段 {index}",
                goal=_as_str(item.get("goal")),
                node_ids=_as_str_list(item.get("node_ids")),
                estimated_minutes=_as_int(item.get("estimated_minutes")),
            )
        )
    return stages


def _parse_nodes(raw: Any) -> list[OutlineNode]:
    if not isinstance(raw, list):
        return []
    nodes: list[OutlineNode] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            continue
        node_id = _as_str(item.get("id")) or f"node-{index}"
        while node_id in seen:
            node_id = f"{node_id}-{index}"
        seen.add(node_id)
        title = _as_str(item.get("title"))
        if not title:
            continue
        nodes.append(
            OutlineNode(
                id=node_id,
                stage_id=_as_str(item.get("stage_id")),
                title=title,
                summary=_as_str(item.get("summary")),
                objectives=_as_str_list(item.get("objectives")),
                prerequisites=_as_str_list(item.get("prerequisites")),
                estimated_minutes=_as_int(item.get("estimated_minutes")),
                status=NODE_PLANNED,
            )
        )
    return nodes


def _parse_terms(raw: Any) -> list[GlossaryTerm]:
    if not isinstance(raw, list):
        return []
    terms: list[GlossaryTerm] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        term = _as_str(item.get("term"))
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(
            GlossaryTerm(
                term=term,
                definition=_as_str(item.get("definition")),
                aliases=_as_str_list(item.get("aliases")),
                node_ids=_as_str_list(item.get("node_ids")),
            )
        )
    return terms


def _assign_stages(stages: Sequence[LearningStage], nodes: Sequence[OutlineNode]) -> None:
    if not stages:
        return
    valid = {stage.id for stage in stages}
    for node in nodes:
        if node.stage_id and node.stage_id not in valid:
            node.stage_id = ""
    if any(not node.stage_id for node in nodes):
        per_stage = max(1, -(-len(nodes) // len(stages)))
        for position, node in enumerate(nodes):
            if node.stage_id:
                continue
            node.stage_id = stages[min(position // per_stage, len(stages) - 1)].id
    for stage in stages:
        if not stage.node_ids:
            stage.node_ids = [node.id for node in nodes if node.stage_id == stage.id]


def _extract_json(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1:
        return None
    candidate = text[start : end + 1] if end > start else text[start:]
    for attempt in (candidate, _repair_json(candidate)):
        try:
            payload = json.loads(attempt)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _repair_json(text: str) -> str:
    repaired = re.sub(r",\s*([}\]])", r"\1", text)
    repaired = re.sub(r"[\x00-\x1f](?![\n\r\t])", " ", repaired)
    missing_brackets = repaired.count("[") - repaired.count("]")
    missing_braces = repaired.count("{") - repaired.count("}")
    repaired += "]" * max(0, missing_brackets)
    repaired += "}" * max(0, missing_braces)
    return repaired


def _candidate_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    source = text or ""
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_.\-]{2,}", source):
        counts[word] = counts.get(word, 0) + 1
    for run in re.findall(r"[\u4e00-\u9fa5]+", source):
        for size in (2, 3, 4):
            for start in range(len(run) - size + 1):
                gram = run[start : start + size]
                if gram in _STOPWORDS:
                    continue
                counts[gram] = counts.get(gram, 0) + 1
    return counts


def _select_terms(counts: Mapping[str, int], limit: int) -> list[str]:
    scored: list[tuple[str, float]] = []
    for term, count in counts.items():
        if len(term) < 2:
            continue
        is_ascii = term.isascii()
        if count < 2 and not is_ascii:
            continue
        weight = 2.0 if is_ascii else float(min(len(term), 4))
        scored.append((term, count * weight))
    scored.sort(key=lambda item: (-item[1], -counts[item[0]], item[0]))
    selected: list[str] = []
    for term, _ in scored:
        if any(term in existing or existing in term for existing in selected):
            continue
        selected.append(term)
        if len(selected) >= limit:
            break
    return selected


def _metadata_terms(text: str) -> list[str]:
    terms: list[str] = []
    for segment in re.split(r"[，,、。;；/\|·\s]+", text or ""):
        cleaned = segment.strip().lstrip("与和及或的")
        if 2 <= len(cleaned) <= 10:
            terms.append(cleaned)
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_.\-]{2,}", text or ""):
        if word not in terms:
            terms.append(word)
    return terms


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_as_str(item) for item in value if _as_str(item)]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,，;；\n]", value) if item.strip()]
    return []
