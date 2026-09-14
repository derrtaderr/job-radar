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
import pytest

from engine.loop.tracker_edit import TrackerEditError, add_row, move_row, touch_row
from engine.loop.tracker_schema import parse_tracker
from tests.fixtures_tracker import DUPLICATE_COMPANY_ROLE, VALID_TRACKER

# A hand-edited tracker carries formatting noise VALID_TRACKER doesn't: an
# annotation, uneven pipe spacing (none at all on one row, extra padding on
# another), a **bold** cell, and a cell with an escaped literal pipe. Every
# company here is fictional. This fixture exists to prove touch_row's
# byte-for-byte claim survives that noise, not just clean input.
MESSY_TRACKER = """\
## Active

| Company | Role | Source | Stage | Comp band | Last touch | Next step | Notes |
|---|---|---|---|---|---|---|---|
|Cobalt Grid|**Data Platform Engineer**|LinkedIn|HM round|150-180k|2026-09-10|Send follow-up|Growth \\| Ops team|
| Harborlight (via referral)   |  Senior Data Engineer  | Referral | Screen | 160-190k | 2026-09-12 | Await scheduling | Warm intro from Alex |

## Drafted but not applied

| Company | Role | Source | Comp band | Resume | Next step | Notes |
|---|---|---|---|---|---|---|
| Meridian Analytics | Analytics Engineer | Job board | 140-165k | v3 | Finish cover letter | JD emphasizes SQL |

## Closed

| Company | Role | Date closed | Outcome | Reason | Carry-forward lesson |
|---|---|---|---|---|---|
| Meridian Rows | Data Engineer | 2026-08-20 | Rejected | Final round, lost to internal candidate | Ask about internal candidates earlier |
"""


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


# --- touch_row: diff helper --------------------------------------------

def _assert_only_line_change(old_text, new_text):
    """Assert new_text is old_text with exactly one line changed IN PLACE
    (same index, nothing inserted or removed). Returns
    (index, old_line, new_line)."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    assert len(old_lines) == len(new_lines)
    diffs = [i for i in range(len(old_lines)) if old_lines[i] != new_lines[i]]
    assert len(diffs) == 1, diffs
    i = diffs[0]
    return i, old_lines[i], new_lines[i]


# --- touch_row: happy path -----------------------------------------------

def test_touch_row_updates_cell_preserves_rest_of_line():
    new_text = touch_row(VALID_TRACKER, "active", "Cobalt Grid",
                          "Data Platform Engineer", "Last touch", "2026-09-13")
    _, old_line, new_line = _assert_only_line_change(VALID_TRACKER, new_text)
    assert "2026-09-10" in old_line
    assert "2026-09-13" in new_line and "2026-09-10" not in new_line

    sections = parse_tracker(new_text)
    row = next(r for r in sections["active"].rows if r["Company"] == "Cobalt Grid")
    assert row["Last touch"] == "2026-09-13"
    assert row["Role"] == "Data Platform Engineer"  # untouched cell intact
    assert row["Next step"] == "Send follow-up"
    assert row["Notes"] == "Strong tech fit"


def test_touch_row_preserves_messy_row_byte_for_byte_except_touched_cell():
    new_text = touch_row(MESSY_TRACKER, "active", "Harborlight",
                          "Senior Data Engineer", "Last touch", "2026-09-13")
    _, old_line, new_line = _assert_only_line_change(MESSY_TRACKER, new_text)
    # untouched cells' exact (uneven) padding survives verbatim
    assert "Harborlight (via referral)   " in new_line
    assert "  Senior Data Engineer  " in new_line
    assert "2026-09-13" in new_line and "2026-09-12" not in new_line

    # the OTHER data row (bold cell, escaped pipe, zero pipe padding) never
    # moved and was never touched, let alone reformatted
    other_old = next(l for l in MESSY_TRACKER.splitlines() if "Cobalt Grid" in l)
    other_new = next(l for l in new_text.splitlines() if "Cobalt Grid" in l)
    assert other_old == other_new
    assert "**Data Platform Engineer**" in other_new
    assert "Growth \\| Ops team" in other_new


# --- touch_row: refusal cases ----------------------------------------------

def test_touch_row_unknown_column_raises_naming_it():
    try:
        touch_row(VALID_TRACKER, "active", "Cobalt Grid",
                  "Data Platform Engineer", "Not A Column", "x")
        assert False, "expected TrackerEditError"
    except TrackerEditError as e:
        assert "Not A Column" in str(e)


def test_touch_row_unknown_section_raises_naming_it():
    try:
        touch_row(VALID_TRACKER, "not-a-section", "Cobalt Grid",
                  "Data Platform Engineer", "Last touch", "2026-09-13")
        assert False, "expected TrackerEditError"
    except TrackerEditError as e:
        assert "not-a-section" in str(e)


def test_touch_row_zero_match_raises_naming_company():
    try:
        touch_row(VALID_TRACKER, "active", "Nonexistent Corp", "Ghost Role",
                  "Last touch", "2026-09-13")
        assert False, "expected TrackerEditError"
    except TrackerEditError as e:
        assert "Nonexistent Corp" in str(e)


def test_touch_row_ambiguous_match_raises_naming_both_lines():
    try:
        touch_row(DUPLICATE_COMPANY_ROLE, "active", "Cobalt Grid",
                  "Data Platform Engineer", "Last touch", "2026-09-13")
        assert False, "expected TrackerEditError"
    except TrackerEditError as e:
        assert "5" in str(e) and "6" in str(e)


# --- CLI: add / move / touch subcommands ------------------------------------

from tools.tracker_cli import main as cli_main  # noqa: E402


def _write(tmp_path, text):
    path = tmp_path / "tracker.md"
    path.write_text(text)
    return path


def test_cli_add_writes_new_row_and_prints_diff(tmp_path, capsys):
    path = _write(tmp_path, VALID_TRACKER)
    rc = cli_main(["add", str(path), "--section", "research",
                   "--set", "Company=Solace Systems",
                   "--set", "Role=Data Engineer"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Solace Systems" in out  # diff shown before writing
    sections = parse_tracker(path.read_text())
    assert any(r["Company"] == "Solace Systems" for r in sections["research"].rows)


def test_cli_add_dry_run_does_not_write(tmp_path, capsys):
    path = _write(tmp_path, VALID_TRACKER)
    original = path.read_text()
    rc = cli_main(["add", str(path), "--section", "research",
                   "--set", "Company=Solace Systems", "--dry-run"])
    assert rc == 0
    assert path.read_text() == original
    assert "Solace Systems" in capsys.readouterr().out


def test_cli_move_writes_target_and_removes_source(tmp_path, capsys):
    path = _write(tmp_path, VALID_TRACKER)
    rc = cli_main(["move", str(path), "--company", "Meridian Analytics",
                   "--role", "Analytics Engineer",
                   "--from", "drafted but not applied", "--to", "active",
                   "--set", "Stage=Applied", "--set", "Last touch=2026-09-13"])
    assert rc == 0
    sections = parse_tracker(path.read_text())
    assert any(r["Company"] == "Meridian Analytics" for r in sections["active"].rows)
    assert not any(r["Company"] == "Meridian Analytics"
                   for r in sections["drafted but not applied"].rows)


def test_cli_touch_updates_cell(tmp_path, capsys):
    path = _write(tmp_path, VALID_TRACKER)
    rc = cli_main(["touch", str(path), "--section", "active",
                   "--company", "Cobalt Grid",
                   "--role", "Data Platform Engineer",
                   "--column", "Last touch", "--value", "2026-09-13"])
    assert rc == 0
    sections = parse_tracker(path.read_text())
    row = next(r for r in sections["active"].rows if r["Company"] == "Cobalt Grid")
    assert row["Last touch"] == "2026-09-13"


def test_cli_touch_unknown_column_errors_without_writing(tmp_path, capsys):
    path = _write(tmp_path, VALID_TRACKER)
    original = path.read_text()
    rc = cli_main(["touch", str(path), "--section", "active",
                   "--company", "Cobalt Grid",
                   "--role", "Data Platform Engineer",
                   "--column", "Not A Column", "--value", "x"])
    assert rc == 1
    assert path.read_text() == original


# --- touch_row on a table whose rows have no trailing pipe ------------------
# "| a | b | c" is a legal markdown row and tracker_check passes it clean, so
# touch_row is reachable with it. Splicing between pipe[i] and pipe[i+1] then
# walks off the end on the LAST column. It failed closed, but with a raw
# IndexError rather than anything a caller could act on.

_NO_TRAILING_PIPE = (
    "## Active\n\n"
    "| Company | Role | Last touch\n"
    "|---|---|---\n"
    "| Cobalt Grid | Data Engineer | 2026-09-10\n\n"
    "## Closed\n\n"
    "| Company | Role | Date closed | Outcome\n"
    "|---|---|---|---\n")


def test_the_fixture_really_is_check_clean():
    # If this ever starts reporting violations the test below is proving
    # nothing — the shape would be rejected upstream instead.
    from engine.loop.tracker_schema import tracker_check
    assert tracker_check(_NO_TRAILING_PIPE) == []


def test_touch_last_column_without_a_trailing_pipe(tmp_path):
    from engine.loop.tracker_edit import touch_row
    out = touch_row(_NO_TRAILING_PIPE, "Active", "Cobalt Grid",
                    "Data Engineer", "Last touch", "2026-09-13")
    assert "| Cobalt Grid | Data Engineer | 2026-09-13" in out
    assert "2026-09-10" not in out


def test_touch_mid_column_without_a_trailing_pipe_is_unaffected(tmp_path):
    # The control: a column with a pipe after it still splices exactly as it
    # always did, so the fix cannot be a blanket "write to end of line".
    from engine.loop.tracker_edit import touch_row
    out = touch_row(_NO_TRAILING_PIPE, "Active", "Cobalt Grid",
                    "Data Engineer", "Role", "Senior Data Engineer")
    assert "| Cobalt Grid | Senior Data Engineer | 2026-09-10" in out


def test_touch_last_column_preserves_a_trailing_pipe_when_there_is_one(tmp_path):
    # The normal shape must keep its closing pipe — the end-of-line splice is
    # only for rows that genuinely have no pipe after the target cell.
    from engine.loop.tracker_edit import touch_row
    text = (
        "## Active\n\n"
        "| Company | Role | Last touch |\n"
        "|---|---|---|\n"
        "| Cobalt Grid | Data Engineer | 2026-09-10 |\n\n"
        "## Closed\n\n"
        "| Company | Role | Date closed | Outcome |\n"
        "|---|---|---|---|\n")
    out = touch_row(text, "Active", "Cobalt Grid", "Data Engineer",
                    "Last touch", "2026-09-13")
    assert "| Cobalt Grid | Data Engineer | 2026-09-13 |" in out


# --- add_row must not create a row move/touch can never find again ----------
# `add` builds its row from --set values alone, with no source row to inherit
# Company and Role from. A row with both cells empty passes `check` (which
# only requires the COLUMNS to exist) and is then unreachable forever: every
# later move/touch matches on Company+Role. The loop docs already tell the
# operator to set both; this is the tool-level backstop behind that advice.

_MIN_TRACKER = (
    "## Active\n\n"
    "| Company | Role | Stage | Last touch |\n"
    "|---|---|---|---|\n"
    "| Cobalt Grid | Data Engineer | Applied | 2026-09-10 |\n\n"
    "## Drafted but not applied\n\n"
    "| Company | Role | Next step |\n"
    "|---|---|---|\n"
    "| Meridian Analytics | Analytics Engineer | Finish cover |\n\n"
    "## Closed\n\n"
    "| Company | Role | Date closed | Outcome |\n"
    "|---|---|---|---|\n"
    "| Northwind Analytics | Data Engineer | 2026-07-15 | Withdrew |\n")


def test_add_row_refuses_a_missing_company_in_active():
    from engine.loop.tracker_edit import TrackerEditError, add_row
    with pytest.raises(TrackerEditError, match="Company"):
        add_row(_MIN_TRACKER, "Active", {"Role": "Data Engineer",
                                         "Stage": "Applied"})


def test_add_row_refuses_a_missing_role_in_active():
    from engine.loop.tracker_edit import TrackerEditError, add_row
    with pytest.raises(TrackerEditError, match="Role"):
        add_row(_MIN_TRACKER, "Active", {"Company": "Tessellate",
                                         "Stage": "Applied"})


def test_add_row_refuses_a_blank_company_in_active():
    # Present-but-empty is the same unreachable row as absent.
    from engine.loop.tracker_edit import TrackerEditError, add_row
    with pytest.raises(TrackerEditError, match="Company"):
        add_row(_MIN_TRACKER, "Active", {"Company": "   ",
                                         "Role": "Data Engineer"})


def test_add_row_refuses_a_missing_company_in_drafted():
    from engine.loop.tracker_edit import TrackerEditError, add_row
    with pytest.raises(TrackerEditError, match="Company"):
        add_row(_MIN_TRACKER, "Drafted but not applied",
                {"Role": "Analytics Engineer"})


def test_add_row_accepts_both_cells_populated():
    from engine.loop.tracker_edit import add_row
    out = add_row(_MIN_TRACKER, "Active",
                  {"Company": "Tessellate", "Role": "Data Engineer",
                   "Stage": "Applied", "Last touch": "2026-09-13"})
    assert "| Tessellate | Data Engineer | Applied | 2026-09-13 |" in out


# --- trailing-backslash cells: a value ending in "\" would swallow the ------
# next cell's boundary pipe when the row is re-parsed (tracker_schema's
# _split_row treats a pipe preceded by "\" as an escaped literal, not a
# column boundary). Refusing with a named TrackerEditError, rather than
# silently escaping it into some other form, keeps the round-trip contract
# simple: whatever gets written is exactly what re-parses back out, or the
# write never happens.

def test_add_row_refuses_a_value_ending_in_a_trailing_backslash():
    with pytest.raises(TrackerEditError, match=r"backslash"):
        add_row(VALID_TRACKER, "research", {
            "Company": "Solace Systems", "Notes": "C:\\path\\",
        })


def test_touch_row_refuses_a_value_ending_in_a_trailing_backslash():
    with pytest.raises(TrackerEditError, match=r"backslash"):
        touch_row(VALID_TRACKER, "active", "Cobalt Grid",
                  "Data Platform Engineer", "Notes", "trailing slash\\")


def test_add_row_accepts_a_value_with_a_non_trailing_backslash():
    # The refusal is specific to a TRAILING backslash (the one that would
    # actually collide with the next cell's boundary pipe) — a backslash
    # anywhere else in the value is unaffected.
    new_text = add_row(VALID_TRACKER, "research", {
        "Company": "Solace Systems", "Notes": "C:\\path\\to\\thing",
    })
    sections = parse_tracker(new_text)
    new_row = sections["research"].rows[-1]
    assert new_row["Notes"] == "C:\\path\\to\\thing"


def test_add_row_does_not_gate_sections_without_those_columns():
    # The rule protects rows that must stay findable by Company+Role. A table
    # that has no such columns is not that shape and must not be blocked.
    from engine.loop.tracker_edit import add_row
    text = ("## Active\n\n| Note |\n|---|\n| something |\n")
    assert "| later |" in add_row(text, "Active", {"Note": "later"})
