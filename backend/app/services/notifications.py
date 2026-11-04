from __future__ import annotations

import time
from typing import Any

from app.ports.auth_repository import AuthRepository
from app.ports.notifier import Notifier

BRAND = "OpenCGP"


class NotificationService:
    def __init__(self, notifier: Notifier, auth_repository: AuthRepository) -> None:
        self.notifier = notifier
        self.auth_repository = auth_repository

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

    def password_reset(self, user: Any) -> None:
        self._notify_user(
            user,
            "密码已被管理员重置 / Password reset by admin",
            "你的登录密码已被管理员重置，请使用新密码登录并及时修改。\n\nYour password was reset by an administrator.",
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
        try:
            members = self.auth_repository.list_members("tenant_default")
        except Exception:
            members = []
        for member in members or []:
            if str(getattr(member, "role", "")) not in ("owner", "admin"):
                continue
            email = getattr(member, "user_email", "") or ""
            if email and email not in emails:
                emails.append(email)
        return emails


def _fmt(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
