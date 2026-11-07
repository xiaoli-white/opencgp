from __future__ import annotations

import re
from typing import Any, Mapping

from app.models.work_profile import ProfileSpec

POV_LABELS = {
    "first": "first person",
    "third_limited": "third person limited",
    "third_omniscient": "third person omniscient",
}
TENSE_LABELS = {"present": "present tense", "past": "past tense"}
POLICY_LABELS = {
    "required": "must cite knowledge-base evidence",
    "optional": "cite when evidence exists; write freely otherwise",
    "forbidden": "must not cite knowledge-base evidence",
}
DEFAULT_UNIT = "Chapter"
DEFAULT_STRICT_WORDS = (600, 1200)
DEFAULT_LOOSE_WORDS = (800, 1500)

_VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def render_template(template: str, values: Mapping[str, Any]) -> str:
    if not template:
        return ""

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            return match.group(0)
        value = values[key]
        return "" if value is None else str(value)

    return _VARIABLE.sub(_replace, template).strip()


def unit_name(spec: ProfileSpec | None, default: str = DEFAULT_UNIT) -> str:
    if spec is None:
        return default
    name = (spec.unit.name or "").strip()
    return name or default


def default_words(spec: ProfileSpec | None, fallback: int = 900) -> int:
    if spec is None:
        return fallback
    return max(1, int(spec.unit.default_words or fallback))


def word_range(
    spec: ProfileSpec | None, fallback: tuple[int, int] | None = None
) -> tuple[int, int]:
    if spec is None:
        return fallback or DEFAULT_STRICT_WORDS
    words = default_words(spec)
    low = max(80, int(words * 0.6))
    high = max(low + 40, int(words * 1.6))
    return low, high


def policy_of(spec: ProfileSpec | None, mode: str) -> str:
    if spec is None:
        return "required" if (mode or "strict") == "strict" else "optional"
    policy = (spec.grounding.citation_policy or "").strip()
    return policy if policy in POLICY_LABELS else "optional"


def policy_label(spec: ProfileSpec | None, mode: str) -> str:
    return POLICY_LABELS.get(policy_of(spec, mode), POLICY_LABELS["optional"])


def voice_lines(spec: ProfileSpec | None) -> list[str]:
    if spec is None:
        return []
    lines: list[str] = []
    tone = (spec.voice.tone or "").strip()
    if tone:
        lines.append(f"- Tone: {tone}")
    pov = POV_LABELS.get((spec.voice.pov or "").strip())
    if pov:
        lines.append(f"- Narrative person: {pov}")
    tense = TENSE_LABELS.get((spec.voice.tense or "").strip())
    if tense:
        lines.append(f"- Narrative tense: {tense}")
    forbidden = [item.strip() for item in spec.voice.forbidden_phrases if item.strip()]
    if forbidden:
        lines.append("- Never use the following wording: " + ", ".join(forbidden))
    return lines


def glossary_lines(spec: ProfileSpec | None, unit: str | None = None) -> list[str]:
    if spec is None or not spec.assets.glossary:
        return []
    label = unit or unit_name(spec)
    return [
        f"- End the body with a \"## Glossary\" section listing the key terms that appear in this {label}; "
        "write each item as \"- Term: one-sentence explanation\" and do not omit the section."
    ]


def prompt_values(
    spec: ProfileSpec | None,
    title: str = "",
    unit: str | None = None,
    unit_index: int | str = "",
    audience: str = "",
    tone: str = "",
    evidence_count: int | str = "",
    instruction: str = "",
) -> dict[str, Any]:
    label = unit or unit_name(spec)
    return {
        "title": title,
        "unit": label,
        "unit_index": unit_index,
        "audience": audience,
        "tone": tone or ((spec.voice.tone or "").strip() if spec else ""),
        "evidence_count": evidence_count,
        "instruction": instruction,
    }


def system_prefix(spec: ProfileSpec | None, values: Mapping[str, Any]) -> str:
    if spec is None:
        return ""
    text = render_template(spec.prompts.system, values)
    if not text:
        return ""
    return "## Additional system requirements\n" + text


def extra_requirement(spec: ProfileSpec | None, kind: str, values: Mapping[str, Any]) -> str:
    if spec is None:
        return ""
    raw = getattr(spec.prompts, kind, "") or ""
    text = render_template(raw, values)
    if not text:
        return ""
    label = {
        "unit": "Additional writing requirements",
        "outline": "Additional outline requirements",
        "revise": "Additional revision requirements",
    }.get(kind, "Additional requirements")
    return f"## {label}\n" + text


def citation_taxonomy_lines(mandatory: bool = True) -> list[str]:
    duty = (
        "Every item in the NEEDS list must carry a marker that points to the evidence passage supporting it."
        if mandatory
        else "In this free-writing mode markers are optional, but when you use retrieved evidence for an item in the NEEDS list, cite it."
    )
    return [
        "",
        "## Semantic citation policy (not a blanket per-paragraph rule)",
        duty,
        "",
        "NEEDS a citation:",
        "- statistics, numbers, or metrics with units, percentages, or ranges;",
        "- theorems, formulas, or complexity claims;",
        "- claims attributed to other people, papers, standards, or organisations;",
        "- historical facts, dates, people, or organisations;",
        "- concrete product behaviour, versions, or default values, including a "
        "sentence such as \"the default value of this API is X\" inside a tutorial;",
        "- comparative claims such as \"3x faster than B\";",
        "- any other externally checkable factual assertion.",
        "",
        "DOES NOT need a citation:",
        "- walkthroughs of example code and line-by-line code commentary, because "
        "the code is its own evidence;",
        "- procedural how-to steps;",
        "- analogies, metaphors, transitions, section summaries, reading guides, "
        "or exercises;",
        "- explicitly labelled subjective advice or personal experience;",
        "- fiction or creative content;",
        "- restatements of earlier paragraphs in the same article.",
        "",
        "Edge rules:",
        "- In a sentence that mixes fact and explanation, cite only the factual "
        "clause, not the explanatory clause.",
        "- Never insert a marker inside a code block or inside inline code; put "
        "the citation in the surrounding prose.",
        "- When genuinely unsure, fall back to the profile citation policy: "
        "required means cite, optional means do not cite but record the gap for "
        "the missing-evidence list, forbidden means never cite.",
    ]
