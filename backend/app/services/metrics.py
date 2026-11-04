from __future__ import annotations

import threading
from typing import Any

BUCKETS = (0.05, 0.2, 1.0, 5.0)
CONTENT_TYPE = "text/plain; version=0.0.4"


def _escape(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )


def _labels(**kwargs: Any) -> str:
    parts = [f'{key}="{_escape(val)}"' for key, val in kwargs.items()]
    return "{" + ",".join(parts) + "}"


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, str], int] = {}
        self._durations: dict[str, dict[str, Any]] = {}
        self._exec: dict[tuple[str, str], int] = {}

    def inc_request(self, method: str, route: str, status: int) -> None:
        key = (str(method or "GET").upper(), str(route or "unmatched"), str(int(status)))
        with self._lock:
            self._requests[key] = self._requests.get(key, 0) + 1

    def observe_duration(self, route: str, seconds: float) -> None:
        name = str(route or "unmatched")
        value = max(0.0, float(seconds))
        with self._lock:
            entry = self._durations.get(name)
            if entry is None:
                entry = {"count": 0, "sum": 0.0, "buckets": [0 for _ in BUCKETS]}
                self._durations[name] = entry
            entry["count"] += 1
            entry["sum"] += value
            for position, bound in enumerate(BUCKETS):
                if value <= bound:
                    entry["buckets"][position] += 1
                    break

    def inc_exec(self, backend: str, result: str) -> None:
        key = (str(backend or "unknown"), str(result or "unknown"))
        with self._lock:
            self._exec[key] = self._exec.get(key, 0) + 1

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._durations.clear()
            self._exec.clear()

    def render(self, extra_snapshot: dict[str, Any] | None = None) -> str:
        snapshot = extra_snapshot or {}
        with self._lock:
            requests = dict(self._requests)
            durations = {
                route: {
                    "count": entry["count"],
                    "sum": entry["sum"],
                    "buckets": list(entry["buckets"]),
                }
                for route, entry in self._durations.items()
            }
            execs = dict(self._exec)
        lines: list[str] = []
        lines.append("# HELP opencgp_http_requests_total 按方法与路由统计的请求数")
        lines.append("# TYPE opencgp_http_requests_total counter")
        for (method, route, status), total in sorted(requests.items()):
            lines.append(
                "opencgp_http_requests_total"
                + _labels(method=method, route=route, status=status)
                + f" {total}"
            )
        lines.append("# HELP opencgp_http_request_duration_seconds 请求耗时直方图")
        lines.append("# TYPE opencgp_http_request_duration_seconds histogram")
        for route, entry in sorted(durations.items()):
            cumulative = 0
            for position, bound in enumerate(BUCKETS):
                cumulative += entry["buckets"][position]
                lines.append(
                    "opencgp_http_request_duration_seconds_bucket"
                    + _labels(route=route, le=str(bound))
                    + f" {cumulative}"
                )
            lines.append(
                "opencgp_http_request_duration_seconds_bucket"
                + _labels(route=route, le="+Inf")
                + f" {entry['count']}"
            )
            lines.append(
                "opencgp_http_request_duration_seconds_sum"
                + _labels(route=route)
                + f" {entry['sum']:.6f}"
            )
            lines.append(
                "opencgp_http_request_duration_seconds_count"
                + _labels(route=route)
                + f" {entry['count']}"
            )
        lines.append("# HELP opencgp_jobs_total 按类型与状态统计的任务数")
        lines.append("# TYPE opencgp_jobs_total gauge")
        for item in snapshot.get("jobs_total") or []:
            lines.append(
                "opencgp_jobs_total"
                + _labels(kind=item.get("kind", ""), status=item.get("status", ""))
                + f" {int(item.get('count') or 0)}"
            )
        lines.append("# HELP opencgp_jobs_active 排队与运行中的任务数")
        lines.append("# TYPE opencgp_jobs_active gauge")
        lines.append(f"opencgp_jobs_active {int(snapshot.get('jobs_active') or 0)}")
        lines.append("# HELP opencgp_queue_backlog 队列积压长度")
        lines.append("# TYPE opencgp_queue_backlog gauge")
        lines.append(f"opencgp_queue_backlog {int(snapshot.get('queue_backlog') or 0)}")
        lines.append("# HELP opencgp_adapter_up adapter 探活结果")
        lines.append("# TYPE opencgp_adapter_up gauge")
        for item in snapshot.get("adapter_up") or []:
            lines.append(
                "opencgp_adapter_up"
                + _labels(name=item.get("name", ""))
                + f" {1 if item.get('up') else 0}"
            )
        lines.append("# HELP opencgp_quota_usage 当前租户本月用量")
        lines.append("# TYPE opencgp_quota_usage gauge")
        for item in snapshot.get("quota_usage") or []:
            lines.append(
                "opencgp_quota_usage"
                + _labels(kind=item.get("kind", ""))
                + f" {int(item.get('value') or 0)}"
            )
        lines.append("# HELP opencgp_exec_runs_total 代码执行次数")
        lines.append("# TYPE opencgp_exec_runs_total counter")
        for (backend, result), total in sorted(execs.items()):
            lines.append(
                "opencgp_exec_runs_total"
                + _labels(backend=backend, result=result)
                + f" {total}"
            )
        info = snapshot.get("info") or {}
        lines.append("# HELP opencgp_info 应用信息")
        lines.append("# TYPE opencgp_info gauge")
        lines.append(
            "opencgp_info"
            + _labels(version=info.get("version", ""), env=info.get("env", ""))
            + " 1"
        )
        return "\n".join(lines) + "\n"


_registry = MetricsRegistry()


def get_metrics() -> MetricsRegistry:
    return _registry
