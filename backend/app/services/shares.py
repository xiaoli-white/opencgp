from __future__ import annotations

import secrets
import time
from typing import Any

from app.models.share_link import RESOURCE_TYPES, ShareLink
from app.ports.course_repository import CourseRepository
from app.ports.longform_repository import LongformRepository
from app.ports.share_repository import ShareRepository
from app.services.errors import (
    ShareExpiredError,
    ShareNotFoundError,
    ShareRateLimitedError,
    ShareRevokedError,
)

RATE_LIMIT_PER_MINUTE = 60


class ShareService:
    def __init__(
        self,
        repository: ShareRepository,
        course_repository: CourseRepository,
        longform_repository: LongformRepository,
    ) -> None:
        self.repository = repository
        self.course_repository = course_repository
        self.longform_repository = longform_repository
        self._hits: dict[str, tuple[float, int]] = {}

    def create(
        self,
        tenant_id: str,
        user_id: str,
        resource_type: str,
        resource_id: str,
        expires_in_days: int = 7,
    ) -> dict[str, Any]:
        if resource_type not in RESOURCE_TYPES:
            raise ValueError(f"不支持的分享类型: {resource_type}")
        token = secrets.token_urlsafe(24)
        days = int(expires_in_days or 0)
        link = self.repository.create(
            ShareLink(
                id="",
                tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
                token=token,
                expires_at=(time.time() + days * 86400) if days > 0 else 0.0,
                created_by=user_id,
            )
        )
        return self._payload(link)

    def list(
        self, tenant_id: str, resource_type: str = "", resource_id: str = ""
    ) -> list[dict[str, Any]]:
        return [
            self._payload(link)
            for link in self.repository.list(tenant_id, resource_type, resource_id)
        ]

    def revoke(self, tenant_id: str, link_id: str) -> bool:
        if not self.repository.revoke(link_id, tenant_id):
            raise ShareNotFoundError(f"分享链接不存在: {link_id}")
        return True

    def resolve_public(self, token: str, client_ip: str = "") -> dict[str, Any]:
        self._guard_rate(client_ip, token)
        link = self.repository.get_by_token(token)
        if link is None:
            raise ShareNotFoundError("分享链接不存在")
        if link.revoked:
            raise ShareRevokedError("分享链接已撤销")
        if link.expires_at and link.expires_at < time.time():
            raise ShareExpiredError("分享链接已过期")
        payload = self._content(link)
        self.repository.count_views(token)
        payload["expires_at"] = link.expires_at
        payload["view_count"] = link.view_count + 1
        return payload

    def _guard_rate(self, client_ip: str, token: str) -> None:
        key = client_ip or "unknown"
        now = time.time()
        window, count = self._hits.get(key, (now, 0))
        if now - window >= 60:
            window, count = now, 0
        count += 1
        self._hits[key] = (window, count)
        if count > RATE_LIMIT_PER_MINUTE:
            raise ShareRateLimitedError("访问过于频繁，请稍后再试")
        if len(self._hits) > 5000:
            self._hits = {key: (window, count)}

    def _content(self, link: ShareLink) -> dict[str, Any]:
        if link.resource_type == "course":
            return self._course_content(link)
        return self._longform_content(link)

    def _course_content(self, link: ShareLink) -> dict[str, Any]:
        course = self.course_repository.get_course(link.resource_id, link.tenant_id)
        if course is None:
            raise ShareNotFoundError("分享的内容不存在")
        lessons = self.course_repository.list_lessons(course.id)
        chapters = [
            {"title": lesson.title, "content": lesson.content}
            for lesson in lessons
            if (lesson.content or "").strip()
        ]
        return {
            "resource_type": "course",
            "title": course.title,
            "subtitle": course.subtitle,
            "author": "",
            "created_at": course.created_at,
            "chapters": chapters,
            "citations": [],
        }

    def _longform_content(self, link: ShareLink) -> dict[str, Any]:
        longform = self.longform_repository.get(link.resource_id)
        if longform is None or (longform.tenant_id and longform.tenant_id != link.tenant_id):
            raise ShareNotFoundError("分享的内容不存在")
        chapters = [
            {"title": section.title, "content": section.content}
            for section in longform.outline
            if (section.content or "").strip()
        ]
        citations = [
            {"source_name": item.source_name, "chunk_index": item.chunk_index}
            for item in longform.citations
        ]
        return {
            "resource_type": "longform",
            "title": longform.title,
            "subtitle": "",
            "author": "",
            "created_at": longform.created_at,
            "chapters": chapters,
            "citations": citations,
        }

    def _payload(self, link: ShareLink) -> dict[str, Any]:
        return {
            "id": link.id,
            "resource_type": link.resource_type,
            "resource_id": link.resource_id,
            "token": link.token,
            "url": f"/s/{link.token}",
            "expires_at": link.expires_at,
            "revoked": link.revoked,
            "view_count": link.view_count,
            "created_at": link.created_at,
        }
