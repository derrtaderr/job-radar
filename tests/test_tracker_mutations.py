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

from engine.loop.tracker_edit import TrackerEditError, add_row, move_row
from engine.loop.tracker_schema import parse_tracker
from tests.fixtures_tracker import DUPLICATE_COMPANY_ROLE, VALID_TRACKER


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


# --- move_row: diff helper -------------------------------------------------

def _assert_only_move(old_text, new_text):
    """Assert new_text is old_text with exactly one line removed and
    exactly one line inserted elsewhere — every other line unchanged, in
    order, wherever it now sits. Returns (removed_line, inserted_line)."""
    old_lines, new_lines, opcodes = _opcodes(old_text, new_text)
    removed, inserted = [], []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        removed += old_lines[i1:i2]
        inserted += new_lines[j1:j2]
    assert len(removed) == 1, (removed, opcodes)
    assert len(inserted) == 1, (inserted, opcodes)
    return removed[0], inserted[0]


# --- move_row: happy path ---------------------------------------------------

def test_move_row_maps_shared_columns_drops_source_only_takes_extra():
    new_text = move_row(
        VALID_TRACKER, "Meridian Analytics", "Analytics Engineer",
        "drafted but not applied", "active",
        {"Stage": "Applied", "Last touch": "2026-09-13"})
    _assert_only_move(VALID_TRACKER, new_text)

    sections = parse_tracker(new_text)
    assert sections["drafted but not applied"].rows == []

    active_companies = {r["Company"]: r for r in sections["active"].rows}
    row = active_companies["Meridian Analytics"]
    assert row["Role"] == "Analytics Engineer"
    assert row["Source"] == "Job board"          # shared, carried from source
    assert row["Comp band"] == "140-165k"        # shared, carried from source
    assert row["Next step"] == "Finish cover letter"
    assert row["Notes"] == "JD emphasizes SQL"
    assert row["Stage"] == "Applied"             # target-only, from extra
    assert row["Last touch"] == "2026-09-13"     # target-only, from extra
    # "Resume" was Drafted-only — nothing to carry it forward to in Active,
    # and the interface is by name, so it never shows up under a wrong key.


def test_move_row_matches_annotation_tolerant_company_cell():
    # Tracker cell is "Harborlight (via referral)"; caller passes the bare
    # name, same tolerance tracker_suppresses gives a scraped company name.
    new_text = move_row(
        VALID_TRACKER, "Harborlight", "Senior Data Engineer",
        "active", "closed",
        {"Date closed": "2026-09-13", "Outcome": "Withdrew"})
    _assert_only_move(VALID_TRACKER, new_text)

    sections = parse_tracker(new_text)
    assert not any("Harborlight" in (r.get("Company") or "")
                   for r in sections["active"].rows)
    closed = next(r for r in sections["closed"].rows
                  if "Harborlight" in r["Company"])
    assert closed["Company"] == "Harborlight (via referral)"
    assert closed["Role"] == "Senior Data Engineer"
    assert closed["Date closed"] == "2026-09-13"
    assert closed["Outcome"] == "Withdrew"


# --- move_row: refusal cases -------------------------------------------------

def test_move_row_zero_match_raises_naming_company_and_role():
    try:
        move_row(VALID_TRACKER, "Nonexistent Corp", "Ghost Role",
                 "active", "closed", {})
        assert False, "expected TrackerEditError"
    except TrackerEditError as e:
        assert "Nonexistent Corp" in str(e) and "Ghost Role" in str(e)


def test_move_row_ambiguous_match_raises_naming_both_lines():
    try:
        move_row(DUPLICATE_COMPANY_ROLE, "Cobalt Grid", "Data Platform Engineer",
                 "active", "closed", {})
        assert False, "expected TrackerEditError"
    except TrackerEditError as e:
        msg = str(e)
        assert "Cobalt Grid" in msg or "2" in msg
        assert "5" in msg and "6" in msg  # the two matching data-row lines


def test_move_row_unknown_from_section_raises():
    try:
        move_row(VALID_TRACKER, "Cobalt Grid", "Data Platform Engineer",
                 "not-a-section", "closed", {})
        assert False, "expected TrackerEditError"
    except TrackerEditError as e:
        assert "not-a-section" in str(e)


def test_move_row_unknown_to_section_raises():
    try:
        move_row(VALID_TRACKER, "Cobalt Grid", "Data Platform Engineer",
                 "active", "not-a-section", {})
        assert False, "expected TrackerEditError"
    except TrackerEditError as e:
        assert "not-a-section" in str(e)


def test_move_row_unknown_extra_key_raises_naming_it():
    try:
        move_row(VALID_TRACKER, "Meridian Analytics", "Analytics Engineer",
                 "drafted but not applied", "active", {"Salary": "999k"})
        assert False, "expected TrackerEditError"
    except TrackerEditError as e:
        assert "Salary" in str(e)
