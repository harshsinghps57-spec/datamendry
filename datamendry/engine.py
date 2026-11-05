"""SQLite-backed, streaming CSV profile and transparent data-repair operations.

This module deliberately uses standard-library CSV and on-disk SQLite instead of
loading the complete dataset in a pandas DataFrame. A source is immutable; each
repair is a reproducible recipe applied at export time.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

MAX_COLUMNS = 100
MAX_FIELD_CHARACTERS = 250_000
BATCH_SIZE = 1000


class DatasetError(ValueError):
    pass


@dataclass(frozen=True)
class RepairOptions:
    trim_whitespace: bool = False
    normalize_blanks: bool = False
    remove_exact_duplicates: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def row_digest(row: list[str | None]) -> str:
    """Unambiguous SHA-256 of a row. 256-bit collisions are negligible."""
    data = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def column_names(raw: list[str]) -> list[str]:
    if not raw or len(raw) > MAX_COLUMNS:
        raise DatasetError(f"CSV must have between 1 and {MAX_COLUMNS} columns")
    names = [str(name).lstrip("\ufeff") for name in raw]
    if any(not value.strip() for value in names):
        raise DatasetError("Every column must have a non-empty header")
    if len(set(value.strip().casefold() for value in names)) != len(names):
        raise DatasetError("Column headers must be unique (case-insensitive)")
    return names


def make_connection(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path), timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA temp_store=FILE")
    con.execute("PRAGMA cache_size=-16000")  # bound SQLite's page cache (~16 MiB)
    return con


def import_csv(source_path: Path, db_path: Path) -> dict:
    """Ingests linearly using batched INSERT and a disk-backed duplicate index."""
    if db_path.exists():
        raise DatasetError("Dataset already exists")
    csv.field_size_limit(MAX_FIELD_CHARACTERS)
    con = make_connection(db_path)
    try:
        with source_path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh, strict=True)
            try:
                headers = column_names(next(reader))
            except StopIteration as exc:
                raise DatasetError("The CSV is empty") from exc
            sql_cols = ", ".join(f"c{i} TEXT" for i in range(len(headers)))
            con.execute(f"CREATE TABLE records (id INTEGER PRIMARY KEY, {sql_cols})")
            con.execute("CREATE TABLE seen_original (digest TEXT PRIMARY KEY) WITHOUT ROWID")
            columns_sql = ", ".join(f"c{i}" for i in range(len(headers)))
            placeholders = ", ".join("?" for _ in headers)
            insert_sql = f"INSERT INTO records ({columns_sql}) VALUES ({placeholders})"
            count = 0
            duplicates = 0
            blank_counts = [0] * len(headers)
            batch: list[list[str]] = []
            digests: list[tuple[str]] = []

            def flush() -> None:
                nonlocal duplicates
                if not batch:
                    return
                con.executemany(insert_sql, batch)
                # Count duplicate hashes using SQLite's disk-backed unique index.
                changes_before = con.total_changes
                con.executemany("INSERT OR IGNORE INTO seen_original(digest) VALUES (?)", digests)
                duplicates += len(digests) - (con.total_changes - changes_before)
                batch.clear()
                digests.clear()

            for line_number, row in enumerate(reader, start=2):
                if len(row) != len(headers):
                    raise DatasetError(f"Row {line_number}: expected {len(headers)} cells, found {len(row)}")
                if any(len(value) > MAX_FIELD_CHARACTERS for value in row):
                    raise DatasetError(f"Row {line_number} has an excessively long cell")
                blank_counts = [value + int(not cell.strip()) for value, cell in zip(blank_counts, row)]
                batch.append(row)
                digests.append((row_digest(row),))
                count += 1
                if len(batch) >= BATCH_SIZE:
                    flush()
            flush()
            if count == 0:
                raise DatasetError("The CSV only contains a header; add at least one row")
            con.execute("DROP TABLE seen_original")
            con.commit()
            return {"columns": headers, "rows": count, "duplicate_rows": duplicates,
                    "missing_cells": sum(blank_counts), "missing_by_column": blank_counts}
    except (csv.Error, UnicodeError, sqlite3.Error) as exc:
        raise DatasetError(f"Could not import CSV: {exc}") from exc
    finally:
        con.close()
        # Failed import must not leave an inaccessible, half-written dataset.
        # Callers clean up the whole workspace on failure.


def fetch_preview(db_path: Path, headers: list[str], limit: int = 20, offset: int = 0) -> dict:
    con = make_connection(db_path)
    try:
        rows = con.execute("SELECT * FROM records ORDER BY id LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return {"columns": headers, "rows": [list(row[1:]) for row in rows],
                "limit": limit, "offset": offset}
    finally:
        con.close()


def _iter_records(con: sqlite3.Connection, n_columns: int) -> Iterator[list[str]]:
    cursor = con.execute("SELECT * FROM records ORDER BY id")
    for row in cursor:
        yield list(row[1:])


def transform_row(row: list[str], options: RepairOptions) -> tuple[list[str | None], int, int]:
    out: list[str | None] = []
    changed = blanks = 0
    for cell in row:
        value: str | None = cell
        if options.trim_whitespace:
            value = value.strip()
        if options.normalize_blanks and not value.strip():
            value = None
        if value != cell:
            changed += 1
        if value is None or not value.strip():
            blanks += 1
        out.append(value)
    return out, changed, blanks


@contextmanager
def _seen_database():
    # Disk-based UNIQUE index avoids accumulating all distinct rows in RAM.
    with tempfile.TemporaryDirectory(prefix="datamendry-dedupe-") as folder:
        con = make_connection(Path(folder) / "seen.sqlite")
        try:
            con.execute("CREATE TABLE seen (digest TEXT PRIMARY KEY) WITHOUT ROWID")
            yield con
        finally:
            con.close()


def _unique_row(con: sqlite3.Connection, row: list[str | None]) -> bool:
    record = con.execute("INSERT OR IGNORE INTO seen(digest) VALUES (?)", (row_digest(row),))
    return record.rowcount > 0


def simulate(db_path: Path, metadata: dict, options: RepairOptions) -> dict:
    """Exact streaming impact summary; bounded Python memory, disk-based dedupe."""
    from contextlib import nullcontext
    con = make_connection(db_path)
    kept = 0
    changed_cells = 0
    removed_duplicates = 0
    blank_cells_after = 0
    try:
        with (_seen_database() if options.remove_exact_duplicates else nullcontext(None)) as seen:
            for row in _iter_records(con, len(metadata["columns"])):
                transformed, changed, blanks = transform_row(row, options)
                if seen is not None and not _unique_row(seen, transformed):
                    removed_duplicates += 1
                    continue
                kept += 1
                changed_cells += changed
                blank_cells_after += blanks
        return {
            "before": {"rows": metadata["rows"], "missing_cells": metadata["missing_cells"],
                       "duplicate_rows": metadata["duplicate_rows"]},
            "after": {"rows": kept, "missing_cells": blank_cells_after},
            "impact": {"changed_cells_in_kept_rows": changed_cells,
                       "removed_rows": removed_duplicates,
                       "retained_rows": kept},
            "recipe": options.as_dict(),
            "source_sha256": metadata["source_sha256"],
            "warnings": (["Removing exact duplicates discards rows; verify that repeated entries are not legitimate events."] if options.remove_exact_duplicates else [])
                      + (["Normalizing blanks will export empty cells; it does not infer or fill missing values."] if options.normalize_blanks else []),
        }
    finally:
        con.close()


def safe_csv_cell(value: str | None) -> str:
    """Defend against CSV formula injection when opened in spreadsheet programs."""
    if value is None:
        return ""
    # Leading spaces are significant to spreadsheet formula detection; quote proactively.
    if re.match(r"^\s*[=+@\-\t\r]", value) and value.strip():
        return "'" + value
    return value


def export_csv_chunks(db_path: Path, headers: list[str], options: RepairOptions) -> Iterator[bytes]:
    """Generator streaming CSV bytes without building a whole in-memory export."""
    from contextlib import nullcontext
    con = make_connection(db_path)
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    try:
        with (_seen_database() if options.remove_exact_duplicates else nullcontext(None)) as seen:
            writer.writerow([safe_csv_cell(col) for col in headers])
            yield b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate(0)
            for row in _iter_records(con, len(headers)):
                transformed, _, _ = transform_row(row, options)
                if seen is not None and not _unique_row(seen, transformed):
                    continue
                writer.writerow([safe_csv_cell(value) for value in transformed])
                if buf.tell() > 64 * 1024:
                    yield buf.getvalue().encode("utf-8")
                    buf.seek(0)
                    buf.truncate(0)
            if buf.tell():
                yield buf.getvalue().encode("utf-8")
    finally:
        con.close()
