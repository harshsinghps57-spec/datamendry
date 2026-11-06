"""Read-only filtered CSV exports; caller authenticates dataset ownership."""
from __future__ import annotations
import csv
import io
import math
import sqlite3
from pathlib import Path
from typing import Iterator
from datamendry.engine import make_connection, safe_csv_cell

FILTER_KINDS = {"all", "contains", "not_contains", "equals", "not_equals", "empty", "not_empty", "lt", "lte", "gt", "gte"}
NUMERIC_OPS = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">="}

def safe_real(value):
    try:
        number = float(str(value).strip())
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, OverflowError):
        return None

def numeric_connection(db_path):
    con = make_connection(db_path)
    con.create_function("dm_real", 1, safe_real, deterministic=True)
    return con


def build_query(columns: list[str], filter_column: str | None, kind: str, value: str, include_columns: list[str]):
    if kind not in FILTER_KINDS:
        raise ValueError("Unsupported filter")
    if not include_columns or len(set(include_columns)) != len(include_columns):
        raise ValueError("Select at least one unique output column")
    if any(column not in columns for column in include_columns):
        raise ValueError("Unknown output column")
    if kind != "all" and filter_column not in columns:
        raise ValueError("Unknown filter column")
    selection = ", ".join(f"c{columns.index(column)}" for column in include_columns)
    where, params = "", ()
    if kind != "all":
        col = f"c{columns.index(filter_column)}"  # index is trusted, never user-supplied SQL
        if kind == "contains":
            where, params = f" WHERE instr({col}, ?) > 0", (value,)
        elif kind == "not_contains":
            where, params = f" WHERE instr({col}, ?) = 0", (value,)
        elif kind in NUMERIC_OPS:
            number = safe_real(value)
            if number is None:
                raise ValueError("Numeric filters require a finite number")
            where, params = f" WHERE dm_real({col}) {NUMERIC_OPS[kind]} ?", (number,)
        elif kind == "equals":
            where, params = f" WHERE {col} = ?", (value,)
        elif kind == "not_equals":
            where, params = f" WHERE {col} <> ?", (value,)
        elif kind == "empty":
            where = f" WHERE TRIM({col}) = ''"
        elif kind == "not_empty":
            where = f" WHERE TRIM({col}) <> ''"
    return f"SELECT {selection} FROM records{where} ORDER BY id", f"SELECT COUNT(*) FROM records{where}", params

def filtered_preview(db_path: Path, columns: list[str], filter_column: str | None, kind: str, value: str, included: list[str], limit: int = 20) -> dict:
    query, count_query, params = build_query(columns, filter_column, kind, value, included)
    con = numeric_connection(db_path)
    try:
        count = con.execute(count_query, params).fetchone()[0]
        rows = [list(row) for row in con.execute(f"{query} LIMIT ?", (*params, limit))]
        return {"columns": included, "matching_rows": count, "rows": rows}
    finally:
        con.close()

def filtered_csv_chunks(db_path: Path, columns: list[str], filter_column: str | None, kind: str, value: str, included: list[str]) -> Iterator[bytes]:
    query, _, params = build_query(columns, filter_column, kind, value, included)
    con = numeric_connection(db_path)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    try:
        writer.writerow([safe_csv_cell(col) for col in included])
        yield b"\xef\xbb\xbf" + buffer.getvalue().encode('utf-8')
        buffer.seek(0); buffer.truncate(0)
        for row in con.execute(query, params):
            writer.writerow([safe_csv_cell(value) for value in row])
            if buffer.tell() >= 65536:
                yield buffer.getvalue().encode('utf-8')
                buffer.seek(0); buffer.truncate(0)
        if buffer.tell():
            yield buffer.getvalue().encode('utf-8')
    finally:
        con.close()
