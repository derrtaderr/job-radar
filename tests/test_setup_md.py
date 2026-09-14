"""SETUP.md is the file a stranger follows with their hands on the keyboard, and
two of its claims are about behavior that fails SILENTLY when the doc is wrong.

A doc that is merely unclear costs a reader a minute. These cost more than that,
which is why they get pins:

- **The tracker's two heading matchers.** The validator strips a trailing
  parenthetical; the radar's suppression readers do not — they match the full
  lowercased heading text. So `## Active (in play)` with
  `tracker_active_sections: [active]` suppresses nothing while the doctor stays
  green, and `## Closed (done)` is never read at all. A doc that attributes the
  validator's leniency to the radar teaches a heading style that quietly turns
  suppression off.
- **The close date is read positionally.** `closed_recent_companies` takes the
  third data cell, not the cell under the `Date closed` header, so an extra
  column inserted ahead of it moves the read onto the wrong cell — and
  `tracker_check` still passes, because the required header is still there.
  "Extra columns anywhere are fine" is true of the validator and false of the
  radar.

Everything else here pins strings the doc QUOTES from code. Where the string is
an importable constant it is imported; where it is a literal raised from a
function, the test calls the function and reads the message back rather than
re-typing it (the same principle the ats_check/verify_pdf constants follow). A
troubleshooting section keyed to strings nobody ever printed is worse than no
troubleshooting section, because it sends a reader searching for text their
terminal will never show.

Pinning prose is a tradeoff: rewording these lines becomes a deliberate two-file
edit. That is the point. The rest of SETUP.md is free to change.
"""
from pathlib import Path

from engine.profile_schema import CLAIM_LEDGER_LINE, check_profile
from engine.radar.config import REQUIRED_FILES
from tools.doctor import _CONFIG_FIX, _HOOKS_PATH_FIX, _VENV_FIX

SETUP_MD = Path(__file__).resolve().parent.parent / "SETUP.md"

AFTER_COPY_MARKER = "<!-- doctor-after-copy -->"


def _doc() -> str:
    return SETUP_MD.read_text()


def _prose() -> str:
    """The doc with every run of whitespace collapsed to one space, so a pinned
    sentence survives being re-wrapped at a different column."""
    return " ".join(_doc().split())


def test_setup_md_exists():
    assert SETUP_MD.is_file()


# --- the two silent-failure corrections ---------------------------------------

def test_radar_readers_match_the_full_heading_text():
    # engine/radar/tracker.py: `section = line[3:].strip().lower()`. No
    # parenthetical stripping anywhere in that path.
    prose = _prose()
    assert "match the full lowercased heading text" in prose
    assert "`## Active (in play)` with `tracker_active_sections: [active]`" in prose


def test_parenthetical_stripping_is_named_as_the_validators_behavior_only():
    assert "`## Closed (done)` is never read, exactly like `## Archive`" in _prose()


def test_extra_columns_are_qualified_for_the_closed_section():
    # closed_recent_companies reads cells[3]. An extra column ahead of
    # `Date closed` shifts the read with tracker_check still green.
    prose = _prose()
    assert "Extra columns are fine everywhere **except before `Date closed` in Closed**" in prose
    assert "**by position**, not by header name" in prose


# --- strings the doc quotes from code -----------------------------------------

def test_claim_ledger_line_is_quoted_verbatim():
    assert CLAIM_LEDGER_LINE in _doc()


def test_both_frontmatter_fence_failures_are_documented():
    # Read the messages off the schema itself rather than re-typing them.
    opening = check_profile("nope")[0]
    unclosed = check_profile("---\nname: Someone\n")[0]
    assert opening in _doc(), opening
    assert unclosed in _doc(), unclosed


def test_doctor_fix_commands_are_quoted_verbatim():
    doc = _doc()
    for fix in (_CONFIG_FIX, _HOOKS_PATH_FIX, _VENV_FIX):
        assert fix in doc, fix


# --- counts and samples --------------------------------------------------------

def test_the_config_file_count_matches_the_loader():
    # Four YAML files plus exclusions.txt are what load_config requires;
    # profile.md is the sixth file a user fills in.
    assert len(REQUIRED_FILES) + 1 == 6
    assert "six files in `config/`" in _prose()


def test_the_after_copy_doctor_sample_carries_no_fail():
    # The walkthrough copies config.example BEFORE running the doctor, so the
    # sample output a reader compares against must not show a config FAIL they
    # will never see. Marked so this reads the right block as the doc grows.
    doc = _doc()
    assert AFTER_COPY_MARKER in doc
    block = doc.split(AFTER_COPY_MARKER, 1)[1].split("```")[1]
    assert "FAIL" not in block, block
