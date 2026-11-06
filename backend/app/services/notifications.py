from __future__ import annotations

import time
from typing import Any

from app.models.auth import DEFAULT_USER_ID
from app.ports.auth_repository import AuthRepository
from app.ports.notifier import Notifier

BRAND = "OpenCGP"


class NotificationService:
    def __init__(
        self, notifier: Notifier, auth_repository: AuthRepository, admin_email: str = ""
    ) -> None:
        self.notifier = notifier
        self.auth_repository = auth_repository
        self.admin_email = admin_email or ""

    def registration_pending(self, user: Any) -> None:
        try:
            recipients = self._admins()
            subject = f"[{BRAND}] New user pending review"
            body = (
                f"A new user has registered and is awaiting review:\n\n"
                f"Display name: {getattr(user, 'display_name', '')}\n"
                f"Email: {getattr(user, 'email', '')}\n"
                f"Time: {_fmt(time.time())}\n\n"
                f"Sign in to OpenCGP -> Server settings -> User management to complete the review.\n\n"
                f"A new user is waiting for approval.\n"
                f"Name: {getattr(user, 'display_name', '')}\nEmail: {getattr(user, 'email', '')}\n"
            )
            for email in recipients:
                self.notifier.send(email, subject, body)
        except Exception as exc:
            print(f"[notify] registration_pending failed: {exc}")

    def registration_received(self, user: Any) -> None:
        self._notify_user(
            user,
            "Registration received",
            (
                f"Hello {getattr(user, 'display_name', '') or getattr(user, 'email', '')}:\n\n"
                f"Your registration has been submitted and is awaiting administrator review.\n\n"
                f"Display name: {getattr(user, 'display_name', '')}\n"
                f"Email: {getattr(user, 'email', '')}\n"
                f"Time: {_fmt(time.time())}\n\n"
                f"We will email you again once the review is complete.\n\n"
                f"Hello {getattr(user, 'display_name', '') or getattr(user, 'email', '')},\n\n"
                f"Your registration has been submitted and is waiting for administrator review.\n"
                f"Name: {getattr(user, 'display_name', '')}\n"
                f"Email: {getattr(user, 'email', '')}\n"
                f"Time: {_fmt(time.time())}\n\n"
                f"We will email you once it is reviewed.\n"
            ),
        )

    def registration_approved(self, user: Any) -> None:
        self._notify_user(
            user,
            "Account approved",
            "Your account has been approved. You can now sign in to OpenCGP and start creating.",
        )

    def registration_rejected(self, user: Any, reason: str = "") -> None:
        tail = f"\n\nReason: {reason}" if reason else ""
        self._notify_user(
            user,
            "Account rejected",
            f"Your registration was not approved.{tail}"
            + (f"\nReason: {reason}" if reason else ""),
        )

    def password_reset(self, user: Any, password: str = "") -> None:
        self._notify_user(
            user,
            "Password reset by admin",
            (
                f"Your sign-in password has been reset by an administrator.\n\n"
                f"New password: {password}\n\n"
                f"Please change it immediately after signing in.\n\n"
                f"Your password has been reset by an administrator.\n\n"
                f"New password: {password}\n\n"
                f"Please change it immediately after signing in."
            ),
        )

    def send_test(self, to: str) -> dict[str, Any]:
        backend = getattr(self.notifier, "name", "none")
        if not self.notifier.available():
            return {"ok": False, "backend": backend, "detail": "SMTP is not configured"}
        ok = self.notifier.send(
            to, f"[{BRAND}] SMTP test", "This is a test email from OpenCGP."
        )
        return {
            "ok": bool(ok),
            "backend": backend,
            "detail": "" if ok else "sending failed; check the SMTP configuration and logs",
        }

    def _notify_user(self, user: Any, subject: str, body: str) -> None:
        try:
            email = getattr(user, "email", "") or ""
            if not email:
                return
            self.notifier.send(email, f"[{BRAND}] {subject}", body)
        except Exception as exc:
            print(f"[notify] direct send failed: {exc}")

    def _admins(self) -> list[str]:
        emails: list[str] = []
        seen: set[str] = set()
        try:
            active_users = {
                user.id: user
                for user in self.auth_repository.list_users(status="active", limit=100000)
                if user.status == "active" and float(user.deleted_at or 0) <= 0
            }
        except Exception:
            active_users = {}
        try:
            tenants = self.auth_repository.list_tenants()
        except Exception:
            tenants = []

        def add(user_id: str, email: str) -> None:
            address = (email or "").strip().lower()
            if not address or address in seen or user_id == DEFAULT_USER_ID:
                return
            seen.add(address)
            emails.append(address)

        for tenant in tenants:
            try:
                members = self.auth_repository.list_members(tenant.id)
            except Exception:
                continue
            for member in members:
                if str(getattr(member, "role", "")) not in ("owner", "admin"):
                    continue
                user = active_users.get(member.user_id)
                if user is None:
                    continue
                add(member.user_id, getattr(member, "user_email", "") or user.email)

        for tenant in tenants:
            try:
                roles = self.auth_repository.list_roles(tenant.id)
            except Exception:
                continue
            managed = {
                role.key for role in roles if "manage_server" in set(role.actions or [])
            }
            if not managed:
                continue
            try:
                members = self.auth_repository.list_members(tenant.id)
            except Exception:
                continue
            for member in members:
                if str(getattr(member, "role", "")) not in managed:
                    continue
                user = active_users.get(member.user_id)
                if user is None:
                    continue
                add(member.user_id, getattr(member, "user_email", "") or user.email)

        for item in (self.admin_email or "").split(","):
            address = item.strip().lower()
            if address and address not in seen:
                seen.add(address)
                emails.append(address)

        if not emails:
            for user in sorted(
                active_users.values(), key=lambda item: float(item.created_at or 0)
            ):
                address = (getattr(user, "email", "") or "").strip().lower()
                if address:
                    emails.append(address)
                    break
        return emails


def _fmt(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
