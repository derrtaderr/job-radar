from pathlib import Path
from engine.radar.config import load_config
from engine.radar.rules_engine import kill_flags, body_location
from tests.fixtures import make_row, scraped_row

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


def test_body_location_verb_is_case_insensitive_at_sentence_start():
    # "Based in Chicago, IL." (sentence-initial capital) must match just like
    # "based in Chicago" does — but the city capture itself stays
    # case-sensitive, so a lowercase non-city word after the verb still can't
    # produce a false match.
    assert body_location("Based in San Francisco.") == "San Francisco"
    assert body_location("we ship data based in reality") is None


def test_sentence_initial_based_kills_location():
    row = make_row(is_remote=False, location="", description="Based in Chicago, IL.")
    assert "location" in _names(row)


# --- jd_says_remote: the public name over the same detector -----------------
# engine/loop/calibrate.py contrasts remote language against outcomes and needs
# this detector. Importing a private name across packages makes a refactor of
# rules_engine silently break the calibrator, so the behavior gets a public
# name here rather than an underscore import there.

def test_jd_says_remote_is_public_and_returns_evidence():
    from engine.radar.rules_engine import jd_says_remote
    assert "fully remote" in jd_says_remote("This is a fully remote position.")


def test_jd_says_remote_skips_negated_mentions():
    from engine.radar.rules_engine import jd_says_remote
    assert jd_says_remote("This is not a remote position.") is None


def test_jd_says_remote_on_silent_jd():
    from engine.radar.rules_engine import jd_says_remote
    assert jd_says_remote("We build data pipelines in Denver.") is None


# --- the live wire shape (row 64 fix wave, R64-01) ---------------------------
# A live scrape delivers markdown, so every hyphen-bearing pattern here — the
# remote override's `remote[- ]first` / `remote[- ]eligible` included — sees
# `remote\-first` on real data unless the boundary unescapes it.

def test_escaped_remote_first_overrides_a_structured_location():
    row = scraped_row(is_remote=False, location="Chicago, IL",
                      description=r"We are remote\-first and always have been.")
    assert "location" not in _names(row)


def test_escaped_remote_eligible_overrides_a_structured_location():
    row = scraped_row(is_remote=False, location="Chicago, IL",
                      description=r"This role is remote\-eligible across the US.")
    assert "location" not in _names(row)


def test_an_escaped_negated_remote_mention_still_does_not_rescue():
    row = scraped_row(is_remote=False, location="Chicago, IL",
                      description=r"This is not a remote\-first company.")
    assert "location" in _names(row)
