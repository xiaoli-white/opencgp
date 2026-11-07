from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)

MAX_OBJECTIVE_CHARS = 180
MAX_GAP_CHARS = 220

GAP_MARKERS = (
    "insufficient material",
    "no evidence",
    "not covered by evidence",
    "not supported by evidence",
    "cannot be determined from the evidence",
    "cannot be written from evidence",
    "无法覆盖",
    "未被证据覆盖",
    "证据未覆盖",
    "证据不足",
    "没有证据",
    "无证据",
    "材料不足",
    "缺乏证据",
    "无法确定",
)

_TEMPLATE_MARKERS = (
    "<title>",
    "<chapter title>",
    "<stage title>",
    "<stage goal>",
    "<node title>",
    "<unit title>",
    "讲 title",
    "章 title",
    "节 title",
    "chapter title",
    "stage title",
    "stage goal",
    "node title",
    "unit title",
    "learning objective",
)

_CJK = re.compile(r"[\u3400-\u9fff]")
_SENTENCE_END = re.compile(r"[。\n；;]")
_WHITESPACE = re.compile(r"\s+")


@dataclass
class GuardOutcome:
    values: list[str] = field(default_factory=list)
    rejections: list[dict[str, str]] = field(default_factory=list)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return _WHITESPACE.sub(" ", str(value)).strip()


def _clip(text: str, limit: int = MAX_OBJECTIVE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def gap_marker(value: Any) -> str:
    lowered = _text(value).casefold()
    if not lowered:
        return ""
    for marker in GAP_MARKERS:
        if marker in lowered:
            return marker
    return ""


def has_gap_marker(value: Any) -> bool:
    return bool(gap_marker(value))


def is_template_value(value: Any) -> bool:
    text = _text(value).casefold()
    if not text:
        return True
    return any(marker in text for marker in _TEMPLATE_MARKERS)


def clean_label(value: Any, fallback: str) -> str:
    text = _text(value).strip(" \t:：;；,，.。、|/\\-—–_·•<>[]{}\"'“”‘’")
    if not text or has_gap_marker(text) or is_template_value(text):
        return fallback
    return _clip(text, 80)


def extract_gaps(content: Any, limit: int = 5) -> list[str]:
    text = _text(content)
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for line in str(content).splitlines():
        stripped_line = line.strip().lstrip("-*+># ").strip()
        if not stripped_line:
            continue
        for sentence in _SENTENCE_END.split(stripped_line):
            sentence = sentence.strip(" \t-—:：")
            if not sentence:
                continue
            lowered = sentence.casefold()
            starts_with_marker = any(lowered.startswith(marker) for marker in GAP_MARKERS)
            starts_with_gap_label = lowered.startswith(("证据缺口", "无法覆盖", "证据不足"))
            if not starts_with_marker and not starts_with_gap_label:
                continue
            if lowered in ("证据缺口", "无法覆盖", "证据不足"):
                continue
            if "<gap description>" in lowered or "<缺口描述>" in sentence:
                continue
            for marker in GAP_MARKERS:
                if lowered.startswith(marker):
                    sentence = sentence[len(marker):].lstrip(" \t:：-—")
                    break
            if not sentence:
                continue
            snippet = _clip(sentence, MAX_GAP_CHARS)
            key = snippet.casefold()
            if key in seen:
                continue
            seen.add(key)
            found.append(snippet)
            if len(found) >= limit:
                return found
    return found


def _style(language: str, *values: str) -> str:
    if (language or "").casefold().startswith("zh"):
        return "zh"
    return "zh" if any(_CJK.search(value or "") for value in values) else "en"


def derive_objectives(
    *,
    series_title: str,
    node_title: str,
    stage_title: str = "",
    stage_goal: str = "",
    node_position: int = 1,
    stage_position: int = 1,
    language: str = "",
) -> list[str]:
    style = _style(language, series_title, node_title, stage_title, stage_goal)
    position = max(1, int(node_position or 1))
    stage_index = max(1, int(stage_position or 1))
    fallback_node = f"第 {position} 讲" if style == "zh" else f"lesson {position}"
    fallback_stage = f"第 {stage_index} 阶段" if style == "zh" else f"stage {stage_index}"
    fallback_topic = "本课程" if style == "zh" else "this course"
    topic = clean_label(series_title, fallback_topic)
    label = clean_label(node_title, fallback_node)
    stage_label = clean_label(stage_title, "") or clean_label(stage_goal, fallback_stage)
    stage_label = _clip(stage_label, 40)
    goal_text = clean_label(stage_goal, "")
    goal_clause = _clip(re.split(r"[，,；;]", goal_text, maxsplit=1)[0], 36) if goal_text else ""
    if style == "zh":
        # A stage label that only repeats the series topic or an ordinal adds
        # nothing; drop it instead of nesting the topic twice in one sentence.
        stage_core = stage_label
        for token in (topic, label):
            if token:
                stage_core = stage_core.replace(token, "")
        stage_core = stage_core.strip(" 「」·:：，,、-—")
        if stage_core and not re.fullmatch(r"第\s*\d+\s*(?:阶段|讲|章|节)", stage_core):
            stage_phrase = f"「{stage_label}」"
        else:
            stage_phrase = ""
        values = [
            (
                f"能够说明「{label}」在{stage_phrase}中要解决的问题，并判断其适用边界。"
                if stage_phrase
                else f"能够说明「{label}」要解决的问题，并判断其适用边界。"
            ),
            f"能够用自己的话解释「{label}」的核心概念，并给出一个具体应用例子。",
            (
                f"能够围绕{stage_phrase}的阶段目标（{goal_clause}）完成「{label}」的自测，并记录尚未弄清的问题。"
                if goal_clause and stage_phrase
                else f"能够完成「{label}」的自测，并记录尚未弄清的问题。"
            ),
        ]
    else:
        values = [
            f"Can explain the problem \"{label}\" addresses in the {stage_label} stage of \"{topic}\" and judge where it applies.",
            f"Can describe the core concepts of \"{label}\" in one's own words and give a concrete example.",
            (
                f"Can complete the self-check for \"{label}\" against the stage goal ({goal_clause}) and record open questions."
                if goal_clause
                else f"Can complete the self-check for \"{label}\" against the stage goal and record open questions."
            ),
        ]
    return [_clip(value) for value in values]


def _with_position(value: str, position: int, style: str) -> str:
    suffix = f"（第 {position} 讲）" if style == "zh" else f" (unit {position})"
    if value.endswith("。"):
        return _clip(f"{value[:-1]}{suffix}。")
    if value.endswith("."):
        return _clip(f"{value[:-1]}{suffix}.")
    return _clip(f"{value}{suffix}")


def _append_unique(
    values: list[str],
    seen: set[str],
    candidate: str,
    position: int,
    style: str,
) -> bool:
    text = _clip(candidate)
    key = text.casefold()
    if not text or key in seen:
        return False
    seen.add(key)
    values.append(text)
    return True


def sanitize_objectives(
    raw: Any,
    *,
    series_title: str,
    node_title: str,
    stage_title: str = "",
    stage_goal: str = "",
    node_position: int = 1,
    stage_position: int = 1,
    language: str = "",
    reserved: set[str] | None = None,
    force_regenerate: bool = False,
) -> GuardOutcome:
    reserved = reserved or set()
    outcome = GuardOutcome()
    raw_items = list(raw) if isinstance(raw, (list, tuple)) else []
    if not force_regenerate:
        seen: set[str] = set()
        for item in raw_items:
            text = _text(item)
            if not text:
                continue
            marker = gap_marker(text)
            if marker:
                outcome.rejections.append(
                    {"field": "objectives", "reason": "gap_marker", "marker": marker, "value": text}
                )
                continue
            key = text.casefold()
            if key in seen:
                outcome.rejections.append(
                    {"field": "objectives", "reason": "duplicate", "marker": "", "value": text}
                )
                continue
            if key in reserved:
                outcome.rejections.append(
                    {"field": "objectives", "reason": "series_duplicate", "marker": "", "value": text}
                )
                continue
            seen.add(key)
            outcome.values.append(_clip(text))
            if len(outcome.values) >= 3:
                break
    else:
        for item in raw_items:
            marker = gap_marker(item)
            if marker:
                outcome.rejections.append(
                    {"field": "objectives", "reason": "gap_marker", "marker": marker, "value": _text(item)}
                )

    style = _style(language, series_title, node_title, stage_title, stage_goal)
    derived = derive_objectives(
        series_title=series_title,
        node_title=node_title,
        stage_title=stage_title,
        stage_goal=stage_goal,
        node_position=node_position,
        stage_position=stage_position,
        language=language,
    )
    seen = {value.casefold() for value in outcome.values}
    for candidate in derived:
        if len(outcome.values) >= 2:
            break
        if candidate.casefold() in reserved:
            continue
        _append_unique(outcome.values, seen, candidate, node_position, style)
    for candidate in derived:
        if len(outcome.values) >= 2:
            break
        _append_unique(
            outcome.values,
            seen,
            _with_position(candidate, node_position, style),
            node_position,
            style,
        )
    return outcome


def derive_prerequisites(
    *,
    series_title: str,
    stage_title: str = "",
    stage_goal: str = "",
    node_position: int = 1,
    language: str = "",
) -> list[str]:
    style = _style(language, series_title, stage_title, stage_goal)
    topic = clean_label(series_title, "本课程" if style == "zh" else "this course")
    if style == "zh":
        return [f"已掌握「{topic}」的基础概念和学习前提"]
    return [f"Basic concepts and prerequisites of \"{topic}\""]


def sanitize_prerequisites(
    raw: Any,
    *,
    series_title: str,
    stage_title: str = "",
    stage_goal: str = "",
    node_position: int = 1,
    language: str = "",
) -> GuardOutcome:
    outcome = GuardOutcome()
    raw_items = list(raw) if isinstance(raw, (list, tuple)) else []
    seen: set[str] = set()
    had_text = False
    for item in raw_items:
        text = _text(item)
        if not text:
            continue
        had_text = True
        marker = gap_marker(text)
        if marker:
            outcome.rejections.append(
                {"field": "prerequisites", "reason": "gap_marker", "marker": marker, "value": text}
            )
            continue
        key = text.casefold()
        if key in seen:
            outcome.rejections.append(
                {"field": "prerequisites", "reason": "duplicate", "marker": "", "value": text}
            )
            continue
        seen.add(key)
        outcome.values.append(_clip(text))
    if had_text and not outcome.values:
        derived = derive_prerequisites(
            series_title=series_title,
            stage_title=stage_title,
            stage_goal=stage_goal,
            node_position=node_position,
            language=language,
        )
        for candidate in derived:
            _append_unique(outcome.values, seen, candidate, node_position, _style(language, series_title))
    return outcome


def sanitize_blueprint_nodes(
    nodes: Sequence[Any],
    stages: Sequence[Any],
    *,
    series_title: str,
    language: str = "",
) -> list[dict[str, str]]:
    stage_positions = {
        getattr(stage, "id", ""): index
        for index, stage in enumerate(stages, start=1)
    }
    stage_map = {
        getattr(stage, "id", ""): stage
        for stage in stages
        if getattr(stage, "id", "")
    }
    reserved: set[str] = set()
    rejections: list[dict[str, str]] = []
    global_position = 0
    for node in nodes:
        stage = stage_map.get(getattr(node, "stage_id", ""))
        stage_title = getattr(stage, "title", "") if stage is not None else ""
        stage_goal = getattr(stage, "goal", "") if stage is not None else ""
        stage_position = stage_positions.get(getattr(node, "stage_id", ""), 1)
        global_position += 1
        objectives = sanitize_objectives(
            getattr(node, "objectives", []),
            series_title=series_title,
            node_title=getattr(node, "title", ""),
            stage_title=stage_title,
            stage_goal=stage_goal,
            node_position=global_position,
            stage_position=stage_position,
            language=language,
            reserved=reserved,
        )
        for rejection in objectives.rejections:
            rejection["node_id"] = getattr(node, "id", "")
            rejections.append(rejection)
            logger.warning(
                "objective guard rejected %s on node %s: %s",
                rejection["reason"],
                rejection.get("node_id", ""),
                rejection.get("value", "")[:120],
            )
        prerequisites = sanitize_prerequisites(
            getattr(node, "prerequisites", []),
            series_title=series_title,
            stage_title=stage_title,
            stage_goal=stage_goal,
            node_position=global_position,
            language=language,
        )
        for rejection in prerequisites.rejections:
            rejection["node_id"] = getattr(node, "id", "")
            rejections.append(rejection)
            logger.warning(
                "objective guard rejected %s on node %s: %s",
                rejection["reason"],
                rejection.get("node_id", ""),
                rejection.get("value", "")[:120],
            )
        node.objectives = list(objectives.values)
        node.prerequisites = list(prerequisites.values)
        reserved.update(value.casefold() for value in node.objectives)
    return rejections


def guard_unit_dicts(
    payloads: Sequence[Mapping[str, Any]],
    *,
    series_title: str,
    language: str = "",
    blueprint: Any = None,
) -> list[dict[str, Any]]:
    nodes = list(getattr(blueprint, "outline", []) or [])
    stages = list(getattr(blueprint, "learning_path", []) or [])
    node_by_unit = {
        getattr(node, "unit_id", ""): node
        for node in nodes
        if getattr(node, "unit_id", "")
    }
    stage_positions = {
        getattr(stage, "id", ""): index
        for index, stage in enumerate(stages, start=1)
    }
    stage_map = {
        getattr(stage, "id", ""): stage
        for stage in stages
        if getattr(stage, "id", "")
    }
    reserved: set[str] = set()
    guarded: list[dict[str, Any]] = []
    for position, payload in enumerate(payloads, start=1):
        item = dict(payload)
        node = node_by_unit.get(str(item.get("id") or ""))
        stage = stage_map.get(getattr(node, "stage_id", "")) if node is not None else None
        node_title = getattr(node, "title", "") or str(item.get("title") or "")
        stage_title = getattr(stage, "title", "") if stage is not None else ""
        stage_goal = getattr(stage, "goal", "") if stage is not None else ""
        stage_position = stage_positions.get(getattr(node, "stage_id", ""), 1) if node is not None else 1
        unit_position = int(item.get("order_index") or position)
        raw_objectives = item.get("learning_objectives") or []
        force = any(has_gap_marker(value) for value in raw_objectives)
        objectives = sanitize_objectives(
            raw_objectives,
            series_title=series_title,
            node_title=node_title,
            stage_title=stage_title,
            stage_goal=stage_goal,
            node_position=unit_position,
            stage_position=stage_position,
            language=language,
            reserved=reserved,
            force_regenerate=force,
        )
        prerequisites = sanitize_prerequisites(
            item.get("prerequisites") or [],
            series_title=series_title,
            stage_title=stage_title,
            stage_goal=stage_goal,
            node_position=unit_position,
            language=language,
        )
        item["learning_objectives"] = list(objectives.values)
        item["prerequisites"] = list(prerequisites.values)
        item["evidence_gaps"] = extract_gaps(item.get("content") or "")
        reserved.update(value.casefold() for value in item["learning_objectives"])
        guarded.append(item)
    return guarded
