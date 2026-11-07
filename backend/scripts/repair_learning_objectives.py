from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.objective_guard import (
    has_gap_marker,
    sanitize_objectives,
    sanitize_prerequisites,
)


@dataclass
class UnitChange:
    unit_id: str
    series_title: str
    order_index: int
    title: str
    before_objectives: list[str]
    after_objectives: list[str]
    before_prerequisites: list[str]
    after_prerequisites: list[str]


def _load_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError):
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _dump_list(values: Sequence[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _load_json(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate sentinel learning objectives from node titles and stages")
    parser.add_argument("--db", required=True, help="Path to the SQLite database copy to repair")
    parser.add_argument("--series-id", default="", help="Only repair one series")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    if not db_path.exists():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 2

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        series_rows = connection.execute("SELECT id, title, language FROM series").fetchall()
        series_map = {str(row["id"]): dict(row) for row in series_rows}
        blueprint_rows = connection.execute(
            "SELECT series_id, payload_json FROM series_blueprints"
        ).fetchall()
        node_by_unit: dict[str, dict[str, Any]] = {}
        stage_positions: dict[str, dict[str, int]] = {}
        for row in blueprint_rows:
            series_id = str(row["series_id"])
            payload = _load_json(row["payload_json"])
            stages = payload.get("learning_path") or payload.get("stages") or []
            positions: dict[str, int] = {}
            stage_map: dict[str, dict[str, Any]] = {}
            for index, stage in enumerate(stages, start=1):
                if not isinstance(stage, Mapping):
                    continue
                stage_id = str(stage.get("id") or "")
                if not stage_id:
                    continue
                positions[stage_id] = index
                stage_map[stage_id] = dict(stage)
            stage_positions[series_id] = positions
            for node in payload.get("outline") or payload.get("nodes") or []:
                if not isinstance(node, Mapping) or not node.get("unit_id"):
                    continue
                stage = stage_map.get(str(node.get("stage_id") or ""), {})
                node_by_unit[str(node["unit_id"])] = {
                    "node": dict(node),
                    "stage": stage,
                    "stage_position": positions.get(str(node.get("stage_id") or ""), 1),
                }

        query = "SELECT * FROM units"
        params: tuple[Any, ...] = ()
        if args.series_id:
            query += " WHERE series_id = ?"
            params = (args.series_id,)
        query += " ORDER BY series_id, order_index"
        units = connection.execute(query, params).fetchall()

        rows_scanned = 0
        changed: list[UnitChange] = []
        reserved_by_series: dict[str, set[str]] = {}
        for row in units:
            rows_scanned += 1
            objectives = _load_list(row["learning_objectives"])
            prerequisites = _load_list(row["prerequisites"])
            objective_sentinel = any(has_gap_marker(item) for item in objectives)
            prerequisite_sentinel = any(has_gap_marker(item) for item in prerequisites)
            if not objective_sentinel and not prerequisite_sentinel:
                continue
            series_id = str(row["series_id"])
            series = series_map.get(series_id, {})
            series_title = str(series.get("title") or "")
            language = str(series.get("language") or "")
            linked = node_by_unit.get(str(row["id"]), {})
            node = linked.get("node") or {}
            stage = linked.get("stage") or {}
            order_index = int(row["order_index"] or 1)
            node_title = str(node.get("title") or row["title"] or "")
            next_objectives = objectives
            if objective_sentinel:
                reserved = reserved_by_series.setdefault(series_id, set())
                outcome = sanitize_objectives(
                    objectives,
                    series_title=series_title,
                    node_title=node_title,
                    stage_title=str(stage.get("title") or ""),
                    stage_goal=str(stage.get("goal") or ""),
                    node_position=order_index,
                    stage_position=int(linked.get("stage_position") or 1),
                    language=language,
                    reserved=reserved,
                    force_regenerate=True,
                )
                next_objectives = outcome.values
                reserved.update(value.casefold() for value in next_objectives)
            next_prerequisites = prerequisites
            if prerequisite_sentinel:
                outcome = sanitize_prerequisites(
                    prerequisites,
                    series_title=series_title,
                    stage_title=str(stage.get("title") or ""),
                    stage_goal=str(stage.get("goal") or ""),
                    node_position=order_index,
                    language=language,
                )
                next_prerequisites = outcome.values
            if next_objectives == objectives and next_prerequisites == prerequisites:
                continue
            changed.append(
                UnitChange(
                    unit_id=str(row["id"]),
                    series_title=series_title,
                    order_index=order_index,
                    title=str(row["title"] or ""),
                    before_objectives=objectives,
                    after_objectives=next_objectives,
                    before_prerequisites=prerequisites,
                    after_prerequisites=next_prerequisites,
                )
            )
            if not args.dry_run:
                connection.execute(
                    "UPDATE units SET learning_objectives = ?, prerequisites = ?,"
                    " updated_at = ? WHERE id = ?",
                    (
                        _dump_list(next_objectives),
                        _dump_list(next_prerequisites),
                        time.time(),
                        row["id"],
                    ),
                )
        if not args.dry_run and changed:
            connection.commit()
    finally:
        connection.close()

    payload = {
        "database": str(db_path),
        "dry_run": bool(args.dry_run),
        "rows_scanned": rows_scanned,
        "rows_changed": len(changed),
        "units": [
            {
                "unit_id": change.unit_id,
                "series_title": change.series_title,
                "order_index": change.order_index,
                "title": change.title,
                "before_objectives": change.before_objectives,
                "after_objectives": change.after_objectives,
                "before_prerequisites": change.before_prerequisites,
                "after_prerequisites": change.after_prerequisites,
            }
            for change in changed
        ],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"database: {db_path}")
        print(f"dry_run: {bool(args.dry_run)}")
        print(f"rows_scanned: {rows_scanned}")
        print(f"rows_changed: {len(changed)}")
        for change in changed:
            print(
                f"- [{change.series_title}] #{change.order_index} {change.title}"
            )
            print(f"  before objectives: {json.dumps(change.before_objectives, ensure_ascii=False)}")
            print(f"  after  objectives: {json.dumps(change.after_objectives, ensure_ascii=False)}")
            if change.before_prerequisites != change.after_prerequisites:
                print(f"  before prerequisites: {json.dumps(change.before_prerequisites, ensure_ascii=False)}")
                print(f"  after  prerequisites: {json.dumps(change.after_prerequisites, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
