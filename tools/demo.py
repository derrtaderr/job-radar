#!/usr/bin/env python3
"""demo — an offline, no-network walk of the whole system on the fictional
`config.example` persona, writing everything into `--out` (default
`demo-out/`, gitignored).

This is NOT a way to run your own search, and it never touches one:

- It loads `config.example` EXPLICITLY, never `config/`. Your real judgment
  (kill rules, comp floor, profile) and your real seen-job state are never
  read, and this script has no path to either.
- `today` is a fixed module constant (DEMO_TODAY below), never
  `datetime.date.today()`. The same code produces the same queue.md and the
  same calibration report every time it runs, on any machine, on any date.
- It sends nothing and edits nothing. Every byte it writes lands under
  `--out`.

What it runs, in order:

1. **Radar.** Twelve canned postings (`tests/fixtures_demo_rows.py`) through
   the real pipeline (`engine/radar/pipeline.py`) with empty state and an
   empty tracker set, rendered into a day folder by the real report code
   (`engine/radar/report.py`) — a queue with kills shown, never swallowed.
2. **Drafting.** If `typst` is on PATH: compiles the example resume and
   cover letter (`tests/fixtures/resume_example.typ`, `.../cover_example.typ`
   — the same fictional persona, already filled in), verifies each PDF
   (`tools/verify_pdf.py`), and runs an ATS keyword check
   (`tools/ats_check.py`) against a canned job description. If `typst` isn't
   on PATH, this branch prints a note and is skipped — everything else in
   the demo still runs.
3. **Loop.** Builds the synthetic mini-season (`tests/fixtures_season.py`) —
   twenty fictional closed applications with real archived outcomes — and
   renders a calibration report (`engine/loop/calibrate.py`) over it.

Usage:

    python tools/demo.py [--out DIR]
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    # Running as a script (`python tools/demo.py`) rather than imported as
    # `tools.demo` — put the repo root on sys.path so the cross-package
    # imports below (engine.*, tools.*, tests.*) resolve.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.draft.compile import compile_pdf
from engine.draft.registry import load_registry
from engine.loop.calibrate import calibration_report
from engine.radar.config import load_config
from engine.radar.pipeline import pipeline
from engine.radar.report import day_paths, write_jds, write_report
from engine.radar.state import save_state
from tools.ats_check import ats_report
from tools.verify_pdf import verify

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fixed, never the real clock — see the module docstring's determinism note.
DEMO_TODAY = date(2026, 9, 13)

PERSONA_EMAIL = "alex.rivera@example.com"
PERSONA_PHONE = "(303) 555-0142"

# A canned job description for the drafting branch's ATS check — a different
# fictional company from the twelve radar postings, so nothing here overlaps
# what the radar pass demonstrates. Repeats the resume fixture's own stack
# (Python, Airflow, dbt, Snowflake, Kafka) so the keyword-coverage report has
# real hits to show, not just gaps.
CANNED_JD = """
Senior Data Engineer — Larchmont Data Systems

Larchmont Data Systems builds workflow automation for mid-market logistics
teams. We're hiring a Senior Data Engineer to own the pipelines that feed our
operations dashboards.

Compensation: $150,000 - $185,000 base, plus equity and full benefits.
Location: Remote (US).

What you'll do:
- Design and operate the batch and streaming pipelines that move raw
  operational data into our warehouse. Python is our primary language for
  pipeline code, and you will be writing Python daily.
- Own our Airflow deployment end to end. Prior Airflow experience running
  production DAGs is required.
- Build and maintain dbt models that transform raw tables into the marts our
  operations team queries. Comfort writing dbt tests is expected.
- Manage our Snowflake warehouse, including query performance tuning.
  Snowflake experience at scale is a must for this role.
- Partner with the product team to instrument new data sources as we expand
  into new markets.

What we're looking for:
- 5+ years as a data engineer, with production Python and Airflow
  experience.
- Hands-on dbt modeling experience.
- Experience with Kafka or another streaming platform is a plus.
- A track record of owning a data platform in production, not just building
  it.

Larchmont Data Systems is a fully remote company.
""".strip()

NEVER_SENDS_LINE = (
    "Nothing here sends anything or edits any config — the demo reads "
    "config.example and writes only into its --out directory.")


def _parse(argv):
    parser = argparse.ArgumentParser(
        prog="demo",
        description="Offline walk of job-radar on the fictional config.example persona.")
    parser.add_argument("--out", default="demo-out", metavar="DIR",
                        help="output directory (default: demo-out/)")
    return parser.parse_args(argv)


def _reset_out_dir(out_dir: Path) -> None:
    """Start clean every run. write_report APPENDS to an existing same-day
    queue.md by design (a real second run shouldn't destroy the first run's
    queue) — but that means a demo rerun into the SAME directory would grow
    the file on every invocation instead of reproducing it. The demo isn't a
    real search with something to preserve, so it clears its own output
    directory first instead of relying on that append behavior."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)


def _run_radar_pass(out_dir: Path) -> tuple:
    """Loads config.example (copied into out_dir so its own output_dir and
    state_file resolve inside --out, never touching the repo root), runs the
    twelve canned rows through the real pipeline, and writes the day folder
    through the real report code. Returns (cfg, list-of-artifact-paths)."""
    config_dir = out_dir / "config"
    shutil.copytree(REPO_ROOT / "config.example", config_dir)
    cfg = load_config(config_dir)

    from tests.fixtures_demo_rows import DEMO_ROWS

    survivors, killed, new_state = pipeline(DEMO_ROWS, {}, cfg, set(), DEMO_TODAY)

    day_dir, queue_path, jd_dir = day_paths(cfg.output_dir, DEMO_TODAY)
    jds_written = write_jds(jd_dir, survivors, killed, str(DEMO_TODAY))
    write_report(queue_path, survivors, killed, str(DEMO_TODAY))
    save_state(new_state, cfg.state_file)

    print(f"[1/3] radar: {len(survivors)} queued, {len(killed)} killed "
          f"(kills: {', '.join(sorted({f[0] for k in killed for f in k['flags']}))}), "
          f"{jds_written} JDs saved -> {queue_path}")

    return cfg, [queue_path, jd_dir]


def _run_drafting_pass(out_dir: Path) -> list:
    """If typst is on PATH: compile the example resume + cover letter,
    verify each PDF, and run ats_check against CANNED_JD. Otherwise, print a
    note and return no artifacts — the rest of the demo is unaffected."""
    if shutil.which("typst") is None:
        print("[2/3] drafting: typst not found on PATH — skipping compile / "
              "verify_pdf / ats_check (install with `brew install typst` to "
              "see this branch). Nothing else in the demo is affected.")
        return []

    registry = load_registry(REPO_ROOT)
    resume_limit = registry.default("resume").page_limit
    cover_limit = registry.default("cover").page_limit

    draft_dir = out_dir / "drafting"
    draft_dir.mkdir(parents=True)

    resume_src = REPO_ROOT / "tests" / "fixtures" / "resume_example.typ"
    cover_src = REPO_ROOT / "tests" / "fixtures" / "cover_example.typ"
    resume_pdf = draft_dir / "resume.pdf"
    cover_pdf = draft_dir / "cover.pdf"

    resume_ok, resume_log = compile_pdf(resume_src, out=resume_pdf)
    if not resume_ok:
        raise RuntimeError(f"demo: resume fixture failed to compile:\n{resume_log}")
    cover_ok, cover_log = compile_pdf(cover_src, out=cover_pdf)
    if not cover_ok:
        raise RuntimeError(f"demo: cover fixture failed to compile:\n{cover_log}")

    resume_violations = verify(resume_pdf, resume_limit, [PERSONA_EMAIL])
    cover_violations = verify(cover_pdf, cover_limit, ["Sincerely"])

    jd_path = draft_dir / "jd.md"
    jd_path.write_text(CANNED_JD + "\n")

    hard_ok, report_text = ats_report(
        resume_pdf, CANNED_JD, {"email": PERSONA_EMAIL, "phone": PERSONA_PHONE})
    ats_path = draft_dir / "ats-report.md"
    ats_path.write_text(report_text + "\n")

    status = "clean" if (not resume_violations and not cover_violations and hard_ok) else "FLAGGED"
    print(f"[2/3] drafting: resume + cover compiled and verified ({status}) "
          f"-> {resume_pdf}, {cover_pdf}, {ats_path}")
    if resume_violations:
        print(f"       resume verify_pdf violations: {resume_violations}")
    if cover_violations:
        print(f"       cover verify_pdf violations: {cover_violations}")

    return [resume_pdf, cover_pdf, jd_path, ats_path]


def _run_loop_pass(out_dir: Path) -> Path:
    """Builds the synthetic mini-season and renders its calibration report.
    A separate, self-contained config lives under loop-demo/config — the
    season fixture pins its own rules.yaml/weights.yaml on purpose (see
    tests/fixtures_season.py's module docstring), independent of the config
    the radar pass above loads."""
    from tests.fixtures_season import build_season

    season_dir = out_dir / "loop-demo"
    season_dir.mkdir(parents=True)
    season = build_season(season_dir)

    report = calibration_report(season.tracker_text, season.archive_dir, season.cfg)
    calibration_path = season_dir / "calibration-report.md"
    calibration_path.write_text(report)

    print(f"[3/3] loop: {season.closed_count} closed rows, {season.joined_count} "
          f"joined to an archive, calibration report -> {calibration_path}")

    return calibration_path


def main(argv=None) -> int:
    args = _parse(argv)
    out_dir = Path(args.out).resolve()
    _reset_out_dir(out_dir)

    print("=" * 72)
    print("job-radar demo — fictional config.example persona, no network, "
          "nothing sent")
    print(f"output directory: {out_dir}")
    print("=" * 72)

    artifacts = []
    _, radar_artifacts = _run_radar_pass(out_dir)
    artifacts += radar_artifacts
    artifacts += _run_drafting_pass(out_dir)
    artifacts.append(_run_loop_pass(out_dir))

    print("-" * 72)
    print("Artifacts written:")
    for path in artifacts:
        print(f"  {path}")
    print(NEVER_SENDS_LINE)
    print("-" * 72)

    return 0


if __name__ == "__main__":
    sys.exit(main())
