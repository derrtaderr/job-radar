"""Header-driven tracker parsing and validation (engine/loop/tracker_schema.py).

All fixtures are synthetic (tests/fixtures_tracker.py) — fictional companies,
real column headers. Nothing here describes a real search.
"""
from engine.loop.tracker_schema import parse_tracker, tracker_check
from tests.fixtures_tracker import (
    BAD_ISO_DATE_ACTIVE,
    BAD_ISO_DATE_CLOSED,
    CELL_COUNT_MISMATCH,
    CELL_COUNT_MISMATCH_SUPPRESSES_DOWNSTREAM_CHECKS,
    DUPLICATE_COMPANY_ROLE,
    DUPLICATE_IN_CLOSED_ALLOWED,
    DUPLICATE_IN_DRAFTED_STILL_FLAGGED,
    ESCAPED_PIPE_CELL,
    MISSING_ACTIVE_SECTION,
    MISSING_CLOSED_SECTION,
    MISSING_REQUIRED_COLUMN_ACTIVE,
    MISSING_REQUIRED_COLUMN_CLOSED,
    MORE_CELLS_THAN_HEADERS,
    VALID_TRACKER,
)


# --- parse_tracker: happy path ---

def test_valid_tracker_parses_all_four_sections():
    sections = parse_tracker(VALID_TRACKER)
    assert set(sections) == {"active", "drafted but not applied", "research", "closed"}


def test_parenthetical_section_heading_is_normalized():
    # "## Research (JD filed, no work started)" -> key "research"
    sections = parse_tracker(VALID_TRACKER)
    assert "research" in sections
    assert len(sections["research"].rows) == 2


def test_row_count_matches_fixture_across_sections():
    sections = parse_tracker(VALID_TRACKER)
    total = sum(len(t.rows) for t in sections.values())
    assert total == 8


def test_row_lookup_by_header_name_is_case_insensitive():
    sections = parse_tracker(VALID_TRACKER)
    row = sections["active"].rows[0]
    assert row["Company"] == "Cobalt Grid"
    assert row.get("company") == "Cobalt Grid"
    assert row.get("COMPANY") == "Cobalt Grid"
    assert row.get("Role") == "Data Platform Engineer"


def test_annotated_cell_is_preserved_verbatim():
    sections = parse_tracker(VALID_TRACKER)
    companies = [row["Company"] for row in sections["active"].rows]
    assert "Harborlight (via referral)" in companies


def test_row_line_numbers_are_1_based_in_original_text():
    lines = VALID_TRACKER.splitlines()
    sections = parse_tracker(VALID_TRACKER)
    row = sections["active"].rows[0]
    assert lines[row.line - 1].strip().startswith("| Cobalt Grid")


def test_row_line_numbers_are_exact_for_a_later_section():
    lines = VALID_TRACKER.splitlines()
    sections = parse_tracker(VALID_TRACKER)
    row = sections["closed"].rows[-1]
    assert "Northwind Analytics" in lines[row.line - 1]


def test_unknown_prose_only_section_is_absent_not_a_violation():
    text = VALID_TRACKER + "\n## Strategy note\n\nJust prose here, no table.\n"
    sections = parse_tracker(text)
    assert "strategy note" not in sections
    assert tracker_check(text) == []


def test_table_bearing_unknown_section_is_returned():
    text = VALID_TRACKER + "\n## Schema notes\n\n| Field | Type |\n|---|---|\n| id | int |\n"
    sections = parse_tracker(text)
    assert "schema notes" in sections
    assert sections["schema notes"].rows[0]["Field"] == "id"


# --- tracker_check: happy path ---

def test_valid_tracker_has_no_violations():
    assert tracker_check(VALID_TRACKER) == []


# --- tracker_check: missing required sections ---

def test_missing_active_section_is_a_violation():
    violations = tracker_check(MISSING_ACTIVE_SECTION)
    assert any("Active" in v and "missing" in v for v in violations)


def test_missing_closed_section_is_a_violation():
    violations = tracker_check(MISSING_CLOSED_SECTION)
    assert any("Closed" in v and "missing" in v for v in violations)


def test_empty_text_reports_both_missing_sections():
    violations = tracker_check("")
    assert any("Active" in v for v in violations)
    assert any("Closed" in v for v in violations)
    assert len(violations) == 2


# --- tracker_check: missing required columns ---

def test_active_missing_last_touch_column_is_a_violation():
    violations = tracker_check(MISSING_REQUIRED_COLUMN_ACTIVE)
    assert any("Last touch" in v and "Active" in v for v in violations)


def test_closed_missing_outcome_column_is_a_violation():
    violations = tracker_check(MISSING_REQUIRED_COLUMN_CLOSED)
    assert any("Outcome" in v and "Closed" in v for v in violations)


def test_extra_columns_are_tolerated():
    # VALID_TRACKER's Active section carries Source/Stage/Comp band/Next
    # step/Notes beyond the three required columns — none of that gates.
    assert tracker_check(VALID_TRACKER) == []


# --- tracker_check: cell count mismatch ---

def test_row_cell_count_mismatch_names_the_line():
    violations = tracker_check(CELL_COUNT_MISMATCH)
    # The short row is line 5 (1: heading, 2: blank, 3: header, 4: separator, 5: data).
    assert any("line 5" in v for v in violations)
    assert any("cells" in v for v in violations)


# --- tracker_check: ISO date validation ---

def test_non_iso_last_touch_is_a_violation():
    violations = tracker_check(BAD_ISO_DATE_ACTIVE)
    assert any("Last touch" in v and "TBD" in v for v in violations)


def test_non_iso_date_closed_is_a_violation():
    violations = tracker_check(BAD_ISO_DATE_CLOSED)
    assert any("Date closed" in v and "recently" in v for v in violations)


def test_annotated_date_cell_is_valid():
    # "2026-09-12 (sent reply)" carries an ISO date plus prose — must not
    # be flagged just because the cell isn't a bare date.
    text = (
        "## Active\n\n"
        "| Company | Role | Last touch |\n|---|---|---|\n"
        "| Cobalt Grid | Data Platform Engineer | 2026-09-12 (sent reply) |\n\n"
        "## Closed\n\n"
        "| Company | Role | Date closed | Outcome |\n|---|---|---|---|\n"
        "| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |\n"
    )
    assert tracker_check(text) == []


def test_empty_date_cell_does_not_violate():
    text = (
        "## Active\n\n"
        "| Company | Role | Last touch |\n|---|---|---|\n"
        "| Cobalt Grid | Data Platform Engineer | |\n\n"
        "## Closed\n\n"
        "| Company | Role | Date closed | Outcome |\n|---|---|---|---|\n"
        "| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |\n"
    )
    assert tracker_check(text) == []


# --- tracker_check: duplicate Company+Role ---

def test_duplicate_company_role_names_both_lines():
    violations = tracker_check(DUPLICATE_COMPANY_ROLE)
    dup = [v for v in violations if "duplicate" in v.lower()]
    assert len(dup) == 1
    assert "line" in dup[0] or "lines" in dup[0]
    assert "5" in dup[0] and "6" in dup[0]


def test_duplicate_across_different_sections_does_not_violate():
    # Same company applying for the same role in two different sections
    # (e.g. drafted, then moved to active) is not a same-section duplicate.
    text = (
        "## Active\n\n"
        "| Company | Role | Last touch |\n|---|---|---|\n"
        "| Cobalt Grid | Data Platform Engineer | 2026-09-10 |\n\n"
        "## Drafted but not applied\n\n"
        "| Company | Role | Comp band |\n|---|---|---|\n"
        "| Cobalt Grid | Data Platform Engineer | 150-180k |\n\n"
        "## Closed\n\n"
        "| Company | Role | Date closed | Outcome |\n|---|---|---|---|\n"
        "| Meridian Rows | Data Engineer | 2026-08-20 | Rejected |\n"
    )
    assert tracker_check(text) == []


# --- CRITICAL fix: duplicate scope is Active/Drafted only, not Closed/Research ---
# Orchestrator ruling 2026-09-13: Closed is append-only by design (reapplication
# cycles months apart legitimately repeat Company+Role — Crux, EZO.io, Tempo on
# the real tracker); Research allows repeats too. Only Active and Drafted but
# not applied gate, because a role can't be live twice AT ONCE.

def test_duplicate_company_role_in_closed_is_allowed():
    assert tracker_check(DUPLICATE_IN_CLOSED_ALLOWED) == []


def test_duplicate_company_role_in_drafted_still_flags_both_lines():
    violations = tracker_check(DUPLICATE_IN_DRAFTED_STILL_FLAGGED)
    dup = [v for v in violations if "duplicate" in v.lower()]
    assert len(dup) == 1
    assert "Meridian Analytics" in dup[0]
    assert "11" in dup[0] and "12" in dup[0]


def test_duplicate_company_role_in_active_still_flags_both_lines():
    # Regression: Active stays gated after the scope fix.
    violations = tracker_check(DUPLICATE_COMPANY_ROLE)
    dup = [v for v in violations if "duplicate" in v.lower()]
    assert len(dup) == 1
    assert "5" in dup[0] and "6" in dup[0]


# --- IMPORTANT 1: escaped pipes inside a cell must not split the row ---

def test_escaped_pipe_cell_parses_as_one_cell():
    sections = parse_tracker(ESCAPED_PIPE_CELL)
    row = sections["active"].rows[0]
    assert row.raw_cell_count == 3
    assert row["Role"] == "Growth | Ops Engineer"


def test_escaped_pipe_cell_produces_no_violations():
    assert tracker_check(ESCAPED_PIPE_CELL) == []


# --- MINOR: more cells than headers drops the overflow, still flags the row ---

def test_more_cells_than_headers_drops_overflow_and_flags_line():
    sections = parse_tracker(MORE_CELLS_THAN_HEADERS)
    row = sections["active"].rows[0]
    assert row.raw_cell_count == 4
    assert row["Last touch"] == "2026-09-10"
    assert row.get("Extra cell") is None  # no fourth header to key it under

    violations = tracker_check(MORE_CELLS_THAN_HEADERS)
    assert any("line 5" in v and "4 cells" in v and "3" in v for v in violations)


# --- a cell-count mismatch suppresses downstream column checks on that row ---
# Column identity is unreliable once the count is wrong (found on a real
# malformed row on a live tracker) — one real bug should report as ONE
# violation, not a cell-count mismatch plus a spurious ISO-date violation on
# a column that shifted left.

def test_cell_count_mismatch_does_not_also_fire_iso_date_check():
    violations = tracker_check(CELL_COUNT_MISMATCH_SUPPRESSES_DOWNSTREAM_CHECKS)
    closed_violations = [v for v in violations if "Closed section" in v]
    assert len(closed_violations) == 1
    assert "cells" in closed_violations[0]
