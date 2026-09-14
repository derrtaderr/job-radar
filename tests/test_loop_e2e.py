"""End-to-end pin for the loop the docs describe: `/outcome` and `/followup`
walked as code, not prose, plus one real-shape import pin and one subprocess
pin of the CLI surface itself.

Every module exercised here already has its own unit suite (test_archive.py,
test_followup.py, test_tracker_schema.py, test_tracker_mutations.py,
test_calibrate.py). This file's job is different: prove the CHAIN those
modules describe in `.claude/commands/outcome.md` and `.claude/commands/
followup.md` actually composes — that what `move_row` writes is what
`tracker_check` still accepts, that what `archive_application` returns is
what `bump_followup` and `stale_active` read, that a season built the real
way (`tests/fixtures_season.py`) still produces the report's pinned
proposals. If any one of those seams drifted, a unit test on either side of
it could still pass while the chain silently broke.

`TestLoopChain`'s methods are stages of ONE synthetic search, not
independent tests — each reads the tracker/archive state the previous stage
left on disk under a class-scoped tmp_path. They run in file-definition
order, which is pytest's default here (no random-order plugin is installed;
see requirements-dev.txt) and is what "test_01", "test_02", ... make explicit
regardless. A later stage failing on its own does not mean the seam it
depends on is broken — check the earlier stage first.

Company, role, and JD text throughout this file are entirely fictional.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from engine.loop import tracker_edit
from engine.loop.archive import (
    FollowupCapError,
    archive_application,
    bump_followup,
    read_outcome,
)
from engine.loop.calibrate import calibration_report
from engine.loop.followup import stale_active
from engine.loop.tracker_schema import parse_tracker, tracker_check
from tests.fixtures_season import build_season

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "tools" / "tracker_cli.py"

_STARTING_TRACKER = (
    "## Active\n\n"
    "| Company | Role | Source | Stage | Comp band | Last touch | Next step | Notes |\n"
    "|---|---|---|---|---|---|---|---|\n"
    "\n"
    "## Drafted but not applied\n\n"
    "| Company | Role | Source | Comp band | Resume | Next step | Notes |\n"
    "|---|---|---|---|---|---|---|\n"
    "\n"
    "## Research (JD filed, no work started)\n\n"
    "| Company | Role | Comp band | Lean | Notes |\n"
    "|---|---|---|---|---|\n"
    "\n"
    "## Closed\n\n"
    "| Company | Role | Date closed | Outcome | Reason | Carry-forward lesson |\n"
    "|---|---|---|---|---|---|\n"
)


@pytest.fixture(scope="class")
def loop_dir(tmp_path_factory):
    """One tmp_path shared across every stage in TestLoopChain, so the
    tracker file and the archive tree accumulate the same way they would
    across a real /outcome and /followup session."""
    return tmp_path_factory.mktemp("loop-e2e")


class TestLoopChain:
    """check -> add (Drafted) -> archive_application -> move to Active ->
    touch -> stale finds it -> bump_followup x2 then cap -> move two rows to
    Closed -> calibration_report over the season fixture."""

    # --- Stage 1: the tracker starts clean ----------------------------------

    def test_01_tracker_check_passes_on_the_starting_tracker(self, loop_dir):
        type(self).tracker_path = loop_dir / "tracker.md"
        type(self).tracker_path.write_text(_STARTING_TRACKER)
        assert tracker_check(self.tracker_path.read_text()) == []

    # --- Stage 2: add a Drafted row -----------------------------------------

    def test_02_add_a_drafted_row(self, loop_dir):
        new_text = tracker_edit.add_row(
            self.tracker_path.read_text(), "Drafted but not applied", {
                "Company": "Cobalt Grid",
                "Role": "Data Platform Engineer",
                "Source": "Job board",
                "Comp band": "150-180k",
                "Resume": "v1",
                "Next step": "Finish cover letter",
                "Notes": "Strong tech fit",
            })
        self.tracker_path.write_text(new_text)

        assert tracker_check(new_text) == []
        drafted = parse_tracker(new_text)["drafted but not applied"].rows
        assert len(drafted) == 1
        assert drafted[0]["Company"] == "Cobalt Grid"

    # --- Stage 3: archive from a fake apply-out dir -------------------------

    def test_03_archive_application_from_apply_out(self, loop_dir):
        apply_dir = loop_dir / "apply-out" / "cobalt-grid-data-platform-engineer"
        apply_dir.mkdir(parents=True)
        (apply_dir / "jd.md").write_text(
            "# Data Platform Engineer at Cobalt Grid\n\n"
            "We are building the data platform that powers reporting.\n")
        (apply_dir / "resume.typ").write_text(
            '#let name = "Example Persona"\n')
        (apply_dir / "cover.typ").write_text(
            '#let name = "Example Persona"\n')

        type(self).archive_dir = loop_dir / "archive"
        dest = archive_application(apply_dir, self.archive_dir, {
            "company": "Cobalt Grid",
            "role": "Data Platform Engineer",
            "applied": "2026-09-01",
        })
        type(self).slug_dir = dest

        assert dest.name == "cobalt-grid-data-platform-engineer"
        assert (dest / "jd.md").is_file()
        assert (dest / "resume.typ").is_file()

        outcome = read_outcome(dest)
        assert outcome["company"] == "Cobalt Grid"
        assert outcome["role"] == "Data Platform Engineer"
        assert outcome["followups"] == 0
        assert outcome["log"] == ["- 2026-09-01: applied"]

    # --- Stage 4: move Drafted -> Active, --set equivalents via the API -----

    def test_04_move_drafted_to_active_with_set_equivalents(self, loop_dir):
        new_text = tracker_edit.move_row(
            self.tracker_path.read_text(),
            "Cobalt Grid", "Data Platform Engineer",
            "Drafted but not applied", "Active", {
                "Stage": "Applied",
                "Last touch": "2026-09-01",
                "Next step": "Wait for response",
            })
        self.tracker_path.write_text(new_text)

        assert tracker_check(new_text) == []
        sections = parse_tracker(new_text)
        assert len(sections["drafted but not applied"].rows) == 0

        active_row = sections["active"].rows[0]
        assert active_row["Company"] == "Cobalt Grid"
        assert active_row["Stage"] == "Applied"
        assert active_row["Last touch"] == "2026-09-01"
        assert active_row["Next step"] == "Wait for response"
        # Comp band existed in Drafted and Active alike, and was not part of
        # `extra` — move_row carries it across by shared column name.
        assert active_row["Comp band"] == "150-180k"

    # --- Stage 5: touch Last touch -------------------------------------------

    def test_05_touch_last_touch(self, loop_dir):
        new_text = tracker_edit.touch_row(
            self.tracker_path.read_text(), "Active",
            "Cobalt Grid", "Data Platform Engineer",
            "Last touch", "2026-09-01")
        self.tracker_path.write_text(new_text)

        assert tracker_check(new_text) == []
        row = parse_tracker(new_text)["active"].rows[0]
        assert row["Last touch"] == "2026-09-01"

    # --- Stage 6: stale scan finds the quiet row ----------------------------

    def test_06_stale_scan_finds_the_quiet_row(self, loop_dir):
        stale, unknown_touch = stale_active(
            self.tracker_path.read_text(), date(2026, 9, 20), 10)

        assert unknown_touch == []
        assert len(stale) == 1
        assert stale[0].company == "Cobalt Grid"
        assert stale[0].role == "Data Platform Engineer"
        assert stale[0].days_quiet == 19

    # --- Stage 7: bump_followup x2 OK, third raises FollowupCapError -------

    def test_07_bump_followup_twice_then_cap_refuses(self, loop_dir):
        assert bump_followup(self.slug_dir) == 1
        assert bump_followup(self.slug_dir) == 2
        with pytest.raises(FollowupCapError):
            bump_followup(self.slug_dir)

        # A refused bump must not have written anything — the count stays 2.
        assert read_outcome(self.slug_dir)["followups"] == 2

    # --- Stage 8: move two rows to Closed -----------------------------------

    def test_08_move_two_rows_to_closed(self, loop_dir):
        # A second Active row to close out as "No response" — added straight
        # to Active (never drafted), the way an application made off a
        # posting with no prior "Drafted" stage would be.
        text = tracker_edit.add_row(self.tracker_path.read_text(), "Active", {
            "Company": "Meridian Analytics",
            "Role": "Analytics Engineer",
            "Source": "Referral",
            "Stage": "Applied",
            "Comp band": "140-165k",
            "Last touch": "2026-08-01",
            "Next step": "Wait for response",
            "Notes": "",
        })
        assert tracker_check(text) == []

        text = tracker_edit.move_row(
            text, "Cobalt Grid", "Data Platform Engineer", "Active", "Closed", {
                "Date closed": "2026-09-25",
                "Outcome": "Offer",
                "Reason": "Strong final round, comp matched target",
                "Carry-forward lesson": "Lead with the platform-migration story earlier",
            })
        text = tracker_edit.move_row(
            text, "Meridian Analytics", "Analytics Engineer", "Active", "Closed", {
                "Date closed": "2026-09-26",
                "Outcome": "No response",
                "Reason": "Recruiter went quiet after the phone screen",
                "Carry-forward lesson": "Follow up sooner after a screen",
            })
        self.tracker_path.write_text(text)

        assert tracker_check(text) == []
        sections = parse_tracker(text)
        assert len(sections["active"].rows) == 0
        closed = {r["Company"]: r for r in sections["closed"].rows}
        assert closed["Cobalt Grid"]["Outcome"] == "Offer"
        assert closed["Cobalt Grid"]["Date closed"] == "2026-09-25"
        assert closed["Meridian Analytics"]["Outcome"] == "No response"
        assert closed["Meridian Analytics"]["Reason"] == (
            "Recruiter went quiet after the phone screen")

    # --- Stage 9: calibration_report over the season fixture ---------------

    def test_09_calibration_report_yields_pinned_proposals_and_the_never_apply_line(
            self, tmp_path):
        # The synthetic season (tests/fixtures_season.py), not the two-row
        # chain built above — the chain proves the mechanics compose, the
        # season is what the spec's done-condition ("sane proposals") is
        # actually pinned against.
        season = build_season(tmp_path)
        report = calibration_report(
            season.tracker_text, season.archive_dir, season.cfg)

        assert (
            "- `weights.yaml`: consider lowering `unlisted_comp_pts` — "
            "5 of 6 interviewed applications had comp listed in the JD, "
            "vs 1 of 7 negative-outcome" in report)
        assert (
            "- `rules.yaml`: consider tightening `rules` — "
            "5 of 7 negative-outcome applications had kill-rule language "
            "in the JD, vs 0 of 6 interviewed" in report)

        assert "## Suppressed proposals" in report
        assert (
            "- remote language in the JD: gap below threshold" in report)
        assert (
            "- a title-tier hit on the role title: gap below threshold"
            in report)

        # The report's own closing honesty line — calibrate.py has no
        # --apply flag and never will.
        assert "never edits config" in report
        assert "by hand" in report


# --- Real-shape import: the exact house tracker shape, fictional data ------
#
# Same section names and column headers as tests/fixtures_tracker.py's
# VALID_TRACKER (the Global Constraints contract), PLUS a repeated
# Company+Role in Closed — a legitimate reapplication months apart, which
# tracker_schema.py's _DUPLICATE_GATED_SECTIONS deliberately excludes Closed
# from (Orchestrator ruling 2026-09-13). VALID_TRACKER alone doesn't exercise
# that, so this fixture adds it on top of the parenthetical Research heading
# and the annotated Last-touch cell VALID_TRACKER already carries.

REAL_SHAPE_TRACKER = """\
## Active

| Company | Role | Source | Stage | Comp band | Last touch | Next step | Notes |
|---|---|---|---|---|---|---|---|
| Cobalt Grid | Data Platform Engineer | LinkedIn | HM round | 150-180k | 2026-09-10 (sent reply) | Send follow-up | Strong tech fit |
| Harborlight (via referral) | Senior Data Engineer | Referral | Screen | 160-190k | 2026-09-12 | Await scheduling | Warm intro from Alex |

## Drafted but not applied

| Company | Role | Source | Comp band | Resume | Next step | Notes |
|---|---|---|---|---|---|---|
| Meridian Analytics | Analytics Engineer | Job board | 140-165k | v3 | Finish cover letter | JD emphasizes SQL |

## Research (JD filed, no work started)

| Company | Role | Comp band | Lean | Notes |
|---|---|---|---|---|
| Tessellate | Platform Engineer | 145-170k | Lean yes | Series B, remote-first |
| Pinecrest Software | Data Engineer | Unlisted | Lean no | Onsite only |

## Closed

| Company | Role | Date closed | Outcome | Reason | Carry-forward lesson |
|---|---|---|---|---|---|
| Northwind Analytics | Data Platform Engineer | 2026-03-10 | Rejected at screen | Comp band below floor | Confirm comp band before the screen |
| Northwind Analytics | Data Platform Engineer | 2026-08-20 | Offer | Reapplied 5 months later, stronger fit on the second pass | None yet |
| Voss Continuum | Data Engineer | 2026-07-15 | Withdrew | Took a different offer | Confirm timeline earlier next time |
"""


def test_real_shape_tracker_imports_clean_with_zero_violations():
    # Pins the "owner's tracker imports clean" contract at the shape level:
    # exact real section names and column headers, a parenthetical Research
    # heading, an annotated Last-touch cell, and a repeated Company+Role in
    # Closed all coexist with zero violations.
    assert tracker_check(REAL_SHAPE_TRACKER) == []


def test_real_shape_tracker_repeated_closed_row_is_not_flagged_as_duplicate():
    # Spelled out as its own assertion so a future regression that re-gates
    # Closed for duplicates fails here by name, not just as a stray entry in
    # the violations list above.
    violations = tracker_check(REAL_SHAPE_TRACKER)
    assert not any("duplicate" in v.lower() for v in violations)
    assert not any("Northwind Analytics" in v for v in violations)


# --- One subprocess pin of the CLI surface: check -> add -> stale ----------
#
# Every other test in this file drives the engine APIs directly. This one
# alone shells out to `tracker_cli.py` the way a human (or /outcome,
# /followup) actually would, so the CLI's argument parsing and process exit
# codes are pinned too, not just the functions underneath it.

def test_cli_end_to_end_check_add_stale(tmp_path):
    tracker_path = tmp_path / "tracker.md"
    tracker_path.write_text(
        "## Active\n\n"
        "| Company | Role | Last touch |\n|---|---|---|\n"
        "\n"
        "## Closed\n\n"
        "| Company | Role | Date closed | Outcome |\n|---|---|---|---|\n")

    check = subprocess.run(
        [sys.executable, str(CLI), "check", str(tracker_path)],
        capture_output=True, text=True, cwd=REPO_ROOT)
    assert check.returncode == 0, check.stderr
    assert "tracker: OK" in check.stdout

    add = subprocess.run(
        [sys.executable, str(CLI), "add", str(tracker_path),
         "--section", "Active",
         "--set", "Company=Cobalt Grid",
         "--set", "Role=Data Platform Engineer",
         "--set", "Last touch=2026-08-01"],
        capture_output=True, text=True, cwd=REPO_ROOT)
    assert add.returncode == 0, add.stderr
    assert "Cobalt Grid" in tracker_path.read_text()

    stale = subprocess.run(
        [sys.executable, str(CLI), "stale", str(tracker_path),
         "--days", "10", "--today", "2026-09-20"],
        capture_output=True, text=True, cwd=REPO_ROOT)
    assert stale.returncode == 0, stale.stderr
    assert "stale (10+ days quiet):" in stale.stdout
    assert "Cobalt Grid" in stale.stdout
    assert "50d quiet" in stale.stdout
