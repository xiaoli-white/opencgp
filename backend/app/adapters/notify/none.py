from __future__ import annotations


class NullNotifier:
    name = "none"

    def available(self) -> bool:
        return False

    def send(self, to: str, subject: str, body: str, html: str | None = None) -> bool:
        print(f"[notify:none] to={to} subject={subject} body={body[:120]}")
        return False

    def healthcheck(self) -> bool:
        return False
