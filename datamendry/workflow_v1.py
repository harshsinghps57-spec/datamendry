"""Safe, deterministic, multi-step CSV workflows for DataMendry v1 milestone 2.

No untrusted code or AI output is executed. Each action must be explicitly allowed,
and a completed preview never mutates the source SQLite database.
"""
from __future__ import annotations

import csv
import io
import math
import re
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from datamendry.assistant_planner import plan_instruction
from datamendry.engine import (
    RepairOptions, _iter_records, _seen_database, _unique_row,
    make_connection, safe_csv_cell, transform_row,
)
from datamendry.filters import FILTER_KINDS, safe_real

ACTION_SET = {"trim_whitespace", "normalize_blanks", "deduplicate", "filter", "exclude_column"}
_NUMERIC = {"lt": lambda x,y: x<y, "lte": lambda x,y: x<=y,
            "gt": lambda x,y: x>y, "gte": lambda x,y: x>=y}


def plan_workflow(message: str, columns: list[str]) -> dict | None:
    """Plan 2-5 unambiguous instructions. None means use legacy single-step planner.

    A rejected multi-step request is action='none' (not a truncated plan).
    """
    # Split only at explicit command boundaries; no fuzzy natural-language guessing.
    segments = [s.strip(' \t\r\n.!') for s in re.split(r"\s*(?:,|;|\bthen\b|\band\b)\s*", message, flags=re.I)]
    segments = [s for s in segments if s]
    if len(segments) < 2:
        return None

    def reject(reason: str) -> dict:
        return {"source":"guided", "action":"none", "column":"", "kind":"all",
                "value":"", "message":reason, "applied":False}

    if len(segments) > 5:
        return reject("A workflow supports at most five steps. Split the request into smaller workflows; no changes were made.")
    steps = []
    for phrase in segments:
        plan = plan_instruction(phrase, columns)
        if plan["action"] not in ACTION_SET:
            return reject("I couldn't safely understand every step. Try 'Remove duplicates, trim whitespace, and keep CGPA above 7'. Nothing was changed.")
        steps.append({k:plan[k] for k in ("action","column","kind","value","message")})
    actions = [step["action"] for step in steps]
    if len(set(actions)) != len(actions):
        return reject("Please use each repair action and at most one filter once per workflow; nothing was changed.")
    # This first version deliberately accepts only one row filter and one column exclusion.
    return {"source":"guided", "action":"workflow", "steps":steps,
            "column":"", "kind":"all", "value":"", "applied":False,
            "message":"Review this combined workflow. DataMendry will trim/normalize, deduplicate, filter, then exclude columns; preview before downloading. Your original is unchanged."}


@dataclass(frozen=True)
class CompiledWorkflow:
    options: RepairOptions
    filter_col: int | None
    filter_kind: str
    filter_value: str
    filter_number: float | None
    selected_indices: tuple[int,...]
    output_columns: tuple[str,...]


def validate_workflow(columns: list[str], steps: list[dict]) -> CompiledWorkflow:
    if not (2 <= len(steps) <= 5):
        raise ValueError("Select between two and five workflow actions")
    if not columns or len(set(columns)) != len(columns):
        raise ValueError("Dataset column headers are invalid")
    actions = [s.get("action") for s in steps]
    if any(a not in ACTION_SET for a in actions) or len(actions) != len(set(actions)):
        raise ValueError("Workflow actions must be supported and unique")
    filters = [s for s in steps if s["action"] == "filter"]
    excluded = [s for s in steps if s["action"] == "exclude_column"]
    if len(filters) > 1 or len(excluded) > 1:
        raise ValueError("At most one row filter and one column exclusion are supported")
    trim = "trim_whitespace" in actions
    blanks = "normalize_blanks" in actions
    dedupe = "deduplicate" in actions
    # Reject hidden directives/parameters for repair-only steps.
    for s in steps:
        if s["action"] in {"trim_whitespace", "normalize_blanks", "deduplicate"}:
            if s.get("column") or s.get("value") or s.get("kind", "all") != "all":
                raise ValueError("Repair actions must not specify extra filter parameters")
    exclude_names = [s["column"] for s in excluded]
    if any(name not in columns for name in exclude_names):
        raise ValueError("Unknown excluded column")
    output = tuple(n for n in columns if n not in exclude_names)
    if not output:
        raise ValueError("At least one output column must remain")
    spec = filters[0] if filters else None
    kind, value, filter_col, filter_number = "all", "", None, None
    if spec:
        kind, value = spec.get("kind", "all"), spec.get("value", "")
        name = spec.get("column", "")
        if name not in columns or kind not in FILTER_KINDS or kind == "all":
            raise ValueError("Unknown filter column or condition")
        if not isinstance(value, str) or len(value) > 500:
            raise ValueError("Invalid filter value")
        filter_col = columns.index(name)
        if kind in _NUMERIC:
            filter_number = safe_real(value)
            if filter_number is None or not math.isfinite(filter_number):
                raise ValueError("A numeric filter needs a finite number")
    return CompiledWorkflow(RepairOptions(trim, blanks, dedupe),filter_col,kind,value,
                            filter_number,tuple(columns.index(n) for n in output),output)


def _matches(row: list[str | None], spec: CompiledWorkflow) -> bool:
    if spec.filter_col is None:
        return True
    raw = row[spec.filter_col] or ""
    kind = spec.filter_kind
    if kind == "empty": return not raw.strip()
    if kind == "not_empty": return bool(raw.strip())
    if kind == "contains": return spec.filter_value in raw
    if kind == "not_contains": return spec.filter_value not in raw
    if kind == "equals": return spec.filter_value == raw
    if kind == "not_equals": return spec.filter_value != raw
    if kind in _NUMERIC:
        n = safe_real(raw)
        return n is not None and _NUMERIC[kind](n,spec.filter_number)
    return True


def _iter_workflow(db_path:Path, columns: list[str], workflow:CompiledWorkflow):
    con = make_connection(db_path)
    try:
        with (_seen_database() if workflow.options.remove_exact_duplicates else nullcontext(None)) as seen:
            for row in _iter_records(con,len(columns)):
                transformed, changed, _ = transform_row(row,workflow.options)
                if seen is not None and not _unique_row(seen,transformed):
                    yield None, changed, True
                    continue
                if _matches(transformed,workflow):
                    yield [transformed[i] for i in workflow.selected_indices],changed,False
                else:
                    yield None,changed,False
    finally:
        con.close()


def workflow_preview(db_path:Path, columns:list[str], steps:list[dict], *, limit:int=25) -> dict:
    spec = validate_workflow(columns,steps)
    preview = []
    kept = removed = filtered_out = changed_cells = 0
    for row,changed,is_duplicate in _iter_workflow(db_path,columns,spec):
        if is_duplicate:
            removed += 1
        elif row is None:
            filtered_out += 1
        else:
            kept += 1
            changed_cells += changed
            if len(preview) < limit:
                preview.append([value if value is not None else "" for value in row])
    return {"columns":list(spec.output_columns), "rows":preview,"matching_rows":kept,
            "removed_duplicates":removed,"filtered_out_rows":filtered_out,
            "changed_cells_in_kept_rows":changed_cells,
            "warnings":(["Exact duplicate removal can discard legitimate repeated records."] if spec.options.remove_exact_duplicates else [])}


def workflow_export_chunks(db_path:Path,columns:list[str],steps:list[dict]) -> Iterator[bytes]:
    spec = validate_workflow(columns,steps)
    buf = io.StringIO(newline="")
    writer = csv.writer(buf,lineterminator="\r\n",quoting=csv.QUOTE_ALL)
    writer.writerow([safe_csv_cell(n) for n in spec.output_columns])
    yield b"\xef\xbb\xbf" + buf.getvalue().encode('utf-8')
    buf.seek(0);buf.truncate(0)
    for row,_,_ in _iter_workflow(db_path,columns,spec):
        if row is None: continue
        writer.writerow([safe_csv_cell(value) for value in row])
        if buf.tell() >= 65536:
            yield buf.getvalue().encode('utf-8')
            buf.seek(0);buf.truncate(0)
    if buf.tell(): yield buf.getvalue().encode('utf-8')
