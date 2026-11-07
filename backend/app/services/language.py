from __future__ import annotations

import re
from typing import Any

from app.config import get_settings

CJK_CHAR_RE = re.compile(r"[\u3400-\u9fff]")
LATIN_CHAR_RE = re.compile(r"[A-Za-z]")

ZH_ALIASES = {"zh", "zh-cn", "zh-hans", "zh-hant", "chinese", "中文", "简体中文", "繁体中文"}
EN_ALIASES = {"en", "en-us", "en-gb", "english", "英文", "英语"}
BILINGUAL_ALIASES = {"bilingual", "mixed", "双语", "中英双语", "中英"}


def normalize_language(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw or raw in ("auto", "default", "none"):
        return ""
    if raw in ZH_ALIASES or raw.startswith("zh-"):
        return "zh"
    if raw in EN_ALIASES or raw.startswith("en-"):
        return "en"
    if raw in BILINGUAL_ALIASES:
        return "bilingual"
    return raw


def detect_script_language(text: str) -> str:
    body = str(text or "")
    cjk = len(CJK_CHAR_RE.findall(body))
    latin = len(LATIN_CHAR_RE.findall(body))
    if not cjk and not latin:
        return ""
    if cjk and cjk >= latin * 0.5:
        return "zh"
    if latin:
        return "en"
    return "zh" if cjk else ""


def profile_language(spec: Any) -> str:
    if spec is None:
        return ""
    meta = getattr(spec, "meta", None)
    if isinstance(meta, dict):
        value = meta.get("language")
    else:
        value = getattr(meta, "language", "")
    if not value:
        value = getattr(spec, "language", "")
    return normalize_language(value)


def resolve_output_language(
    series_language: Any,
    title: str = "",
    profile_language_value: Any = "",
    default_language: Any = "",
) -> str:
    explicit = normalize_language(series_language)
    if explicit:
        return explicit
    from_profile = normalize_language(profile_language_value)
    if from_profile:
        return from_profile
    from_title = detect_script_language(title)
    if from_title:
        return from_title
    fallback = normalize_language(default_language)
    if fallback:
        return fallback
    return normalize_language(get_settings().generation.default_language) or "zh"


def language_name(value: Any) -> str:
    code = normalize_language(value)
    if code == "zh":
        return "Simplified Chinese (zh)"
    if code == "en":
        return "English (en)"
    if code == "bilingual":
        return "Chinese and English (bilingual)"
    return code or "the language of the course title"


def with_output_language(series: Any, spec: Any = None) -> Any:
    if series is None:
        return None
    stored = getattr(series, "language", "")
    explicit = stored if getattr(series, "language_explicit", True) else ""
    resolved = resolve_output_language(
        explicit,
        str(getattr(series, "title", "") or ""),
        profile_language(spec),
    )
    current = normalize_language(stored)
    if current == resolved:
        return series
    updater = getattr(series, "model_copy", None)
    if callable(updater):
        return updater(update={"language": resolved})
    return series
