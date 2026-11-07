from __future__ import annotations

from typing import Any, Protocol, Sequence, runtime_checkable

from app.models.citation import Citation
from app.models.piece import Piece, PieceVersion, OutlineSection


@runtime_checkable
class PieceRepository(Protocol):
    def ensure_schema(self) -> None:
        ...

    def create(self, piece: Piece) -> Piece:
        ...

    def get(self, piece_id: str, tenant_id: str | None = None) -> Piece | None:
        ...

    def list(self, tenant_id: str | None = None, limit: int = 50) -> list[Piece]:
        ...

    def update(
        self,
        piece_id: str,
        outline: Sequence[OutlineSection] | None = None,
        content: str | None = None,
        status: str | None = None,
        last_mode: str | None = None,
        citations: Sequence[Citation] | None = None,
        title: str | None = None,
        profile: dict[str, Any] | None = None,
        target_words: int | None = None,
        profile_id: str | None = None,
        brief: str | None = None,
    ) -> Piece | None:
        ...

    def append_version(
        self,
        piece_id: str,
        content: str,
        outline: Sequence[OutlineSection] | None = None,
        citations: Sequence[Citation] | None = None,
        note: str = "",
        mode: str = "",
    ) -> tuple[Piece, PieceVersion] | None:
        ...

    def list_versions(self, piece_id: str) -> list[PieceVersion]:
        ...

    def get_version(self, piece_id: str, version: int) -> PieceVersion | None:
        ...

    def count_by_user(self, user_id: str) -> int:
        ...

    def transfer_by_user(
        self, user_id: str, target_user_id: str, tenant_ids: Sequence[str] = ()
    ) -> int:
        ...

    def delete(self, piece_id: str, tenant_id: str | None = None) -> bool:
        ...
