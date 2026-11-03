from __future__ import annotations

import json
import time
from typing import Any, Mapping

from app.models.research import ResearchRun
from app.ports.database import Database
from app.ports.research_repository import ResearchRepository

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS research_runs (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        user_id TEXT NOT NULL DEFAULT '',
        topic TEXT NOT NULL,
        depth INTEGER NOT NULL DEFAULT 2,
        status TEXT NOT NULL DEFAULT 'queued',
        brief_json TEXT NOT NULL DEFAULT '{}',
        citations_json TEXT NOT NULL DEFAULT '[]',
        questions_json TEXT NOT NULL DEFAULT '[]',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_research_runs_tenant ON research_runs(tenant_id, created_at)",
)


class DatabaseResearchRepository(ResearchRepository):
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        self._schema_ready = True

    def save(self, run: ResearchRun) -> ResearchRun:
        self.ensure_schema()
        now = time.time()
        created = run.created_at or now
        payload = {
            "brief": run.brief.model_dump(),
            "provider": run.provider,
            "warning": run.warning,
            "web_used": run.web_used,
        }
        self.database.execute(
            """
            INSERT INTO research_runs
                (id, tenant_id, user_id, topic, depth, status,
                 brief_json, citations_json, questions_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                tenant_id = excluded.tenant_id,
                user_id = excluded.user_id,
                topic = excluded.topic,
                depth = excluded.depth,
                status = excluded.status,
                brief_json = excluded.brief_json,
                citations_json = excluded.citations_json,
                questions_json = excluded.questions_json,
                updated_at = excluded.updated_at
            """,
            (
                run.id,
                run.tenant_id,
                run.user_id,
                run.topic,
                int(run.depth),
                run.status,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(
                    [citation.model_dump() for citation in run.citations],
                    ensure_ascii=False,
                ),
                json.dumps(run.questions, ensure_ascii=False),
                created,
                now,
            ),
        )
        return run.model_copy(update={"created_at": created, "updated_at": now})

    def get(self, run_id: str, tenant_id: str | None = None) -> ResearchRun | None:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT * FROM research_runs WHERE id = ?", (run_id,)
        )
        if row is None:
            return None
        if tenant_id is not None and _row_tenant(row) != (tenant_id or ""):
            return None
        return _row_to_run(row)

    def list(self, tenant_id: str | None = None, limit: int = 50) -> list[ResearchRun]:
        self.ensure_schema()
        if tenant_id is None:
            rows = self.database.fetchall(
                "SELECT * FROM research_runs ORDER BY created_at DESC LIMIT ?",
                (int(limit),),
            )
        else:
            rows = self.database.fetchall(
                "SELECT * FROM research_runs WHERE tenant_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (tenant_id or "", int(limit)),
            )
        return [_row_to_run(row) for row in rows]

    def delete(self, run_id: str, tenant_id: str | None = None) -> bool:
        self.ensure_schema()
        existing = self.get(run_id, tenant_id)
        if existing is None:
            return False
        self.database.execute("DELETE FROM research_runs WHERE id = ?", (run_id,))
        return True


def _row_tenant(row: Mapping[str, Any]) -> str:
    return str(row["tenant_id"] or "")


def _load_json(raw: Any, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except (TypeError, ValueError):
        return fallback


def _row_to_run(row: Mapping[str, Any]) -> ResearchRun:
    payload = _load_json(row["brief_json"], {})
    if not isinstance(payload, dict):
        payload = {}
    brief = payload.get("brief")
    if not isinstance(brief, dict):
        brief = payload
    citations = _load_json(row["citations_json"], [])
    questions = _load_json(row["questions_json"], [])
    return ResearchRun(
        id=str(row["id"]),
        tenant_id=_row_tenant(row),
        user_id=str(row["user_id"] or ""),
        topic=str(row["topic"] or ""),
        depth=int(row["depth"] or 1),
        status=str(row["status"] or ""),
        brief=brief if isinstance(brief, dict) else {},
        citations=citations if isinstance(citations, list) else [],
        questions=[str(item) for item in questions] if isinstance(questions, list) else [],
        provider=str(payload.get("provider") or ""),
        warning=str(payload.get("warning") or ""),
        web_used=int(payload.get("web_used") or 0),
        created_at=float(row["created_at"] or 0.0),
        updated_at=float(row["updated_at"] or 0.0),
    )
