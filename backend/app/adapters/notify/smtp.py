from __future__ import annotations

import smtplib
from email.message import EmailMessage


class SMTPNotifier:
    name = "smtp"

    def __init__(
        self,
        host: str = "",
        port: int = 587,
        user: str = "",
        password: str = "",
        sender: str = "",
        use_tls: bool = True,
        timeout: float = 10.0,
    ) -> None:
        self.host = (host or "").strip()
        self.port = int(port or 587)
        self.user = user
        self.password = password
        self.sender = (sender or user or "").strip()
        self.use_tls = bool(use_tls)
        self.timeout = float(timeout or 10)

    def available(self) -> bool:
        return bool(self.host and self.sender)

    def healthcheck(self) -> bool:
        return self.available()

    def send(self, to: str, subject: str, body: str, html: str | None = None) -> bool:
        if not self.available() or not to:
            return False
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        if html:
            message.add_alternative(html, subtype="html")
        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as client:
                if self.use_tls:
                    client.starttls()
                if self.user:
                    client.login(self.user, self.password)
                client.send_message(message)
            return True
        except Exception as exc:
            print(f"[notify:smtp] failed to={to} error={exc}")
            return False
