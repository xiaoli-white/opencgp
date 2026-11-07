"""Edit locks acquired explicitly by a human editor.

Reads never touch the lock table.  A client that wants to edit a unit or a
piece calls the acquire endpoint; while it holds the lock it renews it with a
heartbeat.  Locks have a TTL, so a crashed editor or a lost tab never blocks
other work forever.

The lock table is shared by every API process; acquisition is a single
row-level conditional upsert, not an in-process set.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any, Mapping

from app.services.errors import (
    LockTokenMismatchError,
    UnitLockedError,
    UnitLockLostError,
)

RESOURCE_UNIT = "unit"
RESOURCE_PIECE = "piece"


@dataclass
class EditLock:
    """A row from the ``edit_locks`` table."""

    resource_type: str
    resource_id: str
    tenant_id: str = ""
    user_id: str = ""
    user_name: str = ""
    token: str = ""
    heartbeat_at: float = 0.0
    expires_at: float = 0.0

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "EditLock":
        return cls(
            resource_type=str(row.get("resource_type") or ""),
            resource_id=str(row.get("resource_id") or ""),
            tenant_id=str(row.get("tenant_id") or ""),
            user_id=str(row.get("user_id") or ""),
            user_name=str(row.get("user_name") or ""),
            token=str(row.get("token") or ""),
            heartbeat_at=float(row.get("heartbeat_at") or 0.0),
            expires_at=float(row.get("expires_at") or 0.0),
        )

    def model_dump(self, viewer_id: str = "") -> dict[str, Any]:
        """Return the public lock payload.

        The token is only returned to the user who owns the lock; other
        viewers see the holder name and expiry but cannot hijack the lock.
        """
        mine = bool(viewer_id) and self.user_id == viewer_id
        payload: dict[str, Any] = {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "heartbeat_at": self.heartbeat_at,
            "expires_at": self.expires_at,
            "is_mine": mine,
            "token": self.token if mine else "",
        }
        # Keep the legacy unit-lock payload shape for older clients.
        if self.resource_type == RESOURCE_UNIT:
            payload["unit_id"] = self.resource_id
        elif self.resource_type == RESOURCE_PIECE:
            payload["piece_id"] = self.resource_id
        return payload


class LockService:
    def __init__(self, repository: Any, ttl_seconds: int = 120) -> None:
        self.repository = repository
        self.ttl_seconds = max(10, int(ttl_seconds))

    # ------------------------------------------------------------------
    # Generic resource operations
    # ------------------------------------------------------------------

    def get_edit(self, resource_type: str, resource_id: str) -> EditLock | None:
        getter = getattr(self.repository, "get_edit_lock", None)
        if callable(getter):
            row = getter(resource_type, resource_id)
        else:  # Defensive fallback for older lock repositories.
            row = self.repository.get_lock(resource_id)
            if row is not None and hasattr(row, "model_dump"):
                row = row.model_dump()
        if row is None:
            return None
        lock = EditLock.from_row(row) if isinstance(row, Mapping) else row
        if lock.expires_at <= time.time():
            deleter = getattr(self.repository, "delete_expired_edit_locks", None)
            if callable(deleter):
                deleter(resource_type, resource_id, time.time())
            return None
        return lock

    def acquire_edit(
        self,
        resource_type: str,
        resource_id: str,
        tenant_id: str,
        user_id: str,
        user_name: str,
        force: bool = False,
    ) -> EditLock:
        now = time.time()
        token = secrets.token_urlsafe(16)
        expires_at = now + self.ttl_seconds
        method = getattr(self.repository, "try_acquire_edit_lock", None)
        if callable(method):
            acquired, row = method(
                resource_type,
                resource_id,
                tenant_id,
                user_id,
                user_name or user_id,
                token,
                now,
                expires_at,
                bool(force),
            )
            if acquired and row is not None:
                return EditLock.from_row(row)
            if row is not None:
                holder = EditLock.from_row(row)
                name = holder.user_name or holder.user_id
                raise UnitLockedError(name, holder)
            raise UnitLockedError("another member", None)
        # Fallback: only used by an alternative repository implementation.
        current = self.get_edit(resource_type, resource_id)
        if current is not None and current.user_id != user_id and not force:
            raise UnitLockedError(current.user_name or current.user_id, current)
        lock = EditLock(
            resource_type=resource_type,
            resource_id=resource_id,
            tenant_id=tenant_id,
            user_id=user_id,
            user_name=user_name or user_id,
            token=token,
            heartbeat_at=now,
            expires_at=expires_at,
        )
        return self.repository.save_lock(lock)  # type: ignore[arg-type]

    def heartbeat_edit(
        self, resource_type: str, resource_id: str, token: str
    ) -> EditLock:
        now = time.time()
        expires_at = now + self.ttl_seconds
        renew = getattr(self.repository, "renew_edit_lock", None)
        if callable(renew):
            renewed = renew(
                resource_type, resource_id, token or "", now, expires_at
            )
        else:
            current = self.get_edit(resource_type, resource_id)
            renewed = bool(current is not None and current.token == (token or ""))
            if renewed:
                self.repository.save_lock(current)  # type: ignore[arg-type]
        if not renewed:
            raise UnitLockLostError(
                "the lock is no longer valid; acquire the edit lock again"
            )
        current = self.get_edit(resource_type, resource_id)
        if current is None or current.token != (token or ""):
            raise UnitLockLostError(
                "the lock is no longer valid; acquire the edit lock again"
            )
        return current

    def release_edit(self, resource_type: str, resource_id: str, token: str) -> None:
        deleter = getattr(self.repository, "delete_edit_lock", None)
        if callable(deleter):
            if deleter(resource_type, resource_id, token or ""):
                return
        else:
            current = self.get_edit(resource_type, resource_id)
            if current is None:
                return
            if current.token != (token or ""):
                raise LockTokenMismatchError(
                    "lock token mismatch; cannot release an edit lock held by someone else"
                )
            self.repository.delete_lock(resource_id)
            return
        current = self.get_edit(resource_type, resource_id)
        if current is None:
            return
        raise LockTokenMismatchError(
            "lock token mismatch; cannot release an edit lock held by someone else"
        )

    def release_for_user(
        self, resource_type: str, resource_id: str, user_id: str
    ) -> None:
        """Release a lock after the owner saves or closes the editor."""
        method = getattr(self.repository, "delete_edit_lock_for_user", None)
        if callable(method):
            method(resource_type, resource_id, user_id)
            return
        current = self.get_edit(resource_type, resource_id)
        if current is not None and current.user_id == user_id:
            self.repository.delete_lock(resource_id)

    def guard_edit(self, resource_type: str, resource_id: str, user_id: str) -> None:
        current = self.get_edit(resource_type, resource_id)
        if current is not None and current.user_id != user_id:
            raise UnitLockedError(current.user_name or current.user_id, current)

    def state_for(
        self, resource_type: str, resource_id: str, viewer_id: str
    ) -> dict[str, Any]:
        current = self.get_edit(resource_type, resource_id)
        if current is None:
            return {
                "state": "free",
                "is_mine": False,
                "locked_by_me": False,
                "locked_by_other": False,
                "lock": None,
            }
        mine = bool(viewer_id) and current.user_id == viewer_id
        return {
            "state": "mine" if mine else "other",
            "is_mine": mine,
            "locked_by_me": mine,
            "locked_by_other": not mine,
            "lock": current.model_dump(viewer_id),
        }

    # ------------------------------------------------------------------
    # Unit-specific compatibility wrappers
    # ------------------------------------------------------------------

    def get(self, unit_id: str) -> EditLock | None:
        return self.get_edit(RESOURCE_UNIT, unit_id)

    def acquire(
        self,
        unit_id: str,
        tenant_id: str,
        user_id: str,
        user_name: str,
        force: bool = False,
    ) -> EditLock:
        return self.acquire_edit(
            RESOURCE_UNIT, unit_id, tenant_id, user_id, user_name, force=force
        )

    def heartbeat(self, unit_id: str, token: str) -> EditLock:
        return self.heartbeat_edit(RESOURCE_UNIT, unit_id, token)

    def release(self, unit_id: str, token: str) -> None:
        return self.release_edit(RESOURCE_UNIT, unit_id, token)

    def guard(self, unit_id: str, user_id: str) -> None:
        return self.guard_edit(RESOURCE_UNIT, unit_id, user_id)
