from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.blueprint_titles import (  # noqa: E402
    clean_title,
    is_placeholder_value,
    sanitize_payload,
)

LIVE_DB = (ROOT / "data" / "opencgp.db").resolve()


def _dump_list(values: Sequence[Any]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _load_list(raw: Any) -> list[Any]:
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _iter_rows(connection: sqlite3.Connection, series_filter: str) -> list[sqlite3.Row]:
    query = (
        "SELECT b.series_id, b.version, b.payload_json, s.title AS series_title,"
        " s.language AS series_language"
        " FROM series_blueprints b LEFT JOIN series s ON s.id = b.series_id"
        " ORDER BY b.series_id"
    )
    rows = list(connection.execute(query))
    if not series_filter:
        return rows
    needle = series_filter.casefold()
    return [
        row
        for row in rows
        if needle in str(row["series_title"] or "").casefold()
        or needle in str(row["series_id"] or "").casefold()
    ]


def _repair_payload_objectives(
    payload: dict[str, Any], series_title: str, language: str
) -> int:
    try:
        from app.services.objective_guard import sanitize_objectives
    except Exception:
        return 0
    stages: dict[str, tuple[int, dict[str, Any]]] = {}
    for position, stage in enumerate(payload.get("learning_path") or [], start=1):
        if isinstance(stage, dict):
            stages[str(stage.get("id") or "")] = (position, stage)
    reserved: set[str] = set()
    changed = 0
    for position, node in enumerate(payload.get("outline") or [], start=1):
        if not isinstance(node, dict):
            continue
        stage_position, stage = stages.get(str(node.get("stage_id") or ""), (1, {}))
        current = [str(item) for item in node.get("objectives") or [] if str(item)]
        outcome = sanitize_objectives(
            current,
            series_title=series_title,
            node_title=str(node.get("title") or ""),
            stage_title=str(stage.get("title") or ""),
            stage_goal=str(stage.get("goal") or ""),
            node_position=position,
            stage_position=stage_position,
            language=language,
            reserved=reserved,
        )
        values = list(outcome.values)
        if values != current:
            changed += 1
        node["objectives"] = values
        reserved.update(value.casefold() for value in values)
    return changed


def repair(
    db_path: Path,
    series_filter: str,
    apply: bool,
    show: str,
) -> dict[str, Any]:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    stats: dict[str, Any] = {
        "blueprint_rows_scanned": 0,
        "blueprint_rows_changed": 0,
        "nodes_scanned": 0,
        "nodes_changed": 0,
        "stages_scanned": 0,
        "stages_changed": 0,
        "units_scanned": 0,
        "units_changed": 0,
        "nodes_objectives_changed": 0,
        "units_objectives_changed": 0,
        "units_skipped": [],
        "reports": [],
    }
    now = time.time()
    show_needle = (show or "").casefold()

    for row in _iter_rows(connection, series_filter):
        series_id = str(row["series_id"])
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        series_title = str(row["series_title"] or "") or str(payload.get("series_id") or "")
        series_language = str(row["series_language"] or "")
        stats["blueprint_rows_scanned"] += 1

        outline = payload.get("outline") or payload.get("nodes") or []
        stages = payload.get("learning_path") or payload.get("stages") or []
        before_titles = [
            str(item.get("title") or "") for item in outline if isinstance(item, dict)
        ]
        before_stage_titles = [
            str(item.get("title") or "") for item in stages if isinstance(item, dict)
        ]
        sanitized, repaired_fields = sanitize_payload(payload, series_title)
        objective_nodes_changed = _repair_payload_objectives(
            sanitized, series_title, series_language
        )
        stats["nodes_objectives_changed"] += objective_nodes_changed
        if objective_nodes_changed:
            repaired_fields = [*repaired_fields, "objectives"]
        after_titles = [
            str(item.get("title") or "")
            for item in sanitized.get("outline") or []
            if isinstance(item, dict)
        ]

        stats["nodes_scanned"] += len(before_titles)
        stats["stages_scanned"] += len(before_stage_titles)
        node_changes = sum(1 for a, b in zip(before_titles, after_titles) if a != b)
        stage_changes = sum(
            1
            for a, b in zip(
                before_stage_titles,
                [
                    str(item.get("title") or "")
                    for item in sanitized.get("learning_path") or []
                    if isinstance(item, dict)
                ],
            )
            if a != b
        )
        stats["nodes_changed"] += node_changes
        stats["stages_changed"] += stage_changes
        row_changed = bool(node_changes or stage_changes or repaired_fields)
        if row_changed:
            stats["blueprint_rows_changed"] += 1

        units_before: dict[str, dict[str, Any]] = {}
        for node in outline:
            if not isinstance(node, dict):
                continue
            unit_id = str(node.get("unit_id") or "")
            if not unit_id:
                continue
            unit_row = connection.execute(
                "SELECT id, title, learning_objectives FROM units WHERE id = ?",
                (unit_id,),
            ).fetchone()
            if unit_row is not None:
                units_before[unit_id] = {
                    "title": str(unit_row["title"] or ""),
                    "objectives": _load_list(unit_row["learning_objectives"]),
                }

        for node in sanitized.get("outline") or []:
            if not isinstance(node, dict):
                continue
            unit_id = str(node.get("unit_id") or "")
            current = units_before.get(unit_id)
            if current is None:
                continue
            stats["units_scanned"] += 1
            updates: list[str] = []
            params: list[Any] = []
            new_title = str(node.get("title") or "")
            if new_title and is_placeholder_value(current["title"]):
                updates.append("title = ?")
                params.append(new_title)
            elif new_title and current["title"].strip() != new_title:
                stats["units_skipped"].append(
                    {"unit_id": unit_id, "reason": "manual_title", "title": current["title"]}
                )
            objectives = [
                str(item) for item in node.get("objectives") or [] if str(item)
            ]
            current_objectives = [str(item) for item in current["objectives"] if str(item)]
            if objectives and (
                not current_objectives
                or all(is_placeholder_value(item) for item in current_objectives)
            ):
                if current_objectives != objectives:
                    updates.append("learning_objectives = ?")
                    params.append(_dump_list(objectives))
                    stats["units_objectives_changed"] += 1
            if updates:
                params.extend([now, unit_id])
                if apply:
                    connection.execute(
                        f"UPDATE units SET {', '.join(updates)}, updated_at = ? WHERE id = ?",
                        tuple(params),
                    )
                stats["units_changed"] += 1

        if row_changed and apply:
            connection.execute(
                "UPDATE series_blueprints SET payload_json = ?, updated_at = ? WHERE series_id = ?",
                (json.dumps(sanitized, ensure_ascii=False), now, series_id),
            )

        if show_needle and (
            show_needle in series_title.casefold() or show_needle in series_id.casefold()
        ):
            stats["reports"].append(
                {
                    "series_id": series_id,
                    "series_title": series_title,
                    "version": int(row["version"]),
                    "before_stage_titles": before_stage_titles,
                    "after_stage_titles": [
                        str(item.get("title") or "") for item in sanitized.get("learning_path") or []
                    ],
                    "before_titles": before_titles,
                    "after_titles": after_titles,
                    "units_before": units_before,
                    "repaired_fields": repaired_fields,
                }
            )

    if apply:
        connection.commit()
    connection.close()
    return stats


def verify(db_path: Path, series_title: str) -> dict[str, Any]:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT b.payload_json, s.title FROM series_blueprints b JOIN series s ON s.id = b.series_id"
        " WHERE s.title = ?",
        (series_title,),
    ).fetchone()
    if row is None:
        connection.close()
        return {"found": False}
    payload = json.loads(row["payload_json"])
    titles = [str(node.get("title") or "") for node in payload.get("outline") or []]
    unit_titles = [
        str(item["title"])
        for item in connection.execute(
            "SELECT u.title FROM units u JOIN series s ON s.id = u.series_id"
            " WHERE s.title = ? ORDER BY u.order_index",
            (series_title,),
        )
    ]
    connection.close()
    return {
        "found": True,
        "titles": titles,
        "unit_titles": unit_titles,
        "distinct": len(set(titles)),
        "total": len(titles),
        "placeholders": [title for title in titles if is_placeholder_value(title)],
        "units_distinct": len(set(unit_titles)),
        "units_total": len(unit_titles),
        "units_placeholders": [title for title in unit_titles if is_placeholder_value(title)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair placeholder blueprint titles in a copy of the database")
    parser.add_argument("--db", required=True, help="path to the database copy to repair")
    parser.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    parser.add_argument("--series", default="", help="only repair blueprints whose series title or id contains this text")
    parser.add_argument("--show", default="", help="print before/after titles for matching series")
    parser.add_argument("--verify-series", default="", help="after repairing, verify every title of this series")
    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    if not db_path.exists():
        print(f"database not found: {db_path}")
        return 2
    if db_path == LIVE_DB:
        print(f"refusing to touch the live database: {db_path}")
        return 2
    print(f"database: {db_path}")
    print(f"mode: {'apply' if args.apply else 'dry-run'}")

    stats = repair(db_path, args.series, args.apply, args.show or args.verify_series)

    print(f"blueprint rows scanned: {stats['blueprint_rows_scanned']}")
    print(f"blueprint rows changed: {stats['blueprint_rows_changed']}")
    print(f"outline nodes scanned: {stats['nodes_scanned']}")
    print(f"outline nodes changed: {stats['nodes_changed']}")
    print(f"stages scanned/changed: {stats['stages_scanned']}/{stats['stages_changed']}")
    print(f"units scanned: {stats['units_scanned']}")
    print(
        f"units changed: {stats['units_changed']}"
        f" (objectives repaired: {stats['units_objectives_changed']},"
        f" nodes with objectives repaired: {stats['nodes_objectives_changed']})"
    )
    if stats["units_skipped"]:
        print(f"units with non-placeholder titles left untouched: {len(stats['units_skipped'])}")

    for report in stats["reports"]:
        print("")
        print(f"=== {report['series_title']} ({report['series_id']}) v{report['version']} ===")
        print("stage titles before:")
        for title in report["before_stage_titles"]:
            print(f"  - {title!r}")
        print("stage titles after:")
        for title in report["after_stage_titles"]:
            print(f"  + {title!r}")
        print("node titles before -> after:")
        for before, after in zip(report["before_titles"], report["after_titles"]):
            print(f"  - {before!r}")
            print(f"  + {after!r}")
        print("units before:")
        for unit_id, unit in report["units_before"].items():
            print(f"  - {unit_id}: {unit['title']!r}")
        print(f"repaired fields: {len(report['repaired_fields'])}")

    if args.verify_series:
        result = verify(db_path, args.verify_series)
        print("")
        print(f"=== verification: {args.verify_series} ===")
        if not result.get("found"):
            print("series not found")
            return 1
        print(f"blueprint titles: {result['total']} total, {result['distinct']} distinct")
        print(f"blueprint placeholders: {result['placeholders']}")
        print(f"unit titles: {result['units_total']} total, {result['units_distinct']} distinct")
        print(f"unit placeholders: {result['units_placeholders']}")
        for title in result["titles"]:
            print(f"  * {title}")
        ok = (
            result["total"] == result["distinct"]
            and not result["placeholders"]
            and result["units_total"] == result["units_distinct"]
            and not result["units_placeholders"]
        )
        print(f"verification: {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
