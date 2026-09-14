"""A synthetic season — one fictional job search, resolved, built in tmp_path.

`build_season(tmp_path)` writes three things a calibration run needs: a tracker
whose Closed section carries twenty rows across every outcome class, an archive
tree built through the REAL `archive_application` (not hand-written outcome.md
files, so the join is exercised against what that function actually produces),
and a config directory loaded through the REAL `load_config`.

Every company, role, and JD here is invented. None of it describes a real
search, a real posting, or a real employer.

## Why the numbers are what they are

The spec's done-condition for calibration is "sane proposals" — a report that
proposes exactly what the data supports and NAMES what it cannot. So the JD
texts are constructed so that, of the four contrasts, exactly TWO clear the
floor and exactly TWO land in suppressed:

    contrast          interviewed (N=6)   negative (N=7)   gap    verdict
    comp listed       5 of 6  (83%)       1 of 7  (14%)    69pt   PROPOSAL
    remote language   4 of 6  (67%)       5 of 7  (71%)     5pt   suppressed
    title-tier hit    4 of 6  (67%)       4 of 7  (57%)    10pt   suppressed
    kill-rule terms   0 of 6   (0%)       5 of 7  (71%)    71pt   PROPOSAL

Twenty Closed rows, thirteen of them archived, so the join rate lands at 65%
rather than a suspiciously clean 100% — an unjoined row is a real condition
(applied before the archive existed, applied outside the tool) and the report
has to count it rather than quietly shrinking its own denominator.

## What this fixture deliberately does NOT exercise

Both suppressed contrasts above fail on the GAP, not on N. That is forced, not
an oversight: three of the four contrasts read the same jd.md, so their Ns are
always identical, which means a season can have either four contrasts with
enough data or one — never a mix that yields two proposals AND an
insufficient-data suppression. The insufficient-data branch is pinned
separately in test_calibrate.py against a deliberately thin season.

## Config coupling

rules.yaml and weights.yaml are written here in full rather than copied from
config.example, because the pinned Ns above depend on the exact title_tiers
patterns and kill-rule patterns. Copying the example would let an unrelated
edit to the persona's own judgment files silently change what this fixture
proves. queries.yaml, settings.yaml, and exclusions.txt come from
config.example — calibration never reads them, and load_config requires them.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from engine.loop.archive import archive_application
from engine.radar.config import load_config

_EXAMPLE_CONFIG = Path(__file__).parent.parent / "config.example"

# --- JD building blocks -----------------------------------------------------
# Each is one sentence, isolated on its own line, because body_stated_max reads
# an 80-character window around comp-context language — a stray "$" figure in a
# neighbouring sentence would leak into the comp feature and quietly change the
# pinned Ns.

_COMP_LISTED = (
    "Compensation: the base salary range for this role is "
    "$165,000 to $195,000 per year.")
_COMP_UNLISTED = (
    "Compensation is competitive and will be discussed during the "
    "hiring process.")
_REMOTE = (
    "This is a fully remote position, open to candidates anywhere in "
    "the United States.")
_ONSITE = "The team sits together in our Chicago office four days a week."
_KILL_MANAGEMENT = (
    "You will manage a team of five engineers and own the reporting roadmap.")
_KILL_QUOTA = "This is a quota-carrying role with a named account list."
_NO_KILL = (
    "This is an individual contributor role reporting to the Head of Data.")

_RULES_YAML = """\
comp_floor: 120000
commute_locations: 'Denver|Boulder'
rules:
  - name: not-ic
    reason: people-management as primary scope
    pattern: 'manage a team|direct reports'
  - name: bdr-scope
    reason: quota language means a sales seat, not an engineering seat
    pattern: 'quota[- ]carrying|carry a quota'
"""

_WEIGHTS_YAML = """\
title_tiers:
  - {pattern: 'data platform engineer', points: 30}
  - {pattern: 'senior data engineer', points: 25}
  - {pattern: 'data engineer', points: 20}
  - {pattern: 'analytics engineer', points: 15}
default_title_pts: 5
comp_target: 180000
target_comp_pts: 20
floor_comp_pts: 15
unlisted_comp_pts: 8
fresh_days: 3
fresh_pts: 20
week_pts: 12
old_pts: 5
remote_pts: 10
seniority_pattern: 'senior|staff|principal|lead'
seniority_pts: 8
"""

# --- the season -------------------------------------------------------------
# (company, role, outcome, archived, comp_listed, remote, kill_terms)
# Joined and unjoined rows are interleaved the way a real tracker accumulates
# them, so nothing in the join depends on the archived rows arriving first.
SEASON_ROWS = (
    ("Cobalt Grid", "Data Platform Engineer",
     "Offer", True, True, True, False),
    ("Larkspur Grid", "Data Engineer",
     "Rejected at phone screen", False, False, False, False),
    ("Meridian Analytics", "Senior Data Engineer",
     "Offer declined", True, True, True, False),
    ("Pinecrest Software", "Data Engineer",
     "Rejected at screen", True, True, True, True),
    ("Tessellate", "Data Engineer",
     "Rejected after onsite", True, True, True, False),
    ("Ashfield Metrics", "Data Engineer",
     "Screened out", False, False, False, False),
    ("Bellweather Labs", "Data Platform Engineer",
     "Rejected after recruiter screen", True, False, True, True),
    ("Harborlight", "Analytics Engineer",
     "Rejected at final round", True, True, True, False),
    ("Quill and Sparrow", "Senior Data Engineer",
     "No response", True, False, True, True),
    ("Thornwood Data", "Analytics Engineer",
     "No response", False, False, False, False),
    ("Voss Continuum", "Revenue Operations Engineer",
     "Rejected after HM round", True, True, False, False),
    ("Fernmark Systems", "Analytics Engineer",
     "Ghosted", True, False, True, True),
    ("Aldgate Partners", "Solutions Architect",
     "Timed out", True, False, True, True),
    ("Cindermill Tech", "Data Engineer",
     "Timed out, role refilled", False, False, False, False),
    ("Northwind Analytics", "Growth Systems Lead",
     "Rejected post-panel", True, False, False, False),
    ("Kestrel Dynamics", "Platform Reliability Engineer",
     "No response after 6 weeks", True, False, False, False),
    ("Saltmarsh Software", "Data Platform Engineer",
     "Withdrew", False, False, False, False),
    ("Orrery Compute", "Growth Systems Lead",
     "Silence", True, False, False, False),
    ("Hollowbrook Systems", "Senior Data Engineer",
     "Withdrawn by me", False, False, False, False),
    ("Marbridge Group", "Data Engineer",
     "Role frozen", False, False, False, False),
)

_ACTIVE_SECTION = """\
## Active

| Company | Role | Source | Last touch | Next step |
|---|---|---|---|---|
| Ravenswood Data | Data Engineer | Job board | 2026-09-10 | Await screen |

"""


@dataclass
class Season:
    """Everything a calibration run needs, plus the two counts the report
    header is pinned against."""
    tracker_text: str
    tracker_path: Path
    archive_dir: Path
    config_dir: Path
    cfg: object
    closed_count: int
    joined_count: int


def _slug(company: str, role: str) -> str:
    raw = f"{company} {role}".lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", raw)).strip("-")


def jd_text(company: str, role: str, *, comp: bool, remote: bool,
            kill: bool) -> str:
    """One fictional JD carrying exactly the features asked for, and no
    others. Every feature sentence sits alone so no two of them share a
    detection window."""
    lines = [
        f"# {role} at {company}",
        "",
        "We are building the data platform that powers reporting across "
        "the business.",
        "",
        _COMP_LISTED if comp else _COMP_UNLISTED,
        "",
        _REMOTE if remote else _ONSITE,
        "",
    ]
    if kill:
        # Two different kill rules fire across the season, so the contrast
        # measures "any kill rule matched", not one pattern's quirks.
        lines.append(_KILL_QUOTA if role == "Solutions Architect"
                     else _KILL_MANAGEMENT)
    else:
        lines.append(_NO_KILL)
    return "\n".join(lines) + "\n"


def season_tracker_text() -> str:
    """The tracker markdown alone — for tests that need the rows without
    paying for an archive tree on disk."""
    header = (
        "## Closed\n\n"
        "| Company | Role | Date closed | Outcome | Reason | "
        "Carry-forward lesson |\n"
        "|---|---|---|---|---|---|\n")
    rows = []
    for idx, (company, role, outcome, *_rest) in enumerate(SEASON_ROWS):
        # Dates are generated from the row's position, never from the clock —
        # the report has to be byte-reproducible from the same inputs.
        closed = f"2026-{(idx % 6) + 3:02d}-{(idx % 27) + 1:02d}"
        rows.append(
            f"| {company} | {role} | {closed} | {outcome} | "
            f"See notes | Carry forward |\n")
    return _ACTIVE_SECTION + header + "".join(rows)


def build_config(tmp_path: Path) -> Path:
    """A loadable config directory whose judgment layer is pinned here."""
    config_dir = tmp_path / "config"
    shutil.copytree(_EXAMPLE_CONFIG, config_dir)
    (config_dir / "rules.yaml").write_text(_RULES_YAML)
    (config_dir / "weights.yaml").write_text(_WEIGHTS_YAML)
    return config_dir


def build_season(tmp_path: Path) -> Season:
    """Write the whole synthetic season under `tmp_path` and return it."""
    tracker_text = season_tracker_text()
    tracker_path = tmp_path / "tracker.md"
    tracker_path.write_text(tracker_text)

    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    apply_root = tmp_path / "apply-out"

    joined = 0
    for company, role, _outcome, archived, comp, remote, kill in SEASON_ROWS:
        if not archived:
            continue
        joined += 1
        slug = _slug(company, role)
        apply_dir = apply_root / slug
        apply_dir.mkdir(parents=True)
        (apply_dir / "jd.md").write_text(
            jd_text(company, role, comp=comp, remote=remote, kill=kill))
        (apply_dir / "resume.typ").write_text("#let name = \"Example Persona\"\n")
        archive_application(apply_dir, archive_dir, {
            "company": company, "role": role, "applied": "2026-05-01"})

    config_dir = build_config(tmp_path)

    return Season(
        tracker_text=tracker_text,
        tracker_path=tracker_path,
        archive_dir=archive_dir,
        config_dir=config_dir,
        cfg=load_config(config_dir),
        closed_count=len(SEASON_ROWS),
        joined_count=joined,
    )
