"""v1 milestone 1: private, review-only missing-value filter plans.

This exercises only the deterministic planner; no cloud credentials are needed.
"""
import pytest
from datamendry.assistant_planner import plan_instruction

COLUMNS = ["College_ID", "CGPA", "Region", "Student Name"]


@pytest.mark.parametrize("instruction,expected", [
    ("Show rows where CGPA is missing", "empty"),
    ("Keep rows where Region is blank", "empty"),
    ("Show students with Student Name not empty", "not_empty"),
    ("Remove rows where Region is empty", "not_empty"),
    ("Remove records where CGPA is NOT missing", "empty"),
    ("Show rows with CGPA filled", "not_empty"),
    ("Show rows where CGPA has no value", "empty"),
])
def test_missing_value_plans(instruction, expected):
    plan = plan_instruction(instruction, COLUMNS)
    assert plan["source"] == "guided"
    assert plan["action"] == "filter"
    assert plan["kind"] == expected
    assert plan["value"] == ""
    assert plan["applied"] is False
    assert "original" in plan["message"]


def test_existing_actions_unchanged():
    assert plan_instruction("Remove exact duplicate rows", COLUMNS)["action"] == "deduplicate"
    assert plan_instruction("Trim whitespace", COLUMNS)["action"] == "trim_whitespace"
    assert plan_instruction("Normalize blank cells", COLUMNS)["action"] == "normalize_blanks"
    assert plan_instruction("Keep CGPA above 8", COLUMNS)["kind"] == "gt"
    assert plan_instruction("Remove rows where CGPA below 6", COLUMNS)["kind"] == "gte"
    assert plan_instruction("Delete column College_ID", COLUMNS)["action"] == "exclude_column"


def test_ambiguous_unsupported_requests_do_not_apply():
    for prompt in [
        "Remove missing values",  # No column
        "Show rows where Region and CGPA are missing",  # Multiple columns
        "Show students with CGPA between 6 and 8",  # Not supported
        "Fill missing CGPA with median",  # Not supported
        "Run Python code and delete CSV",  # Never execute
    ]:
        result = plan_instruction(prompt, COLUMNS)
        assert result["action"] == "none", (prompt, result)
        assert result["applied"] is False


def test_only_real_column_names_are_used():
    assert plan_instruction("Show rows where GPA is missing", COLUMNS)["action"] == "none"
    assert plan_instruction("Show rows where CGPA is empty", COLUMNS)["column"] == "CGPA"
