from __future__ import annotations

from typing import Any, Sequence

from app.models.creation_profile import CreationProfile
from app.ports.creation_profile_repository import CreationProfileRepository
from app.services.errors import CreationProfileNotFoundError, PermissionDeniedError

GENRES = ("article", "report", "essay", "tutorial", "custom")
CITATION_POLICIES = ("required", "optional", "forbidden")


class CreationProfileService:
    def __init__(self, repository: CreationProfileRepository) -> None:
        self.repository = repository

    def list(self, tenant_id: str, user_id: str) -> list[dict[str, Any]]:
        items = self.repository.list_visible(tenant_id, user_id)
        return [self.payload(item, user_id) for item in items]

    def get(self, profile_id: str, tenant_id: str) -> CreationProfile:
        item = self.repository.get(profile_id, tenant_id)
        if item is None:
            raise CreationProfileNotFoundError(f"模板不存在: {profile_id}")
        return item

    def create(
        self,
        tenant_id: str,
        user_id: str,
        name: str,
        genre: str = "article",
        tone: str = "",
        audience: str = "",
        pov: str = "",
        citation_policy: str = "optional",
        target_words: int = 3000,
        is_shared: bool = False,
    ) -> CreationProfile:
        label = (name or "").strip()
        if not label:
            raise ValueError("模板名称不能为空")
        resolved_genre = (genre or "article").strip().lower()
        if resolved_genre not in GENRES:
            raise ValueError(f"未知体裁: {resolved_genre}")
        resolved_policy = (citation_policy or "optional").strip().lower()
        if resolved_policy not in CITATION_POLICIES:
            raise ValueError(f"未知引用策略: {resolved_policy}")
        return self.repository.create(
            CreationProfile(
                id="",
                tenant_id=tenant_id,
                user_id=user_id,
                name=label,
                genre=resolved_genre,
                tone=(tone or "").strip(),
                audience=(audience or "").strip(),
                pov=(pov or "").strip(),
                citation_policy=resolved_policy,
                target_words=max(200, min(int(target_words or 3000), 50000)),
                is_shared=bool(is_shared),
            )
        )

    def update(
        self,
        profile_id: str,
        tenant_id: str,
        user_id: str,
        name: str | None = None,
        genre: str | None = None,
        tone: str | None = None,
        audience: str | None = None,
        pov: str | None = None,
        citation_policy: str | None = None,
        target_words: int | None = None,
        is_shared: bool | None = None,
    ) -> CreationProfile:
        item = self.get(profile_id, tenant_id)
        self._require_owner(item, user_id)
        if genre is not None:
            resolved_genre = genre.strip().lower()
            if resolved_genre not in GENRES:
                raise ValueError(f"未知体裁: {resolved_genre}")
            genre = resolved_genre
        if citation_policy is not None:
            resolved_policy = citation_policy.strip().lower()
            if resolved_policy not in CITATION_POLICIES:
                raise ValueError(f"未知引用策略: {resolved_policy}")
            citation_policy = resolved_policy
        if name is not None and not name.strip():
            raise ValueError("模板名称不能为空")
        updated = self.repository.update(
            profile_id,
            name=None if name is None else name.strip(),
            genre=genre,
            tone=tone,
            audience=audience,
            pov=pov,
            citation_policy=citation_policy,
            target_words=target_words,
            is_shared=is_shared,
        )
        if updated is None:
            raise CreationProfileNotFoundError(f"模板不存在: {profile_id}")
        return updated

    def delete(self, profile_id: str, tenant_id: str, user_id: str) -> bool:
        item = self.get(profile_id, tenant_id)
        self._require_owner(item, user_id)
        return self.repository.delete(profile_id, tenant_id)

    def payload(self, item: CreationProfile, user_id: str) -> dict[str, Any]:
        data = item.model_dump()
        data["is_owner"] = item.user_id == user_id
        return data

    def _require_owner(self, item: CreationProfile, user_id: str) -> None:
        if item.user_id and item.user_id != user_id:
            raise PermissionDeniedError("只有模板归属者可以修改")
