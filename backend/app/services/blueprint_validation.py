"""Validation for hand-edited blueprints.

The generated-blueprint sanitizer (``blueprint_titles``) is deliberately
forgiving: it repairs placeholder titles so a bad model response still yields a
usable plan.  A human editor is different - silently rewriting what they typed
is confusing, so structured fields are *rejected* here.  We reuse the same
placeholder detector and the same length constants as the sanitizer instead of
maintaining a second copy of those rules.
"""

from __future__ import annotations

from typing import Any, Iterable

from app.models.blueprint import SeriesBlueprint
from app.services.blueprint_titles import (
    MAX_OBJECTIVE_CHARS,
    MAX_STAGE_TITLE_CHARS,
    MAX_TITLE_CHARS,
    clean_title,
    is_placeholder_value,
)

MAX_OVERVIEW_CHARS = 20_000
MAX_SUMMARY_CHARS = 4_000
MAX_GOAL_CHARS = 500
MAX_DEFINITION_CHARS = 2_000
MAX_STAGES = 40
MAX_NODES = 200
MAX_OBJECTIVES_PER_NODE = 20
MAX_PREREQUISITES_PER_NODE = 20


def _error(path: str, code: str, message: str) -> dict[str, str]:
    return {"path": path, "code": code, "message": message}


def _normalized(value: Any) -> str:
    return clean_title(value).casefold()


def _check_structured(
    errors: list[dict[str, str]],
    path: str,
    value: Any,
    *,
    required: bool,
    limit: int,
    label: str,
) -> None:
    raw = str(value or "").strip()
    if not raw:
        if required:
            errors.append(_error(path, "required", f"{label} must not be empty"))
        return
    if is_placeholder_value(raw):
        errors.append(
            _error(
                path,
                "placeholder",
                f"{label} contains a placeholder such as \"Insufficient material\" or \"<title>\"; write real content",
            )
        )
        return
    if len(raw) > limit:
        errors.append(
            _error(
                path,
                "too_long",
                f"{label} is {len(raw)} characters; the limit is {limit}",
            )
        )


def _check_unique(
    errors: list[dict[str, str]],
    seen: dict[str, str],
    path: str,
    value: Any,
    *,
    label: str,
) -> None:
    key = _normalized(value)
    if not key:
        return
    if key in seen:
        errors.append(
            _error(
                path,
                "duplicate",
                f"{label} \"{str(value).strip()}\" is used more than once; titles must be unique",
            )
        )
        return
    seen[key] = path


def _check_prose(
    errors: list[dict[str, str]],
    path: str,
    value: Any,
    *,
    limit: int,
    label: str,
) -> None:
    text = str(value or "")
    if len(text) > limit:
        errors.append(
            _error(
                path,
                "too_long",
                f"{label} is {len(text)} characters; the limit is {limit}",
            )
        )


def _check_string_list(
    errors: list[dict[str, str]],
    path: str,
    values: Iterable[Any],
    *,
    limit: int,
    item_limit: int,
    label: str,
) -> None:
    items = [str(item or "").strip() for item in values]
    if len(items) > limit:
        errors.append(
            _error(path, "too_many", f"{label} has {len(items)} entries; the limit is {limit}")
        )
    seen: set[str] = set()
    for index, item in enumerate(items):
        item_path = f"{path}[{index}]"
        if not item:
            errors.append(
                _error(item_path, "required", f"{label} item {index + 1} must not be empty")
            )
            continue
        if is_placeholder_value(item):
            errors.append(
                _error(
                    item_path,
                    "placeholder",
                    f"{label} item {index + 1} contains a placeholder; write a real value",
                )
            )
            continue
        if len(item) > item_limit:
            errors.append(
                _error(
                    item_path,
                    "too_long",
                    f"{label} item {index + 1} is {len(item)} characters; the limit is {item_limit}",
                )
            )
        key = item.casefold()
        if key in seen:
            errors.append(
                _error(item_path, "duplicate", f"{label} item {index + 1} is duplicated")
            )
        seen.add(key)


def validate_blueprint_for_edit(blueprint: SeriesBlueprint) -> list[dict[str, str]]:
    """Return every validation error in a hand-edited blueprint.

    Prose fields (overview, node summaries) may legitimately *mention* an
    evidence gap, so the sanitizer's placeholder detector is not applied to
    them.  Structured fields (titles, goals, objectives, glossary terms) must
    contain real values.
    """

    errors: list[dict[str, str]] = []

    if len(blueprint.learning_path) > MAX_STAGES:
        errors.append(
            _error(
                "learning_path",
                "too_many",
                f"the blueprint has {len(blueprint.learning_path)} stages; the limit is {MAX_STAGES}",
            )
        )
    if len(blueprint.outline) > MAX_NODES:
        errors.append(
            _error(
                "outline",
                "too_many",
                f"the blueprint has {len(blueprint.outline)} nodes; the limit is {MAX_NODES}",
            )
        )

    _check_prose(
        errors,
        "overview",
        blueprint.overview,
        limit=MAX_OVERVIEW_CHARS,
        label="overview",
    )

    stage_ids: set[str] = set()
    stage_titles: dict[str, str] = {}
    for index, stage in enumerate(blueprint.learning_path):
        base = f"learning_path[{index}]"
        stage_id = str(stage.id or "").strip()
        if not stage_id:
            errors.append(_error(f"{base}.id", "required", "stage id must not be empty"))
        elif stage_id in stage_ids:
            errors.append(
                _error(f"{base}.id", "duplicate", f"stage id \"{stage_id}\" is duplicated")
            )
        else:
            stage_ids.add(stage_id)
        _check_structured(
            errors,
            f"{base}.title",
            stage.title,
            required=True,
            limit=MAX_STAGE_TITLE_CHARS,
            label="stage title",
        )
        _check_unique(
            errors, stage_titles, f"{base}.title", stage.title, label="stage title"
        )
        _check_structured(
            errors,
            f"{base}.goal",
            stage.goal,
            required=False,
            limit=MAX_GOAL_CHARS,
            label="stage goal",
        )
        if len(stage.node_ids) > MAX_NODES:
            errors.append(
                _error(
                    f"{base}.node_ids",
                    "too_many",
                    f"stage has {len(stage.node_ids)} nodes; the limit is {MAX_NODES}",
                )
            )

    node_ids: set[str] = set()
    node_titles: dict[str, str] = {}
    for index, node in enumerate(blueprint.outline):
        base = f"outline[{index}]"
        node_id = str(node.id or "").strip()
        if not node_id:
            errors.append(_error(f"{base}.id", "required", "node id must not be empty"))
        elif node_id in node_ids:
            errors.append(
                _error(f"{base}.id", "duplicate", f"node id \"{node_id}\" is duplicated")
            )
        else:
            node_ids.add(node_id)
        _check_structured(
            errors,
            f"{base}.title",
            node.title,
            required=True,
            limit=MAX_TITLE_CHARS,
            label="node title",
        )
        _check_unique(
            errors, node_titles, f"{base}.title", node.title, label="node title"
        )
        _check_prose(
            errors,
            f"{base}.summary",
            node.summary,
            limit=MAX_SUMMARY_CHARS,
            label="node summary",
        )
        _check_string_list(
            errors,
            f"{base}.objectives",
            node.objectives,
            limit=MAX_OBJECTIVES_PER_NODE,
            item_limit=MAX_OBJECTIVE_CHARS,
            label="learning objective",
        )
        _check_string_list(
            errors,
            f"{base}.prerequisites",
            node.prerequisites,
            limit=MAX_PREREQUISITES_PER_NODE,
            item_limit=MAX_OBJECTIVE_CHARS,
            label="prerequisite",
        )
        if not node.stage_id:
            errors.append(
                _error(
                    f"{base}.stage_id",
                    "required",
                    "every node must belong to a stage",
                )
            )
        elif node.stage_id not in stage_ids:
            errors.append(
                _error(
                    f"{base}.stage_id",
                    "unknown_stage",
                    f"node stage \"{node.stage_id}\" does not match any stage",
                )
            )

    term_seen: dict[str, str] = {}
    for index, term in enumerate(blueprint.glossary):
        base = f"glossary[{index}]"
        _check_structured(
            errors,
            f"{base}.term",
            term.term,
            required=True,
            limit=60,
            label="glossary term",
        )
        _check_unique(
            errors, term_seen, f"{base}.term", term.term, label="glossary term"
        )
        _check_prose(
            errors,
            f"{base}.definition",
            term.definition,
            limit=MAX_DEFINITION_CHARS,
            label="glossary definition",
        )

    return errors
