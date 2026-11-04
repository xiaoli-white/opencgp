from __future__ import annotations

import re
from typing import Callable, Protocol, Sequence

PkLookup = Callable[[str], Sequence[str]]


class DialectTranslationError(RuntimeError):
    pass


_PRAGMA_TABLE_INFO = re.compile(
    r"^\s*PRAGMA\s+table_info\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*;?\s*$",
    re.IGNORECASE,
)
_TABLE_EXISTS = re.compile(
    r"FROM\s+sqlite_master\s+WHERE\s+type\s*=\s*'table'\s+AND\s+name\s*=\s*\?",
    re.IGNORECASE,
)
_DATE_EPOCH_8 = re.compile(
    r"\bdate\s*\(\s*([A-Za-z_][A-Za-z0-9_.]*)\s*,\s*'unixepoch'\s*,\s*'\+8 hours'\s*\)",
    re.IGNORECASE,
)
_DATETIME_EPOCH = re.compile(
    r"\bdatetime\s*\(\s*([A-Za-z_][A-Za-z0-9_.]*)\s*,\s*'unixepoch'\s*\)",
    re.IGNORECASE,
)
_INSERT_OR_IGNORE = re.compile(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", re.IGNORECASE)
_INSERT_OR_REPLACE = re.compile(
    r"\bINSERT\s+OR\s+REPLACE\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)",
    re.IGNORECASE | re.DOTALL,
)
_INSERT_TABLE = re.compile(r"\bINSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_REAL_TYPE = re.compile(r"\bREAL\b", re.IGNORECASE)
_DDL = re.compile(r"^\s*(?:CREATE|ALTER)\s+TABLE\b", re.IGNORECASE)
_RETURNING = re.compile(r"\bRETURNING\b", re.IGNORECASE)


def _convert_placeholders(sql: str, escape_percent: bool) -> str:
    out: list[str] = []
    quote: str | None = None
    index = 0
    length = len(sql)
    while index < length:
        char = sql[index]
        if quote is not None:
            out.append(char)
            if char == quote:
                if index + 1 < length and sql[index + 1] == quote:
                    out.append(sql[index + 1])
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            out.append(char)
            index += 1
            continue
        if char == "?":
            out.append("\x00")
            index += 1
            continue
        out.append(char)
        index += 1
    text = "".join(out)
    if escape_percent:
        text = text.replace("%", "%%")
    return text.replace("\x00", "%s")


def _append_clause(sql: str, clause: str) -> str:
    match = _RETURNING.search(sql)
    if match is None:
        return f"{sql.rstrip()} {clause}"
    head = sql[: match.start()].rstrip()
    tail = sql[match.start() :]
    return f"{head} {clause} {tail}"


def translate(
    sql: str,
    params: Sequence[object] = (),
    pk_lookup: PkLookup | None = None,
) -> str:
    text = sql
    if not text.strip():
        return text

    pragma = _PRAGMA_TABLE_INFO.match(text)
    if pragma is not None:
        table = pragma.group(1)
        return (
            "SELECT column_name AS name, data_type AS type"
            " FROM information_schema.columns"
            " WHERE table_schema = current_schema()"
            f" AND table_name = '{table}'"
            " ORDER BY ordinal_position"
        )

    if _TABLE_EXISTS.search(text):
        text = _TABLE_EXISTS.sub(
            "FROM information_schema.tables"
            " WHERE table_type = 'BASE TABLE'"
            " AND table_schema = current_schema()"
            " AND table_name = ?",
            text,
        )
        text = text.replace("SELECT name", "SELECT table_name AS name", 1)

    if _INSERT_OR_IGNORE.search(text):
        text = _INSERT_OR_IGNORE.sub("INSERT INTO", text)
        text = _append_clause(text, "ON CONFLICT DO NOTHING")

    if _INSERT_OR_REPLACE.search(text):
        match = _INSERT_OR_REPLACE.search(text)
        assert match is not None
        table = match.group(1)
        columns = [part.strip() for part in match.group(2).split(",") if part.strip()]
        primary_key: list[str] = []
        if pk_lookup is not None:
            primary_key = [str(col) for col in pk_lookup(table)]
        if not primary_key:
            raise DialectTranslationError(
                "无法翻译 INSERT OR REPLACE（表 "
                f"{table} 未找到主键）: {sql.strip()[:400]}"
            )
        updates = [
            f"{column} = excluded.{column}"
            for column in columns
            if column not in primary_key
        ]
        target = ", ".join(primary_key)
        text = _INSERT_OR_REPLACE.sub(
            f"INSERT INTO {table} ({', '.join(columns)})", text, count=1
        )
        if updates:
            text = _append_clause(
                text, f"ON CONFLICT ({target}) DO UPDATE SET {', '.join(updates)}"
            )
        else:
            text = _append_clause(text, f"ON CONFLICT ({target}) DO NOTHING")

    if _DATE_EPOCH_8.search(text):
        text = _DATE_EPOCH_8.sub(
            lambda m: (
                "to_char(to_timestamp("
                + m.group(1)
                + ") + interval '8 hours', 'YYYY-MM-DD')"
            ),
            text,
        )
    if _DATETIME_EPOCH.search(text):
        text = _DATETIME_EPOCH.sub(
            lambda m: "to_timestamp(" + m.group(1) + ")", text
        )

    if _DDL.match(text) and _REAL_TYPE.search(text):
        text = _REAL_TYPE.sub("DOUBLE PRECISION", text)

    return _convert_placeholders(text, escape_percent=bool(params))
