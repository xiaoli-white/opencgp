from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

POVS = ("first", "third_limited", "third_omniscient")
TENSES = ("present", "past")
CITATION_POLICIES = ("required", "optional", "forbidden")
VALIDATORS = ("citation", "length", "structure", "continuity")
STRICTNESS_LEVELS = ("loose", "normal", "strict")
EXPORT_FORMATS = ("md", "html", "epub", "pdf")
SHARE_LEVELS = ("read", "use", "manage")
PROFILE_SCOPES = ("user", "tenant", "global")
SCOPE_USER = "user"
SCOPE_TENANT = "tenant"
SCOPE_GLOBAL = "global"
SYSTEM_TENANT_ID = "system"
SYSTEM_USER_ID = "system"
BUILTIN_ID_PREFIX = "profile_builtin_"
DEFAULT_UNIT_NAME = "Chapter"
DEFAULT_WORDS = 900
MIN_WORDS = 100
MAX_WORDS = 20000
MAX_UNIT_NAME_LENGTH = 8
MAX_PROMPT_LENGTH = 4000
DEFAULT_UNIT_MIN = 1
DEFAULT_UNIT_MAX = 60
DEFAULT_SECTIONS = (2, 5)
DEFAULT_DEPTH = 2


class ProfileMeta(BaseModel):
    name: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    icon: str = "book"


class ProfileUnit(BaseModel):
    name: str = DEFAULT_UNIT_NAME
    plural: str = DEFAULT_UNIT_NAME
    min_units: int = DEFAULT_UNIT_MIN
    max_units: int = DEFAULT_UNIT_MAX
    default_words: int = DEFAULT_WORDS


class ProfileStructure(BaseModel):
    depth: int = DEFAULT_DEPTH
    sections_per_unit: list[int] = Field(default_factory=lambda: [2, 5])
    requires_outline: bool = True


class ProfileVoice(BaseModel):
    tone: str = ""
    pov: str = "third_limited"
    tense: str = "present"
    forbidden_phrases: list[str] = Field(default_factory=list)


class ProfileGrounding(BaseModel):
    citation_policy: str = "optional"
    min_evidence: int = 0
    allow_web: bool = False


class ProfileAssets(BaseModel):
    glossary: bool = False
    setting_book: bool = False
    character_sheet: bool = False
    # Optional article illustration overrides. None means "use the global default".
    auto_images: bool | None = None
    max_images: int | None = None
    style: str = ""


class ProfileValidation(BaseModel):
    validators: list[str] = Field(default_factory=lambda: ["citation"])
    strictness: str = "normal"


class ProfilePrompts(BaseModel):
    system: str = ""
    outline: str = ""
    unit: str = ""
    revise: str = ""


class ProfileExport(BaseModel):
    default_format: str = "md"
    include_citations: bool = True


class ProfileSpec(BaseModel):
    meta: ProfileMeta = Field(default_factory=ProfileMeta)
    unit: ProfileUnit = Field(default_factory=ProfileUnit)
    structure: ProfileStructure = Field(default_factory=ProfileStructure)
    voice: ProfileVoice = Field(default_factory=ProfileVoice)
    grounding: ProfileGrounding = Field(default_factory=ProfileGrounding)
    assets: ProfileAssets = Field(default_factory=ProfileAssets)
    validation: ProfileValidation = Field(default_factory=ProfileValidation)
    prompts: ProfilePrompts = Field(default_factory=ProfilePrompts)
    export: ProfileExport = Field(default_factory=ProfileExport)


class ProfileShare(BaseModel):
    id: str = ""
    profile_id: str = ""
    user_id: str = ""
    level: str = "read"
    created_at: float = 0.0
    user_email: str = ""
    user_display_name: str = ""


class WorkProfile(BaseModel):
    id: str = ""
    tenant_id: str = ""
    owner_user_id: str = ""
    name: str = ""
    description: str = ""
    spec: ProfileSpec = Field(default_factory=ProfileSpec)
    scope: str = SCOPE_USER
    is_builtin: bool = False
    is_shared: bool = False
    version: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0
    owner_name: str = ""


def error_item(path: str, message: str) -> dict[str, str]:
    return {"path": path, "message": message}


def _as_dict(value: Any, path: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    errors.append(error_item(path, "must be an object"))
    return {}


def _as_str(
    value: Any, path: str, errors: list[dict[str, str]], default: str = ""
) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value).strip()
    errors.append(error_item(path, "must be a string"))
    return default


def _as_int(
    value: Any,
    path: str,
    errors: list[dict[str, str]],
    default: int,
    low: int | None = None,
    high: int | None = None,
) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        errors.append(error_item(path, "must be an integer"))
        return default
    if low is not None and parsed < low:
        errors.append(error_item(path, f"must be at least {low}"))
        return default
    if high is not None and parsed > high:
        errors.append(error_item(path, f"must be at most {high}"))
        return default
    return parsed


def _as_bool(value: Any, path: str, errors: list[dict[str, str]], default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off", ""):
            return False
    errors.append(error_item(path, "must be a boolean"))
    return default


def _as_str_list(value: Any, path: str, errors: list[dict[str, str]]) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [item.strip() for item in value.replace("，", ",").split(",")]
        return [item for item in parts if item]
    if isinstance(value, (list, tuple)):
        items: list[str] = []
        for entry in value:
            if isinstance(entry, str):
                text = entry.strip()
            elif isinstance(entry, (int, float)):
                text = str(entry)
            else:
                errors.append(error_item(path, "list items must be strings"))
                continue
            if text:
                items.append(text)
        return items
    errors.append(error_item(path, "must be an array of strings"))
    return []


def normalize_spec(raw: Any) -> tuple[ProfileSpec, list[dict[str, str]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if raw is None:
        data: dict[str, Any] = {}
    elif isinstance(raw, dict):
        data = raw
    else:
        errors.append(error_item("", "spec must be an object"))
        data = {}

    meta_raw = _as_dict(data.get("meta"), "meta", errors)
    unit_raw = _as_dict(data.get("unit"), "unit", errors)
    structure_raw = _as_dict(data.get("structure"), "structure", errors)
    voice_raw = _as_dict(data.get("voice"), "voice", errors)
    grounding_raw = _as_dict(data.get("grounding"), "grounding", errors)
    assets_raw = _as_dict(data.get("assets"), "assets", errors)
    validation_raw = _as_dict(data.get("validation"), "validation", errors)
    prompts_raw = _as_dict(data.get("prompts"), "prompts", errors)
    export_raw = _as_dict(data.get("export"), "export", errors)

    meta = ProfileMeta(
        name=_as_str(meta_raw.get("name"), "meta.name", errors),
        description=_as_str(meta_raw.get("description"), "meta.description", errors),
        tags=_as_str_list(meta_raw.get("tags"), "meta.tags", errors),
        icon=_as_str(meta_raw.get("icon"), "meta.icon", errors, "book") or "book",
    )

    unit_name = (
        _as_str(unit_raw.get("name"), "unit.name", errors)
        if "name" in unit_raw
        else DEFAULT_UNIT_NAME
    )
    if not unit_name:
        errors.append(error_item("unit.name", "unit name must not be empty"))
        unit_name = DEFAULT_UNIT_NAME
    if len(unit_name) > MAX_UNIT_NAME_LENGTH:
        errors.append(
            error_item("unit.name", f"unit name must not exceed {MAX_UNIT_NAME_LENGTH} characters")
        )
        unit_name = unit_name[:MAX_UNIT_NAME_LENGTH]
    plural = _as_str(unit_raw.get("plural"), "unit.plural", errors, unit_name) or unit_name
    min_units = _as_int(
        unit_raw.get("min_units"), "unit.min_units", errors, DEFAULT_UNIT_MIN, 1, 200
    )
    max_units = _as_int(
        unit_raw.get("max_units"), "unit.max_units", errors, DEFAULT_UNIT_MAX, 1, 200
    )
    if max_units < min_units:
        errors.append(error_item("unit.max_units", "max_units must not be less than min_units"))
        max_units = min_units
    default_words = _as_int(
        unit_raw.get("default_words"),
        "unit.default_words",
        errors,
        DEFAULT_WORDS,
        MIN_WORDS,
        MAX_WORDS,
    )
    unit = ProfileUnit(
        name=unit_name,
        plural=plural,
        min_units=min_units,
        max_units=max_units,
        default_words=default_words,
    )

    depth = _as_int(
        structure_raw.get("depth"), "structure.depth", errors, DEFAULT_DEPTH, 1, 5
    )
    sections_raw = structure_raw.get("sections_per_unit")
    sections = list(DEFAULT_SECTIONS)
    if sections_raw is not None:
        if isinstance(sections_raw, (list, tuple)) and len(sections_raw) == 2:
            low = _as_int(sections_raw[0], "structure.sections_per_unit", errors, 2, 1, 20)
            high = _as_int(sections_raw[1], "structure.sections_per_unit", errors, 5, 1, 20)
            if high < low:
                errors.append(
                    error_item("structure.sections_per_unit", "upper bound must not be less than lower bound")
                )
                high = low
            sections = [low, high]
        else:
            errors.append(error_item("structure.sections_per_unit", "must be two integers"))
    structure = ProfileStructure(
        depth=depth,
        sections_per_unit=sections,
        requires_outline=_as_bool(
            structure_raw.get("requires_outline"), "structure.requires_outline", errors, True
        ),
    )

    pov = _as_str(voice_raw.get("pov"), "voice.pov", errors, "third_limited") or "third_limited"
    if pov not in POVS:
        errors.append(error_item("voice.pov", f"unknown point of view: {pov}"))
        pov = "third_limited"
    tense = _as_str(voice_raw.get("tense"), "voice.tense", errors, "present") or "present"
    if tense not in TENSES:
        errors.append(error_item("voice.tense", f"unknown tense: {tense}"))
        tense = "present"
    voice = ProfileVoice(
        tone=_as_str(voice_raw.get("tone"), "voice.tone", errors),
        pov=pov,
        tense=tense,
        forbidden_phrases=_as_str_list(
            voice_raw.get("forbidden_phrases"), "voice.forbidden_phrases", errors
        ),
    )

    policy = (
        _as_str(grounding_raw.get("citation_policy"), "grounding.citation_policy", errors, "optional")
        or "optional"
    )
    if policy not in CITATION_POLICIES:
        errors.append(error_item("grounding.citation_policy", f"unknown citation policy: {policy}"))
        policy = "optional"
    grounding = ProfileGrounding(
        citation_policy=policy,
        min_evidence=_as_int(
            grounding_raw.get("min_evidence"), "grounding.min_evidence", errors, 0, 0, 20
        ),
        allow_web=_as_bool(
            grounding_raw.get("allow_web"), "grounding.allow_web", errors, False
        ),
    )

    auto_images_raw = assets_raw.get("auto_images")
    auto_images = (
        None
        if auto_images_raw is None
        else _as_bool(auto_images_raw, "assets.auto_images", errors, True)
    )
    max_images_raw = assets_raw.get("max_images")
    max_images = (
        None
        if max_images_raw is None
        else _as_int(max_images_raw, "assets.max_images", errors, 3, 0, 20)
    )
    assets = ProfileAssets(
        glossary=_as_bool(assets_raw.get("glossary"), "assets.glossary", errors, False),
        setting_book=_as_bool(
            assets_raw.get("setting_book"), "assets.setting_book", errors, False
        ),
        character_sheet=_as_bool(
            assets_raw.get("character_sheet"), "assets.character_sheet", errors, False
        ),
        auto_images=auto_images,
        max_images=max_images,
        style=_as_str(assets_raw.get("style"), "assets.style", errors),
    )

    validators = _as_str_list(validation_raw.get("validators"), "validation.validators", errors)
    if "validators" not in validation_raw:
        validators = ["citation"]
    kept: list[str] = []
    for item in validators:
        if item not in VALIDATORS:
            errors.append(error_item("validation.validators", f"unknown validator: {item}"))
            continue
        if item not in kept:
            kept.append(item)
    if policy == "forbidden" and "citation" in kept:
        kept = [item for item in kept if item != "citation"]
        warnings.append(
            error_item(
                "validation.validators",
                "citation policy is forbidden; the citation validator was removed automatically",
            )
        )
    strictness = (
        _as_str(validation_raw.get("strictness"), "validation.strictness", errors, "normal")
        or "normal"
    )
    if strictness not in STRICTNESS_LEVELS:
        errors.append(error_item("validation.strictness", f"unknown strictness: {strictness}"))
        strictness = "normal"
    validation = ProfileValidation(validators=kept, strictness=strictness)

    prompts = ProfilePrompts()
    for field in ("system", "outline", "unit", "revise"):
        text = _as_str(prompts_raw.get(field), f"prompts.{field}", errors)
        if len(text) > MAX_PROMPT_LENGTH:
            errors.append(
                error_item(f"prompts.{field}", f"prompt must not exceed {MAX_PROMPT_LENGTH} characters")
            )
            text = text[:MAX_PROMPT_LENGTH]
        setattr(prompts, field, text)

    export_format = (
        _as_str(export_raw.get("default_format"), "export.default_format", errors, "md") or "md"
    )
    if export_format not in EXPORT_FORMATS:
        errors.append(error_item("export.default_format", f"unknown export format: {export_format}"))
        export_format = "md"
    export = ProfileExport(
        default_format=export_format,
        include_citations=_as_bool(
            export_raw.get("include_citations"), "export.include_citations", errors, True
        ),
    )

    spec = ProfileSpec(
        meta=meta,
        unit=unit,
        structure=structure,
        voice=voice,
        grounding=grounding,
        assets=assets,
        validation=validation,
        prompts=prompts,
        export=export,
    )
    return spec, errors, warnings
