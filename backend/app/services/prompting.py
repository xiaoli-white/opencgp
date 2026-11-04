from __future__ import annotations

import re
from typing import Any, Mapping

from app.models.work_profile import ProfileSpec

POV_LABELS = {
    "first": "第一人称",
    "third_limited": "第三人称限知",
    "third_omniscient": "第三人称全知",
}
TENSE_LABELS = {"present": "现在时", "past": "过去时"}
POLICY_LABELS = {
    "required": "必须引用知识库证据",
    "optional": "有证据则引用，无证据可自由写作",
    "forbidden": "不得引用知识库证据",
}
DEFAULT_UNIT = "讲"
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
        lines.append(f"- 语气：{tone}")
    pov = POV_LABELS.get((spec.voice.pov or "").strip())
    if pov:
        lines.append(f"- 叙述人称：{pov}")
    tense = TENSE_LABELS.get((spec.voice.tense or "").strip())
    if tense:
        lines.append(f"- 叙述时态：{tense}")
    forbidden = [item.strip() for item in spec.voice.forbidden_phrases if item.strip()]
    if forbidden:
        lines.append("- 严禁出现以下措辞：" + "、".join(forbidden))
    return lines


def glossary_lines(spec: ProfileSpec | None, unit: str | None = None) -> list[str]:
    if spec is None or not spec.assets.glossary:
        return []
    label = unit or unit_name(spec)
    return [
        f"- 正文结尾必须追加「## 术语」小节，列出本{label}出现的关键术语，"
        "每条写成「- 术语：一句话解释」，不得省略。"
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
    return "## 追加系统要求\n" + text


def extra_requirement(spec: ProfileSpec | None, kind: str, values: Mapping[str, Any]) -> str:
    if spec is None:
        return ""
    raw = getattr(spec.prompts, kind, "") or ""
    text = render_template(raw, values)
    if not text:
        return ""
    label = {
        "unit": "额外写作要求",
        "outline": "额外大纲要求",
        "revise": "额外修改要求",
    }.get(kind, "额外要求")
    return f"## {label}\n" + text
