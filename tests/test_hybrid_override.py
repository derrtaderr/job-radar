"""Tightening the affirmative-remote override (row 64, miss 5).

The live miss, four instances: a hybrid posting reading "Tuesdays and Fridays
are remote/work from home days" fired the remote override and passed as remote.
`_REMOTE_OK` matched "work from home" and `_OFFICE_CADENCE` — which already
defeats the override document-wide — only catches "work from home Wednesdays",
where the day name arrives AFTER the phrase. Here it arrives before.

The fix is scope. The override has to describe the ROLE as remote, so the
SENTENCE carrying the remote language is checked for day names, hybrid phrasing
and in-office cadence. A rejected match does not end the walk: a posting may
describe its hybrid past in one sentence and its remote present in the next, and
the later sentence is still a true statement about the role.
"""
from pathlib import Path

from engine.radar.config import load_config
from engine.radar.rules_engine import jd_says_remote, kill_flags
from tests.fixtures import make_row, scraped_row

EXAMPLE = Path(__file__).parent.parent / "config.example"
CFG = load_config(EXAMPLE)        # commute_locations: Denver|Boulder


def _names(row, cfg=CFG):
    return [n for n, _ in kill_flags(row, cfg)]


def _rules_variant(tmp_path, rules_text):
    (tmp_path / "rules.yaml").write_text(rules_text)
    for name in ("queries", "weights", "settings"):
        (tmp_path / f"{name}.yaml").write_text((EXAMPLE / f"{name}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    return load_config(tmp_path)


def _elsewhere(description):
    """A non-remote posting in a city outside the commute allowlist — so the
    location rule fires unless the remote override rescues it. The override is
    the thing under test."""
    return make_row(is_remote=False, location="Chicago, IL", description=description)


# --- the miss -----------------------------------------------------------------

def test_day_names_before_the_remote_phrase_defeat_the_override():
    # THE four-instance miss, verbatim in shape.
    row = _elsewhere("Tuesdays and Fridays are remote/work from home days.")
    assert "location" in _names(row)


def test_a_work_from_home_day_count_defeats_the_override():
    row = _elsewhere("You will work from home 2 days a week.")
    assert "location" in _names(row)


def test_a_single_named_day_defeats_the_override():
    row = _elsewhere("Employees may work from home on Fridays.")
    assert "location" in _names(row)


def test_a_hybrid_word_in_the_same_sentence_defeats_the_override():
    row = _elsewhere("We are hybrid, and you can work from home when you like.")
    assert "location" in _names(row)


# --- what it must not break ---------------------------------------------------

def test_a_genuinely_remote_role_still_overrides_the_location():
    row = _elsewhere("This is a fully remote role, open to candidates anywhere.")
    assert "location" not in _names(row)


def test_an_office_mentioned_in_a_DIFFERENT_sentence_does_not_defeat_the_override():
    # A remote company can still have an office. Scoping the check to the
    # sentence is what keeps this posting out of the kill list.
    row = _elsewhere("This is a fully remote role. Our office is in Chicago.")
    assert "location" not in _names(row)


def test_a_rejected_match_does_not_end_the_walk():
    # The posting describes a hybrid past and a remote present. The second
    # sentence is a true statement about the role, and bailing on the first
    # rejection would throw it away.
    row = _elsewhere("Fridays used to be work from home days. The role is now "
                     "fully remote for everyone.")
    assert "location" not in _names(row)


def test_a_negated_remote_mention_still_does_not_rescue():
    row = _elsewhere("This is not a remote position.")
    assert "location" in _names(row)


# --- the live wire shape (R64-01) ---------------------------------------------

def _elsewhere_scraped(description):
    return scraped_row(is_remote=False, location="Chicago, IL", description=description)


def test_escaped_in_office_cadence_still_defeats_the_override():
    row = _elsewhere_scraped(
        r"Fully flexible. You will be in\-office 3 days a week with the team.")
    assert "location" in _names(row)


def test_an_escaped_hybrid_sentence_still_defeats_the_override():
    row = _elsewhere_scraped(
        r"We are hybrid\-first, and you can work from home on Fridays.")
    assert "location" in _names(row)


def test_an_escaped_remote_first_claim_still_overrides():
    # The other direction: the escapes must not stop a genuine remote claim from
    # being read either.
    #
    # Phrased WITHOUT the word "no", deliberately. "remote-first, with no office
    # requirement" reads as negated by the `_NEG` window, which scans to the end
    # of the sentence after a match — a pre-existing false negative in the
    # untightened override (it behaves identically on the pre-change tree),
    # unrelated to markdown escapes and not this wave's to change.
    row = _elsewhere_scraped(r"This role is remote\-first and the team is distributed.")
    assert "location" not in _names(row)


# --- config-driven ------------------------------------------------------------

def test_an_empty_hybrid_phrases_restores_the_untightened_override(tmp_path):
    cfg = _rules_variant(
        tmp_path,
        "comp_floor: 120000\ncommute_locations: 'Denver|Boulder'\n"
        "hybrid_phrases: ''\nrules: []\n")
    row = _elsewhere("Tuesdays and Fridays are remote/work from home days.")
    assert "location" not in _names(row, cfg)


def test_an_absent_hybrid_phrases_falls_back_to_the_engine_default(tmp_path):
    cfg = _rules_variant(
        tmp_path,
        "comp_floor: 120000\ncommute_locations: 'Denver|Boulder'\nrules: []\n")
    row = _elsewhere("Tuesdays and Fridays are remote/work from home days.")
    assert "location" in _names(row, cfg)


def test_the_example_config_spells_the_rule_out_and_matches_the_engine_default():
    import yaml

    from engine.radar.rules_engine import DEFAULT_HYBRID_PHRASES
    shipped = yaml.safe_load((EXAMPLE / "rules.yaml").read_text())
    assert shipped["hybrid_phrases"] == DEFAULT_HYBRID_PHRASES


def test_a_bad_hybrid_regex_names_the_key(tmp_path):
    import pytest

    from engine.radar.config import ConfigError
    with pytest.raises(ConfigError, match="hybrid_phrases"):
        _rules_variant(tmp_path, "comp_floor: 120000\nhybrid_phrases: '('\nrules: []\n")


# --- the public detector ------------------------------------------------------

def test_jd_says_remote_is_untightened_unless_a_hybrid_pattern_is_passed():
    # engine/loop/calibrate.py contrasts remote language against application
    # outcomes through this name. Tightening it by default would change what a
    # calibration report says about a season already recorded, which is a
    # different decision from tightening the kill path — so the caller opts in.
    hybrid_text = "Tuesdays and Fridays are remote/work from home days."
    assert jd_says_remote(hybrid_text) is not None
    assert jd_says_remote(hybrid_text, CFG.hybrid_pattern) is None


# --- the tightening must not over-fire (R64-05) ------------------------------
#
# The sentence-scoped rejection went too wide. Its default treated a bare
# `\d+ days?`, a bare "office" mention and a bare "on-site" as hybrid phrasing, so
# genuinely remote postings started failing the override and taking a location
# kill — postings the UNTIGHTENED override had passed. Fixing miss 5 by killing
# remote roles is a worse outcome than miss 5.
#
# The rule that separates them: an affirmative remote claim about the ROLE ("fully
# remote", "remote-first", "100% remote") in the same sentence wins over any
# hybrid or on-site token beside it. A weak mention ("work from home", "working
# remotely") does not — that is exactly the phrasing hybrid postings use when they
# list which days are which.

REMOTE_BUT_MENTIONS_AN_OFFICE = (
    "Fully remote role with 25 days of PTO and a home office stipend.",
    "This role is fully remote, with an optional desk in our office for anyone "
    "who wants one.",
    "We are remote-first; occasional on-site offsites twice a year.",
    "Fully remote. Hybrid schedules are available for those who want them.",
)


def test_a_strong_remote_claim_survives_a_hybrid_token_beside_it():
    for text in REMOTE_BUT_MENTIONS_AN_OFFICE:
        assert "location" not in _names(_elsewhere(text)), text


def test_a_strong_remote_claim_is_still_read_as_remote_language():
    for text in REMOTE_BUT_MENTIONS_AN_OFFICE:
        assert jd_says_remote(text, CFG.hybrid_pattern) is not None, text


def test_a_day_count_not_tied_to_an_office_is_not_hybrid_phrasing():
    # "25 days of PTO" is a benefit. A bare day count says nothing about where
    # the work happens.
    assert "location" not in _names(_elsewhere(
        "This is a fully remote position. We offer 25 days of paid leave."))


def test_a_weak_remote_mention_beside_a_hybrid_token_still_loses():
    # The other side of the same rule, and the case miss 5 actually was: no
    # role-scoped claim anywhere, just which days are which.
    assert "location" in _names(_elsewhere(
        "Tuesdays and Fridays are remote/work from home days."))
    assert "location" in _names(_elsewhere(
        "You will work from home 2 days a week."))


def test_a_mandatory_office_cadence_still_defeats_a_strong_claim():
    # The limit of "the strong claim wins". A posting can say "fully remote" and
    # then require three days in the office; the requirement is the real term, and
    # letting the claim win there would hand back a hybrid role as remote.
    assert "location" in _names(_elsewhere(
        "Fully remote (US). You will be in the office 3 days a week."))
    assert "location" in _names(_elsewhere(
        "This is a fully remote role. Expect to be in-office 4 days per week."))


def test_an_optional_hybrid_offer_does_not_defeat_a_strong_claim():
    # "available for those who want them" is an option, not a term of the role —
    # which is what separates it from the cadence case above.
    assert "location" not in _names(_elsewhere(
        "Fully remote. Hybrid schedules are available for those who want them."))
