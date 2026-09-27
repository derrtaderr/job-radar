"""The negative body override (row 64, miss 4).

The live miss: a posting whose body read "This is a fully on-site position" did
not kill, because the header location passed and the engine only ever read the
body to find a city or to find affirmative REMOTE language. The body could say
the opposite of the header and nothing looked.

This is the mirror of `_jd_says_remote`: body language that describes the role as
on-site, killing as `onsite-body` with the matched line quoted, even when the
header says `is_remote`. A body that contradicts its own header is a real class,
and the scraper's boolean is the less reliable of the two.

The one thing it must not override is the commute allowlist. An on-site role in a
city the user can actually commute to is a role they want.
"""
import dataclasses
from pathlib import Path

from engine.radar.config import load_config
from engine.radar.rules_engine import kill_flags
from tests.fixtures import make_row, scraped_row

EXAMPLE = Path(__file__).parent.parent / "config.example"
CFG = load_config(EXAMPLE)        # commute_locations: Denver|Boulder


def _flags(row, cfg=CFG):
    return dict(kill_flags(row, cfg))


def _rules_variant(tmp_path, rules_text):
    """A config directory identical to config.example but for rules.yaml."""
    (tmp_path / "rules.yaml").write_text(rules_text)
    for name in ("queries", "weights", "settings"):
        (tmp_path / f"{name}.yaml").write_text((EXAMPLE / f"{name}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    (tmp_path / "profile.md").write_text((EXAMPLE / "profile.md").read_text())
    return load_config(tmp_path)


# --- the miss -----------------------------------------------------------------

def test_a_body_saying_fully_on_site_kills_even_with_no_header_location():
    row = make_row(is_remote=True, location="",
                   description="Own the platform. This is a fully on-site position.")
    assert "onsite-body" in _flags(row)


def test_the_kill_quotes_the_line_that_matched():
    # Same honesty floor as every other kill in this repo: a flag nobody can
    # check is a flag nobody can overrule.
    row = make_row(is_remote=True, location="",
                   description="Own the platform. This is a fully on-site position.")
    assert "fully on-site" in _flags(row)["onsite-body"]


def test_an_in_office_day_count_in_the_body_kills():
    for phrase in ("You will be in office 4 days per week.",
                   "We are in the office 3 days a week as a team.",
                   "This is an on-site role at our headquarters.",
                   "The team is 100% on-site."):
        row = make_row(is_remote=True, location="", description="Own it. " + phrase)
        assert "onsite-body" in _flags(row), phrase


def test_a_hyphenless_spelling_still_kills():
    row = make_row(is_remote=True, location="",
                   description="Own the platform. This is a fully onsite position.")
    assert "onsite-body" in _flags(row)


# --- the live wire shape (R64-01) ---------------------------------------------

def test_the_rule_fires_on_the_shape_a_live_scrape_actually_delivers():
    # THE blocker. A live LinkedIn scrape delivers markdown with escaped
    # punctuation, so the body reads "a fully on\-site position" and every
    # hyphen-bearing pattern in the kill path missed it. The rule returned no
    # flags on real data while passing every prose fixture in this file.
    row = scraped_row(is_remote=True, location="",
                      description=r"Own the platform. This is a fully on\-site position.")
    assert "onsite-body" in _flags(row)


def test_an_escaped_in_office_day_count_still_kills():
    row = scraped_row(is_remote=True, location="",
                      description=r"Own it. You will be in\-office 4 days per week.")
    assert "onsite-body" in _flags(row)


def test_an_escaped_comp_band_still_reads_as_a_band():
    # The same escapes reach the comp rule: "$95,000 \- $110,000".
    row = scraped_row(is_remote=True, location="", max_amount=None, min_amount=None,
                      description=r"Salary range for this role is $95,000 \- $110,000.")
    assert "comp-below-floor-stated" in _flags(row)


# --- what it must not do ------------------------------------------------------

def test_a_negated_mention_does_not_kill():
    row = make_row(is_remote=True, location="",
                   description="Own the platform. This is not an on-site position.")
    assert "onsite-body" not in _flags(row)


def test_the_commute_allowlist_beats_the_on_site_rule():
    # An on-site role in a city on the allowlist is a role the user wants. This
    # is the path config.example's own demo-4 posting takes.
    row = make_row(is_remote=False, location="Denver, CO",
                   description="This is a fully on-site position, based out of our "
                               "Denver office.")
    # The phrase itself must be one the rule DOES match, or this test proves
    # nothing about precedence.
    assert CFG.onsite_pattern.search(row["description"])
    assert "onsite-body" not in _flags(row)


def test_a_body_location_on_the_allowlist_also_beats_the_rule():
    row = make_row(is_remote=False, location="",
                   description="Our office in Boulder is home base; this is a fully "
                               "on-site position.")
    assert "onsite-body" not in _flags(row)


def test_a_silent_body_does_not_kill():
    row = make_row(is_remote=True, location="", description="Build data pipelines.")
    assert "onsite-body" not in _flags(row)


def test_a_remote_body_does_not_kill():
    row = make_row(is_remote=True, location="",
                   description="This is a fully remote role, open to anyone in the US.")
    assert "onsite-body" not in _flags(row)


# --- config-driven ------------------------------------------------------------

def test_an_empty_onsite_phrases_turns_the_rule_off(tmp_path):
    # Same opt-out shape as `commute_locations: ''`.
    cfg = _rules_variant(tmp_path, "comp_floor: 120000\nonsite_phrases: ''\nrules: []\n")
    row = make_row(is_remote=True, location="",
                   description="Own the platform. This is a fully on-site position.")
    assert "onsite-body" not in _flags(row, cfg)


def test_an_absent_onsite_phrases_falls_back_to_the_engine_default(tmp_path):
    # An existing config written before this rule existed still gets the fix.
    # The key is how you TUNE the rule, not how you switch it on.
    cfg = _rules_variant(tmp_path, "comp_floor: 120000\nrules: []\n")
    row = make_row(is_remote=True, location="",
                   description="Own the platform. This is a fully on-site position.")
    assert "onsite-body" in _flags(row, cfg)


def test_a_custom_onsite_phrase_is_honored(tmp_path):
    cfg = _rules_variant(
        tmp_path,
        "comp_floor: 120000\nonsite_phrases: 'badge in daily'\nrules: []\n")
    row = make_row(is_remote=True, location="",
                   description="You will badge in daily at our campus.")
    assert "onsite-body" in _flags(row, cfg)
    # ...and the default phrases are replaced, not merged, so the key means
    # exactly what it says.
    other = make_row(is_remote=True, location="",
                     description="This is a fully on-site position.")
    assert "onsite-body" not in _flags(other, cfg)


def test_the_shipped_example_config_carries_a_working_instance():
    assert CFG.onsite_pattern is not None
    assert CFG.onsite_pattern.search("This is a fully on-site position.")


def test_the_example_config_spells_the_rule_out_and_matches_the_engine_default():
    # config.example is a complete, working config a stranger reads to learn the
    # shape of each file, and `cp -r config.example config` is what they then
    # edit. A rule left to an invisible engine default is a rule they cannot
    # find to tune. Pinned equal to the default rather than re-typed softer, so
    # copying the example can never give you a WEAKER rule than not copying it.
    import yaml

    from engine.radar.rules_engine import DEFAULT_ONSITE_PHRASES
    shipped = yaml.safe_load((EXAMPLE / "rules.yaml").read_text())
    assert shipped["onsite_phrases"] == DEFAULT_ONSITE_PHRASES


def test_a_bad_onsite_regex_names_the_key(tmp_path):
    import pytest

    from engine.radar.config import ConfigError
    with pytest.raises(ConfigError, match="onsite_phrases"):
        _rules_variant(tmp_path, "comp_floor: 120000\nonsite_phrases: '('\nrules: []\n")


# --- the on-site rule must not over-fire (R64-06) ----------------------------
#
# The default matched `on-?site (?:position|role|...)` anywhere in the body, so a
# posting OFFERING remote as one of several options was killed as an on-site role.
# A posting that says "remote, hybrid, or on-site" is not describing an on-site
# role; it is describing a choice, and the choice includes what the reader wants.

def test_a_list_of_options_including_remote_is_not_an_on_site_role():
    for text in ("We offer remote, hybrid, or on-site positions depending on "
                 "your preference.",
                 "Candidates may choose an on-site role in Denver or fully remote.",
                 "This can be an on-site position or fully remote, your call."):
        row = make_row(is_remote=True, location="", description=text)
        assert "onsite-body" not in _flags(row), text


def test_a_same_sentence_remote_denial_suppresses_the_kill_a_known_limitation():
    # Pinned as the behavior it is, not as the behavior anyone wanted.
    #
    # "This role is not remote; it is a fully on-site position" does NOT kill, and
    # the cause is upstream of this rule: `_NEG` scans a fixed 30-character window
    # before a match and to the end of the sentence after it, and it cannot tell
    # which phrase the "not" attaches to. Here the "not" belongs to "remote" and
    # the window reads it as negating "on-site". The same window behaves the same
    # way for the remote override and has since Phase 1.
    #
    # Left alone deliberately: widening or clause-splitting `_NEG` changes how
    # every kill in this engine reads a negation, which is not a change to make
    # inside a scoped fix wave. The failure direction is safe — a posting stays in
    # the queue — and the row is still in front of the human.
    row = make_row(is_remote=True, location="",
                   description="This role is not remote; it is a fully on-site position.")
    assert "onsite-body" not in _flags(row)


def test_a_definite_on_site_role_kills_when_the_denial_is_its_own_sentence():
    # The same posting, punctuated so the windows do not collide. This is the
    # discriminator that matters: a denial of remote is not an offer of remote.
    row = make_row(is_remote=True, location="",
                   description="Remote work is not something we offer here. "
                               "This is a fully on-site position.")
    assert "onsite-body" in _flags(row)


def test_a_remote_mention_in_a_different_sentence_does_not_rescue_it():
    row = make_row(is_remote=True, location="",
                   description="We have remote roles on other teams. This one is "
                               "a fully on-site position.")
    assert "onsite-body" in _flags(row)
