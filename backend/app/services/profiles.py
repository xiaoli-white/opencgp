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
        "name": "技术教程",
        "description": "面向工程实践的分步教程，强调可引用证据与结构完整性",
        "spec": {
            "meta": {"name": "技术教程", "description": "分步技术教程", "tags": ["技术", "教程"], "icon": "book"},
            "unit": {"name": "讲", "plural": "讲", "min_units": 1, "max_units": 60, "default_words": 900},
            "structure": {"depth": 2, "sections_per_unit": [2, 5], "requires_outline": True},
            "voice": {"tone": "清晰、务实", "pov": "third_limited", "tense": "present"},
            "grounding": {"citation_policy": "required", "min_evidence": 1, "allow_web": False},
            "assets": {"glossary": True, "setting_book": False, "character_sheet": False},
            "validation": {"validators": ["citation", "structure"], "strictness": "strict"},
            "export": {"default_format": "md", "include_citations": True},
        },
    },
    {
        "key": "article",
        "name": "技术长文",
        "description": "适合技术博客与深度文章的自由写作配置",
        "spec": {
            "meta": {"name": "技术长文", "description": "技术深度长文", "tags": ["技术", "长文"], "icon": "article"},
            "unit": {"name": "节", "plural": "节", "min_units": 3, "max_units": 20, "default_words": 1200},
            "structure": {"depth": 2, "sections_per_unit": [2, 4], "requires_outline": True},
            "voice": {"tone": "专业、克制", "pov": "third_limited", "tense": "present"},
            "grounding": {"citation_policy": "optional", "min_evidence": 0, "allow_web": True},
            "assets": {"glossary": False, "setting_book": False, "character_sheet": False},
            "validation": {"validators": ["length"], "strictness": "normal"},
            "export": {"default_format": "md", "include_citations": True},
        },
    },
    {
        "key": "novel",
        "name": "小说",
        "description": "长篇虚构叙事配置，包含设定集与人物卡",
        "spec": {
            "meta": {"name": "小说", "description": "虚构叙事", "tags": ["小说", "叙事"], "icon": "feather"},
            "unit": {"name": "章", "plural": "章", "min_units": 5, "max_units": 200, "default_words": 3000},
            "structure": {"depth": 3, "sections_per_unit": [3, 6], "requires_outline": True},
            "voice": {"tone": "叙事性强", "pov": "third_limited", "tense": "past"},
            "grounding": {"citation_policy": "forbidden", "min_evidence": 0, "allow_web": False},
            "assets": {"glossary": False, "setting_book": True, "character_sheet": True},
            "validation": {"validators": ["continuity", "length"], "strictness": "normal"},
            "export": {"default_format": "md", "include_citations": False},
        },
    },
    {
        "key": "report",
        "name": "研究报告",
        "description": "结构化的研究报告，要求引用与篇幅双重校验",
        "spec": {
            "meta": {"name": "研究报告", "description": "研究分析报告", "tags": ["研究", "报告"], "icon": "chart"},
            "unit": {"name": "部分", "plural": "部分", "min_units": 3, "max_units": 12, "default_words": 1500},
            "structure": {"depth": 3, "sections_per_unit": [2, 5], "requires_outline": True},
            "voice": {"tone": "客观、严谨", "pov": "third_omniscient", "tense": "present"},
            "grounding": {"citation_policy": "required", "min_evidence": 1, "allow_web": True},
            "assets": {"glossary": True, "setting_book": False, "character_sheet": False},
            "validation": {"validators": ["citation", "length"], "strictness": "strict"},
            "export": {"default_format": "pdf", "include_citations": True},
        },
    },
    {
        "key": "essay",
        "name": "随笔",
        "description": "第一人称自由随笔，不要求引用",
        "spec": {
            "meta": {"name": "随笔", "description": "个人随笔", "tags": ["随笔", "散文"], "icon": "pen"},
            "unit": {"name": "段", "plural": "段", "min_units": 1, "max_units": 30, "default_words": 600},
            "structure": {"depth": 1, "sections_per_unit": [1, 3], "requires_outline": False},
            "voice": {"tone": "松弛、个人化", "pov": "first", "tense": "present"},
            "grounding": {"citation_policy": "forbidden", "min_evidence": 0, "allow_web": False},
            "assets": {"glossary": False, "setting_book": False, "character_sheet": False},
            "validation": {"validators": ["length"], "strictness": "loose"},
            "export": {"default_format": "md", "include_citations": False},
        },
    },
)

POV_LABELS = {"first": "第一人称", "third_limited": "第三人称限知", "third_omniscient": "第三人称全知"}
TENSE_LABELS = {"present": "现在时", "past": "过去时"}
POLICY_LABELS = {"required": "必须引用证据", "optional": "可选引用", "forbidden": "不得引用"}

SYSTEM_TEMPLATE = (
    "你是《{title}》的创作助手，正在按「{profile_name}」配置写作。\n"
    "写作单位：{unit_name}，每个{unit_name}约 {words} 字，共 {min_units}-{max_units} 个{unit_name}。\n"
    "目标读者：{audience}。\n"
    "语气：{tone}；人称：{pov_label}；时态：{tense_label}。\n"
    "引用策略：{policy_label}；禁止使用以下表达：{forbidden}。\n"
    "每个{unit_name}需拆成 {sections_lo}-{sections_hi} 个要点，大纲深度 {depth} 层。"
)

OUTLINE_TEMPLATE = (
    "为《{title}》设计大纲，配置为「{profile_name}」。\n"
    "要求：共 {min_units}-{max_units} 个{unit_name}，每个{unit_name}包含 {sections_lo}-{sections_hi} 个要点，"
    "每个{unit_name}标注约 {words} 字。\n"
    "输出 JSON 数组，元素包含 id、title、summary、target_words 字段。"
)

UNIT_TEMPLATE = (
    "撰写《{title}》的第 {index} 个{unit_name}，标题为「{unit_title}」，约 {words} 字。\n"
    "读者：{audience}；语气：{tone}；人称：{pov_label}。\n"
    "需要覆盖的要点：{sections}。\n"
    "引用策略：{policy_label}。"
)

REVISE_TEMPLATE = (
    "根据以下意见修改《{title}》中「{unit_title}」的内容，保持{unit_name}结构与 {words} 字左右篇幅。\n"
    "修改意见：{instruction}"
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
            raise ProfileNotFoundError(f"创作配置不存在: {profile_id}")
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
            raise ProfileNotFoundError(f"创作配置不存在: {profile_id}")
        return profile

    def _require_editable(self, profile_id: str, ctx: AuthContext) -> WorkProfile:
        profile = self._load(profile_id)
        if profile.is_builtin:
            raise BuiltinProfileError("内置预设不可修改，请先复制")
        if not self.can_edit(profile, ctx):
            raise PermissionDeniedError("没有修改该创作配置的权限")
        return profile

    def payload(self, profile: WorkProfile, ctx: AuthContext) -> dict[str, Any]:
        share = self.repository.get_share(profile.id, ctx.user.id)
        is_owner = bool(profile.owner_user_id) and profile.owner_user_id == ctx.user.id
        owner_name = profile.owner_name or ("系统内置" if profile.is_builtin else "")
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
            raise ProfileInvalidError("创作配置名称不能为空")
        resolved_scope = (scope or SCOPE_USER).strip().lower()
        if resolved_scope not in PROFILE_SCOPES:
            raise ProfileInvalidError(f"未知作用域: {scope}")
        if resolved_scope != SCOPE_USER and not ctx.can("manage_server"):
            raise PermissionDeniedError("非个人作用域需要 manage_server 权限")
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
        label = (name or "").strip() or f"{source.name} 副本"
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
            raise ProfileInvalidError("创作配置名称不能为空")
        updated = self.repository.update(
            profile_id,
            name=label,
            description=None if description is None else (description or "").strip(),
            spec=normalized,
            is_shared=is_shared,
            bump_version=normalized is not None,
        )
        if updated is None:
            raise ProfileNotFoundError(f"创作配置不存在: {profile_id}")
        return self.payload(updated, ctx)

    def delete(self, ctx: AuthContext, profile_id: str) -> dict[str, Any]:
        self._require_editable(profile_id, ctx)
        used = self.repository.count_usage(profile_id)
        if used > 0:
            raise ProfileInUseError(f"仍有 {used} 个作品在使用该配置")
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
            raise ProfileInvalidError("导入数据必须是 JSON 对象")
        if "format" in payload:
            if str(payload.get("format") or "") != EXPORT_FORMAT:
                raise ProfileInvalidError(
                    f"不支持的导入格式: {payload.get('format') or '空'}"
                )
            try:
                version = int(payload.get("version"))
            except (TypeError, ValueError):
                raise ProfileInvalidError("导入版本号必须是整数")
            if version != EXPORT_VERSION:
                raise ProfileInvalidError(f"不支持的导入版本: {version}")
        if "spec" not in payload:
            raise ProfileInvalidError("导入数据缺少 spec 字段")
        spec_raw = payload.get("spec")
        normalized, errors, _warnings = normalize_spec(spec_raw)
        if errors:
            raise ProfileInvalidError(self._error_message(errors), errors=errors)
        resolved_scope = (scope or SCOPE_USER).strip().lower()
        if resolved_scope not in PROFILE_SCOPES:
            raise ProfileInvalidError(f"未知作用域: {scope}")
        if resolved_scope != SCOPE_USER and not ctx.can("manage_server"):
            raise PermissionDeniedError("非个人作用域需要 manage_server 权限")
        label = (name or "").strip()
        if not label:
            label = str(payload.get("name") or "").strip()
        if not label:
            label = str(payload.get("spec", {}).get("meta", {}).get("name") or "").strip() if isinstance(payload.get("spec"), dict) else ""
        if not label:
            label = "导入配置"
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
            subject = f"围绕「{profile.name or spec.meta.name or '示例'}」的一个典型场景"
        unit_name = spec.unit.name
        values = {
            "title": subject,
            "profile_name": profile.name or spec.meta.name,
            "unit_name": unit_name,
            "unit_plural": spec.unit.plural or unit_name,
            "min_units": spec.unit.min_units,
            "max_units": spec.unit.max_units,
            "words": target,
            "audience": "通用读者",
            "tone": spec.voice.tone or "默认语气",
            "pov_label": POV_LABELS.get(spec.voice.pov, spec.voice.pov),
            "tense_label": TENSE_LABELS.get(spec.voice.tense, spec.voice.tense),
            "policy_label": POLICY_LABELS.get(
                spec.grounding.citation_policy, spec.grounding.citation_policy
            ),
            "forbidden": "、".join(spec.voice.forbidden_phrases) or "无",
            "depth": spec.structure.depth,
            "sections_lo": spec.structure.sections_per_unit[0],
            "sections_hi": spec.structure.sections_per_unit[1],
            "index": 1,
            "unit_title": subject,
            "sections": "核心场景、关键细节、情绪推进",
            "instruction": "更清晰、更具体",
        }
        base = self._render(spec.prompts.unit or UNIT_TEMPLATE, values)
        policy = (spec.grounding.citation_policy or "").strip()
        citation_rule = (
            "正文禁止出现任何 [E数字] 形式的引用标记。"
            if policy == "forbidden"
            else "如需引用证据，请使用 [E数字] 标记。"
            if policy == "required"
            else "引用证据可选。"
        )
        prompt = (
            f"{base}\n\n试写要求：这是该{unit_name}的开头一小段，篇幅约 {target} 字，"
            f"不要写完整{unit_name}，不要输出大纲、标题说明或创作说明。{citation_rule}"
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
            "audience": str(data.get("audience") or "通用读者"),
            "tone": spec.voice.tone or "默认语气",
            "pov_label": POV_LABELS.get(spec.voice.pov, spec.voice.pov),
            "tense_label": TENSE_LABELS.get(spec.voice.tense, spec.voice.tense),
            "policy_label": POLICY_LABELS.get(
                spec.grounding.citation_policy, spec.grounding.citation_policy
            ),
            "forbidden": "、".join(spec.voice.forbidden_phrases) or "无",
            "depth": spec.structure.depth,
            "sections_lo": spec.structure.sections_per_unit[0],
            "sections_hi": spec.structure.sections_per_unit[1],
            "index": int(data.get("index") or 1),
            "unit_title": str(data.get("unit_title") or data.get("title") or "第一节"),
            "sections": str(data.get("sections") or "核心概念、实践步骤、常见误区"),
            "instruction": str(data.get("instruction") or "更清晰、更具体"),
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
            raise PermissionDeniedError("没有查看该创作配置共享列表的权限")
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
            raise PermissionDeniedError("只有创建者可以修改共享列表")
        normalized: list[tuple[str, str]] = []
        for user_id, level in items:
            target = (user_id or "").strip()
            if not target:
                continue
            resolved = (level or "read").strip().lower()
            if resolved not in SHARE_LEVELS:
                raise ProfileInvalidError(f"未知共享等级: {level}")
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
        return f"创作配置校验失败：{first.get('path') or 'spec'} {first.get('message')}"
