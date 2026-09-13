import json
from pathlib import Path

from engine.radar.state import load_state, save_state


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
