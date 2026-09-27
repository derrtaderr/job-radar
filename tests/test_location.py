"""Location normalisation — one spelling, one answer (row 64, miss 3).

The live miss: the location rule resolved "New York, United States" two ways on
the same day. The mechanism is a commute allowlist matched as a bare substring
against whatever spelling the board happened to use, and a pattern of `NY` finds
"ny" inside "Pennsylvania" while missing "New York, United States" entirely. So
one place passed and the same place was killed, in one run.

The fix is to normalise first and match on word boundaries within the normalised
parts. These tests pin both halves: the normaliser's canonical form, and the two
cases that used to disagree.
"""
import dataclasses
import re
from pathlib import Path

from engine.radar.config import load_config
from engine.radar.location import normalise_location, pattern_matches_location
from engine.radar.rules_engine import kill_flags
from tests.fixtures import make_row

CFG = load_config(Path(__file__).parent.parent / "config.example")


def _names(row, cfg=CFG):
    return [n for n, _ in kill_flags(row, cfg)]


# --- the canonical form -------------------------------------------------------

def test_one_place_written_four_ways_normalises_one_way():
    assert (normalise_location("New York, United States")
            == normalise_location("New York, NY")
            == normalise_location("New York")
            == normalise_location("NY")
            == "ny")


def test_a_city_keeps_its_name_and_its_state_becomes_an_abbreviation():
    assert normalise_location("Denver, Colorado") == "denver, co"
    assert normalise_location("Denver, CO") == "denver, co"


def test_whitespace_case_and_a_country_suffix_are_flattened():
    assert normalise_location("  BOULDER ,   Colorado , United States ") == "boulder, co"
    assert normalise_location("Austin, TX, USA") == "austin, tx"


def test_an_absent_location_normalises_to_empty():
    assert normalise_location("") == ""
    assert normalise_location(None) == ""


def test_a_remote_marker_survives_normalisation():
    # "Remote" is not a place, and normalisation must not quietly delete the one
    # token that says a posting has no place at all.
    assert normalise_location("Remote, United States") == "remote"


# --- the commute match --------------------------------------------------------

def test_a_commute_pattern_matches_its_city():
    pattern = re.compile("Denver|Boulder", re.I)
    assert pattern_matches_location(pattern, "Denver, CO")
    assert pattern_matches_location(pattern, "Boulder, Colorado")


def test_a_commute_pattern_matches_a_city_inside_a_longer_part():
    # "Denver Tech Center, CO" is Denver. An exact full-match on the part would
    # have broken this, which is why the rule is word boundaries, not equality.
    pattern = re.compile("Denver", re.I)
    assert pattern_matches_location(pattern, "Denver Tech Center, CO")


def test_a_two_letter_pattern_does_not_match_the_middle_of_a_state_name():
    # THE miss. `NY` substring-matches Pennsylvania (...syl-va-nia) and a bare
    # substring search let a Philadelphia req through a New York allowlist.
    pattern = re.compile("NY", re.I)
    assert not pattern_matches_location(pattern, "Pennsylvania, United States")
    assert not pattern_matches_location(pattern, "Albany, New Hampshire")


def test_a_two_letter_pattern_matches_the_state_it_names_however_it_is_spelled():
    # The other half of the same miss: the spelling the board actually used
    # missed the allowlist entirely.
    pattern = re.compile("NY", re.I)
    assert pattern_matches_location(pattern, "New York, United States")
    assert pattern_matches_location(pattern, "New York, NY")
    assert pattern_matches_location(pattern, "NY")


def test_no_commute_pattern_matches_nothing():
    assert not pattern_matches_location(None, "Denver, CO")


# --- through the kill rule ----------------------------------------------------

def _ny_cfg():
    return dataclasses.replace(CFG, commute_pattern=re.compile("NY", re.I))


def test_the_same_place_spelled_two_ways_gets_one_verdict():
    # Both rows are the allowlisted place. Before normalisation one passed and
    # one was killed, in the same run.
    cfg = _ny_cfg()
    for spelling in ("New York, United States", "New York, NY", "NY"):
        row = make_row(is_remote=False, location=spelling,
                       description="Build data pipelines.")
        assert "location" not in _names(row, cfg), spelling


def test_a_place_that_merely_contains_the_pattern_is_still_killed():
    cfg = _ny_cfg()
    row = make_row(is_remote=False, location="Pennsylvania, United States",
                   description="Build data pipelines.")
    assert "location" in _names(row, cfg)


def test_the_shipped_commute_allowlist_still_behaves(cfg=CFG):
    # config.example's Denver|Boulder, unchanged by normalisation.
    assert "location" not in _names(
        make_row(is_remote=False, location="Denver, Colorado",
                 description="Build data pipelines."))
    assert "location" in _names(
        make_row(is_remote=False, location="Chicago, IL",
                 description="Build data pipelines."))


# --- the allowlist is normalised too (R64-04) --------------------------------
#
# Normalising only the LOCATION broke the other side. A commute allowlist written
# as a full state name — "Colorado" — used to substring-match "Denver, Colorado"
# and stopped matching once the location normalised to `denver, co`. That silently
# turned a commutable city into a location kill for anyone whose config named a
# state rather than a city, which is a regression the row introduced rather than a
# miss it set out to fix.
#
# So the allowlist's own entries go through `normalise_location` before matching,
# and all three shapes a person actually writes have to keep working.

def test_an_allowlist_written_as_a_full_state_name_matches_that_state():
    pattern = re.compile("Colorado", re.I)
    assert pattern_matches_location(pattern, "Denver, Colorado")
    assert pattern_matches_location(pattern, "Denver, CO")
    assert pattern_matches_location(pattern, "Boulder, Colorado, United States")


def test_an_allowlist_written_as_an_abbreviation_still_matches():
    pattern = re.compile("CO", re.I)
    assert pattern_matches_location(pattern, "Denver, CO")
    assert pattern_matches_location(pattern, "Denver, Colorado")


def test_an_allowlist_written_as_a_city_still_matches():
    pattern = re.compile("Denver|Boulder", re.I)
    assert pattern_matches_location(pattern, "Denver, CO")
    assert pattern_matches_location(pattern, "Boulder, Colorado")
    assert not pattern_matches_location(pattern, "Chicago, IL")


def test_a_multi_word_state_name_in_an_allowlist_matches():
    pattern = re.compile("New Jersey", re.I)
    assert pattern_matches_location(pattern, "Newark, New Jersey")
    assert pattern_matches_location(pattern, "Newark, NJ")


def test_an_alternation_mixing_a_city_and_a_state_name_matches_both():
    pattern = re.compile("Denver|Colorado", re.I)
    assert pattern_matches_location(pattern, "Denver, CO")
    assert pattern_matches_location(pattern, "Fort Collins, Colorado")
    assert not pattern_matches_location(pattern, "Chicago, IL")


def test_normalising_the_allowlist_does_not_reopen_the_substring_bug():
    # The whole point of R64-03's fix. `NY` must still not match Pennsylvania.
    pattern = re.compile("NY", re.I)
    assert pattern_matches_location(pattern, "New York, United States")
    assert not pattern_matches_location(pattern, "Pennsylvania, United States")


def test_a_pattern_using_real_regex_syntax_is_left_alone():
    # A pattern with metacharacters cannot be split into entries and normalised
    # without changing what it means, so it is matched as written. Naming the
    # limit beats silently mangling someone's regex.
    pattern = re.compile(r"Denver|Bould\w+", re.I)
    assert pattern_matches_location(pattern, "Boulder, CO")
    assert pattern_matches_location(pattern, "Denver, CO")


def test_a_full_state_name_allowlist_no_longer_kills_a_city_in_that_state():
    cfg = dataclasses.replace(CFG, commute_pattern=re.compile("Colorado", re.I))
    for spelling in ("Denver, Colorado", "Denver, CO", "Boulder, Colorado"):
        row = make_row(is_remote=False, location=spelling,
                       description="Build data pipelines.")
        assert "location" not in _names(row, cfg), spelling
