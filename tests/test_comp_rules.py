from pathlib import Path

from engine.radar.config import load_config
from engine.radar.rules_engine import kill_flags, body_stated_max
from tests.fixtures import make_row

CFG = load_config(Path(__file__).parent.parent / "config.example")  # floor 120000


def _names(row):
    return [n for n, _ in kill_flags(row, CFG)]


def test_posted_max_below_floor_kills():
    assert "comp-below-floor" in _names(make_row(max_amount=110000))


def test_hourly_interval_does_not_kill():
    assert "comp-below-floor" not in _names(make_row(max_amount=60, interval="hourly"))


def test_body_stated_salary_below_floor_kills():
    row = make_row(description="Fully remote. We are targeting a salary around 95k for this role.")
    assert "comp-below-floor-stated" in _names(row)


def test_body_stated_salary_above_floor_survives():
    row = make_row(description="Fully remote. Base salary of $170,000 plus equity.")
    assert "comp-below-floor-stated" not in _names(row)


def test_posted_comp_outranks_body_mention():
    # structured field present and >= floor: a stray body number must not kill
    row = make_row(max_amount=150000,
                   description="Fully remote. Our last comp survey said the market median is 90k.")
    assert _names(row) == []


def test_body_number_without_comp_context_is_ignored():
    assert body_stated_max("we processed 125k events per second") is None


def test_body_stated_max_parses_forms():
    assert body_stated_max("targeting a salary around 125k") == 125000
    assert body_stated_max("base pay: $87,500 - $105,000 per year") == 105000
