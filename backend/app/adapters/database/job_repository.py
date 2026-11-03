from __future__ import annotations

import json
import time
from typing import Any, Mapping

from app.models.job import (
    ERROR_MAX_CHARS,
    STATUS_CANCELED,
    STATUS_QUEUED,
    STATUS_RUNNING,
    TERMINAL_STATUSES,
    Job,
)
from app.ports.database import Database

SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL DEFAULT '',
        user_id TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        payload_json TEXT NOT NULL DEFAULT '{}',
        result_json TEXT NOT NULL DEFAULT '',
        error TEXT NOT NULL DEFAULT '',
        progress REAL NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL DEFAULT 0,
        started_at REAL NOT NULL DEFAULT 0,
        finished_at REAL NOT NULL DEFAULT 0,
        updated_at REAL NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_jobs_tenant ON jobs(tenant_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)",
)

MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("jobs", "cancel_requested", "INTEGER NOT NULL DEFAULT 0"),
)


class DatabaseJobRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._schema_ready = False

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        for statement in SCHEMA:
            self.database.execute(statement)
        for table, column, ddl in MIGRATIONS:
            columns = {
                str(row["name"])
                for row in self.database.fetchall(f"PRAGMA table_info({table})")
            }
            if not columns:
                continue
            if column not in columns:
                self.database.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        self._schema_ready = True

    def create(self, job: Job) -> Job:
        self.ensure_schema()
        self.database.execute(
            "INSERT INTO jobs (id, tenant_id, user_id, kind, status, payload_json,"
            " result_json, error, progress, attempts, cancel_requested, created_at,"
            " started_at, finished_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job.id,
                job.tenant_id,
                job.user_id,
                job.kind,
                job.status,
                json.dumps(job.payload, ensure_ascii=False),
                json.dumps(job.result, ensure_ascii=False) if job.result else "",
                job.error,
                float(job.progress),
                int(job.attempts),
                1 if job.cancel_requested else 0,
                job.created_at,
                job.started_at,
                job.finished_at,
                job.updated_at,
            ),
        )
        return job

    def get(self, job_id: str) -> Job | None:
        self.ensure_schema()
        row = self.database.fetchone("SELECT * FROM jobs WHERE id = ?", (job_id,))
        if row is None:
            return None
        return _job_from_row(row)

    def list(
        self,
        tenant_id: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 20,
    ) -> list[Job]:
        self.ensure_schema()
        clauses: list[str] = []
        params: list[Any] = []
        if tenant_id:
            clauses.append("tenant_id = ?")
            params.append(tenant_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(int(limit or 20), 200)))
        rows = self.database.fetchall(
            f"SELECT * FROM jobs{where} ORDER BY created_at DESC LIMIT ?", tuple(params)
        )
        return [_job_from_row(row) for row in rows]

    def update_status(
        self,
        job_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: str = "",
    ) -> Job | None:
        self.ensure_schema()
        now = time.time()
        current = self.get(job_id)
        if current is None:
            return None
        started_at = current.started_at
        if status == STATUS_RUNNING and not started_at:
            started_at = now
        finished_at = now if status in TERMINAL_STATUSES else 0.0
        progress = 1.0 if status == "succeeded" else current.progress
        attempts = current.attempts + 1 if status == STATUS_RUNNING else current.attempts
        self.database.execute(
            "UPDATE jobs SET status = ?, result_json = ?, error = ?, progress = ?,"
            " attempts = ?, started_at = ?, finished_at = ?, updated_at = ?"
            " WHERE id = ?",
            (
                status,
                json.dumps(result, ensure_ascii=False) if result is not None else "",
                (error or "")[:ERROR_MAX_CHARS],
                float(progress),
                int(attempts),
                float(started_at),
                float(finished_at),
                now,
                job_id,
            ),
        )
        return self.get(job_id)

    def update_progress(self, job_id: str, progress: float) -> None:
        self.ensure_schema()
        value = max(0.0, min(float(progress), 1.0))
        self.database.execute(
            "UPDATE jobs SET progress = ?, updated_at = ? WHERE id = ?",
            (value, time.time(), job_id),
        )

    def request_cancel(self, job_id: str) -> Job | None:
        self.ensure_schema()
        job = self.get(job_id)
        if job is None:
            return None
        if job.status in TERMINAL_STATUSES:
            return job
        now = time.time()
        if job.status == STATUS_QUEUED:
            self.database.execute(
                "UPDATE jobs SET cancel_requested = 1, status = ?, finished_at = ?,"
                " updated_at = ? WHERE id = ?",
                (STATUS_CANCELED, now, now, job_id),
            )
        else:
            self.database.execute(
                "UPDATE jobs SET cancel_requested = 1, updated_at = ? WHERE id = ?",
                (now, job_id),
            )
        return self.get(job_id)

    def has_cancel_request(self, job_id: str) -> bool:
        self.ensure_schema()
        row = self.database.fetchone(
            "SELECT cancel_requested FROM jobs WHERE id = ?", (job_id,)
        )
        if row is None:
            return False
        return bool(int(row["cancel_requested"] or 0))

    def recover_stale(self) -> int:
        self.ensure_schema()
        rows = self.database.fetchall(
            "SELECT id FROM jobs WHERE status = ?", (STATUS_RUNNING,)
        )
        now = time.time()
        for row in rows:
            self.database.execute(
                "UPDATE jobs SET status = ?, started_at = 0, progress = 0, updated_at = ?"
                " WHERE id = ?",
                (STATUS_QUEUED, now, str(row["id"])),
            )
        return len(rows)

    def counts(self, tenant_id: str | None = None) -> dict[str, int]:
        self.ensure_schema()
        if tenant_id:
            rows = self.database.fetchall(
                "SELECT status, COUNT(*) AS total FROM jobs WHERE tenant_id = ?"
                " GROUP BY status",
                (tenant_id,),
            )
        else:
            rows = self.database.fetchall(
                "SELECT status, COUNT(*) AS total FROM jobs GROUP BY status"
            )
        counts = {status: 0 for status in (STATUS_QUEUED, STATUS_RUNNING)}
        for row in rows:
            counts[str(row["status"])] = int(row["total"] or 0)
        return counts

    def delete(self, job_id: str) -> bool:
        self.ensure_schema()
        row = self.database.fetchone("SELECT id FROM jobs WHERE id = ?", (job_id,))
        if row is None:
            return False
        self.database.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return True


def _job_from_row(row: Mapping[str, Any]) -> Job:
    payload_raw = str(row.get("payload_json") or "{}")
    result_raw = str(row.get("result_json") or "")
    try:
        payload = json.loads(payload_raw) if payload_raw else {}
    except (TypeError, ValueError):
        payload = {}
    result = None
    if result_raw:
        try:
            parsed = json.loads(result_raw)
            result = parsed if isinstance(parsed, dict) else {"value": parsed}
        except (TypeError, ValueError):
            result = None
    return Job(
        id=str(row["id"]),
        tenant_id=str(row.get("tenant_id") or ""),
        user_id=str(row.get("user_id") or ""),
        kind=str(row.get("kind") or ""),
        status=str(row.get("status") or STATUS_QUEUED),
        payload=payload if isinstance(payload, dict) else {},
        result=result,
        error=str(row.get("error") or ""),
        progress=float(row.get("progress") or 0.0),
        attempts=int(row.get("attempts") or 0),
        cancel_requested=bool(int(row.get("cancel_requested") or 0)),
        created_at=float(row.get("created_at") or 0.0),
        started_at=float(row.get("started_at") or 0.0),
        finished_at=float(row.get("finished_at") or 0.0),
        updated_at=float(row.get("updated_at") or 0.0),
    )
