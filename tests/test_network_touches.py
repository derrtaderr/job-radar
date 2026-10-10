"""The touch ledger: one append-only row per message sent or reply heard."""
import pytest

from engine.network.errors import NetworkError
from engine.network.touches import (
    COLUMNS, Touch, append_touch, latest_by_person, load_touches,
    parse_touches, validate_touch)


def T(**kw):
    base = dict(date="2026-10-12", posting_id="", company="Harborlight",
                person_slug="ana-rivera", path="warm", motive="referral_ask",
                hook_level="shared_history", register="", control="no",
                state="asked", note="")
    base.update(kw)
    return Touch(**base)


def test_append_writes_header_once_and_round_trips(tmp_path):
    path = tmp_path / "touches.csv"
    append_touch(path, T())
    append_touch(path, T(date="2026-10-13", state="replied"))
    text = path.read_text()
    assert text.count(",".join(COLUMNS)) == 1
    assert len(load_touches(path)) == 2


def test_company_with_a_comma_survives(tmp_path):
    path = tmp_path / "touches.csv"
    append_touch(path, T(company="Harborlight, Inc."))
    assert load_touches(path)[0].company == "Harborlight, Inc."


@pytest.mark.parametrize("bad, needle", [
    (dict(state="ghosted"), "state"),
    (dict(date="12/10/2026"), "date"),
    (dict(path="friend"), "path"),
    (dict(company=""), "company"),
    (dict(person_slug=""), "person"),
    (dict(control="maybe"), "control"),
])
def test_validate_names_the_problem(bad, needle):
    problems = validate_touch(T(**bad))
    assert problems and needle in problems[0]


def test_applied_and_override_need_no_person():
    assert validate_touch(T(state="applied", person_slug="", path="")) == []
    assert validate_touch(T(state="override", person_slug="", path="")) == []


def test_malformed_row_is_loud_with_line_number(tmp_path):
    path = tmp_path / "touches.csv"
    append_touch(path, T())
    with path.open("a") as f:
        f.write("2026-10-13,,Harborlight,ana-rivera,warm,,,,no,ghosted,\n")
    with pytest.raises(NetworkError, match="line 3"):
        load_touches(path)


def test_missing_file_is_empty(tmp_path):
    assert load_touches(tmp_path / "touches.csv") == []


def test_newest_row_per_person_wins_with_row_order_breaking_ties():
    rows = [T(), T(state="replied"), T(date="2026-10-11", state="declined")]
    latest = latest_by_person(rows, {})
    assert latest[("harborlight", "ana-rivera")].state == "replied"


def test_parse_rejects_a_wrong_header():
    touches, problems = parse_touches("date,company\n2026-10-12,X\n")
    assert touches == [] and "missing required column" in problems[0]
