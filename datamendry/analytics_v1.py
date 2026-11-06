"""Bounded, on-device CSV column insights for existing private guest workspaces.

No external analytics, model calls, or raw-row exports. All values are read from
an already-authorized SQLite dataset; this module never modifies it.
"""
from __future__ import annotations

import math
from pathlib import Path

from datamendry.engine import make_connection

BIN_COUNT = 12
TOP_VALUE_COUNT = 10
MAX_NUMERIC_ABS = 1e100


def _numeric(raw: str) -> float | None:
    try:
        numeric = float(raw.strip())
    except (ValueError, OverflowError, AttributeError):
        return None
    return numeric if math.isfinite(numeric) and abs(numeric) <= MAX_NUMERIC_ABS else None


def analyze_column(db_path: Path, columns: list[str], column: str) -> dict:
    """Describe exactly one schema-validated column, with bounded JSON output."""
    if column not in columns:
        raise ValueError("Choose a column that exists in this dataset")
    # Only this trusted, computed index is interpolated into SQL.
    column_sql = f"c{columns.index(column)}"
    conn = make_connection(db_path)
    try:
        seen = missing = numeric_count = 0
        mean = m2 = 0.0
        low = high = None
        for (raw,) in conn.execute(f"SELECT {column_sql} FROM records"):
            seen += 1
            if raw is None or not str(raw).strip():
                missing += 1
                continue
            number = _numeric(raw)
            if number is None:
                continue
            numeric_count += 1
            if low is None or number < low:
                low = number
            if high is None or number > high:
                high = number
            # Welford's numerically stable online moments: O(1) memory.
            delta = number - mean
            mean += delta / numeric_count
            m2 += delta * (number - mean)

        present = seen - missing
        base = {"column": column, "rows": seen, "missing": missing,
                "present": present, "numeric_count": numeric_count,
                "invalid_numeric": present - numeric_count,
                "data_sent_externally": False}
        if not present:
            return {**base, "mode": "empty", "bars": [], "stats": None,
                    "note": "This column contains only blank values."}

        # A mixed column should be charted as categories, not misleadingly
        # treated as a numeric population with silently discarded labels.
        numeric_mode = numeric_count >= 2 and numeric_count / present >= 0.90
        if not numeric_mode:
            items = conn.execute(
                f"SELECT TRIM({column_sql}) AS label, COUNT(*) AS count "
                f"FROM records WHERE {column_sql} IS NOT NULL "
                f"AND TRIM({column_sql}) != '' "
                "GROUP BY label ORDER BY count DESC, label ASC LIMIT ?",
                (TOP_VALUE_COUNT,),
            ).fetchall()
            bars = [{"label": str(label)[:90], "count": int(count)} for label, count in items]
            return {**base, "mode": "categorical", "bars": bars, "stats": None,
                    "note": "Most common nonblank values (top 10). Long labels are shortened for display."}

        variance = max(0.0, m2 / numeric_count)
        stdev = math.sqrt(variance)
        counts = [0] * BIN_COUNT
        outliers = 0
        for (raw,) in conn.execute(f"SELECT {column_sql} FROM records"):
            number = _numeric(raw) if raw is not None else None
            if number is None:
                continue
            if stdev > 0 and abs(number - mean) > 3 * stdev:
                outliers += 1
            if low == high:
                idx = 0
            else:
                idx = min(BIN_COUNT - 1, max(0, int((number - low) / (high - low) * BIN_COUNT)))
            counts[idx] += 1

        def fmt(value: float) -> str:
            return f"{value:.4g}"

        bars = []
        for index, count in enumerate(counts):
            start = low + (high - low) * index / BIN_COUNT
            end = low + (high - low) * (index + 1) / BIN_COUNT
            label = fmt(low) if low == high else f"{fmt(start)} – {fmt(end)}"
            bars.append({"label": label, "count": count})
        return {**base, "mode": "numeric", "bars": bars,
                "stats": {"min": low, "max": high, "mean": mean,
                          "std_dev": stdev, "possible_outliers_3sigma": outliers},
                "note": "Numeric histogram uses all parseable finite values. Potential outliers use the exploratory 3σ rule, not a definitive error test."}
    finally:
        conn.close()
