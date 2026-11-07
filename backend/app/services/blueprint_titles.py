from __future__ import annotations

import re
from typing import Any, Callable, Mapping, MutableMapping

from app.models.blueprint import SeriesBlueprint

MAX_TITLE_CHARS = 80
MAX_STAGE_TITLE_CHARS = 60
MAX_OBJECTIVE_CHARS = 160

_GAP_MARKERS = (
    "insufficient material",
    "not covered by evidence",
    "no evidence",
    "无法覆盖",
    "证据不足",
)

_TEMPLATE_VALUES = frozenset(
    {
        "title",
        "chapter title",
        "stage title",
        "stage name",
        "stage goal",
        "node title",
        "unit title",
        "learning objective",
        "objective",
        "prerequisite",
        "term",
        "definition",
        "alias",
        "chapter summary",
        "章节标题",
        "阶段标题",
        "阶段名称",
        "节点标题",
        "单元标题",
        "学习目标",
        "前置知识",
        "术语",
        "定义",
    }
)

_TEMPLATE_PATTERNS = (
    re.compile(r"<[^<>]{0,40}>"),
    re.compile(r"(?:讲|章|节)\s*title", re.IGNORECASE),
    re.compile(
        r"\b(?:chapter|stage|node|unit|section)\s+(?:title|name|goal)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:第\s*\d+\s*[讲章节]|part\s*\d+|chapter\s*\d+|stage\s*\d+)\s*[:：]?$",
        re.IGNORECASE,
    ),
)

_EDGE_PUNCTUATION = " \t\r\n:：;；,，.。、|/\\-—–_·•<>[]{}\"'“”‘’"
_STAGE_PREFIX = re.compile(
    r"^(?:第\s*\d+\s*[阶段讲章节]|stage\s*\d+|part\s*\d+)\s*[:：\-—]\s*",
    re.IGNORECASE,
)
_CJK = re.compile(r"[\u3400-\u9fff]")
# A bare ordinal such as "第2阶段" or "Stage 2" adds nothing to a title.
_ORDINAL_ONLY = re.compile(
    r"^(?:第\s*\d+\s*(?:阶段|讲|章|节)|stage\s*\d+|part\s*\d+)$", re.IGNORECASE
)
_STARTS_WITH_GAP = re.compile(
    r"^[\s\"'“”‘’(\[]*(?:insufficient material|not covered by evidence|no evidence|无法覆盖|证据不足)",
    re.IGNORECASE,
)


def _starts_with_gap_marker(text: str) -> bool:
    return bool(_STARTS_WITH_GAP.match(text or ""))


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _style_for(topic: str) -> str:
    return "zh" if _CJK.search(topic or "") else "en"


def clean_title(value: Any) -> str:
    text = re.sub(r"\s+", " ", _text(value))
    text = re.sub(r"^[<>\[\]{}\"']+|[<>\[\]{}\"']+$", "", text)
    return text.strip(_EDGE_PUNCTUATION)


def is_placeholder_value(value: Any, mention_ok: bool = False) -> bool:
    text = _text(value)
    if not text:
        return True
    lowered = text.casefold()
    if any(marker in lowered for marker in _GAP_MARKERS):
        if not mention_ok or _starts_with_gap_marker(text):
            return True
    compact = re.sub(r"\s+", " ", lowered).strip(" :：-—·|/")
    if compact in _TEMPLATE_VALUES:
        return True
    return any(pattern.search(text) for pattern in _TEMPLATE_PATTERNS)


def _clip(text: str, limit: int) -> str:
    if limit <= 1:
        return text[:limit]
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _topic_core(topic: str, style: str) -> str:
    text = clean_title(topic)
    if not text:
        return "未命名课程" if style == "zh" else "Untitled course"
    return _clip(text, 40)


def _stage_phrase(
    goal: Any, stage_title: Any, position: int, style: str, topic: str = ""
) -> str:
    topic_key = clean_title(topic).casefold()
    for candidate in (goal, stage_title):
        if is_placeholder_value(candidate):
            continue
        text = clean_title(candidate)
        text = _STAGE_PREFIX.sub("", text).strip(_EDGE_PUNCTUATION)
        if not text:
            continue
        if topic_key and topic_key in text.casefold():
            continue
        return _clip(text, 28)
    position = max(1, int(position or 1))
    return f"第{position}阶段" if style == "zh" else f"Stage {position}"


def derive_node_title(
    topic: str,
    index: int,
    stage_goal: Any = "",
    stage_title: Any = "",
    stage_position: int = 1,
) -> str:
    style = _style_for(topic)
    index = max(1, int(index or 1))
    topic_text = _topic_core(topic, style)
    stage_text = _stage_phrase(stage_goal, stage_title, stage_position, style, topic)
    # A stage phrase that is only an ordinal ("第2阶段") carries no information and
    # would just repeat the unit index; drop it instead of padding the title.
    if _ORDINAL_ONLY.match(stage_text.strip()):
        stage_text = ""
    if style == "zh":
        base = (
            f"第{index}讲：{topic_text} · {stage_text}"
            if stage_text
            else f"第{index}讲：{topic_text}"
        )
    else:
        base = (
            f"Part {index}: {topic_text} — {stage_text}"
            if stage_text
            else f"Part {index}: {topic_text}"
        )
    return _clip(clean_title(base), MAX_TITLE_CHARS)


def derive_stage_title(topic: str, index: int) -> str:
    style = _style_for(topic)
    index = max(1, int(index or 1))
    topic_text = _topic_core(topic, style)
    if style == "zh":
        base = f"第{index}阶段：{topic_text}"
    else:
        base = f"Stage {index}: {topic_text}"
    return _clip(clean_title(base), MAX_STAGE_TITLE_CHARS)


def _place_unique(
    candidate: str,
    index: int,
    used: set[str],
    limit: int,
    style: str,
    fallback: Callable[[], str] | None = None,
) -> str:
    key = candidate.casefold()
    if key and key not in used:
        used.add(key)
        return candidate
    if fallback is not None:
        alternative = _clip(clean_title(fallback()), limit)
        alt_key = alternative.casefold()
        if alt_key and alt_key not in used:
            used.add(alt_key)
            return alternative
        candidate = alternative or candidate
    for attempt in range(1, 100):
        suffix = f"（{index}-{attempt}）" if style == "zh" else f" ({index}-{attempt})"
        stem = _clip(candidate, max(8, limit - len(suffix)))
        alternative = f"{stem}{suffix}"
        alt_key = alternative.casefold()
        if alt_key not in used:
            used.add(alt_key)
            return alternative
    return candidate


def sanitize_payload(payload: Mapping[str, Any], topic: str) -> tuple[dict[str, Any], list[str]]:
    data = dict(payload)
    repaired: list[str] = []
    style = _style_for(topic)
    stage_meta: dict[str, tuple[int, str, str]] = {}

    stages = data.get("learning_path") or data.get("stages")
    if isinstance(stages, list):
        stage_titles: list[str] = []
        used_stages: set[str] = set()
        for position, stage in enumerate(stages, start=1):
            if not isinstance(stage, MutableMapping):
                continue
            stage_id = _text(stage.get("id")) or f"stage-{position}"
            raw_title = _text(stage.get("title"))
            if is_placeholder_value(raw_title):
                title = derive_stage_title(topic, position)
                repaired.append(f"stage:{stage_id}:title")
            else:
                title = _clip(clean_title(raw_title), MAX_STAGE_TITLE_CHARS)
            title = _place_unique(
                title,
                position,
                used_stages,
                MAX_STAGE_TITLE_CHARS,
                style,
                lambda position=position: derive_stage_title(topic, position),
            )
            stage["title"] = title
            stage_titles.append(title)
            goal = _text(stage.get("goal"))
            if is_placeholder_value(goal):
                if goal:
                    repaired.append(f"stage:{stage_id}:goal")
                goal = ""
            else:
                goal = _clip(clean_title(goal), MAX_OBJECTIVE_CHARS)
            stage["goal"] = goal
            stage_meta[stage_id] = (position, goal, title)
        data.pop("stages", None)
        data["learning_path"] = stages

    nodes = data.get("outline") or data.get("nodes")
    if isinstance(nodes, list):
        used_titles: set[str] = set()
        for position, node in enumerate(nodes, start=1):
            if not isinstance(node, MutableMapping):
                continue
            stage_id = _text(node.get("stage_id"))
            stage_position, stage_goal, stage_title = stage_meta.get(
                stage_id, (1, "", "")
            )
            raw_title = _text(node.get("title"))
            if is_placeholder_value(raw_title):
                title = derive_node_title(
                    topic, position, stage_goal, stage_title, stage_position
                )
                repaired.append(f"node:{_text(node.get('id')) or position}:title")
            else:
                title = clean_title(raw_title)
            title = _clip(title, MAX_TITLE_CHARS)
            node["title"] = _place_unique(
                title,
                position,
                used_titles,
                MAX_TITLE_CHARS,
                style,
                lambda position=position, stage_goal=stage_goal, stage_title=stage_title, stage_position=stage_position: derive_node_title(
                    topic, position, stage_goal, stage_title, stage_position
                ),
            )
        data.pop("nodes", None)
        data["outline"] = nodes

    glossary = data.get("glossary")
    if isinstance(glossary, list):
        kept: list[dict[str, Any]] = []
        used_terms: set[str] = set()
        for item in glossary:
            if not isinstance(item, MutableMapping):
                continue
            term = clean_title(item.get("term"))
            if not term or is_placeholder_value(item.get("term")):
                repaired.append(f"glossary:{_text(item.get('term')) or 'term'}")
                continue
            key = term.casefold()
            if key in used_terms:
                continue
            used_terms.add(key)
            definition = _text(item.get("definition"))
            if definition and is_placeholder_value(definition, mention_ok=True):
                repaired.append(f"glossary:{term}:definition")
                definition = ""
            item["term"] = _clip(term, 60)
            item["definition"] = definition
            kept.append(item)
        data["glossary"] = kept

    return data, repaired


def sanitize_blueprint(blueprint: SeriesBlueprint, topic: str) -> tuple[SeriesBlueprint, list[str]]:
    data, repaired = sanitize_payload(blueprint.model_dump(), topic)
    if not repaired:
        return blueprint, repaired
    return SeriesBlueprint(**data), repaired
