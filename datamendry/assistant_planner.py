"""Deterministic, private suggestions for commonly requested CSV changes.

This is *not* a generative model. No CSV rows leave the user's session. The
planner only produces a suggestion and never mutates records.
"""
from __future__ import annotations
import re

_NUMBER = r"(-?(?:\d+(?:\.\d*)?|\.\d+))"
_TERMS = (
    ("below", "lt"), ("under", "lt"), ("less than", "lt"),
    ("at most", "lte"), ("less than or equal to", "lte"),
    ("above", "gt"), ("over", "gt"), ("greater than", "gt"),
    ("at least", "gte"), ("greater than or equal to", "gte"),
)
_INVERT = {"lt":"gte", "lte":"gt", "gt":"lte", "gte":"lt", "equals":"not_equals", "contains":"not_contains"}


def _match_column(message: str, columns: list[str]) -> str | None:
    """Only return exact, existing column names, longest-match first."""
    for name in sorted(columns, key=len, reverse=True):
        pattern = re.escape(name).replace("_", "[_ ]").replace(r"\ ", "[ _]")
        if re.search(r"(?<![\w])" + pattern + r"(?![\w])", message, re.I):
            return name
    return None


def plan_instruction(message: str, columns: list[str]) -> dict:
    """Return a *review-only* plan. Never execute based on the text."""
    text = message.strip()
    lower = text.casefold()
    col = _match_column(text, columns)

    def result(action="none", column="", kind="all", value="", message=""):
        return {"source": "guided", "action": action, "column": column,
                "kind": kind, "value": value, "message": message,
                "applied": False}

    if re.search(r"\b(duplicate|dedup|repeated rows?)\b", lower):
        return result("deduplicate", message="Review exact duplicate-row removal in Repair Studio; your original stays untouched.")
    if re.search(r"\b(trim|whitespace|extra spaces?)\b", lower):
        return result("trim_whitespace", message="Review whitespace trimming before exporting a new CSV.")
    if re.search(r"\b(normalize|standardi[sz]e)\b.*\b(blank|empty|null)\b|\b(blank|empty)\b.*\b(normalize|standardi[sz]e)\b", lower):
        return result("normalize_blanks", message="Review blank-field normalization in Repair Studio.")
    if re.search(r"\b(impute|median|mean|average|predict|create new column|add column)\b", lower):
        return result(message="This guided version cannot calculate or fill median/mean values or create new columns. Use Repair Studio or connect an appropriately tested model for planning; no changes were made.")
    if not col:
        return result(message="Name an existing CSV column in your request. For example: 'Remove rows where CGPA is below 6' or 'Keep Region contains West'.")

    # Drop a column, but not rows. Exact column name is validated against the dataset schema.
    if re.search(r"\b(remove|delete|drop|exclude|hide)\b", lower) and re.search(r"\bcolumn|field\b", lower):
        return result("exclude_column", col, message=f"Exclude {col} from a new CSV export. Review the selection before downloading.")

    deleting = bool(re.search(r"\b(remove|delete|drop|exclude)\b", lower))
    for label, kind in sorted(_TERMS, key=lambda item:len(item[0]), reverse=True):
        match = re.search(r"\b" + re.escape(label) + r"\s*" + _NUMBER + r"\b", lower)
        if match:
            if re.search(r"\b(and|or)\b.+\b(below|under|above|over|equals|contains)\b", lower):
                return result(message="Please request one condition at a time; multiple filters are not supported in this guided version.")
            chosen = _INVERT[kind] if deleting else kind
            return result("filter", col, chosen, match.group(1),
                          f"Review a numeric filter on {col} ({chosen} {match.group(1)}). Non-numeric/blank cells are excluded when comparing numbers. Only a new export is affected.")
    # Single-valued text conditions.
    match = re.search(r"\b(contains|equals|is)\s+[\"']?([^\"']+?)[\"']?\s*$", text, re.I)
    if match:
        kind = "contains" if match.group(1).lower() == "contains" else "equals"
        raw_value = match.group(2).strip().rstrip('.')
        if raw_value and len(raw_value) <= 500:
            chosen = _INVERT[kind] if deleting else kind
            return result("filter", col, chosen, raw_value,
                          f"Review this {col} filter before exporting. The saved original is unchanged.")
    return result(message=f"I found column {col}. Choose the operation and value in Filter & export, or try: 'Keep {col} above 6'.")
