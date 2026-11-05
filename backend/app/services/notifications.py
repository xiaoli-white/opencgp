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
            subject = f"[{BRAND}] 新用户待审核 / New user pending review"
            body = (
                f"有新用户注册并等待审核：\n\n"
                f"昵称：{getattr(user, 'display_name', '')}\n"
                f"邮箱：{getattr(user, 'email', '')}\n"
                f"时间：{_fmt(time.time())}\n\n"
                f"请登录 OpenCGP → 服务器设置 → 用户管理 完成审核。\n\n"
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
            "注册已提交 / Registration received",
            (
                f"你好 {getattr(user, 'display_name', '') or getattr(user, 'email', '')}：\n\n"
                f"你的注册申请已提交，正在等待管理员审核。\n\n"
                f"昵称：{getattr(user, 'display_name', '')}\n"
                f"邮箱：{getattr(user, 'email', '')}\n"
                f"时间：{_fmt(time.time())}\n\n"
                f"审核通过后我们会再次邮件通知你。\n\n"
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
            "账号已通过审核 / Account approved",
            "你的账号已通过审核，现在可以登录 OpenCGP 开始创作。\n\nYour account has been approved. You can sign in now.",
        )

    def registration_rejected(self, user: Any, reason: str = "") -> None:
        tail = f"\n\n原因：{reason}" if reason else ""
        self._notify_user(
            user,
            "账号审核未通过 / Account rejected",
            f"你的注册申请未通过审核。{tail}\n\nYour registration was not approved."
            + (f"\nReason: {reason}" if reason else ""),
        )

    def password_reset(self, user: Any, password: str = "") -> None:
        self._notify_user(
            user,
            "密码已被管理员重置 / Password reset by admin",
            (
                f"你的登录密码已被管理员重置。\n\n"
                f"新密码：{password}\n\n"
                f"登录后请立即修改密码。\n\n"
                f"Your password has been reset by an administrator.\n\n"
                f"New password: {password}\n\n"
                f"Please change it immediately after signing in."
            ),
        )

    def send_test(self, to: str) -> dict[str, Any]:
        backend = getattr(self.notifier, "name", "none")
        if not self.notifier.available():
            return {"ok": False, "backend": backend, "detail": "未配置 SMTP"}
        ok = self.notifier.send(
            to, f"[{BRAND}] 邮件通道测试 / SMTP test", "这是一封来自 OpenCGP 的测试邮件。"
        )
        return {
            "ok": bool(ok),
            "backend": backend,
            "detail": "" if ok else "发送失败，请检查 SMTP 配置与日志",
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
