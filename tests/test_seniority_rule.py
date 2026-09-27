"""The years-of-experience band, read at both ends (row 64, miss 6).

The live miss: a req reading "1-4 years of relevant experience, early in their
career" placed SECOND in the queue. Nothing in the engine read seniority out of a
body, so a junior req with a senior-sounding title and a good comp band scored
like a senior one.

A penalty, not a kill, and the reason is evidence quality. A band is a weak claim
about a req — boards and recruiters mislabel seniority constantly, and the
complaint here was ranking, not visibility. A kill would answer a ranking problem
by hiding the posting, which is the failure mode this whole row exists to close.

The upper end gets a flag and no penalty at all: "10+ years" is a stretch worth
knowing about before you spend an application hour, not a reason to drop it.
"""
import datetime
from pathlib import Path

from engine.radar.config import load_config
from engine.radar.rules_engine import kill_flags, score, seniority_notes
from tests.fixtures import make_row

EXAMPLE = Path(__file__).parent.parent / "config.example"
CFG = load_config(EXAMPLE)        # seniority: min_years 5, penalty 15, stretch 10
TODAY = datetime.date(2026, 9, 13)

CLEAN = "Own the ingestion layer that feeds our reporting marts."


def _notes(description, cfg=CFG):
    return dict(seniority_notes(make_row(description=description), cfg))


def _rules_variant(tmp_path, rules_text):
    (tmp_path / "rules.yaml").write_text(rules_text)
    for name in ("queries", "weights", "settings"):
        (tmp_path / f"{name}.yaml").write_text((EXAMPLE / f"{name}.yaml").read_text())
    (tmp_path / "exclusions.txt").write_text("")
    return load_config(tmp_path)


# --- the floor ----------------------------------------------------------------

def test_a_band_starting_below_the_floor_is_flagged():
    # THE miss, verbatim.
    notes = _notes(CLEAN + " We want 1-4 years of relevant experience.")
    assert "junior-band" in notes


def test_the_flag_quotes_the_line_that_matched():
    notes = _notes(CLEAN + " We want 1-4 years of relevant experience.")
    assert "1-4 years" in notes["junior-band"]


def test_every_way_a_posting_says_early_career_is_flagged():
    for phrase in ("We want 0-3 years of experience.",
                   "Ideal for someone early in their career.",
                   "This is an entry level position.",
                   "This is an entry-level role.",
                   "Open to new grad candidates.",
                   "We welcome recent graduates.",
                   "2 to 4 years of experience required."):
        assert "junior-band" in _notes(CLEAN + " " + phrase), phrase


def test_a_band_at_or_above_the_floor_is_not_flagged():
    for phrase in ("5-8 years of experience required.",
                   "7+ years of experience required.",
                   "At least 6 years of experience.",
                   "Minimum of 5 years of experience."):
        assert "junior-band" not in _notes(CLEAN + " " + phrase), phrase


def test_a_posting_that_says_nothing_about_years_is_not_flagged():
    assert _notes(CLEAN) == {}


# --- the stretch --------------------------------------------------------------

def test_a_band_at_the_stretch_threshold_is_flagged_as_a_stretch():
    notes = _notes(CLEAN + " We are looking for 10+ years of experience.")
    assert "seniority-stretch" in notes
    assert "10+ years" in notes["seniority-stretch"]


def test_a_stretch_is_not_a_junior_band():
    assert "junior-band" not in _notes(CLEAN + " 12+ years of experience required.")


# --- neither end is ever a kill ----------------------------------------------

def test_neither_end_of_the_band_ever_kills():
    junior = make_row(description=CLEAN + " 1-4 years of relevant experience.")
    stretch = make_row(description=CLEAN + " 15+ years of experience required.")
    assert [n for n, _ in kill_flags(junior, CFG)] == []
    assert [n for n, _ in kill_flags(stretch, CFG)] == []


# --- the score ----------------------------------------------------------------

def test_a_junior_band_costs_the_configured_penalty():
    clean = make_row(description=CLEAN)
    junior = make_row(description=CLEAN + " 1-4 years of relevant experience.")
    assert score(clean, TODAY, CFG) - score(junior, TODAY, CFG) == CFG.seniority["penalty"]


def test_a_junior_band_ranks_below_an_otherwise_identical_posting():
    # The miss was a ranking failure, so this is the assertion that matters.
    clean = make_row(description=CLEAN)
    junior = make_row(description=CLEAN + " Ideal for someone early in their career.")
    assert score(junior, TODAY, CFG) < score(clean, TODAY, CFG)


def test_a_stretch_costs_nothing():
    clean = make_row(description=CLEAN)
    stretch = make_row(description=CLEAN + " 10+ years of experience required.")
    assert score(stretch, TODAY, CFG) == score(clean, TODAY, CFG)


# --- config-driven ------------------------------------------------------------

def test_no_seniority_config_means_no_flag_and_no_penalty(tmp_path):
    # A seniority floor is a personal preference, like comp_floor — not generic
    # bug-fix machinery. So absent means OFF, and there is no engine default to
    # invent one for a user who never stated one.
    cfg = _rules_variant(tmp_path, "comp_floor: 120000\nrules: []\n")
    assert cfg.seniority is None
    row = make_row(description=CLEAN + " 1-4 years of relevant experience.")
    assert seniority_notes(row, cfg) == []
    assert score(row, TODAY, cfg) == score(make_row(description=CLEAN), TODAY, cfg)


def test_the_floor_and_the_penalty_come_from_config(tmp_path):
    cfg = _rules_variant(
        tmp_path,
        "comp_floor: 120000\nseniority: {min_years: 9, penalty: 40, stretch_years: 20}\n"
        "rules: []\n")
    # 7+ years clears the shipped floor of 5 but not a floor of 9.
    row = make_row(description=CLEAN + " 7+ years of experience required.")
    assert "junior-band" in dict(seniority_notes(row, cfg))
    assert score(make_row(description=CLEAN), TODAY, cfg) - score(row, TODAY, cfg) == 40
    # ...and a 10-year band is no longer a stretch at stretch_years 20.
    stretch = make_row(description=CLEAN + " 10+ years of experience required.")
    assert "seniority-stretch" not in dict(seniority_notes(stretch, cfg))


def test_the_example_config_ships_a_seniority_instance():
    assert CFG.seniority == {"min_years": 5, "penalty": 15, "stretch_years": 10}


def test_a_non_integer_seniority_value_names_the_key(tmp_path):
    import pytest

    from engine.radar.config import ConfigError
    with pytest.raises(ConfigError, match="min_years"):
        _rules_variant(
            tmp_path,
            "comp_floor: 120000\nseniority: {min_years: yes, penalty: 15, "
            "stretch_years: 10}\nrules: []\n")


# --- years that are not experience (R64-07) ----------------------------------
#
# The band's last alternation matched a bare `\d+ years?`, so it read any number
# of years in a posting as a stated floor. On realistic bodies that meant a 401(k)
# vesting schedule, a company's founding date, a growth anecdote and a sabbatical
# policy each cost a posting 15 points. A rule that fires on a benefits paragraph
# is not a seniority rule.
#
# The fix is to require an experience context around the number. "3 years focused
# on HubSpot" is a sub-skill floor and not the role's requirement; "7+ years in GTM
# engineering" is.

NOT_EXPERIENCE = (
    "401(k) match vests after 1 year of service.",
    "Founded 12 years ago, we now serve 300 customers.",
    "Over the past 2 years our team grew 3x.",
    "We offer 20 days PTO and a 1 year sabbatical after 5 years.",
    "Our Series B closed 4 years ago.",
    "This role reports to a director with 2 direct reports.",
)


def test_a_year_that_is_not_experience_is_not_a_floor():
    for text in NOT_EXPERIENCE:
        assert _notes(CLEAN + " " + text) == {}, text


def test_a_year_that_is_not_experience_costs_no_points():
    clean = make_row(description=CLEAN)
    for text in NOT_EXPERIENCE:
        row = make_row(description=CLEAN + " " + text)
        assert score(row, TODAY, CFG) == score(clean, TODAY, CFG), text


def test_a_founding_date_is_not_a_seniority_stretch():
    # It used to flag `seniority-stretch` off "Founded 12 years ago".
    assert "seniority-stretch" not in _notes(
        CLEAN + " Founded 12 years ago, we now serve 300 customers.")


def test_a_sub_skill_floor_does_not_set_the_role_band():
    # The real posting: 3 years on one tool, 7+ overall. The ROLE is a 7-year role.
    notes = _notes(CLEAN + " Requires at least 3 years focused on HubSpot and "
                           "7+ years in GTM engineering overall.")
    assert "junior-band" not in notes


def test_the_largest_stated_floor_is_the_role_band():
    # Two bands that both carry an experience context: the larger is the role's
    # requirement and the smaller is a requirement for one skill inside it.
    notes = _notes(CLEAN + " You have 2 years of experience with dbt and 8+ years "
                           "of experience in data engineering.")
    assert "junior-band" not in notes


def test_the_experience_contexts_a_posting_actually_writes_are_all_read():
    for text, junior in (
        ("We want 1-4 years of relevant experience.", True),
        ("2-4 years' experience required.", True),
        ("3 years in a similar role.", True),
        ("2 years working on production pipelines.", True),
        ("Experience: 1+ years.", True),
        ("8+ years of experience required.", False),
        ("At least 6 years of professional experience.", False),
        ("7 years in data engineering.", False),
    ):
        notes = _notes(CLEAN + " " + text)
        assert ("junior-band" in notes) is junior, (text, notes)


def test_a_phrase_floor_still_flags_on_its_own():
    # "early in their career" states a floor without stating a number, so it must
    # not depend on the numeric path at all.
    assert "junior-band" in _notes(CLEAN + " Ideal for someone early in their career.")
    assert "junior-band" in _notes(
        CLEAN + " Founded 12 years ago. This is an entry level role.")
