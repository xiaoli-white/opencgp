from __future__ import annotations

from collections import OrderedDict
import re
from typing import Any, Iterable, Sequence

from app.models.auth import AuthContext
from app.models.series import Series
from app.models.piece import Piece
from app.models.work_profile import (
    BUILTIN_ID_PREFIX,
    PROFILE_SCOPES,
    SCOPE_GLOBAL,
    SCOPE_TENANT,
    SCOPE_USER,
    SHARE_LEVELS,
    SYSTEM_USER_ID,
    ProfileShare,
    ProfileSpec,
    WorkProfile,
    normalize_spec,
)
from app.ports.work_profile_repository import WorkProfileRepository
from app.services.errors import (
    BuiltinProfileError,
    PermissionDeniedError,
    ProfileInUseError,
    ProfileInvalidError,
    ProfileNotFoundError,
)

EXPORT_FORMAT = "opencgp.profile"
EXPORT_VERSION = 1
SAMPLE_TEXT_MAX = 4000
SAMPLE_CHARS_MIN = 50
SAMPLE_CHARS_MAX = 2000
CITATION_MARKER = re.compile(r"\s*\[E\d+\]")

BUILTIN_TENANT_ID = "system"
BUILTIN_TUTORIAL_ID = f"{BUILTIN_ID_PREFIX}tutorial"
BUILTIN_ARTICLE_ID = f"{BUILTIN_ID_PREFIX}article"
SPEC_CACHE_SIZE = 128

BUILTIN_PRESETS: tuple[dict[str, Any], ...] = (
    {
        "key": "tutorial",
        "name": "Technical tutorial",
        "description": "A step-by-step tutorial for engineering practice, emphasizing citable evidence and structural completeness",
        "spec": {
            "meta": {"name": "Technical tutorial", "description": "Step-by-step technical tutorial", "tags": ["technical", "tutorial"], "icon": "book"},
            "unit": {"name": "Chapter", "plural": "Chapters", "min_units": 1, "max_units": 60, "default_words": 900},
            "structure": {"depth": 2, "sections_per_unit": [2, 5], "requires_outline": True},
            "voice": {"tone": "clear, pragmatic", "pov": "third_limited", "tense": "present"},
            "grounding": {"citation_policy": "required", "min_evidence": 1, "allow_web": False},
            "assets": {"glossary": True, "setting_book": False, "character_sheet": False},
            "validation": {"validators": ["citation", "structure"], "strictness": "strict"},
            "export": {"default_format": "md", "include_citations": True},
        },
    },
    {
        "key": "article",
        "name": "Technical long-form article",
        "description": "A free-writing profile suited to technical blogs and in-depth articles",
        "spec": {
            "meta": {"name": "Technical long-form article", "description": "In-depth technical article", "tags": ["technical", "long-form"], "icon": "article"},
            "unit": {"name": "Section", "plural": "Sections", "min_units": 3, "max_units": 20, "default_words": 1200},
            "structure": {"depth": 2, "sections_per_unit": [2, 4], "requires_outline": True},
            "voice": {"tone": "professional, restrained", "pov": "third_limited", "tense": "present"},
            "grounding": {"citation_policy": "optional", "min_evidence": 0, "allow_web": True},
            "assets": {"glossary": False, "setting_book": False, "character_sheet": False},
            "validation": {"validators": ["length"], "strictness": "normal"},
            "export": {"default_format": "md", "include_citations": True},
        },
    },
    {
        "key": "novel",
        "name": "Novel",
        "description": "A long-form fiction profile with a setting book and character sheets",
        "spec": {
            "meta": {"name": "Novel", "description": "Fictional narrative", "tags": ["novel", "narrative"], "icon": "feather"},
            "unit": {"name": "Chapter", "plural": "Chapters", "min_units": 5, "max_units": 200, "default_words": 3000},
            "structure": {"depth": 3, "sections_per_unit": [3, 6], "requires_outline": True},
            "voice": {"tone": "highly narrative", "pov": "third_limited", "tense": "past"},
            "grounding": {"citation_policy": "forbidden", "min_evidence": 0, "allow_web": False},
            "assets": {"glossary": False, "setting_book": True, "character_sheet": True},
            "validation": {"validators": ["continuity", "length"], "strictness": "normal"},
            "export": {"default_format": "md", "include_citations": False},
        },
    },
    {
        "key": "report",
        "name": "Research report",
        "description": "A structured research report requiring both citation and length validation",
        "spec": {
            "meta": {"name": "Research report", "description": "Research analysis report", "tags": ["research", "report"], "icon": "chart"},
            "unit": {"name": "Part", "plural": "Parts", "min_units": 3, "max_units": 12, "default_words": 1500},
            "structure": {"depth": 3, "sections_per_unit": [2, 5], "requires_outline": True},
            "voice": {"tone": "objective, rigorous", "pov": "third_omniscient", "tense": "present"},
            "grounding": {"citation_policy": "required", "min_evidence": 1, "allow_web": True},
            "assets": {"glossary": True, "setting_book": False, "character_sheet": False},
            "validation": {"validators": ["citation", "length"], "strictness": "strict"},
            "export": {"default_format": "pdf", "include_citations": True},
        },
    },
    {
        "key": "essay",
        "name": "Essay",
        "description": "A first-person free-form essay that does not require citations",
        "spec": {
            "meta": {"name": "Essay", "description": "Personal essay", "tags": ["essay", "prose"], "icon": "pen"},
            "unit": {"name": "Passage", "plural": "Passages", "min_units": 1, "max_units": 30, "default_words": 600},
            "structure": {"depth": 1, "sections_per_unit": [1, 3], "requires_outline": False},
            "voice": {"tone": "relaxed, personal", "pov": "first", "tense": "present"},
            "grounding": {"citation_policy": "forbidden", "min_evidence": 0, "allow_web": False},
            "assets": {"glossary": False, "setting_book": False, "character_sheet": False},
            "validation": {"validators": ["length"], "strictness": "loose"},
            "export": {"default_format": "md", "include_citations": False},
        },
    },
)

POV_LABELS = {"first": "first person", "third_limited": "third person limited", "third_omniscient": "third person omniscient"}
TENSE_LABELS = {"present": "present tense", "past": "past tense"}
POLICY_LABELS = {"required": "citations required", "optional": "citations optional", "forbidden": "citations forbidden"}

SYSTEM_TEMPLATE = (
    "You are the writing assistant for \"{title}\", writing under the \"{profile_name}\" profile.\n"
    "Writing unit: {unit_name}; each {unit_name} is about {words} words, and there are {min_units}-{max_units} {unit_name} in total.\n"
    "Target audience: {audience}.\n"
    "Tone: {tone}; person: {pov_label}; tense: {tense_label}.\n"
    "Citation policy: {policy_label}; never use the following expressions: {forbidden}.\n"
    "Each {unit_name} must be split into {sections_lo}-{sections_hi} key points, with an outline depth of {depth} levels."
)

OUTLINE_TEMPLATE = (
    "Design an outline for \"{title}\" with the \"{profile_name}\" profile.\n"
    "Requirements: {min_units}-{max_units} {unit_name} in total; each {unit_name} contains {sections_lo}-{sections_hi} key points, "
    "and each {unit_name} is about {words} words.\n"
    "Output a JSON array whose elements contain the fields id, title, summary, and target_words."
)

UNIT_TEMPLATE = (
    "Write {unit_name} number {index} of \"{title}\", titled \"{unit_title}\", about {words} words.\n"
    "Reader: {audience}; tone: {tone}; person: {pov_label}.\n"
    "Key points to cover: {sections}.\n"
    "Citation policy: {policy_label}."
)

REVISE_TEMPLATE = (
    "Revise the content of \"{unit_title}\" in \"{title}\" according to the feedback below, keeping the {unit_name} structure and a length of about {words} words.\n"
    "Feedback: {instruction}"
)


class ProfileService:
    def __init__(self, repository: WorkProfileRepository) -> None:
        self.repository = repository
        self._seeded = False
        self._spec_cache: OrderedDict[tuple[str, int], ProfileSpec] = OrderedDict()

    def resolve_for_series(self, series: Series | None) -> ProfileSpec:
        profile_id = (getattr(series, "profile_id", "") or "").strip()
        return self.resolve(profile_id or BUILTIN_TUTORIAL_ID)

    def resolve_for_piece(self, piece: Piece | None) -> ProfileSpec:
        profile_id = (getattr(piece, "profile_id", "") or "").strip()
        return self.resolve(profile_id or BUILTIN_ARTICLE_ID)

    def resolve(self, profile_id: str, fallback_id: str = BUILTIN_TUTORIAL_ID) -> ProfileSpec:
        resolved = (profile_id or "").strip()
        for candidate in (resolved, fallback_id):
            if not candidate:
                continue
            spec = self._cached_spec(candidate)
            if spec is not None:
                return spec
        return ProfileSpec()

    def _cached_spec(self, profile_id: str) -> ProfileSpec | None:
        self.ensure_builtin()
        profile = self.repository.get(profile_id)
        if profile is None:
            return None
        key = (profile.id, int(profile.version))
        cached = self._spec_cache.get(key)
        if cached is not None:
            self._spec_cache.move_to_end(key)
            return cached
        self._spec_cache[key] = profile.spec
        self._spec_cache.move_to_end(key)
        while len(self._spec_cache) > SPEC_CACHE_SIZE:
            self._spec_cache.popitem(last=False)
        return profile.spec

    def ensure_builtin(self) -> None:
        if self._seeded:
            return
        self.repository.ensure_schema()
        existing = {item.id for item in self.repository.list_builtin()}
        for preset in BUILTIN_PRESETS:
            profile_id = f"{BUILTIN_ID_PREFIX}{preset['key']}"
            if profile_id in existing:
                continue
            spec, _errors, _warnings = normalize_spec(preset["spec"])
            self.repository.create(
                WorkProfile(
                    id=profile_id,
                    tenant_id=BUILTIN_TENANT_ID,
                    owner_user_id=SYSTEM_USER_ID,
                    name=preset["name"],
                    description=preset.get("description", ""),
                    spec=spec,
                    is_builtin=True,
                    is_shared=False,
                    version=1,
                )
            )
        self._seeded = True

    def _load(self, profile_id: str) -> WorkProfile:
        self.ensure_builtin()
        profile = self.repository.get(profile_id)
        if profile is None:
            raise ProfileNotFoundError(f"creation profile not found: {profile_id}")
        return profile

    def _readable(self, profile: WorkProfile, ctx: AuthContext) -> bool:
        if profile.is_builtin:
            return True
        user_id = ctx.user.id
        tenant_id = ctx.tenant.id if ctx.tenant is not None else ""
        if profile.scope == SCOPE_GLOBAL:
            return True
        if profile.scope == SCOPE_TENANT and profile.tenant_id == tenant_id:
            return True
        if profile.owner_user_id == user_id:
            return True
        if profile.tenant_id == tenant_id and profile.is_shared:
            return True
        return self.repository.get_share(profile.id, user_id) is not None

    def can_edit(self, profile: WorkProfile, ctx: AuthContext) -> bool:
        if profile.is_builtin:
            return False
        if profile.scope == SCOPE_GLOBAL:
            return bool(ctx.can("manage_server"))
        if profile.scope == SCOPE_TENANT:
            tenant_id = ctx.tenant.id if ctx.tenant is not None else ""
            return profile.tenant_id == tenant_id and bool(ctx.can("manage_server"))
        return bool(profile.owner_user_id) and profile.owner_user_id == ctx.user.id

    def _require_readable(self, profile_id: str, ctx: AuthContext) -> WorkProfile:
        profile = self._load(profile_id)
        if not self._readable(profile, ctx):
            raise ProfileNotFoundError(f"creation profile not found: {profile_id}")
        return profile

    def _require_editable(self, profile_id: str, ctx: AuthContext) -> WorkProfile:
        profile = self._load(profile_id)
        if profile.is_builtin:
            raise BuiltinProfileError("built-in presets cannot be modified; copy one first")
        if not self.can_edit(profile, ctx):
            raise PermissionDeniedError("you do not have permission to modify this creation profile")
        return profile

    def payload(self, profile: WorkProfile, ctx: AuthContext) -> dict[str, Any]:
        share = self.repository.get_share(profile.id, ctx.user.id)
        is_owner = bool(profile.owner_user_id) and profile.owner_user_id == ctx.user.id
        owner_name = profile.owner_name or ("Built-in" if profile.is_builtin else "")
        shared_by_owner = bool(share is not None) or bool(
            profile.is_shared and not is_owner and not profile.is_builtin
        )
        return {
            "id": profile.id,
            "tenant_id": profile.tenant_id,
            "name": profile.name,
            "description": profile.description,
            "spec": profile.spec.model_dump(),
            "scope": profile.scope or SCOPE_USER,
            "is_builtin": profile.is_builtin,
            "is_owner": is_owner,
            "can_edit": self.can_edit(profile, ctx),
            "is_shared": profile.is_shared,
            "shared_by_owner": shared_by_owner,
            "shared_to_me": bool(share is not None),
            "share_level": share.level if share is not None else "",
            "owner_user_id": profile.owner_user_id,
            "owner_name": owner_name,
            "version": profile.version,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }

    def list(self, ctx: AuthContext) -> list[dict[str, Any]]:
        self.ensure_builtin()
        tenant_id = ctx.tenant.id if ctx.tenant is not None else ""
        items = self.repository.list_visible(tenant_id, ctx.user.id)
        return [self.payload(item, ctx) for item in items]

    def get(self, ctx: AuthContext, profile_id: str) -> dict[str, Any]:
        profile = self._require_readable(profile_id, ctx)
        return self.payload(profile, ctx)

    def get_spec(self, ctx: AuthContext, profile_id: str) -> ProfileSpec:
        return self._require_readable(profile_id, ctx).spec

    def create(
        self,
        ctx: AuthContext,
        name: str,
        spec: Any = None,
        is_shared: bool = False,
        description: str = "",
        scope: str = SCOPE_USER,
    ) -> dict[str, Any]:
        label = (name or "").strip()
        if not label:
            raise ProfileInvalidError("creation profile name must not be empty")
        resolved_scope = (scope or SCOPE_USER).strip().lower()
        if resolved_scope not in PROFILE_SCOPES:
            raise ProfileInvalidError(f"unknown scope: {scope}")
        if resolved_scope != SCOPE_USER and not ctx.can("manage_server"):
            raise PermissionDeniedError("non-personal scopes require the manage_server permission")
        normalized, errors, _warnings = normalize_spec(spec)
        if errors:
            raise ProfileInvalidError(self._error_message(errors))
        profile = self.repository.create(
            WorkProfile(
                id="",
                tenant_id=ctx.tenant.id if ctx.tenant is not None else "",
                owner_user_id=ctx.user.id,
                name=label,
                description=(description or "").strip(),
                spec=normalized,
                scope=resolved_scope,
                is_builtin=False,
                is_shared=bool(is_shared),
                version=1,
            )
        )
        return self.payload(profile, ctx)

    def duplicate(
        self, ctx: AuthContext, profile_id: str, name: str | None = None
    ) -> dict[str, Any]:
        source = self._require_readable(profile_id, ctx)
        label = (name or "").strip() or f"{source.name} copy"
        profile = self.repository.create(
            WorkProfile(
                id="",
                tenant_id=ctx.tenant.id if ctx.tenant is not None else "",
                owner_user_id=ctx.user.id,
                name=label,
                description=source.description,
                spec=source.spec,
                is_builtin=False,
                is_shared=False,
                version=1,
            )
        )
        return self.payload(profile, ctx)

    def update(
        self,
        ctx: AuthContext,
        profile_id: str,
        name: str | None = None,
        spec: Any = None,
        is_shared: bool | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        current = self._require_editable(profile_id, ctx)
        normalized: ProfileSpec | None = None
        if spec is not None:
            normalized, errors, _warnings = normalize_spec(spec)
            if errors:
                raise ProfileInvalidError(self._error_message(errors))
        label = current.name if name is None else (name or "").strip()
        if not label:
            raise ProfileInvalidError("creation profile name must not be empty")
        updated = self.repository.update(
            profile_id,
            name=label,
            description=None if description is None else (description or "").strip(),
            spec=normalized,
            is_shared=is_shared,
            bump_version=normalized is not None,
        )
        if updated is None:
            raise ProfileNotFoundError(f"creation profile not found: {profile_id}")
        return self.payload(updated, ctx)

    def delete(self, ctx: AuthContext, profile_id: str) -> dict[str, Any]:
        self._require_editable(profile_id, ctx)
        used = self.repository.count_usage(profile_id)
        if used > 0:
            raise ProfileInUseError(f"{used} works still use this profile")
        removed = self.repository.delete(profile_id)
        return {"ok": bool(removed), "profile_id": profile_id}

    def validate(self, spec: Any) -> dict[str, Any]:
        normalized, errors, warnings = normalize_spec(spec)
        return {
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "spec": normalized.model_dump(),
        }

    def export_payload(self, ctx: AuthContext, profile_id: str) -> dict[str, Any]:
        profile = self._require_readable(profile_id, ctx)
        return {
            "format": EXPORT_FORMAT,
            "version": EXPORT_VERSION,
            "name": profile.name,
            "spec": profile.spec.model_dump(),
        }

    def import_profile(
        self,
        ctx: AuthContext,
        data: Any,
        name: str | None = None,
        scope: str = SCOPE_USER,
    ) -> dict[str, Any]:
        payload: dict[str, Any]
        if isinstance(data, dict):
            payload = data
        else:
            raise ProfileInvalidError("imported data must be a JSON object")
        if "format" in payload:
            if str(payload.get("format") or "") != EXPORT_FORMAT:
                raise ProfileInvalidError(
                    f"unsupported import format: {payload.get('format') or 'empty'}"
                )
            try:
                version = int(payload.get("version"))
            except (TypeError, ValueError):
                raise ProfileInvalidError("the import version must be an integer")
            if version != EXPORT_VERSION:
                raise ProfileInvalidError(f"unsupported import version: {version}")
        if "spec" not in payload:
            raise ProfileInvalidError("imported data is missing the spec field")
        spec_raw = payload.get("spec")
        normalized, errors, _warnings = normalize_spec(spec_raw)
        if errors:
            raise ProfileInvalidError(self._error_message(errors), errors=errors)
        resolved_scope = (scope or SCOPE_USER).strip().lower()
        if resolved_scope not in PROFILE_SCOPES:
            raise ProfileInvalidError(f"unknown scope: {scope}")
        if resolved_scope != SCOPE_USER and not ctx.can("manage_server"):
            raise PermissionDeniedError("non-personal scopes require the manage_server permission")
        label = (name or "").strip()
        if not label:
            label = str(payload.get("name") or "").strip()
        if not label:
            label = str(payload.get("spec", {}).get("meta", {}).get("name") or "").strip() if isinstance(payload.get("spec"), dict) else ""
        if not label:
            label = "Imported profile"
        unique = self._unique_name(label, ctx)
        profile = self.repository.create(
            WorkProfile(
                id="",
                tenant_id=ctx.tenant.id if ctx.tenant is not None else "",
                owner_user_id=ctx.user.id,
                name=unique,
                description=str(payload.get("description") or "").strip(),
                spec=normalized,
                scope=resolved_scope,
                is_builtin=False,
                is_shared=False,
                version=1,
            )
        )
        return self.payload(profile, ctx)

    def _unique_name(self, label: str, ctx: AuthContext) -> str:
        tenant_id = ctx.tenant.id if ctx.tenant is not None else ""
        existing = {
            item.name
            for item in self.repository.list_visible(tenant_id, ctx.user.id)
        }
        if label not in existing:
            return label
        index = 2
        while f"{label} ({index})" in existing:
            index += 1
        return f"{label} ({index})"

    def sample_prompt(
        self,
        ctx: AuthContext,
        profile_id: str,
        topic: str | None = None,
        chars: int = 300,
    ) -> tuple[WorkProfile, str, int]:
        profile = self._require_readable(profile_id, ctx)
        spec = profile.spec
        target = int(chars or 300)
        target = max(SAMPLE_CHARS_MIN, min(SAMPLE_CHARS_MAX, target))
        subject = (topic or "").strip()
        if not subject:
            subject = f"A typical scenario around \"{profile.name or spec.meta.name or 'Example'}\""
        unit_name = spec.unit.name
        values = {
            "title": subject,
            "profile_name": profile.name or spec.meta.name,
            "unit_name": unit_name,
            "unit_plural": spec.unit.plural or unit_name,
            "min_units": spec.unit.min_units,
            "max_units": spec.unit.max_units,
            "words": target,
            "audience": "general readers",
            "tone": spec.voice.tone or "default tone",
            "pov_label": POV_LABELS.get(spec.voice.pov, spec.voice.pov),
            "tense_label": TENSE_LABELS.get(spec.voice.tense, spec.voice.tense),
            "policy_label": POLICY_LABELS.get(
                spec.grounding.citation_policy, spec.grounding.citation_policy
            ),
            "forbidden": ", ".join(spec.voice.forbidden_phrases) or "none",
            "depth": spec.structure.depth,
            "sections_lo": spec.structure.sections_per_unit[0],
            "sections_hi": spec.structure.sections_per_unit[1],
            "index": 1,
            "unit_title": subject,
            "sections": "core scenarios, key details, emotional progression",
            "instruction": "clearer and more specific",
        }
        base = self._render(spec.prompts.unit or UNIT_TEMPLATE, values)
        policy = (spec.grounding.citation_policy or "").strip()
        citation_rule = (
            "The body must not contain any citation marker of the form [E<number>]."
            if policy == "forbidden"
            else "If you cite evidence, use markers of the form [E<number>]."
            if policy == "required"
            else "Citing evidence is optional."
        )
        prompt = (
            f"{base}\n\nTrial-writing requirement: this is a short opening excerpt of the {unit_name}, about {target} words long. "
            f"Do not write the full {unit_name}, and do not output an outline, title description, or creation notes. {citation_rule}"
        )
        return profile, prompt, target

    def finalize_sample(
        self, profile: WorkProfile, text: str, target: int
    ) -> str:
        content = (text or "").strip()
        if (profile.spec.grounding.citation_policy or "").strip() == "forbidden":
            content = CITATION_MARKER.sub("", content).strip()
        if len(content) > SAMPLE_TEXT_MAX:
            content = content[:SAMPLE_TEXT_MAX]
        return content

    def preview(
        self, ctx: AuthContext, profile_id: str, sample: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        profile = self._require_readable(profile_id, ctx)
        spec = profile.spec
        data = dict(sample or {})
        unit_name = spec.unit.name
        values = {
            "title": str(data.get("title") or data.get("topic") or profile.name),
            "profile_name": profile.name or spec.meta.name,
            "unit_name": unit_name,
            "unit_plural": spec.unit.plural or unit_name,
            "min_units": spec.unit.min_units,
            "max_units": spec.unit.max_units,
            "words": spec.unit.default_words,
            "audience": str(data.get("audience") or "general readers"),
            "tone": spec.voice.tone or "default tone",
            "pov_label": POV_LABELS.get(spec.voice.pov, spec.voice.pov),
            "tense_label": TENSE_LABELS.get(spec.voice.tense, spec.voice.tense),
            "policy_label": POLICY_LABELS.get(
                spec.grounding.citation_policy, spec.grounding.citation_policy
            ),
            "forbidden": ", ".join(spec.voice.forbidden_phrases) or "none",
            "depth": spec.structure.depth,
            "sections_lo": spec.structure.sections_per_unit[0],
            "sections_hi": spec.structure.sections_per_unit[1],
            "index": int(data.get("index") or 1),
            "unit_title": str(data.get("unit_title") or data.get("title") or "Section one"),
            "sections": str(data.get("sections") or "core concepts, practice steps, common pitfalls"),
            "instruction": str(data.get("instruction") or "clearer and more specific"),
        }
        return {
            "profile_id": profile.id,
            "unit_name": unit_name,
            "system_prompt": self._render(spec.prompts.system or SYSTEM_TEMPLATE, values),
            "outline_prompt": self._render(spec.prompts.outline or OUTLINE_TEMPLATE, values),
            "unit_prompt": self._render(spec.prompts.unit or UNIT_TEMPLATE, values),
            "revise_prompt": self._render(spec.prompts.revise or REVISE_TEMPLATE, values),
        }

    def list_shares(
        self, ctx: AuthContext, profile_id: str, privileged: bool = False
    ) -> list[ProfileShare]:
        profile = self._require_readable(profile_id, ctx)
        if not self._can_manage_shares(profile, ctx, privileged):
            raise PermissionDeniedError("you do not have permission to view this creation profile's share list")
        return self.repository.list_shares(profile_id)

    def replace_shares(
        self,
        ctx: AuthContext,
        profile_id: str,
        items: Iterable[tuple[str, str]],
        privileged: bool = False,
    ) -> list[ProfileShare]:
        profile = self._load(profile_id)
        if not self._can_manage_shares(profile, ctx, privileged):
            raise PermissionDeniedError("only the creator can modify the share list")
        normalized: list[tuple[str, str]] = []
        for user_id, level in items:
            target = (user_id or "").strip()
            if not target:
                continue
            resolved = (level or "read").strip().lower()
            if resolved not in SHARE_LEVELS:
                raise ProfileInvalidError(f"unknown share level: {level}")
            normalized.append((target, resolved))
        return self.repository.replace_shares(profile_id, normalized)

    def share_payload(self, shares: Sequence[ProfileShare]) -> list[dict[str, Any]]:
        return [
            {
                "user_id": share.user_id,
                "user_email": share.user_email,
                "user_display_name": share.user_display_name,
                "level": share.level,
            }
            for share in shares
        ]

    def _can_manage_shares(
        self, profile: WorkProfile, ctx: AuthContext, privileged: bool
    ) -> bool:
        if privileged:
            return True
        if profile.is_builtin:
            return False
        if profile.owner_user_id == ctx.user.id:
            return True
        share = self.repository.get_share(profile.id, ctx.user.id)
        return share is not None and share.level == "manage"

    def _render(self, template: str, values: dict[str, Any]) -> str:
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace("{" + key + "}", str(value))
        return rendered.strip()

    def _error_message(self, errors: Sequence[dict[str, str]]) -> str:
        first = errors[0]
        return f"creation profile validation failed: {first.get('path') or 'spec'} {first.get('message')}"
