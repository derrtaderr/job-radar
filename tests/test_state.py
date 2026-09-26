import json
from pathlib import Path

from engine.radar.state import (
    entry_field,
    fingerprints,
    load_state,
    make_entry,
    save_state,
    seen_date,
)


def test_state_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    save_state({"j1": "2026-09-13"}, p)
    assert load_state(p) == {"j1": "2026-09-13"}


def test_save_state_ends_with_trailing_newline(tmp_path):
    p = tmp_path / "state.json"
    save_state({"a": "b"}, p)
    assert p.read_text().endswith("\n")


def test_save_state_is_stable_and_sorted(tmp_path):
    # State is committed to a file a human may diff; unsorted keys would make
    # every run look like a change even when nothing moved.
    p = tmp_path / "state.json"
    save_state({"z": "2026-09-13", "a": "2026-09-12"}, p)
    assert list(json.loads(p.read_text())) == ["a", "z"]


def test_load_state_missing_file_is_empty(tmp_path):
    assert load_state(tmp_path / "nope.json") == {}


def test_load_state_corrupt_file_returns_empty(tmp_path, capsys):
    # A corrupt state file must degrade to "we've seen nothing" loudly, never
    # crash the run — but the warning has to name the file so it's fixable.
    p = tmp_path / "state.json"
    p.write_text("{not valid json")
    assert load_state(p) == {}
    assert "corrupt" in capsys.readouterr().out.lower()


def test_load_state_accepts_str_path(tmp_path):
    p = tmp_path / "state.json"
    save_state({"j1": "2026-09-13"}, str(p))
    assert load_state(str(p)) == {"j1": "2026-09-13"}


# --- entry shape (row 64) -----------------------------------------------------
#
# state.json's VALUE grew from a bare date string to a dict carrying the seen
# date, the company/title the run saw, and the two content fingerprints that
# make cross-day repost matching possible. The READER still accepts the legacy
# string, because a real user's state file predates this change and silently
# re-queueing their whole search history would be the worst possible upgrade.

def test_seen_date_reads_a_legacy_string_entry():
    assert seen_date("2026-09-13") == "2026-09-13"


def test_seen_date_reads_a_dict_entry():
    assert seen_date(make_entry("2026-09-13")) == "2026-09-13"


def test_make_entry_carries_company_title_and_both_fingerprints():
    entry = make_entry("2026-09-13", company="Cobalt Grid",
                       title="Data Platform Engineer",
                       fp_comp="c0ffee", fp_body="decaf0")
    assert seen_date(entry) == "2026-09-13"
    assert entry_field(entry, "company") == "Cobalt Grid"
    assert entry_field(entry, "title") == "Data Platform Engineer"
    assert fingerprints(entry) == ("c0ffee", "decaf0")


def test_entry_field_of_a_legacy_string_entry_is_none():
    # A legacy entry knows its date and nothing else. Inventing a value here
    # would let a ledger row match a posting on a field nobody ever recorded.
    assert entry_field("2026-09-13", "company") is None
    assert entry_field("2026-09-13", "title") is None


def test_fingerprints_of_a_legacy_string_entry_are_both_none():
    assert fingerprints("2026-09-13") == (None, None)


def test_a_legacy_shaped_state_file_still_loads(tmp_path):
    # The upgrade path, end to end: a state.json written by an older version
    # loads without error and keeps its dates readable.
    p = tmp_path / "state.json"
    p.write_text('{"j1": "2026-09-12", "j2": "2026-09-13"}\n')
    loaded = load_state(p)
    assert seen_date(loaded["j1"]) == "2026-09-12"
    assert seen_date(loaded["j2"]) == "2026-09-13"


def test_a_mixed_legacy_and_dict_state_file_round_trips(tmp_path):
    # Yesterday's entries stay strings, today's are dicts, and one file holds
    # both — which is exactly what the first run after this change writes.
    p = tmp_path / "state.json"
    save_state({"old": "2026-09-12",
                "new": make_entry("2026-09-13", company="Cobalt Grid")}, p)
    loaded = load_state(p)
    assert seen_date(loaded["old"]) == "2026-09-12"
    assert entry_field(loaded["new"], "company") == "Cobalt Grid"
