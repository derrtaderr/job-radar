from pathlib import Path
from engine.radar.config import load_config
from engine.radar.rules_engine import kill_flags, body_location
from tests.fixtures import make_row

CFG = load_config(Path(__file__).parent.parent / "config.example")  # commute: Denver|Boulder

def _names(row):
    return [n for n, _ in kill_flags(row, CFG)]

def test_structured_location_elsewhere_kills():
    assert "location" in _names(make_row(is_remote=False, location="Chicago, IL",
                                         description="Build data pipelines."))

def test_commute_location_survives():
    assert "location" not in _names(make_row(is_remote=False, location="Denver, CO",
                                             description="Build data pipelines."))

def test_affirmative_remote_overrides_structured_location():
    assert "location" not in _names(make_row(is_remote=False, location="Chicago, IL",
                                             description="This is a fully remote role."))

def test_negated_remote_does_not_rescue():
    assert "location" in _names(make_row(is_remote=False, location="Chicago, IL",
                                         description="This is not a remote position."))

def test_body_stated_city_kills_when_fields_empty():
    row = make_row(is_remote=False, location="",
                   description="We are hiring a platform engineer based in San Francisco.")
    assert "location" in _names(row)

def test_in_office_cadence_defeats_remote_override():
    row = make_row(is_remote=False, location="",
                   description="Work from home Wednesdays; otherwise 4 days a week in our SF office.")
    assert "location" in _names(row)

def test_empty_everything_survives_unknown_is_not_onsite():
    assert "location" not in _names(make_row(is_remote=False, location="",
                                             description="Build data pipelines."))

def test_body_location_parses():
    assert body_location("the role is based in San Francisco.") == "San Francisco"
    assert body_location("our office in Austin is home base") == "Austin"
    assert body_location("we ship data based in reality") is None
