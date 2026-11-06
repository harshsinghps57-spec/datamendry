"""Preview-first, row-preserving targeted CSV transforms; never mutates originals.

All operations are explicitly allowlisted; processing is streaming and uses bounded
memory. Numeric/non-text columns are never guessed to be convertible.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

from datamendry.engine import _iter_records, make_connection, safe_csv_cell

ACTIONS = frozenset({'fill_blank', 'lowercase', 'uppercase', 'titlecase', 'replace_literal', 'round_number'})
MAX_STEPS = 6
MAX_VALUE = 150
MAX_CELL = 100_000


@dataclass(frozen=True)
class Operation:
    action: str
    index: int
    column: str
    value: str = ''
    replacement: str = ''
    places: int = 0


def validate_steps(headers: list[str], steps: list[dict]) -> tuple[Operation, ...]:
    if not headers or len(set(headers)) != len(headers):
        raise ValueError('The CSV must have unique column names')
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError('Add between one and six cleaning steps')
    result: list[Operation] = []
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError('Invalid step')
        action = step.get('action')
        col = step.get('column')
        if action not in ACTIONS or col not in headers:
            raise ValueError('Choose a supported action and an existing column')
        value = step.get('value', '')
        replacement = step.get('replacement', '')
        places = step.get('places', 0)
        if not isinstance(value, str) or len(value) > MAX_VALUE or not isinstance(replacement, str) or len(replacement) > MAX_VALUE:
            raise ValueError('Step values must be text of at most 150 characters')
        if type(places) is not int or not 0 <= places <= 6:
            raise ValueError('Decimal places must be from 0 to 6')
        if action == 'fill_blank' and not value.strip():
            raise ValueError('Choose a non-blank replacement value')
        if action == 'replace_literal' and not value:
            raise ValueError('Enter text to replace; empty searches are not supported')
        if action not in {'fill_blank', 'replace_literal'} and (value or replacement):
            raise ValueError('Unexpected text parameters for this action')
        if action != 'replace_literal' and replacement:
            raise ValueError('Unexpected replacement value')
        if action != 'round_number' and places:
            raise ValueError('Decimal places are only supported for rounding')
        result.append(Operation(action, headers.index(col), col, value, replacement, places))
    return tuple(result)


def apply_row(row: list[str], steps: tuple[Operation, ...]) -> tuple[list[str], list[int], int]:
    result = list(row)
    skipped_numeric = 0
    for step in steps:
        old = result[step.index]
        new = old
        if step.action == 'fill_blank':
            if not old.strip(): new = step.value
        elif step.action == 'lowercase':
            new = old.lower()
        elif step.action == 'uppercase':
            new = old.upper()
        elif step.action == 'titlecase':
            new = old.title()
        elif step.action == 'replace_literal':
            new = old.replace(step.value, step.replacement)
        elif step.action == 'round_number' and old.strip():
            try:
                number = Decimal(old.strip())
                if not number.is_finite():
                    skipped_numeric += 1
                else:
                    quant = Decimal(1).scaleb(-step.places)
                    new = format(number.quantize(quant), 'f')
            except (InvalidOperation, ValueError):
                skipped_numeric += 1
        # Transformations must never grow rows without bound.
        if len(new) > MAX_CELL:
            raise ValueError('A transformed cell exceeds the safety limit')
        result[step.index] = new
    changed = [i for i, (a,b) in enumerate(zip(row,result)) if a != b]
    return result, changed, skipped_numeric


def preview(db_path: Path, headers: list[str], steps: list[dict], *, limit: int = 12) -> dict:
    compiled = validate_steps(headers, steps)
    connection = make_connection(db_path)
    examples: list[dict] = []
    rows = cells = skipped = 0
    try:
        for row in _iter_records(connection, len(headers)):
            after, diff, not_numeric = apply_row(row, compiled)
            rows += 1
            cells += len(diff)
            skipped += not_numeric
            if len(examples) < limit:
                examples.append({'before':row, 'after':after, 'changed_columns':diff})
    finally:
        connection.close()
    warnings = []
    if skipped:
        warnings.append(f'{skipped:,} nonnumeric cell attempts were left unchanged by rounding.')
    if any(s.action == 'fill_blank' for s in compiled):
        warnings.append('Filled blanks use your chosen constant; they are not estimated or inferred.')
    if any(s.action == 'replace_literal' for s in compiled):
        warnings.append('Text replacement is case-sensitive and matches literal text only.')
    return {'columns':headers, 'row_count':rows, 'changed_cells':cells,
            'unchanged_cells':rows*len(headers)-cells, 'skipped_numeric':skipped,
            'rows':examples, 'warnings':warnings, 'source_unchanged':True}


def export_chunks(db_path: Path, headers: list[str], steps: list[dict]) -> Iterator[bytes]:
    compiled = validate_steps(headers, steps)
    con = make_connection(db_path)
    buf = io.StringIO(newline='')
    writer = csv.writer(buf, lineterminator='\r\n', quoting=csv.QUOTE_ALL)
    try:
        writer.writerow([safe_csv_cell(x) for x in headers])
        yield b'\xef\xbb\xbf' + buf.getvalue().encode('utf-8')
        buf.seek(0);buf.truncate(0)
        for row in _iter_records(con, len(headers)):
            after, _, _ = apply_row(row, compiled)
            writer.writerow([safe_csv_cell(x) for x in after])
            if buf.tell() >= 65536:
                yield buf.getvalue().encode('utf-8')
                buf.seek(0);buf.truncate(0)
        if buf.tell():
            yield buf.getvalue().encode('utf-8')
    finally:
        con.close()
