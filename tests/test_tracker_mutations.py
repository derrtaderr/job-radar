"""Tracker mutations — add_row, move_row, touch_row (engine/loop/tracker_edit.py).

Structural counterpart to test_tracker_schema.py: where that suite proves
parse_tracker/tracker_check read the tracker file correctly, this suite
proves the mutation functions WRITE it correctly — touching only the
line(s) an edit concerns and leaving everything else byte-identical. The
diff helpers below use difflib rather than hardcoded line numbers/spacing
so a test still holds if the exact cell padding an implementation chooses
changes; what must never change is which OTHER lines moved.

All fixtures are synthetic (fictional companies, real column-header shape).
"""
import difflib

from engine.loop.tracker_edit import TrackerEditError, add_row
from engine.loop.tracker_schema import parse_tracker
from tests.fixtures_tracker import VALID_TRACKER


# --- diff helpers --------------------------------------------------------

def _opcodes(old_text, new_text):
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    return old_lines, new_lines, sm.get_opcodes()


def _assert_only_insertion(old_text, new_text):
    """Assert new_text is old_text with exactly one line inserted somewhere
    and nothing else touched. Returns the inserted line's text."""
    old_lines, new_lines, opcodes = _opcodes(old_text, new_text)
    inserted = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        assert tag == "insert", (
            f"expected only an insertion, got {tag!r} at {(i1, i2, j1, j2)}: "
            f"old={old_lines[i1:i2]!r} new={new_lines[j1:j2]!r}")
        inserted += new_lines[j1:j2]
    assert len(inserted) == 1, (inserted, opcodes)
    return inserted[0]


# --- add_row: happy path --------------------------------------------------

def test_add_row_appends_after_last_row_ordered_by_headers():
    new_text = add_row(VALID_TRACKER, "research", {
        "Company": "Solace Systems",
        "Role": "Data Engineer",
        "Comp band": "150-175k",
        "Lean": "Lean yes",
        "Notes": "Fully remote",
    })
    inserted = _assert_only_insertion(VALID_TRACKER, new_text)
    assert inserted.startswith("|") and inserted.strip().endswith("|")

    sections = parse_tracker(new_text)
    research_rows = sections["research"].rows
    assert len(research_rows) == 3  # fixture had 2
    new_row = research_rows[-1]
    assert new_row["Company"] == "Solace Systems"
    assert new_row["Role"] == "Data Engineer"
    assert new_row["Comp band"] == "150-175k"
    assert new_row["Lean"] == "Lean yes"
    assert new_row["Notes"] == "Fully remote"


def test_add_row_appends_at_end_of_file_for_last_section():
    new_text = add_row(VALID_TRACKER, "closed", {
        "Company": "Solace Systems",
        "Role": "Data Engineer",
        "Date closed": "2026-09-13",
        "Outcome": "Withdrew",
    })
    _assert_only_insertion(VALID_TRACKER, new_text)
    sections = parse_tracker(new_text)
    companies = [r["Company"] for r in sections["closed"].rows]
    assert companies[-1] == "Solace Systems"


def test_add_row_missing_keys_become_empty_cells():
    new_text = add_row(VALID_TRACKER, "research", {"Company": "Solace Systems"})
    _assert_only_insertion(VALID_TRACKER, new_text)
    sections = parse_tracker(new_text)
    new_row = sections["research"].rows[-1]
    assert new_row["Company"] == "Solace Systems"
    assert new_row["Role"] == ""
    assert new_row["Comp band"] == ""
    assert new_row["Lean"] == ""
    assert new_row["Notes"] == ""


def test_add_row_escapes_literal_pipe_in_a_cell():
    new_text = add_row(VALID_TRACKER, "research", {
        "Company": "Solace Systems", "Notes": "Growth | Ops team",
    })
    sections = parse_tracker(new_text)
    new_row = sections["research"].rows[-1]
    # round-trips back to the literal pipe once re-parsed
    assert new_row["Notes"] == "Growth | Ops team"


# --- add_row: refusal cases ------------------------------------------------

def test_add_row_unknown_key_raises_naming_it():
    try:
        add_row(VALID_TRACKER, "research", {"Company": "X", "Salary": "999k"})
        assert False, "expected TrackerEditError"
    except TrackerEditError as e:
        assert "Salary" in str(e)


def test_add_row_unknown_section_raises_naming_it():
    try:
        add_row(VALID_TRACKER, "not-a-real-section", {"Company": "X"})
        assert False, "expected TrackerEditError"
    except TrackerEditError as e:
        assert "not-a-real-section" in str(e)
