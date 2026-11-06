from __future__ import annotations

import secrets
import time
from typing import Any

from app.models.share_link import RESOURCE_TYPES, ShareLink
from app.ports.series_repository import SeriesRepository
from app.ports.piece_repository import PieceRepository
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
        series_repository: SeriesRepository,
        piece_repository: PieceRepository,
    ) -> None:
        self.repository = repository
        self.series_repository = series_repository
        self.piece_repository = piece_repository
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
            raise ValueError(f"unsupported share type: {resource_type}")
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
            raise ShareNotFoundError(f"share link not found: {link_id}")
        return True

    def resolve_public(self, token: str, client_ip: str = "") -> dict[str, Any]:
        self._guard_rate(client_ip, token)
        link = self.repository.get_by_token(token)
        if link is None:
            raise ShareNotFoundError("share link not found")
        if link.revoked:
            raise ShareRevokedError("the share link has been revoked")
        if link.expires_at and link.expires_at < time.time():
            raise ShareExpiredError("the share link has expired")
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
            raise ShareRateLimitedError("too many requests; please try again later")
        if len(self._hits) > 5000:
            self._hits = {key: (window, count)}

    def _content(self, link: ShareLink) -> dict[str, Any]:
        if link.resource_type == "series":
            return self._series_content(link)
        return self._piece_content(link)

    def _series_content(self, link: ShareLink) -> dict[str, Any]:
        series = self.series_repository.get_series(link.resource_id, link.tenant_id)
        if series is None:
            raise ShareNotFoundError("the shared content does not exist")
        units = self.series_repository.list_units(series.id)
        chapters = [
            {"title": unit.title, "content": unit.content}
            for unit in units
            if (unit.content or "").strip()
        ]
        return {
            "resource_type": "series",
            "title": series.title,
            "subtitle": series.subtitle,
            "author": "",
            "created_at": series.created_at,
            "chapters": chapters,
            "citations": [],
        }

    def _piece_content(self, link: ShareLink) -> dict[str, Any]:
        piece = self.piece_repository.get(link.resource_id)
        if piece is None or (piece.tenant_id and piece.tenant_id != link.tenant_id):
            raise ShareNotFoundError("the shared content does not exist")
        chapters = [
            {"title": section.title, "content": section.content}
            for section in piece.outline
            if (section.content or "").strip()
        ]
        citations = [
            {"source_name": item.source_name, "chunk_index": item.chunk_index}
            for item in piece.citations
        ]
        return {
            "resource_type": "piece",
            "title": piece.title,
            "subtitle": "",
            "author": "",
            "created_at": piece.created_at,
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
