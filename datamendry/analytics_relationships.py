"""Bounded, private exploratory correlations and aggregate two-column views.

Reads only the SQLite file already associated with an authorized browser session.
Responses include coefficients and histogram counts, never raw records.
"""
from __future__ import annotations

import math
from pathlib import Path

from datamendry.analytics_v1 import _numeric
from datamendry.engine import make_connection

MAX_SCANNED_ROWS = 10000
MAX_CORRELATION_COLUMNS = 12
PAIR_BINS = 10


def _load_numeric_sample(db_path: Path, columns: list[str]) -> tuple[list[str], list[list[float | None]], int, bool]:
    """Read at most 10k input records and choose genuinely numeric columns."""
    con = make_connection(db_path)
    try:
        sampled: list[list[float | None]] = []
        numeric = [0] * len(columns)
        present = [0] * len(columns)
        fields = ','.join(f'c{i}' for i in range(len(columns)))
        for row in con.execute(f'SELECT {fields} FROM records ORDER BY id LIMIT ?', (MAX_SCANNED_ROWS + 1,)):
            if len(sampled) == MAX_SCANNED_ROWS:
                break
            converted = []
            for index, raw in enumerate(row):
                if raw is not None and str(raw).strip():
                    present[index] += 1
                value = _numeric(raw) if raw is not None else None
                if value is not None:
                    numeric[index] += 1
                converted.append(value)
            sampled.append(converted)
        # Determine whether more records exist with a separate bounded query.
        scanned = len(sampled)
        has_more = con.execute('SELECT 1 FROM records ORDER BY id LIMIT 1 OFFSET ?', (MAX_SCANNED_ROWS,)).fetchone() is not None if scanned == MAX_SCANNED_ROWS else False
        eligible = [i for i in range(len(columns)) if numeric[i] >= 3 and present[i] >= 3 and numeric[i] / present[i] >= 0.90]
        selected = eligible[:MAX_CORRELATION_COLUMNS]
        return [columns[i] for i in selected], [[row[i] for i in selected] for row in sampled], scanned, has_more
    finally:
        con.close()


def _coefficient(values: list[tuple[float, float]]) -> float | None:
    """Pairwise-complete Pearson r using stable online covariance."""
    n = 0
    x_mean = y_mean = m2x = m2y = covariance = 0.0
    for x, y in values:
        n += 1
        dx = x - x_mean
        x_mean += dx / n
        dy = y - y_mean
        y_mean += dy / n
        m2x += dx * (x - x_mean)
        m2y += dy * (y - y_mean)
        covariance += dx * (y - y_mean)
    if n < 3 or m2x <= 0 or m2y <= 0:
        return None
    denom = math.sqrt(m2x) * math.sqrt(m2y)
    if not math.isfinite(denom) or denom == 0:
        return None
    result = covariance / denom
    return max(-1.0, min(1.0, result)) if math.isfinite(result) else None


def relationship_overview(db_path: Path, columns: list[str]) -> dict:
    selected, records, scanned, truncated = _load_numeric_sample(db_path, columns)
    matrix = []
    for i, left in enumerate(selected):
        for j, right in enumerate(selected):
            if j < i:
                continue
            pairs = [(row[i], row[j]) for row in records if row[i] is not None and row[j] is not None]
            matrix.append({'x': left, 'y': right,
                           'r': _coefficient(pairs), 'paired_rows': len(pairs)})
    return {
        'columns': selected,
        'pairs': matrix,
        'sampled_rows': scanned,
        'truncated': truncated,
        'max_columns': MAX_CORRELATION_COLUMNS,
        'data_sent_externally': False,
        'note': 'Pearson correlations use pairwise valid numeric values from the first 10,000 records. Correlation does not imply causation. Non-numeric, mostly text, and constant columns may have no coefficient.'
    }


def relationship_pair(db_path: Path, columns: list[str], x: str, y: str) -> dict:
    if x not in columns or y not in columns or x == y:
        raise ValueError('Choose two different columns that exist in the dataset')
    selected, rows, scanned, truncated = _load_numeric_sample(db_path, columns)
    if x not in selected or y not in selected:
        raise ValueError('Both columns must be mostly numeric and within the first 12 eligible numeric columns')
    xi, yi = selected.index(x), selected.index(y)
    samples = [(row[xi], row[yi]) for row in rows if row[xi] is not None and row[yi] is not None]
    if len(samples) < 3:
        raise ValueError('At least three paired numeric rows are required')
    low_x, high_x = min(v[0] for v in samples), max(v[0] for v in samples)
    low_y, high_y = min(v[1] for v in samples), max(v[1] for v in samples)
    histogram = [[0] * PAIR_BINS for _ in range(PAIR_BINS)]
    for value_x, value_y in samples:
        bin_x = min(PAIR_BINS - 1, int((value_x - low_x) / (high_x - low_x) * PAIR_BINS)) if high_x > low_x else 0
        bin_y = min(PAIR_BINS - 1, int((value_y - low_y) / (high_y - low_y) * PAIR_BINS)) if high_y > low_y else 0
        histogram[PAIR_BINS - 1 - bin_y][bin_x] += 1
    return {
        'x': x, 'y': y, 'r': _coefficient(samples),
        'paired_rows': len(samples), 'sampled_rows': scanned, 'truncated': truncated,
        'x_min': low_x, 'x_max': high_x, 'y_min': low_y, 'y_max': high_y,
        'bins': histogram, 'data_sent_externally': False,
        'note': 'Binned two-dimensional counts, not individual records. Correlations are exploratory and use the first 10,000 input rows.'
    }
