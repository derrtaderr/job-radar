"""People files: one per company, written only by network_cli.py add."""
import datetime

import pytest

from engine.network.errors import NetworkError
from engine.network.people import (
    load_people_dir, mark_left, parse_people, render_people, write_people)

FILE = """\
company: Northwind Analytics
looked_up: 2026-10-10
source: clay
result: found
people:
  - name: Dee Marsh
    title: VP Growth
    url: https://www.linkedin.com/in/example-dm
    role: hiring_manager
  - name: Eli Park
    title: GTM Engineer
    url: https://www.linkedin.com/in/example-ep
    role: recent_hire
    started: 2026-06-01
"""


def test_parse_fills_defaults():
    pf = parse_people(FILE, "northwind-analytics.yaml")
    assert pf.looked_up == datetime.date(2026, 10, 10)
    assert [p.slug for p in pf.people] == ["dee-marsh", "eli-park"]
    assert pf.people[0].status == "current"
    assert pf.people[1].started == "2026-06-01"


def test_round_trip():
    pf = parse_people(FILE, "x")
    assert parse_people(render_people(pf), "x") == pf


@pytest.mark.parametrize("bad, needle", [
    (FILE.replace("role: recent_hire", "role: friend"), "role"),
    (FILE.replace("result: found", "result: maybe"), "result"),
    (FILE.replace("company: Northwind Analytics\n", ""), "company"),
    ("company: X\nlooked_up: 2026-10-10\nsource: clay\nresult: found\n", "no people"),
    (FILE.replace("result: found", "result: none"), "none"),
])
def test_malformed_files_are_named(bad, needle):
    with pytest.raises(NetworkError, match=needle):
        parse_people(bad, "northwind-analytics.yaml")


def test_write_then_load_dir(tmp_path):
    pf = parse_people(FILE, "x")
    path = write_people(tmp_path / "people", pf, {})
    assert path.name == "northwind-analytics.yaml"
    loaded = load_people_dir(tmp_path / "people", {})
    assert loaded["northwind analytics"] == pf
    assert load_people_dir(tmp_path / "missing", {}) == {}


def test_mark_left():
    pf = mark_left(parse_people(FILE, "x"), "eli-park")
    assert pf.people[1].status == "left_company"
    with pytest.raises(NetworkError, match="nobody"):
        mark_left(pf, "zed")
